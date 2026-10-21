# Lieferung und Warenausgang (Delivery and goods issue)

## Auslieferung anlegen (create outbound delivery)
Wenn der Liefertermin näher rückt, wird aus dem Auftrag eine Auslieferung angelegt. Das geht einzeln mit VL01N oder gesammelt über den Lieferungsvorrat mit VL10. Die Auslieferung sagt dem Lager, welches Material in welcher Menge an welchen Kunden geht. Jede Lieferposition verweist auf die Auftragsposition, aus der sie kommt (ReferenceSDDocument und ReferenceSDDocumentItem). Eine Lieferung kann Positionen aus mehreren Aufträgen desselben Kunden enthalten.

## Kommissionierung (picking)
Bei der Kommissionierung holt das Lager die Ware vom Lagerplatz und stellt sie für den Versand bereit. Mit Lagerverwaltung entsteht dafür ein Transportauftrag oder eine Lageraufgabe. Danach wird die Ware verpackt. Erst wenn die Menge kommissioniert ist, kann der Warenausgang gebucht werden.

## Warenausgang (goods issue)
Der Warenausgang (goods issue) ist der Moment, in dem die Ware das Lager verlässt. Er wird in der Lieferung mit VL02N gebucht. Dabei entsteht ein Materialbeleg, der Bestand sinkt. Gleichzeitig entsteht ein Buchhaltungsbeleg: Das Bestandskonto wird entlastet, das Konto für Bestandsveränderung oder Herstellkosten des Umsatzes wird belastet. Bewertet wird mit dem Preis aus dem Materialstamm. Für die Ware gilt: Erst nach dem Warenausgang kann die lieferbezogene Faktura erstellt werden.

## Status der Lieferung (delivery status)
Die Lieferung hat einen eigenen Warenbewegungsstatus (OverallGoodsMovementStatus). C bedeutet, der Warenausgang ist vollständig gebucht. A bedeutet, er fehlt noch. Dazu kommt der Fakturastatus der Lieferung (OverallDelivReltdBillgStatus). Er zeigt, ob die Lieferung schon abgerechnet ist. Bei Ware steht der Fakturastatus an der Lieferung und nicht am Auftragskopf, weil die Rechnung aus der Lieferung entsteht. Deshalb nutzt dieses Projekt den Lieferstatus, um gelieferte, aber nicht fakturierte Vorgänge zu finden.
