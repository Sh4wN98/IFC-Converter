"""Preview of an IFC model: a light triangle mesh of the whole model for the viewer in the window.

The preview is computed like a conversion, in a child process (see process.convert_in_child), and
kept in a cache, so that a file shows at once the next time it is selected. It favours speed over
accuracy: the fast geometry kernel, coarse curves, and at most PREVIEW_TRIANGLES triangles.

This module holds the data the viewer draws (PreviewMesh) and how it is stored on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy

# Bumped whenever the stored arrays change; older files are ignored (computed again).
PREVIEW_FORMAT_VERSION = 1


@dataclass
class PreviewMesh:
    """A model as indexed triangles, with one colour per vertex.

    Coordinates are in metres, relative to ``origin`` (float64): the model's own coordinates can be
    hundreds of kilometres out (georeferenced), which single precision on the GPU cannot hold.
    A model point is ``positions[i] + origin``. IFC is Z-up.
    """

    positions: numpy.ndarray  # (V, 3) float32, metres, relative to origin
    colors: numpy.ndarray  # (V, 4) uint8 RGBA; alpha < 255 is transparent (glass)
    indices: numpy.ndarray  # (3 * T,) uint32, counter-clockwise seen from outside
    triangle_elements: numpy.ndarray  # (T,) uint32: index into ``elements`` of each triangle
    elements: list[str]  # labels "IfcClass GlobalId „Name“" (converter.product_label)
    origin: numpy.ndarray = field(default_factory=lambda: numpy.zeros(3))  # (3,) float64
    # Shown under the view: e.g. {"source": "Haus.ifc", "schema": "IFC4", "elements": 1234,
    # "triangles": 456789, "left_out": 0}. Plain str/int/float values only.
    info: dict = field(default_factory=dict)

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3

    def bounds(self) -> tuple[numpy.ndarray, numpy.ndarray]:
        """Minimum and maximum corner of the positions (relative to origin); zeros if empty."""
        if not len(self.positions):
            return numpy.zeros(3, numpy.float32), numpy.zeros(3, numpy.float32)
        return self.positions.min(axis=0), self.positions.max(axis=0)


def save_preview(mesh: PreviewMesh, path: str | Path) -> None:
    """Write ``mesh`` to ``path`` (.npz, plain arrays only), replacing it as a whole."""
    path = Path(path)
    part = path.with_name(path.name + ".part")
    keys = sorted(mesh.info)
    with open(part, "wb") as file:
        numpy.savez(
            file,
            version=numpy.array(PREVIEW_FORMAT_VERSION),
            positions=numpy.ascontiguousarray(mesh.positions, numpy.float32),
            colors=numpy.ascontiguousarray(mesh.colors, numpy.uint8),
            indices=numpy.ascontiguousarray(mesh.indices, numpy.uint32),
            triangle_elements=numpy.ascontiguousarray(mesh.triangle_elements, numpy.uint32),
            elements=numpy.array(mesh.elements, dtype=str) if mesh.elements else numpy.zeros(0, dtype="<U1"),
            origin=numpy.asarray(mesh.origin, numpy.float64),
            info_keys=numpy.array(keys, dtype=str) if keys else numpy.zeros(0, dtype="<U1"),
            info_values=numpy.array([str(mesh.info[key]) for key in keys], dtype=str)
            if keys else numpy.zeros(0, dtype="<U1"),
        )
    part.replace(path)


def load_preview(path: str | Path) -> PreviewMesh | None:
    """The mesh stored at ``path``, or None if it is missing, damaged or of another format version."""
    try:
        with numpy.load(path, allow_pickle=False) as data:
            if int(data["version"]) != PREVIEW_FORMAT_VERSION:
                return None
            info = {}
            for key, value in zip(data["info_keys"].tolist(), data["info_values"].tolist()):
                info[key] = _number(value)
            mesh = PreviewMesh(
                positions=data["positions"].reshape(-1, 3),
                colors=data["colors"].reshape(-1, 4),
                indices=data["indices"].reshape(-1),
                triangle_elements=data["triangle_elements"].reshape(-1),
                elements=data["elements"].tolist(),
                origin=data["origin"].reshape(3),
                info=info,
            )
    except (OSError, KeyError, ValueError, EOFError):
        return None
    if len(mesh.colors) != len(mesh.positions) or len(mesh.indices) % 3 \
            or len(mesh.triangle_elements) != mesh.triangle_count:
        return None
    if len(mesh.indices) and int(mesh.indices.max()) >= len(mesh.positions):
        return None
    return mesh


def _number(text: str) -> str | int | float:
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return text
