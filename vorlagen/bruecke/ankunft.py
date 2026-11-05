"""Ankunfts-Nachrichten (seit 0.6): „Sag Mia, wenn sie heimkommt, dass das Essen im Ofen ist“,
„Erinnere mich an den Müll, wenn ich zu Hause bin“, „Gib mir Bescheid, wenn Ben daheim ist“.

Anwesenheit kommt aus den Handy-Trackern in Home Assistant (device_tracker.*, „home“/„not_home“, z. B. aus der
Integration des Routers). Welche Tracker zu wem gehören, steht in daten/anwesenheit.json (nicht im Repo, eigene Geräte):

    {"personen": {"mia": {"name": "Mia", "kontakt": "Mia", "tracker": ["device_tracker.handy_mia"]}, ...},
     "raum": "wohnzimmer", "min_weg_minuten": 30, "verzoegerung_s": 60}

Eine Person ist da, sobald einer ihrer Tracker „home“ meldet, und weg, wenn alle bekannten „not_home“ melden
(„unavailable“/„unknown“ zählen nicht). Als Ankunft zählt nur der Wechsel weg -> da nach mindestens min_weg_minuten:
Handys verlieren das WLAN auch zu Hause für ein paar Minuten (beobachtet: Aussetzer von 3 bis 35 Minuten).
Nach einem Neustart der Brücke zählt der erste Blick nur als Ausgangslage, nie als Ankunft.

Dieses Modul rechnet nur; Lesen von HA, Durchsage und Push macht die Brücke (Funktionen werden übergeben)."""
import json
import os
import time
import uuid

MIN_WEG_MINUTEN = 30
VERZOEGERUNG_S = 60          # der Router sieht das Handy schon in der Einfahrt; erst sprechen, wenn die Person drin ist
GUELTIG_TAGE = 7             # einmalige Aufträge verfallen danach
RAUM = "wohnzimmer"          # Raum der Durchsage, wenn anwesenheit.json keinen nennt (dort braucht es ein Ausgabegerät)
KANAELE = ("auto", "durchsage", "push")


# Sprache der Texte, die die Person direkt sieht oder hört (seit 0.6 im Release). Die Bruecke setzt sie beim Start aus
# der Einrichtung (antworten.json "sprache"), wie bei verhalten.py und szenen.py.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


