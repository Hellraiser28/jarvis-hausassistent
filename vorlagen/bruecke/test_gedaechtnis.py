#!/usr/bin/env python3
"""Einheitentests fuer bruecke/gedaechtnis.py und bruecke/personen.py (seit 0.4). Nur im Testordner."""
import json
import os
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HIER, os.path.join(os.path.dirname(HIER), "bruecke")]
import gedaechtnis as gd  # noqa: E402
import personen as pe  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    if bed:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name, info)


D = tempfile.mkdtemp(prefix="gedaechtnis-test-")
NAMEN = {"alex": "Alex", "sam": "Sam"}

# Personen
json.dump({"alex": {"name": "Alex", "rolle": "haupt", "paperless_id": 3},
           "sam": {"name": "Sam", "rolle": "familie", "kontakt": "Sam", "paperless_id": 4},
           "Böse": {"name": "x", "rolle": "haupt"}, "gast": {"name": "<script>", "rolle": "chef"}},
          open(os.path.join(D, "personen.json"), "w"))
P = pe.laden(D)
pruef("Personen: nur gueltige", sorted(P) == ["alex", "sam"], P)
pruef("Hauptperson", pe.haupt(P) == "alex")
geraete = [{"id": "4b6f5d", "name": "Handy Alex"}, {"id": "aa11bb", "name": "Handy Sam", "person": "sam"},
           {"id": "cc22dd", "name": "fremd", "person": "gast"}]
pruef("Geraet ohne Person: Hauptperson", pe.fuer_geraet(P, geraete, "4b6f5d") == "alex")
pruef("Geraet Sam", pe.fuer_geraet(P, geraete, "aa11bb") == "sam")
pruef("Hauptschluessel", pe.fuer_geraet(P, geraete, "haupt") == "alex")
pruef("unbekannte Person am Geraet: niemand", pe.fuer_geraet(P, geraete, "cc22dd") is None)
pruef("Sam darf Einkaufsliste", pe.darf(P, "sam", "einkaufsliste"))
for w in ("homelab_auftrag", "notizen", "aufgaben", "routine", "verhalten", "handy_suchen",
          "nas_status", "updates", "quelle_hinzufuegen"):
    pruef("Sam darf nicht: " + w, not pe.darf(P, "sam", w))
# seit 0.6: oberflaeche ja, aber nur das eigene Aussehen auf den eigenen Geraeten (prueft die Bruecke), postfach ja,
# aber nur das eigene (postfach_zugang_datei, ohne Mail-Wache; prueft der Werkzeug-Server)
pruef("Sam darf oberflaeche (nur eigenes Aussehen)", pe.darf(P, "sam", "oberflaeche"))
pruef("Sam darf postfach (nur eigenes)", pe.darf(P, "sam", "postfach"))
pruef("Alex darf alles", pe.darf(P, "alex", "homelab_auftrag"))
pruef("Unbekannte Person darf nichts", not pe.darf(P, "gast", "wetter"))
pruef("ohne Datei: nur Hauptperson", pe.laden(tempfile.mkdtemp()) == pe.STANDARD)

# Migration aus gedaechtnis.md
open(os.path.join(D, "gedaechtnis.md"), "w", encoding="utf-8").write(
    "- 22.10.2026 19:05: Privates von Alex\n- 23.10.2026 01:26: Geburtstage der Familie\n"
    "- 24.10.2026 19:14: Denon-Regel\n")
pruef("Migration: 3 uebernommen", gd.migrieren(D, {2: "haus", 3: "haus"}, "alex") == 3)
pruef("Migration: nur einmal", gd.migrieren(D, {}, "alex") == 0)
g = gd.laden(D)
pruef("Migration: Bereiche", [e["bereich"] for e in g["eintraege"]] == ["alex", "haus", "haus"])
pruef("Migration: Datum bleibt", g["eintraege"][0]["datum"] == "22.10.2026 19:05")
# Unix-Rechte nur ausserhalb von Windows pruefbar (dort gelten ACLs)
pruef("Datei 600", os.name == "nt" or oct(os.stat(os.path.join(D, gd.DATEI)).st_mode & 0o777) == "0o600")

