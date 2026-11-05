#!/usr/bin/env python3
"""Baustein quiz.py (Familien-Quizshow, im Release seit 0.6) ohne Bruecke, Leinwand und Ton: Katalog pruefen,
Spieler, Kategorien, Ziehen (reihum/alle, Schwierigkeitsleiter, Gespieltes), Fangfragen (Runde 1 immer, Anteile, je
Runde fuer alle gleich, ohne Fangfragen exakt wie vorher), Antworten, Aufloesen, Ende, Anzeige ohne verfruehte Loesung,
Ansagen mit konfigurierbaren Namen, Ton auswerten (Pausen, Huellkurve), Ablage, englische Texte.
Testordner statt echter Daten, keine Netzzugriffe, kein ffmpeg (PCM wird im Test erzeugt)."""
import json
import math
import os
import random
import shutil
import struct
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import quiz as qz  # noqa: E402

T = tempfile.mkdtemp(prefix="quiz-test-")
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


def frage(fid, stufe, kat, nr, richtig="B", schwierigkeit=3):
    return {"id": fid, "stufe": stufe, "kategorie": kat, "frage": "Testfrage %s Nummer %d?" % (kat, nr),
            "antworten": ["Antwort eins %d" % nr, "Antwort zwei %d" % nr, "Antwort drei %d" % nr, "Antwort vier %d" % nr],
            "richtig": richtig, "wusstest": "Wusstest du, dass Test %d gut ist?" % nr, "schwierigkeit": schwierigkeit}


KATALOG = []
for s in qz.STUFEN:
    for i, kat in enumerate(qz.KATEGORIEN):
        for n in (1, 2):
            KATALOG.append(frage("%s-%s-%03d" % ("k" if s == "kind" else "e", qz.KURZ[kat], n), s, kat, i * 10 + n,
                                 "ABCD"[(i + n) % 4], 1 + (2 * i + n) % 5))

# ---------------------------------------------------------------- N: Namen fuer die festen Ansagen (konfigurierbar)
pruef("N1 Standard: keine Namen, keine Ansagen mit Namen", qz.FAMILIE == () and qz.KINDER == ()
      and not any(k.startswith(("dran_", "sieger_")) for k in qz.FEST) and qz.FEST == qz.FEST_DE)
pruef("N2 namen_laden ohne Datei: Standard", qz.namen_laden(T) == () and qz.FAMILIE == ())
os.makedirs(qz.ordner(T), exist_ok=True)
open(os.path.join(qz.ordner(T), qz.NAMEN), "w").write("{kaputt")
pruef("N3 kaputte Datei: Standard", qz.namen_laden(T) == ())
json.dump({"namen": "Anna", "kinder": []}, open(os.path.join(qz.ordner(T), qz.NAMEN), "w"))
pruef("N3b namen ohne Liste: Standard", qz.namen_laden(T) == ())
json.dump({"namen": ["Mia", "Ben", " anna ", "MIA", 7, "<>", " "], "kinder": ["mia", "Tom"]},
          open(os.path.join(qz.ordner(T), qz.NAMEN), "w"), ensure_ascii=False)
pruef("N4 namen.json: bereinigt, ohne Doppelte, Kinder nur aus der Liste", qz.namen_laden(T) == ("Mia", "Ben", "anna")
      and qz.KINDER == ("Mia",), (qz.FAMILIE, qz.KINDER))
pruef("N5 Ansagen je Name: Kind kindgerecht, Erwachsene sachlich",
      qz.FEST["dran_mia"] == "Mia, jetzt bist du dran!" and qz.FEST["dran_ben"] == "Ben, diese Frage ist für dich."
      and qz.FEST["sieger_mia"] == "Gewonnen hat Mia! Herzlichen Glückwunsch, das hast du toll gemacht!"
      and qz.FEST["sieger_anna"] == "Gewonnen hat anna! Herzlichen Glückwunsch!" and "dran_tom" not in qz.FEST)
pruef("N6 hoechstens MAX_NAMEN", len(qz.setze_namen(["N%d" % i for i in range(30)])) == qz.MAX_NAMEN)
pruef("N7 Schluessel passen zu ton_vorhanden (ein Name mit Umlaut, zwei Woerter)",
      qz.setze_namen(["Jörg", "Tante Ina"]) == ("Jörg", "Tante Ina") and "dran_joerg" in qz.FEST and "sieger_tante_ina" in qz.FEST)
qz.setze_namen(["Mia", "Ben", "Anna"], kinder=["Mia"])
os.remove(os.path.join(qz.ordner(T), qz.NAMEN))

# ---------------------------------------------------------------- Q: Logik
f0 = qz.frage_pruefen(KATALOG[0])
schlecht = []
for aenderung in ({"antworten": ["a", "b", "c"]}, {"antworten": ["a", "a", "b", "c"]}, {"richtig": "E"}, {"stufe": "baby"},
                  {"kategorie": "Quatsch"}, {"id": "X Y"}, {"frage": "kurz"}, {"schwierigkeit": 7}, {"schwierigkeit": "x"},
                  {"schwierigkeit": 0}, {"schwierigkeit": True}):
    try:
        qz.frage_pruefen(dict(KATALOG[0], **aenderung))
        schlecht.append(aenderung)
    except ValueError:
        pass
