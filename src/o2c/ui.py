"""Helpers for the Streamlit app: API calls, number formats and the UI texts in DE and EN.

Kept outside the Streamlit script so they can be tested like any other Python code.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
CHAT_TIMEOUT = 240  # a local model on 8 GB RAM can take a while


class ApiError(Exception):
    """The backend is down or answered with an error. The message is shown in the UI."""


def _call(method: str, path: str, body: dict | None = None, timeout: float = 30) -> Any:
    try:
        response = httpx.request(method, f"{API_URL}{path}", json=body, timeout=timeout)
    except httpx.TransportError as err:
        raise ApiError(
            f"Backend nicht erreichbar unter {API_URL}. Starte: uv run uvicorn o2c.api:app "
            f"/ Backend not reachable at {API_URL}."
        ) from err
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise ApiError(str(detail))
    return response.json()


def get_json(path: str) -> Any:
    return _call("GET", path)


def post_json(path: str, body: dict | None = None, timeout: float = 120) -> Any:
    return _call("POST", path, body, timeout)


def fmt_money(value: Any, lang: str, currency: str = "USD") -> str:
    """4012.65 -> '4.012,65 USD' in German, '4,012.65 USD' in English."""
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}"
    if lang == "de":
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} {currency}"


def fmt_time(value: str | None, lang: str) -> str:
    """'2026-10-21 14:03:05.7' -> '21.10.2026 14:03 UTC' (DE) or '2026-10-21 14:03 UTC' (EN)."""
    if not value:
        return "-"
    moment = datetime.fromisoformat(str(value))
    pattern = "%d.%m.%Y %H:%M" if lang == "de" else "%Y-%m-%d %H:%M"
    return f"{moment.strftime(pattern)} UTC"


TEXT: dict[str, dict[str, str]] = {
    "de": {
        "title": "SAP O2C Assistent",
        "subtitle": "Order-to-Cash Fragen an SAP S/4HANA Daten, auf Deutsch oder Englisch.",
        "page_chat": "Chat",
        "page_dashboard": "Dashboard",
        "language": "Sprache",
        "data_from": "Datenstand",
        "source_api": "SAP Sandbox API",
        "source_fixtures": "Fixtures (Offline-Modus)",
        "refresh": "Daten neu laden",
        "refreshed": "Daten neu geladen.",
        "chat_placeholder": "Frage zu Aufträgen, Lieferungen oder Fakturen ...",
        "chat_off": "Der Chat ist gerade aus. Das Dashboard funktioniert trotzdem.",
        "thinking": "Der Assistent sucht in den SAP-Daten ...",
        "tools_used": "Verwendete Tools",
        "examples": "Beispielfragen",
        "clear_chat": "Chat leeren",
        "kpi_open_orders": "Offene Aufträge",
        "kpi_open_value": "Offener Auftragswert",
        "kpi_dnb": "Geliefert, nicht fakturiert",
        "kpi_dnb_value": "Wert geliefert, nicht fakturiert",
        "chart_revenue": "Fakturierter Umsatz pro Monat",
        "chart_top": "Top 5 Kunden nach Umsatz",
        "chart_funnel": "O2C-Trichter: Aufträge pro Schritt",
        "table_dnb": "Lieferungen mit Warenausgang, aber ohne Faktura",
        "funnel_ordered": "Bestellt",
        "funnel_delivered": "Warenausgang gebucht",
        "funnel_billed": "Fakturiert",
        "col_delivery": "Lieferung",
        "col_orders": "Aufträge",
        "col_customer": "Kunde",
        "col_gi_date": "Warenausgang",
        "col_value": "Wert",
        "col_month": "Monat",
        "col_revenue": "Umsatz",
        "col_step": "Schritt",
        "col_count": "Aufträge",
        "revenue_note": "Rechnungen und Lastschriften positiv, Gutschriften negativ. "
        "Anzahlungsanforderungen und Stornos zählen nicht.",
    },
    "en": {
        "title": "SAP O2C Assistant",
        "subtitle": "Order-to-Cash questions on SAP S/4HANA data, in German or English.",
        "page_chat": "Chat",
        "page_dashboard": "Dashboard",
        "language": "Language",
        "data_from": "Data as of",
        "source_api": "SAP sandbox API",
        "source_fixtures": "fixtures (offline mode)",
        "refresh": "Reload data",
        "refreshed": "Data reloaded.",
        "chat_placeholder": "Ask about orders, deliveries or invoices ...",
        "chat_off": "Chat is off right now. The dashboard still works.",
        "thinking": "The assistant is checking the SAP data ...",
        "tools_used": "Tools used",
        "examples": "Example questions",
        "clear_chat": "Clear chat",
        "kpi_open_orders": "Open orders",
        "kpi_open_value": "Open order value",
        "kpi_dnb": "Delivered, not billed",
        "kpi_dnb_value": "Value delivered, not billed",
        "chart_revenue": "Billed revenue per month",
        "chart_top": "Top 5 customers by revenue",
        "chart_funnel": "O2C funnel: orders per step",
        "table_dnb": "Deliveries with goods issue but no invoice",
        "funnel_ordered": "Ordered",
        "funnel_delivered": "Goods issued",
        "funnel_billed": "Billed",
        "col_delivery": "Delivery",
        "col_orders": "Orders",
        "col_customer": "Customer",
        "col_gi_date": "Goods issue",
        "col_value": "Value",
        "col_month": "Month",
        "col_revenue": "Revenue",
        "col_step": "Step",
        "col_count": "Orders",
        "revenue_note": "Invoices and debit memos count positive, credit memos negative. "
        "Down payment requests and cancellations do not count.",
    },
}

EXAMPLE_QUESTIONS: dict[str, list[str]] = {
    "de": [
        "Welche Aufträge sind geliefert, aber nicht fakturiert?",
        "Wo steht Auftrag 48?",
        "Wie hoch ist der offene Auftragswert für Domestic US Customer 1?",
        "Was bedeutet Warenausgang?",
    ],
    "en": [
        "Which orders are delivered but not billed yet?",
        "What is the status of order 48?",
        "Who are our top 5 customers by revenue?",
        "Why can a delivery stay unbilled?",
    ],
}
