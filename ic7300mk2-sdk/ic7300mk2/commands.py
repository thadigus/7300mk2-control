"""Named parameter registries for the generic get/set accessors.

Each maps a friendly name to the CI-V command bytes. Levels and meters use
2-byte BCD (0..255) data; functions use a single value byte. See
``ai-docs/COMMANDS.md`` for the full opcode reference.

``DOCUMENTED_COMMANDS`` and ``is_tx_frame`` back the server's TX gate: every
frame it forwards is checked against them before it reaches the radio.
"""

from typing import FrozenSet

# Command 0x14 sub-commands. Values are 2-byte BCD 0..255 on the wire (some map
# to a different display unit, e.g. CW pitch 0..255 -> 300..900 Hz).
LEVELS = {
    "af_gain": b"\x14\x01",
    "rf_gain": b"\x14\x02",
    "squelch": b"\x14\x03",
    "nr_level": b"\x14\x06",
    "pbt_inner": b"\x14\x07",
    "pbt_outer": b"\x14\x08",
    "cw_pitch": b"\x14\x09",
    "rf_power": b"\x14\x0a",
    "mic_gain": b"\x14\x0b",
    "key_speed": b"\x14\x0c",
    "compressor_level": b"\x14\x0e",
    "break_in_delay": b"\x14\x0f",
    "nb_level": b"\x14\x12",
    "monitor_gain": b"\x14\x15",
    "vox_gain": b"\x14\x16",
    "anti_vox_gain": b"\x14\x17",
}

# Command 0x15 sub-commands. Read-only, 2-byte BCD 0..255.
METERS = {
    "s_meter": b"\x15\x02",
    "power": b"\x15\x11",
    "swr": b"\x15\x12",
    "alc": b"\x15\x13",
    "compression": b"\x15\x14",
    "vd": b"\x15\x15",
    "id": b"\x15\x16",
}

# Command 0x16 sub-commands. Single value byte (0/1 unless noted).
FUNCTIONS = {
    "preamp": b"\x16\x02",          # 0=off, 1=P.AMP1, 2=P.AMP2
    "agc": b"\x16\x12",             # 0=off, 1=fast, 2=slow
    "noise_blanker": b"\x16\x22",
    "noise_reduction": b"\x16\x40",
    "auto_notch": b"\x16\x41",
    "repeater_tone": b"\x16\x42",
    "repeater_tsql": b"\x16\x43",
    "compressor": b"\x16\x44",
    "monitor": b"\x16\x45",
    "vox": b"\x16\x46",
    "break_in": b"\x16\x47",
    "manual_notch": b"\x16\x48",
    "twin_peak_filter": b"\x16\x4f",
    "dial_lock": b"\x16\x50",
    "ip_plus": b"\x16\x65",
}

# Command 0x27 sub-commands. Except for "enabled", the radio answers NG unless a
# scope-selector byte 00 follows the sub-command: read 27 xx 00, write 27 xx 00 <data>.
SCOPE = {
    "enabled": b"\x27\x10",         # 0/1
    "mode": b"\x27\x14",            # 0=center, 1=fixed, 2=scroll-C, 3=scroll-F
    "span": b"\x27\x15",            # half span, 5-byte LE BCD Hz
    "edge": b"\x27\x16",            # 1..4 (fixed mode)
    "hold": b"\x27\x17",            # 0/1
    "ref": b"\x27\x19",             # 2-byte BE BCD tenths of dB + sign byte
    "speed": b"\x27\x1a",           # 0..2
    "vbw": b"\x27\x1d",             # 0..1
}

#: First command byte of every row in the ``ai-docs/COMMANDS.md`` master table.
#: The FA/FB response codes are replies, not commands, and are left out.
DOCUMENTED_COMMANDS: FrozenSet[int] = frozenset(bytes.fromhex(
    "00 01 02 03 04 05 06 07 08 0b 0e 0f"
    "10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1e"
    "21 25 26 27"
))

_TX_PREFIXES = (
    b"\x1c\x00\x01",  # PTT on
    b"\x1c\x01\x02",  # ATU tune cycle
    b"\x17",          # CW keyer
)
_TX_IF_NONZERO = (b"\x16\x46", b"\x16\x47")  # VOX, break-in
_TX_IF_WRITE = (b"\x1a\x05\x00\x84", b"\x1a\x05\x00\x85")  # modulation source


def is_tx_frame(frame: bytes) -> bool:
    """True if ``frame`` (command + data, no addresses or FD) could key the radio.

    Covers PTT on, the CW keyer, an ATU tune, VOX or break-in on, and a write to
    either modulation-source setting (the bare 4-byte read is not TX).
    """
    if frame.startswith(_TX_PREFIXES):
        return True
    if frame[:2] in _TX_IF_NONZERO:
        return len(frame) > 2 and frame[2] != 0
    if frame[:4] in _TX_IF_WRITE:
        return len(frame) > 4
    return False
