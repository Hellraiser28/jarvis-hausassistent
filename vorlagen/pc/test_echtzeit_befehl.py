#!/usr/bin/env python3
"""Echtzeit-Befehl des PC-Clients (seit Version 15): Muster aus jarvis_pc.py lesen, ohne den Client zu laden (der
braucht Windows-Bibliotheken). Faelle mit den echten Erkennungen vom 26.10.2026 (Kroko: "Javis, Echtzeit").
Laeuft im Repo (tests/ neben spiegel/pc/) und in der Release-Vorlage (neben jarvis_pc.py)."""
import ast
import os
import re
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
for pfad in (os.path.join(HIER, "..", "spiegel", "pc", "jarvis_pc.py"), os.path.join(HIER, "jarvis_pc.py")):
    if os.path.exists(pfad):
        break
else:
    sys.exit("jarvis_pc.py nicht gefunden")

baum = ast.parse(open(pfad, encoding="utf-8").read())
teile = [n for n in baum.body if isinstance(n, ast.Assign) and any(
    isinstance(z, ast.Name) and z.id in ("_KEIN_NAME", "ECHTZEIT_BEFEHL") for z in n.targets)]
umgebung = {"re": re}
exec(compile(ast.Module(body=teile, type_ignores=[]), pfad, "exec"), umgebung)
MUSTER = umgebung["ECHTZEIT_BEFEHL"]


def befehl(text):
    return bool(MUSTER.fullmatch(text.strip().lower()))


JA = ["Echtzeit", "Echtzeit.", "Javis, Echtzeit", "Jarvis, Echtzeit", "Javes Echtzeit", "Starte Echtzeit",
      "Start Echtzeit", "Echtzeitmodus an", "Mach Echtzeit an", "Jarvis, starte den Echtzeitmodus", "Bitte Echtzeit",
      "Hey Javis, Echtzeit", "Friday, Echtzeit", "Echt Zeit", "Real time", "Real-time.", "Start real time",
      "Jarvis, real time", "Turn on real time mode", "Realtime please", "Hey Jarvis, start the real time mode"]
NEIN = ["Was ist Echtzeit?", "Wie funktioniert der Echtzeitmodus?", "Kein Echtzeit", "Nicht Echtzeit", "Echtzeit aus",
        "Stopp Echtzeit", "Erzähl mir was über Echtzeit", "Echtzeit ist toll", "What is real time?", "No real time",
        "Stop real time", "Real time off", "Wie wird das Wetter morgen?", "", "Danke"]

fehler = [("soll Befehl sein", t) for t in JA if not befehl(t)] + [("soll keiner sein", t) for t in NEIN if befehl(t)]
for art, t in fehler:
    print("FEHLER (%s): %r" % (art, t))
print("Echtzeit-Befehl: %d/%d" % (len(JA) + len(NEIN) - len(fehler), len(JA) + len(NEIN)))
sys.exit(1 if fehler else 0)
