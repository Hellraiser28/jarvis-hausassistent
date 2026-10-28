# Änderungen

## 0.4.0 – 2026-10-28

Für die ganze Familie und für den Papierkram. *English: for the whole family and for paperwork: people with their own
memory and permissions, learning at night, scenes, a mailbox assistant, letters and deadlines, an update center, a
yes button for mishearings, and the password detected in the middle of a sentence. App 4.6.1.*

- **Personen:** Jedes Handy kann einer Person gehören, mit eigenem Gedächtnis, Verlauf, eigenen Erinnerungen und
  Rechten (Hauptperson oder Familie). Die Rechte prüft der Werkzeug-Server bei der Liste und bei jedem Aufruf,
  Zustimmungen gelten je Quelle und Person. Neues Modul `personen.py`.
- **Gedächtnis je Person:** ein Bereich „Haus“ für alle und ein eigener je Person, auf Zuruf als TXT-Liste zum
  Bearbeiten und Zurückschicken; übernommen wird erst nach einem Ja. Neues Modul `gedaechtnis.py`, mit Umzug aus dem
  alten `gedaechtnis.md`.
- **Mitlernen:** Auf Wunsch übernimmt Jarvis nachts Dauerhaftes aus den Gesprächen, nie Kennwörter, Gesundheit oder
  Mailinhalte (Sperrliste `TABU_LERNEN`, deutsch und englisch).
- **Szenen:** mehrere Aktionen mit einem Satz oder einem Knopf in der App, gespeichert erst nach einem Ja, ausgeführt
  über dieselben Werkzeuge samt Sperrliste und Testmodus. Neues Modul `szenen.py`, Endpunkt `/v1/szenen`.
- **Postfach:** IMAP nur lesend (der Gelesen-Status bleibt), verschieben ja, löschen nie, „sag Bescheid, wenn …“.
  Neues Modul `postfach.py`.
- **Briefe und Fristen:** fotografierte Briefe nach Paperless-ngx (2.x und 3.x) ins Konto der Person, Fristen mit
  Erinnerung drei Tage vorher. Neues Modul `briefe.py`.
- **Update-Zentrale** (Baustein der Bauanleitung): Container über die vorhandene Verwaltung, Home Assistant samt Core
  mit Sicherung, Betriebssystem und Firmware nur melden. Kern-Dienste nur, wenn die Person sie selbst nennt.
- **Ja-Knopf:** Bei einem vermutlichen Verhörer fragt Jarvis „Meinst du …?“, App und Web-App zeigen einen Knopf dazu.
- **Kennwort im Satz:** Das Codewort wird auch mitten im Satz erkannt. Ohne offene Freigabe wird die Nachricht
  verworfen, der Verlauf schwärzt es zusätzlich.
- **App 4.6.1:** Menü „Szenen“, Ja-Knopf, Fernzugang aus `/v1/gesund`; ein Anhang geht auch beim Sprechen und beim
  Ja-Knopf mit. Web-App-Schicht mit denselben Funktionen.
- **Zweisprachig:** Gedächtnis-Liste und Szenen im App-Menü erscheinen in der Sprache der Einrichtung; eine
  zurückgeschickte Liste darf deutsche oder englische Abschnitte haben. Meldungen von Postfach und Briefen gehen ans
  Gehirn, das in der Sprache der Person antwortet.
- **Nach einer unabhängigen Prüfung vor dem Release:** IMAP prüft das Zertifikat des Mailservers (vorher nahm
  `imaplib` jeden Server an); eine unbekannte Person am Gerät oder eine kaputte `personen.json` heißt „keine
  Rechte“ statt „Hauptperson“; Szenen ändern nur die Person, die sie angelegt hat, und die Hauptperson, Löschen
  trifft nur den genauen Namen, und keine Szene übernimmt den Namen einer anderen; der Ja-Knopf zählt nie als
  Zustimmung; in den Spam-Ordner nur auf Nennung; „Vergessen“ braucht einen genauen Begriff;
  das Gedächtnis löscht nichts still, wenn es voll ist, und überschreibt beim Übernehmen nichts, was sich
  inzwischen geändert hat; offene Fristen fallen nie weg; Sperren auch unter Windows; Mitlernen nur aus den
  Nachrichten der Person und nur in ihren Bereich; keine Paperless-Werkzeuge ohne eigenes Token. Neuer Test
  `test_funde_040.py` (50).
