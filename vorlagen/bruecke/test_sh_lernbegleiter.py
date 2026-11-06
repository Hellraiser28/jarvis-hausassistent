#!/usr/bin/env python3
"""S8 Lernbegleiter (bruecke/lernbegleiter.py), Superhirn seit 0.7.

Alles mit der Attrappe sh_attrappe.Kontext: eigener Datenordner, kein Netz, kein Claude. Lernkarten kommen ueber
ctx._antworten["lernkarten"], Bewertungen ueber ctx._antworten["lernen_pruefen"]; Zeit ueber ctx._jetzt. Am Ende prueft
live_wache(), dass ein echter Datenordner (JARVIS_LIVE_DATEN, optional) unberuehrt ist.
    python3 -B tests/test_sh_lernbegleiter.py
"""
import io
import json
import os
import re
import stat
import sys
import threading
import time
from contextlib import redirect_stdout

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HIER), "bruecke"))
sys.path.insert(0, HIER)

import sh_attrappe  # noqa: E402

unveraendert = sh_attrappe.live_wache()
pruef, ergebnis = sh_attrappe.pruefer()

_vorher = set(os.listdir(os.getcwd()))
_aus = io.StringIO()
with redirect_stdout(_aus):
    import lernbegleiter as lb  # noqa: E402
pruef("Import ohne Ausgabe", _aus.getvalue() == "")
pruef("Import legt keine Dateien an", set(os.listdir(os.getcwd())) == _vorher)

BASIS = time.mktime((2026, 11, 6, 12, 0, 0, 0, 0, -1))      # ein Freitag, 12:00 Ortszeit
TAG = 86400
VOK = [("Haus", "house", ["home"]), ("Hund", "dog", []), ("Katze", "cat", []), ("Baum", "tree", []),
       ("Fenster", "window", []), ("Schule", "school", []), ("Tisch", "table", []), ("Stuhl", "chair", []),
       ("Buch", "book", []), ("Apfel", "apple", []), ("Wasser", "water", []), ("Freund", "friend", []),
       ("Brot", "bread", []), ("Milch", "milk", [])]
LOESUNG = {de: en for de, en, _ in VOK}


def karten(paare, extra=()):
    return json.dumps({"karten": [{"frage": "Was heißt „%s“ auf Englisch?" % de, "antwort": en, "varianten": v,
                                   "erklaerung": "%s heißt auf Englisch %s." % (de, en)} for de, en, v in paare]
                       + list(extra)}, ensure_ascii=False)


def loesung(frage):
    return LOESUNG[re.search(r"„(.+?)“", frage).group(1)]


def neu_ctx(**kw):
    return sh_attrappe.Kontext(jetzt=BASIS, **kw)


def datei(ctx, person):
    return os.path.join(ctx.daten, "lernbegleiter", person + ".json")


def stand_von(ctx, person):
    with open(datei(ctx, person), encoding="utf-8") as f:
        return json.load(f)


def karte(ctx, person, de):
    return next(k for k in stand_von(ctx, person)["karten"] if "„%s“" % de in k["frage"])


def alle_dateien(wurzel):
    aus = []
    for o, _, namen in os.walk(wurzel):
        aus += [os.path.join(o, n) for n in namen]
    return aus


def denk_anzahl(ctx, zweck, stufe=None):
    return sum(1 for g in ctx.gedacht if g["zweck"] == zweck and (stufe is None or g["stufe"] == stufe))


def heute(plus=0):
    return time.strftime("%Y-%m-%d", time.localtime(BASIS + plus * TAG))


# ------------------------------------------------------------------ Schnittstelle
pruef("NAME", lb.NAME == "lernbegleiter")
pruef("RECHTE familie", lb.RECHTE == "familie")
pruef("TAKT_S 300 und runde()", lb.TAKT_S == 300 and callable(lb.runde))
pruef("Schema mit allen Aktionen", lb.WERKZEUG["schema"]["properties"]["aktion"]["enum"] ==
      ["neues_thema", "ueben", "antwort", "stand", "erinnern", "thema_loeschen"])
pruef("anzahl 8–30 im Schema", lb.WERKZEUG["schema"]["properties"]["anzahl"]["minimum"] == 8 and
      lb.WERKZEUG["schema"]["properties"]["anzahl"]["maximum"] == 30)
pruef("Fremdtext: Ziel, lesend nur stand", lb.FREMDTEXT == {"art": "ziel", "nur_lesen": ("aktion", "stand", ["stand"])})
pruef("LAUTSPRECHER_PRIVAT: leere frozenset (keine Aktion nur privat)",
      isinstance(lb.LAUTSPRECHER_PRIVAT, frozenset) and lb.LAUTSPRECHER_PRIVAT == frozenset())
pruef("LAUTSPRECHER_PRIVAT nennt nur echte Aktionen", lb.LAUTSPRECHER_PRIVAT <= set(lb.AKTIONEN))
pruef("Standard Deutsch", lb.SPRACHE == "de" and lb.WERKZEUG["beschreibung"].startswith("Lernbegleiter mit Lernkarten"))

# ------------------------------------------------------------------ SM-2 als reine Funktion
pruef("SM-2: erste richtige Antwort -> 1 Tag, EF +0,1", lb.sm2(5, 0, 2.5, 0) == (1, 2.6, 1), lb.sm2(5, 0, 2.5, 0))
pruef("SM-2: zweite -> 6 Tage", lb.sm2(5, 1, 2.6, 1) == (2, 2.7, 6), lb.sm2(5, 1, 2.6, 1))
pruef("SM-2: dritte -> 6 × EF aufgerundet (16,2 -> 17)", lb.sm2(5, 2, 2.7, 6) == (3, 2.8, 17), lb.sm2(5, 2, 2.7, 6))
iv, w, ef, folge = 0, 0, 2.5, []
for _ in range(4):
    w, ef, iv = lb.sm2(4, w, ef, iv)
    folge.append(iv)
pruef("SM-2 bei q 4 (EF bleibt 2,5): 1, 6, 15, 38", folge == [1, 6, 15, 38] and ef == 2.5, (folge, ef))
pruef("SM-2: teilweise (q 3) zählt als gewusst, EF −0,14", lb.sm2(3, 0, 2.5, 0) == (1, 2.36, 1))
pruef("SM-2: falsch (q 1) setzt zurück, EF −0,54", lb.sm2(1, 5, 2.5, 40) == (0, 1.96, 1))
ef = 2.5
for _ in range(6):
    _, ef, _ = lb.sm2(1, 0, ef, 1)
pruef("SM-2: EF nie unter 1,3", ef == 1.3, ef)
pruef("SM-2: Intervall mit EF 1,3 (6 -> 8)", lb.sm2(5, 2, 1.3, 6)[2] == 8)
pruef("SM-2: q wird auf 0..5 begrenzt", lb.sm2(9, 0, 2.5, 0) == lb.sm2(5, 0, 2.5, 0) and
      lb.sm2(-3, 0, 2.5, 0) == lb.sm2(0, 0, 2.5, 0))
pruef("SM-2: rein (gleiche Eingabe, gleiche Ausgabe)", lb.sm2(4, 3, 2.2, 10) == lb.sm2(4, 3, 2.2, 10))

# ------------------------------------------------------------------ Lokale Prüfung
K = {"antwort": "house", "varianten": ["home"]}
for text in ("house", "House!", "the house", "Home.", "ich glaube house", "ähm, das ist house", "hous"):
    pruef("lokal richtig: %r" % text, lb.pruefen_lokal(text, K) == "richtig", lb.pruefen_lokal(text, K))
for text in ("huose", "garden", "houses and gardens"):
    pruef("lokal offen: %r" % text, lb.pruefen_lokal(text, K) is None)