# Sichtbarkeit
nb = gd.neu(D, "Sam mag Tee\nmit Zeilenumbruch", "sam", "sam")
pruef("neu: Nummer", nb == 4)
pruef("neu: wortgleich nicht doppelt", gd.neu(D, "sam mag tee mit zeilenumbruch", "sam", "sam") == 0)
pruef("neu: Steuerzeichen raus", "\n" not in gd.laden(D)["eintraege"][-1]["text"])
pruef("Alex sieht Sams Privates nicht", all(e["bereich"] != "sam" for e in gd.fuer_person(D, "alex")))
pruef("Sam sieht Alex' Privates nicht", all(e["bereich"] != "alex" for e in gd.fuer_person(D, "sam")))
pruef("Sam sieht Haus", len([e for e in gd.fuer_person(D, "sam") if e["bereich"] == "haus"]) == 2)
k = gd.fuer_kontext(D, "sam", NAMEN)
pruef("Kontext Sam: Haus + ihres, nichts von Alex", "Geburtstage" in k and "Sam mag Tee" in k
      and "Privates von Alex" not in k and "Nur für Sam" in k, k)
pruef("Kontext kurz: Hinweis auf aeltere", "Ältere Einträge" in gd.fuer_kontext(D, "alex", NAMEN, max_zeichen=60))
pruef("Sam kann Alex' Privates nicht vergessen", gd.vergessen(D, "sam", "Privates von Alex") == 0)
pruef("Sam kann Alex' Privates nicht ersetzen", not gd.ersetzen(D, 1, "geaendert", "sam"))
pruef("ersetzen behaelt alten Text", gd.ersetzen(D, 3, "Denon-Regel neu", "alex", quelle="import")
      and gd.laden(D)["eintraege"][2]["frueher"][0]["text"] == "Denon-Regel")

# TXT-Export und -Import (Sam)
t = gd.export_txt(D, "sam", NAMEN)
pruef("Export: Abschnitte", "## Haus" in t and "## Nur für Sam" in t and "Privates von Alex" not in t, t)
zeilen = t.split("\n")
geaendert = []
for z in zeilen:
    if z.startswith("[2]"):
        geaendert.append("[2] 23.10.2026 01:26 | Geburtstage der Familie (ergänzt)")
    elif z.startswith("[3]"):
        continue                                         # geloescht
    elif z.startswith("## Nur für Sam"):
        geaendert += [z, "- Sam arbeitet samstags oft bis 14 Uhr", "[1] 22.10.2026 | Versuch, Alex' Eintrag zu ändern"]
    elif z.startswith("[4]"):
        geaendert.append("[4] 28.10.2026 | Sam mag Tee mit Zeilenumbruch")
        geaendert.append("## Haus")
        geaendert.append("- Neuer Haus-Eintrag")
    else:
        geaendert.append(z)
v = gd.import_vergleich(D, "sam", "\n".join(geaendert), NAMEN, "alex")
# seit 0.6: 2 und 3 sind Alex' Haus-Eintraege, Sam darf sie nicht aendern oder loeschen (Haus-Regel)
pruef("Import: Aenderung an Alex' Haus-Eintrag gesperrt", v["geaendert"] == [] and 2 in v["gesperrt"], v)
pruef("Import: Loeschung von Alex' Haus-Eintrag gesperrt", v["geloescht"] == [] and 3 in v["gesperrt"], v)
pruef("Import: neu 2 in richtigen Bereichen", sorted((x["bereich"], x["text"]) for x in v["neu"]) ==
      [("haus", "Neuer Haus-Eintrag"), ("sam", "Sam arbeitet samstags oft bis 14 Uhr")], v)
pruef("Import: fremde Nummer ignoriert", v["unbekannt"] == [1], v)
pruef("Vergleichstext", "nicht angefasst" in gd.vergleich_text(v, NAMEN, "sam"))
a, l_, n_, u_ = gd.import_uebernehmen(D, "sam", v, "alex")
pruef("Uebernehmen: Zahlen", (a, l_, n_, u_) == (0, 0, 2, 0), (a, l_, n_, u_))
g = gd.laden(D)
pruef("Alex' Eintrag unveraendert", g["eintraege"][0]["text"] == "Privates von Alex")
pruef("Eintrag 3 bleibt (Haus-Regel)", any(e["id"] == 3 for e in g["eintraege"]))
pruef("Verschieben: fremder Haus-Eintrag nicht in den eigenen Bereich", gd.import_vergleich(
    D, "sam", "## Nur für Sam\n[2] x | Geburtstage der Familie (ergänzt)\n## Haus\n", NAMEN, "alex")["geaendert"] == [])
