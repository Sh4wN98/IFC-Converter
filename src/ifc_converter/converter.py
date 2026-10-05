from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as geom

FORMATS = ("glb", "obj", "3dm")

# Called with the conversion progress in percent (0-100). It may raise to abort the conversion.
ProgressCallback = Callable[[int], None]


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
) -> ConversionResult:
    """Convert an IFC file to GLB, OBJ (plus .mtl) or Rhino 3DM and return what was written."""
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported format '{fmt}', choose one of: {', '.join(FORMATS)}")

    input_path = Path(input_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    output_path = Path(output_path) if output_path else input_path.with_suffix(f".{fmt}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model = ifcopenshell.open(str(input_path))
    threads = threads or multiprocessing.cpu_count()

    if fmt == "3dm":
        from ifc_converter.rhino import write_3dm

        elements = write_3dm(model, output_path, threads, progress)
    else:
        elements = _serialize(model, output_path, fmt, threads, progress)

    if progress:
        progress(100)
    return ConversionResult(output=output_path, elements=elements)


def _serialize(model, output_path: Path, fmt: str, threads: int, progress: ProgressCallback | None) -> int:
    """Write GLB/OBJ with IfcOpenShell's built-in serializers."""
    settings = geom.settings()

    # Geometry from the iterator is already in metres, so the scale is fixed at 1.
    serializer = getattr(geom.serializers, fmt)(str(output_path), settings)
    serializer.setFile(model)
    serializer.setUnitNameAndMagnitude("METER", 1.0)
    serializer.writeHeader()

    elements = 0
    iterator = geom.iterator(settings, model, threads)
    if iterator.initialize():
        while True:
            serializer.write(iterator.get())
            elements += 1
            if progress:
                progress(iterator.progress())
            if not iterator.next():
                break
    serializer.finalize()
    return elements
