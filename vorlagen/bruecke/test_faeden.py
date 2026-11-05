#!/usr/bin/env python3
"""Baustein faeden.py (offene Faeden, "Jarvis fasst nach", seit 0.6): Anlegen und Doppelte, Faelligkeit, hoechstens ein
Nachfassen je Faden und Tag, Tagesgrenze (Standard 1, per Zuruf), abschliessende Frage vor dem Verfall ("fallen
lassen?", Ja-Knopf), Verfall (einstellbar), Nachtruhe, keine Faeden ueber Echos/HA-Sprache, jede Person nur ihre
eigenen, Push nur auf Wunsch, Marke, Texte auf Deutsch und Englisch.
Testordner statt echter Daten, keine Netzzugriffe."""
import datetime as dt
import os
import stat
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import faeden as fd  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:220]) if info and not bed else ""))


T = tempfile.mkdtemp(prefix="faeden-")


def leeren():
    if os.path.exists(os.path.join(T, fd.DATEI)):
        os.remove(os.path.join(T, fd.DATEI))


MO = dt.datetime(2026, 11, 2, 10, 0)          # Montag
DI = MO + dt.timedelta(days=1)
MI = MO + dt.timedelta(days=2)

# ---------------------------------------------------------------- anlegen, Doppelte, Faelligkeit
leeren()
n1 = fd.neu(T, "mia", "Mia will den Handwerker wegen der Heizung anrufen.", None, "vorhaben", "werkzeug", MO)
pruef("Anlegen gibt Nummer", n1 == 1, n1)
pruef("Datei privat (600)", stat.S_IMODE(os.stat(os.path.join(T, fd.DATEI)).st_mode) == 0o600)
pruef("Doppelt (aehnlich) wird nicht angelegt",
      fd.neu(T, "mia", "Mia will den Handwerker wegen der Heizung anrufen", jetzt=MO) == 0)
pruef("Zu kurz wird nicht angelegt", fd.neu(T, "mia", "ab", jetzt=MO) == 0)
f = fd.offen(T, "mia", MO)[0]
pruef("Ohne Faelligkeit: naechster Tag", f["faellig"] == "2026-11-03" and f["quelle"] == "werkzeug", f)
n_m = fd.neu(T, "mia", "Mia will ⟦faden: 1⟧ die\x07 Garage   aufräumen.", "2026-11-05", "unsinn", jetzt=MO)
gm = [x for x in fd.alle(T, "mia") if x["id"] == n_m][0]
pruef("Marken und Steuerzeichen werden aus dem Text entfernt, unbekannte art -> vorhaben",
      gm["text"] == "Mia will die Garage aufräumen." and gm["art"] == "vorhaben", gm)
fd.schliessen(T, "mia", n_m, "verworfen", MO)
n_alt = fd.neu(T, "mia", "Mia wollte gestern schon die Steuer machen.", "2026-10-01", jetzt=MO)
pruef("Faelligkeit in der Vergangenheit: morgen", [x for x in fd.offen(T, "mia", MO) if x["id"] == n_alt][0]["faellig"]
      == "2026-11-03")
pruef("Am Anlagetag noch nichts faellig", fd.zum_nachfassen(T, "mia", MO) is None)
x = fd.zum_nachfassen(T, "mia", DI)
pruef("Am Folgetag faellig, aelteste Nummer zuerst", x and x["id"] == n1, x)

# ---------------------------------------------------------------- hoechstens ein Nachfassen je Faden und Tag
pruef("Nachgefragt zaehlt", fd.gefragt(T, "mia", n1, DI) is True)
pruef("Zweites Nachfragen am selben Tag nicht", fd.gefragt(T, "mia", n1, DI) is False)
e = fd.einstellungen(T, "mia")
pruef("Standard: 1 Faden je Tag, Push aus um 18 Uhr, Verfall 14, Nachfassen an",
      (e["je_tag"], e["push"], e["push_stunde"], e["verfall_tage"], e["nachfassen"]) == (1, "aus", 18, 14, "an"), e)
