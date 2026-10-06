from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.util.element as element_util
import rhino3dm

from ifc_converter.converter import ProgressCallback, iter_shapes
from ifc_converter.polysurface import planar_polysurface

NO_STOREY = "Ohne Geschoss"
FILE_VERSION = 7
MAX_STRING_LENGTH = 1000
# Share of the progress range used by the geometry iterator; the rest covers writing the file.
ITERATOR_SHARE = 90
# Elements with more triangles than this are mostly tessellated organic shapes (sanitary objects,
# lamps, plants). As polysurfaces they would cost ~1.7 kB per face without any benefit: they stay meshes.
MAX_BREP_FACES = 1000

Color = tuple[int, int, int, int]

# Opening volumes would show up as solid boxes over every window and door. Spaces stay: they get
# their own layers in Rhino, where they are easy to switch off.
EXCLUDED_CLASSES = ["IfcOpeningElement"]


def write_3dm(
    model: ifcopenshell.file,
    output_path: Path,
    threads: int,
    progress: ProgressCallback | None = None,
    geometry: str = "brep",
) -> int:
    """Write every element with geometry, layered by storey and IFC class.

    With ``geometry="brep"`` elements become joined planar polysurfaces; elements with more than
    MAX_BREP_FACES triangles (tessellated organic shapes) or without a valid Brep stay meshes.
    With ``geometry="mesh"`` every element is a mesh.
    """
    writer = _Writer(model)
    for shape in iter_shapes(model, _settings(), threads, EXCLUDED_CLASSES, progress, ITERATOR_SHARE):
        triangles = shape.geometry.faces
        if not shape.geometry.verts or not triangles:
            continue
        brep = None
        if geometry == "brep" and len(triangles) <= 3 * MAX_BREP_FACES:
            brep = _brep(shape.geometry)
        writer.add(shape, _mesh(shape.geometry) if brep is None else brep)

    if not writer.rhino.Write(str(output_path), FILE_VERSION):
        raise OSError(f"Could not write Rhino file: {output_path}")
    return writer.elements


class _Writer:
    """Adds objects to a Rhino file with the layers, colours, materials and user text of their element."""

    def __init__(self, model: ifcopenshell.file):
        self.model = model
        self.rhino = rhino3dm.File3dm()
        self.rhino.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters
        self.layers = _LayerTable(self.rhino)
        # Storey layers are created up front so the layer panel lists them by elevation.
        for storey in sorted(model.by_type("IfcBuildingStorey"), key=_storey_sort_key):
            self.layers.storey_layer(storey)
        self.materials: dict[tuple[str, Color, float], int] = {}
        self.elements = 0

    def add(self, shape, geometry: rhino3dm.Mesh | rhino3dm.Brep | None) -> None:
        # Each object goes into the Rhino file right away, so only one copy of the geometry is kept.
        if geometry is None:
            return
        element = self.model.by_id(shape.id)
        name, color, transparency = _material(shape.geometry)
        attributes = _attributes(element, color)
        attributes.LayerIndex = self.layers.get(_storey(element), element.is_a(), color)
        attributes.MaterialIndex = _material_index(self.rhino, self.materials, (name, color, transparency))
        attributes.MaterialSource = rhino3dm.ObjectMaterialSource.MaterialFromObject
        if isinstance(geometry, rhino3dm.Brep):
            self.rhino.Objects.AddBrep(geometry, attributes)
        else:
            self.rhino.Objects.AddMesh(geometry, attributes)
        self.elements += 1


def _settings() -> geom.settings:
    settings = geom.settings()
    settings.set("use-world-coords", True)
    # Unwelded vertices keep hard edges between faces sharp when Rhino shades the mesh.
    settings.set("weld-vertices", False)
    settings.set("use-material-names", True)
    settings.set("no-normals", True)
    return settings


def _brep(geometry) -> rhino3dm.Brep | None:
    """The element as a joined polysurface: coplanar triangles become one face (with holes)."""
    indices = geometry.faces
    triangles = [[indices[i:i + 3]] for i in range(0, len(indices), 3)]
    return planar_polysurface(geometry.verts, triangles, geometry.item_ids)


def _attributes(element: ifcopenshell.entity_instance, color: Color) -> rhino3dm.ObjectAttributes:
    attributes = rhino3dm.ObjectAttributes()
    attributes.Name = element.Name or element.GlobalId
    attributes.ObjectColor = color
    attributes.ColorSource = rhino3dm.ObjectColorSource.ColorFromObject
    for key, value in _user_strings(element).items():
        attributes.SetUserString(key, value)
    return attributes


