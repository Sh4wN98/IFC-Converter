from __future__ import annotations

import argparse
import multiprocessing
import os
import signal
import sys
from pathlib import Path

from ifc_converter import __version__, i18n
from ifc_converter.app import log_path
from ifc_converter.converter import FORMATS, GEOMETRIES, KERNELS
from ifc_converter.interactive import (
    check_memory,
    convert_in_terminal,
    crashed_warning,
    error_message,
    failure_hint,
    is_internal_error,
    skipped_warning,
)
from ifc_converter.process import auto_threads


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ifc-convert",
        description="Convert IFC building models to 3D formats.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "inputs", nargs="*", type=Path,
        help="IFC file(s) to convert (.ifc or .ifczip); without any, starts drag-and-drop mode",
    )
    parser.add_argument(
        "-f", "--format", choices=FORMATS, default="glb",
        help="output format: glb, obj, 3dm (Rhino) or dae (Collada) (default: glb)",
    )
    parser.add_argument(
        "-g", "--geometry", choices=GEOMETRIES, default="brep",
        help="3dm only: brep = joined polysurfaces (very detailed elements stay meshes), "
             "mesh = meshes only (default: brep)",
    )
    parser.add_argument(
        "--blocks", action="store_true",
        help="3dm only: type geometry placed several times becomes Rhino blocks (smaller file; "
             "explode an instance in Rhino to edit it)",
    )
    parser.add_argument(
        "--envelope", "--hull", action="store_true",
        help="only the building hull: elements inside the building (interior walls, furniture, fittings, MEP) "
             "are left out; the output is much smaller (a short extra pass computes coarse geometry first)",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("-o", "--output", type=Path, help="output file (only with a single input)")
    target.add_argument("-d", "--out-dir", type=Path, help="directory for the converted files")
    parser.add_argument(
        "-j", "--threads", type=int,
        help=f"geometry threads (default: automatic, {auto_threads()} on this PC; with the 3dm worker processes "
        "about half the CPU cores)",
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
    parser.add_argument(
        "--lang", choices=list(i18n.LANGUAGES), default=i18n.language_from_environment(),
        help="language of the messages about the conversions (default: the IFC_CONVERTER_LANG environment "
             "variable, else en); the help and the result lines stay English",
    )
    return parser


def _interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


def cancel_on_signals() -> None:
    """Let Ctrl+Break (Windows) and SIGTERM cancel like Ctrl+C: the running conversion is stopped and its
    temp files and partial output are removed, instead of the process ending on the spot."""
    for name in ("SIGBREAK", "SIGTERM"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), _interrupt)
            except (OSError, ValueError):  # not the main thread
                pass


def main(argv: list[str] | None = None) -> int:
    # Conversions run in "spawn" child processes. A frozen build (e.g. PyInstaller) starts its own
    # executable for them; this makes it do the child's work instead of parsing the child's arguments
    # as IFC files. A no-op otherwise.
    multiprocessing.freeze_support()
    parser = build_parser()
    args = parser.parse_args(argv)
    # Before anything prints or starts a child process: the children inherit the language.
    i18n.set_language(args.lang)
    if argv is None:  # a real command line, not a call from Python code (tests, scripts)
        from ifc_converter.app import hold_app_mutex, setup_logging
        from ifc_converter.process import remove_stale_temp_files

        setup_logging("CLI")
        hold_app_mutex()
        remove_stale_temp_files()
        cancel_on_signals()
    if args.kernel:
        # Inherited by the child processes that do the conversions.
        os.environ["IFC_CONVERTER_KERNEL"] = args.kernel

    if not args.inputs:
        from ifc_converter.interactive import run

        return run(
            args.format, args.out_dir, args.geometry, low_priority=not args.normal_priority, blocks=args.blocks,
            envelope=args.envelope,
        )

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
                low_priority=not args.normal_priority, blocks=args.blocks, envelope=args.envelope,
            )
        except KeyboardInterrupt:
            print(f"■ {source}: abgebrochen", file=sys.stderr)
            return 130
        except Exception as exc:
            print(f"✗ {source}: {error_message(exc)}", file=sys.stderr)
            print(f"  {failure_hint(is_internal_error(exc), str(log_path()))}", file=sys.stderr)
            failed += 1
            continue
        skipped = f", {result.skipped} without geometry" if result.skipped > 0 else ""
        inside = f", {result.inside} inside left out" if result.inside > 0 else ""
        print(f"✓ {source} → {result.output} ({result.elements} elements{skipped}{inside})")
        if result.crashed:
            print(f"⚠ {source.name}: {crashed_warning(result.crashed)}", file=sys.stderr)
        if result.skipped > 0:
            print(f"⚠ {source.name}: {skipped_warning(result.skipped)}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
