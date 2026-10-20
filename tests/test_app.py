import logging
import re
import struct
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from child_helpers import isolate_user_dirs
from ifc_converter import __version__, app

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "src" / "ifc_converter" / "resources"


@pytest.fixture
def user_dirs(monkeypatch, tmp_path):
    isolate_user_dirs(monkeypatch, tmp_path)
    yield tmp_path
    app.stop_logging()


def test_version_comes_from_pyproject():
    match = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.MULTILINE)
    assert __version__ == match.group(1)


def test_folders_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert app.settings_path() == tmp_path / "Roaming" / "IFC Converter" / "settings.ini"
    assert app.log_dir() == tmp_path / "Local" / "IFC Converter" / "logs"


def test_folders_on_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(app.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert app.settings_path() == tmp_path / "config" / "ifc-converter" / "settings.ini"
    assert app.log_dir() == tmp_path / "state" / "ifc-converter" / "logs"
    monkeypatch.delenv("XDG_STATE_HOME")
    assert app.log_dir() == Path.home() / ".local" / "state" / "ifc-converter" / "logs"


def test_log_file_gets_start_line_versions_and_messages(user_dirs):
    path = app.setup_logging("Test")
    assert path == user_dirs / "logs" / "ifc-converter.log"
    logging.getLogger("ifc_converter.test").warning("eine Warnung")
    text = path.read_text(encoding="utf-8")
    assert f"IFC Converter {__version__} gestartet (Test)" in text
    assert "IfcOpenShell" in text and "rhino3dm" in text
    assert "WARNING" in text and "eine Warnung" in text


def test_log_file_is_small_and_rotates(user_dirs):
    path = app.setup_logging("Test")
    handler = next(h for h in logging.getLogger().handlers if getattr(h, "baseFilename", None) == str(path))
    assert handler.maxBytes <= 1_000_000 and handler.backupCount <= 3
    filler = "x" * 2000
    for _ in range(2500):  # 5 MB: more than the file and its backups hold
        logging.getLogger("ifc_converter.test").info(filler)
    files = sorted(p.name for p in path.parent.iterdir())
    assert files == ["ifc-converter.log", "ifc-converter.log.1", "ifc-converter.log.2", "ifc-converter.log.3"]
    assert all(p.stat().st_size <= 1_010_000 for p in path.parent.iterdir())


def test_setting_up_again_replaces_the_handler(user_dirs):
    app.setup_logging("A")
    app.setup_logging("B")
    ours = [h for h in logging.getLogger().handlers if getattr(h, "baseFilename", "").endswith("ifc-converter.log")]
    assert len(ours) == 1


def test_unwritable_log_folder_is_no_error(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    monkeypatch.setattr(app, "log_dir", lambda: blocker / "logs")
    assert app.setup_logging("Test") is None


def test_uncaught_exceptions_are_logged_and_reported(user_dirs, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    path = app.setup_logging("Test")
    reports = []
    app.install_exception_hooks(lambda summary, details: reports.append((summary, details)))

    try:
        raise ValueError("kaputt")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    thread = threading.Thread(target=lambda: 1 / 0, name="Rechner")
    thread.start()
    thread.join()

    assert reports[0][0] == "ValueError: kaputt"
    assert "Traceback" in reports[0][1] and __version__ in reports[0][1]
    assert reports[1][0] == "ZeroDivisionError: division by zero"
    text = path.read_text(encoding="utf-8")
    assert "Unerwarteter Fehler:" in text and "ValueError: kaputt" in text
    assert "Unerwarteter Fehler im Thread Rechner" in text


def test_a_failing_report_is_only_logged(user_dirs, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    path = app.setup_logging("Test")

    def broken(summary, details):
        raise RuntimeError("Dialog kaputt")

    app.install_exception_hooks(broken)
    try:
        raise ValueError("erster Fehler")
    except ValueError:
        sys.excepthook(*sys.exc_info())  # must not raise
    assert "Fehlerdialog konnte nicht angezeigt werden" in path.read_text(encoding="utf-8")


def test_component_versions():
    import PySide6.QtCore  # noqa: F401 - loaded, as in the GUI

    versions = app.component_versions()
    assert versions["IFC Converter"] == __version__
    for name in ("Python", "IfcOpenShell", "rhino3dm", "Qt", "PySide6", "NumPy", "System"):
        assert versions[name] and versions[name] != "nicht verfügbar"


def test_component_versions_do_not_load_qt():
    # The command line logs the versions too; that must not pull all of Qt into every conversion.
    code = (
        "import sys; from ifc_converter import app; versions = app.component_versions(); "
        "assert 'PySide6.QtCore' not in sys.modules and 'Qt' not in versions, versions"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_icon_files_exist_with_all_sizes():
    assert (RESOURCES / "icon.svg").read_text().startswith("<svg")
    png = (RESOURCES / "icon.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (256, 256)
    ico = (RESOURCES / "icon.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", ico[:6])
    assert (reserved, kind) == (0, 1)
    sizes = {ico[6 + 16 * i] or 256 for i in range(count)}
    assert {16, 24, 32, 48, 256} <= sizes


def test_component_versions_say_not_available_in_the_language(monkeypatch):
    from ifc_converter import i18n

    monkeypatch.setitem(sys.modules, "rhino3dm", None)  # import fails
    assert app.component_versions()["rhino3dm"] == "nicht verfügbar"
    i18n.set_language("en")
    try:
        assert app.component_versions()["rhino3dm"] == "not available"
    finally:
        i18n.set_language("de")
