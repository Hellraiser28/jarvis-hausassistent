#!/usr/bin/env python3
"""Briefe-Modul (seit 0.4) ohne Bruecke und ohne Paperless: Datum, Erinnerungszeitpunkt, Zuordnung von Namen,
Aufgaben-Status (Paperless 2.x und 3.x), Multipart, Fristen je Person. Testordner statt echter Daten."""
import datetime as dt
import os
import shutil
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HIER), "bruecke"))
import briefe  # noqa: E402

T = tempfile.mkdtemp(prefix="briefe-test-")
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    if bed:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name, str(info)[:300])


def wirft(f, *a):
    try:
        f(*a)
    except briefe.Fehler as e:
        return str(e)
    return ""


H = dt.date(2026, 10, 28)
pruef("Datum ISO", briefe.datum("2026-11-15", H) == dt.date(2026, 11, 15))
pruef("Datum deutsch", briefe.datum("15.11.2026", H) == dt.date(2026, 11, 15))
pruef("Datum zu weit weg", "zu weit weg" in wirft(briefe.datum, "2031-01-01", H))
pruef("Datum unlesbar", "verstehe ich nicht" in wirft(briefe.datum, "nächsten Montag", H))
j = dt.datetime(2026, 10, 28, 14, 7)
pruef("Erinnerung drei Tage vorher 9 Uhr", briefe.erinnerung_wann(dt.date(2026, 11, 15), j) == dt.datetime(2026, 11, 12, 9, 0))
pruef("Erinnerung knapp: in einer Stunde", briefe.erinnerung_wann(dt.date(2026, 10, 29), j) == dt.datetime(2026, 10, 28, 15, 5))
pruef("Erinnerung bei vorbei: keine", briefe.erinnerung_wann(dt.date(2026, 10, 27), j) is None)
liste = {1: "Stadtwerke Musterstadt", 2: "Versicherung AG", 3: "Finanzamt Musterstadt"}
pruef("Passend genau", briefe.passend(liste, "finanzamt musterstadt") == 3)
pruef("Passend Teil", briefe.passend(liste, "Stadtwerke") == 1)
pruef("Passend umgekehrt", briefe.passend(liste, "Versicherung AG Nord") == 2)
pruef("Passend nichts", briefe.passend(liste, "Telefonanbieter") is None)
pruef("Passend zu kurz", briefe.passend({1: "AOK"}, "AO") is None)
echt = briefe._anfrage
briefe._anfrage = lambda *a, **k: {"count": 1, "results": [{"status": "success", "result_data": {"document_id": 2170},
                                                             "related_document_ids": [2170]}]}
pruef("Aufgabe 3.x", briefe.aufgabe("t", "x")[:2] == ("SUCCESS", 2170))
briefe._anfrage = lambda *a, **k: [{"status": "SUCCESS", "related_document": "77", "result": "ok"}]
pruef("Aufgabe 2.x", briefe.aufgabe("t", "x")[:2] == ("SUCCESS", 77))
briefe._anfrage = lambda *a, **k: {"count": 0, "results": []}
pruef("Aufgabe noch nicht da", briefe.aufgabe("t", "x")[0] == "PENDING")
briefe._anfrage = echt
koerper, typ = briefe._multipart([("title", "Brief ä"), ("tags", 5)], ("a/b\"c.pdf", "application/pdf", b"%PDF-1"))
pruef("Multipart: Felder und Datei", b'name="title"\r\n\r\nBrief \xc3\xa4' in koerper and b'filename="a_b_c.pdf"' in koerper
      and b"%PDF-1" in koerper and typ.startswith("multipart/form-data; boundary="))
pruef("Hochladen: leere Datei abgelehnt", "leer" in wirft(briefe.hochladen, "t", b"", "x.pdf", "application/pdf"))
pruef("Paperless-Adresse ohne Schraegstrich am Ende", not briefe.PAPERLESS.endswith("/"))
heute = dt.date.today()
briefe.neu(T, "sam", heute + dt.timedelta(days=18), "Rechnung zahlen", "Jahresabrechnung", "Stadtwerke", None, "uuid1", "Frist bis x: y")
f2 = briefe.neu(T, "sam", heute + dt.timedelta(days=5), "Widerspruch einlegen", "Bescheid", "Finanzamt")
briefe.neu(T, "alex", heute + dt.timedelta(days=2), "Frist von Alex")
l = briefe.fuer(T, "sam")
pruef("Fristen je Person, nach Datum", [x["was"] for x in l] == ["Widerspruch einlegen", "Rechnung zahlen"], l)
pruef("Zeile", "(in 5 Tagen): Widerspruch einlegen – Finanzamt" in briefe.zeile(l[0], 1), briefe.zeile(l[0], 1))
briefe.dokument_nachtragen(T, "uuid1", 2170)
pruef("Dokument nachgetragen", briefe.fuer(T, "sam")[1]["dokument"] == 2170)
pruef("Erledigt per Stichwort", briefe.erledigt(T, "sam", "widerspruch")["id"] == f2["id"])
pruef("Erledigt nicht mehr offen", [x["was"] for x in briefe.fuer(T, "sam")] == ["Rechnung zahlen"])
pruef("Fremde Frist nicht erledigen", briefe.erledigt(T, "sam", "Alex") is None)
pruef("Datei 600", oct(os.stat(os.path.join(T, briefe.DATEI)).st_mode & 0o777) == "0o600")
shutil.rmtree(T)
print("Briefe: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
