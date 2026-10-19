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
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# The header is within the first bytes of any STEP file; 16 KB covers long FILE_DESCRIPTIONs.
HEADER_BYTES = 16 * 1024
_SCHEMA = re.compile(rb"FILE_SCHEMA\s*\(\s*\(\s*'([A-Za-z0-9_]+)'\s*\)\s*\)")
_ENTITY = re.compile(rb"^(#\d+\s*=\s*)([A-Z0-9_]+)(\s*\()")


@dataclass(frozen=True)
class Bridge:
    target: str  # the schema the copy declares
    label: str  # German name of the source schema for messages
    renamed: dict[bytes, bytes] = field(default_factory=dict)  # entity name -> IFC counterpart
    dropped: frozenset[bytes] = frozenset()  # entities without a counterpart, left out
    note: str = ""  # what the user should know


BRIDGES: dict[str, Bridge] = {
    "IFC2X2_FINAL": Bridge("IFC2X3", "IFC2x2", note="IFC2x2 (2003) wird als IFC2x3 gelesen, das seine Bauteile und "
                           "Attribute übernommen hat."),
    "IFC2X2": Bridge("IFC2X3", "IFC2x2", note="IFC2x2 (2003) wird als IFC2x3 gelesen, das seine Bauteile und "
                     "Attribute übernommen hat."),
    "IFC4X4": Bridge(
        "IFC4X3_ADD2", "IFC4x4 (Entwurf)",
        renamed={
            b"IFCTUNNEL": b"IFCFACILITY",
            b"IFCTUNNELPART": b"IFCFACILITYPART",
            b"IFCUNDERGROUNDEXCAVATION": b"IFCBUILDINGELEMENTPROXY",
            b"IFCARCHELEMENT": b"IFCBUILDINGELEMENTPROXY",
        },
        dropped=frozenset({b"IFCDATASETINFORMATION", b"IFCRELASSOCIATESDATASET"}),
        note="IFC4x4 ist ein unveröffentlichter Entwurf (Tunnel) und wird als IFC4.3 gelesen: IfcTunnel als "
             "IfcFacility, IfcTunnelPart als IfcFacilityPart, IfcUndergroundExcavation und IfcArchElement als "
             "IfcBuildingElementProxy; Datensatz-Verweise (IfcDataSetInformation) entfallen.",
    ),
}


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
            counts.append(f"{self.renamed} Entitäten umbenannt")
        if self.dropped:
            counts.append(f"{self.dropped} ausgelassen")
        return self.bridge.note + (f" ({', '.join(counts)})." if counts else "")

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
    folder = Path(tempfile.mkdtemp(prefix="ifc-converter-bridge-"))
    copy = folder / path.name
    result = Bridged(copy, bridge)
    target = bridge.target.encode("ascii")
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
    return result
