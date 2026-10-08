"""Stand-ins for convert() that run in the conversion child process (so they must be importable)."""

import os
import signal
import sys
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


def report_priority(input_path, output_path, fmt, threads, progress=None, **options):
    """Write the child's scheduling priority into the output file: the Windows priority class, or the nice value."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetPriorityClass.argtypes = (ctypes.c_void_p,)
        value = kernel32.GetPriorityClass(kernel32.GetCurrentProcess())
    else:
        value = os.getpriority(os.PRIO_PROCESS, 0)
    Path(output_path).write_text(str(value))
    return ConversionResult(output=Path(output_path), elements=1)


def report_threads(input_path, output_path, fmt, threads, progress=None, **options):
    """Write the thread count the child was given into the output file."""
    Path(output_path).write_text(str(threads))
    return ConversionResult(output=Path(output_path), elements=1)


def write_to_stderr(input_path, output_path, fmt, threads, progress=None, **options):
    """Write to stderr from Python and from "native" code (the file descriptor), then succeed."""
    print("python warning on stderr", file=sys.stderr)
    os.write(2, b"native message on fd 2\n")
    Path(output_path).write_text("ok")
    return ConversionResult(output=Path(output_path), elements=1)


def isolate_user_dirs(monkeypatch, path):
    """Point the app's settings and log folders into ``path``, on every platform."""
    from ifc_converter import app

    monkeypatch.setattr(app, "config_dir", lambda: Path(path) / "config")
    monkeypatch.setattr(app, "log_dir", lambda: Path(path) / "logs")


def convert_counting_workers(input_path, output_path, fmt, threads, progress=None, **options):
    """Convert, and write the most worker processes the Rhino export had running to <output>.workers."""
    import concurrent.futures

    running = []

    class Pool(concurrent.futures.ProcessPoolExecutor):
        def submit(self, *args, **kwargs):
            future = super().submit(*args, **kwargs)
            running.append(len(self._processes))
            return future

    concurrent.futures.ProcessPoolExecutor = Pool
    result = convert(input_path, output_path, fmt, threads, progress, **options)
    Path(f"{output_path}.workers").write_text(str(max(running, default=0)))
    return result


def write_slowly(input_path, output_path, fmt, threads, progress=None, status=None, **options):
    """Enter the "write" phase and let the output grow for about two seconds, like rhino3dm's Write()."""
    progress(0)
    status("write", "Rhino-Datei wird geschrieben (1 Objekte) …")
    with open(output_path, "wb") as file:
        for _ in range(5):
            file.write(b"\0" * 1024 ** 2)
            file.flush()
            time.sleep(0.5)
    progress(100)
    return ConversionResult(output=Path(output_path), elements=1)


def stage_and_wait(input_path, output_path, fmt, threads, progress=None, status=None, staging_dir=None, **options):
    """Put a file into the staging folder, tell the test where it is, then wait to be cancelled."""
    (Path(staging_dir) / "staged.3dm").write_bytes(b"\0" * 1024)
    Path(f"{output_path}.staging").write_text(str(staging_dir))
    progress(0)
    time.sleep(120)


def wait_forever(input_path, output_path, fmt, threads, progress=None, **options):
    """Hang without using any CPU, like a kernel waiting for a worker thread that died."""
    progress(0)
    time.sleep(600)


def compute_for_a_while(input_path, output_path, fmt, threads, progress=None, **options):
    """Use CPU for about 3 seconds without reporting progress, like one slow element, then finish."""
    progress(0)
    end = time.monotonic() + 3
    while time.monotonic() < end:
        sum(range(10000))
    Path(output_path).write_text("done")
    progress(100)
    return ConversionResult(output=Path(output_path), elements=1)


def _fail_on_named(name, how):
    """Make the kernel hang (or crash) whenever it computes the product called ``name``."""
    from ifc_converter import converter

    def fail():
        if how == "crash":
            os.kill(os.getpid(), signal.SIGSEGV)
        time.sleep(600)

    iterate, deep_shape = converter._iterate, converter._deep_shape

    def failing_iterate(model, settings, threads, products, library):
        if any(product.Name == name for product in products):
            fail()
        yield from iterate(model, settings, threads, products, library)

    def failing_deep_shape(settings, product, strategy):
        if product.Name == name:
            fail()
        return deep_shape(settings, product, strategy)

    converter._iterate, converter._deep_shape = failing_iterate, failing_deep_shape


def hang_on_wall_7(input_path, output_path, fmt, threads, progress=None, **options):
    _fail_on_named("Wall 7", "hang")
    return convert(input_path, output_path, fmt, threads, progress, **options)


def crash_on_wall_7(input_path, output_path, fmt, threads, progress=None, **options):
    _fail_on_named("Wall 7", "crash")
    return convert(input_path, output_path, fmt, threads, progress, **options)
