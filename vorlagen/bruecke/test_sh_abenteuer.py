#!/usr/bin/env python3
"""Haus-Abenteuer (S9, bruecke/abenteuer.py, seit 0.7).

A1-A27 mit der Attrappe sh_attrappe.Kontext: eigener Raumplan mit Lampen (darunter Fallen: Steckdose als Lampe, reine
An/Aus-Lampe, switch.* im Bereich, nicht verfuegbare Lampe), Uhrzeit ueber ctx._jetzt, kein Netz, kein Claude, kein HA.
Geprueft wird vor allem die Positivliste: Jeder Aufruf an Home Assistant ist light.turn_on/turn_off auf einer erlaubten
Lampe, und am Ende ist jede Lampe wieder wie vorher. raum_lichter() der Attrappe steht fuer die Lampen-Positivliste der
Bruecke (daten/abenteuer_lampen.json geschnitten mit dem HA-Bereich).
A28-A31 (seit 0.7): Lautsprecher-Sperre, weitere Tabu-Namen, Schlafraeume nach Namen, Englisch.

Aufruf: python3 -B tests/test_sh_abenteuer.py
"""
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

HIER = os.path.dirname(os.path.abspath(__file__))
ZWEIG = os.path.dirname(HIER)
sys.path.insert(0, os.path.join(ZWEIG, "bruecke"))
sys.path.insert(0, HIER)
import sh_attrappe  # noqa: E402

wache = sh_attrappe.live_wache()
import abenteuer as ab  # noqa: E402
import fremdtext as ft  # noqa: E402  (nur lesen: die echte Einordnung pruefen)

pruef, ergebnis = sh_attrappe.pruefer()
KONTEXTE = []


def uhr(stunde, minute=0, tag=7):
    return time.mktime((2026, 11, tag, stunde, minute, 0, 0, 0, -1))


RAEUME = {"version": 1, "raeume": {
    "wohnzimmer": {"name": "Wohnzimmer", "alias": ["stube"], "bereich": "Wohnzimmer", "ausgabe": [{"art": "ma"}],
                   "licht": ["light.wohnzimmer_decke", "light.wohnzimmer_stehlampe", "light.tv_ecke_steckdose",
                             "light.wohnzimmer_strip"]},
    "kueche": {"name": "Küche", "bereich": "Küche", "ausgabe": [{"art": "echo"}], "licht": ["light.kueche"]},
    "keller": {"name": "Keller", "bereich": "Keller", "ausgabe": [], "licht": ["light.keller"]},
    "schlafzimmer": {"name": "Schlafzimmer", "bereich": "Schlafzimmer", "ausgabe": [{"art": "echo"}],
                     "licht": ["light.schlafzimmer"]},
    "hausflur": {"name": "Hausflur", "bereich": "Hausflur", "ausgabe": [],
                 "licht": ["switch.receiver_steckdose", "light.flur_weg", "light.flur_receiver", "light.flur_spot",
                           "light.avr_led", "light.flur_band"]}}}
ZUSTAENDE = {
    "light.wohnzimmer_decke": {"state": "on", "attributes": {"supported_color_modes": ["xy", "color_temp"],
                                                             "color_mode": "xy", "xy_color": [0.41, 0.39],
                                                             "brightness": 200, "friendly_name": "Wohnzimmer Decke"}},
    "light.wohnzimmer_stehlampe": {"state": "off", "attributes": {"supported_color_modes": ["color_temp"],
                                                                  "friendly_name": "Stehlampe"}},
    "light.tv_ecke_steckdose": {"state": "on", "attributes": {"supported_color_modes": ["onoff"]}},
    "light.wohnzimmer_strip": {"state": "on", "attributes": {"supported_color_modes": ["onoff"],
                                                             "friendly_name": "Leiste hinten"}},
    "light.kueche": {"state": "on", "attributes": {"supported_color_modes": ["color_temp"], "color_mode": "color_temp",
                                                   "color_temp_kelvin": 3000, "brightness": 128}},
    "light.keller": {"state": "off", "attributes": {"supported_color_modes": ["hs"]}},
    "light.schlafzimmer": {"state": "off", "attributes": {"supported_color_modes": ["rgb"]}},
    "switch.receiver_steckdose": {"state": "on", "attributes": {}},
    "light.flur_weg": {"state": "unavailable", "attributes": {"supported_color_modes": ["hs"]}},
    "light.flur_receiver": {"state": "on", "attributes": {"supported_color_modes": ["hs"], "friendly_name": "Receiver Licht"}},
    "light.flur_spot": {"state": "off", "attributes": {"supported_color_modes": ["onoff"], "friendly_name": "Flur Spot"}},
    "light.avr_led": {"state": "on", "attributes": {"supported_color_modes": ["hs"], "friendly_name": "LED-Band"}},
    "light.flur_band": {"state": "on", "attributes": {"supported_color_modes": ["hs"],
                                                      "friendly_name": "Steckdosenleiste Flur"}},
}
ERLAUBT = {"light.wohnzimmer_decke", "light.wohnzimmer_stehlampe", "light.kueche", "light.keller", "light.schlafzimmer"}


def station(raum, raetsel, antworten, farbe, durchsage="", leinwand=""):
    return {"raum": raum, "raetsel": raetsel, "antworten": antworten,
            "hinweise": ["Schaut genau hin.", "Es ist ganz in eurer Nähe."],
            "effekt": {"farbe": farbe, "durchsage": durchsage, "leinwand": leinwand}}


PLAN = {"titel": "Das Geheimnis der Glühwürmchen",
        "intro": "Die Glühwürmchen des Hauses sind verschwunden. Nur ihr könnt sie finden!",
        "stationen": [
            station("wohnzimmer", "Ich werde kürzer, je länger ich brenne. Was bin ich?", ["Kerze", "Kerzen"], "blau",
                    "Psst, im Wohnzimmer flackert etwas!", "Station 1: Das flackernde Rätsel"),
            station("Küche", "Wie viele Monate hat ein Jahr?", ["12", "zwölf"], "gruen", "Kommt in die Küche!",
                    "Station 2: Die Zahlenküche"),
            station("keller", "Ich öffne Türen, habe aber keine Hand. Was bin ich?", ["Schlüssel"], "rot",
                    "Hier unten ist es dunkel …", "Station 3: Der Kellerschatz"),
            station("stube", "Ich habe vier Beine und Kissen, aber laufe nie. Was bin ich?", ["Sofa", "Couch"],
                    "#ff00ff", "Zurück ins Wohnzimmer!", "Station 4: Das letzte Rätsel")],
        "finale": "Die Glühwürmchen sind zurück und leuchten golden. Ihr seid echte Detektive!"}


def plan_json(**aenderung):
    p = copy.deepcopy(PLAN)
    p.update(aenderung)
    return json.dumps(p, ensure_ascii=False)


def neuer_ctx(plan=None, pruefen=None, jetzt=None):
    a = {"abenteuer_plan": plan if plan is not None else plan_json()}
    if pruefen is not None:
        a["abenteuer_pruefen"] = pruefen
    c = sh_attrappe.Kontext(antworten=a, zustaende=copy.deepcopy(ZUSTAENDE), raeume=copy.deepcopy(RAEUME),
                            jetzt=jetzt if jetzt is not None else uhr(15))
    KONTEXTE.append((c, c.daten))
    return c


def spiel(ctx):
    return ab.laden(ctx)


def dateihash(ctx):
    return hashlib.sha256(open(os.path.join(ctx.daten, "abenteuer", "spiel.json"), "rb").read()).hexdigest()


def nur_licht(ctx, erlaubt=ERLAUBT):
    """Jeder HA-Aufruf: light.turn_on/off auf einer erlaubten Lampe, nur erlaubte Felder."""
    for d, s, daten in ctx.dienste:
        felder = set(daten) - {"entity_id"}
        if d != "light" or s not in ab.LICHT_DIENSTE or daten.get("entity_id") not in erlaubt \
                or not felder <= ab.LICHT_DIENSTE[s]:
            return False
    return True


