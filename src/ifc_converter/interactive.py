"""Drag-and-drop mode: drop IFC files into the terminal, results land on the desktop."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from ifc_converter import __version__
from ifc_converter.app import APP_NAME, log_path
from ifc_converter.converter import FORMATS, INPUT_SUFFIXES, ConversionResult, memory_warning
from ifc_converter.process import auto_threads, convert_in_child

# A dropped path is either quoted ("..." or '...') or a run of non-space characters,
# where a backslash may escape a space (Linux/macOS terminals).
_TOKEN = re.compile(r'"([^"]+)"|\'([^\']+)\'|((?:\\ |\S)+)')

QUIT_WORDS = {"q", "quit", "exit", "ende", "beenden"}

# Explains ConversionResult.skipped wherever results are shown.
SKIPPED_HINT = (
    "Diese Bauteile haben Geometrie, die nicht umgewandelt werden konnte – "
    "z. B. nicht unterstützte Geometrietypen, oder sie werden von ihren Öffnungen vollständig weggeschnitten."
)


def parse_dropped(line: str, windows: bool | None = None) -> list[Path]:
    """Extract file paths from text that a terminal produced for dropped files."""
    if windows is None:
        windows = os.name == "nt"
    line = line.strip()
    if line.startswith("& "):  # PowerShell prefixes dropped paths with the call operator
        line = line[2:].strip()

    # The whole line may be one path with unescaped spaces.
    whole = line.strip("\"'")
    if whole and Path(whole).exists():
        return [Path(whole)]

    paths = []
    for double, single, bare in _TOKEN.findall(line):
        raw = double or single or bare
        if bare and not windows:
            raw = re.sub(r"\\(.)", r"\1", raw)
        if raw.startswith("file://"):
            raw = url2pathname(unquote(urlparse(raw).path))
        paths.append(Path(raw))
    return paths


def desktop_dir() -> Path:
    """The user's desktop folder, honouring OneDrive redirection and localised names.

    The folder is not created here: only a conversion that writes into it does that.
    """
    if os.name == "nt":
        desktop = _windows_desktop()
    else:
        desktop = None
        try:
            out = subprocess.run(
                ["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            # xdg-user-dir falls back to $HOME when no desktop folder is configured.
            if out and Path(out) != Path.home():
                desktop = Path(out)
        except (OSError, subprocess.SubprocessError):
            pass
    return desktop or Path.home() / "Desktop"


def _windows_desktop() -> Path | None:
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]

        # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
        folder_id = GUID(
            0xB4BFCC3A, 0xDB2C, 0x424C, (wintypes.BYTE * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41)
        )
        path_ptr = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path_ptr)):
            return None
        path = Path(path_ptr.value)
        ctypes.windll.ole32.CoTaskMemFree(path_ptr)
        return path
    except Exception:
        return None


def unique_path(path: Path) -> Path:
    """Return `path`, or `name (2).ext`, `name (3).ext`, ... if it already exists."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def skipped_count(skipped: int) -> str:
    """"3 Bauteile ohne Geometrie" (elements whose geometry could not be converted)."""
    return f"{skipped} {'Bauteil' if skipped == 1 else 'Bauteile'} ohne Geometrie"


def skipped_warning(skipped: int) -> str:
    """The warning for elements that were left out for lack of geometry, or "" if there are none."""
    return f"{skipped_count(skipped)}. {SKIPPED_HINT}" if skipped > 0 else ""


# How many skipped elements a message names; the log file lists all of them.
NAMED_ELEMENTS = 10


def crashed_warning(crashed: list[str]) -> str:
    """The warning for elements left out because the kernel crashed or hung on them, or ""."""
    if not crashed:
        return ""
    count = len(crashed)
    names = "; ".join(crashed[:NAMED_ELEMENTS])
    more = f" … und {count - NAMED_ELEMENTS} weitere (alle in der Logdatei)" if count > NAMED_ELEMENTS else ""
    return (
        f"{count} {'Bauteil' if count == 1 else 'Bauteile'} übersprungen, weil der Geometriekern daran "
        f"abstürzte oder hängen blieb: {names}{more}. Im CAD-Programm lassen sie sich über die GlobalId finden."
    )


_LABEL = re.compile(r"^(Ifc\w+) (\S+)(?: „(.*)“)?$", re.DOTALL)


def split_label(label: str) -> tuple[str, str, str]:
    """(class, GlobalId, name) of an element label "IfcWall 2O2Fr… „Name“" (see converter.product_label).

    A label without class and GlobalId (e.g. "#123", a step id) comes back as the GlobalId.
    """
    match = _LABEL.match(label)
    if not match:
        return "", label, ""
    return match.group(1), match.group(2), match.group(3) or ""


# Exceptions about the input, the output folder or the computer, not about the program: their text
# is shown as it is (the converter's own ones are German). Everything else is an internal error.
FILE_ERRORS = {
    "OSError", "FileNotFoundError", "PermissionError", "FileExistsError", "IsADirectoryError",
    "NotADirectoryError", "TimeoutError", "ConnectionError", "ConnectionResetError", "ConnectionAbortedError",
    "BrokenPipeError", "InterruptedError",
}
# How the window's menu opens the log file.
LOG_MENU = "Hilfe → Logdatei öffnen"


