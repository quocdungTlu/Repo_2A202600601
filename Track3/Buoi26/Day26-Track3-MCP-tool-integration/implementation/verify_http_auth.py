"""Bonus verification: HTTP transport with bearer-token auth.

Starts `mcp_server.py --http` as a subprocess, then checks:

1. a request WITHOUT a token is rejected (HTTP 401)
2. a request with a WRONG token is rejected (HTTP 401)
3. a FastMCP client with the CORRECT token can list tools and call search

Exit code 0 means all checks passed.
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from fastmcp import Client

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable
TOKEN = "lab-secret-token"
PORT = 8091
URL = f"http://127.0.0.1:{PORT}/mcp"

RESULTS: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok))
    line = f"{'PASS' if ok else 'FAIL'}  {name}"
    if detail:
        line += f"  -> {detail}"
    print(line)


def wait_for_port(proc: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            httpx.get(URL, timeout=1.0)
            return
        except (httpx.ConnectError, httpx.ConnectTimeout):
            time.sleep(0.3)
    raise RuntimeError(f"server did not open {URL} within {timeout}s")


async def authorized_checks() -> None:
    async with Client(URL, auth=TOKEN) as client:
        tools = {t.name for t in await client.list_tools()}
        check(
            "correct token: tools discoverable over HTTP",
            {"search", "insert", "aggregate"} <= tools,
            str(sorted(tools)),
        )
        res = (await client.call_tool("search", {"table": "students", "limit": 1})).data
        check(
            "correct token: search works over HTTP",
            res["total"] >= 6 and len(res["rows"]) == 1,
            f"total={res['total']}",
        )


def main() -> None:
    env = {**os.environ, "LAB_MCP_TOKEN": TOKEN, "LAB_MCP_PORT": str(PORT)}
    proc = subprocess.Popen(
        [PYTHON, str(HERE / "mcp_server.py"), "--http"],
        cwd=HERE,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_port(proc)
        check("HTTP server starts", True, URL)

        r = httpx.post(URL, json={}, timeout=5.0)
        check("no token rejected with 401", r.status_code == 401, f"status={r.status_code}")

        r = httpx.post(
            URL, json={}, headers={"Authorization": "Bearer wrong-token"}, timeout=5.0
        )
        check("wrong token rejected with 401", r.status_code == 401, f"status={r.status_code}")

        asyncio.run(authorized_checks())
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    if passed != len(RESULTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
