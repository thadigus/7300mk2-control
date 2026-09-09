"""Network transport: the UDP session that carries CI-V to the radio.

Implements the RS-BA1-style control (50001) and CI-V (50002) channels and the
authenticated connect sequence. Runs a single background thread for all socket
I/O and keepalives; public CI-V transactions are submitted from caller threads
and correlated to their replies.

Layouts and the handshake order are specified in ``ai-docs/PROTOCOL.md`` and were
verified against a live radio.
"""

import random
import selectors
import socket
import struct
import threading
import time
from typing import Callable, Optional, Tuple

from .audio import decode as decode_audio
from .constants import (
    ARE_YOU_THERE_INTERVAL,
    AUDIO_PORT,
    AudioCodec,
    BROADCAST_ADDRESS,
    CIV_PORT,
    CONTROL_PORT,
    CONTROLLER_ADDRESS,
    IDLE_INTERVAL,
    PING_INTERVAL,
    RADIO_ADDRESS_DEFAULT,
    TOKEN_RENEW_INTERVAL,
)
from .exceptions import (
    AuthError,
    CommandRejected,
    CommandTimeout,
    ConnectionFailed,
    NotConnected,
    RadioBusy,
)
from .frames import CivFrame, build_frame, parse_frame
from .passcode import passcode

_WAVEFORM_COMMAND = b"\x27\x00"

#: Seconds without any datagram on the control channel before the session is
#: declared lost (the radio pings and idles every ~100 ms while it is alive).
RX_TIMEOUT = 5.0

#: ``ident`` field of a TX audio datagram. Unverified: only the radio's own
#: 0x0681/0x0680 are documented, so a live session may need another value.
TX_AUDIO_IDENT = 0x0080

#: Largest TX audio payload accepted: one 20 ms LPCM16 mono block at 48 kHz.
TX_AUDIO_MAX_PAYLOAD = 1920


def _session_id(local_ip: str, local_port: int) -> int:
    octets = [int(x) for x in local_ip.split(".")]
    return (octets[2] << 24) | (octets[3] << 16) | (local_port & 0xFFFF)


class _Pending:
    __slots__ = ("command", "event", "result", "rejected")

    def __init__(self, command: bytes):
        self.command = command
        self.event = threading.Event()
        self.result = b""
        self.rejected = False


