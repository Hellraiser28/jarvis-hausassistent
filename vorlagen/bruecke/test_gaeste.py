#!/usr/bin/env python3
"""Baustein gaeste.py (Gaeste-Modus, seit 0.6): Einstellungen und Vorgaben, Gastzugang anlegen (Name, Ende, Bremsen),
Ablauf, Raumzuordnung der Sprachgeraete, Gast je Raum, Stand des Gaeste-WLANs, Link zur QR-Seite, Zeitangaben und
Meldungen auf Deutsch und Englisch.
Testordner statt echter Daten, kein Home Assistant, keine Netzzugriffe."""
import json
import os
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import gaeste as gst  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


def fehlertext(f, *a, **k):
    try:
        f(*a, **k)
    except gst.Fehler as e:
        return str(e)
    return ""


T = tempfile.mkdtemp(prefix="gaeste-")
LEER = tempfile.mkdtemp(prefix="gaeste-leer-")
JETZT = time.time()

# ---------------------------------------------------------------- Einstellungen
e = gst.einstellungen(LEER)
pruef("Vorgabe: 48 h, hoechstens 14 Tage, Wohnzimmer, 8 aktiv, 6 je Stunde",
      (e["stunden"], e["max_tage"], e["raeume"], e["max_aktiv"], e["anlegen_je_stunde"]) == (48, 14, ["Wohnzimmer"], 8, 6), e)
pruef("Vorgabe: QR nicht an die Wand", gst.VORGABE["qr_wand"] is False and e["qr_wand"] is False)
pruef("Vorgabe: WLAN-Entitaeten sind Platzhalter", e["wlan_schalter"] == "switch.gaeste_wlan" and e["wlan_qr"] == "image.gaeste_wlan_qr")
pruef("Vorgabe wird nicht veraendert", gst.einstellungen(LEER)["geraete"] is not gst.VORGABE["geraete"])
json.dump({"geraete": {"Home Assistant Voice Wohnzimmer": "Wohnzimmer", "Satellit<x>": "Bad{}"}, "anlegen_je_stunde": 3,
           "qr_wand": True, "stunden": True, "max_aktiv": 0, "max_tage": 500, "raeume": ["Wohnzimmer", "Kü<che>", 3, ""] + ["R"] * 20,
           "wlan_schalter": "switch.router_gast", "wlan_qr": "image.x'); drop"}, open(os.path.join(T, gst.EINSTELLUNGEN), "w"))
e = gst.einstellungen(T)
pruef("Einstellungen: gueltige Werte uebernommen", e["anlegen_je_stunde"] == 3 and e["qr_wand"] is True
      and e["wlan_schalter"] == "switch.router_gast" and e["geraete"]["Home Assistant Voice Wohnzimmer"] == "Wohnzimmer", e)
pruef("Einstellungen: falsche Typen und Unsinn bleiben Vorgabe", e["stunden"] == 48 and e["max_aktiv"] == 8
      and e["wlan_qr"] == "image.gaeste_wlan_qr", e)
pruef("Einstellungen: max_tage hoechstens 90", e["max_tage"] == 90)
pruef("Einstellungen: Raeume bereinigt, hoechstens 10", e["raeume"][:2] == ["Wohnzimmer", "Küche"] and len(e["raeume"]) == 10
      and e["geraete"]["Satellit<x>"] == "Bad", e["raeume"])
json.dump({"geraete": {"Home Assistant Voice Wohnzimmer": "Wohnzimmer"}, "anlegen_je_stunde": 3, "max_aktiv": 3},
          open(os.path.join(T, gst.EINSTELLUNGEN), "w"))

# ---------------------------------------------------------------- Ende lesen
pruef("Ende leer: Vorgabe 48 h", gst.bis_lesen("", JETZT) == JETZT + 48 * 3600)
morgen = (datetime.fromtimestamp(JETZT) + timedelta(days=1)).strftime("%Y-%m-%d")
pruef("Ende nur Datum: 23:59", datetime.fromtimestamp(gst.bis_lesen(morgen, JETZT)).strftime("%H:%M") == "23:59")
pruef("Ende mit Uhrzeit und T", datetime.fromtimestamp(gst.bis_lesen(morgen + "T18:30", JETZT)).strftime("%Y-%m-%d %H:%M")
      == morgen + " 18:30")
