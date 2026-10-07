import logging
import os
import re
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


def test_skipped_count_survives_the_transfer(wall_ifc, tmp_path):
    result = convert_in_child(wall_ifc, tmp_path / "x.glb", func=child_helpers.report_skipped)
    assert (result.elements, result.skipped) == (1, 3)


def test_real_conversion_reports_no_skipped_elements(wall_ifc, tmp_path):
    assert convert_in_child(wall_ifc, tmp_path / "wall.glb").skipped == 0


def test_model_without_geometry_fails_with_converter_message(tmp_path):
    import ifcopenshell.api as api

    model = api.run("project.create_file", version="IFC4")
    api.run("root.create_entity", model, ifc_class="IfcProject", name="Leer")
    path = tmp_path / "leer.ifc"
    model.write(str(path))
    with pytest.raises(ConversionFailed) as info:
        convert_in_child(path, tmp_path / "leer.glb")
    assert info.value.type_name == "ValueError"
    assert "keine Bauteile mit Geometrie" in str(info.value)
    assert not (tmp_path / "leer.glb").exists()


def _attempts(target: Path) -> list[str]:
    return target.with_suffix(".attempts").read_text().split()


@posix_only
def test_hybrid_kernel_crash_is_retried_with_opencascade(wall_ifc, tmp_path, monkeypatch):
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    target = tmp_path / "wall.glb"
    events = []
    result = convert_in_child(
        wall_ifc, target, progress=events.append, on_retry=lambda: events.append("retry"),
        func=child_helpers.segfault_unless_opencascade,
    )
    assert result.elements == 1 and target.stat().st_size > 0
    assert _attempts(target) == ["None", "opencascade"]
    # Progress of the crashed attempt, then the retry, which starts again at 0 %.
    assert events[:3] == [0, 40, "retry"] and events[3] == 0 and events[-1] == 100


@posix_only
@pytest.mark.parametrize("kernel", ["accurate", "hybrid"])
@pytest.mark.parametrize("how", ["argument", "environment"])
def test_strategies_using_the_hybrid_kernel_are_retried(wall_ifc, tmp_path, monkeypatch, kernel, how):
    target = tmp_path / "wall.glb"
    options = {}
    if how == "argument":
        monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
        options["kernel"] = kernel
    else:
        monkeypatch.setenv("IFC_CONVERTER_KERNEL", kernel)
    retries = []
    result = convert_in_child(
        wall_ifc, target, on_retry=lambda: retries.append(1), func=child_helpers.segfault_unless_opencascade, **options,
    )
    assert result.elements == 1 and retries == [1]
    assert _attempts(target)[-1] == "opencascade"


@posix_only
def test_crash_of_the_retry_fails_with_crash_message(wall_ifc, tmp_path, monkeypatch):
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    target = tmp_path / "wall.glb"
    retries = []
    with pytest.raises(ConversionCrashed, match=r"^Umwandlung abgestürzt \(Code -11\)$"):
        convert_in_child(wall_ifc, target, on_retry=lambda: retries.append(1), func=child_helpers.always_segfault)
    assert retries == [1]
    assert _attempts(target) == ["None", "opencascade"]


@posix_only
@pytest.mark.parametrize("how", ["argument", "environment"])
def test_no_retry_when_opencascade_was_chosen(wall_ifc, tmp_path, monkeypatch, how):
    target = tmp_path / "wall.glb"
    options = {}
    if how == "argument":
        options["kernel"] = "opencascade"
    else:
        monkeypatch.setenv("IFC_CONVERTER_KERNEL", "opencascade")
    with pytest.raises(ConversionCrashed):
        convert_in_child(
            wall_ifc, target, on_retry=lambda: pytest.fail("retried"), func=child_helpers.always_segfault,
            **options,
        )
    assert len(_attempts(target)) == 1


@posix_only
def test_no_retry_after_out_of_memory_or_python_error(tmp_path, monkeypatch):
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    crash = tmp_path / "crash.ifc"
    crash.write_text("x")
    no_retry = lambda: pytest.fail("retried")  # noqa: E731
    with pytest.raises(ConversionCrashed, match=re.escape(MEMORY_MESSAGE)):
        convert_in_child(crash, tmp_path / "crash.glb", on_retry=no_retry, func=child_helpers.killed_if_named_crash)
    with pytest.raises(ConversionFailed):
        convert_in_child(crash, tmp_path / "x.glb", on_retry=no_retry, func=child_helpers.raise_error)


