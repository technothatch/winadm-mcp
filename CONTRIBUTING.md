# Contributing to winadm-mcp

Thanks for helping improve a small MCP server for Windows administration.

## Ground rules

- Search [existing issues](https://github.com/technothatch/winadm-mcp/issues) before opening a new one.
- One problem per issue, please.
- Be kind. This is maintained in spare time; assume good intent.

## Reporting a bug

Use the **Bug report** template. The output of the failing tool matters most,
including the `[stderr]` and `[exit N]` lines — they are the difference between
"a command produced nothing" and "a command failed".

Also include:

- `winadm-mcp --version` / the commit you installed from
- Windows version and whether the MCP client runs elevated
- The exact tool call and its arguments (redact anything sensitive)

## Suggesting a feature

Use the **Feature request** template. Say which admin task you're trying to do
from an agent, and whether it should be **read** or **write** access. New tools
default to read-only unless there's a strong reason otherwise.

## Sending a pull request

1. Fork and branch from `main`.
2. Keep the access model intact: anything that mutates state must be gated on
   `--allow-write`, and inputs must be validated before they reach PowerShell.
3. Run the checks locally:

   ```
   pip install -e ".[dev]"
   pytest
   ```

4. Open a PR that references the issue it fixes and explains *why* the change
   is correct, not just what it does.

Small, focused PRs merge fastest.

## Releases

Publishing to PyPI is a maintainer step. Until the package is published there,
install with `pip install git+https://github.com/technothatch/winadm-mcp`.
