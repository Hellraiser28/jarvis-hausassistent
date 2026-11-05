#!/usr/bin/env python3
"""Baustein anruf.py (Jarvis ruft an, seit 0.6): Regeln und Spielregeln (Zuruf, Unwetter, NAS, Ruhezeit, Abstand,
Tageslimit), Ansage, Rueckmeldungen von HA-SIP, Folgeschritt, Speichern, englische Texte.
Nur Attrappen, kein HA, kein Telefon, keine Netzzugriffe."""
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import anruf as an  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


T = tempfile.mkdtemp(prefix="anruf-")
R = an.regeln_laden(os.path.join(T, "fehlt.json"))
MITTAG = datetime(2026, 10, 29, 12, 0).timestamp()

# ---------------------------------------------------------------- Regeln
pruef("Standard: nicht scharf", R["scharf"] is False)
pruef("Anlaesse: zuruf, unwetter, nas (und test), kein Babyfon", set(R["anlaesse"]) == {"test", "zuruf", "unwetter", "nas"})
pruef("Zweiter Versuch nach 5 min (innerhalb 15 min fuer 'wiederholte Anrufer')",
      R["wiederholen"] == 1 and R["wiederholen_nach_min"] == 5 and R["wiederholen_nach_min"] < 15)
open(os.path.join(T, "r.json"), "w").write(json.dumps({"scharf": "ja", "max_tag": -1, "ruhe": ["23:00", "6:00"],
                                                        "anlaesse": {"Boese Taste": {}, "rauch": {"name": "Rauch"}},
                                                        "wiederholen": True, "abstand_min": 5}))
r2 = an.regeln_laden(os.path.join(T, "r.json"))
pruef("Regeln: falsche Typen bleiben Standard", r2["scharf"] is False and r2["max_tag"] == 3 and r2["ruhe"] == ["22:00", "07:00"]
      and r2["wiederholen"] == 1 and r2["abstand_min"] == 5, r2)
pruef("Regeln: nur gueltige Anlass-Namen", set(r2["anlaesse"]) == {"rauch"}, r2["anlaesse"])
open(os.path.join(T, "r3.json"), "w").write(json.dumps({"scharf": True}))
pruef("Regeln: scharf nur mit true", an.regeln_laden(os.path.join(T, "r3.json"))["scharf"] is True)
open(os.path.join(T, "r4.json"), "w").write(json.dumps({"ruhe_ausnahmen": ["zuruf", "nas"], "gleicher_anlass_ausnahmen": "kaputt"}))
R4 = an.regeln_laden(os.path.join(T, "r4.json"))
pruef("anruf.json kann Ausnahmen setzen, falscher Typ bleibt Standard",
      R4["ruhe_ausnahmen"] == ["zuruf", "nas"] and R4["gleicher_anlass_ausnahmen"] == ["zuruf"])
open(os.path.join(T, "r5.json"), "w").write("[1]")
pruef("Regeln: kein Objekt -> Standard", an.regeln_laden(os.path.join(T, "r5.json")) == R)

# ---------------------------------------------------------------- Spielregeln (Standard)
NACHT = datetime(2026, 10, 30, 23, 30).timestamp()
TAG = datetime(2026, 10, 30, 14, 0).timestamp()
pruef("Nachts: Zuruf (Weckanruf) ruft an", an.pruefen("zuruf", R, [], NACHT) == (True, ""))
pruef("Nachts: Unwetter nur Push (Ruhezeit)", an.pruefen("unwetter", R, [], NACHT) == (False, "Ruhezeit"))
pruef("Nachts: NAS nur Push (Ruhezeit)", an.pruefen("nas", R, [], NACHT) == (False, "Ruhezeit"))
pruef("Tags: Unwetter ruft an", an.pruefen("unwetter", R, [], TAG) == (True, ""))
pruef("Babyfon ist kein Anlass", an.pruefen("babyfon", R, [], TAG) == (False, "unbekannter Anlass"))
v = [{"zeit": int(TAG - 3600), "anlass": "zuruf", "status": "quittiert"}]
pruef("Zweiter Zuruf nach 1 h: erlaubt (eigener Auftrag)", an.pruefen("zuruf", R, v, TAG) == (True, ""))
v = [{"zeit": int(TAG - 3600), "anlass": "unwetter", "status": "quittiert"}]
pruef("Zweites Unwetter nach 1 h: nein (4 h)", an.pruefen("unwetter", R, v, TAG) == (False, "derselbe Anlass vor kurzem"))
v = [{"zeit": int(TAG - 600), "anlass": "zuruf", "status": "quittiert"}]
pruef("Abstand 15 min gilt auch fuer Zuruf", an.pruefen("zuruf", R, v, TAG) == (False, "zu kurz nach dem letzten Anruf"))
v = [{"zeit": int(TAG - 7200 * i), "anlass": "zuruf", "status": "quittiert"} for i in (1, 2, 3)]
pruef("Hoechstens 3 am Tag", an.pruefen("zuruf", R, v, TAG) == (False, "Tageslimit erreicht"))

