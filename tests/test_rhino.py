import pytest
import rhino3dm

from ifc_converter import convert
from ifc_converter.cli import main


def _read(path):
    rhino = rhino3dm.File3dm.Read(str(path))
    assert rhino is not None
    return rhino


def _layer_paths(rhino):
    return {layer.Index: layer.FullPath for layer in rhino.Layers}


def test_wall_is_written_as_mesh(wall_ifc):
    progress = []
    result = convert(wall_ifc, fmt="3dm", progress=progress.append)

    assert result.output == wall_ifc.with_suffix(".3dm")
    assert result.elements == 1
    assert progress[-1] == 100
    assert progress == sorted(progress)

    rhino = _read(result.output)
    assert rhino.Settings.ModelUnitSystem == rhino3dm.UnitSystem.Meters
    assert len(rhino.Objects) == 1

    obj = rhino.Objects[0]
    mesh = obj.Geometry
    assert isinstance(mesh, rhino3dm.Mesh)
    assert len(mesh.Normals) == len(mesh.Vertices) > 0
    box = mesh.GetBoundingBox()
    size = (box.Max.X - box.Min.X, box.Max.Y - box.Min.Y, box.Max.Z - box.Min.Z)
    assert size == pytest.approx((5, 0.2, 3))


def test_wall_without_storey_goes_to_fallback_layer(wall_ifc):
    rhino = _read(convert(wall_ifc, fmt="3dm").output)
    obj = rhino.Objects[0]
    assert _layer_paths(rhino)[obj.Attributes.LayerIndex] == "Ohne Geschoss::IfcWall"


def test_storey_and_class_layers(storey_ifc):
    result = convert(storey_ifc, fmt="3dm")
    assert result.elements == 2

    rhino = _read(result.output)
    paths = set(_layer_paths(rhino).values())
    assert {"EG", "EG::IfcWall", "EG::IfcSlab"} <= paths

    layers = {layer.FullPath: layer for layer in rhino.Layers}
    assert layers["EG::IfcWall"].ParentLayerId == layers["EG"].Id
    assert layers["EG::IfcWall"].Color[:3] == (255, 0, 0)


def test_object_attributes(storey_ifc):
    rhino = _read(convert(storey_ifc, fmt="3dm").output)
    objects = {obj.Attributes.GetUserString("IfcClass"): obj.Attributes for obj in rhino.Objects}

    wall = objects["IfcWall"]
    assert wall.Name == "Wall"
    assert wall.GetUserString("IfcName") == "Wall"
    assert len(wall.GetUserString("IfcGlobalId")) == 22
    assert wall.GetUserString("Pset_WallCommon.IsExternal") == "True"
    assert wall.GetUserString("Pset_WallCommon.Reference") == "AW-01"
    assert wall.ColorSource == rhino3dm.ObjectColorSource.ColorFromObject
    assert wall.ObjectColor[:3] == (255, 0, 0)
    assert rhino.Materials[wall.MaterialIndex].DiffuseColor[:3] == (255, 0, 0)

    slab = objects["IfcSlab"]
    assert slab.Name == slab.GetUserString("IfcGlobalId")


def test_progress_abort_propagates(wall_ifc):
    def abort(percent):
        raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        convert(wall_ifc, fmt="3dm", progress=abort)


def test_cli_writes_3dm(wall_ifc, tmp_path, capsys):
    out_dir = tmp_path / "converted"
    assert main([str(wall_ifc), "-f", "3dm", "-d", str(out_dir)]) == 0
    assert _read(out_dir / "wall.3dm") is not None
    assert "1 elements" in capsys.readouterr().out
