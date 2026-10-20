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
so dimensions and positions are untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import ifcopenshell

VOXEL = 0.2  # metres; the grid cell of the flood fill
MAX_VOXELS = 60_000_000  # the grid is coarsened until it fits (about 60 MB per boolean grid)
EXPOSURE = 0.05  # share of a product's voxels next to outside air that makes it part of the hull


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
        text = (f"Nur Gebäudehülle: {self.total - self.inside} von {self.total} Bauteilen liegen außen und "
                f"werden umgewandelt, {self.inside} innen liegende weggelassen (Raster {self.voxel:g} m)")
        if self.unknown:
            text += f"; {self.unknown} ohne Vorab-Geometrie sicherheitshalber übernommen"
        return text.replace(".", ",") + "."


def select(
    model: ifcopenshell.file,
    threads: int,
    products: list[ifcopenshell.entity_instance],
    report: Callable[[str, str], None] | None = None,
    progress: Callable[[int], None] | None = None,
) -> Selection:
    """Which of ``products`` are part of the hull; ``progress`` gets 0–100 for the coarse pass."""
    raise NotImplementedError  # TODO lead: see module docstring