for text in ("Keine Ahnung", "weiß ich nicht", "ähm, keine Ahnung", "Überspringen"):
    pruef("weiß nicht: %r" % text, lb.pruefen_lokal(text, K) == "weiss_nicht")
for soll, text, erwartet in (("cat", "cut", None), ("3,5", "3.5", "richtig"), ("3,5", "3,50", "richtig"),
                             ("21", "einundzwanzig", "richtig"), ("1.000 Meter", "1000 meter", "richtig"),
                             ("1945", "1946", None), ("drei Äpfel", "3 Äpfel", "richtig"),
                             ("Brötchen", "Broetchen", "richtig"), ("Brötchen", "brotchen", "richtig"),
                             ("café", "cafe", "richtig"), ("50 %", "50 Prozent", "richtig"),
                             ("der Hund", "Hund", "richtig"), ("die", "der", None), ("die", "die", "richtig"),
                             ("to go", "go", "richtig"), ("Fahrrad", "Fahr rad", "richtig"), ("12", "zwölf", "richtig")):
    pruef("lokal %r gegen %r" % (text, soll), lb.pruefen_lokal(text, {"antwort": soll}) == erwartet,
          lb.pruefen_lokal(text, {"antwort": soll}))
pruef("Levenshtein", lb.levenshtein("kitten", "sitting") == 3 and lb.levenshtein("house", "hous") == 1)
pruef("Deutsch: englische Füllwörter bleiben unbekannt (wie vor 0.7)", lb.pruefen_lokal("I think house", K) is None and
      lb.pruefen_lokal("no idea", K) is None)

# ------------------------------------------------------------------ Gäste, Unbekannte, Lesen schreibt nichts
ctx = neu_ctx()
for wer in ("gast1", "-unbekannt-", "oma", "", None):
    for aktion in lb.AKTIONEN:
        r = lb.auftrag({"aktion": aktion, "fach": "Englisch", "thema": "x", "text": "x", "uhrzeit": "17:00"}, wer, ctx)
        if "nur für die Familie" not in r["meldung"]:
            pruef("Gast/Unbekannt %r %s abgelehnt" % (wer, aktion), False, r)
pruef("Gäste und Unbekannte bekommen nichts, ohne Claude", not ctx.gedacht)
for b in ({"aktion": "stand"}, {}, {"aktion": "stand", "fuer": "alle"}, {"aktion": "antwort", "text": "x"}):
    lb.auftrag(b, "alex", ctx)
pruef("Lesen ohne Daten schreibt nichts", alle_dateien(ctx.daten) == [], alle_dateien(ctx.daten))
pruef("ohne aktion = stand", "noch keine Lernkarten" in lb.auftrag({}, "kim", ctx)["meldung"])
pruef("andere Person ohne Karten", lb.auftrag({"aktion": "stand", "fuer": "Sam"}, "alex", ctx)["meldung"] ==
      "Sam hat noch keine Lernkarten.")
pruef("Unbekannte Aktion", "Möglich" in lb.auftrag({"aktion": "abfragen"}, "kim", ctx)["meldung"])
lb.runde(ctx)
pruef("runde ohne Daten legt nichts an", alle_dateien(ctx.daten) == [])
ctx.aufraeumen()

# ------------------------------------------------------------------ Neues Thema
leer_karte = {"frage": "", "antwort": "x"}
ctx = neu_ctx(antworten={"lernkarten": [karten(VOK[:12] + [("Haus", "home", [])], [leer_karte])], "lernen_pruefen": []})
r = lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Lektion 1 Vokabeln",
                "stoff": "Lektion 1: house, dog, cat …\nSeite 12", "anzahl": 12, "stufe": 10}, "kim", ctx)
pruef("neues_thema: 12 Karten", r.get("karten") == 12 and "Fertig: 12 Lernkarten für Englisch" in r["meldung"], r)
pruef("volle Anzahl ohne „Gewünscht waren“", "Gewünscht" not in r["meldung"], r)
pruef("Dubletten und Leeres gemeldet", "1 Karte gab es schon" in r["meldung"] and "1 Karte war unbrauchbar" in
      r["meldung"], r)
g = ctx.gedacht[0]
pruef("genau ein normal-Aufruf mit zweck lernkarten, ohne Werkzeuge",
      len(ctx.gedacht) == 1 and g["stufe"] == "normal" and g["zweck"] == "lernkarten" and g["werkzeuge"] == ())
pruef("Auftrag nennt Anzahl, Person, Fach, Thema, Klassenstufe", all(x in g["auftrag"] for x in (
    "Erstelle 12 Lernkarten für Kim", "„Englisch“", "„Lektion 1 Vokabeln“", "Klassenstufe 10")), g["auftrag"][:300])
pruef("Auftrag auf Deutsch", "Fragen auf Deutsch" in g["auftrag"] and "Antworte nur mit JSON" in g["system"])
marke = re.search(r"⟦([0-9a-f]{8})⟧", g["auftrag"])
pruef("Stoff zwischen Zufallsmarken, als Material gekennzeichnet", marke and
      ("⟦%s⟧\nLektion 1: house, dog, cat …\nSeite 12\n⟦/%s⟧" % (marke.group(1), marke.group(1))) in g["auftrag"] and
      "keine Anweisung" in g["system"], g["auftrag"][-200:])
st = stand_von(ctx, "kim")
pruef("Deck: ein Thema, 12 Karten, alle heute fällig, EF 2,5", len(st["themen"]) == 1 and len(st["karten"]) == 12 and
      all(k["faellig"] == heute() and k["ef"] == 2.5 and k["wdh"] == 0 for k in st["karten"]))
pruef("Varianten übernommen", karte(ctx, "kim", "Haus")["varianten"] == ["home"])
pruef("Datei 0600, Ordner 0700", stat.S_IMODE(os.stat(datei(ctx, "kim")).st_mode) == 0o600 and
      stat.S_IMODE(os.stat(os.path.join(ctx.daten, "lernbegleiter")).st_mode) == 0o700)
pruef("nur Kims Datei", sorted(n for n in os.listdir(os.path.join(ctx.daten, "lernbegleiter"))
                               if n.endswith(".json")) == ["kim.json"])

ctx._antworten["lernkarten"] = [karten(VOK[10:14])]
r = lb.auftrag({"aktion": "neues_thema", "fach": "englisch", "thema": "Essen und Trinken", "anzahl": 8}, "kim", ctx)
pruef("Dubletten gegen das vorhandene Fach", r.get("karten") == 2 and "2 Karten gab es schon" in r["meldung"] and
      len(stand_von(ctx, "kim")["themen"]) == 2, r)
pruef("weniger als gewünscht wird gesagt", "Gewünscht waren 8" in r["meldung"], r)
pruef("Fachname bleibt einheitlich", {t["fach"] for t in stand_von(ctx, "kim")["themen"]} == {"Englisch"})
ctx._antworten["lernkarten"] = [karten([("Brot", "bread", []), ("Ei", "egg", []), ("Käse", "cheese", [])])]
LOESUNG.update({"Ei": "egg", "Käse": "cheese"})
r = lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Essen und Trinken"}, "kim", ctx)
pruef("gleiches Thema wird ergänzt", "(ergänzt)" in r["meldung"] and r["karten"] == 2 and
      len(stand_von(ctx, "kim")["themen"]) == 2, r)
pruef("ohne anzahl: Standard 12 im Auftrag", "Erstelle 12 Lernkarten" in ctx.gedacht[-1]["auftrag"])
for anz, soll in ((5, 8), (50, 30), ("15", 15)):
    ctx._antworten["lernkarten"] = [karten([("Rot", "red", []), ("Blau", "blue", []), ("Grün", "green", [])])]
    r = lb.auftrag({"aktion": "neues_thema", "fach": "Malkurs %s" % anz, "thema": "Farben", "anzahl": anz}, "kim", ctx)
    pruef("anzahl %r -> %d" % (anz, soll), ("Erstelle %d Lernkarten" % soll) in ctx.gedacht[-1]["auftrag"] and
          (("diesmal %d" % soll) in r["meldung"]) == (anz != "15"), (r, ctx.gedacht[-1]["auftrag"][:60]))
