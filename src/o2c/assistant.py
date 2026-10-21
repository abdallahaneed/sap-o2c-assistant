"""The O2C assistant: an LLM with tool calling over our fixed, read-only query functions.

Flow for one question:
1. Send the question plus the tool list to the model.
2. If it answers with tool_use blocks, run those Python functions and send the results back.
3. Repeat until it answers with plain text (stop_reason "end_turn"), at most MAX_ROUNDS times.

The model never sees the database and never writes SQL. It can only pick a tool and its
parameters. Two providers, same loop: a free local model via Ollama (default) or Claude.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.engine import Engine

from o2c import queries, rag
from o2c.llm import DEFAULT_OLLAMA_MODEL, OllamaClient

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
MAX_ROUNDS = 6  # safety stop for the tool loop
MAX_LIST_ITEMS = 50  # cap long lists so a tool result does not flood the context

SYSTEM_PROMPT = """Du bist ein Assistent für den Vertriebsinnendienst. Du beantwortest Fragen
zum Order-to-Cash-Prozess in SAP S/4HANA: Aufträge, Lieferungen, Fakturen, Kunden.
You answer questions about the SAP Order-to-Cash process.

Rules:
1. Reply in the language of the user's question, German or English.
2. Use the tools for every number, order, delivery or invoice. Never invent data.
3. Always name the document numbers you used: Auftrag/order, Lieferung/delivery,
   Faktura/invoice. Name deliveries and invoices too, not only orders.
   If a list is long, give the total and the most relevant numbers.
4. If data is missing or a tool returns nothing, say so clearly. Do not guess.
   If a result has a "note" field, pass that note on to the user.
5. Explain briefly which O2C step is behind the answer (order, delivery, goods issue,
   billing). For process questions, call search_process_knowledge and base the
   explanation on those notes. Search with German terms, the notes are in German.
6. You are read only. You cannot change, create or release anything in SAP.
   If asked to, explain which SAP transaction a user would use instead.
7. Customer names: use find_customers first to get the customer number.
8. Data: demo data from the SAP S/4HANA Cloud sandbox, up to 1000 rows per table,
   all amounts in USD. Mention this when it matters for the answer.
9. Call each tool only once per question with the same parameters. The result
   does not change, so read it instead of calling again.
