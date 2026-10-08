"""The application's identity, its per-user folders, the log file and the handling of unexpected errors.

Nothing here needs Qt. The app only ever writes to these folders, to the chosen output folder and to
the temp folder; it needs no admin rights and changes nothing in the system.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import platform
import sys
import threading
import traceback
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ifc_converter import __version__

APP_NAME = "IFC Converter"
# Folder name on Linux and macOS, where names without spaces are the custom.
APP_SLUG = "ifc-converter"
REPOSITORY = "https://github.com/Sh4wN98/IFC-Converter"

LOG_NAME = "ifc-converter.log"
LOG_MAX_BYTES = 1_000_000  # per file; with the backups at most ~4 MB in all
LOG_BACKUPS = 3
LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(process)d] %(name)s: %(message)s"

# Third-party components shown in the About dialog: name -> licence.
LICENSES = {
    "IfcOpenShell": "LGPL-3.0",
    "rhino3dm": "MIT",
    "Qt 6 / PySide6": "LGPL-3.0",
    "NumPy": "BSD-3-Clause",
    "Shapely / GEOS": "BSD-3-Clause / LGPL-2.1",
    "Python": "PSF-2.0",
}

# Held by the running app (window or command line) while it runs, so that the installer and the
# uninstaller refuse to replace or remove its files meanwhile. The same name as AppMutex in
# packaging/installer.iss (made of its AppId).
APP_MUTEX = "IFCConverter-6F0B8E52-3C1D-4B7A-9E2F-5A8C1D4E7B90"

log = logging.getLogger("ifc_converter")

_handler: logging.Handler | None = None
_crash_file = None  # kept open for faulthandler
_mutex = None  # the handle of APP_MUTEX; Windows closes it when the process ends


def hold_app_mutex() -> bool:
    """Create APP_MUTEX and keep it until the process ends (Windows; elsewhere nothing happens).

    Several processes may hold it at once (a window and a command-line conversion). Returns whether
    it is held.
    """
    global _mutex
    if sys.platform != "win32":
        return False
    if _mutex:
        return True
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        _mutex = kernel32.CreateMutexW(None, False, APP_MUTEX) or None
    except (OSError, AttributeError):
        _mutex = None
    if _mutex is None:
        log.warning("Programm-Mutex konnte nicht angelegt werden: Der Installer erkennt das laufende Programm nicht")
    return _mutex is not None


def _home_env(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else fallback


def config_dir() -> Path:
    """Where the settings live: %APPDATA%\\IFC Converter on Windows, ~/.config/ifc-converter on Linux."""
    if sys.platform == "win32":
        return _home_env("APPDATA", Path.home() / "AppData" / "Roaming") / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return _home_env("XDG_CONFIG_HOME", Path.home() / ".config") / APP_SLUG


def log_dir() -> Path:
    """%LOCALAPPDATA%\\IFC Converter\\logs on Windows, ~/.local/state/ifc-converter/logs on Linux."""
    if sys.platform == "win32":
        return _home_env("LOCALAPPDATA", Path.home() / "AppData" / "Local") / APP_NAME / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_NAME
    return _home_env("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP_SLUG / "logs"


def rescue_dir() -> Path:
    """Where finished output goes that could not be copied to its network folder (local, kept)."""
    return log_dir().parent / "Ausgabe" if sys.platform == "win32" else log_dir().parent / "rescued"


def settings_path() -> Path:
    return config_dir() / "settings.ini"


def log_path() -> Path:
    return log_dir() / LOG_NAME


def log_files() -> list[Path]:
    """The log file and its rotated predecessors that exist, oldest first."""
    path = log_path()
    candidates = [path.with_name(f"{LOG_NAME}.{number}") for number in range(LOG_BACKUPS, 0, -1)] + [path]
    return [candidate for candidate in candidates if candidate.is_file()]


def write_anonymized_log(target: Path) -> Path:
    """Write all of the log (all files, oldest first) to ``target`` with personal data replaced.

    Raises FileNotFoundError if there is no log yet, OSError if ``target`` cannot be written.
    """
    from ifc_converter.anonymize import Anonymizer

    files = log_files()
    if not files:
        raise FileNotFoundError(f"Es gibt noch keine Logdatei in {log_dir()}")
    anonymizer = Anonymizer()
    text = "".join(anonymizer.text(path.read_text(encoding="utf-8", errors="replace")) for path in files)
    target = Path(target)
    target.write_text(text, encoding="utf-8")
    return target


def log_anonymized_setting() -> bool:
    """The setting "Logdatei anonymisieren" (anonymize_log in settings.ini), read without Qt."""
    import configparser

    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read(settings_path(), encoding="utf-8")
        return parser.get("General", "anonymize_log", fallback="false").strip().lower() == "true"
    except (configparser.Error, OSError, UnicodeDecodeError):
        return False


class AnonymizingFormatter(logging.Formatter):
    """Writes log records with user, computer, folder, file and element names replaced (see anonymize)."""

    def __init__(self, fmt: str):
        from ifc_converter.anonymize import Anonymizer

        super().__init__(fmt)
        self.anonymizer = Anonymizer()

    def format(self, record: logging.LogRecord) -> str:
        return self.anonymizer.text(super().format(record))


def set_log_anonymized(anonymized: bool) -> None:
    """From now on, write the log file anonymised (or not again)."""
    if _handler is not None and isinstance(_handler.formatter, AnonymizingFormatter) != anonymized:
        _handler.setFormatter(AnonymizingFormatter(LOG_FORMAT) if anonymized else logging.Formatter(LOG_FORMAT))


def setup_logging(kind: str, anonymized: bool | None = None) -> Path | None:
    """Log to the rotating log file from now on; ``kind`` ("GUI", "CLI") goes into the start line.

    ``anonymized`` (default: the setting in settings.ini) writes the log without personal data.
    Returns the log file, or None if it cannot be written (the app then runs without a log). Calling it
    again replaces the handler of the previous call.
    """
    global _handler
    stop_logging()
    root = logging.getLogger()
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")
    except OSError:
        return None
    if anonymized is None:
        anonymized = log_anonymized_setting()
    handler.setFormatter(AnonymizingFormatter(LOG_FORMAT) if anonymized else logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    _handler = handler
    logging.captureWarnings(True)  # warnings would otherwise go to a stderr that pythonw doesn't have
    log.info("%s %s gestartet (%s)", APP_NAME, __version__, kind)
    log.info("System: %s", system_summary())
    log.info("Komponenten: %s", ", ".join(f"{name} {version}" for name, version in component_versions().items()))
    return path


def stop_logging() -> None:
    """Close the log file of setup_logging()."""
    global _handler
    if _handler is not None:
        logging.getLogger().removeHandler(_handler)
        _handler.close()
        _handler = None


def enable_crash_log() -> None:
    """Write the Python stack of a native crash (e.g. in Qt) to crash.log in the log folder.

    Without a console (pythonw, the installed app) such a crash would otherwise leave no trace.
    """
    global _crash_file
    if _crash_file is not None:
        return
    try:
        log_dir().mkdir(parents=True, exist_ok=True)
        _crash_file = open(log_dir() / "crash.log", "a", encoding="utf-8")  # noqa: SIM115 - must stay open
        faulthandler.enable(file=_crash_file)
    except (OSError, RuntimeError, ValueError):
        _crash_file = None


def system_summary() -> str:
    from ifc_converter.converter import available_memory

    cores = os.cpu_count() or 1
    free = available_memory()
    memory = f"{free / 1024 ** 3:.1f} GB RAM frei" if free else "freier RAM unbekannt"
    return f"{platform.platform()}, {cores} logische Kerne, {memory}"


def component_versions() -> dict[str, str]:
    """Versions of the app and the libraries that matter for a support case."""
    versions = {APP_NAME: __version__, "Python": platform.python_version()}
    components = [
        ("IfcOpenShell", lambda: __import__("ifcopenshell").version),
        ("rhino3dm", lambda: __import__("rhino3dm").__version__),
    ]
    # Qt is only reported where it is loaded anyway (GUI, About dialog): importing it just for the
    # log would load all of Qt into every command-line conversion.
    if "PySide6.QtCore" in sys.modules:
        components += [
            ("Qt", lambda: sys.modules["PySide6.QtCore"].qVersion()),
            ("PySide6", lambda: __import__("PySide6").__version__),
        ]
    components.append(("NumPy", lambda: __import__("numpy").__version__))
    for name, getter in components:
        try:
            versions[name] = str(getter())
        except Exception:  # noqa: BLE001 - a missing component must not break the About dialog
            versions[name] = "nicht verfügbar"
    versions["System"] = f"{platform.system()} {platform.release()} ({platform.machine()})"
    return versions


def format_exception(exc_type, exc, tb) -> str:
    return "".join(traceback.format_exception(exc_type, exc, tb))


def install_exception_hooks(report: Callable[[str, str], None]) -> None:
    """Log every uncaught exception, in any thread, and pass (summary, details) to ``report``.

    ``report`` (e.g. a dialog) may be called from any thread. Without this, an error in the windowed
    app would end it silently or vanish, as pythonw has no console to print the traceback to.
    """

    def handle(exc_type, exc, tb, where: str = "") -> None:
        details = format_exception(exc_type, exc, tb)
        log.error("Unerwarteter Fehler%s:\n%s", where, details.rstrip())
        summary = f"{exc_type.__name__}: {exc}" if str(exc) else exc_type.__name__
        try:
            report(summary, f"{APP_NAME} {__version__}\n{details}")
        except Exception:  # noqa: BLE001 - reporting must never raise again
            log.exception("Fehlerdialog konnte nicht angezeigt werden")

    def excepthook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        handle(exc_type, exc, tb)

    def thread_excepthook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        name = f" im Thread {args.thread.name}" if args.thread is not None else ""
        handle(args.exc_type, args.exc_value, args.exc_traceback, name)

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
