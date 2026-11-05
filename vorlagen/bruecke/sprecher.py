"""Stimmerkennung in der Bruecke (seit 0.6): wer spricht, eine Person des Haushalts oder jemand Fremdes? Python 3.8
ohne Zusatzpakete; die Erkennung selbst macht der Dienst jarvis-sprecher (Vorlage vorlagen/sprecher/), erreichbar nur
ueber 127.0.0.1.

Wo es Audio gibt: Home Assistant (Sprachassistent, z. B. Voice PE) ueber die Wyoming-Durchreiche des Dienstes, der PC
ueber /v1/hoer. Die Handy-App erkennt Sprache auf dem Geraet und schickt nur Text; dort bestimmt das Geraet die Person.
Alexa liefert kein Audio.

Grundsatz: Die Stimme kann Rechte nur EINSCHRAENKEN, nie anheben (Stimmklone erreichen die Person, siehe Dienst).
Seit der unabhaengigen Pruefung (Befunde 1-3) noch enger, weil Postfach, Dokumente und Gedaechtnis jeder Person
einzeln gehoeren: Die Stimme wechselt nur in Rollen ohne fremde Privatdaten, also zu "unbekannt" (fremde Stimme:
keine Werkzeuge, nur Gespraech) oder zu einem Gast. Familie und Hauptperson werden nur protokolliert, die Person
bleibt die des Geraets. Im Gastraum bleibt der Gast Gast. Am PC (Geraet der Hauptperson) vorerst gar nicht.
RANG und WECHSEL_ROLLEN fuehren zusaetzlich eine Rolle "kind". personen.py kennt sie nicht und uebergeht Eintraege
mit ihr; sie greift erst, wenn eine Einrichtung sie in personen.py ergaenzt.
Ein Wechsel bekommt einen eigenen Gespraechsfaden (Bruecke: Geraetename mit #person), damit nichts mitwandert.

Modus (.env STIMMEN_MODUS): aus (Standard), zeigen (nur Protokoll und Verlauf, Person bleibt), anwenden.
STIMMEN_STRENG=1: ohne sichere Erkennung am Lautsprecher wie eine fremde Stimme.
Stimmprofile sind biometrische Daten: angelernt wird nur mit ausdruecklicher Zustimmung der Person (bei Kindern der
Eltern), die Profile bleiben auf dem eigenen Rechner (Dienst, SPRECHER_PROFILE).
"""
import json
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

URL = "http://127.0.0.1:10320"
MODI = ("aus", "zeigen", "anwenden")
GETEILT = ("ha", "test-ha")              # Sprachgeraete im Raum
EIGEN = ()                               # PC vorerst nicht (Befund 1: ein Token koennte fremde Aufnahmen einspielen)
RANG = {"haupt": 4, "familie": 3, "kind": 2, "gast": 1}
WECHSEL_ROLLEN = ("kind", "gast")        # nur in diese Rollen wechselt die Stimme ("kind" nur, wenn personen.py es kennt)
TOKEN = ""                               # SPRECHER_TOKEN, setzt die Bruecke beim Start
HOER_MAX_S = 90
NAME = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")

_hoer = {}
_s = threading.Lock()


# Sprache der Texte, die die Person sieht (Fehler beim Anlernen) und der Gruende im Protokoll (Modus zeigen). Die
# Bruecke setzt sie beim Start aus der Einrichtung (antworten.json "sprache"), wie bei szenen.py.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


class Fehler(Exception):
    """erreichbar=False: Der Dienst antwortet gar nicht (die Bruecke meldet dann 503, sonst 400). Als Merkmal statt
    am Wortlaut, weil der Text je nach Sprache wechselt."""

    def __init__(self, text, erreichbar=True):
        super().__init__(text)
        self.erreichbar = erreichbar


def vergleich(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _http(pfad, daten=None, timeout=4.0, methode=None):
    kopf = {"X-Sprecher-Token": TOKEN}
    if daten:
        kopf["Content-Type"] = "audio/wav"
    req = urllib.request.Request(URL + pfad, data=daten, method=methode or ("POST" if daten is not None else "GET"),
                                 headers=kopf)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode("utf-8"))
        except ValueError:
            d = {}
        if e.code == 404:
            return None
        raise Fehler(d.get("fehler") or _t("Stimmerkennung antwortet mit %d.",
                                           "Voice recognition answered with %d.") % e.code)
    except (OSError, ValueError) as e:
        raise Fehler(_t("Stimmerkennung nicht erreichbar (%s).",
                        "Voice recognition not reachable (%s).") % type(e).__name__, erreichbar=False)


