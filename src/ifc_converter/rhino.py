from __future__ import annotations

import itertools
import math
import re
from collections import OrderedDict, deque
from collections.abc import Iterator
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.ifcopenshell_wrapper as wrapper
import ifcopenshell.util.element as element_util
import numpy
import rhino3dm

from ifc_converter.converter import ProgressCallback, geometry_library, iter_shapes
from ifc_converter.polysurface import planar_polysurface

NO_STOREY = "Ohne Geschoss"
# Root layer for curve-only elements outside the spatial structure, such as alignments.
AXES = "Achsen"
FILE_VERSION = 7
MAX_STRING_LENGTH = 1000
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
    # Meshes are computed in their own coordinates, so shapes that share a geometry share its mesh.
    # Polysurfaces are built from world coordinates.
    meshes = _MeshCache() if geometry == "mesh" else None
    if meshes is not None:
        settings.set("use-world-coords", False)
    shapes = iter_shapes(model, settings, threads, EXCLUDED_CLASSES, progress, ITERATOR_SHARE)
    # The second pass is generated lazily, after the first has recorded what it yielded.
    missing = (element for id_, element in curve_elements.items() if id_ not in yielded)
    for shape in itertools.chain(shapes, _curve_shapes(model, missing)):
        if shape.id in curve_elements:
            yielded.add(shape.id)
        triangles = shape.geometry.faces
        if not shape.geometry.verts:
            continue
        if not triangles:
            writer.add(shape, _polylines(shape.geometry, _placement(shape)))
            continue
        if meshes is not None:
            writer.add(shape, meshes.place(shape))
            continue
        brep = None
        if geometry == "brep" and len(triangles) <= 3 * MAX_BREP_FACES:
            brep = _brep(shape.geometry)
        writer.add(shape, _mesh(shape.geometry) if brep is None else brep)

    if not writer.rhino.Write(str(output_path), FILE_VERSION):
        raise OSError(f"Could not write Rhino file: {output_path}")
    return writer.elements


class _Writer:
    """Adds objects to a Rhino file with the layers, colours, materials and user text of their element."""

    def __init__(self, model: ifcopenshell.file):
        self.model = model
        self.rhino = rhino3dm.File3dm()
        self.rhino.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters
        self.paths = _SpatialPaths(model)
        self.layers = _LayerTable(self.rhino)
        # Spatial layers are created up front so the layer panel lists them in the order of the
        # spatial structure, storeys by elevation, ahead of the fallback layers.
        for path in sorted(self.paths.levels(model), key=_levels_sort_key):
            self.layers.spatial(path)
        self.materials: dict[tuple[str, Color, float], int] = {}
        self.elements = 0

    def add(self, shape, geometry: rhino3dm.Mesh | rhino3dm.Brep | list[rhino3dm.Polyline] | None) -> None:
        # Each object goes into the Rhino file right away, so only one copy of the geometry is kept.
        if geometry is None:
            return
        element = self.model.by_id(shape.id)
        name, color, transparency = _material(shape.geometry)
        attributes = _attributes(element, color)
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
    settings.set("use-world-coords", True)
    # Unwelded vertices keep hard edges between faces sharp when Rhino shades the mesh.
    settings.set("weld-vertices", False)
    settings.set("use-material-names", True)
    settings.set("no-normals", True)
    return settings


def _brep(geometry) -> rhino3dm.Brep | None:
    """The element as a joined polysurface: coplanar triangles become one face (with holes)."""
    indices = geometry.faces
    triangles = [[indices[i:i + 3]] for i in range(0, len(indices), 3)]
    return planar_polysurface(geometry.verts, triangles, geometry.item_ids)


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


def _attributes(element: ifcopenshell.entity_instance, color: Color) -> rhino3dm.ObjectAttributes:
    attributes = rhino3dm.ObjectAttributes()
    attributes.Name = element.Name or element.GlobalId
    attributes.ObjectColor = color
    attributes.ColorSource = rhino3dm.ObjectColorSource.ColorFromObject
    for key, value in _user_strings(element).items():
        attributes.SetUserString(key, value)
    return attributes


class _MeshCache:
    """Meshes of the distinct geometries, in their own coordinates, the least recently used dropped first."""

    def __init__(self):
        self._meshes: OrderedDict[str, rhino3dm.Mesh | None] = OrderedDict()
        self._vertices = 0

    def place(self, shape) -> rhino3dm.Mesh | None:
        """The mesh of a shape, moved to where the shape is."""
        key = shape.geometry.id
        if key in self._meshes:
            self._meshes.move_to_end(key)
            mesh = self._meshes[key]
        else:
            mesh = self._meshes[key] = _mesh(shape.geometry)
            self._vertices += len(mesh.Vertices) if mesh else 0
            while self._vertices > MESH_CACHE_VERTICES and len(self._meshes) > 1:
                dropped = self._meshes.popitem(last=False)[1]
                self._vertices -= len(dropped.Vertices) if dropped else 0
        if mesh is None:
            return None
        mesh = mesh.Duplicate()
        placement = _placement(shape)
        if placement is not None:
            # Like the kernel's world coordinates: points and normals move, the triangles keep
            # their order.
            mesh.Transform(_transform(placement))
        return mesh


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


def _mesh(geometry) -> rhino3dm.Mesh | None:
    """The shape as a mesh, welded across smooth edges."""
    if not geometry.verts or not geometry.faces:
        return None
    points = numpy.frombuffer(geometry.verts_buffer, dtype=numpy.float64).reshape(-1, 3)
    triangles = numpy.frombuffer(geometry.faces_buffer, dtype=numpy.int32).reshape(-1, 3)
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


def _user_strings(element: ifcopenshell.entity_instance) -> dict[str, str]:
    strings = {
        "IfcGlobalId": element.GlobalId,
        "IfcClass": element.is_a(),
        "IfcName": element.Name or "",
    }
    try:
        psets = element_util.get_psets(element, psets_only=True)
        quantities = element_util.get_psets(element, qtos_only=True)
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
            strings[f"{pset}.{prop}"] = str(value)[:MAX_STRING_LENGTH]
    return strings


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
            self._classes[key] = self._add(ifc_class, color[:3] + (255,), self._parents[parent][1])[0]
        return self._classes[key]

    def spatial(self, path: SpatialPath) -> tuple[int, object]:
        key = path[-1].id()
        if key not in self._parents:
            parent_id = self.spatial(path[:-1])[1] if len(path) > 1 else None
            self._parents[key] = self._add(_level_name(path[-1]), (0, 0, 0, 255), parent_id)
        return self._parents[key]

    def _add(self, name: str, color: Color, parent_id) -> tuple[int, object]:
        names = self._names.setdefault(parent_id, set())
        candidate, n = name, 2
        while candidate in names:
            candidate, n = f"{name} ({n})", n + 1
        names.add(candidate)

        layer = rhino3dm.Layer()
        layer.Name = candidate
        layer.Color = color
        if parent_id is not None:
            layer.ParentLayerId = parent_id
        index = self._rhino.Layers.Add(layer)
        return index, self._rhino.Layers.FindIndex(index).Id


def _clean_name(name: str | None, fallback: str) -> str:
    """Make a string usable as a Rhino layer/material name."""
    name = re.sub(r"[\x00-\x1f\x7f]", " ", name or "").replace("::", ":")
    name = name.strip().lstrip("([{}])").strip()
    return name[:MAX_STRING_LENGTH] or fallback