# ---------------------------------------------------------------- A1 Import, Schnittstelle
leer = tempfile.mkdtemp(prefix="sh-import-")
r = subprocess.run([sys.executable, "-I", "-B", "-c", "import sys; sys.path.insert(0, %r); import abenteuer; "
                    "print('%%d.%%d' %% sys.version_info[:2])" % os.path.join(ZWEIG, "bruecke")],
                   cwd=leer, capture_output=True, text=True)
pruef("A1 Import ohne Fehler unter Python %s (mindestens 3.8), legt nichts an" % r.stdout.strip(),
      r.returncode == 0 and tuple(int(x) for x in (r.stdout.strip() or "0.0").split(".")) >= (3, 8)
      and os.listdir(leer) == [], r.stderr[-300:])
shutil.rmtree(leer, ignore_errors=True)
pruef("A1 NAME/RECHTE/TAKT", ab.NAME == "abenteuer" and ab.RECHTE == "familie" and ab.TAKT_S == 30)
pruef("A1 Schema", ab.WERKZEUG["schema"]["properties"]["aktion"]["enum"] == ["start", "antwort", "hinweis", "stand", "ende"]
      and ab.WERKZEUG["schema"]["properties"]["dauer_min"]["minimum"] == 15)
e = ab.FREMDTEXT["nur_lesen"]
eintrag = (e[0], e[1], frozenset(e[2]))
pruef("A1 Fremdtext (echte Logik): stand und leer lesen, start/antwort/hinweis/ende/unbekannt sind Ziel",
      ab.FREMDTEXT["art"] == "ziel" and all(ft._aktion(eintrag, a, streng=True) in eintrag[2]
                                            for a in ({"aktion": "stand"}, {}))
      and all(ft._aktion(eintrag, {"aktion": x}, streng=True) not in eintrag[2]
              for x in ("start", "antwort", "hinweis", "ende", "Stand", "zaubern")))

# ---------------------------------------------------------------- A2/A3 Antworten lokal pruefen
JA = [("Kerze", ["Kerze"]), ("die Kerze!", ["Kerze"]), ("KERZEN", ["Kerze", "Kerzen"]), ("zwölf", ["12"]),
      ("12", ["zwölf"]), ("Es sind zwoelf", ["12"]), ("Schlussel", ["Schlüssel"]), ("Schluessel", ["Schlüssel"]),
      ("ich glaube es ist der Kühlschrank", ["Kühlschrank"]), ("Kühlschrnk", ["Kühlschrank"]),
      ("einundzwanzig", ["21"]), ("hundertzwei", ["102"]), ("ein Sofa", ["Sofa"]), ("Ja", ["ja"]),
      ("der rote Apfel", ["roter Apfel", "Apfel"])]
NEIN_ = [("Tatze", ["Katze"]), ("13", ["12"]), ("nicht die Kerze", ["Kerze"]), ("Kerze oder Lampe", ["Kerze"]),
         ("Lampe", ["Kerze"]), ("", ["Kerze"]), ("zwei", ["12"]), ("Maus", ["Haus"]),
         ("das ist bestimmt irgendwas mit einer Kerze im Wohnzimmer auf dem Tisch", ["Kerze"])]
for eingabe, antw in JA:
    pruef("A2 richtig: %r ~ %r" % (eingabe, antw), ab.lokal_richtig(eingabe, antw))
for eingabe, antw in NEIN_:
    pruef("A2 nicht lokal: %r ~ %r" % (eingabe, antw), not ab.lokal_richtig(eingabe, antw))
pruef("A3 Zahlwörter", [ab.zahlwort(w) for w in ("null", "eins", "zwoelf", "siebzehn", "neunundneunzig", "hundert",
                                                 "dreihundertundeins", "tausend", "zweitausendsechzehn", "kerze")]
      == [0, 1, 12, 17, 99, 100, 301, 1000, 2016, None])

# ---------------------------------------------------------------- A4 Plan pruefen
info = {r: {"name": v["name"], "alias": v.get("alias") or []} for r, v in RAEUME["raeume"].items()}
plan, fehler = ab.plan_pruefen(json.loads(plan_json()), info)
pruef("A4 gültiger Plan, Räume über Name/Alias auf id", plan is not None and [s["raum"] for s in plan["stationen"]]
      == ["wohnzimmer", "kueche", "keller", "wohnzimmer"], fehler)
pruef("A4 Farben: Name, #hex", [s["effekt"]["farbe"] for s in plan["stationen"]] ==
      [[0, 80, 255], [0, 200, 40], [255, 0, 0], [255, 0, 255]])
p = json.loads(plan_json())
p["stationen"][2]["raum"] = "garten"
pruef("A4 unbekannter Raum: verworfen", ab.plan_pruefen(p, info)[0] is None and "garten" in ab.plan_pruefen(p, info)[1][0])
pruef("A4 Raum außerhalb der Auswahl: verworfen", ab.plan_pruefen(json.loads(plan_json()),
                                                                 {"kueche": info["kueche"], "keller": info["keller"]})[0] is None)
for n in (3, 8):
    p = json.loads(plan_json())
    p["stationen"] = (p["stationen"] * 2)[:n]
    pruef("A4 %d Stationen: verworfen" % n, ab.plan_pruefen(p, info)[0] is None)
p = json.loads(plan_json())
p["stationen"][0]["hinweise"] = ["nur einer"]
pruef("A4 nur ein Hinweis: verworfen", ab.plan_pruefen(p, info)[0] is None)
p = json.loads(plan_json())
p["stationen"][0]["raetsel"] = "Die Kerze brennt, aber was ist das, was ihr sucht?"
pruef("A4 Rätsel verrät die Lösung: verworfen", "verrät" in " ".join(ab.plan_pruefen(p, info)[1]))
p = json.loads(plan_json())
p["stationen"][0]["effekt"].update(durchsage="Sucht die Kerze!", leinwand="Die Lösung ist Kerze", farbe="schwarzlicht")
s0 = ab.plan_pruefen(p, info)[0]["stationen"][0]
pruef("A4 Durchsage/Leinwand mit der Lösung werden still, unbekannte Farbe = kein Licht",
      s0["effekt"] == {"farbe": None, "durchsage": "", "leinwand": ""}, s0["effekt"])
p = json.loads(plan_json())
p["stationen"][0]["effekt"] = {"farbe": [300, -5, 12.7], "durchsage": "<b>Hallo</b>", "dienst": "switch.turn_off",
                               "entity_id": "switch.receiver_steckdose"}
p["stationen"][0]["antworten"] = ["Kerze", True, "<script>"]
s0 = ab.plan_pruefen(p, info)[0]["stationen"][0]
pruef("A4 fremde Effektfelder fallen weg, Werte begrenzt, keine spitzen Klammern",
      s0["effekt"] == {"farbe": [255, 0, 12], "durchsage": "b Hallo /b", "leinwand": ""} and s0["antworten"] == ["Kerze", "script"],
      s0)
pruef("A4 kein Objekt", ab.plan_pruefen(["x"], info) == (None, ["Kein JSON-Objekt."]))

# ---------------------------------------------------------------- A5 Start am Nachmittag
ctx = neuer_ctx(pruefen=['{"richtig": false}', '{"richtig": false}', '{"richtig": true}'])
r = ab.auftrag({"aktion": "start", "thema": "Glühwürmchen", "spieler": ["Kim", "alex", "Kim"], "dauer_min": 30,
                "stufe": "kind"}, "alex", ctx)
z = spiel(ctx)
pruef("A5 Start ok", r.get("ok") is True and z.get("phase") == "laeuft", r)
pruef("A5 genau ein Plan-Auftrag, Stufe normal", [(g["zweck"], g["stufe"]) for g in ctx.gedacht] ==
      [("abenteuer_plan", "normal")])
