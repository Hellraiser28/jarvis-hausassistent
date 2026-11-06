"""Beobachter „Sag mir Bescheid, wenn …“ (seit 0.7).

Vorbild: Heliox-OS („Watchers“: „Sag mir, wenn Chrome schließt / der Download fertig ist“, gibt nach einem Tag auf).
Hier über Zustände in Home Assistant: „wenn die Waschmaschine fertig ist“, „wenn es draußen unter 0 Grad hat“,
„wenn sich am Garagentor etwas ändert“. Die Brücke prüft alle 30 s, meldet einmal an die fragende Person und
vergisst den Beobachter dann. Spätestens nach 24 Stunden verfällt er still.

Reine Logik ohne Netz: Zustände holt und Meldungen verschickt die Brücke über übergebene Funktionen (testbar).
auftrag() ist der Einstieg für das Werkzeug „beobachten“ (aktion neu|liste|loeschen): Es liest den Zustand beim
Anlegen über die übergebene Funktion und lehnt Kameras und Babyfone ab (die beobachtet Jarvis nie).

Zweisprachig (seit 0.7): Die Brücke setzt die Sprache beim Start (setze_sprache, aus antworten.json "sprache").
Bedingungen und Aktionen bleiben deutsche Schlüssel (gleich, nicht, unter, ueber, aendert; neu, liste, loeschen).
"""
import json
import os
import re
import threading
import time
import urllib.error

DATEI = "beobachter.json"
MAX_JE_PERSON = 10
MAX_STUNDEN = 24
BEDINGUNGEN = ("gleich", "nicht", "unter", "ueber", "aendert")
UNKLAR = ("unavailable", "unknown", "none", "")
# Nie beobachten: Bilder und Ton aus dem Haus (Kameras, Babyfon), auch nicht als „ändert sich“
GESPERRTE_DOMAENEN = ("camera", "image")
GESPERRTE_TEILE = ("babyfon", "kamera", "camera", "baby_monitor", "babymonitor", "babyphone")
_sperre = threading.Lock()

# Sprache der Texte, die die Person direkt sieht oder hört (seit 0.7). Die Brücke setzt sie beim Start aus der
# Einrichtung (antworten.json "sprache"), wie bei verhalten.py und szenen.py.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


def _pfad(daten):
    return os.path.join(daten, DATEI)


