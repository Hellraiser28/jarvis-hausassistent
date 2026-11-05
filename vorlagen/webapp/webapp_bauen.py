#!/usr/bin/env python3
"""Web-App bauen (seit 25.10.2026): app.html der Android-App + jarvis-web.js -> Ordner, den die Bruecke unter /app
ausliefert (nur Heimnetz). Fuer iPhone und andere Geraete ohne die Android-App: in Safari oeffnen, Teilen ->
"Zum Home-Bildschirm", dort oeffnen und koppeln.

  python3 webapp_bauen.py [app.html] [Zielordner] [symbol.png]

Ohne Angaben sucht es app.html, jarvis-web.js und jarvis.png neben sich, dann im Release-Aufbau
(app/android/assets/, vorlagen/webapp/, vorlagen/pc/). Ziel ist sonst ./webapp. Neben index.html entsteht csp.txt:
die Content-Security-Policy mit den Hashes der beiden Inline-Skripte, die die Bruecke fuer /app senden soll."""
import base64
import hashlib
import html.parser
import json
import os
import re
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
J = os.path.dirname(HIER)


def finden(name, *orte):
    for o in orte:
        if os.path.exists(os.path.join(o, name)):
            return os.path.join(o, name)
    return os.path.join(orte[0], name)


APP = sys.argv[1] if len(sys.argv) > 1 else finden("app.html", HIER, os.path.join(os.path.dirname(J), "app", "android", "assets"),
                                                    os.path.expanduser("~/jarvis-app/android/assets"))
ZIEL = sys.argv[2] if len(sys.argv) > 2 else (os.path.join(J, "daten", "webapp") if os.path.isdir(os.path.join(J, "daten"))
                                              else os.path.join(os.getcwd(), "webapp"))
SYMBOL = sys.argv[3] if len(sys.argv) > 3 else finden("jarvis.png", HIER, os.path.join(J, "pc"),
                                                       os.path.join(J, "release", "vorlagen", "pc"))
SCHICHT = next(p for p in (os.path.join(HIER, "jarvis-web.js"), os.path.join(J, "spiegel", "webapp", "jarvis-web.js"))
               if os.path.exists(p))

seite = open(APP, encoding="utf-8").read()
schicht = open(SCHICHT, encoding="utf-8").read()
kopf = ('<meta name="apple-mobile-web-app-capable" content="yes">\n'
        '<meta name="mobile-web-app-capable" content="yes">\n'
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n'
        '<meta name="apple-mobile-web-app-title" content="Jarvis">\n'
        '<meta name="theme-color" content="#070206">\n'
        '<link rel="icon" href="/app/jarvis.png">\n'
        '<link rel="apple-touch-icon" href="/app/jarvis.png">\n'
        '<link rel="manifest" href="/app/manifest.json">\n')
assert seite.count("</head>") == 1 and seite.count("<script>") == 1, "app.html hat eine unerwartete Form"
seite = seite.replace("</head>", kopf + "</head>")
# Die Schicht laeuft vor dem Hauptskript (am Ende von body): window.Jarvis steht dann schon, das HTML auch
seite = seite.replace("<script>", "<script>\n" + schicht + "\n</script>\n<script>")
os.makedirs(ZIEL, exist_ok=True)


def schreiben(name, daten):
    pfad = os.path.join(ZIEL, name)
    with open(pfad + ".neu", "wb") as f:
        f.write(daten if isinstance(daten, bytes) else daten.encode("utf-8"))
    os.chmod(pfad + ".neu", 0o600)
    os.replace(pfad + ".neu", pfad)


class _Skripte(html.parser.HTMLParser):
    """Eingebettete Skripte (ohne src), gelesen wie ein Browser (seit 0.3.4, CodeQL: ein regulaerer Ausdruck liest
    HTML anders als der Browser). Skriptinhalt bleibt roh, Zeichenreferenzen werden darin nicht aufgeloest."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.skripte, self._teil = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and not any(k == "src" for k, _ in attrs):
            self._teil = []

    def handle_data(self, data):
        if self._teil is not None:
            self._teil.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._teil is not None:
            self.skripte.append("".join(self._teil))
            self._teil = None


def inline_skripte(text):
    p = _Skripte()
    p.feed(text)
    p.close()
    return p.skripte


schreiben("index.html", seite)
# CSP: Skripte nur genau diese beiden (Hash), Stile inline erlaubt (die Seite setzt style-Attribute), Schrift von Google
hashes = " ".join("'sha256-%s'" % base64.b64encode(hashlib.sha256(s.encode("utf-8")).digest()).decode()
                  for s in inline_skripte(seite))
schreiben("csp.txt", ("default-src 'none'; script-src %s 'strict-dynamic'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                      "font-src https://fonts.gstatic.com; connect-src 'self'; img-src 'self' data: blob:; "
                      "media-src 'self' blob: data:; manifest-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                      "form-action 'none'\n") % hashes)
schreiben("manifest.json", json.dumps({
    "name": "J.A.R.V.I.S.", "short_name": "Jarvis", "start_url": "/app", "scope": "/app", "display": "standalone",
    "background_color": "#070206", "theme_color": "#070206", "lang": "de",
    "icons": [{"src": "/app/jarvis.png", "sizes": "256x256", "type": "image/png"}]}, ensure_ascii=False, indent=1))
if os.path.exists(SYMBOL):
    schreiben("jarvis.png", open(SYMBOL, "rb").read())
# Seit 0.6: Grundriss. app.html laedt die Skripte erst beim Oeffnen nach (/app/three.min.js, /app/haus3d.js, Bildansicht
# /app/grundrissfoto.js); dieselben Pfade holt der PC-Client fuers HUD. Die CSP erlaubt das mit 'strict-dynamic': nur die
# beiden gehashten Skripte duerfen weitere nachladen, eingeschleustes Markup weiterhin nicht. three.js r160 (MIT, Lizenz
# in three.LICENSE.txt neben der Quelle). Gesucht wird neben diesem Skript, in spiegel/grundriss (Repo), grundriss/
# neben vorlagen/webapp (Release-Aufbau) und neben app.html (die App bringt alle drei mit).
for name in ("three.min.js", "haus3d.js", "grundrissfoto.js"):
    q = finden(name, HIER, os.path.join(HIER, "grundriss"), os.path.join(J, "spiegel", "grundriss"),
               os.path.join(J, "grundriss"), os.path.dirname(APP))
    if os.path.exists(q):
        schreiben(name, open(q, "rb").read())
    else:
        print("Hinweis: %s fehlt, der Grundriss geht in der Web-App dann nicht" % name)
print("Web-App gebaut: %s (%d KB)" % (ZIEL, len(seite) // 1024))
