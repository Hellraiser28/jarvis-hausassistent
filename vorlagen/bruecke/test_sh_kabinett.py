#!/usr/bin/env python3
"""Kabinett (S2, Superhirn, seit 0.7) mit der Attrappe: ohne Netz, ohne Claude, Testordner statt Live-Daten.

Prueft: Import ohne Nebenwirkungen, Lautsprecher-Sperre, englische Fassung (setze_sprache), vier Stimmen parallel und unabhaengig (keine sieht die andere), Advocatus diaboli
greift die naheliegende Loesung an, Zusammenfassung, hoechstens fuenf Denkaufrufe, Stufe normal, kaputtes JSON und
fehlende Stimmen (ehrlich gemeldet), alle oder fast alle Stimmen weg, Tageslimit, Pruefung der Modellantworten
(Grenzen, Marken), Wiedervorlage mit Push zum Termin (Zeitfenster, einmal, Fehlversuche), Rueckblick als
Lernerfahrung (hoechstens 5, je Person getrennt), Rechte (Gaeste nie, fremde Nummern), lesende Aktionen schreiben
nichts, runde wirft nie, Dateirechte 0600, Einordnung fuer Fremdtext und superhirn.nur_lesend.
Laeuft mit: python3 tests/test_sh_kabinett.py
"""
import datetime as dt
import importlib
import json
import os
import re
import stat
import sys
import threading
import time

HIER = os.path.dirname(os.path.abspath(__file__))
ZWEIG = os.path.dirname(HIER)
sys.path[:0] = [HIER, os.path.join(ZWEIG, "bruecke")]

import sh_attrappe  # noqa: E402

pruef, ergebnis = sh_attrappe.pruefer()
wache = sh_attrappe.live_wache()

vorher = set(os.listdir(os.path.join(ZWEIG, "bruecke")))
kb = importlib.import_module("kabinett")
pruef("Import ohne Nebenwirkungen (keine Datei im Modulordner)", set(os.listdir(os.path.join(ZWEIG, "bruecke"))) - vorher
      <= {"__pycache__"})
import denken  # noqa: E402
import superhirn  # noqa: E402


def zeit(j, mo, t, h, mi=0):
    return time.mktime(dt.datetime(j, mo, t, h, mi).timetuple())


def stimme(tag, empf=None):
    return json.dumps({"haltung": "Haltung %s" % tag, "gruende": ["Grund A %s" % tag, "Grund B", "Grund C", "Grund D"],
                       "risiko": "Risiko %s" % tag, "empfehlung": empf or "Empfehlung %s" % tag,
                       "angegriffen": "Sofort kaufen"}, ensure_ascii=False)


SYN = json.dumps({"empfehlung": "Noch ein halbes Jahr warten und dann gebraucht kaufen",
                  "begruendung": "Weil die Preise fallen.", "staerkste_gegenrede": "Das alte Auto kann jederzeit ausfallen",
                  "offene_fragen": ["Wie alt ist das Auto?", "Gibt es Förderung?", "Wo laden?", "Vierte Frage"],
                  "sicherheit": "72"}, ensure_ascii=False)


def antworten(**aus):
    a = {"kabinett_sparfuchs": stimme("SPAR-111"), "kabinett_familie": stimme("FAM-222"),
         "kabinett_zukunft": stimme("ZUK-333"), "kabinett_advocatus": stimme("ADV-444"), "kabinett_synthese": SYN}
    for k, v in aus.items():
        if v is None:
            a.pop("kabinett_" + k, None)
        else:
            a["kabinett_" + k] = v
    return a


def neu(**kw):
    kw.setdefault("jetzt", zeit(2026, 11, 6, 20, 0))
    return sh_attrappe.Kontext(**kw)


# ------------------------------------------------------------------ Grundgeruest
pruef("Schnittstelle: NAME, RECHTE familie, TAKT_S, WERKZEUG mit Schema",
      kb.NAME == "kabinett" and kb.RECHTE == "familie" and kb.TAKT_S > 0 and
      set(kb.WERKZEUG["schema"]["properties"]["aktion"]["enum"]) == {"beraten", "wiedervorlage", "rueckblick", "liste",
                                                                    "zeigen"})
pruef("Fremdtext: Ziel, nur liste und zeigen lesend",
      kb.FREMDTEXT["art"] == "ziel" and kb.FREMDTEXT["nur_lesen"][0] == "aktion" and
      kb.FREMDTEXT["nur_lesen"][1] == "liste" and set(kb.FREMDTEXT["nur_lesen"][2]) == {"liste", "zeigen"})
pruef("superhirn.nur_lesend: liste/zeigen/ohne aktion lesend, beraten/wiedervorlage/rueckblick/Liste nicht",
      superhirn.nur_lesend(kb, {"aktion": "liste"}) and superhirn.nur_lesend(kb, {"aktion": "zeigen", "nr": 1}) and
      superhirn.nur_lesend(kb, {}) and not superhirn.nur_lesend(kb, {"aktion": "beraten"}) and
      not superhirn.nur_lesend(kb, {"aktion": "wiedervorlage"}) and not superhirn.nur_lesend(kb, {"aktion": "rueckblick"})
      and not superhirn.nur_lesend(kb, {"aktion": "Liste"}))
