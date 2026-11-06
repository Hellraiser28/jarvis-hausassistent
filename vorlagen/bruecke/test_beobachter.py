#!/usr/bin/env python3
"""Baustein beobachter.py („Sag mir Bescheid, wenn …“, seit 0.7): Bedingungen, Anlegen mit Grenzen, Melden genau
einmal, Zustellfehler, Verfall, Werkzeug-Einstieg auftrag() mit Kamera-/Babyfon-Sperre, Texte auf Deutsch und
Englisch. Testordner, Zustände und Meldungen sind Attrappen; kein Home Assistant, keine Netzzugriffe."""
import io
import os
import re
import sys
import tempfile
import time
import urllib.error

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import beobachter as bo  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:300]) if info and not bed else ""))


T = tempfile.mkdtemp(prefix="beobachter-")
D = os.path.join(T, "bo")
os.makedirs(D)

# ---------------------------------------------------------------- Bedingungen
pruef("B1 Bedingungen", bo.erfuellt("gleich", "off|standby", "standby") and not bo.erfuellt("gleich", "off", "on")
      and bo.erfuellt("nicht", "run", "finished") and not bo.erfuellt("nicht", "run", "unavailable")
      and bo.erfuellt("unter", "0", "-1,5") and not bo.erfuellt("unter", "0", "2") and bo.erfuellt("ueber", "25", "25.5")
      and not bo.erfuellt("ueber", "25", "unknown") and bo.erfuellt("aendert", "", "open", "closed")
      and not bo.erfuellt("aendert", "", "closed", "closed") and not bo.erfuellt("aendert", "", "unavailable", "closed"))
pruef("B1b unavailable nur, wenn genau danach gefragt", bo.erfuellt("gleich", "unavailable", "unavailable")
      and not bo.erfuellt("nicht", "on", "unknown") and not bo.erfuellt("unter", "5", "") and not bo.erfuellt("x", "1", "0"))

# ---------------------------------------------------------------- Anlegen
fehlt = [bo.neu(D, "alex", "sensor.x", "kaputt", "1", "", 1, "0"), bo.neu(D, "alex", "Licht Flur", "gleich", "on", "", 1, "off"),
         bo.neu(D, "alex", "sensor.x", "unter", "kalt", "", 1, "3"), bo.neu(D, "alex", "sensor.x", "gleich", "", "", 1, "on")]
schon = bo.neu(D, "alex", "sensor.aussen", "unter", "5", "", 1, "3.5")
pruef("B2 ungueltig und schon erfuellt werden abgelehnt", [f[0] for f in fehlt] == [False] * 4 and not schon[0]
      and "schon so" in schon[1], (fehlt, schon))
pruef("B2b Texte der Ablehnungen", fehlt[0][1].startswith("Bedingung muss eine von gleich, nicht")
      and "gültige Entität" in fehlt[1][1] and "Zahl" in fehlt[2][1] and fehlt[3][1] == "Auf welchen Zustand soll ich achten?",
      [f[1] for f in fehlt])
j0 = 1_800_000_000
okn, txt = bo.neu(D, "alex", "sensor.waschmaschine", "nicht", "run", "Die Wäsche ist fertig.", 99, "run", "Waschmaschine",
                  jetzt=j0)
e = bo.liste(D, "alex", j0)[0]
pruef("B3 angelegt, hoechstens 24 h, Ansage nennt Nr. und Dauer", okn and e["bis"] - e["seit"] == 24 * 3600
      and txt == "Mach ich: Ich sag dir Bescheid, sobald Waschmaschine nicht mehr „run“ ist (Nr. 1, längstens 24 h).",
      (txt, e))
_, txt2 = bo.neu(D, "alex", "sensor.aussen", "unter", "0", "", 1.5, "3.5", "Außentemperatur", jetzt=j0)
pruef("B3b Dauer mit Komma, 'unter' in der Ansage", txt2.endswith("sobald Außentemperatur unter 0 fällt (Nr. 2, längstens 1,5 h).")
      and bo.neu(D, "alex", "sensor.y", "aendert", "", "", "kaputt", "a", jetzt=j0)[0], txt2)
bo.loeschen(D, "alex", 0)
for i in range(10):
    bo.neu(D, "alex", "sensor.aussen", "unter", str(-10 - i), "", 2, "3.5", jetzt=j0)
zuviel = bo.neu(D, "alex", "sensor.aussen", "unter", "-50", "", 2, "3.5", jetzt=j0)
bo.neu(D, "sam", "cover.garagentor", "aendert", "", "", 1, "closed", jetzt=j0)
pruef("B4 hoechstens 10 je Person, andere Person unberuehrt", not zuviel[0] and len(bo.liste(D, "alex", j0)) == 10
      and len(bo.liste(D, "sam", j0)) == 1 and "10 Beobachter" in zuviel[1], zuviel)
