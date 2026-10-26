#!/usr/bin/env python3
"""Einheitentests fuer bruecke/ausgabe.py (seit 0.3.3): Kennungen, Namen, Rechte, Eingang/Ausgabe getrennt, neu_fuer,
Pfad-Tricks, Uebergroesse, Ablauf nach 7 Tagen. In einem Wegwerf-Ordner, ohne Netz."""
import json
import os
import shutil
import sys
import tempfile
import time

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
    t0 = time.time()
    k1 = ausgabe.ablegen(d, b"%PDF-1.5 test", "Brief/Test:1", "application/pdf", quelle="app")
    k2 = ausgabe.ablegen(d, b"\xff\xd8\xff bild", "foto", "image/jpeg", art="eingang", quelle="app")
    k3 = ausgabe.ablegen(d, b"x", "andere.txt", "text/plain", quelle="pc")
    pruef("Kennungen: Ausgabe a…, Eingang b…, 24 hex", k1[0] == "a" and k2[0] == "b" and ausgabe.KENNUNG.match(k1)
          and ausgabe.KENNUNG.match(k2) and len(k1) == 25)
    m, roh = ausgabe.holen(d, k1)
    pruef("Name bereinigt, Inhalt gleich", m["name"] == "Brief_Test_1.pdf" and roh == b"%PDF-1.5 test")
    pruef("Endung ergaenzt", ausgabe.meta(d, k2)["name"] == "foto.jpg")
    pruef("Eingang nicht als Ausgabe abholbar", ausgabe.holen(d, k2, art="ausgabe") is None)
    pruef("Pfad-Tricks abgelehnt", ausgabe.holen(d, "../../etc/passwd") is None and ausgabe.meta(d, "a" + "0" * 23) is None
          and ausgabe.holen(d, k1 + "/../x") is None)
    neu = ausgabe.neu_fuer(d, "app", t0)
    pruef("neu_fuer: nur Ausgaben dieser Quelle", [x["kennung"] for x in neu] == [k1])
    pruef("neu_fuer: ohne Pfade und Quellen", set(neu[0]) == {"kennung", "name", "typ", "groesse", "info"})
    pruef("neu_fuer: zweites Mal leer (geliefert)", ausgabe.neu_fuer(d, "app", t0) == [])
    if os.name == "posix":
        pruef("Datei 600, Ordner 700", oct(os.stat(os.path.join(d, "ablage", k1 + ".bin")).st_mode & 0o777) == "0o600"
              and oct(os.stat(os.path.join(d, "ablage")).st_mode & 0o777) == "0o700")
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
    k4 = ausgabe.ablegen(d, b"FLAC", "lied.flac", "audio/flac", art="eingang", quelle="pc")
    k5 = ausgabe.ablegen(d, b"RIFF", "lied.flac", "audio/wav", art="eingang", quelle="pc", original=k4)
    pruef("Original verknuepft", ausgabe.meta(d, k5).get("original") == k4)
    k6 = ausgabe.ablegen(d, b"RIFF", "x", "audio/wav", art="eingang", original="../../etc/passwd")
    pruef("Original nur als gueltige Kennung", "original" not in ausgabe.meta(d, k6))
    m = ausgabe.meta(d, k3)
    m["erstellt"] -= 8 * 86400
    json.dump(m, open(os.path.join(d, "ablage", k3 + ".json"), "w"))
    pruef("nach 7 Tagen weg", ausgabe.holen(d, k3) is None)
finally:
    shutil.rmtree(d)

print("Ablage: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
