#!/usr/bin/env python3
"""Baustein grundriss.py (Grundriss und 3D-Haus, seit 0.6): haus3d.json pruefen und zuschneiden, Antwort fuer
/v1/grundriss, Geraete-Menue (steuern_pruefen, STEUERN), Titelbild- und App-Logo-Namen, Puppenhaus, Foto-Grundriss und
Foto-Projektion, 2D-Plan (Umstellen, Beschreiben), Sprache und Saugroboter-Kennungen.
Testdaten: das erfundene Beispielhaus (beispiel-haus3d.json bzw. beispielhaus_erzeugen.py, gesucht in
../spiegel/grundriss/, ../grundriss/ und neben diesem Test; fehlt es, wird dieser Teil sichtbar uebersprungen), sonst
eingebettete Daten in Temp-Ordnern. Keine Netzzugriffe, keine Bruecke, kein Home Assistant."""
import atexit
import json
import os
import shutil
import stat
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import grundriss as gr  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:300]) if info and not bed else ""))


def wirft(f, *a, **k):
    try:
        f(*a, **k)
    except ValueError:
        return True
    return False


def ordner():
    """Neuer Datenordner mit grundriss-foto/ -> (daten, grundriss-foto); wird am Ende geloescht."""
    t = tempfile.mkdtemp(prefix="grundriss-test-")
    atexit.register(shutil.rmtree, t, True)
    os.makedirs(os.path.join(t, "grundriss-foto"))
    return t, os.path.join(t, "grundriss-foto")


def schreib(pfad, daten, zeit=None):
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(daten if isinstance(daten, str) else json.dumps(daten, ensure_ascii=False))
    if zeit is not None:                 # eigene Aenderungszeit: die Lader zwischenspeichern nach mtime
        os.utime(pfad, (zeit, zeit))


def bild(pfad):
    with open(pfad, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0bild")


def ha(eid, s, **attr):
    return {"entity_id": eid, "state": s, "attributes": attr}


R = lambda x0, y0, x1, y1: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]   # noqa: E731

# ---------------------------------------------------------------- Sprache, Tabu, Saugroboter-Kennungen
pruef("Sprache: Standard Deutsch", gr.SPRACHE == "de")
pruef("Sprache: nur de oder en", wirft(gr.setze_sprache, "fr") and gr.SPRACHE == "de")
pruef("Tabu: Babyfon-Integration auch ohne Herstellerpraefix", all(gr.TABU.search(x) for x in (
    "sensor.avent_temperatur", "camera.flur", "media_player.babyfon", "switch.kamera_privat", "camera.chuangmi_c200")))
pruef("Tabu: normale Geraete nicht", not any(gr.TABU.search(x) for x in ("light.wohnzimmer", "media_player.kueche", "vacuum.saugroboter")))
VORGABE = (gr.SAUGER, gr.SAUGER_RAUM, gr.SAUGER_KARTE)
pruef("Saugroboter: neutrale Vorgaben", VORGABE == ("vacuum.saugroboter", "sensor.saugroboter_aktueller_raum",
                                                    "select.saugroboter_ausgewahlte_karte"), VORGABE)
pruef("Saugroboter: falsche Domain abgelehnt, nichts geaendert", wirft(gr.setze_sauger, "sensor.x", None, None)
      and wirft(gr.setze_sauger, None, "select.x") and wirft(gr.setze_sauger, "vacuum.<b>") and wirft(gr.setze_sauger, 5)
      and (gr.SAUGER, gr.SAUGER_RAUM, gr.SAUGER_KARTE) == VORGABE)
gr.setze_sauger("vacuum.robbi")
pruef("Saugroboter: nur das vacuum umgestellt", (gr.SAUGER, gr.SAUGER_RAUM, gr.SAUGER_KARTE) == ("vacuum.robbi",) + VORGABE[1:])
gr.setze_sauger(*VORGABE)

# ---------------------------------------------------------------- 3D-Haus: Feldfilter (haus3d_laden, _haus3d)
T, O = ordner()
H3 = {"art": "haus3d", "umriss": [-4, -3, 4, 3], "lage": {"breite": 1}, "nordwinkel": 30, "etagen": {
    "eg": {"name": "Erdgeschoss", "boden": 0, "hoehe": 2.6,
           "raeume": [{"id": "wohnzimmer", "name": "Wohnzimmer", "boden": "fliese_dunkel", "poly": R(-4, -3, 0, 3)},
                      {"id": "kueche", "name": "Küche", "boden": "marmor", "poly": R(0, -3, 4, 3), "stufe": 9},
                      {"id": "kaputt", "name": "X", "poly": [[0, 0], [1, 1]]},
                      {"id": "weit", "name": "Y", "poly": R(-400, 0, 1, 1)},
                      {"id": "podest", "name": "Podest", "poly": R(-1, -1, 0, 0), "stufe": 0.4, "ohne_name": True}],
           "oeffnungen": [{"typ": "tuer", "von": [0, -1], "bis": [0, 0]},
                          {"typ": "fenster", "von": [-3, 3], "bis": [-2, 3], "bruestung": 0.8, "sturz": 2.2},
                          {"typ": "<script>", "von": [1, 3], "bis": [2, 3]},
                          {"typ": "durchgang", "von": [0, 1], "bis": "x"},
                          {"typ": "fenster", "von": [2, 3], "bis": [3, 3], "bruestung": 9}],
           "treppen": [{"von": [-3.5, -2.5], "bis": [-1, -2.5], "breite": 0.9, "hoehe": 2.8, "stufen": 15, "gelaender": "sued"},
                       {"von": [0, 0], "bis": [1, 0], "breite": 99, "hoehe": 2, "stufen": 10},
                       {"art": "podest", "rechteck": [-1, -1, 0, 0], "hoehe": 0.4},
                       {"art": "wendel", "rechteck": [0, -1, 1, 0], "drehpunkt": [0, 0], "start": "sued", "ende": "ost",
                        "z0": 0.4, "hoehe": 0.6, "stufen": 3},
                       {"art": "wendel", "rechteck": [0, -1, 1, 0], "drehpunkt": [0, 0], "start": "sued", "ende": "sued",
                        "hoehe": 0.6, "stufen": 3},
                       {"art": "lauf", "von": [1, 1], "bis": [3, 1], "breite": 1, "hoehe": 2.4, "stufen": 12, "z0": 0.4,
                        "gelaender": "oben"}],
           "moebel": [{"typ": "ecksofa", "x": -2, "y": 2, "b": 3, "t": 2, "drehung": 180, "farbe": "grau", "ecke": "ost"},
                      {"typ": "leinwand", "x": -3.9, "y": 0, "b": 2, "t": 0.04, "z": 1, "hoehe": 1.4, "geraet": "beamer"},
                      {"typ": "<img onerror=x>", "x": 0, "y": 0, "b": 1, "t": 1},
                      {"typ": "regal", "x": 0, "y": 0, "b": 1, "t": 1, "farbe": "<b>rot</b>", "drehung": "quer"},
                      {"typ": "tisch", "x": 1e9, "y": 0, "b": 1, "t": 1},
                      {"typ": "schreibtisch", "x": 1, "y": 1, "b": 1.6, "t": 0.7, "monitore": 2, "geraet": "pc"},
                      {"typ": "teppich", "x": 1, "y": 1, "b": 2, "t": 2, "rund": True, "spiegel": "ja"},
                      {"typ": "hochschrank", "x": 1, "y": 1, "b": 0.6, "t": 0.6, "mit": "backofen", "stuehle": 99}],
           "geraete": [{"id": "beamer", "name": "Beamer", "symbol": "tv", "x": -3.8, "y": 0, "z": 1.1,
                        "entitaeten": ["media_player.beamer_box", "sensor.multimedia_leistung"],
                        "an_von": "sensor.multimedia_leistung", "an_ab": 20, "foto": "eg_geraet_beamer.jpg"},
                       {"id": "nas", "name": "Server", "symbol": "server", "x": 2, "y": -2, "immer": True, "entitaeten": []},
                       {"id": "baby", "name": "Babyfon", "x": 1, "y": 1, "entitaeten": ["camera.babyfon"]},
                       {"id": "mix", "name": "Mix", "symbol": "<svg>", "x": 1, "y": 2, "z": 99, "foto": "../x.jpg",
                        "entitaeten": ["media_player.x", "camera.avent_kinderzimmer", "kein punkt"],
                        "an_von": "camera.avent_kinderzimmer", "an_ab": "viel"},
                       {"id": "leer", "name": "Leer", "x": 0, "y": 0, "entitaeten": []}]},
    "dg": {"name": "Dachgeschoss", "boden": 2.85, "hoehe": 2.5, "kniestock": 1.0, "dachneigung": 40,
           "traufen": ["west", "ost", "oben"], "raeume": [{"id": "bad", "name": "Bad", "boden": "holz", "poly": R(-4, -3, 4, 3)}],
           "gelaender": [[[-1, -1], [1, -1]], [[0, 0]]], "moebel": [], "geraete": []},
    "xx": {"name": "Fremd", "raeume": [{"id": "a", "poly": R(0, 0, 1, 1)}]},
    "kg": {"name": "Keller", "raeume": []}}}
