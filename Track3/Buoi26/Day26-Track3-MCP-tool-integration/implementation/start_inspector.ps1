# Launch MCP Inspector (browser UI) against this server.
# Usage: .\start_inspector.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $here ".venv\Scripts\python.exe"
$server = Join-Path $here "mcp_server.py"
npx -y "@modelcontextprotocol/inspector" $python $server
