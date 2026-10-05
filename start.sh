#!/usr/bin/env bash
# Startet den IFC File Converter (Fenster). Mit Dateien als Argument läuft die Kommandozeilen-Version.
# Beim ersten Start (und nach Updates) wird alles automatisch eingerichtet.
set -euo pipefail
cd "$(dirname "$0")"

# Die Umgebung liegt im Home-Ordner, weil exFAT/FAT-USB-Platten keine Symlinks können.
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/venvs/ifc-file-converter"
STAMP="$(cksum pyproject.toml | cut -d' ' -f1)"

if [ "$(cat "$VENV/.installed" 2>/dev/null)" != "$STAMP" ]; then
  echo "Der Converter wird eingerichtet, das dauert einen Moment ..."
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -e .
  echo "$STAMP" > "$VENV/.installed"
fi

if [ $# -gt 0 ] || [ "${IFC_CONVERTER_CLI:-}" = 1 ]; then
  exec "$VENV/bin/python" -m ifc_converter "$@"
fi
exec "$VENV/bin/python" -m ifc_converter.gui