pruef("3D-Haus: ohne Datei None", gr.haus3d_laden(T) is None)
schreib(os.path.join(O, "haus3d.json"), H3, 100)
h = gr.haus3d_laden(T)
pruef("3D-Haus erkannt", h and h["art"] == "haus3d" and h["umriss"] == [-4.0, -3.0, 4.0, 3.0], h)
pruef("Nur Etagen mit Raeumen und bekannter Kennung (kg leer, xx fremd)", sorted(h["etagen"]) == ["dg", "eg"], sorted(h["etagen"]))
pruef("Nordwinkel kommt durch, fremdes Feld lage nicht", h.get("nordwinkel") == 30.0 and "lage" not in h, sorted(h))
E = h["etagen"]["eg"]
pruef("Raeume: kaputtes und zu weites Polygon fallen weg", [r["id"] for r in E["raeume"]] == ["wohnzimmer", "kueche", "podest"])
k = E["raeume"][1]
pruef("Unbekannter Boden wird Beton, Stufe ausserhalb des Rahmens faellt weg", k["boden"] == "beton" and "stufe" not in k, k)
pruef("Raum: Stufe im Rahmen und ohne_name bleiben", E["raeume"][2].get("stufe") == 0.4 and E["raeume"][2].get("ohne_name") is True)
pruef("Oeffnungen: nur bekannte Arten mit zwei Punkten", [o["typ"] for o in E["oeffnungen"]] == ["tuer", "fenster", "fenster"],
      E["oeffnungen"])
pruef("Fenster behaelt Bruestung und Sturz, unmoegliche Bruestung faellt weg", E["oeffnungen"][1].get("bruestung") == 0.8
      and E["oeffnungen"][1].get("sturz") == 2.2 and "bruestung" not in E["oeffnungen"][2], E["oeffnungen"])
tr = E["treppen"]
pruef("Treppen: unmoegliche Breite und Wendel ohne Richtungswechsel fallen weg", [t.get("art", "lauf") for t in tr]
      == ["lauf", "podest", "wendel", "lauf"], tr)
pruef("Treppe: Gelaender und Starthoehe z0 (Standard 0)", tr[0]["gelaender"] == "sued" and tr[0]["z0"] == 0.0
      and tr[3]["z0"] == 0.4 and tr[3]["gelaender"] == "", tr)
pruef("Wendel: Drehpunkt, Richtungen, z0, Stufen als Zahl", tr[2] == {"art": "wendel", "rechteck": [0.0, -1.0, 1.0, 0.0],
      "drehpunkt": [0.0, 0.0], "start": "sued", "ende": "ost", "z0": 0.4, "hoehe": 0.6, "stufen": 3}, tr[2])
typen = [m["typ"] for m in E["moebel"]]
pruef("Moebel: fremder Typ und Riesenkoordinate fallen weg", typen == ["ecksofa", "leinwand", "regal", "schreibtisch", "teppich",
                                                                      "hochschrank"], typen)
pruef("Moebel: Farbe mit Markup und Drehung als Text werden verworfen",
      "farbe" not in E["moebel"][2] and E["moebel"][2]["drehung"] == 0, E["moebel"][2])
pruef("Moebel: Bildschirm behaelt die Verknuepfung zum Geraet", E["moebel"][1].get("geraet") == "beamer")
pruef("Moebel: monitore, ecke, mit; rund nur als true", E["moebel"][3].get("monitore") == 2 and E["moebel"][0].get("ecke") == "ost"
      and E["moebel"][5].get("mit") == "backofen" and E["moebel"][4].get("rund") is True and "spiegel" not in E["moebel"][4]
      and "stuehle" not in E["moebel"][5], E["moebel"])
ids = [g["id"] for g in E["geraete"]]
pruef("Babyfon-Geraet und Geraet ohne Entitaet fallen ganz weg", ids == ["beamer", "nas", "mix"], ids)
mix = E["geraete"][2]
pruef("Kamera-Entitaet und ungueltige Kennung aus gemischtem Geraet entfernt", mix["entitaeten"] == ["media_player.x"], mix)
pruef("an_von nur, wenn erlaubt; Symbol leer; Hoehe auf 1 m; an_ab als Text weg", "an_von" not in mix and mix["symbol"] == ""
      and mix["z"] == 1.0 and "an_ab" not in mix, mix)
pruef("An-Regel (an_von, an_ab) bleibt", E["geraete"][0].get("an_von") == "sensor.multimedia_leistung"
      and E["geraete"][0].get("an_ab") == 20.0)
pruef("Geraetefoto nur mit gueltigem Namen", E["geraete"][0].get("foto") == "eg_geraet_beamer.jpg" and "foto" not in mix)
pruef("Immer-an-Geraet ohne Entitaet bleibt", E["geraete"][1].get("immer") is True and E["geraete"][1]["entitaeten"] == [])
D = h["etagen"]["dg"]
pruef("Dachgeschoss: Kniestock, Neigung, nur bekannte Traufen", D.get("kniestock") == 1.0 and D.get("traufen") == ["west", "ost"], D)
pruef("Gelaender: nur Linien aus zwei Punkten", D["gelaender"] == [[[-1, -1], [1, -1]]], D["gelaender"])
pruef("Nichts mit Kamera/Babyfon im Ergebnis", not any(w in json.dumps(h) for w in ("camera", "babyfon", "avent")))
pruef("Entitaeten fuer die Abfrage: Geraete des 3D-Hauses, ohne Kameras",
      gr.entitaeten({}, None, h) == {"media_player.beamer_box", "sensor.multimedia_leistung", "media_player.x"},
      gr.entitaeten({}, None, h))
pruef("Zwischenspeicher: gleiche Aenderungszeit, gleiches Ergebnis", gr.haus3d_laden(T) is h)
schreib(os.path.join(O, "haus3d.json"), {"art": "anders"}, 101)
pruef("Fremde Datei (art nicht haus3d) wird nicht genommen", gr.haus3d_laden(T) is None)
schreib(os.path.join(O, "haus3d.json"), "{kaputt", 102)
pruef("Kaputtes JSON: kein 3D-Haus, kein Absturz", gr.haus3d_laden(T) is None)
schreib(os.path.join(O, "haus3d.json"), dict(H3, umriss=[4, 3, -4, -3]), 103)
pruef("Umriss verdreht: kein 3D-Haus", gr.haus3d_laden(T) is None)
schreib(os.path.join(O, "haus3d.json"), H3, 104)
h = gr.haus3d_laden(T)

