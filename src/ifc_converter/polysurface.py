"""Joined planar Rhino polysurfaces from IfcOpenShell's triangulated shapes.

The triangles (or any planar polygons with holes) are welded into one closed, consistently
oriented shell per representation item, coplanar neighbours are merged into faces with holes, and
the resulting topology is serialized as an openNURBS Brep record that rhino3dm decodes (rhino3dm
itself cannot build or join polysurfaces).
"""
from __future__ import annotations

import base64
import math
import struct
import uuid
from collections.abc import Sequence

import numpy as np
import rhino3dm

from ifc_converter import on_archive as archive

Point = tuple[float, float, float]
Face = list[list[int]]  # outer loop first, then holes; vertex indices

# Vertices closer than this are merged (metres).
WELD_TOLERANCE = 1e-6
# Polygons that bend out of their plane by more than this are not turned into planar faces.
MAX_PLANE_DEVIATION = 1e-3
# Edges tried as x axis of a face frame (longest first); enough for building faces, bounded for detailed ones.
MAX_FRAME_CANDIDATES = 32
# Loop points x frame candidates from which the frame search runs vectorized.
NUMPY_FRAME_SIZE = 256
# T-junction repair compares naked edges with naked vertices; beyond this many it gets too slow.
MAX_TJUNCTION_VERTICES = 5000
# Edge x vertex pairs compared at once in the T-junction search.
TJUNCTION_BLOCK = 1 << 20

# Store each face's triangles as its render mesh, so Rhino need not mesh every face when it opens
# the file. Costs ~0.75 kB per face (openNURBS' fixed per-mesh overhead), +35-46 % brep geometry
# on the test models.
RENDER_MESHES = False
# Beyond this distance from the origin (metres) render meshes keep double-precision vertices.
DOUBLE_PRECISION_FROM = 10_000.0

# Tessellated curved shapes are left to meshes (see _is_faceted). Facets meet two or more
# neighbours at less than FACET_ANGLE degrees. A shape with at least FACETED_MIN_FACES faces is
# faceted if more than CURVED_SHARE of its faces are facets covering more than CURVED_AREA of its
# area, or if it has more than MANY_FACETS facets (and more than MANY_FACETS_SHARE of its faces)
# that cover more than MANY_FACETS_AREA of its area or number more than MAX_FACETS.
# Flat cut-outs with tessellated outlines (Revit RPC trees and people: a few planar faces with
# 100-500 vertex silhouettes) stay meshes too: their faces average more than this many vertices.
# Building elements stay below 7 on the test models.
MAX_VERTICES_PER_FACE = 20
FACET_ANGLE = 50.0
FACETED_MIN_FACES = 8
CURVED_SHARE, CURVED_AREA = 0.3, 0.2
MANY_FACETS, MANY_FACETS_SHARE, MANY_FACETS_AREA = 24, 0.15, 0.01
MAX_FACETS = 200

TRIM_BOUNDARY, TRIM_MATED = 1, 2
_TRIM = struct.Struct("<2i2d3i4i2d2d32x2d")
LOOP_OUTER, LOOP_INNER = 1, 2
NOT_ISO, X_ISO, Y_ISO, W_ISO, S_ISO, E_ISO, N_ISO = range(7)

SQRT_EPSILON = 1.490116119384765625e-8
EPSILON = 2.2204460492503131e-16

_opennurbs_version: int | None = None


def planar_polysurface(
    verts: Sequence[float], faces: Sequence[Sequence[Sequence[int]]], item_ids: Sequence[int] | None = None,
    solid_items: set[int] | None = None,
) -> rhino3dm.Brep | None:
    """A valid Brep from flat ``verts`` (xyz...) and polygon ``faces`` with holes, or None.

    None also stands for tessellated curved shapes (pipes, round columns, sanitary objects) and
    silhouette cut-outs, which are much smaller and just as good as meshes; see ``_is_faceted`` and
    ``_is_silhouette``.

    ``item_ids`` (one per face) keeps touching representation items, e.g. window frame and glass,
    apart as separate closed shells instead of joining them along non-manifold edges. The shells of
    an item in ``solid_items`` are turned only together, so the voids of hollow solids keep pointing
    inwards.
    """
    points, triangles, point_items = _weld(verts, faces, item_ids)
    welded = _split_t_junctions(points, triangles, point_items)
    solids = None
    if solid_items:
        solids = [point_items[face[0][0]] for face in welded]
        solids = [item if item in solid_items else None for item in solids]
    welded, outer_vectors, sources = _orient(points, welded, solids)
    if not welded:
        return None
    merged, groups = _merge_coplanar(points, welded, outer_vectors)
    merged_vectors = [_area_vector(points, face[0]) for face in merged]
    if _is_faceted(points, merged, merged_vectors) or _is_silhouette(merged):
        return None

    def render_meshes(groups: list[list[int]], vectors: list[Point]) -> list[bytes | None] | None:
        if not RENDER_MESHES:
            return None
        return _render_meshes(points, [[triangles[sources[fi]] for fi in group] for group in groups], vectors)

    brep = _decode(points, merged, merged_vectors, render_meshes(groups, merged_vectors))
    if brep is not None and brep.IsValid:
        return brep
    brep = _decode(points, welded, outer_vectors, render_meshes([[fi] for fi in range(len(welded))], outer_vectors))
    return brep if brep is not None and brep.IsValid else None


