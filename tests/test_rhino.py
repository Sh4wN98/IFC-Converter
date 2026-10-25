import math
from types import SimpleNamespace

import numpy
import pytest
import rhino3dm

from ifc_converter import convert, rhino
from ifc_converter.cli import main


def _read(path):
    rhino = rhino3dm.File3dm.Read(str(path))
    assert rhino is not None
    return rhino


def _layer_paths(rhino):
    return {layer.Index: layer.FullPath for layer in rhino.Layers}


def _size(geometry):
    box = geometry.GetBoundingBox()
    return (box.Max.X - box.Min.X, box.Max.Y - box.Min.Y, box.Max.Z - box.Min.Z)


def test_wall_is_written_as_mesh(wall_ifc):
    progress = []
    result = convert(wall_ifc, fmt="3dm", progress=progress.append, geometry="mesh")

    assert result.output == wall_ifc.with_suffix(".3dm")
    assert result.elements == 1
    assert progress[-1] == 100
    assert progress == sorted(progress)

    rhino = _read(result.output)
    assert rhino.Settings.ModelUnitSystem == rhino3dm.UnitSystem.Meters
    assert len(rhino.Objects) == 1

    obj = rhino.Objects[0]
    mesh = obj.Geometry
    assert isinstance(mesh, rhino3dm.Mesh)
    # A box has only sharp edges: each of its 6 faces keeps its own 4 vertices.
    assert len(mesh.Normals) == len(mesh.Vertices) == 24
    assert _size(mesh) == pytest.approx((5, 0.2, 3))


def test_wall_is_a_closed_polysurface(wall_ifc):
    progress = []
    result = convert(wall_ifc, fmt="3dm", progress=progress.append)
    assert result.elements == 1
    assert progress[-1] == 100 and progress == sorted(progress)

    brep = _read(result.output).Objects[0].Geometry
    assert isinstance(brep, rhino3dm.Brep)
    assert brep.IsValid and brep.IsSolid
    assert len(brep.Faces) == 6
    assert _size(brep) == pytest.approx((5, 0.2, 3))


def test_opening_becomes_a_hole_in_the_polysurface(opening_ifc):
    rhino_file = _read(convert(opening_ifc, fmt="3dm").output)
    wall = next(o.Geometry for o in rhino_file.Objects if o.Attributes.GetUserString("IfcClass") == "IfcWall")
    assert isinstance(wall, rhino3dm.Brep)
    assert wall.IsValid and wall.IsSolid
    # front and back face with the hole, four outer sides, four reveals
    assert len(wall.Faces) == 10
    assert sorted(len(face.Loops) for face in wall.Faces) == [1] * 8 + [2] * 2


def test_detailed_elements_fall_back_to_meshes(storey_ifc, monkeypatch):
    monkeypatch.setattr(rhino, "MAX_BREP_FACES", 12)  # wall and slab have 12 triangles each
    rhino_file = _read(convert(storey_ifc, fmt="3dm").output)
    assert {type(o.Geometry) for o in rhino_file.Objects} == {rhino3dm.Brep}

    monkeypatch.setattr(rhino, "MAX_BREP_FACES", 11)
    progress = []
    result = convert(storey_ifc, fmt="3dm", progress=progress.append)
    assert result.elements == 2
    assert progress[-1] == 100 and progress == sorted(progress)
    rhino_file = _read(result.output)
    objects = {o.Attributes.GetUserString("IfcClass"): o for o in rhino_file.Objects}
    assert {type(o.Geometry) for o in objects.values()} == {rhino3dm.Mesh}
    # the fallback keeps layer, colour and user text
    wall = objects["IfcWall"]
    assert _layer_paths(rhino_file)[wall.Attributes.LayerIndex] == "EG::IfcWall"
    assert wall.Attributes.ObjectColor[:3] == (255, 0, 0)
    assert wall.Attributes.GetUserString("Pset_WallCommon.Reference") == "AW-01"


def test_invalid_polysurface_falls_back_to_mesh(wall_ifc, monkeypatch):
    monkeypatch.setattr(rhino, "planar_polysurface", lambda *args: None)
    rhino_file = _read(convert(wall_ifc, fmt="3dm").output)
    assert len(rhino_file.Objects) == 1
    assert isinstance(rhino_file.Objects[0].Geometry, rhino3dm.Mesh)


def test_invalid_geometry_is_rejected(wall_ifc):
    with pytest.raises(ValueError):
        convert(wall_ifc, fmt="3dm", geometry="nurbs")


def test_wall_without_storey_goes_to_fallback_layer(wall_ifc):
    rhino = _read(convert(wall_ifc, fmt="3dm").output)
    obj = rhino.Objects[0]
    assert _layer_paths(rhino)[obj.Attributes.LayerIndex] == "Ohne Geschoss::IfcWall"


def test_storey_and_class_layers(storey_ifc):
    result = convert(storey_ifc, fmt="3dm")
    assert result.elements == 2

    rhino = _read(result.output)
    paths = set(_layer_paths(rhino).values())
    assert {"EG", "EG::IfcWall", "EG::IfcSlab"} <= paths

    layers = {layer.FullPath: layer for layer in rhino.Layers}
    assert layers["EG::IfcWall"].ParentLayerId == layers["EG"].Id
    assert layers["EG::IfcWall"].Color[:3] == (255, 0, 0)


def test_object_attributes(storey_ifc):
    rhino = _read(convert(storey_ifc, fmt="3dm").output)
    objects = {obj.Attributes.GetUserString("IfcClass"): obj.Attributes for obj in rhino.Objects}

    wall = objects["IfcWall"]
    assert wall.Name == "Wall"
    assert wall.GetUserString("IfcName") == "Wall"
    assert len(wall.GetUserString("IfcGlobalId")) == 22
    assert wall.GetUserString("Pset_WallCommon.IsExternal") == "True"
    assert wall.GetUserString("Pset_WallCommon.Reference") == "AW-01"
    assert wall.ColorSource == rhino3dm.ObjectColorSource.ColorFromObject
    assert wall.ObjectColor[:3] == (255, 0, 0)
    assert rhino.Materials[wall.MaterialIndex].DiffuseColor[:3] == (255, 0, 0)

    slab = objects["IfcSlab"]
    assert slab.Name == slab.GetUserString("IfcGlobalId")


