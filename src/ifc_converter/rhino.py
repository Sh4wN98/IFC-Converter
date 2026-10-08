from __future__ import annotations

import concurrent.futures
import functools
import itertools
import logging
import math
import multiprocessing
import os
import re
import threading
import weakref
from collections import OrderedDict, deque
from collections.abc import Iterator
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.ifcopenshell_wrapper as wrapper
import ifcopenshell.util.element as element_util
import ifcopenshell.util.unit as unit_util
import numpy
import rhino3dm

from ifc_converter.converter import (
    LINEAR_DEFLECTION, ChunkEnd, ProgressCallback, StatusCallback, available_memory, geometry_library,
    iter_shapes, shape_products,
)
from ifc_converter.polysurface import planar_polysurface
from ifc_converter.process import exit_with_parent, no_crash_dialogs

log = logging.getLogger(__name__)

NO_STOREY = "Ohne Geschoss"
# Root layer for curve-only elements outside the spatial structure, such as alignments.
AXES = "Achsen"
FILE_VERSION = 7
MAX_STRING_LENGTH = 1000
# Classes whose layers start hidden: rooms (IfcSpace) are volumes that fill every storey and would
# hide the building behind them; one click shows them.
HIDDEN_CLASSES = {"IfcSpace"}
# Property values that are lengths, areas or volumes, by their measure (or quantity) type, with
# the unit type they are in; the user text gives them in m, m² and m³ like the geometry.
UNIT_DIMENSIONS = {"LENGTHUNIT": 1, "AREAUNIT": 2, "VOLUMEUNIT": 3}
MEASURE_UNITS = {
    "IfcLengthMeasure": "LENGTHUNIT",
    "IfcPositiveLengthMeasure": "LENGTHUNIT",
    "IfcNonNegativeLengthMeasure": "LENGTHUNIT",
    "IfcAreaMeasure": "AREAUNIT",
    "IfcVolumeMeasure": "VOLUMEUNIT",
}
QUANTITY_UNITS = {"IfcQuantityLength": "LENGTHUNIT", "IfcQuantityArea": "AREAUNIT", "IfcQuantityVolume": "VOLUMEUNIT"}
# Share of the progress range used by the geometry iterator; the rest covers writing the file.
ITERATOR_SHARE = 90
# Elements with more triangles than this are mostly tessellated organic shapes (sanitary objects,
# lamps, plants). As polysurfaces they would cost ~1.7 kB per face without any benefit: they stay meshes.
MAX_BREP_FACES = 1000
# Mesh faces meeting at less than this angle shade as one smooth surface, steeper edges stay sharp.
# The geometry kernel tessellates curved surfaces in steps of up to 0.5 rad (29 degrees), so pipes
# and round columns come out smooth, while octagons and chamfers (45 degrees) keep their edges.
CREASE_ANGLE = 40.0
_CREASE_COS = math.cos(math.radians(CREASE_ANGLE))
# Smaller meshes are not welded: a smooth closed surface needs at least 9 sides within the crease
# angle (9 quads and two capping 9-gons are 32 triangles), and the per-mesh cost of welding
# outweighs the few vertices it saves on boxes and the like.
MIN_WELD_TRIANGLES = 32
# Vertices this close (metres) count as one position when welding. The kernel computes a point
# shared by two faces once per face, and the copies can differ in the last bits (below 1e-12 m).
WELD_TOLERANCE = 1e-9
# The mesh export builds each distinct geometry once and copies it to every place it is used
# (IFC models place the same type geometry many times: 8x on average in a plumbing model). The
# meshes kept for that are limited by their total vertex count, ~70 bytes each (~70 MB).
MESH_CACHE_VERTICES = 1_000_000

# The geometry kernel runs on many threads, but turning its triangles into polysurfaces and meshes
# is Python, which runs on one: on a many-core PC that would be most of the conversion time. With
# enough elements to pay for starting them (~1 s, in parallel with the kernel), worker processes
# build them. This process decodes their results and adds them to the file with layers and user
# text, which only it can read: the workers never load the model.
# (Workers could also build the attributes and return whole objects in an encoded File3dm, which
# would save this process the slow SetUserString calls, but rhino3dm never frees a decoded File3dm
# once one of its objects has been accessed.)
MIN_PARALLEL_ELEMENTS = 500
# One worker per this many threads, at most MAX_WORKERS. More would not help: the work left to this
# process (decoding, user text, writing the file) is what limits the speed.
THREADS_PER_WORKER = 2
MAX_WORKERS = 8
# RAM per worker: Python with numpy and rhino3dm (~170 MB) and the element it is building; welding
# the largest Holter Tower element took a worker to 1 GB (the same as it takes this process when
# building it itself). Workers are only started for the memory left after WORKER_MEMORY_RESERVE,
# which stays for the kernel and the output file.
WORKER_MEMORY = 1024 ** 3
WORKER_MEMORY_RESERVE = 2 * 1024 ** 3
# Elements go to the workers in batches of up to this many triangles or elements, which keeps the
# overhead per batch (~0.2 ms) small. Batches sent but not finished are limited to PENDING_TRIANGLES
# (~100 bytes each, ~200 MB) and PENDING_BATCHES.
BATCH_TRIANGLES = 20_000
BATCH_ELEMENTS = 64
PENDING_TRIANGLES = 2_000_000
PENDING_BATCHES = 64

Color = tuple[int, int, int, int]

# Opening volumes would show up as solid boxes over every window and door. Spaces stay: they get
# their own layers in Rhino, where they are easy to switch off.
# The layout parts of an alignment repeat its 3D axis: horizontal ones as a plan at height 0,
# vertical ones as a profile in distance/height coordinates that would lie somewhere off the model.
EXCLUDED_CLASSES = [
    "IfcOpeningElement",
    "IfcAlignmentHorizontal", "IfcAlignmentVertical", "IfcAlignmentCant", "IfcAlignmentSegment",
]
# Elements drawn as lines. The geometry kernel only yields the 3D axis of alignments with a vertical
# layout (a gradient curve); plan-only alignments and grids are computed in a second pass that
# includes curves. Curves are not enabled for everything: elements with a body and an axis would
# get both, and plan annotation would clutter the model.
CURVE_CLASSES = ["IfcAlignment", "IfcGrid"]


