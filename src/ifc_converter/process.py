"""Run convert() in a child process, so running out of memory or a native crash only ends that process.

On Linux the OOM killer SIGKILLs the process using the most memory, which for a multi-GB IFC file is
the one converting it. In a child process that is no longer the GUI, and a cancel can simply terminate
the child, even while IfcOpenShell is still reading the file (which cannot be interrupted otherwise).

The child runs at a lower priority, so the PC stays responsive while it uses all its cores, and what it
writes to stderr (warnings, tracebacks, a native crash's Python stack) ends up in the log file.
"""

from __future__ import annotations

import faulthandler
import json
import logging
import multiprocessing
import os
import signal
import sys
import shutil
import tempfile
import threading
import time
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from multiprocessing.connection import wait
from pathlib import Path

from ifc_converter import converter, i18n
from ifc_converter.converter import (
    DEFAULT_KERNEL, MAX_DEFAULT_THREADS, ConversionResult, ProgressCallback, convert, default_threads, size_text,
)
from ifc_converter.i18n import tr

# "spawn" starts a fresh interpreter on every platform: no forked copy of the GUI's threads and
# memory, and the same behaviour on Linux as on Windows and macOS (where it is the only/default way).
_CONTEXT = multiprocessing.get_context("spawn")

# How often the waiting thread checks for a cancel, in seconds.
POLL_INTERVAL = 0.1
# Seconds between "still running" lines in the log, so a long phase shows where the time goes.
HEARTBEAT = 60
# A conversion whose processes together use less than STALL_CPU seconds of CPU for STALL_TIMEOUT
# seconds is stuck (seen when a kernel thread died of a stack overflow and the others waited for it
# forever): it is ended and reported. Slow but working conversions keep using CPU. Sampled every
# CPU_SAMPLE seconds.
STALL_TIMEOUT = 10 * 60
# Once the child has reported a fatal error (faulthandler writes e.g. "Windows fatal exception:
# stack overflow" to its stderr), it is stuck for good as soon as it stops computing: this is how
# long it may then go without CPU. On Windows a stack overflow in a kernel thread leaves the
# process alive at 0 % CPU instead of ending it.
# SetThreadExecutionState flags.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
FATAL_STALL_TIMEOUT = 60
# Only the stack overflow: faulthandler also reports access violations that OpenCASCADE then handles.
# Marker in the child's stderr -> its name in messages (in the user's language when called).
FATAL_MARKERS = {"Windows fatal exception: stack overflow": lambda: tr("stack overflow")}
STALL_CPU = 1.0
CPU_SAMPLE = 30
# A child that reports no change (progress, phase, position) for this long while it keeps using CPU
# gets a warning in the log: a huge element may simply be slow.
NO_PROGRESS_WARNING = 30 * 60
# While the kernel computes (phases "envelope", "geometry", "deep") such a silence is a hang the
# child did not notice itself (it gives up a run that delivers nothing after converter.HANG_SECONDS
# and reports that; a kernel thread spinning where it cannot see it, e.g. in an iterator's start,
# keeps the CPU busy forever). After the pass's limit plus this margin the child is ended and the
# conversion restarted with the products not delivered yet isolated, as after a crash (see
# silence_limit, _recover). Elsewhere (reading, the hull's fill, writing) there is no such limit.
# MARGIN_ENV overrides the margin (seconds; tests, where it must reach the child as well).
NO_PROGRESS_MARGIN = 5 * 60
MARGIN_ENV = "IFC_CONVERTER_HANG_MARGIN"
# The child writes the Python stack of all its threads to its stderr (which the parent copies into
# the log when it ends it) this long before the parent's limit: where it is stuck, for the next
# version. faulthandler's own watchdog thread does that, because IfcOpenShell holds the interpreter
# lock while it computes: no Python thread of the child runs then (which is also why the child's own
# hang limits, converter.HANG_SECONDS, cannot act on the real kernel). The timer is re-armed with
# every message to the parent, at most every DUMP_REARM seconds.
DUMP_LEAD = 60
DUMP_REARM = 5
# A pause this long between two samples means the computer was suspended, not the conversion stuck.
SUSPEND_GAP = 5 * 60
# Temp files of conversions untouched for this long are leftovers of a killed app.
STALE_TEMP_AGE = 24 * 3600

# Windows: the conversion child and its worker processes run in a job object. They end with the app
# even if it is killed (KILL_ON_JOB_CLOSE), and together they may commit at most JOB_MEMORY_SHARE of
# the physical memory, so that a runaway conversion cannot push the PC's other programs into paging.
JOB_MEMORY_SHARE = 0.85
# A checkpoint (see checkpoint.py) is only kept with this many times the IFC size free in the
# temp folder: the kernel's geometry of a model takes about as much as the 3dm, 1–2x the IFC.
CHECKPOINT_ROOM = 3
# How many of the elements without geometry the log lists by name.
NO_GEOMETRY_LOG_LIMIT = 2000
# Recovery attempts after crashes or hangs in the kernel: computing the affected chunk one product at
# a time, then leaving out a product that still fails (each step needs a new attempt).
MAX_RECOVERIES = 6
# Windows' STATUS_NO_MEMORY, the closest it has to being killed for lack of memory.
_STATUS_NO_MEMORY = 0xC0000017
# From <linux/prctl.h>.
_PR_SET_PDEATHSIG = 1
# Windows priority class of the child: below other programs, above idle (from <winbase.h>).
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
# How much nicer than its parent the child runs on Linux and macOS (0 normal ... 19 lowest).
NICE_INCREMENT = 10
# At most this much of the child's stderr goes into the log (its end, where the errors are).
STDERR_LOG_LIMIT = 32_000
# Windows memory priority of the child (from <winbase.h>; normal is 5): when memory gets short, the
# pages of other programs are kept in RAM before those of the conversion.
MEMORY_PRIORITY_BELOW_NORMAL = 4
# Seconds to wait for a killed child to be gone before giving up on it.
KILL_WAIT = 10
# Elements the kernel crashed or hung on are remembered per file (name, size, modification time,
# kernel strategy, converter version) in QUARANTINE_NAME, so that converting the unchanged file again
# skips them at once instead of finding them anew, which takes a new attempt each. At most
# QUARANTINE_ELEMENTS per file, for the QUARANTINE_FILES files converted last.
QUARANTINE_NAME = "quarantine.json"
QUARANTINE_FILES = 50
QUARANTINE_ELEMENTS = 100

log = logging.getLogger(__name__)


def memory_message() -> str:
    """The error for a child killed for lack of memory (in the user's language)."""
    return tr("The memory was not enough (the process was ended by the system)")


def retry_message() -> str:
    """Shown when a crash in the hybrid geometry kernel is retried with OpenCASCADE alone."""
    return tr("Crash in the fast geometry kernel – retrying with OpenCASCADE only …")


# The two messages used to be module constants (MEMORY_MESSAGE, RETRY_MESSAGE); as such they could
# only be in one language. The names still work, in the language current when they are read.
_MESSAGES = {"MEMORY_MESSAGE": memory_message, "RETRY_MESSAGE": retry_message}