# ---------------------------------------------------------------- Pruefen mit eigenem Anlass
R["anlaesse"]["wasser"] = {"name": "Wasser im Keller"}
pruef("Pruefen: bekannter Anlass am Mittag", an.pruefen("wasser", R, [], MITTAG) == (True, ""))
pruef("Pruefen: unbekannter Anlass", an.pruefen("mail", R, [], MITTAG)[0] is False)
nacht = datetime(2026, 10, 29, 23, 30).timestamp()
frueh = datetime(2026, 10, 30, 6, 59).timestamp()
pruef("Pruefen: Ruhezeit abends und frueh", an.pruefen("wasser", R, [], nacht)[1] == "Ruhezeit"
      and an.pruefen("wasser", R, [], frueh)[1] == "Ruhezeit")
pruef("Pruefen: 07:00 ist keine Ruhezeit mehr", an.pruefen("wasser", R, [], datetime(2026, 10, 30, 7, 0).timestamp())[0])
pruef("Ruhezeit am Tag (ohne Mitternacht)", an.in_ruhezeit(dict(R, ruhe=["12:00", "14:00"]), datetime(2026, 1, 1, 13, 0))
      and not an.in_ruhezeit(dict(R, ruhe=["12:00", "14:00"]), datetime(2026, 1, 1, 14, 0)))
R["ruhe_ausnahmen"] = ["wasser"]
pruef("Pruefen: Ausnahme darf nachts", an.pruefen("wasser", R, [], nacht)[0])
R["ruhe_ausnahmen"] = []
laufend = [{"zeit": MITTAG - 60, "anlass": "test", "status": "angenommen"}]
pruef("Pruefen: nie zwei Anrufe gleichzeitig", an.pruefen("wasser", R, laufend, MITTAG)[1] == "es läuft schon ein Anruf")
kurz = [{"zeit": MITTAG - 300, "anlass": "test", "status": "quittiert"}]
pruef("Pruefen: Mindestabstand", an.pruefen("wasser", R, kurz, MITTAG)[1] == "zu kurz nach dem letzten Anruf")
gleich = [{"zeit": MITTAG - 3600, "anlass": "wasser", "status": "quittiert"}]
pruef("Pruefen: gleicher Anlass zu frueh", an.pruefen("wasser", R, gleich, MITTAG)[1] == "derselbe Anlass vor kurzem")
voll = [{"zeit": MITTAG - 3600 * (i + 1), "anlass": "test", "status": "quittiert"} for i in range(3)]
pruef("Pruefen: Tageslimit", an.pruefen("wasser", R, voll, MITTAG)[1] == "Tageslimit erreicht")
gestern = [{"zeit": MITTAG - 86400 - 3600 * i, "anlass": "wasser", "status": "quittiert"} for i in range(5)]
pruef("Pruefen: gestern zaehlt nicht", an.pruefen("wasser", R, gestern, MITTAG)[0])
trocken = [{"zeit": MITTAG - 60, "anlass": "wasser", "status": "trocken"}] * 5
pruef("Pruefen: Trockenlaeufe zaehlen nicht", an.pruefen("wasser", R, trocken, MITTAG)[0])

