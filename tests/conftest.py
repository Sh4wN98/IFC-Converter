import re

import ifcopenshell
import ifcopenshell.api as api
import ifcopenshell.api.alignment as alignment
import ifcopenshell.api.owner.settings as owner_settings
import numpy
import pytest


@pytest.fixture
def wall_ifc(tmp_path):
    """A minimal IFC4 model with a single 5 x 0.2 x 3 m wall."""
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

    path = tmp_path / "wall.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def storey_ifc(tmp_path):
    """An IFC4 model with a storey "EG" holding a red wall (with a pset) and a slab."""
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Test")
    api.run("unit.assign_unit", model)
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context,
    )
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    storey = api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="EG")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall")
    wall_rep = api.run(
        "geometry.add_wall_representation", model, context=body, length=5, height=3, thickness=0.2
    )
    api.run("geometry.assign_representation", model, product=wall, representation=wall_rep)
    api.run("geometry.edit_object_placement", model, product=wall)
    style = api.run("style.add_style", model, name="Red")
    api.run(
        "style.add_surface_style", model, style=style, ifc_class="IfcSurfaceStyleShading",
        attributes={"SurfaceColour": {"Name": None, "Red": 1.0, "Green": 0.0, "Blue": 0.0}, "Transparency": 0.0},
    )
    api.run("style.assign_representation_styles", model, shape_representation=wall_rep, styles=[style])
    pset = api.run("pset.add_pset", model, product=wall, name="Pset_WallCommon")
    api.run("pset.edit_pset", model, pset=pset, properties={"IsExternal": True, "Reference": "AW-01"})

    slab = api.run("root.create_entity", model, ifc_class="IfcSlab", name=None)
    slab_rep = api.run(
        "geometry.add_wall_representation", model, context=body, length=4, height=0.3, thickness=4
    )
    api.run("geometry.assign_representation", model, product=slab, representation=slab_rep)
    api.run("geometry.edit_object_placement", model, product=slab)
    api.run("spatial.assign_container", model, relating_structure=storey, products=[wall, slab])

    path = tmp_path / "storey.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def opening_ifc(wall_ifc):
    """The wall model plus an opening cut into the wall and a room (IfcSpace) next to it."""
    model = ifcopenshell.open(str(wall_ifc))
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    site = model.by_type("IfcSite")[0]
    wall = model.by_type("IfcWall")[0]

    opening = api.run("root.create_entity", model, ifc_class="IfcOpeningElement", name="Window opening")
    opening_rep = api.run(
        "geometry.add_wall_representation", model, context=body, length=1, height=1, thickness=0.2
    )
    api.run("geometry.assign_representation", model, product=opening, representation=opening_rep)
    # In the middle of the wall (x 2-3 m, z 1-2 m), so it becomes a hole through it.
    placement = numpy.eye(4)
    placement[0][3], placement[2][3] = 2.0, 1.0
    api.run("geometry.edit_object_placement", model, product=opening, matrix=placement)
    api.run("feature.add_feature", model, feature=opening, element=wall)

    space = api.run("root.create_entity", model, ifc_class="IfcSpace", name="Room")
    space_rep = api.run(
        "geometry.add_wall_representation", model, context=body, length=4, height=2.5, thickness=4
    )
    api.run("geometry.assign_representation", model, product=space, representation=space_rep)
    api.run("geometry.edit_object_placement", model, product=space)
    api.run("aggregate.assign_object", model, relating_object=site, products=[space])

    model.write(str(wall_ifc))
    return wall_ifc


@pytest.fixture
def georeferenced_ifc(wall_ifc):
    """The wall model moved to UTM-like coordinates, as in georeferenced bridge and site models."""
    model = ifcopenshell.open(str(wall_ifc))
    matrix = numpy.eye(4)
    matrix[:3, 3] = (512345.678, 5423456.789, 312.5)
    api.run("geometry.edit_object_placement", model, product=model.by_type("IfcWall")[0], matrix=matrix)
    model.write(str(wall_ifc))
    return wall_ifc


