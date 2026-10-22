from __future__ import annotations

import logging
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.util.element
import ifcopenshell.util.unit

from ifc_converter import schema_bridge
from ifc_converter.i18n import tr

# Output formats: "3dm" has its own writer (rhino.py), the others are IfcOpenShell's serializers
# (serializers.py, which says why e.g. glTF, USD and IGES are not among them).
FORMATS = ("glb", "obj", "3dm", "dae")
# Input files: .ifc, or a .ifczip holding one (unpacked to the temp folder while reading). ifcXML
# cannot be read by IfcOpenShell 0.9 (see convert).
INPUT_SUFFIXES = (".ifc", ".ifczip")
# Targets of convert() that are not offered as output formats: "preview" is the light mesh of the
# model shown in the window (.npz, see preview.py), computed like a conversion in the child process.
INTERNAL_FORMATS = ("preview",)
# How the Rhino export represents elements: joined planar polysurfaces (with meshes for elements
# too detailed for that), or meshes only. GLB and OBJ are always meshes.
GEOMETRIES = ("brep", "mesh")

# Opening volumes would cover every window and door; space volumes would hide the building inside.
# The Rhino export keeps spaces on their own layer instead, where they are easy to switch off.
# Grids are only lines, which GLB/OBJ meshes cannot show (the Rhino export writes them as curves).
# The layout parts of an alignment (IFC4X3) repeat its 3D axis: horizontal ones as a plan at height
# 0, vertical ones as a profile in distance/height coordinates, drawn in the XY plane somewhere off
# the model (a bSI test road: 950 m instead of 882 m wide, 150 m instead of 1.5 m high).
ALIGNMENT_LAYOUT_CLASSES = ["IfcAlignmentHorizontal", "IfcAlignmentVertical", "IfcAlignmentCant", "IfcAlignmentSegment"]
EXCLUDED_CLASSES = ["IfcOpeningElement", "IfcSpace", "IfcGrid", *ALIGNMENT_LAYOUT_CLASSES]

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
log = logging.getLogger(__name__)
_kernel: ContextVar[str | None] = ContextVar("kernel", default=None)
# Products the iterator gives no geometry get a second attempt each (see _second_attempts), with this
# tolerance, for at most RESCUE_SECONDS per conversion: a model whose elements are mostly empty
# (e.g. fully cut away) is not held up.
RESCUE_PRECISION = 1e-6
RESCUE_SECONDS = 120

# The checkpoint of the running conversion (3dm only), see checkpoint.py.
_checkpoint: ContextVar = ContextVar("checkpoint", default=None)
# Labels of the products of the running conversion that produced no geometry.
_missing: ContextVar[list | None] = ContextVar("missing", default=None)
# (position callback, step ids to compute one by one, step ids to skip) of the running conversion.
_recovery: ContextVar[tuple | None] = ContextVar("recovery", default=None)
# Number of elements iter_shapes was asked to process during the current conversion.
_candidates: ContextVar[list[int] | None] = ContextVar("candidates", default=None)
# Option "Nur Gebäudehülle": the ids of the products shape_products returns (None: all of them).
_selected: ContextVar[set[int] | None] = ContextVar("selected", default=None)
# The hang limit (seconds) of the running pass, see HANG_SECONDS; None: the "fine" limit.
_hang_seconds: ContextVar[float | None] = ContextVar("hang_seconds", default=None)
# Labels of the products the kernel hung on during the running conversion (reported like crashed
# ones); None in the hull's coarse pass, where a hung product is kept instead.
_hung: ContextVar[list | None] = ContextVar("hung", default=None)
# Share of the progress the hull's coarse geometry pass takes (the conversion gets the rest).
ENVELOPE_SHARE = 25

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
# grows with the model. Running a fresh iterator per chunk of elements keeps that bounded. Chunks
# grow with the thread count: CHUNK_PER_THREAD elements per thread (on 2 threads, 400 instead of 200
# took the kernel 11-16 s instead of 19-33 s for Clinic_Architectural), at least CHUNK_SIZE and at
# most MAX_CHUNK_SIZE elements (the shapes of 1600 elements took ~10 MB more there).
CHUNK_SIZE = 200
CHUNK_PER_THREAD = 50
MAX_CHUNK_SIZE = 2000
# Chunks overlap: once at most 1/OVERLAP_SHARE of the threads still compute (the slowest elements of
# a chunk), the next chunk's iterator starts, instead of the other threads waiting idle for them (on
# a 611 MB model one element kept 15 of 16 threads idle for 3 minutes). Its shapes wait in memory
# until the chunk before is done, as the Rhino export adds elements in model order. While an element
# keeps a chunk waiting, up to LOOKAHEAD_CHUNKS further chunks are computed, but only while
# LOOKAHEAD_MEMORY stays free.
OVERLAP_SHARE = 4
LOOKAHEAD_CHUNKS = 16
LOOKAHEAD_MEMORY = 4 * 1024 ** 3
# Seconds between checks for idle threads while waiting for a slow element.
OVERLAP_POLL = 0.5
# IfcOpenShell cannot stop an iterator: once started, its threads compute all its products and read
# the model meanwhile. When iter_shapes ends early (an error in the consumer, a closed generator),
# it waits up to CLOSE_WAIT seconds for them; slower runs keep the model alive until they are done
# (freeing it under them crashed the process).
CLOSE_WAIT = 60
# The kernel can spin on a single element for hours (a hull's coarse pass stood at 23 % for over two
# hours on a 1.5 GB model), and its threads cannot be stopped. A run (one iterator, see _Run) that
# delivers nothing for this many seconds while the kernel is still at it, or a single computation
# (_deep_shape, _second_attempts) taking this long, has hung: the run is abandoned (its iterator and
# the model are then never freed, see _keep_forever) and its undelivered products are computed one
# by one (see _after_hang); what still hangs is skipped like an element the kernel crashed on. Per
# pass: the conversion itself ("fine"), the hull's coarse pass (it only approximates: a hung product
# is kept there, see envelope.select) and the preview. IFC_CONVERTER_HANG_SECONDS overrides all three.
HANG_SECONDS = {"fine": 20 * 60, "coarse": 5 * 60, "preview": 3 * 60}
HANG_ENV = "IFC_CONVERTER_HANG_SECONDS"
# Of an abandoned run, at most this many undelivered products are computed one by one, and no more
# once this many of them hung as well (each costs the limit again): the rest are reported as not
# computed. Usually the kernel's other threads have finished every other product of the run, so
# only the hung one is undelivered.
HANG_RETRY_LIMIT = 100
HANG_RETRY_HANGS = 2
# What is left of an abandoned run after that (not computed one by one) goes to a fresh run in one
# go, at most this many times per chunk (the first run counts); only then is the rest given up.
HANG_ROUNDS = 2

