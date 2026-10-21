"""The app's dialogs: About, Settings (with the Preferences they edit) and the error dialog."""

from __future__ import annotations

import html
from collections.abc import Callable, Iterator, Mapping
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
from ifc_converter.i18n import tr
from ifc_converter.interactive import inside_text, resource_text, split_label
from ifc_converter.process import auto_threads, cpu_count

RESOURCES = Path(__file__).resolve().parent / "resources"



class _KernelInfo(Mapping[str, tuple[str, str]]):
    """Geometry kernel -> (label, hint) in the settings, translated whenever it is read (see i18n)."""

    _ENTRIES: dict[str, Callable[[], tuple[str, str]]] = {
        "accurate": lambda: (
            tr("Accurate (recommended)"),
            tr("Every element complete and the same on every run; only large triangle meshes (terrain) go to the "
               "fast kernel, which takes them over unchanged."),
        ),
        "hybrid": lambda: (
            tr("Fast"),
            tr("3 to 13 times faster, but may drop or duplicate faces of some elements."),
        ),
        "opencascade": lambda: (
            tr("OpenCASCADE only"),
            tr("Everything with OpenCASCADE, terrain models too: very slow there (over 20 minutes for a large "
               "terrain)."),
        ),
    }

    def __getitem__(self, kernel: str) -> tuple[str, str]:
        return self._ENTRIES[kernel]()

    def __iter__(self) -> Iterator[str]:
        return iter(self._ENTRIES)

    def __len__(self) -> int:
        return len(self._ENTRIES)


KERNEL_INFO = _KernelInfo()


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


def anonymize_hint() -> str:
    """What the anonymised log leaves out and what it keeps (see anonymize)."""
    return tr(
        "Replaces user and computer names, servers and shares of network drives, folder names (<folder>) and "
        "file names (File-1.ifc, File-1.3dm …) and leaves out element names. IFC class and GlobalId, times, "
        "sizes, versions and error messages are kept."
    )