pruef("Andere Person: Standard ebenso", fd.einstellungen(T, "ben")["nachfassen"] == "an"
      and fd.einstellungen(T, "ben")["je_tag"] == 1)
pruef("Tagesgrenze 1: danach kein zweiter Faden", fd.zum_nachfassen(T, "mia", DI) is None)
x = fd.zum_nachfassen(T, "mia", MI)
pruef("Naechster Tag: der andere Faden", x and x["id"] == n_alt, x)
fd.einstellen(T, "mia", je_tag=2)
x = fd.zum_nachfassen(T, "mia", DI)
pruef("je_tag 2: am selben Tag noch einer", x and x["id"] == n_alt, x)
fd.gefragt(T, "mia", n_alt, DI)
fd.neu(T, "mia", "Mia will die Winterreifen bestellen.", "2026-11-03", jetzt=MO)
pruef("je_tag 2: der dritte nicht mehr", fd.zum_nachfassen(T, "mia", DI) is None)
fd.einstellen(T, "mia", je_tag=1)

# ---------------------------------------------------------------- Angebote ohne Nachfrage begrenzt
leeren()
n = fd.neu(T, "mia", "Mia will die Winterreifen bestellen.", "2026-11-02", jetzt=MO)
angebote = [fd.zum_nachfassen(T, "mia", MO) for _ in range(fd.ANGEBOTEN_MAX + 2)]
pruef("Angebot hoechstens %d mal am Tag" % fd.ANGEBOTEN_MAX,
      sum(1 for a in angebote if a) == fd.ANGEBOTEN_MAX, [bool(a) for a in angebote])
pruef("Am naechsten Tag wieder angeboten", fd.zum_nachfassen(T, "mia", DI) is not None)

# ---------------------------------------------------------------- abschliessende Frage vor dem Verfall
leeren()
n = fd.neu(T, "mia", "Mia will die Winterreifen bestellen.", "2026-11-02", jetzt=MO)
for i in range(fd.NACHFRAGEN_MAX):
    x = fd.zum_nachfassen(T, "mia", MO + dt.timedelta(days=i))
    pruef("Nachfrage %d: Phase nachfassen" % (i + 1), x and x["phase"] == "nachfassen", x)
    fd.gefragt(T, "mia", n, MO + dt.timedelta(days=i), x["phase"])
x = fd.zum_nachfassen(T, "mia", MO + dt.timedelta(days=5))
pruef("Nach %d Nachfragen: abschliessende Frage" % fd.NACHFRAGEN_MAX, x and x["phase"] == "abschluss", x)
k = fd.kontext_text(x, "Mia", MO + dt.timedelta(days=5))
pruef("Abschluss-Hinweis: fallen lassen, Verfallsdatum, Marke", "fallen lassen" in k and "16.11." in k
      and "⟦faden: %d⟧" % n in k and "seit 02.11." in k, k)
pruef("Abschluss-Knopf", fd.knopf_text(x) == "Fallen lassen: Mia will die Winterreifen bestellen", fd.knopf_text(x))
pruef("Phase wird nicht gespeichert", "phase" not in fd.alle(T, "mia")[0] and "verfaellt" not in fd.alle(T, "mia")[0])
fd.gefragt(T, "mia", n, MO + dt.timedelta(days=5), "abschluss")
pruef("Abschluss nur einmal gefragt", fd.zum_nachfassen(T, "mia", MO + dt.timedelta(days=6)) is None)
pruef("... Faden bleibt bis zur Frist in der Liste", len(fd.offen(T, "mia", MO + dt.timedelta(days=6))) == 1)
leeren()
n = fd.neu(T, "mia", "Mia will die Winterreifen bestellen.", "2026-11-02", jetzt=MO)
fd.gefragt(T, "mia", n, MO)
x = fd.zum_nachfassen(T, "mia", dt.datetime(2026, 11, 13, 10))
pruef("Auch ohne 3 Nachfragen: %d Tage vor dem Verfall kommt die Abschlussfrage" % fd.ABSCHLUSS_VORLAUF,
      x and x["phase"] == "abschluss", x)
