#!/usr/bin/env python3
"""Raeume, Raumkontext und Durchsagen 2.0 (seit 0.5.2, 29.10.2026; im Release seit 0.6). Reine Logik, Python 3.8,
ohne Zusatzpakete.

daten/raeume.json ordnet Geraete Raeumen zu und sagt, ueber welche Lautsprecher ein Raum erreichbar ist:

  {"version": 1,
   "raeume": {"kueche": {"name": "Küche", "alias": ["küche"], "bereich": "Küche",
                         "ausgabe": [{"art": "echo", "notify": "notify.alexa_media_kuche"}]}},
   "geraete": {"Küche": "kueche", "assist_satellite.beispiel": "wohnzimmer"},
   "ueberall": {"ausgabe": [...]},
   "einstellungen": {"gong": true, "lautstaerke_ansage": 70}}

Ausgabearten (je Eintrag in "ausgabe"; optional "geraet": Name des Geraets, das hier fragt - dann geht die Antwort
bevorzugt dorthin):
  echo      notify (notify.alexa_media_*), optional target       Alexa Media Player, Typ announce (mit Alexas eigenem
                                                                 Ankuendigungston) oder tts (ohne Gong)
  ma        entity (Music-Assistant-Player), optional fallback   music_assistant.play_announcement: Gong
                                                                 (use_pre_announce) und Ansagelautstaerke; Musik wird
                                                                 laut Music-Assistant-Doku fuer die Ansage abgesenkt
  satellit  entity (assist_satellite.*)                          assist_satellite.announce mit preannounce
  player    entity (sonstiger media_player.*, z. B. Cast)        media_player.play_media mit announce
  einblendung notify (notify.*)                                  Texteinblendung statt Ton (z. B. als Ersatz)

Neuer Sprach-Satellit (z. B. Home Assistant Voice PE): ein Eintrag unter "geraete" (Name des Geraets in HA -> Raum),
fertig. Wer kein Eintrag hat, wird ueber den HA-Bereich erkannt, den die Brueckenanbindung mitschickt, oder ueber einen
Geraetenamen, der einem Raumnamen entspricht (so wie ein Echo, der in Alexa „Küche“ heisst).

Flags je Ausgabe (seit 30.10.2026):
  voice_pe          gehoert zum Voice PE: zaehlt erst, wenn einstellungen.voice_pe_aktiv true ist
  bis_voice_pe      faellt bei "ueberall" weg, sobald voice_pe_aktiv true ist (z. B. ein Verstaerker, der bis dahin aushilft)
  nur_wenn_an       true (eigene Entitaet) oder eine media_player-Kennung: nur wenn dieses Geraet an ist (nicht off,
                    unavailable, unknown, standby); nicht pruefbar heisst: nicht benutzen
  lautstaerke_fest  ma ohne announce_volume: die Ansage kommt in der gerade eingestellten Lautstaerke
  ersatz            nur, wenn in diesem Plan sonst nichts zustande kam (z. B. Texteinblendung)
  platzhalter       vorbereitet, nie benutzt (einblendung ohne Benachrichtigungs-App)
Zusaetzlich: "zuruf": {"verstaerker": {"name", "alias", "ausgabe"}} sind Ziele, die nur auf ausdruecklichen Wunsch
gelten („sag es ueber den Verstaerker“), nie ein Raum und nie Teil von "ueberall" (ausser per Flag in der ueberall-Liste).
Raum-Schluessel "hinweis_ohne_ausgabe": ehrlicher Satz, wenn der Raum keine nutzbare Ausgabe hat.

Nichts hier ruft Home Assistant auf: plan() baut nur die Aufrufliste, ausfuehren() setzt sie ab.
Babyfon und Kameras sind tabu (TABU): solche Kennungen lehnt pruefen() ab.
Sprache (seit 0.6 im Release): Meldungen, Hinweise und der Kontextsatz fuers Gehirn auf Deutsch oder Englisch
(setze_sprache(), wie szenen.py). Raumnamen und Aliasse stehen in der Datei und bleiben, wie sie dort stehen.
"""
import json
import os
import re

