#!/usr/bin/env python3
"""PC-Client 24 und HUD (seit 0.7): reine Logik, ohne den Client zu laden (der braucht
Windows-Bibliotheken) und ohne Netz. Teile aus jarvis_pc.py werden wie in test_pc_werte.py ueber ast gelesen, Windows ist
eine Attrappe; die HUD-Logik (Befehlspalette, Groesste Last) laeuft mit node, falls vorhanden.

(1) P1 Tastenkuerzel Strg+Alt+J: Konstanten, Einstellung (Standard an), Nachrichtenschleife, Registrierung belegt/frei,
    Ausloesen (Mikrofon, Echtzeit, ohne Fenster), Zahnrad (einstellungen/einstellen).
(2) P3 Groesste Last: Programmname, Stichprobe aus Get-Process-JSON, Top 5 CPU + Top 3 RAM aus zwei Stichproben
    (Zusammenfassen gleichnamiger Prozesse, neue Prozesse, wiederverwendete Ids, fehlende CPU-Zeit, hoechstens 8).
(3) Ein Fokus-Modus gehoert nicht zu Client 24: kein Fokus im Client, in den Neuigkeiten und im HUD.
(4) HUD mit node: palNorm, palEintraege, palFiltern, lastListe; Fokus-Funktionen gibt es nicht mehr.
(5) HUD als Text: Verdrahtung (Strg+K, Senden nur im PC-Fenster, 30-s-Abfrage, Texte de/en, reduzierte Bewegung).
Aufruf: python3 -B tests/test_pc_ideen.py"""
import ast
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unicodedata
import urllib.error

HIER = os.path.dirname(os.path.abspath(__file__))
# Laeuft im Repo (tests/ neben spiegel/) und in der Release-Vorlage (vorlagen/pc/ neben jarvis_pc.py, HUD in vorlagen/hud/)
PC = next((p for p in (os.path.join(HIER, "..", "spiegel", "pc", "jarvis_pc.py"), os.path.join(HIER, "jarvis_pc.py"))
           if os.path.exists(p)), None)
HUD = next((p for p in (os.path.join(HIER, "..", "spiegel", "hud", "index.html"), os.path.join(HIER, "..", "hud", "index.html"))
            if os.path.exists(p)), None)
if not PC or not HUD:
    sys.exit("jarvis_pc.py oder hud/index.html nicht gefunden")
quelle = open(PC, encoding="utf-8").read()
baum = ast.parse(quelle)
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:220]) if info and not bed else ""))


def _namen(n):
    if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
        return {n.name}
    if isinstance(n, ast.Assign):
        aus = set()
        for z in n.targets:
            for x in (z.elts if isinstance(z, ast.Tuple) else [z]):
                if isinstance(x, ast.Name):
                    aus.add(x.id)
        return aus
    return set()


def teile(*namen):
    gesucht = set(namen)
    gefunden = [n for n in baum.body if _namen(n) & gesucht]
    fehlt = gesucht - set().union(*(_namen(n) for n in gefunden)) if gefunden else gesucht
    if fehlt:
        raise SystemExit("in jarvis_pc.py nicht gefunden: %s" % ", ".join(sorted(fehlt)))
    return gefunden


def ausfuehren(knoten, u):
    exec(compile(ast.fix_missing_locations(ast.Module(body=knoten, type_ignores=[])), PC, "exec"), u)
    return u


def api_klasse(u, *methoden):
    api = next(n for n in baum.body if isinstance(n, ast.ClassDef) and n.name == "Api")
    body = [n for n in api.body if isinstance(n, ast.FunctionDef) and n.name in methoden]
    if {n.name for n in body} != set(methoden):
        raise SystemExit("Api-Methoden fehlen: %s" % (set(methoden) - {n.name for n in body}))
    return ausfuehren([ast.ClassDef(name="Api", bases=[], keywords=[], body=body, decorator_list=[])], u)["Api"]()


class Log:
    def __init__(self):
        self.zeilen = []

    def _z(self, *a):
        self.zeilen.append(a[0] % a[1:] if len(a) > 1 else a[0])

    info = warning = error = _z


# ======================================================================== (1) P1 Tastenkuerzel
K = ausfuehren(teile("VERSION", "NEUIGKEITEN", "KUERZEL_ID", "MOD_ALT", "KUERZEL_MODS", "WM_HOTKEY", "KUERZEL"), {})
pruef("Version ab 24 (seit 0.7.0: 25)", K["VERSION"] >= 24, K["VERSION"])
n24 = K["NEUIGKEITEN"].get(24, {})
pruef("Neuigkeiten 24: de und en, gleich viele Punkte", len(n24.get("de", [])) == len(n24.get("en", [])) == 3, n24)
t24 = " ".join(n24.get("de", []))
pruef("Neuigkeiten 24 nennen Strg+Alt+J, Strg+K und Größte Last",
      all(w in t24 for w in ("Strg+Alt+J", "Strg+K", "Größte Last")), t24)
