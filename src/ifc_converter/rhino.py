from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.util.element as element_util
import rhino3dm

from ifc_converter.converter import ProgressCallback

NO_STOREY = "Ohne Geschoss"
FILE_VERSION = 7
MAX_STRING_LENGTH = 1000
# Share of the progress range used by the geometry iterator; the rest covers writing the file.
ITERATOR_SHARE = 90

Color = tuple[int, int, int, int]


@dataclass
class _Entry:
    storey: ifcopenshell.entity_instance | None
    ifc_class: str
    mesh: rhino3dm.Mesh
    attributes: rhino3dm.ObjectAttributes
    color: Color
    material: tuple[str, Color, float]


def write_3dm(
    model: ifcopenshell.file,
    output_path: Path,
    threads: int,
    progress: ProgressCallback | None = None,
) -> int:
    """Write every element with geometry as a Rhino mesh, layered by storey and IFC class."""
    entries = list(_iter_entries(model, threads, progress))

    rhino = rhino3dm.File3dm()
    rhino.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters
    layers = _LayerTable(rhino)
    materials: dict[tuple[str, Color, float], int] = {}

    for entry in sorted(entries, key=lambda e: _storey_sort_key(e.storey)):
        entry.attributes.LayerIndex = layers.get(entry.storey, entry.ifc_class, entry.color)
        entry.attributes.MaterialIndex = _material_index(rhino, materials, entry.material)
        entry.attributes.MaterialSource = rhino3dm.ObjectMaterialSource.MaterialFromObject
        rhino.Objects.AddMesh(entry.mesh, entry.attributes)

    if not rhino.Write(str(output_path), FILE_VERSION):
        raise OSError(f"Could not write Rhino file: {output_path}")
    return len(entries)


def _iter_entries(model: ifcopenshell.file, threads: int, progress: ProgressCallback | None):
    settings = geom.settings()
    settings.set("use-world-coords", True)
    # Unwelded vertices keep hard edges between faces sharp when Rhino shades the mesh.
    settings.set("weld-vertices", False)
    settings.set("use-material-names", True)
    settings.set("no-normals", True)

    # Opening volumes would show up as solid boxes over every window and door.
    iterator = geom.iterator(settings, model, threads, exclude=["IfcOpeningElement"])
    if not iterator.initialize():
        return
    while True:
        shape = iterator.get()
        entry = _entry(model, shape)
        if entry:
            yield entry
        if progress:
            progress(iterator.progress() * ITERATOR_SHARE // 100)
        if not iterator.next():
            break


def _entry(model: ifcopenshell.file, shape) -> _Entry | None:
    mesh = _mesh(shape.geometry)
    if mesh is None:
        return None

    element = model.by_id(shape.id)
    name, color, transparency = _material(shape.geometry)
    attributes = rhino3dm.ObjectAttributes()
    attributes.Name = element.Name or element.GlobalId
    attributes.ObjectColor = color
    attributes.ColorSource = rhino3dm.ObjectColorSource.ColorFromObject
    for key, value in _user_strings(element).items():
        attributes.SetUserString(key, value)

    return _Entry(
        storey=_storey(element),
        ifc_class=element.is_a(),
        mesh=mesh,
        attributes=attributes,
        color=color,
        material=(name, color, transparency),
    )


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
            parent = self._storey_layer(storey_key, storey)
            # The class layer takes the colour of its first element.
            self._classes[key] = self._add(ifc_class, color[:3] + (255,), parent.Id)
        return self._classes[key]

    def _storey_layer(self, key: int | None, storey: ifcopenshell.entity_instance | None) -> rhino3dm.Layer:
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