pruef("Verschieben durch die Hauptperson: haus -> privat", gd.import_vergleich(
    D, "alex", "## Nur für Alex\n[2] x | Geburtstage der Familie (ergänzt)\n## Haus\n", NAMEN,
    "alex")["geaendert"][0]["bereich"] == "alex")
# Sams eigener Haus-Eintrag bleibt fuer Sam aenderbar (Urheber)
sh = [e["id"] for e in gd.laden(D)["eintraege"] if e["text"] == "Neuer Haus-Eintrag"][0]
v2 = gd.import_vergleich(D, "sam", "## Haus\n[%d] x | Neuer Haus-Eintrag (Sam)\n## Nur für Sam\n" % sh, NAMEN, "alex")
pruef("Import: eigener Haus-Eintrag aenderbar", [x["id"] for x in v2["geaendert"]] == [sh] and sh not in v2["gesperrt"], v2)
leer = gd.import_vergleich(D, "sam", "irgendein Text ohne Abschnitte\n- auch nicht", NAMEN)
pruef("Ohne Abschnitte: nichts neu, aber alles als geloescht erkannt (Rueckfrage zeigt das)", not leer["neu"] and leer["geloescht"])

# Tabus fuers Lernen
for t in ("Das Passwort fürs WLAN ist abc", "Alex nimmt Medikament X", "laut der Mail von Amazon kommt das Paket",
          "[Kennwort]"):
    pruef("Tabu: " + t, gd.TABU_LERNEN.search(t))
pruef("kein Tabu: Vorliebe", not gd.TABU_LERNEN.search("Alex hört den Denon meist auf Lautstärke 40"))

# ---------------------------------------------------------------- seit 0.6: Haus-Regel (bearbeitbar)
import datetime as dt  # noqa: E402
import shutil  # noqa: E402
import time  # noqa: E402

H = tempfile.mkdtemp(prefix="gedaechtnis-haus-")
NH = {"alex": "Alex", "sam": "Sam", "kim": "Kim"}


def eintrag_von(ordner, nr):
    return next((e for e in gd.laden(ordner)["eintraege"] if e["id"] == nr), None)


HA = gd.neu(H, "Haus-Regel von Alex: Die Gartenlampe geht um acht aus.", "haus", "alex")
HS = gd.neu(H, "Haus-Regel von Sam: Der Schlüsselkasten hängt im Flur.", "haus", "sam")
PA = gd.neu(H, "Privater Plan von Alex: Das Geschenk für Opa ist ein Buch.", "alex", "alex")
PS = gd.neu(H, "Privater Plan von Sam: Die Überraschungsparty steigt im Mai.", "sam", "sam")
g = gd.laden(H)
g["eintraege"].append({"id": 99, "bereich": "haus", "text": "Alter Haus-Eintrag ohne Urheber über Mülltonnen.",
                       "datum": "01.01.2026 10:00", "quelle": "uebernommen"})
g["naechste"] = 100
gd._speichern(H, g)
E = {e["id"]: e for e in gd.laden(H)["eintraege"]}
pruef("neu: Urheber steht in autor", E[HS].get("autor") == "sam" and E[HS].get("von") == "sam")
pruef("bearbeitbar: Urheber ja", gd.bearbeitbar(E[HS], "sam", "alex"))
pruef("bearbeitbar: Hauptperson ja", gd.bearbeitbar(E[HS], "alex", "alex"))
pruef("bearbeitbar: andere Person nein", not gd.bearbeitbar(E[HA], "sam", "alex") and not gd.bearbeitbar(E[HA], "kim", "alex"))
pruef("bearbeitbar: ohne Hauptperson nur Urheber (sicherer Standard)",
      not gd.bearbeitbar(E[HS], "alex") and gd.bearbeitbar(E[HS], "sam"))