a = ctx.gedacht[0]["auftrag"]
pruef("A5 Auftrag: Räume mit id, Lautsprecher und Licht, Spieler, Kinderstufe, 4 Stationen",
      "- keller: Keller (Lautsprecher: nein, farbiges Licht: ja)" in a and "- kueche: Küche (Lautsprecher: ja, farbiges "
      "Licht: nur hell/dunkel)" in a and "- hausflur: Hausflur (Lautsprecher: nein, farbiges Licht: nein)" in a
      and "Kim, Alex" in a and "Kinder" in a and "also 4 Stationen" in a, a[:600])
pruef("A5 Spieler ohne Doppelte, groß", z["spieler"] == ["Kim", "Alex"])
pruef("A5 meldung: Titel, Intro, Station 1 im Wohnzimmer", r["meldung"].startswith("„Das Geheimnis der Glühwürmchen“.")
      and "Station 1 von 4, Wohnzimmer: Ich werde kürzer" in r["meldung"] and "Kerze" not in r["meldung"], r["meldung"])
pruef("A5 Lampen je Raum: nur dimmbare/farbige, keine Steckdose, kein switch, keine unerreichbare",
      z["lampen"] == {"wohnzimmer": ["light.wohnzimmer_decke", "light.wohnzimmer_stehlampe"], "kueche": ["light.kueche"],
                      "keller": ["light.keller"], "schlafzimmer": ["light.schlafzimmer"], "hausflur": []}, z["lampen"])
pruef("A5 Licht Station 1: Decke blau 70 %, Stehlampe (nur Weiß) nur hell", ctx.dienste == [
    ("light", "turn_on", {"brightness_pct": 70, "rgb_color": [0, 80, 255], "entity_id": "light.wohnzimmer_decke"}),
    ("light", "turn_on", {"brightness_pct": 70, "entity_id": "light.wohnzimmer_stehlampe"})], ctx.dienste)
pruef("A5 Zustand vorher gemerkt", z["vorher"] == {
    "light.wohnzimmer_decke": {"state": "on", "brightness": 200, "color_mode": "xy", "xy_color": [0.41, 0.39]},
    "light.wohnzimmer_stehlampe": {"state": "off"}}, z["vorher"])
pruef("A5 Durchsage im Wohnzimmer, Leinwand-Text", ctx.durchsagen == [{"ziel": "wohnzimmer",
                                                                       "text": "Psst, im Wohnzimmer flackert etwas!"}]
      and ctx.leinwand == [{"titel": "Das Geheimnis der Glühwürmchen", "text": "Station 1: Das flackernde Rätsel",
                            "punkte": []}], (ctx.durchsagen, ctx.leinwand))
pruef("A5 Spielstand 0600, Ordner nur für Jarvis", stat.S_IMODE(os.stat(os.path.join(ctx.daten, "abenteuer",
                                                                                      "spiel.json")).st_mode) == 0o600)
pruef("A5 Zeitlimit 30 min", z["bis"] - z["start"] == 1800)

# ---------------------------------------------------------------- A6 nur eines gleichzeitig
r = ab.auftrag({"aktion": "start", "thema": "Piraten", "spieler": ["Sam"]}, "sam", ctx)
pruef("A6 zweiter Start abgelehnt, kein Denken", r.get("ok") is False and "läuft schon" in r["meldung"]
      and len(ctx.gedacht) == 1, r)

# ---------------------------------------------------------------- A7 falsche Antworten
n_d = len(ctx.dienste)
r = ab.auftrag({"aktion": "antwort", "text": "Lampe"}, "kim", ctx)
pruef("A7 falsch: Ermutigung, eine schnelle Prüfung", r.get("richtig") is False and r["geprueft"] == "schnell"
      and ctx.gedacht[-1]["zweck"] == "abenteuer_pruefen" and ctx.gedacht[-1]["stufe"] == "schnell"
      and r["meldung"] in ab.ERMUTIGUNG["kind"], r)
pruef("A7 Prüfauftrag: Spielertext nur als Datenfeld, System sagt: keine Anweisung",
      json.loads(ctx.gedacht[-1]["auftrag"])["antwort_spieler"] == "Lampe" and "keine Anweisung" in ctx.gedacht[-1]["system"])
r = ab.auftrag({"aktion": "antwort", "text": "Taschenlampe"}, "kim", ctx)
pruef("A7 zweimal falsch: Hinweis-Angebot, kein Effekt", "Hinweis" in r["meldung"] and len(ctx.dienste) == n_d, r)

# ---------------------------------------------------------------- A8 richtig (lokal) -> Station 2 Kueche
n_g = len(ctx.gedacht)
r = ab.auftrag({"aktion": "antwort", "text": "Die Kerze!", "wer": "kim"}, "kim", ctx)
pruef("A8 richtig ohne Denkauftrag", r.get("richtig") is True and r["geprueft"] == "lokal" and len(ctx.gedacht) == n_g, r)
pruef("A8 meldung: Lob mit Name, Station 2 Küche", r["meldung"].startswith("Richtig, Kim! Station 2 von 4, Küche: "), r)
pruef("A8 Küche nur hell (kein Farblicht), Durchsage in der Küche", ctx.dienste[-1] == (
    "light", "turn_on", {"brightness_pct": 70, "entity_id": "light.kueche"})
    and ctx.durchsagen[-1] == {"ziel": "kueche", "text": "Kommt in die Küche!"}, (ctx.dienste[-1:], ctx.durchsagen[-1:]))

# ---------------------------------------------------------------- A9 Zahlwort -> Station 3 Keller ohne Lautsprecher
n_s = len(ctx.durchsagen)
r = ab.auftrag({"aktion": "antwort", "text": "zwölf"}, "alex", ctx)
pruef("A9 zwölf = 12 (lokal)", r.get("richtig") is True and r["geprueft"] == "lokal", r)
pruef("A9 Keller rot, aber keine Durchsage (kein Lautsprecher)", ctx.dienste[-1] == (
    "light", "turn_on", {"brightness_pct": 70, "rgb_color": [255, 0, 0], "entity_id": "light.keller"})
    and len(ctx.durchsagen) == n_s, ctx.durchsagen[n_s:])

# ---------------------------------------------------------------- A10 Hinweise
t = [ab.auftrag({"aktion": "hinweis"}, "kim", ctx)["meldung"] for _ in range(4)]
pruef("A10 Hinweis 1, 2, Anfangsbuchstabe, dann Schluss", t == ["Hinweis 1: Schaut genau hin.",
                                                               "Hinweis 2: Es ist ganz in eurer Nähe.",
                                                               "Letzter Tipp: Die Lösung beginnt mit „S“ und hat 9 Zeichen.",
                                                               "Mehr verrate ich nicht. Ihr kommt drauf!"], t)

# ---------------------------------------------------------------- A11 richtig per schneller Pruefung
r = ab.auftrag({"aktion": "antwort", "text": "Das Ding zum Aufsperren"}, "sam", ctx)
pruef("A11 großzügig per schneller Prüfung", r.get("richtig") is True and r["geprueft"] == "schnell"
      and "Station 4 von 4, Wohnzimmer" in r["meldung"], r)
pruef("A11 Station 4: Wohnzimmer magenta (Decke), Stehlampe hell", ctx.dienste[-2:] == [
    ("light", "turn_on", {"brightness_pct": 70, "rgb_color": [255, 0, 255], "entity_id": "light.wohnzimmer_decke"}),
    ("light", "turn_on", {"brightness_pct": 70, "entity_id": "light.wohnzimmer_stehlampe"})], ctx.dienste[-2:])
pruef("A11 Vorher-Zustand bleibt der vom ersten Schalten", spiel(ctx)["vorher"]["light.wohnzimmer_decke"]["xy_color"]
      == [0.41, 0.39])