pruef("Ende hoechstens max_tage", gst.bis_lesen("2099-01-01", JETZT) == JETZT + 14 * 86400
      and gst.bis_lesen("2099-01-01", JETZT, max_tage=2) == JETZT + 2 * 86400)
pruef("Ende in der Vergangenheit: abgelehnt", "Vergangenheit" in fehlertext(gst.bis_lesen, "2020-01-01 10:00", JETZT))
pruef("Ende unverstaendlich: abgelehnt", "JJJJ-MM-TT" in fehlertext(gst.bis_lesen, "naechsten Freitag", JETZT))

# ---------------------------------------------------------------- Anlegen, Ablauf, Entfernen
pruef("Ohne Namen: Rueckfrage", fehlertext(gst.neu, T, " <> ", JETZT + 3600, JETZT) == "Wie heißt der Besuch?")
anna = gst.neu(T, "Anna", JETZT + 48 * 3600, JETZT)
pruef("Anlegen: Kennung, Raeume aus den Einstellungen", gst.ID.match(anna["id"]) and anna["raeume"] == ["Wohnzimmer"]
      and anna["erstellt"] == JETZT, anna)
pruef("gaeste.json privat (600)", stat.S_IMODE(os.stat(os.path.join(T, gst.DATEI)).st_mode) == 0o600)
pruef("Gleicher Name, solange aktiv: abgelehnt", fehlertext(gst.neu, T, "anna", JETZT + 3600, JETZT) == "Für anna läuft schon ein Gastzugang.")
ben = gst.neu(T, "Ben", JETZT + 3600, JETZT + 1)
gst.neu(T, "Tom", JETZT + 3600, JETZT + 2)
pruef("Hoechstens max_aktiv (Einstellung 3)", fehlertext(gst.neu, T, "Mia", JETZT + 3600, JETZT) == "Es gibt schon 3 aktive Gastzugänge.")
pruef("Finden nach Name und Kennung", gst.finden(gst.alle(T), "BEN")["id"] == ben["id"] and gst.finden(gst.alle(T), ben["id"])["name"] == "Ben"
      and gst.finden(gst.alle(T), "") is None and gst.finden(gst.alle(T), "Oma") is None)
pruef("Aktive und abgelaufene", len(gst.aktive(T, JETZT)) == 3 and [g["name"] for g in gst.abgelaufene(T, JETZT + 7200)] == ["Ben", "Tom"])
mia = gst.neu(T, "Mia", JETZT + 10000, JETZT + 7200)
pruef("Abgelaufene machen Platz", mia and len(gst.aktive(T, JETZT + 7200)) == 2)
gst.neu(T, "Lea", JETZT + 30 * 86400, JETZT + 8.5 * 86400)       # Grenze 1,5 Tage: Anna (2 Tage) bleibt
pruef("Beim Speichern fallen seit ueber 7 Tagen abgelaufene weg", sorted(g["name"] for g in gst.alle(T)) == ["Anna", "Lea"],
      [g["name"] for g in gst.alle(T)])
pruef("Entfernen", gst.entfernen(T, anna["id"])["name"] == "Anna" and gst.entfernen(T, anna["id"]) is None
      and [g["name"] for g in gst.alle(T)] == ["Lea"])
json.dump([{"id": "gast-abcdef", "name": "Ja\x07ne<b>", "bis": "1e12", "raeume": ["Wohnzimmer", 7]},
           {"id": "gast-123456", "bis": 1e12}, {"id": "boese", "bis": 1e12}, {"id": "gast-fedcba"}, "kaputt",
           {"id": "gast-0000zz", "bis": 1e12}], open(os.path.join(T, gst.DATEI), "w"))
a = gst.alle(T)
pruef("Laden: nur gueltige Eintraege, Name bereinigt, ohne Namen 'Gast'", [(g["id"], g["name"], g["raeume"]) for g in a] ==
      [("gast-abcdef", "Janeb", ["Wohnzimmer"]), ("gast-123456", "Gast", [])], a)
