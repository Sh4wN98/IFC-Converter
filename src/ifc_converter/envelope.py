"""Option "Nur Gebäudehülle": only the elements seen from outside are converted.

Interior walls, furniture, fittings, pipes and ducts make up most of a building model's geometry
but nothing of its outside; a context model (Umgebungsmodell) of a neighbouring building needs
only the hull. ``select`` decides which products of a model are part of the hull:

1. A coarse pass computes every product's geometry (hybrid kernel, coarse tolerance) and samples
   its surfaces into cells of VOXEL metres (coarser for very large models, see budgets()).
2. The outside air is found by a flood fill from the border of a grid of FINE times larger cells
   through empty cells; around that outside air, BAND_DEPTH cells deep into the hull, the fill is
   repeated at the sampled resolution, so that gaps narrower than a coarse cell (a reveal under a
   lintel) stay open and what lines them is seen.
3. A product is part of the hull when any of its cells touches outside air (so nothing that is
   left out borders on the outside: the hull stays closed), or when its property set says
   IsExternal = True.

Everything uncertain is kept: products whose geometry the coarse pass could not build, and models
without a closed hull (no roof, say) simply keep more. Products are never changed, only left out,
so dimensions and positions are untouched. Glass counts as opaque: what is behind a window is not
part of the hull.

A model without a closed hull (an architecture part model without its floors and roof, which sit
in the structural model) has outside air everywhere, so the fill leaves out next to nothing. Then
the property sets decide instead (see OPEN_HULL_SHARE): products marked IsExternal = False are left
out, and so are furniture, fittings, building services and ceilings (INTERIOR_CLASSES, INTERIOR_COVERINGS).

A massing volume (a Revit conceptual mass exported as a box around the whole building, a site
modelled as a block) would seal everything inside it. Products that are very simple and span most
of the model (see MASS_TRIANGLES, MASS_SHARE) are therefore not taken as opaque: they are kept
themselves, but the fill looks through them.
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

# The sampled cell, in metres. Only surfaces are sampled, so an element thinner than a cell is a
# single layer of cells: whatever pokes into that layer from inside (a table foot in a 127 mm slab
# on grade) touches the outside air behind it, and a gap narrower than a cell is sealed, hiding what
# is seen through it. 5 cm resolves slabs, walls, roofs and most gaps; glass and cladding stay
# thinner, which only ever keeps more. Large models get coarser cells (budgets()), which again only
# keeps more.
VOXEL = 0.05
# The whole model is filled on a grid of FINE x FINE x FINE sampled cells per grid cell (dense, 1 byte
# per cell for each of two boolean grids); it is coarsened further (doubled) until it fits MAX_VOXELS.
# The sampled resolution is then only used in the band around the outside air.
FINE = 4
BAND_DEPTH = 12  # sampled cells deep into the hull
MAX_VOXELS = 150_000_000
# Share of a product's voxels next to outside air above which it is part of the hull: any of them.
# A threshold would leave out products with a small visible part (a lintel seen through a gap) and
# open the hull there.
EXPOSURE = 0.0
# When the fill leaves out less than this share of the products, the hull is taken as open and the
# property sets decide (a closed building has interior walls, doors and fittings well above it).
OPEN_HULL_SHARE = 0.02
# Left out in a model without a closed hull: furniture and fittings, building services (pipes, ducts,
# cables, terminals, equipment), lifts, fasteners and reinforcement.
INTERIOR_CLASSES = ("IfcFurnishingElement", "IfcDistributionElement", "IfcDistributionPort", "IfcTransportElement",
                    "IfcFastener", "IfcMechanicalFastener", "IfcReinforcingElement", "IfcDiscreteAccessory")
# Coverings of these types are never part of a hull (cladding and roofing are).
INTERIOR_COVERINGS = ("CEILING", "FLOORING", "SKIRTINGBOARD")
# A product with at most this many coarse triangles whose bounding box holds the centres of at
# least this share of all other products is a massing volume: not opaque for the fill. (The model's
# own extent is no yardstick: a terrain dwarfs the building.)
MASS_TRIANGLES = 200
MASS_SHARE = 0.5
# The sampled cells of all products are kept until the grids are built (8 bytes each, packed; about
# 60 bytes each while the exposure is computed); above this many the cell is doubled. Both limits
# grow with the free memory of the PC, see budgets().
MAX_SAMPLED = 20_000_000
MAX_SAMPLED_CAP = 400_000_000
MAX_VOXELS_CAP = 1_000_000_000
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
    voxel: float = VOXEL  # the sampled cell actually used
    coarse: float = VOXEL * FINE  # the cell of the whole-model fill
    exposure: dict[int, float] = field(default_factory=dict)  # product id -> exposed share
    open_hull: bool = False  # the fill found no closed hull: the property sets decided instead
    marked: int = 0  # open hull: products left out as IsExternal = False
    fittings: int = 0  # open hull: products left out by class (INTERIOR_CLASSES, INTERIOR_COVERINGS)
    masses: int = 0  # massing volumes the fill looked through (see MASS_TRIANGLES)
    dropped_classes: dict[str, int] = field(default_factory=dict)  # IFC class -> products left out

    @property
    def note(self) -> str:
        kept = _count(self.total - self.inside)
        voxel = f"{self.voxel:g} m, grob {self.coarse:g}".replace(".", ",")
        if self.open_hull:
            return (f"Nur Gebäudehülle: Das Modell hat keine geschlossene Hülle (fehlendes Dach, fehlende Decken "
                    f"oder Wände, z. B. ein Teilmodell ohne Rohbau): die Außenluft erreicht fast alle Bauteile "
                    f"(Raster {voxel} m). Stattdessen weggelassen: {_count(self.marked)} als innen gekennzeichnete "
                    f"Bauteile (IsExternal = Nein) sowie {_count(self.fittings)} Möbel, Einrichtungen, Leitungen, "
                    f"Decken- und Bodenbeläge; {kept} von {_count(self.total)} Bauteilen werden umgewandelt."
                    + self.dropped_text)
        text = (f"Nur Gebäudehülle: {kept} von {_count(self.total)} Bauteilen liegen außen und werden umgewandelt, "
                f"{_count(self.inside)} innen liegende weggelassen (Raster {voxel} m)")
        if self.unknown:
            text += f"; {_count(self.unknown)} ohne Vorab-Geometrie sicherheitshalber übernommen"
        if self.flagged:
            text += f"; {_count(self.flagged)} als außen gekennzeichnete (IsExternal) übernommen"
        if self.masses:
            text += f"; {_count(self.masses)} Baumassen (Hüllkörper um das Modell) nicht als undurchsichtig gewertet"
        return text + "." + self.dropped_text

    @property
    def dropped_text(self) -> str:
        """" Weggelassen: 34 IfcWallStandardCase, 16 IfcSlab, …" (the eight largest classes)."""
        if not self.dropped_classes:
            return ""
        ranked = sorted(self.dropped_classes.items(), key=lambda item: (-item[1], item[0]))
        parts = [f"{_count(number)} {name}" for name, number in ranked[:8]]
        if len(ranked) > 8:
            parts.append(f"{_count(sum(number for _, number in ranked[8:]))} weitere")
        return " Weggelassen: " + ", ".join(parts) + "."


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
    sampler = _Sampler(VOXEL, *budgets())
    for shape in _coarse_shapes(model, threads, products, report, progress):
        sampler.add(shape)
    coarse_seconds = time.monotonic() - started
    if report:
        report("envelope", "Gebäudehülle wird bestimmt (Außenluft wird gesucht) …")
    exposure = sampler.exposure()
    selection.voxel, selection.coarse = sampler.voxel, sampler.coarse
    selection.exposure = exposure
    selection.masses = len(sampler.masses)
    marks = external_marks(model)
    for product_id in ids:
        share = exposure.get(product_id)
        if share is None:
            selection.unknown += 1
            selection.keep.add(product_id)
        elif share > EXPOSURE:
            selection.keep.add(product_id)
        elif marks.get(product_id):
            selection.flagged += 1
            selection.keep.add(product_id)
        else:
            selection.inside += 1
    if selection.inside < OPEN_HULL_SHARE * selection.total:
        _select_by_marks(selection, products, marks)
    for product in products:
        if product.id() not in selection.keep:
            selection.dropped_classes[product.is_a()] = selection.dropped_classes.get(product.is_a(), 0) + 1
    converter._release_memory()
    log.info("Gebäudehülle: %d von %d Bauteilen außen (%d ohne Vorab-Geometrie, %d per IsExternal), Raster %g m "
             "(grob %g m, %d Zellen, feiner Saum %d Zellen), Vorab-Geometrie %.0f s, Hülle %.0f s",
             len(selection.keep), selection.total, selection.unknown, selection.flagged, sampler.voxel,
             sampler.coarse, sampler.cells, sampler.band_cells, coarse_seconds,
             time.monotonic() - started - coarse_seconds)
    return selection


def budgets() -> tuple[int, int]:
    """(sampled cells, grid cells) the PC can afford: the defaults, more with more free memory."""
    available = converter.available_memory() or 0
    return (min(MAX_SAMPLED_CAP, max(MAX_SAMPLED, available // 150)),
            min(MAX_VOXELS_CAP, max(MAX_VOXELS, available // 40)))


def _select_by_marks(selection: Selection, products: list, marks: dict[int, bool]) -> None:
    """The hull is open: keep everything except what is marked or furnished as interior."""
    selection.open_hull = True
    selection.keep, selection.inside, selection.unknown, selection.flagged = set(), 0, 0, 0
    for product in products:
        if marks.get(product.id()) is False:
            selection.marked += 1
        elif any(product.is_a(name) for name in INTERIOR_CLASSES) or (
                product.is_a("IfcCovering") and getattr(product, "PredefinedType", None) in INTERIOR_COVERINGS):
            selection.fittings += 1
        else:
            selection.keep.add(product.id())
    selection.inside = selection.marked + selection.fittings


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

    def __init__(self, voxel: float, max_sampled: int = MAX_SAMPLED, max_voxels: int = MAX_VOXELS):
        self.voxel = voxel
        self.coarse = voxel * FINE
        self.max_sampled = max_sampled
        self.max_voxels = max_voxels
        self.origin: numpy.ndarray | None = None  # the first point; cell coordinates are relative to it
        self.keys: dict[int, numpy.ndarray] = {}  # product id -> packed cell coordinates (int64)
        self.triangles: dict[int, int] = {}  # product id -> coarse triangles
        self.unknown: set[int] = set()  # products placed too far away to sample
        self.masses: set[int] = set()  # massing volumes, see exposure()
        self.cells = 0  # cells of the whole-model grid
        self.band_cells = 0  # sampled cells of the band around the outside air
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
        # Points on a cell boundary (storey levels are) count up, also when rounding left them
        # a billionth below it: a table at z = -1e-15 does not reach into the slab's cells.
        cells = numpy.floor((samples - self.origin) / self.voxel + 1e-6).astype(numpy.int64)
        if (numpy.abs(cells) >= _RANGE).any():
            self.unknown.add(shape.id)
            return
        keys = numpy.unique(_pack(cells))
        self.keys[shape.id] = keys
        self.triangles[shape.id] = len(triangles)
        self._stored += len(keys)
        if self._stored > self.max_sampled:
            self._coarsen()

    def _coarsen(self) -> None:
        """Double the grid cell, re-quantising what is stored (the lead-in of very large models)."""
        self.voxel *= 2
        self.coarse = self.voxel * FINE
        self._stored = 0
        for product_id, keys in self.keys.items():
            keys = numpy.unique(_pack(numpy.floor_divide(_unpack(keys), 2)))
            self.keys[product_id] = keys
            self._stored += len(keys)
        log.info("Gebäudehülle: Raster auf %g m vergröbert (%d Rasterzellen gespeichert)", self.voxel, self._stored)

    def exposure(self) -> dict[int, float]:
        """Product id -> share of its cells next to outside air; sampled products only."""
        if not self.keys:
            return {}
        owners = numpy.concatenate([numpy.full(len(keys), index, numpy.int32)
                                    for index, keys in enumerate(self.keys.values())])
        # Cell coordinates fit int32 (within ±2^20 of the origin, see _RANGE); unpacked per product
        # so that the int64 triples never exist for all cells at once.
        fine = numpy.concatenate([_unpack(keys).astype(numpy.int32) for keys in self.keys.values()])
        fine -= fine.min(axis=0)
        factor = FINE
        extent = fine.max(axis=0)
        while numpy.prod(extent // factor + 5) > self.max_voxels and factor < extent.max():
            factor *= 2
        self.coarse = self.voxel * factor
        # Two empty cells around the model: the outermost ring is the border the fill starts from,
        # the next one keeps every product away from it.
        coarse = fine // factor + 2
        local = (fine - (coarse - 2) * factor).astype(numpy.uint8 if factor < 256 else numpy.int32)
        del fine
        shape = tuple(int(n) for n in coarse.max(axis=0) + 3)
        self.cells = int(numpy.prod(shape))
        flat = numpy.ravel_multi_index((coarse[:, 0], coarse[:, 1], coarse[:, 2]), shape)
        # Massing volumes: simple products holding most of the other products are not opaque.
        count = len(self.keys)
        lows = numpy.full((count, 3), numpy.iinfo(numpy.int64).max)
        highs = numpy.full((count, 3), numpy.iinfo(numpy.int64).min)
        numpy.minimum.at(lows, owners, coarse)
        numpy.maximum.at(highs, owners, coarse)
        centres = (lows + highs) / 2
        opaque = numpy.ones(len(flat), dtype=bool)
        if count > 1:
            for index, product_id in enumerate(self.keys):
                if self.triangles[product_id] > MASS_TRIANGLES:
                    continue
                held = ((centres >= lows[index]) & (centres <= highs[index])).all(axis=1).sum() - 1
                if held >= MASS_SHARE * (count - 1):
                    self.masses.add(product_id)
                    opaque[owners == index] = False
        del coarse, lows, highs, centres
        solid = numpy.zeros(self.cells, dtype=bool)
        solid[flat[opaque]] = True
        outside = _outside(solid.reshape(shape)).ravel()
        # Seen from outside: cells lying in outside air of the whole-model grid (a mass), and
        # cells next to outside air at the sampled resolution. The whole-model grid alone would be
        # too coarse for that: an interior wall meeting an exterior wall thinner than its cell
        # would count as exposed through it.
        exposed = outside[flat].copy()
        # The band around the outside air, refined to the sampled cells: gaps narrower than a
        # coarse cell stay open there, and what lines them is seen.
        near = outside.reshape(shape)
        for _ in range(max(1, -(-BAND_DEPTH // factor))):
            near = _dilated(near)
        band = numpy.flatnonzero(near.ravel() & solid)
        del near, solid
        if band.size:
            position = numpy.searchsorted(band, flat)
            in_band = (position < band.size) & (band[numpy.minimum(position, band.size - 1)] == flat)
            fine_ids = (position * factor ** 3 + local[:, 0].astype(numpy.int64) * factor * factor
                        + local[:, 1] * factor + local[:, 2])
            del position, local, flat
            domain = _Band(band, shape, outside, factor)
            self.band_cells = domain.size
            fine_solid = numpy.zeros(domain.size, dtype=bool)
            fine_solid[fine_ids[in_band & opaque]] = True
            fine_outside = domain.outside(fine_solid)
            del fine_solid
            exposed[in_band] |= domain.touching(fine_ids[in_band], fine_outside)
        counts = numpy.bincount(owners, minlength=len(self.keys))
        exposed_counts = numpy.bincount(owners, weights=exposed, minlength=len(self.keys))
        return {product_id: float(exposed_counts[index] / counts[index])
                for index, product_id in enumerate(self.keys)}


class _Band:
    """The sampled cells of the solid grid cells within the band around the outside air: a sparse
    fine grid, addressed as band position * factor³ + local offset."""

    CHUNK = 4_000_000

    def __init__(self, band: numpy.ndarray, shape: tuple, outside: numpy.ndarray, factor: int):
        self.band = band  # sorted flat indices of the grid cells in the band
        self.air = outside  # outside air of the whole-model grid, flat
        self.factor = factor
        self.strides = (shape[1] * shape[2], shape[2], 1)
        self.local_strides = (factor * factor, factor, 1)
        self.size = band.size * factor ** 3

    def neighbours(self, ids: numpy.ndarray, with_source: bool = True) -> tuple:
        """(neighbour ids within the band, the index of their cell in ``ids`` (None unless
        ``with_source``), whether a cell of ``ids`` borders on outside air of the whole-model grid)."""
        factor, cube = self.factor, self.factor ** 3
        position, local = ids // cube, ids % cube
        found, source = [], []
        at_outside = numpy.zeros(len(ids), dtype=bool)
        for axis in range(3):
            along = (local // self.local_strides[axis]) % factor
            for step in (1, -1):
                inside = (along + step >= 0) & (along + step < factor)
                found.append(ids[inside] + step * self.local_strides[axis])
                if with_source:
                    source.append(numpy.flatnonzero(inside))
                crossing = numpy.flatnonzero(~inside)
                if not crossing.size:
                    continue
                cell = self.band[position[crossing]] + step * self.strides[axis]
                at_outside[crossing] |= self.air[cell]
                where = numpy.searchsorted(self.band, cell)
                hit = (where < self.band.size) & (self.band[numpy.minimum(where, self.band.size - 1)] == cell)
                wrapped = local[crossing[hit]] - step * (factor - 1) * self.local_strides[axis]
                found.append(where[hit] * cube + wrapped)
                if with_source:
                    source.append(crossing[hit])
        return numpy.concatenate(found), numpy.concatenate(source) if with_source else None, at_outside

    def outside(self, fine_solid: numpy.ndarray) -> numpy.ndarray:
        """The free sampled cells of the band reachable from the outside air of the whole-model
        grid (a flood fill seeded on the faces towards it)."""
        factor, cube = self.factor, self.factor ** 3
        local = numpy.arange(cube)
        visited = numpy.zeros(self.size, dtype=bool)
        for axis in range(3):
            along = (local // self.local_strides[axis]) % factor
            for step in (1, -1):
                touching = numpy.flatnonzero(self.air[self.band + step * self.strides[axis]])
                face = numpy.flatnonzero(along == (factor - 1 if step == 1 else 0))
                for start in range(0, touching.size, self.CHUNK // cube):
                    seeds = (touching[start:start + self.CHUNK // cube, None] * cube + face[None, :]).ravel()
                    visited[seeds[~fine_solid[seeds]]] = True
        frontier = numpy.flatnonzero(visited)
        while frontier.size:
            # Chunked: the first fronts (all faces towards the outside air) are large.
            grown = []
            for start in range(0, frontier.size, self.CHUNK):
                found, _, _ = self.neighbours(frontier[start:start + self.CHUNK], with_source=False)
                found = numpy.unique(found[~fine_solid[found] & ~visited[found]])
                visited[found] = True
                grown.append(found)
            frontier = numpy.concatenate(grown)
        return visited

    def touching(self, ids: numpy.ndarray, fine_outside: numpy.ndarray) -> numpy.ndarray:
        """Whether each of the sampled cells ``ids`` borders on outside air (fine or coarse)."""
        result = numpy.zeros(len(ids), dtype=bool)
        for start in range(0, len(ids), self.CHUNK):
            chunk = ids[start:start + self.CHUNK]
            found, source, at_outside = self.neighbours(chunk)
            hits = numpy.bincount(source, weights=fine_outside[found], minlength=len(chunk)) > 0
            result[start:start + self.CHUNK] = hits | at_outside
        return result


def _dilated(mask: numpy.ndarray) -> numpy.ndarray:
    """``mask`` grown by one cell in the six directions (the outermost layer stays as it is)."""
    grown = mask.copy()
    grown[1:, :, :] |= mask[:-1, :, :]
    grown[:-1, :, :] |= mask[1:, :, :]
    grown[:, 1:, :] |= mask[:, :-1, :]
    grown[:, :-1, :] |= mask[:, 1:, :]
    grown[:, :, 1:] |= mask[:, :, :-1]
    grown[:, :, :-1] |= mask[:, :, 1:]
    return grown


def _surface_points(a: numpy.ndarray, b: numpy.ndarray, c: numpy.ndarray, spacing: float) -> numpy.ndarray:
    """Points on the triangles (a, b, c) at most ``spacing`` apart: a lattice along the two shorter
    edges of each triangle, subdivided so that no two neighbours are further apart than that along
    either (on the longest edge at most twice that, still within a cell). Triangles are grouped by
    their two subdivision counts, each rounded up to a power of two."""
    corners = numpy.stack([a, b, c], axis=1)  # (n, 3 corners, xyz)
    opposite = numpy.stack([numpy.linalg.norm(b - c, axis=1), numpy.linalg.norm(c - a, axis=1),
                            numpy.linalg.norm(a - b, axis=1)], axis=1)
    # The corner opposite the longest edge comes first, so the lattice runs along the shorter edges.
    first = opposite.argmax(axis=1)
    order = (first[:, None] + numpy.arange(3)[None, :]) % 3
    corners = numpy.take_along_axis(corners, order[:, :, None], axis=1)
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    along_b = numpy.linalg.norm(b - a, axis=1)
    along_c = numpy.linalg.norm(c - a, axis=1)
    cap = 1 << 20
    needed_b = numpy.clip(numpy.ceil(along_b / spacing), 1, cap)
    needed_c = numpy.clip(numpy.ceil(along_c / spacing), 1, cap)
    expected = ((needed_b + 1) * (needed_c + 1) / 2).sum()
    if expected > MAX_POINTS:  # a huge product: coarser, see MAX_POINTS
        scale = numpy.sqrt(MAX_POINTS / expected)
        needed_b = numpy.maximum(1, numpy.ceil(needed_b * scale))
        needed_c = numpy.maximum(1, numpy.ceil(needed_c * scale))
    levels_b = numpy.ceil(numpy.log2(needed_b)).astype(numpy.int64)
    levels_c = numpy.ceil(numpy.log2(needed_c)).astype(numpy.int64)
    groups = levels_b * 32 + levels_c
    result = []
    for group in numpy.unique(groups):
        n_b, n_c = 1 << int(group // 32), 1 << int(group % 32)
        i, j = numpy.meshgrid(numpy.arange(n_b + 1), numpy.arange(n_c + 1), indexing="ij")
        u, v = (i / n_b).ravel(), (j / n_c).ravel()
        inside = u + v <= 1 + 1e-9
        u, v = u[inside][None, :, None], v[inside][None, :, None]
        chosen = groups == group
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
    return {product_id for product_id, external in external_marks(model).items() if external}


def external_marks(model: ifcopenshell.file) -> dict[int, bool]:
    """Product id -> its IsExternal property, from its own property sets or those of its type (an own
    one wins)."""
    own: dict[int, bool] = {}
    typed: dict[int, bool] = {}
    for prop in model.by_type("IfcPropertySingleValue"):
        if prop.Name != "IsExternal":
            continue
        value = prop.NominalValue
        if value is None or getattr(value, "wrappedValue", None) is None:
            continue
        external = bool(value.wrappedValue)
        for pset in model.get_inverse(prop):
            if not pset.is_a("IfcPropertySet"):
                continue
            for owner in model.get_inverse(pset):
                if owner.is_a("IfcRelDefinesByProperties"):
                    own.update((product.id(), external) for product in owner.RelatedObjects)
                elif owner.is_a("IfcTypeObject"):
                    for rel in getattr(owner, "ObjectTypeOf", None) or getattr(owner, "Types", None) or ():
                        typed.update((product.id(), external) for product in rel.RelatedObjects)
    return {**typed, **own}
