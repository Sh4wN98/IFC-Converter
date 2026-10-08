"""Run convert() in a child process, so running out of memory or a native crash only ends that process.

On Linux the OOM killer SIGKILLs the process using the most memory, which for a multi-GB IFC file is
the one converting it. In a child process that is no longer the GUI, and a cancel can simply terminate
the child, even while IfcOpenShell is still reading the file (which cannot be interrupted otherwise).

The child runs at a lower priority, so the PC stays responsive while it uses all its cores, and what it
writes to stderr (warnings, tracebacks, a native crash's Python stack) ends up in the log file.
"""

from __future__ import annotations

import faulthandler
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
from collections.abc import Callable
from multiprocessing.connection import wait
from pathlib import Path

from ifc_converter.converter import (
    DEFAULT_KERNEL, MAX_DEFAULT_THREADS, SPARE_CORES, ConversionResult, ProgressCallback, convert,
    default_threads, size_text,
)

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
STALL_CPU = 1.0
CPU_SAMPLE = 30

MEMORY_MESSAGE = "Der Arbeitsspeicher hat nicht gereicht (Prozess wurde vom System beendet)"
# Shown when a crash in the hybrid geometry kernel is retried with OpenCASCADE alone.
RETRY_MESSAGE = "Absturz im schnellen Geometriekern – neuer Versuch nur mit OpenCASCADE …"
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
# Cores left free for other programs by default.

log = logging.getLogger(__name__)


class Cancelled(Exception):
    """The conversion was cancelled; raised from a progress callback or by convert_in_child()."""


class ConversionFailed(Exception):
    """A Python exception in the child process, as its type name, text and traceback."""

    def __init__(self, type_name: str, text: str, details: str = ""):
        super().__init__(text or type_name)
        self.type_name = type_name
        self.details = details


class ConversionCrashed(Exception):
    """The child process died without a result (killed, or a native crash)."""

    def __init__(self, exitcode: int | None):
        super().__init__(crash_message(exitcode))
        self.exitcode = exitcode


class ConversionStalled(Exception):
    """The child's processes used no CPU for STALL_TIMEOUT: they wait for something that never comes."""

    def __init__(self, seconds: float):
        super().__init__(
            f"Die Umwandlung hat {seconds / 60:.0f} Minuten lang nicht mehr gerechnet und wurde abgebrochen "
            "(sie hing fest). Bitte die Logdatei an den Entwickler schicken."
        )


def cpu_count() -> int:
    """Logical CPUs this process may use."""
    count = os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()
    return count or 1


def auto_threads() -> int:
    """The default number of geometry threads (see converter.default_threads)."""
    return default_threads()


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
    """Whether a child that ended with ``exitcode`` and no result may have crashed in the hybrid kernel.

    The hybrid kernel segfaults on some models that OpenCASCADE converts fine; the strategies
    "hybrid" and "accurate" (triangle meshes) use it. Running out of memory is no such crash.
    """
    kernel = options.get("kernel") or os.environ.get("IFC_CONVERTER_KERNEL") or DEFAULT_KERNEL
    return kernel.lower() in ("accurate", "hybrid") and exitcode not in (None, 0) and not _out_of_memory(exitcode)


def _recover(failure: Exception, options: dict, isolate: set[int], skipped: dict[int, str]) -> str | None:
    """Plan the next attempt after a crash or hang; returns the message for it, or None to give up.

    ``failure.position`` is where the child was: ("chunk", ids, "") or ("element", [id], label).
    """
    what = "hängt fest" if isinstance(failure, ConversionStalled) else "ist abgestürzt"
    if isinstance(failure, ConversionCrashed) and _out_of_memory(failure.exitcode):
        return None
    kind, ids, label = getattr(failure, "position", None) or (None, [], "")
    if kind == "element" and ids and ids[0] not in skipped:
        skipped[ids[0]] = label or f"#{ids[0]}"
        return (f"Die Umwandlung {what} bei {skipped[ids[0]]} – dieses Bauteil wird übersprungen, "
                "neuer Versuch …")
    if kind == "chunk" and ids and not set(ids) <= isolate:
        isolate.update(ids)
        return (f"Die Umwandlung {what} in einem Paket von {len(ids)} Bauteilen – diese werden einzeln "
                "berechnet, neuer Versuch …")
    if isinstance(failure, ConversionCrashed) and _retry_with_opencascade(failure.exitcode, options) \
            and options.get("kernel") != "opencascade":
        options["kernel"] = "opencascade"
        return RETRY_MESSAGE
    return None


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


