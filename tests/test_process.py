import logging
import os
import re
import signal
import subprocess
import sys
import threading
import tempfile
import time
from pathlib import Path

import child_helpers
import ifcopenshell
import pytest

from ifc_converter import i18n, process
from ifc_converter.process import (
    Cancelled,
    ConversionCrashed,
    ConversionFailed,
    convert_in_child,
    crash_message,
)

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL is POSIX only")
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="job objects are Windows only")


@pytest.fixture(autouse=True)
def own_quarantine(tmp_path, monkeypatch):
    """Keep the elements remembered by a test out of the developer's own quarantine file."""
    path = tmp_path / "state" / process.QUARANTINE_NAME
    monkeypatch.setattr(process, "quarantine_path", lambda: path)
    return path


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
    assert str(info.value) == process.memory_message()


def test_hard_exit_is_reported_as_crash_with_code(wall_ifc, tmp_path):
    with pytest.raises(ConversionCrashed, match=r"^Umwandlung abgestürzt \(Code 3\)$"):
        convert_in_child(wall_ifc, tmp_path / "x.glb", func=child_helpers.exit_hard)


def test_crash_messages():
    assert crash_message(-9) == process.memory_message() == process.MEMORY_MESSAGE
    assert crash_message(0xC0000017) == process.memory_message()  # Windows STATUS_NO_MEMORY
    assert crash_message(-11) == "Umwandlung abgestürzt: Speicherzugriffsfehler (Code -11)"
    assert crash_message(0xC0000005) == "Umwandlung abgestürzt: Speicherzugriffsfehler (Code 0xC0000005)"
    assert crash_message(0) == "Umwandlung wurde ohne Ergebnis beendet"
    i18n.set_language("en")
    assert crash_message(-11) == "Conversion crashed: memory access violation (code -11)"
    assert crash_message(-9) == process.MEMORY_MESSAGE
    assert process.MEMORY_MESSAGE == "The memory was not enough (the process was ended by the system)"


def test_the_child_reports_in_the_language_of_the_parent(wall_ifc, tmp_path):
    # The language is handed down through the environment (i18n.ENV); the texts are made in the child.
    texts = []
    i18n.set_language("en")
    assert os.environ[i18n.ENV] == "en"
    result = convert_in_child(wall_ifc, tmp_path / "wall.glb", "glb", status=lambda phase, text: texts.append(text))
    assert result.elements == 1
    assert texts[0].startswith("Reading IFC file (") and "Writing GLB file …" in texts
    assert not any("wird" in text for text in texts)
    i18n.set_language("de")
    texts.clear()
    convert_in_child(wall_ifc, tmp_path / "wall.glb", "glb", status=lambda phase, text: texts.append(text))
    assert texts[0].startswith("IFC-Datei wird gelesen (") and "GLB-Datei wird geschrieben …" in texts


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


def test_die_with_parent_watches_the_parent_elsewhere(monkeypatch):
    # Windows/macOS have no prctl: a thread waits for the parent and then ends the child.
    import ctypes

    watched = []
    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: pytest.fail("prctl called"))
    monkeypatch.setattr(process, "exit_with_parent", watched.append)
    process._die_with_parent(4711)
    _wait_for(lambda: watched)
    assert watched == [4711]


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
        wall_ifc, target, progress=events.append, on_retry=lambda message: events.append("retry"),
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
        wall_ifc, target, on_retry=retries.append, func=child_helpers.segfault_unless_opencascade, **options,
    )
    assert result.elements == 1 and retries == [process.RETRY_MESSAGE]
    assert _attempts(target)[-1] == "opencascade"


@posix_only
def test_crash_of_the_retry_fails_with_crash_message(wall_ifc, tmp_path, monkeypatch):
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    target = tmp_path / "wall.glb"
    retries = []
    with pytest.raises(ConversionCrashed, match=r"^Umwandlung abgestürzt: Speicherzugriffsfehler \(Code -11\)$"):
        convert_in_child(wall_ifc, target, on_retry=retries.append, func=child_helpers.always_segfault)
    assert retries == [process.RETRY_MESSAGE]
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
            wall_ifc, target, on_retry=lambda message: pytest.fail("retried"), func=child_helpers.always_segfault,
            **options,
        )
    assert len(_attempts(target)) == 1


