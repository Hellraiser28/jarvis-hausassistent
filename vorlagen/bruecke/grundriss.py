"""Grundriss und 3D-Haus fuer HUD, App und Web-App (seit 0.6): Daten laden, Live-Zustaende zuschneiden, Geraete
steuern und umstellen. Python 3.8 ohne Zusatzpakete; die Bruecke (/v1/grundriss, /v1/grundriss/bild/<name>,
/v1/grundriss/steuern) und das Werkzeug `grundriss` nutzen es.

Dateien in daten/ (alle optional, von Hand oder mit einem eigenen Skript anlegbar; Muster fuer das 3D-Haus:
vorlagen/grundriss/beispielhaus_erzeugen.py):
  grundriss-foto/haus3d.json  3D-Haus fuer vorlagen/grundriss/haus3d.js: Etagen -> Raeume (Polygone in Metern),
                              Oeffnungen, Treppen, Moebel, Geraete (haus3d_laden)
  grundriss-foto/foto.json    Bildansicht: Puppenhaus je Etage oder Foto-Ebenen, optional "projektion" (foto_laden)
  grundriss.json              2D-Plan aus Saugroboter-Karten: Etagen -> Raeume (Polygone in Metern), HA-Bereich -> Raum
  platzierung.json            entity_id -> {name, symbol, etage, raum, x, y, werte, auto}; "auto": false = von Hand, bleibt

Was hinausgeht, ist bewusst knapp: nur Entitaeten aus dem Plan (und deren werte), je Zustand, Einheit und ein paar
Kennzahlen. Babyfon und Kameras nie, auch wenn jemand sie von Hand eintraegt (TABU).
Sprache der Meldungen: setze_sprache() wie bei szenen.py. Kennungen des Saugroboters: setze_sauger().
"""
import hashlib
import json
import math
import os
import re
import threading
import time

TABU = re.compile(r"(avent|baby|kamera|camera|chuangmi)", re.I)       # Babyfon-Integrationen und Kameras
SYMBOLE = ("sauger", "klima", "heizung", "warmwasser", "licht", "ventilator", "rollo", "tv", "lautsprecher",
           "verstaerker", "ofen", "geschirr", "waesche", "drucker", "server", "router", "zaehler", "steckdose",
           "thermometer", "sensor", "pc")
# Attribute, die die Ansicht zeigt (alles andere bleibt in HA)
ATTRIBUTE = {"climate": ("current_temperature", "temperature", "hvac_action", "hvac_modes", "min_temp", "max_temp",
                         "target_temp_step", "fan_mode", "fan_modes"),
             "water_heater": ("current_temperature", "temperature", "min_temp", "max_temp"),
             "vacuum": ("battery_level", "fan_speed", "status"),
             "light": ("brightness",),
             "media_player": ("source", "app_name", "volume_level", "is_volume_muted", "source_list", "media_title",
                              "media_artist", "supported_features")}
LISTEN = ("hvac_modes", "fan_modes", "source_list")         # fuers Geraete-Menue: Auswahllisten

# Geraete-Menue im 3D-Haus (seit 0.6): ein angetipptes Geraet zeigt ein Menue mit moeglichst allen Funktionen.
# Nur diese Dienste, nur diese Felder; alles andere lehnt die Bruecke ab, bevor der Werkzeug-Server gefragt wird. Der prueft
# danach noch einmal Person, Gast-Raeume, Tabu (Babyfon, Kameras) und NIE_AUS (Steckdosen, die nie ausgehen).
STEUERN = {
    "media_player": {"turn_on": {}, "turn_off": {}, "media_play_pause": {}, "media_play": {}, "media_pause": {},
                     "media_stop": {}, "media_next_track": {}, "media_previous_track": {}, "volume_up": {},
                     "volume_down": {}, "volume_set": {"volume_level": (0, 1)}, "volume_mute": {"is_volume_muted": bool},
                     "select_source": {"source": str}},
    "switch": {"turn_on": {}, "turn_off": {}},
    "light": {"turn_on": {"brightness_pct": (1, 100)}, "turn_off": {}},
    "vacuum": {"start": {}, "pause": {}, "stop": {}, "return_to_base": {}, "locate": {}},
    "climate": {"turn_on": {}, "turn_off": {}, "set_temperature": {"temperature": (5, 32)},
                "set_hvac_mode": {"hvac_mode": str}, "set_fan_mode": {"fan_mode": str}},
    "water_heater": {"set_temperature": {"temperature": (40, 60)}},
}
# Saugroboter fuer die Position im Haus: das vacuum, dazu (Roborock-Integration) ein Sensor mit dem aktuellen Raum und die
# Auswahl der gewaehlten Karte. Die Kennungen haengen vom Geraetenamen und der HA-Sprache ab, also in HA nachsehen; die
# Bruecke setzt sie beim Start aus der Einrichtung (setze_sauger). Ohne Saugroboter finden die Vorgaben einfach nichts.
SAUGER = "vacuum.saugroboter"
SAUGER_RAUM = "sensor.saugroboter_aktueller_raum"
SAUGER_KARTE = "select.saugroboter_ausgewahlte_karte"
LAGE_WORTE = {      # Position im Raum: Anteil der Breite/Tiefe vom Mittelpunkt zum Rand (x rechts, y unten im Plan)
    "links": (-1, 0), "rechts": (1, 0), "oben": (0, -1), "hinten": (0, -1), "unten": (0, 1), "vorne": (0, 1),
    "mitte": (0, 0), "mittig": (0, 0), "linksoben": (-1, -1), "rechtsoben": (1, -1), "linksunten": (-1, 1),
    "rechtsunten": (1, 1), "linkshinten": (-1, -1), "rechtshinten": (1, -1), "linksvorne": (-1, 1), "rechtsvorne": (1, 1),
}