x = fd.zum_nachfassen(T, "mia", dt.datetime(2026, 11, 11, 10))
pruef("... vorher noch normale Nachfrage", x and x["phase"] == "nachfassen", x)
fd.gefragt(T, "mia", n, dt.datetime(2026, 11, 13, 10), "abschluss")
f = fd.verschieben(T, "mia", n, "2026-11-20", dt.datetime(2026, 11, 13, 11))
pruef("Noch wichtig -> verschieben setzt Nachfragen und Abschluss zurueck",
      f and not f.get("gefragt") and "abschluss_gefragt" not in f, f)
x = fd.zum_nachfassen(T, "mia", dt.datetime(2026, 11, 20, 10))
pruef("... und wird am neuen Tag wieder normal nachgefragt", x and x["phase"] == "nachfassen", x)
try:
    fd.verschieben(T, "mia", n, "2026-11-01", dt.datetime(2026, 11, 13, 11))
    pruef("Verschieben in die Vergangenheit abgelehnt", False)
except fd.Fehler as ex:
    pruef("Verschieben in die Vergangenheit abgelehnt", "JJJJ-MM-TT" in str(ex), ex)
leeren()
n = fd.neu(T, "mia", "Mia will die Winterreifen bestellen.", "2026-11-02", jetzt=MO)
fd.gefragt(T, "mia", n, dt.datetime(2026, 11, 13, 10), "abschluss")
pruef("Verfall Standard 14 Tage nach Faelligkeit: am 16.11. noch offen",
      len(fd.offen(T, "mia", dt.datetime(2026, 11, 16, 12))) == 1)
pruef("... am 17.11. nicht mehr", fd.offen(T, "mia", dt.datetime(2026, 11, 17, 12)) == [])
v, weg = fd.pflegen(T, dt.datetime(2026, 11, 17, 12))
pruef("pflegen markiert verfallen", v == 1 and fd.alle(T, "mia")[0]["status"] == "verfallen", (v, fd.alle(T, "mia")))
v, weg = fd.pflegen(T, dt.datetime(2027, 2, 1, 12))
pruef("pflegen entfernt alte Geschlossene", weg == 1 and fd.alle(T, "mia") == [], (v, weg))
leeren()
fd.einstellen(T, "mia", verfall_tage=3)
fd.neu(T, "mia", "Mia will die Winterreifen bestellen.", "2026-11-02", jetzt=MO)
pruef("Verfall einstellbar (3 Tage)", fd.offen(T, "mia", dt.datetime(2026, 11, 6, 9)) == [])
for falsch in ({"verfall_tage": 0}, {"verfall_tage": 400}, {"push": "vielleicht"}, {"je_tag": "viel"}, {"unbekannt": 1}, {}):
    try:
        fd.einstellen(T, "mia", **falsch)
        pruef("Ungueltige Einstellung abgelehnt %s" % falsch, False)
    except fd.Fehler:
        pruef("Ungueltige Einstellung abgelehnt %s" % falsch, True)
pruef("Einstellung ja/nein wird an/aus", fd.einstellen(T, "mia", push="ja")["push"] == "an"
      and fd.einstellen(T, "mia", push="nein")["push"] == "aus")
fd.einstellen(T, "mia", nachfassen="aus", verfall_tage=14)
pruef("Nachfassen aus: nichts angeboten", fd.zum_nachfassen(T, "mia", DI) is None)
fd.einstellen(T, "mia", nachfassen="an")

