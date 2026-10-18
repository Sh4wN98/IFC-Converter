"""Consistency of the Windows packaging (installer, smoke and installer tests, workflow) with the app.

The scripts themselves only run on Windows (in GitHub Actions); this checks what can be checked anywhere.
"""

import re
import sys
import tempfile
from pathlib import Path

import pytest

from ifc_converter import app, process

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
sys.path.insert(0, str(PACKAGING))

import installer_test  # noqa: E402
import smoke_test  # noqa: E402


def installer_script() -> str:
    return (PACKAGING / "installer.iss").read_text(encoding="utf-8-sig")


def setting(name: str) -> str:
    return re.search(rf"^{name}=(.*)$", installer_script(), re.MULTILINE).group(1).strip()


def test_installer_and_app_use_the_same_mutex():
    guid = setting("AppId").strip("{")
    assert setting("AppMutex") == app.APP_MUTEX == smoke_test.APP_MUTEX
    assert app.APP_MUTEX.endswith(guid.rstrip("}"))


def test_uninstaller_removes_only_the_settings_key_of_the_old_name():
    from ifc_converter.gui import LEGACY_NAME

    script = installer_script()
    key = f"Software\\{LEGACY_NAME}\\{LEGACY_NAME}"
    assert f"LegacyKey = '{key}';" in script
    assert f"LegacyParentKey = 'Software\\{LEGACY_NAME}';" in script
    assert "RegDeleteKeyIncludingSubkeys(HKCU, LegacyKey)" in script
    assert "RegDeleteKeyIfEmpty(HKCU, LegacyParentKey)" in script  # the parent only if empty
    assert "RegDeleteKeyIncludingSubkeys(HKCU, LegacyParentKey)" not in script
    assert installer_test.LEGACY_KEY == key


def test_installer_test_knows_the_open_with_entry():
    script = installer_script()
    assert f'Subkey: "{installer_test.PROG_ID_KEY}"' in script
    assert f'Subkey: "{installer_test.OPEN_WITH_KEY}"; ValueType: string; ValueData: ""; ValueName: "{installer_test.PROG_ID}"' in script


def test_setup_version_from_the_file_name():
    assert installer_test.setup_version(Path("dist/IFC-Converter-0.2.5-Setup.exe")) == "0.2.5"
    with pytest.raises(SystemExit):
        installer_test.setup_version(Path("setup.exe"))


def test_smoke_test_knows_the_temp_files_of_conversions(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    before = smoke_test.temp_entries()
    staging = process._staging_dir()
    assert smoke_test.temp_entries() - before == {Path(staging).name}
    with pytest.raises(AssertionError, match="left files in"):
        smoke_test.check_no_leftovers(before, "test")
    Path(staging).rmdir()
    smoke_test.check_no_leftovers(before, "test")
    assert smoke_test.STALE_AGE > process.STALE_TEMP_AGE


def test_workflow_runs_the_packaging_tests():
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    assert "python packaging/smoke_test.py" in workflow
    assert "python packaging/installer_test.py" in workflow
    yaml = pytest.importorskip("yaml")
    steps = yaml.safe_load(workflow)["jobs"]["build-windows"]["steps"]
    assert any("installer_test.py" in step.get("run", "") for step in steps)


@pytest.mark.skipif(sys.platform != "win32", reason="the mutex is for the Windows installer")
def test_app_holds_the_mutex_for_the_installer():
    assert app.hold_app_mutex()
    assert smoke_test.mutex_exists()


@pytest.mark.skipif(sys.platform == "win32", reason="elsewhere than on Windows")
def test_no_mutex_outside_windows():
    assert app.hold_app_mutex() is False


def test_build_keeps_what_the_3d_preview_needs():
    spec = (PACKAGING / "ifc_converter.spec").read_text(encoding="utf-8")
    unneeded = re.search(r"^UNNEEDED_BINARIES = (.*)$", spec, re.MULTILINE).group(1)
    assert "opengl32sw.dll" not in unneeded  # Qt's software OpenGL, for machines without a usable driver
    modules = re.search(r"^PREVIEW_MODULES = (.*)$", spec, re.MULTILINE).group(1)
    for module in ("ifc_converter.viewer", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets"):
        assert f'"{module}"' in modules
    assert spec.count("PREVIEW_MODULES") == 3  # defined, and bundled with both exes
    assert "opengl32sw.dll" in smoke_test.PREVIEW_FILES and "QtOpenGLWidgets.pyd" in smoke_test.PREVIEW_FILES
    from ifc_converter import viewer

    assert viewer.RENDERER_ENV in (ROOT / "README.md").read_text(encoding="utf-8")
