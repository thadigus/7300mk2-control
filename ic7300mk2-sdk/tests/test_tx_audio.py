"""TX audio datagram layout (client -> radio, mirroring PROTOCOL.md section 6.3)."""

import struct

import pytest

from ic7300mk2.constants import AUDIO_PORT, AudioCodec
from ic7300mk2.exceptions import NotConnected
from ic7300mk2.transport import (
    TX_AUDIO_IDENT,
    TX_AUDIO_MAX_PAYLOAD,
    Connection,
    _AudioChannel,
)

RADIO_IP = "127.0.0.1"
PAYLOAD = struct.pack("<960h", *range(-480, 480))  # 20 ms of LPCM16 mono at 48 kHz


class FakeSock:
    """Stands in for the channel's UDP socket, capturing every sendto."""

    def __init__(self):
        self.sent = []

    def sendto(self, data, address):
        self.sent.append((data, address))

    def close(self):
        pass


class FakeConnection:
    def __init__(self, tx_buffer_ms=150):
        self.tx_buffer_ms = tx_buffer_ms
        self.rx_codec = int(AudioCodec.LPCM_1CH_16BIT)
        self._audio_sink = (None, True)


@pytest.fixture
def channel():
    chan = _AudioChannel(FakeConnection(), RADIO_IP)
    chan.sock.close()
    chan.sock = FakeSock()
    chan.active = True
    chan.my_id = 0x11111111
    chan.remote_id = 0x22222222
    yield chan


def _sent(chan):
    return [data for data, _ in chan.sock.sent]


def test_datagram_layout(channel):
    channel.send_audio(PAYLOAD)
    (data, address), = channel.sock.sent
    assert address == (RADIO_IP, AUDIO_PORT)
    assert len(data) == 0x18 + len(PAYLOAD)
    assert struct.unpack_from("<I", data, 0x00)[0] == 0x18 + 1920
    assert struct.unpack_from("<H", data, 0x04)[0] == 0
    assert struct.unpack_from("<I", data, 0x08)[0] == 0x11111111
    assert struct.unpack_from("<I", data, 0x0C)[0] == 0x22222222
    assert struct.unpack_from(">H", data, 0x10)[0] == TX_AUDIO_IDENT
    assert struct.unpack_from(">H", data, 0x12)[0] == 0
    assert struct.unpack_from(">H", data, 0x14)[0] == 0
    assert struct.unpack_from(">H", data, 0x16)[0] == 1920
    assert data[0x18:] == PAYLOAD


def test_sendseq_is_big_endian_and_increments(channel):
    for _ in range(3):
        channel.send_audio(PAYLOAD)
    assert [struct.unpack_from(">H", d, 0x12)[0] for d in _sent(channel)] == [0, 1, 2]
    assert channel.sendseq == 3


def test_sendseq_wraps_at_65536(channel):
    channel.sendseq = 0xFFFF
    channel.send_audio(PAYLOAD)
    channel.send_audio(PAYLOAD)
    assert [struct.unpack_from(">H", d, 0x12)[0] for d in _sent(channel)] == [0xFFFF, 0]
    assert channel.sendseq == 1


def test_transport_seq_is_tracked_for_retransmit(channel):
    channel.send_audio(PAYLOAD)
    channel.send_audio(PAYLOAD)
    first, second = _sent(channel)
    assert struct.unpack_from("<H", first, 0x06)[0] == 1
    assert struct.unpack_from("<H", second, 0x06)[0] == 2
    assert channel._txbuf[1] == first
    assert channel._txbuf[2] == second


def test_short_payload_is_sent_as_is(channel):
    channel.send_audio(b"\x01\x02")
    (data, _), = channel.sock.sent
    assert struct.unpack_from("<I", data, 0x00)[0] == 0x1A
    assert struct.unpack_from(">H", data, 0x16)[0] == 2
    assert data[0x18:] == b"\x01\x02"


def test_largest_accepted_payload(channel):
    channel.send_audio(bytes(TX_AUDIO_MAX_PAYLOAD))
    assert len(_sent(channel)[0]) == 0x18 + TX_AUDIO_MAX_PAYLOAD


def test_oversized_payload_raises_and_sends_nothing(channel):
    with pytest.raises(ValueError):
        channel.send_audio(bytes(TX_AUDIO_MAX_PAYLOAD + 1))
    assert channel.sock.sent == []
    assert channel.sendseq == 0
    assert channel._txbuf == {}


@pytest.fixture
def connection():
    conn = Connection(RADIO_IP, "user", "pass")
    yield conn
    conn.close()


def test_send_tx_audio_without_an_audio_channel_raises(connection):
    with pytest.raises(NotConnected):
        connection.send_tx_audio(PAYLOAD)


def test_send_tx_audio_before_the_channel_is_active_raises(connection, channel):
    connection._connected.set()
    connection._audio = channel
    channel.active = False
    with pytest.raises(NotConnected):
        connection.send_tx_audio(PAYLOAD)
    channel.active = True
    connection.send_tx_audio(PAYLOAD)
    assert len(channel.sock.sent) == 1


def test_send_tx_audio_after_the_link_failed_raises(connection, channel):
    connection._connected.set()
    connection._audio = channel
    connection._fail(NotConnected("gone"))
    with pytest.raises(NotConnected):
        connection.send_tx_audio(PAYLOAD)
    assert channel.sock.sent == []


@pytest.mark.parametrize("tx_buffer_ms", [None, 40, 300])
def test_stream_request_carries_the_tx_audio_buffer(tx_buffer_ms):
    kwargs = {} if tx_buffer_ms is None else {"tx_buffer_ms": tx_buffer_ms}
    conn = Connection(RADIO_IP, "user", "pass", **kwargs)
    try:
        control = conn._control
        control.sock.close()
        control.sock = FakeSock()
        control.guid = bytes(16)
        control.radio_name_raw = b"IC-7300MK2"
        control.request_streams(50100, 50101)
        packet = control.sock.sent[0][0]
        assert struct.unpack_from("<I", packet, 0)[0] == 0x90
        # the buffer is the last u32 before the trailing 01 + 7 zero bytes
        assert struct.unpack_from(">I", packet, len(packet) - 12)[0] == (tx_buffer_ms or 150)
    finally:
        conn.close()
