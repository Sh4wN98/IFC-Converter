"""Render the user guide (docs/guide/guide.html) to a PDF with Qt.

    python packaging/guide.py [--out dist/IFC-Converter-<version>-Guide.pdf]

The HTML is a QTextDocument (a subset of HTML/CSS: no flexbox, images by relative path with their
size given), printed to A4 with QPdfWriter. {version} and {date} in the HTML are filled in.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "guide" / "guide.html"


def render(out: Path) -> Path:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QMarginsF, QSizeF, QUrl
    from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPdfWriter, QTextDocument

    sys.path.insert(0, str(ROOT / "src"))
    from ifc_converter import __version__

    app = QGuiApplication.instance() or QGuiApplication([sys.argv[0]])
    html = SOURCE.read_text(encoding="utf-8")
    html = html.replace("{version}", __version__).replace("{date}", datetime.date.today().strftime("%B %Y"))

    doc = QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(SOURCE.parent) + "/"))
    doc.setHtml(html)

    out.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(out))
    writer.setTitle(f"IFC Converter {__version__} – User Guide")
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(18, 16, 18, 16), QPageLayout.Unit.Millimeter)
    writer.setResolution(96)  # image pixels map 1:1 to the layout, so images reserve their real height
    size = writer.pageLayout().paintRectPixels(writer.resolution()).size()
    doc.setPageSize(QSizeF(size))
    doc.print_(writer)
    print(f"{out} ({doc.pageCount()} pages)")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, help="PDF to write (default: dist/IFC-Converter-<version>-Guide.pdf)")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "src"))
    from ifc_converter import __version__

    out = args.out or ROOT / "dist" / f"IFC-Converter-{__version__}-Guide.pdf"
    render(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