ohne_sw = dict(KATALOG[0])
del ohne_sw["schwierigkeit"]
pruef("Q1 Frage pruefen: gueltig bleibt, kaputte Formen abgelehnt, Schwierigkeit 1-5 (fehlt: 3)",
      f0["richtig"] == KATALOG[0]["richtig"] and not schlecht and f0["schwierigkeit"] == KATALOG[0]["schwierigkeit"]
      and qz.frage_pruefen(ohne_sw)["schwierigkeit"] == 3, schlecht)
pruef("Q1b Frage: Steuerzeichen und spitze Klammern raus", qz.frage_pruefen(dict(KATALOG[0], frage="Was <b>ist</b>\x07 das?"))["frage"]
      == "Was b ist /b das?")
sp, f1 = qz.spieler_lesen("Mia (kind), Ben und Anna")     # gemischte Stufen fuer die Spielmechanik-Tests unten
std, _ = qz.spieler_lesen("Mia, Ben und Anna")             # Standard: alle erwachsen
sp2, _ = qz.spieler_lesen([{"name": "mia", "stufe": "erwachsen"}, {"name": "Oma"}, "Mia"])
sp3, _ = qz.spieler_lesen(["Mia (erwachsen)", "Tom: kind"])
sp4, _ = qz.spieler_lesen(["Mia", "Ben"], {"mia": "kind"})
_, f4 = qz.spieler_lesen([])
_, f5 = qz.spieler_lesen(["a%d" % i for i in range(7)])
pruef("Q2 Spieler: ohne Angabe alle erwachsen, kind nur ausdruecklich, Angabe gewinnt, keine Doppelten, Grenzen",
      [(x["name"], x["stufe"]) for x in std] == [("Mia", "erwachsen"), ("Ben", "erwachsen"), ("Anna", "erwachsen")]
      and [(x["name"], x["stufe"]) for x in sp] == [("Mia", "kind"), ("Ben", "erwachsen"), ("Anna", "erwachsen")] and not f1
      and [(x["name"], x["stufe"]) for x in sp2] == [("Mia", "erwachsen"), ("Oma", "erwachsen")]
      and [(x["name"], x["stufe"]) for x in sp3] == [("Mia", "erwachsen"), ("Tom", "kind")]
      and [(x["name"], x["stufe"]) for x in sp4] == [("Mia", "kind"), ("Ben", "erwachsen")]
      and f4 == "Wer spielt mit? Zum Beispiel: Anna, Ben und Mia." and f5 == "Höchstens 6 Spieler.", (std, sp, sp2, sp3))
pruef("Q3 Kategorie aus freiem Text", qz.kategorie_finden("Tiere") == "Tiere" and qz.kategorie_finden("film und musik") == "Film & Musik"
      and qz.kategorie_finden("Erdkunde") == "Erdkunde" and qz.kategorie_finden("gemischt") is None and qz.kategorie_finden(None) is None
      and qz.kategorie_finden("Quantenchemie der Socken") is False and qz.kategorie_finden("Geografie") == "Erdkunde")
pruef("Q3b Stufe aus freiem Text", qz.stufe_finden("Kinder") == "kind" and qz.stufe_finden("leicht") == "kind"
      and qz.stufe_finden("Erwachsene") == "erwachsen" and qz.stufe_finden("schwer") == "erwachsen" and qz.stufe_finden("x") is None)
z, fehl = qz.neu(KATALOG, sp, None, 3, None, (), random.Random(1), jetzt=1000)
reihe = [s["fuer"] for s in z["fragen"]]
pruef("Q4 Reihum: abwechselnd, jeder Fragen seiner Stufe, keine Frage doppelt, Zeitbalken je Stufe, Tonweg",
      not fehl and reihe == ["Mia", "Ben", "Anna"] * 3
      and all(s["frage"]["stufe"] == ("kind" if s["fuer"] == "Mia" else "erwachsen") for s in z["fragen"])
      and len(set(s["frage"]["id"] for s in z["fragen"])) == 9 and z["fragen"][0]["sekunden"] == 45
      and z["fragen"][1]["sekunden"] == 30 and z["phase"] == "frage" and z["nr"] == 0 and z["ton"] == "auto"
      and z["seit"] == 1000, (reihe, fehl))
je_spieler = {n: [s["frage"]["schwierigkeit"] for s in z["fragen"] if s["fuer"] == n] for n in ("Mia", "Ben", "Anna")}
z5, _ = qz.neu(KATALOG, [x for x in sp if x["name"] == "Mia"], None, 5, None, (), random.Random(9))
pruef("Q4b Wie bei WWM: Runden steigen je Spieler von leicht nach schwer, Leiter und Runde im Zustand",
      all(v == sorted(v) and v[0] < v[-1] for v in je_spieler.values()) and z["runden"] == 3 and z["leiter"] == [1, 3, 5]
      and [qz.ziel_schwierigkeit(r, 5) for r in range(5)] == [1, 2, 3, 4, 5] and qz.ziel_schwierigkeit(0, 1) == 3
      and [s["frage"]["schwierigkeit"] for s in z5["fragen"]] == [1, 2, 3, 4, 5] and qz.runde(z) == 1
      and qz.runde(dict(z, nr=3)) == 2 and qz.runde(dict(z, nr=8)) == 3, (je_spieler, z.get("leiter")))
