#!/usr/bin/env python3
"""Baustein ankunft.py (Nachrichten beim Heimkommen, seit 0.6): Konfiguration, Ankunft erkennen (WLAN-Aussetzer zaehlen
nicht), Auftraege anlegen, vormerken, zustellen, aufraeumen, Zustelltexte auf Deutsch und Englisch.
Testordner und Attrappen fuer die Tracker, kein Home Assistant, keine Netzzugriffe."""
import json
import os
import stat
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import ankunft as ak  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


T = tempfile.mkdtemp(prefix="ankunft-")
KONFIG = {"personen": {"mia": {"name": "Mia", "kontakt": "Mia", "tracker": ["device_tracker.mia_a", "device_tracker.mia_b"]},
                       "ben": {"name": "Ben", "tracker": ["device_tracker.ben"]},
                       "anna": {"name": "Anna", "tracker": ["device_tracker.anna"]},
                       "tom": {"name": "Tom", "tracker": ["sensor.kein_tracker"]}},
          "raum": "flur", "min_weg_minuten": 30, "verzoegerung_s": 60}
json.dump(KONFIG, open(os.path.join(T, "anwesenheit.json"), "w"))
k = ak.konfig_laden(os.path.join(T, "anwesenheit.json"))

# ---------------------------------------------------------------- Konfiguration
pruef("A1 ohne Datei keine Personen (Funktion aus), Standardwerte", ak.konfig_laden(os.path.join(T, "fehlt.json")) ==
      {"personen": {}, "raum": ak.RAUM, "min_weg_s": 1800, "verzoegerung_s": 60})
pruef("A2 Konfig gelesen, 30 min in Sekunden, Raum aus der Datei", set(k["personen"]) == {"mia", "ben", "anna"}
      and k["min_weg_s"] == 1800 and k["raum"] == "flur", k)
pruef("Konfig: ohne device_tracker keine Person", "tom" not in k["personen"])
pruef("Konfig: kontakt faellt auf den Namen zurueck", k["personen"]["ben"]["kontakt"] == "Ben")
pruef("Person per Name oder Schluessel", ak.person_finden(k, "MIA") == "mia" and ak.person_finden(k, " ben ") == "ben"
      and ak.person_finden(k, "Oma") is None)

# ---------------------------------------------------------------- Ankunft erkennen
Z = {}
staende = {"device_tracker.mia_a": "not_home", "device_tracker.mia_b": "unavailable", "device_tracker.ben": "home",
           "device_tracker.anna": "unknown"}
lesen = lambda e: {"state": staende.get(e, "unknown")}  # noqa: E731
t0 = 1_000_000
pruef("A3 erster Blick ist nur Ausgangslage", ak.pruefen(k, Z, lesen, t0) == [] and Z["mia"]["da"] is False
      and Z["ben"]["da"] is True and "anna" not in Z, Z)
staende["device_tracker.mia_b"] = "home"
pruef("A4 nach 10 Minuten zurueck (WLAN-Aussetzer): keine Ankunft", ak.pruefen(k, Z, lesen, t0 + 600) == [] and Z["mia"]["da"])
staende["device_tracker.mia_b"] = "not_home"
ak.pruefen(k, Z, lesen, t0 + 700)
staende["device_tracker.mia_a"] = "home"
pruef("A5 nach 35 Minuten weg: Ankunft", ak.pruefen(k, Z, lesen, t0 + 700 + 2100) == ["mia"])
staende["device_tracker.ben"] = "unavailable"
pruef("A6 unavailable aendert nichts", ak.pruefen(k, Z, lesen, t0 + 5000) == [] and Z["ben"]["da"] is True)
pruef("A7 ein Tracker home reicht", ak.anwesend(["x", "y"], lambda e: {"state": "home" if e == "y" else "not_home"}) is True)
pruef("Anwesend: nur unbekannt -> None, Lesefehler zaehlt nicht",
      ak.anwesend(["x", "y"], lambda e: (_ for _ in ()).throw(OSError()) if e == "x" else "unknown") is None)
pruef("Anwesend: Zustand auch als blosser Text", ak.anwesend(["x"], lambda e: "not_home") is False)

