"""Dimensional accuracy: synthetic models of known dimensions, checked in every output format.

The models are written entity by entity (no ifcopenshell.api geometry helpers), so the expected
dimensions come straight from the IFC values and their units, not from IfcOpenShell.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid
import numpy
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import accuracy  # noqa: E402

from ifc_converter import convert  # noqa: E402

# Planar geometry must come out exact to this (metres): 0.1 mm.
TOLERANCE = 1e-4
MODES = list(accuracy.MODES)


# ------------------------------------------------------------------------------------ IFC builder


class _Model:
    """A minimal IFC model with a project, one length unit, a body context and a site."""

    def __init__(self, schema: str = "IFC4", unit: str = "MILLIMETRE"):
        self.file = f = ifcopenshell.file(schema=schema)
        self.history = None
        if schema == "IFC2X3":
            organization = f.createIfcOrganization(Name="Test")
            application = f.createIfcApplication(organization, "1", "Test", "Test")
            person = f.createIfcPersonAndOrganization(f.createIfcPerson(), organization)
            self.history = f.createIfcOwnerHistory(person, application, None, "ADDED", None, None, None, 0)
        if unit == "MILLIMETRE":
            length = f.createIfcSIUnit(None, "LENGTHUNIT", "MILLI", "METRE")
        elif unit == "METRE":
            length = f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE")
        else:  # FOOT
            metre = f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE")
            exponents = f.createIfcDimensionalExponents(1, 0, 0, 0, 0, 0, 0)
            factor = f.createIfcMeasureWithUnit(f.createIfcLengthMeasure(0.3048), metre)
            length = f.createIfcConversionBasedUnit(exponents, "LENGTHUNIT", "FOOT", factor)
        angle = f.createIfcSIUnit(None, "PLANEANGLEUNIT", None, "RADIAN")
        units = f.createIfcUnitAssignment([length, angle])
        self.context = f.createIfcGeometricRepresentationContext(
            None, "Model", 3, 1e-5, self.axis((0.0, 0.0, 0.0)), None
        )
        if schema == "IFC2X3":
            self.body = self.context
        else:
            self.body = f.createIfcGeometricRepresentationSubContext(
                "Body", "Model", None, None, None, None, self.context, None, "MODEL_VIEW", None
            )
        self.project = f.createIfcProject(self.guid(), self.history, "Test", None, None, None, None, [self.context], units)
        self.site = f.createIfcSite(self.guid(), self.history, "Site", None, None, self.placement(), None, None, "ELEMENT")
        f.createIfcRelAggregates(self.guid(), self.history, None, None, self.project, [self.site])
        self.elements = []

    @staticmethod
    def guid() -> str:
        return ifcopenshell.guid.new()

    def point(self, xyz):
        return self.file.createIfcCartesianPoint([float(c) for c in xyz])

    def direction(self, xyz):
        return self.file.createIfcDirection([float(c) for c in xyz])

    def axis(self, origin, z=(0.0, 0.0, 1.0), x=(1.0, 0.0, 0.0)):
        return self.file.createIfcAxis2Placement3D(self.point(origin), self.direction(z), self.direction(x))

    def placement(self, origin=(0.0, 0.0, 0.0), x=(1.0, 0.0, 0.0), z=(0.0, 0.0, 1.0)):
        return self.file.createIfcLocalPlacement(None, self.axis(origin, z, x))

    def extrusion(self, profile, depth, position=(0.0, 0.0, 0.0)):
        return self.file.createIfcExtrudedAreaSolid(profile, self.axis(position), self.direction((0, 0, 1)), float(depth))

    def rectangle(self, xdim, ydim, centre=(0.0, 0.0)):
        position = self.file.createIfcAxis2Placement2D(self.file.createIfcCartesianPoint([float(c) for c in centre]))
        return self.file.createIfcRectangleProfileDef("AREA", None, position, float(xdim), float(ydim))

    def circle(self, radius):
        position = self.file.createIfcAxis2Placement2D(self.file.createIfcCartesianPoint([0.0, 0.0]))
        return self.file.createIfcCircleProfileDef("AREA", None, position, float(radius))

    def shape(self, items, kind="SweptSolid"):
        representation = self.file.createIfcShapeRepresentation(self.body, "Body", kind, items)
        return self.file.createIfcProductDefinitionShape(None, None, [representation])

    def element(self, ifc_class, name, shape, placement):
        f = self.file
        element = f.create_entity(
            ifc_class, GlobalId=self.guid(), OwnerHistory=self.history, Name=name,
            ObjectPlacement=placement, Representation=shape,
        )
        self.elements.append(element)
        return element

    def opening(self, element, shape, placement):
        f = self.file
        opening = f.createIfcOpeningElement(self.guid(), self.history, "Opening", None, None, placement, shape, None)
        f.createIfcRelVoidsElement(self.guid(), self.history, None, None, element, opening)
        return opening

    def write(self, path: Path) -> Path:
        self.file.createIfcRelContainedInSpatialStructure(
            self.guid(), self.history, None, None, self.elements, self.site
        )
        self.file.write(str(path))
        return path


def _rotation_z(degrees: float) -> numpy.ndarray:
    a = math.radians(degrees)
    return numpy.array([[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0.0, 0.0, 1.0]])


def _box_corners(x0, y0, z0, x1, y1, z1) -> numpy.ndarray:
    return numpy.array([(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], dtype=float)


# Chord error allowed on round geometry: IfcOpenShell's default mesher-linear-deflection (1 mm), which
# the hybrid kernel's CGAL tessellation meets (OpenCASCADE stays below half of it).
CHORD_TOLERANCE = 0.5e-3


@pytest.fixture(scope="module")
def models(tmp_path_factory):
    """The synthetic models, converted in every mode: {name: (expected, {mode: {GlobalId: Shape}}, infos)}."""
    directory = tmp_path_factory.mktemp("accuracy")
    built = {name: builder(directory) for name, builder in BUILDERS.items()}
    result = {}
    for name, (path, expected) in built.items():
        outputs, infos = {}, {}
        for mode, (fmt, geometry, blocks) in accuracy.MODES.items():
            output = directory / f"{name}.{mode}.{fmt}"
            convert(path, output, fmt=fmt, geometry=geometry, threads=1, blocks=blocks)
            outputs[mode], infos[mode] = accuracy.read_output(output, fmt, set(expected))
        result[name] = (expected, outputs, infos)
    return result


def _mm_wall(directory: Path):
    """A 5000 x 200 x 3000 mm wall with a 1000 x 2000 mm opening, turned 30 degrees, in a millimetre model."""
    m = _Model(unit="MILLIMETRE")
    origin = numpy.array((12345.0, 6789.0, 100.0))
    rotation = _rotation_z(30)
    placement = m.placement(origin, x=rotation[:, 0])
    # The rectangle profile is centred on its position: shift it so the wall spans x 0-5000, y 0-200.
    wall = m.element("IfcWall", "Wall", m.shape([m.extrusion(m.rectangle(5000, 200, (2500, 100)), 3000)]), placement)
    opening_placement = m.file.createIfcLocalPlacement(placement, m.axis((2000.0, -50.0, 500.0)))
    m.opening(wall, m.shape([m.extrusion(m.rectangle(1000, 300, (500, 150)), 2000)]), opening_placement)
    path = m.write(directory / "mm_wall.ifc")
    local = numpy.concatenate([_box_corners(0, 0, 0, 5000, 200, 3000), _box_corners(2000, 0, 500, 3000, 200, 2500)])
    corners = (local @ rotation.T + origin) / 1000
    expected = {"corners": corners, "volume": (5 * 3 - 1 * 2) * 0.2, "area": 2 * (15 - 2) + 2 * (5 + 3) * 0.2 + 2 * (1 + 2) * 0.2}
    return path, {wall.GlobalId: expected}


def _feet_box(directory: Path):
    """A 10 x 1 x 8 ft wall at (100 ft, 50 ft, 0) in an IFC2X3 model in feet."""
    m = _Model(schema="IFC2X3", unit="FOOT")
    wall = m.element(
        "IfcWallStandardCase", "Wall", m.shape([m.extrusion(m.rectangle(10, 1, (5, 0.5)), 8)]), m.placement((100.0, 50.0, 0.0))
    )
    path = m.write(directory / "feet.ifc")
    ft = 0.3048
    corners = _box_corners(100, 50, 0, 110, 51, 8) * ft
    expected = {"corners": corners, "volume": 80 * ft ** 3, "area": 2 * (10 * 1 + 10 * 8 + 1 * 8) * ft ** 2}
    return path, {wall.GlobalId: expected}


def _round_column(directory: Path):
    """A round column, radius 250 mm and 3000 mm high, at (4000, 3000, 0) mm."""
    m = _Model(unit="MILLIMETRE")
    column = m.element("IfcColumn", "Column", m.shape([m.extrusion(m.circle(250), 3000)]), m.placement((4000.0, 3000.0, 0.0)))
    path = m.write(directory / "column.ifc")
    return path, {column.GlobalId: {"circle": ((4.0, 3.0), 0.25, (0.0, 3.0))}}


def _georeferenced(directory: Path):
    """IFC4 with an IfcMapConversion: one wall at large project coordinates (shared coordinates, as
    Revit exports them), one near the origin that must stay there (the map conversion is not applied)."""
    m = _Model(unit="METRE")
    f = m.file
    crs = f.createIfcProjectedCRS("EPSG:25832", None, None, None, None, None, None)
    f.createIfcMapConversion(m.context, crs, 512000.0, 5423000.0, 300.0, 0.8, 0.6, 1.0)
    far_origin = numpy.array((512345.6789, 5423456.7891, 312.1234))
    far = m.element("IfcWall", "Far", m.shape([m.extrusion(m.rectangle(5, 0.2, (2.5, 0.1)), 3)]), m.placement(tuple(far_origin)))
    near_origin = numpy.array((12.3456, 7.8912, 0.0))
    near = m.element("IfcWall", "Near", m.shape([m.extrusion(m.rectangle(5, 0.2, (2.5, 0.1)), 3)]), m.placement(tuple(near_origin)))
    # Type geometry with an opening cut into it: the kernel only builds it in world coordinates.
    source = f.createIfcShapeRepresentation(m.body, "Body", "SweptSolid", [m.extrusion(m.rectangle(2, 0.6, (1, 0.3)), 0.9)])
    representation_map = f.createIfcRepresentationMap(m.axis((0.0, 0.0, 0.0)), source)
    operator = f.createIfcCartesianTransformationOperator3D(None, None, m.point((0, 0, 0)), None, None)
    cabinet_origin = far_origin + (10.0, 0.0, 0.0)
    cabinet_placement = m.placement(tuple(cabinet_origin))
    cabinet = m.element(
        "IfcFurnishingElement", "Cabinet", m.shape([f.createIfcMappedItem(representation_map, operator)], "MappedRepresentation"),
        cabinet_placement,
    )
    m.opening(cabinet, m.shape([m.extrusion(m.rectangle(0.5, 0.4, (0.25, 0.2)), 1.0)]),
              f.createIfcLocalPlacement(cabinet_placement, m.axis((0.75, 0.1, 0.5))))
    path = m.write(directory / "georeferenced.ifc")
    box = _box_corners(0, 0, 0, 5, 0.2, 3)
    sink = numpy.concatenate([_box_corners(0, 0, 0, 2, 0.6, 0.9), _box_corners(0.75, 0.1, 0.5, 1.25, 0.5, 0.9)])
    expected = {
        far.GlobalId: {"corners": box + far_origin, "volume": 3.0, "area": 2 * (1 + 15 + 0.6)},
        near.GlobalId: {"corners": box + near_origin, "volume": 3.0, "area": 2 * (1 + 15 + 0.6)},
        cabinet.GlobalId: {"corners": sink + cabinet_origin, "volume": 2 * 0.6 * 0.9 - 0.5 * 0.4 * 0.4, "cut_type": True},
    }
    return path, expected


def _mapped(directory: Path):
    """One 1000 x 500 x 2000 mm type geometry placed plain, mirrored, scaled 2x and scaled non-uniformly."""
    m = _Model(unit="MILLIMETRE")
    f = m.file
    source = f.createIfcShapeRepresentation(
        m.body, "Body", "SweptSolid", [m.extrusion(m.rectangle(1000, 500, (500, 250)), 2000)]
    )
    representation_map = f.createIfcRepresentationMap(m.axis((0.0, 0.0, 0.0)), source)
    local = _box_corners(0, 0, 0, 1000, 500, 2000)
    variants = {
        "plain": (f.createIfcCartesianTransformationOperator3D(None, None, m.point((0, 0, 0)), None, None), numpy.eye(3)),
        "mirrored": (
            f.createIfcCartesianTransformationOperator3D(m.direction((1, 0, 0)), m.direction((0, -1, 0)), m.point((0, 0, 0)), None, m.direction((0, 0, 1))),
            numpy.diag([1.0, -1.0, 1.0]),
        ),
        "scaled": (f.createIfcCartesianTransformationOperator3D(None, None, m.point((0, 0, 0)), 2.0, None), numpy.eye(3) * 2),
        "non-uniform": (
            f.createIfcCartesianTransformationOperator3DnonUniform(None, None, m.point((0, 0, 0)), 1.5, None, 0.5, 2.0),
            numpy.diag([1.5, 0.5, 2.0]),
        ),
    }
    expected = {}
    for k, (name, (operator, linear)) in enumerate(variants.items()):
        item = f.createIfcMappedItem(representation_map, operator)
        origin = numpy.array((k * 5000.0, 1000.0, 0.0))
        element = m.element("IfcFurnishingElement", name, m.shape([item], "MappedRepresentation"), m.placement(tuple(origin)))
        corners = (local @ linear.T + origin) / 1000
        scale = abs(numpy.linalg.det(linear))
        expected[element.GlobalId] = {"corners": corners, "volume": 1.0 * 0.5 * 2.0 * scale, "name": name}
    path = m.write(directory / "mapped.ifc")
    return path, expected


def _hollow(directory: Path):
    """A 1 m cube with a closed 0.5 m cube void inside (a boolean difference), in metres."""
    m = _Model(unit="METRE")
    outer = m.extrusion(m.rectangle(1, 1, (0.5, 0.5)), 1)
    void = m.extrusion(m.rectangle(0.5, 0.5, (0.5, 0.5)), 0.5, position=(0.0, 0.0, 0.25))
    solid = m.file.createIfcBooleanResult("DIFFERENCE", outer, void)
    element = m.element("IfcBuildingElementProxy", "Hollow", m.shape([solid], "CSG"), m.placement((2.0, 3.0, 0.0)))
    path = m.write(directory / "hollow.ifc")
    corners = numpy.concatenate([_box_corners(0, 0, 0, 1, 1, 1), _box_corners(0.25, 0.25, 0.25, 0.75, 0.75, 0.75)]) + (2.0, 3.0, 0.0)
    return path, {element.GlobalId: {"corners": corners, "volume": 1 - 0.125, "area": 6 + 1.5}}


BUILDERS = {
    "mm_wall": _mm_wall,
    "feet": _feet_box,
    "round_column": _round_column,
    "georeferenced": _georeferenced,
    "mapped": _mapped,
    "hollow": _hollow,
}


# ------------------------------------------------------------------------------------------ tests


def _assert_corners(shape: accuracy.Shape, corners: numpy.ndarray, tolerance: float = TOLERANCE) -> None:
    """Every output vertex is one of the expected corners, and every corner is an output vertex."""
    distances = numpy.sqrt(((shape.points[:, None, :] - corners[None, :, :]) ** 2).sum(axis=2))
    assert distances.min(axis=1).max() <= tolerance, "an output vertex is off every expected corner"
    assert distances.min(axis=0).max() <= tolerance, "an expected corner is missing from the output"


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name", ["mm_wall", "feet", "georeferenced", "mapped"])
def test_planar_dimensions(models, name, mode):
    expected, outputs, _ = models[name]
    shapes = outputs[mode]
    assert set(shapes) == set(expected)
    for guid, truth in expected.items():
        if truth.get("cut_type"):
            continue  # test_cut_type_geometry_far_from_origin
        shape = shapes[guid]
        _assert_corners(shape, truth["corners"])
        numpy.testing.assert_allclose(shape.bbox[:3], truth["corners"].min(axis=0), atol=TOLERANCE, rtol=0)
        numpy.testing.assert_allclose(shape.bbox[3:], truth["corners"].max(axis=0), atol=TOLERANCE, rtol=0)
        assert abs(shape.volume) == pytest.approx(truth["volume"], rel=1e-6)
        if "area" in truth:
            assert shape.area == pytest.approx(truth["area"], rel=1e-6)


@pytest.mark.parametrize("mode", MODES)
def test_round_column(models, mode):
    expected, outputs, _ = models["round_column"]
    (guid, truth), = expected.items()
    shape = outputs[mode][guid]
    (cx, cy), radius, (z0, z1) = truth["circle"]
    rho = numpy.hypot(shape.points[:, 0] - cx, shape.points[:, 1] - cy)
    rim = rho > radius / 2
    # Vertices lie on the true circle and the top and bottom are exact.
    assert numpy.abs(rho[rim] - radius).max() <= TOLERANCE
    assert shape.bbox[2] == pytest.approx(z0, abs=TOLERANCE) and shape.bbox[5] == pytest.approx(z1, abs=TOLERANCE)
    inverse = numpy.eye(4)
    inverse[:3, 3] = (-cx, -cy, 0.0)
    chord, on_circle = accuracy.chord_error(shape, (inverse, 0.0, 0.0, radius, z1))
    assert on_circle <= TOLERANCE
    assert chord <= CHORD_TOLERANCE
    # The inscribed polygon loses at most the chord error all around.
    exact = math.pi * radius ** 2 * (z1 - z0)
    assert exact * (1 - 2 * CHORD_TOLERANCE / radius) <= shape.volume <= exact * (1 + 1e-9)


def test_rhino_file_is_metres_with_millimetre_tolerance(models):
    _, _, infos = models["mm_wall"]
    for mode in ("3dm-brep", "3dm-mesh"):
        info = infos[mode]
        assert info["units"] == "Meters"
        assert info["absolute_tolerance"] == pytest.approx(0.001)
        assert info["angle_tolerance_degrees"] == pytest.approx(1.0)
        assert info["single_precision_meshes"] == 0


def test_block_modes_place_type_geometry_as_instances(models):
    # The checks above measure the block modes as Rhino draws them: these are block instances
    # (plain, mirrored, scaled and non-uniformly scaled), not copies.
    _, _, infos = models["mapped"]
    for mode in ("3dm-brep-blocks", "3dm-mesh-blocks"):
        assert infos[mode]["block_instances"] == 4
    assert infos["3dm-brep"]["block_instances"] == 0


# IfcOpenShell applies a mirroring type placement to the vertices without reversing the triangles,
# in local and in world coordinates alike: the mesh formats get mirrored elements inside out (their
# normals point inwards). Polysurfaces are re-oriented by the converter.
# IfcOpenShell's own GLB/OBJ writers keep mirrored type geometry inside out; the 3dm export turns it around.
INSIDE_OUT = pytest.mark.xfail(strict=True, reason="GLB/OBJ: mirrored type geometry is inside out (IfcOpenShell)")


@pytest.mark.parametrize("mode", [m if m.startswith("3dm") else pytest.param(m, marks=INSIDE_OUT) for m in MODES])
def test_mirrored_type_geometry_points_outwards(models, mode):
    expected, outputs, _ = models["mapped"]
    for guid, truth in expected.items():
        assert outputs[mode][guid].volume == pytest.approx(truth["volume"], rel=1e-6), truth["name"]


# The converter points every closed shell of a polysurface outwards, also the void of a hollow solid,
# which then adds its volume instead of taking it away (proposed fix: only turn solids as a whole).


@pytest.mark.parametrize("mode", MODES)
def test_hollow_solid_keeps_its_void(models, mode):
    expected, outputs, _ = models["hollow"]
    (guid, truth), = expected.items()
    shape = outputs[mode][guid]
    _assert_corners(shape, truth["corners"])
    assert shape.area == pytest.approx(truth["area"], rel=1e-6)
    assert shape.volume == pytest.approx(truth["volume"], rel=1e-6)


@pytest.mark.parametrize("mode", MODES)
def test_precision_far_from_origin(models, mode):
    """Shared coordinates half a million metres out keep micrometre precision in every format."""
    expected, outputs, infos = models["georeferenced"]
    for guid, truth in expected.items():
        if not truth.get("cut_type"):
            _assert_corners(outputs[mode][guid], truth["corners"], tolerance=1e-6)
    if mode == "obj":
        assert infos[mode]["max_digits"] >= 11  # 5423456.7891: all digits written


# The hybrid kernel returns no geometry in local coordinates for type geometry with openings cut into
# it, and the converter then takes it in world coordinates: GLB stores those in single precision,
# 0.2 m off half a million metres out. OpenCASCADE builds it in local coordinates (proposed fix).


@pytest.mark.parametrize("mode", MODES)
def test_cut_type_geometry_far_from_origin(models, mode):
    expected, outputs, _ = models["georeferenced"]
    (guid, truth), = ((g, t) for g, t in expected.items() if t.get("cut_type"))
    shape = outputs[mode][guid]
    _assert_corners(shape, truth["corners"])
    assert abs(shape.volume) == pytest.approx(truth["volume"], rel=1e-6)


def test_point_triangle_distance():
    points = numpy.array([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
    triangles = numpy.array([(0, 1, 2)])
    query = numpy.array([(0.2, 0.2, 0.5), (2.0, 0.0, 0.0), (-1.0, -1.0, 0.0), (0.5, 0.5, 0.0)])
    numpy.testing.assert_allclose(
        accuracy.distances_to_mesh(query, points, triangles), [0.5, 1.0, math.sqrt(2), 0.0], atol=1e-12
    )


def test_ground_truth_from_ifc_values(tmp_path):
    """The checker's own expectations, computed from profiles, placements and units, match the fixtures."""
    for builder in (_feet_box, _mapped, _round_column):
        path, expected = builder(tmp_path)
        model = accuracy.open_model(path)
        truths = accuracy.expectations(model, accuracy.candidates(model))
        assert set(truths) == set(expected)
        for guid, truth in truths.items():
            if "corners" in expected[guid]:
                numpy.testing.assert_allclose(numpy.sort(truth.corners, axis=0), numpy.sort(expected[guid]["corners"], axis=0), atol=1e-9)
                assert truth.volume == pytest.approx(expected[guid]["volume"], rel=1e-9)
            else:
                (cx, cy), radius, (z0, z1) = expected[guid]["circle"]
                assert truth.curved and truth.volume == pytest.approx(math.pi * radius ** 2 * (z1 - z0), rel=1e-9)