def save_anonymized_log(parent: QWidget | None = None) -> Path | None:
    """Ask where to save an anonymised copy of the whole log, save it and offer to open its folder."""
    from ifc_converter.interactive import desktop_dir

    if not app_info.log_files():
        QMessageBox.information(
            parent, APP_NAME, tr("There is no log file yet in {folder}.", folder=app_info.log_dir()),
        )
        return None
    path, _ = QFileDialog.getSaveFileName(
        parent, tr("Save anonymised log file"), str(desktop_dir() / ANONYMIZED_LOG_NAME),
        tr("Text files (*.txt);;All files (*)"),
    )
    if not path:
        return None
    try:
        target = app_info.write_anonymized_log(Path(path))
    except OSError as exc:
        QMessageBox.warning(
            parent, APP_NAME, tr("The anonymised log file could not be saved:\n{error}", error=exc),
        )
        return None
    answer = QMessageBox.question(
        parent, APP_NAME,
        tr("The anonymised log file has been saved:\n{path}\n\n{hint}\n\n"
           "Please look through it briefly before sending. Open the folder now?",
           path=target, hint=anonymize_hint()),
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
        self.setWindowTitle(tr("Settings"))
        self.setMinimumSize(600, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        layout.addWidget(self.tabs, stretch=1)
        self.tabs.addTab(self._performance_tab(), tr("Performance"))
        self.tabs.addTab(self._kernel_tab(), tr("Geometry kernel"))
        self.tabs.addTab(self._output_tab(), tr("Output"))
        self.tabs.addTab(self._log_tab(), tr("Log file"))

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        for which, text, tooltip in (
            (QDialogButtonBox.StandardButton.Ok, tr("OK"), tr("Apply and save the settings")),
            (QDialogButtonBox.StandardButton.Cancel, tr("Cancel"), tr("Discard changes")),
            (QDialogButtonBox.StandardButton.RestoreDefaults, tr("Defaults"), tr("Reset all settings to their defaults")),
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
        row.addWidget(QLabel(tr("At most this many threads:")))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(0, cpu_count())
        self.threads_spin.setSpecialValueText(tr("Automatic ({threads})", threads=auto_threads()))
        self.threads_spin.setMinimumWidth(170)
        self.threads_spin.setToolTip(tr("0 or “Automatic” leaves some cores free and takes fewer when little RAM is free."))
        row.addWidget(self.threads_spin)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(_hint(tr(
            "This many processor cores compute the geometry at the same time. Fewer threads slow other programs "
            "down less, but the conversion takes longer. “Automatic” uses up to {threads} of the {cores} logical "
            "cores of this PC (about half, counting the helper processes of the Rhino output) and fewer when "
            "little RAM is free; each thread can need up to about 1 GB with large elements.",
            threads=auto_threads(), cores=cpu_count(),
        )))
        layout.addSpacing(4)
        self.priority_check = QCheckBox(tr("Convert at low priority (recommended)"))
        layout.addWidget(self.priority_check)
        layout.addWidget(_hint(tr(
            "The conversion runs at the Windows priority “Below normal”: Rhino, Revit and the like take precedence "
            "and stay responsive; the conversion only uses the processing time they leave over. Without this "
            "setting it competes with them on equal terms."
        )))
        layout.addSpacing(4)
        self.threads_usage = _hint("")
        layout.addWidget(self.threads_usage)
        layout.addStretch()
        self.threads_spin.valueChanged.connect(self._show_usage)
        self.priority_check.toggled.connect(self._show_usage)
        return page

    def _kernel_tab(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(_hint(tr(
            "What the geometry of the elements is computed with. Applies to all output formats."
        )))
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
        self.open_output_check = QCheckBox(tr("Open the output folder after the conversion"))
        self.open_output_check.setToolTip(tr("Opens the folder in Explorer as soon as all files are converted."))
        layout.addWidget(self.open_output_check)
        layout.addWidget(_hint(tr(
            "Existing files are never overwritten – if the name exists already, (2), (3) … is appended. "
            "The IFC files themselves are never changed."
        )))
        layout.addSpacing(8)
        rhino = QLabel("Rhino (.3dm)")
        rhino_font = rhino.font()
        rhino_font.setWeight(QFont.Weight.DemiBold)
        rhino.setFont(rhino_font)
        layout.addWidget(rhino)
        self.blocks_check = QCheckBox(tr("Identical elements as blocks (smaller file)"))
        self.blocks_check.setToolTip(tr(
            "Elements with the same type geometry (windows, doors, furniture …) become instances of a Rhino block.\n"
            "The file gets smaller, but block instances behave differently from normal objects:\n"
            "To edit the geometry, an instance has to be exploded first (_Explode).\n"
            "User texts, layer and colour are on the instance."
        ))
        layout.addWidget(self.blocks_check)
        layout.addWidget(_hint(tr(
            "Type geometry shared by several elements (windows, doors, furniture …) is stored once as a block and "
            "inserted as an instance per element: file 20–45 % smaller. To edit it in Rhino, a block instance "
            "has to be exploded first (_Explode)."
        )))
        layout.addStretch()
        return page

    def _log_tab(self) -> QWidget:
        page, layout = self._page()
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.addRow(tr("Log file:"), _selectable(str(app_info.log_dir())))
        form.addRow(tr("Settings:"), _selectable(str(app_info.settings_path())))
        layout.addLayout(form)
        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        open_log_button = QPushButton(tr("Open log file"))
        open_log_button.setToolTip(tr("Opens the current log file in the default program for text files."))
        open_log_button.clicked.connect(open_log)
        save_log_button = QPushButton(tr("Save anonymised…"))
        save_log_button.setToolTip(anonymize_hint())
        save_log_button.clicked.connect(lambda: save_anonymized_log(self))
        button_row.addWidget(open_log_button)
        button_row.addWidget(save_log_button)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addSpacing(8)
        self.anonymize_check = QCheckBox(tr("Anonymise log file"))
        self.anonymize_check.setToolTip(anonymize_hint())
        layout.addWidget(self.anonymize_check)
        layout.addWidget(_hint(tr(
            "The log file stays on this PC; nothing is sent automatically. Switched on, from now on it contains "
            "no user, computer, server, folder, file or element names."
        )))
        layout.addStretch()
        return page

    def _show_usage(self) -> None:
        """What a conversion takes of the PC with the settings shown (as at the start of a conversion)."""
        threads = self.threads_spin.value() or auto_threads()
        self.threads_usage.setText(tr(
            "With this, a conversion uses {resources}.",
            resources=resource_text(threads, self.priority_check.isChecked()),
        ))

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
        self.setWindowTitle(tr("About {app}", app=APP_NAME))
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
        title_box.addWidget(_selectable(tr("Version {version}", version=__version__)))
        title_box.addSpacing(4)
        title_box.addWidget(_hint(tr(
            "Converts IFC building models to Rhino files (3DM), GLB and OBJ. Runs entirely locally: "
            "no internet connection, no telemetry, no automatic updates."
        )))
        header.addLayout(title_box, stretch=1)
        layout.addLayout(header)

        components = QGroupBox(tr("Components"))
        grid = QGridLayout(components)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(4)
        for column, heading in enumerate((tr("Component"), tr("Version"), tr("Licence"))):
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
        note = _hint(tr(
            "The libraries are included unchanged. The full licence texts are in the program folder in "
            "THIRD-PARTY-NOTICES.txt and in the folder “licenses”."
        ))
        grid.addWidget(note, len(rows) + 1, 0, 1, 3)
        layout.addWidget(components)

        links = QFormLayout()
        links.setHorizontalSpacing(12)
        links.setVerticalSpacing(4)
        links.addRow(tr("Source code:"), _selectable(REPOSITORY))
        links.addRow(tr("Log file:"), _selectable(str(app_info.log_dir())))
        layout.addLayout(links)

        buttons = QDialogButtonBox()
        self.copy_button = buttons.addButton(tr("Copy version info"), QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.setToolTip(tr("Copies the program and component versions as text, e.g. for a bug report."))
        self.copy_button.clicked.connect(self._copy)
        close = buttons.addButton(tr("Close"), QDialogButtonBox.ButtonRole.AcceptRole)
        close.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(version_report())
        self.copy_button.setText(tr("Copied ✓"))


# ------------------------------------------------------------------------- error


class ErrorDialog(_Dialog):
    """Shown for an unexpected error instead of the app silently dying or ignoring it."""

    def __init__(self, summary: str, details: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.details = details
        self.setWindowTitle(tr("{app} – Unexpected error", app=APP_NAME))
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
        text = QLabel(tr(
            "<b>An unexpected error occurred.</b><br>"
            "The program keeps running. If something no longer works, please restart it.<br>"
            "To report the problem, copy the details and send them along."
        ))
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
        self.copy_button = buttons.addButton(tr("Copy details"), QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.clicked.connect(self.copy_details)
        log_button = buttons.addButton(tr("Open log file"), QDialogButtonBox.ButtonRole.ActionRole)
        log_button.clicked.connect(open_log)
        save_log_button = buttons.addButton(tr("Save anonymised…"), QDialogButtonBox.ButtonRole.ActionRole)
        save_log_button.setToolTip(anonymize_hint())
        save_log_button.clicked.connect(lambda: save_anonymized_log(self))
        close = buttons.addButton(tr("Close"), QDialogButtonBox.ButtonRole.AcceptRole)
        close.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def copy_details(self) -> None:
        QGuiApplication.clipboard().setText(self.details)
        self.copy_button.setText(tr("Copied ✓"))


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



def crashed_reason() -> str:
    """The reason in SkippedDialog for ConversionResult.crashed."""
    return tr("Skipped (geometry kernel crashed)")


def no_geometry_reason() -> str:
    """The reason in SkippedDialog for ConversionResult.no_geometry."""
    return tr("Without geometry")


def find_hint() -> str:
    """How to find a skipped element in the CAD program."""
    return tr(
        "How to find an element in the CAD program: copy the GlobalId and search for it – in ArchiCAD with "
        "“Find & Select” (Ctrl+F) by the IFC property GlobalId or “Archicad IFC ID”, in Revit by the parameter "
        "“IfcGUID” (e.g. in a schedule or with a filter), otherwise in any IFC viewer."
    )


class SkippedDialog(_Dialog):
    """The elements of one file that were not converted, with class, GlobalId and name, to copy.

    ``skipped`` is the number of elements without geometry; it can be larger than ``no_geometry`` when
    not all of them could be named. ``inside`` is the number of elements left out as interior (option
    "Nur Gebäudehülle"); they are only counted, not listed.
    """

    @staticmethod
    def columns() -> tuple[str, str, str, str]:
        """The column headings (reason, class, GlobalId, name), in the user's language."""
        return (tr("Reason"), tr("Class"), tr("GlobalId"), tr("Name"))

    def __init__(
        self, file_name: str, crashed: list[str], no_geometry: list[str], skipped: int = 0,
        inside: int = 0, parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Skipped elements – {file}", file=file_name))
        self.setMinimumSize(720, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        counts = []
        if crashed:
            counts.append(tr("{count} skipped because the geometry kernel crashed or hung on them", count=len(crashed)))
        if no_geometry or skipped:
            counts.append(tr("{count} without geometry (not convertible)", count=max(skipped, len(no_geometry))))
        if inside:
            counts.append(tr("{inside} (building hull only)", inside=inside_text(inside)))
        layout.addWidget(_selectable(f"<b>{html.escape(file_name)}</b>: " + "; ".join(counts) + "."))

        self.rows = [(crashed_reason(), *split_label(label)) for label in crashed]
        self.rows += [(no_geometry_reason(), *split_label(label)) for label in no_geometry]
        self.table = QTableWidget(len(self.rows), len(self.columns()))
        self.table.setHorizontalHeaderLabels(self.columns())
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
        # Without rows (only counts to report) the columns would shrink below their headings.
        header_font = self.table.horizontalHeader().fontMetrics()
        for column, heading in enumerate(self.columns()):
            self.table.setColumnWidth(column, max(self.table.columnWidth(column), header_font.horizontalAdvance(heading) + 24))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        copy = QAction(tr("Copy"), self.table)
        copy.setShortcut(QKeySequence.StandardKey.Copy)
        copy.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        copy.triggered.connect(self.copy_selection)
        self.table.addAction(copy)
        layout.addWidget(self.table, stretch=1)

        if skipped > len(no_geometry):
            layout.addWidget(_hint(tr(
                "{count} more elements without geometry could not be named individually.",
                count=skipped - len(no_geometry),
            )))
        if inside:
            layout.addWidget(_hint(tr(
                "The interior elements left out because of “Building hull only” are not listed individually; "
                "without the option they are converted too."
            )))
        layout.addWidget(_hint(
            tr("Select and Ctrl+C copies the chosen rows (Ctrl+A: all), as a table to paste into Excel or an "
               "e-mail.") + " " + find_hint()
        ))

        buttons = QDialogButtonBox()
        self.copy_button = buttons.addButton(tr("Copy all"), QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.setToolTip(tr("Copies the whole table, to paste into Excel or an e-mail."))
        self.copy_button.clicked.connect(self.copy_all)
        close = buttons.addButton(tr("Close"), QDialogButtonBox.ButtonRole.RejectRole)
        close.setDefault(True)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _text(self, rows: list[tuple[str, ...]]) -> str:
        """Tab-separated with a header line: pastes as a table into Excel, readable as plain text."""
        return "\n".join("\t".join(values) for values in [self.columns(), *rows]) + "\n"

    def copy_all(self) -> None:
        QGuiApplication.clipboard().setText(self._text(self.rows))
        self.copy_button.setText(tr("Copied ✓"))

    def copy_selection(self) -> None:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        if not rows:
            return
        values = [tuple(self.table.item(row, column).text() for column in range(len(self.columns()))) for row in rows]
        QGuiApplication.clipboard().setText(self._text(values))
