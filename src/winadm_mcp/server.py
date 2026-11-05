import argparse
import re

from mcp.server.fastmcp import FastMCP

from . import powershell

SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
PID_RE = re.compile(r"^[0-9]+$")
MESSAGE_MAX = 500


def _as_list(data):
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return [data]


def _fmt_rows(rows, columns):
    if not rows:
        return "(empty)"
    widths = {c: len(c) for c in columns}
    str_rows = []
    for row in rows:
        srow = {c: str(row.get(c, "")) for c in columns}
        str_rows.append(srow)
        for c in columns:
            widths[c] = max(widths[c], len(srow[c]))
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    lines = [header, "  ".join("-" * widths[c] for c in columns)]
    for srow in str_rows:
        lines.append("  ".join(srow[c].ljust(widths[c]) for c in columns))
    return "\n".join(lines)


def _require(name_ok, message):
    if not name_ok:
        return f"error: {message}"
    return None


def list_services(status: str = "", name: str = "") -> str:
    script = (
        "$ErrorActionPreference='Stop'; "
        "Get-Service | Select-Object Name,DisplayName,"
        "@{n='Status';e={$_.Status.ToString()}},"
        "@{n='StartType';e={$_.StartType.ToString()}} | "
        "ConvertTo-Json -Compress -Depth 4"
    )
    try:
        rows = _as_list(powershell.parse_json_output(powershell.run_powershell(script)))
    except Exception as e:
        return f"error: {e}"
    if status:
        rows = [r for r in rows if str(r.get("Status", "")).lower() == status.lower()]
    if name:
        rows = [r for r in rows if name.lower() in str(r.get("Name", "")).lower()]
    return _fmt_rows(rows, ["Name", "Status", "StartType", "DisplayName"])


def service_action(name: str, action: str, allow_write: bool) -> str:
    if not allow_write:
        return "error: write operations are disabled; restart the server with --allow-write"
    if not SERVICE_NAME_RE.match(name or ""):
        return "error: invalid service name (allowed: letters, digits, . _ -)"
    if action not in ("start", "stop", "restart"):
        return "error: action must be start, stop or restart"
    verb = {"start": "Start-Service", "stop": "Stop-Service", "restart": "Restart-Service"}[action]
    script = (
        "$ErrorActionPreference='Stop'; "
        f"{verb} -Name '{name}' -ErrorAction Stop; "
        f"Get-Service -Name '{name}' | Select-Object Name,"
        "@{n='Status';e={$_.Status.ToString()}} | ConvertTo-Json -Compress"
    )
    try:
        data = powershell.parse_json_output(powershell.run_powershell(script, timeout=60))
    except Exception as e:
        return f"error: {e}"
    data = data or {}
    return f"{data.get('Name', name)}: {data.get('Status', 'unknown')} (action: {action})"


def list_processes() -> str:
    script = (
        "$ErrorActionPreference='Stop'; "
        "Get-Process | Select-Object Id,ProcessName,"
        "@{n='WS_MB';e={[math]::Round($_.WorkingSet64/1MB,1)}},"
        "@{n='CPU';e={[math]::Round($_.CPU,1)}} | "
        "ConvertTo-Json -Compress"
    )
    try:
        rows = _as_list(powershell.parse_json_output(powershell.run_powershell(script, timeout=60)))
    except Exception as e:
        return f"error: {e}"
    rows = sorted(rows, key=lambda r: str(r.get("ProcessName", "")))
    return _fmt_rows(rows, ["Id", "ProcessName", "WS_MB", "CPU"])


def kill_process(pid: str, allow_write: bool) -> str:
    if not allow_write:
        return "error: write operations are disabled; restart the server with --allow-write"
    if not PID_RE.match(pid or ""):
        return "error: pid must be a positive integer"
    script = (
        "$ErrorActionPreference='Stop'; "
        f"Stop-Process -Id {pid} -Force -ErrorAction Stop; "
        "'killed"
        f" pid {pid}'"
    )
    try:
        powershell.run_powershell(script)
    except Exception as e:
        return f"error: {e}"
    return f"killed pid {pid}"


