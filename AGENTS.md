# Projekt: latenzarme Diktierapp für Omarchy

## Oberstes Ziel

Nach dem Loslassen von rechtem Alt/AltGr muss der vollständige Text so schnell wie möglich am Cursor der fokussierten Anwendung eingefügt werden und in der vorhandenen Omarchy-Clipboard-History stehen. Korrekte, vollständige Transkription bleibt Voraussetzung; Text abschneiden ist keine Optimierung.

Die einzige dauerhaft protokollierte Kennzahl ist **Alt loslassen → Einfügebefehl von Hyprland bestätigt**, in Millisekunden, ein Wert pro erfolgreichem Diktat. Sie umfasst Decoder-Abschluss, Clipboard-Übergabe und Paste-Befehl. Hyprland bestätigt nicht die Textverarbeitung oder sichtbare Darstellung durch eine beliebige Zielanwendung. Diesen Proxy niemals als gemessenen Pixelzeitpunkt ausgeben oder die Messgrenze vorverlegen, um bessere Zahlen zu erzeugen.

## Verbindliche Performance-Regeln

- Keine Änderung darf diese Latenz absichtlich verschlechtern. Neue Funktionen gehören außerhalb des kritischen Pfads. Bei einem unvermeidlichen Zielkonflikt zuerst den Nutzer entscheiden lassen.
- Kritischer Pfad: letzte Audioframes → vollständiger Decoder-Abschluss → Clipboard bereit → Paste bestätigt. Davor keine Log-/History-Dateischreibzugriffe, Terminalausgaben, Benachrichtigungen, Textnachbearbeitungsdienste oder zusätzlichen Netzwerkanfragen.
- Keine pauschalen Sleeps, künstlichen Tastaturverzögerungen, Zeichen-für-Zeichen-Eingabe, Fokuswechsel oder App-Starts zum Einfügen. Auf tatsächliche Protokollantworten warten, nicht auf geschätzte Bereitschaftszeiten.
- Mikrofon und WebSocket vor `BEREIT` vorbereiten. Während Alt streamen; nicht erst nach dem Loslassen hochladen. Audio außerhalb der Taste lokal verwerfen.
- `CloseStream` verarbeitet den Audiorest. Nicht durch `ForceEndTurn` ersetzen: Eine schnelle Bestätigung des letzten Zwischenstands ist kein vollständiges Transkript.
- Nur einen Paste-Vorgang pro Diktat. Clipboard-History vom bestehenden Omarchy-Watcher erfassen lassen; keine eigene History-Datenbank und keine konkurrierenden Schreibzugriffe auf Omarchys History-Datei.
- Im Audio-/Streamingpfad keine VAD-, Wortzeitstempel- oder Nebenmetrik-Auswertung ohne konkreten, vom Nutzer freigegebenen Bedarf. Keine neuen Bibliotheken oder Dienste ohne nachweislichen Nutzen für das Ziel.
- Den Messwert erst nach der Paste-Bestätigung schreiben. Keine Audioframes, API-Keys oder Transkripte ins Performance-Log. Stille und fehlgeschlagene Übergaben ergeben keinen erfolgreichen Messwert.

## Arbeitsweise und Nachweis

- Bestehende Muster in `bench.py` und `desktop.py` weiterverwenden; kleine, direkte Implementierung statt zusätzlicher Frameworks.
- Änderungen am kritischen Pfad vor/nachher unter vergleichbaren Bedingungen mit mehreren echten Diktaten prüfen. Median und p95 der einen Kennzahl vergleichen; Netzwerkstreuung nicht als Verbesserung verkaufen. Ohne Vergleich keine behauptete Beschleunigung oder Regressionsfreiheit.
- Tatsächliches Einfügen in GUI-Textfeld und Terminal sowie Aufnahme in die vorhandene Clipboard-History praktisch prüfen. Unicode, Cursorposition, Stille und Fehler berücksichtigen. Keine Tests, die nur Quelltext oder interne Verdrahtung bestätigen.
- Vollständigkeit des letzten Wortes und samplegenaue Alt-Grenzen bewahren. Audioverlust macht den Durchlauf ungültig.
- Keine dauerhaften Hyprland-Bindings, Autostarts, Dienste oder Desktop-Konfigurationsänderungen ohne Auftrag. Installierte Omarchy-Dateien unter `/usr/share/omarchy` nur lesen.
- Verhaltensänderungen und tatsächlich ausgeführte Prüfungen in `README.md` dokumentieren. Einschränkungen offen benennen: Nicht jede Anwendung unterstützt dieselben Paste-Kürzel; eine nicht editierbare oder gesperrte Oberfläche ist kein Eingabefeld.
