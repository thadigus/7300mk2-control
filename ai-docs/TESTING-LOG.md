# Testing Log

All tests against IC-7300MK2 @ `icom.turnerservices.cloud`, user `thadigus`, 2026-09-02.

## Control handshake
`FE FE`-free 16-byte control packet, type `0x03` → radio replied type `0x04`
(`I-AM-HERE`) from `icom.turnerservices.cloud:50001`. Control port confirmed live.
(First attempt failed with `No route to host` under Homebrew python - see
the macOS caveat in PROTOCOL.md §11. Re-run under `/usr/bin/python3` worked.)

## Full session + frequency read ✅ SUCCESS CRITERION MET
Full control handshake → login OK (`conntype=FTTH`, token issued) → capabilities
(`name=IC-7300MK2`, `civ=0xB6`, MAC `90:c7:17:25:cf`) → token auth OK → stream
request → status (`civport=50002 audioport=50003`) → CI-V open → queries:

```
freq (03)      = 7 217 948 Hz  (7.217948 MHz)
mode (04)      = 0x00 LSB, filter 2
rig id (19 00) = 0xB6
VFO sel (25 00)= 7 217 948 Hz
VFO uns(25 01) = 14 100 000 Hz
```

Audio began streaming immediately (1388+580-byte LPCM16 pairs, ~20 ms each).

## Read-only CI-V sweep + scope + addressing
- 92 commands swept: **82 OK, 10 NG** (all NG were bare scope subcommands that
  need a selector byte - see PROTOCOL.md §10).
- Scope: `27 11 01` produced ~30 waveform frames/s (~497 bytes); `27 11 00`
  stopped them. Original value read and restored.
- Addressing: `0xB6` OK, `0x00` broadcast OK, `0x94` **no response**.
- Close (magic 0x00) then reopen with magic **0x05** - CI-V still worked, so the
  mk2 accepts both wfview's 0x04 and kappanhang's 0x05 open magic.
- Zero retransmit requests on a clean LAN.

## Edge cases
- **Wrong password** → login response error bytes `FF FF FF FE`, connection
  refused.
- **u-law codec (0x01)** → single 984-byte packets / 20 ms (vs LPCM16's
  1388+580 pair).
- **Second concurrent client** → radio returned status error `0xFDFFFFFF`
  ("busy"); the first client keeps the streams. Single-client device.

## Timing & timeout
- Measured cadences: client PING 500 ms, IDLE 100 ms, radio PING req ~100 ms,
  audio ~10 ms/pkt, token renew 60 s.
- **Going silent:** radio stopped audio within ~1 s, kept pinging 40 s+, CI-V
  wedged; immediate reconnect failed (`busy`). After a ~15 s pause a fresh
  session worked and read `7.217948 MHz` cleanly. Always tear down cleanly.

## Health re-check
After the timeout test + 15 s pause: clean connect, `freq = 7.217948 MHz`,
`mode = AM-read 00/02`. Radio left in a healthy state.