pruef("Werkzeugbeschreibung deutsch mit Umlauten", "für" in kb.WERKZEUG["beschreibung"] and
      "Gegenrede" in kb.WERKZEUG["beschreibung"])

# ------------------------------------------------------------------ Beraten: Normalfall
ctx = neu(antworten=antworten())
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir ein E-Auto kaufen?", "kontext": "Budget 30.000 €\x07, Pendeln "
               "40 km.\nZweite Zeile."}, "alex", ctx)
zwecke = sorted(g["zweck"] for g in ctx.gedacht)
pruef("beraten: fünf Denkaufrufe (4 Stimmen + Zusammenfassung)", len(ctx.gedacht) == 5 and r.get("aufrufe") == 5,
      zwecke)
pruef("beraten: zwecke kabinett_<rolle> und kabinett_synthese", zwecke == sorted(
    ["kabinett_sparfuchs", "kabinett_familie", "kabinett_zukunft", "kabinett_advocatus", "kabinett_synthese"]), zwecke)
pruef("beraten: alle Stufe normal, ohne Werkzeuge", all(g["stufe"] == "normal" and g["werkzeuge"] == ()
                                                         for g in ctx.gedacht))
# Nachpruefung vor 0.7 (Punkt 2): jede Stimme reserviert nur die kleine Stufe, damit vier gleichzeitige plus
# Synthese nicht die vollen 2 $ belegen und das Kabinett auch nachmittags noch mit vier Stimmen antwortet.
import denken as _dk  # noqa: E402
pruef("beraten: Stimmen und Synthese mit kleiner Reservierung (%.2f $), fuenf zusammen unter dem Tageslimit"
      % kb.STIMME_RESERVE_USD,
      all(g["reserve_usd"] == kb.STIMME_RESERVE_USD for g in ctx.gedacht)
      and 5 * kb.STIMME_RESERVE_USD < _dk.TAGESLIMIT_USD and kb.STIMME_RESERVE_USD < _dk.RESERVE_USD["normal"],
      [g["reserve_usd"] for g in ctx.gedacht])
pruef("Meldung: Empfehlung, stärkste Gegenrede, Sicherheit", "Das Kabinett rät: Noch ein halbes Jahr warten" in
      r["meldung"] and "Stärkste Gegenrede: Das alte Auto kann jederzeit ausfallen." in r["meldung"] and
      "Sicherheit: 72 von 100." in r["meldung"], r["meldung"])
pruef("Meldung kurz und ohne Protokoll-Einzelheiten", len(r["meldung"]) < 400 and "Grund A" not in r["meldung"],
      r["meldung"])
pruef("Meldung ohne 'Nicht dabei', wenn alle vier beraten haben", "Nicht dabei" not in r["meldung"])
pruef("Protokoll vollständig: alle vier Stimmen und Zusammenfassung", all(x in r["protokoll"] for x in (
    "Sparfuchs", "Familie & Alltag", "Zukunft", "Advocatus diaboli", "Begründung", "Offene Frage", "greift an")),
    r["protokoll"][:300])
pruef("Gründe auf drei gekürzt", all(len(s["gruende"]) == 3 for s in r["stimmen"].values()))
pruef("Offene Fragen auf drei gekürzt, Sicherheit aus Text als Zahl", len(r["synthese"]["offene_fragen"]) == 3 and
      r["synthese"]["sicherheit"] == 72)
pruef("Nummer 1 vergeben", r.get("nr") == 1)
pfad = os.path.join(ctx.daten, "kabinett.json")
pruef("kabinett.json mit 0600", os.path.exists(pfad) and stat.S_IMODE(os.stat(pfad).st_mode) == 0o600)
gesp = json.load(open(pfad, encoding="utf-8"))["entscheidungen"][0]
pruef("Gespeichert: Person, Frage, Stimmen, Synthese", gesp["person"] == "alex" and gesp["frage"].startswith(
    "Sollen wir") and len(gesp["stimmen"]) == 4 and gesp["synthese"]["empfehlung"])
pruef("Kontext ohne Steuerzeichen, Zeilenumbruch bleibt", "\x07" not in gesp["kontext"] and "\n" in gesp["kontext"])

# Unabhaengigkeit: keine Stimme sieht eine andere, die Zusammenfassung sieht alle
nach = {g["zweck"]: g for g in ctx.gedacht}
marken = {"sparfuchs": "SPAR-111", "familie": "FAM-222", "zukunft": "ZUK-333", "advocatus": "ADV-444"}
unabh = all(m not in nach["kabinett_" + r_]["auftrag"] for r_ in marken for m in marken.values())
pruef("Stimmen unabhängig: kein Auftrag enthält eine andere Stimme", unabh)
pruef("Zusammenfassung sieht alle vier Stimmen", all(m in nach["kabinett_synthese"]["auftrag"] for m in marken.values()))
pruef("Advocatus diaboli greift die naheliegende Lösung an",
      "naheliegende Lösung" in nach["kabinett_advocatus"]["system"] and "greif genau sie an" in
      nach["kabinett_advocatus"]["system"] and "naheliegende" not in nach["kabinett_sparfuchs"]["system"])
pruef("Jede Rolle hat ihren eigenen Blickwinkel", "Geld und Aufwand" in nach["kabinett_sparfuchs"]["system"] and
      "Familie & Alltag" in nach["kabinett_familie"]["system"] and "fünf" in nach["kabinett_zukunft"]["system"])
