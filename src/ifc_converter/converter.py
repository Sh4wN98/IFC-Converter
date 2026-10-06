from __future__ import annotations

import multiprocessing
import os
import sys
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.util.element
import ifcopenshell.util.unit

FORMATS = ("glb", "obj", "3dm")
# How the Rhino export represents elements: joined planar polysurfaces (with meshes for elements
# too detailed for that), or meshes only. GLB and OBJ are always meshes.
GEOMETRIES = ("brep", "mesh")

# Opening volumes would cover every window and door; space volumes would hide the building inside.
# The Rhino export keeps spaces on their own layer instead, where they are easy to switch off.
# Grids are only lines, which GLB/OBJ meshes cannot show (the Rhino export writes them as curves).
EXCLUDED_CLASSES = ["IfcOpeningElement", "IfcSpace", "IfcGrid"]

# Geometry kernels of IfcOpenShell. The hybrid one (CGAL for meshes and simple solids, OpenCASCADE
# for the rest) was 3-13x faster on real models with the same geometry in all but 1 of ~8000 elements,
# and handles large triangulated terrain in seconds where OpenCASCADE alone took over 20 minutes.
KERNELS = {"hybrid": "hybrid-cgal-simple-opencascade", "opencascade": "opencascade"}
# IFC_CONVERTER_KERNEL overrides the default, also for conversions running in child processes.
DEFAULT_KERNEL = "hybrid"
_kernel: ContextVar[str | None] = ContextVar("kernel", default=None)
# Number of elements iter_shapes was asked to process during the current conversion.
_candidates: ContextVar[list[int] | None] = ContextVar("candidates", default=None)

# The measure type of a conversion factor per unit type, for repair_units.
UNIT_MEASURES = {
    "LENGTHUNIT": "IfcLengthMeasure",
    "AREAUNIT": "IfcAreaMeasure",
    "VOLUMEUNIT": "IfcVolumeMeasure",
    "PLANEANGLEUNIT": "IfcPlaneAngleMeasure",
}

# Called with the conversion progress in percent (0-100). It may raise to abort the conversion.
# The first call (0) comes once the IFC file has been read, which can take minutes for large models.
ProgressCallback = Callable[[int], None]

# The geometry iterator keeps every shape it has produced until it is destroyed, so its memory
# grows with the model. Running a fresh iterator per chunk of elements keeps that bounded.
CHUNK_SIZE = 200

# Each geometry thread can need this much RAM for a heavy element (a detailed Revit family took
# ~700 MB), so fewer threads run when memory gets tight.
MEMORY_PER_THREAD = 1024 ** 3

# Expected RAM use, measured on 60 real models (40-180 MB): reading the IFC takes 5.7-6x its size,
# converting adds 1-2 GB (geometry threads, and for 3dm the output, which stays in memory until it is
# written). Peaks were 6-13x the IFC size for GLB and 9-25x for 3dm on MEP-heavy models.
MEMORY_PER_IFC_BYTE = 7
MEMORY_BASE = 2 * 1024 ** 3


@dataclass
class ConversionResult:
    output: Path
    elements: int
    # Elements with a shape representation that produced no geometry (unsupported or broken shapes).
    skipped: int = 0


