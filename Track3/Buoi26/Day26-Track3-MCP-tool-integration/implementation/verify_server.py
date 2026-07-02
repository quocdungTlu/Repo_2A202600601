"""Repeatable verification script (Part 4 of the lab).

Builds a fresh temporary database, runs the server in-memory through the
FastMCP client, and checks every item the lab requires:

1. the server starts
2. the three tools are discoverable
3. the schema resources are discoverable
4. valid tool calls return useful results
5. invalid tool calls return clear errors

Exit code 0 means all checks passed.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from fastmcp import Client
from fastmcp.exceptions import ToolError

from init_db import create_database
from mcp_server import create_server

RESULTS: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok))
    line = f"{'PASS' if ok else 'FAIL'}  {name}"
    if detail:
        line += f"  -> {detail}"
    print(line)


async def expect_error(client: Client, tool: str, args: dict, label: str, fragment: str) -> None:
    try:
        await client.call_tool(tool, args)
        check(label, False, "call unexpectedly succeeded")
    except ToolError as exc:
        check(label, fragment.lower() in str(exc).lower(), str(exc))


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = create_database(Path(tmp) / "verify.db")
        server = create_server(db_path)

        async with Client(server) as client:
            check("server starts (in-memory session opened)", True)

            # --- discovery -------------------------------------------------
            tools = {t.name for t in await client.list_tools()}
            check(
                "tools discoverable (search, insert, aggregate)",
                {"search", "insert", "aggregate"} <= tools,
                str(sorted(tools)),
            )
            resources = {str(r.uri) for r in await client.list_resources()}
            check(
                "full schema resource discoverable",
                "schema://database" in resources,
                str(sorted(resources)),
            )
            templates = {t.uriTemplate for t in await client.list_resource_templates()}
            check(
                "per-table schema template discoverable",
                "schema://table/{table_name}" in templates,
                str(sorted(templates)),
            )

            # --- valid calls -----------------------------------------------
            res = (await client.call_tool(
                "search",
                {
                    "table": "students",
                    "filters": {"cohort": "A1"},
                    "order_by": "score",
                    "descending": True,
                    "limit": 2,
                },
            )).data
            ok = (
                res["total"] == 3
                and len(res["rows"]) == 2
                and res["rows"][0]["name"] == "En Vo"
            )
            check("search: filter + order + pagination", ok, json.dumps(res["rows"]))

            res = (await client.call_tool(
                "insert",
                {"table": "students", "values": {"name": "Giang Do", "cohort": "A1", "score": 8.0}},
            )).data
            check(
                "insert: returns inserted payload with id",
                res["id"] == 7 and res["inserted"]["name"] == "Giang Do",
                json.dumps(res),
            )

            res = (await client.call_tool(
                "aggregate",
                {"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"},
            )).data
            groups = {row["group"]: round(row["value"], 2) for row in res["rows"]}
            check(
                "aggregate: avg score by cohort",
                groups.get("A2") == 7.8 and "A1" in groups,
                json.dumps(groups),
            )

            res = (await client.call_tool("aggregate", {"table": "courses", "metric": "count"})).data
            check("aggregate: count rows", res["rows"][0]["value"] == 3, json.dumps(res["rows"]))

            # --- resources -------------------------------------------------
            content = await client.read_resource("schema://database")
            schema = json.loads(content[0].text)
            check(
                "read schema://database",
                {t["table"] for t in schema["tables"]} == {"courses", "enrollments", "students"},
                str([t["table"] for t in schema["tables"]]),
            )

            content = await client.read_resource("schema://table/students")
            table = json.loads(content[0].text)
            cols = [c["name"] for c in table["columns"]]
            check("read schema://table/students", cols == ["id", "name", "cohort", "score"], str(cols))

            # --- invalid calls ---------------------------------------------
            await expect_error(
                client, "search", {"table": "missing_table"},
                "reject unknown table", "unknown table",
            )
            await expect_error(
                client, "search", {"table": "students", "filters": {"nope": 1}},
                "reject unknown column", "unknown filter column",
            )
            await expect_error(
                client, "search",
                {"table": "students", "filters": {"score": {"op": "DROP", "value": 1}}},
                "reject unsupported operator", "unsupported operator",
            )
            await expect_error(
                client, "aggregate", {"table": "students", "metric": "median", "column": "score"},
                "reject invalid aggregate metric", "unsupported metric",
            )
            await expect_error(
                client, "insert", {"table": "students", "values": {}},
                "reject empty insert", "non-empty",
            )

            try:
                await client.read_resource("schema://table/missing_table")
                check("reject unknown table in schema resource", False, "read unexpectedly succeeded")
            except Exception as exc:
                check("reject unknown table in schema resource", "unknown table" in str(exc).lower(), str(exc))

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    if passed != len(RESULTS):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
