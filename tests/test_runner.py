import subprocess
import sys
import time

import pytest

from winadm_mcp import runner
from winadm_mcp import server as srv


class FakeProc:
    """Minimal stand-in for subprocess.Popen."""

    def __init__(self, stdout="", stderr="", returncode=0, hang=False):
        self._stdout_text = stdout
        self._stderr_text = stderr
        self.returncode = returncode
        self._hang = hang
        self.killed = False
        self.wait_calls = []

    class _Stream:
        def __init__(self, text):
            self._text = text
            self._lines = text.splitlines(keepends=True)

        def __iter__(self):
            return iter(self._lines)

    @property
    def stdout(self):
        return self._Stream(self._stdout_text) if self._stdout_text is not None else None

    @property
    def stderr(self):
        return self._Stream(self._stderr_text) if self._stderr_text is not None else None

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if self._hang:
            raise subprocess.TimeoutExpired(cmd="powershell", timeout=timeout)
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


def test_run_command_captures_output():
    proc = FakeProc(stdout="hello\r\n", stderr="", returncode=0)
    result = runner.run_command("Write-Output hello", popen=lambda *a, **k: proc)
    assert result.stdout == "hello\r\n"
    assert result.returncode == 0
    assert result.timed_out is False


def test_run_command_reports_stderr():
    proc = FakeProc(stdout="", stderr="Cannot find path\r\n", returncode=1)
    result = runner.run_command("Get-Item nope", popen=lambda *a, **k: proc)
    assert "Cannot find path" in result.stderr
    assert result.returncode == 1


def test_timeout_kills_only_the_powershell_process():
    """A timeout must not tree-kill: programs the command started keep running."""
    proc = FakeProc(stdout="partial output\r\n", hang=True)
    result = runner.run_command("Start-Process firefox", timeout=0.01, popen=lambda *a, **k: proc)
    assert result.timed_out is True
    assert proc.killed is True
    # The captured output so far is still returned.
    assert "partial output" in result.stdout


def test_timeout_reports_elapsed_and_keeps_output(monkeypatch):
    proc = FakeProc(stdout="step 1 done\r\nstep 2 done\r\n", hang=True)
    result = runner.run_command("long", timeout=0.01, popen=lambda *a, **k: proc)
    assert result.timed_out is True
    assert result.stdout.count("done") == 2
    assert result.elapsed >= 0


def test_tail_keeps_last_lines():
    proc = FakeProc(stdout="".join(f"line {i}\r\n" for i in range(50)), returncode=0)
    result = runner.run_command("many", popen=lambda *a, **k: proc)
    tail_lines = result.tail.splitlines()
    assert len(tail_lines) <= runner.TAIL_LINES
    assert tail_lines[-1] == "line 49"


def test_snapshot_exposes_partial_output_while_running():
    class SlowStream:
        def __init__(self):
            self.lines = ["first line\r\n"]
            self._done = False

        def __iter__(self):
            yield from self.lines

    class SlowProc(FakeProc):
        def wait(self, timeout=None):
            time.sleep(0.05)
            self.returncode = 0
            return 0

    proc = SlowProc(stdout="first line\r\n", returncode=0)
    cmd = runner.LiveCommand("long", timeout=5, popen=lambda *a, **k: proc)
    cmd.start()
    time.sleep(0.2)
    elapsed, tail = cmd.snapshot()
    cmd.wait(timeout=2)
    assert elapsed >= 0
    assert "first line" in tail


def test_format_output_reports_timeout(monkeypatch):
    result = runner.CommandResult(stdout="partial\r\n", stderr="", returncode=None, timed_out=True, elapsed=12.0)
    text = srv._format_command_output(result)
    assert "partial" in text
    assert "[timed out after 12s" in text
    assert "may still be running" in text


def test_format_output_reports_exit_code():
    result = runner.CommandResult(stdout="ok\r\n", stderr="", returncode=0, timed_out=False)
    assert srv._format_command_output(result) == "ok\n[exit 0]"


def test_format_output_includes_stderr():
    result = runner.CommandResult(stdout="", stderr="boom\r\n", returncode=1, timed_out=False)
    text = srv._format_command_output(result)
    assert "[stderr] boom" in text
    assert text.endswith("[exit 1]")


def test_async_tool_reports_progress(monkeypatch):
    """The async path must send progress notifications while the command runs."""
    sent = []

    class FakeCtx:
        async def report_progress(self, progress, total=None, message=None):
            sent.append((progress, total, message))

    monkeypatch.setattr(srv, "PROGRESS_INTERVAL_SECONDS", 0.01)

    class SlowProc(FakeProc):
        def wait(self, timeout=None):
            time.sleep(0.15)
            self.returncode = 0
            return 0

    proc = SlowProc(stdout="done\r\n", returncode=0)
    real_live = runner.LiveCommand

    def fake_live(script, timeout=120, popen=None):
        return real_live(script, timeout=timeout, popen=lambda *a, **k: proc)

    monkeypatch.setattr(srv.runner, "LiveCommand", fake_live)

    import asyncio

    out = asyncio.run(srv.run_powershell_command_with_progress("whoami", True, FakeCtx()))
    assert "[exit 0]" in out
    assert sent, "no progress notifications were sent"
    progress, total, message = sent[0]
    assert total == 120
    assert "running" in message


def test_async_tool_works_without_a_context(monkeypatch):
    """A client that does not ask for progress must still get the output."""
    proc = FakeProc(stdout="plain\r\n", returncode=0)
    real_live = runner.LiveCommand

    def fake_live(script, timeout=120, popen=None):
        return real_live(script, timeout=timeout, popen=lambda *a, **k: proc)

    monkeypatch.setattr(srv.runner, "LiveCommand", fake_live)
    import asyncio

    out = asyncio.run(srv.run_powershell_command_with_progress("whoami", True, None))
    assert "[exit 0]" in out


def test_async_tool_gate_still_blocks(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should not run")

    monkeypatch.setattr(srv.runner, "LiveCommand", boom)
    import asyncio

    out = asyncio.run(srv.run_powershell_command_with_progress("whoami", False, None))
    assert out.startswith("error:")


def test_run_powershell_command_uses_runner(monkeypatch):
    fake = FakeProc(stdout="desktop\\user\r\n", returncode=0)
    real_run = runner.run_command

    def fake_run(script, timeout=120, popen=None):
        return real_run(script, timeout=timeout, popen=lambda *a, **k: fake)

    monkeypatch.setattr(srv.runner, "run_command", fake_run)
    out = srv.run_powershell_command("whoami", allow_write=True)
    assert "desktop\\user" in out
    assert out.endswith("[exit 0]")


def test_run_powershell_command_gate_still_blocks(monkeypatch):
    called = []

    def boom(*a, **k):
        called.append(1)
        raise AssertionError("should not run")

    monkeypatch.setattr(srv.runner, "run_command", boom)
    assert srv.run_powershell_command("whoami", allow_write=False).startswith("error:")
    assert called == []
