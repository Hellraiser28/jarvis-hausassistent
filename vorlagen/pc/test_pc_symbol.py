#!/usr/bin/env python3
"""PC-Client 23 (0.7): Symbol wie die App (Sternbild). Teile aus jarvis_pc.py lesen, ohne den Client zu laden.

(1) Dateien: spiegel/pc/jarvis.ico hat 16/24/32/48/64/128/256 (PNG, 32 bit), jarvis.png 256 px; die Pruefsummen in
    SYMBOL_PRUEFSUMMEN passen dazu (sonst erkennt kein Client das mitgelieferte Symbol je).
(2) symbol_bereitstellen(): ohne Netz; nimmt das mitgelieferte Symbol (Setup: jarvis.ico, Linux: jarvis.png) nur, wenn
    es genau das Sternbild ist, legt es unter neuem Namen ab, eine vorhandene richtige Kopie bleibt, eine kaputte wird
    ersetzt; ein aelteres Setup-Symbol bleibt unberuehrt.
(3) verknuepfungen_abgleichen(): stellt eine vorhandene Desktop-Verknuepfung einmal um (E["symbol"]), legt keine fehlende
    an, unter Windows dazu angeheftete und Startmenue-Verknuepfungen und die Shell-Meldung; Fehler -> beim naechsten
    Start wieder.
(4) verknuepfung(), angeheftete_umstellen() (Windows, PowerShell nur als Text), shell_symbole_auffrischen() (ctypes-Attrappe)
    und verknuepfung_linux() (echte Dateien im Testordner).
(5) Hauptteil: Symbol vor dem kopflosen Zweig bereitgestellt, kein Netz, kein Faden mehr.
Laeuft im Repo (tests/ neben spiegel/pc/) und in der Release-Vorlage (neben jarvis_pc.py, jarvis.ico, jarvis.png).
Ungeprueft bleibt hier, was nur Windows kann (WScript.Shell, Taskleiste, SHChangeNotify wirklich ausgefuehrt)."""
import ast
import hashlib
import os
import re
import shutil
import struct
import sys
import tempfile
import types

HIER = os.path.dirname(os.path.abspath(__file__))
for PCD in (os.path.join(HIER, "..", "spiegel", "pc"), HIER):
    if os.path.exists(os.path.join(PCD, "jarvis_pc.py")):
        break
else:
    sys.exit("jarvis_pc.py nicht gefunden")
PC = os.path.join(PCD, "jarvis_pc.py")
quelle = open(PC, encoding="utf-8").read()
baum = ast.parse(quelle)
KONST = ("SYMBOL_NEU", "SYMBOL_QUELLE", "SYMBOL_PRUEFSUMMEN", "SYMBOLE", "ANGEHEFTET")
FUNK = ("symbol_pfad", "symbol_bereitstellen", "verknuepfung_linux", "verknuepfung", "verknuepfungen_abgleichen",
        "angeheftete_umstellen", "shell_symbole_auffrischen")
teile = [n for n in baum.body if (isinstance(n, ast.Assign) and any(isinstance(z, ast.Name) and z.id in KONST for z in n.targets))
         or (isinstance(n, ast.FunctionDef) and n.name in FUNK)]
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:240]) if info and not bed else ""))


class Log:
    def __init__(self):
        self.zeilen = []

    def info(self, *a):
        self.zeilen.append(("info", a[0] % a[1:] if len(a) > 1 else a[0]))

    def warning(self, *a):
        self.zeilen.append(("warnung", a[0] % a[1:] if len(a) > 1 else a[0]))


class Dllfunktion:
    """Eine Funktion aus ctypes.WinDLL als Attrappe: nimmt die Aufrufe auf, argtypes/restype wie bei ctypes setzbar."""
    def __init__(self, liste):
        self.liste, self.argtypes, self.restype = liste, None, "unveraendert"

    def __call__(self, *a):
        self.liste.append(a)


class Shell32:
    """ctypes.WinDLL("shell32") als Attrappe."""
    def __init__(self, liste):
        self.SHChangeNotify = Dllfunktion(liste)


