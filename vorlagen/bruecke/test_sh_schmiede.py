#!/usr/bin/env python3
"""Tests Werkzeugschmiede (bruecke/schmiede.py, seit 0.7) mit der Attrappe: ohne Netz, ohne Claude, ohne Docker.

Teil 0 prüft den Schalter: Ohne JARVIS_SCHMIEDE=an (auch on, 1, true) ist die Schmiede aus, jede Aktion sagt das,
runde() und seite() tun nichts. Danach schaltet der Test sie ein (nur in diesem Prozess).
Teil 1 (Logik) ersetzt den Container durch denselben Läufer, lokal mit python3 -I gestartet (SANDBOX_ERSATZ); dort
laufen nur die festen Testcodes aus dieser Datei. Dazu ein Block auf Englisch (setze_sprache("en")).
Teil 2 lässt die echte Sandbox laufen (Docker, Image per Digest lokal, --pull never): Netz zu, Dateisystem read-only,
Speicher- und Prozessgrenze, Endlosschleife nach dem Zeitlimit abgebrochen, kein Container und kein Laufverzeichnis
bleibt übrig, dazu einmal vorschlag/freigeben/nutzen echt. Teil 2 läuft nur mit JARVIS_SCHMIEDE_DOCKER_TEST=1 und wenn
der Docker-Befehl (JARVIS_SCHMIEDE_DOCKER, Standard docker) funktioniert; sonst steht dort "SKIP …" und es zählt nicht
als Fehler. Das Image vorher holen: docker pull <schmiede.IMAGE>.

    python3 -B tests/test_sh_schmiede.py
    JARVIS_SCHMIEDE_DOCKER_TEST=1 JARVIS_SCHMIEDE_DOCKER="sudo docker" python3 -B tests/test_sh_schmiede.py
"""
import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "..", "bruecke"))

import sh_attrappe  # noqa: E402

pruef, ergebnis = sh_attrappe.pruefer()
wache = sh_attrappe.live_wache()

_SCHALTER_VORHER = os.environ.pop("JARVIS_SCHMIEDE", None)     # Teil 0 beginnt ausgeschaltet

import schmiede as sm  # noqa: E402

T0 = time.mktime((2026, 11, 6, 10, 0, 0, 0, 0, -1))
KONTEXTE = []
LAEUFE = []


def kontext(**kw):
    ctx = sh_attrappe.Kontext(jetzt=T0, **kw)
    KONTEXTE.append(ctx)
    return ctx


def lokale_sandbox(code, auftrag, zeitlimit):
    """Derselbe Läufer wie im Container, lokal (nur eigene Testcodes). Gleiche Auswertung wie die echte Sandbox."""
    LAEUFE.append(auftrag.get("modus"))
    ordner = tempfile.mkdtemp(prefix="sh-schmiede-lokal-")
    try:
        sm.laeufer_schreiben(ordner, code)
        start = time.monotonic()
        try:
            p = subprocess.run([sys.executable, "-I", "-B", os.path.join(ordner, "lauf.py"),
                                os.path.join(ordner, "werkzeug.py")], input=json.dumps(auftrag).encode("utf-8"),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=zeitlimit, cwd=ordner)
            r = {"rc": p.returncode, "aus": p.stdout, "err": p.stderr, "abgebrochen": False}
        except subprocess.TimeoutExpired:
            r = {"rc": -9, "aus": b"", "err": b"", "abgebrochen": True}
        r["dauer"] = time.monotonic() - start
    finally:
        shutil.rmtree(ordner, ignore_errors=True)
    return sm.auswerten(r, zeitlimit)


sm.SANDBOX_ERSATZ = lokale_sandbox
sm.IM_HINTERGRUND = False

CODE_GUT = '''def ausfuehren(eingabe):
    """Mehrwertsteuer: netto -> brutto oder brutto -> netto."""
    betrag = eingabe.get("betrag")
    satz = eingabe.get("satz", 19)
    if not isinstance(betrag, (int, float)) or isinstance(betrag, bool) or betrag < 0:
        return {"fehler": "Bitte einen Betrag ab 0 angeben."}
    if eingabe.get("richtung", "netto") == "brutto":
        netto = betrag / (1 + satz / 100)
    else:
        netto = betrag
    steuer = netto * satz / 100
    return {"netto": round(netto, 2), "steuer": round(steuer, 2), "brutto": round(netto + steuer, 2)}
'''
TESTS = [{"eingabe": {"betrag": 100}, "erwartet": {"netto": 100, "steuer": 19, "brutto": 119}},
         {"eingabe": {"betrag": 119, "richtung": "brutto"}, "erwartet": {"netto": 100, "steuer": 19}},
         {"eingabe": {"betrag": 50, "satz": 7}, "erwartet": {"steuer": 3.5, "brutto": 53.5}},
         {"eingabe": {"betrag": "x"}, "erwartet": {"fehler": "Bitte einen Betrag ab 0 angeben."}}]
SCHEMA = {"type": "object", "properties": {"betrag": {"type": "number", "description": "Betrag in Euro"},
                                           "satz": {"type": "number"}, "richtung": {"type": "string"}},
          "required": ["betrag"]}


def antwort(name="mehrwertsteuer", code=CODE_GUT, tests=None, **mehr):
    d = {"name": name, "zweck": "Rechnet Netto, Steuer und Brutto für einen Betrag.", "eingabe_schema": SCHEMA,
         "code": code, "tests": TESTS if tests is None else tests}
    d.update(mehr)
    return "Hier mein Entwurf:\n```json\n" + json.dumps(d, ensure_ascii=False) + "\n```"


GUT = antwort()
BOESE = antwort(code="import os\n" + CODE_GUT)
FALSCH = antwort(code=CODE_GUT.replace('get("satz", 19)', 'get("satz", 16)'))


def m(r):
    return r.get("meldung", "")


def a(ctx, person, **b):
    return sm.auftrag(b, person, ctx)


def code_aus_push(push):
    t = re.search(r"[Cc]ode (\d{4})", push["text"])
    return t.group(1) if t else None


def meta(ctx, name):
    with open(os.path.join(ctx.daten, "schmiede", name, "meta.json"), encoding="utf-8") as f:
        return json.load(f)


def werte(x):
    if isinstance(x, dict):
        for v in x.values():
            for w in werte(v):
                yield w
    elif isinstance(x, list):
        for v in x:
            for w in werte(v):
                yield w
    else:
        yield x


# ================================================================================== Teil 0: Schalter (aus)
AUS_DE = "Die Werkzeugschmiede ist aus"
ctx = kontext(antworten={"schmiede": [GUT]})
pruef("aus: Standard ohne JARVIS_SCHMIEDE", not sm.eingeschaltet())
pruef("aus: jede Aktion (auch liste, auch ohne aktion) sagt es, für alle Rollen",
      all(AUS_DE in m(sm.auftrag(b, p, ctx)) and "Einrichtung" in m(sm.auftrag(b, p, ctx))
          and "Docker" in m(sm.auftrag(b, p, ctx))
          for p in ("alex", "sam", "gast1", "fremd")
          for b in [{}, {"aktion": "Liste"}, None] + [{"aktion": x, "name": "abc", "bedarf": "Mehrwertsteuer rechnen",
                                                       "freigabe_code": "1234", "eingabe": {}} for x in sm.AKTIONEN]))
pruef("aus: runde() tut nichts", sm.runde(ctx) is None)
pruef("aus: seite() antwortet nicht", sm.seite("/schmiede/ansehen", {"name": "abc", "t": "x"}, ctx, True) is None
      and sm.seite("schmiede/ansehen?name=abc&t=x", None, ctx, False) is None)
pruef("aus: kein Denken, kein Push, kein Log, keine Datei", not ctx.gedacht and not ctx.pushes and not ctx.logs
      and os.listdir(ctx.daten) == [], (ctx.gedacht, ctx.pushes, ctx.logs, os.listdir(ctx.daten)))
for wert, an in (("", False), ("aus", False), ("0", False), ("false", False), ("ja", False), ("an", True),
                 ("on", True), ("1", True), ("true", True), ("AN", True), (" On ", True), ("True", True)):
    os.environ["JARVIS_SCHMIEDE"] = wert
    pruef("Schalter JARVIS_SCHMIEDE=%r -> %s" % (wert, "an" if an else "aus"), sm.eingeschaltet() is an)
os.environ.pop("JARVIS_SCHMIEDE", None)

# Docker-Befehl einstellbar, kein sudo als Standard, Sandbox-Schalter exakt
pruef("Docker-Befehl: Standard docker", sm._docker_befehl(None) == ["docker"] and sm._docker_befehl("") == ["docker"]
      and sm._docker_befehl("   ") == ["docker"])
pruef("Docker-Befehl: sudo docker als Liste", sm._docker_befehl("sudo docker") == ["sudo", "docker"]
      and sm._docker_befehl(" sudo  /usr/local/bin/docker ") == ["sudo", "/usr/local/bin/docker"])
pruef("Docker-Befehl: Anführungszeichen (shlex)", sm._docker_befehl('sudo "/opt/mein docker/docker"')
      == ["sudo", "/opt/mein docker/docker"])
pruef("Docker-Befehl: nicht zerlegbar bleibt ein Element (scheitert dann sichtbar)",
      sm._docker_befehl('sudo "docker') == ['sudo "docker'])
pruef("Docker-Befehl: DOCKER kommt aus JARVIS_SCHMIEDE_DOCKER",
      sm.DOCKER == sm._docker_befehl(os.environ.get("JARVIS_SCHMIEDE_DOCKER")), sm.DOCKER)
SCHALTER_SOLL = ["run", "--rm", "-i", "--name", "jarvis-schmiede-test", "--pull", "never",
                 "--network", "none", "--read-only", "--tmpfs", "/tmp:size=16m",
                 "--memory", "256m", "--memory-swap", "256m", "--pids-limit", "64", "--ulimit", "nproc=64:64",
                 "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
                 "--cpu-shares", "256", "--log-driver", "none", "-e", "PYTHONDONTWRITEBYTECODE=1",
                 "-v", "/tmp/x:/werkzeug:ro", "--workdir", "/tmp", sm.IMAGE,
                 "timeout", "-s", "KILL", "20", "python3", "-I", "-B", "/werkzeug/lauf.py", "/werkzeug/werkzeug.py"]
_docker_alt = sm.DOCKER
sm.DOCKER = ["docker"]
befehl = sm.sandbox_befehl("/tmp/x", "jarvis-schmiede-test", 20)
pruef("Sandbox-Befehl: Standard ohne sudo, alle Schalter exakt", befehl == ["docker"] + SCHALTER_SOLL
      and "sudo" not in befehl, befehl)
