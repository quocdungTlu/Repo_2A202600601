# SQLite Lab MCP Server (FastMCP)

A Model Context Protocol server that exposes a small SQLite database
(`students` / `courses` / `enrollments`) through three tools and two
schema resources, built with [FastMCP](https://gofastmcp.com).

| Surface | Name | What it does |
|---|---|---|
| Tool | `search` | Read rows with filters, column projection, ordering, pagination |
| Tool | `insert` | Insert one row, returns the generated id + full inserted row |
| Tool | `aggregate` | `count` / `avg` / `sum` / `min` / `max`, optional filters and `group_by` |
| Resource | `schema://database` | Full schema snapshot (all tables, JSON) |
| Resource template | `schema://table/{table_name}` | Schema of a single table (JSON) |

## Setup

```powershell
cd implementation
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt   # fastmcp + pytest
.\.venv\Scripts\python init_db.py                 # creates + seeds lab.db (idempotent)
```

On macOS/Linux replace `.venv\Scripts\...` with `.venv/bin/...`.

## Run the server

```powershell
.\.venv\Scripts\python mcp_server.py          # stdio (default, for MCP clients)
.\.venv\Scripts\python mcp_server.py --http   # bonus: HTTP with bearer-token auth
```

HTTP mode listens on `http://127.0.0.1:8090/mcp` and requires
`Authorization: Bearer <token>`; the token is `LAB_MCP_TOKEN`
(default `lab-secret-token`). Port override: `LAB_MCP_PORT`.

## Tool usage

Filter format (shared by `search` and `aggregate`):

```json
{"cohort": "A1"}                                  // equality shorthand
{"score": {"op": ">=", "value": 8.5}}             // explicit operator
{"code": {"op": "IN", "value": ["CS101", "AI301"]}}
```

Allowed operators: `= != < <= > >= LIKE IN` (conditions are AND-ed).
Allowed metrics: `count avg sum min max` (`count` is the only one that
works without `column`). `limit` is capped at 100 rows; use `offset`
plus the returned `total` for pagination.

Example calls:

- `search(table="students", filters={"cohort": "A1"}, order_by="score", descending=true, limit=2)`
- `insert(table="students", values={"name": "Giang Do", "cohort": "A1", "score": 8.0})`
- `aggregate(table="students", metric="avg", column="score", group_by="cohort")`

## Safety model

- Table and column names are validated against the live schema
  (`sqlite_master` / `PRAGMA table_info`) before ever touching SQL;
  unknown identifiers are rejected with a clear message.
- Operators and metrics come from fixed whitelists.
- Every **value** is bound as a `?` parameter — never concatenated —
  so inputs like `"x' OR '1'='1"` are matched as literal data.
- Empty inserts, non-scalar values, and bad limit/offset are rejected.

## Testing and verification

```powershell
.\.venv\Scripts\python -m pytest tests -q     # 21 tests
.\.venv\Scripts\python verify_server.py       # 16 checks: discovery, happy paths, error paths
.\.venv\Scripts\python verify_http_auth.py    # 5 checks: bonus HTTP auth (401 without token)
```

All three are self-contained: they build a fresh temporary database and
never touch `lab.db`.

### MCP Inspector

Browser UI: `.\start_inspector.ps1` (or `./start_inspector.sh`).

CLI mode (used to generate the files in `evidence/`):

```bash
npx -y @modelcontextprotocol/inspector --cli .venv/Scripts/python.exe mcp_server.py --method tools/list
npx -y @modelcontextprotocol/inspector --cli .venv/Scripts/python.exe mcp_server.py \
  --method tools/call --tool-name search --tool-arg table=students --tool-arg 'filters={"cohort":"A1"}'
```

`evidence/` contains captured Inspector output for: tool discovery with
schemas, resource + template discovery, both schema resources, a
successful `search` and `aggregate`, and a rejected call
(`inspector_call_search_error.json`), plus the Claude Code client proof
(`claude_mcp_list.txt`, `claude_headless_smoke.txt`).

## Client configuration

### Claude Code (verified)

`.mcp.json` at the repo root (adjust the absolute paths):

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "type": "stdio",
      "command": "D:/AI_Thuc_Chien/Track3/Buoi26/Day26-Track3-MCP-tool-integration/implementation/.venv/Scripts/python.exe",
      "args": ["D:/AI_Thuc_Chien/Track3/Buoi26/Day26-Track3-MCP-tool-integration/implementation/mcp_server.py"],
      "env": {}
    }
  }
}
```

Or: `claude mcp add sqlite-lab -- <abs-path-to-venv-python> <abs-path-to-mcp_server.py>`

Verified on this machine (see `evidence/`):

- `claude mcp list` → `sqlite-lab: ... - ✔ Connected`
- headless run: `claude -p` asked for A1 students + A2 average; Claude
  called `search` and `aggregate` and answered with the correct data
  (3 students, avg 7.8).
- Resources are addressable as `@sqlite-lab:schema://database`.

Important: `command` must point at the **venv** Python (the one with
`fastmcp` installed), and paths must be absolute — clients spawn the
server from a different working directory.

### Gemini CLI

```bash
gemini mcp add sqlite-lab <abs-path-to-venv-python> <abs-path-to-mcp_server.py> \
  --description "SQLite lab FastMCP server" --timeout 10000
gemini mcp list   # should show Connected
```

### Codex

`~/.codex/config.toml`:

```toml
[mcp_servers.sqlite_lab]
command = "<abs-path-to-venv-python>"
args = ["<abs-path-to-mcp_server.py>"]
```

## Demo script (~2 minutes)

1. `python init_db.py` — reproducible database. (10s)
2. `python verify_server.py` — 16/16 checks on one screen. (20s)
3. `.\start_inspector.ps1` — show tools with schemas, read
   `schema://table/students`, run one good `search`, then
   `table=missing_table` to show the clear error. (50s)
4. In Claude Code: ask for "students in cohort A1 and the average score
   of A2" — watch it call `search` + `aggregate`. (30s)
5. `python verify_http_auth.py` — bonus: 401 without token, works with
   token. (10s)

## Project structure

```text
implementation/
  db.py                 # SQLiteAdapter: validation + safe SQL building
  init_db.py            # reproducible schema + seed data
  mcp_server.py         # FastMCP server: 3 tools, 2 resources, --http bonus
  verify_server.py      # 16-check verification (Part 4)
  verify_http_auth.py   # 5-check bonus verification (HTTP + bearer auth)
  start_inspector.ps1 / .sh
  tests/test_server.py  # 21 pytest tests (in-memory FastMCP client)
  evidence/             # Inspector CLI + Claude Code client captures
```

Database layer and MCP layer are separate (`db.py` vs `mcp_server.py`);
`SQLiteAdapter` keeps a small surface (`search` / `insert` / `aggregate`
/ schema inspection) so a PostgreSQL adapter could be swapped in behind
the same MCP tools.
