#!/bin/sh
# Python-Pakete des PC-Clients festnageln, mit Pruefsummen (seit 24.10.2026, Linux seit 25.10.2026).
#   ./pakete_aufloesen.sh [Stichtag]     z. B. 2026-10-11T00:00:00Z
# Loest vorlagen/pc/pakete.in fuer Windows und vorlagen/pc/pakete-linux.in fuer Linux (x86_64 und aarch64) auf,
# jeweils Python 3.12 (uv pip compile in einem Wegwerf-Container), und schreibt pakete.txt bzw. pakete-linux.txt.
# Der Stichtag setzt die Zwei-Wochen-Regel auch fuer alle Abhaengigkeiten durch: nichts, was danach erschienen ist.
# Stichtag hier und in installer/einrichten.ps1 ($Stichtag, fuer windows-mcp) gleich halten.
set -eu
HIER=$(cd "$(dirname "$0")" && pwd)
STICHTAG=${1:-2026-10-11T00:00:00Z}
UV=0.12.24
DOCKER=${DOCKER:-docker}
aufloesen() {   # $1 = Eingabe, $2 = Ausgabe, $3 = Plattform
  $DOCKER run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$HIER/vorlagen/pc:/pc" python:3.12-slim sh -c \
    "pip install -q --user uv==$UV && /tmp/.local/bin/uv pip compile --quiet --generate-hashes \
       --python-platform $3 --python-version 3.12 --exclude-newer $STICHTAG \
       --no-header -o /pc/$2 /pc/$1"
  sed -i "1i # Erzeugt mit release/pakete_aufloesen.sh (uv $UV, $3, Stichtag $STICHTAG). Nicht von Hand aendern." \
    "$HIER/vorlagen/pc/$2"
  echo "$2: $(grep -c '^[a-zA-Z]' "$HIER/vorlagen/pc/$2") Pakete, $(grep -c 'sha256:' "$HIER/vorlagen/pc/$2") Pruefsummen"
}
aufloesen pakete.in pakete.txt x86_64-pc-windows-msvc
# Linux: eine Aufloesung fuer x86_64; uv schreibt alle Pruefsummen der gewaehlten Versionen, also auch die der
# aarch64-Wheels. Ob es fuer aarch64 zu jedem Paket ein Wheel gibt, prueft die zweite Aufloesung (nur Kontrolle).
aufloesen pakete-linux.in pakete-linux.txt x86_64-manylinux_2_28
aufloesen pakete-linux.in pakete-linux-arm.txt aarch64-manylinux_2_28
if [ "$(grep -E '^[a-zA-Z]' "$HIER/vorlagen/pc/pakete-linux.txt")" = "$(grep -E '^[a-zA-Z]' "$HIER/vorlagen/pc/pakete-linux-arm.txt")" ]; then
  echo "aarch64: gleiche Versionen wie x86_64"
  rm "$HIER/vorlagen/pc/pakete-linux-arm.txt"
else
  echo "aarch64: andere Versionen, siehe pakete-linux-arm.txt"
fi
