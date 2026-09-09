"""ic7300mk2 - a Python SDK for the ICOM IC-7300MK2 network CI-V interface.

    from ic7300mk2 import Radio, Mode

    with Radio("icom.turnerservices.cloud", "user", "pass") as radio:
        print(radio.get_frequency())
        radio.set_mode(Mode.USB)
"""

from .constants import Agc, AudioCodec, Filter, Mode, Preamp, Vfo
from .exceptions import (
    AuthError,
    CommandRejected,
    CommandTimeout,
    ConnectionFailed,
    Ic7300Error,
    NotConnected,
    RadioBusy,
)
from .frames import CivFrame
from .radio import Radio
from .spectrum import Spectrum, parse_waveform
from .state import RadioState

__version__ = "0.1.0"

__all__ = [
    "Radio",
    "RadioState",
    "CivFrame",
    "Spectrum",
    "parse_waveform",
    "Mode",
    "Filter",
    "Vfo",
    "Preamp",
    "Agc",
    "AudioCodec",
    "Ic7300Error",
    "ConnectionFailed",
    "AuthError",
    "RadioBusy",
    "NotConnected",
    "CommandTimeout",
    "CommandRejected",
    "__version__",
]
