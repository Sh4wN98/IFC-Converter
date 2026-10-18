import os
import random
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import child_helpers
import ifcopenshell
import ifcopenshell.geom as geom
import numpy
import pytest

from ifc_converter import FORMATS, converter, preview, process
from ifc_converter.cli import build_parser
from ifc_converter.converter import convert
from ifc_converter.preview import PREVIEW_FORMAT_VERSION, PreviewMesh, load_preview, save_preview
from ifc_converter.process import Cancelled


def _cube() -> PreviewMesh:
    corners = numpy.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)], numpy.float32)
    faces = [(0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6), (0, 1, 4), (1, 5, 4),
             (2, 6, 3), (3, 6, 7), (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)]
    return PreviewMesh(
        positions=corners, colors=numpy.full((8, 4), 200, numpy.uint8),
        indices=numpy.array(faces, numpy.uint32).ravel(), triangle_elements=numpy.zeros(12, numpy.uint32),
        elements=["IfcWall 0abc „Wand“"], origin=numpy.array([500000.0, 5400000.0, 120.0]),
        info={"source": "Haus.ifc", "elements": 1, "scale": 0.5},
    )


def test_a_preview_survives_the_round_trip(tmp_path):
    mesh = _cube()
    save_preview(mesh, tmp_path / "p.npz")
    loaded = load_preview(tmp_path / "p.npz")
    assert loaded is not None and loaded.triangle_count == 12
    assert numpy.array_equal(loaded.positions, mesh.positions) and numpy.array_equal(loaded.indices, mesh.indices)
    assert loaded.origin.tolist() == [500000.0, 5400000.0, 120.0]
    assert loaded.elements == ["IfcWall 0abc „Wand“"]
    assert loaded.info == {"source": "Haus.ifc", "elements": 1, "scale": 0.5}
    lo, hi = loaded.bounds()
    assert lo.tolist() == [0, 0, 0] and hi.tolist() == [1, 1, 1]


def test_damaged_or_foreign_previews_are_ignored(tmp_path):
    (tmp_path / "junk.npz").write_bytes(b"not a zip")
    assert load_preview(tmp_path / "junk.npz") is None
    assert load_preview(tmp_path / "missing.npz") is None
    mesh = _cube()
    mesh.indices = mesh.indices.copy()
    mesh.indices[0] = 99  # points past the vertices
    save_preview(mesh, tmp_path / "bad.npz")
    assert load_preview(tmp_path / "bad.npz") is None
    numpy.savez(tmp_path / "old.npz", version=numpy.array(PREVIEW_FORMAT_VERSION + 1))
    assert load_preview(tmp_path / "old.npz") is None


# Computing previews (write_preview, compute_preview) and their cache.

CORPUS = Path("/run/media/shawn/Jonas1TB/claude/ifc-testdata/files")


@pytest.fixture(autouse=True)
def own_cache(tmp_path, monkeypatch):
    """Keep the previews and remembered elements of a test out of the developer's own folders."""
    folder = tmp_path / "cache" / preview.PREVIEW_CACHE_NAME
    monkeypatch.setattr(preview, "preview_cache_dir", lambda: folder)
    monkeypatch.setattr(process, "quarantine_path", lambda: tmp_path / "state" / process.QUARANTINE_NAME)
    return folder


def _compute(path: Path, out: Path) -> PreviewMesh:
    result = convert(path, out, fmt="preview", threads=2, kernel=preview.PREVIEW_KERNEL)
    assert result.output == out
    mesh = load_preview(out)
    assert mesh is not None
    return mesh


def _kernel_bounds(path: Path, ifc_class: str) -> tuple[numpy.ndarray, numpy.ndarray]:
    """The world-coordinate bounding box of the first ``ifc_class`` element, straight from the kernel."""
    model = ifcopenshell.open(str(path))
    shape = _kernel_shape(model.by_type(ifc_class)[0])
    points = numpy.array(shape.geometry.verts, numpy.float64).reshape(-1, 3)
    return points.min(axis=0), points.max(axis=0)


def _kernel_shape(product):
    return geom.create_shape(
        preview.preview_settings(), product, converter._body_representation(product),
        geometry_library=converter.LIBRARIES[preview.PREVIEW_KERNEL],
    )


