from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from pathlib import Path

from ifc_converter import __version__
from ifc_converter.converter import FORMATS, GEOMETRIES, KERNELS
from ifc_converter.interactive import check_memory, convert_in_terminal, skipped_warning
from ifc_converter.process import SPARE_CORES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ifc-convert",
        description="Convert IFC building models to 3D formats.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
    parser.add_argument(
        "-j", "--threads", type=int, help=f"geometry threads (default: all CPU cores but {SPARE_CORES})",
    )
    parser.add_argument(
        "--normal-priority", action="store_true",
        help="convert at normal priority (default: below normal, so the PC stays responsive)",
    )
    parser.add_argument(
        "--kernel", choices=KERNELS,
        help="geometry kernel: accurate (default: OpenCASCADE, the hybrid kernel only for large triangle meshes), "
             "hybrid (3-13x faster, may drop or duplicate faces of some elements) or opencascade (everything)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Conversions run in "spawn" child processes. A frozen build (e.g. PyInstaller) starts its own
    # executable for them; this makes it do the child's work instead of parsing the child's arguments
    # as IFC files. A no-op otherwise.
    multiprocessing.freeze_support()
    parser = build_parser()
    args = parser.parse_args(argv)
    if argv is None:  # a real command line, not a call from Python code (tests, scripts)
        from ifc_converter.app import setup_logging

        setup_logging("CLI")
    if args.kernel:
        # Inherited by the child processes that do the conversions.
        os.environ["IFC_CONVERTER_KERNEL"] = args.kernel

    if not args.inputs:
        from ifc_converter.interactive import run

        return run(args.format, args.out_dir, args.geometry, low_priority=not args.normal_priority)

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
                source, target, args.format, args.threads, args.geometry, label=f"{source.name}: ",
                on_retry=lambda message: print(f"⚠ {source.name}: {message}", file=sys.stderr),
                low_priority=not args.normal_priority,
            )
        except Exception as exc:
            print(f"✗ {source}: {exc}", file=sys.stderr)
            failed += 1
            continue
        skipped = f", {result.skipped} without geometry" if result.skipped > 0 else ""
        print(f"✓ {source} → {result.output} ({result.elements} elements{skipped})")
        if result.skipped > 0:
            print(f"⚠ {source.name}: {skipped_warning(result.skipped)}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
