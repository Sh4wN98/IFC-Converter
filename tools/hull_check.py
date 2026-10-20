"""Validate the option "Nur Gebäudehülle" (envelope.select) on real IFC models.

For every model the products the conversion would compute (converter.shape_products) are listed
with class, GlobalId, name, storey and the IsExternal value of their Pset_*Common (own or type
property set), envelope.select decides which of them are part of the hull, and both are compared:
a confusion matrix IsExternal x kept/dropped, counts per class, the distribution of the exposure
shares, the products flagged external that are not exposed (kept because of the flag) and the
products flagged internal that are exposed (kept: are they really visible from outside?), and all
dropped products per class, as the only serious error is a hull element left out.

    python tools/hull_check.py files/duplex.ifc files/revit_arc.ifc --out-dir out/hull-qa --threads 4
    python tools/hull_check.py files/duplex.ifc --measure obj,3dm-mesh    # output size and time with/without
    python tools/hull_check.py files/duplex.ifc --render                  # PNGs of the kept and dropped products

Per model <out-dir>/<model>.json and <model>.md are written; ``--measure`` converts the model with
and without ``envelope=True`` and records file size, element counts and seconds; ``--render`` computes
coarse meshes of all products and draws the kept and the dropped set from several sides into PNGs
(a small z-buffer rasterizer of its own, no graphics libraries needed). ``--fake-select`` stands in
for envelope.select while it is not implemented (keeps everything).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import struct
import sys
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as geom
import ifcopenshell.util.element
import numpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ifc_converter import converter, envelope  # noqa: E402

# Measurement modes: name -> (format, Rhino geometry).
MEASURE_MODES = {"obj": ("obj", "brep"), "glb": ("glb", "brep"), "3dm-mesh": ("3dm", "mesh"), "3dm-brep": ("3dm", "brep")}
# Upper edges of the exposure histogram buckets (share of a product's voxels next to outside air).
EXPOSURE_EDGES = (0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)
# Thresholds tried for the sweep: how many products exposure alone would keep at each.
SWEEP_THRESHOLDS = (0.005, 0.01, 0.02, 0.03, 0.05, 0.1, 0.2)
# Example GlobalIds listed per class in the Markdown summary.
EXAMPLES = 6
# Rendering: image size, the coarse tessellation and the sample budget of the rasterizer.
IMAGE_SIZE = (960, 720)
RENDER_LINEAR_DEFLECTION = 0.02
RENDER_ANGULAR_DEFLECTION = 0.8
MAX_SAMPLES = 6_000_000
# Views: name -> (azimuth about Z in degrees, elevation above the horizon in degrees).
VIEWS = {
    "top": (0.0, 90.0),
    "south": (0.0, 0.0),
    "east": (90.0, 0.0),
    "north": (180.0, 0.0),
    "west": (270.0, 0.0),
    "iso-sw": (-45.0, 30.0),
    "iso-ne": (135.0, 30.0),
}
# Colours per class group, so that roofs, windows or furniture are told apart at a glance.
CLASS_COLORS = {
    "IfcWall": (205, 195, 175), "IfcWallStandardCase": (205, 195, 175), "IfcWallElementedCase": (205, 195, 175),
    "IfcCurtainWall": (120, 170, 220),
    "IfcSlab": (150, 150, 165), "IfcSlabStandardCase": (150, 150, 165), "IfcSlabElementedCase": (150, 150, 165),
    "IfcRoof": (180, 70, 60), "IfcWindow": (90, 150, 230), "IfcDoor": (190, 120, 60),
    "IfcColumn": (120, 120, 125), "IfcBeam": (120, 120, 125), "IfcMember": (130, 130, 135),
    "IfcPlate": (140, 160, 190), "IfcFooting": (110, 100, 95), "IfcPile": (110, 100, 95),
    "IfcStair": (230, 160, 60), "IfcStairFlight": (230, 160, 60), "IfcRamp": (230, 160, 60),
    "IfcRampFlight": (230, 160, 60), "IfcRailing": (235, 190, 90),
    "IfcFurnishingElement": (165, 100, 165), "IfcFurniture": (165, 100, 165), "IfcSystemFurnitureElement": (165, 100, 165),
    "IfcBuildingElementProxy": (120, 175, 120), "IfcCovering": (225, 215, 195), "IfcCovering.CEILING": (225, 215, 195),
    "IfcSite": (140, 170, 100), "IfcGeographicElement": (140, 170, 100),
    "IfcShadingDevice": (200, 140, 80), "IfcChimney": (150, 90, 80),
}
MEP_COLOR = (60, 170, 170)
# Terrain is left out of the images' frame: a site mesh is often 10x the building.
TERRAIN_CLASSES = ("IfcSite", "IfcGeographicElement")
DEFAULT_COLOR = (180, 180, 180)
BACKGROUND = (255, 255, 255)


# ------------------------------------------------------------------------------------ inventory


@dataclass
class Row:
    """One product of the model as the conversion sees it."""

    id: int
    ifc_class: str
    guid: str
    name: str
    storey: str
    external: bool | None  # IsExternal of its Pset_*Common (own or type), None if there is none
    kept: bool = True
    exposure: float | None = None  # share of its voxels next to outside air, None if no coarse geometry

    def as_dict(self) -> dict:
        return {
            "id": self.id, "class": self.ifc_class, "guid": self.guid, "name": self.name, "storey": self.storey,
            "external": self.external, "kept": self.kept,
            "exposure": None if self.exposure is None else round(self.exposure, 4),
        }


def open_model(path: Path) -> ifcopenshell.file:
    """Open ``path`` the way convert() does (units, extrusions and projects repaired)."""
    model = ifcopenshell.open(str(path))
    converter.repair_units(model)
    converter.repair_extrusions(model)
    converter.merge_projects(model)
    return model


def is_external(product: ifcopenshell.entity_instance) -> bool | None:
    """IsExternal of the product's Pset_*Common, from its own property sets or its type's; None if
    neither says. Any other property set with an IsExternal property counts when no Common set has it."""
    try:
        psets = ifcopenshell.util.element.get_psets(product, psets_only=True)
    except Exception:  # a broken property set must not stop the inventory
        return None
    fallback = None
    for name, properties in psets.items():
        if "IsExternal" not in properties:
            continue
        value = properties["IsExternal"]
        if value is None:
            continue
        if name.startswith("Pset_") and name.endswith("Common"):
            return bool(value)
        fallback = bool(value)
    return fallback


def storey_of(product: ifcopenshell.entity_instance) -> str:
    """Name of the spatial container (storey, site, bridge part …), "" if there is none."""
    try:
        container = ifcopenshell.util.element.get_container(product)
    except Exception:
        return ""
    if container is None:
        return ""
    return f"{container.is_a()} {container.Name or ''}".strip()


def inventory(products: list[ifcopenshell.entity_instance]) -> list[Row]:
    return [
        Row(product.id(), product.is_a(), product.GlobalId, getattr(product, "Name", None) or "",
            storey_of(product), is_external(product))
        for product in products
    ]


def fake_select(model, threads, products, report=None, progress=None) -> envelope.Selection:
    """Stand-in for envelope.select while it is not implemented: keeps every product."""
    if progress:
        progress(100)
    return envelope.Selection(keep={product.id() for product in products}, total=len(products))


# ------------------------------------------------------------------------------------ comparison


def compare(rows: list[Row], selection: envelope.Selection) -> dict:
    """Confusion matrix, counts per class, exposure histogram and the interesting lists."""
    for row in rows:
        row.kept = row.id in selection.keep
        row.exposure = selection.exposure.get(row.id)

    confusion = {}
    for label, value in (("external_true", True), ("external_false", False), ("external_unknown", None)):
        group = [row for row in rows if row.external is value]
        confusion[label] = {"kept": sum(row.kept for row in group), "dropped": sum(not row.kept for row in group)}

    classes: dict[str, dict[str, int]] = {}
    for row in rows:
        entry = classes.setdefault(row.ifc_class, {"total": 0, "kept": 0, "dropped": 0, "external_true": 0,
                                                   "external_false": 0, "unknown": 0})
        entry["total"] += 1
        entry["kept" if row.kept else "dropped"] += 1
        if row.external is True:
            entry["external_true"] += 1
        elif row.external is False:
            entry["external_false"] += 1
        if row.exposure is None:
            entry["unknown"] += 1

    exposures = numpy.array([row.exposure for row in rows if row.exposure is not None], float)
    histogram = []
    lower = -1.0
    for upper in EXPOSURE_EDGES:
        inside = (exposures > lower) & (exposures <= upper) if lower >= 0 else exposures <= upper
        histogram.append({"from": max(lower, 0.0), "to": upper, "count": int(inside.sum())})
        lower = upper

    # Exposure alone at each threshold: products kept, products flagged external that would fall
    # below (kept only by the flag), products flagged internal that would still be kept.
    sweep = []
    flagged_external = numpy.array([row.external is True for row in rows if row.exposure is not None], bool)
    flagged_internal = numpy.array([row.external is False for row in rows if row.exposure is not None], bool)
    for threshold in SWEEP_THRESHOLDS:
        exposed = exposures >= threshold
        sweep.append({
            "threshold": threshold,
            "kept_by_exposure": int(exposed.sum()),
            "external_below": int((flagged_external & ~exposed).sum()),
            "internal_above": int((flagged_internal & exposed).sum()),
        })

    threshold = getattr(envelope, "EXPOSURE", 0.0)
    external_not_exposed = [row for row in rows if row.external is True and row.exposure is not None
                            and row.exposure < threshold]
    internal_exposed = [row for row in rows if row.external is False and row.kept and row.exposure is not None
                        and row.exposure >= threshold]
    dropped = [row for row in rows if not row.kept]
    unknown = [row for row in rows if row.exposure is None]
    return {
        "products": len(rows),
        "kept": sum(row.kept for row in rows),
        "dropped": len(dropped),
        "unknown": len(unknown),
        "selection": {"total": selection.total, "inside": selection.inside, "unknown": selection.unknown,
                      "flagged": selection.flagged, "voxel": selection.voxel, "exposure_threshold": threshold,
                      # Open hull (no roof or floors): the property sets and classes decided instead.
                      "open_hull": getattr(selection, "open_hull", False), "marked": getattr(selection, "marked", 0),
                      "fittings": getattr(selection, "fittings", 0)},
        "confusion": confusion,
        "classes": dict(sorted(classes.items())),
        "exposure_histogram": histogram,
        "threshold_sweep": sweep,
        "external_not_exposed": [row.as_dict() for row in external_not_exposed],
        "internal_exposed": [row.as_dict() for row in internal_exposed],
        "dropped_products": [row.as_dict() for row in dropped],
        "unknown_products": [row.as_dict() for row in unknown],
    }


def check_file(
    path: Path,
    threads: int,
    select: Callable = envelope.select,
    log: Callable[[str], None] = print,
) -> tuple[dict, ifcopenshell.file, list[Row]]:
    """Inventory and selection of one model; returns the report, the model and the rows."""
    started = time.monotonic()
    model = open_model(path)
    read_seconds = time.monotonic() - started
    products = converter.shape_products(model, converter.EXCLUDED_CLASSES)
    rows = inventory(products)
    log(f"{path.name}: {len(rows)} products, read in {read_seconds:.1f} s; selecting …")
    notes: list[str] = []

    def report(phase: str, text: str) -> None:
        notes.append(f"{phase}: {text}")
        log(f"  [{phase}] {text}")

    started = time.monotonic()
    selection = select(model, threads, products, report, None)
    select_seconds = time.monotonic() - started
    report_data = {
        "file": path.name,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "schema": model.schema_identifier,
        "threads": threads,
        "read_seconds": round(read_seconds, 2),
        "select_seconds": round(select_seconds, 2),
        "notes": notes,
        "parameters": {name: getattr(envelope, name) for name in ("VOXEL", "EXPOSURE", "MAX_VOXELS", "OPEN_HULL_SHARE")
                       if hasattr(envelope, name)},
        # Which version of the algorithm was checked (the lead iterates on it).
        "envelope_md5": hashlib.md5(Path(envelope.__file__).read_bytes()).hexdigest()[:8],
    }
    report_data.update(compare(rows, selection))
    log(f"  kept {report_data['kept']} / dropped {report_data['dropped']} / unknown {report_data['unknown']} "
        f"in {select_seconds:.1f} s")
    return report_data, model, rows


# ---------------------------------------------------------------------------------- measurement


def measure(path: Path, out_dir: Path, threads: int, modes: list[str], keep_output: bool,
            log: Callable[[str], None] = print) -> dict:
    """Convert ``path`` with and without the hull option per mode; file sizes, elements and seconds."""
    results = {}
    for mode in modes:
        fmt, geometry = MEASURE_MODES[mode]
        entry = {}
        for variant, hull in (("full", False), ("hull", True)):
            target = out_dir / f"{path.stem}.{mode}.{variant}.{fmt}"
            log(f"  converting {mode} {variant} …")
            started = time.monotonic()
            try:
                result = converter.convert(path, target, fmt=fmt, threads=threads, geometry=geometry, envelope=hull)
            except Exception as exc:  # noqa: BLE001 - recorded, the other variant still runs
                entry[variant] = {"error": f"{type(exc).__name__}: {exc}", "seconds": round(time.monotonic() - started, 1)}
                log(f"  {mode} {variant} failed: {exc}")
                continue
            seconds = time.monotonic() - started
            files = [target] + [target.with_suffix(suffix) for suffix in (".mtl",) if fmt == "obj"]
            size = sum(file.stat().st_size for file in files if file.exists())
            entry[variant] = {
                "seconds": round(seconds, 1), "bytes": size, "elements": result.elements,
                "skipped": result.skipped, "inside": result.inside, "output": str(target),
            }
            log(f"  {mode} {variant}: {size / 1024 ** 2:.1f} MB, {result.elements} elements, {seconds:.1f} s")
            if not keep_output:
                for file in files:
                    file.unlink(missing_ok=True)
                entry[variant].pop("output")
        full, hull = entry.get("full", {}), entry.get("hull", {})
        if "bytes" in full and "bytes" in hull:
            entry["size_ratio"] = round(hull["bytes"] / full["bytes"], 3) if full["bytes"] else None
            entry["time_ratio"] = round(hull["seconds"] / full["seconds"], 2) if full["seconds"] else None
        results[mode] = entry
    return results


# ------------------------------------------------------------------------------------- rendering


@dataclass
class Mesh:
    """Coarse triangles of a set of products, in world coordinates (metres)."""

    points: numpy.ndarray = field(default_factory=lambda: numpy.zeros((0, 3)))  # (n, 3)
    triangles: numpy.ndarray = field(default_factory=lambda: numpy.zeros((0, 3), numpy.int64))  # (m, 3)
    colors: numpy.ndarray = field(default_factory=lambda: numpy.zeros((0, 3), numpy.uint8))  # (m, 3) per triangle

    @classmethod
    def join(cls, parts: list[tuple[numpy.ndarray, numpy.ndarray, tuple[int, int, int]]]) -> Mesh:
        if not parts:
            return cls()
        offsets = numpy.cumsum([0] + [len(points) for points, _, _ in parts[:-1]])
        points = numpy.concatenate([points for points, _, _ in parts])
        triangles = numpy.concatenate([tris + offset for (_, tris, _), offset in zip(parts, offsets)])
        colors = numpy.concatenate([numpy.tile(numpy.array(color, numpy.uint8), (len(tris), 1)) for _, tris, color in parts])
        return cls(points, triangles, colors)


def class_color(ifc_class: str) -> tuple[int, int, int]:
    if ifc_class in CLASS_COLORS:
        return CLASS_COLORS[ifc_class]
    if ifc_class.startswith(("IfcFlow", "IfcDistribution", "IfcDuct", "IfcPipe", "IfcCable", "IfcEnergy")):
        return MEP_COLOR
    return DEFAULT_COLOR


def render_settings():
    settings = geom.settings()
    settings.set("mesher-linear-deflection", RENDER_LINEAR_DEFLECTION)
    settings.set("mesher-angular-deflection", RENDER_ANGULAR_DEFLECTION)
    settings.set("use-world-coords", True)
    settings.set("no-normals", True)
    return settings


@dataclass
class Meshes:
    """The coarse meshes of a model split by the selection, and the points the images are framed on."""

    kept: Mesh
    dropped: Mesh
    flagged: Mesh  # kept by IsExternal although not exposed: a subset of kept
    focus: numpy.ndarray  # (n, 3) bounding box corners of the products that are not terrain


def coarse_meshes(model: ifcopenshell.file, rows: list[Row], threads: int,
                  log: Callable[[str], None] = print) -> Meshes:
    """Coarse meshes (hybrid kernel) of the kept, of the dropped and of the flagged products."""
    by_id = {row.id: row for row in rows}
    products = [model.by_id(row.id) for row in rows]
    kept: list = []
    dropped: list = []
    flagged: list = []  # kept although not exposed (IsExternal = True): drawn on their own as well
    focus: list = []  # bounding boxes of everything but terrain: the frame of the images
    threshold = getattr(envelope, "EXPOSURE", 0.0)
    token = converter._kernel.set("hybrid")
    started = time.monotonic()
    try:
        for shape in converter.iter_shapes(model, render_settings(), threads, converter.EXCLUDED_CLASSES,
                                           products=products):
            row = by_id.get(shape.id)
            if row is None:
                continue
            geometry = shape.geometry
            triangles = numpy.frombuffer(geometry.faces_buffer, dtype=numpy.int32).reshape(-1, 3).astype(numpy.int64)
            if not len(triangles):
                continue
            points = numpy.frombuffer(geometry.verts_buffer, dtype=numpy.float64).reshape(-1, 3).copy()
            part = (points, triangles, class_color(row.ifc_class))
            (kept if row.kept else dropped).append(part)
            if row.ifc_class not in TERRAIN_CLASSES:
                focus += [points.min(axis=0), points.max(axis=0)]
            if row.kept and row.exposure is not None and row.exposure < threshold:
                flagged.append(part)
    finally:
        converter._kernel.reset(token)
    log(f"  coarse meshes: {len(kept)} kept ({len(flagged)} of them by the flag only), {len(dropped)} dropped "
        f"products in {time.monotonic() - started:.1f} s")
    return Meshes(Mesh.join(kept), Mesh.join(dropped), Mesh.join(flagged),
                  numpy.array(focus) if focus else numpy.zeros((0, 3)))


def view_matrix(azimuth: float, elevation: float) -> numpy.ndarray:
    """Rotation world -> camera (x right, y up, z towards the viewer) for a camera looking at the
    model from compass direction ``azimuth`` (0 = from the south, 90 = from the east) and ``elevation``
    degrees above the horizon."""
    a, e = math.radians(azimuth), math.radians(elevation)
    # Camera position direction (unit vector from the model towards the camera).
    toward = numpy.array([math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)])
    up = numpy.array([0.0, 0.0, 1.0])
    if abs(toward[2]) > 0.999:  # straight down: north is up in the image
        up = numpy.array([0.0, 1.0, 0.0])
    right = numpy.cross(up, toward)
    right /= numpy.linalg.norm(right)
    up = numpy.cross(toward, right)
    return numpy.stack([right, up, toward])


def frame(meshes: list[Mesh], matrix: numpy.ndarray, size: tuple[int, int],
          focus: numpy.ndarray | None = None) -> tuple[numpy.ndarray, float]:
    """Image centre in camera coordinates and pixels per metre fitting every mesh (or the ``focus``
    points, if given) into ``size``."""
    if focus is not None and len(focus):
        points = focus
    else:
        points = numpy.concatenate([mesh.points for mesh in meshes if len(mesh.points)] or [numpy.zeros((1, 3))])
    projected = points @ matrix.T
    low, high = projected.min(axis=0), projected.max(axis=0)
    extent = numpy.maximum(high - low, 1e-6)
    scale = 0.92 * min(size[0] / extent[0], size[1] / extent[1])
    return (low + high) / 2, float(scale)


def rasterize(mesh: Mesh, matrix: numpy.ndarray, centre: numpy.ndarray, scale: float,
              size: tuple[int, int] = IMAGE_SIZE, seed: int = 0) -> numpy.ndarray:
    """Draw ``mesh`` into an RGB image (height, width, 3): every triangle is sampled with points in
    proportion to its projected area, the nearest sample per pixel wins (a point-splat z-buffer)."""
    width, height = size
    image = numpy.empty((height, width, 3), numpy.uint8)
    image[:] = BACKGROUND
    if not len(mesh.triangles):
        return image
    camera = (mesh.points @ matrix.T - centre) * scale
    a, b, c = (camera[mesh.triangles[:, i]] for i in range(3))
    normals = numpy.cross(b - a, c - a)
    area2 = numpy.abs(normals[:, 2]) / 2  # projected area in pixels
    light = numpy.array([0.4, 0.5, 0.77])
    lengths = numpy.linalg.norm(normals, axis=1)
    lengths[lengths == 0] = 1.0
    shade = 0.45 + 0.55 * numpy.abs(normals @ light) / lengths
    colors = numpy.clip(mesh.colors * shade[:, None], 0, 255).astype(numpy.uint8)

    counts = numpy.ceil(area2 * 2.5).astype(numpy.int64) + 2
    total = counts.sum()
    if total > MAX_SAMPLES:
        counts = numpy.maximum(numpy.floor(counts * (MAX_SAMPLES / total)).astype(numpy.int64), 1)
    index = numpy.repeat(numpy.arange(len(counts)), counts)
    rng = numpy.random.default_rng(seed)
    u, v = rng.random(len(index)), rng.random(len(index))
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    samples = a[index] + (b[index] - a[index]) * u[:, None] + (c[index] - a[index]) * v[:, None]
    # Corners too, so that thin elements never vanish between samples.
    corners = numpy.concatenate([a, b, c])
    samples = numpy.concatenate([samples, corners])
    index = numpy.concatenate([index, numpy.tile(numpy.arange(len(counts)), 3)])
    xs = numpy.floor(samples[:, 0] + width / 2).astype(numpy.int64)
    ys = numpy.floor(height / 2 - samples[:, 1]).astype(numpy.int64)
    valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
    xs, ys, depth, index = xs[valid], ys[valid], samples[valid, 2], index[valid]
    pixel = ys * width + xs
    order = numpy.lexsort((-depth, pixel))  # per pixel: nearest (largest z, towards the viewer) first
    pixel, index = pixel[order], index[order]
    first = numpy.ones(len(pixel), bool)
    first[1:] = pixel[1:] != pixel[:-1]
    flat = image.reshape(-1, 3)
    flat[pixel[first]] = colors[index[first]]
    return image


def write_png(image: numpy.ndarray, path: Path) -> None:
    """Write an RGB uint8 image as PNG (no image library needed)."""
    height, width, _ = image.shape
    raw = b"".join(b"\x00" + image[y].tobytes() for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6))
                     + chunk(b"IEND", b""))


def render(meshes: Meshes, out_dir: Path, stem: str, views: dict[str, tuple[float, float]] = VIEWS,
           size: tuple[int, int] = IMAGE_SIZE) -> list[str]:
    """PNGs of the kept and the dropped products (and of the flagged ones, if any) from every view,
    in the same frame (the building without its terrain)."""
    paths = []
    sets = [("kept", meshes.kept), ("dropped", meshes.dropped)]
    if len(meshes.flagged.triangles):
        sets.append(("flagged", meshes.flagged))
    for name, (azimuth, elevation) in views.items():
        matrix = view_matrix(azimuth, elevation)
        centre, scale = frame([meshes.kept, meshes.dropped], matrix, size, meshes.focus)
        for label, mesh in sets:
            path = out_dir / f"{stem}.{name}.{label}.png"
            write_png(rasterize(mesh, matrix, centre, scale, size), path)
            paths.append(str(path))
    return paths


# --------------------------------------------------------------------------------------- reports


def _percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "–"


def _mb(size: int | None) -> str:
    return f"{size / 1024 ** 2:.1f} MB" if size is not None else "–"


def write_markdown(report: dict, path: Path) -> None:
    lines = [f"# Hull check: {report['file']}", ""]
    lines.append(f"{_mb(report['size_bytes'])}, {report['schema']}, read {report['read_seconds']} s, "
                 f"select {report['select_seconds']} s with {report['threads']} threads; envelope.py "
                 f"{report.get('envelope_md5', '?')} with "
                 + ", ".join(f"{k}={v}" for k, v in report["parameters"].items()))
    sel = report["selection"]
    lines += ["", "| products | kept | dropped | unknown (no coarse geometry) | flagged (kept by IsExternal) | voxel |",
              "|---|---|---|---|---|---|",
              f"| {report['products']} | {report['kept']} ({_percent(report['kept'], report['products'])}) | "
              f"{report['dropped']} ({_percent(report['dropped'], report['products'])}) | {report['unknown']} | "
              f"{sel['flagged']} | {sel['voxel']} m |", ""]
    if sel.get("open_hull"):
        lines.append(f"**Open hull**: the fill found no closed hull; instead {sel['marked']} products marked "
                     f"IsExternal = False and {sel['fittings']} of the furniture/services classes were dropped.")
    for note in report.get("notes", []):
        lines.append(f"- {note}")
    lines += ["", "## IsExternal vs. selection", "", "| IsExternal | kept | dropped |", "|---|---|---|"]
    for label, key in (("True", "external_true"), ("False", "external_false"), ("not set", "external_unknown")):
        entry = report["confusion"][key]
        lines.append(f"| {label} | {entry['kept']} | {entry['dropped']} |")
    lines += ["", "## Per class", "", "| class | total | kept | dropped | IsExternal True | IsExternal False | unknown |",
              "|---|---|---|---|---|---|---|"]
    for name, entry in report["classes"].items():
        lines.append(f"| {name} | {entry['total']} | {entry['kept']} | {entry['dropped']} | {entry['external_true']} | "
                     f"{entry['external_false']} | {entry['unknown']} |")
    lines += ["", "## Exposure shares", "", "| share | products |", "|---|---|"]
    for bucket in report["exposure_histogram"]:
        label = "0" if bucket["to"] == 0 else f"({bucket['from']:g}, {bucket['to']:g}]"
        lines.append(f"| {label} | {bucket['count']} |")
    lines += ["", "| threshold | kept by exposure alone | IsExternal=True below | IsExternal=False above |", "|---|---|---|---|"]
    for entry in report["threshold_sweep"]:
        lines.append(f"| {entry['threshold']:g} | {entry['kept_by_exposure']} | {entry['external_below']} | "
                     f"{entry['internal_above']} |")

    def listing(title: str, rows: list[dict], limit: int = 40) -> None:
        lines.extend(["", f"## {title} ({len(rows)})", ""])
        if not rows:
            lines.append("none")
            return
        lines.extend(["| class | GlobalId | name | storey | exposure |", "|---|---|---|---|---|"])
        for row in rows[:limit]:
            exposure = "–" if row["exposure"] is None else f"{row['exposure']:.3f}"
            lines.append(f"| {row['class']} | {row['guid']} | {row['name'][:40]} | {row['storey'][:30]} | {exposure} |")
        if len(rows) > limit:
            lines.append(f"| … | {len(rows) - limit} more, see JSON | | | |")

    listing("IsExternal=True but not exposed (kept because of the flag)", report["external_not_exposed"])
    listing("IsExternal=False but exposed (kept: really visible from outside?)", report["internal_exposed"])
    lines += ["", f"## Dropped products per class ({report['dropped']})", ""]
    dropped = report["dropped_products"]
    if dropped:
        lines += ["| class | dropped | IsExternal True | examples (GlobalId „name“) |", "|---|---|---|---|"]
        by_class: dict[str, list[dict]] = {}
        for row in dropped:
            by_class.setdefault(row["class"], []).append(row)
        for name, rows in sorted(by_class.items(), key=lambda item: -len(item[1])):
            flagged = sum(row["external"] is True for row in rows)
            examples = "; ".join(f"{row['guid']} „{row['name'][:25]}“" for row in rows[:EXAMPLES])
            lines.append(f"| {name} | {len(rows)} | {flagged} | {examples} |")
    else:
        lines.append("none")
    listing("Unknown (no coarse geometry, kept to be safe)", report["unknown_products"], 20)
    if report.get("measure"):
        lines += ["", "## Output size and time", "",
                  "| mode | full size | hull size | ratio | full s | hull s | ratio | elements full | elements hull | inside |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for mode, entry in report["measure"].items():
            full, hull = entry.get("full", {}), entry.get("hull", {})
            lines.append(
                f"| {mode} | {_mb(full.get('bytes'))} | {_mb(hull.get('bytes'))} | {entry.get('size_ratio', '–')} | "
                f"{full.get('seconds', full.get('error', '–'))} | {hull.get('seconds', hull.get('error', '–'))} | "
                f"{entry.get('time_ratio', '–')} | {full.get('elements', '–')} | {hull.get('elements', '–')} | "
                f"{hull.get('inside', '–')} |"
            )
    if report.get("renders"):
        lines += ["", "## Renders", ""] + [f"- {path}" for path in report["renders"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("hull-check-out"))
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--measure", default="", help=f"comma-separated modes: {', '.join(MEASURE_MODES)}")
    parser.add_argument("--keep-output", action="store_true", help="keep the converted files of --measure")
    parser.add_argument("--render", action="store_true", help="PNGs of the kept and the dropped products")
    parser.add_argument("--fake-select", action="store_true", help="keep everything instead of calling envelope.select")
    args = parser.parse_args(argv)
    # envelope logs how the selection's time splits between the coarse pass and the fill.
    logging.basicConfig(level=logging.INFO, format="  [log] %(message)s", stream=sys.stdout)
    logging.getLogger("ifc_converter.converter").setLevel(logging.WARNING)

    modes = [mode.strip() for mode in args.measure.split(",") if mode.strip()]
    unknown = [mode for mode in modes if mode not in MEASURE_MODES]
    if unknown:
        parser.error(f"unknown measure mode(s): {', '.join(unknown)}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    select = fake_select if args.fake_select else envelope.select

    for path in args.files:
        report, model, rows = check_file(path, args.threads, select)
        if args.render:
            meshes = coarse_meshes(model, rows, args.threads)
            report["renders"] = render(meshes, args.out_dir, path.stem)
            del meshes
        del model
        if modes:
            report["measure"] = measure(path, args.out_dir, args.threads, modes, args.keep_output)
        (args.out_dir / f"{path.stem}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        write_markdown(report, args.out_dir / f"{path.stem}.md")
        print(f"  written {args.out_dir / path.stem}.{{json,md}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
