# Sicherheit

## Vertrauensgrenze

Jarvis ist für **ein Zuhause** gebaut. Die Vertrauensgrenze ist das eigene Heimnetz bzw. ein VPN (z. B. Tailscale
oder WireGuard). Die Brücke, über die alle Geräte mit dem Gehirn reden, lauscht nie offen im Internet:

- nur auf 127.0.0.1 und den Adressen, über die eigene Geräte kommen
- das Haupt-Token gilt nur von 127.0.0.1, jedes andere Gerät hat ein eigenes, widerrufbares Geräte-Token
- von unterwegs nur über VPN oder über einen zweiten, gehärteten Eingang hinter einem Reverse-Proxy (nur die nötigen
  Endpunkte, nur Geräte-Tokens, Sperre nach Fehlversuchen)

## Wie Jarvis aufgebaut ist

Die Regeln stehen ausführlich in `EINRICHTUNG.md` (Phase 2, „Sicherheit“). Die wichtigsten:

- **Zwei Gehirne.** Das Alltagsgehirn hat keine Shell und keinen Dateizugriff, nur die freigegebenen Werkzeuge. Ein
  Gehirn mit Shell gibt es nur, wenn die Person es will, und nur nach Freigabe.
- **Rechte hängen am Token, nicht an der Anfrage.** Welches Gerät spricht, steht im Token. Werkzeuge mit Wirkung auf
  den PC gibt es nur für Quellen auf einer Positivliste.
- **Tabu-Liste im Werkzeug.** Was Jarvis nie anfassen darf (z. B. Kameras, Türschlösser), sperrt das Werkzeug selbst,
  nicht nur die Anweisung. Geräte nur über einzelne Geräte-IDs, nie über Bereiche oder Etagen.
- **Fremder Text ist nie ein Auftrag.** Inhalte aus Mails, Kalendern, Webseiten und Nachrichten sind Daten. Das
  Gedächtnis geht als Notizen in den Prompt, nicht als Anweisungen.
- **Senden an andere nur nach klarem Ja**, mit Hinweis, dass Jarvis die Nachricht verschickt hat.
- **Kein Zugriff aufs eigene Netz über Umwege:** Quellen, die per Sprache dazukommen, nur über http(s) und nur
  öffentliche Adressen, auch nach der DNS-Auflösung.
- **App und PC-Client prüfen die Brücke, bevor sie ihr Token schicken** (HMAC über eine Zufallszahl, gebildet mit
  dem Hash des Tokens). In einem fremden WLAN mit gleicher Adresse geht so weder das Token noch eine Update-Anfrage an
  ein fremdes Gerät. Die Web-App kann das nicht, siehe „Bekannte Grenzen“.
- **Aussehen nur über geprüfte Einstellungen:** Jarvis ändert sein Aussehen über ein eigenes Werkzeug mit festen
  Schlüsseln und geprüften Werten, nie über den Code der Seite. Fremder Text und Routinen ändern es nicht.
- **Echtzeit je Gerät abschaltbar**, per Schalter am Rechner, nicht per Sprachbefehl.
- **Einstellungen aus dem Zahnrad-Menü** gehen durch dieselbe Prüfung wie die Werkzeuge (bekannte Schlüssel,
  feste Werte, Längengrenzen). Jedes gekoppelte Gerät darf sie ändern, Knöpfe aber nur Geräte und Quellen mit PC-Rechten: Ein Knopf läuft beim
  Klick mit den Rechten des Geräts, an dem geklickt wird. Rückgängig und Grundeinstellung gibt es immer.
- **Web-App nur im Heimnetz:** Die Seite unter `/app` enthält nichts Geheimes und hat eine strenge
  Content-Security-Policy (nur die beiden Skripte der Seite, per Hash; Verbindungen nur zur Brücke; nicht
  einbettbar). Web-App-Geräte gelten nur im Heimnetz, nie über den Fernzugang und nie mit PC-Werkzeugen. Das
  Geräte-Token liegt im Speicher des Browsers; Neu koppeln löscht es, Widerrufen am Rechner macht es ungültig.
- **Oberfläche ohne Geheimnisse:** Die HUD-Seite enthält nichts Persönliches. Ihre Daten holt das PC-Fenster mit
  Token über die Brücke, die lokale Durchreiche liegt unter einem zufälligen Pfad je Start. Alles, was die Seiten
  anzeigen, wird maskiert.
