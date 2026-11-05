#!/usr/bin/env python3
"""Baustein leinwand.py (Anzeige auf dem Beamer, im Release seit 0.6) ohne Bruecke und ohne HA: Zustaende bauen
(Rezept, Liste, Woche, Text, Quiz), blaettern, Sensor-Inhalt samt Groessengrenze und Ansage-Adresse, Ansagen,
Erkennung des Cast-Geraets, Ablage, konfigurierbares Cast-Geraet, englische Texte.
Testordner statt echter Daten, keine Netzzugriffe."""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import leinwand as lw  # noqa: E402

T = tempfile.mkdtemp(prefix="leinwand-test-")
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


REZ = {"name": "Kürbis-Lasagne", "slug": "kuerbis-lasagne", "recipeYield": "4 Portionen", "totalTime": "75 Minuten",
       "recipeIngredient": [{"display": "800 g Kürbis"}, {"display": ""}, {"note": "Salz"}],
       "recipeInstructions": [{"text": "Ofen vorheizen."}, {"text": "Kürbis würfeln."}, {"text": "Schichten und backen."}]}
JETZT = datetime(2026, 11, 3, 18, 5)

# ---------------------------------------------------------------- Zustaende und Blaettern
z = lw.rezept_zustand(REZ, "Anna")
pruef("M1 Rezept: Titel, leere Zutat weg, 1 + 3 Seiten", z["titel"] == "Kürbis-Lasagne" and z["zutaten"] == ["800 g Kürbis", "Salz"]
      and lw.seiten(z) == 4 and z["unter"] == "4 Portionen · 75 Minuten" and z["von"] == "Anna", z)
pruef("M1b Rezept ohne Namen und Zeit", lw.rezept_zustand({"totalTime": "None"})["titel"] == "Rezept"
      and lw.rezept_zustand({"totalTime": "None"})["unter"] == "")
z1, f1 = lw.blaettern(z, "weiter")
z3, f3 = lw.blaettern(z, "3")
z4, f4 = lw.blaettern(z3, "weiter")
z0, f0 = lw.blaettern(z, "zurück")
pruef("M2 Blaettern: weiter, Nummer, Ende und Anfang mit Meldung, Zustand bleibt",
      z1["seite"] == 1 and not f1 and z3["seite"] == 3 and "letzte Schritt" in f4 and z4["seite"] == 3
      and "zurück geht es nicht" in f0 and z0["seite"] == 0 and lw.blaettern(z3, "anfang")[0]["seite"] == 0
      and "Unbekannt" in lw.blaettern(z, "quatsch")[1] and z["seite"] == 0)
pruef("M2b Blaettern ohne Ziel heisst weiter", lw.blaettern(z, None)[0]["seite"] == 1)
st0, a0 = lw.sensor(z, JETZT)
st2, a2 = lw.sensor(lw.blaettern(z, 2)[0], JETZT)
st3, a3 = lw.sensor(z3, JETZT)
pruef("M3 Sensor: Ueberblick mit Schrittliste, Schritt mit Text und Danach, Zustand",
      st0 == "rezept 0/3" and len(a0["schritte"]) == 3 and "schritt" not in a0 and st2 == "rezept 2/3"
      and a2["schritt"] == "Kürbis würfeln." and a2["danach"] == "Schichten und backen." and "schritte" not in a2
      and a3["danach"] == "" and a0["zeit"] == "18:05" and a0["friendly_name"] == "Jarvis Leinwand", (st0, st2, a2))
gross = lw.text_zustand("X", "y" * 5000, ["p" * 500] * 50)
gross["punkte"] = ["q" * 120] * 400                   # mehr, als text_zustand zulassen wuerde
st, a = lw.sensor(gross)
pruef("M4 Sensor bleibt unter der Grenze", len(json.dumps(a, ensure_ascii=False).encode()) <= lw.MAX_ATTRIBUTE and len(a["text"]) <= 1500,
      len(json.dumps(a, ensure_ascii=False).encode()))