@pytest.mark.parametrize("geometry", ["brep", "mesh"])
def test_progress_abort_propagates(wall_ifc, geometry):
    def abort(percent):
        if percent > 0:
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        convert(wall_ifc, fmt="3dm", progress=abort, geometry=geometry)


def test_cli_writes_3dm(wall_ifc, tmp_path, capsys):
    out_dir = tmp_path / "converted"
    assert main([str(wall_ifc), "-f", "3dm", "-d", str(out_dir)]) == 0
    assert _read(out_dir / "wall.3dm") is not None
    assert "1 elements" in capsys.readouterr().out


def test_cli_geometry_flag(wall_ifc, tmp_path):
    target = tmp_path / "wall.3dm"
    assert main([str(wall_ifc), "-f", "3dm", "-o", str(target), "--geometry", "mesh"]) == 0
    assert isinstance(_read(target).Objects[0].Geometry, rhino3dm.Mesh)
    assert main([str(wall_ifc), "-f", "3dm", "-o", str(target), "--overwrite"]) == 0
    assert isinstance(_read(target).Objects[0].Geometry, rhino3dm.Brep)
    with pytest.raises(SystemExit):
        main([str(wall_ifc), "--geometry", "nurbs"])


@pytest.mark.parametrize("geometry", ["brep", "mesh"])
def test_georeferenced_coordinates_keep_their_precision(georeferenced_ifc, geometry):
    # Single-precision vertices would collapse the 0.2 m thickness at a northing of 5.4 million metres.
    result = convert(georeferenced_ifc, fmt="3dm", geometry=geometry)
    obj = _read(result.output).Objects[0]
    box = obj.Geometry.GetBoundingBox()
    assert abs(box.Min.X - 512345.678) < 1e-6 and abs(box.Min.Y - 5423456.789) < 1e-6
    assert all(abs(a - b) < 1e-6 for a, b in zip(_size(obj.Geometry), (5, 0.2, 3)))


def _objects_by_layer(rhino):
    paths = _layer_paths(rhino)
    objects = {}
    for obj in rhino.Objects:
        objects.setdefault(paths[obj.Attributes.LayerIndex], []).append(obj)
    return objects


def test_bridge_layers_follow_facility_and_parts(bridge_ifc):
    result = convert(bridge_ifc, fmt="3dm")
    assert result.elements == 5

    rhino = _read(result.output)
    objects = _objects_by_layer(rhino)
    # Unnamed parts are named after their predefined type, made unique among their siblings.
    # A part with geometry of its own is drawn in its own layer.
    assert {path: len(objs) for path, objs in objects.items()} == {
        "River bridge::Deck::IfcBridgePart": 1,
        "River bridge::Substructure::PIER::IfcColumn": 1,
        "River bridge::Substructure::PIER (2)::IfcColumn": 1,
        "River bridge::IfcBeam": 1,
        "Ohne Geschoss::IfcBuildingElementProxy": 1,
    }
    # The spatial layers come first, in the order of the spatial structure.
    assert [layer.FullPath for layer in rhino.Layers if "::Ifc" not in layer.FullPath] == [
        "River bridge", "River bridge::Deck", "River bridge::Substructure",
        "River bridge::Substructure::PIER", "River bridge::Substructure::PIER (2)", "Ohne Geschoss",
    ]
    layers = {layer.FullPath: layer for layer in rhino.Layers}
    assert layers["River bridge::Substructure::PIER"].ParentLayerId == layers["River bridge::Substructure"].Id
    assert objects["River bridge::IfcBeam"][0].Attributes.GetUserString("IfcName") == "Deck beam"


def test_several_buildings_become_the_top_level(buildings_ifc):
    rhino = _read(convert(buildings_ifc, fmt="3dm").output)
    objects = _objects_by_layer(rhino)
    assert set(objects) == {"Haus A::EG::IfcWall", "Haus B::EG::IfcWall", "Haus A::IfcSlab", "Haus A::EG::IfcGrid"}
    # The storey layers come first, as before: created up front, grouped by building.
    assert [layer.FullPath for layer in rhino.Layers][:4] == ["Haus A", "Haus A::EG", "Haus B", "Haus B::EG"]


def test_grid_axes_become_grouped_lines(buildings_ifc):
    rhino = _read(convert(buildings_ifc, fmt="3dm").output)
    lines = _objects_by_layer(rhino)["Haus A::EG::IfcGrid"]
    assert len(lines) == 2
    assert all(isinstance(line.Geometry, rhino3dm.PolylineCurve) for line in lines)
    assert [line.Geometry.ToPolyline().Length for line in lines] == pytest.approx([10, 10])
    assert lines[0].Attributes.GetGroupList() == lines[1].Attributes.GetGroupList() == (0,)
    assert rhino.Groups.FindIndex(0).Name == "Grid"


@pytest.mark.parametrize("geometry", ["brep", "mesh"])  # world and placed (local) coordinates
def test_alignments_become_polylines(alignment_ifc, geometry):
    result = convert(alignment_ifc, fmt="3dm", geometry=geometry)
    assert result.elements == 2

    rhino = _read(result.output)
    curves = {obj.Attributes.Name: obj for obj in rhino.Objects}
    assert {_layer_paths(rhino)[obj.Attributes.LayerIndex] for obj in curves.values()} == {"Achsen::IfcAlignment"}
    for obj in curves.values():
        assert isinstance(obj.Geometry, rhino3dm.PolylineCurve)
        assert obj.Attributes.GetUserString("IfcClass") == "IfcAlignment"
        assert len(obj.Attributes.GetUserString("IfcGlobalId")) == 22

    # The 3D axis: 80 m straight, a quarter circle of 20 m radius, then straight again up to the
    # end of the vertical layout at 191 m, rising to 302 m.
    axis = curves["Main axis"].Geometry
    box = axis.GetBoundingBox()
    assert axis.PointCount > 20
    assert axis.ToPolyline().Length == pytest.approx(191, abs=0.5)
    assert (box.Min.X, box.Min.Y, box.Min.Z) == pytest.approx((512000, 5423000, 300))
    assert 301.5 < box.Max.Z < 302.1

    # The plan-only polyline keeps its vertices to the millimetre at UTM coordinates.
    ramp = curves["Ramp"].Geometry
    assert ramp.PointCount == 3
    assert ramp.ToPolyline().Length == pytest.approx(150.5)
    assert (ramp.Point(2).X, ramp.Point(2).Y) == (512100.0, 5422950.5)


