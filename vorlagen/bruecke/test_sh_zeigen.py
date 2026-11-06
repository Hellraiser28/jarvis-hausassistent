#!/usr/bin/env python3
"""Zeig's mir (S6, bruecke/zeigen.py, seit 0.7).

Z1-Z19 Logik mit der Attrappe sh_attrappe.Kontext (kein Netz, kein Claude, kein Home Assistant), B* Browserpruefung:
die von Hand geschriebene Beispielseite BEISPIEL (Vulkan, fuer Kinder) als Attrappen-Antwort, ausgeliefert ueber
zeigen.seite() mit zeigen.SEITE_KOPFZEILEN von einem Testserver auf docker0, geprueft in Headless-Chrome
(zenika/alpine-chrome:with-puppeteer, tests/zeigen_browser.js): rendert ohne Skriptfehler auf Beamer und Handy, Regler
und Knoepfe wirken, und eine Gegenprobe zeigt, dass Netz, Speicher und Cookie gesperrt sind. L Lautsprecher-Sperre,
E englische Fassung (setze_sprache).

Aufruf: python3 tests/test_sh_zeigen.py [--browser] [--bilder ORDNER]
Ohne --browser (oder ZEIGEN_BROWSER=1) laeuft nur die Logik, ganz ohne Docker. Der Browserteil braucht Docker
(Befehl aus JARVIS_DOCKER, Standard "docker", z. B. "sudo -n docker"), das Image schon lokal und docker0 auf
172.17.0.1; fehlt etwas davon, wird er uebersprungen (und gesagt). Er laedt nichts nach.
"""
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HIER = os.path.dirname(os.path.abspath(__file__))
ZWEIG = os.path.dirname(HIER)
sys.path.insert(0, os.path.join(ZWEIG, "bruecke"))
sys.path.insert(0, HIER)
import sh_attrappe  # noqa: E402

wache = sh_attrappe.live_wache()
import zeigen as zg  # noqa: E402
import fremdtext as ft  # noqa: E402  (nur lesen: die echte Einordnung pruefen)

pruef, ergebnis = sh_attrappe.pruefer()
ARGS = sys.argv[1:]
BILDER = ARGS[ARGS.index("--bilder") + 1] if "--bilder" in ARGS and ARGS.index("--bilder") + 1 < len(ARGS) else None
# Browserteil nur auf ausdruecklichen Wunsch (die Tests laufen sonst ohne Docker)
OHNE_BROWSER = not ("--browser" in ARGS or os.environ.get("ZEIGEN_BROWSER") == "1") or "--ohne-browser" in ARGS
DOCKER = shlex.split(os.environ.get("JARVIS_DOCKER") or "docker")
IMAGE = "zenika/alpine-chrome:with-puppeteer"

