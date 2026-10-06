"""Desktop GUI: drop IFC files into a window and convert them in the background."""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, QRect, QSettings, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QKeySequence, QPalette, QShortcut
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
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ifc_converter.converter import FORMATS, convert
from ifc_converter.interactive import check_memory, collect_ifc_files, desktop_dir, unique_path

APP_NAME = "IFC File Converter"
DEFAULT_FORMAT = "3dm"
DEFAULT_GEOMETRY = "brep"
SIDE_WIDTH = 320  # settings column on the right

# Format -> (label, hint), in the order shown in the window.
FORMAT_INFO = {
    "3dm": ("3DM (Rhino)", "Rhino-Datei (.3dm) – direkt in Rhino öffnen und weiterbearbeiten."),
    "glb": ("GLB", "glTF binär (.glb) – kompakt, für Web-Viewer, Blender, Three.js und Game-Engines."),
    "obj": ("OBJ", "Wavefront OBJ (.obj + .mtl) – lässt sich in fast jedem 3D-Programm öffnen."),
}

# Rhino geometry mode (convert(..., geometry=...), only used for 3DM) -> (label, hint).
GEOMETRY_INFO = {
    "brep": (
        "Polyflächen (empfohlen)",
        "Wände, Decken, Fenster … als geschlossene Polyflächen mit echten Öffnungen. Sehr detaillierte "
        "Objekte (Möbel, Sanitär, Leuchten) bleiben Netze. Datei ca. 2–3× größer.",
    ),
    "mesh": ("Netze (Meshes)", "Kleinste Dateien, schnellste Umwandlung."),
}

DONE_COLOR = QColor("#2e9d57")
ERROR_COLOR = QColor("#d64545")
PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 1
# QueueItem.progress while the IFC file is still being read: convert() reports progress(0) only afterwards.
READING = -1


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
    output: Path | None = None
    error: str = ""
    warning: str = ""  # RAM warning for large files, shown as tooltip

    @property
    def status_text(self) -> str:
        if self.status is Status.RUNNING:
            if self.progress == READING:
                return "IFC wird gelesen …"
            return f"Läuft … {self.progress} %"
        if self.status is Status.DONE:
            return f"Fertig – {self.elements} Bauteile"
        if self.status is Status.FAILED:
            return f"Fehler: {self.error}"
        if self.status is Status.CANCELLED:
            return "Abgebrochen"
        return "Wartend"


@dataclass
class AddResult:
    added: list[Path]
    rejected: list[Path]
    duplicates: list[Path]