def test_alignment_layout_parts_are_not_drawn(alignment_ifc):
    # Their geometry repeats the axis in plan, or as a profile in distance/height coordinates.
    rhino = _read(convert(alignment_ifc, fmt="3dm").output)
    assert {obj.Attributes.GetUserString("IfcClass") for obj in rhino.Objects} == {"IfcAlignment"}


def _prism(sides):
    """A prism of radius 1 and height 2 as the kernel delivers it: each planar face with its own vertices."""
    ring = [(math.cos(2 * math.pi * k / sides), math.sin(2 * math.pi * k / sides)) for k in range(sides)]
    points, triangles = [], []

    def face(corners):  # a planar polygon, triangulated as a fan
        start = len(points)
        points.extend(corners)
        triangles.extend((start, start + k, start + k + 1) for k in range(1, len(corners) - 1))

    for k in range(sides):
        (x0, y0), (x1, y1) = ring[k], ring[(k + 1) % sides]
        face([(x0, y0, 0), (x1, y1, 0), (x1, y1, 2), (x0, y0, 2)])
    face([(x, y, 0) for x, y in reversed(ring)])
    face([(x, y, 2) for x, y in ring])
    points, triangles = numpy.array(points, dtype=float), numpy.array(triangles, dtype=numpy.int32)
    return SimpleNamespace(
        verts=tuple(points.ravel()), faces=tuple(triangles.ravel()),
        verts_buffer=points.tobytes(), faces_buffer=triangles.tobytes(),
    )


def _vertices_and_normals(mesh):
    points = [(p.X, p.Y, p.Z) for p in mesh.Vertices.ToPoint3dArray()]
    normals = [(n.X, n.Y, n.Z) for n in mesh.Normals]
    return points, normals


def test_curved_surfaces_are_welded_and_shade_smoothly():
    prism = _prism(16)  # 22.5 degrees between the sides
    mesh = rhino._mesh(prism)
    points, normals = _vertices_and_normals(mesh)
    # Each side vertex is shared by both sides meeting there; the caps keep their own.
    assert len(points) == 16 * 2 + 16 * 2 < len(prism.verts) // 3
    assert len(mesh.Faces) == len(prism.faces) // 3
    for (x, y, z), (nx, ny, nz) in zip(points, normals):
        if abs(nz) > 0.5:  # cap vertex: straight up or down, not bent towards the sides
            assert nz == pytest.approx(1 if z else -1, abs=1e-6)
        else:  # side vertex: points away from the axis, like on a cylinder
            assert (nx, ny, nz) == pytest.approx((x, y, 0), abs=1e-6)


def test_edges_steeper_than_the_crease_angle_stay_sharp():
    prism = _prism(8)  # 45 degrees between the sides
    mesh = rhino._mesh(prism)
    points, normals = _vertices_and_normals(mesh)
    assert len(points) == len(prism.verts) // 3
    for n in normals:  # every normal is a face normal: one of 8 side directions or the cap axis
        assert abs(n[2]) == pytest.approx(1) or n[2] == pytest.approx(0, abs=1e-9)


def test_welding_keeps_every_triangle():
    for sides in (8, 16, 48):
        prism = _prism(sides)
        before = numpy.frombuffer(prism.verts_buffer).reshape(-1, 3)[numpy.frombuffer(prism.faces_buffer, numpy.int32).reshape(-1, 3)]
        points, triangles, _ = rhino._weld(
            numpy.frombuffer(prism.verts_buffer).reshape(-1, 3), numpy.frombuffer(prism.faces_buffer, numpy.int32).reshape(-1, 3)
        )
        assert numpy.array_equal(points[triangles], before)


def _signed_volume(mesh):
    points = numpy.array([(p.X, p.Y, p.Z) for p in mesh.Vertices.ToPoint3dArray()])
    a, b, c = (points[[mesh.Faces[i][k] for i in range(len(mesh.Faces))]] for k in range(3))
    return numpy.einsum("ij,ij->i", a, numpy.cross(b, c)).sum() / 6


def test_shared_geometry_is_placed_like_the_kernel_places_it(mirrored_type_ifc, monkeypatch):
    # The mesh export builds the type geometry once and copies it to both places; the reference is
    # the kernel's own world-coordinate geometry, which the polysurface export falls back to as mesh.
    placed = {o.Attributes.Name: o.Geometry for o in _read(convert(mirrored_type_ifc, fmt="3dm", geometry="mesh").output).Objects}
    monkeypatch.setattr(rhino, "MAX_BREP_FACES", 0)
    reference = {o.Attributes.Name: o.Geometry for o in _read(convert(mirrored_type_ifc, fmt="3dm").output).Objects}

    assert set(placed) == set(reference) == {"Cabinet", "Cabinet mirrored"}
    for name, mesh in placed.items():
        box, expected = mesh.GetBoundingBox(), reference[name].GetBoundingBox()
        assert (box.Min.X, box.Min.Y, box.Min.Z, box.Max.X, box.Max.Y, box.Max.Z) == pytest.approx(
            (expected.Min.X, expected.Min.Y, expected.Min.Z, expected.Max.X, expected.Max.Y, expected.Max.Z)
        )
        # The same orientation. (The kernel delivers the mirrored copy inside out: volume -1.)
        assert _signed_volume(mesh) == pytest.approx(_signed_volume(reference[name]))
        assert abs(_signed_volume(mesh)) == pytest.approx(1.0)
    assert placed["Cabinet"].GetBoundingBox().Min.X != placed["Cabinet mirrored"].GetBoundingBox().Min.X


def test_mesh_cache_limit_does_not_change_the_output(mirrored_type_ifc, monkeypatch):
    def boxes():
        objects = _read(convert(mirrored_type_ifc, fmt="3dm", geometry="mesh").output).Objects
        return sorted((o.Attributes.Name, len(o.Geometry.Faces), _size(o.Geometry)) for o in objects)

    cached = boxes()
    monkeypatch.setattr(rhino, "MESH_CACHE_VERTICES", 1)  # every mesh is dropped right away
    assert boxes() == cached


