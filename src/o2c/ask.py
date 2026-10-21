"""Ask the assistant from the terminal, without the API and without quotes.

Run: uv run python -m o2c.ask Welche Auftraege sind geliefert aber nicht fakturiert
"""

from __future__ import annotations

import json
import sys
import time

from dotenv import load_dotenv

from o2c import db, queries
from o2c.assistant import Assistant
from o2c.llm import LLMUnavailable
from o2c.sap_client import PROJECT_ROOT
from o2c.sync import run_sync


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        print("Usage: uv run python -m o2c.ask <your question>")
        return

    engine = db.get_engine()
    db.create_tables(engine)
    if queries.last_sync(engine) is None:
        run_sync(None, engine)  # empty DB: load fixtures first

    print(f"Frage / Question: {question}\n")
    start = time.perf_counter()
    try:
        reply = Assistant(engine).chat(question)
    except LLMUnavailable as err:
        print(err)
        return

    for call in reply.tool_calls:
        status = "ERROR" if call.is_error else "ok"
        print(f"  tool: {call.name}({json.dumps(call.input, ensure_ascii=False)}) {status}")
    print(f"\n{reply.answer}\n")
    print(f"({time.perf_counter() - start:.1f} s)")


if __name__ == "__main__":
    main()
