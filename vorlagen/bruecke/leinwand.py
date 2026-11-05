"""Leinwand (seit 01.11.2026, im Release seit 0.6): Jarvis zeigt Rezepte Schritt fuer Schritt, die Einkaufsliste, die
Woche, einen Text oder das Quiz gross auf dem Beamer bzw. Fernseher.

Weg (alles in HA belegt, nichts Neues nach aussen): Jarvis schreibt den Inhalt als Attribute in sensor.jarvis_leinwand
(POST /api/states), ein Dashboard jarvis-leinwand (Ansicht leinwand, z. B. eine custom:button-card, die die Attribute
rendert) zeigt ihn live an, und cast.show_lovelace_view holt die Ansicht auf das Cast-Geraet am Beamer (CAST, z. B. eine
Android-TV-Box). Die Cast-App von Home Assistant (A078F6B0, pychromecast config.py) laedt dabei die externe
HTTPS-Adresse von HA und meldet sich mit HAs eigenem Cast-Benutzer an. Der Sensor gehoert zu keiner Integration und ist
nach einem HA-Neustart leer, bis Jarvis wieder etwas zeigt.

Dieses Modul ist reine Logik (keine Netzaufrufe): Zustand bauen, blaettern, Sensor-Inhalt kuerzen, Ansage.
daten/leinwand.json haelt den Zustand, damit „weiter“ auch in einem neuen Gespraech funktioniert.
Das Cast-Geraet ist je Haushalt verschieden: setze_cast() (die Bruecke und der Werkzeug-Server setzen es beim Start aus
der .env, LEINWAND_CAST). Sprache der Texte auf der Leinwand und der Ansagen: setze_sprache() wie bei szenen.py.
"""
import json
import math
import os
import re
from datetime import datetime

CAST = "media_player.leinwand"                      # Cast-Seite des Geraets am Beamer; an das eigene Haus anpassen (setze_cast)
SENSOR = "sensor.jarvis_leinwand"
DASHBOARD, ANSICHT = "jarvis-leinwand", "leinwand"
CAST_APP = "A078F6B0"                               # Home Assistant Lovelace (pychromecast APP_HOMEASSISTANT_LOVELACE)
DATEI = "leinwand.json"
ARTEN = ("rezept", "liste", "woche", "text", "quiz")    # quiz seit 01.11.2026 (bruecke/quiz.py, Werkzeug quiz)
QUIZ_FELDER = ("phase", "nr", "gesamt", "frage", "antworten", "fuer", "stufe", "spieler", "seit", "sekunden", "richtig",
               "wusstest", "sieger", "rangliste", "ton", "ton_ab",
               # seit 01.11.2026 abends (Buehne wie bei „Wer wird Millionär“): Runde, Leiter, Schwierigkeit, Zeitmarken
               "runde", "runden", "leiter", "schwierigkeit", "schluessel", "auf_ab", "antw_ab", "aufdecken_ab", "mund",
               "mund_hz", "mund_ab")
# ton (seit 01.11.2026): https-Adresse einer Ansage, die die Seite selbst abspielt (Ton ueber HDMI, der Verstaerker
# bleibt auf dem Eingang des Cast-Geraets); ton_ab: Unix-Zeit, ab der sie spielen soll. sensor() reicht beides durch.
LISTE_JE_SEITE = 24
MAX_ATTRIBUTE = 14000                               # HA warnt ab 16 KB Attributen (Recorder), Luft lassen
WARTEN_S = 150                                      # so lange wartet die Bruecke, bis die Box nach dem Einschalten da ist

# Sprache der Texte, die die Person auf der Leinwand sieht oder als Ansage hoert.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


def setze_cast(entity):
    """Cast-Geraet am Beamer (media_player.*), z. B. aus LEINWAND_CAST in der .env."""
    global CAST
    if not isinstance(entity, str) or not re.fullmatch(r"media_player\.[a-z0-9_]+", entity):
        raise ValueError("cast ist eine Kennung media_player.*")
    CAST = entity


