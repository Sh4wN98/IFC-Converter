"""The text of a GitHub release: the newest section of CHANGELOG.md plus the download line.

    python packaging/release_notes.py CHANGELOG.md --version 0.5.0 > notes.md

The newest section is the first "## " block of the changelog, without its heading line. With
--version, that heading must name exactly this version (the tag's), otherwise the script fails: a
release must not go out with the notes of the previous version or with a placeholder section.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# A placeholder the changelog carries until the section is written (see CHANGELOG.md).
PLACEHOLDER = "(wird vor dem Release ergänzt)"


def top_section(changelog: str) -> tuple[str, str]:
    """The heading text (without "## ") and the body of the first "## " section, both stripped."""
    lines = changelog.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("## ")]
    if not starts:
        raise ValueError("the changelog has no '## ' section")
    first = starts[0]
    end = starts[1] if len(starts) > 1 else len(lines)
    heading = lines[first][3:].strip()
    body = "\n".join(lines[first + 1:end]).strip()
    return heading, body


def section_version(heading: str) -> str:
    """The version number a changelog heading like "0.5.0 – 2026-10-19" starts with."""
    match = re.match(r"v?(\d+(?:\.\d+)*(?:[-+.][0-9A-Za-z.]+)?)", heading)
    return match.group(1) if match else ""


def download_line(version: str) -> str:
    return (
        f"**Download:** `IFC-Converter-{version}-Setup.exe` (Windows-Installer, ohne Administratorrechte), "
        f"`IFC-Converter-{version}-portable.zip` (Windows, nur entpacken), "
        f"`IFC-Converter-{version}-linux-x86_64.tar.gz` (Linux, darin `install.sh`), "
        f"`SHA256SUMS.txt` (Prüfsummen aller Dateien). Immer die neueste Version: "
        f"[IFC-Converter-Setup.exe](https://github.com/Sh4wN98/IFC-Converter/releases/latest/download/IFC-Converter-Setup.exe), "
        f"[IFC-Converter-Guide.pdf](https://github.com/Sh4wN98/IFC-Converter/releases/latest/download/IFC-Converter-Guide.pdf)."
    )


def release_notes(changelog: str, version: str | None = None) -> str:
    """The notes for ``version`` (checked against the newest section if given)."""
    heading, body = top_section(changelog)
    found = section_version(heading)
    if version is not None and found != version:
        raise ValueError(f"the newest changelog section is {found or heading!r}, not {version}")
    if not body or PLACEHOLDER in body:
        raise ValueError(f"the changelog section {heading!r} is still empty or a placeholder")
    return f"{body}\n\n{download_line(version or found)}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("changelog", type=Path, help="CHANGELOG.md")
    parser.add_argument("--version", help="the version being released (must be the newest section)")
    args = parser.parse_args()
    try:
        notes = release_notes(args.changelog.read_text(encoding="utf-8"), args.version)
    except (OSError, ValueError) as exc:
        sys.exit(f"release notes: {exc}")
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