n = len(ctx.gedacht)
pruef("ohne Fach/Thema: Rückfrage ohne Claude", "Fach und Thema" in
      lb.auftrag({"aktion": "neues_thema", "thema": "x"}, "kim", ctx)["meldung"] and len(ctx.gedacht) == n)
ctx._antworten["lernkarten"] = ['[{"frage": "Was heißt rot?", "antwort": "red"}, {"frage": "Was heißt blau?", '
                                '"antwort": "blue"}, {"frage": "Was heißt gelb?", "antwort": "yellow"}]']
r = lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Farben"}, "sam", ctx)
pruef("Antwort als Liste geht", r.get("karten") == 3, r)
ctx._antworten["lernkarten"] = ['[{"frage": "Was heißt rot?", "antwort": "red"}]']
r = lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Rot"}, "alex", ctx)
pruef("einzelne Karte (json_aus liefert ein Objekt): zu wenig, nichts angelegt", "keine brauchbaren" in r["meldung"]
      and not os.path.exists(datei(ctx, "alex")), r)
pruef("karten_aus: alle Formen", len(lb.karten_aus({"karten": [1, 2]})) == 2 and lb.karten_aus({"frage": "x"}) ==
      [{"frage": "x"}] and lb.karten_aus({"x": 1}) == [] and lb.karten_aus("x") == [])


def kaputt(auftrag, system, stufe):
    raise RuntimeError("Claude nicht erreichbar")


class Abgelehnt(Exception):
    pass


def limit(auftrag, system, stufe):
    raise Abgelehnt("Tageslimit fürs Nachdenken erreicht (2.00 $). Morgen wieder.")


ctx._antworten["lernkarten"] = [kaputt, limit, "kein json"]
for name in ("Claude-Fehler", "Tageslimit", "kein JSON"):
    r = lb.auftrag({"aktion": "neues_thema", "fach": "Erste Hilfe", "thema": name}, "alex", ctx)
    pruef("neues_thema bei %s: Meldung, nichts angelegt" % name, "nicht machen" in r["meldung"] and
          not os.path.exists(datei(ctx, "alex")), r)
ctx._antworten["lernkarten"] = [limit]
pruef("Tageslimit im Text", "Tageslimit" in lb.auftrag({"aktion": "neues_thema", "fach": "Erste Hilfe",
                                                         "thema": "Verbände"}, "alex", ctx)["meldung"])
lang = "Satz. " * 5000
ctx._antworten["lernkarten"] = [karten(VOK[:3])]
r = lb.auftrag({"aktion": "neues_thema", "fach": "Allgemeinwissen", "thema": "Lang", "stoff": lang}, "alex", ctx)
pruef("langer Stoff wird gekürzt und gemeldet", "ersten 20000 Zeichen" in r["meldung"] and
      len(ctx.gedacht[-1]["auftrag"]) < 22000, r)
ctx.aufraeumen()

# ------------------------------------------------------------------ Üben und antworten (zwei Runden, Folgetag)
ctx = neu_ctx(antworten={"lernkarten": [karten(VOK[:12])], "lernen_pruefen": []})
lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Lektion 1", "anzahl": 12}, "kim", ctx)
r = lb.auftrag({"aktion": "antwort", "text": "house"}, "kim", ctx)
pruef("antwort ohne offene Frage", "keine Frage offen" in r["meldung"], r)
r = lb.auftrag({"aktion": "ueben"}, "kim", ctx)
pruef("ueben: Anzahl und erste Frage", r["meldung"].startswith("Heute sind 12 Karten dran. Erste Frage, Englisch: "
                                                               "Was heißt „Haus“") and r["faellig"] == 12, r)
pruef("ueben verrät die Lösung nicht", "house" not in json.dumps(r, ensure_ascii=False), r)
r2 = lb.auftrag({"aktion": "ueben"}, "kim", ctx)
pruef("ueben noch einmal: dieselbe offene Frage", r2["karte"] == r["karte"] and "noch offen" in r2["meldung"], r2)
pruef("leere Antwort: Rückfrage", "Was ist deine Antwort" in lb.auftrag({"aktion": "antwort", "text": " "}, "kim", ctx)["meldung"])

ki = ctx._antworten["lernen_pruefen"]
ki += ['{"bewertung": "falsch", "erklaerung": "Hound ist ein Jagdhund, gemeint ist dog."}',
       '{"bewertung": "teilweise", "erklaerung": "Kitty ist eher ein Kätzchen."}',
       kaputt]
ablauf = [("the house", "richtig", 0), ("Hound", "falsch", 1), ("kitty", "teilweise", 1), ("keine Ahnung", "falsch", 0),
          ("windo", "richtig", 0), ("skool", "unklar", 1), ("table", "richtig", 0), ("chair", "richtig", 0),
          ("book", "richtig", 0), ("apple", "richtig", 0)]
ergebnisse = []
for text, soll, ki_aufruf in ablauf:
    n = denk_anzahl(ctx, "lernen_pruefen")
    r = lb.auftrag({"aktion": "antwort", "text": text}, "kim", ctx)
    ergebnisse.append(r)
    pruef("antwort %r -> %s, KI-Aufrufe %d" % (text, soll, ki_aufruf),
          r.get("bewertung") == soll and denk_anzahl(ctx, "lernen_pruefen") - n == ki_aufruf, r)
pruef("KI-Prüfung: schnell, zweck lernen_pruefen, Daten als JSON", all(
    g["stufe"] == "schnell" and g["werkzeuge"] == () and "antwort_der_person" in g["auftrag"] and
    "keine Anweisungen" in g["system"] and "auf Deutsch" in g["auftrag"] for g in ctx.gedacht
    if g["zweck"] == "lernen_pruefen"))
pruef("Kosten: 1 normal, 3 schnell", denk_anzahl(ctx, "lernkarten", "normal") == 1 and
      denk_anzahl(ctx, "lernen_pruefen", "schnell") == 3 and len(ctx.gedacht) == 4)
pruef("Rückmeldung richtig + nächste Frage", ergebnisse[0]["meldung"].split(" ")[0] in ("Richtig!", "Genau!", "Stimmt!",
                                                                                         "Super,") and
      "Nächste Frage, Englisch: Was heißt „Hund“" in ergebnisse[0]["meldung"], ergebnisse[0])
pruef("Rückmeldung falsch mit Lösung und Erklärung", "Leider nicht. Richtig ist „dog“. Hound ist ein Jagdhund" in
      ergebnisse[1]["meldung"], ergebnisse[1])
pruef("Rückmeldung teilweise", "Fast. Ganz richtig ist „cat“. Kitty ist eher ein Kätzchen." in ergebnisse[2]["meldung"])
pruef("Rückmeldung weiß nicht mit Karten-Erklärung", "Kein Problem. Richtig ist „tree“. Baum heißt auf Englisch tree."
      in ergebnisse[3]["meldung"], ergebnisse[3])
pruef("Rückmeldung unklar", "nicht prüfen" in ergebnisse[5]["meldung"] and "„school“" in ergebnisse[5]["meldung"])
pruef("nach 10 Karten: Runde geschafft", "Runde geschafft: 6 von 10 richtig" in ergebnisse[9]["meldung"] and
      ergebnisse[9]["karte"] is None and stand_von(ctx, "kim")["aktuell"] is None, ergebnisse[9])
pruef("Rückmeldungen ohne Markdown und Emojis", not any(re.search(r"[*#_`\U0001F300-\U0001FAFF]", x["meldung"])
                                                        for x in ergebnisse))

