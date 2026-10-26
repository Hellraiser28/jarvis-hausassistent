"""Oberflaechen-Einstellungen von Jarvis (seit 25.10.2026; Ausgangswunsch: "Jarvis, mach deine Oberflaeche gruen").

Alles Persoenliche des HUD (Farbe, Bereiche, Zeile unter dem Logo, Begruessungen, Knoepfe) steht in daten/oberflaeche.json,
nicht mehr im Code der Seite. Die Bruecke gibt die Einstellungen mit dem Zustand aus (/v1/zustand, zustand.json), HUD,
PC-Fenster und App wenden sie an. Ein Update der Seite oder der App laesst sie stehen.

Geaendert wird nur ueber aendern(): bekannte Schluessel, gepruefte Werte, Laengengrenzen. Das Gehirn bekommt dafuer ein
Werkzeug, aber nie Zugriff auf den Code der Seite (sie hat im PC-Fenster Zugriff auf die Fensterschnittstelle).
Nur Python-Standardbibliothek (NAS-Python 3.8)."""
import copy
import json
import os
import re
import time
import unicodedata

FARBEN = ("rot", "cyan", "blau", "gruen", "eigene")
FARB_NAMEN = {"rot": "Rot-Gold", "cyan": "Cyan", "blau": "Blau", "gruen": "Grün", "eigene": "eigene Farben"}
FARB_NAMEN_EN = {"rot": "Red-gold", "cyan": "Cyan", "blau": "Blue", "gruen": "Green", "eigene": "custom colors"}
BEREICHE = ("wetter", "systeme", "haus", "kalender", "welt", "verbindungen", "laufband", "gespraech", "aktionen",
            "begruessung", "werte")
SYMBOLE = ("briefing", "radio", "kopfhoerer", "news", "chip", "ball", "gamepad", "monitor", "liste", "kalender", "licht",
           "wetter", "haus", "stern", "film")
# Bereiche der App (seit 25.10.2026, Zahnrad-Menue): eigene Liste, damit das Handy etwas ausblenden kann, ohne dass sich
# der Wandbildschirm aendert. Standard: alle an (Stand der App 4.0).
APP_BEREICHE = ("werte", "wetter", "strom", "termine", "haus", "server", "radio", "nachrichten", "schnellzugriff",
                "begruessung")
