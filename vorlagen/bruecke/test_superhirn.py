"""Test des Superhirn-Registers (seit 0.7): alle zehn Module laden, gemeinsame Pflichtfelder, Lautsprecher-Sperre
(LAUTSPRECHER_PRIVAT, Fund F1 eines Claude-Security-Scans), Sprache fuer Denkaufrufe und Module auf einmal, englische
Meldungen von denken.py. Ohne Netz, ohne Claude, ohne Docker. Python 3.8."""
import os
import shutil
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import denken  # noqa: E402
import superhirn  # noqa: E402

stand = {"ok": 0, "fehler": 0}


def pruef(name, bed, info=""):
    stand["ok" if bed else "fehler"] += 1
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:300]) if info and not bed else ""))


m = superhirn.module()
pruef("alle zehn Module laden", sorted(m) == sorted(superhirn.NAMEN), sorted(set(superhirn.NAMEN) - set(m)))
for n, mod in m.items():
    w = getattr(mod, "WERKZEUG", None) or {}
    pruef("%s: NAME, RECHTE, WERKZEUG, auftrag" % n, getattr(mod, "NAME", None) == n and
          getattr(mod, "RECHTE", None) in ("haupt", "familie") and isinstance(w.get("beschreibung"), str) and
          isinstance(w.get("schema"), dict) and callable(getattr(mod, "auftrag", None)))
    pruef("%s: LAUTSPRECHER_PRIVAT ist frozenset, setze_sprache da" % n,
          isinstance(getattr(mod, "LAUTSPRECHER_PRIVAT", None), frozenset) and callable(getattr(mod, "setze_sprache", None)))

SOLL = {"kabinett": {"liste", "zeigen"}, "nachtschicht": {"heute", "jetzt"}, "zeitkapsel": {"liste", "archiv"},
        "weltwache": {"liste"}}
for n, mod in m.items():
    pruef("%s: private Aktionen wie festgelegt" % n, set(mod.LAUTSPRECHER_PRIVAT) == SOLL.get(n, set()),
          sorted(mod.LAUTSPRECHER_PRIVAT))
pruef("lautsprecher_privat: Schreibweise egal", superhirn.lautsprecher_privat(m["zeitkapsel"], " Archiv ")
      and superhirn.lautsprecher_privat(m["kabinett"], "LISTE"))
pruef("lautsprecher_privat: leere Aktion = Standardaktion (zeitkapsel, weltwache: liste)",
      superhirn.lautsprecher_privat(m["zeitkapsel"], "") and superhirn.lautsprecher_privat(m["weltwache"], None))
pruef("lautsprecher_privat: Anlegen per Sprache bleibt frei",
      not superhirn.lautsprecher_privat(m["zeitkapsel"], "neu") and not superhirn.lautsprecher_privat(m["ablageort"], ""))
offen = ("alexa", "ALEXA", "test-alexa", "ha", "test-ha", "ha-satellit", "voice", "voice-pe", " voice-kueche ")
eigen = ("app", "app-extern", "pc", "webapp", "pc-sprache", "routine", "", None)
pruef("offener_lautsprecher: Alexa, HA, Sprach-Satelliten", all(superhirn.offener_lautsprecher(q) for q in offen),
      [q for q in offen if not superhirn.offener_lautsprecher(q)])
pruef("offener_lautsprecher: eigene Geraete nicht", not any(superhirn.offener_lautsprecher(q) for q in eigen),
      [q for q in eigen if superhirn.offener_lautsprecher(q)])
try:
    import faeden
    # mindestens so streng wie faeden.quelle_gesperrt (das Register schneidet zusaetzlich Leerzeichen am Rand ab)
    pruef("sperrt alles, was faeden.quelle_gesperrt sperrt",
          all(superhirn.offener_lautsprecher(q) for q in offen + eigen[:-1] if faeden.quelle_gesperrt(q))
          and not any(faeden.quelle_gesperrt(q) for q in eigen[:-1]))
except ImportError:
    print("SKIP faeden.py nicht daneben")

# Sprache auf einmal
superhirn.setze_sprache("en")
pruef("setze_sprache(en): denken und alle Module", denken.SPRACHE == "en" and
      all(getattr(x, "SPRACHE", "en") == "en" for x in m.values()), {n: getattr(x, "SPRACHE", "?") for n, x in m.items()})
pruef("EN: Werkzeugbeschreibungen englisch (kein ä/ö/ü/ß)",
      all(not any(c in x.WERKZEUG["beschreibung"] for c in "äöüß") for x in m.values()),
      [n for n, x in m.items() if any(c in x.WERKZEUG["beschreibung"] for c in "äöüß")])
tmp = tempfile.mkdtemp(prefix="sh-test-")
alt = denken.TAGESLIMIT_USD
try:
    denken.TAGESLIMIT_USD = 0.01
    try:
        denken._reservieren(tmp, "test", 0.5)
        meldung = ""
    except denken.Abgelehnt as e:
        meldung = str(e)
    pruef("EN: Tageslimit-Meldung englisch", meldung.startswith("Daily limit for thinking reached"), meldung)
    superhirn.setze_sprache("de")
    try:
        denken._reservieren(tmp, "test", 0.5)
        meldung = ""
    except denken.Abgelehnt as e:
        meldung = str(e)
    pruef("DE: Tageslimit-Meldung wie bisher", meldung.startswith("Tageslimit fürs Nachdenken erreicht"), meldung)
finally:
    denken.TAGESLIMIT_USD = alt
    shutil.rmtree(tmp, ignore_errors=True)
pruef("setze_sprache(de): alles zurueck", denken.SPRACHE == "de" and
      all(getattr(x, "SPRACHE", "de") == "de" for x in m.values()))
try:
    superhirn.setze_sprache("fr")
    pruef("andere Sprache abgelehnt", False)
except ValueError:
    pruef("andere Sprache abgelehnt", denken.SPRACHE == "de")

print("\nSuperhirn-Register: %d ok, %d Fehler" % (stand["ok"], stand["fehler"]))
sys.exit(1 if stand["fehler"] else 0)