def test_mirrored_type_instances_are_counted(tmp_path):
    path, expected = _mapped(tmp_path)
    model = accuracy.open_model(path)
    mirrored = {p.Name for p in accuracy.candidates(model) if accuracy.is_mirrored(p)}
    assert mirrored == {"mirrored"}


def test_checker_end_to_end(tmp_path):
    path, _ = _feet_box(tmp_path)
    report = accuracy.check_file(path, ["3dm-brep", "glb"], tmp_path, sample=10, threads=1, log=lambda text: None)
    assert report["length_unit_m"] == pytest.approx(0.3048)
    for mode in ("3dm-brep", "glb"):
        entry = report["modes"][mode]
        assert entry["status"] == "ok" and entry["missing_count"] == 0
        assert entry["vs_same_kernel"]["vertex_mm"]["max"] <= 0.01
        assert entry["ground_truth"]["corners_mm"]["max"] <= 0.01
        assert entry["ground_truth"]["volume_planar_mm"]["max"] <= 0.01
    accuracy.write_report([report], tmp_path / "report.md")
    assert "feet.ifc" in (tmp_path / "report.md").read_text()


def test_nearest_vertex_search_matches_brute_force():
    rng = numpy.random.default_rng(1)
    points = rng.uniform(0, 0.01, (500, 3)) + (512000.0, 5423000.0, 300.0)
    query = points[rng.choice(500, 50)] + rng.normal(0, 2e-4, (50, 3))
    brute = numpy.sqrt(((query[:, None] - points[None]) ** 2).sum(axis=2)).min(axis=1)
    found = accuracy.nearest_vertex_distances(query, points)
    close = brute < 1e-3
    numpy.testing.assert_allclose(found[close], brute[close], atol=1e-12)
    assert (found[~close] >= 1e-3 - 1e-12).all()


def test_accurate_kernel_is_deterministic(tmp_path, monkeypatch):
    """The same triangles per element on 2 and 4 threads and with chunks of 1 or all elements."""
    from ifc_converter import converter

    models = [builder(tmp_path) for builder in (_mapped, _georeferenced, _hollow, _mm_wall)]
    results = []
    for threads, chunk in ((2, None), (4, None), (4, 1)):
        if chunk:
            monkeypatch.setattr(converter, "chunk_size", lambda threads: chunk)
        signature = {}
        for path, expected in models:
            output = tmp_path / f"{path.stem}.{threads}.{chunk}.obj"
            convert(path, output, fmt="obj", threads=threads, kernel="accurate")
            shapes, _ = accuracy.read_output(output, "obj", set(expected))
            for guid, shape in shapes.items():
                signature[guid] = (len(shape.triangles), round(shape.area, 9), round(shape.volume, 9), tuple(shape.bbox.round(9)))
        results.append(signature)
    assert results[0] == results[1] == results[2]
