import threading
import time
from pathlib import Path

import numpy
import pytest
from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import QApplication, QLabel

from ifc_converter import gui, preview, preview_pane
from ifc_converter.preview import PreviewMesh, save_preview
from ifc_converter.process import Cancelled


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeView(QLabel):
    element_clicked = Signal(str)
    renderer_name = "Test"

    def __init__(self):
        super().__init__()
        self.mesh = None
        self.message = ""

    def set_mesh(self, mesh):
        self.mesh = mesh

    def set_message(self, text):
        self.message = text

    def reset_view(self):
        pass


def _mesh(elements=3) -> PreviewMesh:
    return PreviewMesh(
        positions=numpy.zeros((3, 3), numpy.float32), colors=numpy.full((3, 4), 255, numpy.uint8),
        indices=numpy.array([0, 1, 2], numpy.uint32), triangle_elements=numpy.zeros(1, numpy.uint32),
        elements=["IfcWall 0abc „Wand“"], info={"elements": elements},
    )


def wait_until(app, condition, timeout=10):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return condition()


@pytest.fixture
def previews(tmp_path, monkeypatch):
    """Cache in tmp_path; compute_preview writes a small mesh unless told otherwise."""
    cache = tmp_path / "cache"
    cache.mkdir()
    calls = []
    behaviour = {"mode": "ok"}
    release = threading.Event()

    def path_of(ifc):
        return cache / (Path(ifc).name + ".npz")

    def cached(ifc):
        found = path_of(ifc)
        return found if found.exists() else None

    def compute(source, target, progress=None, status=None, cancelled=lambda: False, on_retry=None, **options):
        calls.append(Path(source))
        behaviour["threads"] = options.get("threads")
        progress(10)
        if behaviour["mode"] == "wait":
            while not release.wait(0.01):
                if cancelled():
                    raise Cancelled
        if behaviour["mode"] == "fail":
            raise ValueError("Die Datei enthält keine Bauteile mit Geometrie.")
        if behaviour["mode"] == "script":  # batches, waits, retries as the test scripted them
            for step, *args in behaviour["script"]:
                if step == "batch":
                    token, number, labels = args
                    save_preview(_batch(labels, number), preview.batch_path(target, token, number))
                elif step == "wait":
                    while not args[0].wait(0.01):
                        if cancelled():
                            raise Cancelled
                elif step == "retry":
                    on_retry(args[0])
                elif step == "progress":
                    progress(args[0])
                elif step == "fail":
                    raise ValueError(args[0])
                elif step == "cancelled":
                    while not cancelled():
                        time.sleep(0.01)
                    raise Cancelled
        save_preview(_mesh(), target)

    monkeypatch.setattr(preview, "preview_path", path_of, raising=False)
    monkeypatch.setattr(preview, "cached_preview", cached, raising=False)
    monkeypatch.setattr(preview, "compute_preview", compute, raising=False)
    monkeypatch.setattr(preview, "fits_in_memory", lambda size, busy=False: behaviour.get("fits", True), raising=False)
    return calls, behaviour, release, path_of


def _batch(labels, number, total=5) -> PreviewMesh:
    """A batch file's mesh: one triangle per element, with the info a batch carries."""
    count = len(labels)
    return PreviewMesh(
        positions=numpy.zeros((3 * count, 3), numpy.float32), colors=numpy.full((3 * count, 4), 255, numpy.uint8),
        indices=numpy.arange(3 * count, dtype=numpy.uint32), triangle_elements=numpy.arange(count, dtype=numpy.uint32),
        elements=list(labels), info={"elements_total": total, "details_left_out": 7, "detail_kinds": "furniture,mep",
                                      "batch": number, "elements": count},
    )


class GrowingView(FakeView):
    """A view that can replace its mesh without resetting the camera, like the real one."""

    def __init__(self):
        super().__init__()
        self.updates = 0

    def update_mesh(self, mesh):
        self.mesh = mesh
        self.updates += 1


def ifc(tmp_path, name="a.ifc", size=10):
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    return path


