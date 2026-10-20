"""3D view of a preview (preview.PreviewMesh) for the window, like the preview pane of Windows Explorer.

PreviewView draws with OpenGL 3.3 on the graphics card. Where that is not available (remote desktop,
virtual machines, CI runners without a GPU), or with IFC_CONVERTER_PREVIEW_RENDERER=software, it
draws with QPainter instead: fewer triangles, but it works everywhere. An OpenGL error does not end the
program: the view switches to QPainter and logs why.

Controls: left drag orbits (around the clicked point), middle or right drag and Shift+left drag pan,
the wheel zooms towards the cursor, a double-click shows the whole model, a click on an element emits
element_clicked with its label. Keys 1-4 (or the buttons) for the views Iso, Oben, Vorne, Seite,
F for the whole model, Pos1 for the start view.
"""

from __future__ import annotations

import logging
import math
import os
import re
import time
from dataclasses import dataclass
from functools import cache

import numpy
import shiboken6
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QMatrix4x4, QOffscreenSurface, QOpenGLContext, QPainter, QSurfaceFormat, \
    QVector3D
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QStackedLayout, QWidget

from ifc_converter.i18n import tr
from ifc_converter.preview import PreviewMesh

log = logging.getLogger("ifc_converter.viewer")

# "software" draws with QPainter even where OpenGL works (e.g. if a graphics driver misbehaves).
RENDERER_ENV = "IFC_CONVERTER_PREVIEW_RENDERER"
OPENGL = "OpenGL"
SOFTWARE = "Software"
REQUIRED_VERSION = (3, 3)  # core profile, GLSL 3.30

BACKGROUND = QColor("#eef1f4")
FOV_Y = 40.0  # vertical field of view, degrees
# Views as (yaw, pitch) of the viewing direction in degrees: yaw 0 looks east, 90 north; pitch < 0 down.
VIEWS = {
    "iso": (45.0, -math.degrees(math.atan(1 / math.sqrt(2)))),  # from south-west above
    "top": (90.0, -90.0),  # north up
    "front": (90.0, 0.0),  # from the south
    "side": (180.0, 0.0),  # from the east
}


def view_buttons() -> list[tuple[str, str, str]]:
    """(view, button text, tooltip) of the view buttons, in the user interface language."""
    return [
        ("iso", tr("Iso"), tr("Isometric view from the south-west (1)")),
        ("top", tr("Top"), tr("Plan view, north up (2)")),
        ("front", tr("Front"), tr("View from the south (3)")),
        ("side", tr("Side"), tr("View from the east (4)")),
    ]


VIEW_KEYS = {Qt.Key.Key_1: "iso", Qt.Key.Key_2: "top", Qt.Key.Key_3: "front", Qt.Key.Key_4: "side"}
ORBIT_DEGREES_PER_PIXEL = 0.4
ZOOM_STEP = 0.85  # distance factor per wheel notch
FIT_MARGIN = 0.9  # the fitted model fills this part of the view
FIT_POINTS = 50_000  # vertices the view is fitted to
CLICK_TOLERANCE = 4  # pixels the mouse may move for a press and release to count as a click
PICK_SIZE = 5  # pixels around the cursor searched for an element (thin elements are easier to hit)

# QPainter fallback: as many triangles (largest elements first) as it draws in about this time, when
# still and while the view moves; at most SOFTWARE_TRIANGLES.
SOFTWARE_SECONDS, SOFTWARE_MOVING_SECONDS = 0.7, 0.06
SOFTWARE_BUDGETS = (2_000, 5_000, 10_000, 20_000, 50_000, 100_000, 200_000)
SOFTWARE_TRIANGLES = SOFTWARE_BUDGETS[-1]
SPLIT_FRACTION = 16  # triangles longer than this part of the model's diagonal are split ...
SPLIT_GROWTH = 0.3  # ... adding at most this share of triangles
SETTLE_MS = 250  # full detail again this long after the last wheel step

# Light: a soft key light from above left of the viewer, light from the sky, and ambient.
AMBIENT, KEY_LIGHT, SKY_LIGHT = 0.38, 0.50, 0.24
LIGHT_DIRECTION = numpy.array([-0.35, 0.55, 1.0]) / numpy.linalg.norm([-0.35, 0.55, 1.0])  # view space

# OpenGL constants (QOpenGLFunctions takes plain ints).
GL_DEPTH_BUFFER_BIT, GL_COLOR_BUFFER_BIT = 0x0100, 0x4000
GL_TRIANGLES, GL_UNSIGNED_BYTE, GL_UNSIGNED_INT, GL_FLOAT = 0x0004, 0x1401, 0x1405, 0x1406
GL_DEPTH_TEST, GL_BLEND, GL_CULL_FACE, GL_MULTISAMPLE = 0x0B71, 0x0BE2, 0x0B44, 0x809D
GL_ONE, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA = 0x0001, 0x0302, 0x0303
GL_VENDOR, GL_RENDERER, GL_VERSION = 0x1F00, 0x1F01, 0x1F02

VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec4 color;
uniform mat4 mvp;
uniform mat4 modelView;
out vec3 viewPosition;
out vec4 vertexColor;
void main() {
    viewPosition = (modelView * vec4(position, 1.0)).xyz;
    vertexColor = color;
    gl_Position = mvp * vec4(position, 1.0);
}
"""
# Flat shading: the face normal from the screen-space derivatives, turned towards the viewer (the
# winding of IFC geometry is not reliable, so both sides are lit alike).
FRAGMENT_SHADER = """
#version 330 core
in vec3 viewPosition;
in vec4 vertexColor;
uniform vec3 lightDirection;
uniform vec3 viewUp;
uniform vec3 light;  // ambient, key, sky
out vec4 fragColor;
void main() {
    vec3 normal = normalize(cross(dFdx(viewPosition), dFdy(viewPosition)));
    if (dot(normal, viewPosition) > 0.0)
        normal = -normal;
    float brightness = light.x + light.y * max(dot(normal, lightDirection), 0.0)
        + light.z * (0.5 + 0.5 * dot(normal, viewUp));
    fragColor = vec4(min(vertexColor.rgb * brightness, 1.0), vertexColor.a);
}
"""
# Picking: the number of the triangle (+1, 0 is the background) as colour; 24 bits, enough for 16 million
# triangles (a preview has at most a few million).
PICK_SHADER = """
#version 330 core
out vec4 fragColor;
void main() {
    uint id = uint(gl_PrimitiveID) + 1u;
    fragColor = vec4(float(id & 255u), float((id >> 8) & 255u), float((id >> 16) & 255u), 255.0) / 255.0;
}
"""


# --------------------------------------------------------------------------- camera


class Camera:
    """Perspective turntable camera, Z up, in the coordinates of the mesh (relative to its origin).

    The camera looks from ``eye()`` at ``target``, ``distance`` away, in the direction given by
    ``yaw`` and ``pitch`` (degrees). Pixel coordinates are logical widget pixels, origin top left.
    """

    def __init__(self) -> None:
        self.yaw, self.pitch = VIEWS["iso"]
        self.target = numpy.zeros(3)
        self.distance = 10.0
        self.center = numpy.zeros(3)  # the model's bounding box
        self.size = numpy.ones(3)
        self.points: numpy.ndarray | None = None  # sample of the model's vertices
        self.width, self.height = 1, 1

    @property
    def radius(self) -> float:
        """Half the diagonal of the model's box; at least 0.5 m so a point-like model can be looked at."""
        return max(0.5 * float(numpy.linalg.norm(self.size)), 0.5)

    def set_model(self, low, high, points=None) -> None:
        """The model's box and (optional) points of it, to fit the view more tightly than to the box."""
        low, high = numpy.asarray(low, float), numpy.asarray(high, float)
        self.center = (low + high) / 2
        self.size = high - low
        self.points = None if points is None or not len(points) else numpy.asarray(points, float).reshape(-1, 3)

    def set_viewport(self, width: int, height: int) -> None:
        self.width, self.height = max(int(width), 1), max(int(height), 1)

    @property
    def aspect(self) -> float:
        return self.width / self.height

    def basis(self) -> numpy.ndarray:
        """Rows: right, up, forward (unit vectors); right is always horizontal, so Z stays up."""
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        forward = numpy.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
        right = numpy.array([math.sin(yaw), -math.cos(yaw), 0.0])
        return numpy.array([right, numpy.cross(right, forward), forward])

    def eye(self) -> numpy.ndarray:
        return self.target - self.basis()[2] * self.distance

    def view_matrix(self) -> numpy.ndarray:
        right, up, forward = self.basis()
        eye = self.eye()
        view = numpy.identity(4)
        view[0, :3], view[1, :3], view[2, :3] = right, up, -forward
        view[:3, 3] = -view[:3, :3] @ eye
        return view

    def clip_planes(self) -> tuple[float, float]:
        """Near and far plane around the model: tight from outside, still usable from inside."""
        to_center = float(numpy.linalg.norm(self.eye() - self.center))
        radius = self.radius * 1.05
        far = to_center + radius
        near = max(to_center - radius, min(self.distance * 0.05, far * 1e-3), far * 1e-6)
        return near, max(far, near * 2)

    def projection_matrix(self) -> numpy.ndarray:
        near, far = self.clip_planes()
        f = 1 / math.tan(math.radians(FOV_Y) / 2)
        return numpy.array([
            [f / self.aspect, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
            [0, 0, -1, 0],
        ])

    def matrix(self) -> numpy.ndarray:
        """Model coordinates to clip coordinates."""
        return self.projection_matrix() @ self.view_matrix()

    def project(self, points) -> tuple[numpy.ndarray, numpy.ndarray]:
        """Pixel positions (N, 2) and depths in front of the eye (N,) of model points (N, 3)."""
        points = numpy.asarray(points, float).reshape(-1, 3)
        clip = points @ self.matrix()[:, :3].T + self.matrix()[:, 3]
        w = clip[:, 3]
        with numpy.errstate(divide="ignore", invalid="ignore"):
            x = (clip[:, 0] / w + 1) / 2 * self.width
            y = (1 - clip[:, 1] / w) / 2 * self.height
        return numpy.column_stack([x, y]), w

    def ray(self, x: float, y: float) -> tuple[numpy.ndarray, numpy.ndarray]:
        """Eye and unit direction of the ray through pixel (x, y)."""
        right, up, forward = self.basis()
        ty = math.tan(math.radians(FOV_Y) / 2)
        nx, ny = 2 * x / self.width - 1, 1 - 2 * y / self.height
        direction = forward + right * nx * ty * self.aspect + up * ny * ty
        return self.eye(), direction / numpy.linalg.norm(direction)

    def depth(self, point) -> float:
        """Distance of ``point`` in front of the eye, along the viewing direction."""
        return float(numpy.dot(numpy.asarray(point, float) - self.eye(), self.basis()[2]))

    def fit(self) -> None:
        """Look at the whole model from the current direction, centred on the screen."""
        right, up, forward = self.basis()
        points = self.points
        if points is None:
            points = self.center + numpy.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]) \
                * self.size / 2
        tan_y = math.tan(math.radians(FOV_Y) / 2) * FIT_MARGIN
        tan_x = tan_y * self.aspect
        target = self.center.copy()
        for attempt in range(4):
            relative = points - target
            x, y, z = relative @ right, relative @ up, relative @ forward
            # The nearest eye from which every point is inside the (narrowed) view.
            distance = max(float(numpy.max(numpy.abs(x) / tan_x - z)), float(numpy.max(numpy.abs(y) / tan_y - z)),
                           float(numpy.max(-z)) + self.radius * 0.05, 0.01)
            if attempt == 3:
                break
            # Move the target so the model's extent on screen is centred, then fit again.
            depth = z + distance
            screen_x, screen_y = x / depth, y / depth
            shift_x = (screen_x.max() + screen_x.min()) / 2
            shift_y = (screen_y.max() + screen_y.min()) / 2
            if abs(shift_x) < 1e-4 * tan_x and abs(shift_y) < 1e-4 * tan_y:
                break
            target = target + (right * shift_x + up * shift_y) * distance
        self.target, self.distance = target, distance

    def set_view(self, yaw: float, pitch: float) -> None:
        self.yaw, self.pitch = yaw % 360, pitch
        self.fit()

    def orbit(self, dx: float, dy: float, pivot=None) -> None:
        """Turn the model with a mouse movement of (dx, dy) pixels about ``pivot`` (default: the target)."""
        before = self.basis()
        self.yaw = (self.yaw - dx * ORBIT_DEGREES_PER_PIXEL) % 360
        self.pitch = min(max(self.pitch - dy * ORBIT_DEGREES_PER_PIXEL, -90.0), 90.0)
        if pivot is not None:
            rotation = self.basis().T @ before  # old basis to new basis
            pivot = numpy.asarray(pivot, float)
            self.target = pivot + rotation @ (self.target - pivot)

    def pan(self, dx: float, dy: float, depth: float | None = None) -> None:
        """Move the view so that a point at ``depth`` (default: the target's) follows the mouse."""
        right, up, _ = self.basis()
        depth = self.distance if depth is None or depth <= 0 else depth
        per_pixel = 2 * depth * math.tan(math.radians(FOV_Y) / 2) / self.height
        self.target = self.target - right * dx * per_pixel + up * dy * per_pixel

    def zoom(self, factor: float, point=None) -> None:
        """Change the distance by ``factor`` (< 1 closer); ``point`` stays where it is on screen."""
        radius = self.radius
        distance = min(max(self.distance * factor, radius * 1e-4, 0.005), radius * 100)
        factor = distance / self.distance
        if point is not None:
            point = numpy.asarray(point, float)
            self.target = point + (self.target - point) * factor
        self.distance = distance

    def point_at(self, x: float, y: float) -> numpy.ndarray:
        """The point under pixel (x, y) at the depth of the target, where no element is hit."""
        eye, direction = self.ray(x, y)
        return eye + direction * (self.distance / float(numpy.dot(direction, self.basis()[2])))

    def state(self) -> tuple:
        return (self.yaw, self.pitch, *self.target, self.distance, self.width, self.height)


