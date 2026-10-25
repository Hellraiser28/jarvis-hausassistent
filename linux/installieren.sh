#!/usr/bin/env bash
# J.A.R.V.I.S. unter Linux (seit 25.10.2026). Ohne Root-Rechte; nur fehlende Systembibliotheken installiert es nach
# Rückfrage mit sudo. Erneut ausführen = aktualisieren.
#   ./installieren.sh               PC-Client an einen bestehenden Jarvis koppeln (fragt Adresse und Kopplungscode)
#   ./installieren.sh --neu         neuen Jarvis mit Claude Code einrichten (Projektordner ~/Jarvis)
#   ./installieren.sh --entfernen   PC-Client wieder entfernen
# Ohne Rückfragen (alle optional): JARVIS_ADRESSE, JARVIS_CODE, JARVIS_NAME, JARVIS_AUTOSTART=ja|nein,
# JARVIS_MENUE=ja|nein, JARVIS_START=ja|nein, JARVIS_SYSTEMPAKETE=ja|nein, JARVIS_OHNE_FENSTER=ja|nein,
# JARVIS_CLAUDE=ja|nein (--neu), JARVIS_ENTFERNEN=ja|nein (--entfernen). Ohne Terminal und ohne Vorgabe gilt bei
# sudo, beim Installer von Claude Code und beim Löschen "nein". JARVIS_SPRACHE=de|en (sonst die Systemsprache).
# English: same switches; answers yes/no work as well as ja/nein.
# Ohne Fenster (z. B. Raspberry Pi mit Mikrofon und Lautsprecher): Weckwort und Stimme als systemd-Benutzerdienst.
set -euo pipefail
umask 077

HIER=$(cd "$(dirname "$0")" && pwd)
ZIEL=${XDG_DATA_HOME:-$HOME/.local/share}/jarvis
KONFIG=${XDG_CONFIG_HOME:-$HOME/.config}
ANWENDUNGEN=${XDG_DATA_HOME:-$HOME/.local/share}/applications
DIENST=$KONFIG/systemd/user/jarvis.service
PY=$ZIEL/venv/bin/python
EINST=$ZIEL/einstellungen.json
# Lieferkette wie unter Windows (installer/einrichten.ps1): feste Versionen, Prüfsummen, Stichtag 2026-10-11
UV_VERSION=0.12.24
declare -A UV_SHA=(
  [x86_64]=b4dfaef47d491a7296981f8374a4595f55dbf84e8937c8ecd2983574d8bb3da6
  [aarch64]=5231be65f496304623895dacdbf1de8504fec90303684bdf05805aa34414dd21
)
MODELL_BASIS=https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/
declare -A MODELLE=(
  [hey_jarvis_v0.1.onnx]=94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb
  [melspectrogram.onnx]=ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f
  [embedding_model.onnx]=70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f
)