NACHTMODUS = ("aus", "auto")        # auto: zwischen 22 und 6 Uhr gedimmt (Wandbildschirm, PC-Fenster)
BEWEGUNG = ("voll", "ruhig")        # ruhig: Reaktor und Laufband langsamer, kein Flackern
EIGENE_FARBEN = ("c", "titel", "bg", "text", "dim")          # Hexwerte #rrggbb; c = Hauptfarbe, Pflicht
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Grundwerte der Vorlage (gleich wie STANDARD im HUD). Fehlende Schluessel in oberflaeche.json fallen hierauf zurueck.
STANDARD = {
    "name": "J.A.R.V.I.S.",
    "untertitel": "Just A Rather Very Intelligent System",
    "person": "",
    "farbe": "rot",
    "farben": None,
    "bereiche": ["wetter", "systeme", "kalender", "welt", "verbindungen", "laufband", "gespraech", "aktionen", "begruessung"],
    "begruessungen": [[5, "Noch wach{, person}?"], [11, "Guten Morgen{, person}."], [18, "Hallo{, person}. Was liegt an?"],
                      [24, "Guten Abend{, person}."]],
    "start": [["J.A.R.V.I.S.", ""], ["Arc-Reaktor", "STABIL"], ["Gehirn", "CLAUDE"], ["Stimme", "BEREIT"]],
    "aktionen": [{"text": "Briefing", "frage": "Gib mir ein Briefing.", "symbol": "briefing"},
                 {"text": "Termine", "frage": "Was steht heute an?", "symbol": "kalender"},
                 {"text": "Wetter", "frage": "Wie wird das Wetter heute?", "symbol": "wetter"},
                 {"text": "News", "frage": "Was gibt's Neues in der Welt?", "symbol": "news"}],
    "app_aktionen": [],               # eigene Knoepfe fuer die App; leer = dieselben wie im HUD
    "app_bereiche": list(APP_BEREICHE),
    "nachtmodus": "aus",
    "bewegung": "voll",
    "werte_namen": {"strom": "STROM", "euro": "HEUTE", "last": "LAST"},
    "pc_name": "PC",
    "verbindungen_extra": [],
}
# Englische Grundwerte (seit 0.3.0, gleich wie STANDARD_EN im HUD); alles andere wie STANDARD
STANDARD_EN = {
    "begruessungen": [[5, "Still up{, person}?"], [11, "Good morning{, person}."], [18, "Hello{, person}. What's up?"],
                      [24, "Good evening{, person}."]],
    "start": [["J.A.R.V.I.S.", ""], ["Arc reactor", "STABLE"], ["Brain", "CLAUDE"], ["Voice", "READY"]],
    "aktionen": [{"text": "Briefing", "frage": "Give me a briefing.", "symbol": "briefing"},
                 {"text": "Calendar", "frage": "What's on today?", "symbol": "kalender"},
                 {"text": "Weather", "frage": "What's the weather today?", "symbol": "wetter"},
                 {"text": "News", "frage": "What's new in the world?", "symbol": "news"}],
    "werte_namen": {"strom": "POWER", "euro": "TODAY", "last": "LOAD"},
}
# Laengengrenzen: lang genug fuer Echtes, zu kurz fuer eingeschmuggelte Romane
GRENZE = {"name": 30, "untertitel": 80, "person": 30, "pc_name": 30, "gruss": 120, "start_a": 30, "start_b": 20,
          "knopf": 20, "frage": 200, "wert_name": 10, "extra": 30}


class Ungueltig(ValueError):
    """Die Aenderung verstoesst gegen die Regeln; der Text geht so an das Gehirn zurueck."""

# Sprache (seit 0.3.0): "de" (Standard, wie bisher) oder "en". Die Bruecke setzt sie einmal beim Start nach der Sprache
# der Einrichtung (antworten.json "sprache"). Sie bestimmt Grundwerte, Meldungen und Beschreibungen.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


def standard():
    """Grundwerte in der eingestellten Sprache."""
    e = copy.deepcopy(STANDARD)
    if SPRACHE == "en":
        e.update(copy.deepcopy(STANDARD_EN))
    return e


def _text(wert, grenze, was):
    if not isinstance(wert, str):
        raise Ungueltig(_t("%s muss Text sein.", "%s must be text.") % was)
    wert = " ".join(wert.split())                         # keine Zeilenumbrueche, keine Steuerzeichen-Spielereien
    # Seit 0.3.2 (Pruefbericht 0.3.1, Fund 5) auch Format- und Richtungszeichen (Kategorie Cf, z. B. U+202E, U+200B):
    # Mit ihnen liesse sich eine Beschriftung tarnen, die einen ganz anderen Auftrag ausloest.
    if any(ord(z) < 32 or unicodedata.category(z) in ("Cc", "Cf") for z in wert):
        raise Ungueltig(_t("%s enthält Steuer- oder Formatzeichen.", "%s contains control or format characters.") % was)
    if len(wert) > grenze:
        raise Ungueltig(_t("%s ist zu lang (höchstens %d Zeichen).", "%s is too long (at most %d characters).") % (was, grenze))
    return wert


def _liste(wert, hoechstens, was):
    if not isinstance(wert, list):
        raise Ungueltig(_t("%s muss eine Liste sein.", "%s must be a list.") % was)
    if len(wert) > hoechstens:
        raise Ungueltig(_t("%s: höchstens %d Einträge.", "%s: at most %d entries.") % (was, hoechstens))
    return wert