def __getattr__(name: str) -> str:
    if name in _MESSAGES:
        return _MESSAGES[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class Cancelled(Exception):
    """The conversion was cancelled; raised from a progress callback or by convert_in_child()."""


class ConversionFailed(Exception):
    """A Python exception in the child process, as its type name, text and traceback."""

    def __init__(self, type_name: str, text: str, details: str = ""):
        super().__init__(text or type_name)
        self.type_name = type_name
        self.details = details


class ConversionCrashed(Exception):
    """The child process died without a result (killed, or a native crash).

    ``memory_limit`` is set when the processes ran into the memory limit of their job object (Windows).
    """

    def __init__(self, exitcode: int | None, message: str = "", memory_limit: bool = False):
        super().__init__(message or crash_message(exitcode))
        self.exitcode = exitcode
        self.memory_limit = memory_limit


class ConversionStalled(Exception):
    """The child's processes stopped using CPU: they wait for something that never comes. Or, with
    ``silent``, they kept computing without reporting anything for longer than the kernel's hang limit.

    ``fatal`` is the fatal error the child reported before (e.g. "stack overflow"), if any.
    """

    def __init__(self, seconds: float, fatal: str = "", silent: bool = False):
        if fatal:
            super().__init__(tr("Crash in the geometry kernel ({fatal}), after which the conversion was stuck",
                                fatal=fatal))
        elif silent:
            super().__init__(tr("The conversion has made no progress for {duration} although it is computing (the "
                                "geometry kernel hangs)", duration=_duration(seconds)))
        else:
            super().__init__(tr("The conversion has not computed anything for {duration} (it was stuck)",
                                duration=_duration(seconds)))
        self.fatal = fatal
        self.silent = silent


def silence_limit(phase: str, fmt: str) -> float | None:
    """How long the child may compute in ``phase`` without reporting anything before it counts as
    hung (see NO_PROGRESS_MARGIN): the pass's hang limit (see converter.HANG_SECONDS) plus the margin
    while the kernel computes, None in the other phases."""
    if phase == "envelope":
        return converter.hang_limit("coarse") + _margin()
    if phase in ("geometry", "deep"):
        return converter.hang_limit("preview" if fmt == "preview" else "fine") + _margin()
    return None


def _margin() -> float:
    value = os.environ.get(MARGIN_ENV)
    if value:
        try:
            return float(value)
        except ValueError:
            pass
    return float(NO_PROGRESS_MARGIN)


def _duration(seconds: float) -> str:
    if seconds >= 120:
        return tr("{count} minutes", count=f"{seconds / 60:.0f}")
    return tr("{count} seconds", count=f"{seconds:.0f}")


def cpu_count() -> int:
    """Logical CPUs this process may use."""
    count = os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()
    return count or 1


def auto_threads() -> int:
    """The default number of geometry threads (see converter.default_threads)."""
    return default_threads()


# What the common Windows crash codes mean (in the user's language when called).
CRASH_NAMES = {
    0xC00000FD: lambda: tr("stack overflow in the geometry kernel"),
    0xC0000005: lambda: tr("memory access violation"),
    0xC0000409: lambda: tr("internal program abort"),
    -getattr(signal, "SIGSEGV", 11): lambda: tr("memory access violation"),
}


def crash_message(exitcode: int | None) -> str:
    """The message for a child that ended with ``exitcode`` but delivered no result."""
    if _out_of_memory(exitcode):
        return memory_message()
    if exitcode == 0:
        return tr("Conversion ended without a result")
    # Windows reports crashes as NTSTATUS codes such as 0xC0000005, which are only readable in hex.
    code = f"0x{exitcode:08X}" if exitcode is not None and exitcode >= 0xC0000000 else exitcode
    name = CRASH_NAMES.get(exitcode)
    if name:
        return tr("Conversion crashed: {name} (code {code})", name=name(), code=code)
    return tr("Conversion crashed (code {code})", code=code)


def _out_of_memory(exitcode: int | None) -> bool:
    return exitcode == -getattr(signal, "SIGKILL", 9) or exitcode == _STATUS_NO_MEMORY


def _retry_with_opencascade(exitcode: int | None, options: dict) -> bool:
    """Whether a child that ended with ``exitcode`` and no result may have crashed in the hybrid kernel.

    The hybrid kernel segfaults on some models that OpenCASCADE converts fine; the strategies
    "hybrid" and "accurate" (triangle meshes) use it. Running out of memory is no such crash.
    """
    return _uses_hybrid(options) and exitcode not in (None, 0) and not _out_of_memory(exitcode)


def _recover(
    failure: Exception, options: dict, isolate: set[int], skipped: dict[int, str], attempt: int = 2,
    opencascade_first: bool = False,
) -> str | None:
    """Plan attempt number ``attempt`` after a crash or hang; returns the message for it, or None to give up.

    ``failure.position`` is where the child was: ("chunk", ids, "") with the products not finished
    yet, ("element", [id], label), or ("curves", ids, labels one per line) for the Rhino export's
    alignment and grid axes, which are left out then. A crash with a strategy using the hybrid kernel
    is retried with OpenCASCADE alone only if it happened while the kernel computed products and
    nothing narrower is left to try; a crash while reading or writing would only come again. With
    ``opencascade_first`` a crash or hang in the kernel under such a strategy goes to OpenCASCADE at
    once, before narrowing it down.
    """
    if isinstance(failure, ConversionCrashed) and (failure.memory_limit or _out_of_memory(failure.exitcode)):
        return None
    if isinstance(failure, ConversionStalled) and failure.fatal:
        what = tr("Crash in the geometry kernel ({fatal})", fatal=failure.fatal)
    elif isinstance(failure, ConversionStalled):
        what = tr("Hang in the geometry kernel")
    else:
        what = tr("Crash in the geometry kernel")
    again = tr("New attempt ({attempt}. of at most {max})", attempt=attempt, max=MAX_RECOVERIES + 1)
    kind, ids, label = getattr(failure, "position", None) or (None, [], "")
    if opencascade_first and kind in ("chunk", "element") and _uses_hybrid(options):
        options["kernel"] = "opencascade"
        return retry_message()
    if getattr(failure, "phase", "") == "envelope" and kind == "chunk" and _uses_hybrid(options) \
            and options.get("hull_kernel") != "opencascade":
        # The hull's rough pre-computation runs everything through the hybrid kernel, which hangs or
        # crashes on some models (both seen on a 1.5 GB one): the pre-computation is done with
        # OpenCASCADE instead, before narrowing anything down (that would hang again, element by
        # element, with the hybrid kernel first). The conversion itself keeps its strategy.
        options["hull_kernel"] = "opencascade"
        return tr("{what} in the hull's rough pre-computation. {again} with OpenCASCADE for the pre-computation …",
                  what=what, again=again)
    # The messages are one sentence on the failure and one on the attempt (see convert_in_child).
    if kind == "curves" and ids and not set(ids) <= skipped.keys():
        labels = label.split("\n") if label else []
        for number, id_ in enumerate(ids):
            skipped[id_] = labels[number] if number < len(labels) else f"#{id_}"
        return tr("{what} at the axes (IfcAlignment, IfcGrid). {again} without the axes …", what=what, again=again)
    if kind == "element" and ids and ids[0] not in skipped:
        skipped[ids[0]] = label or f"#{ids[0]}"
        return tr("{what} at {label}. {again}, this element is skipped …", what=what, label=skipped[ids[0]],
                  again=again)
    if kind == "chunk" and ids and not set(ids) <= isolate:
        isolate.update(ids)
        if len(ids) == 1:
            return tr("{what} at one element. {again}, it is computed first and on its own …", what=what, again=again)
        return tr("{what} at one of {count} elements. {again}, these are computed first and on their own to find "
                  "the affected one …", what=what, count=len(ids), again=again)
    if kind in ("chunk", "element") and isinstance(failure, ConversionCrashed) \
            and _retry_with_opencascade(failure.exitcode, options) and options.get("kernel") != "opencascade":
        options["kernel"] = "opencascade"
        return retry_message()
    return None


def _uses_hybrid(options: dict) -> bool:
    """Whether the kernel strategy of ``options`` uses the hybrid kernel ("hybrid", "accurate")."""
    kernel = options.get("kernel") or os.environ.get("IFC_CONVERTER_KERNEL") or DEFAULT_KERNEL
    return kernel.lower() in ("accurate", "hybrid")


def _die_with_parent(parent_pid: int) -> None:
    """End this process as soon as its parent dies.

    Otherwise a child whose GUI or terminal was killed would convert on as an orphan, holding gigabytes
    of memory. Linux: the kernel SIGKILLs it (strictly, when the parent *thread* that started the child
    ends, but convert_in_child() does not return before the child is gone, so that thread outlives
    it). Elsewhere a thread waits for the parent to end.
    """
    if not sys.platform.startswith("linux"):
        threading.Thread(target=exit_with_parent, args=(parent_pid,), daemon=True, name="parent-watch").start()
        return
    try:
        import ctypes

        ctypes.CDLL(None).prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
    except (OSError, AttributeError):
        return
    if os.getppid() != parent_pid:  # the parent died before prctl() took effect
        os._exit(1)


def no_crash_dialogs() -> None:
    """Windows: let a crash end this process (and the processes it starts) at once.

    Otherwise Windows Error Reporting may keep the crashed process alive behind an "… has stopped
    working" dialog, and the conversion would hang instead of being reported as a crash.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX; inherited by children.
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    except (OSError, AttributeError):
        pass


def exit_with_parent(parent_pid: int) -> None:
    """Block until the process ``parent_pid`` has ended, then end this process (run it in a thread)."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
        kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        synchronize, infinite = 0x00100000, 0xFFFFFFFF
        handle = kernel32.OpenProcess(synchronize, False, parent_pid)
        if handle:  # else the parent is already gone
            kernel32.WaitForSingleObject(handle, infinite)
    else:
        while os.getppid() == parent_pid:
            time.sleep(0.5)
    os._exit(1)


def _redirect_fd(fd: int, path: str, flags: int) -> bool:
    """Point file descriptor ``fd`` (1 or 2) at ``path``, also for native code that uses the Win32 handle."""
    try:
        target = os.open(path, flags)
        os.dup2(target, fd)
        os.close(target)
    except OSError:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            import msvcrt

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.SetStdHandle.argtypes = (ctypes.c_ulong, ctypes.c_void_p)
            std_handle = {1: -11, 2: -12}[fd] & 0xFFFFFFFF  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            kernel32.SetStdHandle(std_handle, msvcrt.get_osfhandle(fd))
        except (OSError, AttributeError, ValueError):
            pass
    return True


def _silence_stdout() -> None:
    """Send the child's stdout to the null device.

    IfcOpenShell's geometry kernels print debug output for some shapes straight to the C-level
    stdout (megabytes for some bridge models), which would flood the terminal of the CLI. The child
    reports everything through its pipe, so it never needs stdout.
    """
    try:
        sys.stdout.flush()
    except (OSError, ValueError, AttributeError):  # no stdout at all, e.g. under pythonw
        pass
    _redirect_fd(1, os.devnull, os.O_WRONLY)


def _redirect_stderr(path: str | None) -> None:
    """Send the child's stderr to ``path``, a file the parent copies into the log afterwards.

    A windowed app (pythonw) has no stderr at all, and a terminal would mix it into the progress line.
    A native crash's Python stack goes there too (faulthandler).
    """
    if not path or not _redirect_fd(2, path, os.O_WRONLY | os.O_APPEND):
        return
    try:
        sys.stderr = open(2, "w", encoding="utf-8", errors="backslashreplace", buffering=1, closefd=False)  # noqa: SIM115
        faulthandler.enable(file=sys.stderr)
    except (OSError, ValueError, RuntimeError):
        pass


@contextmanager
def keep_awake() -> Iterator[None]:
    """Keep Windows from going to standby (by its idle timer) while a conversion runs.

    Heavy CPU use does not count as activity there, so a conversion of an hour was suspended
    midway. The screen may still turn off and lock. The setting belongs to the calling thread.
    """
    if sys.platform != "win32":
        yield
        return
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)


