# IC-7300MK2 CI-V Command Reference

The complete, model-correct opcode set for the IC-7300MK2. The frame mechanics
(addressing, OK/NG, BCD) are in [`CIV-FUNDAMENTALS.md`](./CIV-FUNDAMENTALS.md);
how the frames reach the radio over the network is in
[`PROTOCOL.md`](./PROTOCOL.md).

- **Source of the table:** wfview's `rigs/IC-7300MK2.rig` (183 entries, the
  vendor-derived command map for this exact model), reconciled with a **live
  read-only sweep** of the radio at `icom.turnerservices.cloud` (see the [verified responses](#verified-responses)
  appendix).
- **Notation:** commands and data are hex. A frame to the radio is
  `FE FE B6 E0 <command> [data] FD`; the radio answers `FE FE E0 B6 <command> [data] FD`,
  or `… FB FD` (OK) / `… FA FD` (NG). `B6` = radio, `E0` = controller.
- **Access:** `R` read-only / `W` write-only / `R/W` both / `act` action/notification.

---

## Reading a command

Example - read the operating frequency (command `03`):

```
send:  FE FE B6 E0 03 FD
recv:  FE FE B6 E0 03 FD                     ← echo, ignore (TO = B6)
recv:  FE FE E0 B6 03 48 79 21 07 00 FD      ← reply (TO = E0)
                     └───────────┘ 5-byte little-endian BCD = 7,217,948 Hz
```

Example - set RF power to ~50% (command `14 0A`, value 128 → BCD `01 28`):

```
send:  FE FE B6 E0 14 0A 01 28 FD
recv:  FE FE E0 B6 FB FD                      ← OK
```

---

## Master command table

| Command | Access | Description | Data range |
|---------|:------:|-------------|------------|
| `00` | act | Send frequency (transceive) - unsolicited on freq change |  |
| `01` | act | Send mode (transceive) - unsolicited on mode change |  |
| `02` | R/W | Band edge frequency |  |
| `03` | R | Read operating frequency | 5-byte LE BCD Hz |
| `04` | R | Read operating mode | mode + filter |
| `05` | W | Set operating frequency | 5-byte LE BCD Hz |
| `06` | W | Set operating mode | mode + filter |
| `07` | R/W | Select VFO mode |  |
| `07 00` | R/W | Select VFO A |  |
| `07 01` | R/W | Select VFO B |  |
| `07 a0` | R/W | Equalize VFO A = B |  |
| `07 b0` | R/W | Exchange VFO A ↔ B |  |
| `08` | R/W | Memory mode / recall channel | `1`…`101` |
| `0b` | R/W | Memory clear | `1`…`101` |
| `0e` | R/W | Scanning | `0`…`99` |
| `0f` | R/W | Split / duplex | `0`…`1` |
| `10` | R/W | Tuning step | `0`…`8` |
| `11` | R/W | Attenuator | `0`…`20` |
| `12 00` | W | Antenna | `0`…`1` |
| `13` | W | Speech (announce) | `0`…`2` |
| `14 01` | R/W | AF gain | `0`…`255` |
| `14 02` | R/W | RF gain | `0`…`255` |
| `14 03` | R/W | Squelch | `0`…`255` |
| `14 06` | R/W | NR level | `0`…`255` |
| `14 07` | R/W | PBT inner | `0`…`255` |
| `14 08` | R/W | PBT outer | `0`…`255` |
| `14 09` | R/W | CW pitch | `300`…`900` Hz |
| `14 0a` | R/W | RF power | `0`…`255` |
| `14 0b` | R/W | Mic gain | `0`…`255` |
| `14 0c` | R/W | Key (CW) speed | `6`…`48` wpm |
| `14 0e` | R/W | Compressor level | `0`…`255` |
| `14 0f` | R/W | Break-in delay | `0`…`255` |
| `14 12` | R/W | NB level | `0`…`255` |
| `14 15` | R/W | Monitor gain | `0`…`255` |
| `14 16` | R/W | VOX gain | `0`…`255` |
| `14 17` | R/W | Anti-VOX gain | `0`…`255` |
| `15 01` | R | Noise/S-meter squelch status | `0`…`1` |
| `15 02` | R | S-meter level | `0`…`255` |
| `15 05` | R | Various squelch status | `0`…`1` |
| `15 07` | R | Overflow (OVF) status | `0`…`1` |
| `15 11` | R | Power (PWR) meter | `0`…`255` |
| `15 12` | R | SWR meter | `0`…`255` |
| `15 13` | R | ALC meter | `0`…`255` |
| `15 14` | R | Compression (COMP) meter | `0`…`255` |
| `15 15` | R | Vd (drain voltage) meter | `0`…`255` |
| `15 16` | R | Id (drain current) meter | `0`…`255` |
| `16 02` | R/W | Preamp | `0`…`2` |
| `16 12` | R/W | AGC | `0`…`2` |
| `16 22` | R/W | Noise blanker (NB) | `0`…`1` |
| `16 40` | R/W | Noise reduction (NR) | `0`…`1` |
| `16 41` | R/W | Auto notch | `0`…`1` |
| `16 42` | R/W | Repeater tone | `0`…`1` |
| `16 43` | R/W | Repeater TSQL | `0`…`1` |
| `16 44` | R/W | Speech compressor | `0`…`1` |
| `16 45` | R/W | Monitor | `0`…`1` |
| `16 46` | R/W | VOX | `0`…`1` |
| `16 47` | R/W | Break-in | `0`…`1` |
| `16 48` | R/W | Manual notch | `0`…`1` |
| `16 4f` | R/W | Twin peak filter (RTTY) | `0`…`1` |
| `16 50` | R/W | Dial lock | `0`…`1` |
| `16 56` | R/W | Filter shape (soft/sharp) | `0`…`31` |
| `16 57` | R/W | Manual notch width | `0`…`2` |
| `16 58` | R/W | SSB TX bandwidth | `0`…`2` |
| `16 65` | R/W | IP+ (IP plus) | `0`…`1` |
| `17` | W | Send CW message (keyer) | ASCII, ≤30 bytes |
| `18` | R/W | Power on/off | `0`…`1` |
| `19 00` | R | Read transceiver CI-V ID | returns `B6` |
| `1a 00` | R/W | Memory channel contents | `1`…`101` |
| `1a 01` | R/W | Band-stacking register | |
| `1a 03` | R/W | Filter passband width | `50`…`10000` Hz |
| `1a 04` | R/W | AGC time constant | `0`…`13` |
| `1a 05 00 01` | R/W | SSB RX HPF/LPF | |
| `1a 05 00 02` | R/W | SSB RX bass | |
| `1a 05 00 03` | R/W | SSB RX treble | |
| `1a 05 00 04` | R/W | AM RX HPF/LPF | |
| `1a 05 00 05` | R/W | AM RX bass | |
| `1a 05 00 06` | R/W | AM RX treble | |
| `1a 05 00 07` | R/W | FM RX HPF/LPF | |
| `1a 05 00 08` | R/W | FM RX bass | |
| `1a 05 00 09` | R/W | FM RX treble | |
| `1a 05 00 10` | R/W | CW RX HPF/LPF | |
| `1a 05 00 12` | R/W | SSB TX bass | |
| `1a 05 00 13` | R/W | SSB TX treble | |
| `1a 05 00 18` | R/W | AM TX bass | |
| `1a 05 00 19` | R/W | AM TX treble | |
| `1a 05 00 20` | R/W | FM TX bass | |
| `1a 05 00 21` | R/W | FM TX treble | |
| `1a 05 00 33` | R/W | Quick split | `0`…`1` |
| `1a 05 00 81` | R/W | USB modulation input level | `0`…`255` |
| `1a 05 00 82` | R/W | ACC1 modulation input level | `0`…`255` |
| `1a 05 00 83` | R/W | LAN modulation input level | `0`…`255` |
| `1a 05 00 84` | R/W | DATA-OFF mod input source | `0`…`5` |
| `1a 05 00 85` | R/W | DATA1 mod input source | `0`…`5` |
| `1a 05 00 89` | R/W | **CI-V transceive** on/off | `0`…`1` |
| `1a 05 00 91` | R/W | CI-V output (for ANT) | `0`…`1` |
| `1a 05 01 32` | R/W | System date | BCD `YYYY MM DD` |
| `1a 05 01 33` | R/W | System time | BCD `HH MM` |
| `1a 05 01 36` | R/W | UTC offset | |
| `1a 05 01 52` … `1a 05 02 03` | R/W | Scope fixed-edge frequency presets (edge 1-4 x band 1.6/2/6/8/11/15/20/22/26/30/45/60/74 MHz) | |
| `1a 05 02 65` | R/W | NB depth | `1`…`10` |
| `1a 05 02 66` | R/W | NB width | `0`…`255` |
| `1a 05 02 67` | R/W | VOX delay | `0`…`20` |
| `1b 00` | R/W | Repeater tone frequency | 3-byte BCD |
| `1b 01` | R/W | TSQL tone frequency | 3-byte BCD |
| `1c 00` | R/W | **PTT / transceiver status** (TX on/off) | `0`…`1` |
| `1c 01` | R/W | Tuner / ATU status | `0`…`2` |
| `1c 02` | R/W | Transmit frequency monitor | `0`…`1` |
| `1c 03` | R | TX frequency | 5-byte LE BCD |
| `1e 00` | R | Number of band edges | |
| `21 00` | R/W | RIT frequency | ±`999` Hz |
| `21 01` | R/W | RIT on/off | `0`…`1` |
| `21 02` | R/W | XIT (TX offset) on/off | `0`…`1` |
| `25 00` | R/W | Selected-VFO frequency | 5-byte LE BCD |
| `25 01` | R/W | Unselected-VFO frequency | 5-byte LE BCD |
| `26 00` | R/W | Selected-VFO mode | mode+data+filter |
| `26 01` | R/W | Unselected-VFO mode | mode+data+filter |
| `27 00` | R/W | Spectrum scope waveform data | (streamed) |
| `27 10` | R/W | Scope on/off | `0`…`1` |
| `27 11` | R/W | Scope waveform **data output** on/off | `0`…`1` |
| `27 13` | R/W | Scope single/dual | |
| `27 14` | R/W | Scope mode (0 center, 1 fixed, 2 scroll-C, 3 scroll-F) | `0`…`3` |
| `27 15` | R/W | Scope span: HALF span in Hz, 5-byte LE BCD (`00 50 02 00 00` = 25 000 Hz = +-25 kHz) | 2500…500000 |
| `27 16` | R/W | Scope edge | `1`…`4` |
| `27 17` | R/W | Scope hold | `0`…`1` |
| `27 19` | R/W | Scope reference level: 2-byte BE BCD tenths of dB + sign (`00`=+, `01`=-) | -20.0…+20.0 |
| `27 1a` | R/W | Scope sweep speed | `0`…`2` |
| `27 1b` | R/W | Scope during TX | `0`…`1` |
| `27 1c` | R/W | Scope center type | `0`…`2` |
| `27 1d` | R/W | Scope VBW (video bandwidth) | `0`…`1` |
| `27 1e` | R/W | Scope fixed-edge selection | `1`…`12` |
| `27 1f` | R/W | Scope RBW (resolution bandwidth) | `0`…`2` |
| `fa` | - | NG response code (rejected) | |
| `fb` | - | OK response code (accepted) | |

**183 commands total.** The `1a 05 01 52 … 02 03` scope-edge presets are collapsed
into one row above (48 individual entries in the rig file, one per edgexband).

---

## Encodings & notes by group

### Frequency - `03` / `05` / `25` / `1C 03`
5-byte little-endian packed BCD, 1 Hz units. See
[CIV-FUNDAMENTALS §5.1](./CIV-FUNDAMENTALS.md#51-frequency--little-endian-packed-bcd).
`25 xx` prefixes the 5 bytes with a VFO selector (`00`=selected, `01`=unselected),
letting you read/set either VFO without switching. `03` acts on the current VFO.

### Mode - `04` / `06` / `26`
Reply/data is **`<mode> <filter>`** (command `26` inserts a data-mode byte:
`<mode> <data> <filter>`).

| mode | byte | | filter | byte |
|------|------|---|--------|------|
| LSB | `00` | | FIL1 | `01` |
| USB | `01` | | FIL2 | `02` |
| AM  | `02` | | FIL3 | `03` |
| CW  | `03` | | | |
| RTTY| `04` | | data mode (`26` only): | |
| FM  | `05` | | OFF | `00` |
| CW-R| `07` | | DATA1/2/3 | `01`/`02`/`03` |
| RTTY-R| `08` | | | |

Verified: `04` → `04 00 02` = LSB, FIL2. `26 00` → `26 00 00 02` = selected VFO
LSB, data OFF, FIL2.

### Levels - `14 xx`
2-byte BCD, 0000-0255 (see [FUNDAMENTALS §5.2](./CIV-FUNDAMENTALS.md#52-levels-and-meters--2-byte-bcd-00000255)).
`14 0A` (RF power) 0-255 maps to 0-100%. `14 0C` (key speed) 6-48 wpm maps across
0-255 internally but the rig file exposes the wpm range. CW pitch `14 09` is
300-900 Hz.

### Meters - `15 xx` (read-only)
2-byte BCD 0000-0255. Approximate scaling (ICOM family conventions):

| Meter | Cmd | Scale |
|-------|-----|-------|
| S-meter | `15 02` | 0=S0, 120≈S9, 241≈S9+60dB |
| Power | `15 11` | 0=0%, 143≈50%, 213≈100% |
| SWR | `15 12` | 0=SWR1.0, 48≈1.5, 80≈2.0, 120≈3.0 |
| ALC | `15 13` | 0=min, 120=ALC zone max |
| COMP | `15 14` | dB of compression |
| Vd | `15 15` | drain voltage |
| Id | `15 16` | drain current |

Verified idle (RX, no TX): S/PWR/SWR/ALC/COMP/Id all `00 00`; Vd `01 64` (=164).

### Function toggles - `16 xx`
Single byte. Most are `00`=OFF / `01`=ON. Multi-state: preamp `16 02`
(`00`=off/`01`=P.AMP1/`02`=P.AMP2), AGC `16 12` (`00`=off/`01`=FAST/`02`=SLOW -
verified `02`).

### Transmit control - `1C`
- `1C 00` **PTT**: read TX state (`00`=RX, `01`=TX); **write `1C 00 01` keys the
  transmitter**, `1C 00 00` unkeys. *(Not exercised in our read-only sweep.)*
- `1C 01` ATU/tuner: `00`=off, `01`=on, `02`=start tune. Verified read `1C 01 01`.
- `1C 03` TX frequency (read): 5-byte LE BCD. Verified.

### CW keyer - `17`
`17` followed by up to ~30 ASCII characters sends CW. Special chars per ICOM CW
keyer spec (e.g. `FF` stops). Write-only.

### RIT - `21`
`21 00` RIT offset: `<2-byte BCD Hz> <sign>` where sign `00`=+, `01`=-, range
±9999 Hz (radio limits to ±9.999 kHz). `21 01`/`21 02` are on/off toggles.

### Spectrum scope - `27` (see [PROTOCOL §10.1](./PROTOCOL.md#101-spectrum-waveform-advanced))
- `27 10` scope display on/off; `27 11` **waveform data output** on/off - set `01`
  to make the radio stream `27 00` waveform frames over the CI-V channel, `00` to
  stop. Verified: `27 11 01` → ~30 frames/s of ~490-497-byte `27 00` packets;
  `27 11 00` stops them.
- **Quirk:** `27 14/15/16/17/19/1A/1D` return `FA` (NG) when read *bare*, but
  succeed when a scope-selector byte `00` is appended (`27 14 00` →
  `27 14 00 00`). `27 1E`/`27 1F` return NG regardless on the tested firmware.
  Always send the selector byte for `27` reads.
- **Writes** use the same selector byte: `27 15 00 <5-byte span>` is accepted,
  `27 15 <5-byte span>` answers NG (verified 2026-09-04 by writing back the
  values just read for span, reference level and mode). The SDK's
  `Radio.get_scope`/`set_scope` encapsulate both rules.

---

## Verified responses

Captured live 2026-09-02 (read-only).
Format: command → raw radio reply.

```
02          band edge         → fe fe e0 b6 02 00 00 03 00 00 2d 00 00 80 74 00 fd
03          frequency         → fe fe e0 b6 03 48 79 21 07 00 fd       (7.217948 MHz)
04          mode              → fe fe e0 b6 04 00 02 fd                (LSB, FIL2)
0f          split             → fe fe e0 b6 0f 00 fd                   (off)
10          tuning step       → fe fe e0 b6 10 00 fd
11          attenuator        → fe fe e0 b6 11 20 fd
14 0a       RF power          → fe fe e0 b6 14 0a 00 00 fd             (0%)
14 01       AF gain           → fe fe e0 b6 14 01 00 58 fd             (=58)
15 02       S-meter           → fe fe e0 b6 15 02 00 00 fd             (S0, no signal)
15 15       Vd meter          → fe fe e0 b6 15 15 01 64 fd             (=164)
16 02       preamp            → fe fe e0 b6 16 02 00 fd                (off)
16 12       AGC               → fe fe e0 b6 16 12 02 fd                (slow)
19 00       CI-V ID           → fe fe e0 b6 19 00 b6 fd                (address B6)
1a 05 00 89 CI-V transceive   → fe fe e0 b6 1a 05 00 89 01 fd          (ON)
1a 05 01 32 system date       → fe fe e0 b6 1a 05 01 32 20 26 09 03 fd (2026-09-03)
1a 05 01 33 system time       → fe fe e0 b6 1a 05 01 33 02 59 fd       (02:59)
1c 00       PTT status        → fe fe e0 b6 1c 00 00 fd                (RX)
1c 01       ATU status        → fe fe e0 b6 1c 01 01 fd                (on)
1c 03       TX frequency      → fe fe e0 b6 1c 03 48 79 21 07 00 fd
21 00       RIT               → fe fe e0 b6 21 00 00 00 00 fd          (0 Hz)
25 00       selected VFO      → fe fe e0 b6 25 00 48 79 21 07 00 fd    (7.217948 MHz)
25 01       unselected VFO    → fe fe e0 b6 25 01 00 00 10 14 00 fd    (14.100000 MHz)
26 00       selected mode     → fe fe e0 b6 26 00 00 00 02 fd          (LSB/data OFF/FIL2)
27 10       scope on/off      → fe fe e0 b6 27 10 01 fd                (on)
1e 00       band-edge count   → fe fe e0 b6 1e 00 11 fd                (17)
```

Sweep totals: **82 commands answered with data, 10 returned NG** (all NG were bare
`27` scope subcommands needing the selector byte, plus `27 1E`/`27 1F`).

---

## Full vendor map

The exhaustive machine-readable source, including value tables the rig file
encodes, is wfview's [`rigs/IC-7300MK2.rig`](https://gitlab.com/eliggett/wfview/-/blob/master/rigs/IC-7300MK2.rig).
The IC-7300MK2 command set is a superset of the original IC-7300; ICOM's published
IC-7300 *Full Manual* CI-V section documents the shared opcodes in prose.
