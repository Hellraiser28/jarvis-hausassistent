#!/usr/bin/env python3
"""Einheitentests fuer bruecke/oberflaeche.py: gueltige Aenderungen, Ablehnungen, Verlauf, Grundeinstellung."""
import json
import os
import shutil
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HIER, os.path.join(os.path.dirname(HIER), "bruecke")]   # Paket/Vorlagen: daneben, Repo: ../bruecke
import oberflaeche as ob  # noqa: E402

ok = fehler = 0


def pruef(name, bedingung):
    global ok, fehler
    if bedingung:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name)


def wirft(name, f):
    global ok, fehler
    try:
        f()
    except ob.Ungueltig as e:
        ok += 1
        return str(e)
    fehler += 1
    print("FEHLER (keine Ablehnung):", name)


d = tempfile.mkdtemp()
try:
    sp = ob.Speicher(d)
    basis = sp.laden()
    pruef("leer -> Vorlage", basis == ob.pruefen({}))
    # ein eingerichteter Stand als Ausgang
    eingerichtet = ob.pruefen({"untertitel": "Just A Rather Very Intelligent System · Haus Beispiel", "person": "Alex",
                         "bereiche": list(ob.BEREICHE), "pc_name": "Wohnzimmer-PC",
                         "verbindungen_extra": [["Fernzugang", "App unterwegs"]],
                         "werte_namen": {"strom": "STROM", "euro": "HEUTE", "last": "NAS"}})
    sp.speichern(eingerichtet, "einrichtung")
    pruef("gespeichert", sp.laden() == eingerichtet)
    gruen = ob.aendern(sp.laden(), {"farbe": "gruen"})
    pruef("gruen", gruen["farbe"] == "gruen" and gruen["farben"] is None and gruen["untertitel"] == eingerichtet["untertitel"])
    sp.speichern(gruen, "pc")
    eigen = ob.aendern(sp.laden(), {"farbe": "eigene", "farben": {"c": "#FF8800", "titel": "#ffe0b0"}})
    pruef("eigene Farbe klein geschrieben", eigen["farben"] == {"c": "#ff8800", "titel": "#ffe0b0"})
    sp.speichern(eigen, "app")
    pruef("zurueck auf rot loescht farben", ob.aendern(eigen, {"farbe": "rot"})["farben"] is None)
    aus = ob.aendern(sp.laden(), {"bereiche_aus": ["haus", "laufband"], "knopf_weg": "Termine"})
    pruef("bereiche aus", "haus" not in aus["bereiche"] and "laufband" not in aus["bereiche"])
    pruef("knopf weg", all(k["text"] != "Termine" for k in aus["aktionen"]))
    dazu = ob.aendern(aus, {"bereiche_an": ["haus", "haus"], "knopf_dazu": {"text": "Licht", "frage": "Mach das Licht an.", "symbol": "licht"}})
    pruef("bereiche an ohne Doppelte, feste Reihenfolge", dazu["bereiche"] == [b for b in ob.BEREICHE if b in dazu["bereiche"]] and dazu["bereiche"].count("haus") == 1)
    pruef("knopf dazu", dazu["aktionen"][-1]["text"] == "Licht")
    pruef("Leerzeichen/Umbrueche zusammengezogen", ob.aendern(dazu, {"untertitel": "  Zuhause\n bei  Alex "})["untertitel"] == "Zuhause bei Alex")
    # Ablehnungen
    wirft("unbekannte farbe", lambda: ob.aendern(dazu, {"farbe": "lila"}))
    wirft("eigene ohne c", lambda: ob.aendern(dazu, {"farbe": "eigene", "farben": {"titel": "#ffffff"}}))
    wirft("CSS-Einschleusung", lambda: ob.aendern(dazu, {"farbe": "eigene", "farben": {"c": "red;background:url(x)"}}))
    wirft("fremde Farbangabe", lambda: ob.aendern(dazu, {"farbe": "eigene", "farben": {"c": "#ff0000", "schrift": "#000000"}}))
    wirft("unbekannter bereich", lambda: ob.aendern(dazu, {"bereiche_an": ["kamera"]}))
    wirft("unbekannter schluessel", lambda: ob.aendern(dazu, {"daten": {"datei": "../geheim.json"}}))
    wirft("zu langer untertitel", lambda: ob.aendern(dazu, {"untertitel": "x" * 81}))
    wirft("steuerzeichen", lambda: ob.aendern(dazu, {"name": "J\x00A"}))
    wirft("unbekanntes symbol", lambda: ob.aendern(dazu, {"knopf_dazu": {"text": "X", "frage": "Y", "symbol": "<svg>"}}))
    wirft("knopf ohne frage", lambda: ob.aendern(dazu, {"knopf_dazu": {"text": "X", "frage": ""}}))
    wirft("zu viele knoepfe", lambda: ob.aendern(dazu, {"aktionen": [{"text": "a", "frage": "b"}] * 11}))
    wirft("begruessung falsch", lambda: ob.aendern(dazu, {"begruessungen": [["11", "Moin"]]}))
    wirft("knopf_weg unbekannt", lambda: ob.aendern(dazu, {"knopf_weg": "Gibtsnicht"}))
    wirft("leere aenderung", lambda: ob.aendern(dazu, {}))
    m = wirft("lila Meldung", lambda: ob.aendern(dazu, {"farbe": "lila"})) or ""
    pruef("Meldung nennt Moeglichkeiten", "gruen" in m)
    # HTML bleibt Text (die Seite maskiert), aber Laenge und Typ werden geprueft
    pruef("HTML als Text erlaubt", ob.aendern(dazu, {"untertitel": "<b>Hallo</b>"})["untertitel"] == "<b>Hallo</b>")
    app = ob.aendern(dazu, {"app_aktionen": [{"text": "Mediathek", "frage": "Was ist neu in der Mediathek?", "symbol": "film"}]})
    pruef("app_aktionen eigene Liste", app["app_aktionen"][0]["symbol"] == "film" and app["aktionen"] == dazu["aktionen"])
    pruef("app_bereiche Standard alle an", ob.pruefen({})["app_bereiche"] == list(ob.APP_BEREICHE))
    ohne = ob.aendern(dazu, {"app_bereiche": ["radio", "werte", "werte"]})
    pruef("app_bereiche feste Reihenfolge ohne Doppelte", ohne["app_bereiche"] == ["werte", "radio"])
    pruef("app_bereiche aendern laesst HUD-Bereiche stehen", ohne["bereiche"] == dazu["bereiche"])
    pruef("app_bereiche leer erlaubt", ob.aendern(dazu, {"app_bereiche": []})["app_bereiche"] == [])
    wirft("app_bereiche unbekannt", lambda: ob.aendern(dazu, {"app_bereiche": ["kamera"]}))
    wirft("app_bereiche kein Liste", lambda: ob.aendern(dazu, {"app_bereiche": "radio"}))
    pruef("Beschreibung nennt ausgeblendete App-Bereiche", "In der App ausgeblendet" in ob.beschreiben(ohne))
    pruef("nachtmodus auto", ob.aendern(dazu, {"nachtmodus": "auto", "bewegung": "ruhig"})["nachtmodus"] == "auto")
    wirft("nachtmodus falsch", lambda: ob.aendern(dazu, {"nachtmodus": "immer"}))
    wirft("bewegung falsch", lambda: ob.aendern(dazu, {"bewegung": "wild"}))
    wirft("app-Knopf ohne Frage", lambda: ob.aendern(dazu, {"app_aktionen": [{"text": "X", "frage": ""}]}))
    # Verlauf und Rueckgaengig
    pruef("aktuell eigene", sp.laden()["farbe"] == "eigene")
    pruef("rueckgaengig -> gruen", sp.rueckgaengig()["farbe"] == "gruen")
    pruef("rueckgaengig -> rot (eingerichtet)", sp.rueckgaengig() == eingerichtet)
    pruef("Grundeinstellung = Vorlage vor der ersten Aenderung", sp.grundeinstellung() == basis)
    # Windows kennt kein 600 (dort schuetzen Ordnerrechte, siehe Bauanleitung)
    pruef("Dateirechte 600", os.name == "nt" or oct(os.stat(sp.datei).st_mode & 0o777) == "0o600")
    # kaputte Datei faellt auf Grund zurueck, unbekannte Schluessel in der Datei ebenso
    json.dump({"farbe": "lila"}, open(sp.datei, "w"))
    pruef("kaputte Datei -> Grund", sp.laden() == sp.grundeinstellung())
    gleich = sp.speichern(sp.laden(), "pc")
    pruef("unveraendert -> kein Verlaufseintrag", gleich is False)
    for i in range(25):
        sp.speichern(ob.aendern(sp.laden(), {"untertitel": "Test %d" % i}), "pc")
    pruef("Verlauf hoechstens 20", len(json.load(open(sp.verlauf))) == 20)
    print("Beschreibung:", ob.beschreiben(dazu))
