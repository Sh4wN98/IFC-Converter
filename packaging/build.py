"""Build the distributable app: PyInstaller folder, portable ZIP and (on Windows) the Inno Setup installer.

    python packaging/build.py                    # everything that works on this platform
    python packaging/build.py --no-installer     # skip Inno Setup

Results land in dist/:
    dist/IFC Converter/                          the program folder (IFC Converter.exe, ifc-convert.exe)
    dist/IFC-Converter-<version>-portable.zip    that folder zipped
    dist/IFC-Converter-<version>-Setup.exe       the installer (Windows, needs Inno Setup 6)
    dist/SHA256SUMS.txt                          checksums of the ZIP and the installer
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from pe import set_stack_reserve, stack_reserve

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"
APP_NAME = "IFC Converter"
# Default thread stack of the exes (Windows' default for the bootloader is 1 MB, see pe.py): the
# geometry kernels need about 1 MB per few thousand levels of nested geometry.
STACK_RESERVE = 256 * 1024 ** 2
# Where the Inno Setup installer (or "choco install innosetup") puts its compiler.
ISCC_CANDIDATES = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
]


def project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def check_tag(version: str) -> None:
    """In a GitHub Actions run for a tag, the tag must be v<version from pyproject>."""
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag = os.environ.get("GITHUB_REF_NAME", "")
        if tag != f"v{version}":
            sys.exit(f"Tag {tag!r} does not match the version in pyproject.toml ({version}); expected v{version}")


def run(command: list[str | Path]) -> None:
    print("+", " ".join(f'"{c}"' if " " in str(c) else str(c) for c in command), flush=True)
    subprocess.run([str(c) for c in command], check=True, cwd=ROOT)


def pyinstaller() -> Path:
    run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", ROOT / "build" / "pyinstaller",
        PACKAGING / "ifc_converter.spec",
    ])
    return DIST / APP_NAME


def enlarge_stacks(app_dir: Path) -> None:
    """Give every thread of the exes STACK_RESERVE of stack (see pe.py)."""
    for exe in sorted(app_dir.glob("*.exe")):
        set_stack_reserve(exe, STACK_RESERVE)
        print(f"{exe.name}: default thread stack {stack_reserve(exe) // 1024 ** 2} MB", flush=True)


def portable_zip(app_dir: Path, version: str) -> Path:
    base = DIST / f"IFC-Converter-{version}-portable"
    print(f"Creating {base.name}.zip", flush=True)
    return Path(shutil.make_archive(str(base), "zip", root_dir=app_dir.parent, base_dir=app_dir.name))


def find_iscc() -> Path | None:
    found = shutil.which("iscc") or shutil.which("ISCC.exe")
    if found:
        return Path(found)
    return next((path for path in ISCC_CANDIDATES if path.is_file()), None)


def installer(app_dir: Path, version: str) -> Path:
    iscc = find_iscc()
    if iscc is None:
        sys.exit("Inno Setup 6 (ISCC.exe) not found: install it from https://jrsoftware.org/isdl.php "
                 "or run with --no-installer")
    run([
        iscc, "/Qp",
        f"/DAppVersion={version}", f"/DSourceDir={app_dir}", f"/DOutputDir={DIST}",
        f"/DIconFile={icon()}", PACKAGING / "installer.iss",
    ])
    return DIST / f"IFC-Converter-{version}-Setup.exe"


def icon() -> Path:
    """The same icon the spec uses for the exes."""
    icons = sorted((ROOT / "src" / "ifc_converter" / "resources").glob("*.ico"))
    return icons[0] if icons else PACKAGING / "placeholder-icon.ico"


def checksums(files: list[Path]) -> None:
    lines = [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}\n" for f in files]
    (DIST / "SHA256SUMS.txt").write_text("".join(lines), encoding="utf-8")
    print("".join(lines), end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-installer", action="store_true", help="do not build the Inno Setup installer")
    parser.add_argument("--no-zip", action="store_true", help="do not create the portable ZIP")
    args = parser.parse_args()

    version = project_version()
    check_tag(version)
    print(f"Building {APP_NAME} {version} with Python {sys.version.split()[0]}", flush=True)

    app_dir = pyinstaller()
    if sys.platform == "win32":
        enlarge_stacks(app_dir)
    outputs = []
    if not args.no_zip:
        outputs.append(portable_zip(app_dir, version))
    if sys.platform == "win32" and not args.no_installer:
        outputs.append(installer(app_dir, version))
    if outputs:
        checksums(outputs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