sm.DOCKER = ["sudo", "docker"]
befehl = sm.sandbox_befehl("/tmp/x", "jarvis-schmiede-test", 20)
pruef("Sandbox-Befehl: mit sudo docker davor, Schalter gleich", befehl == ["sudo", "docker"] + SCHALTER_SOLL, befehl)
sm.DOCKER = _docker_alt
pruef("Image per Digest", sm.IMAGE.startswith("python@sha256:") and len(sm.IMAGE) == len("python@sha256:") + 64)
pruef("Sandbox-Befehl: kein --cpus", not any(f.startswith("--cpus") for f in befehl))

# ab hier eingeschaltet (nur in diesem Prozess)
os.environ["JARVIS_SCHMIEDE"] = "an"
pruef("an: eingeschaltet", sm.eingeschaltet())
pruef("an: runde() tut trotzdem nichts", sm.runde(ctx) is None and os.listdir(ctx.daten) == [])

# ================================================================================== Teil 1: statische Prüfung
pruef("gültiger Code besteht", sm.code_pruefen(CODE_GUT) == [], sm.code_pruefen(CODE_GUT))
ERLAUBT_CODE = ("import math, datetime\nfrom collections import Counter\nimport re as r\n"
                "def ausfuehren(e):\n    return {'a': math.sqrt(2), 'b': r.sub('a', 'b', 'c'),"
                " 'c': datetime.date(2026, 1, 1).isoformat(), 'd': '{:.2f} {0}'.format(1)}\n")
pruef("erlaubte Importe", sm.code_pruefen(ERLAUBT_CODE) == [], sm.code_pruefen(ERLAUBT_CODE))
pruef("getattr mit festem Namen erlaubt", sm.code_pruefen("def ausfuehren(e):\n    return {'x': getattr(e, 'get', "
                                                          "None) is not None}\n") == [])
FALL = {
    "import os": "import os\ndef ausfuehren(e):\n    return {}\n",
    "import subprocess als Teil": "import json, subprocess\ndef ausfuehren(e):\n    return {}\n",
    "from os import system": "from os import system\ndef ausfuehren(e):\n    return {}\n",
    "relativer Import": "from . import x\ndef ausfuehren(e):\n    return {}\n",
    "from calendar import sys": "from calendar import sys\ndef ausfuehren(e):\n    return {}\n",
    "from math import *": "from math import *\ndef ausfuehren(e):\n    return {}\n",
    "open": "def ausfuehren(e):\n    return {'x': open('/etc/passwd').read()}\n",
    "eval": "def ausfuehren(e):\n    return {'x': eval('1+1')}\n",
    "exec": "def ausfuehren(e):\n    exec('x=1')\n    return {}\n",
    "compile": "def ausfuehren(e):\n    compile('1', 'a', 'eval')\n    return {}\n",
    "__import__": "def ausfuehren(e):\n    return {'x': __import__('os')}\n",
    "globals": "def ausfuehren(e):\n    return {'x': len(globals())}\n",
    "getattr mit Dunder": "def ausfuehren(e):\n    return {'x': getattr(e, '__class__')}\n",
    "getattr mit Variable": "def ausfuehren(e):\n    n = 'get'\n    return {'x': getattr(e, n)}\n",
    "getattr als Wert": "def ausfuehren(e):\n    g = getattr\n    return {}\n",
    "setattr": "def ausfuehren(e):\n    setattr(e, 'a', 1)\n    return {}\n",
    "Dunder-Attribut": "def ausfuehren(e):\n    return {'x': ().__class__.__base__}\n",
    "random._os": "import random\ndef ausfuehren(e):\n    return {'x': random._os.getcwd()}\n",
    "calendar.sys": "import calendar\ndef ausfuehren(e):\n    return {'x': calendar.sys.version}\n",
    "re.enum.bltns": "import re\ndef ausfuehren(e):\n    return {'x': re.enum.bltns}\n",
    "fractions.operator": "import fractions\ndef ausfuehren(e):\n    return {'x': fractions.operator}\n",
    "Zeichenkette mit __": "def ausfuehren(e):\n    return {'x': '{0.__class__}'.format(e)}\n",
    # Prüfbericht vor 0.7 (M4): Positivliste je Modul, Module nicht weitergeben, Formatketten
    "json.codecs.open (Bericht)": "import json\ndef ausfuehren(e):\n    return {'t': json.codecs.open('/etc/hostname').read()}\n",
    "re.functools (Bericht)": "import re\ndef ausfuehren(e):\n    return {'t': str(re.functools)}\n",
    "Modul zuweisen": "import json\ndef ausfuehren(e):\n    j = json\n    return {'t': j.codecs}\n",
    "Modul an getattr": "import json\ndef ausfuehren(e):\n    return {'t': getattr(json, 'codecs')}\n",
    "Modul als Argument": "import json\ndef ausfuehren(e):\n    return {'t': str(json)}\n",
    "from json import codecs": "from json import codecs\ndef ausfuehren(e):\n    return {}\n",
    "from json import load": "from json import load\ndef ausfuehren(e):\n    return {}\n",
    "Untermodul importieren": "import collections.abc\ndef ausfuehren(e):\n    return {}\n",
    "statistics.itemgetter": "import statistics\ndef ausfuehren(e):\n    return {'x': statistics.itemgetter(0)}\n",
    "hashlib.file_digest": "import hashlib\ndef ausfuehren(e):\n    return {'x': hashlib.file_digest}\n",
    "format an Variable": "def ausfuehren(e):\n    f = '{0.' + '_' * 2 + 'class' + '_' * 2 + '}'\n    return {'x': f.format(e)}\n",
    "format mit Index": "def ausfuehren(e):\n    return {'x': '{0[a]}'.format(e)}\n",
    "format mit Punkt": "def ausfuehren(e):\n    return {'x': '{0.real}'.format(1)}\n",
    "format_map": "def ausfuehren(e):\n    return {'x': '{a}'.format_map(e)}\n",
    # Nachprüfung vor 0.7 (M4): Code-Objekte aus Koroutinen/Generatoren, type(), object, super, Syntax
    "async def (ag_code)": "async def g():\n    yield 1\ndef ausfuehren(e):\n    return {'x': str(g().ag_code)}\n",
    "cr_code + replace + type": ("async def g(x):\n    return x.y\ndef ausfuehren(e):\n    c = g(None)\n    k = c.cr_code\n"
                                 "    c.close()\n    return {'x': str(k)}\n"),
    "await": "async def ausfuehren(e):\n    await g()\n    return {}\n",
    "yield in Funktion": "def ausfuehren(e):\n    yield 1\n",
    "yield from": "def h(e):\n    yield from e\ndef ausfuehren(e):\n    return {}\n",
    "Generator-Ausdruck": "def ausfuehren(e):\n    g = (x for x in [1, 2])\n    return {'x': str(g.gi_code)}\n",
    "type() als Funktionsbau": "def ausfuehren(e):\n    return {'x': type(ausfuehren)(None, {})}\n",
    "type(x) Typpruefung": "def ausfuehren(e):\n    return {'x': type(e).__name__}\n",
    "object.__subclasses__": "def ausfuehren(e):\n    return {'x': len(object.__subclasses__(object))}\n",
    "super": "def ausfuehren(e):\n    return {'x': str(super)}\n",
    ".replace an Code (co_names)": ("def f():\n    pass\ndef ausfuehren(e):\n    c = f.__code__\n    "
                                   "return {'x': str(c.co_names)}\n"),
    "AttributeError.obj": "def ausfuehren(e):\n    try:\n        e.x\n    except AttributeError as f:\n"
                          "        return {'x': str(f.obj)}\n    return {}\n",
    "Name mit __": "def ausfuehren(e):\n    return {'x': __builtins__}\n",
    "ohne ausfuehren": "def rechne(e):\n    return {}\n",
    "async ausfuehren": "async def ausfuehren(e):\n    return {}\n",
    "ausfuehren ohne Parameter": "def ausfuehren():\n    return {}\n",
    "ausfuehren mit zwei Pflichtparametern": "def ausfuehren(a, b):\n    return {}\n",
    "Syntaxfehler": "def ausfuehren(e)\n    return {}\n",
    "zu lang": "def ausfuehren(e):\n    return {}\n" + "# x\n" * sm.MAX_CODE_ZEILEN,
    "zu viele Zeichen": "def ausfuehren(e):\n    return {'x': '%s'}\n" % ("a" * sm.MAX_CODE_ZEICHEN),
    "leer": "   ",
}
for name, code in FALL.items():
    p = sm.code_pruefen(code)
    pruef("statisch abgelehnt: %s" % name, bool(p), code[:60])
pruef("Problemtext nennt die Zeile", any(t.startswith("Zeile 1: Import „os“") for t in sm.code_pruefen(FALL["import os"])),
      sm.code_pruefen(FALL["import os"]))

e, p = sm.entwurf_pruefen(json.loads(GUT.split("```json\n")[1].split("\n```")[0]))
pruef("entwurf_pruefen: gültig", e is not None and p == [] and e["name"] == "mehrwertsteuer", p)
e, p = sm.entwurf_pruefen({"name": "Mehrwert-Steuer", "zweck": "x", "eingabe_schema": SCHEMA, "code": CODE_GUT,
                           "tests": TESTS})
pruef("entwurf_pruefen: falscher Name", e is not None and any("name" in x for x in p), p)
e, p = sm.entwurf_pruefen({"name": "abc", "zweck": "x", "eingabe_schema": SCHEMA, "code": CODE_GUT,
                           "tests": [{"eingabe": {}, "erwartet": {}}]})
pruef("entwurf_pruefen: leeres erwartet und zu wenige Tests", any("erwartet" in x for x in p)
      and any("Mindestens" in x for x in p), p)
e, p = sm.entwurf_pruefen({"name": "abc", "tests": TESTS})
pruef("entwurf_pruefen: ohne Code kein Entwurf", e is None and any("code" in x for x in p), p)
e, p = sm.entwurf_pruefen({"name": "mehrwertsteuer", "zweck": "x", "eingabe_schema": SCHEMA, "code": CODE_GUT,
                           "tests": TESTS}, belegt={"mehrwertsteuer", "mehrwertsteuer_2"})
pruef("entwurf_pruefen: belegter Name bekommt Anhang", e["name"] == "mehrwertsteuer_3", e["name"])
pruef("Namensregel", all(sm.NAME_MUSTER.fullmatch(n) for n in ("abc", "a_1", "a" * 31))
      and not any(sm.NAME_MUSTER.fullmatch(n) for n in ("ab", "1ab", "Abc", "a-b", "a" * 32, "_ab", "äbc")))