pruef("Kuerzel: Strg+Alt ohne Wiederholung, Taste J", K["KUERZEL_MODS"] == 0x0002 | 0x0001 | 0x4000 and K["KUERZEL_TASTE"] == 0x4A)
pruef("Kuerzel: WM_HOTKEY 0x0312, WM_QUIT 0x0012", K["WM_HOTKEY"] == 0x0312 and K["WM_QUIT"] == 0x0012)
pruef("Kuerzel: Kennung im Bereich fuer Anwendungen (0x0000-0xBFFF)", 0 <= K["KUERZEL_ID"] <= 0xBFFF, hex(K["KUERZEL_ID"]))

for e, soll, name in (({}, True, "fehlt"), ({"tastenkuerzel": True}, True, "true"), ({"tastenkuerzel": False}, False, "false")):
    u = ausfuehren(teile("kuerzel_einstellung"), {"E": e})
    pruef("Einstellung tastenkuerzel %s -> %s" % (name, soll), u["kuerzel_einstellung"]() is soll)


class Fn:
    """Attrappe einer DLL-Funktion: aufrufbar, argtypes/restype setzbar."""

    def __init__(self, fn):
        self.fn, self.aufrufe = fn, []

    def __call__(self, *a):
        self.aufrufe.append(a)
        return self.fn(*a)


def user32(nachrichten, registrieren=1):
    """nachrichten: Liste von (message, wParam) oder Rueckgabewert 0/-1 fuer GetMessageW."""
    folge = list(nachrichten)

    def get(ptr, *_):
        x = folge.pop(0) if folge else 0
        if isinstance(x, tuple):
            ptr._obj.message, ptr._obj.wParam = x
            return 1
        return x
    return types.SimpleNamespace(GetMessageW=Fn(get), PeekMessageW=Fn(lambda *a: 0), RegisterHotKey=Fn(lambda *a: registrieren),
                                 UnregisterHotKey=Fn(lambda *a: 1), PostThreadMessageW=Fn(lambda *a: 1))


SCHLEIFE = teile("KUERZEL_ID", "WM_HOTKEY", "_kuerzel_schleife")
gezaehlt = []
u = ausfuehren(SCHLEIFE, {"ctypes": ctypes, "log": Log()})
from ctypes import wintypes  # noqa: E402  (laeuft auch unter Linux)
m = wintypes.MSG()
uu = user32([(0x0312, 0x4A41), (0x0312, 7), (0x0100, 0x4A41), (0x0312, 0x4A41), 0])
pruef("Schleife: nur WM_HOTKEY mit eigener Kennung loest aus, WM_QUIT beendet",
      u["_kuerzel_schleife"](uu, m, lambda: gezaehlt.append(1)) == 2 and len(gezaehlt) == 2, gezaehlt)


def kaputt():
    raise RuntimeError("Fenster weg")


lg = Log()
u = ausfuehren(SCHLEIFE, {"ctypes": ctypes, "log": lg})
pruef("Schleife: Fehler beim Ausloesen beendet sie nicht, -1 beendet",
      u["_kuerzel_schleife"](user32([(0x0312, 0x4A41), (0x0312, 0x4A41), -1]), m, kaputt) == 2
      and sum("Fenster weg" in z for z in lg.zeilen) == 2, lg.zeilen)

FADEN = teile("KUERZEL_ID", "MOD_ALT", "KUERZEL_MODS", "WM_HOTKEY", "_kuerzel_schleife", "kuerzel_faden")


def faden_lauf(registrieren, nachrichten):
    uu, lg, gedrueckt = user32(nachrichten, registrieren), Log(), []
    kern = types.SimpleNamespace(GetCurrentThreadId=Fn(lambda: 4242))
    fake = types.SimpleNamespace(WinDLL=lambda name, use_last_error=False: uu if name == "user32" else kern,
                                 c_int=ctypes.c_int, POINTER=ctypes.POINTER, byref=ctypes.byref, get_last_error=lambda: 1409)
    st = {"faden": None, "tid": 0, "belegt": False, "versucht": threading.Event()}
    ns = ausfuehren(FADEN, {"ctypes": fake, "log": lg, "kuerzel_gedrueckt": lambda: gedrueckt.append(1)})
    ns["KUERZEL"] = st
    ns["kuerzel_faden"]()
    return uu, lg, st, gedrueckt