@posix_only
def test_no_retry_after_out_of_memory_or_python_error(tmp_path, monkeypatch):
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    crash = tmp_path / "crash.ifc"
    crash.write_text("x")
    no_retry = lambda message: pytest.fail("retried")  # noqa: E731
    with pytest.raises(ConversionCrashed, match=re.escape(process.memory_message())):
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
        import ctypes

        # The parent's class (CI runners start their steps below normal; a child inherits that).
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetPriorityClass.argtypes = (ctypes.c_void_p,)
        assert value == kernel32.GetPriorityClass(kernel32.GetCurrentProcess())
    else:
        assert value == os.getpriority(os.PRIO_PROCESS, 0)


def test_auto_threads_are_the_converter_default(monkeypatch):
    # One definition (converter.default_threads): the kernel's share of half the logical CPUs.
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
    assert "(Exit-Code -11). Absturz im schnellen Geometriekern – neuer Versuch nur mit OpenCASCADE" in caplog.text
    assert "Absturz nach" in caplog.text


@pytest.mark.parametrize("geometry", ["brep", "mesh"])
def test_large_rhino_export_runs_its_workers_inside_the_child(many_walls_ifc, tmp_path, geometry):
    # The conversion child starts worker processes for models of MIN_PARALLEL_ELEMENTS and more. As a
    # daemonic process it could not ("daemonic processes are not allowed to have children"): every
    # large 3dm conversion in the app failed, while small test models never started workers.
    output = tmp_path / f"walls-{geometry}.3dm"
    result = convert_in_child(
        many_walls_ifc, output, "3dm", threads=4, geometry=geometry, func=child_helpers.convert_counting_workers,
    )
    assert result.elements == 600
    assert int(Path(f"{output}.workers").read_text()) > 0  # built by workers, not by the fallback


def test_the_size_written_so_far_is_reported_while_writing(wall_ifc, tmp_path):
    texts = []
    convert_in_child(wall_ifc, tmp_path / "slow.3dm", "3dm", func=child_helpers.write_slowly,
                     status=lambda phase, text: texts.append((phase, text)))
    assert texts[0] == ("write", "Rhino-Datei wird geschrieben (1 Objekte) …")
    sizes = [text for phase, text in texts[1:] if phase == "write"]
    assert sizes and all(text.endswith(" MB geschrieben …") for text in sizes)  # e.g. "…: 2 MB geschrieben …"


def test_long_conversions_leave_a_heartbeat_in_the_log(wall_ifc, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(process, "HEARTBEAT", 0.5)
    with caplog.at_level(logging.INFO, logger="ifc_converter.process"):
        convert_in_child(wall_ifc, tmp_path / "slow.3dm", "3dm", func=child_helpers.write_slowly)
    assert "Rhino-Datei wird geschrieben (1 Objekte) … (nach" in caplog.text  # the phase, with its time
    assert "Läuft seit" in caplog.text


def test_the_staging_folder_is_removed_after_a_cancel(wall_ifc, tmp_path):
    output = tmp_path / "staged.3dm"
    side = Path(f"{output}.staging")
    with pytest.raises(Cancelled):
        convert_in_child(wall_ifc, output, "3dm", func=child_helpers.stage_and_wait,
                         cancelled=lambda: side.exists() and side.read_text() != "")
    staging = Path(side.read_text())
    assert staging.name.startswith("ifc-converter-") and not staging.exists()


def test_crash_dialogs_are_turned_off_on_windows(monkeypatch):
    # A crash must end the process, not keep it alive behind Windows Error Reporting's dialog.
    import ctypes
    import types

    modes = []
    kernel32 = types.SimpleNamespace(SetErrorMode=modes.append)
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(kernel32=kernel32), raising=False)
    monkeypatch.setattr(process.sys, "platform", "win32")
    process.no_crash_dialogs()
    assert modes and modes[0] & 0x0002  # SEM_NOGPFAULTERRORBOX