# Planfelder fuer Kopfstuehle, PC/Server unter dem Schreibtisch, helle Waende und Tueranschlag
F = gr._haus3d({"art": "haus3d", "umriss": [-4, -4, 4, 4], "etagen": {"eg": {"name": "EG", "boden": 0, "hoehe": 2.6,
    "raeume": [{"id": "bad", "name": "Bad", "boden": "fliese_dunkel", "wand": "hell", "poly": R(-4, -4, 0, 0)},
               {"id": "flur", "name": "Flur", "boden": "fliese_dunkel", "wand": "pink", "poly": R(0, 0, 4, 4)}],
    "moebel": [{"typ": "esstisch", "x": 1, "y": 1, "b": 2, "t": 1, "stuehle": 4, "kopf": 2, "stuhlfarbe": "anthrazit"},
               {"typ": "esstisch", "x": 1, "y": 1, "b": 2, "t": 1, "kopf": 9, "stuhlfarbe": "<i>"},
               {"typ": "schreibtisch", "x": 2, "y": 2, "b": 1.5, "t": 0.6, "unten": ["pc", "nas"]},
               {"typ": "schreibtisch", "x": 2, "y": 2, "b": 1.5, "t": 0.6, "unten": ["<script>", "nas", "pc"]},
               {"typ": "epiano", "x": 0, "y": 0, "b": 1.3, "t": 0.5}],
    "oeffnungen": [{"typ": "tuer", "von": [0, 1], "bis": [0, 2], "gegenseite": True},
                   {"typ": "tuer", "von": [0, 2.5], "bis": [0, 3], "gegenseite": "ja"},
                   {"typ": "haustuer", "von": [-4, -3], "bis": [-4, -2], "gegenseite": True},
                   {"typ": "tuer", "von": [1, 0], "bis": [2, 0]}]}}})["etagen"]["eg"]
r = {x["id"]: x for x in F["raeume"]}
m = F["moebel"]
o = F["oeffnungen"]
pruef("Raum hell durch, andere Wandfarbe nicht", r["bad"].get("wand") == "hell" and "wand" not in r["flur"])
pruef("kopf, stuehle, stuhlfarbe durch; zu grosser kopf und Markup nicht", m[0].get("kopf") == 2 and m[0].get("stuehle") == 4
      and m[0].get("stuhlfarbe") == "anthrazit" and "kopf" not in m[1] and "stuhlfarbe" not in m[1], m[:2])
pruef("unten: nur pc/nas, hoechstens zwei", m[2].get("unten") == ["pc", "nas"] and m[3].get("unten") == ["", "nas"], m[2:4])
pruef("Neuer Moebeltyp (Kleinbuchstaben) kommt durch", m[4]["typ"] == "epiano")
pruef("gegenseite nur als true und nur an Tueren", o[0].get("gegenseite") is True and "gegenseite" not in o[1]
      and "gegenseite" not in o[2] and "gegenseite" not in o[3], o)

# ---------------------------------------------------------------- Antwort fuer /v1/grundriss
Z = [ha("media_player.beamer_box", "playing"), ha("camera.avent_kinderzimmer", "idle"), ha("media_player.verstaerker", "on"),
     ha("sensor.fremd", "1")]
a = gr.antwort(None, None, Z, None, h)
pruef("Nur 3D-Haus (ohne Plan, ohne Puppenhaus): ok mit haus3d", a.get("ok") is True and a.get("haus3d") == h
      and a.get("foto") is None and a.get("sauger") is None, sorted(a))
pruef("Zustaende nur der Geraete im 3D-Haus", sorted(a["zustaende"]) == ["media_player.beamer_box"], a["zustaende"])
pruef("Antwort ohne Kamera", "camera" not in json.dumps(a))
FOTO = {"art": "puppenhaus", "etagen": {"eg": {"name": "EG", "basis": "eg_puppenhaus.jpg", "raeume": [], "punkte": [
    {"id": "verstaerker", "name": "Verstärker", "x": 0.5, "y": 0.5, "entitaeten": ["media_player.verstaerker"]}]}}}
bild(os.path.join(O, "eg_puppenhaus.jpg"))
schreib(os.path.join(O, "foto.json"), FOTO, 200)
f = gr.foto_laden(T)
a2 = gr.antwort(None, None, Z, f, h)
pruef("Puppenhaus und 3D-Haus zusammen: beide drin", gr.ist_puppenhaus(a2.get("foto")) and a2.get("haus3d") == h)
pruef("Zustaende fuer beide Ansichten", sorted(a2["zustaende"]) == ["media_player.beamer_box", "media_player.verstaerker"],
      a2["zustaende"])
pruef("Ohne 3D-Haus kein Feld haus3d", "haus3d" not in gr.antwort(None, None, Z, f))
leer = gr.antwort(None, None, [])
pruef("Ohne Daten: ok false mit deutschem Hinweis", leer["ok"] is False and leer["fehler"].startswith("Noch kein Grundriss"), leer)

# ---------------------------------------------------------------- Geraete-Menue: steuern_pruefen, STEUERN
M = gr._haus3d({"art": "haus3d", "umriss": [-4, -4, 4, 4], "etagen": {"eg": {"name": "EG", "boden": 0, "hoehe": 2.5,
    "raeume": [{"id": "wohnzimmer", "name": "Wohnzimmer", "poly": R(-4, -4, 4, 4)}],
    "geraete": [{"id": "verstaerker", "name": "Verstärker", "x": 0, "y": 0,
                 "entitaeten": ["media_player.verstaerker", "switch.verstaerker_steckdose"], "foto": "eg_geraet_verstaerker.jpg"},
                {"id": "pc", "name": "PC", "x": 1, "y": 1, "entitaeten": ["switch.pc_steckdose"], "foto": "../x.jpg"},
                {"id": "klima", "name": "Klima", "x": 2, "y": 1, "entitaeten": ["climate.klima", "light.stehlampe"]},
                {"id": "kamera", "name": "Kamera", "x": 2, "y": 2, "entitaeten": ["camera.schlafzimmer"]}]}}})
g = {x["id"]: x for x in M["etagen"]["eg"]["geraete"]}
pruef("Menue: Foto mit gueltigem Namen bleibt, mit Pfad faellt weg", g["verstaerker"].get("foto") == "eg_geraet_verstaerker.jpg"
      and "foto" not in g["pc"], g)
pruef("Menue: Kamera kommt gar nicht ins Haus", "kamera" not in g, sorted(g))
sp = gr.steuern_pruefen
V = "media_player.verstaerker"
pruef("Lautstaerke 0.4 erlaubt", sp(M, V, "volume_set", {"volume_level": 0.4}) == (True, {"volume_level": 0.4}))
pruef("Lautstaerke 1.5 abgelehnt", sp(M, V, "volume_set", {"volume_level": 1.5}) == (False, "volume_level geht nur von 0 bis 1."))
pruef("Quelle als Text erlaubt, leer oder zu lang nicht", sp(M, V, "select_source", {"source": "TV Audio"})[0]
      and not sp(M, V, "select_source", {"source": ""})[0] and not sp(M, V, "select_source", {"source": "x" * 61})[0])
pruef("Stumm nur als Wahrheitswert", sp(M, V, "volume_mute", {"is_volume_muted": True})[0]
      and sp(M, V, "volume_mute", {"is_volume_muted": 1}) == (False, "Ungültiger Wert für is_volume_muted."))
pruef("Fremdes Feld abgelehnt", sp(M, V, "volume_set", {"volume_level": 0.3, "entity_id": "x.y"}) == (False, "Ungültige Einstellung."))
pruef("Daten kein Objekt abgelehnt", not sp(M, V, "volume_set", [0.3])[0])
pruef("Unbekannter Dienst abgelehnt", sp(M, V, "play_media", {}) == (False, "Das geht an diesem Gerät nicht."))
pruef("Geraet nicht im Plan abgelehnt", sp(M, "media_player.irgendwas", "turn_on", None) == (False, "Das Gerät ist nicht im 3D-Haus."))
pruef("Ohne 3D-Haus nichts erlaubt", not sp(None, V, "turn_on", None)[0])
pruef("Kamera und kaputte Kennung abgelehnt", sp(M, "camera.schlafzimmer", "turn_on", None) == (False, "Dieses Gerät gibt es hier nicht.")
      and not sp(M, "../etc", "turn_on", None)[0] and not sp(M, None, "turn_on", None)[0])
pruef("Wahrheitswert statt Zahl abgelehnt", not sp(M, "climate.klima", "set_temperature", {"temperature": True})[0])
pruef("Klima 22 Grad erlaubt, 40 nicht", sp(M, "climate.klima", "set_temperature", {"temperature": 22})[0]
      and not sp(M, "climate.klima", "set_temperature", {"temperature": 40})[0])
