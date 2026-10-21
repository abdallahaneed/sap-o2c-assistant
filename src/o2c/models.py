"""Pydantic models that turn raw SAP OData rows into clean Python objects.

Each field has an alias with the SAP field name. Pydantic reads the SAP name
and gives us a short, readable name. It also fixes SAP formats:
dates like /Date(1471392000000)/, item numbers like "000010", empty strings.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

_SAP_DATE = re.compile(r"/Date\((-?\d+)")


def parse_sap_date(value: Any) -> date | None:
    """OData V2 sends dates as /Date(milliseconds since 1970)/."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    match = _SAP_DATE.match(str(value))
    if not match:
        raise ValueError(f"Not an SAP date: {value!r}")
    return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=UTC).date()


def empty_to_none(value: Any) -> Any:
    """SAP sends "" for an empty status. None is clearer in Python and SQL."""
    return None if value == "" else value


def parse_item_no(value: Any) -> int | None:
    """Delivery sends "000010", billing sends "10". Both become 10."""
    return None if value in (None, "") else int(value)


SapDate = Annotated[date | None, BeforeValidator(parse_sap_date)]
Status = Annotated[str | None, BeforeValidator(empty_to_none)]
ItemNo = Annotated[int | None, BeforeValidator(parse_item_no)]


class SapModel(BaseModel):
    # populate_by_name: tests may use our names; extra=ignore: skip SAP's __metadata
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @classmethod
    def sap_fields(cls) -> list[str]:
        """SAP field names for $select, taken from the aliases. One source of truth."""
        return [f.alias for f in cls.model_fields.values() if f.alias]


class BusinessPartner(SapModel):
    # Sales documents point to the customer number, so that is our key.
    # In S/4HANA it is usually equal to the business partner number, but not always.
    id: str = Field(alias="Customer")
    name: str = Field(alias="BusinessPartnerFullName")
    country: str | None = None
    city: str | None = None

    @model_validator(mode="before")
    @classmethod
    def take_first_address(cls, data: Any) -> Any:
        # The address comes from $expand=to_BusinessPartnerAddress as a nested list
        if isinstance(data, dict) and "to_BusinessPartnerAddress" in data:
            addresses = data["to_BusinessPartnerAddress"].get("results", [])
            if addresses:
                first = addresses[0]
                data = {
                    **data,
                    "country": first.get("Country") or None,
                    "city": first.get("CityName") or None,
                }
        return data

    @classmethod
    def sap_fields(cls) -> list[str]:
        return [
            "Customer",
            "BusinessPartnerFullName",
            "to_BusinessPartnerAddress/Country",
            "to_BusinessPartnerAddress/CityName",
        ]


class SalesOrder(SapModel):
    id: str = Field(alias="SalesOrder")
    customer_id: str = Field(alias="SoldToParty")
    created_on: SapDate = Field(alias="CreationDate")
    net_amount: Decimal = Field(alias="TotalNetAmount")
    currency: str = Field(alias="TransactionCurrency")
    process_status: Status = Field(alias="OverallSDProcessStatus")
    delivery_status: Status = Field(alias="OverallTotalDeliveryStatus")
    # Only for order related billing (services). Goods are billed per delivery.
    order_billing_status: Status = Field(alias="OverallOrdReltdBillgStatus")


class SalesOrderItem(SapModel):
    order_id: str = Field(alias="SalesOrder")
    item_no: ItemNo = Field(alias="SalesOrderItem")
    material: str = Field(alias="Material")
    quantity: Decimal = Field(alias="RequestedQuantity")
    unit: str = Field(alias="RequestedQuantityUnit")
    net_amount: Decimal = Field(alias="NetAmount")


class OutboundDelivery(SapModel):
    id: str = Field(alias="DeliveryDocument")
    customer_id: str = Field(alias="SoldToParty")
    created_on: SapDate = Field(alias="CreationDate")
    goods_issue_date: SapDate = Field(alias="ActualGoodsMovementDate")
    goods_issue_status: Status = Field(alias="OverallGoodsMovementStatus")
    billing_status: Status = Field(alias="OverallDelivReltdBillgStatus")


class DeliveryItem(SapModel):
    delivery_id: str = Field(alias="DeliveryDocument")
    item_no: ItemNo = Field(alias="DeliveryDocumentItem")
    order_id: Status = Field(alias="ReferenceSDDocument")
    order_item_no: ItemNo = Field(alias="ReferenceSDDocumentItem")
    material: str = Field(alias="Material")
    quantity: Decimal = Field(alias="ActualDeliveryQuantity")
    unit: str = Field(alias="DeliveryQuantityUnit")


class BillingDocument(SapModel):
    id: str = Field(alias="BillingDocument")
    doc_type: str = Field(alias="BillingDocumentType")
    customer_id: str = Field(alias="SoldToParty")
    billing_date: SapDate = Field(alias="BillingDocumentDate")
    net_amount: Decimal = Field(alias="TotalNetAmount")
    currency: str = Field(alias="TransactionCurrency")
    is_cancelled: bool = Field(alias="BillingDocumentIsCancelled")
    posting_status: Status = Field(alias="AccountingPostingStatus")


class BillingItem(SapModel):
    billing_id: str = Field(alias="BillingDocument")
    item_no: ItemNo = Field(alias="BillingDocumentItem")
    order_id: Status = Field(alias="SalesDocument")
    order_item_no: ItemNo = Field(alias="SalesDocumentItem")
    delivery_id: Status = Field(alias="ReferenceSDDocument")
    material: str = Field(alias="Material")
    net_amount: Decimal = Field(alias="NetAmount")