pruef("B4b einzelnen loeschen, unbekannte Nr.", bo.loeschen(D, "alex", 3) == "1 Beobachter gelöscht."
      and bo.loeschen(D, "alex", 3) == "Da war kein passender Beobachter." and bo.loeschen(D, "kim", 0)
      == "Da war kein passender Beobachter." and len(bo.liste(D, "alex", j0)) == 9)
bo.loeschen(D, "alex", 0)
pruef("B5 alle eigenen loeschen laesst die von Sam stehen", bo.liste(D, "alex", j0) == [] and len(bo.liste(D, "sam", j0)) == 1)

# ---------------------------------------------------------------- Pruefen und Melden
bo.neu(D, "alex", "sensor.waschmaschine", "nicht", "run", "Die Wäsche ist fertig.", 5, "run", jetzt=j0)
gemeldet = []
st = {"sensor.waschmaschine": "run", "cover.garagentor": "closed"}
melder = lambda p, t, x: gemeldet.append((p, t, x))  # noqa: E731
bo.pruefen(D, lambda eid: st[eid], melder, jetzt=j0 + 30)
pruef("B6 nichts passiert: keine Meldung", gemeldet == [])
st["sensor.waschmaschine"] = "finished"
a = bo.pruefen(D, lambda eid: st[eid], melder, jetzt=j0 + 60)
bo.pruefen(D, lambda eid: st[eid], melder, jetzt=j0 + 90)
pruef("B7 meldet genau einmal an die Person, danach weg", gemeldet == [("alex", "Jarvis: Bescheid", "Die Wäsche ist fertig.")]
      and len(a) == 1 and a[0]["ausgeloest"] == "finished" and bo.liste(D, "alex", j0 + 90) == []
      and len(bo.liste(D, "sam", j0 + 90)) == 1, gemeldet)
bo.neu(D, "alex", "sensor.waschmaschine", "gleich", "run", "", 1, "finished", jetzt=j0)
st["sensor.waschmaschine"] = "run"


def wirft(p, t, x):
    raise RuntimeError("Netz weg")


bo.pruefen(D, lambda eid: st[eid], wirft, jetzt=j0 + 100)
pruef("B8 Zustellfehler: bleibt fuer den naechsten Versuch", len(bo.liste(D, "alex", j0 + 100)) == 1)
bo.pruefen(D, lambda eid: st[eid], melder, jetzt=j0 + 7200)
pruef("B9 verfallen: still weg, keine Meldung, keine Reste", bo.liste(D, "alex", j0 + 7200) == [] and len(gemeldet) == 1
      and not [n for n in os.listdir(D) if ".neu" in n], (gemeldet, os.listdir(D)))
bo.neu(D, "alex", "cover.garagentor", "aendert", "", "", 1, "closed", "Garagentor", jetzt=j0 + 7200)
st["cover.garagentor"] = "open"


def zustand_wirft(eid):
    raise OSError("HA weg")


bo.pruefen(D, zustand_wirft, melder, jetzt=j0 + 7230)
pruef("B9b HA nicht erreichbar: keine Meldung, Beobachter bleibt", len(gemeldet) == 1 and len(bo.liste(D, "alex", j0 + 7230)) == 1)
bo.pruefen(D, lambda eid: st[eid], melder, jetzt=j0 + 7260)
pruef("B9c Standardtext ohne eigenen Text", gemeldet[-1] == ("alex", "Jarvis: Bescheid", "Garagentor steht jetzt auf „open“."),
      gemeldet[-1])

# ---------------------------------------------------------------- Werkzeug-Einstieg auftrag()
D2 = os.path.join(T, "auftrag")
os.makedirs(D2)
ZUSTAND = {"sensor.waschmaschine": {"state": "run", "attributes": {"friendly_name": "Waschmaschine"}},
           "sensor.aussen": {"state": "3.5", "attributes": {"friendly_name": "Außentemperatur"}},
           "binary_sensor.kamera_flur_bewegung": {"state": "off", "attributes": {}}}
gelesen = []


def ha_attrappe(eid):
    gelesen.append(eid)
    if eid not in ZUSTAND:
        raise urllib.error.HTTPError("x", 404, "Not Found", {}, io.BytesIO(b""))
    return ZUSTAND[eid]


logs = []
r1 = bo.auftrag(D2, "alex", {"aktion": "neu", "entity_id": "sensor.waschmaschine", "bedingung": "nicht", "wert": "run",
                             "text": "Wäsche fertig."}, ha_attrappe, log=lambda *x: logs.append(x), jetzt=j0)