za, _ = qz.neu(KATALOG, sp, None, 2, "alle", (), random.Random(2))
erw, _ = qz.spieler_lesen("Ben, Anna")
zb, _ = qz.neu(KATALOG, erw, None, 4, "alle", (), random.Random(3), ton="leinwand")
pruef("Q5 Modus alle nur bei gleicher Stufe; sonst reihum mit Hinweis",
      za["modus"] == "reihum" and "reihum" in za["hinweis"] and zb["modus"] == "alle" and len(zb["fragen"]) == 4
      and all(s["fuer"] is None and s["frage"]["stufe"] == "erwachsen" for s in zb["fragen"]) and qz.erwartet(zb) == ["Ben", "Anna"]
      and zb["ton"] == "leinwand")
mia = [x for x in sp if x["name"] == "Mia"]
zc, _ = qz.neu(KATALOG, mia, "Tiere", 4, None, (), random.Random(4))
kats = [s["frage"]["kategorie"] for s in zc["fragen"]]
pruef("Q6 Kategorie zu klein: erst die Kategorie, dann ergaenzt, mit Hinweis", kats[:2] == ["Tiere", "Tiere"]
      and all(k != "Tiere" for k in kats[2:]) and len(kats) == 4 and "nicht genug" in zc["hinweis"], (kats, zc["hinweis"]))
kind_ids = [f["id"] for f in KATALOG if f["stufe"] == "kind"]
zd, _ = qz.neu(KATALOG, mia, None, 3, None, kind_ids[2:], random.Random(5))
ids = [s["frage"]["id"] for s in zd["fragen"]]
pruef("Q7 Gespielte zuletzt: erst die zwei neuen, dann gespielte mit Hinweis", set(ids[:2]) == set(kind_ids[:2])
      and ids[2] in kind_ids[2:] and "schon gespielte" in zd["hinweis"], (ids, zd["hinweis"]))
nur_kind = [f for f in KATALOG if f["stufe"] == "kind"][:3]
zk, _ = qz.neu(nur_kind, mia, None, 5, None, (), random.Random(6))
pruef("Q7b Leerer Katalog, keine passenden Fragen, zu wenige Fragen; Anzahl begrenzt",
      qz.neu([], sp)[1].startswith("Es gibt noch keine Quizfragen") and qz.neu(nur_kind, erw)[1] == "Für diese Spieler gibt es gerade keine passenden Fragen."
      and "Es reichen nur 3 Fragen." in zk["hinweis"] and len(qz.neu(KATALOG, mia, None, 99, None, (), random.Random(1))[0]["fragen"]) == 15
      and len(qz.neu(KATALOG, mia, None, "x", None, (), random.Random(1))[0]["fragen"]) == qz.STANDARD_ANZAHL)
# Antworten
s0 = qz.aktuell(z)
falsch_b = "ABCD"[("ABCD".index(s0["frage"]["richtig"]) + 1) % 4]
z_x, mx, dax = qz.antworten(z, "Ben", "A")
z_y, my, _ = qz.antworten(z, "Mia", "Quatsch")
z_w, mw_, _ = qz.antworten(z, "Fremder", "A")
z_1, m1, da1 = qz.antworten(z, "Mia", falsch_b)
gesprochen = {"A": "ah", "B": "be", "C": "tse", "D": "de"}[s0["frage"]["richtig"]]
z_2, m2, da2 = qz.antworten(z_1, "die Mia", "Antwort " + gesprochen)
text_b = qz.buchstabe_finden(s0["frage"]["antworten"][2], s0["frage"]["antworten"])
pruef("Q8 Antworten: falscher Spieler und unklarer Buchstabe aendern nichts, gesprochen, Antworttext, ueberschreiben",
      z_x is z and "für Mia" in mx and z_y is z and "A, B, C oder D" in my and da1 and z_1 is not z
      and z_2["fragen"][0]["antworten"] == {"Mia": s0["frage"]["richtig"]} and text_b == "C" and m1 == "Mia nimmt %s." % falsch_b
      and z["fragen"][0]["antworten"] == {} and "Es spielen Mia, Ben, Anna" in mw_, (mx, my, m2))
pruef("Q8b Buchstaben: eindeutig oder None", qz.buchstabe_finden("B") == "B" and qz.buchstabe_finden("b)") == "B"
      and qz.buchstabe_finden("ich nehme de") == "D" and qz.buchstabe_finden("Antwort") is None
      and qz.buchstabe_finden("eins", ["eins zwei", "eins drei", "vier", "fuenf"]) is None)
w0, mw = qz.weiter(z_2)
z_3, e3 = qz.aufloesen(z_2)
z_4, e4 = qz.aufloesen(z_3)
w1, mw1 = qz.weiter(z_4, jetzt=2000)
pruef("Q9 Aufloesen: +1, nicht doppelt, Ergebnis; weiter erst danach, dann naechste Frage mit neuer Zeit",
      [x["punkte"] for x in z_4["spieler"]] == [1, 0, 0] and e3["treffer"] == ["Mia"] and e4 == e3 and "noch offen" in mw
      and w0 is z_2 and not mw1 and w1["nr"] == 1 and w1["phase"] == "frage" and w1["seit"] == 2000
      and e3["text"] == s0["frage"]["antworten"]["ABCD".index(s0["frage"]["richtig"])], (e3, mw))
