#!/usr/bin/env python3
"""Szenen-Modul (seit 0.4) ohne Bruecke: Schritte pruefen, speichern/ersetzen, finden, umbenennen, Schritt entfernen,
loeschen, Beschreibungen. Testordner statt echter Daten."""
import json
import os
import shutil
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HIER), "bruecke"))
import szenen as sz  # noqa: E402

T = tempfile.mkdtemp(prefix="szenen-test-")
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    if bed:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name, str(info)[:300])


def wirft(f, *a):
    try:
        f(*a)
    except sz.Fehler as e:
        return str(e)
    return ""


LICHT = {"werkzeug": "geraet_steuern", "argumente": {"entity_id": "light.flur", "dienst": "turn_off"}}
PUSH = {"werkzeug": "nachricht", "argumente": {"aktion": "senden", "kanal": "push", "an": "Sam", "text": "Essen ist fertig"}}
pruef("Schritte: gueltig", len(sz.schritte_pruefen([LICHT, PUSH, {"werkzeug": "warten", "argumente": {"sekunden": 99}}])) == 3)
pruef("Schritte: warten begrenzt", sz.schritte_pruefen([{"werkzeug": "warten", "argumente": {"sekunden": 99}}])[0]["argumente"] == {"sekunden": 20})
pruef("Schritte: fremdes Werkzeug", "geht in einer Szene nicht" in wirft(sz.schritte_pruefen, [{"werkzeug": "homelab_auftrag", "argumente": {"auftrag": "x"}}]))
pruef("Schritte: Mail nicht", "kanal=mail" in wirft(sz.schritte_pruefen, [dict(PUSH, argumente=dict(PUSH["argumente"], kanal="mail"))]))
pruef("Schritte: Entwurf nicht", "Entwürfe" in wirft(sz.schritte_pruefen, [dict(PUSH, argumente=dict(PUSH["argumente"], entwurf="e1"))]))
pruef("Schritte: Pflichtfeld", "dienst fehlt" in wirft(sz.schritte_pruefen, [{"werkzeug": "geraet_steuern", "argumente": {"entity_id": "light.x"}}]))
pruef("Schritte: hoechstens 12", "Höchstens" in wirft(sz.schritte_pruefen, [LICHT] * 13))
pruef("Schritte: leer", "mindestens" in wirft(sz.schritte_pruefen, []))
pruef("Schritte: Abfrage nicht", "aktion=status" in wirft(sz.schritte_pruefen, [{"werkzeug": "saugroboter", "argumente": {"aktion": "status"}}]))
pruef("Schritte: als JSON-Text", len(sz.schritte_pruefen(json.dumps([LICHT]))) == 1)
pruef("Schritte: zusammen hoechstens 40 s warten", "40 Sekunden" in wirft(sz.schritte_pruefen, [{"werkzeug": "warten", "argumente": {"sekunden": 20}}] * 3))
pruef("Name: zu lang", "zu lang" in wirft(sz.name_pruefen, "x" * 41))
s1, neu = sz.speichern(T, "Gute Nacht", [LICHT], "alex")
pruef("Speichern neu", neu and s1["id"].startswith("s") and s1["von"] == "alex")
s1b, neu = sz.speichern(T, "gute nacht", [LICHT, LICHT], "alex")
pruef("Gleicher Name ersetzt", not neu and s1b["id"] == s1["id"] and len(sz.laden(T)) == 1 and len(sz.laden(T)[0]["schritte"]) == 2)
pruef("Finden: Szene-Praefix und Gross-/Kleinschreibung", sz.finden(sz.laden(T), "die Szene Gute Nacht")["id"] == s1["id"])
sz.speichern(T, "Essen fertig", [PUSH], "sam")
pruef("Finden: Teil eindeutig", sz.finden(sz.laden(T), "essen")["name"] == "Essen fertig")
pruef("Umbenennen: doppelter Name", "gibt es schon" in wirft(sz.umbenennen, T, s1["id"], "Essen fertig", "alex"))
pruef("Umbenennen", sz.umbenennen(T, s1["id"], "Schlafenszeit", "alex")["name"] == "Schlafenszeit")
pruef("Schritt entfernen", len(sz.schritt_entfernen(T, s1["id"], 2, "alex")["schritte"]) == 1)
pruef("Letzten Schritt nicht entfernen", "letzte Schritt" in wirft(sz.schritt_entfernen, T, s1["id"], 1, "alex"))
pruef("Beschreibung Push", sz.beschreibung(PUSH) == "Push an Sam: „Essen ist fertig“")
pruef("Beschreibung mit Namen und Wort", sz.beschreibung(LICHT, {"light.flur": "Flurlicht"}) == "Flurlicht: aus")
pruef("Beschreibung Lautstaerke", sz.beschreibung({"werkzeug": "geraet_steuern", "argumente": {"entity_id": "media_player.d", "dienst": "volume_set", "daten": {"volume_level": 0.45}}}, {"media_player.d": "Verstärker"}) == "Verstärker: Lautstärke 45 %")
pruef("Beschreibung fuers Gehirn mit Kennung", sz.beschreibung(LICHT) == "light.flur: turn_off")
pruef("Fuer die App", [x["name"] for x in sz.fuer_app(sz.laden(T))] == ["Schlafenszeit", "Essen fertig"])
pruef("Loeschen", sz.loeschen(T, "Essen fertig", "sam")["name"] == "Essen fertig" and len(sz.laden(T)) == 1)
# Unix-Rechte nur ausserhalb von Windows pruefbar (dort gelten ACLs)
pruef("Datei 600", os.name == "nt" or oct(os.stat(os.path.join(T, sz.DATEI)).st_mode & 0o777) == "0o600")
shutil.rmtree(T)
print("Szenen: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
