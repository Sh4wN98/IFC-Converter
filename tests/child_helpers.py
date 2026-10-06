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


def report_skipped(input_path, output_path, fmt, threads, progress=None, **options):
    """Write a stand-in output and report 3 elements whose geometry could not be converted."""
    progress(0)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("fake")
    progress(100)
    return ConversionResult(output=Path(output_path), elements=1, skipped=3)


def _record_attempt(output_path, kernel):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(Path(output_path).with_suffix(".attempts"), "a") as attempts:
        attempts.write(f"{kernel}\n")


def segfault_unless_opencascade(input_path, output_path, fmt, threads, progress=None, kernel=None, **options):
    """Crash natively (SIGSEGV) like the hybrid kernel on some models; convert with OpenCASCADE."""
    _record_attempt(output_path, kernel)
    if kernel != "opencascade":
        progress(0)
        progress(40)
        os.kill(os.getpid(), signal.SIGSEGV)
    return convert(input_path, output_path, fmt, threads, progress, kernel=kernel, **options)


def always_segfault(input_path, output_path, fmt, threads, progress=None, kernel=None, **options):
    _record_attempt(output_path, kernel)
    os.kill(os.getpid(), signal.SIGSEGV)


def leave_glb_temp_files_and_segfault(input_path, output_path, fmt, threads, progress=None, **options):
    """Crash while the GLB serializer's temporary files exist, like a crash in the geometry kernel."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", ".indices.tmp", ".vertices.tmp"):
        Path(f"{output_path}{suffix}").write_text("partial")
    os.kill(os.getpid(), signal.SIGSEGV)


def chatty_native_code(input_path, output_path, fmt, threads, progress=None, **options):
    """Write to the C-level stdout like IfcOpenShell's kernels do for some shapes, then convert."""
    os.write(1, b"local z: 0.00298264,0.0126555,0.999915\n")
    print("python-level chatter")
    return convert(input_path, output_path, fmt, threads, progress, **options)
