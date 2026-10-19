#!/usr/bin/env bash
# Installs the IFC Converter for the current user, no root needed:
#   program folder      ~/.local/opt/ifc-converter        (or $IFC_CONVERTER_PREFIX)
#   commands            ~/.local/bin/ifc-converter, ~/.local/bin/ifc-convert
#   menu entry, icon    ~/.local/share/applications, ~/.local/share/icons  (or $XDG_DATA_HOME)
#   MIME type           application/x-ifc for *.ifc, so "Open with" offers the converter
# The default program for .ifc files is never changed. Running it again updates an installation;
# settings, logs and previews (~/.config/ifc-converter, ~/.local/state/ifc-converter) are kept.
#
# Every path that is created or removed is spelled with ${VAR:?}: an unset or empty variable stops
# the script instead of turning "$PREFIX.alt" into "/.alt" or "rm -rf $X/..." into "rm -rf /...".
set -euo pipefail

fail() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

case "${HOME:-}" in
  /*) ;;
  *) fail "HOME ist leer oder kein absoluter Pfad (${HOME:-}); es wird nichts installiert." ;;
esac

SLUG=ifc-converter
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${IFC_CONVERTER_PREFIX:-${HOME:?}/.local/opt/${SLUG:?}}"
BIN="${HOME:?}/.local/bin"
DATA="${XDG_DATA_HOME:-${HOME:?}/.local/share}"
APPS="${DATA:?}/applications"
ICONS="${DATA:?}/icons/hicolor"
MIME="${DATA:?}/mime"

# Whether a process runs from the installed folder (the window, ifc-convert or a conversion child).
running_from_prefix() {
  local exe
  for exe in /proc/[0-9]*/exe; do
    case "$(readlink "$exe" 2>/dev/null || true)" in
      "${PREFIX:?}"/*) return 0 ;;
    esac
  done
  return 1
}

# System libraries the Qt platform plugins need and that are missing on this machine (a warning only:
# another platform plugin may still work, and the message names the packages).
missing_libraries() {
  local plugin
  command -v ldd >/dev/null 2>&1 || return 0
  for plugin in "${PREFIX:?}/_internal/PySide6/Qt/plugins/platforms/libqxcb.so" \
                "${PREFIX:?}/_internal/PySide6/Qt/plugins/platforms/libqwayland.so" \
                "${PREFIX:?}/_internal/PySide6/Qt/lib/libQt6OpenGL.so.6"; do
    [ -f "$plugin" ] || continue
    LD_LIBRARY_PATH="${PREFIX:?}/_internal:${PREFIX:?}/_internal/PySide6/Qt/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
      ldd "$plugin" 2>/dev/null | awk '/not found/ {print $1}'
  done | sort -u
}

main() {
  [ -x "${HERE:?}/${SLUG:?}/${SLUG:?}" ] && [ -x "${HERE:?}/${SLUG:?}/ifc-convert" ] \
    || fail "Der Programmordner ${HERE:?}/${SLUG:?} fehlt. install.sh im entpackten Ordner des tar.gz ausführen."
  case "${PREFIX:?}" in
    /?*) ;;
    *) fail "IFC_CONVERTER_PREFIX muss ein absoluter Pfad sein: ${PREFIX:?}" ;;
  esac
  if running_from_prefix; then
    fail "Der IFC Converter läuft noch (aus ${PREFIX:?}). Bitte erst beenden, auch laufende Umwandlungen im Terminal; es wird nichts geändert."
  fi

  echo "IFC Converter wird nach ${PREFIX:?} installiert ..."
  rm -rf "${PREFIX:?}.neu" "${PREFIX:?}.alt"
  mkdir -p "$(dirname "${PREFIX:?}")"
  cp -R "${HERE:?}/${SLUG:?}" "${PREFIX:?}.neu"
  install -m 755 "${HERE:?}/uninstall.sh" "${PREFIX:?}.neu/uninstall.sh"
  chmod 755 "${PREFIX:?}.neu/${SLUG:?}" "${PREFIX:?}.neu/ifc-convert"
  # The old installation is replaced in one move, so an interrupted update leaves no half-copied folder.
  if [ -e "${PREFIX:?}" ]; then
    mv "${PREFIX:?}" "${PREFIX:?}.alt"
  fi
  mv "${PREFIX:?}.neu" "${PREFIX:?}"
  rm -rf "${PREFIX:?}.alt"

  mkdir -p "${BIN:?}" "${APPS:?}" "${ICONS:?}/256x256/apps" "${MIME:?}/packages"
  ln -sfn "${PREFIX:?}/${SLUG:?}" "${BIN:?}/${SLUG:?}"
  ln -sfn "${PREFIX:?}/ifc-convert" "${BIN:?}/ifc-convert"
  install -m 644 "${HERE:?}/${SLUG:?}.png" "${ICONS:?}/256x256/apps/${SLUG:?}.png"
  install -m 644 "${HERE:?}/${SLUG:?}.xml" "${MIME:?}/packages/${SLUG:?}.xml"
  # The menu entry with the absolute path of this installation (quoted: the path may contain spaces).
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      Exec=*) line="Exec=\"${PREFIX:?}/${SLUG:?}\" %F" ;;
      TryExec=*) line="TryExec=${PREFIX:?}/${SLUG:?}" ;;
    esac
    printf '%s\n' "$line"
  done < "${HERE:?}/${SLUG:?}.desktop" > "${APPS:?}/${SLUG:?}.desktop"
  chmod 644 "${APPS:?}/${SLUG:?}.desktop"

  # Tell the desktop about the new entry, icon and MIME type (each tool is optional).
  if command -v update-mime-database >/dev/null 2>&1; then update-mime-database "${MIME:?}" >/dev/null 2>&1 || true; fi
  if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database -q "${APPS:?}" 2>/dev/null || true; fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q -t -f "${ICONS:?}" 2>/dev/null || true; fi

  echo "Fertig."
  echo "  Starten:         „IFC Converter“ im Anwendungsmenü oder: ${BIN:?}/${SLUG:?}"
  echo "  Kommandozeile:   ${BIN:?}/ifc-convert haus.ifc -f 3dm"
  echo "  Deinstallieren:  ${PREFIX:?}/uninstall.sh"
  case ":${PATH:-}:" in
    *":${BIN:?}:"*) ;;
    *) echo "  Hinweis: ${BIN:?} ist nicht im PATH; nach dem nächsten Anmelden meist schon, sonst den vollen Pfad verwenden." ;;
  esac
  local missing
  missing="$(missing_libraries)"
  if [ -n "$missing" ]; then
    echo "  Achtung: Auf diesem Rechner fehlen Systembibliotheken, ohne die das Fenster nicht startet:"
    # shellcheck disable=SC2086
    echo "           $(printf '%s ' $missing)"
    echo "           Ubuntu/Debian: sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-randr0 libxcb-xfixes0 libxcb-sync1 libxcb-xkb1 libxcb-shm0 libxcb-glx0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libgl1 libegl1 libfontconfig1 libdbus-1-3"
  fi
}

main "$@"