k = {de: karte(ctx, "kim", de) for de, _, _ in VOK[:12]}
pruef("SM-2 richtig: wdh 1, EF 2,6, morgen fällig", (k["Haus"]["wdh"], k["Haus"]["ef"], k["Haus"]["faellig"],
                                                      k["Haus"]["nochmal"]) == (1, 2.6, heute(1), None), k["Haus"])
pruef("SM-2 falsch: wdh 0, EF 1,96, heute nochmal", (k["Hund"]["wdh"], k["Hund"]["ef"], k["Hund"]["nochmal"]) ==
      (0, 1.96, heute()), k["Hund"])
pruef("SM-2 teilweise: wdh 1, EF 2,36, heute nochmal", (k["Katze"]["wdh"], k["Katze"]["ef"], k["Katze"]["nochmal"]) ==
      (1, 2.36, heute()), k["Katze"])
pruef("Tippfehler (windo) zählt richtig", k["Fenster"]["wdh"] == 1)
pruef("unklar: Planung unverändert, heute nochmal", (k["Schule"]["bewertet"], k["Schule"]["ef"], k["Schule"]["faellig"],
                                                     k["Schule"]["nochmal"]) == (None, 2.5, heute(), heute()), k["Schule"])

r = lb.auftrag({"aktion": "ueben"}, "kim", ctx)
pruef("zweite Runde: 2 neue + 4 zum Wiederholen", r["faellig"] == 6 and "„Wasser“" in r["meldung"], r)
for text in ("water", "friend"):
    r = lb.auftrag({"aktion": "antwort", "text": text}, "kim", ctx)
pruef("danach die Wiederholungen, älteste zuerst", "„Hund“" in r["meldung"], r)
ef_vorher = karte(ctx, "kim", "Hund")["ef"]
r = lb.auftrag({"aktion": "antwort", "text": "dog"}, "kim", ctx)
h = karte(ctx, "kim", "Hund")
pruef("Wiederholung am selben Tag ändert SM-2 nicht", h["ef"] == ef_vorher and h["wdh"] == 0 and h["faellig"] == heute(1)
      and h["nochmal"] is None and stand_von(ctx, "kim")["protokoll"][-1]["wiederholung"] is True, h)
for text in ("cat", "tree"):
    r = lb.auftrag({"aktion": "antwort", "text": text}, "kim", ctx)
r = lb.auftrag({"aktion": "antwort", "text": "school"}, "kim", ctx)
s = karte(ctx, "kim", "Schule")
pruef("nach „unklar“ zählt die nächste Antwort voll", (s["wdh"], s["ef"], s["bewertet"]) == (1, 2.6, heute()), s)
pruef("alles geschafft, morgen 12", "Das war die letzte für heute" in r["meldung"] and "Morgen sind 12 Karten dran" in
      r["meldung"] and r["karte"] is None, r)
r = lb.auftrag({"aktion": "ueben"}, "kim", ctx)
pruef("ueben ohne Fälliges", "Für heute ist alles geschafft! Morgen sind 12 Karten dran." == r["meldung"], r)
pruef("keine weiteren KI-Aufrufe für lokal Erkanntes", len(ctx.gedacht) == 4, len(ctx.gedacht))

r = lb.auftrag({"aktion": "stand"}, "kim", ctx)
pruef("stand: fällig, gelernt, Trefferquote (Wiederholungen zählen nicht)",
      r["meldung"] == "Englisch: 0 heute fällig, 10 von 12 gelernt, Trefferquote der letzten 7 Tage 79 Prozent bei "
                      "12 Antworten.", r)

ctx._jetzt = BASIS + TAG
r = lb.auftrag({"aktion": "ueben"}, "kim", ctx)
pruef("Folgetag: 12 fällig, schwere Karten (niedriger EF) zuerst", r["faellig"] == 12 and "„Hund“" in r["meldung"], r)
for _ in range(12):
    if "„Haus“" in r["meldung"].split("Frage, ")[-1]:
        break
    r = lb.auftrag({"aktion": "antwort", "text": loesung(r["meldung"].split("Frage, ")[-1])}, "kim", ctx)
r = lb.auftrag({"aktion": "antwort", "text": "home"}, "kim", ctx)
pruef("Folgetag: Variante richtig, zweites Intervall 6 Tage", r["bewertung"] == "richtig" and
      karte(ctx, "kim", "Haus")["faellig"] == heute(7) and karte(ctx, "kim", "Haus")["intervall"] == 6,
      karte(ctx, "kim", "Haus"))
pruef("Folgetag ohne KI-Aufruf", len(ctx.gedacht) == 4, len(ctx.gedacht))
ctx._jetzt = BASIS + 9 * TAG
r = lb.auftrag({"aktion": "stand"}, "kim", ctx)
pruef("stand nach über 7 Tagen ohne Üben", "in den letzten 7 Tagen nicht geübt" in r["meldung"] and
      "12 heute fällig" in r["meldung"], r)

# Fach-Filter
ctx._jetzt = BASIS + 9 * TAG
ctx._antworten["lernkarten"] = [json.dumps({"karten": [{"frage": "Wie viel ist %d mal 7?" % i, "antwort": str(i * 7)}
                                                       for i in range(2, 10)]})]
lb.auftrag({"aktion": "neues_thema", "fach": "Kopfrechnen", "thema": "Siebenerreihe"}, "kim", ctx)
lb.auftrag({"aktion": "ueben"}, "kim", ctx)          # offene Englisch-Frage
r = lb.auftrag({"aktion": "ueben", "fach": "kopfrechnen"}, "kim", ctx)
pruef("fach-Filter wechselt die offene Frage", "Kopfrechnen: Wie viel ist" in r["meldung"] and r["faellig"] == 8, r)
r = lb.auftrag({"aktion": "antwort", "text": "vierzehn"}, "kim", ctx)
pruef("Zahlwort gegen Ziffer, nächste aus demselben Fach", r["bewertung"] == "richtig" and "Kopfrechnen:" in r["meldung"],
      r)
r = lb.auftrag({"aktion": "ueben", "fach": "Physik"}, "kim", ctx)
pruef("unbekanntes Fach nennt die vorhandenen", "Physik" in r["meldung"] and "Englisch, Kopfrechnen" in r["meldung"], r)


# Wettlauf: während der KI-Prüfung wird das Thema gelöscht
def loeschen_waehrenddessen(auftrag, system, stufe):
    lb.auftrag({"aktion": "thema_loeschen", "fach": "Kopfrechnen", "thema": "Siebenerreihe"}, "kim", ctx)
    return '{"bewertung": "richtig", "erklaerung": ""}'


ctx._antworten["lernen_pruefen"] = [loeschen_waehrenddessen]
r = lb.auftrag({"aktion": "antwort", "text": "zweiundzwanzig ungefähr"}, "kim", ctx)
pruef("Frage während der Prüfung weggefallen: sauber gemeldet", "inzwischen geändert" in r["meldung"] and
      not any(t["fach"] == "Kopfrechnen" for t in stand_von(ctx, "kim")["themen"]), r)

