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
from ifc_converter.app import APP_NAME
from ifc_converter.converter import FORMATS, ConversionResult, memory_warning
from ifc_converter.process import RETRY_MESSAGE, convert_in_child

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
        self.show(f"{value} %")

    def clear(self) -> None:
        if self._width:
            self.stream.write("\r" + " " * self._width + "\r")
            self.stream.flush()
            self._width, self._text = 0, None


def output_files(target: Path, fmt: str) -> list[Path]:
    """Every file converting to ``target`` may write: OBJ adds a .mtl, and IfcOpenShell's GLB
    serializer buffers in two temporary files that a crashed or terminated conversion leaves behind."""
    if fmt == "obj":
        return [target, target.with_suffix(".mtl")]
    if fmt == "glb":
        return [target, Path(f"{target}.indices.tmp"), Path(f"{target}.vertices.tmp")]
    return [target]


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
    on_retry: Callable[[], None] | None = None,
    low_priority: bool = True,
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

    def retrying() -> None:
        # After a crash in the fast kernel the file is read and converted once more.
        line.clear()
        if on_retry:
            on_retry()
        line.show("IFC wird gelesen …")

    try:
        return convert_in_child(
            source, target, fmt, threads, line.percent, geometry=geometry, on_retry=retrying,
            low_priority=low_priority,
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
            found = sorted(p for p in path.rglob("*") if p.suffix.lower() == ".ifc")
            if found:
                files.extend(found)
            else:
                rejected.append(path)
        elif path.is_file() and path.suffix.lower() == ".ifc":
            files.append(path)
        else:
            rejected.append(path)
    return files, rejected


def run(fmt: str = "glb", output_dir: Path | None = None, geometry: str = "brep", low_priority: bool = True) -> int:
    output_dir = output_dir or desktop_dir()
    print("=" * 60)
    print(f"  {APP_NAME} {__version__}")
    print("=" * 60)
    print("  IFC-Datei(en) oder Ordner hier ins Fenster ziehen, dann Enter.")
    print(f"  Fertige Dateien landen in: {output_dir}")
    print("  Format wechseln: 'glb', 'obj' oder '3dm' eingeben.  Beenden: 'q'")
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
        for source in files:
            target = unique_path(output_dir / f"{source.stem}.{fmt}")
            warning = check_memory(source)
            if warning:
                print(f"  ⚠ {warning}")
            print(f"  … {source.name} wird umgewandelt")
            try:
                result = convert_in_terminal(
                    source, target, fmt, geometry=geometry, label="    ",
                    on_retry=lambda: print(f"  ⚠ {RETRY_MESSAGE}"), low_priority=low_priority,
                )
            except Exception as exc:
                print(f"  ✗ Fehler bei {source.name}: {exc}")
                continue
            skipped = f", {result.skipped} ohne Geometrie" if result.skipped > 0 else ""
            print(f"  ✓ Fertig: {result.output}  ({result.elements} Bauteile{skipped})")
            if result.skipped > 0:
                print(f"  ⚠ {skipped_warning(result.skipped)}")
        print()


if __name__ == "__main__":
    sys.exit(run())