def _kurz(t, n):
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def zustand_laden(daten):
    try:
        z = json.load(open(os.path.join(daten, DATEI), encoding="utf-8"))
        return z if isinstance(z, dict) and z.get("art") in ARTEN else {}
    except (OSError, ValueError):
        return {}


def zustand_speichern(daten, z):
    pfad = os.path.join(daten, DATEI)
    neu = pfad + ".neu"
    with open(neu, "w", encoding="utf-8") as f:
        json.dump(z or {}, f, ensure_ascii=False)
    os.replace(neu, pfad)


# ---------------------------------------------------------------- Zustaende bauen
def rezept_zustand(d, von=""):
    """Aus einem Mealie-Rezept (GET /api/recipes/<slug>): Seite 0 = Ueberblick, Seite k = Schritt k."""
    zutaten = [(z.get("display") or z.get("originalText") or z.get("note") or "").strip()
               for z in d.get("recipeIngredient") or []]
    schritte = [s.get("text", "").strip() for s in d.get("recipeInstructions") or []]
    unter = " · ".join(x for x in (str(d.get("recipeYield") or "").strip(), _zeit(d.get("totalTime"))) if x)
    return {"art": "rezept", "titel": _kurz(d.get("name") or _t("Rezept", "Recipe"), 80), "unter": _kurz(unter, 80),
            "zutaten": [_kurz(z, 70) for z in zutaten if z][:30], "schritte": [_kurz(s, 700) for s in schritte if s][:30],
            "seite": 0, "von": von}


def _zeit(t):
    t = str(t or "").strip()
    return t if t and t.lower() not in ("none", "null") else ""


WETTER = {"sunny": "Sonnig", "clear-night": "Klar", "partlycloudy": "Wolkig", "cloudy": "Bedeckt", "rainy": "Regen",
          "pouring": "Starkregen", "snowy": "Schnee", "snowy-rainy": "Schneeregen", "fog": "Nebel", "hail": "Hagel",
          "lightning": "Gewitter", "lightning-rainy": "Gewitter", "windy": "Windig", "windy-variant": "Windig",
          "exceptional": "Unwetter"}
WETTER_EN = {"sunny": "Sunny", "clear-night": "Clear", "partlycloudy": "Partly cloudy", "cloudy": "Overcast",
             "rainy": "Rain", "pouring": "Heavy rain", "snowy": "Snow", "snowy-rainy": "Sleet", "fog": "Fog",
             "hail": "Hail", "lightning": "Thunderstorm", "lightning-rainy": "Thunderstorm", "windy": "Windy",
             "windy-variant": "Windy", "exceptional": "Severe weather"}


def wetter_zeile(x):
    """Eine Tagesvorhersage aus weather.get_forecasts -> "Regen · 6–11 °C"."""
    def grad(v):
        try:
            return "%d" % round(float(v))
        except (TypeError, ValueError):
            return "?"
    w = _t(WETTER, WETTER_EN).get(str(x.get("condition") or ""), str(x.get("condition") or "").capitalize())
    return _kurz("%s · %s–%s °C" % (w, grad(x.get("templow")), grad(x.get("temperature"))), 40)


def liste_zustand(titel, punkte, von=""):
    p = [_kurz(x, 70) for x in punkte or [] if str(x).strip()][:96]
    return {"art": "liste", "titel": _kurz(titel, 80), "punkte": p, "seite": 0, "von": von}


def woche_zustand(tage, von="", titel=None):
    """tage: [{"tag": "Mo", "datum": "03.11.", "wetter": "...", "essen": "...", "termine": ["18:00 ..."]}], hoechstens 7.
    titel: Standard „Die Woche“ bzw. „The week“."""
    t = []
    for x in (tage or [])[:7]:
        t.append({"tag": _kurz(x.get("tag"), 12), "datum": _kurz(x.get("datum"), 10), "wetter": _kurz(x.get("wetter"), 40),
                  "essen": _kurz(x.get("essen"), 60), "termine": [_kurz(y, 60) for y in x.get("termine") or []][:6]})
    return {"art": "woche", "titel": _kurz(titel or _t("Die Woche", "The week"), 80), "tage": t, "seite": 0, "von": von}


