import os
import random
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import child_helpers
import ifcopenshell
import ifcopenshell.api as api
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
    monkeypatch.chdir(wall_ifc.parent)  # a relative path (relpath fails across Windows drives)
    assert preview.preview_path(Path(wall_ifc.name)) == path
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


def test_preview_threads_and_the_memory_policy(monkeypatch):
    monkeypatch.setattr(converter, "default_threads", lambda: 16)
    assert preview.preview_threads() == 8 and preview.preview_threads(busy=True) == 4
    monkeypatch.setattr(converter, "default_threads", lambda: 3)
    assert preview.preview_threads() == 3 == preview.preview_threads(busy=True)
    size = 600 * 1024 ** 2
    monkeypatch.setattr(converter, "available_memory",
                        lambda: converter.MEMORY_BASE + converter.MEMORY_PER_IFC_BYTE * size)
    assert preview.fits_in_memory(size) is True
    assert preview.fits_in_memory(size, busy=True) is False  # twice the size beside a conversion
    assert preview.fits_in_memory(size // 2, busy=True) is True
    monkeypatch.setattr(converter, "available_memory", lambda: None)
    assert preview.fits_in_memory(size) is None


def test_preview_is_no_output_format(wall_ifc, tmp_path, capsys):
    assert "preview" not in FORMATS and "preview" in converter.INTERNAL_FORMATS
    with pytest.raises(SystemExit):
        build_parser().parse_args([str(wall_ifc), "-f", "preview"])
    assert "preview" not in capsys.readouterr().err.split("choose from")[-1]
    with pytest.raises(ValueError, match="möglich sind: glb, obj, 3dm, dae$"):
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


# Progressive preview: structure first, details left out, batch files.


def test_products_are_ordered_structure_first_and_details_left_out(mixed_ifc, tmp_path):
    model = ifcopenshell.open(str(mixed_ifc))
    products, details = preview.select_products(converter.shape_products(model, preview.PREVIEW_EXCLUDED))
    classes = [product.is_a() for product in products]
    assert "IfcFurniture" not in classes and len(products) == 15
    assert details == {"furniture": 3, "mep": 0, "fasteners": 0, "reinforcement": 0, "deep": 0}
    ranks = [preview.PREVIEW_CLASS_PRIORITY.index(name) for name in classes]
    assert ranks == sorted(ranks) and classes[0] == "IfcSlab" and classes[-1] == "IfcBeam"
    walls = [product.Name for product in products if product.is_a("IfcWall")]
    assert walls == ["IfcWall 0", "IfcWall 3", "IfcWall 6", "IfcWall 9"]  # model order within a class
    # Classes without a priority come last, in model order.
    model4 = ifcopenshell.file(schema="IFC4")
    things = [model4.createIfcBuildingElementProxy(), model4.createIfcDoor(), model4.createIfcSite(),
              model4.createIfcWallStandardCase(), model4.createIfcBuildingElementProxy()]
    ordered = preview.order_products(things)
    assert [thing.is_a() for thing in ordered] == ["IfcSite", "IfcWallStandardCase", "IfcDoor",
                                                   "IfcBuildingElementProxy", "IfcBuildingElementProxy"]
    assert ordered[3] is things[0] and ordered[4] is things[4]
    furniture = model.by_type("IfcFurniture")
    assert preview.select_products(furniture) == (list(furniture), dict.fromkeys(preview.DETAIL_KINDS, 0))  # details only
    mesh = _compute(mixed_ifc, tmp_path / "mixed.npz")
    assert mesh.info["details_left_out"] == 3 and mesh.info["detail_kinds"] == "furniture"
    assert mesh.info["elements"] == 15 and "partial" not in mesh.info
    assert preview.detail_kind_name("furniture") == "Möbel" and preview.detail_kind_name("mep") == "Haustechnik"


def test_deeply_nested_products_are_left_out_as_details(nested_ifc, tmp_path):
    model = ifcopenshell.open(str(nested_ifc))
    body = model.by_type("IfcGeometricRepresentationSubContext")[0]
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Plain wall")
    representation = api.run("geometry.add_wall_representation", model, context=body, length=5, height=3,
                             thickness=0.2)
    api.run("geometry.assign_representation", model, product=wall, representation=representation)
    api.run("geometry.edit_object_placement", model, product=wall)
    path = tmp_path / "deep_and_plain.ifc"
    model.write(str(path))
    mesh = _compute(path, tmp_path / "deep.npz")
    assert len(mesh.elements) == 1 and "Plain wall" in mesh.elements[0]
    assert mesh.info["details_left_out"] == 1 and mesh.info["detail_kinds"] == "deep"
    with pytest.raises(ValueError, match="keine Bauteile mit Geometrie"):  # only the deep one: nothing to show
        convert(nested_ifc, tmp_path / "only_deep.npz", fmt="preview", threads=2, kernel="hybrid")


def _batch_meshes(target: Path) -> list[PreviewMesh]:
    return [load_preview(path) for path in preview.batch_paths(target)]


def test_batches_are_written_while_computing_and_stop_once_elements_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv(preview.BATCH_ENV, "0,1")  # a batch after every shape
    target = tmp_path / "p.npz"
    (tmp_path / "p.npz.part-1-0001.npz").write_bytes(b"old attempt")
    collector = preview._Collector(25, {})
    batches = preview._Batches(target, collector, str, {"elements_total": 7})
    assert preview.batch_paths(target) == []  # the earlier attempt's files went
    for shape in (_shape(1, 5.0, 10), _shape(2, 1.0, 4), _shape(3, 9.0, 8)):  # 22 triangles: within the budget
        collector.add(shape)
        batches.check()
    paths = preview.batch_paths(target)
    assert len(paths) == 3 and [preview.batch_token(path) for path in paths] == [batches.token] * 3
    assert paths == [preview.batch_path(target, batches.token, number) for number in (1, 2, 3)]
    collector.add(_shape(5, 2.0, 6))  # 28: the 1 m element is dropped, no more batches from now on
    batches.check()
    collector.add(_shape(6, 50.0, 3))
    batches.check()
    assert batches.stopped and collector.dropping and len(preview.batch_paths(target)) == 3
    first, second, third = _batch_meshes(target)
    assert first.elements == ["1"] and second.elements == ["2"] and third.elements == ["3"]
    assert first.info == {"elements_total": 7, "batch": 1, "elements": 1, "triangles": 10}
    assert numpy.array_equal(first.origin, second.origin) and numpy.array_equal(first.origin, third.origin)
    assert first.origin.tolist() == [2.5, 2.5, 2.5]  # the centre of the first batch's bounding box
    merged = None
    for batch in (first, second, third):
        merged = preview.merge_batch(merged, batch)
    assert merged.elements == ["1", "2", "3"] and merged.triangle_count == 22
    assert merged.info == {"elements_total": 7, "batch": 3, "elements": 3, "triangles": 22, "partial": 1}
    assert merged.triangle_elements.tolist() == [0] * 10 + [1] * 4 + [2] * 8
    assert int(merged.indices.max()) == len(merged.positions) - 1 == 8
    assert preview.remove_batches(target) == 3 and preview.batch_paths(target) == []
    # Odd names beside the target are no batches of it.
    (tmp_path / "p.npz.part-1-0001.npz.part").write_bytes(b"being written")
    (tmp_path / "p.npz.part-x-0001.npz").write_bytes(b"?")
    (tmp_path / "q.npz.part-1-0001.npz").write_bytes(b"another preview")
    assert preview.batch_paths(target) == []


def test_merging_batches_of_different_origins():
    one = _cube()
    other = _cube()
    other.origin = one.origin + [1.0, 0.0, 0.0]
    other.elements = ["IfcSlab 0def"]
    merged = preview.merge_batch(preview.merge_batch(None, one), other)
    assert merged.elements == one.elements + other.elements and merged.triangle_count == 24
    assert numpy.array_equal(merged.origin, one.origin)
    assert numpy.allclose(merged.positions[8:], one.positions + [1.0, 0.0, 0.0])
    assert merged.indices[36:].tolist() == (one.indices + 8).tolist()
    assert merged.triangle_elements.tolist() == [0] * 12 + [1] * 12 and merged.info["partial"] == 1


def test_batch_settings_come_from_the_environment(monkeypatch):
    monkeypatch.delenv(preview.BATCH_ENV, raising=False)
    assert preview.batch_settings() == (preview.BATCH_SECONDS, preview.BATCH_TRIANGLES)
    monkeypatch.setenv(preview.BATCH_ENV, "0.5,1000")
    assert preview.batch_settings() == (0.5, 1000)
    monkeypatch.setenv(preview.BATCH_ENV, "nonsense")
    assert preview.batch_settings() == (preview.BATCH_SECONDS, preview.BATCH_TRIANGLES)


@pytest.mark.skipif(not (CORPUS / "duplex.ifc").exists(), reason="test corpus not on this machine")
def test_batches_of_a_real_model_merge_to_its_preview(tmp_path, monkeypatch):
    monkeypatch.setenv(preview.BATCH_ENV, "0.05,2000")
    target = tmp_path / "duplex.npz"
    mesh = _compute(CORPUS / "duplex.ifc", target)
    batches = _batch_meshes(target)
    assert len(batches) >= 3
    merged = None
    for batch in batches:
        assert batch.info["elements_total"] == len(mesh.elements) and "partial" not in batch.info
        merged = preview.merge_batch(merged, batch)
    # The shapes after the last batch are only in the final file (which replaces the batches).
    assert set(merged.elements) < set(mesh.elements) and len(merged.elements) > len(mesh.elements) * 0.8
    assert merged.triangle_count < mesh.triangle_count and len(set(merged.elements)) == len(merged.elements)
    assert merged.info["details_left_out"] == mesh.info["details_left_out"] > 0
    assert "furniture" in mesh.info["detail_kinds"]
    # Every element where the final preview has it (the origins differ: the first batch's centre).
    final = {label: _element_points(mesh, number).min(axis=0) for number, label in enumerate(mesh.elements)}
    for number, label in enumerate(merged.elements):
        assert numpy.abs(_element_points(merged, number).min(axis=0) - final[label]).max() < 1e-3, label
    # Structure first: slabs and walls are in the first batches, doors and windows later.
    classes = [label.split()[0] for label in merged.elements]
    assert classes.index("IfcSlab") < classes.index("IfcDoor") and classes.index("IfcWallStandardCase") < \
        classes.index("IfcWindow")
    assert preview.remove_batches(target) == len(batches)


def test_the_cache_key_follows_the_preview_settings(wall_ifc, own_cache, monkeypatch):
    path = preview.preview_path(wall_ifc)
    monkeypatch.setattr(preview, "PREVIEW_DETAIL_CLASSES", {"furniture": ["IfcFurnishingElement", "IfcDoor"]})
    changed = preview.preview_path(wall_ifc)
    assert changed != path
    monkeypatch.setattr(converter, "DEEP_NESTING", 50)
    assert preview.preview_path(wall_ifc) not in (path, changed)


def test_stale_batch_files_are_pruned_and_fresh_ones_kept(own_cache):
    own_cache.mkdir(parents=True)
    kept = own_cache / "a.npz"
    kept.write_bytes(b"x" * 1000)
    stale, fresh = own_cache / "a.npz.part-1-0001.npz", own_cache / "a.npz.part-2-0001.npz"
    stale.write_bytes(b"x" * 5000)  # does not count as a preview for the limit
    os.utime(stale, (1_000_000, 1_000_000))
    fresh.write_bytes(b"x" * 5000)
    assert preview.prune_cache(limit=2000) == 1
    assert kept.exists() and fresh.exists() and not stale.exists()
