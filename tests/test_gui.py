import os
import sys
import time
from functools import partial

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEventLoop, QMimeData, QPointF, QSettings, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import child_helpers  # noqa: E402
from ifc_converter import gui, process  # noqa: E402
from ifc_converter.converter import ConversionResult  # noqa: E402
from ifc_converter.gui import ConversionWorker, FileQueue, Status, format_size  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("output_dir", str(out))
    return settings


@pytest.fixture
def window(app, settings):
    window = gui.MainWindow(settings=settings)
    yield window
    window.close()
    window.deleteLater()


def wait_finished(window, timeout_ms=60_000):
    """Spin an event loop until the window reports the batch finished; returns the cancelled flag."""
    result = {}
    loop = QEventLoop()

    def done(cancelled):
        result["cancelled"] = cancelled
        loop.quit()

    window.conversion_finished.connect(done)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    window.conversion_finished.disconnect(done)
    assert "cancelled" in result, "conversion did not finish in time"
    return result["cancelled"]


def test_window_builds_with_defaults(window, tmp_path):
    assert window.windowTitle() == "IFC File Converter"
    assert window.fmt == "3dm"
    assert window.output_dir == tmp_path / "out"
    assert not window.convert_button.isEnabled()
    assert set(window.format_buttons) == {"3dm", "glb", "obj"}


def test_queue_adds_folders_rejects_non_ifc_and_ignores_duplicates(tmp_path):
    (tmp_path / "proj" / "sub").mkdir(parents=True)
    a = tmp_path / "proj" / "a.ifc"
    b = tmp_path / "proj" / "sub" / "b.IFC"
    a.write_text("x")
    b.write_text("y")
    note = tmp_path / "notes.txt"
    note.write_text("z")

    queue = FileQueue()
    result = queue.add([tmp_path / "proj", note])
    assert result.added == [a, b]
    assert result.rejected == [note]

    again = queue.add([a, str(b)])
    assert again.added == [] and again.duplicates == [a, b]
    assert [item.path for item in queue.items] == [a, b]
    assert queue[0].status_text == "Wartend"

    queue.remove([0])
    assert [item.path for item in queue.items] == [b]


def test_prepare_run_skips_done_files_unless_all_done(tmp_path):
    queue = FileQueue()
    for name in ("a.ifc", "b.ifc"):
        (tmp_path / name).write_text("x")
    queue.add([tmp_path / "a.ifc", tmp_path / "b.ifc"])
    queue[0].status = Status.DONE
    queue[1].status = Status.FAILED
    assert queue.prepare_run() == [1]
    assert queue[1].status is Status.WAITING
    queue[1].status = Status.DONE
    assert queue.prepare_run() == [0, 1]


def test_format_size():
    assert format_size(512) == "512 B"
    assert format_size(1536) == "1,5 KB"
    assert format_size(3 * 1024 * 1024) == "3,0 MB"


def test_window_add_paths_updates_table(window, wall_ifc, tmp_path):
    other = tmp_path / "foto.jpg"
    other.write_text("x")
    result = window.add_paths([wall_ifc, other, wall_ifc])
    assert result.added == [wall_ifc]
    assert result.rejected == [other]
    assert window.table.rowCount() == 1
    assert window.table.item(0, 0).text() == "wall.ifc"
    assert window.status_text(0) == "Wartend"
    assert window.convert_button.isEnabled()
    assert "Keine IFC-Datei" in window.log_view.toPlainText()

    window.clear_list()
    assert window.table.rowCount() == 0
    assert not window.convert_button.isEnabled()