# ---------------------------------------------------------------- Nachtruhe und Quellen
leeren()
fd.neu(T, "mia", "Mia will die Winterreifen bestellen.", "2026-11-02", jetzt=MO)
pruef("Nachtruhe: nichts angeboten", fd.zum_nachfassen(T, "mia", MO, nachtruhe=True) is None)
fd.einstellen(T, "mia", push="an", push_stunde=18)
pruef("Push: nicht in der Nachtruhe", fd.fuer_push(T, ["mia"], dt.datetime(2026, 11, 2, 23), nachtruhe=True) == [])
pruef("Quellen, bei denen jeder mithoert, gesperrt", all(fd.quelle_gesperrt(q) for q in (
    "alexa", "test-alexa", "ha", "test-ha", "voice", "voice-pe", "alexa-kueche", "ha-satellit", "HA")))
pruef("App, PC und Web-App frei", not any(fd.quelle_gesperrt(q) for q in ("app", "app-extern", "webapp", "pc", "test-app", "")))

# ---------------------------------------------------------------- jede Person nur ihre eigenen
leeren()
np = fd.neu(T, "mia", "Mia will den Handwerker wegen der Heizung anrufen.", "2026-11-02", jetzt=MO)
nb = fd.neu(T, "ben", "Ben will das Geschenk für Oma bestellen.", "2026-11-02", jetzt=MO)
pruef("Ben sieht nur seine", [f["id"] for f in fd.offen(T, "ben", MO)] == [nb])
pruef("Ben kann Mias Faden nicht schliessen (Nummer)", fd.schliessen(T, "ben", np, jetzt=MO) is None)
pruef("Ben kann Mias Faden nicht schliessen (Stichwort)", fd.schliessen(T, "ben", "Handwerker", jetzt=MO) is None)
pruef("Ben kann Mias Faden nicht als gefragt markieren", fd.gefragt(T, "ben", np, MO) is False)
pruef("Ben kann Mias Faden nicht verschieben", fd.verschieben(T, "ben", np, "2026-11-20", MO) is None)
r = fd.schliessen(T, "ben", "Geschenk", jetzt=MO)
pruef("Ben hakt eigenen per Stichwort ab", r and r["status"] == "erledigt" and fd.offen(T, "ben", MO) == [], r)
try:
    fd.schliessen(T, "mia", np, "geloescht", MO)
    pruef("Status nur erledigt oder verworfen", False)
except fd.Fehler:
    pruef("Status nur erledigt oder verworfen", True)
L = [{"id": 12, "text": "Winterreifen bestellen"}, {"id": 13, "text": "Winterjacke kaufen"}]
pruef("Finden: Nummer in mehreren Schreibweisen", all(fd.finden(L, w)["id"] == 12 for w in (12, "12", "Nr. 12", "nr12", "#12")))
pruef("Finden: Stichwort nur eindeutig, nicht zu kurz", fd.finden(L, "reifen")["id"] == 12 and fd.finden(L, "winter") is None
      and fd.finden(L, "ja") is None and fd.finden(L, 99) is None)
leeren()
for i in range(fd.OFFEN_MAX):
    fd.neu(T, "tom", "Tom will Aufgabe Nummer %03d erledigen." % i, jetzt=MO)
try:
    fd.neu(T, "tom", "Tom will noch etwas ganz anderes tun.", jetzt=MO)
    pruef("Hoechstens %d offene je Person" % fd.OFFEN_MAX, False)
except fd.Fehler as ex:
    pruef("Hoechstens %d offene je Person" % fd.OFFEN_MAX, "Schon %d offene Fäden" % fd.OFFEN_MAX in str(ex), ex)

# ---------------------------------------------------------------- Push nur auf Wunsch
leeren()
for p_, name in (("mia", "Mia"), ("ben", "Ben")):
    fd.einstellen(T, p_, push="aus")
    fd.neu(T, p_, "%s will etwas Wichtiges erledigen." % name, "2026-11-02", jetzt=MO)