# ---------------------------------------------------------------- A12 stand liest nur
h, n_d, n_s, n_g = dateihash(ctx), len(ctx.dienste), len(ctx.durchsagen), len(ctx.gedacht)
r = ab.auftrag({"aktion": "stand"}, "sam", ctx)
pruef("A12 stand: Station 4, Restzeit, ohne Lösung", r.get("station") == 4 and "noch etwa 30 Minuten" in r["meldung"]
      and "Sofa" not in r["meldung"] and "Kim 1" in r["meldung"], r)
pruef("A12 stand ändert nichts und schaltet nichts", dateihash(ctx) == h and len(ctx.dienste) == n_d
      and len(ctx.durchsagen) == n_s and len(ctx.gedacht) == n_g)
pruef("A12 ohne aktion = stand", ab.auftrag({}, "kim", ctx).get("station") == 4)

# ---------------------------------------------------------------- A13 geschafft
ctx._jetzt = uhr(15, 23)
n_d = len(ctx.dienste)
r = ab.auftrag({"aktion": "antwort", "text": "Couch", "wer": "Kim"}, "kim", ctx)
pruef("A13 geschafft: Finale, Zeit, Punkte", r.get("geschafft") is True and "Die Glühwürmchen sind zurück" in r["meldung"]
      and "alle 4 Stationen in 23 Minuten" in r["meldung"] and "Kim 2" in r["meldung"], r)
gold = [d for d in ctx.dienste[n_d:]]
pruef("A13 Gold nur in Stationsräumen (nicht Schlafzimmer)", sorted(d[2]["entity_id"] for d in gold) ==
      ["light.keller", "light.kueche", "light.wohnzimmer_decke", "light.wohnzimmer_stehlampe"]
      and all(d[2].get("rgb_color") in (None, [255, 170, 0]) for d in gold), gold)
pruef("A13 Finale-Durchsage im letzten Raum und auf der Leinwand", ctx.durchsagen[-1]["ziel"] == "wohnzimmer"
      and ctx.durchsagen[-1]["text"].startswith("Geschafft!") and ctx.leinwand[-1]["text"].startswith("Geschafft!"))
r = ab.auftrag({"aktion": "antwort", "text": "Sofa"}, "kim", ctx)
pruef("A13 danach keine Antworten mehr", r.get("ok") is False and "geschafft" in r["meldung"])
pruef("A13 stand: geschafft", "geschafft" in ab.auftrag({"aktion": "stand"}, "kim", ctx)["meldung"])

# ---------------------------------------------------------------- A14 Nachlauf, dann Licht zurueck
n_d = len(ctx.dienste)
ab.runde(ctx)
pruef("A14 runde vor Ende des Nachlaufs: nichts", len(ctx.dienste) == n_d and spiel(ctx)["phase"] == "geschafft")
ctx._jetzt += ab.NACHLAUF_S + 1
ab.runde(ctx)
zurueck = sorted(ctx.dienste[n_d:], key=lambda d: d[2]["entity_id"])
pruef("A14 jede Lampe wie vorher", zurueck == [
    ("light", "turn_off", {"entity_id": "light.keller"}),
    ("light", "turn_on", {"brightness": 128, "color_temp_kelvin": 3000, "entity_id": "light.kueche"}),
    ("light", "turn_on", {"brightness": 200, "xy_color": [0.41, 0.39], "entity_id": "light.wohnzimmer_decke"}),
    ("light", "turn_off", {"entity_id": "light.wohnzimmer_stehlampe"})], zurueck)
z = spiel(ctx)
pruef("A14 beendet, nichts mehr geschaltet", z["phase"] == "beendet" and z["grund"] == "geschafft" and z["geschaltet"] == [])
pruef("A14 stand nennt das letzte", "Das letzte war „Das Geheimnis der Glühwürmchen“" in
      ab.auftrag({"aktion": "stand"}, "kim", ctx)["meldung"])
pruef("A15 Positivliste: alle HA-Aufrufe nur light.turn_on/off auf erlaubten Lampen", nur_licht(ctx), ctx.dienste)
pruef("A15 nie switch, lock, climate, camera, alarm, cover, media_player", not [d for d in ctx.dienste if d[0] != "light"])

# ---------------------------------------------------------------- A15 Positivliste direkt
z = {"lampen": {"wohnzimmer": ["light.wohnzimmer_decke"]}, "vorher": {"light.wohnzimmer_decke": {"state": "on"}}}
ctx_v = neuer_ctx()
for name, args in (("switch", ("turn_on", "switch.receiver_steckdose", {})), ("toggle", ("toggle", "light.wohnzimmer_decke", {})),
                   ("fremde Lampe", ("turn_on", "light.wohnzimmer_strip", {})),
                   ("Tabu-Name", ("turn_on", "light.flur_receiver", {})),
                   ("fremdes Feld", ("turn_on", "light.wohnzimmer_decke", {"effect": "colorloop"})),
                   ("turn_off einer vorher brennenden Lampe", ("turn_off", "light.wohnzimmer_decke", {})),
                   ("keine Kennung", ("turn_on", None, {}))):
    try:
        ab._licht(ctx_v, z, *args)
        pruef("A15 verboten: %s" % name, False, ctx_v.dienste)
    except ab.Verboten:
        pruef("A15 verboten: %s" % name, not ctx_v.dienste)
ab._licht(ctx_v, z, "turn_on", "light.wohnzimmer_decke", {"rgb_color": [1, 2, 3], "brightness_pct": 5})
pruef("A15 erlaubt: turn_on mit Farbe und Helligkeit", ctx_v.dienste == [
    ("light", "turn_on", {"rgb_color": [1, 2, 3], "brightness_pct": 5, "entity_id": "light.wohnzimmer_decke"})])

# ---------------------------------------------------------------- A16 Zeitlimit mit Auto-Ende
ctx = neuer_ctx()
ab.auftrag({"aktion": "start", "thema": "Uhr", "spieler": "Kim und Sam", "dauer_min": 5}, "sam", ctx)
z = spiel(ctx)
pruef("A16 dauer 5 wird 15 min, Spieler aus Text", z["bis"] - z["start"] == 900 and z["spieler"] == ["Kim", "Sam"])
ab.auftrag({"aktion": "antwort", "text": "Kerzen"}, "kim", ctx)
n_d = len(ctx.dienste)
ctx._jetzt = uhr(15, 14)
ab.runde(ctx)
pruef("A16 vor Ablauf: weiter", spiel(ctx)["phase"] == "laeuft" and len(ctx.dienste) == n_d)
ctx._jetzt = uhr(15, 15, 30)
ab.runde(ctx)
z = spiel(ctx)
pruef("A16 nach Ablauf: beendet, Grund zeit", z["phase"] == "beendet" and z["grund"] == "zeit")
pruef("A16 Ansage „Zeit ist um“ im aktuellen Raum (Küche)", ctx.durchsagen[-1]["ziel"] == "kueche"
      and "Zeit ist um" in ctx.durchsagen[-1]["text"])
pruef("A16 Licht zurück (Wohnzimmer und Küche)", sorted(d[2]["entity_id"] for d in ctx.dienste[n_d:]) ==
      ["light.kueche", "light.wohnzimmer_decke", "light.wohnzimmer_stehlampe"] and nur_licht(ctx))
pruef("A16 Log", any("Zeitlimit" in x for x in ctx.logs))
r = ab.auftrag({"aktion": "antwort", "text": "12"}, "kim", ctx)
pruef("A16 danach: kein Abenteuer", r.get("ok") is False and "kein Abenteuer" in r["meldung"])
pruef("A16 dauer 90 wird 60", (lambda c: (ab.auftrag({"aktion": "start", "spieler": ["Kim"], "dauer_min": 90}, "kim", c),
                                          spiel(c)["bis"] - spiel(c)["start"])[1])(neuer_ctx()) == 3600)