def test_drop_event_adds_files(window, wall_ifc):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(wall_ifc.parent))])
    event = QDropEvent(
        QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    window.dropEvent(event)
    assert [item.path for item in window.queue.items] == [wall_ifc]


def test_converts_in_background_and_continues_after_errors(window, wall_ifc, tmp_path):
    broken = tmp_path / "kaputt.ifc"
    broken.write_text("this is not an IFC file")
    window.set_format("glb")
    window.add_paths([broken, wall_ifc])

    window.start_conversion()
    assert window.is_running
    assert not window.clear_button.isEnabled()
    assert wait_finished(window) is False

    out = tmp_path / "out"
    assert (out / "wall.glb").stat().st_size > 0
    assert not (out / "kaputt.glb").exists()
    assert window.queue[0].status is Status.FAILED
    assert window.status_text(0).startswith("Fehler: ")
    assert window.queue[1].status is Status.DONE
    assert window.status_text(1) == "Fertig – 1 Bauteile"
    assert window.overall_progress.value() == 100
    assert window.open_button.isEnabled()
    assert window.convert_button.isEnabled()

    # Converting again only retries the failed file; the done one is left alone.
    window.start_conversion()
    wait_finished(window)
    assert not (out / "wall (2).glb").exists()


def test_name_collisions_and_beside_input(window, wall_ifc, tmp_path):
    out = tmp_path / "out"
    (out / "wall.obj").write_text("existing")
    window.set_format("obj")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert (out / "wall (2).obj").exists()
    assert (out / "wall.obj").read_text() == "existing"

    window.beside_check.setChecked(True)
    assert not window.output_button.isEnabled()
    window.start_conversion()  # everything done -> converts all again
    wait_finished(window)
    assert (wall_ifc.parent / "wall.obj").exists()


def test_cancelled_worker_marks_files_and_writes_nothing(app, wall_ifc, tmp_path):
    worker = ConversionWorker([(0, wall_ifc)], "glb", tmp_path)
    events = []
    worker.file_cancelled.connect(lambda row: events.append(("cancelled", row)))
    worker.finished.connect(lambda cancelled: events.append(("finished", cancelled)))
    worker.cancel()
    worker.run()  # synchronously in the test thread
    assert events == [("cancelled", 0), ("finished", True)]
    assert not (tmp_path / "wall.glb").exists()


def test_cancel_via_progress_callback_removes_partial_output(app, wall_ifc, tmp_path):
    worker = ConversionWorker([(0, wall_ifc)], "glb", tmp_path)
    events = []
    # Cancel as soon as the first progress update arrives, i.e. while convert() is running.
    worker.file_progress.connect(lambda row, pct: worker.cancel())
    worker.file_cancelled.connect(lambda row: events.append("cancelled"))
    worker.file_done.connect(lambda *args: events.append("done"))
    worker.run()
    assert events == ["cancelled"]
    assert not (tmp_path / "wall.glb").exists()


def test_settings_are_remembered(app, settings, tmp_path):
    first = gui.MainWindow(settings=settings)
    first.set_format("obj")
    first.beside_check.setChecked(True)
    first.close()

    second = gui.MainWindow(settings=settings)
    assert second.fmt == "obj"
    assert second.beside_check.isChecked()
    assert second.output_dir == tmp_path / "out"
    second.close()


def test_reading_state_until_first_progress(window, wall_ifc, tmp_path):
    window.add_paths([wall_ifc])
    window._on_file_started(0, tmp_path / "out" / "wall.glb")
    assert window.queue[0].progress == gui.READING
    assert window.status_text(0) == "IFC wird gelesen …"
    assert window.overall_progress.maximum() == 0  # busy indicator while reading

    window._on_file_progress(0, 0)  # convert() reports 0 % once the file is read
    assert window.status_text(0) == "Läuft … 0 %"
    assert window.overall_progress.maximum() == 100
    window._on_file_progress(0, 40)
    assert window.status_text(0) == "Läuft … 40 %"


def test_cancel_hint_while_reading(window, wall_ifc, tmp_path):
    window.add_paths([wall_ifc])
    window._worker = ConversionWorker([], "glb", tmp_path)  # pretend a batch is running
    try:
        window._on_file_started(0, tmp_path / "out" / "wall.glb")
        assert "wird gelesen" in window.status_label.text()
        window.cancel_conversion()
        # The child process is terminated right away, even while it reads the file.
        assert window.status_label.text() == "Wird abgebrochen …"
    finally:
        window._worker = None


def use_child_func(monkeypatch, func):
    """Let the worker's child processes run ``func`` (a top-level function) instead of convert()."""
    monkeypatch.setattr(gui, "convert_in_child", partial(process.convert_in_child, func=func))


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL is POSIX only")
def test_killed_conversion_fails_file_and_batch_continues(window, wall_ifc, tmp_path, monkeypatch):
    use_child_func(monkeypatch, child_helpers.killed_if_named_crash)
    crash = tmp_path / "crash.ifc"
    crash.write_text("x")
    window.set_format("glb")
    window.add_paths([crash, wall_ifc])
    window.start_conversion()
    assert wait_finished(window) is False

    out = tmp_path / "out"
    assert window.queue[0].status is Status.FAILED
    assert window.status_text(0) == f"Fehler: {process.MEMORY_MESSAGE}"
    assert f"✗ Fehler bei crash.ifc: {process.MEMORY_MESSAGE}" in window.log_view.toPlainText()
    assert not (out / "crash.glb").exists()  # partial output removed
    assert window.queue[1].status is Status.DONE
    assert (out / "wall.glb").stat().st_size > 0


def test_crashed_conversion_reports_exit_code(app, wall_ifc, tmp_path, monkeypatch):
    use_child_func(monkeypatch, child_helpers.exit_hard)
    worker = ConversionWorker([(0, wall_ifc)], "glb", tmp_path)
    failures = []
    worker.file_failed.connect(lambda row, message: failures.append((row, message)))
    worker.run()
    assert failures == [(0, "Umwandlung abgestürzt (Code 3)")]


def test_cancel_terminates_slow_child_quickly(window, wall_ifc, tmp_path, monkeypatch):
    use_child_func(monkeypatch, child_helpers.sleep_while_reading)
    window.set_format("glb")
    window.add_paths([wall_ifc])
    pid_file = tmp_path / "out" / "wall.pid"
    # Cancel once the child is busy "reading" the file (it would sleep for 2 minutes).
    timer = QTimer()
    timer.timeout.connect(lambda: pid_file.exists() and window.cancel_conversion())
    timer.start(50)

    started = time.monotonic()
    window.start_conversion()
    assert wait_finished(window, timeout_ms=30_000) is True
    timer.stop()
    assert time.monotonic() - started < 15
    assert window.queue[0].status is Status.CANCELLED
    assert not (tmp_path / "out" / "wall.glb").exists()  # partial output removed
    if sys.platform != "win32":
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)