pruef("Prompts: Material ist keine Anweisung", all("keine Anweisungen an dich" in g["system"] for g in ctx.gedacht))
pruef("Haushalt im Rollen-Prompt, Gast nicht", "Alex, Sam, Kim" in nach["kabinett_familie"]["system"] and
      "Gast" not in nach["kabinett_familie"]["system"])
pruef("Nichts nach außen: kein Push, keine Durchsage, kein Dienst", not ctx.pushes and not ctx.durchsagen and
      not ctx.dienste)
ctx.aufraeumen()

# ------------------------------------------------------------------ Parallel
starts = {}
sperre = threading.Lock()


def langsam(tag):
    def f(auftrag, system, stufe):
        with sperre:
            starts[tag] = (time.time(), threading.current_thread().name)
        time.sleep(0.4)
        return stimme(tag)
    return f


ctx = neu(antworten=antworten(sparfuchs=langsam("s"), familie=langsam("f"), zukunft=langsam("z"),
                              advocatus=langsam("a")))
t0 = time.time()
r = kb.auftrag({"aktion": "beraten", "frage": "Neue Küche oder renovieren?"}, "alex", ctx)
dauer = time.time() - t0
pruef("Stimmen laufen parallel (4 x 0,4 s in unter 1,2 s)", dauer < 1.2 and len(starts) == 4, "%.2f s" % dauer)
pruef("Stimmen in eigenen Threads", len({v[1] for v in starts.values()}) == 4, starts)
pruef("Parallel: Zusammenfassung erst nach allen Stimmen", ctx.gedacht[-1]["zweck"] == "kabinett_synthese")
ctx.aufraeumen()


def haengt(auftrag, system, stufe):
    time.sleep(1.5)
    return stimme("SPAET")


alt_frist = kb.STIMME_WARTEN_S
kb.STIMME_WARTEN_S = 0.5
ctx = neu(antworten=antworten(familie=haengt, zukunft=haengt))
t0 = time.time()
r = kb.auftrag({"aktion": "beraten", "frage": "Neue Küche oder renovieren?"}, "alex", ctx)
dauer = time.time() - t0
kb.STIMME_WARTEN_S = alt_frist
pruef("Gemeinsame Frist: zwei hängende Stimmen kosten sie nur einmal", dauer < 1.2 and set(r["stimmen"]) ==
      {"sparfuchs", "advocatus"} and "keine Antwort in der Zeit" in r["meldung"], ("%.2f s" % dauer, r["meldung"]))
time.sleep(1.2)                                   # spaete Threads auslaufen lassen, bevor der Ordner weg ist
ctx.aufraeumen()

# ------------------------------------------------------------------ Kaputtes JSON, fehlende Rolle
ctx = neu(antworten=antworten(zukunft="Ich denke, das ist eine gute Idee, aber ohne JSON."))
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir einen Hund holen?"}, "alex", ctx)
pruef("Kaputtes JSON: Zukunft fehlt, Rest berät weiter", "zukunft" not in r["stimmen"] and len(r["stimmen"]) == 3 and
      r["synthese"] is not None, r.get("fehlend"))
pruef("Kaputtes JSON: Meldung sagt es ehrlich", "3 von 4 Stimmen" in r["meldung"] and "Nicht dabei: Zukunft" in
      r["meldung"] and "keine lesbare Antwort" in r["meldung"], r["meldung"])
syn_auftrag = [g for g in ctx.gedacht if g["zweck"] == "kabinett_synthese"][0]["auftrag"]
pruef("Kaputtes JSON: Zusammenfassung weiß vom Ausfall", "Ausgefallen sind: Zukunft" in syn_auftrag)
pruef("Kaputtes JSON: höchstens 5 Aufrufe", len(ctx.gedacht) == 5)
ctx.aufraeumen()

ctx = neu(antworten=antworten(familie=None))            # Attrappe wirft AssertionError: Stimme fehlt
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir umziehen?"}, "alex", ctx)
pruef("Fehlende Rolle (Fehler): Familie fehlt, Meldung nennt sie", "familie" not in r["stimmen"] and
      "Nicht dabei: Familie & Alltag (Fehler beim Nachdenken)" in r["meldung"], r["meldung"])
pruef("Fehlende Rolle: Fehler ins Log", any("kabinett_familie ausgefallen" in z for z in ctx.logs), ctx.logs)
ctx.aufraeumen()

ctx = neu(antworten=antworten(sparfuchs='{"falsch": 1}', zukunft='["liste", "statt", "objekt"]'))
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir die Heizung tauschen?"}, "alex", ctx)
pruef("JSON ohne Haltung/Empfehlung oder als Liste zählt als fehlend", set(r["stimmen"]) == {"familie", "advocatus"} and
      "keine verwertbare Antwort" in r["meldung"], r["meldung"])
ctx.aufraeumen()

ctx = neu(antworten=antworten(synthese="kaputt {"))
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir in den Urlaub fliegen?"}, "alex", ctx)
pruef("Zusammenfassung kaputt: Stimmen einzeln, ehrlich", r["synthese"] is None and "Zusammenfassung ist ausgefallen"
      in r["meldung"] and "Sparfuchs: Empfehlung SPAR-111." in r["meldung"] and "Protokoll Nummer 1" in r["meldung"],
      r["meldung"])