pruef("bearbeitbar: Eintrag ohne Urheber nur Hauptperson",
      gd.bearbeitbar(E[99], "alex", "alex") and not gd.bearbeitbar(E[99], "sam", "alex"))
pruef("bearbeitbar: Eigenes ja, fremdes Privates nie", gd.bearbeitbar(E[PA], "alex", "alex")
      and not gd.bearbeitbar(E[PA], "sam", "alex") and not gd.bearbeitbar(E[PS], "alex", "alex"))
vor = open(os.path.join(H, gd.DATEI), "rb").read()
pruef("ersetzen: fremder Haus-Eintrag abgelehnt, auch mit Quelle app/import",
      gd.ersetzen(H, HA, "geaendert", "sam", "merken", "alex") is False
      and gd.ersetzen(H, HA, "geaendert", "kim", "app", "alex") is False
      and gd.ersetzen(H, HA, "geaendert", "sam", "import", "alex") is False)
pruef("vergessen_nr: fremder Haus-Eintrag, fremdes Privates, unbekannte Nummer: nichts",
      gd.vergessen_nr(H, "sam", HA, "alex") is False and gd.vergessen_nr(H, "alex", PS, "alex") is False
      and gd.vergessen_nr(H, "alex", 12345, "alex") is False)
pruef("Datei nach den Versuchen unveraendert", open(os.path.join(H, gd.DATEI), "rb").read() == vor)
try:
    gd.vergessen(H, "sam", "Gartenlampe", "alex")
    pruef("vergessen: Fehler bei fremdem Haus-Eintrag", False)
except gd.Fehler as e:
    pruef("vergessen: Fehler bei fremdem Haus-Eintrag", "nicht von dir" in str(e) and eintrag_von(H, HA), str(e))
gd.neu(H, "Sam merkt: Die Regel Nummer eins gilt immer.", "haus", "sam")
RZ = gd.neu(H, "Alex merkt: Die Regel Nummer zwei gilt auch.", "haus", "alex")
pruef("vergessen_ex: Mischtreffer loescht nur das Eigene und meldet den Rest",
      gd.vergessen_ex(H, "sam", "regel nummer", "alex") == (1, 1) and eintrag_von(H, RZ))
pruef("ersetzen: Hauptperson aendert Sams Haus-Eintrag",
      gd.ersetzen(H, HS, "Der Schlüsselkasten hängt im Keller.", "alex", "app", "alex") is True)
e = eintrag_von(H, HS)
pruef("Urheber bleibt nach Aenderung durch die Hauptperson", e["autor"] == "sam" and e["von"] == "alex"
      and e["quelle"] == "app" and gd.bearbeitbar(e, "sam", "alex"), e)
g = gd.laden(H)
g["eintraege"].append({"id": 150, "bereich": "haus", "text": "Alt ohne Autor, aber mit von.", "datum": "01.01.2026 10:00",
                       "quelle": "merken", "von": "sam"})
g["naechste"] = 151
gd._speichern(H, g)
gd.ersetzen(H, 150, "Alt ohne Autor, Hauptperson aendert.", "alex", "app", "alex")
pruef("Alter Eintrag ohne autor: Urheber (von) wird vor der Aenderung gesichert", eintrag_von(H, 150)["autor"] == "sam")
pruef("Lernen ersetzt nie Haus-Eintraege, auch nicht die eigenen",
      gd.ersetzen(H, HA, "gelernt-x", "alex", "gelernt", "alex") is False)
v = gd.import_vergleich(H, "sam", gd.export_txt(H, "sam", NH).replace("Mülltonnen", "GEAENDERT"), NH, "alex")
v["geaendert"].append({"id": HA, "alt": eintrag_von(H, HA)["text"], "neu": "EINGESCHLEUST", "bereich_alt": "haus",
                       "bereich": "haus"})
v["geloescht"].append({"id": 99, "text": eintrag_von(H, 99)["text"]})
a_, l_, n_, u_ = gd.import_uebernehmen(H, "sam", v, "alex")
pruef("Uebernehmen: gefaelschter Vergleich aendert/loescht fremde Haus-Eintraege nicht",
      (a_, l_) == (0, 0) and eintrag_von(H, HA)["text"].startswith("Haus-Regel von Alex") and eintrag_von(H, 99),
      (a_, l_, n_, u_))
