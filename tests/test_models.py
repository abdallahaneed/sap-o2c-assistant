"""Tests for parsing raw SAP rows with pydantic."""

from datetime import date
from decimal import Decimal

import pytest
from sample_data import RAW

from o2c.models import (
    BusinessPartner,
    DeliveryItem,
    SalesOrder,
    parse_item_no,
    parse_sap_date,
)


def test_sap_date_becomes_python_date():
    assert parse_sap_date("/Date(1471392000000)/") == date(2016, 8, 17)
    assert parse_sap_date("/Date(1471392000000+0000)/") == date(2016, 8, 17)
    assert parse_sap_date(None) is None


def test_bad_date_is_rejected():
    with pytest.raises(ValueError):
        parse_sap_date("2016-08-17")


def test_item_numbers_are_normalized():
    # Delivery uses "000010", billing uses "10". Both must match the same order item.
    assert parse_item_no("000010") == parse_item_no("10") == 10


def test_sales_order_fields():
    order = SalesOrder.model_validate(RAW["sales_order"][0])
    assert order.id == "1"
    assert order.net_amount == Decimal("52.65")  # exact, not 52.6499999
    assert order.order_billing_status is None  # "" became None


def test_delivery_item_links_to_order():
    item = DeliveryItem.model_validate(RAW["delivery_item"][0])
    assert (item.order_id, item.order_item_no) == ("1", 10)


def test_partner_takes_first_address_or_none():
    with_address = BusinessPartner.model_validate(RAW["business_partner"][0])
    without = BusinessPartner.model_validate(RAW["business_partner"][1])
    assert (with_address.country, with_address.city) == ("DE", "Berlin")
    assert (without.country, without.city) == (None, None)


def test_select_list_comes_from_aliases():
    assert "OverallTotalDeliveryStatus" in SalesOrder.sap_fields()
