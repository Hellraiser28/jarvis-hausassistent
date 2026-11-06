#!/usr/bin/env python3
"""Tests S3 Familienrunde (bruecke/familienrunde.py, seit 0.7) mit der Attrappe: ohne Netz, ohne Claude, ohne
Live-Daten. Dazu die englische Fassung (setze_sprache("en")) und die Lautsprecher-Sperre.

    python3 tests/test_sh_familienrunde.py
"""
import importlib
import json
import os
import re
import stat
import sys
import threading

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "..", "bruecke"))

import sh_attrappe  # noqa: E402

pruef, ergebnis = sh_attrappe.pruefer()
wache = sh_attrappe.live_wache()

import familienrunde as fr  # noqa: E402

T0 = 1793000000.0
KONTEXTE = []


def kontext(**kw):
    ctx = sh_attrappe.Kontext(jetzt=T0, **kw)
    KONTEXTE.append(ctx)
    return ctx


def tok(push):
    return push["klick"].rsplit("/", 1)[1]


def get(ctx, token, pfad="runde/"):
    return fr.seite(pfad + token, {"_methode": "GET"}, ctx, True)


def post(ctx, token, wahl):
    return fr.seite("/runde/" + token, {"_methode": "POST", "wahl": wahl}, ctx, True)


def daten(ctx):
    with open(os.path.join(ctx.daten, fr.DATEI), encoding="utf-8") as f:
        return json.load(f)


def runde_nr(ctx, nr):
    return next(r for r in daten(ctx) if r["nr"] == nr)


def stimme(ctx, nr, person):
    return next(t for t in runde_nr(ctx, nr)["teilnehmer"] if t["person"] == person)["stimme"]


class Los:
    """Ersatz fuer fr.ZUFALL: waehlt einen festen Index aus der Spitze und merkt sich die Aufrufe."""

    def __init__(self, idx=0):
        self.idx, self.aufrufe = idx, []

    def choice(self, seq):
        self.aufrufe.append(list(seq))
        return seq[self.idx]


def neu(ctx, person="alex", **b):
    a = {"aktion": "neu", "frage": "Was essen wir Samstag?", "optionen": ["Pizza", "Pasta", "Salat"],
         "personen": ["Sam", "Kim"], "frist_minuten": 60}
    a.update(b)
    return fr.auftrag(a, person, ctx)


# ------------------------------------------------------------------ Schnittstelle, Import
vorher = threading.active_count()
importlib.reload(fr)
pruef("Import ohne Nebenwirkungen (keine Threads)", threading.active_count() == vorher)
pruef("NAME/RECHTE/TAKT_S", fr.NAME == "familienrunde" and fr.RECHTE == "familie" and fr.TAKT_S == 60)
s = fr.WERKZEUG["schema"]
pruef("WERKZEUG: Beschreibung und Schema", isinstance(fr.WERKZEUG["beschreibung"], str) and s["type"] == "object"
      and s["properties"]["aktion"]["enum"] == ["neu", "stand", "abbrechen"]
      and s["properties"]["optionen"]["maxItems"] == 6 and s["properties"]["frist_minuten"]["maximum"] == 2880)
pruef("WERKZEUG: Beschreibung mit Umlauten", "Säumige" in fr.WERKZEUG["beschreibung"])
pruef("FREMDTEXT: Ziel, nur stand liest", fr.FREMDTEXT == {"art": "ziel", "nur_lesen": ("aktion", "stand", ["stand"])})
pruef("Funktionen vorhanden", all(callable(getattr(fr, n)) for n in ("auftrag", "runde", "seite")))
kz = dict(fr.KOPFZEILEN)
pruef("Kopfzeilen: CSP wie vorgegeben",
      kz["Content-Security-Policy"].startswith("default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"))
pruef("Kopfzeilen: no-store, nosniff, kein Referrer, kein Rahmen",
      kz["Cache-Control"] == "no-store" and kz["X-Content-Type-Options"] == "nosniff"
      and kz["Referrer-Policy"] == "no-referrer" and kz["X-Frame-Options"] == "DENY")

pruef("SEITE_KOPFZEILEN wie bei zeigen", fr.SEITE_KOPFZEILEN is fr.KOPFZEILEN)
import superhirn as sh  # noqa: E402  (gemeinsame Einhaengung, nur gelesen)

pruef("superhirn: lesende Aktionen", sh.lesende_aktionen(fr) == ("aktion", "stand", frozenset({"stand"})))
pruef("superhirn: Testlauf nur stand", sh.nur_lesend(fr, {"aktion": "stand"}) and sh.nur_lesend(fr, {})
      and not sh.nur_lesend(fr, {"aktion": "neu"}) and not sh.nur_lesend(fr, {"aktion": "abbrechen"}))
pruef("superhirn: im Register", "familienrunde" in sh.NAMEN)

# ------------------------------------------------------------------ neu
ctx = kontext()
m = neu(ctx, ansage="Wohnzimmer")
pruef("neu: angelegt mit Nr. 1", m.get("nr") == 1, m)
pruef("neu: Meldung nennt Teilnehmer und Raum", "Sam und Kim" in m["meldung"] and "Wohnzimmer" in m["meldung"],
      m["meldung"])
pruef("neu: Gleichstand-Hinweis (Alex stimmt nicht mit ab)", "das Los" in m["meldung"], m["meldung"])
pruef("neu: je Teilnehmer ein Push", sorted(p["person"] for p in ctx.pushes) == ["kim", "sam"], ctx.pushes)
pruef("neu: Push-Link über ctx.oeffentlich", all(p["klick"].startswith("https://jarvis.test.invalid/runde/")
                                                  for p in ctx.pushes))
toks = {p["person"]: tok(p) for p in ctx.pushes}
pruef("neu: Tokens 22 Zeichen urlsafe, verschieden",
      all(re.fullmatch(r"[A-Za-z0-9_-]{22}", t) for t in toks.values()) and len(set(toks.values())) == 2)
pruef("neu: Push-Text mit Frage und Absender", all("Alex fragt: Was essen wir Samstag?" in p["text"]
                                                    and p["tag"] == "familienrunde-1" for p in ctx.pushes))