pruef("Vergleichstext nennt die Sperre", 99 in v["gesperrt"] and "nicht angefasst" in gd.vergleich_text(v, NH, "sam"), v)

# ---------------------------------------------------------------- seit 0.6: Nutzung ("zuletzt gebraucht")
NUTZ = os.path.join(H, gd.NUTZUNG)


def mtime(pfad):
    return os.stat(pfad).st_mtime_ns


haupt_vorher = mtime(os.path.join(H, gd.DATEI))
pruef("Nutzung: noch keine Datei", not os.path.exists(NUTZ))
t0 = dt.datetime(2026, 10, 30, 12, 0)
pruef("genutzt: nur gueltige, vorhandene Nummern", gd.genutzt(H, [HA, PA, 12345, "x", True, None], t0) == 2)
pruef("Nutzung aendert gedaechtnis.json NICHT (warme Gehirne bleiben)", mtime(os.path.join(H, gd.DATEI)) == haupt_vorher)
nz = json.load(open(NUTZ, encoding="utf-8"))["eintraege"]
pruef("Nutzungsdatei: Zaehler und Datum", nz.get(str(HA)) == {"zuletzt": "30.10.2026 12:00", "n": 1} and "12345" not in nz, nz)
pruef("Nutzungsdatei 600", os.name == "nt" or oct(os.stat(NUTZ).st_mode & 0o777) == "0o600")
m1 = mtime(NUTZ)
pruef("Innerhalb einer Stunde nicht nochmal gezaehlt, nichts geschrieben",
      gd.genutzt(H, [HA], t0 + dt.timedelta(minutes=59)) == 0 and mtime(NUTZ) == m1)
pruef("Nach einer Stunde wieder", gd.genutzt(H, [HA], t0 + dt.timedelta(minutes=61)) == 1
      and json.load(open(NUTZ, encoding="utf-8"))["eintraege"][str(HA)]["n"] == 2)
pruef("Keine Treffer: nichts", gd.genutzt(H, [], t0) == 0 and gd.genutzt(H, None, t0) == 0)
wegwerf = gd.neu(H, "Wegwerfeintrag für die Aufräum-Probe.", "alex", "alex")
gd.genutzt(H, [wegwerf], t0 + dt.timedelta(hours=5))
gd.vergessen_nr(H, "alex", wegwerf, "alex")
gd.genutzt(H, [PA], t0 + dt.timedelta(hours=9))
pruef("Geloeschter Eintrag wird aus der Nutzungsdatei geraeumt", str(wegwerf) not in json.load(open(NUTZ))["eintraege"])
E1 = [{"id": 1, "text": "Freitags gibt es bei uns Pizza zum Abendessen."},
      {"id": 2, "text": "Alex hört morgens gern Radio mit Nachrichten."},
      {"id": 3, "text": "Kaffee ohne Zucker."}, {"id": 4, "text": "Pizza."}]
pruef("verwendet: zwei Inhaltswoerter in der Antwort",
      gd.verwendet(E1, "Freitag ist Pizza-Tag, zum Abendessen gibt es Pizza.", {"alex"}) == [1, 4])
pruef("verwendet: ein Wort reicht bei langem Eintrag nicht", 2 not in gd.verwendet(E1, "Soll ich das Radio anmachen?", {"alex"}))
pruef("verwendet: Name allein zaehlt nicht", gd.verwendet([{"id": 9, "text": "Alexander Alexander"}],
                                                          "Hallo Alexander, wie geht es dir?", {"alex"}) == [])
pruef("verwendet: Beugung erkannt", 3 in gd.verwendet(E1, "Ich bringe den Kaffee ohne Zucker.", set()))
pruef("verwendet: leere Antwort", gd.verwendet(E1, "", set()) == [])
pruef("genutzt_aus_antwort: fremdes Privates zaehlt nie",
      gd.genutzt_aus_antwort(H, "sam", "Das Geschenk für Opa ist ein Buch, sagt der Plan.", NH, t0 + dt.timedelta(days=2)) == 0)
