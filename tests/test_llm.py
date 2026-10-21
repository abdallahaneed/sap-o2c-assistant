"""Tests for the Ollama adapter. A fake Ollama server answers through httpx.MockTransport."""

import json
from types import SimpleNamespace

import httpx
import pytest

from o2c.assistant import TOOLS
from o2c.llm import LLMUnavailable, OllamaClient


def fake_ollama(reply, seen=None, status=200):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(status, json=reply)

    return httpx.MockTransport(handler)


def test_tools_are_translated_to_ollama_format():
    tools = OllamaClient.to_ollama_tools(TOOLS)
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "find_customers"
    assert tools[0]["function"]["parameters"] == TOOLS[0]["input_schema"]


def test_conversation_with_tool_results_is_translated():
    messages = [
        {"role": "user", "content": "Auftrag 1?"},
        {
            "role": "assistant",
            "content": [
                SimpleNamespace(
                    type="tool_use", id="call_0", name="get_order_details", input={"order_id": "1"}
                ),
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_0", "content": "{}"}],
        },
    ]
    out = OllamaClient.to_ollama_messages("SYS", messages)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    assert out[2]["tool_calls"][0]["function"]["arguments"] == {"order_id": "1"}
    assert out[3]["tool_name"] == "get_order_details"  # matched via the id


def test_tool_call_reply_becomes_tool_use_block():
    seen = []
    reply = {
        "message": {
            "content": "",
            "tool_calls": [{"function": {"name": "top_customers", "arguments": {"n": 3}}}],
        }
    }
    client = OllamaClient("http://fake", transport=fake_ollama(reply, seen))
    res = client.messages.create(model="m", system="S", messages=[{"role": "user", "content": "x"}])

    assert res.stop_reason == "tool_use"
    block = res.content[0]
    assert (block.type, block.name, block.input) == ("tool_use", "top_customers", {"n": 3})
    assert seen[0]["think"] is False and seen[0]["stream"] is False


def test_arguments_as_json_string_are_parsed():
    reply = {"message": {"tool_calls": [{"function": {"name": "t", "arguments": '{"n": 2}'}}]}}
    res = OllamaClient.to_response(reply)
    assert res.content[0].input == {"n": 2}


def test_text_reply_ends_the_turn():
    res = OllamaClient.to_response({"message": {"content": "Fertig."}})
    assert res.stop_reason == "end_turn"
    assert res.content[0].text == "Fertig."


def test_model_without_thinking_is_retried_without_flag():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if "think" in body:
            return httpx.Response(400, text='{"error":"model does not support thinking"}')
        return httpx.Response(200, json={"message": {"content": "ok"}})

    client = OllamaClient("http://fake", transport=httpx.MockTransport(handler))
    res = client.messages.create(model="m", system="S", messages=[{"role": "user", "content": "x"}])
    assert res.content[0].text == "ok"
    assert len(seen) == 2 and "think" not in seen[1]


def test_missing_model_gives_pull_hint():
    client = OllamaClient("http://fake", transport=fake_ollama({"error": "not found"}, status=404))
    with pytest.raises(LLMUnavailable, match="ollama pull qwen3:4b-instruct"):
        client.messages.create(model="qwen3:4b-instruct", system="S", messages=[])


def test_server_down_raises_llm_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = OllamaClient("http://fake", transport=httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailable, match="Ollama"):
        client.messages.create(model="m", system="S", messages=[])
    assert client.is_available() is False


def test_leaked_thinking_is_removed():
    reply = {"message": {"content": "Okay, let me think...\n</think>\n\nEs gibt 3 Aufträge."}}
    assert OllamaClient.to_response(reply).content[0].text == "Es gibt 3 Aufträge."
