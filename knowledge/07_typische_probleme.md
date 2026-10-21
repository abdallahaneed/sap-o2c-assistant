# Typische Probleme im O2C (Typical problems)

## Geliefert, aber nicht fakturiert (delivered but not billed)
Die Ware ist beim Kunden, aber es gibt keine gültige Rechnung. Typische Gründe: eine Fakturasperre am Auftrag, ein Fakturalauf (VF04), der nicht lief, ein Fehler bei Preis oder Kontenfindung oder eine stornierte Rechnung. Das Problem ist teuer, weil Umsatz und Zahlungseingang später kommen. Am Monatsende fehlt der Umsatz außerdem im Abschluss. Zuerst prüft man den Fakturavorrat und den Belegfluss der Lieferung. Danach klärt man Sperren und Fehlerprotokolle.

## Lieferung ohne Warenausgang (delivery without goods issue)
Die Lieferung ist angelegt, aber der Warenausgang fehlt. Mögliche Gründe: Die Kommissionierung ist nicht fertig, Bestand fehlt, oder der Warenausgang wurde schlicht vergessen. Für den Kunden heißt das, die Ware ist noch nicht unterwegs. Für die Abrechnung heißt das, eine lieferbezogene Faktura ist noch nicht möglich. Man klärt den Stand mit dem Lager und bucht den Warenausgang mit VL02N, sobald die Ware das Haus verlässt.

## Gesperrte Aufträge (blocked orders)
Ein Auftrag kann eine Liefersperre, eine Fakturasperre oder eine Kreditsperre haben. Liefer- und Fakturasperren setzt meist der Vertrieb bewusst, etwa bei offenen Fragen zum Preis. Kreditsperren setzt das System nach der Kreditprüfung. Man erkennt Sperren im Auftrag und in Listen wie VA05 oder dem Lieferungsvorrat. Gelöst werden sie von der Stelle, die sie gesetzt hat: Vertrieb oder Kreditmanagement.

## Daten fehlen oder passen nicht (missing or inconsistent data)
Manchmal widersprechen sich Status und Belege. Beispiel: Die Lieferung hat den Fakturastatus C, aber keine Rechnung ist sichtbar. Oder es gibt eine Rechnung zu einem Auftrag, der nicht geladen ist. Das passiert oft bei Teilextrakten, wie hier mit 1000 Zeilen pro Tabelle. Die richtige Reaktion ist, den Widerspruch zu benennen und nicht zu raten. Der Assistent sagt dann, welche Daten fehlen und wo man in SAP nachsehen kann.
