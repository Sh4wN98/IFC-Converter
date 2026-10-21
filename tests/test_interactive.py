import io
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from functools import partial
from pathlib import Path

import child_helpers
import pytest

from ifc_converter import interactive, process
from ifc_converter.interactive import collect_ifc_files, parse_dropped, unique_path


def test_parse_linux_single_quoted_with_spaces():
    assert parse_dropped("'/home/a/My Model.ifc' ", windows=False) == [Path("/home/a/My Model.ifc")]


def test_parse_linux_backslash_escaped_spaces():
    assert parse_dropped(r"/home/a/My\ Model.ifc /home/a/b.ifc", windows=False) == [
        Path("/home/a/My Model.ifc"),
        Path("/home/a/b.ifc"),
    ]


def test_parse_file_uri():
    assert parse_dropped("file:///home/a/My%20Model.ifc", windows=False) == [Path("/home/a/My Model.ifc")]


def test_parse_windows_quoted_and_bare_paths():
    line = r'"C:\Users\Jonas\Projekt A\haus.ifc" C:\daten\b.ifc'
    assert [str(p) for p in parse_dropped(line, windows=True)] == [
        r"C:\Users\Jonas\Projekt A\haus.ifc",
        r"C:\daten\b.ifc",
    ]


def test_parse_powershell_call_operator():
    line = r"& 'C:\Users\Jonas\haus.ifc'"
    assert [str(p) for p in parse_dropped(line, windows=True)] == [r"C:\Users\Jonas\haus.ifc"]


def test_parse_unquoted_existing_path_with_spaces(tmp_path):
    path = tmp_path / "mit leerzeichen.ifc"
    path.touch()
    assert parse_dropped(str(path), windows=False) == [path]


def test_unique_path_counts_up(tmp_path):
    (tmp_path / "haus.glb").touch()
    (tmp_path / "haus (2).glb").touch()
    assert unique_path(tmp_path / "haus.glb") == tmp_path / "haus (3).glb"


def test_collect_searches_folders_and_rejects_other_files(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.IFC").touch()
    (tmp_path / "notes.txt").touch()
    files, rejected = collect_ifc_files([tmp_path / "sub", tmp_path / "notes.txt"])
    assert files == [tmp_path / "sub" / "a.IFC"]
    assert rejected == [tmp_path / "notes.txt"]


def test_session_converts_dropped_file_and_switches_format(wall_ifc, tmp_path, monkeypatch, capsys):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    lines = iter([f"'{wall_ifc}'", "obj", f"'{wall_ifc}'", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))

    assert interactive.run(output_dir=desktop) == 0
    assert (desktop / "wall.glb").exists()
    assert (desktop / "wall.obj").exists()
    assert "Fertig" in capsys.readouterr().out


def test_session_reports_non_ifc_and_exits_on_eof(tmp_path, monkeypatch, capsys):
    lines = iter([str(tmp_path / "foto.jpg")])

    def fake_input(prompt=""):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)
    assert interactive.run(output_dir=tmp_path) == 0
    assert "Keine IFC-Datei" in capsys.readouterr().out


def test_check_memory_ignores_missing_files(tmp_path):
    assert interactive.check_memory(tmp_path / "fehlt.ifc") is None


