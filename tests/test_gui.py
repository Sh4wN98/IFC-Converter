import os
import subprocess
import sys
import threading
import time
from functools import partial
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEventLoop, QMimeData, QPointF, QSettings, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import child_helpers  # noqa: E402
from ifc_converter import __version__, gui, process  # noqa: E402
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
    assert window.windowTitle() == f"IFC Converter {__version__}"
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
    assert "1,2–4,5× größer" in window.format_hint.text()
    assert "bei sehr großen Modellen besser „Netze“" in window.format_hint.text()

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

    assert fake_convert == [{"source": wall_ifc, "fmt": "3dm", "geometry": mode, "kernel": "accurate"}]
    assert label in window.log_view.toPlainText()
    assert window.status_text(0) == "Fertig – 3 Bauteile"
    assert window.geometry_box.isEnabled()


def test_geometry_is_not_passed_for_other_formats(window, wall_ifc, fake_convert):
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert fake_convert == [{"source": wall_ifc, "fmt": "glb", "kernel": "accurate"}]
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


def test_skipped_elements_are_shown_in_row_tooltip_and_log(window, wall_ifc, monkeypatch):
    use_child_func(monkeypatch, child_helpers.report_skipped)
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)

    assert window.queue[0].status is Status.DONE
    assert window.status_text(0) == "Fertig – 1 Bauteile (3 ohne Geometrie)"
    tooltip = window.table.item(0, 2).toolTip()
    assert "3 Bauteile ohne Geometrie" in tooltip
    assert "nicht unterstützte Geometrietypen" in tooltip
    assert "⚠ wall.ifc: 3 Bauteile ohne Geometrie. Diese Bauteile haben Geometrie" in window.log_view.toPlainText()


def test_no_skipped_elements_no_hint(window, wall_ifc, tmp_path):
    window.add_paths([wall_ifc])
    window._on_file_done(0, tmp_path / "wall.glb", 5, 0)
    assert window.status_text(0) == "Fertig – 5 Bauteile"
    assert "ohne Geometrie" not in window.table.item(0, 2).toolTip()
    assert "⚠" not in window.log_view.toPlainText()

    window._on_file_done(0, tmp_path / "wall.glb", 5, 1)
    assert window.status_text(0) == "Fertig – 5 Bauteile (1 ohne Geometrie)"
    assert "1 Bauteil ohne Geometrie" in window.table.item(0, 2).toolTip()


@pytest.mark.skipif(sys.platform == "win32", reason="SIGSEGV via os.kill is POSIX only")
def test_kernel_crash_is_retried_and_logged(window, wall_ifc, tmp_path, monkeypatch):
    monkeypatch.delenv("IFC_CONVERTER_KERNEL", raising=False)
    use_child_func(monkeypatch, child_helpers.segfault_unless_opencascade)
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)

    assert window.queue[0].status is Status.DONE, window.queue[0].error
    assert (tmp_path / "out" / "wall.glb").stat().st_size > 0
    log = window.log_view.toPlainText()
    assert f"⚠ {process.RETRY_MESSAGE}" in log
    assert log.index("⚠ Absturz") < log.index("✓ wall.ifc")


def test_retry_goes_back_to_reading_state(window, wall_ifc, tmp_path):
    window.add_paths([wall_ifc])
    window._worker = ConversionWorker([], "glb", tmp_path)  # pretend a batch is running
    try:
        window._on_file_started(0, tmp_path / "out" / "wall.glb")
        window._on_file_progress(0, 40)
        window._on_file_retrying(0)
        assert window.status_text(0) == "IFC wird gelesen …"
        assert window.overall_progress.maximum() == 0  # busy indicator again
        assert "OpenCASCADE" in window.status_label.text()
        window._on_file_progress(0, 0)
        assert window.status_text(0) == "Läuft … 0 %"
    finally:
        window._worker = None


@pytest.mark.skipif(sys.platform == "win32", reason="SIGSEGV via os.kill is POSIX only")
def test_crash_removes_glb_temp_files(window, wall_ifc, tmp_path, monkeypatch):
    use_child_func(monkeypatch, child_helpers.leave_glb_temp_files_and_segfault)
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert window.queue[0].status is Status.FAILED
    assert list((tmp_path / "out").iterdir()) == []


# ------------------------------------------------------------- app polish


from ifc_converter.dialogs import (  # noqa: E402
    AboutDialog,
    ErrorDialog,
    ErrorReporter,
    Preferences,
    SettingsDialog,
)


