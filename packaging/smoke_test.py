"""Smoke test of the built app: convert a generated wall with the frozen ifc-convert and check the results.

    python packaging/smoke_test.py "dist/IFC Converter"          # CLI conversions
    python packaging/smoke_test.py "dist/IFC Converter" --gui    # and start the program window

Runs with a normal Python that has ifcopenshell and rhino3dm (to create the IFC and read the .3dm);
the conversions themselves run only in the built exe. The wall is 5 x 0.2 x 3 m, and every output
must have exactly these dimensions. The input lies in a folder with spaces and umlauts, like many
real project folders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import ifcopenshell.api as api
import rhino3dm

EXPECTED = (0.2, 3.0, 5.0)  # wall dimensions in metres, sorted
TOLERANCE = 1e-6
TIMEOUT = 600
WINDOWS = sys.platform == "win32"


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
    finally:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
        else:
            process.kill()
        process.wait(30)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("app_dir", type=Path, help='the built program folder, e.g. "dist/IFC Converter"')
    parser.add_argument("--gui", action="store_true", help="also start the program window")
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
        # The default ("accurate") computes the wall with OpenCASCADE; this exercises the CGAL kernel too.
        convert(cli, source, out / "wall-brep-hybrid.3dm", "-f", "3dm", "--kernel", "hybrid")
        check_3dm(out / "wall-brep-hybrid.3dm", rhino3dm.Brep)
        convert(cli, source, out / "wall-mesh.3dm", "-f", "3dm", "-g", "mesh")
        check_3dm(out / "wall-mesh.3dm", rhino3dm.Mesh)
        convert(cli, source, out / "wall.glb", "-f", "glb")
        check_glb(out / "wall.glb")
        convert(cli, source, out / "wall.obj", "-f", "obj")
        check_obj(out / "wall.obj")

        if hashlib.sha256(source.read_bytes()).hexdigest() != original:
            raise AssertionError("the input IFC was modified")
        print("  input IFC unchanged ✓")
        leftovers = running(cli.name)
        if leftovers:
            raise AssertionError(f"conversion processes still running: {leftovers}")
        print("  no conversion processes left over ✓")

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
