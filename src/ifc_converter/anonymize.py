"""Remove personal data from log text, so that a log can be sent to the developer.

Replaced: the user name (USERNAME, the profile folder in paths) by <user>, the computer name by
<computer>, server and share of network paths by <server> and <share>, folder names by <folder>
and file names by pseudonyms that keep the extension: the same name always gets the same number
within one Anonymizer, so "Haus A.ifc" and "Haus A.3dm" become "File-1.ifc" and "File-1.3dm" and
stay recognisable as input and output. Whether a path was local (C:\\…) or on the network
(\\\\<server>\\<share>\\…) is kept, as are generic folders (Desktop, AppData\\Local\\Temp, …), the
names of program files in tracebacks, and element labels without their names ("IfcWall 2O2Fr…").
Everything else stays: times, sizes, counts, versions, error codes. The placeholders are in the
language of the user interface (German: <Benutzer>, <Rechner>, <Server>, <Freigabe>, <Ordner>, Datei-1.ifc).
"""

from __future__ import annotations

import functools
import getpass
import os
import platform
import re
import socket
from collections.abc import Iterable

from ifc_converter.i18n import tr


# The placeholders, translated when an Anonymizer is created (the language is set at start, see i18n).
def user_placeholder() -> str:
    return tr("<user>")


def computer_placeholder() -> str:
    return tr("<computer>")


def server_placeholder() -> str:
    return tr("<server>")


def share_placeholder() -> str:
    return tr("<share>")


def folder_placeholder() -> str:
    return tr("<folder>")


def file_placeholder() -> str:
    """The stem of the file pseudonyms: "File" -> File-1.ifc, File-2.3dm …"""
    return tr("File")

# Folder names that tell where a file is without telling anything about the user or the project.
GENERIC_FOLDERS = {
    name.casefold() for name in (
        "Users", "Benutzer", "home", "Desktop", "Documents", "Dokumente", "Downloads", "AppData", "Local",
        "LocalLow", "Roaming", "Temp", "tmp", "var", "private", "Programs", "Program Files",
        "Program Files (x86)", "ProgramData", "Windows", "Microsoft", "OneDrive", "IFC Converter", "Ausgabe",
        "logs", "rescued", "ifc-converter", ".local", "state", "share", ".config", "Library", "Logs",
        "Application Support", "_internal", "site-packages", "Lib", "dist",
    )
}
# Folders whose subfolder is a user's profile, so its name is the user name.
PROFILE_PARENTS = {name.casefold() for name in ("Users", "Users$", "Benutzer", "home", "Home$", "Profiles$")}
# Program files (in tracebacks): their names are kept, and so are the folders after the last of
# PACKAGE_MARKERS (the package, e.g. site-packages\ifcopenshell\geom\main.py).
CODE_SUFFIXES = {".py", ".pyc", ".pyd", ".pyw", ".dll", ".so", ".exe"}
PACKAGE_MARKERS = {name.casefold() for name in ("site-packages", "_internal", "Lib", "src", "dist-packages")}
# Extensions the converter reads and writes: a file name ends at the first of them, also when it
# contains other dots ("Haus 1.2 final.ifc") and when text follows ("Haus.ifc (12 MB)").
FILE_SUFFIXES = (
    "ifczip", "ifcxml", "ifc", "3dm", "glb", "gltf", "obj", "mtl", "part", "tmp", "txt", "log", "ini", "zip",
    "csv", "json",
)
# Temp entries of the converter (process.py): generated names, nothing personal.
OWN_TEMP_PREFIXES = ("ifc-converter-", "ifc-smoke-")

# Where a path starts: a UNC path, a drive or (POSIX) a slash with at least two segments. Not inside
# words or relative paths ("ifc_converter\\process.py", "1/2").
_PATH_START = re.compile(r'(?<![\w.\\/$~-])(?:\\\\(?=[^\\\s])|[A-Za-z]:[\\/]|/(?=[^\s/"\'<>|]+/))')
# Characters that never occur in a path.
_HARD_STOPS = set('"<>|*?\r\n\t„“”\'')
# Text that ends a folder name: a path never continues after it.
_FOLDER_STOPS = (": ", " -> ", " → ", " – ", "; ", ":")
# Text that ends the last name of a path when it has no known extension.
_NAME_STOPS = (" (", ", ", ": ", "; ", " -> ", " → ", " – ", ")", " [", ":")
_KNOWN_SUFFIX = re.compile(r"\.(?:%s)(?=$|[\s,;:)\]'\"“”.])" % "|".join(FILE_SUFFIXES), re.IGNORECASE)
_ANY_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,8}(?=$|[\s,;:)\]'\"“”])")
_SUFFIX_CHAIN = re.compile(r"\.(?:%s)(?:\.|$)" % "|".join(FILE_SUFFIXES), re.IGNORECASE)
_COPY_NUMBER = re.compile(r" \(\d+\)$")