# ---------------------------------------------------------------- Anlegen und Ansage
e = an.anlegen("wasser", "Der Wassermelder im Keller meldet Nässe.", R, [], MITTAG)
pruef("Anlegen: nicht scharf -> trocken", e["status"] == "trocken" and e["grund"] == "", e)
R["scharf"] = True
e = an.anlegen("wasser", "Der Wassermelder im Keller meldet Nässe.", R, [], MITTAG)
pruef("Anlegen: scharf -> waehlt", e["status"] == "waehlt" and e["versuch"] == 1, e)
g = an.anlegen("wasser", "x", R, [], nacht)
pruef("Anlegen: gesperrt mit Grund", g["status"] == "gesperrt" and g["grund"] == "Ruhezeit", g)
t = an.text_sauber("{{ states('lock.tuer') }} {% if %} <b>\x07Hallo\n" + "x" * 400)
pruef("Text: keine Vorlagen, keine Steuerzeichen, gekuerzt", "{" not in t and "%" not in t and "<" not in t and "\x07" not in t
      and len(t) <= an.TEXT_MAX, t[:80])
a = an.ansage("Im Keller ist Wasser.", "Anna")
pruef("Ansage: Gruss mit Namen, Text, Tasten", a.startswith("Hallo Anna, hier ist Jarvis. Im Keller ist Wasser.") and "die 1" in a
      and "die 2" in a, a)
a = an.ansage("Im Keller ist Wasser.")
pruef("Ansage: ohne Namen neutral", a.startswith("Hallo, hier ist Jarvis. Im Keller ist Wasser."), a)
a = an.ansage("x", "{{ states('sensor.geheim') }}")
pruef("Ansage: Name ohne Vorlagen-Klammern", "{" not in a and "}" not in a and "%" not in a, a)

# ---------------------------------------------------------------- Rueckmeldungen von HA-SIP


def lauf(*ereignisse, iid="call-7"):
    x = an.anlegen("wasser", "Wasser.", R, [], MITTAG)
    for ev in ereignisse:
        d = {"internal_id": iid, "call_direction": "outgoing"}
        d.update(ev)
        an.ereignis(x, d, MITTAG + 10)
    return x


pruef("Ereignis: abgenommen, 1 gedrueckt, aufgelegt -> quittiert",
      lauf({"event": "call_established"}, {"event": "dtmf_digit", "digit": "1"}, {"event": "entered_menu", "menu_id": "quittiert"},
           {"event": "call_disconnected"})["status"] == "quittiert")
x = lauf({"event": "call_established"}, {"event": "dtmf_digit", "digit": "2"}, {"event": "entered_menu", "menu_id": "gespraech"})
pruef("Ereignis: 2 gedrueckt -> gespraech", x["status"] == "gespraech", x)
k = an.kontext_hinweis([x], MITTAG + 60, "Anna")
pruef("Kontext: Jarvis kennt den Grund im Gespraech", "Wasser." in k and "Anna" in k
      and an.kontext_hinweis([x], MITTAG + 3600) == "", k)
pruef("Kontext: ohne Namen die Hauptperson", "Du hast die Hauptperson eben angerufen" in an.kontext_hinweis([x], MITTAG + 60)
      and "Die Hauptperson hat am Telefon" in an.kontext_hinweis([x], MITTAG + 60))
an.ereignis(x, {"internal_id": "call-7", "call_direction": "outgoing", "event": "call_disconnected"}, MITTAG + 99)
pruef("Ereignis: Gespraech beendet", x["status"] == "gespraech_beendet")
pruef("Ereignis: niemand nimmt ab", lauf({"event": "outgoing_call_initiated"}, {"event": "ring_timeout"},
                                          {"event": "call_disconnected"})["status"] == "nicht_erreicht")
pruef("Ereignis: abgenommen, nichts gedrueckt", lauf({"event": "call_established"}, {"event": "timeout", "menu_id": "anruf"},
                                                    {"event": "entered_menu", "menu_id": "keine_antwort"})["status"] == "keine_antwort")