pruef("neu: kein Token in Meldung oder Log", not any(t in m["meldung"] or any(t in z for z in ctx.logs)
                                                     for t in toks.values()))
modus = stat.S_IMODE(os.stat(os.path.join(ctx.daten, fr.DATEI)).st_mode)
pruef("Datei 0600", modus == 0o600, oct(modus))
r1 = runde_nr(ctx, 1)
pruef("gespeichert: Frist, Ansage-Raum-ID, offen", r1["frist"] == T0 + 3600 and r1["ansage"] == "wohnzimmer"
      and r1["status"] == "offen" and all(t["zugestellt"] for t in r1["teilnehmer"]), r1)

# ------------------------------------------------------------------ Eingaben pruefen
ctxf = kontext()
faelle = [
    ("eine Option", dict(optionen=["Pizza"]), "feste Antworten"),
    ("sieben Optionen", dict(optionen=list("ABCDEFG")), "feste Antworten"),
    ("doppelte Option", dict(optionen=["Pizza", "pizza"]), "gleich"),
    ("leere Frage", dict(frage="  "), "Was soll ich fragen"),
    ("unbekannte Person", dict(personen=["Oma"]), "Wen meinst du"),
    ("Gast als Teilnehmer", dict(personen=["Sam", "Gast"]), "Gäste"),
    ("falscher Gleichstand", dict(gleichstand="muenze"), "gleichstand"),
    ("unbekannter Raum", dict(ansage="Dachboden"), "kenne ich nicht"),
    ("nur sich selbst", dict(personen=["Alex"]), "außer dir"),
]
for name, b, erwartet in faelle:
    m = neu(ctxf, **b)
    pruef("abgelehnt: " + name, erwartet in m["meldung"] and "nr" not in m, m)
pruef("abgelehnt: nichts verschickt, nichts gespeichert", not ctxf.pushes
      and not os.path.exists(os.path.join(ctxf.daten, fr.DATEI)))
m = neu(ctxf, person="gast1")
pruef("Gast darf keine Runde starten", "nur für die Familie" in m["meldung"], m)
m = neu(ctxf, person="fremd")
pruef("Unbekannte Person darf keine Runde starten", "nur für die Familie" in m["meldung"], m)
pruef("unbekannte Aktion", "aktion muss" in fr.auftrag({"aktion": "loeschen"}, "alex", ctxf)["meldung"])
m = neu(ctxf, frist_minuten=5)
pruef("Frist unter 10 Minuten -> 10", runde_nr(ctxf, m["nr"])["frist"] == T0 + 600 and "10 Minuten" in m["meldung"],
      m)
m = neu(ctxf, frist_minuten=99999)
pruef("Frist über 2880 Minuten -> 2880", runde_nr(ctxf, m["nr"])["frist"] == T0 + 2880 * 60)
m = neu(ctxf, frist_minuten=None)
pruef("Frist Standard 120 Minuten", runde_nr(ctxf, m["nr"])["frist"] == T0 + 7200)
lang = neu(ctxf, frage="x" * 500, optionen=["a" * 100, "b"])
r = runde_nr(ctxf, lang["nr"])
pruef("Frage und Optionen gekürzt", len(r["frage"]) == 200 and len(r["optionen"][0]) == 60)

# ------------------------------------------------------------------ hoechstens 5 offene je Person
ctxm = kontext()
for i in range(5):
    neu(ctxm, person="sam", personen=["Kim"])
m = neu(ctxm, person="sam", personen=["Kim"])
pruef("sechste offene Runde abgelehnt", "5 offene" in m["meldung"] and "nr" not in m, m)
m = neu(ctxm, person="alex")
pruef("andere Person darf weiter", m.get("nr") == 6, m)

# ------------------------------------------------------------------ alle
ctxa = kontext()
m = neu(ctxa, personen=["alle"])
pruef("alle: ganze Familie ohne Gäste", sorted(t["person"] for t in runde_nr(ctxa, m["nr"])["teilnehmer"])
      == ["alex", "kim", "sam"])
pruef("alle: Alex bekommt eigenen Link", any(p["person"] == "alex" and "Deine Runde" in p["text"]
                                              for p in ctxa.pushes))
pruef("alle: Gleichstand-Hinweis (deine Stimme)", "deine Stimme" in m["meldung"], m["meldung"])
c = kontext()
m = neu(c, personen=[])
m2 = neu(c, personen=None)
pruef("ohne personen: Rückfrage statt ganzer Familie", "Wen soll ich fragen" in m["meldung"] and "nr" not in m
      and "Wen soll ich fragen" in m2["meldung"] and not c.pushes, (m, m2))
pruef("„Familie“ wie „alle“", len(runde_nr(c, neu(c, personen=["die Familie"])["nr"])["teilnehmer"]) == 3)

# ------------------------------------------------------------------ Seite
code, typ, roh = get(ctx, toks["sam"])
seite_txt = roh.decode("utf-8")
pruef("GET: 200 HTML", code == 200 and typ == "text/html; charset=utf-8")
pruef("GET: Frage, Absender, drei Knöpfe", "Was essen wir Samstag?" in seite_txt and "Alex fragt:" in seite_txt
      and len(re.findall(r'<button type="submit" name="wahl" value="[0-2]"', seite_txt)) == 3, seite_txt[-600:])
pruef("GET: Formular per POST, kein JavaScript", '<form method="post">' in seite_txt and "<script" not in seite_txt
      and "onclick" not in seite_txt.lower())
pruef("GET: Umlaute in der Seite", "ändern" in seite_txt)
pruef("unbekanntes Token -> 404", get(ctx, "A" * 22)[0] == 404)
pruef("falsches Format -> 404", get(ctx, "abc")[0] == 404 and get(ctx, toks["sam"] + "/x")[0] == 404
      and get(ctx, "../" + toks["sam"])[0] == 404)
pruef("fremder Pfad -> None", fr.seite("gast-qr/" + toks["sam"], {}, ctx, True) is None
      and fr.seite("runden/x", {}, ctx, False) is None)
