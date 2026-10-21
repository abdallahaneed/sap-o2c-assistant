"""Local LLM through Ollama, free and offline, with the same interface as the Anthropic SDK.

The assistant loop speaks Anthropic style: client.messages.create(...) returns content
blocks (text, tool_use) and a stop_reason. This adapter translates that to Ollama's
/api/chat format and back. So assistant.py has one loop for both providers.

Setup on the Mac: install the Ollama app, then `ollama pull qwen3:4b-instruct`.
Use an "instruct" model: thinking models are slow and leak their reasoning.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any

import httpx

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:4b-instruct"


def strip_thinking(text: str) -> str:
    """Thinking models may put their reasoning in the answer, ending with </think>. Drop it."""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


class LLMUnavailable(Exception):
    """The model server cannot be reached. The API turns this into a clear 503 message."""


def _block_value(block: Any, key: str) -> Any:
    """Content blocks arrive as objects (from a response) or as dicts (tool results)."""
    return block.get(key) if isinstance(block, dict) else getattr(block, key, None)


class _Messages:
    def __init__(self, client: OllamaClient) -> None:
        self._client = client

    def create(self, **kwargs: Any) -> SimpleNamespace:
        return self._client.create(**kwargs)


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        num_ctx: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_URL).rstrip("/")
        # Ollama's default context is small. Tools plus results need more room.
        self.num_ctx = num_ctx or int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        # Local models are slower than an API: allow up to 3 minutes per answer
        self._http = httpx.Client(timeout=180, transport=transport)
        self.messages = _Messages(self)  # so callers can write client.messages.create(...)

    # Translation: Anthropic style -> Ollama

    @staticmethod
    def to_ollama_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    @staticmethod
    def to_ollama_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        tool_names: dict[str, str] = {}  # tool_use id -> tool name, Ollama wants the name
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                out.append({"role": msg["role"], "content": content})
                continue
            if msg["role"] == "assistant":
                text = "".join(
                    _block_value(b, "text") or ""
                    for b in content
                    if _block_value(b, "type") == "text"
                )
                calls = []
                for b in content:
                    if _block_value(b, "type") == "tool_use":
                        tool_names[_block_value(b, "id")] = _block_value(b, "name")
                        calls.append(
                            {
                                "function": {
                                    "name": _block_value(b, "name"),
                                    "arguments": _block_value(b, "input"),
                                }
                            }
                        )
                out.append({"role": "assistant", "content": text, "tool_calls": calls})
            else:  # user message with tool results: one "tool" message per result
                for b in content:
                    out.append(
                        {
                            "role": "tool",
                            "tool_name": tool_names.get(b["tool_use_id"], ""),
                            "content": b["content"],
                        }
                    )
        return out

    # Translation: Ollama -> Anthropic style

    @staticmethod
    def to_response(data: dict[str, Any], call_offset: int = 0) -> SimpleNamespace:
        message = data.get("message", {})
        blocks: list[SimpleNamespace] = []
        text = strip_thinking(message.get("content") or "")
        if text:
            blocks.append(SimpleNamespace(type="text", text=text))
        for i, call in enumerate(message.get("tool_calls") or []):
            fn = call.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):  # some models send arguments as a JSON string
                args = json.loads(args) if args.strip() else {}
            blocks.append(
                SimpleNamespace(
                    type="tool_use",
                    # Ollama has no call ids: make stable ones so results can be matched
                    id=call.get("id") or f"call_{call_offset + i}",
                    name=fn.get("name", ""),
                    input=args,
                )
            )
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        return SimpleNamespace(content=blocks, stop_reason=stop)

    def create(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1500,
    ) -> SimpleNamespace:
        payload: dict[str, Any] = {
            "model": model,
            "messages": self.to_ollama_messages(system, messages),
            "tools": self.to_ollama_tools(tools or []),
            "stream": False,
            "think": False,  # skip the slow reasoning phase of thinking models
            "options": {"num_ctx": self.num_ctx, "num_predict": max_tokens, "temperature": 0},
        }
        try:
            response = self._http.post(f"{self.base_url}/api/chat", json=payload)
            if response.status_code == 400 and "think" in response.text:
                # model without thinking support: send again without the flag
                payload.pop("think")
                response = self._http.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.TransportError as err:
            raise LLMUnavailable(
                f"Ollama ist unter {self.base_url} nicht erreichbar. Starte die Ollama-App. "
                f"/ Ollama is not reachable at {self.base_url}. Start the Ollama app."
            ) from err
        if response.status_code == 404:
            raise LLMUnavailable(
                f"Modell {model} fehlt. Lade es mit: ollama pull {model} "
                f"/ Model {model} missing. Run: ollama pull {model}"
            )
        response.raise_for_status()
        # count earlier tool calls so ids stay unique within one conversation
        offset = sum(1 for m in messages if m["role"] == "assistant")
        return self.to_response(response.json(), call_offset=offset * 10)

    def is_available(self) -> bool:
        """Quick check for the health endpoint: is the Ollama server running?"""
        try:
            return self._http.get(f"{self.base_url}/api/tags", timeout=1).status_code == 200
        except httpx.TransportError:
            return False
