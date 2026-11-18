# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from commerce_common.mcp_server import BearerAuth, auth_token_from_env, enforce_local_only_bind

TOKEN = "t" * 32


async def _app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"inner"})


def _client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=BearerAuth(_app, TOKEN)), base_url="http://t"
    )


async def test_requests_without_the_token_are_refused():
    async with _client() as c:
        assert (await c.post("/mcp")).status_code == 401
        assert (await c.post("/mcp", headers={"authorization": "Bearer nope"})).status_code == 401
        assert (await c.post("/mcp", headers={"x-api-key": "x"})).status_code == 401


async def test_token_in_either_header_passes_and_health_is_open():
    async with _client() as c:
        assert (await c.post("/mcp", headers={"authorization": f"Bearer {TOKEN}"})).text == "inner"
        assert (await c.post("/mcp", headers={"x-api-key": TOKEN})).text == "inner"
        assert (await c.get("/healthz")).text == "ok"


def test_short_token_refused_and_token_unlocks_public_bind(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "short")
    with pytest.raises(SystemExit):
        auth_token_from_env()
    monkeypatch.delenv("MCP_AUTH_TOKEN")
    with pytest.raises(SystemExit):
        enforce_local_only_bind("0.0.0.0", server="x", unsafe_env_var="X_UNSAFE")
    monkeypatch.setenv("MCP_AUTH_TOKEN", TOKEN)
    enforce_local_only_bind("0.0.0.0", server="x", unsafe_env_var="X_UNSAFE")
