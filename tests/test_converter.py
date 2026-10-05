import pytest

from ifc_converter import convert
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
