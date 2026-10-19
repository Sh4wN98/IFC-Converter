"""Desktop GUI: drop IFC files into a window and convert them in the background."""

from __future__ import annotations

import getpass
import json
import logging
import multiprocessing
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRect, QRectF, QSettings, QSize, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ifc_converter import __version__
from ifc_converter import app as app_info
from ifc_converter.app import APP_NAME, enable_crash_log, hold_app_mutex, install_exception_hooks, setup_logging
from ifc_converter.converter import DEFAULT_KERNEL, FORMATS, ConversionResult, convert
from ifc_converter.dialogs import (
    KERNEL_INFO,
    AboutDialog,
    ElidedLabel,
    ErrorReporter,
    Preferences,
    SettingsDialog,
    SkippedDialog,
    app_icon,
    muted,
    open_log,
    save_anonymized_log,
)
from ifc_converter.interactive import (
    SKIPPED_HINT,
    check_memory,
    collect_ifc_files,
    crashed_warning,
    desktop_dir,
    duration_text,
    error_message,
    failure_hint,
    is_internal_error,
    number_text,
    output_files,
    resource_text,
    rhino_workers,
    skipped_count,
    skipped_warning,
    unique_path,
)
from ifc_converter.preview_pane import PreviewPane
from ifc_converter.process import RETRY_MESSAGE, Cancelled, convert_in_child, remove_stale_temp_files

# The app's name before it was renamed; its settings are taken over once (see open_settings()).
LEGACY_NAME = "IFC File Converter"
DEFAULT_FORMAT = "3dm"
DEFAULT_GEOMETRY = "brep"
SIDE_WIDTH = 320  # settings column on the right

# Format -> (label, hint), in the order shown in the window.
FORMAT_INFO = {
    "3dm": ("3DM (Rhino)", "Rhino-Datei (.3dm) – direkt in Rhino öffnen und weiterbearbeiten."),
    "glb": ("GLB", "glTF binär (.glb) – kompakt, für Web-Viewer, Blender, Three.js und Game-Engines."),
    "obj": ("OBJ", "Wavefront OBJ (.obj + .mtl) – lässt sich in fast jedem 3D-Programm öffnen."),
    "dae": (
        "DAE (Collada)",
        "COLLADA 1.4 (.dae) – Dreiecksnetze mit Farben, für SketchUp, Blender, Unity und ArchiCAD. "
        "Textdatei, etwa doppelt so groß wie .glb.",
    ),
}

# Rhino geometry mode (convert(..., geometry=...), only used for 3DM) -> (label, hint).
GEOMETRY_INFO = {
    "brep": (
        "Polyflächen (empfohlen)",
        "Wände, Decken, Fenster … als geschlossene Polyflächen mit echten Öffnungen. Sehr detaillierte "
        "Objekte (Möbel, Sanitär, Leuchten) bleiben Netze. Datei je nach Modell 1,2–4,5× größer – "
        "bei sehr großen Modellen besser „Netze“ wählen.",
    ),
    "mesh": ("Netze (Meshes)", "Kleinste Dateien, schnellste Konvertierung. Runde Flächen glatt schattiert, Kanten scharf."),
}

DONE_COLOR = QColor("#2e9d57")
ERROR_COLOR = QColor("#d64545")
RUNNING_COLOR = QColor("#2f80ed")
WAITING_COLOR = QColor("#8a949e")
PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 1
# Between a number and its unit ("2,2 MB", "40 %"): a narrow space that never breaks the line.
NNBSP = "\u202f"
# QueueItem.progress while the IFC file is still being read: convert() reports progress(0) only afterwards.
READING = -1

log = logging.getLogger("ifc_converter.gui")  # also when run as __main__


# --------------------------------------------------------------------------- model


class Status(Enum):
    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueueItem:
    path: Path
    size: int
    status: Status = Status.WAITING
    progress: int = 0
    elements: int = 0
    skipped: int = 0  # elements whose geometry could not be converted
    output: Path | None = None
    error: str = ""
    warning: str = ""  # RAM warning for large files, shown as tooltip
    detail: str = ""  # what the conversion is doing in a long final phase (writing, copying)
    phase: str = ""  # the conversion's current phase (see process.convert_in_child)
    queued: bool = False  # added during a run: converted right after it
    internal_error: bool = False  # the failure is a fault of the program (see interactive.is_internal_error)
    crashed: list[str] = field(default_factory=list)  # left out after kernel crashes (labels)
    no_geometry: list[str] = field(default_factory=list)  # without geometry (labels, as far as known)

    @property
    def has_details(self) -> bool:
        """Whether there are skipped elements to list (see SkippedDialog)."""
        return self.status is Status.DONE and bool(self.crashed or self.no_geometry or self.skipped)

    @property
    def status_text(self) -> str:
        if self.status is Status.RUNNING:
            if self.progress == READING:
                return "IFC wird gelesen …"
            if self.detail:
                return f"Wird konvertiert … {self.progress}{NNBSP}% – {self.detail}"
            return f"Wird konvertiert … {self.progress}{NNBSP}%"
        if self.status is Status.DONE:
            skipped = f" ({number_text(self.skipped)} ohne Geometrie)" if self.skipped > 0 else ""
            return f"Fertig – {count_text(self.elements, 'Bauteil', 'Bauteile')}{skipped}"
        if self.status is Status.FAILED:
            return f"Fehler: {self.error}"
        if self.status is Status.CANCELLED:
            return "Abgebrochen"
        return "Vorgemerkt – startet danach" if self.queued else "Wartend"


@dataclass
class AddResult:
    added: list[Path]
    rejected: list[Path]
    duplicates: list[Path]


