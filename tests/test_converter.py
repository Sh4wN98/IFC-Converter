import contextvars
import math
import os
import sys
import threading
import time
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.unit
import numpy
import pytest
import rhino3dm

from ifc_converter import convert
from ifc_converter.converter import merge_projects, repair_units
from ifc_converter.cli import main


def test_glb_is_written(wall_ifc):
    result = convert(wall_ifc, fmt="glb")
    assert result.output == wall_ifc.with_suffix(".glb")
    assert result.elements == 1
    assert result.output.read_bytes()[:4] == b"glTF"


def test_obj_contains_wall_geometry(wall_ifc, tmp_path):
    result = convert(wall_ifc, tmp_path / "out" / "wall.obj", fmt="obj")
    text = result.output.read_text()
    assert "usemtl IfcWall" in text
    assert "v 5 0.2 3" in text
    assert result.output.with_suffix(".mtl").exists()


@pytest.mark.parametrize("fmt", ["glb", "obj"])
def test_openings_and_spaces_are_left_out(opening_ifc, fmt):
    result = convert(opening_ifc, fmt=fmt)
    assert result.elements == 1


def test_3dm_keeps_spaces_but_not_openings(opening_ifc):
    import rhino3dm

    result = convert(opening_ifc, fmt="3dm")
    classes = sorted(o.Attributes.GetUserString("IfcClass") for o in rhino3dm.File3dm.Read(str(result.output)).Objects)
    assert classes == ["IfcSpace", "IfcWall"]


def test_unknown_format_is_rejected(wall_ifc):
    with pytest.raises(ValueError):
        convert(wall_ifc, fmt="fbx")


def test_missing_input_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        convert(tmp_path / "missing.ifc")


def test_cli_out_dir(wall_ifc, tmp_path, capsys):
    out_dir = tmp_path / "converted"
    assert main([str(wall_ifc), "-f", "obj", "-d", str(out_dir)]) == 0
    assert (out_dir / "wall.obj").exists()
    assert "1 elements" in capsys.readouterr().out


def test_cli_returns_error_for_bad_input(tmp_path):
    assert main([str(tmp_path / "missing.ifc")]) == 1


def test_chunked_iteration_matches_single_pass(storey_ifc, monkeypatch, tmp_path):
    import rhino3dm

    from ifc_converter import converter

    def summary(path):
        objects = rhino3dm.File3dm.Read(str(path)).Objects
        return sorted((o.Attributes.GetUserString("IfcGlobalId"), len(o.Geometry.Vertices)) for o in objects)

    whole = convert(storey_ifc, tmp_path / "whole.3dm", fmt="3dm")
    monkeypatch.setattr(converter, "chunk_size", lambda threads: 1)
    steps = []
    chunked = convert(storey_ifc, tmp_path / "chunked.3dm", fmt="3dm", progress=steps.append)
    assert summary(chunked.output) == summary(whole.output)
    assert steps[0] == 0 and steps[-1] == 100 and steps == sorted(steps)


