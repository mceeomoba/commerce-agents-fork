# SPDX-License-Identifier: Apache-2.0
"""An in-process client for ``MiniMCP`` servers, for tests: one client is one session."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

from .mcp_lite import MiniMCP


class _Client:
    def __init__(self, server: MiniMCP) -> None:
        self._server = server
        self._session = server.new_session()
        self._next = 0

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next += 1
        reply = await self._server.handle(
            self._session, {"jsonrpc": "2.0", "id": self._next, "method": method, "params": params}
        )
        assert reply is not None
        if "error" in reply:
            raise RuntimeError(reply["error"]["message"])
        return reply["result"]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return SimpleNamespace(
            isError=result["isError"],
            content=[SimpleNamespace(type=c["type"], text=c["text"]) for c in result["content"]],
        )

    async def list_tools(self) -> Any:
        result = await self._rpc("tools/list", {})
        return SimpleNamespace(tools=[SimpleNamespace(**t) for t in result["tools"]])


@asynccontextmanager
async def create_connected_server_and_client_session(server: MiniMCP):
    yield _Client(server)
