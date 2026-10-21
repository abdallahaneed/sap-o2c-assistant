# Faktura und Integration mit FI (Billing and FI integration)

## Faktura (billing document, invoice)
Die Faktura ist der Abrechnungsbeleg an den Kunden. Sie wird einzeln mit VF01 erstellt oder gesammelt über den Fakturavorrat mit VF04. Bei Ware ist die Faktura lieferbezogen: Sie entsteht aus der Lieferung, nachdem der Warenausgang gebucht ist. Bei Dienstleistungen ohne Lieferung ist sie auftragsbezogen und entsteht direkt aus dem Auftrag. Jede Fakturaposition verweist auf die Auftragsposition und, bei Ware, auf die Lieferung.

## Fakturaarten (billing types)
F2 ist die normale Rechnung. G2 ist eine Gutschrift (credit memo) und mindert den Umsatz. L2 ist eine Lastschrift (debit memo) und erhöht ihn, etwa bei nachträglichen Kosten. FAZ ist eine Anzahlungsanforderung (down payment request). Sie fordert Geld an, ist aber noch kein Umsatz. S1 storniert eine Rechnung, S2 storniert eine Gutschrift. In diesem Projekt zählt der Umsatz so: F2 und L2 positiv, G2 negativ. FAZ, Stornobelege und stornierte Rechnungen zählen nicht.

## Buchung in FI (accounting posting in FI)
Mit der Faktura entsteht automatisch ein Buchhaltungsbeleg in FI. Der Debitor wird mit dem Bruttobetrag belastet, es entsteht also eine offene Forderung. Gutgeschrieben werden das Erlöskonto mit dem Nettobetrag und das Steuerkonto mit der Umsatzsteuer. Welches Erlöskonto genutzt wird, steuert die Erlöskontenfindung (VKOA). Der Buchungsstatus der Faktura (AccountingPostingStatus) zeigt, ob die Übergabe an FI geklappt hat. C heißt gebucht.

## Storno (cancellation)
Eine falsche Rechnung wird nicht gelöscht, sondern storniert, zum Beispiel mit VF11. Dabei entsteht ein Stornobeleg, der die Buchung in FI umkehrt. Die ursprüngliche Rechnung wird als storniert markiert (BillingDocumentIsCancelled). Danach ist die Lieferung wieder offen zur Fakturierung. Eine stornierte Rechnung darf deshalb nicht als abgerechnet zählen, sonst wäre der Umsatz zu hoch und offene Lieferungen würden übersehen.
