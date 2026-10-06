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


def test_coplanar_triangles_are_merged_and_holes_kept():
    # 2 x 0.2 x 2 wall with a 1 x 1 hole; the front face is given as triangles around the hole,
    # the hole loop of the back face comes first.
    points = [
        (0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2), (0, .2, 0), (2, .2, 0), (2, .2, 2), (0, .2, 2),
        (.5, 0, .5), (1.5, 0, .5), (1.5, 0, 1.5), (.5, 0, 1.5),
        (.5, .2, .5), (1.5, .2, .5), (1.5, .2, 1.5), (.5, .2, 1.5),
    ]
    front = [[[0, 1, 9]], [[0, 9, 8]], [[1, 2, 10]], [[1, 10, 9]], [[2, 3, 11]], [[2, 11, 10]], [[3, 0, 8]], [[3, 8, 11]]]
    faces = front + [
        [[13, 14, 15, 12], [5, 4, 7, 6]],
        [[0, 4, 5, 1]], [[1, 5, 6, 2]], [[2, 6, 7, 3]], [[3, 7, 4, 0]],
        [[8, 9, 13, 12]], [[9, 10, 14, 13]], [[10, 11, 15, 14]], [[11, 8, 12, 15]],
    ]
    brep = planar_polysurface(_flat(points), faces)
    assert brep.IsValid and brep.IsSolid
    assert len(brep.Faces) == 10
    assert sorted(len(face.Loops) for face in brep.Faces) == [1] * 8 + [2] * 2


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
