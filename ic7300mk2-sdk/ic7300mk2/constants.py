"""Protocol constants and enumerations for the IC-7300MK2 CI-V interface."""

from enum import IntEnum

CONTROL_PORT = 50001
CIV_PORT = 50002
AUDIO_PORT = 50003

#: RX/TX audio sample rate negotiated in the stream request (Hz, mono).
AUDIO_SAMPLE_RATE = 48000

CONTROLLER_ADDRESS = 0xE0
RADIO_ADDRESS_DEFAULT = 0xB6
BROADCAST_ADDRESS = 0x00

CIV_OK = 0xFB
CIV_NG = 0xFA

PREAMBLE = b"\xfe\xfe"
END_OF_MESSAGE = 0xFD

PING_INTERVAL = 0.5
IDLE_INTERVAL = 0.1
ARE_YOU_THERE_INTERVAL = 0.5
TOKEN_RENEW_INTERVAL = 60.0

DEFAULT_COMMAND_TIMEOUT = 1.5
DEFAULT_CONNECT_TIMEOUT = 12.0


class Mode(IntEnum):
    """Operating modes (CI-V mode byte for commands 04/06/26)."""

    LSB = 0x00
    USB = 0x01
    AM = 0x02
    CW = 0x03
    RTTY = 0x04
    FM = 0x05
    CW_R = 0x07
    RTTY_R = 0x08


class Filter(IntEnum):
    """Receive filter selection (mode byte's companion)."""

    FIL1 = 0x01
    FIL2 = 0x02
    FIL3 = 0x03


class Vfo(IntEnum):
    """Selector for the per-VFO frequency/mode commands (25/26)."""

    SELECTED = 0x00
    UNSELECTED = 0x01


class Preamp(IntEnum):
    OFF = 0x00
    PREAMP1 = 0x01
    PREAMP2 = 0x02


class Agc(IntEnum):
    OFF = 0x00
    FAST = 0x01
    SLOW = 0x02


class AudioCodec(IntEnum):
    """Codec identifiers for the audio stream request (future audio support)."""

    ULAW_1CH_8BIT = 0x01
    LPCM_1CH_8BIT = 0x02
    LPCM_1CH_16BIT = 0x04
    PCM_2CH_8BIT = 0x08
    LPCM_2CH_16BIT = 0x10
    ULAW_2CH_8BIT = 0x20
    OPUS_1CH = 0x40
    ADPCM_1CH = 0x80
