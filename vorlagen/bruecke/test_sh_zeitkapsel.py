#!/usr/bin/env python3
"""Tests S10 Zeitkapsel (bruecke/zeitkapsel.py, seit 0.7) mit der Attrappe: ohne Netz, ohne Claude, ohne Home
Assistant, ohne Live-Daten. Zeit über ctx._jetzt (Ortszeit des Rechners). Seit 0.7 zusätzlich: Lautsprecher-Sperre
(LAUTSPRECHER_PRIVAT) und alle Meldungen, Durchsagen, Pushes und die Werkzeugbeschreibung auf Englisch.

    python3 -B tests/test_sh_zeitkapsel.py
"""
import datetime as dt
import json
import os
import re
import stat
import sys
import threading
import time

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "..", "bruecke"))

import sh_attrappe  # noqa: E402

pruef, ergebnis = sh_attrappe.pruefer()
wache = sh_attrappe.live_wache()

import zeitkapsel as zk  # noqa: E402


def ts(j, mo, t, h=12, mi=0):
    """Ortszeit -> Unix-Sekunden."""
    return time.mktime((j, mo, t, h, mi, 0, 0, 0, -1))


T0 = ts(2026, 11, 6, 10)                  # Freitag, 06.11.2026, 10:00
HEUTE = dt.date(2026, 11, 6)
GEHEIM = "Liebe Kim, heute bist du 18. Das Passwort zur Schatzkiste ist Kirschkuchen."
KONTEXTE = []


def kontext(jetzt=T0, klasse=sh_attrappe.Kontext, **kw):
    ctx = klasse(jetzt=jetzt, **kw)
    KONTEXTE.append(ctx)
    return ctx


def neu(ctx, person="alex", **b):
    b.setdefault("aktion", "neu")
    return zk.auftrag(b, person, ctx)


def m(r):
    return r.get("meldung", "")


def fehler(a, heute=HEUTE):
    try:
        zk.faelligkeit(a, heute)
        return None
    except ValueError as e:
        return str(e)


def alles_text(ctx, *antworten):
    return json.dumps([ctx.pushes, ctx.durchsagen, ctx.logs, ctx.gedacht, list(antworten)], ensure_ascii=False)


# ------------------------------------------------------------------------------------------ Fälligkeit, Schaltjahr
pruef("datum ISO", zk.faelligkeit({"datum": "2030-01-01"}, HEUTE) == (dt.date(2030, 1, 1), ""))
pruef("datum TT.MM.JJJJ", zk.faelligkeit({"datum": "01.01.2030"}, HEUTE)[0] == dt.date(2030, 1, 1))
pruef("in_jahren 5", zk.faelligkeit({"in_jahren": 5}, HEUTE) == (dt.date(2031, 11, 6), "5 Jahre nach dem Versiegeln"))
pruef("in_jahren als Text", zk.faelligkeit({"in_jahren": "2"}, HEUTE)[0] == dt.date(2028, 11, 6))
pruef("alter 18", zk.faelligkeit({"alter": 18, "geburtstag": "2012-05-12"}, HEUTE) ==
      (dt.date(2030, 5, 12), "zum 18. Geburtstag"))
pruef("29.02. wird im Nicht-Schaltjahr 01.03.",
      zk.faelligkeit({"alter": 18, "geburtstag": "2012-02-29"}, HEUTE)[0] == dt.date(2030, 3, 1))
pruef("29.02. bleibt im Schaltjahr 29.02.",
      zk.faelligkeit({"alter": 20, "geburtstag": "2012-02-29"}, HEUTE)[0] == dt.date(2032, 2, 29))
pruef("in_jahren 1 vom 29.02. -> 01.03.", zk.faelligkeit({"in_jahren": 1}, dt.date(2028, 2, 29))[0] == dt.date(2029, 3, 1))
pruef("in_jahren 4 vom 29.02. -> 29.02.",
      zk.faelligkeit({"in_jahren": 4}, dt.date(2028, 2, 29))[0] == dt.date(2032, 2, 29))
pruef("29.02. als Datum in einem Nicht-Schaltjahr abgelehnt", "verstehe ich nicht" in (fehler({"datum": "2027-02-29"}) or ""))
pruef("29.02. als Datum im Schaltjahr ok", fehler({"datum": "2028-02-29"}) is None)
pruef("heute abgelehnt", "Zukunft" in (fehler({"datum": "2026-11-06"}) or ""))
pruef("Vergangenheit abgelehnt", "Zukunft" in (fehler({"datum": "2020-01-01"}) or ""))
pruef("morgen ok", fehler({"datum": "2026-11-07"}) is None)
pruef("über 100 Jahre abgelehnt", "100 Jahre" in (fehler({"datum": "2127-01-01"}) or ""))
pruef("Alter schon erreicht", "schon erreicht" in (fehler({"alter": 10, "geburtstag": "2012-05-12"}) or ""))
pruef("Alter ohne Geburtstag", "Geburtstag" in (fehler({"alter": 18}) or ""))
pruef("Geburtstag in der Zukunft", "Zukunft" in (fehler({"alter": 1, "geburtstag": "2027-01-01"}) or ""))
for falsch in (0, 101, "x", 2.5, True, None):
    pruef("in_jahren %r abgelehnt" % (falsch,), fehler({"in_jahren": falsch}) is not None)
pruef("ohne ausloeser", fehler(None) is not None and fehler({}) is not None)
pruef("ausloeser als JSON-Text", zk.faelligkeit('{"in_jahren": 3}', HEUTE)[0] == dt.date(2029, 11, 6))

