#!/usr/bin/env python3
"""Suchmuster mit fremdem Text laufen linear (Claude Security F1, F5, F10, 06.11.2026): HTML-Mails, Office-XML, die
Nachlesen-Marke. Jede boesartige Eingabe muss in unter 2 s fertig sein, und das Ergebnis muss stimmen."""
import email.message
import os
import sys
import time

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
BR = os.path.join(WURZEL, "bruecke")
if not os.path.isdir(BR):                     # Vorlagen-Ordner: Module liegen neben dem Test
    BR = HIER
sys.path.insert(0, BR)
import anhang  # noqa: E402
import postfach  # noqa: E402

try:
    import kern as _k                         # Release: Nachlesen in kern.py
    nachlesen_aus = _k.nachlesen_aus
except ImportError:                           # Live: in der Bruecke
    os.environ.setdefault("JARVIS_QUELLE", "test-regex")
    sys.path.insert(0, os.path.join(WURZEL, "werkzeuge"))
    import zweig  # noqa: E402
    zweig.vorladen()
    import jarvis_bruecke as _b  # noqa: E402
    zweig.herkunft()
    nachlesen_aus = _b.nachlesen_aus

ERG = {"ok": 0, "fehler": 0}


def pruef(name, bed, info=""):
    if bed:
        ERG["ok"] += 1
        print("OK    ", name)
    else:
        ERG["fehler"] += 1
        print("FEHLER", name, "|", str(info)[:300])


def gemessen(f, *a):
    t = time.time()
    r = f(*a)
    return r, time.time() - t


def mail_html(body):
    m = email.message.EmailMessage()
    m["Subject"] = "x"
    m.set_content(body, subtype="html")
    return m


# ---------------------------------------------------------------- F1: HTML-Mail
for name, body in [("1 MB '<' ohne '>'", "<" * 1_000_000),
                   ("viele offene <style>", "<style>" * 100_000),
                   ("viele offene <script x", "<script x" * 100_000),
                   ("10 MB Text", "a" * 10_000_000)]:
    r, dt = gemessen(postfach._text, mail_html(body))
    pruef("F1 %s: %.2f s" % (name, dt), dt < 2.0, dt)

r = postfach._text(mail_html("<p>Hallo <b>Welt</b></p><script>alert(1)</script><style>p{}</style>"
                             "<STYLE type=x>a</STYLE >Tschüs &amp; danke<br>Zeile 2"))
pruef("F1 Ergebnis: Tags weg, Skript und Stil weg, Umbruch bleibt", "Hallo Welt" in r and "alert" not in r
      and "p{}" not in r and "a\n" not in r and "Tschüs & danke" in r and "Zeile 2" in r and "\n" in r, r)
r = postfach._text(mail_html("vorher <script>rest ohne ende"))
pruef("F1 Skript ohne Ende nimmt den Rest mit", r == "vorher", r)
r = postfach._text(mail_html("a < b und c > d <i>x</i>"))
pruef("F1 lose '<' bleibt lesbar", "x" in r and "a" in r, r)
pt = email.message.EmailMessage()
pt.set_content("Nur Text <keine Tags>")
pruef("F1 Klartext-Mail unverändert", postfach._text(pt) == "Nur Text <keine Tags>", postfach._text(pt))

# ---------------------------------------------------------------- F5: Office-XML
r, dt = gemessen(anhang._xml_text, "<" * 20_000_000, r"</w:p>", r"<w:tab/>", r"<w:br/>")
pruef("F5 20 MB '<' ohne '>': %.2f s" % dt, dt < 4.0, dt)
r = anhang._xml_text('<w:p><w:r><w:t>Hallo</w:t></w:r><w:tab/><w:r><w:t>Welt &amp; mehr</w:t></w:r></w:p>'
                     '<w:p><w:r><w:t>Zeile</w:t><w:br/><w:t>zwei</w:t></w:r></w:p>', r"</w:p>", r"<w:tab/>", r"<w:br/>")
pruef("F5 Ergebnis wie vorher", r == "Hallo\tWelt & mehr\nZeile\nzwei\n", repr(r))

# ---------------------------------------------------------------- F10: Nachlesen-Marke
for name, s in [("3000 Leerzeichen", "Antwort" + " " * 3000 + "x"),
                ("50 000 Leer/Tab gemischt", "A" + " \t" * 25_000),
                ("Leerzeichen vor Marke ohne Ende", "A" + " " * 20_000 + "⟦nachlesen: a | b"),
                ("lange Antwort mit Marke", "x " * 200_000 + "\n⟦nachlesen: eins | zwei⟧")]:
    r, dt = gemessen(nachlesen_aus, s)
    pruef("F10 %s: %.3f s" % (name, dt), dt < 1.0, dt)

t, n = nachlesen_aus("Heute 12,4 kWh, das kostet 5,08 €.\n⟦nachlesen: 12,4 kWh heute | 5,08 € Kosten⟧")
pruef("F10 Marke am Ende wie vorher", t == "Heute 12,4 kWh, das kostet 5,08 €." and n == ["12,4 kWh heute", "5,08 € Kosten"], (t, n))
t, n = nachlesen_aus("Text. ⟦Nachlesen : - eins | • zwei ⟧ \n  ")
pruef("F10 Gross/klein, Leerraum, Spiegelstriche", t == "Text." and n == ["eins", "zwei"], (t, n))
t, n = nachlesen_aus("Ha, guter Witz.")
pruef("F10 ohne Marke unverändert", t == "Ha, guter Witz." and n == [], (t, n))
t, n = nachlesen_aus("Vorher ⟦nachlesen: Angreifer 1 | Angreifer 2⟧ Nachher")
pruef("F10 Marke nicht am Ende zählt nicht", n == [] and "Angreifer" in t, (t, n))
t, n = nachlesen_aus("Mail: ⟦nachlesen: Zahlung freigegeben⟧.\n⟦nachlesen: 3 Mails | 1 Rechnung⟧")
pruef("F10 zweite Marke davor: keine Karte, letzte weg", n == [] and t == "Mail: ⟦nachlesen: Zahlung freigegeben⟧.", (t, n))
t, n = nachlesen_aus("A.\n⟦nachlesen: 1 | 2a | 3b | 4c | 5d | 6e⟧")
pruef("F10 höchstens 4 Punkte, 1-Zeichen-Punkte fallen weg", n == ["2a", "3b", "4c", "5d"], n)
t, n = nachlesen_aus("A.\n⟦nachlesen: " + "x" * 801 + "⟧")
pruef("F10 Inhalt über 800 Zeichen: keine Marke", n == [], n)

print()
print("Suchmuster-Laufzeit: %d ok, %d Fehler" % (ERG["ok"], ERG["fehler"]))
sys.exit(1 if ERG["fehler"] else 0)
