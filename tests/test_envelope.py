"""Option "Nur Gebäudehülle": only what is seen from outside is converted (envelope)."""

import ifcopenshell
import ifcopenshell.api as api
import numpy
import pytest

from ifc_converter import envelope, i18n
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


def _mark_external(model, *names) -> None:
    for product in model.by_type("IfcProduct"):
        if product.Name in names:
            psets = ifcopenshell.util.element.get_psets(product)
            name = f"Pset_{product.is_a()[3:]}Common"
            pset = model.by_id(psets[name]["id"]) if name in psets else api.run("pset.add_pset", model, product=product, name=name)
            api.run("pset.edit_pset", model, pset=pset, properties={"IsExternal": True})


def test_marks_that_cover_nearly_every_unexposed_element_are_ignored(house_ifc, monkeypatch):
    """A file that marks everything IsExternal = True (seen on a 1.5 GB model: 65,197 of 65,197
    unexposed elements) would keep the whole building: then the fill alone decides."""
    model = ifcopenshell.open(str(house_ifc))
    _mark_external(model, "Inner", "Table")  # both unexposed and marked: 2 of 2
    products = shape_products(model, EXCLUDED_CLASSES)
    selection = envelope.select(model, 2, products)
    assert selection.flagged == 2 and selection.inside == 0 and not selection.marks_ignored  # too few to judge
    monkeypatch.setattr(envelope, "MARKS_UNTRUSTED_MIN", 2)
    selection = envelope.select(model, 2, products)
    assert _names(model, selection.keep) == {"South", "North", "West", "East", "Floor", "Roof", "Column"}
    assert (selection.flagged, selection.inside, selection.marks_ignored) == (0, 2, 2)
    assert "2 als außen gekennzeichnete (IsExternal) ebenfalls weggelassen" in selection.note
    # One unexposed element without the mark (1 of 3 marked): the marks still count.
    monkeypatch.setattr(envelope, "MARKS_UNTRUSTED_MIN", 1)
    pset = ifcopenshell.util.element.get_psets(next(p for p in products if p.Name == "Table"))["Pset_FurnitureCommon"]
    api.run("pset.edit_pset", model, pset=model.by_id(pset["id"]), properties={"IsExternal": False})
    selection = envelope.select(model, 2, products)
    assert (selection.flagged, selection.inside, selection.marks_ignored) == (1, 1, 0)


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
    assert selection.note.endswith(" Weggelassen: 1 IfcFurniture, 1 IfcWall.")
    assert selection.dropped_classes == {"IfcFurniture": 1, "IfcWall": 1}
    i18n.set_language("en")  # the note is made when it is read, in the language of that moment
    assert selection.note.startswith("Building hull only: 7 of 9 elements are on the outside")
    assert selection.note.endswith("(grid 0.05 m, coarse 0.2 m). Left out: 1 IfcFurniture, 1 IfcWall.")


def test_a_product_with_the_smallest_visible_part_stays(house_ifc):
    # A lintel-like block in the south wall, flush with the inner face and reaching the outer face
    # only with a 5 cm strip through a slot in the wall: whatever touches outside air is kept, so
    # the hull never gets a hole where a product with a small visible part was left out.
    model = ifcopenshell.open(str(house_ifc))
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    storey = model.by_type("IfcBuildingStorey")[0]
    _box(model, body, "IfcBeam", "Lintel", (2, 0.6, 0.3), (4, -0.3, 2.5), storey)  # sticks 0.3 m out of the wall
    _box(model, body, "IfcBeam", "Strip", (3, 0.35, 0.05), (1, 0.0, 1.0), storey)  # 5 cm beyond the outer face
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    kept = _names(model, selection.keep)
    assert "Lintel" in kept and "Strip" in kept
    exposure = {model.by_id(id_).Name: share for id_, share in selection.exposure.items()}
    assert 0 < exposure["Strip"] < 0.5