def _error_type(exc: BaseException) -> str:
    # A ConversionFailed carries the type of the exception in the child process.
    return getattr(exc, "type_name", None) or type(exc).__name__


def is_internal_error(exc: BaseException) -> bool:
    """Whether a failed conversion is a fault of the program (worth reporting), not of the file or PC."""
    from ifc_converter.process import ConversionCrashed, ConversionFailed, ConversionStalled

    if isinstance(exc, (ConversionCrashed, ConversionStalled)):
        return False
    if not isinstance(exc, ConversionFailed) and type(exc).__module__.startswith("ifc_converter"):
        return False
    return _error_type(exc) not in (FILE_ERRORS | {"ValueError", "MemoryError", "Error"})


def error_message(exc: BaseException) -> str:
    """A failed conversion in German, for the window and the terminal."""
    name = _error_type(exc)
    text = str(exc)
    if text == name:  # no message of its own
        text = ""
    if name == "MemoryError":
        return "Der Arbeitsspeicher hat nicht gereicht"
    if name == "Error":  # ifcopenshell.Error: the file could not be parsed
        return f"Die Datei ließ sich nicht als IFC lesen (beschädigt oder keine IFC-Datei){f': {text}' if text else ''}"
    if name in FILE_ERRORS and ("[Errno" in text or "[WinError" in text):
        return f"Datei- oder Netzwerkfehler: {text}"
    if is_internal_error(exc):
        return f"Interner Fehler ({name}){f': {text}' if text else ''}"
    return text or name


def failure_hint(internal: bool, log: str = LOG_MENU) -> str:
    """Where the details of a failure are (see is_internal_error); ``log`` says how to find the log file."""
    if internal:
        return f"Bitte die Logdatei ({log}) mitschicken, wenn Sie den Fehler melden."
    return f"Details in der Logdatei ({log})."


def resource_text(threads: int, low_priority: bool, workers: int = 0) -> str:
    """What a conversion takes of the PC, e.g. "bis zu 6 von 32 logischen Kernen, niedrige Priorität"."""
    from ifc_converter.process import cpu_count

    text = f"bis zu {threads} {'Thread' if threads == 1 else 'Threads'} (von {cpu_count()} logischen Kernen)"
    if workers:
        text += f", bei großen 3DM-Modellen dazu bis zu {workers} Hilfsprozesse für die Rhino-Geometrie"
    if low_priority:
        return f"{text}, niedrige Priorität – andere Programme haben Vorrang"
    return f"{text}, normale Priorität"


def rhino_workers(threads: int) -> int:
    """How many worker processes a large Rhino export may start besides the geometry threads, or 0."""
    try:
        from ifc_converter import rhino

        return max(0, int(rhino._worker_count(threads, rhino.MIN_PARALLEL_ELEMENTS)))
    except Exception:  # noqa: BLE001 - only informative; rhino.py may change
        return 0


def duration_text(seconds: float) -> str:
    """A duration in German, e.g. "12,3 s", "52 min 2 s" or "1 h 5 min"."""
    if seconds < 60:
        return f"{seconds:.1f} s".replace(".", ",")
    minutes, seconds = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {seconds} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


def number_text(number: int) -> str:
    """A count with German thousands separators, e.g. "117.137"."""
    return f"{number:,}".replace(",", ".")


def check_memory(path: Path) -> str | None:
    """The RAM warning for `path`, or None (also if the file cannot be read; convert() reports that)."""
    try:
        return memory_warning(path)
    except OSError:
        return None


class ProgressLine:
    """One terminal line with a conversion's progress, rewritten in place after a carriage return.

    Only shown if the stream is a terminal; redirected output gets no progress at all.
    """

    def __init__(self, label: str = "", stream: TextIO | None = None):
        self.stream = stream or sys.stdout
        self.label = label
        try:
            self.enabled = self.stream.isatty()
        except (AttributeError, ValueError, OSError):  # no stdout (pythonw) or a closed one
            self.enabled = False
        self._text: str | None = None
        self._width = 0
        self._percent: int | None = None
        self._detail = ""

    def show(self, text: str) -> None:
        if not self.enabled or text == self._text:
            return
        self._text = text
        line = self.label + text
        # Pad with spaces to overwrite a longer previous text; ANSI erase codes need not work on Windows.
        self.stream.write("\r" + line.ljust(self._width))
        self.stream.flush()
        self._width = max(self._width, len(line))

    def percent(self, value: int) -> None:
        self._percent = value
        self.show(f"{value} %" + (f" – {self._detail}" if self._detail else ""))

    def phase(self, phase: str, text: str) -> None:
        """The long final phases (writing, copying) are shown next to the percentage."""
        self._detail = text if phase in ("write", "copy", "deep") else ""
        if self._percent is not None:
            self.percent(self._percent)

    def clear(self) -> None:
        if self._width:
            self.stream.write("\r" + " " * self._width + "\r")
            self.stream.flush()
            self._width, self._text = 0, None
        self._percent, self._detail = None, ""