def test_a_conversion_without_any_cpu_activity_is_stopped_as_stuck(wall_ifc, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(process, "STALL_TIMEOUT", 2)
    monkeypatch.setattr(process, "CPU_SAMPLE", 0.2)
    started = time.monotonic()
    with caplog.at_level(logging.INFO, logger="ifc_converter.process"):
        with pytest.raises(process.ConversionStalled, match="nicht mehr gerechnet"):
            convert_in_child(wall_ifc, tmp_path / "stuck.3dm", "3dm", func=child_helpers.wait_forever)
    assert time.monotonic() - started < 30
    assert "Keine Rechenaktivität" in caplog.text


def test_a_slow_but_working_conversion_is_not_stopped(wall_ifc, tmp_path, monkeypatch):
    monkeypatch.setattr(process, "STALL_TIMEOUT", 2)
    monkeypatch.setattr(process, "CPU_SAMPLE", 0.2)
    result = convert_in_child(wall_ifc, tmp_path / "slow.3dm", "3dm", func=child_helpers.compute_for_a_while)
    assert result.output.read_text() == "done"


def test_cpu_time_of_a_process_tree():
    assert process.tree_cpu_seconds(os.getpid()) > 0


@pytest.mark.parametrize("fmt", ["3dm", "glb"])
@pytest.mark.parametrize("failure", ["hang", "crash"])
def test_an_element_that_hangs_or_crashes_the_kernel_is_skipped(
    many_walls_ifc, tmp_path, monkeypatch, caplog, fmt, failure
):
    if failure == "crash" and sys.platform == "win32":
        pytest.skip("crashes with POSIX signals")
    monkeypatch.setattr(process, "STALL_TIMEOUT", 3)
    monkeypatch.setattr(process, "CPU_SAMPLE", 0.2)
    target = tmp_path / f"walls.{fmt}"
    messages = []
    func = child_helpers.hang_on_wall_7 if failure == "hang" else child_helpers.crash_on_wall_7
    with caplog.at_level(logging.INFO, logger="ifc_converter.process"):
        result = convert_in_child(many_walls_ifc, target, fmt, threads=2, on_retry=messages.append, func=func)
    # The kernel hangs or crashes before the wall is delivered, so it is the only suspect left of its
    # chunk: computed on its own first, then left out. (A crash may come while the next chunk has
    # just started, whose products are then suspects too; by the time a hang is noticed, they are done.)
    assert len(messages) == 2
    one = "bei einem Bauteil" if failure == "hang" else r"bei einem (Bauteil|von \d+ Bauteilen)"
    assert re.search(f"{one}. Neuer Versuch \\(2. von höchstens 7\\), (es wird|diese werden) zuerst und einzeln",
                     messages[0])
    assert "bei IfcWall " in messages[1] and "Neuer Versuch (3. von höchstens 7), dieses Bauteil wird übersprungen" in messages[1]
    assert (result.elements, result.skipped) == (599, 0)
    assert len(result.crashed) == 1 and result.crashed[0].startswith("IfcWall ")
    assert result.crashed[0].endswith(" „Wall 7“")
    assert target.stat().st_size > 0
    assert "Übersprungen, weil der Geometriekern daran abstürzte oder hängen blieb (1):\n  IfcWall" in caplog.text


def test_the_watchdog_leaves_copying_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(process, "STALL_TIMEOUT", 0)
    monkeypatch.setattr(process, "tree_cpu_seconds", lambda pid: 0.0)
    watch = process._Phases(tmp_path / "x.3dm", None, None, None)
    watch.pid = 1
    watch.enter("copy", "Wird ins Zielverzeichnis kopiert …")
    watch._check_stall(time.monotonic())
    watch._check_stall(time.monotonic() + 1)  # no CPU used, but copying to a network folder
    watch.enter("geometry", "Geometrie …")
    watch._check_stall(time.monotonic() + 2)  # first sample
    with pytest.raises(process.ConversionStalled):
        watch._check_stall(time.monotonic() + 3)


def test_a_hang_after_a_fatal_error_is_stopped_within_a_minute(wall_ifc, tmp_path, monkeypatch, caplog):
    # On Windows a stack overflow in a kernel thread leaves the process alive at 0 % CPU; its report
    # in stderr shortens the wait from STALL_TIMEOUT to FATAL_STALL_TIMEOUT.
    monkeypatch.setattr(process, "FATAL_STALL_TIMEOUT", 1)
    monkeypatch.setattr(process, "CPU_SAMPLE", 0.2)
    started = time.monotonic()
    with caplog.at_level(logging.INFO, logger="ifc_converter.process"):
        with pytest.raises(process.ConversionStalled, match="Stapelüberlauf") as failure:
            convert_in_child(wall_ifc, tmp_path / "x.3dm", "3dm", func=child_helpers.overflow_then_wait)
    assert time.monotonic() - started < 60 < process.STALL_TIMEOUT
    assert failure.value.fatal == "Stapelüberlauf"
    assert "meldet einen schweren Fehler: Windows fatal exception: stack overflow" in caplog.text


def test_the_watchdog_ignores_time_the_computer_was_asleep(tmp_path, monkeypatch):
    monkeypatch.setattr(process, "STALL_TIMEOUT", 600)
    monkeypatch.setattr(process, "tree_cpu_seconds", lambda pid: 5.0)
    watch = process._Phases(tmp_path / "x.3dm", None, None, None)
    watch.pid = 1
    watch.enter("geometry", "Geometrie …")
    now = time.monotonic()
    watch._sampled = now - process.CPU_SAMPLE
    watch.tick()  # first sample: 5 s CPU
    watch._sampled -= 3600  # an hour of standby without CPU use
    watch._active -= 3600
    watch.tick()  # not stopped
    assert watch._active >= now


def test_keep_awake_is_a_context_manager():
    with process.keep_awake():
        pass


def test_stale_temp_files_are_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    old_dir = tmp_path / "ifc-converter-abc"
    old_dir.mkdir()
    (old_dir / "model.3dm").write_bytes(b"x" * 100)
    old_file = tmp_path / "ifc-converter-1.stderr.txt"
    old_file.write_text("x")
    fresh = tmp_path / "ifc-converter-new"
    fresh.mkdir()
    (fresh / "model.3dm").write_bytes(b"x")
    other = tmp_path / "someone-else"
    other.mkdir()
    day_ago = time.time() - 2 * 24 * 3600
    for path in (old_dir, old_dir / "model.3dm", old_file, other):
        os.utime(path, (day_ago, day_ago))
    assert process.remove_stale_temp_files() == 2
    assert not old_dir.exists() and not old_file.exists()
    assert fresh.exists() and other.exists()


@posix_only
@pytest.mark.parametrize("func", [child_helpers.segfault_while_reading, child_helpers.segfault_while_writing])
def test_a_crash_outside_the_kernel_is_not_retried_with_opencascade(wall_ifc, tmp_path, monkeypatch, func):
    # Reading the IFC file or writing the output with OpenCASCADE alone would only crash again.
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    target = tmp_path / "wall.3dm"
    with pytest.raises(ConversionCrashed):
        convert_in_child(wall_ifc, target, "3dm", on_retry=lambda message: pytest.fail(message), func=func)
    assert _attempts(target) == ["None"]


@posix_only
def test_a_crash_in_the_axes_of_the_rhino_export_is_retried_without_them(alignment_ifc, tmp_path):
    messages = []
    result = convert_in_child(
        alignment_ifc, tmp_path / "axes.3dm", "3dm", on_retry=messages.append, func=child_helpers.crash_in_curve_pass,
    )
    assert len(messages) == 1
    assert "bei den Achsen (IfcAlignment, IfcGrid). Neuer Versuch (2. von höchstens 7) ohne die Achsen" in messages[0]
    assert result.crashed == ["IfcAlignment " + result.crashed[0].split()[1] + " „Ramp“"]
    assert result.elements == 1  # the axis with a vertical layout comes from the first pass


def test_elements_that_hung_the_kernel_are_skipped_at_once_next_time(many_walls_ifc, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(process, "STALL_TIMEOUT", 3)
    monkeypatch.setattr(process, "CPU_SAMPLE", 0.2)
    first = convert_in_child(many_walls_ifc, tmp_path / "1.glb", "glb", threads=2, func=child_helpers.hang_on_wall_7)
    assert len(first.crashed) == 1 and first.elements == 599

    retries = []
    with caplog.at_level(logging.INFO, logger="ifc_converter.process"):
        again = convert_in_child(
            many_walls_ifc, tmp_path / "2.glb", "glb", threads=2, on_retry=retries.append,
            func=child_helpers.hang_on_wall_7,
        )
    assert retries == [] and again.crashed == first.crashed and again.elements == 599
    assert f"Bekannt aus früheren Umwandlungen dieser Datei, wird übersprungen" in caplog.text

    # With another kernel strategy, or once the file has changed, the wall is computed again.
    assert convert_in_child(many_walls_ifc, tmp_path / "3.glb", "glb", threads=2, kernel="opencascade").elements == 600
    stat = os.stat(many_walls_ifc)
    os.utime(many_walls_ifc, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10 ** 9))
    assert convert_in_child(many_walls_ifc, tmp_path / "4.glb", "glb", threads=2).elements == 600


def test_the_quarantine_key_belongs_to_one_unchanged_file(wall_ifc, tmp_path):
    key = process._quarantine_key(wall_ifc, "accurate")
    assert key == process._quarantine_key(wall_ifc, "accurate")
    assert key.startswith("wall.ifc|") and key != process._quarantine_key(wall_ifc, "hybrid")
    copy = tmp_path / "other.ifc"
    copy.write_bytes(wall_ifc.read_bytes())
    stat = os.stat(wall_ifc)
    os.utime(copy, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert process._quarantine_key(copy, "accurate") != key
    os.utime(wall_ifc, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10 ** 9))
    assert process._quarantine_key(wall_ifc, "accurate") != key
    assert process._quarantine_key(tmp_path / "missing.ifc", "accurate") is None
    # Bound to the geometry kernel's version, not the converter's.
    import ifcopenshell

    assert key.endswith(f"|accurate|ifcopenshell {ifcopenshell.version}")


def test_the_quarantine_survives_a_broken_file_and_stays_small(own_quarantine):
    import json

    key = "a.ifc|1|2|accurate|0.2.5"
    assert process.load_quarantine(key) == {}  # no file yet
    own_quarantine.parent.mkdir(parents=True)
    for broken in ("{kaputt", "[1, 2]", '{"a.ifc|1|2|accurate|0.2.5": []}', ""):
        own_quarantine.write_text(broken)
        assert process.load_quarantine(key) == {}
    own_quarantine.write_text(json.dumps({key: {"elements": {"x": "#x", "7": "IfcWall 7", "8": 8}}, "b": [1]}))
    assert process.load_quarantine(key) == {7: "IfcWall 7"}
    process.save_quarantine(key, {5: "IfcWall 5"})  # over the broken entry
    assert process.load_quarantine(key) == {5: "IfcWall 5"}

    many = {id_: f"#{id_}" for id_ in range(process.QUARANTINE_ELEMENTS + 10)}
    for number in range(process.QUARANTINE_FILES + 5):
        process.save_quarantine(f"f{number}.ifc|1|2|accurate|0", many)
    data = json.loads(own_quarantine.read_text(encoding="utf-8"))
    assert len(data) == process.QUARANTINE_FILES
    assert key not in data and "f0.ifc|1|2|accurate|0" not in data  # the oldest are forgotten
    assert len(process.load_quarantine(f"f{process.QUARANTINE_FILES + 4}.ifc|1|2|accurate|0")) == process.QUARANTINE_ELEMENTS


def test_an_unwritable_quarantine_is_only_logged(own_quarantine, caplog):
    own_quarantine.parent.write_text("a file where the folder should be")
    process.save_quarantine("a.ifc|1|2|accurate|0", {5: "IfcWall 5"})
    assert "konnten nicht gespeichert werden" in caplog.text


class _FakeJob:
    """Stands in for the Windows job object of a conversion."""

    limit = 3 * 1024 ** 3 // 2

    def __init__(self, hit: bool):
        self.hit = hit
        self.assigned = []
        self.closed = False

    def assign(self, handle):
        self.assigned.append(handle)
        return True

    def memory_limit_hit(self):
        return self.hit

    def close(self):
        self.closed = True


def _fake_jobs(monkeypatch, hit: bool) -> list:
    jobs = []

    def create(low_priority=True):
        jobs.append(_FakeJob(hit))
        return jobs[-1]

    monkeypatch.setattr(process._Job, "create", staticmethod(create))
    return jobs


@pytest.mark.parametrize("func", [child_helpers.exit_in_kernel, child_helpers.raise_memory_error])
def test_running_into_the_job_memory_limit_is_reported_as_out_of_memory(wall_ifc, tmp_path, monkeypatch, func):
    # Allocations beyond the limit fail: a crash in native code or a MemoryError, either way not
    # something another attempt would help with.
    jobs = _fake_jobs(monkeypatch, hit=True)
    with pytest.raises(ConversionCrashed) as info:
        convert_in_child(wall_ifc, tmp_path / "x.glb", on_retry=lambda message: pytest.fail(message), func=func)
    assert info.value.memory_limit
    assert str(info.value).startswith(
        "Der Arbeitsspeicher hat nicht gereicht: Die Umwandlung darf höchstens 1,5 GB belegen (85 % des "
    )
    assert len(jobs) == 1 and jobs[0].assigned and jobs[0].closed


def test_without_the_memory_limit_failures_stay_as_they_were(wall_ifc, tmp_path, monkeypatch):
    jobs = _fake_jobs(monkeypatch, hit=False)
    with pytest.raises(ConversionFailed, match="MemoryError"):
        convert_in_child(wall_ifc, tmp_path / "x.glb", func=child_helpers.raise_memory_error)
    retries = []
    with pytest.raises(ConversionCrashed) as info:
        convert_in_child(wall_ifc, tmp_path / "x.glb", on_retry=retries.append, func=child_helpers.exit_in_kernel)
    # The product computed on its own, then everything with OpenCASCADE alone.
    assert not info.value.memory_limit and retries[1:] == [process.RETRY_MESSAGE]
    assert all(job.closed for job in jobs)


def test_a_conversion_that_finished_despite_the_memory_limit_is_kept(wall_ifc, tmp_path, monkeypatch, caplog):
    _fake_jobs(monkeypatch, hit=True)
    with caplog.at_level(logging.INFO, logger="ifc_converter.process"):
        result = convert_in_child(wall_ifc, tmp_path / "wall.glb")
    assert result.elements == 1
    assert "Speichergrenze des Umwandlungsprozesses (1,5 GB) erreicht, die Umwandlung lief trotzdem" in caplog.text


def test_there_is_no_job_object_outside_windows():
    if sys.platform != "win32":
        assert process._Job.create() is None
        assert process.job_memory_limit() is None


@windows_only
def test_closing_the_job_ends_its_processes():
    import ctypes

    job = process._Job.create()
    assert job is not None and job.limit == process.job_memory_limit()
    child = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), "-c", "import time; time.sleep(60)"])
    try:
        assert job.assign(int(child._handle))
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.IsProcessInJob.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
        inside = ctypes.c_int()
        assert kernel32.IsProcessInJob(int(child._handle), job._handle, ctypes.byref(inside)) and inside.value
        assert not job.memory_limit_hit()
        job.close()
        assert child.wait(10) is not None
    finally:
        child.kill()
        child.wait()


