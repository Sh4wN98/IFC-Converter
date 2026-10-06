"""Run convert() in a child process, so running out of memory or a native crash only ends that process.

On Linux the OOM killer SIGKILLs the process using the most memory, which for a multi-GB IFC file is
the one converting it. In a child process that is no longer the GUI, and a cancel can simply terminate
the child, even while IfcOpenShell is still reading the file (which cannot be interrupted otherwise).
"""

from __future__ import annotations

import multiprocessing
import os
import signal
import sys
from collections.abc import Callable
from multiprocessing.connection import wait
from pathlib import Path

from ifc_converter.converter import DEFAULT_KERNEL, ConversionResult, ProgressCallback, convert

# "spawn" starts a fresh interpreter on every platform: no forked copy of the GUI's threads and
# memory, and the same behaviour on Linux as on Windows and macOS (where it is the only/default way).
_CONTEXT = multiprocessing.get_context("spawn")

# How often the waiting thread checks for a cancel, in seconds.
POLL_INTERVAL = 0.1

MEMORY_MESSAGE = "Der Arbeitsspeicher hat nicht gereicht (Prozess wurde vom System beendet)"
# Shown when a crash in the hybrid geometry kernel is retried with OpenCASCADE.
RETRY_MESSAGE = "Absturz im schnellen Geometriekern – neuer Versuch mit dem langsameren OpenCASCADE-Kern …"
# Windows' STATUS_NO_MEMORY, the closest it has to being killed for lack of memory.
_STATUS_NO_MEMORY = 0xC0000017
# From <linux/prctl.h>.
_PR_SET_PDEATHSIG = 1


class Cancelled(Exception):
    """The conversion was cancelled; raised from a progress callback or by convert_in_child()."""


class ConversionFailed(Exception):
    """A Python exception in the child process, as its type name and text."""

    def __init__(self, type_name: str, text: str):
        super().__init__(text or type_name)
        self.type_name = type_name


class ConversionCrashed(Exception):
    """The child process died without a result (killed, or a native crash)."""

    def __init__(self, exitcode: int | None):
        super().__init__(crash_message(exitcode))
        self.exitcode = exitcode


def crash_message(exitcode: int | None) -> str:
    """A German message for a child that ended with ``exitcode`` but delivered no result."""
    if _out_of_memory(exitcode):
        return MEMORY_MESSAGE
    if exitcode == 0:
        return "Umwandlung wurde ohne Ergebnis beendet"
    # Windows reports crashes as NTSTATUS codes such as 0xC0000005, which are only readable in hex.
    code = f"0x{exitcode:08X}" if exitcode is not None and exitcode >= 0xC0000000 else exitcode
    return f"Umwandlung abgestürzt (Code {code})"


def _out_of_memory(exitcode: int | None) -> bool:
    return exitcode == -getattr(signal, "SIGKILL", 9) or exitcode == _STATUS_NO_MEMORY


def _retry_with_opencascade(exitcode: int | None, options: dict) -> bool:
    """Whether a child that ended with ``exitcode`` and no result crashed in the hybrid kernel.

    The hybrid kernel segfaults on some models that OpenCASCADE converts fine. Running out of memory
    is no such crash, and a kernel chosen explicitly (argument or IFC_CONVERTER_KERNEL) is kept.
    """
    kernel = options.get("kernel") or os.environ.get("IFC_CONVERTER_KERNEL") or DEFAULT_KERNEL
    return kernel.lower() == "hybrid" and exitcode not in (None, 0) and not _out_of_memory(exitcode)