# ------------------------------------------------------------------ Stand und Rechte
ctx._jetzt = BASIS
ctx._antworten["lernkarten"] = [karten(VOK[:4])]
lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Tiere"}, "sam", ctx)
r = lb.auftrag({"aktion": "stand", "fuer": "Sam"}, "kim", ctx)
pruef("Kim sieht Sams Stand nicht", "nur die Hauptperson" in r["meldung"] and "Englisch" not in r["meldung"], r)
r = lb.auftrag({"aktion": "stand", "fuer": "kim"}, "sam", ctx)
pruef("Sam sieht Kims Stand nicht", "nur die Hauptperson" in r["meldung"], r)
r = lb.auftrag({"aktion": "stand", "fuer": "alle"}, "kim", ctx)
pruef("„alle“ nur für die Hauptperson", "nur die Hauptperson" in r["meldung"], r)
r = lb.auftrag({"aktion": "stand", "fuer": "Kim"}, "kim", ctx)
pruef("eigener Name geht", r["meldung"].startswith("Englisch:"), r)
r = lb.auftrag({"aktion": "stand", "fuer": "Kim"}, "alex", ctx)
pruef("Hauptperson sieht Kims Stand", r["meldung"].startswith("Kim – Englisch:"), r)
r = lb.auftrag({"aktion": "stand", "fuer": "alle"}, "alex", ctx)
pruef("Hauptperson sieht alle", "Kim – Englisch" in r["meldung"] and "Sam – Englisch" in r["meldung"], r)
pruef("Deutsch: „all“ ist kein Schlüsselwort (wie vor 0.7)", "nicht als Familienmitglied" in
      lb.auftrag({"aktion": "stand", "fuer": "all"}, "alex", ctx)["meldung"])
pruef("Gäste sind kein Familienmitglied", "nicht als Familienmitglied" in
      lb.auftrag({"aktion": "stand", "fuer": "gast1"}, "alex", ctx)["meldung"])
pruef("Unbekannte ebenso", "nicht als Familienmitglied" in
      lb.auftrag({"aktion": "stand", "fuer": "Oma"}, "alex", ctx)["meldung"])
pruef("Hauptperson ohne eigene Karten", "noch keine Lernkarten" in lb.auftrag({"aktion": "stand"}, "alex", ctx)["meldung"])
pruef("eigener Name der Hauptperson, ohne Karten", lb.auftrag({"aktion": "stand", "fuer": "Alex"}, "alex", ctx)
      ["meldung"].startswith("Du hast noch keine Lernkarten"))
vorher = {p: open(p, "rb").read() for p in alle_dateien(ctx.daten)}
for b, p in (({"aktion": "stand"}, "kim"), ({"aktion": "stand", "fuer": "alle"}, "alex"), ({}, "sam")):
    lb.auftrag(b, p, ctx)
pruef("stand schreibt nichts", {p: open(p, "rb").read() for p in alle_dateien(ctx.daten)} == vorher)

# ------------------------------------------------------------------ Erinnern und runde()
for text, soll in (("17:30", "17:30"), ("17 Uhr", "17:00"), ("7", "07:00"), ("18.45", "18:45"), ("aus", None)):
    pruef("uhrzeit_lesen %r" % text, lb.uhrzeit_lesen(text) == soll)
for text in ("25:00", "17:61", "morgen", "17:3", "5 pm"):
    try:
        lb.uhrzeit_lesen(text)
        pruef("uhrzeit_lesen %r abgelehnt" % text, False)
    except ValueError:
        pruef("uhrzeit_lesen %r abgelehnt" % text, True)
pruef("erinnern mit falscher Uhrzeit", "verstehe ich nicht" in
      lb.auftrag({"aktion": "erinnern", "uhrzeit": "halb sechs"}, "kim", ctx)["meldung"])
r = lb.auftrag({"aktion": "erinnern", "uhrzeit": "17:30"}, "kim", ctx)
pruef("erinnern 17:30", "17:30" in r["meldung"] and stand_von(ctx, "kim")["erinnern"]["uhrzeit"] == "17:30", r)
lb.auftrag({"aktion": "erinnern", "uhrzeit": "17:00"}, "sam", ctx)
ctx.pushes.clear()
R = BASIS + 10 * TAG                                 # Tag 10, 12:00: bei Kim und Sam ist einiges fällig
ctx._jetzt = R + 5 * 3600 + 29 * 60                  # 17:29
lb.runde(ctx)
pruef("runde: vor der Uhrzeit kein Push an Kim", not [p for p in ctx.pushes if p["person"] == "kim"])
pruef("runde: Sam (17:00) bekommt ihren", [p["person"] for p in ctx.pushes] == ["sam"] and
      ctx.pushes[0]["text"].startswith("Heute sind 4 Karten fällig (Englisch 4)."), ctx.pushes)
ctx._jetzt = R + 5 * 3600 + 31 * 60                  # 17:31
lb.runde(ctx)
kim_push = [p for p in ctx.pushes if p["person"] == "kim"]
st_kim = stand_von(ctx, "kim")
n_faellig = sum(1 for k in st_kim["karten"] if k["faellig"] <= heute(10) or k.get("nochmal") == heute(10))
pruef("runde: Push an Kim mit Anzahl", n_faellig > 0 and len(kim_push) == 1 and kim_push[0]["titel"] == "Lernbegleiter"
      and kim_push[0]["text"].startswith("Heute sind %d Karten fällig (Englisch %d)." % (n_faellig, n_faellig)) and
      kim_push[0]["tag"] == "lernbegleiter", (kim_push, n_faellig))
lb.runde(ctx)
ctx._jetzt = R + 6 * 3600
lb.runde(ctx)
pruef("höchstens einmal am Tag", len([p for p in ctx.pushes if p["person"] == "kim"]) == 1 and len(ctx.pushes) == 2)
ctx._jetzt = R + TAG + 8 * 3600                      # Folgetag 20:00, mehr als 2 h nach 17:30
lb.runde(ctx)
pruef("zu spät (Brücke war weg): kein Push", len(ctx.pushes) == 2, ctx.pushes)
ctx._jetzt = R + 2 * TAG + 5 * 3600 + 35 * 60        # übermorgen 17:35
lb.runde(ctx)
pruef("am nächsten Tag wieder", len([p for p in ctx.pushes if p["person"] == "kim"]) == 2, ctx.pushes)

ctx._jetzt = R
ctx._antworten["lernkarten"] = [karten(VOK[:3])]
lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Probe"}, "alex", ctx)
st_p = stand_von(ctx, "alex")
for kk in st_p["karten"]:
    kk["faellig"] = heute(40)
with open(datei(ctx, "alex"), "w", encoding="utf-8") as f:
    json.dump(st_p, f)
lb.auftrag({"aktion": "erinnern", "uhrzeit": "17:30"}, "alex", ctx)
n = len(ctx.pushes)
ctx._jetzt = R + 3 * TAG + 5 * 3600 + 31 * 60
lb.runde(ctx)
pruef("nichts fällig: kein Push an Alex", not [p for p in ctx.pushes[n:] if p["person"] == "alex"], ctx.pushes[n:])
pruef("… aber für heute erledigt vermerkt", stand_von(ctx, "alex")["erinnern"]["zuletzt"] == heute(13))
r = lb.auftrag({"aktion": "erinnern", "uhrzeit": "aus"}, "kim", ctx)
pruef("erinnern aus", "keine Lern-Erinnerung" in r["meldung"] and stand_von(ctx, "kim")["erinnern"] is None)

os.makedirs(os.path.join(ctx.daten, "lernbegleiter"), exist_ok=True)
with open(datei(ctx, "gast1"), "w", encoding="utf-8") as f:
    json.dump(dict(lb._leer(), erinnern={"uhrzeit": "00:00", "zuletzt": None}, themen=st_p["themen"],
                   karten=[dict(kk, faellig=heute()) for kk in st_p["karten"]]), f)
with open(datei(ctx, "sam"), "w") as f:
    f.write("{kaputt")
n = len(ctx.pushes)
ctx._jetzt = R + 4 * TAG + 60
try:
    lb.runde(ctx)
    pruef("runde wirft nicht (kaputte Datei, Gast)", True)
except Exception as e:      # noqa: BLE001
    pruef("runde wirft nicht (kaputte Datei, Gast)", False, e)
pruef("Gast-Datei bekommt keinen Push", not [p for p in ctx.pushes[n:] if p["person"] == "gast1"])


class PersonenKaputt(sh_attrappe.Kontext):
    def personen(self):
        raise RuntimeError("personen.json unlesbar")


