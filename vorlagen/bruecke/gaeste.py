"""Gaeste-Modus (seit 0.6): Besuch spricht mit Jarvis ueber die Sprachgeraete im Raum, ohne an Persoenliches zu kommen.

daten/gaeste.json (600), eine Liste:
    [{"id": "gast-3fa9c1", "name": "Anna", "bis": 1793000000.0, "erstellt": 1792800000.0, "raeume": ["Wohnzimmer"]}]

- Ein Gast bekommt KEIN eigenes Jarvis (keine Kopplung, kein Token, keine Web-App, kein Fernzugang). Solange ein
  Gastzugang laeuft, gelten fuer jede Frage von einem Sprachgeraet (Home Assistant, Alexa) aus einem freigegebenen
  Raum Gastrechte: Person = der Gast, Rolle "gast" (personen.GAST_WERKZEUGE). Das gilt fuer jeden, der dort spricht,
  auch fuer die Familie. Die Stimmerkennung (sprecher.py, wenn eingeschaltet) hebt das nicht auf: Sie senkt Rechte
  nur, wechselt an anderen Sprachgeraeten hoechstens zu einem Gast, und im Gastraum bleibt der Gast Gast. App, PC und
  Web-App sind davon nicht betroffen.
- Anlegen nur durch die Hauptperson (Werkzeug gastzugang -> /intern/gast). Dabei schaltet die Bruecke das Gaeste-WLAN
  ein (Schalter des Routers in Home Assistant, z. B. aus der FRITZ!Box-Integration) und schickt den QR-Code per Push an
  die Hauptperson. Auf den Wandbildschirm kommt er nur mit "qr_wand": true (Standard nein: dort waere er im Heimnetz
  ohne Anmeldung lesbar).
- Ablauf: ab "bis" gelten keine Gastrechte mehr; die Bruecke raeumt auf (Verlauf, Gespraeche, QR-Code) und schaltet
  das Gaeste-WLAN wieder aus, wenn sie es eingeschaltet hat und kein Gast mehr da ist.

Raumzuordnung Geraet -> Raum, in dieser Reihenfolge: "geraete" in daten/gaeste_einstellungen.json, "geraete" in
daten/raeume.json (Format der Raumdurchsagen, nur gelesen, keine Abhaengigkeit), der HA-Bereich, den die Bruecke
mitbekommt, und ein Geraetename, der einem Raumnamen entspricht (die Echos heissen wie ihr Raum).

daten/gaeste_einstellungen.json (optional) ueberschreibt die VORGABE einzeln. wlan_schalter und wlan_qr muessen zu den
eigenen Entitaeten in Home Assistant passen; die Vorgabe sind Platzhalter (fehlt der Schalter in HA, sagt die Bruecke
das ehrlich und schickt den Push ohne QR-Code).
"""
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime

DATEI = "gaeste.json"
EINSTELLUNGEN = "gaeste_einstellungen.json"
WLAN_STAND = "gaeste_wlan.json"            # {"von_uns": true}: das Gaeste-WLAN hat die Bruecke eingeschaltet
ID = re.compile(r"^gast-[0-9a-f]{6}$")
# Sprachgeraete stehen fest in einem Raum; App, PC und Web-App wandern mit der Person und bekommen nie Gastrechte
RAUM_QUELLEN = ("ha", "alexa", "test-ha", "test-alexa")
VORGABE = {
    "stunden": 48,                # Gueltigkeit ohne Angabe
    "max_tage": 14,               # laenger nie
    "raeume": ["Wohnzimmer"],     # Raeume mit Gastrechten (= Home-Assistant-Bereiche fuer Licht und Musik); auf Englisch
                                  # "Living Room" (einstellungen())
    "geraete": {},                # Geraetename -> Raum, z. B. {"Home Assistant Voice Wohnzimmer": "Wohnzimmer"}
    "max_aktiv": 8,
    "anlegen_je_stunde": 6,
    "wlan_schalter": "switch.gaeste_wlan",       # Platzhalter: Schalter des Gaeste-WLANs in HA
    "wlan_qr": "image.gaeste_wlan_qr",           # Platzhalter: QR-Bild des Gaeste-WLANs in HA
    "qr_wand": False,             # QR-Code auch auf dem Wandbildschirm (Standard nein, nur per Push)
}
TAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
TAGE_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONATE_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