# ================================================================================== Teil 1: Läufer (lokal)
r = lokale_sandbox(CODE_GUT, {"modus": "tests", "tests": TESTS, "je_s": 5}, 20)
pruef("Läufer: alle Tests grün", r.get("ok") is True and len(r.get("einzeln", [])) == 4, r)
r = lokale_sandbox(CODE_GUT, {"modus": "nutzen", "eingabe": {"betrag": 10}, "je_s": 5}, 20)
pruef("Läufer: nutzen liefert Ergebnis", r.get("ok") and r.get("ergebnis") == {"netto": 10, "steuer": 1.9,
                                                                              "brutto": 11.9}, r)
r = lokale_sandbox("def ausfuehren(e):\n    return {'x': open('/etc/hostname').read()}\n",
                   {"modus": "nutzen", "eingabe": {}, "je_s": 5}, 20)
pruef("Läufer: open fehlt zur Laufzeit (zweite Linie)", not r.get("ok") and "NameError" in r.get("fehler", ""), r)
r = lokale_sandbox("def ausfuehren(e):\n    return {'x': str(type(e))}\n", {"modus": "nutzen", "eingabe": {}}, 20)
pruef("Läufer: type fehlt zur Laufzeit (zweite Linie)", not r.get("ok") and "NameError" in r.get("fehler", ""), r)
r = lokale_sandbox("def ausfuehren(e):\n    import socket\n    return {}\n", {"modus": "nutzen", "eingabe": {}}, 20)
pruef("Läufer: Import außerhalb der Liste zur Laufzeit gesperrt", not r.get("ok")
      and "Import nicht erlaubt: socket" in r.get("fehler", ""), r)
r = lokale_sandbox("def ausfuehren(e):\n    print('Störfeuer')\n    return [1]\n", {"modus": "nutzen", "eingabe": {}}, 20)
pruef("Läufer: Ergebnis muss dict sein, print stört nicht", not r.get("ok") and "dict" in r.get("fehler", ""), r)
r = lokale_sandbox("def ausfuehren(e):\n    return {'x': float('nan')}\n", {"modus": "nutzen", "eingabe": {}}, 20)
pruef("Läufer: NaN ist kein JSON", not r.get("ok") and "JSON" in r.get("fehler", ""), r)
r = lokale_sandbox("def ausfuehren(e):\n    x = 1\n    return {'x': 1 / (x - 1)}\n", {"modus": "nutzen", "eingabe": {}},
                   20)
pruef("Läufer: Fehler mit Zeile", not r.get("ok") and "ZeroDivisionError" in r["fehler"] and "(Zeile 3)" in r["fehler"],
      r)
r = lokale_sandbox("def rechne(e):\n    return {}\n", {"modus": "nutzen", "eingabe": {}}, 20)
pruef("Läufer: ohne ausfuehren", not r.get("ok") and "Laden:" in r["fehler"] and "ausfuehren fehlt" in r["fehler"], r)
SCHLEIFE_TEST = "def ausfuehren(e):\n    if e.get('n') == 2:\n        while True:\n            pass\n    return {'n': e['n']}\n"
r = lokale_sandbox(SCHLEIFE_TEST, {"modus": "tests", "je_s": 1, "tests": [
    {"eingabe": {"n": 1}, "erwartet": {"n": 1}}, {"eingabe": {"n": 2}, "erwartet": {"n": 2}},
    {"eingabe": {"n": 3}, "erwartet": {"n": 3}}]}, 20)
pruef("Läufer: Endlosschleife in einem Test bricht nur diesen ab", r.get("ok") is False
      and [x["ok"] for x in r["einzeln"]] == [True, False, True] and "Zeitlimit" in r["einzeln"][1]["fehler"], r)
r = lokale_sandbox(CODE_GUT, {"modus": "tests", "je_s": 5, "tests": [
    {"eingabe": {"betrag": 100}, "erwartet": {"brutto": 119.0000001}},
    {"eingabe": {"betrag": 100}, "erwartet": {"brutto": 118}}]}, 20)
pruef("Läufer: Vergleich mit Toleranz, erwartet als Teilmenge", [x["ok"] for x in r["einzeln"]] == [True, False]
      and "erwartet" in r["einzeln"][1]["fehler"], r)

# auswerten (Rohergebnisse wie vom Container)
pruef("auswerten: Image fehlt -> Sandbox-Fehler", sm.auswerten({"rc": 125, "aus": b"", "err": b"WARNING: Your kernel "
      b"does not support PIDs limit\nUnable to find image", "dauer": 0.3}, 20).get("sandbox_fehler") is True)
pruef("auswerten: Docker fehlt (rc None) -> Sandbox-Fehler", sm.auswerten({"rc": None, "aus": b"", "err": b"No such "
      b"file or directory: 'docker'", "dauer": 0.0}, 20).get("sandbox_fehler") is True)
pruef("auswerten: von außen abgebrochen -> Zeitlimit", sm.auswerten({"rc": -9, "aus": b"", "err": b"", "dauer": 35,
                                                                     "abgebrochen": True}, 20).get("zeitlimit") is True)
pruef("auswerten: 124 nach 21 s -> Zeitlimit", sm.auswerten({"rc": 124, "aus": b"", "err": b"", "dauer": 21}, 20)
      .get("zeitlimit") is True)
pruef("auswerten: 137 nach 2 s -> Speicher", "256 MB" in sm.auswerten({"rc": 137, "aus": b"", "err": b"", "dauer": 2},
                                                                      20)["fehler"])
pruef("auswerten: Warnung über PIDs nicht im Fehlertext", "PIDs" not in sm.auswerten(
    {"rc": 125, "aus": b"", "err": b"WARNING: Your kernel does not support PIDs limit\nkaputt", "dauer": 1}, 20)["fehler"])
_falsch = (sm.MARKE + '{"ok": true, "einzeln": [{"nr": 1, "ok": true}]}\n').encode()
pruef("K3 auswerten: Markenzeile bei rc 137 oder Abbruch verworfen, eigene Marke je Lauf",
      not sm.auswerten({"rc": 137, "aus": _falsch, "err": b"", "dauer": 1.0}, 20).get("ok")
      and not sm.auswerten({"rc": 0, "aus": _falsch, "err": b"", "dauer": 1.0, "abgebrochen": True}, 20).get("ok")
      and not sm.auswerten({"rc": 0, "aus": _falsch, "err": b"", "dauer": 1.0}, 20, "<<<SCHMIEDE-andere>>>").get("ok")
      and sm.auswerten({"rc": 0, "aus": _falsch, "err": b"", "dauer": 1.0}, 20).get("ok"))

# ================================================================================== Teil 1: Rechte
ctx = kontext(antworten={"schmiede": [GUT]})
pruef("Sam darf nicht vorschlagen", "nur Alex" in m(a(ctx, "sam", aktion="vorschlag", bedarf="Mehrwertsteuer "
                                                                                             "rechnen bitte")))
pruef("Kim darf nicht freigeben", "nur Alex" in m(a(ctx, "kim", aktion="freigeben", name="abc", freigabe_code="1")))
pruef("Kim darf nicht verwerfen", "nur Alex" in m(a(ctx, "kim", aktion="verwerfen", name="abc")))
pruef("Gast darf gar nichts", all("nur für die Familie" in m(a(ctx, "gast1", aktion=x, name="abc"))
                                  for x in sm.AKTIONEN))
pruef("Unbekannte Person darf gar nichts", "nur für die Familie" in m(a(ctx, "fremd", aktion="liste")))
pruef("abgelehnt ohne Denken", not ctx.gedacht)
pruef("ohne aktion = liste", "Noch keine eigenen Werkzeuge" in m(sm.auftrag({}, "alex", ctx)))
pruef("unbekannte aktion", "aktion muss" in m(a(ctx, "alex", aktion="bauen")))
pruef("aktion genau geschrieben", "aktion muss" in m(a(ctx, "alex", aktion="Liste")))
pruef("Bedarf zu kurz", "Bedarf" in m(a(ctx, "alex", aktion="vorschlag", bedarf="x")))
pruef("ungültiger Name", "Welches Werkzeug" in m(a(ctx, "kim", aktion="nutzen", name="../x")))

# ================================================================================== Teil 1: vorschlag bis nutzen
ctx = kontext(antworten={"schmiede": [GUT]})
LAEUFE[:] = []
r = a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto",
      beispiele=["Was sind 119 Euro brutto netto?"])
pruef("vorschlag: Entwurf steht", "Entwurf „mehrwertsteuer“ steht" in m(r) and "4 von 4" in m(r), m(r))
pruef("vorschlag: kein Freigabe-Code in der Antwort", not re.search(r"Code \d{4}", m(r)) and "Push" in m(r)
      and "Alex hat einen Push" in m(r), m(r))
pruef("vorschlag: ein Denkaufruf, Stufe normal, zweck schmiede", len(ctx.gedacht) == 1
      and ctx.gedacht[0]["stufe"] == "normal" and ctx.gedacht[0]["zweck"] == "schmiede"
      and ctx.gedacht[0]["werkzeuge"] == ())
pruef("vorschlag: Bedarf und Beispiel im Auftrag", "netto und brutto" in ctx.gedacht[0]["auftrag"]
      and "119 Euro" in ctx.gedacht[0]["auftrag"] and "Erlaubte Importe" in ctx.gedacht[0]["system"])
pruef("vorschlag: Tests in der Sandbox gelaufen", LAEUFE == ["tests"], LAEUFE)
pruef("vorschlag: Push an Alex", len(ctx.pushes) == 1 and ctx.pushes[0]["person"] == "alex"
      and "mehrwertsteuer" in ctx.pushes[0]["titel"] and ctx.pushes[0]["tag"] == "jarvis-schmiede", ctx.pushes)
code_wort = code_aus_push(ctx.pushes[0])
pruef("Push: Freigabe-Hinweis mit Code", code_wort is not None and "Werkzeug mehrwertsteuer freigeben, Code %s" %
      code_wort in ctx.pushes[0]["text"] and "Tests: 4 von 4" in ctx.pushes[0]["text"], ctx.pushes[0]["text"])
pruef("Push: Link zur Ansicht", (ctx.pushes[0]["klick"] or "").startswith("https://jarvis.test.invalid/schmiede/ansehen?"
                                                                          "name=mehrwertsteuer&t="))
o = os.path.join(ctx.daten, "schmiede", "mehrwertsteuer")
pruef("Dateien: code.py und meta.json 0600, Ordner 0700",
      stat.S_IMODE(os.stat(os.path.join(o, "code.py")).st_mode) == 0o600
      and stat.S_IMODE(os.stat(os.path.join(o, "meta.json")).st_mode) == 0o600
      and stat.S_IMODE(os.stat(o).st_mode) == 0o700)
