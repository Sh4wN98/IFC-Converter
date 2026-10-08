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
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.ifcopenshell_wrapper as wrapper
import ifcopenshell.util.element as element_util
import ifcopenshell.util.unit as unit_util
import numpy
import rhino3dm

from ifc_converter.converter import (
    LINEAR_DEFLECTION, ChunkEnd, ProgressCallback, StatusCallback, available_memory, geometry_library,
    iter_shapes, product_label, shape_products,
)
from ifc_converter.polysurface import planar_polysurface
from ifc_converter.process import exit_with_parent, no_crash_dialogs

log = logging.getLogger(__name__)

NO_STOREY = "Ohne Geschoss"
# Root layer for curve-only elements outside the spatial structure, such as alignments.
AXES = "Achsen"
# Root layer of the objects that make up block definitions (option "blocks"). Rhino draws an
# instance with the layer of each of these objects, so it stays visible; the instances themselves
# are on the layers of their elements.
BLOCK_LAYER = "Blockdefinitionen"
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
# Property values that only stand in for a missing value (compared stripped, in lower case). They
# made up a third to half of all user text of Revit models, together with values that just repeat
# their property's name (Revit's COBie parameters: "SerialNumber" = "SerialNumber"), and the user
# text was a third of the file size. NOTDEFINED is IFC's own "no value" for enumerations (unlike
# USERDEFINED, which is kept); "$" is an unset STEP attribute that an exporter wrote as text.
PLACEHOLDERS = {
    "", "-", "--", "---", "n/a", "n.a.", "none", "<none>", "null", "unset", "unknown", "notknown",
    "notdefined", "undefined", "<default>", "$",
}
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
# A pool whose worker died is started anew this many times; after that the elements are built one
# at a time in a worker of their own.
MAX_POOL_RESTARTS = 3

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
    blocks: bool = False,
    source: Path | None = None,
) -> int:
    """Write every element with geometry, layered by its place in the spatial structure and IFC class.

    With ``geometry="brep"`` elements become joined planar polysurfaces; elements with more than
    MAX_BREP_FACES triangles (tessellated organic shapes) or without a valid Brep stay meshes.
    With ``geometry="mesh"`` every element is a mesh. Elements that only have edges (alignment
    axes, grids) become polylines. An element with several materials becomes one object per
    material, grouped. With ``blocks`` type geometry placed several times becomes a block
    definition, and its elements block instances. ``source`` (the IFC file) is named in the
    document user text.
    """
    products = shape_products(model, EXCLUDED_CLASSES)
    writer = _Writer(model, products, source)
    curve_elements = {element.id(): element for element in _curve_elements(model)}
    yielded: set[int] = set()
    settings = _settings()

    def culprit(element_id: int, fallback: str | None) -> None:
        label = product_label(model.by_id(element_id))
        if fallback:
            text = f"Rhino-Geometrie ließ einen Hilfsprozess abstürzen, stattdessen als Netz übernommen: {label}"
        else:
            text = f"Rhino-Geometrie ließ einen Hilfsprozess abstürzen, Bauteil weggelassen: {label}"
        if status:
            status("note", text)
        else:
            log.warning("%s", text)

    with _Builder(_worker_count(threads, len(products)), _SolidItems(model), culprit) as builder:
        # Meshes and block definitions are computed in their own coordinates, so shapes that share
        # a geometry share its mesh or block. Polysurfaces are built from world coordinates.
        meshes = _MeshCache(builder) if geometry == "mesh" else None
        definitions = _Blocks(model, products, builder) if blocks else None
        local = meshes is not None or definitions is not None
        if local:
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
            brep = geometry == "brep" and triangles <= MAX_BREP_FACES
            if not triangles:
                entry = _Element([(_material(shape_geometry), _Ready(_polylines(shape_geometry, _placement(shape))))])
            elif definitions is not None and definitions.eligible(shape):
                entry = _Instance(definitions.definition(shape, brep), _placement(shape))
            elif meshes is not None:
                entry = _Element(meshes.place(shape))
            else:
                if local:  # polysurfaces: moved to world coordinates as the kernel would
                    shape_geometry = _world(shape_geometry, _placement(shape))
                entry = _Element(builder.build(shape.id, shape_geometry, brep))
            ordered.add(shape.id, entry)
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