def text_zustand(titel, text="", punkte=None, von=""):
    return {"art": "text", "titel": _kurz(titel or "Jarvis", 80), "text": _kurz(text, 1500),
            "punkte": [_kurz(x, 120) for x in punkte or [] if str(x).strip()][:12], "seite": 0, "von": von}


def quiz_zustand(a, von=""):
    """Aus quiz.anzeige(): Frage, A-D, Spieler mit Punkten; die Loesung nur, wenn sie schon aufgeloest ist."""
    z = {"art": "quiz", "titel": _kurz(a.get("titel") or _t("Familien-Quiz", "Family Quiz"), 80),
         "unter": _kurz(a.get("unter"), 40), "seite": 0, "von": von}
    for k in QUIZ_FELDER:
        if k in a:
            z[k] = a[k]
    return z


# ---------------------------------------------------------------- Blaettern
def seiten(z):
    if z.get("art") == "rezept":
        return 1 + len(z.get("schritte") or [])
    if z.get("art") == "liste":
        return max(1, math.ceil(len(z.get("punkte") or []) / LISTE_JE_SEITE))
    return 1


def blaettern(z, wohin):
    """wohin: "weiter", "zurueck", "anfang" oder eine Zahl (beim Rezept: Schrittnummer, 0 = Ueberblick).
    Gibt (neuer Zustand, Meldung oder None) zurueck; der Zustand wird nicht veraendert, wenn es nicht weitergeht."""
    if z.get("art") == "quiz":
        return z, _t("Auf der Leinwand läuft das Quiz: weiter geht es mit dem Werkzeug quiz (nächste Frage).",
                     "The quiz is on the screen: carry on with the tool quiz (next question).")
    n, s = seiten(z), int(z.get("seite") or 0)
    w = str(wohin if wohin is not None else "weiter").strip().lower()
    if re.fullmatch(r"\d{1,3}", w):
        ziel = int(w)
    elif w in ("weiter", "naechster", "nächster", "vor"):
        ziel = s + 1
    elif w in ("zurueck", "zurück", "vorher"):
        ziel = s - 1
    elif w in ("anfang", "ueberblick", "überblick", "start"):
        ziel = 0
    else:
        return z, _t("Unbekannt: „%s“. Möglich: weiter, zurück, Anfang oder eine Nummer.",
                     "Unknown: “%s”. Possible: weiter, zurueck, anfang or a number.") % wohin
    if ziel >= n:
        return z, (_t("Das war der letzte Schritt. Guten Appetit!", "That was the last step. Enjoy your meal!")
                   if z.get("art") == "rezept" else _t("Das ist schon die letzte Seite.", "This is already the last page."))
    if ziel < 0:
        return z, _t("Weiter zurück geht es nicht.", "It does not go back any further.")
    return dict(z, seite=ziel), None


