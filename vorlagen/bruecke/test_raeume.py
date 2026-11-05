#!/usr/bin/env python3
"""Baustein raeume.py (Raumkontext und Durchsagen 2.0, im Release seit 0.6) ohne Bruecke: Datei pruefen (Tabu fuer
Babyfon und Kameras), Raum erkennen, Kontextsatz, Durchsage planen (Echo, Music Assistant mit Ausweichplayer,
Satellit, Player, Einblendung, Nachtruhe, Antwortweg, Voice-PE-Flags, Zuruf-Ziel, Medien), ausfuehren, beschreiben,
englische Texte. Testordner statt echter Daten, HA ist eine Attrappe, keine Netzzugriffe."""
import copy
import json
import os
import shutil
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import raeume as ra  # noqa: E402

T = tempfile.mkdtemp(prefix="raeume-test-")
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


def wirft(f, *a):
    try:
        f(*a)
    except ra.Ungueltig as e:
        return str(e)
    return ""


def dienste(p):
    return [a["dienst"] for a in p["aufrufe"]]


# Beispiel fuer daten/raeume.json (so koennte ein Haushalt anfangen): Voice PE im Wohnzimmer noch nicht eingerichtet,
# Verstaerker nur auf Zuruf und bis zum Voice PE bei "ueberall", Kinderzimmer mit Box und vorbereiteter Einblendung.
BEISPIEL = {
    "version": 1,
    "raeume": {
        "wohnzimmer": {"name": "Wohnzimmer", "alias": ["stube", "esszimmer"], "bereich": "Wohnzimmer",
                       "hinweis_ohne_ausgabe": "Im Wohnzimmer gibt es noch keinen festen Lautsprecher. Auf Zuruf sage ich es über den Verstärker.",
                       "ausgabe": [{"art": "satellit", "entity": "assist_satellite.beispiel_voice_pe",
                                    "geraet": "Beispiel Voice PE", "voice_pe": True}]},
        "kueche": {"name": "Küche", "bereich": "Küche",
                   "ausgabe": [{"art": "echo", "notify": "notify.alexa_media_beispiel_kueche", "geraet": "Küche"}]},
        "kinderzimmer": {"name": "Kinderzimmer", "alias": ["mia", "mias zimmer"], "bereich": "Kinderzimmer",
                         "ausgabe": [{"art": "player", "entity": "media_player.beispiel_kinderbox", "nur_wenn_an": True},
                                     {"art": "einblendung", "notify": "notify.mobile_app_platzhalter_kinderzimmer",
                                      "platzhalter": True, "ersatz": True}]},
        "keller": {"name": "Keller", "bereich": "Keller", "ausgabe": []}},
    "geraete": {"Beispiel Voice PE": "wohnzimmer", "Küche": "kueche"},
    "zuruf": {"verstaerker": {"name": "Verstärker", "alias": ["receiver", "anlage"], "ausgabe": {
        "art": "ma", "entity": "media_player.beispiel_receiver_ma", "fallback": "media_player.beispiel_receiver_alt",
        "lautstaerke_fest": True}}},
    "ueberall": {"ausgabe": [
        {"art": "echo", "notify": "notify.alexa_media_beispiel_gruppe"},
        {"art": "satellit", "entity": "assist_satellite.beispiel_voice_pe", "voice_pe": True},
        {"art": "ma", "entity": "media_player.beispiel_receiver_ma", "fallback": "media_player.beispiel_receiver_alt",
         "bis_voice_pe": True, "nur_wenn_an": "media_player.beispiel_receiver", "lautstaerke_fest": True}]},
    "einstellungen": {"gong": True, "lautstaerke_ansage": 70, "voice_pe_aktiv": False, "ausblenden": ["internetzugang"]},
}

