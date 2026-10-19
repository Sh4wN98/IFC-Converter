"""Build the distributable app: PyInstaller folder, portable ZIP and (on Windows) the Inno Setup installer,
or (on Linux) the tar.gz with install.sh.

    python packaging/build.py                    # everything that works on this platform
    python packaging/build.py --no-installer     # skip Inno Setup

Results land in dist/ (Windows):
    dist/IFC Converter/                          the program folder (IFC Converter.exe, ifc-convert.exe)
    dist/IFC-Converter-<version>-portable.zip    that folder zipped
    dist/IFC-Converter-<version>-Setup.exe       the installer (Windows, needs Inno Setup 6)
    dist/SHA256SUMS.txt                          checksums of the ZIP and the installer
and on Linux:
    dist/ifc-converter/                          the program folder (ifc-converter, ifc-convert)
    dist/IFC-Converter-<version>-linux-x86_64.tar.gz
                                                 that folder plus .desktop file, icon, MIME type,
                                                 install.sh and uninstall.sh (packaging/linux/)
    dist/SHA256SUMS.txt                          checksum of the tar.gz
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import platform
import shutil
import struct
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

from pe import set_stack_reserve, stack_reserve

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"
APP_NAME = "IFC Converter"
WINDOWS = sys.platform == "win32"
# The program folder PyInstaller builds (ifc_converter.spec): "IFC Converter" on Windows, "ifc-converter"
# on Linux, where names without spaces are the custom.
APP_DIR_NAME = APP_NAME if WINDOWS else "ifc-converter"
# Short name used for the Linux files (.desktop, icon, MIME type, install folder).
APP_SLUG = "ifc-converter"
# What the Linux tar.gz contains next to the program folder (packaging/linux/).
LINUX_FILES = ["install.sh", "uninstall.sh", f"{APP_SLUG}.desktop", f"{APP_SLUG}.xml", "LIESMICH.txt"]
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
        "--distpath", DIST, "--workpath", DIST.parent / "build" / "pyinstaller",
        PACKAGING / "ifc_converter.spec",
    ])
    return DIST / APP_DIR_NAME


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


def icon_png() -> bytes:
    """The icon as PNG for Linux desktops: the app's icon.png, else the largest PNG image in the .ico."""
    png = icon().with_suffix(".png")
    if png.is_file():
        return png.read_bytes()
    # ICO: ICONDIR (6 bytes), then 16-byte entries with width, height, ..., size, offset. Modern icons
    # (and ours) store the large images as PNG, which can be used as they are.
    data = icon().read_bytes()
    count = struct.unpack_from("<HHH", data, 0)[2]
    best = b""
    for index in range(count):
        width, height, _, _, _, _, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * index)
        image = data[offset:offset + size]
        if image.startswith(b"\x89PNG") and (width or 256) * (height or 256) > len(best):
            best = image
    if not best:
        sys.exit(f"{icon()} contains no PNG image; add an icon.png next to it")
    return best


def linux_tarball(app_dir: Path, version: str) -> Path:
    """dist/IFC-Converter-<version>-linux-<arch>.tar.gz: the program folder plus the files of packaging/linux.

    Everything is owned by root with fixed permissions (only the two executables and the scripts are
    executable), whatever the file system of the build machine records.
    """
    top = f"IFC-Converter-{version}-linux-{platform.machine()}"
    target = DIST / f"{top}.tar.gz"
    print(f"Creating {target.name}", flush=True)
    linux = PACKAGING / "linux"
    executables = {f"{top}/{APP_SLUG}/{APP_SLUG}", f"{top}/{APP_SLUG}/ifc-convert",
                   f"{top}/install.sh", f"{top}/uninstall.sh"}

    def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        if info.isdir():
            info.mode = 0o755
        else:
            info.mode = 0o755 if info.name in executables else 0o644
        return info

    with tarfile.open(target, "w:gz", compresslevel=6) as tar:
        tar.add(app_dir, arcname=f"{top}/{APP_SLUG}", filter=normalize)
        for name in LINUX_FILES:
            source = linux / name
            if not source.is_file():
                sys.exit(f"{source} is missing")
            tar.add(source, arcname=f"{top}/{name}", filter=normalize)
        png = icon_png()
        info = tarfile.TarInfo(f"{top}/{APP_SLUG}.png")
        info.size = len(png)
        info.mtime = int(linux.joinpath("install.sh").stat().st_mtime)
        tar.addfile(normalize(info), io.BytesIO(png))
    print(f"  {target.name}: {target.stat().st_size / 1024 ** 2:.0f} MB", flush=True)
    return target


def checksums(files: list[Path]) -> None:
    lines = [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}\n" for f in files]
    (DIST / "SHA256SUMS.txt").write_text("".join(lines), encoding="utf-8")
    print("".join(lines), end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-installer", action="store_true", help="do not build the Inno Setup installer")
    parser.add_argument("--no-zip", action="store_true", help="do not create the portable ZIP (Linux: the tar.gz)")
    parser.add_argument("--reuse-app-dir", action="store_true",
                        help="pack the program folder of the previous build instead of building it again "
                             "(for working on the packaging)")
    parser.add_argument("--build-root", type=Path, metavar="DIR",
                        help="put dist/ and build/ under DIR instead of the project folder (on Linux the "
                             "program folder contains symbolic links, which e.g. exFAT cannot store)")
    args = parser.parse_args()
    global DIST
    if args.build_root:
        DIST = args.build_root.resolve() / "dist"

    version = project_version()
    check_tag(version)
    print(f"Building {APP_NAME} {version} with Python {sys.version.split()[0]}", flush=True)

    if args.reuse_app_dir and (DIST / APP_DIR_NAME).is_dir():
        app_dir = DIST / APP_DIR_NAME
        print(f"Reusing {app_dir}", flush=True)
    else:
        app_dir = pyinstaller()
        if WINDOWS:
            enlarge_stacks(app_dir)
    outputs = []
    if not args.no_zip:
        outputs.append(portable_zip(app_dir, version) if WINDOWS else linux_tarball(app_dir, version))
    if WINDOWS and not args.no_installer:
        outputs.append(installer(app_dir, version))
    if outputs:
        checksums(outputs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
