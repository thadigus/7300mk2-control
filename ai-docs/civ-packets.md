# CI-V Packet Reference (IC-7300MK2)

> Quick cheat-sheet. For the full picture see [`CIV-FUNDAMENTALS.md`](./CIV-FUNDAMENTALS.md)
> (the CI-V layer), [`COMMANDS.md`](./COMMANDS.md) (every opcode), and
> [`PROTOCOL.md`](./PROTOCOL.md) §5 (how CI-V rides over UDP). All verified live.

## Raw CI-V frame (inside the UDP transport wrapper)

```
FE FE <to> <from> <cmd> [subcmd] [data…] FD
```

| Address | Device |
|---------|--------|
| `0xB6` | IC-7300MK2 - **factory default**, read from the capabilities packet |
| `0xE0` | controller / PC (our end), by convention |
| `0x00` | broadcast (radio also answers this) |
| `0x94` | old IC-7300 address - **the mk2 does NOT use this; frames to 0x94 are ignored** |

The radio echoes your outbound frame, then sends the answer with src/dest
swapped:

```
TX:  FE FE B6 E0 03 FD
RX:  FE FE B6 E0 03 FD              ← echo (dest = B6), ignore
RX:  FE FE E0 B6 03 48 79 21 07 00 FD   ← answer (dest = E0)
```

## Common commands (all verified live)

| Cmd | Description | Answer form |
|-----|-------------|-------------|
| `03` | Read operating frequency | `03` + 5-byte LE BCD Hz |
| `04` | Read operating mode | `04 <mode> <filter>` |
| `05` | Set frequency | `FB` (OK) |
| `06` | Set mode | `FB` (OK) |
| `25 00` | Read selected-VFO frequency | `25 00` + 5-byte LE BCD |
| `26 00` | Read selected-VFO mode | `26 00 <mode> <filter>` |
| `15 02` | Read S-meter | `15 02` + 2-byte BCD (0-255) |
| `1C 00` | Read PTT status | `1C 00 <00=RX / 01=TX>` |
| `19 00` | Read transceiver CI-V id | `19 00 B6` |

Ack/error: `FB` = OK, `FA` = NG (rejected/unavailable).

## Frequency BCD decode

5 data bytes, little-endian, 2 BCD digits each, 1 Hz resolution:

```
48 79 21 07 00  →  reverse bytes  →  00 07 21 79 48  →  7 217 948 Hz
```

## Transport wrapper (recap)

CI-V frames ride inside a 0x15-byte header on UDP 50002 (marker byte `0xC1` at
offset 0x10). See [`PROTOCOL.md`](./PROTOCOL.md) §5.2 for the exact layout. Raw
CI-V frames sent to 50002 without an established session are ignored.