def test_a_small_file_gets_its_preview_right_away(app, tmp_path, previews):
    calls, *_ = previews
    pane = preview_pane.PreviewPane(view_factory=FakeView)
    pane.show_file(ifc(tmp_path))
    assert wait_until(app, lambda: pane.view.mesh is not None)
    assert calls == [tmp_path / "a.ifc"]
    assert "3 Bauteile" in pane.info.text() and "Darstellung: Test" in pane.info.text()
    pane.view.element_clicked.emit("IfcWall 0abc „Wand“")
    assert pane.info.text() == "IfcWall 0abc „Wand“"

    calls.clear()  # selected again: from the cache
    pane.show_file(None)
    assert pane.view.message == preview_pane.no_file_text()
    pane.show_file(tmp_path / "a.ifc")
    assert wait_until(app, lambda: pane.view.mesh is not None) and calls == []
    pane.shutdown()


@pytest.mark.parametrize("why", ["large", "converting", "unknown"])
def test_files_without_room_in_memory_wait_for_a_click(app, tmp_path, previews, monkeypatch, why):
    calls, behaviour, *_ = previews
    behaviour["fits"] = None if why == "unknown" else False
    if why == "unknown":  # free memory unknown: by size
        monkeypatch.setattr(preview_pane, "AUTO_PREVIEW_SIZE", 5)
    pane = preview_pane.PreviewPane(busy=lambda: why == "converting", view_factory=FakeView)
    pane.show_file(ifc(tmp_path))
    app.processEvents()
    assert calls == [] and not pane.compute_button.isHidden()
    assert ("Während einer Konvertierung" if why == "converting" else "Große Datei") in pane.view.message
    pane.compute_button.click()
    assert wait_until(app, lambda: pane.view.mesh is not None) and len(calls) == 1
    pane.shutdown()


def test_any_size_starts_at_once_with_room_in_memory_also_beside_a_conversion(app, tmp_path, previews, monkeypatch):
    calls, behaviour, *_ = previews
    monkeypatch.setattr(preview_pane, "AUTO_PREVIEW_SIZE", 5)  # the size does not matter any more
    monkeypatch.setattr(preview, "preview_threads", lambda busy=False: 3 if busy else 7, raising=False)
    pane = preview_pane.PreviewPane(busy=lambda: True, view_factory=FakeView)
    pane.show_file(ifc(tmp_path, size=100))
    assert wait_until(app, lambda: pane.view.mesh is not None)
    assert calls == [tmp_path / "a.ifc"] and behaviour["threads"] == 3  # fewer threads beside the conversion
    pane.shutdown()
    idle = preview_pane.PreviewPane(busy=lambda: False, view_factory=FakeView)
    idle.show_file(ifc(tmp_path, "b.ifc", size=100))
    assert wait_until(app, lambda: idle.view.mesh is not None) and behaviour["threads"] == 7
    idle.shutdown()
    assert "höchstens 8 Threads, 4 während einer Konvertierung" in idle.compute_button.toolTip()


def test_selecting_another_file_cancels_an_unrequested_preview(app, tmp_path, previews):
    calls, behaviour, release, path_of = previews
    behaviour["mode"] = "wait"
    pane = preview_pane.PreviewPane(view_factory=FakeView)
    first, second = ifc(tmp_path, "a.ifc"), ifc(tmp_path, "b.ifc")
    pane.show_file(first)
    assert wait_until(app, lambda: calls == [first])
    assert not pane.cancel_button.isHidden()
    behaviour["mode"] = "ok"
    pane.show_file(second)  # the first is cancelled, the second starts once it has stopped
    assert wait_until(app, lambda: pane.view.mesh is not None)
    assert calls == [first, second] and not path_of(first).exists()
    pane.shutdown()


def test_a_requested_preview_keeps_running_when_another_file_is_selected(app, tmp_path, previews):
    calls, behaviour, release, path_of = previews
    behaviour["mode"], behaviour["fits"] = "wait", False
    pane = preview_pane.PreviewPane(busy=lambda: True, view_factory=FakeView)
    first, second = ifc(tmp_path, "a.ifc"), ifc(tmp_path, "b.ifc")
    pane.show_file(first)
    pane.compute()
    assert wait_until(app, lambda: calls == [first])
    pane.show_file(second)
    release.set()
    assert wait_until(app, lambda: path_of(first).exists())
    assert pane.view.mesh is None and pane.path == second  # cached for later, the second is still shown
    pane.show_file(first)
    assert wait_until(app, lambda: pane.view.mesh is not None)
    pane.shutdown()


