"""Independent verification of placement and dimensions of every element in every output format.

Reference: IfcOpenShell's OpenCASCADE kernel in world coordinates with its default tessellation
(``use-world-coords``, no converter code involved in the geometry), per element: bounding box,
area-weighted centroid of the triangles, surface area and (closed shells) the signed volume by the
divergence theorem. The converter's outputs are read with independent readers (rhino3dm for .3dm
with block instances placed; a small OBJ parser; the GLB JSON chunk and accessors with the node
matrices applied; the DAE XML with node matrices) and every element is matched by its GlobalId
(Rhino user text ``IfcGlobalId``; node/group names ``product-<uuid>-body`` elsewhere).

    python tools/night_accuracy.py duplex.ifc --out-dir out --report rows.md

Per model x format the report lists: elements compared, the largest bounding-box corner and
centroid deviation (mm), the largest area and volume ratio deviation, inside-out shells, elements
missing in the output and extra ones. Extra checks: openings cut (gross vs net volume), mirrored
type geometry, chord error of round extrusions, Rhino document settings/layers/user text, OBJ
material colours against the IFC styles, GLB accessor consistency, DAE unit and up axis, and the
hull option (kept elements identical to the full run).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accuracy  # noqa: E402  (readers' helpers: brep faces, GLB node matrices, guid compression)

MODES = {
    "3dm-brep": ("3dm", "brep", False),
    "3dm-mesh": ("3dm", "mesh", False),
    "3dm-mesh-blocks": ("3dm", "mesh", True),
    "3dm-brep-blocks": ("3dm", "brep", True),
    "glb": ("glb", "brep", False),
    "obj": ("obj", "brep", False),
    "dae": ("dae", "brep", False),
}
DEFAULT_MODES = ["3dm-brep", "3dm-mesh", "3dm-mesh-blocks", "glb", "obj", "dae"]
EXCLUDED = ("IfcOpeningElement", "IfcGrid", "IfcAlignmentHorizontal", "IfcAlignmentVertical",
            "IfcAlignmentCant", "IfcAlignmentSegment")
# Spaces are written to .3dm only (own layers); the other formats leave them out by design.
SPACE_FORMATS = ("3dm",)
POSITION_TOLERANCE_MM = 1.0
RATIO_TOLERANCE = 0.005
_GUID_IN_NAME = re.compile(r"product-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_STYLE_ID = re.compile(r"^IfcSurfaceStyle\w*-(\d+)$")
MAX_CIRCLE_ELEMENTS = 300


# ------------------------------------------------------------------------------------- metrics


@dataclass
class Metrics:
    """Shape measures of one element, merged over its parts (one object per material etc.)."""

    lo: numpy.ndarray | None = None
    hi: numpy.ndarray | None = None
    area: float = 0.0
    moment: numpy.ndarray = field(default_factory=lambda: numpy.zeros(3))  # sum of area * centroid
    volume: float = 0.0  # signed, divergence theorem around ``origin``
    origin: numpy.ndarray | None = None
    triangles: int = 0
    vertices: int = 0
    parts: int = 0
    edges: list = field(default_factory=list)  # (keys of the points, triangle index triples) per part
    closed: bool | None = None
    brep: bool = False
    plane_mm: float = 0.0

    @property
    def centroid(self) -> numpy.ndarray:
        return self.moment / self.area if self.area > 0 else (self.lo + self.hi) / 2

    @property
    def bbox(self) -> numpy.ndarray:
        return numpy.concatenate([self.lo, self.hi])

    def add_mesh(self, points: numpy.ndarray, triangles: numpy.ndarray) -> None:
        points = numpy.asarray(points, dtype=numpy.float64).reshape(-1, 3)
        triangles = numpy.asarray(triangles, dtype=numpy.int64).reshape(-1, 3)
        if not len(points):
            return
        self.parts += 1
        self.vertices += len(points)
        lo, hi = points.min(axis=0), points.max(axis=0)
        self.lo = lo if self.lo is None else numpy.minimum(self.lo, lo)
        self.hi = hi if self.hi is None else numpy.maximum(self.hi, hi)
        if self.origin is None:
            self.origin = lo.copy()
        if not len(triangles):
            return
        local = points - self.origin
        a, b, c = local[triangles[:, 0]], local[triangles[:, 1]], local[triangles[:, 2]]
        cross = numpy.cross(b - a, c - a)
        double_area = numpy.sqrt((cross * cross).sum(axis=1))
        self.area += float(double_area.sum() / 2)
        self.moment += ((a + b + c) / 3 * double_area[:, None]).sum(axis=0) / 2 + self.origin * double_area.sum() / 2
        self.volume += float(numpy.einsum("ij,ij->i", a, cross).sum() / 6)
        self.triangles += len(triangles)
        keys = numpy.rint((points - self.origin) / 1e-9).astype(numpy.int64)
        self.edges.append((keys, triangles))

    def finish(self) -> "Metrics":
        """Decide whether all parts together form closed, consistently oriented shells."""
        if self.closed is None and self.edges:
            keys = numpy.concatenate([k for k, _ in self.edges])
            offsets = numpy.cumsum([0] + [len(k) for k, _ in self.edges[:-1]])
            tri = numpy.concatenate([t + o for (_, t), o in zip(self.edges, offsets)])
            _, position = numpy.unique(keys, axis=0, return_inverse=True)
            t = position.ravel()[tri]
            edges = numpy.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
            edges = edges[edges[:, 0] != edges[:, 1]]
            if len(edges):
                forward = edges[:, 0] < edges[:, 1]
                edges.sort(axis=1)
                pairs, inverse = numpy.unique(edges, axis=0, return_inverse=True)
                balance = numpy.bincount(inverse.ravel(), numpy.where(forward, 1, -1), len(pairs))
                self.closed = bool((balance == 0).all())
            else:
                self.closed = False
        self.edges = []
        return self

    def add_brep(self, brep) -> None:
        """A planar polysurface (rhino3dm.Brep): faces measured from their trim loops."""
        import rhino3dm  # noqa: F401

        vertices = brep.Vertices
        points = numpy.array([(p.X, p.Y, p.Z) for p in (vertices[i].Location for i in range(len(vertices)))])
        if not len(points):
            return
        self.parts += 1
        self.brep = True
        self.vertices += len(points)
        lo, hi = points.min(axis=0), points.max(axis=0)
        self.lo = lo if self.lo is None else numpy.minimum(self.lo, lo)
        self.hi = hi if self.hi is None else numpy.maximum(self.hi, hi)
        if self.origin is None:
            self.origin = lo.copy()
        local = points - self.origin
        faces = brep.Faces
        edge_keys, edge_tris, offset = [], [], 0
        for fi in range(len(faces)):
            face = faces[fi]
            (u0, u1), (v0, v1) = (face.Domain(0).T0, face.Domain(0).T1), (face.Domain(1).T0, face.Domain(1).T1)
            p0, n = face.PointAt((u0 + u1) / 2, (v0 + v1) / 2), face.NormalAt((u0 + u1) / 2, (v0 + v1) / 2)
            normal = numpy.array((n.X, n.Y, n.Z))
            base = numpy.array((p0.X, p0.Y, p0.Z)) - self.origin
            outward = -1.0 if face.OrientationIsReversed else 1.0
            face_area, face_moment = 0.0, numpy.zeros(3)
            for loop in face.Loops:
                indices = [trim.StartVertexIndex for trim in loop.Trims]
                if len(indices) < 3:
                    continue
                lp = local[indices]
                self.plane_mm = max(self.plane_mm, float(numpy.abs((lp - base) @ normal).max()) * 1000)
                # Fan from the first corner: signed areas handle concave loops; holes run the other
                # way round and take their area off the face's.
                a, b, c = lp[0][None, :], lp[1:-1], lp[2:]
                cross = numpy.cross(b - a, c - a)
                signed = (cross @ normal) / 2  # positive where the loop runs counter-clockwise
                face_area += float(signed.sum())
                face_moment += ((a + b + c) / 3 * signed[:, None]).sum(axis=0)
                self.triangles += len(signed)
                # Loop edges for the closedness check: a loop's edge direction as Rhino draws it,
                # flipped with the face orientation, so a closed solid balances.
                order = indices if outward > 0 else indices[::-1]
                tris = numpy.array([(order[0], order[k], order[k + 1]) for k in range(1, len(order) - 1)]) + offset
                edge_tris.append(tris)
            sign = 1.0 if face_area >= 0 else -1.0
            self.area += abs(face_area)
            self.moment += face_moment * sign + self.origin * abs(face_area)
            self.volume += outward * float(base @ normal) * face_area / 3
        keys = numpy.rint(local / 1e-9).astype(numpy.int64)
        if edge_tris:
            self.edges.append((keys, numpy.concatenate(edge_tris)))

    def to_json(self) -> dict:
        return {"bbox": self.bbox.tolist(), "centroid": self.centroid.tolist(), "area": self.area, "volume": self.volume,
                "closed": self.closed, "triangles": self.triangles, "parts": self.parts}


def compare(out: Metrics, ref: Metrics) -> dict:
    """Per-element deviations: positions in millimetres, area and volume as ratios out/ref."""
    result = {
        "bbox_mm": float(numpy.abs(out.bbox - ref.bbox).max() * 1000),
        "centroid_mm": float(numpy.linalg.norm(out.centroid - ref.centroid) * 1000),
        "area_ratio": out.area / ref.area if ref.area > 0 else math.nan,
        "volume_ratio": math.nan,
        "inverted": False,
    }
    if ref.closed and abs(ref.volume) > 0 and (out.closed or out.brep):
        result["volume_ratio"] = abs(out.volume) / abs(ref.volume)
        result["inverted"] = (out.volume < 0) != (ref.volume < 0)
        result["ref_inverted"] = ref.volume < 0
    if out.brep:
        result["plane_mm"] = out.plane_mm
    return result


# ------------------------------------------------------------------------------------- readers


class Collector:
    """Accumulates parts per GlobalId; keeps the points of a few elements for the chord check."""

    def __init__(self, keep_points: set[str] = frozenset()):
        self.metrics: dict[str, Metrics] = {}
        self.keep_points = keep_points
        self.points: dict[str, list] = {}
        self.unnamed = 0  # objects without a GlobalId

    def mesh(self, guid: str | None, points, triangles) -> None:
        if guid is None:
            self.unnamed += 1
            return
        self.metrics.setdefault(guid, Metrics()).add_mesh(points, triangles)
        if guid in self.keep_points:
            self.points.setdefault(guid, []).append(numpy.asarray(points, dtype=numpy.float64).reshape(-1, 3))

    def brep(self, guid: str | None, brep) -> None:
        if guid is None:
            self.unnamed += 1
            return
        self.metrics.setdefault(guid, Metrics()).add_brep(brep)
        if guid in self.keep_points:
            vertices = brep.Vertices
            self.points.setdefault(guid, []).append(
                numpy.array([(p.X, p.Y, p.Z) for p in (vertices[i].Location for i in range(len(vertices)))]).reshape(-1, 3))

    def finish(self) -> dict[str, Metrics]:
        for m in self.metrics.values():
            m.finish()
        return self.metrics


def read_3dm(path: Path, collector: Collector) -> dict:
    import rhino3dm

    model = rhino3dm.File3dm.Read(str(path))
    if model is None:
        raise OSError(f"cannot read {path}")
    settings = model.Settings
    info = {
        "units": str(settings.ModelUnitSystem).split(".")[-1],
        "absolute_tolerance": settings.ModelAbsoluteTolerance,
        "angle_tolerance_degrees": settings.ModelAngleToleranceDegrees,
        "single_precision_meshes": 0, "block_instances": 0, "block_definitions": 0,
        "objects": 0, "without_globalid": 0, "layers": {}, "layer_examples": [],
    }
    layers = {}
    for layer in model.Layers:
        layers[layer.Id] = layer
    def layer_path(index):
        layer = model.Layers.FindIndex(index) if index >= 0 else None
        names = []
        while layer is not None:
            names.append(layer.Name)
            parent = layer.ParentLayerId
            layer = layers.get(parent) if parent and str(parent) != "00000000-0000-0000-0000-000000000000" else None
        return "::".join(reversed(names))
    definition_objects = {obj.Attributes.Id: obj.Geometry for obj in model.Objects if obj.Attributes.IsInstanceDefinitionObject}
    definitions = {}
    for index in range(len(model.InstanceDefinitions)):
        definition = model.InstanceDefinitions.FindIndex(index)
        definitions[definition.Id] = [definition_objects[i] for i in definition.GetObjectIds() if i in definition_objects]
    info["block_definitions"] = len(definitions)
    for obj in model.Objects:
        if obj.Attributes.IsInstanceDefinitionObject:
            continue
        info["objects"] += 1
        guid = obj.Attributes.GetUserString("IfcGlobalId")
        if not guid:
            info["without_globalid"] += 1
            guid = None
        else:
            path_text = layer_path(obj.Attributes.LayerIndex)
            info["layers"][guid] = path_text
        geometries = [obj.Geometry]
        if isinstance(obj.Geometry, rhino3dm.InstanceReference):
            info["block_instances"] += 1
            geometries = []
            for geometry in definitions.get(obj.Geometry.ParentIdefId, []):
                geometry = geometry.Duplicate()
                geometry.Transform(obj.Geometry.Xform)
                geometries.append(geometry)
        for geometry in geometries:
            if isinstance(geometry, rhino3dm.Brep):
                collector.brep(guid, geometry)
            elif isinstance(geometry, rhino3dm.Mesh):
                if not geometry.Vertices.UseDoublePrecisionVertices:
                    info["single_precision_meshes"] += 1
                points = numpy.array([(p.X, p.Y, p.Z) for p in geometry.Vertices.ToPoint3dArray()])
                faces = geometry.Faces
                tris = []
                for i in range(len(faces)):
                    a, b, c, d = faces[i]
                    tris.append((a, b, c))
                    if c != d:
                        tris.append((a, c, d))
                collector.mesh(guid, points, numpy.array(tris, dtype=numpy.int64).reshape(-1, 3))
            elif guid is not None and not isinstance(geometry, (rhino3dm.Polyline, rhino3dm.PolylineCurve, rhino3dm.Curve)):
                info.setdefault("other_geometry", {}).setdefault(type(geometry).__name__, 0)
                info["other_geometry"][type(geometry).__name__] += 1
    return info


def read_glb(path: Path, collector: Collector) -> dict:
    data = path.read_bytes()
    magic, version, total = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise OSError(f"not a GLB file: {path}")
    json_length, json_type = struct.unpack_from("<II", data, 12)
    gltf = json.loads(data[20:20 + json_length])
    bin_start = 20 + json_length
    bin_length, bin_type = struct.unpack_from("<II", data, bin_start)
    binary_start = bin_start + 8
    accessors, views = gltf.get("accessors", []), gltf.get("bufferViews", [])
    info = {"max_local_coordinate": 0.0, "max_translation": 0.0, "far_local_meshes": 0,
            "validation": [], "nodes_with_mesh": 0, "total_length_ok": total == len(data),
            "bin_chunk_ok": bin_type == 0x004E4942 and binary_start + bin_length <= len(data)}
    buffers = gltf.get("buffers", [{}])
    if buffers and buffers[0].get("byteLength", 0) > bin_length:
        info["validation"].append(f"buffer byteLength {buffers[0]['byteLength']} > BIN chunk {bin_length}")
    dtypes = {5120: numpy.int8, 5121: numpy.uint8, 5122: numpy.int16, 5123: numpy.uint16, 5125: numpy.uint32, 5126: numpy.float32}
    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def accessor(index: int) -> numpy.ndarray:
        acc = accessors[index]
        view = views[acc["bufferView"]]
        dtype = numpy.dtype(dtypes[acc["componentType"]])
        width = widths[acc["type"]]
        start = binary_start + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride") or dtype.itemsize * width
        needed = stride * (acc["count"] - 1) + dtype.itemsize * width
        if acc.get("byteOffset", 0) + needed > view["byteLength"]:
            info["validation"].append(f"accessor {index} exceeds its bufferView")
        if stride == dtype.itemsize * width:
            values = numpy.frombuffer(data, dtype, acc["count"] * width, start).reshape(-1, width)
        else:
            raw = numpy.frombuffer(data, numpy.uint8, needed, start)
            rows = numpy.lib.stride_tricks.as_strided(raw, (acc["count"], dtype.itemsize * width), (stride, 1))
            values = rows.copy().view(dtype).reshape(-1, width)
        if "min" in acc and "max" in acc and len(values):
            if not (numpy.allclose(values.min(axis=0), acc["min"], rtol=0, atol=1e-6)
                    and numpy.allclose(values.max(axis=0), acc["max"], rtol=0, atol=1e-6)):
                info["validation"].append(f"accessor {index} min/max mismatch")
        elif acc["type"] == "VEC3" and acc["componentType"] == 5126:
            info["validation"].append(f"accessor {index} without min/max (required for POSITION)")
        return values

    for mesh in gltf.get("meshes", []):
        for p in mesh["primitives"]:
            acc = accessors[p["attributes"]["POSITION"]]
            extent = max(abs(c) for c in acc.get("min", [0]) + acc.get("max", [0]))
            info["max_local_coordinate"] = max(info["max_local_coordinate"], extent)
            info["far_local_meshes"] += extent > 2048.0
    to_z_up = numpy.array([[1.0, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
    nodes = gltf.get("nodes", [])
    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)] if gltf.get("scenes") else {"nodes": list(range(len(nodes)))}
    stack = [(index, to_z_up) for index in scene.get("nodes", [])]
    while stack:
        index, parent = stack.pop()
        node = nodes[index]
        matrix = parent @ accuracy._node_matrix(node)
        stack.extend((child, matrix) for child in node.get("children", []))
        if "mesh" not in node:
            continue
        info["nodes_with_mesh"] += 1
        info["max_translation"] = max(info["max_translation"], float(numpy.abs(matrix[:3, 3]).max()))
        match = _GUID_IN_NAME.search(node.get("name", ""))
        guid = accuracy._compress(match.group(1)) if match else None
        for primitive in gltf["meshes"][node["mesh"]]["primitives"]:
            if primitive.get("mode", 4) != 4:
                continue
            local = accessor(primitive["attributes"]["POSITION"]).astype(numpy.float64)
            points = local @ matrix[:3, :3].T + matrix[:3, 3]
            if "indices" in primitive:
                triangles = accessor(primitive["indices"]).astype(numpy.int64).reshape(-1, 3)
                if len(triangles) and triangles.max() >= len(points):
                    info["validation"].append(f"node {index}: index out of range")
            else:
                triangles = numpy.arange(len(points)).reshape(-1, 3)
            # A mirroring node matrix (negative determinant) flips the winding: as the viewer draws it.
            if numpy.linalg.det(matrix[:3, :3]) < 0:
                triangles = triangles[:, [0, 2, 1]]
            collector.mesh(guid, points, triangles)
    info["validation"] = sorted(set(info["validation"]))[:10]
    return info


def read_obj(path: Path, collector: Collector) -> dict:
    info = {"max_digits": 0, "groups": 0, "materials": {}}
    count = 0
    guid, points, first, faces, material = None, [], 0, [], None
    usemtl_by_guid: dict[str, set] = {}

    def flush():
        if guid is not None:
            info["groups"] += 1
            collector.mesh(guid, numpy.array(points, dtype=numpy.float64).reshape(-1, 3),
                           numpy.array(faces, dtype=numpy.int64).reshape(-1, 3) - first)

    with open(path, "rb") as stream:
        for line in stream:
            tag = line[:2]
            if tag == b"v ":
                count += 1
                values = line.split()[1:4]
                if count % 97 == 1:
                    info["max_digits"] = max(info["max_digits"], *(accuracy._digits(v) for v in values))
                points.append([float(v) for v in values])
            elif tag == b"f ":
                corners = [int(c.split(b"/")[0]) - 1 for c in line.split()[1:]]
                faces.extend((corners[0], corners[k], corners[k + 1]) for k in range(1, len(corners) - 1))
            elif tag == b"g ":
                flush()
                match = _GUID_IN_NAME.search(line.decode("utf-8", "replace"))
                guid = accuracy._compress(match.group(1)) if match else None
                points, first, faces = [], count, []
            elif line.startswith(b"usemtl"):
                material = line.split(None, 1)[1].strip().decode()
                if guid:
                    usemtl_by_guid.setdefault(guid, set()).add(material)
    flush()
    mtl = path.with_suffix(".mtl")
    colours = {}
    if mtl.exists():
        name = None
        for line in mtl.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "newmtl":
                name = parts[1]
                colours[name] = {}
            elif name and parts[0] in ("Kd", "d", "Tr", "Ks", "Ka"):
                colours[name][parts[0]] = [float(v) for v in parts[1:]]
    info["materials"] = colours
    info["materials_used"] = usemtl_by_guid
    return info


def read_dae(path: Path, collector: Collector) -> dict:
    info: dict = {}
    for guid, points, triangles in accuracy.iter_dae(path, info):
        collector.mesh(guid, points, triangles)
    return info


READERS = {"3dm": read_3dm, "glb": read_glb, "obj": read_obj, "dae": read_dae}


# ----------------------------------------------------------------------------------- reference


def open_model(path: Path, log) -> tuple:
    """The IFC as IfcOpenShell reads it; schemas it does not know go through the converter's schema
    bridge (IFC2x2, IFC4x4) and nameless SI units through its unit repair, both noted."""
    import ifcopenshell

    notes = []
    try:
        model = ifcopenshell.open(str(path))
    except ifcopenshell.SchemaError as exc:
        from ifc_converter import schema_bridge

        bridge = schema_bridge.bridge_for(path)
        if bridge is None:
            raise
        bridged = schema_bridge.bridged_copy(path, bridge)
        try:
            model = ifcopenshell.open(str(bridged.path))
        finally:
            bridged.remove()
        notes.append(f"schema bridge: {exc} -> {bridged.note}")
    from ifc_converter.converter import merge_projects, repair_extrusions, repair_units

    import ifcopenshell.util.unit as unit_util

    try:
        before = unit_util.calculate_unit_scale(model)
    except AttributeError:  # nameless SI unit: IfcOpenShell cannot even compute the scale
        before = None
    repair_units(model)
    after = unit_util.calculate_unit_scale(model)
    if before != after:
        notes.append(f"repair_units: length scale {before} -> {after}")
    fixed = repair_extrusions(model)
    if fixed:
        notes.append(f"repair_extrusions: {fixed} negative extrusions")
    projects = len(model.by_type("IfcProject"))
    merge_projects(model)
    if projects > 1:
        notes.append(f"merge_projects: {projects} projects")
    for note in notes:
        log(f"  note: {note}")
    return model, notes


def products_with_bodies(model) -> list:
    """Every product with a representation that is not excluded by class (as the converter's selection)."""
    result = []
    for product in model.by_type("IfcProduct"):
        if product.Representation is None or any(product.is_a(name) for name in EXCLUDED):
            continue
        result.append(product)
    return result


def reference_metrics(model, products: list, threads: int, log, keep_points: set[str],
                      disable_openings: bool = False) -> tuple[dict[str, Metrics], dict[str, list], dict]:
    """OpenCASCADE geometry of the products in world coordinates, default tessellation."""
    import ifcopenshell.geom as geom

    settings = geom.settings()
    settings.set("use-world-coords", True)
    if disable_openings:
        settings.set("disable-opening-subtractions", True)
    collector = Collector(keep_points)
    facts = {"max_abs_coordinate": 0.0, "failed": []}
    t = time.time()
    with accuracy._quiet_stdout():
        for start in range(0, len(products), 200):
            chunk = products[start:start + 200]
            iterator = geom.iterator(settings, model, threads, include=chunk, geometry_library="opencascade")
            if not iterator.initialize():
                continue
            while True:
                shape = iterator.get()
                geometry = shape.geometry
                if geometry.faces_buffer:
                    element = model.by_id(shape.id)
                    points = numpy.frombuffer(geometry.verts_buffer, numpy.float64).reshape(-1, 3)
                    facts["max_abs_coordinate"] = max(facts["max_abs_coordinate"], float(numpy.abs(points).max()))
                    collector.mesh(element.GlobalId, points, numpy.frombuffer(geometry.faces_buffer, numpy.int32).reshape(-1, 3))
                if not iterator.next():
                    break
            del iterator
            if (start // 200) % 10 == 9:
                log(f"    reference {start + len(chunk)}/{len(products)} ({time.time() - t:.0f} s)")
    metrics = collector.finish()
    facts["seconds"] = round(time.time() - t)
    return metrics, collector.points, facts


# ---------------------------------------------------------------------------------- the checks


def summarize(comparisons: dict[str, dict], classes: dict[str, str]) -> dict:
    out: dict = {"n": len(comparisons), "inverted": [g for g, c in comparisons.items() if c["inverted"]][:10],
                 "inverted_count": sum(c["inverted"] for c in comparisons.values())}
    for key in ("bbox_mm", "centroid_mm", "plane_mm"):
        values = [(c[key], g) for g, c in comparisons.items() if key in c and not math.isnan(c[key])]
        if values:
            worst = max(values)
            numbers = numpy.array([v for v, _ in values])
            out[key] = {"max": float(worst[0]), "p95": float(numpy.percentile(numbers, 95)), "worst": worst[1],
                        "worst_class": classes.get(worst[1]), "over": int((numbers > POSITION_TOLERANCE_MM).sum())}
    for key in ("area_ratio", "volume_ratio"):
        values = [(abs(c[key] - 1), c[key], g) for g, c in comparisons.items() if not math.isnan(c[key])]
        if values:
            worst = max(values)
            numbers = numpy.array([v for v, _, _ in values])
            out[key] = {"max_dev": float(worst[0]), "ratio": float(worst[1]), "p95": float(numpy.percentile(numbers, 95)),
                        "worst": worst[2], "worst_class": classes.get(worst[2]), "n": len(values),
                        "over": int((numbers > RATIO_TOLERANCE).sum())}
    return out


def worst_elements(comparisons: dict[str, dict], classes: dict[str, str], limit: int = 12) -> list[dict]:
    rows = []
    for g, c in comparisons.items():
        score = max(c["bbox_mm"] / POSITION_TOLERANCE_MM, c["centroid_mm"] / POSITION_TOLERANCE_MM,
                    abs(c["area_ratio"] - 1) / RATIO_TOLERANCE if not math.isnan(c["area_ratio"]) else 0,
                    abs(c["volume_ratio"] - 1) / RATIO_TOLERANCE if not math.isnan(c["volume_ratio"]) else 0,
                    10 if c["inverted"] else 0)
        if score > 1:
            rows.append({"guid": g, "class": classes.get(g), "score": round(score, 2), **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in c.items()}})
    rows.sort(key=lambda r: -r["score"])
    return rows[:limit]


def check_openings(model, products, output: dict[str, Metrics], reference: dict[str, Metrics], threads: int, log) -> dict:
    """Elements with openings: the output's volume must be the reference's (net), below the gross."""
    with_openings = [p for p in products if getattr(p, "HasOpenings", None)][:60]
    if not with_openings:
        return {"n": 0}
    gross, _, _ = reference_metrics(model, with_openings, threads, log, set(), disable_openings=True)
    rows = []
    for p in with_openings:
        g = p.GlobalId
        if g in gross and g in reference and g in output and reference[g].closed:
            net, big, out = abs(reference[g].volume), abs(gross[g].volume), abs(output[g].volume)
            rows.append({"guid": g, "class": p.is_a(), "gross": big, "net": net, "out": out,
                         "cut": big - net > 1e-9, "out_net_ratio": out / net if net else math.nan})
    not_cut = [r for r in rows if not r["cut"]]
    off = [r for r in rows if r["cut"] and (math.isnan(r["out_net_ratio"]) or abs(r["out_net_ratio"] - 1) > RATIO_TOLERANCE)]
    return {"n": len(rows), "gross_equals_net": len(not_cut), "output_not_net": len(off),
            "examples": (off + not_cut)[:5],
            "mean_cut_share": float(numpy.mean([(r["gross"] - r["net"]) / r["gross"] for r in rows if r["gross"]])) if rows else None}


def check_circles(model, products, points: dict[str, list], classes) -> dict:
    """Chord error of round extrusions in the output (accuracy.expectations' circles)."""
    truths = accuracy.expectations(model, products)
    rows = []
    for g, truth in truths.items():
        if g not in points or not truth.circles:
            continue
        shape = accuracy.Shape(numpy.concatenate(points[g]))
        for circle in truth.circles:
            error = accuracy.chord_error(shape, circle)
            if error:
                rows.append((error[0] * 1000, error[1] * 1000, g))
    if not rows:
        return {"n": 0}
    worst = max(rows)
    on = max(r[1] for r in rows)
    return {"n": len(rows), "chord_mm_max": worst[0], "vertex_off_circle_mm_max": on, "worst": worst[2], "worst_class": classes.get(worst[2])}


def circle_guids(model, products) -> set[str]:
    truths = accuracy.expectations(model, products)
    return {g for g, t in list(truths.items()) if t.circles}


def check_obj_materials(model, info: dict) -> dict:
    """Every .mtl colour must be the IFC style's SurfaceColour (and transparency)."""
    mismatches, checked, unknown = [], 0, 0
    for name, values in info.get("materials", {}).items():
        match = _STYLE_ID.match(name)
        if not match:
            unknown += 1
            continue
        try:
            style = model.by_id(int(match.group(1)))
        except Exception:
            unknown += 1
            continue
        colour = getattr(style, "SurfaceColour", None)
        if colour is None:
            unknown += 1
            continue
        checked += 1
        expected = [colour.Red, colour.Green, colour.Blue]
        kd = values.get("Kd")
        if kd is None or not numpy.allclose(kd, expected, atol=1e-6):
            mismatches.append({"material": name, "Kd": kd, "ifc": expected})
        transparency = getattr(style, "Transparency", None)
        if transparency:
            d = values.get("d", [1.0])[0] if "d" in values else (1 - values["Tr"][0] if "Tr" in values else 1.0)
            if abs(d - (1 - transparency)) > 1e-6:
                mismatches.append({"material": name, "d": d, "ifc_transparency": transparency})
    return {"checked": checked, "unknown_names": unknown, "mismatches": mismatches[:5], "mismatch_count": len(mismatches)}


def check_dae_materials(model, info: dict) -> dict:
    mismatches, checked, unknown = [], 0, 0
    for name, values in info.get("materials", {}).items():
        match = _STYLE_ID.match(name)
        if not match or values is None:
            unknown += 1
            continue
        try:
            style = model.by_id(int(match.group(1)))
        except Exception:
            unknown += 1
            continue
        colour = getattr(style, "SurfaceColour", None)
        if colour is None:
            unknown += 1
            continue
        checked += 1
        expected = [colour.Red, colour.Green, colour.Blue]
        if values["diffuse"] is None or not numpy.allclose(values["diffuse"][:3], expected, atol=1e-6):
            mismatches.append({"material": name, "diffuse": values["diffuse"], "ifc": expected})
    return {"checked": checked, "unknown_names": unknown, "mismatches": mismatches[:5], "mismatch_count": len(mismatches)}


def check_rhino_layers(model, products, info: dict) -> dict:
    """Every element's layer path should name its storey (or site/building) and its class."""
    import ifcopenshell.util.element as element_util

    wrong_class, wrong_level, checked, examples = 0, 0, 0, []
    by_guid = {p.GlobalId: p for p in products}
    for guid, path in info.get("layers", {}).items():
        product = by_guid.get(guid)
        if product is None:
            continue
        checked += 1
        parts = path.split("::")
        cls = product.is_a()
        if not any(cls == part or cls in part for part in parts):
            wrong_class += 1
            examples.append({"guid": guid, "layer": path, "class": cls})
        container = element_util.get_container(product)
        # Layers are by storey (elements in a space or in an aggregate count for their storey);
        # elements contained in a site or building go to a fallback layer.
        for _ in range(8):
            if container is None or container.is_a("IfcBuildingStorey"):
                break
            container = element_util.get_container(container) or element_util.get_aggregate(container)
        if container is not None and container.is_a("IfcBuildingStorey") and container.Name and not any(container.Name.strip() in part for part in parts):
            wrong_level += 1
            if len(examples) < 5:
                examples.append({"guid": guid, "layer": path, "container": container.Name})
    return {"checked": checked, "class_not_in_layer": wrong_class, "container_not_in_layer": wrong_level, "examples": examples[:5]}


def mirrored_guids(products) -> set[str]:
    return {p.GlobalId for p in products if accuracy.is_mirrored(p)}


# -------------------------------------------------------------------------------------- driver


def convert_in_child(source: Path, fmt: str, geometry: str, output: Path, threads: int, blocks: bool, envelope: bool) -> dict:
    for stale in (output, output.with_suffix(".mtl")):
        stale.unlink(missing_ok=True)
    command = [sys.executable, __file__, "--child", str(source), fmt, geometry, str(output), "--threads", str(threads)]
    if blocks:
        command.append("--blocks")
    if envelope:
        command.append("--envelope")
    started = time.time()
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    seconds = round(time.time() - started, 1)
    lines = [line for line in process.stdout.splitlines() if line.startswith("{")]
    if process.returncode == 0 and lines:
        return {"status": "ok", "seconds": seconds, **json.loads(lines[-1])}
    return {"status": "error", "seconds": seconds, "error": (process.stderr.strip().splitlines() or ["?"])[-1][:300]}


def _child(source: str, fmt: str, geometry: str, output: str, threads: int, blocks: bool, envelope: bool) -> int:
    from ifc_converter import convert

    notes = []
    with accuracy._quiet_stdout():
        result = convert(source, output, fmt=fmt, geometry=geometry, threads=threads, blocks=blocks, envelope=envelope,
                         status=lambda phase, text: notes.append(text) if phase == "note" else None)
    print(json.dumps({"elements": result.elements, "skipped": result.skipped, "inside": result.inside,
                      "no_geometry": result.no_geometry[:20], "notes": notes[:10]}), flush=True)
    return 0


def check_file(source: Path, modes: list[str], out_dir: Path, threads: int, log, hull: bool, keep: bool,
               rows_path: Path | None) -> dict:
    started = time.time()
    report: dict = {"file": source.name, "size_mb": round(source.stat().st_size / 1e6, 1), "modes": {}}
    model, notes = open_model(source, log)
    report["notes"] = notes
    report.update(accuracy.model_facts(model))
    products = products_with_bodies(model)
    classes = {p.GlobalId: p.is_a() for p in products}
    circles = set(list(circle_guids(model, products))[:MAX_CIRCLE_ELEMENTS])
    mirrored = mirrored_guids(products)
    report["mirrored_types"] = len(mirrored)
    log(f"  {len(products)} products with representation, {len(circles)} round extrusions, {len(mirrored)} mirrored")
    reference, _, facts = reference_metrics(model, products, threads, log, set())
    report["reference"] = {"n": len(reference), "closed": sum(m.closed for m in reference.values()),
                           "inverted": sum(1 for m in reference.values() if m.closed and m.volume < 0),
                           "mirrored_inverted": sum(1 for g in mirrored if g in reference and reference[g].closed and reference[g].volume < 0),
                           **facts}
    log(f"  reference: {len(reference)} shapes in {facts['seconds']} s, max |coordinate| {facts['max_abs_coordinate']:.1f} m")
    full_outputs: dict[str, dict[str, Metrics]] = {}
    for mode in modes:
        fmt, geometry, blocks = MODES[mode]
        output = out_dir / f"{source.stem}.{mode}.{fmt}"
        log(f"  > {mode}")
        entry = run_mode(source, fmt, geometry, blocks, False, output, threads, model, products, classes, reference, circles, mirrored, log)
        report["modes"][mode] = entry
        if entry["status"] == "ok":
            full_outputs[mode] = entry.pop("_metrics")
        if rows_path:
            append_row(rows_path, report, mode, entry)
        if not keep:
            for path in (output, output.with_suffix(".mtl")):
                path.unlink(missing_ok=True)
    if hull:
        for mode in ("glb", "3dm-brep"):
            if mode not in full_outputs:
                continue
            fmt, geometry, blocks = MODES[mode]
            output = out_dir / f"{source.stem}.{mode}.hull.{fmt}"
            log(f"  > {mode} hull")
            entry = run_mode(source, fmt, geometry, blocks, True, output, threads, model, products, classes, reference, set(), mirrored, log)
            if entry["status"] == "ok":
                hull_metrics = entry.pop("_metrics")
                full = full_outputs[mode]
                identical = different = 0
                examples = []
                for g, m in hull_metrics.items():
                    f = full.get(g)
                    if f is None:
                        continue
                    same = (numpy.array_equal(m.bbox, f.bbox) and m.area == f.area and m.volume == f.volume
                            and m.triangles == f.triangles and m.vertices == f.vertices)
                    if same:
                        identical += 1
                    else:
                        different += 1
                        if len(examples) < 5:
                            examples.append({"guid": g, "class": classes.get(g), "bbox_mm": float(numpy.abs(m.bbox - f.bbox).max() * 1000),
                                             "area_ratio": m.area / f.area if f.area else None})
                external = external_guids(model, products)
                kept = set(hull_metrics)
                entry["hull"] = {"kept": len(hull_metrics), "full": len(full), "identical": identical, "different": different,
                                 "examples": examples, "not_in_full": len(kept - set(full)),
                                 "external_dropped": sorted(external - kept)[:10], "external_dropped_count": len(external - kept),
                                 "external": len(external), "dropped_classes": _class_counts([g for g in full if g not in kept], classes)}
            report["modes"][mode + "-hull"] = entry
            if rows_path:
                append_row(rows_path, report, mode + "-hull", entry)
            if not keep:
                output.unlink(missing_ok=True)
    report["seconds"] = round(time.time() - started)
    return report


def external_guids(model, products) -> set[str]:
    import ifcopenshell.util.element as element_util

    result = set()
    for p in products:
        try:
            psets = element_util.get_psets(p)
        except Exception:
            continue
        for name, values in psets.items():
            if name.startswith("Pset_") and values.get("IsExternal") is True:
                result.add(p.GlobalId)
    return result


def _class_counts(guids, classes) -> dict:
    counts: dict[str, int] = {}
    for g in guids:
        counts[classes.get(g, "?")] = counts.get(classes.get(g, "?"), 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1])[:8])


