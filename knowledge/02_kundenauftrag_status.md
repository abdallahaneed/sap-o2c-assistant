# Kundenauftrag und Status (Sales order and statuses)

## Was ist ein Kundenauftrag (what is a sales order)
Der Kundenauftrag ist die verbindliche Bestellung des Kunden im Vertrieb. Er wird mit der Transaktion VA01 angelegt, mit VA02 geändert und mit VA03 angezeigt. Mit dem Auftrag sagt das Unternehmen dem Kunden eine Menge, einen Preis und einen Liefertermin zu. SAP prüft dabei die Verfügbarkeit und ermittelt den Preis über die Konditionen. Alle folgenden Belege wie Lieferung und Faktura beziehen sich auf diesen Auftrag.

## Wichtige Daten im Auftrag (key sales order data)
Ein Auftrag hat Kopfdaten und Positionsdaten. Im Kopf stehen der Auftraggeber (sold-to party), das Auftragsdatum, die Währung und der Nettowert des ganzen Auftrags. Jede Position enthält ein Material, eine Menge mit Einheit und einen eigenen Nettowert. Positionsnummern laufen meist in Zehnerschritten, also 10, 20, 30. Lieferungen und Rechnungen verweisen immer auf eine bestimmte Position, nicht nur auf den Auftrag.

## Statuswerte A, B, C (status values A, B, C)
SAP zeigt den Fortschritt eines Belegs mit drei Statuswerten. A heißt nicht bearbeitet (not yet processed). B heißt teilweise bearbeitet (partially processed). C heißt vollständig bearbeitet (completely processed). Ein leerer Status bedeutet, dass dieser Schritt für den Beleg nicht relevant ist. In diesem Projekt nutzen wir am Auftrag den Gesamtstatus (OverallSDProcessStatus) und den Lieferstatus (OverallTotalDeliveryStatus). Der Fakturastatus im Auftragskopf gilt nur für auftragsbezogene Faktura, zum Beispiel bei Dienstleistungen. Bei Ware steht der Fakturastatus an der Lieferung.

## Wann ist ein Auftrag offen (when is an order open)
In diesem Projekt gilt ein Auftrag als offen, wenn sein Gesamtstatus A oder B ist. Er ist also noch nicht vollständig geliefert und fakturiert. Der offene Auftragswert ist die Summe der Nettowerte dieser Aufträge. Der Vertrieb sieht daran, welcher Umsatz noch kommt. Die Finanzabteilung nutzt ihn für die Planung, und das Kreditmanagement rechnet offene Aufträge zum Kreditobligo des Kunden.