pruef("abfrage None -> wie GET", fr.seite("runde/" + toks["sam"], None, ctx, False)[0] == 200)
sh_alt = dict(sh._module)
sh._module.clear()
sh._module["familienrunde"] = fr                    # nur im Speicher: die anderen Module bleiben draussen
r = sh.seite("runde/" + toks["sam"], {"_methode": "GET"}, lambda person: ctx, True)
# superhirn.seite liefert (code, typ, bytes, kopfzeilen); die Kopfzeilen kommen aus SEITE_KOPFZEILEN des Moduls
pruef("über superhirn.seite erreichbar, mit den Kopfzeilen des Moduls", r is not None and r[0] == 200 and len(r) == 4
      and "Content-Security-Policy" in r[3], r[3] if r else r)
pruef("superhirn.seite: fremder Pfad -> None", sh.seite("zeigen/x", {}, lambda person: ctx, True) is None)
sh._module.clear()
sh._module.update(sh_alt)
zaehler = {"n": 0}
echt = fr.hmac.compare_digest


def zaehlend(a, b):
    zaehler["n"] += 1
    return echt(a, b)


fr.hmac.compare_digest = zaehlend
get(ctx, toks["kim"])
fr.hmac.compare_digest = echt
pruef("Token-Vergleich mit hmac.compare_digest", zaehler["n"] >= 2, zaehler)

ctxx = kontext()
m = neu(ctxx, frage='<script>alert(1)</script> & "x"', optionen=["<b>fett</b>", "Nein"])
roh = get(ctxx, tok(ctxx.pushes[0]))[2].decode("utf-8")
pruef("XSS: Frage und Optionen escaped", "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;x&quot;" in roh
      and "&lt;b&gt;fett&lt;/b&gt;" in roh and "<script>" not in roh and "<b>fett" not in roh)

# ------------------------------------------------------------------ Abstimmen
code, _, roh = post(ctx, toks["sam"], "1")
pruef("POST: Stimme gezählt, Danke", code == 200 and "Danke, Sam!" in roh.decode() and "„Pasta“" in roh.decode())
pruef("POST: gespeichert", stimme(ctx, 1, "sam") == 1)
code, _, roh = post(ctx, toks["sam"], "2")
pruef("POST: ändern möglich", code == 200 and stimme(ctx, 1, "sam") == 2
      and 'class="gewaehlt">Salat ✓' in roh.decode())
for w in ("9", "3", "x", "-1", "", "1 ", "01", "１"):
    code = post(ctx, toks["sam"], w)[0]
    pruef("POST ungültig %r -> 400, unverändert" % w, code == 400 and stimme(ctx, 1, "sam") == 2)
fr.seite("runde/" + toks["sam"], {"_methode": "GET", "wahl": "0"}, ctx, True)
pruef("GET mit wahl zählt nicht", stimme(ctx, 1, "sam") == 2)
fr.seite("runde/" + toks["sam"], {"wahl": "0"}, ctx, True)
pruef("ohne _methode zählt nicht", stimme(ctx, 1, "sam") == 2)
code = fr.seite("runde/" + toks["sam"], {"_methode": ["POST"], "wahl": ["1"]}, ctx, True)[0]
pruef("Formularfelder als Listen (parse_qs) gehen auch", code == 200 and stimme(ctx, 1, "sam") == 1)
pruef("Stimmen nie im Log", not any("Pasta" in z for z in ctx.logs))

# ------------------------------------------------------------------ stand
st = fr.auftrag({"aktion": "stand"}, "alex", ctx)["meldung"]
pruef("stand Ersteller: Frage, wer abgestimmt hat, wer fehlt", "„Was essen wir Samstag?“" in st
      and "abgestimmt 1 von 2 (Sam)" in st and "fehlt noch: Kim" in st, st)
pruef("stand Ersteller: kein Zwischenstand", "Stimmen:" not in st and "Pasta 1" not in st, st)
st_b = fr.auftrag({"aktion": "stand"}, "sam", ctx)["meldung"]
pruef("stand Teilnehmer: nur Eckdaten, keine fremden Texte", "Nr. 1 von Alex" in st_b and "du hast abgestimmt"
      in st_b and "Was essen" not in st_b and "Pizza" not in st_b and "Pasta" not in st_b, st_b)
st_l = fr.auftrag({}, "kim", ctx)["meldung"]
pruef("stand ohne aktion (Standard): noch nicht abgestimmt", "noch nicht abgestimmt" in st_l, st_l)
pruef("stand Gast: nichts", "nur für die Familie" in fr.auftrag({"aktion": "stand"}, "gast1", ctx)["meldung"])
pruef("stand nr unbekannt", "keine passende" in fr.auftrag({"aktion": "stand", "nr": 77}, "alex", ctx)["meldung"])

# ------------------------------------------------------------------ Halbzeit-Erinnerung
n = len(ctx.pushes)
ctx._jetzt = T0 + 29 * 60
fr.runde(ctx)
pruef("vor Halbzeit: keine Erinnerung", len(ctx.pushes) == n)
ctx._jetzt = T0 + 30 * 60
fr.runde(ctx)
neue = ctx.pushes[n:]
pruef("Halbzeit: Erinnerung nur an Säumige", [p["person"] for p in neue] == ["kim"]
      and "Erinnerung" in neue[0]["titel"] and tok(neue[0]) == toks["kim"], neue)
fr.runde(ctx)
pruef("Erinnerung nur einmal", len(ctx.pushes) == n + 1)
pruef("Erinnerung ersetzt den Link (gleicher tag)", neue[0]["tag"] == "familienrunde-1", neue)

# ------------------------------------------------------------------ Schluss, wenn alle abgestimmt haben
post(ctx, toks["kim"], "1")
n = len(ctx.pushes)
ctx._jetzt = T0 + 31 * 60
fr.runde(ctx)
erg = ctx.pushes[n:]
pruef("alle abgestimmt: Ergebnis an Teilnehmer und Ersteller", sorted(p["person"] for p in erg)
      == ["alex", "kim", "sam"] and all("Ergebnis" in p["titel"] for p in erg), erg)
