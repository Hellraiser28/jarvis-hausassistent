"""Personen hinter den Geraeten (seit 0.4, 28.10.2026): wer fragt, was darf er, wessen Gedaechtnis gilt.

daten/personen.json (600), z. B.
    {"alex": {"name": "Alex", "rolle": "haupt", "paperless_id": 3},
     "sam": {"name": "Sam", "rolle": "familie", "kontakt": "Sam", "paperless_id": 4,
                "paperless_token_datei": "/.../paperless_token_sam",
                "postfach_zugang_datei": "/.../postfach_sam.json"}}

rolle "haupt": alles wie bisher (Admin-Kollege, PC, Postfach, eigene Dokumente und Notizen).
rolle "familie": nur der Haushalt (FAMILIE_WERKZEUGE), eigener Verlauf, eigenes Gedaechtnis plus das gemeinsame,
eigene Erinnerungen auf das eigene Handy. Wer keinem Geraet zugeordnet ist (Hauptschluessel, PC, Home Assistant,
Alexa), ist die Hauptperson; ueber Alexa und die Sprachkette gelten weiter die Einschraenkungen nach Quelle.
Seit 0.6: Paperless mit dem eigenen Token (paperless_token_datei) und ein eigenes Postfach (postfach_zugang_datei,
ohne Mail-Wache); ohne diese Felder hat die Person dort nichts.

rolle "gast" (seit 0.6): steht nie in personen.json, sondern kommt befristet aus daten/gaeste.json (gaeste.py, optional).
Nur GAST_WERKZEUGE, kein Gedaechtnis, ab Ablauf gar nichts mehr. Gaeste sprechen ueber die Sprachgeraete im Raum und
besitzen nie ein Geraet: Ein Geraet mit einem Gast als Person gilt als Geraet ohne Rechte.

Fehler fuehren nie zur Hauptperson: Ist personen.json da, aber nicht lesbar (oder ohne Hauptperson), oder traegt ein
Geraet eine Person, die es nicht gibt (oder einen Gast), liefert fuer_geraet None. Die Bruecke lehnt die Frage dann ab.
"""
import json
import os
import re
import time

try:
    import gaeste                       # seit 0.6, optional: ohne gaeste.py gibt es schlicht keine Gaeste
except ImportError:
    gaeste = None

ID = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")
ROLLEN = ("haupt", "familie")           # "gast" nie aus personen.json, nur aus gaeste.py
STANDARD = {"ich": {"name": "Hauptperson", "rolle": "haupt"}}   # ohne personen.json

# Was eine Person mit Rolle "familie" darf: Haushalt. Nicht: Admin-Kollege, PC, Notizen und Aufgaben der Hauptperson,
# deren Routinen, Nachrichtenquellen, Verhalten von Jarvis, NAS-Zustand, Handy-Suche. Postfach nur das eigene
# (postfach_zugang_datei), das Aussehen (oberflaeche) nur auf den eigenen Geraeten: beides prueft die Bruecke bzw. der
# Werkzeug-Server. handy/handy_bedienen wirken nur auf das Geraet, das gerade fragt.
# Die Liste nennt die Werkzeuge der Beispiel-Einrichtung; an die eigenen Werkzeuge anpassen.
FAMILIE_WERKZEUGE = frozenset("""
termine termin_eintragen haus_status wetter unwetter geraete_suchen geraet_steuern saugroboter nachricht hoerspiel morgenradio fernsehen
nachrichten fussball heute_in_geschichte neu_in_mediathek steam_angebote briefing tv_programm
merken gedaechtnis frueher vergessen gedaechtnis_datei erinnern erinnerungen ankunft offene_faeden vorlesen warten einkaufsliste rezepte
dokumente inventar bahn ferien kurse musik radio internet
pdf_erstellen bild_bearbeiten bild_erzeugen datei_umwandeln umwandeln_moeglich dokument_markdown
szenen brief_ablegen fristen postfach gast_wlan gast_wlan_qr leinwand quiz
handy handy_bedienen
oberflaeche
""".split())