def _element_points(mesh: PreviewMesh, number: int) -> numpy.ndarray:
    """The model coordinates (float64) of the vertices of element ``number``."""
    triangles = mesh.indices.reshape(-1, 3)[mesh.triangle_elements == number]
    return mesh.positions[numpy.unique(triangles)].astype(numpy.float64) + mesh.origin


def test_a_georeferenced_wall_keeps_its_world_coordinates_within_a_millimetre(georeferenced_ifc, tmp_path):
    mesh = _compute(georeferenced_ifc, tmp_path / "wall.npz")
    assert mesh.triangle_count >= 12 and mesh.positions.dtype == numpy.float32
    assert mesh.elements == [converter.product_label(ifcopenshell.open(str(georeferenced_ifc)).by_type("IfcWall")[0])]
    assert mesh.triangle_elements.tolist() == [0] * mesh.triangle_count
    low, high = _kernel_bounds(georeferenced_ifc, "IfcWall")
    points = _element_points(mesh, 0)
    assert numpy.abs(points.min(axis=0) - low).max() < 0.001 and numpy.abs(points.max(axis=0) - high).max() < 0.001
    assert low[0] > 500_000  # really far out
    # The origin is the centre of the model, so the float32 positions are small.
    assert numpy.allclose(mesh.origin, (low + high) / 2, atol=1e-6)
    assert numpy.abs(mesh.positions).max() < 3
    assert len({tuple(color) for color in mesh.colors.tolist()}) == 1 and mesh.colors[0, 3] == 255
    info = mesh.info
    assert info["source"] == "wall.ifc" and info["schema"] == "IFC4"
    assert info["elements"] == 1 and info["triangles"] == mesh.triangle_count and info["left_out"] == 0
    assert info["seconds"] >= info["read_seconds"] >= 0 and info["geometry_seconds"] >= 0


def test_openings_are_cut_and_rooms_and_openings_left_out(opening_ifc, tmp_path):
    mesh = _compute(opening_ifc, tmp_path / "opening.npz")
    assert [label.split()[0] for label in mesh.elements] == ["IfcWall"]
    # The wall's front face (5 x 3 m) has a hole of 1 x 1 m.
    points = mesh.positions.astype(numpy.float64)[mesh.indices.reshape(-1, 3)]
    normals = numpy.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    front = points[:, :, 1].max(axis=1) - points[:, :, 1].min(axis=1) < 1e-6
    front &= numpy.isclose(points[:, 0, 1], points[:, :, 1].min())
    area = numpy.linalg.norm(normals[front], axis=1).sum() / 2
    assert area == pytest.approx(14.0, abs=1e-3)


def test_colours_come_from_the_styles(storey_ifc, tmp_path):
    mesh = _compute(storey_ifc, tmp_path / "storey.npz")
    classes = [label.split()[0] for label in mesh.elements]
    assert sorted(classes) == ["IfcSlab", "IfcWall"]
    wall = classes.index("IfcWall")
    corners = mesh.indices.reshape(-1, 3)[mesh.triangle_elements == wall]
    assert {tuple(color) for color in mesh.colors[corners.reshape(-1)].tolist()} == {(255, 0, 0, 255)}
    assert int(mesh.triangle_elements.max()) == len(mesh.elements) - 1


def _material(r, g, b, transparency=0.0):
    return SimpleNamespace(
        name="m", transparency=transparency,
        diffuse=SimpleNamespace(r=lambda: r, g=lambda: g, b=lambda: b),
    )


