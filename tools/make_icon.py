"""Render src/ifc_converter/resources/icon.svg to icon.png (256 px) and a multi-size icon.ico.

Uses only Qt (QSvgRenderer); the .ico holds PNG images, which Windows supports since Vista.

    python tools/make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

RESOURCES = Path(__file__).resolve().parent.parent / "src" / "ifc_converter" / "resources"
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def ico_bytes(images: dict[int, bytes]) -> bytes:
    """An .ico file with one PNG entry per size (ICONDIR, ICONDIRENTRYs, then the PNG data)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in sorted(images.items()):
        dim = 0 if size >= 256 else size  # 0 means 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    return header + entries + blobs


def main() -> int:
    QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(RESOURCES / "icon.svg"))
    if not renderer.isValid():
        print("icon.svg could not be read", file=sys.stderr)
        return 1
    images = {size: png_bytes(render(renderer, size)) for size in ICO_SIZES}
    (RESOURCES / "icon.png").write_bytes(images[256])
    (RESOURCES / "icon.ico").write_bytes(ico_bytes(images))
    print(f"wrote {RESOURCES / 'icon.png'} and {RESOURCES / 'icon.ico'} ({', '.join(map(str, ICO_SIZES))} px)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
