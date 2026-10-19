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


# ---- Linux build, tar.gz and release -------------------------------------------------------------

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tomllib  # noqa: E402

import build  # noqa: E402
import release_notes  # noqa: E402

LINUX = sys.platform == "linux"
LINUX_FILES = PACKAGING / "linux"

CHANGELOG = """# Änderungen

## 0.5.0 – 2026-10-19

- Linux-Version als tar.gz mit install.sh.
- Fenster: Vorschau schneller.

## 0.4.1 – 2026-10-19

- Älteres.
"""


def test_release_notes_are_the_newest_changelog_section_plus_the_download_line():
    heading, body = release_notes.top_section(CHANGELOG)
    assert heading == "0.5.0 – 2026-10-19"
    assert body == "- Linux-Version als tar.gz mit install.sh.\n- Fenster: Vorschau schneller."
    notes = release_notes.release_notes(CHANGELOG, "0.5.0")
    assert notes.startswith(body + "\n\n**Download:**")
    for name in ("IFC-Converter-0.5.0-Setup.exe", "IFC-Converter-0.5.0-portable.zip",
                 "IFC-Converter-0.5.0-linux-x86_64.tar.gz", "SHA256SUMS.txt"):
        assert name in notes
    assert "0.4.1" not in notes and "## " not in notes


def test_release_notes_refuse_the_wrong_version_and_placeholders():
    with pytest.raises(ValueError, match="is '0.5.0', not 0.4.1"):
        release_notes.release_notes(CHANGELOG, "0.4.1")
    placeholder = CHANGELOG.replace("- Linux-Version als tar.gz mit install.sh.\n- Fenster: Vorschau schneller.",
                                    release_notes.PLACEHOLDER)
    with pytest.raises(ValueError, match="placeholder"):
        release_notes.release_notes(placeholder, "0.5.0")
    with pytest.raises(ValueError, match="no '## ' section"):
        release_notes.top_section("# nothing\n")
    result = subprocess.run([sys.executable, str(PACKAGING / "release_notes.py"), "missing.md"],
                            capture_output=True, text=True, cwd=PACKAGING)
    assert result.returncode != 0 and "release notes:" in result.stderr