pruef("Zusammenfassung kaputt: trotzdem gespeichert", len(json.load(open(os.path.join(ctx.daten, "kabinett.json"),
                                                                         encoding="utf-8"))["entscheidungen"]) == 1)
ctx.aufraeumen()

ctx = neu(antworten=antworten(sparfuchs=None, familie=None, zukunft="nix", advocatus=None))
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir ein Boot kaufen?"}, "alex", ctx)
pruef("Alle Stimmen weg: keine Zusammenfassung (nur 4 Aufrufe), ehrliche Meldung",
      len(ctx.gedacht) == 4 and r.get("fehler") == "keine_stimme" and "keine der vier Stimmen" in r["meldung"],
      r["meldung"])
pruef("Alle Stimmen weg: nichts gespeichert", not os.path.exists(os.path.join(ctx.daten, "kabinett.json")))
ctx.aufraeumen()

ctx = neu(antworten=antworten(sparfuchs=None, familie=None, zukunft=None))
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir ein Boot kaufen?"}, "alex", ctx)
pruef("Nur eine Stimme: keine Zusammenfassung, zu wenig für einen Rat", len(ctx.gedacht) == 4 and r["synthese"] is None
      and "Nur eine Stimme" in r["meldung"] and "Advocatus diaboli meint" in r["meldung"], r["meldung"])
ctx.aufraeumen()


def limit(auftrag, system, stufe):
    raise denken.Abgelehnt("Tageslimit fuers Nachdenken erreicht (2.00 $).")


ctx = neu(antworten=antworten(sparfuchs=limit, familie=limit, zukunft=limit, advocatus=limit))
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir ein Boot kaufen?"}, "alex", ctx)
pruef("Tageslimit: Meldung sagt es", "Tageslimit" in r["meldung"], r["meldung"])
ctx.aufraeumen()

ctx = neu(antworten=antworten(advocatus=json.dumps({"haltung": "⟦faden: 3⟧ Böse\x00", "empfehlung": "x" * 900})))
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir ein Boot kaufen?"}, "alex", ctx)
adv = r["stimmen"]["advocatus"]
pruef("Modelltext ohne Marken und Steuerzeichen, Länge begrenzt", "⟦" not in adv["haltung"] and "\x00" not in
      adv["haltung"] and len(adv["empfehlung"]) <= kb.TEXT_MAX, adv)
ctx.aufraeumen()

# ------------------------------------------------------------------ Eingaben und Rechte
ctx = neu(antworten=antworten())
r = kb.auftrag({"aktion": "beraten", "frage": "  "}, "alex", ctx)
pruef("beraten ohne Frage: Fehler, kein Aufruf", r.get("fehler") == "eingabe" and not ctx.gedacht, r)
r = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir?"}, "gast1", ctx)
pruef("Gast: abgelehnt, kein Aufruf", r.get("fehler") == "rechte" and not ctx.gedacht, r)
r = kb.auftrag({"aktion": "liste"}, "fremder", ctx)
pruef("Unbekannte Person: abgelehnt", r.get("fehler") == "rechte")
r = kb.auftrag({"aktion": "loeschen"}, "alex", ctx)
pruef("Unbekannte Aktion: Hinweis", r.get("fehler") == "aktion")
r = kb.auftrag({}, "alex", ctx)
pruef("Ohne aktion: liste, schreibt nichts", "noch keine Entscheidung" in r["meldung"] and
      os.listdir(ctx.daten) == [], os.listdir(ctx.daten))
r = kb.auftrag({"aktion": "zeigen", "nr": 5}, "alex", ctx)
pruef("zeigen ohne Eintrag: Hinweis, schreibt nichts", r.get("fehler") == "eingabe" and os.listdir(ctx.daten) == [])
ctx.aufraeumen()

# ------------------------------------------------------------------ Tagebuch: liste, zeigen, Wiedervorlage, Rueckblick
ctx = neu(antworten={k: [v] * 20 for k, v in antworten().items()})
r1 = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir ein E-Auto kaufen?"}, "alex", ctx)
r2 = kb.auftrag({"aktion": "beraten", "frage": "Soll Kim ein eigenes Handy bekommen?"}, "sam", ctx)
pruef("Zwei Personen: Nummern 1 und 2", r1["nr"] == 1 and r2["nr"] == 2)
li_p = kb.auftrag({"aktion": "liste"}, "alex", ctx)
li_b = kb.auftrag({"aktion": "liste"}, "sam", ctx)
pruef("liste je Person getrennt", "E-Auto" in li_p["meldung"] and "Handy" not in li_p["meldung"] and
      "Handy" in li_b["meldung"] and "E-Auto" not in li_b["meldung"])
pruef("liste: Nummer und Rat", "Nr. 1 vom 06.11.2026" in li_p["meldung"] and "Rat: Noch ein halbes Jahr" in
      li_p["meldung"], li_p["meldung"])
z = kb.auftrag({"aktion": "zeigen", "nr": 1}, "alex", ctx)
pruef("zeigen: volles Protokoll mit deutschem Datum", "Kabinett Nr. 1 vom 06.11.2026 20:00" in z["meldung"] and
      "Advocatus diaboli" in z["meldung"], z["meldung"][:80])
