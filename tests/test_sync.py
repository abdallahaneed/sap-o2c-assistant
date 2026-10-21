"""Tests for the sync job. Mock mode reads fixtures, API mode uses a fake SAP."""

import json

import httpx
import pytest
from sample_data import RAW
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from o2c import db
from o2c.sap_client import SapClient
from o2c.sync import collect_raw, run_sync


@pytest.fixture
def fixture_dir(tmp_path):
    folder = tmp_path / "fixtures"
    folder.mkdir()
    for name, rows in RAW.items():
        (folder / f"{name}.json").write_text(json.dumps(rows))
    return folder


@pytest.fixture
def engine(tmp_path):
    engine = db.get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    yield engine
    engine.dispose()  # close SQLite connections after each test


def count(engine, row):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(row))


def test_mock_mode_loads_all_tables(engine, fixture_dir):
    counts = run_sync(None, engine, fixture_dir=fixture_dir)

    assert counts["sales_order"] == 3
    assert counts["sales_order_item"] == 3  # orphan for order 999 dropped
    assert count(engine, db.OutboundDeliveryRow) == 3
    assert count(engine, db.BillingItemRow) == 1
    assert count(engine, db.BusinessPartnerRow) == 2


def test_sync_log_records_source(engine, fixture_dir):
    run_sync(None, engine, fixture_dir=fixture_dir)
    with Session(engine) as s:
        sources = set(s.scalars(select(db.SyncLogRow.source)))
    assert sources == {"fixtures"}


def test_second_run_replaces_instead_of_duplicating(engine, fixture_dir):
    run_sync(None, engine, fixture_dir=fixture_dir)
    run_sync(None, engine, fixture_dir=fixture_dir)
    assert count(engine, db.SalesOrderRow) == 3


def test_money_stays_exact(engine, fixture_dir):
    run_sync(None, engine, fixture_dir=fixture_dir)
    with Session(engine) as s:
        total = s.scalar(select(func.sum(db.SalesOrderItemRow.net_amount)))
    assert str(total) == "458.80"


def test_api_mode_saves_fixtures_and_filters_partners(tmp_path):
    seen_filters = []

    def fake_sap(request):
        entity_set = request.url.path.rsplit("/", 1)[-1]
        if entity_set == "A_BusinessPartner":
            seen_filters.append(request.url.params["$filter"])
        names = {
            "A_SalesOrder": "sales_order", "A_SalesOrderItem": "sales_order_item",
            "A_OutbDeliveryHeader": "outbound_delivery", "A_OutbDeliveryItem": "delivery_item",
            "A_BillingDocument": "billing_document", "A_BillingDocumentItem": "billing_item",
            "A_BusinessPartner": "business_partner",
        }  # fmt: skip
        return httpx.Response(200, json={"d": {"results": RAW[names[entity_set]]}})

    client = SapClient("k", base_url="https://x.test", transport=httpx.MockTransport(fake_sap))
    out = tmp_path / "saved"
    raw = collect_raw(client, out, max_rows=1000)

    assert len(raw["sales_order"]) == 3
    assert (out / "billing_item.json").exists()
    # Only customers that appear in our documents are requested
    assert seen_filters == ["Customer eq '17100001' or Customer eq '17100002'"]
