"""Ablage fuer Dateien im Gespraech (seit 0.3.3, 26.10.2026), Python 3.8 ohne Zusatzpakete.

Eingang: Was eine Person an Jarvis schickt (Foto, PDF, Ton ...), legt die Bruecke hier unter einer Kennung ab, damit
Werkzeuge (Bild bearbeiten, umwandeln, PDF daraus) die Datei erreichen. Ausgabe: Was die Werkzeuge erzeugen, liegt hier,
bis das Geraet es abholt (/v1/datei/<kennung>, nur mit Geraete-Token). Nach der Antwort sammelt die Bruecke alles ein,
was waehrend der Frage fuer diese Quelle entstanden ist (neu_fuer), so haengt nichts davon ab, dass das Gehirn eine
Kennung richtig abschreibt.

Kennungen sind 24 Hexzeichen aus secrets (96 Bit), Dateien 600, Ordner 700. Nach AUFBEWAHRUNG_TAGE weg.
"""
import json
import os
import re
import secrets
import time

AUFBEWAHRUNG_TAGE = 7
MAX_BYTES = 100 * 1024 * 1024      # Originale bis 50 MB (Anhang), Umgewandeltes daraus kann groesser werden
KENNUNG = re.compile(r"^[ab][0-9a-f]{24}$")      # a = Ausgabe, b = Eingang (vom Geraet)


class Fehler(Exception):
    pass


def _ordner(daten):
    o = os.path.join(daten, "ablage")
    if not os.path.isdir(o):
        os.makedirs(o, exist_ok=True)
        os.chmod(o, 0o700)
    return o


def _sauberer_name(name, typ):
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", str(name or "")).strip(" .") or "datei"
    if "." not in name[-6:]:
        name += {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                 "text/plain": ".txt"}.get(typ, "")
    return name[:120]


def ablegen(daten, roh, name, typ, art="ausgabe", quelle="", geraet="", info="", original=""):
    """Datei ablegen, Kennung zurueck. art: ausgabe (fuers Geraet) oder eingang (vom Geraet). original (seit 0.3.3):
    Kennung des unveraenderten Originals, wenn das Geraet die Datei fuer Claude aufbereitet hat."""
    if not isinstance(roh, (bytes, bytearray)) or not roh:
        raise Fehler("leere Datei")
    if len(roh) > MAX_BYTES:
        raise Fehler("Datei zu gross (%d MB, hoechstens %d)" % (len(roh) // 1048576, MAX_BYTES // 1048576))
    o = _ordner(daten)
    k = ("a" if art == "ausgabe" else "b") + secrets.token_hex(12)
    meta = {"kennung": k, "name": _sauberer_name(name, typ), "typ": str(typ or "application/octet-stream")[:80],
            "groesse": len(roh), "art": art, "quelle": str(quelle or "")[:40], "geraet": str(geraet or "")[:80],
            "info": str(info or "")[:300], "erstellt": time.time(), "geliefert": False}
    if original and KENNUNG.match(str(original)):
        meta["original"] = str(original)
    for endung, inhalt in ((".bin", bytes(roh)), (".json", json.dumps(meta, ensure_ascii=False).encode())):
        pfad = os.path.join(o, k + endung)
        fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(inhalt)
        os.replace(pfad + ".neu", pfad)
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


def holen(daten, kennung, art=None):
    """(meta, bytes) oder None. art begrenzt auf ausgabe/eingang."""
    m = meta(daten, kennung)
    if not m or (art and m.get("art") != art):
        return None
    try:
        with open(os.path.join(_ordner(daten), kennung + ".bin"), "rb") as f:
            return m, f.read()
    except OSError:
        return None


def neu_fuer(daten, quelle, seit):
    """Ausgaben dieser Quelle seit dem Zeitpunkt, die noch kein Geraet bekommen hat; markiert sie als geliefert."""
    o = _ordner(daten)
    aus = []
    for n in sorted(os.listdir(o)):
        if not n.endswith(".json") or not n.startswith("a"):
            continue
        m = meta(daten, n[:-5])
        if not m or m.get("geliefert") or m.get("quelle") != quelle or m.get("erstellt", 0) < seit - 1:
            continue
        m["geliefert"] = True
        pfad = os.path.join(o, n)
        with open(pfad + ".neu", "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)
        os.chmod(pfad + ".neu", 0o600)
        os.replace(pfad + ".neu", pfad)
        aus.append((m.get("erstellt", 0), {k: m[k] for k in ("kennung", "name", "typ", "groesse", "info")}))
    return [x for _, x in sorted(aus, key=lambda x: x[0])]


def aufraeumen(daten):
    o = _ordner(daten)
    grenze = time.time() - AUFBEWAHRUNG_TAGE * 86400
    for n in os.listdir(o):
        pfad = os.path.join(o, n)
        try:
            if os.path.getmtime(pfad) < grenze:
                os.remove(pfad)
        except OSError:
            pass