def lower_priority() -> None:
    """Run the calling process (and the processes it starts) below normal priority.

    At a lower priority, Rhino, Revit or Outlook still get the CPU first, so the PC stays responsive
    and the conversion uses the time they leave over. On Windows its memory priority is lowered too
    (see MEMORY_PRIORITY_BELOW_NORMAL).
    """
    try:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
            kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
            lower_memory_priority()
        else:
            os.nice(NICE_INCREMENT)
    except (OSError, AttributeError):
        pass


def lower_memory_priority() -> None:
    """Windows 8 and later: give the calling process's memory pages below-normal priority."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetProcessInformation.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong)
        priority = ctypes.c_ulong(MEMORY_PRIORITY_BELOW_NORMAL)
        process_memory_priority = 0  # PROCESS_INFORMATION_CLASS
        kernel32.SetProcessInformation(
            kernel32.GetCurrentProcess(), process_memory_priority, ctypes.byref(priority), ctypes.sizeof(priority),
        )
    except (OSError, AttributeError):  # before Windows 8
        pass


def _child_main(
    conn,
    func: Callable[..., ConversionResult],
    args: tuple,
    kwargs: dict,
    parent_pid: int,
    stderr_path: str | None = None,
    low_priority: bool = True,
) -> None:
    """Entry point of the child process: run ``func`` and send progress and the outcome to ``conn``."""
    # The parent's language (handed down in the environment): status texts, notes and error
    # messages are made here and shown there as they are.
    i18n.set_language(i18n.language_from_environment())
    _die_with_parent(parent_pid)
    no_crash_dialogs()
    _redirect_stderr(stderr_path)
    if low_priority:
        lower_priority()
    # Ctrl+C in a terminal reaches the whole process group. The parent handles it and terminates the
    # child, which would otherwise print its own traceback.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _silence_stdout()
    lock = threading.Lock()  # the geometry runs report from threads of their own
    fmt = args[2] if len(args) > 2 else ""
    state = {"phase": "", "armed": 0.0, "armed_phase": None}  # of the thread dump, see _arm_dump

    def send(message: tuple, activity: bool = True) -> None:
        with lock:
            conn.send(message)
            if activity:  # like the parent sees it: a note is no progress
                _arm_dump(state, fmt)

    def progress(percent: int) -> None:
        send(("progress", percent))

    def status(phase: str, text: str) -> None:
        if phase != "note":
            state["phase"] = phase
        send(("status", phase, text), activity=phase != "note")

    def position(kind: str, ids: list, label: str) -> None:
        send(("position", kind, ids, label))

    try:
        result = func(*args, progress=progress, status=status, position=position, **kwargs)
    except Exception as exc:  # exception objects may not unpickle in the parent, so send plain text
        send(("error", type(exc).__name__, str(exc), traceback.format_exc()))
    else:
        send(("done", result))
    finally:
        with lock:
            conn.close()
        faulthandler.cancel_dump_traceback_later()
        if converter.abandoned():
            _exit_at_once()


def _arm_dump(state: dict, fmt: str) -> None:
    """(Re)start the child's thread dump timer (see DUMP_LEAD): the stacks of all its threads go to
    stderr once it has reported nothing for the phase's silence limit less DUMP_LEAD. No timer in
    phases without a limit. Called with every message to the parent, so the timer is re-armed at most
    every DUMP_REARM seconds (cancelling joins faulthandler's thread) and right away in a new phase."""
    now = time.monotonic()
    limit = silence_limit(state["phase"], fmt)
    if limit is None:
        if state["armed_phase"] is not None:
            faulthandler.cancel_dump_traceback_later()
            state["armed_phase"] = None
        return
    if state["armed_phase"] == state["phase"] and now - state["armed"] < DUMP_REARM:
        return
    try:
        faulthandler.dump_traceback_later(max(0.1, limit - min(DUMP_LEAD, limit / 2)), repeat=False, file=sys.stderr)
    except (OSError, ValueError, AttributeError, RuntimeError):  # no usable stderr (e.g. pythonw without the file)
        return
    state["armed"], state["armed_phase"] = now, state["phase"]


def _exit_at_once() -> None:
    """End the child right now, skipping the interpreter's shutdown: a computation that hung was
    abandoned (see converter.abandoned) and its kernel thread cannot be stopped.

    The outcome is sent and the pipe closed by now, output files are written. A normal exit would
    wait forever: the interpreter frees the modules, with them (unless kept, see
    converter._keep_forever) IfcOpenShell's iterator, whose destructor joins its threads. os._exit
    ends the process with all its threads at once (Linux: exit_group; Windows: ExitProcess, which
    first ends the other threads). On Windows, TerminateProcess on ourselves is used instead, which
    also skips the DLLs' detach routines: with a thread ended in the middle of the kernel, a static
    destructor there could wait for a lock that thread held. Either way the parent sees the exit
    code 0, and would terminate a child still alive after 5 s anyway (see _stop).
    """
    for stream in (sys.stderr, sys.stdout):
        try:
            stream.flush()
        except (OSError, ValueError, AttributeError):
            pass
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint)
            kernel32.TerminateProcess(kernel32.GetCurrentProcess(), 0)
        except (OSError, AttributeError):
            pass
    os._exit(0)