# ------------------------------------------------------------------------------------------ neu
ctx = kontext()
r = neu(ctx, fuer="Kim", text=GEHEIM, ausloeser={"alter": 18, "geburtstag": "2012-05-12"})
tag = dt.date(2030, 5, 12)
pruef("neu: versiegelt", m(r).startswith("Versiegelt: Zeitkapsel Nr. 1 für Kim"), m(r))
pruef("neu: Datum mit Wochentag und Anlass", "%s, 12. Mai 2030 (zum 18. Geburtstag)" % zk.WOCHENTAGE[tag.weekday()]
      in m(r), m(r))
pruef("neu: Standard beides, Wohnzimmer", "als Durchsage im Raum Wohnzimmer und per Push" in m(r), m(r))
pruef("neu: Text nicht in der Antwort", "Kirschkuchen" not in json.dumps(r, ensure_ascii=False))
pruef("neu: nr 1", r.get("nr") == 1 and r.get("faellig") == "2030-05-12")
datei = os.path.join(ctx.daten, "zeitkapsel", "kapseln.json")
pruef("Datei 0600", stat.S_IMODE(os.stat(datei).st_mode) == 0o600)
pruef("Ordner 0700", stat.S_IMODE(os.stat(os.path.dirname(datei)).st_mode) == 0o700)
pruef("keine .neu-Reste", not any(n.endswith(".neu") for n in os.listdir(os.path.dirname(datei))))
gespeichert = json.load(open(datei, encoding="utf-8"))
pruef("gespeichert: Text liegt lesbar da (ehrlich: keine Verschlüsselung)", gespeichert[0]["text"] == GEHEIM)
pruef("gespeichert: Felder", gespeichert[0]["von"] == "alex" and gespeichert[0]["fuer"] == "kim"
      and gespeichert[0]["status"] == "versiegelt" and gespeichert[0]["kanal"] == "beides")

r = neu(ctx, fuer="kim", text="Überraschung!", ausloeser={"datum": "2027-01-01"}, ueberraschung=True, kanal="push")
pruef("neu: Überraschung angesagt", "Kim sieht vorher nicht, dass es sie gibt" in m(r) and "per Push" in m(r), m(r))
r = neu(ctx, "sam", fuer="mich", text="Notiz an mich", ausloeser={"in_jahren": 1}, kanal="durchsage",
        raum="kueche")
pruef("neu: für mich selbst, Küche", "für dich selbst" in m(r) and "im Raum Küche" in m(r) and "per Push" not in m(r),
      m(r))
r = neu(ctx, fuer="Sam", text="Hallo", ausloeser={"datum": "2027-06-01"}, raum="ueberall")
pruef("neu: überall", "als Durchsage überall" in m(r), m(r))

# Rechte und Eingaben
r = neu(ctx, "gast1", fuer="Kim", text="x", ausloeser={"in_jahren": 1})
pruef("Gast darf nicht anlegen", "nur für die Familie" in m(r), m(r))
pruef("Gast darf nicht lesen", "nur für die Familie" in m(zk.auftrag({"aktion": "liste"}, "gast1", ctx)))
pruef("unbekannte Person darf nicht", "nur für die Familie" in m(zk.auftrag({"aktion": "liste"}, "fremd", ctx)))
r = neu(ctx, fuer="Gast", text="x", ausloeser={"in_jahren": 1})
pruef("Gast nie als Empfänger", "Für wen" in m(r) and "Gast" not in m(r).split("Ich kenne:")[1], m(r))
pruef("unbekannter Empfänger", "Für wen" in m(neu(ctx, fuer="Oma", text="x", ausloeser={"in_jahren": 1})))
pruef("leerer Text", "Was soll" in m(neu(ctx, fuer="Kim", text="  \n ", ausloeser={"in_jahren": 1})))
pruef("zu langer Text", "zu lang" in m(neu(ctx, fuer="Kim", text="a" * 1501, ausloeser={"in_jahren": 1})))
pruef("falscher Kanal", "kanal" in m(neu(ctx, fuer="Kim", text="x", ausloeser={"in_jahren": 1}, kanal="brief")))
pruef("unbekannter Raum", "kenne ich nicht" in m(neu(ctx, fuer="Kim", text="x", ausloeser={"in_jahren": 1},
                                                   raum="dachboden")))
pruef("falscher Auslöser", "Wann" in m(neu(ctx, fuer="Kim", text="x", ausloeser={"morgen": 1})))
pruef("Steuerzeichen entfernt", zk._text_saeubern("a\x00b\x1bc\r\n\n\n\nd") == "abc\n\nd")
anzahl = len(json.load(open(datei, encoding="utf-8")))
pruef("abgelehnte Aufträge legen nichts an", anzahl == 4, anzahl)

# ------------------------------------------------------------------------------------------ liste, archiv (versiegelt)
r = zk.auftrag({"aktion": "liste"}, "alex", ctx)
pruef("liste Alex: Eckdaten", "Nr. 1, für Kim, angelegt am 06.11.2026, öffnet sich am 12.05.2030 (zum 18. "
      "Geburtstag), %d Zeichen" % len(GEHEIM) in m(r), m(r))
pruef("liste Alex: Überraschung markiert", "Nr. 2, für Kim" in m(r) and "Überraschung" in m(r))
pruef("liste Alex: nie der Inhalt", "Kirschkuchen" not in json.dumps(r, ensure_ascii=False)
      and "Überraschung!" not in m(r))