10. Keep answers short: a direct answer first, then the documents, then one or two
   sentences on the process step. Plain text, no tables."""

TOOLS: list[dict[str, Any]] = [
    {
        "name": "find_customers",
        "description": (
            "Find customers by part of their name and return customer numbers. "
            "Use this first when the user names a customer instead of giving a number, "
            "then pass the customer_id to other tools. Returns up to 10 matches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Part of the name"}},
            "required": ["name"],
        },
    },
    {
        "name": "get_open_orders",
        "description": (
            "List open sales orders (overall status A or B: not yet completely processed) "
            "with count, total net value and per-order delivery status. "
            "Optionally filter by customer_id. Use for questions about open orders, "
            "offene Aufträge, or open order value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer number, e.g. 17100001. Omit for all customers.",
                }
            },
        },
    },
    {
        "name": "get_delivered_not_billed",
        "description": (
            "List outbound deliveries where goods issue is done but billing is still open, "
            "with the sales orders behind them and their value. Use for questions like "
            "'delivered but not billed', 'geliefert aber nicht fakturiert', missing invoices."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_order_details",
        "description": (
            "Full details of one sales order: header, customer, items, document flow "
            "(deliveries, goods issue, invoices) and the O2C step it has reached. "
            "Use for 'where is order X', 'Status von Auftrag X'. Returns null if unknown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "Sales order number"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "revenue_by_customer",
        "description": (
            "Billed revenue per customer between two dates (both included). Invoices and "
            "debit memos count positive, credit memos negative; down payment requests and "
            "cancelled invoices are excluded. Dates as YYYY-MM-DD."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "top_customers",
        "description": "Top n customers by billed revenue over all loaded data (n from 1 to 50).",
        "input_schema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "description": "How many customers"}},
            "required": ["n"],
        },
    },
    {
        "name": "search_process_knowledge",
        "description": (
            "Search the team's own O2C process notes (German, with English headings). "
            "Use for 'what does X mean', 'why does Y happen', SAP transactions, statuses, "
            "billing types and typical problems. Returns the 3 most relevant passages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search text, German"}},
            "required": ["query"],
        },
    },
]


def _json_default(value: Any) -> Any:
    """json.dumps does not know Decimal and date. Send them as text."""
    if isinstance(value, Decimal | date):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _cap_lists(result: Any) -> Any:
    """Shorten long lists inside a result and say so, instead of silently cutting."""
    if isinstance(result, dict):
        capped = {}
        for key, value in result.items():
            if isinstance(value, list) and len(value) > MAX_LIST_ITEMS:
                capped[key] = value[:MAX_LIST_ITEMS]
                capped[f"{key}_note"] = f"showing {MAX_LIST_ITEMS} of {len(value)}"
            else:
                capped[key] = value
        return capped
    return result


def make_client(provider: str) -> tuple[Any, str]:
    """Pick the LLM backend from LLM_PROVIDER in .env: 'ollama' (free, local) or 'anthropic'."""
    if provider == "anthropic":
        import anthropic  # imported here so the free setup does not need it at runtime

        model = os.getenv("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
        return anthropic.Anthropic(), model  # reads ANTHROPIC_API_KEY from the environment
    model = os.getenv("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
    return OllamaClient(), model


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    output: Any
    is_error: bool = False


@dataclass
class AssistantReply:
    answer: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class Assistant:
    def __init__(
        self,
        engine: Engine,
        client: Any | None = None,
        model: str | None = None,
        knowledge_search: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        if client is None:
            client, default_model = make_client(os.getenv("LLM_PROVIDER", "ollama"))
        else:
            default_model = "test-model"
        self.client = client
        self.model = model or default_model
        search = knowledge_search or rag.search_process_knowledge

        # Tool name -> Python function. This dict is the whole permission system.
        self.tools: dict[str, Callable[..., Any]] = {
            "find_customers": lambda name: queries.find_customers(engine, name),
            "get_open_orders": lambda customer_id=None: queries.get_open_orders(
                engine, customer_id
            ),
            "get_delivered_not_billed": lambda: queries.get_delivered_not_billed(engine),
            "get_order_details": lambda order_id: queries.get_order_details(engine, order_id),
            "revenue_by_customer": lambda date_from, date_to: queries.revenue_by_customer(
                engine, date_from, date_to
            ),
            "top_customers": lambda n: queries.top_customers(engine, n),
            "search_process_knowledge": lambda query: search(query),
        }

    def run_tool(self, name: str, tool_input: dict[str, Any]) -> ToolCall:
        """Run one tool. Errors go back to Claude as text, so it can correct itself."""
        if name not in self.tools:
            return ToolCall(name, tool_input, f"Unknown tool: {name}", is_error=True)
        try:
            output = _cap_lists(self.tools[name](**tool_input))
            return ToolCall(name, tool_input, output)
        except Exception as err:  # wrong parameter names or values from the model
            return ToolCall(name, tool_input, f"{type(err).__name__}: {err}", is_error=True)

    def chat(self, question: str, history: list[dict[str, str]] | None = None) -> AssistantReply:
        """Answer one question. history holds earlier turns as plain text messages."""
        messages: list[dict[str, Any]] = [*(history or []), {"role": "user", "content": question}]
        calls: list[ToolCall] = []

        for _ in range(MAX_ROUNDS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            if response.stop_reason != "tool_use":
                text = "".join(b.text for b in response.content if b.type == "text").strip()
                return AssistantReply(text or "(keine Antwort / no answer)", calls)

            # Claude wants tools: keep its message, run every requested tool, send results back
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                call = self.run_tool(block.name, block.input)
                calls.append(call)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(call.output, default=_json_default),
                        "is_error": call.is_error,
                    }
                )
            messages.append({"role": "user", "content": results})

        return AssistantReply(
            "Ich konnte die Frage nicht in wenigen Schritten beantworten. "
            "Bitte formuliere sie genauer. / I could not answer in a few steps, "
            "please ask more specifically.",
            calls,
        )