pruef("Q9a Nach dem Aufloesen keine Antwort mehr", "schon aufgelöst" in qz.antworten(z_3, "Mia", "A")[1])
zende = dict(w1, nr=len(w1["fragen"]) - 1)
zende["fragen"] = [dict(s, aufgeloest=True) for s in zende["fragen"]]
ze, _ = qz.weiter(zende)
pruef("Q9b Nach der letzten Frage: Ende; Sieger und Stand", ze["phase"] == "ende" and qz.sieger(ze) == ["Mia"]
      and qz.stand_text(ze) == "Mia 1, Ben 0, Anna 0." and qz.weiter(ze)[1] == "Es läuft gerade kein Quiz."
      and qz.antworten(ze, "Mia", "A")[1] == "Es läuft gerade kein Quiz." and qz.beenden(z)["phase"] == "ende"
      and qz.beenden({}) == {} and qz.sieger({}) == [])
a_vor = qz.anzeige(z_2)
a_nach = qz.anzeige(z_3)
a_ende = qz.anzeige(ze)
pruef("Q10 Anzeige: vor dem Aufloesen keine Loesung, nicht wer was gewaehlt hat; danach Loesung, Wahl, Ende mit Sieger",
      "richtig" not in a_vor and "wusstest" not in a_vor and all("wahl" not in x for x in a_vor["spieler"])
      and a_vor["spieler"][0]["hat"] and a_vor["spieler"][0]["dran"] and not a_vor["spieler"][1]["dran"]
      and a_nach["richtig"] == s0["frage"]["richtig"] and a_nach["spieler"][0]["ok"] and a_nach["wusstest"]
      and a_ende["phase"] == "ende" and a_ende["sieger"] == ["Mia"] and "frage" not in a_ende
      and a_vor["titel"] == "Familien-Quiz" and a_vor["unter"] == "Gemischt" and qz.anzeige(zc)["unter"] == "Tiere", (a_vor, a_nach))
URL = "https://jarvis.example.org/alexa/ton/" + "a" * 32 + ".mp3"
pruef("Q10b Anzeige: Ansage nur als https, seit 0 bleibt 0 (Uhr laeuft noch nicht)",
      qz.anzeige(dict(z_2, ton_url=URL, ton_ab=1234.5))["ton"] == URL
      and "ton" not in qz.anzeige(dict(z_2, ton_url="http://jarvis.local:8770/ton/x.mp3"))
      and qz.anzeige(dict(z_2, seit=0))["seit"] == 0)
alle_da = lambda s: True  # noqa: E731
keiner = lambda s: False  # noqa: E731
t_start = qz.ansage(z, "start")
st_s, tx_s = qz.ansage_planen(t_start, alle_da)
st_m, tx_m = qz.ansage_planen(t_start, lambda s: not s.endswith("-frage"))
st_d, _ = qz.ansage_planen(t_start, lambda s: s != "fest-dran_mia")
st_p, _ = qz.ansage_planen(t_start, lambda s: s != qz.PAUSE)
t_l = qz.ansage(z_3, "loesung", e3, random.Random(1))
z_falsch, e_falsch = qz.aufloesen(z_1)
t_lf = qz.ansage(z_falsch, "loesung", e_falsch, random.Random(1))
gleich = dict(ze, spieler=[dict(x, punkte=2) for x in ze["spieler"]])
zwei = dict(ze, spieler=[dict(ze["spieler"][0], punkte=2), dict(ze["spieler"][1], punkte=2), dict(ze["spieler"][2], punkte=0)])
pruef("Q11 Ansagen: Begruessung, dran, Frage, Zeit mit Pausen; Pflichtteil fehlt -> Jarvis-Text; Zusatz fehlt -> weg",
      st_s == ["fest-begruessung", qz.PAUSE, "fest-dran_mia", qz.PAUSE, s0["frage"]["id"] + "-frage", qz.PAUSE, "fest-zeit"]
      and st_m is None and s0["frage"]["frage"] in tx_m and "Mia, jetzt bist du dran!" in tx_m and "fest-dran_mia" not in st_d
      and qz.PAUSE not in st_p and qz.ansage_planen(t_start, keiner)[0] is None, (st_s, st_m, st_d))
pruef("Q11b Loesung mit Lob oder Trost, Ende mit Sieger, Gleichstand, Unentschieden",
      t_l[0][0].startswith("fest-richtig") and t_l[1][0].endswith("-loesung") and t_lf[0][0].startswith("fest-falsch")
      and [x[0] for x in qz.ansage(ze, "ende")] == ["fest-ende", "fest-sieger_mia", "fest-danke"]
      and qz.ansage(gleich, "ende")[1][0] == "fest-unentschieden" and qz.ansage(zwei, "ende")[1][0] == "fest-gleichstand"
      and "Richtig ist" in t_l[1][1] and s0["frage"]["wusstest"] in t_l[1][1], (t_l, t_lf))
tom, _ = qz.spieler_lesen("Tom")
zt, _ = qz.neu(KATALOG, tom + [x for x in erw], None, 1, None, (), random.Random(7))
zt_ende = dict(zt, phase="ende", spieler=[dict(zt["spieler"][0], punkte=3)] + zt["spieler"][1:])
pruef("Q11c Name ohne feste Ansage: dran als Zusatz mit Text, Sieger als Pflichtteil (dann Jarvis' Stimme)",
      ("fest-dran_tom", "Tom, diese Frage ist für dich.", False) in qz.ansage(zt, "start")
      and ("fest-sieger_tom", "Gewonnen hat Tom! Herzlichen Glückwunsch!", True) in qz.ansage(zt_ende, "ende")
      and qz.ansage_planen(qz.ansage(zt_ende, "ende"), lambda s: s != "fest-sieger_tom")[0] is None)