pruef("liste: Metadaten ohne Text", all("text" not in k for k in r["kapseln"]) and len(r["kapseln"]) == 3)
r = zk.auftrag({"aktion": "liste"}, "kim", ctx)
pruef("liste Kim: von Alex, Eckdaten", "Für dich versiegelt (1)" in m(r) and "Nr. 1, von Alex" in m(r), m(r))
pruef("liste Kim: Überraschung unsichtbar", "Nr. 2" not in m(r), m(r))
pruef("liste Kim: kein Inhalt", "Kirschkuchen" not in json.dumps(r, ensure_ascii=False))
r = zk.auftrag({"aktion": "liste"}, "sam", ctx)
pruef("liste Sam: eigene und an sie", "Nr. 3, für dich selbst" in m(r) and "Nr. 4, von Alex" in m(r)
      and "Nr. 1" not in m(r), m(r))
r = zk.auftrag({}, "alex", ctx)
pruef("ohne aktion = liste", "Von dir versiegelt (3)" in m(r), m(r))
pruef("unbekannte aktion", "aktion muss" in m(zk.auftrag({"aktion": "oeffnen"}, "alex", ctx)))
pruef("aktion genau geschrieben", "aktion muss" in m(zk.auftrag({"aktion": "Liste"}, "alex", ctx)))

r = zk.auftrag({"aktion": "archiv", "nr": 1}, "alex", ctx)
pruef("archiv Ersteller vor Fälligkeit: versiegelt", "noch versiegelt" in m(r) and "Kirschkuchen" not in m(r), m(r))
r = zk.auftrag({"aktion": "archiv", "nr": 1}, "kim", ctx)
pruef("archiv Empfänger vor Fälligkeit: versiegelt", "noch versiegelt" in m(r) and "Kirschkuchen" not in m(r), m(r))
pruef("archiv Überraschung für Kim unsichtbar", "finde ich nicht" in m(zk.auftrag({"aktion": "archiv", "nr": 2},
                                                                                   "kim", ctx)))
pruef("archiv Dritte: nicht gefunden", "finde ich nicht" in m(zk.auftrag({"aktion": "archiv", "nr": 1}, "sam", ctx)))
pruef("archiv leer", "noch keine" in m(zk.auftrag({"aktion": "archiv"}, "kim", ctx)))

# ------------------------------------------------------------------------------------------ loeschen
r = zk.auftrag({"aktion": "loeschen", "nr": 1}, "kim", ctx)
pruef("loeschen Empfänger verboten", "Löschen kann nur, wer sie angelegt hat (Alex)" in m(r), m(r))
pruef("loeschen Dritte: nicht gefunden", "finde ich nicht" in m(zk.auftrag({"aktion": "loeschen", "nr": 1}, "sam",
                                                                          ctx)))
pruef("loeschen ohne nr", "Nummer" in m(zk.auftrag({"aktion": "loeschen"}, "alex", ctx)))
r = zk.auftrag({"aktion": "loeschen", "nr": 4}, "alex", ctx)
pruef("loeschen Ersteller", "Nr. 4 für Sam ist gelöscht" in m(r), m(r))
nrn = [k["nr"] for k in json.load(open(datei, encoding="utf-8"))]
pruef("loeschen wirkt, Rest bleibt", nrn == [1, 2, 3], nrn)
pruef("bis hier nirgends der Inhalt", "Kirschkuchen" not in alles_text(ctx))

# ------------------------------------------------------------------------------------------ Grenze 50
ctx50 = kontext()
for i in range(50):
    neu(ctx50, "sam", fuer="Kim", text="Kapsel %d" % i, ausloeser={"in_jahren": 1 + i % 5}, kanal="push")
r = neu(ctx50, "sam", fuer="Kim", text="eine zu viel", ausloeser={"in_jahren": 1}, kanal="push")
pruef("höchstens 50 offene je Person", "50 versiegelte" in m(r), m(r))
r = neu(ctx50, "kim", fuer="Sam", text="meine erste", ausloeser={"in_jahren": 1}, kanal="push")
pruef("Grenze gilt je Person", m(r).startswith("Versiegelt"), m(r))

# ------------------------------------------------------------------------------------------ runde: Fenster, Zustellung
ctx = kontext()
neu(ctx, fuer="Kim", text=GEHEIM, ausloeser={"datum": "2026-11-07"})
zk.runde(ctx)
pruef("runde: noch nicht fällig", not ctx.durchsagen and not ctx.pushes)
for h, mi, was in ((8, 59, "08:59"), (20, 0, "20:00"), (23, 30, "23:30")):
    ctx._jetzt = ts(2026, 11, 7, h, mi)
    zk.runde(ctx)
    pruef("runde: nicht um %s" % was, not ctx.durchsagen and not ctx.pushes)
ctx._jetzt = ts(2026, 11, 8, 3, 0)
zk.runde(ctx)
pruef("runde: nie nachts (03:00 am Folgetag)", not ctx.durchsagen and not ctx.pushes)
ctx._jetzt = ts(2026, 11, 8, 9, 0)
zk.runde(ctx)
pruef("runde: eine Durchsage um 09:00", len(ctx.durchsagen) == 1, ctx.durchsagen)
erwartet = "Eine Zeitkapsel von Alex, versiegelt am 6. November 2026, für Kim. " + GEHEIM
pruef("Durchsage mit Rahmen und Text", ctx.durchsagen and ctx.durchsagen[0]["text"] == erwartet,
      ctx.durchsagen[:1])
