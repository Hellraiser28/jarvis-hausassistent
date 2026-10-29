#!/usr/bin/env python3
"""Baustein lage.py (Reiter "Lage" im Observatorium, seit 0.5.1): PC-Werte, Volumes, Container, Sicherung.
Testordner und Attrappen, keine Netzzugriffe, kein echtes Docker."""
import os
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import lage  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


# ---------------------------------------------------------------- PC-Werte (POST /v1/pc/werte)
w = lage.pc_werte_pruefen({"cpu": 140, "ram": 55, "ram_gib": 32, "fremd": "weg",
                           "platten": [["C:", 84, 1000], ["X:\\\\boese", 1], ["D:", "viel"], "Unsinn", ["E:", -5, True]],
                           "gpu": {"name": "NVIDIA <b>RTX</b> 4070", "last": 37, "temp": 52, "speicher": 18.2}})
pruef("PC: Prozent begrenzt", w["cpu"] == 100.0 and w["ram"] == 55.0 and w["ram_gib"] == 32.0, w)
pruef("PC: nur gueltige Laufwerke", w["platten"] == [["C:", 84.0, 1000], ["E:", 0.0, None]], w["platten"])
pruef("PC: Grafikkartenname bereinigt", w["gpu"]["name"] == "NVIDIA bRTXb 4070" and w["gpu"]["temp"] == 52.0, w["gpu"])
pruef("PC: fremde Felder weg", set(w) == {"cpu", "ram", "ram_gib", "platten", "gpu"}, w)
pruef("PC: Wahrheitswerte sind keine Zahlen", lage.pc_werte_pruefen({"cpu": True, "ram_gib": True})["cpu"] is None
      and lage.pc_werte_pruefen({"ram_gib": True})["ram_gib"] is None)
pruef("PC: hoechstens 8 Laufwerke", len(lage.pc_werte_pruefen({"platten": [["C:", 1]] * 20})["platten"]) == 8)
for roh in ("text", None, [1, 2]):
    try:
        lage.pc_werte_pruefen(roh)
        pruef("PC: %r abgelehnt" % (roh,), False)
    except ValueError:
        pruef("PC: %r abgelehnt" % (roh,), True)
e = lage.pc_eintrag(w, 1000, True, jetzt=1030)
pruef("PC-Eintrag: frisch mit Alter", e and e["alter_s"] == 30 and e["cpu"] == 100.0 and "alter_s" not in w, e)
pruef("PC-Eintrag: zu alt", lage.pc_eintrag(w, 1000, True, jetzt=1000 + lage.PC_MAX_ALTER + 1) is None)
pruef("PC-Eintrag: PC getrennt", lage.pc_eintrag(w, 1000, False, jetzt=1010) is None)
pruef("PC-Eintrag: nie gemeldet", lage.pc_eintrag(None, 0, True, jetzt=1010) is None)

# ---------------------------------------------------------------- Volumes
T = tempfile.mkdtemp(prefix="lage-")
v = lage.volumes([("Daten\x07", T), ("fehlt", os.path.join(T, "gibt-es-nicht"))] + [("x", T)] * 10)
pruef("Volumes: erreichbare Pfade, hoechstens 6", len(v) == 5 and v[0][0] == "Daten" and 0 <= v[0][1] <= 100, v)

# ---------------------------------------------------------------- Container
DOCKER = "\n".join(["web\trunning\tUp 3 hours (healthy)", "db\trunning\tUp 3 hours (unhealthy)",
                    "job\texited\tExited (0) 2 hours ago", "neu\tcreated\tCreated", "wackel\trestarting\tRestarting (1) 5 s ago",
                    "alt\tdead\tDead", "kaputt", "\trunning\tUp"])
c = lage.docker_auswerten(DOCKER)
pruef("Docker: Zahlen", (c["laufend"], c["gesamt"], c["ungesund"], c["neustart"], c["tot"]) == (2, 6, 1, 1, 1), c)
pruef("Docker: Problemnamen", c["probleme"] == ["alt", "db", "wackel"], c["probleme"])
pruef("Docker: gestoppte getrennt", c["gestoppt"] == ["job", "neu"], c["gestoppt"])
pruef("Docker: nicht erreichbar -> None", lage.docker_lage(befehl=(os.path.join(T, "kein-docker"),)) is None)
pruef("Docker: Fehlercode -> None", lage.docker_lage(befehl=(sys.executable, "-c", "import sys; sys.exit(1)", "--")) is None)
skript = os.path.join(T, "docker_attrappe.py")
open(skript, "w", encoding="utf-8").write("import sys\nprint('a\\trunning\\tUp 1 hour')\nprint('b\\texited\\tExited (0)')\n")
c2 = lage.docker_lage(befehl=(sys.executable, skript))
pruef("Docker: ueber den Befehl", c2 and c2["laufend"] == 1 and c2["gesamt"] == 2 and c2["gestoppt"] == ["b"], c2)
c3 = lage.container_eintrag("viele", -1, True, 2, None, ["a\x1b[31m", " ", "b" * 99] + ["x"] * 30, ["g"] * 50)
pruef("Container: eigene Zahlen geprueft", c3["laufend"] is None and c3["gesamt"] is None and c3["ungesund"] == 0
      and c3["neustart"] == 2 and c3["tot"] == 0, c3)
pruef("Container: Namen bereinigt und begrenzt", c3["probleme"][0] == "a[31m" and len(c3["probleme"][1]) == 60
      and len(c3["probleme"]) == 19 and len(c3["gestoppt"]) == 30, c3["probleme"][:3])

# ---------------------------------------------------------------- Sicherung
pruef("Sicherung: ok", lage.sicherung_eintrag("Fotos", True, 21.6) == {"name": "Fotos", "ok": True, "alter_h": 22})
pruef("Sicherung: nur True ist ok", lage.sicherung_eintrag("Fotos", "ja", -3) == {"name": "Fotos", "ok": False, "alter_h": None})
print("Lage: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
