import pytest

import ic7300mk2.radio as radio_module
from ic7300mk2.constants import DEFAULT_COMMAND_TIMEOUT, Filter, Mode
from ic7300mk2.exceptions import NotConnected
from ic7300mk2.radio import Radio


class FakeConnection:
    def __init__(self, *args, **kwargs):
        self.transactions = []
        self.replies = []
        self.audio_sink = None
        self.last_error = None

    def transaction(self, command, data, timeout):
        self.transactions.append((command, data, timeout))
        return self.replies.pop(0) if self.replies else b"\x01"

    def set_audio_handler(self, handler, decode=True):
        self.audio_sink = (handler, decode)


@pytest.fixture
def radio(monkeypatch):
    monkeypatch.setattr(radio_module, "Connection", FakeConnection)
    return Radio("radio.test", "user", "pass")


def wire(radio):
    return [command + data for command, data, _ in radio._conn.transactions]


def test_send_command_uses_radio_timeout_by_default(radio):
    radio.send_command(b"\x03")
    assert radio._conn.transactions == [(b"\x03", b"", DEFAULT_COMMAND_TIMEOUT)]


def test_send_command_passes_explicit_timeout(radio):
    radio.send_command(b"\x14\x0a", b"\x00\x50", timeout=0.25)
    assert radio._conn.transactions == [(b"\x14\x0a", b"\x00\x50", 0.25)]


def test_send_command_uses_constructor_timeout(monkeypatch):
    monkeypatch.setattr(radio_module, "Connection", FakeConnection)
    radio = Radio("radio.test", "user", "pass", command_timeout=3.0)
    radio.send_command(b"\x03")
    assert radio._conn.transactions[0][2] == 3.0


def test_on_audio_forwards_decode_flag(radio):
    def cb(*args):
        pass

    radio.on_audio(cb)
    assert radio._conn.audio_sink == (cb, True)
    radio.on_audio(cb, decode=False)
    assert radio._conn.audio_sink == (cb, False)
    radio.on_audio(None)
    assert radio._conn.audio_sink == (None, True)


def test_last_error_mirrors_connection(radio):
    assert radio.last_error is None
    radio._conn.last_error = NotConnected("gone")
    assert radio.last_error is radio._conn.last_error


# -- mode with data (26 00) -------------------------------------------------

def test_get_mode_ext_decodes_bench_reply(radio):
    radio._conn.replies = [b"\x00\x00\x02"]  # verified live: LSB, data off, FIL2
    assert radio.get_mode_ext() == (Mode.LSB, 0, Filter.FIL2)
    assert wire(radio) == [b"\x26\x00"]
    assert (radio.state.mode, radio.state.filter) == (Mode.LSB, Filter.FIL2)


def test_get_mode_ext_data_modes(radio):
    radio._conn.replies = [b"\x01\x01\x01", b"\x01\x03\x03"]
    assert radio.get_mode_ext() == (Mode.USB, 1, Filter.FIL1)
    assert radio.get_mode_ext() == (Mode.USB, 3, Filter.FIL3)


@pytest.mark.parametrize("mode,data,filt,frame", [
    (Mode.USB, 0, Filter.FIL1, b"\x26\x00\x01\x00\x01"),
    (Mode.USB, 1, Filter.FIL2, b"\x26\x00\x01\x01\x02"),
    (Mode.LSB, 3, Filter.FIL3, b"\x26\x00\x00\x03\x03"),
])
def test_set_mode_ext_wire_bytes(radio, mode, data, filt, frame):
    radio.set_mode_ext(mode, data, filt)
    assert wire(radio) == [frame]
    assert radio._conn.transactions[0][:2] == (b"\x26\x00", frame[2:])
    assert (radio.state.mode, radio.state.filter) == (mode, filt)


def test_set_mode_ext_default_filter(radio):
    radio.set_mode_ext(Mode.CW, 0)
    assert wire(radio) == [b"\x26\x00\x03\x00\x01"]


@pytest.mark.parametrize("data", [-1, 4])
def test_set_mode_ext_rejects_bad_data_mode_before_sending(radio, data):
    with pytest.raises(ValueError):
        radio.set_mode_ext(Mode.USB, data)
    assert radio._conn.transactions == []


def test_get_set_mode_still_use_04_and_06(radio):
    radio._conn.replies = [b"\x00\x02"]
    assert radio.get_mode() == (Mode.LSB, Filter.FIL2)
    radio.set_mode(Mode.USB, Filter.FIL1)
    assert wire(radio) == [b"\x04", b"\x06\x01\x01"]


# -- RIT / XIT enable readback ----------------------------------------------

def test_rit_xit_enabled_getters(radio):
    radio._conn.replies = [b"\x01", b"\x00", b"\x00", b"\x01"]
    assert radio.get_rit_enabled() is True
    assert radio.get_xit_enabled() is False
    assert radio.get_rit_enabled() is False
    assert radio.get_xit_enabled() is True
    assert wire(radio) == [b"\x21\x01", b"\x21\x02", b"\x21\x01", b"\x21\x02"]
