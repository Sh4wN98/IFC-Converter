"""Stand-ins for convert() that run in the conversion child process (so they must be importable)."""

import os
import signal
import sys
import threading
import time
from pathlib import Path

from ifc_converter.converter import ConversionResult, convert


def report_pid(input_path, output_path, fmt, threads, progress=None, **options):
    """Write the process id into the output file instead of converting."""
    progress(0)
    Path(output_path).write_text(str(os.getpid()))
    progress(100)
    return ConversionResult(output=Path(output_path), elements=1)


def killed_if_named_crash(input_path, output_path, fmt, threads, progress=None, **options):
    """Get SIGKILLed like by the OOM killer for files named crash.ifc; convert anything else."""
    if Path(input_path).stem == "crash":
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("partial")
        os.kill(os.getpid(), signal.SIGKILL)
    return convert(input_path, output_path, fmt, threads, progress, **options)


def exit_hard(input_path, output_path, fmt, threads, progress=None, **options):
    """End the process without a result, like a native crash."""
    os._exit(3)


def raise_error(input_path, output_path, fmt, threads, progress=None, **options):
    raise ValueError(f"{Path(input_path).name} ist kaputt")


def raise_bare_error(input_path, output_path, fmt, threads, progress=None, **options):
    raise KeyError


def sleep_while_reading(input_path, output_path, fmt, threads, progress=None, **options):
    """Leave the process id beside the output, then sleep like a very long read of the IFC file."""
    Path(output_path).with_suffix(".pid").write_text(str(os.getpid()))
    Path(output_path).write_text("partial")
    time.sleep(120)
    raise AssertionError("should have been terminated")


def interrupted_then_convert(input_path, output_path, fmt, threads, progress=None, **options):
    """Get a Ctrl+C (SIGINT), as the whole terminal process group does, then convert normally."""
    os.kill(os.getpid(), signal.SIGINT)
    time.sleep(0.2)
    return convert(input_path, output_path, fmt, threads, progress, **options)


def report_skipped(input_path, output_path, fmt, threads, progress=None, **options):
    """Write a stand-in output and report 3 elements whose geometry could not be converted."""
    progress(0)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("fake")
    progress(100)
    return ConversionResult(output=Path(output_path), elements=1, skipped=3)


def _segfault():
    """Crash with SIGSEGV like native code, but without leaving a core dump on the developer's machine."""
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.kill(os.getpid(), signal.SIGSEGV)


def _record_attempt(output_path, kernel):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(Path(output_path).with_suffix(".attempts"), "a") as attempts:
        attempts.write(f"{kernel}\n")


def _segfault_in_kernel(options):
    """Crash natively while the kernel computes products, where no narrower recovery is left to try."""
    options["position"]("chunk", [], "")
    _segfault()


def segfault_unless_opencascade(input_path, output_path, fmt, threads, progress=None, kernel=None, **options):
    """Crash natively (SIGSEGV) like the hybrid kernel on some models; convert with OpenCASCADE."""
    _record_attempt(output_path, kernel)
    if kernel != "opencascade":
        progress(0)
        progress(40)
        _segfault_in_kernel(options)
    return convert(input_path, output_path, fmt, threads, progress, kernel=kernel, **options)


def always_segfault(input_path, output_path, fmt, threads, progress=None, kernel=None, **options):
    _record_attempt(output_path, kernel)
    _segfault_in_kernel(options)


def segfault_while_reading(input_path, output_path, fmt, threads, progress=None, kernel=None, status=None, **options):
    """Crash natively while reading the IFC file, before the kernel computed anything."""
    _record_attempt(output_path, kernel)
    status("read", "IFC-Datei wird gelesen …")
    _segfault()


def segfault_while_writing(input_path, output_path, fmt, threads, progress=None, kernel=None, status=None, **options):
    """Crash natively while writing the output, after the kernel computed every product."""
    _record_attempt(output_path, kernel)
    options["position"]("chunk", [1, 2], "")
    status("write", "Rhino-Datei wird geschrieben (2 Objekte) …")
    _segfault()


def crash_in_curve_pass(input_path, output_path, fmt, threads, progress=None, **options):
    """Crash natively when the Rhino export computes the curves of alignments and grids."""
    from ifc_converter import rhino

    curve_shapes = rhino._curve_shapes

    def crashing(model, elements):
        for shape in curve_shapes(model, elements):
            _segfault()
            yield shape

    rhino._curve_shapes = crashing
    return convert(input_path, output_path, fmt, threads, progress, **options)