zl = dict(z, nr=len(z["fragen"]) - 1)
pruef("Q11d Letzte Frage angekuendigt, Modus alle ohne Namen", qz.ansage(zl, "frage")[0][0] == "fest-letzte"
      and qz.ansage(zb, "frage")[0][0] == "fest-alle" and qz.ansage(z, "loesung") == [] and qz.ansage({}, "start") == [])
pruef("Q11e Sprechtexte", qz.frage_sprechtext({"frage": "Wie?", "antworten": ["a.", "b", "c", "d"]}) == "Wie? A: a. B: b. C: c. D: d."
      and qz.loesung_sprechtext({"richtig": "C", "antworten": ["a", "b", "c.", "d"], "wusstest": ""}) == "Richtig ist C: c.")
qz.zustand_speichern(T, z_2)
open(os.path.join(qz.ordner(T), "kaputt.json"), "w").write("{")
qz.gespielt_merken(T, ["a", "b"])
qz.gespielt_merken(T, ["b", "c"])
pruef("Q12 Ablage: Spielstand, gespielt ohne Doppelte, kaputte Datei", qz.zustand_laden(T) == z_2
      and qz.gespielt_laden(T) == ["a", "b", "c"] and qz.zustand_laden(T + "/gibtsnicht") == {} and qz.katalog_laden(T) == [])
qz.katalog_speichern(T, KATALOG + [dict(KATALOG[0]), {"id": "kaputt"}])
pruef("Q12b Katalog: speichern/laden, Doppelte und Kaputtes fallen still weg", qz.katalog_laden(T) == [qz.frage_pruefen(f) for f in KATALOG]
      and qz.zaehlen(qz.katalog_laden(T))[("kind", "Tiere")] == 2)
with qz.sperre(T):
    pruef("Q12c Sperre legt die Sperrdatei an", os.path.exists(os.path.join(qz.ordner(T), "spiel.lock")))
os.makedirs(os.path.join(qz.ordner(T), qz.TON), exist_ok=True)
open(qz.ton_pfad(T, "fest-zeit"), "wb").write(b"\0" * 500)
open(qz.ton_pfad(T, "fest-kurz"), "wb").write(b"\0" * 100)
pruef("Q12d Ton vorhanden: Name geprueft, Datei gross genug", qz.ton_vorhanden(T, "fest-zeit") and not qz.ton_vorhanden(T, "fest-kurz")
      and not qz.ton_vorhanden(T, "../fest-zeit") and not qz.ton_vorhanden(T, "fehlt"))
pruef("Q12e Doppelte Fragen erkennen", qz.aehnlich("Wie viele Beine hat eine Spinne?", "Wie viele Beine hat eine Spinne eigentlich?")
      and not qz.aehnlich("Wie heisst die Hauptstadt von Frankreich?", "Wie viele Beine hat eine Spinne?"))
os.remove(os.path.join(qz.ordner(T), qz.SPIEL))
os.remove(os.path.join(qz.ordner(T), qz.GESPIELT))


def ton_muster(teile, rate=24000):
    """PCM 16 bit mono: [(laut?, sekunden)] als Sinus bzw. Stille."""
    out = bytearray()
    for laut, sek in teile:
        n = int(rate * sek)
        out += b"".join(struct.pack("<h", int((9000 if laut else 0) * math.sin(2 * math.pi * 220 * i / rate))) for i in range(n))
    return bytes(out)


SPRACHE = [(1, .9), (0, .15), (1, .5), (0, .8), (1, .4), (0, .55), (1, .5), (0, .5), (1, .45), (0, .5), (1, .4)]
pcm_t = ton_muster(SPRACHE)
teile_t = qz.pausen_teile(pcm_t, 24000)
huelle_t = qz.huelle(pcm_t, 24000)
erwartet_t = [round(sum(d for _, d in SPRACHE[:k]), 2) for k in (4, 6, 8, 10)]
pruef("Q13 Ton auswerten: Beginn von A-D nach den vier langen Pausen (kurze Wortpause zaehlt nicht), Huellkurve 20/s",
      teile_t is not None and all(abs(a_ - b_) <= 0.03 for a_, b_ in zip(teile_t, erwartet_t))
      and len(huelle_t) == int(math.ceil(len(pcm_t) / 2 / 24000.0 * 20)) and set(huelle_t) <= set("0123456789abcdef")
      and huelle_t[2] > "a" and huelle_t[int(1.8 * 20)] == "0" and qz.pausen_teile(ton_muster([(1, 2)]), 24000) is None
      and qz.huelle(b"", 24000) == "", (teile_t, erwartet_t, huelle_t[:40]))
z_t = dict(z_2, takt={"auf_ab": 100.0, "antw_ab": [101.0, 102.0, 103.0, 104.0], "mund": "0f0f", "mund_hz": 20, "mund_ab": 100.5,
                      "unbekannt": 1})
