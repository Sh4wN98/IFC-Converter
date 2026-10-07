"""Entry point of the frozen command-line tool (ifc-convert.exe)."""

import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    # First thing: conversions run in "spawn" child processes, which in a frozen build are this exe
    # again. In such a child, this does the conversion and exits.
    multiprocessing.freeze_support()

    # In the frozen app, sys.executable is this exe. A library that runs "sys.executable -m module" or
    # "sys.executable script.py" (IfcOpenShell does in rare fallbacks) must not start the app again.
    if len(sys.argv) > 1 and (sys.argv[1] in ("-m", "-c") or sys.argv[1].endswith(".py")):
        sys.exit(f"{Path(sys.executable).name} is not a Python interpreter: {' '.join(sys.argv[1:])}")

    # The output contains ✓, → and umlauts. A real console takes them anyway; redirected to a file or
    # pipe, Windows would encode with the ANSI code page and fail, so use UTF-8 like start.bat did.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    from ifc_converter.cli import main

    sys.exit(main())
