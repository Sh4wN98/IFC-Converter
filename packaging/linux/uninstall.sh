#!/usr/bin/env bash
# Removes what install.sh installed for the current user: the program folder, the commands in
# ~/.local/bin, the menu entry, the icon and the MIME type. Settings, logs and previews stay
# (~/.config/ifc-converter, ~/.local/state/ifc-converter); delete them by hand if wanted.
#
# Every removed path is spelled with ${VAR:?}: an unset or empty variable stops the script instead of
# turning "rm -rf $PREFIX" into "rm -rf /" or "$APPS/$SLUG.desktop" into "/.desktop".
set -euo pipefail

fail() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

case "${HOME:-}" in
  /*) ;;
  *) fail "HOME ist leer oder kein absoluter Pfad (${HOME:-}); es wird nichts entfernt." ;;
esac

SLUG=ifc-converter
PREFIX="${IFC_CONVERTER_PREFIX:-${HOME:?}/.local/opt/${SLUG:?}}"
BIN="${HOME:?}/.local/bin"
DATA="${XDG_DATA_HOME:-${HOME:?}/.local/share}"
APPS="${DATA:?}/applications"
ICONS="${DATA:?}/icons/hicolor"
MIME="${DATA:?}/mime"

running_from_prefix() {
  local exe
  for exe in /proc/[0-9]*/exe; do
    case "$(readlink "$exe" 2>/dev/null || true)" in
      "${PREFIX:?}"/*) return 0 ;;
    esac
  done
  return 1
}

# Remove a command only if it is our link into the program folder, never someone else's file.
remove_link() {
  if [ -L "${1:?}" ]; then
    case "$(readlink "${1:?}")" in
      "${PREFIX:?}"/*) rm -f "${1:?}" ;;
    esac
  fi
}

main() {
  case "${PREFIX:?}" in
    /?*) ;;
    *) fail "IFC_CONVERTER_PREFIX muss ein absoluter Pfad sein: ${PREFIX:?}" ;;
  esac
  if running_from_prefix; then
    fail "Der IFC Converter läuft noch (aus ${PREFIX:?}). Bitte erst beenden, auch laufende Umwandlungen im Terminal; es wird nichts entfernt."
  fi
  echo "IFC Converter wird entfernt (${PREFIX:?}) ..."
  rm -rf "${PREFIX:?}" "${PREFIX:?}.neu" "${PREFIX:?}.alt"
  remove_link "${BIN:?}/${SLUG:?}"
  remove_link "${BIN:?}/ifc-convert"
  rm -f "${APPS:?}/${SLUG:?}.desktop" "${ICONS:?}/256x256/apps/${SLUG:?}.png" "${MIME:?}/packages/${SLUG:?}.xml"
  if command -v update-mime-database >/dev/null 2>&1; then update-mime-database "${MIME:?}" >/dev/null 2>&1 || true; fi
  if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database -q "${APPS:?}" 2>/dev/null || true; fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q -t -f "${ICONS:?}" 2>/dev/null || true; fi
  echo "Fertig. Einstellungen und Logdateien bleiben erhalten:"
  echo "  ${XDG_CONFIG_HOME:-${HOME:?}/.config}/${SLUG:?}   ${XDG_STATE_HOME:-${HOME:?}/.local/state}/${SLUG:?}"
}

main "$@"