pruef("genutzt_aus_antwort: Haus-Eintrag und eigener Eintrag", gd.genutzt_aus_antwort(
    H, "sam", "Die Regel: Die Gartenlampe geht um acht aus, und die Überraschungsparty steigt im Mai.", NH,
    t0 + dt.timedelta(days=2)) == 2)

# ---------------------------------------------------------------- seit 0.6: Sternbild (Themen, Helligkeit, Rechte)
S = tempfile.mkdtemp(prefix="sternbild-test-")


def stern_eintrag(bereich, text, tage, von=None):
    n = gd.neu(S, text, bereich, von or (bereich if bereich != "haus" else "alex"))
    g = gd.laden(S)
    for e in g["eintraege"]:
        if e["id"] == n:
            e["datum"] = (dt.datetime.now() - dt.timedelta(days=tage)).strftime("%d.%m.%Y %H:%M")
    gd._speichern(S, g)
    return n


H1 = stern_eintrag("haus", "Freitags gibt es Pizza zum Abendessen.", 3)
H2 = stern_eintrag("haus", "Das Wohnzimmerlicht soll abends warm leuchten.", 40, von="sam")
H3 = stern_eintrag("haus", "Die Mülltonne kommt dienstags raus.", 200)
P1 = stern_eintrag("alex", "Alex hört morgens gern Radio mit Nachrichten.", 1)
P2 = stern_eintrag("alex", "Geheimtipp von Alex: Briefmarken-Geschenk für Opa im Dezember.", 5)
B1 = stern_eintrag("sam", "Sam mag keine Pilze im Essen.", 2)
B2 = stern_eintrag("sam", "Sam plant eine Überraschung für Alex zum Geburtstag.", 9)
K1 = stern_eintrag("kim", "Kims Zahnspangentermin ist im Januar.", 4)
s = gd.sternbild(S, "alex", NH, haupt="alex")
ids = {x["id"] for x in s["sterne"]}
pruef("Sternbild: Hauptperson sieht Haus und Eigenes", ids == {H1, H2, H3, P1, P2}, ids)
th = {x["id"]: x["thema"] for x in s["sterne"]}
pruef("Sternbild: Themen Essen, Haus, Musik", (th[H1], th[H2], th[P1]) == ("Essen & Trinken", "Haus & Geräte",
                                                                           "Musik & Medien"), th)
pruef("Sternbild: Haus-Eintrag einer anderen Person nennt den Urheber",
      [x["von"] for x in s["sterne"] if x["id"] == H2] == ["Sam"] and [x["von"] for x in s["sterne"] if x["id"] == H1] == [""])
hell = {x["id"]: x["hell"] for x in s["sterne"]}
pruef("Sternbild: neu heller als alt", hell[P1] > hell[H2] > hell[H3] >= 0.3, hell)
pruef("Sternbild: Bereiche und Zaehler", (s["haus"], s["privat"], s["gesamt"]) == (3, 2, 5)
      and {x["id"]: x["bereich"] for x in s["sterne"]}[P1] == "privat")
pruef("Sternbild: Quelle als Text", [x["quelle_text"] for x in s["sterne"] if x["id"] == P1] == ["gemerkt"])
t2 = gd.themen_ableiten([{"id": 1, "text": "Die Zimtschnecken vom Bäcker Meyer sind Spitze."},
                         {"id": 2, "text": "Beim Bäcker Meyer die Roggenbrötchen holen? Nein, Zimtschnecken."},
                         {"id": 3, "text": "Xylofon liegt im Dachboden."}])
pruef("Themen: wiederkehrendes Wort wird Thema, Einzelnes ist Sonstiges", t2[1] == t2[2] != "Sonstiges" and t2[3] == "Sonstiges", t2)
pruef("Themen: kurzes Stichwort nur am Wortanfang (nas nicht in Ananas)",
      gd.themen_ableiten([{"id": 9, "text": "Ananas schmeckt mir nicht."}])[9] != "Technik & Homelab")
voll = json.dumps(s, ensure_ascii=False)
pruef("Sternbild: Antwort der Hauptperson ohne fremdes Privates", "Pilze" not in voll and "Überraschung" not in voll
      and "Zahnspange" not in voll)
