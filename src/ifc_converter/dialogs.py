"""The app's dialogs: About, Settings (with the Preferences they edit) and the error dialog."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices, QFont, QFontDatabase, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ifc_converter import __version__
from ifc_converter import app as app_info
from ifc_converter.app import APP_NAME, LICENSES, REPOSITORY, component_versions
from ifc_converter.converter import DEFAULT_KERNEL, KERNELS
from ifc_converter.interactive import resource_text, split_label
from ifc_converter.process import auto_threads, cpu_count

RESOURCES = Path(__file__).resolve().parent / "resources"

# Geometry kernel -> (label, hint) in the settings.
KERNEL_INFO = {
    "accurate": (
        "Genau (empfohlen)",
        "Jedes Bauteil vollständig und bei jedem Lauf gleich; nur große Dreiecksnetze (Gelände) nimmt der "
        "schnelle Kern, der sie unverändert übernimmt.",
    ),
    "hybrid": (
        "Schnell",
        "3- bis 13-mal schneller, kann aber bei einzelnen Bauteilen Flächen weglassen oder doppelt erzeugen.",
    ),
    "opencascade": (
        "Nur OpenCASCADE",
        "Alles mit OpenCASCADE, auch Geländemodelle: dort sehr langsam (über 20 Minuten für ein großes Gelände).",
    ),
}


def app_icon() -> QIcon:
    icon = QIcon()
    for name in ("icon.png", "icon.ico"):
        path = RESOURCES / name
        if path.is_file():
            icon.addFile(str(path))
            break
    return icon


def open_path(path: Path) -> bool:
    """Open a file or folder with the program the system uses for it (Explorer, an editor …)."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_log() -> bool:
    """Open the log file, or its folder if nothing has been logged yet."""
    path = app_info.log_path()
    return open_path(path if path.is_file() else app_info.log_dir())


# Name of the anonymised copy of the log, saved on the desktop by default.
ANONYMIZED_LOG_NAME = "ifc-converter-log-anonym.txt"
ANONYMIZE_HINT = (
    "Ersetzt Benutzer- und Rechnernamen, Server und Freigaben von Netzlaufwerken, Ordnernamen "
    "(<Ordner>) und Dateinamen (Datei-1.ifc, Datei-1.3dm …) und lässt Bauteilnamen weg. Erhalten bleiben "
    "IFC-Klasse und GlobalId, Zeiten, Größen, Versionen und Fehlermeldungen."
)


def save_anonymized_log(parent: QWidget | None = None) -> Path | None:
    """Ask where to save an anonymised copy of the whole log, save it and offer to open its folder."""
    from ifc_converter.interactive import desktop_dir

    if not app_info.log_files():
        QMessageBox.information(parent, APP_NAME, f"Es gibt noch keine Logdatei in {app_info.log_dir()}.")
        return None
    path, _ = QFileDialog.getSaveFileName(
        parent, "Anonymisierte Logdatei speichern", str(desktop_dir() / ANONYMIZED_LOG_NAME),
        "Textdateien (*.txt);;Alle Dateien (*)",
    )
    if not path:
        return None
    try:
        target = app_info.write_anonymized_log(Path(path))
    except OSError as exc:
        QMessageBox.warning(parent, APP_NAME, f"Die anonymisierte Logdatei konnte nicht gespeichert werden:\n{exc}")
        return None
    answer = QMessageBox.question(
        parent, APP_NAME,
        f"Die anonymisierte Logdatei wurde gespeichert:\n{target}\n\n{ANONYMIZE_HINT}\n\n"
        "Bitte vor dem Versenden kurz durchsehen. Ordner jetzt öffnen?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes,
    )
    if answer == QMessageBox.StandardButton.Yes:
        open_path(target.parent)
    return target


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Hint")
    palette = label.palette()
    palette.setColor(label.foregroundRole(), palette.color(palette.ColorRole.PlaceholderText))
    label.setPalette(palette)
    return label


def _selectable(text: str) -> QLabel:
    label = QLabel(text)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setWordWrap(True)
    return label


