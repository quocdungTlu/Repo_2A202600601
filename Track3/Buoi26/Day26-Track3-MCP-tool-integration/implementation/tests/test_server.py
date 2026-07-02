"""Tests for the SQLite Lab MCP server.

Every test builds a fresh seeded database in tmp_path and talks to the
server through the in-memory FastMCP client, so tests are isolated and
never touch lab.db.
"""

import asyncio
import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from init_db import create_database
from mcp_server import create_server


@pytest.fixture()
def server(tmp_path):
    db_path = create_database(tmp_path / "test.db")
    return create_server(db_path)


def run_with_client(server, scenario):
    async def runner():
        async with Client(server) as client:
            return await scenario(client)

    return asyncio.run(runner())


# ----------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------

def test_tools_discoverable(server):
    async def scenario(client):
        return {t.name for t in await client.list_tools()}

    assert {"search", "insert", "aggregate"} <= run_with_client(server, scenario)


def test_resources_discoverable(server):
    async def scenario(client):
        resources = {str(r.uri) for r in await client.list_resources()}
        templates = {t.uriTemplate for t in await client.list_resource_templates()}
        return resources, templates

    resources, templates = run_with_client(server, scenario)
    assert "schema://database" in resources
    assert "schema://table/{table_name}" in templates


# ----------------------------------------------------------------------
# search
# ----------------------------------------------------------------------

def test_search_filter_order_pagination(server):
    async def scenario(client):
        res = await client.call_tool(
            "search",
            {
                "table": "students",
                "filters": {"cohort": "A1"},
                "order_by": "score",
                "descending": True,
                "limit": 2,
                "offset": 0,
            },
        )
        return res.data

    data = run_with_client(server, scenario)
    assert data["total"] == 3
    assert [r["name"] for r in data["rows"]] == ["En Vo", "Alice Nguyen"]
    assert data["limit"] == 2 and data["offset"] == 0


def test_search_operator_and_projection(server):
    async def scenario(client):
        res = await client.call_tool(
            "search",
            {
                "table": "students",
                "filters": {"score": {"op": ">=", "value": 8.5}},
                "columns": ["name", "score"],
            },
        )
        return res.data

    data = run_with_client(server, scenario)
    assert {r["name"] for r in data["rows"]} == {"Alice Nguyen", "Chi Le", "En Vo"}
    assert set(data["rows"][0].keys()) == {"name", "score"}


def test_search_in_operator(server):
    async def scenario(client):
        res = await client.call_tool(
            "search",
            {"table": "courses", "filters": {"code": {"op": "IN", "value": ["CS101", "AI301"]}}},
        )
        return res.data

    data = run_with_client(server, scenario)
    assert data["total"] == 2


# ----------------------------------------------------------------------
# insert
# ----------------------------------------------------------------------

def test_insert_returns_payload(server):
    async def scenario(client):
        res = await client.call_tool(
            "insert",
            {"table": "students", "values": {"name": "Giang Do", "cohort": "A2", "score": 7.9}},
        )
        found = await client.call_tool("search", {"table": "students", "filters": {"name": "Giang Do"}})
        return res.data, found.data

    inserted, found = run_with_client(server, scenario)
    assert inserted["id"] == 7
    assert inserted["inserted"]["name"] == "Giang Do"
    assert found["total"] == 1


# ----------------------------------------------------------------------
# aggregate
# ----------------------------------------------------------------------

def test_aggregate_count(server):
    async def scenario(client):
        res = await client.call_tool("aggregate", {"table": "enrollments", "metric": "count"})
        return res.data

    data = run_with_client(server, scenario)
    assert data["rows"][0]["value"] == 8


def test_aggregate_avg_group_by(server):
    async def scenario(client):
        res = await client.call_tool(
            "aggregate",
            {"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"},
        )
        return res.data

    data = run_with_client(server, scenario)
    groups = {row["group"]: round(row["value"], 2) for row in data["rows"]}
    assert groups == {"A1": 8.2, "A2": 7.8}


def test_aggregate_max_with_filter(server):
    async def scenario(client):
        res = await client.call_tool(
            "aggregate",
            {"table": "students", "metric": "max", "column": "score", "filters": {"cohort": "A2"}},
        )
        return res.data

    data = run_with_client(server, scenario)
    assert data["rows"][0]["value"] == 9.1


# ----------------------------------------------------------------------
# resources
# ----------------------------------------------------------------------

def test_full_schema_resource(server):
    async def scenario(client):
        content = await client.read_resource("schema://database")
        return json.loads(content[0].text)

    schema = run_with_client(server, scenario)
    assert {t["table"] for t in schema["tables"]} == {"students", "courses", "enrollments"}


def test_table_schema_template(server):
    async def scenario(client):
        content = await client.read_resource("schema://table/students")
        return json.loads(content[0].text)

    table = run_with_client(server, scenario)
    assert [c["name"] for c in table["columns"]] == ["id", "name", "cohort", "score"]
    assert any(c["primary_key"] for c in table["columns"])


def test_table_schema_template_unknown_table(server):
    async def scenario(client):
        with pytest.raises(Exception, match="[Uu]nknown table"):
            await client.read_resource("schema://table/missing_table")

    run_with_client(server, scenario)


# ----------------------------------------------------------------------
# validation and error handling
# ----------------------------------------------------------------------

def expect_tool_error(server, tool, args, match):
    async def scenario(client):
        with pytest.raises(ToolError, match=match):
            await client.call_tool(tool, args)

    run_with_client(server, scenario)


def test_unknown_table_rejected(server):
    expect_tool_error(server, "search", {"table": "missing_table"}, "Unknown table")


def test_unknown_column_rejected(server):
    expect_tool_error(
        server, "search", {"table": "students", "filters": {"nope": 1}}, "Unknown filter column"
    )


def test_unknown_insert_column_rejected(server):
    expect_tool_error(
        server, "insert", {"table": "students", "values": {"nope": 1}}, "Unknown column"
    )


def test_unsupported_operator_rejected(server):
    expect_tool_error(
        server,
        "search",
        {"table": "students", "filters": {"score": {"op": "DROP TABLE", "value": 1}}},
        "Unsupported operator",
    )


def test_invalid_metric_rejected(server):
    expect_tool_error(
        server,
        "aggregate",
        {"table": "students", "metric": "median", "column": "score"},
        "Unsupported metric",
    )


def test_metric_without_column_rejected(server):
    expect_tool_error(
        server, "aggregate", {"table": "students", "metric": "avg"}, "requires a 'column'"
    )


def test_empty_insert_rejected(server):
    expect_tool_error(server, "insert", {"table": "students", "values": {}}, "non-empty")


def test_bad_order_by_rejected(server):
    expect_tool_error(
        server,
        "search",
        {"table": "students", "order_by": "score; DROP TABLE students"},
        "Unknown order_by column",
    )


def test_injection_value_is_treated_as_data(server):
    async def scenario(client):
        res = await client.call_tool(
            "search",
            {"table": "students", "filters": {"name": "x' OR '1'='1"}},
        )
        tables = await client.read_resource("schema://database")
        return res.data, json.loads(tables[0].text)

    data, schema = run_with_client(server, scenario)
    assert data["total"] == 0  # bound as a literal value, matches nothing
    assert {t["table"] for t in schema["tables"]} == {"students", "courses", "enrollments"}
