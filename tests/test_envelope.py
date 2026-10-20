"""Option "Nur Gebäudehülle": only what is seen from outside is converted (envelope)."""

import ifcopenshell
import ifcopenshell.api as api
import numpy
import pytest

from ifc_converter import envelope
from ifc_converter.converter import EXCLUDED_CLASSES, convert, shape_products


def _box(model, body, ifc_class: str, name: str, size, at, container=None, aggregate=None):
    """An element of ``ifc_class`` as a box of ``size`` (x, y, z) with its corner at ``at``."""
    element = api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    representation = api.run(
        "geometry.add_wall_representation", model, context=body, length=size[0], height=size[2], thickness=size[1],
    )
    api.run("geometry.assign_representation", model, product=element, representation=representation)
    matrix = numpy.eye(4)
    matrix[:3, 3] = at
    api.run("geometry.edit_object_placement", model, product=element, matrix=matrix)
    if container is not None:
        api.run("spatial.assign_container", model, relating_structure=container, products=[element])
    return element


@pytest.fixture
def house_ifc(tmp_path):
    """A closed 10 x 8 x 3 m house: four exterior walls, floor and roof slabs, an interior wall and a
    table inside, a column outside next to it. The interior wall is wrongly flagged IsExternal = False
    and the table has no flag; the column is flagged IsExternal = True."""
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
    _box(model, body, "IfcWall", "South", (10, t, 3), (0, 0, 0), storey)
    _box(model, body, "IfcWall", "North", (10, t, 3), (0, 8 - t, 0), storey)
    _box(model, body, "IfcWall", "West", (t, 8, 3), (0, 0, 0), storey)
    _box(model, body, "IfcWall", "East", (t, 8, 3), (10 - t, 0, 0), storey)
    _box(model, body, "IfcSlab", "Floor", (10, 8, t), (0, 0, -t), storey)
    _box(model, body, "IfcSlab", "Roof", (10, 8, t), (0, 0, 3), storey)
    inner = _box(model, body, "IfcWall", "Inner", (t, 8 - 2 * t, 3), (5, t, 0), storey)
    _box(model, body, "IfcFurniture", "Table", (1.5, 0.8, 0.75), (1, 2, 0), storey)
    column = _box(model, body, "IfcColumn", "Column", (0.4, 0.4, 3), (12, 2, 0), storey)
    for element, flag in ((inner, False), (column, True)):
        pset = api.run("pset.add_pset", model, product=element, name=f"Pset_{element.is_a()[3:]}Common")
        api.run("pset.edit_pset", model, pset=pset, properties={"IsExternal": flag})
    path = tmp_path / "house.ifc"
    model.write(str(path))
    return path


def _names(model, ids) -> set[str]:
    return {model.by_id(id_).Name for id_ in ids}


def test_the_hull_of_a_house(house_ifc):
    model = ifcopenshell.open(str(house_ifc))
    products = shape_products(model, EXCLUDED_CLASSES)
    selection = envelope.select(model, 2, products)
    assert _names(model, selection.keep) == {"South", "North", "West", "East", "Floor", "Roof", "Column"}
    assert (selection.total, selection.inside, selection.unknown, selection.flagged) == (9, 2, 0, 0)
    assert selection.voxel == envelope.VOXEL
    exposure = {model.by_id(id_).Name: share for id_, share in selection.exposure.items()}
    assert exposure["Inner"] == 0 and exposure["Table"] == 0
    assert exposure["Column"] > 0.8 and exposure["Roof"] > 0.4 and exposure["South"] > 0.3
    assert "7 von 9 Bauteilen liegen außen" in selection.note and "2 innen liegende" in selection.note


def test_is_external_keeps_an_element_the_fill_cannot_see(house_ifc):
    model = ifcopenshell.open(str(house_ifc))
    inner = next(wall for wall in model.by_type("IfcWall") if wall.Name == "Inner")
    pset = ifcopenshell.util.element.get_psets(inner)["Pset_WallCommon"]
    api.run("pset.edit_pset", model, pset=model.by_id(pset["id"]), properties={"IsExternal": True})
    assert envelope.external_flags(model) == {inner.id(), next(c.id() for c in model.by_type("IfcColumn"))}
    assert envelope.external_marks(model) == {inner.id(): True, next(c.id() for c in model.by_type("IfcColumn")): True}
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert "Inner" in _names(model, selection.keep) and selection.flagged == 1 and selection.inside == 1
    assert "1 als außen gekennzeichnete" in selection.note


def test_is_external_of_the_type_counts(house_ifc):
    model = ifcopenshell.open(str(house_ifc))
    table = model.by_type("IfcFurniture")[0]
    table_type = api.run("root.create_entity", model, ifc_class="IfcFurnitureType", name="Tables")
    api.run("type.assign_type", model, related_objects=[table], relating_type=table_type)
    pset = api.run("pset.add_pset", model, product=table_type, name="Pset_FurnitureTypeCommon")
    api.run("pset.edit_pset", model, pset=pset, properties={"IsExternal": True})
    assert table.id() in envelope.external_flags(model)
    # An own property set wins over the type's.
    own = api.run("pset.add_pset", model, product=table, name="Pset_FurnitureCommon")
    api.run("pset.edit_pset", model, pset=own, properties={"IsExternal": False})
    assert envelope.external_marks(model)[table.id()] is False


