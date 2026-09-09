"""The high-level Radio API - the SDK's main entry point."""

from typing import Callable, Optional, Tuple, Union

from . import commands
from .exceptions import CommandTimeout
from .constants import (
    Agc,
    AudioCodec,
    CONTROLLER_ADDRESS,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_CONNECT_TIMEOUT,
    Filter,
    Mode,
    Preamp,
    Vfo,
)
from .encoding import (
    decode_frequency,
    decode_level,
    decode_mode,
    decode_mode_ext,
    decode_ref_db,
    decode_rit,
    decode_span_hz,
    encode_frequency,
    encode_level,
    encode_mode,
    encode_mode_ext,
    encode_ref_db,
    encode_rit,
    encode_span_hz,
)
from .frames import CivFrame
from .state import RadioState
from .transport import Connection

FrameCallback = Callable[[CivFrame], None]
AudioCallback = Callable[[bytes, int], None]  # (pcm, seq)
RawAudioCallback = Callable[[bytes, int, float], None]  # (payload, sendseq, t_mono)


class Radio:
    """A network-connected IC-7300MK2.

    Create with the radio's IP or hostname and login credentials, then
    ``connect()`` (or use
    it as a context manager). All command methods block until the radio replies
    and raise on timeout or rejection.

        with Radio("icom.turnerservices.cloud", "user", "pass") as radio:
            print(radio.get_frequency())
            radio.set_mode(Mode.USB)
    """

    def __init__(
        self,
        ip: str,
        username: str,
        password: str,
        program: str = "ic7300mk2",
        command_timeout: float = DEFAULT_COMMAND_TIMEOUT,
        controller_address: int = CONTROLLER_ADDRESS,
        radio_address: Optional[int] = None,
        rx_codec: int = AudioCodec.LPCM_1CH_16BIT,
        tx_buffer_ms: int = 150,
    ):
        self._conn = Connection(
            ip, username, password, program, controller_address, radio_address,
            rx_codec=rx_codec, tx_buffer_ms=tx_buffer_ms,
        )
        self._command_timeout = command_timeout
        self.state = RadioState()
        self._on_frequency: Optional[Callable[[int], None]] = None
        self._on_mode: Optional[Callable[[Tuple[Mode, Filter]], None]] = None

    # -- lifecycle -------------------------------------------------------
    def connect(self, timeout: float = DEFAULT_CONNECT_TIMEOUT) -> "Radio":
        """Open the session and start the CI-V stream. Blocks until ready."""
        self._conn.set_unsolicited_handler(self._on_unsolicited)
        self._conn.connect(timeout)
        return self

    def close(self) -> None:
        """Tear the session down and release the radio."""
        self._conn.close()

    def __enter__(self) -> "Radio":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def is_connected(self) -> bool:
        """False before connect(), after close(), and once the link is lost."""
        return self._conn.is_connected

    @property
    def last_error(self) -> Optional[Exception]:
        """Why the link was lost (radio disconnect, busy, 5 s of silence), or None."""
        return self._conn.last_error

    @property
    def radio_name(self) -> str:
        return self._conn.radio_name

    @property
    def civ_address(self) -> int:
        return self._conn.radio_address

    @property
    def controller_address(self) -> int:
        return self._conn.controller_address

    # -- raw escape hatch ------------------------------------------------
    def send_command(
        self, command: bytes, data: bytes = b"", timeout: Optional[float] = None
    ) -> bytes:
        """Send an arbitrary CI-V command; return the reply's data bytes.

        ``command`` is the command + sub-command (e.g. ``b"\\x14\\x0a"``).
        ``timeout`` (seconds) overrides the radio's command timeout for this
        call. Raises CommandRejected on NG and CommandTimeout if unanswered. Use
        this for any opcode without a dedicated method (see
        ``ai-docs/COMMANDS.md``).
        """
        if timeout is None:
            timeout = self._command_timeout
        return self._conn.transaction(command, data, timeout)

    def _txn(self, command: bytes, data: bytes = b"") -> bytes:
        return self._conn.transaction(command, data, self._command_timeout)

    # -- frequency -------------------------------------------------------
    def get_frequency(self) -> int:
        """Return the operating frequency in Hz."""
        freq = decode_frequency(self._txn(b"\x03"))
        self.state.frequency = freq
        return freq

    def set_frequency(self, hz: int) -> None:
        """Set the operating frequency in Hz."""
        self._txn(b"\x05", encode_frequency(hz))
        self.state.frequency = hz

    def get_vfo_frequency(self, vfo: Vfo = Vfo.SELECTED) -> int:
        """Return the selected or unselected VFO frequency in Hz."""
        return decode_frequency(self._txn(b"\x25" + bytes([int(vfo)])))

    def set_vfo_frequency(self, hz: int, vfo: Vfo = Vfo.SELECTED) -> None:
        """Set a specific VFO's frequency without making it active."""
        self._txn(b"\x25" + bytes([int(vfo)]), encode_frequency(hz))

    # -- mode ------------------------------------------------------------
    def get_mode(self) -> Tuple[Mode, Filter]:
        """Return (mode, filter) of the operating VFO."""
        mode, filt = decode_mode(self._txn(b"\x04"))
        self.state.mode, self.state.filter = mode, filt
        return mode, filt

    def set_mode(self, mode: Mode, filt: Filter = Filter.FIL1) -> None:
        """Set the operating mode and filter."""
        self._txn(b"\x06", encode_mode(mode, filt))
        self.state.mode, self.state.filter = mode, filt

    def get_mode_ext(self) -> Tuple[Mode, int, Filter]:
        """Return (mode, data, filter) of the selected VFO (26 00); data is 0 (off) or 1..3 (DATA1..3)."""
        mode, data, filt = decode_mode_ext(self._txn(b"\x26\x00"))
        self.state.mode, self.state.filter = mode, filt
        return mode, data, filt

    def set_mode_ext(self, mode: Mode, data: int, filt: Filter = Filter.FIL1) -> None:
        """Set mode, data mode (0 off, 1..3 DATA1..3) and filter of the selected VFO (26 00)."""
        self._txn(b"\x26\x00", encode_mode_ext(mode, data, filt))
        self.state.mode, self.state.filter = mode, filt

    # -- VFO -------------------------------------------------------------
    def select_vfo(self, which: str) -> None:
        """Select VFO ``"A"`` or ``"B"``."""
        sub = {"A": 0x00, "B": 0x01}[which.upper()]
        self._txn(bytes([0x07, sub]))

    def equalize_vfos(self) -> None:
        """Copy the active VFO to the other (A = B)."""
        self._txn(b"\x07\xa0")

    def swap_vfos(self) -> None:
        """Exchange VFO A and B."""
        self._txn(b"\x07\xb0")

    # -- split -----------------------------------------------------------
    def get_split(self) -> bool:
        return self._txn(b"\x0f")[0] != 0

    def set_split(self, on: bool) -> None:
        self._txn(b"\x0f", bytes([1 if on else 0]))

    # -- levels (0..255) -------------------------------------------------
    def get_level(self, name: str) -> int:
        """Read a level 0..255 (see ``commands.LEVELS`` for names)."""
        value = decode_level(self._txn(commands.LEVELS[name]))
        self.state.levels[name] = value
        return value

    def set_level(self, name: str, value: int) -> None:
        """Set a level 0..255 (see ``commands.LEVELS`` for names)."""
        self._txn(commands.LEVELS[name], encode_level(value))
        self.state.levels[name] = value

    def get_af_gain(self) -> int:
        return self.get_level("af_gain")

    def set_af_gain(self, value: int) -> None:
        self.set_level("af_gain", value)

    def get_rf_gain(self) -> int:
        return self.get_level("rf_gain")

    def set_rf_gain(self, value: int) -> None:
        self.set_level("rf_gain", value)

    def get_rf_power(self) -> int:
        return self.get_level("rf_power")

    def set_rf_power(self, value: int) -> None:
        self.set_level("rf_power", value)

    def get_squelch(self) -> int:
        return self.get_level("squelch")

    def set_squelch(self, value: int) -> None:
        self.set_level("squelch", value)

    # -- meters (read-only, 0..255) --------------------------------------
    def get_meter(self, name: str) -> int:
        """Read a meter 0..255 (see ``commands.METERS`` for names)."""
        value = decode_level(self._txn(commands.METERS[name]))
        self.state.meters[name] = value
        return value

    def get_s_meter(self) -> int:
        return self.get_meter("s_meter")

    def get_power_meter(self) -> int:
        return self.get_meter("power")

    def get_swr_meter(self) -> int:
        return self.get_meter("swr")

    def get_alc_meter(self) -> int:
        return self.get_meter("alc")

    # -- functions (on/off and small enums) ------------------------------
    def get_function(self, name: str) -> int:
        """Read a function's value byte (see ``commands.FUNCTIONS``)."""
        return self._txn(commands.FUNCTIONS[name])[0]

    def set_function(self, name: str, value: int) -> None:
        """Set a function's value byte (see ``commands.FUNCTIONS``)."""
        self._txn(commands.FUNCTIONS[name], bytes([value]))

    def get_preamp(self) -> Preamp:
        return Preamp(self.get_function("preamp"))

    def set_preamp(self, value: Preamp) -> None:
        self.set_function("preamp", int(value))

    def get_agc(self) -> Agc:
        return Agc(self.get_function("agc"))

    def set_agc(self, value: Agc) -> None:
        self.set_function("agc", int(value))

    def get_noise_blanker(self) -> bool:
        return self.get_function("noise_blanker") != 0

    def set_noise_blanker(self, on: bool) -> None:
        self.set_function("noise_blanker", 1 if on else 0)

    def get_noise_reduction(self) -> bool:
        return self.get_function("noise_reduction") != 0

    def set_noise_reduction(self, on: bool) -> None:
        self.set_function("noise_reduction", 1 if on else 0)

    # -- attenuator ------------------------------------------------------
    def get_attenuator(self) -> bool:
        return self._txn(b"\x11")[0] != 0

    def set_attenuator(self, on: bool) -> None:
        self._txn(b"\x11", bytes([0x20 if on else 0x00]))

    # -- transmit --------------------------------------------------------
    def get_ptt(self) -> bool:
        """Return True if the radio is transmitting."""
        ptt = self._txn(b"\x1c\x00")[0] != 0
        self.state.ptt = ptt
        return ptt

    def set_ptt(self, transmit: bool) -> None:
        """Key (True) or unkey (False) the transmitter.

        This puts the radio on the air. Ensure a load/antenna is connected and
        you are licensed to transmit on the current frequency.
        """
        self._txn(b"\x1c\x00", bytes([1 if transmit else 0]))
        self.state.ptt = transmit

    def get_tx_frequency(self) -> int:
        """Return the transmit frequency in Hz."""
        return decode_frequency(self._txn(b"\x1c\x03"))

    # -- antenna tuner ---------------------------------------------------
    def get_tuner(self) -> int:
        """Return ATU state (0=off, 1=on, 2=tuning)."""
        return self._txn(b"\x1c\x01")[0]

    def set_tuner(self, on: bool) -> None:
        self._txn(b"\x1c\x01", bytes([1 if on else 0]))

    def tune(self) -> None:
        """Start an ATU tuning cycle."""
        self._txn(b"\x1c\x01", b"\x02")

    # -- RIT / XIT -------------------------------------------------------
    def get_rit(self) -> int:
        """Return the RIT offset in Hz (signed)."""
        return decode_rit(self._txn(b"\x21\x00"))

    def set_rit(self, hz: int) -> None:
        self._txn(b"\x21\x00", encode_rit(hz))

    def get_rit_enabled(self) -> bool:
        return self._txn(b"\x21\x01")[0] != 0

    def set_rit_enabled(self, on: bool) -> None:
        self._txn(b"\x21\x01", bytes([1 if on else 0]))

    def get_xit_enabled(self) -> bool:
        return self._txn(b"\x21\x02")[0] != 0

    def set_xit_enabled(self, on: bool) -> None:
        self._txn(b"\x21\x02", bytes([1 if on else 0]))

    # -- power / CW / identity ------------------------------------------
    def power_off(self) -> None:
        """Turn the radio off (18 00)."""
        self._txn(b"\x18", b"\x00")

    def power_on(self) -> None:
        """Turn the radio on (18 01). Requires the radio's LAN to stay powered.

        A radio waking from standby boots without acknowledging the command, so a
        timeout here is treated as success.
        """
        try:
            self._txn(b"\x18", b"\x01")
        except CommandTimeout:
            pass

    def send_cw(self, text: str) -> None:
        """Transmit ``text`` as CW via the keyer (max 30 chars). Keys the radio."""
        self._txn(b"\x17", text.encode("ascii")[:30])

    def get_transceiver_id(self) -> int:
        """Return the radio's CI-V address as it reports it (should be 0xB6)."""
        return self._txn(b"\x19\x00")[0]

    # -- spectrum scope --------------------------------------------------
    def get_scope(self, name: str) -> Union[bool, int, float]:
        """Read a scope setting (see ``commands.SCOPE``): bool for enabled/hold,
        Hz for span, dB for ref, a small int for mode/edge/speed/vbw."""
        return _decode_scope(name, self._txn(_scope_command(name)))

    def set_scope(self, name: str, value: Union[bool, int, float]) -> None:
        """Write a scope setting (see ``commands.SCOPE``). Raises ValueError for an
        unknown name or an out-of-range value before anything is sent."""
        command = _scope_command(name)
        self._txn(command, _encode_scope(name, value))

    def set_scope_enabled(self, on: bool) -> None:
        """Turn the spectrum scope display on/off (27 10)."""
        self.set_scope("enabled", on)

    def enable_waveform(self, callback: FrameCallback) -> None:
        """Stream scope waveform frames to ``callback`` (27 11 01).

        The callback runs on the I/O thread and receives the raw ``27 00``
        CivFrame; it must not issue blocking commands. Call disable_waveform()
        to stop.
        """
        self._conn.set_waveform_handler(callback)
        self._txn(b"\x27\x11", b"\x01")

    def disable_waveform(self) -> None:
        """Stop the waveform stream (27 11 00)."""
        self._txn(b"\x27\x11", b"\x00")
        self._conn.set_waveform_handler(None)


    # -- RX audio --------------------------------------------------------
    @property
    def rx_codec(self) -> int:
        """The RX audio codec negotiated at connect (see AudioCodec)."""
        return self._conn.rx_codec

    def on_audio(
        self,
        callback: Optional[Union[AudioCallback, RawAudioCallback]],
        decode: bool = True,
    ) -> None:
        """Register the RX audio callback; ``None`` stops delivery.

        With ``decode`` (the default) it is ``callback(pcm, seq)``: 16-bit
        little-endian mono PCM at 48 kHz and the transport sequence number.
        With ``decode=False`` it is ``callback(payload, sendseq, t_mono)``: the
        codec bytes exactly as the radio sent them (format per :attr:`rx_codec`),
        the radio's audio sequence number, and ``time.monotonic()`` taken when
        the datagram arrived. Either way the callback runs on the I/O thread and
        must not issue blocking commands.
        """
        self._conn.set_audio_handler(callback, decode)

    # -- TX audio --------------------------------------------------------
    def send_tx_audio(self, payload: bytes) -> None:
        """Send one block of TX audio (48 kHz mono, format per the negotiated TX codec).

        This puts the radio on the air only while the operator has keyed it: it
        sends no CI-V and never keys anything by itself, so the caller owns PTT.
        Raises ValueError above one 20 ms block (1920 bytes) and NotConnected
        without a live link.
        """
        self._conn.send_tx_audio(payload)

    # -- menu settings (1A 05 pp pp) -------------------------------------
    def get_menu_setting(self, param: bytes) -> bytes:
        """Read a 1A05 menu setting; ``param`` is the 2-byte id (e.g. b"\\x00\\x89")."""
        return self._txn(b"\x1a\x05" + param)

    def set_menu_setting(self, param: bytes, data: bytes) -> None:
        self._txn(b"\x1a\x05" + param, data)

    def get_transceive(self) -> bool:
        """Return whether CI-V transceive (unsolicited updates) is enabled."""
        return self.get_menu_setting(b"\x00\x89")[0] != 0

    def set_transceive(self, on: bool) -> None:
        self.set_menu_setting(b"\x00\x89", bytes([1 if on else 0]))

    # -- transceive notifications ---------------------------------------
    def on_frequency_change(self, callback: Callable[[int], None]) -> None:
        """Register a callback fired when the radio reports a new frequency."""
        self._on_frequency = callback

    def on_mode_change(self, callback: Callable[[Tuple[Mode, Filter]], None]) -> None:
        """Register a callback fired when the radio reports a new mode."""
        self._on_mode = callback

    def _on_unsolicited(self, frame: CivFrame) -> None:
        command = frame.command
        if command in (0x00, 0x03) and len(frame.payload) >= 6:
            freq = decode_frequency(frame.payload[1:6])
            self.state.frequency = freq
            if self._on_frequency is not None:
                self._on_frequency(freq)
        elif command in (0x01, 0x04) and len(frame.payload) >= 3:
            mode, filt = decode_mode(frame.payload[1:3])
            self.state.mode, self.state.filter = mode, filt
            if self._on_mode is not None:
                self._on_mode((mode, filt))


