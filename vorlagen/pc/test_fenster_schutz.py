#!/usr/bin/env python3
"""Schutz des PC-Fensters (seit Version 16, Pruefbericht 0.3.1, Fund 8): eigene_seite() und hud_csp() aus jarvis_pc.py
lesen, ohne den Client zu laden (der braucht Windows-Bibliotheken). Mit --html <datei> gibt er die CSP fuer diese
HUD-Seite aus (fuer den Browsertest). Laeuft im Repo (tests/ neben spiegel/pc/) und in der Release-Vorlage."""
import ast
import base64
import hashlib
import html.parser
import os
import re
import sys
import urllib.parse

HIER = os.path.dirname(os.path.abspath(__file__))
for pfad in (os.path.join(HIER, "..", "spiegel", "pc", "jarvis_pc.py"), os.path.join(HIER, "jarvis_pc.py")):
    if os.path.exists(pfad):
        break
else:
    sys.exit("jarvis_pc.py nicht gefunden")

baum = ast.parse(open(pfad, encoding="utf-8").read())
teile = [n for n in baum.body if (isinstance(n, ast.ClassDef) and n.name == "_Skripte") or (
    isinstance(n, ast.FunctionDef) and n.name in ("hud_csp", "eigene_seite", "_inline_skripte"))]
umgebung = {"re": re, "base64": base64, "hashlib": hashlib, "urllib": urllib, "html": html, "HUD_PORT": 8771,
            "_HUD_GEHEIM": "/abc123"}
exec(compile(ast.Module(body=teile, type_ignores=[]), pfad, "exec"), umgebung)
eigene_seite, hud_csp = umgebung["eigene_seite"], umgebung["hud_csp"]

if "--html" in sys.argv:
    print(hud_csp(open(sys.argv[sys.argv.index("--html") + 1], "rb").read()))
    sys.exit(0)

fehler = 0


def pruefe(name, ist, soll):
    global fehler
    if ist != soll:
        fehler += 1
        print("FEHLER %s: %r statt %r" % (name, ist, soll))


EIGEN = [
    "http://127.0.0.1:8771/abc123/assets/jarvis-hud/?pc=1&sprache=de&t=1",
    "http://127.0.0.1:8771/abc123/assets/jarvis-hud/index.html",
]
FREMD = [
    None, "", "about:blank", "https://example.com/", "http://127.0.0.1:8772/abc123/assets/jarvis-hud/",
    "http://127.0.0.1:8771/abc1234/assets/", "http://127.0.0.1:8771/abc123", "http://127.0.0.1:8771/assets/",
    "https://127.0.0.1:8771/abc123/assets/", "http://127.0.0.1.evil.example:8771/abc123/x",
    "http://user@127.0.0.1:8771/abc123/x", "http://127.0.0.1:8771@evil.example/abc123/x",
    "http://localhost:8771/abc123/x", "http://127.0.0.1:99999/abc123/x", "file:///C:/abc123/x",
    "data:text/html,<script>alert(1)</script>", "javascript:alert(1)",
]
for u in EIGEN:
    pruefe("eigen " + str(u), eigene_seite(u), True)
for u in FREMD:
    pruefe("fremd " + str(u), eigene_seite(u), False)


def h(b):
    return "'sha256-%s'" % base64.b64encode(hashlib.sha256(b).digest()).decode()


seite = (b"<html><head><script>var a = 1;</script><script src=\"x.js\"></script>\r\n"
         b"<script type=\"text/javascript\">\r\nvar b = 2;\r\n</script></head></html>")
csp = hud_csp(seite)
pruefe("Hash Skript 1", h(b"var a = 1;") in csp, True)
pruefe("Hash Skript 2 (CRLF -> LF)", h(b"\nvar b = 2;\n") in csp, True)
pruefe("nur eingebettete Skripte", csp.count("'sha256-"), 2)
for teil in ("default-src 'none'", "'unsafe-eval'", "blob:", "frame-ancestors 'none'", "base-uri 'none'",
             "form-action 'none'", "connect-src 'self' wss://generativelanguage.googleapis.com;"):
    pruefe("CSP enthaelt " + teil, teil in csp, True)
