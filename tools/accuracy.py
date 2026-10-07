"""Check the dimensional accuracy of converted files against the IFC.

Every element of a sample is compared in each output format with IfcOpenShell's own geometry
(world coordinates, double precision, the same tessellation settings) from the kernel the
conversion used and from OpenCASCADE: bounding box, vertex positions (distance to the reference
surface), surface area and volume. Independent of any geometry kernel, the IFC's own dimensions are
checked too: extrusions of rectangles, circles, I profiles and polygons (expected corners and
volume, computed here from the profile, the placements and the units), the chord error of round
extrusions, door and window OverallWidth/OverallHeight and the standard quantity sets (Qto).

    python tools/accuracy.py files/*.ifc --modes 3dm-brep,3dm-mesh,glb,obj --out-dir out --report accuracy.md

Each conversion runs in its own process, like tools/benchmark.py.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
import re
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy

MODES = {
    "3dm-brep": ("3dm", "brep"),
    "3dm-mesh": ("3dm", "mesh"),
    "glb": ("glb", "brep"),
    "obj": ("obj", "brep"),
}
# Elements compared per file (chosen at random with a fixed seed), plus up to GROUND_TRUTH_SAMPLE
# elements with independently known dimensions.
DEFAULT_SAMPLE = 1500
GROUND_TRUTH_SAMPLE = 600
# Elements also compared with OpenCASCADE geometry alone: it takes minutes for some detailed Revit
# elements and large terrains.
DEFAULT_OCC_SAMPLE = 300
# Output vertices per element measured against the reference surface (the rest are skipped).
MAX_QUERY_VERTICES = 2000
# Point x triangle pairs evaluated at once.
DISTANCE_BLOCK = 1 << 21
# Output vertices closer than this (metres) to a reference vertex are not measured against the
# triangles; at most MAX_SURFACE_QUERIES others per element are (the farthest from any vertex).
VERTEX_SHORTCUT = 1e-5
MAX_SURFACE_QUERIES = 300
# Grid cell (metres) for the nearest-vertex search.
NEAREST_CELL = 1e-3

_GUID_IN_NAME = re.compile(r"product-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


# ------------------------------------------------------------------------------------- geometry


@dataclass
class Shape:
    """An element's geometry in world coordinates (metres)."""

    points: numpy.ndarray  # (n, 3) float64, every vertex of the output
    triangles: numpy.ndarray | None = None  # (m, 3) indices into points, for meshes
    area: float = 0.0
    volume: float = 0.0  # signed: positive for closed shells pointing outwards
    # Breps: the largest distance of a vertex from the plane of a face it bounds.
    plane_deviation: float = 0.0
    kinds: set = field(default_factory=set)  # "brep", "mesh"

    @property
    def bbox(self) -> numpy.ndarray:
        return numpy.concatenate([self.points.min(axis=0), self.points.max(axis=0)])


def merge_shapes(shapes: list[Shape]) -> Shape:
    if len(shapes) == 1:
        return shapes[0]
    points, triangles, offset = [], [], 0
    for shape in shapes:
        points.append(shape.points)
        if shape.triangles is not None:
            triangles.append(shape.triangles + offset)
        offset += len(shape.points)
    return Shape(
        numpy.concatenate(points), numpy.concatenate(triangles) if triangles else None,
        sum(s.area for s in shapes), sum(s.volume for s in shapes),
        max(s.plane_deviation for s in shapes), set().union(*(s.kinds for s in shapes)),
    )


def mesh_shape(points: numpy.ndarray, triangles: numpy.ndarray) -> Shape:
    """A Shape with the area and signed volume of a triangle mesh."""
    points = numpy.asarray(points, dtype=numpy.float64).reshape(-1, 3)
    triangles = numpy.asarray(triangles, dtype=numpy.int64).reshape(-1, 3)
    shape = Shape(points, triangles, kinds={"mesh"})
    if len(triangles) and len(points):
        # Relative to a point of the shape: far from the origin the products below would cancel out.
        local = points - points.min(axis=0)
        a, b, c = local[triangles[:, 0]], local[triangles[:, 1]], local[triangles[:, 2]]
        cross = numpy.cross(b - a, c - a)
        shape.area = float(numpy.sqrt((cross * cross).sum(axis=1)).sum() / 2)
        shape.volume = float(numpy.einsum("ij,ij->i", a, cross).sum() / 6)
    return shape


def is_closed(shape: Shape) -> bool:
    """Whether the triangles (vertices matched by position) form closed, consistently oriented shells:
    every edge is used as often in one direction as in the other, so the signed volume is meaningful."""
    if shape.triangles is None or not len(shape.triangles):
        return False
    keys = numpy.rint((shape.points - shape.points.min(axis=0)) / 1e-9).astype(numpy.int64)
    _, position = numpy.unique(keys, axis=0, return_inverse=True)
    position = position.ravel()
    t = position[shape.triangles]
    edges = numpy.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    edges = edges[edges[:, 0] != edges[:, 1]]
    if not len(edges):
        return False
    forward = edges[:, 0] < edges[:, 1]
    edges.sort(axis=1)
    pairs, inverse = numpy.unique(edges, axis=0, return_inverse=True)
    balance = numpy.bincount(inverse.ravel(), numpy.where(forward, 1, -1), len(pairs))
    return bool((balance == 0).all())