# Name, colour (RGBA) and transparency (0-1) of a material.
Material = tuple[str, Color, float]


class _Writer:
    """Adds objects to a Rhino file with the layers, colours, materials and user text of their element."""

    def __init__(
        self, model: ifcopenshell.file, products: list[ifcopenshell.entity_instance] | None = None,
        source: Path | None = None,
    ):
        self.model = model
        self.rhino = rhino3dm.File3dm()
        self.rhino.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters
        # 1 mm, as Rhino's "Large Objects - Meters" template: what joins and Booleans in Rhino work
        # with. The geometry is far more precise (polysurface faces: MAX_PLANE_DEVIATION, 1 mm at most).
        self.rhino.Settings.ModelAbsoluteTolerance = 0.001
        self.rhino.Settings.ModelAngleToleranceDegrees = 1.0
        for key, value in _document_strings(model, source).items():
            self.rhino.Strings[key] = value
        self.paths = _SpatialPaths(model)
        self.layers = _LayerTable(self.rhino)
        # Spatial layers are created up front so the layer panel lists them in the order of the
        # spatial structure, storeys by elevation, ahead of the fallback layers.
        for path in sorted(self.paths.levels(model), key=_levels_sort_key):
            self.layers.spatial(path)
        self.materials: dict[Material, int] = {}
        self.property_sets = _PropertySets(model)
        self.groups = _Groups(self.rhino)
        # Products with geometry of their own; aggregates without it become groups of their parts.
        self._with_shape = {product.id() for product in products} if products is not None else None
        self._aggregates: dict[int, int] = {}
        self._block_layer: int | None = None
        self._block_names: set[str] = set()  # Rhino needs them unique
        self.elements = 0

    def add(self, element_id: int, parts: list[tuple[Material, object]]) -> None:
        """Add an element as one object per part (several are grouped), or as polylines."""
        parts = [(material, geometry) for material, geometry in parts if geometry is not None]
        if not parts:
            return
        element = self.model.by_id(element_id)
        material, geometry = parts[0]
        curves = isinstance(geometry, list)
        attributes = self._attributes(element, material, AXES if curves else NO_STOREY)
        if curves:
            if len(geometry) > 1:
                # The pieces of one element select together.
                attributes.AddToGroup(self.groups.add(attributes.Name))
            for polyline in geometry:
                self.rhino.Objects.AddPolyline(polyline, attributes)
        else:
            if len(parts) > 1:
                # One object per material, so glass stays transparent; they select together.
                attributes.AddToGroup(self.groups.add(attributes.Name))
            for material, geometry in parts:
                self._set_material(attributes, material)
                if isinstance(geometry, rhino3dm.Brep):
                    self.rhino.Objects.AddBrep(geometry, attributes)
                else:
                    self.rhino.Objects.AddMesh(geometry, attributes)
        self.elements += 1

    def add_instance(self, element_id: int, definition: _Definition, placement: numpy.ndarray | None) -> None:
        """Add an element as an instance of a block definition."""
        if not self._define(definition):
            return
        element = self.model.by_id(element_id)
        attributes = self._attributes(element, definition.material, NO_STOREY)
        reference = rhino3dm.InstanceReference(
            definition.id, _transform(placement) if placement is not None else rhino3dm.Transform(1.0)
        )
        self.rhino.Objects.AddInstanceObject(reference, attributes)
        self.elements += 1

    def _define(self, definition: _Definition) -> bool:
        """Add the block definition to the file on its first use; False if it has no geometry."""
        if definition.id is None and definition.parts is not None:
            parts = [(material, built.get()) for material, built in definition.parts]
            parts = [(material, geometry) for material, geometry in parts if geometry is not None]
            definition.parts = None  # only one copy of the geometry is kept: the file's
            if parts:
                if self._block_layer is None:
                    self._block_layer = self.layers.root(BLOCK_LAYER)
                objects = []
                for material, _ in parts:
                    attributes = rhino3dm.ObjectAttributes()
                    attributes.LayerIndex = self._block_layer
                    if len(parts) == 1:
                        # Colour and material come from the instance, like those of any other element.
                        attributes.ColorSource = rhino3dm.ObjectColorSource.ColorFromParent
                        attributes.MaterialSource = rhino3dm.ObjectMaterialSource.MaterialFromParent
                    else:  # each material its own, so glass stays transparent
                        attributes.ColorSource = rhino3dm.ObjectColorSource.ColorFromObject
                        self._set_material(attributes, material)
                    objects.append(attributes)
                index = self.rhino.InstanceDefinitions.Add(
                    _unique(definition.name, self._block_names), "", "", "", rhino3dm.Point3d(0, 0, 0),
                    tuple(geometry for _, geometry in parts), tuple(objects),
                )
                definition.id = self.rhino.InstanceDefinitions.FindIndex(index).Id
        return definition.id is not None

    def _attributes(self, element: ifcopenshell.entity_instance, material: Material, root: str) -> rhino3dm.ObjectAttributes:
        path = self.paths.of_element(element)
        attributes = _attributes(element, material[1], self.property_sets, _storey(path))
        attributes.LayerIndex = self.layers.get(path, element.is_a(), material[1], root)
        self._set_material(attributes, material)
        for group in self._aggregate_groups(element):
            attributes.AddToGroup(group)
        return attributes

    def _set_material(self, attributes: rhino3dm.ObjectAttributes, material: Material) -> None:
        attributes.ObjectColor = material[1]
        attributes.MaterialIndex = _material_index(self.rhino, self.materials, material)
        attributes.MaterialSource = rhino3dm.ObjectMaterialSource.MaterialFromObject

    def _aggregate_groups(self, element: ifcopenshell.entity_instance) -> list[int]:
        """The groups of the aggregates (assemblies, curtain walls, stairs) the element is a part of.

        Only aggregates without geometry of their own, up to the first one with geometry or a
        spatial element: the parts are all there is of them in Rhino.
        """
        groups: list[int] = []
        if self._with_shape is None:
            return groups
        parent = element_util.get_aggregate(element)
        while parent is not None and not _is_spatial(parent) and parent.id() not in self._with_shape:
            key = parent.id()
            if key not in self._aggregates:
                self._aggregates[key] = self.groups.add(_clean_name(parent.Name, f"{parent.is_a()} {parent.GlobalId}"))
            groups.append(self._aggregates[key])
            parent = element_util.get_aggregate(parent)
        return groups


