import io
import re
import sys
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