def convert_in_child(
    input_path: str | Path,
    output_path: str | Path | None = None,
    fmt: str = "glb",
    threads: int | None = None,
    progress: ProgressCallback | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    func: Callable[..., ConversionResult] = convert,
    on_retry: Callable[[str], None] | None = None,
    low_priority: bool = True,
    status: Callable[[str, str], None] | None = None,
    opencascade_first: bool = False,
    **options,
) -> ConversionResult:
    """Like convert(), but in a child process; blocks until it is done.

    ``progress`` is called in the calling thread and may raise (e.g. Cancelled) to abort. ``cancelled``
    is polled while waiting; once it returns True the child is terminated and Cancelled is raised.
    A Python exception in the child raises ConversionFailed, a child that dies without a result
    ConversionCrashed. ``func`` stands in for convert() and must be picklable, i.e. a top-level function.

    If the child crashes or hangs (no CPU activity for STALL_TIMEOUT), the file is converted again:
    the products of the chunk where it happened one by one (in a thread with a large stack), then
    without a single product that still fails, which is then reported as skipped; a crash with a
    strategy that uses the hybrid kernel, where no chunk was running, is retried with OpenCASCADE.
    ``on_retry`` gets a message (in the user's language) before each new attempt, and progress starts again
    from reading.
    With ``opencascade_first`` (the preview) a crash or hang in the hybrid kernel is retried with
    OpenCASCADE right away: where the hybrid kernel crashes on one element of a model it often does on
    many alike (all beams of a bridge), and each step of narrowing it down reads the file again.

    ``threads`` defaults to auto_threads(); ``low_priority`` runs the child below normal priority.
    ``status`` gets the current phase ("read", "geometry", "write", "copy") and a description
    (while writing with the size written so far). Start, phases, a heartbeat every minute, outcome and
    duration of the conversion are logged.
    """
    threads = threads or auto_threads()
    args = (input_path, output_path, fmt, threads)
    log.info(tr(
        "Conversion: {input} ({size}) -> {output}, format {fmt}, {threads} threads{options}{priority}",
        input=input_path, size=_size_text(input_path), output=output_path or tr("(next to the IFC file)"), fmt=fmt,
        threads=threads, options="".join(f", {k}={v}" for k, v in options.items()),
        priority="" if low_priority else tr(", normal priority"),
    ))
    started = time.monotonic()
    isolate: set[int] = set()
    kernel = (options.get("kernel") or os.environ.get("IFC_CONVERTER_KERNEL") or DEFAULT_KERNEL).lower()
    quarantine = _quarantine_key(input_path, kernel)
    skipped = load_quarantine(quarantine)
    if skipped:
        log.warning(tr("Known from earlier conversions of this file, skipped (the geometry kernel crashed on it or "
                       "hung) ({count}):\n  {elements}", count=len(skipped), elements="\n  ".join(skipped.values())))
    checkpoint = _checkpoint_dir(input_path) if fmt == "3dm" else None
    try:
        with keep_awake():
            for attempt in range(MAX_RECOVERIES + 1):
                attempt_options = dict(options)
                if isolate:
                    attempt_options["isolate_ids"] = sorted(isolate)
                if skipped:
                    attempt_options["skip_ids"] = sorted(skipped)
                if checkpoint:
                    attempt_options["checkpoint_dir"] = checkpoint
                hung: dict[int, str] = {}  # elements the child gave up as hung in this attempt
                try:
                    result = _run_child(func, args, attempt_options, progress, cancelled, low_priority, status, started,
                                        hung)
                    break
                except (ConversionCrashed, ConversionStalled) as failure:
                    known = len(skipped)
                    skipped.update(hung)  # skipped at once in the next attempt, like crashed ones
                    kernel_before = options.get("kernel")
                    message = _recover(failure, options, isolate, skipped, attempt + 2, opencascade_first)
                    if len(skipped) > known:
                        save_quarantine(quarantine, skipped)
                    if message is None or attempt == MAX_RECOVERIES:
                        raise
                    if checkpoint and options.get("kernel") != kernel_before:
                        _clear(checkpoint)  # computed with the other kernel: everything again
                    elif checkpoint and any(Path(checkpoint).glob("chunk-*.bin")):
                        message = message.removesuffix(" …") + tr(", already computed elements are taken over …")
                    code = tr(" (exit code {code})", code=failure.exitcode) if isinstance(failure, ConversionCrashed) \
                        else ""
                    log.warning("%s%s. %s", failure, code, message.split(". ", 1)[-1])
                    if on_retry:
                        on_retry(message)
            # The child reports the elements it gave up as hung in result.crashed as well: one list.
            skipped.update(hung)
            labels = list(skipped.values())
            result.crashed = labels + [label for label in result.crashed if label not in set(labels)]
            if skipped:  # remembered as used recently
                save_quarantine(quarantine, skipped)
    except Cancelled:
        log.info(tr("Cancelled after {seconds} s: {path}", seconds=_seconds(started), path=input_path))
        raise
    except ConversionFailed as exc:
        log.error(tr("Error after {seconds} s at {path}: {type}: {error}\n{details}", seconds=_seconds(started),
                     path=input_path, type=exc.type_name, error=exc, details=exc.details.rstrip()))
        raise
    except ConversionCrashed as exc:
        log.error(tr("Crash after {seconds} s at {path}: {error} (exit code {code})", seconds=_seconds(started),
                     path=input_path, error=exc, code=exc.exitcode))
        raise
    except ConversionStalled:
        log.error(tr("Stuck, cancelled after {seconds} s: {path}", seconds=_seconds(started), path=input_path))
        raise
    except Exception:
        log.exception(tr("Conversion of {path} failed", path=input_path))
        raise
    finally:
        if checkpoint:
            shutil.rmtree(checkpoint, ignore_errors=True)
    log.info(tr("Finished after {seconds} s: {input} -> {output}, {elements} elements, {missing} without geometry, "
                "{skipped} skipped", seconds=_seconds(started), input=input_path, output=result.output,
                elements=result.elements, missing=result.skipped, skipped=len(result.crashed)))
    if result.crashed:
        log.warning(tr("Skipped because the geometry kernel crashed on them or hung ({count}):\n  {elements}",
                       count=len(result.crashed), elements="\n  ".join(result.crashed)))
    if result.no_geometry:
        shown = result.no_geometry[:NO_GEOMETRY_LOG_LIMIT]
        more = len(result.no_geometry) - len(shown)
        log.info(tr("Without geometry ({count}):\n  {elements}{more}", count=len(result.no_geometry),
                    elements="\n  ".join(shown), more=tr("\n  … and {count} more", count=more) if more else ""))
    return result


