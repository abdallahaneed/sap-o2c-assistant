"""Small raw SAP rows, shaped like the real sandbox answers.

Story: order 1 is delivered and billed. Order 3 is delivered but not billed.
Order 2 is open, its delivery has no goods issue yet.
"""

D = "/Date(1471392000000)/"  # 2016-08-17

RAW = {
    "sales_order": [
        {"SalesOrder": "1", "SoldToParty": "17100001", "CreationDate": D,
         "TotalNetAmount": "52.65", "TransactionCurrency": "USD",
         "OverallSDProcessStatus": "C", "OverallTotalDeliveryStatus": "C",
         "OverallOrdReltdBillgStatus": ""},
        {"SalesOrder": "2", "SoldToParty": "17100001", "CreationDate": D,
         "TotalNetAmount": "353.50", "TransactionCurrency": "USD",
         "OverallSDProcessStatus": "B", "OverallTotalDeliveryStatus": "A",
         "OverallOrdReltdBillgStatus": ""},
        {"SalesOrder": "3", "SoldToParty": "17100002", "CreationDate": D,
         "TotalNetAmount": "52.65", "TransactionCurrency": "USD",
         "OverallSDProcessStatus": "C", "OverallTotalDeliveryStatus": "C",
         "OverallOrdReltdBillgStatus": ""},
    ],
    "sales_order_item": [
        {"SalesOrder": "1", "SalesOrderItem": "10", "Material": "TG11",
         "RequestedQuantity": "3", "RequestedQuantityUnit": "PC", "NetAmount": "52.65"},
        {"SalesOrder": "2", "SalesOrderItem": "10", "Material": "FG226",
         "RequestedQuantity": "10", "RequestedQuantityUnit": "PC", "NetAmount": "353.50"},
        {"SalesOrder": "3", "SalesOrderItem": "10", "Material": "TG11",
         "RequestedQuantity": "3", "RequestedQuantityUnit": "PC", "NetAmount": "52.65"},
        # Orphan: its header is not in the list, sync must drop it
        {"SalesOrder": "999", "SalesOrderItem": "10", "Material": "X",
         "RequestedQuantity": "1", "RequestedQuantityUnit": "PC", "NetAmount": "1.00"},
    ],
    "outbound_delivery": [
        {"DeliveryDocument": "80000000", "SoldToParty": "17100001", "CreationDate": D,
         "ActualGoodsMovementDate": D, "OverallGoodsMovementStatus": "C",
         "OverallDelivReltdBillgStatus": "C"},
        {"DeliveryDocument": "80000001", "SoldToParty": "17100002", "CreationDate": D,
         "ActualGoodsMovementDate": D, "OverallGoodsMovementStatus": "C",
         "OverallDelivReltdBillgStatus": "A"},
        {"DeliveryDocument": "80000002", "SoldToParty": "17100001", "CreationDate": D,
         "ActualGoodsMovementDate": None, "OverallGoodsMovementStatus": "A",
         "OverallDelivReltdBillgStatus": "A"},
    ],
    "delivery_item": [
        {"DeliveryDocument": "80000000", "DeliveryDocumentItem": "000010",
         "ReferenceSDDocument": "1", "ReferenceSDDocumentItem": "000010", "Material": "TG11",
         "ActualDeliveryQuantity": "3.000", "DeliveryQuantityUnit": "PC"},
        {"DeliveryDocument": "80000001", "DeliveryDocumentItem": "000010",
         "ReferenceSDDocument": "3", "ReferenceSDDocumentItem": "000010", "Material": "TG11",
         "ActualDeliveryQuantity": "3.000", "DeliveryQuantityUnit": "PC"},
        {"DeliveryDocument": "80000002", "DeliveryDocumentItem": "000010",
         "ReferenceSDDocument": "2", "ReferenceSDDocumentItem": "000010", "Material": "FG226",
         "ActualDeliveryQuantity": "0.000", "DeliveryQuantityUnit": "PC"},
    ],
    "billing_document": [
        {"BillingDocument": "90000000", "BillingDocumentType": "F2", "SoldToParty": "17100001",
         "BillingDocumentDate": D, "TotalNetAmount": "52.65", "TransactionCurrency": "USD",
         "BillingDocumentIsCancelled": False, "AccountingPostingStatus": "C"},
    ],
    "billing_item": [
        {"BillingDocument": "90000000", "BillingDocumentItem": "10", "SalesDocument": "1",
         "SalesDocumentItem": "10", "ReferenceSDDocument": "80000000", "Material": "TG11",
         "NetAmount": "52.65"},
    ],
    "business_partner": [
        {"Customer": "17100001", "BusinessPartnerFullName": "Inlandskunde DE 1",
         "to_BusinessPartnerAddress": {"results": [{"Country": "DE", "CityName": "Berlin"}]}},
        {"Customer": "17100002", "BusinessPartnerFullName": "Inlandskunde DE 2",
         "to_BusinessPartnerAddress": {"results": []}},
    ],
}  # fmt: skip