sb = gd.sternbild(S, "sam", NH, haupt="alex")
voll_b = json.dumps(sb, ensure_ascii=False)
pruef("Sternbild: Sam sieht Haus + Eigenes, nie Alex' Privates", {x["id"] for x in sb["sterne"]} == {H1, H2, H3, B1, B2}
      and "Briefmarken" not in voll_b and "Radio" not in voll_b and "Zahnspange" not in voll_b)
fl = {x["id"]: (x["aendern"], x["loeschen"]) for x in sb["sterne"]}
pruef("Sternbild: Flags fuer Sam (Alex' Haus-Eintrag gesperrt, eigene frei)",
      fl[H1] == (False, False) and fl[H2] == (True, True) and fl[B1] == (True, True), fl)
pruef("Sternbild: von_haupt markiert Haus-Eintraege der Hauptperson",
      [x["von_haupt"] for x in sb["sterne"] if x["id"] == H1] == [True] and [x["von_haupt"] for x in sb["sterne"] if x["id"] == H2] == [False])
pruef("Sternbild: ohne Recht (darf_aendern/darf_loeschen) keine Knoepfe", not any(
    x["aendern"] or x["loeschen"] for x in gd.sternbild(S, "sam", NH, darf_aendern=False, darf_loeschen=False, haupt="alex")["sterne"]))
pruef("Sternbild: Hauptperson darf alles Sichtbare", all(x["aendern"] and x["loeschen"] for x in s["sterne"]))
alt = stern_eintrag("alex", "Uralter Eintrag über die Wanderschuhe im Keller.", 200)
h0 = next(x["hell"] for x in gd.sternbild(S, "alex", NH, haupt="alex")["sterne"] if x["id"] == alt)
gd.genutzt(S, [alt])
st = next(x for x in gd.sternbild(S, "alex", NH, haupt="alex")["sterne"] if x["id"] == alt)
pruef("Sternbild: gebrauchter alter Eintrag wird heller", st["hell"] > h0 + 0.5 and st["nutzung"] == 1
      and st["tage_genutzt"] == 0 and st["genutzt"], (h0, st))
th_liste = [x["name"] for x in gd.sternbild(S, "kim", NH, haupt="alex")["themen"]]
pruef("Sternbild: Sonstiges steht hinten", "Sonstiges" not in th_liste or th_liste[-1] == "Sonstiges", th_liste)
g = gd.laden(S)                                    # in einem Schreibvorgang auffuellen (schneller als gd.neu je Eintrag)
for i in range(gd.STERNE_MAX + 5):
    g["eintraege"].append({"id": g["naechste"], "bereich": "kim", "text": "Füllung Nummer %d zum Testen der Obergrenze" % i,
                           "datum": "01.01.2026 10:00", "quelle": "merken", "von": "kim", "autor": "kim"})
    g["naechste"] += 1
gd._speichern(S, g)
d_ = gd.sternbild(S, "kim", NH)
pruef("Sternbild: hoechstens STERNE_MAX Sterne, gesamt zaehlt alle", len(d_["sterne"]) == gd.STERNE_MAX
      and d_["gesamt"] > gd.STERNE_MAX)

# Englisch: Themen- und Quellennamen, englische Stichwoerter ohne deutsche Fehltreffer
gd.setze_sprache("en")
te = gd.themen_ableiten([{"id": 1, "text": "We order pizza for dinner on Fridays."},
                         {"id": 2, "text": "The living room light should be warm in the evening."},
                         {"id": 3, "text": "Sam likes the radio in the morning."},
                         {"id": 4, "text": "A note about the boiler."},
                         {"id": 5, "text": "Kim's husband collects stamps."}])
pruef("Englisch: Themen", (te[1], te[2], te[3], te[4]) == ("Food & Drink", "Home & Devices", "Music & Media",
                                                           "Home & Devices"), te)
pruef("Englisch: 'husband' ist keine Band, Einzelnes ist Other", te[5] == "Other", te)
se = gd.sternbild(S, "alex", NH, haupt="alex")
pruef("Englisch: Quelle und Themen im Sternbild", [x["quelle_text"] for x in se["sterne"] if x["id"] == P1] == ["saved"]
      and [x["thema"] for x in se["sterne"] if x["id"] == H1] == ["Food & Drink"], [x["thema"] for x in se["sterne"]][:5])