def _seconds(started: float) -> str:
    """The time since ``started`` for the log, e.g. "12.3"."""
    return f"{time.monotonic() - started:.1f}"


def _checkpoint_dir(input_path: str | Path) -> str | None:
    """A new folder in the local temp folder for the checkpoint of a 3dm conversion, or None if
    there is not CHECKPOINT_ROOM times the IFC size free there (then a restart computes everything)."""
    try:
        base = tempfile.gettempdir()
        if shutil.disk_usage(base).free < CHECKPOINT_ROOM * os.path.getsize(input_path) + 1024 ** 3:
            log.info(tr("Too little room in the temp folder for a checkpoint; after a crash everything is computed "
                        "again"))
            return None
        return tempfile.mkdtemp(prefix="ifc-converter-checkpoint-")
    except OSError:
        return None


def _clear(folder: str) -> None:
    for path in Path(folder).iterdir():
        try:
            path.unlink()
        except OSError:
            pass


def _size_text(path: str | Path) -> str:
    try:
        return f"{os.path.getsize(path) / 1024 ** 2:.1f} MB"
    except OSError:
        return tr("size unknown")


def _run_child(
    func: Callable[..., ConversionResult],
    args: tuple,
    options: dict,
    progress: ProgressCallback | None,
    cancelled: Callable[[], bool],
    low_priority: bool = True,
    status: Callable[[str, str], None] | None = None,
    started: float | None = None,
    hung: dict[int, str] | None = None,
) -> ConversionResult:
    """One attempt of convert_in_child(); ``hung`` collects the elements the child gave up as hung
    ({step id: label}), whether the attempt ends with a result or not."""
    job = _Job.create(low_priority)
    stderr_path = _stderr_file()
    staging = _staging_dir()
    watch = _Phases(args[1] or Path(args[0]).with_suffix(f".{args[2]}"), staging, status, started, fmt=args[2])
    watch.stderr_path = stderr_path
    reader, writer = _CONTEXT.Pipe(duplex=False)
    process = _CONTEXT.Process(
        target=_child_main,
        args=(writer, func, args, {**options, "staging_dir": staging}, os.getpid(), stderr_path, low_priority),
        name="ifc-convert",
        # Not a daemon: daemonic processes may not start processes, and the child starts the worker
        # processes of a large Rhino export. _die_with_parent() ends it with its parent instead.
        daemon=False,
    )
    outcome = None
    memory_limit = False
    try:
        process.start()
        if job:
            # The child starts its worker processes later, which then belong to the job as well.
            job.assign(process.sentinel)  # on Windows the process handle
        watch.pid = process.pid
        writer.close()  # the child has its own copy; ours would only hide the child's end of the pipe
        while outcome is None:
            if cancelled():
                raise Cancelled
            ready = wait([reader, process.sentinel], POLL_INTERVAL)
            watch.tick()
            if reader in ready:
                try:
                    message = reader.recv()
                except (EOFError, OSError):  # the child is ending without a result (Windows: a broken pipe)
                    process.join(5)
                    break
                if message[0] == "progress":
                    watch.percent = message[1]
                    if progress:
                        progress(message[1])
                elif message[0] == "status":
                    watch.enter(message[1], message[2])
                elif message[0] == "position":
                    watch.locate(*message[1:])
                else:
                    outcome = message
            elif process.sentinel in ready:
                # Anything the child sent before it ended is still in the pipe.
                try:
                    while outcome is None and reader.poll():
                        message = reader.recv()
                        if message[0] == "position":
                            watch.locate(*message[1:])
                        elif message[0] not in ("progress", "status"):
                            outcome = message
                except (EOFError, OSError):  # the end of the pipe (Windows: a broken pipe)
                    pass
                break
    finally:
        if hung is not None:
            hung.update(watch.hung)
        # A child that delivered its result is just exiting; a cancelled or failed one is stopped now.
        exitcode = _stop(process, grace=5 if outcome else 0)
        reader.close()
        _log_stderr(stderr_path, failed=outcome is None or outcome[0] == "error")
        if staging:
            shutil.rmtree(staging, ignore_errors=True)
        if job:
            memory_limit = job.memory_limit_hit()
            job.close()  # ends worker processes that outlived the child

    if memory_limit and (outcome is None or outcome[0] == "error"):
        # Allocations failed: as a crash in native code, or as a MemoryError in Python.
        log.error(tr("Memory limit of the conversion process ({limit} GB) reached", limit=_gb(job.limit)))
        raise ConversionCrashed(exitcode, _memory_limit_message(job.limit), memory_limit=True)
    if memory_limit:
        log.warning(tr("Memory limit of the conversion process ({limit} GB) reached, the conversion still ran to the "
                       "end (e.g. without worker processes)", limit=_gb(job.limit)))
    if outcome is None:
        crash = ConversionCrashed(exitcode)
        crash.position, crash.phase = watch.suspects(), watch.phase
        raise crash
    if outcome[0] == "error":
        raise ConversionFailed(*outcome[1:])
    return outcome[1]