def test_without_a_roof_the_property_sets_decide(house_ifc):
    # Outside air reaches everything, so the fill alone would keep all 8 products: then IsExternal
    # and the furniture classes decide.
    model = ifcopenshell.open(str(house_ifc))
    roof = next(slab for slab in model.by_type("IfcSlab") if slab.Name == "Roof")
    api.run("root.remove_product", model, product=roof)
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert selection.open_hull and (selection.marked, selection.fittings, selection.inside) == (1, 1, 2)
    assert _names(model, selection.keep) == {"South", "North", "West", "East", "Floor", "Column"}
    assert "keine geschlossene Hülle" in selection.note and "6 von 8 Bauteilen" in selection.note
    assert "1 als innen gekennzeichnete" in selection.note and "1 Möbel" in selection.note


def test_a_closed_hull_with_few_interior_products_is_not_taken_as_open(house_ifc, monkeypatch):
    monkeypatch.setattr(envelope, "OPEN_HULL_SHARE", 0.0)
    model = ifcopenshell.open(str(house_ifc))
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert not selection.open_hull and selection.inside == 2


def test_products_without_coarse_geometry_are_kept(house_ifc, monkeypatch):
    model = ifcopenshell.open(str(house_ifc))
    products = shape_products(model, EXCLUDED_CLASSES)
    table = model.by_type("IfcFurniture")[0]
    real = envelope._coarse_shapes

    def without_table(model, threads, products, report, progress):
        yield from real(model, threads, [p for p in products if p.id() != table.id()], report, progress)

    monkeypatch.setattr(envelope, "_coarse_shapes", without_table)
    selection = envelope.select(model, 2, products)
    assert table.id() in selection.keep and selection.unknown == 1 and selection.inside == 1
    assert "1 ohne Vorab-Geometrie" in selection.note


def test_a_huge_model_coarsens_its_grid(house_ifc, monkeypatch):
    # The house samples about 62,000 cells at 0.1 m: 8,000 force two doublings while sampling (to
    # 0.4 m, 4,000 cells), and 5,000 cells of grid (the house needs 10,500 at 0.4 m) one more.
    monkeypatch.setattr(envelope, "MAX_SAMPLED", 8000)
    monkeypatch.setattr(envelope, "MAX_VOXELS", 5_000)
    model = ifcopenshell.open(str(house_ifc))
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert selection.voxel == 0.8 and "Raster 0,8 m" in selection.note
    kept = _names(model, selection.keep)
    # Coarser cells keep more, never less: the walls are thinner than a cell now, so the interior
    # wall meeting them looks exposed; the table in the middle of the room does not.
    assert {"South", "North", "West", "East", "Floor", "Roof", "Column"} <= kept and "Table" not in kept


def test_far_away_products_are_kept_as_unknown(house_ifc):
    model = ifcopenshell.open(str(house_ifc))
    table = model.by_type("IfcFurniture")[0]
    matrix = numpy.eye(4)
    matrix[:3, 3] = (1e6, 0, 0)  # 1000 km from the house
    api.run("geometry.edit_object_placement", model, product=table, matrix=matrix)
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert table.id() in selection.keep and selection.unknown == 1


def _obj_elements(path) -> dict[str, list]:
    elements: dict[str, list] = {}
    current = None
    for line in path.read_text().splitlines():
        if line.startswith("g "):
            current = elements.setdefault(line[2:], [])
        elif line.startswith("v ") and current is not None:
            current.append(list(map(float, line.split()[1:4])))
    return elements


def test_convert_with_the_hull_only(house_ifc, tmp_path):
    notes, phases = [], []

    def status(phase, text):
        phases.append(phase)
        if phase == "note":
            notes.append(text)

    percents = []
    full = convert(house_ifc, tmp_path / "full.obj", "obj", threads=2)
    hull = convert(house_ifc, tmp_path / "hull.obj", "obj", threads=2, envelope=True, status=status,
                   progress=percents.append)
    assert (full.elements, full.inside) == (9, 0)
    assert (hull.elements, hull.inside, hull.skipped) == (7, 2, 0)
    assert any(note.startswith("Nur Gebäudehülle: 7 von 9") for note in notes)
    assert "envelope" in phases and phases.index("envelope") < phases.index("geometry")
    assert percents == sorted(percents) and percents[0] == 0 and percents[-1] == 100
    full_elements, hull_elements = _obj_elements(tmp_path / "full.obj"), _obj_elements(tmp_path / "hull.obj")
    assert len(full_elements) == 9 and len(hull_elements) == 7
    for name, points in hull_elements.items():  # the kept elements are exactly as without the option
        assert points == full_elements[name]
    everything = numpy.array([p for points in full_elements.values() for p in points])
    kept = numpy.array([p for points in hull_elements.values() for p in points])
    assert numpy.allclose(everything.min(axis=0), kept.min(axis=0))
    assert numpy.allclose(everything.max(axis=0), kept.max(axis=0))


def test_the_preview_ignores_the_option(house_ifc, tmp_path):
    result = convert(house_ifc, tmp_path / "p.npz", "preview", threads=2, envelope=True)
    assert result.elements == 9 and result.inside == 0