def _fit_points(mesh: PreviewMesh, count: int = FIT_POINTS) -> numpy.ndarray:
    """Up to about ``count`` vertices of the mesh, and those at the ends of every axis."""
    positions = mesh.positions
    if len(positions) <= count:
        return positions
    extremes = numpy.concatenate([positions.argmin(axis=0), positions.argmax(axis=0)])
    return numpy.concatenate([positions[::len(positions) // count + 1], positions[extremes]])


def intersect(origin, direction, a, b, c) -> numpy.ndarray:
    """Distances along the ray to triangles (a, b, c), arrays (N, 3); inf where the ray misses."""
    origin = numpy.asarray(origin, float)
    direction = numpy.asarray(direction, float)
    edge1, edge2 = b - a, c - a
    p = numpy.cross(direction, edge2)
    det = numpy.einsum("ij,ij->i", edge1, p)
    with numpy.errstate(divide="ignore", invalid="ignore"):
        inverse = 1 / det
        s = origin - a
        u = numpy.einsum("ij,ij->i", s, p) * inverse
        q = numpy.cross(s, edge1)
        v = (q @ direction) * inverse
        t = numpy.einsum("ij,ij->i", edge2, q) * inverse
    hit = (numpy.abs(det) > 1e-12) & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
    return numpy.where(hit, t, numpy.inf)


class _Scene:
    """A mesh prepared for drawing: opaque triangles first, then the transparent ones."""

    def __init__(self, mesh: PreviewMesh) -> None:
        self.mesh = mesh
        self.triangles = mesh.indices.reshape(-1, 3)
        transparent = (mesh.colors[:, 3] < 255)[self.triangles].any(axis=1)
        self.opaque_count = int(len(transparent) - numpy.count_nonzero(transparent))
        if self.opaque_count == len(transparent):
            self.order = None  # draw order = triangle order
        else:
            self.order = numpy.concatenate([numpy.flatnonzero(~transparent), numpy.flatnonzero(transparent)])
        self._software: dict[int, _Flat] = {}
        self._rank: numpy.ndarray | None = None
        self._split_length = 1.0

    @property
    def triangle_count(self) -> int:
        return len(self.triangles)

    def draw_indices(self) -> numpy.ndarray:
        if self.order is None:
            return numpy.ascontiguousarray(self.mesh.indices, numpy.uint32)
        return numpy.ascontiguousarray(self.triangles[self.order].reshape(-1), numpy.uint32)

    def triangle_of_draw(self, drawn: int) -> int:
        return int(drawn if self.order is None else self.order[drawn])

    def label(self, triangle: int) -> str:
        if triangle < 0:
            return ""
        element = int(self.mesh.triangle_elements[triangle])
        return self.mesh.elements[element] if element < len(self.mesh.elements) else ""

    def corners(self, triangles) -> tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray]:
        points = self.mesh.positions[self.triangles[triangles]].astype(float)
        return points[:, 0], points[:, 1], points[:, 2]

    def hit_point(self, triangle: int, camera: Camera, x: float, y: float) -> numpy.ndarray:
        """Where the ray through pixel (x, y) meets ``triangle`` (or its plane, near an edge)."""
        eye, direction = camera.ray(x, y)
        a, b, c = self.corners([triangle])
        normal = numpy.cross(b[0] - a[0], c[0] - a[0])
        denominator = float(numpy.dot(normal, direction))
        if abs(denominator) < 1e-12 * max(float(numpy.linalg.norm(normal)), 1e-30):
            return (a[0] + b[0] + c[0]) / 3
        t = float(numpy.dot(normal, a[0] - eye)) / denominator
        return eye + direction * t if t > 0 else (a[0] + b[0] + c[0]) / 3

    def software(self, budget: int) -> _Flat:
        """About ``budget`` triangles for QPainter: those of the largest elements (by surface) first,
        large ones split so that drawing back to front (painter's algorithm) stays mostly right."""
        if budget not in self._software:
            chosen = numpy.sort(self._ranked()[:int(budget / (1 + SPLIT_GROWTH))])
            corners = self.mesh.positions[self.triangles[chosen]].astype(numpy.float32)
            colors = self.mesh.colors[self.triangles[chosen]].astype(numpy.float32).mean(axis=1)
            self._software[budget] = _split_large(_Flat(corners, colors, chosen), budget, self._split_length)
        return self._software[budget]

    def _ranked(self) -> numpy.ndarray:
        """Triangles with an area, those of the element with the largest surface first."""
        if self._rank is None:
            area = numpy.empty(self.triangle_count)
            for start in range(0, self.triangle_count, 500_000):  # bounded temporary memory
                a, b, c = self.corners(slice(start, start + 500_000))
                area[start:start + len(a)] = numpy.linalg.norm(numpy.cross(b - a, c - a), axis=1)
            triangles = numpy.flatnonzero(area > 0)
            elements = self.mesh.triangle_elements[triangles].astype(numpy.int64)
            element_area = numpy.bincount(elements, area[triangles])
            rank = numpy.empty(len(element_area), numpy.int64)
            rank[numpy.argsort(-element_area, kind="stable")] = numpy.arange(len(element_area))
            self._rank = triangles[numpy.argsort(rank[elements], kind="stable")]
            low, high = self.mesh.bounds()
            self._split_length = max(float(numpy.linalg.norm(high - low)) / SPLIT_FRACTION, 1e-3)
        return self._rank


@dataclass
class _Flat:
    """Triangles for QPainter: corners (N, 3, 3) and RGBA (N, 4) as float32, mesh triangle of each."""

    corners: numpy.ndarray
    colors: numpy.ndarray
    source: numpy.ndarray

    def __len__(self) -> int:
        return len(self.corners)


def _split_large(flat: _Flat, limit: int, length: float) -> _Flat:
    """Bisect triangles at their longest edge until none is longer than ``length`` (or ``limit`` is reached).

    Changes the arrays of ``flat``."""
    corners, colors, source = flat.corners, flat.colors, flat.source
    for _ in range(24):
        lengths = numpy.linalg.norm(corners[:, [1, 2, 0]] - corners, axis=2)  # edge k: corner k to k + 1
        longest = lengths.max(axis=1)
        big = numpy.flatnonzero(longest > length)
        room = limit - len(corners)
        if not len(big) or room <= 0:
            break
        if len(big) > room:
            big = big[numpy.argsort(-longest[big], kind="stable")[:room]]
        k = lengths[big].argmax(axis=1)  # the longest edge runs from a to b
        rows, pieces = numpy.arange(len(big)), corners[big]
        a, b, c = pieces[rows, k], pieces[rows, (k + 1) % 3], pieces[rows, (k + 2) % 3]
        middle = (a + b) / 2
        corners[big] = numpy.stack([a, middle, c], axis=1)  # same winding as (a, b, c)
        corners = numpy.concatenate([corners, numpy.stack([middle, b, c], axis=1)])
        colors = numpy.concatenate([colors, colors[big]])
        source = numpy.concatenate([source, source[big]])
    return _Flat(corners, colors, source)


def _shade(colors: numpy.ndarray, normals: numpy.ndarray, up: numpy.ndarray, centroids: numpy.ndarray) -> numpy.ndarray:
    """RGB (N, 3) of flat-shaded triangles like the fragment shader: colours 0..255, all in view space."""
    flip = numpy.einsum("ij,ij->i", normals, centroids) > 0
    normals = numpy.where(flip[:, None], -normals, normals)
    brightness = AMBIENT + KEY_LIGHT * numpy.maximum(normals @ LIGHT_DIRECTION, 0) \
        + SKY_LIGHT * (0.5 + 0.5 * (normals @ up))
    return numpy.minimum(colors * brightness[:, None], 255)


# --------------------------------------------------------------------------- OpenGL


def _surface_format() -> QSurfaceFormat:
    surface = QSurfaceFormat()
    surface.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    surface.setVersion(*REQUIRED_VERSION)
    surface.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface.setDepthBufferSize(24)
    surface.setSamples(4)
    return surface


@cache
def opengl_problem() -> str:
    """Why OpenGL cannot draw the preview on this machine, or "" if it can (checked once)."""
    if os.environ.get(RENDERER_ENV, "").strip().lower() == "software":
        return f"{RENDERER_ENV}=software"
    try:
        if QOpenGLContext.openGLModuleType() != QOpenGLContext.OpenGLModuleType.LibGL:
            return "nur OpenGL ES vorhanden"
        context = QOpenGLContext()
        context.setFormat(_surface_format())
        if not context.create() or context.isOpenGLES():
            return "kein OpenGL-Kontext"
        surface = QOffscreenSurface()
        surface.setFormat(context.format())
        surface.create()
        if not surface.isValid() or not context.makeCurrent(surface):
            return "OpenGL-Kontext nicht nutzbar"
        try:
            problem = _version_problem(context)
            if not problem:
                functions = context.functions()
                log.info("Vorschau mit OpenGL: %s, %s (%s)", functions.glGetString(GL_VERSION),
                         functions.glGetString(GL_RENDERER), functions.glGetString(GL_VENDOR))
        finally:
            context.doneCurrent()
            surface.destroy()
        return problem
    except Exception as exc:  # whatever a driver does, the fallback must still work
        return f"{type(exc).__name__}: {exc}"


def _version_problem(context: QOpenGLContext) -> str:
    """Why the current ``context`` is too old, or "". Its format() may just echo the requested version,
    so the version is read from the driver."""
    text = context.functions().glGetString(GL_VERSION) or ""
    match = re.match(r"\s*(\d+)\.(\d+)", text)
    version = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
    if context.isOpenGLES() or version < REQUIRED_VERSION:
        return f"OpenGL {text or '?'} statt {REQUIRED_VERSION[0]}.{REQUIRED_VERSION[1]}"
    return ""


def _qmatrix(matrix: numpy.ndarray) -> QMatrix4x4:
    return QMatrix4x4(*(float(value) for value in matrix.reshape(-1)))


def _offset(byte_offset: int) -> shiboken6.VoidPtr:
    """A byte offset into the bound index buffer, as the pointer argument of glDrawElements."""
    return shiboken6.VoidPtr(byte_offset)


def _clear_errors(functions) -> None:
    for _ in range(16):
        if not functions.glGetError():
            break


@cache
def _gl_view_class() -> type:
    """The OpenGL renderer; QtOpenGL is imported only here, so a machine without it still gets a view."""
    from PySide6.QtOpenGL import (
        QOpenGLBuffer,
        QOpenGLFramebufferObject,
        QOpenGLShader,
        QOpenGLShaderProgram,
        QOpenGLVertexArrayObject,
    )
    from PySide6.QtOpenGLWidgets import QOpenGLWidget

    class GLView(QOpenGLWidget):
        """Draws the scene with OpenGL; emits ``failed`` (once) on any error instead of raising."""

        failed = Signal(str)

        def __init__(self, owner: PreviewView) -> None:
            super().__init__(owner)
            self.setFormat(_surface_format())
            self._owner = owner
            self._scene: _Scene | None = None
            self._uploaded: _Scene | None = None
            self._gl = None  # resources of the current context
            self._broken = False
            self.detail = ""  # OpenGL version and graphics card, once initialized

        # -- what PreviewView calls

        def set_scene(self, scene: _Scene | None) -> None:
            self._scene = scene
            self.update()

        def set_moving(self, moving: bool) -> None:
            pass

        def image(self) -> QImage:
            return self.grabFramebuffer()

        def pick(self, x: float, y: float) -> int:
            """The triangle (of the mesh) under pixel (x, y), or -1."""
            scene = self._scene
            if self._broken or scene is None or not scene.triangle_count or self.context() is None:
                return -1
            self.makeCurrent()
            try:
                if not self._ready():
                    return -1
                drawn = self._pick(x, y)
            except Exception as exc:
                self._fail(f"Auswahl: {type(exc).__name__}: {exc}")
                return -1
            finally:
                self.doneCurrent()
            return -1 if drawn < 0 else scene.triangle_of_draw(drawn)

        # -- QOpenGLWidget

        def initializeGL(self) -> None:
            self._gl = None
            self._uploaded = None
            try:
                context = self.context()
                problem = _version_problem(context)
                if problem:
                    raise RuntimeError(problem)
                functions = context.functions()
                self.detail = f"{functions.glGetString(GL_VERSION)}, {functions.glGetString(GL_RENDERER)}"
                programs = []
                for fragment in (FRAGMENT_SHADER, PICK_SHADER):
                    program = QOpenGLShaderProgram(self)
                    if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERTEX_SHADER) \
                            or not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragment) \
                            or not program.link():
                        raise RuntimeError(f"Shader: {program.log().strip()}")
                    programs.append(program)
                vao = QOpenGLVertexArrayObject(self)
                if not vao.create():
                    raise RuntimeError("kein Vertex Array Object")
                fbo = QOpenGLFramebufferObject(QSize(PICK_SIZE, PICK_SIZE),
                                               QOpenGLFramebufferObject.Attachment.Depth)
                if not fbo.isValid():
                    raise RuntimeError("kein Framebuffer für die Auswahl")
                # Freed with the context (or when replaced here): Qt's GL objects guard against a context
                # that is already gone.
                self._gl = {"f": functions, "draw": programs[0], "pick": programs[1], "vao": vao, "fbo": fbo,
                            "buffers": []}
            except Exception as exc:
                self._fail(f"{type(exc).__name__}: {exc}")

        def paintEvent(self, event) -> None:
            super().paintEvent(event)
            # Qt calls initializeGL before the first paint, unless it could not make a context for the
            # view (it only logs that): without this, the view would stay empty.
            if self._gl is None and not self._broken:
                self._fail("kein OpenGL-Kontext für die Ansicht")

        def paintGL(self) -> None:
            if self._broken or self._gl is None:
                return
            try:
                self._paint()
            except Exception as exc:
                self._fail(f"{type(exc).__name__}: {exc}")

        # -- drawing

        def _ready(self) -> bool:
            """Resources exist and hold the current scene (uploaded on first use)."""
            if self._gl is None or self._scene is None:
                return False
            if self._uploaded is not self._scene:
                self._upload(self._scene)
            return True

        def _upload(self, scene: _Scene) -> None:
            gl = self._gl
            started = time.perf_counter()
            _clear_errors(gl["f"])
            for buffer in gl["buffers"]:
                buffer.destroy()
            gl["buffers"] = []
            mesh = scene.mesh
            vertex, index = QOpenGLBuffer.Type.VertexBuffer, QOpenGLBuffer.Type.IndexBuffer
            data = [  # (buffer type, array, (attribute location, type, components) or None)
                (vertex, numpy.ascontiguousarray(mesh.positions, numpy.float32), (0, GL_FLOAT, 3)),
                (vertex, numpy.ascontiguousarray(mesh.colors, numpy.uint8), (1, GL_UNSIGNED_BYTE, 4)),
                (index, scene.draw_indices(), None),
            ]
            vao, program = gl["vao"], gl["draw"]
            vao.bind()
            try:
                for kind, array, attribute in data:
                    buffer = QOpenGLBuffer(kind)
                    if not buffer.create():
                        raise RuntimeError("kein Puffer")
                    buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)
                    buffer.bind()
                    buffer.allocate(array.data, array.nbytes)  # bytes go straight from numpy to the driver
                    gl["buffers"].append(buffer)
                    if attribute is not None:
                        location, gl_type, size = attribute
                        program.enableAttributeArray(location)
                        program.setAttributeBuffer(location, gl_type, 0, size, array.itemsize * size)  # normalized
            finally:
                vao.release()
            error = gl["f"].glGetError()
            if error:
                raise RuntimeError(f"OpenGL-Fehler 0x{error:04X} beim Hochladen (zu wenig Grafikspeicher?)")
            self._uploaded = scene
            log.debug("Vorschau hochgeladen: %d Dreiecke in %.2f s", scene.triangle_count,
                      time.perf_counter() - started)

        def _paint(self) -> None:
            f = self._gl["f"]
            _clear_errors(f)  # e.g. left by Qt's own drawing: only errors of this frame count
            f.glClearColor(BACKGROUND.redF(), BACKGROUND.greenF(), BACKGROUND.blueF(), 1.0)
            f.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            if not self._ready() or not self._scene.triangle_count:
                return
            scene, gl, camera = self._scene, self._gl, self._owner.camera
            camera.set_viewport(self.width(), self.height())
            view = camera.view_matrix()
            program = gl["draw"]
            program.bind()
            uniform = program.uniformLocation
            program.setUniformValue(uniform("mvp"), _qmatrix(camera.projection_matrix() @ view))
            program.setUniformValue(uniform("modelView"), _qmatrix(view))
            program.setUniformValue(uniform("lightDirection"), QVector3D(*(float(v) for v in LIGHT_DIRECTION)))
            program.setUniformValue(uniform("viewUp"), QVector3D(*(float(v) for v in view[:3, 2])))
            program.setUniformValue(uniform("light"), QVector3D(AMBIENT, KEY_LIGHT, SKY_LIGHT))
            f.glEnable(GL_DEPTH_TEST)
            f.glDisable(GL_CULL_FACE)
            f.glEnable(GL_MULTISAMPLE)
            gl["vao"].bind()
            try:
                if scene.opaque_count:
                    f.glDisable(GL_BLEND)
                    f.glDrawElements(GL_TRIANGLES, 3 * scene.opaque_count, GL_UNSIGNED_INT, _offset(0))
                transparent = scene.triangle_count - scene.opaque_count
                if transparent:  # glass after everything else, without hiding what lies behind it
                    f.glEnable(GL_BLEND)
                    f.glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
                    f.glDepthMask(False)
                    f.glDrawElements(GL_TRIANGLES, 3 * transparent, GL_UNSIGNED_INT, _offset(12 * scene.opaque_count))
                    f.glDepthMask(True)
                    f.glDisable(GL_BLEND)
            finally:
                gl["vao"].release()
                program.release()
            error = f.glGetError()
            if error:
                raise RuntimeError(f"OpenGL-Fehler 0x{error:04X} beim Zeichnen")

        def _pick(self, x: float, y: float) -> int:
            """Draw triangle numbers into a small framebuffer around (x, y); the one nearest the centre."""
            gl, camera, scene = self._gl, self._owner.camera, self._scene
            camera.set_viewport(self.width(), self.height())
            # Zoom the projection to the PICK_SIZE pixels around the cursor.
            scale_x, scale_y = camera.width / PICK_SIZE, camera.height / PICK_SIZE
            ndc_x, ndc_y = 2 * x / camera.width - 1, 1 - 2 * y / camera.height
            region = numpy.identity(4)
            region[0, 0], region[0, 3] = scale_x, -ndc_x * scale_x
            region[1, 1], region[1, 3] = scale_y, -ndc_y * scale_y
            f, fbo, program = gl["f"], gl["fbo"], gl["pick"]
            fbo.bind()
            try:
                f.glViewport(0, 0, PICK_SIZE, PICK_SIZE)
                f.glClearColor(0, 0, 0, 1)
                f.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                f.glEnable(GL_DEPTH_TEST)
                f.glDisable(GL_BLEND)
                f.glDisable(GL_MULTISAMPLE)
                program.bind()
                program.setUniformValue(program.uniformLocation("mvp"), _qmatrix(region @ camera.matrix()))
                gl["vao"].bind()
                f.glDrawElements(GL_TRIANGLES, 3 * scene.triangle_count, GL_UNSIGNED_INT, _offset(0))
                gl["vao"].release()
                program.release()
                image = fbo.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            finally:
                fbo.release()
            pixels = numpy.frombuffer(image.constBits(), numpy.uint8, image.sizeInBytes())
            pixels = pixels.reshape(PICK_SIZE, image.bytesPerLine())[:, :4 * PICK_SIZE].reshape(PICK_SIZE, PICK_SIZE, 4)
            ids = pixels[..., 0].astype(numpy.int64) | pixels[..., 1].astype(numpy.int64) << 8 \
                | pixels[..., 2].astype(numpy.int64) << 16
            rows, columns = numpy.nonzero(ids)
            if not len(rows):
                return -1
            centre = PICK_SIZE // 2
            nearest = numpy.argmin((rows - centre) ** 2 + (columns - centre) ** 2)
            drawn = int(ids[rows[nearest], columns[nearest]]) - 1
            return drawn if drawn < scene.triangle_count else -1

        def _fail(self, reason: str) -> None:
            if self._broken:
                return
            self._broken = True
            log.warning("Vorschau: OpenGL-Fehler, weiter mit Software-Darstellung: %s", reason)
            QTimer.singleShot(0, lambda: self.failed.emit(reason))

    return GLView