def _gb(size: int) -> str:
    return f"{size / 1024 ** 3:.1f}".replace(".", ",")


def _memory_limit_message(limit: int) -> str:
    return tr("The memory was not enough: The conversion may use at most {limit} GB ({share} % of the memory), so "
              "that other programs keep running. For this file the PC needs more memory.",
              limit=_gb(limit), share=round(JOB_MEMORY_SHARE * 100))


def job_memory_limit() -> int | None:
    """The memory the conversion processes may commit together: JOB_MEMORY_SHARE of the physical memory."""
    total = total_memory()
    return int(total * JOB_MEMORY_SHARE) if total else None


def total_memory() -> int | None:
    """Physical memory in bytes (Windows only, else None)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus(dwLength=ctypes.sizeof(MemoryStatus))
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return status.ullTotalPhys
    except (OSError, AttributeError):
        return None


class _Job:
    """A Windows job object for the conversion child and the worker processes it starts.

    Closing it (or the app ending) kills them all; their memory together is capped at ``limit``,
    and a process that tries to go beyond it is reported through a completion port.
    """

    # From <winnt.h>.
    LIMIT_PRIORITY_CLASS = 0x20
    LIMIT_JOB_MEMORY = 0x200
    LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    EXTENDED_LIMIT_INFORMATION = 9
    ASSOCIATE_COMPLETION_PORT_INFORMATION = 7
    MSG_JOB_MEMORY_LIMIT = 10

    def __init__(self, kernel32, handle, port, limit: int):
        self._kernel32, self._handle, self._port = kernel32, handle, port
        self.limit = limit
        self._hit = False

    @classmethod
    def create(cls, low_priority: bool = True) -> _Job | None:
        """A new job with the limits, or None (not Windows, or the job could not be set up: logged)."""
        if sys.platform != "win32":
            return None
        limit = job_memory_limit()
        if not limit:
            return None
        try:
            return cls._create(limit, low_priority)
        except (OSError, AttributeError) as exc:
            log.warning(tr("Job object for the conversion not available ({error}), continuing without a memory limit",
                           error=exc))
            return None

    @classmethod
    def _create(cls, limit: int, low_priority: bool) -> _Job:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.CreateIoCompletionPort.restype = wintypes.HANDLE
        kernel32.CreateIoCompletionPort.argtypes = (wintypes.HANDLE, wintypes.HANDLE, ctypes.c_size_t, wintypes.DWORD)
        kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.GetQueuedCompletionStatus.argtypes = (
            wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD,
        )
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        job = cls(kernel32, handle, None, limit)
        try:
            info = _ExtendedLimitInformation()
            info.BasicLimitInformation.LimitFlags = cls.LIMIT_KILL_ON_JOB_CLOSE | cls.LIMIT_JOB_MEMORY
            if low_priority:  # also for processes started by the child, whatever they ask for
                info.BasicLimitInformation.LimitFlags |= cls.LIMIT_PRIORITY_CLASS
                info.BasicLimitInformation.PriorityClass = BELOW_NORMAL_PRIORITY_CLASS
            info.JobMemoryLimit = limit
            if not kernel32.SetInformationJobObject(
                handle, cls.EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            invalid_handle = wintypes.HANDLE(-1).value
            job._port = kernel32.CreateIoCompletionPort(invalid_handle, None, 0, 1)
            if job._port:
                port = _CompletionPort(CompletionKey=None, CompletionPort=job._port)
                kernel32.SetInformationJobObject(
                    handle, cls.ASSOCIATE_COMPLETION_PORT_INFORMATION, ctypes.byref(port), ctypes.sizeof(port),
                )
        except BaseException:
            job.close()
            raise
        return job

    def assign(self, process_handle: int) -> bool:
        """Put the process into the job; if that fails (logged), it runs without the job's limits."""
        import ctypes

        if self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            return True
        log.warning(tr("Conversion process not in the job object ({error}), continuing without a memory limit",
                       error=ctypes.WinError(ctypes.get_last_error())))
        return False

    def memory_limit_hit(self) -> bool:
        """Whether a process of the job tried to commit more than ``limit`` (so far)."""
        import ctypes
        from ctypes import wintypes

        while self._port and not self._hit:
            message, key, overlapped = wintypes.DWORD(), ctypes.c_size_t(), ctypes.c_void_p()
            if not self._kernel32.GetQueuedCompletionStatus(
                self._port, ctypes.byref(message), ctypes.byref(key), ctypes.byref(overlapped), 0,
            ):
                break  # no more messages
            self._hit = message.value == self.MSG_JOB_MEMORY_LIMIT
        return self._hit

    def close(self) -> None:
        """Close the job: processes still in it are killed."""
        for handle in (self._handle, self._port):
            if handle:
                self._kernel32.CloseHandle(handle)
        self._handle = self._port = None


def _job_structures():
    import ctypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation), ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class CompletionPort(ctypes.Structure):
        _fields_ = [("CompletionKey", ctypes.c_void_p), ("CompletionPort", ctypes.c_void_p)]

    return ExtendedLimitInformation, CompletionPort


_ExtendedLimitInformation, _CompletionPort = _job_structures()


def quarantine_path() -> Path:
    """The file remembering the elements that crashed or hung the kernel (see QUARANTINE_NAME)."""
    from ifc_converter.app import log_dir

    return log_dir().parent / QUARANTINE_NAME


def _quarantine_key(input_path: str | Path, kernel: str) -> str | None:
    """What identifies an unchanged file and the way it is converted, or None if it cannot be read.

    The version of IfcOpenShell (the geometry kernel) belongs to it, not the converter's: an update
    of the converter alone does not make the kernel get past these elements.
    """
    import ifcopenshell

    try:
        stat = os.stat(input_path)
    except OSError:
        return None
    return f"{Path(input_path).name}|{stat.st_size}|{stat.st_mtime_ns}|{kernel}|ifcopenshell {ifcopenshell.version}"


