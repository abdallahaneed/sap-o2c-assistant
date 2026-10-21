"""SQLite tables for the O2C data, defined with SQLAlchemy.

Links between documents sit on item level, like in SAP:
delivery_item.order_id points to the sales order,
billing_item.order_id and billing_item.delivery_id point back to order and delivery.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from o2c.sap_client import PROJECT_ROOT

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "o2c.db"

# Money as Numeric, never float: 0.1 + 0.2 must stay 0.3
Money = Numeric(15, 2)
Qty = Numeric(13, 3)


class Base(DeclarativeBase):
    pass


class BusinessPartnerRow(Base):
    __tablename__ = "business_partner"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    country: Mapped[str | None]
    city: Mapped[str | None]


class SalesOrderRow(Base):
    __tablename__ = "sales_order"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    # No hard foreign key to business_partner: sandbox data can miss a partner
    customer_id: Mapped[str] = mapped_column(index=True)
    created_on: Mapped[date | None] = mapped_column(Date)
    net_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str]
    process_status: Mapped[str | None]
    delivery_status: Mapped[str | None]
    order_billing_status: Mapped[str | None]


class SalesOrderItemRow(Base):
    __tablename__ = "sales_order_item"
    order_id: Mapped[str] = mapped_column(ForeignKey("sales_order.id"), primary_key=True)
    item_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    material: Mapped[str]
    quantity: Mapped[Decimal] = mapped_column(Qty)
    unit: Mapped[str]
    net_amount: Mapped[Decimal] = mapped_column(Money)


class OutboundDeliveryRow(Base):
    __tablename__ = "outbound_delivery"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(index=True)
    created_on: Mapped[date | None] = mapped_column(Date)
    goods_issue_date: Mapped[date | None] = mapped_column(Date)
    goods_issue_status: Mapped[str | None]
    billing_status: Mapped[str | None]


class DeliveryItemRow(Base):
    __tablename__ = "delivery_item"
    delivery_id: Mapped[str] = mapped_column(ForeignKey("outbound_delivery.id"), primary_key=True)
    item_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str | None] = mapped_column(index=True)
    order_item_no: Mapped[int | None]
    material: Mapped[str]
    quantity: Mapped[Decimal] = mapped_column(Qty)
    unit: Mapped[str]


class BillingDocumentRow(Base):
    __tablename__ = "billing_document"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_type: Mapped[str]
    customer_id: Mapped[str] = mapped_column(index=True)
    billing_date: Mapped[date | None] = mapped_column(Date)
    net_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str]
    is_cancelled: Mapped[bool]
    posting_status: Mapped[str | None]


class BillingItemRow(Base):
    __tablename__ = "billing_item"
    billing_id: Mapped[str] = mapped_column(ForeignKey("billing_document.id"), primary_key=True)
    item_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str | None] = mapped_column(index=True)
    order_item_no: Mapped[int | None]
    # For goods this is the delivery. For order related billing it is the order.
    delivery_id: Mapped[str | None] = mapped_column(index=True)
    material: Mapped[str]
    net_amount: Mapped[Decimal] = mapped_column(Money)


class SyncLogRow(Base):
    __tablename__ = "sync_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_time: Mapped[datetime] = mapped_column(DateTime)
    entity: Mapped[str]
    rows_loaded: Mapped[int]
    source: Mapped[str]  # "api" or "fixtures"


def get_engine(db_url: str | None = None) -> Engine:
    """Create the engine. DB_URL in .env can point elsewhere, default is data/o2c.db."""
    url = db_url or os.getenv("DB_URL") or f"sqlite:///{DEFAULT_DB_PATH}"
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url)


def create_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)
