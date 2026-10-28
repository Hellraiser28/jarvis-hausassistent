#!/usr/bin/env python3
"""Einheitentests fuer bruecke/gedaechtnis.py und bruecke/personen.py (seit 0.4). Nur im Testordner."""
import json
import os
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HIER, os.path.join(os.path.dirname(HIER), "bruecke")]
import gedaechtnis as gd  # noqa: E402
import personen as pe  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    if bed:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name, info)


D = tempfile.mkdtemp(prefix="gedaechtnis-test-")
NAMEN = {"alex": "Alex", "sam": "Sam"}

# Personen
json.dump({"alex": {"name": "Alex", "rolle": "haupt", "paperless_id": 3},
           "sam": {"name": "Sam", "rolle": "familie", "kontakt": "Sam", "paperless_id": 4},
           "Böse": {"name": "x", "rolle": "haupt"}, "gast": {"name": "<script>", "rolle": "chef"}},
          open(os.path.join(D, "personen.json"), "w"))
P = pe.laden(D)
pruef("Personen: nur gueltige", sorted(P) == ["alex", "sam"], P)
pruef("Hauptperson", pe.haupt(P) == "alex")
geraete = [{"id": "4b6f5d", "name": "Handy Alex"}, {"id": "aa11bb", "name": "Handy Sam", "person": "sam"},
           {"id": "cc22dd", "name": "fremd", "person": "gast"}]
pruef("Geraet ohne Person: Hauptperson", pe.fuer_geraet(P, geraete, "4b6f5d") == "alex")
pruef("Geraet Sam", pe.fuer_geraet(P, geraete, "aa11bb") == "sam")
pruef("Hauptschluessel", pe.fuer_geraet(P, geraete, "haupt") == "alex")
pruef("unbekannte Person am Geraet: niemand", pe.fuer_geraet(P, geraete, "cc22dd") is None)
pruef("Sam darf Einkaufsliste", pe.darf(P, "sam", "einkaufsliste"))
for w in ("homelab_auftrag", "postfach", "notizen", "aufgaben", "routine", "oberflaeche", "verhalten", "handy_suchen",
          "nas_status", "updates", "quelle_hinzufuegen"):
    pruef("Sam darf nicht: " + w, not pe.darf(P, "sam", w))
pruef("Alex darf alles", pe.darf(P, "alex", "homelab_auftrag"))
pruef("Unbekannte Person darf nichts", not pe.darf(P, "gast", "wetter"))
pruef("ohne Datei: nur Hauptperson", pe.laden(tempfile.mkdtemp()) == pe.STANDARD)

# Migration aus gedaechtnis.md
open(os.path.join(D, "gedaechtnis.md"), "w", encoding="utf-8").write(
    "- 22.10.2026 19:05: Privates von Alex\n- 23.10.2026 01:26: Geburtstage der Familie\n"
    "- 24.10.2026 19:14: Denon-Regel\n")
pruef("Migration: 3 uebernommen", gd.migrieren(D, {2: "haus", 3: "haus"}, "alex") == 3)
pruef("Migration: nur einmal", gd.migrieren(D, {}, "alex") == 0)
g = gd.laden(D)
pruef("Migration: Bereiche", [e["bereich"] for e in g["eintraege"]] == ["alex", "haus", "haus"])
pruef("Migration: Datum bleibt", g["eintraege"][0]["datum"] == "22.10.2026 19:05")
pruef("Datei 600", oct(os.stat(os.path.join(D, gd.DATEI)).st_mode & 0o777) == "0o600")

# Sichtbarkeit
nb = gd.neu(D, "Sam mag Tee\nmit Zeilenumbruch", "sam", "sam")
pruef("neu: Nummer", nb == 4)
pruef("neu: wortgleich nicht doppelt", gd.neu(D, "sam mag tee mit zeilenumbruch", "sam", "sam") == 0)
pruef("neu: Steuerzeichen raus", "\n" not in gd.laden(D)["eintraege"][-1]["text"])
pruef("Alex sieht Sams Privates nicht", all(e["bereich"] != "sam" for e in gd.fuer_person(D, "alex")))
pruef("Sam sieht Alex' Privates nicht", all(e["bereich"] != "alex" for e in gd.fuer_person(D, "sam")))
pruef("Sam sieht Haus", len([e for e in gd.fuer_person(D, "sam") if e["bereich"] == "haus"]) == 2)
k = gd.fuer_kontext(D, "sam", NAMEN)
pruef("Kontext Sam: Haus + ihres, nichts von Alex", "Geburtstage" in k and "Sam mag Tee" in k
      and "Privates von Alex" not in k and "Nur für Sam" in k, k)
