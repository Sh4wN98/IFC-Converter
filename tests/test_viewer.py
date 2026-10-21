"""The 3D preview widget: camera, both renderers (OpenGL and QPainter), picking and the fallback.

The OpenGL checks run where an OpenGL 3.3 context can be created offscreen (on Linux with Mesa); the
software renderer is tested everywhere, also on the Windows CI runner without a GPU.
"""

import logging
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QIcon, QImage, QMouseEvent, QPalette, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from ifc_converter import viewer  # noqa: E402
from ifc_converter.preview import PreviewMesh  # noqa: E402

RED = (200, 60, 50, 255)
GLASS = (60, 90, 200, 120)
WALL = "IfcWall 2O2Fr$t4X7Zf8NOew3FLOH „Wand“"
WINDOW = "IfcWindow 0LV8Pis1v4AuJh$S0gsL5x „Fenster“"


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def palette(dark: bool = False) -> QPalette:
    """A light (or dark) window palette: the view takes its theme from it, whatever the desktop uses."""
    colours = {"Window": "#2b2f33", "WindowText": "#e6e8ea", "Base": "#1f2326", "Text": "#e6e8ea",
               "Button": "#3a3f44", "ButtonText": "#e6e8ea", "Highlight": "#4a90d9"} if dark else \
        {"Window": "#efefef", "WindowText": "#1f2428", "Base": "#ffffff", "Text": "#1f2428",
         "Button": "#e9e9e9", "ButtonText": "#1f2428", "Highlight": "#3b7dd8"}
    result = QPalette()
    for role, colour in colours.items():
        result.setColor(getattr(QPalette.ColorRole, role), QColor(colour))
    return result


def new_view(dark: bool = False) -> "viewer.PreviewView":
    view = viewer.PreviewView()
    view.setPalette(palette(dark))
    return view


def box(low, high):
    """Corners (8, 3) and triangles (12, 3) of a box, counter-clockwise seen from outside."""
    low, high = numpy.asarray(low, float), numpy.asarray(high, float)
    corners = low + numpy.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)]) * (high - low)
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    triangles = [t for a, b, c, d in faces for t in ((a, b, c), (a, c, d))]
    return corners, numpy.array(triangles)


def boxes_mesh(boxes, origin=(0, 0, 0)) -> PreviewMesh:
    """A mesh of boxes [(low, high, rgba, label)], one element each."""
    positions, colors, indices, elements = [], [], [], []
    for number, (low, high, rgba, _label) in enumerate(boxes):
        corners, triangles = box(low, high)
        indices.append(triangles + 8 * number)
        positions.append(corners)
        colors.append(numpy.tile(rgba, (8, 1)))
        elements.append(numpy.full(len(triangles), number))
    return PreviewMesh(
        positions=numpy.vstack(positions).astype(numpy.float32),
        colors=numpy.vstack(colors).astype(numpy.uint8),
        indices=numpy.vstack(indices).reshape(-1).astype(numpy.uint32),
        triangle_elements=numpy.concatenate(elements).astype(numpy.uint32),
        elements=[label for *_, label in boxes],
        origin=numpy.asarray(origin, float),
    )


def two_boxes() -> PreviewMesh:
    """An opaque red box (a wall) and a transparent blue one (a window) east of it."""
    return boxes_mesh([((0, 0, 0), (4, 3, 3), RED, WALL), ((6, 0, 0), (9, 3, 2), GLASS, WINDOW)])


def many_boxes(count: int) -> PreviewMesh:
    """``count`` boxes on a grid (12 triangles each), every 50th one transparent, 10 elements."""
    side = int(numpy.ceil(numpy.sqrt(count)))
    number = numpy.arange(count)
    low = numpy.column_stack([number % side * 2.0, number // side * 2.0, numpy.zeros(count)])
    corners, triangles = box((0, 0, 0), (1, 1, 1))
    positions = (low[:, None, :] + corners[None]).reshape(-1, 3).astype(numpy.float32)
    colors = numpy.tile(numpy.array([180, 180, 170, 255], numpy.uint8), (len(positions), 1))
    colors.reshape(count, 8, 4)[::50, :, 3] = 100
    indices = (triangles[None] + 8 * number[:, None, None]).reshape(-1).astype(numpy.uint32)
    return PreviewMesh(positions=positions, colors=colors, indices=indices,
                       triangle_elements=numpy.repeat(number % 10, 12).astype(numpy.uint32),
                       elements=[f"IfcBuildingElementProxy {n}" for n in range(10)])


@pytest.fixture
def renderer_env(monkeypatch):
    """Sets the renderer for views made in the test; the OpenGL check is redone around it."""
    viewer.opengl_problem.cache_clear()
    monkeypatch.setattr(viewer, "ANIMATION_MS", 0)  # views jump: the end state is what the tests check

    def choose(name: str) -> None:
        if name == viewer.SOFTWARE:
            monkeypatch.setenv(viewer.RENDERER_ENV, "software")
        else:
            monkeypatch.delenv(viewer.RENDERER_ENV, raising=False)
            if viewer.opengl_problem():
                pytest.skip(f"no OpenGL 3.3 here: {viewer.opengl_problem()}")
        viewer.opengl_problem.cache_clear()

    yield choose
    viewer.opengl_problem.cache_clear()


@pytest.fixture(params=[viewer.OPENGL, viewer.SOFTWARE])
def make_view(request, app, renderer_env):
    """Makes shown PreviewViews of a size with the renderer of the parameter (OpenGL is skipped if unavailable)."""
    renderer_env(request.param)
    views = []

    def make(width=400, height=300, mesh=None, dark=False):
        view = new_view(dark)
        view.resize(width, height)
        view.show()
        app.processEvents()
        assert view.renderer_name == request.param
        if mesh is not None:
            view.set_mesh(mesh)
        views.append(view)
        return view

    yield make
    for view in views:
        view.close()
        view.deleteLater()
    app.processEvents()


def rgb(image, x, y) -> tuple[int, int, int]:
    colour = QColor(image.pixel(int(round(x)), int(round(y))))
    return colour.red(), colour.green(), colour.blue()


def pixel_of(view, point) -> tuple[float, float]:
    (x, y), = view.camera.project([point])[0]
    return x, y


def near(colour, expected, tolerance=6) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(colour, expected))


def background(view, image, x, y) -> tuple[int, int, int]:
    """The background gradient's colour at device pixel (x, y) of ``image``."""
    return viewer.gradient_color(view.theme, y / max(image.height() - 1, 1))


def is_background(view, image, x, y, tolerance=6) -> bool:
    return near(rgb(image, x, y), background(view, image, x, y), tolerance)


def pixels_of(image) -> numpy.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    pixels = numpy.frombuffer(image.constBits(), numpy.uint8, image.sizeInBytes())
    # A copy: the converted image is freed on return, and a view of its bits would then read freed memory.
    return pixels.reshape(image.height(), image.bytesPerLine())[:, :3 * image.width()].reshape(image.height(), -1, 3).copy()


def covered(view, image) -> float:
    """Share of the pixels of ``image`` that are not background."""
    pixels = pixels_of(image).astype(int)
    rows = numpy.array([background(view, image, 0, y) for y in range(image.height())])
    return float(numpy.mean(numpy.abs(pixels - rows[:, None, :]).max(axis=2) > 3))


def send_mouse(widget, kind, position, button=Qt.MouseButton.LeftButton, buttons=None,
               modifiers=Qt.KeyboardModifier.NoModifier):
    position = QPointF(*position)
    if buttons is None:
        buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else button
    event = QMouseEvent(kind, position, widget.mapToGlobal(position), button, buttons, modifiers)
    QApplication.sendEvent(widget, event)


def drag(widget, start, end, button=Qt.MouseButton.LeftButton, modifiers=Qt.KeyboardModifier.NoModifier, steps=5):
    send_mouse(widget, QEvent.Type.MouseButtonPress, start, button, modifiers=modifiers)
    for step in range(1, steps + 1):
        position = [s + (e - s) * step / steps for s, e in zip(start, end)]
        send_mouse(widget, QEvent.Type.MouseMove, position, Qt.MouseButton.NoButton, button, modifiers)
    send_mouse(widget, QEvent.Type.MouseButtonRelease, end, button, modifiers=modifiers)


def wheel(widget, position, notches=1):
    position = QPointF(*position)
    event = QWheelEvent(position, widget.mapToGlobal(position), QPoint(0, 0), QPoint(0, 120 * notches),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


# --------------------------------------------------------------------------- camera


def model_camera(width=300, height=250, low=(0, 0, 0), high=(40, 12, 9)) -> viewer.Camera:
    camera = viewer.Camera()
    camera.set_viewport(width, height)
    camera.set_model(low, high)
    camera.set_view(*viewer.VIEWS["iso"])
    return camera


def corners_of(low, high):
    return numpy.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])