BASIS_KONF = {
    "version": 1,
    "raeume": {
        "wohnzimmer": {"name": "Wohnzimmer", "alias": ["stube", "esszimmer"], "bereich": "Wohnzimmer", "ausgabe": [
            {"art": "satellit", "entity": "assist_satellite.pe_wz", "geraet": "Voice PE Wohnzimmer", "voice_pe": True}],
            "hinweis_ohne_ausgabe": "Im Wohnzimmer gibt es noch keinen festen Lautsprecher, der Voice PE ist noch nicht eingerichtet. Auf Zuruf sage ich es über den Verstärker."},
        "buero": {"name": "Büro", "bereich": "Büro", "ausgabe": [
            {"art": "ma", "entity": "media_player.rx_ma", "fallback": "media_player.rx_alt"},
            {"art": "satellit", "entity": "assist_satellite.pe_bu", "geraet": "Voice PE Büro"}]},
        "kueche": {"name": "Küche", "bereich": "Küche", "ausgabe": [
            {"art": "echo", "notify": "notify.alexa_media_kueche", "geraet": "Küche"}]},
        "kinderzimmer": {"name": "Kinderzimmer", "alias": ["mia"], "bereich": "Kinderzimmer", "ausgabe": [
            {"art": "player", "entity": "media_player.cast_kind", "nur_wenn_an": True},
            {"art": "einblendung", "notify": "notify.mobile_app_mia_platzhalter", "platzhalter": True, "ersatz": True}]},
        "keller": {"name": "Keller", "bereich": "Keller", "ausgabe": []}},
    "geraete": {"Voice PE Wohnzimmer": "wohnzimmer", "Voice PE Büro": "buero", "Tablet Flur": "keller"},
    "zuruf": {"verstaerker": {"name": "Verstärker", "alias": ["receiver", "anlage"], "ausgabe": {
        "art": "ma", "entity": "media_player.rx_ma", "fallback": "media_player.rx_alt", "lautstaerke_fest": True}}},
    "ueberall": {"ausgabe": [{"art": "echo", "notify": "notify.alexa_media_gruppe"},
                             {"art": "satellit", "entity": "assist_satellite.pe_wz", "voice_pe": True},
                             {"art": "ma", "entity": "media_player.rx_ma", "bis_voice_pe": True, "nur_wenn_an": "media_player.rx_avr",
                              "lautstaerke_fest": True}]},
    "einstellungen": {"gong": True, "lautstaerke_ansage": 70, "ausblenden": ["internetzugang", "NAS"]},
}
k = ra.pruefen(BASIS_KONF)

# ---------------------------------------------------------------- Pruefung der Datei
pruef("Beispiel gueltig, Verstaerker nie fest im Wohnzimmer", all(a["art"] != "ma" for a in ra.pruefen(BEISPIEL)["raeume"]["wohnzimmer"]["ausgabe"]))
x = copy.deepcopy(BASIS_KONF)
x["raeume"]["kueche"]["ausgabe"].append({"art": "echo", "notify": "notify.alexa_media_baby_zimmer"})
pruef("Babyfon in der Datei abgelehnt", "tabu" in wirft(ra.pruefen, x))
x = copy.deepcopy(BASIS_KONF)
x["raeume"]["kueche"]["ausgabe"].append({"art": "player", "entity": "media_player.avent_monitor"})
pruef("Babyfon-Muster avent abgelehnt", "tabu" in wirft(ra.pruefen, x))
x = copy.deepcopy(BASIS_KONF)
x["raeume"]["keller"]["ausgabe"].append({"art": "player", "entity": "camera.flur"})
pruef("Kamera in der Datei abgelehnt", wirft(ra.pruefen, x) != "")
x = copy.deepcopy(BASIS_KONF)
x["ueberall"]["ausgabe"].append({"art": "ma", "entity": "media_player.rx_ma", "nur_wenn_an": "media_player.chuangmi_cam"})
pruef("Tabu auch in nur_wenn_an", "tabu" in wirft(ra.pruefen, x))
x = copy.deepcopy(BASIS_KONF)
x["geraete"]["Irgendwas"] = "gibtsnicht"
pruef("Geraet mit unbekanntem Raum", "unbekannten Raum" in wirft(ra.pruefen, x))
x = copy.deepcopy(BASIS_KONF)
x["raeume"]["ueberall"] = {"name": "X"}
pruef("Raumschluessel ueberall verboten", wirft(ra.pruefen, x) != "")
x = copy.deepcopy(BASIS_KONF)
x["raeume"]["kueche"]["ausgabe"] = [{"art": "echo", "notify": "light.kueche"}]
pruef("echo braucht notify.*", wirft(ra.pruefen, x) != "")
x = copy.deepcopy(BASIS_KONF)
x["raeume"]["kueche"]["ausgabe"] = [{"art": "lautsprecher", "entity": "media_player.x"}]
pruef("unbekannte art", "art muss" in wirft(ra.pruefen, x))
x = copy.deepcopy(BASIS_KONF)
x["einstellungen"]["lautstaerke_ansage"] = 150
pruef("Lautstaerke 150 abgelehnt", "1 bis 100" in wirft(ra.pruefen, x))
x = copy.deepcopy(BASIS_KONF)
x["zuruf"]["Gross"] = {"name": "x", "ausgabe": {"art": "echo", "notify": "notify.x"}}
pruef("zuruf-Schluessel nur a-z0-9_", "zuruf" in wirft(ra.pruefen, x))
pruef("Einstellungen uebernommen, ausblenden klein", k["einstellungen"] == {"gong": True, "lautstaerke_ansage": 70,
      "ausblenden": ["internetzugang", "nas"], "voice_pe_aktiv": False}, k["einstellungen"])