def format_size(size: int) -> str:
    """Human readable file size with a German decimal comma."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            break
        value /= 1024
    text = f"{value:.0f}" if unit == "B" else f"{value:.1f}"
    return f"{text.replace('.', ',')} {unit}"


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
        return rows


# -------------------------------------------------------------------------- worker


class _Cancelled(Exception):
    pass


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


class ConversionWorker(QObject):
    """Converts a batch of files one after another; meant to live in a QThread."""

    file_started = Signal(int, object)  # row, target path
    file_warning = Signal(int, str)  # row, RAM warning
    file_progress = Signal(int, int)  # row, percent
    file_done = Signal(int, object, int)  # row, output path, elements
    file_failed = Signal(int, str)  # row, message
    file_cancelled = Signal(int)
    finished = Signal(bool)  # True if cancelled

    def __init__(
        self,
        jobs: list[tuple[int, Path]],
        fmt: str,
        out_dir: Path | None,
        threads: int | None = None,
        geometry: str = DEFAULT_GEOMETRY,
    ):
        super().__init__()
        self.jobs = jobs
        self.fmt = fmt
        self.geometry = geometry
        self.out_dir = out_dir
        self.threads = threads
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
        # OBJ also writes a .mtl; only clean that up after a failure if we created it.
        side_files = [target.with_suffix(".mtl")] if self.fmt == "obj" else []
        side_files = [p for p in side_files if not p.exists()]
        self.file_started.emit(row, target)
        # Checked here rather than in the GUI thread; for a large file it is the only hint for minutes.
        warning = check_memory(source)
        if warning:
            self.file_warning.emit(row, warning)
        last = READING

        def progress(percent: int) -> None:
            nonlocal last
            if self._cancel.is_set():
                raise _Cancelled
            percent = max(0, min(100, int(percent)))
            if percent != last:
                last = percent
                self.file_progress.emit(row, percent)

        try:
            # The geometry mode only exists for Rhino, so GLB/OBJ calls leave it out.
            options = {"geometry": self.geometry} if self.fmt == "3dm" else {}
            result = convert(source, target, self.fmt, self.threads, progress, **options)
        except _Cancelled:
            for path in [target, *side_files]:
                _discard(path)
            self.file_cancelled.emit(row)
        except Exception as exc:  # one broken file must not stop the batch
            for path in [target, *side_files]:
                _discard(path)
            self.file_failed.emit(row, str(exc) or type(exc).__name__)
        else:
            self.file_done.emit(row, result.output, result.elements)


# ------------------------------------------------------------------------- widgets


class StatusDelegate(QStyledItemDelegate):
    """Paints a slim progress fill behind the status text of running files."""

    def paint(self, painter, option, index):
        percent = index.data(PROGRESS_ROLE)
        if percent is not None and percent > 0:
            rect = option.rect.adjusted(3, 4, -3, -4)
            color = QColor(option.palette.color(QPalette.ColorRole.Highlight))
            color.setAlpha(70)
            painter.save()
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
        self.setMinimumHeight(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        icon = QLabel("⬇")
        icon.setObjectName("DropIcon")
        title = QLabel("IFC-Dateien oder Ordner hierher ziehen")
        title.setObjectName("DropTitle")
        hint = QLabel("Ordner werden nach .ifc-Dateien durchsucht")
        hint.setObjectName("Hint")
        self.add_button = QPushButton("Dateien hinzufügen…")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self.browse_requested)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        for widget in (icon, title, hint):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(widget)
        layout.addSpacing(4)
        layout.addWidget(self.add_button, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()
        super().mouseReleaseEvent(event)


STYLESHEET = """
QLabel#AppTitle { font-size: 20px; font-weight: 600; }
QLabel#DropIcon { font-size: 26px; color: palette(highlight); }
QLabel#DropTitle { font-size: 15px; font-weight: 600; }
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
    padding: 10px 8px 8px 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QGroupBox QRadioButton, QGroupBox QCheckBox, QGroupBox QLabel, QGroupBox QLineEdit { font-weight: normal; }
QTableWidget { border: 1px solid palette(mid); border-radius: 8px; }
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
QPushButton#Primary:disabled { background: palette(mid); color: palette(window); }
QProgressBar { border: 1px solid palette(mid); border-radius: 6px; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: palette(highlight); border-radius: 5px; }
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


def _muted(label: QLabel) -> QLabel:
    palette = label.palette()
    muted = palette.color(QPalette.ColorRole.PlaceholderText)
    # Only the enabled groups, so a disabled hint still looks disabled.
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        palette.setColor(group, QPalette.ColorRole.WindowText, muted)
    label.setPalette(palette)
    return label


