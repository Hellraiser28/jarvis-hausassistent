#!/bin/sh
# Linux-Paket fuer das Release bauen (seit 25.10.2026): dist/Jarvis-Linux.tar.gz mit dem Ordner jarvis-linux/.
#   linux/bauen.sh
# Inhalt: installieren.sh, PC-Client, Symbol, Paketlisten mit Pruefsummen, dazu fuer --neu die Bauanleitung und die
# Vorlagen (HUD, Pruefmodul der Oberflaeche). Feste Zeitstempel und Besitzer, damit derselbe Stand dasselbe Archiv ergibt.
set -eu
HIER=$(cd "$(dirname "$0")" && pwd)
R=$(dirname "$HIER")
V=$R/vorlagen
DIST=$HIER/dist
rm -rf "$DIST"
mkdir -p "$DIST/jarvis-linux"
cp "$HIER/installieren.sh" "$DIST/jarvis-linux/"
chmod 755 "$DIST/jarvis-linux/installieren.sh"
cp "$V/pc/jarvis_pc.py" "$V/pc/jarvis.png" "$V/pc/pakete-linux.txt" "$V/pc/weckwort.txt" "$DIST/jarvis-linux/"
[ -f "$V/pc/pakete-linux-arm.txt" ] && cp "$V/pc/pakete-linux-arm.txt" "$DIST/jarvis-linux/"
cp "$V/hud/index.html" "$DIST/jarvis-linux/hud.html"
cp "$V/bruecke/oberflaeche.py" "$V/bruecke/verhalten.py" "$V/webapp/jarvis-web.js" "$V/webapp/webapp_bauen.py" \
  "$DIST/jarvis-linux/"
cp "$R/app/android/assets/app.html" "$DIST/jarvis-linux/app.html"
cp "$V/bruecke/test_oberflaeche.py" "$V/bruecke/test_verhalten.py" "$DIST/jarvis-linux/"
# Fertige Bruecken-Module mit ihren Tests (seit 0.3.3)
for f in anhang.py ed25519.py ausgabe.py pdf.py bilddienst.py konvertieren.py zusatzdienste.py test_anhang.py test_ed25519.py test_pdf.py test_ausgabe.py test_bilddienst.py test_konvertieren.py; do
  cp "$V/bruecke/$f" "$DIST/jarvis-linux/"
done
cp "$R/EINRICHTUNG.md" "$R/EINRICHTUNG.en.md" "$DIST/jarvis-linux/"
cp "$R/LICENSE" "$DIST/jarvis-linux/LICENSE"
chmod 644 "$DIST/jarvis-linux/"*.py "$DIST/jarvis-linux/"*.js "$DIST/jarvis-linux/"*.txt "$DIST/jarvis-linux/"*.png "$DIST/jarvis-linux/"*.html \
  "$DIST/jarvis-linux/"*.md "$DIST/jarvis-linux/LICENSE"
python3 -m py_compile "$DIST/jarvis-linux/jarvis_pc.py"
rm -rf "$DIST/jarvis-linux/__pycache__"
bash -n "$DIST/jarvis-linux/installieren.sh"
# Reproduzierbar: sortiert, fester Zeitstempel, ohne Besitzernamen, gzip ohne Namen/Zeit
( cd "$DIST" && tar --sort=name --mtime='2026-10-24 00:00:00Z' --owner=0 --group=0 --numeric-owner \
    -cf - jarvis-linux | gzip -n -9 > Jarvis-Linux.tar.gz )
( cd "$DIST" && sha256sum Jarvis-Linux.tar.gz > Jarvis-Linux.tar.gz.sha256 && cat Jarvis-Linux.tar.gz.sha256 )
tar tzvf "$DIST/Jarvis-Linux.tar.gz"
