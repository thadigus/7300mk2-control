# IC-7300MK2 Network CI-V (UDP) Protocol Specification

**Scope:** this is the **network transport** spec (layers L1-L2 in
[`ARCHITECTURE.md`](./ARCHITECTURE.md)) - how a CI-V session is opened, authed,
and carried over UDP. The CI-V command language it carries is in
[`CIV-FUNDAMENTALS.md`](./CIV-FUNDAMENTALS.md); the opcode list is in
[`COMMANDS.md`](./COMMANDS.md). New here? Read [`ARCHITECTURE.md`](./ARCHITECTURE.md)
first, or [`README.md`](./README.md) for the whole map.

**Status:** Verified against a live IC-7300MK2 at `icom.turnerservices.cloud` on 2026-09-02.
Every packet layout, command, and timing value below was either observed on the
wire or exercised against the live radio.
Cross-checked against the wfview (`icomudp*.cpp`) and kappanhang (`*.go`)
reference implementations.

> **Bottom line for the library:** the radio does **not** speak raw CI-V on any
> UDP port. Port 50002 only carries CI-V *after* a full authenticated session is
> established on the control port 50001. All three earlier investigation notes
> that concluded "port closed / no response" were wrong: they sent bare CI-V
> frames with no session and (in one case) from a sandboxed process that could
> not route to the radio at all. See [Gotchas](#12-gotchas--things-that-bit-us).

---

## 1. Transport overview

The radio implements ICOM's RS-BA1 "remote LAN" protocol - the same one used by
the IC-705, IC-9700, IC-7610, IC-R8600, IC-905. Three **UDP** channels, each a
fully independent little state machine with its own handshake, sequence numbers,
keepalives, and retransmit logic:

| Port  | Channel | Purpose |
|-------|---------|---------|
| 50001 | **control** | session setup, login, auth token, stream negotiation, keepalive |
| 50002 | **CI-V / serial** | bidirectional CI-V command/response frames |
| 50003 | **audio** | RX (and optional TX) audio stream, RTP-ish |

Key facts:

- **All multi-byte integers in the transport wrapper are little-endian**, except
  a handful of fields inside the auth packets that are explicitly big-endian
  (payload size, inner sequence, sample rates, port numbers - flagged below).
- Each channel is opened by the **client** binding a fresh random local UDP port
  and sending to the radio's fixed port. The radio replies to the source
  address/port of whatever it last heard from.
- The radio is reachable by ICMP ping at all times; that tells you nothing about
  whether the CI-V service will answer. Only the handshake does.
- CI-V frames themselves are **normal ICOM CI-V** (`FE FE … FD`) once you strip
  the 21-byte transport header. If you already have CI-V code, you only need to
  implement the wrapper.

### 1.1 Session IDs (`sentid` / `rcvdid`)

Every packet ≥ 16 bytes carries a pair of 32-bit session IDs. The client derives
its own ID from its local IP + local UDP port:

```
my_id = (ip_octet3 << 24) | (ip_octet4 << 16) | (local_udp_port & 0xFFFF)
```

Example: local `192.0.2.50:62981` → `my_id = 0x0232F605`
(`0x02`=2, `0x32`=50, `0xF605`=62981).

The radio's ID (`remote_id`) is random per session; you learn it from the first
`I-AM-HERE` reply and must echo it back in `rcvdid` on every subsequent packet.
Each of the three channels has its **own** independent `(my_id, remote_id)` pair.

---

## 2. Common packet header

The first 16 bytes of (almost) every packet:

```
off  size  field     notes
0x00  u32   len       total datagram length, little-endian
0x04  u16   type      packet type (control packets); 0x00 for data-bearing pkts
0x06  u16   seq       sequence number, little-endian (see §7)
0x08  u32   sentid    sender session id
0x0C  u32   rcvdid    receiver session id
```

"Control" packets are exactly `len = 0x10` and use `type` to say what they are.
Longer packets set `type = 0x00` and carry a payload after the header; their
"meaning" is decoded from length + payload, not from `type`.

### 2.1 Control packet types (16-byte packets)

| type | name | direction | meaning |
|------|------|-----------|---------|
| `0x03` | ARE-YOU-THERE | C→R | open a channel / probe |
| `0x04` | I-AM-HERE | R→C | reply; carries radio's `sentid` |
| `0x06` | ARE-YOU-READY / I-AM-READY | both | `0x06` w/ seq `0x01` from client = "are you ready"; radio's `0x06` = "ready" |
| `0x00` | IDLE | both | keepalive / filler, carries a seq |
| `0x01` | RETRANSMIT | both | request resend of `seq` (see §7) |
| `0x05` | DISCONNECT | C→R | tear the channel down |

---

## 3. Control-channel connect sequence (port 50001)

This is the exact, verified order. Times in the right column are the observed
round-trip latencies on a LAN (~2 ms RTT).

```
CLIENT                                    RADIO            observed
  |  ARE-YOU-THERE (type 0x03) ─────────►  |
  |  ◄───────────── I-AM-HERE (type 0x04)  |   learn remote_id      ~2 ms
  |  ARE-YOU-READY (type 0x06, seq 1) ───► |
  |  ◄──────────── I-AM-READY  (type 0x06) |                        ~1 ms
  |  LOGIN (0x80 bytes) ─────────────────► |   username/password
  |  ◄──────── LOGIN RESPONSE (0x60 bytes) |   token + conn type    ~2 ms
  |  ◄──────── CAPABILITIES  (0xA8 bytes)  |   radio list + civ addr
  |  TOKEN confirm  (0x40, magic 0x02) ──► |
  |  TOKEN renew    (0x40, magic 0x05) ──► |
  |  ◄──────────── TOKEN reply (0x40)      |   response=0 → auth OK  ~2 ms
  |  STREAM REQUEST (0x90 "conninfo") ───► |   ask for civ+audio
  |  ◄──────────── STATUS (0x50 bytes)     |   returns civ/audio ports
  |  ◄──────────── CONNINFO (0x90 bytes)   |   who's connected
  |                                        |
  |  … then open the CI-V and audio channels (§5, §6) …
```

Concurrently, from the moment `I-AM-HERE` arrives, the client must run keepalives
(§8): PING every 500 ms and IDLE every 100 ms, and answer the radio's own PINGs.

### 3.1 LOGIN packet (client → radio, 0x80 = 128 bytes)

```
0x00  u32  len          = 0x00000080
0x04  u16  type         = 0x0000
0x06  u16  seq          tracked seq (see §7)
0x08  u32  sentid       my_id
0x0C  u32  rcvdid       remote_id
0x10  u32  payloadsize  BIG-ENDIAN = 0x00000070 (len-0x10)
0x14  u8   requestreply = 0x01
0x15  u8   requesttype  = 0x00   (login)
0x16  u16  innerseq     BIG-ENDIAN, starts 0x0030, +1 each auth packet
0x18  u16  (zero)
0x1A  u16  tokrequest   random 16-bit, LITTLE-ENDIAN, echoed by radio
0x1C  u32  token        = 0 (unknown yet)
0x20  32x  (zero)
0x40  16x  username     passcode-scrambled, NUL-padded (see §4)
0x50  16x  password     passcode-scrambled, NUL-padded
0x60  16x  appname      plain ASCII, e.g. "ic7300mk2", NUL-padded
0x70  16x  (zero)
```

### 3.2 LOGIN RESPONSE (radio → client, 0x60 = 96 bytes)

```
0x1A  u16  tokrequest   echoes ours
0x1C  u32  token        ← SAVE THIS; used in all later auth packets
0x30  u32  error        0x00000000 = OK; 0xFEFFFFFF (bytes FF FF FF FE) = bad user/pass
0x40  16x  connection   ASCII conn class, e.g. "FTTH", "WFVIEW"
```

Observed OK response: `error = 00 00 00 00`, `connection = "FTTH"`,
`token = 0x52A99D1D` (random per session). Bad password observed:
`error` bytes `FF FF FF FE`, connection is closed.

### 3.3 TOKEN packet (client → radio, 0x40 = 64 bytes)

Sent three times with different "magic" (`requesttype`) values:

| magic | when | meaning |
|-------|------|---------|
| `0x02` | right after login OK | confirm/create token |
| `0x05` | immediately after, then every 60 s | renew token (radio replies `response=0` = auth complete) |
| `0x01` | at disconnect | release token |

```
0x10  u32  payloadsize  BIG-ENDIAN = 0x30
0x14  u8   requestreply = 0x01
0x15  u8   requesttype  = magic (0x01/0x02/0x05)
0x16  u16  innerseq     BIG-ENDIAN, ++
0x1A  u16  tokrequest   LE
0x1C  u32  token        the token from login response
0x24  u16  resetcap     BIG-ENDIAN 0x0798 (wfview sets this; optional in practice)
```

Radio's TOKEN reply (also 0x40): `requestreply=0x02`, `requesttype=0x05`,
`response @ 0x30 (u32 LE) = 0x00000000` → **auth complete, may request streams.**
`response = 0xFFFFFFFF` → token rejected, restart login.

### 3.4 CAPABILITIES (radio → client, 0xA8 = 168 bytes)

Sent unsolicited right after login OK. Header `0xA8 00 00 00 00 00`. Contains a
count at `0x40` (big-endian u16) then one 0x66-byte **radio_cap** record per
radio starting at `0x42`. For a single-radio device like the 7300MK2 there is one
record. Fields within the record (offsets relative to record start `0x42`):

```
+0x00 16x  guid          e.g. 00 00 00 00 00 00 00 10 80 00 00 90 c7 17 25 cf
+0x07 u16  commoncap     = 0x8010  (0x8010 → MAC-addressed; else GUID-addressed)
+0x0A  6x  macaddress    90:c7:17:25:cf  → radio's Ethernet MAC
+0x10 32x  name          ASCII "IC-7300MK2"
+0x30 32x  audio         ASCII "ICOM_VAUDIO"
+0x50 u16  conntype
+0x52 u8   civ           ← the radio's CI-V address = 0xB6  (SAVE THIS)
+0x53 u16  rxsample
+0x55 u16  txsample
+0x5A u32  baudrate      BIG-ENDIAN = 19200
+0x5E u16  capf          = 0x5001
```

**The CI-V address is read from here (`0xB6`), not assumed.** You need the `guid`
(or `macaddress`+`commoncap`) to fill in the stream-request packet next.

### 3.5 STREAM REQUEST - "conninfo" (client → radio, 0x90 = 144 bytes)

This is the packet that actually asks the radio to open the CI-V and audio
services. **Before sending it, bind your two local UDP ports** (for 50002 and
50003 traffic) because you must tell the radio which local ports you'll use.

```
0x10  u32  payloadsize  BIG-ENDIAN = 0x80
0x14  u8   requestreply = 0x01
0x15  u8   requesttype  = 0x03   (request stream)
0x16  u16  innerseq     BIG-ENDIAN ++
0x1A  u16  tokrequest   LE
0x1C  u32  token
0x20  16x  guid         from capabilities (or mac at 0x2A w/ commoncap 0x8010)
0x40  32x  name         radio name "IC-7300MK2" (copy from capabilities)
0x60  16x  username     passcode-scrambled
0x70  u8   rxenable     = 1
0x71  u8   txenable     = 1 (0 if you won't send TX audio)
0x72  u8   rxcodec      audio codec, see §6.2  (0x04 = LPCM 16-bit mono)
0x73  u8   txcodec
0x74  u32  rxsample     BIG-ENDIAN, e.g. 48000
0x78  u32  txsample     BIG-ENDIAN
0x7C  u32  civport      BIG-ENDIAN = your local UDP port for the CI-V channel
0x80  u32  audioport    BIG-ENDIAN = your local UDP port for the audio channel
0x84  u32  txbuffer     BIG-ENDIAN, tx audio buffer in ms (e.g. 150)
0x88  u8   convert      = 1
```

### 3.6 STATUS (radio → client, 0x50 = 80 bytes) - the payoff

```
0x30  u32  error       0x00000000 OK
                       0xFDFFFFFF → "busy" (another client holds the streams)
                       0xFFFFFFFF → connection failed (reboot radio)
0x40  u8   disc        0x01 → radio forced a disconnect
0x42  u16  civport     BIG-ENDIAN = radio's CI-V port  → 50002
0x46  u16  audioport   BIG-ENDIAN = radio's audio port → 50003
```

Observed success: `error=0, disc=0, civport=50002, audioport=50003`. Now open
those two channels.

---

## 4. Username/password "passcode" scramble

Credentials are lightly obfuscated (NOT encrypted) with a fixed substitution
table + positional offset. Reproduced exactly in
[`ic7300mk2/passcode.py`](../ic7300mk2-sdk/ic7300mk2/passcode.py):

```python
def passcode(s):                       # returns 16 bytes, NUL-padded
    out = bytearray(16)
    for i, ch in enumerate(s.encode("ascii")[:16]):
        p = ch + i                     # add the character's position
        if p > 126:
            p = 32 + p % 127
        out[i] = SEQ[p - 32]           # SEQ is a fixed 95-byte table
    return bytes(out)
```

`SEQ` is the 95-entry table for printable ASCII 0x20-0x7E (see the source). This
matches wfview's `passcode()` and kappanhang's `passcode.go` byte-for-byte.
Usernames and passwords are limited to 16 characters.

---

## 5. CI-V channel (port 50002)

### 5.1 Open

1. Bind the local port you already advertised in the stream request.
2. Run the same control handshake as §3 (ARE-YOU-THERE → I-AM-HERE →
   ARE-YOU-READY → I-AM-READY) against port 50002.
3. Start PING (500 ms) and IDLE (100 ms) keepalives.
4. Send an **OPEN** packet (0x16 bytes) and keep resending it (~1 s) until the
   first CI-V data packet arrives.

**OPEN / CLOSE packet (0x16 = 22 bytes):**

```
0x00  u32  len        = 0x16
0x04..0x0F  standard header (type 0x00, seq, sentid, rcvdid)
0x10  u16  data       = 0x01C0   (little-endian on wire: C0 01)
0x12  u8   (zero)
0x13  u16  sendseq    BIG-ENDIAN CI-V inner sequence
0x15  u8   magic      0x04 = OPEN, 0x00 = CLOSE
```

> **Compatibility note:** kappanhang uses `magic = 0x05` for OPEN; wfview uses
> `0x04`. The 7300MK2 accepts **both** - verified live (reopened with
> `0x05` and CI-V kept working). Use `0x04`.

### 5.2 CI-V DATA packet (both directions, variable length)

```
0x00  u32  len        = 0x15 + civ_len
0x04..0x0F  standard header (type 0x00, seq, sentid, rcvdid)
0x10  u8   0xC1       constant marker for a CI-V data packet
0x11  u16  datalen    LITTLE-ENDIAN = length of the CI-V frame(s)
0x13  u16  sendseq    BIG-ENDIAN CI-V inner sequence (++ per send)
0x15  …    CI-V       one or more raw CI-V frames (FE FE … FD)
```

To recognize an inbound CI-V packet: `len > 0x15` and `byte[0x10] == 0xC1` and
`datalen + 0x15 == len`. Strip the first 0x15 bytes → you have raw CI-V. A single
UDP packet may contain multiple `FE FE…FD` frames; split on `FD`.

### 5.3 Raw CI-V framing

Standard ICOM CI-V, unchanged over the network:

```
FE FE <to> <from> <cmd> [subcmd] [data…] FD
```

- Radio CI-V address (`<to>` when you send, `<from>` when it replies) = **`0xB6`**
  (read from capabilities §3.4; this is the 7300MK2 factory default, *not* the
  old IC-7300's `0x94`).
- Controller address (`<from>` when you send) = **`0xE0`** by convention.
- The radio **echoes your frame back first** (you'll see your own `FE FE B6 E0…`)
  and then sends the answer `FE FE E0 B6…`. Ignore the echo (dest = radio addr).

Frequency read example, captured live:

```
TX:  FE FE B6 E0 03 FD                          "read operating frequency"
RX:  FE FE B6 E0 03 FD                           ← echo, ignore
RX:  FE FE E0 B6 03  48 79 21 07 00  FD          ← answer
                     └─ 5-byte little-endian BCD, 1 Hz units
     reversed → 00 07 21 79 48 → 7 217 948 Hz = 7.217948 MHz
```

Error/ack replies:
- `FE FE E0 B6 FB FD` = **OK** (command accepted, no data)
- `FE FE E0 B6 FA FD` = **NG** (command rejected / not available)

### 5.4 Addressing behavior (verified)

- Sending to `0xB6` (the radio's real address): **works**.
- Sending to `0x00` (broadcast): **works** - radio answers from `0xB6`. Handy if
  you don't want to read capabilities first, but reading it is cleaner.
- Sending to `0x94` (old IC-7300 address): **ignored, no response.** This is the
  single mistake that made the earlier investigations think the port was dead.

---

## 6. Audio channel (port 50003)

### 6.1 Open

Identical control handshake + keepalives as the CI-V channel. Audio starts
flowing from the radio **immediately** after `I-AM-READY`; no OPEN packet needed.
Audio uses PING keepalives but **not** the 100 ms IDLE packets.

### 6.2 Codec negotiation (chosen in the stream request, §3.5 byte 0x72)

| value | codec | verified packetization @ 48 kHz |
|-------|-------|--------------------------------|
| `0x01` | u-law 1-ch 8-bit | one 984-byte pkt / 20 ms (960-byte payload) |
| `0x02` | LPCM 1-ch 8-bit | |
| `0x04` | LPCM 1-ch 16-bit | 1388-byte + 580-byte pkt pair / 20 ms (1920 B payload) |
| `0x08` | PCM 2-ch 8-bit | |
| `0x10` | LPCM 2-ch 16-bit | |
| `0x20` | u-law 2-ch 8-bit | |
| `0x40` | Opus 1-ch | *not offered by 7300MK2 - it forces LPCM (conn type ≠ "WFVIEW")* |
| `0x80` | ADPCM 1-ch | |

For a simple library, **u-law mono (`0x01`)** is the least bandwidth and easiest
to decode; **LPCM16 mono (`0x04`)** is highest quality. Both verified live.

### 6.3 Audio DATA packet (radio → client, 24-byte header + payload)

```
0x00  u16  len        LITTLE-ENDIAN total length (this doubles as the type tag
                      wfview/kappanhang match on: 1388→"6c 05", 580→"44 02",
                      984→"d8 03")
0x04  u16  type       0x0000
0x06  u16  seq        LITTLE-ENDIAN transport seq (for retransmit)
0x08  u32  sentid / 0x0C u32 rcvdid
0x10  u16  ident      audio sub-stream id (observed 0x0681 / 0x0680)
0x12  u16  sendseq    BIG-ENDIAN audio sequence
0x16  u16  datalen    BIG-ENDIAN payload length
0x18  …    PCM/u-law payload
```

Strip 24 bytes → raw audio samples. TX audio (client→radio) mirrors this; see
`icomudpaudio.cpp` / `audiostream.go` if you implement transmit.

---

## 7. Reliability: sequence numbers & retransmit

Each channel keeps two independent counters:

- **Transport seq** (`seq` @ 0x06, little-endian): incremented on every *tracked*
  packet the client sends. Start at 1. Buffer the last ~500 sent packets so you
  can honor retransmit requests.
- **CI-V/audio inner seq** (`sendseq`, big-endian): the application-level counter
  inside CI-V/audio data packets.

**Retransmit request** (either direction):

- Single packet - a 16-byte control packet, `type = 0x01`, `seq` = the wanted
  transport seq. Respond by re-sending the exact buffered datagram; if you no
  longer have it, send an IDLE (`type 0x00`) carrying that seq.
- Range - a 24-byte packet, header `18 00 00 00 01 00`, followed by 4-byte
  `(first,last)` little-endian pairs. Resend each seq in the range.

Losing a few packets is normal; the buffers and retransmit make the stream
self-healing. During clean LAN tests we observed **zero** retransmit requests.

---

## 8. Keepalive & timing (measured live)

Per channel, once connected:

| activity | interval | who |
|----------|----------|-----|
| PING (0x15, type 0x07) | **500 ms** | client sends; radio also pings us ~every 100 ms and we must reply |
| IDLE (0x10, type 0x00) | **100 ms** | client → radio, control & CI-V channels (not audio) |
| TOKEN renew (0x40, magic 0x05) | **60 s** | client → radio, control channel only |
| audio data | ~**10 ms** per packet (20 ms per LPCM16 pair) | radio → client |

**PING** packet (0x15 = 21 bytes): header (type `0x07`) + `reply` byte @ 0x10
(`0x00` = request, `0x01` = reply) + `u32 time` @ 0x11 (ms-of-day timestamp).
When the radio sends a request (`reply=0x00`), copy it back with `reply=0x01` and
swapped IDs. When you send a request the radio echoes it back.

### 8.1 Client-timeout / going silent (verified, important)

If the client stops sending (no pings/idles):

- The radio **stops the audio stream within ~1 s** (no more data packets).
- The radio keeps sending its own pings/idle for **40 s+** before giving up.
- The CI-V stream **wedges**: queries get no response, and an *immediate*
  reconnect also fails - the radio still holds the stale session as "busy".
- Recovery: wait for the stale session to age out (**~15 s observed**), then a
  fresh full handshake works normally. Verified: after a 15 s pause the radio
  answered `7.217948 MHz` on the first read.

**Implication for the library:** keep the keepalive loop honest, and on any
reconnect be prepared to retry for ~15-30 s (the radio may report `busy`
`0xFDFFFFFF` until the old session clears). Always send the clean teardown (§9)
so the radio frees the session immediately instead of waiting to time out.

---

## 9. Clean teardown

In order, best-effort:

1. CI-V channel: send CLOSE (0x16, magic `0x00`).
2. Control channel: send TOKEN release (0x40, magic `0x01`).
3. Every channel: send DISCONNECT (0x10, `type 0x05`).
4. Close sockets.

Doing this frees the radio's session immediately (confirmed: a subsequent connect
reports `busy=0`). Skipping it forces the radio to wait out its ~15 s timeout.

---

## 10. CI-V command reference (7300MK2, verified)

From a live read-only sweep: **82 read commands answered, 10 returned
NG**. Highlights:

| CI-V (to `B6`, from `E0`) | meaning | example answer | decode |
|---------|---------|---------|--------|
| `03` | read operating freq | `03 48 79 21 07 00` | 5-byte LE BCD, Hz |
| `04` | read operating mode | `04 00 02` | mode `00`=LSB, filter `02` |
| `05 <bcd5>` | **set** freq | `FB`=OK | 5-byte LE BCD |
| `06 <mode> <filt>` | **set** mode | `FB`=OK | |
| `07 00`/`07 01` | select VFO A / B | | |
| `0F` | read split | `0F 00` | 0=off |
| `10` | tuning step | `10 00` | |
| `11` | attenuator | `11 20` | |
| `14 0A` | RF power | `14 0A 00 00` | 0-255 → 0-100% |
| `14 01` | AF gain | `14 01 00 58` | 0-255 |
| `15 02` | S-meter | `15 02 00 00` | 0-255 (0=S0) |
| `15 11` | power meter | | 0-255 |
| `15 12` | SWR meter | | |
| `16 02` | preamp | `16 02 00` | |
| `16 12` | AGC | `16 12 02` | |
| `1A 05 00 89` | CI-V transceive on/off | `…89 01` | 1=on |
| `1A 05 01 32` | system date | `…32 20 26 09 03` | BCD YYYY MM DD (2026-09-03) |
| `1A 05 01 33` | system time | `…33 02 59` | BCD HH MM |
| `19 00` | read transceiver CI-V id | `19 00 B6` | confirms `0xB6` |
| `1C 00` | PTT status | `1C 00 00` | 0=RX, 1=TX (read-only used here) |
| `1C 01` | ATU/tuner status | `1C 01 01` | |
| `1C 03` | TX frequency | `1C 03 …` | 5-byte LE BCD |
| `25 00` / `25 01` | read selected / unselected VFO freq | `25 00 48 79 21 07 00` | |
| `26 00` / `26 01` | read selected / unselected mode | `26 00 00 00 02` | |
| `27 10` | spectrum scope on/off | `27 10 01` | |
| `27 11` | scope **data output** on/off | `27 11 00` | 1 = stream waveform over CI-V |
| `1E 00` | number of band edges | `1E 00 11` | |

**Modes** (`04`/`06` first data byte): `00`=LSB `01`=USB `02`=AM `03`=CW
`04`=RTTY `05`=FM `07`=CW-R `08`=RTTY-R. **Filters** (second byte): `01`/`02`/`03`
= FIL1/2/3.

**Scope-subcommand quirk:** `27 14/15/16/17/19/1A/1D` return `FA` (NG) when read
bare, but **succeed when a "scope number" byte `00` is appended**
(`27 14 00` → `27 14 00 00`). `27 1E`/`27 1F` return NG either way on this
firmware. Always send the scope-selector byte.

Full machine-readable command map: wfview's
[`rigs/IC-7300MK2.rig`](https://gitlab.com/eliggett/wfview) (183 commands). The
mk2's CI-V command set is a superset of the original IC-7300.

### 10.1 Spectrum waveform (advanced)

With `27 11 01` the radio streams `27 00 …` waveform frames over the CI-V channel
(observed ~30 frames/s, ~490-497 bytes each). This is optional - skip it for a
"keep it simple" first cut. **Remember to send `27 11 00` to stop the firehose
when done** (verified live).

Over LAN a single frame carries a whole sweep. Offsets are counted from the
command byte, i.e. into a `CivFrame.payload`, which excludes the `FD`
terminator:

```
0   u16  27 00
2   u8   scope number      00 = main scope
3   u8   sequence number   01 for the single LAN sweep frame
4   u8   total sequences   01 for the single LAN sweep frame
5   u8   scope mode        0 center, 1 fixed, 2 scroll-C, 3 scroll-F
6   5B   freq A            LE BCD: center freq in center mode, else lower edge
11  5B   freq B            LE BCD: half-span in center mode, else upper edge
16  u8   out of range      nonzero = tuned freq sits outside the span
17  …    amplitude pixels  one byte each, nominal 0x00..0xA0
```

In center mode the edges are `A -/+ B`; otherwise A and B are the edges
directly. This radio produces 475 pixels per sweep. Amplitudes are
uncalibrated - scale them against the nominal maximum for display.

Multi-frame sweeps are documented for the serial interface, and wfview's
`icomUdpCivData::dataReceived()` splits IC-7300-LAN waveforms into 11 divisions
of 50 pixels, but nothing but `01 01` has been observed on this radio's LAN
interface. `ic7300mk2.spectrum.parse_waveform` rejects any other sequence /
total pair rather than guess at reassembly.

---

## 11. Reference implementation

The [`ic7300mk2`](../ic7300mk2-sdk/) Python SDK implements this protocol end to
end - handshake, login, token, stream request, CI-V open - behind a small API.
To read the current frequency:

```python
from ic7300mk2 import Radio

with Radio("icom.turnerservices.cloud", "thadigus", "<password>") as radio:
    print(radio.get_frequency())   # 7217948  (Hz)
```

> **macOS caveat:** run against the radio under `/usr/bin/python3`, not Homebrew
> python. macOS "Local Network" privacy blocks unsigned interpreters from
> reaching LAN hosts; the platform python is exempt. Symptom otherwise:
> `OSError: [Errno 65] No route to host` on `sendto` even though `ping` works.

---

## 12. Gotchas - things that bit us

1. **Raw CI-V to 50002 does nothing.** There is no session, so the radio ignores
   it. You must complete the 50001 handshake + login + stream request first.
2. **Wrong CI-V address = silence.** The mk2 is `0xB6`, not `0x94`. Read it from
   the capabilities packet; don't hardcode the old value.
3. **Sandboxed/again-signed Python can't reach the LAN on macOS** - looks
   identical to a firewalled port. Use `/usr/bin/python3`.
4. **Little-endian everywhere, except** payloadsize / innerseq / sample rates /
   port numbers / CI-V `sendseq`, which are big-endian. Mixing these up produces
   a login that's silently rejected.
5. **Don't go silent.** Dropping keepalives wedges CI-V and the radio holds the
   session `busy` for ~15 s. Always tear down cleanly.
6. **The radio echoes your CI-V frame** before answering; filter by destination
   address (radio→controller answers have `from = 0xB6`, `to = 0xE0`).

---

## 13. Sources

- Live experimentation against IC-7300MK2 @ `icom.turnerservices.cloud`, 2026-09-02.
- ICOM *CI-V Reference Guide* (generic CI-V layer) - vendored at
  [`reference/`](./reference/); see [`CIV-FUNDAMENTALS.md`](./CIV-FUNDAMENTALS.md).
- wfview - `src/radio/icomudp{base,handler,civdata,audio}.cpp`,
  `include/packettypes.h`, `rigs/IC-7300MK2.rig` - <https://wfview.org>,
  <https://gitlab.com/eliggett/wfview>.
- kappanhang (HA2NON/ES1AKOS/W6EL) - `controlstream.go`, `streamcommon.go`,
  `serialstream.go`, `audiostream.go`, `pkt0.go`, `pkt7.go`, `passcode.go` -
  <https://github.com/nonoo/kappanhang>.
- ICOM CI-V command references for the IC-7300 family (command semantics).