_SCOPE_FLAGS = ("enabled", "hold")
_SCOPE_RANGES = {"mode": (0, 3), "edge": (1, 4), "speed": (0, 2), "vbw": (0, 1)}


def _scope_command(name: str) -> bytes:
    """Command bytes for a scope setting, with the selector byte the radio requires."""
    try:
        command = commands.SCOPE[name]
    except KeyError:
        raise ValueError("unknown scope setting %r (expected one of %s)" % (name, list(commands.SCOPE)))
    return command if name == "enabled" else command + b"\x00"


def _encode_scope(name: str, value: Union[bool, int, float]) -> bytes:
    if name in _SCOPE_FLAGS:
        return bytes([1 if value else 0])
    if name == "span":
        return encode_span_hz(value)
    if name == "ref":
        return encode_ref_db(value)
    low, high = _SCOPE_RANGES[name]
    if not isinstance(value, int) or not low <= value <= high:
        raise ValueError("%s must be an integer %d..%d" % (name, low, high))
    return bytes([value])


def _decode_scope(name: str, data: bytes) -> Union[bool, int, float]:
    if name in _SCOPE_FLAGS:
        return data[0] != 0
    if name == "span":
        return decode_span_hz(data)
    if name == "ref":
        return decode_ref_db(data)
    return data[0]
