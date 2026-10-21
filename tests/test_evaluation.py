"""Tests for the evaluation checks, so a score in the README can be trusted."""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from o2c.assistant import TOOLS
from o2c.evaluation import check, detect_language, parse_number


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("4.012,65", "4012.65"),  # German
        ("4,012.65", "4012.65"),  # English
        ("4012.65", "4012.65"),
        ("2.170.150", "2170150"),  # German thousands only
        ("2,170,150.00", "2170150"),
        ("402,65", "402.65"),
        ("48", "48"),
    ],
)
def test_numbers_in_both_formats(token, expected):
    assert parse_number(token).normalize() == Decimal(expected).normalize()


def test_language_detection():
    assert detect_language("Es gibt 3 Aufträge, die nicht fakturiert sind.") == "de"
    assert detect_language("There are 3 orders that are not billed yet.") == "en"


def test_check_passes_good_answer():
    case = {"lang": "de", "tools": ["get_open_orders"], "numbers": ["4012.65"]}
    answer = "Der offene Auftragswert ist 4.012,65 USD für 48 Aufträge."
    assert check(case, answer, ["get_open_orders"]) == []


def test_check_lists_every_failure():
    case = {
        "lang": "en",
        "tools": ["top_customers"],
        "contains": ["Cycles 17"],
        "not_contains": ["80000"],
    }
    failures = check(case, "Der Kunde mit Lieferung 80000001 ist nicht bekannt.", [])
    assert len(failures) == 4


def test_question_file_is_valid():
    path = Path(__file__).parents[1] / "eval" / "questions.yaml"
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))
    tool_names = {t["name"] for t in TOOLS}
    assert len(cases) == 15
    assert len({c["id"] for c in cases}) == 15  # ids are unique
    for case in cases:
        assert case["lang"] in {"de", "en"}
        assert set(case.get("tools", [])) <= tool_names  # no typo in a tool name