def test_native_stdout_of_the_child_is_silenced(wall_ifc, tmp_path, capfd):
    result = convert_in_child(wall_ifc, tmp_path / "wall.glb", "glb", func=child_helpers.chatty_native_code)
    assert result.elements == 1
    out, _ = capfd.readouterr()
    assert "local z" not in out and "chatter" not in out


def test_child_runs_below_normal_priority(wall_ifc, tmp_path):
    result = convert_in_child(wall_ifc, tmp_path / "low.txt", func=child_helpers.report_priority)
    value = int(result.output.read_text())
    if sys.platform == "win32":
        assert value == process.BELOW_NORMAL_PRIORITY_CLASS
    else:
        own = os.getpriority(os.PRIO_PROCESS, 0)
        assert value == min(19, own + process.NICE_INCREMENT)


def test_child_keeps_normal_priority_if_asked(wall_ifc, tmp_path):
    result = convert_in_child(wall_ifc, tmp_path / "normal.txt", func=child_helpers.report_priority, low_priority=False)
    value = int(result.output.read_text())
    if sys.platform == "win32":
        assert value == 0x20  # NORMAL_PRIORITY_CLASS
    else:
        assert value == os.getpriority(os.PRIO_PROCESS, 0)


def test_auto_threads_are_the_converter_default(monkeypatch):
    # One definition (converter.default_threads): cores but two, at most MAX_DEFAULT_THREADS.
    from ifc_converter import converter

    assert process.auto_threads() == converter.default_threads()
    monkeypatch.setattr(process, "default_threads", lambda: 7)
    assert process.auto_threads() == 7


def test_child_gets_auto_threads_by_default(wall_ifc, tmp_path):
    result = convert_in_child(wall_ifc, tmp_path / "threads.txt", func=child_helpers.report_threads)
    assert int(result.output.read_text()) == process.auto_threads()
    result = convert_in_child(wall_ifc, tmp_path / "threads.txt", threads=3, func=child_helpers.report_threads)
    assert int(result.output.read_text()) == 3


def test_child_stderr_goes_to_the_log_and_temp_file_is_removed(wall_ifc, tmp_path, monkeypatch, caplog):
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(process.tempfile, "tempdir", str(temp))
    caplog.set_level(logging.INFO, logger="ifc_converter")
    convert_in_child(wall_ifc, tmp_path / "out.txt", func=child_helpers.write_to_stderr)
    assert "python warning on stderr" in caplog.text
    assert "native message on fd 2" in caplog.text
    assert list(temp.iterdir()) == []


def test_python_traceback_of_the_child_is_kept_and_logged(wall_ifc, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="ifc_converter")
    with pytest.raises(ConversionFailed) as info:
        convert_in_child(wall_ifc, tmp_path / "x.glb", func=child_helpers.raise_error)
    assert "Traceback" in info.value.details and "def raise_error" not in info.value.details
    assert "in raise_error" in info.value.details
    assert "ValueError: wall.ifc ist kaputt" in caplog.text and "in raise_error" in caplog.text


def test_conversion_start_and_result_are_logged(wall_ifc, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="ifc_converter")
    convert_in_child(wall_ifc, tmp_path / "wall.glb", "glb", threads=2)
    assert re.search(r"Umwandlung: .*wall\.ifc \(\d+,?\.?\d* MB\) -> .*wall\.glb, Format glb, 2 Threads", caplog.text)
    assert re.search(r"Fertig nach \d+\.\d s: .*wall\.ifc -> .*wall\.glb, 1 Bauteile, 0 ohne Geometrie", caplog.text)


@pytest.mark.skipif(sys.platform == "win32", reason="SIGSEGV via os.kill is POSIX only")
def test_native_crash_stack_and_retry_are_logged(wall_ifc, tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    caplog.set_level(logging.INFO, logger="ifc_converter")
    with pytest.raises(ConversionCrashed):
        convert_in_child(wall_ifc, tmp_path / "x.glb", func=child_helpers.always_segfault)
    assert "Fatal Python error: Segmentation fault" in caplog.text
    assert "always_segfault" in caplog.text  # the Python stack of the crash
    assert "neuer Versuch mit OpenCASCADE" in caplog.text
    assert "Absturz nach" in caplog.text
