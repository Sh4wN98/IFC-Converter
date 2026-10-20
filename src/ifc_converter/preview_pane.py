"""The preview pane of the main window: a small 3D view of the selected IFC file.

Previews are computed in a child process like conversions (preview.compute_preview) and cached, so
a file shows at once the next time. Small files get their preview as soon as they are selected;
large ones (reading alone takes minutes) and files selected while a conversion runs only on request,
so the preview never slows down a conversion or the user's other programs unasked.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ifc_converter.converter import size_text
from ifc_converter.dialogs import ElidedLabel, muted
from ifc_converter.i18n import tr

log = logging.getLogger(__name__)

# Files up to this size get their preview as soon as they are selected (reading a 150 MB IFC takes
# about 10 s); larger ones on request.
AUTO_PREVIEW_SIZE = 150 * 1024 ** 2



def no_file_text() -> str:
    """What the pane says while no file is selected."""
    return tr("Select a file in the list – its preview appears here.")


def _number(value) -> str:
    return f"{int(value):,}".replace(",", ".") if isinstance(value, (int, float)) else str(value)


class _Task(QObject):
    """Runs ``work(progress, status, cancelled)`` in its own thread and reports the outcome."""

    progress = Signal(int)
    status = Signal(str)
    finished = Signal(object, str)  # result (None if failed or cancelled), error text ("" if cancelled)

    def __init__(self, work: Callable):
        super().__init__()
        self._work = work
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @Slot()
    def run(self) -> None:
        from ifc_converter.interactive import error_message
        from ifc_converter.process import Cancelled

        try:
            result = self._work(self.progress.emit, lambda phase, text: self.status.emit(text), self._cancel.is_set)
        except Cancelled:
            self.finished.emit(None, "")
        except Exception as exc:  # shown in the pane; the conversion log has the details
            log.warning("Vorschau fehlgeschlagen: %s", exc, exc_info=not isinstance(exc, OSError))
            self.finished.emit(None, error_message(exc))
        else:
            self.finished.emit(None if self._cancel.is_set() else result, "")


class _MessageView(QLabel):
    """Stands in for the 3D view where the viewer cannot be loaded at all."""

    element_clicked = Signal(str)
    renderer_name = "–"

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)

    def set_mesh(self, mesh) -> None:
        if mesh is not None:
            self.setText(tr("The 3D view is not available on this PC."))

    def set_message(self, text: str) -> None:
        self.setText(text)

    def reset_view(self) -> None:
        pass


def _make_view() -> QWidget:
    try:
        from ifc_converter.viewer import PreviewView

        return PreviewView()
    except Exception:  # never let the preview break the window
        log.exception("3D-Ansicht nicht verfügbar")
        return _MessageView()


class PreviewPane(QWidget):
    """Shows the preview of one file at a time (see show_file)."""

    def __init__(
        self,
        busy: Callable[[], bool] = lambda: False,
        view_factory: Callable[[], QWidget] = _make_view,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._busy = busy  # whether a conversion is running
        self.path: Path | None = None
        self._task: _Task | None = None
        self._thread: QThread | None = None
        self._task_path: Path | None = None  # the file the running task is for
        self._task_requested = False  # started by the user (not cancelled when another file is selected)
        self._mesh = None
        self._failed: dict[Path, str] = {}  # files whose preview failed: not computed again unasked
        self._renderer_logged = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        header = QHBoxLayout()
        header.setSpacing(8)
        # Title and info line shorten long file names with "…" instead of widening the window, and the
        # info line keeps its height when empty, so the view does not jump when another file is chosen.
        self.title = ElidedLabel(tr("Preview"))
        self.title.setObjectName("PreviewTitle")
        self.compute_button = QPushButton(tr("Compute preview"))
        self.compute_button.setToolTip(
            tr("Computes the preview of this file now (low priority, at most 4 threads); it is kept for next time.")
        )
        self.compute_button.clicked.connect(self.compute)
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setToolTip(tr("Stop computing the preview"))
        self.cancel_button.clicked.connect(self.cancel)
        self.reset_button = QPushButton(tr("Reset view"))
        self.reset_button.setToolTip(tr("Start view: the whole model from the south-west above (Home; double-click: whole model)"))
        header.addWidget(self.title, stretch=1)
        for button in (self.compute_button, self.cancel_button, self.reset_button):
            header.addWidget(button)
        layout.addLayout(header)

        self.view = view_factory()
        self.view.setMinimumHeight(120)
        self.view.element_clicked.connect(self._element_clicked)
        self.reset_button.clicked.connect(self.view.reset_view)
        layout.addWidget(self.view, stretch=1)

        self.info = muted(ElidedLabel())
        self.info.setObjectName("PreviewInfo")
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.info.setMinimumHeight(self.info.fontMetrics().height() + 2)
        layout.addWidget(self.info)
        self._show_state(no_file_text())

    # ------------------------------------------------------------------ API

    def show_file(self, path: Path | None) -> None:
        """Show the preview of ``path`` (None: nothing selected): from the cache, computed, or on request."""
        path = Path(path) if path else None
        if path == self.path and (self._mesh is not None or self._task is not None):
            return
        self.path, self._mesh = path, None
        if self._task is not None and not self._task_requested and self._task_path != path:
            self._task.cancel()  # computed for a file no longer selected, unasked
        if path is None:
            self.title.setText(tr("Preview"))
            self._show_state(no_file_text())
            return
        self.title.setText(tr("Preview – {file}", file=path.name))
        if self._task is not None and self._task_path == path:
            self._show_state(tr("Computing preview …"), running=True)
            return
        from ifc_converter.preview import cached_preview

        cached = cached_preview(path)
        if cached is not None:
            self._load(cached)
            return
        if path in self._failed:
            self._show_state(tr("No preview possible: {error}", error=self._failed[path]), can_compute=True)
            return
        try:
            size = path.stat().st_size
        except OSError:
            self._show_state(tr("The file is not (or no longer) accessible."))
            return
        if self._busy():
            self._show_state(
                tr("No preview is computed while a conversion runs, so as not to slow it down."),
                can_compute=True,
            )
        elif size > AUTO_PREVIEW_SIZE:
            self._show_state(
                tr("Large file ({size}): the preview takes a few minutes. "
                   "It runs at low priority and is kept for next time.", size=size_text(size)),
                can_compute=True,
            )
        elif self._task is not None:
            self._show_state(tr("Waiting for the running preview to finish …"), can_compute=True)
        else:
            self.compute(requested=False)

    def compute(self, requested: bool = True) -> None:
        """Compute the preview of the shown file (``requested``: by the user, so it keeps running)."""
        if self.path is None:
            return
        if self._task is not None:
            if self._task_path == self.path:
                self._task_requested |= requested
                return
            self._task.cancel()
            self._wait()
        from ifc_converter.preview import compute_preview, preview_path

        source, target = self.path, preview_path(self.path)

        def work(progress, status, cancelled):
            compute_preview(source, target, progress=progress, status=status, cancelled=cancelled)
            return target

        self._failed.pop(source, None)
        self._task_path, self._task_requested = source, requested
        self._start(_Task(work), self._computed)
        self._show_state(tr("Computing preview: reading the IFC file …"), running=True)

    def cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def shutdown(self) -> None:
        """Stop a running preview (the window is closing)."""
        self.cancel()
        self._wait()

    @property
    def is_computing(self) -> bool:
        return self._task is not None

    # -------------------------------------------------------------- internals

    def _start(self, task: _Task, done: Callable) -> None:
        thread = QThread(self)
        task.moveToThread(thread)
        thread.started.connect(task.run)
        task.progress.connect(self._progress)
        task.status.connect(self._status)
        task.finished.connect(done)
        task.finished.connect(thread.quit)
        self._task, self._thread = task, thread
        thread.start()

    def _wait(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._task = self._thread = None

    def _load(self, path: Path) -> None:
        from ifc_converter.preview import load_preview

        self._task_path, self._task_requested = self.path, False
        self._start(_Task(lambda progress, status, cancelled: load_preview(path)), self._loaded)
        self._show_state(tr("Loading preview …"))

    @Slot(object, str)
    def _computed(self, target, error: str) -> None:
        source = self._task_path
        self._wait()
        if source != self.path:  # finished for a file no longer shown: it is cached now
            self.show_file(self.path) if self.path else None
            return
        if error:
            self._failed[source] = error
            self._show_state(tr("No preview possible: {error}", error=error), can_compute=True)
        elif target is None:
            self._show_state(tr("Preview cancelled."), can_compute=True)
        else:
            self._load(target)

    @Slot(object, str)
    def _loaded(self, mesh, error: str) -> None:
        source = self._task_path
        self._wait()
        if source != self.path:
            self.show_file(self.path) if self.path else None
            return
        if mesh is None:
            self._show_state(tr("The preview could not be loaded."), can_compute=True)
        elif not mesh.triangle_count:
            self._show_state(tr("The file contains no geometry that can be shown."))
        else:
            self._mesh = mesh
            self.view.set_mesh(mesh)
            if not self._renderer_logged:
                self._renderer_logged = True
                log.info("Vorschau-Darstellung: %s (%s)", getattr(self.view, "renderer_name", "–"),
                         getattr(self.view, "renderer_detail", ""))
            self._show_buttons(reset=True)
            self.info.setText(self._info_text(mesh))

    @Slot(int)
    def _progress(self, percent: int) -> None:
        if self._task is not None and self._task_path == self.path and self._mesh is None:
            self.view.set_message(tr("Computing preview … {percent}%", percent=max(percent, 0)))

    @Slot(str)
    def _status(self, text: str) -> None:
        if self._task is not None and self._task_path == self.path and self._mesh is None and text:
            self.view.set_message(tr("Preview: {status}", status=text))

    @Slot(str)
    def _element_clicked(self, label: str) -> None:
        if self._mesh is not None:
            self.info.setText(f"{label}" if label else self._info_text(self._mesh))

    def _show_state(self, text: str, can_compute: bool = False, running: bool = False) -> None:
        self.view.set_mesh(None)
        self.view.set_message(text)
        self.info.setText("")
        self.compute_button.setText(tr("Try again") if self.path in self._failed else tr("Compute preview"))
        self._show_buttons(compute=can_compute, cancel=running)

    def _show_buttons(self, compute: bool = False, cancel: bool = False, reset: bool = False) -> None:
        self.compute_button.setVisible(compute)
        self.cancel_button.setVisible(cancel)
        self.reset_button.setVisible(reset)

    def _info_text(self, mesh) -> str:
        info = mesh.info
        parts = [tr("{count} elements", count=_number(info.get("elements", len(mesh.elements))))]
        if info.get("left_out"):
            parts.append(tr("{count} small elements left out", count=_number(info["left_out"])))
        parts.append(tr("Renderer: {renderer}", renderer=getattr(self.view, "renderer_name", "–")))
        return " · ".join(parts) + " – " + tr("Click an element to see its class, GlobalId and name")