class _Dialog(QDialog):
    """A dialog that is always as tall as its word-wrapped labels need at its current width.

    Qt sizes word-wrapped labels for an assumed width, so without this the dialog comes out too short
    and squeezes its rows together.
    """

    def _fit(self) -> None:
        layout = self.layout()
        if layout is None or not layout.hasHeightForWidth():
            return
        needed = layout.totalHeightForWidth(self.width())
        if needed > 0 and needed != self.minimumHeight():
            self.setMinimumHeight(needed)
            if self.height() < needed:
                self.resize(self.width(), needed)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


# ------------------------------------------------------------------- preferences


@dataclass
class Preferences:
    """The advanced settings, as stored in QSettings."""

    threads: int = 0  # 0 means automatic: auto_threads()
    kernel: str = DEFAULT_KERNEL
    low_priority: bool = True
    open_output: bool = False  # open the output folder after a batch
    anonymize_log: bool = False  # write the log file without personal data (see anonymize)

    @classmethod
    def load(cls, settings: QSettings) -> Preferences:
        defaults = cls()
        try:
            threads = int(settings.value("threads", defaults.threads))
        except (TypeError, ValueError):
            threads = defaults.threads
        kernel = str(settings.value("kernel_strategy", "")).lower()
        if not kernel:
            # Earlier versions stored "hybrid" (then the default, saved along with any other setting)
            # under "kernel": only an explicit choice of OpenCASCADE is carried over.
            kernel = "opencascade" if str(settings.value("kernel", "")).lower() == "opencascade" else defaults.kernel
        return cls(
            # Settings may come from a machine with more cores.
            threads=max(0, min(threads, cpu_count())),
            kernel=kernel if kernel in KERNELS else defaults.kernel,
            low_priority=settings.value("low_priority", defaults.low_priority, type=bool),
            open_output=settings.value("open_output_dir", defaults.open_output, type=bool),
            anonymize_log=settings.value("anonymize_log", defaults.anonymize_log, type=bool),
        )

    def save(self, settings: QSettings) -> None:
        settings.setValue("threads", self.threads)
        settings.setValue("kernel_strategy", self.kernel)
        settings.setValue("low_priority", self.low_priority)
        settings.setValue("open_output_dir", self.open_output)
        settings.setValue("anonymize_log", self.anonymize_log)
        settings.sync()

    @property
    def effective_threads(self) -> int:
        return self.threads or auto_threads()


# ---------------------------------------------------------------------- settings