pruef("Ereignis: abgenommen und gleich aufgelegt", lauf({"event": "call_established"}, {"event": "call_disconnected"})["status"] == "aufgelegt")
x = lauf({"event": "call_established"})
fremd = an.ereignis(x, {"internal_id": "anderer", "call_direction": "outgoing", "event": "dtmf_digit", "digit": "1"}, MITTAG)
rein = an.ereignis(x, {"internal_id": "call-7", "call_direction": "incoming", "event": "dtmf_digit", "digit": "1"}, MITTAG)
pruef("Ereignis: fremder Anruf und eingehende Anrufe zaehlen nicht", not fremd and not rein and x["status"] == "angenommen", x)
pruef("Ereignis: Unsinn wird abgelehnt", an.ereignis(x, "kaputt", MITTAG) is False)
pruef("Ereignis: Taste 1 vor dem Abnehmen zaehlt nicht", lauf({"event": "dtmf_digit", "digit": "1"})["status"] == "waehlt")
x = lauf(*[{"event": "dtmf_digit", "digit": "9"}] * 40)
pruef("Ereignis: Verlauf hoechstens 30 Eintraege", len(x["verlauf"]) == 30)

# ---------------------------------------------------------------- Folgeschritt
x = lauf({"event": "ring_timeout"})
pruef("Folge: erst nochmal anrufen", an.naechster_schritt(x, R) == ("nochmal", 300))
x2 = an.anlegen("wasser", "Wasser.", R, [x], MITTAG + 400, versuch=2, vorher=x["id"])
pruef("Folge: Wiederholung umgeht die Abstandssperre", x2["status"] == "waehlt" and x2["vorher"] == x["id"], x2)
an.ereignis(x2, {"internal_id": "call-8", "call_direction": "outgoing", "event": "ring_timeout"}, MITTAG + 430)
pruef("Folge: danach Push", an.naechster_schritt(x2, R) == ("push", None))
pruef("Folge: ohne danach_push nichts", an.naechster_schritt(x2, dict(R, danach_push=False)) == (None, None))
pruef("Folge: nach Quittung nichts", an.naechster_schritt(lauf({"event": "call_established"}, {"event": "dtmf_digit", "digit": "1"}), R) == (None, None))
pruef("Folge: Trockenlauf nichts", an.naechster_schritt({"status": "trocken"}, R) == (None, None))
pruef("Folge: schon erledigt nichts", an.naechster_schritt(dict(x, folge_erledigt=True), R) == (None, None))

# ---------------------------------------------------------------- Speichern
p = os.path.join(T, "anrufe.json")
an.speichern(p, [{"id": str(i), "status": "quittiert"} for i in range(250)])
geladen = an.laden(p)
pruef("Speichern: hoechstens 200, Rechte 600", len(geladen) == 200 and geladen[0]["id"] == "50"
      and stat.S_IMODE(os.stat(p).st_mode) == 0o600, oct(os.stat(p).st_mode))
if os.name == "posix":
    # Die Datei darf auch nicht kurz mit Standardrechten entstehen (Pruefung 05.11.2026: vorher open mit Umask, dann
    # chmod). Beobachter auf os.open und open im Modul, Umask 0 und eine liegengebliebene .neu mit 644.
    gesehen = []
    _os_open = os.open

    def beob_os_open(pfad, flags, mode=0o777, *a, **kw):
        gesehen.append(("os.open", str(pfad), mode))
        return _os_open(pfad, flags, mode, *a, **kw)

    def beob_open(pfad, modus="r", *a, **kw):
        gesehen.append(("open", str(pfad), modus))
        return open(pfad, modus, *a, **kw)

    p2 = os.path.join(T, "anrufe2.json")
    open(p2 + ".neu", "w").write("alt")
    os.chmod(p2 + ".neu", 0o644)
    alte_umask = os.umask(0)
    try:
        os.open, an.open = beob_os_open, beob_open
        an.speichern(p2, [{"id": "1", "status": "quittiert"}])
    finally:
        os.open = _os_open
        del an.open
        os.umask(alte_umask)
    schreibend = [g for g in gesehen if g[0] == "os.open" or "w" in g[2]]
    pruef("Speichern: nur ueber os.open mit 600, auch bei Umask 0 und alter .neu",
          schreibend == [("os.open", p2 + ".neu", 0o600)] and stat.S_IMODE(os.stat(p2).st_mode) == 0o600
          and not os.path.exists(p2 + ".neu") and an.laden(p2) == [{"id": "1", "status": "quittiert"}],
          (schreibend, oct(os.stat(p2).st_mode)))
