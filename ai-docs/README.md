# IC-7300MK2 Network CI-V - Documentation

> [!WARNING] 
> Please be aware that this file, as well as all markdown files in this directory are entirely AI written. Eventually /ai-docs will be replaced by a /docs that is written and reviewed by a human for brevity and accuracy as the project develops.

A one-stop reference for controlling the ICOM IC-7300MK2 over its network
(RS-BA1-style UDP) CI-V interface, and for the stack this repository builds on
top of it. Protocol details were verified against a live radio at
`icom.turnerservices.cloud` on 2026-09-02 and cross-checked against ICOM's
official CI-V reference plus the wfview and kappanhang implementations.

## Start here

| If you want to... | Read |
|-----------------|------|
| Understand the whole thing at a glance | [`ARCHITECTURE.md`](./ARCHITECTURE.md) |
| Implement the network session (handshake, login, packets) | [`PROTOCOL.md`](./PROTOCOL.md) |
| Understand CI-V itself (frames, addressing, BCD, transceive) | [`CIV-FUNDAMENTALS.md`](./CIV-FUNDAMENTALS.md) |
| Look up an opcode | [`COMMANDS.md`](./COMMANDS.md) |
| See a quick CI-V packet cheat-sheet | [`civ-packets.md`](./civ-packets.md) |
| Use the Python library | [`../ic7300mk2-sdk/`](../ic7300mk2-sdk/) |
| Run the HTTP + WebSocket backend | [`../ic7300mk2-server/`](../ic7300mk2-server/) |
| Run the browser front end | [`../ic7300mk2-web/`](../ic7300mk2-web/) |

## The document set

- **[`ARCHITECTURE.md`](./ARCHITECTURE.md)** - the layered model (UDP → ICOM
  stream → CI-V → your app), the three-channel design, the connection state
  machine, timing, failure/recovery, the SDK's module layout, and then the
  system as built: the SDK / server / browser tiers, the server-side state
  poller and its stream, the binary spectrum and audio formats, session
  tokens, and the transmit gate. The mental model; start here.
- **[`PROTOCOL.md`](./PROTOCOL.md)** - the authoritative **network transport**
  spec. Exact packet layouts, the full connect sequence, login/token/auth, stream
  negotiation, CI-V and audio framing, retransmit, keepalive timing, and error
  codes. Build the library from this.
- **[`CIV-FUNDAMENTALS.md`](./CIV-FUNDAMENTALS.md)** - the **generic CI-V layer**
  (same over USB or LAN): frame format, addressing, OK/NG, echo-back, transceive,
  and number encodings. Sourced from ICOM's official reference guide.
- **[`COMMANDS.md`](./COMMANDS.md)** - the **complete 183-command opcode table**
  for the 7300MK2, with encodings, per-group notes, and live-verified example
  responses.
- **[`civ-packets.md`](./civ-packets.md)** - one-page CI-V frame cheat-sheet.
- **[`NOTES.md`](./NOTES.md)** - quick verified facts (addresses, ports, gotchas).
- **[`TESTING-LOG.md`](./TESTING-LOG.md)** - what each live experiment did and
  found.
- **[`RESEARCH.md`](./RESEARCH.md)** - external sources and reference
  implementations.

Several pages link to a `reference/` directory holding the vendored ICOM *CI-V
Reference Guide*. It is not in the tree; those links are dead until someone adds the PDF.

## The 30-second summary

- Three UDP channels: **50001** control/auth, **50002** CI-V, **50003** audio.
- Raw CI-V does nothing until a full authenticated session is negotiated on
  50001; then CI-V (`FE FE B6 E0 ... FD`) flows over 50002.
- Radio CI-V address is **`0xB6`** (factory default for the mk2), controller `0xE0`.
- Login user/pass are lightly scrambled (not encrypted); no transport encryption.
- Three projects sit on that: `ic7300mk2-sdk` (blocking Python `Radio`, one I/O
  thread), `ic7300mk2-server` (FastAPI sessions, bearer tokens, a state poller,
  binary spectrum and audio streams, a default-deny transmit gate), and
  `ic7300mk2-web` (React, WebGL2 panadapter, AudioWorklet receive audio).
- The radio accepts one client at a time, so one server session owns a radio
  and hands its token to whoever opened it.
- Nothing transmits: the server refuses every keying path unless it was started
  with `TX_ENABLED`, which no bench run has done.

## Provenance

- Live experimentation against the IC-7300MK2.
- ICOM *CI-V Reference Guide*.
- wfview - <https://gitlab.com/eliggett/wfview> (`src/radio/icomudp*.cpp`,
  `rigs/IC-7300MK2.rig`).
- kappanhang - <https://github.com/nonoo/kappanhang>.
