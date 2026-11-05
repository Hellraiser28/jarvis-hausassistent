#!/usr/bin/env python3
"""Beispielhaus fuer die 3D-Hausansicht (seit 0.6): ein erfundenes Einfamilienhaus, 10 x 8 m, zwei Etagen.

Dient zwei Zwecken: Vorschau und Bildschirmfotos ohne echtes Zuhause, und als Muster, wie Claude beim Einrichten dein
eigenes Haus beschreibt (Bauanleitung, Abschnitt "3D-Haus"). Ausgabe: beispiel-haus3d.json neben diesem Skript, im
Format, das /v1/grundriss liefert ({ok, haus3d, zustaende, sauger}).

Koordinaten in Metern: x nach Osten, y nach Sueden (Norden ist -y), Ursprung in der Hausmitte. Raeume sind Polygone,
die sich nicht ueberlappen; Aussenwaende entstehen aus den Raumkanten. Oeffnungen liegen auf einer Wand (von/bis),
Moebel stehen mit Mitte (x, y), Breite b, Tiefe t und Drehung in Grad. Geraete verbinden einen Punkt im Haus mit
Home-Assistant-Entitaeten; alle Kennungen hier sind erfunden.
    python3 beispielhaus_erzeugen.py
"""
import json
import os


def R(rid, name, boden, poly, **k):
    return dict({"id": rid, "name": name, "boden": boden, "poly": poly}, **k)


def O(typ, von, bis, **k):
    return dict({"typ": typ, "von": von, "bis": bis}, **k)


def M(typ, x, y, b, t, drehung=0, **k):
    return dict({"typ": typ, "x": x, "y": y, "b": b, "t": t, "drehung": drehung}, **k)


def G(gid, name, symbol, x, y, z, entitaeten, **k):
    return dict({"id": gid, "name": name, "symbol": symbol, "x": x, "y": y, "z": z, "entitaeten": entitaeten}, **k)


