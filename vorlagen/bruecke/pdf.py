"""PDF ohne Zusatzpakete (seit 0.3.3, 26.10.2026), Python 3.8: Text mit Ueberschriften, Listen und **fett** auf A4,
Seitenzahlen, dazu Bilder (JPEG, PNG auch mit Transparenz) als eigene Seiten. Fuer "mach mir daraus ein PDF" aus
getipptem, gesprochenem oder fotografiertem Text und fuer "Foto als PDF".

Schrift: die PDF-Standardschriften Helvetica und Helvetica-Bold (in jedem Betrachter vorhanden, nichts eingebettet)
mit WinAnsiEncoding, also Deutsch und Westeuropaeisch samt Umlauten, ß, €, „“ und –. Zeichen ausserhalb davon werden
ersetzt (Pfeile) oder entfallen (Emojis). Zeichenbreiten aus Adobes AFM-Daten (ueber reportlab gewonnen), damit der
Umbruch stimmt.
"""
import re
import struct
import time
import zlib

# Breiten in 1/1000 em fuer cp1252-Codes 32..255 (Adobe Core-14-Metriken)
HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 761, 556, 0, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0, 0, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 0, 500, 667, 278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278, 556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500]
HELV_B = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584, 761, 556, 0, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0, 0, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 0, 500, 667, 278, 333, 556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 611, 556, 278, 333, 333, 365, 556, 834, 834, 834, 611, 722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611, 556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278, 611, 611, 611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556]

A4_B, A4_H = 595.28, 841.89
RAND = 56.7                   # 2 cm
GROESSE = 11.0
ZEILE = 1.38                  # Zeilenabstand als Vielfaches der Schriftgroesse
UEBER = {1: 18.0, 2: 14.0, 3: 12.0}
MAX_BILDPUNKTE = 16_000_000   # PNG mit Transparenz wird in Python entpackt
ERSATZ = {"→": "->", "←": "<-", "⇒": "=>", "↔": "<->", "✓": "v", "✔": "v",
          "✗": "x", " ": " ", " ": " ", " ": " ", "−": "-", "‐": "-", "‑": "-",
          "≤": "<=", "≥": ">=", "≈": "~", "×": "x"}


class Fehler(Exception):
    pass


def _cp(text):
    aus = []
    for z in str(text):
        if z in ERSATZ:
            aus.append(ERSATZ[z])
            continue
        try:
            z.encode("cp1252")
            aus.append(z)
        except UnicodeEncodeError:
            if z in "\t":
                aus.append("    ")
            # sonst (Emojis, fremde Schriften) entfaellt das Zeichen
    return "".join(aus).encode("cp1252")


def _breite(roh, fett, groesse):
    t = HELV_B if fett else HELV
    return sum(t[b - 32] if b >= 32 else 0 for b in roh) * groesse / 1000.0


def _laeufe(zeile):
    """'Ein **fetter** Satz' -> [(b'Ein ', False), (b'fetter', True), (b' Satz', False)]"""
    teile = re.split(r"(\*\*[^*]+\*\*)", zeile)
    return [(_cp(t[2:-2]), True) if t.startswith("**") and t.endswith("**") and len(t) > 4 else (_cp(t), False)
            for t in teile if t]


def _umbrechen(laeufe, groesse, max_b):
    """Laeufe -> Zeilen aus Laeufen, Woerter an Leerzeichen, ueberlange Woerter zeichenweise."""
    woerter = []                                   # (bytes, fett, Leerzeichen davor)
    for roh, fett in laeufe:
        for i, w in enumerate(re.split(rb"( +)", roh)):
            if not w:
                continue
            if w.strip(b" ") == b"":
                woerter.append((b" ", fett, None))
            else:
                woerter.append((w, fett, False))
    zeilen, jetzt, b = [], [], 0.0
    for w, fett, _ in woerter:
        wb = _breite(w, fett, groesse)
        if w == b" ":
            if jetzt:
                jetzt.append((w, fett))
                b += wb
            continue
        if b + wb > max_b and jetzt:
            while jetzt and jetzt[-1][0] == b" ":
                jetzt.pop()
            zeilen.append(jetzt)
            jetzt, b = [], 0.0
        while wb > max_b:                          # Wort laenger als die Zeile
            n = 1
            while n < len(w) and _breite(w[:n + 1], fett, groesse) <= max_b:
                n += 1
            zeilen.append([(w[:n], fett)])
            w = w[n:]
            wb = _breite(w, fett, groesse)
        jetzt.append((w, fett))
        b += wb
    while jetzt and jetzt[-1][0] == b" ":
        jetzt.pop()
    if jetzt:
        zeilen.append(jetzt)
    return zeilen or [[]]