# --------------------------------------------------------------------------- QPainter


class _SoftwareView(QWidget):
    """Draws the scene with QPainter: flat-shaded triangles back to front, the largest elements only.

    How many triangles depends on how fast this machine draws them (measured on every frame), so that
    a still view takes about SOFTWARE_SECONDS and a moving one SOFTWARE_MOVING_SECONDS.
    """

    def __init__(self, owner: PreviewView, reason: str) -> None:
        super().__init__(owner)
        self._owner = owner
        self.detail = reason  # why not OpenGL
        self._scene: _Scene | None = None
        self._moving = False
        self._cache: tuple[tuple, QImage] | None = None
        self._seconds_per_triangle = 1e-5  # a cautious first guess, measured from the first frame on
        self.drawn = 0  # triangles in the last frame
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def set_scene(self, scene: _Scene | None) -> None:
        self._scene = scene
        self._cache = None
        self.update()

    def set_moving(self, moving: bool) -> None:
        if moving != self._moving:
            self._moving = moving
            self.update()

    def image(self) -> QImage:
        return self._render()

    def budget(self, moving: bool) -> int:
        seconds = SOFTWARE_MOVING_SECONDS if moving else SOFTWARE_SECONDS
        fitting = [count for count in SOFTWARE_BUDGETS if count * self._seconds_per_triangle <= seconds]
        return fitting[-1] if fitting else SOFTWARE_BUDGETS[0]

    def pick(self, x: float, y: float) -> int:
        scene = self._scene
        if scene is None or not scene.triangle_count:
            return -1
        flat = scene.software(self.budget(False))
        if not len(flat):
            return -1
        camera = self._owner.camera
        camera.set_viewport(self.width(), self.height())
        eye, direction = camera.ray(x, y)
        corners = flat.corners.astype(float)
        distances = intersect(eye, direction, corners[:, 0], corners[:, 1], corners[:, 2])
        nearest = int(numpy.argmin(distances))
        return int(flat.source[nearest]) if numpy.isfinite(distances[nearest]) else -1

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.drawImage(0, 0, self._render())
        painter.end()

    def _render(self) -> QImage:
        camera = self._owner.camera
        camera.set_viewport(self.width(), self.height())
        ratio = self.devicePixelRatioF()
        key = (camera.state(), ratio, self._moving, id(self._scene))
        if self._cache is not None and self._cache[0] == key:
            return self._cache[1]
        image = QImage(round(camera.width * ratio), round(camera.height * ratio),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(BACKGROUND)
        self.drawn = 0
        if self._scene is not None and self._scene.triangle_count:
            try:
                flat = self._scene.software(self.budget(self._moving))
                started = time.perf_counter()
                self._draw(image, camera, flat)
                if len(flat) >= 1000:
                    measured = (time.perf_counter() - started) / len(flat)
                    self._seconds_per_triangle = (self._seconds_per_triangle + measured) / 2
            except Exception:  # a broken frame must not end the program
                log.exception("Vorschau: Fehler beim Zeichnen")
        self._cache = (key, image)
        return image

    def _draw(self, image: QImage, camera: Camera, flat: _Flat) -> None:
        view = camera.view_matrix()
        eye_space = flat.corners.astype(float) @ view[:3, :3].T + view[:3, 3]  # (N, 3, 3)
        depth = -eye_space[..., 2]  # in front of the eye > 0
        near, _ = camera.clip_planes()
        visible = (depth > near).all(axis=1)  # triangles through the near plane are left out
        f = 1 / math.tan(math.radians(FOV_Y) / 2)
        with numpy.errstate(divide="ignore", invalid="ignore"):
            x = (eye_space[..., 0] * f / camera.aspect / depth + 1) / 2 * camera.width
            y = (1 - eye_space[..., 1] * f / depth) / 2 * camera.height
        visible &= ~((x < 0).all(axis=1) | (x > camera.width).all(axis=1) | (y < 0).all(axis=1)
                     | (y > camera.height).all(axis=1))
        if not visible.any():
            return
        eye_space, depth, colors = eye_space[visible], depth[visible], flat.colors[visible]
        x, y = numpy.round(x[visible]).astype(numpy.int32), numpy.round(y[visible]).astype(numpy.int32)
        normals = numpy.cross(eye_space[:, 1] - eye_space[:, 0], eye_space[:, 2] - eye_space[:, 0])
        length = numpy.linalg.norm(normals, axis=1)
        normals /= numpy.where(length > 0, length, 1)[:, None]
        rgb = _shade(colors[:, :3], normals, view[:3, 2], eye_space.mean(axis=1)).astype(numpy.uint32)
        argb = numpy.round(colors[:, 3]).astype(numpy.uint32) << 24 | rgb[:, 0] << 16 | rgb[:, 1] << 8 | rgb[:, 2]
        order = numpy.argsort(-depth.mean(axis=1), kind="stable")  # painter's algorithm: far to near
        points = numpy.stack([x, y], axis=2).reshape(-1, 6)[order].tolist()
        painter = QPainter(image)
        painter.setPen(Qt.PenStyle.NoPen)
        try:
            brush = None
            for (x0, y0, x1, y1, x2, y2), colour in zip(points, argb[order].tolist()):
                if colour != brush:
                    painter.setBrush(QColor.fromRgba(colour))
                    brush = colour
                painter.drawConvexPolygon([QPoint(x0, y0), QPoint(x1, y1), QPoint(x2, y2)])
        finally:
            painter.end()
        self.drawn = len(points)


# --------------------------------------------------------------------------- the widget


class PreviewView(QWidget):
    """Interactive 3D view of a PreviewMesh, with OpenGL or (fallback) QPainter.

    ``set_mesh`` shows a model (and ends a message), ``set_message`` shows a text instead of the model
    ("" shows the model again). ``element_clicked`` carries the label of the clicked element, "" for
    the background.
    """

    element_clicked = Signal(str)
    renderer_changed = Signal(str)  # OPENGL or SOFTWARE, after a fallback

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.camera = Camera()
        self._scene: _Scene | None = None
        self._renderer: QWidget | None = None
        self._renderer_name = ""
        self._fitted = True  # the view still shows the fitted model: fit again when resized
        self._drag: dict | None = None
        self._wheel_point: tuple[QPointF, numpy.ndarray] | None = None
        self.setMinimumSize(120, 90)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._message = QLabel()
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet(f"background: {BACKGROUND.name()}; color: #5b6570; padding: 12px;")
        self._stack.addWidget(self._message)

        self._buttons = QFrame(self)
        self._buttons.setObjectName("viewButtons")
        self._buttons.setStyleSheet(
            "#viewButtons { background: rgba(255, 255, 255, 190); border-radius: 4px; }"
            "QPushButton { border: none; padding: 2px 5px; color: #2b3540; background: transparent; }"
            "QPushButton:hover { background: rgba(0, 0, 0, 25); border-radius: 3px; }"
        )
        font = self._buttons.font()
        font.setPointSizeF(font.pointSizeF() * 0.85)
        self._buttons.setFont(font)
        row = QHBoxLayout(self._buttons)
        row.setContentsMargins(1, 1, 1, 1)
        row.setSpacing(0)
        actions = [(text, tooltip, lambda _=False, v=view: self.set_view(v)) for view, text, tooltip in view_buttons()]
        actions.append((tr("All"), tr("Show the whole model (F, double-click)"), self.fit_view))
        for text, tooltip, slot in actions:
            button = QPushButton(text, self._buttons)  # flat by the style sheet; tool buttons get wide margins
            button.setToolTip(tooltip)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            row.addWidget(button)
        self._buttons.adjustSize()
        self._buttons.hide()

        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(lambda: self._renderer is not None and self._renderer.set_moving(False))

        problem = opengl_problem()
        if problem:
            self._use_software(problem)
        else:
            self._use_opengl()

    # -- public API

    @property
    def renderer_name(self) -> str:
        """OPENGL ("OpenGL") or SOFTWARE ("Software")."""
        return self._renderer_name

    @property
    def renderer_detail(self) -> str:
        """For the log or a tooltip: OpenGL version and graphics card, or why the software renderer draws."""
        return self._renderer.detail

    @property
    def mesh(self) -> PreviewMesh | None:
        return None if self._scene is None else self._scene.mesh

    def set_mesh(self, mesh: PreviewMesh | None) -> None:
        """Show ``mesh`` from the start view (None: an empty view)."""
        self._scene = _Scene(mesh) if mesh is not None else None
        if mesh is not None:
            self.camera.set_model(*mesh.bounds(), _fit_points(mesh))
        else:
            self.camera.set_model(numpy.zeros(3), numpy.zeros(3))
        self._renderer.set_scene(self._scene)
        self._message.setText("")
        self._stack.setCurrentWidget(self._renderer)
        self.reset_view()
        self._update_buttons()

    def set_message(self, text: str) -> None:
        """Show ``text`` instead of the model (e.g. "Vorschau wird berechnet … 34 %"); "" shows the model."""
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message if text else self._renderer)
        self._update_buttons()

    def message(self) -> str:
        return self._message.text()

    def reset_view(self) -> None:
        """The start view: isometric from south-west above, the whole model."""
        self.set_view("iso")

    def set_view(self, name: str) -> None:
        """One of VIEWS ("iso", "top", "front", "side"), showing the whole model."""
        self.camera.set_view(*VIEWS[name])
        self._view_changed(fitted=True)

    def fit_view(self) -> None:
        """The whole model, from the current direction."""
        self.camera.fit()
        self._view_changed(fitted=True)

    def element_at(self, x: float, y: float) -> str:
        """Label of the element at pixel (x, y) of the view, "" for the background."""
        triangle, _ = self._pick(QPointF(x, y))
        return "" if self._scene is None else self._scene.label(triangle)

    def image(self) -> QImage:
        """The model as currently drawn (without message and buttons), e.g. for tests or a thumbnail."""
        self._sync_viewport()
        return self._renderer.image()

    # -- renderers

    def _use_opengl(self) -> None:
        try:
            renderer = _gl_view_class()(self)
        except Exception as exc:  # e.g. QtOpenGL missing from a broken installation
            self._use_software(f"{type(exc).__name__}: {exc}")
            return
        renderer.failed.connect(self._use_software)
        self._install(renderer, OPENGL)

    def _use_software(self, reason: str) -> None:
        log.info("Vorschau mit Software-Darstellung (%s)", reason)
        old = self._renderer
        self._install(_SoftwareView(self, reason), SOFTWARE)
        if old is not None:
            self._stack.removeWidget(old)
            old.hide()
            old.deleteLater()
            self.renderer_changed.emit(SOFTWARE)

    def _install(self, renderer: QWidget, name: str) -> None:
        showing_model = self._renderer is None or self._stack.currentWidget() is self._renderer
        self._renderer, self._renderer_name = renderer, name
        renderer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        renderer.setMouseTracking(False)
        renderer.installEventFilter(self)
        renderer.set_scene(self._scene)
        self._stack.addWidget(renderer)
        if showing_model and not self._message.text():
            self._stack.setCurrentWidget(renderer)
        self._buttons.raise_()

    # -- interaction

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is not self._renderer:
            return False
        kind = event.type()
        handlers = {
            QEvent.Type.MouseButtonPress: self._press,
            QEvent.Type.MouseMove: self._move,
            QEvent.Type.MouseButtonRelease: self._release,
            QEvent.Type.MouseButtonDblClick: self._double_click,
            QEvent.Type.Wheel: self._wheel,
        }
        handler = handlers.get(kind)
        if handler is None:
            if kind == QEvent.Type.ContextMenu:
                return True  # the right button pans
            return False
        handler(event)
        return True

    def _press(self, event) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if self._drag is not None or self._scene is None:
            return
        button, position = event.button(), event.position()
        if button == Qt.MouseButton.LeftButton and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            mode = "orbit"
        elif button in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            mode = "pan"
        else:
            return
        triangle, point = self._pick(position)
        self._drag = {"mode": mode, "button": button, "start": position, "last": position, "moved": False,
                      "triangle": triangle, "point": point}

    def _move(self, event) -> None:
        drag = self._drag
        if drag is None:
            return
        position = event.position()
        if not drag["moved"]:
            if (position - drag["start"]).manhattanLength() <= CLICK_TOLERANCE:
                return
            drag["moved"] = True
            self._renderer.set_moving(True)
        dx, dy = position.x() - drag["last"].x(), position.y() - drag["last"].y()
        drag["last"] = position
        if drag["mode"] == "orbit":
            self.camera.orbit(dx, dy, drag["point"] if drag["point"] is not None else None)
        else:
            depth = self.camera.depth(drag["point"]) if drag["point"] is not None else None
            self.camera.pan(dx, dy, depth)
        self._view_changed()

    def _release(self, event) -> None:
        drag = self._drag
        if drag is None or event.button() != drag["button"]:
            return
        self._drag = None
        if drag["moved"]:
            self._renderer.set_moving(False)
        elif drag["button"] == Qt.MouseButton.LeftButton and self._scene is not None:
            self.element_clicked.emit(self._scene.label(drag["triangle"]))

    def _double_click(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            self.fit_view()

    def _wheel(self, event) -> None:
        if self._scene is None:
            return
        steps = event.angleDelta().y() / 120
        if not steps:
            return
        position = event.position()
        if self._wheel_point is not None and self._wheel_point[0] == position:
            point = self._wheel_point[1]  # zooming keeps it under the cursor: no need to pick again
        else:
            _, point = self._pick(position)
            if point is None:
                point = self.camera.point_at(position.x(), position.y())
        self.camera.zoom(ZOOM_STEP ** steps, point)
        self._view_changed()
        self._wheel_point = (QPointF(position), point)
        self._renderer.set_moving(True)
        self._settle.start()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in VIEW_KEYS:
            self.set_view(VIEW_KEYS[key])
        elif key == Qt.Key.Key_F:
            self.fit_view()
        elif key == Qt.Key.Key_Home:
            self.reset_view()
        else:
            super().keyPressEvent(event)

    def _pick(self, position: QPointF) -> tuple[int, numpy.ndarray | None]:
        """Triangle under ``position`` and the point hit on it, (-1, None) for the background."""
        if self._scene is None or self._renderer is None:
            return -1, None
        self._sync_viewport()
        try:
            triangle = self._renderer.pick(position.x(), position.y())
        except Exception:
            log.exception("Vorschau: Fehler bei der Auswahl")
            return -1, None
        if triangle < 0:
            return -1, None
        return triangle, self._scene.hit_point(triangle, self.camera, position.x(), position.y())

    def _view_changed(self, fitted: bool = False) -> None:
        self._fitted = fitted
        self._wheel_point = None
        if self._renderer is not None:
            self._renderer.update()

    def _sync_viewport(self) -> None:
        widget = self._renderer if self._renderer is not None and self._renderer.width() > 1 else self
        self.camera.set_viewport(widget.width(), widget.height())

    def _update_buttons(self) -> None:
        """The view buttons show while the mouse is over a model (the keys work anyway)."""
        self._buttons.setVisible(self._scene is not None and not self._message.text() and self.underMouse()
                                 and self.width() >= self._buttons.width() + 12)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._update_buttons()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._update_buttons()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.camera.set_viewport(self.width(), self.height())
        if self._fitted:
            self.camera.fit()
        self._wheel_point = None
        self._buttons.move(6, 6)
        self._update_buttons()