# ---------------------------------------------------------------- Auftraege
L, meld = ak.auftrag_neu([], k, "Oma", "Hallo", "anna")
pruef("A8 unbekannte Person: Liste der bekannten", L == [] and "Mia" in meld and "Ben" in meld, meld)
L, meld = ak.auftrag_neu([], ak.konfig_laden(os.path.join(T, "fehlt.json")), "Mia", "Hallo", "anna")
pruef("Ohne Konfiguration: noch niemand bekannt", L == [] and meld.endswith("Ich kenne: noch niemand."), meld)
L, meld = ak.auftrag_neu([], k, "Mia", "", "anna")
pruef("A9 ohne Text fuer ankommer: Rueckfrage", L == [] and meld.startswith("Was soll ich Mia"), meld)
L, meld = ak.auftrag_neu([], k, "Mia", "Hallo", "anna", raum="Dachboden", raum_gueltig=lambda r: r == "flur")
pruef("Unbekannter Raum abgelehnt", L == [] and "dachboden" in meld and "kenne ich nicht" in meld, meld)
L, meld = ak.auftrag_neu([], k, "mia", "Das Essen   steht im Ofen.", "anna", kanal="fax", jetzt=t0)
pruef("A10a Auftrag: Text bereinigt, Kanal unbekannt -> auto, gilt 7 Tage", L[0]["text"] == "Das Essen steht im Ofen."
      and L[0]["kanal"] == "auto" and L[0]["bis"] == t0 + 7 * 86400 and len(L[0]["id"]) == 8, L)
pruef("A10b Bestaetigung freundlich", meld == "Mach ich. Wenn Mia nach Hause kommt, richte ich es aus.", meld)
L, meld = ak.auftrag_neu(L, k, "Ben", "", "anna", fuer="mich", immer=True, jetzt=t0)
pruef("A10c Bescheid an mich, jedes Mal, ohne Ablauf", L[1]["fuer"] == "mich" and L[1]["bis"] is None
      and meld == "Mach ich. Jedes Mal, wenn Ben nach Hause kommt, sage ich dir Bescheid.", meld)
L, _ = ak.auftrag_neu(L, k, "Mia", "Zähne putzen!", "ben", jetzt=t0)
pruef("A10d drei Auftraege", len(L) == 3)
pruef("Jede Person sieht nur ihre eigenen", [a["wer"] for a in ak.fuer_person(L, "anna")] == ["mia", "ben"]
      and [a["wer"] for a in ak.fuer_person(L, "ben")] == ["mia"] and ak.fuer_person(L, "") == [])
pruef("Beschreibung", ak.beschreiben(L[0], k) == "an Mia beim Heimkommen: Das Essen steht im Ofen."
      and ak.beschreiben(L[1], k) == "Bescheid, wenn Ben heimkommt (jedes Mal)", [ak.beschreiben(a, k) for a in L])
n = ak.ankunft_vormerken(L, "mia", 60, t0 + 100)
pruef("A11 Ankunft Mia merkt beide Mia-Auftraege vor, faellig erst nach der Verzoegerung",
      n == 2 and ak.faellig(L, t0 + 120) == [] and len(ak.faellig(L, t0 + 161)) == 2)
pruef("Schon vorgemerkte werden nicht nochmal vorgemerkt", ak.ankunft_vormerken(L, "mia", 60, t0 + 130) == 0)
a0 = L[0]
L2 = ak.erledigt(L, a0, t0 + 200)
ak.ankunft_vormerken(L2, "ben", 0, t0 + 200)
L3 = ak.erledigt(L2, [x for x in L2 if x["wer"] == "ben"][0], t0 + 210)
ben = [x for x in L3 if x["wer"] == "ben"]
pruef("A12 einmalige verschwinden, wiederkehrende bleiben ohne Vormerkung", a0 not in L2 and len(ben) == 1
      and "ausloesen_ab" not in ben[0] and ben[0]["zuletzt"] == t0 + 210)
alt = dict(L[2], bis=t0 - 1)
alt.pop("ausloesen_ab", None)
pruef("A13 abgelaufene einmalige werden aufgeraeumt, vorgemerkte und wiederkehrende bleiben",
      ak.aufraeumen([alt, dict(alt, ausloesen_ab=t0), L[1]], t0) == [dict(alt, ausloesen_ab=t0), L[1]])