BEISPIEL = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wie funktioniert ein Vulkan?</title>
<style>
:root{--bg:#0d1326;--karte:#151d36;--text:#e8ecf6;--leise:#a9b4cf;--lava:#ff6a1a;--gelb:#ffc23d;--akzent:#5cc8ff}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);font:clamp(18px,0.9vw + 9px,28px)/1.4 system-ui,"Segoe UI",Roboto,sans-serif}
main{display:grid;grid-template-columns:1fr;gap:1em;padding:clamp(12px,2vw,36px);max-width:1800px;margin:0 auto}
@media (min-aspect-ratio:4/3){main{grid-template-columns:1.2fr 1fr;align-items:center;height:100vh}}
h1{font-size:1.6em;line-height:1.15;margin:0 0 .35em}
.bild{background:var(--karte);border-radius:18px;overflow:hidden;width:100%;aspect-ratio:4/3}
@media (min-aspect-ratio:4/3){.bild{height:100%;max-height:calc(100vh - 4vw);aspect-ratio:auto}}
svg{display:block;width:100%;height:100%}
ol{margin:0 0 .6em;padding-left:1.3em}
li{margin:.2em 0}
.leise{color:var(--leise);margin:.4em 0 0}
label{display:block;font-weight:600;margin:.4em 0 .1em}
input[type=range]{width:100%;height:2em;accent-color:var(--lava)}
.knoepfe{display:flex;gap:.6em;flex-wrap:wrap;margin-top:.4em}
button{font:inherit;font-weight:700;padding:.4em 1.1em;border-radius:999px;border:0;cursor:pointer}
#los{background:var(--lava);color:#1a0800}
#neu{background:#2a3558;color:var(--text)}
button:focus-visible,input:focus-visible{outline:3px solid var(--akzent);outline-offset:3px}
#status{min-height:2.8em;margin:.5em 0 0;font-weight:600;color:var(--gelb)}
.wackeln{animation:wackeln .12s linear 10}
@keyframes wackeln{0%,100%{transform:translate(0,0)}25%{transform:translate(-4px,2px)}75%{transform:translate(4px,-2px)}}
@media (prefers-reduced-motion:reduce){.wackeln{animation:none}}
</style>
</head>
<body>
<main>
  <div class="bild" id="buehne">
    <svg id="szene" viewBox="0 0 800 600" role="img" aria-label="Schnitt durch einen Vulkan mit Magmakammer und Schlot">
      <defs>
        <linearGradient id="himmel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#16244a"/><stop offset="1" stop-color="#2d3f73"/></linearGradient>
        <linearGradient id="magma" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffd23d"/><stop offset=".5" stop-color="#ff6a1a"/><stop offset="1" stop-color="#b3200a"/></linearGradient>
        <clipPath id="schlot"><rect x="378" y="150" width="44" height="300"/></clipPath>
      </defs>
      <rect width="800" height="600" fill="url(#himmel)"/>
      <rect y="420" width="800" height="180" fill="#3b2a20"/>
      <rect y="480" width="800" height="120" fill="#2c1f18"/>
      <path d="M60 430 L360 150 L440 150 L740 430 Z" fill="#5a4636" stroke="#7b624d" stroke-width="4"/>
      <rect x="378" y="150" width="44" height="300" fill="#24160f"/>
      <rect id="lavaspiegel" x="378" y="450" width="44" height="0" fill="url(#magma)" clip-path="url(#schlot)"/>
      <ellipse id="kammer" cx="400" cy="510" rx="150" ry="55" fill="url(#magma)"/>
      <path id="strom1" d="M368 152 C330 210 300 260 250 330" fill="none" stroke="#ff6a1a" stroke-width="12" stroke-linecap="round" stroke-dasharray="300" stroke-dashoffset="300"/>
      <path id="strom2" d="M432 152 C470 220 510 270 560 340" fill="none" stroke="#ff6a1a" stroke-width="12" stroke-linecap="round" stroke-dasharray="300" stroke-dashoffset="300"/>
      <g id="teilchen"></g>
      <g font-size="24" fill="#e8ecf6" font-family="system-ui,sans-serif">
        <text x="572" y="560">Magmakammer</text>
        <line x1="568" y1="552" x2="545" y2="532" stroke="#e8ecf6" stroke-width="2"/>
        <text x="472" y="250">Schlot</text>
        <line x1="468" y1="243" x2="426" y2="262" stroke="#e8ecf6" stroke-width="2"/>
        <text x="290" y="132">Krater</text>
      </g>
      <text id="druckanzeige" x="28" y="50" font-size="30" font-weight="700" fill="#ffc23d" font-family="system-ui,sans-serif">Druck: 20 %</text>
    </svg>
  </div>
  <section>
    <h1>Wie funktioniert ein Vulkan?</h1>
    <ol>
      <li>Tief unter dem Berg ist es so heiß, dass Gestein schmilzt. Dieses flüssige Gestein heißt <b>Magma</b>.</li>
      <li>Im Magma stecken Gase, wie die Bläschen in einer Sprudelflasche. Drückt immer mehr Magma nach, steigt der <b>Druck</b>.</li>
      <li>Wird der Druck zu groß, schießt das Magma durch den <b>Schlot</b> nach oben. Draußen heißt es dann <b>Lava</b>.</li>
    </ol>
    <label for="druck">Druck in der Magmakammer</label>
    <input id="druck" type="range" min="0" max="100" value="20" aria-describedby="status">
    <div class="knoepfe">
      <button id="los" type="button">Ausbruch!</button>
      <button id="neu" type="button">Zurücksetzen</button>
    </div>
    <p id="status" aria-live="polite">Schieb den Regler nach rechts und schau, was passiert.</p>
    <p class="leise">Tipp: Schüttle eine Sprudelflasche und öffne sie langsam – ein Mini-Ausbruch.</p>
  </section>
</main>
<script>
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var ruhig = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var regler = document.getElementById("druck");
  var spiegel = document.getElementById("lavaspiegel");
  var anzeige = document.getElementById("druckanzeige");
  var meldung = document.getElementById("status");
  var gruppe = document.getElementById("teilchen");
  var buehne = document.getElementById("buehne");
  var kammer = document.getElementById("kammer");
  var stroeme = [document.getElementById("strom1"), document.getElementById("strom2")];
  var teilchen = [];
  var bricht = false;
  var flussZeit = 0;
  var letzte = 0;

  function zeichnen() {
    var d = Number(regler.value);
    var h = Math.round(300 * d / 100);
    spiegel.setAttribute("y", String(450 - h));
    spiegel.setAttribute("height", String(h));
    kammer.setAttribute("ry", String(55 + d * 0.15));
    anzeige.textContent = "Druck: " + d + " %";
    if (!bricht) {
      if (d < 40) meldung.textContent = "Das Magma ruht noch in der Kammer.";
      else if (d < 80) meldung.textContent = "Der Druck steigt, das Magma drückt in den Schlot!";
      else meldung.textContent = "Gleich ist es so weit …";
    }
    if (d >= 100 && !bricht) ausbruch();
  }
  function teilchenNeu() {
    var c = document.createElementNS(NS, "circle");
    c.setAttribute("r", (4 + Math.random() * 7).toFixed(1));
    c.setAttribute("fill", Math.random() < 0.3 ? "#ffc23d" : "#ff6a1a");
    gruppe.appendChild(c);
    return { el: c, x: 400 + (Math.random() - 0.5) * 30, y: 150, vx: (Math.random() - 0.5) * 260,
             vy: -(260 + Math.random() * 260), leben: 2.2 };
  }
  function ausbruch() {
    if (bricht) return;
    bricht = true;
    regler.value = "100";
    zeichnen();
    meldung.textContent = "Ausbruch! Die Lava fließt den Berg hinunter.";
    if (!ruhig) {
      buehne.classList.remove("wackeln");
      void buehne.getBoundingClientRect();
      buehne.classList.add("wackeln");
    }
    for (var i = 0; i < (ruhig ? 12 : 60); i++) teilchen.push(teilchenNeu());
    flussZeit = 0;
  }
  function zuruecksetzen() {
    bricht = false;
    teilchen.forEach(function (t) { t.el.remove(); });
    teilchen = [];
    stroeme.forEach(function (s) { s.setAttribute("stroke-dashoffset", "300"); });
    regler.value = "20";
    zeichnen();
    meldung.textContent = "Alles wieder ruhig. Probier es noch einmal!";
  }
  function schritt(zeit) {
    var dt = letzte ? Math.min(0.05, (zeit - letzte) / 1000) : 0;
    letzte = zeit;
    for (var i = teilchen.length - 1; i >= 0; i--) {
      var t = teilchen[i];
      t.vy += 420 * dt;
      t.x += t.vx * dt;
      t.y += t.vy * dt;
      t.leben -= dt;
      if (t.leben <= 0 || t.y > 600) {
        t.el.remove();
        teilchen.splice(i, 1);
        if (bricht && flussZeit < 3 && teilchen.length < (ruhig ? 6 : 30)) teilchen.push(teilchenNeu());
        continue;
      }
      t.el.setAttribute("cx", t.x.toFixed(1));
      t.el.setAttribute("cy", t.y.toFixed(1));
      t.el.setAttribute("opacity", Math.max(0, Math.min(1, t.leben)).toFixed(2));
    }
    if (bricht) {
      flussZeit += dt;
      var rest = Math.max(0, 300 - flussZeit * 110);
      stroeme.forEach(function (s) { s.setAttribute("stroke-dashoffset", rest.toFixed(0)); });
    }
    window.requestAnimationFrame(schritt);
  }
  regler.addEventListener("input", zeichnen);
  document.getElementById("los").addEventListener("click", ausbruch);
  document.getElementById("neu").addEventListener("click", zuruecksetzen);
  zeichnen();
  window.requestAnimationFrame(schritt);
})();
</script>
</body>
</html>
"""

# Am Pruefer vorbei abgelegt (nur fuer die Gegenprobe im Browser): versucht Netz, Speicher und Cookie.
BOESE = """<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Gegenprobe</title></head>
<body><pre id="erg"></pre><script>
var erg = {origin: String(self.origin)}, n = 0;
function fertig() { document.getElementById("erg").textContent = JSON.stringify(erg); }
function eins() { if (++n === 3) fertig(); }
try { localStorage.setItem("x", "1"); erg.speicher = "offen"; } catch (e) { erg.speicher = "gesperrt"; }
try { erg.cookie = "offen:" + document.cookie; } catch (e) { erg.cookie = "gesperrt"; }
try { fetch("LECK/fetch").then(function () { erg.fetch = "offen"; eins(); }, function () { erg.fetch = "gesperrt"; eins(); }); }
catch (e) { erg.fetch = "gesperrt"; eins(); }
try { var x = new XMLHttpRequest(); x.open("GET", "LECK/xhr"); x.onload = function () { erg.xhr = "offen"; eins(); };
      x.onerror = function () { erg.xhr = "gesperrt"; eins(); }; x.send(); } catch (e) { erg.xhr = "gesperrt"; eins(); }
