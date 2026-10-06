import math
import os

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
    monkeypatch.setattr(converter, "CHUNK_SIZE", 1)
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


@pytest.mark.parametrize("kernel", ["hybrid", "opencascade"])
def test_both_kernels_produce_the_wall(wall_ifc, tmp_path, kernel):
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
    convert(wall_ifc, fmt="glb")
    monkeypatch.setenv("IFC_CONVERTER_KERNEL", "opencascade")
    convert(wall_ifc, fmt="glb")
    convert(wall_ifc, fmt="glb", kernel="hybrid")
    assert used == ["hybrid-cgal-simple-opencascade", "opencascade", "hybrid-cgal-simple-opencascade"]


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
    result = convert(storey_ifc, fmt="glb")
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