class _Groups:
    """Adds groups to a Rhino file under names not used yet."""

    def __init__(self, rhino: rhino3dm.File3dm):
        self._rhino = rhino
        self._names: set[str] = set()

    def add(self, name: str) -> int:
        group = rhino3dm.Group()
        group.Name = _unique(name, self._names)
        self._rhino.Groups.Add(group)
        return len(self._rhino.Groups) - 1


def _unique(name: str, names: set[str]) -> str:
    """``name``, or with " (2)", " (3)" ... appended if it is in ``names``; added to them."""
    candidate, n = name, 2
    while candidate in names:
        candidate, n = f"{name} ({n})", n + 1
    names.add(candidate)
    return candidate


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
    element: ifcopenshell.entity_instance, color: Color, property_sets: _PropertySets | None = None,
    storey: str | None = None,
) -> rhino3dm.ObjectAttributes:
    attributes = rhino3dm.ObjectAttributes()
    attributes.Name = element.Name or element.GlobalId
    attributes.ObjectColor = color
    attributes.ColorSource = rhino3dm.ObjectColorSource.ColorFromObject
    for key, value in _user_strings(element, property_sets, storey).items():
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
        self._open: list[tuple[int, _Element | _Instance]] = []
        self._closed: deque[tuple[int, _Element | _Instance]] = deque()

    def add(self, element_id: int, entry: _Element | _Instance) -> None:
        self._open.append((element_id, entry))

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
        while self._closed and (wait or self._closed[0][1].ready()):
            element_id, entry = self._closed.popleft()
            # Each object goes into the Rhino file right away, so only one copy of the geometry is kept.
            entry.write(self._writer, element_id)


