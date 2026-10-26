"""Bilder veraendern und erzeugen (seit 0.3.3, 26.10.2026), Python 3.8 ohne Zusatzpakete.

Claude selbst gibt nur Text aus; Bilder kommen von einem Anbieter, den das Setup waehlt:
- cloudflare: Workers AI, 10.000 Neurons je Tag gratis (Cloudflare-Preisseite, Stand Oktober 2026). FLUX.2 klein 4B
  fuer einfache Aenderungen (Farben, Himmel, Stil, Einfaerben; ~70 je Tag), klein 9B fuer Entfernen, Schrift und
  Umgestalten (~6 je Tag). Getestet am 26.10. mit 10 Aufgaben (Doku Kap. 13.17). Multipart-Felder laut Cloudflare-
  Changelog: prompt, input_image_0..3, width, height.
- gemini: Gemini-Bildmodell ueber die API, nur mit bezahltem Kontingent (das kostenlose hat fuer Bilder Limit 0,
  gemessen am 26.10.: HTTP 429). Etwa 3-7 Cent je Bild laut Google-Preisseite.
- openai: Images API (/v1/images/generations und /v1/images/edits), kostenpflichtig, kein Gratis-Kontingent. Standard
  gpt-image-2.5-flare (laut OpenAI das schnelle Modell fuer den Alltag), "genau" nimmt gpt-image-2.5-sunburst (fuer
  praezise Bearbeitungen). Beide 30 $ je Million Bild-Ausgabetoken, die Tokenzahl je Bild haengt von Qualitaet und
  Groesse ab. OpenAI verlangt fuer GPT-Image-Modelle unter Umstaenden eine Organisations-Verifizierung. Groessen nur
  aus der Standardliste (1024x1024, 1536x1024, 1024x1536, auto), die koennen alle GPT-Image-Modelle.
Der Tageszaehler (daten/bild_zaehler.json) schaetzt die Neurons nach Cloudflares Preisliste und bleibt unter dem Limit;
fuer 9B zu wenig uebrig -> 4B mit Hinweis. Seit 0.3.4 (Pruefbericht 0.3.3, Fund 7) unter Dateisperre mit Reservierung
vor dem Aufruf, dazu ein Tageslimit fuer bezahlte Bilder (OpenAI, Gemini).
"""
import base64
import binascii
import contextlib
import json
import math
import os
import re
import struct
import time
import urllib.error
import urllib.request
import uuid

CF_4B = "@cf/black-forest-labs/flux-2-klein-4b"
CF_9B = "@cf/black-forest-labs/flux-2-klein-9b"
GEMINI_MODELL = "gemini-3.1-flash-image"
OPENAI_MODELL, OPENAI_GENAU = "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"
OPENAI_GROESSE = {"quadrat": "1024x1024", "quer": "1536x1024", "hoch": "1024x1536"}


class Fehler(Exception):
    pass