def pruefen(o):
    """Vollstaendige, gepruefte Einstellungen aus einem (Teil-)Objekt. Unbekannte Schluessel sind ein Fehler."""
    if not isinstance(o, dict):
        raise Ungueltig(_t("Einstellungen müssen ein Objekt sein.", "Settings must be an object."))
    fremd = sorted(set(o) - set(STANDARD))
    if fremd:
        raise Ungueltig(_t("Unbekannte Einstellung: %s. Möglich: %s.", "Unknown setting: %s. Possible: %s.")
                        % (", ".join(fremd), ", ".join(STANDARD)))
    e = standard()
    e.update(copy.deepcopy(o))
    for k in ("name", "untertitel", "person", "pc_name"):
        e[k] = _text(e[k], GRENZE[k], k)
    if not e["name"]:
        e["name"] = STANDARD["name"]
    if e["farbe"] not in FARBEN:
        raise Ungueltig(_t("Farbe %r gibt es nicht. Möglich: rot, cyan, blau, gruen oder eigene (mit Hexfarben).",
                           "There is no color %r. Possible: rot, cyan, blau, gruen or eigene (with hex colors).") % e["farbe"])
    if e["farbe"] == "eigene":
        f = e.get("farben")
        if not isinstance(f, dict) or not HEX.match(str(f.get("c", ""))):
            raise Ungueltig(_t("Eigene Farben brauchen mindestens die Hauptfarbe c als Hexwert, z. B. {\"c\": \"#ff8800\"}.",
                               "Custom colors need at least the main color c as a hex value, e.g. {\"c\": \"#ff8800\"}."))
        fremd = sorted(set(f) - set(EIGENE_FARBEN))
        if fremd:
            raise Ungueltig(_t("Unbekannte Farbangabe: %s. Möglich: %s.", "Unknown color key: %s. Possible: %s.")
                            % (", ".join(fremd), ", ".join(EIGENE_FARBEN)))
        for k, v in f.items():
            if not HEX.match(str(v)):
                raise Ungueltig(_t("Farbe %s muss ein Hexwert wie #ff8800 sein.", "Color %s must be a hex value like #ff8800.") % k)
        e["farben"] = {k: v.lower() for k, v in f.items()}
    else:
        e["farben"] = None
    b = _liste(e["bereiche"], len(BEREICHE), "bereiche")
    unbekannt = [x for x in b if x not in BEREICHE]
    if unbekannt:
        raise Ungueltig(_t("Unbekannter Bereich: %s. Möglich: %s.", "Unknown panel: %s. Possible: %s.")
                        % (", ".join(map(str, unbekannt)), ", ".join(BEREICHE)))
    e["bereiche"] = [x for x in BEREICHE if x in b]          # feste Reihenfolge, keine Doppelten
    ab = _liste(e["app_bereiche"], len(APP_BEREICHE), "app_bereiche")
    unbekannt = [x for x in ab if x not in APP_BEREICHE]
    if unbekannt:
        raise Ungueltig(_t("Unbekannter App-Bereich: %s. Möglich: %s.", "Unknown app section: %s. Possible: %s.")
                        % (", ".join(map(str, unbekannt)), ", ".join(APP_BEREICHE)))
    e["app_bereiche"] = [x for x in APP_BEREICHE if x in ab]
    g = _liste(e["begruessungen"], 8, "begruessungen")
    neu = []
    for eintrag in g:
        if not (isinstance(eintrag, list) and len(eintrag) == 2 and isinstance(eintrag[0], int) and 1 <= eintrag[0] <= 24):
            raise Ungueltig(_t("Eine Begrüßung ist [bis Stunde 1-24, Text], z. B. [11, \"Moin {person}.\"].",
                               "A greeting is [until hour 1-24, text], e.g. [11, \"Morning{, person}.\"]."))
        neu.append([eintrag[0], _text(eintrag[1], GRENZE["gruss"], _t("Begrüßung", "Greeting"))])
    e["begruessungen"] = sorted(neu, key=lambda x: x[0])
    s = _liste(e["start"], 6, "start")
    e["start"] = []
    for z in s:
        if not (isinstance(z, list) and len(z) == 2):
            raise Ungueltig(_t("Eine Startzeile ist [Name, Wert].", "A start line is [name, value]."))
        e["start"].append([_text(z[0], GRENZE["start_a"], _t("Startzeile", "Start line")),
                           _text(z[1], GRENZE["start_b"], _t("Startwert", "Start value"))])
    e["aktionen"] = _knoepfe(e["aktionen"], "aktionen")
    e["app_aktionen"] = _knoepfe(e["app_aktionen"], "app_aktionen")
    if e["nachtmodus"] not in NACHTMODUS:
        raise Ungueltig(_t("nachtmodus ist aus oder auto (zwischen 22 und 6 Uhr gedimmt).",
                           "nachtmodus is aus or auto (dimmed between 10 pm and 6 am)."))
    if e["bewegung"] not in BEWEGUNG:
        raise Ungueltig(_t("bewegung ist voll oder ruhig.", "bewegung is voll or ruhig."))
    w = e["werte_namen"]
    if not isinstance(w, dict) or set(w) - {"strom", "euro", "last"}:
        raise Ungueltig(_t("werte_namen kennt nur strom, euro und last.", "werte_namen only knows strom, euro and last."))
    e["werte_namen"] = dict(standard()["werte_namen"],
                            **{k: _text(v, GRENZE["wert_name"], _t("Wertname", "Value name")).upper() for k, v in w.items()})
    x = _liste(e["verbindungen_extra"], 4, "verbindungen_extra")
    e["verbindungen_extra"] = []
    for z in x:
        if not (isinstance(z, list) and len(z) == 2):
            raise Ungueltig(_t("Eine Zusatzzeile ist [Name, Wert].", "An extra line is [name, value]."))
        e["verbindungen_extra"].append([_text(z[0], GRENZE["extra"], _t("Zusatzzeile", "Extra line")),
                                        _text(z[1], GRENZE["extra"], _t("Zusatzwert", "Extra value"))])
    return e


