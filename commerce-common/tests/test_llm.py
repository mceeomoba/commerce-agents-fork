# SPDX-License-Identifier: Apache-2.0
import json

import httpx

from commerce_common.llm import AsyncLLMClient, to_wire_request


def _sse(*chunks):
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


def _client(handler):
    c = AsyncLLMClient(base_url="http://x/v1", api_key="k")
    c._http = httpx.AsyncClient(base_url="http://x/v1", transport=httpx.MockTransport(handler))
    return c


def test_request_translation():
    wire = to_wire_request(
        {
            "model": "m",
            "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
            "tools": [
                {"name": "t", "description": "d", "input_schema": {"type": "object"}},
                {"type": "web_search_20250305", "name": "web_search"},
            ],
            "tool_choice": {"type": "tool", "name": "t"},
            "messages": [
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "1", "name": "t", "input": {"a": 1}}],
                },
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "1", "content": "ok"}],
                },
            ],
        }
    )
    assert [m["role"] for m in wire["messages"]] == ["system", "user", "assistant", "tool"]
    assert len(wire["tools"]) == 1
    assert wire["tool_choice"]["function"]["name"] == "t"
    assert wire["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'


async def test_stream_text_and_tool_call():
    seen = {}

    def handler(req):
        seen["auth"] = req.headers["authorization"]
        return _sse(
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "search", "arguments": '{"q":'},
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [{"index": 0, "function": {"arguments": '"tent"}'}}]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 3}},
        )

    client = _client(handler)
    async with client.messages.stream(model="m", messages=[{"role": "user", "content": "x"}]) as s:
        types = [e.type async for e in s]
        final = await s.get_final_message()
    assert seen["auth"] == "Bearer k"
    assert "content_block_stop" in types and types[-1] == "message_stop"
    assert final.stop_reason == "tool_use"
    assert final.content[0].text == "Hello"
    assert final.content[1].input == {"q": "tent"} and final.content[1].name == "search"
    assert final.usage.input_tokens == 5


async def test_create_and_auth_error():
    client = _client(
        lambda r: httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )
    )
    r = await client.messages.create(model="m", messages=[{"role": "user", "content": "x"}])
    assert r.content[0].text == "hi"
    bad = _client(lambda r: httpx.Response(401, text="no"))
    import pytest

    from commerce_common.llm import AuthenticationError

    with pytest.raises(AuthenticationError):
        await bad.messages.create(model="m", messages=[{"role": "user", "content": "x"}])
