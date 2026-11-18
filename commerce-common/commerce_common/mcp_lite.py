# SPDX-License-Identifier: Apache-2.0
"""A minimal MCP server (Streamable HTTP, JSON responses) with no third-party MCP package.

Implements the open Model Context Protocol wire format for what a tool server needs:
``initialize``, ``notifications/*``, ``ping``, ``tools/list`` and ``tools/call`` over
JSON-RPC 2.0 on ``POST /mcp``. Each ``initialize`` mints an ``Mcp-Session-Id``; later
requests must carry it, and one session is one "connection" (``Context.session``).
Handlers declare typed parameters (pydantic models allowed) and a ``ctx: Context``.
"""

from __future__ import annotations

import inspect
import json
import secrets
import typing
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from commerce_common.pyd import TypeAdapter, ValidationError

SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_SESSIONS = 256
MAX_BODY_BYTES = 1_000_000


class Session:
    """One client connection; per-connection state hangs off this object."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id


@dataclass
class Context:
    session: Session


@dataclass
class _Tool:
    name: str
    description: str
    handler: Callable[..., Awaitable[str]]
    schema: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    params: dict[str, Any] = field(default_factory=dict)  # name -> (TypeAdapter, default)


class MiniMCP:
    def __init__(self, name: str, instructions: str, host: str = "127.0.0.1", port: int = 8200):
        self.name = name
        self.instructions = instructions
        self.host = host
        self.port = port
        self.tools: dict[str, _Tool] = {}
        self._sessions: OrderedDict[str, Session] = OrderedDict()

    # -- registration ------------------------------------------------------------------

    def tool(self, name: str, description: str) -> Callable[[Any], Any]:
        def decorate(handler: Any) -> Any:
            hints = typing.get_type_hints(handler)
            params: dict[str, Any] = {}
            props: dict[str, Any] = {}
            required: list[str] = []
            for pname, p in inspect.signature(handler).parameters.items():
                if hints.get(pname) is Context:
                    continue
                adapter = TypeAdapter(hints.get(pname, Any))
                params[pname] = (adapter, p.default)
                props[pname] = adapter.json_schema()
                if p.default is inspect.Parameter.empty:
                    required.append(pname)
            schema: dict[str, Any] = {"type": "object", "properties": props}
            if required:
                schema["required"] = required
            self.tools[name] = _Tool(name, description, handler, schema, params)
            return handler

        return decorate

    def set_schema(self, name: str, schema: dict[str, Any]) -> None:
        """Publish ``schema`` for ``name`` instead of the one derived from the signature."""
        self.tools[name].schema = schema

    # -- protocol ----------------------------------------------------------------------

    async def handle(self, session: Session, message: dict[str, Any]) -> dict[str, Any] | None:
        """One JSON-RPC message in; the response, or None for a notification."""
        mid = message.get("id")
        method = message.get("method")
        if mid is None:
            return None  # notifications get no response
        params = message.get("params") or {}
        try:
            if method == "ping":
                result: Any = {}
            elif method == "tools/list":
                result = {
                    "tools": [
                        {"name": t.name, "description": t.description, "inputSchema": t.schema}
                        for t in self.tools.values()
                    ]
                }
            elif method == "tools/call":
                result = await self._call(session, params)
            else:
                return _error(mid, -32601, f"method not found: {method}")
        except _RpcError as err:
            return _error(mid, err.code, str(err))
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        wanted = params.get("protocolVersion")
        return {
            "protocolVersion": wanted if wanted in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": self.name, "version": "0.1.0"},
            "instructions": self.instructions,
        }

    async def _call(self, session: Session, params: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(str(params.get("name")))
        if tool is None:
            raise _RpcError(-32602, f"unknown tool: {params.get('name')}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            raise _RpcError(-32602, "arguments must be an object")
        try:
            kwargs: dict[str, Any] = {}
            for pname, (adapter, default) in tool.params.items():
                if pname in args and args[pname] is not None:
                    kwargs[pname] = adapter.validate_python(args[pname])
                elif default is inspect.Parameter.empty:
                    raise ValueError(f"missing required argument: {pname}")
                else:
                    kwargs[pname] = default
            text = await tool.handler(ctx=Context(session), **kwargs)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except (ValidationError, ValueError) as err:
            return {
                "content": [{"type": "text", "text": f"invalid arguments: {err}"}],
                "isError": True,
            }

    # -- sessions ----------------------------------------------------------------------

    def new_session(self) -> Session:
        session = Session(secrets.token_urlsafe(24))
        self._sessions[session.session_id] = session
        while len(self._sessions) > MAX_SESSIONS:
            self._sessions.popitem(last=False)
        return session

    def get_session(self, session_id: str | None) -> Session | None:
        if session_id and session_id in self._sessions:
            self._sessions.move_to_end(session_id)
            return self._sessions[session_id]
        return None

    # -- HTTP --------------------------------------------------------------------------

    def asgi_app(self) -> Starlette:
        async def mcp(request: Request) -> Response:
            if request.method == "DELETE":
                self._sessions.pop(request.headers.get("mcp-session-id", ""), None)
                return Response(status_code=200)
            if request.method != "POST":
                return Response(status_code=405, headers={"Allow": "POST, DELETE"})
            raw = await request.body()
            if len(raw) > MAX_BODY_BYTES:
                return JSONResponse(_error(None, -32600, "request too large"), status_code=413)
            try:
                body = json.loads(raw)
            except ValueError:
                return JSONResponse(_error(None, -32700, "parse error"), status_code=400)
            batch = body if isinstance(body, list) else [body]
            if not batch or not all(isinstance(m, dict) for m in batch):
                return JSONResponse(_error(None, -32600, "invalid request"), status_code=400)
            headers: dict[str, str] = {}
            init = next((m for m in batch if m.get("method") == "initialize"), None)
            if init is not None:
                session = self.new_session()
                headers["Mcp-Session-Id"] = session.session_id
                out = [
                    {
                        "jsonrpc": "2.0",
                        "id": init.get("id"),
                        "result": self.initialize(init.get("params") or {}),
                    }
                ]
            else:
                sid = request.headers.get("mcp-session-id")
                found = self.get_session(sid)
                if found is None:
                    status = 404 if sid else 400
                    return JSONResponse(
                        _error(None, -32600, "missing or unknown session"), status_code=status
                    )
                out = [r for m in batch if (r := await self.handle(found, m)) is not None]
            if not out:
                return Response(status_code=202, headers=headers)
            return JSONResponse(out if isinstance(body, list) else out[0], headers=headers)

        return Starlette(routes=[Route("/mcp", mcp, methods=["POST", "GET", "DELETE"])])


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _error(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}