pruef("M4b Text begrenzt", len(gross["text"]) == 1500 and gross["text"].endswith("…")
      and len(lw.text_zustand("X", "", ["p"] * 50)["punkte"]) == 12 and lw.text_zustand("", "")["titel"] == "Jarvis")
li = lw.liste_zustand("Einkauf", ["A%d" % i for i in range(30)] + ["  "])
s1, a1 = lw.sensor(li)
s2, b2 = lw.sensor(lw.blaettern(li, "weiter")[0])
pruef("M5 Liste in Seiten zu 24, leere Punkte weg", lw.seiten(li) == 2 and len(a1["punkte"]) == 24 and len(b2["punkte"]) == 6
      and s1 == "liste 1/2" and s2 == "liste 2/2" and a1["anzahl"] == 30, (s1, s2))
pruef("M5b Liste hoechstens 96 Punkte, einseitig ohne Zaehler", len(lw.liste_zustand("L", ["x"] * 200)["punkte"]) == 96
      and lw.sensor(lw.liste_zustand("L", ["x"]))[0] == "liste")
wz = lw.woche_zustand([{"tag": "Mo", "datum": "02.11.", "termine": ["t%d" % i for i in range(9)]}] * 9)
pruef("M6 Woche hoechstens 7 Tage, 6 Termine; Standardtitel; Wetterzeile",
      len(wz["tage"]) == 7 and len(wz["tage"][0]["termine"]) == 6 and wz["titel"] == "Die Woche"
      and lw.woche_zustand([], titel="Die nächsten sieben Tage")["titel"] == "Die nächsten sieben Tage"
      and lw.wetter_zeile({"condition": "rainy", "templow": 5.6, "temperature": 11.2}) == "Regen · 6–11 °C"
      and lw.wetter_zeile({"condition": "neu"}) == "Neu · ?–? °C")
pruef("M6b Woche im Sensor", lw.sensor(wz)[1]["tage"] == wz["tage"] and lw.sensor(wz)[0] == "woche")

# ---------------------------------------------------------------- Cast-Geraet erkennen und konfigurieren
LW_AN = {"state": "playing", "attributes": {"app_id": lw.CAST_APP}}
ANDERES = {"state": "playing", "attributes": {"app_id": "XYZ", "app_name": "Video"}}
PAUSE = {"state": "paused", "attributes": {"app_id": "XYZ"}}
LEER = {"state": "off", "attributes": {}}
WEG = {"state": "unavailable", "attributes": {}}
pruef("M7 Erkennung der Box", lw.zeigt_leinwand(LW_AN) and not lw.anderes_laeuft(LW_AN) and lw.anderes_laeuft(ANDERES)
      and lw.anderes_laeuft(PAUSE) and lw.erreichbar(LEER) and not lw.anderes_laeuft(LEER) and not lw.erreichbar(WEG)
      and not lw.erreichbar({}) and not lw.erreichbar(None) and not lw.zeigt_leinwand(None))
pruef("C1 Standard-Cast neutral, Dienst fuer cast.show_lovelace_view", lw.zeige_dienst() == {
      "entity_id": "media_player.leinwand", "dashboard_path": "jarvis-leinwand", "view_path": "leinwand"})
lw.setze_cast("media_player.box_wohnzimmer")
pruef("C2 setze_cast wirkt auf den Dienst", lw.CAST == "media_player.box_wohnzimmer"
      and lw.zeige_dienst()["entity_id"] == "media_player.box_wohnzimmer")
for falsch in ("light.x", "media_player.Gross", "", None, "media_player.x; rm"):
    try:
        lw.setze_cast(falsch)
        pruef("C3 ungueltiges Cast-Geraet abgelehnt: %r" % (falsch,), False)
    except ValueError:
        pruef("C3 ungueltiges Cast-Geraet abgelehnt: %r" % (falsch,), lw.CAST == "media_player.box_wohnzimmer")

