"""Smoke test of the Linux build (and of the tar.gz with install.sh), modelled on smoke_test.py.

    python packaging/smoke_test_linux.py dist/ifc-converter --gui
    python packaging/smoke_test_linux.py dist/ifc-converter --gui --tarball dist/IFC-Converter-0.5.0-linux-x86_64.tar.gz

Runs with a normal Python that has ifcopenshell and rhino3dm (to create the IFCs and read the .3dm);
the conversions themselves run only in the built executables. Checks, like on Windows: the 5 x 0.2 x
3 m wall in all formats (3DM polysurfaces with the default and the hybrid kernel, 3DM meshes, GLB,
OBJ), every output with exactly these dimensions in metres; the 600-wall model with worker processes;
the model nested 5000 levels deep; a cancelled (SIGTERM) and a killed conversion leave nothing in the
temp folder; the program window starts (offscreen, no display needed). Linux-specific: every shared
library the build needs is either in the build or found on this machine (ldd walk), the Qt platform
plugins (xcb, Wayland, offscreen) and the OpenGL libraries of the 3D preview are in the build, and
the tar.gz installs, updates, refuses while the program runs and uninstalls cleanly in a fake HOME.
Runs in about 3 minutes on a laptop; needs no root and writes only to its temp folders.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from pathlib import Path

import rhino3dm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import (  # noqa: E402
    NESTING,
    check_3dm,
    check_cancel,
    check_glb,
    check_gui,
    check_killed,
    check_large_model,
    check_no_leftovers,
    check_obj,
    convert,
    make_nested,
    make_wall,
    make_walls,
    running,
    snapshot,
    temp_entries,
)

ROOT = Path(__file__).resolve().parent.parent
SLUG = "ifc-converter"
# Geometry threads for the 600-wall model: enough for one worker process (rhino.py starts one per two
# threads), and the CI runners and the dev laptop have four cores.
THREADS = 2
# What must be in the build, below _internal (the 3D preview's OpenGL, the desktop platform plugins).
REQUIRED_FILES = [
    "PySide6/Qt/plugins/platforms/libqxcb.so",
    "PySide6/Qt/plugins/platforms/libqwayland.so",
    "PySide6/Qt/plugins/platforms/libqoffscreen.so",
    "PySide6/Qt/lib/libQt6XcbQpa.so.6",
    "PySide6/Qt/lib/libQt6WaylandClient.so.6",
    "PySide6/Qt/lib/libQt6OpenGL.so.6",
    "PySide6/Qt/lib/libQt6OpenGLWidgets.so.6",
    "PySide6/QtOpenGL.abi3.so",
    "PySide6/QtOpenGLWidgets.abi3.so",
    "ifcopenshell/ifcopenshell_geometry_kernel_opencascade.so",
    "ifcopenshell/ifcopenshell_geometry_kernel_cgal.so",
    "ifcopenshell/ifcopenshell_geometry_glb.so",
    "ifcopenshell/ifcopenshell_geometry_mapping_ifc4.so",
    "ifcopenshell/express/express_parser.py",
    "THIRD-PARTY-NOTICES.txt",
    "licenses/LGPL-3.0.txt",
]
# Plugin folders that must contain at least one plugin: OpenGL under X11, window decorations and shell
# integration under Wayland, image formats for the icons.
REQUIRED_PLUGIN_DIRS = [
    "PySide6/Qt/plugins/xcbglintegrations",
    "PySide6/Qt/plugins/wayland-shell-integration",
    "PySide6/Qt/plugins/wayland-graphics-integration-client",
    "PySide6/Qt/plugins/imageformats",
]
# What the tar.gz must contain next to the program folder (build.py, packaging/linux/).
TARBALL_FILES = ["install.sh", "uninstall.sh", f"{SLUG}.desktop", f"{SLUG}.png", f"{SLUG}.xml", "LIESMICH.txt"]
LDD_TIMEOUT = 60


def project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def shared_objects(app_dir: Path) -> list[Path]:
    """The ELF files of the build (regular files, not the symbolic links PyInstaller adds)."""
    return sorted(
        path for path in app_dir.rglob("*")
        if path.is_file() and not path.is_symlink() and is_elf(path)
    )


def check_shared_libraries(app_dir: Path) -> None:
    """ldd walk: no library that the executables, Python modules and plugins need may be missing.

    The frozen app finds its own libraries through LD_LIBRARY_PATH (set by PyInstaller's bootloader to
    _internal) and the rpath of the Qt plugins; everything else must come from the system, and a
    missing one would only show up when that part is used (the X11 platform plugin, the OpenGL
    preview). Prints the system libraries the build relies on, which is what the README lists.
    """
    objects = shared_objects(app_dir)
    folders = sorted({str(path.parent) for path in objects})
    env = dict(os.environ, LD_LIBRARY_PATH=os.pathsep.join(folders + [os.environ.get("LD_LIBRARY_PATH", "")]))
    missing: dict[str, list[str]] = {}
    system: set[str] = set()
    checked = 0
    for path in objects:
        result = subprocess.run(["ldd", str(path)], capture_output=True, text=True, timeout=LDD_TIMEOUT, env=env)
        if result.returncode != 0:
            continue  # not a dynamic executable (e.g. a static helper), nothing to resolve
        checked += 1
        for line in result.stdout.splitlines():
            parts = line.split()
            if "not found" in line:
                missing.setdefault(parts[0], []).append(str(path.relative_to(app_dir)))
            elif len(parts) >= 3 and parts[1] == "=>" and parts[2].startswith("/"):
                if not Path(parts[2]).resolve().is_relative_to(app_dir.resolve()):
                    system.add(Path(parts[2]).name)
    if missing:
        lines = [f"    {lib}  (needed by {', '.join(users[:3])}{' ...' if len(users) > 3 else ''})"
                 for lib, users in sorted(missing.items())]
        raise AssertionError("shared libraries missing from the build and from this machine:\n" + "\n".join(lines))
    print(f"  {checked} ELF files, every shared library resolves ✓")
    print(f"  system libraries used ({len(system)}): {' '.join(sorted(system))}")


def check_files(app_dir: Path) -> None:
    internal = app_dir / "_internal"
    for exe in (app_dir / SLUG, app_dir / "ifc-convert"):
        if not exe.is_file():
            raise SystemExit(f"{exe} does not exist")
        if not os.access(exe, os.X_OK):
            raise SystemExit(f"{exe} is not executable")
    missing = [name for name in REQUIRED_FILES if not (internal / name).is_file()]
    empty = [name for name in REQUIRED_PLUGIN_DIRS if not any((internal / name).glob("*.so"))]
    if missing or empty:
        raise SystemExit(f"missing from the build: {', '.join(missing + [d + '/*.so' for d in empty])}")
    if not any(internal.joinpath("ifcopenshell").rglob("*.exp")):
        raise SystemExit("missing from the build: the IFC schema files (ifcopenshell/**/*.exp)")
    print(f"  executables, Qt platform plugins (xcb, wayland, offscreen), OpenGL and IfcOpenShell libraries present ✓")


def check_cli_help(cli: Path) -> None:
    """--help and --version work (and nothing else starts, e.g. the drag-and-drop mode)."""
    for option in ("--help", "--version"):
        result = subprocess.run([str(cli), option], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise AssertionError(f"ifc-convert {option}: exit code {result.returncode}\n{result.stderr[-2000:]}")
        if option == "--version" and result.stdout.strip() != f"ifc-convert {project_version()}":
            raise AssertionError(f"ifc-convert --version printed {result.stdout.strip()!r}, "
                                 f"expected 'ifc-convert {project_version()}'")
    print(f"  ifc-convert --help, --version ({project_version()}) ✓")


def check_nested(cli: Path, source: Path, out: Path) -> None:
    """The deeply nested model converts (its geometry runs in a thread with a large stack)."""
    convert(cli, source, out / "nested.3dm", "-f", "3dm")
    objects = rhino3dm.File3dm.Read(str(out / "nested.3dm")).Objects
    if len(objects) != 1:
        raise AssertionError(f"nested.3dm: {len(objects)} objects instead of 1")
    print(f"  {NESTING} nested levels converted ✓")


def fake_home_env(home: Path) -> dict[str, str]:
    """An environment whose user folders all lie under ``home`` (no XDG_* of the real user)."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("XDG_") and key != "IFC_CONVERTER_PREFIX"}
    env["HOME"] = str(home)
    env["QT_QPA_PLATFORM"] = "offscreen"
    return env


