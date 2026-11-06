"""Superhirn (seit 0.7): Register der zehn Module und gemeinsame Einhaengung.

Jedes Modul bruecke/<name>.py liefert NAME, RECHTE, WERKZEUG {beschreibung, schema}, FREMDTEXT, auftrag(b, person, ctx),
optional runde(ctx) mit TAKT_S und seite(pfad, abfrage, ctx, oeffentlich). Die Bruecke baut den Kontext ctx und ruft
die Module ueber /intern/sh/<name>; der Werkzeug-Server erzeugt daraus die MCP-Werkzeuge (siehe werkzeuge()).
Python 3.8, nur Standardbibliothek; Import ohne Nebenwirkungen.
"""
import importlib
import threading
import time

NAMEN = ("schmiede", "kabinett", "familienrunde", "nachtschicht", "weltwache", "zeigen", "ablageort", "lernbegleiter",
         "abenteuer", "zeitkapsel")
_module = {}
_letzte_runde = {}
_runden_sperre = threading.Lock()


def module():
    """name -> Modul (nur die, die es im Stand gibt und die sich laden lassen)."""
    if not _module:
        for n in NAMEN:
            try:
                _module[n] = importlib.import_module(n)
            except ImportError:
                continue
    return dict(_module)


def lesende_aktionen(m):
    """(Parametername, Standardaktion, Menge lesender Aktionen) aus FREMDTEXT, oder None."""
    nl = (getattr(m, "FREMDTEXT", None) or {}).get("nur_lesen")
    if not nl:
        return None
    return nl[0], nl[1], frozenset(nl[2])


def setze_sprache(sprache):
    """Seit 0.7: Sprache ("de" oder "en") fuer die Denkaufrufe und alle geladenen Module auf einmal. Die Bruecke ruft das
    beim Start, nach dem Laden der Module (wie setze_sprache der uebrigen Bausteine)."""
    import denken
    denken.setze_sprache(sprache)
    for m in module().values():
        f = getattr(m, "setze_sprache", None)
        if callable(f):
            f(sprache)


# Seit 0.7 (Fund F1 eines Claude-Security-Scans): Ueber gemeinsame Lautsprecher (Alexa, die Sprachkette von Home
# Assistant, Sprach-Satelliten) gilt jeder Sprecher als die Person des Geraets, meist die Hauptperson. Wer davor steht,
# hoerte sonst ihre privaten Dinge (Kabinett-Liste, Nachtschicht, Zeitkapsel-Archiv, die Liste der Welt-Wachen). Jedes
# Modul nennt diese Aktionen in LAUTSPRECHER_PRIVAT; die Bruecke fragt vor jedem Auftrag:
#     if superhirn.offener_lautsprecher(quelle) and superhirn.lautsprecher_privat(modul, aktion): ablehnen
# Dieselben Quellen sperrt faeden.quelle_gesperrt (offene Faeden).
OFFEN_SPRACHE = ("alexa", "test-alexa", "ha", "test-ha", "voice", "voice-pe")


def offener_lautsprecher(quelle):
    """Kommt die Frage ueber einen Lautsprecher, den alle hoeren koennen (auch kuenftige voice-*/ha-*-Quellen)?"""
    q = str(quelle or "").strip().lower()
    return q in OFFEN_SPRACHE or q.startswith(("alexa", "ha-", "voice"))


def lautsprecher_privat(m, aktion):
    """Gehoert diese Aktion des Moduls nie auf einen gemeinsamen Lautsprecher? Normalisiert wie die Module (" Liste " =
    "liste"); eine leere Aktion ist die Standardaktion aus FREMDTEXT (z. B. zeitkapsel: "liste")."""
    a = str(aktion or "").strip().lower()
    if not a:
        nl = lesende_aktionen(m)
        a = nl[1] if nl else ""
    return a in (getattr(m, "LAUTSPRECHER_PRIVAT", None) or frozenset())


def nur_lesend(m, args):
    """Ist dieser Aufruf rein lesend (fuer Testlaeufe und Fremdtext)?"""
    art = (getattr(m, "FREMDTEXT", None) or {}).get("art")
    if art in ("lesend", "quelle"):
        return True
    nl = lesende_aktionen(m)
    return bool(nl) and str((args or {}).get(nl[0], nl[1])) in nl[2]


_modul_sperren = {}


def _eine_runde(n, f, ctx, log, sperre):
    try:
        f(ctx)
    except Exception as x:
        log("Superhirn-Runde %s:" % n, type(x).__name__, str(x)[:200])
    finally:
        sperre.release()


def runden(ctx_fuer, log, jetzt=None, faden=True):
    """Aus der Hintergrund-Schleife: runde(ctx) jedes Moduls, das faellig ist (TAKT_S), je Modul in einem eigenen
    Faden (ein langer Welt-Wache-Lauf haelt die anderen nicht auf). Ein Modul laeuft nie zweimal gleichzeitig; ein
    Modulfehler stoppt die anderen nicht. faden=False (Tests): nacheinander im aufrufenden Faden."""
    jetzt = jetzt or time.time()
    gestartet = []
    with _runden_sperre:
        for n, m in module().items():
            f, takt = getattr(m, "runde", None), getattr(m, "TAKT_S", None)
            if not callable(f) or not takt or jetzt - _letzte_runde.get(n, 0) < takt:
                continue
            sp = _modul_sperren.setdefault(n, threading.Lock())
            if not sp.acquire(blocking=False):
                continue                     # laeuft noch vom letzten Mal
            _letzte_runde[n] = jetzt
            gestartet.append((n, f, sp))
    for n, f, sp in gestartet:
        if faden:
            threading.Thread(target=_eine_runde, args=(n, f, ctx_fuer(None), log, sp), daemon=True,
                             name="superhirn-" + n).start()
        else:
            _eine_runde(n, f, ctx_fuer(None), log, sp)
    return [n for n, _, _ in gestartet]


def seite(pfad, abfrage, ctx_fuer, oeffentlich):
    """Eigene Webseiten der Module (z. B. runde/<token>, zeigen/<id>): erstes Modul, das antwortet.
    -> (code, content_type, bytes, kopfzeilen) oder None. Die Module liefern (code, typ, bytes); die Kopfzeilen (CSP
    u. a.) kommen aus SEITE_KOPFZEILEN bzw. KOPFZEILEN des Moduls, das geantwortet hat."""
    for n, m in module().items():
        f = getattr(m, "seite", None)
        if not callable(f):
            continue
        r = f(pfad, abfrage, ctx_fuer(None), oeffentlich)
        if r:
            kopf = getattr(m, "SEITE_KOPFZEILEN", None) or getattr(m, "KOPFZEILEN", None) or {}
            return r[0], r[1], r[2], dict(kopf)
    return None