finally:
    shutil.rmtree(d)
o = ob.optionen()
pruef("optionen: Schema fuers Zahnrad", set(o) == {"farben", "farb_namen", "bereiche", "app_bereiche", "symbole",
                                                    "nachtmodus", "bewegung", "designs", "design_namen", "grenzen"}
      and o["app_bereiche"] == list(ob.APP_BEREICHE) and all(f in o["farb_namen"] for f in o["farben"]))
# Design "Observatorium" (seit 0.5)
pruef("design: Vorgabe klassisch", ob.pruefen({})["design"] == "klassisch")
pruef("design: kern gueltig", ob.pruefen({"design": "kern"})["design"] == "kern")
try:
    ob.pruefen({"design": "ultron"})
    pruef("design: unbekannt abgelehnt", False)
except ob.Ungueltig:
    pruef("design: unbekannt abgelehnt", True)
pruef("design: beschreiben nennt es", ob.beschreiben(ob.pruefen({"design": "kern"})).startswith("Design: Observatorium"))
# Sprache (0.3.0): englische Grundwerte und Meldungen, danach wieder Deutsch
ob.setze_sprache("en")
en = ob.pruefen({})
pruef("en: Grundwerte englisch", en["begruessungen"][1][1] == "Good morning{, person}." and en["werte_namen"]["last"] == "LOAD"
      and en["aktionen"][1]["text"] == "Calendar")