z = kb.auftrag({"aktion": "zeigen", "nr": 1}, "sam", ctx)
pruef("zeigen: fremde Nummer gibt es nicht", z.get("fehler") == "eingabe" and "E-Auto" not in z["meldung"])
for w in (0, 27, "abc", True, None, 2.5):
    rr = kb.auftrag({"aktion": "wiedervorlage", "nr": 1, "wochen": w}, "alex", ctx)
    pruef("wiedervorlage wochen=%r abgelehnt" % (w,), rr.get("fehler") == "eingabe", rr)
rr = kb.auftrag({"aktion": "wiedervorlage", "nr": 1, "wochen": 4}, "sam", ctx)
pruef("wiedervorlage fremder Nummer abgelehnt", rr.get("fehler") == "eingabe")
rr = kb.auftrag({"aktion": "wiedervorlage", "nr": "1", "wochen": "4", "entscheidung": "Wir kaufen den gebrauchten "
                 "ID.3"}, "alex", ctx)
pruef("wiedervorlage: Termin in 4 Wochen", rr.get("termin") == "2026-12-04" and "04.12.2026" in rr["meldung"], rr)
rr = kb.auftrag({"aktion": "wiedervorlage", "nr": 2, "wochen": 1}, "sam", ctx)
pruef("wiedervorlage ohne Entscheidung (Sam, 1 Woche)", rr.get("termin") == "2026-11-13")

ctx._jetzt = zeit(2026, 12, 3, 12, 0)
kb.runde(ctx)
pp = [p for p in ctx.pushes if p["person"] == "alex"]
pb = [p for p in ctx.pushes if p["person"] == "sam"]
pruef("runde vor Alex' Termin: kein Push an Alex", not pp, pp)
pruef("Sam (Termin 13.11. längst fällig) bekommt ihren eigenen Push, ohne Alex' Inhalt", len(pb) == 1 and
      "Vor einer Woche hat das Kabinett mit dir über „Soll Kim ein eigenes Handy bekommen?“ beraten (Rat: " in
      pb[0]["text"] and "Wie hast du entschieden, und wie hat es sich bewährt?" in
      pb[0]["text"] and "ID.3" not in pb[0]["text"], pb)
ctx.pushes.clear()
ctx._jetzt = zeit(2026, 12, 4, 9, 30)
kb.runde(ctx)
pruef("runde am Termin, aber vor 10 Uhr: kein Push", not ctx.pushes, ctx.pushes)
ctx._jetzt = zeit(2026, 12, 4, 10, 15)
kb.runde(ctx)
pp = [p for p in ctx.pushes if p["person"] == "alex"]
pruef("runde am Termin um 10:15: genau ein Push, an Alex, mit Text", len(ctx.pushes) == 1 and len(pp) == 1 and
      pp[0]["text"].startswith("Vor 4 Wochen hast du entschieden: Wir kaufen den gebrauchten ID.3. Wie hat es sich "
                               "bewährt?") and pp[0]["tag"] == "jarvis-kabinett", ctx.pushes)
ctx.pushes.clear()
kb.runde(ctx)
ctx._jetzt = zeit(2026, 12, 5, 11, 0)
kb.runde(ctx)
pruef("Wiedervorlage nur einmal", not ctx.pushes, ctx.pushes)

# Rueckblick als Lernerfahrung
rb = kb.auftrag({"aktion": "rueckblick", "nr": 1, "text": "Hat sich bewährt, Ladekosten LERN-999 niedriger als "
                 "gedacht."}, "alex", ctx)
pruef("rueckblick gespeichert", rb.get("nr") == 1 and "gespeichert" in rb["meldung"])
pruef("rueckblick fremder Nummer abgelehnt", kb.auftrag({"aktion": "rueckblick", "nr": 1, "text": "Quatsch"}, "sam",
                                                       ctx).get("fehler") == "eingabe")
pruef("rueckblick ohne Text abgelehnt", kb.auftrag({"aktion": "rueckblick", "nr": 1, "text": ""}, "alex",
                                                  ctx).get("fehler") == "eingabe")
n0 = len(ctx.gedacht)
r3 = kb.auftrag({"aktion": "beraten", "frage": "Sollen wir eine Wallbox kaufen?"}, "alex", ctx)
neu_g = ctx.gedacht[n0:]
pruef("Lernerfahrung fließt in alle Stimmen der neuen Beratung ein", all("LERN-999" in g["auftrag"] for g in neu_g) and
      all("Frühere Entscheidungen von Alex" in g["auftrag"] for g in neu_g) and r3["lernerfahrungen"] == [1])
n0 = len(ctx.gedacht)
kb.auftrag({"aktion": "beraten", "frage": "Soll Kim Klavierunterricht nehmen?"}, "sam", ctx)
pruef("Lernerfahrung je Person getrennt (Sam sieht Alex' Rückblick nicht)",
      not any("LERN-999" in g["auftrag"] for g in ctx.gedacht[n0:]))
ctx.aufraeumen()

ctx = neu(antworten={k: [v] * 40 for k, v in antworten().items()})
for i in range(7):
    kb.auftrag({"aktion": "beraten", "frage": "Entscheidung Nummer %d?" % (i + 1)}, "alex", ctx)
    ctx._jetzt += 60
    kb.auftrag({"aktion": "rueckblick", "nr": i + 1, "text": "Rückblick RB-%d" % (i + 1)}, "alex", ctx)