def _laden(daten):
    try:
        d = json.load(open(_pfad(daten), encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _speichern(daten, liste):
    tmp = _pfad(daten) + ".neu%d" % threading.get_ident()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _pfad(daten))


def _zahl(s):
    try:
        return float(str(s).replace(",", ".").strip())
    except ValueError:
        return None


def erfuellt(bedingung, wert, zustand, start=None):
    """Ist die Bedingung jetzt erfuellt? Unklare Zustaende (unavailable) erfuellen nie etwas, ausser man fragt genau danach."""
    z = str(zustand if zustand is not None else "").strip()
    werte = [w.strip().lower() for w in str(wert or "").split("|") if w.strip()]
    if z.lower() in UNKLAR and not (bedingung == "gleich" and z.lower() in werte):
        return False
    if bedingung == "gleich":
        return z.lower() in werte
    if bedingung == "nicht":
        return bool(werte) and z.lower() not in werte
    if bedingung == "aendert":
        return start is not None and z != str(start)
    a, b = _zahl(z), _zahl(wert)
    if a is None or b is None:
        return False
    return a < b if bedingung == "unter" else a > b


def beschreibung(e):
    w = e.get("wert", "")
    if SPRACHE == "en":
        return {"gleich": "is “%s”" % w, "nicht": "is no longer “%s”" % w, "unter": "drops below %s" % w,
                "ueber": "rises above %s" % w, "aendert": "changes"}.get(e.get("bedingung"), "?")
    return {"gleich": "auf „%s“ steht" % w, "nicht": "nicht mehr „%s“ ist" % w, "unter": "unter %s fällt" % w,
            "ueber": "über %s steigt" % w, "aendert": "sich ändert"}.get(e.get("bedingung"), "?")


def _stunden_text(stunden):
    s = "%g" % stunden
    return s if SPRACHE == "en" else s.replace(".", ",")


def neu(daten, person, entity_id, bedingung, wert, text, stunden, start, name="", jetzt=None):
    """(ok, Meldung). start = Zustand beim Anlegen (fuer 'aendert' und die Ansage)."""
    jetzt = jetzt or time.time()
    if bedingung not in BEDINGUNGEN:
        return False, _t("Bedingung muss eine von %s sein.", "bedingung must be one of %s.") % ", ".join(BEDINGUNGEN)
    if not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", str(entity_id or "")):
        return False, _t("Ich brauche eine gültige Entität (z. B. sensor.waschmaschine_status).",
                         "I need a valid entity (e.g. sensor.washing_machine_status).")
    if bedingung in ("unter", "ueber") and _zahl(wert) is None:
        return False, _t("Für „unter“ und „über“ brauche ich eine Zahl.", "For below and above I need a number.")
    if bedingung in ("gleich", "nicht") and not str(wert or "").strip():
        return False, _t("Auf welchen Zustand soll ich achten?", "Which state should I watch for?")
    try:
        stunden = float(stunden or MAX_STUNDEN)
    except (TypeError, ValueError):
        stunden = MAX_STUNDEN
    stunden = max(0.1, min(float(MAX_STUNDEN), stunden))
    if erfuellt(bedingung, wert, start, start) and bedingung != "aendert":
        return False, _t("Das ist jetzt schon so (%s steht auf „%s“).",
                         "That's already the case (%s is “%s”).") % (name or entity_id, start)
    with _sperre:
        liste = [e for e in _laden(daten) if e.get("bis", 0) > jetzt]
        if sum(1 for e in liste if e.get("person") == person) >= MAX_JE_PERSON:
            return False, _t("Du hast schon %d Beobachter laufen, lösch erst einen.",
                             "You already have %d watchers running, delete one first.") % MAX_JE_PERSON
        nr = max([e.get("nr", 0) for e in liste] + [0]) + 1
        e = {"nr": nr, "person": person, "entity_id": entity_id, "name": str(name or entity_id)[:80],
             "bedingung": bedingung, "wert": str(wert or "")[:60], "text": str(text or "").strip()[:300],
             "start": None if start is None else str(start)[:60], "seit": jetzt, "bis": jetzt + stunden * 3600}
        liste.append(e)
        _speichern(daten, liste)
    return True, _t("Mach ich: Ich sag dir Bescheid, sobald %s %s (Nr. %d, längstens %s h).",
                    "Will do: I'll let you know as soon as %s %s (no. %d, for at most %s h).") % (
        e["name"], beschreibung(e), nr, _stunden_text(stunden))


def liste(daten, person, jetzt=None):
    jetzt = jetzt or time.time()
    return [e for e in _laden(daten) if e.get("person") == person and e.get("bis", 0) > jetzt]


def loeschen(daten, person, nr=0):
    """nr=0: alle der Person. Meldung."""
    with _sperre:
        alt = _laden(daten)
        neu_liste = [e for e in alt if not (e.get("person") == person and (not nr or e.get("nr") == int(nr)))]
        weg = len(alt) - len(neu_liste)
        if weg:
            _speichern(daten, neu_liste)
    if not weg:
        return _t("Da war kein passender Beobachter.", "There was no matching watcher.")
    if SPRACHE == "en":
        return "%d watcher%s deleted." % (weg, "" if weg == 1 else "s")
    return "%d Beobachter gelöscht." % weg


def pruefen(daten, zustand_holen, melden, jetzt=None):
    """Einmal alle Beobachter pruefen. zustand_holen(entity_id) -> Zustand (str) oder wirft; melden(person, titel, text).
    Gibt die ausgeloesten Eintraege zurueck. Verfallene fallen still weg."""
    jetzt = jetzt or time.time()
    with _sperre:
        alle = _laden(daten)
    if not alle:
        return []
    bleiben, ausgeloest = [], []
    cache = {}
    for e in alle:
        if e.get("bis", 0) <= jetzt:
            continue
        eid = e.get("entity_id")
        if eid not in cache:
            try:
                cache[eid] = zustand_holen(eid)
            except Exception:
                cache[eid] = None
        z = cache[eid]
        if z is not None and erfuellt(e.get("bedingung"), e.get("wert"), z, e.get("start")):
            text = e.get("text") or _t("%s steht jetzt auf „%s“.", "%s is now “%s”.") % (e.get("name"), z)
            try:
                melden(e.get("person"), _t("Jarvis: Bescheid", "Jarvis: Heads-up"), text)
            except Exception:
                bleiben.append(e)            # beim naechsten Mal erneut versuchen
                continue
            ausgeloest.append(dict(e, ausgeloest=z))
        else:
            bleiben.append(e)
    if len(bleiben) != len(alle):
        with _sperre:
            aktuell = _laden(daten)          # in der Zwischenzeit angelegte behalten
            erledigt = {e.get("nr") for e in alle if e not in bleiben}
            _speichern(daten, [e for e in aktuell if e.get("nr") not in erledigt and e.get("bis", 0) > jetzt])
    return ausgeloest


# ---------------------------------------------------------------- Einstieg fuer das Werkzeug „beobachten“

def gesperrt(entity_id):
    """Kameras und Babyfone beobachtet Jarvis nie (auch nicht „ändert sich“)."""
    e = str(entity_id or "").lower()
    return e.split(".")[0] in GESPERRTE_DOMAENEN or any(t in e for t in GESPERRTE_TEILE)


def liste_text(daten, person, jetzt=None):
    """Die laufenden Beobachter der Person als Text (eine Zeile je Beobachter)."""
    l = liste(daten, person, jetzt)
    if not l:
        return _t("Keine Beobachter aktiv.", "No watchers active.")
    zeile = _t("Nr. %d: %s %s (bis %s Uhr)%s", "No. %d: %s %s (until %s)%s")
    return "\n".join(zeile % (e["nr"], e["name"], beschreibung(e), time.strftime("%H:%M", time.localtime(e["bis"])),
                              (" – „%s“" % e["text"] if SPRACHE != "en" else " – “%s”" % e["text"])
                              if e.get("text") else "") for e in l)


def auftrag(daten, person, args, zustand_lesen, log=None, jetzt=None):
    """Werkzeug beobachten: aktion neu|liste|loeschen. zustand_lesen(entity_id) -> HA-Zustand als dict
    ({"state", "attributes"}) oder wirft (urllib.error.HTTPError mit code, wenn HA die Entität nicht kennt).
    Der Zustand beim Anlegen kommt direkt aus HA. -> Meldung."""
    b = args if isinstance(args, dict) else {}
    a = str(b.get("aktion", "liste"))
    if a == "liste":
        return liste_text(daten, person, jetzt)
    if a == "loeschen":
        try:
            nr = int(b.get("nr") or 0)
        except (TypeError, ValueError):
            nr = 0
        return loeschen(daten, person, nr)
    if a != "neu":
        return _t("aktion muss neu, liste oder loeschen sein.", "aktion must be neu, liste or loeschen.")
    eid = str(b.get("entity_id", "")).strip()
    if not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", eid):
        return _t("Ich brauche eine gültige Entität (z. B. sensor.waschmaschine_status).",
                  "I need a valid entity (e.g. sensor.washing_machine_status).")
    if gesperrt(eid):
        return _t("Kameras und Babyfon beobachte ich nicht.", "I don't watch cameras or baby monitors.")
    try:
        s = zustand_lesen(eid)
    except urllib.error.HTTPError as x:
        return _t("Die Entität %s kenne ich nicht (HA: %s).", "I don't know the entity %s (HA: %s).") % (eid, x.code)
    except Exception as x:
        return _t("Home Assistant antwortet gerade nicht (%s).",
                  "Home Assistant isn't responding right now (%s).") % type(x).__name__
    s = s if isinstance(s, dict) else {}
    name = (s.get("attributes") or {}).get("friendly_name") or eid
    ok, text = neu(daten, person, eid, str(b.get("bedingung", "")), b.get("wert", ""), b.get("text", ""),
                   b.get("stunden"), s.get("state"), name=name, jetzt=jetzt)
    if ok and log:
        log("Beobachter angelegt:", eid, str(b.get("bedingung")), "für", person)
    return text