- **Bauanleitung:** neue Bausteine mit Proben in Phase 3, dazu der Umstieg von 0.3.x unter „Später ändern“.
- Tests ohne Netz: `test_gedaechtnis.py` (53), `test_szenen.py` (27), `test_postfach.py` (27), `test_briefe.py`
  (25), `test_sprache_040.py` (31).
- **Fernzugang für die App von GitHub:** Die App lernt die https-Adresse des Fernzugangs aus der Kopplung, die
  Vorlage nannte das Feld `fernzugang` aber nur „auf Wunsch“. Ohne das Feld blieb die App unterwegs ohne Verbindung
  (Zahnrad → Verbindung: Fernzugang „–“). Jetzt Pflicht, sobald es einen Fernzugang gibt, in `/v1/koppeln` und in
  `/v1/gesund` mit gültigem Beweis; ab App 4.6 lernt eine schon gekoppelte App die Adresse daraus nach. Neuer
  Prüfpunkt im Testplan (Mobilfunk, WLAN aus). *English: the app now gets the remote access address from pairing and
  from `/v1/gesund` with a valid proof; the field is required whenever remote access exists.*

## 0.3.4 – 2026-10-26

Sicherheit nach einer unabhängigen Prüfung von 0.3.3 und nach GitHub-CodeQL. *English: security fixes after an
independent review of 0.3.3 and GitHub CodeQL.*

- **Dateien gehören dem Gerät, das gefragt hat:** Ergebnisse und Anhänge sind an Gerät und Anfrage gebunden. Abholen,
  der Verlauf in `/v1/zustand` und die Werkzeuge prüfen das; vorher konnte jedes gekoppelte Gerät die Ergebnisse aller
  anderen holen, und bei zwei Handys gleichzeitig konnte ein Ergebnis beim falschen landen. Die Brücke gibt dem
  Werkzeug-Server des Gehirns vor jeder Frage mit, wer fragt (`ablage/aktiv/<pid>.json`).
- **Schlagzeilen:** Fragen zu einer Schlagzeile lösen keine Bild- oder Umwandel-Aufträge aus.
- **Bomben und große Anfragen:** Grenze für die entpackte Summe einer PowerPoint/Word-Datei und für die Zahl der
  Folien (vorher wurden aus 41 KB 40 MB Text); PNG wird nur bis zur erwarteten Größe entpackt, Bildmaße sind bei
  allen Bildarten begrenzt; höchstens zwei große Anfragen gleichzeitig.
- **Kosten:** Der Cloudflare-Zähler reserviert vor dem Aufruf unter einer Dateisperre; für OpenAI und Gemini gibt es
  ein Tageslimit (`BILD_TAGESLIMIT_BEZAHLT`, Standard 20).
- **PC-Client 20:** Öffnet nur noch Dateien aus einer Erlaubnisliste direkt, alles andere über „Speichern unter …“;
  unter Windows mit Herkunftsmarke (Mark of the Web). Dateinamen ohne Richtungszeichen (U+202E) und Gerätenamen.
- **App 4.5 und Web-App:** „Öffnen“ nur für Bilder, PDF, Ton, Video und Text; Adressen aus Auswahl- und
  Speichern-Dialogen nur von fremden Anbietern (CodeQL); das Original muss in Größe und Name zur gewählten Datei
  passen.
- **Original und Dienste:** Das Original wird an den ersten Bytes erkannt (kein SVG); Fehlertexte der Dienste gehen
  nicht mehr ans Gehirn, Weiterleitungen werden nicht verfolgt, Zugänge werden auf ihre Form geprüft.
- **Dateiname im Kopf des Anhangs** als JSON-Zeichenkette und ohne Rahmen- oder Anführungszeichen.
- **CodeQL:** Skripte für die Content-Security-Policy werden mit einem HTML-Parser gelesen statt mit einem regulären
  Ausdruck (gleiche Prüfsummen auf allen Seiten).