def test_session_prints_memory_warning(wall_ifc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("ifc_converter.interactive.memory_warning", lambda path: "zu wenig RAM")
    lines = iter([f"'{wall_ifc}'", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert interactive.run(output_dir=tmp_path) == 0
    out = capsys.readouterr().out
    assert "⚠ zu wenig RAM" in out
    assert "Fertig" in out


def test_cli_prints_memory_warning_to_stderr(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    monkeypatch.setattr("ifc_converter.interactive.memory_warning", lambda path: "zu wenig RAM")
    assert main([str(wall_ifc), "-f", "glb", "-d", str(tmp_path / "out")]) == 0
    captured = capsys.readouterr()
    assert "⚠ zu wenig RAM" in captured.err
    assert (tmp_path / "out" / "wall.glb").exists()


class FakeTerminal(io.StringIO):
    def isatty(self):
        return True


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL is POSIX only")


def use_child_func(monkeypatch, func):
    """Let the conversion child processes run ``func`` (a top-level function) instead of convert()."""
    monkeypatch.setattr(interactive, "convert_in_child", partial(process.convert_in_child, func=func))


def test_cli_shows_progress_on_a_terminal(wall_ifc, tmp_path, monkeypatch):
    from ifc_converter.cli import main

    terminal = FakeTerminal()
    monkeypatch.setattr(sys, "stdout", terminal)
    assert main([str(wall_ifc), "-f", "glb", "-d", str(tmp_path / "out")]) == 0
    text = terminal.getvalue()
    assert text.startswith("\rwall.ifc: IFC wird gelesen …")
    assert "\rwall.ifc: 0 %" in text and "\rwall.ifc: 100 %" in text
    # The progress line is blanked out before the result is printed.
    assert re.search(r"\r +\r✓ .*wall\.ifc → .*wall\.glb \(1 elements\)\n$", text)


def test_cli_prints_no_progress_when_redirected(wall_ifc, tmp_path, capsys):
    from ifc_converter.cli import main

    assert main([str(wall_ifc), "-f", "glb", "-d", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "\r" not in out and "%" not in out and "gelesen" not in out
    assert out.startswith("✓ ")


@posix_only
def test_cli_batch_continues_after_killed_conversion(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    use_child_func(monkeypatch, child_helpers.killed_if_named_crash)
    crash = tmp_path / "crash.ifc"
    crash.write_text("x")
    out = tmp_path / "out"
    assert main([str(crash), str(wall_ifc), "-f", "glb", "-d", str(out)]) == 1
    captured = capsys.readouterr()
    assert f"✗ {crash}: {process.MEMORY_MESSAGE}" in captured.err
    assert not (out / "crash.glb").exists()  # partial output removed
    assert "✓ " in captured.out and (out / "wall.glb").stat().st_size > 0


def test_cli_reports_crash_code(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    use_child_func(monkeypatch, child_helpers.exit_hard)
    assert main([str(wall_ifc), "-d", str(tmp_path)]) == 1
    assert "Umwandlung abgestürzt (Code 3)" in capsys.readouterr().err


def test_cli_failure_keeps_a_file_that_existed_before(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    use_child_func(monkeypatch, child_helpers.raise_error)
    existing = tmp_path / "haus.glb"
    existing.write_text("alt")
    assert main([str(wall_ifc), "-o", str(existing)]) == 1
    assert "wall.ifc ist kaputt" in capsys.readouterr().err
    assert existing.read_text() == "alt"


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs file permissions")
def test_cli_refuses_an_unwritable_output_folder_before_converting(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    use_child_func(monkeypatch, child_helpers.raise_error)
    read_only = tmp_path / "ro"
    read_only.mkdir()
    read_only.chmod(0o555)
    try:
        assert main([str(wall_ifc), "-d", str(read_only)]) == 1
        err = capsys.readouterr().err
        assert "In den Ausgabeordner " in err and "Permission denied" in err
        assert "Interner Fehler" not in err
        assert "ist kaputt" not in err  # the child was never started
    finally:
        read_only.chmod(0o755)


def test_cli_cancel_message_follows_the_language(capsys):
    from ifc_converter import i18n

    i18n.set_language("en")
    assert i18n.tr("cancelled") == "cancelled"
    i18n.set_language("de")
    assert i18n.tr("cancelled") == "abgebrochen"


@posix_only
def test_session_continues_after_killed_conversion(wall_ifc, tmp_path, monkeypatch):
    use_child_func(monkeypatch, child_helpers.killed_if_named_crash)
    crash = tmp_path / "crash.ifc"
    crash.write_text("x")
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    terminal = FakeTerminal()
    monkeypatch.setattr(sys, "stdout", terminal)
    lines = iter([f"'{crash}' '{wall_ifc}'", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))

    assert interactive.run(output_dir=desktop) == 0
    text = terminal.getvalue()
    assert f"✗ Fehler bei crash.ifc: {process.MEMORY_MESSAGE}" in text
    assert "\r    IFC wird gelesen …" in text and "\r    100 %" in text
    assert "✓ Fertig" in text
    assert not (desktop / "crash.glb").exists()
    assert (desktop / "wall.glb").exists()


def test_progress_line_pads_dedupes_and_clears():
    terminal = FakeTerminal()
    line = interactive.ProgressLine("a: ", terminal)
    line.show("IFC wird gelesen …")
    line.percent(5)
    line.percent(5)
    line.clear()
    line.clear()
    width = len("a: IFC wird gelesen …")
    assert terminal.getvalue() == (
        "\ra: IFC wird gelesen …" + "\r" + "a: 5 %".ljust(width) + "\r" + " " * width + "\r"
    )


def test_progress_line_is_silent_without_a_terminal():
    stream = io.StringIO()
    line = interactive.ProgressLine("a: ", stream)
    line.show("IFC wird gelesen …")
    line.percent(50)
    line.clear()
    assert stream.getvalue() == ""
    assert not interactive.ProgressLine(stream=None).enabled or sys.stdout.isatty()


def test_cli_shows_skipped_elements(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    use_child_func(monkeypatch, child_helpers.report_skipped)
    assert main([str(wall_ifc), "-d", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out.rstrip().endswith("(1 elements, 3 without geometry)")
    assert f"⚠ wall.ifc: 3 Bauteile ohne Geometrie. {interactive.SKIPPED_HINT}" in captured.err


def test_cli_without_skipped_elements_has_no_hint(wall_ifc, tmp_path, capsys):
    from ifc_converter.cli import main

    assert main([str(wall_ifc), "-d", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out.rstrip().endswith("(1 elements)")
    assert "Geometrie" not in captured.err


def test_session_shows_skipped_elements(wall_ifc, tmp_path, monkeypatch, capsys):
    use_child_func(monkeypatch, child_helpers.report_skipped)
    lines = iter([f"'{wall_ifc}'", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert interactive.run(output_dir=tmp_path) == 0
    out = capsys.readouterr().out
    assert "(1 Bauteile, 3 ohne Geometrie)" in out
    assert f"  ⚠ 3 Bauteile ohne Geometrie. {interactive.SKIPPED_HINT}" in out


def test_skipped_warning_texts():
    assert interactive.skipped_warning(0) == ""
    assert interactive.skipped_warning(1).startswith("1 Bauteil ohne Geometrie. Diese Bauteile")
    assert interactive.skipped_warning(3).startswith("3 Bauteile ohne Geometrie. ")


@posix_only
def test_cli_retries_kernel_crash_with_opencascade(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    use_child_func(monkeypatch, child_helpers.segfault_unless_opencascade)
    assert main([str(wall_ifc), "-f", "glb", "-d", str(tmp_path / "out")]) == 0
    captured = capsys.readouterr()
    assert f"⚠ wall.ifc: {process.RETRY_MESSAGE}" in captured.err
    assert "✓ " in captured.out and (tmp_path / "out" / "wall.glb").stat().st_size > 0


@posix_only
def test_cli_kernel_flag_opencascade_disables_retry(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    # main() puts --kernel into the environment for the child processes; undo that afterwards.
    monkeypatch.setenv("IFC_CONVERTER_KERNEL", "")
    use_child_func(monkeypatch, child_helpers.always_segfault)
    assert main([str(wall_ifc), "-d", str(tmp_path), "--kernel", "opencascade"]) == 1
    captured = capsys.readouterr()
    assert "Absturz im schnellen" not in captured.err
    assert "Umwandlung abgestürzt: Speicherzugriffsfehler (Code -11)" in captured.err


@posix_only
def test_session_retries_kernel_crash(wall_ifc, tmp_path, monkeypatch):
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    use_child_func(monkeypatch, child_helpers.segfault_unless_opencascade)
    terminal = FakeTerminal()
    monkeypatch.setattr(sys, "stdout", terminal)
    lines = iter([f"'{wall_ifc}'", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert interactive.run(output_dir=tmp_path) == 0
    text = terminal.getvalue()
    retry = text.index(f"  ⚠ {process.RETRY_MESSAGE}")
    # The progress line starts over with reading after the retry message.
    assert text.index("\r    IFC wird gelesen …", retry) < text.index("✓ Fertig")
    assert (tmp_path / "wall.glb").exists()


def test_output_files_include_side_and_temp_files(tmp_path):
    target = tmp_path / "a.glb"
    assert interactive.output_files(target, "glb") == [
        target, tmp_path / "a.glb.indices.tmp", tmp_path / "a.glb.vertices.tmp",
    ]
    assert interactive.output_files(tmp_path / "a.obj", "obj") == [tmp_path / "a.obj", tmp_path / "a.mtl"]
    assert interactive.output_files(tmp_path / "a.3dm", "3dm") == [tmp_path / "a.3dm"]


@posix_only
def test_cli_removes_glb_temp_files_after_crash(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    use_child_func(monkeypatch, child_helpers.leave_glb_temp_files_and_segfault)
    assert main([str(wall_ifc), "-f", "glb", "-d", str(tmp_path / "out")]) == 1
    assert list((tmp_path / "out").iterdir()) == []


def test_cli_version(capsys):
    from ifc_converter import __version__
    from ifc_converter.cli import main

    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.strip() == f"ifc-convert {__version__}"


def _record_child_calls(monkeypatch):
    calls = []

    def fake(source, target, fmt, threads=None, progress=None, low_priority=True, **options):
        calls.append({"threads": threads, "low_priority": low_priority})
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text("fake")
        return process.ConversionResult(output=Path(target), elements=1)

    monkeypatch.setattr(interactive, "convert_in_child", fake)
    return calls


def test_cli_converts_at_low_priority_unless_told_otherwise(wall_ifc, tmp_path, monkeypatch):
    from ifc_converter.cli import main

    calls = _record_child_calls(monkeypatch)
    assert main([str(wall_ifc), "-d", str(tmp_path)]) == 0
    assert main([str(wall_ifc), "-d", str(tmp_path), "--normal-priority", "-j", "3"]) == 0
    assert calls == [{"threads": None, "low_priority": True}, {"threads": 3, "low_priority": False}]


def test_cli_logs_only_when_run_from_the_command_line(wall_ifc, tmp_path, monkeypatch):
    from ifc_converter import app
    from ifc_converter.cli import main

    child_helpers.isolate_user_dirs(monkeypatch, tmp_path)
    _record_child_calls(monkeypatch)
    log = tmp_path / "logs" / "ifc-converter.log"
    assert main([str(wall_ifc), "-d", str(tmp_path / "a")]) == 0  # called from Python code
    assert not log.exists()

    monkeypatch.setattr(sys, "argv", ["ifc-convert", str(wall_ifc), "-d", str(tmp_path / "b")])
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))  # main() clears out stale temp files
    handlers = {name: signal.getsignal(getattr(signal, name)) for name in ("SIGTERM", "SIGBREAK") if hasattr(signal, name)}
    try:
        assert main() == 0
    finally:
        app.stop_logging()
        for name, handler in handlers.items():
            signal.signal(getattr(signal, name), handler)
    assert "gestartet (CLI)" in log.read_text(encoding="utf-8")


def test_frozen_child_start_does_not_parse_its_arguments(monkeypatch):
    """A frozen app starts itself for the conversion child; freeze_support() must run first."""
    from ifc_converter import cli

    calls = []
    monkeypatch.setattr(cli.multiprocessing, "freeze_support", lambda: calls.append("freeze_support") or sys.exit(0))
    with pytest.raises(SystemExit):
        cli.main(["--multiprocessing-fork", "parent_pid=1", "pipe_handle=2"])
    assert calls == ["freeze_support"]


def test_desktop_dir_is_not_created(monkeypatch, tmp_path):
    monkeypatch.setattr(interactive.os, "name", "posix")
    monkeypatch.setattr(interactive.Path, "home", lambda: tmp_path)

    def no_xdg(*args, **kwargs):
        raise OSError("no xdg-user-dir")

    monkeypatch.setattr(interactive.subprocess, "run", no_xdg)
    assert interactive.desktop_dir() == tmp_path / "Desktop"
    assert not (tmp_path / "Desktop").exists()


def test_session_creates_the_output_folder_only_for_a_conversion(wall_ifc, tmp_path, monkeypatch, capsys):
    out = tmp_path / "Desktop"
    _record_child_calls(monkeypatch)
    lines = iter(["foo.txt", str(wall_ifc)])

    def fake_input(prompt):
        try:
            line = next(lines)
        except StopIteration:
            raise EOFError from None
        if line == str(wall_ifc):
            assert not out.exists()
        return line

    monkeypatch.setattr("builtins.input", fake_input)
    assert interactive.run("glb", out) == 0
    assert (out / "wall.glb").exists()


def test_element_labels_are_split_into_class_globalid_and_name():
    from ifc_converter.interactive import split_label

    assert split_label("IfcCovering 2ZLyRk6BAL6bNsO1TmDoEc „Belag 2 cm“") == (
        "IfcCovering", "2ZLyRk6BAL6bNsO1TmDoEc", "Belag 2 cm")
    assert split_label("IfcWall 1hqIFTRjfV6AWq_bMtnZwI") == ("IfcWall", "1hqIFTRjfV6AWq_bMtnZwI", "")
    assert split_label("#4711") == ("", "#4711", "")


def test_error_messages_are_german_and_internal_errors_marked():
    from ifc_converter.interactive import error_message, failure_hint, is_internal_error

    internal = process.ConversionFailed("KeyError", "'Name'")
    assert error_message(internal) == "Interner Fehler (KeyError): 'Name'"
    assert is_internal_error(internal)
    assert error_message(process.ConversionFailed("KeyError", "")) == "Interner Fehler (KeyError)"
    assert failure_hint(True) == "Bitte die Logdatei (Hilfe → Logdatei öffnen) mitschicken, wenn Sie den Fehler melden."

    user = process.ConversionFailed("ValueError", "Die Datei enthält keine Bauteile mit Geometrie.")
    assert error_message(user) == "Die Datei enthält keine Bauteile mit Geometrie."
    assert not is_internal_error(user)
    assert failure_hint(False, "C:\\log.txt") == "Details in der Logdatei (C:\\log.txt)."

    broken = process.ConversionFailed("Error", "Unable to parse IFC SPF header")
    assert error_message(broken).startswith("Die Datei ließ sich nicht als IFC lesen (beschädigt oder keine IFC-Datei)")
    assert not is_internal_error(broken)
    disk = process.ConversionFailed("PermissionError", "[Errno 13] Permission denied: 'x.3dm'")
    assert error_message(disk) == "Datei- oder Netzwerkfehler: [Errno 13] Permission denied: 'x.3dm'"
    assert error_message(process.ConversionFailed("MemoryError", "")) == "Der Arbeitsspeicher hat nicht gereicht"
    crash = process.ConversionCrashed(3)
    assert error_message(crash) == str(crash) and not is_internal_error(crash)
    assert error_message(ValueError("Nicht unterstütztes Format")) == "Nicht unterstütztes Format"
    assert is_internal_error(TypeError("x"))


def test_converter_errors_are_german(tmp_path):
    from ifc_converter.converter import convert

    with pytest.raises(FileNotFoundError, match="^IFC-Datei nicht gefunden: "):
        convert(tmp_path / "fehlt.ifc")
    with pytest.raises(ValueError, match="^Nicht unterstütztes Format „stl“, möglich sind: glb, obj, 3dm, dae$"):
        convert(tmp_path / "fehlt.ifc", fmt="stl")
    with pytest.raises(ValueError, match="^Nicht unterstützte Geometrieart „nurbs“"):
        convert(tmp_path / "fehlt.ifc", geometry="nurbs")
    with pytest.raises(ValueError, match="^Unbekannter Geometriekern „cgal“"):
        convert(tmp_path / "fehlt.ifc", kernel="cgal")


def test_cli_marks_internal_errors_and_says_where_the_log_is(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    child_helpers.isolate_user_dirs(monkeypatch, tmp_path)
    use_child_func(monkeypatch, child_helpers.raise_bare_error)
    assert main([str(wall_ifc), "-d", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert f"✗ {wall_ifc}: Interner Fehler (KeyError)" in err
    assert f"Bitte die Logdatei ({tmp_path / 'logs' / 'ifc-converter.log'}) mitschicken" in err


def test_resource_text():
    from ifc_converter.interactive import resource_text

    cores = process.cpu_count()
    assert resource_text(1, True) == (
        f"bis zu 1 Thread (von {cores} logischen Kernen), niedrige Priorität – andere Programme haben Vorrang")
    assert resource_text(6, False, workers=3) == (
        f"bis zu 6 Threads (von {cores} logischen Kernen), bei großen 3DM-Modellen dazu bis zu 3 Hilfsprozesse "
        "für die Rhino-Geometrie, normale Priorität")


def test_session_cancels_the_running_file_on_ctrl_c(wall_ifc, tmp_path, monkeypatch, capsys):
    calls = []

    def interrupted(source, target, fmt, *args, **kwargs):
        calls.append(source)
        raise KeyboardInterrupt

    monkeypatch.setattr(interactive, "convert_in_child", interrupted)
    lines = iter([f"'{wall_ifc}' '{wall_ifc.parent}'", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert interactive.run(output_dir=tmp_path / "out") == 0
    out = capsys.readouterr().out
    assert "■ Abgebrochen: wall.ifc (1 weitere nicht umgewandelt)" in out
    assert len(calls) == 1  # the other file was not started, and the session went on to "q"
    assert "Rechenleistung: bis zu" in out


def _child_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_cli_cancelled_by_signal_cleans_up(wall_ifc, tmp_path):
    """SIGTERM (Ctrl+Break on Windows) stops the conversion and leaves no temp files or partial output."""
    temp = tmp_path / "temp"
    temp.mkdir()
    target = tmp_path / "out" / "wall.glb"
    target.parent.mkdir()
    code = (
        "import sys; from functools import partial; import child_helpers; "
        "from ifc_converter import cli, interactive, process; "
        "interactive.convert_in_child = partial(process.convert_in_child, func=child_helpers.sleep_while_reading); "
        "sys.argv = ['ifc-convert', sys.argv[1], '-o', sys.argv[2], '-f', 'glb']; sys.exit(cli.main())"
    )
    env = {
        **os.environ, "TMPDIR": str(temp), "TEMP": str(temp), "TMP": str(temp),
        "XDG_STATE_HOME": str(tmp_path / "state"), "LOCALAPPDATA": str(tmp_path / "local"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"), "APPDATA": str(tmp_path / "roaming"),
        "PYTHONPATH": os.pathsep.join([str(Path(__file__).parent), *sys.path]),
    }
    windows = sys.platform == "win32"
    command = [sys.executable, "-c", code, str(wall_ifc), str(target)]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0
    cli_process = subprocess.Popen(command, env=env, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                   creationflags=flags)
    pid_file = target.with_suffix(".pid")
    deadline = time.monotonic() + 60
    while not pid_file.exists() and time.monotonic() < deadline and cli_process.poll() is None:
        time.sleep(0.05)
    assert pid_file.exists(), "the conversion child did not start"
    time.sleep(0.3)
    assert list(temp.glob("ifc-converter-*")), "the conversion made no temp files"
    cli_process.send_signal(signal.CTRL_BREAK_EVENT if windows else signal.SIGTERM)
    try:
        _, err = cli_process.communicate(timeout=30)
    finally:
        cli_process.kill()
    assert cli_process.returncode == 130, err
    assert f"■ {wall_ifc}: abgebrochen" in err
    assert not target.exists()
    assert not list(temp.glob("ifc-converter-*"))
    if not windows:
        child = int(pid_file.read_text())
        deadline = time.monotonic() + 10
        while _child_alive(child) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _child_alive(child)


# ------------------------------------------------------------ 0.6.0 Nur Gebäudehülle


def test_inside_text():
    assert interactive.inside_text(1) == "1 innen liegendes weggelassen"
    assert interactive.inside_text(2431) == "2.431 innen liegende weggelassen"


def _record_child_options(monkeypatch, inside=0):
    calls = []

    def fake(source, target, fmt, threads=None, progress=None, low_priority=True, **options):
        calls.append(options)
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text("fake")
        return process.ConversionResult(output=Path(target), elements=1, inside=inside)

    monkeypatch.setattr(interactive, "convert_in_child", fake)
    return calls


def test_cli_envelope_flag_reaches_the_child_and_the_inside_count_is_printed(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import build_parser, main

    assert "--envelope, --hull" in build_parser().format_help()
    calls = _record_child_options(monkeypatch, inside=5)
    assert main([str(wall_ifc), "-d", str(tmp_path)]) == 0
    assert main([str(wall_ifc), "-d", str(tmp_path), "--envelope"]) == 0
    assert main([str(wall_ifc), "-d", str(tmp_path), "-f", "3dm", "--hull"]) == 0
    assert [options.get("envelope") for options in calls] == [None, True, True]
    assert [options.get("blocks") for options in calls] == [None, None, None]
    lines = capsys.readouterr().out.rstrip().splitlines()
    assert all(line.endswith("(1 elements, 5 inside left out)") for line in lines)


def test_cli_converts_only_the_hull(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter.cli import main

    use_child_func(monkeypatch, child_helpers.convert_only_hull)
    assert main([str(wall_ifc), "-d", str(tmp_path), "--hull"]) == 0
    captured = capsys.readouterr()
    assert captured.out.rstrip().endswith("wall.glb (1 elements, 2 inside left out)")
    assert (tmp_path / "wall.glb").stat().st_size > 0
    assert "Geometrie" not in captured.err


def test_session_summary_names_the_inside_count(wall_ifc, tmp_path, monkeypatch, capsys):
    calls = _record_child_options(monkeypatch, inside=5)
    lines = iter([f"'{wall_ifc}'", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert interactive.run(output_dir=tmp_path, envelope=True) == 0
    assert calls == [{"geometry": "brep", "on_retry": calls[0]["on_retry"], "status": calls[0]["status"],
                      "envelope": True}]
    out = capsys.readouterr().out
    assert "  Nur Gebäudehülle: innen liegende Bauteile" in out
    assert "(1 Bauteile, 5 innen liegende weggelassen)" in out


def test_session_without_the_option_says_nothing_of_the_hull(wall_ifc, tmp_path, monkeypatch, capsys):
    calls = _record_child_options(monkeypatch)
    lines = iter([f"'{wall_ifc}'", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert interactive.run(output_dir=tmp_path) == 0
    assert "envelope" not in calls[0]
    assert "Gebäudehülle" not in capsys.readouterr().out


def test_progress_line_shows_the_envelope_phase():
    terminal = FakeTerminal()
    line = interactive.ProgressLine("a: ", stream=terminal)
    line.percent(10)
    line.phase("envelope", "Gebäudehülle wird bestimmt (Geometrie grob vorberechnet) …")
    assert terminal.getvalue().endswith("\ra: 10 % – Gebäudehülle wird bestimmt (Geometrie grob vorberechnet) …")
    line.phase("geometry", "Geometrie wird berechnet (4 Threads) …")
    line.percent(30)
    assert terminal.getvalue().rstrip().endswith("\ra: 30 %")


# ----------------------------------------------------------------------------- English texts
# The helpers the window and the command line share follow the user-interface language (i18n);
# the tests above run in German (conftest), these switch to English.


@pytest.fixture
def english():
    from ifc_converter import i18n

    i18n.set_language("en")
    yield
    i18n.set_language("de")


def test_helper_texts_in_english(english):
    cores = process.cpu_count()
    assert interactive.skipped_count(1) == "1 element without geometry"
    assert interactive.skipped_count(3) == "3 elements without geometry"
    assert interactive.skipped_warning(3).startswith("3 elements without geometry. These elements have geometry")
    assert interactive.SKIPPED_HINT.startswith("These elements have geometry")
    assert interactive.inside_text(1) == "1 interior element left out"
    assert interactive.inside_text(2431) == "2,431 interior elements left out"
    assert interactive.number_text(117137) == "117,137" and interactive.number_text(999) == "999"
    assert interactive.number_text(1234567) == "1,234,567" and interactive.number_text(-1000) == "-1,000"
    assert interactive.duration_text(12.34) == "12.3 s" and interactive.duration_text(3122) == "52 min 2 s"
    assert interactive.duration_text(3900) == "1 h 5 min"
    assert interactive.resource_text(1, True) == (
        f"up to 1 thread (of {cores} logical cores), low priority – other programs take precedence")
    assert interactive.resource_text(6, False, workers=3) == (
        f"up to 6 threads (of {cores} logical cores), plus up to 3 helper processes for the Rhino geometry "
        "with large 3DM models, normal priority")
    assert interactive.crashed_warning(["IfcWall 2O2Fr$t4X7Zf8NOew3FLOH „Wand“"]) == (
        "1 element skipped because the geometry kernel crashed or hung on it: IfcWall 2O2Fr$t4X7Zf8NOew3FLOH „Wand“. "
        "In the CAD program it can be found by its GlobalId.")
    many = interactive.crashed_warning([f"IfcWall {n:022d}" for n in range(12)])
    assert many.startswith("12 elements skipped because the geometry kernel crashed or hung on them: IfcWall 00")
    assert " … and 2 more (all of them in the log file). In the CAD program they can be found" in many


def test_error_texts_in_english(english):
    from ifc_converter.interactive import error_message, failure_hint

    assert error_message(process.ConversionFailed("KeyError", "'Name'")) == "Internal error (KeyError): 'Name'"
    assert error_message(process.ConversionFailed("KeyError", "")) == "Internal error (KeyError)"
    assert error_message(process.ConversionFailed("MemoryError", "")) == "There was not enough memory"
    assert error_message(process.ConversionFailed("Error", "Unable to parse")) == (
        "The file could not be read as IFC (damaged or not an IFC file): Unable to parse")
    assert error_message(process.ConversionFailed("PermissionError", "[Errno 13] Permission denied: 'x.3dm'")) == (
        "File or network error: [Errno 13] Permission denied: 'x.3dm'")
    assert failure_hint(True) == "Please attach the log file (Help → Open log file) when reporting the error."
    assert failure_hint(False, "C:\\log.txt") == "Details are in the log file (C:\\log.txt)."


def test_german_helper_texts_are_the_old_ones():
    # The fixture in conftest switches to German: the texts asserted all over this file.
    assert interactive.duration_text(12.34) == "12,3 s"
    assert interactive.number_text(1234567) == "1.234.567"


def test_cli_lang_flag_sets_the_language_before_anything_runs(wall_ifc, tmp_path, monkeypatch, capsys):
    from ifc_converter import i18n
    from ifc_converter.cli import main

    use_child_func(monkeypatch, child_helpers.report_skipped)
    assert main([str(wall_ifc), "-d", str(tmp_path), "--lang", "en"]) == 0
    err = capsys.readouterr().err
    assert "⚠ wall.ifc: 3 elements without geometry. These elements have geometry" in err
    assert i18n.language() == "en" and os.environ[i18n.ENV] == "en"  # the child processes inherit it

    assert main([str(wall_ifc), "-d", str(tmp_path / "de"), "--lang", "de"]) == 0
    assert "⚠ wall.ifc: 3 Bauteile ohne Geometrie." in capsys.readouterr().err
    assert i18n.language() == "de"


def test_cli_lang_defaults_to_the_environment(monkeypatch):
    from ifc_converter.cli import build_parser

    monkeypatch.setenv("IFC_CONVERTER_LANG", "fr")
    assert build_parser().parse_args([]).lang == "fr"
    monkeypatch.setenv("IFC_CONVERTER_LANG", "klingon")
    assert build_parser().parse_args([]).lang == "en"
    monkeypatch.delenv("IFC_CONVERTER_LANG")
    assert build_parser().parse_args([]).lang == "en"
    assert build_parser().parse_args(["--lang", "pl"]).lang == "pl"
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--lang", "xx"])