_sperre = threading.Lock()
_cache = {"pfad": None, "stand": None, "daten": None}

# Sprache der Texte, die die Person direkt sieht (Meldungen des Geraete-Menues, Antworten des Werkzeugs). Die Bruecke
# setzt sie beim Start aus der Einrichtung (antworten.json "sprache"), wie bei szenen.py.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


def setze_sauger(vacuum=None, raum=None, karte=None):
    """Kennungen des Saugroboters setzen (vacuum.*, sensor.* aktueller Raum, select.* gewaehlte Karte); None laesst den
    bisherigen Wert. Ungueltige Kennungen -> ValueError, dann bleibt alles wie es war."""
    global SAUGER, SAUGER_RAUM, SAUGER_KARTE
    for dom, e in (("vacuum", vacuum), ("sensor", raum), ("select", karte)):
        if e is not None and not (isinstance(e, str) and ENTITAET.fullmatch(e) and e.startswith(dom + ".")):
            raise ValueError("ungueltige Kennung fuer %s: %r" % (dom, e))
    SAUGER, SAUGER_RAUM, SAUGER_KARTE = vacuum or SAUGER, raum or SAUGER_RAUM, karte or SAUGER_KARTE


def _norm(s):
    s = str(s or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]", "", s)


def laden(daten_ordner):
    """-> (grundriss, platzierung) oder (None, None); neu gelesen, sobald sich eine Datei aendert."""
    g, p = os.path.join(daten_ordner, "grundriss.json"), os.path.join(daten_ordner, "platzierung.json")
    try:
        stand = (os.path.getmtime(g), os.path.getmtime(p))
    except OSError:
        return None, None
    with _sperre:
        if _cache["pfad"] != daten_ordner or _cache["stand"] != stand:
            try:
                _cache["daten"] = (json.load(open(g, encoding="utf-8")), json.load(open(p, encoding="utf-8")))
            except (OSError, ValueError):
                return None, None
            _cache["pfad"], _cache["stand"] = daten_ordner, stand
        return _cache["daten"]


BILD_NAME = re.compile(r"^(eg|og|kg|dg|k\d)_[a-z0-9_]{1,30}\.(jpg|png|webp)$")
# Seit 0.6: Titelbild eines Medien-Players als Standbild auf Beamer und Fernseher im 3D-Haus, wenn sie laufen.
# Der Name passt ins Muster oben (App, Web-App und PC-Client pruefen dasselbe), die Bruecke kennt die Zuordnung
# Name -> (Entitaet, entity_picture) nur fuer Player, die die Ansicht zeigt. Plex-Pfade holt sie beim Plex-Server,
# alles andere ueber HAs Bild-Proxy; nie eine fremde Adresse aus dem Attribut.
LIVE_NAME = re.compile(r"^eg_live_([0-9a-f]{12})\.jpg$")
PLEX_PFAD = re.compile(r"^/library/metadata/\d+/(thumb|art)/\d+$")
TITELBILDER = {}                                           # Hash -> (Entitaet, entity_picture)


def titelbild_name(entity_id, bild):
    """Name fuer das Titelbild eines Players (wechselt mit dem Bild) und Zuordnung merken."""
    h = hashlib.sha1((entity_id + "\x00" + bild).encode("utf-8", "replace")).hexdigest()[:12]
    TITELBILDER[h] = (entity_id, bild)
    while len(TITELBILDER) > 40:
        TITELBILDER.pop(next(iter(TITELBILDER)))
    return "eg_live_%s.jpg" % h


# Seit 0.6: Android-TV-Boxen melden nur die laufende App, kein Bild (die Leinwand zeigte sonst nur, dass sie an ist).
# Dann zeigt die Ansicht das App-Logo (Quelle Google Play, die Bruecke speichert es auf dem Server zwischen).
APP_PAKET = re.compile(r"^[a-z][a-z0-9_]{0,40}(\.[a-z0-9_]{1,40}){1,6}$")
APP_OHNE = ("launcher", "setupwraith", "settings", "screensaver", "dreamx", "backdrop")


def app_logo_paket(app_id):
    """Paketname, fuer den ein Logo gezeigt wird, oder None (Startbildschirm, Einstellungen, Unsinn)."""
    if not isinstance(app_id, str) or not APP_PAKET.fullmatch(app_id):
        return None
    return None if any(w in app_id for w in APP_OHNE) else app_id


def titelbild_quelle(name):
    """(Entitaet, entity_picture) zu einem Titelbild-Namen oder None."""
    m = LIVE_NAME.fullmatch(name or "")
    return TITELBILDER.get(m.group(1)) if m else None
BILD_TYP = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
_foto_cache = {"pfad": None, "stand": None, "daten": None}


ENTITAET = re.compile(r"^[a-z_]{2,30}\.[a-z0-9_]{1,120}$")