open(os.path.join(T, gst.DATEI), "w").write("{}")
pruef("Laden: keine Liste -> leer", gst.alle(T) == [])

# ---------------------------------------------------------------- Raumzuordnung
json.dump({"version": 1, "raeume": {"wohnzimmer": {"name": "Wohnzimmer", "bereich": "Wohnzimmer", "ausgabe": []},
                                    "kueche": {"name": "Küche", "bereich": "Küche", "ausgabe": []}},
           "geraete": {"Satellit Couch": "wohnzimmer", "Küche": "kueche", "Flur": "flur"}}, open(os.path.join(T, "raeume.json"), "w"))
pruef("App, PC, Web-App: nie ein Raum", gst.raum_von(T, "app", "Wohnzimmer") == "" and gst.raum_von(T, "pc", "Home Assistant Voice Wohnzimmer") == "")
pruef("Geraet aus den Einstellungen", gst.raum_von(T, "ha", "home assistant voice wohnzimmer") == "Wohnzimmer")
pruef("Geraet aus raeume.json", gst.raum_von(T, "ha", "Satellit Couch") == "Wohnzimmer"
      and gst.raum_von(T, "test-ha", "Flur") == "flur")
pruef("Unbekanntes Geraet mit HA-Bereich", gst.raum_von(T, "ha", "Unbekannter Satellit", "Wohn<zimmer>") == "Wohnzimmer")
pruef("Echo heisst wie sein Raum", gst.raum_von(T, "alexa", "Wohnzimmer") == "Wohnzimmer" and gst.raum_von(T, "alexa", "Küche") == "Küche")
pruef("Unbekannt: kein Raum", gst.raum_von(T, "alexa", "Dachboden") == "" and gst.raum_von(T, "ha", "") == "")
os.remove(os.path.join(T, "raeume.json"))
pruef("Ohne raeume.json: nur Einstellungen", gst.raum_von(T, "ha", "Satellit Couch") == ""
      and gst.raum_von(T, "ha", "Home Assistant Voice Wohnzimmer") == "Wohnzimmer")

# ---------------------------------------------------------------- Gast je Raum
g1 = gst.neu(T, "Anna", JETZT + 3600, JETZT)
g2 = gst.neu(T, "Ben", JETZT + 7200, JETZT + 5)
pruef("Gast im Raum: der juengste aktive", gst.gast_fuer_raum(T, "wohnzimmer", JETZT + 10)["id"] == g2["id"])
pruef("Anderer Raum oder leer: keiner", gst.gast_fuer_raum(T, "Küche", JETZT) is None and gst.gast_fuer_raum(T, "", JETZT) is None)
pruef("Nach Ablauf sofort keine Gastrechte", gst.gast_fuer_raum(T, "Wohnzimmer", JETZT + 7201) is None
      and gst.gast_fuer_raum(T, "Wohnzimmer", JETZT + 3601)["id"] == g2["id"])

# ---------------------------------------------------------------- Gaeste-WLAN und QR-Seite
W = tempfile.mkdtemp(prefix="gaeste-wlan-")
pruef("WLAN-Stand ohne Datei", gst.wlan_von_uns(W) is False and gst.wlan_bis(W) == 0.0 and gst.qr_link(W) == "")
gst.wlan_von_uns(W, True)
gst.wlan_bis(W, JETZT + 48 * 3600)
pruef("Von uns eingeschaltet, mit Ende", gst.wlan_von_uns(W) is True and gst.wlan_bis(W) == JETZT + 48 * 3600
      and stat.S_IMODE(os.stat(os.path.join(W, gst.WLAN_STAND)).st_mode) == 0o600)
link = gst.qr_link(W, JETZT + 3600, JETZT)
pruef("Link: 22 Zeichen, gueltig bis zum Ende", gst.LINK.match(link) and gst.qr_link(W, jetzt=JETZT) == link
      and gst.qr_link(W, jetzt=JETZT + 3601) == "", link)