pruef("Ergebnis: Mehrheit mit Verteilung", "Pasta (2 von 2 Stimmen)" in erg[0]["text"]
      and "Pizza 0, Pasta 2, Salat 0" in erg[0]["text"], erg[0]["text"])
pruef("Durchsage im Wohnzimmer", ctx.durchsagen and ctx.durchsagen[-1]["ziel"] == "wohnzimmer"
      and "Pasta" in ctx.durchsagen[-1]["text"], ctx.durchsagen)
pruef("Status beendet", runde_nr(ctx, 1)["status"] == "beendet")
code, _, roh = get(ctx, toks["sam"])
pruef("Seite nach Schluss: Ergebnis, kein Formular", code == 200 and "Pasta (2 von 2 Stimmen)" in roh.decode()
      and "<form" not in roh.decode() and "Deine Stimme: Pasta" in roh.decode())
code = post(ctx, toks["sam"], "0")[0]
pruef("POST nach Schluss: 409, unverändert", code == 409 and stimme(ctx, 1, "sam") == 1)
fr.runde(ctx)
pruef("Ergebnis nur einmal", len(ctx.pushes) == n + 3)
pruef("Ergebnis ersetzt den Link (gleicher tag)", all(p["tag"] == "familienrunde-1" for p in erg), erg)
st = fr.auftrag({"aktion": "stand", "nr": 1}, "alex", ctx)["meldung"]
pruef("stand Ersteller nach Schluss: Ergebnis", "beendet" in st and "Pasta" in st, st)
st_b = fr.auftrag({"aktion": "stand", "nr": 1}, "sam", ctx)["meldung"]
pruef("stand Teilnehmer nach Schluss: ohne Text", "beendet" in st_b and "Pasta" not in st_b, st_b)

# ------------------------------------------------------------------ Fristende mit Teilnahme
ctx2 = kontext()
m = neu(ctx2, personen=["alle"], frist_minuten=10)
t2 = {p["person"]: tok(p) for p in ctx2.pushes}
post(ctx2, t2["sam"], "0")
ctx2._jetzt = T0 + 9 * 60
fr.runde(ctx2)
pruef("vor Fristende offen", runde_nr(ctx2, 1)["status"] == "offen")
ctx2._jetzt = T0 + 10 * 60
fr.runde(ctx2)
r = runde_nr(ctx2, 1)
pruef("Fristende: beendet mit 1 von 3", r["status"] == "beendet" and r["ergebnis"]["abgegeben"] == 1
      and r["ergebnis"]["gewinner"] == 0 and "Abgestimmt haben 1 von 3" in ctx2.pushes[-1]["text"])
pruef("ohne ansage keine Durchsage", not ctx2.durchsagen)
code = fr.seite("runde/" + t2["kim"], {"_methode": "POST", "wahl": "1"}, ctx2, True)[0]
pruef("nach Fristende keine Stimme mehr", code == 409)

# ------------------------------------------------------------------ Gleichstand
los = Los(1)
fr.ZUFALL = los
ctx3 = kontext()
neu(ctx3, personen=["alle"], optionen=["Kino", "Spieleabend"])
t3 = {p["person"]: tok(p) for p in ctx3.pushes}
post(ctx3, t3["alex"], "0")
post(ctx3, t3["sam"], "1")
ctx3._jetzt = T0 + 3600
fr.runde(ctx3)
r = runde_nr(ctx3, 1)
pruef("Gleichstand fragende_person: Alex' Stimme entscheidet", r["ergebnis"]["gewinner"] == 0
      and r["ergebnis"]["entscheid"] == "fragende_person" and not los.aufrufe
      and "Alex' Stimme entscheidet" in ctx3.pushes[-1]["text"], (r["ergebnis"], ctx3.pushes[-1]))

ctx4 = kontext()
neu(ctx4, optionen=["Kino", "Spieleabend"])                       # Alex stimmt nicht mit ab
t4 = {p["person"]: tok(p) for p in ctx4.pushes}
post(ctx4, t4["sam"], "0")
post(ctx4, t4["kim"], "1")
ctx4._jetzt = T0 + 61
fr.runde(ctx4)
r = runde_nr(ctx4, 1)
pruef("Gleichstand ohne Stimme der fragenden Person: Los", r["ergebnis"]["entscheid"] == "zufall_ersatz"
      and r["ergebnis"]["gewinner"] == 1 and los.aufrufe[-1] == [0, 1]
      and "also entscheidet das Los: " not in ctx4.pushes[-1]["text"]
      and "entscheidet das Los" in ctx4.pushes[-1]["text"], (r["ergebnis"], ctx4.pushes[-1]["text"]))

ctx5 = kontext()
neu(ctx5, personen=["alle"], optionen=["A", "B", "C"], gleichstand="zufall")
t5 = {p["person"]: tok(p) for p in ctx5.pushes}
post(ctx5, t5["alex"], "0")
post(ctx5, t5["sam"], "2")
post(ctx5, t5["kim"], "1")
fr.runde(ctx5)                                                    # alle haben abgestimmt
r = runde_nr(ctx5, 1)
pruef("Gleichstand zufall: Los über alle Spitzenreiter", r["ergebnis"]["entscheid"] == "zufall"
      and los.aufrufe[-1] == [0, 1, 2] and r["ergebnis"]["gewinner"] == 1
      and "das Los entscheidet" in ctx5.pushes[-1]["text"], r["ergebnis"])
fr.ZUFALL = fr.random.SystemRandom()

ctx6 = kontext()
neu(ctx6, ansage="Küche", frist_minuten=10)
ctx6._jetzt = T0 + 600
fr.runde(ctx6)
pruef("keine Stimmen: niemand abgestimmt, keine Durchsage", "niemand abgestimmt" in ctx6.pushes[-1]["text"]
      and not ctx6.durchsagen and runde_nr(ctx6, 1)["ergebnis"]["entscheid"] == "keine_stimmen")