try:
    gd.vergessen(H, "sam", "Gartenlampe", "alex")
    pruef("Englisch: Sperrmeldung", False)
except gd.Fehler as e:
    pruef("Englisch: Sperrmeldung", "not saved by you" in str(e), str(e))
pruef("Englisch: Vergleichstext nennt die Sperre", "left untouched" in gd.vergleich_text(v, NH, "sam"))
gd.setze_sprache("de")

# ---------------------------------------------------------------- seit 0.6: Personen (Postfach je Person, Gaeste)
PD = tempfile.mkdtemp(prefix="personen-test-")
json.dump({"alex": {"name": "Alex", "rolle": "haupt"},
           "sam": {"name": "Sam", "rolle": "familie", "postfach_zugang_datei": "/pfad/postfach_sam.json",
                   "paperless_token_datei": "/pfad/paperless_token_sam", "paperless_id": 4},
           "robin": {"name": "Robin", "rolle": "gast"}},
          open(os.path.join(PD, "personen.json"), "w"))
P6 = pe.laden(PD)
pruef("Personen: postfach_zugang_datei uebernommen", P6["sam"].get("postfach_zugang_datei") == "/pfad/postfach_sam.json"
      and P6["sam"].get("paperless_token_datei") == "/pfad/paperless_token_sam")
pruef("Personen: rolle gast nie aus personen.json", "robin" not in P6)


class GaesteAttrappe:
    def __init__(self, liste):
        self.liste = liste

    def aktive(self, daten):
        return [dict(g) for g in self.liste]


alt_gaeste = pe.gaeste
GAST = {"id": "gast-a1b2c3", "name": "Gast Robin", "bis": time.time() + 3600, "raeume": ["wohnzimmer"]}
try:
    pe.gaeste = GaesteAttrappe([GAST])
    P7 = pe.laden(PD)
    pruef("Gaeste: aktiver Gast mit Rolle gast", P7.get("gast-a1b2c3", {}).get("rolle") == "gast"
          and P7["gast-a1b2c3"]["raeume"] == ["wohnzimmer"] and pe.ist_gast(P7, "gast-a1b2c3"), P7)
    pruef("Gaeste: darf nur GAST_WERKZEUGE", pe.darf(P7, "gast-a1b2c3", "wetter") and pe.darf(P7, "gast-a1b2c3", "tv_programm")
          and not pe.darf(P7, "gast-a1b2c3", "gedaechtnis") and not pe.darf(P7, "gast-a1b2c3", "fernsehen")
          and not pe.darf(P7, "gast-a1b2c3", "postfach"))
    P7["gast-a1b2c3"]["bis"] = time.time() - 1
    pruef("Gaeste: abgelaufen darf nichts mehr", not pe.darf(P7, "gast-a1b2c3", "wetter"))
    pruef("Gaeste: Geraet mit Gast als Person hat keine Rechte",
          pe.fuer_geraet(pe.laden(PD), [{"id": "g1", "person": "gast-a1b2c3"}], "g1") is None)
    pruef("Gaeste: Hauptperson und Familie unveraendert", pe.haupt(P7) == "alex" and not pe.ist_gast(P7, "sam"))
    pruef("Gaeste: ohne personen.json Hauptperson plus Gast", set(pe.laden(tempfile.mkdtemp())) == {"ich", "gast-a1b2c3"})
    pe.gaeste = GaesteAttrappe([dict(GAST, id="sam")])
    pruef("Gaeste: Kennung aus personen.json wird nie ueberschrieben", pe.laden(PD)["sam"]["rolle"] == "familie")
    pe.gaeste = GaesteAttrappe([GAST])
    open(os.path.join(PD, "personen.json"), "w").write("{kaputt")
    pruef("Gaeste: kaputte personen.json heisst niemand, auch kein Gast", pe.laden(PD) == {})
    pe.gaeste = None
    pruef("Gaeste: ohne gaeste.py keine Gaeste", pe.laden(tempfile.mkdtemp()) == pe.STANDARD)
finally:
    pe.gaeste = alt_gaeste
for ordner in (H, S, PD):
    shutil.rmtree(ordner, ignore_errors=True)

print("Gedächtnis und Personen: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
