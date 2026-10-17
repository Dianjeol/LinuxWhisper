# LinuxWhisper

Diktieren unter Omarchy: **Rechtes Alt/AltGr halten, sprechen, loslassen.** Der vollständige Text wird am Cursor eingefügt und von der vorhandenen Clipboard-History erfasst.

Nutzt Deepgram Flux Multilingual, standardmäßig auf Deutsch am EU-Endpunkt. Trotz des Namens kein lokales Whisper-Modell.

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

`./run` nutzt `DEEPGRAM_API_KEY`; fehlt die Variable, lädt der Launcher die interaktive Bash mit `~/.bashrc`. Eine `.env`-Datei wird nicht geladen. API-Keys niemals committen.

## Nutzung

Auf **BEREIT** warten, ein Textfeld fokussieren und diktieren. Mikrofon und Verbindung sind dann vorbereitet. **Strg+C** beendet; nur eine Instanz gleichzeitig starten. Es werden keine Bindings, Autostarts oder Dienste eingerichtet.

- AltGr bleibt für andere Apps sichtbar: Auch AltGr-Tastenkombinationen starten eine Aufnahme. Linkes Alt nicht.
- Einfügen erfolgt einmal: `Strg+V` in Apps, `Umschalt+Einfügen` in Fenstern mit Omarchys `terminal`-Tag. Kein zusätzliches Enter, kein Fokuswechsel.
- Während des Abschlusses im gewünschten Textfeld bleiben. Gesperrte Flächen und abweichende Paste-Kürzel werden nicht universell unterstützt; Terminale behandeln Zeilenumbrüche gemäß ihrer Konfiguration.
- Clipboard-History öffnen: **Super+Strg+V**. Die App nutzt den bestehenden Omarchy-Watcher, keine eigene History.

```bash
./run --once                 # Ein Diktat, dann beenden
./run --help                 # Alle Optionen, etwa Sprache, Region und Logpfad
.venv/bin/python -m sounddevice  # Audiogeräte auflisten
```

## Daten und Latenz

Das Mikrofon bleibt geöffnet; Audio außerhalb der gehaltenen Taste wird lokal verworfen. Während des Diktats wird Audio an Deepgram übertragen, aber von der App nicht als Datei gespeichert. Der Text ersetzt die Zwischenablage und bleibt in der lokalen Clipboard-History erhalten.

Pro erfolgreichem, nichtleerem Diktat wird eine Zahl in Millisekunden geschrieben:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/sound/latency.log
```

Gemessen wird **Alt loslassen → Einfügebefehl von Hyprland bestätigt**: einschließlich Audiorest, vollständigem Decoder-Abschluss mit `CloseStream` und Clipboard-Übergabe. Das bestätigt weder die Verarbeitung noch die sichtbare Darstellung durch die Zielanwendung; die spätere History-Speicherung gehört ebenfalls nicht zur Messung.

Log-Schreiben und Terminalausgabe erfolgen erst danach. Das Log enthält weder Audio noch Transkripte oder API-Keys. Stille und fehlgeschlagene Übergaben erzeugen keinen Erfolgswert; ein späterer Logfehler kann trotz bereits eingefügtem Text auftreten. Entwicklungsregeln: [AGENTS.md](AGENTS.md).

## Prüfstand

Bisher lokal dokumentiert: echte Deepgram-Transkription mit vollständigem Satzende, Unicode und Cursor-Selektion im GUI-Textfeld, Terminal-Paste, Clipboard-History, Stille, Übergabefehler und samplegenaue Alt-Grenzen. Physische Alt-Tastendrücke wurden nicht automatisiert.

Für diese Veröffentlichungsvorbereitung geprüft: isolierte Python-3.14-Installation, `pip check`, `./run --help` und Bash-Syntax. Git-Staging in einer temporären Kopie schließt Umgebung, Schlüsseldateien, Audio, Logs und Bytecode aus; ein Muster-Scan nach Zugangsdaten blieb ohne Fund.

Aufnahme- und Einfügecode bleiben unverändert; GUI-Diktate wurden dafür nicht erneut geprüft. Ein kontrollierter Vorher-/Nachher-Latenzvergleich liegt nicht vor; keine behauptete Beschleunigung.

## Lizenz

[MIT](LICENSE).