def run_mode(source, fmt, geometry, blocks, envelope, output, threads, model, products, classes, reference, circles, mirrored, log) -> dict:
    result = convert_in_child(source, fmt, geometry, output, threads, blocks, envelope)
    entry = {"seconds": result.get("seconds"), "status": result["status"], "notes": result.get("notes", [])}
    if result["status"] != "ok":
        entry["error"] = result.get("error")
        log(f"    FAILED: {entry['error']}")
        return entry
    entry["converter"] = {k: result.get(k) for k in ("elements", "skipped", "inside", "no_geometry")}
    entry["output_mb"] = round(sum(p.stat().st_size for p in (output, output.with_suffix(".mtl")) if p.exists()) / 1e6, 1)
    t = time.time()
    collector = Collector(circles)
    try:
        info = READERS[fmt](output, collector)
    except Exception as exc:
        entry["status"] = "error"
        entry["error"] = f"reading: {type(exc).__name__}: {exc}"
        log(f"    READ FAILED: {entry['error']}")
        return entry
    metrics = collector.finish()
    entry["read_seconds"] = round(time.time() - t)
    entry["info"] = {k: v for k, v in info.items() if k not in ("layers", "materials", "materials_used")}
    entry["unnamed_objects"] = collector.unnamed
    comparisons = {g: compare(m, reference[g]) for g, m in metrics.items() if g in reference}
    entry["compared"] = len(comparisons)
    spaces = {g for g, c in classes.items() if c == "IfcSpace"}
    missing = [g for g in reference if g not in metrics and (fmt in SPACE_FORMATS or g not in spaces)]
    extra = [g for g in metrics if g not in reference]
    entry["spaces"] = {"reference": sum(g in reference for g in spaces), "output": sum(g in metrics for g in spaces)}
    entry["missing"] = {"count": len(missing), "classes": _class_counts(missing, classes), "examples": missing[:10]}
    entry["extra"] = {"count": len(extra), "classes": _class_counts(extra, classes), "examples": extra[:10]}
    entry["summary"] = summarize(comparisons, classes)
    entry["worst"] = worst_elements(comparisons, classes)
    entry["mirrored"] = {"n": sum(g in comparisons for g in mirrored),
                         "inverted": [g for g in mirrored if g in comparisons and comparisons[g]["inverted"]][:10],
                         "closed": sum(1 for g in mirrored if g in metrics and metrics[g].closed)}
    entry["openings"] = check_openings(model, products, metrics, reference, threads, log)
    if circles:
        entry["circles"] = check_circles(model, products, collector.points, classes)
    if fmt == "obj":
        entry["materials"] = check_obj_materials(model, info)
    elif fmt == "dae":
        entry["materials"] = check_dae_materials(model, info)
    elif fmt == "3dm":
        entry["layers"] = check_rhino_layers(model, products, info)
    entry["_metrics"] = metrics
    s = entry["summary"]
    log(f"    {len(comparisons)} compared, missing {len(missing)}, extra {len(extra)}, bbox max {s.get('bbox_mm', {}).get('max', 0):.3f} mm, "
        f"centroid max {s.get('centroid_mm', {}).get('max', 0):.3f} mm, area dev max {s.get('area_ratio', {}).get('max_dev', 0) * 100:.3f} %, "
        f"volume dev max {s.get('volume_ratio', {}).get('max_dev', 0) * 100:.3f} %, inverted {s['inverted_count']} ({entry['read_seconds']} s read)")
    return entry


