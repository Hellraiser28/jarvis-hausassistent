#!/usr/bin/env python3
"""PC-Client 21: pc_werte() aus jarvis_pc.py lesen, ohne den Client zu laden (wie test_neuigkeiten.py). Die
Windows-Schnittstellen (kernel32, Laufwerke, nvidia-smi) sind Attrappen; geprueft wird die Rechnung, nicht Windows.
Laeuft im Repo (tests/ neben spiegel/pc/) und in der Release-Vorlage (neben jarvis_pc.py)."""
import ast
import collections
import ctypes
import os
import re
import subprocess
import sys
import types

HIER = os.path.dirname(os.path.abspath(__file__))
for pfad in (os.path.join(HIER, "..", "spiegel", "pc", "jarvis_pc.py"), os.path.join(HIER, "jarvis_pc.py")):
    if os.path.exists(pfad):
        break
else:
    sys.exit("jarvis_pc.py nicht gefunden")
NAMEN = ("_FILETIME", "_SPEICHERSTATUS", "_NVIDIA", "_cpu_zeiten", "_gpu", "pc_werte")
baum = ast.parse(open(pfad, encoding="utf-8").read())
teile = [n for n in baum.body if (isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in NAMEN) or
         (isinstance(n, ast.Assign) and any(isinstance(z, ast.Name) and z.id in NAMEN for z in n.targets))]
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


class Kernel:
    def __init__(self):
        self.zeiten = [(1000, 4000), (1600, 5000)]     # (Leerlauf, Kernel+Nutzer) je Aufruf: 600 von 1000 leer -> 40 %
        self.aufruf = 0

    def GetSystemTimes(self, leer, kern, nutzer):
        l, g = self.zeiten[min(self.aufruf, len(self.zeiten) - 1)]
        self.aufruf += 1
        leer._obj.lo, leer._obj.hi = l, 0
        kern._obj.lo, kern._obj.hi = g - 100, 0
        nutzer._obj.lo, nutzer._obj.hi = 100, 0
        return 1

    def GlobalMemoryStatusEx(self, m):
        m._obj.dwMemoryLoad, m._obj.ullTotalPhys = 55, 32 * 2 ** 30
        return 1

    def GetLogicalDrives(self):
        return (1 << 2) | (1 << 3) | (1 << 4)           # C, D, E

    def GetDriveTypeW(self, lw):
        return 2 if lw.startswith("E") else 3           # E ist ein USB-Stick


Platz = collections.namedtuple("Platz", "total used free")


def lauf(gpu_ausgabe="NVIDIA GeForce RTX 4070, 37, 52, 2048, 11264\n", gpu_pfad="/x/nvidia-smi", rc=0):
    k = Kernel()
    fake_ctypes = types.SimpleNamespace(Structure=ctypes.Structure, c_uint32=ctypes.c_uint32, c_uint64=ctypes.c_uint64,
                                        byref=ctypes.byref, sizeof=ctypes.sizeof, windll=types.SimpleNamespace(kernel32=k))
    fake_shutil = types.SimpleNamespace(which=lambda n: gpu_pfad,
                                        disk_usage=lambda lw: Platz(1000 * 2 ** 30, 840 * 2 ** 30, 160 * 2 ** 30) if lw.startswith("C")
                                        else Platz(4000 * 2 ** 30, 1000 * 2 ** 30, 3000 * 2 ** 30))
    fake_sub = types.SimpleNamespace(SubprocessError=subprocess.SubprocessError,
                                     run=lambda *a, **kw: types.SimpleNamespace(stdout=gpu_ausgabe, returncode=rc))
    u = {"ctypes": fake_ctypes, "shutil": fake_shutil, "subprocess": fake_sub, "re": re, "WINDOWS": True}
    exec(compile(ast.Module(body=teile, type_ignores=[]), pfad, "exec"), u)
    vorher = u["_cpu_zeiten"]()
    return u["pc_werte"](vorher)[0]


pruef("Alle Teile gefunden", {getattr(n, "name", None) or n.targets[0].id for n in teile} == set(NAMEN))
w = lauf()
pruef("CPU ueber das Intervall", w["cpu"] == 40.0, w)
pruef("RAM und Groesse", w["ram"] == 55 and w["ram_gib"] == 32.0, w)
pruef("Nur feste Laufwerke", w["platten"] == [["C:", 84, 1000], ["D:", 25, 4000]], w["platten"])
pruef("Grafikkarte", w["gpu"] == {"name": "NVIDIA GeForce RTX 4070", "last": 37.0, "temp": 52.0, "speicher": 18.2}, w["gpu"])
pruef("Ohne nvidia-smi keine Grafikkarte", lauf(gpu_pfad=None)["gpu"] is None)
pruef("nvidia-smi mit Fehler -> keine Grafikkarte", lauf(rc=9)["gpu"] is None)
pruef("Kaputte Ausgabe -> Zahlen leer, kein Absturz", lauf(gpu_ausgabe="NVIDIA X, [N/A], 50, 1, 0\n")["gpu"]["last"] is None)
print("PC-Werte: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
