"""Tests for the UI helpers and a smoke test of the Streamlit app with a fake backend."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from o2c import ui

APP = str(Path(__file__).parents[1] / "app" / "streamlit_app.py")

FAKE_KPIS = {
    "last_sync": {"run_time": "2026-10-21 14:03:05.739993", "source": "fixtures"},
    "open_orders": {"count": 48, "value": "4012.65"},
    "delivered_not_billed": {
        "count": 1,
        "value": "52.65",
        "deliveries": [
            {
                "delivery_id": "80000001",
                "customer_id": "17100001",
                "customer_name": "Domestic US Customer 1",
                "goods_issue_date": "2016-08-17",
                "billing_status": "A",
                "order_ids": ["3"],
                "value": "52.65",
            }
        ],
    },
    "revenue_by_month": [{"month": "2016-08", "revenue": "52.65"}],
    "top_customers": [{"customer_id": "17100001", "customer_name": "C1", "revenue": "52.65"}],
    "funnel": {"ordered": 3, "delivered": 2, "billed": 1},
    "currency": "USD",
}


def test_money_format_german_and_english():
    assert ui.fmt_money("4012.65", "de") == "4.012,65 USD"
    assert ui.fmt_money("4012.65", "en") == "4,012.65 USD"
    assert ui.fmt_money(None, "de") == "0,00 USD"


def test_time_format():
    assert ui.fmt_time("2026-10-21 14:03:05.739993", "de") == "21.10.2026 14:03 UTC"
    assert ui.fmt_time(None, "en") == "-"


def test_both_languages_have_the_same_texts():
    assert ui.TEXT["de"].keys() == ui.TEXT["en"].keys()


@pytest.fixture
def fake_backend(monkeypatch):
    calls = []

    def get_json(path):
        return {"/kpis": FAKE_KPIS, "/health": {"chat_enabled": True}}[path]

    def post_json(path, body=None, timeout=120):
        calls.append((path, body))
        return {"answer": "Lieferung 80000001 ist offen.", "tool_calls": []}

    monkeypatch.setattr(ui, "get_json", get_json)
    monkeypatch.setattr(ui, "post_json", post_json)
    yield calls


def run_app():
    import streamlit as st

    st.cache_data.clear()  # cached KPIs from an earlier test must not leak in
    return AppTest.from_file(APP, default_timeout=30).run()


def test_chat_page_shows_examples(fake_backend):
    at = run_app()
    assert not at.exception
    assert at.title[0].value == "SAP O2C Assistent"
    assert any("geliefert" in b.label for b in at.button)


def test_chat_sends_question_and_shows_answer(fake_backend):
    at = run_app()
    at.chat_input[0].set_value("Was ist offen?").run()
    assert fake_backend[0][0] == "/chat"
    assert fake_backend[0][1]["question"] == "Was ist offen?"
    assert any("80000001" in m.value for m in at.markdown)


def test_dashboard_shows_kpis_in_german_format(fake_backend):
    at = run_app()
    at.sidebar.radio[1].set_value("Dashboard").run()
    assert not at.exception
    assert "48" in [m.value for m in at.metric]
    assert any("4.012,65 USD" in m.value for m in at.markdown)