# ------------------------------------------------------------------ abbrechen
ctx7 = kontext()
neu(ctx7)
t7 = {p["person"]: tok(p) for p in ctx7.pushes}
m = fr.auftrag({"aktion": "abbrechen", "nr": 1}, "sam", ctx7)["meldung"]
pruef("abbrechen nur durch Ersteller", "nur, wer die Runde gestartet hat" in m and runde_nr(ctx7, 1)["status"]
      == "offen", m)
pruef("abbrechen durch Gast abgelehnt", "nur für die Familie" in fr.auftrag({"aktion": "abbrechen", "nr": 1},
                                                                            "gast1", ctx7)["meldung"])
n = len(ctx7.pushes)
m = fr.auftrag({"aktion": "abbrechen"}, "alex", ctx7)["meldung"]
pruef("abbrechen ohne nr bei einer offenen Runde", "Nr. 1 abgebrochen" in m and runde_nr(ctx7, 1)["status"]
      == "abgebrochen", m)
pruef("abbrechen: Teilnehmer bekommen Bescheid", sorted(p["person"] for p in ctx7.pushes[n:]) == ["kim", "sam"]
      and all("abgebrochen" in p["text"] for p in ctx7.pushes[n:]))
roh = get(ctx7, t7["sam"])[2].decode()
pruef("Seite nach Abbruch", "abgebrochen" in roh and "<form" not in roh)
pruef("POST nach Abbruch: 409", post(ctx7, t7["sam"], "0")[0] == 409)
pruef("abbrechen doppelt", "schon vorbei" in fr.auftrag({"aktion": "abbrechen", "nr": 1}, "alex", ctx7)["meldung"])
fr.runde(ctx7)
pruef("abgebrochene Runde: kein Ergebnis-Push", len(ctx7.pushes) == n + 2)

# ------------------------------------------------------------------ Tokens verfallen, Aufraeumen
schluss = runde_nr(ctx, 1)["schluss"]
ctx._jetzt = schluss + 24 * 3600 - 1
pruef("Link gilt bis 24 h nach Schluss", get(ctx, toks["sam"])[0] == 200)
ctx._jetzt = schluss + 24 * 3600
pruef("Link 24 h nach Schluss ungültig", get(ctx, toks["sam"])[0] == 404)
fr.runde(ctx)
pruef("Tokens nach 24 h aus der Datei entfernt", all(t["token"] == "" for t in runde_nr(ctx, 1)["teilnehmer"]))
pruef("stand zeigt beendete Runde noch", "beendet" in fr.auftrag({"aktion": "stand"}, "alex", ctx)["meldung"])
ctx._jetzt = schluss + 7 * 86400
fr.runde(ctx)
pruef("nach 7 Tagen entfernt", daten(ctx) == [])

# ------------------------------------------------------------------ Push-Kanaele, Robustheit
class OhneKim(sh_attrappe.Kontext):
    def push(self, person, titel, text, klick=None, tag="jarvis"):
        if person == "kim":
            return False
        return sh_attrappe.Kontext.push(self, person, titel, text, klick, tag)


ctx8 = OhneKim(jetzt=T0)
KONTEXTE.append(ctx8)
m = neu(ctx8)
pruef("ohne Push-Kanal: genannt, Runde läuft", "Nicht erreicht (kein Push-Kanal): Kim" in m["meldung"]
      and m.get("nr") == 1, m)
pruef("zugestellt gespeichert", {t["person"]: t["zugestellt"] for t in runde_nr(ctx8, 1)["teilnehmer"]}
      == {"sam": True, "kim": False})
m = neu(ctx8, personen=["Kim"])
pruef("niemand erreichbar: Runde verworfen", "niemanden erreichen" in m["meldung"] and len(daten(ctx8)) == 1, m)


class Kaputt(sh_attrappe.Kontext):
    def push(self, *a, **k):
        raise RuntimeError("ntfy weg")

    def durchsage(self, *a, **k):
        raise RuntimeError("Lautsprecher weg")


ctx9 = Kaputt(jetzt=T0)
KONTEXTE.append(ctx9)
with open(os.path.join(ctx9.daten, fr.DATEI), "w") as f:
    json.dump([{"nr": 1, "ersteller": "alex", "frage": "F", "optionen": ["A", "B"], "gleichstand": "zufall",
                "ansage": "kueche", "start": T0 - 7200, "frist": T0 - 1, "erinnert": False, "status": "offen",
                "teilnehmer": [{"person": "sam", "token": "B" * 22, "stimme": 0, "zeit": T0 - 60}],
                "schluss": None, "ergebnis": None}], f)
try:
    fr.runde(ctx9)
    ok = True
except Exception as x:
    ok = x
pruef("runde wirft nicht, wenn Push und Durchsage scheitern", ok is True and runde_nr(ctx9, 1)["status"] == "beendet",
      ok)
with open(os.path.join(ctx9.daten, fr.DATEI), "w") as f:
    f.write("{kaputt")
try:
    fr.runde(ctx9)
    ok = True
except Exception as x:
    ok = x
pruef("runde wirft nicht bei kaputter Datei, Datei gesichert", ok is True
      and os.path.exists(os.path.join(ctx9.daten, fr.DATEI + ".kaputt")), ok)
pruef("seite wirft nicht bei kaputtem Kontext", fr.seite("runde/" + "C" * 22, {"_methode": "POST"}, object(), True)[0]
      in (404, 500))

# ------------------------------------------------------------------ Rezeptideen (ctx.rezept_ideen, seit 0.7)
cm = kontext()
r = fr.auftrag({"aktion": "neu", "frage": "Was essen wir Samstag?", "optionen_aus": "rezepte", "anzahl": 3,
                "personen": ["Sam", "Kim"]}, "alex", cm)
rd = daten(cm)[0] if os.path.exists(os.path.join(cm.daten, fr.DATEI)) else {}
pruef("Rezepte: drei Rezeptideen als Antworten, Runde merkt sich die Quelle",
      rd.get("optionen") == ["Lasagne", "Pizza Margherita", "Linsensuppe"] and rd.get("quelle") == fr.QUELLE_REZEPTE, (r, rd))