def test_standard_quantities_are_kept_vendor_quantity_dumps_dropped(wall_ifc):
    import ifcopenshell
    import ifcopenshell.api as api

    model = ifcopenshell.open(str(wall_ifc))
    wall = model.by_type("IfcWall")[0]
    standard = api.run("pset.add_qto", model, product=wall, name="Qto_WallBaseQuantities")
    api.run("pset.edit_qto", model, qto=standard, properties={"NetSideArea": 15.0})
    vendor = api.run("pset.add_qto", model, product=wall, name="ArchiCADQuantities")
    api.run("pset.edit_qto", model, qto=vendor, properties={"Surface Area": 15.0})
    model.write(str(wall_ifc))

    attributes = _read(convert(wall_ifc, fmt="3dm").output).Objects[0].Attributes
    assert attributes.GetUserString("Qto_WallBaseQuantities.NetSideArea") == "15.0"
    assert not any(key.startswith("ArchiCADQuantities") for key, _ in attributes.GetUserStrings())


def _contents(path):
    """Everything of each object but the random face ids of polysurfaces, in file order."""
    rhino = _read(path)
    layers, materials = _layer_paths(rhino), [m.Name for m in rhino.Materials]
    objects = []
    for o in rhino.Objects:
        geometry, attributes = o.Geometry, o.Attributes
        if isinstance(geometry, rhino3dm.Brep):
            points = [(v.Location.X, v.Location.Y, v.Location.Z) for v in geometry.Vertices]
            shape = ("Brep", points, len(geometry.Faces), len(geometry.Edges), geometry.IsSolid)
        else:
            shape = (type(geometry).__name__, geometry.Encode()["data"])
        objects.append((
            attributes.Name, shape, layers[attributes.LayerIndex], materials[attributes.MaterialIndex],
            tuple(attributes.ObjectColor), list(attributes.GetUserStrings()),
        ))
    return list(layers.values()), materials, objects


@pytest.mark.parametrize("geometry", ["brep", "mesh"])
def test_worker_processes_write_the_same_file(mixed_ifc, tmp_path, monkeypatch, geometry):
    serial = convert(mixed_ifc, tmp_path / "serial.3dm", fmt="3dm", geometry=geometry)
    monkeypatch.setattr(rhino, "_worker_count", lambda threads, elements: 2)
    monkeypatch.setattr(rhino, "BATCH_ELEMENTS", 3)  # several batches, finishing in any order
    parallel = convert(mixed_ifc, tmp_path / "parallel.3dm", fmt="3dm", geometry=geometry)
    assert parallel.elements == serial.elements == 18
    assert _contents(parallel.output) == _contents(serial.output)


def test_objects_are_written_in_model_order(mixed_ifc, tmp_path, monkeypatch):
    import ifcopenshell

    from ifc_converter import converter

    names = [p.Name for p in converter.shape_products(ifcopenshell.open(str(mixed_ifc)), rhino.EXCLUDED_CLASSES)]
    monkeypatch.setattr(converter, "chunk_size", lambda threads: 5)
    for threads in (1, 4):
        objects = _read(convert(mixed_ifc, tmp_path / f"{threads}.3dm", fmt="3dm", threads=threads).output).Objects
        assert [o.Attributes.Name for o in objects] == names


class _BrokenPool:
    """A process pool whose workers have died."""

    def __init__(self, *args, **kwargs):
        pass

    def submit(self, *args, **kwargs):
        import concurrent.futures.process

        future = concurrent.futures.Future()
        future.set_exception(concurrent.futures.process.BrokenProcessPool("worker killed"))
        return future

    def shutdown(self, *args, **kwargs):
        pass


def test_failed_workers_leave_the_work_to_the_main_process(mixed_ifc, tmp_path, monkeypatch):
    serial = convert(mixed_ifc, tmp_path / "serial.3dm", fmt="3dm")
    monkeypatch.setattr(rhino, "_worker_count", lambda threads, elements: 2)
    monkeypatch.setattr(rhino.concurrent.futures, "ProcessPoolExecutor", _BrokenPool)
    rescued = convert(mixed_ifc, tmp_path / "rescued.3dm", fmt="3dm")
    assert _contents(rescued.output) == _contents(serial.output)


def test_worker_count_respects_threads_memory_and_model_size(monkeypatch):
    gb = 1024 ** 3
    monkeypatch.setattr(rhino, "available_memory", lambda: 100 * gb)
    assert rhino._worker_count(64, 100_000) == rhino.MAX_WORKERS
    assert rhino._worker_count(4, 100_000) == 4 // rhino.THREADS_PER_WORKER
    assert rhino._worker_count(1, 100_000) == 0
    assert rhino._worker_count(64, rhino.MIN_PARALLEL_ELEMENTS - 1) == 0  # small model: not worth it
    monkeypatch.setattr(rhino, "available_memory", lambda: 4 * gb)
    assert rhino._worker_count(64, 100_000) == 2  # 2 GB beyond the reserve, 1 GB each
    monkeypatch.setattr(rhino, "available_memory", lambda: gb)
    assert rhino._worker_count(64, 100_000) == 0


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="checks /proc")
def test_workers_exit_when_their_process_is_killed(tmp_path):
    import os
    import signal
    import subprocess
    import sys
    import time

    # A conversion process with two busy workers is killed (as a cancel does): the workers must not
    # linger, holding memory and cores.
    code = (
        "import concurrent.futures, multiprocessing, os, sys, time\n"
        "from ifc_converter import rhino\n"
        "pool = concurrent.futures.ProcessPoolExecutor(2, multiprocessing.get_context('spawn'), rhino._worker_init, (os.getpid(),))\n"
        "futures = [pool.submit(time.sleep, 600) for _ in range(2)]\n"
        "while len(pool._processes) < 2: time.sleep(0.1)\n"
        "print(*pool._processes, flush=True)\n"
        "time.sleep(600)\n"
    )
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    workers = [int(pid) for pid in child.stdout.readline().split()]
    assert len(workers) == 2
    os.kill(child.pid, signal.SIGKILL)
    child.wait()

    def alive(pid):
        try:
            with open(f"/proc/{pid}/stat") as stat:
                return stat.read().split(")")[-1].split()[0] != "Z"
        except (FileNotFoundError, ProcessLookupError):  # gone before the open, or between open and read
            return False

    deadline = time.monotonic() + 10
    while any(alive(pid) for pid in workers) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not any(alive(pid) for pid in workers)


