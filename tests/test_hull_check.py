"""tools/hull_check.py: the check of the option "Nur Gebäudehülle" on real models."""
from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

import ifcopenshell.api as api
import numpy
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import hull_check  # noqa: E402
from ifc_converter import envelope  # noqa: E402


def _house(tmp_path: Path) -> Path:
    """A storey with an exterior wall (own pset IsExternal=True), an interior wall whose type says
    IsExternal=False, and a proxy without any flag."""
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Test")
    api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METRE"})
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run("context.add_context", model, context_type="Model", context_identifier="Body",
                   target_view="MODEL_VIEW", parent=context)
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Haus")
    storey = api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="EG")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    def box(ifc_class, name, position):
        element = api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
        representation = api.run("geometry.add_wall_representation", model, context=body, length=4, height=3,
                                 thickness=0.3)
        api.run("geometry.assign_representation", model, product=element, representation=representation)
        matrix = numpy.eye(4)
        matrix[:3, 3] = position
        api.run("geometry.edit_object_placement", model, product=element, matrix=matrix)
        api.run("spatial.assign_container", model, relating_structure=storey, products=[element])
        return element

    outer = box("IfcWall", "Aussenwand", (0, 0, 0))
    pset = api.run("pset.add_pset", model, product=outer, name="Pset_WallCommon")
    api.run("pset.edit_pset", model, pset=pset, properties={"IsExternal": True})
    inner = box("IfcWall", "Innenwand", (0, 2, 0))
    wall_type = api.run("root.create_entity", model, ifc_class="IfcWallType", name="Innen")
    api.run("type.assign_type", model, related_objects=[inner], relating_type=wall_type)
    type_pset = api.run("pset.add_pset", model, product=wall_type, name="Pset_WallCommon")
    api.run("pset.edit_pset", model, pset=type_pset, properties={"IsExternal": False})
    box("IfcBuildingElementProxy", "Sonstiges", (0, 4, 0))
    path = tmp_path / "haus.ifc"
    model.write(str(path))
    return path


def test_inventory_reads_is_external_from_own_and_type_psets(tmp_path):
    model = hull_check.open_model(_house(tmp_path))
    products = hull_check.converter.shape_products(model, hull_check.converter.EXCLUDED_CLASSES)
    rows = {row.name: row for row in hull_check.inventory(products)}
    assert rows["Aussenwand"].external is True
    assert rows["Innenwand"].external is False  # from the type's property set
    assert rows["Sonstiges"].external is None
    assert rows["Aussenwand"].storey == "IfcBuildingStorey EG"
    assert rows["Aussenwand"].ifc_class == "IfcWall" and len(rows["Aussenwand"].guid) == 22


def test_check_file_compares_selection_with_flags(tmp_path, monkeypatch):
    path = _house(tmp_path)

    def fake(model, threads, products, report=None, progress=None):
        by_name = {product.Name: product.id() for product in products}
        report("note", "fake")
        return envelope.Selection(
            keep={by_name["Aussenwand"], by_name["Sonstiges"]}, total=3, inside=1, unknown=1, flagged=1,
            exposure={by_name["Aussenwand"]: 0.01, by_name["Innenwand"]: 0.0},  # proxy: no coarse geometry
        )

    monkeypatch.setattr(envelope, "EXPOSURE", 0.05)
    report, model, rows = hull_check.check_file(path, 1, fake, log=lambda text: None)
    assert (report["products"], report["kept"], report["dropped"], report["unknown"]) == (3, 2, 1, 1)
    assert report["confusion"] == {
        "external_true": {"kept": 1, "dropped": 0}, "external_false": {"kept": 0, "dropped": 1},
        "external_unknown": {"kept": 1, "dropped": 0},
    }
    assert report["classes"]["IfcWall"] == {"total": 2, "kept": 1, "dropped": 1, "external_true": 1,
                                            "external_false": 1, "unknown": 0}
    assert report["classes"]["IfcBuildingElementProxy"]["unknown"] == 1
    assert [row["name"] for row in report["external_not_exposed"]] == ["Aussenwand"]
    assert report["internal_exposed"] == []
    assert [row["name"] for row in report["dropped_products"]] == ["Innenwand"]
    assert [row["name"] for row in report["unknown_products"]] == ["Sonstiges"]
    assert sum(bucket["count"] for bucket in report["exposure_histogram"]) == 2
    sweep = {entry["threshold"]: entry for entry in report["threshold_sweep"]}
    assert sweep[0.005]["kept_by_exposure"] == 1 and sweep[0.05]["kept_by_exposure"] == 0
    assert sweep[0.05]["external_below"] == 1
    assert report["notes"] == ["note: fake"] and report["parameters"]["EXPOSURE"] == 0.05

    hull_check.write_markdown(report, tmp_path / "haus.md")
    text = (tmp_path / "haus.md").read_text(encoding="utf-8")
    inner = next(row for row in rows if row.name == "Innenwand")
    assert inner.guid in text and "| IfcWall | 1 | 0 |" in text  # dropped per class
    assert "| True | 1 | 0 |" in text


