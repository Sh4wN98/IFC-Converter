"""Writer for the openNURBS binary archive format, as far as needed for planar Brep objects.

rhino3dm cannot build or join polysurfaces, but it can decode an object from its archive
representation (`CommonObject.Decode`). This module produces that representation; the layout
follows the documented openNURBS file format (openNURBS is MIT licensed).
"""
from __future__ import annotations

import base64
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

CLASS_LINE_CURVE = uuid.UUID("4ED7D4DB-E947-11d3-BFE5-0010830122F0")
CLASS_PLANE_SURFACE = uuid.UUID("4ED7D4DF-E947-11d3-BFE5-0010830122F0")
CLASS_BREP = uuid.UUID("60B5DBC5-E660-11d3-BFE4-0010830122F0")

# 3dm archive version the objects are written for (Rhino 7 and later).
ARCHIVE_VERSION = 70


class Chunk:
    """A long chunk: typecode, 64-bit length, data and, for CRC typecodes, a CRC32 of its own data.

    Nested chunks are part of the data but not of the CRC, as in openNURBS.
    """

    def __init__(self, typecode: int):
        self.typecode = typecode
        self._parts: list[tuple[bytes, bool]] = []

    def raw(self, data: bytes) -> Chunk:
        self._parts.append((data, True))
        return self

    def nested(self, data: bytes) -> Chunk:
        self._parts.append((data, False))
        return self

    def chunk(self, child: Chunk) -> Chunk:
        return self.nested(child.to_bytes())

    def byte(self, value: int) -> Chunk:
        return self.raw(struct.pack("<B", value))

    def bool(self, value: bool) -> Chunk:
        return self.byte(1 if value else 0)

    def int(self, value: int) -> Chunk:
        return self.raw(struct.pack("<i", value))

    def ints(self, values: Sequence[int]) -> Chunk:
        return self.raw(struct.pack(f"<{len(values)}i", *values))

    def int_array(self, values: Sequence[int]) -> Chunk:
        self.int(len(values))
        return self.ints(values) if values else self

    def double(self, value: float) -> Chunk:
        return self.raw(struct.pack("<d", value))

    def doubles(self, values: Sequence[float]) -> Chunk:
        return self.raw(struct.pack(f"<{len(values)}d", *values))

    def point(self, p: Point) -> Chunk:
        return self.doubles((p[0], p[1], p[2]))

    def interval(self, t0: float, t1: float) -> Chunk:
        return self.doubles((t0, t1))

    def uuid(self, value: uuid.UUID) -> Chunk:
        return self.raw(value.bytes_le)

    def version(self, major: int, minor: int) -> Chunk:
        return self.byte(major * 16 + minor)

    def to_bytes(self) -> bytes:
        body = b"".join(data for data, _ in self._parts)
        if self.typecode & TCODE_CRC:
            crc = 0
            for data, counted in self._parts:
                if counted:
                    crc = zlib.crc32(data, crc)
            body += struct.pack("<I", crc)
        return struct.pack("<Iq", self.typecode, len(body)) + body


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
    record = Chunk(TCODE_OPENNURBS_CLASS)
    record.chunk(Chunk(TCODE_OPENNURBS_CLASS_UUID).uuid(class_id))
    record.chunk(data)
    record.nested(struct.pack("<Iq", TCODE_OPENNURBS_CLASS_END, 0))
    return record.to_bytes()


def object_array(objects: Sequence[bytes]) -> Chunk:
    """An array of curve or surface records, as stored inside a Brep."""
    chunk = anonymous_chunk().version(1, 0).int(len(objects))
    for record in objects:
        chunk.int(1).nested(record)
    return chunk


def line_curve(start: Point, end: Point, t0: float, t1: float, dimension: int) -> bytes:
    data = class_data().version(1, 0)
    data.point(start).point(end).interval(t0, t1).int(dimension)
    return write_object(CLASS_LINE_CURVE, data)


def plane_surface(origin: Point, xaxis: Point, yaxis: Point, zaxis: Point, udomain, vdomain) -> bytes:
    """A plane surface whose (u, v) parameters are plain plane coordinates (domain == extents)."""
    data = class_data().version(1, 1)
    offset = -(zaxis[0] * origin[0] + zaxis[1] * origin[1] + zaxis[2] * origin[2])
    data.point(origin).point(xaxis).point(yaxis).point(zaxis)
    data.doubles((zaxis[0], zaxis[1], zaxis[2], offset))
    data.interval(*udomain).interval(*vdomain)
    data.interval(*udomain).interval(*vdomain)
    return write_object(CLASS_PLANE_SURFACE, data)


def decode_dict(record: bytes, opennurbs_version: int) -> dict:
    """The dictionary rhino3dm's `Decode` expects for an object record."""
    return {
        "version": 10000,
        "archive3dm": ARCHIVE_VERSION,
        "opennurbs": opennurbs_version,
        "data": base64.b64encode(record).decode("ascii"),
    }
