"""Cached radio state, updated by polling and by transceive notifications."""

from dataclasses import dataclass, field
from typing import Dict, Optional

from .constants import Filter, Mode


@dataclass
class RadioState:
    """A snapshot of radio state the SDK keeps up to date.

    Frequency and mode are refreshed automatically from the radio's transceive
    broadcasts when transceive is enabled; other fields are populated when the
    corresponding getter is called.
    """

    frequency: Optional[int] = None
    mode: Optional[Mode] = None
    filter: Optional[Filter] = None
    ptt: Optional[bool] = None
    split: Optional[bool] = None
    meters: Dict[str, int] = field(default_factory=dict)
    levels: Dict[str, int] = field(default_factory=dict)
