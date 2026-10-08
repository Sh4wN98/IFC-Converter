"""Smoke test of the built app: convert a generated wall with the frozen ifc-convert and check the results.

    python packaging/smoke_test.py "dist/IFC Converter"          # CLI conversions
    python packaging/smoke_test.py "dist/IFC Converter" --gui    # and start the program window
    python packaging/smoke_test.py "<installed folder>" --quick --gui   # one conversion and the window

Runs with a normal Python that has ifcopenshell and rhino3dm (to create the IFC and read the .3dm);
the conversions themselves run only in the built exe. The wall is 5 x 0.2 x 3 m, and every output
must have exactly these dimensions. The input lies in a folder with spaces and umlauts, like many
real project folders. Conversions must leave nothing in the temp folder, also when they are cancelled
(Ctrl+Break), and what a killed one leaves is cleared by a later start. With the environment variable
CI set (GitHub Actions), checks that cannot run on this machine fail instead of being skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import ifcopenshell.api as api
import rhino3dm
from pe import set_stack_reserve, stack_reserve

EXPECTED = (0.2, 3.0, 5.0)  # wall dimensions in metres, sorted
TOLERANCE = 1e-6
TIMEOUT = 600
# Elements of the large test model: above rhino.MIN_PARALLEL_ELEMENTS, so the conversion child starts
# its worker processes (a daemonic child could not, and every large 3dm conversion failed in 0.2.0).
WALLS = 600
# Levels of nested type geometry in the deep test model: a 1 MB thread stack (Windows' default)
# overflows at a few thousand levels, which crashed the conversion of a real model in 0.2.1.
NESTING = 5000
STACK_RESERVE = 256 * 1024 ** 2
# Time for the control run with a 1 MB stack; the 256 MB exe converts the model in seconds.
CONTROL_TIMEOUT = 300
WINDOWS = sys.platform == "win32"
CI = bool(os.environ.get("CI"))
# Temp entries of conversions (process.py) start with this.
TEMP_PREFIX = "ifc-converter-"
# How long the app leaves temp entries alone (process.STALE_TEMP_AGE), plus a margin.
STALE_AGE = 25 * 3600
# The mutex the running app holds for the installer (app.APP_MUTEX, AppMutex in installer.iss).
APP_MUTEX = "IFCConverter-6F0B8E52-3C1D-4B7A-9E2F-5A8C1D4E7B90"


def make_wall(path: Path) -> None:
    """The 5 x 0.2 x 3 m wall of tests/conftest.py."""
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Test")
    api.run("unit.assign_unit", model)
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context,
    )
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall")
    api.run("spatial.assign_container", model, relating_structure=site, products=[wall])
    representation = api.run(
        "geometry.add_wall_representation", model, context=body, length=5, height=3, thickness=0.2
    )
    api.run("geometry.assign_representation", model, product=wall, representation=representation)
    api.run("geometry.edit_object_placement", model, product=wall)
    model.write(str(path))


def make_walls(path: Path, count: int = WALLS) -> None:
    """``count`` 2 x 0.2 x 3 m walls sharing their type's geometry: enough for the worker processes."""
    import numpy

    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Test")
    api.run("unit.assign_unit", model)
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context,
    )
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    wall_type = api.run("root.create_entity", model, ifc_class="IfcWallType", name="Wall type")
    box = api.run("geometry.add_wall_representation", model, context=body, length=2, height=3, thickness=0.2)
    api.run("geometry.assign_representation", model, product=wall_type, representation=box)
    walls = []
    for i in range(count):
        wall = api.run("root.create_entity", model, ifc_class="IfcWall", name=f"Wall {i}")
        matrix = numpy.eye(4)
        matrix[:3, 3] = (2.5 * (i % 30), 1.0 * (i // 30), 0.0)
        api.run("geometry.edit_object_placement", model, product=wall, matrix=matrix)
        walls.append(wall)
    api.run("type.assign_type", model, related_objects=walls, relating_type=wall_type)
    api.run("spatial.assign_container", model, relating_structure=site, products=walls)
    model.write(str(path))


def make_nested(path: Path, depth: int = NESTING) -> None:
    """One 10 x 0.3 x 3 m wall whose geometry is nested ``depth`` levels deep in IfcMappedItems."""
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Test")
    api.run("unit.assign_unit", model)
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context,
    )
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    origin = model.createIfcCartesianPoint((0.0, 0.0, 0.0))
    placement = model.createIfcAxis2Placement3D(origin, None, None)
    profile = model.createIfcRectangleProfileDef(
        "AREA", None, model.createIfcAxis2Placement2D(model.createIfcCartesianPoint((0.0, 0.0)), None), 10.0, 0.3
    )
    solid = model.createIfcExtrudedAreaSolid(profile, placement, model.createIfcDirection((0.0, 0.0, 1.0)), 3.0)
    representation = model.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
    operator = model.createIfcCartesianTransformationOperator3D(None, None, origin, 1.0, None)
    for _ in range(depth):
        source = model.createIfcRepresentationMap(placement, representation)
        item = model.createIfcMappedItem(source, operator)
        representation = model.createIfcShapeRepresentation(body, "Body", "MappedRepresentation", [item])
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Deep wall")
    wall.Representation = model.createIfcProductDefinitionShape(None, None, [representation])
    api.run("geometry.edit_object_placement", model, product=wall)
    api.run("spatial.assign_container", model, relating_structure=site, products=[wall])
    model.write(str(path))


def check_stacks(app_dir: Path, cli: Path, source: Path, out: Path) -> None:
    """The exes have a large default thread stack, and that is what deeply nested models need."""
    # Only our exes: an installed copy also contains Inno Setup's (32-bit) uninstaller.
    for exe in (cli, cli.with_name("IFC Converter.exe")):
        if stack_reserve(exe) != STACK_RESERVE:
            raise AssertionError(f"{exe.name}: default thread stack {stack_reserve(exe)} instead of {STACK_RESERVE}")
    print(f"  default thread stack of the exes: {STACK_RESERVE // 1024 ** 2} MB ✓")
    convert(cli, source, out / "nested.3dm", "-f", "3dm")
    objects = rhino3dm.File3dm.Read(str(out / "nested.3dm")).Objects
    if len(objects) != 1:
        raise AssertionError(f"nested.3dm: {len(objects)} objects instead of 1")
    print(f"  {NESTING} nested levels converted ✓")
    # The converter computes deeply nested elements in a thread with a stack of its own: even the
    # same exe with Windows' default 1 MB stack converts this model (up to 0.2.2 it crashed or hung).
    small = cli.with_name("ifc-convert-1mb.exe")
    shutil.copy2(cli, small)
    try:
        set_stack_reserve(small, 1024 ** 2)
        command = [str(small), str(source), "-o", str(out / "nested-1mb.3dm"), "-f", "3dm"]
        try:
            result = subprocess.run(command, capture_output=True, timeout=CONTROL_TIMEOUT, encoding="utf-8",
                                    errors="replace")
        except subprocess.TimeoutExpired:
            raise AssertionError(f"with a 1 MB stack the nested model hangs (stopped after {CONTROL_TIMEOUT} s)")
        output = result.stdout + result.stderr
        if result.returncode != 0:
            raise AssertionError(f"with a 1 MB stack the nested model failed:\n{output[-2000:]}")
        objects = rhino3dm.File3dm.Read(str(out / "nested-1mb.3dm")).Objects
        if len(objects) != 1:
            raise AssertionError(f"nested-1mb.3dm: {len(objects)} objects instead of 1")
        print("  with a 1 MB default stack the nested model converts as well ✓")
    finally:
        # A hung run leaves processes behind that lock the copy; end them before deleting it.
        subprocess.run(["taskkill", "/F", "/T", "/IM", small.name], capture_output=True)
        for _ in range(20):
            try:
                small.unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.5)


