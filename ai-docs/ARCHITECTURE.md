# Architecture: CI-V over Network on the IC-7300MK2

How the pieces fit together, end to end. Sections 1-7 are the radio side: the
protocol layers, the three UDP channels, the connection lifecycle, and the SDK
built on them. Sections 8-12 are the stack above it: the SDK / server / browser
tiers, the state stream, the binary stream formats, session tokens, and the
transmit gate. Byte-level detail lives in
[`PROTOCOL.md`](./PROTOCOL.md) (transport),
[`CIV-FUNDAMENTALS.md`](./CIV-FUNDAMENTALS.md) (CI-V), and
[`COMMANDS.md`](./COMMANDS.md) (opcodes). This page is the mental model.

---

## 1. Layered model

The thing that trips people up: **CI-V is an application protocol that normally
runs over a serial cable, and ICOM tunnels it over UDP** with a reliability +
auth layer bolted on. There are four layers:

```
┌───────────────────────────────────────────────────────────────┐
│ L4  Application         your code: "read frequency", "set mode" │
│                         cached radio state, rig-control API      │
├───────────────────────────────────────────────────────────────┤
│ L3  CI-V                FE FE B6 E0 <cmd> <data> FD             │  ← same as USB
│                         addressing, OK/NG, BCD, transceive       │
├───────────────────────────────────────────────────────────────┤
│ L2  ICOM stream         per-channel session: are-you-there,     │
│     (RS-BA1)            login+token auth, stream request,        │
│                         seq numbers, retransmit, keepalive       │
├───────────────────────────────────────────────────────────────┤
│ L1  UDP/IP              three datagram sockets to the radio      │
└───────────────────────────────────────────────────────────────┘
```

- **L1/L2 are the "network" part** - unique to LAN-capable ICOM radios, shared
  with the IC-705/9700/7610/R8600/905. Implemented once, reused for every radio.
- **L3 is ordinary CI-V** - if you ever add a USB-serial backend, L3 and L4 are
  unchanged; only L1/L2 are swapped for a serial port.
- **L4 is your library's public API.**

This separation is the single most important design decision: keep L2 (transport)
and L3 (CI-V) in different modules so a future USB backend drops in under L3.

---

## 2. The three channels

A network session is **three independent UDP channels**, each its own L2 state
machine, opened in sequence. Only the control channel authenticates; it hands the
other two their port numbers.

```
                 ┌──────────────── control (UDP 50001) ────────────────┐
   PC  ─────────►│ handshake → LOGIN(user/pass) → token → STREAM REQ    │
                 │ ◄── STATUS: "CI-V is on :50002, audio on :50003"     │
                 └──────────────────────────────────────────────────────┘
                          │ (learn civ/audio ports)         │
              ┌───────────┘                                 └───────────┐
              ▼                                                         ▼
   ┌──────── CI-V (UDP 50002) ────────┐             ┌──────── audio (UDP 50003) ───────┐
   │ handshake → OPEN → FE FE…FD both │             │ handshake → RX PCM/u-law stream  │
   │ ways (commands, replies, scope)  │             │ (+ optional TX audio)            │
   └──────────────────────────────────┘             └──────────────────────────────────┘
```