pruef("Kontext kurz: Hinweis auf aeltere", "Ältere Einträge" in gd.fuer_kontext(D, "alex", NAMEN, max_zeichen=60))
pruef("Sam kann Alex' Privates nicht vergessen", gd.vergessen(D, "sam", "Privates von Alex") == 0)
pruef("Sam kann Alex' Privates nicht ersetzen", not gd.ersetzen(D, 1, "geaendert", "sam"))
pruef("ersetzen behaelt alten Text", gd.ersetzen(D, 3, "Denon-Regel neu", "alex", quelle="import")
      and gd.laden(D)["eintraege"][2]["frueher"][0]["text"] == "Denon-Regel")

# TXT-Export und -Import (Sam)
t = gd.export_txt(D, "sam", NAMEN)
pruef("Export: Abschnitte", "## Haus" in t and "## Nur für Sam" in t and "Privates von Alex" not in t, t)
zeilen = t.split("\n")
geaendert = []
for z in zeilen:
    if z.startswith("[2]"):
        geaendert.append("[2] 23.10.2026 01:26 | Geburtstage der Familie (ergänzt)")
    elif z.startswith("[3]"):
        continue                                         # geloescht
    elif z.startswith("## Nur für Sam"):
        geaendert += [z, "- Sam arbeitet samstags oft bis 14 Uhr", "[1] 22.10.2026 | Versuch, Alex' Eintrag zu ändern"]
    elif z.startswith("[4]"):
        geaendert.append("[4] 28.10.2026 | Sam mag Tee mit Zeilenumbruch")
        geaendert.append("## Haus")
        geaendert.append("- Neuer Haus-Eintrag")
    else:
        geaendert.append(z)
v = gd.import_vergleich(D, "sam", "\n".join(geaendert), NAMEN)
pruef("Import: geaendert 1", [x["id"] for x in v["geaendert"]] == [2], v)
pruef("Import: geloescht 3", [x["id"] for x in v["geloescht"]] == [3], v)
pruef("Import: neu 2 in richtigen Bereichen", sorted((x["bereich"], x["text"]) for x in v["neu"]) ==
      [("haus", "Neuer Haus-Eintrag"), ("sam", "Sam arbeitet samstags oft bis 14 Uhr")], v)
pruef("Import: fremde Nummer ignoriert", v["unbekannt"] == [1], v)
pruef("Vergleichstext", "gelöscht [3]" in gd.vergleich_text(v, NAMEN, "sam"))
a, l_, n_, u_ = gd.import_uebernehmen(D, "sam", v)
pruef("Uebernehmen: Zahlen", (a, l_, n_, u_) == (1, 1, 2, 0), (a, l_, n_, u_))
g = gd.laden(D)
pruef("Alex' Eintrag unveraendert", g["eintraege"][0]["text"] == "Privates von Alex")
pruef("Eintrag 3 weg", all(e["id"] != 3 for e in g["eintraege"]))
pruef("Verschieben: haus -> privat", gd.import_vergleich(D, "sam", "## Nur für Sam\n[2] x | Geburtstage der "
                                                                  "Familie (ergänzt)\n## Haus\n", NAMEN)["geaendert"][0]["bereich"] == "sam")
leer = gd.import_vergleich(D, "sam", "irgendein Text ohne Abschnitte\n- auch nicht", NAMEN)
pruef("Ohne Abschnitte: nichts neu, aber alles als geloescht erkannt (Rueckfrage zeigt das)", not leer["neu"] and leer["geloescht"])

# Tabus fuers Lernen
for t in ("Das Passwort fürs WLAN ist abc", "Alex nimmt Medikament X", "laut der Mail von Amazon kommt das Paket",
          "[Kennwort]"):
    pruef("Tabu: " + t, gd.TABU_LERNEN.search(t))
pruef("kein Tabu: Vorliebe", not gd.TABU_LERNEN.search("Alex hört den Denon meist auf Lautstärke 40"))

print("Gedächtnis und Personen: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
