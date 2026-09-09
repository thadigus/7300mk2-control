# CI-V Fundamentals (the ICOM Communications Interface V)

This is the **generic CI-V layer** - the command/response language spoken by the
radio's application. It is identical whether the frames travel over USB serial or
inside the network transport described in [`PROTOCOL.md`](./PROTOCOL.md). If you
understand this page, the network wrapper is "just" how the `FE FE … FD` bytes
get to the radio.

**Primary source:** ICOM's official *CI-V Reference Guide* (vendored at
[`reference/ICOM_CI-V_Reference_Guide_IC-R15.pdf`](./reference/ICOM_CI-V_Reference_Guide_IC-R15.pdf)).
That guide is written for the IC-R15 receiver, but the **frame format, addressing,
OK/NG, echo-back, transceive, and BCD encoding are common to the entire CI-V
family, including the IC-7300MK2.** Model-specific opcodes live in
[`COMMANDS.md`](./COMMANDS.md); the differences from the R15 are noted at the
bottom of this page.

---

## 1. Frame format

Every CI-V message has the same seven-part shape (ICOM's own numbering):

```
 ┌1─────┬2────┬3────┬4────┬5────┬6──────────┬7──┐
 │ FE FE │ TO  │ FROM│ Cn  │ Sc  │ data area │ FD│
 └───────┴─────┴─────┴─────┴─────┴───────────┴───┘
   1 Preamble (fixed, always two 0xFE)
   2 TO   - destination CI-V address
   3 FROM - source CI-V address
   4 Cn   - command number            (see COMMANDS.md)
   5 Sc   - sub command number        (optional, command-dependent)
   6 data - BCD / binary payload      (optional, command-dependent)
   7 FD   - end-of-message (fixed)
```

- **Preamble** is exactly `FE FE`. (On a shared serial bus a wake-up burst of
  extra `FE` bytes may precede it - see §6. Over the network this is never
  needed.)
- The **data area** and **sub command** are present only for the commands that
  need them.
- Length is implicit: a frame runs from `FE FE` to the first `FD`.

### The four message directions

| Direction | Frame | Meaning |
|-----------|-------|---------|
| Controller → radio | `FE FE <radio> <ctrl> Cn [Sc] [data] FD` | a command |
| Radio → controller | `FE FE <ctrl> <radio> Cn [Sc] [data] FD` | reply with data |
| Radio → controller | `FE FE <ctrl> <radio> FB FD` | **OK** - command accepted, no data to return |
| Radio → controller | `FE FE <ctrl> <radio> FA FD` | **NG** - command rejected / not available |

Note the **addresses swap** between the command and the reply: whoever sends puts
its own address in FROM. `FB` (0xFB) and `FA` (0xFA) are fixed OK/NG codes.

---

## 2. Addressing

Each CI-V device has a one-byte address. The controller (PC) uses `E0` by
convention (some software uses `0xE1`).

| Address | Device |
|---------|--------|
| `E0` | controller / PC (our end) - the conventional default |
| `B0` | IC-R15 default (example, from the reference guide) |
| **`B6`** | **IC-7300MK2 default** (read live from the capabilities packet) |
| `94` | original IC-7300 default (the mk2 does **not** use this) |
| `00` | broadcast - every radio on the bus responds |

**Verified on the 7300MK2:** frames to `B6` work; frames to `00` (broadcast) work
and the radio answers from `B6`; frames to `94` are ignored. Always confirm the
address by reading it - command `19 00` returns the radio's own CI-V address, and
the network capabilities packet reports it too.

---

## 3. Echo-back

On a bus where TX and RX share a line (USB serial, and the LAN CI-V stream too),
the radio **echoes the controller's frame back** before it answers. The
7300MK2's LAN stream does this: after you send `FE FE B6 E0 03 FD` you receive
your own frame back, then the real reply. **Filter echoes by destination
address** - a genuine reply has TO = your controller address (`E0`); an echo has
TO = the radio address (`B6`). "CI-V Echo Back" is also a menu switch on the
radio (per the reference guide, USB jack); the network path echoes regardless.

---

## 4. Transceive (unsolicited updates)

When **CI-V Transceive** is ON (7300MK2 setting `1A 05 00 89` = `01`; verified ON
on our radio), the radio spontaneously broadcasts a frame whenever the operator
changes something on the front panel - e.g. turning the VFO emits a
`00` (send frequency) frame, changing mode emits `01`. These arrive unsolicited
on the same CI-V channel, addressed to `00` (broadcast).

Consequences for the library:
- You must tolerate inbound frames you didn't request. Parse by
  `(command, subcommand)`, not by "the next packet after my query."
- Commands `00` (send frequency) and `01` (send mode) are the *transceive*
  variants of `05`/`06`; you generally **read** with `03`/`04`/`25`/`26` and
  **write** with `05`/`06`, and *receive* `00`/`01` as notifications.
- If you don't want notifications, they can be turned off, but leaving them on is
  the easy way to keep a cached radio state fresh.

---

## 5. Number encoding

### 5.1 Frequency - little-endian packed BCD

Frequencies are sent as **5 bytes of packed BCD, least-significant byte first**,
in **1 Hz** units on the 7300MK2. Two decimal digits per byte.

```
7,217,948 Hz  →  digit pairs (LSB first):  48 79 21 07 00
                 byte0 = 48 → tens/units  "48"  (   48 Hz)
                 byte1 = 79 → x100        "79"  ( 79xx Hz)
                 byte2 = 21 → x10k        "21"
                 byte3 = 07 → x1M         "07"
                 byte4 = 00 → x100M       "00"
   read back:  reverse bytes → 00 07 21 79 48 → 0007217948 → 7.217948 MHz
```

Decode in code:

```python
def decode_freq(b):          # b = 5 bytes, little-endian BCD
    digits = ''.join('%x%x' % (x >> 4, x & 0xF) for x in reversed(b))
    return int(digits)       # Hz

def encode_freq(hz):
    s = '%010d' % hz         # 10 digits
    return bytes(int(s[i:i+2], 16) for i in range(8, -1, -2))  # LSB first
```

> The ICOM reference guide draws this as a digit-position grid (1 Hz digit fixed
> on some receivers, 1 GHz digit fixed, etc.). On the 7300MK2 all 1 Hz-100 MHz
> digits are freely settable within the radio's range (0.03-74.8 MHz RX / ham
> bands TX). Some receivers restrict the 10 Hz digit based on the 100 Hz digit;
> the 7300MK2 tunes to 1 Hz.

