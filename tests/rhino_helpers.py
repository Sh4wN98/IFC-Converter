"""Stand-ins for the Rhino export's worker function (they run in its worker processes, so they must be importable)."""

import os

from ifc_converter import rhino

# The element whose geometry kills the worker, and whether only as a polysurface ("brep") or "always".
CRASH_ELEMENT = "IFC_CONVERTER_TEST_CRASH_ELEMENT"
CRASH_MODE = "IFC_CONVERTER_TEST_CRASH_MODE"


def crash_on_element(jobs):
    """rhino._build_batch, but the process dies on the element named in CRASH_ELEMENT, like a native crash."""
    for job in jobs:
        if str(job[0]) == os.environ.get(CRASH_ELEMENT) and (job[1] or os.environ.get(CRASH_MODE) == "always"):
            os._exit(3)
    results = []
    for job in jobs:
        geometry = rhino._build_from_buffers(*job[1:])
        kind = "brep" if isinstance(geometry, rhino.rhino3dm.Brep) else "mesh"
        results.append(None if geometry is None else (kind, geometry.Encode()))
    return results