TABU = re.compile(r"(avent|baby|camera\.|chuangmi)", re.I)
ARTEN = ("echo", "ma", "satellit", "player", "einblendung")
UEBERALL_WORTE = ("ueberall", "alle raeume", "ganzen haus", "im haus", "alle")
TON_PLATZHALTER = "http://<bruecke>:8770/ton/<wird-beim-Senden-erzeugt>.mp3"
# Quellen, bei denen der Raum aus Geraetename oder HA-Bereich abgeleitet werden darf: Echos und Sprach-Satelliten stehen
# fest in einem Raum. App, PC und Web-App wandern mit der Person, dort zaehlt nur ein ausdruecklicher Eintrag.
RAUM_QUELLEN = ("alexa", "ha", "test-alexa", "test-ha")

# Sprache der Texte, die die Person sieht oder hoert (Absagen, Hinweise), und des Kontextsatzes fuers Gehirn.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


class Ungueltig(Exception):
    pass


def norm(s):
    s = str(s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _entity(wert, praefix, was):
    if not isinstance(wert, str) or not re.fullmatch(r"%s\.[a-z0-9_]+" % praefix, wert):
        raise Ungueltig(_t("%s: %r ist keine Kennung %s.*", "%s: %r is not an id %s.*") % (was, wert, praefix))
    if TABU.search(wert):
        raise Ungueltig(_t("%s: Babyfon und Kameras sind tabu (%s)", "%s: baby monitors and cameras are off limits (%s)")
                        % (was, wert))
    return wert


def _ausgabe_pruefen(a, wo):
    if not isinstance(a, dict) or a.get("art") not in ARTEN:
        raise Ungueltig(_t("%s: art muss eine von %s sein", "%s: art must be one of %s") % (wo, ", ".join(ARTEN)))
    art, e = a["art"], {"art": a["art"]}
    if art == "echo":
        e["notify"] = _entity(a.get("notify"), "notify", wo)
        if a.get("target") is not None:
            e["target"] = _entity(a["target"], "media_player", wo)
    elif art == "satellit":
        e["entity"] = _entity(a.get("entity"), "assist_satellite", wo)
    elif art == "einblendung":
        e["notify"] = _entity(a.get("notify"), "notify", wo)
    else:
        e["entity"] = _entity(a.get("entity"), "media_player", wo)
        if art == "ma" and a.get("fallback") is not None:
            e["fallback"] = _entity(a["fallback"], "media_player", wo)
    if a.get("geraet") is not None:
        e["geraet"] = str(a["geraet"])[:80]
    for flag in ("platzhalter", "voice_pe", "bis_voice_pe", "lautstaerke_fest", "ersatz"):
        if a.get(flag):
            e[flag] = True
    w = a.get("nur_wenn_an")
    if w is True:
        e["nur_wenn_an"] = True
    elif w:
        e["nur_wenn_an"] = _entity(w, "media_player", wo)
    return e


def pruefen(d):
    """Datei pruefen und in eine feste Form bringen; Ungueltig mit klarem Satz bei Fehlern."""
    if not isinstance(d, dict) or not isinstance(d.get("raeume"), dict) or not d["raeume"]:
        raise Ungueltig(_t("raeume.json braucht einen Block \"raeume\"", "raeume.json needs a block \"raeume\""))
    k = {"raeume": {}, "geraete": {}, "ueberall": [],
         "zuruf": {},
         "einstellungen": {"gong": True, "lautstaerke_ansage": None, "ausblenden": ["internetzugang"], "voice_pe_aktiv": False}}
    for slug, r in d["raeume"].items():
        if not re.fullmatch(r"[a-z0-9_]+", str(slug)) or slug in ("ueberall", "hier"):
            raise Ungueltig(_t("Raumschluessel %r: nur a-z, 0-9, _ (nicht ueberall/hier)",
                               "Room key %r: only a-z, 0-9, _ (not ueberall/hier)") % slug)
        if not isinstance(r, dict) or not str(r.get("name") or "").strip():
            raise Ungueltig(_t("Raum %s braucht einen name", "Room %s needs a name") % slug)
        alias = [norm(x) for x in [r["name"], slug] + list(r.get("alias") or []) if norm(x)]
        k["raeume"][slug] = {
            "name": str(r["name"]).strip()[:60], "alias": sorted(set(alias), key=lambda x: (-len(x), x)),
            "bereich": str(r.get("bereich") or "")[:60], "hinweis_ohne_ausgabe": str(r.get("hinweis_ohne_ausgabe") or "")[:300],
            "ausgabe": [_ausgabe_pruefen(a, _t("Raum %s", "Room %s") % slug) for a in (r.get("ausgabe") or [])]}
    for name, slug in (d.get("geraete") or {}).items():
        if slug not in k["raeume"]:
            raise Ungueltig(_t("Geraet %r zeigt auf unbekannten Raum %r", "Device %r points to unknown room %r") % (name, slug))
        k["geraete"][str(name)[:80]] = slug
    u = (d.get("ueberall") or {}).get("ausgabe")
    if u is not None:
        k["ueberall"] = [_ausgabe_pruefen(a, "ueberall") for a in u]
    else:      # Standard: alle Ausgaben aller Raeume, ohne Doppelte
        gesehen = []
        for r in k["raeume"].values():
            for a in r["ausgabe"]:
                if not any(_gleich(a, b) for b in gesehen):
                    gesehen.append(a)
        k["ueberall"] = gesehen
    for name, z in (d.get("zuruf") or {}).items():
        if not re.fullmatch(r"[a-z0-9_]+", str(name)) or not isinstance(z, dict) or not str(z.get("name") or "").strip():
            raise Ungueltig(_t("zuruf %r: Schluessel a-z0-9_ und ein name noetig", "zuruf %r: key a-z0-9_ and a name needed")
                            % name)
        k["zuruf"][name] = {"name": str(z["name"]).strip()[:60],
                            "alias": sorted(set(norm(x) for x in [z["name"], name] + list(z.get("alias") or []) if norm(x)),
                                            key=lambda x: (-len(x), x)),
                            "ausgabe": _ausgabe_pruefen(z.get("ausgabe"), "zuruf %s" % name)}
    s = d.get("einstellungen") or {}
    if "voice_pe_aktiv" in s:
        k["einstellungen"]["voice_pe_aktiv"] = bool(s["voice_pe_aktiv"])
    if "gong" in s:
        k["einstellungen"]["gong"] = bool(s["gong"])
    if s.get("lautstaerke_ansage") is not None:
        k["einstellungen"]["lautstaerke_ansage"] = _lautstaerke(s["lautstaerke_ansage"])
    if s.get("ausblenden") is not None:
        if not isinstance(s["ausblenden"], list) or not all(isinstance(x, str) for x in s["ausblenden"]):
            raise Ungueltig(_t("einstellungen.ausblenden muss eine Liste von Textstuecken sein",
                               "einstellungen.ausblenden must be a list of text pieces"))
        k["einstellungen"]["ausblenden"] = [x.lower() for x in s["ausblenden"] if x][:40]
    return k


def _lautstaerke(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise Ungueltig(_t("Lautstaerke %r ist keine Zahl", "Volume %r is not a number") % (v,))
    if not 1 <= n <= 100:
        raise Ungueltig(_t("Lautstaerke %d: erlaubt sind 1 bis 100", "Volume %d: 1 to 100 allowed") % n)
    return n


def _gleich(a, b):
    return a["art"] == b["art"] and a.get("entity") == b.get("entity") and a.get("notify") == b.get("notify") \
        and a.get("target") == b.get("target")


def laden(daten):
    """Konfiguration aus <daten>/raeume.json, oder None, wenn es sie nicht gibt oder sie nicht stimmt (dann bleibt
    alles beim bisherigen Verhalten). Zweiter Rueckgabewert: Fehlertext oder None."""
    pfad = os.path.join(daten, "raeume.json")
    try:
        roh = json.load(open(pfad, encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as e:
        return None, _t("raeume.json nicht lesbar (%s)", "raeume.json not readable (%s)") % type(e).__name__
    try:
        return pruefen(roh), None
    except Ungueltig as e:
        return None, str(e)


# ---------------------------------------------------------------- Raum erkennen

def raum_finden(k, text):
    """Raumschluessel, "ueberall" oder None aus einem freien Text (Raumname, Alias, "überall")."""
    t = " %s " % norm(text)
    if not t.strip():
        return None
    for name, z in k["zuruf"].items():
        if any(" %s " % a in t for a in z["alias"]):
            return "zuruf:" + name
    treffer = [(len(a), slug) for slug, r in k["raeume"].items() for a in r["alias"] if " %s " % a in t]
    if treffer:
        return max(treffer)[1]
    if any(" %s " % w in t for w in UEBERALL_WORTE):
        return "ueberall"
    return None


def raum_von_geraet(k, quelle, geraet, hinweis=None):
    """In welchem Raum wurde gefragt? Reihenfolge: ausdruecklicher Eintrag unter "geraete" (gewinnt immer), dann nur bei
    Echo und Sprach-Satellit: HA-Bereich des Geraets (hinweis), dann ein Geraetename, der einem Raumnamen entspricht.
    Unbekannt heisst None: nie raten."""
    g = str(geraet or "")
    if g in k["geraete"]:
        return k["geraete"][g]
    n = norm(g)
    for name, slug in k["geraete"].items():
        if norm(name) == n and n:
            return slug
    if quelle not in RAUM_QUELLEN:
        return None
    for versuch in (hinweis, g):
        n = norm(versuch)
        if n:
            for slug, r in k["raeume"].items():
                if n in r["alias"] or n == norm(r["bereich"]):
                    return slug
    return None


def kontext(k, slug):
    """Satz fuer das Gehirn (steht im Kontext jeder Frage), oder leer. Der Raumname steht ausdruecklich drin, weil warme
    Gehirn-Prozesse nicht je Geraet laufen: das Gehirn gibt ihn den Werkzeugen selbst mit."""
    if not k or slug not in k.get("raeume", {}):
        return ""
    r = k["raeume"][slug]
    if SPRACHE == "en":
        return (" Asked in the room: %s. “Here”, “in this room” and questions without a place (“Turn the light on”, “How "
                "warm is it?”) mean this room%s. With raum_geraete (raum = %s) you see what Home Assistant has there, and "
                "you pass the room to tools explicitly. The answer comes out on the device in this room; an announcement "
                "into the same room goes to nachricht with an = %s." % (
                    r["name"], (" (HA area “%s”)" % r["bereich"]) if r["bereich"] else "", r["name"], r["name"]))
    return (" Gefragt im Raum: %s. „Hier“, „in diesem Raum“ und Fragen ohne Ortsangabe („Mach das Licht an“, „Wie warm ist "
            "es?“) meinen diesen Raum%s. Mit raum_geraete (raum = %s) siehst du, was dort in Home Assistant steht, und gibst "
            "den Raum Werkzeugen ausdrücklich mit. Die Antwort kommt auf dem Gerät in diesem Raum; eine Durchsage in "
            "denselben Raum gehört mit an = %s an nachricht." % (r["name"], (" (HA-Bereich „%s“)" % r["bereich"]) if r["bereich"] else "",
                                                                   r["name"], r["name"]))


def ziel_gueltig(k, ziel):
    return bool(k) and (ziel in k["raeume"] or ziel == "ueberall" or (str(ziel).startswith("zuruf:") and ziel[6:] in k["zuruf"]))


def raum_name(k, slug):
    if slug == "ueberall":
        return _t("überall", "everywhere")
    if str(slug).startswith("zuruf:") and k and slug[6:] in k["zuruf"]:
        return k["zuruf"][slug[6:]]["name"]
    return k["raeume"][slug]["name"] if k and slug in k["raeume"] else slug


# ---------------------------------------------------------------- Durchsage planen

def _auswahl(k, slug, bevorzugt):
    if slug == "ueberall":
        return list(k["ueberall"])
    if slug.startswith("zuruf:"):
        return [k["zuruf"][slug[6:]]["ausgabe"]]
    ausgabe = k["raeume"][slug]["ausgabe"]
    if bevorzugt:
        eigene = [a for a in ausgabe if a.get("geraet") == bevorzugt]
        if eigene:
            return eigene
    return ausgabe


def text_sauber(t):
    """Durchsagetext wie anruf.text_sauber: keine Steuerzeichen und keine Vorlagen-Klammern, denn Home Assistant rendert
    Vorlagen ({{ }}, {% %}) und Alexa liest Auszeichnungen (<...>). Das Prozentzeichen wird zum Wort, damit
    "Akku bei 20 %" verstaendlich bleibt."""
    t = str(t or "").replace("%", _t(" Prozent ", " percent "))
    t = re.sub(r"[\x00-\x1f\x7f{}<>]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def plan(k, ziel, text, gong=None, lautstaerke=None, ruhe=None, zustand=None, ton_url=None, bevorzugt=None, medien=False):
    """Aufrufliste fuer eine Durchsage, ohne etwas auszufuehren.

    ziel: Raumschluessel oder "ueberall". ruhe: (aktiv, bis_stunde) aus der Nachtruhe, aktiv sperrt alles. zustand:
    Funktion entity_id -> HA-Zustand (nur Lesen), fuer den Ausweichplayer. ton_url: Funktion -> Adresse von Jarvis'
    Stimme (nur wenn ein Player sie braucht); ohne sie steht ein Platzhalter im Plan (Trockenlauf).
    bevorzugt: Name des fragenden Geraets, dessen Ausgabe zuerst zaehlt (Antwortweg).
    medien (seit 01.11.2026, Quizshow): auch Satelliten spielen die fertige Datei aus ton_url ab (assist_satellite.announce
    mit media_id, laut HA-Quelltext direkt als URL) statt den Text mit ihrer eigenen Stimme zu sprechen.
    Ergebnis: {"ziel", "aufrufe": [{"dienst", "daten", "hinweis"}], "hinweise": [...], "abgelehnt": None | Text}.
    Der Text geht bereinigt (text_sauber) in alle Aufrufe und ins Ergebnis."""
    text = text_sauber(text)
    erg = {"ziel": ziel, "text": text, "aufrufe": [], "hinweise": [], "abgelehnt": None}
    if not text:
        erg["abgelehnt"] = _t("Kein Text für die Durchsage.", "No text for the announcement.")
        return erg
    if ruhe and ruhe[0]:
        erg["abgelehnt"] = _t("Nachtruhe bis %d Uhr: Durchsagen sind aus. Als Push schicken oder die Nachtruhe abschalten "
                              "(Werkzeug verhalten), wenn es dringend ist.",
                              "Quiet hours until %d o'clock: announcements are off. Send it as a push or switch quiet "
                              "hours off (tool verhalten) if it is urgent.") % ruhe[1]
        return erg
    if ziel != "ueberall" and ziel not in k["raeume"] and not (ziel.startswith("zuruf:") and ziel[6:] in k["zuruf"]):
        erg["abgelehnt"] = _t("Unbekannter Raum %r. Räume: %s.", "Unknown room %r. Rooms: %s.") % (
            ziel, ", ".join(sorted(k["raeume"])) + ", ueberall")
        return erg
    if gong is None:
        gong = k["einstellungen"]["gong"]
    if lautstaerke is None:
        lautstaerke = k["einstellungen"]["lautstaerke_ansage"]
    elif lautstaerke is not False:
        try:
            lautstaerke = _lautstaerke(lautstaerke)
        except Ungueltig as e:
            erg["abgelehnt"] = _t("Ansagelautstärke ungültig: %s", "Announcement volume invalid: %s") % e
            return erg
    if lautstaerke is False:
        lautstaerke = None
    alle = _auswahl(k, ziel, bevorzugt)
    pe = k["einstellungen"]["voice_pe_aktiv"]
    ausgaben = []
    for a in alle:
        ziel_e = a.get("entity") or a.get("notify")
        if a.get("platzhalter"):
            erg["hinweise"].append(_t("%s ist nur vorbereitet (Platzhalter), nicht benutzt",
                                      "%s is only prepared (placeholder), not used") % ziel_e)
        elif a.get("voice_pe") and not pe:
            erg["hinweise"].append(_t("Voice PE (%s) noch nicht eingerichtet (voice_pe_aktiv aus): nicht benutzt",
                                      "Voice PE (%s) not set up yet (voice_pe_aktiv off): not used") % ziel_e)
        elif a.get("bis_voice_pe") and pe and ziel == "ueberall":
            erg["hinweise"].append(_t("%s gehört seit dem Voice PE nicht mehr zu überall",
                                      "%s is no longer part of everywhere since the Voice PE") % ziel_e)
        else:
            ausgaben.append(a)
    if not ausgaben:
        erg["abgelehnt"] = _ohne_ausgabe(k, ziel, erg)
        return erg
    url = [None]

    def adresse():
        if url[0] is None:
            url[0] = ton_url() if ton_url else TON_PLATZHALTER
        return url[0]

    for a in ausgaben:
        art = a["art"]
        if a.get("ersatz") and erg["aufrufe"]:
            continue
        w = a.get("nur_wenn_an")
        if w:
            pr = w if isinstance(w, str) else a.get("entity")
            if not zustand or not _an(zustand, pr):
                erg["hinweise"].append(_t("%s ist nicht an (oder nicht prüfbar): nicht benutzt",
                                          "%s is not on (or cannot be checked): not used") % pr)
                continue
        if art == "einblendung":
            erg["aufrufe"].append({"dienst": a["notify"].replace(".", "/"), "daten": {"title": "Jarvis", "message": text},
                                   "hinweis": _t("Texteinblendung statt Ton", "Text overlay instead of sound")})
        elif art == "echo":
            body = {"message": text, "data": {"type": "announce" if gong else "tts"}}
            if a.get("target"):
                body["target"] = [a["target"]]
            erg["aufrufe"].append({"dienst": a["notify"].replace(".", "/"), "daten": body, "hinweis": (
                _t("Alexa spielt bei announce ihren eigenen Ankündigungston, Musik senkt Alexa selbst ab (nach Amazons "
                   "Verhalten, hier nicht gemessen)",
                   "With announce Alexa plays its own chime and lowers music itself (Amazon's behaviour, not measured "
                   "here)") if gong else _t("ohne Ankündigungston (tts)", "without chime (tts)"))})
        elif art == "ma":
            ziel_e = a["entity"]
            if zustand and a.get("fallback") and _weg(zustand, ziel_e):
                erg["hinweise"].append(_t("%s nicht verfügbar, Ausweichplayer %s (spielt ohne Gong, Musik bleibt danach aus)",
                                          "%s unavailable, fallback player %s (plays without chime, music stays off "
                                          "afterwards)") % (ziel_e, a["fallback"]))
                erg["aufrufe"].append({"dienst": "media_player/play_media", "daten": {
                    "entity_id": a["fallback"], "media_content_id": adresse(), "media_content_type": "music"},
                    "hinweis": _t("Ausweichweg über den Ausweichplayer", "Fallback via the fallback player")})
                continue
            if zustand and _weg(zustand, ziel_e):
                erg["hinweise"].append(_t("%s nicht verfügbar, kein Ausweichplayer eingetragen: übersprungen",
                                          "%s unavailable, no fallback player configured: skipped") % ziel_e)
                continue
            d = {"entity_id": ziel_e, "url": adresse(), "use_pre_announce": bool(gong)}
            an_aus = _t("an", "on") if gong else _t("aus", "off")
            if a.get("lautstaerke_fest"):
                erg["aufrufe"].append({"dienst": "music_assistant/play_announcement", "daten": d, "hinweis": _t(
                    "Gong %s; kein announce_volume: Ansage in der gerade eingestellten Lautstärke, nichts wird angehoben "
                    "(ob Music Assistant laufende Musik selbst absenkt, steuert dieser Aufruf nicht)",
                    "Chime %s; no announce_volume: announcement at the volume currently set, nothing is raised (whether "
                    "Music Assistant lowers running music itself is not controlled by this call)") % an_aus})
                continue
            if lautstaerke:
                d["announce_volume"] = lautstaerke
            erg["aufrufe"].append({"dienst": "music_assistant/play_announcement", "daten": d,
                                   "hinweis": _t("Gong %s; laufende Musik wird für die Ansage abgesenkt und läuft danach weiter "
                                                 "(laut Music-Assistant-Doku, nicht live erprobt)",
                                                 "Chime %s; running music is lowered for the announcement and continues "
                                                 "afterwards (per Music Assistant docs, not tried live)") % an_aus})
        elif art in ("satellit", "player") and zustand and _weg(zustand, a["entity"]):
            erg["hinweise"].append(_t("%s nicht verfügbar: übersprungen", "%s unavailable: skipped") % a["entity"])
        elif art == "satellit" and medien:
            erg["aufrufe"].append({"dienst": "assist_satellite/announce", "daten": {
                "entity_id": a["entity"], "message": text, "media_id": adresse(), "preannounce": bool(gong)},
                "hinweis": _t("Satellit spielt die fertige Ansage ab; Lautstärke regelt der Satellit",
                              "Satellite plays the finished announcement; the satellite controls the volume")})
        elif art == "satellit":
            erg["aufrufe"].append({"dienst": "assist_satellite/announce", "daten": {
                "entity_id": a["entity"], "message": text, "preannounce": bool(gong)},
                "hinweis": _t("Satellit spricht mit seiner eigenen Stimme; Lautstärke und Absenkung regelt der Satellit",
                              "Satellite speaks with its own voice; the satellite controls volume and ducking")})
        else:
            erg["aufrufe"].append({"dienst": "media_player/play_media", "daten": {
                "entity_id": a["entity"], "media_content_id": adresse(), "media_content_type": "music", "announce": True},
                "hinweis": _t("Ansage über den Player; ob dort Musik abgesenkt wird, hängt vom Gerät ab",
                              "Announcement via the player; whether music is lowered there depends on the device")})
    if not erg["aufrufe"]:
        erg["abgelehnt"] = _ohne_ausgabe(k, ziel, erg)
    return erg


def _ohne_ausgabe(k, ziel, erg):
    """Ehrlicher Satz, wenn nichts zum Sprechen uebrig ist (Raum ohne Ausgabe, Voice PE fehlt, Geraet aus)."""
    if ziel in k["raeume"] and k["raeume"][ziel]["hinweis_ohne_ausgabe"]:
        return k["raeume"][ziel]["hinweis_ohne_ausgabe"]
    return _t("Für %s ist gerade kein Lautsprecher erreichbar. %s", "No speaker is reachable for %s right now. %s") % (
        raum_name(k, ziel), "; ".join(erg["hinweise"]))


def _an(zustand, entity):
    try:
        z = zustand(entity)
        z = z.get("state") if isinstance(z, dict) else z
    except Exception:
        return False
    return z not in ("off", "unavailable", "unknown", "standby", None)


def _weg(zustand, entity):
    try:
        z = zustand(entity)
        z = z.get("state") if isinstance(z, dict) else z
    except Exception:
        return False        # nicht pruefbar: versuchen (wie bisher)
    return z in ("unavailable", "unknown", None)


def ausfuehren(p, ha):
    """Aufrufe eines Plans absetzen. ha(pfad, daten) schickt einen POST. Gibt (geklappt, fehlgeschlagen) zurueck."""
    ok, fehl = 0, []
    for a in p["aufrufe"]:
        try:
            ha("/api/services/" + a["dienst"], a["daten"])
            ok += 1
        except Exception as e:
            fehl.append("%s (%s)" % (a["dienst"], type(e).__name__))
    return ok, fehl


def beschreiben(p):
    """Plan als lesbarer Text (Trockenlauf, Protokoll). Nie ein Geheimnis darin: nur Dienste und Daten."""
    if p["abgelehnt"]:
        return _t("Abgelehnt: %s", "Refused: %s") % p["abgelehnt"]
    zeilen = ["%s %s" % (a["dienst"], json.dumps(a["daten"], ensure_ascii=False)) for a in p["aufrufe"]]
    return "; ".join(zeilen) + ("  [%s]" % "; ".join(p["hinweise"]) if p["hinweise"] else "")