def _decode(
    points: list[Point], faces: list[Face], outer_vectors: list[Point], render_meshes: list[bytes | None] | None
) -> rhino3dm.Brep | None:
    record = _brep_record(points, faces, outer_vectors, render_meshes)
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
    coords = np.asarray(verts, dtype=float).reshape(-1, 3)
    raw = list(map(tuple, coords.tolist()))
    # rint rounds halves to even like round()
    grid = list(map(tuple, np.rint(coords / WELD_TOLERANCE).astype(np.int64).tolist()))
    use_items = item_ids is not None and len(item_ids) == len(faces)
    indices: dict[int, dict[tuple, int]] = {}  # per item: grid point -> welded point
    points: list[Point] = []
    point_items: list[int] = []
    welded: list[Face] = []
    for fi, face in enumerate(faces):
        item = item_ids[fi] if use_items else 0
        index = indices.get(item)
        if index is None:
            index = indices[item] = {}
        loops = []
        for loop in face:
            mapped = []
            for i in loop:
                key = grid[i]
                point = index.get(key)
                if point is None:
                    point = index[key] = len(points)
                    points.append(raw[i])
                    point_items.append(item)
                if not mapped or mapped[-1] != point:
                    mapped.append(point)
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
            for a, b in zip(loop, loop[-1:] + loop[:-1]):
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
    for (a, b), near in _near_edges(points, naked, candidates, point_items, tolerance):
        pa, pb = points[a], points[b]
        length = math.dist(pa, pb)
        inside = []
        for v in near:
            if v != a and v != b:
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


