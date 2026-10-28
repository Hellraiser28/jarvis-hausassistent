#!/usr/bin/env python3
"""Englische Seite der 0.4-Module (gedaechtnis, szenen): Texte, die die Person direkt sieht, und das Einlesen einer
zurueckgeschickten Gedaechtnis-Liste mit englischen Abschnitten. Testordner statt echter Daten."""
import os
import shutil
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HIER), "bruecke"))
import gedaechtnis as gd  # noqa: E402
import szenen as sz  # noqa: E402

T = tempfile.mkdtemp(prefix="sprache-test-")
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


NAMEN = {"alex": "Alex", "sam": "Sam"}
for m in (gd, sz):
    try:
        m.setze_sprache("fr")
        pruef(m.__name__ + ": fremde Sprache abgelehnt", False)
    except ValueError:
        pruef(m.__name__ + ": fremde Sprache abgelehnt", True)

gd.setze_sprache("en")
n1 = gd.neu(T, "Bins go out on Tuesday", "haus", "alex")
n2 = gd.neu(T, "Alex likes green tea", "alex", "alex")
txt = gd.export_txt(T, "alex", NAMEN)
pruef("Export: englischer Kopf", txt.startswith("# Jarvis memory for Alex, as of "), txt[:80])
pruef("Export: englische Abschnitte", "## House\n" in txt and "## Only for Alex\n" in txt, txt)
pruef("Export: keine deutschen Reste", "Gedächtnis" not in txt and "Haus" not in txt and "Nur für" not in txt, txt)
zurueck = txt.replace("Alex likes green tea", "Alex likes black tea") + "- Alex plays chess on Fridays\n"
v = gd.import_vergleich(T, "alex", zurueck, NAMEN)
pruef("Import englisch: geaendert", [(x["id"], x["neu"]) for x in v["geaendert"]] == [(n2, "Alex likes black tea")], v)
pruef("Import englisch: neu im eigenen Bereich", v["neu"] == [{"bereich": "alex", "text": "Alex plays chess on Fridays"}], v)
pruef("Import englisch: nichts geloescht", v["geloescht"] == [], v)
pruef("Import: deutsche Abschnitte gehen weiter", gd.import_vergleich(T, "alex", txt.replace("## House", "## Haus")
                                                                     .replace("## Only for Alex", "## Nur für Alex"),
                                                                     NAMEN)["geloescht"] == [])
vt = gd.vergleich_text(v, NAMEN, "alex")
pruef("Vergleich englisch", "changed [%d]: Alex likes black tea" % n2 in vt and "new (only Alex)" in vt, vt)
pruef("Vergleich leer", gd.vergleich_text({"geaendert": [], "geloescht": [], "neu": [], "unbekannt": []}, NAMEN, "alex")
      == "No changes.")
k = gd.fuer_kontext(T, "alex", NAMEN)
pruef("Kontext englisch", "## House (everyone in the household)" in k and "## Only for Alex" in k, k)
for satz in ("My password is hunter2", "Sam has a doctor's appointment", "According to the email the bill is due",
             "Sam is pregnant", "My credit card ends in 1234"):
    pruef("Lernen gesperrt: " + satz, bool(gd.TABU_LERNEN.search(satz)))
pruef("Lernen frei: harmloser Satz", not gd.TABU_LERNEN.search("Sam prefers the living room lights warm"))
gd.setze_sprache("de")
pruef("Zurueck auf Deutsch", gd.export_txt(T, "alex", NAMEN).startswith("# Jarvis-Gedächtnis für Alex"))

sz.setze_sprache("en")
LICHT = {"werkzeug": "geraet_steuern", "argumente": {"entity_id": "light.hall", "dienst": "turn_off"}}
PUSH = {"werkzeug": "nachricht", "argumente": {"aktion": "senden", "kanal": "push", "an": "Sam", "text": "Dinner"}}
pruef("Szene: Geraet", sz.beschreibung(LICHT, {"light.hall": "Hall light"}) == "Hall light: off")
pruef("Szene: Push", sz.beschreibung(PUSH) == "Push to Sam: “Dinner”", sz.beschreibung(PUSH))
pruef("Szene: Durchsage", sz.beschreibung({"werkzeug": "nachricht", "argumente": dict(PUSH["argumente"], kanal="durchsage",
                                                                                     an="kitchen")})
      == "Announcement to kitchen: “Dinner”")
pruef("Szene: Musik", sz.beschreibung({"werkzeug": "musik", "argumente": {"suche": "Jazz", "lautsprecher": "kitchen"}})
      == "Music “Jazz” on kitchen")
pruef("Szene: warten", sz.beschreibung({"werkzeug": "warten", "argumente": {"sekunden": 5}}) == "Wait 5 seconds")
pruef("Szene: Lautstaerke", sz.beschreibung({"werkzeug": "geraet_steuern", "argumente": {
    "entity_id": "media_player.a", "dienst": "volume_set", "daten": {"volume_level": 0.3}}}, {}) == "media_player.a: volume 30 %")
pruef("Szene: Fehler englisch", "is not possible in a scene" in wirft(sz.schritte_pruefen, [{"werkzeug": "homelab_auftrag"}]))
pruef("Szene: Name englisch", "too long" in wirft(sz.name_pruefen, "x" * 41))
pruef("Szene: eigene Werkzeuge nicht vorgegeben", "hoerspiel" not in sz.ERLAUBT and "morgenradio" not in sz.ERLAUBT)
sz.speichern(T, "Good night", [LICHT], "alex")
pruef("Szene finden: my scene", sz.finden(sz.laden(T), "my scene good night")["name"] == "Good night")
pruef("Szene finden: die Szene", sz.finden(sz.laden(T), "die Szene good night")["name"] == "Good night")
sz.setze_sprache("de")
pruef("Szene zurueck auf Deutsch", sz.beschreibung(PUSH) == "Push an Sam: „Dinner“")
shutil.rmtree(T)
print("Sprache 0.4: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
