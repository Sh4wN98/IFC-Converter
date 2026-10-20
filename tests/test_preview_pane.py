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

    def compute(source, target, progress=None, status=None, cancelled=lambda: False, **options):
        calls.append(Path(source))
        progress(10)
        if behaviour["mode"] == "wait":
            while not release.wait(0.01):
                if cancelled():
                    raise Cancelled
        if behaviour["mode"] == "fail":
            raise ValueError("Die Datei enthält keine Bauteile mit Geometrie.")
        save_preview(_mesh(), target)

    monkeypatch.setattr(preview, "preview_path", path_of, raising=False)
    monkeypatch.setattr(preview, "cached_preview", cached, raising=False)
    monkeypatch.setattr(preview, "compute_preview", compute, raising=False)
    return calls, behaviour, release, path_of


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


@pytest.mark.parametrize("why", ["large", "converting"])
def test_large_files_and_files_during_a_conversion_wait_for_a_click(app, tmp_path, previews, monkeypatch, why):
    calls, *_ = previews
    if why == "large":
        monkeypatch.setattr(preview_pane, "AUTO_PREVIEW_SIZE", 5)
    pane = preview_pane.PreviewPane(busy=lambda: why == "converting", view_factory=FakeView)
    pane.show_file(ifc(tmp_path))
    app.processEvents()
    assert calls == [] and not pane.compute_button.isHidden()
    assert ("Große Datei" if why == "large" else "Während einer Konvertierung") in pane.view.message
    pane.compute_button.click()
    assert wait_until(app, lambda: pane.view.mesh is not None) and len(calls) == 1
    pane.shutdown()


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
    behaviour["mode"] = "wait"
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
    monkeypatch.setattr(gui.PreviewPane.__init__, "__defaults__", (lambda: False, FakeView, None))
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