def test_property_sets_match_get_psets(mixed_ifc):
    import ifcopenshell
    import ifcopenshell.util.element as element_util

    model = ifcopenshell.open(str(mixed_ifc))
    sets = rhino._PropertySets(model)
    for product in model.by_type("IfcProduct"):
        expected = element_util.get_psets(product, psets_only=True), element_util.get_psets(product, qtos_only=True)
        psets, quantities = sets.of(product)
        # The same sets and properties, in the same order.
        assert [(name, list(values.items())) for name, values in psets.items()] == [
            (name, list(values.items())) for name, values in expected[0].items()
        ]
        assert quantities == expected[1]
    assert not sets._shared  # shared definitions are dropped after their last use


def test_space_layers_start_hidden(tmp_path):
    rhino_file = rhino3dm.File3dm()
    layers = rhino._LayerTable(rhino_file)
    space = layers.get((), "IfcSpace", (10, 20, 30, 40))
    wall = layers.get((), "IfcWall", (10, 20, 30, 255))
    assert rhino_file.Layers.FindIndex(space).Visible is False
    assert rhino_file.Layers.FindIndex(wall).Visible is True


def test_lengths_in_user_text_are_in_metres(tmp_path):
    import ifcopenshell
    import ifcopenshell.api as api

    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="mm")
    length = model.createIfcSIUnit(None, "LENGTHUNIT", "MILLI", "METRE")
    area = model.createIfcSIUnit(None, "AREAUNIT", None, "SQUARE_METRE")
    model.createIfcUnitAssignment([length, area])
    project.UnitsInContext = model.by_type("IfcUnitAssignment")[0]
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="W")
    qto = api.run("pset.add_qto", model, product=wall, name="Qto_WallBaseQuantities")
    api.run("pset.edit_qto", model, qto=qto, properties={"Length": 6403.99999999979, "NetSideArea": 22.5})
    pset = api.run("pset.add_pset", model, product=wall, name="Custom")
    pset.HasProperties = [
        model.createIfcPropertySingleValue("Offset", None, model.createIfcLengthMeasure(250.0), None),
        model.createIfcPropertySingleValue("Count", None, model.createIfcInteger(3), None),
        model.createIfcPropertySingleValue("Thick", None, model.createIfcLengthMeasure(2.0), model.createIfcSIUnit(None, "LENGTHUNIT", "CENTI", "METRE")),
    ]
    strings = rhino._user_strings(wall, rhino._PropertySets(model))
    assert strings["Qto_WallBaseQuantities.Length"] == "6.404"
    assert strings["Qto_WallBaseQuantities.NetSideArea"] == "22.5"  # m² already
    assert strings["Custom.Offset"] == "0.25"
    assert strings["Custom.Count"] == "3"
    assert strings["Custom.Thick"] == "0.02"


def test_enumerated_list_and_bounded_values_become_user_text_too(mixed_ifc):
    """IfcOpenShell gives them as lists and dicts; they used to be dropped without a word."""
    import ifcopenshell
    import ifcopenshell.api as api

    model = ifcopenshell.open(str(mixed_ifc))
    wall = model.by_type("IfcWall")[0]
    pset = api.run("pset.add_pset", model, product=wall, name="Custom")
    pset.HasProperties = [
        model.createIfcPropertyEnumeratedValue("Status", None, [model.createIfcLabel("NEW"), model.createIfcLabel("EXISTING")], None),
        model.createIfcPropertyListValue("Sizes", None, [model.createIfcInteger(1), model.createIfcInteger(2)], None),
        model.createIfcPropertyBoundedValue("Load", None, model.createIfcReal(2.5), model.createIfcReal(1.5), None, None),
    ]
    strings = rhino._user_strings(wall, rhino._PropertySets(model))
    assert strings["Custom.Status"] == "NEW, EXISTING"
    assert strings["Custom.Sizes"] == "1, 2"
    assert strings["Custom.Load.UpperBoundValue"] == "2.5" and strings["Custom.Load.LowerBoundValue"] == "1.5"
    assert "Custom.Load" not in strings


# ------------------------------------------------------------------------ user text


def _with_psets(path, properties, **attributes):
    """The first wall of the model at ``path`` with a property set "Test" and ``attributes`` set."""
    import ifcopenshell
    import ifcopenshell.api as api

    model = ifcopenshell.open(str(path))
    wall = model.by_type("IfcWall")[0]
    pset = api.run("pset.add_pset", model, product=wall, name="Test")
    pset.HasProperties = [
        model.createIfcPropertySingleValue(name, None, model.create_entity(kind, value), None)
        for name, (kind, value) in properties.items()
    ]
    for name, value in attributes.items():
        setattr(wall, name, value)
    model.write(str(path))
    return path


def test_placeholder_values_are_left_out(wall_ifc):
    properties = {
        "Empty": ("IfcLabel", ""), "Blank": ("IfcLabel", "  "), "NA": ("IfcLabel", "N/A"), "Dash": ("IfcLabel", "-"),
        "Unset": ("IfcLabel", "UNSET"), "NotDefined": ("IfcLabel", "NOTDEFINED"), "Default": ("IfcLabel", "<default>"),
        "NoneText": ("IfcLabel", "None"), "Dollar": ("IfcLabel", "$"),
        # Revit's COBie parameters: the value repeats the property's name.
        "SerialNumber": ("IfcText", "SerialNumber"),
        # Real values, also short or zero ones, stay.
        "Reference": ("IfcIdentifier", "AW-01"), "Zero": ("IfcInteger", 0), "Off": ("IfcBoolean", False),
        "Kind": ("IfcLabel", "USERDEFINED"), "Ratio": ("IfcReal", 0.0),
    }
    attributes = _read(convert(_with_psets(wall_ifc, properties, Name=None), fmt="3dm").output).Objects[0].Attributes
    strings = dict(attributes.GetUserStrings())
    tests = {key.split(".", 1)[1]: value for key, value in strings.items() if key.startswith("Test.")}
    assert tests == {"Reference": "AW-01", "Zero": "0", "Off": "False", "Kind": "USERDEFINED", "Ratio": "0.0"}
    # Identity is always there (an empty name cannot be stored: Rhino drops empty user text).
    assert strings["IfcClass"] == "IfcWall" and len(strings["IfcGlobalId"]) == 22


