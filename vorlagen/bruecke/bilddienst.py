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
fuer 9B zu wenig uebrig -> 4B mit Hinweis.
"""
import base64
import json
import math
import os
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


def _zaehler(daten, plus=0.0):
    pfad = os.path.join(daten, "bild_zaehler.json")
    try:
        with open(pfad, encoding="utf-8") as f:
            z = json.load(f)
    except (OSError, ValueError):
        z = {}
    if z.get("tag") != _tag_utc():
        z = {"tag": _tag_utc(), "neurons": 0.0, "bilder": 0}
    if plus:
        z["neurons"] = round(z.get("neurons", 0) + plus, 1)
        z["bilder"] = z.get("bilder", 0) + 1
        with open(pfad + ".neu", "w", encoding="utf-8") as f:
            json.dump(z, f)
        os.chmod(pfad + ".neu", 0o600)
        os.replace(pfad + ".neu", pfad)
    return z


def _wieder_ab():
    """Ortszeit, zu der Cloudflare das Tageskontingent zuruecksetzt (00:00 UTC)."""
    morgen = (int(time.time()) // 86400 + 1) * 86400
    return time.strftime("%H:%M", time.localtime(morgen))


def stand(daten, cfg):
    z = _zaehler(daten)
    return {"tag": z["tag"], "neurons": z.get("neurons", 0), "bilder": z.get("bilder", 0),
            "limit": cfg.get("tageslimit", 9000), "wieder_ab": _wieder_ab()}


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
    z = _zaehler(daten)
    frei = cfg.get("tageslimit", 9000) - z.get("neurons", 0)
    modell, hinweis = (CF_9B if genau else CF_4B), ""
    if modell == CF_9B and neurons(CF_9B, ein, aus) > frei:
        modell, hinweis = CF_4B, "Für das genauere Modell reicht das Gratis-Kontingent heute nicht mehr, deshalb das schnellere."
    kosten = neurons(modell, ein, aus)
    if kosten > frei:
        raise Fehler("Das Gratis-Kontingent für Bilder ist für heute aufgebraucht, ab %s Uhr geht es wieder." % _wieder_ab())
    felder = {"prompt": auftrag[:2000], "width": str(aus[0]), "height": str(aus[1])}
    dateien = {"input_image_0": ("bild", typ, bild)} if bild else {}
    koerper, art = _formular(felder, dateien)
    req = urllib.request.Request("https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s" % (cfg["cf_konto"], modell),
                                 data=koerper, headers={"Authorization": "Bearer " + cfg["cf_token"], "Content-Type": art})
    try:
        with urllib.request.urlopen(req, timeout=100) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            meld = "; ".join(str(x.get("message")) for x in json.loads(e.read().decode()).get("errors", []))[:200]
        except Exception:
            meld = ""
        if e.code == 429 or "neuron" in meld.lower() or "limit" in meld.lower():
            raise Fehler("Cloudflare meldet: Tageskontingent erreicht, ab %s Uhr geht es wieder." % _wieder_ab())
        if e.code in (401, 403):
            raise Fehler("Cloudflare lehnt den Zugang ab (%d)." % e.code)
        raise Fehler("Cloudflare: HTTP %d %s" % (e.code, meld))
    except OSError as e:
        raise Fehler("Cloudflare nicht erreichbar (%s)." % type(e).__name__)
    b64 = (d.get("result") or {}).get("image")
    if not b64:
        raise Fehler("Cloudflare hat kein Bild geliefert.")
    roh = base64.b64decode(b64)
    _zaehler(daten, kosten)
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
        with urllib.request.urlopen(req, timeout=100) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise Fehler("Gemini lehnt Bilder ab: Kontingent erschöpft oder kein bezahltes Kontingent (429).")
        raise Fehler("Gemini: HTTP %d" % e.code)
    except OSError as e:
        raise Fehler("Gemini nicht erreichbar (%s)." % type(e).__name__)
    for teil in ((d.get("candidates") or [{}])[0].get("content") or {}).get("parts", []):
        if "inlineData" in teil:
            return base64.b64decode(teil["inlineData"]["data"]), teil["inlineData"].get("mimeType", "image/png"), {
                "modell": GEMINI_MODELL, "hinweis": "", "neurons": 0}
    raise Fehler("Gemini hat kein Bild geliefert (%s)." % ((d.get("candidates") or [{}])[0].get("finishReason") or "ohne Grund"))


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
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            meld = str((json.loads(e.read().decode()).get("error") or {}).get("message") or "")[:200]
        except Exception:
            meld = ""
        if e.code == 401:
            raise Fehler("OpenAI lehnt den Schlüssel ab (401).")
        if e.code == 429:
            raise Fehler("OpenAI meldet: Limit oder Guthaben erschöpft (429).")
        if e.code == 403 and "verif" in meld.lower():
            raise Fehler("OpenAI verlangt für Bildmodelle eine Verifizierung der Organisation (Entwicklerkonsole, "
                         "Einstellungen, Organisation).")
        raise Fehler("OpenAI: HTTP %d %s" % (e.code, meld))
    except OSError as e:
        raise Fehler("OpenAI nicht erreichbar (%s)." % type(e).__name__)
    b64 = ((d.get("data") or [{}])[0] or {}).get("b64_json")
    if not b64:
        raise Fehler("OpenAI hat kein Bild geliefert.")
    roh = base64.b64decode(b64)
    nutzung = d.get("usage") or {}
    return roh, ("image/png" if roh[:4] == b"\x89PNG" else "image/jpeg"), {
        "modell": modell, "hinweis": "", "neurons": 0, "token": nutzung.get("output_tokens") or 0}


def bearbeiten(cfg, daten, bild, typ, auftrag, genau=False):
    """Bild nach Auftrag (englisch formuliert) veraendern -> (Bytes, MIME, Info)."""
    if cfg.get("dienst") == "cloudflare":
        return _cloudflare(cfg, daten, auftrag, bild, typ, genau)
    if cfg.get("dienst") == "gemini":
        return _gemini(cfg, auftrag, bild, typ)
    if cfg.get("dienst") == "openai":
        return _openai(cfg, auftrag, bild, typ, genau)
    raise Fehler("Bilder bearbeiten ist nicht eingerichtet.")


FORMATE = {"quadrat": ((1024, 1024), "1:1"), "quer": ((1024, 576), "16:9"), "hoch": ((576, 1024), "9:16")}


def erzeugen(cfg, daten, beschreibung, format="quadrat", genau=False):
    """Neues Bild aus einer (englischen) Beschreibung -> (Bytes, MIME, Info)."""
    masse, verhaeltnis = FORMATE.get(format, FORMATE["quadrat"])
    if cfg.get("dienst") == "cloudflare":
        return _cloudflare(cfg, daten, beschreibung, None, genau=genau, masse=masse)
    if cfg.get("dienst") == "gemini":
        return _gemini(cfg, beschreibung, None, seitenverhaeltnis=verhaeltnis)
    if cfg.get("dienst") == "openai":
        return _openai(cfg, beschreibung, None, genau=genau, format=format)
    raise Fehler("Bilder erzeugen ist nicht eingerichtet.")
