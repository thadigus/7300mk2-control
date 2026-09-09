#!/usr/bin/env python3
"""Read and print the radio's current status.

    /usr/bin/python3 examples/read_status.py <ip> <username> <password>
"""
import sys

from ic7300mk2 import Radio


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    ip, username, password = sys.argv[1:4]

    with Radio(ip, username, password) as radio:
        mode, filt = radio.get_mode()
        print("radio:      ", radio.radio_name)
        print("CI-V addr:  ", hex(radio.civ_address))
        print("frequency:  ", f"{radio.get_frequency() / 1e6:.6f} MHz")
        print("mode:       ", mode.name, filt.name)
        print("VFO A/B:    ",
              f"{radio.get_vfo_frequency() / 1e6:.6f} /"
              f" {radio.get_vfo_frequency(vfo=1) / 1e6:.6f} MHz")
        print("split:      ", radio.get_split())
        print("preamp/AGC: ", radio.get_preamp().name, radio.get_agc().name)
        print("attenuator: ", radio.get_attenuator())
        print("RF power:   ", radio.get_rf_power())
        print("S-meter:    ", radio.get_s_meter())
        print("PTT:        ", "TX" if radio.get_ptt() else "RX")
    return 0


if __name__ == "__main__":
    sys.exit(main())