# Sprache der Texte, die die Person direkt sieht oder hoert (seit 0.6 im Release). Die Bruecke setzt sie beim Start aus
# der Einrichtung (antworten.json "sprache"), wie bei verhalten.py und szenen.py.
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


def _text(s, laenge=40):
    return re.sub(r"[\x00-\x1f<>\[\]{}⟦⟧`\"'\\]", "", str(s or "")).strip()[:laenge]


def norm(s):
    s = str(s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def einstellungen(daten):
    e = dict(VORGABE, geraete={}, raeume=[_t("Wohnzimmer", "Living Room")])
    try:
        roh = json.load(open(os.path.join(daten, EINSTELLUNGEN), encoding="utf-8"))
    except (OSError, ValueError):
        roh = {}
    if not isinstance(roh, dict):
        return e
    for k in ("stunden", "max_tage", "max_aktiv", "anlegen_je_stunde"):
        if isinstance(roh.get(k), int) and not isinstance(roh.get(k), bool) and 0 < roh[k] <= 10000:
            e[k] = roh[k]
    if isinstance(roh.get("raeume"), list):
        e["raeume"] = [_text(x) for x in roh["raeume"] if isinstance(x, str) and _text(x)][:10]
    if isinstance(roh.get("geraete"), dict):
        e["geraete"] = {str(k)[:80]: _text(v) for k, v in list(roh["geraete"].items())[:40] if isinstance(v, str) and _text(v)}
    for k in ("wlan_schalter", "wlan_qr"):
        if isinstance(roh.get(k), str) and re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", roh[k]):
            e[k] = roh[k]
    if isinstance(roh.get("qr_wand"), bool):
        e["qr_wand"] = roh["qr_wand"]
    e["max_tage"] = min(e["max_tage"], 90)
    return e


def alle(daten):
    """Alle Eintraege (auch abgelaufene), geprueft."""
    try:
        roh = json.load(open(os.path.join(daten, DATEI), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    liste = []
    for g in roh if isinstance(roh, list) else []:
        if not isinstance(g, dict) or not ID.match(str(g.get("id", ""))):
            continue
        try:
            bis, erstellt = float(g["bis"]), float(g.get("erstellt") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        liste.append({"id": g["id"], "name": _text(g.get("name")) or _t("Gast", "Guest"), "bis": bis, "erstellt": erstellt,
                      "raeume": [_text(r) for r in g.get("raeume") or [] if isinstance(r, str) and _text(r)][:10]})
    return liste


def aktive(daten, jetzt=None):
    jetzt = time.time() if jetzt is None else jetzt
    return [g for g in alle(daten) if g["bis"] > jetzt]


def abgelaufene(daten, jetzt=None):
    jetzt = time.time() if jetzt is None else jetzt
    return [g for g in alle(daten) if g["bis"] <= jetzt]


def _schreiben(pfad, obj):
    fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.chmod(pfad + ".neu", 0o600)
    os.replace(pfad + ".neu", pfad)


def speichern(daten, liste):
    _schreiben(os.path.join(daten, DATEI), liste)


def finden(liste, wer):
    """Nach Kennung oder Namen (ohne Gross-/Kleinschreibung); bei mehreren gleichen Namen keiner."""
    w = str(wer or "").strip().lower()
    if not w:
        return None
    treffer = [g for g in liste if g["id"] == w] or [g for g in liste if g["name"].lower() == w]
    return treffer[0] if len(treffer) == 1 else None


def bis_lesen(text, jetzt=None, stunden=48, max_tage=14):
    """'JJJJ-MM-TT HH:MM' oder 'JJJJ-MM-TT' (dann 23:59) oder leer (Vorgabe). Nie vorbei, nie laenger als max_tage."""
    jetzt = time.time() if jetzt is None else jetzt
    t = str(text or "").strip().replace("T", " ")
    if not t:
        bis = jetzt + stunden * 3600
    else:
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
                bis = datetime.strptime(t + " 23:59", "%Y-%m-%d %H:%M").timestamp()
            else:
                bis = datetime.strptime(t[:16], "%Y-%m-%d %H:%M").timestamp()
        except ValueError:
            raise Fehler(_t("Zeit nicht verstanden, bitte als JJJJ-MM-TT oder JJJJ-MM-TT HH:MM.",
                            "Time not understood, please give it as YYYY-MM-DD or YYYY-MM-DD HH:MM."))
    if bis <= jetzt + 60:
        raise Fehler(_t("Das Ende liegt in der Vergangenheit.", "The end is in the past."))
    return min(bis, jetzt + max_tage * 86400)


def neu(daten, name, bis, jetzt=None):
    """Neuen Gastzugang anlegen (nur die Bruecke ruft das, nach der Rollenpruefung). Raeume aus den Einstellungen."""
    jetzt = time.time() if jetzt is None else jetzt
    e = einstellungen(daten)
    name = _text(name)
    if not name:
        raise Fehler(_t("Wie heißt der Besuch?", "What is the visitor's name?"))
    liste = alle(daten)
    aktiv = [g for g in liste if g["bis"] > jetzt]
    if len(aktiv) >= e["max_aktiv"]:
        raise Fehler(_t("Es gibt schon %d aktive Gastzugänge.", "There are already %d active guest accesses.") % len(aktiv))
    if any(g["name"].lower() == name.lower() for g in aktiv):
        raise Fehler(_t("Für %s läuft schon ein Gastzugang.", "%s already has a guest access.") % name)
    vorhanden = {g["id"] for g in liste}
    gid = "gast-" + secrets.token_hex(3)
    while gid in vorhanden:
        gid = "gast-" + secrets.token_hex(3)
    g = {"id": gid, "name": name, "bis": float(bis), "erstellt": jetzt, "raeume": list(e["raeume"])}
    speichern(daten, [x for x in liste if x["bis"] > jetzt - 7 * 86400] + [g])
    return g


def entfernen(daten, gid):
    liste = alle(daten)
    rest = [g for g in liste if g["id"] != gid]
    if len(rest) == len(liste):
        return None
    speichern(daten, rest)
    return next(g for g in liste if g["id"] == gid)


def _raeume_json(daten):
    """Geraete -> Raumname aus daten/raeume.json (Format der Raumdurchsagen), nur lesen; ohne Datei leer."""
    try:
        d = json.load(open(os.path.join(daten, "raeume.json"), encoding="utf-8"))
        raeume, geraete = d.get("raeume") or {}, d.get("geraete") or {}
        return {str(k): str((raeume.get(v) or {}).get("name") or (raeume.get(v) or {}).get("bereich") or v)
                for k, v in geraete.items() if isinstance(v, str)}
    except (OSError, ValueError, AttributeError):
        return {}


def raum_von(daten, quelle, geraet, bereich=""):
    """Raum eines Sprachgeraets (Name, wie in den Einstellungen) oder "" (kein Sprachgeraet, unbekannt)."""
    if quelle not in RAUM_QUELLEN:
        return ""
    e, rj = einstellungen(daten), _raeume_json(daten)
    g = norm(geraet)
    for k, v in list(e["geraete"].items()) + list(rj.items()):
        if g and norm(k) == g:
            return v
    if bereich:
        return _text(bereich)
    return next((r for r in set(e["raeume"]) | set(rj.values()) if g and norm(r) == g), "")


def gast_fuer_raum(daten, raum, jetzt=None):
    """Der juengste aktive Gastzugang, der diesen Raum umfasst, sonst None."""
    if not raum:
        return None
    treffer = [g for g in aktive(daten, jetzt) if norm(raum) in {norm(r) for r in g["raeume"]}]
    return max(treffer, key=lambda g: g["erstellt"]) if treffer else None


def _wlan_stand(daten):
    try:
        d = json.load(open(os.path.join(daten, WLAN_STAND)))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def wlan_von_uns(daten, wert=None):
    if wert is None:
        return _wlan_stand(daten).get("von_uns") is True
    d = dict(_wlan_stand(daten), von_uns=bool(wert))
    if not wert:
        for k in ("bis", "link", "link_bis"):    # aus: QR-Anfrage erledigt, Link zur QR-Seite ungueltig
            d.pop(k, None)
    _schreiben(os.path.join(daten, WLAN_STAND), d)
    return bool(wert)


def wlan_bis(daten, wert=None):
    """Bis wann das Gaeste-WLAN nach einer QR-Anfrage aus der App ohne Gastzugang an bleibt (0: keine Anfrage).
    Ausschalten tut die Bruecke, und nur, wenn sie es eingeschaltet hat (wlan_von_uns)."""
    if wert is None:
        b = _wlan_stand(daten).get("bis")
        return float(b) if isinstance(b, (int, float)) and not isinstance(b, bool) else 0.0
    _schreiben(os.path.join(daten, WLAN_STAND), dict(_wlan_stand(daten), bis=float(wert)))
    return float(wert)


LINK = re.compile(r"^[A-Za-z0-9_-]{22}$")


def qr_link(daten, bis=None, jetzt=None):
    """Zufallslink (128 Bit) fuer die QR-Seite der Bruecke (/gast-qr/<link>, nur Heimnetz).
    Mit bis: anlegen oder verlaengern (hoechstens so lange wie das Gaeste-WLAN-Fenster) und zurueckgeben; ohne bis:
    der gueltige Link oder ''. Geht das WLAN durch die Bruecke aus, verfaellt er (wlan_von_uns(False))."""
    jetzt = time.time() if jetzt is None else jetzt
    d = _wlan_stand(daten)
    gueltig = isinstance(d.get("link"), str) and LINK.match(d["link"]) and isinstance(d.get("link_bis"), (int, float)) \
        and d["link_bis"] > jetzt
    if bis is None:
        return d["link"] if gueltig else ""
    if not gueltig:
        d["link"], d["link_bis"] = secrets.token_urlsafe(16), 0.0
    d["link_bis"] = max(float(d["link_bis"]), float(bis))
    _schreiben(os.path.join(daten, WLAN_STAND), d)
    return d["link"]


def qr_link_pruefen(daten, kandidat, jetzt=None):
    """Passt kandidat zum gueltigen Link? Vergleich in konstanter Zeit."""
    aktuell = qr_link(daten, jetzt=jetzt)
    return bool(aktuell) and isinstance(kandidat, str) and hmac.compare_digest(aktuell, kandidat)


def wann(ts):
    """Ende eines Gastzugangs in Worten: "morgen 18:00 Uhr", "Freitag 06.11. 18:00 Uhr" bzw. "Friday 6 Nov at 18:00"."""
    d = datetime.fromtimestamp(ts)
    tage = (d.date() - datetime.now().date()).days
    if SPRACHE == "en":
        tag = {0: "today", 1: "tomorrow"}.get(tage, "%s %d %s" % (TAGE_EN[d.weekday()], d.day, MONATE_EN[d.month - 1]))
        return "%s at %s" % (tag, d.strftime("%H:%M"))
    tag = {0: "heute", 1: "morgen"}.get(tage, TAGE[d.weekday()] + d.strftime(" %d.%m."))
    return "%s %s Uhr" % (tag, d.strftime("%H:%M"))
