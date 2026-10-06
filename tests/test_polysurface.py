import math

import pytest

import rhino3dm

from ifc_converter import polysurface
from ifc_converter.polysurface import planar_polysurface

# Unit cube, faces counter-clockwise seen from outside.
CUBE_POINTS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
CUBE_FACES = [[[0, 3, 2, 1]], [[4, 5, 6, 7]], [[0, 1, 5, 4]], [[1, 2, 6, 5]], [[2, 3, 7, 6]], [[3, 0, 4, 7]]]


def _flat(points):
    return [c for p in points for c in p]


def test_cube_is_a_closed_polysurface():
    brep = planar_polysurface(_flat(CUBE_POINTS), CUBE_FACES)
    assert brep.IsValid and brep.IsSolid
    assert len(brep.Faces) == 6 and len(brep.Edges) == 12


def test_inconsistent_orientation_and_inside_out_shells_are_repaired():
    faces = [CUBE_FACES[0], [CUBE_FACES[1][0][::-1]], *CUBE_FACES[2:]]
    brep = planar_polysurface(_flat(CUBE_POINTS), faces)
    assert brep.IsValid and brep.IsSolid

    inside_out = [[loop[::-1] for loop in face] for face in CUBE_FACES]
    brep = planar_polysurface(_flat(CUBE_POINTS), inside_out)
    assert brep.IsSolid
    for face in brep.Faces:
        u = (face.Domain(0).T0 + face.Domain(0).T1) / 2
        v = (face.Domain(1).T0 + face.Domain(1).T1) / 2
        point, normal = face.PointAt(u, v), face.NormalAt(u, v)
        if face.OrientationIsReversed:
            normal = -normal
        # pointing away from the cube's centre
        assert normal.X * (point.X - .5) + normal.Y * (point.Y - .5) + normal.Z * (point.Z - .5) > 0


# 2 x 0.2 x 2 wall with a 1 x 1 hole; the front face is given as triangles around the hole,
# the hole loop of the back face comes first.
WALL_POINTS = [
    (0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2), (0, .2, 0), (2, .2, 0), (2, .2, 2), (0, .2, 2),
    (.5, 0, .5), (1.5, 0, .5), (1.5, 0, 1.5), (.5, 0, 1.5),
    (.5, .2, .5), (1.5, .2, .5), (1.5, .2, 1.5), (.5, .2, 1.5),
]
WALL_FACES = [
    [[0, 1, 9]], [[0, 9, 8]], [[1, 2, 10]], [[1, 10, 9]], [[2, 3, 11]], [[2, 11, 10]], [[3, 0, 8]], [[3, 8, 11]],
    [[13, 14, 15, 12], [5, 4, 7, 6]],
    [[0, 4, 5, 1]], [[1, 5, 6, 2]], [[2, 6, 7, 3]], [[3, 7, 4, 0]],
    [[8, 9, 13, 12]], [[9, 10, 14, 13]], [[10, 11, 15, 14]], [[11, 8, 12, 15]],
]


