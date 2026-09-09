"""Decode spectrum-scope waveform frames (``27 00``) into edge frequencies + bins.

Frame layout is specified in ``ai-docs/PROTOCOL.md`` section 10.1 and was
verified against a live radio. Frames whose sequence number or total is not 1
are rejected: multi-frame sweeps are documented for the serial interface but
have never been observed on LAN.

Amplitudes are uncalibrated; scale them against ``AMPLITUDE_MAX`` for display.
"""

from dataclasses import dataclass
from typing import Optional

from .encoding import bcd_decode_le

_WAVEFORM_COMMAND = b"\x27\x00"
_SEQ = 3
_TOTAL = 4
_MODE = 5
_FREQ_A = 6
_FREQ_B = 11
_OOR = 16
_FREQ_LEN = 5
_PIXELS_START = 17
_SCOPE_CENTER = 0

#: Nominal maximum amplitude byte value reported by the radio.
AMPLITUDE_MAX = 0xA0


@dataclass(frozen=True)
class Spectrum:
    """One decoded scope sweep."""

    lower_hz: int
    upper_hz: int
    bins: bytes
    out_of_range: bool = False
    mode: int = _SCOPE_CENTER  # scope mode byte: 0 center, 1 fixed, 2/3 scroll

    @property
    def span_hz(self) -> int:
        return self.upper_hz - self.lower_hz


def parse_waveform(payload: bytes) -> Optional[Spectrum]:
    """Decode a ``27 00`` waveform payload, or ``None`` if it is not a full sweep.

    ``payload`` is a :class:`~ic7300mk2.frames.CivFrame` payload (starts at the
    ``27`` command byte, no ``FD``).
    """
    if len(payload) <= _PIXELS_START or payload[:2] != _WAVEFORM_COMMAND:
        return None
    if payload[_SEQ] != 1 or payload[_TOTAL] != 1:
        return None
    mode = payload[_MODE]
    a = bcd_decode_le(payload[_FREQ_A:_FREQ_A + _FREQ_LEN])
    b = bcd_decode_le(payload[_FREQ_B:_FREQ_B + _FREQ_LEN])
    if mode == _SCOPE_CENTER:
        lower, upper = a - b, a + b  # a = center, b = half-span
    else:
        lower, upper = a, b
    if upper <= lower:
        return None
    return Spectrum(
        lower_hz=lower,
        upper_hz=upper,
        bins=bytes(payload[_PIXELS_START:]),
        out_of_range=bool(payload[_OOR]),
        mode=mode,
    )
