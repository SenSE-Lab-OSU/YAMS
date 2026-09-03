"""Back-compat shim.

Counter-alignment of an extracted CSV to a YAMS `.txt` reference moved into
PLASMA's extraction CLI:

    python -m plasma.devices.msense.extract sync --csv <c.csv> --txt <ref.txt> --out <dir>

`python -m yams.msense_yams_sync --csv ... --txt ... --out ...` still works — it
forwards to that `sync` sub-command.
"""
import sys

from plasma.devices.msense.extract.__main__ import main as _extract_main


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "sync":
        argv = ["sync"] + argv
    _extract_main(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