def test_vertices_shared_by_two_materials_get_one_colour_each():
    # Two triangles sharing an edge: an opaque red one and a half transparent blue one.
    points = numpy.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], numpy.float64)
    triangles = numpy.array([[0, 1, 2], [1, 3, 2]], numpy.int32)
    geometry = SimpleNamespace(
        materials=[_material(1, 0, 0), _material(0, 0, 1, 0.5)],
        material_ids_buffer=numpy.array([0, 1], numpy.int32).tobytes(),
    )
    vertices, colors, faces = preview._colored(geometry, points, triangles)
    assert len(vertices) == 6  # the shared edge's two vertices twice
    first, second = (colors[faces[0]].tolist(), colors[faces[1]].tolist())
    assert first == [[255, 0, 0, 255]] * 3 and second == [[0, 0, 255, 128]] * 3
    assert numpy.array_equal(vertices[faces], points[triangles])
    # Faces without a material take the main one; one material needs no split.
    geometry.material_ids_buffer = numpy.array([1, -1], numpy.int32).tobytes()
    vertices, colors, faces = preview._colored(geometry, points, triangles)
    assert len(vertices) == 4 and colors.tolist() == [[0, 0, 255, 128]] * 4
    geometry.materials = []
    assert preview._colored(geometry, points, triangles)[1].tolist() == [list(preview.DEFAULT_COLOR)] * 4


def _shape(id_: int, size: float, triangles: int):
    """A fake kernel shape: ``triangles`` triangles in a box of ``size`` metres."""
    points = numpy.array([[0, 0, 0], [size, 0, 0], [0, size, size]], numpy.float64)
    return SimpleNamespace(id=id_, geometry=SimpleNamespace(
        verts_buffer=points.tobytes(), faces_buffer=numpy.tile([0, 1, 2], triangles).astype(numpy.int32).tobytes(),
        materials=[], material_ids_buffer=b"",
    ))


def test_beyond_the_budget_the_smallest_elements_are_left_out_in_any_order():
    # (id, size, triangles): 40 triangles within a budget of 25.
    shapes = [_shape(1, 5.0, 10), _shape(2, 1.0, 4), _shape(3, 9.0, 8), _shape(4, 0.5, 2), _shape(5, 2.0, 6),
              _shape(6, 50.0, 26), _shape(7, 0.1, 2)]
    results = set()
    for seed in range(20):
        collector = preview._Collector(25, {id_: id_ for id_ in range(10)})
        for shape in random.Random(seed).sample(shapes, len(shapes)):
            collector.add(shape)
        mesh = collector.mesh(str)
        results.add((tuple(mesh.elements), collector.left_out, mesh.triangle_count))
    # The largest element alone is over the budget; then 9 m, 5 m and 2 m fit (24), 1 m would not.
    assert results == {(("1", "3", "5"), 4, 24)}


