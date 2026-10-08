from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
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

# Geometry libraries of IfcOpenShell. The hybrid one (CGAL for meshes and simple solids, OpenCASCADE
# for the rest) is 3-13x faster on real models and handles large triangulated terrain in seconds where
# OpenCASCADE alone took over 20 minutes. But it drops or duplicates faces of some elements depending
# on the thread count and on the other elements computed with them (an ArchiCAD wall lost 24 % of its
# surface, Revit families and skylights got faces twice), so the result is not reproducible.
LIBRARIES = {"hybrid": "hybrid-cgal-simple-opencascade", "opencascade": "opencascade"}
# Kernel strategies: "accurate" computes everything with OpenCASCADE except elements made only of
# large triangle meshes (see _triangle_mesh_only), which the hybrid kernel passes through unchanged
# (identical to OpenCASCADE on every such element of the test models) in a fraction of the time.
# "hybrid" uses the hybrid kernel for everything (OpenCASCADE where it gives up), "opencascade" only
# OpenCASCADE.
KERNELS = ("accurate", "hybrid", "opencascade")
# IFC_CONVERTER_KERNEL overrides the default, also for conversions running in child processes.
DEFAULT_KERNEL = "accurate"
# "accurate" leaves triangle meshes with fewer triangles to OpenCASCADE: they take it no time.
MIN_HYBRID_TRIANGLES = 1000
# Representations that never become a body (curves, boxes, points), for _triangle_mesh_only.
NON_BODY_TYPES = ("Curve", "Curve2D", "Curve3D", "BoundingBox", "Point", "PointCloud")
_kernel: ContextVar[str | None] = ContextVar("kernel", default=None)
# Labels of the products of the running conversion that produced no geometry.
_missing: ContextVar[list | None] = ContextVar("missing", default=None)
# (position callback, step ids to compute one by one, step ids to skip) of the running conversion.
_recovery: ContextVar[tuple | None] = ContextVar("recovery", default=None)
# Number of elements iter_shapes was asked to process during the current conversion.
_candidates: ContextVar[list[int] | None] = ContextVar("candidates", default=None)

# The measure type of a conversion factor per unit type, for repair_units.
UNIT_MEASURES = {
    "LENGTHUNIT": "IfcLengthMeasure",
    "AREAUNIT": "IfcAreaMeasure",
    "VOLUMEUNIT": "IfcVolumeMeasure",
    "PLANEANGLEUNIT": "IfcPlaneAngleMeasure",
}

# Largest distance (metres) of the triangles of curved surfaces from the true surface. The kernels'
# default (1 mm) equals Rhino's 1 mm tolerance; half of it keeps round columns, pipes and arcs well
# inside it, for about 1 % larger files (measured on Clinic, Revit STR/MEP).
LINEAR_DEFLECTION = 0.0005

# Called with the conversion progress in percent (0-100). It may raise to abort the conversion.
# The first call (0) comes once the IFC file has been read, which can take minutes for large models.
ProgressCallback = Callable[[int], None]
# Called with the phase ("read", "geometry", "write", "copy") and a short German description when the
# conversion enters a phase or makes progress within one. Reading the IFC, writing the output and
# copying it to a network folder can each take minutes without any percentage moving.
StatusCallback = Callable[[str, str], None]
# Called with "chunk" or "element", the step ids of the products about to be computed and a label
# ("IfcWall 2O2Fr…"), so that after a crash or a hang the parent knows where it happened.
PositionCallback = Callable[[str, list, str], None]

# Products whose geometry is nested deeper than this (IfcBooleanResult chains, IfcMappedItems within
# IfcMappedItems; normal elements have fewer than 10 levels) are computed one by one in a thread of
# our own with DEEP_STACK of stack. The kernels recurse once per level, and in their worker threads
# a model with thousands of levels overflowed the stack: a crash (0xC00000FD), or with a larger main
# thread stack a conversion that hung at 0 % CPU for good.
DEEP_NESTING = 100
# The depth of geometry that contains itself (IfcMappedItem or boolean operands referring back):
# such products are not computed at all.
CYCLIC = 10 ** 9
# More geometry items than this behind one product only come from type geometry that contains itself.
MAX_VISITED_ITEMS = 1_000_000
DEEP_STACK = 240 * 1024 ** 2  # Python on Windows accepts less than 256 MB