def _mesh(geometry) -> rhino3dm.Mesh | None:
    verts, faces = geometry.verts, geometry.faces
    if not verts or not faces:
        return None

    mesh = rhino3dm.Mesh()
    # Bound methods and zip over one iterator avoid per-vertex attribute lookups and indexing.
    add_vertex, add_face = mesh.Vertices.Add, mesh.Faces.AddFace
    coords = iter(verts)
    for x, y, z in zip(coords, coords, coords):
        add_vertex(x, y, z)
    indices = iter(faces)
    for a, b, c in zip(indices, indices, indices):
        add_face(a, b, c)
    # Vertices are only shared within a face, so the computed normals keep edges sharp.
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


def _material(geometry) -> tuple[str, Color, float]:
    """Name, colour and transparency (0-1) of the material covering most faces."""
    if not geometry.materials:
        return "Default", (180, 180, 180, 255), 0.0
    ids = Counter(i for i in geometry.material_ids if i >= 0)
    material = geometry.materials[ids.most_common(1)[0][0] if ids else 0]

    diffuse = material.diffuse
    transparency = material.transparency
    if transparency is None or math.isnan(transparency):
        transparency = 0.0
    transparency = min(max(transparency, 0.0), 1.0)
    color = (
        _channel(diffuse.r()),
        _channel(diffuse.g()),
        _channel(diffuse.b()),
        _channel(1.0 - transparency),
    )
    return material.name or "Default", color, transparency


def _channel(value: float) -> int:
    return round(min(max(value, 0.0), 1.0) * 255)


def _material_index(rhino: rhino3dm.File3dm, cache: dict, key: tuple[str, Color, float]) -> int:
    if key not in cache:
        name, color, transparency = key
        material = rhino3dm.Material()
        material.Name = _clean_name(name, "Material")
        material.DiffuseColor = color[:3] + (255,)
        material.Transparency = transparency
        cache[key] = rhino.Materials.Add(material)
    return cache[key]


def _storey(element: ifcopenshell.entity_instance) -> ifcopenshell.entity_instance | None:
    parent = element_util.get_parent(element)
    while parent is not None:
        if parent.is_a("IfcBuildingStorey"):
            return parent
        parent = element_util.get_parent(parent)
    return None


def _storey_sort_key(storey: ifcopenshell.entity_instance | None) -> tuple:
    if storey is None:
        return (1, 0.0, "")
    return (0, storey.Elevation or 0.0, storey.Name or "")


def _user_strings(element: ifcopenshell.entity_instance) -> dict[str, str]:
    strings = {
        "IfcGlobalId": element.GlobalId,
        "IfcClass": element.is_a(),
        "IfcName": element.Name or "",
    }
    try:
        psets = element_util.get_psets(element)
    except Exception:
        psets = {}
    for pset, properties in psets.items():
        for prop, value in properties.items():
            if prop == "id" or not isinstance(value, (str, int, float, bool)):
                continue
            strings[f"{pset}.{prop}"] = str(value)[:MAX_STRING_LENGTH]
    return strings


class _LayerTable:
    """Creates parent layers per storey with child layers per IFC class on demand."""

    def __init__(self, rhino: rhino3dm.File3dm):
        self._rhino = rhino
        self._storeys: dict[int | None, rhino3dm.Layer] = {}
        self._classes: dict[tuple[int | None, str], int] = {}
        self._names: set[str] = set()

    def get(self, storey: ifcopenshell.entity_instance | None, ifc_class: str, color: Color) -> int:
        storey_key = storey.id() if storey is not None else None
        key = (storey_key, ifc_class)
        if key not in self._classes:
            parent = self.storey_layer(storey)
            # The class layer takes the colour of its first element.
            self._classes[key] = self._add(ifc_class, color[:3] + (255,), parent.Id)
        return self._classes[key]

    def storey_layer(self, storey: ifcopenshell.entity_instance | None) -> rhino3dm.Layer:
        key = storey.id() if storey is not None else None
        if key not in self._storeys:
            name = _clean_name(storey.Name, f"Geschoss #{key}") if storey is not None else NO_STOREY
            name = self._unique(name)
            index = self._add(name, (0, 0, 0, 255), None)
            self._storeys[key] = self._rhino.Layers.FindIndex(index)
        return self._storeys[key]

    def _unique(self, name: str) -> str:
        candidate, n = name, 2
        while candidate in self._names:
            candidate, n = f"{name} ({n})", n + 1
        self._names.add(candidate)
        return candidate

    def _add(self, name: str, color: Color, parent_id) -> int:
        layer = rhino3dm.Layer()
        layer.Name = name
        layer.Color = color
        if parent_id is not None:
            layer.ParentLayerId = parent_id
        return self._rhino.Layers.Add(layer)


def _clean_name(name: str | None, fallback: str) -> str:
    """Make a string usable as a Rhino layer/material name."""
    name = re.sub(r"[\x00-\x1f\x7f]", " ", name or "").replace("::", ":")
    name = name.strip().lstrip("([{}])").strip()
    return name[:MAX_STRING_LENGTH] or fallback