if [ -t 1 ]; then BLAU=$'\e[36m'; GELB=$'\e[33m'; GRUEN=$'\e[32m'; ROT=$'\e[31m'; AUS=$'\e[0m'; else BLAU=; GELB=; GRUEN=; ROT=; AUS=; fi
# Sprache (seit 0.3.0): JARVIS_SPRACHE, sonst LC_ALL, LC_MESSAGES, LANG; de* = Deutsch, alles andere Englisch
case "${JARVIS_SPRACHE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in de*) EN=false ;; *) EN=true ;; esac
t() { if $EN; then printf '%s' "$2"; else printf '%s' "$1"; fi; }
schritt() { printf '\n%s>> %s%s\n' "$BLAU" "$1" "$AUS"; }
hinweis() { printf '   %s%s%s\n' "$GELB" "$1" "$AUS"; }
gut() { printf '   %s%s%s\n' "$GRUEN" "$1" "$AUS"; }
fehler() { printf '\n   %s%s: %s%s\n' "$ROT" "$(t FEHLER ERROR)" "$1" "$AUS" >&2; exit 1; }
# Frage mit Vorgabe; eine gesetzte Umgebungsvariable beantwortet sie ohne Rückfrage
frage() {   # $1 = Variable, $2 = Text, $3 = Vorgabe
  local wert=${!1:-}
  if [ -z "$wert" ]; then
    if [ -t 0 ]; then read -r -p "   $2${3:+ [$3]}: " wert || true; fi
    wert=${wert:-${3:-}}
  fi
  printf -v "$1" '%s' "$wert"
}
ja() { case "${1,,}" in j|ja|y|yes|1|an) return 0 ;; *) return 1 ;; esac; }
# Zustimmung zu etwas mit Wirkung (sudo, fremder Installer, Löschen): ohne Terminal nie stillschweigend "ja"
zustimmung() {   # $1 = Variable, $2 = Text, $3 = Vorgabe im Terminal
  if [ -z "${!1:-}" ] && [ ! -t 0 ]; then
    hinweis "$(t "Keine Rückfrage möglich (kein Terminal): nein. Vorgeben mit $4=ja." "Can't ask (no terminal): no. Set $4=yes to allow it.")"
    printf -v "$1" '%s' "nein"
    return
  fi
  frage "$1" "$2" "$3"
}
# Werte fuer Desktop-Dateien und systemd-Units maskieren (Pfade mit Leerzeichen, %, $, Anfuehrungszeichen)
desktop_arg() {
  local s=$1
  s=${s//\\/\\\\\\\\}; s=${s//\"/\\\"}; s=${s//\`/\\\`}; s=${s//\$/\\\$}; s=${s//%/%%}
  printf '"%s"' "$s"
}
desktop_wert() { local s=${1//\\/\\\\}; printf '%s' "$s"; }
systemd_arg() {
  local s=$1
  s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//%/%%}; s=${s//\$/\$\$}
  printf '"%s"' "$s"
}
# Laufenden Client beenden: nur genau "<venv-python> <ordner>/jarvis_pc.py ...", kein Editor mit der Datei
client_beenden() {
  local muster; muster=$(printf '%s %s' "$PY" "$ZIEL/jarvis_pc.py" | sed 's/[][\\.*^$+?(){}|/]/\\&/g')
  pkill -f -- "^$muster( |\$)" 2>/dev/null || true
}
laden() {   # $1 = Adresse, $2 = Datei
  if command -v curl >/dev/null; then curl -fsSL --retry 2 -o "$2" "$1"
  elif command -v wget >/dev/null; then wget -q -O "$2" "$1"
  else fehler "$(t "Weder curl noch wget gefunden. Bitte eins davon installieren." "Neither curl nor wget found. Please install one of them.")"; fi
}
pruefsumme() { sha256sum "$1" | cut -d' ' -f1; }

uv_bereit() {
  UV=$ZIEL/uv/uv
  if [ -x "$UV" ] && "$UV" --version 2>/dev/null | grep -q " $UV_VERSION"; then return; fi
  local arch; arch=$(uname -m)
  [ -n "${UV_SHA[$arch]:-}" ] || fehler "$(t "Prozessor $arch wird nicht unterstützt (nur x86_64 und aarch64)." "Processor $arch is not supported (only x86_64 and aarch64).")"
  local tmp; tmp=$(mktemp -d)
  laden "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$arch-unknown-linux-gnu.tar.gz" "$tmp/uv.tgz"
  [ "$(pruefsumme "$tmp/uv.tgz")" = "${UV_SHA[$arch]}" ] || { rm -rf "$tmp"; fehler "$(t "Prüfsumme von uv stimmt nicht." "Checksum of uv doesn't match.")"; }
  mkdir -p "$ZIEL/uv"
  tar xzf "$tmp/uv.tgz" -C "$tmp"
  mv "$tmp/uv-$arch-unknown-linux-gnu/uv" "$UV"
  rm -rf "$tmp"
  "$UV" --version
}

# Fehlende Systembibliotheken: PortAudio (Mikrofon und Lautsprecher) und was Qt WebEngine (das Fenster) braucht.
# Ermittelt wird mit ldd an den mitgelieferten Qt-Bibliotheken, also genau das, was auf diesem Rechner fehlt.
declare -A PAKET_APT=(
  [libportaudio.so.2]=libportaudio2 [libxcb-cursor.so.0]=libxcb-cursor0 [libxkbcommon-x11.so.0]=libxkbcommon-x11-0
  [libxkbcommon.so.0]=libxkbcommon0 [libxcb-icccm.so.4]=libxcb-icccm4 [libxcb-keysyms.so.1]=libxcb-keysyms1
  [libxcb-image.so.0]=libxcb-image0 [libxcb-render-util.so.0]=libxcb-render-util0 [libxcb-shape.so.0]=libxcb-shape0
  [libxcb-xkb.so.1]=libxcb-xkb1 [libxcb-randr.so.0]=libxcb-randr0 [libxcb-xfixes.so.0]=libxcb-xfixes0
  [libxcb-sync.so.1]=libxcb-sync1 [libxcb-shm.so.0]=libxcb-shm0 [libxcb-render.so.0]=libxcb-render0
  [libxcb-xinput.so.0]=libxcb-xinput0 [libxcb-glx.so.0]=libxcb-glx0 [libxcb.so.1]=libxcb1 [libX11-xcb.so.1]=libx11-xcb1
  [libX11.so.6]=libx11-6 [libXext.so.6]=libxext6 [libXcomposite.so.1]=libxcomposite1 [libXdamage.so.1]=libxdamage1
  [libXrandr.so.2]=libxrandr2 [libXtst.so.6]=libxtst6 [libXfixes.so.3]=libxfixes3 [libXrender.so.1]=libxrender1
  [libXi.so.6]=libxi6 [libxkbfile.so.1]=libxkbfile1 [libxshmfence.so.1]=libxshmfence1 [libnss3.so]=libnss3
  [libnssutil3.so]=libnss3 [libsmime3.so]=libnss3 [libnspr4.so]=libnspr4 [libplc4.so]=libnspr4 [libplds4.so]=libnspr4
  [libEGL.so.1]=libegl1 [libGL.so.1]=libgl1 [libOpenGL.so.0]=libopengl0 [libfontconfig.so.1]=libfontconfig1
  [libfreetype.so.6]=libfreetype6 [libdbus-1.so.3]=libdbus-1-3 [libglib-2.0.so.0]=libglib2.0-0
  [libgthread-2.0.so.0]=libglib2.0-0 [libgobject-2.0.so.0]=libglib2.0-0 [libexpat.so.1]=libexpat1
  [libasound.so.2]=libasound2 [libgbm.so.1]=libgbm1 [libdrm.so.2]=libdrm2 [libwayland-client.so.0]=libwayland-client0
  [libwayland-cursor.so.0]=libwayland-cursor0 [libwayland-egl.so.1]=libwayland-egl1 [libxml2.so.2]=libxml2
  [libatomic.so.1]=libatomic1 [libxcb-util.so.1]=libxcb-util1 [libxcb-xinerama.so.0]=libxcb-xinerama0
)
declare -A PAKET_DNF=(
  [libportaudio.so.2]=portaudio [libxcb-cursor.so.0]=xcb-util-cursor [libxkbcommon-x11.so.0]=libxkbcommon-x11
  [libxcb-icccm.so.4]=xcb-util-wm [libxcb-keysyms.so.1]=xcb-util-keysyms [libxcb-image.so.0]=xcb-util-image
  [libxcb-render-util.so.0]=xcb-util-renderutil [libnss3.so]=nss [libxkbfile.so.1]=libxkbfile [libasound.so.2]=alsa-lib
  [libatomic.so.1]=libatomic [libxcb-util.so.1]=xcb-util
)
declare -A PAKET_PACMAN=(
  [libportaudio.so.2]=portaudio [libxcb-cursor.so.0]=xcb-util-cursor [libxkbcommon-x11.so.0]=libxkbcommon-x11
  [libxcb-icccm.so.4]=xcb-util-wm [libxcb-keysyms.so.1]=xcb-util-keysyms [libxcb-image.so.0]=xcb-util-image
  [libxcb-render-util.so.0]=xcb-util-renderutil [libnss3.so]=nss [libxkbfile.so.1]=libxkbfile [libasound.so.2]=alsa-lib
  [libxcb-util.so.1]=xcb-util
)
fehlende_bibliotheken() {
  local sp; sp=$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
  {
    # ctypes sucht wie der Client (ldconfig auch unter /sbin, das fehlt normalen Nutzern oft im PATH)
    "$PY" -I -c 'import ctypes.util, sys; sys.exit(0 if ctypes.util.find_library("portaudio") else 1)' 2>/dev/null ||
      echo libportaudio.so.2
    for f in "$sp"/PyQt6/Qt6/lib/libQt6WebEngineCore.so.6 "$sp"/PyQt6/Qt6/lib/libQt6Gui.so.6 \
             "$sp"/PyQt6/Qt6/plugins/platforms/libqxcb.so "$sp"/PyQt6/Qt6/lib/libQt6XcbQpa.so.6; do
      if [ -e "$f" ]; then LD_LIBRARY_PATH="$sp/PyQt6/Qt6/lib" ldd "$f" 2>/dev/null | awk '/not found/ {print $1}' || true; fi
    done
  } | sort -u
}
systempakete() {
  local fehlt; fehlt=$(fehlende_bibliotheken)
  if [ -z "$fehlt" ]; then gut "$(t "alle Systembibliotheken vorhanden." "all system libraries present.")"; return; fi
  local pm="" pakete=() lib p
  if command -v apt-get >/dev/null; then pm=apt
  elif command -v dnf >/dev/null; then pm=dnf
  elif command -v pacman >/dev/null; then pm=pacman; fi
  for lib in $fehlt; do
    case $pm in
      apt) p=${PAKET_APT[$lib]:-}
           # Ubuntu ab 24.04 / Debian 13: einige Pakete heißen ...t64
           if [ -n "$p" ] && apt-cache show "${p}t64" >/dev/null 2>&1; then p=${p}t64; fi ;;
      dnf) p=${PAKET_DNF[$lib]:-} ;;
      pacman) p=${PAKET_PACMAN[$lib]:-} ;;
      *) p= ;;
    esac
    if [ -n "$p" ]; then pakete+=("$p"); else hinweis "$(t "fehlt: $lib (Paket bitte selbst suchen)" "missing: $lib (please find the package yourself)")"; fi
  done
  [ ${#pakete[@]} -gt 0 ] || return 0
  local liste; liste=$(printf '%s\n' "${pakete[@]}" | sort -u | tr '\n' ' ')
  hinweis "$(t "Es fehlen Systempakete: $liste" "System packages missing: $liste")"
  local antwort=${JARVIS_SYSTEMPAKETE:-}
  [ -n "$antwort" ] || zustimmung antwort "$(t "Jetzt mit sudo installieren? (ja/nein)" "Install them now with sudo? (yes/no)")" "$(t ja yes)" JARVIS_SYSTEMPAKETE
  if ja "$antwort"; then
    local ok=true
    case $pm in
      apt) { sudo apt-get update -qq && sudo apt-get install -y $liste; } || ok=false ;;
      dnf) sudo dnf install -y $liste || ok=false ;;
      pacman) sudo pacman -S --needed --noconfirm $liste || ok=false ;;
    esac
    $ok || hinweis "$(t "Installation mit sudo hat nicht geklappt. Bitte selbst installieren: $liste" "Installing with sudo didn't work. Please install yourself: $liste")"
  else
    hinweis "$(t "Übersprungen. Ohne diese Pakete fehlen Fenster oder Ton; später einfach erneut ausführen." "Skipped. Without these packages the window or sound is missing; just run this again later.")"
  fi
}

