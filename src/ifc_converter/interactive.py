"""Drag-and-drop mode: drop IFC files into the terminal, results land on the desktop."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from ifc_converter.converter import FORMATS, convert, memory_warning

# A dropped path is either quoted ("..." or '...') or a run of non-space characters,
# where a backslash may escape a space (Linux/macOS terminals).
_TOKEN = re.compile(r'"([^"]+)"|\'([^\']+)\'|((?:\\ |\S)+)')

QUIT_WORDS = {"q", "quit", "exit", "ende", "beenden"}


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
    """The user's desktop folder, honouring OneDrive redirection and localised names."""
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
    desktop = desktop or Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    return desktop


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


def check_memory(path: Path) -> str | None:
    """The RAM warning for `path`, or None (also if the file cannot be read; convert() reports that)."""
    try:
        return memory_warning(path)
    except OSError:
        return None


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


def run(fmt: str = "glb", output_dir: Path | None = None, geometry: str = "brep") -> int:
    output_dir = output_dir or desktop_dir()
    print("=" * 60)
    print("  IFC File Converter")
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

        for source in files:
            target = unique_path(output_dir / f"{source.stem}.{fmt}")
            warning = check_memory(source)
            if warning:
                print(f"  ⚠ {warning}")
            print(f"  … {source.name} wird umgewandelt")
            try:
                result = convert(source, target, fmt, geometry=geometry)
            except Exception as exc:
                print(f"  ✗ Fehler bei {source.name}: {exc}")
                continue
            print(f"  ✓ Fertig: {result.output}  ({result.elements} Bauteile)")
        print()


if __name__ == "__main__":
    sys.exit(run())