def test_type_predefined_type_tag_and_storey_in_user_text(storey_ifc):
    import ifcopenshell
    import ifcopenshell.api as api

    model = ifcopenshell.open(str(storey_ifc))
    wall, slab = model.by_type("IfcWall")[0], model.by_type("IfcSlab")[0]
    wall_type = api.run("root.create_entity", model, ifc_class="IfcWallType", name="AW 36.5", predefined_type="SOLIDWALL")
    api.run("type.assign_type", model, related_objects=[wall], relating_type=wall_type)
    wall.PredefinedType, wall.Tag = "NOTDEFINED", "123456"
    slab.PredefinedType, slab.ObjectType = "USERDEFINED", "Bodenplatte"
    model.write(str(storey_ifc))

    objects = {o.Attributes.GetUserString("IfcClass"): dict(o.Attributes.GetUserStrings()) for o in _read(convert(storey_ifc, fmt="3dm").output).Objects}
    wall, slab = objects["IfcWall"], objects["IfcSlab"]
    assert (wall["IfcType"], wall["IfcPredefinedType"], wall["IfcTag"], wall["IfcStorey"]) == ("AW 36.5", "SOLIDWALL", "123456", "EG")
    assert slab["IfcPredefinedType"] == "Bodenplatte" and "IfcObjectType" not in slab  # the name given, once
    assert "IfcType" not in slab and "IfcTag" not in slab  # nothing to say


def test_document_user_text_names_source_schema_and_georeferencing(wall_ifc):
    import ifcopenshell

    model = ifcopenshell.open(str(wall_ifc))
    context = model.by_type("IfcGeometricRepresentationContext")[0]
    metre = model.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE")
    crs = model.createIfcProjectedCRS("EPSG:25832", None, None, None, None, None, metre)
    # The project is in millimetres (the fixture's default units), the map in metres: a scale of
    # 0.001 takes project coordinates to the map, as in the bSI infrastructure samples.
    model.createIfcMapConversion(context, crs, 512345.678, 5423456.789, 312.5, 0.0, 1.0, 0.001)
    model.write(str(wall_ifc))

    strings = dict(_read(convert(wall_ifc, fmt="3dm").output).Strings)
    assert strings["IfcSourceFile"] == "wall.ifc"
    assert strings["IfcSchema"] == "IFC4"
    assert strings["IfcProject"] == "Test"
    # In metres, like the model; the x axis points north: 90 degrees from grid east.
    assert strings["IfcMapConversion.Eastings"] == "512345.678"
    assert strings["IfcMapConversion.Northings"] == "5423456.789"
    assert strings["IfcMapConversion.OrthogonalHeight"] == "312.5"
    assert strings["IfcMapConversion.Rotation"] == "90.0"
    # The scale as it applies to the metre geometry: the raw 0.001 belongs to millimetre coordinates.
    assert strings["IfcMapConversion.Scale"] == "1.0"
    assert strings["IfcProjectedCRS.Name"] == "EPSG:25832"
    # The coordinates stay in the project's own system.
    box = _read(convert(wall_ifc, fmt="3dm").output).Objects[0].Geometry.GetBoundingBox()
    assert (box.Min.X, box.Min.Y, box.Min.Z) == pytest.approx((0, 0, 0))


# ----------------------------------------------------------- several materials, groups


def _styled(model, item, name, rgb, transparency=0.0):
    import ifcopenshell.api as api

    style = api.run("style.add_style", model, name=name)
    api.run(
        "style.add_surface_style", model, style=style, ifc_class="IfcSurfaceStyleShading",
        attributes={"SurfaceColour": {"Name": None, "Red": rgb[0], "Green": rgb[1], "Blue": rgb[2]}, "Transparency": transparency},
    )
    api.run("style.assign_item_style", model, item=item, style=style)


@pytest.fixture
def window_ifc(tmp_path):
    """Two windows of one type (a frame and a transparent glass pane), one inside a curtain wall
    without geometry of its own (an aggregate), and a wall."""
    import ifcopenshell.api as api
    from conftest import _box, _metre_model

    model, body, site = _metre_model("IFC4")
    window_type = api.run("root.create_entity", model, ifc_class="IfcWindowType", name="Fenster 1")
    frame = api.run("geometry.add_wall_representation", model, context=body, length=1.0, height=1.2, thickness=0.1)
    glass = api.run("geometry.add_wall_representation", model, context=body, length=0.8, height=1.0, thickness=0.02)
    glass.Items[0].Position.Location.Coordinates = (0.1, 0.04, 0.1)
    frame.Items = frame.Items + glass.Items
    _styled(model, frame.Items[0], "Rahmen", (0.5, 0.3, 0.1))
    _styled(model, frame.Items[1], "Glas", (0.0, 0.5, 0.75), transparency=0.9)
    api.run("geometry.assign_representation", model, product=window_type, representation=frame)
    windows = []
    for i, name in enumerate(("Fenster links", "Fenster rechts")):
        window = api.run("root.create_entity", model, ifc_class="IfcWindow", name=name)
        matrix = numpy.eye(4)
        matrix[:3, 3] = (3.0 * i, 0.0, 1.0)
        api.run("geometry.edit_object_placement", model, product=window, matrix=matrix)
        api.run("type.assign_type", model, related_objects=[window], relating_type=window_type)
        windows.append(window)
    curtain_wall = api.run("root.create_entity", model, ifc_class="IfcCurtainWall", name="Fassade Süd")
    api.run("aggregate.assign_object", model, relating_object=curtain_wall, products=[windows[1]])
    wall = _box(model, body, "IfcWall", "Wand", (5, 0.3, 3), (0, 1, 0))
    api.run("spatial.assign_container", model, relating_structure=site, products=[windows[0], curtain_wall, wall])
    path = tmp_path / "window.ifc"
    model.write(str(path))
    return path


def _group_names(rhino_file, attributes):
    return sorted(rhino_file.Groups.FindIndex(index).Name for index in attributes.GetGroupList() or ())