def test_a_gap_narrower_than_a_coarse_cell_stays_open(house_ifc):
    # A screen in front of the south wall's cladding with a 12 cm gap between them, lined by a thin
    # panel: the gap is sealed on the 0.2 m grid but open at 0.05 m, so the panel is seen through it.
    model = ifcopenshell.open(str(house_ifc))
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    storey = model.by_type("IfcBuildingStorey")[0]
    _box(model, body, "IfcCovering", "Backing", (8, 0.2, 3), (1, -0.2, 0), storey)
    _box(model, body, "IfcPlate", "Screen", (6, 0.2, 3), (2, -0.52, 0), storey)
    _box(model, body, "IfcCovering", "Panel", (4, 0.02, 1), (3, -0.22, 1), storey)
    products = shape_products(model, EXCLUDED_CLASSES)
    selection = envelope.select(model, 2, products)
    assert (selection.voxel, selection.coarse) == (0.05, 0.2)
    kept = _names(model, selection.keep)
    assert {"Backing", "Screen", "Panel"} <= kept and "Table" not in kept and "Inner" not in kept
    exposure = {model.by_id(id_).Name: share for id_, share in selection.exposure.items()}
    assert 0 < exposure["Panel"] <= 0.5  # only the face towards the gap


def test_many_dropped_classes_are_summed_up():
    selection = envelope.Selection(keep=set(), total=100, inside=60,
                                   dropped_classes={f"IfcClass{i}": i for i in range(1, 11)})
    assert selection.dropped_text == (" Weggelassen: 10 IfcClass10, 9 IfcClass9, 8 IfcClass8, 7 IfcClass7, 6 IfcClass6, "
                                      "5 IfcClass5, 4 IfcClass4, 3 IfcClass3, 3 weitere.")


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


def test_a_massing_volume_does_not_seal_the_house(house_ifc):
    # A Revit conceptual mass comes out as a simple box around the whole building: it must not hide
    # the real hull from the fill. It is kept itself (seen from outside), the house decided as without it.
    model = ifcopenshell.open(str(house_ifc))
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    storey = model.by_type("IfcBuildingStorey")[0]
    _box(model, body, "IfcBuildingElementProxy", "Mass", (14, 12, 5), (-1, -1, -1), storey)
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert selection.masses == 1 and "1 Baumassen" in selection.note
    assert _names(model, selection.keep) == {"South", "North", "West", "East", "Floor", "Roof", "Column", "Mass"}
    assert selection.inside == 2


def test_two_wing_masses_do_not_seal_the_house(house_ifc):
    # Two massing volumes, each around one half of the house: neither holds half of all products,
    # but each holds enough of them to be a mass and not a wall.
    model = ifcopenshell.open(str(house_ifc))
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    storey = model.by_type("IfcBuildingStorey")[0]
    _box(model, body, "IfcBuildingElementProxy", "Mass West", (5, 12, 5), (-1, -1, -1), storey)
    _box(model, body, "IfcBuildingElementProxy", "Mass East", (9, 12, 5), (4, -1, -1), storey)
    _box(model, body, "IfcFurniture", "Chair", (0.5, 0.5, 1), (1, 4, 0), storey)
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert selection.masses == 2
    kept = _names(model, selection.keep)
    assert {"South", "North", "West", "East", "Floor", "Roof", "Column", "Mass West", "Mass East"} <= kept
    assert "Table" not in kept and "Chair" not in kept and "Inner" not in kept


