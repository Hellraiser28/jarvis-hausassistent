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

print("Fensterschutz: %d Fälle, %d Fehler" % (len(EIGEN) + len(FREMD) + 11, fehler))
sys.exit(1 if fehler else 0)
