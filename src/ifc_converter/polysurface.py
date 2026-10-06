"""Joined planar Rhino polysurfaces from IfcOpenShell's triangulated shapes.

The triangles (or any planar polygons with holes) are welded into one closed, consistently
oriented shell per representation item, coplanar neighbours are merged into faces with holes, and
the resulting topology is serialized as an openNURBS Brep record that rhino3dm decodes (rhino3dm
itself cannot build or join polysurfaces).
"""
from __future__ import annotations

import math
import uuid
from collections.abc import Sequence

import rhino3dm

from ifc_converter import on_archive as archive

Point = tuple[float, float, float]
Face = list[list[int]]  # outer loop first, then holes; vertex indices

# Vertices closer than this are merged (metres).
WELD_TOLERANCE = 1e-6
# Polygons that bend out of their plane by more than this are not turned into planar faces.
MAX_PLANE_DEVIATION = 1e-3
# T-junction repair compares naked edges with naked vertices; beyond this many it gets too slow.
MAX_TJUNCTION_VERTICES = 5000

TRIM_BOUNDARY, TRIM_MATED = 1, 2
LOOP_OUTER, LOOP_INNER = 1, 2
NOT_ISO, X_ISO, Y_ISO, W_ISO, S_ISO, E_ISO, N_ISO = range(7)

SQRT_EPSILON = 1.490116119384765625e-8
EPSILON = 2.2204460492503131e-16

_opennurbs_version: int | None = None


def planar_polysurface(
    verts: Sequence[float], faces: Sequence[Sequence[Sequence[int]]], item_ids: Sequence[int] | None = None
) -> rhino3dm.Brep | None:
    """A valid Brep from flat ``verts`` (xyz...) and polygon ``faces`` with holes, or None.

    ``item_ids`` (one per face) keeps touching representation items, e.g. window frame and glass,
    apart as separate closed shells instead of joining them along non-manifold edges.
    """
    points, welded, point_items = _weld(verts, faces, item_ids)
    welded = _split_t_junctions(points, welded, point_items)
    welded = _orient(points, welded)
    if not welded:
        return None
    brep = _decode(points, _merge_coplanar(points, welded))
    if brep is None or not brep.IsValid:
        brep = _decode(points, welded)
    return brep if brep is not None and brep.IsValid else None


def _decode(points: list[Point], faces: list[Face]) -> rhino3dm.Brep | None:
    record = _brep_record(points, faces)
    if record is None:
        return None
    return rhino3dm.Brep.Decode(archive.decode_dict(record, _version()))


def _version() -> int:
    global _opennurbs_version
    if _opennurbs_version is None:
        box = rhino3dm.Brep.CreateFromBoundingBox(rhino3dm.BoundingBox(0, 0, 0, 1, 1, 1))
        _opennurbs_version = box.Encode()["opennurbs"]
    return _opennurbs_version


# ---------------------------------------------------------------------------------------- topology


def _weld(verts, faces, item_ids) -> tuple[list[Point], list[Face], list[int]]:
    """Merge coincident vertices of the same representation item and drop degenerate loops."""
    raw = [(verts[i], verts[i + 1], verts[i + 2]) for i in range(0, len(verts), 3)]
    use_items = item_ids is not None and len(item_ids) == len(faces)
    index: dict[tuple, int] = {}
    points: list[Point] = []
    point_items: list[int] = []
    welded: list[Face] = []
    for fi, face in enumerate(faces):
        item = item_ids[fi] if use_items else 0
        loops = []
        for loop in face:
            mapped = []
            for i in loop:
                p = raw[i]
                key = (item, round(p[0] / WELD_TOLERANCE), round(p[1] / WELD_TOLERANCE), round(p[2] / WELD_TOLERANCE))
                if key not in index:
                    index[key] = len(points)
                    points.append(p)
                    point_items.append(item)
                if not mapped or mapped[-1] != index[key]:
                    mapped.append(index[key])
            while len(mapped) > 1 and mapped[0] == mapped[-1]:
                mapped.pop()
            if len(mapped) >= 3:
                loops.append(mapped)
        if loops:
            welded.append(loops)
    return points, welded, point_items


def _edge_uses(faces: list[Face]) -> dict[tuple[int, int], int]:
    uses: dict[tuple[int, int], int] = {}
    for face in faces:
        for loop in face:
            for k, a in enumerate(loop):
                b = loop[k - 1]
                key = (a, b) if a < b else (b, a)
                uses[key] = uses.get(key, 0) + 1
    return uses