@windows_only
def test_the_job_memory_limit_stops_a_runaway_conversion(wall_ifc, tmp_path, monkeypatch):
    monkeypatch.setattr(process, "job_memory_limit", lambda: 1024 ** 3)
    with pytest.raises(ConversionCrashed) as info:
        convert_in_child(wall_ifc, tmp_path / "x.glb", on_retry=lambda message: pytest.fail(message),
                         func=child_helpers.allocate_too_much)
    assert info.value.memory_limit and "höchstens 1,0 GB" in str(info.value)


def test_worker_processes_of_the_child_run_below_normal_priority(wall_ifc, tmp_path):
    result = convert_in_child(wall_ifc, tmp_path / "priority.txt", func=child_helpers.report_worker_priority)
    values = [int(line) for line in result.output.read_text().split()]
    worker, child = values[:2]
    assert worker == child
    if sys.platform == "win32":
        assert child == process.BELOW_NORMAL_PRIORITY_CLASS
        assert values[2] == process.MEMORY_PRIORITY_BELOW_NORMAL
    else:
        assert child == min(19, os.getpriority(os.PRIO_PROCESS, 0) + process.NICE_INCREMENT)


def test_stopping_a_child_that_cannot_be_killed_does_not_hang(monkeypatch, caplog):
    monkeypatch.setattr(process, "KILL_WAIT", 0.1)

    class Immortal:
        pid = 4711
        exitcode = None

        def join(self, timeout=None):
            assert timeout is not None  # never waits without end

        def is_alive(self):
            return True

        def terminate(self):
            pass

        def kill(self):
            pass

        def close(self):
            pytest.fail("closed while still running")

    assert process._stop(Immortal()) is None
    assert "ließ sich nicht beenden" in caplog.text