uu, lg, st, g = faden_lauf(0, [])
pruef("Registrierung belegt: nur Protokoll, kein Absturz, Zustand belegt",
      st["belegt"] is True and st["tid"] == 0 and st["versucht"].is_set() and any("1409" in z for z in lg.zeilen)
      and not uu.GetMessageW.aufrufe, (st, lg.zeilen))
r = uu.RegisterHotKey.aufrufe[0]
pruef("Registrierung: ohne Fenster, Kennung, Strg+Alt+NoRepeat, J", r[0] is None and r[1:] == (0x4A41, 0x4003, 0x4A), r)
uu, lg, st, g = faden_lauf(1, [(0x0312, 0x4A41), 0])
pruef("Registrierung frei: loest aus, gibt das Kuerzel am Ende frei",
      len(g) == 1 and st["belegt"] is False and st["tid"] == 0 and len(uu.UnregisterHotKey.aufrufe) == 1
      and st["versucht"].is_set(), (g, st, uu.UnregisterHotKey.aufrufe))
pruef("Schlange vor der Registrierung angelegt (PeekMessageW)", len(uu.PeekMessageW.aufrufe) == 1)

GEDRUECKT = teile("kuerzel_gedrueckt")


class Fenster:
    def __init__(self):
        self.js = []

    def evaluate_js(self, s):
        self.js.append(s)


def drueck(mikro, echtzeit, mit_fenster=True):
    f = Fenster() if mit_fenster else None
    vorn = []
    ns = ausfuehren(GEDRUECKT, {"log": Log(), "MIKRO": {"an": mikro}, "ECHTZEIT": {"an": echtzeit}, "SOFORT_HOEREN": threading.Event(),
                                "fenster": f, "fenster_nach_vorn": lambda: vorn.append(1)})
    ns["kuerzel_gedrueckt"]()
    return ns["SOFORT_HOEREN"].is_set(), f.js if f else None, vorn


s, js, vorn = drueck(True, False)
pruef("Gedrueckt mit Mikrofon: Fenster vor, Hoerschleife ausgeloest, HUD weiss es", s and vorn and js == [
    "window.kuerzelGedrueckt && window.kuerzelGedrueckt(true)"], (s, js))
s, js, vorn = drueck(True, True)
pruef("Gedrueckt waehrend Echtzeit: nur Fenster, kein Zuhoeren", not s and vorn and js[0].endswith("(false)"), (s, js))
s, js, vorn = drueck(False, False)
pruef("Gedrueckt ohne Mikrofon: nur Fenster, HUD setzt den Cursor", not s and js[0].endswith("(false)"), (s, js))
s, js, vorn = drueck(True, False, mit_fenster=False)
pruef("Gedrueckt ohne Fenster (--ohne-fenster): hoert trotzdem zu", s and js is None)
pruef("Hoerschleife prueft das Ereignis und raeumt es auf",
      "sofort = SOFORT_HOEREN.is_set()" in quelle and quelle.count("SOFORT_HOEREN.clear()") >= 3
      and "bloecke.get(timeout=0.3)" in quelle)
pruef("start_hintergrund startet das Kuerzel nur unter Windows und nach Einstellung",
      "if WINDOWS and kuerzel_einstellung():" in quelle and 'MIKRO["an"] = True' in quelle)


def zahnrad(windows, e):
    aufrufe = []
    ns = {"E": e, "VERSION": 24, "WINDOWS": windows, "KUERZEL": {"belegt": False}, "log": Log(), "ABGELEHNT": {"fehler": "x"},
          "aus_dem_fenster": lambda n: True, "einstellungen_speichern": lambda: aufrufe.append("gespeichert"),
          "verknuepfung": lambda *a: aufrufe.append(("verknuepfung",) + a),
          "kuerzel_an": lambda warten=False: aufrufe.append(("an", warten)), "kuerzel_aus": lambda: aufrufe.append("aus")}
    ausfuehren(teile("kuerzel_einstellung"), ns)
    return api_klasse(ns, "einstellungen", "einstellen"), aufrufe, ns


a, auf, ns = zahnrad(True, {})
r = a.einstellungen()
pruef("Zahnrad Windows: Tastenkuerzel standardmaessig an, nicht belegt", r.get("tastenkuerzel") is True and r.get("tastenkuerzel_belegt") is False, r)
ns["KUERZEL"]["belegt"] = True
pruef("Zahnrad: belegt wird gemeldet", a.einstellungen()["tastenkuerzel_belegt"] is True)
r = a.einstellen("tastenkuerzel", False)
pruef("Ausschalten: gespeichert, Faden beendet, keine Verknuepfung", ns["E"]["tastenkuerzel"] is False and r["tastenkuerzel"] is False
      and auf == ["gespeichert", "aus"], auf)