def _split_t_junctions(points: list[Point], faces: list[Face], point_items: list[int]) -> list[Face]:
    """Insert vertices lying inside a naked edge into that edge, so both sides share the edge."""
    naked = [edge for edge, count in _edge_uses(faces).items() if count == 1]
    candidates = sorted({v for edge in naked for v in edge})
    if not naked or len(candidates) > MAX_TJUNCTION_VERTICES:
        return faces
    tolerance = WELD_TOLERANCE / 10
    inserts: dict[tuple[int, int], list[int]] = {}
    for a, b in naked:
        pa, pb = points[a], points[b]
        length = math.dist(pa, pb)
        inside = []
        for v in candidates:
            if v != a and v != b and point_items[v] == point_items[a]:
                da, db = math.dist(pa, points[v]), math.dist(points[v], pb)
                if da > tolerance and db > tolerance and da + db - length < tolerance:
                    inside.append((da, v))
        if inside:
            inserts[(a, b)] = [v for _, v in sorted(inside)]
    if not inserts:
        return faces

    result = []
    for face in faces:
        new_face = []
        for loop in face:
            new_loop = []
            for k, a in enumerate(loop):
                b = loop[(k + 1) % len(loop)]
                new_loop.append(a)
                if (a, b) in inserts:
                    new_loop.extend(inserts[(a, b)])
                elif (b, a) in inserts:
                    new_loop.extend(reversed(inserts[(b, a)]))
            new_face.append(new_loop)
        result.append(new_face)
    return result


def _orient(points: list[Point], faces: list[Face]) -> list[Face]:
    """Outer loop first, holes against it, neighbours consistent, closed shells pointing outwards.

    IfcOpenShell's polygon output guarantees neither which loop is the outer one nor a consistent
    loop direction across faces.
    """
    oriented: list[Face] = []
    for face in faces:
        vectors = [_area_vector(points, loop) for loop in face]
        k = max(range(len(face)), key=lambda j: _dot(vectors[j], vectors[j]))
        normal = vectors[k]
        if _dot(normal, normal) == 0:
            continue
        holes = [
            loop[::-1] if _dot(vector, normal) > 0 else loop
            for j, (loop, vector) in enumerate(zip(face, vectors)) if j != k
        ]
        oriented.append([face[k], *holes])

    # Walk across edges shared by exactly two faces; two uses in the same direction mean one flip.
    uses: dict[tuple[int, int], list[tuple[int, bool]]] = {}
    for fi, face in enumerate(oriented):
        for loop in face:
            for k, a in enumerate(loop):
                b = loop[(k + 1) % len(loop)]
                uses.setdefault((min(a, b), max(a, b)), []).append((fi, a < b))
    neighbours: list[list[tuple[int, bool]]] = [[] for _ in oriented]
    for users in uses.values():
        if len(users) == 2 and users[0][0] != users[1][0]:
            (f, forward_f), (g, forward_g) = users
            neighbours[f].append((g, forward_f == forward_g))
            neighbours[g].append((f, forward_f == forward_g))
    flip: list[bool | None] = [None] * len(oriented)
    shells = []
    for start in range(len(oriented)):
        if flip[start] is not None:
            continue
        flip[start] = False
        stack, shell = [start], [start]
        while stack:
            f = stack.pop()
            for g, same_direction in neighbours[f]:
                if flip[g] is None:
                    flip[g] = flip[f] ^ same_direction
                    stack.append(g)
                    shell.append(g)
        shells.append(shell)
    oriented = [[loop[::-1] for loop in face] if flip[fi] else face for fi, face in enumerate(oriented)]

    # A shell with negative signed volume points inwards.
    for shell in shells:
        volume = 0.0
        for fi in shell:
            area = (0.0, 0.0, 0.0)
            for loop in oriented[fi]:
                area = _add(area, _area_vector(points, loop))
            volume += _dot(points[oriented[fi][0][0]], area)
        if volume < 0:
            for fi in shell:
                oriented[fi] = [loop[::-1] for loop in oriented[fi]]
    return oriented


