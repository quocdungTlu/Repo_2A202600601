#!/usr/bin/env bash
# Launch MCP Inspector (browser UI) against this server.
# Usage: ./start_inspector.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$HERE/.venv/Scripts/python.exe"
[ -f "$PYTHON" ] || PYTHON="$HERE/.venv/bin/python"
npx -y @modelcontextprotocol/inspector "$PYTHON" "$HERE/mcp_server.py"
