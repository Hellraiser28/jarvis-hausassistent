"""Szenen (seit 0.4): mehrere Aktionen mit einem Satz oder einem Knopf in der App, nur auf Zuruf.

Eine Szene ist eine feste Liste von Werkzeug-Aufrufen ({"werkzeug", "argumente"}), die der Werkzeug-Server der Reihe
nach ausfuehrt, ohne dass das Gehirn jeden Schritt einzeln ueberlegt. Erlaubt sind nur Werkzeuge mit Wirkung im
Haushalt (ERLAUBT, an die eigenen Werkzeuge anpassen). Aendern, Umbenennen und Loeschen darf nur, wer die Szene angelegt
hat, und die Hauptperson (darf_aendern); Loeschen und Umbenennen treffen nur den genauen Namen oder die Kennung; gesperrte Geraete (z. B. Babyfon, Kameras) prueft das Werkzeug
selbst (Tabu-Liste). Anlegen und Aendern per Sprache erst nach
einem klaren Ja in der naechsten Nachricht (prueft die Bruecke), Loeschen nur, wenn die Person die Szene nennt.
Python 3.8, nur Standardbibliothek. Datei daten/szenen.json (600), Schreiben unter Dateisperre.
"""
import json
import os
import re
import secrets
import time
from contextlib import contextmanager

DATEI = "szenen.json"
MAX_SZENEN = 30
MAX_SCHRITTE = 12
MAX_NAME = 40
# Werkzeug -> erlaubte Werte einzelner Argumente (None = beliebig). Nur Aktionen, keine Abfragen und nichts nach aussen
# ausser Push und Durchsage (Mails bleiben beim Entwurf mit Zustimmung).
ERLAUBT = {
    "geraet_steuern": {},
    "saugroboter": {"aktion": ("start", "pause", "stop", "heim", "raeume", "routine")},
    "musik": {"aktion": ("spielen",)},
    "radio": {},
    "vorlesen": {},
    "nachricht": {"aktion": ("senden",), "kanal": ("push", "durchsage")},
    "warten": {},
}
PFLICHT = {"geraet_steuern": ("entity_id", "dienst"), "musik": ("suche",), "radio": ("sender",), "vorlesen": ("text",),
           "nachricht": ("aktion", "kanal", "text")}


# Sprache der Texte, die die Person direkt sieht (seit 0.4 im Release). Die Bruecke setzt sie beim Start aus
# der Einrichtung (antworten.json "sprache"), wie bei verhalten.py und oberflaeche.py.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


class Fehler(Exception):
    pass


def norm(s):
    s = str(s or "").lower().strip()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"^(?:(?:die |meine |unsere )?szene|(?:the |my |our )?scene) ", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _sperren(fd):
    """Exklusive Dateisperre: flock unter Linux und macOS, msvcrt unter Windows (wie bilddienst.py)."""
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)
    except ImportError:                 # Windows: LK_LOCK versucht es etwa 10 s lang, dann OSError
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        except OSError:
            raise Fehler("Die Datei ist gerade gesperrt, bitte gleich noch einmal versuchen.")


def _entsperren(fd):
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
    except ImportError:                 # Windows: vor dem Schliessen ausdruecklich freigeben
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def _ersetzen_atomar(neu, pfad):
    """os.replace; unter Windows kurz wiederholen, falls gerade ein Leser die Datei offen hat."""
    for i in range(20):
        try:
            os.replace(neu, pfad)
            return
        except PermissionError:
            if os.name != "nt" or i == 19:
                raise
            time.sleep(0.05)


