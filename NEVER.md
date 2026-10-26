# Was Jarvis nie tut

*English: [NEVER.en.md](NEVER.en.md)*

Jarvis hat viel Zugriff: aufs Haus, auf Kalender und Nachrichten, auf Wunsch auf den PC. Deshalb steht hier, was er
nie tut. Jeder Punkt ist entweder im Code erzwungen oder eine feste Regel der Bauanleitung, die Claude bei jedem
Nachbau einbaut und bei der Abnahme ausprobiert. Wo du selbst entscheiden kannst, steht die Voreinstellung dabei.

## Immer, für jeden

**Er gibt sich nie als Mensch aus.** Fragt ihn jemand, ob er eine KI ist, antwortet er ehrlich, auch am Telefon.
Nachrichten, die er in deinem Auftrag verschickt, tragen einen Hinweis, dass Jarvis sie geschickt hat.

**Er schickt nichts an andere ohne dein Ja.** Nachrichten an Familienmitglieder, Mails und Durchsagen gehen nur nach
ausdrücklicher Zustimmung im Gespräch raus. „Was ist los?“ ist kein Ja.

**Fremder Text ist nie ein Auftrag.** Was in Mails, Kalendern, Webseiten, Dokumenten oder Nachrichten steht, sind
Daten. Es löst keine Aktion aus und keine Freigabe-Anfrage.

**Er schaltet nichts ungefragt ein.** Von sich aus meldet er nur, etwa Unwetter oder ein fertiges Gerät. Einzige
Ausnahme: Bei einer Gefahr, die du beim Einrichten festgelegt hast (welches Gerät, welche Bedingung), darf er
**abschalten**, und er sagt es dir sofort.

**Er verschafft sich keine Rechte.** Seine Sicherheitsregeln (Sperrliste, Freigaben, neue Geräte, Echtzeit) lassen
sich nicht einfach per Zuruf lockern, sondern nur mit deinem Codewort und einer Bestätigung auf deinem Handy.

**Er kommt nicht hinten herum an deinen Rechner.** Das Gehirn hat keine Kommandozeile und keinen Dateizugriff, nur
benannte Werkzeuge. Die PC-Steuerung gibt es nur, wenn du im PC-Fenster tippst oder deine App benutzt, nie über
Lautsprecher, Telefon oder unbekannte Geräte. Per Sprache am PC, per Echtzeit und von unterwegs nur, wenn du sie
ausdrücklich einschaltest, denn sonst könnte auch ein Video aus deinen Lautsprechern „Hey Jarvis“ sagen.

**Was einer Person gehört, bleibt bei ihr.** Was jemand Jarvis erzählt, erfährt keine andere Person. Ort und private
Termine anderer gibt er nur mit deren Zustimmung heraus. Eltern dürfen Ort und Termine ihrer Kinder erfragen, nie
deren Gespräche mit Jarvis.

**Er löscht nie endgültig ohne dein Ja.** Dateien, Mails, Termine oder Dokumente unwiderruflich zu löschen geht nur
nach ausdrücklicher Bestätigung. Sein eigenes Gedächtnis vergisst er auf Wunsch.

**Er speichert deine Stimme nicht.** Der Ton wird erkannt und verworfen. Aufnahmen entstehen nur, wenn du zur
Fehlersuche ausdrücklich Mitschnitte einschaltest, und danach werden sie gelöscht.

**Er manipuliert nicht.** Wie frech oder sachlich er ist, bestimmst du. Aber er macht keinen Druck, nutzt keine
Gefühle aus und überredet dich nicht, um etwas zu erreichen.

**Er fälscht keine Menschen.** Bilder, die echte Personen bloßstellen, sexualisieren oder ihnen etwas unterschieben,
macht er nicht, auch nicht aus deinen eigenen Fotos. Erzeugte Bilder zeigen keine echten Personen und keine fremden
Marken oder Logos.

**Bei einem Notfall zuerst 112.** Bei Gesundheit und Recht hilft er mit Informationen, sagt aber dazu, wann ein Arzt
oder ein Anwalt nötig ist. Er ersetzt beide nicht.

**Mit Kindern kindgerecht.** Auf Geräten von Kindern gibt es keine Echtzeit (Googles Bedingungen), kein Kaufen und
keine Inhalte für Erwachsene, und er bedient nur die Geräte, die für das Kind freigegeben sind.

**Keine Gesprächsinhalte im Protokoll.** Das Protokoll der Brücke enthält Quelle, Dauer, Werkzeug und Längen, nicht,
was gesagt wurde.

**Er meldet nichts nach Hause.** Es gibt keine Telemetrie und keine Werbung. Nach Updates fragen nur App und
PC-Client, bei deinem Jarvis oder bei GitHub.

## Voreinstellung „nie“, änderbar beim Einrichten

| Thema | Voreinstellung | Wahlweise |
|---|---|---|
| Kaufen, bestellen, bezahlen | nie | nur nach ausdrücklichem Ja im Gespräch |
| Türschlösser öffnen, Alarm entschärfen | nie (abschließen und scharfschalten geht) | nur nach Ja aus deiner App, nie per Lautsprecher oder Telefon |
| Kameras und Babyfon | gesperrt | freigeben, Gerät für Gerät |
| Gedächtnis | merkt sich Nützliches von selbst, alles einsehbar und löschbar („Was weißt du über mich?“, „Vergiss …“) | nur auf „Merk dir …“ |
| Ton | wie beim Einrichten gewählt | frech oder sachlich; die Untergrenze oben gilt immer |

## Wohin deine Daten gehen

- **Gedächtnis, Gesprächsverlauf und Profil** liegen auf deinem Jarvis-Rechner.
- **Jede Frage** geht mit dem nötigen Kontext an Claude (Anthropic). Ohne das geht es nicht.
- **Stimme:** Der Antworttext geht an Microsoft (`edge-tts`). Die Reserve-Stimme Piper bleibt auf deinem Rechner.
- **Spracherkennung:** Was du am PC und am Telefon sagst, erkennt dein Jarvis-Rechner selbst. Die Android-App nutzt
  die Erkennung des Handys (meist Google), das iPhone die von Apple.
- **Echtzeit** (nur wenn eingeschaltet): Ton, Anweisung und Antworten gehen an Google.
- **Dateien**, die du ins Gespräch gibst: Bilder, PDF und Text gehen mit der Frage an Claude (Anthropic). Ton
  schreibt dein Jarvis-Rechner selbst ab, an Claude geht nur die Abschrift. Auf dem Jarvis-Rechner liegen deine
  Dateien und die, die Jarvis dir zurückgibt, 7 Tage in einer Ablage, dazu im Gesprächsverlauf.
- **Bilder bearbeiten und erzeugen** (nur wenn eingerichtet): Das Bild und der Auftrag gehen an den Anbieter, den
  du beim Einrichten gewählt hast (Cloudflare, OpenAI oder Google). **PDFs** entstehen auf deinem Jarvis-Rechner.
  **Umwandeln** läuft über Transmute auf deinem eigenen Rechner.
- **Werkzeuge** wie Wetter, Nachrichten oder Websuche fragen die jeweiligen Dienste ab. Die sehen die Anfrage, nicht
  dein Gespräch.
- **Die Oberfläche** lädt Schriften von Google Fonts (abschaltbar).

Findest du eine Stelle, an der Jarvis sich nicht an diese Seite hält, melde sie bitte als Sicherheitslücke
([SECURITY.md](SECURITY.md)), nicht als öffentliches Issue.