# ---------------------------------------------------------------- Ablage
lw.zustand_speichern(T, z3)
open(T + "/kaputt.json", "w").write("{")
pruef("M8 Zustand speichern/laden, fehlender Ordner leer", lw.zustand_laden(T)["seite"] == 3
      and lw.zustand_laden(T + "/gibtsnicht") == {} and not os.path.exists(T + "/" + lw.DATEI + ".neu"))
open(T + "/" + lw.DATEI, "w").write("{")
pruef("M8b kaputte Datei und fremde Art: leer", lw.zustand_laden(T) == {})
json.dump({"art": "film"}, open(T + "/" + lw.DATEI, "w"))
pruef("M8c unbekannte Art: leer", lw.zustand_laden(T) == {})
lw.zustand_speichern(T, None)
pruef("M8d Leeren", lw.zustand_laden(T) == {} and json.load(open(T + "/" + lw.DATEI)) == {})
st_l, a_l = lw.sensor({}, JETZT)
pruef("M9 Leere Leinwand", st_l == "leer" and a_l["art"] == "leer" and a_l["icon"] == "mdi:projector-screen-off-outline")

# ---------------------------------------------------------------- Quiz (Inhalt wie quiz.anzeige ihn liefert)
QA = {"art": "quiz", "titel": "Familien-Quiz", "unter": "Tiere", "phase": "frage", "nr": 1, "gesamt": 9,
      "spieler": [{"name": "Mia", "punkte": 0, "dran": True, "hat": False}, {"name": "Ben", "punkte": 0, "dran": False, "hat": False}],
      "runde": 1, "runden": 3, "leiter": [1, 3, 5], "schluessel": "abc:0:frage", "frage": "Wie viele Beine hat eine Spinne?",
      "antworten": ["Sechs", "Acht", "Zehn", "Vier"], "fuer": "Mia", "stufe": "kind", "seit": 1000, "sekunden": 45,
      "schwierigkeit": 1, "auf_ab": 100.0, "antw_ab": [101.0, 102.0, 103.0, 104.0], "mund": "0f0f", "mund_hz": 20,
      "mund_ab": 100.5, "fremd": "weg"}
lz = lw.quiz_zustand(QA, "Anna")
st_q, at_q = lw.sensor(lz)
pruef("L1 Leinwand art quiz: Zustand und Sensor ohne Loesung, fremde Felder weg", st_q == "quiz 1/9" and at_q["art"] == "quiz"
      and at_q["frage"] == QA["frage"] and len(at_q["antworten"]) == 4 and "richtig" not in at_q and "fremd" not in at_q
      and at_q["mund"] == "0f0f" and at_q["antw_ab"] == [101.0, 102.0, 103.0, 104.0] and at_q["von"] == "Anna"
      and len(json.dumps(at_q, ensure_ascii=False).encode()) < lw.MAX_ATTRIBUTE, (st_q, at_q))
_, at_l = lw.sensor(lw.quiz_zustand(dict(QA, richtig="B", wusstest="Spinnen haben acht Beine.")))
st_e, at_e = lw.sensor(lw.quiz_zustand({"phase": "ende", "sieger": ["Mia"], "rangliste": [{"name": "Mia", "punkte": 3}]}))
pruef("L1b Loesung erst, wenn sie im Inhalt steht; Ende mit Sieger; Standardtitel", at_l["richtig"] == "B"
      and st_e == "quiz ende" and at_e["sieger"] == ["Mia"] and at_e["titel"] == "Familien-Quiz")
pruef("L2 Blaettern beim Quiz verweist auf das Quiz, Ansage", lw.blaettern(lz, "weiter")[0] is lz
      and "Werkzeug quiz" in lw.blaettern(lz, "weiter")[1] and "Frage 1 von 9" in lw.ansage(lz)
      and lw.ansage(lw.quiz_zustand({"phase": "ende"})) == "Auf der Leinwand steht der Endstand des Quiz.")
