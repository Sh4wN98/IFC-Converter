"""Preview of an IFC model: a light triangle mesh of the whole model for the viewer in the window.

The preview is computed like a conversion, in a child process (see process.convert_in_child), and
kept in a cache, so that a file shows at once the next time it is selected. It favours speed over
accuracy: the fast geometry kernel, coarse curves, and at most PREVIEW_TRIANGLES triangles.

This module holds the data the viewer draws (PreviewMesh), how it is stored on disk, how it is
computed (write_preview in the child, compute_preview in the app) and the cache of computed previews.

The preview is progressive: while the child computes, it writes what it has since the previous batch
to small batch files beside the target (see _Batches, batch_paths); the pane polls for them and
merges them (merge_batch) into a growing mesh, so a rough picture shows within seconds, structure
first (PREVIEW_CLASS_PRIORITY), while details (PREVIEW_DETAIL_CLASSES) are left out entirely.
"""

from __future__ import annotations

import hashlib
import heapq
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy

from ifc_converter.i18n import tr

# Bumped whenever the stored arrays or the info change; older files are ignored (computed again).
PREVIEW_FORMAT_VERSION = 2

# The preview of a model has at most this many triangles (about 100 MB in the viewer); beyond that
# the smallest elements (by the size of their bounding box) are left out first, see _Collector.
PREVIEW_TRIANGLES = 3_000_000
# The hybrid kernel is 3-13x faster than OpenCASCADE on real models; that it drops or duplicates a
# few faces now and then does not matter for a look at the model.
PREVIEW_KERNEL = "hybrid"
# Coarser curves than a conversion (LINEAR_DEFLECTION, 0.5 mm): a round column of 50 cm gets 16
# instead of 64 sides at 1 cm. The angular deflection is the kernel's own default.
PREVIEW_LINEAR_DEFLECTION = 0.01
PREVIEW_ANGULAR_DEFLECTION = 0.5
# Threads of the kernel at most: PREVIEW_THREADS while no conversion runs, PREVIEW_THREADS_BUSY
# beside one (and the user's other demanding programs), see preview_threads.
PREVIEW_THREADS = 8
PREVIEW_THREADS_BUSY = 4
# Left out of the preview, besides what the kernel cannot show as faces anyway (curves, points):
# openings (cut into their walls instead), rooms, which would hide the building inside, annotation,
# virtual elements (space boundaries), zones and grid and alignment axes.
PREVIEW_EXCLUDED = [
    "IfcFeatureElementSubtraction", "IfcSpace", "IfcSpatialZone", "IfcAnnotation", "IfcVirtualElement", "IfcGrid",
    "IfcPositioningElement", "IfcAlignmentHorizontal", "IfcAlignmentVertical", "IfcAlignmentCant",
    "IfcAlignmentSegment",
]
# Structure first: the products are computed in this order of classes (within a class in the model's
# order), so that the first batches of a progressive preview already show site, slabs, roofs and walls.
PREVIEW_CLASS_PRIORITY = [
    "IfcSite", "IfcGeographicElement", "IfcSlab", "IfcRoof", "IfcWall", "IfcColumn", "IfcBeam", "IfcStair",
    "IfcStairFlight", "IfcRamp", "IfcRampFlight", "IfcCurtainWall", "IfcPlate", "IfcMember", "IfcWindow",
    "IfcDoor", "IfcRailing",
]
# Details left out of the preview entirely (a look at the model does not need them, and they are most
# of the elements of a big model): kind -> classes (with their subclasses). Counted in
# mesh.info["details_left_out"], the kinds found in mesh.info["detail_kinds"] (see detail_kind_name).
# Products nested deeper than converter.DEEP_NESTING (the kernel computes them one by one with a big
# stack; they are the ones that crash it) are left out as well, as the kind "deep".
PREVIEW_DETAIL_CLASSES = {
    "furniture": ["IfcFurnishingElement"],
    "mep": ["IfcDistributionElement"],  # IfcFlow*, IfcEnergyConversionDevice, IfcDistributionControlElement …
    "fasteners": ["IfcFastener", "IfcMechanicalFastener", "IfcDiscreteAccessory", "IfcVibrationIsolator",
                  "IfcVibrationDamper"],
    "reinforcement": ["IfcReinforcingElement", "IfcTendon", "IfcTendonAnchor"],
}
DETAIL_KINDS = (*PREVIEW_DETAIL_CLASSES, "deep")
# Progressive preview: the elements collected since the previous batch are written to a batch file
# every BATCH_SECONDS at first, then every BATCH_SHARE of the time since the geometry started, or
# as soon as BATCH_TRIANGLES are pending (see _Batches). Tests shorten both through BATCH_ENV
# ("seconds,triangles"), which the child inherits.
BATCH_SECONDS = 2.0
BATCH_SHARE = 0.05
BATCH_TRIANGLES = 200_000
BATCH_ENV = "IFC_CONVERTER_PREVIEW_BATCH"
# A batch file is "<target name>.part-<token>-<number>.npz" (see batch_path): the token tells the
# attempts of a retried computation apart, the number orders the batches of one attempt.
BATCH_NAME = re.compile(r"\.part-(\d+)-(\d{4})\.npz$")
# Cache of computed previews: in the app's local data folder, never beside the IFC (often a network
# share, and not ours to write to). The oldest used previews go once they take more than this.
PREVIEW_CACHE_NAME = "previews"
PREVIEW_CACHE_BYTES = 2 * 1024 ** 3
# A ".part" or batch file older than this is the leftover of a computation that was killed.
STALE_PART_AGE = 3600
# Colour of faces without a material or style (as in the Rhino export).
DEFAULT_COLOR = (180, 180, 180, 255)

