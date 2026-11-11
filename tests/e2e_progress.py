"""End-to-end check: a real MCP client gets progress notifications for a
long-running PowerShell command, and the output comes back when it finishes.

Run with the Windows venv:
    python tests/e2e-progress.mjs  (no - this is Python)
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from winadm_mcp.server import main; main()", "--allow-write"],
        env={**os.environ, "WINADM_PROGRESS_INTERVAL": "2"},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("server:", init.serverInfo.name, init.serverInfo.version)

            tools = await session.list_tools()
            print("tools:", len(tools.tools))

            progress_events = []

            async def on_progress(progress, total, message):
                progress_events.append((progress, total, message))
                print(f"  [progress] {progress}/{total} {message}")

            # A command that takes ~12s: long enough for at least one
            # progress notification with the 10s default interval.
            cmd = "1..12 | ForEach-Object { Start-Sleep -Seconds 1; Write-Output \"step $_\" }"

            result = await session.call_tool(
                "run_powershell_command_tool",
                arguments={"command": cmd},
                progress_callback=on_progress,
            )

            text = result.content[0].text
            print("output tail:", text.splitlines()[-3:])
            print("progress events:", len(progress_events))

            if not progress_events:
                print("NO_PROGRESS")
                return 1
            print("E2E_PROGRESS_OK")
            return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