mt = meta(ctx, "mehrwertsteuer")
pruef("meta: Status entwurf, Testergebnis", mt["status"] == "entwurf" and mt["testergebnis"]["ok"] is True
      and mt["testergebnis"]["bestanden"] == 4 and mt["erstellt_von"] == "alex" and mt["denkrunden"] == 1)
with open(os.path.join(o, "code.py"), encoding="utf-8") as f:
    pruef("meta: Code gleich, Prüfsumme", f.read() == CODE_GUT and mt["sha256"] == sm._sha(CODE_GUT))
pruef("meta: Freigabe-Code nicht im Klartext", code_wort not in [str(w) for w in werte(mt)] and "freigabe_hash" in mt)
pruef("Log ohne Code", not any(code_wort in z for z in ctx.logs), ctx.logs)

r = a(ctx, "alex", aktion="liste")
pruef("liste Alex: Entwurf sichtbar", "mehrwertsteuer [entwurf, Tests 4 von 4]" in m(r), m(r))
r = a(ctx, "kim", aktion="liste")
pruef("liste Kim: Entwurf unsichtbar", "Noch keine" in m(r), m(r))
pruef("zeigen Kim: Entwurf unsichtbar", "gibt es nicht" in m(a(ctx, "kim", aktion="zeigen", name="mehrwertsteuer")))
r = a(ctx, "alex", aktion="zeigen", name="mehrwertsteuer")
pruef("zeigen Alex: Code und Tests", CODE_GUT in m(r) and "1. ok" in m(r) and r.get("status") == "entwurf", m(r)[:300])
pruef("nutzen eines Entwurfs geht nicht", "Ein aktives Werkzeug" in m(a(ctx, "alex", aktion="nutzen",
                                                                         name="mehrwertsteuer", eingabe={"betrag": 1})))

# freigeben
pruef("freigeben ohne Code fragt", "Freigabe-Code" in m(a(ctx, "alex", aktion="freigeben", name="mehrwertsteuer")))
falsch = "%04d" % ((int(code_wort) + 1) % 10000)
r = a(ctx, "alex", aktion="freigeben", name="mehrwertsteuer", freigabe_code=falsch)
pruef("freigeben falscher Code", "stimmt nicht (noch 2 Versuche)" in m(r), m(r))
r = a(ctx, "alex", aktion="freigeben", name="mehrwertsteuer", freigabe_code=" ".join(code_wort))
pruef("freigeben richtiger Code (gesprochen mit Leerzeichen)", "ist freigegeben" in m(r) and "betrag (number)" in m(r),
      m(r))
mt = meta(ctx, "mehrwertsteuer")
pruef("meta: aktiv, Code-Hash entfernt", mt["status"] == "aktiv" and "freigabe_hash" not in mt
      and mt["freigegeben_von"] == "alex")
pruef("nochmal freigeben", "schon aktiv" in m(a(ctx, "alex", aktion="freigeben", name="mehrwertsteuer",
                                                freigabe_code=code_wort)))

# nutzen
LAEUFE[:] = []
r = a(ctx, "kim", aktion="nutzen", name="mehrwertsteuer", eingabe={"betrag": 200})
pruef("nutzen Kim: Ergebnis", r.get("ergebnis") == {"netto": 200, "steuer": 38, "brutto": 238}
      and "Ergebnis von „mehrwertsteuer“" in m(r), r)
pruef("nutzen läuft in der Sandbox", LAEUFE == ["nutzen"], LAEUFE)
r = a(ctx, "sam", aktion="nutzen", name="mehrwertsteuer", eingabe='{"betrag": 119, "richtung": "brutto"}')
pruef("nutzen mit eingabe als JSON-Text", (r.get("ergebnis") or {}).get("netto") == 100, r)
pruef("nutzen: Pflichtfeld fehlt", "Es fehlt das Feld „betrag“" in m(a(ctx, "kim", aktion="nutzen",
                                                                       name="mehrwertsteuer", eingabe={})))
pruef("nutzen: falscher Typ", "„betrag“ muss eine Zahl sein" in m(a(ctx, "kim", aktion="nutzen", name="mehrwertsteuer",
                                                                     eingabe={"betrag": "zwei"})))
pruef("nutzen: Unsinn statt Objekt", "Objekt" in m(a(ctx, "kim", aktion="nutzen", name="mehrwertsteuer",
                                                       eingabe="kein json")))
pruef("nutzen zählt mit", meta(ctx, "mehrwertsteuer")["nutzungen"] == 2)
pruef("liste Kim: aktives Werkzeug mit Feldern", "mehrwertsteuer: Rechnet Netto" in m(a(ctx, "kim", aktion="liste"))
      and "betrag (number)" in m(a(ctx, "kim", aktion="liste")))
pruef("zeigen Kim: aktives Werkzeug", CODE_GUT in m(a(ctx, "kim", aktion="zeigen", name="mehrwertsteuer")))

# Code nach der Freigabe verändert: läuft nicht
LAEUFE[:] = []
with open(os.path.join(o, "code.py"), "a", encoding="utf-8") as f:
    f.write("\n# nachträglich\n")
r = a(ctx, "kim", aktion="nutzen", name="mehrwertsteuer", eingabe={"betrag": 1})
pruef("veränderter Code wird nicht ausgeführt", "weicht von der freigegebenen Fassung ab" in m(r) and not LAEUFE, m(r))
with open(os.path.join(o, "code.py"), "w", encoding="utf-8") as f:
    f.write(CODE_GUT)

# Stundenlimit
alt = sm.NUTZUNGEN_STUNDE
sm.NUTZUNGEN_STUNDE = len(sm._nutzungen)
pruef("Stundenlimit für Läufe", "in der letzten Stunde" in m(a(ctx, "kim", aktion="nutzen", name="mehrwertsteuer",
                                                                eingabe={"betrag": 1})))
sm.NUTZUNGEN_STUNDE = alt

# Name belegt: neuer Vorschlag bekommt _2
ctx._antworten["schmiede"] = [GUT]
r = a(ctx, "alex", aktion="vorschlag", bedarf="Noch einmal Mehrwertsteuer, bitte")
pruef("belegter Name: mehrwertsteuer_2", "„mehrwertsteuer_2“" in m(r) and meta(ctx, "mehrwertsteuer")["status"] == "aktiv",
      m(r))
pruef("vorhandene Werkzeuge im Auftrag genannt", "- mehrwertsteuer: Rechnet Netto" in ctx.gedacht[-1]["auftrag"])

# verwerfen
pruef("verwerfen unbekannt", "gibt es nicht" in m(a(ctx, "alex", aktion="verwerfen", name="gibtsnicht")))
r = a(ctx, "alex", aktion="verwerfen", name="mehrwertsteuer")
pruef("verwerfen aktiv", "verworfen und läuft nicht mehr" in m(r), m(r))
pruef("verworfen: nicht mehr nutzbar", "Ein aktives Werkzeug" in m(a(ctx, "kim", aktion="nutzen", name="mehrwertsteuer",
                                                                     eingabe={"betrag": 1})))
pruef("verworfen: aufgehoben unter .verworfen", len(glob.glob(os.path.join(ctx.daten, "schmiede", ".verworfen",
                                                                           "mehrwertsteuer-*"))) == 1)
pruef("verworfen: nicht in der Liste", "mehrwertsteuer:" not in m(a(ctx, "alex", aktion="liste")))

# ================================================================================== Teil 1: Reparaturrunden
ctx = kontext(antworten={"schmiede": [BOESE, GUT]})
r = a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
pruef("Reparatur nach statischem Fehler: Entwurf steht", "steht" in m(r) and len(ctx.gedacht) == 2, m(r))
pruef("Reparatur-Auftrag nennt das Problem", "Import „os“ ist nicht erlaubt" in ctx.gedacht[1]["auftrag"]
      and "Entwurf:" in ctx.gedacht[1]["auftrag"])
pruef("meta: zwei Denkrunden", meta(ctx, "mehrwertsteuer")["denkrunden"] == 2)

ctx = kontext(antworten={"schmiede": [FALSCH, GUT]})
LAEUFE[:] = []
r = a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
pruef("Reparatur nach roten Tests", "steht" in m(r) and LAEUFE == ["tests", "tests"], (m(r), LAEUFE))
pruef("Reparatur-Auftrag nennt den Test", "Test 1: erwartet" in ctx.gedacht[1]["auftrag"], ctx.gedacht[1]["auftrag"][-400:])

ctx = kontext(antworten={"schmiede": [antwort(name="Mehrwert-Steuer"), GUT]})
r = a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
pruef("Reparatur nach falschem Namen", "„mehrwertsteuer“ steht" in m(r) and "name" in ctx.gedacht[1]["auftrag"], m(r))

ctx = kontext(antworten={"schmiede": [FALSCH, FALSCH, FALSCH, GUT]})
r = a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
pruef("höchstens 2 Reparaturrunden (3 Denkaufrufe)", len(ctx.gedacht) == 3, len(ctx.gedacht))
pruef("gescheitert gemeldet", "nicht hinbekommen" in m(r) and "nach 3 Versuchen" in m(r), m(r))
pruef("gescheitert gespeichert", meta(ctx, "mehrwertsteuer")["status"] == "gescheitert")
pruef("gescheitert: Push ohne Code", len(ctx.pushes) == 1 and "nicht fertig" in ctx.pushes[0]["titel"]
      and not re.search(r"Code \d{4}", ctx.pushes[0]["text"]), ctx.pushes)
pruef("gescheitert: nicht freigebbar", "nicht bestanden" in m(a(ctx, "alex", aktion="freigeben",
                                                                name="mehrwertsteuer", freigabe_code="0000")))
pruef("gescheitert: zeigen nennt die Probleme", "Problem: Test 1" in m(a(ctx, "alex", aktion="zeigen",
                                                                          name="mehrwertsteuer")))

ctx = kontext(antworten={"schmiede": ['{"name": "x"}', "kein json", '{"tests": []}', '{"name": "y"}']})
r = a(ctx, "alex", aktion="vorschlag", bedarf="Etwas ganz Unklares bauen")
pruef("nichts Brauchbares: nichts gespeichert", "kein brauchbares Werkzeug" in m(r) and not sm._alle(ctx), m(r))


class DenkenKaputt(sh_attrappe.Kontext):
    def denken_json(self, *a, **kw):
        raise RuntimeError("Tageslimit")


ctx = DenkenKaputt(jetzt=T0)
KONTEXTE.append(ctx)
pruef("Denken scheitert: freundliche Meldung", "nicht nachdenken" in m(a(ctx, "alex", aktion="vorschlag",
                                                                         bedarf="Mehrwertsteuer rechnen bitte")))