# ---------------------------------------------------------------- A17 Nachtruhe
ctx = neuer_ctx(jetzt=uhr(22))
r = ab.auftrag({"aktion": "start", "thema": "Geister", "spieler": ["Alex"]}, "alex", ctx)
pruef("A17 nachts ohne leise: abgelehnt, kein Denken", r.get("ok") is False and "Nachtruhe" in r["meldung"]
      and not ctx.gedacht, r)
p = json.loads(plan_json())
r = ab.auftrag({"aktion": "start", "thema": "Geister", "spieler": ["Alex"], "leise": True}, "alex", ctx)
pruef("A17 nachts leise: Start, ohne Schlafzimmer, Auftrag sagt leise", r.get("ok") is True
      and "schlafzimmer" not in ctx.gedacht[0]["auftrag"] and "leises Spiel" in ctx.gedacht[0]["auftrag"]
      and "Leise" in r["meldung"], r)
pruef("A17 leise: keine Durchsage, Licht gedimmt 40 %", not ctx.durchsagen and ctx.dienste[0][2]["brightness_pct"] == 40)
ab.auftrag({"aktion": "ende"}, "alex", ctx)
ctx = neuer_ctx(jetzt=uhr(23), plan=plan_json(stationen=[station("schlafzimmer", "Was hat ein Bett, schläft aber nie?",
                                                                 ["Fluss"], "blau")] + PLAN["stationen"][1:]))
r = ab.auftrag({"aktion": "start", "spieler": ["Alex"], "leise": True, "raeume": ["Schlafzimmer", "Küche", "keller",
                                                                                   "Wohnzimmer"]}, "alex", ctx)
pruef("A17 Schlafzimmer nachts nur, wenn ausdrücklich genannt", r.get("ok") is True
      and ctx.dienste[0][2]["entity_id"] == "light.schlafzimmer", r)
ab.auftrag({"aktion": "ende"}, "alex", ctx)
ctx = neuer_ctx(jetzt=uhr(20, 50))
ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
n_s = len(ctx.durchsagen)
ctx._jetzt = uhr(21, 5)
ab.auftrag({"aktion": "antwort", "text": "Kerze"}, "kim", ctx)
pruef("A17 Spiel läuft in die Nacht: ab 21 Uhr keine Durchsagen mehr", n_s == 1 and len(ctx.durchsagen) == 1
      and ctx.dienste[-1][2]["entity_id"] == "light.kueche")
ctx._jetzt = uhr(6, 59, tag=8)
pruef("A17 bis 7 Uhr Nachtruhe", ab.nachtruhe(ctx) and not ab.nachtruhe(neuer_ctx(jetzt=uhr(7))))

# ---------------------------------------------------------------- A18/A19 Plan ungueltig, Denken verweigert
schlecht = json.loads(plan_json())
schlecht["stationen"][1]["raum"] = "dachboden"
ctx = neuer_ctx(plan=[json.dumps(schlecht), plan_json()])
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
pruef("A18 erster Plan verworfen, zweiter gut", r.get("ok") is True and len(ctx.gedacht) == 2
      and "dachboden" in ctx.gedacht[1]["auftrag"] and "ungültig" in ctx.gedacht[1]["auftrag"], r)
ctx = neuer_ctx(plan=[json.dumps(schlecht), "Ich habe leider kein JSON."])
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
pruef("A18 zweimal ungültig: ehrliche Absage, nichts geschaltet, frei", r.get("ok") is False and "kein stimmiges" in
      r["meldung"] and not ctx.dienste and not ctx.durchsagen and spiel(ctx)["phase"] == "frei", r)
pruef("A18 danach ist ein neuer Start möglich", ab.auftrag({"aktion": "stand"}, "kim", ctx)["phase"] == "frei")


class Abgelehnt(RuntimeError):
    pass


def tageslimit(a, s, st):
    raise Abgelehnt("Tageslimit fuers Nachdenken erreicht (2.00 $). Morgen wieder.")


ctx = neuer_ctx(plan=tageslimit)
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
pruef("A19 Tageslimit: ein Versuch, Absage", r.get("ok") is False and len(ctx.gedacht) == 1 and not ctx.dienste, r)

# ---------------------------------------------------------------- A20 ende
ctx = neuer_ctx()
ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
n_d = len(ctx.dienste)
r = ab.auftrag({"aktion": "ende"}, "sam", ctx)
pruef("A20 ende: Licht zurück, ehrlich gezählt", r.get("ok") is True and "0 von 4" in r["meldung"]
      and "wieder wie vorher" in r["meldung"] and sorted(d[1] for d in ctx.dienste[n_d:]) == ["turn_off", "turn_on"], r)
r = ab.auftrag({"aktion": "ende"}, "sam", ctx)
pruef("A20 zweites ende: nichts läuft", r.get("ok") is False and "kein Abenteuer" in r["meldung"])

# ---------------------------------------------------------------- A21 HA hakt beim Zuruecksetzen
ctx = neuer_ctx()
ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
echt = ctx.ha_dienst


def kaputt(domain, dienst, daten):
    if daten.get("entity_id") == "light.wohnzimmer_decke":
        raise OSError("HA weg")
    return echt(domain, dienst, daten)


ctx.ha_dienst = kaputt
r = ab.auftrag({"aktion": "ende"}, "kim", ctx)
pruef("A21 ein Licht geht nicht zurück: ehrlich gesagt, gemerkt", "1 Lampe" in r["meldung"]
      and r["nicht_zurueck"] == ["light.wohnzimmer_decke"] and spiel(ctx)["geschaltet"] == ["light.wohnzimmer_decke"], r)
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
pruef("A21 Neustart wartet, solange Lampen offen sind", r.get("ok") is False and "Lampen" in r["meldung"], r)
ctx.ha_dienst = echt
ab.runde(ctx)
pruef("A21 runde holt es nach", spiel(ctx)["geschaltet"] == [] and ctx.dienste[-1] == (
    "light", "turn_on", {"brightness": 200, "xy_color": [0.41, 0.39], "entity_id": "light.wohnzimmer_decke"}))
pruef("A21 danach startet ein neues Abenteuer", ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx).get("ok"))

# ---------------------------------------------------------------- A22 Personen und Eingaben
ctx = neuer_ctx()
for wer in ("gast1", "fremd", None):
    r = ab.auftrag({"aktion": "start", "spieler": ["X"]}, wer, ctx)
    pruef("A22 %s bekommt nichts" % wer, r.get("ok") is False and "Familie" in r["meldung"] and not ctx.gedacht)
pruef("A22 unbekannte Aktion", "start, antwort, hinweis, stand, ende" in ab.auftrag({"aktion": "zaubern"}, "kim", ctx)["meldung"])
pruef("A22 antwort ohne Abenteuer", "kein Abenteuer" in ab.auftrag({"aktion": "antwort", "text": "x"}, "kim", ctx)["meldung"])
pruef("A22 hinweis ohne Abenteuer", ab.auftrag({"aktion": "hinweis"}, "kim", ctx).get("ok") is False)
pruef("A22 start ohne Spieler: Rückfrage", "Wer spielt mit" in ab.auftrag({"aktion": "start"}, "kim", ctx)["meldung"])
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"], "raeume": ["Küche", "Garten"]}, "kim", ctx)
pruef("A22 unbekannter Wunschraum", r.get("ok") is False and "Garten" in r["meldung"] and not ctx.gedacht, r)
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"], "raeume": ["Küche"]}, "kim", ctx)
pruef("A22 nur ein Raum reicht nicht", r.get("ok") is False and "zwei Räume" in r["meldung"])
ab.auftrag({"aktion": "start", "spieler": ["Kim"], "leinwand": False}, "kim", ctx)
pruef("A22 leinwand false: kein Leinwand-Text", not ctx.leinwand)
r = ab.auftrag({"aktion": "antwort", "text": "  "}, "kim", ctx)
pruef("A22 leere Antwort: Rückfrage ohne Denken", r.get("ok") is False and len(ctx.gedacht) == 1)

