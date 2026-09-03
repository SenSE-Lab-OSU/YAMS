"""Back-compat shim.

The offline `.bin` extraction toolkit moved into PLASMA:

    python -m plasma.devices.msense.extract dir  -i <dir> -o <out>
    python -m plasma.devices.msense.extract batch -i <zips> -o <out>

`python -m yams.data_extraction -i <dir> -o <out>` still works — it forwards
straight to that CLI (a bare `-i`/`-o` with no sub-command is treated as `dir`).
"""
import sys

from plasma.devices.msense.extract.__main__ import main as _extract_main


def main(argv=None):
    _extract_main(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