class _Channel:
    """One UDP channel: session ids, sequencing, keepalives, retransmit buffer."""

    def __init__(self, conn: "Connection", name: str, radio_ip: str, dest_port: int):
        self.conn = conn
        self.name = name
        self.radio_ip = radio_ip
        self.dest_port = dest_port
        self.active = False

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))
        self.sock.setblocking(False)
        self.local_port = self.sock.getsockname()[1]

        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect((radio_ip, dest_port))
        self.local_ip = probe.getsockname()[0]
        probe.close()

        self.my_id = _session_id(self.local_ip, self.local_port)
        self.remote_id = 0
        self.got_here = False
        self.got_ready = False

        self.send_seq = 1
        self.ping_seq = 0
        self._tx_lock = threading.Lock()
        self._txbuf = {}

        self._last_ping = 0.0
        self._last_idle = 0.0
        self._last_ayt = 0.0
        self.last_rx = time.monotonic()
        self.send_idles = True

    def _send(self, data: bytes) -> None:
        self.sock.sendto(data, (self.radio_ip, self.dest_port))

    def _control(self, ptype: int, seq: int) -> bytes:
        return struct.pack("<IHHII", 0x10, ptype, seq, self.my_id, self.remote_id)

    def _header(self, total_len: int, ptype: int = 0) -> bytes:
        return struct.pack("<IHHII", total_len, ptype, 0, self.my_id, self.remote_id)

    def send_untracked(self, ptype: int, seq: int = 0) -> None:
        self._send(self._control(ptype, seq))

    def send_tracked(self, data: bytes) -> None:
        with self._tx_lock:
            buf = bytearray(data)
            buf[6] = self.send_seq & 0xFF
            buf[7] = (self.send_seq >> 8) & 0xFF
            data = bytes(buf)
            self._txbuf[self.send_seq] = data
            if len(self._txbuf) > 512:
                del self._txbuf[next(iter(self._txbuf))]
            self.send_seq = (self.send_seq + 1) & 0xFFFF
            self._send(data)
            self._last_idle = time.monotonic()

    def tick(self, now: float) -> None:
        if not self.active:
            return
        if not self.got_here:
            if now - self._last_ayt >= ARE_YOU_THERE_INTERVAL:
                self._last_ayt = now
                self.send_untracked(0x03, 0)
            return
        if now - self._last_ping >= PING_INTERVAL:
            self._last_ping = now
            self._send(
                self._header(0x15, 0x07)[:6]
                + struct.pack("<H", self.ping_seq)
                + struct.pack("<II", self.my_id, self.remote_id)
                + b"\x00"
                + struct.pack("<I", int(time.time() * 1000) & 0xFFFFFFFF)
            )
        if self.send_idles and self.got_ready and now - self._last_idle >= IDLE_INTERVAL:
            self.send_tracked(self._control(0x00, 0))

    def handle_common(self, raw: bytes) -> bool:
        if len(raw) == 0x10:
            _, ptype, seq, sentid, _ = struct.unpack("<IHHII", raw)
            if ptype == 0x04:
                self.remote_id = sentid
                if not self.got_here:
                    self.got_here = True
                    self.send_untracked(0x06, 0x01)
                    self.on_here()
                return True
            if ptype == 0x06:
                if not self.got_ready:
                    self.got_ready = True
                    self.on_ready()
                return True
            if ptype == 0x01:
                data = self._txbuf.get(seq)
                self._send(data if data else self._control(0x00, seq))
                return True
            if ptype == 0x00:
                return True
        if len(raw) == 0x15 and raw[4] == 0x07:
            if raw[16] == 0x00:
                reply = bytearray(raw)
                reply[0] = 0x15
                reply[8:12] = struct.pack("<I", self.my_id)
                reply[12:16] = struct.pack("<I", self.remote_id)
                reply[16] = 0x01
                self._send(bytes(reply))
            else:
                self.ping_seq = (self.ping_seq + 1) & 0xFFFF
            return True
        if len(raw) >= 0x18 and raw[0] == 0x18 and raw[4] == 0x01:
            offset = 0x10
            while offset + 4 <= len(raw):
                first, last = struct.unpack_from("<HH", raw, offset)
                seq = first
                while True:
                    data = self._txbuf.get(seq)
                    self._send(data if data else self._control(0x00, seq))
                    if seq == last:
                        break
                    seq = (seq + 1) & 0xFFFF
                offset += 4
            return True
        return False

    def drain(self) -> None:
        while True:
            try:
                data, _ = self.sock.recvfrom(4096)
            except (BlockingIOError, OSError):
                return
            self.last_rx = time.monotonic()
            self.handle(data)

    def handle(self, raw: bytes) -> None:
        self.handle_common(raw)

    def on_here(self) -> None:
        pass

    def on_ready(self) -> None:
        pass

    def disconnect(self) -> None:
        if self.got_here:
            try:
                self.send_untracked(0x05, 0)
            except OSError:
                pass

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class _ControlChannel(_Channel):
    def __init__(self, conn: "Connection", radio_ip: str):
        super().__init__(conn, "control", radio_ip, CONTROL_PORT)
        self.active = True
        self.auth_seq = 0x30
        self.tok_request = random.randint(0, 0xFFFF)
        self.token = 0
        self.logged_in = False
        self.auth_ok = False
        self.guid = b""
        self.radio_name_raw = b""
        self.civ_address: Optional[int] = None
        self.connection_type = ""
        self._last_token = 0.0

    def _auth_header(self, total_len: int, payload_size: int, reqreply: int, reqtype: int) -> bytearray:
        out = bytearray(self._header(total_len))
        out += struct.pack(">I", payload_size)
        out += bytes([reqreply, reqtype])
        out += struct.pack(">H", self.auth_seq)
        out += b"\x00\x00"
        out += struct.pack("<H", self.tok_request)
        out += struct.pack("<I", self.token)
        self.auth_seq = (self.auth_seq + 1) & 0xFFFF
        return out

    def on_ready(self) -> None:
        packet = self._auth_header(0x80, 0x70, 0x01, 0x00)
        packet += bytes(32)
        packet += passcode(self.conn.username)
        packet += passcode(self.conn.password)
        packet += self.conn.program.encode("ascii", "replace")[:16].ljust(16, b"\x00")
        packet += bytes(16)
        self.send_tracked(bytes(packet))

    def send_token(self, magic: int) -> None:
        packet = self._auth_header(0x40, 0x30, 0x01, magic)
        packet += bytes(0x40 - len(packet))
        self.send_tracked(bytes(packet))

    def request_streams(self, civ_local: int, audio_local: int) -> None:
        # The radio only arms the CI-V listener when the stream request also
        # negotiates audio; an audio-disabled request returns ports but never
        # opens CI-V. We negotiate RX audio and simply don't service the audio
        # channel (control-only SDK).
        packet = self._auth_header(0x90, 0x80, 0x01, 0x03)
        packet += self.guid
        packet += bytes(16)
        packet += self.radio_name_raw[:32].ljust(32, b"\x00")
        packet += passcode(self.conn.username)
        packet += bytes([1, 1, self.conn.rx_codec, 0x04])  # rxenable, txenable, rxcodec, txcodec
        packet += struct.pack(">I", 48000)   # rx sample rate
        packet += struct.pack(">I", 48000)   # tx sample rate
        packet += struct.pack(">I", civ_local)
        packet += struct.pack(">I", audio_local)
        packet += struct.pack(">I", self.conn.tx_buffer_ms)  # tx audio buffer (ms)
        packet += b"\x01"
        packet += bytes(7)
        self.send_tracked(bytes(packet))

    def tick(self, now: float) -> None:
        super().tick(now)
        if self.auth_ok and now - self._last_token >= TOKEN_RENEW_INTERVAL:
            self._last_token = now
            self.send_token(0x05)

    def handle(self, raw: bytes) -> None:
        if self.handle_common(raw):
            return
        length = len(raw)
        if length == 0x60 and not self.logged_in:
            self._handle_login_response(raw)
        elif length == 0x40:
            self._handle_token(raw)
        elif length >= 0xA8 and raw[0] == 0xA8 and (length - 0x42) % 0x66 == 0:
            self._handle_capabilities(raw)
        elif length == 0x50:
            self._handle_status(raw)

    def _handle_login_response(self, raw: bytes) -> None:
        error = raw[0x30:0x34]
        if error == b"\xff\xff\xff\xfe":
            self.conn._fail(AuthError("invalid username or password"))
            return
        self.token = struct.unpack_from("<I", raw, 0x1C)[0]
        self.connection_type = raw[0x40:0x50].split(b"\x00")[0].decode("ascii", "replace")
        self.logged_in = True
        self.send_token(0x02)
        self.send_token(0x05)
        self._last_token = time.monotonic()

    def _handle_token(self, raw: bytes) -> None:
        reqreply, reqtype = raw[0x14], raw[0x15]
        response = struct.unpack_from("<I", raw, 0x30)[0]
        if reqreply == 0x02 and reqtype == 0x05 and response == 0:
            self.auth_ok = True
            self.conn._maybe_request_streams()

    def _handle_capabilities(self, raw: bytes) -> None:
        base = 0x42
        self.guid = raw[base:base + 16]
        self.radio_name_raw = raw[base + 0x10:base + 0x30]
        self.civ_address = raw[base + 0x52]
        self.conn.radio_name = self.radio_name_raw.split(b"\x00")[0].decode("ascii", "replace")
        self.conn._maybe_request_streams()

    def _handle_status(self, raw: bytes) -> None:
        error = struct.unpack_from("<I", raw, 0x30)[0]
        disc = raw[0x40]
        civ_port = struct.unpack_from(">H", raw, 0x42)[0]
        audio_port = struct.unpack_from(">H", raw, 0x46)[0]
        if error == 0xFDFFFFFF:
            self.conn._fail(RadioBusy("radio is in use by another client"))
        elif error == 0xFFFFFFFF:
            self.conn._fail(ConnectionFailed("connection failed; try rebooting the radio"))
        elif error == 0 and disc == 0x01:
            self.conn._fail(ConnectionFailed("radio disconnected the session"))
        elif error == 0 and civ_port:
            self.conn._on_ports(civ_port, audio_port)