n0 = len(ctx.gedacht)
kb.auftrag({"aktion": "beraten", "frage": "Neue Entscheidung?"}, "alex", ctx)
a = ctx.gedacht[n0]["auftrag"]
pruef("Höchstens 5 Lernerfahrungen, die neuesten", all("RB-%d" % i in a for i in range(3, 8)) and "RB-1“" not in a and
      "RB-2“" not in a, a[:600])
ctx.aufraeumen()

# Rueckblick vor dem Termin: keine Nachfrage mehr
ctx = neu(antworten=antworten())
kb.auftrag({"aktion": "beraten", "frage": "Sollen wir ein E-Auto kaufen?"}, "alex", ctx)
kb.auftrag({"aktion": "wiedervorlage", "nr": 1, "wochen": 2}, "alex", ctx)
kb.auftrag({"aktion": "rueckblick", "nr": 1, "text": "Schon jetzt klar: gut."}, "alex", ctx)
ctx._jetzt = zeit(2026, 11, 20, 12, 0)
kb.runde(ctx)
pruef("Rückblick vor dem Termin: keine Nachfrage", not ctx.pushes)
pruef("liste zeigt 'mit Rückblick'", "mit Rückblick" in kb.auftrag({"aktion": "liste"}, "alex", ctx)["meldung"])
ctx.aufraeumen()

# Push schlaegt fehl: erneut versuchen, nach FEHLVERSUCHE_MAX aufgeben
ctx = neu(antworten=antworten())
kb.auftrag({"aktion": "beraten", "frage": "Sollen wir ein E-Auto kaufen?"}, "alex", ctx)
kb.auftrag({"aktion": "wiedervorlage", "nr": 1, "wochen": 1}, "alex", ctx)
ctx.push = lambda *a, **k: False
ctx._jetzt = zeit(2026, 11, 13, 12, 0)
for _ in range(kb.FEHLVERSUCHE_MAX + 2):
    kb.runde(ctx)
wv = json.load(open(os.path.join(ctx.daten, "kabinett.json"), encoding="utf-8"))["entscheidungen"][0]["wiedervorlage"]
pruef("Push scheitert: nach %d Versuchen aufgegeben" % kb.FEHLVERSUCHE_MAX, wv["status"] == "fehlgeschlagen" and
      wv["fehlversuche"] == kb.FEHLVERSUCHE_MAX, wv)


def wirft(*a, **k):
    raise RuntimeError("HA weg")


ctx.push = wirft
kb.auftrag({"aktion": "wiedervorlage", "nr": 1, "wochen": 1}, "alex", ctx)
ctx._jetzt = zeit(2026, 11, 20, 12, 0)
try:
    kb.runde(ctx)
    ok = True
except Exception as e:  # noqa: BLE001
    ok = repr(e)
pruef("runde wirft nicht, wenn der Push wirft", ok is True, ok)
ctx.aufraeumen()

# runde robust
ctx = neu()
open(os.path.join(ctx.daten, "kabinett.json"), "w").write("{kaputt")
ctx._jetzt = zeit(2026, 11, 13, 12, 0)
try:
    kb.runde(ctx)
    ctx.personen = wirft
    kb.runde(ctx)
    ok = True
except Exception as e:  # noqa: BLE001
    ok = repr(e)
pruef("runde wirft nie (kaputte Datei, Personen weg)", ok is True, ok)
pruef("runde: Fehler ins Log", any("runde fehlgeschlagen" in z for z in ctx.logs), ctx.logs)
ctx.aufraeumen()

# Gast als frueherer Eigentuemer: kein Push
ctx = neu(antworten=antworten())
kb.auftrag({"aktion": "beraten", "frage": "Sollen wir ein E-Auto kaufen?"}, "kim", ctx)
kb.auftrag({"aktion": "wiedervorlage", "nr": 1, "wochen": 1}, "kim", ctx)
ctx._personen = {"alex": {"name": "Alex", "rolle": "haupt"}, "kim": {"name": "Kim", "rolle": "gast"}}
ctx._jetzt = zeit(2026, 11, 13, 12, 0)
kb.runde(ctx)
pruef("Wiedervorlage nie an einen Gast", not ctx.pushes)
ctx.aufraeumen()

# ------------------------------------------------------------------ Lautsprecher-Sperre (seit 0.7)
pruef("LAUTSPRECHER_PRIVAT: genau liste und zeigen, als frozenset",
      isinstance(kb.LAUTSPRECHER_PRIVAT, frozenset) and kb.LAUTSPRECHER_PRIVAT == frozenset({"liste", "zeigen"}))
pruef("LAUTSPRECHER_PRIVAT: nur Aktionen aus dem Schema, alle lesend, Standardaktion inbegriffen",
      kb.LAUTSPRECHER_PRIVAT <= set(kb.WERKZEUG["schema"]["properties"]["aktion"]["enum"])
      and kb.LAUTSPRECHER_PRIVAT <= superhirn.lesende_aktionen(kb)[2]
      and superhirn.lesende_aktionen(kb)[1] in kb.LAUTSPRECHER_PRIVAT)

# ------------------------------------------------------------------ Englisch (seit 0.7)
DEUTSCH = re.compile(r"[äöüÄÖÜß„]|\b(?:ist|nicht|Bitte|bitte|und|oder|der|die|das|dich|mit|vom|Nr|Kabinett|Stimme|"
                     r"Stimmen|Sicherheit|Protokoll|Rückblick|Wochen)\b")