def leave_glb_temp_files_and_segfault(input_path, output_path, fmt, threads, progress=None, **options):
    """Crash while the GLB serializer's temporary files exist, like a crash in the geometry kernel."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", ".indices.tmp", ".vertices.tmp"):
        Path(f"{output_path}{suffix}").write_text("partial")
    _segfault()


def chatty_native_code(input_path, output_path, fmt, threads, progress=None, **options):
    """Write to the C-level stdout like IfcOpenShell's kernels do for some shapes, then convert."""
    os.write(1, b"local z: 0.00298264,0.0126555,0.999915\n")
    print("python-level chatter")
    return convert(input_path, output_path, fmt, threads, progress, **options)


def report_priority(input_path, output_path, fmt, threads, progress=None, **options):
    """Write the child's scheduling priority into the output file: the Windows priority class, or the nice value."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetPriorityClass.argtypes = (ctypes.c_void_p,)
        value = kernel32.GetPriorityClass(kernel32.GetCurrentProcess())
    else:
        value = os.getpriority(os.PRIO_PROCESS, 0)
    Path(output_path).write_text(str(value))
    return ConversionResult(output=Path(output_path), elements=1)


def report_threads(input_path, output_path, fmt, threads, progress=None, **options):
    """Write the thread count the child was given into the output file."""
    Path(output_path).write_text(str(threads))
    return ConversionResult(output=Path(output_path), elements=1)


def write_to_stderr(input_path, output_path, fmt, threads, progress=None, **options):
    """Write to stderr from Python and from "native" code (the file descriptor), then succeed."""
    print("python warning on stderr", file=sys.stderr)
    os.write(2, b"native message on fd 2\n")
    Path(output_path).write_text("ok")
    return ConversionResult(output=Path(output_path), elements=1)


def isolate_user_dirs(monkeypatch, path):
    """Point the app's settings and log folders into ``path``, on every platform."""
    from ifc_converter import app

    monkeypatch.setattr(app, "config_dir", lambda: Path(path) / "config")
    monkeypatch.setattr(app, "log_dir", lambda: Path(path) / "logs")


def convert_counting_workers(input_path, output_path, fmt, threads, progress=None, **options):
    """Convert, and write the most worker processes the Rhino export had running to <output>.workers."""
    import concurrent.futures

    running = []

    class Pool(concurrent.futures.ProcessPoolExecutor):
        def submit(self, *args, **kwargs):
            future = super().submit(*args, **kwargs)
            running.append(len(self._processes))
            return future

    concurrent.futures.ProcessPoolExecutor = Pool
    result = convert(input_path, output_path, fmt, threads, progress, **options)
    Path(f"{output_path}.workers").write_text(str(max(running, default=0)))
    return result


def write_slowly(input_path, output_path, fmt, threads, progress=None, status=None, **options):
    """Enter the "write" phase and let the output grow for about two seconds, like rhino3dm's Write()."""
    progress(0)
    status("write", "Rhino-Datei wird geschrieben (1 Objekte) …")
    with open(output_path, "wb") as file:
        for _ in range(5):
            file.write(b"\0" * 1024 ** 2)
            file.flush()
            time.sleep(0.5)
    progress(100)
    return ConversionResult(output=Path(output_path), elements=1)


def stage_and_wait(input_path, output_path, fmt, threads, progress=None, status=None, staging_dir=None, **options):
    """Put a file into the staging folder, tell the test where it is, then wait to be cancelled."""
    (Path(staging_dir) / "staged.3dm").write_bytes(b"\0" * 1024)
    Path(f"{output_path}.staging").write_text(str(staging_dir))
    progress(0)
    time.sleep(120)


def wait_forever(input_path, output_path, fmt, threads, progress=None, **options):
    """Hang without using any CPU, like a kernel waiting for a worker thread that died."""
    progress(0)
    time.sleep(600)


def compute_for_a_while(input_path, output_path, fmt, threads, progress=None, **options):
    """Use CPU for about 3 seconds without reporting progress, like one slow element, then finish."""
    progress(0)
    end = time.monotonic() + 3
    while time.monotonic() < end:
        sum(range(10000))
    Path(output_path).write_text("done")
    progress(100)
    return ConversionResult(output=Path(output_path), elements=1)