- **Setup:** warnt deutlich, wenn ein Sicherheitsmodul bei einem erneuten Lauf nicht ersetzt wurde.
- Tests: `test_ausgabe.py` (30), `test_anhang.py` (54), `test_pdf.py` (23), `test_bilddienst.py` mit gleichzeitigen
  Aufträgen und ohne jede echte Netzanfrage.

## 0.3.3 – 2026-10-26

Jarvis gibt Dateien zurück: PDFs, Bilder, umgewandelte Dateien. Welche Dienste er dafür nutzt, fragt das Setup.
*English: Jarvis returns files: PDFs, images, converted files. The setup asks which services to use.*

- **PDF erstellen:** aus getipptem, gesprochenem oder fotografiertem Text, auf Wunsch mit den Fotos. Läuft auf dem
  Jarvis-Rechner ohne Zusatzpakete (`pdf.py`, A4, Überschriften, Aufzählungen, Seitenzahlen, Umlaute). Test:
  `test_pdf.py`.
- **Bilder verändern und erzeugen:** über Cloudflare Workers AI (gratis, Tageskontingent, FLUX.2 klein 4B und 9B),
  OpenAI (kostenpflichtig, `gpt-image-2.5-flare`, genau `gpt-image-2.5-sunburst`) oder Gemini (nur mit bezahltem
  Kontingent). Ein Zähler hält das Cloudflare-Kontingent ein und weicht vom genauen auf das schnelle Modell aus,
  wenn es knapp wird. Test: `test_bilddienst.py`, ohne Netz und ohne echte Schlüssel.
- **Dateien umwandeln:** über Transmute (selbst betrieben), etwa Bild nach JPG/PNG/WebP/PDF, PDF nach Word oder
  durchsuchbarem PDF/A, Office nach PDF, Audio und Video.
- **Original mitschicken:** Die Geräte bereiten Anhänge für Claude auf (Bild verkleinert, Ton 16 kHz mono). Zum
  Umwandeln geht jetzt zusätzlich das Original mit, bis 50 MB: Aus einer FLAC wird eine MP3 in voller Qualität,
  Fotos bleiben in voller Auflösung. Die Android-App streamt das Original direkt aus der Datei, PC-Client 19 und
  Web-App legen es bei. Qualitätsstufen low, medium, high (Audio 96/192/320 kbit/s), eine unbekannte Stufe meldet
  Jarvis. Test: `test_konvertieren.py`.
- **Dateien im Gespräch:** Ergebnisse kommen als Karte mit Vorschau und Öffnen, Teilen, Speichern in App 4.4 und
  Web-App, im PC-Client 18 mit Öffnen und „Speichern unter …“. Programmdateien öffnet der PC nie direkt. Abholen nur
  mit Token, mit Sandbox-Kopfzeilen; Dateien bleiben 7 Tage, dann räumt die Brücke sie weg. Test: `test_ausgabe.py`,
  `test_dateien_pc.py`.
- **Setup-Seite „Dateien und Bilder“:** Bildanbieter und Umwandler wählen, ohne Schlüssel; die legt Claude in der
  Einrichtung als Datei an. Zugänge stehen in der `.env` oder als Pfad auf eine Schlüsseldatei (`NAME_DATEI`).
- **Mitgeliefert:** Setup und Linux-Paket legen jetzt alle fertigen Brücken-Module samt Tests nach `einrichtung/`.
  `anhang.py` und `ed25519.py` nannte die Bauanleitung seit 0.3.2 „fertig im Release“, ausgeliefert wurden sie aber
  nicht.
- **NEVER.md:** Jarvis fälscht keine Menschen (keine Bilder, die echte Personen bloßstellen, sexualisieren oder ihnen
  etwas unterschieben); dazu, wohin Bilder zum Bearbeiten gehen.

## 0.3.2 – 2026-10-26

Sicherheit nach einer unabhängigen Prüfung von 0.3.1, dazu „Was Jarvis nie tut“. *English: security fixes after an
independent review of 0.3.1, plus NEVER.en.md ("What Jarvis never does").*

