"""Reading IFC schemas IfcOpenShell does not know, as the closest schema it knows.

IfcOpenShell 0.9 ships IFC2X3, IFC4, IFC4X1, IFC4X2 and IFC4X3 (ADD1, ADD2, TC1). Two more turn up
in practice:

- **IFC2X2** (2003): IFC2X3 kept its entities and attributes (it mostly added), so a file declared as
  IFC2X2 reads as IFC2X3 once the header says so. The 10 MB "Energy Tower" of the test corpus
  (234,074 entities) parses completely that way and converts.
- **IFC4X4** (draft, tunnels): IFC4X3_ADD2 plus a handful of draft entities. Those are mapped to
  their IFC4.3 counterparts (a tunnel is a facility, an excavation or arch element is an element
  with a body), the two dataset records have no counterpart and are left out. The Trimble tunnel
  of the corpus (695,000 entities) then gives 21 products, 16 with geometry.

The bridge rewrites a copy of the file in the local temp folder, line by line, and the conversion
reads that copy; the original is never touched. Dimensions are not affected: only entity names and
the header change.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ifc_converter.i18n import tr

# The header is within the first bytes of any STEP file; 16 KB covers long FILE_DESCRIPTIONs.
HEADER_BYTES = 16 * 1024
# Free space the temp folder must keep beyond the copy (staging and checkpoints use it too).
COPY_ROOM = 512 * 1024 ** 2
_SCHEMA = re.compile(rb"FILE_SCHEMA\s*\(\s*\(\s*'([A-Za-z0-9_]+)'\s*\)\s*\)")
_ENTITY = re.compile(rb"^(#\d+\s*=\s*)([A-Z0-9_]+)(\s*\()")


@dataclass(frozen=True)
class Bridge:
    target: str  # the schema the copy declares
    label: Callable[[], str]  # name of the source schema for messages, in the user's language when called
    renamed: dict[bytes, bytes] = field(default_factory=dict)  # entity name -> IFC counterpart
    dropped: frozenset[bytes] = frozenset()  # entities without a counterpart, left out
    note: Callable[[], str] = lambda: ""  # what the user should know, in the user's language when called
    alias: bool = False  # the same schema under another header name (not listed as a bridged version)


def _ifc2x2_note() -> str:
    return tr("IFC2x2 (2003) is read as IFC2x3, which took over its entities and attributes.")


def _ifc4x4_note() -> str:
    return tr("IFC4x4 is an unpublished draft (tunnels) and is read as IFC4.3: IfcTunnel as IfcFacility, "
              "IfcTunnelPart as IfcFacilityPart, IfcUndergroundExcavation and IfcArchElement as "
              "IfcBuildingElementProxy; dataset references (IfcDataSetInformation) are dropped.")


def _alias(declared: str, target: str) -> Bridge:
    """``declared`` is ``target`` under another name (a technical corrigendum, addendum or release
    candidate): read as such, with a note."""
    return Bridge(target, lambda: declared, alias=True,
                  note=lambda: tr("{declared} is read as {target} (the same schema under another name).",
                                  declared=declared, target=target))


# Header names IfcOpenShell does not know but which name a schema it knows.
ALIASES = {
    "IFC2X2_ADD1": "IFC2X3", "IFC2X3_TC1": "IFC2X3", "IFC2X3_FINAL": "IFC2X3",
    "IFC4_ADD1": "IFC4", "IFC4_ADD2": "IFC4", "IFC4_ADD2_TC1": "IFC4",
    "IFC4X3_RC1": "IFC4X3_ADD2", "IFC4X3_RC2": "IFC4X3_ADD2", "IFC4X3_RC3": "IFC4X3_ADD2", "IFC4X3_RC4": "IFC4X3_ADD2",
}

BRIDGES: dict[str, Bridge] = {
    "IFC2X2_FINAL": Bridge("IFC2X3", lambda: "IFC2x2", note=_ifc2x2_note),
    "IFC2X2": Bridge("IFC2X3", lambda: "IFC2x2", note=_ifc2x2_note),
    "IFC4X4": Bridge(
        "IFC4X3_ADD2", lambda: tr("IFC4x4 (draft)"),
        renamed={
            b"IFCTUNNEL": b"IFCFACILITY",
            b"IFCTUNNELPART": b"IFCFACILITYPART",
            b"IFCUNDERGROUNDEXCAVATION": b"IFCBUILDINGELEMENTPROXY",
            b"IFCARCHELEMENT": b"IFCBUILDINGELEMENTPROXY",
        },
        dropped=frozenset({b"IFCDATASETINFORMATION", b"IFCRELASSOCIATESDATASET"}),
        note=_ifc4x4_note,
    ),
}
BRIDGES.update({declared: _alias(declared, target) for declared, target in ALIASES.items()})


def declared_schema(path: str | Path) -> str | None:
    """The schema a STEP file's header declares (upper case), or None if there is no header."""
    try:
        with open(path, "rb") as file:
            match = _SCHEMA.search(file.read(HEADER_BYTES))
    except OSError:
        return None
    return match.group(1).decode("ascii").upper() if match else None


