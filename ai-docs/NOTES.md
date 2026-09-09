# Notes / Quick Facts

Index: [`README.md`](./README.md). Authoritative docs:
[`ARCHITECTURE.md`](./ARCHITECTURE.md) (model),
[`PROTOCOL.md`](./PROTOCOL.md) (transport),
[`CIV-FUNDAMENTALS.md`](./CIV-FUNDAMENTALS.md) (CI-V),
[`COMMANDS.md`](./COMMANDS.md) (opcodes). Verified facts:

## Radio
- Model: **IC-7300MK2**, host `icom.turnerservices.cloud`, MAC `90:c7:17:25:cf`.
- **CI-V address: `0xB6`** (factory default for the mk2; the original 7300 was
  `0x94`). Read it from the capabilities packet, don't hardcode.
- Single-client: a second simultaneous session gets `busy` (`0xFDFFFFFF`).

## Ports (all UDP)
- `50001` control/session, `50002` CI-V, `50003` audio.
- **Raw CI-V to 50002 without a session is ignored** - this is by design, not a
  closed port.

## Session essentials
- Session id = `(ip[2]<<24)|(ip[3]<<16)|local_port`, per channel.
- Transport wrapper is little-endian; auth-packet payloadsize / innerseq /
  sample rates / port numbers / CI-V sendseq are big-endian.
- Login user/pass are "passcode"-scrambled (substitution table, not encryption),
  max 16 chars.
- Keepalives: PING 500 ms, IDLE 100 ms, token renew 60 s. Reply to the radio's
  own pings.
- Tear down cleanly (CI-V close → token release → disconnect) or the radio holds
  the session `busy` ~15 s.

## macOS gotcha
Use `/usr/bin/python3` for live control on macOS. Homebrew python is blocked from the LAN
by macOS Local Network privacy → `No route to host` on send even though ping
works.

## CI-V examples
- Read freq: `FE FE B6 E0 03 FD` → `FE FE E0 B6 03 <5-byte LE BCD> FD`.
- The radio echoes your frame first; filter answers by dest addr `E0`.
- `FB` = OK, `FA` = NG.

## Current state (2026-09-02)
Radio tuned to **7.217948 MHz, LSB**. Unselected VFO at 14.100000 MHz.
Full read/write CI-V verified working over the network.