t1 = ak.zustelltext(L[0], k, "Anna")
t2 = ak.zustelltext(dict(L[0], von="mia"), k, "Mia")
t3 = ak.zustelltext(L[1], k, "Anna")
t4 = ak.zustelltext(dict(L[1], text="Der Kuchen ist da."), k, "Anna")
pruef("A14 Zustelltexte", t1 == "Willkommen zu Hause, Mia. Anna lässt ausrichten: Das Essen steht im Ofen."
      and t2 == "Willkommen zu Hause, Mia. Du wolltest daran denken: Das Essen steht im Ofen."
      and t3 == "Ben ist gerade nach Hause gekommen." and t4 == "Ben ist gerade nach Hause gekommen. Der Kuchen ist da.",
      (t1, t2, t3, t4))

# ---------------------------------------------------------------- Speichern
pz, pa = os.path.join(T, "ankunft_zustand.json"), os.path.join(T, "ankunft.json")
ak.zustand_speichern(pz, Z)
ak.auftraege_speichern(pa, L3)
pruef("Speichern: Zustand und Auftraege zurueckgelesen, Rechte 600", ak.zustand_laden(pz) == json.loads(json.dumps(Z))
      and ak.auftraege_laden(pa) == L3 and stat.S_IMODE(os.stat(pa).st_mode) == 0o600
      and stat.S_IMODE(os.stat(pz).st_mode) == 0o600 and not os.path.exists(pa + ".neu"))
open(pz, "w").write("[1, 2]")
pruef("Kaputte oder fehlende Dateien: leer", ak.zustand_laden(pz) == {} and ak.auftraege_laden(os.path.join(T, "x")) == [])

# ---------------------------------------------------------------- Englisch
try:
    ak.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", True)
ak.setze_sprache("en")
_, m1 = ak.auftrag_neu([], k, "Oma", "Hi", "anna")
_, m2 = ak.auftrag_neu([], k, "Mia", "", "anna")
_, m3 = ak.auftrag_neu([], k, "Mia", "Hi", "anna", raum="attic", raum_gueltig=lambda r: False)
_, m4 = ak.auftrag_neu([], k, "Mia", "Dinner is in the oven.", "anna")
_, m5 = ak.auftrag_neu([], k, "Ben", "", "anna", fuer="mich", immer=True)
_, m6 = ak.auftrag_neu([], ak.konfig_laden(os.path.join(T, "fehlt.json")), "Mia", "Hi", "anna")
pruef("EN: Meldungen beim Anlegen", m1 == "For “Oma” I can't see when the person comes home. I know: Mia, Ben, Anna."
      and m2 == "What should I tell Mia?" and m3 == "I don't know the room “attic”."
      and m4 == "Will do. When Mia comes home, I'll pass it on."
      and m5 == "Will do. Every time Ben comes home, I'll let you know." and m6.endswith("I know: nobody yet."),
      (m1, m2, m3, m4, m5, m6))
e1 = ak.zustelltext(dict(L[0], text="Dinner is in the oven."), k, "Anna")
e2 = ak.zustelltext(dict(L[0], text="Dinner is in the oven.", von="mia"), k, "Mia")
e3 = ak.zustelltext(dict(L[1], text="Cake is here."), k, "Anna")
pruef("EN: Zustelltexte", e1 == "Welcome home, Mia. Anna asked me to tell you: Dinner is in the oven."
      and e2 == "Welcome home, Mia. You wanted to remember: Dinner is in the oven." and e3 == "Ben just got home. Cake is here.",
      (e1, e2, e3))
pruef("EN: Beschreibung", ak.beschreiben(L[0], k) == "to Mia on arriving home: Das Essen steht im Ofen."
      and ak.beschreiben(L[1], k) == "Let you know when Ben gets home (every time)", [ak.beschreiben(a, k) for a in L])
ak.setze_sprache("de")
pruef("Zurueck auf Deutsch", ak.zustelltext(L[1], k, "Anna") == "Ben ist gerade nach Hause gekommen.")

print("Ankunft: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