@contextmanager
def _gesperrt(daten):
    fd = os.open(os.path.join(daten, DATEI + ".sperre"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        _sperren(fd)
        try:
            yield
        finally:
            _entsperren(fd)
    finally:
        os.close(fd)


def laden(daten):
    try:
        d = json.load(open(os.path.join(daten, DATEI), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [s for s in (d.get("szenen") if isinstance(d, dict) else []) or [] if isinstance(s, dict) and s.get("id")]


def _schreiben(daten, liste):
    pfad = os.path.join(daten, DATEI)
    fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"szenen": liste}, f, ensure_ascii=False, indent=1)
    _ersetzen_atomar(pfad + ".neu", pfad)


def name_pruefen(name):
    n = re.sub(r"\s+", " ", str(name or "")).strip().strip("„“\"'")
    if not n or len(n) > MAX_NAME or not norm(n):
        raise Fehler(_t("Der Name fehlt oder ist zu lang (höchstens %d Zeichen).",
                         "The name is missing or too long (at most %d characters).") % MAX_NAME)
    return n


def schritte_pruefen(schritte):
    """Form, Erlaubnis und Groesse; die Argumente selbst prueft der Werkzeug-Server gegen die echte Funktion."""
    if isinstance(schritte, str):
        try:
            schritte = json.loads(schritte)
        except ValueError:
            raise Fehler(_t("Die Schritte sind kein JSON.", "The steps are not JSON."))
    if not isinstance(schritte, list) or not schritte:
        raise Fehler(_t("Eine Szene braucht mindestens einen Schritt.", "A scene needs at least one step."))
    if len(schritte) > MAX_SCHRITTE:
        raise Fehler(_t("Höchstens %d Schritte je Szene.", "At most %d steps per scene.") % MAX_SCHRITTE)
    aus = []
    for i, s in enumerate(schritte, 1):
        if not isinstance(s, dict):
            raise Fehler(_t("Schritt %d ist kein Objekt.", "Step %d is not an object.") % i)
        w, a = str(s.get("werkzeug") or ""), s.get("argumente") or {}
        if w not in ERLAUBT:
            raise Fehler(_t("Schritt %d: „%s“ geht in einer Szene nicht. Möglich: %s.",
                            "Step %d: “%s” is not possible in a scene. Possible: %s.") % (i, w, ", ".join(sorted(ERLAUBT))))
        if not isinstance(a, dict) or len(json.dumps(a, ensure_ascii=False)) > 1500:
            raise Fehler(_t("Schritt %d: Argumente fehlen oder sind zu lang.", "Step %d: arguments are missing or too long.") % i)
        for k in PFLICHT.get(w, ()):
            if a.get(k) in (None, ""):
                raise Fehler(_t("Schritt %d (%s): %s fehlt.", "Step %d (%s): %s is missing.") % (i, w, k))
        for k, werte in ERLAUBT[w].items():
            if k in a and str(a[k]).lower() not in werte:
                raise Fehler(_t("Schritt %d (%s): %s=%s geht in einer Szene nicht (nur %s).",
                                "Step %d (%s): %s=%s is not possible in a scene (only %s).") % (i, w, k, a[k], ", ".join(werte)))
        if w == "geraet_steuern" and "daten" in a and not isinstance(a["daten"], dict):
            raise Fehler(_t("Schritt %d: daten muss ein Objekt sein.", "Step %d: daten must be an object.") % i)
        if w == "nachricht" and a.get("entwurf"):
            raise Fehler(_t("Schritt %d: Entwürfe gehören nicht in eine Szene.", "Step %d: drafts do not belong in a scene.") % i)
        if w == "warten":
            try:
                a = {"sekunden": max(1, min(20, int(a.get("sekunden") or 5)))}
            except (TypeError, ValueError):
                raise Fehler(_t("Schritt %d: sekunden muss eine Zahl sein.", "Step %d: sekunden must be a number.") % i)
        aus.append({"werkzeug": w, "argumente": a})
    if sum(x["argumente"]["sekunden"] for x in aus if x["werkzeug"] == "warten") > 40:
        raise Fehler(_t("Zusammen höchstens 40 Sekunden warten.", "At most 40 seconds of waiting in total."))
    return aus


def finden(liste, wer, genau=False):
    """Nach Kennung, genauem Namen oder (nicht mit genau=True) eindeutigem Namensteil. Loeschen und Umbenennen nehmen
    genau=True: "Kinoabend" darf nie "Kino" treffen."""
    w = str(wer or "").strip()
    for s in liste:
        if s["id"] == w:
            return s
    n = norm(w)
    gleich = [s for s in liste if norm(s["name"]) == n]
    if gleich or genau:
        return gleich[0] if len(gleich) == 1 else None          # zwei gleiche Namen: keine raten
    teil = [s for s in liste if n and (n in norm(s["name"]) or norm(s["name"]) in n)]
    return teil[0] if len(teil) == 1 else None


def darf_aendern(s, person, haupt=False):
    """Aendern, Umbenennen, Schritt entfernen, Loeschen: wer die Szene angelegt hat, und die Hauptperson."""
    return bool(person) and (haupt or s.get("von") == person)


def _fremd(s):
    return _t("„%s“ hat jemand anderes angelegt, die Szene kann nur diese Person oder die Hauptperson ändern.",
              "“%s” was created by someone else; only that person or the main person can change it.") % s["name"]


def speichern(daten, name, schritte, von, ersetzt=None, haupt=False):
    """Neu anlegen oder (gleicher Name bzw. ersetzt=Kennung) ersetzen. Gibt (szene, neu: bool) zurueck. Eine fremde
    Szene mit demselben Namen ersetzt nur die Hauptperson."""
    name, schritte = name_pruefen(name), schritte_pruefen(schritte)
    with _gesperrt(daten):
        liste = laden(daten)
        gleich = [s for s in liste if norm(s["name"]) == norm(name)]
        if ersetzt:
            alt = finden(liste, ersetzt, genau=True)
            if not alt:
                raise Fehler(_t("Diese Szene gibt es nicht mehr.", "This scene no longer exists."))
            if any(s["id"] != alt["id"] for s in gleich):       # nie den Namen einer anderen Szene uebernehmen
                raise Fehler(_t("Eine Szene „%s“ gibt es schon.", "A scene “%s” already exists.") % name)
        else:
            alt = gleich[0] if gleich else None
        if alt and not darf_aendern(alt, von, haupt):
            raise Fehler(_fremd(alt))
        jetzt = time.strftime("%Y-%m-%d %H:%M")
        if alt:
            alt.update(name=name, schritte=schritte, geaendert=jetzt, geaendert_von=von)
            s, neu = alt, False
        else:
            if len(liste) >= MAX_SZENEN:
                raise Fehler(_t("Schon %d Szenen, lösch erst eine.", "Already %d scenes, delete one first.") % MAX_SZENEN)
            s = {"id": "s" + secrets.token_hex(3), "name": name, "schritte": schritte, "von": von, "erstellt": jetzt}
            liste.append(s)
            neu = True
        _schreiben(daten, liste)
    return s, neu


def loeschen(daten, wer, person, haupt=False):
    with _gesperrt(daten):
        liste = laden(daten)
        s = finden(liste, wer, genau=True)
        if not s:
            return None
        if not darf_aendern(s, person, haupt):
            raise Fehler(_fremd(s))
        _schreiben(daten, [x for x in liste if x["id"] != s["id"]])
    return s


def umbenennen(daten, wer, neu, person, haupt=False):
    neu = name_pruefen(neu)
    with _gesperrt(daten):
        liste = laden(daten)
        s = finden(liste, wer, genau=True)
        if not s:
            return None
        if not darf_aendern(s, person, haupt):
            raise Fehler(_fremd(s))
        if any(norm(x["name"]) == norm(neu) and x["id"] != s["id"] for x in liste):
            raise Fehler(_t("Eine Szene „%s“ gibt es schon.", "A scene “%s” already exists.") % neu)
        s["name"] = neu
        _schreiben(daten, liste)
    return s


def schritt_entfernen(daten, wer, nr, person, haupt=False):
    with _gesperrt(daten):
        liste = laden(daten)
        s = finden(liste, wer, genau=True)
        if not s:
            return None
        if not darf_aendern(s, person, haupt):
            raise Fehler(_fremd(s))
        try:
            i = int(nr) - 1
        except (TypeError, ValueError):
            raise Fehler(_t("Schritt %s gibt es nicht.", "There is no step %s.") % nr)
        if not 0 <= i < len(s["schritte"]):
            raise Fehler(_t("Schritt %s gibt es nicht.", "There is no step %s.") % nr)
        if len(s["schritte"]) == 1:
            raise Fehler(_t("Das ist der letzte Schritt. Lösch dann lieber die ganze Szene.",
                            "That is the last step. Delete the whole scene instead."))
        del s["schritte"][i]
        s["geaendert"] = time.strftime("%Y-%m-%d %H:%M")
        _schreiben(daten, liste)
    return s


DIENST_WORT = {"turn_off": "aus", "turn_on": "an", "toggle": "umschalten", "media_pause": "Pause", "media_play": "abspielen",
               "media_stop": "Stopp", "media_play_pause": "Pause/Weiter", "media_next_track": "nächster Titel",
               "volume_mute": "stumm", "open_cover": "öffnen", "close_cover": "schließen", "stop_cover": "anhalten",
               "press": "drücken", "lock": "abschließen", "unlock": "aufschließen", "start": "starten", "pause": "pausieren",
               "return_to_base": "zur Station", "select_source": "Quelle", "set_temperature": "Temperatur",
               "set_hvac_mode": "Modus", "select_option": "auswählen", "set_value": "Wert"}
DIENST_WORT_EN = {"turn_off": "off", "turn_on": "on", "toggle": "toggle", "media_pause": "pause", "media_play": "play",
                  "media_stop": "stop", "media_play_pause": "pause/resume", "media_next_track": "next track",
                  "volume_mute": "mute", "open_cover": "open", "close_cover": "close", "stop_cover": "stop",
                  "press": "press", "lock": "lock", "unlock": "unlock", "start": "start", "pause": "pause",
                  "return_to_base": "back to the dock", "select_source": "source", "set_temperature": "temperature",
                  "set_hvac_mode": "mode", "select_option": "select", "set_value": "value"}


def beschreibung(schritt, namen=None):
    """Ein Schritt in Worten (fuer Sprache und App). namen: entity_id -> Anzeigename (sonst die Kennung)."""
    w, a = schritt["werkzeug"], schritt["argumente"]
    if w == "geraet_steuern":
        e, d = str(a.get("entity_id")), str(a.get("dienst"))
        daten = dict(a["daten"]) if isinstance(a.get("daten"), dict) else {}
        wer = (namen or {}).get(e) or e
        if d == "volume_set" and isinstance(daten.get("volume_level"), (int, float)):
            return _t("%s: Lautstärke %d %%", "%s: volume %d %%") % (wer, round(daten["volume_level"] * 100))
        if d == "turn_on" and "brightness_pct" in daten:
            return _t("%s: an, %s %%", "%s: on, %s %%") % (wer, daten.pop("brightness_pct"))
        extra = ", ".join("%s %s" % (k, v) for k, v in daten.items())
        wort = _t(DIENST_WORT, DIENST_WORT_EN).get(d, d)
        return "%s: %s%s" % (wer, wort if namen is not None else d, " (%s)" % extra if extra else "")
    if w == "nachricht":
        return _t("%s%s: „%s“", "%s%s: “%s”") % (
            _t("Durchsage", "Announcement") if a.get("kanal") == "durchsage" else "Push",
            (_t(" an ", " to ") + str(a.get("an"))) if a.get("an") else "", str(a.get("text"))[:80])
    auf = (_t(" auf ", " on ") + str(a["lautsprecher"])) if a.get("lautsprecher") else ""
    if w == "musik":
        return _t("Musik „%s“%s", "Music “%s”%s") % (a.get("suche"), auf)
    if w == "radio":
        return "Radio %s%s" % (a.get("sender"), auf)
    if w == "vorlesen":
        return _t("Vorlesen%s: „%s“", "Read aloud%s: “%s”") % (auf, str(a.get("text"))[:80])
    if w == "saugroboter":
        return _t("Saugroboter: %s%s", "Vacuum: %s%s") % (a.get("aktion", "start"),
                                                           (" " + str(a.get("raeume") or a.get("routine") or "")).rstrip())
    if w == "warten":
        return _t("%d Sekunden warten", "Wait %d seconds") % a.get("sekunden", 5)
    return w


def als_text(s):
    return "„%s“: %s" % (s["name"], "; ".join("%d. %s" % (i, beschreibung(x)) for i, x in enumerate(s["schritte"], 1)))


def fuer_app(liste, namen=None, person=None, haupt=False, personen_namen=None):
    """Fuer das App-Menue: aendern (darf diese Person die Szene aendern?) und von als Anzeigename der Person."""
    pn = personen_namen or {}
    return [{"id": s["id"], "name": s["name"], "von": pn.get(s.get("von"), s.get("von") or ""),
             "aendern": darf_aendern(s, person, haupt),
             "schritte": [beschreibung(x, namen if namen is not None else {}) for x in s["schritte"]]} for s in liste]
