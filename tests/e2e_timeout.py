"""End-to-end check: a command that exceeds the tool timeout returns the output
produced so far, and the program it started is still running afterwards.

The tool timeout is 120s, so this test patches it down through the
environment rather than waiting two minutes.
"""

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def count_notepad() -> int:
    import subprocess

    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process notepad -ErrorAction SilentlyContinue | Measure-Object).Count"],
        capture_output=True, text=True,
    )
    try:
        return int(out.stdout.strip())
    except ValueError:
        return -1


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from winadm_mcp.server import main; main()", "--allow-write"],
        env={**os.environ, "WINADM_COMMAND_TIMEOUT": "5"},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            before = count_notepad()
            cmd = "Start-Process notepad; Write-Output 'started'; Start-Sleep 120"

            result = await session.call_tool(
                "run_powershell_command_tool",
                arguments={"command": cmd},
            )
            text = result.content[0].text
            print("--- tool output ---")
            print(text)
            print("-------------------")

            await asyncio.sleep(2)
            after = count_notepad()
            print(f"notepad before={before} after={after}")

            # cleanup
            import subprocess

            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Stop-Process -Name notepad -Force -ErrorAction SilentlyContinue"])

            ok = True
            if "started" not in text:
                print("MISSING_PARTIAL_OUTPUT")
                ok = False
            if "[timed out" not in text:
                print("MISSING_TIMEOUT_MARKER")
                ok = False
            if after <= before:
                print("CHILD_WAS_KILLED")
                ok = False

            print("E2E_TIMEOUT_OK" if ok else "E2E_TIMEOUT_FAILED")
            return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