pruef("Link verlaengern behaelt den Link, nie kuerzer", gst.qr_link(W, JETZT + 7200, JETZT) == link
      and gst.qr_link(W, JETZT + 600, JETZT) == link and gst.qr_link(W, jetzt=JETZT + 7000) == link)
pruef("Link pruefen", gst.qr_link_pruefen(W, link, JETZT) and not gst.qr_link_pruefen(W, link[:-1] + ("A" if link[-1] != "A" else "B"), JETZT)
      and not gst.qr_link_pruefen(W, None, JETZT) and not gst.qr_link_pruefen(W, link, JETZT + 8000))
pruef("Abgelaufener Link wird beim Verlaengern neu gewuerfelt", gst.qr_link(W, JETZT + 99999, JETZT + 8000) != link)
gst.wlan_von_uns(W, False)
pruef("WLAN aus durch die Bruecke: Ende und Link verfallen", gst.wlan_von_uns(W) is False and gst.wlan_bis(W) == 0.0
      and gst.qr_link(W, jetzt=JETZT) == "")
json.dump({"von_uns": "ja", "bis": True, "link": "kurz", "link_bis": 1e12}, open(os.path.join(W, gst.WLAN_STAND), "w"))
pruef("WLAN-Stand mit falschen Typen", gst.wlan_von_uns(W) is False and gst.wlan_bis(W) == 0.0 and gst.qr_link(W) == "")

# ---------------------------------------------------------------- Zeitangaben
heute = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
spaeter = heute + timedelta(days=5)
pruef("Wann: heute, morgen, Wochentag mit Datum", gst.wann(heute.timestamp()) == "heute 18:00 Uhr"
      and gst.wann((heute + timedelta(days=1)).timestamp()) == "morgen 18:00 Uhr"
      and gst.wann(spaeter.timestamp()) == "%s %s 18:00 Uhr" % (gst.TAGE[spaeter.weekday()], spaeter.strftime("%d.%m.")),
      gst.wann(spaeter.timestamp()))

# ---------------------------------------------------------------- Englisch
try:
    gst.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", True)
gst.setze_sprache("en")
pruef("EN: Wann", gst.wann(heute.timestamp()) == "today at 18:00" and gst.wann((heute + timedelta(days=1)).timestamp())
      == "tomorrow at 18:00" and gst.wann(spaeter.timestamp()) == "%s %d %s at 18:00" % (
          gst.TAGE_EN[spaeter.weekday()], spaeter.day, gst.MONATE_EN[spaeter.month - 1]), gst.wann(spaeter.timestamp()))
pruef("EN: Vorgabe-Raum", gst.einstellungen(LEER)["raeume"] == ["Living Room"])
json.dump({"raeume": ["Wohnzimmer"]}, open(os.path.join(W, gst.EINSTELLUNGEN), "w"))
pruef("EN: eingestellte Raeume bleiben", gst.einstellungen(W)["raeume"] == ["Wohnzimmer"])
m = [fehlertext(gst.bis_lesen, "2020-01-01", JETZT), fehlertext(gst.bis_lesen, "next Friday", JETZT),
     fehlertext(gst.neu, T, "", JETZT + 3600, JETZT), fehlertext(gst.neu, T, "Anna", JETZT + 3600, JETZT)]
gst.neu(T, "Mia", JETZT + 3600, JETZT)
m.append(fehlertext(gst.neu, T, "Lea", JETZT + 3600, JETZT))
pruef("EN: Meldungen", m == ["The end is in the past.", "Time not understood, please give it as YYYY-MM-DD or YYYY-MM-DD HH:MM.",
                             "What is the visitor's name?", "Anna already has a guest access.",
                             "There are already 3 active guest accesses."], m)
json.dump([{"id": "gast-123456", "bis": 1e12}], open(os.path.join(T, gst.DATEI), "w"))
pruef("EN: ohne Namen 'Guest'", gst.alle(T)[0]["name"] == "Guest")
gst.setze_sprache("de")
pruef("Zurueck auf Deutsch", gst.alle(T)[0]["name"] == "Gast" and gst.einstellungen(LEER)["raeume"] == ["Wohnzimmer"])

print("Gaeste: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
