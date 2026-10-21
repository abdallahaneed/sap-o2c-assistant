"""Sync job: load O2C data from SAP (or from fixtures) into SQLite.

With SAP_API_KEY set: call the sandbox, save every response as a fixture, load the DB.
Without a key: mock mode, load the DB from data/fixtures. Same code path after that.
Run: uv run python -m o2c.sync          (add --fixtures to force mock mode)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from o2c import db, models
from o2c.sap_client import (
    DEFAULT_BASE_URL,
    FIXTURE_DIR,
    PROJECT_ROOT,
    SapClient,
    load_fixture,
    save_fixture,
)


@dataclass
class EntitySpec:
    """Where one table comes from in SAP and how to parse and store it."""

    name: str  # table name, also the fixture file name
    service: str
    entity_set: str
    model: type[models.SapModel]
    row: type[db.Base]
    orderby: str  # stable sort so paging does not skip or repeat rows


SPECS = [
    EntitySpec("sales_order", "API_SALES_ORDER_SRV", "A_SalesOrder",
               models.SalesOrder, db.SalesOrderRow, "SalesOrder"),
    EntitySpec("sales_order_item", "API_SALES_ORDER_SRV", "A_SalesOrderItem",
               models.SalesOrderItem, db.SalesOrderItemRow, "SalesOrder,SalesOrderItem"),
    EntitySpec("outbound_delivery", "API_OUTBOUND_DELIVERY_SRV", "A_OutbDeliveryHeader",
               models.OutboundDelivery, db.OutboundDeliveryRow, "DeliveryDocument"),
    EntitySpec("delivery_item", "API_OUTBOUND_DELIVERY_SRV", "A_OutbDeliveryItem",
               models.DeliveryItem, db.DeliveryItemRow, "DeliveryDocument,DeliveryDocumentItem"),
    EntitySpec("billing_document", "API_BILLING_DOCUMENT_SRV", "A_BillingDocument",
               models.BillingDocument, db.BillingDocumentRow, "BillingDocument"),
    EntitySpec("billing_item", "API_BILLING_DOCUMENT_SRV", "A_BillingDocumentItem",
               models.BillingItem, db.BillingItemRow, "BillingDocument,BillingDocumentItem"),
]  # fmt: skip

PARTNER_SPEC = EntitySpec(
    "business_partner", "API_BUSINESS_PARTNER", "A_BusinessPartner",
    models.BusinessPartner, db.BusinessPartnerRow, "Customer",
)  # fmt: skip

# Child table -> (field pointing to parent, parent table). Used to drop orphans.
PARENTS = {
    "sales_order_item": ("order_id", "sales_order"),
    "delivery_item": ("delivery_id", "outbound_delivery"),
    "billing_item": ("billing_id", "billing_document"),
}


def fetch_partners(client: SapClient, customer_ids: list[str]) -> list[dict[str, Any]]:
    """Load only the customers our documents use, 15 per call via $filter."""
    rows: list[dict[str, Any]] = []
    for start in range(0, len(customer_ids), 15):
        batch = customer_ids[start : start + 15]
        odata_filter = " or ".join(f"Customer eq '{cid}'" for cid in batch)
        rows += client.get_all(
            PARTNER_SPEC.service,
            PARTNER_SPEC.entity_set,
            select=models.BusinessPartner.sap_fields(),
            expand=["to_BusinessPartnerAddress"],
            filter=odata_filter,
            orderby=PARTNER_SPEC.orderby,
        )
    return rows


def collect_raw(client: SapClient | None, fixture_dir: Path, max_rows: int) -> dict[str, list]:
    """Get raw SAP rows per table, from the API (and save fixtures) or from fixtures."""
    raw: dict[str, list] = {}
    for spec in SPECS:
        if client:
            raw[spec.name] = client.get_all(
                spec.service, spec.entity_set, select=spec.model.sap_fields(),
                orderby=spec.orderby, max_rows=max_rows,
            )  # fmt: skip
            save_fixture(spec.name, raw[spec.name], folder=fixture_dir)
        else:
            raw[spec.name] = load_fixture(spec.name, folder=fixture_dir)

    if client:
        ids = {r["SoldToParty"] for t in ("sales_order", "outbound_delivery", "billing_document")
               for r in raw[t]}  # fmt: skip
        raw["business_partner"] = fetch_partners(client, sorted(ids))
        save_fixture("business_partner", raw["business_partner"], folder=fixture_dir)
    else:
        raw["business_partner"] = load_fixture("business_partner", folder=fixture_dir)
    return raw


def parse(raw: dict[str, list]) -> dict[str, list[models.SapModel]]:
    """Validate raw rows with pydantic and drop items whose header was not loaded."""
    parsed = {
        spec.name: [spec.model.model_validate(r) for r in raw[spec.name]]
        for spec in [*SPECS, PARTNER_SPEC]
    }
    for child, (field, parent) in PARENTS.items():
        parent_ids = {p.id for p in parsed[parent]}
        kept = [c for c in parsed[child] if getattr(c, field) in parent_ids]
        dropped = len(parsed[child]) - len(kept)
        if dropped:
            # Happens when max_rows cuts headers but not their items
            print(f"  note: dropped {dropped} {child} rows without a loaded header")
        parsed[child] = kept
    return parsed


def load(engine: Engine, parsed: dict[str, list[models.SapModel]], source: str) -> None:
    """Full refresh in one transaction: delete old rows, insert new ones, write sync_log."""
    db.create_tables(engine)
    now = datetime.now(UTC).replace(tzinfo=None)
    specs = [*SPECS, PARTNER_SPEC]
    with Session(engine) as session, session.begin():
        # Children first, so no item points to a deleted header in between
        for spec in reversed(specs):
            session.execute(delete(spec.row))
        for spec in specs:
            session.add_all(spec.row(**m.model_dump()) for m in parsed[spec.name])
            session.add(db.SyncLogRow(
                run_time=now, entity=spec.name,
                rows_loaded=len(parsed[spec.name]), source=source,
            ))  # fmt: skip


def run_sync(
    api_key: str | None,
    engine: Engine,
    fixture_dir: Path = FIXTURE_DIR,
    base_url: str = DEFAULT_BASE_URL,
    max_rows: int = 1000,
) -> dict[str, int]:
    """Whole sync. Returns rows loaded per table."""
    client = SapClient(api_key, base_url) if api_key else None
    source = "api" if client else "fixtures"
    try:
        raw = collect_raw(client, fixture_dir, max_rows)
    finally:
        if client:
            client.close()
    parsed = parse(raw)
    load(engine, parsed, source)
    return {name: len(rows) for name, rows in parsed.items()}


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    force_fixtures = "--fixtures" in sys.argv
    api_key = None if force_fixtures else (os.getenv("SAP_API_KEY", "").strip() or None)
    print(f"Source: {'SAP sandbox API' if api_key else 'fixtures (mock mode)'}")
    counts = run_sync(
        api_key, db.get_engine(), base_url=os.getenv("SAP_BASE_URL", DEFAULT_BASE_URL)
    )
    for name, count in counts.items():
        print(f"  {name:<20} {count:>5} rows")
    print(f"Database: {db.DEFAULT_DB_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