# Sandbox kaputt: nichts speichern, keine Reparatur verschwenden
alt_ersatz = sm.SANDBOX_ERSATZ
sm.SANDBOX_ERSATZ = lambda code, auftrag, zl: {"ok": False, "sandbox_fehler": True, "fehler": "Image fehlt"}
ctx = kontext(antworten={"schmiede": [GUT, GUT]})
r = a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
pruef("Sandbox kaputt: nichts gespeichert, ein Denkaufruf", "Sandbox läuft gerade nicht" in m(r) and not sm._alle(ctx)
      and len(ctx.gedacht) == 1, m(r))
sm.SANDBOX_ERSATZ = alt_ersatz

# ================================================================================== Teil 1: falsche Codes, Grenzen
ctx = kontext(antworten={"schmiede": [GUT]})
a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
code_wort = code_aus_push(ctx.pushes[-1])
falsch = "%04d" % ((int(code_wort) + 1) % 10000)
for i in range(sm.FALSCHE_CODES):
    r = a(ctx, "alex", aktion="freigeben", name="mehrwertsteuer", freigabe_code=falsch)
pruef("drei falsche Codes sperren", "jetzt gesperrt" in m(r) and meta(ctx, "mehrwertsteuer")["status"] == "gesperrt", m(r))
pruef("gesperrt: auch der richtige Code hilft nicht", "gesperrt" in m(a(ctx, "alex", aktion="freigeben",
                                                                         name="mehrwertsteuer", freigabe_code=code_wort)))


def aktiv_anlegen(ctx, name):
    o = os.path.join(ctx.daten, "schmiede", name)
    os.makedirs(o, mode=0o700, exist_ok=True)
    sm._schreiben(os.path.join(o, "code.py"), CODE_GUT)
    sm._meta_speichern(ctx, name, {"name": name, "zweck": "x", "eingabe_schema": SCHEMA, "tests": TESTS,
                                   "status": "aktiv", "sha256": sm._sha(CODE_GUT), "ansehen_token": "t"})


ctx = kontext(antworten={"schmiede": [GUT]})
a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
code_wort = code_aus_push(ctx.pushes[-1])
for i in range(sm.MAX_AKTIV):
    aktiv_anlegen(ctx, "werkzeug_%02d" % i)
r = a(ctx, "alex", aktion="freigeben", name="mehrwertsteuer", freigabe_code=code_wort)
pruef("höchstens 20 aktive: Freigabe abgelehnt", "schon 20" in m(r), m(r))
pruef("höchstens 20 aktive: Vorschlag abgelehnt", "schon 20" in m(a(ctx, "alex", aktion="vorschlag",
                                                                    bedarf="Noch ein Werkzeug bitte")))

ctx = kontext(antworten={"schmiede": [GUT]})
sm._schreiben(os.path.join(sm._ordner(ctx), "zaehler.json"), json.dumps(
    {"tag": time.strftime("%Y-%m-%d", time.localtime(T0)), "vorschlaege": sm.MAX_VORSCHLAEGE_TAG}))
pruef("Tageslimit für Vorschläge", "morgen wieder" in m(a(ctx, "alex", aktion="vorschlag",
                                                          bedarf="Mehrwertsteuer rechnen bitte")) and not ctx.gedacht)

# ================================================================================== Teil 1: im Hintergrund
sm.IM_HINTERGRUND = True


def langsam(auftrag, system, stufe):
    time.sleep(0.5)
    return GUT


ctx = kontext(antworten={"schmiede": langsam})
r = a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
pruef("Hintergrund: sofortige Antwort", "baue mir das Werkzeug jetzt" in m(r) and not ctx.pushes, m(r))
r2 = a(ctx, "alex", aktion="vorschlag", bedarf="Noch ein Werkzeug, gleichzeitig")
pruef("Hintergrund: nur ein Bau gleichzeitig", "baue gerade schon" in m(r2), m(r2))
ende = time.time() + 30
while not ctx.pushes and time.time() < ende:
    time.sleep(0.1)
time.sleep(0.2)
pruef("Hintergrund: Push kommt", len(ctx.pushes) == 1 and code_aus_push(ctx.pushes[0]), ctx.pushes)
pruef("Hintergrund: Sperre wieder frei", sm._bau_sperre.acquire(blocking=False))
sm._bau_sperre.release()
sm.IM_HINTERGRUND = False

# ================================================================================== Teil 1: Ansicht
ctx = kontext(antworten={"schmiede": [GUT]})
a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
token = meta(ctx, "mehrwertsteuer")["ansehen_token"]
r = sm.seite("/schmiede/ansehen", {"name": ["mehrwertsteuer"], "t": [token]}, ctx, True)
pruef("Ansicht: 200 HTML", r and r[0] == 200 and r[1].startswith("text/html"), r and r[:2])
seite_text = r[2].decode("utf-8") if r else ""
pruef("Ansicht: Code escaped, Tests, Hinweis", "betrag &lt; 0" in seite_text and "Fehler" not in seite_text.split(
    "<h2>Code")[0].split("<h2>Tests")[1] and "Freigeben: Sag" in seite_text and 'lang="de"' in seite_text,
      seite_text[:200])
pruef("Ansicht: Code nicht auf der Seite", code_aus_push(ctx.pushes[-1]) not in seite_text.split("<h2>Code")[0])
r = sm.seite("schmiede/ansehen?name=mehrwertsteuer&t=" + token, None, ctx, False)
pruef("Ansicht: Abfrage im Pfad", r and r[0] == 200)
r = sm.seite("/schmiede/ansehen?name=mehrwertsteuer&t=" + token, {"_methode": "GET"}, ctx, False)
pruef("Ansicht: Abfrage im Pfad, abfrage mit anderen Schlüsseln", r and r[0] == 200)
r = sm.seite("/schmiede/ansehen", "name=mehrwertsteuer&t=" + token, ctx, False)
pruef("Ansicht: abfrage als Text", r and r[0] == 200)
r = sm.seite("/schmiede/ansehen", {"name": "mehrwertsteuer", "t": "falsch"}, ctx, True)
pruef("Ansicht: falsches Token 404 (zählt als Fehlversuch)", r and r[0] == 404)
pruef("Ansicht: ohne Token 404", sm.seite("/schmiede/ansehen", {"name": "mehrwertsteuer"}, ctx, True)[0] == 404)
_jetzt_alt = ctx._jetzt
ctx._jetzt = (ctx.jetzt()) + sm.ANSEHEN_S + 60
pruef("Ansicht: nach 7 Tagen abgelaufen (404)", sm.seite("/schmiede/ansehen", {"name": "mehrwertsteuer", "t": token}, ctx,
                                                       True)[0] == 404)
ctx._jetzt = _jetzt_alt
pruef("Ansicht: Kopfzeilen CSP, X-Frame-Options, Referrer-Policy", {k for k, _ in sm.SEITE_KOPFZEILEN} >= {
    "Content-Security-Policy", "X-Frame-Options", "Referrer-Policy", "Cache-Control"}
      and "default-src 'none'" in dict(sm.SEITE_KOPFZEILEN)["Content-Security-Policy"])
pruef("Ansicht: fremder Pfad None", sm.seite("/runde/abc", {}, ctx, True) is None)
os.environ["JARVIS_SCHMIEDE"] = "aus"
pruef("Ansicht: ausgeschaltet antwortet die Seite nicht (auch mit gültigem Token)",
      sm.seite("/schmiede/ansehen", {"name": "mehrwertsteuer", "t": token}, ctx, True) is None)
os.environ["JARVIS_SCHMIEDE"] = "an"

# ================================================================================== Teil 1: Schnittstelle
pruef("Schnittstelle: NAME, RECHTE, TAKT_S", sm.NAME == "schmiede" and sm.RECHTE == "familie" and sm.TAKT_S is None)
pruef("Schema-Aktionen = AKTIONEN", sm.WERKZEUG["schema"]["properties"]["aktion"]["enum"] == list(sm.AKTIONEN))
param, standard, lesend = sm.FREMDTEXT["nur_lesen"]
pruef("Fremdtext: Standardaktion wie im Modul, Ziele nicht lesend", param == "aktion" and standard == "liste"
      and not set(lesend) & set(sm.NUR_HAUPT) and set(lesend) <= set(sm.AKTIONEN))
pruef("Fremdtext: zeigen als Quelle", sm.FREMDTEXT["quelle_aktionen"][2] == ["zeigen"])
pruef("Werkzeugbeschreibung deutsch", sm.WERKZEUG is sm.WERKZEUG_DE and "abgeschottet" in sm.WERKZEUG["beschreibung"]
      and "denk dir nie einen aus" in sm.WERKZEUG["beschreibung"])
pruef("LAUTSPRECHER_PRIVAT: leer (frozenset), nur Aktionen aus AKTIONEN",
      isinstance(sm.LAUTSPRECHER_PRIVAT, frozenset) and sm.LAUTSPRECHER_PRIVAT == frozenset()
      and sm.LAUTSPRECHER_PRIVAT <= set(sm.AKTIONEN))
import superhirn  # noqa: E402
pruef("superhirn.nur_lesend: liste/zeigen/nutzen und ohne aktion lesend",
      all(superhirn.nur_lesend(sm, x) for x in ({}, {"aktion": "liste"}, {"aktion": "zeigen"}, {"aktion": "nutzen"})))
pruef("superhirn.nur_lesend: vorschlag/freigeben/verwerfen nicht",
      not any(superhirn.nur_lesend(sm, {"aktion": x}) for x in ("vorschlag", "freigeben", "verwerfen", "Liste")))
pruef("superhirn.runden: Schmiede hat keine Runde", "schmiede" not in superhirn.runden(
    lambda _: ctx, lambda *x: None, jetzt=T0 + 10 ** 6, faden=False))
# Einträge für die Fremdtext-Sperre in die echte Fremdtext-Logik (nur im Speicher dieses Tests, die Datei bleibt)
import fremdtext as ft  # noqa: E402
_alt = (ft.ZIELE, ft.QUELLEN, dict(ft.NUR_LESEN), dict(ft.QUELLE_AKTIONEN))
ft.ZIELE = ft.ZIELE | {"schmiede"}
ft.QUELLEN = ft.QUELLEN | {"schmiede"}
ft.NUR_LESEN["schmiede"] = ("aktion", "liste", frozenset({"liste", "zeigen", "nutzen"}))
ft.QUELLE_AKTIONEN["schmiede"] = ("aktion", "liste", frozenset({"zeigen"}))
pruef("fremdtext: vorschlag/freigeben/verwerfen gesperrt, liste/zeigen/nutzen frei",
      all(ft.ist_ziel("mcp__jarvis__schmiede", {"aktion": x}) for x in ("vorschlag", "freigeben", "verwerfen"))
      and not any(ft.ist_ziel("mcp__jarvis__schmiede", {"aktion": x}) for x in ("liste", "zeigen", "nutzen"))
      and not ft.ist_ziel("schmiede", {}) and ft.ist_ziel("schmiede"))