log = logging.getLogger(__name__)


@dataclass
class PreviewMesh:
    """A model as indexed triangles, with one colour per vertex.

    Coordinates are in metres, relative to ``origin`` (float64): the model's own coordinates can be
    hundreds of kilometres out (georeferenced), which single precision on the GPU cannot hold.
    A model point is ``positions[i] + origin``. IFC is Z-up.
    """

    positions: numpy.ndarray  # (V, 3) float32, metres, relative to origin
    colors: numpy.ndarray  # (V, 4) uint8 RGBA; alpha < 255 is transparent (glass)
    indices: numpy.ndarray  # (3 * T,) uint32, counter-clockwise seen from outside
    triangle_elements: numpy.ndarray  # (T,) uint32: index into ``elements`` of each triangle
    elements: list[str]  # labels "IfcClass GlobalId „Name“" (converter.product_label)
    origin: numpy.ndarray = field(default_factory=lambda: numpy.zeros(3))  # (3,) float64
    # Shown under the view: e.g. {"source": "Haus.ifc", "schema": "IFC4", "elements": 1234,
    # "triangles": 456789, "left_out": 0, "details_left_out": 321, "detail_kinds": "furniture,mep"}.
    # A merged batch (merge_batch) has "partial": 1 and "elements_total". Plain str/int/float values.
    info: dict = field(default_factory=dict)

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3

    def bounds(self) -> tuple[numpy.ndarray, numpy.ndarray]:
        """Minimum and maximum corner of the positions (relative to origin); zeros if empty."""
        if not len(self.positions):
            return numpy.zeros(3, numpy.float32), numpy.zeros(3, numpy.float32)
        return self.positions.min(axis=0), self.positions.max(axis=0)


def save_preview(mesh: PreviewMesh, path: str | Path) -> None:
    """Write ``mesh`` to ``path`` (.npz, plain arrays only), replacing it as a whole."""
    path = Path(path)
    part = path.with_name(path.name + ".part")
    keys = sorted(mesh.info)
    with open(part, "wb") as file:
        numpy.savez(
            file,
            version=numpy.array(PREVIEW_FORMAT_VERSION),
            positions=numpy.ascontiguousarray(mesh.positions, numpy.float32),
            colors=numpy.ascontiguousarray(mesh.colors, numpy.uint8),
            indices=numpy.ascontiguousarray(mesh.indices, numpy.uint32),
            triangle_elements=numpy.ascontiguousarray(mesh.triangle_elements, numpy.uint32),
            elements=numpy.array(mesh.elements, dtype=str) if mesh.elements else numpy.zeros(0, dtype="<U1"),
            origin=numpy.asarray(mesh.origin, numpy.float64),
            info_keys=numpy.array(keys, dtype=str) if keys else numpy.zeros(0, dtype="<U1"),
            info_values=numpy.array([str(mesh.info[key]) for key in keys], dtype=str)
            if keys else numpy.zeros(0, dtype="<U1"),
        )
    part.replace(path)