pruef("Durchsage ins Wohnzimmer", ctx.durchsagen and ctx.durchsagen[0]["ziel"] == "wohnzimmer")
pruef("ein Push an Kim mit Inhalt", len(ctx.pushes) == 1 and ctx.pushes[0]["person"] == "kim"
      and ctx.pushes[0]["titel"] == "Zeitkapsel von Alex" and GEHEIM in ctx.pushes[0]["text"]
      and "Versiegelt am 6. November 2026" in ctx.pushes[0]["text"] and ctx.pushes[0]["tag"] == "zeitkapsel",
      ctx.pushes)
k = json.load(open(os.path.join(ctx.daten, "zeitkapsel", "kapseln.json"), encoding="utf-8"))[0]
pruef("danach geöffnet", k["status"] == "geoeffnet" and k["geoeffnet_am"] == ts(2026, 11, 8, 9, 0))
zk.runde(ctx)
ctx._jetzt = ts(2026, 11, 9, 10, 0)
zk.runde(ctx)
pruef("nie doppelt", len(ctx.durchsagen) == 1 and len(ctx.pushes) == 1)
pruef("Log ohne Inhalt", "Kirschkuchen" not in json.dumps(ctx.logs, ensure_ascii=False))
r = zk.auftrag({"aktion": "archiv"}, "kim", ctx)
pruef("archiv Empfänger nach dem Öffnen: Inhalt", GEHEIM in m(r) and "versiegelt am 06.11.2026, geöffnet am "
      "08.11.2026" in m(r), m(r))
pruef("archiv Ersteller: Inhalt", GEHEIM in m(zk.auftrag({"aktion": "archiv", "nr": 1}, "alex", ctx)))
pruef("archiv Dritte: nichts", "noch keine" in m(zk.auftrag({"aktion": "archiv"}, "sam", ctx)))
pruef("liste nach dem Öffnen", "Geöffnet im Archiv: 1" in m(zk.auftrag({"aktion": "liste"}, "alex", ctx)))

# Kanäle einzeln, verspätete Zustellung, an sich selbst
ctx = kontext()
neu(ctx, fuer="Kim", text="nur Push", ausloeser={"datum": "2026-11-07"}, kanal="push")
neu(ctx, "sam", fuer="mich", text="nur Ansage", ausloeser={"datum": "2026-11-07"}, kanal="durchsage", raum="flur")
ctx._jetzt = ts(2026, 11, 12, 15, 0)                 # Rechner war ein paar Tage aus: trotzdem zustellen
zk.runde(ctx)
pruef("nur Push: kein Durchsage-Text davon", len(ctx.pushes) == 1 and ctx.pushes[0]["text"].endswith("nur Push"))
pruef("nur Durchsage: in den Flur, an sich selbst", len(ctx.durchsagen) == 1 and ctx.durchsagen[0]["ziel"] == "flur"
      and ctx.durchsagen[0]["text"].startswith("Eine Zeitkapsel von Sam an sich selbst, versiegelt am "
                                                "6. November 2026."), ctx.durchsagen)
pruef("verspätet zugestellt, beide geöffnet", all(k["status"] == "geoeffnet" for k in json.load(
    open(os.path.join(ctx.daten, "zeitkapsel", "kapseln.json"), encoding="utf-8"))))


# Durchsage scheitert (Nachtruhe o. ä.): Push einmal, Durchsage eine Stunde später
class Stumm(sh_attrappe.Kontext):
    def __init__(self, *a, **kw):
        sh_attrappe.Kontext.__init__(self, *a, **kw)
        self.versuche, self.stumm_bis = 0, 1

    def durchsage(self, ziel, text):
        self.versuche += 1
        if self.versuche <= self.stumm_bis:
            return "keiner"
        return sh_attrappe.Kontext.durchsage(self, ziel, text)


ctx = kontext(klasse=Stumm)
neu(ctx, fuer="Kim", text=GEHEIM, ausloeser={"datum": "2026-11-07"})
ctx._jetzt = ts(2026, 11, 7, 10, 0)
zk.runde(ctx)
k = json.load(open(os.path.join(ctx.daten, "zeitkapsel", "kapseln.json"), encoding="utf-8"))[0]
pruef("Durchsage gescheitert: noch versiegelt, Push schon da", k["status"] == "versiegelt" and len(ctx.pushes) == 1
      and not ctx.durchsagen and k["zustellung"]["durchsage"]["ok"] is False)
ctx._jetzt = ts(2026, 11, 7, 10, 30)
zk.runde(ctx)
pruef("vor Ablauf der Stunde kein neuer Versuch", ctx.versuche == 1)
ctx._jetzt = ts(2026, 11, 7, 11, 1)
zk.runde(ctx)
k = json.load(open(os.path.join(ctx.daten, "zeitkapsel", "kapseln.json"), encoding="utf-8"))[0]
pruef("zweiter Versuch: Durchsage da, Push nicht wiederholt", len(ctx.durchsagen) == 1 and len(ctx.pushes) == 1
      and k["status"] == "geoeffnet", (ctx.versuche, len(ctx.pushes), k["status"]))

# Absturz mitten in der Zustellung (Vermerk „begonnen“ ohne Ergebnis): gilt als zugestellt, nie doppelt
ctx = kontext()
neu(ctx, fuer="Kim", text=GEHEIM, ausloeser={"datum": "2026-11-07"})
d = os.path.join(ctx.daten, "zeitkapsel", "kapseln.json")
liste = json.load(open(d, encoding="utf-8"))
liste[0]["zustellung"] = {"push": {"start": ts(2026, 11, 7, 9, 0)}}
liste[0]["erster_versuch"] = ts(2026, 11, 7, 9, 0)
json.dump(liste, open(d, "w", encoding="utf-8"))
ctx._jetzt = ts(2026, 11, 7, 9, 5)
zk.runde(ctx)
k = json.load(open(d, encoding="utf-8"))[0]
pruef("Absturz-Vermerk: kein zweiter Push", not ctx.pushes and len(ctx.durchsagen) == 1 and k["status"] == "geoeffnet",
      (ctx.pushes, k["status"]))