def check_network_folder(cli: Path, source: Path, out: Path, log: Path) -> None:
    """Output to a UNC path is written locally first and then copied (the admin share of this PC)."""
    drive, rest = os.path.splitdrive(str(out.resolve()))
    share = Path(f"\\\\localhost\\{drive[0]}${rest}")
    if not share.is_dir():
        if CI:
            raise AssertionError(f"{share} is not reachable, so output to a network folder cannot be checked")
        print(f"  network folder check skipped: {share} is not reachable")
        return
    offset = log.stat().st_size if log.is_file() else 0
    target = share / "wall-unc.3dm"
    convert(cli, source, target, "-f", "3dm")
    check_3dm(target, rhino3dm.Brep)
    written = log.read_bytes()[offset:].decode("utf-8", "replace") if log.is_file() else ""
    if "Wird ins Zielverzeichnis kopiert" not in written:
        raise AssertionError(f"output for {share} was not staged locally:\n{written[-2000:]}")
    print("  UNC folder: written locally, then copied ✓")


def check_large_model(path: Path, log: Path, log_offset: int) -> None:
    """All walls are in the 3dm, and the worker processes ran (no fallback to the main process)."""
    objects = rhino3dm.File3dm.Read(str(path)).Objects
    if len(objects) != WALLS:
        raise AssertionError(f"{path.name}: {len(objects)} objects instead of {WALLS}")
    written = log.read_bytes()[log_offset:].decode("utf-8", "replace") if log.is_file() else ""
    if "Worker processes failed" in written or "Traceback" in written:
        raise AssertionError(f"the worker processes failed:\n{written[-3000:]}")
    print(f"  {path.name}: {WALLS} objects, worker processes ran ✓")


