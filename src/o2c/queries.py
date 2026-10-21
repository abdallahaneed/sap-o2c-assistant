"""Fixed, tested, read-only queries. The assistant may only call these.

The LLM never writes SQL. It picks a function and passes parameters.
Parameters go in as bound values (:name), never pasted into the SQL text.
Amounts come back as Decimal. All orders in the sandbox are USD.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from o2c import db
from o2c.db import get_engine

# SAP status codes on order and delivery level
STATUS_TEXT = {
    "A": "not yet processed",
    "B": "partially processed",
    "C": "completely processed",
    None: "not relevant",
}

# How each billing type counts towards revenue. Types not listed do not count:
# FAZ is a down payment request, S1/S2 cancel another document (which is flagged cancelled).
REVENUE_SIGN = {"F2": 1, "L2": 1, "G2": -1}

# SQL snippets built from REVENUE_SIGN, so the rule lives in one place.
# Only our own constants go into these strings, never user input.
_REVENUE_SQL = (
    "CASE bd.doc_type "
    + " ".join(f"WHEN '{t}' THEN {s}" for t, s in REVENUE_SIGN.items())
    + " ELSE 0 END * bd.net_amount"
)
_REVENUE_FILTER = "bd.is_cancelled = 0 AND bd.doc_type IN ({})".format(
    ", ".join(f"'{t}'" for t in REVENUE_SIGN)
)


def _rows(engine: Engine, sql: str, **params: Any) -> list[dict[str, Any]]:
    """Run a fixed SQL statement with bound parameters, return rows as dicts."""
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def _money(value: Any) -> Decimal:
    """SQLite returns sums as float. Round back to an exact 2 decimal amount."""
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def find_customers(engine: Engine, name: str) -> list[dict[str, Any]]:
    """Find customers by part of their name, so 'Kunde X' can become a customer id."""
    return _rows(
        engine,
        """SELECT id AS customer_id, name, country, city FROM business_partner
           WHERE name LIKE :pattern ORDER BY name LIMIT 10""",
        pattern=f"%{name}%",
    )


def get_open_orders(engine: Engine, customer_id: str | None = None) -> dict[str, Any]:
    """Orders not completely processed (overall status A or B), optionally for one customer."""
    rows = _rows(
        engine,
        """SELECT so.id AS order_id, so.customer_id, bp.name AS customer_name,
                  so.created_on, so.net_amount, so.currency,
                  so.process_status, so.delivery_status
           FROM sales_order so
           LEFT JOIN business_partner bp ON bp.id = so.customer_id
           WHERE so.process_status IN ('A', 'B')
             AND (:customer_id IS NULL OR so.customer_id = :customer_id)
           ORDER BY CAST(so.id AS INTEGER)""",
        customer_id=customer_id,
    )
    for r in rows:
        r["net_amount"] = _money(r["net_amount"])
        r["delivery_status_text"] = STATUS_TEXT.get(r["delivery_status"], "unknown")
    return {
        "count": len(rows),
        "total_value": sum((r["net_amount"] for r in rows), Decimal("0.00")),
        "currency": "USD",
        "orders": rows,
    }


def get_delivered_not_billed(engine: Engine) -> dict[str, Any]:
    """Deliveries with goods issue done but billing open. Value from the referenced order items."""
    rows = _rows(
        engine,
        """SELECT od.id AS delivery_id, od.customer_id, bp.name AS customer_name,
                  od.goods_issue_date, od.billing_status,
                  GROUP_CONCAT(DISTINCT di.order_id) AS order_ids,
                  SUM(soi.net_amount) AS value
           FROM outbound_delivery od
           JOIN delivery_item di ON di.delivery_id = od.id
           LEFT JOIN sales_order_item soi
               ON soi.order_id = di.order_id AND soi.item_no = di.order_item_no
           LEFT JOIN business_partner bp ON bp.id = od.customer_id
           WHERE od.goods_issue_status = 'C' AND od.billing_status IN ('A', 'B')
           GROUP BY od.id
           ORDER BY od.id""",
    )
    for r in rows:
        r["order_ids"] = sorted((r["order_ids"] or "").split(","), key=lambda x: (len(x), x))
        r["value"] = _money(r["value"])
    return {
        "count": len(rows),
        "total_value": sum((r["value"] for r in rows), Decimal("0.00")),
        "currency": "USD",
        "deliveries": rows,
    }


def o2c_step(flow: list[dict[str, Any]], process_status: str | None) -> str:
    """Name the furthest O2C step an order has reached, from its document flow rows.

    Billed means: a valid invoice is in our data, or SAP's delivery billing status is C.
    The status matters because the invoice can sit outside the rows we loaded.
    """
    has_invoice = any(f["billing_id"] and not f["billing_cancelled"] for f in flow)
    status_billed = any(f["delivery_billing_status"] == "C" for f in flow)
    if has_invoice or status_billed:
        return "billed" if process_status == "C" else "partially billed"
    if any(f["goods_issue_status"] == "C" for f in flow):
        return "goods issued, not billed"
    if any(f["delivery_id"] for f in flow):
        return "delivery created, goods issue open"
    return "ordered, no delivery yet"


def get_order_details(engine: Engine, order_id: str) -> dict[str, Any] | None:
    """One order with items, customer and full document flow. None if the order is unknown."""
    header = _rows(
        engine,
        """SELECT so.*, bp.name AS customer_name, bp.country, bp.city
           FROM sales_order so LEFT JOIN business_partner bp ON bp.id = so.customer_id
           WHERE so.id = :order_id""",
        order_id=order_id,
    )
    if not header:
        return None
    order = header[0]
    order["net_amount"] = _money(order["net_amount"])
    order["items"] = _rows(
        engine,
        """SELECT item_no, material, quantity, unit, net_amount
           FROM sales_order_item WHERE order_id = :order_id ORDER BY item_no""",
        order_id=order_id,
    )
    for item in order["items"]:
        item["net_amount"] = _money(item["net_amount"])
    order["document_flow"] = _rows(
        engine,
        """SELECT order_item_no, delivery_id, goods_issue_status, goods_issue_date,
                  delivery_billing_status, billing_id, billing_type, billing_date,
                  billing_cancelled
           FROM document_flow WHERE order_id = :order_id
           ORDER BY order_item_no, delivery_id, billing_id""",
        order_id=order_id,
    )
    order["o2c_step"] = o2c_step(order["document_flow"], order["process_status"])
    flow = order["document_flow"]
    if any(f["delivery_billing_status"] == "C" for f in flow) and not any(
        f["billing_id"] for f in flow
    ):
        # Tell the assistant openly, so it does not invent an invoice number
        order["note"] = (
            "SAP marks the delivery as billed, but the invoice is not in the loaded data."
        )
    return order


def revenue_by_customer(
    engine: Engine, date_from: date | str, date_to: date | str
) -> list[dict[str, Any]]:
    """Billed revenue per customer in a date range (both days included)."""
    rows = _rows(
        engine,
        f"""SELECT bd.customer_id, bp.name AS customer_name,
                   SUM({_REVENUE_SQL}) AS revenue, COUNT(*) AS documents
            FROM billing_document bd
            LEFT JOIN business_partner bp ON bp.id = bd.customer_id
            WHERE {_REVENUE_FILTER}
              AND bd.billing_date BETWEEN :date_from AND :date_to
            GROUP BY bd.customer_id
            ORDER BY revenue DESC""",
        date_from=str(date_from),
        date_to=str(date_to),
    )
    for r in rows:
        r["revenue"] = _money(r["revenue"])
    return rows


def top_customers(engine: Engine, n: int = 5) -> list[dict[str, Any]]:
    """Top n customers by billed revenue over all time."""
    n = max(1, min(int(n), 50))  # guard: the LLM may pass odd values
    rows = _rows(
        engine,
        f"""SELECT bd.customer_id, bp.name AS customer_name, SUM({_REVENUE_SQL}) AS revenue
            FROM billing_document bd
            LEFT JOIN business_partner bp ON bp.id = bd.customer_id
            WHERE {_REVENUE_FILTER}
            GROUP BY bd.customer_id
            ORDER BY revenue DESC
            LIMIT :n""",
        n=n,
    )
    for r in rows:
        r["revenue"] = _money(r["revenue"])
    return rows


# Dashboard queries (used by the KPI page, not by the LLM)


def revenue_by_month(engine: Engine) -> list[dict[str, Any]]:
    rows = _rows(
        engine,
        f"""SELECT strftime('%Y-%m', bd.billing_date) AS month, SUM({_REVENUE_SQL}) AS revenue
            FROM billing_document bd
            WHERE {_REVENUE_FILTER}
            GROUP BY month ORDER BY month""",
    )
    for r in rows:
        r["revenue"] = _money(r["revenue"])
    return rows


def o2c_funnel(engine: Engine) -> dict[str, int]:
    """How many orders reached each step: ordered, goods issued, billed."""
    row = _rows(
        engine,
        # ordered counts from sales_order: orders whose items were not loaded still count.
        # billed uses the same rule as o2c_step: valid invoice or delivery billing status C.
        """SELECT (SELECT COUNT(*) FROM sales_order) AS ordered,
                  COUNT(DISTINCT CASE WHEN goods_issue_status = 'C' THEN order_id END)
                      AS delivered,
                  COUNT(DISTINCT CASE WHEN (billing_id IS NOT NULL AND billing_cancelled = 0)
                      OR delivery_billing_status = 'C' THEN order_id END) AS billed
           FROM document_flow""",
    )[0]
    return {key: int(value) for key, value in row.items()}


def last_sync(engine: Engine) -> dict[str, Any] | None:
    """Time and source of the latest data refresh, for the dashboard header."""
    rows = _rows(
        engine,
        "SELECT run_time, source FROM sync_log ORDER BY run_time DESC, id DESC LIMIT 1",
    )
    return rows[0] if rows else None


def main() -> None:
    """Quick look at the real data: uv run python -m o2c.queries"""
    engine = get_engine()
    db.create_tables(engine)  # adds the document_flow view to an existing DB
    sync = last_sync(engine)
    print(f"Data from: {sync['source']} at {sync['run_time']}")
    open_orders = get_open_orders(engine)
    print(f"Open orders: {open_orders['count']}, value {open_orders['total_value']} USD")
    dnb = get_delivered_not_billed(engine)
    print(f"Delivered not billed: {dnb['count']}, value {dnb['total_value']} USD")
    for d in dnb["deliveries"]:
        print(f"  delivery {d['delivery_id']}  orders {d['order_ids']}  {d['value']} USD")
    print("Top 5 customers:")
    for c in top_customers(engine, 5):
        print(f"  {c['customer_id']:<12} {c['customer_name']:<30} {c['revenue']:>12} USD")
    print(f"Funnel: {o2c_funnel(engine)}")
    order = get_order_details(engine, "1")
    print(f"Order 1: step '{order['o2c_step']}', flow {order['document_flow'][:1]}")


if __name__ == "__main__":
    main()