class _Element:
    """An element as objects of their own: its parts, (material, geometry being built) each."""

    def __init__(self, parts: list[tuple[Material, _Ready | _Deferred | _Placed]]):
        self._parts = parts

    def ready(self) -> bool:
        return all(built.ready() for _, built in self._parts)

    def write(self, writer: _Writer, element_id: int) -> None:
        writer.add(element_id, [(material, built.get()) for material, built in self._parts])


class _Instance:
    """An element as an instance of a block definition, at ``placement`` (None: where it is)."""

    def __init__(self, definition: _Definition, placement: numpy.ndarray | None):
        self._definition, self._placement = definition, placement

    def ready(self) -> bool:
        return self._definition.ready()

    def write(self, writer: _Writer, element_id: int) -> None:
        writer.add_instance(element_id, self._definition, self._placement)


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
        self.pool: concurrent.futures.Executor | None = None  # the pool it was sent to
        # Per job the encoded polysurface or mesh, or None (see _build_batch).
        self.results: list | None = None

    def set_results(self, results: list) -> None:
        self.results = results
        self.jobs = self.future = self.pool = None  # the future would keep the results


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
    """Builds the polysurfaces and meshes of shapes, in ``workers`` worker processes or (0) right away.

    If a worker dies (out of memory, or a crash in native code such as rhino3dm), the pool is
    started anew for the batches to come, and the batches it lost are built again one element at a
    time in a worker of their own, so a crash there points at its element: that one is retried as a
    mesh, or left out, and ``culprit`` hears about it (element id, "mesh" or None).
    """

    def __init__(self, workers: int, solids: _SolidItems | None = None, culprit: Callable | None = None):
        self._workers = workers
        self._solids = solids
        self._culprit = culprit
        self._pool: concurrent.futures.ProcessPoolExecutor | None = None
        self._restarts = 0
        # The worker for elements built one at a time, and whether workers cannot run at all.
        self._isolation: concurrent.futures.ProcessPoolExecutor | None = None
        self._in_process = False
        self._batch = _Batch()
        # Batches sent to the workers: their futures and triangles.
        self._pending: deque[tuple[concurrent.futures.Future, int]] = deque()
        self._pending_triangles = 0

    def __enter__(self) -> _Builder:
        return self

    def __exit__(self, *exc_info) -> None:
        for pool in (self._pool, self._isolation):
            if pool is not None:
                # On an error or a cancel nothing more is needed from the workers.
                pool.shutdown(wait=exc_info[0] is None, cancel_futures=True)
        self._pool = self._isolation = None

    def build(self, element_id: int, geometry, brep: bool) -> list[tuple[Material, _Ready | _Deferred]]:
        """Per material of ``geometry``: the material and its polysurface (if ``brep``) or else its
        mesh, or None."""
        faces, solid_ids = geometry.faces_buffer, b""
        if self._solids is not None:
            faces, solid_ids = _outward(geometry, self._solids)
        return [
            (material, self._submit((element_id, brep, verts, part_faces, items if brep else b"", solid_ids if brep else b"")))
            for material, verts, part_faces, items in _split(geometry, faces)
        ]

    def _submit(self, job: tuple) -> _Ready | _Deferred:
        if not self._workers and not self._restarts:
            return _Ready(_build_from_buffers(*job[1:]))
        batch = self._batch
        batch.jobs.append(job)
        batch.triangles += len(job[3]) // 12
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
        if not self._workers:  # the workers broke down too often: one at a time from here on
            batch.set_results(self._isolated(batch.jobs))
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
                self._pool = _pool(self._workers)
            batch.future = self._pool.submit(_build_batch, batch.jobs)
            batch.pool = self._pool
        except Exception as exc:  # a broken pool, or workers that cannot be started at all
            self._broken(exc)
            batch.set_results(_build_batch(batch.jobs))
            return
        # The input is only kept to build it again should a worker fail.
        batch.future.add_done_callback(functools.partial(_release_jobs, weakref.ref(batch)))
        self._pending.append((batch.future, batch.triangles))
        self._pending_triangles += batch.triangles

    def result(self, batch: _Batch) -> list:
        """The results of ``batch``, built again one element at a time if a worker died."""
        if batch.results is None:
            if batch.future is None:
                self.flush()
            if batch.results is None:
                try:
                    batch.set_results(batch.future.result())
                except concurrent.futures.BrokenExecutor as exc:
                    # Every batch in the pool fails with it; the pool is replaced once.
                    if batch.pool is self._pool:
                        self._restart(exc)
                    batch.set_results(self._isolated(batch.jobs))
        return batch.results

    def _restart(self, error: BaseException) -> None:
        self._restarts += 1
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._pool = None
        if self._restarts > MAX_POOL_RESTARTS:
            self._workers = 0
        log.warning(
            "A worker process ended (%s: %s), %s", type(error).__name__, error,
            "building its elements again one by one" if self._workers else
            "building the remaining geometry one element at a time",
        )

    def _isolated(self, jobs: list[tuple]) -> list:
        """Build ``jobs`` one at a time in a worker of their own: a crash points at its element."""
        results = []
        for job in jobs:
            element_id, brep = job[0], job[1]
            # A polysurface that crashes the worker is tried once more as a mesh.
            attempts = [job, (element_id, False, job[2], job[3], b"", b"")] if brep else [job]
            for number, attempt in enumerate(attempts):
                try:
                    result = self._build_isolated(attempt)
                except concurrent.futures.BrokenExecutor:
                    self._isolation.shutdown(wait=False, cancel_futures=True)
                    self._isolation = None
                    continue
                if number and self._culprit:
                    self._culprit(element_id, "mesh")
                break
            else:
                result = None
                if self._culprit:
                    self._culprit(element_id, None)
            results.append(result)
        return results

    def _build_isolated(self, job: tuple):
        if self._isolation is None and not self._in_process:
            try:
                self._isolation = _pool(1)
                # An empty batch shows the new worker runs at all (it may not, e.g. out of memory).
                self._isolation.submit(_build_batch, []).result()
            except Exception as exc:
                log.warning("Worker processes cannot run (%s: %s), building in the main process", type(exc).__name__, exc)
                if self._isolation is not None:
                    self._isolation.shutdown(wait=False, cancel_futures=True)
                    self._isolation = None
                self._in_process = True
        if self._in_process:
            return _build_batch([job])[0]
        return self._isolation.submit(_build_batch, [job]).result()[0]

    def _broken(self, error: BaseException) -> None:
        if self._workers:
            log.warning(
                "Worker processes failed (%s: %s), building the remaining geometry in the main process",
                type(error).__name__, error,
            )
        self._workers = 0
        self._in_process = True


