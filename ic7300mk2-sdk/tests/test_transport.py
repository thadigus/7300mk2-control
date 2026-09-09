import selectors
import struct
import time
import types

import pytest

import ic7300mk2.transport as transport_module
from ic7300mk2.constants import AudioCodec
from ic7300mk2.exceptions import ConnectionFailed, NotConnected, RadioBusy
from ic7300mk2.transport import RX_TIMEOUT, Connection, _AudioChannel


class FakeConnection:
    def __init__(self, handler, decode, rx_codec=AudioCodec.LPCM_1CH_16BIT):
        self._audio_sink = (handler, decode)
        self.rx_codec = int(rx_codec)


def _channel(handler, decode=True, rx_codec=AudioCodec.LPCM_1CH_16BIT):
    chan = _AudioChannel.__new__(_AudioChannel)
    chan.conn = FakeConnection(handler, decode, rx_codec)
    return chan


def _datagram(payload, sendseq=0x1234, datalen=None, seq=7, ptype=0):
    if datalen is None:
        datalen = len(payload)
    header = struct.pack("<IHHII", 0x18 + len(payload), ptype, seq, 0x11111111, 0x22222222)
    header += struct.pack(">HHHH", 0x0681, sendseq, 0, datalen)
    assert len(header) == 0x18
    return header + payload


PAYLOAD = bytes(range(16))


def test_raw_handler_gets_payload_sendseq_and_monotonic_time():
    calls = []
    before = time.monotonic()
    _channel(lambda *a: calls.append(a), decode=False).handle(_datagram(PAYLOAD))
    after = time.monotonic()
    assert len(calls) == 1
    payload, sendseq, t_mono = calls[0]
    assert payload == PAYLOAD
    assert sendseq == 0x1234
    assert before <= t_mono <= after


def test_raw_handler_sendseq_is_big_endian():
    calls = []
    _channel(lambda *a: calls.append(a), decode=False).handle(_datagram(PAYLOAD, sendseq=0x0102))
    assert calls[0][1] == 0x0102


def test_raw_handler_slices_payload_to_datalen():
    calls = []
    _channel(lambda *a: calls.append(a), decode=False).handle(_datagram(PAYLOAD, datalen=10))
    assert calls[0][0] == PAYLOAD[:10]


def test_raw_handler_zero_datalen_falls_back_to_rest_of_datagram():
    calls = []
    _channel(lambda *a: calls.append(a), decode=False).handle(_datagram(PAYLOAD, datalen=0))
    assert calls[0][0] == PAYLOAD


def test_raw_handler_oversized_datalen_falls_back_to_rest_of_datagram():
    calls = []
    _channel(lambda *a: calls.append(a), decode=False).handle(_datagram(PAYLOAD, datalen=0xFFFF))
    assert calls[0][0] == PAYLOAD


def test_decode_handler_gets_pcm_and_transport_seq():
    calls = []
    _channel(lambda *a: calls.append(a), decode=True).handle(_datagram(PAYLOAD, seq=0x0201))
    assert calls == [(PAYLOAD, 0x0201)]


def test_decode_handler_expands_ulaw():
    calls = []
    chan = _channel(lambda *a: calls.append(a), decode=True, rx_codec=AudioCodec.ULAW_1CH_8BIT)
    chan.handle(_datagram(b"\xff\x7f"))
    assert calls[0][0] == b"\x00\x00\x00\x00"


def test_ignored_datagrams():
    for decode in (True, False):
        calls = []
        chan = _channel(lambda *a: calls.append(a), decode=decode)
        chan.handle(_datagram(PAYLOAD, ptype=1))
        chan.handle(_datagram(b""))
        assert calls == []
    chan = _channel(None, decode=False)
    chan.handle(_datagram(PAYLOAD))


# -- liveness: a connected session with a fake clock, socket and selector ----

class FakeClock:
    """Stands in for the ``time`` module inside transport."""

    def __init__(self, now=1000.0):
        self.now = now

    def monotonic(self):
        return self.now

    time = monotonic

    def sleep(self, seconds):
        self.now += seconds


class FakeSock:
    def __init__(self):
        self.inbox = []

    def recvfrom(self, size):
        if not self.inbox:
            raise BlockingIOError
        return self.inbox.pop(0), ("10.0.0.1", 50001)


class FakeSelector:
    def __init__(self, channel):
        self.key = types.SimpleNamespace(data=channel)

    def select(self, timeout=None):
        return [(self.key, selectors.EVENT_READ)]

    def close(self):
        pass


@pytest.fixture
def link(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(transport_module, "time", clock)
    conn = Connection("127.0.0.1", "user", "pass")
    control = conn._control
    real_sock = control.sock
    control.sock = FakeSock()
    control.sent = []
    control._send = control.sent.append
    conn._selector.close()
    conn._selector = FakeSelector(control)
    control.got_here = control.got_ready = True
    conn._on_civ_ready()
    yield conn, clock
    real_sock.close()


def _ping_request(seq=1):
    return struct.pack("<IHHII", 0x15, 0x07, seq, 0xAAAA, 0xBBBB) + b"\x00" + struct.pack("<I", 12345)


def _status(error=0, disc=0):
    raw = bytearray(0x50)
    raw[0] = 0x50
    struct.pack_into("<I", raw, 0x30, error)
    raw[0x40] = disc
    return bytes(raw)


def test_connected_after_civ_ready(link):
    conn, _ = link
    assert conn.is_connected
    assert conn.last_error is None


@pytest.mark.parametrize("status,error_type", [
    (_status(disc=0x01), ConnectionFailed),
    (_status(error=0xFDFFFFFF), RadioBusy),
    (_status(error=0xFFFFFFFF), ConnectionFailed),
])
def test_radio_ending_the_session_drops_is_connected(link, status, error_type):
    conn, _ = link
    conn._control.sock.inbox.append(status)
    conn._step()
    assert not conn.is_connected
    assert isinstance(conn.last_error, error_type)
    with pytest.raises(NotConnected):
        conn.transaction(b"\x03", b"", 0.1)


def test_healthy_status_keeps_the_link(link):
    conn, _ = link
    conn._control.sock.inbox.append(_status())
    conn._step()
    assert conn.is_connected


def test_silence_drops_is_connected_after_rx_timeout(link):
    conn, clock = link
    clock.now += RX_TIMEOUT - 0.1
    conn._step()
    assert conn.is_connected
    clock.now += 0.2
    conn._step()
    assert not conn.is_connected
    assert isinstance(conn.last_error, ConnectionFailed)
    assert "%g s" % RX_TIMEOUT in str(conn.last_error)


def test_silence_before_connect_is_not_an_error(link):
    conn, clock = link
    conn._connected.clear()
    clock.now += RX_TIMEOUT + 1
    conn._step()
    assert conn.last_error is None
    assert not conn.is_connected


def test_pings_keep_the_link_alive(link):
    conn, clock = link
    steps = int(3 * RX_TIMEOUT / 0.1)
    for seq in range(steps):
        clock.now += 0.1
        conn._control.sock.inbox.append(_ping_request(seq))
        conn._step()
        assert conn.is_connected
    assert conn.last_error is None
    replies = [d for d in conn._control.sent if len(d) == 0x15 and d[4] == 0x07 and d[16] == 0x01]
    assert len(replies) == steps


def test_first_error_sticks_and_stepping_continues(link):
    conn, clock = link
    clock.now += RX_TIMEOUT + 1
    conn._step()
    first = conn.last_error
    clock.now += 1
    conn._control.sock.inbox.append(_status(error=0xFDFFFFFF))
    conn._step()
    assert conn.last_error is first
    assert not conn.is_connected