pruef("Absturz-Vermerk im Log", any("ohne Ergebnis" in z for z in ctx.logs), ctx.logs)


# Nur Durchsage und die geht zwei Tage nicht: Push als Ersatz
class ImmerStumm(sh_attrappe.Kontext):
    def durchsage(self, ziel, text):
        return False


ctx = kontext(klasse=ImmerStumm)
neu(ctx, fuer="Kim", text="Ersatzweg", ausloeser={"datum": "2026-11-07"}, kanal="durchsage")
for tag_, h in ((7, 9), (7, 10), (8, 12), (9, 9)):
    ctx._jetzt = ts(2026, 11, tag_, h, 5)
    zk.runde(ctx)
pruef("nach zwei Tagen noch kein Push (erst vormerken)", not ctx.pushes)
ctx._jetzt = ts(2026, 11, 9, 9, 10)
zk.runde(ctx)
k = json.load(open(os.path.join(ctx.daten, "zeitkapsel", "kapseln.json"), encoding="utf-8"))[0]
pruef("Ersatz-Push kommt einmal, Kapsel geöffnet", len(ctx.pushes) == 1 and k["status"] == "geoeffnet"
      and k.get("ersatz_push") is True, (ctx.pushes, k["status"]))
ctx._jetzt = ts(2026, 11, 10, 10, 0)
zk.runde(ctx)
pruef("Ersatz-Push nicht wiederholt", len(ctx.pushes) == 1)


# Runde wirft nie (Push und Durchsage werfen, Datei kaputt)
class Kaputt(sh_attrappe.Kontext):
    def push(self, *a, **kw):
        raise RuntimeError("ntfy weg")

    def durchsage(self, ziel, text):
        raise OSError("HA weg")


ctx = kontext(klasse=Kaputt)
neu(ctx, fuer="Kim", text="x", ausloeser={"datum": "2026-11-07"})
ctx._jetzt = ts(2026, 11, 7, 12, 0)
try:
    zk.runde(ctx)
    geworfen = None
except Exception as x:
    geworfen = x
pruef("runde wirft nicht bei Fehlern im Versand", geworfen is None, geworfen)
pruef("Fehler im Log", any("ging nicht" in z for z in ctx.logs), ctx.logs)
pruef("ohne Erfolg bleibt sie versiegelt", json.load(open(os.path.join(ctx.daten, "zeitkapsel", "kapseln.json"),
                                                          encoding="utf-8"))[0]["status"] == "versiegelt")
with open(os.path.join(ctx.daten, "zeitkapsel", "kapseln.json"), "w") as f:
    f.write("{kaputt")
try:
    zk.runde(ctx)
    geworfen = None
except Exception as x:
    geworfen = x
pruef("runde wirft nicht bei kaputter Datei", geworfen is None, geworfen)


# Löschen während der Zustellung: danach nichts mehr
class LoeschtBeimSprechen(sh_attrappe.Kontext):
    def durchsage(self, ziel, text):
        zk.auftrag({"aktion": "loeschen", "nr": 1}, "alex", self)
        return sh_attrappe.Kontext.durchsage(self, ziel, text)


ctx = kontext(klasse=LoeschtBeimSprechen)
neu(ctx, fuer="Kim", text="x", ausloeser={"datum": "2026-11-07"})
ctx._jetzt = ts(2026, 11, 7, 12, 0)
zk.runde(ctx)
pruef("gelöscht während der Durchsage: kein Push mehr", not ctx.pushes and not json.load(
    open(os.path.join(ctx.daten, "zeitkapsel", "kapseln.json"), encoding="utf-8")))


# Zwei Runden gleichzeitig: nur eine stellt zu
class Langsam(sh_attrappe.Kontext):
    def durchsage(self, ziel, text):
        time.sleep(0.3)
        return sh_attrappe.Kontext.durchsage(self, ziel, text)


ctx = kontext(klasse=Langsam)
neu(ctx, fuer="Kim", text="x", ausloeser={"datum": "2026-11-07"})
ctx._jetzt = ts(2026, 11, 7, 12, 0)
faeden = [threading.Thread(target=zk.runde, args=(ctx,)) for _ in range(3)]
for t in faeden:
    t.start()
for t in faeden:
    t.join()
zk.runde(ctx)
pruef("gleichzeitige Runden: einmal zugestellt", len(ctx.durchsagen) == 1 and len(ctx.pushes) == 1,
      (len(ctx.durchsagen), len(ctx.pushes)))

# Höchstens JE_RUNDE je Runde
ctx = kontext()
for i in range(zk.JE_RUNDE + 2):
    neu(ctx, fuer="Kim", text="Nr %d" % i, ausloeser={"datum": "2026-11-07"}, kanal="push")
ctx._jetzt = ts(2026, 11, 7, 12, 0)
zk.runde(ctx)
pruef("höchstens %d je Runde" % zk.JE_RUNDE, len(ctx.pushes) == zk.JE_RUNDE, len(ctx.pushes))
zk.runde(ctx)
pruef("Rest in der nächsten Runde", len(ctx.pushes) == zk.JE_RUNDE + 2, len(ctx.pushes))