# Seit 0.6: Was ein Gast darf. Nichts mit Gedaechtnis, Terminen, Postfach, Dokumenten, Nachrichten an Menschen,
# Szenen, PC oder Admin. geraet_steuern, geraete_suchen, musik, radio und rezepte schraenkt der Werkzeug-Server fuer
# Gaeste zusaetzlich ein (freigegebene Raeume, nur Licht und Musik, Rezepte nur lesen). tv_programm liest nur das
# Fernsehprogramm; einschalten (fernsehen) duerfen Gaeste nicht.
GAST_WERKZEUGE = frozenset("""
wetter unwetter geraete_suchen geraet_steuern musik radio rezepte gast_wlan
fussball heute_in_geschichte bahn ferien kurse warten tv_programm
""".split())


def _mit_gaesten(daten, p):
    """Seit 0.6: aktive Gaeste (gaeste.py) mit Rolle "gast" dazu, nur solange sie gelten. Eine Kennung aus
    personen.json wird nie von einem Gast ueberschrieben."""
    if gaeste is None:
        return p
    for g in gaeste.aktive(daten):
        if g["id"] not in p:
            p[g["id"]] = {"name": g["name"], "rolle": "gast", "bis": g["bis"], "raeume": list(g["raeume"])}
    return p


def laden(daten):
    """Gepruefte Personenliste; ohne Datei nur die Hauptperson (plus aktive Gaeste). Ist die Datei da, aber kaputt
    oder ohne Hauptperson: leeres Ergebnis ({}), also niemand mit Rechten, auch kein Gast, bis sie repariert ist."""
    pfad = os.path.join(daten, "personen.json")
    if not os.path.exists(pfad):
        return _mit_gaesten(daten, dict(STANDARD))
    try:
        roh = json.load(open(pfad, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    p = {}
    for k, v in (roh.items() if isinstance(roh, dict) else []):
        if not ID.match(str(k)) or not isinstance(v, dict) or v.get("rolle") not in ROLLEN:
            continue
        name = str(v.get("name") or k.capitalize())[:40]
        e = {"name": re.sub(r"[\x00-\x1f<>]", "", name), "rolle": v["rolle"]}
        for feld in ("kontakt", "paperless_token_datei", "postfach_zugang_datei"):
            if isinstance(v.get(feld), str) and v[feld] and len(v[feld]) < 300:
                e[feld] = v[feld]
        if isinstance(v.get("paperless_id"), int) and v["paperless_id"] > 0:
            e["paperless_id"] = v["paperless_id"]
        p[k] = e
    if not any(e["rolle"] == "haupt" for e in p.values()):
        return {}
    return _mit_gaesten(daten, p)


def haupt(p):
    """Kennung der Hauptperson (die erste mit Rolle haupt); None, wenn es keine gibt (personen.json kaputt)."""
    return next((k for k, e in p.items() if e["rolle"] == "haupt"), None)


def fuer_geraet(p, geraete, besitzer):
    """Person hinter einem Besitzer (Geraete-ID oder "haupt"). Geraet ohne Person: Hauptperson. Geraet mit einer
    Person, die es nicht (mehr) gibt, oder mit einem Gast (Gaeste besitzen keine Geraete): None, nie die Hauptperson."""
    for g in geraete or []:
        if g.get("id") == besitzer and g.get("person"):
            return g["person"] if g["person"] in p and p[g["person"]]["rolle"] != "gast" else None
    return haupt(p)


def name(p, person):
    if not person:
        return ""
    return p.get(person, {}).get("name") or str(person).capitalize()


def ist_haupt(p, person):
    return p.get(person, {}).get("rolle") == "haupt"


def ist_gast(p, person):
    return p.get(person, {}).get("rolle") == "gast"


def darf(p, person, werkzeug):
    e = p.get(person)
    if not e:
        return False
    if e["rolle"] == "haupt":
        return True
    if e["rolle"] == "familie":
        return werkzeug in FAMILIE_WERKZEUGE
    if e["rolle"] == "gast":                # Ablauf hier noch einmal, falls p schon aelter ist
        return e.get("bis", 0) > time.time() and werkzeug in GAST_WERKZEUGE
    return False


def andere(p, person):
    """Die uebrigen Personen (fuer Filter: deren Privates sieht diese Person nie)."""
    return [k for k in p if k != person]
