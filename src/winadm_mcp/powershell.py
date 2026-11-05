import base64
import json
import subprocess
import sys


def encode_command(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def run_powershell_capture(script: str, timeout: int = 30) -> tuple[str, str, int]:
    if sys.platform != "win32":
        raise RuntimeError(
            "winadm-mcp tools require Windows (PowerShell not available on this platform)"
        )
    # CREATE_NO_WINDOW keeps PowerShell from flashing a console window when the
    # MCP client is a GUI app (Claude Desktop and friends run without a console).
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encode_command(script),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    return proc.stdout, proc.stderr, proc.returncode


def run_powershell(script: str, timeout: int = 30) -> str:
    out, err, code = run_powershell_capture(script, timeout)
    if code != 0:
        detail = (err or out or "").strip()
        raise RuntimeError(f"powershell exited {code}: {detail}")
    return out


def parse_json_output(raw: str):
    text = raw.strip()
    if not text:
        return None
    return json.loads(text)
