# winadm-mcp

**An MCP server that gives AI agents safe, read-mostly access to Windows administration:
services, processes, the event log and system info.**

```
$ pip install git+https://github.com/technothatch/winadm-mcp
$ winadm-mcp --allow-write
```

Point Claude Desktop / Claude Code / any MCP client at it and your agent can answer
"why is my printer not working" (Spooler stopped?), "what ate my RAM" or
"what broke since boot" — without you alt-tabbing through `services.msc`,
Task Manager and Event Viewer.

## Tools

| Tool | Access | What it does |
|------|--------|--------------|
| `list_windows_services` | read | all services with status + start type; filter by status/name |
| `service_action_tool` | **write** | start / stop / restart a service |
| `list_windows_processes` | read | PID, working set MB, CPU seconds |
| `kill_process_tool` | **write** | force-kill by PID |
| `read_eventlog` | read | newest events from any log (default System, error/warning/critical) |
| `run_powershell_command_tool` | **write** | run a PowerShell command and return its output (with progress notifications) |
| `windows_system_info` | read | OS, hostname, last boot, memory totals |

**Read-only by default.** Write tools refuse to act unless the server is started with
`--allow-write`. Service names and PIDs are validated before they touch PowerShell.

> **The story behind it:** [Give Windows administration tools a defined boundary](https://technothatch.iyre.com/blog/winadm-mcp-inside-the-project/)
> — the TechnoThatch journal piece on the read-only-by-default design.

## Install / run

> **Status:** not on PyPI yet. Install from GitHub until it is published:
>
> ```
> pip install git+https://github.com/technothatch/winadm-mcp
> winadm-mcp                      # read-only (recommended first)
> winadm-mcp --allow-write        # enable write tools
> ```
>
> The `uvx winadm-mcp` / `pip install winadm-mcp` forms will work once the
> package is on PyPI.

Claude Desktop config example (after `pip install`, use the `winadm-mcp` entry point
directly — `uvx` only works once the package is on PyPI):

```json
{
  "mcpServers": {
    "winadm": {
      "command": "winadm-mcp",
      "args": []
    }
  }
}
```

## Long-running commands

`run_powershell_command_tool` sends MCP **progress notifications** while a command is
still running: elapsed time, and the last line the command printed. MCP clients give up
on calls that stay silent (Claude Code aborts after 300 s with "sent no response or
progress"), so a long command that says nothing looks exactly like a hung one.

```
[progress] 10.1/120.0 running 10s - last output: step 8
```

When the command exceeds its timeout, the tool returns **the output produced so far**
plus how long it ran, instead of a bare "timed out":

```
started
[timed out after 6s - the PowerShell process was ended, but programs it started may still be running]
```

A timeout stops the PowerShell process only. Programs the command started
(`Start-Process firefox`, a build kicked off by a helper) keep running — a killed GUI
app or an interrupted build cannot be brought back, and an agent can always see and
end a leftover console process itself.

Two environment variables tune this:

| Variable | Default | Effect |
|---|---|---|
| `WINADM_PROGRESS_INTERVAL` | `10` | seconds between progress notifications |
| `WINADM_COMMAND_TIMEOUT` | `120` | seconds before a command is stopped |

## Honest technical notes

- Every tool is a small PowerShell one-liner invoked with `-EncodedCommand`
  (UTF-16LE base64, no temp files, no shell string interpolation of user input —
  names/PIDs are regex-validated first).
- Output is read on background threads. A descendant that inherits the pipes can keep
  them open, so waiting for them is deliberately bounded — a slow pipe never hangs the
  tool call.
- A timeout kills the PowerShell process, never the process tree (`taskkill /T` also
  kills GUI programs the command meant to outlive it).
- Windows-only by nature; on other OSes tools return a clear error instead of lying.
- Tested on Linux CI with fully mocked PowerShell (deterministic, no admin rights needed)
  and smoke-tested on `windows-latest`.

## Development

```
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE)
