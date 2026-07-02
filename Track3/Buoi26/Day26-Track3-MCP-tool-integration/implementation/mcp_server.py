"""FastMCP server exposing a SQLite database through search/insert/aggregate.

Tools:
    search    - read rows with filters, projection, ordering, pagination
    insert    - add one row, returns the inserted payload with its id
    aggregate - count/avg/sum/min/max with optional filters and group_by

Resources:
    schema://database             - full schema snapshot (all tables)
    schema://table/{table_name}   - schema of a single table

Runs on stdio by default (never print to stdout: it would corrupt the
JSON-RPC stream). Use create_server(db_path) to build an instance against
a different database, e.g. in tests.
"""

import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError

from db import DEFAULT_DB_PATH, SQLiteAdapter, ValidationError

DEFAULT_HTTP_PORT = 8090


def create_server(db_path: str | Path = DEFAULT_DB_PATH, auth=None) -> FastMCP:
    mcp = FastMCP("SQLite Lab MCP Server", auth=auth)
    adapter = SQLiteAdapter(db_path)

    @mcp.tool(name="search")
    def search(
        table: str,
        filters: dict[str, Any] | None = None,
        columns: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        """Search rows in a table.

        Args:
            table: table name (see the schema://database resource).
            filters: {column: value} for equality, or
                {column: {"op": "=|!=|<|<=|>|>=|LIKE|IN", "value": ...}}.
                IN takes a list as value. Conditions are AND-ed.
            columns: columns to return; omit for all columns.
            limit: max rows to return (1-100, default 20).
            offset: rows to skip, for pagination.
            order_by: column to sort by; descending=true reverses the order.

        Returns rows plus pagination metadata (total/limit/offset).
        """
        try:
            result = adapter.search(
                table=table,
                columns=columns,
                filters=filters,
                limit=limit,
                offset=offset,
                order_by=order_by,
                descending=descending,
            )
        except ValidationError as exc:
            raise ToolError(str(exc)) from exc
        return {"table": table, **result}

    @mcp.tool(name="insert")
    def insert(table: str, values: dict[str, Any]) -> dict[str, Any]:
        """Insert one row into a table.

        Args:
            table: table name (see the schema://database resource).
            values: non-empty {column: value} map. Values must be strings,
                numbers, or null. Auto-increment ids are generated.

        Returns the generated id and the full inserted row.
        """
        try:
            result = adapter.insert(table=table, values=values)
        except ValidationError as exc:
            raise ToolError(str(exc)) from exc
        return {"table": table, **result}

    @mcp.tool(name="aggregate")
    def aggregate(
        table: str,
        metric: str,
        column: str | None = None,
        filters: dict[str, Any] | None = None,
        group_by: str | None = None,
    ) -> dict[str, Any]:
        """Compute an aggregate over a table.

        Args:
            table: table name (see the schema://database resource).
            metric: one of count, avg, sum, min, max.
            column: column to aggregate; required except for count.
            filters: same format as the search tool.
            group_by: optional column to group results by.

        Returns one row per group (or a single row without group_by),
        each with a "value" field.
        """
        try:
            result = adapter.aggregate(
                table=table,
                metric=metric,
                column=column,
                filters=filters,
                group_by=group_by,
            )
        except ValidationError as exc:
            raise ToolError(str(exc)) from exc
        return {"table": table, **result}

    @mcp.resource("schema://database", mime_type="application/json")
    def database_schema() -> str:
        """Full database schema: every table with its column definitions."""
        try:
            snapshot = {
                "database": adapter.db_path.name,
                "tables": [adapter.get_table_schema(t) for t in adapter.list_tables()],
            }
        except ValidationError as exc:
            raise ResourceError(str(exc)) from exc
        return json.dumps(snapshot, indent=2)

    @mcp.resource("schema://table/{table_name}", mime_type="application/json")
    def table_schema(table_name: str) -> str:
        """Schema of a single table: column names, types, and constraints."""
        try:
            return json.dumps(adapter.get_table_schema(table_name), indent=2)
        except ValidationError as exc:
            raise ResourceError(str(exc)) from exc

    return mcp


mcp = create_server()


def _run_http() -> None:
    """Bonus: HTTP transport protected by a static bearer token.

    The token comes from the LAB_MCP_TOKEN environment variable
    (default "lab-secret-token" for classroom demos). Requests without
    a valid Authorization: Bearer header are rejected with 401.
    """
    import os

    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

    token = os.environ.get("LAB_MCP_TOKEN", "lab-secret-token")
    verifier = StaticTokenVerifier(
        tokens={token: {"client_id": "sqlite-lab-client", "scopes": []}}
    )
    port = int(os.environ.get("LAB_MCP_PORT", DEFAULT_HTTP_PORT))
    server = create_server(auth=verifier)
    server.run(transport="http", host="127.0.0.1", port=port)


if __name__ == "__main__":
    import sys

    if "--http" in sys.argv:
        _run_http()
    else:
        mcp.run()  # stdio transport by default
