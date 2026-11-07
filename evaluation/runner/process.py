"""Run one process tree under a hard wall-clock limit and measure what it actually used."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ProcResult:
    returncode: int | None
    timed_out: bool
    stopped: bool  # on_line asked to stop, e.g. the step or cost budget ran out
    wall_s: float
    cpu_s: float
    peak_rss_mb: float


def _kill(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_limited(argv: list[str], *, cwd: str, env: dict | None, wall_s: float, stdin: str | None = None,
                on_line: Callable[[str], bool] | None = None, output: list[str] | None = None) -> ProcResult:
    """Kills the whole process group at the limit. on_line sees each output line; returning False stops the run."""
    p = subprocess.Popen(argv, cwd=cwd, env=env, text=True, errors="replace", start_new_session=True,
                         stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
    stop = threading.Event()

    def feed() -> None:
        try:
            p.stdin.write(stdin)
            p.stdin.close()
        except (BrokenPipeError, ValueError, OSError):
            pass

    def read() -> None:
        for line in p.stdout:
            if output is not None:
                output.append(line)
            if on_line is not None and on_line(line) is False:
                stop.set()

    readers = [threading.Thread(target=read, daemon=True)]
    if stdin is not None:
        readers.append(threading.Thread(target=feed, daemon=True))
    for t in readers:
        t.start()
    t0 = time.monotonic()
    timed_out = stopped = False
    while True:  # wait4 gives this tree's own usage, where RUSAGE_CHILDREN would mix in earlier trials
        pid, status, usage = os.wait4(p.pid, os.WNOHANG)
        if pid:
            break
        if time.monotonic() - t0 > wall_s and not (timed_out or stopped):
            timed_out = True
            _kill(p.pid)
        elif stop.is_set() and not (timed_out or stopped):
            stopped = True
            _kill(p.pid)
        time.sleep(0.05)
    p.returncode = os.waitstatus_to_exitcode(status)
    _kill(p.pid)  # anything it left running in the background
    readers[0].join(timeout=2)
    scale = 1 if sys.platform == "darwin" else 1024  # ru_maxrss: bytes on macOS, KB on Linux
    return ProcResult(p.returncode, timed_out, stopped, time.monotonic() - t0, usage.ru_utime + usage.ru_stime,
                      usage.ru_maxrss * scale / 1e6)