def test_the_budget_holds_for_a_real_model(mixed_ifc, tmp_path, monkeypatch):
    full = _compute(mixed_ifc, tmp_path / "full.npz")
    monkeypatch.setattr(preview, "PREVIEW_TRIANGLES", full.triangle_count // 2)
    half = _compute(mixed_ifc, tmp_path / "half.npz")
    assert 0 < half.triangle_count <= full.triangle_count // 2
    assert half.info["left_out"] == len(full.elements) - len(half.elements) > 0
    assert set(half.elements) < set(full.elements)
    # Elements left out are no elements without geometry: the conversion counts them all.
    result = convert(mixed_ifc, tmp_path / "again.npz", fmt="preview", threads=2, kernel="hybrid")
    assert (result.elements, result.skipped) == (len(full.elements), 0)
    monkeypatch.setattr(preview, "PREVIEW_TRIANGLES", 5)  # fewer than any element has
    with pytest.raises(ValueError, match="Zu viele Dreiecke für die Vorschau"):
        convert(mixed_ifc, tmp_path / "none.npz", fmt="preview", threads=2, kernel="hybrid")
    assert not (tmp_path / "none.npz").exists()


@pytest.mark.skipif(not (CORPUS / "duplex.ifc").exists(), reason="test corpus not on this machine")
def test_preview_of_a_real_model(tmp_path):
    source = CORPUS / "duplex.ifc"
    mesh = _compute(source, tmp_path / "duplex.npz")
    assert mesh.triangle_count > 10_000 and len(mesh.elements) > 100
    assert not [label for label in mesh.elements if label.startswith(("IfcSpace", "IfcOpeningElement"))]
    assert len(numpy.unique(mesh.colors.view(numpy.uint32))) > 5
    assert (mesh.colors[:, 3] < 255).any()  # glass
    assert int(mesh.triangle_elements.max()) == len(mesh.elements) - 1
    assert mesh.info["triangles"] == mesh.triangle_count and mesh.info["schema"] == "IFC2X3"
    # Each element where the kernel puts it (some of each class).
    model = ifcopenshell.open(str(source))
    numbers = {label.split()[1]: number for number, label in enumerate(mesh.elements)}
    checked = set()
    for product in model.by_type("IfcBuildingElement"):
        if product.is_a() in checked or product.GlobalId not in numbers:
            continue
        checked.add(product.is_a())
        shape = _kernel_shape(product)
        points = numpy.array(shape.geometry.verts).reshape(-1, 3)
        ours = _element_points(mesh, numbers[product.GlobalId])
        assert numpy.abs(ours.min(axis=0) - points.min(axis=0)).max() < 0.001, product
        assert numpy.abs(ours.max(axis=0) - points.max(axis=0)).max() < 0.001, product
    assert len(checked) >= 5


def test_the_cache_key_follows_the_file(wall_ifc, own_cache, monkeypatch):
    path = preview.preview_path(wall_ifc)
    assert path.parent == own_cache != wall_ifc.parent and path.suffix == ".npz"
    assert preview.preview_path(wall_ifc) == path
    assert preview.preview_path(Path(os.path.relpath(wall_ifc))) == path
    stat = wall_ifc.stat()
    os.utime(wall_ifc, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    changed = preview.preview_path(wall_ifc)
    assert changed != path
    with open(wall_ifc, "ab") as file:
        file.write(b"\n")
    os.utime(wall_ifc, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert preview.preview_path(wall_ifc) not in (path, changed)
    current = preview.preview_path(wall_ifc)
    monkeypatch.setattr(preview, "PREVIEW_FORMAT_VERSION", preview.PREVIEW_FORMAT_VERSION + 1)
    assert preview.preview_path(wall_ifc) != current
    monkeypatch.undo()
    monkeypatch.setattr(preview, "preview_cache_dir", lambda: own_cache)
    monkeypatch.setattr(ifcopenshell, "version", "99.0.0")
    assert preview.preview_path(wall_ifc) != current
    with pytest.raises(OSError):
        preview.preview_path(wall_ifc.with_name("missing.ifc"))


def test_cached_previews_are_found_and_damaged_ones_removed(wall_ifc, own_cache):
    assert preview.cached_preview(wall_ifc) is None
    assert preview.cached_preview(wall_ifc.with_name("missing.ifc")) is None
    path = preview.preview_path(wall_ifc)
    own_cache.mkdir(parents=True)
    save_preview(_cube(), path)
    os.utime(path, (1_000_000, 1_000_000))
    assert preview.cached_preview(wall_ifc) == path
    assert path.stat().st_mtime > 1_000_000  # used now
    path.write_bytes(b"broken")
    assert preview.cached_preview(wall_ifc) is None and not path.exists()
    numpy.savez(path, version=numpy.array(PREVIEW_FORMAT_VERSION + 1))
    assert preview.cached_preview(wall_ifc) is None and not path.exists()


def test_the_cache_keeps_the_previews_used_last_within_its_size(own_cache):
    assert preview.prune_cache() == 0  # no folder yet
    own_cache.mkdir(parents=True)
    paths = []
    for number in range(5):
        path = own_cache / f"{number}.npz"
        path.write_bytes(b"x" * 1000)
        os.utime(path, (1_000_000 + number, 1_000_000 + number))
        paths.append(path)
    stale, fresh = own_cache / "old.npz.part", own_cache / "new.npz.part"
    stale.write_bytes(b"x")
    os.utime(stale, (1_000_000, 1_000_000))
    fresh.write_bytes(b"x")
    other = own_cache / "notes.txt"
    other.write_text("not ours")
    # The oldest (0) is kept as asked, so 1 and 2 go.
    assert preview.prune_cache(limit=3000, keep=paths[0]) == 3
    assert [path.exists() for path in paths] == [True, False, False, True, True]
    assert not stale.exists() and fresh.exists() and other.exists()


def test_compute_preview_runs_in_a_child_and_lands_in_the_cache(wall_ifc, own_cache, monkeypatch):
    monkeypatch.setattr(preview, "PREVIEW_CACHE_BYTES", 0)  # prunes everything except the new one
    own_cache.mkdir(parents=True)
    (own_cache / "older.npz").write_bytes(b"x")
    progress, phases = [], []
    path = preview.compute_preview(wall_ifc, progress=progress.append, status=lambda phase, text: phases.append(phase))
    assert path == preview.preview_path(wall_ifc) and preview.cached_preview(wall_ifc) == path
    mesh = load_preview(path)
    assert mesh.info["elements"] == 1 and mesh.triangle_count >= 12
    assert progress[0] == 0 and progress[-1] == 100
    assert phases[0] == "read" and "write" in phases
    assert sorted(own_cache.iterdir()) == [path]


def test_compute_preview_can_be_cancelled(wall_ifc, own_cache):
    reading = threading.Event()
    with pytest.raises(Cancelled):
        preview.compute_preview(wall_ifc, cancelled=reading.is_set, status=lambda phase, text: reading.set())
    assert reading.is_set()
    assert not own_cache.exists() or not list(own_cache.iterdir())


def test_compute_preview_passes_few_threads_and_the_fast_kernel(wall_ifc, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(process, "convert_in_child", lambda *args, **options: calls.append((args, options)))
    preview.compute_preview(wall_ifc, tmp_path / "p.npz")
    (path, output, fmt, threads, *_), options = calls[0]
    assert (output, fmt, options["kernel"]) == (tmp_path / "p.npz", "preview", "hybrid")
    assert 1 <= threads == preview.preview_threads() <= preview.PREVIEW_THREADS
    assert options["low_priority"] is True


def test_preview_is_no_output_format(wall_ifc, tmp_path, capsys):
    assert "preview" not in FORMATS and "preview" in converter.INTERNAL_FORMATS
    with pytest.raises(SystemExit):
        build_parser().parse_args([str(wall_ifc), "-f", "preview"])
    assert "preview" not in capsys.readouterr().err.split("choose from")[-1]
    with pytest.raises(ValueError, match="möglich sind: glb, obj, 3dm$"):
        convert(wall_ifc, fmt="fbx")
    # Without an output path it goes beside the IFC, like the formats (only the app's cache is used).
    assert convert(wall_ifc, fmt="preview").output == wall_ifc.with_suffix(".npz")


def test_a_crash_of_the_fast_kernel_goes_to_opencascade_at_once_if_asked():
    def crash():
        crashed = process.ConversionCrashed(-11)
        crashed.position = ("chunk", [7, 8], "")
        return crashed

    options, isolate = {"kernel": "hybrid"}, set()
    assert process._recover(crash(), options, isolate, {}, opencascade_first=True) == process.RETRY_MESSAGE
    assert options["kernel"] == "opencascade" and not isolate
    # Under OpenCASCADE (or without the option) the elements are narrowed down as before.
    assert "einzeln" in process._recover(crash(), options, isolate, {}, opencascade_first=True)
    assert isolate == {7, 8}
    options, isolate = {"kernel": "hybrid"}, set()
    assert "einzeln" in process._recover(crash(), options, isolate, {}) and options["kernel"] == "hybrid"
    # Running out of memory is no crash of the kernel.
    killed = process.ConversionCrashed(-9)
    killed.position = ("chunk", [7], "")
    assert process._recover(killed, {"kernel": "hybrid"}, set(), {}, opencascade_first=True) is None


@pytest.mark.skipif(sys.platform == "win32", reason="crashes with POSIX signals")
def test_a_preview_whose_fast_kernel_crashes_is_computed_with_opencascade(many_walls_ifc, tmp_path):
    target = tmp_path / "walls.npz"
    messages = []
    result = process.convert_in_child(
        many_walls_ifc, target, "preview", 2, on_retry=messages.append, opencascade_first=True,
        func=child_helpers.crash_on_wall_7_unless_opencascade, kernel=preview.PREVIEW_KERNEL,
    )
    assert messages == [process.RETRY_MESSAGE]
    assert target.with_suffix(".attempts").read_text().split() == ["hybrid", "opencascade"]
    assert (result.elements, result.crashed) == (600, [])
    assert load_preview(target).info["elements"] == 600