pruef("Pflichtfeld fehlt", sp(M, V, "volume_mute", {}) == (False, "Es fehlt: is_volume_muted."))
pruef("Licht: an mit Helligkeit 1..100, an ohne Helligkeit fehlt", sp(M, "light.stehlampe", "turn_on", {"brightness_pct": 60})[0]
      and not sp(M, "light.stehlampe", "turn_on", {"brightness_pct": 0})[0] and not sp(M, "light.stehlampe", "turn_on", None)[0])
pruef("Steckdose aus ist hier erlaubt (Sperrliste prueft der Werkzeug-Server)", sp(M, "switch.verstaerker_steckdose", "turn_off", None)
      == (True, {}))
pruef("STEUERN: keine Kameras, kein Schloss, nur bekannte Domains", sorted(gr.STEUERN) == ["climate", "light", "media_player", "switch",
                                                                                         "vacuum", "water_heater"])
k = gr.kurz(ha(V, "on", friendly_name="AV-Receiver", source_list=["TV Audio", "Radio", 5], volume_level=0.35, is_volume_muted=False,
               supported_features=69005, entity_picture="/api/x?token=geheim", hvac_modes=["heat"], icon="mdi:x"))
pruef("kurz: Quellenliste nur Texte", k["a"].get("source_list") == ["TV Audio", "Radio"], k)
pruef("kurz: Anzeigename dabei, fremde Attribute nicht", k.get("n") == "AV-Receiver" and "icon" not in k["a"]
      and "hvac_modes" not in k["a"], k)
pruef("kurz: Bild-Adresse mit Token nicht dabei", "geheim" not in json.dumps(k) and "entity_picture" not in json.dumps(k), k)
kl = gr.kurz(ha("climate.klima", "cool", hvac_modes=["off", "cool"] + ["x" * 50] * 60, temperature=22, unit_of_measurement="°C",
                fan_mode={"kaputt": 1}))
pruef("kurz: Listen gekuerzt, Einheit dabei, Objekte verworfen", len(kl["a"]["hvac_modes"]) == 40 and len(kl["a"]["hvac_modes"][2]) == 40
      and kl.get("e") == "°C" and "fan_mode" not in kl["a"], kl)

# ---------------------------------------------------------------- Titelbild und App-Logo (Namen statt URLs)
PLEXPFAD = "/library/metadata/188068/thumb/179"
s1 = ha("media_player.box", "playing", app_name="Plex", entity_picture=PLEXPFAD)
kb = gr.kurz(s1)
name = (kb.get("a") or {}).get("bild", "")
pruef("Player mit Bild: Name im Muster", gr.BILD_NAME.fullmatch(name) and gr.LIVE_NAME.fullmatch(name), name)
pruef("keine URL in den Daten", PLEXPFAD not in repr(kb))
pruef("Zuordnung gemerkt", gr.titelbild_quelle(name) == ("media_player.box", PLEXPFAD))
pruef("anderes Bild, anderer Name", gr.kurz(ha("media_player.box", "playing", entity_picture="/library/metadata/1/thumb/2"))["a"]["bild"]
      != name)
pruef("aus: kein Bild", "bild" not in (gr.kurz(dict(s1, state="off")).get("a") or {}))
pruef("Licht: nie Bild", "bild" not in (gr.kurz(ha("light.x", "on", entity_picture="/x")).get("a") or {}))
pruef("unbekannter Name: nichts", gr.titelbild_quelle("eg_live_000000000000.jpg") is None and gr.titelbild_quelle("eg_x.jpg") is None
      and gr.titelbild_quelle(None) is None)
pruef("Plex-Pfad streng", gr.PLEX_PFAD.fullmatch(PLEXPFAD) and not gr.PLEX_PFAD.fullmatch("/library/metadata/1/thumb/2/../../x")
      and not gr.PLEX_PFAD.fullmatch("http://boese/library/metadata/1/thumb/2"))
for i in range(60):
    gr.titelbild_name("media_player.viele", "/bild/%d" % i)
pruef("hoechstens 40 Titelbilder gemerkt", len(gr.TITELBILDER) <= 40, len(gr.TITELBILDER))
s6 = ha("media_player.box_wz", "on", app_id="de.beispiel.mediathek", app_name="Mediathek")
k6 = gr.kurz(s6)["a"]
pruef("Box mit App, ohne Bild: Logo-Name", gr.LIVE_NAME.fullmatch(k6.get("bild", "")) and k6.get("logo") is True, k6)
pruef("Logo-Zuordnung", gr.titelbild_quelle(k6["bild"]) == ("media_player.box_wz", "app:de.beispiel.mediathek"))
pruef("idle: kein Logo", "bild" not in (gr.kurz(dict(s6, state="idle")).get("a") or {}))
for aid in ("com.google.android.apps.tv.launcherx", "com.android.tv.settings", "AndroidNativeApp", "../etc", "de.x/../y", "", None, 5):
    pruef("kein Logo fuer %r" % (aid,), "bild" not in (gr.kurz(dict(s6, attributes={"app_id": aid})).get("a") or {})
          and gr.app_logo_paket(aid) is None)
pruef("app_logo_paket: gueltiges Paket bleibt", gr.app_logo_paket("com.netflix.ninja") == "com.netflix.ninja")
k7 = gr.kurz(ha("media_player.cast", "playing", app_id="com.netflix.ninja", entity_picture="/p/q"))["a"]
pruef("echtes Bild schlaegt Logo", "logo" not in k7 and gr.titelbild_quelle(k7["bild"]) == ("media_player.cast", "/p/q"))
k8 = gr.kurz(ha("media_player.beamer", "on", source="HDMI3", media_title="HDMI3"))["a"]
pruef("Titel = Eingang: verworfen", "media_title" not in k8 and k8.get("source") == "HDMI3", k8)
k9 = gr.kurz(ha("media_player.verstaerker", "on", source="TV-Box", media_title="Krimi am Sonntag"))["a"]
pruef("echter Titel bleibt", k9.get("media_title") == "Krimi am Sonntag", k9)

# ---------------------------------------------------------------- Puppenhaus (foto.json mit art "puppenhaus")
T2, O2 = ordner()
for n in ("eg_puppenhaus.jpg", "kg_puppenhaus.jpg"):
    bild(os.path.join(O2, n))
PH = {"art": "puppenhaus", "etagen": {
    "eg": {"name": "Erdgeschoss", "basis": "eg_puppenhaus.jpg",
           "raeume": [{"id": "wohnzimmer", "name": "Wohnzimmer", "x": 0.6, "y": 0.7, "roborock": "Wohnzimmer"},
                      {"id": "kaputt", "name": "X", "x": 1.5, "y": 0.2}],
           "punkte": [{"id": "verstaerker", "name": "Verstärker", "symbol": "lautsprecher", "x": 0.8, "y": 0.6,
                       "entitaeten": ["media_player.verstaerker", "sensor.verstaerker_leistung"]},
                      {"id": "pc", "name": "PC", "symbol": "pc", "x": 0.76, "y": 0.23, "an_von": "sensor.pc_leistung",
                       "an_ab": 15, "entitaeten": ["switch.pc_steckdose", "sensor.pc_leistung"]},
                      {"id": "nas", "name": "Server", "symbol": "server", "x": 0.78, "y": 0.26, "immer": True, "entitaeten": []},
                      {"id": "baby", "name": "Babyfon", "x": 0.3, "y": 0.3, "entitaeten": ["camera.babyfon"]},
                      {"id": "mix", "name": "Mix", "x": 0.4, "y": 0.4, "symbol": "<script>",
                       "entitaeten": ["media_player.x", "camera.avent_kinderzimmer", "kein punkt"], "an_von": "camera.avent_kinderzimmer"},
                      {"id": "weit", "name": "Weit", "x": -0.1, "y": 0.5, "entitaeten": ["media_player.y"]}]},
    "dg": {"name": "Dachgeschoss", "basis": "dg_puppenhaus.jpg", "punkte": []},
    "xx": {"name": "Fremd", "basis": "eg_puppenhaus.jpg"},
    "kg": {"name": "Keller", "basis": "kg_puppenhaus.jpg", "raeume": [], "punkte": [
        {"id": "trockner", "name": "Trockner", "x": 0.6, "y": 0.2, "an_ab": "viel", "entitaeten": ["sensor.trockner_leistung"]}]}}}