def _placed(points, x, y, z, degrees):
    """``points`` turned by ``degrees`` about the z axis and moved to (x, y, z)."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [(x + c * px - s * py, y + s * px + c * py, z + pz) for px, py, pz in points]


def test_coplanar_triangles_are_merged_and_holes_kept():
    brep = planar_polysurface(_flat(WALL_POINTS), WALL_FACES)
    assert brep.IsValid and brep.IsSolid
    assert len(brep.Faces) == 10
    assert sorted(len(face.Loops) for face in brep.Faces) == [1] * 8 + [2] * 2


@pytest.mark.parametrize("placement", [
    (512345.678, 5412345.678, 250.0, 30.0),  # UTM-like easting/northing, turned in plan
    (512345.678, 5412345.678, 250.0, 47.3),
    (5412345.678, 512345.678, 1250.0, 123.4),
])
def test_georeferenced_coplanar_triangles_are_merged(placement):
    brep = planar_polysurface(_flat(_placed(WALL_POINTS, *placement)), WALL_FACES)
    assert brep is not None and brep.IsValid and brep.IsSolid
    assert len(brep.Faces) == 10
    assert sorted(len(face.Loops) for face in brep.Faces) == [1] * 8 + [2] * 2


def test_georeferenced_slender_box_is_merged():
    # A 21.7 m long, 12 x 2 mm tendon 494 km from the origin, as two triangles per side.
    box = [(x, y, z) for x in (0, 21.739) for y in (0, 0.012) for z in (0, 0.002)]
    sides = [(0, 2, 6, 4), (1, 5, 7, 3), (0, 4, 5, 1), (2, 3, 7, 6), (0, 1, 3, 2), (4, 6, 7, 5)]
    faces = [[[a, b, c]] for a, b, c, d in sides] + [[[a, c, d]] for a, b, c, d in sides]
    brep = planar_polysurface(_flat(_placed(box, 493584.881, 4651234.567, 280.0, 37.0)), faces)
    assert brep is not None and brep.IsValid and brep.IsSolid
    assert len(brep.Faces) == 6


def test_touching_items_become_separate_shells():
    # two cubes sharing the face x = 1, as in a window frame touching its glass
    second = [(x + 1, y, z) for x, y, z in CUBE_POINTS]
    faces = CUBE_FACES + [[[i + 8 for i in loop] for loop in face] for face in CUBE_FACES]
    items = [1] * 6 + [2] * 6
    brep = planar_polysurface(_flat(CUBE_POINTS + second), faces, items)
    assert brep.IsValid and brep.IsSolid and brep.IsManifold
    assert len(brep.Faces) == 12


def test_t_junctions_are_closed():
    # the top of the cube split into two halves, so the side faces miss the vertices at x = 0.5
    points = CUBE_POINTS + [(0.5, 0, 1), (0.5, 1, 1)]
    top = [[[4, 8, 9, 7]], [[8, 5, 6, 9]]]
    faces = [CUBE_FACES[0], *top, *CUBE_FACES[2:]]
    brep = planar_polysurface(_flat(points), faces)
    assert brep.IsValid and brep.IsSolid
    assert len(brep.Faces) == 6  # the two halves are merged again


def test_strongly_bent_polygon_is_rejected():
    points = [(0, 0, 0), (1, 0, 0), (1, 1, 0.1), (0, 1, 0)]
    assert planar_polysurface(_flat(points), [[[0, 1, 2, 3]]]) is None



def test_plane_surfaces_hug_their_faces():
    # A wedge whose triangle faces start with the hypotenuse: a frame along that edge gives an
    # equally small but rotated rectangle that sticks out of the wedge's bounding box.
    points = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1)]
    faces = [[[2, 1, 0]], [[4, 5, 3]], [[0, 1, 4, 3]], [[1, 2, 5, 4]], [[2, 0, 3, 5]]]
    brep = planar_polysurface(_flat(points), faces)
    assert brep.IsValid and brep.IsSolid and len(brep.Faces) == 5

    box = brep.GetBoundingBox()
    assert (box.Min.X, box.Min.Y, box.Min.Z) == (0, 0, 0)
    assert abs(box.Max.X - 1) < 1e-9 and abs(box.Max.Y - 1) < 1e-9 and abs(box.Max.Z - 1) < 1e-9


def _prism(outline, height, holes=()):
    """A closed prism over the counter-clockwise ``outline`` (xy), with clockwise ``holes``."""
    loops = [outline, *holes]
    points, rings = [], []
    for loop in loops:
        start = len(points)
        points += [(x, y, 0.0) for x, y in loop] + [(x, y, height) for x, y in loop]
        n = len(loop)
        rings.append((list(range(start, start + n)), list(range(start + n, start + 2 * n))))
    faces = [[bottom[::-1] for bottom, _ in rings], [top for _, top in rings]]
    for bottom, top in rings:
        n = len(bottom)
        faces += [[[bottom[k], bottom[(k + 1) % n], top[(k + 1) % n], top[k]]] for k in range(n)]
    return _flat(points), faces


def _circle(radius, segments, cx=0.0, cy=0.0):
    return [
        (cx + radius * math.cos(2 * math.pi * k / segments), cy + radius * math.sin(2 * math.pi * k / segments))
        for k in range(segments)
    ]


def test_tessellated_round_shapes_are_left_to_meshes():
    verts, faces = _prism(_circle(0.1, 24), 3.0)  # a round column or pipe
    assert planar_polysurface(verts, faces) is None
    verts, faces = _prism(_circle(0.1, 8), 3.0)  # coarsely tessellated, 45 degrees between facets
    assert planar_polysurface(verts, faces) is None


def test_round_opening_and_prisms_with_few_sides_stay_polysurfaces():
    square = [(-2, -2), (2, -2), (2, 2), (-2, 2)]
    verts, faces = _prism(square, 0.25, holes=[_circle(0.1, 32)[::-1]])  # slab with a pipe penetration
    brep = planar_polysurface(verts, faces)
    assert brep is not None and brep.IsSolid and len(brep.Faces) == 38

    verts, faces = _prism(_circle(1, 6), 3.0)  # hexagonal column, 60 degrees between sides
    brep = planar_polysurface(verts, faces)
    assert brep is not None and brep.IsSolid and len(brep.Faces) == 8


def _triangulated_box(x, y, z):
    """A 1 x 2 x 3 box at (x, y, z) as two triangles per side."""
    box = [(x + dx, y + dy, z + dz) for dx in (0, 1) for dy in (0, 2) for dz in (0, 3)]
    sides = [(0, 2, 6, 4), (1, 5, 7, 3), (0, 4, 5, 1), (2, 3, 7, 6), (0, 1, 3, 2), (4, 6, 7, 5)]
    return _flat(box), [[[a, b, c]] for a, b, c, d in sides] + [[[a, c, d]] for a, b, c, d in sides]


def test_no_render_meshes_by_default():
    brep = planar_polysurface(*_triangulated_box(0, 0, 0))
    assert all(brep.Faces[i].GetMesh(rhino3dm.MeshType.Render) is None for i in range(len(brep.Faces)))


@pytest.mark.parametrize("origin", [(0.0, 0.0, 0.0), (493584.881, 4651234.567, 280.0)])
def test_render_meshes_are_the_faces_triangles_and_survive_the_file(monkeypatch, tmp_path, origin):
    monkeypatch.setattr(polysurface, "RENDER_MESHES", True)
    verts, faces = _triangulated_box(*origin)
    model = rhino3dm.File3dm()
    model.Objects.AddBrep(planar_polysurface(verts, faces))
    model.Write(str(tmp_path / "box.3dm"), 7)
    brep = rhino3dm.File3dm.Read(str(tmp_path / "box.3dm")).Objects[0].Geometry
    assert brep.IsValid and brep.IsSolid and len(brep.Faces) == 6
    corners = {tuple(verts[i:i + 3]) for i in range(0, len(verts), 3)}
    for i in range(len(brep.Faces)):
        face = brep.Faces[i]
        mesh = face.GetMesh(rhino3dm.MeshType.Render)
        assert mesh is not None and len(mesh.Faces) == 2
        # exact corners, also far from the origin (double precision vertices)
        points = [mesh.Vertices.Point3dAt(k) for k in range(len(mesh.Vertices))]
        assert {(p.X, p.Y, p.Z) for p in points} <= corners
        u = (face.Domain(0).T0 + face.Domain(0).T1) / 2
        v = (face.Domain(1).T0 + face.Domain(1).T1) / 2
        normal = face.NormalAt(u, v)
        if face.OrientationIsReversed:
            normal = -normal
        mesh_normal = mesh.Normals[0]
        assert mesh_normal.X * normal.X + mesh_normal.Y * normal.Y + mesh_normal.Z * normal.Z > 0.999


def test_silhouette_cut_outs_are_left_to_meshes():
    # Two crossed vertical planes with a 120-point star outline each, like a Revit RPC tree.
    star = [(math.cos(k * math.pi / 60) * (1.0 + 0.3 * (k % 2)), math.sin(k * math.pi / 60) * (1.0 + 0.3 * (k % 2)))
            for k in range(120)]
    points, faces = [], []
    for plane in ("xz", "yz"):
        start = len(points)
        points += [(u, 0.0, v + 2.0) if plane == "xz" else (0.0, u, v + 2.0) for u, v in star]
        centre = len(points)
        points.append((0.0, 0.0, 2.0))
        faces += [[[centre, start + k, start + (k + 1) % 120]] for k in range(120)]
    assert planar_polysurface(_flat(points), faces) is None