pruef("Aliasse normiert, laengste zuerst", k["raeume"]["wohnzimmer"]["alias"] == ["wohnzimmer", "esszimmer", "stube"]
      and k["zuruf"]["verstaerker"]["alias"] == ["verstaerker", "receiver", "anlage"], (k["raeume"]["wohnzimmer"]["alias"], k["zuruf"]))
pruef("ohne Datei: None, kein Fehler", ra.laden(T) == (None, None))
open(T + "/raeume.json", "w").write("{kaputt")
pruef("kaputte Datei: None mit Fehlertext", ra.laden(T)[0] is None and ra.laden(T)[1])
json.dump({"raeume": {}}, open(T + "/raeume.json", "w"))
pruef("leere Raeume: Fehlertext", ra.laden(T)[0] is None and "raeume" in ra.laden(T)[1])
json.dump(BASIS_KONF, open(T + "/raeume.json", "w"), ensure_ascii=False)
pruef("gueltige Datei: geladen", ra.laden(T)[0] == k and ra.laden(T)[1] is None)
pruef("Standard-ueberall = alle Ausgaben ohne Doppelte",
      len(ra.pruefen({"raeume": {"a": {"name": "A", "ausgabe": [{"art": "echo", "notify": "notify.x"}]},
                                  "b": {"name": "B", "ausgabe": [{"art": "echo", "notify": "notify.x"}]}}})["ueberall"]) == 1)

# ---------------------------------------------------------------- Raum erkennen
pruef("Echo Kueche per Name", ra.raum_von_geraet(k, "alexa", "Küche") == "kueche")
pruef("Echo ohne Namen: None", ra.raum_von_geraet(k, "alexa", "Echo") is None)
pruef("Satellit per Eintrag", ra.raum_von_geraet(k, "ha", "Voice PE Wohnzimmer") == "wohnzimmer")
pruef("neuer Satellit per HA-Bereich (ohne Eintrag)", ra.raum_von_geraet(k, "ha", "Voice PE Neu", "Küche") == "kueche")
pruef("Eintrag gewinnt gegen HA-Bereich", ra.raum_von_geraet(k, "ha", "Voice PE Wohnzimmer", "Küche") == "wohnzimmer")
pruef("App ohne Eintrag: kein Raum (wandert mit der Person)", ra.raum_von_geraet(k, "app", "Küche", "Küche") is None)
pruef("App mit ausdruecklichem Eintrag: Raum", ra.raum_von_geraet(k, "app", "Tablet Flur") == "keller")
pruef("unbekannter Bereich: None", ra.raum_von_geraet(k, "ha", "Neu", "Dachboden") is None)
pruef("Telefon (VoIP) ohne Bereich: None", ra.raum_von_geraet(k, "ha", "fritz.box", "") is None)
pruef("Raum im Text: Alias", ra.raum_finden(k, "in der Stube") == "wohnzimmer")
pruef("Raum im Text: Umlaut", ra.raum_finden(k, "Kueche") == "kueche" and ra.raum_finden(k, "in der Küche") == "kueche")
pruef("Raum im Text: ueberall", ra.raum_finden(k, "überall im Haus") == "ueberall")
pruef("Raum im Text: Unsinn", ra.raum_finden(k, "Mars") is None and ra.raum_finden(k, "  ") is None)
pruef("Esszimmer = Wohnzimmer", ra.raum_finden(k, "im Esszimmer") == "wohnzimmer")
pruef("Zuruf Verstaerker erkannt", ra.raum_finden(k, "sag es über den Verstärker") == "zuruf:verstaerker"
      and ra.raum_finden(k, "Wohnzimmer über den Receiver") == "zuruf:verstaerker")