ctx_k = PersonenKaputt(jetzt=BASIS)
ctx_k.aufraeumen()                        # eigener leerer Ordner weg, er arbeitet auf dem von ctx
ctx_k.daten = ctx.daten
try:
    lb.runde(ctx_k)
    pruef("runde wirft nicht, wenn Personen fehlen", not ctx_k.pushes)
except Exception as e:      # noqa: BLE001
    pruef("runde wirft nicht, wenn Personen fehlen", False, e)


class OhneKanal(sh_attrappe.Kontext):
    def push(self, person, titel, text, klick=None, tag="jarvis"):
        self.pushes.append({"person": person})
        return False                                 # wie ein Push ohne eingetragenen Kanal


ctx_o = OhneKanal(jetzt=R + 5 * TAG + 5 * 3600 + 31 * 60)
ctx_o.aufraeumen()
ctx_o.daten = ctx.daten
lb.auftrag({"aktion": "erinnern", "uhrzeit": "17:30"}, "kim", ctx_o)
lb.runde(ctx_o)
pruef("Push ohne Kanal: einmal versucht, im Log vermerkt", len(ctx_o.pushes) == 1 and
      any("nicht zugestellt" in z for z in ctx_o.logs), (ctx_o.pushes, ctx_o.logs))
pruef("Personen unlesbar: auftrag lehnt ab", "nur für die Familie" in lb.auftrag({"aktion": "stand"}, "alex", ctx_k)["meldung"])

# ------------------------------------------------------------------ Kaputte Datei, Thema löschen
r = lb.auftrag({"aktion": "stand"}, "sam", ctx)
pruef("kaputte Datei: Lesen gibt leer und lässt sie liegen", "noch keine" in r["meldung"] and
      open(datei(ctx, "sam")).read() == "{kaputt")
lb.auftrag({"aktion": "erinnern", "uhrzeit": "18:00"}, "sam", ctx)
pruef("Schreiben legt die kaputte Datei zur Seite", any(n.startswith("sam.json.kaputt-") for n in
                                                         os.listdir(os.path.join(ctx.daten, "lernbegleiter"))))

r = lb.auftrag({"aktion": "thema_loeschen"}, "kim", ctx)
pruef("thema_loeschen ohne Thema listet", "Englisch: Lektion 1" in r["meldung"], r)
r = lb.auftrag({"aktion": "thema_loeschen", "thema": "Lektion 9"}, "kim", ctx)
pruef("thema_loeschen unbekannt listet", "habe ich bei dir nicht" in r["meldung"], r)
ctx._antworten["lernkarten"] = [json.dumps({"karten": [{"frage": "Was heißt Haus auf Spanisch?", "antwort": "casa"},
                                                       {"frage": "Was heißt Hund auf Spanisch?", "antwort": "perro"},
                                                       {"frage": "Was heißt Katze auf Spanisch?", "antwort": "gato"}]})]
lb.auftrag({"aktion": "neues_thema", "fach": "Spanisch", "thema": "Lektion 1"}, "kim", ctx)
r = lb.auftrag({"aktion": "thema_loeschen", "thema": "Lektion 1"}, "kim", ctx)
pruef("gleiches Thema in zwei Fächern: Rückfrage", "mehreren Fächern" in r["meldung"] and "Spanisch" in r["meldung"], r)
ctx._jetzt = R + 20 * TAG
lb.auftrag({"aktion": "ueben", "fach": "Englisch"}, "kim", ctx)
offen = stand_von(ctx, "kim")["aktuell"]["karte"]
r = lb.auftrag({"aktion": "thema_loeschen", "fach": "englisch", "thema": "lektion 1"}, "kim", ctx)
st = stand_von(ctx, "kim")
pruef("Thema gelöscht: Karten, Protokoll, offene Frage", r["karten"] == 12 and "Gelöscht: Englisch, „Lektion 1“ mit 12 "
      "Karten." == r["meldung"] and not any(k["id"] == offen for k in st["karten"]) and st["aktuell"] is None and
      not any(p.get("karte") == offen for p in st["protokoll"]), r)
pruef("das gleichnamige Thema im anderen Fach bleibt", [(t["fach"], t["thema"]) for t in st["themen"]] ==
      [("Spanisch", "Lektion 1")] and len(st["karten"]) == 3, st["themen"])
ctx.aufraeumen()

# ------------------------------------------------------------------ Parallel: drei Personen gleichzeitig
ctx = neu_ctx(antworten={"lernkarten": lambda a, s, st: karten(VOK[:5])})
fehler = []


def lege_an(p):
    try:
        lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Parallel"}, p, ctx)
        for _ in range(3):
            lb.auftrag({"aktion": "ueben"}, p, ctx)
            lb.auftrag({"aktion": "antwort", "text": "house"}, p, ctx)
    except Exception as e:      # noqa: BLE001
        fehler.append(e)


faeden = [threading.Thread(target=lege_an, args=(p,)) for p in ("alex", "sam", "kim")]
for t in faeden:
    t.start()
for t in faeden:
    t.join()
pruef("drei Personen parallel: je eigene Datei, nichts verloren", not fehler and
      all(len(stand_von(ctx, p)["karten"]) == 5 for p in ("alex", "sam", "kim")), fehler)
ctx.aufraeumen()

# ------------------------------------------------------------------ Fremder Text (Sicherheitspruefung vor 0.7, S1)
# Stoff aus einer Frage mit fremdem Text (Foto, Mail ...) markiert das Thema; jede spaetere Ausgabe ausser erinnern meldet
# "fremd": True, damit sich der Text nicht ueber den Lernstand "waschen" laesst.
ctx = neu_ctx(antworten={"lernkarten": lambda a, s, st: karten(VOK[:4])})
r = lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Sauber"}, "sam", ctx)
pruef("S1: sauberer Stoff, keine Fremd-Meldung", "fremd" not in r and not stand_von(ctx, "sam")["themen"][0]["fremd"], r)
pruef("S1: sauber geübt, keine Fremd-Meldung", "fremd" not in lb.auftrag({"aktion": "ueben"}, "sam", ctx))
ctx.fremd = "Anhang"
r = lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Arbeitsblatt"}, "kim", ctx)
pruef("S1: Stoff aus fremdem Text markiert das Thema", r.get("fremd") is True and
      stand_von(ctx, "kim")["themen"][0]["fremd"] == "Anhang", (r, stand_von(ctx, "kim")["themen"]))
ctx.fremd = ""
for aktion, b in (("ueben", {}), ("antwort", {"text": "house"}), ("stand", {})):
    r = lb.auftrag(dict(b, aktion=aktion), "kim", ctx)
    pruef("S1: spätere saubere Frage, %s meldet fremd" % aktion, r.get("fremd") is True, r)
r = lb.auftrag({"aktion": "erinnern", "uhrzeit": "17:00"}, "kim", ctx)
pruef("S1: erinnern gibt keinen Lernstoff wieder, keine Fremd-Meldung", "fremd" not in r, r)
pruef("S1: Hauptperson ohne fuer: nur der eigene Stand zählt", "fremd" not in lb.auftrag({"aktion": "stand"}, "alex", ctx))
pruef("S1: Hauptperson mit fuer „alle“: fremd", lb.auftrag({"aktion": "stand", "fuer": "alle"}, "alex", ctx)
      .get("fremd") is True)
pruef("S1: Familie fragt nach anderen (abgelehnt), eigener Stand sauber",
      "fremd" not in lb.auftrag({"aktion": "stand", "fuer": "Kim"}, "sam", ctx))
ctx.fremd = "postfach"
ctx._antworten["lernkarten"] = lambda a, s, st: karten(VOK[4:8])
lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Sauber"}, "sam", ctx)
pruef("S1: neue fremde Karten markieren ein bestehendes sauberes Thema", any(
    t["thema"] == "Sauber" and t["fremd"] == "postfach" for t in stand_von(ctx, "sam")["themen"]))