a_t = qz.anzeige(z_t)
pruef("Q14 Anzeige mit Zeitmarken, Runde, Leiter, Schwierigkeit und Schluessel je Frage und Phase",
      a_t["auf_ab"] == 100.0 and a_t["antw_ab"] == [101.0, 102.0, 103.0, 104.0] and a_t["mund"] == "0f0f"
      and a_t["mund_ab"] == 100.5 and "unbekannt" not in a_t and a_t["runde"] == 1 and a_t["runden"] == 3
      and a_t["leiter"] == [1, 3, 5] and a_t["schwierigkeit"] == s0["frage"]["schwierigkeit"]
      and a_t["schluessel"] == "%s:0:frage" % z_2["id"] and "aufdecken_ab" not in a_t, a_t)


# ---------------------------------------------------------------- F: Fangfragen
def frage_f(fid, stufe, kat, nr, sw, fang=False, typ=None):
    f = {"id": fid, "stufe": stufe, "kategorie": kat, "frage": "Testfrage %s Nummer %d?" % (kat, nr),
         "antworten": ["Antwort eins %d" % nr, "Antwort zwei %d" % nr, "Antwort drei %d" % nr, "Antwort vier %d" % nr],
         "richtig": "ABCD"[nr % 4], "wusstest": "Wusstest du, dass Test %d gut ist?" % nr, "schwierigkeit": sw}
    if fang:
        f["fang"] = True
        if typ:
            f["typ"] = typ
    return f


# Normaler Katalog: je Stufe und Kategorie 6 Fragen, Schwierigkeit 1-5 verteilt
NORMAL = []
for s in qz.STUFEN:
    for i, kat in enumerate(qz.KATEGORIEN):
        for n in range(6):
            NORMAL.append(frage_f("%s-%s-%03d" % (s[0], qz.KURZ[kat], n), s, kat, i * 10 + n, 1 + (i + n) % 5))
# Fangfragen: je Stufe 30 Stueck in Allgemeinwissen, Tiere, Essen (keine in Sport), Schwierigkeit 1-3
FANG = []
for s in qz.STUFEN:
    for j in range(30):
        kat = ("Allgemeinwissen", "Tiere", "Essen")[j % 3]
        FANG.append(frage_f("%s-fang-%s-%03d" % (s[0], qz.KURZ[kat], j), s, kat, 500 + j, 1 + j % 3, True,
                            qz.FANG_TYPEN[j % 3]))
MIT = [qz.frage_pruefen(f) for f in NORMAL + FANG]
OHNE = [qz.frage_pruefen(f) for f in NORMAL]
FANG_IDS = set(f["id"] for f in FANG)
ist_fang = lambda f: f["id"] in FANG_IDS  # noqa: E731


def spieler(*namen):
    return [{"name": n, "stufe": "erwachsen", "punkte": 0} for n in namen]


f_ok = qz.frage_pruefen(FANG[0])
f_ohne_typ = qz.frage_pruefen(dict(FANG[0], typ=None))
f_normal = qz.frage_pruefen(NORMAL[0])
f_kein_bool = qz.frage_pruefen(dict(NORMAL[0], fang="ja", typ="falle"))
try:
    qz.frage_pruefen(dict(FANG[0], typ="quatsch"))
    falscher_typ = False
except ValueError:
    falscher_typ = True
pruef("F1 Katalog: fang und typ bleiben, typ fehlt -> falle, falscher typ abgelehnt, normale Fragen ohne Feld",
      f_ok.get("fang") is True and f_ok.get("typ") == qz.FANG_TYPEN[0] and f_ohne_typ.get("typ") == "falle"
      and falscher_typ and "fang" not in f_normal and "typ" not in f_normal and "fang" not in f_kein_bool,
      (f_ok, f_ohne_typ, f_normal, f_kein_bool))


def ziehen_alt(katalog, sp_, kategorie, anzahl, modus, gespielt=(), zufall=None):
    """Der Algorithmus vor den Fangfragen (04.11.2026), unveraendert zum Vergleich."""
    zufall = zufall or random.Random()
    gespielt = set(gespielt or ())
    genommen, hinweise = set(), []

    def eine(stufe, ziel):
        stufen = [f for f in katalog if f["stufe"] == stufe and f["id"] not in genommen]
        for pool, merke in (([f for f in stufen if (not kategorie or f["kategorie"] == kategorie) and f["id"] not in gespielt], None),
                            ([f for f in stufen if f["id"] not in gespielt], "andere Kategorien"),
                            ([f for f in stufen if not kategorie or f["kategorie"] == kategorie], "schon gespielte"),
                            (stufen, "schon gespielte")):
            if pool:
                if merke and merke not in hinweise and (kategorie or merke == "schon gespielte"):
                    hinweise.append(merke)
                abstand = min(abs(f.get("schwierigkeit", 3) - ziel) for f in pool)
                f = zufall.choice([f for f in pool if abs(f.get("schwierigkeit", 3) - ziel) == abstand])
                genommen.add(f["id"])
                return f
        return None

    slots = []
    for runde_ in range(anzahl):
        ziel = qz.ziel_schwierigkeit(runde_, anzahl)
        if modus == "alle":
            f = eine(sp_[0]["stufe"], ziel)
            if not f:
                break
            slots.append({"fuer": None, "frage": f})
        else:
            for s_ in sp_:
                f = eine(s_["stufe"], ziel)
                if not f:
                    break
                slots.append({"fuer": s_["name"], "frage": f})
            else:
                continue
            break
    if modus != "alle":
        voll = len(slots) - len(slots) % len(sp_)
        slots = slots[:voll]
    h = ""
    if "andere Kategorien" in hinweise:
        h = "In der Kategorie %s gab es nicht genug neue Fragen, ich habe mit anderen ergänzt." % kategorie
    elif "schon gespielte" in hinweise:
        h = "Es sind auch schon gespielte Fragen dabei, der Vorrat an neuen ist aufgebraucht."
    return slots, h