@pytest.mark.parametrize("view", list(viewer.VIEWS))
@pytest.mark.parametrize("size", [(300, 250), (1200, 400), (250, 600)])
@pytest.mark.parametrize("model", [((0, 0, 0), (1, 1, 1)), ((0, 0, 0), (60, 12, 9)),
                                   ((-1000, -800, 0), (1000, 900, 40))])
def test_fit_shows_the_whole_model_and_fills_the_view(view, size, model):
    camera = model_camera(*size, *model)
    camera.set_view(*viewer.VIEWS[view])
    pixels, depth = camera.project(corners_of(*model))
    near_plane, far_plane = camera.clip_planes()
    assert (depth > near_plane).all() and (depth < far_plane).all()
    assert (pixels >= -0.5).all() and (pixels[:, 0] <= size[0] + 0.5).all() and (pixels[:, 1] <= size[1] + 0.5).all()
    extent = (pixels.max(axis=0) - pixels.min(axis=0)) / size
    assert extent.max() > 0.85 * viewer.FIT_MARGIN  # tight in at least one direction
    centre = (pixels.max(axis=0) + pixels.min(axis=0)) / 2 / size
    assert numpy.allclose(centre, 0.5, atol=0.02)


def test_fit_to_points_is_tighter_than_to_the_box():
    # A long diagonal bar seen from the south: the near corners of its box reach further out on screen.
    points = numpy.array([[0, 0, 0], [100, 100, 0], [0, 0, 1], [100, 100, 1]], float)
    camera = model_camera(400, 300, (0, 0, 0), (100, 100, 1))
    camera.set_view(*viewer.VIEWS["front"])
    box_distance = camera.distance
    camera.set_model((0, 0, 0), (100, 100, 1), points)
    camera.fit()
    assert camera.distance < box_distance * 0.95
    pixels, _ = camera.project(points)
    assert (pixels >= -0.5).all() and (pixels[:, 0] <= 400.5).all() and (pixels[:, 1] <= 300.5).all()


def test_start_view_is_isometric_from_south_west_above():
    camera = model_camera()
    eye = camera.eye()
    assert eye[0] < camera.center[0] and eye[1] < camera.center[1] and eye[2] > camera.center[2]
    right, up, forward = camera.basis()
    assert numpy.allclose(forward, numpy.array([1, 1, -1]) / numpy.sqrt(3))
    assert right[2] == 0 and up[2] > 0


def test_views_look_from_the_named_side():
    camera = model_camera()
    camera.set_view(*viewer.VIEWS["top"])
    right, up, forward = camera.basis()
    assert numpy.allclose(forward, [0, 0, -1]) and numpy.allclose(up, [0, 1, 0])  # north up
    camera.set_view(*viewer.VIEWS["front"])
    assert numpy.allclose(camera.basis()[2], [0, 1, 0])  # from the south, looking north
    camera.set_view(*viewer.VIEWS["side"])
    assert numpy.allclose(camera.basis()[2], [-1, 0, 0])  # from the east


def test_orbit_keeps_z_up_and_the_pivot_in_place():
    camera = model_camera()
    pivot = numpy.array([35.0, 2.0, 9.0])
    before, _ = camera.project([pivot])
    rng = numpy.random.default_rng(1)
    for dx, dy in rng.uniform(-400, 400, (40, 2)):
        camera.orbit(dx, dy, pivot)
        right, up, forward = camera.basis()
        assert right[2] == 0  # no roll: vertical lines stay vertical
        assert up[2] >= -1e-12  # never upside down
        assert -90 <= camera.pitch <= 90
        after, _ = camera.project([pivot])
        assert numpy.allclose(after, before, atol=1e-6)
        assert numpy.isclose(numpy.linalg.norm(camera.basis(), axis=1), 1).all()


def test_orbit_follows_the_mouse():
    camera = model_camera()
    yaw, pitch = camera.yaw, camera.pitch
    camera.orbit(50, 0)
    assert camera.yaw == pytest.approx((yaw - 50 * viewer.ORBIT_DEGREES_PER_PIXEL) % 360)
    camera.orbit(0, 30)  # dragging down looks more from above
    assert camera.pitch < pitch


def test_zoom_keeps_the_point_under_the_cursor():
    camera = model_camera()
    point = numpy.array([5.0, 1.0, 8.0])
    before, _ = camera.project([point])
    distance = camera.distance
    camera.zoom(0.5, point)
    after, _ = camera.project([point])
    assert camera.distance == pytest.approx(distance / 2)
    assert numpy.allclose(after, before, atol=1e-6)
    for _ in range(200):  # limits: never through the model's scale into nothing, never lost
        camera.zoom(0.5, point)
    assert camera.distance > 0
    for _ in range(400):
        camera.zoom(2)
    assert camera.distance <= camera.radius * 100 + 1e-9


def test_pan_moves_the_point_with_the_mouse():
    camera = model_camera()
    point = camera.point_at(120, 80)
    before, _ = camera.project([point])
    camera.pan(30, -20, camera.depth(point))
    after, _ = camera.project([point])
    assert numpy.allclose(after - before, [[30, -20]], atol=1e-6)


@pytest.mark.parametrize("size", [1.0, 2000.0])
def test_clip_planes_hold_models_from_1_m_to_2_km(size):
    camera = model_camera(low=(0, 0, 0), high=(size, size, size / 10))
    near_plane, far_plane = camera.clip_planes()
    assert 0 < near_plane < far_plane
    assert far_plane / near_plane < 1e5  # enough depth precision
    camera.zoom(1e-3, camera.center)  # close up inside the model
    near_plane, far_plane = camera.clip_planes()
    assert near_plane <= camera.distance * 0.06
    assert far_plane / near_plane <= 1e6 + 1


def test_ray_and_projection_agree():
    camera = model_camera()
    eye, direction = camera.ray(70, 200)
    pixels, depth = camera.project([eye + direction * 17])
    assert numpy.allclose(pixels, [[70, 200]], atol=1e-6)