# ---------------------------------------------------------------- A23 runde wirft nie
ctx = neuer_ctx()
os.makedirs(os.path.join(ctx.daten, "abenteuer"))
open(os.path.join(ctx.daten, "abenteuer", "spiel.json"), "w").write("{kaputt")
ab.runde(ctx)
z = {"phase": "laeuft", "bis": 0}
ab.speichern(ctx, z)
try:
    ab.runde(ctx)
    ctx.daten = "/proc/nicht/da"
    ab.runde(ctx)
    pruef("A23 runde wirft nie (kaputte Datei, kaputter Stand, kein Ordner)", any("runde fehlgeschlagen" in x for x in ctx.logs))
except Exception as x:
    pruef("A23 runde wirft nie", False, x)

# ---------------------------------------------------------------- A24 Obergrenze schnelle Pruefungen
ctx = neuer_ctx(pruefen='{"richtig": true}')
ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
z = spiel(ctx)
z["pruefungen"] = ab.MAX_PRUEF
ab.speichern(ctx, z)
r = ab.auftrag({"aktion": "antwort", "text": "Feuerzeug"}, "kim", ctx)
pruef("A24 nach %d Prüfungen nur noch lokal" % ab.MAX_PRUEF, r.get("richtig") is False and r["geprueft"] == "lokal"
      and len(ctx.gedacht) == 1, r)

# ---------------------------------------------------------------- A25 waehrend des Planens
ctx = neuer_ctx()
ab.speichern(ctx, {"version": 1, "phase": "plant", "seit": ctx.jetzt() - 60})
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
pruef("A25 während ein Plan entsteht: kein zweiter", r.get("ok") is False and not ctx.gedacht)
pruef("A25 stand sagt es", "denke mir gerade" in ab.auftrag({"aktion": "stand"}, "kim", ctx)["meldung"])
ab.speichern(ctx, {"version": 1, "phase": "plant", "seit": ctx.jetzt() - ab.PLANT_VERFALL_S - 1})
ab.runde(ctx)
pruef("A25 hängengebliebenes Planen verfällt", spiel(ctx)["phase"] == "frei")
pruef("A25 danach Start möglich", ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx).get("ok") is True)

# ---------------------------------------------------------------- A27 Absturz mitten im Schalten
ctx = neuer_ctx()


def absturz(domain, dienst, daten):
    raise SystemExit("Prozess stirbt mitten im Schalten")


ctx.ha_dienst = absturz
try:
    ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
    pruef("A27 Absturz simuliert", False)
except SystemExit:
    z = spiel(ctx)
    pruef("A27 Vorher-Zustand lag schon auf der Platte, bevor geschaltet wurde",
          set(z.get("vorher") or {}) == {"light.wohnzimmer_decke", "light.wohnzimmer_stehlampe"}, z.get("vorher"))

# ---------------------------------------------------------------- A28 Lautsprecher-Sperre (seit 0.7)
pruef("A28 LAUTSPRECHER_PRIVAT: frozenset, leer (Gemeinschaftsspiel, nichts Privates)",
      isinstance(ab.LAUTSPRECHER_PRIVAT, frozenset) and ab.LAUTSPRECHER_PRIVAT == frozenset())

# ---------------------------------------------------------------- A29 Tabu-Schichten: Satelliten, englische Namen
DIMM = {"state": "on", "attributes": {"supported_color_modes": ["hs"]}}
FALLEN = ["light.voice_pe_led_ring", "light.wohnzimmer_satellit", "light.flur_assist", "light.porch_siren",
          "light.bad_heater", "light.office_power_strip", "light.amplifier_glow", "light.kinder_babyfon",
          "light.flur_kamera", "light.buero_lampe", "light.buero_spot"]
ctx = sh_attrappe.Kontext(jetzt=uhr(15), raeume={"version": 1, "raeume": {
    "buero": {"name": "Büro", "bereich": "Büro", "ausgabe": [], "licht": FALLEN}}},
    zustaende=dict({e: copy.deepcopy(DIMM) for e in FALLEN},
                   **{"light.buero_spot": {"state": "on", "attributes": {"supported_color_modes": ["hs"],
                                                                          "friendly_name": "Voice LED"}}}))
KONTEXTE.append((ctx, ctx.daten))
pruef("A29 nur echte Lampen: Sprach-Satelliten, Babyfon, Kamera, Sirene, Heizer, Steckdosenleiste, Verstärker tabu "
      "(Kennung oder Anzeigename)", [l["eid"] for l in ab.lampen_finden(ctx, "buero")] == ["light.buero_lampe"],
      ab.lampen_finden(ctx, "buero"))
z = {"lampen": {"buero": FALLEN}, "vorher": {}}
verboten = 0
for eid in FALLEN[:-2]:
    try:
        ab._licht(ctx, z, "turn_on", eid, {"brightness_pct": 5})
    except ab.Verboten:
        verboten += 1
pruef("A29 _licht wirft Verboten bei jedem Tabu-Namen, auch wenn er in der Liste steht",
      verboten == len(FALLEN) - 2 and not ctx.dienste, ctx.dienste)

# ---------------------------------------------------------------- A30 Schlafraeume nachts nach Kennung, Name, Alias
RAEUME_NACHT = {"version": 1, "raeume": {
    "living_room": {"name": "Living room", "ausgabe": [{"art": "ma"}]}, "kitchen": {"name": "Kitchen", "ausgabe": []},
    "buero": {"name": "Büro", "ausgabe": []}, "bedroom": {"name": "Bedroom", "ausgabe": []},
    "nursery": {"name": "Nursery", "ausgabe": []}, "zimmer_kim": {"name": "Kim", "alias": ["kids room"], "ausgabe": []},
    "gaeste": {"name": "Guest bedroom", "ausgabe": []}, "eltern": {"name": "Elternschlafzimmer", "ausgabe": []}}}
plan_nacht = plan_json(stationen=[dict(s, raum=r) for s, r in zip(PLAN["stationen"], ("living_room", "kitchen", "buero",
                                                                                        "living_room"))])
ctx = sh_attrappe.Kontext(antworten={"abenteuer_plan": plan_nacht}, raeume=copy.deepcopy(RAEUME_NACHT), jetzt=uhr(22))
KONTEXTE.append((ctx, ctx.daten))
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"], "leise": True}, "kim", ctx)
a = ctx.gedacht[0]["auftrag"] if ctx.gedacht else ""
pruef("A30 nachts ohne Wunsch: Wohn-, Küchen-, Büroraum ja; Schlaf-, Kinder-, Gästeschlafzimmer nein",
      r.get("ok") is True and all("- %s:" % x in a for x in ("living_room", "kitchen", "buero"))
      and not any("- %s:" % x in a for x in ("bedroom", "nursery", "zimmer_kim", "gaeste", "eltern")), (r, a[:500]))
pruef("A30 _schlafraum: Kennung, Name und Alias", ab._schlafraum("schlafzimmer", {}) and ab._schlafraum(
    "x", {"name": "Kinderzimmer"}) and ab._schlafraum("x", {"name": "X", "alias": ["Bedroom 2"]})
      and not ab._schlafraum("wohnzimmer", {"name": "Wohnzimmer"}) and not ab._schlafraum("kitchen", {"name": "Kitchen"}))
ab.auftrag({"aktion": "ende"}, "kim", ctx)

# ---------------------------------------------------------------- A31 Englisch (seit 0.7)
DEUTSCH = re.compile(r"[äöüÄÖÜß„]|\b(ist|nicht|Bitte|bitte|und|oder|der|die|das|ein|eine|Abenteuer|Hinweis|Raum|Räume|"
                     r"Licht|Lampe|Minuten|Stationen gelöst|von|wieder|Leinwand|Durchsage|Spieler|Lösung)\b")
MELDUNGEN_EN = []