@functools.lru_cache(maxsize=None)
def _pseudonym_pattern(file_word: str) -> re.Pattern[str]:
    """Matches a name that is a pseudonym already ("File-1.ifc", "File-1 (2).3dm")."""
    return re.compile(rf"^{re.escape(file_word)}-\d+(?: \(\d+\))?(?:\.|$)")
# A file name without a folder, e.g. in a message "Haus_A.ifc wird umgewandelt".
_BARE_FILE = re.compile(
    r"(?<![\w\\/<>.$~-])[\w$~-][^\s\\/\"„“”'<>|:*?,;()]*?\.(?:ifczip|ifcxml|ifc|3dm|glb|gltf|obj|mtl)(?![\w.])",
    re.IGNORECASE,
)
# An element label "IfcCovering 2ZLyRk6BAL6bNsO1TmDoEc „Name“" (converter.product_label): the name goes.
_LABEL_NAME = re.compile(r"(\bIfc[A-Za-z0-9]+ [0-9A-Za-z_$]{22}) „[^“\n]*“")


def own_identity() -> tuple[set[str], set[str]]:
    """The user and computer names of this machine (as far as they can be found out)."""
    users: set[str] = set()
    for source in (lambda: os.environ.get("USERNAME"), lambda: os.environ.get("USER"), getpass.getuser,
                   os.getlogin, lambda: os.path.basename(os.path.expanduser("~"))):
        try:
            users.add(source() or "")
        except Exception:  # noqa: BLE001 - no terminal (os.getlogin), no user in the environment
            pass
    computers: set[str] = set()
    for source in (lambda: os.environ.get("COMPUTERNAME"), socket.gethostname, platform.node):
        try:
            name = source() or ""
        except Exception:  # noqa: BLE001
            continue
        computers.update({name, name.split(".")[0]})
    return users, computers


