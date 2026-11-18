# SPDX-License-Identifier: Apache-2.0
from starlette.testclient import TestClient

from commerce_common.mcp_lite import Context, MiniMCP
from commerce_common.mcp_server import BearerAuth

TOKEN = "t" * 32


def _app():
    server = MiniMCP("t", "i")

    @server.tool("echo", "echo")
    async def echo(text: str, ctx: Context) -> str:
        return text

    return BearerAuth(server.asgi_app(), TOKEN)


def _rpc(method, mid=1, **params):
    return {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}


def test_http_flow_requires_token_and_session():
    c = TestClient(_app())
    assert c.post("/mcp", json=_rpc("initialize")).status_code == 401
    h = {"Authorization": f"Bearer {TOKEN}"}
    r = c.post("/mcp", json=_rpc("initialize", protocolVersion="2025-06-18"), headers=h)
    assert r.status_code == 200 and r.json()["result"]["serverInfo"]["name"] == "t"
    h["Mcp-Session-Id"] = r.headers["mcp-session-id"]
    assert (
        c.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h
        ).status_code
        == 202
    )
    assert (
        c.post("/mcp", json=_rpc("tools/list", 2), headers=h).json()["result"]["tools"][0]["name"]
        == "echo"
    )
    ok = c.post(
        "/mcp", json=_rpc("tools/call", 3, name="echo", arguments={"text": "hi"}), headers=h
    ).json()
    assert ok["result"]["content"][0]["text"] == "hi"
    bad = c.post("/mcp", json=_rpc("tools/call", 4, name="echo", arguments={}), headers=h).json()
    assert bad["result"]["isError"]
    nosess = c.post("/mcp", json=_rpc("tools/list"), headers={"Authorization": f"Bearer {TOKEN}"})
    assert nosess.status_code == 400