pruefe("kein unsafe-inline bei Skripten", "'unsafe-inline'" in csp.split("script-src", 1)[1].split(";", 1)[0], False)

faelle = len(EIGEN) + len(FREMD) + 11

# ---------------------------------------------------------------- Faehigkeit je Start (seit 25, Claude Security 0.7, F8)
# Vorher pruefte aus_dem_fenster() nur die Fensteradresse. Waehrend das HUD nach einer fremden Seite neu laedt, wartet
# pywebviews get_current_url(); ein Aufruf der fremden Seite kam danach mit der HUD-Adresse durch.
import json  # noqa: E402
import secrets  # noqa: E402
import hmac  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

F8_NAMEN = ("faehigkeit_neu", "faehigkeit_passt", "hud_mit_faehigkeit", "fenster_geschuetzt", "url_jetzt", "seite_pruefen",
            "aus_dem_fenster")
F8_WERTE = ("_FENSTER", "_FENSTER_SPERRE", "_AUFRUF", "URL_WARTEN_S", "START_ADRESSE")
f8 = [n for n in baum.body if (isinstance(n, ast.FunctionDef) and n.name in F8_NAMEN) or (
    isinstance(n, ast.Assign) and any(isinstance(z, ast.Name) and z.id in F8_WERTE for z in n.targets))]
api_klasse = next(n for n in baum.body if isinstance(n, ast.ClassDef) and n.name == "Api")
anmelden = next(n for n in api_klasse.body if isinstance(n, ast.FunctionDef) and n.name == "anmelden")


class Protokoll:
    def __init__(self):
        self.zeilen = []

    def _z(self, *a):
        self.zeilen.append(a[0] % a[1:] if len(a) > 1 else a[0])

    info = warning = error = _z


class Fenster:
    """Attrappe fuer pywebviews Fenster: Adresse, Laden, wahlweise blockierendes get_current_url()."""
    def __init__(self, url):
        self.url, self.geladen, self.blockiert = url, [], 0.0

    def get_current_url(self):
        if self.blockiert:
            time.sleep(self.blockiert)
        return self.url

    def load_url(self, url):
        self.geladen.append(url)
        self.url = url


HUD = "http://127.0.0.1:8771/abc123/assets/jarvis-hud/?pc=1&sprache=de&t=1"
FREMD_SEITE = "https://evil.example/"
f = Fenster(HUD)
u8 = dict(umgebung, secrets=secrets, hmac=hmac, threading=threading, log=Protokoll(), fenster=f)
exec(compile(ast.Module(body=f8, type_ignores=[]), pfad, "exec"), u8)
u8["URL_WARTEN_S"] = 0.3
u8["START_ADRESSE"][0] = HUD
u8["url_jetzt"].__defaults__ = (0.3,)
probe_quelle = ast.Module(body=[ast.ClassDef(name="Probe", bases=[], keywords=[], decorator_list=[], body=[anmelden] + ast.parse(
    "def tu(self, x=None, y=None):\n    return ('ok', x, y) if aus_dem_fenster('tu') else 'abgelehnt'\n").body)],
    type_ignores=[])
exec(compile(ast.fix_missing_locations(probe_quelle), pfad, "exec"), u8)
Probe = u8["Probe"]
for _n in ("anmelden", "tu"):
    setattr(Probe, _n, u8["fenster_geschuetzt"](getattr(Probe, _n)))
p8 = Probe()


def k_jetzt():
    return u8["_FENSTER"]["faehigkeit"]


def warte_auf_seitenpruefung():
    for t in [t for t in threading.enumerate() if t.name == "seite"]:
        t.join(3)