def temp_entries() -> set[str]:
    """Names of the conversions' files and folders in the temp folder."""
    return {entry.name for entry in Path(tempfile.gettempdir()).glob(f"{TEMP_PREFIX}*")}


def check_no_leftovers(before: set[str], what: str) -> None:
    left = sorted(temp_entries() - before)
    if left:
        raise AssertionError(f"{what} left files in {tempfile.gettempdir()}: {left}")
    print(f"  {what}: nothing left in the temp folder ✓")


def mutex_exists() -> bool:
    """Whether some process holds APP_MUTEX (Windows only)."""
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    kernel32.OpenMutexW.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p)
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel32.OpenMutexW(0x00100000, False, APP_MUTEX)  # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(handle)
    return bool(handle)


def kill_tree(process: subprocess.Popen) -> None:
    """End ``process`` and its children at once, like the Task Manager or a power cut."""
    if WINDOWS:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def wait_for_no_processes(image: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while running(image):
        if time.monotonic() > deadline:
            raise AssertionError(f"{image} processes still running after {timeout:.0f} s: {running(image)}")
        time.sleep(0.5)


def start_interruptible(cli: Path, source: Path, target: Path, *options: str) -> subprocess.Popen:
    """Start ifc-convert in a process group of its own; returns once its conversion child runs."""
    command = [str(cli), str(source), "-o", str(target), *options]
    print("+", " ".join(command), flush=True)
    group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8",
                               errors="replace", **group)
    deadline = time.monotonic() + 120
    while len(running(cli.name)) < 2:  # the exe and the conversion child it started
        if process.poll() is not None:
            raise AssertionError(f"ifc-convert ended (exit code {process.returncode}) before it could be "
                                 f"interrupted:\n{process.stdout.read()[-2000:]}")
        if time.monotonic() > deadline:
            kill_tree(process)
            raise AssertionError("ifc-convert started no conversion child within 120 s")
        time.sleep(0.2)
    time.sleep(2)  # well inside the conversion, still reading the IFC
    if WINDOWS and not mutex_exists():
        kill_tree(process)
        raise AssertionError(f"ifc-convert does not hold the mutex {APP_MUTEX} for the installer")
    return process