def deutsch(text):
    return DEUTSCH.findall(str(text))


try:
    kb.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", kb.SPRACHE == "de")


def stimme_en(tag):
    return json.dumps({"haltung": "Position %s" % tag, "gruende": ["Reason A %s" % tag, "Reason B"],
                       "risiko": "Risk %s" % tag, "empfehlung": "Recommendation %s" % tag,
                       "angegriffen": "Buy right away"})


SYN_EN = json.dumps({"empfehlung": "Wait half a year and then buy used", "begruendung": "Because prices are falling.",
                     "staerkste_gegenrede": "The old car could break down at any time",
                     "offene_fragen": ["How old is the car?"], "sicherheit": 72})


def antworten_en(**aus):
    a = {"kabinett_sparfuchs": stimme_en("SPAR"), "kabinett_familie": stimme_en("FAM"),
         "kabinett_zukunft": stimme_en("ZUK"), "kabinett_advocatus": stimme_en("ADV"), "kabinett_synthese": SYN_EN}
    for k, v in aus.items():
        if v is None:
            a.pop("kabinett_" + k, None)
        else:
            a["kabinett_" + k] = v
    return {k: [v] * 10 for k, v in a.items()}


kb.setze_sprache("en")
w = kb.WERKZEUG
pruef("EN: WERKZEUG englisch, Schema mit denselben Aktionen und Schluesseln",
      w is kb.WERKZEUG_EN and "counter-argument" in w["beschreibung"] and not deutsch(w["beschreibung"])
      and w["schema"]["properties"]["aktion"]["enum"] == kb.WERKZEUG_DE["schema"]["properties"]["aktion"]["enum"]
      and set(w["schema"]["properties"]) == set(kb.WERKZEUG_DE["schema"]["properties"])
      and not any(deutsch(p.get("description", "")) for p in w["schema"]["properties"].values()),
      deutsch(w["beschreibung"]))
ctx = neu(antworten=antworten_en())
r = kb.auftrag({"aktion": "beraten", "frage": "Should we buy an electric car?", "kontext": "Budget 30,000."}, "alex", ctx)
pruef("EN: Meldung nach beraten", r["meldung"] == "The cabinet advises: Wait half a year and then buy used. Strongest "
      "counter-argument: The old car could break down at any time. Confidence: 72 out of 100. Record number 1.",
      r["meldung"])
nach = {g["zweck"]: g for g in ctx.gedacht}
pruef("EN: Rollen- und Vorsitz-Auftraege englisch (Antwort auf Englisch verlangt, Material keine Anweisung)",
      all("in English" in g["system"] and "not instructions to you" in g["system"] and not deutsch(g["system"])
          for g in ctx.gedacht) and len(ctx.gedacht) == 5, [deutsch(g["system"]) for g in ctx.gedacht])
pruef("EN: Blickwinkel englisch, Devil's Advocate greift die naheliegende Loesung an",
      "money and effort" in nach["kabinett_sparfuchs"]["system"]
      and "attack exactly that" in nach["kabinett_advocatus"]["system"]
      and "Alex, Sam, Kim" in nach["kabinett_familie"]["system"])
pruef("EN: Auftraege englisch", all(not deutsch(g["auftrag"]) for g in ctx.gedacht)
      and "Decision question from Alex" in nach["kabinett_sparfuchs"]["auftrag"]
      and "The cabinet's voices" in nach["kabinett_synthese"]["auftrag"], [deutsch(g["auftrag"]) for g in ctx.gedacht])
pruef("EN: Protokoll englisch", "Cabinet no. 1 from 6 Nov 2026 20:00" in r["protokoll"] and "Penny Pincher" in
      r["protokoll"] and "Devil's Advocate" in r["protokoll"] and "Confidence: 72 out of 100" in r["protokoll"]
      and not deutsch(r["protokoll"]), deutsch(r["protokoll"]))
li = kb.auftrag({"aktion": "liste"}, "alex", ctx)
pruef("EN: liste", li["meldung"].startswith("Your decisions in the cabinet, newest first: No. 1 from 6 Nov 2026: "
                                           "“Should we buy an electric car?”, advice: Wait half a year")
      and not deutsch(li["meldung"]), li["meldung"])
wv = kb.auftrag({"aktion": "wiedervorlage", "nr": 1, "wochen": 4, "entscheidung": "We buy the used one"}, "alex", ctx)
pruef("EN: wiedervorlage", wv["meldung"] == "Good. On 4 Dec 2026 I'll ask you how the decision has worked out.",
      wv["meldung"])
r2 = kb.auftrag({"aktion": "beraten", "frage": "Should Kim get her own phone?"}, "sam", ctx)
kb.auftrag({"aktion": "wiedervorlage", "nr": r2["nr"], "wochen": 1}, "sam", ctx)
ctx._jetzt = zeit(2026, 12, 4, 10, 15)
kb.runde(ctx)
pa = [p for p in ctx.pushes if p["person"] == "alex"]
ps = [p for p in ctx.pushes if p["person"] == "sam"]
pruef("EN: Push mit Entscheidung", len(pa) == 1 and pa[0]["titel"] == "Jarvis: How has your decision worked out?"
      and pa[0]["text"] == "4 weeks ago you decided: We buy the used one. How has it worked out? Just tell me, I'll "
      "remember it for future deliberations (cabinet number 1).", pa)
