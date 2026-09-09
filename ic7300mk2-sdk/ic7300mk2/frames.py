"""CI-V frame construction and parsing (the ``FE FE ... FD`` layer)."""

from typing import NamedTuple, Optional

from .constants import (
    CIV_NG,
    CIV_OK,
    CONTROLLER_ADDRESS,
    END_OF_MESSAGE,
    PREAMBLE,
    RADIO_ADDRESS_DEFAULT,
)


class CivFrame(NamedTuple):
    """A parsed CI-V frame.

    ``payload`` is everything between the source address and the FD terminator:
    the command byte(s) followed by any data.
    """

    to: int
    frm: int
    payload: bytes

    @property
    def command(self) -> int:
        return self.payload[0] if self.payload else -1

    @property
    def is_ok(self) -> bool:
        return self.command == CIV_OK

    @property
    def is_ng(self) -> bool:
        return self.command == CIV_NG

    def matches(self, command: bytes) -> bool:
        """True if this frame is the reply to a command starting with ``command``."""
        return self.payload[:len(command)] == command

    def data_after(self, command: bytes) -> bytes:
        """Return the data bytes following ``command`` in the payload."""
        return self.payload[len(command):]


def build_frame(
    command: bytes,
    data: bytes = b"",
    to: int = RADIO_ADDRESS_DEFAULT,
    frm: int = CONTROLLER_ADDRESS,
) -> bytes:
    """Build a CI-V frame ``FE FE <to> <frm> <command><data> FD``."""
    return PREAMBLE + bytes([to, frm]) + command + data + bytes([END_OF_MESSAGE])


def parse_frame(raw: bytes) -> Optional[CivFrame]:
    """Parse one CI-V frame, or return None if it is not a well-formed frame."""
    if len(raw) < 6 or raw[:2] != PREAMBLE or raw[-1] != END_OF_MESSAGE:
        return None
    return CivFrame(to=raw[2], frm=raw[3], payload=raw[4:-1])


def split_frames(raw: bytes) -> list:
    """Split a buffer that may hold several concatenated CI-V frames."""
    frames = []
    start = raw.find(PREAMBLE)
    while start != -1:
        end = raw.find(END_OF_MESSAGE, start)
        if end == -1:
            break
        frame = parse_frame(raw[start:end + 1])
        if frame is not None:
            frames.append(frame)
        start = raw.find(PREAMBLE, end + 1)
    return frames