def _knoepfe(liste, was):
    a = _liste(liste, 10, was)
    raus = []
    for k in a:
        if not isinstance(k, dict) or set(k) - {"text", "frage", "symbol"}:
            raise Ungueltig(_t("Ein Knopf ist {text, frage, symbol}.", "A button is {text, frage, symbol}."))
        symbol = k.get("symbol") or "stern"
        if symbol not in SYMBOLE:
            raise Ungueltig(_t("Symbol %r gibt es nicht. Möglich: %s.", "There is no icon %r. Possible: %s.") % (symbol, ", ".join(SYMBOLE)))
        knopf = {"text": _text(k.get("text", ""), GRENZE["knopf"], _t("Knopftext", "Button text")),
                 "frage": _text(k.get("frage", ""), GRENZE["frage"], _t("Knopffrage", "Button question")), "symbol": symbol}
        if not knopf["text"] or not knopf["frage"]:
            raise Ungueltig(_t("Ein Knopf braucht Text und Frage.", "A button needs text and a question."))
        raus.append(knopf)
    return raus


# Knoepfe fuehren ihre Frage beim Klick mit den Rechten des Geraets aus, an dem geklickt wird (PC-Fenster, App). Wer
# sie aendert, braucht deshalb dieselben Rechte; die Bruecke prueft das mit betrifft_knoepfe() (seit 25.10.2026).
KNOPF_SCHLUESSEL = ("aktionen", "app_aktionen", "knopf_dazu", "knopf_weg")


def betrifft_knoepfe(aenderung):
    """True, wenn die Aenderung Knoepfe setzt, dazunimmt oder entfernt."""
    return isinstance(aenderung, dict) and any(k in aenderung for k in KNOPF_SCHLUESSEL)