# ------------------------------------------------------------------------------------------ Schnittstelle
pruef("Schnittstelle: NAME, RECHTE, TAKT_S", zk.NAME == "zeitkapsel" and zk.RECHTE == "familie" and zk.TAKT_S == 300)
pruef("Schema-Aktionen = AKTIONEN", zk.WERKZEUG["schema"]["properties"]["aktion"]["enum"] == list(zk.AKTIONEN))
param, standard, lesend = zk.FREMDTEXT["nur_lesen"]
pruef("Fremdtext: Standardaktion wie im Modul", param == "aktion" and standard == "liste"
      and set(lesend) <= set(zk.AKTIONEN) and "neu" not in lesend and "loeschen" not in lesend)
pruef("Fremdtext: archiv ist Quelle", zk.FREMDTEXT["quelle_aktionen"][2] == ["archiv"])
pruef("Werkzeugbeschreibung deutsch mit Umlauten", "Botschaft" in zk.WERKZEUG["beschreibung"]
      and "ö" in zk.WERKZEUG["beschreibung"])
import superhirn  # noqa: E402
pruef("superhirn.nur_lesend: liste/archiv und ohne aktion lesend",
      all(superhirn.nur_lesend(zk, x) for x in ({}, {"aktion": "liste"}, {"aktion": "archiv"})))
pruef("superhirn.nur_lesend: neu/loeschen nicht", not any(superhirn.nur_lesend(zk, {"aktion": x})
                                                          for x in ("neu", "loeschen", "Liste")))
# Einträge aus dem Einbau-Zettel in die echte Fremdtext-Logik (nur im Speicher dieses Tests, die Datei bleibt)
import fremdtext as ft  # noqa: E402
_alt = (ft.ZIELE, ft.QUELLEN, dict(ft.NUR_LESEN), dict(ft.QUELLE_AKTIONEN))
ft.ZIELE = ft.ZIELE | {"zeitkapsel"}
ft.QUELLEN = ft.QUELLEN | {"zeitkapsel"}
ft.NUR_LESEN["zeitkapsel"] = ("aktion", "liste", frozenset({"liste", "archiv"}))
ft.QUELLE_AKTIONEN["zeitkapsel"] = ("aktion", "liste", frozenset({"archiv"}))
pruef("fremdtext: neu/loeschen gesperrt, liste/archiv frei",
      all(ft.ist_ziel("mcp__jarvis__zeitkapsel", {"aktion": x}) for x in ("neu", "loeschen"))
      and not any(ft.ist_ziel("mcp__jarvis__zeitkapsel", {"aktion": x}) for x in ("liste", "archiv"))
      and ft.ist_ziel("zeitkapsel"))
pruef("fremdtext: nur archiv ist Quelle", ft.ist_quelle("zeitkapsel", {"aktion": "archiv"})
      and not any(ft.ist_quelle("zeitkapsel", {"aktion": x}) for x in ("liste", "neu")))
ft.ZIELE, ft.QUELLEN = _alt[0], _alt[1]
ft.NUR_LESEN.clear()
ft.NUR_LESEN.update(_alt[2])
ft.QUELLE_AKTIONEN.clear()
ft.QUELLE_AKTIONEN.update(_alt[3])

# ------------------------------------------------------------------------------------------ Lautsprecher-Sperre (0.7)
pruef("LAUTSPRECHER_PRIVAT: liste und archiv (frozenset), neu bleibt per Sprache erlaubt",
      isinstance(zk.LAUTSPRECHER_PRIVAT, frozenset) and zk.LAUTSPRECHER_PRIVAT == frozenset({"liste", "archiv"})
      and zk.LAUTSPRECHER_PRIVAT <= set(zk.AKTIONEN) and "neu" not in zk.LAUTSPRECHER_PRIVAT)

# ------------------------------------------------------------------------------------------ Englisch (seit 0.7)
DEUTSCH = re.compile(r"[äöüÄÖÜß„]|\b(ist|nicht|Bitte|bitte|und|oder|der|die|das|ein|eine|von|für|im|Zeitkapsel|"
                     r"versiegelt|Versiegelt|Durchsage|Raum|Zeichen|Geburtstag|Jahre|Uhr|gelöscht|dich|selbst|"
                     r"Überraschung|Archiv)\b")
TEXTE_EN = []


def en(r):
    t = m(r) if isinstance(r, dict) else str(r)
    TEXTE_EN.append(t)
    return t


def fehler_en(a, heute=HEUTE):
    return en(fehler(a, heute) or "")


werkzeug_obj = zk.WERKZEUG
try:
    zk.setze_sprache("fr")
    pruef("EN setze_sprache('fr') wirft ValueError", False)
except ValueError:
    pruef("EN setze_sprache('fr') wirft ValueError, Sprache bleibt", zk.SPRACHE == "de")
zk.setze_sprache("en")
b = zk.WERKZEUG["beschreibung"]
s = zk.WERKZEUG["schema"]["properties"]
pruef("EN WERKZEUG englisch (gleiches Objekt, Aktionen und Schlüssel gleich)",
      zk.WERKZEUG is werkzeug_obj and b.startswith("Time capsule:") and "in English" in b
      and not re.search(r"[äöüÄÖÜß„]|\b(ist|nicht|und|oder|der|die|das|für|Botschaft|Empfänger)\b", b)
      and s["aktion"]["enum"] == list(zk.AKTIONEN) and s["kanal"]["enum"] == list(zk.KANAELE)
      and s["fuer"]["description"] == "Recipient: name, id or \"me\""
      and s["ausloeser"]["properties"]["datum"]["description"] == "YYYY-MM-DD", b)
