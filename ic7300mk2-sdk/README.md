# ic7300mk2

A dependency-free Python SDK for controlling an ICOM **IC-7300MK2** over its
built-in network (LAN) CI-V interface. Point it at the radio's IP or hostname, log in, and
drive the whole CI-V command set from Python - no RS-BA1 software, no USB cable.

Protocol details behind this SDK are documented in
[`../ai-docs/`](../ai-docs/). The SDK carries CI-V control plus the audio
stream in both directions.

## Install

Python 3.8+ and no runtime dependencies. The SDK is a member of the repo's uv
workspace; from the repository root:

```sh
uv sync --all-packages       # installs the SDK (and the server) editable into .venv/
```

Another project can depend on it by path (`uv add /path/to/ic7300mk2-sdk`).

> **macOS:** live control must run under Apple's `/usr/bin/python3`. Homebrew
> Python and uv-managed interpreters are blocked from reaching LAN devices by
> macOS Local Network privacy and fail with `No route to host`. Create the venv
> with `uv venv --python /usr/bin/python3` before `uv sync`. This is a macOS
> sandbox rule, not an SDK issue.

## Quick start

```python
from ic7300mk2 import Radio, Mode, Filter

with Radio("icom.turnerservices.cloud", username="your-user", password="your-pass") as radio:
    print(radio.radio_name)            # "IC-7300MK2"
    print(radio.get_frequency())       # 7217948  (Hz)
    print(radio.get_mode())            # (<Mode.LSB>, <Filter.FIL2>)

    radio.set_frequency(14_074_000)
    radio.set_mode(Mode.USB, Filter.FIL1)
    print(radio.get_s_meter())         # 0..255
```

`Radio` connects on `__enter__` and tears the session down on `__exit__`.
Without the context manager, call `radio.connect()` and `radio.close()` yourself.

## What you can control

| Area | Methods |
|------|---------|
| Frequency | `get/set_frequency`, `get/set_vfo_frequency(Vfo.SELECTED/UNSELECTED)` |
| Mode | `get/set_mode(Mode, Filter)`; `get/set_mode_ext(Mode, data, Filter)` adds the data mode (0 off, 1-3 DATA1-3) via `26 00` |
| VFO | `select_vfo("A"/"B")`, `equalize_vfos`, `swap_vfos`, `get/set_split` |
| Levels (0-255) | `get/set_level(name)` and shortcuts: `af_gain`, `rf_gain`, `rf_power`, `squelch` |
| Meters (0-255) | `get_meter(name)` and shortcuts: `s_meter`, `power_meter`, `swr_meter`, `alc_meter` |
| Functions | `get/set_function(name)`, `get/set_preamp`, `get/set_agc`, `get/set_noise_blanker`, `get/set_noise_reduction` |
| Attenuator | `get/set_attenuator` |
| Transmit | `get/set_ptt`, `get_tx_frequency`, `send_cw(text)`, `send_tx_audio(payload)` |
| Audio | `on_audio(cb, decode=True)` for RX; `rx_codec`; `Radio(..., tx_buffer_ms=150)` sets the TX buffer the radio holds |
| Antenna tuner | `get/set_tuner`, `tune()` |
| RIT / XIT | `get/set_rit`, `get/set_rit_enabled`, `get/set_xit_enabled` |
| Spectrum scope | `get/set_scope(name)` (`enabled`, `mode`, `span`, `edge`, `hold`, `ref`, `speed`, `vbw`), `set_scope_enabled`, `enable_waveform(cb)`, `disable_waveform` |
| Menu settings | `get/set_menu_setting(param, data)`, `get/set_transceive` |
| Power / identity | `power_on`, `power_off`, `get_transceiver_id` |
| Anything else | `send_command(command, data, timeout=None)` - raw CI-V escape hatch |

The full opcode list, including commands without a dedicated method, is in
[`../ai-docs/COMMANDS.md`](../ai-docs/COMMANDS.md). Reach any of them with
`send_command`:

```python
raw = radio.send_command(b"\x1a\x05\x01\x33")   # read system time
```

`get_level`/`get_meter`/`get_function`/`get_scope` take the friendly names in
[`commands.py`](ic7300mk2/commands.py) (`LEVELS`, `METERS`, `FUNCTIONS`,
`SCOPE`). Scope values are typed per name: `enabled`/`hold` are bools, `span`
is the half span in Hz (2500 .. 500000; the sweep covers twice that), `ref` is
dB in 0.5 steps (-20.0 .. 20.0), `mode`/`edge`/`speed`/`vbw` are small ints.
Every `27` sub-command except `27 10` needs a scope-selector byte `00` on both
reads and writes; `get_scope`/`set_scope` add it.

## Live state and transceive

The radio broadcasts frequency/mode changes when CI-V transceive is on (it is by
default). Register callbacks to react, and read `radio.state` for the last known
values:

```python
radio.on_frequency_change(lambda hz: print("VFO now", hz))
radio.on_mode_change(lambda mode_filter: print("mode now", mode_filter))
# ... front-panel tuning now prints updates; callbacks run on the I/O thread and
# must not issue blocking commands.
```

## Transmit safety

`set_ptt(True)`, `send_cw(...)`, and `tune()` put the radio **on the air**. Only
transmit with a proper antenna or dummy load connected and within the privileges
of your license on the current frequency.

`send_tx_audio(payload)` sends one block of TX audio (up to 1920 bytes, one 20 ms
LPCM16 mono block at 48 kHz) and keys nothing by itself: it is only modulation
while the caller holds PTT. The datagram mirrors the RX layout
([`../ai-docs/PROTOCOL.md`](../ai-docs/PROTOCOL.md) section 6.3), but its `ident`
field is unverified - only the radio's own 0x0681/0x0680 are documented, so
`transport.TX_AUDIO_IDENT` (0x0080) may need changing after a live TX session.

## Errors

All raise from `ic7300mk2`:

- `AuthError` - bad username/password.
- `RadioBusy` - another client holds the radio.
- `ConnectionFailed` - session could not be established (also the base for the
  two above).
- `CommandTimeout` - the radio didn't answer in time.
- `CommandRejected` - the radio returned NG (command not available in the current
  state).
- `NotConnected` - a command was issued before `connect()` or after the link
  dropped.

The link is watched after `connect()`: `radio.is_connected` turns false and
`radio.last_error` holds the reason when the radio ends the session (disconnect
or busy) or sends nothing on the control channel for 5 s. Create a new `Radio`
to reconnect.

## Development

```sh
uv run pytest ic7300mk2-sdk/tests      # framing + encoding tests (no radio needed)
uv run python ic7300mk2-sdk/examples/read_status.py icom.turnerservices.cloud user pass
```

The reconnect-if-busy behavior: the radio is single-client and holds a dropped
session for ~15 s. If `connect()` raises `RadioBusy` or times out right after a
prior session, retry after a short wait.

## Layout

```
ic7300mk2/
  radio.py       high-level Radio API (start here)
  transport.py   UDP session engine (control, CI-V and audio channels, I/O thread)
  frames.py      CI-V frame build/parse
  encoding.py    BCD frequency/level/tone/RIT/scope codecs
  commands.py    named LEVELS / METERS / FUNCTIONS / SCOPE registries
  constants.py   ports, addresses, Mode/Filter/Vfo/Preamp/Agc enums
  passcode.py    login credential scramble
  state.py       cached RadioState
  exceptions.py  error hierarchy
```