class _CivChannel(_Channel):
    def __init__(self, conn: "Connection", radio_ip: str):
        super().__init__(conn, "civ", radio_ip, CIV_PORT)
        self.civ_seq = 0
        self.opened = False
        self._last_open = 0.0

    def on_ready(self) -> None:
        self.send_open_close(open_stream=True)
        self._last_open = time.monotonic()
        self.conn._on_civ_ready()

    def tick(self, now: float) -> None:
        super().tick(now)
        if self.got_ready and not self.opened and now - self._last_open >= 0.5:
            self._last_open = now
            self.send_open_close(open_stream=True)

    def _next_civ_seq(self) -> int:
        with self._tx_lock:
            seq = self.civ_seq
            self.civ_seq = (self.civ_seq + 1) & 0xFFFF
        return seq

    def send_open_close(self, open_stream: bool) -> None:
        magic = 0x04 if open_stream else 0x00
        packet = bytearray(self._header(0x16))
        packet += b"\xc0\x01\x00"
        packet += struct.pack(">H", self._next_civ_seq())
        packet += bytes([magic])
        self.send_tracked(bytes(packet))

    def send_civ(self, command: bytes, data: bytes = b"") -> None:
        frame = build_frame(
            command, data, to=self.conn.radio_address, frm=self.conn.controller_address
        )
        packet = bytearray(self._header(0x15 + len(frame)))
        packet += b"\xc1"
        packet += struct.pack("<H", len(frame))
        packet += struct.pack(">H", self._next_civ_seq())
        packet += frame
        self.send_tracked(bytes(packet))

    def handle(self, raw: bytes) -> None:
        if self.handle_common(raw):
            return
        if len(raw) > 0x15 and raw[0x10] == 0xC1:
            data_len = struct.unpack_from("<H", raw, 0x11)[0]
            if data_len + 0x15 == struct.unpack_from("<I", raw, 0)[0]:
                self.opened = True
                payload = raw[0x15:0x15 + data_len]
                for piece in payload.split(b"\xfd"):
                    if piece:
                        frame = parse_frame(piece + b"\xfd")
                        if frame is not None:
                            self.conn._on_civ_frame(frame)