def aendern(aktuell, aenderung):
    """Aenderung auf die aktuellen Einstellungen anwenden. Neben ganzen Schluesseln gehen auch Schritte:
    bereiche_an / bereiche_aus (Listen), knopf_dazu ({text, frage, symbol}), knopf_weg (Text des Knopfs)."""
    if not isinstance(aenderung, dict) or not aenderung:
        raise Ungueltig(_t("Keine Änderung angegeben.", "No change given."))
    aenderung = dict(aenderung)   # seit 0.3.2 (Fund 6): das Objekt des Aufrufers bleibt unveraendert, betrifft_knoepfe()
                                  # erkennt die Knopf-Aenderung also auch noch nach diesem Aufruf
    neu = copy.deepcopy(aktuell)
    schritte = {k: aenderung.pop(k) for k in ("bereiche_an", "bereiche_aus", "knopf_dazu", "knopf_weg") if k in aenderung}
    neu.update(aenderung)
    if "farbe" in aenderung and aenderung["farbe"] != "eigene" and "farben" not in aenderung:
        neu["farben"] = None
    if "bereiche_an" in schritte:
        neu["bereiche"] = list(neu["bereiche"]) + list(_liste(schritte["bereiche_an"], len(BEREICHE), "bereiche_an"))
    if "bereiche_aus" in schritte:
        weg = _liste(schritte["bereiche_aus"], len(BEREICHE), "bereiche_aus")
        unbekannt = [x for x in weg if x not in BEREICHE]
        if unbekannt:
            raise Ungueltig(_t("Unbekannter Bereich: %s.", "Unknown panel: %s.") % ", ".join(map(str, unbekannt)))
        neu["bereiche"] = [x for x in neu["bereiche"] if x not in weg]
    if "knopf_weg" in schritte:
        name = str(schritte["knopf_weg"]).strip().lower()
        vorher = len(neu["aktionen"])
        neu["aktionen"] = [k for k in neu["aktionen"] if k["text"].lower() != name]
        if len(neu["aktionen"]) == vorher:
            raise Ungueltig(_t("Einen Knopf %r gibt es nicht.", "There is no button %r.") % schritte["knopf_weg"])
    if "knopf_dazu" in schritte:
        neu["aktionen"] = list(neu["aktionen"]) + [schritte["knopf_dazu"]]
    return pruefen(neu)


def optionen():
    """Erlaubte Werte fuers Zahnrad-Menue der App (POST /v1/einstellungen, Schluessel "optionen"). Die App baut ihr Menue
    daraus; Schema: farben, farb_namen, bereiche, app_bereiche, symbole, nachtmodus, bewegung (Listen bzw. Wörterbuch),
    grenzen (Laengengrenzen)."""
    return {"farben": list(FARBEN), "farb_namen": dict(FARB_NAMEN_EN if SPRACHE == "en" else FARB_NAMEN), "bereiche": list(BEREICHE),
            "app_bereiche": list(APP_BEREICHE), "symbole": list(SYMBOLE), "nachtmodus": list(NACHTMODUS),
            "bewegung": list(BEWEGUNG), "grenzen": dict(GRENZE)}


def beschreiben(e):
    """Kurzfassung fuer das Gehirn (und zum Vorlesen)."""
    namen = FARB_NAMEN_EN if SPRACHE == "en" else FARB_NAMEN
    farbe = namen[e["farbe"]] + (" (%s)" % e["farben"]["c"] if e["farbe"] == "eigene" else "")
    aus = [b for b in BEREICHE if b not in e["bereiche"]]
    extra = ""
    if e["app_aktionen"]:
        extra += _t(" Knöpfe in der App: %s.", " Buttons in the app: %s.") % ", ".join(k["text"] for k in e["app_aktionen"])
    app_aus = [b for b in APP_BEREICHE if b not in e["app_bereiche"]]
    if app_aus:
        extra += _t(" In der App ausgeblendet: %s.", " Hidden in the app: %s.") % ", ".join(app_aus)
    if e["nachtmodus"] != "aus" or e["bewegung"] != "voll":
        extra += _t(" Nachtmodus: %s, Bewegung: %s.", " Night mode: %s, motion: %s.") % (e["nachtmodus"], e["bewegung"])
    keine = _t("keine", "none")
    return (_t("Farbe: %s. Zeile unter dem Logo: %s. Bereiche an: %s%s. Knöpfe: %s.%s",
               "Color: %s. Line under the logo: %s. Panels on: %s%s. Buttons: %s.%s") % (
        farbe, e["untertitel"] or _t("(leer)", "(empty)"), ", ".join(e["bereiche"]) or keine,
        _t("; aus: ", "; off: ") + ", ".join(aus) if aus else "", ", ".join(k["text"] for k in e["aktionen"]) or keine, extra))