def output_files(target: Path, fmt: str) -> list[Path]:
    """Every file converting to ``target`` may write: OBJ adds a .mtl, and IfcOpenShell's GLB
    serializer buffers in two temporary files that a crashed or terminated conversion leaves behind."""
    from ifc_converter.serializers import output_files as serializer_files

    return serializer_files(target, fmt, temp=True)


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def convert_in_terminal(
    source: Path,
    target: Path | None,
    fmt: str,
    threads: int | None = None,
    geometry: str = "brep",
    label: str = "",
    on_retry: Callable[[str], None] | None = None,
    low_priority: bool = True,
    blocks: bool = False,
) -> ConversionResult:
    """convert() in a child process with a progress line on stdout.

    Running out of memory or a crash in the geometry kernel then only fails this file (as an
    exception), so a batch can go on. Partial output is removed after a failure, but only files this
    conversion created, never ones that existed before.
    """
    target = Path(target) if target else source.with_suffix(f".{fmt}")
    created = [path for path in output_files(target, fmt) if not path.exists()]
    line = ProgressLine(label)
    # convert() reports 0 % only once the IFC file is read, which can take minutes.
    line.show("IFC wird gelesen …")

    def retrying(message: str) -> None:
        # After a crash or hang the file is read and converted once more.
        line.clear()
        if on_retry:
            on_retry(message)
        line.show("IFC wird gelesen …")

    try:
        return convert_in_child(
            source, target, fmt, threads, line.percent, geometry=geometry, on_retry=retrying,
            low_priority=low_priority, status=line.phase, **({"blocks": True} if blocks and fmt == "3dm" else {}),
        )
    except BaseException:
        for path in created:
            _discard(path)
        raise
    finally:
        line.clear()


def collect_ifc_files(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    """Split dropped paths into IFC files (folders are searched) and rejected paths."""
    files, rejected = [], []
    for path in paths:
        if path.is_dir():
            found = sorted(p for p in path.rglob("*") if p.suffix.lower() in INPUT_SUFFIXES)
            if found:
                files.extend(found)
            else:
                rejected.append(path)
        elif path.is_file() and path.suffix.lower() in INPUT_SUFFIXES:
            files.append(path)
        else:
            rejected.append(path)
    return files, rejected


def run(
    fmt: str = "glb", output_dir: Path | None = None, geometry: str = "brep", low_priority: bool = True,
    blocks: bool = False,
) -> int:
    output_dir = output_dir or desktop_dir()
    print("=" * 60)
    print(f"  {APP_NAME} {__version__}")
    print("=" * 60)
    print("  IFC-Datei(en) oder Ordner hier ins Fenster ziehen, dann Enter.")
    print(f"  Fertige Dateien landen in: {output_dir}")
    formats = ", ".join(f"'{name}'" for name in FORMATS[:-1]) + f" oder '{FORMATS[-1]}'"
    print(f"  Format wechseln: {formats} eingeben.  Beenden: 'q'")
    print("  Abbrechen einer laufenden Umwandlung: Strg+C")
    print(f"  Rechenleistung: {resource_text(auto_threads(), low_priority)}")
    print()

    while True:
        try:
            line = input(f"[{fmt.upper()}] Datei reinziehen > ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        command = line.strip().lower()
        if not command:
            continue
        if command in QUIT_WORDS:
            return 0
        if command in FORMATS:
            fmt = command
            print(f"  Format ist jetzt {fmt.upper()}.\n")
            continue

        files, rejected = collect_ifc_files(parse_dropped(line))
        for path in rejected:
            print(f"  ✗ Keine IFC-Datei gefunden: {path}")

        if files:
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                print(f"  ✗ Ausgabeordner kann nicht angelegt werden: {exc}")
                continue
        for number, source in enumerate(files):
            target = unique_path(output_dir / f"{source.stem}.{fmt}")
            warning = check_memory(source)
            if warning:
                print(f"  ⚠ {warning}")
            print(f"  … {source.name} wird umgewandelt")
            try:
                result = convert_in_terminal(
                    source, target, fmt, geometry=geometry, label="    ",
                    on_retry=lambda message: print(f"  ⚠ {message}"), low_priority=low_priority, blocks=blocks,
                )
            except KeyboardInterrupt:
                rest = len(files) - number - 1
                print(f"  ■ Abgebrochen: {source.name}" + (f" ({rest} weitere nicht umgewandelt)" if rest else ""))
                break
            except Exception as exc:
                print(f"  ✗ Fehler bei {source.name}: {error_message(exc)}")
                print(f"    {failure_hint(is_internal_error(exc), str(log_path()))}")
                continue
            skipped = f", {result.skipped} ohne Geometrie" if result.skipped > 0 else ""
            print(f"  ✓ Fertig: {result.output}  ({number_text(result.elements)} Bauteile{skipped})")
            if result.crashed:
                print(f"  ⚠ {crashed_warning(result.crashed)}")
            if result.skipped > 0:
                print(f"  ⚠ {skipped_warning(result.skipped)}")
        print()


if __name__ == "__main__":
    sys.exit(run())
