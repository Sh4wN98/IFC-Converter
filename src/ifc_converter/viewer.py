"""3D view of a preview (preview.PreviewMesh) for the window, like the preview pane of Windows Explorer.

PreviewView draws with OpenGL 3.3 on the graphics card. Where that is not available (remote desktop,
virtual machines, CI runners without a GPU), or with IFC_CONVERTER_PREVIEW_RENDERER=software, it
draws with QPainter instead: fewer triangles, but it works everywhere. An OpenGL error does not end the
program: the view switches to QPainter and logs why.

Both renderers draw the same scene: a vertical gradient behind the model (light or dark, after the
window's palette), flat-shaded faces lit by the sky, the ground and a key light from the upper left
with a touch of gloss, dark feature edges along creases of 30° and more (switchable), a soft shadow on
the ground under the model, and an axis triad (x red, y green, z blue) in the lower left corner.

The triad and the label chip of the selected element are part of the rendered image (drawn with
QPainter by both renderers), not a widget over the view: on some Windows/NVIDIA setups a translucent
widget over a QOpenGLWidget is not composited and vanished together with the hover-only toolbar.

Controls: left drag orbits (around the clicked point), middle or right drag and Shift+left drag pan,
the wheel zooms towards the cursor, a double-click shows the whole model, a click on an element
highlights it, shows its label and emits element_clicked. Keys 1-4 (or the buttons) for the views
Iso, Top, Front, Side, F for the whole model, Home for the start view, E shows or hides the edges,
P switches between perspective and orthographic (parallel) projection, Esc clears the selection.
The buttons are a separate widget, ``view.toolbar`` (ViewToolbar), that the preview pane puts into
its header: always visible, enabled while a model is shown. The view changes animate briefly
(ANIMATION_MS); the options are reported through option_changed so that the window can keep them in
its settings. ``update_mesh`` replaces the model while it is still growing (progressive preview)
without resetting the view.
"""

from __future__ import annotations

import copy
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from functools import cache

import numpy
import shiboken6
from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer, \
    QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QMatrix4x4, QOffscreenSurface, QOpenGLContext, \
    QPainter, QPalette, QPen, QPixmap, QPolygonF, QRadialGradient, QSurfaceFormat, QTransform, \
    QVector3D, QVector4D
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedLayout, QWidget

from ifc_converter.i18n import tr
from ifc_converter.preview import PreviewMesh

log = logging.getLogger("ifc_converter.viewer")

# "software" draws with QPainter even where OpenGL works (e.g. if a graphics driver misbehaves).
RENDERER_ENV = "IFC_CONVERTER_PREVIEW_RENDERER"
OPENGL = "OpenGL"
SOFTWARE = "Software"
REQUIRED_VERSION = (3, 3)  # core profile, GLSL 3.30

PERSPECTIVE, ORTHOGRAPHIC = "perspective", "orthographic"
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
ANIMATION_MS = 250  # the view buttons, keys and the double-click glide to the new view this long

# Feature edges: creases of at least this angle between the faces, borders and non-manifold edges.
EDGE_ANGLE = 30.0
EDGE_TOLERANCE = 1e-4  # metres: vertices this close count as one (unwelded or split by material)
EDGES_IN_BACKGROUND = 300_000  # meshes with more triangles get their edges in a thread
EDGE_LIMIT = 6_000_000  # at most this many segments are kept
EDGES_WHILE_MOVING = 1_000_000  # more segments than this are drawn on still frames only (OpenGL)
# A growing model (update_mesh): its edges are computed in a thread once no newer mesh came for this long.
EDGE_SETTLE_MS = 3000
# The ground shadow: an ellipse this much larger than the model's footprint, just under its lowest point.
SHADOW_SPREAD = 1.35
SHADOW_FADE_PITCH = 12.0  # degrees: the shadow fades out as the camera looks up from below
TRIAD_SIZE = 22  # pixels, the length of an axis of the triad

# QPainter fallback: as many triangles (largest elements first) as it draws in about this time, when
# still and while the view moves; at most SOFTWARE_TRIANGLES.
SOFTWARE_SECONDS, SOFTWARE_MOVING_SECONDS = 0.7, 0.06
SOFTWARE_BUDGETS = (2_000, 5_000, 10_000, 20_000, 50_000, 100_000, 200_000)
SOFTWARE_TRIANGLES = SOFTWARE_BUDGETS[-1]
SPLIT_FRACTION = 16  # triangles longer than this part of the model's diagonal are split ...
SPLIT_GROWTH = 0.3  # ... adding at most this share of triangles
SETTLE_MS = 250  # full detail again this long after the last wheel step

# Light, all in view space: a hemisphere (sky above, ground below) as the ambient part, a soft key
# light from above left of the viewer (wrapped, so no face goes black) and a touch of gloss.
SKY_COLOR = numpy.array([0.50, 0.52, 0.56])
GROUND_COLOR = numpy.array([0.30, 0.29, 0.30])
KEY_LIGHT, KEY_WRAP = 0.55, 0.5
SPECULAR, SHININESS = 0.10, 28.0
LIGHT_DIRECTION = numpy.array([-0.35, 0.55, 1.0]) / numpy.linalg.norm([-0.35, 0.55, 1.0])
SELECTION_COLOR = QColor("#ff9b26")  # the selected element is tinted with this
SELECTION_MIX = 0.5


@dataclass(frozen=True)
class Theme:
    """The colours of the scene around the model, for a light or a dark window."""

    name: str
    top: QColor  # background gradient, top ...
    bottom: QColor  # ... and bottom
    edge: QColor  # feature edges (alpha: how strong)
    shadow: QColor  # the ground shadow at its centre (alpha: how strong)
    text: QColor  # messages and labels
    chip: QColor  # background of the label chip and the toolbar
    chip_border: QColor


LIGHT_THEME = Theme("light", QColor("#d9e1ea"), QColor("#fcfdfe"), QColor(24, 32, 42, 150), QColor(40, 48, 58, 135),
                    QColor("#4f5964"), QColor(255, 255, 255, 215), QColor(0, 0, 0, 28))
# On the dark background a shadow would not show: the model stands on a faintly lit floor instead.
DARK_THEME = Theme("dark", QColor("#3a3f45"), QColor("#121416"), QColor(0, 0, 0, 180), QColor(190, 200, 210, 34),
                   QColor("#c4c9ce"), QColor(30, 33, 37, 225), QColor(255, 255, 255, 30))
BACKGROUND = QColor("#eef1f4")  # the light background's mean, for callers that need one colour
AXIS_COLORS = {"x": QColor("#e0443e"), "y": QColor("#3f9d4a"), "z": QColor("#3579d8")}


def theme_for(palette: QPalette) -> Theme:
    """The light theme for a light window palette, the dark one for a dark one."""
    return DARK_THEME if palette.color(QPalette.ColorRole.Window).lightness() < 128 else LIGHT_THEME


def gradient_color(theme: Theme, fraction: float) -> tuple[int, int, int]:
    """The background colour ``fraction`` (0 top, 1 bottom) of the way down the view."""
    fraction = min(max(fraction, 0.0), 1.0)
    return tuple(int(round(getattr(theme.top, part)() * (1 - fraction) + getattr(theme.bottom, part)() * fraction))
                 for part in ("red", "green", "blue"))