schreib(os.path.join(O2, "foto.json"), PH, 300)
f = gr.foto_laden(T2)
pruef("Puppenhaus erkannt", gr.ist_puppenhaus(f) and f["art"] == "puppenhaus")
pruef("Nur Etagen mit vorhandenem Bild und bekannter Kennung (dg ohne Bild, xx fremd)", sorted(f["etagen"]) == ["eg", "kg"],
      sorted(f["etagen"]))
E = f["etagen"]["eg"]
pruef("Raum ausserhalb 0..1 faellt weg", [r["id"] for r in E["raeume"]] == ["wohnzimmer"])
ids = [p["id"] for p in E["punkte"]]
pruef("Babyfon-Punkt und Punkt ausserhalb des Bilds fallen weg", "baby" not in ids and "weit" not in ids, ids)
mix = next(p for p in E["punkte"] if p["id"] == "mix")
pruef("Kamera-Entitaet und ungueltige Kennung aus gemischtem Punkt entfernt", mix["entitaeten"] == ["media_player.x"], mix)
pruef("an_von nur, wenn erlaubt; unbekanntes Symbol leer", "an_von" not in mix and mix["symbol"] == "")
pc = next(p for p in E["punkte"] if p["id"] == "pc")
pruef("An-Regel (an_von, an_ab) bleibt", pc.get("an_von") == "sensor.pc_leistung" and pc.get("an_ab") == 15.0)
pruef("Immer-an-Punkt ohne Entitaet bleibt", next(p for p in E["punkte"] if p["id"] == "nas").get("immer") is True)
pruef("an_ab als Text wird ignoriert", "an_ab" not in f["etagen"]["kg"]["punkte"][0])
pruef("Entitaeten fuer die Abfrage: Punkte, ohne Kameras",
      gr.entitaeten({}, f) == {"media_player.verstaerker", "sensor.verstaerker_leistung", "switch.pc_steckdose", "sensor.pc_leistung",
                               "media_player.x", "sensor.trockner_leistung"}, gr.entitaeten({}, f))
ZS = [ha("media_player.verstaerker", "on", source="TV"), ha("camera.avent_kinderzimmer", "idle"),
      ha(gr.SAUGER, "cleaning", battery_level=70), ha(gr.SAUGER_KARTE, "Erdgeschoss"), ha(gr.SAUGER_RAUM, "Wohnzimmer")]
a = gr.antwort(None, None, ZS, f)
pruef("Antwort ohne 2D-Plan: ok", a.get("ok") is True and "grundriss" not in a, sorted(a))
pruef("Antwort enthaelt keine Kamera", "camera" not in json.dumps(a))
pruef("Zustaende nur der Punkte", sorted(a["zustaende"]) == ["media_player.verstaerker"], a["zustaende"])
pruef("Saugroboter: Etage eg, Raum wohnzimmer, aktiv", a["sauger"] == {"etage": "eg", "raum": "wohnzimmer", "aktiv": True}, a["sauger"])
ZS[2]["state"] = "docked"
pruef("Saugroboter in der Station: nicht aktiv", gr.antwort(None, None, ZS, f)["sauger"]["aktiv"] is False)
ZS[3]["state"] = "Obergeschoss"
pruef("Andere Karte ohne passenden Raum: kein Saugroboter-Punkt", gr.antwort(None, None, ZS, f)["sauger"] is None)
gr.setze_sauger("vacuum.robbi", "sensor.robbi_raum", "select.robbi_karte")
ZR = [ha("vacuum.robbi", "returning"), ha("select.robbi_karte", "Erdgeschoss"), ha("sensor.robbi_raum", "Wohnzimmer")]
pruef("Saugroboter mit eigenen Kennungen (setze_sauger)", gr.sauger_puppenhaus(f, {s["entity_id"]: s for s in ZR})
      == {"etage": "eg", "raum": "wohnzimmer", "aktiv": True})
gr.setze_sauger(*VORGABE)
pruef("Bilder nur mit festem Namen", gr.bild_datei(T2, "eg_puppenhaus.jpg") == (os.path.join(O2, "eg_puppenhaus.jpg"), "image/jpeg")
      and gr.bild_datei(T2, "../foto.json")[0] is None and gr.bild_datei(T2, "foto.json")[0] is None
      and gr.bild_datei(T2, "eg_fehlt.jpg")[0] is None and gr.bild_datei(T2, None)[0] is None)

# ---------------------------------------------------------------- Foto-Projektion aufs 3D-Haus (foto.json "projektion")
T3, O3 = ordner()
for n in ("eg_puppenhaus5.jpg", "eg_pj_r.jpg", "eg_pj_l.jpg", "eg_pj_h.jpg", "eg_pj_x.jpg"):
    bild(os.path.join(O3, n))
K = {"az": 0.9, "pol": 0.75, "dist": 14.5, "ziel": [0, 0, 0.1]}
PJ = {"art": "puppenhaus",
      "etagen": {"eg": {"name": "Erdgeschoss", "basis": "eg_puppenhaus5.jpg", "raeume": [], "punkte": []}},
      "projektion": {
          "eg": [{"bild": "eg_puppenhaus5.jpg", "kamera": {"az": 0, "pol": 0.7, "dist": 13.8, "ziel": [0, 0, 0.1]}},
                 {"bild": "eg_pj_r.jpg", "kamera": K},
                 {"bild": "../geheim.jpg", "kamera": K},                                   # Name ungueltig
                 {"bild": "eg_fehlt.jpg", "kamera": K},                                    # Datei fehlt
                 {"bild": "eg_pj_l.jpg", "kamera": {"az": "x", "pol": 0.75, "dist": 14.5, "ziel": [0, 0, 0]}},
                 {"bild": "eg_pj_h.jpg", "kamera": dict(K, ziel=[0, 0])}],                 # nach Platz 4 ohnehin weg
          "dg": [{"bild": "eg_pj_x.jpg", "kamera": K}],                                     # Etage gibt es nicht
          "kg": "kaputt"}}
schreib(os.path.join(O3, "foto.json"), PJ, 400)
f = gr.foto_laden(T3)
pj = (f or {}).get("projektion") or {}
pruef("Projektion: nur gueltige Eintraege der ersten vier", [p["bild"] for p in pj.get("eg", [])] == ["eg_puppenhaus5.jpg", "eg_pj_r.jpg"], pj)
pruef("Projektion: Kamera als Zahlen", pj.get("eg", [{}, {}])[1].get("kamera") == {"az": 0.9, "pol": 0.75, "dist": 14.5,
                                                                                  "ziel": [0.0, 0.0, 0.1]}, pj)
pruef("Projektion: fremde/kaputte Etagen weg", set(pj) == {"eg"}, pj)
pruef("Projektion: Kamera ausserhalb des Rahmens weg", gr._projektion({"eg": [{"bild": "eg_pj_r.jpg", "kamera": dict(K, pol=2)},
                                                                              {"bild": "eg_pj_r.jpg", "kamera": dict(K, dist=float("inf"))}]},
                                                                       {"eg": {}}, lambda n: True) == {})
HK = {"etagen": {"eg": {"name": "EG"}}}
a = gr.antwort(None, None, [], f, HK)
pruef("Antwort traegt projektion neben haus3d", a.get("projektion") == pj and a.get("haus3d") == HK, sorted(a))
pruef("ohne 3D-Haus keine projektion", "projektion" not in gr.antwort(None, None, [], f, None))
PJ.pop("projektion")
schreib(os.path.join(O3, "foto.json"), PJ, 401)
f3 = gr.foto_laden(T3)
pruef("ohne Eintrag kein Feld projektion", f3 is not None and "projektion" not in f3, f3)