def check_cancel(cli: Path, source: Path, out: Path) -> None:
    """Ctrl+Break stops a conversion like Ctrl+C: exit code 130, no output, no temp files, no processes."""
    before = temp_entries()
    target = out / "cancelled.3dm"
    process = start_interruptible(cli, source, target, "-f", "3dm")
    try:
        if WINDOWS:
            os.kill(process.pid, signal.CTRL_BREAK_EVENT)  # reaches the process group of the exe
        else:
            os.kill(process.pid, signal.SIGTERM)  # only the exe, which then stops its child itself
        output, _ = process.communicate(timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        kill_tree(process)
        raise AssertionError(f"ifc-convert could not be cancelled with Ctrl+Break: {exc}") from exc
    print(f"  exit code {process.returncode}")
    for line in output.splitlines():
        print(f"  | {line}")
    if process.returncode != 130 or "abgebrochen" not in output:
        raise AssertionError(f"Ctrl+Break: exit code {process.returncode} instead of 130 (cancelled)")
    if target.exists():
        raise AssertionError(f"the cancelled conversion left {target.name} behind")
    wait_for_no_processes(cli.name)
    check_no_leftovers(before, "a cancelled conversion")


def check_killed(cli: Path, source: Path, out: Path, quick_source: Path) -> None:
    """A killed conversion cannot clean up after itself; a later start removes what it left once it is old."""
    before = temp_entries()
    process = start_interruptible(cli, source, out / "killed.3dm", "-f", "3dm")
    kill_tree(process)
    process.communicate(timeout=60)
    wait_for_no_processes(cli.name)
    left = sorted(temp_entries() - before)
    print(f"  a killed conversion left {left or 'nothing'} in the temp folder")
    old = time.time() - STALE_AGE
    for name in left:
        entry = Path(tempfile.gettempdir()) / name
        for path in [*entry.rglob("*"), entry] if entry.is_dir() else [entry]:
            os.utime(path, (old, old))
    convert(cli, quick_source, out / "after-kill.glb", "-f", "glb")
    remaining = sorted(temp_entries() & set(left))
    if remaining:
        raise AssertionError(f"the next start did not remove what the killed conversion left: {remaining}")
    print("  the next start removed it ✓")


def check_extent(label: str, minimum, maximum) -> None:
    extent = tuple(sorted(hi - lo for lo, hi in zip(minimum, maximum)))
    if any(abs(a - b) > TOLERANCE for a, b in zip(extent, EXPECTED)):
        raise AssertionError(f"{label}: extent {extent}, expected {EXPECTED}")
    print(f"  {label}: extent {tuple(round(e, 9) for e in extent)} m ✓")


def check_3dm(path: Path, geometry_type: type) -> None:
    model = rhino3dm.File3dm.Read(str(path))
    if model is None:
        raise AssertionError(f"{path.name}: not a readable .3dm file")
    objects = list(model.Objects)
    if len(objects) != 1:
        raise AssertionError(f"{path.name}: {len(objects)} objects, expected 1")
    geometry = objects[0].Geometry
    if not isinstance(geometry, geometry_type):
        raise AssertionError(f"{path.name}: {type(geometry).__name__}, expected {geometry_type.__name__}")
    if isinstance(geometry, rhino3dm.Brep) and not geometry.IsSolid:
        raise AssertionError(f"{path.name}: the polysurface is not closed")
    strings = dict(objects[0].Attributes.GetUserStrings())
    if strings.get("IfcClass") != "IfcWall":
        raise AssertionError(f"{path.name}: user text IfcClass={strings.get('IfcClass')!r}, expected IfcWall")
    box = geometry.GetBoundingBox()
    check_extent(f"{path.name} ({type(geometry).__name__})", (box.Min.X, box.Min.Y, box.Min.Z), (box.Max.X, box.Max.Y, box.Max.Z))


def check_glb(path: Path) -> None:
    data = path.read_bytes()
    magic, _version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise AssertionError(f"{path.name}: not a binary glTF file")
    chunk_length, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A:  # "JSON"
        raise AssertionError(f"{path.name}: first chunk is not JSON")
    gltf = json.loads(data[20:20 + chunk_length])
    positions = [
        gltf["accessors"][primitive["attributes"]["POSITION"]]
        for mesh in gltf["meshes"] for primitive in mesh["primitives"]
    ]
    minimum = [min(a["min"][i] for a in positions) for i in range(3)]
    maximum = [max(a["max"][i] for a in positions) for i in range(3)]
    check_extent(path.name, minimum, maximum)


def check_obj(path: Path) -> None:
    vertices = [
        tuple(float(v) for v in line.split()[1:4])
        for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("v ")
    ]
    if not vertices:
        raise AssertionError(f"{path.name}: no vertices")
    check_extent(path.name, [min(v[i] for v in vertices) for i in range(3)], [max(v[i] for v in vertices) for i in range(3)])


def convert(cli: Path, source: Path, target: Path, *options: str) -> None:
    command = [str(cli), str(source), "-o", str(target), *options]
    print("+", " ".join(command), flush=True)
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, timeout=TIMEOUT, encoding="utf-8", errors="replace")
    print(f"  exit code {result.returncode} after {time.monotonic() - started:.1f} s")
    for line in (result.stdout + result.stderr).splitlines():
        print(f"  | {line}")
    if result.returncode != 0:
        raise AssertionError(f"ifc-convert failed with exit code {result.returncode}")
    if "✗" in result.stdout + result.stderr or "Traceback" in result.stderr:
        raise AssertionError("ifc-convert reported an error")
    if not target.is_file() or target.stat().st_size == 0:
        raise AssertionError(f"{target} was not written")


def snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    """Size and modification time of every file in ``folder``: the app must never write there."""
    return {
        str(path.relative_to(folder)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in folder.rglob("*") if path.is_file()
    }


def running(image: str) -> list[str]:
    """Process IDs of running processes with the given executable name."""
    if WINDOWS:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {image}"],
            capture_output=True, text=True,
        ).stdout
        return [line.split('","')[1] for line in out.splitlines() if line.startswith(f'"{image}"')]
    out = subprocess.run(["pgrep", "-x", image[:15]], capture_output=True, text=True).stdout
    return out.split()


