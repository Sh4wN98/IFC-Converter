import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEventLoop, QMimeData, QPointF, QSettings, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ifc_converter import gui  # noqa: E402
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
