from ic7300mk2 import Spectrum, parse_waveform
from ic7300mk2.encoding import encode_frequency

PIXELS = bytes(range(0, 0xA0, 5))


def _payload(mode, a_hz, b_hz, pixels=PIXELS, oor=0, seq=1, total=1, scope=0):
    return (
        b"\x27\x00" + bytes([scope, seq, total, mode])
        + encode_frequency(a_hz) + encode_frequency(b_hz) + bytes([oor]) + pixels
    )


def test_center_mode_edges():
    spec = parse_waveform(_payload(0, 14_100_000, 25_000))
    assert spec == Spectrum(
        lower_hz=14_075_000, upper_hz=14_125_000, bins=PIXELS, out_of_range=False, mode=0
    )
    assert spec.span_hz == 50_000


def test_fixed_mode_edges():
    spec = parse_waveform(_payload(1, 14_000_000, 14_350_000, oor=1))
    assert (spec.lower_hz, spec.upper_hz) == (14_000_000, 14_350_000)
    assert spec.mode == 1
    assert spec.out_of_range is True


def test_scroll_modes_use_edges_directly():
    for mode in (2, 3):
        spec = parse_waveform(_payload(mode, 7_000_000, 7_200_000))
        assert (spec.lower_hz, spec.upper_hz, spec.mode) == (7_000_000, 7_200_000, mode)


def test_bins_are_the_payload_slice():
    payload = _payload(0, 14_100_000, 25_000)
    spec = parse_waveform(payload)
    assert type(spec.bins) is bytes
    assert spec.bins == payload[17:]
    assert len(spec.bins) == len(PIXELS)


def test_sequence_and_total_guard():
    assert parse_waveform(_payload(0, 14_100_000, 25_000, seq=1, total=1)) is not None
    assert parse_waveform(_payload(0, 14_100_000, 25_000, seq=2, total=1)) is None
    assert parse_waveform(_payload(0, 14_100_000, 25_000, seq=1, total=2)) is None
    assert parse_waveform(_payload(0, 14_100_000, 25_000, seq=0, total=0)) is None


def test_rejects_non_sweeps():
    assert parse_waveform(b"\x27\x10\x01") is None
    assert parse_waveform(_payload(0, 14_100_000, 25_000, pixels=b"")) is None
    assert parse_waveform(_payload(1, 14_000_000, 14_000_000)) is None
    assert parse_waveform(_payload(1, 14_350_000, 14_000_000)) is None
    assert parse_waveform(_payload(0, 14_100_000, 0)) is None