def test_worker_reports_first_progress_only_after_reading(app, wall_ifc, tmp_path):
    worker = ConversionWorker([(0, wall_ifc)], "glb", tmp_path)
    events = []
    worker.file_started.connect(lambda row, target: events.append("started"))
    worker.file_progress.connect(lambda row, pct: events.append(pct))
    worker.run()
    assert events[0] == "started"
    assert events[1] == 0 and events[-1] == 100


def test_memory_warning_is_logged_and_shown_as_tooltip(window, wall_ifc, monkeypatch):
    monkeypatch.setattr("ifc_converter.interactive.memory_warning", lambda path: f"{path.name} ist riesig")
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)

    assert "⚠ wall.ifc ist riesig" in window.log_view.toPlainText()
    assert "wall.ifc ist riesig" in window.row_tooltip(0)
    assert "wall.ifc ist riesig" in window.table.item(0, 2).toolTip()
    assert not window.table.item(0, 0).icon().isNull()
    # The warning does not stop the conversion.
    assert window.queue[0].status is Status.DONE


def test_no_warning_no_icon(window, wall_ifc, monkeypatch):
    monkeypatch.setattr("ifc_converter.interactive.memory_warning", lambda path: None)
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert "⚠" not in window.log_view.toPlainText()
    assert window.table.item(0, 0).icon().isNull()


def test_geometry_option_defaults_to_brep_and_follows_format(window):
    assert window.fmt == "3dm"
    assert window.geometry == "brep"
    assert window.geometry_box.isEnabled()
    assert "Polyflächen" in window.geometry_buttons["brep"].text()
    assert "2–3×" in window.format_hint.text()

    window.set_format("glb")
    assert not window.geometry_box.isEnabled()
    assert window.format_hint.text().startswith("glTF binär")
    window.set_format("obj")
    assert not window.geometry_box.isEnabled()
    window.set_format("3dm")
    assert window.geometry_box.isEnabled()

    window.set_geometry("mesh")
    assert window.format_hint.text().startswith("Kleinste Dateien")


def test_geometry_option_is_remembered(app, settings):
    first = gui.MainWindow(settings=settings)
    first.set_geometry("mesh")
    first.close()
    second = gui.MainWindow(settings=settings)
    assert second.geometry == "mesh"
    second.close()


def test_invalid_saved_geometry_falls_back_to_brep(app, settings):
    settings.setValue("rhino_geometry", "nurbs")
    window = gui.MainWindow(settings=settings)
    assert window.geometry == "brep"
    window.close()


@pytest.fixture
def fake_convert(monkeypatch):
    """Replace convert() in the GUI module and record its arguments."""
    calls = []

    def fake(source, target, fmt, threads=None, progress=None, **kwargs):
        calls.append({"source": source, "fmt": fmt, **kwargs})
        progress(0)
        target.write_text("fake")
        progress(100)
        return ConversionResult(output=target, elements=3)

    monkeypatch.setattr("ifc_converter.gui.convert", fake)
    # The fake records its calls in this process, so convert in-process.
    monkeypatch.setattr(ConversionWorker, "use_subprocess", False)
    return calls


@pytest.mark.parametrize("mode, label", [("brep", "3DM (Polyflächen)"), ("mesh", "3DM (Netze)")])
def test_geometry_is_passed_to_convert_and_logged(window, wall_ifc, fake_convert, mode, label):
    window.set_format("3dm")
    window.set_geometry(mode)
    window.add_paths([wall_ifc])
    window.start_conversion()
    assert not window.geometry_box.isEnabled()  # locked while running
    wait_finished(window)

    assert fake_convert == [{"source": wall_ifc, "fmt": "3dm", "geometry": mode}]
    assert label in window.log_view.toPlainText()
    assert window.status_text(0) == "Fertig – 3 Bauteile"
    assert window.geometry_box.isEnabled()


def test_geometry_is_not_passed_for_other_formats(window, wall_ifc, fake_convert):
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert fake_convert == [{"source": wall_ifc, "fmt": "glb"}]
    assert "→ GLB," in window.log_view.toPlainText()


def test_geometry_options_match_converter():
    from ifc_converter.converter import GEOMETRIES

    assert set(gui.GEOMETRY_INFO) == set(GEOMETRIES)
    assert gui.DEFAULT_GEOMETRY in GEOMETRIES


@pytest.mark.parametrize("mode", ["brep", "mesh"])
def test_real_3dm_conversion_with_geometry(window, wall_ifc, tmp_path, mode):
    window.set_format("3dm")
    window.set_geometry(mode)
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert window.queue[0].status is Status.DONE, window.queue[0].error
    assert (tmp_path / "out" / "wall.3dm").stat().st_size > 0