def write_3dm(
    model: ifcopenshell.file,
    output_path: Path,
    threads: int,
    progress: ProgressCallback | None = None,
    geometry: str = "brep",
    status: StatusCallback | None = None,
) -> int:
    """Write every element with geometry, layered by its place in the spatial structure and IFC class.

    With ``geometry="brep"`` elements become joined planar polysurfaces; elements with more than
    MAX_BREP_FACES triangles (tessellated organic shapes) or without a valid Brep stay meshes.
    With ``geometry="mesh"`` every element is a mesh. Elements that only have edges (alignment
    axes, grids) become polylines.
    """
    writer = _Writer(model)
    curve_elements = {element.id(): element for element in _curve_elements(model)}
    yielded: set[int] = set()
    settings = _settings()
    products = shape_products(model, EXCLUDED_CLASSES)
    with _Builder(_worker_count(threads, len(products)), _SolidItems(model)) as builder:
        # Meshes are computed in their own coordinates, so shapes that share a geometry share its
        # mesh. Polysurfaces are built from world coordinates.
        meshes = _MeshCache(builder) if geometry == "mesh" else None
        if meshes is not None:
            settings.set("use-world-coords", False)
        ordered = _Ordered(writer)
        shapes = iter_shapes(
            model, settings, threads, EXCLUDED_CLASSES, progress, ITERATOR_SHARE, products, chunk_ends=True,
            status=status,
        )
        # The second pass is generated lazily, after the first has recorded what it yielded.
        missing = (element for id_, element in curve_elements.items() if id_ not in yielded)
        for shape in itertools.chain(shapes, _curve_shapes(model, missing)):
            if isinstance(shape, ChunkEnd):
                builder.flush()
                ordered.close(shape.ids)
                continue
            if shape.id in curve_elements:
                yielded.add(shape.id)
            shape_geometry = shape.geometry
            if not shape_geometry.verts_buffer:
                continue
            triangles = len(shape_geometry.faces_buffer) // 12
            if not triangles:
                built = _Ready(_polylines(shape_geometry, _placement(shape)))
            elif meshes is not None:
                built = meshes.place(shape)
            else:
                built = builder.build(shape_geometry, geometry == "brep" and triangles <= MAX_BREP_FACES)
            ordered.add(shape.id, _material(shape_geometry), built)
            ordered.commit()
        builder.flush()
        ordered.close(None)
        ordered.commit(wait=True)

    if status:
        # rhino3dm holds the GIL while it writes, so the progress of this phase (the file growing)
        # can only be watched from another process; process.py does that.
        status("write", f"Rhino-Datei wird geschrieben ({writer.elements} Objekte) …")
    if not writer.rhino.Write(str(output_path), FILE_VERSION):
        raise OSError(f"Could not write Rhino file: {output_path}")
    return writer.elements


class _Writer:
    """Adds objects to a Rhino file with the layers, colours, materials and user text of their element."""

    def __init__(self, model: ifcopenshell.file):
        self.model = model
        self.rhino = rhino3dm.File3dm()
        self.rhino.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters
        # 1 mm, as Rhino's "Large Objects - Meters" template: what joins and Booleans in Rhino work
        # with. The geometry is far more precise (polysurface faces: MAX_PLANE_DEVIATION, 1 mm at most).
        self.rhino.Settings.ModelAbsoluteTolerance = 0.001
        self.rhino.Settings.ModelAngleToleranceDegrees = 1.0
        self.paths = _SpatialPaths(model)
        self.layers = _LayerTable(self.rhino)
        # Spatial layers are created up front so the layer panel lists them in the order of the
        # spatial structure, storeys by elevation, ahead of the fallback layers.
        for path in sorted(self.paths.levels(model), key=_levels_sort_key):
            self.layers.spatial(path)
        self.materials: dict[tuple[str, Color, float], int] = {}
        self.property_sets = _PropertySets(model)
        self.elements = 0

    def add(
        self, element_id: int, material: tuple[str, Color, float],
        geometry: rhino3dm.Mesh | rhino3dm.Brep | list[rhino3dm.Polyline] | None,
    ) -> None:
        if geometry is None:
            return
        element = self.model.by_id(element_id)
        name, color, transparency = material
        attributes = _attributes(element, color, self.property_sets)
        curves = isinstance(geometry, list)
        attributes.LayerIndex = self.layers.get(
            self.paths.of_element(element), element.is_a(), color, AXES if curves else NO_STOREY
        )
        attributes.MaterialIndex = _material_index(self.rhino, self.materials, (name, color, transparency))
        attributes.MaterialSource = rhino3dm.ObjectMaterialSource.MaterialFromObject
        if isinstance(geometry, rhino3dm.Brep):
            self.rhino.Objects.AddBrep(geometry, attributes)
        elif not curves:
            self.rhino.Objects.AddMesh(geometry, attributes)
        else:
            if len(geometry) > 1:
                # The pieces of one element select together.
                group = rhino3dm.Group()
                group.Name = attributes.Name
                self.rhino.Groups.Add(group)
                attributes.AddToGroup(len(self.rhino.Groups) - 1)
            for polyline in geometry:
                self.rhino.Objects.AddPolyline(polyline, attributes)
        self.elements += 1


def _curve_elements(model: ifcopenshell.file) -> list[ifcopenshell.entity_instance]:
    elements = []
    for ifc_class in CURVE_CLASSES:
        try:
            elements += model.by_type(ifc_class)
        except RuntimeError:  # not in this schema (IfcAlignment before IFC4X3)
            pass
    return [element for element in elements if element.Representation]


def _curve_shapes(model: ifcopenshell.file, elements) -> Iterator:
    """One curve shape per element, preferring its 3D "Axis" over a plan "FootPrint"."""
    elements = list(elements)
    if not elements:
        return
    settings = _settings()
    settings.set("dimensionality", wrapper.CURVES)
    iterator = geom.iterator(settings, model, 1, include=elements, geometry_library=geometry_library())
    shapes: dict[int, object] = {}
    if iterator.initialize():
        while True:
            shape = iterator.get()
            if shape.id not in shapes or shape.context == "Axis":
                shapes[shape.id] = shape
            if not iterator.next():
                break
    # Yielding from here keeps the iterator, which owns the shapes' data, alive until they are written.
    yield from shapes.values()


def _settings() -> geom.settings:
    settings = geom.settings()
    settings.set("mesher-linear-deflection", LINEAR_DEFLECTION)
    settings.set("use-world-coords", True)
    # Unwelded vertices keep hard edges between faces sharp when Rhino shades the mesh.
    settings.set("weld-vertices", False)
    settings.set("use-material-names", True)
    settings.set("no-normals", True)
    return settings


