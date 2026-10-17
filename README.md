# LinuxWhisper — vollständiger Text, maximal schnell am Cursor

**Performance ist das Hauptziel dieser App:** Nach dem Loslassen der Aufnahmetaste soll der vollständige Text mit möglichst wenig Wartezeit am Cursor erscheinen. Text abschneiden ist keine Optimierung.

- **Rechtes Alt/AltGr halten, sprechen, loslassen:** direkt diktieren.
- **Text markieren, F4 halten, Anweisung sprechen, loslassen:** die Agentenantwort ersetzt die Auswahl im Textfeld und liegt im Clipboard sowie in Omarchys bestehender Clipboard-History.

Beide Wege nutzen Deepgram Flux Multilingual, standardmäßig auf Deutsch am EU-Endpunkt. F4 nutzt zusätzlich [DeepSeek V4.1 Flash über OpenRouter](https://openrouter.ai/deepseek/deepseek-v4.1-flash), exakt `deepseek/deepseek-v4.1-flash`. Trotz des App-Namens kein lokales Whisper-Modell.

## Performance zuerst

- Mikrofon und Deepgram-WebSocket sind vor **BEREIT** geöffnet. Audio streamt während der gehaltenen Taste, nicht erst danach.
- `CloseStream` verarbeitet auch den Audiorest und das letzte Wort. Kein `ForceEndTurn`, kein künstliches Antwortlimit, kein Einfügen unfertiger Teilergebnisse.
- F4 liest die Auswahl und baut DNS/TCP/TLS zu OpenRouter bereits während der Aufnahme auf. Genau eine Modellanfrage folgt auf das vollständige Transkript; kein Warm-up-HTTP-Aufruf.
- [Reasoning ist deaktiviert](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens); [Provider-Routing priorisiert Latenz](https://openrouter.ai/docs/guides/routing/provider-selection#provider-sorting), nicht den niedrigsten Preis. Lange Antworten benötigen trotzdem ihre vollständige Generierungszeit.
- AltGr stellt keine OpenRouter-Anfrage und liest keine Textauswahl. Der neue Agentenpfad bleibt getrennt; keine zusätzlichen Python-Abhängigkeiten.
- Genau ein Paste, keine Sleeps, kein Zeichen-für-Zeichen-Tippen, kein Fokuswechsel. Clipboard-Bereitstellung und Fensterklassifikation laufen wie bisher gleichzeitig; keine Log-Schreibzugriffe vor der Paste-Bestätigung.


## Einrichtung

Voraussetzungen: Omarchy mit Hyprland/Wayland, Python ≥ 3.11, Mikrofon, laufende Omarchy-Clipboard-Erfassung und Leserechte auf die Tastaturgeräte unter `/dev/input/event*`. Diese Rechte ermöglichen das Mitlesen von Tastatureingaben; die App nicht mit `sudo` starten.

Im Projektverzeichnis:

```bash
sudo pacman -S --needed python python-pip base-devel linux-api-headers portaudio wl-clipboard
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Bei der [Anmeldung bei Deepgram](https://console.deepgram.com/signup) erhalten neue Konten kostenloses API-Startguthaben. Danach gelten die [Nutzungspreise](https://deepgram.com/pricing). Dort einen API-Key erstellen und in Bash für die aktuelle Sitzung setzen, ohne ihn in der Shell-History zu speichern:

```bash
read -rsp 'Deepgram API-Key: ' DEEPGRAM_API_KEY; echo
export DEEPGRAM_API_KEY
./run
```

`./run` nutzt `DEEPGRAM_API_KEY` und für F4 zusätzlich `OPENROUTER_API_KEY`. Fehlt einer der beiden Werte in der Umgebung, lädt der Launcher die interaktive Bash mit `~/.bashrc`. Dort die Schlüssel exportieren. Eine `.env`-Datei wird nicht geladen. Ohne OpenRouter-Key funktioniert AltGr weiter; F4 meldet den fehlenden Schlüssel. API-Keys niemals committen.

OpenRouter-Key erstellen: [OpenRouter Keys](https://openrouter.ai/settings/keys). Für die aktuelle Bash-Sitzung:

```bash
read -rsp 'OpenRouter API-Key: ' OPENROUTER_API_KEY; echo
export OPENROUTER_API_KEY
./run
```

## Nutzung

Auf **BEREIT** warten, ein Textfeld fokussieren und diktieren. Mikrofon und Verbindung sind dann vorbereitet. **Strg+C** beendet; nur eine Instanz gleichzeitig starten. Die App selbst richtet keine Bindings, Autostarts oder Dienste ein.

- AltGr und F4 bleiben für andere Apps sichtbar; vorhandene App-Shortcuts können reagieren. Auch AltGr-Tastenkombinationen starten eine Aufnahme. Linkes Alt nicht. Während einer Aufnahme beendet nur das Loslassen ihrer eigenen Taste die Aufnahme.
- Einfügen erfolgt einmal: `Strg+V` in Apps, `Umschalt+Einfügen` in Fenstern mit Omarchys `terminal`-Tag. Kein zusätzliches Enter, kein Fokuswechsel.
- Während des Abschlusses im gewünschten Textfeld bleiben. Gesperrte Flächen und abweichende Paste-Kürzel werden nicht universell unterstützt; Terminale behandeln Zeilenumbrüche gemäß ihrer Konfiguration.
- Clipboard-History öffnen: **Super+Strg+V**. Die App nutzt den bestehenden Omarchy-Watcher, keine eigene History.

```bash
./run --once                 # Eine AltGr- oder F4-Aufnahme, dann beenden
./run --help                 # Alle Optionen, etwa Sprache, Region und Logpfad
.venv/bin/python -m sounddevice  # Audiogeräte auflisten
```

### F4: markierten Text per Sprache bearbeiten

1. Den gewünschten Text im Zielfenster **neu markieren**.
2. **F4 halten**, beispielsweise „Schreibe diesen Text bitte freundlicher“ sagen.
3. **F4 loslassen**; Fenster, Cursor und Auswahl bis zur Antwort unverändert lassen.

Die gesprochene Anweisung und die beim Aufnahmestart gelesene Auswahl gehen gemeinsam an OpenRouter. Nur das vollständige Ergebnis wird eingefügt, ohne zusätzliche Einleitung des Agenten. Jede Aufnahme ist unabhängig; es gibt keinen Chatverlauf.

Die Auswahl wird ohne Kopier-Tastenkürzel und ohne Änderung der normalen Zwischenablage über Waylands **PRIMARY** gelesen (`wl-paste --primary`). Die Anwendung muss diese Textauswahl bereitstellen; unter anderem wurde ein natives Chromium-Textfeld geprüft. PRIMARY ist systemweit: Eine alte Auswahl aus einem anderen Fenster lässt sich damit nicht als veraltet erkennen. Deshalb immer im Zielfenster neu markieren; Apps ohne PRIMARY-Unterstützung sind für diesen F4-Weg nicht geeignet.

Eine leere/nicht lesbare Auswahl, Stille, API-Fehler oder eine unvollständige Modellantwort führen zu keinem Paste. Ohne gesprochene Anweisung wird keine Modellanfrage gestellt. Die TLS-Vorbereitung kann bereits stattgefunden haben. Bei erkanntem Wechsel des fokussierten Fensters bleibt die fertige Antwort nur im Clipboard. Ein Cursor-/Auswahlwechsel innerhalb desselben Fensters wird nicht erkannt; der Fokuscheck ist keine atomare Sperre gegen spätere Fokuswechsel.

Im Terminal wird die Antwort am Eingabecursor eingefügt; eine markierte Terminalausgabe wird dadurch nicht umgeschrieben. Zeilenumbrüche können dort Befehle auslösen — keine ausführbaren Inhalte ungeprüft erzeugen lassen.


### Optionaler Autostart

Bei einem Checkout unter `~/Work/LinuxWhisper` in `~/.config/hypr/autostart.lua` ergänzen:

```lua
o.launch_on_start(os.getenv("HOME") .. "/Work/LinuxWhisper/run")
```

Den Projektpfad gegebenenfalls anpassen. Die API-Keys müssen dauerhaft in der Umgebung oder über `~/.bashrc` verfügbar sein. Der Start erfolgt im Hintergrund beim nächsten Hyprland-Sitzungsstart, nicht bei einem Konfigurations-Reload.

## Daten und Latenz

Das Mikrofon bleibt geöffnet; Audio außerhalb der gehaltenen Taste wird lokal verworfen. Während AltGr oder F4 wird Audio an Deepgram übertragen, aber von der App nicht als Datei gespeichert. **Bei F4 werden zusätzlich die Textauswahl und das vollständige Anweisungstranskript an OpenRouter und dessen Modellprovider gesendet.** Der Deepgram-EU-Endpunkt garantiert keine EU-Verarbeitung bei OpenRouter. Keine vertraulichen Texte markieren, die nicht an diese Anbieter gehen dürfen.

Der eingefügte Text ersetzt die Zwischenablage und bleibt in der lokalen Omarchy-Clipboard-History erhalten. Die App schreibt keine eigene History und keine Transkripte, Auswahlen oder Antworten in Dateien. Der Prompt ist kein Schutzversprechen gegen manipulative Inhalte in der Auswahl.

Pro erfolgreichem, nichtleerem **AltGr-Diktat** wird eine Zahl in Millisekunden geschrieben:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/sound/latency.log
```

Gemessen wird **Alt loslassen → Einfügebefehl von Hyprland bestätigt**: einschließlich Audiorest, vollständigem Decoder-Abschluss mit `CloseStream` und Clipboard-Übergabe. Das bestätigt weder die Verarbeitung noch die sichtbare Darstellung durch die Zielanwendung; die spätere History-Speicherung gehört ebenfalls nicht zur Messung.

Log-Schreiben und Terminalausgabe erfolgen erst danach. Das Log enthält weder Audio noch Transkripte oder API-Keys. Stille und fehlgeschlagene Übergaben erzeugen keinen Erfolgswert; ein späterer Logfehler kann trotz bereits eingefügtem Text auftreten. Entwicklungsregeln: [AGENTS.md](AGENTS.md).

F4-Werte werden nicht in dieses AltGr-Log gemischt. Die zusätzliche Modellgenerierung gehört beim Agenten zur tatsächlichen Wartezeit bis zum vollständigen Einfügen; sie wird nicht durch eine vorverlegte Messgrenze verborgen.

## Prüfstand

Für die F4-Erweiterung praktisch geprüft:

- Start über `./run --once` mit echtem Mikrofon und echtem Deepgram-WebSocket bis **BEREIT**; `./run --help` und `bash -n run`.
- Deutsche Prüf-Sprachaufnahme in Echtzeit an den echten Deepgram-EU-Endpunkt gestreamt, danach echte Anfrage an das oben genannte OpenRouter-Modell. Die Aufnahme enthielt „Schreibe diesen Text bitte freundlicher.“
- Sichtbare Ersetzung einer echten Tastatur-Markierung im nativen Chromium-Textfeld, einschließlich „Grüße, Jörg“, unverändertem Text vor/nach der Auswahl und vollständigem Satzende. Auch der F4-Zweig der Hauptschleife wurde mit injizierten Tasten-/Audioereignissen ausgeführt; sein AltGr-Latenzlog blieb leer. Das GUI-Fixture stellte den Testfensterfokus her; der Produktionscode wechselt keinen Fokus.
- Die echte Modellantwort per `Umschalt+Einfügen` in einem mit Omarchys `terminal`-Tag klassifizierten Foot-Terminal eingelesen und exakt verglichen. Aufnahme in der vorhandenen Omarchy-History nur lesend bestätigt.
- Stille und fehlende PRIMARY-Auswahl mit echtem Deepgram geprüft: keine Modellanfrage, kein Paste, Clipboard unverändert. Echter OpenRouter-HTTP-401 sauber abgewiesen. Erkannter Fensterwechsel verhinderte den Paste; die Antwort blieb im Clipboard.
- Vor und nach der Änderung je drei Deepgram-Sprach-Replays mit vollständigem letzten Wort; AltGr-Abschluss und Paste-Bestätigung ausgeführt. Das sind keine physischen Diktate und kein belastbarer Nachweis von Beschleunigung oder Regressionsfreiheit. Ein kontrollierter Mikrofon-Vorher-/Nachher-Vergleich mit Median/p95 fehlt weiterhin.
- `.venv/bin/python -m unittest -v test_flow`: vier bestandene Regressionstests für samplegenaue AltGr-/F4-Grenzen trotz Loslassen der anderen Taste, Unicode/Formatierung, abgebrochene/leere Antworten und vertrauliche Fehlerantworten.

Physische AltGr-/F4-Tastendrücke und ein erneuter Sitzungsstart wurden nicht automatisiert geprüft. `pip check` meldet in der vorhandenen Umgebung ein unabhängiges fehlendes `systemd-python` für `proton-vpn-daemon`; die App führt keine neue Abhängigkeit ein.

Zuvor dokumentiert: Autostart-Startpfad über `uwsm-app` bis **BEREIT**, auch ohne geerbten API-Key; `hyprctl reload` und `hyprctl configerrors` fehlerfrei. Für F4 wurden keine Hyprland-Bindings, Autostarts oder Dienste eingerichtet oder Konfigurationsdateien verändert.

## Lizenz

[MIT](LICENSE).