def append_row(path: Path, report: dict, mode: str, entry: dict) -> None:
    if not path.exists():
        path.write_text(
            "| Model | Mode | Compared | bbox max (mm) | centroid max (mm) | area dev max | volume dev max | inverted | missing | extra | over tol. (pos/area/vol) | time |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
    with open(path, "a", encoding="utf-8") as f:
        f.write(format_row(report, mode, entry) + "\n")


def format_row(report: dict, mode: str, entry: dict) -> str:
    if entry["status"] != "ok":
        return f"| {report['file']} | {mode} | failed: {entry.get('error')} |||||||||"
    s = entry["summary"]
    b, c, a, v = s.get("bbox_mm", {}), s.get("centroid_mm", {}), s.get("area_ratio", {}), s.get("volume_ratio", {})
    miss, extra = entry["missing"], entry["extra"]
    over = f"{b.get('over', 0) + 0}/{a.get('over', 0)}/{v.get('over', 0)}"
    hull = entry.get("hull")
    hull_text = f" hull: {hull['kept']}/{hull['full']} kept, {hull['identical']} identical, {hull['different']} differ, {hull['external_dropped_count']} external dropped" if hull else ""
    return (f"| {report['file']} | {mode} | {entry['compared']} | {b.get('max', 0):.3f} | {c.get('max', 0):.3f} | "
            f"{a.get('max_dev', 0) * 100:.3f} % (n={a.get('n', 0)}) | {v.get('max_dev', 0) * 100:.3f} % (n={v.get('n', 0)}) | "
            f"{s['inverted_count']} | {miss['count']} {json.dumps(miss['classes']) if miss['count'] else ''} | "
            f"{extra['count']} {json.dumps(extra['classes']) if extra['count'] else ''} | {over} | {entry['seconds']} s{hull_text} |")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--modes", default=",".join(DEFAULT_MODES))
    parser.add_argument("--out-dir", type=Path, default=Path("night-accuracy-out"))
    parser.add_argument("--report", type=Path, default=Path("night-accuracy-rows.md"), help="table rows, appended per model x mode")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--hull", action="store_true", help="also convert with the hull option and compare with the full run")
    parser.add_argument("--keep-output", action="store_true")
    parser.add_argument("--blocks", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--envelope", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--child", nargs=4, metavar=("IFC", "FMT", "GEOMETRY", "OUT"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    import importlib.util

    if importlib.util.find_spec("ifc_converter") is None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    if args.child:
        return _child(*args.child, args.threads, args.blocks, args.envelope)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        parser.error(f"unknown mode(s): {', '.join(unknown)}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    log = lambda text: print(text, flush=True)  # noqa: E731
    for source in args.files:
        log(f"> {source.name}")
        try:
            report = check_file(source, modes, args.out_dir, args.threads, log, args.hull, args.keep_output, args.report)
        except Exception as exc:
            import traceback

            report = {"file": source.name, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-3000:]}
            log(f"  ERROR {report['error']}")
        with open(args.out_dir / f"{source.stem}.json", "w", encoding="utf-8") as f:
            json.dump(report, f, default=str, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