pruef("fremdtext: nur zeigen ist Quelle", ft.ist_quelle("schmiede", {"aktion": "zeigen"})
      and not any(ft.ist_quelle("schmiede", {"aktion": x}) for x in ("liste", "nutzen", "vorschlag")))
ft.ZIELE, ft.QUELLEN = _alt[0], _alt[1]
ft.NUR_LESEN.clear()
ft.NUR_LESEN.update(_alt[2])
ft.QUELLE_AKTIONEN.clear()
ft.QUELLE_AKTIONEN.update(_alt[3])

# ================================================================================== Teil 1: Englisch
DEUTSCH = re.compile(r"[äöüÄÖÜß„]|\b(ist|nicht|Bitte|und|der|die|das|mit|noch|schon|gibt|wurde|Werkzeug|Werkzeuge|"
                     r"Werkzeugschmiede|Eingabe|Zeile|Fehler|bestanden|Entwurf|Versuche|Ergebnis|Laden|erhalten|"
                     r"entwurf|gescheitert|gesperrt|aktiv|keine|fehlt)\b")


def deutsch(text):
    t = DEUTSCH.search(str(text))
    return t.group(0) if t else None


EN = []      # (Name, Text): alles, was im englischen Block ein Mensch oder das Modell liest


def en(name, text):
    EN.append((name, text))
    return text


CODE_EN = '''def ausfuehren(eingabe):
    """Sales tax: net -> gross or gross -> net."""
    amount = eingabe.get("amount")
    rate = eingabe.get("rate", 19)
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0:
        return {"fehler": "Please give an amount of 0 or more."}
    if eingabe.get("direction", "net") == "gross":
        net = amount / (1 + rate / 100)
    else:
        net = amount
    tax = net * rate / 100
    return {"net": round(net, 2), "tax": round(tax, 2), "gross": round(net + tax, 2)}
'''
TESTS_EN = [{"eingabe": {"amount": 100}, "erwartet": {"net": 100, "tax": 19, "gross": 119}},
            {"eingabe": {"amount": 119, "direction": "gross"}, "erwartet": {"net": 100, "tax": 19}},
            {"eingabe": {"amount": 50, "rate": 7}, "erwartet": {"tax": 3.5, "gross": 53.5}},
            {"eingabe": {"amount": "x"}, "erwartet": {"fehler": "Please give an amount of 0 or more."}}]
SCHEMA_EN = {"type": "object", "properties": {"amount": {"type": "number", "description": "Amount in euros"},
                                              "rate": {"type": "number"}, "direction": {"type": "string"}},
             "required": ["amount"]}


def antwort_en(code=CODE_EN):
    return json.dumps({"name": "sales_tax", "zweck": "Calculates net, tax and gross for an amount.",
                       "eingabe_schema": SCHEMA_EN, "code": code, "tests": TESTS_EN})


GUT_EN, FALSCH_EN = antwort_en(), antwort_en(CODE_EN.replace('get("rate", 19)', 'get("rate", 16)'))

sm.setze_sprache("en")
pruef("EN: WERKZEUG und SYSTEM umgestellt", sm.WERKZEUG is sm.WERKZEUG_EN and sm.SYSTEM is sm.SYSTEM_EN)


def ohne_beschreibung(x):
    if isinstance(x, dict):
        return {k: ohne_beschreibung(v) for k, v in x.items() if k != "description"}
    return x


pruef("EN: Schema gleich bis auf die Beschreibungen (Aktionen, Schlüssel)",
      ohne_beschreibung(sm.WERKZEUG_EN["schema"]) == ohne_beschreibung(sm.WERKZEUG_DE["schema"]))
en("WERKZEUG beschreibung", sm.WERKZEUG["beschreibung"])
for k, v in sm.WERKZEUG["schema"]["properties"].items():
    if "description" in v:
        en("WERKZEUG %s" % k, v["description"])
pruef("EN: WERKZEUG englisch", "isolation" in sm.WERKZEUG["beschreibung"] and "never make one up"
      in sm.WERKZEUG["beschreibung"] and "main person" in sm.WERKZEUG["beschreibung"])
en("SYSTEM", sm.SYSTEM)
pruef("EN: Auftrag ans Modell verlangt Englisch", "one English sentence" in sm.SYSTEM and "in English" in sm.SYSTEM)

os.environ["JARVIS_SCHMIEDE"] = "0"
ctx = kontext(antworten={"schmiede": [GUT_EN]})
r = en("aus", m(a(ctx, "alex", aktion="liste")))
pruef("EN: ausgeschaltet", "tool forge is switched off" in r and "JARVIS_SCHMIEDE=on" in r and "Docker" in r, r)
os.environ["JARVIS_SCHMIEDE"] = "on"

pruef("EN: liste leer", en("liste leer", m(a(ctx, "alex", aktion="liste"))) == "No tools of my own yet.")
pruef("EN: Gast", "only for the family" in en("gast", m(a(ctx, "gast1", aktion="liste"))))
pruef("EN: nur Hauptperson", "Only Alex may" in en("nur haupt", m(a(ctx, "kim", aktion="vorschlag",
                                                                     bedarf="Sales tax please, quickly"))))
en("aktion", m(a(ctx, "alex", aktion="bauen")))
en("bedarf kurz", m(a(ctx, "alex", aktion="vorschlag", bedarf="x")))
en("name", m(a(ctx, "alex", aktion="zeigen", name="../x")))
LAEUFE[:] = []
r = a(ctx, "alex", aktion="vorschlag", bedarf="Calculate sales tax, net and gross",
      beispiele=["What is 119 euros gross in net?"])
pruef("EN: vorschlag", "Draft “sales_tax” is ready" in en("vorschlag", m(r)) and "4 of 4 tests passed" in m(r)
      and "Alex has received a push" in m(r) and not re.search(r"\d{4}\b(?! tests)", m(r).replace("4 of 4", "")), m(r))
pruef("EN: Auftrag und System englisch", ctx.gedacht[-1]["auftrag"].startswith("Build a tool for this need:")
      and "Examples of how" in ctx.gedacht[-1]["auftrag"] and ctx.gedacht[-1]["system"] == sm.SYSTEM_EN)
en("auftrag", ctx.gedacht[-1]["auftrag"].replace("What is 119 euros gross in net?", ""))
push = ctx.pushes[-1]
en("push titel", push["titel"])
en("push text", push["text"])
code_wort = code_aus_push(push)
pruef("EN: Push", push["titel"] == "Jarvis: new tool “sales_tax”" and "Tests: 4 of 4 passed." in push["text"]
      and "approve tool sales_tax, code %s" % code_wort in push["text"] and "discard tool sales_tax" in push["text"],
      push)
r = en("liste haupt", m(a(ctx, "alex", aktion="liste")))
pruef("EN: liste mit Entwurf (Status übersetzt, gespeichert bleibt entwurf)", "sales_tax [draft, tests 4 of 4]" in r
      and meta(ctx, "sales_tax")["status"] == "entwurf" and a(ctx, "alex", aktion="liste")["werkzeuge"][0]["status"]
      == "entwurf", r)
r = a(ctx, "alex", aktion="zeigen", name="sales_tax")
pruef("EN: zeigen", r["meldung"].startswith("Tool “sales_tax” (draft): Calculates") and "Tests: 4 of 4 passed." in
      r["meldung"] and r["status"] == "entwurf", r["meldung"][:200])
en("zeigen", r["meldung"].replace(CODE_EN, ""))
r = sm.seite("/schmiede/ansehen", {"name": "sales_tax", "t": meta(ctx, "sales_tax")["ansehen_token"]}, ctx, True)
seite_en = r[2].decode("utf-8")
pruef("EN: Seite", r[0] == 200 and 'lang="en"' in seite_en and "<h1>Tool “sales_tax”</h1>" in seite_en
      and "Need:" in seite_en and "Input:" in seite_en and "To approve, say “approve tool sales_tax" in seite_en
      and "4 of 4 passed" in seite_en and ">draft<" not in seite_en and "draft" in seite_en, seite_en[:300])
en("seite", re.sub(r"<pre>.*</pre>", "", seite_en, flags=re.S))
en("seite 404", sm.seite("/schmiede/ansehen", {"name": "sales_tax", "t": "x"}, ctx, True)[2].decode())
en("freigeben ohne code", m(a(ctx, "alex", aktion="freigeben", name="sales_tax")))
r = en("freigeben falsch", m(a(ctx, "alex", aktion="freigeben", name="sales_tax",
                                 freigabe_code="%04d" % ((int(code_wort) + 1) % 10000))))
pruef("EN: falscher Code", r == "The code is wrong (2 attempts left).", r)
r = en("freigeben", m(a(ctx, "alex", aktion="freigeben", name="sales_tax", freigabe_code=code_wort)))
pruef("EN: freigegeben", r.startswith("“sales_tax” is approved and now belongs to my tools") and "amount (number)" in r,
      r)
en("schon aktiv", m(a(ctx, "alex", aktion="freigeben", name="sales_tax", freigabe_code=code_wort)))
r = a(ctx, "kim", aktion="nutzen", name="sales_tax", eingabe={"amount": 200})
pruef("EN: nutzen", r.get("ergebnis") == {"net": 200, "tax": 38, "gross": 238} and m(r).startswith(
    "Result of “sales_tax”:"), r)
en("nutzen", m(r))
pruef("EN: Pflichtfeld", en("pflicht", m(a(ctx, "kim", aktion="nutzen", name="sales_tax", eingabe={})))
      .startswith("The field “amount” is missing. Input for “sales_tax”:"))
pruef("EN: Typ", "“amount” must be a number." in en("typ", m(a(ctx, "kim", aktion="nutzen", name="sales_tax",
                                                                eingabe={"amount": "two"}))))
en("kein objekt", m(a(ctx, "kim", aktion="nutzen", name="sales_tax", eingabe="no json")))
en("kein objekt 2", sm.eingabe_pruefen(SCHEMA_EN, []))
en("unbekannt nutzen", m(a(ctx, "kim", aktion="nutzen", name="gibtsnicht")))
en("liste familie", m(a(ctx, "kim", aktion="liste")))
_alt = sm.NUTZUNGEN_STUNDE
sm.NUTZUNGEN_STUNDE = len(sm._nutzungen)
pruef("EN: Stundenlimit", "runs in the last hour" in en("stunde", m(a(ctx, "kim", aktion="nutzen", name="sales_tax",
                                                                      eingabe={"amount": 1}))))