var b = new Image(); b.onload = function () { erg.bild = "offen"; eins(); }; b.onerror = function () { erg.bild = "gesperrt"; eins(); };
b.src = "LECK/bild.png";
setTimeout(fertig, 4000);
</script></body></html>
"""


def seite_mit(einschub, kopf=""):
    """Kleine gueltige Seite mit einem Einschub im body (und optional im head)."""
    return ('<!doctype html><html lang="de"><head><meta charset="utf-8"><title>T</title>%s</head><body><p>Hallo</p>%s'
            '</body></html>\n' % (kopf, einschub))


def mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


KONTEXTE = []


def neuer_ctx(**kw):
    c = sh_attrappe.Kontext(**kw)
    KONTEXTE.append((c, c.daten))
    return c


# ---------------------------------------------------------------- Z1 Import ohne Nebenwirkungen, Python 3.8
leer = tempfile.mkdtemp(prefix="sh-import-")
r = subprocess.run([sys.executable, "-I", "-B", "-c", "import sys; sys.path.insert(0, %r); import zeigen; print(sys.version_info[:2])"
                    % os.path.join(ZWEIG, "bruecke")], cwd=leer, capture_output=True, text=True)
pruef("Z1 Import ohne Fehler unter Python %s (ab 3.8)" % r.stdout.strip(), r.returncode == 0
      and re.fullmatch(r"\((\d+), (\d+)\)", r.stdout.strip()) is not None
      and tuple(int(x) for x in re.findall(r"\d+", r.stdout)) >= (3, 8),
      r.stderr[-300:] or r.stdout)
pruef("Z1 Import legt nichts an", os.listdir(leer) == [], os.listdir(leer))
shutil.rmtree(leer, ignore_errors=True)

# ---------------------------------------------------------------- Z2 Schnittstelle
pruef("Z2 NAME/RECHTE/TAKT", zg.NAME == "zeigen" and zg.RECHTE == "familie" and zg.TAKT_S == 3600)
pruef("Z2 Schema mit aktion erklaeren|zeigen|liste", zg.WERKZEUG["schema"]["properties"]["aktion"]["enum"] ==
      ["erklaeren", "zeigen", "liste"] and zg.WERKZEUG["schema"]["required"] == ["aktion"])
pruef("Z2 CSP wie vorgegeben", zg.CSP == ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                           "img-src data:; font-src data:; connect-src 'none'; base-uri 'none'; "
                                           "form-action 'none'"))
pruef("Z2 Kopfzeile = CSP + sandbox allow-scripts, kein X-Frame-Options (iframe der Leinwand)",
      zg.SEITE_KOPFZEILEN["Content-Security-Policy"] == zg.CSP + "; sandbox allow-scripts"
      and "X-Frame-Options" not in zg.SEITE_KOPFZEILEN and zg.SEITE_KOPFZEILEN["X-Content-Type-Options"] == "nosniff")
e = zg.FREMDTEXT["nur_lesen"]
eintrag = (e[0], e[1], frozenset(e[2]))
pruef("Z2 Fremdtext (echte Logik aus fremdtext.py): liste liest, erklaeren/zeigen/leer/unbekannt sind Ziel",
      zg.FREMDTEXT["art"] == "ziel" and ft._aktion(eintrag, {"aktion": "liste"}, streng=True) in eintrag[2]
      and all(ft._aktion(eintrag, a, streng=True) not in eintrag[2]
              for a in ({"aktion": "erklaeren"}, {"aktion": "zeigen", "id": "0" * 24}, {}, {"aktion": "LISTE"},
                        {"aktion": "loeschen"})))

# ---------------------------------------------------------------- Z3/Z4 Pruefer: Beispiel und harmlose Muster
pruef("Z3 Beispielseite besteht die Pruefung", zg.pruefen(BEISPIEL) == [], zg.pruefen(BEISPIEL))
pruef("Z3 Beispielseite ist klein (%d KB)" % (len(BEISPIEL.encode()) // 1024), len(BEISPIEL.encode()) < 30 * 1024)
HARMLOS = {
    "rect.top/style.top/scrollTop": "<script>var r={top:1,left:2};var a=r.top.toFixed(1);el.style.top='3px';"
                                    "var s=document.body.scrollTop.toString();var n=el.parentNode;</script>",
    "SVG-Namensraum und xlink": '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
                                '<use href="#a"/><use xlink:href="#b"/><rect fill="url(#g)"/></svg>',
    "data:-Bild und data:-Schrift": '<img src="data:image/png;base64,iVBORw0KGgo=" alt="">'
                                    '<style>@font-face{font-family:x;src:url(data:font/woff2;base64,d09GMgAB)}</style>',
    "Kommentare und Text": "<p>Das ist top. Er öffnet die Tür.</p><script>// Teil 1: Kräfte\nvar x = 1; /* oben */</script>",
    "Methode namens open auf einem Objekt": "<script>var tuer={open:function(){return 1}};tuer.open();</script>",
    "Inline-Ereignis ohne Netz": '<button onclick="zaehle(1)">+</button><script>function zaehle(n){return n}</script>',
}
for name, schnipsel in HARMLOS.items():
    f = zg.pruefen(seite_mit(schnipsel))
    pruef("Z4 harmlos bleibt erlaubt: %s" % name, f == [], f)

# ---------------------------------------------------------------- Z5 Pruefer: jede Verbotsstelle einzeln
VERBOTEN = {
    "fetch": "<script>fetch('/x')</script>",
    "XMLHttpRequest": "<script>var x = new XMLHttpRequest();</script>",
    "WebSocket": "<script>var w = new WebSocket(u);</script>",
    "EventSource": "<script>var q = new EventSource(u);</script>",
    "sendBeacon": "<script>navigator.sendBeacon(u, 1);</script>",
    "import(": "<script>import(u).then(function(){});</script>",
    "<iframe": '<iframe srcdoc="x"></iframe>',
    "<object": "<object></object>",
    "<embed": "<embed>",
    "<base": '<base target="_self">',
    "<form": "<form><input></form>",
    "<meta http-equiv": '<meta http-equiv="refresh" content="1">',
    "window.open": "<script>window.open('#x');</script>",
    "open( ohne window": "<script>var o = open;o('#');open('#y');</script>",
    "document.cookie": "<script>var c = document.cookie;</script>",
    "top.": "<script>top.document.title = 'x';</script>",
    "parent.": "<script>parent.x = 1;</script>",
    "location": "<script>location.href = '#x';</script>",
    "localStorage": "<script>localStorage.getItem('x');</script>",
    "window[...]": "<script>window['fe' + 'tch']('/x');</script>",
    "eval": "<script>eval('1');</script>",
    "setTimeout mit Text": "<script>setTimeout('x()', 9);</script>",
    "postMessage": "<script>window.postMessage(1, '*');</script>",
    "WebRTC": "<script>new RTCPeerConnection();</script>",
    "Kamera": "<script>navigator.mediaDevices.getUserMedia({video: true});</script>",
    "alert": "<script>alert('x');</script>",
    "Worker": "<script>new Worker(u);</script>",
    "Ereignis mit fetch": "<button onclick=\"fetch('/x')\">x</button>",
    "externes Bild": '<img src="https://example.org/a.png">',
    "externer Link": '<a href="http://example.org">x</a>',
    "Adresse ohne Schema //": '<img src="//example.org/a.png">',
    "relative Bilddatei": '<img src="bild.png">',
    "url() mit Pfad": "<div style=\"background:url(/bild.png)\"></div>",
    "@import": "<style>@import 'x.css';</style>",
    "<link": '<link rel="stylesheet" href="#x">',
    "script src": '<script src="#x"></script>',
    "javascript:": '<a href="javascript:void(0)">x</a>',
    "Adresse als Text": "<p>Mehr unter https://de.wikipedia.org/wiki/Vulkan</p>",
    "verschleierte Adresse": "<script>var u = 'https:\\/\\/example.org';</script>",
    "ws:// Adresse": "<script>var u = 'ws://192.0.2.1:1';</script>",
    "blob:": "<script>var u = 'blob:x';</script>",
    "Datei/Kamera-Auswahl": '<input type="file" accept="image/*" capture="environment">',
    "<audio": "<audio></audio>",
    "script type=module": '<script type="module">var a = 1;</script>',
    "srcset": '<img srcset="a.png 2x" alt="">',
    "ping": '<a href="#a" ping="#b">x</a>',
}
for name, schnipsel in VERBOTEN.items():
    f = zg.pruefen(seite_mit(schnipsel))
    pruef("Z5 abgelehnt: %s" % name, bool(f), "nicht erkannt")
f = zg.pruefen(BEISPIEL.replace("</body>", "<!--" + "x" * (250 * 1024) + "--></body>"))
pruef("Z5 abgelehnt: über 250 KB", any("Zu groß" in x for x in f), f)
pruef("Z5 abgelehnt: ohne </html> (abgeschnitten)", bool(zg.pruefen(BEISPIEL[:len(BEISPIEL) // 2])))
pruef("Z5 abgelehnt: <script> nicht geschlossen", bool(zg.pruefen(seite_mit("<script>var a = 1;"))))
f = zg.pruefen(seite_mit("<script>fetch('/x');</script>"))
pruef("Z5 Verstoß nennt die Fundstelle", len(f) == 1 and "fetch" in f[0] and "/x" in f[0], f)

# ---------------------------------------------------------------- Z6 HTML aus der Antwort holen
pruef("Z6 Zaun und Text drumherum", zg.html_aus("Hier ist die Seite:\n```html\n" + BEISPIEL + "```\nViel Spaß!")
      == BEISPIEL.strip() + "\n")
pruef("Z6 ohne HTML: None", zg.html_aus("Tut mir leid, das kann ich nicht.") is None)
pruef("Z6 abgeschnitten: None", zg.html_aus(BEISPIEL[:2000]) is None)
pruef("Z6 Titel aus <title>", zg.titel_aus(BEISPIEL, "x") == "Wie funktioniert ein Vulkan?")

# ---------------------------------------------------------------- Z7 erklaeren
ctx = neuer_ctx(antworten={"zeigen": "```html\n" + BEISPIEL + "\n```"})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Wie funktioniert ein Vulkan?", "fuer": "kind"}, "kim", ctx)
sid = r.get("id") or ""
pfad = os.path.join(ctx.daten, "zeigen", sid + ".html")
pruef("Z7 erklaeren: ok, id 24 Hex", r.get("ok") is True and re.fullmatch(r"[0-9a-f]{24}", sid) is not None, r)
pruef("Z7 genau ein Denkauftrag, Stufe normal, zweck zeigen",
      [(g["zweck"], g["stufe"], g["werkzeuge"]) for g in ctx.gedacht] == [("zeigen", "normal", ())], ctx.gedacht)
# Nachpruefung vor 0.7 (Punkt 3): eigene Reservierung, weil die Seite bis 250 KB (grob 1 $) gross werden darf
import denken as _dkz  # noqa: E402
pruef("Z7 eigene Reservierung deckt die 250-KB-Seite und liegt ueber der Stufe normal",
      ctx.gedacht[0]["reserve_usd"] == zg.RESERVE_USD and zg.RESERVE_USD >= 1.0
      and zg.RESERVE_USD > _dkz.RESERVE_USD["normal"], (zg.RESERVE_USD, ctx.gedacht[0]["reserve_usd"]))
pruef("Z7 Auftrag nennt Thema und Kinderstufe, System die Regeln",
      "Vulkan" in ctx.gedacht[0]["auftrag"] and "Kind" in ctx.gedacht[0]["auftrag"]
      and "connect" not in ctx.gedacht[0]["auftrag"] and "fetch" in ctx.gedacht[0]["system"])
pruef("Z7 Datei liegt da, 0600, Inhalt = geprüftes HTML", os.path.isfile(pfad) and mode(pfad) == 0o600
      and open(pfad, encoding="utf-8").read() == BEISPIEL.strip() + "\n", mode(pfad) if os.path.exists(pfad) else "fehlt")
pruef("Z7 Index und Zähler 0600", all(mode(os.path.join(ctx.daten, "zeigen", n)) == 0o600
                                       for n in ("index.json", "zaehler.json")))
pruef("Z7 meldung nennt Titel und Heimnetz-Link", "Wie funktioniert ein Vulkan?" in r["meldung"]
      and ctx.lan("zeigen/" + sid) in r["meldung"] and "Leinwand" not in r["meldung"], r["meldung"])
pruef("Z7 Link unterwegs (Fernzugang) im Ergebnis, nicht in der meldung",
      r.get("link_unterwegs") == ctx.oeffentlich("zeigen/" + sid) and "https://" not in r["meldung"])
pruef("Z7 erklaeren setzt die Leinwand nicht", zg._aktuell_id(ctx) is None and "leinwand" not in r)
pruef("Z7 nichts nach außen (kein Push, keine Durchsage, kein HA)", not ctx.pushes and not ctx.durchsagen
      and not ctx.dienste and not ctx.leinwand)

# ---------------------------------------------------------------- Z8 zeigen
ctx.zustaende = {}
ctx._antworten["zeigen"] = BEISPIEL
r2 = zg.auftrag({"aktion": "zeigen", "thema": "Vulkan", "fuer": "kind"}, "alex", ctx)
pruef("Z8 zeigen: aktuell zeigt auf die neue Seite", r2.get("ok") and zg._aktuell_id(ctx) == r2["id"], r2)
pruef("Z8 meldung mit Link und Leinwand-Hinweis", ctx.lan("zeigen/" + r2["id"]) in r2["meldung"]
      and "Leinwand" in r2["meldung"], r2["meldung"])
pruef("Z8 Ergebnis sagt der Brücke, welche Ansicht", r2.get("leinwand") == {"dashboard_path": "jarvis-leinwand",
                                                                              "view_path": "zeigen"})
pruef("Z8 aktuell.json 0600", mode(os.path.join(ctx.daten, "zeigen", "aktuell.json")) == 0o600)

# ---------------------------------------------------------------- Z9-Z11 Reparatur und Absage
ctx = neuer_ctx(antworten={"zeigen": [seite_mit("<script>fetch('/x')</script>"), BEISPIEL]})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Vulkan"}, "alex", ctx)
pruef("Z9 Reparatur: zweiter Versuch klappt", r.get("ok") is True and r.get("versuche") == 2, r)
pruef("Z9 Reparaturauftrag nennt den Verstoß", len(ctx.gedacht) == 2 and "fetch" in ctx.gedacht[1]["auftrag"]
      and "nicht bestanden" in ctx.gedacht[1]["auftrag"] and ctx.gedacht[1]["zweck"] == "zeigen", ctx.gedacht[-1:])
ctx = neuer_ctx(antworten={"zeigen": [seite_mit("<iframe></iframe>"), seite_mit("<script>top.x=1</script>")]})
r = zg.auftrag({"aktion": "zeigen", "thema": "Vulkan"}, "alex", ctx)
pruef("Z10 zweimal abgelehnt: ehrliche Absage", r.get("ok") is False and "Sicherheitsprüfung" in r["meldung"]
      and len(ctx.gedacht) == 2, r)
pruef("Z10 nichts abgelegt, Leinwand unverändert", not [n for n in os.listdir(os.path.join(ctx.daten, "zeigen"))
                                                        if n.endswith(".html")] and zg._aktuell_id(ctx) is None)
pruef("Z10 Gründe im Log, nicht beim Nutzer als Code", any("abgelehnt" in x for x in ctx.logs) and "<" not in r["meldung"])
ctx = neuer_ctx(antworten={"zeigen": ["Gern! Leider kann ich das nicht.", BEISPIEL]})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Vulkan"}, "alex", ctx)
pruef("Z11 Antwort ohne HTML: Reparatur, dann ok", r.get("ok") is True and len(ctx.gedacht) == 2
      and "vollständiges HTML" in ctx.gedacht[1]["auftrag"], r)

# ---------------------------------------------------------------- Z12 seite()
ctx = neuer_ctx(antworten={"zeigen": BEISPIEL})
sid = zg.auftrag({"aktion": "zeigen", "thema": "Vulkan"}, "alex", ctx)["id"]
code, typ, roh = zg.seite("zeigen/" + sid, "", ctx, False)
txt = roh.decode()
pruef("Z12 zeigen/<id>: 200 text/html", code == 200 and typ == "text/html; charset=utf-8")
pruef("Z12 CSP als <meta> direkt nach <head>", re.search(r"<head>\s*<meta http-equiv=\"Content-Security-Policy\" "
                                                       r"content=\"default-src 'none';", txt) is not None)
pruef("Z12 sonst unverändert", txt.replace(re.search(r'<meta http-equiv="Content-Security-Policy"[^>]*>'
                                                    r'<meta name="referrer"[^>]*>', txt).group(0), "")
      == BEISPIEL.strip() + "\n")
pruef("Z12 mit Schrägstrich und Abfrage", zg.seite("/zeigen/%s?x=1" % sid, "", ctx, False)[0] == 200)
pruef("Z12 Fernzugang: zeigen/<id> geht (96 Bit Zufall)", zg.seite("zeigen/" + sid, {}, ctx, True)[0] == 200)
for p in ("zeigen/" + "0" * 24, "zeigen/" + sid.upper(), "zeigen/../index.json", "zeigen/index.json", "zeigen/",
          "zeigen/%s.html" % sid, "zeigen/aktuell/x"):
    pruef("Z12 404: %s" % p, zg.seite(p, "", ctx, False)[0] == 404)
pruef("Z12 fremder Pfad: None", zg.seite("v1/zustand", "", ctx, False) is None and zg.seite("zeigenx/1", "", ctx, False)
      is None)
code, typ, roh = zg.seite("zeigen/aktuell", "", ctx, False)
pruef("Z12 aktuell im Heimnetz: die gezeigte Seite", code == 200 and b"Wie funktioniert ein Vulkan?" in roh)
pruef("Z12 aktuell im Fernzugang ohne Schlüssel: 404", zg.seite("zeigen/aktuell", "", ctx, True)[0] == 404)
pruef("Z12 Schlüssel entsteht nicht durch Anfragen", not os.path.exists(os.path.join(ctx.daten, "zeigen", "leinwand.json")))
adresse = zg.leinwand_adresse(ctx)
k = urllib.parse.parse_qs(urllib.parse.urlsplit(adresse).query)["k"][0]
pruef("Z12 leinwand_adresse: https, Schlüssel ≥ 32 Zeichen, Datei 0600", adresse.startswith(
    ctx.oeffentlich("zeigen/aktuell?k=")) and len(k) >= 32 and mode(os.path.join(ctx.daten, "zeigen", "leinwand.json")) == 0o600)
pruef("Z12 Schlüssel bleibt gleich", zg.leinwand_adresse(ctx) == adresse)
pruef("Z12 Fernzugang mit Schlüssel (Text oder dict): 200",
      zg.seite("zeigen/aktuell", "k=" + k, ctx, True)[0] == 200 and zg.seite("zeigen/aktuell", {"k": [k]}, ctx, True)[0]
      == 200 and zg.seite("zeigen/aktuell?k=" + k, None, ctx, True)[0] == 200)
pruef("Z12 Fernzugang mit falschem Schlüssel: 404", zg.seite("zeigen/aktuell", "k=" + k[:-1] + "x", ctx, True)[0] == 404)
ctx2 = neuer_ctx()
code, typ, roh = zg.seite("zeigen/aktuell", "", ctx2, False)
pruef("Z12 aktuell ohne Seite: ruhige Platzhalterseite", code == 200 and "Gerade ist nichts zu sehen" in roh.decode()
      and zg.pruefen(zg.LEER_HTML) == [])

# ---------------------------------------------------------------- Z13 liste
ctx = neuer_ctx(antworten={"zeigen": lambda a, s, st: BEISPIEL.replace("Wie funktioniert ein Vulkan?",
                                                                      "Seite " + a.split("\n")[0][7:])},
                jetzt=time.time())
for i in range(12):
    ctx._jetzt += 60
    zg.auftrag({"aktion": "erklaeren", "thema": "Nr %02d" % i}, "kim" if i < 11 else "sam", ctx)
r = zg.auftrag({"aktion": "liste"}, "kim", ctx)
titel = [s["titel"] for s in r["seiten"]]
pruef("Z13 liste: die letzten 10, neueste zuerst, nur eigene", titel == ["Seite Nr %02d" % i for i in range(10, 0, -1)],
      titel)
pruef("Z13 liste nennt Links und ids", all(ctx.lan("zeigen/" + s["id"]) in r["meldung"] and s["id"] in r["meldung"]
                                          for s in r["seiten"]))
r = zg.auftrag({"aktion": "liste"}, "alex", ctx)
pruef("Z13 Alex sieht alle, mit Namen", r["seiten"][0]["titel"] == "Seite Nr 11" and "von Sam" in r["meldung"]
      and "von Kim" in r["meldung"], r["meldung"][:200])
pruef("Z13 liste kostet nichts", len(ctx.gedacht) == 12)
r = zg.auftrag({"aktion": "liste"}, "sam", ctx)
pruef("Z13 Sam sieht nur ihre", [s["titel"] for s in r["seiten"]] == ["Seite Nr 11"])

# ---------------------------------------------------------------- Z14 zeigen mit vorhandener id
alt = r["seiten"][0]["id"]
n = len(ctx.gedacht)
r = zg.auftrag({"aktion": "zeigen", "id": alt}, "alex", ctx)
pruef("Z14 vorhandene Seite auf die Leinwand, ohne neu zu bauen", r.get("ok") and zg._aktuell_id(ctx) == alt
      and len(ctx.gedacht) == n and "Leinwand" in r["meldung"], r)
r = zg.auftrag({"aktion": "zeigen", "id": "f" * 24}, "alex", ctx)
pruef("Z14 unbekannte id: Hinweis, Leinwand bleibt", r.get("ok") is False and zg._aktuell_id(ctx) == alt)
pruef("Z14 liste markiert die Leinwand", "gerade auf der Leinwand" in zg.auftrag({"aktion": "liste"}, "sam", ctx)["meldung"])

# ---------------------------------------------------------------- Z15 Personen und Eingaben
ctx = neuer_ctx(antworten={"zeigen": BEISPIEL})
for wer in ("gast1", "unbekannt", None):
    r = zg.auftrag({"aktion": "erklaeren", "thema": "Vulkan"}, wer, ctx)
    pruef("Z15 %s bekommt nichts" % wer, r.get("ok") is False and "Familie" in r["meldung"] and not ctx.gedacht)
r = zg.auftrag({"aktion": "malen", "thema": "Vulkan"}, "alex", ctx)
pruef("Z15 unbekannte Aktion", r.get("ok") is False and "erklaeren, zeigen, liste" in r["meldung"] and not ctx.gedacht)
r = zg.auftrag({"aktion": "erklaeren", "thema": "  "}, "alex", ctx)
pruef("Z15 ohne Thema: Rückfrage, kein Denken", r.get("ok") is False and not ctx.gedacht)
zg.auftrag({"thema": "Vulkan <script>"}, "alex", ctx)
pruef("Z15 ohne aktion = erklaeren; Thema ohne spitze Klammern im Auftrag",
      len(ctx.gedacht) == 1 and "<script>" not in ctx.gedacht[0]["auftrag"] and zg._aktuell_id(ctx) is None)

# ---------------------------------------------------------------- Z16 Tageskontingent, Z17 Tageslimit von denken
ctx = neuer_ctx(antworten={"zeigen": BEISPIEL}, jetzt=time.time())
os.makedirs(os.path.join(ctx.daten, "zeigen"))
zg._json_schreiben(os.path.join(ctx.daten, "zeigen", "zaehler.json"), {"tag": zg._heute(ctx), "n": zg.TAGES_MAX})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Vulkan"}, "alex", ctx)
pruef("Z16 Tageskontingent erschöpft: Absage ohne Denken", r.get("ok") is False and "Morgen" in r["meldung"]
      and not ctx.gedacht, r)
ctx._jetzt += 86400
r = zg.auftrag({"aktion": "erklaeren", "thema": "Vulkan"}, "alex", ctx)
pruef("Z16 am nächsten Tag wieder frei", r.get("ok") is True)
ctx = neuer_ctx(antworten={"zeigen": [seite_mit("<iframe></iframe>")]})
zg._json_schreiben(os.path.join(zg._ordner(ctx), "zaehler.json"), {"tag": zg._heute(ctx), "n": zg.TAGES_MAX - 1})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Vulkan"}, "alex", ctx)
pruef("Z16 letzter Auftrag des Tages: keine Reparatur mehr", r.get("ok") is False and len(ctx.gedacht) == 1, r)


class Abgelehnt(RuntimeError):
    pass


def tageslimit(a, s, st):
    raise Abgelehnt("Tageslimit fuers Nachdenken erreicht (2.00 $). Morgen wieder.")


ctx = neuer_ctx(antworten={"zeigen": tageslimit})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Vulkan"}, "alex", ctx)
pruef("Z17 Tageslimit aus denken.py wird ehrlich weitergegeben", r.get("ok") is False and "Tageslimit" in r["meldung"], r)
ctx = neuer_ctx(antworten={"zeigen": lambda a, s, st: 1 / 0})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Vulkan"}, "alex", ctx)
pruef("Z17 anderer Fehler: knappe Absage ohne Technik", r.get("ok") is False and "ZeroDivision" not in r["meldung"], r)

# ---------------------------------------------------------------- Z18 Aufraeumen nach 30 Tagen
ctx = neuer_ctx(antworten={"zeigen": BEISPIEL})
r = zg.auftrag({"aktion": "zeigen", "thema": "Vulkan"}, "alex", ctx)
ordner = os.path.join(ctx.daten, "zeigen")
open(os.path.join(ordner, "a" * 24 + ".html"), "w").close()               # verwaist, frisch: bleibt
os.utime(os.path.join(ordner, "a" * 24 + ".html"))
zg.runde(ctx)
pruef("Z18 frische Seiten bleiben", os.path.exists(os.path.join(ordner, r["id"] + ".html"))
      and os.path.exists(os.path.join(ordner, "a" * 24 + ".html")) and zg._aktuell_id(ctx) == r["id"])
ctx._jetzt = time.time() + 29 * 86400
zg.runde(ctx)
pruef("Z18 nach 29 Tagen noch da", zg.seite("zeigen/" + r["id"], "", ctx, False)[0] == 200)
ctx._jetzt = time.time() + 31 * 86400
pruef("Z18 nach 31 Tagen liefert seite() schon vor dem Aufräumen 404", zg.seite("zeigen/" + r["id"], "", ctx, False)[0]
      == 404)
zg.runde(ctx)
pruef("Z18 runde löscht alte Seiten, verwaiste und den Leinwand-Zeiger",
      [n for n in os.listdir(ordner) if n.endswith(".html")] == [] and zg._index(ctx) == []
      and zg._aktuell_id(ctx) is None, os.listdir(ordner))
pruef("Z18 Log nennt die Zahl", any("2 alte Seite" in x for x in ctx.logs), ctx.logs)
pruef("Z18 aktuell zeigt danach den Platzhalter", b"Gerade ist nichts" in zg.seite("zeigen/aktuell", "", ctx, False)[2])
ctx.daten = "/proc/nicht/da"
try:
    zg.runde(ctx)
    pruef("Z18 runde wirft nie (Datenordner kaputt)", any("runde fehlgeschlagen" in x for x in ctx.logs))
except Exception as x:
    pruef("Z18 runde wirft nie (Datenordner kaputt)", False, x)


# ---------------------------------------------------------------- L Lautsprecher-Sperre (seit 0.7)
pruef("L LAUTSPRECHER_PRIVAT leer (frozenset): liste nennt nur Titel und Links",
      isinstance(zg.LAUTSPRECHER_PRIVAT, frozenset) and zg.LAUTSPRECHER_PRIVAT == frozenset())

# ---------------------------------------------------------------- E Englisch (seit 0.7)
DEUTSCH = re.compile(r"[äöüÄÖÜß„]|\b(?:ist|nicht|Bitte|bitte|und|oder|der|die|das|dich|mit|für|bei|Seite|Leinwand|"
                     r"Heimnetz|Thema|Fertig|Morgen|Verboten|Adresse|Zugriff|Netzzugriff|Kind|Kinder)\b")


def deutsch(text):
    return DEUTSCH.findall(str(text))


try:
    zg.setze_sprache("fr")
    pruef("E fremde Sprache abgelehnt", False)
except ValueError:
    pruef("E fremde Sprache abgelehnt", zg.SPRACHE == "de")
zg.setze_sprache("en")
BEISPIEL_EN = BEISPIEL.replace('<html lang="de">', '<html lang="en">').replace(
    "<title>Wie funktioniert ein Vulkan?</title>", "<title>How does a volcano work?</title>")
w = zg.WERKZEUG
pruef("E WERKZEUG englisch, Aktionen und Schluessel gleich", w is zg.WERKZEUG_EN and not deutsch(w["beschreibung"])
      and "big screen" in w["beschreibung"] and w["schema"]["properties"]["aktion"]["enum"] == ["erklaeren", "zeigen", "liste"]
      and set(w["schema"]["properties"]) == set(zg.WERKZEUG_DE["schema"]["properties"])
      and w["schema"]["required"] == ["aktion"]
      and not any(deutsch(p.get("description", "")) for p in w["schema"]["properties"].values()),
      deutsch(w["beschreibung"]))
pruef("E Pruefer, CSP und Kopfzeilen haengen nicht von der Sprache ab",
      zg.SEITE_KOPFZEILEN["Content-Security-Policy"] == zg.CSP + "; sandbox allow-scripts"
      and zg.pruefen(BEISPIEL) == [] and zg.pruefen(BEISPIEL_EN) == []
      and all(zg.pruefen(seite_mit(s)) == [] for s in HARMLOS.values())
      and all(zg.pruefen(seite_mit(s)) for s in VERBOTEN.values()))
meldungen = [m for s in VERBOTEN.values() for m in zg.pruefen(seite_mit(s))]
meldungen += zg.pruefen(BEISPIEL.replace("</body>", "<!--" + "x" * (250 * 1024) + "--></body>")) + zg.pruefen("")
meldungen += zg.pruefen(seite_mit("<script>var a = 1;")) + zg.pruefen(BEISPIEL[:len(BEISPIEL) // 2])
pruef("E Pruefmeldungen englisch (gehen in den Reparaturauftrag)", not [m for m in meldungen if deutsch(m)]
      and "Too large: " in " ".join(meldungen) and "Not an HTML document." in meldungen,
      [m for m in meldungen if deutsch(m)][:5])
f = zg.pruefen(seite_mit("<script>fetch('/x');</script>"))
pruef("E Verstoss nennt die Fundstelle", f == ["fetch (network access) at: fetch('/x');"], f)
ctx = neuer_ctx(antworten={"zeigen": [seite_mit("<script>fetch('/x')</script>"), BEISPIEL_EN]})
r = zg.auftrag({"aktion": "erklaeren", "thema": "How does a volcano work?", "fuer": "kind"}, "kim", ctx)
g1, g2 = ctx.gedacht[0], ctx.gedacht[-1]
pruef("E Bauauftrag englisch: Seite auf Englisch verlangt, Regeln unveraendert",
      'In English: <html lang="en">' in g1["system"] and "fetch" in g1["system"] and not deutsch(g1["system"])
      and g1["auftrag"].startswith("Topic: How does a volcano work?\nFor a child") and "Build the page now." in
      g1["auftrag"] and not deutsch(g1["auftrag"]), deutsch(g1["system"]) + deutsch(g1["auftrag"]))
pruef("E Reparaturauftrag englisch", len(ctx.gedacht) == 2 and "Your last page failed the security check" in g2["auftrag"]
      and "fetch (network access)" in g2["auftrag"] and not deutsch(g2["auftrag"]), g2["auftrag"][-300:])
pruef("E erklaeren: meldung", r.get("ok") is True and r["meldung"] == "Done: “How does a volcano work?” (for children). "
      "Open on the home network: " + ctx.lan("zeigen/" + r["id"]), r["meldung"])
ctx._antworten["zeigen"] = BEISPIEL_EN
r2 = zg.auftrag({"aktion": "zeigen", "thema": "Volcano"}, "alex", ctx)
pruef("E zeigen: Leinwand-Hinweis", r2.get("ok") and r2["meldung"].endswith(
    " (for adults). Open on the home network: " + ctx.lan("zeigen/" + r2["id"]) + " It's now the current page for the "
    "big screen (big-screen view “Show me”).") and r2.get("leinwand") == zg.LEINWAND_ANSICHT, r2["meldung"])
r3 = zg.auftrag({"aktion": "zeigen", "id": r["id"]}, "alex", ctx)
r4 = zg.auftrag({"aktion": "zeigen", "id": "e" * 24}, "alex", ctx)
pruef("E vorhandene Seite und unbekannte id", r3["meldung"] == "“How does a volcano work?” is now the current page for "
      "the big screen (big-screen view “Show me”). Open on the home network: " + ctx.lan("zeigen/" + r["id"])
      and r4["meldung"] == "There's no page with this id (any more). aktion liste shows the latest ones.", (r3, r4))
li = zg.auftrag({"aktion": "liste"}, "alex", ctx)["meldung"]
pruef("E liste englisch", li.startswith("The latest explainer pages:\n• ") and " (for children), by Kim, on the big "
      "screen right now: " in li and not deutsch(li), li)
ctx_leer = neuer_ctx(antworten={"zeigen": BEISPIEL_EN})
fehler_en = [zg.auftrag({"aktion": "liste"}, "kim", ctx_leer)["meldung"],
             zg.auftrag({"aktion": "erklaeren", "thema": "x"}, "gast1", ctx_leer)["meldung"],
             zg.auftrag({"aktion": "malen"}, "alex", ctx_leer)["meldung"],
             zg.auftrag({"aktion": "erklaeren", "thema": " "}, "alex", ctx_leer)["meldung"]]
pruef("E Hinweise englisch", fehler_en == [
    "No explainer pages yet.", "“Show me” is only for the family.",
    "Unknown action “malen”. Possible: erklaeren, zeigen, liste.",
    "What should I explain? Give me a topic, for example “how a volcano works”."], fehler_en)
code, typ, roh = zg.seite("zeigen/aktuell", "", ctx_leer, False)
pruef("E Platzhalterseite englisch und sauber", code == 200 and zg.LEER_HTML is zg.LEER_HTML_EN
      and '<html lang="en">' in roh.decode() and "Nothing to see right now." in roh.decode()
      and zg.pruefen(zg.LEER_HTML) == [] and not deutsch(zg.LEER_HTML), roh[:200])
pruef("E 404 englisch", zg.seite("zeigen/" + "0" * 24, "", ctx_leer, False)[2] == b"This page doesn't exist (any more).")
ctx = neuer_ctx(antworten={"zeigen": [seite_mit("<iframe></iframe>"), seite_mit("<script>top.x=1</script>")]})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Volcano"}, "alex", ctx)
pruef("E zweimal abgelehnt: ehrliche Absage", r.get("ok") is False and r["meldung"] == "The page about “Volcano” failed "
      "my security check on the second attempt too, so I won't show it. Try a slightly different wording.", r)
ctx = neuer_ctx(antworten={"zeigen": BEISPIEL_EN}, jetzt=time.time())
zg._json_schreiben(os.path.join(zg._ordner(ctx), "zaehler.json"), {"tag": zg._heute(ctx), "n": zg.TAGES_MAX})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Volcano"}, "alex", ctx)
pruef("E Tageskontingent", r["meldung"] == "I've built enough explainer pages for today (at most %d jobs a day). "
      "Again tomorrow." % zg.TAGES_MAX and not ctx.gedacht, r)
ctx = neuer_ctx(antworten={"zeigen": tageslimit})
r = zg.auftrag({"aktion": "erklaeren", "thema": "Volcano"}, "alex", ctx)
ctx2 = neuer_ctx(antworten={"zeigen": lambda a, s, st: 1 / 0})
r2 = zg.auftrag({"aktion": "erklaeren", "thema": "Volcano"}, "alex", ctx2)
pruef("E Tageslimit und anderer Fehler: englisch, ohne Technik", r.get("ok") is False and "daily limit" in r["meldung"]
      and not deutsch(r["meldung"]) and r2["meldung"] == "Thinking didn't work just now.", (r, r2))
zg.setze_sprache("de")
pruef("Zurueck auf Deutsch", zg.WERKZEUG is zg.WERKZEUG_DE and zg.SYSTEM is zg.SYSTEM_DE and zg.LEER_HTML is
      zg.LEER_HTML_DE and zg.FUER_TEXT is zg.FUER_TEXT_DE and zg.pruefen("") == ["Kein HTML-Dokument."])


# ---------------------------------------------------------------- B Browser
def browser_pruefen():
    if OHNE_BROWSER:
        print("ÜBERSPRUNGEN Browserprüfung (nur mit --browser)")
        return
    try:
        da = subprocess.run(DOCKER + ["image", "inspect", IMAGE], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        da = False
    if not da:
        print("ÜBERSPRUNGEN Browserprüfung (kein Docker oder Image %s fehlt)" % IMAGE)
        return
    ctx = neuer_ctx(antworten={"zeigen": BEISPIEL})
    sid = zg.auftrag({"aktion": "zeigen", "thema": "Wie funktioniert ein Vulkan?", "fuer": "kind"}, "kim", ctx)["id"]
    leck, gesehen = [], []

    class Hand(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            gesehen.append(self.path)
            if self.path.startswith("/leck"):
                leck.append(self.path)
                return self._senden(200, "text/plain", b"x", {})
            pfad, _, abfrage = self.path.partition("?")
            kopf = zg.SEITE_KOPFZEILEN
            if pfad.startswith("/ohne-kopf/"):
                pfad, kopf = pfad[len("/ohne-kopf"):], {}
            erg = zg.seite(pfad, abfrage, ctx, False)
            if erg is None:
                return self._senden(404, "text/plain", b"nein", {})
            self._senden(erg[0], erg[1], erg[2], kopf)

        def _senden(self, code, typ, roh, kopf):
            self.send_response(code)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(roh)))
            for k, v in kopf.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(roh)

    try:
        server = ThreadingHTTPServer(("172.17.0.1", 0), Hand)
    except OSError as x:
        print("ÜBERSPRUNGEN Browserprüfung (docker0 172.17.0.1 nicht verfügbar: %s)" % x)
        return
    basis = "http://172.17.0.1:%d/" % server.server_address[1]
    boese = "b" * 24
    zg._schreiben(os.path.join(ctx.daten, "zeigen", boese + ".html"), BOESE.replace("LECK", basis + "leck").encode())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    aus = tempfile.mkdtemp(prefix="zeigen-browser-")
    os.chmod(aus, 0o777)                     # der Container schreibt als eigener Nutzer (Ordner unter /tmp)
    try:
        r = subprocess.run(DOCKER + ["run", "--rm", "--pull", "never", "-e", "NODE_PATH=/usr/src/app/node_modules",
                            "-e", "TZ=" + (os.environ.get("TZ") or "UTC"), "-v", os.path.join(HIER, "zeigen_browser.js") + ":/skript.js:ro",
                            "-v", aus + ":/out", IMAGE, "node", "/skript.js", basis, "/out", sid, boese],
                           capture_output=True, text=True, timeout=240)
        zeilen = [z for z in r.stdout.splitlines() if z.startswith(("OK ", "FEHLER "))]
        for z in zeilen:
            name, _, info = z.split(" ", 1)[1].strip().partition(" | ")
            pruef("B " + name, z.startswith("OK "), info)
        pruef("B Browserlauf vollständig (%d Prüfungen)" % len(zeilen), r.returncode == 0 and len(zeilen) >= 25,
              (r.stdout[-300:] + r.stderr[-300:]))
        pruef("B Testserver: keine Anfrage an die Leck-Adresse", not leck, leck)
        pruef("B Testserver: nur Seiten unter zeigen/ angefragt", all(re.match(r"/(ohne-kopf/)?zeigen/|/favicon\.ico$", p)
                                                                      for p in gesehen), gesehen)
        if BILDER:
            os.makedirs(BILDER, exist_ok=True)
            for n in sorted(os.listdir(aus)):
                if n.endswith(".png"):
                    shutil.copy(os.path.join(aus, n), os.path.join(BILDER, n))
                    print("Bild: %s" % os.path.join(BILDER, n))
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(aus, ignore_errors=True)


browser_pruefen()

# ---------------------------------------------------------------- Live-Daten, Aufraeumen
pruef("X Live-Daten unberührt", wache())
for _c, _d in KONTEXTE:
    shutil.rmtree(_d, ignore_errors=True)
sys.exit(ergebnis("Zeig's mir"))