def erkennen(wav):
    """Ergebnis des Dienstes oder None (nicht erreichbar, Fehler): die Frage laeuft dann wie bisher."""
    try:
        return _http("/erkennen", wav, timeout=4)
    except Fehler:
        return None


def zuletzt(text, max_s=20, client=None, warten_s=2.0, uhr=time.time, schlaf=time.sleep):
    """Ergebnis der Wyoming-Durchreiche zu genau diesem Text, nur vom erwarteten Geraet (client = IP, Befund 5). Wartet
    bis warten_s, weil die Erkennung kurz nach dem Text fertig wird (Befund 4)."""
    ende = uhr() + warten_s
    while True:
        try:
            r = _http("/zuletzt?" + urllib.parse.urlencode({"text": text, "max_s": max_s}), timeout=2)
        except Fehler:
            return None
        if r and (client is None or r.get("client") == client):
            return r
        if uhr() >= ende:
            return None
        schlaf(0.4)


def anlernen(person, wav):
    if not NAME.match(person or ""):
        raise Fehler(_t("Ungültiger Personenname.", "Invalid person name."))
    return _http("/anlernen?" + urllib.parse.urlencode({"person": person}), wav, timeout=30)


def vergessen(person):
    if not NAME.match(person or ""):
        raise Fehler(_t("Ungültiger Personenname.", "Invalid person name."))
    return _http("/vergessen?" + urllib.parse.urlencode({"person": person}), b"", timeout=10)


def profile():
    return _http("/profile", timeout=5)


def hoer_merken(besitzer, text, erg, uhr=time.time):
    """/v1/hoer: Ergebnis zum Text merken; die Frage mit diesem Text kommt gleich als /v1/frage vom selben Geraet."""
    if not erg or not text:
        return
    with _s:
        jetzt = uhr()
        for k in [k for k, v in _hoer.items() if jetzt - v["zeit"] > HOER_MAX_S]:
            _hoer.pop(k, None)
        _hoer[besitzer or "haupt"] = {"text": vergleich(text), "zeit": jetzt, "erg": dict(erg)}


def hoer_finden(besitzer, text, uhr=time.time):
    with _s:
        e = _hoer.get(besitzer or "haupt")
        if e and uhr() - e["zeit"] <= HOER_MAX_S and e["text"] and e["text"] == vergleich(text):
            _hoer.pop(besitzer or "haupt", None)        # gilt fuer genau eine Frage
            return e["erg"]
    return None


def entscheiden(modus, quelle, standard, erg, rollen, unbekannt, streng=False):
    """-> (person, grund). standard: Person laut Geraet/Raum. rollen: {person: rolle} aus personen.json.
    Wechsel nur zu unbekannt oder in eine Rolle aus WECHSEL_ROLLEN (aus personen.py: Gast) und nur nach unten; streng
    (STIMMEN_STRENG=1): ohne sichere Erkennung (kein Ergebnis, zu kurz, unsicher) wie fremd. Profile ohne Person (z. B.
    jemand, der angelernt, aber nicht in personen.json eingetragen ist) zaehlen wie fremd."""
    if modus != "anwenden" or quelle not in GETEILT + EIGEN:
        return standard, ""
    rang = lambda p: RANG.get(rollen.get(p), 0)          # noqa: E731
    gast_oder_weniger = rang(standard) <= RANG["gast"]
    stufe, wer = (erg or {}).get("stufe"), (erg or {}).get("person")
    if stufe == "sicher" and wer:
        if wer == standard:
            return standard, _t("Stimme bestätigt", "Voice confirmed")
        if wer in rollen and rollen.get(wer) in WECHSEL_ROLLEN and rang(wer) < rang(standard):
            return wer, _t("Stimme: %s", "Voice: %s") % wer
        if wer in rollen:
            return standard, _t("Stimme %s erkannt, Person bleibt (gewechselt wird nur nach unten, etwa zu einem Gast)",
                                "Voice %s recognized, person stays (switching only downwards, e.g. to a guest)") % wer
        stufe = "fremd"
    if stufe == "fremd" or (streng and stufe in (None, "zu_kurz", "unsicher")):
        if quelle in GETEILT and not gast_oder_weniger:
            return unbekannt, (_t("fremde Stimme", "unknown voice") if stufe == "fremd" else
                               _t("keine sichere Stimme (streng)", "no reliable voice (strict)"))
        return standard, (_t("fremde Stimme, Gast bleibt Gast", "unknown voice, guest stays guest")
                          if gast_oder_weniger else "")
    return standard, _t("Stimme %s, Gerät bleibt", "Voice %s, device stays") % (stufe or _t("keine", "none"))