del auf[:]
a.einstellen("tastenkuerzel", True)
pruef("Einschalten: Faden mit Warten auf die Registrierung", auf == ["gespeichert", ("an", True)], auf)
del auf[:]
a.einstellen("autostart", False)
pruef("Autostart wie bisher (Verknuepfung)", auf == ["gespeichert", ("verknuepfung", "Startup", False)], auf)
a, auf, ns = zahnrad(False, {})
r = a.einstellungen()
a.einstellen("tastenkuerzel", False)
pruef("Linux: kein Schalter, Einstellen wirkungslos", "tastenkuerzel" not in r and "tastenkuerzel" not in ns["E"] and not auf, (r, auf))

# ======================================================================== (2) P3 Groesste Last
P = ausfuehren(teile("PROZESSE_MAX", "prozess_name", "_zahl_oder_none", "prozess_stichprobe", "prozesse_top"),
               {"re": re, "unicodedata": unicodedata})
pn = P["prozess_name"]
pruef("Name ohne Pfad und .exe", pn(r"C:\Program Files\Google\Chrome\Application\chrome.exe") == "chrome" and pn("Code.EXE") == "Code"
      and pn("/usr/bin/python3") == "python3", pn(r"C:\x\chrome.exe"))
pruef("Name hoechstens 40 Zeichen", len(pn("A" * 60 + ".exe")) == 40)
pruef("Name ohne Steuer- und Richtungszeichen", pn("ev\u202eil\x07.exe") == "evil", repr(pn("ev\u202eil\x07.exe")))
pruef("Name leer bleibt leer", pn(None) == "" and pn("") == "")

GB = 2 ** 30
roh = [{"Id": 0, "ProcessName": "Idle", "CPU": 9999.0, "WorkingSet64": 8192},
       {"Id": 4, "ProcessName": "System", "CPU": None, "WorkingSet64": 150 * 2 ** 20},
       {"Id": 101, "ProcessName": "chrome", "CPU": 10.0, "WorkingSet64": 1 * GB},
       {"Id": True, "ProcessName": "kaputt", "CPU": 1, "WorkingSet64": 1},
       {"Id": 7, "ProcessName": "", "CPU": 1, "WorkingSet64": 1},
       "kein Objekt"]
s = P["prozess_stichprobe"](roh)
pruef("Stichprobe: Idle, kaputte und namenlose Eintraege fallen weg", set(s) == {4, 101}, s)
pruef("Stichprobe: fehlende CPU-Zeit bleibt None, Speicher in Byte", s[4] == ("System", None, 150 * 2 ** 20) and s[101] == ("chrome", 10.0, GB), s)
pruef("Stichprobe: ein einzelner Prozess kommt als Objekt", set(P["prozess_stichprobe"](
    {"Id": 9, "ProcessName": "x", "CPU": 1.5, "WorkingSet64": 10}) or {}) == {9})
pruef("Stichprobe: Unsinn -> leer", P["prozess_stichprobe"](None) == {} and P["prozess_stichprobe"]("x") == {})

MB = 2 ** 20
vorher = {101: ("chrome", 10.0, 900 * MB), 102: ("chrome", 5.0, 500 * MB), 104: ("Code", 100.0, 700 * MB),
          200: ("explorer", 50.0, 200 * MB), 300: ("svchost", None, 80 * MB), 400: ("alt", 70.0, 10 * MB),
          500: ("MsMpEng", 40.0, 300 * MB)}
jetzt = {101: ("chrome", 22.0, 1000 * MB), 102: ("chrome", 11.0, 600 * MB), 103: ("chrome", 3.0, 400 * MB),
         104: ("Code", 112.0, 800 * MB), 200: ("explorer", 50.6, 250 * MB), 300: ("svchost", 20.0, 90 * MB),
         400: ("neu", 1.2, 5 * MB), 500: ("MsMpEng", 40.0, 2100 * MB), 600: ("Memory Compression", None, 1800 * MB),
         700: ("vmmem", 300.0, 3000 * MB), 800: ("python", 4.8, 60 * MB), 900: ("Teams", 2.4, 1200 * MB)}
top = P["prozesse_top"](vorher, jetzt, 30.0, 8)
nach = {e["name"]: e for e in top}
pruef("Top: chrome zusammengefasst (12 + 6 + 3 neu = 21 s von 240 s)", nach.get("chrome", {}).get("cpu") == 8.8
      and nach["chrome"]["ram_mb"] == 2000, nach.get("chrome"))
