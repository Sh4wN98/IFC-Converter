"""Render the preview figure of the user guide offscreen: docs/guide/viewer-en.png (English guide).

    python tools/guide_screens.py MODEL.ifc [--out-dir docs/guide] [--width 560] [--height 370] [--light]
        [--languages en] [--prefix viewer]

The figure is the preview pane as it sits in the window (title, the view bar, the 3D view with the
axis triad, the info line), with the model's preview (computed into the preview cache if it is not
there yet, like the program does), a wall clicked (its tint, chip and label), the Fusion style and
the dark palette of the window screenshots (``--light`` for the light one). The 3D view is drawn with
OpenGL where an offscreen context exists, else in software; both look the same. Each language gets
its own image, like window-en.png.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # the shell may say "wayland;xcb": a screenshot needs neither

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DARK = {"Window": "#2b2f33", "WindowText": "#e6e8ea", "Base": "#1f2326", "Text": "#e6e8ea", "Button": "#3a3f44",
        "ButtonText": "#e6e8ea", "Highlight": "#4a90d9", "HighlightedText": "#ffffff"}
LIGHT = {"Window": "#efefef", "WindowText": "#1f2428", "Base": "#ffffff", "Text": "#1f2428", "Button": "#e9e9e9",
         "ButtonText": "#1f2428", "Highlight": "#3b7dd8", "HighlightedText": "#ffffff"}


def palette(colours: dict[str, str]):
    from PySide6.QtGui import QColor, QPalette

    result = QPalette()
    for role, colour in colours.items():
        result.setColor(getattr(QPalette.ColorRole, role), QColor(colour))
    return result


def ensure_preview(model: Path) -> Path:
    """The model's cached preview, computed now if there is none (a child process, like the program)."""
    from ifc_converter.preview import cached_preview, compute_preview

    cached = cached_preview(model)
    if cached is not None:
        return cached
    print(f"computing the preview of {model.name} …")
    return compute_preview(model, status=lambda phase, text: print(f"  {text}"))


def render(model: Path, out: Path, language: str, width: int, height: int, light: bool) -> Path:
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QApplication

    from ifc_converter import gui, i18n
    from ifc_converter.preview_pane import PreviewPane
    from ifc_converter.viewer import PreviewView

    app = QApplication.instance()
    i18n.set_language(language)
    pane = PreviewPane(view_factory=PreviewView)
    hover = pane.palette().color(pane.palette().ColorRole.Highlight).darker(118).name()
    pane.setStyleSheet(gui.STYLESHEET.replace("%HOVER%", hover))
    pane.resize(width, height)
    pane.show()
    app.processEvents()
    pane.show_file(model)
    deadline = time.monotonic() + 120
    while pane.view.mesh is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    if pane.view.mesh is None:
        raise SystemExit(f"no preview of {model} after 120 s: {pane.view.message()}")
    view = pane.view
    view.image()  # drawn once: picking needs the GL resources
    # Click a visible wall (or whatever is there) a little below the middle of the view: tint, chip, info line.
    points = [(0.5, 0.6), (0.4, 0.55), (0.6, 0.65), (0.5, 0.5), (0.3, 0.6), (0.7, 0.5)]
    labels = [view.element_at(view.width() * x, view.height() * y) for x, y in points]
    label = next((found for found in labels if found.startswith("IfcWall")), next((found for found in labels if found), ""))
    if label:
        view.select_element(label)
        view.element_clicked.emit(label)
    pane.view.wait_for_edges()
    app.processEvents()
    pixmap = pane.grab()
    # The 3D view's own image (what the user sees) instead of what grab() makes of a QOpenGLWidget offscreen.
    painter = QPainter(pixmap)
    painter.drawImage(pane.view.geometry().topLeft(), pane.view.image())
    painter.end()
    out.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(out), "PNG")
    print(f"{out} ({pixmap.width()}x{pixmap.height()}, {language}, {pane.view.renderer_name})")
    pane.shutdown()
    pane.close()
    pane.deleteLater()
    app.processEvents()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("model", type=Path, help="an IFC file, e.g. duplex.ifc of the test corpus")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "docs" / "guide")
    parser.add_argument("--prefix", default="viewer", help="file name before -<language>.png")
    parser.add_argument("--languages", default="en")
    parser.add_argument("--width", type=int, default=560)
    parser.add_argument("--height", type=int, default=370)
    parser.add_argument("--light", action="store_true", help="the light palette instead of the dark one")
    args = parser.parse_args(argv)
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    app.setPalette(palette(LIGHT if args.light else DARK))
    model = args.model.resolve()
    ensure_preview(model)
    for language in args.languages.split(","):
        render(model, args.out_dir / f"{args.prefix}-{language.strip()}.png", language.strip(), args.width,
               args.height, args.light)
    return 0


if __name__ == "__main__":
    sys.exit(main())
