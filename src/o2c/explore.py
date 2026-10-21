"""One-time exploration: check which SAP services and entity sets really exist.

Downloads $metadata for each service and saves 3 sample rows per entity set.
We use the results to design models.py on facts, not guesses.
Run: uv run python -m o2c.explore
"""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv

from o2c.sap_client import (
    DEFAULT_BASE_URL,
    FIXTURE_DIR,
    METADATA_DIR,
    PROJECT_ROOT,
    SapApiError,
    SapClient,
    save_fixture,
)

# Service name -> entity sets we want to look at
TARGETS = {
    "API_SALES_ORDER_SRV": ["A_SalesOrderItem"],
    "API_BUSINESS_PARTNER": ["A_BusinessPartner", "A_Customer", "A_BusinessPartnerAddress"],
    "API_OUTBOUND_DELIVERY_SRV": ["A_OutbDeliveryHeader", "A_OutbDeliveryItem"],
    "API_BILLING_DOCUMENT_SRV": ["A_BillingDocument", "A_BillingDocumentItem"],
}


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("SAP_API_KEY", "").strip()
    if not api_key:
        print("Needs SAP_API_KEY in .env.")
        return

    client = SapClient(api_key, os.getenv("SAP_BASE_URL", DEFAULT_BASE_URL))
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    peek_dir = FIXTURE_DIR / "explore"
    try:
        for service, entities in TARGETS.items():
            print(f"\n{service}")
            try:
                xml = client.get_metadata(service)
            except SapApiError as err:
                # Keep going: one broken service should not stop the others
                print(f"  metadata FAILED: {err}")
                continue
            (METADATA_DIR / f"{service}.xml").write_text(xml, encoding="utf-8")
            sets = re.findall(r'<EntitySet Name="([^"]+)"', xml)
            print(f"  metadata ok, {len(sets)} entity sets")

            for entity in entities:
                if entity not in sets:
                    print(f"  {entity}: NOT in metadata")
                    continue
                try:
                    rows = client.get_page(service, entity, top=3)
                except SapApiError as err:
                    print(f"  {entity}: FAILED {err}")
                    continue
                save_fixture(entity, rows, folder=peek_dir)
                print(f"  {entity}: {len(rows)} sample rows saved")
    finally:
        client.close()


if __name__ == "__main__":
    main()
