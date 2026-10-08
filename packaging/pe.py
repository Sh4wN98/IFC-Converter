"""Read and set the default thread stack size of a Windows executable (PE32+ header).

Windows gives every thread that is created without an explicit stack size the size recorded in the
executable's header: 1 MB for the PyInstaller bootloader. The geometry kernels recurse once per level
of nesting (IfcBooleanResult chains, nested IfcMappedItems), and a model with a few thousand levels
overflowed that stack ("Windows fatal exception: stack overflow", exit code 0xC00000FD), while
Linux's 8 MB default hid it. The memory is only reserved; pages are committed as the stack grows.
"""

from __future__ import annotations

import struct
from pathlib import Path

PE32_PLUS = 0x20B
# Offsets in the PE32+ optional header.
CHECKSUM = 64
STACK_RESERVE = 72


def _optional_header(data: bytes) -> int:
    if data[:2] != b"MZ":
        raise ValueError("not an executable (no MZ header)")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("no PE signature")
    optional = pe + 24  # signature + COFF file header
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic != PE32_PLUS:
        raise ValueError(f"not a 64-bit executable (optional header magic {magic:#x})")
    return optional


def stack_reserve(exe: Path) -> int:
    """The default thread stack size (bytes) recorded in ``exe``."""
    data = Path(exe).read_bytes()
    return struct.unpack_from("<Q", data, _optional_header(data) + STACK_RESERVE)[0]


def set_stack_reserve(exe: Path, size: int) -> None:
    """Record ``size`` bytes as the default thread stack size of ``exe`` and update its checksum."""
    data = bytearray(Path(exe).read_bytes())
    optional = _optional_header(data)
    struct.pack_into("<Q", data, optional + STACK_RESERVE, size)
    struct.pack_into("<I", data, optional + CHECKSUM, _checksum(data, optional + CHECKSUM))
    Path(exe).write_bytes(data)


def _checksum(data: bytearray, checksum_offset: int) -> int:
    """The PE image checksum (as computed by imagehlp's CheckSumMappedFile)."""
    padded = bytes(data) + b"\0" * (len(data) % 2)
    words = struct.unpack(f"<{len(padded) // 2}H", padded)
    skip = checksum_offset // 2  # the checksum field itself (two 16-bit words) counts as zero
    total = sum(words) - words[skip] - words[skip + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return total + len(data)