ctx.fremd = 'Anhang,post"fach;<x>'
ctx._antworten["lernkarten"] = lambda a, s, st: karten(VOK[8:12])
lb.auftrag({"aktion": "neues_thema", "fach": "Englisch", "thema": "Zeichen"}, "alex", ctx)
pruef("S1: Fremdarten bereinigt gespeichert", [t["fremd"] for t in stand_von(ctx, "alex")["themen"]] ==
      ["Anhang,postfachx"], stand_von(ctx, "alex")["themen"])
ctx.fremd = ""
r = lb.auftrag({"aktion": "thema_loeschen", "fach": "Englisch", "thema": "Arbeitsblatt"}, "kim", ctx)
pruef("S1: Löschen eines fremden Themas meldet fremd (Name steht in der Meldung)", r.get("fremd") is True and
      r.get("karten") == 4, r)
r = lb.auftrag({"aktion": "stand"}, "kim", ctx)
pruef("S1: danach ohne fremdes Thema wieder sauber", "fremd" not in r, r)
ctx.aufraeumen()

# ------------------------------------------------------------------ Englisch
try:
    lb.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", True)
pruef("nach Ablehnung weiter Deutsch", lb.SPRACHE == "de")
lb.setze_sprache("en")
DEUTSCH = re.compile(r"[äöüÄÖÜß„]|\b(ist|sind|nicht|Bitte|bitte|und|oder|der|die|das|Karte|Karten|heute|morgen|Frage|"
                     r"Fach|Thema|Runde|richtig|Lernkarten|keine|schon|noch|dir|du|Du)\b")


def englisch(name, text, *teile):
    pruef("EN: %s" % name, isinstance(text, str) and not DEUTSCH.search(text) and all(t in text for t in teile), text)


EN_VOK = [("house", "casa", []), ("dog", "perro", []), ("cat", "gato", []), ("tree", "árbol", []),
          ("window", "ventana", []), ("school", "escuela", []), ("table", "mesa", []), ("chair", "silla", []),
          ("book", "libro", []), ("apple", "manzana", []), ("water", "agua", []), ("friend", "amigo", ["amiga"])]


def karten_en(paare):
    return json.dumps({"karten": [{"frage": "What is “%s” in Spanish?" % en, "antwort": es, "varianten": v,
                                   "erklaerung": "%s is %s in Spanish." % (en.capitalize(), es)}
                                  for en, es, v in paare]}, ensure_ascii=False)


w = lb.WERKZEUG
englisch("WERKZEUG-Beschreibung", w["beschreibung"], "Study buddy", "flashcards", "SM-2", "“all”", "“off”")
pruef("EN: Schema und Aktionen unverändert", w["schema"]["properties"]["aktion"]["enum"] == list(lb.AKTIONEN) and
      set(w["schema"]["properties"]) == {"aktion", "fach", "thema", "stoff", "anzahl", "stufe", "text", "fuer",
                                         "uhrzeit"})
pruef("EN: Vorlagen unverändert (WERKZEUG ist eine Kopie)", lb.WERKZEUG_DE["beschreibung"].startswith("Lernbegleiter")
      and w is not lb.WERKZEUG_EN)

ctx = neu_ctx(antworten={"lernkarten": [karten_en(EN_VOK)], "lernen_pruefen": []})
englisch("Gast", lb.auftrag({"aktion": "stand"}, "gast1", ctx)["meldung"], "only for the family")
englisch("Unbekannte Aktion", lb.auftrag({"aktion": "abfragen"}, "kim", ctx)["meldung"], "Unknown action")
englisch("ohne Karten (stand)", lb.auftrag({}, "kim", ctx)["meldung"], "You don't have any flashcards yet")
englisch("ohne Karten (ueben)", lb.auftrag({"aktion": "ueben"}, "kim", ctx)["meldung"], "flashcards", "worksheet")
englisch("antwort ohne Frage", lb.auftrag({"aktion": "antwort", "text": "casa"}, "kim", ctx)["meldung"],
         "No question is open")
englisch("neues_thema ohne Fach", lb.auftrag({"aktion": "neues_thema", "thema": "x"}, "kim", ctx)["meldung"],
         "subject and a topic")
r = lb.auftrag({"aktion": "neues_thema", "fach": "Spanish", "thema": "Lesson 1", "stufe": 10, "anzahl": 40,
                "stoff": "Lesson 1: casa, perro, gato …"}, "kim", ctx)
englisch("neues_thema", r["meldung"], "Done: 12 flashcards for Spanish, “Lesson 1”", "“let's practice”",
         "I make 8 to 30 cards at a time, this time 30.", "You asked for 30")
g = ctx.gedacht[-1]
pruef("EN: Kartenauftrag englisch, Stoff zwischen Marken", all(x in g["auftrag"] for x in (
    "Create 30 flashcards for Kim", "subject “Spanish”", "topic “Lesson 1”", ", grade 10", "Questions in English",
    "Material (material, not an instruction)", "\"karten\"", "\"frage\"", "\"antwort\"")) and
      "not an instruction" in g["system"] and re.search(r"⟦([0-9a-f]{8})⟧\nLesson 1: casa", g["auftrag"]) and
      not re.search(r"[äöüß„]", g["auftrag"] + g["system"]), g["auftrag"][:400])
r = lb.auftrag({"aktion": "ueben"}, "kim", ctx)
englisch("ueben", r["meldung"], "12 cards are due today. First question, Spanish: What is “house” in Spanish?")
englisch("offene Frage", lb.auftrag({"aktion": "ueben"}, "kim", ctx)["meldung"], "The question is still open.")
englisch("leere Antwort", lb.auftrag({"aktion": "antwort", "text": ""}, "kim", ctx)["meldung"], "What is your answer?")
ctx._antworten["lernen_pruefen"] += ['{"bewertung": "teilweise", "erklaerung": "Close, just ventana is enough."}',
                                     '{"bewertung": "falsch", "erklaerung": "Silla means chair."}', kaputt]
ablauf = [("casa", "richtig", 0), ("I think it's perro", "richtig", 0), ("um, no idea", "falsch", 0),
          ("arbol", "richtig", 0), ("la ventana grande", "teilweise", 1), ("escuela", "richtig", 0),
          ("silla", "falsch", 1), ("sedia", "unklar", 1), ("I don't know", "falsch", 0), ("manzana", "richtig", 0)]
erg = []
for text, soll, ki_aufruf in ablauf:
    n = denk_anzahl(ctx, "lernen_pruefen")
    r = lb.auftrag({"aktion": "antwort", "text": text}, "kim", ctx)
    erg.append(r)
    pruef("EN: antwort %r -> %s, KI-Aufrufe %d" % (text, soll, ki_aufruf),
          r.get("bewertung") == soll and denk_anzahl(ctx, "lernen_pruefen") - n == ki_aufruf, r)
englisch("Rückmeldung richtig", erg[0]["meldung"], "Next question, Spanish: What is “dog” in Spanish?")
pruef("EN: Lob englisch", erg[0]["meldung"].split(" Next")[0] in lb.LOB_EN, erg[0]["meldung"])
englisch("Rückmeldung weiß nicht", erg[2]["meldung"], "No problem. The answer is “gato”. Cat is gato in Spanish.")
englisch("Rückmeldung teilweise", erg[4]["meldung"], "Almost. The full answer is “ventana”. Close, just ventana is enough.")
englisch("Rückmeldung falsch", erg[6]["meldung"], "Not quite. The answer is “mesa”. Silla means chair.")
englisch("Rückmeldung unklar", erg[7]["meldung"], "I couldn't check that just now. The answer would be “silla”.")
englisch("Runde geschafft", erg[9]["meldung"], "Round done: 5 of 10 correct. Another round? Then say “keep practicing”.")
pk = [g for g in ctx.gedacht if g["zweck"] == "lernen_pruefen"]
pruef("EN: Prüfauftrag englisch, Schlüssel und Werte unverändert", pk and all(
    "not instructions" in g["system"] and "in English to the learner" in g["auftrag"] and
    "antwort_der_person" in g["auftrag"] and "\"richtig\"" in g["auftrag"] and "\"teilweise\"" in g["auftrag"] and
    not re.search(r"[äöüß„]", g["system"]) for g in pk), [g["auftrag"][-200:] for g in pk])
