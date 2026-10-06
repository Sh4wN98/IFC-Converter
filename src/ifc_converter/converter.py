from __future__ import annotations

import multiprocessing
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as geom

FORMATS = ("glb", "obj", "3dm")
# How the Rhino export represents elements: joined planar polysurfaces (with meshes for elements
# too detailed for that), or meshes only. GLB and OBJ are always meshes.
GEOMETRIES = ("brep", "mesh")

# Opening volumes would cover every window and door; space volumes would hide the building inside.
# The Rhino export keeps spaces on their own layer instead, where they are easy to switch off.
EXCLUDED_CLASSES = ["IfcOpeningElement", "IfcSpace"]

# Called with the conversion progress in percent (0-100). It may raise to abort the conversion.
# The first call (0) comes once the IFC file has been read, which can take minutes for large models.
ProgressCallback = Callable[[int], None]

# The geometry iterator keeps every shape it has produced until it is destroyed, so its memory
# grows with the model. Running a fresh iterator per chunk of elements keeps that bounded.
CHUNK_SIZE = 200

# Each geometry thread can need this much RAM for a heavy element (a detailed Revit family took
# ~700 MB), so fewer threads run when memory gets tight.
MEMORY_PER_THREAD = 1024 ** 3

# Expected RAM use: the parsed model takes ~3x the IFC size (measured on a 140 MB Revit export),
# the output meshes about as much as the IFC again, plus a base for the geometry threads.
MEMORY_PER_IFC_BYTE = 5
MEMORY_BASE = 1024 ** 3


@dataclass
class ConversionResult:
    output: Path
    elements: int


def convert(
    input_path: str | Path,
    output_path: str | Path | None = None,
    fmt: str = "glb",
    threads: int | None = None,
    progress: ProgressCallback | None = None,
    geometry: str = "brep",
) -> ConversionResult:
    """Convert an IFC file to GLB, OBJ (plus .mtl) or Rhino 3DM and return what was written.

    ``geometry`` ("brep" or "mesh") only affects the Rhino export.
    """
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported format '{fmt}', choose one of: {', '.join(FORMATS)}")
    geometry = geometry.lower()
    if geometry not in GEOMETRIES:
        raise ValueError(f"Unsupported geometry '{geometry}', choose one of: {', '.join(GEOMETRIES)}")

    input_path = Path(input_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    output_path = Path(output_path) if output_path else input_path.with_suffix(f".{fmt}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model = ifcopenshell.open(str(input_path))
    threads = threads or multiprocessing.cpu_count()
    if progress:
        progress(0)

    if fmt == "3dm":
        from ifc_converter.rhino import write_3dm

        elements = write_3dm(model, output_path, threads, progress, geometry)
    else:
        elements = _serialize(model, output_path, fmt, threads, progress)

    if progress:
        progress(100)
    return ConversionResult(output=output_path, elements=elements)


def iter_shapes(
    model: ifcopenshell.file,
    settings: geom.settings,
    threads: int,
    exclude: list[str],
    progress: ProgressCallback | None = None,
    progress_share: int = 100,
) -> Iterator:
    """Yield the triangulated shape of every product, computed chunk by chunk to cap memory use.

    Progress is reported from 0 up to ``progress_share`` percent.
    """
    products = [
        product for product in model.by_type("IfcProduct")
        if product.Representation and not any(product.is_a(name) for name in exclude)
    ]
    for start in range(0, len(products), CHUNK_SIZE):
        chunk = products[start:start + CHUNK_SIZE]
        iterator = geom.iterator(settings, model, _affordable_threads(threads), include=chunk)
        if iterator.initialize():  # False when nothing in this chunk has geometry
            while True:
                yield iterator.get()
                if not iterator.next():
                    break
        del iterator
        _release_memory()
        if progress:
            progress((start + len(chunk)) * progress_share // len(products))


def _affordable_threads(threads: int) -> int:
    """At most ``threads``, but no more than the free memory can carry."""
    available = available_memory()
    if available is None:
        return threads
    return max(1, min(threads, available // MEMORY_PER_THREAD))


def _release_memory() -> None:
    """Hand memory freed by the geometry kernel back to the OS.

    glibc keeps freed blocks of the iterator's worker threads in per-thread arenas, so without
    trimming the process size grows chunk after chunk even though nothing is in use any more.
    """
    if _malloc_trim:
        _malloc_trim(0)


def _load_malloc_trim():
    if not sys.platform.startswith("linux"):
        return None
    try:
        import ctypes

        return ctypes.CDLL("libc.so.6").malloc_trim
    except (OSError, AttributeError):  # not glibc, e.g. musl
        return None


_malloc_trim = _load_malloc_trim()


def _serialize(model, output_path: Path, fmt: str, threads: int, progress: ProgressCallback | None) -> int:
    """Write GLB/OBJ with IfcOpenShell's built-in serializers."""
    settings = geom.settings()

    # Geometry from the iterator is already in metres, so the scale is fixed at 1.
    serializer = getattr(geom.serializers, fmt)(str(output_path), settings)
    serializer.setFile(model)
    serializer.setUnitNameAndMagnitude("METER", 1.0)
    serializer.writeHeader()

    elements = 0
    for shape in iter_shapes(model, settings, threads, EXCLUDED_CLASSES, progress, 95):
        serializer.write(shape)
        elements += 1
    serializer.finalize()
    return elements


def memory_warning(input_path: str | Path) -> str | None:
    """A warning if the file probably needs more RAM than the machine has free, else None."""
    needed = Path(input_path).stat().st_size * MEMORY_PER_IFC_BYTE + MEMORY_BASE
    available = available_memory()
    if available is None or needed <= available:
        return None
    return (
        f"{Path(input_path).name} braucht voraussichtlich ca. {_gb(needed)} GB Arbeitsspeicher, "
        f"frei sind nur {_gb(available)} GB. Andere Programme schließen, sonst wird es sehr langsam "
        f"oder die Umwandlung bricht ab."
    )


def _gb(size: int) -> str:
    return f"{size / 1024 ** 3:.1f}".replace(".", ",")


def available_memory() -> int | None:
    """Free physical memory in bytes, or None if it cannot be determined."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus(dwLength=ctypes.sizeof(MemoryStatus))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullAvailPhys
        if sys.platform == "darwin":
            return None
        with open("/proc/meminfo") as meminfo:
            for line in meminfo:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, AttributeError):
        pass
    return None
