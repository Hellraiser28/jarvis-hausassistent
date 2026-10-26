#!/usr/bin/env python3
"""Einheitentests fuer bruecke/pdf.py (seit 0.3.3): Aufbau (Kopf, Querverweise, Seitenzahl), Umlaute im Inhaltsstrom,
Umbruch innerhalb der Breite, Bilder (JPEG-Kopf, PNG mit Transparenz als SMask), Fehlerfaelle. Ohne Netz."""
import os
import re
import struct
import sys
import zlib

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HIER, os.path.join(os.path.dirname(HIER), "bruecke")]   # Paket/Vorlagen: daneben, Repo: ../bruecke
import pdf  # noqa: E402

ok = fehler = 0


def pruef(name, bedingung):
    global ok, fehler
    if bedingung:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name)


def jpeg_kopf(w, h):
    """Nur SOI + SOF0 + EOI: pdf.py liest Groesse und Farbkanaele, dekodiert nichts."""
    return (b"\xff\xd8\xff\xc0" + struct.pack(">HBHHB", 17, 8, h, w, 3) + bytes([1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1])
            + b"\xff\xd9")


def png_rgba(w, h):
    roh = b"".join(b"\x00" + b"".join(bytes([x % 256, y % 256, 99, 128]) for x in range(w)) for y in range(h))

    def stueck(art, inhalt):
        return struct.pack(">I", len(inhalt)) + art + inhalt + struct.pack(">I", zlib.crc32(art + inhalt) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + stueck(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            stueck(b"IDAT", zlib.compress(roh)) + stueck(b"IEND", b""))


def aufbau(roh):
    """Kopf, Ende, startxref zeigt auf xref, jede Tabellenzeile auf 'n 0 obj'."""
    if not roh.startswith(b"%PDF-1.5") or not roh.rstrip().endswith(b"%%EOF"):
        return False
    start = int(re.search(rb"startxref\n(\d+)\n", roh).group(1))
    if roh[start:start + 4] != b"xref":
        return False
    zeilen = roh[start:].split(b"\n")
    anzahl = int(zeilen[1].split()[1])
    for i in range(1, anzahl):
        lage = int(zeilen[2 + i][:10])
        if not roh[lage:].startswith(b"%d 0 obj" % i):
            return False
    return True


def stroeme(roh):
    aus = []
    for m in re.finditer(rb"/Filter /FlateDecode /Length (\d+) >>\nstream\n", roh):
        n = int(m.group(1))
        try:
            aus.append(zlib.decompress(roh[m.end():m.end() + n]))
        except zlib.error:
            pass
    return b"\n".join(aus)


roh, n = pdf.erstellen("Kündigung", "Sehr geehrte Damen und Herren,\n\nmit freundlichen Grüßen\n- Punkt mit **fett**\n"
                                    "1. Erster\nPreis 12,50 € „inklusive“ → fertig 😀")
pruef("Aufbau (Kopf, Querverweise, Ende)", aufbau(roh))
pruef("eine Seite", n == 1 and len(re.findall(rb"/Type /Page ", roh)) == 1)
inhalt = stroeme(roh)
pruef("Umlaute als WinAnsi im Strom", b"K\\374ndigung" in inhalt and b"Gr\\374\\337en" in inhalt)
pruef("Euro und Anfuehrungszeichen", b"\\200" in inhalt and b"\\204inklusive\\223" in inhalt)
pruef("fett mit der zweiten Schrift", b"/F2" in inhalt and b"(fett) Tj" in inhalt)
pruef("Pfeil ersetzt, Emoji entfaellt", pdf._cp("→ x 😀") == b"-> x ")
pruef("Titel in den Metadaten (UTF-16)", b"/Title <FEFF" in roh)

lang = "\n\n".join("## Abschnitt %d\n" % i + ("Übung macht den Meister. " * 40) for i in range(1, 9))
roh, n = pdf.erstellen("Lang", lang)
pruef("langer Text: mehrere Seiten", n >= 3 and aufbau(roh) and len(re.findall(rb"/Type /Page ", roh)) == n)
breite = pdf.A4_B - 2 * pdf.RAND
zu_breit = [z for z in pdf._umbrechen(pdf._laeufe("Übung macht den Meister. " * 30 + "Donaudampfschifffahrt" * 8),
                                      pdf.GROESSE, breite)
            if sum(pdf._breite(r, f, pdf.GROESSE) for r, f in z) > breite + 0.01]
pruef("Umbruch bleibt in der Breite (auch ueberlange Woerter)", not zu_breit)

roh, n = pdf.erstellen("Fotos", "", [jpeg_kopf(1280, 853), png_rgba(40, 30)])
pruef("nur Bilder: keine Titelseite", n == 2 and aufbau(roh))
pruef("JPEG als DCTDecode, PNG mit SMask", b"/DCTDecode" in roh and b"/SMask" in roh and b"/Width 1280 /Height 853" in roh)
roh, n = pdf.erstellen("Text und Bild", "Beleg vom Einkauf", [jpeg_kopf(600, 800)])
pruef("Text und Bild: zwei Seiten", n == 2)

for name, daten in (("Text statt Bild", b"kein Bild"), ("kaputtes PNG", b"\x89PNG\r\n\x1a\nabc"),
                    ("JPEG ohne Kopf", b"\xff\xd8\xff\xd9")):
    try:
        pdf.erstellen("x", "", [daten])
        pruef("abgelehnt: " + name, False)
    except Exception:
        pruef("abgelehnt: " + name, True)
try:
    pdf.erstellen("", "", [])
    pruef("leer abgelehnt", False)
except pdf.Fehler:
    pruef("leer abgelehnt", True)

print("PDF: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
