# PyInstaller spec: one folder "IFC Converter" with the program window (IFC Converter.exe, no console)
# and the command-line tool (ifc-convert.exe), sharing one _internal folder.
#
#   pyinstaller --noconfirm packaging/ifc_converter.spec     (or simply: python packaging/build.py)
#
# On Linux the same spec builds the folder "ifc-converter" with the executables ifc-converter (window)
# and ifc-convert (command line): names without spaces, as is the custom there (build.py packs the
# folder into the tar.gz together with the .desktop file, the icon and install.sh).
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
WINDOWS = sys.platform == "win32"
# The program folder and the window's executable: "IFC Converter" on Windows, "ifc-converter" elsewhere.
APP_DIR_NAME = APP_NAME if WINDOWS else "ifc-converter"
GUI_EXE_NAME = APP_NAME if WINDOWS else "ifc-converter"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

# The app's own icon if the app ships one, else a placeholder. Only Windows (and macOS) executables carry
# an icon; on Linux the icon travels as a PNG next to the .desktop file (see build.py).
ICON = next(iter(sorted((ROOT / "src" / "ifc_converter" / "resources").glob("*.ico"))), HERE / "placeholder-icon.ico")
EXE_ICON = str(ICON) if WINDOWS or sys.platform == "darwin" else None

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
# A big Qt DLL the app does not need: the Direct3D shader compiler. opengl32sw.dll (Mesa, ~20 MB) stays:
# Qt falls back to it where the graphics driver offers no usable OpenGL (remote desktop, virtual machines),
# so the 3D preview (viewer.py) still draws with OpenGL there.
UNNEEDED_BINARIES = {"d3dcompiler_47.dll"}
# Linux: Qt platform plugins for machines without a display server (framebuffer, KMS/EGL devices, VNC,
# Vulkan display). The app runs on desktops (xcb/Wayland; offscreen for the tests), and these plugins
# would pull in system libraries (libgbm, libinput, libvulkan ...) that a desktop PC need not have.
UNNEEDED_LINUX_BINARIES = {
    "libqeglfs.so", "libqlinuxfb.so", "libqminimalegl.so", "libqvkkhrdisplay.so", "libqvnc.so",
    "libqt6eglfsdeviceintegration.so.6", "libqt6eglfskmssupport.so.6",
}
UNNEEDED_LINUX_PLUGIN_DIRS = ("PySide6/Qt/plugins/egldeviceintegrations/",)
# The 3D preview imports QtOpenGL/QtOpenGLWidgets only when it draws; listed so they are always bundled.
PREVIEW_MODULES = ["ifc_converter.viewer", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets"]


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
    if sys.platform.startswith("linux"):
        a.binaries = [
            b for b in a.binaries
            if Path(b[0]).name.lower() not in UNNEEDED_LINUX_BINARIES
            and not b[0].replace("\\", "/").startswith(UNNEEDED_LINUX_PLUGIN_DIRS)
        ]
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
                StringStruct("CompanyName", "Jonas"),
                StringStruct("FileDescription", APP_NAME),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", APP_NAME),
                StringStruct("LegalCopyright", "Jonas"),
                StringStruct("OriginalFilename", filename),
                StringStruct("ProductName", APP_NAME),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
        ],
    )


gui = analysis("gui_entry.py", hiddenimports=PREVIEW_MODULES)
# Both exes share one _internal folder, but each has its own archive of Python modules. A module the
# CLI imports only dynamically (e.g. Qt for the version list in the log) would be found there as a
# half-broken namespace package; bundling everything the GUI uses in the CLI too rules that out.
cli = analysis("cli_entry.py", hiddenimports=["ifc_converter.gui", *PREVIEW_MODULES])

gui_exe = EXE(
    PYZ(gui.pure),
    gui.scripts,
    exclude_binaries=True,
    name=GUI_EXE_NAME,
    console=False,
    icon=EXE_ICON,
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
    icon=EXE_ICON,
    version=version_info("ifc-convert.exe"),
    upx=False,
    contents_directory="_internal",
)
COLLECT(
    gui_exe, gui.binaries, gui.datas,
    cli_exe, cli.binaries, cli.datas,
    name=APP_DIR_NAME,
    upx=False,
)