def run_script(script: Path, home: Path, *args: str, expect: int = 0, env_extra: dict | None = None) -> str:
    """Run install.sh/uninstall.sh with ``home`` as HOME (no XDG folders set) and return its output."""
    env = fake_home_env(home)
    env.update(env_extra or {})
    print(f"+ HOME={home} {script.name} {' '.join(args)}", flush=True)
    result = subprocess.run(["bash", str(script), *args], capture_output=True, text=True, timeout=300, env=env)
    output = result.stdout + result.stderr
    for line in output.splitlines():
        print(f"  | {line}")
    if result.returncode != expect:
        raise AssertionError(f"{script.name}: exit code {result.returncode}, expected {expect}")
    return output


def check_installation(home: Path, prefix: Path) -> None:
    data = home / ".local" / "share"
    for path in (prefix / SLUG, prefix / "ifc-convert", prefix / "uninstall.sh", prefix / "_internal" / "THIRD-PARTY-NOTICES.txt",
                 data / "applications" / f"{SLUG}.desktop", data / "icons" / "hicolor" / "256x256" / "apps" / f"{SLUG}.png",
                 data / "mime" / "packages" / f"{SLUG}.xml"):
        if not path.is_file():
            raise AssertionError(f"install.sh did not create {path}")
    for name in (SLUG, "ifc-convert"):
        link = home / ".local" / "bin" / name
        if not link.is_symlink() or link.resolve() != (prefix / name).resolve():
            raise AssertionError(f"{link} is not a link to {prefix / name}")
    desktop = (data / "applications" / f"{SLUG}.desktop").read_text(encoding="utf-8")
    if f'Exec="{prefix / SLUG}" %F' not in desktop or f"TryExec={prefix / SLUG}" not in desktop:
        raise AssertionError(f"the menu entry does not start {prefix / SLUG}:\n{desktop}")
    if "MimeType=application/x-ifc;" not in desktop:
        raise AssertionError("the menu entry does not declare the IFC MIME type")
    if shutil.which("desktop-file-validate"):
        result = subprocess.run(["desktop-file-validate", str(data / "applications" / f"{SLUG}.desktop")],
                                capture_output=True, text=True, timeout=60)
        if result.returncode != 0 or result.stdout.strip():
            raise AssertionError(f"desktop-file-validate: {result.stdout}{result.stderr}")
    if shutil.which("update-mime-database"):
        globs = (data / "mime" / "globs2").read_text(encoding="utf-8") if (data / "mime" / "globs2").is_file() else ""
        if "application/x-ifc:*.ifc" not in globs:
            raise AssertionError("the MIME type for *.ifc was not registered (mime/globs2)")
    for leftover in (Path(f"{prefix}.neu"), Path(f"{prefix}.alt")):
        if leftover.exists():
            raise AssertionError(f"install.sh left {leftover} behind")
    print(f"  installed under {prefix}: program, commands, menu entry, icon, MIME type ✓")