def load_preview(path: str | Path) -> PreviewMesh | None:
    """The mesh stored at ``path``, or None if it is missing, damaged or of another format version."""
    try:
        with numpy.load(path, allow_pickle=False) as data:
            if int(data["version"]) != PREVIEW_FORMAT_VERSION:
                return None
            info = {}
            for key, value in zip(data["info_keys"].tolist(), data["info_values"].tolist()):
                info[key] = _number(value)
            mesh = PreviewMesh(
                positions=data["positions"].reshape(-1, 3),
                colors=data["colors"].reshape(-1, 4),
                indices=data["indices"].reshape(-1),
                triangle_elements=data["triangle_elements"].reshape(-1),
                elements=data["elements"].tolist(),
                origin=data["origin"].reshape(3),
                info=info,
            )
    except (OSError, KeyError, ValueError, EOFError):
        return None
    if len(mesh.colors) != len(mesh.positions) or len(mesh.indices) % 3 \
            or len(mesh.triangle_elements) != mesh.triangle_count:
        return None
    if len(mesh.indices) and int(mesh.indices.max()) >= len(mesh.positions):
        return None
    return mesh


def _number(text: str) -> str | int | float:
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return text


def batch_path(target: str | Path, token: int, number: int) -> Path:
    """Where batch ``number`` of the attempt ``token`` of the preview computed at ``target`` goes."""
    target = Path(target)
    return target.with_name(f"{target.name}.part-{token}-{number:04d}.npz")


def batch_paths(target: str | Path) -> list[Path]:
    """The batch files written so far for the preview computed at ``target``, in the order written
    (an earlier attempt's before a later one's, see batch_token)."""
    target = Path(target)
    prefix = target.name + ".part-"
    found = []
    try:
        for path in target.parent.iterdir():
            match = BATCH_NAME.search(path.name) if path.name.startswith(prefix) else None
            if match and path.name[len(target.name):] == match.group(0):
                found.append((int(match.group(1)), int(match.group(2)), path))
    except OSError:
        return []
    return [path for _, _, path in sorted(found)]


def batch_token(path: str | Path) -> int:
    """The attempt a batch file belongs to: each attempt of a retried computation has its own token."""
    match = BATCH_NAME.search(Path(path).name)
    return int(match.group(1)) if match else 0


def remove_batches(target: str | Path) -> int:
    """Remove the batch files of the preview at ``target``; returns how many went."""
    return sum(_remove(path) for path in batch_paths(target))