class MainWindow(QMainWindow):
    conversion_finished = Signal(bool)  # True if cancelled; mainly for tests

    COLUMNS = ("Datei", "Größe", "Status")

    def __init__(self, settings: QSettings | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings or QSettings(APP_NAME, APP_NAME)
        self.queue = FileQueue()
        self._thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._run_rows: list[int] = []
        self._run_done = 0
        self._run_failed = 0
        self._last_output_dir: Path | None = None
        self._current_row: int | None = None
        self._warning_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(860, 600)
        available = self.screen().availableGeometry()
        self.resize(min(1000, available.width() - 40), min(720, available.height() - 40))
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLESHEET)

        self._build_ui()
        self._load_settings()
        # Never allow the window to get smaller than its content needs.
        self.setMinimumSize(self.minimumSize().expandedTo(self.centralWidget().minimumSizeHint()))
        self._update_actions()

    # ---------------------------------------------------------------- layout

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        subtitle = _muted(QLabel("IFC-Gebäudemodelle in 3D-Formate umwandeln"))
        header = QVBoxLayout()
        header.setSpacing(0)
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, stretch=1)

        # Left: drop zone, file table, list buttons.
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
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header_view.setHighlightSections(False)
        self.table.setColumnWidth(2, 230)
        self.table.setItemDelegateForColumn(2, StatusDelegate(self.table))
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.cellDoubleClicked.connect(self._open_row_folder)
        left.addWidget(self.table, stretch=1)
        QShortcut(QKeySequence.StandardKey.Delete, self.table, activated=self.remove_selected)

        list_buttons = QHBoxLayout()
        self.remove_button = QPushButton("Entfernen")
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton("Liste leeren")
        self.clear_button.clicked.connect(self.clear_list)
        self.count_label = _muted(QLabel())
        list_buttons.addWidget(self.remove_button)
        list_buttons.addWidget(self.clear_button)
        list_buttons.addStretch()
        list_buttons.addWidget(self.count_label)
        left.addLayout(list_buttons)

        # Right: format and output settings.
        right = QVBoxLayout()
        right.setSpacing(10)
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
        self.format_group = QButtonGroup(self)
        self.format_buttons: dict[str, QRadioButton] = {}
        for fmt, (label, _hint) in FORMAT_INFO.items():
            if fmt not in FORMATS:
                continue
            button = QRadioButton(label)
            self.format_group.addButton(button)
            self.format_buttons[fmt] = button
            format_layout.addWidget(button)
            button.toggled.connect(self._format_changed)
            if fmt == "3dm":
                format_layout.addWidget(self._build_geometry_options())
        self.format_hint = _muted(HintLabel([hint for _label, hint in (*FORMAT_INFO.values(), *GEOMETRY_INFO.values())]))
        self.format_hint.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        format_layout.addSpacing(2)
        format_layout.addWidget(self.format_hint)
        right.addWidget(format_box)

        output_box = QGroupBox("Speicherort")
        output_layout = QVBoxLayout(output_box)
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_button = QPushButton("Ändern…")
        self.output_button.clicked.connect(self.choose_output_dir)
        row = QHBoxLayout()
        row.addWidget(self.output_edit, stretch=1)
        row.addWidget(self.output_button)
        output_layout.addLayout(row)
        self.beside_check = QCheckBox("Neben der IFC-Datei speichern")
        self.beside_check.toggled.connect(self._beside_changed)
        output_layout.addWidget(self.beside_check)
        collision_hint = "Vorhandene Dateien werden nie überschrieben: Gibt es den Namen schon, wird (2), (3) … angehängt."
        self.output_button.setToolTip(collision_hint)
        self.beside_check.setToolTip(collision_hint)
        right.addWidget(output_box)
        right.addStretch()

        # Bottom: progress, log, actions.
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setFormat("Bereit")
        root.addWidget(self.overall_progress)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Protokoll")
        self.log_view.setFixedHeight(96)
        root.addWidget(self.log_view)

        actions = QHBoxLayout()
        self.status_label = _muted(QLabel())
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.open_button = QPushButton("Ausgabeordner öffnen")
        self.open_button.clicked.connect(self.open_output_dir)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.clicked.connect(self.cancel_conversion)
        self.convert_button = QPushButton("Konvertieren")
        self.convert_button.setObjectName("Primary")
        self.convert_button.setDefault(True)
        self.convert_button.clicked.connect(self.start_conversion)
        actions.addWidget(self.status_label, stretch=1)
        actions.addWidget(self.open_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.convert_button)
        root.addLayout(actions)

        self.setCentralWidget(central)

    def _build_geometry_options(self) -> QWidget:
        """Sub-options under 3DM: polysurfaces or meshes."""
        self.geometry_box = QWidget()
        layout = QVBoxLayout(self.geometry_box)
        layout.setContentsMargins(24, 0, 0, 4)
        layout.setSpacing(2)
        layout.addWidget(QLabel("Geometrie:"))
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
        self.output_edit.setToolTip(f"{path}\n\nVorhandene Dateien werden nie überschrieben: (2), (3) … wird angehängt.")
        self.output_edit.setCursorPosition(0)
        if save:
            self.settings.setValue("output_dir", str(path))

    def _beside_changed(self, checked: bool) -> None:
        self.settings.setValue("beside_input", checked)
        self._update_actions()

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Ausgabeordner wählen", str(self.output_dir))
        if path:
            self._set_output_dir(Path(path))

    # ------------------------------------------------------------- file list

    def add_paths(self, paths: list[str | Path]) -> AddResult:
        result = self.queue.add(paths)
        start = self.table.rowCount()
        for offset, _path in enumerate(result.added):
            self._insert_row(start + offset)
        for path in result.rejected:
            self.log(f"✗ Keine IFC-Datei gefunden: {path}")
        if result.duplicates:
            names = ", ".join(p.name for p in result.duplicates[:3])
            more = " …" if len(result.duplicates) > 3 else ""
            self.log(f"• Schon in der Liste: {names}{more}")
        if result.added:
            self.log(f"+ {len(result.added)} Datei(en) hinzugefügt")
        self._update_actions()
        return result

    def browse_files(self) -> None:
        start = self.settings.value("last_input_dir", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(
            self, "IFC-Dateien hinzufügen", str(start), "IFC-Dateien (*.ifc *.IFC);;Alle Dateien (*)"
        )
        if files:
            self.settings.setValue("last_input_dir", str(Path(files[0]).parent))
            self.add_paths(files)

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
        if item.status is Status.DONE:
            cell.setForeground(DONE_COLOR)
            tooltip = str(item.output)
        elif item.status is Status.FAILED:
            cell.setForeground(ERROR_COLOR)
            tooltip = item.error
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
        out_dir = None if self.beside_check.isChecked() else self.output_dir
        if out_dir is not None:
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, APP_NAME, f"Ausgabeordner kann nicht angelegt werden:\n{exc}")
                return
        rows = self.queue.prepare_run()
        for row in rows:
            self._refresh_row(row)
        self._run_rows, self._run_done, self._run_failed = rows, 0, 0

        fmt = self.fmt
        target = "neben den IFC-Dateien" if out_dir is None else str(out_dir)
        geometry = self.geometry
        label = f"3DM ({GEOMETRY_INFO[geometry][0].split(' (')[0]})" if fmt == "3dm" else fmt.upper()
        self.log(f"▶ {len(rows)} Datei(en) → {label}, Ziel: {target}")

        jobs = [(row, self.queue[row].path) for row in rows]
        self._worker = ConversionWorker(jobs, fmt, out_dir, geometry=geometry)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_warning.connect(self._on_file_warning)
        self._worker.file_progress.connect(self._on_file_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.file_failed.connect(self._on_file_failed)
        self._worker.file_cancelled.connect(self._on_file_cancelled)
        self._worker.finished.connect(self._on_finished)
        # quit() is thread-safe; a direct call lets _on_finished wait for the thread without deadlocking.
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._thread.finished.connect(self._worker.deleteLater)

        self._update_overall(0)
        self._update_actions()
        self.status_label.setText("Konvertierung läuft …")
        self._started_at = time.monotonic()
        self._thread.start()

    def cancel_conversion(self) -> None:
        if self._worker is not None and not self._worker.cancelled:
            self._worker.cancel()
            self.cancel_button.setEnabled(False)
            current = self.queue[self._current_row] if self._current_row is not None else None
            if current and current.status is Status.RUNNING and current.progress == READING:
                # convert() cannot be interrupted while ifcopenshell reads the file.
                self.status_label.setText("Wird abgebrochen, sobald die IFC-Datei fertig gelesen ist …")
            else:
                self.status_label.setText("Wird abgebrochen …")
            self.log("■ Abbruch angefordert")

    def _on_file_started(self, row: int, target: Path) -> None:
        item = self.queue[row]
        item.status, item.progress = Status.RUNNING, READING
        self._current_row = row
        self._refresh_row(row)
        self.table.scrollToItem(self.table.item(row, 0))
        self._update_overall(0)
        # Reading gives no progress at all, so show a busy bar to make clear the app is not frozen.
        self.overall_progress.setRange(0, 0)
        self._set_activity(f"IFC wird gelesen ({format_size(item.size)}) – kann einige Minuten dauern …")
        self.log(f"… {item.path.name} ({format_size(item.size)}) → {target.name}")

    def _on_file_warning(self, row: int, message: str) -> None:
        item = self.queue[row]
        item.warning = message
        self._refresh_row(row)
        self.log(f"⚠ {message}")

    def _set_activity(self, text: str) -> None:
        if self._worker is not None and not self._worker.cancelled:
            self.status_label.setText(text)

    def _on_file_progress(self, row: int, percent: int) -> None:
        item = self.queue[row]
        if item.status is not Status.RUNNING:
            return
        if item.progress == READING:
            self._set_activity(f"{item.path.name} wird umgewandelt …")
        item.progress = percent
        self._refresh_row(row)
        self._update_overall(percent)

    def _on_file_done(self, row: int, output: Path, elements: int) -> None:
        item = self.queue[row]
        item.status, item.progress, item.output, item.elements = Status.DONE, 100, output, elements
        self._refresh_row(row)
        self._run_done += 1
        self._last_output_dir = output.parent
        self._update_overall(0)
        self.log(f"✓ {item.path.name} → {output}  ({elements} Bauteile)")

    def _on_file_failed(self, row: int, message: str) -> None:
        item = self.queue[row]
        item.status, item.error = Status.FAILED, message
        self._refresh_row(row)
        self._run_failed += 1
        self._update_overall(0)
        self.log(f"✗ Fehler bei {item.path.name}: {message}")

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
        self._current_row = None

        seconds = time.monotonic() - self._started_at
        summary = f"{self._run_done} von {len(self._run_rows)} Datei(en) fertig"
        if self._run_failed:
            summary += f", {self._run_failed} mit Fehler"
        if cancelled:
            summary += " – abgebrochen"
        summary += f" ({seconds:.1f} s)".replace(".", ",")
        self.status_label.setText(("Abgebrochen" if cancelled else "Fertig") + f" nach {seconds:.1f} s".replace(".", ","))
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setFormat(summary.split(" (")[0])
        if not cancelled:
            self.overall_progress.setValue(100)
        self.log(f"■ {summary}")
        self._update_actions()
        self.conversion_finished.emit(cancelled)

    def _update_overall(self, current_percent: int) -> None:
        total = len(self._run_rows) or 1
        finished = self._run_done + self._run_failed
        self.overall_progress.setRange(0, 100)
        value = int((finished * 100 + (current_percent if finished < total else 0)) / total)
        self.overall_progress.setValue(min(100, value))
        self.overall_progress.setFormat(f"{finished} / {total} Dateien – %p %")

    # --------------------------------------------------------------- helpers

    def open_output_dir(self) -> None:
        folder = self._last_output_dir or self.output_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

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
        for button in self.format_buttons.values():
            button.setEnabled(not running)
        self.geometry_box.setEnabled(not running and self.fmt == "3dm")
        self.beside_check.setEnabled(not running)
        beside = self.beside_check.isChecked()
        self.output_edit.setEnabled(not running and not beside)
        self.output_button.setEnabled(not running and not beside)
        count = len(self.queue)
        self.count_label.setText(f"{count} Datei" if count == 1 else f"{count} Dateien")
        if not running and not self.status_label.text():
            self.status_label.setText("Dateien hinzufügen und auf „Konvertieren“ klicken.")

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

    def closeEvent(self, event):
        if self.is_running:
            answer = QMessageBox.question(
                self, APP_NAME, "Die Konvertierung läuft noch. Abbrechen und beenden?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.cancel()
            if self._thread is not None:
                self._thread.quit()
                self._thread.wait()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    # Files passed on the command line (e.g. dropped onto the launcher) are added right away.
    paths = app.arguments()[1:] if argv is None else argv
    if paths:
        window.add_paths(paths)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