pruef("Kontextsatz nennt Raum und Bereich", "Gefragt im Raum: Küche" in ra.kontext(k, "kueche") and "HA-Bereich „Küche“" in ra.kontext(k, "kueche")
      and "an = Küche" in ra.kontext(k, "kueche"))
pruef("Kontextsatz ohne Raum leer", ra.kontext(k, None) == "" and ra.kontext(None, "kueche") == "")
pruef("Ziel gueltig", ra.ziel_gueltig(k, "kueche") and ra.ziel_gueltig(k, "ueberall") and ra.ziel_gueltig(k, "zuruf:verstaerker")
      and not ra.ziel_gueltig(k, "zuruf:gibtsnicht") and not ra.ziel_gueltig(None, "kueche") and not ra.ziel_gueltig(k, "mars"))
pruef("Raumnamen", ra.raum_name(k, "ueberall") == "überall" and ra.raum_name(k, "zuruf:verstaerker") == "Verstärker"
      and ra.raum_name(k, "buero") == "Büro" and ra.raum_name(k, "mars") == "mars")

# ---------------------------------------------------------------- Plan
p = ra.plan(k, "kueche", "Essen ist fertig")
pruef("Kueche: Echo announce", p["aufrufe"] == [{"dienst": "notify/alexa_media_kueche", "daten": {
    "message": "Essen ist fertig", "data": {"type": "announce"}}, "hinweis": p["aufrufe"][0]["hinweis"]}], p)
p = ra.plan(k, "kueche", "Essen ist fertig", gong=False)
pruef("Kueche ohne Gong: tts", p["aufrufe"][0]["daten"]["data"]["type"] == "tts", p)
p = ra.plan(k, "buero", "Hallo", zustand=lambda e: {"state": "idle"})
pruef("Buero: MA-Ansage + Satellit", dienste(p) == ["music_assistant/play_announcement", "assist_satellite/announce"], p)
ma = p["aufrufe"][0]["daten"]
pruef("MA: Gong, Lautstaerke 70, Stimme per Adresse (Platzhalter im Trockenlauf)", ma == {"entity_id": "media_player.rx_ma",
      "url": ra.TON_PLATZHALTER, "use_pre_announce": True, "announce_volume": 70}, ma)
pruef("Satellit: preannounce", p["aufrufe"][1]["daten"] == {"entity_id": "assist_satellite.pe_bu", "message": "Hallo", "preannounce": True})
p = ra.plan(k, "buero", "Hallo", gong=False, lautstaerke=40)
pruef("MA ohne Gong, Lautstaerke 40", p["aufrufe"][0]["daten"]["use_pre_announce"] is False and p["aufrufe"][0]["daten"]["announce_volume"] == 40, p)
p = ra.plan(k, "buero", "Hallo", lautstaerke=False)
pruef("Lautstaerke False: keine Angabe", "announce_volume" not in p["aufrufe"][0]["daten"], p)
p0 = ra.plan(k, "buero", "Hallo", lautstaerke=0)
pruef("Lautstaerke 0 ungueltig: abgelehnt, nichts geplant", p0["abgelehnt"] and "ungültig" in p0["abgelehnt"] and not p0["aufrufe"], p0)
url_rufe = []
p = ra.plan(k, "buero", "Hallo", zustand=lambda e: {"state": "unavailable" if e == "media_player.rx_ma" else "idle"},
            ton_url=lambda: url_rufe.append(1) or "http://lan/ton/x.mp3")
pruef("MA weg: Ausweichplayer ohne Gong", p["aufrufe"][0] == {"dienst": "media_player/play_media", "daten": {
    "entity_id": "media_player.rx_alt", "media_content_id": "http://lan/ton/x.mp3", "media_content_type": "music"},
    "hinweis": "Ausweichweg über den Ausweichplayer"} and p["hinweise"], p)
pruef("Stimme wird nur einmal erzeugt", url_rufe == [1], url_rufe)
x = copy.deepcopy(BASIS_KONF)
del x["raeume"]["buero"]["ausgabe"][0]["fallback"]
p = ra.plan(ra.pruefen(x), "buero", "Hallo", zustand=lambda e: {"state": "unavailable" if e == "media_player.rx_ma" else "idle"})
pruef("MA weg ohne Ausweichplayer: uebersprungen, Satellit spricht", dienste(p) == ["assist_satellite/announce"]
      and "übersprungen" in " ".join(p["hinweise"]), p)