pruef("Top: neuer Prozess zaehlt ganz, Wert auf 100 % begrenzt", nach.get("vmmem", {}).get("cpu") == 100.0, nach.get("vmmem"))
neu = P["prozesse_top"]({400: ("alt", 70.0, MB)}, {400: ("neu", 1.2, MB)}, 30.0, 8)
pruef("Top: Id wiederverwendet (alt -> neu) zaehlt als neu", neu == [{"name": "neu", "cpu": 0.5, "ram_mb": 1}], neu)
sv = P["prozesse_top"]({300: ("svchost", None, MB)}, {300: ("svchost", 20.0, 90 * MB)}, 30.0, 8)
pruef("Top: zuvor ohne CPU-Zeit -> 0, nicht die ganze Laufzeit", sv == [{"name": "svchost", "cpu": 0.0, "ram_mb": 90}], sv)
pruef("Top: erst CPU (5), dann 3 Speicher unter den uebrigen (MsMpEng hatte keine CPU-Zeit im Intervall)",
      [e["name"] for e in top] == ["vmmem", "chrome", "Code", "python", "Teams", "MsMpEng", "Memory Compression", "explorer"],
      [e["name"] for e in top])
pruef("Top: Speicher-Eintraege ohne Dubletten", len({e["name"] for e in top}) == len(top))
pruef("Top: Felder und Typen", all(set(e) == {"name", "cpu", "ram_mb"} and isinstance(e["cpu"], float)
                                   and isinstance(e["ram_mb"], int) for e in top), top)
pruef("Top: eine Nachkommastelle", all(round(e["cpu"], 1) == e["cpu"] for e in top))
viele_v = {i: ("p%d" % i, 0.0, i * MB) for i in range(1, 40)}
viele_j = {i: ("p%d" % i, float(i), i * MB) for i in range(1, 40)}
top = P["prozesse_top"](viele_v, viele_j, 10.0, 4)
pruef("Top: hoechstens 8, Speicher rueckt nach, wenn die Groessten schon bei der CPU stehen",
      [e["name"] for e in top] == ["p39", "p38", "p37", "p36", "p35", "p34", "p33", "p32"], [e["name"] for e in top])
viele_j = {i: ("p%d" % i, float(i), (100 - i) * MB) for i in range(1, 40)}
top = P["prozesse_top"](viele_v, viele_j, 10.0, 4)
pruef("Top: verschiedene CPU- und RAM-Spitzen ergeben genau 8", len(top) == 8 and [e["name"] for e in top][5:] == ["p1", "p2", "p3"], top)
pruef("Top: Grossschreibung egal beim Zusammenfassen", len(P["prozesse_top"]({1: ("Chrome", 0.0, MB)}, {1: ("Chrome", 3.0, MB), 2: ("chrome", 3.0, MB)}, 10.0, 2)) == 1)
pruef("Top: ohne erste Stichprobe keine Liste", P["prozesse_top"]({}, jetzt, 30.0, 8) == [] and P["prozesse_top"](None, jetzt, 30.0, 8) == [])
pruef("Top: ohne Intervall keine Liste", P["prozesse_top"](vorher, jetzt, 0, 8) == [] and P["prozesse_top"](vorher, jetzt, None, 8) == [])
pruef("Top: Kerne 0/None -> wie 1", P["prozesse_top"]({1: ("a", 0.0, MB)}, {1: ("a", 1.0, MB)}, 10.0, None)[0]["cpu"] == 10.0)
pruef("Top: Leerlauf -> nur die 3 groessten Speicher", [e["name"] for e in P["prozesse_top"](
    {1: ("a", 1.0, 5 * MB), 2: ("b", 1.0, 9 * MB), 3: ("c", 1.0, 7 * MB), 4: ("d", 1.0, 1 * MB)},
    {1: ("a", 1.0, 5 * MB), 2: ("b", 1.0, 9 * MB), 3: ("c", 1.0, 7 * MB), 4: ("d", 1.0, 1 * MB)}, 30.0, 8)] == ["b", "c", "a"])
pruef("werte_melden haengt prozesse an (zwei Stichproben, Intervall, logische Kerne)",
      'w["prozesse"] = top' in quelle and "prozesse_top(p_vorher[1], p_jetzt[1], p_jetzt[0] - p_vorher[0], os.cpu_count())" in quelle)
pruef("Get-Process ohne eigene PowerShell und ohne Leerlauf, als JSON", "$_.Id -ne $PID -and $_.Id -ne 0" in quelle
      and "ConvertTo-Json -Compress" in quelle)