# ---------------------------------------------------------------- Foto-Grundriss (Ebenen ueber einem Basisbild)
T4, O4 = ordner()
for n in ("eg_aus.jpg", "eg_an.jpg", "og_aus.jpg"):
    bild(os.path.join(O4, n))
schreib(os.path.join(T4, "geheim.txt"), "nicht ausliefern")
AB = {"s": 100.0, "cx": 512, "cy": 512, "groesse": 1024}
FG = {"etagen": {"eg": {"basis": "eg_aus.jpg", "abbildung": AB, "ebenen": [
          {"id": "s16", "raum": "s16", "bild": "eg_an.jpg", "entitaeten": ["switch.kueche_licht", "camera.babyfon", 5]},
          {"id": "x", "raum": "s16", "bild": "../geheim.txt", "entitaeten": []},
          {"id": "y", "raum": "s17", "bild": "eg_fehlt.jpg", "entitaeten": ["light.y"]}]},
      "og": {"basis": "og_aus.jpg", "abbildung": {"s": "gross"}, "ebenen": []},
      "kg": {"basis": "kg_fehlt.jpg", "abbildung": AB, "ebenen": []}}}
schreib(os.path.join(O4, "foto.json"), FG, 500)
fl = gr.foto_laden(T4)
pruef("Foto-Grundriss: nur Etagen mit Basisbild und vollstaendiger Abbildung", sorted(fl["etagen"]) == ["eg"], fl)
pruef("Foto-Grundriss: ungueltiger Bildname und fehlendes Bild fallen weg, Tabu-Entitaet auch",
      [x["id"] for x in fl["etagen"]["eg"]["ebenen"]] == ["s16"] and fl["etagen"]["eg"]["ebenen"][0]["entitaeten"] == ["switch.kueche_licht"],
      fl["etagen"]["eg"]["ebenen"])
pruef("Foto-Grundriss: kein Puppenhaus", not gr.ist_puppenhaus(fl))
pruef("entitaeten() nimmt die Licht-Entitaeten der Ebenen mit", gr.entitaeten({}, fl) == {"switch.kueche_licht"})
schreib(os.path.join(O4, "foto.json"), "[kaputt", 501)
pruef("Foto-Grundriss: kaputtes JSON -> None", gr.foto_laden(T4) is None)

# ---------------------------------------------------------------- 2D-Plan aus Saugroboter-Karten (grundriss.json, platzierung.json)
G = {"etagen": [
    {"id": "kg", "name": "Keller", "ebene": -1, "raeume": [
        {"id": "keller", "name": "Keller", "polygon": R(-4, -2, 4, 2), "mitte": [0, 0], "schematisch": True}]},
    {"id": "eg", "name": "Erdgeschoss", "ebene": 0, "raeume": [
        {"id": "s16", "name": "Küche", "polygon": R(-4, -2, -0.5, 2), "mitte": [-2.25, 0], "flaeche_m2": 14.0},
        {"id": "s17", "name": "Wohnzimmer", "polygon": R(-0.4, -2, 4, 2), "mitte": [1.8, 0], "flaeche_m2": 17.6}]},
    {"id": "og", "name": "Obergeschoss", "ebene": 1, "raeume": [
        {"id": "s18", "name": "Flur", "polygon": R(-4, -2, 0, 2), "mitte": [-2, 0], "flaeche_m2": 16.0},
        {"id": "s19", "name": "Bad", "polygon": R(0, -2, 4, 2), "mitte": [2, 0], "flaeche_m2": 16.0}]}],
    "flaechen": {"wohnzimmer": {"etage": "eg", "raum": "s17", "name": "Wohnzimmer"},
                 "hausflur": {"etage": "og", "raum": "s18", "name": "Hausflur"},
                 "kinderzimmer": {"etage": None, "raum": None, "name": "Kinderzimmer"}}}
P = {"version": 1, "eintraege": {
        "switch.tv_ecke": {"name": "TV-Ecke", "symbol": "steckdose", "etage": "eg", "raum": "s17", "x": 1.8, "y": 0,
                           "werte": ["sensor.tv_ecke_leistung"], "auto": True},
        "light.stehlampe": {"name": "Stehlampe", "symbol": "licht", "etage": "eg", "raum": "s17", "x": 2, "y": 1, "auto": True},
        "light.leselampe": {"name": "Leselampe", "symbol": "licht", "etage": "og", "raum": "s18", "x": -2, "y": 1, "auto": True},
        "climate.heizung": {"name": "Heizung", "symbol": "heizung", "etage": "kg", "raum": "keller", "x": 0, "y": 0, "auto": True}},
     "unplatziert": {"switch.steckdose_pc": {"name": "Steckdose PC", "symbol": "steckdose", "grund": "kein Bereich"}}}
T5 = tempfile.mkdtemp(prefix="grundriss-2d-")
atexit.register(shutil.rmtree, T5, True)
pruef("2D-Plan: ohne Dateien (None, None)", gr.laden(T5) == (None, None))
schreib(os.path.join(T5, "grundriss.json"), G, 600)
gr.speichern(T5, P)
pruef("speichern: Datei nur fuer den Eigentuemer (600)", stat.S_IMODE(os.stat(os.path.join(T5, "platzierung.json")).st_mode) == 0o600)
g2, p2 = gr.laden(T5)
pruef("laden: Plan und Platzierung zurueck", g2 == G and p2 == P)
pruef("Raum finden: 'Flur oben' -> OG, 'Bad', 'Küche', HA-Bereich 'Hausflur', 'Keller'",
      (gr.raum_finden(G, "Flur oben"), gr.raum_finden(G, "Bad"), gr.raum_finden(G, "Küche"), gr.raum_finden(G, "Hausflur"),
       gr.raum_finden(G, "Keller")) == (("og", "s18"), ("og", "s19"), ("eg", "s16"), ("og", "s18"), ("kg", "keller")))
pruef("Raum finden: unbekannt -> None", gr.raum_finden(G, "Dachboden") is None and gr.raum_finden(G, "Kinderzimmer") is None)
pruef("Geraet finden: Kennung, Name, Teilwort, mehrdeutig", gr.entitaet_finden(P, "climate.heizung") == ("climate.heizung", [])
      and gr.entitaet_finden(P, "tv-ecke") == ("switch.tv_ecke", []) and gr.entitaet_finden(P, "steckdose pc")[0] == "switch.steckdose_pc"
      and gr.entitaet_finden(P, "lampe")[0] is None and sorted(gr.entitaet_finden(P, "lampe")[1]) == ["light.leselampe", "light.stehlampe"])
r17 = G["etagen"][1]["raeume"][1]
pruef("Lagewort: Mitte und Unsinn -> Raummitte", gr.lage_punkt(r17, "Mitte") == (1.8, 0) and gr.lage_punkt(r17, "irgendwo") == (1.8, 0))
lx, ly = gr.lage_punkt(r17, "links")
pruef("Lagewort: links -> links der Mitte, im Raum", lx < 1.8 and ly == 0 and gr._innen(r17["polygon"], lx, ly), (lx, ly))
ok_, msg, P2 = gr.verschieben(G, P, "Steckdose PC", "Wohnzimmer", "rechts oben")
neu = P2["eintraege"].get("switch.steckdose_pc", {})
pruef("Verschieben: aus 'ohne Platz' in den Raum, rechts oben, auto false", ok_ and neu.get("auto") is False and neu["raum"] == "s17"
      and neu["x"] > 1.8 and neu["y"] < 0 and gr._innen(r17["polygon"], neu["x"], neu["y"]) and "grund" not in neu
      and "switch.steckdose_pc" not in P2["unplatziert"] and msg == "Steckdose PC steht jetzt im Grundriss: Wohnzimmer, rechts oben.",
      (msg, neu))