abweichung = []
gespielt_teil = [f["id"] for f in OHNE[::3]]
for seed in range(120):
    for sp_, kat, anzahl, modus, gesp in ((spieler("Anna", "Ben"), None, 5, "reihum", ()),
                                          ([{"name": "Mia", "stufe": "kind", "punkte": 0}] + spieler("Anna"), "Sport", 6,
                                           "reihum", gespielt_teil),
                                          (spieler("Anna", "Ben", "Mia"), "Tiere", 15, "alle", gespielt_teil),
                                          (spieler("Anna"), None, 15, "reihum", [f["id"] for f in OHNE])):
        z1, z2 = random.Random(seed), random.Random(seed)
        a, ha = ziehen_alt(OHNE, sp_, kat, anzahl, modus, gesp, z1)
        n, hn = qz.ziehen(OHNE, sp_, kat, anzahl, modus, gesp, z2)
        if ([(s_["fuer"], s_["frage"]["id"]) for s_ in a] != [(s_["fuer"], s_["frage"]["id"]) for s_ in n] or ha != hn
                or z1.random() != z2.random()):
            abweichung.append((seed, kat, modus))
pruef("F2 Ohne Fangfragen im Katalog: Auswahl, Hinweise und Zufallsfolge exakt wie vorher (480 Spiele)",
      not abweichung, abweichung[:5])
r1_ohne, ungleich = [], []
for seed in range(200):
    slots, _ = qz.ziehen(MIT, spieler("Anna", "Ben", "Mia"), None, 5, "reihum", (), random.Random(seed))
    for r in range(5):
        runde_ = slots[r * 3:(r + 1) * 3]
        arten = set(ist_fang(s_["frage"]) for s_ in runde_)
        if len(arten) != 1:
            ungleich.append((seed, r))
        if r == 0 and arten != {True}:
            r1_ohne.append(seed)
pruef("F3 Runde 1 beginnt immer mit einer Fangfrage, und in jeder Runde bekommen alle dieselbe Art (200 Spiele, 3 Spieler)",
      not r1_ohne and not ungleich, (r1_ohne[:5], ungleich[:5]))
zaehl = [0] * 5
N = 3000
for seed in range(N):
    slots, _ = qz.ziehen(MIT, spieler("Anna"), None, 5, "reihum", (), random.Random(10000 + seed))
    for r, s_ in enumerate(slots):
        zaehl[r] += ist_fang(s_["frage"])
anteil = [round(x / N, 3) for x in zaehl]
pruef("F4 Anteile je Runde: 1 -> 100 %, 2 -> etwa 50 %, ab 3 -> etwa 20 % (3000 Spiele)",
      anteil[0] == 1.0 and abs(anteil[1] - 0.5) < 0.04 and all(abs(a - 0.2) < 0.03 for a in anteil[2:]), anteil)
sport, h_sport = qz.ziehen(MIT, spieler("Anna"), "Sport", 3, "reihum", (), random.Random(3))
tiere, h_tiere = qz.ziehen(MIT, spieler("Anna"), "Tiere", 3, "reihum", (), random.Random(3))
pruef("F5 Kategorie: ohne Fangfragen darin normale Fragen der Kategorie ohne Hinweis; sonst die Fangfrage aus der Kategorie",
      all(s_["frage"]["kategorie"] == "Sport" and not ist_fang(s_["frage"]) for s_ in sport) and h_sport == ""
      and ist_fang(tiere[0]["frage"]) and tiere[0]["frage"]["kategorie"] == "Tiere" and h_tiere == "",
      ([s_["frage"]["id"] for s_ in sport], h_sport, [s_["frage"]["id"] for s_ in tiere], h_tiere))
alle_fang_gespielt = [f["id"] for f in FANG]
wieder = []
for seed in range(100):
    slots, h = qz.ziehen(MIT, spieler("Anna", "Ben"), None, 5, "reihum", alle_fang_gespielt, random.Random(seed))
    if any(ist_fang(s_["frage"]) for s_ in slots) or h:
        wieder.append((seed, h))
teil = alle_fang_gespielt[:-2]
rest, _ = qz.ziehen(MIT, spieler("Anna", "Ben"), None, 5, "reihum", teil, random.Random(1))
frei = [s_["frage"]["id"] for s_ in rest if ist_fang(s_["frage"])]
pruef("F6 Gespielte Fangfragen nicht wieder (statt dessen normale, ohne Hinweis); die letzten freien werden noch genommen",
      not wieder and all(i in alle_fang_gespielt[-2:] for i in frei), (wieder[:5], frei))
alt_anteil = qz.FANG_ANTEIL
qz.FANG_ANTEIL = (0.0, 0.0, 0.0)
ohne_fang = []
for seed in range(100):
    slots, _ = qz.ziehen(MIT, spieler("Anna", "Ben"), None, 10, "reihum", (), random.Random(seed))
    ohne_fang += [s_["frage"]["id"] for s_ in slots if ist_fang(s_["frage"])]
