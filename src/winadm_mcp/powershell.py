import base64
import json
import subprocess
import sys


def encode_command(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def run_powershell(script: str, timeout: int = 30) -> str:
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
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"powershell exited {proc.returncode}: {detail}")
    return proc.stdout


def parse_json_output(raw: str):
    text = raw.strip()
    if not text:
        return None
    return json.loads(text)
