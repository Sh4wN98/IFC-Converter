"""The app's dialogs: About, Settings (with the Preferences they edit) and the error dialog."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QSize, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSizePolicy,
    QStyle,
    QTabWidget,
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


def muted(label: QLabel) -> QLabel:
    """Grey text (the palette's placeholder colour) for secondary information, in the main window too."""
    palette = label.palette()
    colour = palette.color(QPalette.ColorRole.PlaceholderText)
    # Only the enabled groups, so a disabled hint still looks disabled.
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        palette.setColor(group, QPalette.ColorRole.WindowText, colour)
    label.setPalette(palette)
    return label


class ElidedLabel(QLabel):
    """A one-line label that shortens its text with "…" instead of growing or clipping.

    ``text()`` still returns the whole text (and the tooltip shows it when it is shortened), so the
    label never forces the window wider than the user made it: status lines, file names, info lines.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._full = text
        self.setToolTip("")
        super().setText(text)
        self.update()

    def text(self) -> str:
        return self._full

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(self.fontMetrics().horizontalAdvance("…") + 2, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        rect = self.contentsRect()
        elided = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, rect.width())
        if elided != self._full and self.toolTip() != self._full:
            self.setToolTip(self._full)
        elif elided == self._full and self.toolTip():
            self.setToolTip("")
        painter = QPainter(self)
        role = self.foregroundRole()
        painter.setPen(self.palette().color(QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled, role))
        painter.drawText(rect, int(self.alignment()) | Qt.TextFlag.TextSingleLine, elided)


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
    blocks: bool = False  # Rhino: type geometry placed several times as blocks (convert(blocks=...))

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
            blocks=settings.value("rhino_blocks", defaults.blocks, type=bool),
        )

    def save(self, settings: QSettings) -> None:
        settings.setValue("threads", self.threads)
        settings.setValue("kernel_strategy", self.kernel)
        settings.setValue("low_priority", self.low_priority)
        settings.setValue("open_output_dir", self.open_output)
        settings.setValue("anonymize_log", self.anonymize_log)
        settings.setValue("rhino_blocks", self.blocks)
        settings.sync()

    @property
    def effective_threads(self) -> int:
        return self.threads or auto_threads()


# ---------------------------------------------------------------------- settings


class SettingsDialog(QDialog):
    """Einstellungen: threads, priority, geometry kernel and what happens with the output folder.

    One tab per topic, so the dialog stays small enough for a laptop screen at 150 % scaling.
    """

    def __init__(self, preferences: Preferences, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumSize(600, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        layout.addWidget(self.tabs, stretch=1)
        self.tabs.addTab(self._performance_tab(), "Leistung")
        self.tabs.addTab(self._kernel_tab(), "Geometriekern")
        self.tabs.addTab(self._output_tab(), "Ausgabe")
        self.tabs.addTab(self._log_tab(), "Logdatei")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        for which, text, tooltip in (
            (QDialogButtonBox.StandardButton.Ok, "OK", "Einstellungen übernehmen und speichern"),
            (QDialogButtonBox.StandardButton.Cancel, "Abbrechen", "Änderungen verwerfen"),
            (QDialogButtonBox.StandardButton.RestoreDefaults, "Standardwerte", "Alle Einstellungen auf die Vorgaben zurücksetzen"),
        ):
            self.buttons.button(which).setText(text)
            self.buttons.button(which).setToolTip(tooltip)
            self.buttons.button(which).setIcon(QIcon())  # some Linux styles add icons; Windows has none
        self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self.set_preferences(Preferences())
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.set_preferences(preferences)

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        return page, layout

    def _performance_tab(self) -> QWidget:
        page, layout = self._page()
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Höchstens so viele Threads:"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(0, cpu_count())
        self.threads_spin.setSpecialValueText(f"Automatisch ({auto_threads()})")
        self.threads_spin.setMinimumWidth(170)
        self.threads_spin.setToolTip("0 bzw. „Automatisch“ lässt einige Kerne frei und nimmt bei wenig freiem RAM weniger.")
        row.addWidget(self.threads_spin)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(_hint(
            "So viele Prozessorkerne berechnen die Geometrie gleichzeitig. Weniger Threads bremsen andere "
            "Programme weniger, die Konvertierung dauert dafür länger. "
            f"„Automatisch“ nutzt bis zu {auto_threads()} der {cpu_count()} logischen Kerne dieses PCs (mit den "
            "Hilfsprozessen der Rhino-Ausgabe etwa die Hälfte) und bei wenig freiem RAM weniger; jeder Thread "
            "kann bei großen Bauteilen bis ca. 1 GB brauchen."
        ))
        layout.addSpacing(4)
        self.priority_check = QCheckBox("Mit niedriger Priorität konvertieren (empfohlen)")
        layout.addWidget(self.priority_check)
        layout.addWidget(_hint(
            "Die Konvertierung läuft mit der Windows-Priorität „Niedriger als normal“: Rhino, Revit & Co. haben "
            "Vorrang und bleiben flüssig bedienbar; die Konvertierung nutzt nur die Rechenzeit, die sie übrig "
            "lassen. Ohne diese Einstellung konkurriert sie gleichberechtigt mit ihnen."
        ))
        layout.addSpacing(4)
        self.threads_usage = _hint("")
        layout.addWidget(self.threads_usage)
        layout.addStretch()
        self.threads_spin.valueChanged.connect(self._show_usage)
        self.priority_check.toggled.connect(self._show_usage)
        return page

    def _kernel_tab(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(_hint(
            "Womit die Geometrie der Bauteile berechnet wird. Gilt für alle Zielformate."
        ))
        layout.addSpacing(4)
        self.kernel_group = QButtonGroup(self)
        self.kernel_buttons: dict[str, QRadioButton] = {}
        for kernel, (label, hint) in KERNEL_INFO.items():
            button = QRadioButton(label)
            button.setToolTip(hint)
            self.kernel_group.addButton(button)
            self.kernel_buttons[kernel] = button
            layout.addWidget(button)
            description = _hint(hint)
            description.setContentsMargins(22, 0, 0, 6)
            layout.addWidget(description)
        layout.addStretch()
        return page

    def _output_tab(self) -> QWidget:
        page, layout = self._page()
        self.open_output_check = QCheckBox("Ausgabeordner nach der Konvertierung öffnen")
        self.open_output_check.setToolTip("Öffnet den Ordner im Explorer, sobald alle Dateien konvertiert sind.")
        layout.addWidget(self.open_output_check)
        layout.addWidget(_hint(
            "Vorhandene Dateien werden nie überschrieben – gibt es den Namen schon, wird (2), (3) … "
            "angehängt. Die IFC-Dateien selbst werden nie verändert."
        ))
        layout.addSpacing(8)
        rhino = QLabel("Rhino (.3dm)")
        rhino_font = rhino.font()
        rhino_font.setWeight(QFont.Weight.DemiBold)
        rhino.setFont(rhino_font)
        layout.addWidget(rhino)
        self.blocks_check = QCheckBox("Gleiche Bauteile als Blöcke (kleinere Datei)")
        self.blocks_check.setToolTip(
            "Bauteile mit derselben Typ-Geometrie (Fenster, Türen, Möbel …) werden Instanzen eines Rhino-Blocks.\n"
            "Die Datei wird kleiner, aber Blockinstanzen verhalten sich anders als normale Objekte:\n"
            "Zum Bearbeiten der Geometrie muss eine Instanz erst aufgelöst werden (_Explode).\n"
            "Benutzertexte, Layer und Farbe stehen an der Instanz."
        )
        layout.addWidget(self.blocks_check)
        layout.addWidget(_hint(
            "Typ-Geometrie, die mehrere Bauteile teilen (Fenster, Türen, Möbel …), wird einmal als Block gespeichert "
            "und je Bauteil als Instanz eingefügt: Datei 20–45 % kleiner. Zum Bearbeiten in Rhino muss eine "
            "Blockinstanz erst aufgelöst werden (_Explode)."
        ))
        layout.addStretch()
        return page

    def _log_tab(self) -> QWidget:
        page, layout = self._page()
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.addRow("Logdatei:", _selectable(str(app_info.log_dir())))
        form.addRow("Einstellungen:", _selectable(str(app_info.settings_path())))
        layout.addLayout(form)
        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        open_log_button = QPushButton("Logdatei öffnen")
        open_log_button.setToolTip("Öffnet die aktuelle Logdatei im Standardprogramm für Textdateien.")
        open_log_button.clicked.connect(open_log)
        save_log_button = QPushButton("Anonymisiert speichern…")
        save_log_button.setToolTip(ANONYMIZE_HINT)
        save_log_button.clicked.connect(lambda: save_anonymized_log(self))
        button_row.addWidget(open_log_button)
        button_row.addWidget(save_log_button)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addSpacing(8)
        self.anonymize_check = QCheckBox("Logdatei anonymisieren")
        self.anonymize_check.setToolTip(ANONYMIZE_HINT)
        layout.addWidget(self.anonymize_check)
        layout.addWidget(_hint(
            "Die Logdatei bleibt auf diesem PC; nichts wird automatisch versendet. Eingeschaltet, enthält sie "
            "ab jetzt keine Benutzer-, Rechner-, Server-, Ordner-, Datei- und Bauteilnamen mehr."
        ))
        layout.addStretch()
        return page

    def _show_usage(self) -> None:
        """What a conversion takes of the PC with the settings shown (as at the start of a conversion)."""
        threads = self.threads_spin.value() or auto_threads()
        self.threads_usage.setText(
            f"Eine Konvertierung nutzt damit {resource_text(threads, self.priority_check.isChecked())}."
        )

    def set_preferences(self, preferences: Preferences) -> None:
        self.threads_spin.setValue(preferences.threads)
        self.priority_check.setChecked(preferences.low_priority)
        self._show_usage()
        self.kernel_buttons.get(preferences.kernel, self.kernel_buttons[DEFAULT_KERNEL]).setChecked(True)
        self.open_output_check.setChecked(preferences.open_output)
        self.anonymize_check.setChecked(preferences.anonymize_log)
        self.blocks_check.setChecked(preferences.blocks)

    def preferences(self) -> Preferences:
        kernel = next(k for k, button in self.kernel_buttons.items() if button.isChecked())
        return Preferences(
            threads=self.threads_spin.value(),
            kernel=kernel,
            low_priority=self.priority_check.isChecked(),
            open_output=self.open_output_check.isChecked(),
            anonymize_log=self.anonymize_check.isChecked(),
            blocks=self.blocks_check.isChecked(),
        )


# ------------------------------------------------------------------------- about


def version_report() -> str:
    """The component versions as plain text, for the clipboard."""
    return "\n".join(f"{name}: {version}" for name, version in component_versions().items())


def _licence_of(component: str) -> str:
    """The licence of a component of component_versions(), e.g. "Qt" from the "Qt 6 / PySide6" entry."""
    for name, licence in LICENSES.items():
        if component == name or component in [part.strip() for part in name.split("/")] or component in name.split():
            return licence
    return ""


class AboutDialog(_Dialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Über {APP_NAME}")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(16)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(72, 72))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        header.addWidget(icon)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(APP_NAME)
        title_font = title.font()
        title_font.setPointSizeF(title_font.pointSizeF() * 1.6)
        title_font.setWeight(QFont.Weight.DemiBold)
        title.setFont(title_font)
        title_box.addWidget(title)
        title_box.addWidget(_selectable(f"Version {__version__}"))
        title_box.addSpacing(4)
        title_box.addWidget(_hint(
            "Konvertiert IFC-Gebäudemodelle in Rhino-Dateien (3DM), GLB und OBJ. Läuft vollständig lokal: "
            "keine Internetverbindung, keine Telemetrie, keine automatischen Updates."
        ))
        header.addLayout(title_box, stretch=1)
        layout.addLayout(header)

        components = QGroupBox("Komponenten")
        grid = QGridLayout(components)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(4)
        for column, heading in enumerate(("Komponente", "Version", "Lizenz")):
            label = _hint(heading)
            label.setWordWrap(False)
            grid.addWidget(label, 0, column)
        rows = [(name, version, _licence_of(name)) for name, version in component_versions().items() if name != APP_NAME]
        listed = {name for name, _version, _licence in rows}
        rows += [(name, "–", licence) for name, licence in LICENSES.items()
                 if not any(part.strip() in listed or part.strip() == name for part in name.split("/"))]
        rows.sort(key=lambda row: row[0] == "System")  # the operating system last, after the libraries
        for row, (name, version, licence) in enumerate(rows, start=1):
            grid.addWidget(QLabel(name), row, 0)
            grid.addWidget(_selectable(version), row, 1)
            grid.addWidget(QLabel(licence), row, 2)
        grid.setColumnStretch(1, 1)
        note = _hint(
            "Die Bibliotheken sind unverändert enthalten. Die vollständigen Lizenztexte stehen im "
            "Programmordner in THIRD-PARTY-NOTICES.txt und im Ordner „licenses“."
        )
        grid.addWidget(note, len(rows) + 1, 0, 1, 3)
        layout.addWidget(components)

        links = QFormLayout()
        links.setHorizontalSpacing(12)
        links.setVerticalSpacing(4)
        links.addRow("Quellcode:", _selectable(REPOSITORY))
        links.addRow("Logdatei:", _selectable(str(app_info.log_dir())))
        layout.addLayout(links)

        buttons = QDialogButtonBox()
        self.copy_button = buttons.addButton("Versionsinfo kopieren", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.setToolTip("Kopiert Programm- und Komponentenversionen als Text, z. B. für eine Fehlermeldung.")
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
        self.setMinimumWidth(700)  # four buttons in a row
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)
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
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        counts = []
        if crashed:
            counts.append(f"{len(crashed)} übersprungen, weil der Geometriekern daran abstürzte oder hängen blieb")
        if no_geometry or skipped:
            counts.append(f"{max(skipped, len(no_geometry))} ohne Geometrie (nicht konvertierbar)")
        layout.addWidget(_selectable(f"<b>{html.escape(file_name)}</b>: " + "; ".join(counts) + "."))

        self.rows = [(CRASHED_REASON, *split_label(label)) for label in crashed]
        self.rows += [(NO_GEOMETRY_REASON, *split_label(label)) for label in no_geometry]
        self.table = QTableWidget(len(self.rows), len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
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
        self.copy_button.setToolTip("Kopiert die ganze Tabelle, zum Einfügen in Excel oder eine E-Mail.")
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