class _AudioChannel(_Channel):
    """Audio channel: runs the handshake/keepalives, delivers RX and sends TX audio.

    The radio does not start CI-V data until every negotiated stream's channel
    has completed its handshake, so this channel always runs. Incoming audio is
    delivered only while an audio handler is registered (see
    :meth:`Connection.set_audio_handler`); otherwise it is discarded cheaply.
    Datagram layout: ``ai-docs/PROTOCOL.md`` section 6.3.
    """

    def __init__(self, conn: "Connection", radio_ip: str):
        super().__init__(conn, "audio", radio_ip, AUDIO_PORT)
        self.send_idles = False
        self.sendseq = 0

    def _next_sendseq(self) -> int:
        with self._tx_lock:
            seq = self.sendseq
            self.sendseq = (self.sendseq + 1) & 0xFFFF
        return seq

    def send_audio(self, payload: bytes) -> None:
        """Send one TX audio datagram: the 24-byte header of section 6.3, then payload."""
        if len(payload) > TX_AUDIO_MAX_PAYLOAD:
            raise ValueError(
                "tx audio payload of %d bytes exceeds %d"
                % (len(payload), TX_AUDIO_MAX_PAYLOAD)
            )
        packet = bytearray(self._header(0x18 + len(payload)))
        packet += struct.pack(">HHHH", TX_AUDIO_IDENT, self._next_sendseq(), 0, len(payload))
        packet += payload
        self.send_tracked(bytes(packet))

    def handle(self, raw: bytes) -> None:
        if self.handle_common(raw):
            return
        handler, decode = self.conn._audio_sink
        if handler is None or len(raw) <= 0x18:
            return
        ptype = struct.unpack_from("<H", raw, 4)[0]
        if ptype == 0x01:  # retransmit / control, not audio
            return
        if not decode:
            sendseq = struct.unpack_from(">H", raw, 0x12)[0]
            datalen = struct.unpack_from(">H", raw, 0x16)[0]
            end = 0x18 + datalen if 0 < datalen <= len(raw) - 0x18 else len(raw)
            handler(raw[0x18:end], sendseq, time.monotonic())
            return
        seq = struct.unpack_from("<H", raw, 6)[0]
        try:
            pcm = decode_audio(raw[0x18:], self.conn.rx_codec)
        except ValueError:
            return
        handler(pcm, seq)