gesperrt = [bo.auftrag(D2, "alex", {"aktion": "neu", "entity_id": e, "bedingung": "aendert"}, ha_attrappe, jetzt=j0)
            for e in ("camera.flur", "image.tuer", "binary_sensor.babyfon_ton", "binary_sensor.kamera_flur_bewegung",
                      "sensor.baby_monitor_temperatur")]
r4 = bo.auftrag(D2, "alex", {"aktion": "neu", "entity_id": "sensor.gibtsnicht", "bedingung": "aendert"}, ha_attrappe, jetzt=j0)
r5 = bo.auftrag(D2, "sam", {"aktion": "neu", "entity_id": "sensor.aussen", "bedingung": "unter", "wert": "0"}, ha_attrappe,
                jetzt=j0)
r6 = bo.auftrag(D2, "alex", {"aktion": "neu", "entity_id": "sensor.aussen", "bedingung": "unter", "wert": "0"},
                zustand_wirft, jetzt=j0)
r7 = bo.auftrag(D2, "alex", {"aktion": "neu", "entity_id": "Sensor Flur"}, ha_attrappe, jetzt=j0)
pruef("B10 auftrag legt an (Name aus HA), Kamera/Babyfon/unbekannt/HA weg/ungueltig abgelehnt",
      r1.startswith("Mach ich") and "Waschmaschine" in r1 and all(g == "Kameras und Babyfon beobachte ich nicht." for g in gesperrt)
      and r4 == "Die Entität sensor.gibtsnicht kenne ich nicht (HA: 404)." and r5.startswith("Mach ich")
      and r6 == "Home Assistant antwortet gerade nicht (OSError)." and "gültige Entität" in r7, (r1, gesperrt, r4, r5, r6, r7))
pruef("B10b Kameras und Babyfon werden gar nicht erst gelesen", not [g for g in gelesen if "kamera" in g or "camera" in g
      or "baby" in g or g.startswith("image.")], gelesen)
pruef("B10c Log beim Anlegen ohne Text des Auftrags", len(logs) == 1 and "sensor.waschmaschine" in logs[0]
      and "Wäsche fertig." not in logs[0], logs)
lst = bo.auftrag(D2, "alex", {"aktion": "liste"}, ha_attrappe, jetzt=j0)
bis = time.strftime("%H:%M", time.localtime(j0 + 24 * 3600))
pruef("B11 Liste zeigt nur die eigenen", lst == "Nr. 1: Waschmaschine nicht mehr „run“ ist (bis %s Uhr) – „Wäsche fertig.“" % bis,
      lst)
pruef("B11b ohne aktion: Liste; unbekannte aktion; loeschen mit kaputter Nr. = alle eigenen",
      bo.auftrag(D2, "alex", {}, ha_attrappe, jetzt=j0) == lst
      and bo.auftrag(D2, "alex", {"aktion": "schalten"}, ha_attrappe) == "aktion muss neu, liste oder loeschen sein."
      and bo.auftrag(D2, "alex", {"aktion": "loeschen", "nr": "x"}, ha_attrappe) == "1 Beobachter gelöscht."
      and bo.auftrag(D2, "alex", {"aktion": "liste"}, ha_attrappe, jetzt=j0) == "Keine Beobachter aktiv."
      and bo.auftrag(D2, "alex", "kaputt", ha_attrappe, jetzt=j0) == "Keine Beobachter aktiv."
      and len(bo.liste(D2, "sam", j0)) == 1)
pruef("B11c gesperrt(): Domaenen und Namensteile", bo.gesperrt("camera.x") and bo.gesperrt("image.x")
      and bo.gesperrt("sensor.babyphone_akku") and not bo.gesperrt("sensor.waschmaschine") and not bo.gesperrt("cover.garagentor"))

# ---------------------------------------------------------------- Englisch
try:
    bo.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", True)
bo.setze_sprache("en")
D3 = os.path.join(T, "en")
os.makedirs(D3)
en = [bo.neu(D3, "kim", "sensor.x", "kaputt", "1", "", 1, "0")[1], bo.neu(D3, "kim", "Licht", "gleich", "on", "", 1, "off")[1],
      bo.neu(D3, "kim", "sensor.x", "unter", "cold", "", 1, "3")[1], bo.neu(D3, "kim", "sensor.x", "gleich", "", "", 1, "on")[1],
      bo.neu(D3, "kim", "sensor.aussen", "unter", "5", "", 1, "3.5", "Outside temperature")[1]]
