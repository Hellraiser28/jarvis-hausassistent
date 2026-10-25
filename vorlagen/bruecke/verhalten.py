"""Verhaltensschalter von Jarvis (seit 25.10.2026; Ausgangswunsch: "Optionen, wie sich Jarvis verhalten soll, mit an/aus").

daten/verhalten.json, geaendert nur ueber aendern() (bekannte Schluessel, feste Werte). Standard ist das bisherige
Verhalten. Wirkung in der Bruecke:
- zwischensaetze aus: kein "Ich schau kurz in den Kalender" (die Anzeige des Werkzeugs bleibt)
- antwortstil kurz/ausfuehrlich: ein Satz im Lage-Vorspann jeder Frage
- nachtruhe an: zwischen nachtruhe_von und nachtruhe_bis keine Durchsagen und kein Vorlesen ueber Lautsprecher
Nur Python-Standardbibliothek (NAS-Python 3.8)."""
import copy
import json
import os

STANDARD = {"zwischensaetze": "an", "antwortstil": "normal", "nachtruhe": "aus", "nachtruhe_von": 22, "nachtruhe_bis": 7}
WERTE = {"zwischensaetze": ("an", "aus"), "antwortstil": ("kurz", "normal", "ausfuehrlich"), "nachtruhe": ("an", "aus")}
STIL_DE = {"kurz": "Antwortstil: kurz, höchstens zwei Sätze, außer die Person will ausdrücklich mehr.",
           "ausfuehrlich": "Antwortstil: ausführlich, gern mit Einzelheiten und kurzer Begründung."}
STIL_EN = {"kurz": "Answer style: short, two sentences at most, unless the person explicitly wants more.",
           "ausfuehrlich": "Answer style: detailed, with particulars and a short reason."}
STIL = STIL_DE          # Bruecke: vh.STIL[stil]; folgt setze_sprache()


class Ungueltig(ValueError):
    pass

# Sprache (seit 0.3.0): "de" (Standard, wie bisher) oder "en". Die Bruecke setzt sie einmal beim Start nach der Sprache
# der Einrichtung (antworten.json "sprache"). Sie bestimmt Grundwerte, Meldungen und Beschreibungen.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache
    global STIL
    STIL = STIL_EN if sprache == "en" else STIL_DE


def _t(de, en):
    return en if SPRACHE == "en" else de


def pruefen(o):
    if not isinstance(o, dict):
        raise Ungueltig(_t("Einstellungen müssen ein Objekt sein.", "Settings must be an object."))
    fremd = sorted(set(o) - set(STANDARD))
    if fremd:
        raise Ungueltig(_t("Unbekannte Einstellung: %s. Möglich: %s.", "Unknown setting: %s. Possible: %s.")
                        % (", ".join(fremd), ", ".join(STANDARD)))
    e = copy.deepcopy(STANDARD)
    e.update(o)
    for k, erlaubt in WERTE.items():
        if e[k] not in erlaubt:
            raise Ungueltig(_t("%s ist %s.", "%s is %s.") % (k, _t(" oder ", " or ").join(erlaubt)))
    for k in ("nachtruhe_von", "nachtruhe_bis"):
        if not isinstance(e[k], int) or isinstance(e[k], bool) or not 0 <= e[k] <= 23:
            raise Ungueltig(_t("%s ist eine volle Stunde von 0 bis 23.", "%s is a full hour from 0 to 23.") % k)
    if e["nachtruhe_von"] == e["nachtruhe_bis"]:
        raise Ungueltig(_t("Nachtruhe braucht verschiedene Anfangs- und Endstunden.", "Quiet hours need different start and end hours."))
    return e


def aendern(aktuell, aenderung):
    if not isinstance(aenderung, dict) or not aenderung:
        raise Ungueltig(_t("Keine Änderung angegeben.", "No change given."))
    return pruefen(dict(aktuell, **aenderung))


def optionen():
    """Erlaubte Werte fuers Zahnrad-Menue (Schluessel "optionen"."verhalten"): je Schalter die Liste der Werte."""
    return {k: list(w) for k, w in WERTE.items()}


def nachtruhe_jetzt(e, stunde):
    if e["nachtruhe"] != "an":
        return False
    von, bis = e["nachtruhe_von"], e["nachtruhe_bis"]
    return (stunde >= von or stunde < bis) if von > bis else (von <= stunde < bis)


def beschreiben(e):
    if SPRACHE == "en":
        stil = {"kurz": "short", "normal": "normal", "ausfuehrlich": "detailed"}[e["antwortstil"]]
        an = {"an": "on", "aus": "off"}
        return ("Interim phrases: %s. Answer style: %s. Quiet hours: %s%s." % (
            an[e["zwischensaetze"]], stil, an[e["nachtruhe"]],
            " (%d:00 to %d:00, no announcements and no reading aloud)" % (e["nachtruhe_von"], e["nachtruhe_bis"])
            if e["nachtruhe"] == "an" else ""))
    return ("Zwischensätze: %s. Antwortstil: %s. Nachtruhe: %s%s." % (
        e["zwischensaetze"], e["antwortstil"].replace("ausfuehrlich", "ausführlich"), e["nachtruhe"],
        " (%d bis %d Uhr, keine Durchsagen und kein Vorlesen)" % (e["nachtruhe_von"], e["nachtruhe_bis"])
        if e["nachtruhe"] == "an" else ""))


def laden(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            return pruefen(json.load(f))
    except (OSError, ValueError):
        return pruefen({})


def speichern(pfad, e):
    tmp = pfad + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pruefen(e), f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, pfad)