@pytest.mark.parametrize("geometry", ["brep", "mesh"])
def test_element_with_several_materials_keeps_them(window_ifc, geometry):
    result = convert(window_ifc, fmt="3dm", geometry=geometry)
    assert result.elements == 3  # IFC elements, not objects

    rhino_file = _read(result.output)
    parts = [o for o in rhino_file.Objects if o.Attributes.Name == "Fenster links"]
    materials = {rhino_file.Materials[o.Attributes.MaterialIndex].Name: o for o in parts}
    assert set(materials) == {"Rahmen", "Glas"}
    glass, frame = materials["Glas"], materials["Rahmen"]
    assert rhino_file.Materials[glass.Attributes.MaterialIndex].Transparency == pytest.approx(0.9)
    assert glass.Attributes.ObjectColor == (0, 128, 191, round((1 - 0.9) * 255))
    assert frame.Attributes.ObjectColor[3] == 255
    assert _size(glass.Geometry) == pytest.approx((0.8, 0.02, 1.0))
    assert _size(frame.Geometry) == pytest.approx((1.0, 0.1, 1.2))
    # The parts select together and carry the same user text, on the layer of their class.
    assert _group_names(rhino_file, glass.Attributes) == _group_names(rhino_file, frame.Attributes) == ["Fenster links"]
    assert list(glass.Attributes.GetUserStrings()) == list(frame.Attributes.GetUserStrings())
    assert _layer_paths(rhino_file)[glass.Attributes.LayerIndex] == "Ohne Geschoss::IfcWindow"
    # The material covering most faces comes first; the layer takes its colour.
    assert parts[0] is frame or parts[0].Attributes.MaterialIndex == frame.Attributes.MaterialIndex


@pytest.mark.parametrize("blocks", [False, True])
def test_aggregate_parts_are_grouped_under_the_aggregate(window_ifc, blocks):
    rhino_file = _read(convert(window_ifc, fmt="3dm", blocks=blocks).output)
    right = [o for o in rhino_file.Objects if o.Attributes.Name == "Fenster rechts" and not o.Attributes.IsInstanceDefinitionObject]
    # Also in the group of its two materials (as objects of their own; a block instance is one object).
    expected = ["Fenster rechts", "Fassade Süd"] if not blocks else ["Fassade Süd"]
    assert len(right) == (1 if blocks else 2)
    for obj in right:
        assert _group_names(rhino_file, obj.Attributes) == sorted(expected)
    wall = next(o for o in rhino_file.Objects if o.Attributes.Name == "Wand")
    assert not wall.Attributes.GetGroupList()


# ------------------------------------------------------------------------------ blocks


def _placed(rhino_file):
    """Per element (GlobalId) its geometry as drawn: block instances resolved; and per element the
    kind of object it is."""
    definition_objects = {o.Attributes.Id: o.Geometry for o in rhino_file.Objects if o.Attributes.IsInstanceDefinitionObject}
    definitions = {}
    for index in range(len(rhino_file.InstanceDefinitions)):
        definition = rhino_file.InstanceDefinitions.FindIndex(index)
        definitions[definition.Id] = [definition_objects[i] for i in definition.GetObjectIds()]
    placed, kinds = {}, {}
    for o in rhino_file.Objects:
        if o.Attributes.IsInstanceDefinitionObject:
            continue
        guid = o.Attributes.GetUserString("IfcGlobalId")
        geometries = [o.Geometry]
        if isinstance(o.Geometry, rhino3dm.InstanceReference):
            geometries = []
            for geometry in definitions[o.Geometry.ParentIdefId]:
                geometry = geometry.Duplicate()
                geometry.Transform(o.Geometry.Xform)
                geometries.append(geometry)
        placed.setdefault(guid, []).extend(geometries)
        kinds.setdefault(guid, set()).add(type(o.Geometry).__name__)
    return placed, kinds


def _points(geometries):
    points = []
    for geometry in geometries:
        if isinstance(geometry, rhino3dm.Brep):
            points += [(v.Location.X, v.Location.Y, v.Location.Z) for v in geometry.Vertices]
        else:
            points += [(p.X, p.Y, p.Z) for p in geometry.Vertices.ToPoint3dArray()]
    return numpy.unique(numpy.round(numpy.array(points), 9), axis=0)


@pytest.mark.parametrize("geometry", ["brep", "mesh"])
@pytest.mark.parametrize("fixture", ["mixed_ifc", "mirrored_type_ifc", "window_ifc"])
def test_block_instances_are_exactly_where_the_copies_are(request, tmp_path, fixture, geometry):
    path = request.getfixturevalue(fixture)
    copies = convert(path, tmp_path / "copies.3dm", fmt="3dm", geometry=geometry)
    blocks = convert(path, tmp_path / "blocks.3dm", fmt="3dm", geometry=geometry, blocks=True)
    assert blocks.elements == copies.elements

    reference, _ = _placed(_read(copies.output))
    placed, kinds = _placed(_read(blocks.output))
    assert set(placed) == set(reference)
    assert any("InstanceReference" in kind for kind in kinds.values())
    for guid, geometries in placed.items():
        expected = reference[guid]
        assert len(geometries) == len(expected)
        # The same vertices (to a nanometre), the same orientation (signed volume) per part.
        numpy.testing.assert_allclose(_points(geometries), _points(expected), rtol=0, atol=1e-9)
        if geometry == "mesh":
            assert sorted(_signed_volume(g) for g in geometries) == pytest.approx(sorted(_signed_volume(g) for g in expected), abs=1e-9)


