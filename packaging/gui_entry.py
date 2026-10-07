"""Entry point of the frozen program window (IFC Converter.exe)."""

import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    # First thing: conversions run in "spawn" child processes, which in a frozen build are this exe
    # again. In such a child, this does the conversion and exits instead of opening another window.
    multiprocessing.freeze_support()

    # In the frozen app, sys.executable is this exe. A library that runs "sys.executable -m module" or
    # "sys.executable script.py" (IfcOpenShell does in rare fallbacks) must not start the app again.
    if len(sys.argv) > 1 and (sys.argv[1] in ("-m", "-c") or sys.argv[1].endswith(".py")):
        sys.exit(f"{Path(sys.executable).name} is not a Python interpreter: {' '.join(sys.argv[1:])}")

    from ifc_converter.gui import main

    sys.exit(main())