# Output for a network folder is written to the local temp folder first and copied in one go:
# openNURBS writes in small pieces, each a round trip over the network. Only if the temp folder has
# this many times the IFC's size free (a 3dm with polysurfaces was up to 4.6 times the IFC).
# Seconds to wait before each new attempt to copy output to a network folder (e.g. while the
# connection comes back after a hiccup or a standby).
COPY_RETRY_WAITS = (10, 30, 60, 120)
STAGING_ROOM = 8
COPY_BLOCK = 16 * 1024 ** 2

# The geometry iterator keeps every shape it has produced until it is destroyed, so its memory
# grows with the model. Running a fresh iterator per chunk of elements keeps that bounded. Each
# chunk starts the threads anew and ends with them waiting for its slowest element, so chunks grow
# with the thread count: CHUNK_PER_THREAD elements per thread (on 2 threads, 400 instead of 200
# took the kernel 11-16 s instead of 19-33 s for Clinic_Architectural), at least CHUNK_SIZE and at
# most MAX_CHUNK_SIZE elements (the shapes of 1600 elements took ~10 MB more there).
CHUNK_SIZE = 200
CHUNK_PER_THREAD = 50
MAX_CHUNK_SIZE = 2000

# Cores left free by default for the user's other programs: it is a work PC.
SPARE_CORES = 2
# By default at most this many threads: beyond it the kernel only waits for the Python stage (measured),
# while each thread can hold up to MEMORY_PER_THREAD for a heavy element.
MAX_DEFAULT_THREADS = 16
# The geometry iterator never runs on fewer threads than this. Running on one thread takes another
# code path in IfcOpenShell's hybrid kernel, which gives some mapped items every triangle twice
# (Revit fixtures, ArchiCAD skylights: 212 of 1162 triangles), so the result depended on how much
# memory happened to be free.
MIN_THREADS = 2

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
    # Those elements as "IfcClass GlobalId „Name“" (as far as the geometry step can tell).
    no_geometry: list[str] = field(default_factory=list)
    # Elements left out because the geometry kernel crashed or hung on them (filled in by process).
    crashed: list[str] = field(default_factory=list)