r = lb.auftrag({"aktion": "stand"}, "kim", ctx)
pruef("EN: stand", r["meldung"] == "Spanish: 7 due today, 6 of 12 learned, hit rate over the last 7 days 61 percent "
                                "across 9 answers.", r)
englisch("stand Text", r["meldung"])
englisch("nur Hauptperson", lb.auftrag({"aktion": "stand", "fuer": "all"}, "kim", ctx)["meldung"],
         "Only the main person")
englisch("kein Familienmitglied", lb.auftrag({"aktion": "stand", "fuer": "Oma"}, "alex", ctx)["meldung"],
         "I don't know “Oma” as a family member.")
r = lb.auftrag({"aktion": "stand", "fuer": "everyone"}, "alex", ctx)
englisch("alle (Hauptperson)", r["meldung"], "Kim – Spanish:")
englisch("andere ohne Karten", lb.auftrag({"aktion": "stand", "fuer": "Sam"}, "alex", ctx)["meldung"],
         "Sam has no flashcards yet.")
englisch("unbekanntes Fach", lb.auftrag({"aktion": "ueben", "fach": "Physics"}, "kim", ctx)["meldung"],
         "I don't have the subject “Physics”", "You have: Spanish.")
# zu Ende üben
r = lb.auftrag({"aktion": "ueben"}, "kim", ctx)
for _ in range(20):
    if r.get("karte") is None and "First question" not in r["meldung"] and "Next question" not in r["meldung"]:
        break
    frage = re.search(r"What is “(.+?)” in Spanish\?", r["meldung"].split("question, ")[-1])
    loes = {en: es for en, es, _ in EN_VOK}[frage.group(1)]
    r = lb.auftrag({"aktion": "antwort", "text": loes}, "kim", ctx)
englisch("letzte für heute", r["meldung"], "That was the last one for today, well done! Tomorrow ", " cards are due.")
englisch("alles geschafft", lb.auftrag({"aktion": "ueben"}, "kim", ctx)["meldung"], "All done for today! Tomorrow")

for text, soll in (("No idea", "weiss_nicht"), ("I don't know", "weiss_nicht"), ("dunno", "weiss_nicht"),
                   ("um, I have no idea", "weiss_nicht"), ("skip", "weiss_nicht")):
    pruef("EN: weiß nicht %r" % text, lb.pruefen_lokal(text, {"antwort": "casa"}) == soll)
for soll, text, erwartet in (("21", "twenty-one", "richtig"), ("21", "twenty one", "richtig"), ("12", "twelve", "richtig"),
                             ("1,000 meters", "1000 meters", "richtig"), ("3.5", "3,5", "richtig"),
                             ("50 %", "50 percent", "richtig"), ("pass", "pass", "richtig"), ("no", "no", "richtig"),
                             ("1,000", "1", None), ("house", "I think it's the house", "richtig"),
                             ("house", "perhaps home", None)):
    pruef("EN: lokal %r gegen %r" % (text, soll), lb.pruefen_lokal(text, {"antwort": soll}) == erwartet,
          lb.pruefen_lokal(text, {"antwort": soll}))
for text, soll in (("5 pm", "17:00"), ("5:30 pm", "17:30"), ("7 am", "07:00"), ("12 am", "00:00"), ("12 pm", "12:00"),
                   ("17:30", "17:30"), ("6 o'clock", "06:00"), ("off", None), ("none", None), ("aus", None)):
    pruef("EN: uhrzeit_lesen %r" % text, lb.uhrzeit_lesen(text) == soll, lb.uhrzeit_lesen(text))
for text in ("13 pm", "half past five", "25:00"):
    try:
        lb.uhrzeit_lesen(text)
        pruef("EN: uhrzeit_lesen %r abgelehnt" % text, False)
    except ValueError:
        pruef("EN: uhrzeit_lesen %r abgelehnt" % text, True)
englisch("erinnern falsch", lb.auftrag({"aktion": "erinnern", "uhrzeit": "teatime"}, "sam", ctx)["meldung"],
         "I don't understand the time")
ctx._antworten["lernkarten"] = [json.dumps({"karten": json.loads(karten_en(EN_VOK[:4] + EN_VOK[:1]))["karten"] +
                                           [{"frage": "", "antwort": "x"}]}, ensure_ascii=False)]
englisch("neues_thema Sam", lb.auftrag({"aktion": "neues_thema", "fach": "Spanish", "thema": "Animals"}, "sam",
                                       ctx)["meldung"], "Done: 4 flashcards", "Left out 1 card that already existed.",
         "1 card was unusable.", "You asked for 12, the material did not give more.")
englisch("erinnern", lb.auftrag({"aktion": "erinnern", "uhrzeit": "5:30 pm"}, "sam", ctx)["meldung"],
         "every day at 17:30")
ctx.pushes.clear()
ctx._jetzt = BASIS + 5 * 3600 + 31 * 60
lb.runde(ctx)
sp = [p for p in ctx.pushes if p["person"] == "sam"]
pruef("EN: Push-Titel und -Text", len(sp) == 1 and sp[0]["titel"] == "Study buddy" and sp[0]["tag"] == "lernbegleiter"
      and sp[0]["text"] == "4 cards are due today (Spanish 4). Just say “Jarvis, let's practice”." and not DEUTSCH.search(sp[0]["text"]), sp)
englisch("erinnern aus", lb.auftrag({"aktion": "erinnern", "uhrzeit": "off"}, "sam", ctx)["meldung"],
         "no more study reminders")
englisch("thema_loeschen ohne Thema", lb.auftrag({"aktion": "thema_loeschen"}, "kim", ctx)["meldung"],
         "Which topic should I delete? You have: Spanish: Lesson 1.")
englisch("thema_loeschen unbekannt", lb.auftrag({"aktion": "thema_loeschen", "thema": "Lesson 9"}, "kim", ctx)["meldung"],
         "I don't have the topic “Lesson 9”")
englisch("thema_loeschen", lb.auftrag({"aktion": "thema_loeschen", "thema": "Lesson 1"}, "kim", ctx)["meldung"],
         "Deleted: Spanish, “Lesson 1” with 12 cards.")
ctx._antworten["lernkarten"] = [kaputt]
englisch("Claude-Fehler", lb.auftrag({"aktion": "neues_thema", "fach": "First aid", "thema": "Bandages"}, "kim",
                                     ctx)["meldung"], "I couldn't make the flashcards just now",
         "Claude was not reachable")
ctx._antworten["lernkarten"] = ['[{"frage": "What is red?", "antwort": "rojo"}]']
englisch("zu wenig Karten", lb.auftrag({"aktion": "neues_thema", "fach": "Spanish", "thema": "Colors"}, "kim",
                                       ctx)["meldung"], "usable flashcards")
ctx.aufraeumen()
lb.setze_sprache("de")
ctx = neu_ctx()
pruef("Zurück auf Deutsch: WERKZEUG und Meldungen", lb.SPRACHE == "de" and
      lb.WERKZEUG["beschreibung"] == lb.WERKZEUG_DE["beschreibung"] and lb.pruefen_lokal("no idea", K) is None and
      "nur für die Familie" in lb.auftrag({}, "gast1", ctx)["meldung"])
ctx.aufraeumen()

pruef("Live-Daten unberührt", unveraendert())
sys.exit(ergebnis("S8 Lernbegleiter"))
