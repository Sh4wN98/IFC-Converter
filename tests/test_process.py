import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import child_helpers
import pytest

from ifc_converter import process
from ifc_converter.process import (
    MEMORY_MESSAGE,
    Cancelled,
    ConversionCrashed,
    ConversionFailed,
    convert_in_child,
    crash_message,
)

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL is POSIX only")


def test_converts_wall_in_child_with_progress(wall_ifc, tmp_path):
    progress = []
    result = convert_in_child(wall_ifc, tmp_path / "wall.glb", "glb", progress=progress.append)
    assert result.output == tmp_path / "wall.glb"
    assert result.elements == 1
    assert result.output.stat().st_size > 0
    assert progress[0] == 0 and progress[-1] == 100


def test_runs_in_another_process(wall_ifc, tmp_path):
    result = convert_in_child(wall_ifc, tmp_path / "pid.glb", func=child_helpers.report_pid)
    assert int(result.output.read_text()) != os.getpid()


def test_python_exception_comes_back_as_type_and_text(wall_ifc, tmp_path):
    with pytest.raises(ConversionFailed) as info:
        convert_in_child(wall_ifc, tmp_path / "x.glb", func=child_helpers.raise_error)
    assert str(info.value) == "wall.ifc ist kaputt"
    assert info.value.type_name == "ValueError"

    with pytest.raises(ConversionFailed, match="^KeyError$"):
        convert_in_child(wall_ifc, tmp_path / "x.glb", func=child_helpers.raise_bare_error)


@posix_only
def test_killed_child_is_reported_as_out_of_memory(tmp_path):
    crash = tmp_path / "crash.ifc"
    crash.write_text("x")
    with pytest.raises(ConversionCrashed) as info:
        convert_in_child(crash, tmp_path / "crash.glb", func=child_helpers.killed_if_named_crash)
    assert info.value.exitcode == -9
    assert str(info.value) == MEMORY_MESSAGE


def test_hard_exit_is_reported_as_crash_with_code(wall_ifc, tmp_path):
    with pytest.raises(ConversionCrashed, match=r"^Umwandlung abgestürzt \(Code 3\)$"):
        convert_in_child(wall_ifc, tmp_path / "x.glb", func=child_helpers.exit_hard)


def test_crash_messages():
    assert crash_message(-9) == MEMORY_MESSAGE
    assert crash_message(0xC0000017) == MEMORY_MESSAGE  # Windows STATUS_NO_MEMORY
    assert crash_message(-11) == "Umwandlung abgestürzt (Code -11)"
    assert crash_message(0xC0000005) == "Umwandlung abgestürzt (Code 0xC0000005)"
    assert crash_message(0) == "Umwandlung wurde ohne Ergebnis beendet"


def test_cancel_terminates_child_while_it_is_reading(wall_ifc, tmp_path):
    target = tmp_path / "slow.glb"
    pid_file = target.with_suffix(".pid")
    cancel = threading.Event()
    # Cancel once the child is busy "reading" the file.
    watcher = threading.Thread(target=lambda: (_wait_for(pid_file.exists), cancel.set()), daemon=True)
    watcher.start()

    started = time.monotonic()
    with pytest.raises(Cancelled):
        convert_in_child(wall_ifc, target, cancelled=cancel.is_set, func=child_helpers.sleep_while_reading)
    assert time.monotonic() - started < 15  # the child would sleep for 2 minutes
    assert _process_gone(int(pid_file.read_text()))


def test_raising_progress_callback_stops_child(wall_ifc, tmp_path):
    def progress(percent):
        raise Cancelled

    with pytest.raises(Cancelled):
        convert_in_child(wall_ifc, tmp_path / "x.glb", progress=progress, func=child_helpers.report_pid)


@posix_only
def test_child_ignores_ctrl_c(wall_ifc, tmp_path):
    # The parent handles Ctrl+C and terminates the child; the child must not die on it by itself.
    result = convert_in_child(wall_ifc, tmp_path / "wall.glb", func=child_helpers.interrupted_then_convert)
    assert result.output.stat().st_size > 0


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG is Linux only")
def test_child_dies_with_killed_parent(wall_ifc, tmp_path):
    target = tmp_path / "slow.glb"
    pid_file = target.with_suffix(".pid")
    tests_dir = str(Path(child_helpers.__file__).parent)
    # A parent process that runs a slow conversion child and then gets SIGKILLed, like by the OOM killer.
    parent = subprocess.Popen([
        sys.executable, "-c",
        "import sys; sys.path.insert(0, sys.argv[1]); import child_helpers; "
        "from ifc_converter.process import convert_in_child; "
        "convert_in_child(sys.argv[2], sys.argv[3], func=child_helpers.sleep_while_reading)",
        tests_dir, str(wall_ifc), str(target),
    ])
    try:
        _wait_for(pid_file.exists)
        child = int(pid_file.read_text())
        assert not _process_gone(child)
        parent.kill()
    finally:
        parent.kill()
        parent.wait()
    _wait_for(lambda: _process_gone(child), timeout=10)
    assert _process_gone(child)


def test_die_with_parent_is_a_no_op_elsewhere(monkeypatch):
    import ctypes

    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: pytest.fail("prctl called"))
    process._die_with_parent(os.getppid() + 1)  # neither calls prctl nor exits


def _wait_for(condition, timeout=30):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.05)


def _process_gone(pid: int) -> bool:
    if sys.platform == "win32":
        return True  # convert_in_child() only returns after joining the child
    try:
        with open(f"/proc/{pid}/stat") as stat:
            return stat.read().rsplit(")", 1)[1].split()[0] == "Z"  # dead, not yet reaped by init
    except FileNotFoundError:
        return True
    except OSError:  # no /proc, e.g. macOS
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False