class KeinNetz:
    """urllib als Attrappe: jeder Zugriff ist ein Fehler (das Symbol kommt nur aus lokalen Dateien)."""
    def __getattr__(self, name):
        raise AssertionError("Netzzugriff: urllib.%s" % name)


def umgebung(ordner, windows=True, einst=None, ps_antwort="", dll_fehler=False):
    """Teile des Clients mit Attrappen; PowerShell und Shell32 nur aufgezeichnet, kein Netz."""
    u = {"WINDOWS": windows, "ORDNER": ordner, "VERSION": 24,
         "E": einst if einst is not None else {}, "log": Log(), "ps": [], "gespeichert": [],
         "PYTHONW": os.path.join(ordner, "venv", "Scripts", "pythonw.exe"), "__file__": os.path.join(ordner, "jarvis_pc.py"),
         "os": os, "hashlib": hashlib, "shell": [], "dlls": [], "urllib": KeinNetz()}

    def win_dll(name):
        u["dlls"].append(name)
        if dll_fehler:
            raise OSError("kein shell32")
        u["dll"] = Shell32(u["shell"])
        return u["dll"]

    import ctypes as echt_ctypes
    u["ctypes"] = types.SimpleNamespace(WinDLL=win_dll, c_long=echt_ctypes.c_long, c_uint=echt_ctypes.c_uint,
                                        c_wchar_p=echt_ctypes.c_wchar_p)

    def bruecke_echt():
        raise AssertionError("Brueckenbeweis fuer das Symbol: nicht mehr noetig")

    u["bruecke_echt"] = bruecke_echt
    u["einstellungen_speichern"] = lambda: u["gespeichert"].append(dict(u["E"]))

    def powershell(befehl, zeit=60):
        u["ps"].append(befehl)
        m = re.fullmatch(r"\[Environment\]::GetFolderPath\('(\w+)'\)", befehl)
        if befehl.startswith("$sh = "):
            return ps_antwort
        return os.path.join(ordner, m.group(1)) if m else ""

    u["powershell"] = powershell
    exec(compile(ast.Module(body=teile, type_ignores=[]), PC, "exec"), u)
    return u


def ico_eintraege(daten):
    _, typ, anzahl = struct.unpack("<HHH", daten[:6])
    aus = []
    for i in range(anzahl):
        b, h, _, _, _, bpp, groesse, start = struct.unpack("<BBBBHHII", daten[6 + 16 * i: 22 + 16 * i])
        aus.append((b or 256, h or 256, bpp, daten[start:start + 8] == b"\x89PNG\r\n\x1a\n"))
    return typ, aus


ORDNER_LISTE = []


def neuer_ordner():
    """Testordner mit Apostroph, Leerzeichen und Umlaut im Namen (wie ein Windows-Benutzer O'Brien)."""
    ORDNER_LISTE.append(tempfile.mkdtemp(prefix="pc-symbol-"))
    o = os.path.join(ORDNER_LISTE[-1], "Jarvis Ö'Brien")
    os.makedirs(o)
    return o


def aufraeumen():
    for t in ORDNER_LISTE:
        shutil.rmtree(t, ignore_errors=True)


def schreiben(pfad, daten):
    with open(pfad, "wb") as f:
        f.write(daten)


def lesen(pfad):
    with open(pfad, "rb") as f:
        return f.read()


ICO = lesen(os.path.join(PCD, "jarvis.ico"))
PNG = lesen(os.path.join(PCD, "jarvis.png"))
SHA = {"jarvis-sternbild.ico": hashlib.sha256(ICO).hexdigest(), "jarvis-sternbild.png": hashlib.sha256(PNG).hexdigest()}