- **Testmodus:** Proben mit der Quelle `test…` führen Werkzeuge mit Wirkung nur trocken aus.
- **Geheimnisse** nie im Chat, nie in Git, nie in Befehlszeilen. Sie liegen in Dateien, die nur das eigene
  Benutzerkonto lesen kann. Den Ordner des PC-Clients setzt das Setup auf Rechte nur für dieses Konto (dazu SYSTEM und
  Administratoren), auch wenn er außerhalb des Benutzerprofils liegt.
- **Lieferkette:** uv, die Python-Pakete des Clients (samt Abhängigkeiten) und die Weckwort-Modelle lädt das Setup
  in festen Versionen und prüft ihre SHA-256. Neue Versionen erst, wenn sie mindestens zwei Wochen alt sind.
  Ausnahmen: Windows-MCP ist nur über diesen Stichtag festgelegt (ohne Prüfsummen), ein schon installiertes uv wird in
  seiner Version genommen, Claude Code und Git kommen aktuell von ihren offiziellen Quellen.
- **Updates:**
    - Der PC-Client holt neue Fassungen von der eigenen Brücke, erst nach ihrem Beweis und nur mit Signatur (HMAC mit
      dem Token-Hash über die SHA-256). Ist GitHub eingestellt, nur Releases mit Tag `pc-<Nummer>` und Prüfsumme. Er
      sucht alle sechs Stunden; `"auto_update": false` in den Einstellungen lässt nur noch den Knopf.
    - Die Release-App fragt GitHub nach einer neuen Fassung (`Jarvis-App.json` mit SHA-256) und lädt sie erst auf
      Tipp. Android installiert nur, was mit demselben Schlüssel signiert ist.
    - Die Web-App kommt bei jedem Öffnen frisch von der Brücke.

## Bekannte Grenzen

- **Jarvis unterscheidet keine Stimmen.** Wer im Raum spricht, spricht mit den Rechten des Geräts. Aufträge mit
  Shell von Lautsprechern aus lassen sich deshalb abschalten.
- **Ein Gehirn mit Shell** erreicht auch gesperrte Dateien. Davor schützen dann nur Anweisung und Freigabe.
- **Die Web-App** kommt per HTTP, ihr Geräte-Token liegt im Browser-Speicher dieser Adresse. Antwortet in einem
  fremden Netz ein anderes Gerät unter derselben Adresse, kann es das Token auslesen; ein Beweis der Brücke hilft
  hier nicht, weil die fremde Seite ihren eigenen Code mitbringt. Deshalb gelten Web-App-Geräte nur im Heimnetz und
  ohne PC-Werkzeuge. Öffne die Web-App am besten nur zu Hause. Wer mehr will: die Brücke per HTTPS mit eigenem Namen
  anbieten (z. B. `tailscale cert`).
- **Die Setup.exe ist nicht signiert.** Prüfe die SHA-256 aus dem Release-Text, bevor du sie startest.
- **Claude Code und Git** installiert das Setup in der aktuellen Fassung über die offiziellen Quellen, nicht
  festgenagelt.
- **Die PC-Steuerung (Windows-MCP)** lauscht auf Port 8000 an allen Netzwerkkarten. Erreichbar ist sie nur vom
  Jarvis-Rechner: Firewall-Regel nur für diese Adresse und nur in privaten Netzen, dazu eine Positivliste und ein
  eigener Schlüssel in Windows-MCP selbst.
- Was Jarvis baut, baut **Claude nach dieser Anleitung**. Das Ergebnis hängt von der Umgebung und von den
  Entscheidungen der Person ab. Die Abnahme in Phase 3 prüft die wichtigsten Punkte, ersetzt aber keine eigene
  Durchsicht.

## Eine Lücke melden

Bitte nicht als öffentliches Issue. Nutze auf GitHub „Security“ → „Report a vulnerability“ (private Meldung). Schreib
dazu, welche Datei betroffen ist und wie man es nachstellt. Du bekommst eine Antwort, sobald jemand sie gesehen hat.
Das ist ein privates Projekt, eine feste Reaktionszeit gibt es nicht.
