"""Anthropic SDK integratsiyasi: haqiqiy HTTP o'rniga soxta transport."""

import json

import anthropic
import httpx2 as httpx
import pytest

from app.ai.llm.anthropic_client import AnthropicLLM
from app.ai.llm.base import LLMError, LLMUnavailable
from app.ai.llm.fallback import FallbackLLM
from app.ai.tools import TOOLS


def make_llm(handler, model: str = "claude-haiku-4-5") -> AnthropicLLM:
    client = anthropic.AsyncAnthropic(
        api_key="test", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    return AnthropicLLM("test", model, client=client)


def ok_body(model: str, content: list[dict], stop_reason: str) -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 50,
            "output_tokens": 12,
            "cache_read_input_tokens": 3000,
            "cache_creation_input_tokens": 0,
        },
    }


async def test_request_shape_and_tool_use_parsing():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        content = [
            {"type": "text", "text": "Qidiryapman"},
            {"type": "tool_use", "id": "toolu_1", "name": "search_products", "input": {"query": "ko'ylak"}},
        ]
        return httpx.Response(200, json=ok_body(seen["model"], content, "tool_use"))

    llm = make_llm(handler)
    resp = await llm.chat(system="SYS", messages=[{"role": "user", "content": "salom"}], tools=TOOLS)

    assert seen["model"] == "claude-haiku-4-5" and seen["max_tokens"] == 2048
    assert seen["system"] == [{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]
    assert [t["name"] for t in seen["tools"]] == [t["name"] for t in TOOLS]
    assert resp.stop_reason == "tool_use" and resp.text == "Qidiryapman"
    assert resp.tool_calls[0].name == "search_products" and resp.tool_calls[0].input == {"query": "ko'ylak"}
    assert resp.usage.cache_read_tokens == 3000 and resp.usage.total_in == 3050
    # Bloklar keyingi so'rovga qaytarib yuborish uchun toza dict
    assert resp.content[1] == {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "search_products",
        "input": {"query": "ko'ylak"},
    }


@pytest.mark.parametrize(
    "status,exc", [(529, LLMUnavailable), (500, LLMUnavailable), (429, LLMUnavailable), (400, LLMError)]
)
async def test_error_mapping(status, exc):
    def handler(request):
        return httpx.Response(status, json={"type": "error", "error": {"type": "x", "message": "boom"}})

    with pytest.raises(exc):
        await make_llm(handler).chat(system="S", messages=[{"role": "user", "content": "x"}])


async def test_fallback_switches_model_on_overload():
    models = []

    def handler(request):
        body = json.loads(request.content)
        models.append((body["model"], body["max_tokens"]))
        if body["model"] == "claude-haiku-4-5":
            return httpx.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "x"}})
        return httpx.Response(200, json=ok_body(body["model"], [{"type": "text", "text": "zaxira"}], "end_turn"))

    primary = make_llm(handler)
    secondary = make_llm(handler, "claude-sonnet-5")
    secondary.max_tokens = 8192
    resp = await FallbackLLM(primary, secondary).chat(
        system="S", messages=[{"role": "user", "content": "x"}], max_tokens=400
    )
    assert resp.text == "zaxira"
    assert models == [("claude-haiku-4-5", 400), ("claude-sonnet-5", 8192)]