def _pool(workers: int) -> concurrent.futures.ProcessPoolExecutor:
    return concurrent.futures.ProcessPoolExecutor(
        workers, multiprocessing.get_context("spawn"), _worker_init, (os.getpid(),)
    )


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

    Each job is (element id, brep, verts, faces, item ids, solid item ids); each result ("brep" or
    "mesh", the geometry's Encode()) or None. Decoding gives the very same geometry.
    """
    results = []
    for job in jobs:
        geometry = _build_from_buffers(*job[1:])
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


def _split(geometry, faces: bytes) -> list[tuple[Material, bytes, bytes, bytes]]:
    """The parts of a shape by material: (material, verts, faces, item ids), each with only its own
    vertices; the material covering most faces first.

    Faces without a material go with that one. Materials alike in name, colour and transparency
    count as one.
    """
    materials = [_material_of(material) for material in geometry.materials]
    count = len(faces) // 12
    ids = numpy.frombuffer(geometry.material_ids_buffer, dtype=numpy.int32)
    if not materials or len(ids) != count:
        return [(_material(geometry), geometry.verts_buffer, faces, geometry.item_ids_buffer)]
    # Each material index stands for the first one alike.
    first = {}
    alike = numpy.array([first.setdefault(material, index) for index, material in enumerate(materials)])
    known = ids[(ids >= 0) & (ids < len(materials))]
    main = _main_material(alike[known]) if len(known) else 0
    keys = numpy.where((ids >= 0) & (ids < len(materials)), alike[numpy.clip(ids, 0, len(materials) - 1)], main)
    present = numpy.unique(keys)
    if len(present) == 1:
        return [(materials[int(present[0])], geometry.verts_buffer, faces, geometry.item_ids_buffer)]
    triangles = numpy.frombuffer(faces, dtype=numpy.int32).reshape(-1, 3)
    points = numpy.frombuffer(geometry.verts_buffer, dtype=numpy.float64).reshape(-1, 3)
    items = numpy.frombuffer(geometry.item_ids_buffer, dtype=numpy.int32)
    order = [main] + [int(key) for key in present if key != main]
    parts = []
    for key in order:
        selected = keys == key
        used, local = numpy.unique(triangles[selected], return_inverse=True)
        part_items = items[selected].tobytes() if len(items) == count else b""
        parts.append((
            materials[key], points[used].tobytes(), local.reshape(-1, 3).astype(numpy.int32).tobytes(), part_items,
        ))
    return parts


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
        # Per geometry its parts (material, mesh) and the number of input vertices.
        self._meshes: OrderedDict[str, tuple[list, int]] = OrderedDict()
        self._vertices = 0

    def place(self, shape) -> list[tuple[Material, _Placed]]:
        """The meshes of a shape (one per material), moved to where the shape is."""
        key = shape.geometry.id
        if key in self._meshes:
            self._meshes.move_to_end(key)
            parts = self._meshes[key][0]
        else:
            # Counted before welding: the meshes being built in the workers are not known yet.
            vertices = len(shape.geometry.verts_buffer) // 24
            parts = self._builder.build(shape.id, shape.geometry, False)
            self._meshes[key] = parts, vertices
            self._vertices += vertices
            while self._vertices > MESH_CACHE_VERTICES and len(self._meshes) > 1:
                self._vertices -= self._meshes.popitem(last=False)[1][1]
        placement = _placement(shape)
        return [(material, _Placed(mesh, placement)) for material, mesh in parts]


class _Definition:
    """A block definition: built once, added to the file on its first use."""

    def __init__(self, name: str, parts: list[tuple[Material, _Ready | _Deferred]]):
        self.name = name
        self.parts: list | None = parts
        self.material = parts[0][0]  # the instances' colour and material
        self.id = None  # the definition's id in the file, once added

    def ready(self) -> bool:
        return self.id is not None or self.parts is None or all(built.ready() for _, built in self.parts)


class _Blocks:
    """The block definitions of type geometry that several elements place (option "blocks").

    Which elements share a geometry shows in the IFC: their body is the same representation, or
    places the same representation maps (IfcMappedItem). Only those become instances: a block for a
    single element would only add a definition. The kernel's geometry id tells which of them do
    end up with the same geometry (an opening cut into one makes it differ).
    """

    def __init__(self, model: ifcopenshell.file, products: list, builder: _Builder):
        self._model = model
        self._builder = builder
        self._definitions: dict[str, _Definition] = {}
        users: dict[int, int] = {}
        keys: dict[int, set[int]] = {}
        for product in products:
            if _has_openings(product):
                continue
            shared = _shared_representations(product)
            keys[product.id()] = shared
            for key in shared:
                users[key] = users.get(key, 0) + 1
        self._eligible = {product for product, shared in keys.items() if any(users[key] > 1 for key in shared)}

    def eligible(self, shape) -> bool:
        # Shapes the kernel could only compute in world coordinates have no placement of their own.
        return shape.id in self._eligible and not shape.geometry.id.endswith("world-coords")

    def definition(self, shape, brep: bool) -> _Definition:
        """The block definition of the shape's geometry (polysurfaces if ``brep``, else meshes)."""
        key = shape.geometry.id
        if key not in self._definitions:
            # Named after the type, as in the authoring program, else after the first element.
            element = self._model.by_id(shape.id)
            element_type = element_util.get_type(element)
            name = _clean_name(element_type.Name if element_type else None, _clean_name(element.Name, element.is_a()))
            self._definitions[key] = _Definition(name, self._builder.build(shape.id, shape.geometry, brep))
        return self._definitions[key]


def _has_openings(product: ifcopenshell.entity_instance) -> bool:
    return bool(getattr(product, "HasOpenings", None))


def _shared_representations(product: ifcopenshell.entity_instance) -> set[int]:
    """The ids of the body representations of a product and of the representation maps they place:
    what other products may share with it."""
    shared: set[int] = set()
    for representation in product.Representation.Representations if product.Representation else ():
        if representation.RepresentationIdentifier not in (None, "Body", "Facetation"):
            continue
        shared.add(representation.id())
        for item in representation.Items:
            if item.is_a("IfcMappedItem"):
                shared.add(item.MappingSource.id())
    return shared


def _world(geometry, placement: numpy.ndarray | None):
    """The geometry with its vertices moved by ``placement`` (None: as it is)."""
    if placement is None:
        return geometry
    points = numpy.frombuffer(geometry.verts_buffer, dtype=numpy.float64).reshape(-1, 3)
    return SimpleNamespace(
        verts_buffer=(points @ placement[:3, :3].T + placement[:3, 3]).tobytes(),
        faces_buffer=geometry.faces_buffer, item_ids_buffer=geometry.item_ids_buffer,
        material_ids_buffer=geometry.material_ids_buffer, materials=geometry.materials,
    )


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


def _material(geometry) -> Material:
    """Name, colour and transparency (0-1) of the material covering most faces."""
    if not geometry.materials:
        return DEFAULT_MATERIAL
    ids = numpy.frombuffer(geometry.material_ids_buffer, dtype=numpy.int32)
    ids = ids[ids >= 0]
    return _material_of(geometry.materials[_main_material(ids) if len(ids) else 0])


DEFAULT_MATERIAL: Material = ("Default", (180, 180, 180, 255), 0.0)


def _main_material(ids: numpy.ndarray) -> int:
    """The most frequent of the material ids; on a tie the one that comes first."""
    values, first, counts = numpy.unique(ids, return_index=True, return_counts=True)
    return int(values[numpy.lexsort((first, -counts))[0]])


def _material_of(material) -> Material:
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


def _material_index(rhino: rhino3dm.File3dm, cache: dict, key: Material) -> int:
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


def _user_strings(
    element: ifcopenshell.entity_instance, property_sets: _PropertySets | None = None, storey: str | None = None,
) -> dict[str, str]:
    strings = {
        "IfcGlobalId": element.GlobalId,
        "IfcClass": element.is_a(),
        "IfcName": element.Name or "",
    }
    element_type = element_util.get_type(element)
    predefined = _predefined_type(element, element_type)
    object_type = getattr(element, "ObjectType", None)
    for key, value in (
        ("IfcType", element_type.Name if element_type else None),
        ("IfcPredefinedType", predefined),
        ("IfcObjectType", object_type if object_type != predefined else None),
        ("IfcTag", getattr(element, "Tag", None)),
        ("IfcStorey", storey),
    ):
        if isinstance(value, str) and not _placeholder(value):
            strings[key] = value[:MAX_STRING_LENGTH]
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
            if isinstance(value, str) and _placeholder(value, prop):
                continue
            # 12 significant digits drop float noise ("6403.99999999979" → "6404") and keep 0.01 mm
            # even in georeferenced coordinates.
            text = _float_text(value) if isinstance(value, float) else str(value)
            strings[f"{pset}.{prop}"] = text[:MAX_STRING_LENGTH]
    return strings


def _predefined_type(element: ifcopenshell.entity_instance, element_type: ifcopenshell.entity_instance | None) -> str | None:
    """The element's PredefinedType, or its type's, which takes precedence; for USERDEFINED the
    name given in ObjectType (ElementType for types). None if neither has one (NOTDEFINED)."""
    for entity, custom in ((element_type, "ElementType"), (element, "ObjectType")):
        value = getattr(entity, "PredefinedType", None) if entity is not None else None
        if value == "USERDEFINED":
            value = getattr(entity, custom, None) or value
        if value and value != "NOTDEFINED":
            return value
    return None


def _placeholder(value: str, name: str | None = None) -> bool:
    """Whether a text value only stands in for a missing one (see PLACEHOLDERS), or repeats the
    ``name`` of its property."""
    return value.strip().lower() in PLACEHOLDERS or value == name


def _storey(path: SpatialPath) -> str | None:
    """The name of the innermost storey in a layer path."""
    for level in reversed(path):
        if level.is_a("IfcBuildingStorey"):
            return level.Name
    return None


def _document_strings(model: ifcopenshell.file, source: Path | None) -> dict[str, str]:
    """The document user text: source file, schema, project and georeferencing.

    The geometry stays in the project coordinates; IfcMapConversion is given here so it can be
    applied in Rhino. Eastings, northings and height in metres, the rotation of the project's x
    axis from grid east in degrees (counter-clockwise).
    """
    strings = {}
    if source is not None:
        strings["IfcSourceFile"] = Path(source).name
    strings["IfcSchema"] = getattr(model, "schema_identifier", None) or model.schema
    projects = model.by_type("IfcProject")
    if projects and projects[0].Name and not _placeholder(projects[0].Name):
        strings["IfcProject"] = projects[0].Name
    try:
        conversions = model.by_type("IfcMapConversion")
    except RuntimeError:  # IFC2X3
        conversions = []
    if conversions:
        conversion = conversions[0]
        crs = conversion.TargetCRS
        map_unit = getattr(crs, "MapUnit", None)
        try:
            scale = unit_util.get_named_unit_scale(map_unit) if map_unit else unit_util.calculate_unit_scale(model)
        except Exception:
            scale = 1.0
        for name in ("Eastings", "Northings", "OrthogonalHeight"):
            value = getattr(conversion, name, None)
            if value is not None:
                strings[f"IfcMapConversion.{name}"] = _float_text(float(value) * scale)
        abscissa = getattr(conversion, "XAxisAbscissa", None)
        ordinate = getattr(conversion, "XAxisOrdinate", None)
        if abscissa is not None and ordinate is not None:
            strings["IfcMapConversion.XAxisAbscissa"] = _float_text(float(abscissa))
            strings["IfcMapConversion.XAxisOrdinate"] = _float_text(float(ordinate))
            strings["IfcMapConversion.Rotation"] = _float_text(math.degrees(math.atan2(ordinate, abscissa)))
        if getattr(conversion, "Scale", None) is not None:
            strings["IfcMapConversion.Scale"] = _float_text(float(conversion.Scale))
        if crs is not None and crs.Name:
            strings["IfcProjectedCRS.Name"] = crs.Name
    return {key: value[:MAX_STRING_LENGTH] for key, value in strings.items()}


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

    def root(self, name: str) -> int:
        """A layer of its own at the top level."""
        if name not in self._parents:
            self._parents[name] = self._add(name, (0, 0, 0, 255), None)
        return self._parents[name][0]

    def spatial(self, path: SpatialPath) -> tuple[int, object]:
        key = path[-1].id()
        if key not in self._parents:
            parent_id = self.spatial(path[:-1])[1] if len(path) > 1 else None
            self._parents[key] = self._add(_level_name(path[-1]), (0, 0, 0, 255), parent_id)
        return self._parents[key]

    def _add(self, name: str, color: Color, parent_id, visible: bool = True) -> tuple[int, object]:
        layer = rhino3dm.Layer()
        layer.Name = _unique(name, self._names.setdefault(parent_id, set()))
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