def merge_batch(mesh: PreviewMesh | None, batch: PreviewMesh) -> PreviewMesh:
    """``mesh`` (the batches merged so far, or None) with the elements of ``batch`` appended: one
    growing mesh around the first batch's origin, with ``info["partial"]`` set."""
    if mesh is None:
        positions, colors, indices = batch.positions, batch.colors, batch.indices
        triangle_elements, elements, origin = batch.triangle_elements, list(batch.elements), batch.origin
    else:
        shifted = batch.positions
        if not numpy.array_equal(batch.origin, mesh.origin):
            shifted = (batch.positions.astype(numpy.float64) + (batch.origin - mesh.origin)).astype(numpy.float32)
        positions = numpy.concatenate([mesh.positions, shifted])
        colors = numpy.concatenate([mesh.colors, batch.colors])
        indices = numpy.concatenate([mesh.indices, batch.indices + numpy.uint32(len(mesh.positions))])
        triangle_elements = numpy.concatenate([mesh.triangle_elements,
                                               batch.triangle_elements + numpy.uint32(len(mesh.elements))])
        elements, origin = mesh.elements + list(batch.elements), mesh.origin
    info = dict(batch.info)
    info.update(elements=len(elements), triangles=len(indices) // 3, partial=1)
    return PreviewMesh(positions=positions, colors=colors, indices=indices, triangle_elements=triangle_elements,
                       elements=elements, origin=origin, info=info)


def detail_kind_name(kind: str) -> str:
    """How a kind of PREVIEW_DETAIL_CLASSES (or "deep") is called under the view."""
    names = {
        "furniture": tr("furniture"), "mep": tr("MEP"), "fasteners": tr("fasteners"),
        "reinforcement": tr("reinforcement"), "deep": tr("deeply nested"),
    }
    return names.get(kind, kind)


def preview_cache_dir() -> Path:
    """%LOCALAPPDATA%\\IFC Converter\\previews on Windows, ~/.local/state/ifc-converter/previews on Linux."""
    from ifc_converter.app import log_dir

    return log_dir().parent / PREVIEW_CACHE_NAME


def preview_path(ifc_path: str | Path) -> Path:
    """Where the preview of ``ifc_path`` is cached, by a hash of what makes it what it is: the file
    (absolute path, size, modification time), the format and settings of the preview and the version
    of IfcOpenShell. A changed file gets a new name, its old preview is pruned in time. Raises
    OSError if the file cannot be read."""
    import ifcopenshell

    path = os.path.normcase(os.path.abspath(ifc_path))
    stat = os.stat(path)
    from ifc_converter.converter import DEEP_NESTING

    details = ",".join(sorted(name for classes in PREVIEW_DETAIL_CLASSES.values() for name in classes))
    key = "|".join(str(part) for part in (
        path, stat.st_size, stat.st_mtime_ns, PREVIEW_FORMAT_VERSION, PREVIEW_TRIANGLES, PREVIEW_KERNEL,
        PREVIEW_LINEAR_DEFLECTION, PREVIEW_ANGULAR_DEFLECTION, f"ifcopenshell {ifcopenshell.version}",
        f"details {details}", f"deep {DEEP_NESTING}",
    ))
    digest = hashlib.sha256(key.encode("utf-8", "surrogatepass")).hexdigest()[:32]
    return preview_cache_dir() / f"{digest}.npz"


def cached_preview(ifc_path: str | Path) -> Path | None:
    """The cached preview of ``ifc_path`` if there is a usable one (it then counts as used now), else
    None. A damaged one or one of another format version is removed."""
    try:
        path = preview_path(ifc_path)
    except OSError:
        return None
    try:
        with numpy.load(path, allow_pickle=False) as data:  # reads only the directory and the version
            usable = int(data["version"]) == PREVIEW_FORMAT_VERSION
    except FileNotFoundError:
        return None
    except (OSError, KeyError, ValueError, EOFError):
        usable = False
    if not usable:
        _remove(path)
        return None
    try:
        os.utime(path)  # for prune_cache: used last now
    except OSError:
        pass
    return path


def prune_cache(limit: int | None = None, keep: Path | None = None) -> int:
    """Remove the least recently used previews until the cache takes at most ``limit`` bytes
    (PREVIEW_CACHE_BYTES; never ``keep``), and leftovers of killed computations (".part" and batch
    files older than STALE_PART_AGE). Returns how many files went; errors are skipped."""
    limit = PREVIEW_CACHE_BYTES if limit is None else limit
    folder = preview_cache_dir()
    try:
        entries = []
        for path in folder.iterdir():
            stat = path.stat()
            entries.append((stat.st_mtime, stat.st_size, path))
    except OSError:
        return 0
    removed = 0
    now = time.time()
    previews = []
    for mtime, size, path in entries:
        if path.name.endswith(".part") or BATCH_NAME.search(path.name):
            if now - mtime > STALE_PART_AGE and _remove(path):
                removed += 1
        elif path.suffix == ".npz":
            previews.append((mtime, size, path))
    total = sum(size for _, size, _ in previews)
    for _, size, path in sorted(previews, key=lambda entry: entry[0]):
        if total <= limit:
            break
        if keep is not None and path == Path(keep):
            continue
        if _remove(path):
            removed += 1
            total -= size
    return removed


def _remove(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        log.debug("Vorschau %s ließ sich nicht löschen: %s", path, exc)
        return False


def preview_threads(busy: bool = False) -> int:
    """The kernel threads of a preview: at most PREVIEW_THREADS, PREVIEW_THREADS_BUSY while a
    conversion runs (``busy``), fewer on small PCs (default_threads)."""
    from ifc_converter.converter import default_threads

    return min(PREVIEW_THREADS_BUSY if busy else PREVIEW_THREADS, default_threads())


def fits_in_memory(size: int, busy: bool = False) -> bool | None:
    """Whether the preview of an IFC of ``size`` bytes has room in the free memory (as a conversion
    needs it: converter.MEMORY_BASE plus MEMORY_PER_IFC_BYTE per byte, twice the size while a
    conversion runs, as both keep their model in memory); None if the free memory is unknown."""
    from ifc_converter.converter import MEMORY_BASE, MEMORY_PER_IFC_BYTE, available_memory

    available = available_memory()
    if available is None:
        return None
    return available >= MEMORY_BASE + MEMORY_PER_IFC_BYTE * size * (2 if busy else 1)


def batch_settings() -> tuple[float, int]:
    """(seconds, triangles) of _Batches: BATCH_SECONDS and BATCH_TRIANGLES unless BATCH_ENV says otherwise."""
    value = os.environ.get(BATCH_ENV, "")
    if value:
        try:
            seconds, triangles = value.split(",")
            return float(seconds), int(triangles)
        except ValueError:
            log.warning("%s=%r ist nicht „Sekunden,Dreiecke“, Standardwerte werden verwendet", BATCH_ENV, value)
    return BATCH_SECONDS, BATCH_TRIANGLES


def compute_preview(
    input_path: str | Path,
    output_npz: str | Path | None = None,
    threads: int | None = None,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    status: Callable[[str, str], None] | None = None,
    on_retry: Callable[[str], None] | None = None,
    low_priority: bool = True,
) -> Path:
    """Compute the preview of ``input_path`` and save it at ``output_npz`` (default: preview_path,
    in the cache, which is then pruned); returns where it is. Blocks until done: call it from a
    worker thread.

    It runs like a conversion in a child process (process.convert_in_child): below normal priority,
    in a job object with a memory limit (Windows), ended with the app. A crash or hang in the fast
    kernel is retried with OpenCASCADE alone, one there without the elements concerned (see
    convert_in_child's ``opencascade_first``). ``progress``, ``cancelled``, ``status`` and ``on_retry``
    are those of convert_in_child: a cancel raises process.Cancelled, failures ConversionFailed,
    ConversionCrashed or ConversionStalled. ``threads`` defaults to preview_threads(). The same file
    should not be computed twice at once (both would save through the same ".part" file).
    """
    from ifc_converter.process import convert_in_child

    output = Path(output_npz) if output_npz else preview_path(input_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        convert_in_child(
            input_path, output, "preview", threads or preview_threads(), progress, cancelled,
            on_retry=on_retry, low_priority=low_priority, status=status, opencascade_first=True,
            kernel=PREVIEW_KERNEL,
        )
    finally:
        _remove(output.with_name(output.name + ".part"))  # of a child stopped while saving
        remove_batches(output)
    if output.parent == preview_cache_dir():
        prune_cache(keep=output)
    return output


def preview_settings():
    """Geometry settings of the preview: world coordinates, coarse curves, no normals (the viewer
    shades flat), welded vertices (fewer of them; colours are split by material in _Collector)."""
    import ifcopenshell.geom as geom

    settings = geom.settings()
    settings.set("mesher-linear-deflection", PREVIEW_LINEAR_DEFLECTION)
    settings.set("mesher-angular-deflection", PREVIEW_ANGULAR_DEFLECTION)
    settings.set("use-world-coords", True)
    settings.set("no-normals", True)
    return settings


def write_preview(
    model,
    output_path: Path,
    threads: int,
    progress: Callable[[int], None] | None = None,
    status: Callable[[str, str], None] | None = None,
    source: Path | None = None,
    read_seconds: float = 0.0,
) -> int:
    """Compute the preview of ``model`` and save it at ``output_path``; returns the elements with
    geometry (those left out for the triangle budget included, as they are no elements without;
    details left out entirely are not counted, see select_products).

    Runs in the conversion child, as convert(fmt="preview"). The elements' triangles are collected
    shape by shape (the kernel's shapes are not kept) within PREVIEW_TRIANGLES, and written to batch
    files on the way (see _Batches), structure first.
    """
    from ifc_converter.converter import iter_shapes, product_label, shape_products

    started = time.monotonic()
    products, details = select_products(shape_products(model, PREVIEW_EXCLUDED))
    collector = _Collector(PREVIEW_TRIANGLES, {product.id(): index for index, product in enumerate(products)})
    info = {
        "details_left_out": sum(details.values()),
        "detail_kinds": ",".join(kind for kind in DETAIL_KINDS if details.get(kind)),
    }

    def label(id_: int) -> str:
        return product_label(model.by_id(id_))

    batches = _Batches(output_path, collector, label, {**info, "elements_total": len(products)})
    for shape in iter_shapes(
        model, preview_settings(), threads, PREVIEW_EXCLUDED, progress, 95, products, status=status,
    ):
        collector.add(shape)
        batches.check()
    geometry_seconds = time.monotonic() - started
    if status:
        status("write", tr("Saving preview ({count} triangles) …", count=collector.triangles))
    mesh = collector.mesh(label)
    mesh.info = {
        "source": source.name if source else "",
        "schema": model.schema_identifier,
        "elements": len(mesh.elements),
        "triangles": mesh.triangle_count,
        "left_out": collector.left_out,
        **info,
        "read_seconds": round(read_seconds, 2),
        "geometry_seconds": round(geometry_seconds, 2),
        "seconds": round(read_seconds + time.monotonic() - started, 2),
    }
    if not mesh.elements:
        if collector.left_out:  # each element alone over the budget, e.g. a single huge terrain
            raise ValueError(tr("Too many triangles for the preview (more than {limit} per element).",
                                limit=f"{PREVIEW_TRIANGLES:,}".replace(",", ".")))
        return 0  # convert() reports a model without any geometry
    save_preview(mesh, output_path)
    return len(mesh.elements) + collector.left_out


def select_products(products: list) -> tuple[list, dict[str, int]]:
    """The products of the preview, structure first (see PREVIEW_CLASS_PRIORITY), and how many
    details were left out by kind (PREVIEW_DETAIL_CLASSES and the deeply nested ones, "deep").
    A model of details only (a plumbing model) keeps them: a preview of nothing helps nobody."""
    from ifc_converter.converter import deep_products

    counts = dict.fromkeys(DETAIL_KINDS, 0)
    kind_of_class: dict[str, str | None] = {}  # by class name: is_a per product would be slow
    kept, details = [], []
    for product in products:
        name = product.is_a()
        if name not in kind_of_class:
            kind_of_class[name] = next(
                (kind for kind, classes in PREVIEW_DETAIL_CLASSES.items() if any(product.is_a(c) for c in classes)),
                None,
            )
        kind = kind_of_class[name]
        if kind:
            counts[kind] += 1
            details.append(product)
        else:
            kept.append(product)
    if not kept:  # a model of details only (a plumbing model): then they are the model
        kept, counts = details, dict.fromkeys(DETAIL_KINDS, 0)
    deep = {product.id() for product, _ in deep_products(kept)}
    if deep:
        counts["deep"] = len(deep)
        kept = [product for product in kept if product.id() not in deep]
    return order_products(kept), counts


def order_products(products: list) -> list:
    """``products`` by class priority (PREVIEW_CLASS_PRIORITY, then the rest), in model order within."""
    ranks: dict[str, int] = {}
    last = len(PREVIEW_CLASS_PRIORITY)

    def rank(product) -> int:
        name = product.is_a()
        if name not in ranks:
            ranks[name] = next((i for i, cls in enumerate(PREVIEW_CLASS_PRIORITY) if product.is_a(cls)), last)
        return ranks[name]

    return sorted(products, key=rank)  # stable: model order within a class


class _Batches:
    """Writes the elements collected since the previous batch to a batch file now and then (see
    BATCH_SECONDS), so the pane shows the model while it is still being computed: the first batch
    after BATCH_SECONDS, later ones at growing intervals, or sooner once BATCH_TRIANGLES are pending.
    All batches share the first batch's origin (the centre of its bounding box). Writing stops once
    the collector drops elements for its budget: the final file replaces everything then. Batch
    files of an earlier attempt at the same target are removed first."""

    def __init__(self, target: str | Path, collector: _Collector, label: Callable[[int], str], info: dict):
        self.target, self.collector, self.label, self.info = Path(target), collector, label, dict(info)
        self.seconds, self.triangles = batch_settings()
        self.token = time.time_ns() // 1_000_000
        self.started = self.last = time.monotonic()
        self.number = 0
        self.origin: numpy.ndarray | None = None
        self.stopped = False
        remove_batches(self.target)

    def check(self) -> None:
        """Write a batch if one is due (called after every shape)."""
        if self.stopped:
            return
        if self.collector.dropping:
            self.stopped = True
            self.collector.added, self.collector.added_triangles = [], 0
            return
        if not self.collector.added:
            return
        now = time.monotonic()
        due = self.collector.added_triangles >= self.triangles \
            or now - self.last >= max(self.seconds, BATCH_SHARE * (now - self.started))
        if due:
            self.write()
            self.last = time.monotonic()

    def write(self) -> None:
        parts, self.collector.added, self.collector.added_triangles = self.collector.added, [], 0
        if self.origin is None:
            bottom = numpy.min([part.anchor for part in parts], axis=0)
            top = numpy.max([part.top for part in parts], axis=0)
            self.origin = (bottom + top) / 2
        mesh = _assemble(parts, self.origin, self.label)
        self.number += 1
        mesh.info = {**self.info, "batch": self.number, "elements": len(parts), "triangles": mesh.triangle_count}
        try:
            save_preview(mesh, batch_path(self.target, self.token, self.number))
        except OSError as exc:  # no room or rights: the final file still comes
            log.warning("Vorschau-Zwischenstand %d ließ sich nicht schreiben: %s", self.number, exc)
            self.stopped = True


@dataclass(order=True)
class _Part:
    """The triangles of one element, kept by _Collector; ordered by size (bounding box diagonal)."""

    size: float
    id: int
    anchor: numpy.ndarray = field(compare=False)  # (3,) float64, the corner of the bounding box
    positions: numpy.ndarray = field(compare=False)  # (V, 3) float32, relative to anchor
    colors: numpy.ndarray = field(compare=False)  # (V, 4) uint8
    triangles: numpy.ndarray = field(compare=False)  # (T, 3) uint32
    top: numpy.ndarray = field(compare=False)  # (3,) float64, the opposite corner


class _Collector:
    """Collects the triangles of the shapes, at most ``budget`` of them.

    Beyond the budget the smallest elements are dropped first, also those still to come: once an
    element was dropped, no smaller one is taken. So the result is the same in whatever order the
    kernel delivers the shapes. An element with more triangles than the budget alone is left out.
    Positions are kept relative to a corner of their element, in single precision: that is far below
    a millimetre for an element even 100 m large, however far out the model lies.
    """

    def __init__(self, budget: int, order: dict[int, int]):
        self.budget = budget
        self.order = order  # model order of the products, for the order of the elements
        self.parts: list[_Part] = []  # a heap, smallest first
        self.triangles = 0
        self.left_out = 0
        self._cut: tuple[float, int] | None = None  # (size, id) of the largest element dropped
        self.added: list[_Part] = []  # since the previous batch (_Batches takes them), in kernel order
        self.added_triangles = 0

    def add(self, shape) -> None:
        geometry = shape.geometry
        triangles = numpy.frombuffer(geometry.faces_buffer, dtype=numpy.int32).reshape(-1, 3)
        if not len(triangles):  # curves or points only
            return
        points = numpy.frombuffer(geometry.verts_buffer, dtype=numpy.float64).reshape(-1, 3)
        bottom, top = points.min(axis=0), points.max(axis=0)
        key = (float(numpy.linalg.norm(top - bottom)), int(shape.id))
        if len(triangles) > self.budget or (self._cut is not None and key <= self._cut):
            self.left_out += 1
            return
        points, colors, triangles = _colored(geometry, points, triangles)
        part = _Part(
            key[0], key[1], bottom, (points - bottom).astype(numpy.float32), colors,
            triangles.astype(numpy.uint32), top,
        )
        heapq.heappush(self.parts, part)
        self.added.append(part)
        self.added_triangles += len(triangles)
        self.triangles += len(triangles)
        while self.triangles > self.budget:
            dropped = heapq.heappop(self.parts)
            self.triangles -= len(dropped.triangles)
            self.left_out += 1
            self._cut = (dropped.size, dropped.id)

    @property
    def dropping(self) -> bool:
        """Whether elements have been dropped for the budget (from then on batches would mislead)."""
        return self._cut is not None

    def mesh(self, label: Callable[[int], str]) -> PreviewMesh:
        """The collected elements in model order as one mesh, around the centre of their bounding box."""
        parts = sorted(self.parts, key=lambda part: self.order.get(part.id, len(self.order)))
        if not parts:
            return PreviewMesh(
                positions=numpy.zeros((0, 3), numpy.float32), colors=numpy.zeros((0, 4), numpy.uint8),
                indices=numpy.zeros(0, numpy.uint32), triangle_elements=numpy.zeros(0, numpy.uint32), elements=[],
            )
        bottom = numpy.min([part.anchor for part in parts], axis=0)
        top = numpy.max([part.top for part in parts], axis=0)
        return _assemble(parts, (bottom + top) / 2, label)


def _assemble(parts: list[_Part], origin: numpy.ndarray, label: Callable[[int], str]) -> PreviewMesh:
    """``parts`` in their order as one mesh with positions relative to ``origin``."""
    vertices = sum(len(part.positions) for part in parts)
    triangles = sum(len(part.triangles) for part in parts)
    positions = numpy.empty((vertices, 3), numpy.float32)
    colors = numpy.empty((vertices, 4), numpy.uint8)
    indices = numpy.empty((triangles, 3), numpy.uint32)
    triangle_elements = numpy.empty(triangles, numpy.uint32)
    vertex = triangle = 0
    for number, part in enumerate(parts):
        count, faces = len(part.positions), len(part.triangles)
        positions[vertex:vertex + count] = part.positions + (part.anchor - origin)  # in float64, then rounded
        colors[vertex:vertex + count] = part.colors
        indices[triangle:triangle + faces] = part.triangles + vertex
        triangle_elements[triangle:triangle + faces] = number
        vertex += count
        triangle += faces
    return PreviewMesh(
        positions=positions, colors=colors, indices=indices.reshape(-1), triangle_elements=triangle_elements,
        elements=[label(part.id) for part in parts], origin=numpy.asarray(origin, numpy.float64),
    )


def _colored(geometry, points: numpy.ndarray, triangles: numpy.ndarray):
    """The vertices with one colour each (RGBA from the faces' materials, see rhino._material_of)
    and the triangles on them. A vertex shared by faces of different materials is split."""
    from ifc_converter.rhino import _main_material, _material_of

    palette = numpy.array([_material_of(material)[1] for material in geometry.materials] or [DEFAULT_COLOR],
                          numpy.uint8)
    ids = numpy.frombuffer(geometry.material_ids_buffer, dtype=numpy.int32)
    if len(ids) != len(triangles) or len(palette) == 1:
        ids = numpy.zeros(len(triangles), numpy.int64)
    else:  # faces without a material take the main one, as in the Rhino export
        valid = (ids >= 0) & (ids < len(palette))
        ids = numpy.where(valid, ids, _main_material(ids[valid]) if valid.any() else 0).astype(numpy.int64)
    if (ids == ids[0]).all():
        return points, numpy.broadcast_to(palette[ids[0]], (len(points), 4)), triangles
    keys = triangles.astype(numpy.int64) * len(palette) + ids[:, None]
    unique, inverse = numpy.unique(keys.reshape(-1), return_inverse=True)
    return points[unique // len(palette)], palette[unique % len(palette)], inverse.reshape(-1, 3)