- **NEVER.md / NEVER.en.md:** was Jarvis nie tut, und wo die Voreinstellung „nie“ ist und sich ändern lässt. Jeder
  Punkt ist im Code oder als feste Regel der Bauanleitung erzwungen. Die Bauanleitung fragt die Voreinstellungen in
  Runde 7 ab (Kaufen, Türen, Kameras, Gedächtnis, Gefahr-Abschaltung, Haushalt), hat die Regeln im Abschnitt
  Sicherheit und prüft sie bei der Abnahme mit eigenen Proben. README verlinkt beide Fassungen.
- **PC-Client 16 und 17:** Gesprochenes am PC kommt als eigene Quelle `pc-sprache`. Per Sprache und per Echtzeit gibt es am
  PC standardmäßig keine PC-Werkzeuge mehr (Schalter `PC_PER_SPRACHE`, `PC_IN_ECHTZEIT`), weil sonst auch Ton aus den
  eigenen Lautsprechern oder ein von Gemini umformulierter fremder Text den PC steuern konnte. Brückenbeweis und
  Update-Signatur werden über Bytes verglichen (Umlaute in einer Antwort warfen vorher einen Fehler).
- **PC-Fenster:** Die Fensterfunktionen (Fragen, Echtzeit, Zahnrad, Updates) arbeiten nur noch für die eigene
  HUD-Seite. Landet das Fenster auf einer fremden Seite, etwa durch einen hineingezogenen Link, lädt es das HUD neu.
  Die Durchreiche schickt eine Content-Security-Policy (Skripte nur per Hash, Verbindungen nur zu sich selbst und
  Gemini Live). Der Brückenbeweis gilt 60 Sekunden statt 10 Minuten, ein Laptop beweist also nach jedem Umziehen
  neu. Das Symbol kommt nicht mehr ohne Token aus dem Netz. Test: `test_fenster_schutz.py`.
- **Schlagzeilen:** Fragen zu einer Schlagzeile laufen überall (PC, App, Web-App, unterwegs) unter der Quelle
  `meldung`, dort lösen Werkzeuge nichts aus. Der Titel geht als JSON-Zeichenkette mit.
- **Haupt-PC:** Die Brücke erkennt ihn am Token statt am Gerätenamen.
- **Knöpfe nur nach einem Ja:** Will Jarvis einen Knopf anlegen oder ändern, liest er Beschriftung und Auftrag vor
  und setzt ihn erst nach einem klaren Ja. Das HUD zeigt den Auftrag hinter einem Knopf beim Überfahren.
- **Dateien im Gespräch:** Bilder, PDF, Texte, Word/OpenDocument/PowerPoint und Tonaufnahmen (abgeschrieben vom Ohr)
  in App, Web-App und PC-Fenster (dort auch per Ziehen und Ablegen). Am Handy auch „Foto aufnehmen“ (App und
  Web-App am iPhone). Neu: `anhang.py` mit 36 Tests, App 4.3.
- **Fenster und Bildschirmgrößen (Client 17):** Das PC-Fenster öffnet sich maximiert, auch nach einem Start im
  Hintergrund. Das HUD zeigt in Kalender, Welt, Haus, Verbindungen und Gespräch nur ganze Einträge, statt sie
  unten anzuschneiden; bei wenig Fensterhöhe (etwa ein Laptop mit 125 % Skalierung) rückt es enger zusammen.
- **Neu in dieser Version:** App und PC-Fenster zeigen nach einem Update einmal, was neu ist (nicht nach einer
  Neuinstallation). Wer per Update kommt, muss dafür nicht auf GitHub schauen.
- **Kopplung mit Beweis:** Setup, Linux-Installer und App schicken den Kopplungscode erst, wenn die Brücke bewiesen
  hat, dass sie ihn kennt (`/v1/koppeln/beweis`, PBKDF2 mit 200000 Runden). Vorher konnte ein fremdes Gerät unter
  der Adresse den Code abgreifen und selbst ein Token ausgeben. Ältere Brücken werden dabei abgelehnt: erst die
  Brücke aktualisieren, dann Geräte koppeln.