_pl = ast.get_source_segment(quelle, next(n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name == "prozesse_lesen"))
pruef("Prozessnamen nie ins Protokoll (prozesse_lesen meldet nur den Fehlertyp)",
      re.findall(r"log\.\w+\(.*\)", _pl) == ['log.info("Prozesse: %s", type(e).__name__)']
      and not re.search(r"log\.\w+\(", ast.get_source_segment(quelle, next(n for n in baum.body if isinstance(n, ast.FunctionDef)
                                                                        and n.name == "prozesse_top"))), _pl)
pruef("pc_werte unveraendert (test_pc_werte bleibt gueltig)", "prozesse" not in ast.get_source_segment(
    quelle, next(n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name == "pc_werte")))

# ======================================================================== (3) kein Fokus-Modus
# Client 24 bringt Tastenkuerzel, Befehlspalette und Groesste Last; einen Fokus-Modus gibt es nicht
api_namen = {n.name for n in next(n for n in baum.body if isinstance(n, ast.ClassDef) and n.name == "Api").body
             if isinstance(n, ast.FunctionDef)}
pruef("Fokus raus: Api ohne fokus_status und fokus", not {"fokus_status", "fokus"} & api_namen, sorted(api_namen))
pruef("Fokus raus: keine Helfer mehr (fokus_sauber, _ganzzahl)",
      not any(_namen(n) & {"fokus_sauber", "_ganzzahl"} for n in baum.body))
pruef("Fokus raus: weder /v1/fokus noch Fokus irgendwo im Client", not re.search(r"(?i)fokus|focus", quelle),
      re.findall(r"(?i).{0,30}(?:fokus|focus).{0,30}", quelle)[:3])
pruef("Fokus raus: Neuigkeiten 24 ohne Fokus (de und en)",
      not re.search(r"(?i)fokus|focus", json.dumps(n24, ensure_ascii=False)) and "Fokus" not in n24.get("titel", ""), n24)
pruef("Kern-Funktionen der Api unberuehrt", {"frage", "einstellungen", "einstellen", "neuigkeiten"} <= api_namen)