def _bloecke(titel, text):
    """Markdown-leicht -> [(art, Ebene/Marke, Laeufe)]: titel, h, absatz, punkt, leer."""
    aus = []
    if str(titel or "").strip():
        aus.append(("h", 1, _laeufe(str(titel).strip().lstrip("#").strip())))
        aus.append(("leer", 0, []))
    for z in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = z.rstrip()
        if not s.strip():
            aus.append(("leer", 0, []))
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", s.strip())
        if m:
            aus.append(("h", len(m.group(1)), _laeufe(m.group(2))))
            continue
        m = re.match(r"^\s*(?:[-*•]|–)\s+(.*)$", s)
        if m:
            aus.append(("punkt", "•", _laeufe(m.group(1))))
            continue
        m = re.match(r"^\s*(\d{1,3}[.)])\s+(.*)$", s)
        if m:
            aus.append(("punkt", m.group(1), _laeufe(m.group(2))))
            continue
        aus.append(("absatz", 0, _laeufe(s.strip())))
    return aus


def _esc(roh):
    aus = []
    for b in roh:
        if b in (40, 41, 92):
            aus.append("\\" + chr(b))
        elif 32 <= b < 127:
            aus.append(chr(b))
        else:
            aus.append("\\%03o" % b)
    return "".join(aus)


def _text_seiten(titel, text):
    """Seiten als Listen von Zeichenbefehlen (Strings fuer den Inhaltsstrom)."""
    seiten, cmds = [], []
    y = A4_H - RAND
    unten = RAND + 24
    breite = A4_B - 2 * RAND

    def neue_seite():
        nonlocal cmds, y
        seiten.append(cmds)
        cmds, y = [], A4_H - RAND

    def zeile_setzen(laeufe, x, groesse, farbe="0 g"):
        nonlocal y
        if y - groesse * ZEILE < unten:
            neue_seite()
        y -= groesse * ZEILE
        teile = ["BT", farbe, "%.2f %.2f Td" % (x, y)]
        for roh, fett in laeufe:
            if roh:
                teile.append("/%s %.1f Tf (%s) Tj" % ("F2" if fett else "F1", groesse, _esc(roh)))
        teile.append("ET")
        cmds.append(" ".join(teile))

    vorher = None
    for art, marke, laeufe in _bloecke(titel, text):
        if art == "leer":
            if vorher not in (None, "leer"):
                y -= GROESSE * 0.6
            vorher = "leer"
            continue
        if art == "h":
            g = UEBER.get(marke, 12.0)
            if vorher not in (None, "leer"):
                y -= g * 0.5
            if y - g * ZEILE * 2.5 < unten:       # Ueberschrift nicht allein unten auf der Seite
                neue_seite()
            for z in _umbrechen([(r, True) for r, _ in laeufe], g, breite):
                zeile_setzen(z, RAND, g)
            y -= g * 0.25
        elif art == "punkt":
            einzug = 16.0 if marke == "•" else max(16.0, _breite(_cp(marke), False, GROESSE) + 6)
            for i, z in enumerate(_umbrechen(laeufe, GROESSE, breite - einzug)):
                if i == 0:
                    zeile_setzen([(_cp(marke), False)], RAND + 2, GROESSE)
                    y += GROESSE * ZEILE              # Text auf dieselbe Zeile wie die Marke
                zeile_setzen(z, RAND + einzug, GROESSE)
        else:
            for z in _umbrechen(laeufe, GROESSE, breite):
                zeile_setzen(z, RAND, GROESSE)
        vorher = art
    seiten.append(cmds)
    return [s for s in seiten if s] or ([] if not (titel or text) else [[]])


# ------------------------------------------------------------------ Bilder