_, en_ok = bo.neu(D3, "kim", "sensor.washer", "nicht", "run", "", 1.5, "run", "Washing machine", jetzt=j0)
_, en_ok2 = bo.neu(D3, "kim", "sensor.aussen", "unter", "0", "Bring the plants in.", 2, "3.5", "Outside temperature", jetzt=j0)
pruef("EN: Meldungen beim Anlegen", en == ["bedingung must be one of gleich, nicht, unter, ueber, aendert.",
                                          "I need a valid entity (e.g. sensor.washing_machine_status).",
                                          "For below and above I need a number.", "Which state should I watch for?",
                                          "That's already the case (Outside temperature is “3.5”)."]
      and en_ok == "Will do: I'll let you know as soon as Washing machine is no longer “run” (no. 1, for at most 1.5 h).",
      (en, en_ok))
pruef("EN: Beschreibungen", [bo.beschreibung({"bedingung": b, "wert": "on"}) for b in bo.BEDINGUNGEN + ("x",)]
      == ["is “on”", "is no longer “on”", "drops below on", "rises above on", "changes", "?"])
lst_en = bo.auftrag(D3, "kim", {"aktion": "liste"}, ha_attrappe, jetzt=j0)
pruef("EN: Liste", lst_en == "No. 1: Washing machine is no longer “run” (until %s)\nNo. 2: Outside temperature drops below 0 "
      "(until %s) – “Bring the plants in.”" % (time.strftime("%H:%M", time.localtime(j0 + 1.5 * 3600)),
                                              time.strftime("%H:%M", time.localtime(j0 + 2 * 3600))), lst_en)
gemeldet.clear()
bo.pruefen(D3, lambda eid: {"sensor.washer": "finished", "sensor.aussen": "1"}[eid], melder, jetzt=j0 + 30)
pruef("EN: Meldung mit Standardtext und englischem Titel", gemeldet == [("kim", "Jarvis: Heads-up", "Washing machine is now “finished”.")],
      gemeldet)
en_auftrag = [bo.auftrag(D3, "kim", {"aktion": "neu", "entity_id": "camera.door", "bedingung": "aendert"}, ha_attrappe),
              bo.auftrag(D3, "kim", {"aktion": "neu", "entity_id": "sensor.gibtsnicht", "bedingung": "aendert"}, ha_attrappe),
              bo.auftrag(D3, "kim", {"aktion": "neu", "entity_id": "sensor.aussen", "bedingung": "unter", "wert": "0"},
                         zustand_wirft),
              bo.auftrag(D3, "kim", {"aktion": "schalten"}, ha_attrappe),
              bo.auftrag(D3, "kim", {"aktion": "loeschen", "nr": 2}, ha_attrappe),
              bo.auftrag(D3, "kim", {"aktion": "loeschen", "nr": 2}, ha_attrappe),
              bo.auftrag(D3, "kim", {"aktion": "liste"}, ha_attrappe, jetzt=j0)]
pruef("EN: Werkzeug-Einstieg", en_auftrag == ["I don't watch cameras or baby monitors.",
                                             "I don't know the entity sensor.gibtsnicht (HA: 404).",
                                             "Home Assistant isn't responding right now (OSError).",
                                             "aktion must be neu, liste or loeschen.", "1 watcher deleted.",
                                             "There was no matching watcher.", "No watchers active."], en_auftrag)
for i in range(3):
    bo.neu(D3, "kim", "sensor.aussen", "unter", str(-i), "", 1, "3.5", jetzt=j0)
pruef("EN: Mehrzahl beim Loeschen und Grenze", bo.loeschen(D3, "kim", 0) == "3 watchers deleted."
      and bo.neu(D3, "kim", "sensor.aussen", "unter", "-1", "", 1, "3.5", jetzt=j0)[0])
for i in range(9):
    bo.neu(D3, "kim", "sensor.aussen", "unter", str(-10 - i), "", 1, "3.5", jetzt=j0)
grenze = bo.neu(D3, "kim", "sensor.aussen", "unter", "-50", "", 1, "3.5", jetzt=j0)[1]
pruef("EN: zu viele", grenze == "You already have 10 watchers running, delete one first.", grenze)
alle_en = en + [en_ok, en_ok2, lst_en, grenze] + [x for _, _, x in gemeldet] + en_auftrag
deutsch = [m for m in alle_en if re.search(r"[äöüÄÖÜß„]|\b(ist|nicht|Bitte|bitte|kenne|Uhr|Beobachter|Bescheid)\b",
                                            m.replace("“nicht", "").replace("nicht, ", ""))]
pruef("EN: kein deutscher Rest in den Meldungen", not deutsch, deutsch)
bo.setze_sprache("de")
pruef("Zurueck auf Deutsch", bo.loeschen(D3, "kim", 0) == "10 Beobachter gelöscht."
      and bo.beschreibung({"bedingung": "aendert"}) == "sich ändert")

import shutil  # noqa: E402
shutil.rmtree(T, ignore_errors=True)
print("Beobachter: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