# ======================================================================== (4) HUD-Logik mit node
hud = open(HUD, encoding="utf-8").read()
mm = re.search(r"/\*PALETTE-LOGIK-START\*/(.*?)/\*PALETTE-LOGIK-ENDE\*/", hud, re.S)
pruef("HUD: Logikblock gefunden", bool(mm))
node = next((p for p in (shutil.which("node"), os.path.expanduser("~/.local/bin/node")) if p and os.path.exists(p)), None)
if mm and node:
    PROBE = r"""
const T = (k, ...w) => k + (w.length ? "(" + w.join(",") + ")" : "");
const F = { bereiche: [
  { name: "Haus", faehigkeiten: [
    { name: "Licht", text: "Lampen schalten", beispiele: ["Mach das Licht im Wohnzimmer an", "Wie wird das Wetter?"] },
    { name: "Müllabfuhr", text: "Abfuhrtermine", nur: "Alex", beispiele: ["Wann kommt die Biotonne?"] } ] },
  { name: "Welt", faehigkeiten: [ { name: "Wetter", text: "Vorhersage", beispiele: ["Wie wird das Wetter morgen?", 5, ""] } ] } ] };
const V = [ { frage: "alte Frage", quelle: "pc" }, { frage: "Erzähl mir mehr zu dieser Schlagzeile", quelle: "meldung" },
  { frage: "Wie wird das Wetter?", quelle: "app" }, { frage: "  Wie wird das Wetter?  ", quelle: "pc-sprache" }, { frage: "x", quelle: "pc" },
  { frage: "Neueste Frage", quelle: "pc" } ];
const viele = Array.from({ length: 12 }, (_, i) => ({ frage: "Frage " + i, quelle: "pc" }));
const e0 = palEintraege(F, V, T);
const txt = (l) => l.map((x) => x.text);
const aus = {
  norm: palNorm("Größe Ärger, „Müll“!  ß"),
  e0: e0.map((x) => [x.art, x.text, x.info]),
  viele: palEintraege(null, viele, T).length,
  leer: palEintraege(undefined, undefined, T).length,
  f_wetter: txt(palFiltern(e0, "wetter")), f_mehr: txt(palFiltern(e0, "licht wohnzimmer")),
  f_akzent: txt(palFiltern(e0, "MULLABFUHR")), f_bereich: txt(palFiltern(e0, "haus")), f_nichts: palFiltern(e0, "zzz").length,
  f_alle: palFiltern(e0, "  ").length === e0.length, f_max: palFiltern(e0, "", 2).length,
  f_wort: txt(palFiltern(palEintraege({ bereiche: [{ name: "X", faehigkeiten: [{ name: "Y", beispiele: ["Spielt Radio", "Radio an"] }] }] }, [], T), "radio")),
  arten: [...new Set(e0.map((x) => x.art))].sort(),
  f_fokus: [palFiltern(e0, "fokus 30").length, palFiltern(e0, "Fokus für 45 Minuten").length, palFiltern(e0, "fokus beenden").length],
  weg: [typeof palFokusMinuten, typeof fokusLesen, typeof fokusGesamt, typeof fokusAnteil, typeof FOKUS_DAUERN],
  last: lastListe([{ name: " chrome ", cpu: 12.3, ram_mb: 2048.4 }, { name: "", cpu: 1 }, null, { name: "x".repeat(50), cpu: 300, ram_mb: -5 },
    { name: "y", cpu: "viel" }, ...Array.from({ length: 10 }, (_, i) => ({ name: "p" + i, cpu: i, ram_mb: i }))]),
  last_kein: [lastListe(undefined).length, lastListe("x").length]
};
console.log(JSON.stringify(aus));
"""
    d = tempfile.mkdtemp(prefix="pc-ideen-")
    datei = os.path.join(d, "probe.js")
    with open(datei, "w", encoding="utf-8") as f:
        f.write(mm.group(1) + "\n" + PROBE)
    p = subprocess.run([node, datei], capture_output=True, text=True, timeout=60)
    shutil.rmtree(d, ignore_errors=True)
    pruef("node: Probe laeuft", p.returncode == 0, p.stderr[-300:])
    if p.returncode == 0:
        r = json.loads(p.stdout)
        pruef("palNorm: klein, ohne Akzente, ss, ohne Satzzeichen", r["norm"] == "grosse arger mull ss", r["norm"])
        pruef("Eintraege: Fragen neueste zuerst, ohne Doppelte/Schlagzeile/zu kurz, dann Beispiele ohne Doppelte",
              [x[1] for x in r["e0"]] == ["Neueste Frage", "Wie wird das Wetter?", "alte Frage", "Mach das Licht im Wohnzimmer an",
                                          "Wann kommt die Biotonne?", "Wie wird das Wetter morgen?"], r["e0"])
        pruef("Eintraege: Arten und Herkunft", [x[0] for x in r["e0"]] == ["frage"] * 3 + ["beispiel"] * 3
              and r["e0"][0][2] == "pal_fragen" and r["e0"][4][2] == "Haus · Müllabfuhr · nur(Alex)", r["e0"])
        pruef("Eintraege: nur eigene Fragen und Beispiele, kein Fokus", r["arten"] == ["beispiel", "frage"], r["arten"])
        pruef("Suche nach Fokus findet keinen Fokus-Eintrag", r["f_fokus"] == [0, 0, 0], r["f_fokus"])
        pruef("Fokus-Funktionen gibt es nicht mehr", r["weg"] == ["undefined"] * 5, r["weg"])
        pruef("Eintraege: hoechstens 8 eigene Fragen", r["viele"] == 8, r["viele"])
        pruef("Eintraege: ohne Daten leer, kein Fehler", r["leer"] == 0)
        pruef("Filter 'wetter': Satzanfang vor Rest", r["f_wetter"] == ["Wie wird das Wetter?", "Wie wird das Wetter morgen?"], r["f_wetter"])
        pruef("Filter mehrere Woerter", r["f_mehr"] == ["Mach das Licht im Wohnzimmer an"], r["f_mehr"])
        pruef("Filter ohne Akzente (MULLABFUHR findet Müllabfuhr ueber die Faehigkeit)", r["f_akzent"] == ["Wann kommt die Biotonne?"], r["f_akzent"])
        pruef("Filter ueber den Bereich (nur drumherum = hinten)", r["f_bereich"] == ["Mach das Licht im Wohnzimmer an", "Wann kommt die Biotonne?"], r["f_bereich"])
        pruef("Filter: nichts gefunden -> leer", r["f_nichts"] == 0)
        pruef("Filter: leere Suche zeigt alles, Grenze wirkt", r["f_alle"] is True and r["f_max"] == 2)
        pruef("Filter: Satzanfang vor Wortanfang", r["f_wort"] == ["Radio an", "Spielt Radio"], r["f_wort"])
        pruef("lastListe: gekuerzt, begrenzt, ohne Namenlose, hoechstens 8",
              len(r["last"]) == 8 and r["last"][0] == {"name": "chrome", "cpu": 12.3, "ram_mb": 2048}
              and r["last"][1] == {"name": "x" * 40, "cpu": 100, "ram_mb": 0} and r["last"][2]["cpu"] == 0, r["last"][:3])
        pruef("lastListe: kein Feld oder Unsinn -> leer", r["last_kein"] == [0, 0])