def _merge_coplanar(points: list[Point], faces: list[Face]) -> list[Face]:
    """Merge edge-connected coplanar faces into one face with holes and drop the collinear vertices
    left on straight edges. Regions whose boundary is not one outer loop plus holes stay unmerged."""
    planes = []
    for face in faces:
        normal = _unit(_area_vector(points, face[0]))
        planes.append((normal, _dot(normal, points[face[0][0]]) if normal else 0.0))

    parent = list(range(len(faces)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    directed: dict[tuple[int, int], list[int]] = {}
    for fi, face in enumerate(faces):
        for loop in face:
            for k, a in enumerate(loop):
                directed.setdefault((a, loop[(k + 1) % len(loop)]), []).append(fi)
    for (a, b), users in directed.items():
        others = directed.get((b, a))
        if len(users) != 1 or not others or len(others) != 1:
            continue
        f, g = users[0], others[0]
        (nf, df), (ng, dg) = planes[f], planes[g]
        if f != g and nf and ng and _dot(nf, ng) > 1 - 1e-9 and abs(df - dg) < WELD_TOLERANCE:
            parent[find(f)] = find(g)

    regions: dict[int, list[int]] = {}
    for fi in range(len(faces)):
        regions.setdefault(find(fi), []).append(fi)

    merged: list[Face] = []
    for members in regions.values():
        face = _region_face(points, [faces[fi] for fi in members], planes[members[0]][0])
        if face is None:
            merged.extend(faces[fi] for fi in members)
        else:
            merged.append(face)

    neighbours: dict[int, set[int]] = {}
    for face in merged:
        for loop in face:
            for k, a in enumerate(loop):
                b = loop[k - 1]
                neighbours.setdefault(a, set()).add(b)
                neighbours.setdefault(b, set()).add(a)
    removable = set()
    for v, around in neighbours.items():
        if len(around) == 2:
            a, b = around
            if math.dist(points[a], points[v]) + math.dist(points[v], points[b]) - math.dist(points[a], points[b]) < 1e-8:
                removable.add(v)
    if not removable:
        return merged
    result = []
    for face in merged:
        loops = [[v for v in loop if v not in removable] for loop in face]
        result.append(loops if all(len(loop) >= 3 for loop in loops) else face)
    return result


def _region_face(points: list[Point], faces: list[Face], normal: Point | None) -> Face | None:
    """The boundary of coplanar faces as one face, or None if it is not a single outer loop plus holes."""
    if len(faces) == 1:
        return faces[0]
    edges = set()
    for face in faces:
        for loop in face:
            for k, a in enumerate(loop):
                edges.add((a, loop[(k + 1) % len(loop)]))
    following: dict[int, int] = {}
    for a, b in edges:
        if (b, a) not in edges:
            if a in following:
                return None  # the boundary touches itself
            following[a] = b
    loops = []
    while following:
        start = next(iter(following))
        loop, v = [start], following.pop(start)
        while v != start:
            if v not in following:
                return None
            loop.append(v)
            v = following.pop(v)
        loops.append(loop)
    outer = [loop for loop in loops if _dot(_area_vector(points, loop), normal) > 0]
    if len(outer) != 1:
        return None
    return [outer[0], *(loop for loop in loops if loop is not outer[0])]


# ---------------------------------------------------------------------------------------- record


def _brep_record(points: list[Point], faces: list[Face]) -> bytes | None:
    """The openNURBS record of a Brep with one plane surface per face and line edges/trims."""
    curves_2d: list[bytes] = []
    curves_3d: list[bytes] = []
    surfaces: list[bytes] = []
    edge_index: dict[tuple[int, int], int] = {}
    edges: list[list] = []  # start, end, trims, length, tolerance
    trims: list[tuple] = []  # curve, edge, start, end, reversed, iso, loop, length
    loops: list[tuple[list[int], int, int]] = []
    brep_faces: list[tuple[list[int], int]] = []
    vertices: dict[int, int] = {}  # point index -> brep vertex index
    vertex_tolerance: dict[int, float] = {}

    for face in faces:
        frame = _face_frame(points, face[0])
        if frame is None:
            continue
        origin, xaxis, yaxis, normal = frame
        deviation = {i: abs(_dot(_sub(points[i], origin), normal)) for loop in face for i in loop}
        if max(deviation.values()) > MAX_PLANE_DEVIATION:
            return None
        uv_loops = [
            [(_dot(_sub(points[i], origin), xaxis), _dot(_sub(points[i], origin), yaxis)) for i in loop]
            for loop in face
        ]
        us = [u for u, _ in uv_loops[0]]
        vs = [v for _, v in uv_loops[0]]
        udomain, vdomain = (min(us), max(us)), (min(vs), max(vs))
        if udomain[0] >= udomain[1] or vdomain[0] >= vdomain[1]:
            continue

        face_index = len(brep_faces)
        surface_index = len(surfaces)
        surfaces.append(archive.plane_surface(origin, xaxis, yaxis, normal, udomain, vdomain))
        loop_indices = []
        for position, (loop, uv) in enumerate(zip(face, uv_loops)):
            outer = position == 0
            if (_signed_area(uv) > 0) != outer:  # outer loops run counter-clockwise, holes clockwise
                loop, uv = loop[::-1], uv[::-1]
            loop_index = len(loops)
            loop_trims = []
            for k, a in enumerate(loop):
                b = loop[(k + 1) % len(loop)]
                key = (a, b) if a < b else (b, a)
                if key not in edge_index:
                    edge_index[key] = len(edges)
                    length = math.dist(points[key[0]], points[key[1]])
                    curves_3d.append(archive.line_curve(points[key[0]], points[key[1]], 0.0, length, 3))
                    edges.append([key[0], key[1], [], length, 0.0])
                edge = edges[edge_index[key]]
                # The trim lies on the plane, the edge runs through the original points.
                edge[4] = max(edge[4], deviation[a], deviation[b])
                for v in (a, b):
                    vertex_tolerance[v] = max(vertex_tolerance.get(v, 0.0), deviation[v])
                edge[2].append(len(trims))
                ua, ub = uv[k], uv[(k + 1) % len(uv)]
                loop_trims.append(len(trims))
                trims.append((
                    len(curves_2d), edge_index[key], a, b, int(a != key[0]),
                    _iso(ua, ub, udomain, vdomain), loop_index, edge[3],
                ))
                curves_2d.append(archive.line_curve((ua[0], ua[1], 0.0), (ub[0], ub[1], 0.0), 0.0, edge[3], 2))
                vertices.setdefault(a, len(vertices))
            loops.append((loop_trims, LOOP_OUTER if outer else LOOP_INNER, face_index))
            loop_indices.append(loop_index)
        brep_faces.append((loop_indices, surface_index))

    if not brep_faces:
        return None

    vertex_points: list[Point] = [points[0]] * len(vertices)
    vertex_edges: list[list[int]] = [[] for _ in vertices]
    for point_index, vertex_index in vertices.items():
        vertex_points[vertex_index] = points[point_index]
    for edge_number, (start, end, *_) in enumerate(edges):
        vertex_edges[vertices[start]].append(edge_number)
        if end != start:
            vertex_edges[vertices[end]].append(edge_number)

    data = archive.class_data().version(3, 3)
    data.chunk(archive.object_array(curves_2d))
    data.chunk(archive.object_array(curves_3d))
    data.chunk(archive.object_array(surfaces))

    chunk = archive.anonymous_chunk().version(1, 0).int(len(vertex_points))
    tolerances = {vertices[i]: tol for i, tol in vertex_tolerance.items()}
    for i, point in enumerate(vertex_points):
        chunk.int(i).point(point).int_array(vertex_edges[i]).double(tolerances.get(i, 0.0))
    data.chunk(chunk)

    chunk = archive.anonymous_chunk().version(1, 0).int(len(edges))
    for i, (start, end, edge_trims, length, tolerance) in enumerate(edges):
        chunk.int(i).int(i).int(0).interval(0.0, length)
        chunk.ints((vertices[start], vertices[end])).int_array(edge_trims).double(tolerance).interval(0.0, length)
    data.chunk(chunk)

    chunk = archive.anonymous_chunk().version(1, 0).int(len(trims))
    for i, (curve, edge, start, end, reversed_3d, iso, loop, length) in enumerate(trims):
        trim_type = TRIM_MATED if len(edges[edge][2]) > 1 else TRIM_BOUNDARY
        chunk.int(i).int(curve).interval(0.0, length).int(edge).ints((vertices[start], vertices[end]))
        chunk.int(reversed_3d).int(trim_type).int(iso).int(loop)
        chunk.doubles((0.0, 0.0)).interval(0.0, length)
        chunk.raw(bytes(32))  # proxy-curve reversal flag and reserved bytes
        chunk.doubles((0.0, 0.0))  # legacy tolerances
    data.chunk(chunk)

    chunk = archive.anonymous_chunk().version(1, 0).int(len(loops))
    for i, (loop_trims, loop_type, face_index) in enumerate(loops):
        chunk.int(i).int_array(loop_trims).int(loop_type).int(face_index)
    data.chunk(chunk)

    chunk = archive.anonymous_chunk().version(1, 2).int(len(brep_faces))
    for i, (loop_indices, surface_index) in enumerate(brep_faces):
        chunk.int(i).int_array(loop_indices).int(surface_index).int(0).int(0)
    for _ in brep_faces:
        chunk.uuid(uuid.uuid4())
    chunk.bool(False)  # no per-face colours
    data.chunk(chunk)

    data.point(tuple(min(p[k] for p in vertex_points) for k in range(3)))
    data.point(tuple(max(p[k] for p in vertex_points) for k in range(3)))
    for _ in range(2):  # no render and analysis meshes: Rhino meshes the faces itself
        data.chunk(archive.anonymous_chunk().raw(bytes(len(brep_faces))))
    data.int(0)  # solid orientation not stored, Rhino computes it
    data.chunk(archive.anonymous_chunk(1, 1).bool(False))  # no region topology
    return archive.write_object(archive.CLASS_BREP, data)


def _face_frame(points: list[Point], outer: list[int]) -> tuple[Point, Point, Point, Point] | None:
    """Origin and orthonormal axes of the plane of ``outer``, with z along its normal."""
    normal = _unit(_area_vector(points, outer))
    if normal is None:
        return None
    origin = points[outer[0]]
    for i in outer[1:]:
        direction = _sub(points[i], origin)
        xaxis = _unit(_sub(direction, _scale(normal, _dot(direction, normal))))
        if xaxis is not None:
            return origin, xaxis, _cross(normal, xaxis), normal
    return None


def _iso(ua: tuple[float, float], ub: tuple[float, float], udomain, vdomain) -> int:
    """Whether a 2d trim line is isoparametric, decided exactly like openNURBS' validity check does."""
    xmin, xmax = min(ua[0], ub[0]), max(ua[0], ub[0])
    ymin, ymax = min(ua[1], ub[1]), max(ua[1], ub[1])
    s0, s1 = udomain
    t0, t1 = vdomain
    stol, ttol = (s1 - s0) / 32.0, (t1 - t0) / 32.0
    if not (xmax - xmin <= stol or ymax - ymin <= ttol):
        return NOT_ISO
    iso = NOT_ISO
    if (xmax - xmin) * (t1 - t0) <= (ymax - ymin) * (s1 - s0):
        if xmax <= s0 + stol:
            a, b = _parameter_tolerance(s0, s1, s0)
            if a <= xmin and xmax <= b:
                iso = W_ISO
        elif xmin >= s1 - stol:
            a, b = _parameter_tolerance(s0, s1, s1)
            if a <= xmin and xmax <= b:
                iso = E_ISO
        if iso == NOT_ISO and (s0 < xmax or xmin < s1):
            a, b = _parameter_tolerance(s0, s1, 0.5 * (xmin + xmax))
            if a <= xmin and xmax <= b:
                iso = X_ISO
    else:
        if ymax <= t0 + ttol:
            a, b = _parameter_tolerance(t0, t1, t0)
            if a < ymin and ymax <= b:
                iso = S_ISO
        elif ymin >= t1 - ttol:
            a, b = _parameter_tolerance(t0, t1, t1)
            if a < ymin and ymax <= b:
                iso = N_ISO
        # openNURBS compares the x range here as well; kept so the flags match its check.
        if iso == NOT_ISO and (t0 < xmax or xmin < t1):
            a, b = _parameter_tolerance(t0, t1, 0.5 * (ymin + ymax))
            if a < ymin and ymax <= b:
                iso = Y_ISO
    return iso


def _parameter_tolerance(t0: float, t1: float, t: float) -> tuple[float, float]:
    t = min(max(t, t0), t1)
    delta = (t1 - t0) * 8.0 * SQRT_EPSILON + (abs(t0) + abs(t1)) * EPSILON
    delta = min(delta, 0.5 * (t1 - t0))
    return t - delta, t + delta


# ---------------------------------------------------------------------------------------- vectors


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a: Point, s: float) -> Point:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Point) -> Point | None:
    length = math.sqrt(_dot(a, a))
    return (a[0] / length, a[1] / length, a[2] / length) if length > 0 else None


def _area_vector(points: list[Point], loop: list[int]) -> Point:
    """Newell's vector: normal of the loop, twice its area long."""
    x = y = z = 0.0
    for k, i in enumerate(loop):
        p, q = points[i], points[loop[(k + 1) % len(loop)]]
        x += (p[1] - q[1]) * (p[2] + q[2])
        y += (p[2] - q[2]) * (p[0] + q[0])
        z += (p[0] - q[0]) * (p[1] + q[1])
    return (x, y, z)


def _signed_area(uv: list[tuple[float, float]]) -> float:
    return 0.5 * sum(uv[k - 1][0] * uv[k][1] - uv[k][0] * uv[k - 1][1] for k in range(len(uv)))