p = ra.plan(k, "ueberall", "Alle mal herhören", zustand=lambda e: {"state": "off" if "rx_avr" in e else "idle"})
pruef("ueberall: Verstaerker aus, nur Echo-Gruppe", dienste(p) == ["notify/alexa_media_gruppe"] and p["hinweise"], p)
p = ra.plan(k, "kinderzimmer", "Hallo", zustand=lambda e: {"state": "unavailable"})
pruef("Player weg: alles uebersprungen = abgelehnt", p["abgelehnt"] and "nicht an" in " ".join(p["hinweise"]), p)
p = ra.plan(k, "kinderzimmer", "Hallo", zustand=lambda e: {"state": "idle"})
pruef("Player: play_media announce", p["aufrufe"][0]["daten"]["announce"] is True and p["aufrufe"][0]["dienst"] == "media_player/play_media", p)
p = ra.plan(k, "keller", "Hallo")
pruef("Raum ohne Lautsprecher: abgelehnt", p["abgelehnt"] and "kein Lautsprecher" in p["abgelehnt"], p)
p = ra.plan(k, "buero", "Hallo", ruhe=(True, 7))
pruef("Nachtruhe sperrt alles", p["abgelehnt"] and "Nachtruhe bis 7" in p["abgelehnt"] and not p["aufrufe"], p)
p = ra.plan(k, "buero", "Hallo", ruhe=(False, 7))
pruef("Nachtruhe aus: geht", not p["abgelehnt"], p)
p = ra.plan(k, "buero", "Antwort", bevorzugt="Voice PE Büro")
pruef("Antwortweg: nur das fragende Geraet", dienste(p) == ["assist_satellite/announce"], p)
p = ra.plan(k, "buero", "Antwort", bevorzugt="Unbekanntes Geraet")
pruef("Antwortweg: unbekanntes Geraet = alle Ausgaben des Raums", len(p["aufrufe"]) == 2, p)
pruef("Plan: unbekannter Raum", "Unbekannter Raum" in ra.plan(k, "mars", "x")["abgelehnt"])
pruef("Plan: leerer Text", ra.plan(k, "kueche", "  ")["abgelehnt"] == "Kein Text für die Durchsage.")
# Bereinigung wie anruf.text_sauber: HA rendert Vorlagen, Alexa liest Auszeichnungen (Pruefung 05.11.2026)
BOESE = "Hallo {{ states('lock.haustuer') }} {% for x in y %}<speak><audio src='x'/></speak>\x07 Akku 20 %"
p = ra.plan(k, "kueche", BOESE)
m = p["aufrufe"][0]["daten"]["message"] if p["aufrufe"] else ""
pruef("Durchsage: keine Vorlagen-Klammern, Auszeichnungen, Steuerzeichen oder % im Echo-Text",
      m and not any(z in m for z in "{}<>%\x07") and "Akku 20 Prozent" in m and p["text"] == m, m)
p = ra.plan(k, "buero", BOESE, zustand=lambda e: {"state": "idle"})
sat = [a["daten"]["message"] for a in p["aufrufe"] if "message" in a["daten"]]
pruef("Durchsage: auch der Satellit bekommt den bereinigten Text", sat and all(not any(z in s for z in "{}<>%") for s in sat),
      sat)
p = ra.plan(k, "kueche", "{{ }} <> \x00")
pruef("Durchsage: nur Klammern und Steuerzeichen = leer, abgelehnt", p["abgelehnt"] == "Kein Text für die Durchsage."
      and not p["aufrufe"], p)
pruef("Durchsage: normaler Text bleibt", ra.text_sauber("  Essen ist fertig! ") == "Essen ist fertig!")
ra.setze_sprache("en")
pruef("Durchsage: % auf Englisch als Wort", ra.text_sauber("Battery 20%") == "Battery 20 percent")
ra.setze_sprache("de")
n = []
ok_n, fehl = ra.ausfuehren(ra.plan(k, "kueche", "x"), lambda pfad, d: n.append(pfad))
pruef("ausfuehren ruft /api/services/<dienst>", n == ["/api/services/notify/alexa_media_kueche"] and ok_n == 1 and not fehl, n)


