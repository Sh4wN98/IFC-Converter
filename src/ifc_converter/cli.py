from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ifc_converter.converter import FORMATS, GEOMETRIES
from ifc_converter.interactive import check_memory, convert_in_terminal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ifc-convert",
        description="Convert IFC building models to 3D formats.",
    )
    parser.add_argument(
        "inputs", nargs="*", type=Path,
        help="IFC file(s) to convert; without any, starts drag-and-drop mode",
    )
    parser.add_argument(
        "-f", "--format", choices=FORMATS, default="glb",
        help="output format: glb, obj or 3dm (Rhino) (default: glb)",
    )
    parser.add_argument(
        "-g", "--geometry", choices=GEOMETRIES, default="brep",
        help="3dm only: brep = joined polysurfaces (very detailed elements stay meshes), "
             "mesh = meshes only (default: brep)",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("-o", "--output", type=Path, help="output file (only with a single input)")
    target.add_argument("-d", "--out-dir", type=Path, help="directory for the converted files")
    parser.add_argument("-j", "--threads", type=int, help="geometry threads (default: all CPU cores)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.inputs:
        from ifc_converter.interactive import run

        return run(args.format, args.out_dir, args.geometry)

    if args.output and len(args.inputs) > 1:
        parser.error("--output only works with a single input; use --out-dir instead")

    failed = 0
    for source in args.inputs:
        if args.output:
            target = args.output
        elif args.out_dir:
            target = args.out_dir / source.with_suffix(f".{args.format}").name
        else:
            target = None

        warning = check_memory(source)
        if warning:
            print(f"⚠ {warning}", file=sys.stderr)
        try:
            # In a child process, so running out of memory or a crash only fails this file.
            result = convert_in_terminal(
                source, target, args.format, args.threads, args.geometry, label=f"{source.name}: "
            )
        except Exception as exc:
            print(f"✗ {source}: {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"✓ {source} → {result.output} ({result.elements} elements)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
