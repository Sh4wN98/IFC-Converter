import pytest
import rhino3dm

from ifc_converter import convert, rhino
from ifc_converter.cli import main


def _read(path):
    rhino = rhino3dm.File3dm.Read(str(path))
    assert rhino is not None
    return rhino


def _layer_paths(rhino):
    return {layer.Index: layer.FullPath for layer in rhino.Layers}


def _size(geometry):
    box = geometry.GetBoundingBox()
    return (box.Max.X - box.Min.X, box.Max.Y - box.Min.Y, box.Max.Z - box.Min.Z)


def test_wall_is_written_as_mesh(wall_ifc):
    progress = []
    result = convert(wall_ifc, fmt="3dm", progress=progress.append, geometry="mesh")

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
    assert _size(mesh) == pytest.approx((5, 0.2, 3))


def test_wall_is_a_closed_polysurface(wall_ifc):
    progress = []
    result = convert(wall_ifc, fmt="3dm", progress=progress.append)
    assert result.elements == 1
    assert progress[-1] == 100 and progress == sorted(progress)

    brep = _read(result.output).Objects[0].Geometry
    assert isinstance(brep, rhino3dm.Brep)
    assert brep.IsValid and brep.IsSolid
    assert len(brep.Faces) == 6
    assert _size(brep) == pytest.approx((5, 0.2, 3))


def test_opening_becomes_a_hole_in_the_polysurface(opening_ifc):
    rhino_file = _read(convert(opening_ifc, fmt="3dm").output)
    wall = next(o.Geometry for o in rhino_file.Objects if o.Attributes.GetUserString("IfcClass") == "IfcWall")
    assert isinstance(wall, rhino3dm.Brep)
    assert wall.IsValid and wall.IsSolid
    # front and back face with the hole, four outer sides, four reveals
    assert len(wall.Faces) == 10
    assert sorted(len(face.Loops) for face in wall.Faces) == [1] * 8 + [2] * 2


def test_detailed_elements_fall_back_to_meshes(storey_ifc, monkeypatch):
    monkeypatch.setattr(rhino, "MAX_BREP_FACES", 12)  # wall and slab have 12 triangles each
    rhino_file = _read(convert(storey_ifc, fmt="3dm").output)
    assert {type(o.Geometry) for o in rhino_file.Objects} == {rhino3dm.Brep}

    monkeypatch.setattr(rhino, "MAX_BREP_FACES", 11)
    progress = []
    result = convert(storey_ifc, fmt="3dm", progress=progress.append)
    assert result.elements == 2
    assert progress[-1] == 100 and progress == sorted(progress)
    rhino_file = _read(result.output)
    objects = {o.Attributes.GetUserString("IfcClass"): o for o in rhino_file.Objects}
    assert {type(o.Geometry) for o in objects.values()} == {rhino3dm.Mesh}
    # the fallback keeps layer, colour and user text
    wall = objects["IfcWall"]
    assert _layer_paths(rhino_file)[wall.Attributes.LayerIndex] == "EG::IfcWall"
    assert wall.Attributes.ObjectColor[:3] == (255, 0, 0)
    assert wall.Attributes.GetUserString("Pset_WallCommon.Reference") == "AW-01"


def test_invalid_polysurface_falls_back_to_mesh(wall_ifc, monkeypatch):
    monkeypatch.setattr(rhino, "planar_polysurface", lambda *args: None)
    rhino_file = _read(convert(wall_ifc, fmt="3dm").output)
    assert len(rhino_file.Objects) == 1
    assert isinstance(rhino_file.Objects[0].Geometry, rhino3dm.Mesh)


def test_invalid_geometry_is_rejected(wall_ifc):
    with pytest.raises(ValueError):
        convert(wall_ifc, fmt="3dm", geometry="nurbs")


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


@pytest.mark.parametrize("geometry", ["brep", "mesh"])
def test_progress_abort_propagates(wall_ifc, geometry):
    def abort(percent):
        if percent > 0:
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        convert(wall_ifc, fmt="3dm", progress=abort, geometry=geometry)


def test_cli_writes_3dm(wall_ifc, tmp_path, capsys):
    out_dir = tmp_path / "converted"
    assert main([str(wall_ifc), "-f", "3dm", "-d", str(out_dir)]) == 0
    assert _read(out_dir / "wall.3dm") is not None
    assert "1 elements" in capsys.readouterr().out


def test_cli_geometry_flag(wall_ifc, tmp_path):
    target = tmp_path / "wall.3dm"
    assert main([str(wall_ifc), "-f", "3dm", "-o", str(target), "--geometry", "mesh"]) == 0
    assert isinstance(_read(target).Objects[0].Geometry, rhino3dm.Mesh)
    assert main([str(wall_ifc), "-f", "3dm", "-o", str(target)]) == 0
    assert isinstance(_read(target).Objects[0].Geometry, rhino3dm.Brep)
    with pytest.raises(SystemExit):
        main([str(wall_ifc), "--geometry", "nurbs"])
