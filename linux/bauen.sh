#!/bin/sh
# Linux-Paket fuer das Release bauen (seit 25.10.2026): dist/Jarvis-Linux.tar.gz mit dem Ordner jarvis-linux/.
#   linux/bauen.sh
# Inhalt: installieren.sh, PC-Client, Symbol, Paketlisten mit Pruefsummen, dazu fuer --neu die Bauanleitung und unter
# vorlagen/ alles, was nach ~/Jarvis/einrichtung kommt. Feste Zeitstempel und Besitzer, damit derselbe Stand dasselbe
# Archiv ergibt.
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
# Vorlagen fuer --neu (seit 0.6 per Platzhalter statt fester Liste, Pruefung 05.11.2026: es kamen nur die Module von
# 0.3.3 mit): alle Bruecken-Module mit ihren Tests, HUD, App-Seite, Web-App und die Ordner grundriss/, sprecher/,
# gemeinsam/. installieren.sh --neu kopiert vorlagen/ 1:1 nach ~/Jarvis/einrichtung (wie das Windows-Setup).
VL=$DIST/jarvis-linux/vorlagen
mkdir -p "$VL"
cp "$V"/bruecke/*.py "$VL/"
cp "$V/hud/index.html" "$VL/hud.html"
cp "$R/app/android/assets/app.html" "$V/webapp/jarvis-web.js" "$V/webapp/webapp_bauen.py" "$V/pc/jarvis.png" "$VL/"
cp -R "$V/grundriss" "$V/sprecher" "$V/gemeinsam" "$VL/"
# test_grundriss.py sucht das Beispielhaus in ../grundriss/ und neben sich, nicht in einrichtung/grundriss/: die Testdaten
# deshalb zusaetzlich neben die Tests, sonst ueberspringt er den Teil im Projekt
cp "$V/grundriss/beispiel-haus3d.json" "$VL/"
cp "$R/EINRICHTUNG.md" "$R/EINRICHTUNG.en.md" "$DIST/jarvis-linux/"
cp "$R/LICENSE" "$DIST/jarvis-linux/LICENSE"
find "$DIST/jarvis-linux" -depth \( -name __pycache__ -o -name '*.pyc' \) -exec rm -rf {} +
find "$DIST/jarvis-linux" -type d -exec chmod 755 {} +
find "$DIST/jarvis-linux" -type f -exec chmod 644 {} +
chmod 755 "$DIST/jarvis-linux/installieren.sh"
python3 -m py_compile "$DIST/jarvis-linux/jarvis_pc.py"
rm -rf "$DIST/jarvis-linux/__pycache__"
bash -n "$DIST/jarvis-linux/installieren.sh"
# Reproduzierbar: sortiert, fester Zeitstempel, ohne Besitzernamen, gzip ohne Namen/Zeit
( cd "$DIST" && tar --sort=name --mtime='2026-10-24 00:00:00Z' --owner=0 --group=0 --numeric-owner \
    -cf - jarvis-linux | gzip -n -9 > Jarvis-Linux.tar.gz )
( cd "$DIST" && sha256sum Jarvis-Linux.tar.gz > Jarvis-Linux.tar.gz.sha256 && cat Jarvis-Linux.tar.gz.sha256 )
tar tzvf "$DIST/Jarvis-Linux.tar.gz"