pruef("Rezepte: Titel NICHT in der Antwort ans Gehirn (fremder Text), nur die Zahl",
      "Lasagne" not in r["meldung"] and "3 Rezeptideen aus der Rezeptsammlung" in r["meldung"], r)
an_alex = [p for p in cm.pushes if p["person"] == "alex"]
pruef("Rezepte: Liste per Push an die fragende Person", len(an_alex) == 1 and "Lasagne" in an_alex[0]["text"], cm.pushes)
seite_rezepte = get(cm, tok([p for p in cm.pushes if p["person"] == "sam"][0]))
pruef("Rezepte: Abstimmseite zeigt die Rezepte", seite_rezepte[0] == 200 and "Lasagne" in seite_rezepte[2].decode("utf-8"))
# Fehler 06.11.: Die fragende Person stimmt mit ab. Die Liste kam mit demselben tag wie ihr Abstimm-Link, und die
# HA-App ersetzte den Link durch die Liste (Antippen oeffnete nur noch HA)
cm5 = kontext()
KONTEXTE.append(cm5)
r5 = fr.auftrag({"aktion": "neu", "frage": "Was essen wir Samstag?", "optionen_aus": "rezepte", "anzahl": 3,
                 "personen": ["Alex", "Sam"]}, "alex", cm5)
an_alex5 = [p for p in cm5.pushes if p["person"] == "alex"]
link5 = [p for p in an_alex5 if p["klick"]]
ideen5 = [p for p in an_alex5 if not p["klick"]]
pruef("Rezepte, fragende Person stimmt mit: Link und Liste mit verschiedenem tag",
      len(link5) == 1 and len(ideen5) == 1 and link5[0]["tag"] == "familienrunde-1"
      and ideen5[0]["tag"] == "familienrunde-1-ideen" and "Lasagne" in ideen5[0]["text"], (r5, cm5.pushes))
st_m = fr.auftrag({"aktion": "stand"}, "alex", cm)["meldung"]
pruef("Rezepte: stand ohne Rezepttitel", "Rezeptideen aus der Rezeptsammlung" in st_m and "Lasagne" not in st_m, st_m)
cm2 = kontext()
cm2.rezepte = ["Pasta Carbonara", "Pasta Pesto"]
r2 = fr.auftrag({"aktion": "neu", "frage": "Welche Pasta?", "optionen_aus": "rezepte", "rezept_suche": "Pasta",
                 "personen": ["Sam"]}, "alex", cm2)
cm3 = kontext()
cm3.rezepte = ["Nur eins"]
r3 = fr.auftrag({"aktion": "neu", "frage": "Was essen wir?", "optionen_aus": "rezepte", "personen": ["Sam"]}, "alex", cm3)
cm4 = kontext()
cm4.rezept_ideen = lambda anzahl, suche=None: (_ for _ in ()).throw(OSError("Rezeptquelle weg"))
r4 = fr.auftrag({"aktion": "neu", "frage": "Was essen wir?", "optionen_aus": "rezepte", "personen": ["Sam"]}, "alex", cm4)
pruef("Rezepte: mit Suchwort, zu wenige Ideen und Quelle weg: ehrliche Absage statt halber Runde",
      daten(cm2)[0]["optionen"] == ["Pasta Carbonara", "Pasta Pesto"] and "zu wenige Rezeptideen" in r3["meldung"]
      and "zu wenige Rezeptideen" in r4["meldung"] and not os.path.exists(os.path.join(cm3.daten, fr.DATEI)) or
      not daten(cm3), (r2, r3, r4))

# ------------------------------------------------------------------ Lautsprecher-Sperre (seit 0.7)
pruef("LAUTSPRECHER_PRIVAT leer (frozenset): stand nennt bei fremden Runden keine Texte",
      isinstance(fr.LAUTSPRECHER_PRIVAT, frozenset) and fr.LAUTSPRECHER_PRIVAT == frozenset())

# ------------------------------------------------------------------ Englisch (seit 0.7)
DEUTSCH = re.compile(r"[äöüÄÖÜß„]|\b(?:ist|nicht|Bitte|bitte|und|oder|der|die|das|dich|mit|von|bis|Uhr|Runde|Stimme|"
                     r"Stimmen|Familienrunde|abgestimmt|Nr|heute|morgen)\b")


def deutsch(text):
    return DEUTSCH.findall(str(text))


try:
    fr.setze_sprache("fr")
    pruef("EN: fremde Sprache abgelehnt", False)
except ValueError:
    pruef("EN: fremde Sprache abgelehnt", fr.SPRACHE == "de")
fr.setze_sprache("en")
w = fr.WERKZEUG
pruef("EN: WERKZEUG englisch, Schema unveraendert", w is fr.WERKZEUG_EN and "Family vote" in w["beschreibung"]
      and not deutsch(w["beschreibung"]) and w["schema"] == fr.WERKZEUG_DE["schema"], deutsch(w["beschreibung"]))
pruef("EN: Kopfzeilen und Token-Muster unabhaengig von der Sprache", fr.SEITE_KOPFZEILEN is fr.KOPFZEILEN
      and dict(fr.KOPFZEILEN)["Content-Security-Policy"] == fr.CSP and fr.TOKEN.pattern == r"^[A-Za-z0-9_-]{22}$")
ce = kontext()
m = neu(ce, frage="What shall we eat on Saturday?", optionen=["Pizza", "Pasta", "Salad"], ansage="Wohnzimmer")
pruef("EN: neu meldet englisch", re.fullmatch(r"I'm asking Sam and Kim: “What shall we eat on Saturday\?” \(Pizza / "
                                             r"Pasta / Salad\), answers until today at \d\d:\d\d\. You're not voting "
                                             r"yourself, so if there's a tie, a draw decides\. I'll also announce the "
                                             r"result in the room Wohnzimmer\. \(No\. 1\)", m["meldung"]) is not None,
      m["meldung"])
te = {p["person"]: tok(p) for p in ce.pushes}
pruef("EN: Push an die Teilnehmer", all(p["titel"] == "Family vote" and re.fullmatch(
    r"Alex asks: What shall we eat on Saturday\? Tap to vote \(until today at \d\d:\d\d\)\.", p["text"])
    for p in ce.pushes) and len(ce.pushes) == 2, ce.pushes)