pruef("Ohne Wunsch: kein Push", fd.fuer_push(T, ["mia", "ben"], dt.datetime(2026, 11, 2, 19)) == [])
fd.einstellen(T, "mia", push="an", push_stunde=18)
fd.einstellen(T, "ben", push="an", push_stunde=20)
pruef("Vor der Push-Stunde: nichts", fd.fuer_push(T, ["mia", "ben"], dt.datetime(2026, 11, 2, 17, 59)) == [])
r = fd.fuer_push(T, ["mia", "ben"], dt.datetime(2026, 11, 2, 18, 5))
pruef("18:05: nur Mia, nur ihr Faden", [(p_, [f["text"] for f in l]) for p_, l in r] ==
      [("mia", ["Mia will etwas Wichtiges erledigen."])], r)
r = fd.fuer_push(T, ["mia", "ben"], dt.datetime(2026, 11, 2, 20, 1))
pruef("20:01: Ben, Mia nicht noch einmal", [p_ for p_, _ in r] == ["ben"], r)
pruef("Hoechstens ein Push je Tag", fd.fuer_push(T, ["mia", "ben"], dt.datetime(2026, 11, 2, 21)) == [])
pruef("Nach dem Push: am selben Tag keine Nachfrage im Gespraech",
      fd.zum_nachfassen(T, "mia", dt.datetime(2026, 11, 2, 21)) is None)
pt = fd.push_text([{"text": "Handwerker anrufen"}, {"text": "Keller entrümpeln", "phase": "abschluss"}])
pruef("Push-Text", pt == "Noch offen: Handwerker anrufen. Erledigt? Sag mir kurz Bescheid. Schon lange offen: Keller "
      "entrümpeln. Soll ich das fallen lassen?", pt)
leeren()
fd.einstellen(T, "mia", push="an")
nx = fd.neu(T, "mia", "Mia will den Keller entrümpeln.", "2026-11-02", jetzt=MO)
d_ = fd.laden(T)
d_["faeden"][0]["gefragt"] = ["2026-11-02", "2026-11-03", "2026-11-04"]
fd._speichern(T, d_)
r = fd.fuer_push(T, ["mia"], dt.datetime(2026, 11, 6, 18, 1))
pruef("Push mit Abschlussfrage", len(r) == 1 and "fallen lassen" in fd.push_text(r[0][1]), r)
pruef("... als Abschluss vermerkt", fd.alle(T, "mia")[0].get("abschluss_gefragt") == "2026-11-06")
pruef("Ohne Antwort verfaellt er zur Frist", fd.pflegen(T, dt.datetime(2026, 11, 17, 4))[0] == 1
      and fd.alle(T, "mia")[0]["status"] == "verfallen")

# ---------------------------------------------------------------- Texte und Marke
f = {"id": 7, "text": "Mia wartet, ob der Zug wieder fährt.", "art": "warten", "faellig": "2026-11-02",
     "angelegt": "2026-10-30 09:00", "gefragt": ["2026-11-01"]}
pruef("Zeile: heute, Nachfragen", fd.zeile(f, 1, MO) == "1. [7] Mia wartet, ob der Zug wieder fährt. (fällig heute, schon 1× "
      "nachgefragt)", fd.zeile(f, 1, MO))
pruef("Zeile: morgen, seit gestern, Datum", fd.zeile(dict(f, gefragt=[]), None, MO - dt.timedelta(days=1)).endswith("(fällig morgen)")
      and "seit gestern" in fd.zeile(f, None, DI) and "(fällig 02.11." in fd.zeile(f, None, MI))
k = fd.kontext_text(dict(f, phase="nachfassen"), "Mia", MO)
pruef("Kontext: Notiz, Marke, Pruefhinweis bei warten", "kein Auftrag" in k and "⟦faden: 7⟧" in k and "wartet auf etwas" in k
      and "sieh vorher nach" in k and "seit 30.10." in k, k)