# ---------------------------------------------------------------- (1) Dateien und Pruefsummen
typ, eintraege = ico_eintraege(ICO)
pruef("jarvis.ico: Symboldatei", typ == 1)
pruef("jarvis.ico: 16/24/32/48/64/128/256", sorted(e[0] for e in eintraege) == [16, 24, 32, 48, 64, 128, 256], eintraege)
pruef("jarvis.ico: quadratisch, 32 bit, PNG", all(b == h and bpp == 32 and png for b, h, bpp, png in eintraege), eintraege)
pruef("jarvis.png: 256 x 256", PNG[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", PNG[16:24]) == (256, 256))
u = umgebung(neuer_ordner())
pruef("Pruefsummen im Client = Dateien neben dem Client", u["SYMBOL_PRUEFSUMMEN"] == SHA, (u["SYMBOL_PRUEFSUMMEN"], SHA))
pruef("Windows: neues Symbol zuerst, dann rot, dann Setup", u["SYMBOLE"] == ["jarvis-sternbild.ico", "jarvis-rot.ico", "jarvis.ico"]
      and u["SYMBOL_NEU"] == "jarvis-sternbild.ico" and u["SYMBOL_QUELLE"] == "jarvis.ico")
ul = umgebung(neuer_ordner(), windows=False)
pruef("Linux: PNG", ul["SYMBOLE"] == ["jarvis-sternbild.png", "jarvis.png"] and ul["SYMBOL_NEU"] == "jarvis-sternbild.png"
      and ul["SYMBOL_QUELLE"] == "jarvis.png")
pruef("Neuer Name (Windows haelt Symbole je Pfad)", u["SYMBOL_NEU"] != u["SYMBOL_QUELLE"] and ul["SYMBOL_NEU"] != ul["SYMBOL_QUELLE"])

# ---------------------------------------------------------------- (2) symbol_bereitstellen (ohne Netz)
o = neuer_ordner()
u = umgebung(o)
pruef("nichts mitgeliefert: False, nichts angelegt", u["symbol_bereitstellen"]() is False and os.listdir(o) == [], os.listdir(o))
schreiben(os.path.join(o, "jarvis.ico"), b"altes Setup-Symbol")
u = umgebung(o)
pruef("aelteres Setup-Symbol: False, bleibt unberuehrt", u["symbol_bereitstellen"]() is False
      and sorted(os.listdir(o)) == ["jarvis.ico"] and lesen(os.path.join(o, "jarvis.ico")) == b"altes Setup-Symbol")
pruef("aelteres Setup-Symbol: Hinweis im Protokoll", any("nicht das Sternbild" in z for _, z in u["log"].zeilen), u["log"].zeilen)
schreiben(os.path.join(o, "jarvis.ico"), ICO)
u = umgebung(o)
pruef("Setup bringt das Sternbild: True", u["symbol_bereitstellen"]() is True)
pruef("Setup bringt das Sternbild: unter neuem Namen abgelegt", lesen(os.path.join(o, "jarvis-sternbild.ico")) == ICO)
pruef("Setup-Datei bleibt, wie sie ist", lesen(os.path.join(o, "jarvis.ico")) == ICO)
pruef("keine .neu-Reste", not [n for n in os.listdir(o) if n.endswith(".neu")])
os.remove(os.path.join(o, "jarvis.ico"))
u = umgebung(o)
pruef("Kopie vorhanden und richtig: True, auch ohne Setup-Datei", u["symbol_bereitstellen"]() is True)
schreiben(os.path.join(o, "jarvis-sternbild.ico"), b"kaputt")
schreiben(os.path.join(o, "jarvis.ico"), ICO)
u = umgebung(o)
pruef("kaputte Kopie wird aus der Setup-Datei ersetzt", u["symbol_bereitstellen"]() is True
      and lesen(os.path.join(o, "jarvis-sternbild.ico")) == ICO)
o = neuer_ordner()
schreiben(os.path.join(o, "jarvis.ico"), ICO + b"\0" * (1024 * 1024))
u = umgebung(o)
pruef("ueber 1 MB: nein", u["symbol_bereitstellen"]() is False and not os.path.exists(os.path.join(o, "jarvis-sternbild.ico")))
o = neuer_ordner()
schreiben(os.path.join(o, "jarvis.ico"), ICO[:-1] + b"x")
u = umgebung(o)
pruef("eine Stelle anders: nein", u["symbol_bereitstellen"]() is False and not os.path.exists(os.path.join(o, "jarvis-sternbild.ico")))
o = neuer_ordner()
schreiben(os.path.join(o, "jarvis.png"), PNG)
schreiben(os.path.join(o, "jarvis.ico"), ICO)
u = umgebung(o, windows=False)
pruef("Linux: aus jarvis.png wird jarvis-sternbild.png", u["symbol_bereitstellen"]() is True
      and lesen(os.path.join(o, "jarvis-sternbild.png")) == PNG and not os.path.exists(os.path.join(o, "jarvis-sternbild.ico")))
o = neuer_ordner()
schreiben(os.path.join(o, "jarvis.png"), ICO)
u = umgebung(o, windows=False)
pruef("Linux: ICO unter dem PNG-Namen gilt nicht", u["symbol_bereitstellen"]() is False)
o = neuer_ordner()
schreiben(os.path.join(o, "jarvis.ico"), ICO)
os.makedirs(os.path.join(o, "jarvis-sternbild.ico.neu"))      # Schreiben scheitert (Ordner im Weg)
u = umgebung(o)
pruef("Schreibfehler: False, Warnung, kein Absturz", u["symbol_bereitstellen"]() is False
      and any(a == "warnung" for a, _ in u["log"].zeilen), u["log"].zeilen)

# symbol_pfad: neuestes vorhandenes
o = neuer_ordner()
u = umgebung(o)
pruef("symbol_pfad: nichts da -> None", u["symbol_pfad"]() is None)
open(os.path.join(o, "jarvis.ico"), "wb").close()
pruef("symbol_pfad: nur Setup-Symbol", u["symbol_pfad"]() == os.path.join(o, "jarvis.ico"))
open(os.path.join(o, "jarvis-rot.ico"), "wb").close()
pruef("symbol_pfad: rot vor Setup", u["symbol_pfad"]() == os.path.join(o, "jarvis-rot.ico"))
open(os.path.join(o, "jarvis-sternbild.ico"), "wb").close()
pruef("symbol_pfad: Sternbild vor rot", u["symbol_pfad"]() == os.path.join(o, "jarvis-sternbild.ico"))

# ---------------------------------------------------------------- (3) verknuepfungen_abgleichen


def abgleich(einst, dateien, fehler_bei=None, windows=True, angeheftet_fehler=False):
    o = neuer_ordner()
    for n in dateien:
        open(os.path.join(o, n), "wb").close()
    u = umgebung(o, einst=einst, windows=windows)
    gerufen = []

    def verknuepfung(ort, an, nur_wenn_da=False):
        gerufen.append((ort, an, nur_wenn_da))
        if fehler_bei and fehler_bei == (ort, nur_wenn_da):
            raise OSError("PowerShell kaputt")

    def angeheftete_umstellen(symbol):
        gerufen.append(("Angeheftet", symbol))
        if angeheftet_fehler:
            raise OSError("PowerShell kaputt")
        return ["X:\\TaskBar\\Jarvis.lnk"]

    u["verknuepfung"] = verknuepfung
    u["angeheftete_umstellen"] = angeheftete_umstellen
    u["shell_symbole_auffrischen"] = lambda pfade: gerufen.append(("Shell", list(pfade)))
    u["verknuepfungen_abgleichen"]()
    u["O"] = o
    return u, gerufen


E = {"autostart": True, "desktop_symbol": True, "desktop_symbol_angelegt": True, "zuletzt_version": 22}
u, gerufen = abgleich(E, ["jarvis.ico", "jarvis-sternbild.ico"])
pruef("Update auf 23: Autostart wie immer, Desktop nur wenn da, dann Taskleiste/Startmenue, dann Shell-Meldung",
      gerufen == [("Startup", True, False), ("Desktop", True, True),
                  ("Angeheftet", os.path.join(u["O"], "jarvis-sternbild.ico")), ("Shell", ["X:\\TaskBar\\Jarvis.lnk"])], gerufen)
pruef("Update auf 23: Stand gemerkt", E.get("symbol") == "jarvis-sternbild.ico" and u["gespeichert"], E)
pruef("Update auf 23: Anzahl im Protokoll", any("1 angeheftete" in z for _, z in u["log"].zeilen), u["log"].zeilen)
u, gerufen = abgleich(E, ["jarvis.ico", "jarvis-sternbild.ico"])
pruef("naechster Start: Desktop, Taskleiste, Shell nicht nochmal", gerufen == [("Startup", True, False)], gerufen)
E2 = {"desktop_symbol_angelegt": True, "autostart": False}
u, gerufen = abgleich(E2, ["jarvis.ico"])
pruef("nur aelteres Setup-Symbol: Desktop bleibt dabei, Stand jarvis.ico", ("Desktop", True, True) in gerufen
      and E2.get("symbol") == "jarvis.ico", (gerufen, E2))
pruef("Autostart aus bleibt aus", gerufen[0] == ("Startup", False, False), gerufen)
u, gerufen = abgleich(E2, ["jarvis.ico", "jarvis-sternbild.ico"])
pruef("spaeter mit neuem Setup: dann umgestellt", ("Desktop", True, True) in gerufen and E2["symbol"] == "jarvis-sternbild.ico",
      (gerufen, E2))
E3 = {"desktop_symbol": True}
u, gerufen = abgleich(E3, ["jarvis.ico", "jarvis-sternbild.ico"])
pruef("Neuinstallation: Desktop einmal angelegt, nicht doppelt geschrieben",
      [g for g in gerufen if g[0] in ("Startup", "Desktop")] == [("Startup", True, False), ("Desktop", True, False)]
      and E3["symbol"] == "jarvis-sternbild.ico", (gerufen, E3))
E6 = {"desktop_symbol_angelegt": True}
u, gerufen = abgleich(E6, ["jarvis-sternbild.png"], windows=False)
pruef("Linux: keine Taskleisten-Suche, keine Shell-Meldung", not [g for g in gerufen if g[0] in ("Angeheftet", "Shell")]
      and E6.get("symbol") == "jarvis-sternbild.png", (gerufen, E6))
E7 = {"desktop_symbol_angelegt": True}
u, gerufen = abgleich(E7, ["jarvis-sternbild.ico"], angeheftet_fehler=True)
pruef("Fehler bei der Taskleiste: Stand nicht gemerkt, keine Shell-Meldung", "symbol" not in E7
      and not [g for g in gerufen if g[0] == "Shell"], (gerufen, E7))
E4 = {"desktop_symbol": False, "desktop_symbol_angelegt": True}
u, gerufen = abgleich(E4, ["jarvis-sternbild.ico"])
pruef("Desktop-Symbol abgeschaltet: nur vorhandene (nur_wenn_da), nichts anlegen",
      ("Desktop", True, False) not in gerufen and ("Desktop", True, True) in gerufen, gerufen)
E5 = {"desktop_symbol_angelegt": True}
u, gerufen = abgleich(E5, ["jarvis-sternbild.ico"], fehler_bei=("Desktop", True))
pruef("Fehler beim Umstellen: Stand nicht gemerkt (naechster Start versucht es wieder)", "symbol" not in E5, E5)
pruef("Fehler beim Umstellen: Warnung, kein Absturz", any(a == "warnung" for a, _ in u["log"].zeilen))
u, gerufen = abgleich({"desktop_symbol_angelegt": True}, [])
pruef("gar kein Symbol: nichts umstellen", gerufen == [("Startup", True, False)], gerufen)

# ---------------------------------------------------------------- (4a) angeheftete_umstellen und shell_symbole_auffrischen
o = neuer_ordner()
sym = os.path.join(o, "jarvis-sternbild.ico")
u = umgebung(o, windows=False)
pruef("Linux: angeheftete_umstellen tut nichts", u["angeheftete_umstellen"](sym) == [] and u["ps"] == [])
u = umgebung(o)
pruef("ohne Symbol: nichts", u["angeheftete_umstellen"](None) == [] and u["ps"] == [])
u = umgebung(o, ps_antwort="Warnung von irgendwas\r\nC:\\U\\TaskBar\\Jarvis.lnk\r\n\r\nC:\\U\\Programs\\J\\Jarvis.lnk\r\n")
erg = u["angeheftete_umstellen"](sym)
pruef("liefert nur die .lnk-Zeilen", erg == ["C:\\U\\TaskBar\\Jarvis.lnk", "C:\\U\\Programs\\J\\Jarvis.lnk"], erg)
b = u["ps"][0] if u["ps"] else ""
qq = lambda t: t.replace("'", "''")      # noqa: E731
pruef("ein PowerShell-Aufruf", len(u["ps"]) == 1, u["ps"])
pruef("PowerShell: Ziel, Symbol und Skript mit verdoppeltem Apostroph", ("$ziel = '%s'" % qq(u["PYTHONW"])) in b
      and ("$symbol = '%s'" % qq(sym)) in b and ("'%s'" % qq(os.path.join(o, "jarvis_pc.py"))) in b, b)
pruef("PowerShell: Taskleiste und eigenes Startmenue", "Join-Path $env:APPDATA '%s'" % u["ANGEHEFTET"] in b
      and "[Environment]::GetFolderPath('Programs')" in b and u["ANGEHEFTET"].endswith("User Pinned\\TaskBar"), b)
pruef("PowerShell: nur eigene (Ziel und Skript), nur IconLocation", "-ine $ziel" in b and "IndexOf($k" in b
      and "$s.IconLocation = $symbol; $s.Save()" in b and "TargetPath =" not in b and "Arguments =" not in b, b)
pruef("PowerShell: nichts anheften, nichts loeschen", not re.search(r"(?i)pin|Remove-Item|Delete|New-Item|Copy-Item|Verb",
                                                                    b.replace(u["ANGEHEFTET"], "")), b)
pruef("PowerShell: keine doppelten Anfuehrungszeichen (Befehlszeile)", '"' not in b, b)

u = umgebung(o)
u["shell_symbole_auffrischen"](["C:\\a\\Jarvis.lnk", "C:\\b\\Jarvis.lnk"])
pruef("Shell: eigene shell32-Instanz", u["dlls"] == ["shell32"], u["dlls"])
pruef("Shell: SHCNE_UPDATEITEM je Pfad, dann SHCNE_ASSOCCHANGED", u["shell"] == [
    (0x00002000, 0x0005, "C:\\a\\Jarvis.lnk", None), (0x00002000, 0x0005, "C:\\b\\Jarvis.lnk", None),
    (0x08000000, 0x0000, None, None)], u["shell"])
pruef("Shell: argtypes gesetzt (Breitzeichen fuer die Pfade)", u["dll"].SHChangeNotify.argtypes[2] is u["ctypes"].c_wchar_p
      and u["dll"].SHChangeNotify.restype is None)
u = umgebung(o)
u["shell_symbole_auffrischen"]([])
pruef("Shell: ohne umgestellte Pfade trotzdem einmal ASSOCCHANGED", u["shell"] == [(0x08000000, 0x0000, None, None)], u["shell"])
u = umgebung(o, dll_fehler=True)
u["shell_symbole_auffrischen"](["C:\\a\\Jarvis.lnk"])
pruef("Shell: Fehler nur ins Protokoll", any("Symbol-Zwischenspeicher" in z for _, z in u["log"].zeilen))
u = umgebung(o, windows=False)
u["shell_symbole_auffrischen"](["x"])
pruef("Shell: unter Linux nichts", u["dlls"] == [] and u["shell"] == [])

# ---------------------------------------------------------------- (4) verknuepfung (Windows) und verknuepfung_linux
o = neuer_ordner()
os.makedirs(os.path.join(o, "Desktop"))
open(os.path.join(o, "jarvis-sternbild.ico"), "wb").close()
u = umgebung(o)
u["verknuepfung"]("Desktop", True, nur_wenn_da=True)
pruef("Windows: fehlende Desktop-Verknuepfung wird nicht angelegt", not [b for b in u["ps"] if "CreateShortcut" in b], u["ps"])
open(os.path.join(o, "Desktop", "Jarvis.lnk"), "wb").close()
u = umgebung(o)
u["verknuepfung"]("Desktop", True, nur_wenn_da=True)
b = [b for b in u["ps"] if "CreateShortcut" in b]
pruef("Windows: vorhandene bekommt das Sternbild", len(b) == 1 and ("$s.IconLocation = '%s'" % os.path.join(o, "jarvis-sternbild.ico").replace("'", "''")) in b[0], b)
pruef("Windows: Apostroph im Pfad verdoppelt", b and "Ö''Brien" in b[0] and "Ö'Brien" not in b[0].replace("Ö''Brien", ""), b)
os.remove(os.path.join(o, "jarvis-sternbild.ico"))
u = umgebung(o)
u["verknuepfung"]("Desktop", True, nur_wenn_da=True)
b = [b for b in u["ps"] if "CreateShortcut" in b]
pruef("Windows: ohne Symboldatei kein IconLocation", b and "IconLocation" not in b[0], b)

o = neuer_ordner()
alt_xdg = (os.environ.get("XDG_CONFIG_HOME"), os.environ.get("XDG_DATA_HOME"))
os.environ["XDG_CONFIG_HOME"], os.environ["XDG_DATA_HOME"] = os.path.join(o, "konfig"), os.path.join(o, "daten")
menue = os.path.join(o, "daten", "applications", "jarvis.desktop")
start = os.path.join(o, "konfig", "autostart", "jarvis.desktop")
open(os.path.join(o, "jarvis.png"), "wb").close()
ul = umgebung(o, windows=False)
ul["verknuepfung"]("Desktop", True, nur_wenn_da=True)
pruef("Linux: fehlender Menueeintrag wird nicht angelegt", not os.path.exists(menue))
ul["verknuepfung"]("Desktop", True)
pruef("Linux: Menueeintrag mit jarvis.png", "Icon=%s\n" % os.path.join(o, "jarvis.png") in open(menue, encoding="utf-8").read())
open(os.path.join(o, "jarvis-sternbild.png"), "wb").close()
ul["verknuepfung"]("Desktop", True, nur_wenn_da=True)
inhalt = open(menue, encoding="utf-8").read()
pruef("Linux: vorhandener Menueeintrag bekommt das Sternbild", "Icon=%s\n" % os.path.join(o, "jarvis-sternbild.png") in inhalt
      and "--fenster" in inhalt, inhalt)
ul["verknuepfung"]("Startup", True, nur_wenn_da=True)
pruef("Linux: fehlender Autostart wird nicht angelegt", not os.path.exists(start))
for k, v in zip(("XDG_CONFIG_HOME", "XDG_DATA_HOME"), alt_xdg):
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v

# ---------------------------------------------------------------- (5) Hauptteil
haupt = quelle[quelle.index('if __name__ == "__main__":'):]
pruef("Start: Symbol bereitgestellt vor dem kopflosen Zweig", 0 <= haupt.find("symbol_bereitstellen()")
      < haupt.index("kopflos(\"so eingestellt\")"))
pruef("Start: Fenster mit symbol_pfad", re.search(r"\n\s+symbol = symbol_pfad\(\)", haupt)
      and "webview.start(start_hintergrund, icon=symbol" in haupt)
pruef("kein Symbol-Download mehr (kein Faden, keine Anfrage, kein Glance-Ordner)", "SYMBOL_FADEN" not in quelle
      and "symbol_holen" not in quelle and not re.search(r"DATEIEN \+ SYMBOL", quelle))
pruef("keine alten Namen SYMBOL/SYMBOL_ALT mehr", not re.search(r"\bSYMBOL(_ALT)?\b(?!_)", quelle))
fn = ast.get_source_segment(quelle, next(n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name == "symbol_bereitstellen"))
pruef("symbol_bereitstellen ohne Netz und ohne Brueckenbeweis", not re.search(r"urllib|urlopen|bruecke|DATEIEN|http", fn), fn[:200])

aufraeumen()
print("PC-Symbol: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
