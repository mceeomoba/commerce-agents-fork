# SPDX-License-Identifier: Apache-2.0
# Derived from the commerce-agents project (Copyright 2026 Anthropic PBC, Apache-2.0).
"""A small async client for any OpenAI-compatible chat-completions endpoint.

The turn loop speaks a content-block message format (text and tool_use blocks, tool_result
blocks in user messages) and a block-level stream (content_block_start / delta / stop).
This module keeps that internal format and translates it to and from the common
``/chat/completions`` wire format, so the agents run on Groq, OpenRouter, Google's
OpenAI-compatible endpoint, Ollama, vLLM, LM Studio, or any other compatible server.

Environment: ``LLM_BASE_URL`` (default ``https://api.groq.com/openai/v1``), ``LLM_API_KEY``
and ``LLM_MODEL``. Provider-only features (server-side web search, hosted code execution,
prompt caching, extended thinking) are dropped from requests.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


def default_model() -> str:
    return os.environ.get("LLM_MODEL", DEFAULT_MODEL)


class LLMError(Exception):
    """A failed model call."""


class AuthenticationError(LLMError):
    """The endpoint rejected the credentials (HTTP 401/403)."""


class _Obj(SimpleNamespace):
    """Attribute access plus the ``model_dump`` the loop uses on blocks and messages."""

    def model_dump(self, exclude_none: bool = False, exclude: set[str] | None = None) -> dict:
        out: dict[str, Any] = {}
        for key, value in vars(self).items():
            if (exclude and key in exclude) or (exclude_none and value is None):
                continue
            out[key] = value
        return out

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), default=str)


def _usage(prompt: int = 0, completion: int = 0) -> _Obj:
    return _Obj(
        input_tokens=prompt,
        output_tokens=completion,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


# -- request translation ---------------------------------------------------------------------


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n\n".join(p for p in parts if p)


def _tool_result_text(content: Any) -> str:
    return _text_of(content) if not isinstance(content, str) else content


def to_wire_messages(system: Any, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wire: list[dict[str, Any]] = []
    sys_text = _text_of(system)
    if sys_text:
        wire.append({"role": "system", "content": sys_text})
    for message in messages:
        role, content = message["role"], message["content"]
        if isinstance(content, str):
            wire.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text = _text_of(content)
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})},
                }
                for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                entry["tool_calls"] = calls
            if text or calls:
                wire.append(entry)
            continue
        # user: tool results become tool messages (they must directly follow the calls),
        # remaining text becomes a user message after them.
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                body = _tool_result_text(block.get("content"))
                if block.get("is_error"):
                    body = f"Error: {body}"
                wire.append(
                    {"role": "tool", "tool_call_id": block["tool_use_id"], "content": body}
                )
        text = _text_of([b for b in content if isinstance(b, dict) and b.get("type") == "text"])
        if text:
            wire.append({"role": "user", "content": text})
    return wire


def to_wire_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out = []
    for tool in tools or []:
        if tool.get("type") not in (None, "custom"):
            continue  # server-side tools (web search, code execution) have no equivalent
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
        )
    return out


def to_wire_request(request: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": request.get("model") or default_model(),
        "messages": to_wire_messages(request.get("system"), request["messages"]),
    }
    if request.get("max_tokens"):
        body["max_tokens"] = request["max_tokens"]
    tools = to_wire_tools(request.get("tools"))
    if tools:
        body["tools"] = tools
        choice = request.get("tool_choice") or {"type": "auto"}
        kind = choice.get("type")
        if kind == "none":
            body["tool_choice"] = "none"
        elif kind == "any":
            body["tool_choice"] = "required"
        elif kind == "tool":
            body["tool_choice"] = {"type": "function", "function": {"name": choice["name"]}}
        else:
            body["tool_choice"] = "auto"
    return body


_STOP = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}


# -- response / stream -----------------------------------------------------------------------


def _parse_args(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("tool arguments are not an object")
    return value


class MessageStream:
    """``async with client.messages.stream(**request) as stream`` — iterate for events in the
    content-block shape, then ``await stream.get_final_message()``."""

    def __init__(self, client: "AsyncLLMClient", request: dict[str, Any]) -> None:
        self._client = client
        self._body = to_wire_request(request) | {
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        self._final: _Obj | None = None

    async def __aenter__(self) -> "MessageStream":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[_Obj]:
        return self._events()

    async def _events(self) -> AsyncIterator[_Obj]:
        usage = _usage()
        yield _Obj(type="message_start", message=_Obj(usage=usage))
        blocks: list[_Obj] = []
        text_index: int | None = None
        tool_slots: dict[int, int] = {}  # wire tool index -> block index
        tool_bufs: dict[int, str] = {}
        stop = "end_turn"
        async with self._client._http.stream(
            "POST", "/chat/completions", json=self._body, headers=self._client._headers
        ) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread()).decode("utf-8", "replace")[:500]
                self._client._raise(resp.status_code, detail)
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except ValueError:
                    continue
                if u := chunk.get("usage"):
                    usage = _usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if text := delta.get("content"):
                        if text_index is None:
                            text_index = len(blocks)
                            blocks.append(_Obj(type="text", text=""))
                            yield _Obj(
                                type="content_block_start",
                                index=text_index,
                                content_block=blocks[text_index],
                            )
                        blocks[text_index].text += text
                        yield _Obj(
                            type="content_block_delta",
                            index=text_index,
                            delta=_Obj(type="text_delta", text=text),
                        )
                    for call in delta.get("tool_calls") or []:
                        wire_idx = call.get("index", 0)
                        fn = call.get("function") or {}
                        if wire_idx not in tool_slots:
                            if text_index is not None:
                                yield _Obj(type="content_block_stop", index=text_index)
                                text_index = None
                            idx = len(blocks)
                            tool_slots[wire_idx] = idx
                            tool_bufs[idx] = ""
                            blocks.append(
                                _Obj(
                                    type="tool_use",
                                    id=call.get("id") or f"call_{uuid.uuid4().hex[:20]}",
                                    name=fn.get("name", ""),
                                    input={},
                                )
                            )
                            yield _Obj(
                                type="content_block_start", index=idx, content_block=blocks[idx]
                            )
                        idx = tool_slots[wire_idx]
                        if frag := fn.get("arguments"):
                            tool_bufs[idx] += frag
                            yield _Obj(
                                type="content_block_delta",
                                index=idx,
                                delta=_Obj(type="input_json_delta", partial_json=frag),
                            )
                    if reason := choice.get("finish_reason"):
                        stop = _STOP.get(reason, "end_turn")
        if text_index is not None:
            yield _Obj(type="content_block_stop", index=text_index)
        for idx in sorted(tool_bufs):
            blocks[idx].input = _parse_args(tool_bufs[idx])  # ValueError ends the round
            yield _Obj(type="content_block_stop", index=idx)
        if tool_bufs and stop == "end_turn":
            stop = "tool_use"
        self._final = _Obj(type="message", role="assistant", content=blocks, stop_reason=stop, usage=usage)
        yield _Obj(type="message_delta", usage=usage)
        yield _Obj(type="message_stop")

    async def get_final_message(self) -> _Obj:
        if self._final is None:
            async for _ in self._events():
                pass
        assert self._final is not None
        return self._final


class _Messages:
    def __init__(self, client: "AsyncLLMClient") -> None:
        self._client = client

    def stream(self, **request: Any) -> MessageStream:
        return MessageStream(self._client, request)

    async def create(self, **request: Any) -> _Obj:
        body = to_wire_request(request)
        resp = await self._client._http.post(
            "/chat/completions", json=body, headers=self._client._headers
        )
        if resp.status_code >= 400:
            self._client._raise(resp.status_code, resp.text[:500])
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        blocks: list[_Obj] = []
        if msg.get("content"):
            blocks.append(_Obj(type="text", text=msg["content"]))
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            try:
                args = _parse_args(fn.get("arguments") or "")
            except ValueError:
                args = {}
            blocks.append(
                _Obj(
                    type="tool_use",
                    id=call.get("id") or f"call_{uuid.uuid4().hex[:20]}",
                    name=fn.get("name", ""),
                    input=args,
                )
            )
        u = data.get("usage") or {}
        stop = _STOP.get(choice.get("finish_reason") or "stop", "end_turn")
        if any(b.type == "tool_use" for b in blocks):
            stop = "tool_use"
        return _Obj(
            type="message",
            role="assistant",
            content=blocks,
            stop_reason=stop,
            usage=_usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)),
        )


class AsyncLLMClient:
    """OpenAI-compatible client exposing ``messages.stream`` and ``messages.create``."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = 120.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        key = api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")
        self.api_key = key
        self._headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self.messages = _Messages(self)

    def _raise(self, status: int, detail: str) -> None:
        if status in (401, 403):
            raise AuthenticationError(f"HTTP {status}: {detail}")
        raise LLMError(f"HTTP {status}: {detail}")

    async def aclose(self) -> None:
        await self._http.aclose()