def test_threads_shrink_when_memory_is_tight(monkeypatch):
    from ifc_converter import converter

    gb = 1024 ** 3
    monkeypatch.setattr(converter, "available_memory", lambda: int(2.5 * gb))
    assert converter._affordable_threads(8) == 2
    monkeypatch.setattr(converter, "available_memory", lambda: gb // 2)
    assert converter._affordable_threads(8) == 1
    monkeypatch.setattr(converter, "available_memory", lambda: None)
    assert converter._affordable_threads(8) == 8


def test_memory_warning(wall_ifc, monkeypatch):
    from ifc_converter import converter

    monkeypatch.setattr(converter, "available_memory", lambda: 10 ** 12)
    assert converter.memory_warning(wall_ifc) is None
    monkeypatch.setattr(converter, "available_memory", lambda: 1000)
    message = converter.memory_warning(wall_ifc)
    assert "wall.ifc" in message and "0,0 GB" in message


@pytest.mark.parametrize("kernel", ["accurate", "hybrid", "opencascade"])
def test_every_kernel_produces_the_wall(wall_ifc, tmp_path, kernel):
    result = convert(wall_ifc, tmp_path / f"{kernel}.obj", fmt="obj", kernel=kernel)
    assert result.elements == 1
    assert "v 5 0.2 3" in result.output.read_text()


def test_kernel_is_validated_and_can_come_from_the_environment(wall_ifc, monkeypatch):
    from ifc_converter import converter

    with pytest.raises(ValueError):
        convert(wall_ifc, fmt="glb", kernel="parasolid")

    used = []
    real_iterator = converter.geom.iterator

    def recording_iterator(*args, geometry_library, **kwargs):
        used.append(geometry_library)
        return real_iterator(*args, geometry_library=geometry_library, **kwargs)

    monkeypatch.setattr(converter.geom, "iterator", recording_iterator)
    convert(wall_ifc, fmt="glb")  # "accurate": a wall goes to OpenCASCADE
    monkeypatch.setenv("IFC_CONVERTER_KERNEL", "hybrid")
    convert(wall_ifc, fmt="glb")
    convert(wall_ifc, fmt="glb", kernel="opencascade")
    assert used == ["opencascade", "hybrid-cgal-simple-opencascade", "opencascade"]


def test_cli_kernel_flag(wall_ifc, tmp_path, monkeypatch):
    # main() sets the variable for its child processes; setting it here first lets monkeypatch undo that.
    monkeypatch.setenv("IFC_CONVERTER_KERNEL", "hybrid")
    assert main([str(wall_ifc), "-f", "obj", "-d", str(tmp_path), "--kernel", "opencascade"]) == 0
    assert (tmp_path / "wall.obj").exists()
    assert os.environ["IFC_CONVERTER_KERNEL"] == "opencascade"
    with pytest.raises(SystemExit):
        main([str(wall_ifc), "--kernel", "nope"])


def test_unsupported_schema_gets_a_clear_message(wall_ifc, tmp_path):
    text = wall_ifc.read_text().replace("FILE_SCHEMA(('IFC4'))", "FILE_SCHEMA(('IFC4X4'))")
    assert "IFC4X4" in text
    future = tmp_path / "tunnel.ifc"
    future.write_text(text)
    with pytest.raises(ValueError, match="IFC-Version wird nicht unterstützt.*IFC4X4.*IFC2X3"):
        convert(future, fmt="glb")


@pytest.mark.parametrize("fmt", ["glb", "3dm"])
def test_representation_without_items_does_not_drop_other_elements(broken_site_ifc, fmt):
    assert convert(broken_site_ifc, fmt=fmt).elements == 1


@pytest.mark.parametrize("fmt", ["glb", "obj", "3dm"])
def test_elements_without_geometry_are_counted(broken_element_ifc, fmt):
    result = convert(broken_element_ifc, fmt=fmt)
    assert (result.elements, result.skipped) == (1, 1)


@pytest.mark.parametrize("fmt", ["glb", "obj", "3dm"])
def test_no_geometry_at_all_is_an_error_and_leaves_no_file(only_broken_ifc, fmt):
    with pytest.raises(ValueError, match="Keine Geometrie erzeugt"):
        convert(only_broken_ifc, fmt=fmt)
    assert not list(only_broken_ifc.parent.glob(f"broken.*[!c]"))  # only the .ifc remains


def test_file_without_any_geometry_is_an_error(tmp_path):
    import ifcopenshell.api as api

    model = api.run("project.create_file", version="IFC4")
    api.run("root.create_entity", model, ifc_class="IfcProject", name="Empty")
    path = tmp_path / "empty.ifc"
    model.write(str(path))
    with pytest.raises(ValueError, match="keine Bauteile mit Geometrie"):
        convert(path, fmt="glb")


def test_shapes_the_hybrid_kernel_skips_are_built_with_opencascade(storey_ifc, monkeypatch):
    from ifc_converter import converter

    real_iterator = converter.geom.iterator
    libraries = []

    def hybrid_without_walls(settings, model, threads, include, geometry_library):
        libraries.append((geometry_library, sorted(p.is_a() for p in include)))
        if geometry_library != "opencascade":
            include = [p for p in include if not p.is_a("IfcWall")]  # pretend the wall fails
        return real_iterator(settings, model, threads, include=include, geometry_library=geometry_library)

    monkeypatch.setattr(converter.geom, "iterator", hybrid_without_walls)
    result = convert(storey_ifc, fmt="glb", kernel="hybrid")
    assert (result.elements, result.skipped) == (2, 0)
    assert libraries == [
        ("hybrid-cgal-simple-opencascade", ["IfcSlab", "IfcWall"]),
        ("opencascade", ["IfcWall"]),
    ]


def test_openroads_feet_are_repaired(openroads_feet_ifc):
    model = ifcopenshell.open(str(openroads_feet_ifc))
    assert "IFCMEASUREWITHUNIT(0.304800609601219," in openroads_feet_ifc.read_text()
    repair_units(model)
    units = {unit.Name: unit for unit in model.by_type("IfcConversionBasedUnit")}
    assert {name: unit.UnitType for name, unit in units.items()} == {
        "ft (US Survey)": "LENGTHUNIT", "ft2 (US Survey)": "AREAUNIT", "ft3 (US Survey)": "VOLUMEUNIT",
    }
    assert units["ft (US Survey)"].ConversionFactor.ValueComponent.is_a("IfcLengthMeasure")
    assert ifcopenshell.util.unit.calculate_unit_scale(model) == pytest.approx(0.304800609601219)


def test_openroads_feet_convert_to_metres(openroads_feet_ifc):
    # Unrepaired, the geometry kernel takes the model as metres: a 10 m wall instead of 10 ft.
    brep = rhino3dm.File3dm.Read(str(convert(openroads_feet_ifc, fmt="3dm").output)).Objects[0].Geometry
    box = brep.GetBoundingBox()
    size = (box.Max.X - box.Min.X, box.Max.Y - box.Min.Y, box.Max.Z - box.Min.Z)
    assert size == pytest.approx((3.048006096, 0.3048006096, 0.9144018288))


def _obj_mesh(path):
    vertices, triangles = [], []
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            vertices.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            triangles.append([int(corner.split("/")[0]) - 1 for corner in line.split()[1:4]])
    return numpy.array(vertices), numpy.array(triangles)


def test_federated_model_keeps_its_units_and_openings(federated_ifc, tmp_path):
    # With two IfcProjects IfcOpenShell ignored the units: the wall came out in feet taken as metres,
    # and the arcs of the openings, trimmed in degrees, were read as radians.
    vertices, triangles = _obj_mesh(convert(federated_ifc, tmp_path / "federated.obj", fmt="obj").output)
    assert vertices.max(0) - vertices.min(0) == pytest.approx((9.144, 0.3048, 3.048))
    a, b, c = (vertices[triangles[:, corner]] for corner in range(3))
    volume = abs(numpy.einsum("ij,ij->i", a, numpy.cross(b, c)).sum()) / 6
    opening_area = 2 * 4 + math.pi / 2  # square feet
    assert volume == pytest.approx((30 * 1 * 10 - 12 * opening_area) * 0.3048 ** 3, rel=0.01)


def test_projects_are_merged_if_their_units_agree(federated_ifc):
    model = ifcopenshell.open(str(federated_ifc))
    merge_projects(model)
    (project,) = model.by_type("IfcProject")
    assert sorted(site.Name for rel in project.IsDecomposedBy for site in rel.RelatedObjects) == ["Linked site", "Site"]

    model = ifcopenshell.open(str(federated_ifc))
    metres = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    model.by_type("IfcProject")[1].UnitsInContext = model.createIfcUnitAssignment([metres])
    merge_projects(model)
    assert len(model.by_type("IfcProject")) == 2


def test_only_products_with_3d_geometry_go_to_the_kernel(wall_ifc):
    import ifcopenshell
    import ifcopenshell.api as api

    from ifc_converter.converter import _has_3d_shape

    model = ifcopenshell.open(str(wall_ifc))
    wall = model.by_type("IfcWall")[0]
    model_context = model.by_type("IfcGeometricRepresentationContext")[0]
    plan = api.run("context.add_context", model, context_type="Plan")

    def product(ifc_class, representation_class, context, identifier, items):
        element = model.create_entity(ifc_class, GlobalId=ifcopenshell.guid.new())
        representation = model.create_entity(
            representation_class, ContextOfItems=context, RepresentationIdentifier=identifier, Items=items,
        )
        element.Representation = model.createIfcProductDefinitionShape(None, None, [representation])
        return element

    vertex = model.createIfcVertexPoint(model.createIfcCartesianPoint((0.0, 0.0, 0.0)))
    face = model.createIfcFaceSurface([], model.createIfcPlane(model.createIfcAxis2Placement3D(
        model.createIfcCartesianPoint((0.0, 0.0, 0.0)))), True)
    symbol = model.createIfcPolyline([model.createIfcCartesianPoint((0.0, 0.0)), model.createIfcCartesianPoint((1.0, 0.0))])

    assert _has_3d_shape(wall)
    assert not _has_3d_shape(product("IfcStructuralPointConnection", "IfcTopologyRepresentation", model_context, "Reference", [vertex]))
    assert _has_3d_shape(product("IfcStructuralSurfaceMember", "IfcTopologyRepresentation", model_context, "Reference", [face]))
    assert not _has_3d_shape(product("IfcAnnotation", "IfcShapeRepresentation", plan, "Annotation", [symbol]))
    assert not _has_3d_shape(model.by_type("IfcSite")[0])  # no representation at all
    box = model.createIfcBoundingBox(model.createIfcCartesianPoint((0.0, 0.0, 0.0)), 1.0, 1.0, 1.0)
    space = product("IfcSpace", "IfcShapeRepresentation", model_context, "Box", [box])
    space.Representation.Representations[0].RepresentationType = "BoundingBox"
    assert not _has_3d_shape(space)


@pytest.mark.parametrize("fmt", ["glb", "3dm"])
def test_representations_without_context_are_converted(contextless_ifc, fmt):
    result = convert(contextless_ifc, fmt=fmt)
    assert (result.elements, result.skipped) == (1, 0)


@pytest.mark.parametrize("fmt, geometry", [("glb", "brep"), ("obj", "brep"), ("3dm", "mesh"), ("3dm", "brep")])
def test_type_geometry_with_opening_is_not_lost(mapped_with_opening_ifc, fmt, geometry):
    # In local coordinates the kernel returns nothing for these; they used to vanish silently from GLB/OBJ.
    result = convert(mapped_with_opening_ifc, fmt=fmt, geometry=geometry)
    assert (result.elements, result.skipped) == (1, 0)
    if fmt == "obj":
        assert result.output.read_text().count("\nf ") > 12  # more than a plain box: the cut-out is there


@pytest.mark.parametrize("cpus, threads", [(64, 16), (32, 11), (12, 4), (8, 3), (2, 1), (1, 1)])
def test_default_threads_leave_half_the_cpus_to_other_programs(monkeypatch, cpus, threads):
    # Kernel threads plus the Rhino export's workers (one per two threads) stay within about half the
    # logical CPUs: 32 on the target PC give 11 threads and 5 workers.
    from ifc_converter import converter, rhino

    monkeypatch.setattr(os, "process_cpu_count", lambda: cpus, raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: cpus)
    assert converter.default_threads() == threads
    assert converter.cpu_budget() == max(1, round(cpus * converter.CPU_SHARE))
    workers = min(rhino.MAX_WORKERS, threads // rhino.THREADS_PER_WORKER)
    assert threads + workers <= converter.cpu_budget()
    assert converter.worker_budget(threads) == converter.cpu_budget() - threads


def test_chunks_grow_with_the_thread_count():
    from ifc_converter import converter

    assert converter.chunk_size(1) == converter.chunk_size(4) == converter.CHUNK_SIZE
    assert converter.chunk_size(16) == 16 * converter.CHUNK_PER_THREAD
    assert converter.chunk_size(1000) == converter.MAX_CHUNK_SIZE


def test_chunk_ends_follow_their_shapes_in_model_order(storey_ifc, monkeypatch):
    from ifc_converter import converter, rhino

    model = ifcopenshell.open(str(storey_ifc))
    monkeypatch.setattr(converter, "chunk_size", lambda threads: 1)
    products = converter.shape_products(model, rhino.EXCLUDED_CLASSES)
    items = list(converter.iter_shapes(model, rhino._settings(), 2, rhino.EXCLUDED_CLASSES, chunk_ends=True))
    ends = [item for item in items if isinstance(item, converter.ChunkEnd)]
    assert [end.ids for end in ends] == [[product.id()] for product in products]
    for shape, end in zip(items[::2], items[1::2]):  # each one-element chunk: its shape, then its end
        assert end.ids == [shape.id]


def test_kernel_never_runs_single_threaded(monkeypatch):
    from ifc_converter import converter

    monkeypatch.setattr(converter, "available_memory", lambda: 1024 ** 3 // 2)
    assert converter._kernel_threads(1) == converter._kernel_threads(8) == converter.MIN_THREADS
    monkeypatch.setattr(converter, "available_memory", lambda: None)
    assert converter._kernel_threads(8) == 8


def _terrain(model, body, name, triangles, position=(0.0, 0.0, 0.0)):
    """An IfcGeographicElement whose body is a triangle mesh (IFC4X3: IfcTriangulatedIrregularNetwork)."""
    import ifcopenshell.api as api

    side = int((triangles / 2) ** 0.5) + 1
    points = [(float(x), float(y), 0.1 * ((x * y) % 7)) for y in range(side + 1) for x in range(side + 1)]
    faces = []
    for y in range(side):
        for x in range(side):
            a = y * (side + 1) + x + 1
            faces += [(a, a + 1, a + side + 2), (a, a + side + 2, a + side + 1)]
    faces = faces[:triangles]
    coordinates = model.createIfcCartesianPointList3D(points)
    mesh = model.createIfcTriangulatedIrregularNetwork(coordinates, None, False, faces, None, [0] * len(faces))
    shape = model.createIfcShapeRepresentation(body, "Body", "Tessellation", [mesh])
    element = api.run("root.create_entity", model, ifc_class="IfcGeographicElement", name=name)
    element.Representation = model.createIfcProductDefinitionShape(None, None, [shape])
    matrix = numpy.eye(4)
    matrix[:3, 3] = position
    api.run("geometry.edit_object_placement", model, product=element, matrix=matrix)
    return element


def _faceted_box(model, size):
    """An IfcFacetedBrep box from the origin to ``size``."""
    x, y, z = size
    corners = [(0, 0, 0), (x, 0, 0), (x, y, 0), (0, y, 0), (0, 0, z), (x, 0, z), (x, y, z), (0, y, z)]
    points = [model.createIfcCartesianPoint([float(c) for c in corner]) for corner in corners]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    faces = [
        model.createIfcFace([model.createIfcFaceOuterBound(model.createIfcPolyLoop([points[i] for i in quad]), True)])
        for quad in quads
    ]
    return model.createIfcFacetedBrep(model.createIfcClosedShell(faces))


@pytest.fixture
def routing_ifc(tmp_path):
    """IFC4X3: a large terrain, a small one, one with an opening, and a faceted brep wall."""
    import ifcopenshell.api as api

    from conftest import _box, _metre_model

    model, body, site = _metre_model("IFC4X3")
    _terrain(model, body, "Terrain", 5000)
    _terrain(model, body, "Small terrain", 50, (200.0, 0.0, 0.0))
    cut = _terrain(model, body, "Cut terrain", 5000, (400.0, 0.0, 0.0))
    opening = _box(model, body, "IfcOpeningElement", "Pit", (5, 5, 5), (410, 10, -2))
    api.run("feature.add_feature", model, feature=opening, element=cut)
    wall = _box(model, body, "IfcWall", "Brep wall", (5, 0.2, 3), (0, -10, 0))
    wall.Representation.Representations[0].Items = [_faceted_box(model, (5.0, 0.2, 3.0))]
    path = tmp_path / "routing.ifc"
    model.write(str(path))
    return path


def test_accurate_routes_only_large_triangle_meshes_to_the_hybrid_kernel(routing_ifc, monkeypatch):
    from ifc_converter import converter

    real_iterator = converter.geom.iterator
    calls = []

    def recording_iterator(settings, model, threads, include, geometry_library):
        calls.append((geometry_library, sorted(p.Name for p in include)))
        return real_iterator(settings, model, threads, include=include, geometry_library=geometry_library)

    monkeypatch.setattr(converter.geom, "iterator", recording_iterator)
    result = convert(routing_ifc, fmt="glb")
    assert result.elements == 4 and result.skipped == 0
    assert calls == [
        ("hybrid-cgal-simple-opencascade", ["Terrain"]),
        ("opencascade", ["Brep wall", "Cut terrain", "Small terrain"]),
    ]


def test_triangle_mesh_only(routing_ifc):
    import ifcopenshell

    from ifc_converter import converter

    model = ifcopenshell.open(str(routing_ifc))
    routed = {p.Name: converter._triangle_mesh_only(p) for p in converter.shape_products(model, converter.EXCLUDED_CLASSES)}
    assert routed == {"Terrain": True, "Small terrain": False, "Cut terrain": False, "Brep wall": False}


@pytest.mark.parametrize("fmt", ["3dm", "glb", "obj"])
def test_phases_are_reported(wall_ifc, fmt):
    calls = []
    convert(wall_ifc, fmt=fmt, status=lambda phase, text: calls.append((phase, text)))
    phases = [phase for phase, _ in calls]
    assert phases[:2] == ["read", "geometry"]
    assert "IFC-Datei wird gelesen" in calls[0][1]
    if fmt != "obj":  # OBJ is written while the geometry is computed
        assert phases[-1] == "write"
    assert "copy" not in phases  # a local folder is written directly


@pytest.mark.parametrize("fmt", ["3dm", "glb", "obj"])
def test_output_for_a_network_folder_is_staged_locally_and_copied(wall_ifc, tmp_path, monkeypatch, fmt):
    from ifc_converter import converter

    monkeypatch.setattr(converter, "is_network_path", lambda path: True)
    staging = tmp_path / "staging"
    staging.mkdir()
    target = tmp_path / "share" / f"wall.{fmt}"
    calls = []
    result = convert(wall_ifc, target, fmt, status=lambda phase, text: calls.append((phase, text)), staging_dir=staging)
    assert result.output == target and target.stat().st_size > 0
    if fmt == "obj":
        assert target.with_suffix(".mtl").is_file()
    assert [phase for phase, _ in calls][-1] == "copy"
    assert not list(staging.iterdir())  # the staged copy is gone
    assert not list(target.parent.glob("*.part"))


def _failing_copies(monkeypatch, failures: int):
    """Make the first ``failures`` copies to the network folder fail like a lost connection."""
    from ifc_converter import converter

    copy = converter._copy
    calls = []

    def flaky(source, target, done, total, report):
        calls.append(target)
        if len(calls) <= failures:
            target.with_name(target.name + ".part").write_bytes(b"half")
            raise OSError(64, "Der angegebene Netzwerkname ist nicht mehr verfügbar")
        return copy(source, target, done, total, report)

    monkeypatch.setattr(converter, "_copy", flaky)
    monkeypatch.setattr(converter, "COPY_RETRY_WAITS", (0, 0))
    monkeypatch.setattr(converter, "is_network_path", lambda path: True)
    return calls


def test_a_failed_copy_to_the_network_is_tried_again(wall_ifc, tmp_path, monkeypatch):
    calls = _failing_copies(monkeypatch, failures=2)
    messages = []
    target = tmp_path / "share" / "wall.3dm"
    result = convert(wall_ifc, target, "3dm", status=lambda phase, text: messages.append(text),
                     staging_dir=tmp_path)
    assert result.output == target and target.stat().st_size > 1000
    assert len(calls) == 3
    assert any("Kopieren fehlgeschlagen" in text and "neuer Versuch 2" in text for text in messages)


def test_output_that_cannot_be_copied_is_kept_locally(wall_ifc, tmp_path, monkeypatch):
    from ifc_converter import app

    _failing_copies(monkeypatch, failures=99)
    rescue = tmp_path / "rescue"
    monkeypatch.setattr(app, "rescue_dir", lambda: rescue)
    target = tmp_path / "share" / "wall.3dm"
    with pytest.raises(OSError, match="Sie liegt hier: .*wall.3dm – bitte von Hand kopieren"):
        convert(wall_ifc, target, "3dm", staging_dir=tmp_path)
    assert (rescue / "wall.3dm").stat().st_size > 1000
    assert not target.exists()


def test_staging_is_skipped_without_room(wall_ifc, tmp_path, monkeypatch):
    import shutil

    from ifc_converter import converter

    monkeypatch.setattr(converter, "is_network_path", lambda path: True)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(10, 10, 0))
    calls = []
    result = convert(wall_ifc, tmp_path / "wall.glb", "glb", status=lambda phase, text: calls.append((phase, text)))
    assert result.output.is_file()
    assert "copy" not in [phase for phase, _ in calls]  # written over the "network" directly


def test_network_paths_are_recognised(monkeypatch):
    from ifc_converter import converter

    monkeypatch.setattr(converter.sys, "platform", "win32")
    assert converter.is_network_path(Path(r"\\srvbf001\Users$\bwestrich\Desktop\IFC Test\a.3dm"))
    assert converter.is_network_path(Path("//server/share/a.3dm"))
    monkeypatch.setattr(converter.sys, "platform", "linux")
    assert not converter.is_network_path(Path("/home/user/a.3dm"))


def test_size_text():
    from ifc_converter.converter import size_text

    assert size_text(345 * 1024 ** 2) == "345 MB"
    assert size_text(int(1.25 * 1024 ** 3)) == "1,2 GB"


def test_deeply_nested_products_are_found(nested_ifc, wall_ifc):
    from ifc_converter.converter import DEEP_NESTING, deep_products

    model = ifcopenshell.open(str(nested_ifc))
    [(product, depth)] = deep_products(model.by_type("IfcWall"))
    assert depth == 5001 > DEEP_NESTING  # 5000 mapped items around the extrusion
    assert deep_products(ifcopenshell.open(str(wall_ifc)).by_type("IfcWall")) == []


@pytest.mark.skipif(sys.platform == "win32", reason="the stack limit is set with POSIX rlimits")
@pytest.mark.parametrize("fmt, geometry", [("3dm", "brep"), ("3dm", "mesh"), ("glb", "brep")])
def test_deep_nesting_converts_with_a_1_mb_stack(nested_ifc, tmp_path, fmt, geometry):
    # Every thread of the process gets 1 MB of stack, as on Windows: only the thread the converter
    # starts for deeply nested products has more. Before, this crashed (or hung, on Windows).
    import resource
    import subprocess

    def small_stack():
        resource.setrlimit(resource.RLIMIT_STACK, (1024 ** 2, resource.getrlimit(resource.RLIMIT_STACK)[1]))

    output = tmp_path / f"nested.{fmt}"
    code = (
        "import sys; from ifc_converter import convert; "
        "r = convert(sys.argv[1], sys.argv[2], sys.argv[3], threads=4, geometry=sys.argv[4]); "
        "sys.exit(0 if (r.elements, r.skipped) == (1, 0) else 3)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(nested_ifc), str(output), fmt, geometry],
        preexec_fn=small_stack, capture_output=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-2000:]
    assert output.stat().st_size > 0


def test_the_deep_stack_size_is_accepted_on_this_platform():
    # Python on Windows rejects thread stacks of 256 MB and more ("size not valid").
    import threading

    from ifc_converter.converter import DEEP_STACK

    previous = threading.stack_size(DEEP_STACK)
    threading.stack_size(previous)


def test_geometry_that_contains_itself_is_not_computed(wall_ifc, tmp_path):
    from ifc_converter.converter import CYCLIC, _triangle_mesh_only, deep_products

    model = ifcopenshell.open(str(wall_ifc))
    wall = model.by_type("IfcWall")[0]
    body = wall.Representation.Representations[-1]
    origin = model.createIfcCartesianPoint((0.0, 0.0, 0.0))
    source = model.createIfcRepresentationMap(model.createIfcAxis2Placement3D(origin, None, None), body)
    item = model.createIfcMappedItem(source, model.createIfcCartesianTransformationOperator3D(None, None, origin, 1.0, None))
    body.Items = list(body.Items) + [item]  # the body now contains itself
    assert deep_products([wall]) == [(wall, CYCLIC)]
    assert _triangle_mesh_only(wall) is False
    path = tmp_path / "cyclic.ifc"
    model.write(str(path))
    # Not computed (the kernel would recurse forever): the only wall gives no geometry.
    with pytest.raises(ValueError, match="Keine Geometrie erzeugt"):
        convert(path, tmp_path / "cyclic.glb", "glb")


def _slow_kernel(monkeypatch, slow_name, release):
    """Let the kernel hold back the shape of the product called ``slow_name`` until ``release`` is set,
    like one slow element; returns the products of each iterator in the order they were started."""
    from ifc_converter import converter

    iterate = converter._iterate
    started = []

    def slow_iterate(model, settings, threads, products, library):
        started.append([product.Name for product in products])
        shapes = list(iterate(model, settings, threads, products, library))

        def run():  # the other threads deliver their shapes meanwhile
            slow = [shape for shape in shapes if model.by_id(shape.id).Name == slow_name]
            yield from (shape for shape in shapes if shape not in slow)
            if slow:
                release.wait(60)
            yield from slow

        return run()

    monkeypatch.setattr(converter, "_iterate", slow_iterate)
    return started


def _wait_until(condition, timeout=30):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.02)
    return condition()


@pytest.mark.parametrize("memory, started_early", [(10 ** 12, 6), (1024 ** 3, 2)])
def test_later_chunks_are_computed_while_a_slow_element_holds_one_up(
    many_walls_ifc, monkeypatch, memory, started_early
):
    # The other threads go on with the next chunk instead of waiting idle; with LOOKAHEAD_MEMORY free,
    # with further chunks as well. The shapes still come chunk by chunk in model order, and only the
    # slow element is a suspect should the kernel crash or hang on it.
    from ifc_converter import converter, process, rhino

    monkeypatch.setattr(converter, "chunk_size", lambda threads: 100)
    monkeypatch.setattr(converter, "available_memory", lambda: memory)
    release = threading.Event()
    started = _slow_kernel(monkeypatch, "Wall 7", release)
    model = ifcopenshell.open(str(many_walls_ifc))
    products = converter.shape_products(model, rhino.EXCLUDED_CLASSES)
    watch = process._Phases(Path("x.3dm"), None, None, None)
    items = []
    recovery = converter._recovery.set((watch.locate, set(), set()))
    try:
        shapes = converter.iter_shapes(model, rhino._settings(), 2, rhino.EXCLUDED_CLASSES, chunk_ends=True)
        consumer = threading.Thread(target=contextvars.copy_context().run, args=(lambda: items.extend(shapes),))
        consumer.start()
        try:
            assert _wait_until(lambda: len(started) >= started_early)
            time.sleep(0.5)  # no further chunk starts
            assert len(started) == started_early
            assert all(len(names) == 100 for names in started)
            assert _wait_until(lambda: watch.suspects() == ("chunk", [products[7].id()], ""))
            assert len(items) == 99  # the first chunk waits for its slow element, the others for it
        finally:
            release.set()
            consumer.join(60)
    finally:
        converter._recovery.reset(recovery)
    ends = [index for index, item in enumerate(items) if isinstance(item, converter.ChunkEnd)]
    assert ends == [100, 201, 302, 403, 504, 605]
    for start, end in zip([-1, *ends], ends):
        assert [item.id for item in items[start + 1:end]] != []
        assert {item.id for item in items[start + 1:end]} == set(items[end].ids)
    assert [id_ for end in ends for id_ in items[end].ids] == [product.id() for product in products]
    assert watch.position == ("done", [], "")


def test_overlapping_chunks_keep_the_threads_within_the_budget(many_walls_ifc, monkeypatch):
    # A run starts only while at most a quarter of the threads are still busy with earlier ones.
    from ifc_converter import converter, rhino

    monkeypatch.setattr(converter, "chunk_size", lambda threads: 50)
    monkeypatch.setattr(converter, "available_memory", lambda: 10 ** 12)
    busy = []
    start = converter._Pipeline.start

    def recording_start(self, *args, **kwargs):
        busy.append(sum(run.busy() for run in self._alive))
        return start(self, *args, **kwargs)

    monkeypatch.setattr(converter._Pipeline, "start", recording_start)
    model = ifcopenshell.open(str(many_walls_ifc))
    shapes = list(converter.iter_shapes(model, rhino._settings(), 8, rhino.EXCLUDED_CLASSES))
    assert len(shapes) == 600 and len(busy) == 12
    assert max(busy) <= 8 // converter.OVERLAP_SHARE


def test_an_abandoned_iteration_stops_its_runs(many_walls_ifc, monkeypatch):
    from ifc_converter import converter, rhino

    monkeypatch.setattr(converter, "chunk_size", lambda threads: 100)
    runs = []
    start = converter._Pipeline.start

    def recording_start(self, *args, **kwargs):
        runs.append(start(self, *args, **kwargs))
        return runs[-1]

    monkeypatch.setattr(converter._Pipeline, "start", recording_start)
    model = ifcopenshell.open(str(many_walls_ifc))
    shapes = converter.iter_shapes(model, rhino._settings(), 2, rhino.EXCLUDED_CLASSES)
    next(shapes)
    shapes.close()
    assert runs and all(run.stopped for run in runs if not run.finished)
