#!/bin/sh
# Baut dist/Jarvis-Setup.exe mit makensis in einem Container (kein Windows nötig).
# Aufruf: ./bauen.sh [Version]   z. B. ./bauen.sh 0.1.0
# Braucht Docker. Das Bild "jarvis-nsis:3" (Debian + nsis) wird beim ersten Lauf gebaut.
set -eu
HIER=$(cd "$(dirname "$0")" && pwd)
RELEASE=$(dirname "$HIER")
VERSION=${1:-0.1.0}
DOCKER=${DOCKER:-docker}
CLIENT=${CLIENT:-$RELEASE/vorlagen/pc}          # jarvis_pc.py und jarvis.ico
HUD=${HUD:-$RELEASE/vorlagen/hud/index.html}      # HUD (fuer alle gleich, Einstellungen kommen von der Bruecke)
OBERFLAECHE=${OBERFLAECHE:-$RELEASE/vorlagen/bruecke/oberflaeche.py}   # Pruefmodul fuer die Oberflaechen-Einstellungen
# Fester Link auf die App im neuesten GitHub-Release (Setup-Seite "Jarvis aufs Handy", als Link und als QR-Code)
APP_URL=${APP_URL:-https://github.com/Hellraiser28/jarvis-hausassistent/releases/latest/download/Jarvis-App.apk}
for f in "$CLIENT/jarvis_pc.py" "$CLIENT/jarvis.ico" "$CLIENT/pakete.txt" "$CLIENT/weckwort.txt" "$HUD" "$OBERFLAECHE"; do
  [ -f "$f" ] || { echo "FEHLER: $f fehlt (erst release/vorlagen_erzeugen.sh laufen lassen)" >&2; exit 1; }
done

# Dateien, die ins Setup kommen
rm -rf "$HIER/dateien"
mkdir -p "$HIER/dateien" "$HIER/dist"
cp "$HIER/einrichten.ps1" "$HIER/entfernen.ps1" "$RELEASE/EINRICHTUNG.md" "$RELEASE/EINRICHTUNG.en.md" "$HIER/bilder/seitenbild.bmp" \
  "$HIER/dateien/"
cp "$CLIENT/jarvis_pc.py" "$CLIENT/jarvis.ico" "$CLIENT/pakete.txt" "$CLIENT/weckwort.txt" "$HIER/dateien/"
cp "$HUD" "$HIER/dateien/hud.html"
cp "$OBERFLAECHE" "$HIER/dateien/oberflaeche.py"
# Verhalten und Web-App (seit 25.10.2026), fuer den Weg "neu" (Claude baut daraus die Bruecke)
cp "$RELEASE/vorlagen/bruecke/verhalten.py" "$RELEASE/vorlagen/webapp/jarvis-web.js" "$RELEASE/vorlagen/webapp/webapp_bauen.py" \
  "$HIER/dateien/"
cp "$RELEASE/app/android/assets/app.html" "$HIER/dateien/app.html"
# Symbol fuer die Web-App und die Einheitentests der beiden Pruefmodule (laufen neben den Modulen)
cp "$CLIENT/jarvis.png" "$RELEASE/vorlagen/bruecke/test_oberflaeche.py" "$RELEASE/vorlagen/bruecke/test_verhalten.py" "$HIER/dateien/"
# Lizenz fuer die Lizenzseite: Markdown-Zeichen weg, Windows-Zeilenenden
sed -e 's/^#\{1,\} //' -e 's/\*\*\*//g' -e 's/\*\*//g' -e 's/\[\([^]]*\)\](#[^)]*)/\1/g' -e 's/^<\(http[^>]*\)>$/\1/' \
  -e 's/$/\r/' "$RELEASE/LICENSE" > "$HIER/dateien/LICENSE.txt"

# QR-Code fuer die App aus genau der Adresse, die das Setup auch als Link zeigt (Bild "jarvis-qr:1" beim ersten Lauf)
if ! $DOCKER image inspect jarvis-qr:1 >/dev/null 2>&1; then
  printf 'FROM python:3.12-slim\nRUN pip install --no-cache-dir qrcode==8.2 pillow==11.3.0\n' | $DOCKER build -q -t jarvis-qr:1 -
fi
$DOCKER run --rm --user "$(id -u):$(id -g)" -v "$HIER:/arbeit" -w /arbeit jarvis-qr:1 \
  python bilder/app_qr.py "$APP_URL" dateien/app-qr.bmp

# Windows PowerShell 5.1 liest Skripte ohne BOM als Windows-1252: aus "Ä" wird "Ã„", und "„" gilt PowerShell als
# Anführungszeichen. Das Skript bricht dann sofort ab (Laptop-Test 23.10.2026). Mit Umlauten also nur mit UTF-8-BOM.
for ps in "$HIER"/dateien/*.ps1; do
  if LC_ALL=C grep -q '[^ -~[:space:]]' "$ps" && [ "$(head -c 3 "$ps" | od -An -tx1 | tr -d ' ')" != "efbbbf" ]; then
    echo "FEHLER: $(basename "$ps") enthält Nicht-ASCII-Zeichen, aber keine UTF-8-BOM" >&2
    exit 1
  fi
done

if ! $DOCKER image inspect jarvis-nsis:3 >/dev/null 2>&1; then
  printf 'FROM debian:bookworm-slim\nRUN apt-get update && apt-get install -y --no-install-recommends nsis && rm -rf /var/lib/apt/lists/*\n' |
    $DOCKER build -q -t jarvis-nsis:3 -
fi

# -WX: Warnungen sind Fehler. Eigene Benutzerkennung, damit die exe nicht root gehört.
$DOCKER run --rm --user "$(id -u):$(id -g)" -v "$HIER:/arbeit" -w /arbeit jarvis-nsis:3 \
  makensis -V2 -WX -DVERSION="$VERSION" -DAPP_URL="$APP_URL" jarvis-setup.nsi

ls -l "$HIER/dist/Jarvis-Setup.exe"
sha256sum "$HIER/dist/Jarvis-Setup.exe"