def pruefe8(name, bed):
    global faelle
    faelle += 1
    pruefe(name, bool(bed), True)


k1 = k_jetzt()
pruefe8("F8: Faehigkeit 32 Zeichen urlsafe", re.fullmatch(r"[A-Za-z0-9_-]{32}", k1))
pruefe8("F8: Aufruf mit Faehigkeit vom HUD", p8.tu(k1, "a", y=2) == ("ok", "a", 2))
pruefe8("F8: ohne Faehigkeit abgelehnt", p8.tu() == "abgelehnt")
pruefe8("F8: falsche Faehigkeit abgelehnt", p8.tu("x" * 32, "a") == "abgelehnt")
pruefe8("F8: Faehigkeit als Zahl abgelehnt", p8.tu(12345, "a") == "abgelehnt")
warte_auf_seitenpruefung()
pruefe8("F8: HUD-Adresse, falsche Faehigkeit: kein Neuladen, Faehigkeit bleibt", f.geladen == [] and k_jetzt() == k1)
pruefe8("F8: ohne Wrapper (Faehigkeit nicht gesetzt) abgelehnt", u8["aus_dem_fenster"]("direkt") is False)
pruefe8("F8: nach dem Aufruf ist die Faehigkeit wieder zurueckgesetzt", getattr(u8["_AUFRUF"], "ok", False) is False)

# fremde Seite im Fenster: neue Faehigkeit, Sperre, zurueck zum HUD
f.url = FREMD_SEITE
pruefe8("F8: fremde Seite, richtige (alte) Faehigkeit: abgelehnt", p8.tu(k1, "a") == "abgelehnt")
warte_auf_seitenpruefung()
pruefe8("F8: fremde Seite -> HUD neu geladen", f.geladen == [HUD] and f.url == HUD)
k2 = k_jetzt()
pruefe8("F8: fremde Seite -> neue Faehigkeit", k2 != k1)
pruefe8("F8: fremde Seite -> gesperrt", u8["_FENSTER"]["gesperrt"] is True)
pruefe8("F8: alte Faehigkeit nach dem Neuladen abgelehnt (Rennen aus dem Bericht)", p8.tu(k1, "a") == "abgelehnt")
pruefe8("F8: neue Faehigkeit vor der Anmeldung abgelehnt", p8.tu(k2, "a") == "abgelehnt")
pruefe8("F8: Anmeldung mit alter Faehigkeit abgelehnt", p8.anmelden(k1) is False and u8["_FENSTER"]["gesperrt"])
warte_auf_seitenpruefung()
f.url = FREMD_SEITE
pruefe8("F8: Anmeldung von fremder Adresse abgelehnt", p8.anmelden(k2) is False and u8["_FENSTER"]["gesperrt"])
f.url = HUD
pruefe8("F8: Anmeldung des frischen HUD hebt die Sperre auf", p8.anmelden(k2) is True and not u8["_FENSTER"]["gesperrt"])
pruefe8("F8: danach geht es wieder", p8.tu(k2, "b") == ("ok", "b", None))

# blockierendes get_current_url (Fenster laedt gerade): gilt als Ablehnung, auch mit richtiger Faehigkeit
f.blockiert = 1.0
t0 = time.time()
erg = p8.tu(k2, "c")
pruefe8("F8: Adresse nicht sofort lesbar -> abgelehnt, ohne zu warten", erg == "abgelehnt" and time.time() - t0 < 0.9)
f.blockiert = 0.0
time.sleep(1.1)

# HUD-Seite: Skript ganz vorn im <head>, CSP-Hash passt, ohne <head> davor
seite_neu = u8["hud_mit_faehigkeit"](b"<!DOCTYPE html><html><HEAD lang=\"de\"><meta charset=\"utf-8\"><script>var a=1;</script>"
                                      b"</head><body></body></html>")