def _polylines(geometry, placement: numpy.ndarray | None = None) -> list[rhino3dm.Polyline] | None:
    """The edges of a wire-only shape chained into polylines (in double precision), or None."""
    verts = numpy.frombuffer(geometry.verts_buffer, dtype=numpy.float64).reshape(-1, 3)
    if placement is not None:
        verts = verts @ placement[:3, :3].T + placement[:3, 3]
    verts, edges = verts.ravel().tolist(), geometry.edges
    polylines: list[rhino3dm.Polyline] = []
    points: list[tuple[float, float, float]] = []
    indices = iter(edges)
    for a, b in zip(indices, indices):
        start = (verts[3 * a], verts[3 * a + 1], verts[3 * a + 2])
        end = (verts[3 * b], verts[3 * b + 1], verts[3 * b + 2])
        # The kernel emits the segments of a curve in order, each with its own copy of the shared
        # point, so a segment continues the polyline when it starts where the last one ended.
        if points and points[-1] == start:
            points.append(end)
        elif points and points[-1] == end:
            points.append(start)
        else:
            polylines.append(_polyline(points))
            points = [start, end]
    polylines.append(_polyline(points))
    polylines = [polyline for polyline in polylines if polyline is not None]
    return polylines or None


def _polyline(points: list[tuple[float, float, float]]) -> rhino3dm.Polyline | None:
    polyline = rhino3dm.Polyline()
    for point in points:
        polyline.Add(*point)
    return polyline if polyline.Length > 0 else None


def _attributes(
    element: ifcopenshell.entity_instance, color: Color, property_sets: _PropertySets | None = None
) -> rhino3dm.ObjectAttributes:
    attributes = rhino3dm.ObjectAttributes()
    attributes.Name = element.Name or element.GlobalId
    attributes.ObjectColor = color
    attributes.ColorSource = rhino3dm.ObjectColorSource.ColorFromObject
    for key, value in _user_strings(element, property_sets).items():
        attributes.SetUserString(key, value)
    return attributes


class _Ordered:
    """Adds the elements to the Rhino file in model order, chunk by chunk.

    The kernel's threads deliver the shapes of a chunk in the order they finish, which differs from
    run to run, and the workers finish them in yet another order. Adding them in the order of the
    model's products makes the file (objects, layers, materials) the same for any number of threads.
    """

    def __init__(self, writer: _Writer):
        self._writer = writer
        self._open: list[tuple[int, tuple, _Ready | _Deferred | _Placed]] = []
        self._closed: deque[tuple[int, tuple, _Ready | _Deferred | _Placed]] = deque()

    def add(self, element_id: int, material: tuple, built) -> None:
        self._open.append((element_id, material, built))

    def close(self, ids: list[int] | None) -> None:
        """End the chunk of products ``ids`` (in model order; None: keep the order of arrival)."""
        if ids is not None:
            position = {id_: i for i, id_ in enumerate(ids)}
            self._open.sort(key=lambda entry: position.get(entry[0], len(ids)))
        self._closed.extend(self._open)
        self._open = []

    def commit(self, wait: bool = False) -> None:
        """Add the elements of closed chunks that are ready (``wait``: all of them) to the file.

        A closed chunk is committed after the first shape of the next one has arrived, so the
        kernel's threads already work on that chunk meanwhile.
        """
        while self._closed and (wait or self._closed[0][2].ready()):
            element_id, material, built = self._closed.popleft()
            # Each object goes into the Rhino file right away, so only one copy of the geometry is kept.
            self._writer.add(element_id, material, built.get())


class _Ready:
    """Geometry built in this process."""

    def __init__(self, geometry):
        self._geometry = geometry

    def ready(self) -> bool:
        return True

    def get(self):
        return self._geometry


class _Batch:
    """Elements sent to a worker process together."""

    def __init__(self):
        self.jobs: list[tuple] | None = []
        self.triangles = 0
        self.future: concurrent.futures.Future | None = None
        # Per job the encoded polysurface or mesh, or None (see _build_batch).
        self.results: list | None = None

    def set_results(self, results: list) -> None:
        self.results = results
        self.jobs = self.future = None  # the future would keep the results


class _Deferred:
    """Geometry built by a worker process, decoded in this one when it is needed."""

    def __init__(self, builder: _Builder, batch: _Batch, index: int):
        self._builder, self._batch, self._index = builder, batch, index
        self._done = False
        self._geometry = None

    def ready(self) -> bool:
        batch = self._batch
        return self._done or batch.results is not None or (batch.future is not None and batch.future.done())

    def get(self):
        if not self._done:
            built = self._builder.result(self._batch)[self._index]
            if built is not None:
                kind, data = built
                built = (rhino3dm.Brep if kind == "brep" else rhino3dm.Mesh).Decode(data)
            self._geometry, self._done = built, True
            self._builder = self._batch = None
        return self._geometry


class _Builder:
    """Builds the polysurfaces and meshes of shapes, in ``workers`` worker processes or (0) right away."""

    def __init__(self, workers: int, solids: _SolidItems | None = None):
        self._workers = workers
        self._solids = solids
        self._pool: concurrent.futures.ProcessPoolExecutor | None = None
        self._batch = _Batch()
        # Batches sent to the workers: their futures and triangles.
        self._pending: deque[tuple[concurrent.futures.Future, int]] = deque()
        self._pending_triangles = 0

    def __enter__(self) -> _Builder:
        return self

    def __exit__(self, *exc_info) -> None:
        if self._pool is not None:
            # On an error or a cancel nothing more is needed from the workers.
            self._pool.shutdown(wait=exc_info[0] is None, cancel_futures=True)
            self._pool = None

    def build(self, geometry, brep: bool) -> _Ready | _Deferred:
        """The polysurface of ``geometry`` (if ``brep``) or else its mesh, or None."""
        faces, solid_ids = geometry.faces_buffer, b""
        if self._solids is not None:
            faces, solid_ids = _outward(geometry, self._solids)
        job = (brep, geometry.verts_buffer, faces, geometry.item_ids_buffer if brep else b"", solid_ids if brep else b"")
        if not self._workers:
            return _Ready(_build_from_buffers(*job))
        batch = self._batch
        batch.jobs.append(job)
        batch.triangles += len(geometry.faces_buffer) // 12
        built = _Deferred(self, batch, len(batch.jobs) - 1)
        if batch.triangles >= BATCH_TRIANGLES or len(batch.jobs) >= BATCH_ELEMENTS:
            self.flush()
        return built

    def flush(self) -> None:
        """Send the elements collected so far to the workers."""
        batch = self._batch
        if not batch.jobs:
            return
        self._batch = _Batch()
        if not self._workers:  # the workers broke down
            batch.set_results(_build_batch(batch.jobs))
            return
        # Keep what is in flight within bounds: wait for the oldest batches.
        while self._pending and (
            self._pending[0][0].done()
            or self._pending_triangles > PENDING_TRIANGLES or len(self._pending) >= PENDING_BATCHES
        ):
            future, triangles = self._pending.popleft()
            self._pending_triangles -= triangles
            concurrent.futures.wait([future])
        try:
            if self._pool is None:
                self._pool = concurrent.futures.ProcessPoolExecutor(
                    self._workers, multiprocessing.get_context("spawn"), _worker_init, (os.getpid(),)
                )
            batch.future = self._pool.submit(_build_batch, batch.jobs)
        except Exception as exc:  # a broken pool, or workers that cannot be started at all
            self._broken(exc)
            batch.set_results(_build_batch(batch.jobs))
            return
        # The input is only kept to build it here should a worker fail.
        batch.future.add_done_callback(functools.partial(_release_jobs, weakref.ref(batch)))
        self._pending.append((batch.future, batch.triangles))
        self._pending_triangles += batch.triangles

    def result(self, batch: _Batch) -> list:
        """The results of ``batch``, built here if the workers failed."""
        if batch.results is None:
            if batch.future is None:
                self.flush()
            if batch.results is None:
                try:
                    batch.set_results(batch.future.result())
                except concurrent.futures.BrokenExecutor:
                    # A worker died (out of memory, a crash in native code): build the rest here.
                    self._broken()
                    batch.set_results(_build_batch(batch.jobs))
        return batch.results

    def _broken(self, error: BaseException | None = None) -> None:
        if self._workers:
            log.warning(
                "Worker processes failed (%s), building the remaining geometry in the main process",
                f"{type(error).__name__}: {error}" if error else "a worker ended",
            )
        self._workers = 0