pruef("Verschieben: Ausgangsdaten unveraendert", "switch.steckdose_pc" in P["unplatziert"] and "switch.steckdose_pc" not in P["eintraege"])
ok_, msg, _ = gr.verschieben(G, P, "Stehlampe", x=3.5, y=-1.5)
pruef("Verschieben: Punkt im bisherigen Raum, Lage Mitte im Text", ok_ and msg.endswith("Wohnzimmer, Mitte."), msg)
pruef("Verschieben: Punkt ausserhalb abgelehnt", gr.verschieben(G, P, "Stehlampe", x=9, y=9)[1] == "Der Punkt liegt nicht im Raum Wohnzimmer.")
pruef("Verschieben: unbekanntes Geraet", gr.verschieben(G, P, "Gibtsnicht", "Wohnzimmer")[1] == "Kein Gerät im Grundriss heißt so.")
pruef("Verschieben: mehrdeutig nennt Kandidaten", gr.verschieben(G, P, "lampe", "Bad")[1].startswith("Mehrere passen: "))
pruef("Verschieben: unbekannter Raum", gr.verschieben(G, P, "TV-Ecke", "Dachboden")[1] == "Den Raum Dachboden kenne ich im Grundriss nicht.")
pruef("Verschieben: ohne Raum und ohne bisherigen Platz", gr.verschieben(G, P, "Steckdose PC")[1] == "Sag mir, in welchem Raum es steht.")
PT = json.loads(json.dumps(P2))
PT["eintraege"]["camera.babyfon"] = {"name": "Babyfon", "symbol": "sensor", "etage": "eg", "raum": "s17", "x": 0, "y": 0, "auto": False}
pruef("Verschieben: Tabu, auch von Hand eingetragen", gr.verschieben(G, PT, "camera.babyfon", "Bad")[1] == "Das zeige ich im Grundriss nicht.")
ZP = [ha("switch.tv_ecke", "on"), ha("sensor.tv_ecke_leistung", "143.2", device_class="power", unit_of_measurement="W"),
      ha("camera.babyfon", "idle", access_token="geheim"), ha("sensor.fremd", "1"), ha("climate.heizung", "heat", temperature=21),
      ha(gr.SAUGER_KARTE, "Erdgeschoss"), ha(gr.SAUGER_RAUM, "Wohnzimmer")]
A = gr.antwort(G, PT, ZP)
roh = json.dumps(A)
pruef("2D-Antwort: kein Babyfon, kein Token, keine fremden Entitaeten", "babyfon" not in roh and "geheim" not in roh
      and "sensor.fremd" not in A["zustaende"] and A["ok"] is True, sorted(A["zustaende"]))
pruef("2D-Antwort: Werte-Entitaeten mit Einheit", A["zustaende"].get("sensor.tv_ecke_leistung") == {"s": "143.2", "e": "W"},
      A["zustaende"].get("sensor.tv_ecke_leistung"))
pruef("2D-Antwort: Saugroboter nur, wenn er im Plan steht", A["sauger"] is None)
PT["eintraege"][gr.SAUGER] = {"name": "Saugroboter", "symbol": "sauger", "etage": "eg", "raum": "s17", "x": 0, "y": 0, "auto": True}
pruef("2D-Antwort: Saugroboter ueber Karte und Raum", gr.antwort(G, PT, ZP)["sauger"] == {"etage": "eg", "raum": "s17"})
pruef("2D-Antwort: mit 3D-Haus zusaetzlich haus3d", gr.antwort(G, PT, ZP, None, h).get("haus3d") == h)
pruef("2D-Plan ohne Platzierung: ok false", gr.antwort(G, None, ZP)["ok"] is False)
pruef("entitaeten(): Werte dabei, Tabu nicht", gr.entitaeten(PT) == {"switch.tv_ecke", "sensor.tv_ecke_leistung", "light.stehlampe",
                                                                    "light.leselampe", "climate.heizung", "switch.steckdose_pc", gr.SAUGER})
txt = gr.beschreiben(G, P2, ZP)
pruef("Beschreiben: Raeume je Etage mit Geraeten und Zustand", "Erdgeschoss, Wohnzimmer (17.6 m²): " in txt and "TV-Ecke (on)" in txt
      and "Keller, Keller (? m², schematisch): Heizung (heat)" in txt and "Obergeschoss, Bad (16.0 m²): keine Geräte" in txt, txt)
pruef("Beschreiben: nur ein Raum, unbekannter Raum", gr.beschreiben(G, P, ZP, "Bad") == "Obergeschoss, Bad (16.0 m²): keine Geräte"
      and gr.beschreiben(G, P, ZP, "Dachboden") == "Den Raum Dachboden kenne ich im Grundriss nicht.")
pruef("Beschreiben: Geraete ohne Platz am Ende", gr.beschreiben(G, P).endswith("Ohne Platz im Grundriss: Steckdose PC"))

# ---------------------------------------------------------------- Englisch (setze_sprache)
gr.setze_sprache("en")
try:
    pruef("en: Meldungen des Geraete-Menues", (sp(M, "camera.schlafzimmer", "turn_on", None)[1], sp(M, "media_player.irgendwas", "turn_on", None)[1],
                                              sp(M, V, "play_media", {})[1], sp(M, V, "volume_set", {"x": 1})[1], sp(M, V, "volume_mute", {})[1],
                                              sp(M, V, "volume_mute", {"is_volume_muted": 0})[1], sp(M, V, "volume_set", {"volume_level": 2})[1])
          == ("This device does not exist here.", "This device is not in the 3D house.", "This device cannot do that.", "Invalid setting.",
              "Missing: is_volume_muted.", "Invalid value for is_volume_muted.", "volume_level only goes from 0 to 1."))
    pruef("en: kein Grundriss", gr.antwort(None, None, [])["fehler"] == "No floor plan yet (daten/grundriss-foto/haus3d.json is missing).")
    pruef("en: Umstellen", gr.verschieben(G, P, "Stehlampe", x=3.5, y=-1.5)[1] == "Stehlampe is now in the floor plan: Wohnzimmer, centre."
          and gr.verschieben(G, P, "Gibtsnicht", "Bad")[1] == "No device in the floor plan has that name."
          and gr.verschieben(G, P, "lampe", "Bad")[1].startswith("Several match: ")
          and gr.verschieben(G, P, "TV-Ecke", "Dachboden")[1] == "I do not know the room Dachboden in the floor plan."
          and gr.verschieben(G, P, "Steckdose PC")[1] == "Tell me which room it is in."
          and gr.verschieben(G, P, "Stehlampe", x=9, y=9)[1] == "That point is not inside the room Wohnzimmer."
          and gr.verschieben(G, PT, "camera.babyfon", "Bad")[1] == "I do not show that in the floor plan.")
    te = gr.beschreiben(G, P)
    pruef("en: Beschreiben", "(? m², schematic)" in te and "Bad (16.0 m²): no devices" in te
          and te.endswith("Not placed in the floor plan: Steckdose PC"), te)
finally:
    gr.setze_sprache("de")
pruef("zurueck auf Deutsch", sp(M, V, "play_media", {})[1] == "Das geht an diesem Gerät nicht.")

# ---------------------------------------------------------------- Erfundenes Beispielhaus (Vorlage fuer das eigene Haus)
SUCHE = [os.path.join(os.path.dirname(HIER), "spiegel", "grundriss"),    # Repo: tests/ neben spiegel/grundriss/
         os.path.join(os.path.dirname(HIER), "grundriss"),               # Vorlage: vorlagen/bruecke/ neben vorlagen/grundriss/
         os.path.join(HIER, "grundriss"),                                # Projekt: einrichtung/ mit Unterordner grundriss/
         HIER]
BEISPIEL = erzeuger = None
for d in SUCHE:
    j = os.path.join(d, "beispiel-haus3d.json")
    if BEISPIEL is None and os.path.isfile(j):
        BEISPIEL = json.load(open(j, encoding="utf-8"))
        print("      Beispielhaus:", os.path.relpath(j, os.path.dirname(HIER)))
    if erzeuger is None and os.path.isfile(os.path.join(d, "beispielhaus_erzeugen.py")):
        sys.path.insert(0, d)
        sys.dont_write_bytecode = True       # kein __pycache__ im Beispielordner
        import beispielhaus_erzeugen as erzeuger  # noqa: E402
        sys.path.remove(d)
if erzeuger is not None:
    if BEISPIEL is None:
        BEISPIEL = json.loads(json.dumps(erzeuger.AUSGABE))
        print("      Beispielhaus: aus beispielhaus_erzeugen.AUSGABE")
    else:
        pruef("Beispielhaus: JSON passt zum Erzeuger (sonst python3 beispielhaus_erzeugen.py)",
              BEISPIEL == json.loads(json.dumps(erzeuger.AUSGABE)))
