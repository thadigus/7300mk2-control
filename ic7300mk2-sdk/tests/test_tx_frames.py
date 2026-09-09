import pytest

from ic7300mk2.commands import DOCUMENTED_COMMANDS, is_tx_frame

TX_FRAMES = [
    b"\x1c\x00\x01",              # PTT on
    b"\x1c\x00\x01\x00",          # PTT on with trailing bytes
    b"\x17",                      # CW keyer, empty message
    b"\x17CQ CQ DE N0CALL",       # CW keyer with text
    b"\x1c\x01\x02",              # ATU tune cycle
    b"\x16\x46\x01",              # VOX on
    b"\x16\x47\x01",              # break-in semi
    b"\x16\x47\x02",              # break-in full
    b"\x1a\x05\x00\x84\x00",      # DATA-OFF mod source write
    b"\x1a\x05\x00\x85\x03",      # DATA1 mod source write
    b"\x1a\x05\x00\x84\x00\x05",  # mod source write, longer data
]

NON_TX_FRAMES = [
    b"\x1c\x00\x00",          # PTT off
    b"\x1c\x00",              # PTT read
    b"\x1c\x01\x01",          # tuner on (not a tune cycle)
    b"\x1c\x01\x00",          # tuner off
    b"\x1c\x01",              # tuner read
    b"\x1c\x02\x01",          # TX frequency monitor
    b"\x16\x46\x00",          # VOX off
    b"\x16\x47\x00",          # break-in off
    b"\x16\x46",              # VOX read
    b"\x16\x47",              # break-in read
    b"\x16\x45\x01",          # monitor on (unrelated function)
    b"\x1a\x05\x00\x84",      # mod source read
    b"\x1a\x05\x00\x85",      # mod source read
    b"\x1a\x05\x00\x83\x01\x00",  # LAN mod level write
    b"\x1a\x05\x01\x84\x01",  # different menu page
    b"\x03",                  # frequency read
    b"\x05\x00\x00\x00\x14\x00",  # frequency write
    b"\x14\x0a\x00\x50",      # level write
    b"\x18\x01",              # power on
    b"",
]


@pytest.mark.parametrize("frame", TX_FRAMES, ids=lambda f: f.hex(" "))
def test_tx_frames(frame):
    assert is_tx_frame(frame)


@pytest.mark.parametrize("frame", NON_TX_FRAMES, ids=lambda f: f.hex(" ") or "empty")
def test_non_tx_frames(frame):
    assert not is_tx_frame(frame)


@pytest.mark.parametrize(
    "command, data",
    [(b"\x1c", b"\x00\x01"), (b"\x1c\x00", b"\x01"), (b"\x1c\x00\x01", b"")],
)
def test_split_encoding_invariance(command, data):
    assert is_tx_frame(command + data)


@pytest.mark.parametrize("frame", TX_FRAMES, ids=lambda f: f.hex(" "))
def test_every_split_point_agrees(frame):
    for i in range(len(frame) + 1):
        assert is_tx_frame(frame[:i] + frame[i:])


def test_documented_commands():
    assert isinstance(DOCUMENTED_COMMANDS, frozenset)
    assert DOCUMENTED_COMMANDS == frozenset(
        [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0B, 0x0E, 0x0F,
         0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B,
         0x1C, 0x1E, 0x21, 0x25, 0x26, 0x27]
    )
    for undocumented in (0x09, 0x0A, 0x0C, 0x0D, 0x1D, 0x1F, 0x20, 0x30, 0xFA, 0xFB):
        assert undocumented not in DOCUMENTED_COMMANDS
    assert b"\x03"[0] in DOCUMENTED_COMMANDS