- **Update-Signatur mit Ed25519:** über Version und Prüfsumme zusammen, mit eigenem Schlüssel der Brücke statt
  eines HMAC aus dem Token; GitHub-Updates (`pc-<Nummer>`) brauchen die Signatur des Projekts. `ed25519.py` nach
  RFC 8032 mit den Testvektoren der RFC geprüft, ebenso die Prüfkopie im Client.
- **Windows-Setup:** Die Ordnerrechte werden gesetzt, bevor Dateien und Kopplungscode hineinkommen. Scheitert das
  außerhalb des Benutzerprofils, bricht das Setup ab.
- **Prüfmodul der Oberfläche:** Format- und Richtungszeichen in Texten abgelehnt (damit ließ sich eine
  Knopf-Beschriftung tarnen), `aendern()` ändert das übergebene Objekt nicht mehr, „Rückgängig“ und „Grundeinstellung“
  behalten für Quellen ohne PC-Rechte die Knöpfe. 77 Tests.
- **Linux-Installer:** Brückenbeweis über Bytes.

## 0.3.1 – 2026-10-26

Spracherkennung, Anrufen, kleinere Korrekturen. *English: better speech recognition (Kroko), a new "phone calls"
building block, PC client 15 understands "real time", and the HUD follows the setup language.*

- **Ohr:** Für Deutsch baut die Anleitung jetzt Kroko (deutsches Streaming-Modell über sherpa-onnx, im selben Image
  `rhasspy/wyoming-whisper`) statt Whisper „base“. Gemessen auf echten Telefon-Mitschnitten: 5 von 5 Sätzen richtig
  statt 3 von 5, 1,3 bis 1,7 s je Satz statt 3 bis 4,6 s; bei 20 Kurzbefehlen 18 statt 15 richtig. Kroko erkennt mit,
  während gesprochen wird. Für Englisch dasselbe mit dem englischen Kroko-Modell: mit zwei Kunststimmen 23 von 24
  Sätzen bei 0,9 s im Mittel (Parakeet v2 23 von 24 bei 2,2 s, Whisper „base“ 19 von 24). Unter Windows ohne Docker
  bleibt es bei faster-whisper „base“.
- **Baustein „Anrufen“:** Jarvis über eine eigene Rufnummer, mit Home Assistant OS, dem Add-on HA-SIP und der
  Integration „Voice over IP“. Mit allen Fallen aus dem ersten Aufbau, darunter: `local_only: true` verwirft die
  Webhooks von HA-SIP ohne Meldung.
- **PC-Client 15:** Der Echtzeit-Befehl nimmt ein beliebiges Wort davor (den Namen, auch verhört wie „Javis“), nur
  keine Verneinung, und versteht jetzt auch Englisch („start real time“), das Version 14 trotz englischer Oberfläche
  nicht kannte. Neuer Test `vorlagen/pc/test_echtzeit_befehl.py` (36 Fälle, auch im Workflow).
- **HUD:** folgt der Sprache der Einrichtung (`sprache` im Zustand der Brücke; im PC-Fenster gibt der Client sie
  mit) statt der Browsersprache. `?sprache=` an der Adresse geht weiter vor.
- **Mac:** Das README nennt die Web-App als Weg für den Mac. Ein eigener Mac-Client folgt erst, wenn ihn jemand auf
  einem echten Mac testen kann.

## 0.3.0 – 2026-10-25

Deutsch und Englisch. *English: the setup, app 4.2, web app, HUD, PC client 14, Linux installer and all documents
now come in German and English; see README.en.md.*

- **Setup:** Sprachwahl beim Start (vorbelegt mit der Windows-Sprache), alle Seiten und die Einrichtungsskripte in
  beiden Sprachen. Die Wahl wird auch die Sprache von Jarvis. Texte in `installer/texte.nsh`, eine weitere Sprache
  braucht nur dort eine Zeile je Text.
- **App 4.2 und Web-App:** Wörterbuch Deutsch/Englisch, Sprache des Geräts oder im Zahnrad gewählt (Diese App →
  Sprache). Die Spracherkennung der App folgt der Sprache. Update-Quelle der App wählbar (`update_api`, z. B. für
  Forgejo oder Gitea).