def _metre_model(version):
    model = api.run("project.create_file", version=version)
    if version == "IFC2X3":  # every root entity needs an owner history
        organization = model.createIfcOrganization(Name="Test")
        model.createIfcPersonAndOrganization(model.createIfcPerson(), organization)
        model.createIfcApplication(organization, "1", "Test", "Test")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Test")
    api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METRE"})
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context,
    )
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    return model, body, site


def _box(model, body, ifc_class, name, size=(1, 1, 1), position=(0, 0, 0)):
    element = api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    length, thickness, height = size
    representation = api.run(
        "geometry.add_wall_representation", model, context=body, length=length, height=height, thickness=thickness
    )
    api.run("geometry.assign_representation", model, product=element, representation=representation)
    matrix = numpy.eye(4)
    matrix[:3, 3] = position
    api.run("geometry.edit_object_placement", model, product=element, matrix=matrix)
    return element


def _spatial(model, ifc_class, name, parent, **attributes):
    element = api.run("root.create_entity", model, ifc_class=ifc_class, name=name, **attributes)
    api.run("aggregate.assign_object", model, relating_object=parent, products=[element])
    return element


@pytest.fixture
def bridge_ifc(tmp_path):
    """An IFC4X3 bridge: two unnamed piers in a substructure with a column each, a beam in the bridge
    itself, a deck part with geometry of its own and a marker in the site."""
    model, body, site = _metre_model("IFC4X3")
    bridge = _spatial(model, "IfcBridge", "River bridge", site, predefined_type="GIRDER")
    deck = _box(model, body, "IfcBridgePart", "Deck", (20, 4, 0.3), (0, -2, 7))
    deck.PredefinedType = "DECK"
    api.run("aggregate.assign_object", model, relating_object=bridge, products=[deck])
    substructure = _spatial(model, "IfcBridgePart", "Substructure", bridge, predefined_type="SUBSTRUCTURE")
    for x in (0, 20):
        pier = _spatial(model, "IfcBridgePart", None, substructure, predefined_type="PIER")
        column = _box(model, body, "IfcColumn", "Column", (1, 1, 6), (x, 0, 0))
        api.run("spatial.assign_container", model, relating_structure=pier, products=[column])
    beam = _box(model, body, "IfcBeam", "Deck beam", (20, 1, 1), (0, 0, 6))
    api.run("spatial.assign_container", model, relating_structure=bridge, products=[beam])
    proxy = _box(model, body, "IfcBuildingElementProxy", "Terrain marker")
    api.run("spatial.assign_container", model, relating_structure=site, products=[proxy])

    path = tmp_path / "bridge.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def alignment_ifc(tmp_path):
    """Two georeferenced IFC4X3 alignments: one with a vertical layout (a 3D gradient curve), one plan-only polyline."""
    model, _, _ = _metre_model("IFC4X3")
    axis = alignment.create_by_pi_method(
        model, "Main axis",
        hpoints=[(512000.0, 5423000.0), (512100.0, 5423000.0), (512100.0, 5423100.0)], radii=[20.0],
        vpoints=[(0.0, 300.0), (100.0, 302.0), (191.0, 300.0)], lengths=[40.0],
    )
    # Segment curves as real exports have them: horizontal ones in plan, vertical ones as a profile.
    alignment.create_segment_representations(model, axis)
    points = [(512000.0, 5422900.0), (512100.0, 5422900.0), (512100.0, 5422950.5)]
    alignment.create_as_polyline(model, "Ramp", [model.createIfcCartesianPoint(p) for p in points])

    path = tmp_path / "alignment.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def buildings_ifc(tmp_path, monkeypatch):
    """An IFC2X3 site with two buildings, each with a storey "EG" holding a wall, and a grid in building A."""
    monkeypatch.setattr(owner_settings, "get_user", lambda model: model.by_type("IfcPersonAndOrganization")[0])
    monkeypatch.setattr(owner_settings, "get_application", lambda model: model.by_type("IfcApplication")[0])
    model, body, site = _metre_model("IFC2X3")
    storeys = []
    for x, name in ((0, "Haus A"), (20, "Haus B")):
        building = _spatial(model, "IfcBuilding", name, site)
        storey = _spatial(model, "IfcBuildingStorey", "EG", building)
        storeys.append(storey)
        wall = _box(model, body, "IfcWall", "Wall", (5, 0.2, 3), (x, 0, 0))
        api.run("spatial.assign_container", model, relating_structure=storey, products=[wall])
    slab = _box(model, body, "IfcSlab", "Roof", (5, 5, 0.2), (0, 0, 3))
    api.run("spatial.assign_container", model, relating_structure=model.by_type("IfcBuilding")[0], products=[slab])

    grid = api.run("root.create_entity", model, ifc_class="IfcGrid", name="Grid")
    api.run("geometry.edit_object_placement", model, product=grid)
    api.run("spatial.assign_container", model, relating_structure=storeys[0], products=[grid])
    axes = []
    for tag, p1, p2 in (("A", (0, 0, 0), (10, 0, 0)), ("1", (0, -2, 0), (0, 8, 0))):
        axis = api.run("grid.create_grid_axis", model, axis_tag=tag, uvw_axes="UAxes" if tag == "A" else "VAxes", grid=grid)
        api.run("grid.create_axis_curve", model, grid_axis=axis, p1=p1, p2=p2)
        axes.append(axis.AxisCurve)
    footprint = api.run(
        "context.add_context", model, context_type="Model", context_identifier="FootPrint",
        target_view="MODEL_VIEW", parent=model.by_type("IfcGeometricRepresentationContext")[0],
    )
    representation = model.createIfcShapeRepresentation(
        footprint, "FootPrint", "GeometricCurveSet", [model.createIfcGeometricCurveSet(axes)]
    )
    api.run("geometry.assign_representation", model, product=grid, representation=representation)

    path = tmp_path / "buildings.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def broken_site_ifc(wall_ifc):
    """The wall model with a site representation without items, as OpenRoads writes it."""
    model = ifcopenshell.open(str(wall_ifc))
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    representation = model.createIfcShapeRepresentation(body, "Body", "Tessellation", None)
    model.by_type("IfcSite")[0].Representation = model.createIfcProductDefinitionShape(None, None, [representation])
    model.write(str(wall_ifc))
    return wall_ifc