# ---------------------------------------------------------------- Sensor und Ansage
def sensor(z, jetzt=None):
    """(state, attributes) fuer sensor.jarvis_leinwand; Listen werden gekuerzt, bis es unter MAX_ATTRIBUTE passt."""
    jetzt = jetzt or datetime.now()
    name = _t("Jarvis Leinwand", "Jarvis Screen")
    if not z or z.get("art") not in ARTEN:
        return "leer", {"art": "leer", "friendly_name": name, "icon": "mdi:projector-screen-off-outline",
                        "zeit": jetzt.strftime("%H:%M")}
    n, s = seiten(z), int(z.get("seite") or 0)
    a = {"art": z["art"], "titel": z.get("titel", ""), "unter": z.get("unter", ""), "seite": s, "seiten": n,
         "von": z.get("von", ""), "zeit": jetzt.strftime("%H:%M"), "friendly_name": name,
         "icon": "mdi:projector-screen-outline"}
    if str(z.get("ton") or "").startswith("https://"):
        a["ton"], a["ton_ab"] = z["ton"], z.get("ton_ab") or 0
    if z["art"] == "rezept":
        sch = z.get("schritte") or []
        a["zutaten"] = list(z.get("zutaten") or [])
        if s == 0:
            a["schritte"] = [_kurz(x, 110) for x in sch]
        else:
            a["schritt"] = sch[s - 1]
            a["danach"] = _kurz(sch[s], 140) if s < len(sch) else ""
    elif z["art"] == "liste":
        p = z.get("punkte") or []
        a["anzahl"] = len(p)
        a["punkte"] = p[s * LISTE_JE_SEITE:(s + 1) * LISTE_JE_SEITE]
    elif z["art"] == "woche":
        a["tage"] = z.get("tage") or []
    elif z["art"] == "quiz":
        for k in QUIZ_FELDER:
            if k in z:
                a[k] = z[k]
        return ("quiz %s" % ("ende" if z.get("phase") == "ende" else "%d/%d" % (z.get("nr", 1), z.get("gesamt", 1)))), a
    else:
        a["text"], a["punkte"] = z.get("text", ""), list(z.get("punkte") or [])
    for feld in ("zutaten", "schritte", "punkte", "tage"):          # notfalls kuerzen, groesste zuerst
        while len(json.dumps(a, ensure_ascii=False).encode()) > MAX_ATTRIBUTE and len(a.get(feld) or []) > 3:
            a[feld] = a[feld][:-1]
    status = z["art"] if n == 1 else "%s %d/%d" % (z["art"], s + 1 if z["art"] != "rezept" else s, n - 1 if z["art"] == "rezept" else n)
    return status, a


def ansage(z):
    """Kurzer Text fuer Jarvis' Antwort (wird vorgelesen): beim Rezeptschritt der ganze Schritt."""
    if not z:
        return _t("Auf der Leinwand ist gerade nichts.", "There is nothing on the screen right now.")
    s, n = int(z.get("seite") or 0), seiten(z)
    if z["art"] == "rezept":
        if s == 0:
            return _t("%s auf der Leinwand: %d Zutaten, %d Schritte. Sag „weiter“ für den ersten Schritt.",
                      "%s on the screen: %d ingredients, %d steps. Say “next” for the first step.") % (
                z["titel"], len(z.get("zutaten") or []), n - 1)
        return _t("Schritt %d von %d: %s", "Step %d of %d: %s") % (s, n - 1, z["schritte"][s - 1])
    if z["art"] == "liste":
        return _t("%s auf der Leinwand (%d Einträge%s).", "%s on the screen (%d items%s).") % (
            z["titel"], len(z.get("punkte") or []), _t(", Seite %d von %d", ", page %d of %d") % (s + 1, n) if n > 1 else "")
    if z["art"] == "woche":
        return _t("%s auf der Leinwand (%d Tage).", "%s on the screen (%d days).") % (z["titel"], len(z.get("tage") or []))
    if z["art"] == "quiz":
        if z.get("phase") == "ende":
            return _t("Auf der Leinwand steht der Endstand des Quiz.", "The final score of the quiz is on the screen.")
        return _t("Auf der Leinwand läuft das Quiz (Frage %s von %s).", "The quiz is on the screen (question %s of %s).") % (
            z.get("nr", 1), z.get("gesamt", 1))
    return _t("„%s“ steht auf der Leinwand.", "“%s” is on the screen.") % z["titel"]


def zeigt_leinwand(cast_zustand):
    """True, wenn die Box gerade die Lovelace-Cast-App von HA zeigt (dann reicht es, den Sensor zu aendern)."""
    a = (cast_zustand or {}).get("attributes") or {}
    return a.get("app_id") == CAST_APP


def erreichbar(cast_zustand):
    return (cast_zustand or {}).get("state") not in (None, "unavailable", "unknown")


def anderes_laeuft(cast_zustand):
    """Auf der Box laeuft gerade etwas anderes (Wiedergabe in einer anderen App): dann nicht ungefragt uebernehmen."""
    return erreichbar(cast_zustand) and not zeigt_leinwand(cast_zustand) and cast_zustand.get("state") in ("playing", "paused")


def zeige_dienst():
    return {"entity_id": CAST, "dashboard_path": DASHBOARD, "view_path": ANSICHT}
