"""Convert IFC building models to 3D formats."""

import re
from pathlib import Path


def _version() -> str:
    """The version from pyproject.toml, the single place where it is set.

    In a source checkout pyproject.toml is read directly (installed metadata of an editable install
    goes stale when the version changes); otherwise the installed package metadata has it (a frozen
    app must bundle that metadata, e.g. PyInstaller's copy_metadata("ifc-file-converter")).
    """
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if re.search(r'^name\s*=\s*"ifc-file-converter"', text, re.MULTILINE):
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if match:
            return match.group(1)
    try:
        from importlib.metadata import version

        return version("ifc-file-converter")
    except Exception:  # noqa: BLE001 - PackageNotFoundError, or no metadata at all in a frozen app
        return "0+unbekannt"


__version__ = _version()

from ifc_converter.converter import FORMATS, ConversionResult, convert  # noqa: E402

__all__ = ["FORMATS", "ConversionResult", "convert", "__version__"]
