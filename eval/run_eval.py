"""Run the 15 evaluation questions against the assistant and write a score report.

Run: uv run python eval/run_eval.py
Optional: uv run python eval/run_eval.py dnb_de top_customer   (only these ids)
Writes eval/results.md (for the README) and eval/results.json (full answers).
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from o2c import db, queries
from o2c.assistant import Assistant
from o2c.evaluation import Result, check
from o2c.sap_client import PROJECT_ROOT
from o2c.sync import run_sync

EVAL_DIR = Path(__file__).parent


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    cases = yaml.safe_load((EVAL_DIR / "questions.yaml").read_text(encoding="utf-8"))
    only = set(sys.argv[1:])
    if only:
        cases = [c for c in cases if c["id"] in only]

    engine = db.get_engine()
    db.create_tables(engine)
    if queries.last_sync(engine) is None:
        run_sync(None, engine)

    assistant = Assistant(engine)
    print(f"Model: {assistant.model}  ({len(cases)} questions)\n")

    results: list[Result] = []
    for case in cases:
        start = time.perf_counter()
        try:
            reply = assistant.chat(case["question"])
            answer, tools = reply.answer, [c.name for c in reply.tool_calls]
        except Exception as err:  # a crash counts as a failed question, the run goes on
            answer, tools = f"ERROR: {err}", []
        seconds = time.perf_counter() - start
        failures = check(case, answer, tools)
        results.append(
            Result(case["id"], case["question"], not failures, failures, tools, seconds, answer)
        )
        mark = "PASS" if not failures else "FAIL"
        print(f"{mark}  {case['id']:<30} {seconds:5.1f} s  {'; '.join(failures)}")

    passed = sum(r.passed for r in results)
    avg = sum(r.seconds for r in results) / max(len(results), 1)
    print(f"\nScore: {passed}/{len(results)}   average {avg:.1f} s per question")

    provider = os.getenv("LLM_PROVIDER", "ollama")
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Evaluation result",
        "",
        f"Model: {assistant.model} ({provider}). Run: {stamp}.",
        f"Score: **{passed} of {len(results)}** passed. Average time: {avg:.1f} s.",
        "",
        "| Question | Result | Time | Failed checks |",
        "|---|---|---|---|",
    ]
    for r in results:
        failed = "; ".join(r.failures) or "-"
        lines.append(
            f"| {r.question} | {'pass' if r.passed else 'fail'} | {r.seconds:.0f} s | {failed} |"
        )
    (EVAL_DIR / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (EVAL_DIR / "results.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Written: eval/results.md and eval/results.json")


if __name__ == "__main__":
    main()