def _release_jobs(batch: weakref.ref, future: concurrent.futures.Future) -> None:
    batch = batch()
    if batch is not None and not future.cancelled() and future.exception() is None:
        batch.jobs = None


def _worker_count(threads: int, elements: int) -> int:
    """The number of worker processes for a model with ``elements`` elements (0: build in this process)."""
    if elements < MIN_PARALLEL_ELEMENTS:
        return 0
    count = min(MAX_WORKERS, threads // THREADS_PER_WORKER)
    available = available_memory()
    if available is not None:
        count = min(count, (available - WORKER_MEMORY_RESERVE) // WORKER_MEMORY)
    return max(0, count)


def _worker_init(parent_pid: int) -> None:
    no_crash_dialogs()
    # A worker blocks reading its next batch, also when the conversion was cancelled by killing its
    # process: without this it would wait forever (Windows) or until killed with it (Linux only).
    threading.Thread(target=exit_with_parent, args=(parent_pid,), daemon=True).start()


def _build_batch(jobs: list[tuple]) -> list[tuple[str, dict] | None]:
    """Run in a worker: the encoded polysurfaces or meshes of a batch of elements (see _build).

    Each job is (brep, verts, faces, item ids, solid item ids); each result ("brep" or "mesh", the
    geometry's Encode()) or None. Decoding gives the very same geometry.
    """
    results = []
    for job in jobs:
        geometry = _build_from_buffers(*job)
        kind = "brep" if isinstance(geometry, rhino3dm.Brep) else "mesh"
        results.append(None if geometry is None else (kind, geometry.Encode()))
    return results


def _build_from_buffers(
    brep: bool, verts: bytes, faces: bytes, item_ids: bytes, solid_ids: bytes = b""
) -> rhino3dm.Brep | rhino3dm.Mesh | None:
    # The element as a joined polysurface (coplanar triangles become one face with holes), else a mesh.
    if brep:
        indices = tuple(numpy.frombuffer(faces, dtype=numpy.int32).tolist())
        polysurface = planar_polysurface(
            tuple(numpy.frombuffer(verts, dtype=numpy.float64).tolist()),
            [[indices[i:i + 3]] for i in range(0, len(indices), 3)],
            tuple(numpy.frombuffer(item_ids, dtype=numpy.int32).tolist()),
            set(numpy.frombuffer(solid_ids, dtype=numpy.int32).tolist()),
        )
        if polysurface is not None:
            return polysurface
    return _mesh_from_buffers(verts, faces)


class _Placed:
    """A shared mesh, moved to where one of its shapes is."""

    def __init__(self, mesh: _Ready | _Deferred, placement: numpy.ndarray | None):
        self._mesh, self._placement = mesh, placement

    def ready(self) -> bool:
        return self._mesh.ready()

    def get(self) -> rhino3dm.Mesh | None:
        mesh = self._mesh.get()
        if mesh is None:
            return None
        mesh = mesh.Duplicate()
        if self._placement is not None:
            # Like the kernel's world coordinates: points and normals move, the triangles keep
            # their order.
            mesh.Transform(_transform(self._placement))
        return mesh


class _MeshCache:
    """Meshes of the distinct geometries, in their own coordinates, the least recently used dropped first."""

    def __init__(self, builder: _Builder):
        self._builder = builder
        # Per geometry its mesh and the number of input vertices.
        self._meshes: OrderedDict[str, tuple[_Ready | _Deferred, int]] = OrderedDict()
        self._vertices = 0

    def place(self, shape) -> _Placed:
        """The mesh of a shape, moved to where the shape is."""
        key = shape.geometry.id
        if key in self._meshes:
            self._meshes.move_to_end(key)
            mesh = self._meshes[key][0]
        else:
            # Counted before welding: the meshes being built in the workers are not known yet.
            vertices = len(shape.geometry.verts_buffer) // 24
            mesh = self._builder.build(shape.geometry, False)
            self._meshes[key] = mesh, vertices
            self._vertices += vertices
            while self._vertices > MESH_CACHE_VERTICES and len(self._meshes) > 1:
                self._vertices -= self._meshes.popitem(last=False)[1][1]
        return _Placed(mesh, _placement(shape))


def _placement(shape) -> numpy.ndarray | None:
    """The 4x4 matrix placing a shape's geometry, or None where it is already in place."""
    matrix = numpy.frombuffer(shape.transformation_buffer, dtype=numpy.float64).reshape(4, 4, order="F")
    return None if numpy.array_equal(matrix, _IDENTITY) else matrix


_IDENTITY = numpy.eye(4)


def _transform(matrix: numpy.ndarray) -> rhino3dm.Transform:
    transform = rhino3dm.Transform(1.0)
    for (row, column), value in numpy.ndenumerate(matrix):
        setattr(transform, f"M{row}{column}", float(value))
    return transform


class _SolidItems:
    """Which representation items are solids, whose triangles must enclose their volume.

    Surface models (Revit writes furniture and ceilings as IfcFaceBasedSurfaceModel) have no
    inside, so their orientation is only a guess.
    """

    def __init__(self, model: ifcopenshell.file):
        self._model = model
        self._solid: dict[int, bool] = {}

    def among(self, item_ids) -> set[int]:
        solid = self._solid
        for item in set(item_ids) - solid.keys():
            try:
                entity = self._model.by_id(item)
            except RuntimeError:
                solid[item] = False
                continue
            solid[item] = bool(
                entity.is_a("IfcSolidModel") or entity.is_a("IfcBooleanResult") or entity.is_a("IfcCsgPrimitive3D")
                or (entity.is_a("IfcTessellatedFaceSet") and getattr(entity, "Closed", None) is True)
            )
        return {item for item in set(item_ids) if solid[item]}


def _outward(geometry, solids: _SolidItems) -> tuple[bytes, bytes]:
    """The faces buffer with each representation item that encloses a negative volume turned
    around, and the ids of the solid items (int32 buffers).

    IfcOpenShell applies a mirroring type placement (mirrored doors, windows and furniture) to the
    vertices without reversing the triangles, and Revit writes many closed surface models (ceilings,
    furniture) with their faces pointing inwards: such meshes shade dark and have a negative volume
    in Rhino. Solids are turned as a whole, so the void of a hollow solid keeps pointing inwards;
    surface models only when they are closed (polysurfaces turn each closed shell outwards, too).
    """
    faces = geometry.faces_buffer
    items = numpy.frombuffer(geometry.item_ids_buffer, dtype=numpy.int32)
    triangles = numpy.frombuffer(faces, dtype=numpy.int32).reshape(-1, 3)
    if not len(triangles) or len(items) != len(triangles):
        return faces, b""
    ids, item = numpy.unique(items, return_inverse=True)
    solid = numpy.isin(ids, list(solids.among(ids.tolist())))
    solid_ids = ids[solid].astype(numpy.int32).tobytes()
    points = numpy.frombuffer(geometry.verts_buffer, dtype=numpy.float64).reshape(-1, 3)
    local = points - points.min(axis=0)  # far from the origin the products would cancel out
    a, b, c = local[triangles[:, 0]], local[triangles[:, 1]], local[triangles[:, 2]]
    inside_out = numpy.bincount(item, numpy.einsum("ij,ij->i", a, numpy.cross(b, c)), len(ids)) < 0
    if not inside_out.any():
        return faces, solid_ids
    surface = inside_out & ~solid
    if surface.any():
        # Closed: every edge (vertices matched by position) is used as often in each direction.
        position = _group(numpy.rint(points * (1.0 / WELD_TOLERANCE)).astype(numpy.int64))[triangles]
        edges = numpy.concatenate([position[:, [0, 1]], position[:, [1, 2]], position[:, [2, 0]]])
        edge_items = numpy.tile(item, 3)
        keep = (edges[:, 0] != edges[:, 1]) & surface[edge_items]
        edges, edge_items = edges[keep], edge_items[keep]
        if len(edges):
            key = _group(numpy.column_stack((edge_items, edges.min(axis=1), edges.max(axis=1))))
            balance = numpy.bincount(key, numpy.where(edges[:, 0] < edges[:, 1], 1, -1))
            surface[edge_items[balance[key] != 0]] = False
    flip = ((inside_out & solid) | surface)[item]
    if not flip.any():
        return faces, solid_ids
    triangles = triangles.copy()
    triangles[flip] = triangles[flip][:, ::-1]
    return triangles.tobytes(), solid_ids


def _mesh(geometry) -> rhino3dm.Mesh | None:
    """The shape as a mesh, welded across smooth edges."""
    return _mesh_from_buffers(geometry.verts_buffer, geometry.faces_buffer)


def _mesh_from_buffers(verts: bytes, faces: bytes) -> rhino3dm.Mesh | None:
    if not verts or not faces:
        return None
    points = numpy.frombuffer(verts, dtype=numpy.float64).reshape(-1, 3)
    triangles = numpy.frombuffer(faces, dtype=numpy.int32).reshape(-1, 3)
    normals = None
    if len(triangles) >= MIN_WELD_TRIANGLES:
        points, triangles, normals = _weld(points, triangles)

    mesh = rhino3dm.Mesh()
    # Vertices are added in double precision: single-precision floats lose whole decimetres far
    # from the origin (georeferenced bridges, sites in UTM), and opennurbs writes double-precision
    # meshes 2-3x faster (Clinic_Plumbing: 14 s instead of 47 s) for ~14% more file size.
    # rhino3dm has no bulk API: map() over plain lists keeps the per-call overhead in C.
    deque(map(mesh.Vertices.AddPoint3d, *points.T.tolist()), maxlen=0)
    deque(map(mesh.Faces.AddFace, *triangles.T.tolist()), maxlen=0)
    if normals is None:
        # Unwelded, or only flat faces: every vertex normal is its faces' normal, which Rhino
        # computes faster.
        mesh.Normals.ComputeNormals()
    else:
        # Rhino's ComputeNormals averages the triangles at a vertex unweighted, which tilts the
        # normals where a curved surface has more triangles on one side of a vertex than the other.
        deque(map(mesh.Normals.Add, *normals.T.tolist()), maxlen=0)
    mesh.Compact()
    return mesh


def _weld(points: numpy.ndarray, triangles: numpy.ndarray) -> tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray | None]:
    """Merge the vertices at the same position that belong to one smooth surface.

    The kernel shares vertices only within a face of the solid (or not at all for triangulated
    IFC geometry), so every edge between two faces is sharp. Each vertex gets a normal (the mean
    of its triangles' normals). At each position, a vertex is given the sum of the normals within
    CREASE_ANGLE of its own, and vertices with the same sum are merged: they see the same smooth
    neighbourhood, so two vertices on either side of a crease never merge, even through a third
    vertex in between. Returns the merged vertex positions, the triangles indexing them and the
    vertex normals: the face normals around each vertex weighted by the triangles' corner angles,
    or None where every vertex lies in one plane with all its triangles.
    """
    # Vertex normals: the sum of the unit normals of the vertex's triangles, normalised.
    a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    u, v = b - a, c - a
    normals = numpy.empty_like(u)
    normals[:, 0] = u[:, 1] * v[:, 2] - u[:, 2] * v[:, 1]
    normals[:, 1] = u[:, 2] * v[:, 0] - u[:, 0] * v[:, 2]
    normals[:, 2] = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
    normals /= numpy.maximum(numpy.sqrt((normals * normals).sum(axis=1)), 1e-300)[:, None]
    corners = triangles.ravel()
    vertex_normals = numpy.empty((len(points), 3))
    for axis in range(3):
        vertex_normals[:, axis] = numpy.bincount(corners, numpy.repeat(normals[:, axis], 3), len(points))
    vertex_normals /= numpy.maximum(numpy.sqrt((vertex_normals * vertex_normals).sum(axis=1)), 1e-300)[:, None]

    # Positions, snapped to WELD_TOLERANCE, and nodes: the vertices of one position with the same
    # normal (a flat fan of triangles around a point), which merge in any case.
    position = _group(numpy.rint(points * (1.0 / WELD_TOLERANCE)).astype(numpy.int64))
    normal_key = numpy.rint(vertex_normals * 1e9).astype(numpy.int64)
    by_node = numpy.lexsort((normal_key[:, 2], normal_key[:, 1], normal_key[:, 0], position))
    node_start = numpy.empty(len(points), dtype=bool)
    node_start[0] = True
    node_start[1:] = (position[by_node[1:]] != position[by_node[:-1]]) | numpy.any(
        normal_key[by_node[1:]] != normal_key[by_node[:-1]], axis=1
    )
    node = numpy.empty(len(points), dtype=numpy.intp)
    node[by_node] = numpy.cumsum(node_start) - 1
    first_vertex = by_node[node_start]  # nodes in order of position
    node_normals = vertex_normals[first_vertex]
    node_position = position[first_vertex]
    count = len(first_vertex)

    # For every node i, the sum of the normals of the nodes j at its position within the angle of
    # its own. Pairs are listed node by node, so the sums are one segmented reduction.
    starts = numpy.empty(count, dtype=bool)
    starts[0] = True
    numpy.not_equal(node_position[1:], node_position[:-1], out=starts[1:])
    group = numpy.cumsum(starts) - 1
    sizes = numpy.bincount(group)[group]
    pair_first = numpy.cumsum(sizes) - sizes
    i = numpy.repeat(numpy.arange(count), sizes)
    j = numpy.repeat(numpy.flatnonzero(starts)[group], sizes) + numpy.arange(len(i)) - numpy.repeat(pair_first, sizes)
    neighbours = node_normals[j]
    within = (node_normals[i] * neighbours).sum(axis=1) >= _CREASE_COS
    summed = numpy.add.reduceat(neighbours * within[:, None], pair_first)

    # One vertex per position and neighbourhood; rounding absorbs summation noise. A node of
    # degenerate triangles only (zero normal) is within no angle and stays on its own.
    key = numpy.rint(summed * 1e6).astype(numpy.int64)
    key[:, 0] = numpy.where(summed.any(axis=1), key[:, 0], -1 - numpy.arange(count))
    node_vertex = _group(numpy.column_stack((group, key)))
    vertex = node_vertex[node]
    welded = vertex[triangles]
    vertices = int(node_vertex.max()) + 1
    first = numpy.empty(vertices, dtype=numpy.intp)
    first[vertex[::-1]] = numpy.arange(len(points))[::-1]  # the first input vertex of each

    # Shading normals weighted by corner angle, so how a surface happens to be split into
    # triangles does not tilt them.
    edges = [e / numpy.maximum(numpy.sqrt((e * e).sum(axis=1)), 1e-300)[:, None] for e in (b - a, c - b, a - c)]
    angles = numpy.arccos(numpy.clip(numpy.column_stack([
        -(edges[2] * edges[0]).sum(axis=1), -(edges[0] * edges[1]).sum(axis=1), -(edges[1] * edges[2]).sum(axis=1),
    ]), -1.0, 1.0)).ravel()
    shading = numpy.empty((vertices, 3))
    for axis in range(3):
        shading[:, axis] = numpy.bincount(welded.ravel(), numpy.repeat(normals[:, axis], 3) * angles, vertices)
    lengths = numpy.sqrt((shading * shading).sum(axis=1))
    # A vertex of degenerate triangles only gets any unit normal; its triangles cover no area.
    shading[lengths == 0] = (0.0, 0.0, 1.0)
    shading /= numpy.where(lengths > 0, lengths, 1.0)[:, None]
    proper = numpy.repeat(normals.any(axis=1), 3)  # corners of non-degenerate triangles
    flat = ((shading[welded.ravel()] * numpy.repeat(normals, 3, axis=0)).sum(axis=1)[proper] > 1 - 1e-9).all()
    return points[first], welded, None if flat else shading


def _group(rows: numpy.ndarray) -> numpy.ndarray:
    """Number equal rows of int64 columns alike (0, 1, ...).

    Sorting a hash of the rows brings equal rows together far faster than sorting the rows. Rows
    are compared themselves, so a hash collision can only give one row value two numbers.
    """
    order = numpy.argsort(_hash(rows), kind="stable")
    ordered = rows[order]
    new = numpy.empty(len(rows), dtype=bool)
    new[0] = True
    numpy.any(ordered[1:] != ordered[:-1], axis=1, out=new[1:])
    group = numpy.empty(len(rows), dtype=numpy.intp)
    group[order] = numpy.cumsum(new) - 1
    return group


def _hash(columns: numpy.ndarray) -> numpy.ndarray:
    """A 64-bit hash per row of int64 columns (overflow wraps around)."""
    result = numpy.zeros(len(columns), dtype=numpy.int64)
    for column in columns.T:
        result = result * -7046029254386353131 ^ column
    return result


def _material(geometry) -> tuple[str, Color, float]:
    """Name, colour and transparency (0-1) of the material covering most faces."""
    if not geometry.materials:
        return "Default", (180, 180, 180, 255), 0.0
    ids = numpy.frombuffer(geometry.material_ids_buffer, dtype=numpy.int32)
    ids = ids[ids >= 0]
    index = 0
    if len(ids):
        # The most frequent material; on a tie the one that comes first.
        values, first, counts = numpy.unique(ids, return_index=True, return_counts=True)
        index = int(values[numpy.lexsort((first, -counts))[0]])
    material = geometry.materials[index]

    diffuse = material.diffuse
    transparency = material.transparency
    if transparency is None or math.isnan(transparency):
        transparency = 0.0
    transparency = min(max(transparency, 0.0), 1.0)
    color = (
        _channel(diffuse.r()),
        _channel(diffuse.g()),
        _channel(diffuse.b()),
        _channel(1.0 - transparency),
    )
    return material.name or "Default", color, transparency


def _channel(value: float) -> int:
    return round(min(max(value, 0.0), 1.0) * 255)


def _material_index(rhino: rhino3dm.File3dm, cache: dict, key: tuple[str, Color, float]) -> int:
    if key not in cache:
        name, color, transparency = key
        material = rhino3dm.Material()
        material.Name = _clean_name(name, "Material")
        material.DiffuseColor = color[:3] + (255,)
        material.Transparency = transparency
        cache[key] = rhino.Materials.Add(material)
    return cache[key]


# A chain of spatial elements, outermost first, that becomes a chain of nested layers.
SpatialPath = tuple[ifcopenshell.entity_instance, ...]


class _SpatialPaths:
    """The layer path of each element: the spatial elements it sits in below the site.

    Buildings keep their classic layout ``<storey>::<IfcClass>``: the building itself is left out,
    and only the innermost storey counts (partial storeys do not nest). If the model has several
    buildings they become the top level, ``<building>::<storey>::<IfcClass>``. Infrastructure
    facilities (IfcBridge, IfcRoad, IfcRailway, IfcMarineFacility, ...) and their (nested) parts
    each add a level: ``<bridge>::<substructure>::<pier>::<IfcClass>``. Sites, spaces and zones add
    none. Elements outside any of these get an empty path.
    """

    def __init__(self, model: ifcopenshell.file):
        self._omit_building = len(model.by_type("IfcBuilding")) <= 1
        self._cache: dict[int, SpatialPath] = {}

    def levels(self, model: ifcopenshell.file) -> set[SpatialPath]:
        """The paths of all storeys and of the spatial elements that hold elements or geometry."""
        try:
            spatial = model.by_type("IfcSpatialElement")
        except RuntimeError:  # IFC2X3
            spatial = model.by_type("IfcSpatialStructureElement")
        paths = set()
        for element in spatial:
            if (
                element.is_a("IfcBuildingStorey") or element.Representation
                or any(rel.RelatedElements for rel in element.ContainsElements)
            ):
                paths.add(self.of_spatial(element))
        paths.discard(())
        return paths

    def of_element(self, element: ifcopenshell.entity_instance) -> SpatialPath:
        # A spatial element with geometry of its own (a road shoulder) is drawn in its own layer;
        # spaces add no level, so they stay in their storey.
        if _is_spatial(element):
            return self.of_spatial(element)
        # Elements reach their container through aggregates (assembly parts) and nests.
        parent = element_util.get_parent(element)
        while parent is not None and not _is_spatial(parent):
            parent = element_util.get_parent(parent)
        return self.of_spatial(parent) if parent is not None else ()

    def of_spatial(self, spatial: ifcopenshell.entity_instance) -> SpatialPath:
        key = spatial.id()
        path = self._cache.get(key)
        if path is None:
            parent = element_util.get_parent(spatial)
            path = self.of_spatial(parent) if parent is not None and _is_spatial(parent) else ()
            if spatial.is_a("IfcBuildingStorey"):
                path = tuple(level for level in path if not level.is_a("IfcBuildingStorey")) + (spatial,)
            elif spatial.is_a("IfcBuilding"):
                if not self._omit_building:
                    path += (spatial,)
            # IfcFacility and IfcFacilityPart exist from IFC4X3 on; is_a is False before.
            elif spatial.is_a("IfcFacility") or spatial.is_a("IfcFacilityPart"):
                path += (spatial,)
            self._cache[key] = path
        return path


def _is_spatial(entity: ifcopenshell.entity_instance) -> bool:
    # IfcSpatialElement is IFC4+, IFC2X3 only has IfcSpatialStructureElement.
    return entity.is_a("IfcSpatialElement") or entity.is_a("IfcSpatialStructureElement")


def _levels_sort_key(path: SpatialPath) -> tuple:
    """Depth first in file order, with sibling storeys by elevation."""
    return tuple(
        (level.Elevation or 0.0, level.Name or "", level.id()) if level.is_a("IfcBuildingStorey")
        else (0.0, "", level.id())
        for level in path
    )


def _level_name(level: ifcopenshell.entity_instance) -> str:
    if level.is_a("IfcBuildingStorey"):
        return _clean_name(level.Name, f"Geschoss #{level.id()}")
    # Unnamed facility parts are named after their kind (PIER, DECK, ...).
    kind = getattr(level, "PredefinedType", None)
    if kind == "USERDEFINED":
        kind = getattr(level, "ObjectType", None)
    elif kind == "NOTDEFINED":
        kind = None
    return _clean_name(level.Name, _clean_name(kind, level.is_a()))


def _user_strings(element: ifcopenshell.entity_instance, property_sets: _PropertySets | None = None) -> dict[str, str]:
    strings = {
        "IfcGlobalId": element.GlobalId,
        "IfcClass": element.is_a(),
        "IfcName": element.Name or "",
    }
    try:
        if property_sets is None:
            psets = element_util.get_psets(element, psets_only=True)
            quantities = element_util.get_psets(element, qtos_only=True)
        else:
            psets, quantities = property_sets.of(element, si=True)
    except Exception:
        psets, quantities = {}, {}
    # Standard quantities (areas, volumes, lengths) are kept. Vendor quantity dumps such as
    # ArchiCADQuantities are dropped: in ArchiCAD files they were ~85 % of all quantity values,
    # mostly repeating the standard ones, and made up much of the file size and conversion time.
    psets.update({name: values for name, values in quantities.items() if _standard_quantities(name)})
    for pset, properties in psets.items():
        for prop, value in properties.items():
            if prop == "id" or not isinstance(value, (str, int, float, bool)):
                continue
            # 12 significant digits drop float noise ("6403.99999999979" → "6404") and keep 0.01 mm
            # even in georeferenced coordinates.
            text = _float_text(value) if isinstance(value, float) else str(value)
            strings[f"{pset}.{prop}"] = text[:MAX_STRING_LENGTH]
    return strings


def _float_text(value: float) -> str:
    """A property value without float noise, still recognisable as a decimal ("15.0", "6.404")."""
    text = f"{value:.12g}"
    return text if any(c in text for c in ".enia") else text + ".0"


class _PropertySets:
    """The property sets and quantity sets of elements, as ``get_psets`` gives them, in one pass.

    ``get_psets`` walks an element's definitions once for its property sets and once more for its
    quantities, and repeats its type's sets for every element of the type. Here both come from one
    walk, each type's sets are read once, and so are definitions that several elements share, while
    they are still needed. The result is the same, down to the order of sets and properties.
    """

    def __init__(self, model: ifcopenshell.file):
        # Factor to SI (m, m², m³) of the project's length, area and volume unit.
        self._unit_scales = {kind: unit_util.calculate_unit_scale(model, kind) for kind in UNIT_DIMENSIONS}
        self._factors: dict[int, dict[str, float]] = {}
        self._types: dict[int, tuple[dict, dict, dict]] = {}
        # Elements left that use each shared definition.
        self._uses: dict[int, int] = {}
        self._shared: dict[int, dict] = {}
        for relationship in model.by_type("IfcRelDefinesByProperties"):
            for definition in _definitions(relationship):
                self._uses[definition.id()] = self._uses.get(definition.id(), 0) + len(relationship.RelatedObjects)

    def of(self, element: ifcopenshell.entity_instance, si: bool = False) -> tuple[dict, dict]:
        """``get_psets(element, psets_only=True)`` and ``get_psets(element, qtos_only=True)``.

        With ``si`` lengths, areas and volumes are converted from the file's units to m, m² and m³,
        the units of the Rhino file: a Revit wall's Qto Length of "6403.99999999979" (mm) is 6.404.
        """
        psets: dict[str, dict] = {}
        quantities: dict[str, dict] = {}
        factors: dict[str, dict[str, float]] = {}
        element_type = element_util.get_type(element)
        if element_type:
            type_psets, type_quantities, type_factors = self._type_sets(element_type)
            psets = {name: dict(values) for name, values in type_psets.items()}
            quantities = {name: dict(values) for name, values in type_quantities.items()}
            factors = {name: dict(values) for name, values in type_factors.items()}
        for relationship in element.IsDefinedBy or ():
            if relationship.is_a("IfcRelDefinesByProperties"):
                for definition in _definitions(relationship):
                    sets = _kind(definition, psets, quantities)
                    if sets is not None:
                        sets.setdefault(definition.Name, {}).update(self._properties(definition))
                        if si:
                            found = factors.setdefault(definition.Name, {})
                            found.update(self._factors_of(definition))
        if si:
            for name, scale in factors.items():
                for sets in (psets, quantities):
                    values = sets.get(name)
                    for prop, factor in scale.items() if values else ():
                        value = values.get(prop)
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            values[prop] = value * factor
        return psets, quantities

    def _factors_of(self, definition: ifcopenshell.entity_instance) -> dict[str, float]:
        """The factors to SI of the length, area and volume values in a property or quantity set."""
        key = definition.id()
        if key not in self._factors:
            factors = {}
            if definition.is_a("IfcPropertySet"):
                for prop in definition.HasProperties or ():
                    if prop.is_a("IfcPropertySingleValue") and prop.NominalValue is not None:
                        kind = MEASURE_UNITS.get(prop.NominalValue.is_a())
                        factor = self._scale(kind, prop.Unit) if kind else 1.0
                        if factor != 1.0:
                            factors[prop.Name] = factor
            elif definition.is_a("IfcElementQuantity"):
                for quantity in definition.Quantities or ():
                    kind = QUANTITY_UNITS.get(quantity.is_a())
                    factor = self._scale(kind, quantity.Unit) if kind else 1.0
                    if factor != 1.0:
                        factors[quantity.Name] = factor
            self._factors[key] = factors
        return self._factors[key]

    def _scale(self, kind: str, unit: ifcopenshell.entity_instance | None) -> float:
        if unit is None:
            return self._unit_scales[kind]
        if unit.is_a("IfcSIUnit"):  # e.g. millimetre on the property itself
            return unit_util.get_prefix_multiplier(unit.Prefix) ** UNIT_DIMENSIONS[kind] if unit.Prefix else 1.0
        return 1.0  # imperial units on single properties: left as they are

    def _type_sets(self, element_type: ifcopenshell.entity_instance) -> tuple[dict, dict, dict]:
        key = element_type.id()
        if key not in self._types:
            psets: dict[str, dict] = {}
            quantities: dict[str, dict] = {}
            factors: dict[str, dict[str, float]] = {}
            if element_type.is_a("IfcTypeObject"):
                for definition in element_type.HasPropertySets or []:
                    sets = _kind(definition, psets, quantities)
                    if sets is not None:
                        sets.setdefault(definition.Name, {}).update(element_util.get_property_definition(definition))
                        factors.setdefault(definition.Name, {}).update(self._factors_of(definition))
            else:
                psets = element_util.get_psets(element_type, psets_only=True, should_inherit=False)
                quantities = element_util.get_psets(element_type, qtos_only=True, should_inherit=False)
            self._types[key] = psets, quantities, factors
        return self._types[key]

    def _properties(self, definition: ifcopenshell.entity_instance) -> dict:
        key = definition.id()
        uses = self._uses.pop(key, 0)  # including this one
        properties = self._shared.get(key) if uses > 1 else self._shared.pop(key, None)
        if properties is None:
            properties = element_util.get_property_definition(definition)
        if uses > 1:
            self._shared[key] = properties
            self._uses[key] = uses - 1
        return properties


def _definitions(relationship: ifcopenshell.entity_instance) -> tuple:
    definition = relationship.RelatingPropertyDefinition
    # IfcPropertySetDefinitionSet is a defined type wrapping a list of property set definitions.
    return definition.wrappedValue if definition.is_a("IfcPropertySetDefinitionSet") else (definition,)


def _kind(definition: ifcopenshell.entity_instance, psets: dict, quantities: dict) -> dict | None:
    """Where ``get_psets`` puts a definition: with the property sets, the quantities or neither."""
    if definition.is_a("IfcPropertySet") or definition.is_a("IfcPreDefinedPropertySet"):
        return psets
    return quantities if definition.is_a("IfcElementQuantity") else None


def _standard_quantities(name: str) -> bool:
    """Whether a quantity set is one of IFC's standard ones (IFC4 "Qto_…", IFC2x3 "BaseQuantities")."""
    return name.startswith("Qto_") or name == "BaseQuantities"


class _LayerTable:
    """Creates nested layers per spatial element with child layers per IFC class on demand."""

    def __init__(self, rhino: rhino3dm.File3dm):
        self._rhino = rhino
        # Spatial layers by entity id, root fallback layers by name: (layer index, layer id).
        self._parents: dict[int | str, tuple[int, object]] = {}
        self._classes: dict[tuple[int | str, str], int] = {}
        # Layer names already used below each parent (None: top level); Rhino needs them unique.
        self._names: dict[object, set[str]] = {}

    def get(self, path: SpatialPath, ifc_class: str, color: Color, root: str = NO_STOREY) -> int:
        """The class layer below ``path``, or below the ``root`` layer if the path is empty."""
        parent = path[-1].id() if path else root
        key = (parent, ifc_class)
        if key not in self._classes:
            if path:
                self.spatial(path)
            elif root not in self._parents:
                self._parents[root] = self._add(root, (0, 0, 0, 255), None)
            # The class layer takes the colour of its first element.
            self._classes[key] = self._add(
                ifc_class, color[:3] + (255,), self._parents[parent][1], visible=ifc_class not in HIDDEN_CLASSES,
            )[0]
        return self._classes[key]

    def spatial(self, path: SpatialPath) -> tuple[int, object]:
        key = path[-1].id()
        if key not in self._parents:
            parent_id = self.spatial(path[:-1])[1] if len(path) > 1 else None
            self._parents[key] = self._add(_level_name(path[-1]), (0, 0, 0, 255), parent_id)
        return self._parents[key]

    def _add(self, name: str, color: Color, parent_id, visible: bool = True) -> tuple[int, object]:
        names = self._names.setdefault(parent_id, set())
        candidate, n = name, 2
        while candidate in names:
            candidate, n = f"{name} ({n})", n + 1
        names.add(candidate)

        layer = rhino3dm.Layer()
        layer.Name = candidate
        layer.Color = color
        layer.Visible = visible
        if parent_id is not None:
            layer.ParentLayerId = parent_id
        index = self._rhino.Layers.Add(layer)
        return index, self._rhino.Layers.FindIndex(index).Id


def _clean_name(name: str | None, fallback: str) -> str:
    """Make a string usable as a Rhino layer/material name."""
    name = re.sub(r"[\x00-\x1f\x7f]", " ", name or "").replace("::", ":")
    name = name.strip().lstrip("([{}])").strip()
    return name[:MAX_STRING_LENGTH] or fallback
