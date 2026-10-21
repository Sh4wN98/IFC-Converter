"""The preview pane of the main window: a small 3D view of the selected IFC file.

Previews are computed in a child process like conversions (preview.compute_preview) and cached, so
a file shows at once the next time. A file gets its preview as soon as it is selected when the free
memory has room for it (beside a running conversion as well), else on request, so the preview never
slows down a conversion or the user's other programs unasked. While it is computed, the pane polls
for the batch files the child writes (preview.batch_paths) and shows the model as it grows.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ifc_converter.converter import size_text
from ifc_converter.dialogs import ElidedLabel, muted
from ifc_converter.i18n import tr
from ifc_converter.interactive import number_text

log = logging.getLogger(__name__)

# When the free memory cannot be determined: files up to this size get their preview as soon as they
# are selected (reading a 150 MB IFC takes about 10 s), larger ones on request.
AUTO_PREVIEW_SIZE = 150 * 1024 ** 2
# How often the pane looks for new batch files while a preview is computed.
BATCH_POLL_MS = 1000
# After this many new attempts of the child (the kernel crashed or hung) the preview is cancelled and
# what is shown is kept: each attempt reads the whole file again.
MAX_RETRIES = 2
# The view's options in the settings: option name -> (settings key, default).
VIEW_OPTIONS = {"edges": ("preview_edges", True), "projection": ("preview_projection", "perspective")}


def no_file_text() -> str:
    """What the pane says while no file is selected."""
    return tr("Select a file in the list – its preview appears here.")


def _number(value) -> str:
    return number_text(int(value)) if isinstance(value, (int, float)) else str(value)


class _Task(QObject):
    """Runs ``work(progress, status, cancelled, retried)`` in its own thread and reports the outcome."""

    progress = Signal(int)
    status = Signal(str)
    retried = Signal(str)  # the child starts a new attempt (message of process.convert_in_child)
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
            result = self._work(
                self.progress.emit, lambda phase, text: self.status.emit(text), self._cancel.is_set, self.retried.emit,
            )
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
        settings: QSettings | None = None,
    ):
        super().__init__(parent)
        self._busy = busy  # whether a conversion is running
        self._settings = settings  # keeps the view's options (edges, projection), if given
        self.path: Path | None = None
        self._task: _Task | None = None
        self._thread: QThread | None = None
        self._task_path: Path | None = None  # the file the running task is for
        self._task_target: Path | None = None  # where its preview (and the batch files) go
        self._task_requested = False  # started by the user (not cancelled when another file is selected)
        self._mesh = None  # what the view shows: the final preview, or the batches so far (info["partial"])
        self._partial = None  # the batches of the running task merged so far
        self._partial_token = 0  # the attempt they are from (preview.batch_token)
        self._loaded_batches: set[str] = set()
        self._loader: _Task | None = None  # loads and merges new batch files
        self._loader_thread: QThread | None = None
        self._retries = 0  # new attempts of the running task
        self._incomplete = ""  # why the shown preview stays incomplete: "cancelled", "crashed" or "error"
        self._error = ""
        self._percent = -1
        self._failed: dict[Path, str] = {}  # files whose preview failed: not computed again unasked
        self._renderer_logged = False
        self._poll = QTimer(self)
        self._poll.setInterval(BATCH_POLL_MS)
        self._poll.timeout.connect(self._poll_batches)

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
            tr("Computes the preview of this file now (low priority, at most 8 threads, 4 while a conversion runs); "
               "it is kept for next time.")
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
        self._restore_view_options()

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
        self.path, self._mesh, self._incomplete = path, None, ""
        if self._task is not None and not self._task_requested and self._task_path != path:
            self._task.cancel()  # computed for a file no longer selected, unasked
        if path is None:
            self.title.setText(tr("Preview"))
            self._show_state(no_file_text())
            return
        self.title.setText(tr("Preview – {file}", file=path.name))
        if self._task is not None and self._task_path == path:
            if self._partial is not None:  # selected again while computed: what there is so far
                self._show_partial(self._partial)
            else:
                self._show_state(tr("Computing preview …"), running=True)
            return
        from ifc_converter.preview import cached_preview, fits_in_memory

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
        busy = self._busy()
        fits = fits_in_memory(size, busy)
        if fits is None:  # free memory unknown: by size, and never beside a conversion
            fits = not busy and size <= AUTO_PREVIEW_SIZE
        if not fits and busy:
            self._show_state(
                tr("No preview is computed while a conversion runs, so as not to slow it down."),
                can_compute=True,
            )
        elif not fits:
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
        from ifc_converter.preview import compute_preview, preview_path, preview_threads, remove_batches

        source, target = self.path, preview_path(self.path)
        threads = preview_threads(self._busy())

        def work(progress, status, cancelled, retried):
            compute_preview(source, target, threads=threads, progress=progress, status=status, cancelled=cancelled,
                            on_retry=retried)
            return target

        self._failed.pop(source, None)
        self._task_path, self._task_target, self._task_requested = source, target, requested
        self._partial, self._partial_token, self._loaded_batches = None, 0, set()
        self._retries, self._incomplete, self._error, self._percent = 0, "", "", -1
        remove_batches(target)  # of an attempt that was killed: the child writes its own
        task = _Task(work)
        task.progress.connect(self._progress)
        task.status.connect(self._status)
        task.retried.connect(self._retried)
        self._task, self._thread = task, self._start(task, self._computed)
        self._show_state(tr("Computing preview: reading the IFC file …"), running=True)
        self._poll.start()

    def cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def shutdown(self) -> None:
        """Stop a running preview (the window is closing)."""
        self._poll.stop()
        self.cancel()
        self._wait()
        self._wait_loader()

    @property
    def is_computing(self) -> bool:
        return self._task is not None

    # -------------------------------------------------------------- internals

    def _restore_view_options(self) -> None:
        """Apply the view's options from the settings and keep them there when they change."""
        option_changed = getattr(self.view, "option_changed", None)
        if option_changed is None:  # the message stand-in, or a test double
            return
        if self._settings is not None:
            for option, (key, default) in VIEW_OPTIONS.items():
                value = self._settings.value(key, default, type=type(default))
                if option == "edges":
                    self.view.set_edges(bool(value))
                elif option == "projection":
                    self.view.set_projection(str(value))
        option_changed.connect(self._view_option_changed)

    @Slot(str, object)
    def _view_option_changed(self, option: str, value) -> None:
        if self._settings is not None and option in VIEW_OPTIONS:
            self._settings.setValue(VIEW_OPTIONS[option][0], value)

    def _start(self, task: _Task, done: Callable) -> QThread:
        thread = QThread(self)
        task.moveToThread(thread)
        thread.started.connect(task.run)
        task.finished.connect(done)
        task.finished.connect(thread.quit)
        thread.start()
        return thread

    def _wait(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._task = self._thread = None

    def _wait_loader(self) -> None:
        if self._loader_thread is not None:
            self._loader_thread.quit()
            self._loader_thread.wait()
        self._loader = self._loader_thread = None

    def _load(self, path: Path) -> None:
        from ifc_converter.preview import load_preview

        self._task_path, self._task_requested = self.path, False
        task = _Task(lambda progress, status, cancelled, retried: load_preview(path))
        self._task, self._thread = task, self._start(task, self._loaded)
        if self._mesh is None:
            self._show_state(tr("Loading preview …"))
        else:  # the batches stay in view until the whole preview is there
            self.info.setText(tr("Loading preview …"))

    @Slot(object, str)
    def _computed(self, target, error: str) -> None:
        from ifc_converter.preview import remove_batches

        source, computed = self._task_path, self._task_target
        self._poll.stop()
        self._wait()
        self._wait_loader()
        self._partial, self._task_target = None, None
        if computed is not None:
            remove_batches(computed)  # what was shown is in memory; the final file has everything
        if source != self.path:  # finished for a file no longer shown: it is cached now
            self.show_file(self.path) if self.path else None
            return
        if error:
            self._failed[source] = error
            if self._mesh is not None:
                self._incomplete, self._error = "error", error
                self._show_incomplete()
            else:
                self._show_state(tr("No preview possible: {error}", error=error), can_compute=True)
        elif target is None:
            if self._incomplete != "crashed":
                self._incomplete = "cancelled"
            if self._mesh is not None:
                self._show_incomplete()
            elif self._incomplete == "crashed":
                self._show_state(tr("No preview possible: the geometry kernel crashed repeatedly."), can_compute=True)
            else:
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
            if self._mesh is not None:
                self._incomplete, self._error = "error", tr("The preview could not be loaded.")
                self._show_incomplete()
            else:
                self._show_state(tr("The preview could not be loaded."), can_compute=True)
        elif not mesh.triangle_count:
            self._show_state(tr("The file contains no geometry that can be shown."))
        else:
            self._show_mesh(mesh)
            self._incomplete = ""
            self._show_buttons(reset=True)
            self.info.setText(self._info_text(mesh))

    def _show_mesh(self, mesh) -> None:
        """Show ``mesh``: a first one from the start view, a replacement (the model grown by a batch,
        the final preview after the batches) keeping the camera where the view can (update_mesh)."""
        update = getattr(self.view, "update_mesh", None)
        if self._mesh is None or update is None:
            self.view.set_mesh(mesh)
        else:
            update(mesh)
        self._mesh = mesh
        if not self._renderer_logged:
            self._renderer_logged = True
            log.info("Vorschau-Darstellung: %s (%s)", getattr(self.view, "renderer_name", "–"),
                     getattr(self.view, "renderer_detail", ""))

    def _show_partial(self, mesh) -> None:
        """Show the batches merged so far (the task is still running)."""
        self._show_mesh(mesh)
        self._show_buttons(cancel=True, reset=True)
        self.info.setText(self._info_text(mesh))

    def _show_incomplete(self) -> None:
        """Keep the shown batches after a cancel, crash limit or error; a click computes again."""
        self.compute_button.setText(tr("Try again") if self.path in self._failed else tr("Compute preview"))
        self._show_buttons(compute=True, reset=True)
        self.info.setText(self._info_text(self._mesh))

    @Slot()
    def _poll_batches(self) -> None:
        """Load the batch files that appeared since the last look, in a thread, and merge them."""
        from ifc_converter.preview import batch_paths, batch_token, load_preview, merge_batch

        if self._task is None or self._task_target is None or self._loader is not None:
            return
        paths = [path for path in batch_paths(self._task_target) if path.name not in self._loaded_batches]
        if not paths:
            return
        partial, token = self._partial, self._partial_token

        def load(progress, status, cancelled, retried):
            mesh, current, names = partial, token, []
            for path in paths:
                batch = load_preview(path)
                names.append(path.name)
                if batch is None:  # damaged, or gone: the final file has it
                    continue
                if batch_token(path) != current:  # a new attempt after a crash starts over
                    mesh, current = None, batch_token(path)
                mesh = merge_batch(mesh, batch)
            return mesh, current, names

        self._loader = _Task(load)
        self._loader_thread = self._start(self._loader, self._batches_loaded)

    @Slot(object, str)
    def _batches_loaded(self, result, error: str) -> None:
        self._wait_loader()
        if result is None or self._task is None:
            return
        mesh, token, names = result
        self._loaded_batches.update(names)
        if mesh is None:
            return
        self._partial, self._partial_token = mesh, token
        # Shown unless another file is selected meanwhile, or a new attempt has not yet caught up with
        # what the crashed one had shown.
        if self._task_path == self.path and (self._mesh is None or mesh.triangle_count >= self._mesh.triangle_count):
            self._show_partial(mesh)

    @Slot(int)
    def _progress(self, percent: int) -> None:
        self._percent = percent
        if self._task is not None and self._task_path == self.path:
            if self._mesh is None:
                self.view.set_message(tr("Computing preview … {percent}%", percent=max(percent, 0)))
            else:
                self.info.setText(self._info_text(self._mesh))

    @Slot(str)
    def _status(self, text: str) -> None:
        if self._task is not None and self._task_path == self.path and self._mesh is None and text:
            self.view.set_message(tr("Preview: {status}", status=text))

    @Slot(str)
    def _retried(self, message: str) -> None:
        """The child starts a new attempt: say so; after MAX_RETRIES keep what is shown and stop."""
        self._retries += 1
        if self._task is None:
            return
        if self._retries >= MAX_RETRIES:
            self._incomplete = "crashed"
            self._task.cancel()
            return
        if self._task_path == self.path:
            if self._mesh is None:
                self.view.set_message(tr("Preview: {status}", status=message))
            else:
                self.info.setText(self._info_text(self._mesh))

    @Slot(str)
    def _element_clicked(self, label: str) -> None:
        """The clicked element's label in the info line (the view highlights it); "" shows the summary again."""
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
        from ifc_converter.preview import detail_kind_name

        info = mesh.info
        parts = []
        if info.get("partial"):
            if self._incomplete == "cancelled":
                parts.append(tr("Preview cancelled – incomplete"))
            elif self._incomplete == "crashed":
                parts.append(tr("Preview incomplete (the geometry kernel crashed repeatedly)"))
            elif self._incomplete == "error":
                parts.append(tr("Preview incomplete: {error}", error=self._error))
            elif self._retries:
                parts.append(tr("Preview incomplete so far (the geometry kernel crashed), computing the rest …"))
            else:
                parts.append(tr("Computing preview … {percent}%", percent=max(self._percent, 0)))
            parts.append(tr("{count} of {total} elements so far", count=_number(info.get("elements", 0)),
                            total=_number(info.get("elements_total", 0))))
        else:
            parts.append(tr("{count} elements", count=_number(info.get("elements", len(mesh.elements)))))
        if info.get("details_left_out"):
            kinds = ", ".join(detail_kind_name(kind) for kind in str(info.get("detail_kinds", "")).split(",") if kind)
            parts.append(tr("{count} details left out ({kinds})", count=_number(info["details_left_out"]), kinds=kinds))
        if info.get("left_out"):
            parts.append(tr("{count} small elements left out", count=_number(info["left_out"])))
        parts.append(tr("Renderer: {renderer}", renderer=getattr(self.view, "renderer_name", "–")))
        return " · ".join(parts) + " – " + tr("Click an element to see its class, GlobalId and name")