def get_eventlog(log_name: str = "System", max_events: int = 25, level: str = "error,warning,critical") -> str:
    if not re.match(r"^[A-Za-z0-9_ ]+$", log_name or ""):
        return "error: invalid log name"
    try:
        max_events = max(1, min(int(max_events), 200))
    except (TypeError, ValueError):
        return "error: max_events must be an integer"
    level_map = {"critical": 1, "error": 2, "warning": 3, "information": 4}
    levels = []
    for part in str(level).lower().split(","):
        part = part.strip()
        if part in level_map:
            levels.append(level_map[part])
    if not levels:
        return "error: level must be a comma list of critical,error,warning,information"
    level_ps = ",".join(str(l) for l in levels)
    script = (
        "$ErrorActionPreference='Stop'; "
        f"Get-WinEvent -FilterHashtable @{{LogName='{log_name}'; Level={level_ps}}} "
        f"-MaxEvents {max_events} -ErrorAction Stop | "
        "Select-Object TimeCreated,Id,LevelDisplayName,ProviderName,Message | "
        "ConvertTo-Json -Compress -Depth 3"
    )
    try:
        rows = _as_list(powershell.parse_json_output(powershell.run_powershell(script, timeout=60)))
    except Exception as e:
        return f"error: {e}"
    lines = []
    for r in rows:
        msg = str(r.get("Message", "")).replace("\r", " ").replace("\n", " ")
        if len(msg) > MESSAGE_MAX:
            msg = msg[: MESSAGE_MAX - 1] + "…"
        lines.append(
            f"[{r.get('TimeCreated', '?')}] {r.get('LevelDisplayName', '?')} "
            f"{r.get('ProviderName', '?')} (id {r.get('Id', '?')}): {msg}"
        )
    return "\n".join(lines) if lines else "(no events)"


OUTPUT_MAX = 20_000


def run_powershell_command(command: str, allow_write: bool) -> str:
    if not allow_write:
        return "error: write operations are disabled; restart the server with --allow-write"
    if not (command or "").strip():
        return "error: command must not be empty"
    try:
        out = powershell.run_powershell(command, timeout=120).rstrip()
    except Exception as e:
        return f"error: {e}"
    if len(out) > OUTPUT_MAX:
        out = out[: OUTPUT_MAX - 1] + "…"
    return out if out else "(no output)"


def system_info() -> str:
    script = (
        "$ErrorActionPreference='Stop'; "
        "$os = Get-CimInstance Win32_OperatingSystem; "
        "[pscustomobject]@{"
        "ComputerName=$env:COMPUTERNAME;"
        "OS=$os.Caption;"
        "Version=$os.Version;"
        "LastBoot=$os.LastBootUpTime.ToString('o');"
        "TotalGB=[math]::Round($os.TotalVisibleMemorySize/1MB,1);"
        "FreeGB=[math]::Round($os.FreePhysicalMemory/1MB,1)"
        "} | ConvertTo-Json -Compress"
    )
    try:
        data = powershell.parse_json_output(powershell.run_powershell(script)) or {}
    except Exception as e:
        return f"error: {e}"
    return "\n".join(f"{k}: {v}" for k, v in data.items())


def create_server(allow_write: bool = False) -> FastMCP:
    mcp = FastMCP(
        "winadm-mcp",
        instructions=(
            "Windows administration tools. Read-only by default; write actions "
            "(service start/stop/restart, process kill) require the server to be "
            "started with --allow-write. All tools require a Windows host."
        ),
    )

    @mcp.tool()
    def list_windows_services(status: str = "", name: str = "") -> str:
        """List Windows services with status and start type. Optionally filter by
        status (Running/Stopped/etc.) or substring of the service name."""
        return list_services(status=status, name=name)

    @mcp.tool()
    def service_action_tool(name: str, action: str) -> str:
        """Start, stop or restart a Windows service. Requires --allow-write."""
        return service_action(name, action, allow_write)

    @mcp.tool()
    def list_windows_processes() -> str:
        """List processes with PID, working set (MB) and CPU seconds."""
        return list_processes()

    @mcp.tool()
    def kill_process_tool(pid: str) -> str:
        """Force-kill a process by PID. Requires --allow-write."""
        return kill_process(pid, allow_write)

    @mcp.tool()
    def read_eventlog(
        log_name: str = "System", max_events: int = 25, level: str = "error,warning,critical"
    ) -> str:
        """Read recent events from a Windows event log (default: System,
        levels error/warning/critical, newest first)."""
        return get_eventlog(log_name=log_name, max_events=max_events, level=level)

    @mcp.tool()
    def run_powershell_command_tool(command: str) -> str:
        """Run a PowerShell command on the Windows host and return stdout/stderr.
        Requires --allow-write (this is arbitrary command execution)."""
        return run_powershell_command(command, allow_write)

    @mcp.tool()
    def windows_system_info() -> str:
        """OS name/version, hostname, last boot time and memory totals."""
        return system_info()

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(prog="winadm-mcp", description="Windows admin MCP server")
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="enable write actions (service start/stop/restart, process kill)",
    )
    args = parser.parse_args()
    create_server(allow_write=args.allow_write).run()