def test_rasterizer_and_png_writer(tmp_path):
    # One upright square facing south (towards -Y), 2 x 2 m, red.
    points = numpy.array([[0, 0, 0], [2, 0, 0], [2, 0, 2], [0, 0, 2]], float)
    triangles = numpy.array([[0, 1, 2], [0, 2, 3]])
    mesh = hull_check.Mesh.join([(points, triangles, (200, 0, 0))])
    matrix = hull_check.view_matrix(*hull_check.VIEWS["south"])
    centre, scale = hull_check.frame([mesh], matrix, (100, 80))
    image = hull_check.rasterize(mesh, matrix, centre, scale, (100, 80))
    red = (image[:, :, 0] > 50) & (image[:, :, 1] < 50)
    assert image.shape == (80, 100, 3) and 0.5 < red.mean() < 0.95  # fills most of the image
    assert not red[0].any() and not red[:, 0].any()  # a margin around it
    # Seen from above the square is a line: a few pixels, not nothing.
    top = hull_check.rasterize(mesh, hull_check.view_matrix(*hull_check.VIEWS["top"]), centre, scale, (100, 80))
    assert 0 < ((top[:, :, 0] > 50) & (top[:, :, 1] < 50)).sum() < 500

    hull_check.write_png(image, tmp_path / "square.png")
    data = (tmp_path / "square.png").read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", data[16:24]) == (100, 80)
    start = data.index(b"IDAT") + 4
    length = struct.unpack(">I", data[start - 8:start - 4])[0]
    raw = zlib.decompress(data[start:start + length])
    assert len(raw) == 80 * (1 + 100 * 3)


def test_end_to_end_with_real_selection_and_renders(tmp_path):
    path = _house(tmp_path)
    out = tmp_path / "out"
    assert hull_check.main([str(path), "--out-dir", str(out), "--threads", "1", "--render"]) == 0
    report = json.loads((out / "haus.json").read_text(encoding="utf-8"))
    # Three free-standing boxes: everything sees outside air. With no closed hull the algorithm may
    # fall back to the property sets and drop the wall marked IsExternal = False, nothing else.
    assert report["products"] == 3 and report["classes"]["IfcWall"]["external_true"] == 1
    assert {row["name"] for row in report["dropped_products"]} <= {"Innenwand"}
    assert report["confusion"]["external_true"] == {"kept": 1, "dropped": 0}
    assert set(report["classes"]) == {"IfcWall", "IfcBuildingElementProxy"}
    assert (out / "haus.md").is_file()
    assert len(report["renders"]) == 2 * len(hull_check.VIEWS)
    kept = out / "haus.iso-sw.kept.png"
    assert kept.is_file() and kept.stat().st_size > 1000
    assert (out / "haus.iso-sw.dropped.png").is_file()


def test_fake_select_keeps_everything(tmp_path):
    model = hull_check.open_model(_house(tmp_path))
    products = hull_check.converter.shape_products(model, hull_check.converter.EXCLUDED_CLASSES)
    selection = hull_check.fake_select(model, 1, products)
    assert selection.keep == {product.id() for product in products} and selection.total == 3


def test_measure_records_sizes_and_times(tmp_path, monkeypatch):
    path = _house(tmp_path)
    calls = []

    def fake(model, threads, products, report=None, progress=None):
        calls.append(len(products))
        return envelope.Selection(keep={products[0].id()}, total=len(products), inside=len(products) - 1)

    monkeypatch.setattr(envelope, "select", fake)
    results = hull_check.measure(path, tmp_path, 1, ["obj"], keep_output=True, log=lambda text: None)
    entry = results["obj"]
    assert entry["full"]["elements"] == 3 and entry["hull"]["elements"] == 1 and entry["hull"]["inside"] == 2
    assert 0 < entry["hull"]["bytes"] < entry["full"]["bytes"] and 0 < entry["size_ratio"] < 1
    assert Path(entry["full"]["output"]).is_file() and Path(entry["hull"]["output"]).is_file()
    assert calls == [3]


@pytest.mark.parametrize("name", ["top", "south", "iso-sw"])
def test_view_matrices_are_rotations(name):
    matrix = hull_check.view_matrix(*hull_check.VIEWS[name])
    assert numpy.allclose(matrix @ matrix.T, numpy.eye(3)) and numpy.linalg.det(matrix) == pytest.approx(1.0)
    # The image's up (second row) never points downwards in the world.
    assert matrix[1, 2] >= 0