pruef("Knopf: Erledigt", fd.knopf_text(f) == "Erledigt: Mia wartet, ob der Zug wieder fährt")
t, nr = fd.marke_aus("Licht ist aus. Zug schon wieder unterwegs?\n⟦faden: 7⟧\n⟦nachlesen: Licht aus | Wohnzimmer⟧")
pruef("Marke raus, andere Marken bleiben", nr == [7] and "⟦faden" not in t and t.endswith("⟦nachlesen: Licht aus | Wohnzimmer⟧"), t)
pruef("Ohne Marke: Text unveraendert", fd.marke_aus("Hallo") == ("Hallo", []))

# ---------------------------------------------------------------- Englisch
try:
    fd.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", True)
fd.setze_sprache("en")
pruef("EN: Zeile", fd.zeile(f, 1, MO) == "1. [7] Mia wartet, ob der Zug wieder fährt. (due today, asked 1× already)"
      and "since yesterday" in fd.zeile(f, None, DI) and "(due 2 Nov" in fd.zeile(f, None, MI)
      and fd.zeile(dict(f, gefragt=[]), None, MO - dt.timedelta(days=1)).endswith("(due tomorrow)"), fd.zeile(f, None, MI))
pruef("EN: Knopf", fd.knopf_text(f) == "Done: Mia wartet, ob der Zug wieder fährt"
      and fd.knopf_text(dict(f, phase="abschluss")) == "Drop it: Mia wartet, ob der Zug wieder fährt")
pt = fd.push_text([dict(f, text="Call the plumber"), dict(f, text="Clear the cellar", phase="abschluss")])
pruef("EN: Push", pt == "Still open: Call the plumber. Done? Just let me know. Open for a long time: Clear the cellar. "
      "Shall I drop it?", pt)
k = fd.kontext_text(dict(f, phase="nachfassen"), "Mia", MO)
pruef("EN: Kontext nachfassen", k.startswith(" Open thread of Mia (no. 7, since 30 Oct, waiting for something)")
      and "⟦faden: 7⟧" in k and "look it up first" in k and "not a task" in k, k)
k = fd.kontext_text(dict(f, phase="abschluss", verfaellt="2026-11-16"), "Mia", MO)
pruef("EN: Kontext Abschluss", "expires on 16 Nov" in k and "whether you should drop it" in k and "⟦faden: 7⟧" in k, k)
k = fd.kontext_text(dict(f, art="vorhaben", phase="nachfassen"), "Mia", MO)
pruef("EN: Kontext Vorhaben ohne Pruefhinweis", ", plan)" in k and "look it up" not in k, k)
meldungen = []
for falsch in ({"push": "vielleicht"}, {"je_tag": "viel"}, {"je_tag": 9}, {"unbekannt": 1}, {}):
    try:
        fd.einstellen(T, "mia", **falsch)
    except fd.Fehler as ex:
        meldungen.append(str(ex))
pruef("EN: Fehler beim Einstellen", meldungen == ["push is an (on) or aus (off).", "je_tag is a whole number.",
                                                   "je_tag goes from 1 to 3.", "Unknown setting unbekannt. Possible: nachfassen, "
                                                   "je_tag, push, push_stunde, verfall_tage.", "No change given."], meldungen)
leeren()
try:
    for i in range(fd.OFFEN_MAX + 1):
        fd.neu(T, "tom", "Tom will Aufgabe Nummer %03d erledigen." % i, jetzt=MO)
    pruef("EN: zu viele Faeden", False)
except fd.Fehler as ex:
    pruef("EN: zu viele Faeden", str(ex) == "Already %d open threads. Tick a few off first." % fd.OFFEN_MAX, ex)
fd.setze_sprache("de")
pruef("Zurueck auf Deutsch", fd.knopf_text(f).startswith("Erledigt: "))

print("Offene Fäden: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