def test_preferences_round_trip_and_defaults(settings):
    prefs = Preferences.load(settings)
    assert prefs == Preferences(threads=0, kernel="accurate", low_priority=True, open_output=False)
    assert prefs.effective_threads == process.auto_threads()

    Preferences(threads=2, kernel="opencascade", low_priority=False, open_output=True).save(settings)
    loaded = Preferences.load(settings)
    assert loaded == Preferences(threads=2, kernel="opencascade", low_priority=False, open_output=True)
    assert loaded.effective_threads == 2


def test_invalid_preferences_fall_back(settings):
    settings.setValue("threads", "viele")
    settings.setValue("kernel_strategy", "cgal-magic")
    assert Preferences.load(settings) == Preferences()
    settings.setValue("threads", 100_000)  # from a machine with more cores
    assert Preferences.load(settings).threads == process.cpu_count()


def test_settings_of_earlier_versions(settings):
    # "hybrid" was the default and saved along with any setting: now the accurate strategy applies.
    settings.setValue("kernel", "hybrid")
    assert Preferences.load(settings).kernel == "accurate"
    settings.setValue("kernel", "opencascade")
    assert Preferences.load(settings).kernel == "opencascade"
    settings.setValue("kernel_strategy", "hybrid")
    assert Preferences.load(settings).kernel == "hybrid"


def test_settings_dialog_offers_the_kernel_strategies(app):
    dialog = SettingsDialog(Preferences())
    assert list(dialog.kernel_buttons) == ["accurate", "hybrid", "opencascade"]
    assert [b.text() for b in dialog.kernel_buttons.values()] == ["Genau (empfohlen)", "Schnell", "Nur OpenCASCADE"]
    assert dialog.kernel_buttons["accurate"].isChecked()
    dialog.deleteLater()


def test_settings_dialog_edits_preferences(app):
    threads = min(3, process.cpu_count())  # CI runners for private repositories have 2 cores
    dialog = SettingsDialog(Preferences(threads=threads, kernel="opencascade", low_priority=False, open_output=True))
    assert dialog.preferences() == Preferences(threads=threads, kernel="opencascade", low_priority=False, open_output=True)
    assert dialog.threads_spin.maximum() == process.cpu_count()
    assert dialog.threads_spin.specialValueText() == f"Automatisch ({process.auto_threads()})"

    dialog.threads_spin.setValue(0)
    dialog.kernel_buttons["hybrid"].setChecked(True)
    assert dialog.preferences().kernel == "hybrid" and dialog.preferences().threads == 0

    dialog.buttons.button(dialog.buttons.StandardButton.RestoreDefaults).click()
    assert dialog.preferences() == Preferences()
    dialog.deleteLater()


def test_settings_from_the_dialog_are_saved_and_used(window, settings, monkeypatch):
    chosen = Preferences(threads=2, kernel="opencascade", low_priority=False, open_output=False)
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: SettingsDialog.DialogCode.Accepted)
    monkeypatch.setattr(SettingsDialog, "preferences", lambda self: chosen)
    window.show_settings()
    assert window.preferences == chosen
    assert Preferences.load(settings) == chosen


@pytest.fixture
def child_calls(monkeypatch):
    """Replace convert_in_child() in the GUI module and record its arguments."""
    calls = []

    def fake(source, target, fmt, threads, progress, cancelled, on_retry=None, low_priority=True, status=None,
             **options):
        assert callable(status)  # the phases reach the window
        calls.append({"threads": threads, "low_priority": low_priority, **options})
        progress(0)
        status("write", "Rhino-Datei wird geschrieben …")
        target.write_text("fake")
        progress(100)
        return ConversionResult(output=target, elements=1)

    monkeypatch.setattr(gui, "convert_in_child", fake)
    return calls


def test_preferences_reach_the_conversion(window, wall_ifc, child_calls):
    window.preferences = Preferences(threads=3, kernel="opencascade", low_priority=False)
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert child_calls == [{"threads": 3, "low_priority": False, "kernel": "opencascade"}]
    assert "Geometriekern Nur OpenCASCADE" in window.log_view.toPlainText()


def test_automatic_threads_and_low_priority_by_default(window, wall_ifc, child_calls):
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert child_calls == [{"threads": process.auto_threads(), "low_priority": True, "kernel": "accurate"}]
    assert "Geometriekern" not in window.log_view.toPlainText()