def distances_to_mesh(query: numpy.ndarray, points: numpy.ndarray, triangles: numpy.ndarray) -> numpy.ndarray:
    """The distance of every query point to the nearest triangle."""
    result = numpy.full(len(query), numpy.inf)
    if not len(query) or not len(triangles):
        return result
    origin = points.min(axis=0)  # precision far from the world origin
    query = query - origin
    a, b, c = (points[triangles[:, k]] - origin for k in range(3))
    block = max(1, DISTANCE_BLOCK // len(query))
    for first in range(0, len(triangles), block):
        sl = slice(first, first + block)
        d = _point_triangle_distance(query[:, None, :], a[None, sl], b[None, sl], c[None, sl])
        numpy.minimum(result, d.min(axis=1), out=result)
    return result


def _point_triangle_distance(p, a, b, c):
    """Distance of points p to triangles abc (broadcast), robust for degenerate triangles."""
    ab, ac = b - a, c - a
    n = numpy.cross(ab, ac)
    nn = (n * n).sum(axis=-1)
    ap = p - a
    # inside the prism over the triangle: the projection has non-negative barycentric coordinates
    with numpy.errstate(invalid="ignore", divide="ignore"):
        u = (numpy.cross(ap, ac) * n).sum(axis=-1) / nn
        v = (numpy.cross(ab, ap) * n).sum(axis=-1) / nn
        plane = numpy.abs((ap * n).sum(axis=-1)) / numpy.sqrt(nn)
    inside = (nn > 0) & (u >= 0) & (v >= 0) & (u + v <= 1)
    edge = numpy.minimum(numpy.minimum(_segment_distance(p, a, b), _segment_distance(p, b, c)), _segment_distance(p, c, a))
    return numpy.where(inside, plane, edge)


def _segment_distance(p, a, b):
    ab = b - a
    length = (ab * ab).sum(axis=-1)
    with numpy.errstate(invalid="ignore", divide="ignore"):
        t = numpy.clip(((p - a) * ab).sum(axis=-1) / length, 0.0, 1.0)
    t = numpy.where(length > 0, t, 0.0)
    d = p - (a + t[..., None] * ab)
    return numpy.sqrt((d * d).sum(axis=-1))


def vertex_deviation(output: Shape, reference: Shape) -> float:
    """The largest distance (metres) of an output vertex from the reference surface (an upper bound:
    the distance to the nearest reference vertex where that is below VERTEX_SHORTCUT)."""
    if reference.triangles is None or not len(reference.triangles) or not len(output.points):
        return math.nan
    query = output.points
    if len(query) > MAX_QUERY_VERTICES:
        query = query[numpy.random.default_rng(0).choice(len(query), MAX_QUERY_VERTICES, replace=False)]
    distance = nearest_vertex_distances(query, reference.points)
    far = distance > VERTEX_SHORTCUT
    if far.any():
        rows = numpy.flatnonzero(far)
        if len(rows) > MAX_SURFACE_QUERIES:  # a sample of them
            skipped = rows
            rows = numpy.sort(numpy.random.default_rng(0).choice(rows, MAX_SURFACE_QUERIES, replace=False))
            distance[skipped] = numpy.nan
        surface = distances_to_mesh(query[rows], reference.points, reference.triangles)
        distance[rows] = surface
    return float(numpy.nanmax(distance))


def nearest_vertex_distances(query: numpy.ndarray, points: numpy.ndarray, cell: float = NEAREST_CELL) -> numpy.ndarray:
    """The distance of every query point to the nearest of ``points`` if closer than ``cell``, else
    at least ``cell`` (inf when no point is in the neighbouring grid cells)."""
    origin = points.min(axis=0)
    keys = _cell_keys(numpy.floor((points - origin) / cell).astype(numpy.int64))
    order = numpy.argsort(keys, kind="stable")
    sorted_keys = keys[order]
    cells = numpy.floor((query - origin) / cell).astype(numpy.int64)
    best = numpy.full(len(query), numpy.inf)
    for offset in itertools.product((-1, 0, 1), repeat=3):
        k = _cell_keys(cells + offset)
        low = numpy.searchsorted(sorted_keys, k, "left")
        count = numpy.searchsorted(sorted_keys, k, "right") - low
        for j in range(int(count.max(initial=0))):
            valid = j < count
            index = order[numpy.minimum(low + j, len(order) - 1)]
            d = numpy.sqrt(((points[index] - query) ** 2).sum(axis=1))
            best = numpy.where(valid, numpy.minimum(best, d), best)
    return best


def _cell_keys(cells: numpy.ndarray) -> numpy.ndarray:
    """One int64 per grid cell (collisions only cost time: distances are computed exactly)."""
    return (cells[:, 0] * 73856093) ^ (cells[:, 1] * 19349663) ^ (cells[:, 2] * 83492791)


def compare(output: Shape, reference: Shape) -> dict:
    """Deviations of an output shape from its reference, in millimetres (area: relative)."""
    result = {
        "bbox_mm": float(numpy.abs(output.bbox - reference.bbox).max() * 1000),
        "vertex_mm": vertex_deviation(output, reference) * 1000,
        "area_rel": abs(output.area - reference.area) / reference.area if reference.area > 0 else math.nan,
        "volume_mm": math.nan,
        "inverted": False,
    }
    if reference.area > 0 and is_closed(reference):
        # The volume difference spread over the surface: how far the surface moved on average.
        result["volume_mm"] = abs(abs(output.volume) - abs(reference.volume)) / reference.area * 1000
        # Closed but inside out (negative signed volume), e.g. mirrored type geometry.
        result["inverted"] = output.volume < 0
        result["reference_inverted"] = reference.volume < 0
    if "brep" in output.kinds:
        result["plane_mm"] = output.plane_deviation * 1000
    return result


# ------------------------------------------------------------------------------------- readers


def read_output(path: Path, fmt: str, wanted: set[str]) -> tuple[dict[str, Shape], dict]:
    """The shapes of the wanted GlobalIds in a converted file, and facts about the file."""
    reader = {"3dm": read_3dm, "glb": read_glb, "obj": read_obj}[fmt]
    shapes, info = reader(path, wanted)
    return {guid: merge_shapes(parts) for guid, parts in shapes.items()}, info


def read_3dm(path: Path, wanted: set[str]) -> tuple[dict[str, list[Shape]], dict]:
    import rhino3dm

    model = rhino3dm.File3dm.Read(str(path))
    if model is None:
        raise OSError(f"cannot read {path}")
    settings = model.Settings
    info = {
        "units": str(settings.ModelUnitSystem).split(".")[-1],
        "absolute_tolerance": settings.ModelAbsoluteTolerance,
        "angle_tolerance_degrees": settings.ModelAngleToleranceDegrees,
        "relative_tolerance": settings.ModelRelativeTolerance,
        "single_precision_meshes": 0,
    }
    shapes: dict[str, list[Shape]] = {}
    for obj in model.Objects:
        guid = obj.Attributes.GetUserString("IfcGlobalId")
        if guid not in wanted:
            continue
        geometry = obj.Geometry
        if isinstance(geometry, rhino3dm.Brep):
            shape = brep_shape(geometry)
        elif isinstance(geometry, rhino3dm.Mesh):
            if not geometry.Vertices.UseDoublePrecisionVertices:
                info["single_precision_meshes"] += 1
            shape = rhino_mesh_shape(geometry)
        else:
            continue
        shapes.setdefault(guid, []).append(shape)
    return shapes, info


def rhino_mesh_shape(mesh) -> Shape:
    vertices = mesh.Vertices
    points = numpy.array([(p.X, p.Y, p.Z) for p in (vertices.Point3dAt(i) for i in range(len(vertices)))])
    faces = mesh.Faces
    triangles = []
    for i in range(len(faces)):
        a, b, c, d = faces[i]
        triangles.append((a, b, c))
        if c != d:
            triangles.append((a, c, d))
    return mesh_shape(points, numpy.array(triangles))


def brep_shape(brep) -> Shape:
    """Area, volume and plane deviation of a planar polysurface, from its faces' trim loops."""
    vertices = brep.Vertices
    points = numpy.array([(p.X, p.Y, p.Z) for p in (vertices[i].Location for i in range(len(vertices)))])
    origin = points.min(axis=0) if len(points) else numpy.zeros(3)
    area = volume = deviation = 0.0
    faces = brep.Faces
    for fi in range(len(faces)):
        face = faces[fi]
        (u0, u1), (v0, v1) = _interval(face.Domain(0)), _interval(face.Domain(1))
        u, v = (u0 + u1) / 2, (v0 + v1) / 2
        p0 = face.PointAt(u, v)
        n = face.NormalAt(u, v)
        normal = numpy.array((n.X, n.Y, n.Z))
        base = numpy.array((p0.X, p0.Y, p0.Z)) - origin
        net = numpy.zeros(3)
        for loop in face.Loops:
            indices = [trim.StartVertexIndex for trim in loop.Trims]
            loop_points = points[indices] - origin
            net += _newell(loop_points)
            deviation = max(deviation, float(numpy.abs((loop_points - base) @ normal).max()))
        # The loops run counter-clockwise around the surface normal, holes clockwise; a reversed
        # face points the other way.
        signed = float(net @ normal) / 2
        outward = -1.0 if face.OrientationIsReversed else 1.0
        area += abs(signed)
        volume += outward * float(base @ normal) * signed / 3
    return Shape(points, None, area, volume, deviation, {"brep"})


def _interval(interval) -> tuple[float, float]:
    return interval.T0, interval.T1


def _newell(loop: numpy.ndarray) -> numpy.ndarray:
    """Newell's vector of a closed polygon: its normal, twice its area long."""
    nxt = numpy.roll(loop, -1, axis=0)
    return numpy.array([
        ((loop[:, 1] - nxt[:, 1]) * (loop[:, 2] + nxt[:, 2])).sum(),
        ((loop[:, 2] - nxt[:, 2]) * (loop[:, 0] + nxt[:, 0])).sum(),
        ((loop[:, 0] - nxt[:, 0]) * (loop[:, 1] + nxt[:, 1])).sum(),
    ])


def read_glb(path: Path, wanted: set[str]) -> tuple[dict[str, list[Shape]], dict]:
    """Meshes of a binary glTF, placed by their node matrices in double precision, back in Z-up."""
    data = path.read_bytes()
    magic, _, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise OSError(f"not a GLB file: {path}")
    json_length, = struct.unpack_from("<I", data, 12)
    gltf = json.loads(data[20:20 + json_length])
    binary_start = 20 + json_length + 8
    accessors, views = gltf.get("accessors", []), gltf.get("bufferViews", [])
    # Single precision rounds by up to 0.12 mm beyond 2048 m (half its 2.4e-4 m spacing there).
    info = {"max_local_coordinate": 0.0, "max_translation": 0.0, "far_local_meshes": 0}
    for mesh in gltf.get("meshes", []):
        extent = max(
            (max(abs(c) for c in accessors[p["attributes"]["POSITION"]].get("min", [0]) + accessors[p["attributes"]["POSITION"]].get("max", [0]))
             for p in mesh["primitives"]), default=0.0,
        )
        info["max_local_coordinate"] = max(info["max_local_coordinate"], extent)
        info["far_local_meshes"] += extent > 2048.0
    dtypes = {5120: numpy.int8, 5121: numpy.uint8, 5122: numpy.int16, 5123: numpy.uint16, 5125: numpy.uint32, 5126: numpy.float32}
    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def accessor(index: int) -> numpy.ndarray:
        acc = accessors[index]
        view = views[acc["bufferView"]]
        dtype = numpy.dtype(dtypes[acc["componentType"]])
        width = widths[acc["type"]]
        start = binary_start + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride") or dtype.itemsize * width
        if stride == dtype.itemsize * width:
            return numpy.frombuffer(data, dtype, acc["count"] * width, start).reshape(-1, width)
        raw = numpy.frombuffer(data, numpy.uint8, stride * (acc["count"] - 1) + dtype.itemsize * width, start)
        rows = numpy.lib.stride_tricks.as_strided(raw, (acc["count"], dtype.itemsize * width), (stride, 1))
        return rows.copy().view(dtype).reshape(-1, width)

    # glTF is Y-up: (x, y, z) in the file is (x, z, -y) in IFC.
    to_z_up = numpy.array([[1.0, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
    shapes: dict[str, list[Shape]] = {}
    nodes = gltf.get("nodes", [])
    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)] if gltf.get("scenes") else {"nodes": list(range(len(nodes)))}
    stack = [(index, to_z_up) for index in scene.get("nodes", [])]
    while stack:
        index, parent = stack.pop()
        node = nodes[index]
        matrix = parent @ _node_matrix(node)
        stack.extend((child, matrix) for child in node.get("children", []))
        if "mesh" not in node:
            continue
        info["max_translation"] = max(info["max_translation"], float(numpy.abs(matrix[:3, 3]).max()))
        match = _GUID_IN_NAME.search(node.get("name", ""))
        guid = _compress(match.group(1)) if match else None
        if guid not in wanted:
            continue
        for primitive in gltf["meshes"][node["mesh"]]["primitives"]:
            if primitive.get("mode", 4) != 4:  # lines and points (alignment axes) have no surface
                continue
            local = accessor(primitive["attributes"]["POSITION"]).astype(numpy.float64)
            points = local @ matrix[:3, :3].T + matrix[:3, 3]
            if "indices" in primitive:
                triangles = accessor(primitive["indices"]).astype(numpy.int64).reshape(-1, 3)
            else:
                triangles = numpy.arange(len(points)).reshape(-1, 3)
            shapes.setdefault(guid, []).append(mesh_shape(points, triangles))
    return shapes, info


def _node_matrix(node: dict) -> numpy.ndarray:
    if "matrix" in node:
        return numpy.array(node["matrix"], dtype=numpy.float64).reshape(4, 4).T  # column-major
    matrix = numpy.eye(4)
    if "scale" in node:
        matrix = numpy.diag([*node["scale"], 1.0]) @ matrix
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        rotation = numpy.eye(4)
        rotation[:3, :3] = [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
        matrix = rotation @ matrix
    if "translation" in node:
        translation = numpy.eye(4)
        translation[:3, 3] = node["translation"]
        matrix = translation @ matrix
    return matrix


def _compress(uuid_text: str) -> str:
    import ifcopenshell.guid

    return ifcopenshell.guid.compress(uuid_text.replace("-", ""))


def read_obj(path: Path, wanted: set[str]) -> tuple[dict[str, list[Shape]], dict]:
    """Groups of an OBJ file, streamed: only the wanted ones are kept."""
    info = {"max_digits": 0}
    shapes: dict[str, list[Shape]] = {}
    count = 0  # vertices so far (OBJ indices are global, 1-based)
    guid, points, first, faces = None, [], 0, []

    def flush():
        if guid is not None and points and faces:
            shapes.setdefault(guid, []).append(mesh_shape(numpy.array(points), numpy.array(faces) - first))

    with open(path, "rb") as stream:
        for line in stream:
            tag = line[:2]
            if tag == b"v ":
                count += 1
                if guid is not None:
                    values = line.split()[1:4]
                    info["max_digits"] = max(info["max_digits"], *(_digits(v) for v in values))
                    points.append([float(v) for v in values])
            elif tag == b"f ":
                if guid is not None:
                    corners = [int(c.split(b"/")[0]) - 1 for c in line.split()[1:]]
                    faces.extend((corners[0], corners[k], corners[k + 1]) for k in range(1, len(corners) - 1))
            elif tag == b"g ":
                flush()
                match = _GUID_IN_NAME.search(line.decode("utf-8", "replace"))
                candidate = _compress(match.group(1)) if match else None
                guid = candidate if candidate in wanted else None
                points, first, faces = [], count, []
    flush()
    return shapes, info


def _digits(number: bytes) -> int:
    """Significant digits written for a number."""
    mantissa = number.lstrip(b"-").split(b"e")[0].split(b"E")[0].replace(b".", b"")
    return len(mantissa.lstrip(b"0")) or 1


# ----------------------------------------------------------------------------------- reference


def open_model(path: Path):
    """The IFC model as the converter reads it (units repaired, federated projects merged)."""
    import ifcopenshell

    from ifc_converter.converter import merge_projects, repair_units

    model = ifcopenshell.open(str(path))
    repair_units(model)
    merge_projects(model)
    return model


def candidates(model) -> list:
    """The products every output format contains (the GLB/OBJ selection), with unique GlobalIds."""
    from ifc_converter.converter import EXCLUDED_CLASSES, _has_3d_shape

    products = [
        p for p in model.by_type("IfcProduct")
        if _has_3d_shape(p) and not any(p.is_a(name) for name in EXCLUDED_CLASSES)
    ]
    seen: dict[str, int] = {}
    for p in products:
        seen[p.GlobalId] = seen.get(p.GlobalId, 0) + 1
    return [p for p in products if seen[p.GlobalId] == 1]


def reference_shapes(model, products: list, kernel: str, threads: int, deflection: float | None = None) -> dict[str, Shape]:
    """IfcOpenShell's triangulation of the products in world coordinates, keyed by GlobalId.

    ``kernel`` is a strategy of converter.KERNELS: "accurate" routes the products like the converter.
    """
    import ifcopenshell.geom as geom

    from ifc_converter.converter import LIBRARIES, LINEAR_DEFLECTION, _triangle_mesh_only

    if kernel == "accurate":
        fast = [p for p in products if _triangle_mesh_only(p)]
        ids = {p.id() for p in fast}
        shapes = reference_shapes(model, fast, "hybrid", threads, deflection)
        shapes.update(reference_shapes(model, [p for p in products if p.id() not in ids], "opencascade", threads, deflection))
        return shapes

    settings = geom.settings()
    settings.set("use-world-coords", True)
    settings.set("weld-vertices", False)
    # The converter's tessellation, so the reference triangles match the output's.
    settings.set("mesher-linear-deflection", deflection or LINEAR_DEFLECTION)
    shapes: dict[str, Shape] = {}
    with _quiet_stdout():
        for start in range(0, len(products), 200):
            chunk = products[start:start + 200]
            iterator = geom.iterator(settings, model, threads, include=chunk, geometry_library=LIBRARIES[kernel])
            if not iterator.initialize():
                continue
            while True:
                shape = iterator.get()
                geometry = shape.geometry
                if geometry.verts and geometry.faces:
                    element = model.by_id(shape.id)
                    shapes[element.GlobalId] = mesh_shape(
                        numpy.frombuffer(geometry.verts_buffer, numpy.float64),
                        numpy.frombuffer(geometry.faces_buffer, numpy.int32),
                    )
                if not iterator.next():
                    break
            del iterator
    return shapes


class _quiet_stdout:
    """The geometry kernels print debug text to the C-level stdout."""

    def __enter__(self):
        sys.stdout.flush()
        self.saved = os.dup(1)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.close(devnull)

    def __exit__(self, *exc):
        sys.stdout.flush()
        os.dup2(self.saved, 1)
        os.close(self.saved)


# -------------------------------------------------------------------------------- ground truth


@dataclass
class Expectation:
    """Dimensions of an element known from the IFC values alone (metres)."""

    volume: float  # sum of the extrusions' volumes
    corners: numpy.ndarray | None  # vertices the output must contain (polygonal profiles)
    curved: bool  # some profile is round: the volume shrinks by the tessellation
    # Round extrusions: (matrix to the solid's frame in metres, profile centre x, y, radius, depth)
    circles: list = field(default_factory=list)


def _profile(profile) -> tuple[float, list | None, list] | None:
    """Area (project units²), polygon corners in profile coordinates and round parts (circles as
    (x, y, r), None for fillets); None if unsupported."""
    kind = profile.is_a()
    position = getattr(profile, "Position", None)
    m = numpy.eye(3)
    if position is not None:
        origin = position.Location.Coordinates
        x = numpy.array(position.RefDirection.DirectionRatios[:2], dtype=float) if position.RefDirection else numpy.array([1.0, 0.0])
        x /= numpy.linalg.norm(x)
        m[:2, 0], m[:2, 1], m[:2, 2] = x, (-x[1], x[0]), origin[:2]

    def placed(points):
        return [tuple((m @ (px, py, 1.0))[:2]) for px, py in points]

    if kind == "IfcRectangleProfileDef":
        a, b = profile.XDim / 2, profile.YDim / 2
        return profile.XDim * profile.YDim, placed([(-a, -b), (a, -b), (a, b), (-a, b)]), []
    if kind == "IfcRoundedRectangleProfileDef":
        return profile.XDim * profile.YDim - (4 - math.pi) * profile.RoundingRadius ** 2, None, [None]
    if kind == "IfcRectangleHollowProfileDef":
        x, y, t = profile.XDim, profile.YDim, profile.WallThickness
        outer, inner = profile.OuterFilletRadius or 0.0, profile.InnerFilletRadius or 0.0
        area = x * y - (4 - math.pi) * outer ** 2 - ((x - 2 * t) * (y - 2 * t) - (4 - math.pi) * inner ** 2)
        return area, None, [None] if outer or inner else []
    if kind == "IfcCircleProfileDef":
        cx, cy = placed([(0.0, 0.0)])[0]
        return math.pi * profile.Radius ** 2, None, [(cx, cy, profile.Radius)]
    if kind == "IfcCircleHollowProfileDef":
        cx, cy = placed([(0.0, 0.0)])[0]
        r, t = profile.Radius, profile.WallThickness
        return math.pi * (r * r - (r - t) ** 2), None, [(cx, cy, r)]
    if kind == "IfcIShapeProfileDef":
        if getattr(profile, "FlangeEdgeRadius", None) or getattr(profile, "FlangeSlope", None):
            return None
        b, h, tw, tf = profile.OverallWidth, profile.OverallDepth, profile.WebThickness, profile.FlangeThickness
        r = profile.FilletRadius or 0.0
        return 2 * b * tf + (h - 2 * tf) * tw + (4 - math.pi) * r * r, None, [None] if r else []
    if kind in ("IfcArbitraryClosedProfileDef", "IfcArbitraryProfileDefWithVoids"):
        outer = _polygon(profile.OuterCurve)
        if outer is None:
            return None
        area = abs(_shoelace(outer))
        corners = list(outer)
        for curve in getattr(profile, "InnerCurves", None) or ():
            inner = _polygon(curve)
            if inner is None:
                return None
            area -= abs(_shoelace(inner))
            corners += inner
        return area, corners, []
    return None


def _polygon(curve) -> list | None:
    """The points of a closed polygon given as IfcPolyline or straight-only IfcIndexedPolyCurve."""
    if curve.is_a("IfcPolyline"):
        points = [tuple(p.Coordinates[:2]) for p in curve.Points]
    elif curve.is_a("IfcIndexedPolyCurve"):
        coords = [tuple(c[:2]) for c in curve.Points.CoordList]
        if curve.Segments:
            if any(not s.is_a("IfcLineIndex") for s in curve.Segments):
                return None
            indices = [i for s in curve.Segments for i in s.wrappedValue]
            points = [coords[i - 1] for i in indices]
        else:
            points = coords
    else:
        return None
    unique = []
    for p in points:
        if not unique or numpy.hypot(p[0] - unique[-1][0], p[1] - unique[-1][1]) > 1e-12:
            unique.append(p)
    if len(unique) > 1 and numpy.hypot(unique[0][0] - unique[-1][0], unique[0][1] - unique[-1][1]) <= 1e-12:
        unique.pop()
    return unique if len(unique) >= 3 else None


def _shoelace(points) -> float:
    return 0.5 * sum(points[k - 1][0] * points[k][1] - points[k][0] * points[k - 1][1] for k in range(len(points)))


def expectations(model, products: list) -> dict[str, Expectation]:
    """Elements made only of supported extrusions without openings, with what their geometry must be."""
    import ifcopenshell.util.placement as placement
    import ifcopenshell.util.unit as unit_util

    scale = unit_util.calculate_unit_scale(model)
    result: dict[str, Expectation] = {}
    for product in products:
        if getattr(product, "HasOpenings", None) or getattr(product, "HasProjections", None):
            continue
        if product.is_a("IfcElement") and any(rel.is_a("IfcRelVoidsElement") for rel in getattr(product, "HasOpenings", []) or []):
            continue
        bodies = [
            r for r in product.Representation.Representations
            if r.RepresentationIdentifier == "Body" and r.Items
        ]
        if len(bodies) != 1:
            continue
        items = []  # (extrusion, matrix of the mapped item or identity)
        supported = True
        for item in bodies[0].Items:
            if item.is_a("IfcMappedItem"):
                matrix = placement.get_mappeditem_transformation(item)
                inner = item.MappingSource.MappedRepresentation.Items
                if matrix is None or any(not i.is_a("IfcExtrudedAreaSolid") for i in inner):
                    supported = False
                    break
                items.extend((i, matrix) for i in inner)
            elif item.is_a("IfcExtrudedAreaSolid"):
                items.append((item, numpy.eye(4)))
            else:
                supported = False
                break
        if not supported or not items or product.ObjectPlacement is None:
            continue
        place = placement.get_local_placement(product.ObjectPlacement)
        volume, corners, curved, circles, polygonal = 0.0, [], False, [], True
        for solid, mapped in items:
            profile = _profile(solid.SweptArea)
            if profile is None:
                supported = False
                break
            area, outline, round_parts = profile
            direction = numpy.array(solid.ExtrudedDirection.DirectionRatios, dtype=float)
            direction /= numpy.linalg.norm(direction)
            position = placement.get_axis2placement(solid.Position) if solid.Position else numpy.eye(4)
            matrix = place @ mapped @ position
            linear = matrix[:3, :3]
            volume += area * solid.Depth * abs(direction[2]) * abs(numpy.linalg.det(linear)) * scale ** 3
            if outline is None:
                polygonal = False
            else:
                for x, y in outline:
                    for z in (0.0, solid.Depth):
                        p = numpy.array((x, y, 0.0)) + direction * z
                        corners.append((matrix @ (*p, 1.0))[:3] * scale)
            if round_parts:
                curved = True
                orthonormal = numpy.allclose(linear.T @ linear, numpy.eye(3), atol=1e-9)
                if orthonormal and numpy.allclose(direction, (0.0, 0.0, 1.0)):
                    to_metres = matrix.copy()
                    to_metres[:3, 3] *= scale
                    for cx, cy, r in filter(None, round_parts):
                        circles.append((numpy.linalg.inv(to_metres), cx * scale, cy * scale, r * scale, solid.Depth * scale))
        if supported and volume > 0:
            # Corners only where every profile is a polygon: the output has no other vertices then.
            result[product.GlobalId] = Expectation(volume, numpy.array(corners) if polygonal else None, curved, circles)
    return result


def chord_error(shape: Shape, circle) -> tuple[float, float] | None:
    """For a round extrusion: the largest distance of a chord from the true circle and of a vertex from it (m)."""
    inverse, cx, cy, r, depth = circle
    local = shape.points @ inverse[:3, :3].T + inverse[:3, 3]
    rho = numpy.hypot(local[:, 0] - cx, local[:, 1] - cy)
    on = (numpy.abs(rho - r) < 0.05 * r) & (local[:, 2] > -1e-6) & (local[:, 2] < depth + 1e-6)
    if on.sum() < 6:
        return None
    angles = numpy.unique(numpy.round(numpy.arctan2(local[on, 1] - cy, local[on, 0] - cx), 9))
    if len(angles) < 3:
        return None
    gaps = numpy.diff(numpy.concatenate([angles, angles[:1] + 2 * math.pi]))
    return r * (1 - math.cos(gaps.max() / 2)), float(numpy.abs(rho[on] - r).max())


def door_window_dimensions(model, products: list) -> dict[str, tuple[str, float, float, numpy.ndarray]]:
    """Doors and windows with OverallWidth and OverallHeight: (class, width, height, inverse placement), metres."""
    import ifcopenshell.util.placement as placement
    import ifcopenshell.util.unit as unit_util

    scale = unit_util.calculate_unit_scale(model)
    result = {}
    for product in products:
        if not (product.is_a("IfcDoor") or product.is_a("IfcWindow")) or product.ObjectPlacement is None:
            continue
        width, height = getattr(product, "OverallWidth", None), getattr(product, "OverallHeight", None)
        if not width or not height:
            continue
        matrix = placement.get_local_placement(product.ObjectPlacement)
        matrix[:3, 3] *= scale
        result[product.GlobalId] = (product.is_a(), width * scale, height * scale, numpy.linalg.inv(matrix))
    return result


def quantity_volumes(model, products: list) -> dict[str, float]:
    """NetVolume (else GrossVolume) of the standard quantity sets, in m³."""
    import ifcopenshell.util.element as element_util
    import ifcopenshell.util.unit as unit_util

    scale = unit_util.calculate_unit_scale(model, "VOLUMEUNIT")
    result = {}
    for product in products:
        try:
            qtos = element_util.get_psets(product, qtos_only=True)
        except Exception:
            continue
        for name, values in qtos.items():
            if not (name.startswith("Qto_") or name == "BaseQuantities"):
                continue
            value = values.get("NetVolume") or values.get("GrossVolume")
            if isinstance(value, (int, float)) and value > 0:
                result[product.GlobalId] = value * scale
                break
    return result


# ----------------------------------------------------------------------------------- the checks


def check_file(source: Path, modes: list[str], out_dir: Path, sample: int, threads: int,
               keep: bool = False, deflection: float | None = None, log=None, occ_sample: int = DEFAULT_OCC_SAMPLE) -> dict:
    """Convert ``source`` in every mode and measure the outputs against reference and ground truth."""
    from ifc_converter.converter import DEFAULT_KERNEL

    log = log or (lambda text: print(text, flush=True))
    kernel = os.environ.get("IFC_CONVERTER_KERNEL", DEFAULT_KERNEL).lower()
    report: dict = {"file": source.name, "size_mb": round(source.stat().st_size / 1e6, 1), "modes": {}, "kernel": kernel}
    started = time.time()
    model = open_model(source)
    report.update(model_facts(model))
    products = candidates(model)
    report["mirrored_types"] = sum(map(is_mirrored, products))
    rng = random.Random(0)
    chosen = rng.sample(products, min(sample, len(products)))
    truths = expectations(model, products)
    doors = door_window_dimensions(model, products)
    qtos = quantity_volumes(model, products)
    extra_ids = list(truths)[:GROUND_TRUTH_SAMPLE] + list(doors)[:GROUND_TRUTH_SAMPLE // 2]
    by_guid = {p.GlobalId: p for p in products}
    chosen_ids = {p.GlobalId for p in chosen}
    chosen += [by_guid[g] for g in rng.sample(extra_ids, len(extra_ids)) if g not in chosen_ids]
    wanted = {p.GlobalId for p in chosen}
    log(f"  {len(products)} elements, {len(wanted)} compared ({sum(g in wanted for g in truths)} with known dimensions)")

    references = {}
    for name in dict.fromkeys((kernel, "opencascade")):
        t = time.time()
        subset = chosen if name == kernel else random.Random(1).sample(chosen, min(occ_sample, len(chosen)))
        references[name] = reference_shapes(model, subset, name, threads, deflection)
        log(f"  reference {name}: {len(references[name])} shapes in {time.time() - t:.0f} s")
    if kernel != "opencascade":
        # The converter redoes the elements the hybrid kernel cannot build with OpenCASCADE.
        missing = [p for p in chosen if p.GlobalId not in references[kernel] and p.GlobalId not in references["opencascade"]]
        references["opencascade"].update(reference_shapes(model, missing, "opencascade", threads, deflection))
    same = dict(references["opencascade"])
    same.update(references[kernel])
    report["kernel_vs_opencascade"] = summarize(
        {g: compare(s, references["opencascade"][g]) for g, s in references[kernel].items() if g in references["opencascade"]}
    )
    report["reference_ground_truth"] = ground_truth(same, truths, doors, qtos)
    # Entity instances keep the whole model in memory; only class names are needed from here on.
    classes = {p.GlobalId: p.is_a() for p in chosen}
    del model, products, chosen, by_guid
    import gc

    from ifc_converter.converter import _release_memory

    gc.collect()
    _release_memory()  # the conversions run in children: hand the model's memory back meanwhile

    for mode in modes:
        fmt, geometry = MODES[mode]
        output = out_dir / f"{source.stem}.{mode}.{fmt}"
        log(f"  ▶ {mode}")
        try:
            result = convert_in_child(source, fmt, geometry, output, threads, deflection)
            entry = {"seconds": result.get("seconds"), "status": result["status"]}
            if result["status"] == "ok":
                entry["output_mb"] = round(sum(p.stat().st_size for p in (output, output.with_suffix(".mtl")) if p.exists()) / 1e6, 1)
                shapes, info = read_output(output, fmt, wanted)
                entry["info"] = info
                entry["missing"] = sorted(g for g in same if g not in shapes)[:20]
                entry["missing_count"] = sum(g not in shapes for g in same)
                comparisons = {g: compare(s, same[g]) for g, s in shapes.items() if g in same}
                entry["vs_same_kernel"] = summarize(comparisons)
                entry["vs_opencascade"] = summarize(
                    {g: compare(s, references["opencascade"][g]) for g, s in shapes.items() if g in references["opencascade"]}
                )
                entry["ground_truth"] = ground_truth(shapes, truths, doors, qtos)
                entry["classes"] = _worst_classes(comparisons, classes)
            else:
                entry["error"] = result.get("error")
            report["modes"][mode] = entry
        except Exception as exc:  # a reader problem must not lose the other modes
            report["modes"][mode] = {"status": "error", "error": f"checking: {type(exc).__name__}: {exc}"}
        finally:
            if not keep:
                for path in (output, output.with_suffix(".mtl")):
                    path.unlink(missing_ok=True)
    report["seconds"] = round(time.time() - started)
    return report


def is_mirrored(product) -> bool:
    """Whether the product's body places type geometry mirrored (IfcOpenShell leaves it inside out)."""
    import ifcopenshell.util.placement as placement

    def determinants(representation, sign=1.0, depth=0):
        for item in representation.Items:
            if item.is_a("IfcMappedItem") and depth < 8:
                matrix = placement.get_mappeditem_transformation(item)
                if matrix is not None:
                    yield from determinants(item.MappingSource.MappedRepresentation, sign * numpy.linalg.det(matrix[:3, :3]), depth + 1)
            else:
                yield sign

    for representation in product.Representation.Representations:
        if representation.RepresentationIdentifier == "Body" and any(d < 0 for d in determinants(representation)):
            return True
    return False


def model_facts(model) -> dict:
    """Schema, units and georeferencing of the model."""
    import ifcopenshell.util.unit as unit_util

    facts = {"schema": model.schema, "length_unit_m": unit_util.calculate_unit_scale(model)}
    names = []
    for assignment in model.by_type("IfcUnitAssignment"):
        for unit in assignment.Units:
            if getattr(unit, "UnitType", None) == "LENGTHUNIT":
                names.append(f"{getattr(unit, 'Prefix', None) or ''}{unit.Name}")
    facts["length_units"] = sorted(set(names))
    facts["projects"] = len(model.by_type("IfcProject"))
    try:
        conversions = model.by_type("IfcMapConversion")
    except RuntimeError:
        conversions = []
    facts["map_conversion"] = [
        {"eastings": c.Eastings, "northings": c.Northings, "height": c.OrthogonalHeight,
         "x_axis": (c.XAxisAbscissa, c.XAxisOrdinate), "scale": c.Scale,
         "crs": getattr(c.TargetCRS, "Name", None)}
        for c in conversions
    ]
    sites = model.by_type("IfcSite")
    facts["ref_latitude"] = [list(s.RefLatitude) if s.RefLatitude else None for s in sites][:3]
    return facts


def ground_truth(shapes: dict[str, Shape], truths: dict[str, Expectation], doors: dict, qtos: dict) -> dict:
    """Output geometry against the dimensions known from the IFC (metres, millimetres where noted)."""
    corner, planar, curved, chords, on_circle = [], [], [], [], []
    for guid, truth in truths.items():
        shape = shapes.get(guid)
        if shape is None:
            continue
        if truth.corners is not None and len(shape.points):
            # Every output vertex must be one of the expected corners (polysurfaces may leave out
            # corners on straight edges), and the bounding boxes must match.
            corners = truth.corners
            d = max(float(numpy.sqrt(((corners - p) ** 2).sum(axis=1)).min()) for p in _sample(shape.points))
            box = float(numpy.abs(shape.bbox - numpy.concatenate([corners.min(axis=0), corners.max(axis=0)])).max())
            corner.append((max(d, box) * 1000, guid))
        offset = abs(abs(shape.volume) - truth.volume) / shape.area * 1000 if shape.area else math.nan
        (curved if truth.curved else planar).append((offset, guid))
        for circle in truth.circles:
            error = chord_error(shape, circle)
            if error:
                chords.append((error[0] * 1000, guid))
                on_circle.append((error[1] * 1000, guid))
    widths, heights = [], []
    for guid, (_, width, height, inverse) in doors.items():
        shape = shapes.get(guid)
        if shape is None:
            continue
        local = shape.points @ inverse[:3, :3].T + inverse[:3, 3]
        extent = local.max(axis=0) - local.min(axis=0)
        widths.append(extent[0] / width)
        heights.append(extent[2] / height)
    ratios = [abs(shapes[g].volume) / v for g, v in qtos.items() if g in shapes]

    def stats(values):
        values = [v for v in values if not math.isnan(v[0])]
        if not values:
            return None
        numbers = numpy.array([v for v, _ in values])
        worst = max(values)
        return {"n": len(values), "max": float(numbers.max()), "p95": float(numpy.percentile(numbers, 95)), "worst": worst[1]}

    def ratio_stats(values):
        if not values:
            return None
        values = numpy.array(values)
        return {"n": len(values), "median": float(numpy.median(values)),
                "within_1pct": float((numpy.abs(values - 1) <= 0.01).mean()),
                "within_5pct": float((numpy.abs(values - 1) <= 0.05).mean())}

    return {
        "corners_mm": stats(corner), "volume_planar_mm": stats(planar), "volume_curved_mm": stats(curved),
        "chord_mm": stats(chords), "vertex_on_circle_mm": stats(on_circle),
        "door_width_ratio": ratio_stats(widths), "door_height_ratio": ratio_stats(heights),
        "door_width_m_median": float(numpy.median([doors[g][1] for g in doors])) if doors else None,
        "qto_volume_ratio": ratio_stats(ratios),
    }


def _sample(points: numpy.ndarray, limit: int = MAX_QUERY_VERTICES) -> numpy.ndarray:
    if len(points) <= limit:
        return points
    return points[numpy.random.default_rng(0).choice(len(points), limit, replace=False)]


def summarize(comparisons: dict[str, dict]) -> dict:
    """Max and 95th percentile of each deviation, with the GlobalId of the worst element."""
    summary: dict = {
        "n": len(comparisons),
        "inverted": sum(c["inverted"] for c in comparisons.values()),
        "reference_inverted": sum(c.get("reference_inverted", False) for c in comparisons.values()),
        "inverted_examples": [g for g, c in comparisons.items() if c["inverted"]][:5],
    }
    for key in ("bbox_mm", "vertex_mm", "area_rel", "volume_mm", "plane_mm"):
        values = [(c[key], g) for g, c in comparisons.items() if key in c and not math.isnan(c[key])]
        if values:
            numbers = numpy.array([v for v, _ in values])
            summary[key] = {"max": float(numbers.max()), "p95": float(numpy.percentile(numbers, 95)), "worst": max(values)[1]}
    return summary


def _worst_classes(comparisons: dict[str, dict], classes: dict[str, str]) -> dict:
    """The largest vertex deviation per IFC class (mm)."""
    worst: dict[str, float] = {}
    for guid, comparison in comparisons.items():
        value = comparison["vertex_mm"]
        if not math.isnan(value):
            worst[classes[guid]] = max(worst.get(classes[guid], 0.0), value)
    return dict(sorted(worst.items(), key=lambda kv: -kv[1])[:8])


# ------------------------------------------------------------------------------------ conversion


def convert_in_child(source: Path, fmt: str, geometry: str, output: Path, threads: int, deflection: float | None) -> dict:
    for stale in (output, output.with_suffix(".mtl")):
        stale.unlink(missing_ok=True)
    command = [sys.executable, __file__, "--child", str(source), fmt, geometry, str(output), "--threads", str(threads)]
    if deflection:
        command += ["--deflection", str(deflection)]
    started = time.time()
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    seconds = round(time.time() - started, 1)
    lines = [line for line in process.stdout.splitlines() if line.startswith("{")]
    if process.returncode == 0 and lines:
        return {"status": "ok", "seconds": seconds, **json.loads(lines[-1])}
    return {"status": "error", "seconds": seconds, "error": (process.stderr.strip().splitlines() or ["?"])[-1][:300]}


def _child(source: str, fmt: str, geometry: str, output: str, threads: int, deflection: float | None) -> int:
    import ifcopenshell.geom as geom

    if deflection:
        # The converter creates its settings with geom.settings(); give them the finer tessellation.
        original = geom.settings

        class settings(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.set("mesher-linear-deflection", deflection)

        geom.settings = settings
    from ifc_converter import convert

    with _quiet_stdout():
        result = convert(source, output, fmt=fmt, geometry=geometry, threads=threads)
    print(json.dumps({"elements": result.elements, "skipped": result.skipped}), flush=True)
    return 0


# ---------------------------------------------------------------------------------------- report


def write_report(reports: list[dict], path: Path) -> None:
    lines = [
        "# Dimensional accuracy",
        "",
        "Deviations in millimetres (area: relative). *vertex*: largest distance of an output vertex from the",
        "reference surface; *bbox*: largest difference of a bounding box coordinate; *ΔV/A*: volume difference",
        "divided by the surface area (how far the surface moved on average); *plane*: brep vertices off their",
        "face plane. Reference: IfcOpenShell in world coordinates, double precision.",
        "",
    ]
    for r in reports:
        if "error" in r:
            lines += [f"## {r['file']}", "", f"Failed: {r['error']}", ""]
            continue
        mc = "; ".join(
            f"E {c['eastings']} N {c['northings']} H {c['height']} scale {c['scale']} ({c['crs']})" for c in r["map_conversion"]
        ) or "none"
        lines += [
            f"## {r['file']} ({r['size_mb']} MB, {r['schema']}, unit {', '.join(r['length_units']) or '?'} = {r['length_unit_m']:g} m)",
            "",
            f"Projects: {r['projects']}. IfcMapConversion: {mc}. Mirrored type instances: {r.get('mirrored_types', '?')}. "
            f"Kernel: {r['kernel']}. Checked in {r['seconds']} s.",
            "",
            "| Mode | Elements | Missing | vertex max / p95 | bbox max / p95 | area max / p95 | ΔV/A max / p95 | plane max | inside out (ref) | vs OCC vertex max / p95 | Output |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        k = r["kernel_vs_opencascade"]
        lines.append(
            f"| {r['kernel']} reference vs OCC | {k['n']} | | {_pair(k, 'vertex_mm')} | {_pair(k, 'bbox_mm')} | "
            f"{_pair(k, 'area_rel', pct=True)} | {_pair(k, 'volume_mm')} | | {k['inverted']} ({k['reference_inverted']}) | | |"
        )
        for mode, e in r["modes"].items():
            if e["status"] != "ok":
                lines.append(f"| {mode} | failed: {e.get('error')} |||||||||| ")
                continue
            s, o = e["vs_same_kernel"], e["vs_opencascade"]
            plane = f"{s['plane_mm']['max']:.4f}" if "plane_mm" in s else ""
            lines.append(
                f"| {mode} | {s['n']} | {e['missing_count']} | {_pair(s, 'vertex_mm')} | {_pair(s, 'bbox_mm')} | "
                f"{_pair(s, 'area_rel', pct=True)} | {_pair(s, 'volume_mm')} | {plane} | {s['inverted']} ({s['reference_inverted']}) | "
                f"{_pair(o, 'vertex_mm')} | {e['output_mb']} MB, {e['seconds']} s |"
            )
        lines += ["", "Ground truth from the IFC values:", "",
                  "| Mode | vertices & bbox vs IFC max (n) | ΔV/A planar max / p95 (n) | ΔV/A round max (n) | chord max (n) | door width ratio | door height ratio | Qto volume ratio |",
                  "|---|---|---|---|---|---|---|---|"]
        rows = [("reference", r["reference_ground_truth"])] + [
            (mode, e["ground_truth"]) for mode, e in r["modes"].items() if e["status"] == "ok"
        ]
        for mode, g in rows:
            lines.append(
                f"| {mode} | {_gt(g['corners_mm'])} | {_gt(g['volume_planar_mm'], p95=True)} | {_gt(g['volume_curved_mm'])} | "
                f"{_gt(g['chord_mm'])} | {_ratio(g['door_width_ratio'])} | {_ratio(g['door_height_ratio'])} | {_ratio(g['qto_volume_ratio'])} |"
            )
        g = r["reference_ground_truth"]
        if g.get("door_width_m_median"):
            lines += ["", f"Median door/window OverallWidth: {g['door_width_m_median']:.3f} m."]
        infos = {mode: e.get("info") for mode, e in r["modes"].items() if e.get("info")}
        if infos:
            lines += ["", "Output facts: " + "; ".join(f"{m}: {json.dumps(i)}" for m, i in infos.items())]
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pair(summary: dict, key: str, pct: bool = False) -> str:
    if key not in summary:
        return "–"
    v = summary[key]
    if pct:
        return f"{v['max'] * 100:.3g} % / {v['p95'] * 100:.2g} %"
    return f"{v['max']:.4g} / {v['p95']:.2g}"


def _gt(stats: dict | None, p95: bool = False) -> str:
    if not stats:
        return "–"
    text = f"{stats['max']:.3g} / {stats['p95']:.2g}" if p95 else f"{stats['max']:.3g}"
    return f"{text} ({stats['n']})"


def _ratio(stats: dict | None) -> str:
    if not stats:
        return "–"
    return f"{stats['median']:.4f} ({stats['within_5pct'] * 100:.0f} % ±5 %, n={stats['n']})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--modes", default=",".join(MODES), help=f"comma-separated: {', '.join(MODES)}")
    parser.add_argument("--out-dir", type=Path, default=Path("accuracy-out"))
    parser.add_argument("--report", type=Path, default=Path("accuracy-report.md"))
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE, help="elements compared per file")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--deflection", type=float, help="mesher-linear-deflection in metres for conversion and reference")
    parser.add_argument("--occ-sample", type=int, default=DEFAULT_OCC_SAMPLE, help="elements also compared with OpenCASCADE")
    parser.add_argument("--keep-output", action="store_true")
    parser.add_argument("--from-jsonl", nargs="+", type=Path, help="only write the report from earlier results")
    parser.add_argument("--child", nargs=4, metavar=("IFC", "FMT", "GEOMETRY", "OUT"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    import importlib.util

    if importlib.util.find_spec("ifc_converter") is None:  # not installed: use the source tree
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    if args.child:
        return _child(*args.child, args.threads, args.deflection)
    if args.from_jsonl:
        reports = [json.loads(line) for path in args.from_jsonl for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        write_report(reports, args.report)
        print(f"Report: {args.report}")
        return 0
    if not args.files:
        parser.error("no IFC files given")
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        parser.error(f"unknown mode(s): {', '.join(unknown)}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for source in args.files:
        print(f"▶ {source.name}", flush=True)
        try:
            report = check_file(
                source, modes, args.out_dir, args.sample, args.threads, args.keep_output, args.deflection,
                occ_sample=args.occ_sample,
            )
        except Exception as exc:  # one broken file must not stop the run
            import traceback

            report = {"file": source.name, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-2000:]}
        reports.append(report)
        with open(args.report.with_suffix(".jsonl"), "a", encoding="utf-8") as log:
            log.write(json.dumps(report, default=str) + "\n")
        write_report(reports, args.report)
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
