"""Writer for the openNURBS binary archive format, as far as needed for planar Brep objects.

rhino3dm cannot build or join polysurfaces, but it can decode an object from its archive
representation (`CommonObject.Decode`). This module produces that representation; the layout
follows the documented openNURBS file format (openNURBS is MIT licensed).
"""
from __future__ import annotations

import base64
import functools
import struct
import uuid
import zlib
from collections.abc import Sequence

Point = Sequence[float]

TCODE_SHORT = 0x80000000
TCODE_CRC = 0x8000
TCODE_ANONYMOUS_CHUNK = 0x40000000 | TCODE_CRC
TCODE_OPENNURBS_CLASS = 0x00027FFA
TCODE_OPENNURBS_CLASS_UUID = 0x00027FFB | TCODE_CRC
TCODE_OPENNURBS_CLASS_DATA = 0x00027FFC | TCODE_CRC
TCODE_OPENNURBS_CLASS_END = 0x00027FFF | TCODE_SHORT

CLASS_POLYLINE_CURVE = uuid.UUID("4ED7D4E6-E947-11d3-BFE5-0010830122F0")
CLASS_PLANE_SURFACE = uuid.UUID("4ED7D4DF-E947-11d3-BFE5-0010830122F0")
CLASS_BREP = uuid.UUID("60B5DBC5-E660-11d3-BFE4-0010830122F0")

# 3dm archive version the objects are written for (Rhino 7 and later).
ARCHIVE_VERSION = 70

_BYTE = struct.Struct("<B")
_INT = struct.Struct("<i")
_UINT = struct.Struct("<I")
_DOUBLE = struct.Struct("<d")
_POINT = struct.Struct("<3d")
_INTERVAL = struct.Struct("<2d")
_HEADER = struct.Struct("<Iq")
# Class data of a plane surface (version 1.1: origin, x, y and z axis, plane equation, extents, domain).
_PLANE_SURFACE = struct.Struct("<B24d")
_ARRAY_ITEM = _INT.pack(1)
_CLASS_END = _HEADER.pack(TCODE_OPENNURBS_CLASS_END, 0)


class Chunk:
    """A long chunk: typecode, 64-bit length, data and, for CRC typecodes, a CRC32 of its own data.

    Nested chunks are part of the data but not of the CRC, as in openNURBS.
    """

    def __init__(self, typecode: int):
        self.typecode = typecode
        self._parts: list[bytes] = []
        self._counted: list[bytes] = []

    def raw(self, data: bytes) -> Chunk:
        self._parts.append(data)
        self._counted.append(data)
        return self

    def nested(self, data: bytes) -> Chunk:
        self._parts.append(data)
        return self

    def chunk(self, child: Chunk) -> Chunk:
        return self.nested(child.to_bytes())

    def mixed(self, data: bytes, counted: bytes) -> Chunk:
        """Append ``data`` (fields with nested chunks in between) of which only ``counted`` enters the CRC."""
        self._parts.append(data)
        self._counted.append(counted)
        return self

    def byte(self, value: int) -> Chunk:
        return self.raw(_BYTE.pack(value))

    def bool(self, value: bool) -> Chunk:
        return self.byte(1 if value else 0)

    def int(self, value: int) -> Chunk:
        return self.raw(_INT.pack(value))

    def ints(self, values: Sequence[int]) -> Chunk:
        return self.raw(struct.pack(f"<{len(values)}i", *values))

    def int_array(self, values: Sequence[int]) -> Chunk:
        return self.raw(struct.pack(f"<i{len(values)}i", len(values), *values))

    def double(self, value: float) -> Chunk:
        return self.raw(_DOUBLE.pack(value))

    def doubles(self, values: Sequence[float]) -> Chunk:
        return self.raw(struct.pack(f"<{len(values)}d", *values))

    def point(self, p: Point) -> Chunk:
        return self.raw(_POINT.pack(p[0], p[1], p[2]))

    def interval(self, t0: float, t1: float) -> Chunk:
        return self.raw(_INTERVAL.pack(t0, t1))

    def uuid(self, value: uuid.UUID) -> Chunk:
        return self.raw(value.bytes_le)

    def version(self, major: int, minor: int) -> Chunk:
        return self.byte(major * 16 + minor)

    def to_bytes(self) -> bytes:
        body = b"".join(self._parts)
        if self.typecode & TCODE_CRC:
            body += _UINT.pack(zlib.crc32(b"".join(self._counted)))
        return _HEADER.pack(self.typecode, len(body)) + body


