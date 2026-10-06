"""Stand-ins for convert() that run in the conversion child process (so they must be importable)."""

import os
import signal
import time
from pathlib import Path

from ifc_converter.converter import ConversionResult, convert


def report_pid(input_path, output_path, fmt, threads, progress=None, **options):
    """Write the process id into the output file instead of converting."""
    progress(0)
    Path(output_path).write_text(str(os.getpid()))
    progress(100)
    return ConversionResult(output=Path(output_path), elements=1)


def killed_if_named_crash(input_path, output_path, fmt, threads, progress=None, **options):
    """Get SIGKILLed like by the OOM killer for files named crash.ifc; convert anything else."""
    if Path(input_path).stem == "crash":
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("partial")
        os.kill(os.getpid(), signal.SIGKILL)
    return convert(input_path, output_path, fmt, threads, progress, **options)


def exit_hard(input_path, output_path, fmt, threads, progress=None, **options):
    """End the process without a result, like a native crash."""
    os._exit(3)


def raise_error(input_path, output_path, fmt, threads, progress=None, **options):
    raise ValueError(f"{Path(input_path).name} ist kaputt")


def raise_bare_error(input_path, output_path, fmt, threads, progress=None, **options):
    raise KeyError


def sleep_while_reading(input_path, output_path, fmt, threads, progress=None, **options):
    """Leave the process id beside the output, then sleep like a very long read of the IFC file."""
    Path(output_path).with_suffix(".pid").write_text(str(os.getpid()))
    Path(output_path).write_text("partial")
    time.sleep(120)
    raise AssertionError("should have been terminated")


def interrupted_then_convert(input_path, output_path, fmt, threads, progress=None, **options):
    """Get a Ctrl+C (SIGINT), as the whole terminal process group does, then convert normally."""
    os.kill(os.getpid(), signal.SIGINT)
    time.sleep(0.2)
    return convert(input_path, output_path, fmt, threads, progress, **options)