def en(r):
    """Meldung merken (fuer die Sammelpruefung) und zurueckgeben."""
    m = r.get("meldung", "") if isinstance(r, dict) else str(r)
    MELDUNGEN_EN.append(m)
    return m


def englisch(t):
    return bool(t and t.strip()) and not DEUTSCH.search(t)


werkzeug_obj = ab.WERKZEUG
try:
    ab.setze_sprache("fr")
    pruef("A31 setze_sprache('fr') wirft ValueError", False)
except ValueError:
    pruef("A31 setze_sprache('fr') wirft ValueError, Sprache bleibt", ab.SPRACHE == "de")
ab.setze_sprache("en")
b = ab.WERKZEUG["beschreibung"]
pruef("A31 WERKZEUG englisch (gleiches Objekt, Schema gleich, Beschreibungen englisch)",
      ab.WERKZEUG is werkzeug_obj and b.startswith("House adventure:") and "in English" in b
      and not re.search(r"[äöüÄÖÜß]|\b(ist|nicht|und|oder|der|die|das|Licht|Räume)\b", b)
      and ab.WERKZEUG["schema"]["properties"]["aktion"]["enum"] == ["start", "antwort", "hinweis", "stand", "ende"]
      and ab.WERKZEUG["schema"]["properties"]["raeume"]["description"] == "Only these rooms (name or id)"
      and ab.WERKZEUG["schema"]["properties"]["text"]["description"] == "The players' answer", b)

RAEUME_EN = copy.deepcopy(RAEUME)
for rid, name in (("wohnzimmer", "Living room"), ("kueche", "Kitchen"), ("keller", "Cellar"),
                  ("schlafzimmer", "Bedroom"), ("hausflur", "Hallway")):
    RAEUME_EN["raeume"][rid]["name"] = name
    RAEUME_EN["raeume"][rid]["bereich"] = name
RAEUME_EN["raeume"]["wohnzimmer"]["alias"] = ["lounge"]
HINWEISE_EN = ["Look closely.", "It is very close to you."]
PLAN_EN = {"titel": "The Secret of the Fireflies",
           "intro": "The fireflies of the house have vanished. Only you can find them!",
           "stationen": [dict(station(r, q, a, f, d, l), hinweise=HINWEISE_EN) for r, q, a, f, d, l in (
               ("living room", "I get shorter the longer I burn. What am I?", ["candle", "candles"], "blue",
                "Psst, something is flickering in the living room!", "Station 1: The flickering riddle"),
               ("Kitchen", "How many months does a year have?", ["12", "twelve"], "green", "Come to the kitchen!",
                "Station 2: The number kitchen"),
               ("cellar", "I open doors but have no hand. What am I?", ["key"], "red", "It's dark down here ...",
                "Station 3: The cellar treasure"),
               ("Lounge", "I have four legs and cushions but never walk. What am I?", ["sofa", "couch"], "#ff00ff",
                "Back to the living room!", "Station 4: The last riddle"))],
           "finale": "The fireflies are back and glowing golden. You are real detectives!"}


def neuer_ctx_en(plan=None, pruefen=None, jetzt=None):
    a = {"abenteuer_plan": plan if plan is not None else json.dumps(PLAN_EN)}
    if pruefen is not None:
        a["abenteuer_pruefen"] = pruefen
    c = sh_attrappe.Kontext(antworten=a, zustaende=copy.deepcopy(ZUSTAENDE), raeume=copy.deepcopy(RAEUME_EN),
                            jetzt=jetzt if jetzt is not None else uhr(15))
    KONTEXTE.append((c, c.daten))
    return c


pruef("A31 englische Antworten lokal", all(ab.lokal_richtig(e, a) for e, a in (
    ("the candle", ["candle"]), ("I think it's the candle!", ["candle"]), ("CANDLES", ["candle", "candles"]),
    ("twelve", ["12"]), ("12", ["twelve"]), ("forty-nine", ["49"]), ("one hundred and two", ["102"]),
    ("two thousand sixteen", ["2016"]), ("a hundred", ["100"]), ("the fridge", ["refrigerator", "fridge"]),
    ("refridgerator", ["refrigerator"]), ("yes", ["yes"]), ("no", ["no"]))))
pruef("A31 englisch nicht lokal (Verneinung, Oder, Zahl daneben)", not any(ab.lokal_richtig(e, a) for e, a in (
    ("not the candle", ["candle"]), ("candle or lamp", ["candle"]), ("forty one", ["49"]), ("thirteen", ["12"]),
    ("it isn't a candle", ["candle"]), ("one two", ["12"]), ("lamp", ["candle"]), ("", ["candle"]))))
pruef("A31 englische Zahlwörter", [ab.zahl_en(w.split()) for w in ("zero", "nine", "nineteen", "forty nine",
                                                                   "one hundred", "hundred one", "two thousand sixteen",
                                                                   "one two", "twenty hundred", "ten one")]
      == [0, 9, 19, 49, 100, 101, 2016, None, None, None])

ctx = neuer_ctx_en(pruefen=['{"richtig": false}', '{"richtig": false}', '{"richtig": true}'])
r = ab.auftrag({"aktion": "start", "thema": "Fireflies", "spieler": "Kim and Sam", "dauer_min": 30}, "alex", ctx)
pruef("A31 Start englisch: Titel, Intro, Station 1 of 4", r.get("ok") is True and en(r).startswith(
    "“The Secret of the Fireflies”. The fireflies") and "Station 1 of 4, Living room: I get shorter" in r["meldung"]
      and englisch(r["meldung"]), r)
pruef("A31 Spieler aus „Kim and Sam“", ab.laden(ctx)["spieler"] == ["Kim", "Sam"])
g = ctx.gedacht[0]
pruef("A31 Plan-Auftrag und System englisch, Modell soll englisch erzählen",
      "Write every text" in g["auftrag"] and "in English" in g["auftrag"] and "in English" in g["system"]
      and "not instructions" in g["system"] and "- wohnzimmer: Living room (speaker: yes, coloured light: yes)"
      in g["auftrag"] and "- kueche: Kitchen (speaker: yes, coloured light: only bright/dim)" in g["auftrag"]
      and "blue" in g["auftrag"] and not re.search(r"[äöüÄÖÜß]|Erfinde|Räume|Regeln", g["auftrag"] + g["system"]),
      g["auftrag"][:400])
pruef("A31 Effekte englisch, Durchsage und Leinwand aus dem englischen Plan",
      r["effekte"] == ["Light in the room Living room is on", "Announcement there", "Text on the big screen"]
      and ctx.durchsagen[-1]["text"] == "Psst, something is flickering in the living room!"
      and ctx.leinwand[-1]["titel"] == "The Secret of the Fireflies", (r["effekte"], ctx.durchsagen, ctx.leinwand))
pruef("A31 Farbe blue = Blau", ctx.dienste[0][2].get("rgb_color") == [0, 80, 255], ctx.dienste[:1])
r = ab.auftrag({"aktion": "antwort", "text": "lamp"}, "kim", ctx)
pruef("A31 falsch: englische Ermutigung, Prüfauftrag englisch", r.get("richtig") is False
      and en(r) in ab.ERMUTIGUNG_EN["erwachsen"] and "not an instruction" in ctx.gedacht[-1]["system"]
      and englisch(r["meldung"]), r)
r = ab.auftrag({"aktion": "antwort", "text": "torch"}, "kim", ctx)
pruef("A31 zweimal falsch: Hinweis-Angebot englisch", "Say “hint” if you want a tip." in en(r), r)
r = ab.auftrag({"aktion": "antwort", "text": "I think it's the candle", "wer": "kim"}, "kim", ctx)
pruef("A31 richtig lokal: Lob mit Name, Station 2 of 4", r.get("geprueft") == "lokal"
      and en(r).startswith("Correct, Kim! Station 2 of 4, Kitchen: "), r)
