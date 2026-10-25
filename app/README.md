# Jarvis-App (Android)

Die fertige App liegt in jedem Release als `Jarvis-App.apk`, dazu `Jarvis-App.json` mit Versionsnummer und SHA-256.
Das Setup zeigt einen QR-Code auf die neueste Fassung. Hier liegt der Quellcode.

## So funktioniert sie

- Eine WebView mit der Oberfläche `android/assets/app.html` und eine kleine Java-Schicht
  (`android/java/…/MainActivity.java`): Spracherkennung des Handys, Sprachausgabe über die Brücke, Echtzeit über
  Gemini Live, Update-Knopf.
- **Keine festen Adressen.** Heimnetz-Adresse und Fernzugang kommen aus der Kopplung: per Kopplungslink
  `jarvis://koppeln?adresse=…&code=…` von der Kopplungsseite deiner Brücke oder per Eingabe. http nimmt die App nur
  für Adressen im eigenen Netz an (private IPv4, Tailscale, `*.local`), sonst nur https.
- Bevor die App ihr Token im Heimnetz schickt, beweist die Brücke, dass sie das Token kennt (HMAC über eine
  Zufallszahl).
- **Aussehen von der Brücke:** Farbe, Knöpfe, Begrüßung und Startzeilen kommen mit dem Zustand
  (`oberflaeche`). Ein App-Update überschreibt sie nicht.
- **Updates** aus dem neuesten GitHub-Release, geprüft per SHA-256. Android spielt nur ein, was mit demselben
  Schlüssel signiert ist.
- `android/assets/vorgaben.json` steuert die Fassung: leer lassen für die Kopplung per Link, `update_github` zeigt auf
  dieses Projekt. Liegt deine Fassung auf Forgejo oder Gitea, setz zusätzlich `update_api` auf deren API, etwa
  `https://forgejo.example.org/api/v1` (nur https; Standard ist GitHub).

## Echtheit prüfen

Die App aus den Releases ist mit dem Schlüssel dieses Projekts signiert (`CN=Jarvis Hausassistent, O=Hellraiser28`).
Fingerabdruck des Zertifikats (SHA-256):

```
98:2C:5F:E6:33:CF:91:4D:86:C6:F2:DA:77:EA:A5:A3:0E:67:48:56:27:07:B5:51:02:EA:82:3A:D1:E4:36:D1
```

Prüfen mit `apksigner verify --print-certs Jarvis-App.apk` (Android-SDK) oder `keytool -printcert -jarfile
Jarvis-App.apk` (Java). Steht dort ein anderer Fingerabdruck, stammt die Datei nicht aus diesem Projekt.

## Selbst bauen

Nur nötig, wenn du die App änderst. Mit einem eigenen Schlüssel lassen sich danach keine Updates aus diesem Projekt
mehr einspielen.

```sh
ANDROID_SDK=/pfad/zum/sdk SCHLUESSEL=/pfad/zu/schluessel.jks SCHLUESSEL_ALIAS=jarvis \
SCHLUESSEL_PASS_DATEI=/pfad/zur/passwortdatei app/bauen.sh
```

Das SDK braucht `build-tools/34.0.0` und `platforms/android-34`. Gebaut wird ohne Gradle in einem JDK-Container.
Deshalb dürfen im Java-Code keine Lambdas stehen.
