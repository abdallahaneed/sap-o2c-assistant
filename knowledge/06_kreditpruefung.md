# Kreditprüfung Grundlagen (Credit check basics)

## Wozu eine Kreditprüfung (why a credit check)
Ein Unternehmen liefert auf Rechnung und trägt damit das Risiko, dass der Kunde nicht zahlt. Die Kreditprüfung begrenzt dieses Risiko. Jeder Kunde bekommt ein Kreditlimit. Dagegen steht das Kreditobligo (credit exposure): offene Forderungen, offene Aufträge, offene Lieferungen und noch nicht gebuchte Rechnungen. Überschreitet ein neuer Vorgang das Limit, greift die Prüfung.

## Wann geprüft wird (when the credit check runs)
Die Prüfung kann an mehreren Stellen laufen: beim Anlegen oder Ändern des Auftrags, bei der Lieferung oder beim Warenausgang. Welche Stelle gilt, wird im Customizing festgelegt. In S/4HANA läuft die Prüfung über SAP Credit Management. Dort pflegt man Kreditlimit und Risikoklasse am Geschäftspartner (Transaktion UKM_BP). Für den Einstieg reicht: Je früher geprüft wird, desto weniger Arbeit entsteht für einen Vorgang, der am Ende gesperrt wird.

## Was bei einer Sperre passiert (what happens with a credit block)
Fällt die Prüfung negativ aus, wird der Beleg kreditgesperrt. Ein gesperrter Auftrag lässt sich nicht beliefern, eine gesperrte Lieferung nicht ausbuchen. Ein Kreditsachbearbeiter prüft den Fall und gibt den Beleg frei oder lehnt ihn ab, zum Beispiel mit VKM1 für gesperrte SD-Belege. Der Vertriebsinnendienst sollte den Kunden informieren und klären, ob eine Zahlung offen ist. Hinweis: Die Sandbox-Daten in diesem Projekt enthalten keine Kreditsperren. Fragen dazu beantwortet der Assistent nur allgemein.
