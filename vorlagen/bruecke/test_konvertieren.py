#!/usr/bin/env python3
"""Einheitentests fuer bruecke/konvertieren.py (seit 0.3.3): Ablauf gegen eine nachgebaute Transmute-API (ohne Netz),
Formatnamen (jpg/jpeg), Qualitaetsstufen (deutsch und englisch, unbekannte Stufen mit Meldung statt still)."""
import json
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HIER, os.path.join(os.path.dirname(HIER), "bruecke")]
import konvertieren as k  # noqa: E402

fehler = 0
aufrufe = []
FORMATE = {"mp3": ["medium", "high", "low"], "jpeg": [], "pdf": []}


def falsch(cfg, methode, pfad, daten=None, art="application/json", zeit=k.ZEIT):
    aufrufe.append((methode, pfad, json.loads(daten) if art == "application/json" and daten else None))
    if methode == "POST" and pfad == "/api/files":
        return json.dumps({"metadata": {"id": "f1", "compatible_formats": FORMATE}}).encode()
    if methode == "POST" and pfad == "/api/conversions":
        return json.dumps({"id": "c1", "extension": "." + json.loads(daten)["output_format"]}).encode()
    if methode == "GET":
        return b"ERGEBNIS"
    return b""


def pruefe(name, ok):
    global fehler
    if not ok:
        fehler += 1
        print("FEHLER:", name)


k._anfrage = falsch
cfg = {"adresse": "http://x", "schluessel": "unecht"}
roh, name, typ = k.umwandeln(cfg, b"FLAC", "lied.flac", "audio/flac", "mp3", "high")
anf = [a[2] for a in aufrufe if a[1] == "/api/conversions"][-1]
pruefe("mp3 high an Transmute", anf == {"id": "f1", "output_format": "mp3", "quality": "high"})
pruefe("Ergebnis und Name", roh == b"ERGEBNIS" and name == "lied.mp3" and typ == "audio/mpeg")
pruefe("aufgeraeumt (Quelle und Ergebnis geloescht)", ("DELETE", "/api/files/f1", None) in aufrufe
       and any(a[0] == "DELETE" and "c1" in a[1] for a in aufrufe))
k.umwandeln(cfg, b"FLAC", "lied.flac", "audio/flac", "mp3", "hoch")
pruefe("deutsche Stufe hoch -> high", [a[2] for a in aufrufe if a[1] == "/api/conversions"][-1]["quality"] == "high")
k.umwandeln(cfg, b"FLAC", "lied.flac", "audio/flac", "mp3")
pruefe("ohne Stufe keine quality", "quality" not in [a[2] for a in aufrufe if a[1] == "/api/conversions"][-1])
for ziel, stufe, erwartet in (("mp3", "ultra", "Möglich: medium, high, low"), ("jpg", "high", "keine Stufen")):
    try:
        k.umwandeln(cfg, b"x", "bild.png", "image/png", ziel, stufe)
        pruefe("unbekannte Stufe %s/%s abgelehnt" % (ziel, stufe), False)
    except k.Fehler as e:
        pruefe("unbekannte Stufe %s/%s: %s" % (ziel, stufe, e), erwartet in str(e))
k.umwandeln(cfg, b"x", "bild.png", "image/png", "jpg")
pruefe("jpg wird zu jpeg", [a[2] for a in aufrufe if a[1] == "/api/conversions"][-1]["output_format"] == "jpeg")
try:
    k.umwandeln(cfg, b"x", "bild.png", "image/png", "docx")
    pruefe("unmoegliches Ziel abgelehnt", False)
except k.Fehler as e:
    pruefe("unmoegliches Ziel nennt die Moeglichkeiten", "Möglich:" in str(e) and "mp3" in str(e))
pruefe("formate mit Stufen", k.formate(cfg, b"x", "a.flac", "audio/flac", mit_qualitaet=True)["mp3"] == ["medium", "high", "low"])
pruefe("formate ohne Stufen", k.formate(cfg, b"x", "a.flac", "audio/flac") == ["jpeg", "mp3", "pdf"])
print("Umwandeln: %d Fehler" % fehler)
sys.exit(1 if fehler else 0)
