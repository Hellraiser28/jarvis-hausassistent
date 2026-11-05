"""Jarvis ruft an (seit 0.6): ausgehender Anruf auf das Handy der Hauptperson ueber HA-SIP.

Weg: Bruecke -> HA-Skript script.jarvis_ruft_an (HA-SIP "dial" mit Ansage und Tastenmenue: 1 = gehoert, 2 = mit Jarvis
sprechen) -> Rueckmeldungen von HA-SIP per Webhook -> HA-Automation -> POST /v1/anruf/ereignis an die Bruecke. Die
Rufnummer steht nur in HA, nie hier.

Ob angerufen wird, entscheidet dieser Code, nie das Sprachmodell und nie Text von aussen (Mails, Nachrichten): Ein Anruf
braucht einen festgelegten Anlass aus den Regeln (daten/anruf.json). Solange "scharf" nicht gesetzt ist, wird nur
protokolliert, was passiert waere ("trocken"); scharf wird es erst nach einem Testanruf.

Spielregeln (Standard, in daten/anruf.json einstellbar): Anlaesse sind der eigene Zuruf der Hauptperson (Weckanruf,
"ruf mich an, wenn ..."), Unwetterwarnungen Stufe 3/4 und ein kritisches NAS (Platte, RAID); das Babyfon nie. In der
Ruhezeit 22-7 Uhr ruft nur an, was die Hauptperson ausdruecklich bestellt hat, alles andere bleibt Push. Hoechstens 3
Anrufe am Tag, 15 Minuten Abstand, derselbe Anlass erst nach 4 Stunden (ein Zuruf ist jedes Mal ein eigener Auftrag).
Nimmt niemand ab, kommt der zweite Versuch nach 5 Minuten, also innerhalb der 15 Minuten, in denen Android bei "Bitte
nicht stoeren" einen wiederholten Anrufer durchlaesst; danach Push.

Nur Python-Standardbibliothek (3.8)."""
import json
import os
import re
import time
from datetime import datetime

REGELN_STANDARD = {
    "scharf": False,                 # erst nach einem Testanruf (HA-Skript eingerichtet)
    "ruhe": ["22:00", "07:00"],      # Ruhezeit (ueber Mitternacht erlaubt)
    "ruhe_ausnahmen": ["zuruf"],     # nachts nur, was die Hauptperson ausdruecklich bestellt hat
    "max_tag": 3,                    # hoechstens so viele Anrufe je Kalendertag
    "abstand_min": 15,               # Mindestabstand zwischen zwei Anrufen (gilt nicht fuer den zweiten Versuch)
    "gleicher_anlass_min": 240,      # derselbe Anlass erst nach so vielen Minuten wieder
    "gleicher_anlass_ausnahmen": ["zuruf"],   # jeder Zuruf ist ein eigener Auftrag
    "wiederholen": 1,                # so oft nochmal anrufen, wenn niemand abnimmt oder nicht quittiert wird
    "wiederholen_nach_min": 5,       # innerhalb von 15 min: Android laesst wiederholte Anrufer durch "Bitte nicht stoeren"
    "danach_push": True,             # am Ende ohne Quittung: Push mit dem Text
    "anlaesse": {"test": {"name": "Testanruf"},
                 "zuruf": {"name": "Auftrag der Hauptperson (Weckanruf, ruf mich an, wenn ...)"},
                 "unwetter": {"name": "DWD-Unwetter Stufe 3 oder 4"},
                 "nas": {"name": "NAS kritisch (Platte, RAID)"}},
}
ENDZUSTAENDE = ("quittiert", "gespraech_beendet", "nicht_erreicht", "keine_antwort", "aufgelegt", "trocken", "gesperrt",
                "fehler")
OHNE_QUITTUNG = ("nicht_erreicht", "keine_antwort", "aufgelegt")
TEXT_MAX = 280
LAUF_MAX_S = 600                     # ohne Endzustand nach 10 Minuten: verfallen (HA hat sich nie gemeldet)
# (Deutsch, Englisch); %s in ANSAGE_VOR: " <Anrede>" oder leer
ANSAGE_VOR = ("Hallo%s, hier ist Jarvis. ", "Hello%s, this is Jarvis. ")
ANSAGE_NACH = (" Drück die 1, wenn du es gehört hast, oder die 2, wenn du mit mir sprechen willst.",
               " Press 1 if you heard it, or 2 if you want to talk to me.")


# Sprache der Texte, die die Person direkt hoert oder sieht (seit 0.6 im Release). Die Bruecke setzt sie beim Start aus
# der Einrichtung (antworten.json "sprache"), wie bei verhalten.py und szenen.py.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