pruef("EN Ordnungszahlen", [zk.ordnungszahl_en(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111, 112)] ==
      ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st", "111th", "112th"])
pruef("EN Anlass", zk.faelligkeit({"in_jahren": 5}, HEUTE)[1] == "5 years after sealing"
      and zk.faelligkeit({"in_jahren": 1}, HEUTE)[1] == "one year after sealing"
      and zk.faelligkeit({"alter": 18, "geburtstag": "2012-05-12"}, HEUTE)[1] == "for the 18th birthday"
      and zk.faelligkeit({"alter": 21, "geburtstag": "2012-05-12"}, HEUTE)[1] == "for the 21st birthday")
pruef("EN Fehler der Fälligkeit", fehler_en({}).startswith("When should it open?")
      and fehler_en({"datum": "2027-02-29"}).startswith("I don't understand the date “2027-02-29”")
      and fehler_en({"in_jahren": 0}) == "in_jahren must be a whole number from 1 to 100."
      and fehler_en({"alter": 10, "geburtstag": "2012-05-12"}) == "The age 10 has already been reached (12 May 2022)."
      and fehler_en({"alter": 18}).startswith("For an age I need the birthday")
      and fehler_en({"alter": 1, "geburtstag": "2027-01-01"}) == "The birthday is in the future."
      and fehler_en({"datum": "2020-01-01"}) == "The day must be in the future, tomorrow at the earliest."
      and fehler_en({"datum": "2127-01-01"}) == "At most 100 years into the future.", TEXTE_EN[-8:])

RAEUME_EN = {"version": 1, "raeume": {"wohnzimmer": {"name": "Living room", "bereich": "Living room", "ausgabe": []},
                                      "kitchen": {"name": "Kitchen", "bereich": "Kitchen", "ausgabe": []}}}
GEHEIM_EN = "Dear Kim, today you are 18. The password for the treasure chest is cherry cake."
ctx = kontext(raeume=RAEUME_EN)
r = neu(ctx, fuer="Kim", text=GEHEIM_EN, ausloeser={"alter": 18, "geburtstag": "2012-05-12"})
tag = dt.date(2030, 5, 12)
pruef("EN neu: versiegelt, Datum, Anlass, Fenster, Weg", en(r) == (
    "Sealed: time capsule no. 1 for Kim. It opens on %s, 12 May 2030 (for the 18th birthday) between 9:00 and 20:00, "
    "as an announcement in the room Living room and by push. I won't reveal the content before then, not even to you."
    % zk.WOCHENTAGE_EN[tag.weekday()]) and "cherry" not in json.dumps(r), m(r))
r = neu(ctx, "sam", fuer="me", text="Note to myself", ausloeser={"in_jahren": 1}, kanal="push")
pruef("EN neu: für mich (me), per Push", en(r).startswith("Sealed: time capsule no. 2 for yourself. It opens on ")
      and "(one year after sealing)" in m(r) and ", by push. " in m(r), m(r))
r = neu(ctx, fuer="Sam", text="Surprise!", ausloeser={"datum": "2027-01-01"}, ueberraschung=True, kanal="push")
pruef("EN neu: Überraschung", en(r).endswith(" Sam won't see beforehand that it exists."), m(r))
r = neu(ctx, fuer="kim", text="Hello", ausloeser={"datum": "2027-06-01"}, kanal="durchsage", raum="ueberall")
pruef("EN neu: überall", ", as an announcement everywhere. " in en(r), m(r))
for wer, b_, erwartet in (
        ("alex", {"fuer": "Grandma", "text": "x", "ausloeser": {"in_jahren": 1}},
         "Who is the time capsule for? I know: Alex, Sam, Kim (or “me”)."),
        ("alex", {"fuer": "Kim", "text": " \n ", "ausloeser": {"in_jahren": 1}}, "What should the time capsule say?"),
        ("alex", {"fuer": "Kim", "text": "a" * 1501, "ausloeser": {"in_jahren": 1}},
         "The message is too long (1501 characters, at most 1500)."),
        ("alex", {"fuer": "Kim", "text": "x", "ausloeser": {"in_jahren": 1}, "kanal": "letter"},
         "kanal must be durchsage (announcement), push or beides (both)."),
        ("alex", {"fuer": "Kim", "text": "x", "ausloeser": {"in_jahren": 1}, "raum": "attic"},
         "I don't know the room “attic”. Possible: kitchen, wohnzimmer or ueberall (everywhere)."),
        ("gast1", {"fuer": "Kim", "text": "x", "ausloeser": {"in_jahren": 1}}, "Time capsules are only for the family.")):
    r = neu(ctx, wer, **b_)
    pruef("EN Absage: %s" % erwartet[:40], en(r) == erwartet, m(r))
pruef("EN unbekannte aktion", en(zk.auftrag({"aktion": "open"}, "alex", ctx)) ==
      "aktion must be one of liste, neu, archiv, loeschen.")
pruef("EN abgelehnte Aufträge legen nichts an", len(json.load(open(os.path.join(ctx.daten, "zeitkapsel",
                                                                                   "kapseln.json")))) == 4)

r = zk.auftrag({"aktion": "liste"}, "alex", ctx)
pruef("EN liste Absender: Eckdaten ohne Inhalt", en(r).startswith("Sealed by you (3):\n- No. 3, for Sam, created on "
      "6 Nov 2026, opens on 1 Jan 2027, 9 characters, by push, surprise\n") and "- No. 1, for Kim, created on 6 Nov "
      "2026, opens on 12 May 2030 (for the 18th birthday), %d characters, as an announcement in the room Living room "
      "and by push" % len(GEHEIM_EN) in m(r) and m(r).endswith("\nI won't reveal the content of sealed capsules "
                                                                "before the day.") and "cherry" not in json.dumps(r), m(r))
r = zk.auftrag({"aktion": "liste"}, "kim", ctx)
pruef("EN liste Empfänger", en(r).startswith("Sealed for you (2):\n- No. 4, from Alex, created on 6 Nov 2026, opens on "
                                             "1 Jun 2027, 5 characters\n- No. 1, from Alex"), m(r))
r = zk.auftrag({"aktion": "liste"}, "sam", ctx)
pruef("EN liste: an sich selbst, Überraschung unsichtbar", "- No. 2, for yourself, created on" in en(r)
      and "No. 3" not in m(r), m(r))
pruef("EN liste leer", en(zk.auftrag({"aktion": "liste"}, "alex", kontext(raeume=RAEUME_EN))) == "No time capsules.")
pruef("EN archiv versiegelt", en(zk.auftrag({"aktion": "archiv", "nr": 1}, "kim", ctx)) ==
      "Time capsule no. 1 is still sealed and opens on 12 May 2030. I won't reveal the content before then.")
pruef("EN archiv Überraschung unsichtbar", en(zk.auftrag({"aktion": "archiv", "nr": 3}, "sam", ctx)) ==
      "I can't find a time capsule no. 3.")
pruef("EN archiv leer", en(zk.auftrag({"aktion": "archiv"}, "kim", ctx)) ==
      "There is no opened time capsule in the archive yet.")
pruef("EN loeschen Empfänger", en(zk.auftrag({"aktion": "loeschen", "nr": 1}, "kim", ctx)) ==
      "Only the person who created it can delete it (Alex).")
pruef("EN loeschen ohne nr", en(zk.auftrag({"aktion": "loeschen"}, "alex", ctx)) ==
      "Which time capsule? Tell me the number (nr) from the list.")
pruef("EN loeschen Absender", en(zk.auftrag({"aktion": "loeschen", "nr": 4}, "alex", ctx)) ==
      "Time capsule no. 4 for Kim is deleted.")
pruef("EN loeschen an sich selbst", en(zk.auftrag({"aktion": "loeschen", "nr": 2}, "sam", ctx)) ==
      "Time capsule no. 2 for yourself is deleted.")

ctx = kontext(raeume=RAEUME_EN)
neu(ctx, fuer="Kim", text=GEHEIM_EN, ausloeser={"datum": "2026-11-07"})
neu(ctx, "sam", fuer="me", text="Note to myself", ausloeser={"datum": "2026-11-07"}, raum="kitchen")
neu(ctx, fuer="Kim", text="One year later", ausloeser={"in_jahren": 1}, kanal="push")
ctx._jetzt = ts(2026, 11, 7, 9, 0)
zk.runde(ctx)
pruef("EN Durchsagen mit Rahmen", [d["text"] for d in ctx.durchsagen] == [
    "A time capsule from Alex, sealed on 6 November 2026, for Kim. " + GEHEIM_EN,
    "A time capsule from Sam to themselves, sealed on 6 November 2026. Note to myself"]
      and [d["ziel"] for d in ctx.durchsagen] == ["wohnzimmer", "kitchen"], ctx.durchsagen)
pruef("EN Pushes: Titel und Text", [(p["person"], p["titel"], p["text"]) for p in ctx.pushes] == [
    ("kim", "Time capsule from Alex", "Sealed on 6 November 2026.\n\n" + GEHEIM_EN),
    ("sam", "Time capsule from yourself", "Sealed on 6 November 2026.\n\nNote to myself")], ctx.pushes)
ctx._jetzt = ts(2027, 11, 6, 10, 0)
zk.runde(ctx)
pruef("EN Push mit Anlass", ctx.pushes[-1]["text"] == "Sealed on 6 November 2026 (one year after sealing).\n\n"
      "One year later", ctx.pushes[-1:])
r = zk.auftrag({"aktion": "archiv", "nr": 1}, "kim", ctx)
pruef("EN archiv nach dem Öffnen", en(r) == "Time capsule no. 1 from Alex for Kim, sealed on 6 Nov 2026, opened on "
      "7 Nov 2026:\n“%s”" % GEHEIM_EN, m(r))
pruef("EN liste nach dem Öffnen", en(zk.auftrag({"aktion": "liste"}, "alex", ctx)) == "Opened, in the archive: 2.\n"
      "I won't reveal the content of sealed capsules before the day.")
for d in ctx.durchsagen:
    TEXTE_EN.append(d["text"])
for p in ctx.pushes:
    TEXTE_EN.extend([p["titel"], p["text"]])
fehl = [t for t in TEXTE_EN if not t or DEUTSCH.search(t)]
pruef("EN alle %d geprüften Texte ohne deutschen Rest" % len(TEXTE_EN), len(TEXTE_EN) >= 30 and not fehl, fehl)

zk.setze_sprache("de")
pruef("zurück auf Deutsch: WERKZEUG, Anlass, Datum", zk.SPRACHE == "de" and zk.WERKZEUG is werkzeug_obj
      and zk.WERKZEUG == zk.WERKZEUG_DE and "Botschaft" in zk.WERKZEUG["beschreibung"]
      and zk.faelligkeit({"in_jahren": 5}, HEUTE)[1] == "5 Jahre nach dem Versiegeln"
      and zk._kurz(HEUTE) == "06.11.2026" and m(zk.auftrag({}, "kim", kontext())) == "Keine Zeitkapseln.")

for c in KONTEXTE:
    c.aufraeumen()
pruef("Live-Daten unverändert", wache())
sys.exit(ergebnis("Zeitkapsel"))
