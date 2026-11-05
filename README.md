# winadm-mcp

**An MCP server that gives AI agents safe, read-mostly access to Windows administration:
services, processes, the event log and system info.**

```
$ uvx winadm-mcp --allow-write
# or: winadm-mcp
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
| `run_powershell_command_tool` | **write** | run a PowerShell command and return its output |
| `windows_system_info` | read | OS, hostname, last boot, memory totals |

**Read-only by default.** Write tools refuse to act unless the server is started with
`--allow-write`. Service names and PIDs are validated before they touch PowerShell.

## Install / run

```
uvx winadm-mcp                      # read-only (recommended first)
uvx winadm-mcp --allow-write        # enable write tools
```

or `pip install winadm-mcp` and run `winadm-mcp`.

Claude Desktop config example:

```json
{
  "mcpServers": {
    "winadm": {
      "command": "uvx",
      "args": ["winadm-mcp"]
    }
  }
}
```

## Honest technical notes

- Every tool is a small PowerShell one-liner invoked with `-EncodedCommand`
  (UTF-16LE base64, no temp files, no shell string interpolation of user input —
  names/PIDs are regex-validated first).
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