def test_a_broken_pipe_is_a_crash_not_an_error_of_the_app(wall_ifc, tmp_path, monkeypatch):
    # On Windows, reading from the pipe of a child that is gone raises BrokenPipeError, not EOFError.
    context = process._CONTEXT

    class BrokenReader:
        def __init__(self, connection):
            self._connection = connection

        def __getattr__(self, name):
            return getattr(self._connection, name)

        def poll(self, *args):
            raise BrokenPipeError(109, "Die Pipe wurde beendet")

        def recv(self):
            raise BrokenPipeError(109, "Die Pipe wurde beendet")

    class Context:
        def __getattr__(self, name):
            return getattr(context, name)

        def Pipe(self, duplex=True):
            reader, writer = context.Pipe(duplex=duplex)
            return BrokenReader(reader), writer

    monkeypatch.setattr(process, "_CONTEXT", Context())
    with pytest.raises(ConversionCrashed, match=r"Code 3\)$"):
        convert_in_child(wall_ifc, tmp_path / "x.glb", func=child_helpers.exit_hard)


@pytest.mark.skipif(sys.platform == "win32", reason="crashes with POSIX signals")
@pytest.mark.parametrize("options", [{"geometry": "mesh"}, {"geometry": "brep"}, {"geometry": "brep", "blocks": True}])
def test_a_restart_takes_over_the_chunks_finished_before_the_crash(many_walls_ifc, tmp_path, caplog, options):
    import rhino3dm

    target = tmp_path / "resumed.3dm"
    messages = []
    before = set(Path(tempfile.gettempdir()).glob("ifc-converter-checkpoint-*"))  # e.g. of parallel runs
    with caplog.at_level(logging.INFO, logger="ifc_converter.process"):
        result = convert_in_child(
            many_walls_ifc, target, "3dm", threads=2, on_retry=messages.append,
            func=child_helpers.crash_late_on_wall_450, **options,
        )
    assert (result.elements, len(result.crashed)) == (599, 1) and "Wall 450" in result.crashed[0]
    assert any("bereits berechnete Bauteile werden übernommen" in message for message in messages)
    # The last attempt read the chunks finished before the crash back and computed only the rest
    # (the crashed attempts cannot count: a crash ends their process at once).
    taken = re.findall(r"(\d+) Bauteile aus dem vorigen Versuch übernommen, (\d+) werden berechnet", caplog.text)
    taken = taken[-1]  # of the last attempt, which leaves "Wall 450" out
    assert int(taken[0]) >= 200 and int(taken[0]) + int(taken[1]) == 599
    computed = [int(line) for line in Path(f"{target}.computed").read_text().split()]
    assert computed == [int(taken[1])]
    assert set(Path(tempfile.gettempdir()).glob("ifc-converter-checkpoint-*")) <= before  # removed again

    # The same objects as without any crash, down to the vertices (the file's quarantine leaves
    # "Wall 450" out of this conversion right away).
    reference = convert_in_child(many_walls_ifc, tmp_path / "plain.3dm", "3dm", threads=2, **options)
    assert (reference.elements, reference.crashed) == (599, result.crashed)

    def objects(path):
        found = {}
        for obj in rhino3dm.File3dm.Read(str(path)).Objects:
            guid = obj.Attributes.GetUserString("IfcGlobalId")
            if not guid:  # a block definition's geometry
                continue
            geometry = obj.Geometry
            if isinstance(geometry, rhino3dm.InstanceReference):
                place = tuple(round(value, 9) for value in geometry.Xform.ToFloatArray(True))
            else:
                box = geometry.GetBoundingBox()
                place = tuple(round(value, 9) for point in (box.Min, box.Max) for value in (point.X, point.Y, point.Z))
            found[guid] = (type(geometry).__name__, place)
        return found

    resumed, plain = objects(target), objects(tmp_path / "plain.3dm")
    assert len(resumed) == 599 and set(resumed) == set(plain)
    assert all(resumed[guid][1] == plain[guid][1] for guid in resumed)


