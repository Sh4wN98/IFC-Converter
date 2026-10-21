"""Failing tests that demonstrate confirmed findings of the night review (report-night-review.md).

Written as xfail(strict=True) in the night review; the marks came off as the findings were fixed
once the finding is fixed.
"""
from __future__ import annotations

import time

import numpy
import pytest
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom as geom

from ifc_converter import converter


def _two_project_model(path, second_units):
    """A millimetre model (one 1000 mm cube) with a second, invalid IfcProject.

    IFC allows one IfcProject per file, but federated exports do write several (210 King: three);
    IfcOpenShell then reads the file as metres. merge_projects repairs that only when every project
    declares the same units; a second project without units (allowed in IFC4) or with other units
    leaves the model 1000x too large.
    """
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="First")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETERS"})
    context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW",
        parent=context,
    )
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="Cube")
    ifcopenshell.api.run("spatial.assign_container", model, products=[wall], relating_structure=site)
    profile = model.create_entity(
        "IfcRectangleProfileDef", ProfileType="AREA", XDim=1000.0, YDim=1000.0,
        Position=model.create_entity("IfcAxis2Placement2D", Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0))),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid", SweptArea=profile, Depth=1000.0,
        ExtrudedDirection=model.create_entity("IfcDirection", (0.0, 0.0, 1.0)),
        Position=model.create_entity(
            "IfcAxis2Placement3D", Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0, 0.0))
        ),
    )
    representation = model.create_entity(
        "IfcShapeRepresentation", ContextOfItems=body, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[solid],
    )
    ifcopenshell.api.run("geometry.assign_representation", model, product=wall, representation=representation)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=wall)
    second = model.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Second")
    if second_units == "metres":
        second.UnitsInContext = model.create_entity(
            "IfcUnitAssignment", Units=[model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")]
        )
    model.write(str(path))
    return ifcopenshell.open(str(path))


def _cube_size(model):
    wall = model.by_type("IfcWall")[0]
    settings = geom.settings()
    settings.set("use-world-coords", True)
    shape = geom.create_shape(settings, wall, converter._body_representation(wall))
    verts = numpy.array(shape.geometry.verts).reshape(-1, 3)
    return float((verts.max(axis=0) - verts.min(axis=0)).max())


def test_merge_projects_second_project_without_units(tmp_path):
    model = _two_project_model(tmp_path / "two.ifc", second_units=None)
    assert _cube_size(model) == pytest.approx(1000.0)  # IfcOpenShell reads the file as metres
    converter.merge_projects(model)
    assert len(model.by_type("IfcProject")) == 1
    assert _cube_size(model) == pytest.approx(1.0, abs=1e-6)


def test_merge_projects_second_project_other_units(tmp_path):
    model = _two_project_model(tmp_path / "two.ifc", second_units="metres")
    converter.merge_projects(model)
    # Either merged into the first project's units or at least not silently 1000x too large.
    assert _cube_size(model) == pytest.approx(1.0, abs=1e-6)


def test_stall_watchdog_survives_worker_exit(tmp_path, monkeypatch):
    """The Rhino export shuts its worker pool down right before the (single-threaded) write phase.

    tree_cpu_seconds only sums live processes, so the total drops by the workers' CPU time; the
    child then computes at 100 % CPU but counts as idle until it has earned the drop back. A write
    phase longer than STALL_TIMEOUT is killed as "stuck".
    """
    from ifc_converter import process

    monkeypatch.setattr(process, "STALL_TIMEOUT", 10)
    samples = iter([100.0, 101.0, 40.0, 41.0, 42.0, 43.0, 44.0, 45.0, 46.0, 47.0, 48.0, 49.0, 50.0, 51.0, 52.0])
    monkeypatch.setattr(process, "tree_cpu_seconds", lambda pid: next(samples))
    watch = process._Phases(tmp_path / "x.3dm", None, None, None)
    watch.pid = 1
    watch.enter("write", "writing")
    now = time.monotonic()
    watch._check_stall(now)  # 100 s with the workers alive
    watch._check_stall(now + 1)  # 101 s: active
    # The workers exit: 60 CPU-seconds leave the sum. From here on the child earns 1 CPU-s per
    # wall-clock second, which is full activity on one core, for longer than STALL_TIMEOUT.
    for step in range(2, 15):
        watch._check_stall(now + step)  # must not raise ConversionStalled


def _hull_house(path, bench: bool):
    """A closed 10 x 8 x 3 m house without any interior element, a column outside and, with
    ``bench``, an IfcFurniture standing in the garden, fully exposed (envelope sub-review case B1)."""
    import ifcopenshell.api as api

    def box(model, body, ifc_class, name, size, at, container):
        element = api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
        representation = api.run("geometry.add_wall_representation", model, context=body, length=size[0],
                                 height=size[2], thickness=size[1])
        api.run("geometry.assign_representation", model, product=element, representation=representation)
        matrix = numpy.eye(4)
        matrix[:3, 3] = at
        api.run("geometry.edit_object_placement", model, product=element, matrix=matrix)
        api.run("spatial.assign_container", model, relating_structure=container, products=[element])
        return element

    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="House")
    api.run("unit.assign_unit", model)
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run("context.add_context", model, context_type="Model", context_identifier="Body",
                   target_view="MODEL_VIEW", parent=context)
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    storey = api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="EG")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    api.run("aggregate.assign_object", model, relating_object=building, products=[storey])
    t = 0.3
    box(model, body, "IfcWall", "South", (10, t, 3), (0, 0, 0), storey)
    box(model, body, "IfcWall", "North", (10, t, 3), (0, 8 - t, 0), storey)
    box(model, body, "IfcWall", "West", (t, 8, 3), (0, 0, 0), storey)
    box(model, body, "IfcWall", "East", (t, 8, 3), (10 - t, 0, 0), storey)
    box(model, body, "IfcSlab", "Floor", (10, 8, t), (0, 0, -t), storey)
    box(model, body, "IfcSlab", "Roof", (10, 8, t), (0, 0, 3), storey)
    box(model, body, "IfcColumn", "Column", (0.4, 0.4, 3), (12, 2, 0), storey)
    if bench:
        box(model, body, "IfcFurniture", "Bench", (1.8, 0.5, 0.45), (3, -2, 0), storey)
    model.write(str(path))
    return ifcopenshell.open(str(path))


def test_hull_keeps_exposed_furniture_of_a_closed_house_without_interior(tmp_path):
    from ifc_converter import envelope

    model = _hull_house(tmp_path / "house.ifc", bench=True)
    products = converter.shape_products(model, converter.EXCLUDED_CLASSES)
    selection = envelope.select(model, 2, products)
    kept = {model.by_id(id_).Name for id_ in selection.keep}
    # The house is closed, nothing is inside: the fill sees every element from outside, the bench
    # in the garden included. The fallback for open hulls must not run (or must not drop it).
    assert "Bench" in kept