def test_keyboard_shortcuts(window):
    def keys(action):
        return [s.toString() for s in action.shortcuts()]

    assert keys(window.add_files_action) == ["Ctrl+O"]
    assert keys(window.convert_action) == ["Ctrl+Return", "Ctrl+Enter"]
    assert "Del" in keys(window.remove_action)
    assert keys(window.settings_action) == ["Ctrl+,"]
    # Every action lives on the window, so its shortcut works without opening a menu.
    for action in (window.add_files_action, window.convert_action, window.remove_action):
        assert action in window.actions()


def test_convert_and_remove_actions(window, wall_ifc, tmp_path, child_calls):
    other = tmp_path / "zweite.ifc"
    other.write_text("x")
    window.add_paths([wall_ifc, other])
    window.table.selectRow(1)
    assert window.remove_action.isEnabled()
    window.remove_action.trigger()
    assert [item.path for item in window.queue.items] == [wall_ifc]

    window.set_format("glb")
    window.convert_action.trigger()
    assert not window.convert_action.isEnabled() and not window.add_files_action.isEnabled()
    wait_finished(window)
    assert window.queue[0].status is Status.DONE
    assert window.convert_action.isEnabled()


def test_help_menu_has_log_output_and_about(window):
    menus = {action.text(): action.menu() for action in window.menuBar().actions()}
    assert list(menus) == ["&Datei", "&Bearbeiten", "E&xtras", "&Hilfe"]
    help_items = [action.text() for action in menus["&Hilfe"].actions() if not action.isSeparator()]
    assert help_items == ["Ausgabeordner öffnen", "Logdatei öffnen", "Über IFC Converter"]


def test_finished_notification_in_background(window, wall_ifc, child_calls, monkeypatch):
    alerts = []
    monkeypatch.setattr(gui.QApplication, "alert", lambda widget, msec=0: alerts.append(widget))
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    titles = []
    window.windowTitleChanged.connect(titles.append)
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)

    assert any(title.startswith("100 % – IFC Converter") for title in titles)  # progress in the taskbar
    assert window.windowTitle() == f"✓ Fertig – IFC Converter {__version__}"
    assert alerts == [window]
    assert window.status_label.text().startswith("✓ Fertig nach")
    assert window.status_label.property("state") == "done"

    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.changeEvent(gui.QEvent(gui.QEvent.Type.ActivationChange))
    assert window.windowTitle() == f"IFC Converter {__version__}"


def test_failures_are_shown_in_the_status(window, wall_ifc, monkeypatch):
    use_child_func(monkeypatch, child_helpers.raise_error)
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert window.status_label.property("state") == "failed"
    assert "1 mit Fehler" in window.status_label.text()


def test_output_folder_opens_after_batch_if_wanted(window, wall_ifc, tmp_path, child_calls, monkeypatch):
    opened = []
    monkeypatch.setattr(gui.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()))
    window.set_format("glb")
    window.add_paths([wall_ifc])
    window.start_conversion()
    wait_finished(window)
    assert opened == []

    window.preferences = Preferences(open_output=True)
    window.start_conversion()
    wait_finished(window)
    assert [Path(p) for p in opened] == [tmp_path / "out"]


def test_window_state_and_table_columns_are_remembered(app, settings):
    first = gui.MainWindow(settings=settings)
    first.table.setColumnWidth(2, 345)
    first.close()
    second = gui.MainWindow(settings=settings)
    assert second.table.columnWidth(2) == 345
    second.close()


def test_receive_paths_from_another_start(window, wall_ifc):
    window.receive_paths([str(wall_ifc)])
    assert [item.path for item in window.queue.items] == [wall_ifc]
    window.receive_paths([])  # only brings the window to the front
    assert len(window.queue) == 1


def _unique_name():
    return f"ifc-converter-test-{os.getpid()}-{time.monotonic_ns()}"


