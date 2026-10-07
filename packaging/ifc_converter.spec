# PyInstaller spec: one folder "IFC Converter" with the program window (IFC Converter.exe, no console)
# and the command-line tool (ifc-convert.exe), sharing one _internal folder.
#
#   pyinstaller --noconfirm packaging/ifc_converter.spec     (or simply: python packaging/build.py)
#
# A folder ("onedir") instead of a single exe: starts faster (nothing is unpacked to %TEMP% on every
# start, which also matters for the conversion child processes), triggers far fewer antivirus false
# positives, and the LGPL libraries (Qt, IfcOpenShell) stay replaceable DLLs.
import re
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

HERE = Path(SPECPATH)
ROOT = HERE.parent
APP_NAME = "IFC Converter"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

# The app's own icon if the app ships one, else a placeholder.
ICON = next(iter(sorted((ROOT / "src" / "ifc_converter" / "resources").glob("*.ico"))), HERE / "placeholder-icon.ico")

datas = []
resources = ROOT / "src" / "ifc_converter" / "resources"
if resources.is_dir():
    datas.append((str(resources), "ifc_converter/resources"))
# Package metadata: version numbers for the about dialog, and the license texts of what is bundled.
for dist in ("ifc-file-converter", "ifcopenshell", "rhino3dm", "PySide6-Essentials", "shiboken6", "numpy", "shapely"):
    try:
        datas += copy_metadata(dist)
    except Exception as exc:  # e.g. ifc-file-converter not installed, only on sys.path
        print(f"WARNING: no metadata for {dist}: {exc}")
datas += [(str(HERE / "THIRD-PARTY-NOTICES.txt"), "."), (str(HERE / "licenses"), "licenses")]

EXCLUDES = [
    # Never used at runtime, but some packages reference them optionally.
    "tkinter", "_tkinter", "PyQt5", "PyQt6", "OCC", "matplotlib", "IPython", "pytest", "_pytest",
    "ifcopenshell.geom.app",  # IfcOpenShell's own PyQt5 viewer
]
# Big Qt DLLs a widgets app does not need: software OpenGL and the Direct3D shader compiler.
UNNEEDED_BINARIES = {"opengl32sw.dll", "d3dcompiler_47.dll"}


def analysis(script: str, hiddenimports: list[str] = ()) -> Analysis:
    a = Analysis(
        [str(HERE / script)],
        pathex=[str(ROOT / "src")],
        datas=datas,
        hookspath=[str(HERE / "hooks")],  # IfcOpenShell
        hiddenimports=list(hiddenimports),
        excludes=EXCLUDES,
        noarchive=False,
    )
    a.binaries = [b for b in a.binaries if Path(b[0]).name.lower() not in UNNEEDED_BINARIES]
    return a


def version_info(filename: str):
    """The version resource shown in the exe's file properties (Windows only)."""
    if sys.platform != "win32":
        return None
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
    )

    numbers = tuple(int(n) for n in re.findall(r"\d+", VERSION.split("+")[0])[:4])
    numbers += (0,) * (4 - len(numbers))
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([StringTable("040704B0", [
                StringStruct("CompanyName", "Jonas Kleinert"),
                StringStruct("FileDescription", APP_NAME),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", APP_NAME),
                StringStruct("LegalCopyright", "Jonas Kleinert"),
                StringStruct("OriginalFilename", filename),
                StringStruct("ProductName", APP_NAME),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
        ],
    )


gui = analysis("gui_entry.py")
# Both exes share one _internal folder, but each has its own archive of Python modules. A module the
# CLI imports only dynamically (e.g. Qt for the version list in the log) would be found there as a
# half-broken namespace package; bundling everything the GUI uses in the CLI too rules that out.
cli = analysis("cli_entry.py", hiddenimports=["ifc_converter.gui"])

gui_exe = EXE(
    PYZ(gui.pure),
    gui.scripts,
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    icon=str(ICON),
    version=version_info(f"{APP_NAME}.exe"),
    upx=False,  # UPX-packed exes are a classic antivirus false positive
    contents_directory="_internal",
)
cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    exclude_binaries=True,
    name="ifc-convert",
    console=True,
    icon=str(ICON),
    version=version_info("ifc-convert.exe"),
    upx=False,
    contents_directory="_internal",
)
COLLECT(
    gui_exe, gui.binaries, gui.datas,
    cli_exe, cli.binaries, cli.datas,
    name=APP_NAME,
    upx=False,
)
