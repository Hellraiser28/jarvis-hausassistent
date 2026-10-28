"""Personen hinter den Geraeten (seit 0.4, 28.10.2026): wer fragt, was darf er, wessen Gedaechtnis gilt.

daten/personen.json (600), z. B.
    {"alex": {"name": "Alex", "rolle": "haupt", "paperless_id": 3},
     "sam": {"name": "Sam", "rolle": "familie", "kontakt": "Sam", "paperless_id": 4,
                "paperless_token_datei": "/.../paperless_token_sam"}}

rolle "haupt": alles wie bisher (Admin-Kollege, PC, Postfach, eigene Dokumente und Notizen).
rolle "familie": nur der Haushalt (FAMILIE_WERKZEUGE), eigener Verlauf, eigenes Gedaechtnis plus das gemeinsame,
eigene Erinnerungen auf das eigene Handy. Wer keinem Geraet zugeordnet ist (Hauptschluessel, PC, Home Assistant,
Alexa), ist die Hauptperson; ueber Alexa und die Sprachkette gelten weiter die Einschraenkungen nach Quelle.

Fehler fuehren nie zur Hauptperson: Ist personen.json da, aber nicht lesbar (oder ohne Hauptperson), oder traegt ein
Geraet eine Person, die es nicht gibt, liefert fuer_geraet None. Die Bruecke lehnt die Frage dann ab.
"""
import json
import os
import re

ID = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")
ROLLEN = ("haupt", "familie")
STANDARD = {"ich": {"name": "Hauptperson", "rolle": "haupt"}}   # ohne personen.json

# Was eine Person mit Rolle "familie" darf: Haushalt. Nicht: Admin-Kollege, PC, Postfach, Notizen und Aufgaben der
# Hauptperson, deren Routinen, Nachrichtenquellen, Verhalten und Aussehen von Jarvis, NAS-Zustand, Handy-Suche.
FAMILIE_WERKZEUGE = frozenset("""
termine haus_status wetter unwetter geraete_suchen geraet_steuern saugroboter nachricht hoerspiel morgenradio
nachrichten fussball heute_in_geschichte neu_in_mediathek steam_angebote briefing
merken gedaechtnis frueher vergessen gedaechtnis_datei erinnern erinnerungen vorlesen warten einkaufsliste rezepte
dokumente inventar bahn ferien kurse musik radio internet
pdf_erstellen bild_bearbeiten bild_erzeugen datei_umwandeln umwandeln_moeglich
szenen brief_ablegen fristen
""".split())


def laden(daten):
    """Gepruefte Personenliste; ohne Datei nur die Hauptperson. Ist die Datei da, aber kaputt oder ohne Hauptperson:
    leeres Ergebnis ({}), also niemand mit Rechten, bis sie repariert ist."""
    pfad = os.path.join(daten, "personen.json")
    if not os.path.exists(pfad):
        return dict(STANDARD)
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
        for feld in ("kontakt", "paperless_token_datei"):
            if isinstance(v.get(feld), str) and v[feld] and len(v[feld]) < 300:
                e[feld] = v[feld]
        if isinstance(v.get("paperless_id"), int) and v["paperless_id"] > 0:
            e["paperless_id"] = v["paperless_id"]
        p[k] = e
    if not any(e["rolle"] == "haupt" for e in p.values()):
        return {}
    return p


def haupt(p):
    """Kennung der Hauptperson (die erste mit Rolle haupt); None, wenn es keine gibt (personen.json kaputt)."""
    return next((k for k, e in p.items() if e["rolle"] == "haupt"), None)


def fuer_geraet(p, geraete, besitzer):
    """Person hinter einem Besitzer (Geraete-ID oder "haupt"). Geraet ohne Person: Hauptperson. Geraet mit einer
    Person, die es nicht (mehr) gibt: None, nie die Hauptperson."""
    for g in geraete or []:
        if g.get("id") == besitzer and g.get("person"):
            return g["person"] if g["person"] in p else None
    return haupt(p)


def name(p, person):
    if not person:
        return ""
    return p.get(person, {}).get("name") or str(person).capitalize()


def ist_haupt(p, person):
    return p.get(person, {}).get("rolle") == "haupt"


def darf(p, person, werkzeug):
    e = p.get(person)
    if not e:
        return False
    return e["rolle"] == "haupt" or werkzeug in FAMILIE_WERKZEUGE


def andere(p, person):
    """Die uebrigen Personen (fuer Filter: deren Privates sieht diese Person nie)."""
    return [k for k in p if k != person]