def test_second_start_hands_its_files_to_the_running_app(app, wall_ifc):
    name = _unique_name()
    server = gui.InstanceServer(name)
    assert server.listen()
    received = []
    server.paths_received.connect(received.append)
    # The second start is a process of its own with its own QApplication, as when a file is dropped
    # onto the exe (Windows' named pipes need its event dispatcher); this one runs the event loop.
    code = (
        "import sys; from PySide6.QtWidgets import QApplication; app = QApplication([]); "
        "from ifc_converter import gui; sys.exit(0 if gui.send_to_running_instance(sys.argv[1:2], sys.argv[2]) else 3)"
    )
    sender = subprocess.Popen(
        [sys.executable, "-c", code, str(wall_ifc), name], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    deadline = time.monotonic() + 30
    while (not received or sender.poll() is None) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert sender.wait(5) == 0
    assert received == [[str(wall_ifc)]]
    server.server.close()


def test_first_start_finds_no_running_app(app):
    assert gui.send_to_running_instance(["x.ifc"], _unique_name(), timeout_ms=200) is False


def test_settings_are_taken_over_from_the_old_app_name(app, tmp_path):
    legacy = QSettings(str(tmp_path / "old.ini"), QSettings.Format.IniFormat)
    legacy.setValue("format", "obj")
    legacy.setValue("output_dir", str(tmp_path))
    legacy.sync()

    path = tmp_path / "new" / "settings.ini"
    settings = gui.open_settings(path, legacy)
    assert settings.value("format") == "obj"
    assert path.is_file()
    assert QSettings(str(path), QSettings.Format.IniFormat).value("output_dir") == str(tmp_path)

    legacy.setValue("format", "glb")  # only taken over once
    assert gui.open_settings(path, legacy).value("format") == "obj"


def test_about_dialog_shows_versions_and_licenses(app):
    dialog = AboutDialog()
    texts = "\n".join(label.text() for label in dialog.findChildren(gui.QLabel))
    assert f"Version {__version__}" in texts
    for expected in ("IfcOpenShell", "LGPL-3.0", "rhino3dm", "MIT", "github.com/Sh4wN98/IFC-Converter"):
        assert expected in texts
    dialog.copy_button.click()
    assert f"IFC Converter: {__version__}" in QApplication.clipboard().text()
    dialog.deleteLater()


def test_error_dialog_copies_details(app):
    dialog = ErrorDialog("ValueError: kaputt", "Traceback …\nValueError: kaputt")
    dialog.copy_button.click()
    assert QApplication.clipboard().text() == "Traceback …\nValueError: kaputt"
    assert dialog.copy_button.text() == "Kopiert ✓"
    dialog.deleteLater()


def test_error_reporter_shows_one_dialog_at_a_time(app):
    reporter = ErrorReporter()
    threading.Thread(target=lambda: reporter.report("A", "a")).start()
    reporter.report("B", "b")
    deadline = time.monotonic() + 5
    while reporter.dialog is None and time.monotonic() < deadline:
        app.processEvents()
    app.processEvents()
    first = reporter.dialog
    assert first is not None and first.details in ("a", "b")
    assert len([w for w in QApplication.topLevelWidgets() if isinstance(w, ErrorDialog) and w.isVisible()]) <= 1
    first.accept()
    app.processEvents()
    assert reporter.dialog is None
    reporter.report("C", "c")
    app.processEvents()
    assert reporter.dialog is not None and reporter.dialog.details == "c"
    reporter.dialog.accept()


def test_error_in_a_slot_shows_the_error_dialog(app, monkeypatch):
    from ifc_converter.app import install_exception_hooks

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    reporter = ErrorReporter()
    install_exception_hooks(reporter.report)
    QTimer.singleShot(0, lambda: {}["fehlt"])
    deadline = time.monotonic() + 5
    while reporter.dialog is None and time.monotonic() < deadline:
        app.processEvents()
    assert reporter.dialog is not None
    assert "KeyError: 'fehlt'" in reporter.dialog.details
    reporter.dialog.accept()
    app.processEvents()


def test_long_final_phases_are_shown_in_the_row_and_status_line(window, wall_ifc):
    window.add_paths([wall_ifc])
    item = window.queue[0]
    window._worker = gui.ConversionWorker([], "3dm", None)  # a running batch, so the status line follows
    window._on_file_started(0, wall_ifc.with_suffix(".3dm"))
    window._on_file_progress(0, 90)
    window._on_file_status(0, "geometry", "Geometrie wird berechnet (16 Threads) …")
    assert item.status_text == "Läuft … 90 %"  # the percentage tells enough there
    window._on_file_status(0, "write", "Rhino-Datei wird geschrieben (600 Objekte): 1,2 GB geschrieben …")
    assert item.status_text == "Läuft … 90 % – Rhino-Datei wird geschrieben (600 Objekte): 1,2 GB geschrieben …"
    assert "1,2 GB geschrieben" in window.status_label.text()
    assert "Rhino-Datei wird geschrieben" in window.log_view.toPlainText()
    window._worker = None