if BEISPIEL is None:
    print("UEBERSPRUNGEN Beispielhaus: weder beispiel-haus3d.json noch beispielhaus_erzeugen.py gefunden (gesucht in %s)"
          % ", ".join(os.path.relpath(d, os.path.dirname(HIER)) for d in SUCHE))
else:
    roh = BEISPIEL["haus3d"]
    T6, O6 = ordner()
    schreib(os.path.join(O6, "haus3d.json"), roh, 700)
    hb = gr.haus3d_laden(T6)
    pruef("Beispielhaus: haus3d_laden nimmt es an, alle Etagen", hb is not None and sorted(hb["etagen"]) == sorted(roh["etagen"]),
          hb and sorted(hb["etagen"]))
    verloren, anders = [], []
    for eid, e in roh["etagen"].items():
        Eb = hb["etagen"][eid]
        for teil in ("raeume", "oeffnungen", "treppen", "moebel", "geraete", "gelaender"):
            a_, b_ = e.get(teil) or [], Eb.get(teil) or []
            if len(a_) != len(b_):
                verloren.append("%s.%s: %d -> %d" % (eid, teil, len(a_), len(b_)))
                continue
            for x, y in zip(a_, b_):
                if isinstance(x, dict):
                    verloren += ["%s.%s.%s" % (eid, teil, f_) for f_ in sorted(set(x) - set(y))]
                    anders += ["%s.%s.%s=%r" % (eid, teil, f_, x[f_]) for f_ in sorted(set(x) & set(y))
                               if x[f_] != y[f_] and not (isinstance(x[f_], (int, float)) and float(x[f_]) == float(y[f_]))]
                elif x != y:
                    anders.append("%s.%s" % (eid, teil))
    pruef("Beispielhaus: keine Raeume, Oeffnungen, Treppen, Moebel, Geraete oder Gelaender und keines ihrer Felder geht verloren",
          not verloren, verloren)
    pruef("Beispielhaus: geaendert wird nur das Symbol punkt (wird leer, der Viewer zeigt dann ohnehin den Punkt)",
          all(x.endswith(".symbol='punkt'") for x in anders), anders)
    weg_oben = sorted(set(roh) - set(hb))
    weg_etage = sorted({k for e in roh["etagen"].values() for k in e} - {k for e in hb["etagen"].values() for k in e})
    pruef("Beispielhaus: verworfen werden nur version, hinweis und loecher (liest haus3d.js nicht)",
          set(weg_oben) <= {"version", "hinweis"} and set(weg_etage) <= {"loecher"}, (weg_oben, weg_etage))
    if weg_etage:
        print("      HINWEIS: haus3d_laden verwirft die Etagenfelder %s des Beispielhauses (haus3d.js liest sie derzeit nicht)"
              % ", ".join(weg_etage))
    EG, OG = hb["etagen"].get("eg", {}), hb["etagen"].get("og", {})
    alle_m = [m for e in hb["etagen"].values() for m in e["moebel"]]
    pruef("Beispielhaus: Felder fuer den Viewer da (bruestung, gelaender, monitore, stuehle, stuhlfarbe, mit, geraet, an_von, an_ab)",
          any("bruestung" in o_ for o_ in EG.get("oeffnungen", [])) and OG.get("gelaender") == roh["etagen"]["og"]["gelaender"]
          and EG.get("treppen", [{}])[0].get("gelaender") == "sued"
          and any(m.get("monitore") == 2 for m in alle_m) and any(m.get("stuehle") == 6 and m.get("stuhlfarbe") for m in alle_m)
          and {m.get("mit") for m in alle_m} >= {"kuehlschrank", "backofen", "kochfeld"}
          and sum(1 for m in alle_m if m.get("geraet")) == sum(1 for e in roh["etagen"].values() for m in e["moebel"] if m.get("geraet"))
          and all(g_.get("an_von") in g_["entitaeten"] and isinstance(g_.get("an_ab"), float)
                  for e in hb["etagen"].values() for g_ in e["geraete"] if "an_von" in g_))
    pruef("Beispielhaus: jeder Bildschirm (moebel.geraet) zeigt auf ein Geraet derselben Etage",
          all(m["geraet"] in {g_["id"] for g_ in e["geraete"]} for e in hb["etagen"].values() for m in e["moebel"] if m.get("geraet")))
    pruef("Beispielhaus: Oeffnungstypen und Moebeltypen bekannt", all(o_["typ"] in gr.OEFFNUNGEN for e in hb["etagen"].values()
                                                                       for o_ in e["oeffnungen"]) and all(gr.WORT.fullmatch(m["typ"]) for m in alle_m))
    pruef("Beispielhaus: keine Tabu-Entitaet", not any(gr.TABU.search(x) for x in gr.entitaeten({}, None, hb)))
    ZB = BEISPIEL.get("zustaende") or {}
    alle_e = {x for e in hb["etagen"].values() for g_ in e["geraete"] for x in g_["entitaeten"]}
    pruef("Beispielhaus: zu jeder Geraete-Entitaet ein Beispielzustand", alle_e == set(ZB), sorted(alle_e ^ set(ZB)))
    HA = [ha(eid, z["s"], **dict(z.get("a") or {}, friendly_name=z.get("n"), **({"unit_of_measurement": z["e"]} if "e" in z else {})))
          for eid, z in ZB.items()] + [ha("camera.babyfon", "idle"), ha("sensor.fremd", "1")]
    ab = gr.antwort(None, None, HA, None, hb)
    pruef("Beispielhaus: antwort() ok mit haus3d, ohne Kamera und Fremdes", ab["ok"] is True and ab["haus3d"] == hb
          and "camera.babyfon" not in ab["zustaende"] and "sensor.fremd" not in ab["zustaende"])
    pruef("Beispielhaus: kurz() ergibt genau die Beispielzustaende (Format wie /v1/grundriss)", ab["zustaende"] == ZB,
          [k_ for k_ in ZB if ab["zustaende"].get(k_) != ZB[k_]])
    pruef("Beispielhaus ohne foto.json: keine Saugerposition (die kommt aus dem Puppenhaus)", ab["sauger"] is None)
    ph = {"art": "puppenhaus", "etagen": {"eg": {"name": "Erdgeschoss", "basis": "eg_puppenhaus.jpg", "punkte": [],
          "raeume": [{"id": r_["id"], "name": r_["name"], "x": 0.5, "y": 0.5, "roborock": r_["name"]} for r_ in EG.get("raeume", [])]}}}
    bild(os.path.join(O6, "eg_puppenhaus.jpg"))
    schreib(os.path.join(O6, "foto.json"), ph, 701)
    zs = HA + [ha(gr.SAUGER_KARTE, "Erdgeschoss"), ha(gr.SAUGER_RAUM, "Wohnzimmer")]
    ab2 = gr.antwort(None, None, zs, gr.foto_laden(T6), hb)
    pruef("Beispielhaus mit Puppenhaus-Raeumen: Saugerposition wie in beispiel-haus3d.json", ab2["sauger"] == BEISPIEL.get("sauger"),
          (ab2["sauger"], BEISPIEL.get("sauger")))
    pruef("Beispielhaus: Geraete-Menue (Licht, Lautstaerke, Heizung, Warmwasser, Sauger)", all((
        sp(hb, "light.wohnzimmer", "turn_on", {"brightness_pct": 50})[0], sp(hb, "media_player.wohnzimmer_tv", "volume_set", {"volume_level": 0.2})[0],
        sp(hb, "climate.heizung", "set_temperature", {"temperature": 21})[0], sp(hb, "water_heater.warmwasser", "set_temperature", {"temperature": 50})[0],
        not sp(hb, "water_heater.warmwasser", "set_temperature", {"temperature": 70})[0], sp(hb, "vacuum.saugroboter", "start", None)[0],
        not sp(hb, "sensor.pc_leistung", "turn_on", None)[0])))
print("Grundriss: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