def lower_priority() -> None:
    """Run the calling process (and the processes it starts) below normal priority.

    A conversion uses every core it gets; at a lower priority, Rhino, Revit or Outlook still get the
    CPU first, so the PC stays responsive and the conversion uses the time they leave over.
    """
    try:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
            kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(NICE_INCREMENT)
    except (OSError, AttributeError):
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
    _die_with_parent(parent_pid)
    no_crash_dialogs()
    _redirect_stderr(stderr_path)
    if low_priority:
        lower_priority()
    # Ctrl+C in a terminal reaches the whole process group. The parent handles it and terminates the
    # child, which would otherwise print its own traceback.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _silence_stdout()

    def progress(percent: int) -> None:
        conn.send(("progress", percent))

    def status(phase: str, text: str) -> None:
        conn.send(("status", phase, text))

    def position(kind: str, ids: list, label: str) -> None:
        conn.send(("position", kind, ids, label))

    try:
        result = func(*args, progress=progress, status=status, position=position, **kwargs)
    except Exception as exc:  # exception objects may not unpickle in the parent, so send plain text
        conn.send(("error", type(exc).__name__, str(exc), traceback.format_exc()))
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
    on_retry: Callable[[str], None] | None = None,
    low_priority: bool = True,
    status: Callable[[str, str], None] | None = None,
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
    ``on_retry`` gets a German message before each new attempt, and progress starts again from reading.

    ``threads`` defaults to auto_threads(); ``low_priority`` runs the child below normal priority.
    ``status`` gets the current phase ("read", "geometry", "write", "copy") and a German description
    (while writing with the size written so far). Start, phases, a heartbeat every minute, outcome and
    duration of the conversion are logged.
    """
    threads = threads or auto_threads()
    args = (input_path, output_path, fmt, threads)
    log.info(
        "Umwandlung: %s (%s) -> %s, Format %s, %d Threads%s%s", input_path, _size_text(input_path),
        output_path or "(neben der IFC-Datei)", fmt, threads, "".join(f", {k}={v}" for k, v in options.items()),
        "" if low_priority else ", normale Priorität",
    )
    started = time.monotonic()
    isolate: set[int] = set()
    skipped: dict[int, str] = {}
    try:
        for attempt in range(MAX_RECOVERIES + 1):
            attempt_options = dict(options)
            if isolate:
                attempt_options["isolate_ids"] = sorted(isolate)
            if skipped:
                attempt_options["skip_ids"] = sorted(skipped)
            try:
                result = _run_child(func, args, attempt_options, progress, cancelled, low_priority, status, started)
                break
            except (ConversionCrashed, ConversionStalled) as failure:
                message = _recover(failure, options, isolate, skipped)
                if message is None or attempt == MAX_RECOVERIES:
                    raise
                code = f" (Exit-Code {failure.exitcode})" if isinstance(failure, ConversionCrashed) else ""
                log.warning("%s%s – %s", failure, code, message)
                if on_retry:
                    on_retry(message)
        if skipped:
            log.warning("Übersprungen, weil der Geometriekern daran abstürzte oder hängen blieb: %s",
                        "; ".join(skipped.values()))
    except Cancelled:
        log.info("Abgebrochen nach %.1f s: %s", time.monotonic() - started, input_path)
        raise
    except ConversionFailed as exc:
        log.error("Fehler nach %.1f s bei %s: %s: %s\n%s", time.monotonic() - started, input_path,
                  exc.type_name, exc, exc.details.rstrip())
        raise
    except ConversionCrashed as exc:
        log.error("Absturz nach %.1f s bei %s: %s (Exit-Code %s)", time.monotonic() - started, input_path,
                  exc, exc.exitcode)
        raise
    except ConversionStalled:
        log.error("Hing fest, abgebrochen nach %.1f s: %s", time.monotonic() - started, input_path)
        raise
    except Exception:
        log.exception("Umwandlung von %s fehlgeschlagen", input_path)
        raise
    log.info("Fertig nach %.1f s: %s -> %s, %d Bauteile, %d ohne Geometrie", time.monotonic() - started,
             input_path, result.output, result.elements, result.skipped)
    return result


def _size_text(path: str | Path) -> str:
    try:
        return f"{os.path.getsize(path) / 1024 ** 2:.1f} MB"
    except OSError:
        return "Größe unbekannt"


def _run_child(
    func: Callable[..., ConversionResult],
    args: tuple,
    options: dict,
    progress: ProgressCallback | None,
    cancelled: Callable[[], bool],
    low_priority: bool = True,
    status: Callable[[str, str], None] | None = None,
    started: float | None = None,
) -> ConversionResult:
    """One attempt of convert_in_child()."""
    stderr_path = _stderr_file()
    staging = _staging_dir()
    watch = _Phases(args[1] or Path(args[0]).with_suffix(f".{args[2]}"), staging, status, started)
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
    try:
        process.start()
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
                except EOFError:  # the child is ending without a result
                    process.join(5)
                    break
                if message[0] == "progress":
                    watch.percent = message[1]
                    if progress:
                        progress(message[1])
                elif message[0] == "status":
                    watch.enter(message[1], message[2])
                elif message[0] == "position":
                    watch.position = tuple(message[1:])
                else:
                    outcome = message
            elif process.sentinel in ready:
                # Anything the child sent before it ended is still in the pipe.
                while outcome is None and reader.poll():
                    try:
                        message = reader.recv()
                    except EOFError:
                        break
                    if message[0] == "position":
                        watch.position = tuple(message[1:])
                    elif message[0] not in ("progress", "status"):
                        outcome = message
                break
    finally:
        # A child that delivered its result is just exiting; a cancelled or failed one is stopped now.
        exitcode = _stop(process, grace=5 if outcome else 0)
        reader.close()
        _log_stderr(stderr_path, failed=outcome is None or outcome[0] == "error")
        if staging:
            shutil.rmtree(staging, ignore_errors=True)

    if outcome is None:
        crash = ConversionCrashed(exitcode)
        crash.position = watch.position
        raise crash
    if outcome[0] == "error":
        raise ConversionFailed(*outcome[1:])
    return outcome[1]


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

    def __init__(self, output: Path, staging: str | None, status, started: float | None):
        self.output = Path(output)
        self.staging = Path(staging) if staging else None
        self.status = status
        self.started = started or time.monotonic()
        self.phase = self.text = ""
        self.percent = 0
        self._shown = self._logged = time.monotonic()
        self.pid: int | None = None
        self.position: tuple | None = None  # where the child is: ("chunk"|"element", ids, label)
        self._sampled = self._active = time.monotonic()
        self._active_cpu: float | None = None

    def enter(self, phase: str, text: str) -> None:
        if phase != self.phase:
            log.info("%s (nach %.0f s)", text, time.monotonic() - self.started)
        self.phase, self.text = phase, text
        self._show(text)

    def tick(self) -> None:
        now = time.monotonic()
        if self.pid and now - self._sampled >= CPU_SAMPLE:
            self._sampled = now
            self._check_stall(now)
        if now - self._logged >= HEARTBEAT:
            self._logged = now
            log.info("Läuft seit %.0f s, %d %%: %s", now - self.started, self.percent, self.text or "…")
        if self.phase == "write" and now - self._shown >= 1:
            self._show(f"{self.text.removesuffix(' …')}: {size_text(self._written())} geschrieben …")

    def _check_stall(self, now: float) -> None:
        if self.phase == "copy":  # copying to a slow network folder needs hardly any CPU
            self._active, self._active_cpu = now, None
            return
        cpu = tree_cpu_seconds(self.pid)
        if cpu is None:  # not measurable here: no watchdog
            return
        if self._active_cpu is None or cpu - self._active_cpu >= STALL_CPU:
            self._active, self._active_cpu = now, cpu
        elif now - self._active >= STALL_TIMEOUT:
            log.error("Keine Rechenaktivität seit %.0f s (CPU %.1f s), %d %%: %s",
                      now - self._active, cpu, self.percent, self.text or "…")
            stalled = ConversionStalled(now - self._active)
            stalled.position = self.position
            raise stalled

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
        cut = f" (letzte {STDERR_LOG_LIMIT // 1000} KB von {size // 1000} KB)" if size > STDERR_LOG_LIMIT else ""
        log.log(logging.WARNING if failed else logging.INFO, "Ausgabe des Umwandlungsprozesses%s:\n%s", cut, text)
    try:
        os.unlink(path)
    except OSError:
        pass


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