def _anteil(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1


def _puppenhaus(f, da):
    """Puppenhaus (seit 0.6): je Etage ein fertiges Bild (leicht schraeg von oben, z. B. von einem Bildmodell aus einem
    Rundgang-Video erzeugt) und von Hand gesetzte Punkte in Bildkoordinaten (x/y = Anteil von Breite/Hoehe). Kein
    Plan aus Saugroboter-Karten noetig. Alles wird geprueft; Kameras und Babyfon (TABU) kommen nie hinein."""
    etagen = {}
    for eid, e in (f.get("etagen") or {}).items():
        if eid not in ("kg", "eg", "og", "dg") or not isinstance(e, dict) or not da(e.get("basis")):
            continue
        raeume = [{"id": str(r["id"])[:30], "name": str(r.get("name") or "")[:40], "x": r["x"], "y": r["y"],
                   "roborock": str(r.get("roborock") or "")[:40]}
                  for r in (e.get("raeume") or [])[:30]
                  if isinstance(r, dict) and r.get("id") and _anteil(r.get("x")) and _anteil(r.get("y"))]
        punkte = []
        for p in (e.get("punkte") or [])[:40]:
            if not isinstance(p, dict) or not p.get("id") or not _anteil(p.get("x")) or not _anteil(p.get("y")):
                continue
            ents = [y for y in p.get("entitaeten") or [] if isinstance(y, str) and ENTITAET.fullmatch(y)
                    and not TABU.search(y)][:4]
            if TABU.search(str(p.get("name") or "")) or not (ents or p.get("immer") is True):
                continue
            q = {"id": str(p["id"])[:30], "name": str(p.get("name") or "")[:40],
                 "symbol": p.get("symbol") if p.get("symbol") in SYMBOLE else "", "x": p["x"], "y": p["y"],
                 "entitaeten": ents}
            if p.get("an_von") in ents:
                q["an_von"] = p["an_von"]
            if isinstance(p.get("an_ab"), (int, float)) and not isinstance(p.get("an_ab"), bool):
                q["an_ab"] = float(p["an_ab"])
            if p.get("immer") is True:
                q["immer"] = True
            punkte.append(q)
        etagen[eid] = {"name": str(e.get("name") or eid.upper())[:30], "basis": e["basis"], "raeume": raeume,
                       "punkte": punkte}
    if not etagen:
        return None
    aus = {"art": "puppenhaus", "etagen": etagen}
    pj = _projektion(f.get("projektion"), etagen, da)
    if pj:
        aus["projektion"] = pj
    return aus


def _projektion(roh, etagen, da):
    """Foto-Projektion fuers 3D-Haus (seit 0.6, optional): je Etage bis 4 Bilder mit der Kamera, aus deren Blickwinkel
    sie erzeugt wurden ({az, pol, dist, ziel: [x, y, z]}). Nur vorhandene Bilder mit gueltigem Namen und endliche Zahlen."""
    zahl = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    pj = {}
    for eid, liste in (roh or {}).items() if isinstance(roh, dict) else ():
        if eid not in etagen or not isinstance(liste, list):
            continue
        gut = []
        for p in liste[:4]:
            k = p.get("kamera") if isinstance(p, dict) else None
            if not isinstance(k, dict) or not da(p.get("bild")):
                continue
            z = k.get("ziel")
            if not (all(zahl(k.get(x)) for x in ("az", "pol", "dist")) and isinstance(z, list) and len(z) == 3
                    and all(zahl(v) for v in z) and 0 < k["pol"] < 1.6 and 1 < k["dist"] < 80):
                continue
            gut.append({"bild": p["bild"], "kamera": {"az": float(k["az"]), "pol": float(k["pol"]), "dist": float(k["dist"]),
                                                      "ziel": [float(v) for v in z]}})
        if gut:
            pj[eid] = gut
    return pj


def ist_puppenhaus(foto):
    return bool(foto) and foto.get("art") == "puppenhaus"


def foto_laden(daten_ordner):
    """Foto-Grundriss (seit 0.6): daten/grundriss-foto/foto.json oder None. Nur Ebenen, deren Bild wirklich da ist und
    deren Name passt. Mit "art": "puppenhaus" die Puppenhaus-Form."""
    ordner = os.path.join(daten_ordner, "grundriss-foto")
    pfad = os.path.join(ordner, "foto.json")
    try:
        stand = os.path.getmtime(pfad)
    except OSError:
        return None
    with _sperre:
        if _foto_cache["pfad"] != pfad or _foto_cache["stand"] != stand:
            try:
                f = json.load(open(pfad, encoding="utf-8"))
            except (OSError, ValueError):
                return None
            da = lambda n: isinstance(n, str) and BILD_NAME.fullmatch(n) and os.path.isfile(os.path.join(ordner, n))
            if isinstance(f, dict) and f.get("art") == "puppenhaus":
                _foto_cache.update(pfad=pfad, stand=stand, daten=_puppenhaus(f, da))
                return _foto_cache["daten"]
            etagen = {}
            for eid, e in (f.get("etagen") or {}).items():
                ab = e.get("abbildung") or {}
                if not da(e.get("basis")) or not all(isinstance(ab.get(k), (int, float)) for k in ("s", "cx", "cy", "groesse")):
                    continue
                ebenen = [{"id": str(x.get("id"))[:40], "raum": str(x.get("raum"))[:40], "bild": x["bild"],
                           "entitaeten": [y for y in x.get("entitaeten", []) if isinstance(y, str) and not TABU.search(y)][:20]}
                          for x in e.get("ebenen", []) if isinstance(x, dict) and da(x.get("bild"))]
                etagen[eid] = {"basis": e["basis"], "abbildung": {k: ab[k] for k in ("s", "cx", "cy", "groesse")}, "ebenen": ebenen}
            _foto_cache.update(pfad=pfad, stand=stand, daten={"etagen": etagen} if etagen else None)
        return _foto_cache["daten"]


# ------------------------------------------------------------------ 3D-Haus (seit 0.6)

_h3_cache = {"pfad": None, "stand": None, "daten": None}
WORT = re.compile(r"^[a-z_]{1,30}$")
OEFFNUNGEN = ("tuer", "durchgang", "offen", "fenster", "terrassentuer", "haustuer", "dachfenster", "gaube")
BOEDEN = ("fliese_dunkel", "holz", "beton")


def _zahl(v, lo=-50.0, hi=50.0):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi


def _punkt(p):
    return isinstance(p, (list, tuple)) and len(p) == 2 and all(_zahl(x) for x in p)


RICHTUNGEN = ("nord", "sued", "ost", "west")


def _rechteck(r):
    """[x0, y0, x1, y1] mit x0 < x1 und y0 < y1."""
    return isinstance(r, (list, tuple)) and len(r) == 4 and all(_zahl(x) for x in r) and r[0] < r[2] and r[1] < r[3]


def _haus3d(f):
    """Plan des Hauses in Metern fuer vorlagen/grundriss/haus3d.js (echtes 3D, nur waagerechte und senkrechte Waende).
    Von Hand oder mit einem eigenen Skript erzeugt (Muster: vorlagen/grundriss/beispielhaus_erzeugen.py). Alles wird
    geprueft und auf bekannte Felder zugeschnitten; Kameras und Babyfon (TABU) kommen nie hinein, Geraete nur mit
    gueltigen Entitaeten."""
    U = f.get("umriss")
    if not (isinstance(U, list) and len(U) == 4 and all(_zahl(x) for x in U) and U[0] < U[2] and U[1] < U[3]):
        return None
    etagen = {}
    for eid, e in (f.get("etagen") or {}).items():
        if eid not in ("kg", "eg", "og", "dg") or not isinstance(e, dict):
            continue
        raeume = []
        for r in (e.get("raeume") or [])[:30]:
            poly = r.get("poly") if isinstance(r, dict) else None
            if not r.get("id") or not isinstance(poly, list) or not 3 <= len(poly) <= 40 or not all(_punkt(p) for p in poly):
                continue
            q = {"id": str(r["id"])[:30], "name": str(r.get("name") or "")[:40],
                 "boden": r.get("boden") if r.get("boden") in BOEDEN else "beton", "poly": [[float(a), float(b)] for a, b in poly]}
            if _zahl(r.get("stufe"), 0, 2):
                q["stufe"] = float(r["stufe"])
            if r.get("ohne_name") is True:
                q["ohne_name"] = True
            if r.get("wand") == "hell":                 # weiss verputzter Raum (z. B. Bad)
                q["wand"] = "hell"
            raeume.append(q)
        if not raeume:
            continue
        oeff = []
        for o in (e.get("oeffnungen") or [])[:150]:
            if isinstance(o, dict) and o.get("typ") in OEFFNUNGEN and _punkt(o.get("von")) and _punkt(o.get("bis")):
                q = {"typ": o["typ"], "von": list(o["von"]), "bis": list(o["bis"])}
                for k in ("bruestung", "sturz"):
                    if _zahl(o.get(k), 0, 4):
                        q[k] = o[k]
                if o["typ"] == "tuer" and o.get("gegenseite") is True:   # Blatt schwenkt zur anderen Seite
                    q["gegenseite"] = True
                oeff.append(q)
        treppen = []
        for t in (e.get("treppen") or [])[:12]:
            if not isinstance(t, dict):
                continue
            z0 = float(t["z0"]) if _zahl(t.get("z0"), 0, 5) else 0.0
            art = t.get("art") or "lauf"
            # Gerade Laeufe (art "lauf", Standard) mit Starthoehe z0, Podeste (art "podest") und gewendelte Stufen
            # (art "wendel")
            if art == "podest" and _rechteck(t.get("rechteck")) and _zahl(t.get("hoehe"), 0.05, 5):
                treppen.append({"art": "podest", "rechteck": [float(x) for x in t["rechteck"]], "hoehe": float(t["hoehe"])})
            elif art == "wendel" and _rechteck(t.get("rechteck")) and _punkt(t.get("drehpunkt")) \
                    and t.get("start") in RICHTUNGEN and t.get("ende") in RICHTUNGEN and t["start"] != t["ende"] \
                    and _zahl(t.get("hoehe"), 0.05, 5) and _zahl(t.get("stufen"), 2, 12):
                treppen.append({"art": "wendel", "rechteck": [float(x) for x in t["rechteck"]],
                                "drehpunkt": [float(x) for x in t["drehpunkt"]], "start": t["start"], "ende": t["ende"],
                                "z0": z0, "hoehe": float(t["hoehe"]), "stufen": int(t["stufen"])})
            elif art == "lauf" and _punkt(t.get("von")) and _punkt(t.get("bis")) and _zahl(t.get("breite"), 0.5, 3) \
                    and _zahl(t.get("hoehe"), -5, 5) and _zahl(t.get("stufen"), 2, 40):
                treppen.append({"von": list(t["von"]), "bis": list(t["bis"]), "breite": t["breite"], "hoehe": t["hoehe"],
                                "stufen": int(t["stufen"]), "z0": z0,
                                "gelaender": t.get("gelaender") if t.get("gelaender") in RICHTUNGEN else ""})
        gelaender = [[list(l[0]), list(l[1])] for l in (e.get("gelaender") or [])[:20]
                     if isinstance(l, list) and len(l) == 2 and _punkt(l[0]) and _punkt(l[1])]
        moebel = []
        for m in (e.get("moebel") or [])[:250]:
            if not isinstance(m, dict) or not WORT.fullmatch(str(m.get("typ"))) or not (_zahl(m.get("x")) and _zahl(m.get("y"))) \
                    or not (_zahl(m.get("b"), 0.01, 10) and _zahl(m.get("t"), 0.005, 10)):
                continue
            q = {k: m[k] for k in ("typ", "x", "y", "b", "t")}
            q["drehung"] = m["drehung"] if _zahl(m.get("drehung"), -360, 360) else 0
            for k in ("z", "hoehe"):
                if _zahl(m.get(k), 0, 5):
                    q[k] = m[k]
            for k in ("stuehle", "monitore"):
                if _zahl(m.get(k), 0, 12):
                    q[k] = int(m[k])
            if _zahl(m.get("kopf"), 0, 2):              # Stuehle vor Kopf am Esstisch
                q["kopf"] = int(m["kopf"])
            if isinstance(m.get("unten"), list):        # unter dem Schreibtisch [links, rechts]
                u = [x if x in ("pc", "nas") else "" for x in m["unten"][:2] if isinstance(x, str)]
                if any(u):
                    q["unten"] = u
            for k in ("farbe", "stuhlfarbe", "mit", "ecke", "geraet"):
                if isinstance(m.get(k), str) and WORT.fullmatch(m[k]):
                    q[k] = m[k]
            for k in ("rund", "spiegel"):
                if m.get(k) is True:
                    q[k] = True
            moebel.append(q)
        geraete = []
        for g in (e.get("geraete") or [])[:40]:
            if not isinstance(g, dict) or not g.get("id") or not (_zahl(g.get("x")) and _zahl(g.get("y"))):
                continue
            ents = [y for y in g.get("entitaeten") or [] if isinstance(y, str) and ENTITAET.fullmatch(y)
                    and not TABU.search(y)][:4]
            if TABU.search(str(g.get("name") or "")) or not (ents or g.get("immer") is True):
                continue
            q = {"id": str(g["id"])[:30], "name": str(g.get("name") or "")[:40],
                 "symbol": g.get("symbol") if g.get("symbol") in SYMBOLE else "", "x": g["x"], "y": g["y"],
                 "z": g["z"] if _zahl(g.get("z"), 0, 5) else 1.0, "entitaeten": ents}
            if g.get("an_von") in ents:
                q["an_von"] = g["an_von"]
            if _zahl(g.get("an_ab"), -1e6, 1e6):
                q["an_ab"] = float(g["an_ab"])
            if g.get("immer") is True:
                q["immer"] = True
            if isinstance(g.get("foto"), str) and BILD_NAME.fullmatch(g["foto"]):
                q["foto"] = g["foto"]                       # Foto fuers Geraete-Menue (z. B. aus einer Inventar-App)
            geraete.append(q)
        q = {"name": str(e.get("name") or eid.upper())[:30], "boden": e["boden"] if _zahl(e.get("boden"), -10, 20) else 0.0,
             "hoehe": e["hoehe"] if _zahl(e.get("hoehe"), 1.5, 5) else 2.6, "raeume": raeume, "oeffnungen": oeff,
             "treppen": treppen, "gelaender": gelaender, "moebel": moebel, "geraete": geraete}
        if _zahl(e.get("kniestock"), 0, 3) and _zahl(e.get("dachneigung"), 10, 70):
            q.update(kniestock=e["kniestock"], dachneigung=e["dachneigung"],
                     traufen=[t for t in e.get("traufen") or [] if t in ("nord", "sued", "ost", "west")][:2])
        etagen[eid] = q
    if not etagen:
        return None
    h = {"art": "haus3d", "umriss": [float(x) for x in U], "etagen": etagen}
    if _zahl(f.get("nordwinkel"), -360, 360):      # wohin Planoben zeigt (Grad, fuer den Sonnenstand)
        h["nordwinkel"] = float(f["nordwinkel"])
    return h


def haus3d_laden(daten_ordner):
    """3D-Haus: daten/grundriss-foto/haus3d.json oder None (gecacht nach Aenderungszeit)."""
    pfad = os.path.join(daten_ordner, "grundriss-foto", "haus3d.json")
    try:
        stand = os.path.getmtime(pfad)
    except OSError:
        return None
    with _sperre:
        if _h3_cache["pfad"] != pfad or _h3_cache["stand"] != stand:
            try:
                f = json.load(open(pfad, encoding="utf-8"))
            except (OSError, ValueError):
                return None
            _h3_cache.update(pfad=pfad, stand=stand, daten=_haus3d(f) if isinstance(f, dict) and f.get("art") == "haus3d" else None)
        return _h3_cache["daten"]


def bild_datei(daten_ordner, name):
    """Pfad und Typ eines Grundriss-Bilds oder (None, None) - nur Namen nach BILD_NAME, nur aus grundriss-foto/."""
    if not isinstance(name, str) or not BILD_NAME.fullmatch(name):
        return None, None
    pfad = os.path.join(daten_ordner, "grundriss-foto", name)
    return (pfad, BILD_TYP[name.rsplit(".", 1)[1]]) if os.path.isfile(pfad) else (None, None)


def entitaeten(platzierung, foto=None, haus3d=None):
    """Alle Entitaeten, deren Zustand die Ansicht braucht (ohne Tabu)."""
    aus = set()
    for e in list(((foto or {}).get("etagen") or {}).values()) + list(((haus3d or {}).get("etagen") or {}).values()):
        for x in e.get("ebenen", []) + e.get("punkte", []) + e.get("geraete", []):
            aus.update(y for y in x.get("entitaeten", []) if not TABU.search(y))
    for teil in ("eintraege", "unplatziert"):
        for eid, e in (platzierung or {}).get(teil, {}).items():
            if TABU.search(eid):
                continue
            aus.add(eid)
            aus.update(w for w in e.get("werte", []) if isinstance(w, str) and not TABU.search(w))
    return aus


def kurz(s):
    """HA-Zustand -> {s: Zustand, e: Einheit, a: {...}} (nur die Felder aus ATTRIBUTE)."""
    a = s.get("attributes") or {}
    d = {"s": str(s.get("state", ""))[:60]}
    if a.get("unit_of_measurement"):
        d["e"] = str(a["unit_of_measurement"])[:12]
    if isinstance(a.get("friendly_name"), str):
        d["n"] = a["friendly_name"][:50]
    zus = {k: a[k] for k in ATTRIBUTE.get(s["entity_id"].split(".")[0], ()) if k in a and a[k] is not None}
    for k, v in list(zus.items()):
        if k in LISTEN and isinstance(v, list):
            zus[k] = [str(x)[:40] for x in v if isinstance(x, str)][:40]
        elif isinstance(v, str):
            zus[k] = v[:40]
        elif not isinstance(v, (int, float, bool)):
            del zus[k]
    bild = a.get("entity_picture")
    if s["entity_id"].startswith("media_player."):
        # Ein Titel, der nur den Eingang wiederholt ("HDMI3", "TV-Box"), sagt nichts und verdraengte auf der Leinwand die
        # Box mit der laufenden App
        if zus.get("media_title") and zus.get("media_title") == zus.get("source"):
            del zus["media_title"]
        if isinstance(bild, str) and bild and d["s"] in ("playing", "paused", "on", "idle"):
            zus["bild"] = titelbild_name(s["entity_id"], bild)   # Titelbild, nie die URL selbst
        elif d["s"] in ("playing", "paused", "on") and app_logo_paket(a.get("app_id")):
            zus["bild"] = titelbild_name(s["entity_id"], "app:" + a["app_id"])
            zus["logo"] = True
    if zus:
        d["a"] = zus
    return d


def _sauger(grundriss, z):
    """Wo der Saugroboter gerade ist (Karte + Raum laut Roborock), als {etage, raum} oder None."""
    karte = _norm((z.get(SAUGER_KARTE) or {}).get("state"))
    raum = _norm((z.get(SAUGER_RAUM) or {}).get("state"))
    for e in grundriss.get("etagen", []):
        if _norm(e.get("name")) != karte:
            continue
        for r in e.get("raeume", []):
            if _norm(r.get("name")) == raum:
                return {"etage": e["id"], "raum": r["id"]}
    return None


def sauger_puppenhaus(foto, z):
    """Wo der Saugroboter gerade arbeitet, als {etage, raum, aktiv}: gewaehlte Karte -> Etage (Erdgeschoss eg,
    Obergeschoss dg), aktueller Raum laut Roborock -> Raum des Puppenhauses ueber dessen Feld roborock."""
    s = str((z.get(SAUGER) or {}).get("state") or "")
    karte = _norm((z.get(SAUGER_KARTE) or {}).get("state"))
    raum = _norm((z.get(SAUGER_RAUM) or {}).get("state"))
    etage = {"erdgeschoss": "eg", "obergeschoss": "dg", "dachgeschoss": "dg", "keller": "kg"}.get(karte)
    e = (foto.get("etagen") or {}).get(etage) if etage else None
    for r in (e or {}).get("raeume", []):
        if r.get("roborock") and _norm(r["roborock"]) == raum:
            return {"etage": etage, "raum": r["id"], "aktiv": s in ("cleaning", "returning")}
    return None


def antwort(grundriss, platzierung, zustaende, foto=None, haus3d=None):
    """Antwort fuer /v1/grundriss: Plan, Platzierung (ohne Tabu) und Zustaende nur der gezeigten Entitaeten.
    Ein Puppenhaus oder ein 3D-Haus (haus3d) reicht allein, ohne 2D-Plan aus Saugroboter-Karten."""
    if ist_puppenhaus(foto) or (haus3d and not grundriss):
        z = {s["entity_id"]: s for s in zustaende or [] if isinstance(s, dict) and "entity_id" in s}
        a = {"ok": True, "foto": foto if ist_puppenhaus(foto) else None,
             "zustaende": {eid: kurz(z[eid]) for eid in sorted(entitaeten({}, foto, haus3d)) if eid in z},
             "sauger": sauger_puppenhaus(foto, z) if ist_puppenhaus(foto) else None, "stand": int(time.time())}
        if haus3d:
            a["haus3d"] = haus3d
            if ist_puppenhaus(foto) and foto.get("projektion"):
                a["projektion"] = foto["projektion"]       # Bildansicht auf das 3D-Haus projizieren (optional)
        return a
    if not grundriss or not platzierung:
        return {"ok": False, "fehler": _t("Noch kein Grundriss erzeugt (daten/grundriss-foto/haus3d.json fehlt).",
                                          "No floor plan yet (daten/grundriss-foto/haus3d.json is missing).")}
    z = {s["entity_id"]: s for s in zustaende or [] if isinstance(s, dict) and "entity_id" in s}
    brauche = entitaeten(platzierung, foto, haus3d)
    p = {t: {k: v for k, v in platzierung.get(t, {}).items() if not TABU.search(k)} for t in ("eintraege", "unplatziert")}
    a = {"ok": True, "grundriss": grundriss, "platzierung": p,
         "zustaende": {eid: kurz(z[eid]) for eid in sorted(brauche) if eid in z},
         "sauger": _sauger(grundriss, z) if SAUGER in p["eintraege"] else None,
         "foto": foto, "stand": int(time.time())}
    if haus3d:
        a["haus3d"] = haus3d
    return a


def steuern_pruefen(haus3d, entity_id, dienst, daten):
    """Geraete-Menue: (True, saubere Daten) oder (False, Meldung). Nur Entitaeten, die im 3D-Haus an einem Geraet haengen,
    nur Dienste und Felder aus STEUERN, nie Tabu."""
    e, d = str(entity_id or ""), str(dienst or "")
    if not ENTITAET.fullmatch(e) or TABU.search(e):
        return False, _t("Dieses Gerät gibt es hier nicht.", "This device does not exist here.")
    im_haus = {x for et in ((haus3d or {}).get("etagen") or {}).values() for g in et.get("geraete") or []
               for x in g.get("entitaeten") or []}
    if e not in im_haus:
        return False, _t("Das Gerät ist nicht im 3D-Haus.", "This device is not in the 3D house.")
    erlaubt = STEUERN.get(e.split(".")[0], {})
    if d not in erlaubt:
        return False, _t("Das geht an diesem Gerät nicht.", "This device cannot do that.")
    if daten is None:
        daten = {}
    if not isinstance(daten, dict) or set(daten) - set(erlaubt[d]):
        return False, _t("Ungültige Einstellung.", "Invalid setting.")
    sauber = {}
    for k, art in erlaubt[d].items():
        if k not in daten:
            return False, _t("Es fehlt: %s.", "Missing: %s.") % k
        v = daten[k]
        if art is bool:
            if not isinstance(v, bool):
                return False, _t("Ungültiger Wert für %s.", "Invalid value for %s.") % k
        elif art is str:
            if not isinstance(v, str) or not 0 < len(v) <= 60:
                return False, _t("Ungültiger Wert für %s.", "Invalid value for %s.") % k
        else:
            if isinstance(v, bool) or not _zahl(v, art[0], art[1]):
                return False, _t("%s geht nur von %s bis %s.", "%s only goes from %s to %s.") % (k, art[0], art[1])
        sauber[k] = v
    return True, sauber


# ------------------------------------------------------------------ Korrekturen (Werkzeug "grundriss")

def raum_finden(grundriss, text, etage=None):
    """Raum per Name ("Wohnzimmer", "Schlafzimmer 2", "Flur oben") oder HA-Bereich -> (etage, raum) oder None."""
    t = _norm(text)
    et_wort = None
    for w, eid in (("oben", "og"), ("obergeschoss", "og"), ("unten", "eg"), ("erdgeschoss", "eg"), ("keller", "kg")):
        if t.endswith(w) and t != w:
            t, et_wort = t[:-len(w)], eid
    etage = etage or et_wort
    kandidaten = []
    for e in grundriss.get("etagen", []):
        if etage and e["id"] != etage:
            continue
        for r in e.get("raeume", []):
            n = _norm(r.get("name"))
            if n == t or _norm(r.get("id")) == t:
                kandidaten.append((0, e.get("ebene", 0) < 0, e.get("ebene", 0), e["id"], r["id"]))
            elif t and len(t) >= 3 and (n.startswith(t) or t.startswith(n)):
                kandidaten.append((1, e.get("ebene", 0) < 0, e.get("ebene", 0), e["id"], r["id"]))
    for bid, f in grundriss.get("flaechen", {}).items():
        if f.get("raum") and (_norm(f.get("name")) == t or _norm(bid) == t) and (not etage or f["etage"] == etage):
            kandidaten.append((0, False, -9, f["etage"], f["raum"]))
    if not kandidaten:
        return None
    kandidaten.sort()
    return kandidaten[0][3], kandidaten[0][4]


def entitaet_finden(platzierung, text):
    """entity_id oder Name (Teilwort) -> entity_id; mehrdeutig/unbekannt -> (None, Liste der Kandidaten)."""
    alle = dict(platzierung.get("unplatziert", {}), **platzierung.get("eintraege", {}))
    if text in alle:
        return text, []
    t = _norm(text)
    genau = [k for k, v in alle.items() if _norm(v.get("name")) == t]
    if len(genau) == 1:
        return genau[0], []
    teil = [k for k, v in alle.items() if t and (t in _norm(v.get("name")) or t in _norm(k))]
    if len(teil) == 1:
        return teil[0], []
    return None, (genau or teil)


def _raum(grundriss, et, rid):
    for e in grundriss.get("etagen", []):
        if e["id"] == et:
            for r in e.get("raeume", []):
                if r["id"] == rid:
                    return r
    return None


def _innen(poly, x, y):
    drin = False
    for i in range(len(poly)):
        x1, y1 = poly[i - 1]
        x2, y2 = poly[i]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            drin = not drin
    return drin


def lage_punkt(raum, lage):
    """Lagewort ("links", "rechts oben", "Mitte") -> Punkt im Raum, 70 % des Wegs von der Mitte zum Rand in diese
    Richtung (dann sicher innen)."""
    mx, my = raum["mitte"]
    dx = dy = 0
    for wort in re.split(r"[\s,/-]+", str(lage or "")):
        v = LAGE_WORTE.get(_norm(wort))
        if v:
            dx, dy = dx + v[0], dy + v[1]
    richtung = (max(-1, min(1, dx)), max(-1, min(1, dy)))
    if richtung == (0, 0):
        return mx, my
    poly = raum["polygon"]
    dx, dy = richtung
    lang = math.hypot(dx, dy)
    dx, dy = dx / lang, dy / lang
    s, letzte = 0.0, 0.0
    while s < 30:                      # bis zum Rand laufen
        s += 0.05
        if not _innen(poly, mx + dx * s, my + dy * s):
            break
        letzte = s
    s = letzte * 0.7
    return round(mx + dx * s, 2), round(my + dy * s, 2)


def verschieben(grundriss, platzierung, text, raum_text=None, lage=None, x=None, y=None):
    """Geraet umstellen; -> (ok, meldung, neue_platzierung). Setzt "auto": false, damit ein neuer Lauf des Generators
    die Korrektur behaelt."""
    eid, kand = entitaet_finden(platzierung, text)
    if not eid:
        namen = [dict(platzierung.get("unplatziert", {}), **platzierung.get("eintraege", {}))[k]["name"] for k in kand]
        return False, ((_t("Mehrere passen: %s.", "Several match: %s.") % ", ".join(namen[:8])) if namen else
                       _t("Kein Gerät im Grundriss heißt so.", "No device in the floor plan has that name.")), platzierung
    if TABU.search(eid):
        return False, _t("Das zeige ich im Grundriss nicht.", "I do not show that in the floor plan."), platzierung
    alle = dict(platzierung.get("unplatziert", {}), **platzierung.get("eintraege", {}))
    alt = dict(alle[eid])
    if raum_text:
        z = raum_finden(grundriss, raum_text)
        if not z:
            return False, _t("Den Raum %s kenne ich im Grundriss nicht.",
                             "I do not know the room %s in the floor plan.") % raum_text, platzierung
        et, rid = z
    elif alt.get("etage") and alt.get("raum"):
        et, rid = alt["etage"], alt["raum"]
    else:
        return False, _t("Sag mir, in welchem Raum es steht.", "Tell me which room it is in."), platzierung
    r = _raum(grundriss, et, rid)
    if x is not None and y is not None:
        px, py = round(float(x), 2), round(float(y), 2)
        if not _innen(r["polygon"], px, py):
            return False, _t("Der Punkt liegt nicht im Raum %s.",
                             "That point is not inside the room %s.") % r["name"], platzierung
    else:
        px, py = lage_punkt(r, lage)
    neu = {"eintraege": dict(platzierung.get("eintraege", {})), "unplatziert": dict(platzierung.get("unplatziert", {})),
           "version": platzierung.get("version", 1)}
    neu["unplatziert"].pop(eid, None)
    alt.pop("grund", None)
    neu["eintraege"][eid] = dict(alt, etage=et, raum=rid, x=px, y=py, auto=False)
    neu["eintraege"] = dict(sorted(neu["eintraege"].items()))
    return True, _t("%s steht jetzt im Grundriss: %s, %s.", "%s is now in the floor plan: %s, %s.") % (
        alt.get("name", eid), r["name"], lage or _t("Mitte", "centre")), neu


def speichern(daten_ordner, platzierung):
    pfad = os.path.join(daten_ordner, "platzierung.json")
    tmp = pfad + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(platzierung, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, pfad)


def beschreiben(grundriss, platzierung, zustaende=None, raum_text=None):
    """Text fuers Werkzeug: Raeume je Etage mit ihren Geraeten (und Zustand, wenn bekannt)."""
    z = {s["entity_id"]: s for s in zustaende or []}
    filt = raum_finden(grundriss, raum_text) if raum_text else None
    if raum_text and not filt:
        return _t("Den Raum %s kenne ich im Grundriss nicht.", "I do not know the room %s in the floor plan.") % raum_text
    teile = []
    for e in grundriss.get("etagen", []):
        for r in e.get("raeume", []):
            if filt and (e["id"], r["id"]) != filt:
                continue
            g = [v for k, v in platzierung.get("eintraege", {}).items()
                 if v.get("etage") == e["id"] and v.get("raum") == r["id"] and not TABU.search(k)]
            ids = [k for k, v in platzierung.get("eintraege", {}).items() if v in g]
            liste = []
            for k, v in zip(ids, g):
                s = z.get(k)
                liste.append(v["name"] + ((" (%s%s)" % (s["state"], (" " + s["attributes"].get("unit_of_measurement"))
                                                         if s["attributes"].get("unit_of_measurement") else "")) if s else ""))
            teile.append("%s, %s (%s m²%s): %s" % (e["name"], r["name"], r.get("flaeche_m2", "?"),
                                                  _t(", schematisch", ", schematic") if r.get("schematisch") else "",
                                                  "; ".join(liste) if liste else _t("keine Geräte", "no devices")))
    unpl = [v["name"] for k, v in platzierung.get("unplatziert", {}).items() if not TABU.search(k)]
    if unpl and not filt:
        teile.append(_t("Ohne Platz im Grundriss: ", "Not placed in the floor plan: ") + ", ".join(unpl))
    return "\n".join(teile)
