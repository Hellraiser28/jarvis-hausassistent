#!/usr/bin/env python3
"""Neu in dieser Version (PC-Client ab 16): neuigkeiten_offen() aus jarvis_pc.py lesen, ohne den Client zu laden.
Neuinstallation zeigt nichts, ein Update zeigt einmal, jede Version hat Punkte in beiden Sprachen.
Laeuft im Repo (tests/ neben spiegel/pc/) und in der Release-Vorlage (neben jarvis_pc.py)."""
import ast
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
for pfad in (os.path.join(HIER, "..", "spiegel", "pc", "jarvis_pc.py"), os.path.join(HIER, "jarvis_pc.py")):
    if os.path.exists(pfad):
        break
else:
    sys.exit("jarvis_pc.py nicht gefunden")

baum = ast.parse(open(pfad, encoding="utf-8").read())
teile = [n for n in baum.body if (isinstance(n, ast.Assign) and any(isinstance(z, ast.Name) and z.id in (
    "NEUIGKEITEN", "VERSION") for z in n.targets)) or (isinstance(n, ast.FunctionDef) and n.name == "neuigkeiten_offen")]
fehler = 0


def lauf(einstellungen, sprache="de"):
    u = {"E": einstellungen, "SPRACHE": sprache,
         "BESTAND": "zuletzt_version" in einstellungen or bool(einstellungen.get("desktop_symbol_angelegt"))}
    exec(compile(ast.Module(body=teile, type_ignores=[]), pfad, "exec"), u)
    return u["neuigkeiten_offen"](), u["VERSION"], u["NEUIGKEITEN"]


def pruefe(name, ist, soll):
    global fehler
    if ist != soll:
        fehler += 1
        print("FEHLER %s: %r statt %r" % (name, ist, soll))


offen, version, alle = lauf({})
pruefe("Neuinstallation: nichts", offen, [])
offen, _, _ = lauf({"desktop_symbol_angelegt": True})
pruefe("Update von vor 16: aktuelle Version zuerst", [o["titel"] for o in offen][:1], [alle[version]["titel"]])
offen, _, _ = lauf({"desktop_symbol_angelegt": True, "zuletzt_version": version})
pruefe("schon gesehen: nichts", offen, [])
offen, _, _ = lauf({"zuletzt_version": version - 1}, "en")
pruefe("englisch", offen[0]["punkte"], alle[version]["en"])
for v, n in alle.items():
    pruefe("Version %d hat de und en gleich viele Punkte" % v, len(n.get("de", [])) == len(n.get("en", [])) > 0, True)
pruefe("aktuelle Version hat Neuigkeiten", version in alle, True)

print("Neuigkeiten: %d Fehler" % fehler)
sys.exit(1 if fehler else 0)
