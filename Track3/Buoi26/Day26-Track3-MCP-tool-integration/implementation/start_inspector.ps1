# Launch MCP Inspector (browser UI) against this server.
# Usage: .\start_inspector.ps1
# Note: paths are passed with forward slashes — the Inspector UI parses
# backslashes in the Arguments field as escape characters and mangles
# Windows paths (python then can't find the script -> "Disconnected").
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Join-Path $here ".venv\Scripts\python.exe") -replace '\\', '/'
$server = (Join-Path $here "mcp_server.py") -replace '\\', '/'
npx -y "@modelcontextprotocol/inspector" $python $server
