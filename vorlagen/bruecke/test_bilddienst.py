#!/usr/bin/env python3
"""Einheitentests fuer bruecke/bilddienst.py und bruecke/zusatzdienste.py (seit 0.3.3), ohne Netz und ohne echte
Schluessel: urlopen wird abgefangen. Prueft Bildgroessen, Anfragen an Cloudflare und OpenAI (Format laut deren
Dokumentation bzw. SDK), Fehlerzuordnung, Tageszaehler und das Lesen der Zugaenge aus .env und Schluesseldateien."""
import base64
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import urllib.error

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HIER, os.path.join(os.path.dirname(HIER), "bruecke")]
import bilddienst as b  # noqa: E402
import zusatzdienste as z  # noqa: E402

fehler = 0


def pruefe(name, ok):
    global fehler
    if not ok:
        fehler += 1
        print("FEHLER:", name)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 640, 480) + b"\x08\x02\x00\x00\x00"
JPG = b"\xff\xd8\xff\xc0" + struct.pack(">HBHHB", 17, 8, 853, 1280, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xd9"
gesehen = []
antwort = {}


class Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def falsch_urlopen(req, timeout=None):
    gesehen.append(req)
    if antwort["code"] != 200:
        raise urllib.error.HTTPError(req.full_url, antwort["code"], "x", {}, io.BytesIO(json.dumps(antwort["body"]).encode()))
    return Antwort(json.dumps(antwort["body"]).encode())


b.urllib.request.urlopen = falsch_urlopen

pruefe("Groesse PNG", b.groesse(PNG) == (640, 480))
pruefe("Groesse JPEG", b.groesse(JPG) == (1280, 853))
pruefe("Groesse unbekannt", b.groesse(b"kein bild") is None)
w, h = b.ausgabe_masse(1280, 853)
pruefe("Ausgabe: laengste Seite 1024, Vielfache von 16", (w, h) == (1024, 688) and w % 16 == 0 and h % 16 == 0)
pruefe("Neurons: 9B deutlich teurer als 4B", b.neurons(b.CF_9B, (1024, 688), (1024, 688)) > 8 * b.neurons(b.CF_4B, (1024, 688), (1024, 688)))

d = tempfile.mkdtemp()
try:
    # Cloudflare: Multipart mit prompt, width, height, input_image_0; Zaehler steigt
    antwort.update(code=200, body={"result": {"image": base64.b64encode(PNG).decode()}})
    cf = {"dienst": "cloudflare", "cf_konto": "konto1", "cf_token": "unecht-cf", "tageslimit": 9000}
    roh, typ, info = b.bearbeiten(cf, d, JPG, "image/jpeg", "make the sky blue")
    r = gesehen[-1]
    pruefe("Cloudflare: Adresse mit Konto und 4B", r.full_url.endswith("/accounts/konto1/ai/run/" + b.CF_4B))
    pruefe("Cloudflare: Felder", all(x in r.data for x in (b'name="prompt"', b'name="width"\r\n\r\n1024',
                                                            b'name="height"\r\n\r\n688', b'name="input_image_0"', JPG)))
    pruefe("Cloudflare: Ergebnis und Zaehler", roh == PNG and typ == "image/png" and b.stand(d, cf)["bilder"] == 1)
    cf_knapp = dict(cf, tageslimit=int(b.stand(d, cf)["neurons"]) + 200)
    roh, typ, info = b.bearbeiten(cf_knapp, d, JPG, "image/jpeg", "remove the cup", genau=True)
    pruefe("Cloudflare: zu wenig fuer 9B -> 4B mit Hinweis", info["modell"] == b.CF_4B.split("/")[-1] and info["hinweis"])
    try:
        b.erzeugen(dict(cf, tageslimit=1), d, "a cat")
        pruefe("Cloudflare: Limit erreicht", False)
    except b.Fehler as e:
        pruefe("Cloudflare: Limit erreicht", "aufgebraucht" in str(e))
    antwort.update(code=401, body={"errors": [{"message": "Authentication error"}]})
    try:
        b.erzeugen(cf, d, "a cat")
        pruefe("Cloudflare 401", False)
    except b.Fehler as e:
        pruefe("Cloudflare 401", "401" in str(e) and "unecht" not in str(e))

    # OpenAI: generations als JSON, edits als Multipart mit Feld image
    antwort.update(code=200, body={"data": [{"b64_json": base64.b64encode(PNG).decode()}], "usage": {"output_tokens": 1056}})
    oa = {"dienst": "openai", "openai_schluessel": "sk-unecht"}
    roh, typ, info = b.erzeugen(oa, d, "a red cup", "quer")
    r, k = gesehen[-1], json.loads(gesehen[-1].data)
    pruefe("OpenAI erzeugen: Endpunkt und JSON", r.full_url == "https://api.openai.com/v1/images/generations"
           and r.get_header("Content-type") == "application/json")
    pruefe("OpenAI erzeugen: Modell, Groesse, Qualitaet, Format",
           (k["model"], k["size"], k["quality"], k["output_format"]) == (b.OPENAI_MODELL, "1536x1024", "medium", "jpeg"))
    pruefe("OpenAI: kein response_format, Bearer", "response_format" not in k and r.get_header("Authorization") == "Bearer sk-unecht")
    pruefe("OpenAI: Ergebnis", roh == PNG and typ == "image/png" and info["token"] == 1056)
    b.bearbeiten(oa, d, JPG, "image/jpeg", "make it blue", genau=True)
    r = gesehen[-1]
    pruefe("OpenAI bearbeiten: edits, Multipart, image, genau = sunburst, size auto",
           r.full_url == "https://api.openai.com/v1/images/edits" and b'name="image"; filename="bild.jpg"' in r.data
           and b.OPENAI_GENAU.encode() in r.data and b'name="size"\r\n\r\nauto' in r.data and JPG in r.data)
    for code, meld, erwartet in ((401, "Incorrect API key", "Schlüssel ab"), (429, "quota", "Guthaben"),
                                 (403, "Your organization must be verified", "Verifizierung")):
        antwort.update(code=code, body={"error": {"message": meld}})
        try:
            b.erzeugen(oa, d, "x")
            pruefe("OpenAI %d" % code, False)
        except b.Fehler as e:
            pruefe("OpenAI %d" % code, erwartet in str(e) and "sk-unecht" not in str(e))
    for dienst in ("aus", "unbekannt"):
        try:
            b.erzeugen({"dienst": dienst}, d, "x")
            pruefe("nicht eingerichtet: " + dienst, False)
        except b.Fehler:
            pass

    # Zusatzdienste: Werte direkt, als Datei mit nur dem Wert, als Datei mit NAME=wert
    open(os.path.join(d, "roh.txt"), "w").write("abc123\n")
    open(os.path.join(d, "geheim.txt"), "w", encoding="utf-8-sig").write("# Kommentar\nCLOUDFLARE_KONTO=k1\nCLOUDFLARE_TOKEN = \"t 2\"\n")
    with open(os.path.join(d, ".env"), "w") as f:
        f.write("CLOUDFLARE_KONTO_DATEI=%s\nCLOUDFLARE_TOKEN_DATEI=%s\nTRANSMUTE_ADRESSE=http://x:3313/\n"
                "TRANSMUTE_SCHLUESSEL_DATEI=%s\n" % (os.path.join(d, "geheim.txt"), os.path.join(d, "geheim.txt"),
                                                     os.path.join(d, "roh.txt")))
    c = z.lesen(d)
    pruefe("Zusatz: Cloudflare aus NAME=wert-Datei", (c["bild"]["cf_konto"], c["bild"]["cf_token"]) == ("k1", "t 2"))
    pruefe("Zusatz: ohne BILD_DIENST gilt cloudflare", c["bild"]["dienst"] == "cloudflare")
    pruefe("Zusatz: Transmute, Adresse ohne Schraegstrich", c["transmute"] == {"adresse": "http://x:3313", "schluessel": "abc123"})
    pruefe("Zusatz: Uebersicht ohne Zugaenge", z.uebersicht(d) == {"pdf": True, "bild": "cloudflare", "umwandeln": "transmute"}
           and "k1" not in json.dumps(z.uebersicht(d)))
    with open(os.path.join(d, ".env"), "w") as f:
        f.write("BILD_DIENST=openai\nOPENAI_SCHLUESSEL=sk-x\nOPENAI_BILDQUALITAET=ultra\n")
    c = z.lesen(d)
    pruefe("Zusatz: OpenAI, unbekannte Qualitaet verworfen", c["bild"]["dienst"] == "openai" and c["bild"]["openai_qualitaet"] == ""
           and z.uebersicht(d)["bild"] == "openai")
    with open(os.path.join(d, ".env"), "w") as f:
        f.write("BILD_DIENST=openai\n")
    pruefe("Zusatz: Dienst ohne Schluessel = aus", z.uebersicht(d)["bild"] == "aus")
    os.remove(os.path.join(d, ".env"))
    pruefe("Zusatz: ohne .env alles aus ausser PDF", z.uebersicht(d) == {"pdf": True, "bild": "aus", "umwandeln": "aus"})
finally:
    shutil.rmtree(d)

print("Bilder und Zusatzdienste: %d Fehler" % fehler)
sys.exit(1 if fehler else 0)
