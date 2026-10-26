#!/usr/bin/env python3
"""Dateien von Jarvis im PC-Client (ab 18, 0.3.3): Kennung pruefen, Namen bereinigen, ausfuehrbare Endungen nie direkt
oeffnen, Vorschau nur fuer Bilder. Funktionen aus jarvis_pc.py gelesen, ohne den Client (Fenster, Mikrofon) zu laden.
Laeuft im Repo (tests/ neben spiegel/pc/) und in der Release-Vorlage (neben jarvis_pc.py)."""
import ast
import base64
import os
import re
import sys
import unicodedata

HIER = os.path.dirname(os.path.abspath(__file__))
for pfad in (os.path.join(HIER, "..", "spiegel", "pc", "jarvis_pc.py"), os.path.join(HIER, "jarvis_pc.py")):
    if os.path.exists(pfad):
        break
else:
    sys.exit("jarvis_pc.py nicht gefunden")

NAMEN = ("DATEI_KENNUNG", "DIREKT_OEFFNEN", "WINDOWS_GERAETE", "_datei_name", "_herkunft_markieren", "datei_holen",
         "datei_vorschau", "datei_oeffnen")
baum = ast.parse(open(pfad, encoding="utf-8").read())
teile = [n for n in baum.body if (isinstance(n, ast.Assign) and any(isinstance(z, ast.Name) and z.id in NAMEN
                                                                      for z in n.targets))
         or (isinstance(n, ast.FunctionDef) and n.name in NAMEN)]
geholt = []
JPEG = b"\xff\xd8\xff\xe0" + b"x" * 40
DATEIEN = {"a" + "1" * 24: JPEG, "a" + "2" * 24: b"%PDF-1.5 ...", "a" + "3" * 24: b"\xff\xd8\xff" + b"x" * (5 * 1024 * 1024)}


def bruecke_holen(p, zeit=30):
    geholt.append(p)
    return DATEIEN[p.rsplit("/", 1)[1]]


class Log:
    def info(self, *a):
        pass


u = {"re": re, "os": os, "base64": base64, "unicodedata": unicodedata, "bruecke_holen": bruecke_holen, "log": Log(), "WINDOWS": False,
     "tx": lambda de, en: de, "DATEI_ORDNER": "/nirgends"}
exec(compile(ast.Module(body=teile, type_ignores=[]), pfad, "exec"), u)
fehler = 0


def pruefe(name, ist, soll):
    global fehler
    if ist != soll:
        fehler += 1
        print("FEHLER:", name, "| ist:", repr(ist)[:120], "| soll:", repr(soll)[:120])


pruefe("Name bereinigt", u["_datei_name"]('..\\boese/"x"<y>.pdf'), "_boese_x_y_.pdf")
pruefe("leerer Name", u["_datei_name"]("  .. "), "datei")
for n in ("Setup.exe", "x.BAT", "run.ps1", "a.lnk", "skript.js", "Rechnung.pdf.scr", "start.sh", "hilfe.chm", "x.msc",
          "makro.docm", "tabelle.xlsm", "disk.iso", "verbindung.rdp", "design.theme", "seite.html", "bild.svg", "z.cer",
          "app.appinstaller", "x.settingcontent-ms", "y.library-ms", "a.diagcab", "b.msix", "c.one", "d.xll"):
    pruefe("nie direkt oeffnen (Fund 8): " + n, bool(u["DIREKT_OEFFNEN"].search(n)), False)
for n in ("Brief.pdf", "Bild.jpg", "Bild.JPEG", "Tabelle.xlsx", "Musik.mp3", "Notiz.txt", "Lied.flac", "Text.odt"):
    pruefe("direkt oeffnen erlaubt: " + n, bool(u["DIREKT_OEFFNEN"].search(n)), True)
pruefe("Fund 10: Richtungszeichen entfernt", u["_datei_name"]("Rechnung\u202efdp.exe"), "Rechnungfdp.exe")
pruefe("Fund 10: Geraetename entschaerft", u["_datei_name"]("NUL.txt"), "_NUL.txt")
pruefe("Herkunftsmarke ohne Windows: nichts", u["_herkunft_markieren"]("/nirgends/x.pdf"), None)
erg = u["datei_oeffnen"]("a" + "1" * 24, "Setup.exe")
pruefe("datei_oeffnen lehnt .exe ab, ohne zu holen", ("fehler" in erg, geholt), (True, []))
for k in ("../a", "b" + "1" * 24, "a" + "1" * 23, "a" + "1" * 24 + "/x"):
    try:
        u["datei_holen"](k)
        pruefe("Kennung abgelehnt: " + k, False, True)
    except ValueError:
        pass
pruefe("nichts geholt bei falschen Kennungen", geholt, [])
pruefe("Vorschau JPEG", u["datei_vorschau"]("a" + "1" * 24).startswith("data:image/jpeg;base64,"), True)
pruefe("keine Vorschau fuer PDF", u["datei_vorschau"]("a" + "2" * 24), "")
pruefe("keine Vorschau ueber 4 MB", u["datei_vorschau"]("a" + "3" * 24), "")
pruefe("Pfad zur Bruecke", geholt[0], "/v1/datei/a" + "1" * 24)

print("Dateien (PC): %d Fehler" % fehler)
sys.exit(1 if fehler else 0)