- **HUD:** Deutsch/Englisch nach Browser bzw. Windows, `?sprache=en` für Wandbildschirme. Unveränderte deutsche
  Grundwerte der Brücke erscheinen in der englischen Fassung englisch.
- **Prüfmodule:** `oberflaeche.setze_sprache()` und `verhalten.setze_sprache()`: englische Grundwerte, Meldungen und
  Antwortstil. Standard bleibt Deutsch, mit Tests.
- **Eigener Signaturschlüssel der App** (Zertifikat-SHA-256 `98:2C:5F:E6:…:E4:36:D1`, siehe `app/README.md`). Eine
  vorher installierte Test-App mit dem alten Schlüssel muss einmal deinstalliert werden.
- **PC-Client 14:** Meldungen und Begrüßung nach `sprache` aus den Einstellungen, die Begrüßung spricht den Namen
  nach `aussprache`.
- **Zahnrad im PC-Fenster** (Wunsch aus dem Laptop-Test): Aussehen und Verhalten lassen sich dort mit zwei Klicks
  einstellen, wie in der App 4.2. Der PC-Client reicht sie an die Brücke durch, sagen geht weiter.
- **Aussprache des Namens:** neues freiwilliges Feld im Setup („So spricht man deinen Namen aus“). Sie gilt nur für
  die Stimme (eigene Stimme, Echtzeit, Begrüßung), in Texten und Anzeigen bleibt der Rufname. Idee aus dem ersten
  Laptop-Test.
- **Reste-Prüfung** (`installer/reste-pruefen.ps1`) findet jetzt auch weitere Jarvis-Ordner im Profil (etwa ein
  eigener Gehirn- oder Sicherungsordner) und Firewall-Regeln auch ohne Adminrechte (über `netsh`). Beim Rückbau des
  Laptop-Tests hätte die alte Fassung beides übersehen.
- **Stolpersteine unter Windows** in der Bauanleitung, aus dem Protokoll des ersten vollständigen Testlaufs
  (Windows-MCP braucht Python 3.14, BOM von PowerShell, Priorität der Aufgabenplanung, Whisper-Threads, erster Ton,
  Prüfsummen der Weckwort-Modelle u. a.). Die Einheitentests überspringen unter Windows die Rechte-Prüfung, der
  PC-Client liest `einstellungen.json` auch mit BOM.
- **Bauanleitung nach dem Laptop-Test:** In einer eigenen Variante des PC-Clients bleibt `VERSION` eine Zahl (eine
  Kennzeichnung kommt in ein eigenes Feld); die Abnahme prüft die Anzeige im Zahnrad.
- **Linux-Installer:** Meldungen nach `JARVIS_SPRACHE` bzw. der Systemsprache, `--neu` legt die englische Bauanleitung
  dazu. Nach dem Koppeln holt er wie das Windows-Setup `/v1/client` (Sprache, Stimme, Adressen, Aussprache); vorher
  blieb ein Linux-Client an einem englischen Jarvis bei Deutsch.
- **Dokumente:** `EINRICHTUNG.en.md`, `SECURITY.en.md`, `CONTRIBUTING.en.md`, `app/README.en.md`, `README.en.md`
  vollständig.

Sicherheit (unabhängige Prüfung des Unterschieds zu 0.2.0, nichts Kritisches):

- **Knöpfe nur mit PC-Rechten:** Ein Knopf läuft beim Klick im PC-Fenster mit PC-Werkzeugen. Bisher durfte jedes
  gekoppelte Gerät Knöpfe setzen, auch die Web-App oder ein Lautsprecher per Sprache, das war ein Umweg zu den
  PC-Werkzeugen (bestand schon in 0.2.0). Jetzt nur noch Quellen, die selbst PC-Rechte haben können
  (`oberflaeche.betrifft_knoepfe()`, Regel in der Bauanleitung), und ein Web-App-Token zählt am Zahnrad als `webapp`.
- **Zahnrad:** Client und Bauanleitung lassen nur die Aktionen des Zahnrads durch, Änderungen als Objekt bis 8 KB.
- **PC-Fenster:** Ist der Port der Durchreiche belegt, nimmt sie einen freien. Bisher lud das Fenster dann direkt aus
  dem Netz und hatte trotzdem die volle Schnittstelle; jetzt hat es sie nur unter `127.0.0.1`.
