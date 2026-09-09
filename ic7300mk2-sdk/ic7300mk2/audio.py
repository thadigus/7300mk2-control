"""Decode RX audio payloads to 16-bit little-endian mono PCM (browser-ready).

The radio streams RX audio on UDP 50003. Each data packet carries raw samples at
offset 0x18, encoded with the codec negotiated in the stream request. This module
turns a payload into signed 16-bit little-endian PCM regardless of the source
codec, so downstream consumers (Web Audio, WAV, etc.) get one uniform format.

Supported RX codecs (see :class:`~ic7300mk2.constants.AudioCodec`):

* ``LPCM_1CH_16BIT`` (0x04) - 16-bit signed **little-endian** mono; passed through.
* ``ULAW_1CH_8BIT`` (0x01) - G.711 mu-law mono; expanded to 16-bit here.
"""

import struct

from .constants import AudioCodec


def _build_mulaw_table() -> list:
    table = []
    bias = 0x84
    for value in range(256):
        u = ~value & 0xFF
        sign = u & 0x80
        exponent = (u >> 4) & 0x07
        mantissa = u & 0x0F
        magnitude = ((mantissa << 3) + bias) << exponent
        sample = magnitude - bias
        table.append(-sample if sign else sample)
    return table


# mu-law byte -> signed 16-bit sample, packed little-endian for direct output.
_MULAW_LE = [struct.pack("<h", s) for s in _build_mulaw_table()]


def decode(payload: bytes, codec: int) -> bytes:
    """Decode an RX audio ``payload`` into 16-bit LE mono PCM bytes.

    Unknown codecs raise :class:`ValueError`.
    """
    if codec == AudioCodec.LPCM_1CH_16BIT:
        n = len(payload) & ~1  # whole samples only; already little-endian
        return bytes(payload[:n])
    if codec == AudioCodec.ULAW_1CH_8BIT:
        return b"".join(_MULAW_LE[b] for b in payload)
    raise ValueError("unsupported RX audio codec 0x%02x" % codec)