def _fail_on_named(name, how):
    """Make the kernel hang (or crash) whenever it computes the product called ``name``."""
    from ifc_converter import converter

    def fail():
        if how == "crash":
            _segfault()
        time.sleep(600)

    iterate, deep_shape = converter._iterate, converter._deep_shape

    def failing_iterate(model, settings, threads, products, library):
        # Like the real kernel: the other threads finish their products, then it is stuck.
        others = [product for product in products if product.Name != name]
        shapes = iterate(model, settings, threads, others, library) if others else ()

        def run():
            yield from shapes
            if len(others) < len(products):
                fail()

        return run()

    def failing_deep_shape(settings, product, strategy, *args):
        if product.Name == name:
            fail()
        return deep_shape(settings, product, strategy, *args)

    converter._iterate, converter._deep_shape = failing_iterate, failing_deep_shape


def hang_on_wall_7(input_path, output_path, fmt, threads, progress=None, **options):
    _fail_on_named("Wall 7", "hang")
    return convert(input_path, output_path, fmt, threads, progress, **options)


def crash_on_wall_7(input_path, output_path, fmt, threads, progress=None, **options):
    _fail_on_named("Wall 7", "crash")
    return convert(input_path, output_path, fmt, threads, progress, **options)


def crash_on_wall_7_unless_opencascade(input_path, output_path, fmt, threads, progress=None, kernel=None, **options):
    """Crash the kernel at "Wall 7" like the hybrid kernel on some models; OpenCASCADE computes it."""
    _record_attempt(output_path, kernel)
    if kernel != "opencascade":
        _fail_on_named("Wall 7", "crash")
    return convert(input_path, output_path, fmt, threads, progress, kernel=kernel, **options)


def overflow_then_wait(input_path, output_path, fmt, threads, progress=None, **options):
    """Report a stack overflow like faulthandler on Windows, then hang without CPU, as a kernel did there."""
    progress(0)
    os.write(2, b"Windows fatal exception: stack overflow\n\nThread 0x1 (most recent call first):\n")
    time.sleep(600)


def exit_in_kernel(input_path, output_path, fmt, threads, progress=None, **options):
    """End without a result while the kernel computes a product, like a crash there."""
    options["position"]("chunk", [1], "")
    os._exit(3)


def raise_memory_error(input_path, output_path, fmt, threads, progress=None, **options):
    raise MemoryError


def allocate_too_much(input_path, output_path, fmt, threads, progress=None, **options):
    """Try to allocate 4 GB, more than the memory limit the test gives the conversion's job object."""
    blocks = [bytearray(1024 ** 3) for _ in range(4)]
    return ConversionResult(output=Path(output_path), elements=len(blocks))


def _worker_priority():
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetPriorityClass.argtypes = (ctypes.c_void_p,)
        return kernel32.GetPriorityClass(kernel32.GetCurrentProcess())
    return os.getpriority(os.PRIO_PROCESS, 0)


def report_worker_priority(input_path, output_path, fmt, threads, progress=None, **options):
    """Write the priority of a worker process the child starts (as the Rhino export does), its own
    priority and on Windows its memory priority, one per line."""
    import concurrent.futures
    import multiprocessing

    with concurrent.futures.ProcessPoolExecutor(1, multiprocessing.get_context("spawn")) as pool:
        worker = pool.submit(_worker_priority).result()
    lines = [worker, _worker_priority()]
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetProcessInformation.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong)
        priority = ctypes.c_ulong()
        kernel32.GetProcessInformation(kernel32.GetCurrentProcess(), 0, ctypes.byref(priority), 4)
        lines.append(priority.value)
    Path(output_path).write_text("\n".join(map(str, lines)))
    return ConversionResult(output=Path(output_path), elements=1)