class SettingsDialog(_Dialog):
    """Einstellungen: threads, priority, geometry kernel and what happens with the output folder."""

    def __init__(self, preferences: Preferences, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        performance = QGroupBox("Leistung")
        form = QVBoxLayout(performance)
        row = QHBoxLayout()
        row.addWidget(QLabel("Max. Threads:"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(0, cpu_count())
        self.threads_spin.setSpecialValueText(f"Automatisch ({auto_threads()})")
        self.threads_spin.setMinimumWidth(170)
        row.addWidget(self.threads_spin)
        row.addStretch()
        form.addLayout(row)
        form.addWidget(_hint(
            "So viele Prozessorkerne berechnen die Geometrie gleichzeitig. Weniger Threads bremsen andere "
            "Programme weniger, die Umwandlung dauert dafür länger. "
            f"„Automatisch“ nutzt auf diesem PC bis zu {auto_threads()} seiner {cpu_count()} logischen Kerne und "
            "lässt den Rest für andere Programme frei. Jeder Thread kann bei großen Bauteilen bis ca. 1 GB RAM "
            "brauchen; bei wenig freiem Speicher werden automatisch weniger genutzt."
        ))
        self.threads_usage = _hint("")
        form.addWidget(self.threads_usage)
        self.priority_check = QCheckBox("Mit niedriger Priorität umwandeln (empfohlen)")
        form.addWidget(self.priority_check)
        form.addWidget(_hint(
            "Die Umwandlung läuft mit der Windows-Priorität „Niedriger als normal“: Programme wie Rhino oder "
            "Revit haben immer Vorrang und bleiben flüssig bedienbar, die Umwandlung nutzt nur die Rechenzeit, "
            "die sie übrig lassen. Ohne diese Einstellung konkurriert sie gleichberechtigt mit ihnen."
        ))
        self.threads_spin.valueChanged.connect(self._show_usage)
        self.priority_check.toggled.connect(self._show_usage)
        layout.addWidget(performance)

        kernel_box = QGroupBox("Geometriekern")
        kernel_layout = QVBoxLayout(kernel_box)
        self.kernel_group = QButtonGroup(self)
        self.kernel_buttons: dict[str, QRadioButton] = {}
        for kernel, (label, hint) in KERNEL_INFO.items():
            button = QRadioButton(label)
            self.kernel_group.addButton(button)
            self.kernel_buttons[kernel] = button
            kernel_layout.addWidget(button)
            kernel_layout.addWidget(_hint(hint))
        layout.addWidget(kernel_box)

        output_box = QGroupBox("Ausgabe")
        output_layout = QVBoxLayout(output_box)
        self.open_output_check = QCheckBox("Ausgabeordner nach dem Konvertieren öffnen")
        output_layout.addWidget(self.open_output_check)
        output_layout.addWidget(_hint(
            "Vorhandene Dateien werden nie überschrieben – gibt es den Namen schon, wird (2), (3) … "
            "angehängt. Die IFC-Dateien selbst werden nie verändert."
        ))
        layout.addWidget(output_box)

        storage = QGroupBox("Speicherorte")
        storage_form = QFormLayout(storage)
        storage_form.addRow("Einstellungen:", _selectable(str(app_info.settings_path())))
        storage_form.addRow("Protokoll:", _selectable(str(app_info.log_dir())))
        open_log_button = QPushButton("Logdatei öffnen")
        open_log_button.clicked.connect(open_log)
        save_log_button = QPushButton("Anonymisiert speichern…")
        save_log_button.clicked.connect(lambda: save_anonymized_log(self))
        button_row = QHBoxLayout()
        button_row.addWidget(open_log_button)
        button_row.addWidget(save_log_button)
        button_row.addStretch()
        storage_form.addRow("", button_row)
        self.anonymize_check = QCheckBox("Logdatei anonymisieren")
        self.anonymize_check.setToolTip(ANONYMIZE_HINT)
        storage_form.addRow("", self.anonymize_check)
        storage_form.addRow("", _hint(
            "Die Logdatei bleibt auf diesem PC; nichts wird automatisch versendet. Eingeschaltet, enthält sie "
            "ab jetzt keine Benutzer-, Rechner-, Server-, Ordner-, Datei- und Bauteilnamen mehr."
        ))
        layout.addWidget(storage)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        for which, text in (
            (QDialogButtonBox.StandardButton.Ok, "OK"),
            (QDialogButtonBox.StandardButton.Cancel, "Abbrechen"),
            (QDialogButtonBox.StandardButton.RestoreDefaults, "Standardwerte"),
        ):
            self.buttons.button(which).setText(text)
            self.buttons.button(which).setIcon(QIcon())  # some Linux styles add icons; Windows has none
        self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self.set_preferences(Preferences())
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.set_preferences(preferences)

    def _show_usage(self) -> None:
        """What a conversion takes of the PC with the settings shown (as at the start of a conversion)."""
        threads = self.threads_spin.value() or auto_threads()
        self.threads_usage.setText(f"Eine Umwandlung nutzt damit {resource_text(threads, self.priority_check.isChecked())}.")

    def set_preferences(self, preferences: Preferences) -> None:
        self.threads_spin.setValue(preferences.threads)
        self.priority_check.setChecked(preferences.low_priority)
        self._show_usage()
        self.kernel_buttons.get(preferences.kernel, self.kernel_buttons[DEFAULT_KERNEL]).setChecked(True)
        self.open_output_check.setChecked(preferences.open_output)
        self.anonymize_check.setChecked(preferences.anonymize_log)

    def preferences(self) -> Preferences:
        kernel = next(k for k, button in self.kernel_buttons.items() if button.isChecked())
        return Preferences(
            threads=self.threads_spin.value(),
            kernel=kernel,
            low_priority=self.priority_check.isChecked(),
            open_output=self.open_output_check.isChecked(),
            anonymize_log=self.anonymize_check.isChecked(),
        )


# ------------------------------------------------------------------------- about


def version_report() -> str:
    """The component versions as plain text, for the clipboard."""
    return "\n".join(f"{name}: {version}" for name, version in component_versions().items())


class AboutDialog(_Dialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Über {APP_NAME}")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(16)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(80, 80))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        header.addWidget(icon)
        title_box = QVBoxLayout()
        title = QLabel(APP_NAME)
        title_font = title.font()
        title_font.setPointSizeF(title_font.pointSizeF() * 1.6)
        title_font.setWeight(QFont.Weight.DemiBold)
        title.setFont(title_font)
        title_box.addWidget(title)
        title_box.addWidget(_selectable(f"Version {__version__}"))
        title_box.addWidget(_hint(
            "Wandelt IFC-Gebäudemodelle in Rhino-Dateien (3DM), GLB und OBJ um. Läuft vollständig lokal: "
            "keine Internetverbindung, keine Telemetrie, keine automatischen Updates."
        ))
        header.addLayout(title_box, stretch=1)
        layout.addLayout(header)

        versions = QGroupBox("Versionen")
        versions_form = QFormLayout(versions)
        for name, version in component_versions().items():
            if name != APP_NAME:
                versions_form.addRow(f"{name}:", _selectable(version))
        layout.addWidget(versions)

        licenses = QGroupBox("Open-Source-Komponenten")
        licenses_form = QFormLayout(licenses)
        for name, license_name in LICENSES.items():
            licenses_form.addRow(f"{name}:", QLabel(license_name))
        licenses_form.addRow(_hint(
            "Die Bibliotheken sind unverändert enthalten. Die vollständigen Lizenztexte stehen im "
            "Programmordner in THIRD-PARTY-NOTICES.txt und im Ordner „licenses“."
        ))
        layout.addWidget(licenses)

        layout.addWidget(_selectable(f"Quellcode: {REPOSITORY}"))
        layout.addWidget(_selectable(f"Protokoll: {app_info.log_dir()}"))

        buttons = QDialogButtonBox()
        self.copy_button = buttons.addButton("Versionsinfo kopieren", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.clicked.connect(self._copy)
        close = buttons.addButton("Schließen", QDialogButtonBox.ButtonRole.AcceptRole)
        close.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(version_report())
        self.copy_button.setText("Kopiert ✓")


# ------------------------------------------------------------------------- error


class ErrorDialog(_Dialog):
    """Shown for an unexpected error instead of the app silently dying or ignoring it."""

    def __init__(self, summary: str, details: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.details = details
        self.setWindowTitle(f"{APP_NAME} – Unerwarteter Fehler")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical).pixmap(40, 40))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        header.addWidget(icon)
        text = QLabel(
            "<b>Es ist ein unerwarteter Fehler aufgetreten.</b><br>"
            "Das Programm läuft weiter. Falls etwas nicht mehr funktioniert, bitte neu starten.<br>"
            "Zum Melden des Problems die Details kopieren und mitschicken."
        )
        text.setWordWrap(True)
        header.addWidget(text, stretch=1)
        layout.addLayout(header)
        layout.addWidget(_selectable(summary))

        self.details_view = QPlainTextEdit(details)
        self.details_view.setReadOnly(True)
        self.details_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.details_view.setMinimumHeight(160)
        self.details_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.details_view, stretch=1)

        buttons = QDialogButtonBox()
        self.copy_button = buttons.addButton("Details kopieren", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.clicked.connect(self.copy_details)
        log_button = buttons.addButton("Logdatei öffnen", QDialogButtonBox.ButtonRole.ActionRole)
        log_button.clicked.connect(open_log)
        save_log_button = buttons.addButton("Anonymisiert speichern…", QDialogButtonBox.ButtonRole.ActionRole)
        save_log_button.setToolTip(ANONYMIZE_HINT)
        save_log_button.clicked.connect(lambda: save_anonymized_log(self))
        close = buttons.addButton("Schließen", QDialogButtonBox.ButtonRole.AcceptRole)
        close.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def copy_details(self) -> None:
        QGuiApplication.clipboard().setText(self.details)
        self.copy_button.setText("Kopiert ✓")


class ErrorReporter(QObject):
    """Shows an ErrorDialog for errors reported from any thread, one at a time.

    Meant as the ``report`` callback of app.install_exception_hooks(). Errors while a dialog is open are
    only logged (by the hook), so a failing timer cannot flood the screen with dialogs.
    """

    reported = Signal(str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.dialog: ErrorDialog | None = None
        # Emitted from any thread; the dialog is created in this object's (the GUI) thread.
        self.reported.connect(self._show, Qt.ConnectionType.QueuedConnection)

    def report(self, summary: str, details: str) -> None:
        self.reported.emit(summary, details)

    @Slot(str, str)
    def _show(self, summary: str, details: str) -> None:
        if self.dialog is not None:
            return
        self.dialog = ErrorDialog(summary, details, QApplication.activeWindow())
        self.dialog.finished.connect(self._closed)
        # Shown non-modal from the event loop, so an error inside a modal dialog does not nest loops.
        QTimer.singleShot(0, self.dialog.show)

    def _closed(self) -> None:
        if self.dialog is not None:
            self.dialog.deleteLater()
        self.dialog = None


# ----------------------------------------------------------------------- skipped

# The reasons in SkippedDialog, for ConversionResult.crashed and .no_geometry.
CRASHED_REASON = "Übersprungen (Geometriekern abgestürzt)"
NO_GEOMETRY_REASON = "Ohne Geometrie"
FIND_HINT = (
    "So finden Sie ein Bauteil im CAD-Programm: GlobalId kopieren und danach suchen – in ArchiCAD mit "
    "„Suchen & Auswählen“ (Strg+F) über die IFC-Eigenschaft GlobalId bzw. „Archicad IFC ID“, in Revit über "
    "den Parameter „IfcGUID“ (z. B. in einer Bauteilliste oder mit einem Filter), sonst in jedem IFC-Viewer."
)


class SkippedDialog(_Dialog):
    """The elements of one file that were not converted, with class, GlobalId and name, to copy.

    ``skipped`` is the number of elements without geometry; it can be larger than ``no_geometry`` when
    not all of them could be named.
    """

    COLUMNS = ("Grund", "Klasse", "GlobalId", "Name")

    def __init__(
        self, file_name: str, crashed: list[str], no_geometry: list[str], skipped: int = 0,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Übersprungene Bauteile – {file_name}")
        self.setMinimumSize(720, 420)
        layout = QVBoxLayout(self)

        counts = []
        if crashed:
            counts.append(f"{len(crashed)} übersprungen, weil der Geometriekern daran abstürzte oder hängen blieb")
        if no_geometry or skipped:
            counts.append(f"{max(skipped, len(no_geometry))} ohne Geometrie (nicht umwandelbar)")
        layout.addWidget(_selectable(f"<b>{html.escape(file_name)}</b>: " + "; ".join(counts) + "."))

        self.rows = [(CRASHED_REASON, *split_label(label)) for label in crashed]
        self.rows += [(NO_GEOMETRY_REASON, *split_label(label)) for label in no_geometry]
        self.table = QTableWidget(len(self.rows), len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        for row, values in enumerate(self.rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        copy = QAction("Kopieren", self.table)
        copy.setShortcut(QKeySequence.StandardKey.Copy)
        copy.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        copy.triggered.connect(self.copy_selection)
        self.table.addAction(copy)
        layout.addWidget(self.table, stretch=1)

        if skipped > len(no_geometry):
            layout.addWidget(_hint(
                f"{skipped - len(no_geometry)} weitere Bauteile ohne Geometrie ließen sich nicht einzeln benennen."
            ))
        layout.addWidget(_hint(
            "Markieren und Strg+C kopiert die gewählten Zeilen (Strg+A: alle), als Tabelle zum Einfügen in Excel "
            "oder eine E-Mail. " + FIND_HINT
        ))

        buttons = QDialogButtonBox()
        self.copy_button = buttons.addButton("Alles kopieren", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.clicked.connect(self.copy_all)
        close = buttons.addButton("Schließen", QDialogButtonBox.ButtonRole.RejectRole)
        close.setDefault(True)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _text(self, rows: list[tuple[str, ...]]) -> str:
        """Tab-separated with a header line: pastes as a table into Excel, readable as plain text."""
        return "\n".join("\t".join(values) for values in [self.COLUMNS, *rows]) + "\n"

    def copy_all(self) -> None:
        QGuiApplication.clipboard().setText(self._text(self.rows))
        self.copy_button.setText("Kopiert ✓")

    def copy_selection(self) -> None:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        if not rows:
            return
        values = [tuple(self.table.item(row, column).text() for column in range(len(self.COLUMNS))) for row in rows]
        QGuiApplication.clipboard().setText(self._text(values))
