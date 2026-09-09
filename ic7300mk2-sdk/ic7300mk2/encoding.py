"""CI-V value encoding: packed BCD for frequencies, levels, tones, and RIT.

ICOM encodes numbers as packed binary-coded decimal (two decimal digits per
byte). Frequencies are little-endian (least-significant byte first); most other
fields are big-endian. All helpers here operate on plain ``bytes``.
"""

from typing import Tuple

from .constants import Filter, Mode


def bcd_encode_le(value: int, length: int) -> bytes:
    """Encode a non-negative integer as ``length`` little-endian BCD bytes."""
    return bcd_encode_be(value, length)[::-1]


def bcd_decode_le(data: bytes) -> int:
    """Decode little-endian BCD bytes to an integer."""
    return bcd_decode_be(data[::-1])


def bcd_encode_be(value: int, length: int) -> bytes:
    """Encode a non-negative integer as ``length`` big-endian BCD bytes."""
    if value < 0:
        raise ValueError("value must be non-negative")
    digits = "%0*d" % (length * 2, value)
    if len(digits) > length * 2:
        raise ValueError("value too large for %d BCD bytes" % length)
    return bytes(int(digits[i:i + 2], 16) for i in range(0, len(digits), 2))


def bcd_decode_be(data: bytes) -> int:
    """Decode big-endian BCD bytes to an integer."""
    return int("".join("%02x" % b for b in data))


def encode_frequency(hz: int) -> bytes:
    """Encode a frequency in Hz as 5 little-endian BCD bytes (1 Hz units)."""
    if not 0 <= hz <= 9_999_999_999:
        raise ValueError("frequency out of range")
    return bcd_encode_le(hz, 5)


def decode_frequency(data: bytes) -> int:
    """Decode 5 little-endian BCD bytes to a frequency in Hz."""
    return bcd_decode_le(data[:5])


def encode_level(value: int) -> bytes:
    """Encode a 0..255 level as 2 big-endian BCD bytes (e.g. 128 -> 01 28)."""
    if not 0 <= value <= 255:
        raise ValueError("level must be 0..255")
    return bcd_encode_be(value, 2)


def decode_level(data: bytes) -> int:
    """Decode a 2-byte big-endian BCD level to 0..255."""
    return bcd_decode_be(data[:2])


def encode_mode(mode: Mode, filt: Filter = Filter.FIL1) -> bytes:
    """Encode mode + filter as the 2-byte payload for command 06."""
    return bytes([int(mode), int(filt)])


def decode_mode(data: bytes) -> Tuple[Mode, Filter]:
    """Decode a mode reply (command 04) into (Mode, Filter)."""
    mode = Mode(data[0])
    filt = Filter(data[1]) if len(data) > 1 else Filter.FIL1
    return mode, filt


def encode_mode_ext(mode: Mode, data: int, filt: Filter = Filter.FIL1) -> bytes:
    """Encode mode + data mode (0 off, 1..3 DATA1..3) + filter as the payload for command 26."""
    if not 0 <= data <= 3:
        raise ValueError("data mode must be 0..3")
    return bytes([int(mode), data, int(filt)])


def decode_mode_ext(data: bytes) -> Tuple[Mode, int, Filter]:
    """Decode a command 26 reply (``<mode> <data> <filter>``) into (Mode, data, Filter)."""
    return Mode(data[0]), data[1], Filter(data[2])


def encode_tone(hz_tenths: int) -> bytes:
    """Encode a CTCSS/repeater tone (in tenths of Hz, e.g. 885 = 88.5 Hz)."""
    return b"\x00" + bcd_encode_be(hz_tenths, 2)


def decode_tone(data: bytes) -> float:
    """Decode a 3-byte tone reply to Hz (e.g. 00 08 85 -> 88.5)."""
    return bcd_decode_be(data[-2:]) / 10.0


def encode_span_hz(hz: int) -> bytes:
    """Encode a scope half span in Hz as 5 little-endian BCD bytes (27 15)."""
    if not 0 <= hz <= 9_999_999_999:
        raise ValueError("span out of range")
    return bcd_encode_le(hz, 5)


def decode_span_hz(data: bytes) -> int:
    """Decode 5 little-endian BCD bytes to a scope half span in Hz."""
    return bcd_decode_le(data[:5])


def encode_ref_db(db: float) -> bytes:
    """Encode a scope reference level (-20.0..20.0 dB, 0.5 steps) as 2 BE BCD tenths + sign byte."""
    if not -20.0 <= db <= 20.0:
        raise ValueError("reference level out of range (-20.0..20.0 dB)")
    tenths = round(db * 10)
    if abs(db * 10 - tenths) > 1e-6 or tenths % 5:
        raise ValueError("reference level must be a multiple of 0.5 dB")
    return bcd_encode_be(abs(tenths), 2) + bytes([0x01 if tenths < 0 else 0x00])


def decode_ref_db(data: bytes) -> float:
    """Decode a 3-byte reference level reply (2 BE BCD tenths + sign, 01 = negative) to dB."""
    tenths = bcd_decode_be(data[:2])
    return (-tenths if data[2] else tenths) / 10.0


def encode_rit(hz: int) -> bytes:
    """Encode a RIT/XIT offset in Hz as 2 LE BCD magnitude bytes + sign byte."""
    if not -9999 <= hz <= 9999:
        raise ValueError("RIT offset out of range (-9999..9999)")
    sign = 0x01 if hz < 0 else 0x00
    return bcd_encode_le(abs(hz), 2) + bytes([sign])


def decode_rit(data: bytes) -> int:
    """Decode a 3-byte RIT reply (2 LE BCD magnitude + sign) to signed Hz."""
    magnitude = bcd_decode_le(data[:2])
    return -magnitude if data[2] else magnitude