elif mm:
    print("HINWEIS node fehlt, HUD-Logik nicht ausgefuehrt (nur Textpruefungen)")

# ======================================================================== (5) HUD als Text
pruef("HUD: Strg+K oeffnet und schliesst, Esc vor dem Grundriss (Erfassungsphase)",
      re.search(r'\(e\.ctrlKey \|\| e\.metaKey\) && !e\.altKey && !e\.shiftKey && \(e\.key === "k" \|\| e\.key === "K"\)', hud)
      and '}, true);' in hud[hud.find("if (PAL.offen) palZu(); else palAuf();"):][:400])
pruef("HUD: Senden nur mit pywebview.api.frage (Glance nur nachschlagen)",
      "const palSenden = () => PC() && !!(window.pywebview && window.pywebview.api && window.pywebview.api.frage);" in hud
      and "if (!palSenden()) return;" in hud and "fragen(x.text); palZu();" in hud)
pruef("HUD: Pfeiltasten, Enter, Tab bleibt im Dialog", all(s in hud for s in ('e.key === "ArrowDown"', 'e.key === "Enter"', 'e.key === "Tab"')))
pruef("HUD: Knopf im klassischen Kopf und im Observatorium", 'id="pal-knopf"' in hud and 'id="k-palette"' in hud
      and 'for (const id of ["pal-knopf", "k-palette"])' in hud)
pruef("HUD: Palette ausserhalb von .raster", 0 < hud.find('id="palette"') < hud.find('<div class="raster">'))
pruef("HUD: kein Fokus-Ring mehr (Element, CSS, JS, Abfrage)", 'id="fokus"' not in hud and "fk-" not in hud
      and not re.search(r"\.fokus\b|fkApi|fokus_status|/v1/fokus|fokus\.json|fokusAbfragen|fokusZeigen", hud),
      re.findall(r".{0,30}(?:fk-|fkApi|fokus_status|fokusAbfragen).{0,30}", hud)[:3])
pruef("HUD: Palette ohne Fokus-Eintraege (Schnellstart, beenden, freier Eintrag)", not re.search(
      r'art: "fokus"|pal-art-fokus|palFokusMinuten|fokusStarten|fokusBeenden|FOKUS_DAUERN', hud))
pruef("HUD: Fokus-Texte weg (de und en)", not re.search(r'"(?:pal_fokus\w*|fk_\w+|pal_fehler)":', hud))
pruef("HUD: Groesste Last im Reiter Lage nur mit Feld", "const last = lastListe(p.prozesse);" in hud and "if (last.length)" in hud)
pruef("HUD: Tastenkuerzel-Schalter nur, wenn der Client ihn meldet", 'k.hidden = typeof e.tastenkuerzel !== "boolean";' in hud
      and 'data-name="tastenkuerzel" hidden' in hud)
pruef("HUD: Kuerzel-Rueckruf fuer den Client", "window.kuerzelGedrueckt = function (hoert)" in hud)
pruef("HUD: reduzierte Bewegung und ruhig fuer die Palette",
      "@media (prefers-reduced-motion: reduce) { .pal-box { animation: none !important; } }" in hud
      and "html.ruhig .pal-box { animation: none; }" in hud)
neue = ["pal_knopf", "pal_titel", "pal_suche", "pal_leer", "pal_fragen", "pal_eigen", "pal_fuss_pc", "pal_fuss_glance",
        "l_last", "tastenkuerzel", "tastenkuerzel_k", "tastenkuerzel_belegt"]
fehlend = [k for k in neue if hud.count('"%s":' % k) != 2]
pruef("HUD: alle neuen Texte deutsch und englisch", not fehlend, fehlend)
pruef("HUD: Nutzertext in der Palette maskiert", "<span>${esc(x.text)}</span><small>${esc(x.info || \"\")}</small>" in hud)
pruef("HUD: Eintragsart als pal-art-* (beispiel ist schon eine Klasse)", 'class="pal-e pal-art-${x.art}' in hud
      and not re.search(r"\.pal-e\.(fokus|frage|beispiel|eigen)\b", hud))
pruef("HUD: Akzent-Bereich in palNorm als Escape, nicht als Kombinationszeichen",
      "replace(/[\\u0300-\\u036f]/g" in hud and "\u0300" not in hud)
pruef("HUD: kernBauen-Sperre wird nicht zurueckgesetzt (Knoepfe nicht doppelt)", "var kernAni, kernGebaut, kernTextSchluessel," in hud
      and not re.search(r"var [^;\n]*kernGebaut = false", hud))

print("PC-Client 24: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