def test_a_failed_preview_says_why(app, tmp_path, previews):
    _, behaviour, *_ = previews
    behaviour["mode"] = "fail"
    pane = preview_pane.PreviewPane(view_factory=FakeView)
    pane.show_file(ifc(tmp_path))
    assert wait_until(app, lambda: pane.view.message.startswith("Keine Vorschau möglich"))
    assert "keine Bauteile mit Geometrie" in pane.view.message and not pane.compute_button.isHidden()
    assert pane.compute_button.text() == "Erneut versuchen"
    calls, *_ = previews
    pane.show_file(None)
    pane.show_file(tmp_path / "a.ifc")  # remembered: not computed again unasked
    app.processEvents()
    assert len(calls) == 1 and pane.view.message.startswith("Keine Vorschau möglich")
    behaviour["mode"] = "ok"
    pane.compute_button.click()
    assert wait_until(app, lambda: pane.view.mesh is not None) and len(calls) == 2
    pane.shutdown()


def test_the_window_previews_the_selected_file_and_can_hide_it(app, tmp_path, previews, monkeypatch):
    calls, *_ = previews
    monkeypatch.setattr(preview_pane, "_make_view", FakeView)
    monkeypatch.setattr(gui.PreviewPane.__init__, "__defaults__", (lambda: False, FakeView, None, None))
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = gui.MainWindow(settings=settings)
    try:
        window.add_paths([ifc(tmp_path, "hidden.ifc")])
        app.processEvents()
        assert calls == []  # nothing is computed for a window that is not shown (e.g. in tests)
        window.clear_list()
        window.show()
        window.add_paths([ifc(tmp_path, "a.ifc"), ifc(tmp_path, "b.ifc")])
        assert wait_until(app, lambda: window.preview.view.mesh is not None)
        assert calls == [tmp_path / "a.ifc"]  # the first added file is selected
        window.table.selectRow(1)
        assert wait_until(app, lambda: calls == [tmp_path / "a.ifc", tmp_path / "b.ifc"])
        window.set_preview_visible(False)
        assert window.preview.isHidden() and settings.value("preview_visible", type=bool) is False
    finally:
        window.close()
        window.deleteLater()


def test_title_and_info_line_shorten_long_names_instead_of_widening(app, tmp_path, previews):
    pane = preview_pane.PreviewPane(view_factory=FakeView)
    pane.resize(300, 300)
    pane.show()
    name = "Ein_ausgesprochen_langer_Projektname_mit_vielen_Zeichen_2026_Architektur.ifc"
    pane.show_file(ifc(tmp_path, name))
    assert wait_until(app, lambda: pane.view.mesh is not None)
    assert pane.title.text() == f"Vorschau – {name}"  # the full text, drawn shortened
    assert pane.title.minimumSizeHint().width() < 40
    assert pane.info.minimumHeight() > 0  # keeps its line when empty: no jumping view
    pane.show_file(None)
    assert pane.info.text() == "" and pane.title.text() == "Vorschau"
    assert pane.info.minimumHeight() > 0
    pane.shutdown()
    pane.close()


class OptionView(FakeView):
    """A view with options, like PreviewView: edges and projection, reported through option_changed."""

    option_changed = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.edges = True
        self.projection = "perspective"

    def set_edges(self, visible):
        self.edges = visible

    def set_projection(self, projection):
        self.projection = projection