- **Installer:** Setup und Linux-Installer schicken ein gespeichertes Token erst nach dem Beweis der Brücke und
  übernehmen Werte aus `/v1/client` nur geprüft. Ein kaputter Port verhindert den Start des Clients nicht mehr.
- **edge-tts:** keine Ausnahme mehr von der Zwei-Wochen-Regel, sondern Prüfsumme und bis dahin die lokale Stimme.
- **Robuster:** App und HUD nehmen nur `de`/`en` als Sprache, das Zahnrad im HUD baut sich auch bei einer
  unvollständigen Antwort der Brücke auf.

Neue Bausteine in der Bauanleitung (im eigenen Betrieb erprobt):

- **Unwetter:** amtliche DWD-Warnungen für die eigene Gemeinde, als Werkzeug, im Wetter und von selbst als Push
  (ab Stufe 2, nachts ab Stufe 3).
- **Gerät fertig:** Regeln für Home Connect und Steckdosen mit Leistungsmessung (aus echten Läufen abgeleitet),
  Ansagen nie in Schlaf- und Kinderzimmern.
- **Handy suchen:** lautes „Hier bin ich“ über die Home-Assistant-App, auch wenn das Handy lautlos ist.
- **Musik überall:** mehrere Räume gleichzeitig, Echos über ihren eigenen Dienst, Schlaf- und Kinderzimmer
  ausgenommen.
- **Bildschirm erklären** am PC: Bildschirmfoto über Windows-MCP, nur auf Nachfrage.
- **Erster Ton vorab:** Der Ton des ersten Satzes entsteht, während Jarvis noch schreibt.

## 0.2.0 – 2026-10-25

Erste öffentliche Fassung.

- **Linux:** `Jarvis-Linux.tar.gz` mit `installieren.sh` (ohne Root, eigene Python-Umgebung, Pakete mit
  Prüfsummen für x86_64 und aarch64). Fehlende Bibliotheken für Ton und Fenster ermittelt das Skript selbst und
  installiert sie nach Rückfrage. Mit Bildschirm: Fenster, Autostart, Menüeintrag. Ohne Bildschirm (z. B. Raspberry
  Pi): Weckwort und Stimme als Benutzerdienst. Dazu `--neu` (Claude Code) und `--entfernen`.
- **Android-App 4.1 im Release** (`Jarvis-App.apk`): keine festen Adressen, Kopplung per Link oder Code, Updates aus
  dem neuesten GitHub-Release mit Prüfsumme. Neues **Zahnrad-Menü** mit allem, was sich einstellen lässt: Farbe
  (auch eigene), Name, Anrede, Nachtmodus, ruhige Bewegung, was die App zeigt, eigene Knöpfe (hinzufügen, sortieren,
  entfernen), Bereiche des Wandbildschirms, Verhalten, Stimme, Antworten als Text, Verbindung, Version und Update.
- **Web-App für iPhone und iPad** ohne App Store: die Oberfläche der App, ausgeliefert von der Brücke im Heimnetz
  unter `/app`, zum Home-Bildschirm hinzufügbar. Ihre Geräte gelten nur im Heimnetz und ohne PC-Werkzeuge,
  Content-Security-Policy mit Hashes der Skripte.
- **Setup:** Seite „Jarvis aufs Handy“ mit QR-Code zur App, Lizenzseite, Ordner für den PC-Client wählbar. Er muss
  leer oder neu sein, bekommt Rechte nur für das eigene Konto, und die Deinstallation löscht ihn nur mit der Marke
  des Setups ganz. Sie entfernt nur noch, was das Setup angelegt hat (Verknüpfungen mit festem Namen, Windows-MCP
  nur, wenn es vom Setup kommt).
- **Verhalten auf Zuruf:** Zwischensätze an/aus, Antwortstil kurz/normal/ausführlich, Nachtruhe für Durchsagen und
  Vorlesen. Standard ist das bisherige Verhalten.