sm.NUTZUNGEN_STUNDE = _alt
with open(os.path.join(ctx.daten, "schmiede", "sales_tax", "code.py"), "a", encoding="utf-8") as f:
    f.write("\n# later\n")
pruef("EN: veränderter Code", "differs from the approved version" in en("veraendert", m(a(
    ctx, "kim", aktion="nutzen", name="sales_tax", eingabe={"amount": 1}))))
r = en("verwerfen", m(a(ctx, "alex", aktion="verwerfen", name="sales_tax")))
pruef("EN: verwerfen", r == "“sales_tax” is discarded and no longer runs.", r)
en("verwerfen unbekannt", m(a(ctx, "alex", aktion="verwerfen", name="gibtsnicht")))

# Prüftexte, Läufer und Auswertung auf Englisch
for name in ("import os", "from calendar import sys", "relativer Import", "open", "getattr mit Variable",
             "Modul zuweisen", "calendar.sys", "statistics.itemgetter", "format an Variable", "format mit Index",
             "Zeichenkette mit __", "Generator-Ausdruck", "yield in Funktion", "ohne ausfuehren", "async ausfuehren",
             "ausfuehren ohne Parameter", "Syntaxfehler", "zu lang", "zu viele Zeichen", "leer"):
    p = sm.code_pruefen(FALL[name])
    pruef("EN: statisch abgelehnt: %s" % name, bool(p), FALL[name][:60])
    for t in p:
        en("code_pruefen %s" % name, t)
pruef("EN: Problemtext mit Zeile", "Line 1: Import “os” is not allowed." in sm.code_pruefen(FALL["import os"]))
pruef("EN: Generator-Ausdruck benannt", any("a generator expression is not allowed" in t
                                            for t in sm.code_pruefen(FALL["Generator-Ausdruck"])))
_, p = sm.entwurf_pruefen({"name": "Bad-Name", "zweck": "", "eingabe_schema": [], "code": CODE_EN,
                           "tests": [{"eingabe": {}, "erwartet": {}}] * 13})
for t in p:
    en("entwurf_pruefen", t)
pruef("EN: entwurf_pruefen", any("does not match" in t for t in p) and any("At least" in t for t in p)
      and any("At most" in t for t in p), p)
for d in ("no dict", {"name": "abc", "tests": TESTS_EN}, {"name": "abc", "code": CODE_EN}):
    for t in sm.entwurf_pruefen(d)[1]:
        en("entwurf_pruefen 2", t)
for r in ({"rc": 125, "aus": b"", "err": b"", "dauer": 0.3}, {"rc": 137, "aus": b"", "err": b"", "dauer": 2},
          {"rc": 124, "aus": b"", "err": b"", "dauer": 21}, {"rc": 1, "aus": b"", "err": b"", "dauer": 1}):
    en("auswerten", sm.auswerten(r, 20)["fehler"])
pruef("EN: auswerten", sm.auswerten({"rc": 124, "aus": b"", "err": b"", "dauer": 21}, 20)["fehler"]
      == "Time limit of 20 s exceeded, the run was stopped.")
r = lokale_sandbox("def ausfuehren(e):\n    import socket\n    return {}\n", {"modus": "nutzen", "eingabe": {}}, 20)
pruef("EN: Läufer Import", "Import not allowed: socket" in en("laeufer import", r.get("fehler", "")), r)
r = lokale_sandbox("def ausfuehren(e):\n    x = 1\n    return {'x': 1 / (x - 1)}\n", {"modus": "nutzen", "eingabe": {}},
                   20)
pruef("EN: Läufer Zeile", "(line 3)" in en("laeufer zeile", r.get("fehler", "")), r)
en("laeufer dict", lokale_sandbox("def ausfuehren(e):\n    return [1]\n", {"modus": "nutzen", "eingabe": {}},
                                  20).get("fehler"))
en("laeufer json", lokale_sandbox("def ausfuehren(e):\n    return {'x': float('nan')}\n",
                                  {"modus": "nutzen", "eingabe": {}}, 20).get("fehler"))
en("laeufer laden", lokale_sandbox("def rechne(e):\n    return {}\n", {"modus": "nutzen", "eingabe": {}}, 20)
   .get("fehler"))
r = lokale_sandbox(SCHLEIFE_TEST, {"modus": "tests", "je_s": 1, "tests": [
    {"eingabe": {"n": 1}, "erwartet": {"n": 2}}, {"eingabe": {"n": 2}, "erwartet": {"n": 2}}]}, 20)
pruef("EN: Läufer Zeitlimit und Vergleich", "Time limit of 1 s per call" in r["einzeln"][1]["fehler"]
      and r["einzeln"][0]["fehler"].startswith("expected"), r)
en("laeufer zeitlimit", r["einzeln"][1]["fehler"])
en("laeufer erwartet", r["einzeln"][0]["fehler"])

# Reparatur, Scheitern, Sandbox und Denken kaputt auf Englisch
ctx = kontext(antworten={"schmiede": [FALSCH_EN, FALSCH_EN, FALSCH_EN]})
r = en("gescheitert", m(a(ctx, "alex", aktion="vorschlag", bedarf="Calculate sales tax, net and gross")))
pruef("EN: gescheitert", r.startswith("I did not get the tool “sales_tax” working after 3 attempts: Test 1: expected"),
      r)
en("reparatur", ctx.gedacht[1]["auftrag"].split("Draft:")[0] + ctx.gedacht[1]["auftrag"].split("Problems:")[1]
   .replace(json.dumps(TESTS_EN[0]["erwartet"]), ""))
pruef("EN: Reparatur-Auftrag", ctx.gedacht[1]["auftrag"].startswith("Your last draft did not pass the check.")
      and "Problems:\n- Test 1: expected" in ctx.gedacht[1]["auftrag"])
en("push gescheitert", ctx.pushes[-1]["titel"] + "\n" + ctx.pushes[-1]["text"])
pruef("EN: Push gescheitert", ctx.pushes[-1]["titel"] == "Jarvis: tool “sales_tax” not finished")
en("nicht freigebbar", m(a(ctx, "alex", aktion="freigeben", name="sales_tax", freigabe_code="1")))
en("zeigen gescheitert", m(a(ctx, "alex", aktion="zeigen", name="sales_tax")).replace(
    CODE_EN.replace('get("rate", 19)', 'get("rate", 16)'), ""))
ctx = kontext(antworten={"schmiede": ['{"name": "x"}', "no json", '{"tests": []}']})
en("nichts brauchbar", m(a(ctx, "alex", aktion="vorschlag", bedarf="Build something quite unclear")))
ctx = DenkenKaputt(jetzt=T0)
KONTEXTE.append(ctx)
en("denken kaputt", m(a(ctx, "alex", aktion="vorschlag", bedarf="Calculate sales tax, please")))
sm.SANDBOX_ERSATZ = lambda code, auftrag, zl: sm.auswerten({"rc": 125, "aus": b"", "err": b"Unable to find image",
                                                            "dauer": 0.2}, zl)
ctx = kontext(antworten={"schmiede": [GUT_EN]})
r = en("sandbox kaputt", m(a(ctx, "alex", aktion="vorschlag", bedarf="Calculate sales tax, net and gross")))
pruef("EN: Sandbox kaputt", r.startswith("The sandbox is not running right now (The sandbox could not be started:")
      and not sm._alle(ctx), r)
sm.SANDBOX_ERSATZ = alt_ersatz

# Grenzen und Sperre auf Englisch
ctx = kontext(antworten={"schmiede": [GUT_EN]})
a(ctx, "alex", aktion="vorschlag", bedarf="Calculate sales tax, net and gross")
code_wort = code_aus_push(ctx.pushes[-1])
for i in range(sm.FALSCHE_CODES):
    r = m(a(ctx, "alex", aktion="freigeben", name="sales_tax", freigabe_code="%04d" % ((int(code_wort) + 1) % 10000)))
en("gesperrt", r)
en("gesperrt 2", m(a(ctx, "alex", aktion="freigeben", name="sales_tax", freigabe_code=code_wort)))
for i in range(sm.MAX_AKTIV):
    aktiv_anlegen(ctx, "werkzeug_%02d" % i)
en("20 aktiv", m(a(ctx, "alex", aktion="vorschlag", bedarf="Yet another tool, please")))
ctx = kontext(antworten={"schmiede": [GUT_EN]})
sm._schreiben(os.path.join(sm._ordner(ctx), "zaehler.json"), json.dumps(
    {"tag": time.strftime("%Y-%m-%d", time.localtime(T0)), "vorschlaege": sm.MAX_VORSCHLAEGE_TAG}))
en("tageslimit", m(a(ctx, "alex", aktion="vorschlag", bedarf="Calculate sales tax, please")))

sm.IM_HINTERGRUND = True
ctx = kontext(antworten={"schmiede": lambda auftrag, system, stufe: (time.sleep(0.3), GUT_EN)[1]})
r = en("hintergrund", m(a(ctx, "alex", aktion="vorschlag", bedarf="Calculate sales tax, net and gross")))
en("hintergrund 2", m(a(ctx, "alex", aktion="vorschlag", bedarf="Another tool at the same time")))
ende = time.time() + 30
while not ctx.pushes and time.time() < ende:
    time.sleep(0.1)
time.sleep(0.2)
pruef("EN: Hintergrund", r.startswith("I am building the tool now") and len(ctx.pushes) == 1
      and ctx.pushes[0]["titel"] == "Jarvis: new tool “sales_tax”", (r, ctx.pushes))
sm.IM_HINTERGRUND = False

deutsch_reste = [(n, deutsch(t), str(t)[:120]) for n, t in EN if deutsch(t)]
pruef("EN: kein deutscher Rest in %d geprüften Texten" % len(EN), not deutsch_reste, deutsch_reste[:5])
pruef("EN: Prüfmuster greift (Gegenprobe)", deutsch("Der Code stimmt nicht.") and deutsch("„x“")
      and not deutsch("The code is wrong (2 attempts left)."))
try:
    sm.setze_sprache("fr")
    pruef("setze_sprache: unbekannte Sprache abgelehnt", False)
except ValueError:
    pruef("setze_sprache: unbekannte Sprache abgelehnt, Sprache bleibt", sm.SPRACHE == "en")
