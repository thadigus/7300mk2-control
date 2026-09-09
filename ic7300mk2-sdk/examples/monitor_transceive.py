#!/usr/bin/env python3
"""Print frequency/mode changes as they happen on the radio's front panel.

    /usr/bin/python3 examples/monitor_transceive.py <ip> <username> <password>

Turn the VFO or change mode on the radio and watch the updates arrive.
"""
import sys
import time

from ic7300mk2 import Radio


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    ip, username, password = sys.argv[1:4]

    with Radio(ip, username, password) as radio:
        radio.on_frequency_change(lambda hz: print(f"frequency -> {hz / 1e6:.6f} MHz"))
        radio.on_mode_change(lambda mf: print(f"mode      -> {mf[0].name} {mf[1].name}"))
        print("listening for front-panel changes; Ctrl-C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
