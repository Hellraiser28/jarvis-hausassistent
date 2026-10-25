#!/usr/bin/env python3
"""Einheitentests fuer bruecke/verhalten.py"""
import os
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HIER, os.path.join(os.path.dirname(HIER), "bruecke")]   # Paket/Vorlagen: daneben, Repo: ../bruecke
import verhalten as vh  # noqa: E402

ok = fehler = 0


def pruef(name, b):
    global ok, fehler
    if b:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name)


def wirft(name, f):
    global ok, fehler
    try:
        f()
    except vh.Ungueltig:
        ok += 1
        return
    fehler += 1
    print("FEHLER (keine Ablehnung):", name)


s = vh.pruefen({})
pruef("Standard = bisheriges Verhalten", s == vh.STANDARD)
pruef("Nachtruhe aus: nie", not any(vh.nachtruhe_jetzt(s, h) for h in range(24)))
n = vh.aendern(s, {"nachtruhe": "an"})
pruef("22-7: 23 Uhr ruhig", vh.nachtruhe_jetzt(n, 23))
pruef("22-7: 3 Uhr ruhig", vh.nachtruhe_jetzt(n, 3))
pruef("22-7: 7 Uhr wach", not vh.nachtruhe_jetzt(n, 7))
pruef("22-7: 21 Uhr wach", not vh.nachtruhe_jetzt(n, 21))
m = vh.aendern(n, {"nachtruhe_von": 13, "nachtruhe_bis": 15})
pruef("13-15 Mittagsruhe: 14 ruhig, 15 wach", vh.nachtruhe_jetzt(m, 14) and not vh.nachtruhe_jetzt(m, 15))
pruef("kurz", vh.aendern(s, {"antwortstil": "kurz"})["antwortstil"] == "kurz")
wirft("unbekannter Stil", lambda: vh.aendern(s, {"antwortstil": "frech"}))
wirft("unbekannter Schluessel", lambda: vh.aendern(s, {"kennwort": "x"}))
wirft("Stunde 24", lambda: vh.aendern(s, {"nachtruhe_von": 24}))
wirft("Stunde als Text", lambda: vh.aendern(s, {"nachtruhe_bis": "7"}))
wirft("Stunde als bool", lambda: vh.aendern(s, {"nachtruhe_bis": True}))
wirft("gleiche Stunden", lambda: vh.aendern(s, {"nachtruhe_von": 7, "nachtruhe_bis": 7}))
wirft("leer", lambda: vh.aendern(s, {}))
d = tempfile.mkdtemp()
p = os.path.join(d, "verhalten.json")
pruef("fehlende Datei = Standard", vh.laden(p) == vh.STANDARD)
vh.speichern(p, n)
# Windows kennt kein 600 (dort schuetzen Ordnerrechte, siehe Bauanleitung): Rechte nur anderswo pruefen
pruef("gespeichert, 600", vh.laden(p) == n and (os.name == "nt" or oct(os.stat(p).st_mode & 0o777) == "0o600"))
open(p, "w").write('{"antwortstil": "wild"}')
pruef("kaputte Datei = Standard", vh.laden(p) == vh.STANDARD)
print("Beschreibung:", vh.beschreiben(n))
pruef("optionen: je Schalter die Werte", vh.optionen() == {k: list(w) for k, w in vh.WERTE.items()}
      and all(isinstance(w, list) and w for w in vh.optionen().values()))
vh.setze_sprache("en")
pruef("en: Stil englisch", vh.STIL["kurz"].startswith("Answer style: short"))
pruef("en: Beschreibung englisch", vh.beschreiben(vh.STANDARD).startswith("Interim phrases: on."))
try:
    vh.pruefen({"antwortstil": "wild"})
    pruef("en: Meldung englisch", False)
except vh.Ungueltig as x:
    pruef("en: Meldung englisch", "kurz or normal or ausfuehrlich" in str(x))
vh.setze_sprache("de")
pruef("de: Stil wieder deutsch", vh.STIL["kurz"].startswith("Antwortstil: kurz"))
print("%d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