def rechteck(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


# ================================================================== Erdgeschoss
EG = {
    "name": "Erdgeschoss", "boden": 0.0, "hoehe": 2.6,
    "raeume": [
        R("flur", "Flur", "fliese_dunkel", rechteck(-5.0, -4.0, -0.5, -0.5)),
        R("wc", "WC", "fliese_dunkel", rechteck(-5.0, -0.5, -3.3, 1.5), wand="hell"),
        R("hwr", "Hauswirtschaft", "beton", rechteck(-5.0, 1.5, -3.3, 4.0)),
        R("kueche", "Küche", "fliese_dunkel", rechteck(-3.3, -0.5, -0.5, 4.0)),
        R("wohnen", "Wohnzimmer", "holz", rechteck(-0.5, -4.0, 5.0, 1.0)),
        R("essen", "Essen", "holz", rechteck(-0.5, 1.0, 5.0, 4.0)),
    ],
    "oeffnungen": [
        O("haustuer", [-5.0, -2.4], [-5.0, -1.4]),
        O("tuer", [-4.4, -0.5], [-3.6, -0.5]),
        O("durchgang", [-2.6, -0.5], [-1.6, -0.5]),
        O("tuer", [-0.5, -2.6], [-0.5, -1.7]),
        O("tuer", [-3.3, 2.6], [-3.3, 3.4]),
        O("durchgang", [-0.5, 1.8], [-0.5, 3.4]),
        O("offen", [0.2, 1.0], [4.3, 1.0]),
        O("terrassentuer", [5.0, -2.6], [5.0, -0.8]),
        O("fenster", [1.0, -4.0], [2.4, -4.0]),
        O("fenster", [3.0, -4.0], [4.4, -4.0]),
        O("fenster", [0.6, 4.0], [2.0, 4.0]),
        O("fenster", [3.0, 4.0], [4.4, 4.0]),
        O("fenster", [-2.8, 4.0], [-1.2, 4.0], bruestung=1.0),
        O("fenster", [-5.0, 0.2], [-5.0, 0.9], bruestung=1.4),
        O("fenster", [-5.0, 2.6], [-5.0, 3.4], bruestung=1.2),
    ],
    # Gerade Treppe an der Nordwand des Flurs: unten im Osten, oben im Westen (Treppenloch im OG darueber)
    "treppen": [{"von": [-1.3, -3.5], "bis": [-4.3, -3.5], "breite": 1.0, "hoehe": 2.85, "stufen": 13, "gelaender": "sued"}],
    "moebel": [
        # Wohnzimmer
        M("teppich", 1.6, -0.6, 2.6, 2.0),
        M("ecksofa", 2.9, -0.8, 2.8, 2.0, 270, farbe="grau"),
        M("couchtisch", 1.5, -0.4, 1.1, 0.6, 90, farbe="eiche"),
        M("lowboard", -0.3, -0.2, 1.8, 0.4, 90, farbe="anthrazit"),
        M("fernseher", -0.33, -0.2, 1.4, 0.06, 90, z=0.85, hoehe=0.8, geraet="tv_wohnzimmer"),
        M("bucherregal", 4.78, -3.3, 1.0, 0.35, 270, farbe="eiche"),
        M("klimageraet", 2.7, -3.86, 0.9, 0.25, 0, z=2.15),
        M("pflanze", 4.6, 0.6, 0.45, 0.45),
        # Essen
        M("esstisch", 2.3, 2.6, 1.8, 0.9, 0, farbe="eiche", stuehle=6, stuhlfarbe="anthrazit"),
        M("sideboard", 4.78, 2.6, 1.6, 0.45, 270, farbe="weiss"),
        M("pflanze", -0.15, 3.7, 0.4, 0.4),
        # Kueche
        M("kuechenzeile", -1.9, 3.68, 2.6, 0.62, 180, farbe="weiss"),
        M("hochschrank", -3.0, 0.4, 0.6, 0.62, 90, farbe="weiss", mit="kuehlschrank"),
        M("hochschrank", -3.0, 1.0, 0.6, 0.62, 90, farbe="weiss", mit="backofen"),
        M("insel", -1.9, 1.6, 1.6, 0.9, 0, farbe="anthrazit", mit="kochfeld"),
        # Flur
        M("garderobe", -4.8, -3.3, 1.0, 0.35, 90),
        M("kommode", -4.8, -0.95, 0.8, 0.4, 90, farbe="weiss"),
        # WC
        M("wc", -4.7, 1.0, 0.4, 0.55, 90),
        M("waschtisch", -3.55, 0.6, 0.5, 0.4, 270),
        # Hauswirtschaft
        M("waschmaschine", -4.65, 2.0, 0.6, 0.6, 90),
        M("trockner", -4.65, 3.75, 0.6, 0.6, 90),
        M("regal", -3.6, 3.75, 0.9, 0.4, 180, farbe="metall"),
    ],
    "geraete": [
        G("tv_wohnzimmer", "Fernseher Wohnzimmer", "tv", -0.33, -0.2, 0.85,
          ["media_player.wohnzimmer_tv", "switch.tv_ecke", "sensor.tv_ecke_leistung"], an_von="sensor.tv_ecke_leistung", an_ab=15),
        G("licht_wohnen", "Licht Wohnzimmer", "punkt", 1.8, -1.6, 2.3, ["light.wohnzimmer"]),
        G("klima", "Klimaanlage", "klima", 2.7, -3.75, 2.1, ["climate.wohnzimmer"]),
        G("licht_essen", "Licht Esstisch", "punkt", 2.3, 2.6, 2.0, ["light.esstisch"]),
        G("lautsprecher_kueche", "Lautsprecher Küche", "lautsprecher", -2.9, 3.6, 1.0, ["media_player.kueche"]),
        G("waschmaschine", "Waschmaschine", "punkt", -4.65, 2.0, 0.5,
          ["switch.waschmaschine", "sensor.waschmaschine_leistung"], an_von="sensor.waschmaschine_leistung", an_ab=5),
        G("heizung", "Heizung", "heizung", -3.6, 3.75, 1.2, ["climate.heizung", "water_heater.warmwasser"]),
        G("sauger", "Saugroboter", "sauger", -3.9, 3.7, 0.15, ["vacuum.saugroboter"]),
    ],
}

# ================================================================== Obergeschoss
OG = {
    "name": "Obergeschoss", "boden": 2.85, "hoehe": 2.5,
    "raeume": [
        R("flur_og", "Flur", "holz", [[-5.0, -4.0], [-0.5, -4.0], [-0.5, 1.6], [-2.5, 1.6], [-2.5, -2.2], [-5.0, -2.2]]),
        R("bad", "Bad", "fliese_dunkel", rechteck(-5.0, -2.2, -2.5, 0.4), wand="hell"),
        R("kind", "Kinderzimmer", "holz", rechteck(-5.0, 0.4, -2.5, 4.0)),
        R("arbeiten", "Arbeitszimmer", "holz", rechteck(-2.5, 1.6, 1.0, 4.0)),
        R("schlafen", "Schlafzimmer", "holz", rechteck(-0.5, -4.0, 5.0, 1.6)),
        R("ankleide", "Ankleide", "holz", rechteck(1.0, 1.6, 5.0, 4.0)),
    ],
    "gelaender": [[[-4.3, -3.0], [-1.3, -3.0]], [[-1.3, -4.0], [-1.3, -3.0]]],
    "oeffnungen": [
        O("tuer", [-2.5, -1.6], [-2.5, -0.8]),
        O("tuer", [-2.5, 0.6], [-2.5, 1.4]),
        O("tuer", [-2.2, 1.6], [-1.4, 1.6]),
        O("tuer", [-0.5, -2.85], [-0.5, -2.15]),
        O("tuer", [3.4, 1.6], [4.2, 1.6]),
        O("fenster", [-5.0, -1.4], [-5.0, -0.6], bruestung=1.2),
        O("fenster", [-5.0, 1.6], [-5.0, 3.0]),
        O("fenster", [-4.4, 4.0], [-3.2, 4.0]),
        O("fenster", [-1.8, 4.0], [-0.2, 4.0]),
        O("fenster", [0.8, -4.0], [2.2, -4.0]),
        O("fenster", [3.0, -4.0], [4.4, -4.0]),
        O("fenster", [5.0, -2.0], [5.0, -0.6]),
        O("fenster", [5.0, 2.4], [5.0, 3.2]),
    ],
    "moebel": [
        # Schlafzimmer
        M("teppich", 2.4, -1.4, 2.6, 1.8),
        M("doppelbett", 2.4, -2.85, 1.8, 2.1, 0, farbe="grau"),
        M("nachttisch", 1.15, -3.7, 0.45, 0.4, 0, farbe="eiche"),
        M("nachttisch", 3.65, -3.7, 0.45, 0.4, 0, farbe="eiche"),
        M("kleiderschrank", -0.2, -0.4, 2.0, 0.6, 90, farbe="weiss"),
        M("kommode", 2.4, 1.35, 1.4, 0.45, 180, farbe="weiss"),
        M("fernseher", 2.4, 1.45, 1.1, 0.06, 180, z=0.95, hoehe=0.65, geraet="tv_schlafzimmer"),
        # Bad
        M("dusche", -4.5, -1.7, 0.9, 0.9),
        M("wc", -4.75, 0.0, 0.4, 0.55, 90),
        M("waschtisch", -3.3, -1.95, 0.8, 0.45, 0),
        M("spiegelschrank", -3.3, -2.1, 0.8, 0.15, 0, z=1.35),
        # Kinderzimmer
        M("teppich", -3.75, 2.4, 1.4, 1.0, 0, farbe="blau"),
        M("kinderbett", -4.5, 2.4, 0.9, 2.0, 0, farbe="weiss"),
        M("kleiderschrank", -4.2, 0.72, 1.2, 0.55, 0, farbe="weiss"),
        M("schreibtisch", -3.2, 3.68, 1.2, 0.6, 180, farbe="weiss"),
        M("kallax", -2.75, 2.4, 0.8, 0.4, 270, farbe="weiss"),
        # Arbeitszimmer
        M("schreibtisch", -0.8, 3.6, 1.6, 0.75, 180, farbe="eiche", monitore=2, geraet="pc"),
        M("buerostuhl", -0.8, 2.95, 0.6, 0.6, 180),
        M("regal", 0.78, 2.7, 1.2, 0.35, 270, farbe="eiche"),
        M("pflanze", -2.2, 3.7, 0.4, 0.4),
        # Ankleide
        M("kleiderschrank", 3.0, 3.68, 3.0, 0.6, 180, farbe="weiss"),
        M("kommode", 4.75, 2.6, 1.0, 0.45, 270, farbe="eiche"),
    ],
    "geraete": [
        G("tv_schlafzimmer", "Fernseher Schlafzimmer", "tv", 2.4, 1.45, 0.95, ["media_player.schlafzimmer_tv"]),
        G("licht_schlafen", "Licht Schlafzimmer", "punkt", 2.4, -1.2, 2.2, ["light.schlafzimmer"]),
        G("pc", "PC", "pc", -0.8, 3.6, 1.0, ["switch.pc_steckdose", "sensor.arbeitszimmer_pc_leistung"], an_von="sensor.arbeitszimmer_pc_leistung", an_ab=15),
        G("lautsprecher_kind", "Lautsprecher Kinderzimmer", "lautsprecher", -3.2, 3.7, 0.9, ["media_player.kinderzimmer"]),
        G("licht_kind", "Licht Kinderzimmer", "punkt", -3.75, 2.2, 2.2, ["light.kinderzimmer"]),
    ],
}

HAUS = {"art": "haus3d", "version": 1, "hinweis": "Erfundenes Beispielhaus (Jarvis 0.6). Alle Kennungen sind erfunden.",
        "umriss": [-5.0, -4.0, 5.0, 4.0], "nordwinkel": 0, "etagen": {"eg": EG, "og": OG}}

# Beispielzustaende wie /v1/grundriss sie liefert: s = Zustand, n = Anzeigename, e = Einheit, a = Attribute
ZUSTAENDE = {
    "media_player.wohnzimmer_tv": {"s": "playing", "n": "Fernseher Wohnzimmer",
                                   "a": {"app_name": "Mediathek", "media_title": "Naturdoku: Die Alpen", "volume_level": 0.3,
                                         "is_volume_muted": False, "supported_features": 152463}},
    "switch.tv_ecke": {"s": "on", "n": "TV-Ecke"},
    "sensor.tv_ecke_leistung": {"s": "142", "e": "W", "n": "TV-Ecke Leistung"},
    "light.wohnzimmer": {"s": "on", "n": "Licht Wohnzimmer", "a": {"brightness": 178}},
    "climate.wohnzimmer": {"s": "off", "n": "Klimaanlage", "a": {"current_temperature": 21.5, "temperature": 22,
                                                                   "hvac_modes": ["off", "cool", "heat", "dry", "fan_only", "auto"],
                                                                   "min_temp": 16, "max_temp": 30, "target_temp_step": 1}},
    "light.esstisch": {"s": "on", "n": "Licht Esstisch", "a": {"brightness": 230}},
    "media_player.kueche": {"s": "playing", "n": "Lautsprecher Küche",
                            "a": {"app_name": "Radio", "media_title": "Morgenmagazin", "volume_level": 0.25, "supported_features": 56253}},
    "switch.waschmaschine": {"s": "on", "n": "Waschmaschine"},
    "sensor.waschmaschine_leistung": {"s": "412", "e": "W", "n": "Waschmaschine Leistung"},
    "climate.heizung": {"s": "heat", "n": "Heizung", "a": {"current_temperature": 45, "temperature": 21, "hvac_modes": ["heat", "off"],
                                                           "min_temp": 3, "max_temp": 37, "target_temp_step": 1}},
    "water_heater.warmwasser": {"s": "eco", "n": "Warmwasser", "a": {"current_temperature": 49, "temperature": 50, "min_temp": 10, "max_temp": 60}},
    "vacuum.saugroboter": {"s": "cleaning", "n": "Saugroboter", "a": {"battery_level": 78, "fan_speed": "balanced"}},
    "media_player.schlafzimmer_tv": {"s": "off", "n": "Fernseher Schlafzimmer", "a": {"supported_features": 21437}},
    "light.schlafzimmer": {"s": "off", "n": "Licht Schlafzimmer"},
    "switch.pc_steckdose": {"s": "on", "n": "PC-Steckdose"},
    "sensor.arbeitszimmer_pc_leistung": {"s": "96", "e": "W", "n": "PC Leistung"},
    "media_player.kinderzimmer": {"s": "idle", "n": "Lautsprecher Kinderzimmer", "a": {"volume_level": 0.2, "supported_features": 56253}},
    "light.kinderzimmer": {"s": "on", "n": "Licht Kinderzimmer", "a": {"brightness": 120}},
}

AUSGABE = {"ok": True, "haus3d": HAUS, "zustaende": ZUSTAENDE,
           "sauger": {"aktiv": True, "etage": "eg", "raum": "wohnen"}, "stand": 1793899800}   # ein Abend, 18:30 Uhr

if __name__ == "__main__":
    ziel = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beispiel-haus3d.json")
    with open(ziel, "w", encoding="utf-8") as f:
        json.dump(AUSGABE, f, ensure_ascii=False, indent=1)
    n = {k: (len(e["raeume"]), len(e["moebel"]), len(e["geraete"])) for k, e in HAUS["etagen"].items()}
    print("geschrieben:", ziel, "| Raeume/Moebel/Geraete je Etage:", n)