# OpenGL constants (QOpenGLFunctions takes plain ints).
GL_DEPTH_BUFFER_BIT, GL_COLOR_BUFFER_BIT = 0x0100, 0x4000
GL_LINES, GL_TRIANGLES, GL_TRIANGLE_STRIP = 0x0001, 0x0004, 0x0005
GL_UNSIGNED_BYTE, GL_UNSIGNED_INT, GL_FLOAT = 0x1401, 0x1405, 0x1406
GL_DEPTH_TEST, GL_BLEND, GL_CULL_FACE, GL_MULTISAMPLE = 0x0B71, 0x0BE2, 0x0B44, 0x809D
GL_POLYGON_OFFSET_FILL, GL_LINE_SMOOTH = 0x8037, 0x0B20
GL_LESS, GL_LEQUAL = 0x0201, 0x0203
GL_ONE, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA = 0x0001, 0x0302, 0x0303
GL_VENDOR, GL_RENDERER, GL_VERSION = 0x1F00, 0x1F01, 0x1F02
GL_SCISSOR_TEST, GL_STENCIL_TEST = 0x0C11, 0x0B90

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
# winding of IFC geometry is not reliable, so both sides are lit alike). The light is the same as
# in _shade (the QPainter renderer).
FRAGMENT_SHADER = """
#version 330 core
in vec3 viewPosition;
in vec4 vertexColor;
uniform vec3 lightDirection;
uniform vec3 viewUp;
uniform vec3 skyColor;
uniform vec3 groundColor;
uniform vec4 key;   // key light, wrap, specular, shininess
uniform vec4 tint;  // rgb mixed in by a (the selected element)
out vec4 fragColor;
void main() {
    vec3 normal = normalize(cross(dFdx(viewPosition), dFdy(viewPosition)));
    if (dot(normal, viewPosition) > 0.0)
        normal = -normal;
    vec3 base = mix(vertexColor.rgb, tint.rgb, tint.a);
    float hemisphere = 0.5 + 0.5 * dot(normal, viewUp);
    vec3 ambient = mix(groundColor, skyColor, hemisphere);
    float diffuse = clamp((dot(normal, lightDirection) + key.y) / (1.0 + key.y), 0.0, 1.0);
    vec3 halfway = normalize(lightDirection - normalize(viewPosition));
    float gloss = pow(max(dot(normal, halfway), 0.0), key.w) * key.z;
    fragColor = vec4(min(base * (ambient + key.x * diffuse) + gloss, 1.0), vertexColor.a);
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
# Feature edges: the mesh's positions, one colour.
LINE_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 position;
uniform mat4 mvp;
void main() {
    gl_Position = mvp * vec4(position, 1.0);
}
"""
LINE_FRAGMENT_SHADER = """
#version 330 core
uniform vec4 color;
out vec4 fragColor;
void main() {
    fragColor = color;
}
"""
# The background: one triangle over the whole view, a vertical gradient.
BACKGROUND_VERTEX_SHADER = """
#version 330 core
out float fraction;
void main() {
    vec2 corner = vec2(float((gl_VertexID & 1) << 2) - 1.0, float((gl_VertexID & 2) << 1) - 1.0);
    fraction = 1.0 - corner.y * 0.5 - 0.5;
    gl_Position = vec4(corner, 0.999, 1.0);
}
"""
BACKGROUND_FRAGMENT_SHADER = """
#version 330 core
in float fraction;
uniform vec3 top;
uniform vec3 bottom;
out vec4 fragColor;
void main() {
    fragColor = vec4(mix(top, bottom, clamp(fraction, 0.0, 1.0)), 1.0);
}
"""
# The ground shadow: an ellipse (centre, two half axes) fading out towards its rim.
GROUND_VERTEX_SHADER = """
#version 330 core
uniform mat4 mvp;
uniform vec3 center;
uniform vec3 axisX;
uniform vec3 axisY;
out vec2 uv;
void main() {
    uv = vec2(float(gl_VertexID & 1) * 2.0 - 1.0, float((gl_VertexID >> 1) & 1) * 2.0 - 1.0);
    gl_Position = mvp * vec4(center + axisX * uv.x + axisY * uv.y, 1.0);
}
"""
GROUND_FRAGMENT_SHADER = """
#version 330 core
in vec2 uv;
uniform vec4 color;
out vec4 fragColor;
void main() {
    float fade = 1.0 - smoothstep(0.55, 1.0, length(uv));
    fragColor = vec4(color.rgb, color.a * fade);
}
"""


# --------------------------------------------------------------------------- camera


class Camera:
    """Turntable camera, Z up, in the coordinates of the mesh (relative to its origin), perspective
    or orthographic.

    The camera looks from ``eye()`` at ``target``, ``distance`` away, in the direction given by
    ``yaw`` and ``pitch`` (degrees). In the orthographic projection the view is as wide as the
    perspective one at the target, so switching keeps the model's size on screen. Pixel coordinates
    are logical widget pixels, origin top left.
    """

    def __init__(self) -> None:
        self.yaw, self.pitch = VIEWS["iso"]
        self.target = numpy.zeros(3)
        self.distance = 10.0
        self.orthographic = False
        self.center = numpy.zeros(3)  # the model's bounding box
        self.size = numpy.ones(3)
        self.points: numpy.ndarray | None = None  # sample of the model's vertices
        self.width, self.height = 1, 1

    @property
    def radius(self) -> float:
        """Half the diagonal of the model's box; at least 0.5 m so a point-like model can be looked at."""
        return max(0.5 * float(numpy.linalg.norm(self.size)), 0.5)

    @property
    def projection(self) -> str:
        return ORTHOGRAPHIC if self.orthographic else PERSPECTIVE

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

    @property
    def half_height(self) -> float:
        """Half the height of the view at the target, in metres."""
        return self.distance * math.tan(math.radians(FOV_Y) / 2)

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
        if self.orthographic:
            h = self.half_height
            return numpy.array([
                [1 / (h * self.aspect), 0, 0, 0],
                [0, 1 / h, 0, 0],
                [0, 0, -2 / (far - near), -(far + near) / (far - near)],
                [0, 0, 0, 1],
            ])
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
        depth = (points - self.eye()) @ self.basis()[2]
        return numpy.column_stack([x, y]), depth

    def ray(self, x: float, y: float) -> tuple[numpy.ndarray, numpy.ndarray]:
        """Origin and unit direction of the ray through pixel (x, y)."""
        right, up, forward = self.basis()
        nx, ny = 2 * x / self.width - 1, 1 - 2 * y / self.height
        if self.orthographic:
            h = self.half_height
            return self.eye() + right * nx * h * self.aspect + up * ny * h, forward
        ty = math.tan(math.radians(FOV_Y) / 2)
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
            if self.orthographic:
                distance = max(float(numpy.max(numpy.abs(x))) / tan_x, float(numpy.max(numpy.abs(y))) / tan_y,
                               float(numpy.max(-z)) + self.radius * 0.05, 0.01)
            else:
                distance = max(float(numpy.max(numpy.abs(x) / tan_x - z)), float(numpy.max(numpy.abs(y) / tan_y - z)),
                               float(numpy.max(-z)) + self.radius * 0.05, 0.01)
            if attempt == 3:
                break
            # Move the target so the model's extent on screen is centred, then fit again.
            depth = 1.0 if self.orthographic else z + distance
            screen_x, screen_y = x / depth, y / depth
            shift_x = (screen_x.max() + screen_x.min()) / 2
            shift_y = (screen_y.max() + screen_y.min()) / 2
            if abs(shift_x) < 1e-4 * tan_x and abs(shift_y) < 1e-4 * tan_y:
                break
            scale = 1.0 if self.orthographic else distance
            target = target + (right * shift_x + up * shift_y) * scale
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
        depth = self.distance if depth is None or depth <= 0 or self.orthographic else depth
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
        return (self.yaw, self.pitch, *self.target, self.distance, self.orthographic, self.width, self.height)

    def pose(self) -> tuple[float, float, numpy.ndarray, float]:
        """What an animation moves: yaw, pitch, target, distance."""
        return self.yaw, self.pitch, self.target.copy(), self.distance

    def set_pose(self, pose: tuple[float, float, numpy.ndarray, float]) -> None:
        self.yaw, self.pitch, self.target, self.distance = pose[0] % 360, pose[1], numpy.array(pose[2]), pose[3]


def interpolate_pose(start, end, fraction: float):
    """The pose ``fraction`` (0..1) of the way from ``start`` to ``end``: the shortest turn, the
    distance geometrically (a zoom feels even that way)."""
    yaw0, pitch0, target0, distance0 = start
    yaw1, pitch1, target1, distance1 = end
    turn = (yaw1 - yaw0 + 180) % 360 - 180
    return (
        yaw0 + turn * fraction,
        pitch0 + (pitch1 - pitch0) * fraction,
        numpy.asarray(target0, float) + (numpy.asarray(target1, float) - numpy.asarray(target0, float)) * fraction,
        distance0 * (distance1 / distance0) ** fraction if distance0 > 0 and distance1 > 0
        else distance0 + (distance1 - distance0) * fraction,
    )


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


