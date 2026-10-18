import numpy

from ifc_converter.preview import PREVIEW_FORMAT_VERSION, PreviewMesh, load_preview, save_preview


def _cube() -> PreviewMesh:
    corners = numpy.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)], numpy.float32)
    faces = [(0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6), (0, 1, 4), (1, 5, 4),
             (2, 6, 3), (3, 6, 7), (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)]
    return PreviewMesh(
        positions=corners, colors=numpy.full((8, 4), 200, numpy.uint8),
        indices=numpy.array(faces, numpy.uint32).ravel(), triangle_elements=numpy.zeros(12, numpy.uint32),
        elements=["IfcWall 0abc „Wand“"], origin=numpy.array([500000.0, 5400000.0, 120.0]),
        info={"source": "Haus.ifc", "elements": 1, "scale": 0.5},
    )


def test_a_preview_survives_the_round_trip(tmp_path):
    mesh = _cube()
    save_preview(mesh, tmp_path / "p.npz")
    loaded = load_preview(tmp_path / "p.npz")
    assert loaded is not None and loaded.triangle_count == 12
    assert numpy.array_equal(loaded.positions, mesh.positions) and numpy.array_equal(loaded.indices, mesh.indices)
    assert loaded.origin.tolist() == [500000.0, 5400000.0, 120.0]
    assert loaded.elements == ["IfcWall 0abc „Wand“"]
    assert loaded.info == {"source": "Haus.ifc", "elements": 1, "scale": 0.5}
    lo, hi = loaded.bounds()
    assert lo.tolist() == [0, 0, 0] and hi.tolist() == [1, 1, 1]


def test_damaged_or_foreign_previews_are_ignored(tmp_path):
    (tmp_path / "junk.npz").write_bytes(b"not a zip")
    assert load_preview(tmp_path / "junk.npz") is None
    assert load_preview(tmp_path / "missing.npz") is None
    mesh = _cube()
    mesh.indices = mesh.indices.copy()
    mesh.indices[0] = 99  # points past the vertices
    save_preview(mesh, tmp_path / "bad.npz")
    assert load_preview(tmp_path / "bad.npz") is None
    numpy.savez(tmp_path / "old.npz", version=numpy.array(PREVIEW_FORMAT_VERSION + 1))
    assert load_preview(tmp_path / "old.npz") is None
