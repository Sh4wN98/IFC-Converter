"""Finished geometry kept on disk, so that a conversion restarted after a crash or hang goes on.

The Rhino export (3dm) takes the kernel's shapes chunk by chunk. A checkpoint writes the shapes of
every finished chunk to a file in a folder that outlives the conversion process; the next attempt
reads them back instead of computing them again, and computes only the rest. Only what rhino.py
reads of a shape is kept (vertices, faces, items, materials, placement), so this does not serve the
GLB/OBJ serializers, which need the kernel's own objects.

The files are written by this program for itself, in a folder of its own in the local temp folder,
and read with an unpickler that only rebuilds plain data (no classes, no code).
"""

from __future__ import annotations

import io
import logging
import os
import pickle
from collections.abc import Iterator
from pathlib import Path

import numpy

log = logging.getLogger(__name__)

# Chunk files are named chunk-<number>.bin; a file appears complete or not at all (os.replace).
_PATTERN = "chunk-*.bin"


class Checkpoint:
    """The finished chunks of a conversion in ``folder`` (which the caller creates and removes)."""

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self._records: list[tuple] = []
        self._next = len(self._files())
        self._broken = False
        self.written = 0  # chunks written by this attempt

    def done_ids(self) -> set[int]:
        """The step ids of the products in the finished chunks."""
        return {id_ for ids, _ in self.replay(shapes=False) for id_ in ids}

    def replay(self, shapes: bool = True) -> Iterator[tuple[list[int], list]]:
        """The finished chunks, in the order they were written: their product ids and their shapes.

        A file that cannot be read (e.g. the disk is full) ends the replay: what follows it is
        computed again.
        """
        for path in self._files():
            try:
                with open(path, "rb") as file:
                    ids, records = _load(file)
            except (OSError, pickle.UnpicklingError, EOFError, ValueError, TypeError) as exc:
                log.warning("Zwischenstand %s nicht lesbar (%s), wird neu berechnet", path.name, exc)
                return
            yield ids, [_ReplayShape(*record) for record in records] if shapes else []

    def record(self, shape) -> None:
        """Keep ``shape`` for the chunk being computed."""
        if self._broken:
            return
        geometry = shape.geometry
        materials = [
            (material.name, (material.diffuse.r(), material.diffuse.g(), material.diffuse.b()), material.transparency)
            for material in geometry.materials
        ]
        faces = bytes(geometry.faces_buffer)
        # The edges are only read for shapes of lines alone (alignment axes); for others they would
        # take as much room as the faces.
        edges = b"" if faces else bytes(geometry.edges_buffer)
        self._records.append((
            shape.id, shape.context, bytes(shape.transformation_buffer), geometry.id, bytes(geometry.verts_buffer),
            faces, bytes(geometry.item_ids_buffer), bytes(geometry.material_ids_buffer), materials, edges,
        ))

    def chunk_done(self, ids: list[int]) -> None:
        """Write the shapes recorded since the last chunk as the chunk of the products ``ids``."""
        records, self._records = self._records, []
        if self._broken:
            return
        path = self.folder / f"chunk-{self._next:06d}.bin"
        part = path.with_suffix(".part")
        try:
            with open(part, "wb") as file:
                pickle.dump((list(ids), records), file, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(part, path)
        except OSError as exc:
            # No checkpoint is no reason to stop the conversion: a restart computes everything again.
            self._broken = True
            log.warning("Zwischenstand kann nicht gespeichert werden (%s); ohne weiter", exc)
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
            return
        self._next += 1
        self.written += 1

    def _files(self) -> list[Path]:
        try:
            return sorted(self.folder.glob(_PATTERN))
        except OSError:
            return []


class _PlainUnpickler(pickle.Unpickler):
    """Rebuilds only lists, tuples, numbers, strings and bytes."""

    def find_class(self, module: str, name: str):
        raise pickle.UnpicklingError(f"not plain data: {module}.{name}")


def _load(file: io.BufferedReader) -> tuple[list[int], list[tuple]]:
    ids, records = _PlainUnpickler(file).load()
    if not isinstance(ids, list) or not isinstance(records, list):
        raise ValueError("unexpected content")
    return ids, records


class _Color:
    def __init__(self, rgb: tuple[float, float, float]):
        self._rgb = rgb

    def r(self) -> float:
        return self._rgb[0]

    def g(self) -> float:
        return self._rgb[1]

    def b(self) -> float:
        return self._rgb[2]


class _Material:
    def __init__(self, name: str, rgb: tuple[float, float, float], transparency: float):
        self.name, self.diffuse, self.transparency = name, _Color(rgb), transparency


class _Geometry:
    def __init__(self, id_, verts, faces, item_ids, material_ids, materials, edges):
        self.id = id_
        self.verts_buffer, self.faces_buffer, self.edges_buffer = verts, faces, edges
        self.item_ids_buffer, self.material_ids_buffer = item_ids, material_ids
        self.materials = [_Material(*material) for material in materials]

    @property
    def edges(self) -> tuple[int, ...]:
        return tuple(numpy.frombuffer(self.edges_buffer, dtype=numpy.int32).tolist())

    @property
    def verts(self) -> bytes:
        """Only tested for emptiness, as the kernel's tuple of coordinates is."""
        return self.verts_buffer


class _ReplayShape:
    """A shape read back from a checkpoint, with the attributes of the kernel's shape that the
    Rhino export reads."""

    def __init__(
        self, id_, context, transformation, geometry_id, verts, faces, item_ids, material_ids, materials, edges,
    ):
        self.id, self.context, self.transformation_buffer = id_, context, transformation
        self.geometry = _Geometry(geometry_id, verts, faces, item_ids, material_ids, materials, edges)