def anonymous_chunk(major: int | None = None, minor: int | None = None) -> Chunk:
    """An anonymous chunk, optionally starting with a (major, minor) version as two ints."""
    chunk = Chunk(TCODE_ANONYMOUS_CHUNK)
    if major is not None:
        chunk.int(major).int(minor)
    return chunk


def class_data() -> Chunk:
    return Chunk(TCODE_OPENNURBS_CLASS_DATA)


def write_object(class_id: uuid.UUID, data: Chunk) -> bytes:
    """An object record: class chunk holding the class UUID, the object data and an end marker."""
    return _object_record(class_id, data.to_bytes())


def _object_record(class_id: uuid.UUID, data_chunk: bytes) -> bytes:
    uuid_chunk = _uuid_chunk(class_id)
    length = len(uuid_chunk) + len(data_chunk) + len(_CLASS_END)
    return _HEADER.pack(TCODE_OPENNURBS_CLASS, length) + uuid_chunk + data_chunk + _CLASS_END


@functools.cache
def _uuid_chunk(class_id: uuid.UUID) -> bytes:
    return Chunk(TCODE_OPENNURBS_CLASS_UUID).uuid(class_id).to_bytes()


def _class_record(class_id: uuid.UUID, data: bytes) -> bytes:
    """An object record whose class data ``data`` contains no nested chunks."""
    data_chunk = _HEADER.pack(TCODE_OPENNURBS_CLASS_DATA, len(data) + 4) + data + _UINT.pack(zlib.crc32(data))
    return _object_record(class_id, data_chunk)


def object_array(objects: Sequence[bytes]) -> Chunk:
    """An array of curve or surface records, as stored inside a Brep."""
    chunk = anonymous_chunk().version(1, 0).int(len(objects))
    if objects:
        chunk.mixed(_ARRAY_ITEM + _ARRAY_ITEM.join(objects), _ARRAY_ITEM * len(objects))
    return chunk


def polyline_curve(points: Sequence[Point], dimension: int) -> bytes:
    """A polyline through ``points`` with the parameters 0, 1, 2, ... at its vertices."""
    count = len(points)
    return _class_record(CLASS_POLYLINE_CURVE, struct.pack(
        f"<Bi{3 * count}di{count}di", 0x10, count, *(c for p in points for c in p), count, *range(count), dimension
    ))


def plane_surface(origin: Point, xaxis: Point, yaxis: Point, zaxis: Point, udomain, vdomain) -> bytes:
    """A plane surface whose (u, v) parameters are plain plane coordinates (domain == extents)."""
    offset = -(zaxis[0] * origin[0] + zaxis[1] * origin[1] + zaxis[2] * origin[2])
    return _class_record(CLASS_PLANE_SURFACE, _PLANE_SURFACE.pack(
        0x11, *origin, *xaxis, *yaxis, *zaxis, zaxis[0], zaxis[1], zaxis[2], offset,
        udomain[0], udomain[1], vdomain[0], vdomain[1], udomain[0], udomain[1], vdomain[0], vdomain[1],
    ))


def decode_dict(record: bytes, opennurbs_version: int) -> dict:
    """The dictionary rhino3dm's `Decode` expects for an object record."""
    return {
        "version": 10000,
        "archive3dm": ARCHIVE_VERSION,
        "opennurbs": opennurbs_version,
        "data": base64.b64encode(record).decode("ascii"),
    }