def test_intersect_finds_the_nearest_triangle():
    a = numpy.array([[0, 0, 0], [0, 0, 5]], float)
    b = numpy.array([[1, 0, 0], [1, 0, 5]], float)
    c = numpy.array([[0, 1, 0], [0, 1, 5]], float)
    distances = viewer.intersect([0.2, 0.2, 10], [0, 0, -1], a, b, c)
    assert distances.tolist() == [10, 5]
    assert numpy.isinf(viewer.intersect([2, 2, 10], [0, 0, -1], a, b, c)).all()


def test_split_large_keeps_the_surface_and_winding():
    corners, triangles = box((0, 0, 0), (10, 4, 3))
    points = corners[triangles].astype(numpy.float32)
    flat = viewer._Flat(points.copy(), numpy.ones((12, 4), numpy.float32), numpy.arange(12))
    split = viewer._split_large(flat, 10_000, 1.0)

    def normals(p):
        return numpy.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])

    assert len(split) > 100
    assert numpy.linalg.norm(split.corners[:, [1, 2, 0]] - split.corners, axis=2).max() <= 1.0 + 1e-6
    area = numpy.linalg.norm(normals(split.corners), axis=1).sum()
    assert area == pytest.approx(numpy.linalg.norm(normals(points), axis=1).sum(), rel=1e-5)
    # Every piece faces the way its original triangle did.
    original = normals(points)[split.source]
    assert (numpy.einsum("ij,ij->i", normals(split.corners), original) > 0).all()
    assert len(viewer._split_large(viewer._Flat(points.copy(), flat.colors, flat.source), 50, 1.0)) == 50


def test_software_selection_takes_the_largest_elements_first():
    mesh = boxes_mesh([((0, 0, 0), (1, 1, 1), RED, "klein"), ((0, 0, 5), (20, 20, 6), RED, "groß"),
                       ((5, 0, 0), (6, 2, 1), RED, "mittel")])
    scene = viewer._Scene(mesh)
    assert sorted(scene._ranked()[:12].tolist()) == list(range(12, 24))
    flat = scene.software(12)
    assert set(mesh.triangle_elements[flat.source].tolist()) == {1}


# --------------------------------------------------------------------------- rendering


def test_renderer_draws_the_model_and_the_background(make_view):
    view = make_view(mesh=two_boxes())
    image = view.image()
    assert image.width() >= 400 and image.height() >= 300
    assert view.renderer_detail  # the graphics card, or why not OpenGL
    ratio = image.width() / 400
    top_of_wall = pixel_of(view, (2, 1.5, 3))
    red = rgb(image, top_of_wall[0] * ratio, top_of_wall[1] * ratio)
    assert red[0] > 120 and red[1] < 100 and red[2] < 100, red
    glass = pixel_of(view, (7.5, 1.5, 2))
    blue = rgb(image, glass[0] * ratio, glass[1] * ratio)
    assert blue[2] > blue[0] + 40 and blue[2] > 120, blue  # blended with what is behind it
    assert blue[0] > 60  # but not opaque: the light background shows through
    for corner in [(2, 2), (image.width() - 3, 2), (2, image.height() - 3), (image.width() - 3, image.height() - 3)]:
        assert is_background(view, image, *corner), (corner, rgb(image, *corner), background(view, image, *corner))
    # A gradient: lighter at the bottom than at the top (the light theme).
    assert view.theme is viewer.LIGHT_THEME
    assert sum(rgb(image, 2, image.height() - 3)) > sum(rgb(image, 2, 2)) + 60


