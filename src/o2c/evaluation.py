"""Scoring for the evaluation set in eval/questions.yaml.

Each question has simple, checkable expectations: tools called, document numbers named,
numbers in the answer, answer language. No LLM grades another LLM here: every check is
plain Python, so a pass or fail can be explained line by line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from o2c.language import detect_language

# A number with digits and optional . or , separators, e.g. 4.012,65 or 2,170,150.00
_NUMBER = re.compile(r"\d[\d.,]*\d|\d")


def parse_number(token: str) -> Decimal | None:
    """Read a number in German or English format. Three digits after a single
    separator mean thousands (1.000 = 1000), otherwise it is the decimal mark."""
    dots, commas = token.count("."), token.count(",")
    if dots and commas:  # both present: the last one is the decimal mark
        decimal_mark = "." if token.rfind(".") > token.rfind(",") else ","
        thousands = "," if decimal_mark == "." else "."
        token = token.replace(thousands, "").replace(decimal_mark, ".")
    elif dots or commas:
        mark = "." if dots else ","
        groups = token.split(mark)
        if len(groups) > 2 or len(groups[-1]) == 3:
            token = token.replace(mark, "")  # thousands separators only
        else:
            token = token.replace(mark, ".")
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def numbers_in(text: str) -> set[Decimal]:
    values = (parse_number(t) for t in _NUMBER.findall(text))
    return {v.normalize() for v in values if v is not None}


@dataclass
class Result:
    id: str
    question: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    seconds: float = 0.0
    answer: str = ""


def check(case: dict[str, Any], answer: str, tools_called: list[str]) -> list[str]:
    """Return the list of failed checks. An empty list means the question passed."""
    failures = []
    low = answer.lower()

    if case.get("lang") and detect_language(answer) != case["lang"]:
        failures.append(f"language is not {case['lang']}")
    for tool in case.get("tools", []):
        if tool not in tools_called:
            failures.append(f"tool {tool} not called")
    for text in case.get("contains", []):
        if text.lower() not in low:
            failures.append(f"missing '{text}'")
    any_of = case.get("contains_any", [])
    if any_of and not any(text.lower() in low for text in any_of):
        failures.append(f"none of {any_of}")
    found = numbers_in(answer)
    for number in case.get("numbers", []):
        if Decimal(number).normalize() not in found:
            failures.append(f"number {number} missing")
    for text in case.get("not_contains", []):
        if text.lower() in low:
            failures.append(f"must not contain '{text}'")
    return failures