def _add_broken_wall(model):
    """A wall whose extrusion profile is a two-point "polygon": no geometry kernel can build it."""
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Broken")
    line = model.createIfcPolyline([model.createIfcCartesianPoint((0.0, 0.0)), model.createIfcCartesianPoint((1.0, 0.0))])
    profile = model.createIfcArbitraryClosedProfileDef("AREA", None, line)
    solid = model.createIfcExtrudedAreaSolid(profile, None, model.createIfcDirection((0.0, 0.0, 1.0)), 3.0)
    representation = model.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
    wall.Representation = model.createIfcProductDefinitionShape(None, None, [representation])
    api.run("geometry.edit_object_placement", model, product=wall)
    return wall


@pytest.fixture
def broken_element_ifc(wall_ifc):
    """The wall model plus one wall whose geometry cannot be built."""
    model = ifcopenshell.open(str(wall_ifc))
    _add_broken_wall(model)
    model.write(str(wall_ifc))
    return wall_ifc


@pytest.fixture
def only_broken_ifc(wall_ifc, tmp_path):
    """A model whose only element with geometry cannot be built."""
    model = ifcopenshell.open(str(wall_ifc))
    model.remove(model.by_type("IfcWall")[0])
    _add_broken_wall(model)
    path = tmp_path / "broken.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def openroads_feet_ifc(tmp_path):
    """A 10 x 1 x 3 ft wall in US survey feet with the unit defects of OpenRoads Designer exports:
    untyped conversion factors, and square and cubic feet declared as length units."""
    model, body, site = _metre_model("IFC4")
    wall = _box(model, body, "IfcWall", "Wall", (10, 1, 3))
    api.run("spatial.assign_container", model, relating_structure=site, products=[wall])

    dimensions = model.createIfcDimensionalExponents(1, 0, 0, 0, 0, 0, 0)
    units = [model.createIfcSIUnit(None, "PLANEANGLEUNIT", None, "RADIAN")]
    for name, si_type, si_name, measure, factor in (
        ("ft (US Survey)", "LENGTHUNIT", "METRE", "IfcLengthMeasure", 0.304800609601219),
        ("ft2 (US Survey)", "AREAUNIT", "SQUARE_METRE", "IfcAreaMeasure", 0.0929034116433),
        ("ft3 (US Survey)", "VOLUMEUNIT", "CUBIC_METRE", "IfcVolumeMeasure", 0.02831701649376),
    ):
        si_unit = model.createIfcSIUnit(None, si_type, None, si_name)
        conversion = model.createIfcMeasureWithUnit(model.create_entity(measure, factor), si_unit)
        units.append(model.createIfcConversionBasedUnit(dimensions, "LENGTHUNIT", name, conversion))
    model.by_type("IfcProject")[0].UnitsInContext = model.createIfcUnitAssignment(units)

    path = tmp_path / "feet.ifc"
    model.write(str(path))
    # ifcopenshell only writes typed measures, so the bare numbers are put in afterwards.
    text = re.sub(r"IFCMEASUREWITHUNIT\(IFC\w+MEASURE\(([^)]*)\)", r"IFCMEASUREWITHUNIT(\1", path.read_text())
    path.write_text(text)
    return path


