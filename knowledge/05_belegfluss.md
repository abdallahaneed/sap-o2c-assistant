# Belegfluss (Document flow)

## Was zeigt der Belegfluss (what the document flow shows)
Der Belegfluss zeigt alle Belege, die zu einem Vorgang gehören, in ihrer Reihenfolge. In VA03, VL03N oder VF03 öffnet man ihn über die Schaltfläche Belegfluss. Dort sieht man Auftrag, Lieferung, Warenausgang, Faktura und Buchhaltungsbeleg mit ihrem Status. Für die Frage "Wo steht mein Auftrag?" ist das der schnellste Weg. Man sieht sofort, welcher Schritt fehlt.

## Verknüpfung auf Positionsebene (document links on item level)
Die Belege sind über ihre Positionen verknüpft, nicht nur über die Köpfe. Eine Lieferposition verweist auf die Auftragsposition. Eine Fakturaposition verweist auf die Auftragsposition und bei Ware zusätzlich auf die Lieferung. Deshalb kann eine Lieferung Positionen aus mehreren Aufträgen enthalten. Und ein Auftrag kann in mehreren Teillieferungen und Rechnungen abgewickelt werden. Wer nur die Kopfdaten verknüpft, verliert diese Fälle.

## So liest du ihn in diesem Tool (how to read it in this tool)
Der Assistent baut den Belegfluss aus den geladenen SAP-Daten nach. Pro Auftragsposition zeigt er die Lieferung, den Warenausgangsstatus, die Rechnung und deren Datum. Daraus leitet er den erreichten O2C-Schritt ab: "ordered, no delivery yet", "delivery created, goods issue open", "goods issued, not billed", "partially billed" oder "billed". Stornierte Rechnungen zählen nicht. Steht an der Lieferung der Fakturastatus C, die Rechnung fehlt aber in den geladenen Daten, sagt der Assistent das offen. Er erfindet keine Belegnummer.
