"""Tests for the query functions, on the small story in sample_data.py.

Order 1: delivered and billed. Order 2: open, goods issue missing.
Order 3: delivered, its invoice was cancelled, so it counts as not billed.
"""

import json
from decimal import Decimal

import pytest
from sample_data import RAW

from o2c import db, queries
from o2c.sync import run_sync


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    folder = tmp_path_factory.mktemp("fixtures")
    for name, rows in RAW.items():
        (folder / f"{name}.json").write_text(json.dumps(rows))
    engine = db.get_engine(f"sqlite:///{folder / 'test.db'}")
    run_sync(None, engine, fixture_dir=folder)
    yield engine
    engine.dispose()


def test_find_customers_by_part_of_name(engine):
    hits = queries.find_customers(engine, "DE 2")
    assert [h["customer_id"] for h in hits] == ["17100002"]


def test_open_orders(engine):
    result = queries.get_open_orders(engine)
    assert [o["order_id"] for o in result["orders"]] == ["2"]
    assert result["total_value"] == Decimal("353.50")


def test_open_orders_for_other_customer_is_empty(engine):
    assert queries.get_open_orders(engine, customer_id="17100002")["count"] == 0


def test_delivered_not_billed(engine):
    result = queries.get_delivered_not_billed(engine)
    assert [d["delivery_id"] for d in result["deliveries"]] == ["80000001"]
    assert result["deliveries"][0]["order_ids"] == ["3"]
    assert result["total_value"] == Decimal("52.65")


def test_order_details_full_flow(engine):
    order = queries.get_order_details(engine, "1")
    assert order["customer_name"] == "Inlandskunde DE 1"
    flow = order["document_flow"][0]
    assert (flow["delivery_id"], flow["billing_id"]) == ("80000000", "90000000")
    assert order["o2c_step"] == "billed"


def test_cancelled_invoice_does_not_count_as_billed(engine):
    assert queries.get_order_details(engine, "3")["o2c_step"] == "goods issued, not billed"


def test_order_without_goods_issue(engine):
    order = queries.get_order_details(engine, "2")
    assert order["o2c_step"] == "delivery created, goods issue open"


def test_unknown_order_returns_none(engine):
    assert queries.get_order_details(engine, "does-not-exist") is None


def test_revenue_counts_credit_memo_negative_and_skips_others(engine):
    rows = queries.revenue_by_customer(engine, "2016-01-01", "2016-12-31")
    # 52.65 invoice minus 10.00 credit memo. Down payment and cancelled invoice ignored.
    assert rows == [
        {"customer_id": "17100001", "customer_name": "Inlandskunde DE 1",
         "revenue": Decimal("42.65"), "documents": 2},
    ]  # fmt: skip


def test_revenue_date_range_is_respected(engine):
    rows = queries.revenue_by_customer(engine, "2016-08-01", "2016-08-31")
    assert rows[0]["revenue"] == Decimal("52.65")  # September credit memo outside


def test_top_customers_limits_n(engine):
    assert len(queries.top_customers(engine, 1)) == 1
    assert len(queries.top_customers(engine, -5)) == 1  # odd input is clamped


def test_revenue_by_month(engine):
    assert queries.revenue_by_month(engine) == [
        {"month": "2016-08", "revenue": Decimal("52.65")},
        {"month": "2016-09", "revenue": Decimal("-10.00")},
    ]


def test_funnel(engine):
    assert queries.o2c_funnel(engine) == {"ordered": 3, "delivered": 2, "billed": 1}


def test_last_sync_shows_source(engine):
    assert queries.last_sync(engine)["source"] == "fixtures"


def test_sql_injection_attempt_is_harmless(engine):
    # Bound parameters: the input is treated as text, not as SQL
    assert queries.get_order_details(engine, "1' OR '1'='1") is None


def test_status_c_counts_as_billed_without_loaded_invoice():
    # Like order 48 in the sandbox: invoice beyond the 1000 row cap, status says billed
    flow = [
        {
            "delivery_id": "80000029",
            "goods_issue_status": "C",
            "delivery_billing_status": "C",
            "billing_id": None,
            "billing_cancelled": None,
        }
    ]
    assert queries.o2c_step(flow, "C") == "billed"


def test_order_without_items_still_counts_as_ordered(engine):
    # Funnel 'ordered' comes from sales_order, not from items
    assert queries.o2c_funnel(engine)["ordered"] == 3


def test_note_says_invoice_exists_but_is_not_loaded(engine, monkeypatch):
    flow = [
        {
            "order_item_no": 10,
            "delivery_id": "80000029",
            "goods_issue_status": "C",
            "goods_issue_date": "2016-09-14",
            "delivery_billing_status": "C",
            "billing_id": None,
            "billing_type": None,
            "billing_date": None,
            "billing_cancelled": None,
        }
    ]
    real_rows = queries._rows

    def fake_rows(engine_, sql, **params):
        return flow if "FROM document_flow" in sql else real_rows(engine_, sql, **params)

    monkeypatch.setattr(queries, "_rows", fake_rows)
    order = queries.get_order_details(engine, "1")
    assert order["o2c_step"] == "billed"
    assert "invoice exists in SAP" in order["note"]