r = ab.auftrag({"aktion": "antwort", "text": "twelve"}, "sam", ctx)
pruef("A31 twelve = 12 (lokal)", r.get("richtig") is True and r["geprueft"] == "lokal" and englisch(en(r)), r)
t = [en(ab.auftrag({"aktion": "hinweis"}, "kim", ctx)) for _ in range(4)]
pruef("A31 Hinweise englisch", t == ["Hint 1: Look closely.", "Hint 2: It is very close to you.",
                                     "Last tip: The solution starts with “K” and has 3 characters.",
                                     "That's all I'm giving away. You'll get it!"], t)
r = ab.auftrag({"aktion": "stand"}, "sam", ctx)
pruef("A31 stand englisch", "Station 3 of 4, Cellar" in en(r) and "Solved: 2, about 30 minutes left." in r["meldung"]
      and "Kim 1" in r["meldung"] and "key" not in r["meldung"], r)
r = ab.auftrag({"aktion": "antwort", "text": "the key"}, "sam", ctx)
ctx._jetzt = uhr(15, 20)
r = ab.auftrag({"aktion": "antwort", "text": "couch", "wer": "Kim"}, "kim", ctx)
pruef("A31 geschafft englisch", r.get("geschafft") is True and "You solved all 4 stations in 20 minutes!" in en(r)
      and "Kim 2" in r["meldung"] and "The lights will soon go back" in r["meldung"], r)
pruef("A31 Finale-Durchsage und Leinwand englisch", ctx.durchsagen[-1]["text"].startswith("You did it! The fireflies")
      and ctx.leinwand[-1]["text"].startswith("You did it!"))
pruef("A31 stand nach dem Finale", en(ab.auftrag({"aktion": "stand"}, "kim", ctx)) ==
      "“The Secret of the Fireflies” is completed! Scores: Kim 2, Sam 0.")
pruef("A31 keine Antworten mehr", en(ab.auftrag({"aktion": "antwort", "text": "x"}, "kim", ctx)) ==
      "No adventure is running right now. The last one was completed!")
ctx._jetzt += ab.NACHLAUF_S + 1
ab.runde(ctx)
pruef("A31 nach dem Nachlauf: Licht zurück, stand nennt das letzte", ab.laden(ctx)["geschaltet"] == []
      and en(ab.auftrag({"aktion": "stand"}, "kim", ctx)) ==
      "No adventure is running right now. The last one was “The Secret of the Fireflies”.")
pruef("A31 ende ohne Spiel", en(ab.auftrag({"aktion": "ende"}, "kim", ctx)) == "No adventure is running right now.")

ctx = neuer_ctx_en()
ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
r = ab.auftrag({"aktion": "ende"}, "sam", ctx)
pruef("A31 ende englisch", en(r) == "Adventure “The Secret of the Fireflies” ended: 0 of 4 stations solved. The lights "
      "are back to how they were.", r)
ctx = neuer_ctx_en()
ab.auftrag({"aktion": "start", "spieler": ["Kim"], "dauer_min": 15}, "kim", ctx)
ctx._jetzt = uhr(15, 16)
ab.runde(ctx)
pruef("A31 Zeitlimit: Durchsage englisch", ctx.durchsagen[-1]["text"] ==
      "Time is up! The adventure “The Secret of the Fireflies” is over.", ctx.durchsagen[-1:])
ctx = neuer_ctx_en(jetzt=uhr(22))
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
pruef("A31 Nachtruhe englisch", r.get("ok") is False and "quiet time (21:00 to 7:00)" in en(r) and not ctx.gedacht, r)
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"], "leise": True}, "kim", ctx)
pruef("A31 leise englisch, Auftrag ohne Schlafzimmer, Durchsagen leer", r.get("ok") is True
      and en(r).endswith(" (Quiet: no announcements.)") and "quiet game" in ctx.gedacht[0]["auftrag"]
      and "schlafzimmer" not in ctx.gedacht[0]["auftrag"], r)
schlecht = copy.deepcopy(PLAN_EN)
schlecht["stationen"][1]["raum"] = "attic"
ctx = neuer_ctx_en(plan=[json.dumps(schlecht), "No JSON, sorry."])
r = ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
pruef("A31 ungültiger Plan: Korrektur-Auftrag und Absage englisch", r.get("ok") is False
      and "Your last plan was invalid" in ctx.gedacht[1]["auftrag"] and "room “attic” does not exist"
      in ctx.gedacht[1]["auftrag"] and "Fix that." in ctx.gedacht[1]["auftrag"]
      and en(r).startswith("I couldn't come up with a coherent adventure"), r)
pruef("A31 Planfehler englisch", ab.plan_pruefen(["x"], {}) == (None, ["Not a JSON object."])
      and all(englisch(f) or "raetsel" in f for f in ab.plan_pruefen({"stationen": [{"raum": "x"}]}, {})[1]),
      ab.plan_pruefen({"stationen": [{"raum": "x"}]}, {})[1])
ctx = neuer_ctx_en()
for wer, b_ in (("gast1", {"aktion": "start", "spieler": ["X"]}), ("kim", {"aktion": "zaubern"}),
                ("kim", {"aktion": "antwort", "text": "x"}), ("kim", {"aktion": "start"}),
                ("kim", {"aktion": "start", "spieler": ["Kim"], "raeume": ["Kitchen", "Garden"]}),
                ("kim", {"aktion": "start", "spieler": ["Kim"], "raeume": ["Kitchen"]})):
    en(ab.auftrag(b_, wer, ctx))
pruef("A31 Absagen englisch", MELDUNGEN_EN[-6:] == [
    "The house adventure is only for the family.", "Unknown action “zaubern”. Possible: start, antwort, hinweis, stand, "
    "ende.", "No adventure is running right now.", "Who is playing? For example: Alex, Sam and Kim.",
    "I don't know these rooms: Garden. There are: Living room, Kitchen, Cellar, Bedroom, Hallway.",
    "An adventure needs at least two rooms."], MELDUNGEN_EN[-6:])
ab.auftrag({"aktion": "start", "spieler": ["Kim"]}, "kim", ctx)
pruef("A31 leere Antwort englisch", en(ab.auftrag({"aktion": "antwort", "text": " "}, "kim", ctx)) == "What is your answer?")
fehl = [m for m in MELDUNGEN_EN if not englisch(m)]
pruef("A31 alle %d geprüften Meldungen ohne deutschen Rest" % len(MELDUNGEN_EN), len(MELDUNGEN_EN) >= 20 and not fehl, fehl)

ab.setze_sprache("de")
pruef("A31 zurück auf Deutsch: WERKZEUG, Meldungen, lokale Prüfung", ab.SPRACHE == "de" and ab.WERKZEUG is werkzeug_obj
      and ab.WERKZEUG["beschreibung"].startswith("Haus-Abenteuer:") and ab.WERKZEUG == ab.WERKZEUG_DE
      and ab.lokal_richtig("zwölf", ["12"]) and not ab.lokal_richtig("Kerze oder Lampe", ["Kerze"])
      and ab.auftrag({"aktion": "stand"}, "kim", neuer_ctx())["meldung"] == "Gerade läuft kein Abenteuer.")

# ---------------------------------------------------------------- A26 Gesamtbilanz Positivliste
alle_dienste = [d for c, _ in KONTEXTE for d in c.dienste]
pruef("A26 über alle %d Testkontexte: %d HA-Aufrufe, alle light.turn_on/off auf erlaubten Lampen"
      % (len(KONTEXTE), len(alle_dienste)), len(alle_dienste) > 40 and all(nur_licht(c) for c, _ in KONTEXTE),
      [d for c, _ in KONTEXTE if not nur_licht(c) for d in c.dienste][:5])

# ---------------------------------------------------------------- Live-Daten, Aufraeumen
pruef("X Live-Daten unberührt", wache())
for _c, d in KONTEXTE:
    shutil.rmtree(d, ignore_errors=True)
sys.exit(ergebnis("Haus-Abenteuer"))
