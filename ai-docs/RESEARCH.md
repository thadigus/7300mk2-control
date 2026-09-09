# Research Sources & Reference Material

For the protocol itself, see [`PROTOCOL.md`](./PROTOCOL.md). This file collects
the external references used to reverse-engineer and verify it.

## Reference implementations (read these for corner cases)

### wfview (C++/Qt) - the most complete
- <https://wfview.org> / <https://gitlab.com/eliggett/wfview>
- Key files:
  - `include/packettypes.h` - every UDP packet struct (control, ping, token,
    login, status, conninfo, capabilities, audio).
  - `src/radio/icomudpbase.cpp` - session ids, ping/idle, retransmit engine.
  - `src/radio/icomudphandler.cpp` - control channel: login, token, stream
    request, capability/status/conninfo parsing.
  - `src/radio/icomudpcivdata.cpp` - CI-V channel: open/close, data framing,
    spectrum-waterfall splitting.
  - `src/radio/icomudpaudio.cpp` - audio framing, TX audio.
  - `include/icomudpbase.h` - the `passcode()` scramble + the substitution table.
  - `rigs/IC-7300MK2.rig` - **machine-readable list of all 183 CI-V commands** for
    this exact model (`CIVAddress=182` = 0xB6). Best single source for the
    command map.
- The IC-7300MK2 is supported from the wfview **v2.20-dev / v2.21** line; older
  releases may show it as "default". Not yet in a long-term stable at time of
  writing.

### kappanhang (Go) - cleanest byte-level reference
- <https://github.com/nonoo/kappanhang> (by HA2NON, ES1AKOS, W6EL)
- `controlstream.go` has literal annotated hex dumps of the login/auth exchange -
  invaluable for getting field offsets exactly right.
- `passcode.go` is the scramble table as a plain map.
- `pkt0.go` (idle/retransmit), `pkt7.go` (ping), `serialstream.go` (CI-V),
  `audiostream.go` (audio).

## ICOM documentation
- **CI-V Reference Guide** - vendored in [`reference/`](./reference/)
  (`ICOM_CI-V_Reference_Guide_IC-R15.pdf` + extracted `.txt`). Written for the
  IC-R15 receiver, but the CI-V *frame format, addressing, OK/NG, echo-back,
  transceive, and BCD encoding are common to the whole CI-V family* including the
  7300MK2. This is the canonical public source for the generic CI-V layer; it is
  the basis of [`CIV-FUNDAMENTALS.md`](./CIV-FUNDAMENTALS.md). Downloaded from
  icomamerica.com (`IC-R15_ENG_CI-V_0.pdf`, © Icom Inc., Mar. 2024).
- RS-BA1 (IP Remote Control Software) manuals - describe the 50001/50002/50003
  port roles and the client/server model this protocol implements.
- IC-7300 family CI-V command references - semantics of the `03/04/05/06/14/15/
  16/1A/25/26/27…` commands. The mk2 command set is a superset of the IC-7300;
  the full model-specific opcode list is in [`COMMANDS.md`](./COMMANDS.md).

## Community
- wfview forum (<https://forum.wfview.org>) threads on IC-7300MK2 bring-up.
- kappanhang was built for the IC-705, which shares this identical protocol; most
  of its findings transfer directly.

## Verification method used here
Rather than trust the docs, every field was confirmed on the wire against the
live radio. Where wfview and kappanhang disagreed (e.g. CI-V open "magic" `0x04`
vs `0x05`), the radio was tested with both.