def check_uninstalled(home: Path, prefix: Path) -> None:
    data = home / ".local" / "share"
    left = [str(path) for path in (
        prefix, Path(f"{prefix}.neu"), Path(f"{prefix}.alt"),
        home / ".local" / "bin" / SLUG, home / ".local" / "bin" / "ifc-convert",
        data / "applications" / f"{SLUG}.desktop", data / "icons" / "hicolor" / "256x256" / "apps" / f"{SLUG}.png",
        data / "mime" / "packages" / f"{SLUG}.xml",
    ) if path.exists() or path.is_symlink()]
    if left:
        raise AssertionError(f"uninstall.sh left behind: {left}")
    for kept in (home / ".config" / SLUG, home / ".local" / "state" / SLUG):
        if not kept.is_dir():
            raise AssertionError(f"uninstall.sh removed the user's data: {kept}")
    print("  uninstalled: program, commands, menu entry, icon and MIME type gone; settings and logs kept ✓")


def check_tarball(tarball: Path, work: Path, source: Path) -> None:
    """Contents and permissions of the tar.gz; install, update, refusal while running, uninstall in a fake HOME."""
    top = tarball.name[:-len(".tar.gz")]
    print(f"+ checking {tarball.name} ({tarball.stat().st_size / 1024 ** 2:.0f} MB)", flush=True)
    with tarfile.open(tarball) as tar:
        members = tar.getmembers()
        names = {member.name for member in members}
        bad = [m.name for m in members if m.name.startswith("/") or ".." in m.name.split("/") or not m.name.startswith(top + "/")]
        if bad:
            raise AssertionError(f"tar.gz entries outside {top}/: {bad[:5]}")
        for name in [f"{SLUG}/{SLUG}", f"{SLUG}/ifc-convert", *TARBALL_FILES]:
            if f"{top}/{name}" not in names:
                raise AssertionError(f"{name} is missing from the tar.gz")
        for member in members:
            if member.uid or member.gid or member.uname != "root":
                raise AssertionError(f"{member.name} is owned by {member.uname}/{member.uid} instead of root")
            if member.isfile():
                expected = 0o755 if member.name in {f"{top}/{SLUG}/{SLUG}", f"{top}/{SLUG}/ifc-convert",
                                                    f"{top}/install.sh", f"{top}/uninstall.sh"} else 0o644
                if stat.S_IMODE(member.mode) != expected:
                    raise AssertionError(f"{member.name}: mode {stat.S_IMODE(member.mode):o} instead of {expected:o}")
        print(f"  {len(members)} entries under {top}/, root-owned, only executables and scripts executable ✓")
        extract = work / "extract"
        extract.mkdir()
        tar.extractall(extract, filter="data")
    folder = extract / top
    home = work / "home"
    home.mkdir()
    prefix = home / ".local" / "opt" / SLUG

    run_script(folder / "uninstall.sh", home, expect=1, env_extra={"HOME": ""})
    print("  uninstall.sh refuses with an empty HOME ✓")
    run_script(folder / "install.sh", home)
    check_installation(home, prefix)
    # The installed copy works, via the command links, with the user's folders under HOME.
    env = fake_home_env(home)
    link = home / ".local" / "bin" / "ifc-convert"
    result = subprocess.run([str(link), "--version"], capture_output=True, text=True, timeout=120, env=env)
    if result.returncode != 0 or project_version() not in result.stdout:
        raise AssertionError(f"{link} --version failed: {result.returncode} {result.stdout} {result.stderr[-1000:]}")
    target = work / "installed.glb"
    result = subprocess.run([str(link), str(source), "-o", str(target), "-f", "glb"], capture_output=True,
                            text=True, timeout=600, env=env)
    for line in (result.stdout + result.stderr).splitlines():
        print(f"  | {line}")
    if result.returncode != 0 or not target.is_file():
        raise AssertionError(f"the installed ifc-convert failed (exit code {result.returncode})")
    check_glb(target)
    log = home / ".local" / "state" / SLUG / "logs" / f"{SLUG}.log"
    if not log.is_file():
        raise AssertionError(f"the installed app did not write its log to {log}")
    (home / ".config" / SLUG).mkdir(parents=True, exist_ok=True)  # as the window would, for the settings
    print(f"  installed ifc-convert converts; log in {log.relative_to(home)} ✓")
    # Running it again is an update: the folder is replaced, nothing is left half-way.
    run_script(folder / "install.sh", home)
    check_installation(home, prefix)
    print("  update (install.sh again) ✓")
    # While the program runs from the installed folder, install.sh and uninstall.sh refuse and change nothing.
    gui = subprocess.Popen([str(prefix / SLUG)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(5)
        if gui.poll() is not None:
            raise AssertionError(f"the installed program window exited (exit code {gui.returncode})")
        output = run_script(prefix / "uninstall.sh", home, expect=1)
        if "läuft noch" not in output or not (prefix / "ifc-convert").is_file():
            raise AssertionError("uninstall.sh did not refuse while the program runs")
        output = run_script(folder / "install.sh", home, expect=1)
        if "läuft noch" not in output:
            raise AssertionError("install.sh did not refuse while the program runs")
        print("  install.sh and uninstall.sh refuse while the program runs ✓")
    finally:
        gui.kill()
        gui.wait(30)
    run_script(prefix / "uninstall.sh", home)
    check_uninstalled(home, prefix)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("app_dir", type=Path, help="the built program folder, e.g. dist/ifc-converter")
    parser.add_argument("--gui", action="store_true", help="also start the program window (offscreen)")
    parser.add_argument("--tarball", type=Path, help="also check this IFC-Converter-<version>-linux-*.tar.gz "
                                                     "(contents, install.sh, uninstall.sh in a fake HOME)")
    parser.add_argument("--work", type=Path, help="folder for the temporary files (default: the temp folder; "
                                                  "the tar.gz test needs a file system with symbolic links)")
    args = parser.parse_args()
    if sys.platform != "linux":
        raise SystemExit("this smoke test is for the Linux build")
    # No display needed: the window and anything Qt in the CLI run offscreen.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app_dir = args.app_dir.resolve()
    cli = app_dir / "ifc-convert"
    gui = app_dir / SLUG
    check_files(app_dir)
    check_shared_libraries(app_dir)
    check_cli_help(cli)

    before = snapshot(app_dir)
    temp_before = temp_entries()
    if args.work:
        args.work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ifc-smoke-", dir=args.work) as tmp:
        folder = Path(tmp) / "Projekt Müller – Prüfung"
        folder.mkdir()
        source = folder / "Wand ä.ifc"
        make_wall(source)
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        out = folder / "Ausgabe"
        out.mkdir()

        convert(cli, source, out / "wall-brep.3dm", "-f", "3dm")
        check_3dm(out / "wall-brep.3dm", rhino3dm.Brep)
        convert(cli, source, out / "wall-brep-hybrid.3dm", "-f", "3dm", "--kernel", "hybrid")
        check_3dm(out / "wall-brep-hybrid.3dm", rhino3dm.Brep)
        convert(cli, source, out / "wall-mesh.3dm", "-f", "3dm", "-g", "mesh")
        check_3dm(out / "wall-mesh.3dm", rhino3dm.Mesh)
        convert(cli, source, out / "wall.glb", "-f", "glb")
        check_glb(out / "wall.glb")
        convert(cli, source, out / "wall.obj", "-f", "obj")
        check_obj(out / "wall.obj")

        from ifc_converter.app import log_path

        walls = folder / "Wände.ifc"
        make_walls(walls)
        log = log_path()
        offset = log.stat().st_size if log.is_file() else 0
        for geometry in ("brep", "mesh"):
            target = out / f"walls-{geometry}.3dm"
            convert(cli, walls, target, "-f", "3dm", "-g", geometry, "-j", str(THREADS))
            check_large_model(target, log, offset)

        nested = folder / "Verschachtelt.ifc"
        make_nested(nested)
        check_nested(cli, nested, out)

        if hashlib.sha256(source.read_bytes()).hexdigest() != original:
            raise AssertionError("the input IFC was modified")
        print("  input IFC unchanged ✓")
        leftovers = running(cli.name)
        if leftovers:
            raise AssertionError(f"conversion processes still running: {leftovers}")
        print("  no conversion processes left over ✓")
        check_no_leftovers(temp_before, "the conversions")

        # The nested model: the 600 walls convert in under 3 s on the CI runner, before the signal arrives.
        check_cancel(cli, nested, out)
        check_killed(cli, nested, out, source)

        if args.gui:
            check_gui(gui, source)
        if args.tarball:
            work = Path(tmp) / "tarball"
            work.mkdir()
            check_tarball(args.tarball.resolve(), work, source)

    changed = sorted(set(snapshot(app_dir).items()) ^ set(before.items()))
    if changed:
        raise AssertionError(f"the app wrote into its own folder: {sorted({path for path, _ in changed})}")
    print("  program folder unchanged ✓")
    print("Linux smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