class Anonymizer:
    """Anonymises text line by line; the same file name gets the same pseudonym in all text it sees.

    ``users`` and ``computers`` default to the names of this machine. Names shorter than 3 characters
    are not replaced outside of paths: they would hit ordinary words.
    """

    def __init__(self, users: Iterable[str] | None = None, computers: Iterable[str] | None = None):
        if users is None or computers is None:
            own_users, own_computers = own_identity()
            users = own_users if users is None else users
            computers = own_computers if computers is None else computers
        self.users = {name.casefold() for name in users if name}
        self.computers = {name.casefold() for name in computers if name}
        self._files: dict[str, int] = {}
        # The placeholders of the language at this moment: one anonymised text uses the same ones throughout.
        self.user, self.computer = user_placeholder(), computer_placeholder()
        self.server, self.share, self.folder = server_placeholder(), share_placeholder(), folder_placeholder()
        self.file = file_placeholder()
        names = [(name, self.user) for name in self.users] + [(name, self.computer) for name in self.computers]
        names = sorted((n for n in names if len(n[0]) >= 3), key=lambda n: -len(n[0]))
        self._identity = [
            (re.compile(rf"(?<![\w$-]){re.escape(name)}(?![\w$])", re.IGNORECASE), token) for name, token in names
        ]

    # ------------------------------------------------------------------ text

    def text(self, text: str) -> str:
        return "\n".join(self.line(line) for line in text.split("\n"))

    def line(self, line: str) -> str:
        line = _LABEL_NAME.sub(r"\1", line)
        line = self._paths(line)
        line = _BARE_FILE.sub(lambda match: self.file_name(match.group(0)), line)
        for pattern, token in self._identity:
            line = pattern.sub(token, line)
        return line

    # ----------------------------------------------------------------- names

    def file_name(self, name: str) -> str:
        """"File-<n>" with the extension(s) of ``name``; the same stem always gets the same number."""
        if _pseudonym_pattern(self.file).match(name):
            return name
        chain = _SUFFIX_CHAIN.search(name)
        if chain and chain.start() > 0:
            stem, rest = name[:chain.start()], name[chain.start():]
        else:
            stem, rest = os.path.splitext(name)
        copy = _COPY_NUMBER.search(stem)
        if copy:  # "Haus (2).3dm", the converter's name for a second output: same file, same number
            stem, rest = stem[:copy.start()], copy.group(0) + rest
        number = self._files.setdefault(stem.casefold(), len(self._files) + 1)
        return f"{self.file}-{number}{rest}"

    def _folder(self, name: str, parent: str | None) -> str:
        key = name.casefold()
        if (parent is not None and parent.casefold() in PROFILE_PARENTS) or key in self.users:
            return self.user
        if key in self.computers:
            return self.computer
        if key in GENERIC_FOLDERS or key.startswith(OWN_TEMP_PREFIXES):
            return name
        return self.folder

    # ----------------------------------------------------------------- paths

    def _paths(self, line: str) -> str:
        out = []
        position = 0
        while True:
            match = _PATH_START.search(line, position)
            if not match:
                out.append(line[position:])
                return "".join(out)
            out.append(line[position:match.start()])
            end, replacement = self._path(line, match.start(), match.group(0))
            out.append(replacement)
            position = end

    def _path(self, line: str, start: int, prefix: str) -> tuple[int, str]:
        """Read the path at ``start``; returns where it ends and its anonymised form."""
        separator = "\\" if prefix.startswith("\\") or "\\" in prefix else "/"
        segments: list[str] = []
        position = start + len(prefix)
        while True:
            end = position
            while end < len(line) and line[end] not in _HARD_STOPS and line[end] not in "\\/":
                end += 1
            segment = line[position:end]
            if end < len(line) and line[end] in "\\/" and _is_folder(segment):
                segments.append(segment)
                position = end + 1
                continue
            last = _last_name(segment)
            if last:
                segments.append(last)
                end = position + len(last)
            elif segments:  # a trailing separator
                end = position
            break
        if not segments:
            return start + len(prefix), prefix
        return end, self._join(prefix, separator, segments)

    def _join(self, prefix: str, separator: str, segments: list[str]) -> str:
        if prefix.startswith("\\\\"):  # \\server\share\...: the share may be the profiles ("Users$")
            server, *names = segments
            head = [self.computer if server.casefold() in self.computers else self.server]
            parent = None
            if names:
                head.append(self.share)
                parent, names = names[0], names[1:]
            lead = "\\\\"
        else:
            head, parent, names, lead = [], None, segments, prefix
        last = names[-1] if names else ""
        is_file = bool(_KNOWN_SUFFIX.search(last) or _ANY_SUFFIX.search(last))
        keep_from = len(names)
        if is_file and os.path.splitext(last)[1].casefold() in CODE_SUFFIXES:
            markers = [i for i, name in enumerate(names[:-1]) if name.casefold() in PACKAGE_MARKERS]
            keep_from = markers[-1] if markers else len(names) - 1
        result = []
        for index, name in enumerate(names):
            if index >= keep_from:
                result.append(name)
            elif index == len(names) - 1 and is_file:
                result.append(self.file_name(name))
            else:
                result.append(self._folder(name, names[index - 1] if index else parent))
        return lead + separator.join([*head, *result])


def _is_folder(segment: str) -> bool:
    """Whether ``segment``, followed by a separator, is a folder of the path (not text after a file name)."""
    return bool(segment) and not any(stop in segment for stop in _FOLDER_STOPS) and not _KNOWN_SUFFIX.search(segment)


def _last_name(segment: str) -> str:
    """The part of ``segment`` (text after a path's last separator) that belongs to the path."""
    match = _KNOWN_SUFFIX.search(segment)
    if match:
        return segment[:match.end()]
    cut = min((segment.find(stop) for stop in _NAME_STOPS if stop in segment), default=len(segment))
    return segment[:cut].rstrip(" .")


def anonymize(text: str, anonymizer: Anonymizer | None = None) -> str:
    """``text`` with personal data replaced (see the module docstring)."""
    return (anonymizer or Anonymizer()).text(text)