def bridge_for(path: str | Path) -> Bridge | None:
    """The bridge a file needs to be read, or None if IfcOpenShell reads it as it is."""
    schema = declared_schema(path)
    return BRIDGES.get(schema) if schema else None


@dataclass
class Bridged:
    path: Path  # the rewritten copy
    bridge: Bridge
    renamed: int = 0  # entity instances renamed
    dropped: int = 0  # entity instances left out

    @property
    def note(self) -> str:
        counts = []
        if self.renamed:
            counts.append(tr("{count} entities renamed", count=self.renamed))
        if self.dropped:
            counts.append(tr("{count} left out", count=self.dropped))
        return self.bridge.note() + (f" ({', '.join(counts)})." if counts else "")

    def remove(self) -> None:
        try:
            self.path.unlink()
            self.path.parent.rmdir()
        except OSError:
            pass


def bridged_copy(path: str | Path, bridge: Bridge) -> Bridged:
    """Write the copy of ``path`` that declares ``bridge.target`` into a new temp folder
    (``ifc-converter-*``, cleared by the usual temp cleanup should the process die)."""
    path = Path(path)
    size = path.stat().st_size
    free = shutil.disk_usage(tempfile.gettempdir()).free
    if free < size + COPY_ROOM:
        raise OSError(tr("Not enough free space in the temp folder for a working copy of the file ({needed} needed, "
                         "{free} free).", needed=_gb(size + COPY_ROOM), free=_gb(free)))
    folder = Path(tempfile.mkdtemp(prefix="ifc-converter-bridge-"))
    copy = folder / path.name
    result = Bridged(copy, bridge)
    target = bridge.target.encode("ascii")
    try:
        with open(path, "rb") as source, open(copy, "wb") as out:
            in_header = True
            for line in source:
                if in_header:
                    line, found = _SCHEMA.subn(b"FILE_SCHEMA(('" + target + b"'))", line, count=1)
                    if found or line.startswith(b"DATA;"):
                        in_header = line.strip() != b"DATA;" and not found
                elif bridge.renamed or bridge.dropped:
                    match = _ENTITY.match(line)
                    if match:
                        name = match.group(2)
                        if name in bridge.dropped:
                            result.dropped += 1
                            continue
                        replacement = bridge.renamed.get(name)
                        if replacement:
                            line = match.group(1) + replacement + match.group(3) + line[match.end():]
                            result.renamed += 1
                out.write(line)
        os.chmod(copy, 0o600)
    except BaseException:  # also a cancel (KeyboardInterrupt): no half-written copy stays behind
        result.remove()
        raise
    return result


def _gb(size: int) -> str:
    return f"{size / 1024 ** 3:.1f} GB"
