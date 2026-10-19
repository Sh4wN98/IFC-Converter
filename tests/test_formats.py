"""The output formats written by IfcOpenShell's serializers (serializers.py) and the .ifczip input."""

import re
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy
import pytest

from ifc_converter import serializers
from ifc_converter.converter import FORMATS, INPUT_SUFFIXES, convert

WALL = numpy.array([5.0, 0.2, 3.0])  # the wall_ifc extent in metres


def _extent(points) -> numpy.ndarray:
    points = numpy.asarray(points, dtype=float)
    return points.max(axis=0) - points.min(axis=0)


def test_the_offered_formats_and_input_suffixes():
    assert FORMATS == ("glb", "obj", "3dm", "dae")
    assert INPUT_SUFFIXES == (".ifc", ".ifczip")
    assert set(serializers.SERIALIZERS) == {"glb", "obj", "stp", "dae"}
    assert serializers.output_files(Path("x.obj"), "obj") == [Path("x.obj"), Path("x.mtl")]
    assert serializers.output_files(Path("x.glb"), "glb", temp=True)[1:] == [
        Path("x.glb.indices.tmp"), Path("x.glb.vertices.tmp")]
    assert serializers.output_files(Path("x.3dm"), "3dm") == [Path("x.3dm")]
    assert serializers.requires_opencascade("stp") and not serializers.requires_opencascade("dae")
    assert "stp" not in FORMATS  # unplaced B-rep, see serializers.py


def test_collada_holds_the_wall_in_metres_z_up(wall_ifc, tmp_path):
    result = convert(wall_ifc, tmp_path / "wall.dae", "dae", threads=2)
    assert result.elements == 1
    root = ET.parse(tmp_path / "wall.dae").getroot()
    ns = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
    assert [(u.get("name"), u.get("meter")) for u in root.findall(".//c:unit", ns)] == [("METER", "1")]
    assert [u.text for u in root.findall(".//c:up_axis", ns)] == ["Z_UP"]
    assert len(root.findall(".//c:geometry", ns)) == 1
    coordinates = [float(v) for f in root.findall(".//c:float_array", ns) if "position" in f.get("id", "")
                   for v in f.text.split()]
    assert numpy.allclose(_extent(numpy.array(coordinates).reshape(-1, 3)), WALL, atol=1e-6)


def test_an_ifczip_converts_like_the_ifc_inside(wall_ifc, tmp_path):
    zipped = tmp_path / "wall.ifczip"
    with zipfile.ZipFile(zipped, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(wall_ifc, "wall.ifc")
    result = convert(zipped, tmp_path / "wall.glb", "glb", threads=2)
    assert result.elements == 1 and result.output == tmp_path / "wall.glb"
    data = (tmp_path / "wall.glb").read_bytes()
    assert data[:4] == b"glTF"
    length = struct.unpack("<I", data[12:16])[0]
    assert b'"nodes"' in data[20:20 + length]


def test_ifcxml_is_refused_with_a_clear_message(tmp_path):
    path = tmp_path / "haus.ifcxml"
    path.write_text("<ifcXML/>")
    with pytest.raises(ValueError, match="ifcXML-Dateien kann IfcOpenShell nicht lesen"):
        convert(path, tmp_path / "haus.glb", "glb")


def test_the_cli_knows_the_new_formats(wall_ifc, tmp_path):
    from ifc_converter.cli import main

    assert main([str(wall_ifc), "-f", "dae", "-d", str(tmp_path), "-j", "2"]) == 0
    assert (tmp_path / "wall.dae").stat().st_size > 1000
