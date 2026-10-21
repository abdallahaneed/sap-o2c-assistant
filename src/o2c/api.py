"""FastAPI backend: chat, KPIs and data refresh.

Start: uv run uvicorn o2c.api:app --reload
Docs:  http://127.0.0.1:8000/docs (FastAPI builds them from the code)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from o2c import db, queries
from o2c.assistant import Assistant
from o2c.llm import LLMUnavailable, OllamaClient
from o2c.sap_client import DEFAULT_BASE_URL, PROJECT_ROOT
from o2c.sync import run_sync

load_dotenv(PROJECT_ROOT / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup: open the DB, load fixtures if the DB is empty."""
    engine = db.get_engine()
    db.create_tables(engine)
    if queries.last_sync(engine) is None:
        run_sync(None, engine)  # first start: fill from fixtures, no key needed
    app.state.engine = engine
    app.state.assistant = None  # created on first chat, needs ANTHROPIC_API_KEY
    yield
    engine.dispose()


app = FastAPI(title="SAP O2C Assistant", version="0.1.0", lifespan=lifespan)


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    # The example pre-fills the /docs page, so nobody has to type JSON quotes
    question: str = Field(
        min_length=1,
        max_length=2000,
        examples=["Welche Aufträge sind geliefert, aber nicht fakturiert?"],
    )
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "ollama")


def get_assistant():
    """Create the assistant once. Without a model, chat is off but the KPIs still work."""
    if app.state.assistant is None:
        if provider() == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
            raise HTTPException(
                status_code=503,
                detail="Kein ANTHROPIC_API_KEY gesetzt. Chat ist aus, das Dashboard läuft. "
                "/ No ANTHROPIC_API_KEY set. Chat is off, the dashboard works.",
            )
        app.state.assistant = Assistant(app.state.engine)
    return app.state.assistant


@app.get("/health")
def health() -> dict[str, Any]:
    if provider() == "anthropic":
        enabled = bool(os.getenv("ANTHROPIC_API_KEY"))
    else:
        enabled = OllamaClient().is_available()
    return {"status": "ok", "chat_provider": provider(), "chat_enabled": enabled}


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    try:
        reply = get_assistant().chat(
            request.question, [turn.model_dump() for turn in request.history]
        )
    except LLMUnavailable as err:  # Ollama not running or model not pulled
        raise HTTPException(status_code=503, detail=str(err)) from err
    return {"answer": reply.answer, "tool_calls": [asdict(c) for c in reply.tool_calls]}


@app.get("/kpis")
def kpis() -> dict[str, Any]:
    engine = app.state.engine
    open_orders = queries.get_open_orders(engine)
    not_billed = queries.get_delivered_not_billed(engine)
    return {
        "last_sync": queries.last_sync(engine),
        "open_orders": {"count": open_orders["count"], "value": open_orders["total_value"]},
        "delivered_not_billed": {
            "count": not_billed["count"],
            "value": not_billed["total_value"],
            "deliveries": not_billed["deliveries"],
        },
        "revenue_by_month": queries.revenue_by_month(engine),
        "top_customers": queries.top_customers(engine, 5),
        "funnel": queries.o2c_funnel(engine),
        "currency": "USD",
    }


@app.post("/refresh")
def refresh() -> dict[str, Any]:
    """Reload data: from the SAP sandbox if SAP_API_KEY is set, else from fixtures.

    This only writes our local SQLite file. Nothing is ever written to SAP.
    """
    api_key = os.getenv("SAP_API_KEY", "").strip() or None
    counts = run_sync(
        api_key, app.state.engine, base_url=os.getenv("SAP_BASE_URL", DEFAULT_BASE_URL)
    )
    return {"source": "api" if api_key else "fixtures", "rows": counts}