Each channel independently maintains: its own `(my_id, remote_id)` session-id
pair, its own transport sequence counter, its own tx-buffer for retransmits, and
its own ping/idle keepalive timers. See [PROTOCOL §1.1](./PROTOCOL.md#11-session-ids-sentid--rcvdid).

For a **CI-V-only control library** (the project's first milestone) you need the
control channel and the CI-V channel. The audio channel is optional and can be
added later without touching the other two.

---

## 3. Connection lifecycle (state machine)

The control channel drives everything. States, with the trigger that advances
each:

```
  DISCONNECTED
      │  send ARE-YOU-THERE (0x03), repeat every 500ms
      ▼
  LINKING ───────────────► recv I-AM-HERE (0x04): learn remote_id
      │  send ARE-YOU-READY (0x06)
      ▼
  READY ─────────────────► recv I-AM-READY (0x06)
      │  send LOGIN (0x80, user/pass)
      ▼
  AUTHENTICATING ────────► recv LOGIN-RESPONSE (0x60): save token
      │                    recv CAPABILITIES (0xA8): save civ addr, guid
      │  send TOKEN confirm (0x02) + TOKEN renew (0x05)
      ▼
  AUTHENTICATED ─────────► recv TOKEN reply, response==0
      │  send STREAM REQUEST (0x90) with my civ/audio local ports
      ▼
  STREAMS-NEGOTIATED ────► recv STATUS (0x50): radio's civ/audio ports
      │  open CI-V channel (handshake + OPEN 0x16)
      │  open audio channel (handshake)         [optional]
      ▼
  RUNNING ◄──────────────► CI-V commands/replies flow; keepalives run
      │  send CI-V CLOSE, TOKEN release (0x01), DISCONNECT (0x05)
      ▼
  DISCONNECTED
```

Two background obligations while in RUNNING (per channel):

- **Keepalive:** PING every 500 ms, IDLE every 100 ms (control + CI-V; audio has
  no idle), TOKEN renew every 60 s (control only). And **reply to the radio's own
  pings** or it drops you.
- **Reliability:** buffer sent packets by sequence number; on a retransmit request
  (`type 0x01`) resend the buffered datagram. See
  [PROTOCOL §7](./PROTOCOL.md#7-reliability-sequence-numbers--retransmit).

### Failure / recovery edges

| Event | Symptom | Handling |
|-------|---------|----------|
| Bad credentials | LOGIN-RESPONSE error `FF FF FF FE` | fail fast, surface to user |
| Radio busy (another client) | STATUS error `FD FF FF FF` | retry with backoff; single-client radio |
| Connection failed | STATUS error `FF FF FF FF` | wait / reboot radio |
| Client went silent | audio stops ~1 s; CI-V wedges; radio holds session ~15 s | keep keepalives alive; on reconnect retry ~15-30 s until `busy` clears |
| Packet loss | retransmit requests | serve from tx-buffer; self-heals |

See [PROTOCOL §8.1](./PROTOCOL.md#81-client-timeout--going-silent-verified-important).

---

## 4. Timing model

Everything is driven by short timers; there is no request/response blocking at the
transport layer. Observed intervals (LAN, ~2 ms RTT):

```
control:  PING──────500ms──────PING            IDLE─100ms─IDLE─100ms─…
          TOKEN───────────────60s───────────────TOKEN
CI-V:     PING──────500ms──────PING            IDLE─100ms─IDLE─…
          (OPEN retried ~1s until first data arrives)
audio:    PING──────500ms──────PING            radio→PC data every ~10ms
          (no idle packets)
```

A CI-V "command" is therefore **fire-and-forget with correlation**: you send the
frame and match the reply by `(command, subcommand)` when it arrives, because
transceive notifications and your replies share the channel. A synchronous
`civ_command()` helper just pumps the event loop until a matching reply (or
`FA`/`FB`) shows up or a timeout elapses - see the SDK's `transaction()`.

---

## 5. SDK structure (as built)

The layers above map onto flat modules in
[`ic7300mk2-sdk/ic7300mk2/`](../ic7300mk2-sdk/ic7300mk2/):

```
ic7300mk2/
├── radio.py       L4: the blocking public API - one Radio per radio
├── transport.py   L2: Connection plus the control / CI-V / audio channels, one I/O thread
├── frames.py      L3: build and parse FE FE … FD, OK/NG
├── encoding.py    L3: BCD frequency, 0-255 levels, mode, RIT, scope span and ref level
├── commands.py    L3: LEVELS / METERS / FUNCTIONS / SCOPE registries,
│                      DOCUMENTED_COMMANDS and is_tx_frame (§12)
├── constants.py   ports, addresses, Mode / Filter / Vfo / Preamp / Agc / AudioCodec
├── spectrum.py    27 00 sweep decoder -> Spectrum(lower_hz, upper_hz, bins, oor, mode)
├── audio.py       u-law or LPCM16 payload -> 16-bit LE mono PCM
├── passcode.py    username/password scramble table
├── state.py       cached RadioState, refreshed by transceive
└── exceptions.py  error hierarchy
```

Design notes:

- **One I/O thread, non-blocking sockets.** `transport.Connection` runs every
  channel, keepalive and retransmit on a single thread with `selectors`.
  Callers block in `transaction()` until the reply is correlated, and the
  `_txn_lock` around it makes CI-V one serialized channel per radio.
- **`_Channel` base class** holds the per-channel state of §2; `_ControlChannel`,
  `_CivChannel` and `_AudioChannel` override only their packet handlers. This
  matches wfview's `icomUdpBase` → `icomUdpHandler` / `icomUdpCivData` /
  `icomUdpAudio` hierarchy.
- **L3 is pure.** `frames.py`, `encoding.py` and `commands.py` have no socket
  code, so a USB-serial backend would replace only `transport.py`.
- **Callbacks run on the I/O thread.** `enable_waveform`, `on_audio`,
  `on_frequency_change` and `on_mode_change` all fire there, so a handler must
  not issue a blocking command. The server hands each one straight to a queue
  (§8).
- **Cached state.** `state.RadioState` holds what transceive pushes for a single
  `Radio`; the multi-client cache the web app reads is the server's poller (§9).
- **Codec choice for audio.** u-law mono (`0x01`) for bandwidth, LPCM16 mono
  (`0x04`) for quality, fixed at connect. See
  [PROTOCOL §6.2](./PROTOCOL.md#62-codec-negotiation-chosen-in-the-stream-request-35-byte-0x72).

---

## 6. Security posture (know what this is)

The radio link:

- The login "passcode" is **obfuscation, not encryption** (a fixed substitution
  table - [PROTOCOL §4](./PROTOCOL.md#4-usernamepassword-passcode-scramble)).
  Credentials and all traffic are effectively plaintext on the LAN.
- There is **no transport encryption**. Anyone on the network segment can read
  the audio and CI-V, or hijack the session. Keep the radio on a trusted VLAN;
  if it must cross untrusted networks, tunnel over a VPN.
- The radio is **single-client** for the streams - a second login gets `busy`.
  This doubles as a crude lock but is not access control.

The stack in front of it:

- The browser never reaches the radio. It talks to `ic7300mk2-server`, which
  holds the one UDP session and hands out per-session bearer tokens (§11).
- `docker compose` publishes only 8443 (nginx, TLS, self-signed certificate from
  `ic7300mk2-web/docker-entrypoint.d/40-selfsigned.sh`). The plaintext frontend
  port 8173 and the backend port 8139 bind to `127.0.0.1`, so a token or a radio
  password never crosses the network in clear.
- Radio credentials go to the server once per session create and are never
  stored in the browser. The session token is kept in localStorage under
  `ic7300.prefs.v1`, bounded by the server's idle timeout.
- Still open: `POST /api/sessions` is unauthenticated, so anyone who can reach
  the server can try radio logins on any host it can route to. `RADIO_HOSTS`,
  the per-host throttle and the connect semaphore bound that; internet exposure
  wants an authenticating proxy or a VPN in front (§11).

---

## 7. Where to start (implementation order)

The order the SDK was built in, and where each step landed:

| Step | Result | Code |
|------|--------|------|
| 1. Transport bring-up | control + CI-V channels through to STATUS | `transport.py` |
| 2. CI-V channel + frame codec | the first frequency read | `transport.py`, `frames.py` |
| 3. Typed command helpers | frequency, mode, levels, meters, functions, scope | `radio.py`, `commands.py`, `encoding.py` |
| 4. Cached state + transceive | `on_frequency_change`, `on_mode_change` | `state.py`, `radio.py` |
| 5. Reconnect and liveness | `is_connected` false on failure or 5 s of silence | `transport.py` |
| 6. Audio | RX decode, raw passthrough, the TX send path | `audio.py`, `transport.py` |

Everything above the SDK - sessions, the shared state cache, the streams and the
transmit gate - is the server. That starts at §8.

---

## 8. The three tiers

```
   browser (ic7300mk2-web)          server (ic7300mk2-server)         SDK (ic7300mk2)      radio
   ┌──────────────────────┐         ┌───────────────────────┐        ┌──────────────┐
   │ stores, React        │◄──REST──┤ routes, threadpool    ├─calls──► Radio        │──►50001
   │ stateStream          │◄──ws────┤ StatePoller           │        │ (blocking)   │◄─►50002
   │ scopeView + WebGL2   │◄──ws────┤ hub: spectrum         │◄─queue─┤ I/O thread   │◄──50003
   │ worker + AudioWorklet│◄──ws────┤ hub: audio            │◄─queue─┤ callbacks    │
   │ txAudio + mic        │───ws───►│ TX gate + watchdog    ├────────►              │
   └──────────────────────┘         └───────────────────────┘        └──────────────┘
```

| Tier | Owns | Key files |
|------|------|-----------|
| SDK | one blocking `Radio` per radio, one I/O thread, CI-V correlation, decode | `radio.py`, `transport.py` |
| server | sessions and tokens, the state poller, the broadcast hubs, the stream framing, the transmit gate | `service.py`, `poller.py`, `manager.py`, `auth.py`, `app.py`, `hub.py` |
| browser | stores, the stream consumers, the WebGL2 renderer, the audio worklets, the UI | `src/state/`, `src/sync/`, `src/scope/`, `src/audio/`, `src/components/` |

Threads inside one server session: the SDK I/O thread, the poller thread
(`state-poller`), the TX watchdog (`tx-watchdog`, started only when `TX_ENABLED`
is set), the FastAPI threadpool that runs the blocking route calls, and the
asyncio loop that serves the sockets. `hub.Hub.publish` is the only crossing
from the SDK thread into the loop: it calls `loop.call_soon_threadsafe` and fans
the item into per-client queues, dropping the oldest item when a queue is full,
so a slow browser can never apply backpressure to the radio.

Session-scoped routes are written short from here on: `/state`, `/tx/arm` and
`/ws/audio` all live under `/api/sessions/{id}/`.

The browser keeps stream data out of React. `scopeView.ts` owns the spectrum
socket, the GL renderer and the pointer handling; `rxTransport.worker.ts` owns
the audio socket and posts each buffer straight to the `pcm-sink` worklet
through a `MessagePort`. React re-renders only from the small external stores in
`src/state/` (`store.ts` is a per-key `useSyncExternalStore`).

---

## 9. The state stream

### Why polling lives on the server

The radio pushes frequency and mode, and nothing else. With CI-V transceive on
it broadcasts those two (`radio.on_frequency_change` / `on_mode_change`); levels,
functions, meters, the tuner, RIT and the scope settings answer only when asked.
CI-V is also one serialized channel: `Connection.transaction` holds `_txn_lock`
for the whole send-and-wait, so every read anywhere in the system queues behind
every other read. Clients polling on their own would multiply that by the number
of open tabs.

One `StatePoller` thread per session therefore reads the radio on a schedule,
keeps a flat cache, and publishes only what changed. `GET /state` serves the same
cache at no CI-V cost, and any number of `/ws/state` clients cost nothing extra.

### Budget

| Quantity | Value |
|----------|-------|
| One CI-V transaction, end to end | about 8.6 ms, measured on the bench LAN |
| With the poller's idle gap (`RADIO_POLL_GAP_MS`, 5 ms) | roughly 70 transactions per second of capacity |
| What the tier table below asks for | about 17 reads per second, near a quarter of it |

The rest is headroom for user commands, which always win. `RadioService._call`
wraps every SDK call in `poller.user_command()`, which raises a counter under a
`threading.Condition`; the poller finishes the read already in flight, then waits
while the counter is nonzero, and pauses 250 ms after any write. `GET /stats`
reports the achieved period per tier, read RTT p50/p95, and the mean time user
commands waited (`user_wait_ms`).

### Tiers (`poller.TIERS`)

| Tier | Period | Keys |
|------|--------|------|
| meter | 250 ms | `meters.s_meter` while receiving; `meters.power/swr/alc/compression` rotate while `ptt` |
| ptt | 1 s | `ptt` |
| deck | 1 s | `levels.rf_power`, `af_gain`, `rf_gain`, `squelch` |
| medium | 2 s | `functions.preamp/agc/noise_blanker/noise_reduction/auto_notch`, `attenuator`, `split`, `tuner`, `rit` |
| slow | 10 s | the remaining levels and functions, `meters.vd/id`, `tx_frequency`, `vfo_unselected`, `rit_enabled`, `xit_enabled`, mode/data/filter via `26 00`, `transceive`, `scope.*` |
| fallback | 5 s | `frequency`, and only while `transceive` is false |

With no `/ws/state` subscriber, or while `power` is not `on`, the schedule
collapses to a 2 s frequency probe (`PROBE_PERIOD_S`).

### Snapshot, deltas, write-through

`/ws/state` sends `{"type":"snapshot","seq","state"}` once, then
`{"type":"delta","seq","changes"}` on every change (a `null` value removes a
key) and `{"type":"ping"}` every 15 s. `seq` increments once per delta;
`radioStore.deltaPatch` drops anything at or below the last seq applied, and a
snapshot is authoritative (keys it lacks are removed).

Writes do not wait for the next poll. Once the radio acknowledges a setter,
`poller.wrote()` updates the cache, publishes the delta at once, pauses the
schedule for 250 ms and books a verify read 300 ms later. Two races close around
it: a poll that started before the write is discarded (`entry.wrote_at` against
the read's start time), and a transceive echo carrying the same value cancels the
pending verify (`poller.observed`). Actions with no known result value - VFO
swap, A=B, an ATU tune - call `poller.touch()` instead, which only schedules a
re-read.

### Power and connection

```
power:   unknown ──first OK from the frequency probe──► on
                 ──3 NG replies to the probe──────────► standby
         standby ──POST /power {"on": true}───────────► booting ──first OK──► on
                    (30 s grace: the radio boots silently, so timeouts are expected)

connection: ok ──5 consecutive timeouts──► unresponsive ──any reply──► ok
            ok ──radio.is_connected false──► lost ──POST /reconnect──► ok
```

`lost` means the SDK link is gone: the radio closed the session, or nothing
arrived on the control channel for 5 s (`transport.RX_TIMEOUT`). Polling stops
there; `POST /reconnect` opens a new link, re-arms the waveform and audio
callbacks if clients still hold them, and continues the same `seq` counter.

---

## 10. Stream formats

Both binary streams put a fixed header in front of the payload and leave the
arithmetic to the browser. JSON was measured out of the design: 475 amplitude
ints re-encoded 30 times a second ran `json.dumps` on the event loop, and the
SDK's per-sample u-law expansion ran on the I/O thread that also has to answer
the radio's pings.

`/ws/spectrum`, one message per sweep, `struct "<IIBBH"` then the bins:

| Offset | Field | What it is for |
|--------|-------|----------------|
| 0 | u32 lower edge Hz | left edge; with `upper` it gives Hz per bin and the pixel-to-frequency map behind click-to-tune |
| 4 | u32 upper edge Hz | right edge |
| 8 | u8 out of range | the tuned frequency sits outside the span; the overlay draws an arrow |
| 9 | u8 scope mode | 0 center, 1 fixed, 2/3 scroll; the renderer works from the edges alone, and clears the waterfall history when the span changes |
| 10 | u16 bin count | 475 on this radio; the renderer resizes its textures when it changes |
| 12 | bins | one amplitude byte each, nominally 0..0xA0 |

`/ws/audio`, one message per radio datagram, `struct "<BBHI"` then the codec
payload exactly as the radio sent it:

| Offset | Field | What it is for |
|--------|-------|----------------|
| 0 | u8 version | 1; a client that does not know the version drops the frame |
| 1 | u8 codec id | `0x04` LPCM16 LE mono, `0x01` u-law; the worklet picks the decoder |
| 2 | u16 sequence | the radio's own big-endian `sendseq` (datagram offset 0x12): a gap means lost audio, so the buffer inserts silence rather than splicing |
| 4 | u32 server ms | `time.monotonic()` at receipt on the I/O thread, wrapping at 2^32; the browser subtracts it from its own clock to show transit |
| 8 | payload | u-law or LPCM16 bytes, undecoded |

Forwarding the codec bytes puts the decode where there is spare CPU (a 256-entry
table in `audio/codec.ts`, run inside the worklet) and keeps a u-law session at
about a third of the LPCM16 bandwidth all the way to the browser.

The jitter buffer (`audio/jitter.ts`) runs one policy: prefill to the target,
fill an underrun with silence for the missing frames only, trim the oldest audio
with a 64-sample crossfade on overrun. The sequence number drives gap counting
and the re-prime decision; the timestamp only feeds the latency readout.
Transit is `u32Diff(nowMs - offsetMs, serverMs)` where the offset is the
lowest-RTT ping/pong sample over a 30 s window (`audio/clock.ts`); the
radio-to-server hop carries no timestamp and cannot be measured. Block cadence is
measured from arrivals rather than assumed, and the floor the UI offers is
`blockMs + 5`.

`/ws/tx` carries the mirror image: `struct "<BBH"` (version, codec `0x04`,
sequence) then 960 Int16 LE samples, one 20 ms block at 48 kHz.

---

## 11. Session authentication

`POST /api/sessions` connects a radio and returns a `token` once. The server
keeps only its SHA-256 digest on the `RadioService`; `GET /api/sessions/{id}`
returns `token: null`, and there is no session listing.

- Every `/api/sessions/{id}/...` route depends on `auth.authed_service`:
  `Authorization: Bearer <token>` compared with `hmac.compare_digest` over
  digests. An unknown id is compared against a fixed dummy digest first, so
  response time does not reveal which ids exist. Missing or wrong is 401 with
  `WWW-Authenticate: Bearer`.
- Every WebSocket is accepted, then checked: an `Origin` outside `CORS_ORIGINS`
  closes with 4403 (no `Origin` at all is allowed, since CLI tools and a future
  sidecar send none and the token is still required), and one
  `{"type":"auth","token":...}` frame must arrive within 3 s or the socket closes
  with 4401. Only then does it subscribe to a hub or acquire a radio stream.

**No user account model.** The radio is the authority: it accepts one client, and
whoever knows its credentials can have it. A session is that single connection
and the token is a capability for it, so there is no user directory to keep in
step with the radio's own login. The cost is that a token in a browser profile is
the whole authorization; the idle reaper is what bounds it.

**Takeover.** A second create for a host that already has a connected session
compares `sha256(username + NUL + password)` against the digest the live session
was created with, constant time. Matching credentials get 409 `SessionExists`, or
with `"replace": true` the old session is closed (unkeying first) and a new token
issued - the recovery path for a lost token. Mismatched credentials fall through
to the radio, which refuses the second login itself. Five mismatches lock
takeover for that host for 15 minutes, measured from the fifth failure and never
extended by attempts during the lock, so an owner is locked out for at most one
window.

**Idle reaper.** `SessionManager.reap` runs every 30 s and closes any session
with no open authenticated stream and no authenticated call for
`SESSION_IDLE_TIMEOUT_S` (default 900), plus anything older than
`SESSION_MAX_AGE_S` when that is set. Closing unkeys first.

**What is not protected.** `POST /api/sessions` is unauthenticated by design -
the radio password is the credential - which makes it a connect-to-arbitrary-host
primitive: anyone who can reach the server can have it open UDP sessions to hosts
it can route to, and can guess radio passwords one round trip at a time. What
bounds it: `RADIO_HOSTS` (allow-list, empty means any), the per-host login
throttle (1, 2, 4 ... 60 s, answered as 429 with `Retry-After` and never by
sleeping in the handler), and a semaphore of four concurrent connects (503 beyond
that). The deployment answer is TLS plus an authenticating proxy or a VPN in
front of the server; nothing here is meant to face the internet alone.

---

## 12. The transmit model

Nothing in this stack can key the radio unless the server was started with
`TX_ENABLED`. The bench has never transmitted.

### Where the gate is

In `RadioService`, below every route. Each path assembles the CI-V frame it is
about to send and runs `commands.is_tx_frame(command + data)` over it, so
re-splitting the same bytes between the `command` and `data` fields of
`POST /civ` changes nothing:

| Frame | Path |
|-------|------|
| `1C 00 01` | PTT on |
| `1C 01 02` | ATU tune cycle |
| `17 ...` | CW keyer |
| `16 46 <nonzero>` | VOX on |
| `16 47 <nonzero>` | break-in on |
| `1A 05 00 84/85` with data | DATA modulation source (the bare read is not TX) |

TX audio passes the same gate before it reaches `radio.send_tx_audio`. While TX
is disabled, `send_civ` additionally refuses any first byte outside
`commands.DOCUMENTED_COMMANDS`, so undocumented write opcodes cannot be probed
from the console. `set_ptt(False)` is never gated.

### The three conditions

Checked in this order, each answering 403:

| Condition | Error |
|-----------|-------|
| the server was started with `TX_ENABLED` | `TxDisabled` |
| the session is armed and the arm has not expired (`POST /tx/arm`, ttl clamped to 10 s .. `TX_ARM_TTL_S`) | `TxDisarmed` |
| a `/ws/tx` socket is open and its last heartbeat is under 3 s old | `TxNoHeartbeat` |

The check, the keying transaction and the `keyed_by_server` flag are one step
under `_tx_lock`. The flag is set *before* the call, because a keying command
that times out may still have reached the radio and has to be supervised; the
predicate is evaluated again when the call returns, so an arm that expired
meanwhile unkeys at once.

### The watchdog

A thread ticks every 250 ms and is level-triggered: each tick re-derives the
current state, so a missed edge cannot leave the radio keyed. While this session
may be transmitting it aborts for any of:

| Reason | Meaning |
|--------|---------|
| `disabled` | `TX_ENABLED` is not set |
| `disarmed` | the arm expired, or `DELETE /tx/arm` ran |
| `socket_closed` | the last `/ws/tx` socket closed |
| `heartbeat` | no heartbeat for 3 s |
| `timeout` | keyed longer than `TX_TIMEOUT_S` (default 180 s) |

"May be transmitting" is wider than PTT: it covers a CW message in flight and VOX
or break-in that this arm turned on. The same check runs after every keying
command, on `/ws/tx` close, on disarm, on session close, and on `close_all()` at
shutdown. `{"type":"ptt","on":false}` on `/ws/tx` runs on a worker thread rather
than the HTTP threadpool, so a saturated pool cannot delay an unkey.

Abort sends `1C 00 00`, then `17 FF` if CW was in flight, `16 46 00` / `16 47 00`
if this arm turned them on, and `1C 01 00` if the tuner reads `02`. Three
attempts half a second apart; if the radio still will not take them, or the link
is gone, the session is closed and `tx.fault` says why.

The last backstop is hardware. The radio's own time-out timer (menu
Set > Function > Time-Out Timer) is the only thing that unkeys a radio whose
server has died. Turn it on before setting `TX_ENABLED` anywhere, and give the
backend `stop_grace_period: 20s` so a shutdown has room to finish unkeying.

### Unverified until a live TX session

The bench has never transmitted, so the TX audio datagram is built from the RX
layout and from wfview by analogy. Open questions for a scheduled session with a
dummy load, the radio's time-out timer on, and `TX_ENABLED=true`:

- `transport.TX_AUDIO_IDENT` (0x0080). Only the radio's own 0x0681 / 0x0680 are
  documented; what a client should send is a guess.
- The two bytes at offset 0x14, currently sent as zero.
- Whether a 20 ms LPCM16 block goes as one datagram or as the 1388 + 580 pair the
  radio uses for RX
  ([PROTOCOL §6.3](./PROTOCOL.md#63-audio-data-packet-radio--client-24-byte-header--payload)).
- Whether the radio unkeys by itself when the session drops.