def feature_edges(mesh: PreviewMesh, angle: float = EDGE_ANGLE,
                  tolerance: float = EDGE_TOLERANCE) -> tuple[numpy.ndarray, numpy.ndarray]:
    """The edges that make the model read as volumes: creases of at least ``angle`` degrees between
    two faces, borders of open surfaces and edges shared by more than two faces (where elements
    meet). Vertices within ``tolerance`` count as one, so unwelded meshes work too.

    Returns the segments (E, 2) uint32 as indices into the mesh's positions, and the flags (T, 3)
    of the triangles' edges (edge k runs from corner k to corner k + 1) for the QPainter renderer.
    """
    triangles = mesh.indices.reshape(-1, 3)
    if not len(triangles):
        return numpy.zeros((0, 2), numpy.uint32), numpy.zeros((0, 3), bool)
    quantized = numpy.round(mesh.positions.astype(numpy.float64) / tolerance).astype(numpy.int64)
    with numpy.errstate(over="ignore"):
        key = quantized[:, 0] * 73856093 ^ quantized[:, 1] * 19349663 ^ quantized[:, 2] * 83492791
    del quantized
    classes, vertex_class = numpy.unique(key, return_inverse=True)
    del key
    corner = vertex_class.reshape(-1).astype(numpy.int64)[triangles]  # (T, 3)
    other = corner[:, [1, 2, 0]]
    edge_key = numpy.minimum(corner, other) * len(classes) + numpy.maximum(corner, other)
    del corner, other, vertex_class
    _, inverse, counts = numpy.unique(edge_key.reshape(-1), return_inverse=True, return_counts=True)
    del edge_key
    inverse = inverse.reshape(-1)
    feature = counts != 2  # borders and where more than two faces meet
    slots = numpy.argsort(inverse, kind="stable")  # slot = 3 * triangle + k, grouped by edge
    starts = numpy.cumsum(counts) - counts
    pairs = numpy.flatnonzero(counts == 2)
    if len(pairs):
        first, second = slots[starts[pairs]] // 3, slots[starts[pairs] + 1] // 3
        normals = numpy.empty((len(triangles), 3), numpy.float32)
        for start in range(0, len(triangles), 500_000):  # bounded temporary memory
            points = mesh.positions[triangles[start:start + 500_000]].astype(numpy.float32)
            chunk = numpy.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
            length = numpy.linalg.norm(chunk, axis=1)
            normals[start:start + len(chunk)] = chunk / numpy.where(length > 0, length, 1)[:, None]
        agreement = numpy.abs(numpy.einsum("ij,ij->i", normals[first], normals[second]))
        feature[pairs] = agreement < math.cos(math.radians(angle))
        del normals, first, second, agreement
    flags = feature[inverse].reshape(-1, 3)
    chosen = slots[starts[feature]]
    t, k = chosen // 3, chosen % 3
    segments = numpy.column_stack([triangles[t, k], triangles[t, (k + 1) % 3]]).astype(numpy.uint32)
    return segments, flags


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
        self._draw_position: numpy.ndarray | None = None
        self.edges: numpy.ndarray | None = None  # (E, 2) feature edges, once computed
        self.edge_flags: numpy.ndarray | None = None  # (T, 3)
        self.edge_error = ""
        self.edge_thread: threading.Thread | None = None
        self._software: dict[int, _Flat] = {}
        self._rank: numpy.ndarray | None = None
        self._split_length = 1.0
        low, high = mesh.bounds()
        self.low, self.high = numpy.asarray(low, float), numpy.asarray(high, float)

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

    def element_of(self, triangle: int) -> int:
        return -1 if triangle < 0 else int(self.mesh.triangle_elements[triangle])

    def element_named(self, label: str) -> int:
        try:
            return self.mesh.elements.index(label) if label else -1
        except ValueError:
            return -1

    def draw_runs(self, element: int) -> list[tuple[int, int]]:
        """(first, count) runs of the element's triangles in draw order; usually one or two."""
        if element < 0:
            return []
        triangles = numpy.flatnonzero(self.mesh.triangle_elements == element)
        if not len(triangles):
            return []
        if self.order is not None:
            if self._draw_position is None:
                self._draw_position = numpy.empty(len(self.order), numpy.int64)
                self._draw_position[self.order] = numpy.arange(len(self.order))
            triangles = numpy.sort(self._draw_position[triangles])
        breaks = numpy.flatnonzero(numpy.diff(triangles) != 1) + 1
        return [(int(run[0]), len(run)) for run in numpy.split(triangles, breaks)]

    def compute_edges(self) -> None:
        """The feature edges (see feature_edges); an error leaves them None and is kept."""
        if self.edges is not None:
            return
        started = time.perf_counter()
        try:
            segments, flags = feature_edges(self.mesh)
        except Exception as exc:  # out of memory on a huge mesh: the model still shows, without edges
            log.warning("Vorschau: keine Kanten (%s: %s)", type(exc).__name__, exc)
            self.edge_error = f"{type(exc).__name__}: {exc}"
            return
        if len(segments) > EDGE_LIMIT:
            segments = segments[:EDGE_LIMIT]
        self.edge_flags = flags
        self.edges = segments  # set last: the renderers read ``edges`` to see whether they are ready
        self._software = {k: v for k, v in self._software.items() if v.edges is not None}
        log.debug("Vorschau: %d Kanten in %.2f s", len(segments), time.perf_counter() - started)

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

    def shadow(self) -> tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray]:
        """Centre and half axes (x, y) of the ground shadow ellipse, just under the model."""
        half = (self.high - self.low) / 2
        radius = max(float(numpy.linalg.norm(half)), 0.5)
        spread = numpy.maximum(half[:2] * SHADOW_SPREAD, radius * 0.1)
        center = numpy.array([(self.low[0] + self.high[0]) / 2, (self.low[1] + self.high[1]) / 2,
                              self.low[2] - max(radius * 2e-3, 1e-3)])
        return center, numpy.array([spread[0], 0.0, 0.0]), numpy.array([0.0, spread[1], 0.0])

    def software(self, budget: int) -> _Flat:
        """About ``budget`` triangles for QPainter: those of the largest elements (by surface) first,
        large ones split so that drawing back to front (painter's algorithm) stays mostly right."""
        if budget not in self._software:
            chosen = numpy.sort(self._ranked()[:int(budget / (1 + SPLIT_GROWTH))])
            corners = self.mesh.positions[self.triangles[chosen]].astype(numpy.float32)
            colors = self.mesh.colors[self.triangles[chosen]].astype(numpy.float32).mean(axis=1)
            edges = None if self.edge_flags is None else self.edge_flags[chosen]
            self._software[budget] = _split_large(_Flat(corners, colors, chosen, edges), budget, self._split_length)
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
            self._split_length = max(float(numpy.linalg.norm(self.high - self.low)) / SPLIT_FRACTION, 1e-3)
        return self._rank


@dataclass
class _Flat:
    """Triangles for QPainter: corners (N, 3, 3) and RGBA (N, 4) as float32, mesh triangle of each,
    and which of their edges are feature edges (N, 3) bool, or None while unknown."""

    corners: numpy.ndarray
    colors: numpy.ndarray
    source: numpy.ndarray
    edges: numpy.ndarray | None = None

    def __len__(self) -> int:
        return len(self.corners)


def _split_large(flat: _Flat, limit: int, length: float) -> _Flat:
    """Bisect triangles at their longest edge until none is longer than ``length`` (or ``limit`` is reached).

    Changes the arrays of ``flat``."""
    corners, colors, source, edges = flat.corners, flat.colors, flat.source, flat.edges
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
        if edges is not None:
            flags = edges[big]
            ab, bc, ca = flags[rows, k], flags[rows, (k + 1) % 3], flags[rows, (k + 2) % 3]
            none = numpy.zeros(len(big), bool)
            edges[big] = numpy.stack([ab, none, ca], axis=1)  # (a, m, c): a-m, m-c, c-a
            edges = numpy.concatenate([edges, numpy.stack([ab, bc, none], axis=1)])  # (m, b, c)
    return _Flat(corners, colors, source, edges)


def _shade(colors: numpy.ndarray, normals: numpy.ndarray, up: numpy.ndarray, centroids: numpy.ndarray) -> numpy.ndarray:
    """RGB (N, 3) of flat-shaded triangles like the fragment shader: colours 0..255, all in view space."""
    flip = numpy.einsum("ij,ij->i", normals, centroids) > 0
    normals = numpy.where(flip[:, None], -normals, normals)
    hemisphere = 0.5 + 0.5 * (normals @ up)
    ambient = GROUND_COLOR + (SKY_COLOR - GROUND_COLOR) * hemisphere[:, None]
    diffuse = numpy.clip((normals @ LIGHT_DIRECTION + KEY_WRAP) / (1 + KEY_WRAP), 0, 1)
    length = numpy.linalg.norm(centroids, axis=1)
    to_eye = -centroids / numpy.where(length > 0, length, 1)[:, None]
    half = LIGHT_DIRECTION + to_eye
    half /= numpy.maximum(numpy.linalg.norm(half, axis=1), 1e-12)[:, None]
    gloss = numpy.maximum(numpy.einsum("ij,ij->i", normals, half), 0) ** SHININESS * SPECULAR
    return numpy.minimum(colors * (ambient + KEY_LIGHT * diffuse[:, None]) + gloss[:, None] * 255, 255)


def _tinted(colors: numpy.ndarray, mask: numpy.ndarray) -> numpy.ndarray:
    """``colors`` (N, 4) float with the rows of ``mask`` tinted with the selection colour."""
    if not mask.any():
        return colors
    tint = numpy.array([SELECTION_COLOR.red(), SELECTION_COLOR.green(), SELECTION_COLOR.blue()], numpy.float32)
    colors = colors.copy()
    colors[mask, :3] = colors[mask, :3] * (1 - SELECTION_MIX) + tint * SELECTION_MIX
    return colors


