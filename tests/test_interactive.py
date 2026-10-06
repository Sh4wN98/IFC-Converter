from pathlib import Path

from ifc_converter import interactive
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