def convert(
    input_path: str | Path,
    output_path: str | Path | None = None,
    fmt: str = "glb",
    threads: int | None = None,
    progress: ProgressCallback | None = None,
    geometry: str = "brep",
    kernel: str | None = None,
    status: StatusCallback | None = None,
    staging_dir: str | Path | None = None,
    position: PositionCallback | None = None,
    isolate_ids: list[int] | None = None,
    skip_ids: list[int] | None = None,
) -> ConversionResult:
    """Convert an IFC file to GLB, OBJ (plus .mtl) or Rhino 3DM and return what was written.

    ``geometry`` ("brep" or "mesh") only affects the Rhino export. ``kernel`` picks the geometry
    kernel (see KERNELS); by default IFC_CONVERTER_KERNEL or DEFAULT_KERNEL. ``status`` gets the
    phases (see StatusCallback). Output for a network folder is written in ``staging_dir`` (or a
    temp folder) first and then copied. ``position``, ``isolate_ids`` and ``skip_ids`` let a caller
    recover from a crash or hang in the kernel: products are computed one by one or left out.
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

    def report(phase: str, text: str) -> None:
        if status:
            status(phase, text)

    report("read", f"IFC-Datei wird gelesen ({size_text(input_path.stat().st_size)}) …")
    try:
        model = ifcopenshell.open(str(input_path))
    except ifcopenshell.SchemaError as exc:
        supported = ", ".join(s for s in ifcopenshell.ifcopenshell_wrapper.schema_names() if s.startswith("IFC"))
        raise ValueError(f"IFC-Version wird nicht unterstützt ({exc}). Unterstützt werden: {supported}.") from exc
    repair_units(model)
    merge_projects(model)
    threads = threads or default_threads()
    token = _kernel.set(kernel)
    candidates = [0]
    candidates_token = _candidates.set(candidates)
    recovery_token = _recovery.set((position, set(isolate_ids or ()), set(skip_ids or ())))
    missing: list[str] = []
    missing_token = _missing.set(missing)
    report("geometry", f"Geometrie wird berechnet ({threads} Threads) …")
    if progress:
        progress(0)

    with _staging(output_path, input_path.stat().st_size, staging_dir) as target:
        try:
            if fmt == "3dm":
                from ifc_converter.rhino import write_3dm

                elements = write_3dm(model, target, threads, progress, geometry, report)
            else:
                elements = _serialize(model, target, fmt, threads, progress, report)
        finally:
            _kernel.reset(token)
            _candidates.reset(candidates_token)
            _recovery.reset(recovery_token)
            _missing.reset(missing_token)

        if elements == 0:
            # An empty file reported as success would look like a finished conversion.
            for path in _output_files(target, fmt):
                path.unlink(missing_ok=True)
            if candidates[0]:
                raise ValueError(
                    f"Keine Geometrie erzeugt: keines der {candidates[0]} Bauteile mit Geometrie ließ sich "
                    "umwandeln (vermutlich nicht unterstützte Geometrietypen)."
                )
            raise ValueError("Die Datei enthält keine Bauteile mit Geometrie.")
        if target != output_path:
            _deliver(target, output_path, fmt, report)

    if progress:
        progress(100)
    return ConversionResult(
        output=output_path, elements=elements, skipped=max(0, candidates[0] - elements), no_geometry=missing,
    )


def size_text(size: int) -> str:
    """A file size in German notation, e.g. "1,2 GB" or "345 MB"."""
    if size >= 1024 ** 3:
        return f"{size / 1024 ** 3:.1f} GB".replace(".", ",")
    return f"{size / 1024 ** 2:.0f} MB"


def _output_files(path: Path, fmt: str) -> list[Path]:
    """The files a conversion to ``path`` writes (OBJ: the .mtl next to it)."""
    return [path, path.with_suffix(".mtl")] if fmt == "obj" else [path]


@contextmanager
def _staging(output_path: Path, ifc_size: int, folder: str | Path | None) -> Iterator[Path]:
    """The path to write to: in ``folder`` (or a new temp folder) for output to a network folder."""
    if not is_network_path(output_path):
        yield output_path
        return
    base = Path(folder) if folder else Path(tempfile.gettempdir())
    if shutil.disk_usage(base).free < STAGING_ROOM * ifc_size + 1024 ** 3:
        yield output_path  # too little room for it locally: write over the network after all
        return
    own = Path(tempfile.mkdtemp(prefix="ifc-converter-", dir=folder))
    try:
        yield own / output_path.name
    finally:
        shutil.rmtree(own, ignore_errors=True)


def is_network_path(path: Path) -> bool:
    """Whether ``path`` is on a network share (Windows: a UNC path or a mapped network drive)."""
    if sys.platform != "win32":
        return False
    text = str(path)
    if text.startswith(("\\\\", "//")):
        return True
    drive = Path(text).drive
    if not drive:
        return False
    try:
        import ctypes

        return ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == 4  # DRIVE_REMOTE
    except (OSError, AttributeError):
        return False


def _deliver(staged: Path, output_path: Path, fmt: str, report: Callable[[str, str], None]) -> None:
    """Copy the staged output to the network folder in large blocks, reporting the progress.

    Each file is copied to "<name>.part" and renamed when complete, so the folder never holds a
    half-written file under the real name; a failed copy is tried again COPY_ATTEMPTS times. If it
    still fails, the staged output is moved to rescue_dir() rather than deleted with the staging
    folder, and the error says where it is.
    """
    files = [(source, output_path.with_suffix(source.suffix)) for source in _output_files(staged, fmt)]
    files = [(source, target) for source, target in files if source.exists()]
    total = sum(source.stat().st_size for source, _ in files)
    report("copy", f"Wird ins Zielverzeichnis kopiert ({size_text(total)}) …")
    done = 0
    for source, target in files:
        for attempt, wait in enumerate((*COPY_RETRY_WAITS, None), 1):
            try:
                _copy(source, target, done, total, report)
                break
            except OSError as exc:
                if wait is None:
                    raise _rescue(files, output_path, exc) from exc
                report("copy", f"Kopieren fehlgeschlagen ({exc.strerror or exc}) – neuer Versuch {attempt + 1} "
                               f"in {wait} s …")
                time.sleep(wait)
        done += source.stat().st_size


def _copy(source: Path, target: Path, done: int, total: int, report: Callable[[str, str], None]) -> None:
    part = target.with_name(target.name + ".part")
    copied, last = done, 0.0
    try:
        with open(source, "rb") as reader, open(part, "wb") as writer:
            while block := reader.read(COPY_BLOCK):
                writer.write(block)
                copied += len(block)
                if time.monotonic() - last >= 1:
                    last = time.monotonic()
                    report("copy", f"Wird ins Zielverzeichnis kopiert … {size_text(copied)} von {size_text(total)}")
        os.replace(part, target)
    except OSError:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _rescue(files: list[tuple[Path, Path]], output_path: Path, error: OSError) -> Exception:
    """Move the staged output to rescue_dir(); returns the error to raise, saying where it went."""
    from ifc_converter.app import rescue_dir

    folder = rescue_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        kept = []
        for source, target in files:
            destination = _free_name(folder / target.name)
            shutil.move(source, destination)
            kept.append(destination)
    except OSError:
        return OSError(f"Die fertige Datei konnte nicht nach {output_path.parent} kopiert werden ({error}).")
    return OSError(
        f"Die fertige Datei konnte nicht nach {output_path.parent} kopiert werden ({error.strerror or error}). "
        f"Sie liegt hier: {kept[0]} – bitte von Hand kopieren."
    )


def _free_name(path: Path) -> Path:
    """``path``, or "name (2).ext" etc. if it exists."""
    number = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate


def default_threads() -> int:
    """All logical CPUs this process may use but SPARE_CORES, at least one, at most MAX_DEFAULT_THREADS."""
    count = os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()
    return max(1, min((count or 1) - SPARE_CORES, MAX_DEFAULT_THREADS))


def chunk_size(threads: int) -> int:
    """The number of elements per geometry iterator for ``threads`` threads."""
    return min(max(CHUNK_SIZE, CHUNK_PER_THREAD * threads), MAX_CHUNK_SIZE)


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


@dataclass
class ChunkEnd:
    """Yielded by ``iter_shapes(..., chunk_ends=True)`` after the last shape of a chunk."""

    # The ids of the chunk's products, in model order. The kernel's threads deliver shapes in
    # whatever order they finish, which differs from run to run.
    ids: list[int]


def shape_products(model: ifcopenshell.file, exclude: list[str]) -> list[ifcopenshell.entity_instance]:
    """The products ``iter_shapes`` computes shapes for."""
    return [
        product for product in model.by_type("IfcProduct")
        if _has_3d_shape(product) and not any(product.is_a(name) for name in exclude)
    ]


def iter_shapes(
    model: ifcopenshell.file,
    settings: geom.settings,
    threads: int,
    exclude: list[str],
    progress: ProgressCallback | None = None,
    progress_share: int = 100,
    products: list[ifcopenshell.entity_instance] | None = None,
    chunk_ends: bool = False,
    status: StatusCallback | None = None,
) -> Iterator:
    """Yield the triangulated shape of every product, computed chunk by chunk to cap memory use.

    Progress is reported from 0 up to ``progress_share`` percent. ``products`` may pass in
    ``shape_products(model, exclude)`` if already known. With ``chunk_ends`` a ChunkEnd follows
    the shapes of each chunk. Deeply nested products come first, one by one (see DEEP_NESTING);
    ``status`` hears about each of them.
    """
    if products is None:
        products = shape_products(model, exclude)
    position, isolate, skip = _recovery.get() or (None, set(), set())
    if skip:  # products that crashed or hung the kernel before: left out, reported by the caller
        products = [product for product in products if product.id() not in skip]
    counter = _candidates.get()
    if counter is not None:
        counter[0] += len(products)
    total = len(products)
    candidates = products
    produced: set[int] = set()
    deep = deep_products(products)
    deep_ids = {product.id() for product, _ in deep}
    deep += [(product, 0) for product in products if product.id() in isolate and product.id() not in deep_ids]
    if deep:
        deep_ids = {product.id() for product, _ in deep}
        products = [product for product in products if product.id() not in deep_ids]
    strategy = kernel_strategy()
    library = geometry_library()
    local = not settings.get("use-world-coords")
    size = chunk_size(threads)
    # Computed first: if one of them crashes or hangs the kernel again, the next attempt starts
    # after minutes instead of after all the other products.
    for number, (product, depth) in enumerate(deep, 1):
        label = product_label(product)
        if depth >= CYCLIC:
            if status:
                status("note", f"Geometrie enthält sich selbst (fehlerhafte Datei), nicht umgewandelt: {label}")
            continue
        if position:
            position("element", [product.id()], label)
        if status:
            kind = f"Tief verschachteltes Bauteil ({depth} Ebenen)" if depth else "Bauteil"
            # One phase for all of them: the log gets the first line, the window each one.
            status("deep", f"{kind} {number} von {len(deep)} wird einzeln berechnet: {label} …")
        shape = _deep_shape(settings, product, strategy)
        if shape is not None:
            yield _produced(shape, produced)
        if progress:
            progress(number * progress_share // total)
    if deep:
        if chunk_ends:
            yield ChunkEnd([product.id() for product, _ in deep])
        if status:
            status("geometry", f"Geometrie wird berechnet ({threads} Threads) …")

    def delivered(shape):
        # Products whose shape is done are no suspects if the kernel crashes or hangs in this chunk.
        if position:
            position("delivered", [shape.id], "")
        return _produced(shape, produced)

    for start in range(0, len(products), size):
        chunk = products[start:start + size]
        if position:
            position("chunk", [product.id() for product in chunk], "")
        if strategy == "accurate":
            hybrid = [product for product in chunk if _triangle_mesh_only(product)]
            fast = {product.id() for product in hybrid}
            rest = [product for product in chunk if product.id() not in fast]
            parts = [(hybrid, LIBRARIES["hybrid"]), (rest, LIBRARIES["opencascade"])]
        else:
            hybrid = chunk if strategy == "hybrid" else []
            parts = [(chunk, library)]
        done = set()
        # In local coordinates the kernel returns empty geometry for type geometry (mapped items)
        # with openings cut into it, e.g. Revit cabinets with a sink cut-out: those are redone in
        # world coordinates, which the serializers and the Rhino export accept as well.
        empty = []
        for part, part_library in parts:
            if not part:
                continue
            for shape in _iterate(model, settings, threads, part, part_library):
                done.add(shape.id)
                if local and not shape.geometry.verts:
                    empty.append(model.by_id(shape.id))
                else:
                    yield delivered(shape)
        if hybrid:
            # The hybrid kernel gives up on some shapes that OpenCASCADE can still build, and leaves
            # type geometry with openings empty in local coordinates, where OpenCASCADE builds it:
            # in world coordinates GLB would store it in single precision (0.2 m off 5,000 km out).
            hybrid_ids = {product.id() for product in hybrid}
            missing = [product for product in hybrid if product.id() not in done]
            missing += [product for product in empty if product.id() in hybrid_ids]
            empty = [product for product in empty if product.id() not in hybrid_ids]
            if missing:
                for shape in _iterate(model, settings, threads, missing, LIBRARIES["opencascade"]):
                    if local and not shape.geometry.verts:
                        empty.append(model.by_id(shape.id))
                    else:
                        yield delivered(shape)
        if empty:
            settings.set("use-world-coords", True)  # iterators copy their settings
            try:
                world = list(_iterate(model, settings, threads, empty, library))
            finally:
                settings.set("use-world-coords", False)
            for shape in world:
                yield delivered(shape)
        if chunk_ends:
            yield ChunkEnd([product.id() for product in chunk])
        _release_memory()
        if progress:
            progress((len(deep) + start + len(chunk)) * progress_share // total)

    missing = _missing.get()
    if missing is not None:
        missing.extend(product_label(product) for product in candidates if product.id() not in produced)
    if position:  # a crash or hang from here on is not in the kernel
        position("done", [], "")


def _produced(shape, produced: set[int]):
    """``shape``, noted in ``produced`` if it has geometry."""
    if shape.geometry.verts:
        produced.add(shape.id)
    return shape


def product_label(product: ifcopenshell.entity_instance) -> str:
    """How a product is named in messages: class, GlobalId (to search for it) and its name."""
    name = f" „{product.Name}“" if getattr(product, "Name", None) else ""
    return f"{product.is_a()} {product.GlobalId}{name}"


def deep_products(products: list) -> list[tuple[ifcopenshell.entity_instance, int]]:
    """The products whose geometry (or that of their openings) is nested deeper than DEEP_NESTING."""
    depths: dict[int, int] = {}
    deep = []
    for product in products:
        depth = _product_depth(product, depths)
        for relation in getattr(product, "HasOpenings", None) or ():
            depth = max(depth, _product_depth(relation.RelatedOpeningElement, depths))
        if depth > DEEP_NESTING:
            deep.append((product, depth))
    return deep


def _product_depth(product: ifcopenshell.entity_instance, depths: dict[int, int]) -> int:
    if not product.Representation:
        return 0
    return max(
        (_nesting_depth(item, depths) for representation in product.Representation.Representations
         for item in representation.Items or ()),
        default=0,
    )


def _nesting_depth(item: ifcopenshell.entity_instance, depths: dict[int, int]) -> int:
    """Levels of IfcMappedItem / IfcBooleanResult / IfcCsgSolid nesting below ``item`` (itself: 1).

    Iterative, as the nesting can be far deeper than Python's recursion limit; ``depths`` caches the
    result per entity, since type geometry and operands are shared. Geometry that contains itself
    (a broken file) is CYCLIC deep: the kernel would recurse into it forever.
    """
    stack = [(item, False)]
    on_path: set[int] = set()
    while stack:
        entity, expanded = stack.pop()
        key = entity.id()
        if key in depths:
            continue
        children = _nested_children(entity)
        if expanded:
            on_path.discard(key)
            depths[key] = min(CYCLIC, 1 + max((depths.get(child.id(), 0) for child in children), default=0))
        elif not children:
            depths[key] = 1
        elif any(child.id() in on_path or child.id() == key for child in children):
            depths[key] = CYCLIC
        else:
            on_path.add(key)
            stack.append((entity, True))
            stack.extend((child, False) for child in children if child.id() not in depths)
    return depths[item.id()]


def _nested_children(entity: ifcopenshell.entity_instance) -> list:
    if entity.is_a("IfcMappedItem"):
        return list(entity.MappingSource.MappedRepresentation.Items)
    if entity.is_a("IfcBooleanResult"):
        return [operand for operand in (entity.FirstOperand, entity.SecondOperand) if operand is not None]
    if entity.is_a("IfcCsgSolid"):
        return [entity.TreeRootExpression]
    return []


def _deep_shape(settings: geom.settings, product: ifcopenshell.entity_instance, strategy: str):
    """The shape of a deeply nested product, computed in a thread with DEEP_STACK of stack, or None.

    geom.create_shape() computes in the calling thread, unlike the iterator's worker threads.
    """
    representation = _body_representation(product)
    if representation is None:
        return None
    # The same kernel as in a chunk: under "accurate" the hybrid one only for big triangle meshes
    # (OpenCASCADE takes over 20 minutes for some terrain), with OpenCASCADE where it gives up.
    if strategy == "hybrid" or (strategy == "accurate" and _triangle_mesh_only(product)):
        libraries = ["hybrid", "opencascade"]
    else:
        libraries = ["opencascade"]
    for library in libraries:

        def compute():
            return geom.create_shape(settings, product, representation, geometry_library=LIBRARIES[library])

        try:
            shape = _with_large_stack(compute)
        except RuntimeError:  # the kernel could not build it
            continue
        if shape.geometry.verts or settings.get("use-world-coords"):
            return shape
        # Local coordinates gave nothing (type geometry with openings): world coordinates do.
        settings.set("use-world-coords", True)
        try:
            return _with_large_stack(compute)
        except RuntimeError:
            continue
        finally:
            settings.set("use-world-coords", False)
    return None


def _body_representation(product: ifcopenshell.entity_instance):
    """The representation the iterator would compute for ``product``: "Body", else the first 3D one."""
    representations = [r for r in product.Representation.Representations if r.is_a("IfcShapeModel") and r.Items]
    for identifier in ("Body", "Facetation"):
        for representation in representations:
            if representation.RepresentationIdentifier == identifier:
                return representation
    return next((r for r in representations if r.RepresentationType not in NON_BODY_TYPES), None)


def _with_large_stack(function: Callable):
    """``function()`` run in a thread with DEEP_STACK of stack (the calling thread waits)."""
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["value"] = function()
        except BaseException as exc:  # handed to the calling thread
            outcome["error"] = exc

    previous = threading.stack_size(DEEP_STACK)
    try:
        thread = threading.Thread(target=run, name="deep-geometry")
        thread.start()
    finally:
        threading.stack_size(previous)
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def _triangle_mesh_only(product: ifcopenshell.entity_instance) -> bool:
    """Whether the product's 3D body is only triangle meshes (IfcTriangulatedFaceSet, also terrain as
    IfcTriangulatedIrregularNetwork, directly or as type geometry) with at least MIN_HYBRID_TRIANGLES
    triangles and without openings: what "accurate" leaves to the hybrid kernel."""
    if getattr(product, "HasOpenings", None):
        return False
    triangles = 0
    for representation in product.Representation.Representations:
        if not representation.is_a("IfcShapeModel") or representation.RepresentationType in NON_BODY_TYPES:
            continue
        items = list(representation.Items)
        visited = 0
        while items:
            item = items.pop()
            visited += 1
            if visited > MAX_VISITED_ITEMS:  # type geometry that contains itself (a broken file)
                return False
            if item.is_a("IfcMappedItem"):
                items.extend(item.MappingSource.MappedRepresentation.Items)
            elif item.is_a("IfcTriangulatedFaceSet"):
                triangles += len(item.CoordIndex)
            else:
                return False
    return triangles >= MIN_HYBRID_TRIANGLES


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
        settings, model, _kernel_threads(threads), include=products, geometry_library=library,
    )
    initialized = iterator.initialize()  # False when nothing among the products has geometry...
    if not initialized:
        # ...but also when a single product's representation has no items (invalid, written by
        # OpenRoads for the site), which would drop all of them: retry without those.
        valid = [product for product in products if all(r.Items for r in product.Representation.Representations)]
        if valid and len(valid) < len(products):
            iterator = geom.iterator(
                settings, model, _kernel_threads(threads), include=valid, geometry_library=library,
            )
            initialized = iterator.initialize()
    if initialized:
        while True:
            yield iterator.get()
            if not iterator.next():
                break
    del iterator


def kernel_strategy() -> str:
    """The kernel strategy of the running conversion (one of KERNELS)."""
    return _kernel.get() or os.environ.get("IFC_CONVERTER_KERNEL", DEFAULT_KERNEL).lower()


def geometry_library() -> str:
    """The IfcOpenShell geometry library for whole groups of elements in the running conversion, for
    geom.iterator: OpenCASCADE unless the strategy is "hybrid"."""
    return LIBRARIES["hybrid" if kernel_strategy() == "hybrid" else "opencascade"]


def _kernel_threads(threads: int) -> int:
    """The threads to run a geometry iterator on: what memory allows, but at least MIN_THREADS."""
    return max(MIN_THREADS, _affordable_threads(threads))


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


def _serialize(
    model, output_path: Path, fmt: str, threads: int, progress: ProgressCallback | None,
    report: Callable[[str, str], None] = lambda phase, text: None,
) -> int:
    """Write GLB/OBJ with IfcOpenShell's built-in serializers."""
    settings = geom.settings()
    settings.set("mesher-linear-deflection", LINEAR_DEFLECTION)

    # Geometry from the iterator is already in metres, so the scale is fixed at 1.
    serializer = getattr(geom.serializers, fmt)(str(output_path), settings)
    serializer.setFile(model)
    serializer.setUnitNameAndMagnitude("METER", 1.0)
    serializer.writeHeader()

    elements = 0
    for shape in iter_shapes(model, settings, threads, EXCLUDED_CLASSES, progress, 95, status=report):
        if not shape.geometry.verts:  # nothing to write, so it counts as skipped
            continue
        serializer.write(shape)
        elements += 1
    report("write", f"{fmt.upper()}-Datei wird geschrieben …")
    serializer.finalize()
    return elements


def memory_warning(input_path: str | Path) -> str | None:
    """A warning if the file probably needs more RAM than the machine has free, else None."""
    size = Path(input_path).stat().st_size
    # The working memory on top of the model only matters for real models, not for tiny test files.
    needed = size * MEMORY_PER_IFC_BYTE + min(MEMORY_BASE, size * 20)
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
