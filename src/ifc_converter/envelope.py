"""Option "Nur Gebäudehülle": only the elements seen from outside are converted.

Interior walls, furniture, fittings, pipes and ducts make up most of a building model's geometry
but nothing of its outside; a context model (Umgebungsmodell) of a neighbouring building needs
only the hull. ``select`` decides which products of a model are part of the hull:

1. A coarse pass computes every product's geometry (hybrid kernel, coarse tolerance) and samples
   its surfaces into a voxel grid of VOXEL metres (coarser for very large models, see MAX_VOXELS).
2. The outside air is found by a flood fill from the grid's border through empty voxels.
3. A product is part of the hull when a share of at least EXPOSURE of its voxels touches outside
   air, or when its property set says IsExternal = True.

Everything uncertain is kept: products whose geometry the coarse pass could not build, and models
without a closed hull (no roof, say) simply keep more. Products are never changed, only left out,
so dimensions and positions are untouched. Glass counts as opaque: what is behind a window is not
part of the hull.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import ifcopenshell
import ifcopenshell.geom as geom
import numpy

from ifc_converter import converter

log = logging.getLogger(__name__)

VOXEL = 0.2  # metres; the grid cell of the flood fill
# The grid is coarsened (cell doubled) until it fits: 1 byte per cell for each of two boolean grids.
# A coarser grid keeps more: an interior wall meeting an exterior wall thinner than a cell looks
# exposed through it, so the grid is only coarsened for models whose grid is really large.
MAX_VOXELS = 150_000_000
EXPOSURE = 0.05  # share of a product's voxels next to outside air that makes it part of the hull
# The sampled voxels of all products are kept until the grid is built (8 bytes each, packed; about
# three times that while the exposure is computed); above this many the grid cell is doubled.
MAX_SAMPLED = 30_000_000
# A single product (a terrain, say) is sampled with at most this many points per call; beyond that
# its sampling gets coarser, which can let outside air leak in: more is kept, never less.
MAX_POINTS = 4_000_000
# The coarse pass's mesh tolerances: 5 cm chords are well below the grid cell.
LINEAR_DEFLECTION = 0.05
ANGULAR_DEFLECTION = 0.5
# Voxel coordinates relative to the first sampled point are packed into 21 bits each: ±200 km at
# VOXEL; a product further away than that (broken placement) is kept as unknown.
_BITS = 21
_RANGE = 1 << (_BITS - 1)


@dataclass
class Selection:
    keep: set[int]  # ids of the products that are part of the hull (and of those kept to be safe)
    total: int = 0  # products examined
    inside: int = 0  # products left out as interior
    unknown: int = 0  # products without geometry in the coarse pass, kept to be safe
    flagged: int = 0  # products kept because IsExternal = True although not exposed
    voxel: float = VOXEL  # the grid cell actually used
    exposure: dict[int, float] = field(default_factory=dict)  # product id -> exposed share

    @property
    def note(self) -> str:
        kept, voxel = _count(self.total - self.inside), f"{self.voxel:g}".replace(".", ",")
        text = (f"Nur Gebäudehülle: {kept} von {_count(self.total)} Bauteilen liegen außen und werden umgewandelt, "
                f"{_count(self.inside)} innen liegende weggelassen (Raster {voxel} m)")
        if self.unknown:
            text += f"; {_count(self.unknown)} ohne Vorab-Geometrie sicherheitshalber übernommen"
        if self.flagged:
            text += f"; {_count(self.flagged)} als außen gekennzeichnete (IsExternal) übernommen"
        if self.total and not self.inside:
            text += "; das Modell hat anscheinend keine geschlossene Hülle (fehlendes Dach oder fehlende Wände?)"
        return text + "."


def _count(number: int) -> str:
    return f"{number:,}".replace(",", ".")

def select(
    model: ifcopenshell.file,
    threads: int,
    products: list[ifcopenshell.entity_instance],
    report: Callable[[str, str], None] | None = None,
    progress: Callable[[int], None] | None = None,
) -> Selection:
    """Which of ``products`` are part of the hull; ``progress`` gets 0–100 for the coarse pass."""
    started = time.monotonic()
    ids = {product.id() for product in products}
    selection = Selection(keep=set(), total=len(products))
    if not products:
        return selection
    sampler = _Sampler(VOXEL)
    for shape in _coarse_shapes(model, threads, products, report, progress):
        sampler.add(shape)
    coarse_seconds = time.monotonic() - started
    if report:
        report("envelope", "Gebäudehülle wird bestimmt (Außenluft wird gesucht) …")
    exposure = sampler.exposure()
    selection.voxel = sampler.voxel
    selection.exposure = exposure
    flagged = external_flags(model) & ids
    for product_id in ids:
        share = exposure.get(product_id)
        if share is None:
            selection.unknown += 1
            selection.keep.add(product_id)
        elif share >= EXPOSURE:
            selection.keep.add(product_id)
        elif product_id in flagged:
            selection.flagged += 1
            selection.keep.add(product_id)
        else:
            selection.inside += 1
    converter._release_memory()
    log.info("Gebäudehülle: %d von %d Bauteilen außen (%d ohne Vorab-Geometrie, %d per IsExternal), Raster %g m, "
             "%d Rasterzellen, Vorab-Geometrie %.0f s, Hülle %.0f s", len(selection.keep), selection.total,
             selection.unknown, selection.flagged, sampler.voxel, sampler.cells, coarse_seconds,
             time.monotonic() - started - coarse_seconds)
    return selection


def _coarse_shapes(model, threads: int, products: list, report, progress):
    """The products' shapes from the coarse pass: hybrid kernel (unless OpenCASCADE was chosen
    outright), coarse tolerance, world coordinates; nothing of it counts as the conversion's
    (no checkpoint, no candidates, no second attempts, no "without geometry")."""
    settings = geom.settings()
    settings.set("mesher-linear-deflection", LINEAR_DEFLECTION)
    settings.set("mesher-angular-deflection", ANGULAR_DEFLECTION)
    settings.set("use-world-coords", True)
    settings.set("no-normals", True)
    kernel = converter.kernel_strategy()
    tokens = [
        converter._kernel.set("hybrid" if kernel != "opencascade" else kernel),
        converter._checkpoint.set(None), converter._candidates.set(None), converter._missing.set(None),
    ]

    def status(phase: str, text: str) -> None:
        # The coarse pass's own phases would read like the conversion's; its notes and deep products
        # are worth seeing.
        if report and phase in ("note", "deep"):
            report(phase, text)

    try:
        yield from converter.iter_shapes(
            model, settings, threads, converter.EXCLUDED_CLASSES, progress, 100, products, status=status,
            second_attempts=False,
        )
    finally:
        for variable, token in zip((converter._kernel, converter._checkpoint, converter._candidates, converter._missing),
                                   tokens):
            variable.reset(token)


class _Sampler:
    """Collects, per product, the voxels its surfaces pass through, and finds the ones next to
    outside air once all products are in."""

    def __init__(self, voxel: float):
        self.voxel = voxel
        self.origin: numpy.ndarray | None = None  # the first point; voxel coordinates are relative to it
        self.keys: dict[int, numpy.ndarray] = {}  # product id -> packed voxel coordinates (int64)
        self.unknown: set[int] = set()  # products placed too far away to sample
        self.cells = 0
        self._stored = 0

    def add(self, shape) -> None:
        geometry = shape.geometry
        triangles = numpy.frombuffer(geometry.faces_buffer, dtype=numpy.int32).reshape(-1, 3)
        if not len(triangles):  # curves or points only: no surface to see
            return
        points = numpy.frombuffer(geometry.verts_buffer, dtype=numpy.float64).reshape(-1, 3)
        if not numpy.isfinite(points).all():
            self.unknown.add(shape.id)
            return
        if self.origin is None:
            self.origin = numpy.floor(points[0] / self.voxel) * self.voxel
        samples = _surface_points(points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]],
                                  self.voxel / 2)
        cells = numpy.floor((samples - self.origin) / self.voxel).astype(numpy.int64)
        if (numpy.abs(cells) >= _RANGE).any():
            self.unknown.add(shape.id)
            return
        keys = numpy.unique(_pack(cells))
        self.keys[shape.id] = keys
        self._stored += len(keys)
        if self._stored > MAX_SAMPLED:
            self._coarsen()

    def _coarsen(self) -> None:
        """Double the grid cell, re-quantising what is stored (the lead-in of very large models)."""
        self.voxel *= 2
        self._stored = 0
        for product_id, keys in self.keys.items():
            keys = numpy.unique(_pack(numpy.floor_divide(_unpack(keys), 2)))
            self.keys[product_id] = keys
            self._stored += len(keys)
        log.info("Gebäudehülle: Raster auf %g m vergröbert (%d Rasterzellen gespeichert)", self.voxel, self._stored)

    def exposure(self) -> dict[int, float]:
        """Product id -> share of its voxels next to outside air; sampled products only."""
        if not self.keys:
            return {}
        owners = numpy.concatenate([numpy.full(len(keys), index, numpy.int32)
                                    for index, keys in enumerate(self.keys.values())])
        cells = _unpack(numpy.concatenate(list(self.keys.values())))
        low, high = cells.min(axis=0), cells.max(axis=0)
        factor = 1
        while numpy.prod((high - low) // factor + 5) > MAX_VOXELS:
            factor *= 2
        if factor > 1:
            cells = numpy.floor_divide(cells, factor)
            low, high = cells.min(axis=0), cells.max(axis=0)
            self.voxel *= factor
            log.info("Gebäudehülle: Raster für die Füllung auf %g m vergröbert", self.voxel)
        # Two empty cells around the model: the outermost ring is the border the fill starts from,
        # the next one keeps every product away from it.
        shape = tuple(int(n) for n in high - low + 5)
        cells = cells - low + 2
        self.cells = int(numpy.prod(shape))
        flat = numpy.ravel_multi_index((cells[:, 0], cells[:, 1], cells[:, 2]), shape)
        del cells
        solid = numpy.zeros(self.cells, dtype=bool)
        solid[flat] = True
        outside = _outside(solid.reshape(shape)).ravel()
        del solid
        exposed = numpy.zeros(len(flat), dtype=bool)
        for stride in (shape[1] * shape[2], shape[2], 1):
            for step in (stride, -stride):
                exposed |= outside[flat + step]
        counts = numpy.bincount(owners, minlength=len(self.keys))
        exposed_counts = numpy.bincount(owners, weights=exposed, minlength=len(self.keys))
        return {product_id: float(exposed_counts[index] / counts[index])
                for index, product_id in enumerate(self.keys)}


def _surface_points(a: numpy.ndarray, b: numpy.ndarray, c: numpy.ndarray, spacing: float) -> numpy.ndarray:
    """Points on the triangles (a, b, c) at most ``spacing`` apart (a barycentric lattice), so that
    every voxel a triangle passes through gets a point. Triangles are grouped by the number of
    subdivisions, rounded up to a power of two."""
    edges = numpy.maximum.reduce([numpy.linalg.norm(b - a, axis=1), numpy.linalg.norm(c - b, axis=1),
                                  numpy.linalg.norm(a - c, axis=1)])
    needed = numpy.ceil(edges / spacing)
    needed = numpy.maximum(1, numpy.minimum(needed, 1 << 20))
    expected = ((needed + 1) * (needed + 2) / 2).sum()
    if expected > MAX_POINTS:  # a huge product: coarser, see MAX_POINTS
        needed = numpy.maximum(1, numpy.ceil(needed * numpy.sqrt(MAX_POINTS / expected)))
    levels = numpy.ceil(numpy.log2(needed)).astype(numpy.int64)
    result = []
    for level in numpy.unique(levels):
        n = 1 << int(level)
        i, j = numpy.triu_indices(n + 1)  # i + j <= n ... as (i, n - j) below
        i, j = i, n - j
        u = (i / n)[None, :, None]
        v = (j / n)[None, :, None]
        chosen = levels == level
        points = a[chosen, None, :] * (1 - u - v) + b[chosen, None, :] * u + c[chosen, None, :] * v
        result.append(points.reshape(-1, 3))
    return numpy.concatenate(result)


def _pack(cells: numpy.ndarray) -> numpy.ndarray:
    shifted = cells + _RANGE
    return (shifted[:, 0] << (2 * _BITS)) | (shifted[:, 1] << _BITS) | shifted[:, 2]


def _unpack(keys: numpy.ndarray) -> numpy.ndarray:
    mask = (1 << _BITS) - 1
    return numpy.stack([(keys >> (2 * _BITS)) & mask, (keys >> _BITS) & mask, keys & mask], axis=1) - _RANGE


def _outside(solid: numpy.ndarray) -> numpy.ndarray:
    """The empty cells connected to the border of ``solid`` (whose outermost ring is empty):
    a breadth-first flood fill over flat indices, six-connected."""
    shape = solid.shape
    free = ~solid.ravel()
    # The outermost ring is marked outside without being visited: its neighbours would leave the
    # array. The fill starts from the ring inside it.
    outside = numpy.ones(shape, dtype=bool)
    outside[1:-1, 1:-1, 1:-1] = False
    second = numpy.zeros(shape, dtype=bool)
    second[1:-1, 1:-1, 1:-1] = True
    second[2:-2, 2:-2, 2:-2] = False
    frontier = numpy.flatnonzero(second)
    del second
    outside = outside.ravel()
    outside[frontier] = True
    strides = (shape[1] * shape[2], shape[2], 1)
    while frontier.size:
        neighbours = numpy.concatenate([frontier + step for stride in strides for step in (stride, -stride)])
        neighbours = neighbours[free[neighbours] & ~outside[neighbours]]
        frontier = numpy.unique(neighbours)
        outside[frontier] = True
    return outside.reshape(shape)


def external_flags(model: ifcopenshell.file) -> set[int]:
    """The ids of the products whose property sets (own or of their type) say IsExternal = True."""
    flagged: set[int] = set()
    for prop in model.by_type("IfcPropertySingleValue"):
        if prop.Name != "IsExternal":
            continue
        value = prop.NominalValue
        if value is None or not getattr(value, "wrappedValue", False):
            continue
        for pset in model.get_inverse(prop):
            if not pset.is_a("IfcPropertySet"):
                continue
            for owner in model.get_inverse(pset):
                if owner.is_a("IfcRelDefinesByProperties"):
                    flagged.update(product.id() for product in owner.RelatedObjects)
                elif owner.is_a("IfcTypeObject"):
                    for rel in getattr(owner, "ObjectTypeOf", None) or getattr(owner, "Types", None) or ():
                        flagged.update(product.id() for product in rel.RelatedObjects)
    return flagged