def regeln_laden(pfad):
    """Regeln aus daten/anruf.json ueber die Standardwerte legen. Falsche Typen bleiben beim Standard."""
    r = json.loads(json.dumps(REGELN_STANDARD))
    try:
        roh = json.load(open(pfad, encoding="utf-8"))
    except (OSError, ValueError):
        return r
    if not isinstance(roh, dict):
        return r
    for k, standard in REGELN_STANDARD.items():
        v = roh.get(k)
        if k == "scharf":
            r[k] = v is True
        elif k == "ruhe" and isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) and re.fullmatch(r"\d\d:\d\d", x) for x in v):
            r[k] = v
        elif k in ("ruhe_ausnahmen", "gleicher_anlass_ausnahmen") and isinstance(v, list):
            r[k] = [x for x in v if isinstance(x, str)]
        elif k == "anlaesse" and isinstance(v, dict):
            r[k] = {a: d for a, d in v.items() if isinstance(a, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,31}", a) and isinstance(d, dict)}
        elif isinstance(standard, bool) and isinstance(v, bool):
            r[k] = v
        elif isinstance(standard, int) and not isinstance(standard, bool) and isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 10000:
            r[k] = v
    return r


def text_sauber(t):
    """Ansagetext: keine Steuerzeichen, keine Vorlagen-Klammern (HA rendert Vorlagen), hoechstens TEXT_MAX Zeichen."""
    t = re.sub(r"[\x00-\x1f\x7f{}%<>]", " ", str(t or ""))
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > TEXT_MAX:
        t = t[:TEXT_MAX - 1].rsplit(" ", 1)[0] + "…"
    return t


def ansage(text, name=""):
    """Was am Telefon gesprochen wird. name: Anrede der angerufenen Person (die Bruecke gibt den Anzeigenamen der
    Hauptperson aus personen.json mit); leer: ohne Namen."""
    n = text_sauber(name)[:40]
    return _t(*ANSAGE_VOR) % ((" " + n) if n else "") + text_sauber(text) + _t(*ANSAGE_NACH)


def _minuten(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def in_ruhezeit(regeln, jetzt):
    von, bis = (_minuten(x) for x in regeln["ruhe"])
    m = jetzt.hour * 60 + jetzt.minute
    return von <= m < bis if von <= bis else (m >= von or m < bis)


def pruefen(anlass, regeln, verlauf, jetzt_s, jetzt_dt=None):
    """(True, "") oder (False, Grund). verlauf: bisherige Eintraege (neueste zuletzt)."""
    jetzt_dt = jetzt_dt or datetime.fromtimestamp(jetzt_s)
    if anlass not in regeln["anlaesse"]:
        return False, _t("unbekannter Anlass", "unknown occasion")
    if in_ruhezeit(regeln, jetzt_dt) and anlass not in regeln["ruhe_ausnahmen"]:
        return False, _t("Ruhezeit", "quiet hours")
    echt = [e for e in verlauf if e.get("status") not in ("gesperrt", "trocken")]
    if aktiv(verlauf, jetzt_s):
        return False, _t("es läuft schon ein Anruf", "a call is already in progress")
    heute = jetzt_dt.strftime("%Y-%m-%d")
    if sum(1 for e in echt if datetime.fromtimestamp(e.get("zeit", 0)).strftime("%Y-%m-%d") == heute) >= regeln["max_tag"]:
        return False, _t("Tageslimit erreicht", "daily limit reached")
    if echt and jetzt_s - echt[-1].get("zeit", 0) < regeln["abstand_min"] * 60:
        return False, _t("zu kurz nach dem letzten Anruf", "too soon after the last call")
    gleich = [e for e in echt if e.get("anlass") == anlass] if anlass not in regeln["gleicher_anlass_ausnahmen"] else []
    if gleich and jetzt_s - gleich[-1].get("zeit", 0) < regeln["gleicher_anlass_min"] * 60:
        return False, _t("derselbe Anlass vor kurzem", "same occasion recently")
    return True, ""


def anlegen(anlass, text, regeln, verlauf, jetzt_s, versuch=1, vorher=None):
    """Neuer Eintrag: status "waehlt" (scharf), "trocken" (nicht scharf) oder "gesperrt" (mit Grund)."""
    ok, grund = pruefen(anlass, regeln, verlauf, jetzt_s) if versuch == 1 else (True, "")
    ms, vergeben = int(jetzt_s * 1000), {x.get("id") for x in verlauf}
    while "a%x" % ms in vergeben:        # zwei Eintraege in derselben Millisekunde nie mit gleicher Kennung
        ms += 1
    e = {"id": "a%x" % ms, "zeit": int(jetzt_s), "anlass": anlass, "text": text_sauber(text),
         "versuch": versuch, "status": "waehlt" if ok and regeln["scharf"] else ("trocken" if ok else "gesperrt"),
         "grund": grund, "verlauf": [], "internal_id": None}
    if vorher:
        e["vorher"] = vorher
    return e


def ereignis(e, daten, jetzt_s):
    """Rueckmeldung von HA-SIP einarbeiten. Gibt True zurueck, wenn sie zu diesem Anruf gehoert und verarbeitet wurde."""
    if not isinstance(daten, dict) or daten.get("call_direction") not in (None, "outgoing"):
        return False
    iid = str(daten.get("internal_id") or "")[:80]
    if e.get("internal_id") and iid and iid != e["internal_id"]:
        return False
    if iid and not e.get("internal_id"):
        e["internal_id"] = iid
    ev = str(daten.get("event") or "")[:40]
    menue = str(daten.get("menu_id") or "")[:40]
    ziffer = str(daten.get("digit") or "")[:4]
    e["verlauf"].append([int(jetzt_s), ev, menue or ziffer])
    del e["verlauf"][:-30]
    s = e["status"]
    if ev == "call_established" and s == "waehlt":
        e["status"] = "angenommen"
    elif ev == "ring_timeout" and s == "waehlt":
        e["status"] = "nicht_erreicht"
    elif ev == "entered_menu" and menue == "quittiert" or ev == "dtmf_digit" and ziffer == "1" and s == "angenommen":
        e["status"] = "quittiert"
    elif ev == "entered_menu" and menue == "gespraech" or ev == "dtmf_digit" and ziffer == "2" and s == "angenommen":
        e["status"] = "gespraech"
    elif ev == "entered_menu" and menue == "keine_antwort" or ev == "timeout" and s == "angenommen":
        e["status"] = "keine_antwort"
    elif ev == "call_disconnected":
        e["status"] = {"waehlt": "nicht_erreicht", "angenommen": "aufgelegt", "gespraech": "gespraech_beendet"}.get(s, s)
    return True


def naechster_schritt(e, regeln):
    """Nach einem Endzustand ohne Quittung: ("nochmal", Sekunden) oder ("push", None) oder (None, None)."""
    if e.get("status") not in OHNE_QUITTUNG or e.get("folge_erledigt"):
        return None, None
    if e.get("versuch", 1) <= regeln["wiederholen"]:
        return "nochmal", regeln["wiederholen_nach_min"] * 60
    return ("push", None) if regeln["danach_push"] else (None, None)


def aktiv(verlauf, jetzt_s=None):
    """Der laufende Anruf (nicht im Endzustand, juenger als LAUF_MAX_S) oder None."""
    jetzt_s = time.time() if jetzt_s is None else jetzt_s
    for e in reversed(verlauf):
        if e.get("status") not in ENDZUSTAENDE and jetzt_s - e.get("zeit", 0) < LAUF_MAX_S:
            return e
    return None


def verfallen(verlauf, jetzt_s):
    """Laufende Anrufe ohne Rueckmeldung nach LAUF_MAX_S auf "fehler" setzen. Gibt die Zahl zurueck."""
    n = 0
    for e in verlauf:
        if e.get("status") not in ENDZUSTAENDE and jetzt_s - e.get("zeit", 0) >= LAUF_MAX_S:
            e["status"], e["grund"], n = "fehler", _t("keine Rückmeldung von HA", "no response from HA"), n + 1
    return n


def laden(pfad):
    try:
        d = json.load(open(pfad, encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def speichern(pfad, verlauf):
    """Verlauf (Ansagetexte, Anlaesse) atomar und von Anfang an nur fuer den Besitzer lesbar (600), wie gaeste.py:
    os.open legt die Datei gleich mit 600 an, das chmod davor deckt eine liegengebliebene .neu mit anderen Rechten ab."""
    verlauf = verlauf[-200:]
    neu = pfad + ".neu"
    fd = os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(neu, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(verlauf, f, ensure_ascii=False)
    os.replace(neu, pfad)


def kontext_hinweis(verlauf, jetzt_s, name=""):
    """Fuer den Lage-Kontext: Jarvis weiss, warum er gerade anruft, wenn die angerufene Person am Telefon mit ihm
    spricht. name: wie bei ansage(); leer: "die Hauptperson"."""
    n = str(name or "").strip()[:40] or _t("die Hauptperson", "the main person")
    for e in reversed(verlauf):
        if e.get("status") == "gespraech" and jetzt_s - e.get("zeit", 0) < 900:
            return _t(" Du hast %(n)s eben angerufen, Grund: „%(t)s“. %(N)s hat am Telefon die 2 gedrückt und spricht "
                      "jetzt mit dir. Fang mit dem Grund an, kurz.",
                      " You just called %(n)s, reason: “%(t)s”. %(N)s pressed 2 on the phone and is talking to you now. "
                      "Start with the reason, briefly.") % {"n": n, "N": n[:1].upper() + n[1:], "t": e.get("text", "")}
    return ""