def test_checkpoints_hold_plain_data_only(tmp_path):
    import pickle

    from ifc_converter.checkpoint import Checkpoint

    (tmp_path / "chunk-000000.bin").write_bytes(pickle.dumps(([1], [(object,)])))
    assert list(Checkpoint(tmp_path).replay()) == []  # refused, not executed


def test_a_checkpoint_that_cannot_be_written_does_not_stop_the_conversion(tmp_path, caplog):
    from ifc_converter.checkpoint import Checkpoint

    checkpoint = Checkpoint(tmp_path / "missing" / "folder")
    checkpoint._records.append((1, "Body", b"", "g", b"", b"", b"", b"", [], b""))
    with caplog.at_level(logging.WARNING, logger="ifc_converter.checkpoint"):
        checkpoint.chunk_done([1])  # no exception
    assert "Zwischenstand kann nicht gespeichert werden" in caplog.text
    assert checkpoint.written == 0 and list(checkpoint.replay()) == []


def test_no_checkpoint_without_room_or_for_glb(wall_ifc, tmp_path, monkeypatch):
    import shutil as shutil_module

    real = shutil_module.disk_usage
    monkeypatch.setattr(shutil_module, "disk_usage", lambda path: real(path)._replace(free=10))
    assert process._checkpoint_dir(wall_ifc) is None
    monkeypatch.setattr(shutil_module, "disk_usage", real)
    folder = process._checkpoint_dir(wall_ifc)
    assert folder and Path(folder).name.startswith("ifc-converter-checkpoint-")
    Path(folder).rmdir()

    made = []
    monkeypatch.setattr(process, "_checkpoint_dir", lambda path: made.append(path) or str(tmp_path))
    convert_in_child(wall_ifc, tmp_path / "wall.glb", "glb")
    assert made == []  # GLB/OBJ need the kernel's own shapes, so no checkpoint


