#!/usr/bin/env python3
"""Einheitentests fuer bruecke/ausgabe.py (seit 0.3.3): Kennungen, Namen, Rechte, Eingang/Ausgabe getrennt, Pfad-Tricks,
Uebergroesse, Ablauf nach 7 Tagen. Seit 0.3.4 (Pruefbericht 0.3.3): Besitzer und Anfrage (Funde 1-3), Namen ohne
Richtungszeichen und Geraetenamen (Fund 10), Liste erlaubter Typen beim Abholen (Fund 12), Angaben zum laufenden
Gehirn (aktiv/<pid>.json). In einem Wegwerf-Ordner, ohne Netz."""
import json
import os
import shutil
import sys
import tempfile
import threading

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HIER, os.path.join(os.path.dirname(HIER), "bruecke")]
import ausgabe  # noqa: E402

ok = fehler = 0


def pruef(name, bedingung):
    global ok, fehler
    if bedingung:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name)


d = tempfile.mkdtemp()
try:
    k1 = ausgabe.ablegen(d, b"%PDF-1.5 test", "Brief/Test:1", "application/pdf", quelle="app", besitzer="geraet1",
                         anfrage="anfrage01")
    k2 = ausgabe.ablegen(d, b"\xff\xd8\xff bild", "foto", "image/jpeg", art="eingang", quelle="app", besitzer="geraet1",
                         anfrage="anfrage01")
    k3 = ausgabe.ablegen(d, b"x", "andere.txt", "text/plain", quelle="app", besitzer="geraet2", anfrage="anfrage02")
    pruef("Kennungen: Ausgabe a…, Eingang b…, 24 hex", k1[0] == "a" and k2[0] == "b" and ausgabe.KENNUNG.match(k1)
          and ausgabe.KENNUNG.match(k2) and len(k1) == 25)
    m, roh = ausgabe.holen(d, k1)
    pruef("Name bereinigt, Inhalt gleich", m["name"] == "Brief_Test_1.pdf" and roh == b"%PDF-1.5 test")
    pruef("Endung ergaenzt", ausgabe.meta(d, k2)["name"] == "foto.jpg")
    pruef("Eingang nicht als Ausgabe abholbar", ausgabe.holen(d, k2, art="ausgabe") is None)
    pruef("Pfad-Tricks abgelehnt", ausgabe.holen(d, "../../etc/passwd") is None and ausgabe.meta(d, "a" + "0" * 23) is None
          and ausgabe.holen(d, k1 + "/../x") is None)
    # Fund 1: Besitzer
    pruef("Besitzer: eigenes Geraet bekommt die Datei", ausgabe.holen(d, k1, art="ausgabe", besitzer="geraet1") is not None)
    pruef("Besitzer: anderes Geraet nicht", ausgabe.holen(d, k1, art="ausgabe", besitzer="geraet2") is None)
    pruef("Besitzer: leerer Besitzer nie", ausgabe.holen(d, k1, besitzer="") is None)
    alt = ausgabe.ablegen(d, b"alt", "alt.txt", "text/plain")
    pruef("Besitzer: Datei ohne Besitzer (0.3.3) bekommt niemand", ausgabe.holen(d, alt, besitzer="haupt") is None)
    pruef("Besitzer mit ungueltigen Zeichen wird leer", ausgabe.meta(d, ausgabe.ablegen(
        d, b"y", "y", "text/plain", besitzer="../x"))["besitzer"] == "")
    # Fund 2: nach Anfrage einsammeln
    neu = ausgabe.neu_fuer(d, "anfrage01")
    pruef("neu_fuer: nur Ausgaben dieser Anfrage", [x["kennung"] for x in neu] == [k1])
    pruef("neu_fuer: ohne Pfade und Quellen", set(neu[0]) == {"kennung", "name", "typ", "groesse", "info"})
    pruef("neu_fuer: zweites Mal leer (geliefert)", ausgabe.neu_fuer(d, "anfrage01") == [])
    pruef("neu_fuer: andere Anfrage bleibt fuer sich", [x["kennung"] for x in ausgabe.neu_fuer(d, "anfrage02")] == [k3])
    pruef("neu_fuer: ungueltige Anfrage leer", ausgabe.neu_fuer(d, "") == [] and ausgabe.neu_fuer(d, "../x") == [])
    viele = [ausgabe.ablegen(d, b"z", "z%d.txt" % i, "text/plain", besitzer="g", anfrage="parallel") for i in range(20)]
    erg = []
    faeden = [threading.Thread(target=lambda: erg.append(ausgabe.neu_fuer(d, "parallel"))) for _ in range(6)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    alle = [x["kennung"] for liste in erg for x in liste]
    pruef("neu_fuer: gleichzeitig jede Datei genau einmal", sorted(alle) == sorted(viele))
    # Fund 10: Namen
    k = ausgabe.ablegen(d, b"x", "Rechnung‮fdp.exe", "application/octet-stream", besitzer="g")
    pruef("Name ohne Richtungszeichen", ausgabe.meta(d, k)["name"] == "Rechnungfdp.exe")
    k = ausgabe.ablegen(d, b"x", "CON.txt", "text/plain", besitzer="g")
    pruef("Windows-Geraetename entschaerft", ausgabe.meta(d, k)["name"] == "_CON.txt")
    # Fund 12: Typen beim Abholen
    pruef("Typ: PDF bleibt", ausgabe.ausliefer_typ("application/pdf") == "application/pdf")
    pruef("Typ: HTML, SVG, XML, APK werden octet-stream", all(ausgabe.ausliefer_typ(t) == "application/octet-stream" for t in (
        "text/html", "image/svg+xml", "application/xhtml+xml", "text/xml", "text/xsl",
        "application/vnd.android.package-archive", "")))
    pruef("Typ: Gross/Klein und Zusatz egal", ausgabe.ausliefer_typ("Image/PNG; x=1") == "image/png")
    # laufendes Gehirn
    ausgabe.aktiv_schreiben(d, 4242, "geraet1", "anfrage09")
    pruef("aktiv: schreiben und lesen", ausgabe.aktiv_lesen(d, 4242) == ("geraet1", "anfrage09"))
    pruef("aktiv: unbekanntes Gehirn leer", ausgabe.aktiv_lesen(d, 4243) == ("", ""))
    ausgabe.aktiv_schreiben(d, 4244, "", "")
    pruef("aktiv: ohne Fragenden leer", ausgabe.aktiv_lesen(d, 4244) == ("", ""))
    if os.name == "posix":
        pruef("Datei 600, Ordner 700", oct(os.stat(os.path.join(d, "ablage", k1 + ".bin")).st_mode & 0o777) == "0o600"
              and oct(os.stat(os.path.join(d, "ablage")).st_mode & 0o777) == "0o700"
              and oct(os.stat(os.path.join(d, "ablage", "aktiv")).st_mode & 0o777) == "0o700")
    try:
        ausgabe.ablegen(d, b"x" * (ausgabe.MAX_BYTES + 1), "gross", "x")
        pruef("Uebergroesse abgelehnt", False)
    except ausgabe.Fehler:
        pruef("Uebergroesse abgelehnt", True)
    try:
        ausgabe.ablegen(d, b"", "leer", "x")
        pruef("leere Datei abgelehnt", False)
    except ausgabe.Fehler:
        pruef("leere Datei abgelehnt", True)
    m = ausgabe.meta(d, k3)
    m["erstellt"] -= 8 * 86400
    json.dump(m, open(os.path.join(d, "ablage", k3 + ".json"), "w"))
    pruef("nach 7 Tagen weg", ausgabe.holen(d, k3) is None)
    k4 = ausgabe.ablegen(d, b"FLAC", "lied.flac", "audio/flac", art="eingang", quelle="pc", besitzer="g")
    k5 = ausgabe.ablegen(d, b"RIFF", "lied.flac", "audio/wav", art="eingang", quelle="pc", original=k4, besitzer="g")
    pruef("Original verknuepft", ausgabe.meta(d, k5).get("original") == k4)
    k6 = ausgabe.ablegen(d, b"RIFF", "x", "audio/wav", art="eingang", original="../../etc/passwd")
    pruef("Original nur als gueltige Kennung", "original" not in ausgabe.meta(d, k6))
finally:
    shutil.rmtree(d)

print("Ablage: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