def test_ceilings_and_floorings_go_with_the_open_hull_fallback(house_ifc):
    model = ifcopenshell.open(str(house_ifc))
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    storey = model.by_type("IfcBuildingStorey")[0]
    ceiling = _box(model, body, "IfcCovering", "Ceiling", (6, 5, 0.05), (2, 1.5, 2.8), storey)  # no lid
    ceiling.PredefinedType = "CEILING"
    cladding = _box(model, body, "IfcCovering", "Cladding", (10, 0.05, 3), (0, -0.05, 0), storey)
    cladding.PredefinedType = "CLADDING"
    roof = next(slab for slab in model.by_type("IfcSlab") if slab.Name == "Roof")
    api.run("root.remove_product", model, product=roof)
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert selection.open_hull and selection.fittings == 2  # the table and the ceiling
    kept = _names(model, selection.keep)
    assert "Cladding" in kept and "Ceiling" not in kept and "Decken- und Bodenbeläge" in selection.note


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
    # The house samples about 250,000 cells at 0.05 m: 8,000 force three doublings while sampling
    # (to 0.4 m, 4,000 cells); the whole-model grid of 4 x 4 x 4 of them (1.6 m) then has 770 cells
    # with its padding, and 400 force one more doubling of it (3.2 m, 336 cells); the sampled cell stays.
    monkeypatch.setattr(envelope, "budgets", lambda: (8000, 400))
    model = ifcopenshell.open(str(house_ifc))
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert (selection.voxel, selection.coarse) == (0.4, 3.2) and "Raster 0,4 m, grob 3,2 m" in selection.note
    kept = _names(model, selection.keep)
    # Coarser cells keep more, never less: the walls are thinner than a cell now, so the interior
    # wall meeting them looks exposed; the table in the middle of the room does not.
    assert {"South", "North", "West", "East", "Floor", "Roof", "Column"} <= kept


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
    from ifc_converter.preview import load_preview

    result = convert(house_ifc, tmp_path / "p.npz", "preview", threads=2, envelope=True)
    # 8, not 9: the table is a detail the preview leaves out on its own (counted), not "inside".
    assert result.elements == 8 and result.inside == 0
    info = load_preview(tmp_path / "p.npz").info
    assert info["details_left_out"] == 1 and info["detail_kinds"] == "furniture"


def test_a_closed_house_with_nothing_inside_is_not_taken_as_open(house_ifc):
    # A shell model: the fill leaves out next to nothing, but the house encloses air, so it is
    # closed and the bench in front of it (furniture, seen from outside) stays.
    model = ifcopenshell.open(str(house_ifc))
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    storey = model.by_type("IfcBuildingStorey")[0]
    for name in ("Inner", "Table"):
        api.run("root.remove_product", model, product=next(p for p in model.by_type("IfcProduct") if p.Name == name))
    _box(model, body, "IfcFurniture", "Bench", (1.5, 0.5, 0.5), (3, -2, 0), storey)
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert not selection.open_hull and selection.inside == 0
    assert "Bench" in _names(model, selection.keep)


def test_nothing_sampled_never_triggers_the_fallback(house_ifc, monkeypatch):
    # Without coarse geometry at all (everything unknown) nothing may be dropped.
    model = ifcopenshell.open(str(house_ifc))
    monkeypatch.setattr(envelope, "_coarse_shapes", lambda *args: iter(()))
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert not selection.open_hull and selection.inside == 0 and selection.unknown == 9


def test_a_stray_product_kilometres_away_stays_out_of_the_grid(house_ifc):
    model = ifcopenshell.open(str(house_ifc))
    body = next(c for c in model.by_type("IfcGeometricRepresentationSubContext") if c.ContextIdentifier == "Body")
    storey = model.by_type("IfcBuildingStorey")[0]
    _box(model, body, "IfcBuildingElementProxy", "Survey point", (0.5, 0.5, 0.5), (8000, 0, 0), storey)
    selection = envelope.select(model, 2, shape_products(model, EXCLUDED_CLASSES))
    assert "Survey point" in _names(model, selection.keep) and selection.unknown == 1
    assert _names(model, selection.keep) == {"South", "North", "West", "East", "Floor", "Roof", "Column",
                                             "Survey point"}
    assert selection.voxel == envelope.VOXEL  # the grid did not grow to kilometres