# --------------------------------------------------------------------------- OpenGL


def _surface_format() -> QSurfaceFormat:
    surface = QSurfaceFormat()
    surface.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    surface.setVersion(*REQUIRED_VERSION)
    surface.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface.setDepthBufferSize(24)
    surface.setSamples(4)  # 4x MSAA where the driver offers it; it falls back to fewer or none itself
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
                log.info("Vorschau mit OpenGL: %s, %s (%s), %dx MSAA", functions.glGetString(GL_VERSION),
                         functions.glGetString(GL_RENDERER), functions.glGetString(GL_VENDOR),
                         context.format().samples())
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


def _qvector(vector) -> QVector3D:
    return QVector3D(*(float(value) for value in vector))


def _qcolor(color: QColor) -> QVector4D:
    return QVector4D(color.redF(), color.greenF(), color.blueF(), color.alphaF())


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
            self._uploaded_edges: numpy.ndarray | None = None
            self._gl = None  # resources of the current context
            self._broken = False
            self._moving = False
            self.detail = ""  # OpenGL version and graphics card, once initialized
            self.samples = 0  # MSAA samples of the context, once initialized
            self._decoration_error = False

        # -- what PreviewView calls

        def set_scene(self, scene: _Scene | None) -> None:
            self._scene = scene
            self.update()

        def set_moving(self, moving: bool) -> None:
            if moving != self._moving:
                self._moving = moving
                self.update()

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
            self._uploaded_edges = None
            try:
                context = self.context()
                problem = _version_problem(context)
                if problem:
                    raise RuntimeError(problem)
                functions = context.functions()
                self.samples = context.format().samples()
                self.detail = f"{functions.glGetString(GL_VERSION)}, {functions.glGetString(GL_RENDERER)}"
                programs = {}
                for name, vertex, fragment in (
                    ("draw", VERTEX_SHADER, FRAGMENT_SHADER),
                    ("pick", VERTEX_SHADER, PICK_SHADER),
                    ("line", LINE_VERTEX_SHADER, LINE_FRAGMENT_SHADER),
                    ("background", BACKGROUND_VERTEX_SHADER, BACKGROUND_FRAGMENT_SHADER),
                    ("ground", GROUND_VERTEX_SHADER, GROUND_FRAGMENT_SHADER),
                ):
                    program = QOpenGLShaderProgram(self)
                    if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vertex) \
                            or not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragment) \
                            or not program.link():
                        raise RuntimeError(f"Shader: {program.log().strip()}")
                    programs[name] = program
                vao, aux = QOpenGLVertexArrayObject(self), QOpenGLVertexArrayObject(self)
                if not vao.create() or not aux.create():
                    raise RuntimeError("kein Vertex Array Object")
                fbo = QOpenGLFramebufferObject(QSize(PICK_SIZE, PICK_SIZE),
                                               QOpenGLFramebufferObject.Attachment.Depth)
                if not fbo.isValid():
                    raise RuntimeError("kein Framebuffer für die Auswahl")
                # Freed with the context (or when replaced here): Qt's GL objects guard against a context
                # that is already gone.
                self._gl = {"f": functions, "programs": programs, "vao": vao, "aux": aux, "fbo": fbo,
                            "buffers": [], "index": None, "edges": None}
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
                return
            if self._scene is not None:
                self._paint_decorations()

        def _paint_decorations(self) -> None:
            """The triad and the label chip, with QPainter into the widget's framebuffer (after the GL
            passes, so the GL state they leave does not matter; _paint resets what it needs)."""
            painter = QPainter(self)
            if not painter.isActive():
                return
            try:
                self._owner.paint_decorations(painter, self.width(), self.height())
            except Exception:  # a missing font must not take the model with it
                if not self._decoration_error:
                    self._decoration_error = True
                    log.exception("Vorschau: Achsenkreuz nicht gezeichnet")
            finally:
                painter.end()

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
            gl["buffers"], gl["index"], gl["edges"] = [], None, None
            self._uploaded_edges = None
            mesh = scene.mesh
            vertex, index = QOpenGLBuffer.Type.VertexBuffer, QOpenGLBuffer.Type.IndexBuffer
            data = [  # (buffer type, array, (attribute location, type, components) or None)
                (vertex, numpy.ascontiguousarray(mesh.positions, numpy.float32), (0, GL_FLOAT, 3)),
                (vertex, numpy.ascontiguousarray(mesh.colors, numpy.uint8), (1, GL_UNSIGNED_BYTE, 4)),
                (index, scene.draw_indices(), None),
            ]
            vao, program = gl["vao"], gl["programs"]["draw"]
            vao.bind()
            try:
                for kind, array, attribute in data:
                    buffer = self._buffer(kind, array)
                    gl["buffers"].append(buffer)
                    if attribute is not None:
                        location, gl_type, size = attribute
                        program.enableAttributeArray(location)
                        program.setAttributeBuffer(location, gl_type, 0, size, array.itemsize * size)  # normalized
                    else:
                        gl["index"] = buffer
            finally:
                vao.release()
            error = gl["f"].glGetError()
            if error:
                raise RuntimeError(f"OpenGL-Fehler 0x{error:04X} beim Hochladen (zu wenig Grafikspeicher?)")
            self._uploaded = scene
            log.debug("Vorschau hochgeladen: %d Dreiecke in %.2f s", scene.triangle_count,
                      time.perf_counter() - started)

        def _buffer(self, kind, array: numpy.ndarray):
            buffer = QOpenGLBuffer(kind)
            if not buffer.create():
                raise RuntimeError("kein Puffer")
            buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)
            buffer.bind()
            buffer.allocate(array.data, array.nbytes)  # bytes go straight from numpy to the driver
            return buffer

        def _upload_edges(self, scene: _Scene) -> None:
            """The feature edges as a second index buffer (once they are computed).

            Called with the VAO bound, whose element buffer binding is what gets bound here: the
            mesh's index buffer is put back at the end, so the VAO never points at no buffer (then
            the next glDrawElements would read its offset as an address and crash the window)."""
            gl = self._gl
            if gl["edges"] is not None:
                gl["edges"].destroy()
                gl["edges"] = None
            if scene.edges is not None and len(scene.edges):
                segments = numpy.ascontiguousarray(scene.edges, numpy.uint32).reshape(-1)
                gl["edges"] = self._buffer(QOpenGLBuffer.Type.IndexBuffer, segments)
                error = gl["f"].glGetError()
                if error:
                    raise RuntimeError(f"OpenGL-Fehler 0x{error:04X} beim Hochladen der Kanten")
            if gl["index"] is not None:
                gl["index"].bind()
            self._uploaded_edges = scene.edges

        def _paint(self) -> None:
            f = self._gl["f"]
            _clear_errors(f)  # e.g. left by Qt's own drawing: only errors of this frame count
            theme = self._owner.theme
            # QPainter (the decorations of the last frame) may leave a scissor or stencil test behind.
            f.glDisable(GL_SCISSOR_TEST)
            f.glDisable(GL_STENCIL_TEST)
            f.glDepthMask(True)
            f.glClearColor(theme.bottom.redF(), theme.bottom.greenF(), theme.bottom.blueF(), 1.0)
            f.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            f.glDisable(GL_CULL_FACE)
            if self.samples:
                f.glEnable(GL_MULTISAMPLE)
            self._paint_background(theme)
            if not self._ready() or not self._scene.triangle_count:
                return
            scene, gl, camera = self._scene, self._gl, self._owner.camera
            camera.set_viewport(self.width(), self.height())
            view = camera.view_matrix()
            mvp = _qmatrix(camera.projection_matrix() @ view)
            program = gl["programs"]["draw"]
            program.bind()
            uniform = program.uniformLocation
            program.setUniformValue(uniform("mvp"), mvp)
            program.setUniformValue(uniform("modelView"), _qmatrix(view))
            program.setUniformValue(uniform("lightDirection"), _qvector(LIGHT_DIRECTION))
            program.setUniformValue(uniform("viewUp"), _qvector(view[:3, 2]))
            program.setUniformValue(uniform("skyColor"), _qvector(SKY_COLOR))
            program.setUniformValue(uniform("groundColor"), _qvector(GROUND_COLOR))
            program.setUniformValue(uniform("key"), QVector4D(KEY_LIGHT, KEY_WRAP, SPECULAR, SHININESS))
            program.setUniformValue(uniform("tint"), QVector4D(0, 0, 0, 0))
            f.glEnable(GL_DEPTH_TEST)
            f.glDepthFunc(GL_LESS)
            f.glEnable(GL_POLYGON_OFFSET_FILL)  # faces a little behind their edges
            f.glPolygonOffset(1.0, 1.0)
            gl["vao"].bind()
            try:
                if scene.opaque_count:
                    f.glDisable(GL_BLEND)
                    f.glDrawElements(GL_TRIANGLES, 3 * scene.opaque_count, GL_UNSIGNED_INT, _offset(0))
                program.release()
                f.glEnable(GL_BLEND)
                f.glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
                f.glDepthMask(False)
                self._paint_ground(scene, camera, mvp, theme)
                program.bind()
                transparent = scene.triangle_count - scene.opaque_count
                if transparent:  # glass after everything else, without hiding what lies behind it
                    f.glDrawElements(GL_TRIANGLES, 3 * transparent, GL_UNSIGNED_INT, _offset(12 * scene.opaque_count))
                selected = self._owner.selected_element
                if selected >= 0:  # the selected element again, tinted, over its first drawing
                    f.glDepthFunc(GL_LEQUAL)
                    program.setUniformValue(uniform("tint"), QVector4D(SELECTION_COLOR.redF(), SELECTION_COLOR.greenF(),
                                                                       SELECTION_COLOR.blueF(), SELECTION_MIX))
                    for first, count in scene.draw_runs(selected):
                        f.glDrawElements(GL_TRIANGLES, 3 * count, GL_UNSIGNED_INT, _offset(12 * first))
                    f.glDepthFunc(GL_LESS)
                f.glDepthMask(True)
                program.release()
                f.glDisable(GL_POLYGON_OFFSET_FILL)
                if self._owner.edges_visible:
                    self._paint_edges(scene, mvp, theme)
                f.glDisable(GL_BLEND)
            finally:
                gl["vao"].release()
                program.release()
            error = f.glGetError()
            if error:
                raise RuntimeError(f"OpenGL-Fehler 0x{error:04X} beim Zeichnen")

        def _paint_background(self, theme: Theme) -> None:
            f, gl = self._gl["f"], self._gl
            program = gl["programs"]["background"]
            f.glDisable(GL_DEPTH_TEST)
            f.glDepthMask(False)
            f.glDisable(GL_BLEND)
            program.bind()
            program.setUniformValue(program.uniformLocation("top"), QVector3D(theme.top.redF(), theme.top.greenF(),
                                                                              theme.top.blueF()))
            program.setUniformValue(program.uniformLocation("bottom"),
                                    QVector3D(theme.bottom.redF(), theme.bottom.greenF(), theme.bottom.blueF()))
            gl["aux"].bind()
            f.glDrawArrays(GL_TRIANGLES, 0, 3)
            gl["aux"].release()
            program.release()
            f.glDepthMask(True)

        def _paint_ground(self, scene: _Scene, camera: Camera, mvp: QMatrix4x4, theme: Theme) -> None:
            """The soft shadow under the model (blending on, depth writes off)."""
            strength = min(max(-camera.pitch / SHADOW_FADE_PITCH, 0.0), 1.0)
            if strength <= 0:
                return
            f, gl = self._gl["f"], self._gl
            program = gl["programs"]["ground"]
            center, axis_x, axis_y = scene.shadow()
            color = QColor(theme.shadow)
            color.setAlphaF(theme.shadow.alphaF() * strength)
            gl["vao"].release()
            gl["aux"].bind()
            program.bind()
            program.setUniformValue(program.uniformLocation("mvp"), mvp)
            program.setUniformValue(program.uniformLocation("center"), _qvector(center))
            program.setUniformValue(program.uniformLocation("axisX"), _qvector(axis_x))
            program.setUniformValue(program.uniformLocation("axisY"), _qvector(axis_y))
            program.setUniformValue(program.uniformLocation("color"), _qcolor(color))
            f.glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
            program.release()
            gl["aux"].release()
            gl["vao"].bind()

        def _paint_edges(self, scene: _Scene, mvp: QMatrix4x4, theme: Theme) -> None:
            """The feature edges as lines (the VAO is bound; its index buffer is put back afterwards)."""
            f, gl = self._gl["f"], self._gl
            if self._uploaded_edges is not scene.edges:
                self._upload_edges(scene)
            edges = gl["edges"]
            if edges is None or (self._moving and len(scene.edges) > EDGES_WHILE_MOVING):
                return
            program = gl["programs"]["line"]
            program.bind()
            program.setUniformValue(program.uniformLocation("mvp"), mvp)
            program.setUniformValue(program.uniformLocation("color"), _qcolor(theme.edge))
            f.glLineWidth(1.0)
            if not self.samples:  # no MSAA: ask for smooth lines where the driver still has them
                f.glEnable(GL_LINE_SMOOTH)
                _clear_errors(f)
            edges.bind()
            try:
                f.glDrawElements(GL_LINES, 2 * len(scene.edges), GL_UNSIGNED_INT, _offset(0))
            finally:
                gl["index"].bind()
                program.release()
                if not self.samples:
                    f.glDisable(GL_LINE_SMOOTH)
                    _clear_errors(f)

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
            f, fbo, program = gl["f"], gl["fbo"], gl["programs"]["pick"]
            fbo.bind()
            try:
                f.glViewport(0, 0, PICK_SIZE, PICK_SIZE)
                f.glClearColor(0, 0, 0, 1)
                f.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                f.glEnable(GL_DEPTH_TEST)
                f.glDepthFunc(GL_LESS)
                f.glDisable(GL_BLEND)
                f.glDisable(GL_MULTISAMPLE)
                f.glDisable(GL_POLYGON_OFFSET_FILL)
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
    a still view takes about SOFTWARE_SECONDS and a moving one SOFTWARE_MOVING_SECONDS. The feature
    edges are drawn (antialiased) on still frames only.
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
        camera, owner = self._owner.camera, self._owner
        camera.set_viewport(self.width(), self.height())
        ratio = self.devicePixelRatioF()
        theme = owner.theme
        edges = owner.edges_visible and self._scene is not None and self._scene.edges is not None
        key = (camera.state(), ratio, self._moving, id(self._scene), theme.name, edges, owner.selected_element)
        if self._cache is not None and self._cache[0] == key:
            return self._cache[1]
        image = QImage(round(camera.width * ratio), round(camera.height * ratio),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        painter = QPainter(image)
        gradient = QLinearGradient(0, 0, 0, camera.height)
        gradient.setColorAt(0, theme.top)
        gradient.setColorAt(1, theme.bottom)
        painter.fillRect(QRectF(0, 0, camera.width, camera.height), gradient)
        painter.end()
        self.drawn = 0
        if self._scene is not None and self._scene.triangle_count:
            try:
                self._draw_ground(image, camera, theme)
                flat = self._scene.software(self.budget(self._moving))
                started = time.perf_counter()
                self._draw(image, camera, flat, theme, edges and not self._moving)
                if len(flat) >= 1000:
                    measured = (time.perf_counter() - started) / len(flat)
                    self._seconds_per_triangle = (self._seconds_per_triangle + measured) / 2
            except Exception:  # a broken frame must not end the program
                log.exception("Vorschau: Fehler beim Zeichnen")
        if self._scene is not None:
            painter = QPainter(image)
            try:
                owner.paint_decorations(painter, camera.width, camera.height)
            except Exception:
                log.exception("Vorschau: Achsenkreuz nicht gezeichnet")
            finally:
                painter.end()
        self._cache = (key, image)
        return image

    def _draw_ground(self, image: QImage, camera: Camera, theme: Theme) -> None:
        """The soft shadow under the model: the ellipse as seen, filled with a radial gradient."""
        strength = min(max(-camera.pitch / SHADOW_FADE_PITCH, 0.0), 1.0)
        if strength <= 0:
            return
        center, axis_x, axis_y = self._scene.shadow()
        angles = numpy.linspace(0, 2 * math.pi, 48, endpoint=False)
        rim = center + numpy.outer(numpy.cos(angles), axis_x) + numpy.outer(numpy.sin(angles), axis_y)
        pixels, depth = camera.project(numpy.vstack([rim, center, center + axis_x, center + axis_y]))
        near, _ = camera.clip_planes()
        if (depth <= near).any() or not numpy.isfinite(pixels).all():
            return
        colour = QColor(theme.shadow)
        colour.setAlphaF(theme.shadow.alphaF() * strength)
        clear = QColor(colour)
        clear.setAlpha(0)
        # An affine map of the unit circle onto the ellipse as seen (good enough for a shadow).
        c, px, py = pixels[-3], pixels[-2], pixels[-1]
        transform = QTransform(px[0] - c[0], px[1] - c[1], py[0] - c[0], py[1] - c[1], c[0], c[1])
        gradient = QRadialGradient(QPointF(0, 0), 1.0)
        gradient.setColorAt(0.0, colour)
        gradient.setColorAt(0.55, colour)
        gradient.setColorAt(1.0, clear)
        gradient.setCoordinateMode(QRadialGradient.CoordinateMode.LogicalMode)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setTransform(transform)
        painter.setBrush(gradient)
        painter.drawEllipse(QPointF(0, 0), 1.0, 1.0)
        painter.end()

    def _draw(self, image: QImage, camera: Camera, flat: _Flat, theme: Theme, edges: bool) -> None:
        view = camera.view_matrix()
        eye_space = flat.corners.astype(float) @ view[:3, :3].T + view[:3, 3]  # (N, 3, 3)
        depth = -eye_space[..., 2]  # in front of the eye > 0
        near, _ = camera.clip_planes()
        visible = (depth > near).all(axis=1)  # triangles through the near plane are left out
        f = 1 / math.tan(math.radians(FOV_Y) / 2)
        scale = camera.distance if camera.orthographic else depth
        with numpy.errstate(divide="ignore", invalid="ignore"):
            x = (eye_space[..., 0] * f / camera.aspect / scale + 1) / 2 * camera.width
            y = (1 - eye_space[..., 1] * f / scale) / 2 * camera.height
        visible &= ~((x < 0).all(axis=1) | (x > camera.width).all(axis=1) | (y < 0).all(axis=1)
                     | (y > camera.height).all(axis=1))
        if not visible.any():
            return
        eye_space, depth, colors = eye_space[visible], depth[visible], flat.colors[visible]
        selected = self._owner.selected_element
        if selected >= 0:
            colors = _tinted(colors, self._scene.mesh.triangle_elements[flat.source[visible]] == selected)
        x, y = x[visible], y[visible]
        xi, yi = numpy.round(x).astype(numpy.int32), numpy.round(y).astype(numpy.int32)
        normals = numpy.cross(eye_space[:, 1] - eye_space[:, 0], eye_space[:, 2] - eye_space[:, 0])
        length = numpy.linalg.norm(normals, axis=1)
        normals /= numpy.where(length > 0, length, 1)[:, None]
        rgb = _shade(colors[:, :3], normals, view[:3, 2], eye_space.mean(axis=1)).astype(numpy.uint32)
        argb = numpy.round(colors[:, 3]).astype(numpy.uint32) << 24 | rgb[:, 0] << 16 | rgb[:, 1] << 8 | rgb[:, 2]
        order = numpy.argsort(-depth.mean(axis=1), kind="stable")  # painter's algorithm: far to near
        points = numpy.stack([xi, yi], axis=2).reshape(-1, 6)[order].tolist()
        lines = None
        if edges and flat.edges is not None:
            lines = [row if any(row) else None for row in flat.edges[visible][order].tolist()]
            exact = numpy.stack([x, y], axis=2).reshape(-1, 6)[order].tolist()
        painter = QPainter(image)
        painter.setPen(Qt.PenStyle.NoPen)
        pen = QPen(theme.edge, 1.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        try:
            brush = None
            for number, ((x0, y0, x1, y1, x2, y2), colour) in enumerate(zip(points, argb[order].tolist())):
                if colour != brush:
                    painter.setBrush(QColor.fromRgba(colour))
                    brush = colour
                painter.drawConvexPolygon([QPoint(x0, y0), QPoint(x1, y1), QPoint(x2, y2)])
                if lines is not None and lines[number] is not None:
                    fx0, fy0, fx1, fy1, fx2, fy2 = exact[number]
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setPen(pen)
                    flag = lines[number]
                    if flag[0]:
                        painter.drawLine(QPointF(fx0, fy0), QPointF(fx1, fy1))
                    if flag[1]:
                        painter.drawLine(QPointF(fx1, fy1), QPointF(fx2, fy2))
                    if flag[2]:
                        painter.drawLine(QPointF(fx2, fy2), QPointF(fx0, fy0))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        finally:
            painter.end()
        self.drawn = len(points)


# --------------------------------------------------------------------------- triad, chip and toolbar


def draw_triad(painter: QPainter, camera: Camera, theme: Theme, origin: QPointF) -> None:
    """The world axes as seen, x red, y green, z blue, letters at the tips (far axes first)."""
    right, up, forward = camera.basis()
    axes = []
    for name, axis in (("x", (1, 0, 0)), ("y", (0, 1, 0)), ("z", (0, 0, 1))):
        axis = numpy.asarray(axis, float)
        axes.append((float(axis @ forward), name, float(axis @ right), -float(axis @ up)))
    font = painter.font()
    font.setPointSizeF(max(font.pointSizeF() * 0.8, 6.5))
    font.setBold(True)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    for away, name, dx, dy in sorted(axes):
        colour = QColor(AXIS_COLORS[name])
        if away > 0.3:  # pointing away from the viewer: fainter
            colour.setAlphaF(0.55)
        tip = QPointF(origin.x() + dx * TRIAD_SIZE, origin.y() + dy * TRIAD_SIZE)
        pen = QPen(colour, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(origin, tip)
        label = QPointF(origin.x() + dx * (TRIAD_SIZE + 8), origin.y() + dy * (TRIAD_SIZE + 8))
        width = metrics.horizontalAdvance(name)
        painter.setPen(QPen(theme.text if away > 0.3 else colour))
        painter.drawText(QPointF(label.x() - width / 2, label.y() + metrics.ascent() / 2 - 1), name)
    painter.setPen(QPen(theme.text, 1.0))
    painter.setBrush(theme.chip)
    painter.drawEllipse(origin, 2.5, 2.5)


def draw_chip(painter: QPainter, theme: Theme, label: str, width: float, height: float) -> None:
    """The label of the selected element in a rounded chip at the bottom, shortened to the width."""
    if not label:
        return
    font = painter.font()
    font.setBold(False)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    room = width - 2 * (TRIAD_SIZE + 24) - 24
    if room < 60:
        return
    text = metrics.elidedText(label, Qt.TextElideMode.ElideMiddle, int(room))
    chip_width, chip_height = metrics.horizontalAdvance(text) + 20, metrics.height() + 8
    rect = QRectF((width - chip_width) / 2, height - chip_height - 10, chip_width, chip_height)
    painter.setPen(QPen(theme.chip_border, 1.0))
    painter.setBrush(theme.chip)
    painter.drawRoundedRect(rect, chip_height / 2, chip_height / 2)
    painter.setPen(QPen(theme.text))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def _icon(kind: str, colour: QColor, size: int = 16) -> QIcon:
    """A small line icon for the toolbar, drawn for the common device pixel ratios."""
    icon = QIcon()
    for ratio in (1, 2, 3):
        pixmap = QPixmap(size * ratio, size * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(colour, 1.4)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        _draw_icon(painter, kind, size, colour)
        painter.end()
        icon.addPixmap(pixmap)
        faint = QPixmap(pixmap.size())
        faint.setDevicePixelRatio(ratio)
        faint.fill(Qt.GlobalColor.transparent)
        painter = QPainter(faint)
        painter.setOpacity(0.35)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        icon.addPixmap(faint, QIcon.Mode.Disabled)
    return icon


def _draw_icon(painter: QPainter, kind: str, size: int, colour: QColor) -> None:
    s = size
    cube = [QPointF(s * 0.5, s * 0.12), QPointF(s * 0.88, s * 0.32), QPointF(s * 0.88, s * 0.7),
            QPointF(s * 0.5, s * 0.9), QPointF(s * 0.12, s * 0.7), QPointF(s * 0.12, s * 0.32)]
    centre = QPointF(s * 0.5, s * 0.5)
    if kind == "iso":
        painter.drawPolygon(QPolygonF(cube))
        for corner in (cube[1], cube[3], cube[5]):
            painter.drawLine(centre, corner)
    elif kind == "top":
        painter.drawRect(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
        painter.drawLine(QPointF(s * 0.18, s * 0.5), QPointF(s * 0.82, s * 0.5))
        painter.drawLine(QPointF(s * 0.5, s * 0.5), QPointF(s * 0.5, s * 0.82))
    elif kind == "front":
        painter.drawPolygon(QPolygonF([QPointF(s * 0.15, s * 0.85), QPointF(s * 0.15, s * 0.45), QPointF(s * 0.5, s * 0.15),
                                       QPointF(s * 0.85, s * 0.45), QPointF(s * 0.85, s * 0.85)]))
        painter.drawRect(QRectF(s * 0.42, s * 0.6, s * 0.16, s * 0.25))
    elif kind == "side":
        painter.drawRect(QRectF(s * 0.2, s * 0.15, s * 0.6, s * 0.7))
        painter.drawLine(QPointF(s * 0.2, s * 0.5), QPointF(s * 0.8, s * 0.5))
        painter.drawLine(QPointF(s * 0.2, s * 0.5), QPointF(s * 0.5, s * 0.15))
    elif kind == "fit":
        a, b, c = s * 0.12, s * 0.88, s * 0.28
        for x, y, dx, dy in ((a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)):
            painter.drawPolyline(QPolygonF([QPointF(x, y + dy * c), QPointF(x, y), QPointF(x + dx * c, y)]))
        painter.drawRect(QRectF(s * 0.38, s * 0.38, s * 0.24, s * 0.24))
    elif kind == "edges":
        faint = QColor(colour)
        faint.setAlphaF(0.28)
        painter.setBrush(faint)
        painter.drawPolygon(QPolygonF(cube))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = painter.pen()
        pen.setWidthF(2.0)
        painter.setPen(pen)
        for corner in (cube[1], cube[3], cube[5]):
            painter.drawLine(centre, corner)
    elif kind == "projection":  # a frustum: converging lines, the near and the far edge
        painter.drawPolygon(QPolygonF([QPointF(s * 0.3, s * 0.2), QPointF(s * 0.7, s * 0.2), QPointF(s * 0.9, s * 0.82),
                                       QPointF(s * 0.1, s * 0.82)]))
        painter.drawLine(QPointF(s * 0.2, s * 0.5), QPointF(s * 0.8, s * 0.5))


TOOLBAR_ICON = QSize(16, 16)


def toolbar_actions() -> list[tuple[str, str, str]]:
    """(name, icon kind, tooltip) of the toolbar buttons, in the user interface language."""
    return [(view, view, f"{text} – {tip}") for view, text, tip in view_buttons()] + [
        ("fit", "fit", tr("Show the whole model (F, double-click)")),
        ("edges", "edges", tr("Show edges (E)")),
        ("projection", "projection", tr("Parallel projection instead of perspective (P)")),
    ]


class ViewToolbar(QFrame):
    """The view buttons as a compact row: Iso, Top, Front, Side | whole model, edges, projection.

    Made by PreviewView as ``view.toolbar`` without a parent; the preview pane puts it into its header
    (a layout's addWidget takes it over). It is enabled while the view shows a model and disabled
    otherwise, never hidden, so the user sees what the view can do. The view keeps the checkable
    buttons (edges, projection) in step with its options; the keys work when the view has the focus.
    """

    def __init__(self, view: PreviewView) -> None:
        super().__init__()
        self.setObjectName("viewButtons")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(1)
        self.buttons: dict[str, QPushButton] = {}
        slots = {
            "fit": lambda _=False: view.fit_view(),
            "edges": lambda checked: view.set_edges(bool(checked)),
            "projection": lambda checked: view.set_projection(ORTHOGRAPHIC if checked else PERSPECTIVE),
        }
        for name, kind, tooltip in toolbar_actions():
            if name == "fit":
                line = QFrame(self)
                line.setObjectName("viewSeparator")
                line.setFixedSize(1, 16)
                row.addWidget(line)
            button = QPushButton(self)
            button.setObjectName(f"view_{name}")
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip.split(" – ")[0])
            button.setIconSize(TOOLBAR_ICON)
            button.setFixedSize(26, 24)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if name in ("edges", "projection"):
                button.setCheckable(True)
                button.setChecked(name == "edges")
                button.toggled.connect(slots[name])
            else:
                button.clicked.connect(slots.get(name) or (lambda _=False, v=name: view.set_view(v)))
            row.addWidget(button)
            self.buttons[name] = button
        self.setEnabled(False)
        self.adjustSize()

    def restyle(self, palette: QPalette, theme: Theme) -> None:
        """Colours after the window's palette: a flat row with a faint frame, icons in the text colour."""
        text = palette.color(QPalette.ColorRole.WindowText)
        base = palette.color(QPalette.ColorRole.Button)
        border = QColor(text)
        border.setAlpha(45)
        highlight = palette.color(QPalette.ColorRole.Highlight)
        self.setStyleSheet(
            f"#viewButtons {{ background: {base.name()};"
            f" border: 1px solid rgba({border.red()}, {border.green()}, {border.blue()}, {border.alpha()});"
            " border-radius: 6px; }"
            "#viewButtons QPushButton { border: none; padding: 0; margin: 0; background: transparent; border-radius: 4px; }"
            f"#viewButtons QPushButton:hover {{ background: rgba({text.red()}, {text.green()}, {text.blue()}, 30); }}"
            f"#viewButtons QPushButton:checked {{ background: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 70);"
            f" border: 1px solid rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 160); }}"
            f"#viewSeparator {{ background: rgba({text.red()}, {text.green()}, {text.blue()}, 60); margin: 0 3px; }}"
        )
        for name, kind, _ in toolbar_actions():
            self.buttons[name].setIcon(_icon(kind, text))


# --------------------------------------------------------------------------- the widget


class PreviewView(QWidget):
    """Interactive 3D view of a PreviewMesh, with OpenGL or (fallback) QPainter.

    ``set_mesh`` shows a model (and ends a message), ``set_message`` shows a text instead of the model
    ("" shows the model again). ``element_clicked`` carries the label of the clicked element, "" for
    the background (the click also selects it, see ``select_element``). ``option_changed`` reports
    "edges" (bool) and "projection" (PERSPECTIVE or ORTHOGRAPHIC) when they change, for the settings.
    """

    element_clicked = Signal(str)
    renderer_changed = Signal(str)  # OPENGL or SOFTWARE, after a fallback
    option_changed = Signal(str, object)
    _edges_ready = Signal(object)  # the scene whose edges a thread finished

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.camera = Camera()
        self.theme = theme_for(self.palette())
        self._scene: _Scene | None = None
        self._renderer: QWidget | None = None
        self._renderer_name = ""
        self._fitted = True  # the view still shows the fitted model: fit again when resized
        self._drag: dict | None = None
        self._wheel_point: tuple[QPointF, numpy.ndarray] | None = None
        self._edges = True
        self._selected = -1
        self._animation: QVariantAnimation | None = None
        self.setMinimumSize(120, 90)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._message = QLabel()
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._stack.addWidget(self._message)

        # The buttons live outside the view (the pane's header); the view keeps them in step.
        self.toolbar = ViewToolbar(self)
        self._tool_buttons = self.toolbar.buttons
        self._restyle()

        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(lambda: self._renderer is not None and self._renderer.set_moving(False))
        self._edges_ready.connect(self._edges_computed)
        self._edge_worker: threading.Thread | None = None  # at most one edge computation at a time
        self._edge_timer = QTimer(self)  # a growing model: edges once no newer mesh came for a while
        self._edge_timer.setSingleShot(True)
        self._edge_timer.timeout.connect(lambda: self._prepare_edges(background=True))
        self._animation_end: tuple | None = None

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

    @property
    def edges_visible(self) -> bool:
        return self._edges

    @property
    def projection(self) -> str:
        return self.camera.projection

    @property
    def selected_element(self) -> int:
        """Index of the selected element in the mesh's elements, -1 for none."""
        return self._selected

    @property
    def selected_label(self) -> str:
        if self._scene is None or self._selected < 0 or self._selected >= len(self._scene.mesh.elements):
            return ""
        return self._scene.mesh.elements[self._selected]

    @property
    def animating(self) -> bool:
        return self._animation is not None and self._animation.state() == QVariantAnimation.State.Running

    def set_mesh(self, mesh: PreviewMesh | None) -> None:
        """Show ``mesh`` from the start view (None: an empty view)."""
        self._stop_animation()
        self._selected = -1
        self._scene = _Scene(mesh) if mesh is not None else None
        if mesh is not None:
            self.camera.set_model(*mesh.bounds(), _fit_points(mesh))
        else:
            self.camera.set_model(numpy.zeros(3), numpy.zeros(3))
        self._edge_timer.stop()
        self._renderer.set_scene(self._scene)
        self._message.setText("")
        self._stack.setCurrentWidget(self._renderer)
        self.reset_view(animate=False)
        self._update_toolbar()
        if self._edges:
            self._prepare_edges()

    def update_mesh(self, mesh: PreviewMesh | None) -> None:
        """Replace the shown model by ``mesh`` (a preview still growing, every few seconds) without
        resetting the view: the camera keeps its pose; while the view is still fitted (not orbited,
        zoomed or panned since the last fit) and the model grew beyond its old bounds, it is fitted
        again without animation. The selection stays if the selected element's label still exists.
        The feature edges are computed in a thread once no newer mesh came for EDGE_SETTLE_MS and never
        twice at once, so this stays cheap for millions of triangles (the upload is all it costs).
        Without a model shown yet (or with None) it is set_mesh."""
        old = self._scene
        if old is None or mesh is None:
            self.set_mesh(mesh)
            return
        label = self.selected_label
        if self.animating:  # the view ends up where the animation was heading
            end = self._animation_end
            self._stop_animation()
            if end is not None:
                self.camera.set_pose(end)
                self._fitted = True
        scene = _Scene(mesh)
        self._scene = scene
        self._selected = scene.element_named(label)
        self.camera.set_model(*mesh.bounds(), _fit_points(mesh))
        self._edge_timer.stop()
        self._renderer.set_scene(scene)
        self._message.setText("")
        self._stack.setCurrentWidget(self._renderer)
        grew = bool((scene.low < old.low - 1e-3).any() or (scene.high > old.high + 1e-3).any())
        if self._fitted and grew:
            self._sync_viewport()
            self.camera.fit()
        self._wheel_point = None
        self._redraw()
        self._update_toolbar()
        if self._edges:
            self._prepare_edges(delay=True)

    def set_message(self, text: str) -> None:
        """Show ``text`` instead of the model (e.g. "Vorschau wird berechnet … 34 %"); "" shows the model."""
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message if text else self._renderer)
        self._update_toolbar()

    def message(self) -> str:
        return self._message.text()

    def reset_view(self, animate: bool = True) -> None:
        """The start view: isometric from south-west above, the whole model."""
        self.set_view("iso", animate)

    def set_view(self, name: str, animate: bool = True) -> None:
        """One of VIEWS ("iso", "top", "front", "side"), showing the whole model."""
        goal = self._goal()
        goal.set_view(*VIEWS[name])
        self._go_to(goal, animate)

    def fit_view(self, animate: bool = True) -> None:
        """The whole model, from the current direction."""
        goal = self._goal()
        goal.fit()
        self._go_to(goal, animate)

    def set_edges(self, visible: bool) -> None:
        """Show or hide the feature edges (computed on first use, for a large mesh in a thread)."""
        visible = bool(visible)
        changed = visible != self._edges
        self._edges = visible
        button = self._tool_buttons["edges"]
        if button.isChecked() != visible:
            button.setChecked(visible)
        if visible:
            self._prepare_edges()
        self._redraw()
        if changed:
            self.option_changed.emit("edges", visible)

    def set_projection(self, projection: str) -> None:
        """PERSPECTIVE or ORTHOGRAPHIC (parallel) projection; the model keeps its size on screen."""
        orthographic = projection == ORTHOGRAPHIC
        changed = orthographic != self.camera.orthographic
        self.camera.orthographic = orthographic
        button = self._tool_buttons["projection"]
        if button.isChecked() != orthographic:
            button.setChecked(orthographic)
        if changed:
            self._stop_animation()
            if self._fitted:
                self.camera.fit()
            self._view_changed(fitted=self._fitted)
            self.option_changed.emit("projection", self.camera.projection)

    def select_element(self, label: str) -> None:
        """Highlight the element with this label ("" clears) and show its label chip."""
        self._selected = self._scene.element_named(label) if self._scene is not None else -1
        self._redraw()

    def clear_selection(self) -> None:
        if self._selected >= 0:
            self._selected = -1
            self._redraw()
            self.element_clicked.emit("")

    def element_at(self, x: float, y: float) -> str:
        """Label of the element at pixel (x, y) of the view, "" for the background."""
        triangle, _ = self._pick(QPointF(x, y))
        return "" if self._scene is None else self._scene.label(triangle)

    def image(self) -> QImage:
        """The model as currently drawn, with the triad and the label chip (not the message), e.g. for
        tests or a thumbnail."""
        self._sync_viewport()
        return self._renderer.image()

    def paint_decorations(self, painter: QPainter, width: float, height: float) -> None:
        """The axis triad (lower left) and the chip with the selected element's label (bottom centre)
        over a drawn model of ``width`` x ``height`` logical pixels; both renderers call this last."""
        if self._scene is None:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        draw_triad(painter, self.camera, self.theme, QPointF(12 + TRIAD_SIZE, height - 12 - TRIAD_SIZE))
        draw_chip(painter, self.theme, self.selected_label, width, height)

    def wait_for_edges(self, timeout: float = 30.0) -> bool:
        """Block until the current scene's edges are computed (for tests); False on timeout."""
        deadline = time.monotonic() + timeout
        while self._scene is not None and self._scene.edges is None and not self._scene.edge_error \
                and time.monotonic() < deadline:
            time.sleep(0.01)
        return self._scene is None or self._scene.edges is not None

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

    # -- theme and toolbar

    def _restyle(self) -> None:
        """Colours of the toolbar, icons and message after the palette (light or dark)."""
        self.theme = theme_for(self.palette())
        self.toolbar.restyle(self.palette(), self.theme)
        self._message.setStyleSheet(
            f"background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 {self.theme.top.name()},"
            f" stop: 1 {self.theme.bottom.name()}); color: {self.theme.text.name()}; padding: 12px;")

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange, QEvent.Type.StyleChange):
            self._restyle()
            self._redraw()

    # -- edges

    def _prepare_edges(self, delay: bool = False, background: bool = False) -> None:
        """Compute the current scene's edges: at once for a small mesh, else in a thread (``background``:
        in a thread whatever the size; ``delay``: only once no newer mesh came for EDGE_SETTLE_MS).
        Never more than one thread at a time: a scene replaced while its edges are computed is
        finished and dropped, then the current one gets its turn (see _edges_computed)."""
        scene = self._scene
        if scene is None or not self._edges or scene.edges is not None or scene.edge_error \
                or scene.edge_thread is not None:
            return
        if delay:
            self._edge_timer.start(EDGE_SETTLE_MS)
            return
        if scene.triangle_count <= EDGES_IN_BACKGROUND and not background:
            scene.compute_edges()
            self._redraw()
            return
        if self._edge_worker is not None and self._edge_worker.is_alive():
            return  # an older scene's edges are still being computed: _edges_computed comes back here

        def work() -> None:
            scene.compute_edges()
            self._edges_ready.emit(scene)

        scene.edge_thread = threading.Thread(target=work, name="preview-edges", daemon=True)
        self._edge_worker = scene.edge_thread
        scene.edge_thread.start()

    def _edges_computed(self, scene) -> None:
        if self._edge_worker is scene.edge_thread:
            self._edge_worker = None  # its work is done (the thread itself may still be about to exit)
        if self._renderer is None:
            return
        if scene is self._scene:
            self._redraw()
        elif not self._edge_timer.isActive():
            self._prepare_edges(background=True)  # the current scene waited for this thread

    # -- animation

    def _goal(self) -> Camera:
        """A copy of the camera to compute the view to move to."""
        self._sync_viewport()
        return copy.copy(self.camera)

    def _go_to(self, goal: Camera, animate: bool) -> None:
        self._stop_animation()
        if not animate or ANIMATION_MS <= 0 or not self.isVisible():
            self.camera.set_pose(goal.pose())
            self._view_changed(fitted=True)
            return
        start, end = self.camera.pose(), goal.pose()
        self._animation_end = end
        animation = QVariantAnimation(self)
        animation.setDuration(ANIMATION_MS)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        self._animation = animation
        self._renderer.set_moving(True)

        def step(value) -> None:
            self.camera.set_pose(interpolate_pose(start, end, float(value)))
            self._view_changed(fitted=False)

        def done() -> None:
            if self._animation is animation:
                self._animation = None
                self._animation_end = None
                self.camera.set_pose(end)
                self._renderer.set_moving(False)
                self._view_changed(fitted=True)

        animation.valueChanged.connect(step)
        animation.finished.connect(done)
        animation.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _stop_animation(self) -> None:
        animation, self._animation = self._animation, None
        self._animation_end = None
        if animation is not None:
            animation.stop()
            if self._renderer is not None:
                self._renderer.set_moving(False)

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
        self._stop_animation()
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
            self._selected = self._scene.element_of(drag["triangle"])
            self._redraw()
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
        self._stop_animation()
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
        elif key == Qt.Key.Key_E:
            self.set_edges(not self._edges)
        elif key == Qt.Key.Key_P:
            self.set_projection(PERSPECTIVE if self.camera.orthographic else ORTHOGRAPHIC)
        elif key == Qt.Key.Key_Escape and self._selected >= 0:
            self.clear_selection()
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
        self._redraw()

    def _redraw(self) -> None:
        if self._renderer is not None:
            self._renderer.update()

    def _sync_viewport(self) -> None:
        widget = self._renderer if self._renderer is not None and self._renderer.width() > 1 else self
        self.camera.set_viewport(widget.width(), widget.height())

    def _update_toolbar(self) -> None:
        """The buttons work while a model is shown (the keys too); otherwise they are greyed out."""
        self.toolbar.setEnabled(self._scene is not None and not self._message.text())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.camera.set_viewport(self.width(), self.height())
        if self._fitted and not self.animating:
            self.camera.fit()
        self._wheel_point = None