def test_view_options_are_restored_from_and_kept_in_the_settings(app, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("preview_edges", False)
    settings.setValue("preview_projection", "orthographic")
    pane = preview_pane.PreviewPane(view_factory=OptionView, settings=settings)
    assert pane.view.edges is False and pane.view.projection == "orthographic"
    pane.view.option_changed.emit("edges", True)
    pane.view.option_changed.emit("projection", "perspective")
    pane.view.option_changed.emit("unknown", 1)
    assert settings.value("preview_edges", type=bool) is True
    assert settings.value("preview_projection") == "perspective" and settings.value("unknown") is None
    fresh = preview_pane.PreviewPane(view_factory=OptionView, settings=QSettings(str(tmp_path / "new.ini"),
                                                                                QSettings.Format.IniFormat))
    assert fresh.view.edges is True and fresh.view.projection == "perspective"  # the defaults
    plain = preview_pane.PreviewPane(view_factory=OptionView)  # without settings: nothing restored, nothing kept
    plain.view.option_changed.emit("edges", False)
    assert plain.view.edges is True
    preview_pane.PreviewPane(view_factory=FakeView, settings=settings)  # a view without options is fine
    for widget in (pane, fresh, plain):
        widget.shutdown()


def test_the_real_view_in_the_pane_keeps_its_options(app, tmp_path, monkeypatch):
    monkeypatch.setenv("IFC_CONVERTER_PREVIEW_RENDERER", "software")
    from ifc_converter import viewer

    viewer.opengl_problem.cache_clear()
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("preview_projection", "orthographic")
    pane = preview_pane.PreviewPane(view_factory=viewer.PreviewView, settings=settings)
    assert pane.view.projection == "orthographic" and pane.view.edges_visible
    pane.view.set_edges(False)
    assert settings.value("preview_edges", type=bool) is False
    # The view's buttons sit in the pane's header (always visible, greyed out without a model), not over the view.
    toolbar = pane.view.toolbar
    assert toolbar.parentWidget() is pane and not toolbar.isEnabled()
    header = pane.layout().itemAt(0).layout()
    assert header.indexOf(toolbar) == header.indexOf(pane.reset_button) - 1
    assert toolbar.buttons["projection"].isChecked() and not toolbar.buttons["edges"].isChecked()
    pane.shutdown()
    viewer.opengl_problem.cache_clear()


# The progressive preview: batch files are shown as they come, kept after a cancel or crash.


def _script(previews, *steps):
    _, behaviour, *_ = previews
    behaviour["mode"], behaviour["script"] = "script", list(steps)


def _elements(pane) -> list:
    return list(pane.view.mesh.elements) if pane.view.mesh is not None else []


@pytest.mark.parametrize("view_class", [GrowingView, FakeView])
def test_the_preview_grows_from_batches_until_the_whole_is_loaded(app, tmp_path, previews, monkeypatch, view_class):
    calls, behaviour, release, path_of = previews
    monkeypatch.setattr(preview_pane, "BATCH_POLL_MS", 20)
    steps = [threading.Event() for _ in range(3)]
    _script(previews, ("batch", 1, 1, ["IfcSlab 1"]), ("wait", steps[0]), ("progress", 40),
            ("batch", 1, 2, ["IfcWall 2", "IfcWall 3"]), ("wait", steps[1]), ("progress", 80), ("wait", steps[2]))
    pane = preview_pane.PreviewPane(view_factory=view_class)
    pane.show_file(ifc(tmp_path))
    assert wait_until(app, lambda: _elements(pane) == ["IfcSlab 1"])
    assert pane.info.text().startswith("Vorschau wird berechnet … 10 % · bisher 1 von 5 Bauteilen · 7 Details weggelassen "
                                       "(Möbel, Haustechnik) · Darstellung: Test")
    assert not pane.cancel_button.isHidden() and not pane.reset_button.isHidden() and pane.compute_button.isHidden()
    steps[0].set()
    assert wait_until(app, lambda: _elements(pane) == ["IfcSlab 1", "IfcWall 2", "IfcWall 3"])
    assert wait_until(app, lambda: pane.info.text().startswith("Vorschau wird berechnet … 40 % · bisher 3 von 5"))
    assert pane.view.mesh.info["partial"] == 1 and pane.view.mesh.triangle_count == 3
    if view_class is GrowingView:
        assert pane.view.updates == 1  # the first batch from the start view, the second keeps the camera
    pane.view.element_clicked.emit("IfcWall 2")
    assert pane.info.text() == "IfcWall 2"
    steps[1].set()
    assert wait_until(app, lambda: pane.info.text().startswith("Vorschau wird berechnet … 80 %"))
    assert len(preview.batch_paths(path_of(tmp_path / "a.ifc"))) == 2
    steps[2].set()  # the whole preview is saved and loaded; the batch files go
    assert wait_until(app, lambda: pane.view.mesh is not None and "partial" not in pane.view.mesh.info)
    assert pane.info.text().startswith("3 Bauteile · Darstellung: Test")
    assert preview.batch_paths(path_of(tmp_path / "a.ifc")) == [] and path_of(tmp_path / "a.ifc").exists()
    assert pane.cancel_button.isHidden() and not pane.reset_button.isHidden()
    if view_class is GrowingView:
        assert pane.view.updates == 2
    pane.shutdown()


def test_a_cancelled_preview_keeps_what_it_shows(app, tmp_path, previews, monkeypatch):
    calls, behaviour, release, path_of = previews
    monkeypatch.setattr(preview_pane, "BATCH_POLL_MS", 20)
    _script(previews, ("batch", 1, 1, ["IfcSlab 1", "IfcRoof 2"]), ("cancelled",))
    pane = preview_pane.PreviewPane(view_factory=GrowingView)
    pane.show_file(ifc(tmp_path))
    assert wait_until(app, lambda: _elements(pane) == ["IfcSlab 1", "IfcRoof 2"])
    pane.cancel_button.click()
    assert wait_until(app, lambda: not pane.is_computing)
    assert _elements(pane) == ["IfcSlab 1", "IfcRoof 2"]  # still there
    assert pane.info.text().startswith("Vorschau abgebrochen – unvollständig · bisher 2 von 5 Bauteilen")
    assert not pane.compute_button.isHidden() and pane.compute_button.text() == "Vorschau berechnen"
    assert not pane.reset_button.isHidden() and pane.cancel_button.isHidden()
    assert not path_of(tmp_path / "a.ifc").exists() and preview.batch_paths(path_of(tmp_path / "a.ifc")) == []
    behaviour["mode"] = "ok"
    pane.compute_button.click()  # computes again, from the start
    assert wait_until(app, lambda: pane.view.mesh is not None and "partial" not in pane.view.mesh.info)
    assert len(calls) == 2
    pane.shutdown()


def test_after_two_new_attempts_the_preview_stops_and_keeps_what_it_shows(app, tmp_path, previews, monkeypatch):
    calls, behaviour, release, path_of = previews
    monkeypatch.setattr(preview_pane, "BATCH_POLL_MS", 20)
    steps = [threading.Event() for _ in range(3)]
    _script(previews,
            ("batch", 1, 1, ["IfcSlab 1"]), ("batch", 1, 2, ["IfcWall 2", "IfcWall 3"]), ("wait", steps[0]),
            ("retry", "Absturz im schnellen Geometriekern – neuer Versuch nur mit OpenCASCADE …"),
            ("batch", 2, 1, ["IfcSlab 1b"]), ("wait", steps[1]),  # the new attempt starts over …
            ("batch", 2, 2, ["IfcWall 2b", "IfcWall 3b", "IfcColumn 4b"]), ("wait", steps[2]),  # … and catches up
            ("retry", "Neuer Versuch (3. von höchstens 7) …"), ("cancelled",))
    pane = preview_pane.PreviewPane(view_factory=GrowingView)
    pane.show_file(ifc(tmp_path))
    assert wait_until(app, lambda: _elements(pane) == ["IfcSlab 1", "IfcWall 2", "IfcWall 3"])
    steps[0].set()
    assert wait_until(app, lambda: pane.info.text().startswith("Vorschau bisher unvollständig (der Geometriekern ist "
                                                               "abgestürzt), der Rest wird berechnet …"))
    assert "bisher 3 von 5 Bauteilen" in pane.info.text()
    assert wait_until(app, lambda: len(preview.batch_paths(path_of(tmp_path / "a.ifc"))) == 3)
    app.processEvents()
    assert _elements(pane) == ["IfcSlab 1", "IfcWall 2", "IfcWall 3"]  # the new attempt has less so far
    steps[1].set()
    assert wait_until(app, lambda: _elements(pane) == ["IfcSlab 1b", "IfcWall 2b", "IfcWall 3b", "IfcColumn 4b"])
    assert "bisher 4 von 5 Bauteilen" in pane.info.text()
    steps[2].set()  # the second new attempt: enough, the preview is cancelled
    assert wait_until(app, lambda: not pane.is_computing)
    assert _elements(pane) == ["IfcSlab 1b", "IfcWall 2b", "IfcWall 3b", "IfcColumn 4b"]
    assert pane.info.text().startswith("Vorschau unvollständig (der Geometriekern ist wiederholt abgestürzt) · "
                                       "bisher 4 von 5 Bauteilen")
    assert not pane.compute_button.isHidden() and pane.compute_button.text() == "Vorschau berechnen"
    assert not path_of(tmp_path / "a.ifc").exists()  # not cached: a click tries again
    assert len(calls) == 1
    pane.shutdown()


def test_without_anything_shown_the_retry_limit_reports_the_crashes(app, tmp_path, previews):
    _script(previews, ("retry", "Absturz …"), ("retry", "Absturz …"), ("cancelled",))
    pane = preview_pane.PreviewPane(view_factory=GrowingView)
    pane.show_file(ifc(tmp_path))
    assert wait_until(app, lambda: not pane.is_computing)
    assert pane.view.mesh is None and not pane.compute_button.isHidden()
    assert pane.view.message == "Keine Vorschau möglich: Der Geometriekern ist wiederholt abgestürzt."
    pane.shutdown()


def test_a_failure_after_batches_keeps_them_and_says_why(app, tmp_path, previews, monkeypatch):
    calls, behaviour, release, path_of = previews
    monkeypatch.setattr(preview_pane, "BATCH_POLL_MS", 20)
    step = threading.Event()
    _script(previews, ("batch", 1, 1, ["IfcSlab 1"]), ("wait", step), ("fail", "Zu viele Dreiecke für die Vorschau."))
    pane = preview_pane.PreviewPane(view_factory=GrowingView)
    pane.show_file(ifc(tmp_path))
    assert wait_until(app, lambda: _elements(pane) == ["IfcSlab 1"])
    step.set()
    assert wait_until(app, lambda: not pane.is_computing)
    assert _elements(pane) == ["IfcSlab 1"]
    assert pane.info.text().startswith("Vorschau unvollständig: Zu viele Dreiecke für die Vorschau. · bisher 1 von 5")
    assert pane.compute_button.text() == "Erneut versuchen" and not pane.compute_button.isHidden()
    pane.show_file(None)
    pane.show_file(tmp_path / "a.ifc")  # remembered as failed
    app.processEvents()
    assert pane.view.message.startswith("Keine Vorschau möglich") and len(calls) == 1
    pane.shutdown()


def test_batches_of_a_file_no_longer_shown_are_merged_but_not_shown(app, tmp_path, previews, monkeypatch):
    calls, behaviour, release, path_of = previews
    monkeypatch.setattr(preview_pane, "BATCH_POLL_MS", 20)
    behaviour["fits"] = False  # the second file waits, so the pane stays with the first task
    steps = [threading.Event() for _ in range(2)]
    _script(previews, ("batch", 1, 1, ["IfcSlab 1"]), ("wait", steps[0]), ("batch", 1, 2, ["IfcWall 2"]),
            ("wait", steps[1]))
    pane = preview_pane.PreviewPane(view_factory=GrowingView)
    first, second = ifc(tmp_path, "a.ifc"), ifc(tmp_path, "b.ifc")
    pane.show_file(first)
    pane.compute()  # requested: keeps running
    assert wait_until(app, lambda: _elements(pane) == ["IfcSlab 1"])
    pane.show_file(second)
    assert pane.view.mesh is None and "Große Datei" in pane.view.message
    steps[0].set()
    assert wait_until(app, lambda: len(pane._loaded_batches) == 2)
    assert pane.view.mesh is None
    pane.show_file(first)  # back: what there is so far
    assert _elements(pane) == ["IfcSlab 1", "IfcWall 2"] and "bisher 2 von 5" in pane.info.text()
    steps[1].set()
    assert wait_until(app, lambda: pane.view.mesh is not None and "partial" not in pane.view.mesh.info)
    pane.shutdown()