def window_titles(pid: int) -> list[str]:
    """Titles of the visible top-level windows of a process (Windows only)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buffer, 512)
            if buffer.value:
                titles.append(buffer.value)
        return True

    user32.EnumWindows(callback, 0)
    return titles


def check_gui(gui: Path, source: Path) -> None:
    """Start the program window with a file argument; it must show its main window and keep running.

    On Windows the window titles are checked (a missing Qt plugin or a failing import shows an error
    dialog instead); elsewhere Qt runs offscreen and the process just has to stay alive.
    """
    print(f"+ {gui} {source}", flush=True)
    env = dict(os.environ)
    if not WINDOWS:
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    process = subprocess.Popen([str(gui), str(source)], env=env)
    titles: list[str] = []
    try:
        deadline = time.monotonic() + (60 if WINDOWS else 10)
        while time.monotonic() < deadline:
            time.sleep(1)
            if process.poll() is not None:
                raise AssertionError(f"the program window exited (exit code {process.returncode})")
            if WINDOWS:
                titles = window_titles(process.pid)
                errors = [t for t in titles if any(w in t.lower() for w in ("error", "exception", "fehler"))]
                if errors:
                    raise AssertionError(f"the program window shows an error dialog: {errors}")
                if any("Converter" in t for t in titles):
                    break
        else:
            if WINDOWS:
                raise AssertionError(f"no main window after 60 s (visible windows: {titles})")
        time.sleep(3)  # e.g. a failing import right after the window appeared
        if process.poll() is not None:
            raise AssertionError(f"the program window exited (exit code {process.returncode})")
        print(f"  running, windows: {titles or '(offscreen)'} ✓")
        if WINDOWS:
            if not mutex_exists():
                raise AssertionError(f"the program window does not hold the mutex {APP_MUTEX} for the installer")
            print("  holds the mutex for the installer ✓")
    finally:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
        else:
            process.kill()
        process.wait(30)
    if WINDOWS and mutex_exists():
        raise AssertionError("the mutex for the installer is still held after the program window ended")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("app_dir", type=Path, help='the built program folder, e.g. "dist/IFC Converter"')
    parser.add_argument("--gui", action="store_true", help="also start the program window")
    parser.add_argument("--quick", action="store_true",
                        help="only one conversion (e.g. to check an installed or updated app)")
    args = parser.parse_args()

    suffix = ".exe" if WINDOWS else ""
    cli = args.app_dir / f"ifc-convert{suffix}"
    gui = args.app_dir / f"IFC Converter{suffix}"
    for exe in (cli, gui):
        if not exe.is_file():
            raise SystemExit(f"{exe} does not exist")
    for name in ("THIRD-PARTY-NOTICES.txt", "licenses/LGPL-3.0.txt"):
        if not (args.app_dir / "_internal" / name).is_file():
            raise SystemExit(f"{name} is missing from the build")

    before = snapshot(args.app_dir)
    temp_before = temp_entries()
    with tempfile.TemporaryDirectory(prefix="ifc-smoke-") as tmp:
        folder = Path(tmp) / "Projekt Müller – Prüfung"
        folder.mkdir()
        source = folder / "Wand ä.ifc"
        make_wall(source)
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        out = folder / "Ausgabe"
        out.mkdir()

        convert(cli, source, out / "wall-brep.3dm", "-f", "3dm")
        check_3dm(out / "wall-brep.3dm", rhino3dm.Brep)
        if args.quick:
            check_no_leftovers(temp_before, "the conversion")
            if args.gui:
                check_gui(gui, source)
            print("Quick smoke test passed.")
            return 0
        # The default ("accurate") computes the wall with OpenCASCADE; this exercises the CGAL kernel too.
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
            convert(cli, walls, target, "-f", "3dm", "-g", geometry, "-j", "4")
            check_large_model(target, log, offset)

        if WINDOWS:
            check_network_folder(cli, source, out, log)
            nested = folder / "Verschachtelt.ifc"
            make_nested(nested)
            check_stacks(args.app_dir, cli, nested, out)

        if hashlib.sha256(source.read_bytes()).hexdigest() != original:
            raise AssertionError("the input IFC was modified")
        print("  input IFC unchanged ✓")
        leftovers = running(cli.name)
        if leftovers:
            raise AssertionError(f"conversion processes still running: {leftovers}")
        print("  no conversion processes left over ✓")
        check_no_leftovers(temp_before, "the conversions")

        check_cancel(cli, walls, out)
        check_killed(cli, walls, out, source)

        if args.gui:
            check_gui(gui, source)

    changed = sorted(set(snapshot(args.app_dir).items()) ^ set(before.items()))
    if changed:
        raise AssertionError(f"the app wrote into its own folder: {sorted({path for path, _ in changed})}")
    print("  program folder unchanged ✓")
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
