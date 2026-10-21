"""Render the short user guide (docs/guide/guide.html, German and English) to a PDF with Qt.

    python packaging/guide.py [--out dist/IFC-Converter-<version>-Kurzanleitung.pdf]

The HTML is a QTextDocument (a subset of HTML/CSS: no flexbox, images by relative path), printed
to A4 with QPdfWriter. {version} and {english_page} in the HTML are filled in; the English part
starts on a new page, whose number is found by a first rendering pass.
"""

from __future__ import annotations

import argparse
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

    def document(english_page: str) -> QTextDocument:
        doc = QTextDocument()
        doc.setBaseUrl(QUrl.fromLocalFile(str(SOURCE.parent) + "/"))
        doc.setHtml(html.replace("{version}", __version__).replace("{english_page}", english_page))
        return doc

    def write(doc: QTextDocument, path: Path) -> int:
        writer = QPdfWriter(str(path))
        writer.setTitle(f"IFC Converter {__version__} – Kurzanleitung / Quick Guide")
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageMargins(QMarginsF(18, 16, 18, 16), QPageLayout.Unit.Millimeter)
        writer.setResolution(96)  # image pixels map 1:1 to the layout, so images reserve their real height
        layout = writer.pageLayout()
        size = layout.paintRectPixels(writer.resolution()).size()
        doc.setPageSize(QSizeF(size))
        doc.print_(writer)
        return doc.pageCount()

    out.parent.mkdir(parents=True, exist_ok=True)
    # First pass to learn where the English part begins: the German part ends with a page break.
    probe = document("?")
    pages = write(probe, out)
    german = QTextDocument()
    german.setBaseUrl(probe.baseUrl())
    german.setHtml(html.split("<!-- ===================================================== ENGLISH -->")[0]
                   .replace("{version}", __version__).replace("{english_page}", "?") + "</body></html>")
    german.setPageSize(probe.pageSize())
    english_page = german.pageCount() + 1
    pages = write(document(str(english_page)), out)
    print(f"{out} ({pages} pages, English from page {english_page})")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, help="PDF to write (default: dist/IFC-Converter-<version>-Kurzanleitung.pdf)")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "src"))
    from ifc_converter import __version__

    out = args.out or ROOT / "dist" / f"IFC-Converter-{__version__}-Kurzanleitung.pdf"
    render(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