sm.setze_sprache("de")
pruef("zurück auf Deutsch", sm.SPRACHE == "de" and sm.WERKZEUG is sm.WERKZEUG_DE and sm.SYSTEM is sm.SYSTEM_DE
      and m(a(kontext(), "alex", aktion="liste")) == "Noch keine eigenen Werkzeuge.")

# ================================================================================== Teil 2: echte Sandbox
PROBE = r'''import json, os, socket, threading, time
r = {"uid": os.getuid(), "gid": os.getgid()}
r["capeff"] = [z.split()[1] for z in open("/proc/self/status") if z.startswith("CapEff")][0]
r["routen_v4"] = len(open("/proc/net/route").read().strip().splitlines()) - 1
def verbinden(adresse, familie):
    try:
        s = socket.socket(familie, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(adresse)
        return "verbunden"
    except OSError as e:
        return "%s:%s" % (type(e).__name__, e.errno)
r["lan"] = verbinden(("192.0.2.1", 80), socket.AF_INET)   # Dokumentationsadresse; ohne Netz ist jede unerreichbar
r["internet"] = verbinden(("1.1.1.1", 53), socket.AF_INET)
r["internet_v6"] = verbinden(("2606:4700:4700::1111", 53), socket.AF_INET6)
try:
    socket.getaddrinfo("example.com", 80)
    r["dns"] = "aufgeloest"
except OSError as e:
    r["dns"] = type(e).__name__
def schreiben(pfad, groesse=10):
    try:
        with open(pfad, "wb") as f:
            f.write(b"x" * groesse)
        return "geschrieben"
    except OSError as e:
        return "%s:%s" % (type(e).__name__, e.errno)
r["werkzeug"] = schreiben("/werkzeug/neu.txt")
r["wurzel"] = schreiben("/usr/local/neu.txt")
r["etc"] = schreiben("/etc/neu.txt")
r["tmp_klein"] = schreiben("/tmp/klein.bin", 4 * 1024 * 1024)
r["tmp_gross"] = schreiben("/tmp/gross.bin", 20 * 1024 * 1024)
faeden = []
try:
    for i in range(200):
        t = threading.Thread(target=time.sleep, args=(3,))
        t.start()
        faeden.append(t)
    r["faeden"] = len(faeden)
except RuntimeError:
    r["faeden"] = len(faeden)
print(json.dumps(r))
'''
SPEICHER = "x = bytearray(400 * 1024 * 1024)\nprint('400 MB bekommen')\n"
SCHLEIFE = '''def ausfuehren(eingabe):
    while True:
        try:
            while True:
                pass
        except BaseException:
            pass
'''


def container_reste():
    p = subprocess.run(sm.DOCKER + ["ps", "-a", "--filter", "name=jarvis-schmiede-", "-q"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
    return p.stdout.decode().split()


def probe_lauf(skript, zeitlimit=20):
    ordner = tempfile.mkdtemp(prefix="jarvis-schmiede-probe-")
    try:
        os.chmod(ordner, 0o755)
        with open(os.path.join(ordner, "probe.py"), "w") as f:
            f.write(skript)
        os.chmod(os.path.join(ordner, "probe.py"), 0o644)
        return sm.container_lauf(ordner, b"", zeitlimit, datei="probe.py", argumente=())
    finally:
        shutil.rmtree(ordner, ignore_errors=True)


def docker_geht():
    """Antwortet der Docker-Dienst über DOCKER? -> (ja/nein, Grund)."""
    try:
        p = subprocess.run(sm.DOCKER + ["version", "--format", "{{.Server.Version}}"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except (OSError, subprocess.SubprocessError) as x:
        return False, "%s: %s" % (type(x).__name__, x)
    if p.returncode != 0:
        return False, "Rückgabe %s: %s" % (p.returncode, p.stderr.decode("utf-8", "replace").strip()[-200:])
    return True, ""


if os.environ.get("JARVIS_SCHMIEDE_DOCKER_TEST") != "1":
    print("SKIP echte Sandbox (Teil 2): JARVIS_SCHMIEDE_DOCKER_TEST=1 ist nicht gesetzt, Beleg fehlt")
else:
    geht, grund = docker_geht()
    if not geht:
        print("SKIP echte Sandbox (Teil 2): Docker-Befehl %s funktioniert nicht (%s), Beleg fehlt" % (
            " ".join(sm.DOCKER), grund))
    else:
        sm.SANDBOX_ERSATZ = None
        vorher_tmp = set(glob.glob(os.path.join(tempfile.gettempdir(), "jarvis-schmiede-*")))
        bild = subprocess.run(sm.DOCKER + ["image", "inspect", sm.IMAGE, "--format", "{{.Id}}"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        pruef("echt: Image %s liegt lokal (sonst: docker pull %s)" % (sm.IMAGE, sm.IMAGE), bild.returncode == 0,
              bild.stderr[-200:])

        r = probe_lauf(PROBE)
        try:
            pr = json.loads(r["aus"].decode().strip().splitlines()[-1])
        except (ValueError, IndexError):
            pr = {}
        print("BELEG Probe:", json.dumps(pr, ensure_ascii=False), "(%.1f s)" % r["dauer"])
        pruef("echt: läuft als 65534 ohne Capabilities", pr.get("uid") == 65534 and pr.get("gid") == 65534
              and pr.get("capeff") == "0000000000000000", pr)
        pruef("echt: Netz zu (keine Route, LAN und Internet unerreichbar)", pr.get("routen_v4") == 0
              and pr.get("lan", "").startswith("OSError") and pr.get("internet", "").startswith("OSError")
              and pr.get("internet_v6", "").startswith("OSError") and pr.get("dns") == "gaierror", pr)
        pruef("echt: Dateisystem read-only (Code, /usr, /etc)", pr.get("werkzeug") == "OSError:30"
              and pr.get("wurzel") == "OSError:30" and pr.get("etc") == "OSError:30", pr)
        pruef("echt: /tmp nur 16 MB", pr.get("tmp_klein") == "geschrieben" and pr.get("tmp_gross") == "OSError:28", pr)
        pruef("echt: Prozessgrenze (ulimit nproc 64)", 0 < pr.get("faeden", 999) < 70, pr.get("faeden"))

        r = probe_lauf(SPEICHER)
        print("BELEG Speicher: rc=%s, %.1f s, Ausgabe=%r" % (r["rc"], r["dauer"], r["aus"].decode()[:40]))
        pruef("echt: keine 400 MB (Speichergrenze 256 MB)", b"400 MB bekommen" not in r["aus"] and r["rc"] != 0, r["rc"])

        start = time.monotonic()
        r = sm.sandbox(SCHLEIFE, {"modus": "nutzen", "eingabe": {}, "je_s": 60}, sm.ZEITLIMIT_S)
        dauer = time.monotonic() - start
        print("BELEG Endlosschleife: %r nach %.1f s" % (r, dauer))
        pruef("echt: Endlosschleife nach dem Zeitlimit abgebrochen", r.get("ok") is False and r.get("zeitlimit") is True
              and sm.ZEITLIMIT_S <= dauer < sm.ZEITLIMIT_S + sm.NACHFRIST_S, (r, dauer))
        pruef("echt: kein Container übrig", container_reste() == [], container_reste())

        # Falls die Grenze im Container versagt: von außen nach zeitlimit + NACHFRIST_S per docker kill beenden.
        # Dafür die innere Grenze (timeout im Container) nur in diesem Test auf 120 s setzen.
        orig_befehl, orig_nachfrist = sm.sandbox_befehl, sm.NACHFRIST_S

        def ohne_innere_grenze(ordner, name, zeitlimit, datei="lauf.py", argumente=("/werkzeug/werkzeug.py",)):
            b = orig_befehl(ordner, name, zeitlimit, datei, argumente)
            b[b.index("timeout") + 3] = "120"
            return b
        sm.sandbox_befehl, sm.NACHFRIST_S = ohne_innere_grenze, 2
        start = time.monotonic()
        r = probe_lauf("import time\ntime.sleep(100)\n", zeitlimit=3)
        dauer = time.monotonic() - start
        sm.sandbox_befehl, sm.NACHFRIST_S = orig_befehl, orig_nachfrist
        for _ in range(10):
            if not container_reste():
                break
            time.sleep(0.5)
        print("BELEG Abbruch von außen: abgebrochen=%s rc=%s nach %.1f s" % (r["abgebrochen"], r["rc"], dauer))
        pruef("echt: hängender Container wird von außen beendet", r["abgebrochen"] is True and 5 <= dauer < 30
              and container_reste() == [], (r["abgebrochen"], dauer, container_reste()))
        pruef("echt: auswerten meldet das als Zeitlimit", sm.auswerten(r, 3).get("zeitlimit") is True)

        ctx = kontext(antworten={"schmiede": [GUT]})
        start = time.monotonic()
        r = a(ctx, "alex", aktion="vorschlag", bedarf="Mehrwertsteuer rechnen, netto und brutto")
        print("BELEG vorschlag echt: %s (%.1f s)" % (m(r), time.monotonic() - start))
        pruef("echt: Tests im Container grün", "4 von 4" in m(r), m(r))
        code_wort = code_aus_push(ctx.pushes[-1]) if ctx.pushes else None
        r = a(ctx, "alex", aktion="freigeben", name="mehrwertsteuer", freigabe_code=code_wort)
        pruef("echt: freigegeben", "ist freigegeben" in m(r), m(r))
        r = a(ctx, "kim", aktion="nutzen", name="mehrwertsteuer", eingabe={"betrag": 119, "richtung": "brutto"})
        print("BELEG nutzen echt:", m(r))
        pruef("echt: nutzen im Container", (r.get("ergebnis") or {}).get("netto") == 100, r)
        r = sm.sandbox("def ausfuehren(e):\n    return {'x': open('/etc/hostname').read()}\n",
                       {"modus": "nutzen", "eingabe": {}, "je_s": 5}, sm.ZEITLIMIT_S)
        pruef("echt: eingeschränkte Builtins auch im Container", "NameError" in r.get("fehler", ""), r)
        pruef("echt: kein Container übrig (am Ende)", container_reste() == [], container_reste())
        nachher_tmp = set(glob.glob(os.path.join(tempfile.gettempdir(), "jarvis-schmiede-*")))
        pruef("echt: kein Laufverzeichnis übrig", nachher_tmp <= vorher_tmp, nachher_tmp - vorher_tmp)

for c in KONTEXTE:
    c.aufraeumen()
if _SCHALTER_VORHER is None:
    os.environ.pop("JARVIS_SCHMIEDE", None)
else:
    os.environ["JARVIS_SCHMIEDE"] = _SCHALTER_VORHER
pruef("Live-Daten unverändert", wache())
sys.exit(ergebnis("Werkzeugschmiede"))