@pytest.fixture
def mirrored_type_ifc(tmp_path):
    """A furniture type (an off-centre box) placed twice: as modelled, and mirrored in x through its mapping."""
    model, body, site = _metre_model("IFC4")
    furniture_type = api.run("root.create_entity", model, ifc_class="IfcFurnitureType", name="Cabinet")
    representation = api.run(
        "geometry.add_wall_representation", model, context=body, length=2, height=1, thickness=0.5
    )
    api.run("geometry.assign_representation", model, product=furniture_type, representation=representation)
    for name in ("Cabinet", "Cabinet mirrored"):
        furniture = api.run("root.create_entity", model, ifc_class="IfcFurniture", name=name)
        api.run("geometry.edit_object_placement", model, product=furniture)
        api.run("spatial.assign_container", model, relating_structure=site, products=[furniture])
        api.run("type.assign_type", model, related_objects=[furniture], relating_type=furniture_type)
    mapped = model.by_type("IfcFurniture")[1].Representation.Representations[0].Items[0]
    mapped.MappingTarget = model.createIfcCartesianTransformationOperator3D(
        model.createIfcDirection((-1.0, 0.0, 0.0)), model.createIfcDirection((0.0, 1.0, 0.0)),
        model.createIfcCartesianPoint((5.0, 0.0, 0.0)), 1.0, model.createIfcDirection((0.0, 0.0, 1.0)),
    )
    path = tmp_path / "mirrored.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def federated_ifc(tmp_path):
    """Two models in one file, as Revit exports linked models: a second IfcProject (with a site)
    next to the one holding a 30 x 1 x 10 ft wall with 12 arched openings, in feet and degrees.

    The arcs are trimmed in degrees the way Revit writes them (180 to almost 0, on a circle turned
    by 180 degrees); each opening is 2 x 4 ft plus a half circle of 1 ft radius on top.
    """
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Architecture")
    feet = api.run("unit.add_conversion_based_unit", model, name="foot")
    degrees = api.run("unit.add_conversion_based_unit", model, name="degree")
    api.run("unit.assign_unit", model, units=[feet, degrees])
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context,
    )
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Facade")
    api.run("spatial.assign_container", model, relating_structure=site, products=[wall])
    representation = api.run(  # in metres, written in feet
        "geometry.add_wall_representation", model, context=body, length=9.144, height=3.048, thickness=0.3048
    )
    api.run("geometry.assign_representation", model, product=wall, representation=representation)
    api.run("geometry.edit_object_placement", model, product=wall)

    def point(*coordinates):
        return model.createIfcCartesianPoint([float(c) for c in coordinates])

    def direction(*ratios):
        return model.createIfcDirection([float(r) for r in ratios])

    for i in range(12):
        arc = model.createIfcTrimmedCurve(
            model.createIfcCircle(model.createIfcAxis2Placement2D(point(0, 6), direction(-1, 0)), 1.0),
            [model.create_entity("IfcParameterValue", 180.0)],
            [model.create_entity("IfcParameterValue", 4.57999874130747e-13)],
            True, "PARAMETER",
        )
        outline = model.createIfcCompositeCurve([
            model.createIfcCompositeCurveSegment(
                "CONTINUOUS", True, model.createIfcPolyline([point(-1, 6), point(-1, 2), point(1, 2), point(1, 6)]),
            ),
            model.createIfcCompositeCurveSegment("CONTINUOUS", True, arc),
        ], False)
        # Extruded through the wall (y -1 to 2 ft), with the profile's y axis pointing up.
        solid = model.createIfcExtrudedAreaSolid(
            model.createIfcArbitraryClosedProfileDef("AREA", None, outline),
            model.createIfcAxis2Placement3D(point(1.5 + 2.4 * i, -1, 0), direction(0, 1, 0), direction(-1, 0, 0)),
            direction(0, 0, 1), 3.0,
        )
        opening = api.run("root.create_entity", model, ifc_class="IfcOpeningElement")
        opening.Representation = model.createIfcProductDefinitionShape(None, None, [
            model.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid]),
        ])
        api.run("geometry.edit_object_placement", model, product=opening)
        api.run("feature.add_feature", model, feature=opening, element=wall)

    linked = model.createIfcProject(
        ifcopenshell.guid.new(), Name="Electrical", UnitsInContext=model.createIfcUnitAssignment([feet, degrees]),
    )
    linked_site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Linked site")
    api.run("aggregate.assign_object", model, relating_object=linked, products=[linked_site])

    path = tmp_path / "federated.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def contextless_ifc(wall_ifc):
    """The wall model with its body representation lacking a context, as FZKViewer writes it."""
    model = ifcopenshell.open(str(wall_ifc))
    for representation in model.by_type("IfcShapeRepresentation"):
        representation.ContextOfItems = None
    model.write(str(wall_ifc))
    return wall_ifc