desktop_datei() {   # $1 = Pfad, $2 = Zusatzargument (--fenster oder leer)
  mkdir -p "$(dirname "$1")"
  local icon=""; [ -f "$ZIEL/jarvis.png" ] && icon="Icon=$(desktop_wert "$ZIEL/jarvis.png")"
  # Exec-Argumente nach der Desktop-Entry-Spezifikation maskiert (Pfade können Leerzeichen, % oder $ enthalten)
  printf '[Desktop Entry]\nType=Application\nName=J.A.R.V.I.S.\nComment=Home assistant\nComment[de]=Hausassistent\nExec=%s %s%s\nPath=%s\nTerminal=false\nCategories=Utility;\n%s\n' \
    "$(desktop_arg "$PY")" "$(desktop_arg "$ZIEL/jarvis_pc.py")" "${2:+ $2}" "$(desktop_wert "$ZIEL")" "$icon" > "$1.neu"
  chmod 755 "$1.neu"
  mv "$1.neu" "$1"
}

# Client losgeloest starten. Kein "( ... &)": die Unter-Shell hielte sonst die Ausgabe dieses Skripts offen, und wer es
# in einer Pipeline aufruft, wartet ewig (Containertest 25.10.2026). setsid -f gibt es seit util-linux 2.31.
starten() {
  if setsid --help 2>&1 | grep -q -- '--fork'; then
    (cd "$ZIEL" && exec setsid -f "$PY" "$ZIEL/jarvis_pc.py" "$@" >/dev/null 2>&1 < /dev/null)
  else
    (cd "$ZIEL" && exec nohup "$PY" "$ZIEL/jarvis_pc.py" "$@" >/dev/null 2>&1 < /dev/null &) >/dev/null 2>&1
  fi
}