def _read_quarantine() -> dict:
    try:
        with open(quarantine_path(), encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):  # missing, unreadable or corrupt: start afresh
        return {}
    return data if isinstance(data, dict) else {}


def load_quarantine(key: str | None) -> dict[int, str]:
    """The remembered elements of the file with ``key``, as {step id: label}."""
    if not key:
        return {}
    entry = _read_quarantine().get(key)
    elements = entry.get("elements") if isinstance(entry, dict) else None
    if not isinstance(elements, dict):
        return {}
    known = {}
    for id_, label in list(elements.items())[:QUARANTINE_ELEMENTS]:
        if isinstance(id_, str) and id_.isdigit() and isinstance(label, str):
            known[int(id_)] = label
    return known


def save_quarantine(key: str | None, elements: dict[int, str]) -> None:
    """Remember ``elements`` ({step id: label}) for the file with ``key``; errors are only logged."""
    if not key:
        return
    data = {name: entry for name, entry in _read_quarantine().items() if isinstance(entry, dict)}
    data.pop(key, None)
    data[key] = {
        "elements": {str(id_): label for id_, label in list(elements.items())[:QUARANTINE_ELEMENTS]},
        "used": time.time(),
    }
    def used(name: str) -> float:
        value = data[name].get("used")
        return value if isinstance(value, (int, float)) else 0.0

    for name in sorted(data, key=used)[:-QUARANTINE_FILES]:
        del data[name]
    path = quarantine_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        part.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(part, path)
    except OSError as exc:
        log.warning(tr("Skipped elements could not be saved ({path}): {error}", path=path, error=exc))


def _staging_dir() -> str | None:
    """A new temp folder in which the child stages output for a network folder (see converter)."""
    try:
        return tempfile.mkdtemp(prefix="ifc-converter-")
    except OSError:
        return None


class _Phases:
    """Follows the child's phases: passes them on, logs them, and measures the file being written.

    rhino3dm holds the child's interpreter lock while it writes a 3dm, so the child cannot report
    on that itself; the size of the growing file shows that it is not stuck.
    """

    def __init__(self, output: Path, staging: str | None, status, started: float | None, fmt: str = ""):
        self.output = Path(output)
        self.staging = Path(staging) if staging else None
        self.status = status
        self.fmt = fmt
        self.started = started or time.monotonic()
        self.phase = self.text = ""
        self.percent = 0
        self._shown = self._logged = time.monotonic()
        self.pid: int | None = None
        self.position: tuple | None = None  # where the child is: ("chunk"|"element", ids, label)
        self._remaining: set[int] | None = None  # products of the chunk not delivered yet
        self.hung: dict[int, str] = {}  # products the child gave up as hung: {step id: label}
        self._changed = time.monotonic()  # when progress, phase or position last changed
        self._seen_percent = 0
        self.stderr_path: str | None = None
        self.fatal = ""  # the first fatal error found in the child's stderr
        self._stderr_read = 0
        self._sampled = self._active = time.monotonic()
        self._active_cpu: float | None = None

    def enter(self, phase: str, text: str) -> None:
        if phase == "note":  # something for the log only
            log.warning("%s", text)
            return
        if phase in ("write", "copy"):  # a crash from here on is not in the kernel
            self.locate("done", [], "")
        if phase != self.phase:
            log.info(tr("{message} (after {seconds} s)", message=text,
                        seconds=f"{time.monotonic() - self.started:.0f}"))
        if (phase, text) != (self.phase, self.text):
            self._changed = time.monotonic()
        self.phase, self.text = phase, text
        self._show(text)

    def locate(self, kind: str, ids: list, label: str) -> None:
        """Where the child is: computing a "chunk" of products or one "element", or "done"; or which
        products of the chunk it has "delivered"; or which product it gave up as "hung" (skipped
        like one the kernel crashed on; the position stays)."""
        self._changed = time.monotonic()
        if kind == "delivered":
            if self._remaining is not None:
                self._remaining.difference_update(ids)
            return
        if kind == "hung":
            for id_ in ids:
                self.hung[id_] = label or f"#{id_}"
            if self._remaining is not None:
                self._remaining.difference_update(ids)
            return
        self.position = (kind, ids, label)
        self._remaining = set(ids) if kind == "chunk" else None

    def suspects(self) -> tuple | None:
        """The position for recovery: of a chunk only the products not delivered yet (all of them if
        it got past every one, e.g. when the crash came after the kernel)."""
        if self.position and self.position[0] == "chunk" and self._remaining:
            return ("chunk", sorted(self._remaining), "")
        return self.position

    def tick(self) -> None:
        now = time.monotonic()
        if self.percent != self._seen_percent:
            self._seen_percent, self._changed = self.percent, now
        if self.pid and now - self._sampled >= CPU_SAMPLE:
            if now - self._sampled > SUSPEND_GAP:
                # The computer was asleep (this loop runs every second): no reason to stop the child,
                # and the sleep is no silence of it either.
                self._active, self._active_cpu, self._changed = now, None, now
            self._sampled = now
            self._check_stall(now)
        if now - self._logged >= HEARTBEAT:
            self._logged = now
            log.info(tr("Running for {seconds} s, {percent} %: {message}", seconds=f"{now - self.started:.0f}",
                        percent=self.percent, message=self.text or "…"))
        if self.phase == "write" and now - self._shown >= 1:
            self._show(tr("{message}: {size} written …", message=self.text.removesuffix(" …"),
                          size=size_text(self._written())))

    def _check_stall(self, now: float) -> None:
        if self.phase == "copy":  # copying to a slow network folder needs hardly any CPU
            self._active, self._active_cpu = now, None
            return
        cpu = tree_cpu_seconds(self.pid)
        if cpu is None:  # not measurable here: no watchdog
            return
        if not self.fatal:
            self._find_fatal()
        timeout = FATAL_STALL_TIMEOUT if self.fatal else STALL_TIMEOUT
        if self._active_cpu is None or cpu - self._active_cpu >= STALL_CPU:
            self._active, self._active_cpu = now, cpu
            silence = now - self._changed
            # Only while the kernel is at products: the child reports every chunk and single element
            # before computing it, and "done" after the last; the scans and set-up around them
            # (nesting depths, Rhino blocks, the pool's drain) are plain Python and may take long.
            limit = silence_limit(self.phase, self.fmt) if self.position and self.position[0] in ("chunk", "element") \
                else None
            if limit is not None and silence >= limit:
                # Computing, but nothing to show for it for longer than the kernel's hang limit, after
                # which the child would have reported a hang it noticed: it hangs where it cannot
                # notice, and is ended and restarted with the products not finished yet isolated.
                log.error(tr("No progress for {minutes} min although the conversion is computing (CPU {cpu} s), "
                             "{percent} %: {message} – the geometry kernel hangs, the conversion is restarted",
                             minutes=f"{silence / 60:.0f}", cpu=f"{cpu:.1f}", percent=self.percent,
                             message=self.text or "…"))
                stalled = ConversionStalled(silence, silent=True)
                stalled.position, stalled.phase = self.suspects(), self.phase
                raise stalled
            if silence >= NO_PROGRESS_WARNING:
                # A huge element may simply be slow (no limit in this phase). Warned once per silence.
                self._changed = now
                log.warning(tr("No progress for {minutes} min although the conversion is computing (CPU {cpu} s), "
                               "{percent} %: {message}", minutes=f"{silence / 60:.0f}", cpu=f"{cpu:.1f}",
                               percent=self.percent, message=self.text or "…"))
        elif cpu < self._active_cpu:
            # The tree's CPU time dropped: worker processes exited (the Rhino pool after the geometry).
            # That is a new reference, not activity; the child earns STALL_CPU from here on.
            self._active_cpu = cpu
        elif now - self._active >= timeout:
            log.error(tr("No computing activity for {seconds} s (CPU {cpu} s){fatal}, {percent} %: {message}",
                         seconds=f"{now - self._active:.0f}", cpu=f"{cpu:.1f}",
                         fatal=tr(" after {fatal}", fatal=self.fatal) if self.fatal else "", percent=self.percent,
                         message=self.text or "…"))
            stalled = ConversionStalled(now - self._active, self.fatal)
            stalled.position, stalled.phase = self.suspects(), self.phase
            raise stalled

    def _find_fatal(self) -> None:
        """Look for a fatal error in what the child wrote to stderr since the last look."""
        if not self.stderr_path:
            return
        overlap = max(len(marker) for marker in FATAL_MARKERS)
        try:
            with open(self.stderr_path, "rb") as file:
                file.seek(max(0, self._stderr_read - overlap))
                text = file.read(16 * 1024 ** 2).decode("utf-8", errors="replace")
                self._stderr_read = file.tell()
        except OSError:
            return
        for marker, name in FATAL_MARKERS.items():
            if marker in text:
                self.fatal = name()
                log.warning(tr("The conversion process reports a fatal error: {marker}", marker=marker))
                return

    def _written(self) -> int:
        """Bytes written so far: the output, or what is staged for it in the temp folder."""
        paths = [self.output]
        if self.staging and self.staging.is_dir():
            paths += self.staging.rglob("*")
        total = 0
        for path in paths:
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:  # being created or removed right now
                pass
        return total

    def _show(self, text: str) -> None:
        self._shown = time.monotonic()
        if self.status:
            self.status(self.phase, text)