### 5.2 Levels and meters - 2-byte BCD, 0000-0255

Front-panel "0-255" quantities (AF gain, RF power, S-meter, …) are sent as
**2 bytes of BCD encoding the value 0000-0255** (not hex!). Example: RF power at
50% ≈ `01 28` (=128). The reference guide's AF/squelch tables show how the raw
0-255 maps onto the radio's displayed VOL0-VOL39 / LEVELn steps - the wire value
is always the 0-255 BCD number.

```python
def decode_lvl(b):  return int('%02x%02x' % (b[0], b[1]))   # b = 2 bytes BCD
def encode_lvl(v):  return bytes([v // 100, ((v // 10) % 10) << 4 | (v % 10)])
```

### 5.3 On/off, enums - single byte

Booleans and small enums are a single byte: `00`/`01` (off/on), or a small index
(e.g. AGC `00`=OFF `01`=FAST `02`=SLOW). See each command in
[`COMMANDS.md`](./COMMANDS.md).

### 5.4 Signed values - RIT / scope reference

A few values are signed with a separate sign byte (e.g. RIT frequency `21 00` is
`<2-byte BCD magnitude> <00=+/01=->`; scope reference `27 19` similar). Documented
per-command.

---

## 6. Serial-bus wake-up padding (context, not needed on LAN)

Over a slow shared serial bus, the reference guide notes that the **power-ON
command `18 01`** must be preceded by a burst of `FE` bytes to wake the CPU
(≈15 at 4800 bps, 30 at 9600, 60 at 19200). This is a serial-only quirk. **The
network CI-V stream never needs it** - the session is already established and the
radio is awake. Documented here only so the extra `FE`s in serial captures aren't
mistaken for part of the frame.

---

## 7. How the 7300MK2 differs from the R15 reference guide

The vendored guide is a receiver's; use it for the *mechanics*, not the opcode
list. Key differences relevant to the 7300MK2:

| Aspect | IC-R15 (guide) | IC-7300MK2 |
|--------|----------------|------------|
| Default address | `B0` | **`B6`** |
| Frequency resolution | 10 Hz stepped | 1 Hz |
| Modes | AM/AM-N/FM/FM-N/WFM | LSB/USB/AM/CW/RTTY/FM/CW-R/RTTY-R (+ data) |
| VFO select `07` | `D0`/`D1` = A/B band | `00`/`01` = VFO A/B, `A0` equalize, `B0` swap |
| Transmit | none (RX only) | full TX: PTT `1C 00`, TX freq `1C 03`, power `14 0A`, ATU `1C 01`, CW keyer `17` |
| Spectrum scope | none | command group `27` (waveform stream, span, edges, ref) |
| Meters | S-meter only | S/PWR/SWR/ALC/COMP/Vd/Id (`15 11`-`15 16`) |
| Transport | USB serial only | USB serial **and** network (RS-BA1 UDP) |

For the authoritative, model-correct opcode set see **[`COMMANDS.md`](./COMMANDS.md)**.