class Connection:
    """Owns the control + CI-V channels, the I/O thread, and the connect sequence."""

    def __init__(
        self,
        ip: str,
        username: str,
        password: str,
        program: str = "ic7300mk2",
        controller_address: int = CONTROLLER_ADDRESS,
        radio_address: Optional[int] = None,
        rx_codec: int = AudioCodec.LPCM_1CH_16BIT,
        tx_buffer_ms: int = 150,
    ):
        self.ip = ip
        self.rx_codec = int(rx_codec)
        self.tx_buffer_ms = int(tx_buffer_ms)
        try:
            self.radio_ip = socket.gethostbyname(ip)  # accepts a hostname or an IP
        except OSError as exc:
            raise ConnectionFailed("cannot resolve radio host %r (%s)" % (ip, exc))
        self.username = username
        self.password = password
        self.program = program
        self.radio_name = ""
        self.controller_address = controller_address
        self._radio_address_override = radio_address
        self.radio_address = radio_address if radio_address is not None else RADIO_ADDRESS_DEFAULT

        self._control = _ControlChannel(self, self.radio_ip)
        self._civ: Optional[_CivChannel] = None
        self._audio: Optional[_AudioChannel] = None
        self._streams_requested = False

        self._selector = selectors.DefaultSelector()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._error: Optional[Exception] = None

        self._txn_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: Optional[_Pending] = None

        self._unsolicited_handler: Optional[Callable[[CivFrame], None]] = None
        self._waveform_handler: Optional[Callable[[CivFrame], None]] = None
        self._audio_sink: Tuple[Optional[Callable[..., None]], bool] = (None, True)

    # -- lifecycle -------------------------------------------------------
    def connect(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        self._selector.register(self._control.sock, selectors.EVENT_READ, self._control)
        self._thread = threading.Thread(target=self._run, name="ic7300mk2-io", daemon=True)
        self._thread.start()
        if not self._connected.wait(timeout):
            error = self._error or ConnectionFailed(
                "timed out establishing session with %s" % self.ip
            )
            self.close()
            raise error
        if self._error:
            self.close()
            raise self._error
        # The radio sends CI-V data only in response to a command, so confirm the
        # stream is live by reading the transceiver id (the open packet may still
        # be retrying underneath). Any reply proves the stream opened - a rejection
        # (NG) counts too, since a radio in standby answers NG to most commands.
        last_error: Optional[Exception] = None
        while True:
            try:
                self.transaction(b"\x19\x00", b"", 1.0)
                return
            except CommandRejected:
                return
            except (CommandTimeout, NotConnected) as exc:
                last_error = exc
            if self._error is not None:
                self.close()
                raise self._error
            if time.monotonic() >= deadline:
                break
        self.close()
        raise ConnectionFailed(
            "CI-V stream did not open on %s (%s)" % (self.ip, last_error)
        )

    def close(self) -> None:
        if self._civ is not None and self._civ.opened:
            try:
                self._civ.send_open_close(open_stream=False)
            except OSError:
                pass
            time.sleep(0.15)
        if self._control.auth_ok:
            try:
                self._control.send_token(0x01)
            except OSError:
                pass
            time.sleep(0.15)
        for channel in self._channels():
            channel.disconnect()
        self._stop.set()
        if self._thread is not None and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)
        self._selector.close()
        for channel in self._channels():
            channel.close()

    @property
    def is_connected(self) -> bool:
        return (
            self._connected.is_set()
            and self._error is None
            and not self._stop.is_set()
            and (self._thread is None or self._thread.is_alive())
        )

    @property
    def last_error(self) -> Optional[Exception]:
        """The error that ended the session (radio disconnect, silence), or None."""
        return self._error

    # -- transactions ----------------------------------------------------
    def transaction(self, command: bytes, data: bytes, timeout: float) -> bytes:
        if not self.is_connected or self._civ is None:
            raise NotConnected("not connected to the radio")
        with self._txn_lock:
            pending = _Pending(command)
            with self._pending_lock:
                self._pending = pending
            self._civ.send_civ(command, data)
            if not pending.event.wait(timeout):
                with self._pending_lock:
                    if self._pending is pending:
                        self._pending = None
                        raise CommandTimeout("no reply to command " + command.hex(" "))
                    # The reply landed in the race window between wait() timing
                    # out and this lock; fall through and use its result.
            with self._pending_lock:
                self._pending = None
        if pending.rejected:
            raise CommandRejected(command)
        return pending.result

    def set_unsolicited_handler(self, handler: Callable[[CivFrame], None]) -> None:
        self._unsolicited_handler = handler

    def set_waveform_handler(self, handler: Callable[[CivFrame], None]) -> None:
        self._waveform_handler = handler

    def set_audio_handler(
        self, handler: Optional[Callable[..., None]], decode: bool = True
    ) -> None:
        """Register the RX audio callback; ``None`` stops delivery.

        With ``decode`` the handler gets ``(pcm, seq)``: 16-bit LE mono PCM and
        the transport sequence (LE u16 at 0x06). Without it the handler gets
        ``(payload, sendseq, t_mono)``: the codec bytes as sent (``datalen`` at
        0x16, or the rest of the datagram if that is 0 or too large), the audio
        sequence (BE u16 at 0x12) and ``time.monotonic()`` at receipt. Runs on
        the I/O thread; it must not issue blocking commands.
        """
        self._audio_sink = (handler, decode)

    def send_tx_audio(self, payload: bytes) -> None:
        """Send one TX audio payload to the radio (see ``_AudioChannel.send_audio``)."""
        audio = self._audio
        if not self.is_connected or audio is None or not audio.active:
            raise NotConnected("not connected to the radio")
        audio.send_audio(payload)

    # -- internal callbacks (run on the I/O thread) ---------------------
    def _channels(self):
        return [c for c in (self._control, self._civ, self._audio) if c is not None]

    def _run(self) -> None:
        self._control.active = True
        while not self._stop.is_set():
            try:
                self._step()
            except Exception:
                # A malformed datagram or transient socket error must not kill
                # the I/O thread and silently wedge the session.
                pass

    def _step(self) -> None:
        now = time.monotonic()
        for channel in self._channels():
            channel.tick(now)
        for key, _ in self._selector.select(timeout=0.02):
            key.data.drain()
        if self._error is None and self._connected.is_set() and now - self._control.last_rx > RX_TIMEOUT:
            self._fail(ConnectionFailed("no traffic from the radio for %g s" % RX_TIMEOUT))

    def _fail(self, error: Exception) -> None:
        if self._error is None:
            self._error = error
        self._connected.set()

    def _maybe_request_streams(self) -> None:
        control = self._control
        if self._streams_requested or not control.auth_ok or not control.guid:
            return
        self._streams_requested = True
        if self._radio_address_override is None and control.civ_address is not None:
            self.radio_address = control.civ_address
        self._civ = _CivChannel(self, self.radio_ip)
        self._audio = _AudioChannel(self, self.radio_ip)
        control.request_streams(self._civ.local_port, self._audio.local_port)

    def _on_ports(self, civ_port: int, audio_port: int) -> None:
        if self._civ is None or self._civ.active:
            return
        self._civ.dest_port = civ_port
        self._civ.active = True
        self._selector.register(self._civ.sock, selectors.EVENT_READ, self._civ)
        if self._audio is not None:
            self._audio.dest_port = audio_port
            self._audio.active = True
            self._selector.register(self._audio.sock, selectors.EVENT_READ, self._audio)

    def _on_civ_ready(self) -> None:
        if not self._connected.is_set():
            self._connected.set()

    def _on_civ_frame(self, frame: CivFrame) -> None:
        if frame.to == self.controller_address and frame.payload[:2] == _WAVEFORM_COMMAND:
            if self._waveform_handler is not None:
                self._waveform_handler(frame)
            return
        if frame.to == self.controller_address:
            with self._pending_lock:
                pending = self._pending
                if pending is not None and (
                    frame.is_ng or frame.is_ok or frame.matches(pending.command)
                ):
                    if frame.is_ng:
                        pending.rejected = True
                    elif frame.is_ok:
                        pending.result = b""
                    else:
                        pending.result = frame.data_after(pending.command)
                    self._pending = None
                    pending.event.set()
                    return
        if frame.to in (self.controller_address, BROADCAST_ADDRESS):
            if self._unsolicited_handler is not None:
                self._unsolicited_handler(frame)