def convert(
    input_path: str | Path,
    output_path: str | Path | None = None,
    fmt: str = "glb",
    threads: int | None = None,
    progress: ProgressCallback | None = None,
    geometry: str = "brep",
    kernel: str | None = None,
) -> ConversionResult:
    """Convert an IFC file to GLB, OBJ (plus .mtl) or Rhino 3DM and return what was written.

    ``geometry`` ("brep" or "mesh") only affects the Rhino export. ``kernel`` picks the geometry
    kernel (see KERNELS); by default IFC_CONVERTER_KERNEL or DEFAULT_KERNEL.
    """
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported format '{fmt}', choose one of: {', '.join(FORMATS)}")
    geometry = geometry.lower()
    if geometry not in GEOMETRIES:
        raise ValueError(f"Unsupported geometry '{geometry}', choose one of: {', '.join(GEOMETRIES)}")

    kernel = (kernel or os.environ.get("IFC_CONVERTER_KERNEL") or DEFAULT_KERNEL).lower()
    if kernel not in KERNELS:
        raise ValueError(f"Unsupported kernel '{kernel}', choose one of: {', '.join(KERNELS)}")

    input_path = Path(input_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    output_path = Path(output_path) if output_path else input_path.with_suffix(f".{fmt}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        model = ifcopenshell.open(str(input_path))
    except ifcopenshell.SchemaError as exc:
        supported = ", ".join(s for s in ifcopenshell.ifcopenshell_wrapper.schema_names() if s.startswith("IFC"))
        raise ValueError(f"IFC-Version wird nicht unterstützt ({exc}). Unterstützt werden: {supported}.") from exc
    repair_units(model)
    merge_projects(model)
    threads = threads or multiprocessing.cpu_count()
    token = _kernel.set(kernel)
    candidates = [0]
    candidates_token = _candidates.set(candidates)
    if progress:
        progress(0)

    try:
        if fmt == "3dm":
            from ifc_converter.rhino import write_3dm

            elements = write_3dm(model, output_path, threads, progress, geometry)
        else:
            elements = _serialize(model, output_path, fmt, threads, progress)
    finally:
        _kernel.reset(token)
        _candidates.reset(candidates_token)

    if elements == 0:
        # An empty file reported as success would look like a finished conversion.
        for path in (output_path, output_path.with_suffix(".mtl") if fmt == "obj" else None):
            if path:
                path.unlink(missing_ok=True)
        if candidates[0]:
            raise ValueError(
                f"Keine Geometrie erzeugt: keines der {candidates[0]} Bauteile mit Geometrie ließ sich "
                "umwandeln (vermutlich nicht unterstützte Geometrietypen)."
            )
        raise ValueError("Die Datei enthält keine Bauteile mit Geometrie.")

    if progress:
        progress(100)
    return ConversionResult(output=output_path, elements=elements, skipped=max(0, candidates[0] - elements))


def repair_units(model: ifcopenshell.file) -> None:
    """Repair conversion-based units that IfcOpenShell cannot read, in memory.

    OpenRoads Designer writes the conversion factor as a bare number instead of a typed measure,
    and declares its square and cubic feet as length units. IfcOpenShell then ignores all units and
    reads the model as metres: a model in US survey feet came out 3.28x too large.
    """
    for unit in model.by_type("IfcConversionBasedUnit"):
        factor = unit.ConversionFactor
        if factor is None:
            continue
        # The unit the factor converts to tells the real unit type (SQUARE_METRE: an area unit).
        actual_type = getattr(factor.UnitComponent, "UnitType", None)
        if actual_type and actual_type != unit.UnitType and "USERDEFINED" not in (actual_type, unit.UnitType):
            unit.UnitType = actual_type
        if isinstance(factor.ValueComponent, (int, float)):
            measure = UNIT_MEASURES.get(unit.UnitType, "IfcRatioMeasure")
            factor.ValueComponent = model.create_entity(measure, float(factor.ValueComponent))


def merge_projects(model: ifcopenshell.file) -> None:
    """Merge the projects of a federated model into the first one, in memory.

    Some exports combine several models in one file, each with its own IfcProject (210 King: the
    architecture, electrical and MEP models). IfcOpenShell only reads the units of a file with
    exactly one project, otherwise it takes lengths as metres and angles as radians: that model in
    feet came out 3.28x too large, and the arcs of arched openings, trimmed in degrees, made broken
    opening solids. Each facade wall then lost all of its openings after ~25 s of failing booleans.
    Projects with different units are left alone, as no single unit would fit them all.
    """
    projects = model.by_type("IfcProject")
    if len(projects) < 2 or len({_unit_scales(project) for project in projects}) > 1:
        return
    for project in projects[1:]:
        # Re-link what belongs to the project (its sites, properties) before removing it.
        for inverse in model.get_inverse(project):
            ifcopenshell.util.element.replace_attribute(inverse, project, projects[0])
        model.remove(project)


def _unit_scales(project: ifcopenshell.entity_instance) -> tuple:
    """The length and plane angle units of a project, as factors to metres and radians."""
    units = project.UnitsInContext.Units if project.UnitsInContext else ()
    return tuple(
        next((round(ifcopenshell.util.unit.get_unit_scale(unit), 12) for unit in units
              if getattr(unit, "UnitType", None) == unit_type), None)
        for unit_type in ("LENGTHUNIT", "PLANEANGLEUNIT")
    )


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
        if _has_3d_shape(product) and not any(product.is_a(name) for name in exclude)
    ]
    counter = _candidates.get()
    if counter is not None:
        counter[0] += len(products)
    library = geometry_library()
    local = not settings.get("use-world-coords")
    for start in range(0, len(products), CHUNK_SIZE):
        chunk = products[start:start + CHUNK_SIZE]
        done = set()
        # In local coordinates the kernel returns empty geometry for type geometry (mapped items)
        # with openings cut into it, e.g. Revit cabinets with a sink cut-out: those are redone in
        # world coordinates, which the serializers and the Rhino export accept as well.
        empty = []
        for shape in _iterate(model, settings, threads, chunk, library):
            done.add(shape.id)
            if local and not shape.geometry.verts:
                empty.append(model.by_id(shape.id))
            else:
                yield shape
        if library != KERNELS["opencascade"]:
            # The hybrid kernel gives up on some shapes that OpenCASCADE can still build.
            missing = [product for product in chunk if product.id() not in done]
            if missing:
                for shape in _iterate(model, settings, threads, missing, KERNELS["opencascade"]):
                    if local and not shape.geometry.verts:
                        empty.append(model.by_id(shape.id))
                    else:
                        yield shape
        if empty:
            settings.set("use-world-coords", True)  # iterators copy their settings
            try:
                world = list(_iterate(model, settings, threads, empty, library))
            finally:
                settings.set("use-world-coords", False)
            yield from world
        _release_memory()
        if progress:
            progress((start + len(chunk)) * progress_share // len(products))


def _has_3d_shape(product: ifcopenshell.entity_instance) -> bool:
    """Whether the product has a representation the 3D geometry kernel can turn into geometry.

    Structural analysis models (e.g. RFEM exports with ~190,000 nodes, joints and member axes) and
    2D plan symbols ("Plan" contexts) produce nothing in the kernel but cost a lot of time, and
    would be reported as elements without geometry. Analytical surface members do become faces.
    """
    if not product.Representation or product.is_a("IfcStructuralActivity"):
        return False
    if product.is_a("IfcStructuralItem") and not product.is_a("IfcStructuralSurfaceMember"):
        return False
    for representation in product.Representation.Representations:
        if not representation.is_a("IfcShapeModel") or not representation.Items:
            continue
        # Bounding boxes and 2D curves (wall axes, space outlines) never become 3D geometry.
        if representation.RepresentationType in ("BoundingBox", "Curve2D"):
            continue
        context = representation.ContextOfItems
        if context and context.is_a("IfcGeometricRepresentationSubContext") and context.ParentContext:
            context = context.ParentContext
        # Some exporters (e.g. FZKViewer) write no context at all; treat that as 3D.
        if context is None or context.ContextType != "Plan":
            return True
    return False


def _iterate(model, settings, threads: int, products: list, library: str) -> Iterator:
    """Yield the shapes of ``products`` from one geometry iterator, which is freed afterwards."""
    iterator = geom.iterator(
        settings, model, _affordable_threads(threads), include=products, geometry_library=library,
    )
    initialized = iterator.initialize()  # False when nothing among the products has geometry...
    if not initialized:
        # ...but also when a single product's representation has no items (invalid, written by
        # OpenRoads for the site), which would drop all of them: retry without those.
        valid = [product for product in products if all(r.Items for r in product.Representation.Representations)]
        if valid and len(valid) < len(products):
            iterator = geom.iterator(
                settings, model, _affordable_threads(threads), include=valid, geometry_library=library,
            )
            initialized = iterator.initialize()
    if initialized:
        while True:
            yield iterator.get()
            if not iterator.next():
                break
    del iterator


def geometry_library() -> str:
    """The IfcOpenShell geometry library of the running conversion, for geom.iterator."""
    return KERNELS[_kernel.get() or os.environ.get("IFC_CONVERTER_KERNEL", DEFAULT_KERNEL).lower()]


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
        if not shape.geometry.verts:  # nothing to write, so it counts as skipped
            continue
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