open(p, "w").write("{}")
pruef("Laden: kein Verlauf -> leer", an.laden(p) == [] and an.laden(os.path.join(T, "fehlt")) == [])
pruef("Aktiv: laufender Anruf gefunden", an.aktiv([{"status": "quittiert"}, {"status": "angenommen", "id": "z", "zeit": MITTAG}], MITTAG + 5)["id"] == "z")
haengt = [{"zeit": MITTAG - 3600, "anlass": "test", "status": "waehlt"}]
pruef("Verfall: alter Anruf ohne Rueckmeldung sperrt nicht", an.pruefen("wasser", R, haengt, MITTAG)[0] and an.verfallen(haengt, MITTAG) == 1
      and haengt[0]["status"] == "fehler" and haengt[0]["grund"] == "keine Rückmeldung von HA")
# ---------------------------------------------------------------- Kennung eindeutig (ein gesperrter und ein echter Anruf
# in derselben Millisekunde: die Zuordnung nach Kennung darf nie den falschen greifen)
k1 = an.anlegen("mail", "x", R, [], MITTAG)
k2 = an.anlegen("wasser", "y", R, [k1], MITTAG)
k3 = an.anlegen("wasser", "z", R, [k1, k2], MITTAG)
pruef("Kennung: gleiche Millisekunde, drei verschiedene Kennungen", len({k1["id"], k2["id"], k3["id"]}) == 3,
      [k1["id"], k2["id"], k3["id"]])
pruef("Kennung: Format bleibt a<hex>", all(re.fullmatch(r"a[0-9a-f]+", k["id"]) for k in (k1, k2, k3)))

# ---------------------------------------------------------------- Englisch
try:
    an.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", True)
an.setze_sprache("en")
a = an.ansage("There is water in the basement.", "Anna")
pruef("EN: Ansage", a == "Hello Anna, this is Jarvis. There is water in the basement. Press 1 if you heard it, or 2 if you "
      "want to talk to me.", a)
pruef("EN: Ansage ohne Namen", an.ansage("x").startswith("Hello, this is Jarvis. x"))
R["scharf"] = False
gruende = [an.pruefen("mail", R, [], MITTAG)[1], an.pruefen("wasser", R, [], nacht)[1],
           an.pruefen("wasser", R, laufend, MITTAG)[1], an.pruefen("wasser", R, voll, MITTAG)[1],
           an.pruefen("wasser", R, kurz, MITTAG)[1], an.pruefen("wasser", R, gleich, MITTAG)[1]]
pruef("EN: Gruende", gruende == ["unknown occasion", "quiet hours", "a call is already in progress", "daily limit reached",
                                 "too soon after the last call", "same occasion recently"], gruende)
haengt = [{"zeit": MITTAG - 3600, "anlass": "test", "status": "waehlt"}]
an.verfallen(haengt, MITTAG)
pruef("EN: Verfall", haengt[0]["grund"] == "no response from HA", haengt)
R["scharf"] = True
x = lauf({"event": "call_established"}, {"event": "dtmf_digit", "digit": "2"})
k = an.kontext_hinweis([x], MITTAG + 60, "Anna")
pruef("EN: Kontext", k == " You just called Anna, reason: “Wasser.”. Anna pressed 2 on the phone and is talking to you now. "
      "Start with the reason, briefly.", k)
pruef("EN: Kontext ohne Namen", "You just called the main person" in an.kontext_hinweis([x], MITTAG + 60)
      and "The main person pressed 2" in an.kontext_hinweis([x], MITTAG + 60))
an.setze_sprache("de")
pruef("Zurueck auf Deutsch", an.ansage("x").startswith("Hallo, hier ist Jarvis."))

print("Anruf: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
