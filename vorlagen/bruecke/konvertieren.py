"""Dateien umwandeln ueber Transmute (seit 0.3.3, 26.10.2026), Python 3.8 ohne Zusatzpakete.

Transmute (selbst gehostet, API v2): Datei hochladen -> Transmute nennt die moeglichen Zielformate -> Umwandlung
anfordern (die Antwort beschreibt die fertige Datei) -> herunterladen -> beide Dateien dort wieder loeschen. Gemessen
am 26.10.: PNG nach JPG in 2,2 s. Kann u. a. OCR (PDF -> durchsuchbares PDF/A), PDF -> Word, Markdown/HTML/Word ->
PDF, Office ueber LibreOffice, Audio/Video ueber FFmpeg, E-Mails, E-Books.
"""
import json
import mimetypes
import urllib.error
import urllib.request
import uuid

ZEIT = 110          # Werkzeuge haben 120 s (MCP_TOOL_TIMEOUT), lange Videos gehen nicht in einem Zug


# Gleiche Formate, verschieden geschrieben (Transmute fuehrt z. B. "jpeg", Menschen sagen "jpg")
GLEICH = {"jpg": ("jpeg",), "jpeg": ("jpg",), "tif": ("tiff",), "tiff": ("tif",), "htm": ("html",), "html": ("htm",),
          "yml": ("yaml",), "yaml": ("yml",), "markdown": ("md",), "md": ("markdown",), "word": ("docx",),
          "excel": ("xlsx",), "powerpoint": ("pptx",), "text": ("txt",), "pdfa": ("pdf/a",)}


class Fehler(Exception):
    pass


def _anfrage(cfg, methode, pfad, daten=None, art="application/json", zeit=ZEIT):
    if not cfg.get("adresse") or not cfg.get("schluessel"):
        raise Fehler("Umwandeln ist nicht eingerichtet (Transmute-Adresse und -Schlüssel fehlen).")
    kopf = {"Authorization": "Bearer " + cfg["schluessel"]}
    if daten is not None:
        kopf["Content-Type"] = art
    req = urllib.request.Request(cfg["adresse"] + pfad, data=daten, headers=kopf, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=zeit) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        try:
            grund = json.loads(e.read().decode()).get("detail")
        except Exception:
            grund = None
        if e.code == 401:
            raise Fehler("Transmute lehnt den Schlüssel ab (401).")
        raise Fehler("Transmute: HTTP %d%s" % (e.code, (" – %s" % str(grund)[:200]) if grund else ""))
    except OSError as e:
        raise Fehler("Transmute nicht erreichbar (%s)." % type(e).__name__)


def _hochladen(cfg, roh, name, typ):
    g = uuid.uuid4().hex
    name = str(name or "datei").replace('"', "")
    koerper = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                % (g, name, typ or "application/octet-stream")).encode() + roh + ("\r\n--%s--\r\n" % g).encode())
    return json.loads(_anfrage(cfg, "POST", "/api/files", koerper, "multipart/form-data; boundary=" + g))["metadata"]


def _weg(cfg, pfad):
    try:
        _anfrage(cfg, "DELETE", pfad, zeit=15)
    except Fehler:
        pass


# Qualitaetsstufen, wie Transmute sie nennt (backend/converters/ffmpeg_convert.py, gelesen am 26.10.2026): Audio
# high/medium/low = 320/192/96 kbit/s (AC-3 448/256/128), Video CRF 18/23/28. Deutsche Woerter dazu.
QUALITAET = {"hoch": "high", "beste": "high", "gut": "high", "mittel": "medium", "normal": "medium",
             "niedrig": "low", "klein": "low", "gering": "low"}


def formate(cfg, roh, name, typ, mit_qualitaet=False):
    """Moegliche Zielformate fuer diese Datei (laedt hoch, liest, loescht). mit_qualitaet: {format: [stufen]}."""
    m = _hochladen(cfg, roh, name, typ)
    try:
        f = m.get("compatible_formats") or {}
        return {k: list(v or []) for k, v in sorted(f.items())} if mit_qualitaet else sorted(f.keys())
    finally:
        _weg(cfg, "/api/files/" + m["id"])


def umwandeln(cfg, roh, name, typ, ziel, qualitaet=None):
    """-> (Bytes, Dateiname, MIME-Typ). ziel z. B. pdf, docx, jpg, mp3, pdf/a."""
    ziel = str(ziel or "").strip().lower().lstrip(".")
    m = _hochladen(cfg, roh, name, typ)
    erg = None
    try:
        moeglich = m.get("compatible_formats") or {}
        if ziel not in moeglich:
            ziel = next((a for a in GLEICH.get(ziel, ()) if a in moeglich), ziel)   # jpg/jpeg, tif/tiff ...
        if ziel not in moeglich:
            raise Fehler("Nach %s kann Transmute diese Datei nicht umwandeln. Möglich: %s" % (
                ziel, ", ".join(sorted(moeglich)[:40]) or "nichts"))
        anf = {"id": m["id"], "output_format": ziel}
        if qualitaet:       # seit 0.3.3: eine Stufe, die es nicht gibt, nicht still uebergehen
            q = QUALITAET.get(str(qualitaet).strip().lower(), str(qualitaet).strip().lower())
            stufen = moeglich.get(ziel) or []
            if q not in stufen:
                raise Fehler("Qualität „%s“ gibt es für %s nicht. %s" % (qualitaet, ziel, (
                    "Möglich: " + ", ".join(stufen)) if stufen else "Für dieses Format gibt es keine Stufen."))
            anf["quality"] = q
        erg = json.loads(_anfrage(cfg, "POST", "/api/conversions", json.dumps(anf).encode()))
        daten = _anfrage(cfg, "GET", "/api/files/" + erg["id"])
        if not daten:
            raise Fehler("Transmute hat eine leere Datei geliefert.")
        endung = (erg.get("extension") or "." + ziel.split("/")[0]).lstrip(".")
        stamm = str(name or "datei").rsplit(".", 1)[0]
        typ_aus = mimetypes.guess_type("x." + endung)[0] or "application/octet-stream"
        return daten, "%s.%s" % (stamm, endung), typ_aus
    finally:
        if erg:
            _weg(cfg, "/api/conversions/" + erg["id"])
        _weg(cfg, "/api/files/" + m["id"])
