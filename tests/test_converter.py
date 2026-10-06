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
