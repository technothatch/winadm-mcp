"""Run PowerShell commands with streaming output, progress hooks and safe timeouts.

Two behaviours here were designed deliberately, and both are the result of
getting it wrong first:

* **A timeout kills only the PowerShell process we started.**  Killing the whole
  tree (``taskkill /T``) also kills programs the command deliberately launched
  and expected to outlive it -- a GUI app started with ``Start-Process``, or a
  build started by a helper process.  Those cannot be brought back.  A console
  program that ignores the break and keeps running is the lesser evil: the agent
  can see it and end it.

* **The output pipes are read by background threads.**  A descendant that
  inherited the pipes keeps them open, so waiting for the pipes to close can
  block forever after the PowerShell process is already gone.  The readers are
  therefore given a short grace period and then abandoned; whatever was
  captured up to that point is still returned.

The runner never raises for a non-zero exit code and never raises for a
timeout: both are normal outcomes and are reported in the result object.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass

from .powershell import encode_command

#: How many trailing output lines are kept for progress messages.
TAIL_LINES = 20
#: How long we wait for the pipe readers to finish after the process is gone.
READER_GRACE_SECONDS = 2.0


@dataclass
class CommandResult:
    """Outcome of a PowerShell command."""

    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    timed_out: bool = False
    elapsed: float = 0.0
    tail: str = ""


class _Output:
    """Thread-safe accumulator for one output stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lines: list[str] = []
        self._tail: deque[str] = deque(maxlen=TAIL_LINES)

    def add(self, line: str) -> None:
        with self._lock:
            self._lines.append(line)
            self._tail.append(line.rstrip("\r\n"))

    def text(self) -> str:
        with self._lock:
            return "".join(self._lines)

    def tail_text(self) -> str:
        with self._lock:
            return "\n".join(self._tail)


class _Reader(threading.Thread):
    """Reads one pipe into an :class:`_Output` until the stream closes."""

    def __init__(self, stream, sink: _Output) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._sink = sink

    def run(self) -> None:
        try:
            for line in self._stream:
                self._sink.add(line)
        except (ValueError, OSError):
            pass


class LiveCommand:
    """A PowerShell command that runs in the background and can be polled.

    While the command is running, :meth:`snapshot` exposes the output captured
    so far, which is what progress notifications carry.
    """

    def __init__(self, script: str, timeout: float = 120, popen=None) -> None:
        self._script = script
        self._timeout = timeout
        self._popen = popen or subprocess.Popen
        self._stdout = _Output()
        self._stderr = _Output()
        self._lock = threading.Lock()
        self._finished = threading.Event()
        self._started = time.monotonic()
        self.result: CommandResult | None = None
        self.error: BaseException | None = None
        self._proc = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> "LiveCommand":
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        self._thread = thread
        return self

    def _run(self) -> None:
        try:
            result = self._execute()
        except BaseException as exc:  # pragma: no cover - defensive
            with self._lock:
                self.error = exc
        else:
            with self._lock:
                self.result = result
        finally:
            self._finished.set()

    def _execute(self) -> CommandResult:
        if self._popen is subprocess.Popen and sys.platform != "win32":
            raise RuntimeError(
                "winadm-mcp tools require Windows (PowerShell not available on this platform)"
            )

        # CREATE_NO_WINDOW keeps PowerShell from flashing a console window when
        # the MCP client is a GUI app (Claude Desktop and friends run without a
        # console).
        popen_kwargs = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        started = time.monotonic()
        proc = self._popen(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encode_command(self._script),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **popen_kwargs,
        )
        self._proc = proc

        readers: list[_Reader] = []
        if proc.stdout is not None:
            readers.append(_Reader(proc.stdout, self._stdout))
        if proc.stderr is not None:
            readers.append(_Reader(proc.stderr, self._stderr))
        for reader in readers:
            reader.start()

        timed_out = False
        try:
            proc.wait(timeout=self._timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Kill only the PowerShell process. Descendants keep running on
            # purpose: a GUI app the command started should outlive it.
            try:
                proc.kill()
            except OSError:  # pragma: no cover - may have exited already
                pass

        for reader in readers:
            # A descendant that inherited the pipe can keep it open
            # indefinitely, so this wait is bounded on purpose.
            reader.join(timeout=READER_GRACE_SECONDS)

        return CommandResult(
            stdout=self._stdout.text(),
            stderr=self._stderr.text(),
            returncode=proc.returncode,
            timed_out=timed_out,
            elapsed=time.monotonic() - started,
            tail=self._stdout.tail_text() or self._stderr.tail_text(),
        )

    # -- polling -----------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._finished.wait(timeout)

    def elapsed(self) -> float:
        return time.monotonic() - self._started

    def snapshot(self) -> tuple[float, str]:
        """Return ``(elapsed_seconds, tail_of_output)`` for progress messages."""
        return self.elapsed(), (self._stdout.tail_text() or self._stderr.tail_text())


def run_command(script: str, timeout: float = 120, popen=None) -> CommandResult:
    """Run *script* in PowerShell and return its output.

    ``popen`` exists so tests can inject a fake process; production code uses
    :func:`subprocess.Popen`.
    """
    cmd = LiveCommand(script, timeout=timeout, popen=popen)
    cmd.start()
    cmd.wait()
    if cmd.error is not None:
        raise cmd.error
    assert cmd.result is not None
    return cmd.result
