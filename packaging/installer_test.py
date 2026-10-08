"""Test the Windows installer: update, fresh install, refusal while the app runs, "Open with", uninstall.

    python packaging/installer_test.py dist/IFC-Converter-<version>-Setup.exe [--previous <older Setup.exe>]

Installs for the current user only, like a user would (silently), so it must run on a throwaway
machine such as a GitHub Actions runner: it uninstalls whatever IFC Converter is installed there and
changes the user's registry under HKCU\\Software\\Classes and HKCU\\Software\\IFC File Converter.

1. Update (with --previous): the older release is installed, a settings file is put in place, the new
   version is installed over it. The settings file must be unchanged and the updated app must run
   (one conversion and the program window, see smoke_test.py --quick).
2. Fresh install with the default tasks: Start menu entry only, no desktop icon, no "Open with" entry;
   the full smoke test with the installed app. While the program window runs, Setup and the
   uninstaller must refuse (AppMutex). Uninstalling removes the program, its shortcut and the registry
   key of the app's old name (gui.LEGACY_NAME), and then its parent key, which is empty.
3. Install with the "Open with" task: its registry entries exist and the uninstaller removes them; of
   the old name's settings it removes only that key, not other keys beside it.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
APP_NAME = "IFC Converter"
SETUP_TIMEOUT = 600
UNINSTALL_TIMEOUT = 120
# Classes key of the optional "Open with" entry and the value naming it under .ifc (installer.iss).
PROG_ID_KEY = r"Software\Classes\IFCConverter.ifc"
OPEN_WITH_KEY = r"Software\Classes\.ifc\OpenWithProgids"
PROG_ID = "IFCConverter.ifc"
# Settings of the app's earlier name (gui.LEGACY_NAME in the registry) and a key beside them that the
# uninstaller must leave alone.
LEGACY_PARENT = r"Software\IFC File Converter"
LEGACY_KEY = LEGACY_PARENT + r"\IFC File Converter"
OTHER_KEY = LEGACY_PARENT + r"\Andere Anwendung"
SETUP_NAME = re.compile(r"IFC-Converter-(.+)-Setup\.exe$")


def app_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_NAME


def settings_file() -> Path:
    return Path(os.environ["APPDATA"]) / APP_NAME / "settings.ini"


def shortcut(where: str) -> Path:
    if where == "desktop":
        return Path(os.environ["USERPROFILE"]) / "Desktop" / f"{APP_NAME}.lnk"
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk"


def setup_version(setup: Path) -> str:
    """The version in the name of an installer, e.g. "0.2.5" for IFC-Converter-0.2.5-Setup.exe."""
    match = SETUP_NAME.search(setup.name)
    if not match:
        raise SystemExit(f"{setup.name} is not named IFC-Converter-<version>-Setup.exe")
    return match.group(1)


# ------------------------------------------------------------------ registry


def key_exists(path: str) -> bool:
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, path))
    except FileNotFoundError:
        return False
    return True


def value_exists(path: str, name: str) -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return False
    return True


def default_value(path: str) -> str:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
        return str(winreg.QueryValueEx(key, "")[0])


def subkeys(path: str) -> list[str]:
    import winreg

    names = []
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
        while True:
            try:
                names.append(winreg.EnumKey(key, len(names)))
            except OSError:
                return names


def create_key(path: str, name: str, value: str) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def delete_key(path: str) -> None:
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


# ------------------------------------------------------------- processes


def tasks() -> list[str]:
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace").stdout
    return [line.split('","')[0].strip('"') for line in out.splitlines() if line.startswith('"')]


def uninstaller_running() -> bool:
    """unins000.exe restarts itself as %TEMP%\\_iu*.tmp and returns at once; this is that copy."""
    return any(name.lower() == "unins000.exe" or (name.lower().startswith("_iu") and name.lower().endswith(".tmp"))
               for name in tasks())


def show_log(path: Path) -> None:
    if path.is_file():
        print(f"--- {path.name} (end) ---")
        print("\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]))


def run_setup(setup: Path, log: Path, *options: str) -> int:
    command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={log}", *options]
    print("+", " ".join(command), flush=True)
    started = time.monotonic()
    try:
        code = subprocess.run(command, timeout=SETUP_TIMEOUT).returncode
    except subprocess.TimeoutExpired:
        show_log(log)
        raise AssertionError(f"{setup.name} did not finish within {SETUP_TIMEOUT} s") from None
    print(f"  exit code {code} after {time.monotonic() - started:.0f} s")
    return code


def install(setup: Path, log: Path, *options: str) -> None:
    code = run_setup(setup, log, *options)
    exe = app_dir() / f"{APP_NAME}.exe"
    if code != 0 or not exe.is_file():
        show_log(log)
        raise AssertionError(f"{setup.name} {' '.join(options)}: exit code {code}, {exe} exists: {exe.is_file()}")
    print(f"  installed to {app_dir()} ✓")


def run_uninstaller(log: Path) -> None:
    """Start the uninstaller silently and wait until it (and its copy in %TEMP%) has ended."""
    command = [str(app_dir() / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={log}"]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, timeout=UNINSTALL_TIMEOUT)
    deadline = time.monotonic() + UNINSTALL_TIMEOUT
    time.sleep(2)  # the copy in %TEMP% starts after the original has returned
    while uninstaller_running():
        if time.monotonic() > deadline:
            raise AssertionError(f"the uninstaller still runs after {UNINSTALL_TIMEOUT} s")
        time.sleep(1)


def uninstall(log: Path) -> None:
    run_uninstaller(log)
    exe = app_dir() / f"{APP_NAME}.exe"
    for _ in range(30):  # files of a just-ended process can stay locked for a moment
        if not exe.exists():
            break
        time.sleep(1)
    if exe.exists():
        show_log(log)
        raise AssertionError("the uninstaller left the program behind")
    if shortcut("start").exists():
        raise AssertionError("the uninstaller left the Start menu shortcut behind")
    print("  uninstalled ✓")


def smoke(*options: str) -> None:
    command = [sys.executable, str(PACKAGING / "smoke_test.py"), str(app_dir()), *options]
    print("+", " ".join(command), flush=True)
    if subprocess.run(command).returncode != 0:
        raise AssertionError(f"smoke test of the installed app failed ({' '.join(options) or 'full'})")


def installed_version() -> str:
    out = subprocess.run([str(app_dir() / "ifc-convert.exe"), "--version"], capture_output=True, text=True,
                         timeout=120).stdout.strip()
    return out.removeprefix("ifc-convert ").strip()


# ------------------------------------------------------------------ steps


def check_update(previous: Path, setup: Path, work: Path) -> None:
    print(f"== Update from {previous.name} to {setup.name}", flush=True)
    install(previous, work / "install-previous.log")
    if installed_version() != setup_version(previous):
        raise AssertionError(f"the previous release reports version {installed_version()!r}")
    settings = settings_file()
    settings.parent.mkdir(parents=True, exist_ok=True)
    marker = f"installer-test-{os.getpid()}"
    settings.write_text(f"[General]\nformat=obj\nrhino_geometry=mesh\ninstaller_test={marker}\n", encoding="utf-8")
    kept = settings.read_bytes()
    install(setup, work / "install-update.log")
    if installed_version() != setup_version(setup):
        raise AssertionError(f"after the update the app reports version {installed_version()!r}")
    if not settings.is_file() or settings.read_bytes() != kept:
        raise AssertionError(f"the update changed or removed {settings}")
    print(f"  version {setup_version(setup)}, settings file unchanged ✓")
    smoke("--quick", "--gui")
    if marker not in settings.read_text(encoding="utf-8", errors="replace"):
        raise AssertionError("the updated app lost the existing settings")
    print("  the updated app runs and keeps the settings ✓")
    uninstall(work / "uninstall-update.log")
    if not settings.is_file():
        raise AssertionError("the uninstaller removed the settings (they are kept)")
    settings.unlink()


def check_refusal_while_running(setup: Path, work: Path) -> None:
    """While the program window runs, Setup and the uninstaller refuse instead of closing it."""
    from smoke_test import mutex_exists

    gui = subprocess.Popen([str(app_dir() / f"{APP_NAME}.exe")])
    try:
        deadline = time.monotonic() + 60
        while not mutex_exists():
            if gui.poll() is not None or time.monotonic() > deadline:
                raise AssertionError("the installed program window did not start (or holds no mutex)")
            time.sleep(1)
        exe = app_dir() / f"{APP_NAME}.exe"
        before = exe.stat().st_mtime_ns
        log = work / "install-while-running.log"
        if run_setup(setup, log) == 0:
            show_log(log)
            raise AssertionError("Setup installed although the program was running")
        if gui.poll() is not None:
            raise AssertionError("Setup closed the running program instead of refusing")
        if exe.stat().st_mtime_ns != before:
            raise AssertionError("Setup replaced files of the running program")
        print("  Setup refuses while the program runs ✓")
        run_uninstaller(work / "uninstall-while-running.log")
        if not exe.is_file() or gui.poll() is not None:
            show_log(work / "uninstall-while-running.log")
            raise AssertionError("the uninstaller removed or closed the running program")
        print("  the uninstaller refuses while the program runs ✓")
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(gui.pid)], capture_output=True)
        gui.wait(30)


def check_fresh_install(setup: Path, work: Path) -> None:
    print(f"== Fresh install of {setup.name} (default tasks)", flush=True)
    install(setup, work / "install.log")
    if not shortcut("start").exists():
        raise AssertionError("no Start menu shortcut")
    if shortcut("desktop").exists():
        raise AssertionError("desktop icon created although unchecked by default")
    if key_exists(PROG_ID_KEY) or value_exists(OPEN_WITH_KEY, PROG_ID):
        raise AssertionError("Open-with entry created although unchecked by default")
    print("  Start menu shortcut only ✓")
    smoke()
    check_refusal_while_running(setup, work)
    # The settings of the app's old name: removed with their parent key, which is left empty.
    create_key(LEGACY_KEY, "format", "obj")
    uninstall(work / "uninstall.log")
    if key_exists(LEGACY_KEY):
        raise AssertionError(f"the uninstaller left HKCU\\{LEGACY_KEY} behind")
    if key_exists(LEGACY_PARENT):
        others = subkeys(LEGACY_PARENT)
        if not others:
            raise AssertionError(f"the uninstaller left the empty key HKCU\\{LEGACY_PARENT} behind")
        print(f"  HKCU\\{LEGACY_PARENT} kept for its other keys: {others}")
    print("  settings of the old app name removed from the registry ✓")


def check_open_with(setup: Path, work: Path) -> None:
    print(f"== Install of {setup.name} with the \"Open with\" entry", flush=True)
    install(setup, work / "install-openwith.log", "/TASKS=openwith")
    command = default_value(PROG_ID_KEY + r"\shell\open\command")
    if str(app_dir() / f"{APP_NAME}.exe") not in command or "%1" not in command:
        raise AssertionError(f"Open-with command is {command!r}")
    if not value_exists(OPEN_WITH_KEY, PROG_ID):
        raise AssertionError(f"no {PROG_ID} in HKCU\\{OPEN_WITH_KEY}")
    if value_exists(r"Software\Classes\.ifc", "") and default_value(r"Software\Classes\.ifc") == PROG_ID:
        raise AssertionError("the installer changed the default program of .ifc files")
    print("  Open-with entry registered, default program untouched ✓")
    create_key(LEGACY_KEY, "format", "obj")
    create_key(OTHER_KEY, "keep", "1")
    try:
        uninstall(work / "uninstall-openwith.log")
        if key_exists(PROG_ID_KEY) or value_exists(OPEN_WITH_KEY, PROG_ID):
            raise AssertionError("the uninstaller left the Open-with entry behind")
        if key_exists(LEGACY_KEY):
            raise AssertionError(f"the uninstaller left HKCU\\{LEGACY_KEY} behind")
        if not value_exists(OTHER_KEY, "keep"):
            raise AssertionError(f"the uninstaller removed HKCU\\{OTHER_KEY}, which is not its own")
        print("  Open-with entry and old settings removed, other keys kept ✓")
    finally:
        delete_key(OTHER_KEY)
        delete_key(LEGACY_KEY)
        delete_key(LEGACY_PARENT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("setup", type=Path, help="the new IFC-Converter-<version>-Setup.exe")
    parser.add_argument("--previous", type=Path, help="Setup.exe of an older release, to test the update")
    parser.add_argument("--work", type=Path, default=Path("installer-test"), help="folder for the setup logs")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("The installer test runs on Windows only.")
    if not os.environ.get("CI") and (app_dir() / f"{APP_NAME}.exe").exists():
        raise SystemExit(f"{APP_NAME} is installed in {app_dir()}; this test would uninstall it. Run it on a "
                         "throwaway machine (or set CI=1 to go ahead).")
    setup = args.setup.resolve()
    setup_version(setup)
    args.work.mkdir(parents=True, exist_ok=True)
    work = args.work.resolve()
    if args.previous:
        check_update(args.previous.resolve(), setup, work)
    else:
        print("== Update test skipped: no previous release given")
    check_fresh_install(setup, work)
    check_open_with(setup, work)
    print("Installer test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