- **PC-Client 13:** läuft auch unter Linux, ohne Fenster als Rückfall, Ordner aus seinem eigenen Ort. Er schickt
  sein Token erst, wenn die Brücke sich bewiesen hat (wie die App), spielt Updates der Brücke nur mit Signatur ein
  und holt die HUD-Daten mit Token. GitHub-Updates nur über Tags `pc-<Nummer>` mit Prüfsumme, die automatische
  Suche lässt sich abschalten (`"auto_update": false`).
- **Lizenz:** PolyForm Noncommercial 1.0.0 (private und nicht-kommerzielle Nutzung frei), Beitragsregeln in
  `CONTRIBUTING.md`, Issue-Vorlagen, ein Workflow baut Setup und Linux-Paket auf ein Tag hin.
- **Setup: neue Seite „Deine Oberfläche“** (nur beim Neueinrichten): Design (Rot-Gold, Cyan, Blau, Grün oder eigene
  Farben), Zeile unter dem Logo, Bereiche der Hauptseite mit Vorauswahl passend zu den Fähigkeiten, eigene Wünsche.
  Die Antworten landen in `antworten.json`, Claude baut daraus die Oberfläche (Bauanleitung, Runde 6a).
- **Oberfläche für alle gleich, Einstellungen getrennt:** Die Seite enthält nichts Persönliches mehr. Farbe,
  Bereiche, Begrüßung und Knöpfe kommen von der Brücke mit dem Zustand, die Daten als fertige JSON-Dateien. Neu sind
  die Farbsätze Blau und Grün, eigene Farben und abschaltbare Bereiche. Die Begrüßung zeigt jetzt die richtige
  Tageszeit, vorher hieß es immer „Abend“.
- **Aussehen auf Zuruf:** Werkzeug `oberflaeche` mit Vorschau (geht nach 60 Sekunden von selbst zurück), Behalten,
  Rückgängig und Grundeinstellung. Das Prüfmodul `oberflaeche.py` liegt als Vorlage bei. Updates überschreiben die
  Einstellungen nicht.
- **Echtzeit je Gerät abschaltbar** (für Geräte von Kindern), Gedächtnis in der Echtzeit-Anweisung als Schalter,
  Ratenlimit je Gerät auch im Heimnetz, Protokoll ohne Gesprächsinhalte (Bauanleitung).
- **PC-Client 12 und 13** statt 6 im Setup: Update-Knopf, Echtzeit-Modus, Zwischenstand, eigenes Symbol. Beim Weckwort
  holt er das Fenster nur noch aus der Minimierung zurück, vorher sprang es aus dem Vollbild.
- **Lieferkette:** uv 0.12.24 mit Prüfsumme des Installers, alle Python-Pakete samt Abhängigkeiten mit Prüfsummen
  (Stichtag 11.10.2026), Weckwort-Modelle mit SHA-256, Windows-MCP 0.8.8 mit demselben Stichtag.
- **PC-Steuerung:** Firewall-Regel nur noch in privaten Netzen und Domänen, mit Hinweis, falls Windows das Heimnetz
  als „Öffentlich“ führt. Die Regel wird kodiert übergeben, PowerShell immer mit vollem Pfad.
- **Deinstallation:** Die Firewall-Regel wird auch entfernt, wenn der Ordner von Windows-MCP schon fehlt, und
  Windows-MCP wird samt Python-Prozess beendet. `reste-pruefen.ps1` trennt echte Reste von bewusst gebliebenen
  Werkzeugen (Claude Code, uv, Git) und meldet wieder „SAUBER“.
- Ein Apostroph im Benutzerpfad bricht den Modell-Download nicht mehr ab.
- **Bauanleitung:** Runde 6a (Oberfläche), Echtzeit mit eigenem Gemini-Schlüssel und den Bedingungen von Google,
  Zwischenstand, Selbsttest, Updates, vollständige Endpunktliste, Lehren aus einer Sicherheitsprüfung (Rechte am
  Token, Beweis der Brücke vor dem Token, Schutz vor Zugriffen aufs eigene Netz, Senden nur nach klarem Ja).
- Das Setup lässt sich aus einem frischen Klon bauen.

## 0.1.x – 2026-10-23

Testfassungen für den ersten vollständigen Durchlauf auf einem frischen Windows-Laptop (nicht veröffentlicht).
