"""IFC2x2 and the IFC4x4 draft are read as the closest schema IfcOpenShell knows (schema_bridge)."""

import re

import ifcopenshell
import pytest

from ifc_converter import schema_bridge
from ifc_converter.converter import convert


def _with_header(wall_ifc, tmp_path, schema: str, rename: dict[str, str] | None = None, extra: str = ""):
    """wall_ifc declared as ``schema``, with entity names renamed and extra lines before ENDSEC."""
    text = wall_ifc.read_text(encoding="utf-8")
    text, found = re.subn(r"FILE_SCHEMA\s*\(\s*\(\s*'[A-Z0-9_]+'\s*\)\s*\)", f"FILE_SCHEMA(('{schema}'))", text, count=1)
    assert found == 1
    for old, new in (rename or {}).items():
        text = re.sub(rf"^(#\d+\s*=\s*){old}\(", rf"\g<1>{new}(", text, flags=re.M)
    if extra:
        text = text.replace("\nENDSEC;\nEND-ISO-10303-21;", f"\n{extra}\nENDSEC;\nEND-ISO-10303-21;")
        assert extra in text
    path = tmp_path / f"wall-{schema.lower()}.ifc"
    path.write_text(text, encoding="utf-8")
    return path


def test_declared_schema_and_bridges(wall_ifc, tmp_path):
    assert schema_bridge.declared_schema(wall_ifc) == "IFC4"
    assert schema_bridge.bridge_for(wall_ifc) is None
    assert schema_bridge.declared_schema(tmp_path / "missing.ifc") is None
    (tmp_path / "junk.ifc").write_bytes(b"not a step file")
    assert schema_bridge.declared_schema(tmp_path / "junk.ifc") is None
    old = _with_header(wall_ifc, tmp_path, "IFC2X2_FINAL")
    assert schema_bridge.bridge_for(old).target == "IFC2X3"
    draft = _with_header(wall_ifc, tmp_path, "IFC4X4")
    assert schema_bridge.bridge_for(draft).target == "IFC4X3_ADD2"


def test_an_ifc2x2_file_is_read_as_ifc2x3(buildings_ifc, tmp_path):
    # buildings_ifc is IFC2X3 (two walls and a roof slab): declared as IFC2X2 it reads the same way.
    old = _with_header(buildings_ifc, tmp_path, "IFC2X2_FINAL")
    with pytest.raises(ifcopenshell.SchemaError):
        ifcopenshell.open(str(old))  # IfcOpenShell itself cannot
    notes = []
    result = convert(old, tmp_path / "old.glb", "glb", threads=2,
                     status=lambda phase, text: notes.append(text) if phase == "note" else None)
    assert result.elements == 3 and result.skipped == 0
    assert any(note.startswith("IFC2x2 (2003) wird als IFC2x3 gelesen") and "Maße und Lage bleiben" in note
               for note in notes)
    assert not list(tmp_path.glob("ifc-converter-bridge-*"))  # the copy lives in the temp folder, briefly


def test_the_ifc4x4_draft_entities_get_their_ifc4_3_counterparts(wall_ifc, tmp_path):
    # The wall becomes an "arch element" of the draft, plus the dataset records the draft adds.
    draft = _with_header(
        wall_ifc, tmp_path, "IFC4X4", rename={"IFCWALL": "IFCARCHELEMENT"},
        extra="#9001=IFCDATASETINFORMATION('x',$,$,$,$,$,$,$,$,$,$,$,$,$,$,$,$,$);\n"
              "#9002=IFCRELASSOCIATESDATASET('0DataSet0000000000000',$,$,$,(),#9001);",
    )
    copy = schema_bridge.bridged_copy(draft, schema_bridge.bridge_for(draft))
    try:
        text = copy.path.read_text(encoding="utf-8")
        assert "FILE_SCHEMA(('IFC4X3_ADD2'))" in text and "IFCARCHELEMENT(" not in text
        assert "IFCBUILDINGELEMENTPROXY(" in text and "IFCDATASETINFORMATION" not in text
        assert (copy.renamed, copy.dropped) == (1, 2)
        assert "1 Entitäten umbenannt, 2 ausgelassen" in copy.note
    finally:
        copy.remove()
    assert not copy.path.exists()

    notes = []
    result = convert(draft, tmp_path / "draft.glb", "glb", threads=2,
                     status=lambda phase, text: notes.append(text) if phase == "note" else None)
    assert result.elements == 1 and result.skipped == 0
    assert any("IFC4x4 ist ein unveröffentlichter Entwurf" in note for note in notes)
    assert draft.read_text(encoding="utf-8").count("IFCARCHELEMENT(") == 1  # the original is untouched


def test_a_bridged_file_keeps_its_dimensions(buildings_ifc, tmp_path):
    def extent(obj):
        points = [list(map(float, line.split()[1:4])) for line in obj.read_text().splitlines() if line.startswith("v ")]
        return [round(max(p[i] for p in points) - min(p[i] for p in points), 6) for i in range(3)]

    convert(buildings_ifc, tmp_path / "plain.obj", "obj", threads=2)
    convert(_with_header(buildings_ifc, tmp_path, "IFC2X2_FINAL"), tmp_path / "old.obj", "obj", threads=2)
    assert extent(tmp_path / "plain.obj") == [25.0, 5.0, 3.2]
    assert extent(tmp_path / "old.obj") == extent(tmp_path / "plain.obj")


def test_unknown_schemas_still_fail_clearly(wall_ifc, tmp_path):
    with pytest.raises(ValueError, match="IFC-Version wird nicht unterstützt.*IFC5.*IFC2x2, IFC4x4"):
        convert(_with_header(wall_ifc, tmp_path, "IFC5"), tmp_path / "x.glb", "glb")