try:
    ob.aendern(en, {"farbe": "lila"})
    pruef("en: lila abgelehnt", False)
except ob.Ungueltig as x:
    pruef("en: Meldung englisch", str(x).startswith("There is no color"))
pruef("en: Beschreibung englisch", ob.beschreiben(en).startswith("Design: Classic (reactor). Color: Red-gold."))
pruef("en: Farbnamen englisch", ob.optionen()["farb_namen"]["blau"] == "Blue")
try:
    ob.setze_sprache("fr")
    pruef("fr abgelehnt", False)
except ValueError:
    pruef("fr abgelehnt", True)
ob.setze_sprache("de")
pruef("de: wieder deutsch", ob.pruefen({})["begruessungen"][1][1] == "Guten Morgen{, person}." and ob.SPRACHE == "de")
pruef("STANDARD_EN nur bekannte Schluessel", set(ob.STANDARD_EN) <= set(ob.STANDARD))
# Knoepfe (seit 25.10.2026): die Bruecke nimmt sie nur aus Quellen mit PC-Rechten an und erkennt sie hiermit
for a in ({"aktionen": []}, {"app_aktionen": []}, {"knopf_dazu": {"text": "a", "frage": "b"}}, {"knopf_weg": "a"},
          {"farbe": "blau", "aktionen": []}):
    pruef("Knopf-Aenderung erkannt: %r" % a, ob.betrifft_knoepfe(a))
for a in ({"farbe": "blau"}, {"bereiche_aus": ["aktionen"]}, {}, None, "aktionen", ["aktionen"]):
    pruef("keine Knopf-Aenderung: %r" % (a,), not ob.betrifft_knoepfe(a))
# Seit 0.3.2 (Pruefbericht 0.3.1): Fund 5 Format- und Richtungszeichen, Fund 6 aendern() ohne Seiteneffekt,
# Fund 7 Rueckgaengig und Grundeinstellung ohne PC-Rechte behalten die Knoepfe
wirft("Fund 5: U+202E abgelehnt", lambda: ob._text("Licht‮", 20, "Knopf"))
wirft("Fund 5: U+200B abgelehnt", lambda: ob._text("Lic​ht", 20, "Knopf"))
pruef("Fund 5: U+0085 (Zeilenende) wird wie Leerraum entfernt", ob._text("Licht\u0085", 20, "Knopf") == "Licht")
wirft("Fund 5: U+009B (Steuerzeichen C1) abgelehnt", lambda: ob._text("Licht\u009b", 20, "Knopf"))
wirft("Fund 5: Knopf mit Richtungszeichen abgelehnt", lambda: ob.aendern(
    ob.pruefen({}), {"knopf_dazu": {"text": "Wetter‮", "frage": "x", "symbol": "wetter"}}))
pruef("Fund 5: Umlaute und Symbole bleiben erlaubt", ob._text("Grüße ☀", 20, "Knopf") == "Grüße ☀")
a = {"knopf_dazu": {"text": "Test", "frage": "Wie spät ist es?", "symbol": "wetter"}}
ob.aendern(ob.pruefen({}), a)
pruef("Fund 6: Objekt des Aufrufers unveraendert", "knopf_dazu" in a and ob.betrifft_knoepfe(a))
d7 = tempfile.mkdtemp()
try:
    sp7 = ob.Speicher(d7)
    s1 = ob.aendern(sp7.laden(), {"knopf_dazu": {"text": "Geheim", "frage": "mach was", "symbol": "wetter"}})
    sp7.speichern(s1, "pc")
    sp7.speichern(ob.aendern(sp7.laden(), {"knopf_weg": "Geheim", "farbe": "blau"}), "pc")
    r = sp7.rueckgaengig(knoepfe_behalten=True)
    pruef("Fund 7: Rueckgaengig ohne PC-Rechte holt geloeschten Knopf nicht zurueck",
          all(k["text"] != "Geheim" for k in r["aktionen"]))
    pruef("Fund 7: ... die Farbe aber schon", r["farbe"] == s1["farbe"] and r["farbe"] != "blau")
    sp7.speichern(ob.aendern(sp7.laden(), {"knopf_dazu": {"text": "Zwei", "frage": "y", "symbol": "wetter"}}), "pc")
    sp7.speichern(ob.aendern(sp7.laden(), {"knopf_weg": "Zwei"}), "pc")
    pruef("Fund 7: mit PC-Rechten holt Rueckgaengig den Knopf zurueck",
          any(k["text"] == "Zwei" for k in sp7.rueckgaengig()["aktionen"]))
    g = sp7.grundeinstellung(knoepfe_behalten=True)
    pruef("Fund 7: Grundeinstellung ohne PC-Rechte behaelt die jetzigen Knoepfe",
          g["aktionen"] == sp7.laden()["aktionen"])
finally:
    shutil.rmtree(d7, ignore_errors=True)
print("%d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