def kaputt(pfad, d):
    raise OSError("weg")


pruef("ausfuehren meldet Fehler statt zu werfen", ra.ausfuehren(ra.plan(k, "kueche", "x"), kaputt) == (0, ["notify/alexa_media_kueche (OSError)"]))
pruef("beschreiben nennt Dienst und Daten", "notify/alexa_media_kueche" in ra.beschreiben(ra.plan(k, "kueche", "Test")))
pruef("beschreiben einer Absage", ra.beschreiben(ra.plan(k, "kueche", "")) == "Abgelehnt: Kein Text für die Durchsage.")

# ---------------------------------------------------------------- Voice PE, Verstaerker auf Zuruf, Kinderzimmer
p = ra.plan(k, "wohnzimmer", "Hallo", zustand=lambda e: {"state": "on"})
pruef("Wohnzimmer ohne Voice PE: keine Ausgabe, ehrlicher Satz mit Angebot", p["abgelehnt"] and "noch keinen festen Lautsprecher" in p["abgelehnt"]
      and "Verstärker" in p["abgelehnt"] and not p["aufrufe"], p)
p = ra.plan(k, "zuruf:verstaerker", "Hallo", lautstaerke=50, zustand=lambda e: {"state": "idle"})
pruef("Verstaerker auf Zuruf: Gong, nie announce_volume (auch nicht ausdruecklich)", dienste(p) == ["music_assistant/play_announcement"]
      and "announce_volume" not in p["aufrufe"][0]["daten"] and p["aufrufe"][0]["daten"]["use_pre_announce"] is True, p)
p = ra.plan(k, "zuruf:verstaerker", "Hallo", zustand=lambda e: {"state": "unavailable" if e == "media_player.rx_ma" else "idle"},
            ton_url=lambda: "http://lan/x.mp3")
pruef("Verstaerker auf Zuruf, MA weg: Ausweichplayer", p["aufrufe"][0]["daten"]["entity_id"] == "media_player.rx_alt", p)
p = ra.plan(k, "ueberall", "Hallo", zustand=lambda e: {"state": "on"})
pruef("ueberall, Verstaerker an, Voice PE noch nicht: Echo-Gruppe + Verstaerker ohne Lautstaerke",
      dienste(p) == ["notify/alexa_media_gruppe", "music_assistant/play_announcement"]
      and "announce_volume" not in p["aufrufe"][1]["daten"], p)
p = ra.plan(k, "ueberall", "Hallo")
pruef("ueberall, Verstaerker-Zustand nicht pruefbar: nicht benutzt", dienste(p) == ["notify/alexa_media_gruppe"], p)
x = copy.deepcopy(BASIS_KONF)
x["einstellungen"]["voice_pe_aktiv"] = True
kv = ra.pruefen(x)
p = ra.plan(kv, "wohnzimmer", "Hallo")
pruef("Voice PE aktiv: Wohnzimmer = Satellit", dienste(p) == ["assist_satellite/announce"], p)
p = ra.plan(kv, "ueberall", "Hallo", zustand=lambda e: {"state": "on"})
pruef("Voice PE aktiv: Verstaerker gehoert nicht mehr zu ueberall, auch nicht wenn an",
      dienste(p) == ["notify/alexa_media_gruppe", "assist_satellite/announce"], p)
p = ra.plan(kv, "zuruf:verstaerker", "Hallo")
pruef("Voice PE aktiv: Verstaerker geht weiter auf Zuruf", p["aufrufe"] and "music_assistant" in p["aufrufe"][0]["dienst"], p)
p = ra.plan(k, "kinderzimmer", "Hallo", zustand=lambda e: {"state": "off"})
pruef("Kinderzimmer, Box aus: nichts, Einblendung ist nur Platzhalter", not p["aufrufe"] and p["abgelehnt"]
      and "Platzhalter" in " ".join(p["hinweise"]), p)
y = copy.deepcopy(BASIS_KONF)
y["raeume"]["kinderzimmer"]["ausgabe"][1].pop("platzhalter")
ky = ra.pruefen(y)
p = ra.plan(ky, "kinderzimmer", "Hallo", zustand=lambda e: {"state": "off"})
pruef("Kinderzimmer, Box aus, Einblendung eingerichtet: Texteinblendung als Ersatz", dienste(p) == ["notify/mobile_app_mia_platzhalter"]
      and p["aufrufe"][0]["daten"] == {"title": "Jarvis", "message": "Hallo"}, p)