pruefe8("F8: HUD-Seite: Skript direkt nach <head>", re.search(rb"<HEAD lang=\"de\"><script>\(function\(\)\{var K=\"" +
                                                         k_jetzt().encode() + rb"\"", seite_neu))
eingebettet = umgebung["_inline_skripte"](seite_neu)
pruefe8("F8: HUD-Seite: CSP enthaelt den Hash des eingefuegten Skripts", len(eingebettet) == 2
        and h(eingebettet[0]) in hud_csp(seite_neu))
pruefe8("F8: Seite ohne <head>: Skript davor", u8["hud_mit_faehigkeit"](b"<p>x</p>").startswith(b"<script>(function(){var K="))

# Im echten Client: jede Fensterfunktion geschuetzt, jede (ausser anmelden) fragt aus_dem_fenster zuerst
api_methoden = [n for n in api_klasse.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]


def erste_anweisung(fn):
    ohne_doc = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body
    return ast.dump(ohne_doc[0])


ohne = [n.name for n in api_methoden if n.name != "anmelden" and "aus_dem_fenster" not in erste_anweisung(n)]
pruefe8("F8: jede Fensterfunktion beginnt mit aus_dem_fenster (%d Methoden)" % len(api_methoden), not ohne)
if ohne:
    print("   ohne Pruefung:", ohne)
quelle_pc = open(pfad, encoding="utf-8").read()
pruefe8("F8: Schutzschleife ueber alle Api-Methoden im Client",
        re.search(r"^for _n, _f in list\(vars\(Api\)\.items\(\)\):.*\n    if not _n\.startswith\(\"_\"\) and callable\(_f\):\n"
                  r"        setattr\(Api, _n, fenster_geschuetzt\(_f\)\)", quelle_pc, re.M))
pruefe8("F8: Durchreiche bettet die Faehigkeit in die HUD-Seite ein",
        'hud_mit_faehigkeit(bruecke_holen("/v1/client/hud", 15))' in quelle_pc)

# Das eingefuegte Skript im echten JavaScript (Node, falls vorhanden): haengt die Faehigkeit vor jeden Aufruf
node = shutil.which("node")
if node:
    k_js = k_jetzt()
    skript = u8["hud_mit_faehigkeit"](b"<head></head>").decode()
    skript = skript[skript.index("<script>") + 8:skript.index("</script>")]
    js = """
var aufrufe = [], hoerer = {};
var window = {addEventListener: function (n, f) { hoerer[n] = f; }};
var stub = function (name) { return function () { aufrufe.push([name].concat(Array.prototype.slice.call(arguments)));
  return {catch: function () {}}; }; };
%s
window.pywebview = {api: {frage: stub("frage"), einstellen: stub("einstellen"), anmelden: stub("anmelden")}};
hoerer.pywebviewready();
hoerer.pywebviewready();
window.pywebview.api.frage("Hallo");
window.pywebview.api.einstellen("x", 1);
console.log(JSON.stringify(aufrufe));
""" % skript
    with tempfile.TemporaryDirectory() as d:
        datei = os.path.join(d, "probe.js")
        open(datei, "w", encoding="utf-8").write(js)
        aus = subprocess.run([node, datei], capture_output=True, text=True, timeout=30)
    try:
        aufrufe = json.loads(aus.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        aufrufe = None
    pruefe8("F8 (Node): einmal angemeldet, Faehigkeit vor jedem Aufruf, nicht doppelt eingewickelt",
            aufrufe == [["anmelden", k_js], ["frage", k_js, "Hallo"], ["einstellen", k_js, "x", 1]])
    if aufrufe is None:
        print("   node:", aus.stdout[-300:], aus.stderr[-300:])
else:
    print("Hinweis: node fehlt, JavaScript-Teil uebersprungen")

print("Fensterschutz: %d Fälle, %d Fehler" % (faelle, fehler))
sys.exit(1 if fehler else 0)