def tree_cpu_seconds(pid: int) -> float | None:
    """CPU seconds used so far by process ``pid`` and all its descendants (workers), or None."""
    try:
        if sys.platform == "win32":
            return _windows_tree_cpu(pid)
        if sys.platform.startswith("linux"):
            return _linux_tree_cpu(pid)
    except (OSError, ValueError, AttributeError):
        pass
    return None


def _descendants(pid: int, parents: dict[int, int]) -> set[int]:
    family, added = {pid}, True
    while added:
        children = {child for child, parent in parents.items() if parent in family} - family
        family |= children
        added = bool(children)
    return family


def _linux_tree_cpu(pid: int) -> float:
    stats = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                with open(f"/proc/{entry}/stat") as file:
                    fields = file.read().rsplit(")", 1)[1].split()
            except OSError:
                continue
            # After the command name: state, ppid, …, utime (field 14) and stime (15).
            stats[int(entry)] = (int(fields[1]), int(fields[11]) + int(fields[12]))
    ticks = os.sysconf("SC_CLK_TCK")
    family = _descendants(pid, {child: parent for child, (parent, _) in stats.items()})
    return sum(stats[member][1] for member in family if member in stats) / ticks


def _windows_tree_cpu(pid: int) -> float:
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, wintypes.HANDLE(-1).value):
        raise OSError("no process snapshot")
    parents = {}
    try:
        entry = ProcessEntry(dwSize=ctypes.sizeof(ProcessEntry))
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    total = 0
    for member in _descendants(pid, parents):
        handle = kernel32.OpenProcess(0x1000, False, member)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if kernel32.GetProcessTimes(handle, *(ctypes.byref(time_) for time_ in times)):
                for time_ in times[2:]:  # kernel and user time, in 100 ns
                    total += (time_.dwHighDateTime << 32) | time_.dwLowDateTime
        finally:
            kernel32.CloseHandle(handle)
    return total / 1e7


def remove_stale_temp_files(max_age: float = STALE_TEMP_AGE) -> int:
    """Delete what conversions left in the temp folder when they were killed (e.g. by a power cut).

    Only entries named "ifc-converter-*" that were not changed for ``max_age`` seconds, so a
    conversion running at the same time (in a terminal) keeps its files. Returns how many went.
    """
    removed = 0
    limit = time.time() - max_age
    try:
        entries = list(Path(tempfile.gettempdir()).glob("ifc-converter-*"))
    except OSError:
        return 0
    for entry in entries:
        try:
            newest = max([entry.stat().st_mtime, *(child.stat().st_mtime for child in entry.rglob("*"))])
            if newest > limit:
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _stderr_file() -> str | None:
    """A new, empty temp file for the child's stderr, or None if the temp folder is not writable."""
    try:
        fd, path = tempfile.mkstemp(prefix="ifc-converter-", suffix=".stderr.txt")
    except OSError:
        return None
    os.close(fd)
    return path


def _log_stderr(path: str | None, failed: bool) -> None:
    """Copy the end of what the child wrote to stderr into the log, then delete the file."""
    if not path:
        return
    try:
        with open(path, "rb") as file:
            size = file.seek(0, os.SEEK_END)
            file.seek(max(0, size - STDERR_LOG_LIMIT))
            text = file.read().decode("utf-8", errors="replace").strip()
    except OSError:
        text, size = "", 0
    if text:
        cut = tr(" (last {shown} KB of {size} KB)", shown=STDERR_LOG_LIMIT // 1000, size=size // 1000) \
            if size > STDERR_LOG_LIMIT else ""
        log.log(logging.WARNING if failed else logging.INFO,
                tr("Output of the conversion process{cut}:\n{message}", cut=cut, message=text))
    try:
        os.unlink(path)
    except OSError:
        pass


def _stop(process, grace: float = 0) -> int | None:
    """Wait ``grace`` seconds for the child to end, then terminate it; returns its exit code.

    Returns once the child is gone, so its output files are closed and can be deleted; but after
    KILL_WAIT seconds even if killing it had no effect (logged), rather than hang the app.
    """
    if process.pid is None:  # never started
        return None
    process.join(grace)
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(KILL_WAIT)
    if process.is_alive():
        log.error(tr("The conversion process {pid} could not be ended", pid=process.pid))
        return None
    exitcode = process.exitcode
    process.close()
    return exitcode
