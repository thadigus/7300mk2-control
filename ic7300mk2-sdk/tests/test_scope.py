import pytest

import ic7300mk2.radio as radio_module
from ic7300mk2 import commands
from ic7300mk2.radio import Radio


class ScriptedConnection:
    """Records every transaction and answers from a queue of reply data."""

    def __init__(self, *args, **kwargs):
        self.transactions = []
        self.replies = []

    def transaction(self, command, data, timeout):
        self.transactions.append((bytes(command), bytes(data)))
        return self.replies.pop(0) if self.replies else b""


@pytest.fixture
def radio(monkeypatch):
    monkeypatch.setattr(radio_module, "Connection", ScriptedConnection)
    return Radio("radio.test", "user", "pass")


def wire(radio):
    return [command + data for command, data in radio._conn.transactions]


# Reply data as captured on the bench: the bytes after "27 xx 00" (after "27 10" for enabled).
LIVE_READS = [
    ("enabled", b"\x27\x10", b"\x01", True),
    ("mode", b"\x27\x14\x00", b"\x00", 0),
    ("span", b"\x27\x15\x00", b"\x00\x50\x02\x00\x00", 25000),
    ("edge", b"\x27\x16\x00", b"\x01", 1),
    ("hold", b"\x27\x17\x00", b"\x00", False),
    ("ref", b"\x27\x19\x00", b"\x00\x00\x00", 0.0),
    ("speed", b"\x27\x1a\x00", b"\x00", 0),
    ("vbw", b"\x27\x1d\x00", b"\x00", 0),
]


@pytest.mark.parametrize("name,command,reply,value", LIVE_READS)
def test_get_scope_sends_selector_and_decodes(radio, name, command, reply, value):
    radio._conn.replies = [reply]
    result = radio.get_scope(name)
    assert result == value and type(result) is type(value)
    assert radio._conn.transactions == [(command, b"")]


def test_get_scope_decodes_nonzero_values(radio):
    radio._conn.replies = [b"\x03", b"\x00\x00\x50\x00\x00", b"\x01\x25\x01", b"\x01"]
    assert radio.get_scope("mode") == 3
    assert radio.get_scope("span") == 500000
    assert radio.get_scope("ref") == -12.5
    assert radio.get_scope("hold") is True


WRITES = [
    ("enabled", True, b"\x27\x10\x01"),
    ("enabled", False, b"\x27\x10\x00"),
    ("mode", 1, b"\x27\x14\x00\x01"),
    ("span", 25000, b"\x27\x15\x00\x00\x50\x02\x00\x00"),
    ("span", 2500, b"\x27\x15\x00\x00\x25\x00\x00\x00"),
    ("edge", 4, b"\x27\x16\x00\x04"),
    ("hold", True, b"\x27\x17\x00\x01"),
    ("ref", 0.0, b"\x27\x19\x00\x00\x00\x00"),
    ("ref", -7.5, b"\x27\x19\x00\x00\x75\x01"),
    ("ref", 20.0, b"\x27\x19\x00\x02\x00\x00"),
    ("speed", 2, b"\x27\x1a\x00\x02"),
    ("vbw", 1, b"\x27\x1d\x00\x01"),
]


@pytest.mark.parametrize("name,value,frame", WRITES)
def test_set_scope_wire_bytes(radio, name, value, frame):
    radio.set_scope(name, value)
    assert wire(radio) == [frame]
    command, _ = radio._conn.transactions[0]
    assert command == commands.SCOPE[name] + (b"" if name == "enabled" else b"\x00")


def test_set_scope_enabled_wrapper(radio):
    radio.set_scope_enabled(True)
    radio.set_scope_enabled(False)
    assert radio._conn.transactions == [(b"\x27\x10", b"\x01"), (b"\x27\x10", b"\x00")]


@pytest.mark.parametrize("name,value", [
    ("bogus", 1),
    ("mode", 4), ("mode", -1), ("mode", 1.5),
    ("edge", 0), ("edge", 5),
    ("speed", 3), ("vbw", 2),
    ("ref", 0.3), ("ref", 20.5), ("ref", -20.5), ("ref", float("nan")),
    ("span", -1), ("span", 10_000_000_000),
])
def test_set_scope_rejects_before_sending(radio, name, value):
    with pytest.raises(ValueError):
        radio.set_scope(name, value)
    assert radio._conn.transactions == []


def test_get_scope_unknown_name(radio):
    with pytest.raises(ValueError):
        radio.get_scope("bogus")
    assert radio._conn.transactions == []