def _die_with_parent(parent_pid: int) -> None:
    """Linux: have the kernel SIGKILL this process as soon as its parent dies; a no-op elsewhere.

    Otherwise a child whose GUI or terminal was killed would convert on as an orphan, holding gigabytes
    of memory. Strictly, the signal comes when the parent *thread* that started the child ends, but
    convert_in_child() does not return before the child is gone, so that thread outlives it.
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes

        ctypes.CDLL(None).prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
    except (OSError, AttributeError):
        return
    if os.getppid() != parent_pid:  # the parent died before prctl() took effect
        os._exit(1)


def _silence_stdout() -> None:
    """Send the child's stdout to the null device.

    IfcOpenShell's geometry kernels print debug output for some shapes straight to the C-level
    stdout (megabytes for some bridge models), which would flood the terminal of the CLI. The child
    reports everything through its pipe, so it never needs stdout.
    """
    try:
        sys.stdout.flush()
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.close(devnull)
    except (OSError, ValueError, AttributeError):  # no stdout at all, e.g. under pythonw
        pass


def _child_main(conn, func: Callable[..., ConversionResult], args: tuple, kwargs: dict, parent_pid: int) -> None:
    """Entry point of the child process: run ``func`` and send progress and the outcome to ``conn``."""
    _die_with_parent(parent_pid)
    # Ctrl+C in a terminal reaches the whole process group. The parent handles it and terminates the
    # child, which would otherwise print its own traceback.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _silence_stdout()

    def progress(percent: int) -> None:
        conn.send(("progress", percent))

    try:
        result = func(*args, progress=progress, **kwargs)
    except Exception as exc:  # exception objects may not unpickle in the parent, so send plain text
        conn.send(("error", type(exc).__name__, str(exc)))
    else:
        conn.send(("done", result))
    finally:
        conn.close()


def convert_in_child(
    input_path: str | Path,
    output_path: str | Path | None = None,
    fmt: str = "glb",
    threads: int | None = None,
    progress: ProgressCallback | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    func: Callable[..., ConversionResult] = convert,
    on_retry: Callable[[], None] | None = None,
    **options,
) -> ConversionResult:
    """Like convert(), but in a child process; blocks until it is done.

    ``progress`` is called in the calling thread and may raise (e.g. Cancelled) to abort. ``cancelled``
    is polled while waiting; once it returns True the child is terminated and Cancelled is raised.
    A Python exception in the child raises ConversionFailed, a child that dies without a result
    ConversionCrashed. ``func`` stands in for convert() and must be picklable, i.e. a top-level function.

    If the child crashes in the hybrid geometry kernel, the file is converted once more with
    kernel="opencascade"; ``on_retry`` is called before that, and progress starts again from reading.
    """
    args = (input_path, output_path, fmt, threads)
    try:
        return _run_child(func, args, options, progress, cancelled)
    except ConversionCrashed as crash:
        if not _retry_with_opencascade(crash.exitcode, options):
            raise
    if on_retry:
        on_retry()
    return _run_child(func, args, {**options, "kernel": "opencascade"}, progress, cancelled)


def _run_child(
    func: Callable[..., ConversionResult],
    args: tuple,
    options: dict,
    progress: ProgressCallback | None,
    cancelled: Callable[[], bool],
) -> ConversionResult:
    """One attempt of convert_in_child()."""
    reader, writer = _CONTEXT.Pipe(duplex=False)
    process = _CONTEXT.Process(
        target=_child_main,
        args=(writer, func, args, options, os.getpid()),
        name="ifc-convert",
        daemon=True,  # never outlive a normally exiting parent
    )
    outcome = None
    try:
        process.start()
        writer.close()  # the child has its own copy; ours would only hide the child's end of the pipe
        while outcome is None:
            if cancelled():
                raise Cancelled
            ready = wait([reader, process.sentinel], POLL_INTERVAL)
            if reader in ready:
                try:
                    message = reader.recv()
                except EOFError:  # the child is ending without a result
                    process.join(5)
                    break
                if message[0] == "progress":
                    if progress:
                        progress(message[1])
                else:
                    outcome = message
            elif process.sentinel in ready:
                # Anything the child sent before it ended is still in the pipe.
                while outcome is None and reader.poll():
                    try:
                        message = reader.recv()
                    except EOFError:
                        break
                    if message[0] != "progress":
                        outcome = message
                break
    finally:
        # A child that delivered its result is just exiting; a cancelled or failed one is stopped now.
        exitcode = _stop(process, grace=5 if outcome else 0)
        reader.close()

    if outcome is None:
        raise ConversionCrashed(exitcode)
    if outcome[0] == "error":
        raise ConversionFailed(outcome[1], outcome[2])
    return outcome[1]


def _stop(process, grace: float = 0) -> int | None:
    """Wait ``grace`` seconds for the child to end, then terminate it; returns its exit code.

    Returns only once the child is gone, so its output files are closed and can be deleted.
    """
    if process.pid is None:  # never started
        return None
    process.join(grace)
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
    process.join()
    exitcode = process.exitcode
    process.close()
    return exitcode