def _jpeg(roh):
    i = 2
    while i + 9 < len(roh):
        if roh[i] != 0xFF:
            i += 1
            continue
        marke = roh[i + 1]
        if marke in (0xD8, 0x01) or 0xD0 <= marke <= 0xD7:
            i += 2
            continue
        laenge = struct.unpack(">H", roh[i + 2:i + 4])[0]
        if marke in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            bits, h, w, k = roh[i + 4], *struct.unpack(">HH", roh[i + 5:i + 9]), roh[i + 9]
            raum = {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}.get(k)
            if not raum or bits != 8:
                raise Fehler("JPEG mit %d Farbkanaelen/%d Bit wird nicht unterstuetzt" % (k, bits))
            zusatz = " /Decode [1 0 1 0 1 0 1 0]" if k == 4 else ""   # Adobe-CMYK ist invertiert gespeichert
            return {"w": w, "h": h, "dict": "/ColorSpace %s /BitsPerComponent 8 /Filter /DCTDecode%s" % (raum, zusatz),
                    "daten": roh, "maske": None}
        i += 2 + laenge
    raise Fehler("JPEG ohne Bildkopf")


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _entfiltern(roh, w, h, bpp):
    zeile = w * bpp
    aus = bytearray(h * zeile)
    vor = bytearray(zeile)
    p = 0
    for r in range(h):
        f = roh[p]
        z = bytearray(roh[p + 1:p + 1 + zeile])
        p += 1 + zeile
        if f == 1:
            for i in range(bpp, zeile):
                z[i] = (z[i] + z[i - bpp]) & 255
        elif f == 2:
            z = bytearray((x + y) & 255 for x, y in zip(z, vor))
        elif f == 3:
            for i in range(zeile):
                z[i] = (z[i] + ((z[i - bpp] if i >= bpp else 0) + vor[i]) // 2) & 255
        elif f == 4:
            for i in range(zeile):
                z[i] = (z[i] + _paeth(z[i - bpp] if i >= bpp else 0, vor[i], vor[i - bpp] if i >= bpp else 0)) & 255
        elif f != 0:
            raise Fehler("PNG mit unbekanntem Filter")
        aus[r * zeile:(r + 1) * zeile] = z
        vor = z
    return aus


def _png(roh):
    if roh[:8] != b"\x89PNG\r\n\x1a\n":
        raise Fehler("kein PNG")
    p, idat, plte = 8, [], b""
    w = h = tiefe = typ = interlace = None
    while p + 8 <= len(roh):
        laenge, art = struct.unpack(">I4s", roh[p:p + 8])
        inhalt = roh[p + 8:p + 8 + laenge]
        if art == b"IHDR":
            w, h, tiefe, typ, _, _, interlace = struct.unpack(">IIBBBBB", inhalt)
        elif art == b"PLTE":
            plte = inhalt
        elif art == b"IDAT":
            idat.append(inhalt)
        elif art == b"IEND":
            break
        p += 12 + laenge
    if not w or interlace:
        raise Fehler("PNG mit Zeilensprung (interlaced) wird nicht unterstuetzt")
    daten = b"".join(idat)
    if typ in (0, 2, 3):
        farben = {0: 1, 2: 3, 3: 1}[typ]
        raum = {0: "/DeviceGray", 2: "/DeviceRGB"}.get(typ) or "[/Indexed /DeviceRGB %d <%s>]" % (
            len(plte) // 3 - 1, plte.hex())
        return {"w": w, "h": h, "dict": "/ColorSpace %s /BitsPerComponent %d /Filter /FlateDecode /DecodeParms "
                "<< /Predictor 15 /Colors %d /BitsPerComponent %d /Columns %d >>" % (raum, tiefe, farben, tiefe, w),
                "daten": daten, "maske": None}
    if typ in (4, 6) and tiefe == 8:
        if w * h > MAX_BILDPUNKTE:
            raise Fehler("PNG mit Transparenz ist zu gross (%d Megapixel)" % (w * h // 1_000_000))
        bpp = 2 if typ == 4 else 4
        pixel = _entfiltern(zlib.decompress(daten), w, h, bpp)
        farbe = bytes(pixel[i] for i in range(len(pixel)) if i % bpp != bpp - 1) if bpp == 2 else \
            b"".join(bytes(pixel[i:i + 3]) for i in range(0, len(pixel), 4))
        alpha = bytes(pixel[bpp - 1::bpp])
        return {"w": w, "h": h, "dict": "/ColorSpace %s /BitsPerComponent 8 /Filter /FlateDecode" % (
            "/DeviceGray" if typ == 4 else "/DeviceRGB"), "daten": zlib.compress(farbe, 6),
            "maske": zlib.compress(alpha, 6)}
    raise Fehler("PNG mit %d Bit Tiefe (Typ %d) wird nicht unterstuetzt" % (tiefe, typ))


def bild_lesen(roh):
    if roh[:3] == b"\xff\xd8\xff":
        return _jpeg(roh)
    if roh[:8] == b"\x89PNG\r\n\x1a\n":
        return _png(roh)
    raise Fehler("Bilder gehen als JPEG oder PNG in ein PDF")


# ------------------------------------------------------------------ Zusammenbau

def _pdf_text(s):
    """Zeichenkette fuer das Info-Woerterbuch: ASCII direkt, sonst UTF-16BE mit BOM."""
    s = str(s)[:200]
    try:
        s.encode("ascii")
        return "(%s)" % s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    except UnicodeEncodeError:
        return "<FEFF%s>" % s.encode("utf-16-be").hex().upper()


def erstellen(titel="", text="", bilder=(), autor="Jarvis"):
    """-> (PDF-Bytes, Seitenzahl). bilder: JPEG/PNG-Bytes, je eine Seite."""
    # Nur Bilder ("Foto als PDF"): der Titel steht dann nur in den Metadaten, keine leere Titelseite davor
    hat_text = str(text or "").strip() or (str(titel or "").strip() and not bilder)
    textseiten = _text_seiten(titel, text) if hat_text else []
    bildinfo = [bild_lesen(b) for b in bilder]
    gesamt = len(textseiten) + len(bildinfo)
    if not gesamt:
        raise Fehler("Kein Inhalt fuer das PDF")
    objekte = []                              # Index + 1 = Objektnummer

    def neu(inhalt):
        objekte.append(inhalt)
        return len(objekte)

    def strom(dict_text, daten):
        return ("<< %s /Length %d >>\nstream\n" % (dict_text, len(daten))).encode() + daten + b"\nendstream"

    katalog = neu(None)
    seitenbaum = neu(None)
    f1 = neu(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = neu(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    kinder = []

    def fuss(nr):
        t = _cp("%d / %d" % (nr, gesamt))
        x = (A4_B - _breite(t, False, 8.5)) / 2
        return "BT 0.45 g /F1 8.5 Tf %.2f %.2f Td (%s) Tj ET" % (x, RAND / 2, _esc(t))

    nr = 0
    for cmds in textseiten:
        nr += 1
        inhalt = zlib.compress(("\n".join(cmds + [fuss(nr)])).encode("latin-1"), 6)
        c = neu(strom("/Filter /FlateDecode", inhalt))
        kinder.append(neu(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Resources << /Font << /F1 %d 0 R "
                           "/F2 %d 0 R >> >> /Contents %d 0 R >>" % (seitenbaum, A4_B, A4_H, f1, f2, c)).encode()))
    for b in bildinfo:
        nr += 1
        maske = ""
        if b["maske"] is not None:
            m = neu(strom("/Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
                          "/BitsPerComponent 8 /Filter /FlateDecode" % (b["w"], b["h"]), b["maske"]))
            maske = " /SMask %d 0 R" % m
        bild = neu(strom("/Type /XObject /Subtype /Image /Width %d /Height %d %s%s" % (b["w"], b["h"], b["dict"], maske),
                         b["daten"]))
        mb, mh = A4_B - 2 * RAND, A4_H - 2 * RAND - 10
        s = min(mb / b["w"], mh / b["h"])
        bw, bh = b["w"] * s, b["h"] * s
        x, y = (A4_B - bw) / 2, (A4_H - bh) / 2 + 5
        inhalt = zlib.compress(("q %.2f 0 0 %.2f %.2f %.2f cm /Bild Do Q\n%s" % (bw, bh, x, y, fuss(nr))).encode(), 6)
        c = neu(strom("/Filter /FlateDecode", inhalt))
        kinder.append(neu(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Resources << /Font << /F1 %d 0 R "
                           ">> /XObject << /Bild %d 0 R >> >> /Contents %d 0 R >>" % (
                               seitenbaum, A4_B, A4_H, f1, bild, c)).encode()))
    objekte[katalog - 1] = ("<< /Type /Catalog /Pages %d 0 R >>" % seitenbaum).encode()
    objekte[seitenbaum - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (
        " ".join("%d 0 R" % k for k in kinder), len(kinder))).encode()
    jetzt = time.strftime("D:%Y%m%d%H%M%S")
    info = neu(("<< /Title %s /Author %s /Producer (Jarvis) /CreationDate (%s) >>" % (
        _pdf_text(titel or "Dokument"), _pdf_text(autor), jetzt)).encode())
    aus = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
    lagen = []
    for i, o in enumerate(objekte, 1):
        lagen.append(len(aus))
        aus += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(aus)
    aus += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1)
    for l in lagen:
        aus += b"%010d 00000 n \n" % l
    aus += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objekte) + 1, katalog, info, xref)
    return bytes(aus), gesamt