def _json_laden(pfad, leer):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def _json_speichern(pfad, daten):
    with open(pfad + ".neu", "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
    os.chmod(pfad + ".neu", 0o600)
    os.replace(pfad + ".neu", pfad)


def konfig_laden(pfad):
    """Zuordnung Person -> Tracker. Leer, wenn die Datei fehlt (dann ist die Funktion aus)."""
    k = _json_laden(pfad, {})
    personen = {}
    for schluessel, p in (k.get("personen") or {}).items():
        tracker = [t for t in (p.get("tracker") or []) if str(t).startswith("device_tracker.")]
        if tracker:
            personen[str(schluessel).lower()] = {"name": p.get("name") or schluessel.capitalize(),
                                                 "kontakt": p.get("kontakt") or p.get("name") or schluessel,
                                                 "tracker": tracker}
    return {"personen": personen, "raum": k.get("raum") or RAUM,
            "min_weg_s": int(k.get("min_weg_minuten") or MIN_WEG_MINUTEN) * 60,
            "verzoegerung_s": int(k.get("verzoegerung_s", VERZOEGERUNG_S))}


def person_finden(konfig, wer):
    """Schlüssel der Person zu einem Namen ("Mia", "mia", "Ben") oder None."""
    w = str(wer or "").strip().lower()
    for s, p in konfig["personen"].items():
        if w in (s, p["name"].lower()):
            return s
    return None


def anwesend(tracker, lesen):
    """True: mindestens ein Tracker „home“; False: alle bekannten „not_home“; None: nichts Verwertbares."""
    gesehen = False
    for t in tracker:
        try:
            z = lesen(t)
        except Exception:
            continue
        s = (z.get("state") if isinstance(z, dict) else z) or ""
        if s == "home":
            return True
        if s == "not_home":
            gesehen = True
    return False if gesehen else None


def pruefen(konfig, zustand, lesen, jetzt=None):
    """Zustand je Person fortschreiben (in place) und die Ankünfte dieser Runde liefern (Liste von Schlüsseln)."""
    jetzt = time.time() if jetzt is None else jetzt
    ankuenfte = []
    for s, p in konfig["personen"].items():
        a = anwesend(p["tracker"], lesen)
        if a is None:
            continue
        z = zustand.get(s)
        if z is None:                                   # erster Blick (oder neue Person): nur Ausgangslage
            zustand[s] = {"da": a, "seit": jetzt}
            continue
        if a == z["da"]:
            continue
        weg_dauer = jetzt - z["seit"]
        zustand[s] = {"da": a, "seit": jetzt}
        if a and weg_dauer >= konfig["min_weg_s"]:
            ankuenfte.append(s)
    return ankuenfte


def zustand_laden(pfad):
    """Wer war zuletzt da oder weg, seit wann (überlebt einen Neustart der Brücke)."""
    z = _json_laden(pfad, {})
    return z if isinstance(z, dict) else {}


def zustand_speichern(pfad, zustand):
    _json_speichern(pfad, zustand)


def auftraege_laden(pfad):
    return _json_laden(pfad, [])


def auftraege_speichern(pfad, liste):
    _json_speichern(pfad, liste)


def auftrag_neu(liste, konfig, wer, text, von, fuer="ankommer", kanal="auto", raum="", immer=False, jetzt=None,
                raum_gueltig=None):
    """Neuer Auftrag. wer: wessen Ankunft; von: wer ihn gestellt hat (Personenschlüssel der Brücke);
    fuer: "ankommer" (Nachricht an die ankommende Person) oder "mich" (Bescheid an von). Ergebnis: (liste, meldung)."""
    jetzt = time.time() if jetzt is None else jetzt
    s = person_finden(konfig, wer)
    if not s:
        bekannt = ", ".join(p["name"] for p in konfig["personen"].values()) or _t("noch niemand", "nobody yet")
        return liste, _t("Bei „%s“ sehe ich nicht, wann die Person nach Hause kommt. Ich kenne: %s.",
                         "For “%s” I can't see when the person comes home. I know: %s.") % (wer, bekannt)
    text = " ".join(str(text or "").split())[:400]
    fuer = "mich" if str(fuer).lower() in ("mich", "von", "fragende") else "ankommer"
    if fuer == "ankommer" and not text:
        return liste, _t("Was soll ich %s ausrichten?", "What should I tell %s?") % konfig["personen"][s]["name"]
    kanal = kanal if kanal in KANAELE else "auto"
    raum = str(raum or "").strip().lower()
    if raum and raum_gueltig and not raum_gueltig(raum):
        return liste, _t("Den Raum „%s“ kenne ich nicht.", "I don't know the room “%s”.") % raum
    a = {"id": uuid.uuid4().hex[:8], "wer": s, "text": text, "fuer": fuer, "von": von or "", "kanal": kanal,
         "raum": raum, "immer": bool(immer), "erstellt": int(jetzt),
         "bis": None if immer else int(jetzt + GUELTIG_TAGE * 86400)}
    name = konfig["personen"][s]["name"]
    wann = _t("Jedes Mal, wenn", "Every time") if immer else _t("Wenn", "When")
    if fuer == "mich":
        m = _t("Mach ich. %s %s nach Hause kommt, sage ich dir Bescheid.",
               "Will do. %s %s comes home, I'll let you know.") % (wann, name)
    else:
        m = _t("Mach ich. %s %s nach Hause kommt, richte ich es aus.",
               "Will do. %s %s comes home, I'll pass it on.") % (wann, name)
    return liste + [a], m


def fuer_person(liste, von):
    """Aufträge, die diese Person gestellt hat (nur die eigenen sieht man)."""
    return [a for a in liste if a.get("von", "") == (von or "")]


def beschreiben(a, konfig):
    name = konfig["personen"].get(a["wer"], {}).get("name", a["wer"])
    if a["fuer"] == "mich":
        t = _t("Bescheid, wenn %s heimkommt", "Let you know when %s gets home") % name \
            + (": " + a["text"] if a["text"] else "")
    else:
        t = _t("an %s beim Heimkommen: %s", "to %s on arriving home: %s") % (name, a["text"])
    return t + (_t(" (jedes Mal)", " (every time)") if a.get("immer") else "")


def aufraeumen(liste, jetzt=None):
    jetzt = time.time() if jetzt is None else jetzt
    return [a for a in liste if a.get("immer") or not a.get("bis") or a["bis"] > jetzt or a.get("ausloesen_ab")]


def ankunft_vormerken(liste, person, verzoegerung_s, jetzt=None):
    """Aufträge zu dieser Ankunft auf jetzt + Verzögerung setzen. Liefert die Zahl der vorgemerkten."""
    jetzt = time.time() if jetzt is None else jetzt
    n = 0
    for a in liste:
        if a["wer"] == person and not a.get("ausloesen_ab") and (a.get("immer") or not a.get("bis") or a["bis"] > jetzt):
            a["ausloesen_ab"] = int(jetzt + verzoegerung_s)
            n += 1
    return n


def faellig(liste, jetzt=None):
    jetzt = time.time() if jetzt is None else jetzt
    return [a for a in liste if a.get("ausloesen_ab") and a["ausloesen_ab"] <= jetzt]


def erledigt(liste, a, jetzt=None):
    """Nach dem Zustellen: einmalige raus, wiederkehrende zurücksetzen."""
    jetzt = time.time() if jetzt is None else jetzt
    rest = []
    for x in liste:
        if x.get("id") != a.get("id"):
            rest.append(x)
        elif x.get("immer"):
            x = dict(x)
            x.pop("ausloesen_ab", None)
            x["zuletzt"] = int(jetzt)
            rest.append(x)
    return rest


def zustelltext(a, konfig, name_von):
    """Gesprochener bzw. gepushter Text. name_von: Anzeigename dessen, der den Auftrag gestellt hat."""
    name = konfig["personen"].get(a["wer"], {}).get("name", a["wer"])
    if a["fuer"] == "mich":
        return _t("%s ist gerade nach Hause gekommen.%s", "%s just got home.%s") % (name, (" " + a["text"]) if a["text"] else "")
    if name_von and name_von.lower() != name.lower():
        return _t("Willkommen zu Hause, %s. %s lässt ausrichten: %s",
                  "Welcome home, %s. %s asked me to tell you: %s") % (name, name_von, a["text"])
    return _t("Willkommen zu Hause, %s. Du wolltest daran denken: %s",
              "Welcome home, %s. You wanted to remember: %s") % (name, a["text"])