def test_renderer_shades_faces_differently(make_view):
    view = make_view(mesh=two_boxes())
    image = view.image()
    ratio = image.width() / 400
    top, west, south = ((pixel_of(view, point)) for point in [(2, 1.5, 3), (0, 1.5, 1.5), (2, 0, 1.5)])
    colours = [rgb(image, x * ratio, y * ratio) for x, y in (top, west, south)]
    assert len({colour[0] // 8 for colour in colours}) == 3, colours  # three faces, three brightnesses
    assert colours[0][0] > colours[2][0]  # lit from above


def test_both_renderers_look_alike(app, renderer_env):
    images = {}
    for name in (viewer.OPENGL, viewer.SOFTWARE):
        renderer_env(name)
        view = new_view()
        view.resize(320, 240)
        view.show()
        app.processEvents()
        view.set_mesh(two_boxes())
        view.set_edges(False)  # the lines land on slightly different pixels
        images[name] = view.image().scaled(320, 240)
        view.close()
    differences = []
    for x in range(0, 320, 8):
        for y in range(0, 240, 8):
            a, b = rgb(images[viewer.OPENGL], x, y), rgb(images[viewer.SOFTWARE], x, y)
            differences.append(max(abs(p - q) for p, q in zip(a, b)))
    assert numpy.median(differences) <= 2
    assert numpy.mean(numpy.array(differences) > 40) < 0.03  # only along edges


def test_toolbar_is_a_separate_widget_enabled_while_a_model_is_shown(make_view):
    # Not over the GL view (a translucent widget over a QOpenGLWidget vanished on a Windows/NVIDIA PC), not
    # hover-only (the user never found it): the pane puts it into its header; the view greys it out.
    view = make_view(400, 250)
    toolbar = view.toolbar
    assert isinstance(toolbar, viewer.ViewToolbar) and toolbar.parentWidget() is None
    assert not toolbar.isEnabled() and not toolbar.isVisible()
    view.set_mesh(two_boxes())
    assert toolbar.isEnabled()
    assert toolbar.width() <= 230 and toolbar.height() <= 32  # fits beside the pane's title at 1080p
    view.set_message("Vorschau wird berechnet …")
    assert not toolbar.isEnabled()
    view.set_message("")
    assert toolbar.isEnabled()
    view.set_mesh(None)
    assert not toolbar.isEnabled()
    assert not view.findChildren(QPushButton)  # nothing of the toolbar is inside the view


def test_view_works_small_and_large(make_view):
    small = make_view(400, 250, two_boxes())
    tiny = make_view(150, 120, two_boxes())  # the toolbar is not in the view: no width it needs
    large = make_view(1600, 1000, two_boxes())
    for view in (small, tiny, large):
        image = view.image()
        ratio = image.width() / view.width()
        x, y = pixel_of(view, (2, 1.5, 3))
        assert rgb(image, x * ratio, y * ratio)[0] > 120


def test_empty_and_no_mesh(make_view):
    view = make_view()
    image = view.image()
    assert is_background(view, image, 10, 10)
    empty = PreviewMesh(positions=numpy.zeros((0, 3), numpy.float32), colors=numpy.zeros((0, 4), numpy.uint8),
                        indices=numpy.zeros(0, numpy.uint32), triangle_elements=numpy.zeros(0, numpy.uint32),
                        elements=[])
    view.set_mesh(empty)
    image = view.image()
    assert is_background(view, image, image.width() // 2, image.height() // 2)
    assert view.element_at(200, 150) == ""
    view.set_mesh(two_boxes())
    view.set_mesh(None)
    image = view.image()
    assert is_background(view, image, image.width() // 2, image.height() // 2)
    assert view.element_at(200, 150) == ""
    drag(view._renderer, (100, 100), (200, 150))  # nothing to turn, nothing breaks
    wheel(view._renderer, (100, 100))


def test_georeferenced_mesh_is_drawn_relative_to_its_origin(make_view):
    mesh = two_boxes()
    mesh.origin = numpy.array([458_123.25, 5_438_456.5, 312.0])
    view = make_view(mesh=mesh)
    x, y = pixel_of(view, (2, 1.5, 3))
    image = view.image()
    ratio = image.width() / 400
    assert rgb(image, x * ratio, y * ratio)[0] > 120


def test_message_replaces_the_model(make_view):
    view = make_view(mesh=two_boxes())
    view.set_message("Vorschau wird berechnet … 34 %")
    assert view._stack.currentWidget() is view._message
    assert view.message() == "Vorschau wird berechnet … 34 %"
    assert not view.toolbar.isEnabled()
    view.set_message("")
    assert view._stack.currentWidget() is view._renderer
    view.set_message("Keine Vorschau")
    view.set_mesh(two_boxes())  # a model ends the message
    assert view._stack.currentWidget() is view._renderer and view.message() == ""


# --------------------------------------------------------------------------- picking and controls


def test_picking_returns_the_element(make_view):
    view = make_view(mesh=two_boxes())
    view.image()
    assert view.element_at(*pixel_of(view, (2, 1.5, 3))) == WALL
    assert view.element_at(*pixel_of(view, (0, 1.5, 1.5))) == WALL
    assert view.element_at(*pixel_of(view, (7.5, 1.5, 2))) == WINDOW  # glass can be picked too
    assert view.element_at(3, 3) == ""


def test_click_emits_the_element_and_drag_does_not(make_view):
    view = make_view(mesh=two_boxes())
    view.image()
    clicked = []
    view.element_clicked.connect(clicked.append)
    renderer = view._renderer
    x, y = pixel_of(view, (2, 1.5, 3))
    send_mouse(renderer, QEvent.Type.MouseButtonPress, (x, y))
    send_mouse(renderer, QEvent.Type.MouseButtonRelease, (x + 2, y))  # a little jitter is still a click
    send_mouse(renderer, QEvent.Type.MouseButtonPress, (3, 3))
    send_mouse(renderer, QEvent.Type.MouseButtonRelease, (3, 3))
    assert clicked == [WALL, ""]
    drag(renderer, (x, y), (x + 60, y))
    send_mouse(renderer, QEvent.Type.MouseButtonPress, (x, y), Qt.MouseButton.RightButton)
    send_mouse(renderer, QEvent.Type.MouseButtonRelease, (x, y), Qt.MouseButton.RightButton)
    assert clicked == [WALL, ""]


def test_left_drag_orbits_around_the_clicked_point(make_view):
    view = make_view(mesh=two_boxes())
    view.image()
    point = numpy.array([2, 1.5, 3.0])
    x, y = pixel_of(view, point)
    yaw = view.camera.yaw
    drag(view._renderer, (x, y), (x + 100, y + 40))
    assert view.camera.yaw != yaw
    assert view.camera.basis()[0][2] == 0
    assert numpy.allclose(pixel_of(view, point), (x, y), atol=0.5)  # the model turned about the grabbed point


@pytest.mark.parametrize("button,modifiers", [
    (Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier),
    (Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier),
    (Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier),
])
def test_pan_drags_the_model_along(make_view, button, modifiers):
    view = make_view(mesh=two_boxes())
    view.image()
    point = (2, 1.5, 3)
    x, y = pixel_of(view, point)
    yaw, pitch = view.camera.yaw, view.camera.pitch
    drag(view._renderer, (x, y), (x + 50, y - 30), button, modifiers)
    assert (view.camera.yaw, view.camera.pitch) == (yaw, pitch)
    assert numpy.allclose(pixel_of(view, point), (x + 50, y - 30), atol=0.5)


def test_wheel_zooms_towards_the_cursor_and_double_click_fits(make_view):
    view = make_view(mesh=two_boxes())
    view.image()
    fitted = view.camera.distance
    point = (7.5, 1.5, 2)
    x, y = pixel_of(view, point)
    wheel(view._renderer, (x, y), 2)
    assert view.camera.distance == pytest.approx(fitted * viewer.ZOOM_STEP ** 2)
    assert numpy.allclose(pixel_of(view, point), (x, y), atol=0.5)
    wheel(view._renderer, (x, y), -1)
    assert numpy.allclose(pixel_of(view, point), (x, y), atol=0.5)
    wheel(view._renderer, (5, 5), 1)  # on the background: towards the point at the target's depth
    assert view.camera.distance == pytest.approx(fitted * viewer.ZOOM_STEP ** 2)
    send_mouse(view._renderer, QEvent.Type.MouseButtonDblClick, (x, y))
    assert view.camera.distance == pytest.approx(fitted)


def test_keys_and_buttons_choose_views(make_view):
    view = make_view(mesh=two_boxes())
    view.setFocus()
    from PySide6.QtTest import QTest

    QTest.keyClick(view, Qt.Key.Key_2)
    assert view.camera.pitch == -90
    QTest.keyClick(view, Qt.Key.Key_4)
    assert view.camera.yaw == 180 and view.camera.pitch == 0
    QTest.keyClick(view, Qt.Key.Key_Home)
    assert (view.camera.yaw, view.camera.pitch) == viewer.VIEWS["iso"]
    buttons = view._tool_buttons
    assert set(buttons) == {"iso", "top", "front", "side", "fit", "edges", "projection"}
    assert buttons["front"].toolTip() == "Vorne – Ansicht von Süden (3)" and not buttons["front"].text()
    assert not buttons["front"].icon().isNull()
    buttons["front"].click()
    assert (view.camera.yaw, view.camera.pitch) == viewer.VIEWS["front"]
    fitted = view.camera.distance
    view.camera.zoom(0.3)
    buttons["fit"].click()
    assert view.camera.distance == pytest.approx(fitted)
    view.camera.zoom(0.3)
    QTest.keyClick(view, Qt.Key.Key_F)
    assert view.camera.distance == pytest.approx(fitted)


def test_resize_refits_until_the_user_moves_the_view(make_view, app):
    view = make_view(300, 250, two_boxes())
    view.resize(800, 300)
    app.processEvents()
    pixels, _ = view.camera.project(corners_of((0, 0, 0), (9, 3, 3)))
    assert pixels[:, 0].min() >= 0 and pixels[:, 0].max() <= 800 and pixels[:, 1].max() <= 300
    view.camera.zoom(0.5)
    view._view_changed()
    distance = view.camera.distance
    view.resize(500, 300)
    app.processEvents()
    assert view.camera.distance == distance


# --------------------------------------------------------------------------- fallback


def test_software_renderer_when_forced(app, renderer_env):
    renderer_env(viewer.SOFTWARE)
    view = new_view()
    assert view.renderer_name == viewer.SOFTWARE == "Software"
    assert viewer.opengl_problem() == f"{viewer.RENDERER_ENV}=software"
    assert view.renderer_detail == f"{viewer.RENDERER_ENV}=software"
    view.close()


def test_fallback_when_no_context_can_be_made(app, renderer_env, monkeypatch):
    renderer_env(viewer.SOFTWARE)
    monkeypatch.delenv(viewer.RENDERER_ENV)
    monkeypatch.setattr(viewer, "REQUIRED_VERSION", (9, 9))  # no driver offers this
    viewer.opengl_problem.cache_clear()
    assert viewer.opengl_problem()
    view = new_view()
    view.resize(300, 250)
    view.set_mesh(two_boxes())
    assert view.renderer_name == viewer.SOFTWARE
    x, y = pixel_of(view, (2, 1.5, 3))
    assert rgb(view.image(), x, y)[0] > 120
    view.close()


def test_fallback_when_the_opengl_widget_is_missing(app, renderer_env, monkeypatch):
    renderer_env(viewer.OPENGL)

    def broken():
        raise ImportError("DLL load failed while importing QtOpenGLWidgets")

    monkeypatch.setattr(viewer, "_gl_view_class", broken)
    view = new_view()
    assert view.renderer_name == viewer.SOFTWARE
    view.close()


def test_fallback_when_shaders_fail(app, renderer_env, monkeypatch, caplog):
    renderer_env(viewer.OPENGL)
    caplog.set_level(logging.INFO, logger="ifc_converter.viewer")
    monkeypatch.setattr(viewer, "FRAGMENT_SHADER", "#version 330 core\nthis is not GLSL")
    view = new_view()
    changes = []
    view.renderer_changed.connect(changes.append)
    view.resize(300, 250)
    view.show()
    view.set_mesh(two_boxes())
    assert view.renderer_name == viewer.OPENGL
    view.image()  # initializes OpenGL: the shader does not compile
    deadline = time.monotonic() + 10
    while view.renderer_name != viewer.SOFTWARE and time.monotonic() < deadline:
        app.processEvents()
    assert view.renderer_name == viewer.SOFTWARE
    assert changes == [viewer.SOFTWARE]
    assert "Shader" in caplog.text
    x, y = pixel_of(view, (2, 1.5, 3))
    image = view.image()
    assert rgb(image, x * image.width() / 300, y * image.width() / 300)[0] > 120
    assert view.element_at(x, y) == WALL
    view.close()


def test_fallback_when_drawing_fails(app, renderer_env):
    renderer_env(viewer.OPENGL)
    view = new_view()
    view.resize(300, 250)
    view.show()
    view.set_mesh(two_boxes())
    view.image()
    view._renderer._paint = lambda: (_ for _ in ()).throw(RuntimeError("OpenGL-Fehler 0x0505 beim Zeichnen"))
    view._renderer.update()
    view.image()
    deadline = time.monotonic() + 10
    while view.renderer_name != viewer.SOFTWARE and time.monotonic() < deadline:
        app.processEvents()
    assert view.renderer_name == viewer.SOFTWARE
    view.close()


def test_software_budget_follows_the_drawing_speed(app, renderer_env):
    renderer_env(viewer.SOFTWARE)
    view = new_view()
    renderer = view._renderer
    renderer._seconds_per_triangle = 1e-6
    assert renderer.budget(False) == viewer.SOFTWARE_TRIANGLES
    assert renderer.budget(True) == 50_000
    renderer._seconds_per_triangle = 1e-4
    assert renderer.budget(False) == 5_000
    assert renderer.budget(True) == viewer.SOFTWARE_BUDGETS[0]
    view.close()


# --------------------------------------------------------------------------- large models


@pytest.mark.parametrize("renderer", [viewer.OPENGL, viewer.SOFTWARE])
def test_large_mesh_uploads_and_draws_in_time(app, renderer_env, renderer):
    renderer_env(renderer)
    mesh = many_boxes(250_000)  # 3 million triangles, 2 million vertices
    assert mesh.triangle_count == 3_000_000
    view = new_view()
    view.resize(640, 480)
    view.show()
    app.processEvents()
    started = time.perf_counter()
    view.set_mesh(mesh)
    view.image()
    first = time.perf_counter() - started
    started = time.perf_counter()
    for step in range(3):
        view.camera.orbit(10, 0)
        view._renderer.update()
        image = view.image()
    redraw = (time.perf_counter() - started) / 3
    point = (500.5, 500.5, 1)  # the top of a box in the middle of the grid
    if renderer == viewer.SOFTWARE:  # which draws only some of the boxes
        point = view._scene.software(view._renderer.budget(False)).corners[0].mean(axis=0)
    x, y = pixel_of(view, point)
    started = time.perf_counter()
    label = view.element_at(x, y)
    pick = time.perf_counter() - started
    print(f"\n{renderer}: 3M triangles, first frame {first:.2f} s, redraw {redraw:.3f} s, pick {pick:.3f} s")
    assert label.startswith("IfcBuildingElementProxy")
    assert covered(view, image) > (0.1 if renderer == viewer.OPENGL else 0.0002)  # the software one draws few boxes
    assert first < 60 and redraw < 10 and pick < 5
    view.close()
    view.deleteLater()
    app.processEvents()


def test_wheel_picks_again_after_the_view_turned(make_view):
    view = make_view(mesh=two_boxes())
    view.image()
    x, y = pixel_of(view, (2, 1.5, 3))
    wheel(view._renderer, (x, y))
    assert view._wheel_point is not None
    drag(view._renderer, (x, y), (x + 80, y))
    assert view._wheel_point is None
    point = view._scene.hit_point(view._pick(QPointF(x, y))[0], view.camera, x, y)
    wheel(view._renderer, (x, y))
    assert numpy.allclose(pixel_of(view, point), (x, y), atol=0.5)


def test_fallback_when_the_view_gets_no_context(app, renderer_env, monkeypatch):
    renderer_env(viewer.OPENGL)
    monkeypatch.setattr(viewer._gl_view_class(), "initializeGL", lambda self: None)  # as if Qt never called it
    view = new_view()
    view.resize(300, 250)
    view.show()
    view.set_mesh(two_boxes())
    deadline = time.monotonic() + 10
    while view.renderer_name != viewer.SOFTWARE and time.monotonic() < deadline:
        view._renderer.repaint()
        app.processEvents()
    assert view.renderer_name == viewer.SOFTWARE
    view.close()


def test_software_renderer_draws_less_while_moving(app, renderer_env):
    renderer_env(viewer.SOFTWARE)
    from PySide6.QtTest import QTest

    view = new_view()
    view.resize(400, 300)
    view.show()
    app.processEvents()
    view.set_mesh(many_boxes(10_000))  # 120 000 triangles
    renderer = view._renderer
    renderer.budget = lambda moving: 5_000 if moving else 50_000  # not measured: fixed for the test
    view.image()
    still = renderer.drawn
    x, y = 200, 150
    send_mouse(renderer, QEvent.Type.MouseButtonPress, (x, y))
    send_mouse(renderer, QEvent.Type.MouseMove, (x + 40, y), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    view.image()
    moving = renderer.drawn
    send_mouse(renderer, QEvent.Type.MouseButtonRelease, (x + 40, y))
    view.image()
    coarse = 5_000 * (1 + viewer.SPLIT_GROWTH)
    assert moving <= coarse < still
    assert renderer.drawn > coarse
    wheel(renderer, (x, y))
    view.image()
    assert renderer.drawn <= coarse
    QTest.qWait(viewer.SETTLE_MS + 200)
    view.image()
    assert renderer.drawn > coarse  # full detail again after the wheel stopped
    view.close()


# --------------------------------------------------------------------------- looks: edges, shadow, theme, selection


def test_feature_edges_of_a_box_are_its_twelve_edges():
    mesh = two_boxes()
    segments, flags = viewer.feature_edges(mesh)
    assert flags.shape == (24, 3) and segments.dtype == numpy.uint32
    assert len(segments) == 24  # 12 edges per box; the diagonals of the faces are no creases
    assert int(flags.sum()) == 48  # every edge belongs to two triangles
    lengths = numpy.linalg.norm(mesh.positions[segments[:, 0]] - mesh.positions[segments[:, 1]], axis=1)
    assert sorted(numpy.round(lengths, 3).tolist()) == sorted([4, 3, 3] * 4 + [3, 3, 2] * 4)
    # A flat surface of two coplanar triangles: only its border.
    flat = PreviewMesh(positions=numpy.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], numpy.float32),
                       colors=numpy.full((4, 4), 255, numpy.uint8), indices=numpy.array([0, 1, 2, 0, 2, 3], numpy.uint32),
                       triangle_elements=numpy.zeros(2, numpy.uint32), elements=["IfcSlab 1"])
    segments, flags = viewer.feature_edges(flat)
    assert len(segments) == 4 and flags.tolist() == [[True, True, False], [False, True, True]]


def test_edges_draw_dark_lines_and_can_be_switched_off(make_view):
    view = make_view(mesh=two_boxes())
    assert view.edges_visible and view._tool_buttons["edges"].isChecked()
    with_edges = pixels_of(view.image()).astype(int)
    changes = []
    view.option_changed.connect(lambda key, value: changes.append((key, value)))
    view.set_edges(False)
    assert not view._tool_buttons["edges"].isChecked() and changes == [("edges", False)]
    without = pixels_of(view.image()).astype(int)
    different = numpy.abs(with_edges - without).max(axis=2) > 20
    assert 0.002 < different.mean() < 0.15  # thin lines along the boxes' edges, nothing else
    assert (with_edges[different].sum(axis=1) < without[different].sum(axis=1)).mean() > 0.8  # darker
    view.setFocus()
    from PySide6.QtTest import QTest

    QTest.keyClick(view, Qt.Key.Key_E)
    assert view.edges_visible and changes == [("edges", False), ("edges", True)]
    view._tool_buttons["edges"].click()
    assert not view.edges_visible


def test_edges_of_a_large_mesh_come_from_a_thread(make_view, monkeypatch, app):
    monkeypatch.setattr(viewer, "EDGES_IN_BACKGROUND", 10)
    view = make_view(mesh=many_boxes(100))
    scene = view._scene
    assert scene.edge_thread is not None
    assert view.wait_for_edges()
    assert len(scene.edges) == 1200
    deadline = time.monotonic() + 5  # the thread's signal reaches the view, which redraws
    while scene.edge_thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
    app.processEvents()
    image = view.image()
    view.set_edges(False)
    assert (numpy.abs(pixels_of(image).astype(int) - pixels_of(view.image()).astype(int)).max(axis=2) > 20).any()


def test_dark_palette_gives_the_dark_theme(make_view):
    view = make_view(mesh=two_boxes(), dark=True)
    assert view.theme is viewer.DARK_THEME
    image = view.image()
    assert is_background(view, image, 2, 2) and sum(rgb(image, 2, 2)) < 250
    assert sum(rgb(image, 2, image.height() - 3)) < sum(rgb(image, 2, 2))  # darker at the bottom
    x, y = pixel_of(view, (2, 1.5, 3))
    ratio = image.width() / 400
    assert rgb(image, x * ratio, y * ratio)[0] > 120  # the model is lit the same
    view.setPalette(palette(dark=False))
    QApplication.sendEvent(view, QEvent(QEvent.Type.PaletteChange))
    assert view.theme is viewer.LIGHT_THEME


def test_ground_shadow_lies_under_the_model(make_view):
    view = make_view(mesh=two_boxes())
    view.set_edges(False)
    image = view.image()
    ratio = image.width() / 400
    # Just outside the footprint on the ground, south-west of the wall: darker than the plain background.
    x, y = pixel_of(view, (-0.6, -0.6, 0))
    shadow = rgb(image, x * ratio, y * ratio)
    assert sum(shadow) < sum(background(view, image, x * ratio, y * ratio)) - 30
    view.camera.pitch = 20  # from below: no shadow in the way
    view._view_changed()
    image = view.image()
    assert is_background(view, image, 5, image.height() - 5)


def test_click_selects_and_tints_the_element_and_escape_clears(make_view):
    view = make_view(mesh=two_boxes())
    view.set_edges(False)
    plain = pixels_of(view.image()).astype(int)
    clicked = []
    view.element_clicked.connect(clicked.append)
    x, y = pixel_of(view, (2, 1.5, 3))
    send_mouse(view._renderer, QEvent.Type.MouseButtonPress, (x, y))
    send_mouse(view._renderer, QEvent.Type.MouseButtonRelease, (x, y))
    assert clicked == [WALL] and view.selected_label == WALL and view.selected_element == 0
    image = view.image()
    tinted = pixels_of(image).astype(int)
    ratio = image.width() / 400
    px, py = int(x * ratio), int(y * ratio)
    assert tinted[py, px, 1] > plain[py, px, 1] + 30  # more orange: green goes up on the red wall
    gx, gy = pixel_of(view, (7.5, 1.5, 2))
    assert abs(tinted[int(gy * ratio), int(gx * ratio)] - plain[int(gy * ratio), int(gx * ratio)]).max() <= 6
    view.setFocus()
    from PySide6.QtTest import QTest

    QTest.keyClick(view, Qt.Key.Key_Escape)
    assert clicked == [WALL, ""] and view.selected_label == "" and view.selected_element == -1
    assert numpy.abs(pixels_of(view.image()).astype(int) - plain).max() <= 6
    view.select_element(WINDOW)
    assert view.selected_element == 1
    view.select_element("no such element")
    assert view.selected_element == -1
    view.select_element(WALL)
    view.set_mesh(two_boxes())  # a new model: nothing selected
    assert view.selected_element == -1


# --------------------------------------------------------------------------- projection and animation


def test_orthographic_projection_keeps_parallel_lines_parallel(make_view):
    view = make_view(mesh=two_boxes())
    changes = []
    view.option_changed.connect(lambda key, value: changes.append((key, value)))
    assert view.projection == viewer.PERSPECTIVE
    near_edge = view.camera.project([[0, 0, 0], [4, 0, 0]])[0]
    far_edge = view.camera.project([[0, 3, 3], [4, 3, 3]])[0]
    assert not numpy.allclose(near_edge[1] - near_edge[0], far_edge[1] - far_edge[0], atol=0.5)  # perspective
    view.set_projection(viewer.ORTHOGRAPHIC)
    assert view.projection == viewer.ORTHOGRAPHIC and view.camera.orthographic
    assert view._tool_buttons["projection"].isChecked() and changes == [("projection", "orthographic")]
    near_edge = view.camera.project([[0, 0, 0], [4, 0, 0]])[0]
    far_edge = view.camera.project([[0, 3, 3], [4, 3, 3]])[0]
    assert numpy.allclose(near_edge[1] - near_edge[0], far_edge[1] - far_edge[0], atol=1e-6)
    pixels, depth = view.camera.project(view.mesh.positions)
    assert (pixels >= -0.5).all() and (pixels[:, 0] <= 400.5).all() and (pixels[:, 1] <= 300.5).all()  # refitted
    near_plane, far_plane = view.camera.clip_planes()
    assert (depth > near_plane).all() and (depth < far_plane).all()
    image = view.image()
    ratio = image.width() / 400
    x, y = pixel_of(view, (2, 1.5, 3))
    assert rgb(image, x * ratio, y * ratio)[0] > 120
    assert view.element_at(x, y) == WALL  # picking and the ray agree in the parallel projection too
    point = (7.5, 1.5, 2)
    x, y = pixel_of(view, point)
    wheel(view._renderer, (x, y), 2)
    assert numpy.allclose(pixel_of(view, point), (x, y), atol=0.5)  # zoom to the cursor
    drag(view._renderer, (x, y), (x + 50, y - 30), Qt.MouseButton.MiddleButton)
    assert numpy.allclose(pixel_of(view, point), (x + 50, y - 30), atol=0.5)  # pan
    view.setFocus()
    from PySide6.QtTest import QTest

    QTest.keyClick(view, Qt.Key.Key_P)
    assert view.projection == viewer.PERSPECTIVE and not view._tool_buttons["projection"].isChecked()
    assert changes == [("projection", "orthographic"), ("projection", "perspective")]


def test_view_changes_animate_to_the_end_state(make_view, monkeypatch, app):
    view = make_view(mesh=two_boxes())
    goal = viewer.Camera()
    goal.set_viewport(view.camera.width, view.camera.height)
    goal.set_model(*two_boxes().bounds(), viewer._fit_points(two_boxes()))
    goal.set_view(*viewer.VIEWS["top"])
    monkeypatch.setattr(viewer, "ANIMATION_MS", 250)
    started = time.monotonic()
    view.set_view("top")
    assert view.animating and view.camera.pitch > -90  # on its way
    while view.animating and time.monotonic() - started < 5:
        app.processEvents()
    assert not view.animating and 0.15 < time.monotonic() - started < 3
    assert (view.camera.yaw, view.camera.pitch) == viewer.VIEWS["top"]
    assert numpy.allclose(view.camera.target, goal.target) and view.camera.distance == pytest.approx(goal.distance)
    assert view._fitted
    # A press stops an animation where it is; a double-click starts the fit animation.
    view.camera.zoom(0.5)
    view.fit_view()
    assert view.animating
    send_mouse(view._renderer, QEvent.Type.MouseButtonPress, (10, 10))
    assert not view.animating
    send_mouse(view._renderer, QEvent.Type.MouseButtonRelease, (10, 10))
    send_mouse(view._renderer, QEvent.Type.MouseButtonDblClick, (10, 10))
    assert view.animating
    while view.animating and time.monotonic() - started < 10:
        app.processEvents()
    assert view.camera.distance == pytest.approx(goal.distance)


def test_pose_interpolation_takes_the_short_turn():
    start = (350.0, -10.0, numpy.zeros(3), 10.0)
    end = (10.0, -30.0, numpy.array([2.0, 0, 0]), 40.0)
    yaw, pitch, target, distance = viewer.interpolate_pose(start, end, 0.5)
    assert yaw % 360 == pytest.approx(0) and pitch == -20 and target.tolist() == [1, 0, 0] and distance == 20
    assert viewer.interpolate_pose(start, end, 1.0)[0] % 360 == pytest.approx(10)


def test_toolbar_is_compact_and_has_tooltips_with_shortcuts(make_view):
    view = make_view(400, 250, two_boxes())
    toolbar = view.toolbar
    assert toolbar.width() <= 230 and toolbar.height() <= 30
    tips = {name: button.toolTip() for name, button in toolbar.buttons.items()}
    assert tips["iso"].endswith("(1)") and tips["fit"].startswith("Ganzes Modell") and "(E)" in tips["edges"]
    assert "(P)" in tips["projection"]
    for name, button in toolbar.buttons.items():
        assert button.width() <= 28 and not button.icon().isNull(), name
        assert not button.icon().pixmap(16, QIcon.Mode.Disabled).isNull()  # greyed while no model is shown
    assert view._tool_buttons is toolbar.buttons


def test_toolbar_buttons_drive_the_view_and_follow_its_options(make_view):
    view = make_view(400, 250, two_boxes())
    buttons = view.toolbar.buttons
    assert list(buttons) == ["iso", "top", "front", "side", "fit", "edges", "projection"]
    buttons["top"].click()
    assert view.camera.pitch == -90
    buttons["side"].click()
    assert (view.camera.yaw, view.camera.pitch) == viewer.VIEWS["side"]
    buttons["iso"].click()
    assert (view.camera.yaw, view.camera.pitch) == viewer.VIEWS["iso"]
    fitted = view.camera.distance
    view.camera.zoom(0.4)
    buttons["fit"].click()
    assert view.camera.distance == pytest.approx(fitted)
    assert buttons["edges"].isChecked() and buttons["edges"].isCheckable()
    buttons["edges"].click()
    assert not view.edges_visible
    view.set_edges(True)
    assert buttons["edges"].isChecked()  # the view keeps the button in step (settings, key E)
    assert not buttons["projection"].isChecked()
    buttons["projection"].click()
    assert view.projection == viewer.ORTHOGRAPHIC
    view.set_projection(viewer.PERSPECTIVE)
    assert not buttons["projection"].isChecked()


# --------------------------------------------------------------------------- triad and chip in the image


def hued(image, box, channel: int, margin: int = 25) -> int:
    """How many pixels of ``image`` in ``box`` (x0, y0, x1, y1) are clearly red (0), green (1) or blue (2):
    that channel exceeds both others by ``margin``. The faint (away-pointing) axes still count."""
    x0, y0, x1, y1 = box
    region = pixels_of(image)[y0:y1, x0:x1].astype(int)
    others = numpy.delete(region, channel, axis=2).max(axis=2)
    return int((region[..., channel] - others > margin).sum())


def triad_box(image, view) -> tuple[int, int, int, int]:
    ratio = image.width() / view.width()
    size = int((2 * viewer.TRIAD_SIZE + 24) * ratio)
    return 0, image.height() - size, size, image.height()


@pytest.mark.parametrize("dark", [False, True])
def test_axis_triad_is_part_of_the_rendered_image(make_view, dark):
    # Drawn by the renderers themselves (QPainter in paintGL / into the software image), so it shows wherever
    # the model shows: not a widget over the GL view, which a Windows/NVIDIA PC did not composite.
    view = make_view(400, 300, boxes_mesh([((0, 0, 0), (4, 3, 3), (180, 180, 170, 255), WALL)]), dark=dark)
    image = view.image()
    box = triad_box(image, view)
    for channel in range(3):  # x red, y green, z blue, all pointing up in the start view
        assert hued(image, box, channel) >= 8, channel
    assert hued(image, (0, 0, image.width(), image.height() // 2), 2) == 0  # only in the corner (a grey model)
    view.camera.pitch = 20  # from below the x axis points down-right: still inside the corner
    view._view_changed()
    assert hued(view.image(), box, 0) >= 8
    view.set_mesh(None)
    image = view.image()
    for channel in range(3):
        assert hued(image, box, channel) == 0


@pytest.mark.parametrize("dark", [False, True])
def test_selection_chip_is_part_of_the_rendered_image(make_view, dark):
    view = make_view(400, 300, two_boxes(), dark=dark)
    view.set_edges(False)
    plain = pixels_of(view.image()).astype(int)
    view.select_element(WALL)
    image = view.image()
    with_chip = pixels_of(image).astype(int)
    ratio = image.width() / 400
    changed = numpy.abs(with_chip - plain).sum(axis=2) > 60
    band = (slice(int(262 * ratio), int(292 * ratio)), slice(int(150 * ratio), int(250 * ratio)))
    assert changed[band].sum() > 30  # the label's letters and the chip's rim at the bottom centre
    assert not is_background(view, image, 200 * ratio, 276 * ratio, 3) or dark  # the light chip over the gradient
    assert changed[: int(20 * ratio)].sum() == 0  # nothing at the top
    view.select_element("")
    assert numpy.abs(pixels_of(view.image()).astype(int) - plain).max() <= 6


# --------------------------------------------------------------------------- update_mesh (growing preview)


def grown(far=20.0) -> PreviewMesh:
    """two_boxes plus a third box far to the north-east: the bounds grow."""
    return boxes_mesh([((0, 0, 0), (4, 3, 3), RED, WALL), ((6, 0, 0), (9, 3, 2), GLASS, WINDOW),
                       ((far, far, 0), (far + 2, far + 2, 5), RED, "IfcColumn 3 „Stütze“")])


def inside_view(view) -> bool:
    pixels, _ = view.camera.project(view.mesh.positions)
    return bool((pixels >= -0.5).all() and (pixels[:, 0] <= view.camera.width + 0.5).all()
                and (pixels[:, 1] <= view.camera.height + 0.5).all())


def test_update_mesh_refits_while_fitted_and_keeps_the_pose_otherwise(make_view):
    view = make_view(400, 300, two_boxes())
    distance = view.camera.distance
    view.update_mesh(two_boxes())  # same bounds: nothing moves
    assert view.camera.distance == distance and view._fitted
    view.update_mesh(grown())
    assert view.mesh.triangle_count == 36 and view._fitted
    assert view.camera.distance > distance * 1.5 and inside_view(view)  # the whole grown model again
    assert (view.camera.yaw, view.camera.pitch) == viewer.VIEWS["iso"]
    assert not view.animating
    view.camera.orbit(30, 5)
    view.camera.zoom(0.6)
    view._view_changed()  # the user moved the view: it is theirs now
    pose = view.camera.pose()
    view.update_mesh(grown(40.0))
    assert view.mesh.triangle_count == 36 and not view._fitted
    yaw, pitch, target, far = view.camera.pose()
    assert (yaw, pitch, far) == (pose[0], pose[1], pose[3]) and numpy.array_equal(target, pose[2])
    assert not inside_view(view)  # not refitted
    x, y = pixel_of(view, (2, 1.5, 3))
    if 0 <= x < 400 and 0 <= y < 300:
        assert view.element_at(x, y) == WALL  # drawn where the kept pose says
    view.fit_view()
    assert view._fitted and inside_view(view)
    assert view.toolbar.isEnabled()


def test_update_mesh_keeps_the_selection_while_its_element_exists(make_view):
    view = make_view(400, 300, two_boxes())
    view.select_element(WINDOW)
    assert view.selected_element == 1
    reordered = boxes_mesh([((20, 20, 0), (22, 22, 5), RED, "IfcColumn 3 „Stütze“"), ((0, 0, 0), (4, 3, 3), RED, WALL),
                            ((6, 0, 0), (9, 3, 2), GLASS, WINDOW)])
    view.update_mesh(reordered)
    assert view.selected_element == 2 and view.selected_label == WINDOW
    view.update_mesh(boxes_mesh([((0, 0, 0), (4, 3, 3), RED, WALL)]))
    assert view.selected_element == -1 and view.selected_label == ""
    assert view.element_at(*pixel_of(view, (2, 1.5, 3))) == WALL  # picking works on the new mesh


def test_update_mesh_without_a_model_or_with_a_message_shows_the_model(make_view):
    view = make_view(400, 300)
    view.set_message("Vorschau wird berechnet …")
    view.update_mesh(two_boxes())  # like set_mesh: start view, message gone, toolbar on
    assert view.mesh is not None and view.message() == "" and view._stack.currentWidget() is view._renderer
    assert view.toolbar.isEnabled() and view._fitted and inside_view(view)
    view.set_message("Vorschau wird berechnet … 40 %")
    view.update_mesh(grown())
    assert view.message() == "" and view._stack.currentWidget() is view._renderer
    view.update_mesh(None)
    assert view.mesh is None and not view.toolbar.isEnabled()


def test_update_mesh_finishes_a_running_animation_first(make_view, monkeypatch, app):
    view = make_view(400, 300, two_boxes())
    monkeypatch.setattr(viewer, "ANIMATION_MS", 250)
    view.set_view("top")
    assert view.animating
    view.update_mesh(grown())
    assert not view.animating and (view.camera.yaw, view.camera.pitch) == viewer.VIEWS["top"]
    assert view._fitted and inside_view(view)


def test_update_mesh_computes_edges_once_the_mesh_settles_and_never_twice_at_once(make_view, monkeypatch, app):
    from PySide6.QtTest import QTest

    monkeypatch.setattr(viewer, "EDGES_IN_BACKGROUND", 10)
    monkeypatch.setattr(viewer, "EDGE_SETTLE_MS", 300)
    calls, running, overlap = [], [0], [0]
    original = viewer.feature_edges

    def counted(mesh, *args, **kwargs):
        running[0] += 1
        overlap[0] = max(overlap[0], running[0])
        calls.append(mesh.triangle_count)
        time.sleep(0.15)
        try:
            return original(mesh, *args, **kwargs)
        finally:
            running[0] -= 1

    monkeypatch.setattr(viewer, "feature_edges", counted)
    view = make_view(400, 300)
    view.set_mesh(many_boxes(20))  # in a thread (> EDGES_IN_BACKGROUND)
    assert view.wait_for_edges() and calls == [240]
    for count in (30, 40, 50, 60):  # a growing preview, every few seconds: no edge work per call
        view.update_mesh(many_boxes(count))
        QTest.qWait(30)
    assert calls == [240] and view._scene.edge_thread is None
    deadline = time.monotonic() + 5
    while (view._scene.edges is None or view._scene.edge_thread.is_alive()) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert calls == [240, 720]  # only the settled mesh
    image = view.image()
    view.set_edges(False)
    assert (numpy.abs(pixels_of(image).astype(int) - pixels_of(view.image()).astype(int)).max(axis=2) > 20).any()
    view.set_edges(True)
    # A new mesh while a thread still works on the old one: it waits for its turn, one thread at a time.
    view.set_mesh(many_boxes(70))
    first = view._scene
    assert first.edge_thread is not None and first.edge_thread.is_alive()
    view.set_mesh(many_boxes(80))
    second = view._scene
    assert second.edge_thread is None  # not started yet
    deadline = time.monotonic() + 5
    while second.edges is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert second.edges is not None and calls == [240, 720, 840, 960] and overlap[0] == 1


def test_waiting_scene_gets_its_edges_as_soon_as_the_old_thread_reports(make_view, monkeypatch, app):
    # The thread reports (signal) before it has exited: the view must not wait for the exit, or the next
    # scene would never get its edges.
    monkeypatch.setattr(viewer, "EDGES_IN_BACKGROUND", 10)
    original = viewer.feature_edges
    release = threading.Event()

    def slow(mesh, *args, **kwargs):
        result = original(mesh, *args, **kwargs)
        release.wait(5)
        return result

    monkeypatch.setattr(viewer, "feature_edges", slow)
    view = make_view(400, 300)
    view.set_mesh(many_boxes(20))
    first = view._scene
    view.set_mesh(many_boxes(30))
    second = view._scene
    assert first.edge_thread.is_alive() and second.edge_thread is None
    view._edges_computed(first)  # as the queued signal would arrive while the thread still runs
    assert second.edge_thread is not None
    release.set()
    assert view.wait_for_edges() and len(second.edges) == 360