p = ra.plan(ky, "kinderzimmer", "Hallo", zustand=lambda e: {"state": "playing"})
pruef("Kinderzimmer, Box an: Ansage, kein Ersatz", dienste(p) == ["media_player/play_media"], p)

# ---------------------------------------------------------------- Medien (Quizshow): Satellit spielt die fertige Datei
K = ra.pruefen({"raeume": {"wohnzimmer": {"name": "Wohnzimmer", "ausgabe": [
    {"art": "satellit", "entity": "assist_satellite.voice_wz"}]}},
    "zuruf": {"verstaerker": {"name": "Verstärker", "ausgabe": {"art": "ma", "entity": "media_player.receiver_ma",
                                                                 "fallback": "media_player.receiver_alt", "lautstaerke_fest": True}}}})
p_alt = ra.plan(K, "wohnzimmer", "Hallo", ton_url=lambda: "http://x/ton/a.mp3")
p_med = ra.plan(K, "wohnzimmer", "Hallo", gong=False, ton_url=lambda: "http://x/ton/a.mp3", medien=True)
p_vs = ra.plan(K, "zuruf:verstaerker", "Hallo", gong=False, lautstaerke=False, ton_url=lambda: "http://x/ton/a.mp3", medien=True)
pruef("R1 Raumplan: Satellit spricht sonst selbst, mit medien die Datei; Verstaerker ueber Music Assistant ohne Gong",
      "media_id" not in p_alt["aufrufe"][0]["daten"] and p_med["aufrufe"][0]["daten"]["media_id"] == "http://x/ton/a.mp3"
      and p_med["aufrufe"][0]["daten"]["preannounce"] is False and p_vs["aufrufe"][0]["dienst"] == "music_assistant/play_announcement"
      and p_vs["aufrufe"][0]["daten"] == {"entity_id": "media_player.receiver_ma", "url": "http://x/ton/a.mp3",
                                          "use_pre_announce": False}, (p_med, p_vs))

# ---------------------------------------------------------------- Englisch
ra.setze_sprache("en")
pruef("EN: Kontextsatz", ra.kontext(k, "kueche").startswith(" Asked in the room: Küche.") and "HA area “Küche”" in ra.kontext(k, "kueche")
      and "an = Küche" in ra.kontext(k, "kueche"))
pruef("EN: Absagen", ra.plan(k, "kueche", " ")["abgelehnt"] == "No text for the announcement."
      and "Quiet hours until 7" in ra.plan(k, "buero", "x", ruhe=(True, 7))["abgelehnt"]
      and "Unknown room" in ra.plan(k, "mars", "x")["abgelehnt"]
      and "volume invalid" in ra.plan(k, "buero", "x", lautstaerke=500)["abgelehnt"]
      and "No speaker is reachable for Keller" in ra.plan(k, "keller", "x")["abgelehnt"])
p = ra.plan(k, "buero", "Hi", zustand=lambda e: {"state": "unavailable" if e == "media_player.rx_ma" else "idle"}, ton_url=lambda: "u")
pruef("EN: Hinweise", p["aufrufe"][0]["hinweis"] == "Fallback via the fallback player" and "fallback player" in p["hinweise"][0]
      and "own voice" in p["aufrufe"][1]["hinweis"], p)
pruef("EN: Raumdatei-Fehler und Raumname", "off limits" in wirft(ra.pruefen, dict(BASIS_KONF, zuruf={"x": {"name": "X", "ausgabe": {
      "art": "player", "entity": "media_player.baby_cam"}}})) and ra.raum_name(k, "ueberall") == "everywhere"
      and ra.beschreiben(ra.plan(k, "kueche", "")).startswith("Refused: "))
pruef("EN: Hinweis bleibt, wie er in der Datei steht", "noch keinen festen Lautsprecher" in ra.plan(k, "wohnzimmer", "x")["abgelehnt"])
try:
    ra.setze_sprache("xx")
    pruef("Sprache: nur de oder en", False)
except ValueError:
    pruef("Sprache: nur de oder en", ra.SPRACHE == "en")
ra.setze_sprache("de")
pruef("DE wieder", ra.raum_name(k, "ueberall") == "überall")

shutil.rmtree(T, ignore_errors=True)
print("Raeume: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