nur_fang = [f for f in MIT if f["stufe"] == "erwachsen" and ist_fang(f)] + [f for f in MIT if f["stufe"] == "kind"]
notfall, _ = qz.ziehen(nur_fang, spieler("Anna"), None, 3, "reihum", (), random.Random(2))
qz.FANG_ANTEIL = alt_anteil
pruef("F7 Ohne Fang-Runde keine Fangfrage aus den normalen Ziehungen; gibt es nur noch Fangfragen, kommen die trotzdem",
      not ohne_fang and len(notfall) == 3, (ohne_fang[:5], len(notfall)))
alle, _ = qz.ziehen(MIT, spieler("Anna", "Ben"), None, 5, "alle", (), random.Random(4))
kind, _ = qz.ziehen(MIT, [{"name": "Mia", "stufe": "kind", "punkte": 0}], None, 5, "reihum", (), random.Random(4))
pruef("F8 Modus alle und Kinderstufe: Runde 1 ist eine Fangfrage der richtigen Stufe",
      ist_fang(alle[0]["frage"]) and alle[0]["fuer"] is None and alle[0]["frage"]["stufe"] == "erwachsen"
      and ist_fang(kind[0]["frage"]) and kind[0]["frage"]["stufe"] == "kind",
      (alle[0]["frage"]["id"], kind[0]["frage"]["id"]))
zf, fehl_f = qz.neu(MIT, spieler("Anna"), None, 3, None, (), random.Random(5), jetzt=1000)
vor = qz.anzeige(zf, jetzt=1000)
pruef("F9 Vor dem Aufloesen: Leinwand-Inhalt und Ansage ohne Hinweis auf eine Fangfrage",
      not fehl_f and ist_fang(qz.aktuell(zf)["frage"]) and "fang" not in vor and "typ" not in vor
      and "Fang" not in json.dumps(vor, ensure_ascii=False)
      and "Fang" not in " ".join(t_ for _, t_, _ in qz.ansage(zf, "start")), vor)

# ---------------------------------------------------------------- Englisch
qz.setze_sprache("en")
pruef("EN: feste Ansagen und Namen neu gebaut", qz.FEST["zeit"] == "The clock is ticking!" and qz.FEST["dran_mia"] == "Mia, it's your turn now!"
      and qz.FEST["dran_ben"] == "Ben, this question is for you." and qz.FEST["sieger_mia"] == "Mia wins! Congratulations, you did great!"
      and qz.FEST["sieger_anna"] == "Anna wins! Congratulations!" and set(qz.FEST_EN) <= set(qz.FEST)
      and set(qz.FEST_EN) == set(qz.FEST_DE))
pruef("EN: Ansage, unbekannter Name, Loesung", "Welcome to the family quiz show!" in qz.ansage_planen(qz.ansage(z, "start"), alle_da)[1]
      and ("fest-dran_tom", "Tom, this question is for you.", False) in qz.ansage(zt, "start")
      and ("fest-sieger_tom", "Tom wins! Congratulations!", True) in qz.ansage(zt_ende, "ende")
      and qz.loesung_sprechtext({"richtig": "A", "antworten": ["x", "y", "z", "w"], "wusstest": "Fun."}) == "The correct answer is A: x. Fun.")
pruef("EN: Meldungen", qz.spieler_lesen([])[1] == "Who is playing? For example: Anna, Ben and Mia."
      and qz.spieler_lesen(["a%d" % i for i in range(7)])[1] == "At most 6 players."
      and qz.neu([], sp)[1].startswith("There are no quiz questions yet") and qz.weiter(z_2)[1].startswith("The question is still open")
      and qz.weiter(ze)[1] == "No quiz is running right now." and qz.antworten(z, "Ben", "A")[1] == "This question is for Mia. Ben is up next."
      and qz.antworten(z, "Mia", "x")[1] == "Which answer does Mia mean? Please A, B, C or D."
      and qz.antworten(z, "Mia", "B")[1] == "Mia takes B." and "already resolved" in qz.antworten(z_3, "Mia", "A")[1])
zc_en, _ = qz.neu(KATALOG, mia, "Tiere", 4, None, (), random.Random(4))
za_en, _ = qz.neu(KATALOG, sp, None, 2, "alle", (), random.Random(2))
pruef("EN: Hinweise und Anzeige", "category Animals" in zc_en["hinweis"] and "in turns" in za_en["hinweis"]
      and qz.anzeige(zc_en)["unter"] == "Animals" and qz.anzeige(z)["unter"] == "Mixed" and qz.anzeige(z)["titel"] == "Family Quiz",
      (zc_en["hinweis"], za_en["hinweis"]))
pruef("EN: Katalog bleibt Daten (Kategorie deutsch gespeichert)", zc_en["kategorie"] == "Tiere"
      and all(k in qz.KATEGORIE_EN for k in qz.KATEGORIEN))
try:
    qz.setze_sprache("fr")
    pruef("Sprache: nur de oder en", False)
except ValueError:
    pruef("Sprache: nur de oder en", qz.SPRACHE == "en")
qz.setze_sprache("de")
pruef("DE wieder: FEST deutsch mit Namen", qz.FEST["zeit"] == "Die Zeit läuft!" and qz.FEST["dran_mia"] == "Mia, jetzt bist du dran!")

shutil.rmtree(T, ignore_errors=True)
print("Quiz: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