def test_blocks_share_the_type_geometry(mixed_ifc, tmp_path):
    rhino_file = _read(convert(mixed_ifc, fmt="3dm", blocks=True).output)
    # The furniture type, placed three times; everything else as before.
    assert len(rhino_file.InstanceDefinitions) == 1
    definition = rhino_file.InstanceDefinitions.FindIndex(0)
    assert definition.Name == "Cabinet"
    instances = [o for o in rhino_file.Objects if isinstance(o.Geometry, rhino3dm.InstanceReference)]
    assert sorted(o.Attributes.Name for o in instances) == ["Cabinet 0", "Cabinet 1", "Cabinet 2"]
    paths = _layer_paths(rhino_file)
    for instance in instances:
        attributes = instance.Attributes
        assert paths[attributes.LayerIndex] == "OG::IfcFurniture"
        assert attributes.GetUserString("Pset_Type.Maker") == "ACME"
        assert attributes.GetUserString("IfcType") == "Cabinet"
        assert attributes.ColorSource == rhino3dm.ObjectColorSource.ColorFromObject
    # The definition's object takes colour and material from the instance, and sits on a layer of its own.
    (member,) = [o for o in rhino_file.Objects if o.Attributes.IsInstanceDefinitionObject]
    assert member.Attributes.ColorSource == rhino3dm.ObjectColorSource.ColorFromParent
    assert member.Attributes.MaterialSource == rhino3dm.ObjectMaterialSource.MaterialFromParent
    assert paths[member.Attributes.LayerIndex] == rhino.BLOCK_LAYER
    assert not member.Attributes.GetUserStrings()


def test_block_parts_keep_their_materials(window_ifc):
    rhino_file = _read(convert(window_ifc, fmt="3dm", blocks=True).output)
    members = [o for o in rhino_file.Objects if o.Attributes.IsInstanceDefinitionObject]
    assert sorted(rhino_file.Materials[o.Attributes.MaterialIndex].Name for o in members) == ["Glas", "Rahmen"]
    assert {o.Attributes.ColorSource for o in members} == {rhino3dm.ObjectColorSource.ColorFromObject}
    assert rhino_file.InstanceDefinitions.FindIndex(0).Name == "Fenster 1"


def test_cli_blocks_flag(mixed_ifc, tmp_path):
    target = tmp_path / "mixed.3dm"
    assert main([str(mixed_ifc), "-f", "3dm", "-o", str(target), "--blocks"]) == 0
    assert len(_read(target).InstanceDefinitions) == 1
    assert main([str(mixed_ifc), "-f", "3dm", "-o", str(target), "--overwrite"]) == 0
    assert len(_read(target).InstanceDefinitions) == 0


# --------------------------------------------------------------- crashing worker processes


def test_a_pool_found_broken_when_submitting_is_replaced_and_its_batch_isolated(monkeypatch):
    """A worker that died between two batches breaks the pool before the next submit: that batch
    goes to a worker of its own, element by element, and the pool is started anew (not: everything
    from here on in this process, where the element that killed the worker would end the conversion)."""
    from concurrent.futures.process import BrokenProcessPool

    class Broken:
        def submit(self, function, jobs):
            raise BrokenProcessPool("a worker died")

        def shutdown(self, **kwargs):
            pass

    made = []
    monkeypatch.setattr(rhino, "_pool", lambda workers: made.append(workers) or Broken())
    isolated = []
    monkeypatch.setattr(rhino._Builder, "_build_isolated",
                        lambda self, job: isolated.append(job[0]) or ("built", job[0]))
    builder = rhino._Builder(workers=2)
    deferred = [builder._submit((number, False, b"", b"", b"", b"")) for number in (1, 2)]
    builder.flush()
    assert isolated == [1, 2] and made == [2]
    assert builder._workers == 2 and builder._restarts == 1 and builder._pool is None and not builder._in_process
    assert builder.result(deferred[0]._batch) == [("built", 1), ("built", 2)]


@pytest.mark.parametrize("mode", ["brep", "always"])
def test_worker_crash_is_put_down_to_its_element(mixed_ifc, tmp_path, monkeypatch, mode):
    import ifcopenshell

    import rhino_helpers

    model = ifcopenshell.open(str(mixed_ifc))
    culprit = next(p for p in model.by_type("IfcWall") if p.Name == "IfcWall 3")
    serial = convert(mixed_ifc, tmp_path / "serial.3dm", fmt="3dm")
    monkeypatch.setattr(rhino, "_worker_count", lambda threads, elements: 2)
    monkeypatch.setattr(rhino, "BATCH_ELEMENTS", 3)
    monkeypatch.setattr(rhino, "_build_batch", rhino_helpers.crash_on_element)
    monkeypatch.setenv(rhino_helpers.CRASH_ELEMENT, str(culprit.id()))
    monkeypatch.setenv(rhino_helpers.CRASH_MODE, mode)
    notes = []
    result = convert(mixed_ifc, tmp_path / "rescued.3dm", fmt="3dm", status=lambda phase, text: notes.append((phase, text)))

    # The log names the element, nothing else is lost, and the rest is built as before.
    (note,) = [text for phase, text in notes if phase == "note"]
    assert culprit.GlobalId in note and "IfcWall" in note
    expected = [entry for entry in _contents(serial.output)[2]]
    rescued = _contents(result.output)[2]
    if mode == "brep":  # as a mesh instead
        assert "als Netz" in note and result.elements == serial.elements
        index = next(i for i, entry in enumerate(expected) if entry[0] == "IfcWall 3")
        assert rescued[index][1][0] == "Mesh"
        del expected[index], rescued[index]
    else:  # left out
        assert "weggelassen" in note and result.elements == serial.elements - 1
        expected = [entry for entry in expected if entry[0] != "IfcWall 3"]
    assert rescued == expected


def test_workers_restart_after_a_crash(monkeypatch):
    # A pool whose worker died is replaced; the batches it lost are built one element at a time.
    started = []

    class Pool(_BrokenPool):
        def __init__(self, workers, *args, **kwargs):
            started.append(workers)

    monkeypatch.setattr(rhino.concurrent.futures, "ProcessPoolExecutor", Pool)
    builder = rhino._Builder(2)
    prism = _prism(8)
    geometry = SimpleNamespace(
        verts_buffer=prism.verts_buffer, faces_buffer=prism.faces_buffer, item_ids_buffer=b"",
        material_ids_buffer=b"", materials=[],
    )
    with builder:
        for _ in range(rhino.MAX_POOL_RESTARTS + 2):
            ((_, built),) = builder.build(1, geometry, False)
            builder.flush()
            assert isinstance(built.get(), rhino3dm.Mesh)
    # Each failed pool is started anew (2 workers) and checked with a single worker that turns out
    # broken as well, so the elements are built here; after MAX_POOL_RESTARTS no pool is started.
    assert started.count(2) == rhino.MAX_POOL_RESTARTS + 1