def abandon_iteration(path, how, chunk=600, threads=2):
    """Run in a process of its own: start iter_shapes, take a few shapes and leave it ("close" the
    generator, an "error" in the consumer, or just drop it for "gc"), free the model and print, right
    away, how many geometry-run threads and (Linux) how many more native threads than before are
    alive. Kernel threads still computing on the freed model would crash the process."""
    import gc
    import threading

    import ifcopenshell

    from ifc_converter import converter, rhino

    def native_threads():
        return len(os.listdir("/proc/self/task")) if sys.platform.startswith("linux") else 0

    converter.chunk_size = lambda threads: int(chunk)
    model = ifcopenshell.open(path)
    before = native_threads()
    shapes = converter.iter_shapes(model, rhino._settings(), int(threads), rhino.EXCLUDED_CLASSES)
    try:
        for number, _ in enumerate(shapes):
            if number == 3:
                if how == "error":
                    raise RuntimeError("the consumer failed")
                break
    except RuntimeError:
        pass
    if how == "close":
        shapes.close()
    del shapes, model, _
    gc.collect()
    runs = sum(thread.name == "geometry-run" for thread in threading.enumerate())
    print(runs, max(0, native_threads() - before), flush=True)
    time.sleep(2)  # a kernel thread left behind would crash meanwhile


def crash_late_on_wall_450(input_path, output_path, fmt, threads, progress=None, **options):
    """Chunks of 100 products; crash when the kernel reaches "Wall 450", after chunks 0–3 are done.
    Writes the number of products the kernel was asked for to <output>.computed (one line per attempt)."""
    from ifc_converter import converter

    converter.chunk_size = lambda threads: 100
    _fail_on_named("Wall 450", "crash")
    iterate, deep_shape = converter._iterate, converter._deep_shape
    asked = []

    def counting_iterate(model, settings, threads, products, library):
        asked.extend(products)
        return iterate(model, settings, threads, products, library)

    def counting_deep_shape(settings, product, strategy, *args):
        asked.append(product)
        return deep_shape(settings, product, strategy, *args)

    converter._iterate, converter._deep_shape = counting_iterate, counting_deep_shape
    try:
        return convert(input_path, output_path, fmt, threads, progress, **options)
    finally:
        with open(f"{output_path}.computed", "a") as file:
            file.write(f"{len(asked)}\n")


def convert_only_hull(input_path, output_path, fmt, threads, progress=None, **options):
    """convert() with a stand-in for envelope.select (the real selection is not part of these tests):
    every product is kept, two interior ones are reported as left out, and the coarse pass reports
    its progress like the real one. Patched here because the child is a fresh process."""
    from ifc_converter import envelope

    def select(model, threads, products, report=None, progress=None):
        if progress:
            progress(0)
            progress(100)
        return envelope.Selection(keep={product.id() for product in products}, total=len(products) + 2, inside=2)

    envelope.select = select
    return convert(input_path, output_path, fmt, threads, progress, **options)


class _StuckShapes:
    """The shapes of a run whose kernel thread spins on one product for good: ``shapes`` come at
    once, then nothing ever again; freeing it never returns either, like IfcOpenShell's iterator,
    whose destructor joins its threads (the child must end all the same)."""

    def __init__(self, shapes, stuck):
        self.shapes, self.stuck = shapes, stuck

    def __iter__(self):
        yield from self.shapes
        if self.stuck:
            threading.Event().wait()

    def __del__(self):
        if self.stuck:
            threading.Event().wait()


def _hang_in_kernel_on(name):
    from ifc_converter import converter

    iterate = converter._iterate

    def stuck_iterate(model, settings, threads, products, library):
        others = [product for product in products if product.Name != name]
        shapes = list(iterate(model, settings, threads, others, library)) if others else []
        return _StuckShapes(shapes, len(others) < len(products))

    converter._iterate = stuck_iterate


def hang_in_kernel_on_wall_7(input_path, output_path, fmt, threads, progress=None, **options):
    """The kernel hangs on "Wall 7" for good (its thread cannot be stopped); the conversion itself must
    give the wall up (IFC_CONVERTER_HANG_SECONDS is short in the test) and the child end promptly."""
    _hang_in_kernel_on("Wall 7")
    return convert(input_path, output_path, fmt, threads, progress, **options)


def report_hung(input_path, output_path, fmt, threads, progress=None, **options):
    """Report two elements as hung through the position channel and one of them in the result as
    well, like convert() does; the parent must list each once."""
    options["position"]("hung", [1], "IfcWall 1 „Hung“")
    options["position"]("hung", [2], "IfcWall 2 „Lost“")
    Path(output_path).write_text("fake")
    return ConversionResult(output=Path(output_path), elements=1, crashed=["IfcWall 2 „Lost“"])