def test_changelog_newest_section_is_this_or_a_newer_version():
    """The release job takes the newest section for the tag's version; a forgotten CHANGELOG fails it."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    heading, _ = release_notes.top_section(changelog)
    newest = release_notes.section_version(heading)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert newest, heading
    assert tuple(int(n) for n in newest.split(".")[:3]) >= tuple(int(n) for n in project.split(".")[:3])


def test_workflow_builds_tests_and_releases_the_linux_app():
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    yaml = pytest.importorskip("yaml")
    jobs = yaml.safe_load(workflow)["jobs"]
    linux = jobs["build-linux"]
    assert linux["runs-on"] == "ubuntu-latest"
    runs = " ".join(step.get("run", "") for step in linux["steps"])
    assert "python packaging/build.py" in runs
    assert "python packaging/smoke_test_linux.py dist/ifc-converter --gui --tarball" in runs
    uploads = [step for step in linux["steps"] if "upload-artifact" in step.get("uses", "")]
    assert uploads[-1]["with"]["name"] == "IFC-Converter-linux"
    assert "tar.gz" in uploads[-1]["with"]["path"] and "SHA256SUMS.txt" in uploads[-1]["with"]["path"]
    # The Windows job is untouched and still uploads its artifact under the old name.
    windows_uploads = [step for step in jobs["build-windows"]["steps"] if "upload-artifact" in step.get("uses", "")]
    assert windows_uploads[-1]["with"]["name"] == "IFC-Converter-windows"
    release = jobs["release"]
    assert set(release["needs"]) == {"test", "build-windows", "build-linux"}
    downloads = [step["with"]["name"] for step in release["steps"] if "download-artifact" in step.get("uses", "")]
    assert downloads == ["IFC-Converter-windows", "IFC-Converter-linux"]
    runs = " ".join(step.get("run", "") for step in release["steps"])
    assert "sha256sum -c SHA256SUMS.txt" in runs and "sha256sum -- * > SHA256SUMS.txt" in runs
    assert 'packaging/release_notes.py CHANGELOG.md --version "${GITHUB_REF_NAME#v}"' in runs
    assert "--notes-file notes.md" in runs and "--notes " not in runs
    assert "gh release create" in runs and "release/*" in runs


def test_spec_and_build_agree_on_the_linux_names():
    spec = (PACKAGING / "ifc_converter.spec").read_text(encoding="utf-8")
    assert 'APP_DIR_NAME = APP_NAME if WINDOWS else "ifc-converter"' in spec
    assert 'GUI_EXE_NAME = APP_NAME if WINDOWS else "ifc-converter"' in spec
    assert 'name="ifc-convert"' in spec
    assert build.APP_DIR_NAME == ("IFC Converter" if sys.platform == "win32" else "ifc-converter")
    # The desktop platform plugins stay; only the display-server-less ones go.
    unneeded = re.search(r"UNNEEDED_LINUX_BINARIES = \{(.*?)\}", spec, re.DOTALL).group(1)
    for keep in ("libqxcb.so", "libqwayland.so", "libqoffscreen.so", "libqt6opengl"):
        assert keep not in unneeded
    assert "libqeglfs.so" in unneeded and "libqvnc.so" in unneeded
    for name in build.LINUX_FILES:
        assert (LINUX_FILES / name).is_file(), name


def test_linux_desktop_file_and_mime_type_match():
    desktop = (LINUX_FILES / "ifc-converter.desktop").read_text(encoding="utf-8")
    mime = (LINUX_FILES / "ifc-converter.xml").read_text(encoding="utf-8")
    assert 'type="application/x-ifc"' in mime and '<glob pattern="*.ifc"/>' in mime
    assert "MimeType=application/x-ifc;" in desktop
    assert "Exec=ifc-converter %F" in desktop and "Icon=ifc-converter" in desktop
    assert "Name=IFC Converter" in desktop
    if shutil.which("desktop-file-validate"):
        result = subprocess.run(["desktop-file-validate", str(LINUX_FILES / "ifc-converter.desktop")],
                                capture_output=True, text=True)
        assert result.returncode == 0 and not result.stdout, result.stdout + result.stderr


def test_icon_png_for_linux():
    png = build.icon_png()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    # Also from the .ico alone (the way it works when there is no icon.png next to it).
    data = build.icon().read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00"


def _fake_tarball_folder(folder: Path) -> None:
    """The layout of the tar.gz with copies of ``sleep`` instead of the real program.

    Real binaries, not scripts: the scripts detect a running program by /proc/<pid>/exe, which for a
    script would point at the shell.
    """
    app = folder / "ifc-converter"
    (app / "_internal").mkdir(parents=True)
    (app / "_internal" / "THIRD-PARTY-NOTICES.txt").write_text("notices\n")
    for name in ("ifc-converter", "ifc-convert"):
        shutil.copy(shutil.which("sleep"), app / name)
        (app / name).chmod(0o755)
    for name in build.LINUX_FILES:
        shutil.copy(LINUX_FILES / name, folder / name)
    (folder / "ifc-converter.png").write_bytes(build.icon_png())


def _script(folder: Path, name: str, home: Path, expect: int = 0, **env_extra: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_") and k != "IFC_CONVERTER_PREFIX"}
    env["HOME"] = str(home)
    env.update(env_extra)
    result = subprocess.run(["bash", str(folder / name)], capture_output=True, text=True, env=env, timeout=120)
    assert result.returncode == expect, f"{name}: exit {result.returncode}\n{result.stdout}{result.stderr}"
    return result.stdout + result.stderr


@pytest.mark.skipif(not LINUX, reason="install.sh and uninstall.sh are for the Linux tar.gz")
def test_linux_install_update_and_uninstall_in_a_fake_home(tmp_path):
    import smoke_test_linux

    folder = tmp_path / "IFC-Converter-9.9.9-linux-x86_64"
    _fake_tarball_folder(folder)
    home = tmp_path / "home"
    home.mkdir()
    prefix = home / ".local" / "opt" / "ifc-converter"

    # Nothing happens with an empty HOME or a relative prefix.
    assert "HOME ist leer" in _script(folder, "install.sh", home, expect=1, HOME="")
    assert "absoluter Pfad" in _script(folder, "uninstall.sh", home, expect=1, IFC_CONVERTER_PREFIX="relative/x")
    assert not (home / ".local").exists()

    output = _script(folder, "install.sh", home)
    assert "Fertig." in output
    smoke_test_linux.check_installation(home, prefix)
    link = home / ".local" / "bin" / "ifc-convert"
    assert subprocess.run([str(link), "0"], capture_output=True, text=True).returncode == 0
    # An update replaces the folder; a stray file from the old installation is gone afterwards.
    (prefix / "stale.txt").write_text("old")
    _script(folder, "install.sh", home)
    smoke_test_linux.check_installation(home, prefix)
    assert not (prefix / "stale.txt").exists()
    # Both scripts refuse while something runs from the installed folder.
    running = subprocess.Popen([str(prefix / "ifc-convert"), "30"], stdout=subprocess.DEVNULL)
    try:
        assert "läuft noch" in _script(folder, "install.sh", home, expect=1)
        assert "läuft noch" in _script(prefix, "uninstall.sh", home, expect=1)
        assert (prefix / "ifc-convert").is_file()
    finally:
        running.kill()
        running.wait(30)
    (home / ".config" / "ifc-converter").mkdir(parents=True)
    (home / ".local" / "state" / "ifc-converter").mkdir(parents=True)
    output = _script(prefix, "uninstall.sh", home)
    assert "bleiben erhalten" in output
    smoke_test_linux.check_uninstalled(home, prefix)
    # Running uninstall.sh again is harmless.
    _script(folder, "uninstall.sh", home)


def test_readme_describes_the_linux_release():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for text in ("## Installation unter Linux", "install.sh", "uninstall.sh", "linux-x86_64.tar.gz",
                 "SHA256SUMS.txt", "QT_QPA_PLATFORM", "~/.config/ifc-converter", "~/.local/state/ifc-converter",
                 "smoke_test_linux.py", "IFC-Converter-linux"):
        assert text in readme, text