URL = "https://jarvis.example.org/alexa/ton/" + "a" * 32 + ".mp3"
_, at_t = lw.sensor(lw.quiz_zustand(dict(QA, ton=URL, ton_ab=1234.5)))
_, at_h = lw.sensor(dict(lw.text_zustand("T", "x"), ton="http://jarvis.local:8770/ton/x.mp3"))   # beim Quiz filtert quiz.anzeige
_, at_r = lw.sensor(dict(lw.text_zustand("T", "x"), ton=URL, ton_ab=7))
_, at_0 = lw.sensor(lw.quiz_zustand(dict(QA, seit=0)))
pruef("L2b Ansage fuer die Seite: ton (nur https) und ton_ab im Sensor, auch fuer andere Arten; seit 0 bleibt 0",
      at_t["ton"] == URL and at_t["ton_ab"] == 1234.5 and at_h.get("ton") is None and at_r["ton"] == URL and at_r["ton_ab"] == 7
      and "ton" not in at_q and at_0["seit"] == 0, (at_t.get("ton"), at_h.get("ton"), at_0.get("seit")))

# ---------------------------------------------------------------- Ansagen
pruef("A1 Ansagen Rezept, Schritt, Liste, Woche, Text, leer",
      lw.ansage(z) == "Kürbis-Lasagne auf der Leinwand: 2 Zutaten, 3 Schritte. Sag „weiter“ für den ersten Schritt."
      and lw.ansage(z1) == "Schritt 1 von 3: Ofen vorheizen."
      and lw.ansage(li) == "Einkauf auf der Leinwand (30 Einträge, Seite 1 von 2)."
      and lw.ansage(lw.liste_zustand("Kurz", ["a"])) == "Kurz auf der Leinwand (1 Einträge)."
      and lw.ansage(wz) == "Die Woche auf der Leinwand (7 Tage)."
      and lw.ansage(lw.text_zustand("Hausaufgabe")) == "„Hausaufgabe“ steht auf der Leinwand."
      and lw.ansage({}) == "Auf der Leinwand ist gerade nichts.")

# ---------------------------------------------------------------- Englisch
lw.setze_sprache("en")
ze = lw.rezept_zustand({"name": "Pumpkin lasagne", "recipeIngredient": [{"display": "Pumpkin"}],
                        "recipeInstructions": [{"text": "Heat the oven."}, {"text": "Bake."}]})
pruef("EN: Ansagen", lw.ansage(ze) == "Pumpkin lasagne on the screen: 1 ingredients, 2 steps. Say “next” for the first step."
      and lw.ansage(lw.blaettern(ze, "2")[0]) == "Step 2 of 2: Bake."
      and lw.ansage(li) == "Einkauf on the screen (30 items, page 1 of 2)."
      and lw.ansage(lw.woche_zustand([])) == "The week on the screen (0 days)."
      and lw.ansage(lw.text_zustand("Note")) == "“Note” is on the screen."
      and lw.ansage({}) == "There is nothing on the screen right now."
      and lw.ansage(lz) == "The quiz is on the screen (question 1 of 9).")
pruef("EN: Blaettern-Meldungen", lw.blaettern(lw.blaettern(ze, "2")[0], "weiter")[1] == "That was the last step. Enjoy your meal!"
      and lw.blaettern(li, "zurueck")[1] == "It does not go back any further." and "Unknown" in lw.blaettern(ze, "x")[1]
      and "tool quiz" in lw.blaettern(lz, "weiter")[1])
pruef("EN: Standardtitel, Wetter, Sensorname", lw.rezept_zustand({})["titel"] == "Recipe" and lw.woche_zustand([])["titel"] == "The week"
      and lw.quiz_zustand({})["titel"] == "Family Quiz" and lw.wetter_zeile({"condition": "cloudy", "templow": 1, "temperature": 4})
      == "Overcast · 1–4 °C" and lw.sensor({})[1]["friendly_name"] == "Jarvis Screen")
try:
    lw.setze_sprache("es")
    pruef("Sprache: nur de oder en", False)
except ValueError:
    pruef("Sprache: nur de oder en", lw.SPRACHE == "en")
lw.setze_sprache("de")
pruef("DE wieder", lw.ansage({}) == "Auf der Leinwand ist gerade nichts.")

shutil.rmtree(T, ignore_errors=True)
print("Leinwand: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