pruef("EN: Push ohne Entscheidung fragt mit", len(ps) == 1 and ps[0]["text"].startswith(
    "A week ago the cabinet discussed “Should Kim get her own phone?” with you (advice: Wait half a year and then "
    "buy used). What did you decide, and how has it worked out?") and not deutsch(ps[0]["text"]), ps)
rb = kb.auftrag({"aktion": "rueckblick", "nr": 1, "text": "Worked out well, charging LEARN-7 cheaper."}, "alex", ctx)
pruef("EN: rueckblick", rb["meldung"] == "Thanks, I've saved your review of number 1. The cabinet will keep it in mind "
      "in your next deliberations.", rb["meldung"])
n0 = len(ctx.gedacht)
kb.auftrag({"aktion": "beraten", "frage": "Should we buy a wallbox?"}, "alex", ctx)
pruef("EN: Lernerfahrung englisch", all("Earlier decisions by Alex" in g["auftrag"] and "LEARN-7" in g["auftrag"]
                                        and "Review by Alex" in g["auftrag"] and not deutsch(g["auftrag"])
                                        for g in ctx.gedacht[n0:]), ctx.gedacht[n0]["auftrag"][:400])
fehler_en = [kb.auftrag({"aktion": "liste"}, "gast1", ctx), kb.auftrag({"aktion": "loeschen"}, "alex", ctx),
             kb.auftrag({"aktion": "zeigen"}, "alex", ctx), kb.auftrag({"aktion": "zeigen", "nr": 99}, "alex", ctx),
             kb.auftrag({"aktion": "wiedervorlage", "nr": 1, "wochen": 30}, "alex", ctx),
             kb.auftrag({"aktion": "rueckblick", "nr": 1, "text": ""}, "alex", ctx),
             kb.auftrag({"aktion": "beraten", "frage": ""}, "alex", ctx), kb.auftrag({}, "kim", ctx)]
pruef("EN: Fehlermeldungen und leere Liste englisch", all(m.get("meldung") and not deutsch(m["meldung"])
                                                         for m in fehler_en)
      and fehler_en[0]["meldung"] == "The cabinet only advises members of the household."
      and fehler_en[7]["meldung"] == "You haven't discussed any decision with the cabinet yet.",
      [m["meldung"] for m in fehler_en])
ctx.aufraeumen()
ctx = neu(antworten=antworten_en(zukunft="no JSON here, sorry"))
r = kb.auftrag({"aktion": "beraten", "frage": "Should we get a dog?"}, "alex", ctx)
pruef("EN: ausgefallene Stimme ehrlich gemeldet", "3 of 4 voices took part. Missing: Future (no readable answer)."
      in r["meldung"] and not deutsch(r["meldung"]), r["meldung"])
syn = [g for g in ctx.gedacht if g["zweck"] == "kabinett_synthese"][0]["auftrag"]
pruef("EN: Vorsitz erfaehrt den Ausfall", "Dropped out: Future." in syn, syn[-300:])
ctx.aufraeumen()
ctx = neu(antworten=antworten_en(synthese="broken {"))
r = kb.auftrag({"aktion": "beraten", "frage": "Should we fly on holiday?"}, "alex", ctx)
pruef("EN: Zusammenfassung ausgefallen", r["meldung"].startswith("The summary failed, here are the voices one by one: "
                                                                "Penny Pincher: Recommendation SPAR.")
      and not deutsch(r["meldung"]), r["meldung"])
ctx.aufraeumen()
ctx = neu(antworten=antworten_en(sparfuchs=None, familie=None, zukunft=None))
r = kb.auftrag({"aktion": "beraten", "frage": "Should we buy a boat?"}, "alex", ctx)
pruef("EN: nur eine Stimme", r["meldung"].startswith("Only one voice answered, too few for a council. Devil's Advocate "
                                                    "thinks: Recommendation ADV.") and not deutsch(r["meldung"]),
      r["meldung"])
ctx.aufraeumen()
ctx = neu(antworten={k: limit for k in antworten_en()})
r = kb.auftrag({"aktion": "beraten", "frage": "Should we buy a boat?"}, "alex", ctx)
pruef("EN: Tageslimit erkannt und gemeldet", r.get("fehler") == "keine_stimme" and "(daily limit for thinking reached)"
      in r["meldung"] and not deutsch(r["meldung"]), r["meldung"])
ctx.aufraeumen()
kb.setze_sprache("de")
pruef("Zurueck auf Deutsch: WERKZEUG, Rollen, Vorsitz", kb.WERKZEUG is kb.WERKZEUG_DE and kb.ROLLEN is kb.ROLLEN_DE
      and kb.SYSTEM_SYNTHESE is kb.SYSTEM_SYNTHESE_DE and kb.ROLLEN_NAMEN["advocatus"] == "Advocatus diaboli"
      and kb._datum_text("2026-11-06") == "06.11.2026")

# ------------------------------------------------------------------ Python 3.8 und Live-Daten
pruef("Läuft unter Python 3.8 oder neuer", sys.version_info[:2] >= (3, 8), sys.version)
pruef("Live-Daten unverändert", wache(("kabinett.json", "kabinett.lock")))
sys.exit(ergebnis("Kabinett"))
