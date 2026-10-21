# Order-to-Cash Überblick (O2C overview)

## Ziel des Prozesses (purpose of the process)
Order-to-Cash beschreibt den Weg vom ersten Kundenwunsch bis zum Geld auf dem Bankkonto. Der Prozess beginnt mit einer Anfrage oder einem Auftrag und endet mit dem Zahlungseingang. Für ein Unternehmen ist diese Kette wichtig, weil hier Umsatz und Liquidität entstehen. Jede Verzögerung kostet Geld: Ware, die geliefert, aber nicht fakturiert ist, bringt noch keinen Umsatz. Eine Rechnung, die nicht bezahlt wird, bindet Kapital. Deshalb will der Vertriebsinnendienst jederzeit wissen, wo ein Auftrag gerade steht.

## Die Schritte (process steps)
Anfrage (inquiry, VA11): Der Kunde fragt nach Preis und Verfügbarkeit. Noch keine Verpflichtung.
Angebot (quotation, VA21): Das Unternehmen bietet Menge, Preis und Termin an, meist mit Gültigkeitsdatum.
Kundenauftrag (sales order, VA01): Der Kunde bestellt verbindlich. Ab hier plant SAP Material und Liefertermin.
Auslieferung (outbound delivery, VL01N): Das Lager bekommt den Auftrag, die Ware bereitzustellen.
Kommissionierung (picking): Die Ware wird aus dem Lagerplatz geholt und verpackt.
Warenausgang (goods issue, VL02N): Die Ware verlässt das Lager. Der Bestand sinkt und es entsteht eine Buchung in der Finanzbuchhaltung.
Faktura (billing, VF01 oder VF04): Die Rechnung wird erstellt und als Forderung in FI gebucht.
Zahlungseingang (incoming payment, F-28): Der Kunde zahlt, die offene Forderung wird ausgeglichen.

## Beteiligte Module (SAP modules involved)
SD (Sales and Distribution) steuert Anfrage, Angebot, Auftrag, Lieferung und Faktura. MM und die Logistik (LE, bei Lagerverwaltung auch EWM) kümmern sich um Bestand, Kommissionierung und Warenausgang. FI bucht beim Warenausgang die Bestandsveränderung und bei der Faktura die Forderung und den Umsatz. CO bekommt Kosten und Erlöse für die Ergebnisrechnung. Die wichtigste Übergabe von SD an FI passiert bei der Faktura: Ab dann ist der Vorgang eine offene Forderung in der Debitorenbuchhaltung.