# Share of the logical CPUs a conversion keeps busy by default, kernel threads and the Rhino export's
# worker processes together: it is a work PC, where other demanding programs run at the same time.
CPU_SHARE = 0.5
# Of that budget, the kernel gets this share; the Rhino export starts one worker per two threads
# (rhino.THREADS_PER_WORKER), which then use the rest. 32 logical CPUs: 11 threads and 5 workers.
KERNEL_SHARE = 2 / 3
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
    # Elements left out because the geometry kernel crashed or hung on them: those it hung on (given
    # up by the conversion itself, see HANG_SECONDS) from convert, those it crashed on from process.
    crashed: list[str] = field(default_factory=list)
    # Elements left out as interior (option "Nur Gebäudehülle", see envelope).
    inside: int = 0


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
    blocks: bool = False,
    checkpoint_dir: str | Path | None = None,
    envelope: bool = False,
    hull_kernel: str | None = None,
) -> ConversionResult:
    """Convert an IFC file to GLB, OBJ (plus .mtl), Rhino 3DM or DAE and return what was written.

    ``fmt="preview"`` (not offered to users, see INTERNAL_FORMATS) writes the preview (.npz) of
    preview.write_preview instead; the app calls it through preview.compute_preview.

    ``geometry`` ("brep" or "mesh") and ``blocks`` (type geometry placed several times as Rhino
    blocks) only affect the Rhino export. With ``envelope`` only the building hull is converted:
    products inside the building are left out (see envelope.select; ``hull_kernel`` "opencascade" does
    its rough pre-computation with OpenCASCADE instead of the hybrid kernel). ``kernel`` picks the geometry
    kernel (see KERNELS); by default IFC_CONVERTER_KERNEL or DEFAULT_KERNEL. ``status`` gets the
    phases (see StatusCallback). Output for a network folder is written in ``staging_dir`` (or a
    temp folder) first and then copied. ``position``, ``isolate_ids`` and ``skip_ids`` let a caller
    recover from a crash or hang in the kernel: products are computed one by one or left out.
    """
    fmt = fmt.lower()
    if fmt not in FORMATS + INTERNAL_FORMATS:
        raise ValueError(tr('Unsupported format "{fmt}"; possible formats: {formats}', fmt=fmt,
                            formats=", ".join(FORMATS)))
    geometry = geometry.lower()
    if geometry not in GEOMETRIES:
        raise ValueError(tr('Unsupported geometry kind "{geometry}"; possible kinds: {kinds}', geometry=geometry,
                            kinds=", ".join(GEOMETRIES)))

    kernel = (kernel or os.environ.get("IFC_CONVERTER_KERNEL") or DEFAULT_KERNEL).lower()
    if kernel not in KERNELS:
        raise ValueError(tr('Unknown geometry kernel "{kernel}"; possible kernels: {kernels}', kernel=kernel,
                            kernels=", ".join(KERNELS)))

    input_path = Path(input_path)
    if not input_path.is_file():
        raise FileNotFoundError(tr("IFC file not found: {path}", path=input_path))
    if input_path.suffix.lower() in (".ifcxml", ".xml"):
        raise ValueError(tr(
            "IfcOpenShell cannot read ifcXML files ({name}). Please export the model from the authoring program "
            "as .ifc (STEP text format) or .ifczip.", name=input_path.name,
        ))
    suffix = ".npz" if fmt == "preview" else f".{fmt}"
    output_path = Path(output_path) if output_path else input_path.with_suffix(suffix)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def report(phase: str, text: str) -> None:
        if status:
            status(phase, text)

    report("read", tr("Reading IFC file ({size}) …", size=size_text(input_path.stat().st_size)))
    read_started = time.monotonic()
    # Schemas IfcOpenShell does not know (IFC2x2, the IFC4x4 draft) are read as the closest it knows,
    # from a rewritten copy (see schema_bridge); a .ifczip is read as it is.
    bridge = schema_bridge.bridge_for(input_path) if input_path.suffix.lower() == ".ifc" else None
    bridged = schema_bridge.bridged_copy(input_path, bridge) if bridge else None
    try:
        model = ifcopenshell.open(str(bridged.path if bridged else input_path))
    except ifcopenshell.SchemaError as exc:
        supported = ", ".join(s for s in ifcopenshell.ifcopenshell_wrapper.schema_names() if s.startswith("IFC"))
        bridges = ", ".join(sorted({b.label() for b in schema_bridge.BRIDGES.values() if not b.alias}))
        raise ValueError(tr(
            "IFC version is not supported ({error}). Supported: {supported}; {bridges} are also read as the "
            "closest related schema.", error=exc, supported=supported, bridges=bridges,
        )) from exc
    finally:
        if bridged:
            bridged.remove()  # the model is in memory now
    if bridged:
        report("note", tr("{note} Dimensions and positions stay unchanged.", note=bridged.note))
    if not _ends_properly(input_path):
        report("note", tr("The IFC file seems to be cut off (no END-ISO-10303-21 at its end): the output may be "
                          "incomplete."))
    repair_units(model)
    repair_extrusions(model)
    units_note = merge_projects(model)
    if units_note:
        report("note", units_note)
    read_seconds = time.monotonic() - read_started
    threads = threads or default_threads()
    token = _kernel.set(kernel)
    candidates = [0]
    candidates_token = _candidates.set(candidates)
    recovery_token = _recovery.set((position, set(isolate_ids or ()), set(skip_ids or ())))
    missing: list[str] = []
    missing_token = _missing.set(missing)
    hung: list[str] = []
    hung_token = _hung.set(hung)
    hang_token = _hang_seconds.set(hang_limit("preview" if fmt == "preview" else "fine"))
    checkpoint = None
    if checkpoint_dir and fmt == "3dm":
        from ifc_converter.checkpoint import Checkpoint

        checkpoint = Checkpoint(checkpoint_dir)
    checkpoint_token = _checkpoint.set(checkpoint)
    selection = None
    selected_token = None
    if progress:
        progress(0)
    if envelope and fmt != "preview":
        from ifc_converter import envelope as hull

        report("envelope", tr("Determining the building hull (geometry roughly precomputed) …"))
        selection = hull.select(
            model, threads, shape_products(model, EXCLUDED_CLASSES), report,
            (lambda percent: progress(percent * ENVELOPE_SHARE // 100)) if progress else None,
            **({"kernel": hull_kernel} if hull_kernel else {}),  # only when asked: stand-ins take five arguments
        )
        selected_token = _selected.set(selection.keep)
        report("note", selection.note)
        if progress:
            inner = progress
            progress = lambda percent: inner(ENVELOPE_SHARE + percent * (100 - ENVELOPE_SHARE) // 100)
    report("geometry", tr("Computing geometry ({threads} threads) …", threads=threads))

    with _staging(output_path, input_path.stat().st_size, staging_dir) as target:
        try:
            if fmt == "3dm":
                from ifc_converter.rhino import write_3dm

                elements = write_3dm(model, target, threads, progress, geometry, report, blocks, input_path)
            elif fmt == "preview":
                from ifc_converter.preview import write_preview

                elements = write_preview(model, target, threads, progress, report, input_path, read_seconds)
            else:
                from ifc_converter.serializers import write

                elements = write(model, target, fmt, threads, progress, report)
        finally:
            _kernel.reset(token)
            _candidates.reset(candidates_token)
            _recovery.reset(recovery_token)
            _missing.reset(missing_token)
            _hung.reset(hung_token)
            _hang_seconds.reset(hang_token)
            _checkpoint.reset(checkpoint_token)
            if selected_token is not None:
                _selected.reset(selected_token)

        if elements == 0:
            # An empty file reported as success would look like a finished conversion.
            for path in _output_files(target, fmt):
                path.unlink(missing_ok=True)
            if candidates[0]:
                raise ValueError(tr(
                    "No geometry produced: none of the {count} elements with geometry could be converted "
                    "(probably unsupported geometry types).", count=candidates[0],
                ))
            raise ValueError(tr("The file contains no elements with geometry."))
        if target != output_path:
            _deliver(target, output_path, fmt, report)

    if progress:
        progress(100)
    return ConversionResult(
        output=output_path, elements=elements, skipped=max(0, candidates[0] - elements), no_geometry=missing,
        crashed=hung, inside=selection.inside if selection else 0,
    )


def _ends_properly(path: Path) -> bool:
    """Whether a STEP file (.ifc) ends with END-ISO-10303-21; a cut-off download or copy does not.
    Other inputs (.ifczip) are not checked."""
    if path.suffix.lower() != ".ifc":
        return True
    try:
        with open(path, "rb") as file:
            file.seek(max(0, path.stat().st_size - 256))
            return b"END-ISO-10303-21" in file.read()
    except OSError:
        return True


def size_text(size: int) -> str:
    """A file size with the language's decimal mark, e.g. "1.2 GB" / "1,2 GB" or "345 MB"."""
    if size >= 1024 ** 3:
        integer, _, fraction = f"{size / 1024 ** 3:.1f}".partition(".")
        return tr("{integer}.{fraction}", integer=integer, fraction=fraction) + " GB"
    return f"{size / 1024 ** 2:.0f} MB"


def _output_files(path: Path, fmt: str) -> list[Path]:
    """The files a conversion to ``path`` writes (OBJ: the .mtl next to it)."""
    from ifc_converter.serializers import output_files

    return output_files(path, fmt)


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
    report("copy", tr("Copying to the target folder ({size}) …", size=size_text(total)))
    done = 0
    for source, target in files:
        for attempt, wait in enumerate((*COPY_RETRY_WAITS, None), 1):
            try:
                _copy(source, target, done, total, report)
                break
            except OSError as exc:
                if wait is None:
                    raise _rescue(files, output_path, exc) from exc
                report("copy", tr("Copying failed ({error}) – attempt {attempt} in {seconds} s …",
                                  error=exc.strerror or exc, attempt=attempt + 1, seconds=wait))
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
                    report("copy", tr("Copying to the target folder … {copied} of {total}",
                                      copied=size_text(copied), total=size_text(total)))
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
        return OSError(tr("The finished file could not be copied to {folder} ({error}).",
                          folder=output_path.parent, error=error))
    return OSError(tr(
        "The finished file could not be copied to {folder} ({error}). It is here: {path} – please copy it by hand.",
        folder=output_path.parent, error=error.strerror or error, path=kept[0],
    ))


def _free_name(path: Path) -> Path:
    """``path``, or "name (2).ext" etc. if it exists."""
    number = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate


def cpu_budget() -> int:
    """The logical CPUs a conversion keeps busy by default: CPU_SHARE of those this process may use."""
    count = os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()
    return max(1, round((count or 1) * CPU_SHARE))


def default_threads() -> int:
    """The kernel's share of cpu_budget() (KERNEL_SHARE), at least one, at most MAX_DEFAULT_THREADS."""
    return max(1, min(round(cpu_budget() * KERNEL_SHARE), MAX_DEFAULT_THREADS))


def worker_budget(threads: int) -> int:
    """How many worker processes may run beside ``threads`` kernel threads within cpu_budget()."""
    return max(0, cpu_budget() - threads)


def chunk_size(threads: int) -> int:
    """The number of elements per geometry iterator for ``threads`` threads."""
    return min(max(CHUNK_SIZE, CHUNK_PER_THREAD * threads), MAX_CHUNK_SIZE)


# The SI unit of each unit type (IfcSIUnitName), for SI units written without a name.
SI_UNIT_NAMES = {
    "LENGTHUNIT": "METRE", "AREAUNIT": "SQUARE_METRE", "VOLUMEUNIT": "CUBIC_METRE",
    "PLANEANGLEUNIT": "RADIAN", "SOLIDANGLEUNIT": "STERADIAN", "MASSUNIT": "GRAM", "TIMEUNIT": "SECOND",
    "THERMODYNAMICTEMPERATUREUNIT": "DEGREE_CELSIUS", "FORCEUNIT": "NEWTON", "PRESSUREUNIT": "PASCAL",
    "ENERGYUNIT": "JOULE", "POWERUNIT": "WATT", "FREQUENCYUNIT": "HERTZ", "ELECTRICCURRENTUNIT": "AMPERE",
    "ELECTRICVOLTAGEUNIT": "VOLT", "LUMINOUSINTENSITYUNIT": "CANDELA", "AMOUNTOFSUBSTANCEUNIT": "MOLE",
}


def repair_units(model: ifcopenshell.file) -> None:
    """Repair conversion-based units that IfcOpenShell cannot read, in memory.

    OpenRoads Designer writes the conversion factor as a bare number instead of a typed measure,
    and declares its square and cubic feet as length units. IfcOpenShell then ignores all units and
    reads the model as metres: a model in US survey feet came out 3.28x too large.
    """
    # Some exporters write the SI unit without its name, e.g. IfcSIUnit(*,.LENGTHUNIT.,.MILLI.,$) for
    # millimetres (bridges of the Zenodo "AutoGen" set): IfcOpenShell then reads the model as metres,
    # 1000x too large. The unit type tells the name.
    for unit in model.by_type("IfcSIUnit"):
        if unit.Name is None and unit.UnitType in SI_UNIT_NAMES:
            unit.Name = SI_UNIT_NAMES[unit.UnitType]
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


def repair_extrusions(model: ifcopenshell.file) -> int:
    """Turn extrusions with a negative depth the right way round, in memory; returns how many.

    IFC only allows positive depths, and the geometry kernel rejects an IfcExtrudedAreaSolid with
    a negative one ("Non-positive extrusion height"): the element loses that part silently, or all
    of its geometry (bridge girders of the Zenodo "AutoGen" set: 304 extrusions, 28 beams without
    geometry). A depth of -6 along a direction is the same solid as 6 along the opposite direction,
    so the solid keeps its place and size.
    """
    repaired = 0
    for solid in model.by_type("IfcExtrudedAreaSolid"):
        depth = solid.Depth
        if depth is None or depth >= 0:
            continue
        direction = solid.ExtrudedDirection
        # A new direction entity: the old one may be shared with extrusions of a positive depth.
        solid.ExtrudedDirection = model.create_entity(
            "IfcDirection", [-float(ratio) for ratio in direction.DirectionRatios]
        )
        solid.Depth = -depth
        repaired += 1
    if repaired:
        log.info(tr("{count} extrusions with negative depth turned around", count=repaired))
    return repaired


def merge_projects(model: ifcopenshell.file) -> str | None:
    """Merge the projects of a federated model into the first one that has units, in memory, and
    return a note for the user if their units disagreed.

    Some exports combine several models in one file, each with its own IfcProject (210 King: the
    architecture, electrical and MEP models). IfcOpenShell only reads the units of a file with
    exactly one project, otherwise it takes lengths as metres and angles as radians: that model in
    feet came out 3.28x too large, and the arcs of arched openings, trimmed in degrees, made broken
    opening solids. Each facade wall then lost all of its openings after ~25 s of failing booleans.
    A project without units of its own (a linked model's empty project) has no say. Projects with
    different units are merged all the same, with a note: read with the first project's units most
    of the model is right, read as metres none of it would be.
    """
    projects = model.by_type("IfcProject")
    if len(projects) < 2:
        return None
    scales = {_unit_scales(project) for project in projects} - {(None, None)}
    survivor = next((project for project in projects if _unit_scales(project) != (None, None)), projects[0])
    note = None
    if len(scales) > 1:
        note = tr("The file holds {count} projects with different units; all of them are read with the units of "
                  "the first one ({name}). Please check the dimensions.", count=len(projects),
                  name=survivor.Name or survivor.GlobalId)
    for project in projects:
        if project is survivor:
            continue
        # Re-link what belongs to the project (its sites, properties) before removing it.
        for inverse in model.get_inverse(project):
            ifcopenshell.util.element.replace_attribute(inverse, project, survivor)
        model.remove(project)
    return note


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
    """The products ``iter_shapes`` computes shapes for (only the hull's with option "Nur Gebäudehülle")."""
    selected = _selected.get()
    return [
        product for product in model.by_type("IfcProduct")
        if _has_3d_shape(product) and not any(product.is_a(name) for name in exclude)
        and (selected is None or product.id() in selected)
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
    second_attempts: bool = True,
    hang_seconds: float | None = None,
) -> Iterator:
    """Yield the triangulated shape of every product, computed chunk by chunk to cap memory use.

    Progress is reported from 0 up to ``progress_share`` percent. ``products`` may pass in
    ``shape_products(model, exclude)`` if already known. With ``chunk_ends`` a ChunkEnd follows
    the shapes of each chunk. Deeply nested products come first, one by one (see DEEP_NESTING);
    ``status`` hears about each of them. Products without geometry get a second attempt with a
    finer tolerance (see RESCUE_SECONDS) unless ``second_attempts`` is off (the hull's coarse pass).
    A run or a single computation that delivers nothing for ``hang_seconds`` (by default the running
    pass's limit, see HANG_SECONDS) is abandoned, see _after_hang.
    """
    if products is None:
        products = shape_products(model, exclude)
    limit = hang_seconds if hang_seconds is not None else _hang_seconds.get()
    if limit is None:
        limit = hang_limit("fine")
    hung_ids: set[int] = set()  # products the kernel hung on: neither computed again nor "without geometry"
    position, isolate, skip = _recovery.get() or (None, set(), set())
    if skip:  # products that crashed or hung the kernel before: left out, reported by the caller
        products = [product for product in products if product.id() not in skip]
    counter = _candidates.get()
    if counter is not None:
        counter[0] += len(products)
    total = len(products)
    candidates = products
    produced: set[int] = set()
    checkpoint = _checkpoint.get()
    finished = 0
    if checkpoint is not None:
        # Chunks finished by an attempt that crashed or hung: read back instead of computed again.
        wanted = {product.id() for product in products}
        replayed: set[int] = set()
        for ids, shapes in checkpoint.replay():
            for shape in shapes:
                if shape.id in wanted:
                    yield _produced(shape, produced)
            if chunk_ends:
                yield ChunkEnd([id_ for id_ in ids if id_ in wanted])
            replayed.update(ids)
            finished = len(replayed & wanted)
            if progress:
                progress(finished * progress_share // total)
        if replayed:
            products = [product for product in products if product.id() not in replayed]
            if status:
                status("note", tr("{finished} elements taken over from the previous attempt, {count} are computed",
                                  finished=finished, count=len(products)))

    def keep(shape):
        if checkpoint is not None:
            checkpoint.record(shape)
        return _produced(shape, produced)

    def chunk_end(ids: list[int]) -> Iterator:
        if checkpoint is not None:
            checkpoint.chunk_done(ids)
        if chunk_ends:
            yield ChunkEnd(ids)

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
                status("note", tr("Geometry contains itself (faulty file), not converted: {label}", label=label))
            continue
        if position:
            position("element", [product.id()], label)
        if status:
            # One phase for all of them: the log gets the first line, the window each one.
            if depth:
                status("deep", tr("Deeply nested element ({depth} levels) {number} of {total} is computed on its own: "
                                  "{label} …", depth=depth, number=number, total=len(deep), label=label))
            else:
                status("deep", tr("Element {number} of {total} is computed on its own: {label} …",
                                  number=number, total=len(deep), label=label))
        try:
            shape = _deep_shape(settings, product, strategy, limit, model)
        except KernelHung:
            _report_hung(product, hung_ids, status, position, limit)
            shape = None
        if shape is not None:
            yield keep(shape)
        if progress:
            progress((finished + number) * progress_share // total)
    if deep:
        yield from chunk_end([product.id() for product, _ in deep])
        if status:
            status("geometry", tr("Computing geometry ({threads} threads) …", threads=threads))

    rescue, rescued = [RESCUE_SECONDS if second_attempts else 0], 0  # time left for second attempts, products saved
    chunks = [products[start:start + size] for start in range(0, len(products), size)]
    pipeline = _Pipeline(model, settings, threads, position, chunks, strategy, library, limit)
    finished += len(deep)
    try:
        for index, chunk in enumerate(chunks):
            hybrid: list = []
            done = set()
            # In local coordinates the kernel returns empty geometry for type geometry (mapped items)
            # with openings cut into it, e.g. Revit cabinets with a sink cut-out: those are redone in
            # world coordinates, which the serializers and the Rhino export accept as well.
            empty = []

            def take(run: _Run, check_empty: bool = True, rounds: int = 1) -> Iterator:
                for shape in pipeline.shapes(run, index):
                    done.add(shape.id)
                    if check_empty and local and not has_geometry(shape):
                        empty.append(model.by_id(shape.id))
                    else:
                        yield keep(shape)
                if run.abandoned:
                    # Its undelivered products are computed one by one (world coordinates where local
                    # ones give nothing, see _deep_shape) or reported hung; what that leaves (after
                    # HANG_RETRY_HANGS) gets a fresh run, without the hung ones, up to HANG_ROUNDS times.
                    done.update(run.ids)
                    leftover: list = []
                    for shape in _after_hang(run, settings, strategy, position, status, limit, hung_ids, leftover):
                        yield keep(shape)
                    pipeline.report_position()
                    if leftover and rounds < HANG_ROUNDS:
                        if status:
                            status("note", tr("{count} elements of the chunk are computed again together, without the "
                                              "ones the geometry kernel hung on …", count=len(leftover)))
                        done.difference_update(product.id() for product in leftover)  # the fresh run tells
                        yield from take(pipeline.start(index, leftover, run.library, world=run.world), check_empty,
                                        rounds + 1)
                    elif leftover:
                        _give_up_hung(leftover, status, position, limit, hung_ids)

            while (run := pipeline.next_run(index)) is not None:
                if run.library == LIBRARIES["hybrid"]:
                    hybrid += run.products
                yield from take(run)
            if hybrid:
                # The hybrid kernel gives up on some shapes that OpenCASCADE can still build, and leaves
                # type geometry with openings empty in local coordinates, where OpenCASCADE builds it:
                # in world coordinates GLB would store it in single precision (0.2 m off 5,000 km out).
                hybrid_ids = {product.id() for product in hybrid}
                missing = [product for product in hybrid if product.id() not in done]
                missing += [product for product in empty if product.id() in hybrid_ids]
                empty = [product for product in empty if product.id() not in hybrid_ids]
                if missing:
                    yield from take(pipeline.start(index, missing, LIBRARIES["opencascade"]))
            if empty:
                yield from take(pipeline.start(index, empty, library, world=True), check_empty=False)
            failed = [product for product in chunk if product.id() not in produced and product.id() not in hung_ids]
            if failed and rescue[0] > 0:
                for shape in _second_attempts(settings, failed, position, rescue, status, limit, hung_ids, model):
                    rescued += 1
                    yield keep(shape)
                pipeline.report_position()
            yield from chunk_end([product.id() for product in chunk])
            _release_memory()
            finished += len(chunk)
            if progress:
                progress(finished * progress_share // total)
    finally:
        pipeline.close()

    if rescued and status:
        status("note", tr("{count} elements only computed in the second attempt (finer tolerance or other kernel)",
                          count=rescued))
    if rescue[0] <= 0 and second_attempts and status:
        status("note", tr("Second attempts ended after {seconds} s; further elements without geometry were not "
                          "tried on their own any more", seconds=RESCUE_SECONDS))
    if hung_ids and counter is not None:  # like products skipped after a crash: not candidates
        counter[0] -= len(hung_ids)
    without = [product for product in candidates if product.id() not in produced and product.id() not in hung_ids]
    # An aggregate whose parts became geometry (e.g. a curtain wall of plates and members, whose own
    # body ArchiCAD leaves empty) misses nothing: it is neither reported nor counted as without.
    covered = [product for product in without if _parts_produced(product, produced)]
    if covered and counter is not None:
        counter[0] -= len(covered)
    missing = _missing.get()
    if missing is not None:
        covered_ids = {product.id() for product in covered}
        missing.extend(product_label(product) for product in without if product.id() not in covered_ids)
    if position:  # a crash or hang from here on is not in the kernel
        position("done", [], "")


def curve_phase(elements: list) -> list:
    """Of ``elements`` (alignments and grids), those the Rhino export computes as curves after
    iter_shapes, and tell the caller that it does: if the kernel crashes or hangs there, the next
    attempt leaves them out (they are then skipped)."""
    position, _, skip = _recovery.get() or (None, set(), set())
    elements = [element for element in elements if element.id() not in skip]
    if position and elements:
        position("curves", [element.id() for element in elements], "\n".join(map(product_label, elements)))
    return elements


class _Run:
    """The shapes of ``products`` from one geometry iterator.

    The iterator's threads compute from the start on, whether the shapes are taken or not; a thread
    of its own takes them from the kernel as they are done and queues them for iter_shapes.
    """

    def __init__(self, index: int, products: list, library: str, width: int, model, settings, world: bool = False):
        # The kernel's threads read the model (and the iterator its settings) until they are done.
        self.model, self.settings = model, settings
        self.index = index  # of the chunk
        self.products = products
        self.ids = [product.id() for product in products]
        self.library = library
        self.world = world  # computed in world coordinates although the settings say local
        self.width = width
        self.computed: set[int] = set()  # products whose shape the kernel has delivered
        self.finished = False
        self.stopped = False
        self.abandoned = False  # given up as hung, see _Pipeline.hung
        self.last_delivery = time.monotonic()  # when the kernel last delivered a shape (or the start)
        self.source = None  # the _Shapes of the iterator, kept for as long as the run lives
        self._queue: queue.SimpleQueue = queue.SimpleQueue()

    def busy(self) -> int:
        """The kernel threads still at work on this run (at most one per product not computed)."""
        return 0 if self.finished else max(0, min(self.width, len(self.ids) - len(self.computed)))

    def drain(self, shapes, computed: Callable[[_Run, object], None]) -> None:
        """Runs in the run's thread: hand each shape to ``computed`` (which queues it, see
        _Pipeline._computed) once the kernel has computed it.

        Once the run is stopped, the remaining shapes are taken and dropped: only an iterator that
        has delivered everything has no threads left that read the model. (An abandoned run never
        gets there: its thread stays in the kernel for good.)
        """
        failed = None
        try:
            for shape in shapes:
                if self.stopped or failed:
                    continue
                try:
                    computed(self, shape)
                except BaseException as exc:  # e.g. the pipe to the parent is gone
                    failed = exc
                    continue
        except BaseException as exc:
            failed = failed or exc
        finally:
            self.finished = True
            if failed and not self.stopped:  # handed to iter_shapes
                self._queue.put(_Failed(failed))
            self._queue.put(_END)

    def shapes(self, waiting: Callable[[], bool]) -> Iterator:
        """The queued shapes as they come; ``waiting`` is called while there are none, and ends
        the run once it returns True (the run was abandoned: what is queued is still taken)."""
        abandoned = False
        while True:
            try:
                item = self._queue.get(timeout=0 if abandoned else OVERLAP_POLL)
            except queue.Empty:
                if abandoned:
                    return
                abandoned = waiting()
                continue
            if item is _END:
                return
            if isinstance(item, _Failed):
                if abandoned:
                    return
                raise item.error
            yield item

    def queue_shape(self, shape) -> None:
        self._queue.put(shape)


@dataclass
class _Failed:
    error: BaseException


_END = object()


class _Pipeline:
    """Runs the geometry iterators of iter_shapes for ``chunks``, overlapping them (see OVERLAP_SHARE).

    The iterators are created in the thread of iter_shapes, in the order their shapes are needed.
    ``position`` hears of every start: all products of the runs not finished with as a "chunk", then
    those of them already computed as "delivered". After a crash or a hang only the products the
    kernel was still at, or had not started, are suspects.
    """

    def __init__(
        self, model, settings, threads: int, position: PositionCallback | None, chunks: list[list],
        strategy: str, library: str, hang_seconds: float | None = None,
    ):
        self.model, self.settings, self.threads = model, settings, threads
        self.strategy, self.library = strategy, library
        self.hang_seconds = hang_seconds  # None: runs are never abandoned
        self.slack = max(1, threads // OVERLAP_SHARE)
        self._position = position
        self._lock = threading.Lock()  # orders the positions sent here and by the runs' threads
        self._chunks = iter(enumerate(chunks))
        self._planned: deque[tuple[int, list, str]] = deque()  # parts of chunks, not started yet
        self._started: deque[_Run] = deque()  # planned runs started, in the order they are needed
        self._alive: list[_Run] = []  # every run started and not finished with
        self._threads: list[tuple[_Run, threading.Thread]] = []  # of every run started

    def next_run(self, index: int) -> _Run | None:
        """The next planned run of chunk ``index``, started now if it was not yet; None after its last."""
        if not self._started:
            step = self._next_planned()
            if step is None or step[0] != index:
                return None
            self._start_planned()
        if self._started[0].index != index:
            return None
        return self._started.popleft()

    def start(self, index: int, products: list, library: str, world: bool = False) -> _Run:
        """Start a run for ``products`` of chunk ``index`` right away (in world coordinates if ``world``)."""
        run = _Run(index, products, library, _kernel_threads(self.threads), self.model, self.settings, world)
        self._alive.append(run)
        self.report_position()
        if world:
            self.settings.set("use-world-coords", True)  # iterators copy their settings
        try:
            shapes = _start_iterator(self.model, self.settings, self.threads, products, library, self.hang_seconds)
        except KernelHung:
            # The iterator's start waits for its first shape, which never came: the run is abandoned
            # before it delivered anything (its products are computed one by one, see _after_hang).
            with self._lock:
                run.stopped = run.abandoned = run.finished = True
            run.queue_shape(_END)
            self._alive.remove(run)
            self.report_position()
            return run
        except BaseException:
            self._alive.remove(run)
            raise
        finally:
            if world:
                self.settings.set("use-world-coords", False)
        run.source = shapes  # the iterator stays until the run is finished with, like its shapes
        thread = threading.Thread(target=run.drain, args=(shapes, self._computed), name="geometry-run", daemon=True)
        thread.start()
        self._threads.append((run, thread))
        return run

    def report_position(self) -> None:
        """Tell ``position`` the products of the runs alive: all as a "chunk", the computed as "delivered"."""
        if self._position:
            with self._lock:
                self._position("chunk", [id_ for alive in self._alive for id_ in alive.ids], "")
                computed = [id_ for alive in self._alive for id_ in alive.computed]
                if computed:
                    self._position("delivered", computed, "")

    def shapes(self, run: _Run, index: int) -> Iterator:
        """The shapes of ``run`` as the kernel delivers them; meanwhile idle threads get more work.
        A run that hangs (see hung) is abandoned: ``run.abandoned`` says so afterwards."""
        self.top_up(index)

        def waiting() -> bool:
            self.top_up(index)
            return self.hung(run)

        for shape in run.shapes(waiting):
            yield shape
            self.top_up(index)
        if not run.abandoned:
            self._alive.remove(run)

    def hung(self, run: _Run) -> bool:
        """Abandon ``run`` if it has delivered nothing for ``hang_seconds`` while the kernel is still
        at it; returns whether it is abandoned now. Its thread stays in the kernel, so its iterator
        and the model are never freed (see _keep_forever); the shapes it delivered are still taken."""
        if run.finished or self.hang_seconds is None or time.monotonic() - run.last_delivery < self.hang_seconds:
            return False
        with self._lock:  # from here on no shape of it is computed (queued) any more
            run.stopped = run.abandoned = True
        self._alive.remove(run)
        _keep_forever(run.source)
        _keep_forever(run.model)
        self.report_position()
        return True

    def top_up(self, current: int) -> None:
        """Start the next planned runs while at most ``slack`` threads are busy (chunk ``current`` is
        the one whose shapes are being taken)."""
        while (step := self._next_planned()) is not None:
            if sum(run.busy() for run in self._alive) > self.slack:
                return
            if step[0] > current + 1 and not self._look_ahead(current, step[0]):
                return
            self._start_planned()

    def close(self) -> None:
        """Stop the runs not finished with and wait for the threads of all runs (see CLOSE_WAIT)."""
        for run in self._alive:
            run.stopped = True
        deadline = time.monotonic() + CLOSE_WAIT
        threads = [thread for run, thread in self._threads if not run.abandoned]  # those never end
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        left = sum(thread.is_alive() for thread in threads)
        if left:
            log.warning(tr("{count} geometry computations are still running after {seconds} s and are ended in "
                           "the background", count=left, seconds=int(CLOSE_WAIT)))
        self._alive.clear()
        self._threads.clear()

    def _look_ahead(self, current: int, index: int) -> bool:
        """Whether chunk ``index`` may start: only while an element keeps chunk ``current`` waiting."""
        if index > current + LOOKAHEAD_CHUNKS:
            return False
        if not any(run.index <= current and run.busy() for run in self._alive):
            return False
        available = available_memory()
        return available is None or available >= LOOKAHEAD_MEMORY

    def _next_planned(self) -> tuple[int, list, str] | None:
        while not self._planned:
            index, chunk = next(self._chunks, (None, None))
            if chunk is None:
                return None
            self._planned.extend((index, part, library) for part, library in self._parts(chunk))
        return self._planned[0]

    def _start_planned(self) -> None:
        index, products, library = self._planned.popleft()
        self._started.append(self.start(index, products, library))

    def _parts(self, chunk: list) -> list[tuple[list, str]]:
        """The runs of a chunk: under "accurate" its large triangle meshes with the hybrid kernel
        (see _triangle_mesh_only) and the rest with OpenCASCADE."""
        if self.strategy == "accurate":
            meshes = [product for product in chunk if _triangle_mesh_only(product)]
            fast = {product.id() for product in meshes}
            rest = [product for product in chunk if product.id() not in fast]
            parts = [(meshes, LIBRARIES["hybrid"]), (rest, LIBRARIES["opencascade"])]
        else:
            parts = [(chunk, self.library)]
        return [(part, library) for part, library in parts if part]

    def _computed(self, run: _Run, shape) -> None:
        """Called by the threads of the runs for each shape the kernel delivers: noted, reported and
        queued for iter_shapes in one go, so that abandoning the run (see hung) loses none of them."""
        with self._lock:
            if run.stopped:
                return
            run.computed.add(shape.id)
            run.last_delivery = time.monotonic()
            if self._position:
                self._position("delivered", [shape.id], "")
            run.queue_shape(shape)


class KernelHung(Exception):
    """A single computation in the kernel took longer than the hang limit (see HANG_SECONDS)."""


def hang_limit(kind: str) -> float:
    """The hang limit in seconds of pass ``kind`` ("fine", "coarse", "preview"), see HANG_SECONDS;
    the environment variable HANG_ENV overrides it (e.g. for tests)."""
    value = os.environ.get(HANG_ENV)
    if value:
        try:
            return float(value)
        except ValueError:
            pass
    return float(HANG_SECONDS[kind])


# Objects a thread stuck in the kernel still uses (iterators, models, settings): never freed, see
# _keep_forever. The list is for the record (and for process to see that there are any).
_ABANDONED: list = []


def _keep_forever(obj) -> None:
    """Make ``obj`` immortal: an extra reference that is never dropped, so neither its destructor nor
    that of what it holds ever runs, not even at the interpreter's exit.

    IfcOpenShell's iterator joins its threads in its destructor, and a thread spinning on an element
    never returns: freeing the iterator would hang the exit forever, freeing the model under the
    thread would crash the process. So both stay, and the conversion process ends with os._exit
    (see process._child_main) once its result is sent.
    """
    if obj is None:
        return
    import ctypes

    ctypes.pythonapi.Py_IncRef.argtypes = (ctypes.py_object,)
    ctypes.pythonapi.Py_IncRef(obj)
    _ABANDONED.append(obj)


def abandoned() -> int:
    """How many objects this process keeps for threads stuck in the kernel (0: nothing was abandoned)."""
    return len(_ABANDONED)


def _minutes(limit: float) -> int:
    return round(limit / 60)


def _report_hung(product, hung_ids: set[int], status, position, limit: float, quiet: bool = False) -> None:
    """Note ``product`` as hung: skipped like one the kernel crashed on (result.crashed, the parent's
    quarantine through ``position``), or kept in the hull's coarse pass (see envelope.select)."""
    hung_ids.add(product.id())
    label = product_label(product)
    hung = _hung.get()
    if hung is None:  # the coarse pass approximates only: an unknown product is kept
        if status and not quiet:
            status("note", tr("The geometry kernel hung on {label} for more than {minutes} min in the rough "
                              "pre-computation: the element is kept as part of the hull", label=label,
                              minutes=_minutes(limit)))
        return
    hung.append(label)
    if position:
        position("hung", [product.id()], label)
    if status and not quiet:
        status("note", tr("The geometry kernel hung on {label} for more than {minutes} min: the element is skipped",
                          label=label, minutes=_minutes(limit)))


def _after_hang(
    run: _Run, settings, strategy: str, position, status, limit: float, hung_ids: set[int], leftover: list,
) -> Iterator:
    """The shapes of the products of the abandoned ``run`` that the kernel had not delivered.

    Only the kernel knows which of them it hung on. A single undelivered product is the one (the
    kernel's other threads finished the rest, the usual case). Of several, each is computed on its
    own under the same limit (see _deep_shape), at most HANG_RETRY_LIMIT of them and no more once
    HANG_RETRY_HANGS hung as well; the rest go into ``leftover`` for the caller (a fresh run, see
    HANG_ROUNDS, or _give_up_hung), so nothing is claimed about them that is not known.
    """
    undelivered = [product for product in run.products if product.id() not in run.computed]
    if not undelivered:  # the run finished the moment it was abandoned
        return
    if len(undelivered) == 1:
        _report_hung(undelivered[0], hung_ids, status, position, limit)
        return
    if status:
        status("note", tr("The geometry kernel hung on one of {count} elements for more than {minutes} min: they are "
                          "computed one by one …", count=len(undelivered), minutes=_minutes(limit)))
    hangs = 0
    for number, product in enumerate(undelivered):
        if hangs >= HANG_RETRY_HANGS or number >= HANG_RETRY_LIMIT:
            leftover.extend(undelivered[number:])
            return
        if position:
            position("element", [product.id()], product_label(product))
        try:
            shape = _deep_shape(settings, product, strategy, limit, run.model)
        except KernelHung:
            hangs += 1
            _report_hung(product, hung_ids, status, position, limit)
            continue
        if shape is not None:
            yield shape


def _give_up_hung(rest: list, status, position, limit: float, hung_ids: set[int]) -> None:
    """Report ``rest`` (products of a chunk the kernel kept hanging on) as not computed."""
    if status:
        if _hung.get() is None:
            status("note", tr("{count} elements not computed because the geometry kernel hung on their chunk "
                              "in the rough pre-computation: they are kept as part of the hull", count=len(rest)))
        else:
            status("note", tr("{count} elements not computed because the geometry kernel hung on their "
                              "chunk: they are skipped", count=len(rest)))
    for product in rest:
        _report_hung(product, hung_ids, status, position, limit, quiet=True)


def _parts_produced(product: ifcopenshell.entity_instance, produced: set[int]) -> bool:
    """Whether any part that ``product`` is decomposed into (IfcRelAggregates, at any depth) became geometry."""
    stack, seen = [product], {product.id()}
    while stack:
        for relation in getattr(stack.pop(), "IsDecomposedBy", None) or ():
            for part in relation.RelatedObjects:
                if part.id() in produced:
                    return True
                if part.id() not in seen:
                    seen.add(part.id())
                    stack.append(part)
    return False


def _produced(shape, produced: set[int]):
    """``shape``, noted in ``produced`` if it has geometry."""
    if has_geometry(shape):
        produced.add(shape.id)
    return shape


def has_geometry(shape) -> bool:
    """Whether ``shape`` (triangulated, or native B-rep for the STEP/IGES serializers) is not empty."""
    geometry = shape.geometry
    verts = getattr(geometry, "verts", None)
    if verts is not None:
        return bool(verts)
    return geometry.size() > 0  # native: the number of OpenCASCADE shapes


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


def _deep_shape(
    settings: geom.settings, product: ifcopenshell.entity_instance, strategy: str, limit: float | None = None,
    model=None, deadline: float | None = None,
):
    """The shape of a deeply nested product, computed in a thread with DEEP_STACK of stack, or None.

    geom.create_shape() computes in the calling thread, unlike the iterator's worker threads.
    Raises KernelHung once the computations (up to four: two kernels, local and world coordinates)
    together take longer than ``limit`` seconds (or reach ``deadline``, a time.monotonic() value,
    shared with other attempts for the product): the parent allows a single element the limit
    plus a margin before it ends the process (see process.silence_limit). ``model`` is then kept
    alive for the thread left behind (see _keep_forever).
    """
    representation = _body_representation(product)
    if representation is None:
        return None
    if deadline is None and limit is not None:
        deadline = time.monotonic() + limit
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
            shape = _with_large_stack(compute, _time_left(deadline), model)
        except RuntimeError:  # the kernel could not build it
            continue
        if has_geometry(shape) or settings.get("use-world-coords"):
            return shape
        # Local coordinates gave nothing (type geometry with openings): world coordinates do.
        settings.set("use-world-coords", True)
        try:
            return _with_large_stack(compute, _time_left(deadline), model)
        except RuntimeError:
            continue
        finally:
            settings.set("use-world-coords", False)
    return None


def _time_left(deadline: float | None) -> float | None:
    """Seconds until ``deadline`` (None: no limit); KernelHung once it has passed."""
    if deadline is None:
        return None
    left = deadline - time.monotonic()
    if left <= 0:
        raise KernelHung
    return left


def _second_attempts(
    settings: geom.settings, products: list, position, budget: list[float], status=None, limit: float | None = None,
    hung_ids: set[int] | None = None, model=None,
) -> Iterator:
    """Second attempts for ``products`` that the iterator gave no geometry, one by one, as long as
    ``budget[0]`` seconds are left: OpenCASCADE with RESCUE_PRECISION, then the hybrid kernel.
    An attempt that hangs (``limit``, see _deep_shape) makes the product a hung one.

    OpenCASCADE gives up on some faceted solids at its default tolerance of 0.01 mm that it builds
    at 0.001 mm (beams of millimetre bridges, which came out right only while the file's unit was
    misread as metres and everything was 1000x larger).
    """
    for product in products:
        if budget[0] <= 0:
            return
        if position:
            position("element", [product.id()], product_label(product))
        started = time.monotonic()
        deadline = started + limit if limit is not None else None  # both attempts together
        previous = settings.get("precision")
        settings.set("precision", RESCUE_PRECISION)
        try:
            shape = _deep_shape(settings, product, "opencascade", limit, model, deadline)
            if (shape is None or not has_geometry(shape)) and not _native_output(settings):
                # The STEP writer drops the hybrid kernel's shapes, so they are no rescue there.
                settings.set("precision", previous)
                shape = _deep_shape(settings, product, "hybrid", limit, model, deadline)
        except KernelHung:
            _report_hung(product, hung_ids if hung_ids is not None else set(), status, position, limit or 0.0)
            shape = None
        finally:
            settings.set("precision", previous)
        budget[0] -= time.monotonic() - started
        if shape is not None and has_geometry(shape):
            yield shape


def _native_output(settings: geom.settings) -> bool:
    """Whether ``settings`` ask for B-rep shapes (STEP) instead of triangle meshes."""
    from ifc_converter.serializers import NATIVE_OUTPUT

    return settings.get("iterator-output") == NATIVE_OUTPUT


def _body_representation(product: ifcopenshell.entity_instance):
    """The representation the iterator would compute for ``product``: "Body", else the first 3D one."""
    representations = [r for r in product.Representation.Representations if r.is_a("IfcShapeModel") and r.Items]
    for identifier in ("Body", "Facetation"):
        for representation in representations:
            if representation.RepresentationIdentifier == identifier:
                return representation
    return next((r for r in representations if r.RepresentationType not in NON_BODY_TYPES), None)


def _with_large_stack(function: Callable, timeout: float | None = None, keep=None):
    """``function()`` run in a thread with DEEP_STACK of stack (the calling thread waits).

    Raises KernelHung if it is not done after ``timeout`` seconds: the thread is left behind (it
    cannot be stopped), with ``function`` and ``keep`` (the model) alive for it, see _keep_forever.
    """
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["value"] = function()
        except BaseException as exc:  # handed to the calling thread
            outcome["error"] = exc

    previous = threading.stack_size(DEEP_STACK)
    try:
        # A daemon: a thread left behind must not keep the interpreter from exiting.
        thread = threading.Thread(target=run, name="deep-geometry", daemon=True)
        thread.start()
    finally:
        threading.stack_size(previous)
    thread.join(timeout)
    if thread.is_alive():
        _keep_forever(function)
        _keep_forever(keep)
        raise KernelHung
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


def _start_iterator(model, settings, threads: int, products: list, library: str, timeout: float | None) -> Iterator:
    """_iterate(), but given up after ``timeout`` seconds (None: never): the iterator's start waits
    for its first shape, which a kernel thread spinning on each of the first products never delivers.
    Raises KernelHung then; the thread left behind keeps the iterator and the model (see _keep_forever)."""
    if timeout is None:
        return _iterate(model, settings, threads, products, library)
    outcome: dict = {}

    def start() -> None:
        try:
            outcome["shapes"] = _iterate(model, settings, threads, products, library)
        except BaseException as exc:  # handed to the calling thread
            outcome["error"] = exc

    thread = threading.Thread(target=start, name="geometry-start", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        # Should the start return after all, its shapes (the iterator) stay in outcome, never freed;
        # its threads go on computing the chunk in the background (like those of an abandoned run).
        _keep_forever(outcome)
        _keep_forever(model)
        raise KernelHung
    if "error" in outcome:
        raise outcome["error"]
    return outcome["shapes"]


def _iterate(model, settings, threads: int, products: list, library: str) -> Iterator:
    """Start one geometry iterator for ``products`` and return its shapes; it is freed after the last.

    Its threads compute in the background from now on, while the shapes are only taken later.
    """
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
    return _Shapes(iterator if initialized else None, model)


class _Shapes:
    """The shapes of an initialized geometry iterator (None: no shapes), which it keeps alive.

    It also keeps the model, which the iterator only points to, and is released after the iterator.
    """

    def __init__(self, iterator, model):
        self.iterator = iterator
        self.model = model

    def __del__(self):
        self.iterator = None  # before the model
        self.model = None

    def __iter__(self) -> Iterator:
        if self.iterator is None:
            return
        while True:
            yield self.iterator.get()
            if not self.iterator.next():
                break


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


def memory_warning(input_path: str | Path) -> str | None:
    """A warning if the file probably needs more RAM than the machine has free, else None."""
    size = Path(input_path).stat().st_size
    # The working memory on top of the model only matters for real models, not for tiny test files.
    needed = size * MEMORY_PER_IFC_BYTE + min(MEMORY_BASE, size * 20)
    available = available_memory()
    if available is None or needed <= available:
        return None
    return tr(
        "{name} will probably need about {needed} GB of memory, only {available} GB are free. Close other "
        "programs, otherwise it gets very slow or the conversion breaks off.",
        name=Path(input_path).name, needed=_gb(needed), available=_gb(available),
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