code, typ, roh = get(ce, te["sam"])
s_en = roh.decode("utf-8")
pruef("EN: Abstimmseite englisch (lang, Titel, Kopf, Hinweis), ohne deutsche Reste", code == 200
      and '<html lang="en">' in s_en and "<title>Family vote</title>" in s_en and "<h1>FAMILY VOTE</h1>" in s_en
      and "<p>Alex asks:</p>" in s_en and "You can change your vote until today at" in s_en
      and '<form method="post">' in s_en and "<script" not in s_en and not deutsch(s_en), deutsch(s_en))
code, _, roh = post(ce, te["sam"], "1")
pruef("EN: Stimme gezaehlt", code == 200 and "Thanks, Sam! Your vote for “Pasta” has been counted." in roh.decode())
code, _, roh = post(ce, te["sam"], "7")
pruef("EN: ungueltige Wahl 400", code == 400 and "That answer doesn't exist, please use one of the buttons."
      in roh.decode() and stimme(ce, 1, "sam") == 1)
st = fr.auftrag({"aktion": "stand"}, "alex", ce)["meldung"]
pruef("EN: stand Ersteller", re.fullmatch(r"No\. 1 \(open until today at \d\d:\d\d\): “What shall we eat on "
                                         r"Saturday\?” \(Pizza / Pasta / Salad\) – 1 of 2 voted \(Sam\); still "
                                         r"missing: Kim\. Result only at the end\.", st) is not None, st)
st_s = fr.auftrag({"aktion": "stand"}, "sam", ce)["meldung"]
st_k = fr.auftrag({}, "kim", ce)["meldung"]
pruef("EN: stand Teilnehmer ohne fremde Texte", "No. 1 from Alex, open until today at" in st_s
      and "you have voted (you can change it via the link)." in st_s and "you haven't voted yet (link by push)." in st_k
      and "Saturday" not in st_s + st_k and "Pasta" not in st_s + st_k and not deutsch(st_s + st_k), (st_s, st_k))
n = len(ce.pushes)
ce._jetzt = T0 + 30 * 60
fr.runde(ce)
pruef("EN: Erinnerung", [p["person"] for p in ce.pushes[n:]] == ["kim"] and ce.pushes[n]["titel"] ==
      "Family vote: reminder" and ce.pushes[n]["text"].startswith("Alex is still waiting for your vote: What shall we "
                                                                  "eat on Saturday? Tap to vote (until today at"),
      ce.pushes[n:])
post(ce, te["kim"], "1")
n = len(ce.pushes)
ce._jetzt = T0 + 31 * 60
fr.runde(ce)
erg_en = ce.pushes[n:]
pruef("EN: Ergebnis per Push", sorted(p["person"] for p in erg_en) == ["alex", "kim", "sam"]
      and all(p["titel"] == "Family vote: result" and p["text"] == "“What shall we eat on Saturday?”: Pasta (2 of 2 "
              "votes). Votes: Pizza 0, Pasta 2, Salad 0. 2 of 2 voted." for p in erg_en), erg_en)
pruef("EN: Durchsage", ce.durchsagen and ce.durchsagen[-1]["text"] == "The family vote is decided. “What shall we eat "
      "on Saturday?”: Pasta (2 of 2 votes).", ce.durchsagen)
code, _, roh = get(ce, te["sam"])
pruef("EN: Seite nach Schluss", code == 200 and "Your vote: Pasta." in roh.decode() and "<form" not in roh.decode())
code, _, roh = post(ce, te["sam"], "0")
pruef("EN: POST nach Schluss 409", code == 409 and "The vote is already over, your vote no longer counts." in
      roh.decode() and stimme(ce, 1, "sam") == 1)
pruef("EN: stand nach Schluss", fr.auftrag({"aktion": "stand", "nr": 1}, "alex", ce)["meldung"].startswith(
    "No. 1 (finished): “What shall we eat on Saturday?”: Pasta"))
pruef("EN: ungueltiger Link", get(ce, "Q" * 22)[2] == b"Not valid (any more).")

ce2 = kontext()
m = neu(ce2, frage="Cinema or games?", personen=["everyone"], optionen=["Cinema", "Games night"])
t2 = {p["person"]: tok(p) for p in ce2.pushes}
pruef("EN: „everyone“ = ganze Familie ohne Gaeste, eigene Stimme entscheidet beim Gleichstand",
      sorted(t2) == ["alex", "kim", "sam"] and "If there's a tie, your vote decides." in m["meldung"]
      and "You'll get a voting link too." in m["meldung"]
      and any(p["person"] == "alex" and p["text"].startswith("Your vote: ") for p in ce2.pushes), m["meldung"])
post(ce2, t2["alex"], "0")
post(ce2, t2["sam"], "1")
ce2._jetzt = T0 + 3600
fr.runde(ce2)
pruef("EN: Gleichstand fragende Person", ce2.pushes[-1]["text"].startswith(
    "“Cinema or games?”: Cinema. Tie between Cinema and Games night, Alex's vote decides.")
    and not deutsch(ce2.pushes[-1]["text"]), ce2.pushes[-1]["text"])
los = Los(0)
fr.ZUFALL = los
ce3 = kontext()
neu(ce3, frage="Cinema or games?", personen=["Sam", "Kim"], optionen=["Cinema", "Games night"])
t3 = {p["person"]: tok(p) for p in ce3.pushes}
post(ce3, t3["sam"], "0")
post(ce3, t3["kim"], "1")
fr.runde(ce3)
pruef("EN: Gleichstand ohne Stimme der fragenden Person", "Tie between Cinema and Games night, Alex voted for none "
      "of them, so a draw decides." in ce3.pushes[-1]["text"], ce3.pushes[-1]["text"])
fr.ZUFALL = fr.random.SystemRandom()
ce4 = kontext()
m = neu(ce4, frage="Pizza tonight?", optionen=["Yes", "No"], personen=["me", "Sam"], gleichstand="zufall",
        frist_minuten=5)