def test_shapes_read_back_from_a_checkpoint_equal_the_kernels(alignment_ifc, tmp_path):
    # Every attribute the Rhino export reads, for solids and for the line-only shapes of alignments.
    from ifc_converter import converter, rhino
    from ifc_converter.checkpoint import Checkpoint

    model = ifcopenshell.open(str(alignment_ifc))
    checkpoint = Checkpoint(tmp_path)
    shapes = [s for s in converter.iter_shapes(model, rhino._settings(), 2, rhino.EXCLUDED_CLASSES)]
    for shape in shapes:
        checkpoint.record(shape)
    checkpoint.chunk_done([shape.id for shape in shapes])
    [(ids, replayed)] = list(Checkpoint(tmp_path).replay())
    assert ids == [shape.id for shape in shapes] and len(replayed) == len(shapes)
    for real, copy in zip(shapes, replayed):
        a, b = real.geometry, copy.geometry
        assert (copy.id, copy.context, bytes(copy.transformation_buffer)) == (real.id, real.context, bytes(real.transformation_buffer))
        assert (b.id, b.verts_buffer, b.faces_buffer, b.item_ids_buffer, b.material_ids_buffer) == (
            a.id, bytes(a.verts_buffer), bytes(a.faces_buffer), bytes(a.item_ids_buffer), bytes(a.material_ids_buffer))
        assert bool(b.verts) == bool(a.verts)
        if not a.faces:
            assert b.edges == tuple(a.edges) and b.edges
        # repr: a missing transparency is NaN, which never equals itself
        assert [repr((m.name, m.diffuse.r(), m.diffuse.g(), m.diffuse.b(), m.transparency)) for m in b.materials] == [
            repr((m.name, m.diffuse.r(), m.diffuse.g(), m.diffuse.b(), m.transparency)) for m in a.materials]