def groesse(roh):
    """(Breite, Hoehe) aus JPEG/PNG/WebP-Kopf, sonst None."""
    try:
        if roh[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", roh[16:24])
        if roh[:4] == b"RIFF" and roh[8:12] == b"WEBP":
            if roh[12:16] == b"VP8X":
                return 1 + int.from_bytes(roh[24:27], "little"), 1 + int.from_bytes(roh[27:30], "little")
            if roh[12:16] == b"VP8 ":
                return struct.unpack("<HH", roh[26:30])[0] & 0x3FFF, struct.unpack("<HH", roh[26:30])[1] & 0x3FFF
        if roh[:3] == b"\xff\xd8\xff":
            i = 2
            while i + 9 < len(roh):
                if roh[i] != 0xFF:
                    i += 1
                    continue
                m = roh[i + 1]
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", roh[i + 5:i + 9])
                    return w, h
                i += 2 + struct.unpack(">H", roh[i + 2:i + 4])[0]
    except (struct.error, IndexError):
        pass
    return None


def ausgabe_masse(w, h, lang=1024):
    """Laengste Seite 1024, Vielfache von 16, mindestens 256."""
    if not w or not h:
        return lang, lang
    s = lang / float(max(w, h))
    return max(256, int(round(w * s / 16)) * 16), max(256, int(round(h * s / 16)) * 16)


def neurons(modell, ein, aus):
    """Schaetzung nach Cloudflares Preisliste (Neurons je 512er-Kachel bzw. Megapixel)."""
    kacheln = lambda m: math.ceil(m[0] / 512.0) * math.ceil(m[1] / 512.0) if m else 0
    if modell == CF_9B:
        mp_aus = aus[0] * aus[1] / 1048576.0
        return 1363.64 + max(0.0, mp_aus - 1) * 181.82 + ((ein[0] * ein[1] / 1048576.0) * 181.82 if ein else 0)
    return kacheln(ein) * 5.37 + kacheln(aus) * 26.05


def _tag_utc():
    return time.strftime("%Y-%m-%d", time.gmtime())


# ------------------------------------------------------------------ Tageszaehler (seit 0.3.4 unter Sperre, Fund 7)
# Mehrere Werkzeug-Server (einer je Gehirn) buchen gleichzeitig: Pruefen und Reservieren passieren unter einer
# Dateisperre, VOR dem Aufruf. Schlaegt der Aufruf fehl, wird die Reservierung zurueckgebucht.

@contextlib.contextmanager
def _gesperrt(daten):
    fd = os.open(os.path.join(daten, "bild_zaehler.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        except ImportError:                 # Windows
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        yield
    finally:
        os.close(fd)


def _zaehler(daten):
    try:
        with open(os.path.join(daten, "bild_zaehler.json"), encoding="utf-8") as f:
            z = json.load(f)
    except (OSError, ValueError):
        z = {}
    if z.get("tag") != _tag_utc():
        z = {"tag": _tag_utc(), "neurons": 0.0, "bilder": 0, "bezahlt": 0}
    z.setdefault("bezahlt", 0)
    return z


def _buchen(daten, neurons=0.0, bezahlt=0, bilder=0, grenze_neurons=None, grenze_bezahlt=None):
    """Unter Sperre pruefen und buchen. False, wenn eine Grenze ueberschritten wuerde (dann bleibt alles, wie es war)."""
    pfad = os.path.join(daten, "bild_zaehler.json")
    with _gesperrt(daten):
        z = _zaehler(daten)
        if grenze_neurons is not None and z.get("neurons", 0) + neurons > grenze_neurons:
            return False
        if grenze_bezahlt is not None and z.get("bezahlt", 0) + bezahlt > grenze_bezahlt:
            return False
        z["neurons"] = round(max(0.0, z.get("neurons", 0) + neurons), 1)
        z["bezahlt"] = max(0, z.get("bezahlt", 0) + bezahlt)
        z["bilder"] = max(0, z.get("bilder", 0) + bilder)
        with open(pfad + ".neu", "w", encoding="utf-8") as f:
            json.dump(z, f)
        os.chmod(pfad + ".neu", 0o600)
        os.replace(pfad + ".neu", pfad)
        return True


def _wieder_ab():
    """Ortszeit, zu der Cloudflare das Tageskontingent zuruecksetzt (00:00 UTC)."""
    morgen = (int(time.time()) // 86400 + 1) * 86400
    return time.strftime("%H:%M", time.localtime(morgen))


def stand(daten, cfg):
    z = _zaehler(daten)
    return {"tag": z["tag"], "neurons": z.get("neurons", 0), "bilder": z.get("bilder", 0), "bezahlt": z.get("bezahlt", 0),
            "limit": cfg.get("tageslimit", 9000), "limit_bezahlt": cfg.get("bezahlt_limit", 20), "wieder_ab": _wieder_ab()}


# ------------------------------------------------------------------ Netz (seit 0.3.4, Fund 14)

class _KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nicht verfolgen: urllib nimmt die Authorization-Kopfzeile sonst zu einem anderen Host mit."""

    def redirect_request(self, *a, **k):
        return None


_OEFFNER = urllib.request.build_opener(_KeineWeiterleitung)
LESEN_MAX = 40 * 1024 * 1024


def _json_holen(req, timeout):
    with _OEFFNER.open(req, timeout=timeout) as r:
        roh = r.read(LESEN_MAX + 1)
    if len(roh) > LESEN_MAX:
        raise Fehler("Die Antwort des Bilddienstes ist zu gross.")
    return json.loads(roh.decode("utf-8", "replace"))


def _fehlertext(e, feld):
    """Fehlertext des Dienstes, nur zum Erkennen bekannter Faelle; ans Gehirn geht er nicht (fremder Text)."""
    try:
        d = json.loads(e.read(65536).decode("utf-8", "replace"))
    except Exception:
        return ""
    if feld == "errors":
        return "; ".join(str(x.get("message")) for x in d.get("errors", []) if isinstance(x, dict))[:300]
    return str((d.get("error") or {}).get("message") or "")[:300]


def _b64(text):
    try:
        return base64.b64decode(re.sub(r"\s+", "", str(text or "")), validate=True)
    except (ValueError, binascii.Error):
        raise Fehler("Der Bilddienst hat kein gueltiges Bild geliefert.")


def _formular(felder, dateien):
    g = uuid.uuid4().hex
    teile = []
    for k, v in felder.items():
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (g, k, v)).encode("utf-8"))
    for k, (name, typ, roh) in dateien.items():
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                      % (g, k, name, typ)).encode() + roh + b"\r\n")
    teile.append(("--%s--\r\n" % g).encode())
    return b"".join(teile), "multipart/form-data; boundary=" + g


def _cloudflare(cfg, daten, auftrag, bild=None, typ="image/jpeg", genau=False, masse=None):
    if not cfg.get("cf_konto") or not cfg.get("cf_token"):
        raise Fehler("Cloudflare ist nicht eingerichtet (Konto-ID und Token fehlen).")
    ein = groesse(bild) if bild else None
    aus = masse or (ausgabe_masse(*ein) if ein else (1024, 1024))
    limit = cfg.get("tageslimit", 9000)
    modell, hinweis = (CF_9B if genau else CF_4B), ""
    kosten = neurons(modell, ein, aus)
    if not _buchen(daten, neurons=kosten, grenze_neurons=limit):       # reservieren, bevor der Aufruf rausgeht
        if modell != CF_9B:
            raise Fehler("Das Gratis-Kontingent für Bilder ist für heute aufgebraucht, ab %s Uhr geht es wieder." % _wieder_ab())
        modell, hinweis = CF_4B, "Für das genauere Modell reicht das Gratis-Kontingent heute nicht mehr, deshalb das schnellere."
        kosten = neurons(modell, ein, aus)
        if not _buchen(daten, neurons=kosten, grenze_neurons=limit):
            raise Fehler("Das Gratis-Kontingent für Bilder ist für heute aufgebraucht, ab %s Uhr geht es wieder." % _wieder_ab())
    try:
        felder = {"prompt": auftrag[:2000], "width": str(aus[0]), "height": str(aus[1])}
        dateien = {"input_image_0": ("bild", typ, bild)} if bild else {}
        koerper, art = _formular(felder, dateien)
        req = urllib.request.Request("https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s" % (cfg["cf_konto"], modell),
                                     data=koerper, headers={"Authorization": "Bearer " + cfg["cf_token"], "Content-Type": art})
        try:
            d = _json_holen(req, 100)
        except urllib.error.HTTPError as e:
            meld = _fehlertext(e, "errors").lower()
            if e.code == 429 or "neuron" in meld or "limit" in meld:
                raise Fehler("Cloudflare meldet: Tageskontingent erreicht, ab %s Uhr geht es wieder." % _wieder_ab())
            if e.code in (401, 403):
                raise Fehler("Cloudflare lehnt den Zugang ab (%d)." % e.code)
            raise Fehler("Cloudflare: HTTP %d" % e.code)
        except OSError as e:
            raise Fehler("Cloudflare nicht erreichbar (%s)." % type(e).__name__)
        roh = _b64((d.get("result") or {}).get("image"))
        if not roh:
            raise Fehler("Cloudflare hat kein Bild geliefert.")
    except Fehler:
        _buchen(daten, neurons=-kosten)          # Reservierung zurueck
        raise
    _buchen(daten, bilder=1)
    return roh, ("image/png" if roh[:4] == b"\x89PNG" else "image/jpeg"), {
        "modell": modell.split("/")[-1], "hinweis": hinweis, "neurons": round(kosten)}


def _gemini(cfg, auftrag, bild=None, typ="image/jpeg", seitenverhaeltnis=None):
    if not cfg.get("gemini_schluessel"):
        raise Fehler("Für Bilder über Gemini fehlt der Schlüssel.")
    teile = ([{"inlineData": {"mimeType": typ, "data": base64.b64encode(bild).decode()}}] if bild else []) + \
        [{"text": auftrag[:4000]}]
    bild_cfg = {"imageSize": "1K"}
    if seitenverhaeltnis and not bild:
        bild_cfg["aspectRatio"] = seitenverhaeltnis
    koerper = {"contents": [{"parts": teile}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": bild_cfg}}
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % GEMINI_MODELL,
                                 data=json.dumps(koerper).encode(),
                                 headers={"x-goog-api-key": cfg["gemini_schluessel"], "Content-Type": "application/json"})
    try:
        d = _json_holen(req, 100)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise Fehler("Gemini lehnt Bilder ab: Kontingent erschöpft oder kein bezahltes Kontingent (429).")
        raise Fehler("Gemini: HTTP %d" % e.code)
    except OSError as e:
        raise Fehler("Gemini nicht erreichbar (%s)." % type(e).__name__)
    for teil in ((d.get("candidates") or [{}])[0].get("content") or {}).get("parts", []):
        if "inlineData" in teil:
            typ_aus = str(teil["inlineData"].get("mimeType") or "")
            return _b64(teil["inlineData"].get("data")), typ_aus if typ_aus in ("image/png", "image/jpeg", "image/webp") \
                else "image/png", {"modell": GEMINI_MODELL, "hinweis": "", "neurons": 0}
    grund = str((d.get("candidates") or [{}])[0].get("finishReason") or "")
    raise Fehler("Gemini hat kein Bild geliefert%s." % ((" (%s)" % grund) if re.fullmatch(r"[A-Z_]{1,40}", grund) else ""))


def _openai(cfg, auftrag, bild=None, typ="image/jpeg", genau=False, format=None):
    if not cfg.get("openai_schluessel"):
        raise Fehler("Für Bilder über OpenAI fehlt der Schlüssel.")
    modell = cfg.get("openai_modell_genau" if genau else "openai_modell") or (OPENAI_GENAU if genau else OPENAI_MODELL)
    ausgabe = "png" if typ == "image/png" else "jpeg"
    felder = {"model": modell, "prompt": auftrag[:4000], "quality": cfg.get("openai_qualitaet") or "medium",
              "output_format": ausgabe}
    if bild:
        felder["size"] = "auto"
        endung = {"image/png": "png", "image/webp": "webp"}.get(typ, "jpg")
        koerper, art = _formular(felder, {"image": ("bild." + endung, typ, bild)})
        adresse = "https://api.openai.com/v1/images/edits"
    else:
        felder["size"] = OPENAI_GROESSE.get(format or "quadrat", "1024x1024")
        koerper, art = json.dumps(felder).encode(), "application/json"
        adresse = "https://api.openai.com/v1/images/generations"
    req = urllib.request.Request(adresse, data=koerper,
                                 headers={"Authorization": "Bearer " + cfg["openai_schluessel"], "Content-Type": art})
    try:
        d = _json_holen(req, 180)
    except urllib.error.HTTPError as e:
        meld = _fehlertext(e, "error").lower()
        if e.code == 401:
            raise Fehler("OpenAI lehnt den Schlüssel ab (401).")
        if e.code == 429:
            raise Fehler("OpenAI meldet: Limit oder Guthaben erschöpft (429).")
        if e.code == 403 and "verif" in meld:
            raise Fehler("OpenAI verlangt für Bildmodelle eine Verifizierung der Organisation (Entwicklerkonsole, "
                         "Einstellungen, Organisation).")
        if e.code == 400 and ("safety" in meld or "moderation" in meld):
            raise Fehler("OpenAI hat den Auftrag abgelehnt (Inhaltsrichtlinie).")
        raise Fehler("OpenAI: HTTP %d" % e.code)
    except OSError as e:
        raise Fehler("OpenAI nicht erreichbar (%s)." % type(e).__name__)
    roh = _b64(((d.get("data") or [{}])[0] or {}).get("b64_json"))
    if not roh:
        raise Fehler("OpenAI hat kein Bild geliefert.")
    nutzung = d.get("usage") or {}
    return roh, ("image/png" if roh[:4] == b"\x89PNG" else "image/jpeg"), {
        "modell": modell, "hinweis": "", "neurons": 0, "token": nutzung.get("output_tokens") or 0}


def _bezahlt(cfg, daten, aufruf):
    """OpenAI und Gemini kosten je Bild: Tageslimit (BILD_TAGESLIMIT_BEZAHLT, Standard 20), reserviert vor dem Aufruf."""
    if not _buchen(daten, bezahlt=1, grenze_bezahlt=cfg.get("bezahlt_limit", 20)):
        raise Fehler("Heute sind schon %d bezahlte Bilder entstanden, das ist die eingestellte Grenze "
                     "(BILD_TAGESLIMIT_BEZAHLT). Morgen geht es wieder." % cfg.get("bezahlt_limit", 20))
    try:
        erg = aufruf()
    except Fehler:
        _buchen(daten, bezahlt=-1)
        raise
    _buchen(daten, bilder=1)
    return erg


def bearbeiten(cfg, daten, bild, typ, auftrag, genau=False):
    """Bild nach Auftrag (englisch formuliert) veraendern -> (Bytes, MIME, Info)."""
    if cfg.get("dienst") == "cloudflare":
        return _cloudflare(cfg, daten, auftrag, bild, typ, genau)
    if cfg.get("dienst") == "gemini":
        return _bezahlt(cfg, daten, lambda: _gemini(cfg, auftrag, bild, typ))
    if cfg.get("dienst") == "openai":
        return _bezahlt(cfg, daten, lambda: _openai(cfg, auftrag, bild, typ, genau))
    raise Fehler("Bilder bearbeiten ist nicht eingerichtet.")


FORMATE = {"quadrat": ((1024, 1024), "1:1"), "quer": ((1024, 576), "16:9"), "hoch": ((576, 1024), "9:16")}


def erzeugen(cfg, daten, beschreibung, format="quadrat", genau=False):
    """Neues Bild aus einer (englischen) Beschreibung -> (Bytes, MIME, Info)."""
    masse, verhaeltnis = FORMATE.get(format, FORMATE["quadrat"])
    if cfg.get("dienst") == "cloudflare":
        return _cloudflare(cfg, daten, beschreibung, None, genau=genau, masse=masse)
    if cfg.get("dienst") == "gemini":
        return _bezahlt(cfg, daten, lambda: _gemini(cfg, beschreibung, None, seitenverhaeltnis=verhaeltnis))
    if cfg.get("dienst") == "openai":
        return _bezahlt(cfg, daten, lambda: _openai(cfg, beschreibung, None, genau=genau, format=format))
    raise Fehler("Bilder erzeugen ist nicht eingerichtet.")
