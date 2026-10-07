"""Stress test the converter on real IFC files and report time, peak memory and output quality.

Every conversion runs in its own process, so a crash or an out-of-memory kill only loses that
run, and peak memory is measured per conversion.

    python tools/benchmark.py files/*.ifc --modes 3dm-brep,3dm-mesh,glb --out-dir out --report report.md
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

MODES = {
    "3dm-brep": ("3dm", "brep"),
    "3dm-mesh": ("3dm", "mesh"),
    "glb": ("glb", "brep"),
    "obj": ("obj", "brep"),
}
# Coordinates beyond this lose millimetre precision in single-precision formats (GLB, Rhino mesh vertices).
LARGE_COORDINATE = 100_000.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--modes", default="3dm-brep,3dm-mesh,glb", help=f"comma-separated: {', '.join(MODES)}")
    parser.add_argument("--out-dir", type=Path, default=Path("benchmark-out"))
    parser.add_argument("--report", type=Path, default=Path("benchmark-report.md"))
    parser.add_argument("--timeout", type=float, default=4 * 3600, help="seconds per conversion")
    parser.add_argument("--threads", type=int, help="geometry threads (default: all cores)")
    parser.add_argument("--keep-output", action="store_true", help="keep converted files (default: delete after checks)")
    parser.add_argument("--child", nargs=4, metavar=("IFC", "FMT", "GEOMETRY", "OUT"), help=argparse.SUPPRESS)
    parser.add_argument("--inspect", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.child:
        return _child(*args.child, args.threads)
    if args.inspect:
        print(json.dumps(inspect_output(args.inspect)))
        return 0

    if not args.files:
        parser.error("no IFC files given")
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        parser.error(f"unknown mode(s): {', '.join(unknown)}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.report.with_suffix(".jsonl")

    results = []
    for source in args.files:
        for mode in modes:
            print(f"▶ {source.name} [{mode}] ({source.stat().st_size / 1e6:.0f} MB)", flush=True)
            result = run_one(source, mode, args)
            results.append(result)
            with open(results_path, "a", encoding="utf-8") as log:
                log.write(json.dumps(result) + "\n")
            print(f"  {_summary_line(result)}", flush=True)
            write_report(results, args.report)
    print(f"Report: {args.report}")
    return 0 if all(r["status"] == "ok" for r in results) else 1


def run_one(source: Path, mode: str, args) -> dict:
    fmt, geometry = MODES[mode]
    output = args.out_dir / f"{source.stem}.{mode}.{fmt}"
    for stale in (output, output.with_suffix(".mtl")):
        stale.unlink(missing_ok=True)

    command = [sys.executable, __file__, "--child", str(source), fmt, geometry, str(output)]
    if args.threads:
        command += ["--threads", str(args.threads)]
    started = time.time()
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    sampler = _PeakSampler(process.pid)
    sampler.start()

    events, stderr_lines = [], []
    stderr_reader = threading.Thread(target=lambda: stderr_lines.extend(process.stderr), daemon=True)
    stderr_reader.start()
    timed_out = False
    try:
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):  # libraries may print bare numbers to stdout
                events.append(event)
            if time.time() - started > args.timeout:
                timed_out = True
                process.kill()
                break
        process.wait(timeout=max(1.0, args.timeout - (time.time() - started)))
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    sampler.stop()
    stderr_reader.join(timeout=5)

    result = {
        "file": source.name,
        "size_mb": round(source.stat().st_size / 1e6, 1),
        "mode": mode,
        "seconds": round(time.time() - started, 1),
        "peak_mb": sampler.peak_mb,
        "exit_code": process.returncode,
    }
    done = next((e for e in events if e.get("event") == "done"), None)
    error = next((e for e in events if e.get("event") == "error"), None)
    read = next((e for e in events if e.get("event") == "progress" and e["percent"] == 0), None)
    result["read_seconds"] = read["t"] if read else None

    if done:
        result.update(status="ok", elements=done["elements"], skipped=done.get("skipped", 0),
                      output_mb=round(_output_size(output) / 1e6, 1))
        result["checks"] = _inspect_in_subprocess(output)
    elif timed_out:
        result.update(status="timeout", error=f"over {args.timeout:.0f} s")
    elif error:
        result.update(status="error", error=f"{error['type']}: {error['message']}"[:500])
    elif process.returncode and process.returncode < 0:
        number = -process.returncode
        if number == signal.SIGKILL:
            result.update(status="killed", error="SIGKILL (out of memory?)")
        else:
            result.update(status="crashed", error=f"{signal.Signals(number).name} (native crash)")
    else:
        tail = "".join(stderr_lines[-5:]).strip()
        result.update(status="crashed", error=f"exit code {process.returncode}: {tail}"[:500])

    if not args.keep_output:
        for path in (output, output.with_suffix(".mtl")):
            path.unlink(missing_ok=True)
    return result


def _child(source: str, fmt: str, geometry: str, output: str, threads: int | None) -> int:
    """Convert one file and report progress as JSON lines on stdout."""
    start = time.time()
    # The geometry kernels print debug output to the C-level stdout; keep our events on a copy of it.
    events = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    os.close(devnull)

    def emit(**event) -> None:
        events.write(json.dumps({"t": round(time.time() - start, 2), **event}) + "\n")

    last = -1

    def progress(percent: int) -> None:
        nonlocal last
        if percent != last:
            last = percent
            emit(event="progress", percent=percent)

    from ifc_converter import convert

    try:
        result = convert(source, output, fmt, threads, progress, geometry=geometry)
    except Exception as exc:
        emit(event="error", type=type(exc).__name__, message=str(exc))
        return 1
    emit(event="done", elements=result.elements, skipped=result.skipped)
    return 0


class _PeakSampler(threading.Thread):
    """Tracks the peak resident memory of a process (Linux /proc, or psutil if installed)."""

    def __init__(self, pid: int):
        super().__init__(daemon=True)
        self.pid = pid
        self.peak_mb = 0
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            rss = _rss_mb(self.pid)
            if rss is not None:
                self.peak_mb = max(self.peak_mb, rss)
            self._halt.wait(0.1)

    def stop(self) -> None:
        self._halt.set()
        self.join(timeout=2)


def _rss_mb(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/status") as status:
            for line in status:
                if line.startswith("VmHWM:"):  # the kernel's own peak, so short spikes are not missed
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    try:
        import psutil

        return psutil.Process(pid).memory_info().rss // 2 ** 20
    except Exception:
        return None


def _output_size(output: Path) -> int:
    return sum(p.stat().st_size for p in (output, output.with_suffix(".mtl")) if p.exists())


def _inspect_in_subprocess(output: Path) -> dict:
    """Inspect the output in a separate process so reading a huge file doesn't skew anything."""
    try:
        completed = subprocess.run(
            [sys.executable, __file__, "--inspect", str(output)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600,
        )
        lines = completed.stdout.strip().splitlines()
        if not lines:
            tail = completed.stderr.strip().splitlines()[-1:] or [""]
            return {"inspect_error": f"exit code {completed.returncode}: {tail[0]}"[:300]}
        return json.loads(lines[-1])
    except Exception as exc:
        return {"inspect_error": f"{type(exc).__name__}: {exc}"[:300]}


def inspect_output(output: Path) -> dict:
    suffix = output.suffix.lower()
    if suffix == ".3dm":
        return _inspect_3dm(output)
    if suffix == ".glb":
        return _inspect_glb(output)
    if suffix == ".obj":
        return _inspect_obj(output)
    return {}


def _inspect_3dm(path: Path) -> dict:
    import rhino3dm

    model = rhino3dm.File3dm.Read(str(path))
    if model is None:
        return {"readable": False}
    checks = {"readable": True, "breps": 0, "valid_breps": 0, "solid_breps": 0, "meshes": 0, "other": 0,
              "no_user_text": 0, "layers": len(model.Layers)}
    low, high = [math.inf] * 3, [-math.inf] * 3
    for obj in model.Objects:
        geometry = obj.Geometry
        if isinstance(geometry, rhino3dm.Brep):
            checks["breps"] += 1
            checks["valid_breps"] += geometry.IsValid
            checks["solid_breps"] += geometry.IsSolid
        elif isinstance(geometry, rhino3dm.Mesh):
            checks["meshes"] += 1
        else:
            checks["other"] += 1
        if obj.Attributes.UserStringCount == 0:
            checks["no_user_text"] += 1
        box = geometry.GetBoundingBox()
        for i, (lo, hi) in enumerate(((box.Min.X, box.Max.X), (box.Min.Y, box.Max.Y), (box.Min.Z, box.Max.Z))):
            low[i], high[i] = min(low[i], lo), max(high[i], hi)
    return checks | _extent(low, high)


def _inspect_glb(path: Path) -> dict:
    import struct

    with open(path, "rb") as glb:
        magic, version, length = struct.unpack("<4sII", glb.read(12))
        chunk_length, _ = struct.unpack("<II", glb.read(8))
        document = json.loads(glb.read(chunk_length))
    if magic != b"glTF":
        return {"readable": False}
    low, high = [math.inf] * 3, [-math.inf] * 3
    for accessor in document.get("accessors", []):
        if accessor.get("type") == "VEC3" and "min" in accessor and "max" in accessor:
            low = [min(a, b) for a, b in zip(low, accessor["min"])]
            high = [max(a, b) for a, b in zip(high, accessor["max"])]
    # Node translations move the geometry; report them too so large offsets are visible.
    offsets = [abs(v) for node in document.get("nodes", []) for v in node.get("translation", [])]
    offsets += [abs(v) for node in document.get("nodes", []) for v in node.get("matrix", [])[12:15]]
    return {
        "readable": True,
        "length_matches": length == path.stat().st_size,
        "meshes": len(document.get("meshes", [])),
        "nodes": len(document.get("nodes", [])),
        "max_node_offset": round(max(offsets, default=0.0), 1),
    } | _extent(low, high)


def _inspect_obj(path: Path) -> dict:
    vertices = faces = 0
    low, high = [math.inf] * 3, [-math.inf] * 3
    with open(path, errors="replace") as obj:
        for line in obj:
            if line.startswith("v "):
                vertices += 1
                xyz = [float(v) for v in line.split()[1:4]]
                low = [min(a, b) for a, b in zip(low, xyz)]
                high = [max(a, b) for a, b in zip(high, xyz)]
            elif line.startswith("f "):
                faces += 1
    return {"readable": True, "vertices": vertices, "faces": faces} | _extent(low, high)


def _extent(low: list[float], high: list[float]) -> dict:
    if not all(math.isfinite(v) for v in low + high):
        return {"extent_m": None, "max_abs_coordinate": None, "large_coordinates": False}
    max_abs = max(abs(v) for v in low + high)
    return {
        "extent_m": [round(h - l, 1) for l, h in zip(low, high)],
        "max_abs_coordinate": round(max_abs, 1),
        "large_coordinates": max_abs > LARGE_COORDINATE,
    }


def _summary_line(result: dict) -> str:
    if result["status"] != "ok":
        return f"✗ {result['status']}: {result.get('error', '')} ({result['seconds']} s, peak {result['peak_mb']} MB)"
    return (f"✓ {result['elements']} elements, {result['seconds']} s, peak {result['peak_mb']} MB, "
            f"{result['output_mb']} MB out, checks {result.get('checks')}")


def write_report(results: list[dict], path: Path) -> None:
    lines = [
        "# Converter benchmark",
        "",
        "| file | MB | mode | status | s (read) | peak MB | elements | out MB | breps valid/solid/total · meshes | extent m | max coord | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        c = r.get("checks") or {}
        geometry = (f"{c.get('valid_breps')}/{c.get('solid_breps')}/{c.get('breps')} · {c.get('meshes')}"
                    if "breps" in c else c.get("meshes", ""))
        notes = r.get("error", "")
        if r.get("skipped"):
            notes += f" {r['skipped']} without geometry"
        if c.get("large_coordinates") or (c.get("max_node_offset") or 0) > LARGE_COORDINATE:
            notes += " ⚠ large coordinates"
        if c.get("no_user_text"):
            notes += f" ⚠ {c['no_user_text']} objects without user text"
        if c.get("breps") and c.get("valid_breps") != c.get("breps"):
            notes += " ⚠ invalid breps"
        if c.get("inspect_error"):
            notes += f" ⚠ inspect: {c['inspect_error']}"
        lines.append(
            f"| {r['file']} | {r['size_mb']} | {r['mode']} | {r['status']} | {r['seconds']} ({r.get('read_seconds')}) "
            f"| {r['peak_mb']} | {r.get('elements', '')} | {r.get('output_mb', '')} | {geometry} "
            f"| {c.get('extent_m', '')} | {c.get('max_abs_coordinate', '')} | {notes.strip()} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