def test_a_product_the_coarse_pass_hangs_on_is_kept(house_ifc, monkeypatch):
    # The coarse pass only approximates: a product the kernel hangs on there is given up after the
    # pass's limit, counts as unknown and stays in the output (like one without coarse geometry),
    # and is not reported as crashed or hung to the conversion.
    import threading

    from ifc_converter import converter

    monkeypatch.setenv(converter.HANG_ENV, "0.5")
    iterate = converter._iterate
    release = threading.Event()

    def hanging_iterate(model, settings, threads, products, library):
        table = [product for product in products if product.Name == "Table"]
        others = [product for product in products if product.Name != "Table"]
        shapes = list(iterate(model, settings, threads, others, library)) if others else []

        def run():
            yield from shapes
            if table:
                release.wait()

        return run()

    monkeypatch.setattr(converter, "_iterate", hanging_iterate)
    model = ifcopenshell.open(str(house_ifc))
    products = shape_products(model, EXCLUDED_CLASSES)
    notes, positions = [], []
    recovery = converter._recovery.set((lambda kind, ids, label: positions.append(kind), set(), set()))
    hung_list = ["untouched"]  # what convert() would collect the hung elements in
    hung = converter._hung.set(hung_list)
    try:
        selection = envelope.select(model, 2, products, lambda phase, text: notes.append((phase, text)))
    finally:
        release.set()
        converter._recovery.reset(recovery)
        converter._hung.reset(hung)
    table = model.by_type("IfcFurniture")[0]
    assert table.id() in selection.keep and selection.unknown == 1 and selection.inside == 1
    assert "Inner" not in _names(model, selection.keep)
    assert any(phase == "note" and text.startswith("Der Geometriekern hängt seit mehr als 0 min an IfcFurniture ")
               and text.endswith("„Table“ (grobe Vorberechnung): das Bauteil bleibt als Teil der Hülle erhalten")
               for phase, text in notes)
    # Nothing reported to the conversion: no "hung" position, nothing in its list of hung elements.
    assert "hung" not in positions and hung_list == ["untouched"]


def test_the_hull_text_comes_back_after_the_deep_elements(house_ifc, monkeypatch):
    # The coarse pass forwards the deep elements' status; once they are done, iter_shapes reports
    # "geometry", which must bring the hull's own text back instead of leaving the last deep
    # element's text in the window for the rest of the pass.
    from ifc_converter import converter

    def fake_iter_shapes(model, settings, threads, exclude, progress, share, products, status=None, **kwargs):
        status("deep", "Tief verschachteltes Bauteil (143 Ebenen) 1 von 1 wird einzeln berechnet: IfcCovering x …")
        status("geometry", "Geometrie wird berechnet (2 Threads) …")
        status("note", "eine Notiz")
        status("read", "nicht weitergegeben")
        return iter(())

    monkeypatch.setattr(converter, "iter_shapes", fake_iter_shapes)
    model = ifcopenshell.open(str(house_ifc))
    reported = []
    list(envelope._coarse_shapes(model, 2, shape_products(model, EXCLUDED_CLASSES),
                                 lambda phase, text: reported.append((phase, text)), None))
    assert reported == [
        ("deep", "Tief verschachteltes Bauteil (143 Ebenen) 1 von 1 wird einzeln berechnet: IfcCovering x …"),
        ("envelope", "Gebäudehülle wird bestimmt (Geometrie grob vorberechnet) …"),
        ("note", "eine Notiz"),
    ]


def test_the_coarse_pass_uses_the_hybrid_kernel_unless_asked_for_opencascade(house_ifc, monkeypatch):
    from ifc_converter import converter

    strategies = []

    def fake_iter_shapes(model, settings, threads, exclude, progress, share, products, status=None, **kwargs):
        strategies.append(converter.kernel_strategy())
        return iter(())

    monkeypatch.setattr(converter, "iter_shapes", fake_iter_shapes)
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    model = ifcopenshell.open(str(house_ifc))
    products = shape_products(model, EXCLUDED_CLASSES)
    list(envelope._coarse_shapes(model, 2, products, None, None))
    list(envelope._coarse_shapes(model, 2, products, None, None, "opencascade"))
    token = converter._kernel.set("opencascade")
    try:
        list(envelope._coarse_shapes(model, 2, products, None, None))
    finally:
        converter._kernel.reset(token)
    assert strategies == ["hybrid", "opencascade", "opencascade"]
