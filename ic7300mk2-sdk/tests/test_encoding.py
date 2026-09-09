import pytest

from ic7300mk2 import Filter, Mode
from ic7300mk2.encoding import (
    decode_frequency,
    decode_level,
    decode_mode,
    decode_mode_ext,
    decode_ref_db,
    decode_rit,
    decode_span_hz,
    decode_tone,
    encode_frequency,
    encode_level,
    encode_mode,
    encode_mode_ext,
    encode_ref_db,
    encode_rit,
    encode_span_hz,
)


def test_frequency_roundtrip():
    for hz in (0, 1, 7_217_948, 14_074_000, 74_800_000):
        assert decode_frequency(encode_frequency(hz)) == hz


def test_frequency_known_bytes():
    assert encode_frequency(7_217_948) == bytes.fromhex("48 79 21 07 00".replace(" ", ""))
    assert decode_frequency(bytes.fromhex("4879210700")) == 7_217_948


def test_level_roundtrip():
    for value in (0, 58, 128, 164, 255):
        assert decode_level(encode_level(value)) == value


def test_level_known_bytes():
    assert encode_level(128) == b"\x01\x28"
    assert encode_level(58) == b"\x00\x58"
    assert decode_level(b"\x01\x64") == 164


def test_mode_roundtrip():
    encoded = encode_mode(Mode.USB, Filter.FIL2)
    assert encoded == b"\x01\x02"
    assert decode_mode(encoded) == (Mode.USB, Filter.FIL2)


def test_mode_known():
    assert decode_mode(b"\x00\x02") == (Mode.LSB, Filter.FIL2)


def test_mode_ext_roundtrip_and_live_bytes():
    assert decode_mode_ext(b"\x00\x00\x02") == (Mode.LSB, 0, Filter.FIL2)
    for data in range(4):
        encoded = encode_mode_ext(Mode.USB, data, Filter.FIL3)
        assert encoded == bytes([0x01, data, 0x03])
        assert decode_mode_ext(encoded) == (Mode.USB, data, Filter.FIL3)
    assert encode_mode_ext(Mode.CW, 0) == b"\x03\x00\x01"
    for bad in (-1, 4):
        with pytest.raises(ValueError):
            encode_mode_ext(Mode.USB, bad)


def test_rit_signed():
    assert decode_rit(encode_rit(-250)) == -250
    assert decode_rit(encode_rit(500)) == 500
    assert decode_rit(b"\x00\x00\x00") == 0


def test_tone_decode():
    assert decode_tone(b"\x00\x08\x85") == 88.5


def test_span_roundtrip_and_live_bytes():
    for hz in (2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000):
        assert decode_span_hz(encode_span_hz(hz)) == hz
    assert encode_span_hz(25000) == bytes.fromhex("0050020000")
    assert decode_span_hz(bytes.fromhex("0050020000")) == 25000
    for bad in (-1, 10_000_000_000):
        with pytest.raises(ValueError):
            encode_span_hz(bad)


def test_ref_db_roundtrip_and_sign():
    for db in (-20.0, -7.5, -0.5, 0.0, 0.5, 12.5, 20.0):
        assert decode_ref_db(encode_ref_db(db)) == db
    assert encode_ref_db(0.0) == b"\x00\x00\x00"
    assert encode_ref_db(-7.5) == b"\x00\x75\x01"
    assert encode_ref_db(20) == b"\x02\x00\x00"
    assert decode_ref_db(b"\x01\x25\x01") == -12.5
    assert decode_ref_db(b"\x00\x05\x00") == 0.5
    for bad in (0.3, 0.25, 20.5, -20.5, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            encode_ref_db(bad)