pruef("EN: „me“ = fragende Person, Frist korrigiert, Los", "I set the deadline to 10 minutes (allowed 10 to 2880)."
      in m["meldung"] and "If there's a tie, a draw decides." in m["meldung"]
      and sorted(t["person"] for t in runde_nr(ce4, m["nr"])["teilnehmer"]) == ["alex", "sam"], m["meldung"])
ce4._jetzt = T0 + 600
fr.runde(ce4)
pruef("EN: niemand abgestimmt", ce4.pushes[-1]["text"] == "Nobody voted on “Pizza tonight?”.",
      ce4.pushes[-1]["text"])
ce5 = kontext()
fehler_en = [neu(ce5, person="gast1")["meldung"], fr.auftrag({"aktion": "x"}, "alex", ce5)["meldung"],
             neu(ce5, personen=[])["meldung"], neu(ce5, personen=["Grandma"])["meldung"],
             neu(ce5, personen=["Sam", "Gast"])["meldung"], neu(ce5, optionen=["A"])["meldung"],
             neu(ce5, optionen=["A", "a"])["meldung"], neu(ce5, gleichstand="coin")["meldung"],
             neu(ce5, personen=["me"])["meldung"], neu(ce5, frage=" ")["meldung"],
             fr.auftrag({"aktion": "stand"}, "alex", ce5)["meldung"], fr.auftrag({"aktion": "abbrechen"}, "alex",
                                                                                ce5)["meldung"]]
pruef("EN: Fehlermeldungen englisch", fehler_en == [
    "Family votes are only for the family.", "aktion must be neu, stand or abbrechen.",
    "Who should I ask? Give me names or “everyone”.", "Who do you mean by “Grandma”? I know: Alex, Kim, Sam.",
    "Guests don't take part in family votes (Gast).", "I need 2 to 6 fixed answers (no free text).",
    "Two answers are the same, please give each one only once.", "gleichstand must be fragende_person or zufall.",
    "Who should I ask besides you?", "What should I ask?", "No family votes.", "You have no open vote."], fehler_en)
pruef("EN: unbekannter Raum", neu(ce5, ansage="Attic")["meldung"].startswith("I don't know the room “Attic”. "
                                                                             "Possible: "))
pruef("EN: nichts verschickt", not ce5.pushes)
ce6 = kontext()
m = neu(ce6, frage='<script>alert(1)</script> & "x"', optionen=["<b>bold</b>", "No"])
t6 = {p["person"]: tok(p) for p in ce6.pushes}
roh = get(ce6, t6["sam"])[2].decode("utf-8")
pruef("EN: XSS auch englisch escaped", "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;x&quot;" in roh
      and "&lt;b&gt;bold&lt;/b&gt;" in roh and "<script>" not in roh and "<b>bold" not in roh)
mb = fr.auftrag({"aktion": "abbrechen", "nr": m["nr"]}, "sam", ce6)["meldung"]
n = len(ce6.pushes)
ma = fr.auftrag({"aktion": "abbrechen"}, "alex", ce6)["meldung"]
pruef("EN: abbrechen", mb == "Only whoever started the vote can cancel it (Alex)." and ma == "Vote no. 1 cancelled, the "
      "others have been told." and all(p["text"].startswith("Alex cancelled the vote “") and p["titel"] == "Family vote"
                                       for p in ce6.pushes[n:]) and len(ce6.pushes[n:]) == 2, (mb, ma))
pruef("EN: Seite nach Abbruch", "Alex cancelled the vote." in get(ce6, t6["sam"])[2].decode()
      and fr.auftrag({"aktion": "abbrechen", "nr": 1}, "alex", ce6)["meldung"] == "Vote no. 1 is already over.")
cr = kontext()
r = fr.auftrag({"aktion": "neu", "frage": "What do we eat?", "optionen_aus": "rezepte", "anzahl": 3,
                "personen": ["Sam", "Kim"]}, "alex", cr)
an_alex = [p for p in cr.pushes if p["person"] == "alex"]
pruef("EN: Rezeptideen ohne Titel in der Antwort", "3 recipe ideas from the recipe collection, the list comes by push"
      in r["meldung"] and "Lasagne" not in r["meldung"] and len(an_alex) == 1
      and an_alex[0]["titel"] == "Family vote: recipe ideas" and an_alex[0]["text"].startswith(
          "To choose from for “What do we eat?”: Lasagne / "), (r, an_alex))
st = fr.auftrag({"aktion": "stand"}, "alex", cr)["meldung"]
pruef("EN: stand ohne Rezepttitel", "(recipe ideas from the recipe collection)" in st and "Lasagne" not in st, st)
cr2 = kontext()
cr2.rezepte = ["Only one"]
r2 = fr.auftrag({"aktion": "neu", "frage": "What do we eat?", "optionen_aus": "rezepte", "personen": ["Sam"]}, "alex",
                cr2)
pruef("EN: zu wenige Rezeptideen", r2["meldung"] == "Too few recipe ideas came from the recipe collection just now. "
      "Better give me the answers yourself.", r2)
c8 = OhneKim(jetzt=T0)
KONTEXTE.append(c8)
m8 = neu(c8)
m9 = neu(c8, personen=["Kim"])
pruef("EN: ohne Push-Kanal", "Not reached (no push channel): Kim." in m8["meldung"] and m9["meldung"] ==
      "I couldn't reach anyone (no push channel), so I dropped the vote again.", (m8, m9))
fr.setze_sprache("de")
roh = get(ce, te["kim"])[2].decode("utf-8")
pruef("Zurueck auf Deutsch: WERKZEUG und Seite", fr.WERKZEUG is fr.WERKZEUG_DE and '<html lang="de">' in roh
      and "<h1>FAMILIENRUNDE</h1>" in roh and "Deine Stimme: Pasta." in roh)

# ------------------------------------------------------------------ Ende
for c in KONTEXTE:
    c.aufraeumen()
pruef("Live-Daten unverändert", wache(("familienrunde.json",)))
sys.exit(ergebnis("Familienrunde"))
