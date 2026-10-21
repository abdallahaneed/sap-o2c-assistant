"""Tests for the SAP client. They use a fake transport, so no network and no API key."""

import httpx
import pytest

from o2c.sap_client import SapApiError, SapClient, load_fixture, save_fixture


def odata(rows):
    """Wrap rows the way OData V2 does: {"d": {"results": [...]}}."""
    return {"d": {"results": rows}}


def make_client(handler, **kwargs):
    return SapClient(
        "test-key",
        base_url="https://example.test/odata",
        backoff_seconds=0,  # no waiting in tests
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_sends_api_key_and_json_format():
    seen = {}

    def handler(request):
        seen["key"] = request.headers["APIKey"]
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=odata([{"SalesOrder": "1"}]))

    rows = make_client(handler).get_page(
        "API_SALES_ORDER_SRV", "A_SalesOrder", select=["SalesOrder"], top=5
    )

    assert rows == [{"SalesOrder": "1"}]
    assert seen["key"] == "test-key"
    assert seen["params"]["$format"] == "json"
    assert seen["params"]["$select"] == "SalesOrder"
    assert seen["params"]["$top"] == "5"


def test_get_all_follows_pages_until_short_page():
    def handler(request):
        skip = int(request.url.params["$skip"])
        data = [{"n": i} for i in range(skip, min(skip + 2, 5))]  # 5 rows total
        return httpx.Response(200, json=odata(data))

    rows = make_client(handler).get_all("S", "E", page_size=2)

    assert [r["n"] for r in rows] == [0, 1, 2, 3, 4]


def test_retries_on_rate_limit_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429)
        return httpx.Response(200, json=odata([]))

    assert make_client(handler).get_page("S", "E") == []
    assert calls["n"] == 3


def test_gives_up_after_max_retries():
    def handler(request):
        return httpx.Response(503)

    with pytest.raises(SapApiError):
        make_client(handler, max_retries=2).get_page("S", "E")


def test_client_error_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="Property XYZ not found")

    with pytest.raises(SapApiError, match="400"):
        make_client(handler).get_page("S", "E")
    assert calls["n"] == 1


def test_fixture_round_trip(tmp_path):
    rows = [{"SalesOrder": "1", "TotalNetAmount": "52.65"}]
    save_fixture("demo", rows, folder=tmp_path)
    assert load_fixture("demo", folder=tmp_path) == rows


def test_metadata_asks_for_xml():
    seen = {}

    def handler(request):
        seen["accept"] = request.headers["Accept"]
        return httpx.Response(200, text="<edmx:Edmx/>")

    assert make_client(handler).get_metadata("S") == "<edmx:Edmx/>"
    assert seen["accept"] == "application/xml"
