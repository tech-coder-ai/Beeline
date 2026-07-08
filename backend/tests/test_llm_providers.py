"""LLM provider tests: Stellar request/response contract and JSON parsing."""
import httpx
import pytest

from app.llm.base import parse_json_loosely
from app.llm.providers import StellarProvider


def test_parse_json_loosely_strips_markdown_fences():
    text = '```json\n{"summary": "ok", "confidence": 0.9}\n```'
    assert parse_json_loosely(text) == {"summary": "ok", "confidence": 0.9}


def test_parse_json_loosely_extracts_embedded_object():
    text = 'Sure, here is the result: {"a": 1, "b": [1,2]} Hope that helps!'
    assert parse_json_loosely(text) == {"a": 1, "b": [1, 2]}


def test_parse_json_loosely_returns_empty_on_garbage():
    assert parse_json_loosely("not json at all") == {}


@pytest.mark.asyncio
async def test_stellar_provider_sends_expected_payload():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content
        return httpx.Response(200, json={"response": "hello from stellar"})

    transport = httpx.MockTransport(handler)

    provider = StellarProvider({
        "endpoint": "http://stellar.local/generate",
        "response_field": "response",
    })

    import httpx as httpx_module
    original_client = httpx_module.AsyncClient

    class PatchedClient(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx_module.AsyncClient = PatchedClient
    try:
        result = await provider.complete("system prompt", "user message")
    finally:
        httpx_module.AsyncClient = original_client

    assert result.text == "hello from stellar"
    assert captured["url"] == "http://stellar.local/generate"
    import json
    body = json.loads(captured["body"])
    assert body == {"systemPrompt": "system prompt", "userMessage": "user message"}


@pytest.mark.asyncio
async def test_stellar_provider_nested_response_field():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"output": "nested text"}})

    transport = httpx.MockTransport(handler)
    provider = StellarProvider({
        "endpoint": "http://stellar.local/generate",
        "response_field": "data.output",
    })

    import httpx as httpx_module
    original_client = httpx_module.AsyncClient

    class PatchedClient(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx_module.AsyncClient = PatchedClient
    try:
        result = await provider.complete("sys", "usr")
    finally:
        httpx_module.AsyncClient = original_client

    assert result.text == "nested text"