def format_size(size: int) -> str:
    """Human readable file size with a German decimal comma, e.g. "2,2 MB"."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            break
        value /= 1024
    text = f"{value:.0f}" if unit == "B" else f"{value:.1f}"
    return f"{text.replace('.', ',')}{NNBSP}{unit}"


def count_text(count: int, singular: str, plural: str) -> str:
    """A count with its noun, e.g. "1 Datei", "3 Dateien", "117.137 Bauteile"."""
    return f"{number_text(count)} {singular if count == 1 else plural}"


def files_text(count: int) -> str:
    return count_text(count, "Datei", "Dateien")


def target_path(source: Path, fmt: str, out_dir: Path | None) -> Path:
    """Where `source` is written to: `out_dir` (or next to the IFC file), never overwriting."""
    return unique_path((out_dir or source.parent) / f"{source.stem}.{fmt}")


class FileQueue:
    """The list of IFC files in the window, independent of any widgets."""

    def __init__(self) -> None:
        self.items: list[QueueItem] = []

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, row: int) -> QueueItem:
        return self.items[row]

    @staticmethod
    def _key(path: Path) -> str:
        return os.path.normcase(str(path.resolve()))

    def add(self, paths: list[str | Path]) -> AddResult:
        files, rejected = collect_ifc_files([Path(p) for p in paths])
        known = {self._key(item.path) for item in self.items}
        added, duplicates = [], []
        for path in files:
            key = self._key(path)
            if key in known:
                duplicates.append(path)
                continue
            known.add(key)
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            self.items.append(QueueItem(path, size))
            added.append(path)
        return AddResult(added, rejected, duplicates)

    def remove(self, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self.items):
                del self.items[row]

    def clear(self) -> None:
        self.items.clear()

    def prepare_run(self) -> list[int]:
        """Rows to convert next: everything not finished yet, or all rows if everything is done."""
        rows = [i for i, item in enumerate(self.items) if item.status is not Status.DONE]
        if not rows:
            rows = list(range(len(self.items)))
        for row in rows:
            item = self.items[row]
            item.status, item.progress, item.error, item.warning = Status.WAITING, 0, "", ""
            item.queued, item.crashed, item.no_geometry = False, [], []
        return rows


# -------------------------------------------------------------------------- worker


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


class ConversionWorker(QObject):
    """Converts a batch of files one after another; meant to live in a QThread.

    Each file is converted in a child process (see ifc_converter.process), so running out of memory or
    a crash in the geometry kernel fails that file instead of closing the window, and a cancel takes
    effect immediately. With ``use_subprocess`` False it calls convert() directly (used by tests).
    """

    use_subprocess = True

    file_started = Signal(int, object)  # row, target path
    file_warning = Signal(int, str)  # row, RAM warning
    file_progress = Signal(int, int)  # row, percent
    file_retrying = Signal(int, str)  # row, message; converting again after a crash or hang
    file_status = Signal(int, str, str)  # row, phase, description (see process.convert_in_child)
    file_done = Signal(int, object)  # row, ConversionResult
    file_failed = Signal(int, str, bool)  # row, message, whether it is an internal error
    file_cancelled = Signal(int)
    finished = Signal(bool)  # True if cancelled

    def __init__(
        self,
        jobs: list[tuple[int, Path]],
        fmt: str,
        out_dir: Path | None,
        threads: int | None = None,
        geometry: str = DEFAULT_GEOMETRY,
        kernel: str | None = None,
        low_priority: bool = True,
        blocks: bool = False,
    ):
        super().__init__()
        self.jobs = jobs
        self.fmt = fmt
        self.geometry = geometry
        self.out_dir = out_dir
        self.threads = threads
        self.kernel = kernel
        self.low_priority = low_priority
        self.blocks = blocks
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @Slot()
    def run(self) -> None:
        for row, source in self.jobs:
            if self.cancelled:
                self.file_cancelled.emit(row)
                continue
            self._convert_one(row, source)
        self.finished.emit(self.cancelled)

    def _convert_one(self, row: int, source: Path) -> None:
        target = target_path(source, self.fmt, self.out_dir)
        # Side files (.mtl, GLB temp files) are only cleaned up after a failure if we created them.
        side_files = [p for p in output_files(target, self.fmt)[1:] if not p.exists()]
        self.file_started.emit(row, target)
        # Checked here rather than in the GUI thread; for a large file it is the only hint for minutes.
        warning = check_memory(source)
        if warning:
            self.file_warning.emit(row, warning)
        last = READING

        def progress(percent: int) -> None:
            nonlocal last
            if self._cancel.is_set():
                raise Cancelled
            percent = max(0, min(100, int(percent)))
            if percent != last:
                last = percent
                self.file_progress.emit(row, percent)

        try:
            # The geometry mode only exists for Rhino, so GLB/OBJ calls leave it out.
            options = {"geometry": self.geometry} if self.fmt == "3dm" else {}
            if self.fmt == "3dm" and self.blocks:
                options["blocks"] = True
            if self.kernel:
                options["kernel"] = self.kernel
            if self.use_subprocess:

                def retrying(message: str) -> None:
                    nonlocal last
                    last = READING
                    self.file_retrying.emit(row, message)

                result = convert_in_child(
                    source, target, self.fmt, self.threads, progress, self._cancel.is_set,
                    on_retry=retrying, low_priority=self.low_priority,
                    status=lambda phase, text: self.file_status.emit(row, phase, text), **options,
                )
            else:
                result = convert(source, target, self.fmt, self.threads, progress, **options)
        except Cancelled:
            for path in [target, *side_files]:
                _discard(path)
            self.file_cancelled.emit(row)
        except Exception as exc:  # one broken file must not stop the batch
            if not self.use_subprocess:  # convert_in_child() logs its failures itself
                log.exception("Fehler bei %s", source)
            for path in [target, *side_files]:
                _discard(path)
            self.file_failed.emit(row, error_message(exc), is_internal_error(exc))
        else:
            self.file_done.emit(row, result)


# ------------------------------------------------------------------------- widgets


_status_icons: dict[Status, QIcon] = {}


def status_icon(status: Status) -> QIcon:
    """A small round glyph for the status column: tick (done), cross (failed), dot (running), ring (waiting)."""
    icon = _status_icons.get(status)
    if icon is not None:
        return icon
    icon = QIcon()
    for size in (16, 32, 48):  # the icon stays crisp at 150 % and 200 % scaling
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        unit = size / 16
        circle = QRectF(2 * unit, 2 * unit, 12 * unit, 12 * unit)
        if status is Status.WAITING:
            painter.setPen(QPen(WAITING_COLOR, 1.5 * unit))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(circle)
        else:
            colour = {Status.DONE: DONE_COLOR, Status.FAILED: ERROR_COLOR, Status.RUNNING: RUNNING_COLOR}.get(
                status, WAITING_COLOR
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawEllipse(circle)
            pen = QPen(QColor("white"), 1.8 * unit)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            if status is Status.DONE:
                painter.drawPolyline([QRectF(5 * unit, 8 * unit, 0, 0).topLeft(),
                                      QRectF(7.2 * unit, 10.4 * unit, 0, 0).topLeft(),
                                      QRectF(11.2 * unit, 5.8 * unit, 0, 0).topLeft()])
            elif status is Status.FAILED:
                painter.drawLine(QRectF(5.6 * unit, 5.6 * unit, 0, 0).topLeft(), QRectF(10.4 * unit, 10.4 * unit, 0, 0).topLeft())
                painter.drawLine(QRectF(10.4 * unit, 5.6 * unit, 0, 0).topLeft(), QRectF(5.6 * unit, 10.4 * unit, 0, 0).topLeft())
            elif status is Status.CANCELLED:
                painter.drawLine(QRectF(5.2 * unit, 8 * unit, 0, 0).topLeft(), QRectF(10.8 * unit, 8 * unit, 0, 0).topLeft())
            else:  # running: a white dot in the middle, the progress fill shows the rest
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("white"))
                painter.drawEllipse(QRectF(6 * unit, 6 * unit, 4 * unit, 4 * unit))
        painter.end()
        icon.addPixmap(pixmap)
    _status_icons[status] = icon
    return icon


class StatusDelegate(QStyledItemDelegate):
    """Paints a slim progress fill behind the status text of running files."""

    def paint(self, painter, option, index):
        percent = index.data(PROGRESS_ROLE)
        if percent is not None and percent > 0:
            rect = option.rect.adjusted(2, 3, -2, -3)
            color = QColor(option.palette.color(QPalette.ColorRole.Highlight))
            color.setAlpha(60)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRect(rect.x(), rect.y(), int(rect.width() * percent / 100), rect.height()), 4, 4)
            painter.restore()
        super().paint(painter, option, index)


class DropZone(QFrame):
    """The big dashed area; the window itself handles the drops."""

    browse_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setProperty("active", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Klicken öffnet den Dateidialog (Strg+O). Ordner werden nach .ifc-Dateien durchsucht.")

        self.icon = QLabel("⬇")
        self.icon.setObjectName("DropIcon")
        self.title = QLabel("IFC-Dateien oder Ordner hierher ziehen")
        self.title.setObjectName("DropTitle")
        self.hint = muted(QLabel("Ordner werden nach .ifc- und .ifczip-Dateien durchsucht – auch mehrere auf einmal"))
        self.hint.setObjectName("Hint")
        self.add_button = QPushButton("Dateien hinzufügen…")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self.browse_requested)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(6)
        for widget in (self.icon, self.title, self.hint):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            widget.setWordWrap(True)  # a narrow window wraps the text instead of growing
            self._layout.addWidget(widget)
        self._layout.addWidget(self.add_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self.set_compact(False)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_compact(self, compact: bool) -> None:
        """Smaller once the list has files, so the list and the preview get the room."""
        if self.property("compact") == compact:
            return
        self.setProperty("compact", compact)
        self.icon.setVisible(not compact)
        self.hint.setVisible(not compact)
        self._layout.setContentsMargins(16, 10 if compact else 16, 16, 10 if compact else 16)
        self.setMinimumHeight(0 if compact else 124)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()
        super().mouseReleaseEvent(event)


STYLESHEET = """
QLabel#AppTitle { font-size: 20px; font-weight: 600; }
QLabel#Status[state="done"] { color: #2e9d57; font-weight: 600; }
QLabel#Status[state="failed"] { color: #d64545; font-weight: 600; }
QLabel#DropIcon { font-size: 26px; color: palette(highlight); }
QLabel#DropTitle { font-size: 15px; font-weight: 600; }
QLabel#PreviewTitle, QLabel#SectionTitle { font-weight: 600; }
#DropZone {
    border: 2px dashed palette(mid);
    border-radius: 12px;
    background: palette(base);
}
#DropZone:hover, #DropZone[active="true"] {
    border-color: palette(highlight);
    background: palette(alternate-base);
}
#Side, #SideViewport, #SideContent { background: transparent; }
QGroupBox {
    font-weight: 600;
    border: 1px solid palette(mid);
    border-radius: 8px;
    margin-top: 10px;
    padding: 12px 10px 10px 10px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QGroupBox QRadioButton, QGroupBox QCheckBox, QGroupBox QLabel, QGroupBox QLineEdit { font-weight: normal; }
QTableWidget { border: 1px solid palette(mid); border-radius: 8px; }
QHeaderView::section { padding: 4px 6px; border: none; border-bottom: 1px solid palette(mid); background: palette(window); }
QPlainTextEdit#Log { border: 1px solid palette(mid); border-radius: 8px; font-family: monospace; }
QPushButton { padding: 5px 12px; }
QPushButton#Primary {
    background: palette(highlight);
    color: palette(highlighted-text);
    border: none;
    border-radius: 6px;
    padding: 8px 22px;
    font-weight: 600;
}
QPushButton#Primary:hover { background: %HOVER%; }
QPushButton#Primary:disabled { background: palette(mid); color: palette(window); }
QPushButton[highlight="true"] {
    border: 1px solid palette(highlight);
    border-radius: 6px;
    color: palette(highlight);
    background: palette(base);
    font-weight: 600;
}
QPushButton[highlight="true"]:hover { background: palette(alternate-base); }
QToolButton#LogToggle { border: none; padding: 2px 6px; color: palette(window-text); }
QToolButton#LogToggle:hover { background: palette(alternate-base); border-radius: 4px; }
QProgressBar { border: 1px solid palette(mid); border-radius: 6px; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: palette(highlight); border-radius: 5px; }
QSplitter::handle:vertical { height: 8px; }
QSplitter::handle:horizontal { width: 8px; }
"""


class HintLabel(QLabel):
    """Word-wrapped label that reserves the height of the longest of its possible texts.

    Layouts don't account for the height of word-wrapped labels reliably (the hint got clipped), and a
    constant height also keeps the box from jumping when the text changes.
    """

    def __init__(self, texts: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self._texts = texts
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = QRect(0, 0, max(1, self.width()), 10_000)
        flags = Qt.TextFlag.TextWordWrap
        height = max(self.fontMetrics().boundingRect(rect, flags, text).height() for text in self._texts) + 2
        if height != self.minimumHeight():
            self.setMinimumHeight(height)


class MainWindow(QMainWindow):
    conversion_finished = Signal(bool)  # True if cancelled; mainly for tests

    COLUMNS = ("Datei", "Größe", "Status")

    def __init__(self, settings: QSettings | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings or open_settings()
        self.preferences = Preferences.load(self.settings)
        app_info.set_log_anonymized(self.preferences.anonymize_log)
        self.queue = FileQueue()
        self._thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._run_rows: list[int] = []
        self._run_done = 0
        self._run_failed = 0
        self._pending_rows: list[int] = []  # added during the run, converted after it
        # Since "Konvertieren" was clicked, over the run and those of files added meanwhile.
        self._chain_started_at = time.monotonic()
        self._chain_done = self._chain_failed = 0
        self._last_output_dir: Path | None = None
        self._started_at = time.monotonic()
        self._warning_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)

        self.setWindowIcon(app_icon())
        self._set_title()
        self.setMinimumSize(860, 600)
        available = self.screen().availableGeometry()
        self.resize(min(1100, available.width() - 40), min(860, available.height() - 40))
        self.setAcceptDrops(True)
        # QSS cannot darken a palette colour, so the hover shade of the primary button is computed here.
        hover = self.palette().color(QPalette.ColorRole.Highlight).darker(118).name()
        self.setStyleSheet(STYLESHEET.replace("%HOVER%", hover))

        self._build_ui()
        self._build_menus()
        self._load_settings()
        # Never allow the window to get smaller than its content needs.
        self.setMinimumSize(self.minimumSize().expandedTo(self.centralWidget().minimumSizeHint()))
        self._update_actions()

    # ---------------------------------------------------------------- layout

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # Header: icon, title and subtitle.
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(40, 40))
        logo.setFixedSize(40, 40)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        subtitle = muted(QLabel("IFC-Gebäudemodelle in 3D-Formate konvertieren"))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(logo)
        header.addLayout(titles, stretch=1)
        root.addLayout(header)
        root.addSpacing(4)

        # Upper part (files, preview, settings) and the log share a vertical splitter: the user decides
        # how much room the log gets; "Protokoll" below folds it away.
        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(8)
        body = QHBoxLayout()
        body.setSpacing(16)
        upper_layout.addLayout(body, stretch=1)

        # Left: drop zone, file table, list buttons, preview.
        left = QVBoxLayout()
        left.setSpacing(8)
        body.addLayout(left, stretch=1)

        self.drop_zone = DropZone()
        self.drop_zone.browse_requested.connect(self.browse_files)
        left.addWidget(self.drop_zone)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setIconSize(QSize(16, 16))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.verticalHeader().setMinimumSectionSize(24)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header_view.setHighlightSections(False)
        header_view.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setColumnWidth(2, 260)
        self.table.setItemDelegateForColumn(2, StatusDelegate(self.table))
        self.table.setMinimumHeight(2 * 28 + 30)  # header and two rows
        self.table.setToolTip("Doppelklick auf eine fertige Datei öffnet ihren Ausgabeordner; Rechtsklick für mehr.")
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.cellDoubleClicked.connect(self._open_row_folder)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_row_menu)
        files = QWidget()
        files_layout = QVBoxLayout(files)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(8)
        files_layout.addWidget(self.table, stretch=1)

        list_buttons = QHBoxLayout()
        list_buttons.setSpacing(8)
        self.remove_button = QPushButton("Entfernen")
        self.remove_button.setToolTip("Markierte Dateien aus der Liste nehmen (Entf). Die Dateien selbst bleiben unberührt.")
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton("Liste leeren")
        self.clear_button.setToolTip("Alle Dateien aus der Liste nehmen.")
        self.clear_button.clicked.connect(self.clear_list)
        self.details_button = QPushButton("Übersprungene Bauteile…")
        self.details_button.setToolTip(
            "Listet die Bauteile der gewählten Datei, die nicht konvertiert wurden, mit Klasse, GlobalId und Name "
            "(auch per Rechtsklick auf die Zeile)."
        )
        self.details_button.clicked.connect(lambda: self.show_details())
        self.count_label = muted(ElidedLabel())
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        list_buttons.addWidget(self.remove_button)
        list_buttons.addWidget(self.clear_button)
        list_buttons.addWidget(self.details_button)
        list_buttons.addStretch()
        list_buttons.addWidget(self.count_label)
        files_layout.addLayout(list_buttons)

        # Below the list: a 3D preview of the selected file (Ansicht → Vorschau).
        self.preview = PreviewPane(busy=lambda: self.is_running)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(files)
        self.splitter.addWidget(self.preview)
        # The preview gets twice the room of the list (a few files need little); the user can drag it.
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([200, 400])
        self.splitter.handle(1).setToolTip("Ziehen: Liste und Vorschau aufteilen")
        left.addWidget(self.splitter, stretch=1)
        self.table.itemSelectionChanged.connect(self._update_preview)

        # Right: format and output settings.
        right = QVBoxLayout()
        right.setSpacing(12)
        side = QWidget()
        side.setObjectName("SideContent")
        side.setLayout(right)
        right.setContentsMargins(0, 0, 0, 0)
        # Scrollable, so the window still fits small screens (e.g. laptops with 150 % scaling).
        side_scroll = QScrollArea()
        side_scroll.setObjectName("Side")
        side_scroll.viewport().setObjectName("SideViewport")
        side_scroll.setWidget(side)
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll.setFixedWidth(SIDE_WIDTH)
        body.addWidget(side_scroll)

        format_box = QGroupBox("Zielformat")
        format_layout = QVBoxLayout(format_box)
        format_layout.setSpacing(6)
        self.format_group = QButtonGroup(self)
        self.format_buttons: dict[str, QRadioButton] = {}
        for fmt, (label, hint) in FORMAT_INFO.items():
            if fmt not in FORMATS:
                continue
            button = QRadioButton(label)
            button.setToolTip(hint)
            self.format_group.addButton(button)
            self.format_buttons[fmt] = button
            format_layout.addWidget(button)
            button.toggled.connect(self._format_changed)
            if fmt == "3dm":
                format_layout.addWidget(self._build_geometry_options())
        self.format_hint = muted(HintLabel([hint for _label, hint in (*FORMAT_INFO.values(), *GEOMETRY_INFO.values())]))
        self.format_hint.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        format_layout.addSpacing(2)
        format_layout.addWidget(self.format_hint)
        right.addWidget(format_box)

        output_box = QGroupBox("Speicherort")
        output_layout = QVBoxLayout(output_box)
        output_layout.setSpacing(6)
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_button = QPushButton("Ändern…")
        self.output_button.clicked.connect(self.choose_output_dir)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.output_edit, stretch=1)
        row.addWidget(self.output_button)
        output_layout.addLayout(row)
        self.beside_check = QCheckBox("Neben der IFC-Datei speichern")
        self.beside_check.toggled.connect(self._beside_changed)
        output_layout.addWidget(self.beside_check)
        collision_hint = "Vorhandene Dateien werden nie überschrieben: Gibt es den Namen schon, wird (2), (3) … angehängt."
        self.output_button.setToolTip(f"Ausgabeordner wählen.\n{collision_hint}")
        self.beside_check.setToolTip(f"Jede Datei landet im Ordner ihrer IFC-Datei.\n{collision_hint}")
        right.addWidget(output_box)
        right.addStretch()

        # Progress of the whole batch, directly under the list and the settings.
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setFormat("Bereit")
        self.overall_progress.setToolTip("Fortschritt über alle Dateien der Liste")
        upper_layout.addWidget(self.overall_progress)

        # The log: what happened, with times; the splitter handle above it lets the user enlarge it.
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Protokoll – hier steht, was mit jeder Datei passiert ist.")
        self.log_view.setMinimumHeight(60)
        self.log_view.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # Tab skips it; it is only read
        self.log_view.setToolTip("Protokoll dieser Sitzung. Alles steht auch in der Logdatei (Hilfe → Logdatei öffnen).")
        self.log_splitter = QSplitter(Qt.Orientation.Vertical)
        self.log_splitter.setChildrenCollapsible(False)
        self.log_splitter.addWidget(upper)
        self.log_splitter.addWidget(self.log_view)
        self.log_splitter.setStretchFactor(0, 1)
        self.log_splitter.setStretchFactor(1, 0)
        self.log_splitter.setSizes([600, 110])
        self.log_splitter.handle(1).setToolTip("Ziehen: Protokoll vergrößern oder verkleinern")
        root.addWidget(self.log_splitter, stretch=1)

        # Bottom: log toggle, status line, actions.
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.log_toggle = QToolButton()
        self.log_toggle.setObjectName("LogToggle")
        self.log_toggle.setText("Protokoll")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(True)
        self.log_toggle.setAutoRaise(True)
        self.log_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.log_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.log_toggle.setToolTip("Protokoll ein- oder ausblenden (F4)")
        self.log_toggle.toggled.connect(self.set_log_visible)
        self.status_label = muted(ElidedLabel())
        self.status_label.setObjectName("Status")
        self.open_button = QPushButton("Ausgabeordner öffnen")
        self.open_button.setToolTip("Öffnet den Ordner der zuletzt geschriebenen Datei.")
        self.open_button.clicked.connect(self.open_output_dir)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.setToolTip("Laufende Konvertierung abbrechen. Fertige Dateien bleiben, die angefangene wird gelöscht.")
        self.cancel_button.clicked.connect(self.cancel_conversion)
        self.convert_button = QPushButton("Konvertieren")
        self.convert_button.setObjectName("Primary")
        self.convert_button.setDefault(True)
        self.convert_button.setToolTip("Alle Dateien der Liste konvertieren (Strg+Enter)")
        self.convert_button.clicked.connect(self.start_conversion)
        actions.addWidget(self.log_toggle)
        actions.addWidget(self.status_label, stretch=1)
        actions.addWidget(self.open_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.convert_button)
        root.addLayout(actions)

        self.setCentralWidget(central)

    def _build_menus(self) -> None:
        def action(text: str, slot, shortcuts=()) -> QAction:
            act = QAction(text, self)
            act.triggered.connect(slot)
            act.setShortcuts([QKeySequence(s) for s in shortcuts])
            act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            self.addAction(act)  # shortcuts also work while the menu bar is hidden
            return act

        self.add_files_action = action("Dateien hinzufügen…", self.browse_files, ["Ctrl+O"])
        self.add_folder_action = action("Ordner hinzufügen…", self.browse_folder, ["Ctrl+Shift+O"])
        self.convert_action = action("Konvertieren", self.start_conversion, ["Ctrl+Return", "Ctrl+Enter"])
        self.cancel_action = action("Abbrechen", self.cancel_conversion)
        self.quit_action = action("Beenden", self.close, ["Ctrl+Q"])
        self.remove_action = action("Entfernen", self.remove_selected, [QKeySequence.StandardKey.Delete])
        self.clear_action = action("Liste leeren", self.clear_list)
        self.settings_action = action("Einstellungen…", self.show_settings, ["Ctrl+,"])
        self.open_output_action = action("Ausgabeordner öffnen", self.open_output_dir)
        self.open_log_action = action("Logdatei öffnen", open_log)
        self.save_log_action = action("Anonymisierte Logdatei speichern…", lambda: save_anonymized_log(self))
        self.about_action = action(f"Über {APP_NAME}", self.show_about)
        self.preview_action = action("Vorschau", self.set_preview_visible, ["F3"])
        self.preview_action.setCheckable(True)
        self.log_action = action("Protokoll", self.set_log_visible, ["F4"])
        self.log_action.setCheckable(True)
        self.log_action.setChecked(True)
        self.drop_zone.add_button.setToolTip("IFC-Dateien auswählen (Strg+O). Ordner: Datei → Ordner hinzufügen…")

        menus = self.menuBar()
        file_menu = menus.addMenu("&Datei")
        file_menu.addActions([self.add_files_action, self.add_folder_action])
        file_menu.addSeparator()
        file_menu.addActions([self.convert_action, self.cancel_action])
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)
        edit_menu = menus.addMenu("&Bearbeiten")
        edit_menu.addActions([self.remove_action, self.clear_action])
        view_menu = menus.addMenu("&Ansicht")
        view_menu.addActions([self.preview_action, self.log_action])
        tools_menu = menus.addMenu("E&xtras")
        tools_menu.addAction(self.settings_action)
        help_menu = menus.addMenu("&Hilfe")
        help_menu.addActions([self.open_output_action, self.open_log_action, self.save_log_action])
        help_menu.addSeparator()
        help_menu.addAction(self.about_action)

    def _build_geometry_options(self) -> QWidget:
        """Sub-options under 3DM: polysurfaces or meshes."""
        self.geometry_box = QWidget()
        layout = QVBoxLayout(self.geometry_box)
        layout.setContentsMargins(22, 0, 0, 4)
        layout.setSpacing(4)
        layout.addWidget(muted(QLabel("Geometrie")))
        self.geometry_group = QButtonGroup(self)
        self.geometry_buttons: dict[str, QRadioButton] = {}
        for mode, (label, hint) in GEOMETRY_INFO.items():
            button = QRadioButton(label)
            button.setToolTip(hint)
            self.geometry_group.addButton(button)
            self.geometry_buttons[mode] = button
            layout.addWidget(button)
            button.toggled.connect(self._geometry_changed)
        return self.geometry_box

    # -------------------------------------------------------------- settings

    def _load_settings(self) -> None:
        fmt = str(self.settings.value("format", DEFAULT_FORMAT))
        if fmt not in self.format_buttons:
            fmt = DEFAULT_FORMAT if DEFAULT_FORMAT in self.format_buttons else next(iter(self.format_buttons))
        self.format_buttons[fmt].setChecked(True)

        saved = self.settings.value("output_dir", "")
        out_dir = Path(saved) if saved and Path(saved).is_dir() else None
        self._set_output_dir(out_dir or desktop_dir(), save=False)

        self.beside_check.setChecked(self.settings.value("beside_input", False, type=bool))
        self._beside_changed(self.beside_check.isChecked())

        mode = str(self.settings.value("rhino_geometry", DEFAULT_GEOMETRY))
        self.geometry_buttons[mode if mode in self.geometry_buttons else DEFAULT_GEOMETRY].setChecked(True)

        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        header = self.settings.value("table_header")
        if header is not None:
            self.table.horizontalHeader().restoreState(header)
        splitter = self.settings.value("preview_splitter")
        if splitter is not None:
            self.splitter.restoreState(splitter)
        visible = self.settings.value("preview_visible", True, type=bool)
        self.preview_action.setChecked(visible)
        self.preview.setVisible(visible)
        log_splitter = self.settings.value("log_splitter")
        if log_splitter is not None:
            self.log_splitter.restoreState(log_splitter)
        self.set_log_visible(self.settings.value("log_visible", True, type=bool))

    @property
    def fmt(self) -> str:
        for fmt, button in self.format_buttons.items():
            if button.isChecked():
                return fmt
        return DEFAULT_FORMAT

    @property
    def output_dir(self) -> Path:
        return Path(self.output_edit.text())

    @property
    def geometry(self) -> str:
        for mode, button in self.geometry_buttons.items():
            if button.isChecked():
                return mode
        return DEFAULT_GEOMETRY

    def set_format(self, fmt: str) -> None:
        self.format_buttons[fmt].setChecked(True)

    def set_geometry(self, mode: str) -> None:
        self.geometry_buttons[mode].setChecked(True)

    def _format_changed(self, checked: bool) -> None:
        if not checked:
            return
        self._update_hint()
        self.settings.setValue("format", self.fmt)
        self._update_actions()

    def _geometry_changed(self, checked: bool) -> None:
        if not checked:
            return
        self._update_hint()
        self.settings.setValue("rhino_geometry", self.geometry)

    def _update_hint(self) -> None:
        # For 3DM the geometry choice is what matters, so its hint replaces the format hint.
        if self.fmt == "3dm":
            self.format_hint.setText(GEOMETRY_INFO[self.geometry][1])
        else:
            self.format_hint.setText(FORMAT_INFO[self.fmt][1])

    def _set_output_dir(self, path: Path, save: bool = True) -> None:
        self.output_edit.setText(str(path))
        self.output_edit.setToolTip(f"Ausgabeordner: {path}\n\nVorhandene Dateien werden nie überschrieben: (2), (3) … wird angehängt.")
        self.output_edit.setCursorPosition(0)
        if save:
            self.settings.setValue("output_dir", str(path))

    def _beside_changed(self, checked: bool) -> None:
        self.settings.setValue("beside_input", checked)
        self._update_actions()

    def show_settings(self) -> None:
        dialog = SettingsDialog(self.preferences, self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self.preferences = dialog.preferences()
            self.preferences.save(self.settings)
            app_info.set_log_anonymized(self.preferences.anonymize_log)
            log.info("Einstellungen: %s", self.preferences)

    def show_about(self) -> None:
        AboutDialog(self).exec()

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Ausgabeordner wählen", str(self.output_dir))
        if path:
            self._set_output_dir(Path(path))

    # ------------------------------------------------------------- file list

    def add_paths(self, paths: list[str | Path]) -> AddResult:
        """Add files and folders to the list; during a run they are converted right after it."""
        result = self.queue.add(paths)
        start = self.table.rowCount()
        for offset, _path in enumerate(result.added):
            if self.is_running:
                self.queue[start + offset].queued = True
                self._pending_rows.append(start + offset)
            self._insert_row(start + offset)
        for path in result.rejected:
            self.log(f"✗ Keine IFC-Datei gefunden: {path} – nur .ifc- und .ifczip-Dateien und Ordner damit "
                     "(ifcXML kann nicht gelesen werden)")
        if result.duplicates:
            names = ", ".join(p.name for p in result.duplicates[:3])
            more = " …" if len(result.duplicates) > 3 else ""
            self.log(f"• Schon in der Liste: {names}{more}")
        if result.added and self.is_running:
            self.log(f"+ {files_text(len(result.added))} vorgemerkt: Konvertierung gleich nach der laufenden, "
                     "mit denselben Einstellungen.")
        elif result.added:
            self.log(f"+ {files_text(len(result.added))} hinzugefügt")
        if result.added and not self.table.selectionModel().selectedRows():
            self.table.selectRow(start)  # its preview shows right away
        self._update_actions()
        return result

    def browse_files(self) -> None:
        start = self.settings.value("last_input_dir", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(
            self, "IFC-Dateien hinzufügen", str(start),
            "IFC-Dateien (*.ifc *.IFC *.ifczip *.ifcZIP);;Alle Dateien (*)",
        )
        if files:
            self.settings.setValue("last_input_dir", str(Path(files[0]).parent))
            self.add_paths(files)

    def browse_folder(self) -> None:
        start = self.settings.value("last_input_dir", str(Path.home()))
        folder = QFileDialog.getExistingDirectory(self, "Ordner mit IFC-Dateien hinzufügen", str(start))
        if folder:
            self.settings.setValue("last_input_dir", folder)
            self.add_paths([folder])

    def remove_selected(self) -> None:
        if self.is_running:
            return
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()}, reverse=True)
        self.queue.remove(rows)
        for row in rows:
            self.table.removeRow(row)
        self._update_actions()

    def clear_list(self) -> None:
        if self.is_running:
            return
        self.queue.clear()
        self.table.setRowCount(0)
        self.overall_progress.setValue(0)
        self.overall_progress.setFormat("Bereit")
        self._update_actions()

    def _insert_row(self, row: int) -> None:
        item = self.queue[row]
        self.table.insertRow(row)
        name = QTableWidgetItem(item.path.name)
        name.setToolTip(str(item.path))
        size = QTableWidgetItem(format_size(item.size))
        size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(row, 0, name)
        self.table.setItem(row, 1, size)
        self.table.setItem(row, 2, QTableWidgetItem())
        self._refresh_row(row)

    def _refresh_row(self, row: int) -> None:
        item = self.queue[row]
        cell = self.table.item(row, 2)
        cell.setText(item.status_text)
        cell.setData(PROGRESS_ROLE, item.progress if item.status is Status.RUNNING else None)
        cell.setIcon(status_icon(item.status))
        if item.status is Status.DONE:
            cell.setForeground(DONE_COLOR)
            tooltip = f"Geschrieben: {item.output}"
            if item.crashed:
                tooltip += f"\n\n⚠ {len(item.crashed)} übersprungen (Geometriekern abgestürzt oder hängen geblieben)"
            if item.skipped > 0:
                tooltip += f"\n\n⚠ {skipped_count(item.skipped)}: {SKIPPED_HINT}"
            if item.has_details:
                tooltip += "\n\nListe zum Kopieren: Rechtsklick → „Übersprungene Bauteile…“"
        elif item.status is Status.FAILED:
            cell.setForeground(ERROR_COLOR)
            tooltip = f"{item.error}\n\n{failure_hint(item.internal_error)}"
        else:
            cell.setData(Qt.ItemDataRole.ForegroundRole, None)
            tooltip = ""
        warning = f"⚠ {item.warning}" if item.warning else ""
        cell.setToolTip("\n\n".join(t for t in (tooltip, warning) if t))
        name = self.table.item(row, 0)
        name.setToolTip("\n\n".join(t for t in (str(item.path), warning) if t))
        name.setIcon(self._warning_icon if item.warning else QIcon())

    def row_tooltip(self, row: int) -> str:
        return self.table.item(row, 0).toolTip()

    def status_text(self, row: int) -> str:
        return self.table.item(row, 2).text()

    # ------------------------------------------------------------ conversion

    @property
    def is_running(self) -> bool:
        return self._worker is not None

    def start_conversion(self) -> None:
        if self.is_running or not len(self.queue):
            return
        self._pending_rows = []
        self._chain_started_at = time.monotonic()
        self._chain_done = self._chain_failed = 0
        if not self._start_run(self.queue.prepare_run()):
            self._update_actions()

    def _start_run(self, rows: list[int]) -> bool:
        """Convert ``rows`` (all waiting) in the background; False if the output folder is not usable."""
        out_dir = None if self.beside_check.isChecked() else self.output_dir
        if out_dir is not None:
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, APP_NAME, f"Ausgabeordner kann nicht angelegt werden:\n{exc}")
                return False
        for row in rows:
            self._refresh_row(row)
        self._run_rows, self._run_done, self._run_failed = rows, 0, 0

        fmt = self.fmt
        target = "neben den IFC-Dateien" if out_dir is None else str(out_dir)
        geometry = self.geometry
        label = f"3DM ({GEOMETRY_INFO[geometry][0].split(' (')[0]})" if fmt == "3dm" else fmt.upper()
        prefs = self.preferences
        kernel = "" if prefs.kernel == DEFAULT_KERNEL else f", Geometriekern {KERNEL_INFO[prefs.kernel][0]}"
        blocks = ", gleiche Bauteile als Blöcke" if fmt == "3dm" and prefs.blocks else ""
        self.log(f"▶ {files_text(len(rows))} → {label}{blocks}, Ziel: {target}{kernel}")
        threads = prefs.effective_threads
        resources = resource_text(threads, prefs.low_priority, rhino_workers(threads) if fmt == "3dm" else 0)
        self.log(f"• Rechenleistung: {resources}")

        jobs = [(row, self.queue[row].path) for row in rows]
        self._worker = ConversionWorker(
            jobs, fmt, out_dir, threads=prefs.effective_threads, geometry=geometry, kernel=prefs.kernel,
            low_priority=prefs.low_priority, blocks=prefs.blocks,
        )
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_warning.connect(self._on_file_warning)
        self._worker.file_progress.connect(self._on_file_progress)
        self._worker.file_retrying.connect(self._on_file_retrying)
        self._worker.file_status.connect(self._on_file_status)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.file_failed.connect(self._on_file_failed)
        self._worker.file_cancelled.connect(self._on_file_cancelled)
        self._worker.finished.connect(self._on_finished)
        # quit() is thread-safe; a direct call lets _on_finished wait for the thread without deadlocking.
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._thread.finished.connect(self._worker.deleteLater)

        self._update_overall(0)
        self._update_actions()
        self._set_status("Konvertierung läuft …")
        self._started_at = time.monotonic()
        self._thread.start()
        return True

    def cancel_conversion(self) -> None:
        if self._worker is not None and not self._worker.cancelled:
            self._worker.cancel()
            self._update_actions()
            self._set_status("Wird abgebrochen …")
            self.log("■ Abbruch angefordert")

    def _on_file_started(self, row: int, target: Path) -> None:
        item = self.queue[row]
        item.status, item.progress, item.detail, item.phase = Status.RUNNING, READING, "", ""
        self._refresh_row(row)
        self.table.scrollToItem(self.table.item(row, 0))
        self._update_overall(0)
        # Reading gives no progress at all, so show a busy bar to make clear the app is not frozen.
        self.overall_progress.setRange(0, 0)
        self._set_activity(f"IFC wird gelesen ({format_size(item.size)}) – kann einige Minuten dauern …")
        self.log(f"… {item.path.name} ({format_size(item.size)}) → {target.name}")

    def _on_file_retrying(self, row: int, message: str = RETRY_MESSAGE) -> None:
        item = self.queue[row]
        if item.status is not Status.RUNNING:
            return
        # The file is read again from the start, so back to the reading state and the busy bar.
        item.progress, item.detail, item.phase = READING, "", ""
        self._refresh_row(row)
        self._update_overall(0)
        self.overall_progress.setRange(0, 0)
        self._set_activity(f"{item.path.name}: neuer Versuch – IFC wird gelesen …")
        self.log(f"⚠ {item.path.name}: {message}")

    def _on_file_status(self, row: int, phase: str, text: str) -> None:
        item = self.queue[row]
        if item.status is not Status.RUNNING:
            return
        # The row only shows the long phases in which the percentage stands still: deeply nested
        # elements (computed one by one), writing and copying the output.
        detail = text if phase in ("write", "copy", "deep") else ""
        if detail != item.detail:
            if detail and phase != item.phase:
                self.log(f"… {item.path.name}: {text}")
            item.detail = detail
            self._refresh_row(row)
        item.phase = phase
        if phase != "read":
            self._set_activity(f"{item.path.name}: {text}")

    def _on_file_warning(self, row: int, message: str) -> None:
        item = self.queue[row]
        item.warning = message
        self._refresh_row(row)
        self.log(f"⚠ {message}")

    def _set_activity(self, text: str) -> None:
        if self._worker is not None and not self._worker.cancelled:
            self._set_status(text)

    def _on_file_progress(self, row: int, percent: int) -> None:
        item = self.queue[row]
        if item.status is not Status.RUNNING:
            return
        if item.progress == READING:
            self._set_activity(f"{item.path.name} wird konvertiert …")
        item.progress = percent
        self._refresh_row(row)
        self._update_overall(percent)

    def _on_file_done(self, row: int, result: ConversionResult) -> None:
        item = self.queue[row]
        item.status, item.progress, item.output, item.elements = Status.DONE, 100, result.output, result.elements
        item.skipped, item.crashed, item.no_geometry = result.skipped, list(result.crashed), list(result.no_geometry)
        self._refresh_row(row)
        self._run_done += 1
        self._last_output_dir = result.output.parent
        self._update_overall(0)
        self.log(f"✓ {item.path.name} → {result.output}  ({count_text(result.elements, 'Bauteil', 'Bauteile')})")
        if result.crashed:
            self.log(f"⚠ {item.path.name}: {crashed_warning(result.crashed)}")
        if result.skipped > 0:
            self.log(f"⚠ {item.path.name}: {skipped_warning(result.skipped)}")
        if item.has_details:
            self.log("   → Liste zum Kopieren: Rechtsklick auf die Datei → „Übersprungene Bauteile…“")
        self._update_actions()

    def _on_file_failed(self, row: int, message: str, internal: bool = False) -> None:
        item = self.queue[row]
        item.status, item.error, item.internal_error = Status.FAILED, message, internal
        self._refresh_row(row)
        self._run_failed += 1
        self._update_overall(0)
        self.log(f"✗ Fehler bei {item.path.name}: {message}")
        self.log(f"   → {failure_hint(internal)}")

    def _on_file_cancelled(self, row: int) -> None:
        item = self.queue[row]
        item.status = Status.CANCELLED
        self._refresh_row(row)

    def _on_finished(self, cancelled: bool) -> None:
        if self._thread is not None:
            self._thread.wait()
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

        seconds = time.monotonic() - self._started_at
        summary = f"{self._run_done} von {files_text(len(self._run_rows))} fertig"
        if self._run_failed:
            summary += f", {self._run_failed} mit Fehler"
        if cancelled:
            summary += " – abgebrochen"
        summary += f" ({duration_text(seconds)})"
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setFormat(summary.split(" (")[0])
        if not cancelled:
            self.overall_progress.setValue(100)
        self.log(f"■ {summary}")
        self._chain_done += self._run_done
        self._chain_failed += self._run_failed
        if self._start_pending(cancelled):
            return
        self._notify_finished(cancelled, time.monotonic() - self._chain_started_at)
        self._update_actions()
        if self.preferences.open_output and not cancelled and self._chain_done and self._last_output_dir:
            self.open_output_dir()
        self.conversion_finished.emit(cancelled)

    def _start_pending(self, cancelled: bool) -> bool:
        """Convert the files added during the run that just ended; False if there are none (or cancelled)."""
        pending = [row for row in self._pending_rows if self.queue[row].status is Status.WAITING]
        self._pending_rows = []
        for row in pending:
            self.queue[row].queued = False
            self._refresh_row(row)
        if not pending:
            return False
        if cancelled:
            noun = "vorgemerkte Datei" if len(pending) == 1 else "vorgemerkte Dateien"
            self.log(f"• {len(pending)} {noun} nicht konvertiert – „Konvertieren“ startet sie.")
            return False
        self.log(f"▶ Weiter mit {files_text(len(pending))}, hinzugefügt während der Konvertierung")
        return self._start_run(pending)

    def _notify_finished(self, cancelled: bool, seconds: float) -> None:
        """Say that the batch is over: in the window, its title and, if it is in the background, the taskbar."""
        duration = duration_text(seconds)
        if cancelled:
            text, state, title = f"Abgebrochen nach {duration}", "", "Abgebrochen"
        elif self._chain_failed:
            done = f"{self._chain_done} fertig, " if self._chain_done else ""
            text, state, title = f"✗ {done}{self._chain_failed} mit Fehler – nach {duration}", "failed", "Fehler"
        else:
            text, state, title = f"✓ Fertig nach {duration}", "done", "✓ Fertig"
        self._set_status(text, state)
        if self.isActiveWindow():
            self._set_title()
        else:
            # Stays until the window is activated again; the taskbar entry flashes (Windows) or is marked.
            self._set_title(title)
            QApplication.alert(self)

    def _set_status(self, text: str, state: str = "") -> None:
        self.status_label.setText(text)
        if self.status_label.property("state") != state:
            self.status_label.setProperty("state", state)
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

    def _set_title(self, prefix: str = "") -> None:
        title = f"{APP_NAME} {__version__}"
        self.setWindowTitle(f"{prefix} – {title}" if prefix else title)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() and not self.is_running:
            self._set_title()
        super().changeEvent(event)

    def _update_overall(self, current_percent: int) -> None:
        total = len(self._run_rows) or 1
        finished = self._run_done + self._run_failed
        self.overall_progress.setRange(0, 100)
        value = min(100, int((finished * 100 + (current_percent if finished < total else 0)) / total))
        self.overall_progress.setValue(value)
        self.overall_progress.setFormat(f"{finished} von {files_text(total)} fertig – %p{NNBSP}%")
        self._set_title(f"{value} %")  # visible in the taskbar while the window is in the background

    # --------------------------------------------------------------- helpers

    def open_output_dir(self) -> None:
        folder = self._last_output_dir or self.output_dir
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            self.log(f"✗ Ausgabeordner gibt es (noch) nicht: {folder}")

    def _selected_details_row(self) -> int | None:
        """The selected row if it is the only one and has skipped elements to list."""
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        if len(rows) == 1:
            row = rows.pop()
            if row < len(self.queue) and self.queue[row].has_details:
                return row
        return None

    def show_details(self, row: int | None = None) -> SkippedDialog | None:
        """Open the list of the elements of ``row`` (default: the selected one) that were not converted."""
        row = self._selected_details_row() if row is None else row
        if row is None:
            return None
        item = self.queue[row]
        dialog = SkippedDialog(item.path.name, item.crashed, item.no_geometry, item.skipped, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()  # not modal: the list can stay open next to the CAD program
        return dialog

    def _show_row_menu(self, position) -> None:
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        item = self.queue[row]
        menu = QMenu(self)
        details = menu.addAction("Übersprungene Bauteile…")
        details.setEnabled(item.has_details)
        details.triggered.connect(lambda: self.show_details(row))
        folder = menu.addAction("Ausgabeordner öffnen")
        folder.setEnabled(item.status is Status.DONE and item.output is not None)
        folder.triggered.connect(lambda: self._open_row_folder(row, 0))
        if item.status is Status.FAILED:
            menu.addAction("Logdatei öffnen").triggered.connect(open_log)
        menu.popup(self.table.viewport().mapToGlobal(position))

    def _open_row_folder(self, row: int, _column: int) -> None:
        item = self.queue[row]
        if item.status is Status.DONE and item.output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.output.parent)))

    def log(self, message: str) -> None:
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _update_actions(self) -> None:
        running = self.is_running
        has_items = len(self.queue) > 0
        self.convert_button.setEnabled(has_items and not running)
        self.cancel_button.setEnabled(running and not self._worker.cancelled)
        self.remove_button.setEnabled(not running and bool(self.table.selectionModel().selectedRows()))
        self.clear_button.setEnabled(not running and has_items)
        self.open_button.setEnabled(not running and self._last_output_dir is not None)
        # After a successful batch, the way to the result is the most likely next click.
        self._set_highlight(self.open_button, self.open_button.isEnabled() and self._chain_done > 0)
        self.drop_zone.set_compact(has_items)
        for act, button in (
            (self.convert_action, self.convert_button), (self.cancel_action, self.cancel_button),
            (self.remove_action, self.remove_button), (self.clear_action, self.clear_button),
        ):
            act.setEnabled(button.isEnabled())
        # Files added during a run are converted right after it (see add_paths).
        self.settings_action.setEnabled(not running)
        self.details_button.setEnabled(self._selected_details_row() is not None)
        for button in self.format_buttons.values():
            button.setEnabled(not running)
        self.geometry_box.setEnabled(not running and self.fmt == "3dm")
        self.beside_check.setEnabled(not running)
        beside = self.beside_check.isChecked()
        self.output_edit.setEnabled(not running and not beside)
        self.output_button.setEnabled(not running and not beside)
        count = len(self.queue)
        done = sum(1 for item in self.queue if item.status is Status.DONE)
        self.count_label.setText(f"{done} von {files_text(count)} fertig" if done else files_text(count))
        if not running and not self.status_label.text():
            self._set_status("Dateien hinzufügen und auf „Konvertieren“ klicken.")

    @staticmethod
    def _set_highlight(button: QPushButton, on: bool) -> None:
        if bool(button.property("highlight")) != on:
            button.setProperty("highlight", on)
            button.style().unpolish(button)
            button.style().polish(button)

    # ---------------------------------------------------------- drag & drop

    @staticmethod
    def _local_paths(event) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event):
        if self._local_paths(event):
            event.acceptProposedAction()
            self.drop_zone.set_active(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._local_paths(event):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drop_zone.set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_zone.set_active(False)
        paths = self._local_paths(event)
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

    # ---------------------------------------------------------------- closing

    def _running_text(self) -> str:
        """E.g. "„Modell.ifc“ wird seit 42 min 3 s umgewandelt (89 %)."."""
        running = next((item for item in self.queue if item.status is Status.RUNNING), None)
        if running is None:
            return "Die Konvertierung läuft noch."
        since = duration_text(time.monotonic() - self._started_at)
        return f"„{running.path.name}“ wird konvertiert, die Konvertierung läuft seit {since} ({max(running.progress, 0)} %)."

    def closeEvent(self, event):
        if self.is_running:
            answer = QMessageBox.question(
                self, APP_NAME,
                f"{self._running_text()}\n\nBeim Beenden wird die Konvertierung abgebrochen, ihr Fortschritt geht "
                "verloren. Trotzdem beenden?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,  # Enter keeps it running
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.cancel()
            if self._thread is not None:
                self._thread.quit()
                self._thread.wait()
        self.preview.shutdown()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("table_header", self.table.horizontalHeader().saveState())
        self.settings.setValue("preview_splitter", self.splitter.saveState())
        self.settings.setValue("log_splitter", self.log_splitter.saveState())
        self.settings.sync()
        super().closeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_preview()

    def set_preview_visible(self, visible: bool) -> None:
        self.preview.setVisible(visible)
        self.preview_action.setChecked(visible)
        self.settings.setValue("preview_visible", visible)
        self._update_preview()

    def set_log_visible(self, visible: bool) -> None:
        """Show or fold away the log (Ansicht → Protokoll, F4, or the "Protokoll" button)."""
        self.log_view.setVisible(visible)
        self.log_action.setChecked(visible)
        self.log_toggle.setChecked(visible)
        self.log_toggle.setArrowType(Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow)
        self.settings.setValue("log_visible", visible)

    def _update_preview(self) -> None:
        """Show the preview of the selected file (the current one of several), if the pane is shown."""
        if not self.isVisible() or not self.preview_action.isChecked():
            return
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        current = self.table.currentRow()
        row = current if current in rows else (rows[0] if rows else None)
        self.preview.show_file(self.queue[row].path if row is not None and row < len(self.queue) else None)

    def receive_paths(self, paths: list[str]) -> None:
        """Files sent by another start of the app (e.g. dropped onto its icon): add them, show the window."""
        log.info("Zweiter Start: %d Pfad(e) übernommen", len(paths))
        if paths:
            # During a run they are converted right after it, like files dropped into the window.
            self.add_paths(paths)
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()


# ------------------------------------------------------------------ app start


def open_settings(path: Path | None = None, legacy: QSettings | None = None) -> QSettings:
    """The settings, in an INI file (also on Windows: easy to find, back up or reset; no registry).

    The first time, the settings of the app's earlier name (registry on Windows) are copied over;
    the old ones are left alone.
    """
    path = path or app_info.settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    if not path.exists():
        legacy = legacy if legacy is not None else QSettings(LEGACY_NAME, LEGACY_NAME)
        keys = legacy.allKeys()
        for key in keys:
            settings.setValue(key, legacy.value(key))
        if keys:
            settings.sync()
            log.info("%d Einstellungen von %s übernommen", len(keys), legacy.fileName())
    return settings


def instance_name() -> str:
    """Name of the local socket (a named pipe on Windows) of the running app, one per user."""
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - no user name in the environment
        user = str(Path.home().name)
    return "ifc-converter-" + re.sub(r"[^A-Za-z0-9_.-]", "_", user)


def send_to_running_instance(paths: list[str], name: str | None = None, timeout_ms: int = 1000) -> bool:
    """Hand ``paths`` to an already running app; False if there is none.

    Dropping files onto the app's icon starts it again; this keeps one window with one queue (two
    conversions at once would compete for the memory).
    """
    socket = QLocalSocket()
    socket.connectToServer(name or instance_name())
    if not socket.waitForConnected(timeout_ms):
        return False
    if sys.platform == "win32":
        try:  # let the running app bring its window to the front
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except (OSError, AttributeError):
            pass
    socket.write(json.dumps([str(Path(p).absolute()) for p in paths]).encode("utf-8"))
    socket.flush()
    sent = socket.waitForBytesWritten(timeout_ms) or socket.bytesToWrite() == 0
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(timeout_ms)
    return sent


class InstanceServer(QObject):
    """Receives the paths of later starts of the app (see send_to_running_instance())."""

    paths_received = Signal(list)

    def __init__(self, name: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.name = name or instance_name()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)
        self._buffers: dict[QLocalSocket, bytes] = {}

    def listen(self) -> bool:
        if self.server.listen(self.name):
            return True
        # A socket file left behind by a crashed app (Linux/macOS); nobody answered on it.
        QLocalServer.removeServer(self.name)
        return self.server.listen(self.name)

    def _accept(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self._buffers[socket] = b""
            socket.readyRead.connect(self._read)
            socket.disconnected.connect(self._finish)
            if socket.bytesAvailable():
                self._read(socket)
            if socket.state() == QLocalSocket.LocalSocketState.UnconnectedState:
                self._finish(socket)

    @Slot()
    def _read(self, socket: QLocalSocket | None = None) -> None:
        socket = socket or self.sender()
        if socket in self._buffers:
            self._buffers[socket] += bytes(socket.readAll())

    @Slot()
    def _finish(self, socket: QLocalSocket | None = None) -> None:
        socket = socket or self.sender()
        if socket not in self._buffers:
            return
        self._read(socket)
        data = self._buffers.pop(socket)
        socket.readyRead.disconnect(self._read)
        socket.disconnected.disconnect(self._finish)
        socket.deleteLater()
        try:
            paths = json.loads(data.decode("utf-8")) if data else []
        except (UnicodeDecodeError, ValueError):
            return
        if isinstance(paths, list):
            self.paths_received.emit([str(p) for p in paths])


def main(argv: list[str] | None = None) -> int:
    # Conversions run in "spawn" child processes. A frozen build (e.g. PyInstaller) starts its own
    # executable for them, and this makes it do the child's work instead of opening another window.
    # A no-op otherwise.
    multiprocessing.freeze_support()
    app = QApplication.instance() or QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    # Files passed on the command line (e.g. dropped onto the app's icon) are added right away.
    paths = app.arguments()[1:] if argv is None else argv
    if send_to_running_instance(paths):
        return 0

    setup_logging("GUI")
    enable_crash_log()
    # While the window is open (and with it any conversion), the installer refuses to update or remove it.
    hold_app_mutex()
    reporter = ErrorReporter(app)
    install_exception_hooks(reporter.report)

    removed = remove_stale_temp_files()
    if removed:
        log.info("%d alte Zwischendateien im Temp-Ordner gelöscht", removed)
    window = MainWindow()
    server = InstanceServer(parent=window)
    server.paths_received.connect(window.receive_paths)
    if not server.listen():
        log.warning("Zweiter Start kann keine Dateien übergeben: %s", server.server.errorString())
    window.show()
    if paths:
        window.add_paths(paths)
    code = app.exec()
    log.info("%s beendet", APP_NAME)
    return code


if __name__ == "__main__":
    sys.exit(main())
