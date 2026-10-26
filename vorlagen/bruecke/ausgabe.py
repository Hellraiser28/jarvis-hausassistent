"""Ablage fuer Dateien im Gespraech (seit 0.3.3, 26.10.2026), Python 3.8 ohne Zusatzpakete.

Eingang: Was eine Person an Jarvis schickt (Foto, PDF, Ton ...), legt die Bruecke hier unter einer Kennung ab, damit
Werkzeuge (Bild bearbeiten, umwandeln, PDF daraus) die Datei erreichen. Ausgabe: Was die Werkzeuge erzeugen, liegt hier,
bis das Geraet es abholt (/v1/datei/<kennung>).

Seit 0.3.4 (Pruefbericht 0.3.3, Funde 1-3) gehoert jede Datei einem Besitzer (dem Geraet, das gefragt hat: Geraete-ID
oder "haupt") und einer Anfrage. Abholen und Werkzeuge pruefen den Besitzer; die Bruecke sammelt nach der Antwort genau
die Ergebnisse dieser Anfrage ein (neu_fuer). Wer gerade fragt, schreibt die Bruecke vor jeder Frage nach
ablage/aktiv/<pid des Gehirns>.json; der Werkzeug-Server ist ein Kindprozess des Gehirns und liest es ueber os.getppid().

Kennungen sind 24 Hexzeichen aus secrets (96 Bit), Dateien 600, Ordner 700. Nach AUFBEWAHRUNG_TAGE weg.
"""
import json
import os
import re
import secrets
import threading
import time
import unicodedata

AUFBEWAHRUNG_TAGE = 7
MAX_BYTES = 100 * 1024 * 1024      # Originale bis 50 MB (Anhang), Umgewandeltes daraus kann groesser werden
KENNUNG = re.compile(r"^[ab][0-9a-f]{24}$")      # a = Ausgabe, b = Eingang (vom Geraet)
BESITZER = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
WINDOWS_GERAETE = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.I)
# Typen, die beim Abholen so ausgeliefert werden; alles andere als application/octet-stream (Pruefbericht 0.3.3, Fund 12)
AUSLIEFERN = {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/gif", "audio/mpeg", "audio/wav",
              "audio/x-wav", "audio/flac", "audio/ogg", "audio/mp4", "audio/aac", "audio/opus", "video/mp4", "video/webm",
              "text/plain", "text/csv",
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              "application/vnd.openxmlformats-officedocument.presentationml.presentation",
              "application/vnd.oasis.opendocument.text", "application/vnd.oasis.opendocument.spreadsheet",
              "application/vnd.oasis.opendocument.presentation"}
_sperre = threading.Lock()


class Fehler(Exception):
    pass


def _ordner(daten, unter=""):
    o = os.path.join(daten, "ablage", unter) if unter else os.path.join(daten, "ablage")
    if not os.path.isdir(o):
        os.makedirs(o, exist_ok=True)
        os.chmod(o, 0o700)
    return o


