"""Username/password obfuscation used by the ICOM login packet.

A fixed substitution table (printable ASCII 0x20..0x7E) plus a positional
offset. This is obfuscation, not encryption; credentials are effectively
plaintext on the wire.
"""

_SEQUENCE = bytes.fromhex(
    "47 5d 4c 42 66 20 23 46 4e 57 45 3d 67 76 60 41"
    "62 39 59 2d 68 7e 7c 65 7d 49 29 72 73 78 21 6e"
    "5a 5e 4a 3e 71 2c 2a 54 3c 3a 63 4f 43 75 27 79"
    "5b 35 70 48 6b 56 6f 34 32 6c 30 61 6d 7b 2f 4b"
    "64 38 2b 2e 50 40 3f 55 33 37 25 77 24 26 74 6a"
    "28 53 4d 69 22 5c 44 31 36 58 3b 7a 51 5f 52"
)


def passcode(text: str) -> bytes:
    """Return the 16-byte scrambled form of ``text`` (NUL-padded, max 16 chars)."""
    out = bytearray(16)
    for i, ch in enumerate(text.encode("ascii")[:16]):
        p = ch + i
        if p > 126:
            p = 32 + p % 127
        out[i] = _SEQUENCE[p - 32]
    return bytes(out)