def _schreiben(pfad, daten):
    tmp = pfad + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, pfad)


class Speicher:
    """daten/oberflaeche.json (aktuell), oberflaeche-grund.json (Stand nach der Einrichtung, Ziel von "Grundeinstellung"),
    oberflaeche-verlauf.json (die letzten 20 Fassungen, Ziel von "rueckgaengig")."""

    def __init__(self, ordner):
        self.datei = os.path.join(ordner, "oberflaeche.json")
        self.grund = os.path.join(ordner, "oberflaeche-grund.json")
        self.verlauf = os.path.join(ordner, "oberflaeche-verlauf.json")

    def _lesen(self, pfad, sonst):
        try:
            with open(pfad, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return sonst

    def laden(self):
        """Aktuelle Einstellungen; eine kaputte oder fehlende Datei faellt auf Grundeinstellung bzw. Vorlage zurueck."""
        for pfad in (self.datei, self.grund):
            roh = self._lesen(pfad, None)
            if roh is not None:
                try:
                    return pruefen(roh)
                except Ungueltig:
                    continue
        return pruefen({})

    def speichern(self, neu, quelle):
        alt = self.laden()
        if alt == neu:
            return False
        verlauf = self._lesen(self.verlauf, [])
        verlauf.append({"zeit": time.strftime("%Y-%m-%d %H:%M:%S"), "quelle": quelle, "vorher": alt})
        _schreiben(self.verlauf, verlauf[-20:])
        _schreiben(self.datei, neu)
        if not os.path.exists(self.grund):
            _schreiben(self.grund, alt)
        return True

    def _knoepfe_von_jetzt(self, ziel):
        """Knoepfe aus dem aktuellen Stand ins Ziel uebernehmen (fuer Quellen ohne PC-Rechte, seit 0.3.2, Fund 7)."""
        jetzt = self.laden()
        return pruefen(dict(ziel, aktionen=jetzt["aktionen"], app_aktionen=jetzt["app_aktionen"]))

    def rueckgaengig(self, knoepfe_behalten=False):
        """Letzte Fassung zurueck. knoepfe_behalten=True fuer Quellen ohne PC-Rechte: Aussehen und Bereiche gehen
        zurueck, die Knoepfe bleiben wie jetzt (sonst kaeme ein bewusst geloeschter Knopf samt Auftrag zurueck)."""
        verlauf = self._lesen(self.verlauf, [])
        if not verlauf:
            raise Ungueltig(_t("Es gibt keine frühere Fassung.", "There is no earlier version."))
        letzte = verlauf.pop()
        ziel = pruefen(letzte["vorher"])
        if knoepfe_behalten:
            ziel = self._knoepfe_von_jetzt(ziel)
        _schreiben(self.datei, ziel)
        _schreiben(self.verlauf, verlauf)
        return self.laden()

    def grundeinstellung(self, knoepfe_behalten=False):
        """Stand nach der Einrichtung (zum Speichern durch den Aufrufer); knoepfe_behalten wie bei rueckgaengig()."""
        roh = self._lesen(self.grund, None)
        ziel = pruefen(roh) if roh is not None else pruefen({})
        return self._knoepfe_von_jetzt(ziel) if knoepfe_behalten else ziel