def name_bereinigen(name):
    """Ohne Steuer-, Format- und Richtungszeichen (U+202E u. a., Fund 10), ohne Zeichen, die Windows oder Pfade
    stoeren, ohne Windows-Geraetenamen (CON, NUL ...)."""
    name = "".join(c for c in str(name or "") if unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co", "Cn"))
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip(" .")
    if WINDOWS_GERAETE.match(name):
        name = "_" + name
    return name


def _sauberer_name(name, typ):
    name = name_bereinigen(name) or "datei"
    if "." not in name[-6:]:
        name += {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                 "text/plain": ".txt"}.get(typ, "")
    return name[:120]


def ausliefer_typ(typ):
    """Content-Type fuers Abholen: nur bekannte, ungefaehrliche Typen, sonst application/octet-stream."""
    typ = str(typ or "").split(";")[0].strip().lower()
    return typ if typ in AUSLIEFERN else "application/octet-stream"


def _schreiben(pfad, inhalt):
    fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(inhalt)
    os.replace(pfad + ".neu", pfad)


def ablegen(daten, roh, name, typ, art="ausgabe", quelle="", geraet="", info="", original="", besitzer="", anfrage=""):
    """Datei ablegen, Kennung zurueck. art: ausgabe (fuers Geraet) oder eingang (vom Geraet). original (seit 0.3.3):
    Kennung des unveraenderten Originals. besitzer und anfrage (seit 0.3.4): wer gefragt hat und in welcher Anfrage."""
    if not isinstance(roh, (bytes, bytearray)) or not roh:
        raise Fehler("leere Datei")
    if len(roh) > MAX_BYTES:
        raise Fehler("Datei zu gross (%d MB, hoechstens %d)" % (len(roh) // 1048576, MAX_BYTES // 1048576))
    o = _ordner(daten)
    k = ("a" if art == "ausgabe" else "b") + secrets.token_hex(12)
    meta = {"kennung": k, "name": _sauberer_name(name, typ), "typ": str(typ or "application/octet-stream")[:80],
            "groesse": len(roh), "art": art, "quelle": str(quelle or "")[:40], "geraet": str(geraet or "")[:80],
            "info": str(info or "")[:300], "erstellt": time.time(), "geliefert": False,
            "besitzer": str(besitzer) if BESITZER.match(str(besitzer or "")) else "",
            "anfrage": str(anfrage) if BESITZER.match(str(anfrage or "")) else ""}
    if original and KENNUNG.match(str(original)):
        meta["original"] = str(original)
    _schreiben(os.path.join(o, k + ".bin"), bytes(roh))
    _schreiben(os.path.join(o, k + ".json"), json.dumps(meta, ensure_ascii=False).encode())
    aufraeumen(daten)
    return k


def meta(daten, kennung):
    if not KENNUNG.match(str(kennung or "")):
        return None
    try:
        with open(os.path.join(_ordner(daten), kennung + ".json"), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return None
    if time.time() - m.get("erstellt", 0) > AUFBEWAHRUNG_TAGE * 86400:
        return None
    return m


def holen(daten, kennung, art=None, besitzer=None):
    """(meta, bytes) oder None. art begrenzt auf ausgabe/eingang, besitzer (seit 0.3.4) auf das Geraet, das gefragt hat;
    Dateien ohne Besitzer (aus 0.3.3) bekommt dann niemand."""
    m = meta(daten, kennung)
    if not m or (art and m.get("art") != art):
        return None
    if besitzer is not None and (not besitzer or m.get("besitzer", "") != besitzer):
        return None
    try:
        with open(os.path.join(_ordner(daten), kennung + ".bin"), "rb") as f:
            return m, f.read()
    except OSError:
        return None


def neu_fuer(daten, anfrage):
    """Ergebnisse genau dieser Anfrage, die noch kein Geraet bekommen hat; markiert sie als geliefert (unter Sperre)."""
    if not BESITZER.match(str(anfrage or "")):
        return []
    o = _ordner(daten)
    aus = []
    with _sperre:
        for n in sorted(os.listdir(o)):
            if not n.endswith(".json") or not n.startswith("a"):
                continue
            m = meta(daten, n[:-5])
            if not m or m.get("geliefert") or m.get("anfrage") != anfrage:
                continue
            m["geliefert"] = True
            _schreiben(os.path.join(o, n), json.dumps(m, ensure_ascii=False).encode())
            aus.append((m.get("erstellt", 0), {k: m[k] for k in ("kennung", "name", "typ", "groesse", "info")}))
    return [x for _, x in sorted(aus, key=lambda x: x[0])]


def aktiv_schreiben(daten, pid, besitzer, anfrage):
    """Vor jeder Frage: wer fragt, fuer den Werkzeug-Server dieses Gehirns (Kindprozess, liest per os.getppid())."""
    _schreiben(os.path.join(_ordner(daten, "aktiv"), "%d.json" % int(pid)),
               json.dumps({"besitzer": besitzer, "anfrage": anfrage, "zeit": time.time()}).encode())


def aktiv_lesen(daten, pid):
    """(besitzer, anfrage) der laufenden Frage dieses Gehirns, sonst ("", "")."""
    try:
        with open(os.path.join(daten, "ablage", "aktiv", "%d.json" % int(pid)), encoding="utf-8") as f:
            a = json.load(f)
    except (OSError, ValueError, TypeError):
        return "", ""
    b, q = str(a.get("besitzer") or ""), str(a.get("anfrage") or "")
    return (b, q) if BESITZER.match(b) and BESITZER.match(q) else ("", "")


def aufraeumen(daten):
    o = _ordner(daten)
    grenze = time.time() - AUFBEWAHRUNG_TAGE * 86400
    for n in os.listdir(o):
        pfad = os.path.join(o, n)
        try:
            if os.path.isfile(pfad) and os.path.getmtime(pfad) < grenze:
                os.remove(pfad)
        except OSError:
            pass
    a = os.path.join(o, "aktiv")            # Angaben zu laengst beendeten Gehirnen
    if os.path.isdir(a):
        for n in os.listdir(a):
            try:
                if os.path.getmtime(os.path.join(a, n)) < time.time() - 86400:
                    os.remove(os.path.join(a, n))
            except OSError:
                pass
