from ic7300mk2 import CivFrame
from ic7300mk2.frames import build_frame, parse_frame, split_frames


def test_build_frequency_query():
    assert build_frame(b"\x03") == bytes.fromhex("fe fe b6 e0 03 fd".replace(" ", ""))


def test_build_with_data_and_addresses():
    frame = build_frame(b"\x05", bytes.fromhex("4879210700"), to=0xB6, frm=0xE0)
    assert frame == bytes.fromhex("fefeb6e005487921070 0fd".replace(" ", ""))


def test_parse_reply():
    frame = parse_frame(bytes.fromhex("fefee0b60348792107 00fd".replace(" ", "")))
    assert frame is not None
    assert frame.to == 0xE0 and frame.frm == 0xB6
    assert frame.command == 0x03
    assert frame.data_after(b"\x03") == bytes.fromhex("4879210700")


def test_parse_ok_ng():
    assert parse_frame(b"\xfe\xfe\xe0\xb6\xfb\xfd").is_ok
    assert parse_frame(b"\xfe\xfe\xe0\xb6\xfa\xfd").is_ng


def test_parse_rejects_malformed():
    assert parse_frame(b"\x00\x01\x02") is None
    assert parse_frame(b"\xfe\xfe\xe0\xb6\x03") is None


def test_matches():
    frame = parse_frame(b"\xfe\xfe\xe0\xb6\x25\x00\x48\x79\x21\x07\x00\xfd")
    assert frame.matches(b"\x25\x00")
    assert not frame.matches(b"\x25\x01")
    assert frame.data_after(b"\x25\x00") == bytes.fromhex("4879210700")


def test_split_multiple_frames():
    buf = b"\xfe\xfe\xe0\xb6\x03\x00\xfd" + b"\xfe\xfe\xe0\xb6\x04\x00\x02\xfd"
    frames = split_frames(buf)
    assert len(frames) == 2
    assert frames[0].command == 0x03 and frames[1].command == 0x04