# ------------------------------------------------------------------ Weg 1: mit bestehendem Jarvis verbinden
verbinden() {
  schritt "$(t "Jarvis-Rechner finden" "Finding the Jarvis host")"
  frage JARVIS_ADRESSE "$(t "Adresse des Jarvis-Rechners (z. B. 192.168.1.20)" "Address of the Jarvis host (e.g. 192.168.1.20)")" ""
  [ -n "$JARVIS_ADRESSE" ] || fehler "$(t "Keine Adresse angegeben." "No address given.")"
  local adresse=${JARVIS_ADRESSE%/}
  [[ $adresse == *://* ]] || adresse="http://$adresse"
  # ohne Port: 8770 (Standard der Brücke im Heimnetz)
  if [[ $adresse == http://* ]] && ! [[ ${adresse#http://} =~ :[0-9]+$ ]]; then adresse="$adresse:8770"; fi
  local host=${adresse#*://}; host=${host%:*}
  echo "   $(t Brücke Bridge): $adresse"
  laden "$adresse/v1/gesund" /dev/null || fehler "$(t "Jarvis-Rechner nicht erreichbar. Adresse und Netz prüfen." "Jarvis host not reachable. Check the address and network.")"
  gut "$(t "erreichbar." "reachable.")"

  # Alle Fragen vor den langen Downloads
  frage JARVIS_CODE "$(t "Kopplungscode (leer lassen bei erneuter Einrichtung)" "Pairing code (leave empty when setting up again)")" ""
  frage JARVIS_NAME "$(t "Dein Name (für die Begrüßung, optional)" "Your name (for the greeting, optional)")" ""
  local autostart=false menue=false ohne=false
  if [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    frage JARVIS_OHNE_FENSTER "$(t "Kein Bildschirm erkannt. Jarvis ohne Fenster als Hintergrunddienst betreiben? (ja/nein)" "No screen detected. Run Jarvis without a window as a background service? (yes/no)")" "$(t ja yes)"
  else
    frage JARVIS_OHNE_FENSTER "$(t "Ohne Fenster betreiben (nur Weckwort und Stimme)? (ja/nein)" "Run without a window (wake word and voice only)? (yes/no)")" "$(t nein no)"
  fi
  if ja "$JARVIS_OHNE_FENSTER"; then
    ohne=true
  else
    frage JARVIS_AUTOSTART "$(t "Jarvis bei der Anmeldung starten? (ja/nein)" "Start Jarvis when you sign in? (yes/no)")" "$(t ja yes)"
    frage JARVIS_MENUE "$(t "Eintrag im Anwendungsmenü? (ja/nein)" "Entry in the application menu? (yes/no)")" "$(t ja yes)"
    ja "$JARVIS_AUTOSTART" && autostart=true
    ja "$JARVIS_MENUE" && menue=true
  fi

  mkdir -p "$ZIEL"
  schritt "$(t "Python-Umgebung (eigene Kopie unter $ZIEL, vorhandenes Python bleibt unberührt)" "Python environment (its own copy under $ZIEL, any existing Python stays untouched)")"
  uv_bereit
  export UV_PYTHON_INSTALL_DIR=$ZIEL/python
  [ -x "$PY" ] || "$UV" venv --quiet --python 3.12 "$ZIEL/venv"
  "$PY" --version

  schritt "$(t "Diesen Rechner koppeln" "Pairing this computer")"
  local name; name=$(hostname 2>/dev/null || cat /etc/hostname 2>/dev/null || echo Linux)
  name=${name%%.*}
  # Token, Code und Einstellungen nur über die Standardeingabe, nie in einer Befehlszeile (ps)
  local alt=""
  [ -f "$EINST" ] && alt=$(cat "$EINST")
  local programm
  programm=$(cat <<'PYEOF'
import hashlib, hmac, json, os, secrets, socket, sys, urllib.error, urllib.parse, urllib.request
EN = len(sys.argv) > 2 and sys.argv[2] == "true"


def bruecke_echt(adresse, token):
    """Wie der PC-Client (seit 0.3.0 auch hier): Ein gespeichertes Token geht erst raus, wenn die Gegenstelle mit dem
    Token-Hash beweist, dass sie es kennt. Sonst bekaeme ein fremdes Geraet mit derselben Adresse es geschenkt."""
    if adresse.startswith("https://"):
        return True
    th = hashlib.sha256(token.encode()).hexdigest()
    kennung = hashlib.sha256(("jarvis-kennung:" + th).encode()).hexdigest()[:16]
    nonce = secrets.token_hex(16)
    try:
        d = json.loads(urllib.request.urlopen("%s/v1/gesund?kennung=%s&nonce=%s" % (adresse, kennung, nonce),
                                              timeout=10).read().decode())
    except (urllib.error.URLError, ValueError, OSError):
        return False
    beweis = str(d.get("beweis", "")) if isinstance(d, dict) else ""
    return hmac.compare_digest(beweis, hmac.new(th.encode(), ("jarvis-lan:" + nonce).encode(), hashlib.sha256).hexdigest())


def ip(name):
    try:
        return socket.gethostbyname(name)
    except (OSError, UnicodeError):
        return None


def gueltig(k, v, bruecke):
    """Werte fuer die Einstellungen nur in ihrer erwarteten Form (seit 0.3.0, Sicherheitspruefung): Ports als Zahl,
    Sprache de/en, Adressen per http(s) auf dem Rechner der Bruecke, sonst kurze Texte."""
    if isinstance(v, bool) or v is None:
        return False
    if k in ("ohr_port", "stimme_port"):
        return str(v).isdigit() and 0 < int(v) < 65536
    if k == "sprache":
        return v in ("de", "en")
    if k in ("hud", "dateien"):
        if not isinstance(v, str) or len(v) > 300:
            return False
        u, b = urllib.parse.urlsplit(v), urllib.parse.urlsplit(bruecke)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        eigene = ip(u.hostname)
        return u.hostname == b.hostname or (eigene is not None and eigene == ip(b.hostname))
    return isinstance(v, str) and 0 < len(v.strip()) <= 40
zeilen = sys.stdin.read().split("\n", 6)
adresse, host, code, geraet, name, schalter, alt = zeilen
autostart, menue, ohne = (s == "true" for s in schalter.split())
token = None
try:
    a = json.loads(alt)
except ValueError:
    a = {}
if not isinstance(a, dict):
    a = {}
if a.get("bruecke") == adresse:
    token = a.get("token")
if code.strip():
    req = urllib.request.Request(adresse + "/v1/koppeln", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"code": code.strip().upper(), "name": geraet}).encode())
    try:
        token = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())["token"]
    except urllib.error.HTTPError as e:
        try:
            grund = json.loads(e.read().decode()).get("fehler", "")
        except ValueError:
            grund = ""
        sys.exit(("   Pairing refused (HTTP %d%s)." if EN else "   Kopplung abgelehnt (HTTP %d%s).") % (e.code, ", " + grund if grund else ""))
if not token:
    sys.exit("   No pairing code and no earlier pairing with this Jarvis found." if EN else
             "   Kein Kopplungscode und keine frühere Kopplung mit diesem Jarvis gefunden.")
if not code.strip() and not a.get("ohne_brueckenbeweis") and not bruecke_echt(adresse, token):
    sys.exit("   Something answers at this address that cannot prove it is your Jarvis. The stored token stays here;"
             " check the address and network, or pair again with a code." if EN else
             "   Unter dieser Adresse antwortet etwas, das sich nicht als dein Jarvis ausweist. Das gespeicherte Token"
             " bleibt hier; Adresse und Netz prüfen oder mit einem Code neu koppeln.")
req = urllib.request.Request(adresse + "/v1/zustand", headers={"Authorization": "Bearer " + token})
urllib.request.urlopen(req, timeout=10).read()
# Adressen, Sprache, Stimme und Aussprache vom Jarvis selbst (seit 0.3.0, wie das Windows-Setup); aeltere Bruecken
# kennen /v1/client nicht, dann gelten die Vorgaben des Clients
try:
    req = urllib.request.Request(adresse + "/v1/client", headers={"Authorization": "Bearer " + token})
    c = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
except (urllib.error.URLError, ValueError, OSError):
    c = {}
e = {"nas": host, "bruecke": adresse, "token": token, "schwelle": a.get("schwelle", 0.5), "mikrofon": a.get("mikrofon"),
     "name": name or a.get("name", ""), "autostart": autostart, "desktop_symbol": menue, "desktop_symbol_angelegt": menue,
     "ohne_fenster": ohne}
for k in ("dateien", "hud", "ohr_port", "stimme_port", "sprache", "stimme", "aussprache", "update_github", "auto_update",
          "ohne_brueckenbeweis"):
    if k in a and a.get("bruecke") == adresse:      # nur von derselben Bruecke uebernehmen
        if k in ("update_github", "auto_update", "ohne_brueckenbeweis") or gueltig(k, a[k], adresse):
            e[k] = a[k]
for k in ("dateien", "hud", "ohr_port", "stimme_port", "sprache", "stimme", "aussprache"):
    v = c.get(k) if isinstance(c, dict) else None
    if gueltig(k, v, adresse):
        e[k] = v
pfad = sys.argv[1]
with open(pfad + ".neu", "w", encoding="utf-8") as f:
    json.dump(e, f, ensure_ascii=False, indent=1)
os.chmod(pfad + ".neu", 0o600)
os.replace(pfad + ".neu", pfad)
print(("   Paired. Settings in %s (readable only by your account)." if EN else
       "   Gekoppelt. Einstellungen in %s (nur für dein Konto lesbar).") % pfad)
PYEOF
)
  printf '%s\n%s\n%s\n%s\n%s\n%s\n%s' "$adresse" "$host" "$JARVIS_CODE" "$name" "$JARVIS_NAME" "$autostart $menue $ohne" "$alt" | \
    "$PY" -I -c "$programm" "$EINST" "$EN" || fehler "$(t "Kopplung fehlgeschlagen." "Pairing failed.")"

  schritt "$(t "Pakete (feste Versionen mit Prüfsummen)" "Packages (pinned versions with checksums)")"
  local liste=$HIER/pakete-linux.txt
  [ "$(uname -m)" = aarch64 ] && [ -f "$HIER/pakete-linux-arm.txt" ] && liste=$HIER/pakete-linux-arm.txt
  "$UV" pip install --quiet --python "$PY" --require-hashes -r "$liste"
  "$UV" pip install --quiet --python "$PY" --no-deps --require-hashes -r "$HIER/weckwort.txt"
  gut "$(t "installiert." "installed.")"

  schritt "$(t "Systembibliotheken für Ton und Fenster" "System libraries for sound and window")"
  systempakete

  schritt "$(t "Weckwort-Modell „Hey Jarvis“ (mit Prüfsumme)" "Wake word model “Hey Jarvis” (with checksum)")"
  mkdir -p "$ZIEL/modelle"
  local datei
  for datei in "${!MODELLE[@]}"; do
    local pfad=$ZIEL/modelle/$datei
    if ! { [ -f "$pfad" ] && [ "$(pruefsumme "$pfad")" = "${MODELLE[$datei]}" ]; }; then laden "$MODELL_BASIS$datei" "$pfad"; fi
    [ "$(pruefsumme "$pfad")" = "${MODELLE[$datei]}" ] || { rm -f "$pfad"; fehler "$(t "Prüfsumme von $datei stimmt nicht." "Checksum of $datei doesn't match.")"; }
  done
  gut "$(t "drei Modelle geprüft." "three models checked.")"

  schritt "$(t "Jarvis-Client einrichten" "Setting up the Jarvis client")"
  install -m 644 "$HIER/jarvis_pc.py" "$ZIEL/jarvis_pc.py"
  install -m 644 "$HIER/jarvis.png" "$ZIEL/jarvis.png"
  if $autostart; then desktop_datei "$KONFIG/autostart/jarvis.desktop" ""; else rm -f "$KONFIG/autostart/jarvis.desktop"; fi
  if $menue; then desktop_datei "$ANWENDUNGEN/jarvis.desktop" "--fenster"; else rm -f "$ANWENDUNGEN/jarvis.desktop"; fi
  if $ohne; then
    mkdir -p "$(dirname "$DIENST")"
    printf '[Unit]\nDescription=J.A.R.V.I.S. (%s)\nAfter=network-online.target sound.target\n\n[Service]\nExecStart=%s %s --ohne-fenster\nWorkingDirectory=%s\nRestart=on-failure\nRestartSec=15\n\n[Install]\nWantedBy=default.target\n' \
      "$(t 'ohne Fenster' 'no window')" "$(systemd_arg "$PY")" "$(systemd_arg "$ZIEL/jarvis_pc.py")" "$(systemd_arg "$ZIEL")" > "$DIENST"
    echo "   $(t Hintergrunddienst 'Background service'): $DIENST"
  else
    rm -f "$DIENST"
    echo "   Autostart: $($autostart && t an on || t aus off), $(t Menüeintrag 'menu entry'): $($menue && t ja yes || t nein no) $(t '(umschaltbar im Jarvis-Fenster, Zahnrad)' '(switchable in the Jarvis window, gear)')"
  fi
  "$PY" -I -c 'import sounddevice' 2>/dev/null || hinweis "$(t "Ton fehlt noch (PortAudio). Jarvis geht dann nur über die Texteingabe." "Sound is still missing (PortAudio). Jarvis then only works via text input.")"

  schritt "$(t "Jarvis starten" "Starting Jarvis")"
  if command -v systemctl >/dev/null; then systemctl --user stop jarvis.service 2>/dev/null || true; fi
  client_beenden
  local start=${JARVIS_START:-ja}
  if ! ja "$start"; then
    echo "   $(t 'Start übersprungen (JARVIS_START=nein).' 'Start skipped (JARVIS_START=no).')"
  elif $ohne; then
    if command -v systemctl >/dev/null && systemctl --user daemon-reload 2>/dev/null; then
      systemctl --user enable --now jarvis.service && gut "$(t "läuft als Dienst (systemctl --user status jarvis). Protokoll: $ZIEL/jarvis.log" "running as a service (systemctl --user status jarvis). Log: $ZIEL/jarvis.log")"
      hinweis "$(t 'Damit er auch ohne Anmeldung läuft (nach einem Neustart):' 'To keep it running without a sign-in (after a reboot):') loginctl enable-linger $(id -un)"
    else
      starten --ohne-fenster
      hinweis "$(t "Kein systemd für Benutzer gefunden. Jarvis läuft jetzt, startet nach einem Neustart aber nicht von selbst." "No systemd for users found. Jarvis is running now, but won't start by itself after a reboot.")"
    fi
  elif [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    hinweis "$(t "Keine grafische Sitzung. Jarvis startet bei der nächsten Anmeldung (Autostart) oder über das Menü." "No graphical session. Jarvis starts at your next sign-in (autostart) or from the menu.")"
  else
    starten --begruessung
    gut "$(t "läuft. Protokoll: $ZIEL/jarvis.log" "running. Log: $ZIEL/jarvis.log")"
  fi
  printf '\n   %s%s%s\n' "$GRUEN" "$(t 'FERTIG. Sag „Hey Jarvis“ oder öffne das Jarvis-Fenster.' 'DONE. Say “Hey Jarvis” or open the Jarvis window.')" "$AUS"
}

# ------------------------------------------------------------------ Weg 2: neuen Jarvis mit Claude Code einrichten
neu() {
  local projekt=$HOME/Jarvis
  schritt "$(t "Projektordner anlegen" "Creating the project folder")"
  mkdir -p "$projekt/einrichtung"
  install -m 644 "$HIER/EINRICHTUNG.md" "$projekt/EINRICHTUNG.md"
  install -m 644 "$HIER/EINRICHTUNG.en.md" "$projekt/EINRICHTUNG.en.md"
  local f
  # Erneuter Lauf: Vorlagen, die Claude erweitert haben kann, nicht überschreiben; die neue Fassung kommt als .neu daneben
  for f in jarvis_pc.py jarvis.png hud.html oberflaeche.py verhalten.py test_oberflaeche.py test_verhalten.py app.html \
           jarvis-web.js webapp_bauen.py; do
    if [ -f "$projekt/einrichtung/$f" ] && ! cmp -s "$HIER/$f" "$projekt/einrichtung/$f" && [ "$f" != jarvis_pc.py ]; then
      install -m 644 "$HIER/$f" "$projekt/einrichtung/$f.neu"
      hinweis "$(t "einrichtung/$f behalten (vielleicht angepasst), die neue Vorlage liegt als $f.neu daneben." "kept einrichtung/$f (maybe customized), the new template is next to it as $f.neu.")"
    else
      install -m 644 "$HIER/$f" "$projekt/einrichtung/$f"
    fi
  done
  if [ ! -f "$projekt/CLAUDE.md" ] && $EN; then
    cat > "$projekt/CLAUDE.md" <<'EOF'
# Jarvis project

This folder is this person's home assistant J.A.R.V.I.S., built by Claude Code.

- Build guide and rules: EINRICHTUNG.en.md (read before every change; German original: EINRICHTUNG.md).
- Answers from the setup: antworten.json (on Linux there is no questionnaire, the questions come in the conversation).
  Confirmed profile after round 8: einrichtung/profil.json.
- Secrets live only under geheim/ (permissions 600, never print them, never in Git).
- Always run your own tests with a source test… (test mode).
- Interface: einrichtung/hud.html is the same for everyone. Personal things live only in the bridge settings
  (check module einrichtung/oberflaeche.py, round 6a; setze_sprache("en")). Page updates never overwrite them.
EOF
  fi
  if [ ! -f "$projekt/CLAUDE.md" ]; then
    cat > "$projekt/CLAUDE.md" <<'EOF'
# Jarvis-Projekt

Dieser Ordner ist der Hausassistent J.A.R.V.I.S. dieser Person, gebaut von Claude Code.

- Bauanleitung und Regeln: EINRICHTUNG.md (vor jeder Änderung lesen).
- Antworten aus dem Setup: antworten.json (unter Linux gibt es keinen Fragebogen, die Fragen kommen im Gespräch).
  Bestätigtes Profil nach Runde 8: einrichtung/profil.json.
- Geheimnisse liegen nur unter geheim/ (Rechte 600, nie ausgeben, nie in Git).
- Eigene Proben immer mit einer Quelle test… (Testmodus).
- Oberfläche: einrichtung/hud.html ist für alle gleich. Persönliches steht nur in den Einstellungen der Brücke
  (Prüfmodul einrichtung/oberflaeche.py, Runde 6a). Updates der Seite überschreiben die Einstellungen nie.
EOF
  fi
  echo "   $projekt"

  schritt "$(t "Claude Code (offizieller Installer von claude.ai)" "Claude Code (official installer from claude.ai)")"
  export PATH="$HOME/.local/bin:$PATH"
  if command -v claude >/dev/null; then echo "   $(t 'schon da.' 'already there.')"
  else
    local antwort=${JARVIS_CLAUDE:-}
    [ -n "$antwort" ] || zustimmung antwort "$(t "Claude Code jetzt installieren (curl -fsSL https://claude.ai/install.sh | bash)? (ja/nein)" "Install Claude Code now (curl -fsSL https://claude.ai/install.sh | bash)? (yes/no)")" "$(t ja yes)" JARVIS_CLAUDE
    ja "$antwort" || fehler "$(t "Ohne Claude Code geht es hier nicht weiter. Später erneut mit --neu starten." "Can't go on without Claude Code. Run again later with --neu.")"
    command -v curl >/dev/null || fehler "$(t "Der Installer von Claude Code braucht curl." "The Claude Code installer needs curl.")"
    # Claude Code kommt bewusst aktuell vom offiziellen Installer (Anthropic), nicht festgenagelt
    curl -fsSL https://claude.ai/install.sh | bash
  fi
  claude --version
  printf '\n   %s%s%s\n' "$GRUEN" "$(t 'Gleich startet Claude Code. Beim ersten Start im Browser anmelden und den Ordner bestätigen.' 'Claude Code starts in a moment. On first start, sign in in the browser and confirm the folder.')" "$AUS"
  cd "$projekt"
  # Fester Text, keine Antworten in der Befehlszeile
  if $EN; then exec claude "Read EINRICHTUNG.en.md and guide me through the setup."; fi
  exec claude "Lies EINRICHTUNG.md und fuehre mich durch die Einrichtung."
}

# ------------------------------------------------------------------ Entfernen
entfernen() {
  schritt "$(t "Jarvis-Client entfernen" "Removing the Jarvis client")"
  if [ -f "$DIENST" ] && command -v systemctl >/dev/null; then systemctl --user disable --now jarvis.service 2>/dev/null || true; fi
  client_beenden
  rm -f "$KONFIG/autostart/jarvis.desktop" "$ANWENDUNGEN/jarvis.desktop" "$DIENST"
  case "$ZIEL" in */jarvis) ;; *) fehler "$(t "Unerwarteter Zielordner: $ZIEL" "Unexpected target folder: $ZIEL")" ;; esac
  if [ -d "$ZIEL" ] && ! [ -f "$ZIEL/jarvis_pc.py" ] && ! [ -f "$EINST" ]; then
    hinweis "$(t "$ZIEL sieht nicht nach diesem Installer aus (kein jarvis_pc.py, keine einstellungen.json). Bleibt stehen." "$ZIEL doesn't look like this installer's folder (no jarvis_pc.py, no einstellungen.json). Left in place.")"
  elif [ -d "$ZIEL" ]; then
    local antwort=${JARVIS_ENTFERNEN:-}
    [ -n "$antwort" ] || zustimmung antwort "$(t "Ordner $ZIEL samt Einstellungen und Protokoll löschen? (ja/nein)" "Delete folder $ZIEL with its settings and log? (yes/no)")" "$(t ja yes)" JARVIS_ENTFERNEN
    if ja "$antwort"; then rm -rf -- "$ZIEL"; gut "$(t "gelöscht." "deleted.")"; else echo "   $(t 'Ordner bleibt.' 'Folder stays.')"; fi
  fi
  hinweis "$(t "Auf dem Jarvis-Rechner das Gerät noch widerrufen (Werkzeug geraete.py), dann ist auch das Token ungültig." "Revoke the device on the Jarvis host too (tool geraete.py), then the token is invalid as well.")"
}

printf '\n   %sJ . A . R . V . I . S .   %s%s\n   ------------------------------------\n' "$BLAU" "$(t 'unter Linux' 'on Linux')" "$AUS"
case "${1:-}" in
  --neu) neu ;;
  --entfernen) entfernen ;;
  ""|--verbinden) verbinden ;;
  *) sed -n '2,9p' "$0"; exit 2 ;;
esac
