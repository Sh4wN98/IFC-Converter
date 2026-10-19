"""Output formats written with IfcOpenShell's built-in geometry serializers (everything but .3dm).

Which of the serializers of IfcOpenShell 0.9.0 are offered, and why not the others (evaluated on
duplex, revit_arc, Clinic Architectural and an IFC4X3 bridge, see tests/test_formats.py):

- ``glb``: binary glTF, triangle meshes, Y-up; each element is a node named after its GlobalId with
  its placement as the node matrix (so the single-precision vertices stay exact far from the
  origin). Streams through two temp files next to the output, limited to 4 GB by the format.
- ``obj`` (+ ``.mtl``): triangle meshes in world coordinates with 15 digits; streams.
- ``dae``: COLLADA 1.4.1, triangle meshes, Z-up, in metres, one node per element (name = GlobalId),
  materials from the IFC styles. The whole document is kept in memory and written at the end.

Not offered:

- ``stp``/``step``: OpenCASCADE's STEP writer takes the kernel's B-rep without the element placement
  (a 17 m wall of the duplex sat at the origin; "use-world-coords" does not apply to native output),
  names every face "product-<uuid>" instead of the GlobalId and keeps the whole model in memory
  (61 MB for the 2 MB duplex). Left in SERIALIZERS for experiments, not in converter.FORMATS.

- ``gltf``: IfcOpenShell maps it to the GLB serializer, which writes a binary .glb whatever the
  extension (no JSON .gltf with a .bin side file), so it would only be GLB under another name.
- ``usd``/``usda``/``usdc``: not compiled into the IfcOpenShell 0.9.0 wheels ("No geometry
  serializer registered for usd").
- ``iges``/``igs``: OpenCASCADE's IGES writer declares the file in millimetres while the numbers are
  the metres of the geometry, so every CAD program reads the model 1000x too small.
- ``svg``: 2D plan sections, not a 3D export; ``ttl``: RDF/GeoSPARQL text, not a CAD format.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell.geom as geom
import ifcopenshell.ifcopenshell_wrapper as wrapper

GB = 1024 ** 3


@dataclass(frozen=True)
class Serializer:
    """One output format written by ``ifcopenshell.geom.serializers.<name>``."""

    name: str  # the attribute of geom.serializers
    suffix: str  # of the output file, which is also the format key (haus.ifc -> haus.stp)
    side_suffixes: tuple[str, ...] = ()  # files written next to the output with the same stem (.mtl)
    temp_names: tuple[str, ...] = ()  # appended to the output name while writing, removed at the end
    native: bool = False  # exact B-rep (NATIVE iterator output), OpenCASCADE only
    streams: bool = True  # elements are written as they come, else kept until the end
    max_bytes: int | None = None  # the largest file the format can hold
    phase: str = ""  # the German text of the "write" phase


SERIALIZERS: dict[str, Serializer] = {
    "glb": Serializer(
        "glb", ".glb", temp_names=(".indices.tmp", ".vertices.tmp"), max_bytes=4 * GB,
        phase="GLB-Datei wird geschrieben …",
    ),
    "obj": Serializer("obj", ".obj", side_suffixes=(".mtl",), phase="OBJ-Datei wird geschrieben …"),
    "stp": Serializer(
        "step", ".stp", native=True, streams=False,
        phase="STEP-Datei wird geschrieben (exakte Flächen, dauert bei großen Modellen Minuten) …",
    ),
    "dae": Serializer("collada", ".dae", streams=False, phase="DAE-Datei wird geschrieben …"),
}

# Native (B-rep) output: the kernel's shapes as OpenCASCADE shapes instead of triangle meshes.
NATIVE_OUTPUT = wrapper.NATIVE


def output_files(target: Path, fmt: str, temp: bool = False) -> list[Path]:
    """The files a conversion to ``target`` writes: the output, its side files (OBJ: the .mtl) and
    with ``temp`` the temporary files a crashed or terminated conversion may leave behind (GLB)."""
    serializer = SERIALIZERS.get(fmt)
    if serializer is None:  # 3dm, preview
        return [target]
    files = [target] + [target.with_suffix(suffix) for suffix in serializer.side_suffixes]
    if temp:
        files += [target.with_name(target.name + name) for name in serializer.temp_names]
    return files


def requires_opencascade(fmt: str) -> bool:
    """Whether ``fmt`` can only be written from OpenCASCADE geometry (exact B-rep)."""
    serializer = SERIALIZERS.get(fmt)
    return serializer is not None and serializer.native


def write(
    model, target: Path, fmt: str, threads: int, progress: Callable[[int], None] | None,
    report: Callable[[str, str], None] = lambda phase, text: None,
) -> int:
    """Write ``model`` to ``target`` with the serializer of ``fmt`` and return the elements written.

    Shapes come from converter.iter_shapes (chunk by chunk, excluded classes left out); for a
    native format the kernel strategy is "opencascade" whatever the conversion asked for.
    """
    from ifc_converter import converter

    serializer = SERIALIZERS[fmt]
    settings = geom.settings()
    settings.set("mesher-linear-deflection", converter.LINEAR_DEFLECTION)
    if serializer.native:
        settings.set("iterator-output", NATIVE_OUTPUT)
        # The triangulating serializers place each element themselves (GLB: node matrices); the STEP
        # writer takes the B-rep as it comes, so the kernel must place it (the duplex came out twice
        # as wide, its mirrored type geometry sitting at the origin).
        settings.set("use-world-coords", True)
    token = converter._kernel.set("opencascade") if serializer.native else None
    try:
        # Geometry from the iterator is already in metres, so the scale is fixed at 1.
        writer = getattr(geom.serializers, serializer.name)(str(target), settings)
        writer.setFile(model)
        writer.setUnitNameAndMagnitude("METER", 1.0)
        writer.writeHeader()

        elements = 0
        for shape in converter.iter_shapes(
            model, settings, threads, converter.EXCLUDED_CLASSES, progress, 95, status=report,
        ):
            if not converter.has_geometry(shape):  # nothing to write, so it counts as skipped
                continue
            writer.write(shape)
            elements += 1
        report("write", serializer.phase)
        writer.finalize()
        # The COLLADA serializer writes its document when it is destroyed, the GLB one removes its
        # temp files then: both must have happened before the output is copied or measured.
        del writer
    finally:
        if token is not None:
            converter._kernel.reset(token)
    if elements and not target.is_file():
        # The STEP writer drops shapes it cannot transfer without a word and writes no file at all
        # when none is left; an empty success would look like a finished conversion.
        raise ValueError(f"Die {fmt.upper()}-Datei konnte nicht geschrieben werden: der Serializer hat keines "
                         f"der {elements} Bauteile übernommen.")
    return elements
