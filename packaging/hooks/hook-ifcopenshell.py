"""PyInstaller hook for IfcOpenShell 0.8/0.9.

IfcOpenShell loads its schema, geometry kernel (CGAL, OpenCASCADE, ...) and serializer plugins at
runtime from the folder of its own libraries, so all of them must stay together in
_internal/ifcopenshell. PyInstaller would also link them into the top-level _internal folder, where
the frozen app finds them first; IfcOpenShell then looks for its plugins there, finds none, and every
conversion fails ("Couldn't find express file 'ifc4.exp'", "No geometry serializer registered for glb").
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, get_package_paths

binaries = collect_dynamic_libs("ifcopenshell", search_patterns=["*.dll", "*.pyd", "*.so", "*.so.*", "*.dylib"])
datas = collect_data_files(
    "ifcopenshell",
    excludes=["**/fixtures/**", "mvd/**", "**/*.pyi", "**/*.md", "**/*.in", "**/py.typed"],
)
# Importing ifcopenshell.express (for the rules below) checks that express_parser.py exists as a file
# and otherwise writes it into the program folder by running "sys.executable bootstrap.py", which in
# the frozen app starts IFC Converter.exe / ifc-convert.exe again. The real file must be on disk.
datas.append((str(Path(get_package_paths("ifcopenshell")[1]) / "express" / "express_parser.py"), "ifcopenshell/express"))
bindepend_symlink_suppression = ["**/ifcopenshell/*"]
# Derived attributes (e.g. IfcSIUnit.Dimensions) are computed by rule modules that IfcOpenShell imports
# by schema name. Missing, it would try to compile them by running sys.executable, i.e. this app.
hiddenimports = collect_submodules("ifcopenshell.express.rules")
# IfcOpenShell's own viewer (ifcopenshell.geom.app) and pythonocc helpers are never used.
excludedimports = ["PyQt5", "OCC"]
