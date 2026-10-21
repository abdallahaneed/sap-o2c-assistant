"""Read-only client for the SAP S/4HANA Cloud sandbox on the SAP Business Accelerator Hub.

The sandbox speaks OData V2 and returns JSON when we ask for $format=json.
Every call is a GET. This client never writes data to SAP.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap"

# Project root is two levels above src/o2c/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = PROJECT_ROOT / "data" / "fixtures"
METADATA_DIR = PROJECT_ROOT / "data" / "metadata"

# Status codes worth a second try: rate limit and temporary server errors
RETRY_STATUS = {429, 500, 502, 503, 504}


class SapApiError(Exception):
    """Raised when SAP returns an error we should not retry."""


class SapClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 4,
        backoff_seconds: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # The sandbox expects the key in a header called APIKey
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._http = httpx.Client(
            headers={"APIKey": api_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,  # tests pass a fake transport here
        )

    def _request(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET with retry and exponential backoff (1s, 2s, 4s, ...)."""
        for attempt in range(self.max_retries + 1):
            try:
                response = self._http.get(url, params=params, headers=headers)
            except httpx.TransportError:
                # Network problem: retry unless we are out of attempts
                if attempt == self.max_retries:
                    raise
            else:
                if response.status_code not in RETRY_STATUS:
                    if response.is_error:
                        raise SapApiError(
                            f"SAP returned {response.status_code}: {response.text[:300]}"
                        )
                    return response
                if attempt == self.max_retries:
                    raise SapApiError(f"Gave up after {attempt + 1} tries: {response.status_code}")
            time.sleep(self.backoff_seconds * (2**attempt))
        raise SapApiError("Unreachable")  # loop always returns or raises

    def get_page(
        self,
        service: str,
        entity: str,
        select: list[str] | None = None,
        expand: list[str] | None = None,
        top: int = 50,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch one page of an entity set. OData V2 wraps rows in d.results."""
        params: dict[str, Any] = {"$format": "json", "$top": top, "$skip": skip}
        if select:
            params["$select"] = ",".join(select)
        if expand:
            params["$expand"] = ",".join(expand)
        response = self._request(f"{self.base_url}/{service}/{entity}", params)
        return response.json()["d"]["results"]

    def get_all(
        self,
        service: str,
        entity: str,
        select: list[str] | None = None,
        expand: list[str] | None = None,
        page_size: int = 50,
        max_rows: int = 500,
    ) -> list[dict[str, Any]]:
        """Page through an entity set with $top and $skip until a short page comes back."""
        rows: list[dict[str, Any]] = []
        while len(rows) < max_rows:
            page = self.get_page(service, entity, select, expand, top=page_size, skip=len(rows))
            rows.extend(page)
            if len(page) < page_size:
                break  # last page reached
        return rows[:max_rows]

    def get_metadata(self, service: str) -> str:
        """Download the $metadata XML. It lists every entity and field name of a service."""
        # $metadata is XML, so we override the default JSON Accept header here
        response = self._request(
            f"{self.base_url}/{service}/$metadata", headers={"Accept": "application/xml"}
        )
        return response.text

    def close(self) -> None:
        self._http.close()


def save_fixture(name: str, rows: list[dict[str, Any]], folder: Path = FIXTURE_DIR) -> Path:
    """Store raw API rows as pretty JSON so the app can run offline later."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_fixture(name: str, folder: Path = FIXTURE_DIR) -> list[dict[str, Any]]:
    """Read rows back from a saved fixture (used in mock mode)."""
    return json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))


# Header fields we need from A_SalesOrder. If one name is wrong, SAP answers 400.
SALES_ORDER_FIELDS = [
    "SalesOrder",
    "SalesOrderType",
    "SoldToParty",
    "CreationDate",
    "TotalNetAmount",
    "TransactionCurrency",
    "OverallSDProcessStatus",
    "OverallTotalDeliveryStatus",
    "OverallOrdReltdBillgStatus",
]


def main() -> None:
    """Milestone 1 check: fetch a few sales orders and save them as a fixture."""
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("SAP_API_KEY", "").strip()
    if not api_key:
        if not (FIXTURE_DIR / "sales_orders_sample.json").exists():
            print("No SAP_API_KEY in .env and no fixture yet. Add your key first.")
            return
        rows = load_fixture("sales_orders_sample")
        print(f"No SAP_API_KEY set. Mock mode: loaded {len(rows)} orders from fixtures.")
        return

    client = SapClient(api_key, os.getenv("SAP_BASE_URL", DEFAULT_BASE_URL))
    try:
        # Save $metadata first so we can check real field names offline
        METADATA_DIR.mkdir(parents=True, exist_ok=True)
        xml = client.get_metadata("API_SALES_ORDER_SRV")
        (METADATA_DIR / "API_SALES_ORDER_SRV.xml").write_text(xml, encoding="utf-8")

        rows = client.get_page(
            "API_SALES_ORDER_SRV", "A_SalesOrder", select=SALES_ORDER_FIELDS, top=5
        )
        path = save_fixture("sales_orders_sample", rows)
    finally:
        client.close()

    print(f"Loaded {len(rows)} sales orders from the SAP sandbox.")
    for row in rows:
        print(
            f"  {row['SalesOrder']}  customer {row['SoldToParty']}  "
            f"{row['TotalNetAmount']} {row['TransactionCurrency']}  "
            f"delivery {row['OverallTotalDeliveryStatus'] or '-'}  "
            f"billing {row['OverallOrdReltdBillgStatus'] or '-'}"
        )
    print(f"Saved fixture: {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