@pytest.fixture
def mapped_with_opening_ifc(tmp_path):
    """A cabinet whose box comes from its type (IfcMappedItem) with a cut-out, like Revit sink cabinets."""
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

    cabinet_type = api.run("root.create_entity", model, ifc_class="IfcFurnitureType", name="Cabinet")
    box = api.run("geometry.add_wall_representation", model, context=body, length=1, height=2, thickness=0.6)
    api.run("geometry.assign_representation", model, product=cabinet_type, representation=box)
    cabinet = api.run("root.create_entity", model, ifc_class="IfcFurniture", name="Cabinet with cut-out")
    api.run("geometry.edit_object_placement", model, product=cabinet)
    api.run("type.assign_type", model, related_objects=[cabinet], relating_type=cabinet_type)
    api.run("spatial.assign_container", model, relating_structure=site, products=[cabinet])

    opening = api.run("root.create_entity", model, ifc_class="IfcOpeningElement", name="Cut-out")
    cut = api.run("geometry.add_wall_representation", model, context=body, length=0.4, height=0.4, thickness=0.6)
    api.run("geometry.assign_representation", model, product=opening, representation=cut)
    matrix = numpy.eye(4)
    matrix[:3, 3] = (0.3, 0.0, 0.8)
    api.run("geometry.edit_object_placement", model, product=opening, matrix=matrix)
    api.run("feature.add_feature", model, feature=opening, element=cabinet)

    path = tmp_path / "cabinet.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def mixed_ifc(tmp_path):
    """Two storeys with boxes of several classes, round columns (tessellated: meshes), a furniture type
    placed three times (one shared geometry), property sets on elements, a shared set and a type set."""
    model, body, site = _metre_model("IFC4")
    building = _spatial(model, "IfcBuilding", "Building", site)
    storeys = [_spatial(model, "IfcBuildingStorey", name, building) for name in ("EG", "OG")]
    elements = []
    for i in range(12):
        ifc_class = ("IfcWall", "IfcSlab", "IfcBeam")[i % 3]
        element = _box(model, body, ifc_class, f"{ifc_class} {i}", (1 + i * 0.1, 0.2, 2.5), (i * 2.0, 0, 3.0 * (i % 2)))
        api.run("spatial.assign_container", model, relating_structure=storeys[i % 2], products=[element])
        pset = api.run("pset.add_pset", model, product=element, name="Pset_Test")
        api.run("pset.edit_pset", model, pset=pset, properties={"Index": i, "Label": f"element {i}"})
        elements.append(element)
    # One property set defining several elements.
    rel = model.by_type("IfcRelDefinesByProperties")[0]
    rel.RelatedObjects = tuple(rel.RelatedObjects) + tuple(elements[1:4])
    for i in range(3):
        column = api.run("root.create_entity", model, ifc_class="IfcColumn", name=f"Column {i}")
        profile = model.createIfcCircleProfileDef("AREA", None, None, 0.25)
        representation = api.run("geometry.add_profile_representation", model, context=body, profile=profile, depth=3.0)
        api.run("geometry.assign_representation", model, product=column, representation=representation)
        matrix = numpy.eye(4)
        matrix[:3, 3] = (i * 3.0, 5.0, 0.0)
        api.run("geometry.edit_object_placement", model, product=column, matrix=matrix)
        api.run("spatial.assign_container", model, relating_structure=storeys[0], products=[column])
    furniture_type = api.run("root.create_entity", model, ifc_class="IfcFurnitureType", name="Cabinet")
    representation = api.run("geometry.add_wall_representation", model, context=body, length=1, height=0.8, thickness=0.5)
    api.run("geometry.assign_representation", model, product=furniture_type, representation=representation)
    type_pset = api.run("pset.add_pset", model, product=furniture_type, name="Pset_Type")
    api.run("pset.edit_pset", model, pset=type_pset, properties={"Maker": "ACME", "Label": "type"})
    for i in range(3):
        furniture = api.run("root.create_entity", model, ifc_class="IfcFurniture", name=f"Cabinet {i}")
        matrix = numpy.eye(4)
        matrix[:3, 3] = (i * 2.0, -3.0, 0.0)
        api.run("geometry.edit_object_placement", model, product=furniture, matrix=matrix)
        api.run("spatial.assign_container", model, relating_structure=storeys[1], products=[furniture])
        api.run("type.assign_type", model, related_objects=[furniture], relating_type=furniture_type)
        pset = api.run("pset.add_pset", model, product=furniture, name="Pset_Type")
        api.run("pset.edit_pset", model, pset=pset, properties={"Label": f"cabinet {i}"})
    path = tmp_path / "mixed.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def many_walls_ifc(tmp_path):
    """600 walls sharing their type's geometry: enough elements for the Rhino export's worker processes."""
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
    for i in range(600):
        wall = api.run("root.create_entity", model, ifc_class="IfcWall", name=f"Wall {i}")
        matrix = numpy.eye(4)
        matrix[:3, 3] = (2.5 * (i % 30), 1.0 * (i // 30), 0.0)
        api.run("geometry.edit_object_placement", model, product=wall, matrix=matrix)
        walls.append(wall)
    api.run("type.assign_type", model, related_objects=walls, relating_type=wall_type)
    api.run("spatial.assign_container", model, relating_structure=site, products=walls)
    path = tmp_path / "walls.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def nested_ifc(tmp_path):
    """One 10 x 0.3 x 3 m wall whose geometry is nested 5000 levels deep in IfcMappedItems.

    The kernels recurse once per level: with 1 MB of stack (Windows' default for a thread) a model
    like this overflowed it, in a worker thread of the kernel even with a large main thread.
    """
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
    for _ in range(5000):
        source = model.createIfcRepresentationMap(placement, representation)
        item = model.createIfcMappedItem(source, operator)
        representation = model.createIfcShapeRepresentation(body, "Body", "MappedRepresentation", [item])
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Deep wall")
    wall.Representation = model.createIfcProductDefinitionShape(None, None, [representation])
    api.run("geometry.edit_object_placement", model, product=wall)
    api.run("spatial.assign_container", model, relating_structure=site, products=[wall])
    path = tmp_path / "nested.ifc"
    model.write(str(path))
    return path