def _near_edges(
    points: list[Point], edges: list[tuple[int, int]], candidates: list[int], point_items: list[int], tolerance: float
):
    """Each edge with the candidate vertices of its item, other than its ends, that may lie on it.

    Points with ``|pa - p| + |p - pb| < |pa - pb| + tolerance`` lie in an ellipsoid around the edge
    whose points are at most half of ``margin`` away from it.
    """
    coords = np.array([points[v] for v in candidates])
    vertex_ids = np.array(candidates)
    items = np.array([point_items[v] for v in candidates])
    ends = np.array(edges)
    start, end = np.array([points[a] for a, _ in edges]), np.array([points[b] for _, b in edges])
    axis = end - start
    length_squared = (axis ** 2).sum(axis=1)
    margin = np.sqrt(tolerance * (2 * np.sqrt(length_squared) + tolerance)) + tolerance
    low, high = np.minimum(start, end) - margin[:, None], np.maximum(start, end) + margin[:, None]
    edge_items = np.array([point_items[a] for a, _ in edges])
    block = max(1, TJUNCTION_BLOCK // len(candidates))
    for first in range(0, len(edges), block):
        rows = slice(first, first + block)
        near = items == edge_items[rows, None]
        for k in range(3):
            near &= coords[:, k] >= low[rows, k, None]
            near &= coords[:, k] <= high[rows, k, None]
        hits_edge, hits_vertex = np.nonzero(near)  # row by row, vertices ascending
        hits_edge += first
        keep = (vertex_ids[hits_vertex] != ends[hits_edge, 0]) & (vertex_ids[hits_vertex] != ends[hits_edge, 1])
        hits_edge, hits_vertex = hits_edge[keep], hits_vertex[keep]
        if not len(hits_edge):
            continue
        # distance to the edge, for long edges whose bounding box holds many vertices
        offset = coords[hits_vertex] - start[hits_edge]
        t = (offset * axis[hits_edge]).sum(axis=1) / np.maximum(length_squared[hits_edge], 1e-300)
        offset -= np.clip(t, 0.0, 1.0)[:, None] * axis[hits_edge]
        close = (offset ** 2).sum(axis=1) <= margin[hits_edge] ** 2
        near_vertices: dict[int, list[int]] = {}
        for e, v in zip(hits_edge[close].tolist(), vertex_ids[hits_vertex[close]].tolist()):
            near_vertices.setdefault(e, []).append(v)
        for e, vertices in near_vertices.items():
            yield edges[e], vertices


def _orient(
    points: list[Point], faces: list[Face], solids: list[int | None] | None = None
) -> tuple[list[Face], list[Point], list[int]]:
    """Outer loop first, holes against it, neighbours consistent, closed shells pointing outwards.

    IfcOpenShell's polygon output guarantees neither which loop is the outer one nor a consistent
    loop direction across faces. Also returns the area vector of each outer loop and the index of
    each face in ``faces`` (faces without area are dropped). ``solids`` gives per face the solid it
    belongs to (or None): the shells of one solid are turned together, so that the solid as a whole
    points outwards and its voids inwards.
    """
    oriented: list[Face] = []
    outer_vectors: list[Point] = []
    sources: list[int] = []
    for fi, face in enumerate(faces):
        if len(face) == 1:
            vector = _area_vector(points, face[0])
            if _dot(vector, vector) != 0:
                oriented.append([face[0]])
                outer_vectors.append(vector)
                sources.append(fi)
            continue
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
        outer_vectors.append(normal)
        sources.append(fi)

    # Walk across edges shared by exactly two faces; two uses in the same direction mean one flip.
    uses: dict[tuple[int, int], list[tuple[int, bool]]] = {}
    for fi, face in enumerate(oriented):
        for loop in face:
            for a, b in zip(loop, loop[1:] + loop[:1]):
                if a < b:
                    uses.setdefault((a, b), []).append((fi, True))
                else:
                    uses.setdefault((b, a), []).append((fi, False))
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
    for fi, face in enumerate(oriented):
        if flip[fi]:
            oriented[fi] = [loop[::-1] for loop in face]
            outer_vectors[fi] = _area_vector(points, oriented[fi][0])

    # A shell with negative signed volume points inwards. The shells of a solid count together.
    groups: dict[object, list[list[int]]] = {}
    for k, shell in enumerate(shells):
        solid = solids[sources[shell[0]]] if solids else None
        groups.setdefault(("shell", k) if solid is None else solid, []).append(shell)
    for group in groups.values():
        volume = 0.0
        ox, oy, oz = points[oriented[group[0][0]][0][0]]  # precision far from the world origin
        for shell in group:
            for fi in shell:
                area = _add((0.0, 0.0, 0.0), outer_vectors[fi])
                for loop in oriented[fi][1:]:
                    area = _add(area, _area_vector(points, loop))
                px, py, pz = points[oriented[fi][0][0]]
                volume += _dot((px - ox, py - oy, pz - oz), area)
        if volume < 0:
            for shell in group:
                for fi in shell:
                    oriented[fi] = [loop[::-1] for loop in oriented[fi]]
                    outer_vectors[fi] = _area_vector(points, oriented[fi][0])
    return oriented, outer_vectors, sources


def _merge_coplanar(
    points: list[Point], faces: list[Face], outer_vectors: list[Point]
) -> tuple[list[Face], list[list[int]]]:
    """Merge edge-connected coplanar faces into one face with holes and drop the collinear vertices
    left on straight edges. Regions whose boundary is not one outer loop plus holes stay unmerged.

    Also returns the indices of the faces in ``faces`` that make up each merged face."""
    normals = [_unit(vector) for vector in outer_vectors]
    # Far from the origin (georeferenced models) normals from world coordinates are too imprecise
    # for the distance test below, so it uses normals computed relative to the face, when needed.
    local_normals: list[Point | None] = [None] * len(faces)
    parent = list(range(len(faces)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    directed: dict[tuple[int, int], list[int]] = {}
    for fi, face in enumerate(faces):
        for loop in face:
            for edge in zip(loop, loop[1:] + loop[:1]):
                directed.setdefault(edge, []).append(fi)
    for (a, b), users in directed.items():
        others = directed.get((b, a))
        if len(users) != 1 or not others or len(others) != 1:
            continue
        f, g = users[0], others[0]
        nf, ng = normals[f], normals[g]
        if f == g or not nf or not ng or _dot(nf, ng) <= 1 - 1e-9:
            continue
        # Coplanar if every point of each face lies within the weld tolerance of the other's plane:
        # distances between the faces, not plane offsets from the world origin, which are off by
        # millimetres 500 km away from it (and grow with any face's distance from the origin).
        nf, ng = local_normals[f], local_normals[g]
        if nf is None:
            nf = local_normals[f] = _plane_normal(points, faces[f][0]) or normals[f]
        if ng is None:
            ng = local_normals[g] = _plane_normal(points, faces[g][0]) or normals[g]
        if _within_plane(points, faces[g][0], points[faces[f][0][0]], nf) and _within_plane(
            points, faces[f][0], points[faces[g][0][0]], ng
        ):
            parent[find(f)] = find(g)

    regions: dict[int, list[int]] = {}
    for fi in range(len(faces)):
        regions.setdefault(find(fi), []).append(fi)

    merged: list[Face] = []
    groups: list[list[int]] = []
    for members in regions.values():
        face = _region_face(points, [faces[fi] for fi in members], normals[members[0]])
        if face is None:
            merged.extend(faces[fi] for fi in members)
            groups.extend([fi] for fi in members)
        else:
            merged.append(face)
            groups.append(members)

    neighbours: dict[int, set[int]] = {}
    for face in merged:
        for loop in face:
            for a, b in zip(loop, loop[-1:] + loop[:-1]):
                neighbours.setdefault(a, set()).add(b)
                neighbours.setdefault(b, set()).add(a)
    removable = set()
    for v, around in neighbours.items():
        if len(around) == 2:
            a, b = around
            if math.dist(points[a], points[v]) + math.dist(points[v], points[b]) - math.dist(points[a], points[b]) < 1e-8:
                removable.add(v)
    if not removable:
        return merged, groups
    result = []
    for face in merged:
        loops = [[v for v in loop if v not in removable] for loop in face]
        result.append(loops if all(len(loop) >= 3 for loop in loops) else face)
    return result, groups


def _render_meshes(points: list[Point], groups: list[list[Face]], vectors: list[Point]) -> list[bytes | None]:
    """Per face (the welded input polygons it was merged from) the record of its render mesh, or None
    if one of them is not a triangle."""
    large = max(abs(c) for p in points for c in p) > DOUBLE_PRECISION_FROM
    meshes: list[bytes | None] = []
    for group, vector in zip(groups, vectors):
        if all(len(face) == 1 and len(face[0]) == 3 for face in group):
            meshes.append(_render_mesh(points, [face[0] for face in group], vector, large))
        else:
            meshes.append(None)
    return meshes


def _render_mesh(points: list[Point], triangles: list[list[int]], normal: Point, large: bool) -> bytes:
    """The openNURBS record of a mesh of ``triangles``, all turned to face along ``normal``."""
    mesh = rhino3dm.Mesh()
    add_vertex = mesh.Vertices.AddPoint3d if large else mesh.Vertices.Add
    add_face = mesh.Faces.AddFace
    nx, ny, nz = normal
    index: dict[int, int] = {}
    for a, b, c in triangles:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points[a], points[b], points[c]
        ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
        if (uy * vz - uz * vy) * nx + (uz * vx - ux * vz) * ny + (ux * vy - uy * vx) * nz < 0:
            b, c = c, b
        corners = []
        for v in (a, b, c):
            k = index.get(v)
            if k is None:
                k = index[v] = len(index)
                add_vertex(*points[v])
            corners.append(k)
        add_face(*corners)
    mesh.Normals.ComputeNormals()
    return base64.b64decode(mesh.Encode()["data"])


def _is_silhouette(faces: list[Face]) -> bool:
    """Whether the faces are flat cut-outs with long tessellated outlines, e.g. RPC billboards."""
    return sum(len(loop) for face in faces for loop in face) > MAX_VERTICES_PER_FACE * len(faces)


def _is_faceted(points: list[Point], faces: list[Face], outer_vectors: list[Point]) -> bool:
    """Whether the shape is a tessellated curved one: pipes, round ducts and columns, rebar, fittings,
    sanitary objects, curved walls, or furniture covered with small round knobs.

    Merging coplanar faces gains nothing there, and as a polysurface such a shape takes 20 to 50 times
    the space of its mesh. A flat face touching a single facet (a flange next to a rounded fillet) is
    no facet, and few facets on a small part of the area (a round opening in a slab) keep a polysurface.
    """
    if len(faces) < FACETED_MIN_FACES:
        return False
    normals = [_unit(vector) for vector in outer_vectors]
    owner: dict[tuple[int, int], int] = {}
    for fi, face in enumerate(faces):
        for loop in face:
            for edge in zip(loop, loop[1:] + loop[:1]):
                owner[edge] = fi
    limit = math.cos(math.radians(FACET_ANGLE))
    shallow: list[set[int]] = [set() for _ in faces]
    for (a, b), f in owner.items():
        g = owner.get((b, a))
        if g is not None and g != f and normals[f] and normals[g] and _dot(normals[f], normals[g]) > limit:
            shallow[f].add(g)
    facets = [fi for fi, neighbours in enumerate(shallow) if len(neighbours) >= 2]
    if len(facets) <= MANY_FACETS_SHARE * len(faces):
        return False
    areas = [math.sqrt(_dot(vector, vector)) for vector in outer_vectors]
    area_share = sum(areas[fi] for fi in facets) / (sum(areas) or 1.0)
    if len(facets) > CURVED_SHARE * len(faces) and area_share > CURVED_AREA:
        return True
    return len(facets) > MANY_FACETS and (area_share > MANY_FACETS_AREA or len(facets) > MAX_FACETS)


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


def _brep_record(
    points: list[Point], faces: list[Face], outer_vectors: list[Point], render_meshes: list[bytes | None] | None = None
) -> bytes | None:
    """The openNURBS record of a Brep with one plane surface per face and polyline edges/trims.

    The trims of a loop share one closed 2d polyline, each using the segment [k, k + 1] of it; the
    edges likewise use segments of the 3d polyline of the loop they first appear in. One curve per
    trim and edge would take about a fifth more space and decoding time.
    """
    polyline_curve, iso_flag = archive.polyline_curve, _iso
    curves_2d: list[bytes] = []
    curves_3d: list[bytes] = []
    surfaces: list[bytes] = []
    edge_index: dict[tuple[int, int], int] = {}
    # per edge: start and end point, trims, 3d curve and segment, tolerance
    edge_start: list[int] = []
    edge_end: list[int] = []
    edge_trims: list[list[int]] = []
    edge_curve: list[tuple[int, int]] = []
    edge_tolerance: list[float] = []
    trims: list[tuple] = []  # 2d curve and segment, edge, start, end, reversed, iso, loop
    loops: list[tuple[list[int], int, int]] = []
    brep_faces: list[tuple[list[int], int]] = []
    vertices: dict[int, int] = {}  # point index -> brep vertex index
    vertex_tolerance: dict[int, float] = {}

    face_meshes: list[bytes | None] = []  # render mesh records of the faces written
    for fi, (face, outer_vector) in enumerate(zip(faces, outer_vectors)):
        frame = _face_frame(points, face[0], outer_vector)
        if frame is None:
            continue
        origin, (xx, xy, xz), (yx, yy, yz), (nx, ny, nz) = frame
        ox, oy, oz = origin
        deviation: dict[int, float] = {}
        uv: dict[int, tuple[float, float]] = {}
        for loop in face:
            for i in loop:
                if i not in uv:
                    px, py, pz = points[i]
                    dx, dy, dz = px - ox, py - oy, pz - oz
                    deviation[i] = abs(dx * nx + dy * ny + dz * nz)
                    uv[i] = (dx * xx + dy * xy + dz * xz, dx * yx + dy * yy + dz * yz)
        if max(deviation.values()) > MAX_PLANE_DEVIATION:
            return None
        outer_uv = [uv[i] for i in face[0]]
        us = [u for u, _ in outer_uv]
        vs = [v for _, v in outer_uv]
        udomain, vdomain = (min(us), max(us)), (min(vs), max(vs))
        if udomain[0] >= udomain[1] or vdomain[0] >= vdomain[1]:
            continue

        # The trims lie on the plane, the edges run through the original points.
        for i, tolerance in deviation.items():
            vertex_tolerance[i] = max(vertex_tolerance.get(i, 0.0), tolerance)
        face_index = len(brep_faces)
        surface_index = len(surfaces)
        surfaces.append(archive.plane_surface(origin, (xx, xy, xz), (yx, yy, yz), (nx, ny, nz), udomain, vdomain))
        loop_indices = []
        for position, loop in enumerate(face):
            outer = position == 0
            loop_uv = outer_uv if outer else [uv[i] for i in loop]
            if (_signed_area(loop_uv) > 0) != outer:  # outer loops run counter-clockwise, holes clockwise
                loop, loop_uv = loop[::-1], loop_uv[::-1]
            loop_index = len(loops)
            loop_trims = []
            count = len(loop)
            curve_2d = len(curves_2d)
            curves_2d.append(polyline_curve([(u, v, 0.0) for u, v in loop_uv + loop_uv[:1]], 2))
            curve_3d = None
            for k in range(count):
                a = loop[k]
                b = loop[k + 1] if k + 1 < count else loop[0]
                key = (a, b) if a < b else (b, a)
                edge = edge_index.get(key)
                if edge is None:
                    if curve_3d is None:
                        curve_3d = len(curves_3d)
                        curves_3d.append(polyline_curve([points[i] for i in loop + loop[:1]], 3))
                    edge = edge_index[key] = len(edge_start)
                    edge_start.append(a)
                    edge_end.append(b)
                    edge_trims.append([])
                    edge_curve.append((curve_3d, k))
                    edge_tolerance.append(0.0)
                edge_tolerance[edge] = max(edge_tolerance[edge], deviation[a], deviation[b])
                trim = len(trims)
                edge_trims[edge].append(trim)
                loop_trims.append(trim)
                ua = loop_uv[k]
                ub = loop_uv[k + 1] if k + 1 < count else loop_uv[0]
                trims.append((
                    curve_2d, k, edge, a, b, int(a != edge_start[edge]), iso_flag(ua, ub, udomain, vdomain), loop_index,
                ))
                if a not in vertices:
                    vertices[a] = len(vertices)
            loops.append((loop_trims, LOOP_OUTER if outer else LOOP_INNER, face_index))
            loop_indices.append(loop_index)
        brep_faces.append((loop_indices, surface_index))
        face_meshes.append(render_meshes[fi] if render_meshes else None)

    if not brep_faces:
        return None

    vertex_points: list[Point] = [points[0]] * len(vertices)
    vertex_edges: list[list[int]] = [[] for _ in vertices]
    for point_index, vertex_index in vertices.items():
        vertex_points[vertex_index] = points[point_index]
    for edge_number, (start, end) in enumerate(zip(edge_start, edge_end)):
        vertex_edges[vertices[start]].append(edge_number)
        if end != start:
            vertex_edges[vertices[end]].append(edge_number)

    data = archive.class_data().version(3, 3)
    data.chunk(archive.object_array(curves_2d))
    data.chunk(archive.object_array(curves_3d))
    data.chunk(archive.object_array(surfaces))

    pack = struct.pack
    tolerances = [0.0] * len(vertices)
    for i, tolerance in vertex_tolerance.items():
        tolerances[vertices[i]] = tolerance
    records = [
        pack(f"<i3di{len(around)}id", i, point[0], point[1], point[2], len(around), *around, tolerance)
        for i, (point, around, tolerance) in enumerate(zip(vertex_points, vertex_edges, tolerances))
    ]
    data.chunk(archive.anonymous_chunk().version(1, 0).int(len(vertex_points)).raw(b"".join(records)))

    # index, 3d curve, proxy-curve reversal flag, curve domain, vertices, trims, tolerance, domain
    records = [
        pack(
            f"<3i2d2ii{len(users)}i3d", i, curve, 0, segment, segment + 1, vertices[start], vertices[end],
            len(users), *users, tolerance, segment, segment + 1,
        )
        for i, (start, end, users, (curve, segment), tolerance) in enumerate(
            zip(edge_start, edge_end, edge_trims, edge_curve, edge_tolerance)
        )
    ]
    data.chunk(archive.anonymous_chunk().version(1, 0).int(len(edge_start)).raw(b"".join(records)))

    # index, 2d curve, domain, edge, vertices, reversed, type, iso, loop, legacy tolerances, proxy
    # domain, proxy-curve reversal flag and reserved bytes, legacy tolerances
    pack_trim = _TRIM.pack
    records = [
        pack_trim(
            i, curve, segment, segment + 1, edge, vertices[start], vertices[end], reversed_3d,
            TRIM_MATED if len(edge_trims[edge]) > 1 else TRIM_BOUNDARY, iso, loop,
            0.0, 0.0, segment, segment + 1, 0.0, 0.0,
        )
        for i, (curve, segment, edge, start, end, reversed_3d, iso, loop) in enumerate(trims)
    ]
    data.chunk(archive.anonymous_chunk().version(1, 0).int(len(trims)).raw(b"".join(records)))

    records = [
        pack(f"<ii{len(loop_trims)}i2i", i, len(loop_trims), *loop_trims, loop_type, face_index)
        for i, (loop_trims, loop_type, face_index) in enumerate(loops)
    ]
    data.chunk(archive.anonymous_chunk().version(1, 0).int(len(loops)).raw(b"".join(records)))

    records = [
        pack(f"<ii{len(loop_indices)}i3i", i, len(loop_indices), *loop_indices, surface_index, 0, 0)
        for i, (loop_indices, surface_index) in enumerate(brep_faces)
    ]
    records.extend(uuid.uuid4().bytes_le for _ in brep_faces)
    records.append(b"\x00")  # no per-face colours
    data.chunk(archive.anonymous_chunk().version(1, 2).int(len(brep_faces)).raw(b"".join(records)))

    xs, ys, zs = zip(*vertex_points)
    data.point((min(xs), min(ys), min(zs)))
    data.point((max(xs), max(ys), max(zs)))
    # Per face a flag and the render mesh; faces without one are meshed by Rhino.
    chunk = archive.anonymous_chunk()
    for mesh in face_meshes:
        if mesh is None:
            chunk.raw(b"\x00")
        else:
            chunk.raw(b"\x01").nested(mesh)
    data.chunk(chunk)
    data.chunk(archive.anonymous_chunk().raw(bytes(len(brep_faces))))  # no analysis meshes
    data.int(0)  # solid orientation not stored, Rhino computes it
    data.chunk(archive.anonymous_chunk(1, 1).bool(False))  # no region topology
    return archive.write_object(archive.CLASS_BREP, data)


def _face_frame(points: list[Point], outer: list[int], area_vector: Point) -> tuple[Point, Point, Point, Point] | None:
    """Origin and orthonormal axes of the plane of ``outer`` (with that ``area_vector``), z along its normal."""
    normal = _unit(area_vector)
    if normal is None:
        return None
    origin = points[outer[0]]
    ox, oy, oz = origin
    loop = [points[i] for i in outer]
    relative = [(p[0] - ox, p[1] - oy, p[2] - oz) for p in loop]
    # The plane surface spans the loop's bounding rectangle in this frame. Align the x axis with the
    # edge whose rectangle has the smallest world bounding box; otherwise the untrimmed surface can
    # stick out far beyond the face and Rhino's bounding boxes (zoom extents, selection) are too large.
    directions = [(q[0] - p[0], q[1] - p[1], q[2] - p[2]) for p, q in zip(loop, loop[1:] + loop[:1])]
    directions.sort(key=lambda d: -(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]))
    directions = directions[:MAX_FRAME_CANDIDATES]
    if len(relative) * len(directions) >= NUMPY_FRAME_SIZE:
        extents = _frame_extents_numpy(normal, relative, directions)
    else:
        extents = _frame_extents(normal, relative, directions)
    best = None
    for xaxis, yaxis, u0, u1, v0, v1 in extents:
        (xx, xy, xz), (yx, yy, yz) = xaxis, yaxis
        # world bounding box of the rectangle's corners origin + x * u + y * v
        x0, x1, y0, y1 = xx * u0, xx * u1, yx * v0, yx * v1
        cx = (ox + (x0 + y0), ox + (x0 + y1), ox + (x1 + y0), ox + (x1 + y1))
        x0, x1, y0, y1 = xy * u0, xy * u1, yy * v0, yy * v1
        cy = (oy + (x0 + y0), oy + (x0 + y1), oy + (x1 + y0), oy + (x1 + y1))
        x0, x1, y0, y1 = xz * u0, xz * u1, yz * v0, yz * v1
        cz = (oz + (x0 + y0), oz + (x0 + y1), oz + (x1 + y0), oz + (x1 + y1))
        size = sum((max(cx) - min(cx), max(cy) - min(cy), max(cz) - min(cz)))
        if best is None or size < best[0] - 1e-9:
            best = (size, xaxis, yaxis)
    if best is None:
        return None
    return origin, best[1], best[2], normal


def _frame_extents(normal: Point, relative: list[Point], directions: list[Point]):
    """For each edge direction: the frame axes it gives and the loop's u and v range in that frame.

    An axis equal or opposite to an earlier one gives the same rectangle and is left out.
    """
    nx, ny, nz = normal
    seen = set()
    for dx, dy, dz in directions:
        # x axis: the edge direction projected onto the plane
        s = dx * nx + dy * ny + dz * nz
        ax, ay, az = dx - nx * s, dy - ny * s, dz - nz * s
        length = math.sqrt(ax * ax + ay * ay + az * az)
        if not length > 0:
            continue
        xaxis = xx, xy, xz = ax / length, ay / length, az / length
        if xaxis in seen:
            continue
        seen.add(xaxis)
        seen.add((-xx, -xy, -xz))
        yx, yy, yz = ny * xz - nz * xy, nz * xx - nx * xz, nx * xy - ny * xx
        us = [rx * xx + ry * xy + rz * xz for rx, ry, rz in relative]
        vs = [rx * yx + ry * yy + rz * yz for rx, ry, rz in relative]
        yield xaxis, (yx, yy, yz), min(us), max(us), min(vs), max(vs)


def _frame_extents_numpy(normal: Point, relative: list[Point], directions: list[Point]):
    """``_frame_extents`` for long loops, with the same floating point operations in the same order."""
    nx, ny, nz = normal
    d = np.array(directions)
    dx, dy, dz = d[:, 0], d[:, 1], d[:, 2]
    s = dx * nx + dy * ny + dz * nz
    ax, ay, az = dx - nx * s, dy - ny * s, dz - nz * s
    length = np.sqrt(ax * ax + ay * ay + az * az)
    keep = length > 0
    length = length[keep]
    xx, xy, xz = ax[keep] / length, ay[keep] / length, az[keep] / length
    yx, yy, yz = ny * xz - nz * xy, nz * xx - nx * xz, nx * xy - ny * xx
    r = np.array(relative)
    rx, ry, rz = r[:, 0], r[:, 1], r[:, 2]
    us = rx * xx[:, None] + ry * xy[:, None] + rz * xz[:, None]
    vs = rx * yx[:, None] + ry * yy[:, None] + rz * yz[:, None]
    columns = (xx, xy, xz, yx, yy, yz, us.min(axis=1), us.max(axis=1), vs.min(axis=1), vs.max(axis=1))
    for xx, xy, xz, yx, yy, yz, u0, u1, v0, v1 in zip(*(c.tolist() for c in columns)):
        yield (xx, xy, xz), (yx, yy, yz), u0, u1, v0, v1


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


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


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


def _within_plane(points: list[Point], loop: list[int], origin: Point, normal: Point) -> bool:
    """Whether all points of ``loop`` are closer than the weld tolerance to the plane through ``origin``."""
    ox, oy, oz = origin
    nx, ny, nz = normal
    for i in loop:
        p = points[i]
        if abs((p[0] - ox) * nx + (p[1] - oy) * ny + (p[2] - oz) * nz) >= WELD_TOLERANCE:
            return False
    return True


def _plane_normal(points: list[Point], loop: list[int]) -> Point | None:
    """Unit normal of the loop computed relative to its first point, precise far from the origin."""
    ox, oy, oz = points[loop[0]]
    if len(loop) == 3:
        p, q = points[loop[1]], points[loop[2]]
        px, py, pz = p[0] - ox, p[1] - oy, p[2] - oz
        qx, qy, qz = q[0] - ox, q[1] - oy, q[2] - oz
        normal = (py * qz - pz * qy, pz * qx - px * qz, px * qy - py * qx)
    else:
        x = y = z = 0.0
        for i, j in zip(loop, loop[1:] + loop[:1]):
            p, q = points[i], points[j]
            px, py, pz = p[0] - ox, p[1] - oy, p[2] - oz
            qx, qy, qz = q[0] - ox, q[1] - oy, q[2] - oz
            x += (py - qy) * (pz + qz)
            y += (pz - qz) * (px + qx)
            z += (px - qx) * (py + qy)
        normal = (x, y, z)
    return _unit(normal)


def _signed_area(uv: list[tuple[float, float]]) -> float:
    return 0.5 * sum(uv[k - 1][0] * uv[k][1] - uv[k][0] * uv[k - 1][1] for k in range(len(uv)))
