"""Werkzeugschmiede (seit 0.7, Superhirn): Fehlt Jarvis eine Fähigkeit, schreibt er sich ein kleines Python-Werkzeug,
testet es abgeschottet und legt es der Hauptperson zur Freigabe vor. Freigegeben gehört es dauerhaft zu Jarvis und
läuft bei jeder Nutzung wieder abgeschottet.

Einschalten: Standardmäßig ist die Schmiede AUS. Nur wenn in der Umgebung der Brücke JARVIS_SCHMIEDE den Wert "an"
(auch "on", "1", "true"; Groß-/Kleinschreibung egal) hat, arbeitet das Modul. Sonst antwortet jede Aktion (auch liste)
mit einem freundlichen Hinweis, runde() und seite() tun nichts, und es entsteht keine Datei. Die Schmiede braucht
Docker auf demselben Rechner wie die Brücke.

Docker-Befehl: JARVIS_SCHMIEDE_DOCKER (Standard "docker"; per shlex zerlegt, also geht auch "sudo docker" oder ein
voller Pfad mit sudo davor). Wer docker aufrufen darf (Gruppe docker oder eine sudo-Regel dafür), hat damit
root-gleiche Rechte auf dem Rechner. Das entscheidet man beim Einrichten; die Schmiede ändert daran nichts und ruft
docker nur mit dem festen Sandbox-Befehl unten auf.

Ablauf
  vorschlag (nur die Hauptperson): ctx.denken_json(stufe="normal", zweck="schmiede") liefert
      {name, zweck, eingabe_schema, code, tests: [{eingabe, erwartet}]}; code definiert def ausfuehren(eingabe) -> dict.
      Danach statische Prüfung (code_pruefen, ast), dann die Tests in der Sandbox. Scheitert eins von beiden, bekommt
      Claude die Probleme zurück, höchstens REPARATUREN Runden. Ergebnis ist ein Entwurf unter
      ctx.daten/schmiede/<name>/ (code.py, meta.json mit Status und Testergebnis) und ein Push an die Hauptperson mit
      einem vierstelligen Freigabe-Code. Läuft im Hintergrund (IM_HINTERGRUND), weil es ein bis drei Minuten dauern kann.
  freigeben (nur Hauptperson, name + freigabe_code aus dem Push): Entwurf wird aktiv. Den Code kennt das Gehirn nicht
      (er steht weder in der Antwort noch in einer Werkzeugausgabe), also kann es ein Werkzeug nicht selbst freigeben.
      Drei falsche Codes sperren den Entwurf.
  nutzen (Familie): führt ein aktives Werkzeug mit eingabe in der Sandbox aus. Vorher wird die Prüfsumme von code.py
      mit der bei der Freigabe verglichen: Ein nachträglich veränderter Code läuft nicht.
  liste, zeigen (Familie: nur aktive), verwerfen (nur Hauptperson).

Sicherheit (ehrlich): Die Grenze ist der Container, nicht die statische Prüfung.
  - Sandbox: docker run --rm -i --network none --read-only --tmpfs /tmp:size=16m --memory 256m --pids-limit 64
    --cap-drop ALL --security-opt no-new-privileges --user 65534:65534, Code read-only eingebunden, Eingabe als JSON
    auf stdin, Ausgabe JSON auf stdout, hartes Zeitlimit (timeout -s KILL im Container, docker kill von außen).
    Kein --cpus (manche Kernel, z. B. auf einigen NAS, können keine CFS-Bandbreite, der Container startete dann
    nicht); statt dessen --cpu-shares 256 (nur Gewichtung). Manche Kernel verwerfen --pids-limit mit einer Warnung,
    deshalb zusätzlich --ulimit nproc=64:64 (Prozesse des Nutzers 65534; läuft auf dem Wirt schon etwas als 65534,
    zählt es mit, dann bekommt die Sandbox entsprechend weniger Fäden).
  - Seccomp: Docker legt normalerweise ein Seccomp-Profil um jeden Container. Ohne Seccomp im Kernel (z. B. manche
    NAS) oder mit "seccomp-profile": "unconfined" im Docker-Dienst fehlt diese Schicht; dann schützt nur der Container
    selbst (Namensräume, Netz aus, read-only, keine Capabilities, Nutzer 65534, no-new-privileges, Grenzen) plus die
    statische Prüfung.
  - Die statische Prüfung (Import-Positivliste, verbotene Namen und Attribute) und die eingeschränkten Builtins im
    Läufer fangen Versehen und offensichtlichen Missbrauch ab. Vollständig ist so eine Prüfung in Python nie (über
    Zeichenketten zur Laufzeit lassen sich Attribute zusammensetzen); deshalb läuft jeder Code nur im Container.
  - Restrisiko: Ein Container ist keine VM. Ein Kernel-Ausbruch wäre eine Lücke im Kernel des Wirts.

Image: per Digest gepinnt (IMAGE), gestartet mit --pull never. Auf dem Wirt muss es vorher einmal mit genau diesem
Digest geholt werden (docker pull python@sha256:…, siehe IMAGE), sonst meldet die Schmiede einen Sandbox-Fehler. Gegen
ein Aufräumen ungenutzter Images (docker image prune -a) hilft ein eigenes Tag, z. B.
docker tag python@sha256:… jarvis-schmiede:sandbox.

Daten: ctx.daten/schmiede/<name>/code.py und meta.json (0600, Ordner 0700). Zum Lauf wird der Code in ein frisches
Verzeichnis unter /tmp kopiert (0755/0644, damit der Nutzer 65534 im Container ihn lesen kann; Code ist nicht geheim)
und danach gelöscht. Brücke und Docker-Dienst müssen dasselbe /tmp sehen (ein PrivateTmp= in der Dienst-Unit der Brücke
würde das brechen). Verworfene Werkzeuge wandern nach ctx.daten/schmiede/.verworfen/<name>-<zeit>/.

Sprache: Meldungen, Pushes, Ansichtsseite, Problemtexte, Werkzeugbeschreibung und die Aufträge an das Modell auf
Deutsch oder Englisch (setze_sprache(), wie gaeste.py). Aktionsnamen, JSON-Schlüssel und Statuswerte in meta.json
bleiben gleich.

Python 3.8, nur Standardbibliothek, Import ohne Nebenwirkungen (die Umgebung wird nur gelesen).
"""
import ast
import hashlib
import html
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import uuid

NAME = "schmiede"
RECHTE = "familie"            # nutzen, liste, zeigen auch für die Familie; vorschlag/freigeben/verwerfen prüft auftrag
TAKT_S = None                 # keine Runde im Hintergrund (runde() gibt es nur der Vollständigkeit halber)

AKTIONEN = ("liste", "nutzen", "zeigen", "vorschlag", "freigeben", "verwerfen")
NUR_HAUPT = ("vorschlag", "freigeben", "verwerfen")

# Schalter (seit 0.7 im Release): standardmäßig aus. Gelesen bei jedem Aufruf, nicht beim Import.
SCHALTER = "JARVIS_SCHMIEDE"
EIN_WERTE = ("an", "on", "1", "true")

NAME_MUSTER = re.compile(r"[a-z][a-z0-9_]{2,30}")
MAX_AKTIV = 20
MAX_ENTWUERFE = 10
MAX_VORSCHLAEGE_TAG = 8        # je Vorschlag höchstens 1 + REPARATUREN Denkaufrufe (Kostenbremse neben denken.py)
REPARATUREN = 2
MAX_CODE_ZEICHEN = 16000
MAX_CODE_ZEILEN = 400
MIN_TESTS, MAX_TESTS = 2, 12
MAX_BEDARF = 2000
MAX_EINGABE_BYTES = 16000
MAX_ERGEBNIS_ZEICHEN = 6000     # was an das Gehirn zurückgeht
MAX_AUSGABE_BYTES = 256 * 1024  # mehr liest die Brücke vom Container nicht
NUTZUNGEN_STUNDE = 60
FALSCHE_CODES = 3

ZEITLIMIT_S = 20                # je Containerlauf (Tests oder eine Nutzung)
TEST_JE_S = 5                   # je Testfall im Läufer (SIGALRM)
NACHFRIST_S = 15                # Containerstart; danach docker kill von außen
# Per Digest gepinnt (Prüfbericht vor 0.7, K8): python:3.12-slim, Python 3.12.16. Fehlt das Image (aufgeräumt, anderes
# gezogen), startet die Sandbox nicht (--pull never) und meldet einen Sandbox-Fehler. Auf dem Wirt deshalb einmal genau
# dieses Image holen: docker pull python@sha256:<Digest unten>. Neuer Stand: Digest per
# "docker image inspect python:3.12-slim --format '{{json .RepoDigests}}'" hier eintragen und die Tests laufen lassen.
IMAGE = "python@sha256:e695ab189fa2d082b1c61c69a6b888a5adeca61ceeccad107b1ed2a125721a9e"


def _docker_befehl(wert):
    """JARVIS_SCHMIEDE_DOCKER -> Befehlsliste (shlex.split, damit "sudo docker" geht). Leer: ["docker"], kein sudo als
    Standard. Nicht zerlegbar (offenes Anführungszeichen): unverändert als ein Element; das scheitert dann beim Start
    als Sandbox-Fehler, statt still einen anderen Befehl zu nehmen."""
    wert = str(wert or "").strip()
    if not wert:
        return ["docker"]
    try:
        teile = shlex.split(wert)
    except ValueError:
        return [wert]
    return teile or ["docker"]


DOCKER = _docker_befehl(os.environ.get("JARVIS_SCHMIEDE_DOCKER"))
SANDBOX_TMP = None              # None: tempfile-Standard (/tmp, muss dasselbe sein, das der Docker-Dienst sieht)
SANDBOX_ERSATZ = None           # Tests: callable(code, auftrag, zeitlimit) -> dict wie sandbox()
IM_HINTERGRUND = True           # vorschlag baut in einem eigenen Thread; Tests setzen False
MARKE = "<<<SCHMIEDE>>>"

ERLAUBTE_IMPORTE = frozenset({"math", "statistics", "datetime", "re", "json", "decimal", "fractions", "itertools",
                              "collections", "string", "textwrap", "unicodedata", "calendar", "hashlib", "random"})
# Positivliste je Modul (Prüfbericht vor 0.7, M4): Nur diese Namen dürfen hinter "modul." oder in "from modul
# import ..." stehen. Erzeugt aus dir() unter Python 3.12 ohne Untermodule (json.codecs, re.functools ...) und ohne
# Unterstrich, dann von Hand gekürzt: nichts mit Dateien (json.dump/load, hashlib.file_digest), Ausgabe oder Umgebung
# (calendar.main/prcal/different_locale, re.DEBUG/purge), Formatierer (string.Formatter) oder Weitergereichtes
# (statistics.itemgetter/reduce ..., calendar.IntEnum). Ein Modul selbst darf nur direkt vor einem Punkt stehen: nicht
# zuweisen, übergeben oder an getattr geben (sonst j = json; j.codecs).
ERLAUBTE_NAMEN = {
    "math": frozenset("acos acosh asin asinh atan atan2 atanh cbrt ceil comb copysign cos cosh degrees dist e erf erfc "
                      "exp exp2 expm1 fabs factorial floor fmod frexp fsum gamma gcd hypot inf isclose isfinite isinf "
                      "isnan isqrt lcm ldexp lgamma log log10 log1p log2 modf nan nextafter perm pi pow prod radians "
                      "remainder sin sinh sqrt sumprod tan tanh tau trunc ulp".split()),
    "statistics": frozenset("LinearRegression NormalDist StatisticsError correlation covariance fmean geometric_mean "
                            "harmonic_mean linear_regression mean median median_grouped median_high median_low mode "
                            "multimode pstdev pvariance quantiles stdev variance".split()),
    "datetime": frozenset("MAXYEAR MINYEAR UTC date datetime time timedelta timezone tzinfo".split()),
    "re": frozenset("A ASCII DOTALL I IGNORECASE M MULTILINE Match NOFLAG Pattern RegexFlag S U UNICODE VERBOSE X "
                    "compile error escape findall finditer fullmatch match search split sub subn".split()),
    "json": frozenset("JSONDecodeError JSONDecoder JSONEncoder dumps loads".split()),
    "decimal": frozenset("BasicContext Clamped Context ConversionSyntax Decimal DecimalException DecimalTuple "
                         "DefaultContext DivisionByZero DivisionImpossible DivisionUndefined ExtendedContext "
                         "FloatOperation Inexact InvalidContext InvalidOperation MAX_EMAX MAX_PREC MIN_EMIN MIN_ETINY "
                         "Overflow ROUND_05UP ROUND_CEILING ROUND_DOWN ROUND_FLOOR ROUND_HALF_DOWN ROUND_HALF_EVEN "
                         "ROUND_HALF_UP ROUND_UP Rounded Subnormal Underflow getcontext localcontext".split()),
    "fractions": frozenset("Fraction".split()),
    "itertools": frozenset("accumulate batched chain combinations combinations_with_replacement compress count cycle "
                           "dropwhile filterfalse groupby islice pairwise permutations product repeat starmap "
                           "takewhile tee zip_longest".split()),
    "collections": frozenset("ChainMap Counter OrderedDict UserDict UserList UserString defaultdict deque "
                             "namedtuple".split()),
    "string": frozenset("Template ascii_letters ascii_lowercase ascii_uppercase capwords digits hexdigits octdigits "
                        "printable punctuation whitespace".split()),
    "textwrap": frozenset("TextWrapper dedent fill indent shorten wrap".split()),
    "unicodedata": frozenset("bidirectional category combining decimal decomposition digit east_asian_width "
                             "is_normalized lookup mirrored name normalize numeric unidata_version".split()),
    "calendar": frozenset("APRIL AUGUST Calendar DECEMBER Day EPOCH FEBRUARY FRIDAY IllegalMonthError "
                          "IllegalWeekdayError JANUARY JULY JUNE MARCH MAY MONDAY Month NOVEMBER OCTOBER SATURDAY "
                          "SEPTEMBER SUNDAY THURSDAY TUESDAY TextCalendar WEDNESDAY day_abbr day_name firstweekday "
                          "isleap leapdays mdays month_abbr month_name monthcalendar monthrange timegm weekday "
                          "weekheader".split()),
    "hashlib": frozenset("algorithms_available algorithms_guaranteed blake2b blake2s md5 new pbkdf2_hmac sha1 sha224 "
                         "sha256 sha384 sha3_224 sha3_256 sha3_384 sha3_512 sha512 shake_128 shake_256".split()),
    "random": frozenset("Random SystemRandom betavariate binomialvariate choice choices expovariate gammavariate "
                        "gauss getrandbits lognormvariate normalvariate paretovariate randbytes randint random "
                        "randrange sample seed shuffle triangular uniform vonmisesvariate weibullvariate".split()),
}
VERBOTENE_NAMEN = frozenset({"open", "eval", "exec", "compile", "__import__", "globals", "locals", "vars", "input",
                             "breakpoint", "exit", "quit", "help", "memoryview", "setattr", "delattr",
                             "__builtins__",
                             # seit der Nachprüfung vor 0.7 (M4): type() baut aus einem Code-Objekt eine neue
                             # Funktion mit eigenen globals (type(f)(code, {})); classmethod/staticmethod/property/
                             # super/vars reichen an interne Objekte
                             "type", "super", "classmethod", "staticmethod", "property", "object", "globals"})
# Attribute, über die man aus erlaubten Modulen an sys/os/builtins käme (calendar.sys, re.enum.bltns, fractions.operator
# ...), dazu Rahmen- und Code-Objekte. Alles mit führendem Unterstrich ist ohnehin verboten (random._os).
VERBOTENE_ATTRIBUTE = frozenset({"sys", "os", "builtins", "bltns", "subprocess", "importlib", "modules", "socket", "io",
                                 "shutil", "pathlib", "ctypes", "gc", "inspect", "types", "posix", "signal",
                                 "threading", "operator", "attrgetter", "methodcaller", "get_field", "vformat",
                                 "environ", "system", "popen", "fork", "enum", "copyreg", "weakref", "f_globals",
                                 "f_locals", "f_builtins", "f_back", "f_code", "gi_frame", "gi_code", "cr_frame",
                                 "ag_frame", "tb_frame", "tb_next", "co_code", "mro", "load_module", "exec_module",
                                 # seit dem Prüfbericht vor 0.7 (M4): Untermodule und Weitergereichtes
                                 "codecs", "functools", "abc", "numbers", "copyreg", "decoder", "encoder", "scanner",
                                 "sre_compile", "sre_parse", "warnings", "contextlib", "linecache", "tokenize",
                                 "format_map", "Formatter", "file_digest", "datetime_CAPI",
                                 # Nachprüfung vor 0.7 (M4): alle Code-, Rahmen-, Generator- und Koroutinen-Felder.
                                 # cr_code/ag_code/gi_code liefern das Code-Objekt, code.replace(co_names=…) baut daraus
                                 # beliebige Namenszugriffe. Deshalb jedes cr_*, ag_*, gi_*, co_*, f_*, tb_* und replace.
                                 "cr_code", "cr_await", "cr_running", "cr_origin", "cr_suspended",
                                 "ag_code", "ag_await", "ag_running", "gi_code", "gi_running",
                                 "gi_yieldfrom", "co_names", "co_consts", "co_varnames", "co_freevars", "co_cellvars",
                                 "co_filename", "co_argcount", "func_globals", "func_code", "__wrapped__",
                                 # Nachprüfung vor 0.7 (billige Härtung): AttributeError.obj (ab 3.10) liefert das
                                 # Objekt, an dem ein Zugriff scheiterte - ein konkreter Weg wurde nicht gefunden, aber
                                 # die Suche war nicht vollständig
                                 "obj"})
# Syntax, die ein Code-, Generator- oder Koroutinen-Objekt beschafft (M4): ganz verboten. Ohne sie kommt niemand an
# cr_code/ag_code/gi_code und damit an code.replace(co_names=…). Rechen- und Textwerkzeuge brauchen nichts davon.
# Lambda bleibt erlaubt (Sortierschlüssel): an sein Code-Objekt käme man nur über .__code__ (Dunder, schon gesperrt).
# Ein Generator-Ausdruck dagegen gibt über .gi_code ohne Unterstrich ein Code-Objekt her, deshalb verboten.
VERBOTENE_KNOTEN = (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith, ast.Yield, ast.YieldFrom,
                    ast.GeneratorExp)
try:                                 # ab Python 3.10: Klassenmuster können Attribute setzen (C(__globals__=g))
    VERBOTENE_KNOTEN += (ast.Match,)
except AttributeError:               # unter dem 3.8-Parser der Prüfung gibt es ast.Match nicht
    pass
KNOTEN_NAME = {"AsyncFunctionDef": "async def", "Await": "await", "AsyncFor": "async for", "AsyncWith": "async with",
               "Yield": "yield", "YieldFrom": "yield from", "Lambda": "lambda", "GeneratorExp": "ein Generator-Ausdruck",
               "Match": "match/case"}
KNOTEN_NAME_EN = dict(KNOTEN_NAME, GeneratorExp="a generator expression")
# Im Läufer fehlen diese Builtins ganz (zweite Linie hinter der statischen Prüfung)
LAEUFER_OHNE = ("open", "eval", "exec", "compile", "input", "breakpoint", "globals", "locals", "vars", "help", "exit",
                "quit", "memoryview", "setattr", "delattr", "__loader__", "__spec__",
                # Nachprüfung vor 0.7 (M4): type() baut aus einem Code-Objekt eine Funktion mit eigenen globals
                "type", "super", "classmethod", "staticmethod", "property", "object")

_sperre = threading.Lock()          # meta.json lesen, ändern, schreiben
_lauf_sperre = threading.Lock()     # höchstens ein Container zur Zeit
_bau_sperre = threading.Lock()      # höchstens ein Vorschlag zur Zeit
_nutzungen = []                     # Zeitpunkte der letzten Nutzungen (Stundenlimit, nur im Speicher)

# Kosten: stufe "normal" für Code mit Tests. "schnell" braucht erfahrungsgemäß mehr Reparaturrunden (und kostet dann
# mehr), "gruendlich" ist für Werkzeuge dieser Größe nicht nötig.
SYSTEM_DE = """Du baust für den Hausassistenten Jarvis kleine, abgeschottete Python-Werkzeuge. Sie laufen in einem \
Container ohne Netz und ohne Dateizugriff mit 20 Sekunden Zeit und rechnen nur: Eingabe als JSON-Objekt rein, Ergebnis \
als JSON-Objekt raus.

Antworte NUR mit einem JSON-Objekt:
{"name": "...", "zweck": "...", "eingabe_schema": {...}, "code": "...", "tests": [{"eingabe": {...}, "erwartet": {...}}]}

Regeln:
- name: 3 bis 31 Zeichen, nur a-z, 0-9 und _, beginnt mit einem Buchstaben, sprechend (z. B. mehrwertsteuer, tage_bis).
- zweck: ein deutscher Satz, was das Werkzeug kann (höchstens 200 Zeichen).
- eingabe_schema: JSON-Schema eines Objekts (type object, properties mit type und description, required). Feldnamen \
klein, ohne Umlaute.
- code: definiert def ausfuehren(eingabe): und gibt ein dict mit reinen JSON-Werten zurück (str, int, float, bool, \
None, list, dict). Bei ungültiger Eingabe ein dict mit "fehler" (deutscher Satz) zurückgeben statt zu werfen.
- Erlaubte Importe: math, statistics, datetime, re, json, decimal, fractions, itertools, collections, string, \
textwrap, unicodedata, calendar, hashlib, random. Nichts anderes.
- Verboten: open, eval, exec, compile, __import__, globals, locals, vars, setattr, delattr, type, super, object, \
classmethod, staticmethod, property, getattr mit nicht-konstantem oder unterstrichenem Namen, Attribute mit führendem \
Unterstrich, Zeichenketten mit doppeltem Unterstrich, print für Ergebnisse. Für Typprüfungen isinstance statt type.
- Kein async/await, kein yield, kein Generator-Ausdruck (…) und kein match/case. Schleifen, Listen-/Dict-Abstraktionen \
und lambda sind erlaubt.
- Syntax muss unter Python 3.8 gültig sein, der Code läuft unter Python 3.12. Höchstens 400 Zeilen.
- Keine Abhängigkeit von Uhrzeit oder Zufall in den Tests: Wird ein Datum gebraucht, kommt es als Eingabefeld (z. B. \
heute als JJJJ-MM-TT, optional).
- tests: 3 bis 8 Fälle mit von Hand nachgerechneten Werten. erwartet enthält nur die geprüften Schlüssel des \
Ergebnisses. Kommazahlen im Code und im Test auf 2 Stellen runden. Mindestens ein Test mit ungültiger Eingabe.
- Texte im Ergebnis deutsch mit echten Umlauten."""
SYSTEM_EN = """You build small, isolated Python tools for the home assistant Jarvis. They run in a container without \
network and without file access, with 20 seconds of time, and only calculate: input as a JSON object in, result as a \
JSON object out.

Answer ONLY with a JSON object (keep the keys exactly as written):
{"name": "...", "zweck": "...", "eingabe_schema": {...}, "code": "...", "tests": [{"eingabe": {...}, "erwartet": {...}}]}

Rules:
- name: 3 to 31 characters, only a-z, 0-9 and _, starts with a letter, descriptive (e.g. sales_tax, days_until).
- zweck: one English sentence saying what the tool can do (at most 200 characters).
- eingabe_schema: JSON schema of an object (type object, properties with type and description, required). Field \
names in lower case, ASCII letters only.
- code: defines def ausfuehren(eingabe): and returns a dict with plain JSON values (str, int, float, bool, None, list, \
dict). On invalid input return a dict with "fehler" (an English sentence) instead of raising.
- Allowed imports: math, statistics, datetime, re, json, decimal, fractions, itertools, collections, string, \
textwrap, unicodedata, calendar, hashlib, random. Nothing else.
- Forbidden: open, eval, exec, compile, __import__, globals, locals, vars, setattr, delattr, type, super, object, \
classmethod, staticmethod, property, getattr with a non-constant or underscored name, attributes with a leading \
underscore, strings with a double underscore, print for results. For type checks use isinstance instead of type.
- No async/await, no yield, no generator expression (…) and no match/case. Loops, list/dict comprehensions and lambda \
are allowed.
- The syntax must be valid under Python 3.8, the code runs under Python 3.12. At most 400 lines.
- No dependence on the time of day or on randomness in the tests: if a date is needed, it comes as an input field \
(e.g. today as YYYY-MM-DD, optional).
- tests: 3 to 8 cases with values worked out by hand. erwartet contains only the checked keys of the result. Round \
decimal numbers to 2 places in the code and in the test. At least one test with invalid input.
- Texts in the result in English."""
SYSTEM = SYSTEM_DE          # folgt setze_sprache()

# Sprache der Texte, die ein Mensch liest oder hört, und der Aufträge an das Modell (seit 0.7 im Release). Die Brücke
# setzt sie beim Start aus der Einrichtung, wie bei gaeste.py.
SPRACHE = "de"


def _t(de, en):
    return en if SPRACHE == "en" else de


STATUS_EN = {"entwurf": "draft", "gescheitert": "failed", "gesperrt": "locked", "aktiv": "active"}


def _status_wort(st):
    """Status nur für die Anzeige übersetzen; in meta.json und in Rückgabefeldern bleibt der Wert, wie er ist."""
    return STATUS_EN.get(st, st) if SPRACHE == "en" else st


def eingeschaltet():
    """JARVIS_SCHMIEDE=an (auch on, 1, true): sonst ist die Schmiede aus. Bei jedem Aufruf gelesen."""
    return str(os.environ.get(SCHALTER) or "").strip().lower() in EIN_WERTE


def _aus_meldung():
    return {"meldung": _t("Die Werkzeugschmiede ist aus. Sie lässt sich in der Einrichtung einschalten "
                          "(JARVIS_SCHMIEDE=an) und braucht Docker.",
                          "The tool forge is switched off. It can be switched on in the setup (JARVIS_SCHMIEDE=on) "
                          "and needs Docker.")}


# ---------------------------------------------------------------------------------------------- Personen, Dateien

def _rolle(ctx, person):
    return (ctx.personen().get(person) or {}).get("rolle")


def _haupt_name(ctx):
    return next((e.get("name") or k for k, e in ctx.personen().items() if e.get("rolle") == "haupt"),
                _t("die Hauptperson", "the main person"))


def _ordner(ctx):
    o = os.path.join(ctx.daten, "schmiede")
    os.makedirs(o, mode=0o700, exist_ok=True)
    return o


def _werkzeug_ordner(ctx, name):
    return os.path.join(_ordner(ctx), name)


def _schreiben(pfad, text, modus=0o600):
    neu = pfad + ".neu"
    fd = os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, modus)
    with open(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(neu, modus)
    os.replace(neu, pfad)


def _meta_laden(ctx, name):
    if not NAME_MUSTER.fullmatch(str(name or "")):
        return None
    try:
        with open(os.path.join(_werkzeug_ordner(ctx, name), "meta.json"), encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) else None
    except (OSError, ValueError):
        return None


def _meta_speichern(ctx, name, meta):
    o = _werkzeug_ordner(ctx, name)
    os.makedirs(o, mode=0o700, exist_ok=True)
    _schreiben(os.path.join(o, "meta.json"), json.dumps(meta, ensure_ascii=False, indent=1))


def _code_laden(ctx, name):
    try:
        with open(os.path.join(_werkzeug_ordner(ctx, name), "code.py"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _alle(ctx):
    """Alle Werkzeuge (meta), ohne verworfene."""
    try:
        namen = sorted(os.listdir(_ordner(ctx)))
    except OSError:
        return []
    return [m for m in (_meta_laden(ctx, n) for n in namen if NAME_MUSTER.fullmatch(n)) if m]


def _sha(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _code_hash(salz, code):
    return hashlib.sha256((salz + ":" + code).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------- Statische Prüfung

def _attribut_verboten(name):
    return str(name).startswith("_") or name in VERBOTENE_ATTRIBUTE


def _format_harmlos(text, tiefe=0):
    """Formatkette ohne Attribut- und Indexzugriff in den Feldern ("{0.__class__}", "{x[y]}" wären Umwege)."""
    import string as _string
    if tiefe > 2:
        return False
    try:
        for _, feld, spec, _ in _string.Formatter().parse(text):
            if feld is not None and ("." in feld or "[" in feld):
                return False
            if spec and "{" in spec and not _format_harmlos(spec, tiefe + 1):
                return False
    except (ValueError, TypeError):
        return False
    return True


def code_pruefen(code):
    """Statische Prüfung per ast -> Liste von Problemtexten (leer = in Ordnung). Zweite Linie, nicht die Grenze.
    Seit 0.7 sind nur die Texte zweisprachig; jede Prüfung ist dieselbe wie vorher."""
    if not isinstance(code, str) or not code.strip():
        return [_t("Der Code fehlt.", "The code is missing.")]
    if len(code) > MAX_CODE_ZEICHEN:
        return [_t("Der Code ist zu lang (%d Zeichen, erlaubt %d).", "The code is too long (%d characters, allowed %d).")
                % (len(code), MAX_CODE_ZEICHEN)]
    if code.count("\n") + 1 > MAX_CODE_ZEILEN:
        return [_t("Der Code ist zu lang (mehr als %d Zeilen).", "The code is too long (more than %d lines).")
                % MAX_CODE_ZEILEN]
    try:
        baum = ast.parse(code, "werkzeug.py")
    except SyntaxError as e:
        return [_t("Syntaxfehler in Zeile %s: %s", "Syntax error in line %s: %s") % (e.lineno, e.msg)]
    except (ValueError, MemoryError, RecursionError) as e:
        return [_t("Code nicht lesbar: %s", "Code not readable: %s") % type(e).__name__]
    probleme = []
    knoten_name = KNOTEN_NAME_EN if SPRACHE == "en" else KNOTEN_NAME

    def p(knoten, text):
        probleme.append(_t("Zeile %s: %s", "Line %s: %s") % (getattr(knoten, "lineno", "?"), text))

    # Positivliste (M4): welcher Name steht für welches Modul, und welche Namen stehen direkt vor einem Punkt
    module = {}
    for k in ast.walk(baum):
        if isinstance(k, ast.Import):
            for a in k.names:
                module[a.asname or a.name] = a.name
    vor_punkt = {id(k.value) for k in ast.walk(baum) if isinstance(k, ast.Attribute)}

    # getattr/hasattr nur als direkter Aufruf mit konstantem, harmlosem Namen
    erlaubte_aufrufe = set()
    for k in ast.walk(baum):
        if isinstance(k, ast.Call) and isinstance(k.func, ast.Name) and k.func.id in ("getattr", "hasattr"):
            a = k.args[1] if len(k.args) >= 2 else None
            if isinstance(a, ast.Constant) and isinstance(a.value, str) and not _attribut_verboten(a.value):
                erlaubte_aufrufe.add(id(k.func))
    for k in ast.walk(baum):
        if isinstance(k, VERBOTENE_KNOTEN):
            p(k, _t("%s ist nicht erlaubt (nur einfaches Rechnen und Textarbeit).",
                    "%s is not allowed (only simple calculation and text work).")
              % knoten_name.get(type(k).__name__, type(k).__name__))
        if isinstance(k, ast.Import):
            for a in k.names:
                if a.name not in ERLAUBTE_IMPORTE:                 # auch keine Untermodule (a.b)
                    p(k, _t("Import „%s“ ist nicht erlaubt.", "Import “%s” is not allowed.") % a.name)
        elif isinstance(k, ast.ImportFrom):
            if k.level or not k.module or k.module not in ERLAUBTE_IMPORTE:
                p(k, _t("Import aus „%s“ ist nicht erlaubt.", "Import from “%s” is not allowed.")
                  % ("." * (k.level or 0) + (k.module or "")))
            for a in k.names:
                if a.name == "*" or _attribut_verboten(a.name) or a.name not in ERLAUBTE_NAMEN.get(k.module or "", ()):
                    p(k, _t("„from %s import %s“ ist nicht erlaubt.", "“from %s import %s” is not allowed.")
                      % (k.module, a.name))
        elif isinstance(k, ast.Name):
            if k.id in VERBOTENE_NAMEN or "__" in k.id:
                p(k, _t("„%s“ ist nicht erlaubt.", "“%s” is not allowed.") % k.id)
            elif k.id in ("getattr", "hasattr") and id(k) not in erlaubte_aufrufe:
                p(k, _t("%s nur mit festem Attributnamen ohne Unterstrich.",
                        "%s only with a fixed attribute name without underscore.") % k.id)
            elif k.id in module and (id(k) not in vor_punkt or not isinstance(k.ctx, ast.Load)):
                p(k, _t("Das Modul „%s“ nur direkt verwenden (%s.name), nicht zuweisen oder weitergeben.",
                        "Use the module “%s” only directly (%s.name), do not assign it or pass it on.") % (k.id, k.id))
        elif isinstance(k, ast.Attribute):
            if _attribut_verboten(k.attr):
                p(k, _t("Attribut „%s“ ist nicht erlaubt.", "Attribute “%s” is not allowed.") % k.attr)
            elif isinstance(k.value, ast.Name) and k.value.id in module and \
                    k.attr not in ERLAUBTE_NAMEN.get(module[k.value.id], ()):
                p(k, _t("„%s.%s“ ist nicht erlaubt.", "“%s.%s” is not allowed.") % (k.value.id, k.attr))
            elif k.attr == "format" and not (isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)
                                             and _format_harmlos(k.value.value)):
                p(k, _t("„.format“ nur an einer festen Zeichenkette mit einfachen Feldern (kein Punkt, keine Klammer).",
                        "“.format” only on a fixed string with simple fields (no dot, no bracket)."))
        elif isinstance(k, ast.Constant) and isinstance(k.value, str) and "__" in k.value:
            p(k, _t("Zeichenketten mit doppeltem Unterstrich sind nicht erlaubt.",
                    "Strings with a double underscore are not allowed."))
    funktionen = [k for k in baum.body if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and k.name == "ausfuehren"]
    if not funktionen:
        probleme.append(_t("Es fehlt def ausfuehren(eingabe) auf oberster Ebene.",
                           "def ausfuehren(eingabe) at the top level is missing."))
    elif isinstance(funktionen[-1], ast.AsyncFunctionDef):
        probleme.append(_t("ausfuehren darf nicht async sein.", "ausfuehren must not be async."))
    else:
        a = funktionen[-1].args
        positionell = list(getattr(a, "posonlyargs", None) or []) + list(a.args)
        pflicht = len(positionell) - len(a.defaults)
        kw_pflicht = any(d is None for d in a.kw_defaults)
        if not (positionell or a.vararg) or pflicht > 1 or kw_pflicht:
            probleme.append(_t("ausfuehren braucht genau einen Parameter (eingabe).",
                               "ausfuehren needs exactly one parameter (eingabe)."))
    return probleme[:20]


def entwurf_pruefen(d, belegt=()):
    """Antwort von Claude -> (entwurf oder None, probleme). None, wenn nichts Brauchbares da ist (kein Code, keine
    Tests). belegt: Namen aktiver Werkzeuge; ein solcher Name bekommt _2, _3 ... angehängt."""
    if not isinstance(d, dict):
        return None, [_t("Die Antwort war kein JSON-Objekt.", "The answer was not a JSON object.")]
    probleme = []
    name = str(d.get("name") or "").strip()
    if not NAME_MUSTER.fullmatch(name):
        probleme.append(_t("name „%s“ passt nicht zu [a-z][a-z0-9_]{2,30}.",
                           "name “%s” does not match [a-z][a-z0-9_]{2,30}.") % name[:40])
    elif name in belegt:
        basis = name[:28]
        name = next(("%s_%d" % (basis, i) for i in range(2, 100) if "%s_%d" % (basis, i) not in belegt), name)
    zweck = " ".join(str(d.get("zweck") or "").split())[:200]
    if not zweck:
        probleme.append(_t("zweck fehlt.", "zweck is missing."))
    schema = d.get("eingabe_schema")
    if not isinstance(schema, dict) or schema.get("type", "object") != "object":
        probleme.append(_t("eingabe_schema muss ein JSON-Schema mit type object sein.",
                           "eingabe_schema must be a JSON schema with type object."))
        schema = {"type": "object", "properties": {}}
    code = d.get("code")
    tests = d.get("tests")
    if not isinstance(code, str) or not code.strip():
        return None, probleme + [_t("code fehlt.", "code is missing.")]
    if not isinstance(tests, list) or not tests:
        return None, probleme + [_t("tests fehlen.", "tests are missing.")]
    saubere = []
    for i, t in enumerate(tests[:MAX_TESTS], 1):
        if not isinstance(t, dict) or not isinstance(t.get("eingabe"), dict) \
                or not isinstance(t.get("erwartet"), dict) or not t.get("erwartet"):
            probleme.append(_t("Test %d braucht eingabe (Objekt) und erwartet (nicht leeres Objekt).",
                               "Test %d needs eingabe (an object) and erwartet (a non-empty object).") % i)
            continue
        saubere.append({"eingabe": t["eingabe"], "erwartet": t["erwartet"]})
    if len(tests) > MAX_TESTS:
        probleme.append(_t("Höchstens %d Tests.", "At most %d tests.") % MAX_TESTS)
    if len(saubere) < MIN_TESTS:
        probleme.append(_t("Mindestens %d gültige Tests.", "At least %d valid tests.") % MIN_TESTS)
    if len(json.dumps(saubere, ensure_ascii=False)) > 32000:
        probleme.append(_t("Die Tests sind zu groß.", "The tests are too large."))
    probleme += code_pruefen(code)
    return {"name": name, "zweck": zweck, "eingabe_schema": schema, "code": code, "tests": saubere}, probleme


# ---------------------------------------------------------------------------------------------- Läufer und Sandbox

LAEUFER = r'''"""Läufer der Werkzeugschmiede: lädt werkzeug.py mit eingeschränkten Builtins und ruft ausfuehren(eingabe) auf.
Eingabe JSON auf stdin ({"modus": "tests", "tests": [...]} oder {"modus": "nutzen", "eingabe": {...}}), Ausgabe eine
Zeile MARKE + JSON auf stdout. Läuft im Container (Python 3.12) und in den Tests lokal (Python 3.8)."""
import builtins
import io
import json
import math
import signal
import sys
import traceback

ERLAUBT = @@ERLAUBT@@
OHNE = @@OHNE@@
MARKE = @@MARKE@@
T = @@TEXTE@@


class Zeitlimit(BaseException):
    pass


def _alarm(signum, rahmen):
    raise Zeitlimit()


_echt_import = builtins.__import__


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or str(name).split(".")[0] not in ERLAUBT:
        raise ImportError(T["import"] + str(name))
    return _echt_import(name, globals, locals, fromlist, level)


def fehlertext(e):
    zeile = ""
    for fr in traceback.extract_tb(e.__traceback__):
        if fr.filename == "werkzeug.py":
            zeile = T["zeile"] % fr.lineno
    return ("%s: %s" % (type(e).__name__, e))[:300] + zeile


def laden(pfad):
    with open(pfad, encoding="utf-8") as f:
        quelle = f.read()
    eingebaut = dict((k, getattr(builtins, k)) for k in dir(builtins) if k not in OHNE)
    eingebaut["__import__"] = _import
    ns = {"__builtins__": eingebaut, "__name__": "werkzeug"}
    exec(compile(quelle, "werkzeug.py", "exec"), ns)
    f = ns.get("ausfuehren")
    if not callable(f):
        raise ValueError(T["fehlt"])
    return f


def gleich(ist, soll):
    """erwartet (soll) muss im Ergebnis (ist) enthalten sein; Zahlen mit kleiner Toleranz."""
    if isinstance(soll, dict):
        return isinstance(ist, dict) and all(k in ist and gleich(ist[k], v) for k, v in soll.items())
    if isinstance(soll, list):
        return isinstance(ist, (list, tuple)) and len(ist) == len(soll) and all(gleich(a, b) for a, b in zip(ist, soll))
    if isinstance(soll, bool) or isinstance(ist, bool):
        return ist is soll
    if isinstance(soll, (int, float)) and isinstance(ist, (int, float)):
        return math.isclose(ist, soll, rel_tol=1e-6, abs_tol=1e-9)
    return ist == soll


def kurz(x, n=400):
    try:
        t = json.dumps(x, ensure_ascii=False)
    except (TypeError, ValueError):
        t = repr(x)
    return t if len(t) <= n else t[:n] + " …"


def aufruf(f, eingabe, je_s):
    signal.setitimer(signal.ITIMER_REAL, je_s)
    try:
        erg = f(eingabe)
    except Zeitlimit:
        return {"ok": False, "fehler": T["zeitlimit"] % je_s}
    except BaseException as e:
        return {"ok": False, "fehler": fehlertext(e)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    if not isinstance(erg, dict):
        return {"ok": False, "fehler": T["kein_dict"] % type(erg).__name__}
    try:
        t = json.dumps(erg, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as e:
        return {"ok": False, "fehler": T["kein_json"] % str(e)[:200]}
    if len(t) > 60000:
        return {"ok": False, "fehler": T["zu_gross"] % len(t)}
    return {"ok": True, "ergebnis": erg}


def main():
    try:
        auftrag = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        auftrag = {}
    marke = str(auftrag.get("marke") or MARKE)   # je Lauf zufällig (das Werkzeug kennt sie nicht)
    raus = sys.stdout
    sys.stdout = io.StringIO()            # print im Werkzeug landet nicht in der Ausgabe
    signal.signal(signal.SIGALRM, _alarm)
    je_s = float(auftrag.get("je_s") or 5)
    try:
        signal.setitimer(signal.ITIMER_REAL, je_s)
        try:
            f = laden(sys.argv[1])
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    except Zeitlimit:
        antwort = {"ok": False, "fehler": T["laden_lange"]}
    except BaseException as e:
        antwort = {"ok": False, "fehler": T["laden"] + fehlertext(e)}
    else:
        if auftrag.get("modus") == "tests":
            einzeln = []
            for i, t in enumerate(auftrag.get("tests") or [], 1):
                r = aufruf(f, t.get("eingabe"), je_s)
                if not r["ok"]:
                    einzeln.append({"nr": i, "ok": False, "fehler": r["fehler"]})
                elif gleich(r["ergebnis"], t.get("erwartet")):
                    einzeln.append({"nr": i, "ok": True, "ergebnis": kurz(r["ergebnis"])})
                else:
                    einzeln.append({"nr": i, "ok": False, "ergebnis": kurz(r["ergebnis"]),
                                    "fehler": T["erwartet"] % (kurz(t.get("erwartet"), 300),
                                                               kurz(r["ergebnis"], 300))})
            antwort = {"ok": bool(einzeln) and all(x["ok"] for x in einzeln), "einzeln": einzeln}
        else:
            antwort = aufruf(f, auftrag.get("eingabe"), je_s)
    raus.write(marke + json.dumps(antwort, ensure_ascii=False) + "\n")
    raus.flush()


main()
'''
# Texte des Läufers (seit 0.7 zweisprachig; nur Fehlermeldungen, die Logik des Läufers ist dieselbe)
LAEUFER_TEXTE = {
    "de": {"import": "Import nicht erlaubt: ", "zeile": " (Zeile %d)", "fehlt": "Die Funktion ausfuehren fehlt.",
           "zeitlimit": "Zeitlimit von %g s je Aufruf überschritten.",
           "kein_dict": "ausfuehren muss ein dict zurückgeben, nicht %s.",
           "kein_json": "Ergebnis ist kein reines JSON: %s", "zu_gross": "Ergebnis ist zu groß (%d Zeichen).",
           "erwartet": "erwartet %s, erhalten %s", "laden_lange": "Das Laden des Codes dauert zu lange.",
           "laden": "Laden: "},
    "en": {"import": "Import not allowed: ", "zeile": " (line %d)", "fehlt": "The function ausfuehren is missing.",
           "zeitlimit": "Time limit of %g s per call exceeded.",
           "kein_dict": "ausfuehren must return a dict, not %s.",
           "kein_json": "The result is not pure JSON: %s", "zu_gross": "The result is too large (%d characters).",
           "erwartet": "expected %s, got %s", "laden_lange": "Loading the code takes too long.",
           "laden": "Loading: "},
}


def laeufer_text():
    return (LAEUFER.replace("@@ERLAUBT@@", repr(sorted(ERLAUBTE_IMPORTE)))
            .replace("@@OHNE@@", repr(LAEUFER_OHNE)).replace("@@MARKE@@", repr(MARKE))
            .replace("@@TEXTE@@", repr(LAEUFER_TEXTE["en" if SPRACHE == "en" else "de"])))


def laeufer_schreiben(ordner, code):
    """werkzeug.py und lauf.py in ein Laufverzeichnis (lesbar für den Nutzer 65534 im Container)."""
    for datei, text in (("werkzeug.py", code), ("lauf.py", laeufer_text())):
        pfad = os.path.join(ordner, datei)
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(pfad, 0o644)


def sandbox_befehl(ordner, name, zeitlimit, datei="lauf.py", argumente=("/werkzeug/werkzeug.py",)):
    """Der docker-Aufruf der Sandbox (Liste für subprocess). Vorne steht DOCKER (JARVIS_SCHMIEDE_DOCKER), danach immer
    dieselben Schalter. Kein --cpus: manche Kernel können das nicht."""
    return DOCKER + ["run", "--rm", "-i", "--name", name, "--pull", "never",
                     "--network", "none", "--read-only", "--tmpfs", "/tmp:size=16m",
                     "--memory", "256m", "--memory-swap", "256m", "--pids-limit", "64", "--ulimit", "nproc=64:64",
                     "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
                     "--cpu-shares", "256", "--log-driver", "none", "-e", "PYTHONDONTWRITEBYTECODE=1",
                     "-v", "%s:/werkzeug:ro" % ordner, "--workdir", "/tmp", IMAGE,
                     "timeout", "-s", "KILL", str(int(zeitlimit)), "python3", "-I", "-B", "/werkzeug/" + datei
                     ] + list(argumente)


def _container_weg(name):
    for befehl in (["kill", name], ["rm", "-f", name]):
        try:
            subprocess.run(DOCKER + befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20)
        except (OSError, subprocess.SubprocessError):
            pass


def container_lauf(ordner, eingabe, zeitlimit, datei="lauf.py", argumente=("/werkzeug/werkzeug.py",)):
    """Einen Container starten, eingabe (bytes) auf stdin, Ausgabe begrenzt lesen. Hartes Zeitlimit: timeout im
    Container, nach zeitlimit + NACHFRIST_S docker kill von außen. -> {rc, aus, err, dauer, abgebrochen, name}"""
    name = "jarvis-schmiede-" + uuid.uuid4().hex[:12]
    befehl = sandbox_befehl(ordner, name, zeitlimit, datei, argumente)
    start = time.monotonic()
    try:
        p = subprocess.Popen(befehl, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        return {"rc": None, "aus": b"", "err": str(e).encode(), "dauer": 0.0, "abgebrochen": False, "name": name}
    puffer = {"aus": bytearray(), "err": bytearray()}

    def lesen(strom, ziel):
        while True:
            try:
                stueck = os.read(strom.fileno(), 65536)
            except OSError:
                break
            if not stueck:
                break
            rest = MAX_AUSGABE_BYTES - len(ziel)
            if rest > 0:
                ziel.extend(stueck[:rest])

    def schreiben():
        try:
            p.stdin.write(eingabe)
            p.stdin.close()
        except (OSError, ValueError):
            pass

    faeden = [threading.Thread(target=lesen, args=(p.stdout, puffer["aus"]), daemon=True),
              threading.Thread(target=lesen, args=(p.stderr, puffer["err"]), daemon=True),
              threading.Thread(target=schreiben, daemon=True)]
    for t in faeden:
        t.start()
    abgebrochen = False
    try:
        p.wait(timeout=zeitlimit + NACHFRIST_S)
    except subprocess.TimeoutExpired:
        abgebrochen = True
        _container_weg(name)
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    for t in faeden:
        t.join(5)
    return {"rc": p.returncode, "aus": bytes(puffer["aus"]), "err": bytes(puffer["err"]),
            "dauer": time.monotonic() - start, "abgebrochen": abgebrochen, "name": name}


def _stoerung(err):
    zeilen = [z for z in bytes(err or b"").decode("utf-8", "replace").splitlines()
              if z.strip() and not z.startswith("WARNING: Your kernel does not support")]
    return " ".join(zeilen)[-300:] or _t("keine Meldung", "no message")


def auswerten(r, zeitlimit, marke=MARKE):
    """Rohergebnis eines Laufs -> Antwort des Läufers oder eine Fehlerbeschreibung. Gewertet wird die Markenzeile nur
    bei Rückgabe 0 und ohne Abbruch (Prüfbericht K3: sonst ließe sich ein Ergebnis vor dem Absturz fälschen)."""
    aus = bytes(r.get("aus") or b"").decode("utf-8", "replace")
    zeilen = [z for z in aus.splitlines() if z.startswith(marke)]
    dauer = round(float(r.get("dauer") or 0), 1)
    if zeilen and r.get("rc") == 0 and not r.get("abgebrochen"):
        try:
            d = json.loads(zeilen[-1][len(marke):])
        except ValueError:
            d = None
        if isinstance(d, dict):
            d["dauer_s"] = dauer
            return d
    rc = r.get("rc")
    if r.get("abgebrochen") or (rc in (124, 137) and dauer >= zeitlimit - 1):
        return {"ok": False, "zeitlimit": True, "dauer_s": dauer,
                "fehler": _t("Zeitlimit von %d s überschritten, der Lauf wurde abgebrochen.",
                             "Time limit of %d s exceeded, the run was stopped.") % zeitlimit}
    if rc == 137:
        return {"ok": False, "dauer_s": dauer, "fehler": _t("Abgebrochen, vermutlich über 256 MB Speicher.",
                                                            "Stopped, probably over 256 MB of memory.")}
    if rc is None or rc in (125, 126, 127):
        return {"ok": False, "sandbox_fehler": True, "dauer_s": dauer,
                "fehler": _t("Die Sandbox ließ sich nicht starten: ", "The sandbox could not be started: ")
                + _stoerung(r.get("err"))}
    return {"ok": False, "dauer_s": dauer,
            "fehler": _t("Das Werkzeug endete ohne Ergebnis (Code %s): %s", "The tool ended without a result (code %s): %s")
            % (rc, _stoerung(r.get("err")))}


def sandbox(code, auftrag, zeitlimit=ZEITLIMIT_S):
    """Code abgeschottet ausführen. auftrag: {"modus": "tests", "tests": [...]} oder {"modus": "nutzen", "eingabe": ...},
    optional "je_s". -> Antwort des Läufers ({"ok", "einzeln"} bzw. {"ok", "ergebnis"}) oder {"ok": False, "fehler"}."""
    if SANDBOX_ERSATZ is not None:
        return SANDBOX_ERSATZ(code, auftrag, zeitlimit)
    if not _lauf_sperre.acquire(timeout=60):
        return {"ok": False, "sandbox_fehler": True, "fehler": _t("Die Sandbox ist gerade belegt.",
                                                                  "The sandbox is busy right now.")}
    try:
        ordner = tempfile.mkdtemp(prefix="jarvis-schmiede-", dir=SANDBOX_TMP)
        try:
            os.chmod(ordner, 0o755)
            laeufer_schreiben(ordner, code)
            marke = "<<<SCHMIEDE-%s>>>" % secrets.token_hex(12)
            r = container_lauf(ordner, json.dumps(dict(auftrag, marke=marke), ensure_ascii=False).encode("utf-8"),
                               zeitlimit)
        finally:
            shutil.rmtree(ordner, ignore_errors=True)
    finally:
        _lauf_sperre.release()
    return auswerten(r, zeitlimit, marke)


def tests_laufen(code, tests):
    """Alle Tests in einem Containerlauf -> {ok, bestanden, gesamt, einzeln, fehler?, sandbox_fehler?, dauer_s}."""
    r = sandbox(code, {"modus": "tests", "tests": tests, "je_s": TEST_JE_S}, ZEITLIMIT_S)
    einzeln = r.get("einzeln") if isinstance(r.get("einzeln"), list) else []
    erg = {"ok": bool(r.get("ok")) and len(einzeln) == len(tests), "bestanden": sum(1 for x in einzeln if x.get("ok")),
           "gesamt": len(tests), "einzeln": einzeln[:MAX_TESTS], "dauer_s": r.get("dauer_s")}
    if r.get("fehler"):
        erg["fehler"] = str(r["fehler"])[:400]
    if r.get("sandbox_fehler"):
        erg["sandbox_fehler"] = True
    return erg


# ---------------------------------------------------------------------------------------------- Bauen

def _kurz_json(x, n):
    t = json.dumps(x, ensure_ascii=False)
    return t if len(t) <= n else t[:n] + " …"


def _auftrag_text(bedarf, beispiele, vorhandene):
    t = _t("Baue ein Werkzeug für diesen Bedarf:\n%s\n", "Build a tool for this need:\n%s\n") % bedarf
    if beispiele:
        t += _t("\nBeispiele, wie es genutzt werden soll:\n", "\nExamples of how it is meant to be used:\n") + \
            "\n".join("- " + b for b in beispiele) + "\n"
    if vorhandene:
        t += _t("\nDiese Werkzeuge gibt es schon (nicht doppelt bauen, anderen Namen wählen):\n",
                "\nThese tools already exist (do not build them twice, choose a different name):\n") + "\n".join(
            "- %s: %s" % (n, z) for n, z in vorhandene) + "\n"
    return t


def _reparatur_text(antwort, probleme):
    return (_t("Dein letzter Entwurf hat die Prüfung nicht bestanden.\n\nEntwurf:\n%s\n\nProbleme:\n%s\n\nKorrigiere den "
               "Entwurf und antworte wieder NUR mit dem vollständigen JSON. Ändere einen erwarteten Testwert nur, wenn "
               "er nachweislich falsch nachgerechnet war.",
               "Your last draft did not pass the check.\n\nDraft:\n%s\n\nProblems:\n%s\n\nCorrect the draft and again "
               "answer ONLY with the complete JSON. Change an expected test value only if it was demonstrably worked "
               "out wrongly.") % (_kurz_json(antwort, 24000), "\n".join("- " + p for p in probleme[:20])))


def _testprobleme(ergebnis):
    lauf = _t("Lauf: ", "Run: ")
    if ergebnis.get("fehler") and not ergebnis.get("einzeln"):
        return [lauf + ergebnis["fehler"]]
    return ["Test %s: %s" % (x.get("nr"), x.get("fehler") or _t("falsch", "wrong"))
            for x in ergebnis.get("einzeln", []) if not x.get("ok")] or \
        [lauf + str(ergebnis.get("fehler") or _t("nicht alle Tests liefen", "not all tests ran"))]


def _zaehler(ctx, erhoehen=False):
    """Vorschläge heute (Kostenbremse). Datei schmiede/zaehler.json."""
    pfad = os.path.join(_ordner(ctx), "zaehler.json")
    tag = time.strftime("%Y-%m-%d", time.localtime(ctx.jetzt()))
    try:
        with open(pfad, encoding="utf-8") as f:
            z = json.load(f)
    except (OSError, ValueError):
        z = {}
    n = int(z.get("vorschlaege") or 0) if z.get("tag") == tag else 0
    if erhoehen:
        n += 1
        _schreiben(pfad, json.dumps({"tag": tag, "vorschlaege": n}))
    return n


def _ansehen_link(ctx, name, token):
    return ctx.oeffentlich("schmiede/ansehen?" + urllib.parse.urlencode({"name": name, "t": token}))


def _bauen(ctx, person, bedarf, beispiele):
    """Ein Vorschlag von Anfang bis Push. -> Meldung (für das Gespräch, ohne Freigabe-Code)."""
    with _sperre:
        alle = _alle(ctx)
    aktiv = [m for m in alle if m.get("status") == "aktiv"]
    belegt = {m["name"] for m in aktiv}
    try:
        antwort = ctx.denken_json(_auftrag_text(bedarf, beispiele, [(m["name"], m.get("zweck", "")) for m in aktiv]),
                                  system=SYSTEM, stufe="normal", zweck="schmiede")
    except Exception as x:
        ctx.log("Schmiede: Nachdenken ging nicht:", type(x).__name__, x)
        return _t("Ich konnte gerade nicht nachdenken (%s). Versuch es später noch einmal.",
                  "I could not think it through just now (%s). Please try again later.") % type(x).__name__
    denkrunden, entwurf, probleme, ergebnis = 1, None, [], None
    for runde in range(REPARATUREN + 1):
        entwurf, probleme = entwurf_pruefen(antwort, belegt)
        ergebnis = None
        if entwurf is not None and not probleme:
            ergebnis = tests_laufen(entwurf["code"], entwurf["tests"])
            if ergebnis.get("sandbox_fehler"):
                ctx.log("Schmiede: Sandbox-Fehler:", ergebnis.get("fehler"))
                return _t("Die Sandbox läuft gerade nicht (%s). Ich habe nichts gespeichert.",
                          "The sandbox is not running right now (%s). I have saved nothing.") % ergebnis.get("fehler")
            if ergebnis["ok"]:
                break
            probleme = _testprobleme(ergebnis)
        if runde == REPARATUREN:
            break
        try:
            antwort = ctx.denken_json(_reparatur_text(antwort, probleme), system=SYSTEM, stufe="normal",
                                      zweck="schmiede")
            denkrunden += 1
        except Exception as x:
            ctx.log("Schmiede: Reparatur ging nicht:", type(x).__name__, x)
            break
    if entwurf is None:
        text = _t("Ich habe kein brauchbares Werkzeug hinbekommen: %s",
                  "I could not come up with a usable tool: %s") % "; ".join(probleme[:3])
        ctx.push(person, _t("Jarvis: Werkzeug nicht gebaut", "Jarvis: tool not built"), text, tag="jarvis-schmiede")
        return text
    ok = bool(ergebnis and ergebnis.get("ok"))
    name = entwurf["name"]
    if not ok and not NAME_MUSTER.fullmatch(name):
        name = "entwurf_%s" % uuid.uuid4().hex[:6]
    jetzt = ctx.jetzt()
    meta = {"name": name, "zweck": entwurf["zweck"], "eingabe_schema": entwurf["eingabe_schema"],
            "tests": entwurf["tests"], "bedarf": bedarf, "beispiele": beispiele,
            "status": "entwurf" if ok else "gescheitert", "erstellt": jetzt, "erstellt_von": person,
            "denkrunden": denkrunden, "sha256": _sha(entwurf["code"]), "ansehen_token": secrets.token_urlsafe(16),
            "testergebnis": ergebnis or {"ok": False, "fehler": "; ".join(probleme[:5])},
            "probleme": probleme[:10], "fehlversuche": 0, "nutzungen": 0}
    code_wort = None
    if ok:
        code_wort = "%04d" % secrets.randbelow(10000)
        meta["freigabe_salz"] = secrets.token_hex(8)
        meta["freigabe_hash"] = _code_hash(meta["freigabe_salz"], code_wort)
    with _sperre:
        alt = _meta_laden(ctx, name)
        if alt and alt.get("status") == "aktiv":          # sollte belegt verhindern; nie ein aktives überschreiben
            return _t("Ein aktives Werkzeug „%s“ gibt es schon, ich habe nichts überschrieben.",
                      "An active tool “%s” already exists, I have overwritten nothing.") % name
        o = _werkzeug_ordner(ctx, name)
        os.makedirs(o, mode=0o700, exist_ok=True)
        _schreiben(os.path.join(o, "code.py"), entwurf["code"])
        _meta_speichern(ctx, name, meta)
    link = _ansehen_link(ctx, name, meta["ansehen_token"])
    if ok:
        ctx.log("Schmiede: Entwurf %s fertig (%d Denkrunden)" % (name, denkrunden))
        ctx.push(person, _t("Jarvis: neues Werkzeug „%s“", "Jarvis: new tool “%s”") % name,
                 _t("%s\nTests: %d von %d bestanden.\nFreigeben: Sag „Werkzeug %s freigeben, Code %s“.\n"
                    "Verwerfen: „Werkzeug %s verwerfen“.",
                    "%s\nTests: %d of %d passed.\nTo approve, say “approve tool %s, code %s”.\n"
                    "To discard: “discard tool %s”.") % (entwurf["zweck"], ergebnis["bestanden"], ergebnis["gesamt"],
                                                       name, code_wort, name),
                 klick=link, tag="jarvis-schmiede")
        empfaenger = (ctx.personen().get(person) or {}).get("name") or person
        return _t("Entwurf „%s“ steht: %s %d von %d Tests bestanden. %s hat einen Push mit dem Freigabe-Code "
                  "bekommen; erst damit wird das Werkzeug aktiv.",
                  "Draft “%s” is ready: %s %d of %d tests passed. %s has received a push with the approval code; "
                  "only with it does the tool become active.") % (name, entwurf["zweck"], ergebnis["bestanden"],
                                                                  ergebnis["gesamt"], empfaenger)
    ctx.log("Schmiede: Entwurf %s gescheitert (%d Denkrunden)" % (name, denkrunden))
    grund = "; ".join(probleme[:2]) or _t("Tests nicht bestanden", "tests not passed")
    ctx.push(person, _t("Jarvis: Werkzeug „%s“ nicht fertig", "Jarvis: tool “%s” not finished") % name,
             _t("Nach %d Versuchen noch nicht in Ordnung: %s\nAnsehen oder verwerfen: „Werkzeug %s verwerfen“.",
                "Still not right after %d attempts: %s\nView it or discard it: “discard tool %s”.") % (
                 denkrunden, grund[:300], name), klick=link, tag="jarvis-schmiede")
    return _t("Das Werkzeug „%s“ habe ich nach %d Versuchen nicht hinbekommen: %s",
              "I did not get the tool “%s” working after %d attempts: %s") % (name, denkrunden, grund[:300])


def _bauen_hintergrund(ctx, person, bedarf, beispiele):
    try:
        _bauen(ctx, person, bedarf, beispiele)
    except Exception as x:
        ctx.log("Schmiede: Bauen abgebrochen:", type(x).__name__, x)
        try:
            ctx.push(person, _t("Jarvis: Werkzeug nicht gebaut", "Jarvis: tool not built"),
                     _t("Beim Bauen ging etwas schief (%s).", "Something went wrong while building (%s).")
                     % type(x).__name__, tag="jarvis-schmiede")
        except Exception:
            pass
    finally:
        _bau_sperre.release()


# ---------------------------------------------------------------------------------------------- Eingaben

def _typ_passt(typ, v):
    if isinstance(typ, list):
        return any(_typ_passt(t, v) for t in typ)
    if typ == "string":
        return isinstance(v, str)
    if typ == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if typ == "integer":
        return (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer())
    if typ == "boolean":
        return isinstance(v, bool)
    if typ == "array":
        return isinstance(v, list)
    if typ == "object":
        return isinstance(v, dict)
    if typ == "null":
        return v is None
    return True


TYPNAMEN = {"string": "ein Text", "number": "eine Zahl", "integer": "eine ganze Zahl", "boolean": "wahr oder falsch",
            "array": "eine Liste", "object": "ein Objekt"}
TYPNAMEN_EN = {"string": "a text", "number": "a number", "integer": "a whole number", "boolean": "true or false",
               "array": "a list", "object": "an object"}


def eingabe_pruefen(schema, eingabe):
    """Leichte Prüfung gegen das eingabe_schema (required, type je Feld). -> Problemtext oder None."""
    if not isinstance(eingabe, dict):
        return _t("eingabe muss ein Objekt sein.", "eingabe must be an object.")
    if len(json.dumps(eingabe, ensure_ascii=False)) > MAX_EINGABE_BYTES:
        return _t("Die Eingabe ist zu groß.", "The input is too large.")
    props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    for k in schema.get("required") or []:
        if k not in eingabe:
            return _t("Es fehlt das Feld „%s“.", "The field “%s” is missing.") % k
    typnamen = TYPNAMEN_EN if SPRACHE == "en" else TYPNAMEN
    for k, v in eingabe.items():
        typ = (props.get(k) or {}).get("type") if isinstance(props.get(k), dict) else None
        if typ and not _typ_passt(typ, v):
            return _t("„%s“ muss %s sein.", "“%s” must be %s.") % (
                k, typnamen.get(typ, typ) if isinstance(typ, str) else "/".join(typ))
    return None


def _felder(schema):
    props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    pflicht = set(schema.get("required") or [])
    return ", ".join("%s%s (%s)" % (k, "" if k in pflicht else "?", (v or {}).get("type", "?") if isinstance(v, dict)
                                    else "?") for k, v in props.items()) or _t("keine", "none")


# ---------------------------------------------------------------------------------------------- Werkzeug

def auftrag(b, person, ctx):
    """Werkzeug schmiede. b = Argumente (aktion, name, eingabe, bedarf, beispiele, freigabe_code)."""
    if not eingeschaltet():                 # standardmäßig aus: nichts lesen, nichts anlegen, nicht nachdenken
        return _aus_meldung()
    b = b if isinstance(b, dict) else {}
    rolle = _rolle(ctx, person)
    if rolle not in ("haupt", "familie"):
        return {"meldung": _t("Die Werkzeugschmiede gibt es nur für die Familie.", "The tool forge is only for the family.")}
    aktion = b.get("aktion")
    if aktion is None:
        aktion = "liste"
    if aktion not in AKTIONEN:
        return {"meldung": _t("aktion muss eine von %s sein.", "aktion must be one of %s.") % ", ".join(AKTIONEN)}
    if aktion in NUR_HAUPT and rolle != "haupt":
        return {"meldung": _t("Werkzeuge vorschlagen, freigeben und verwerfen darf nur %s.",
                              "Only %s may propose, approve and discard tools.") % _haupt_name(ctx)}
    if aktion == "liste":
        return _liste(ctx, rolle)
    if aktion == "vorschlag":
        return _vorschlag(ctx, person, b)
    name = str(b.get("name") or "").strip()
    if not NAME_MUSTER.fullmatch(name):
        return {"meldung": _t("Welches Werkzeug? Namen bestehen aus a-z, 0-9 und _ (3 bis 31 Zeichen).",
                              "Which tool? Names consist of a-z, 0-9 and _ (3 to 31 characters).")}
    if aktion == "nutzen":
        return _nutzen(ctx, person, name, b.get("eingabe"))
    if aktion == "zeigen":
        return _zeigen(ctx, rolle, name)
    if aktion == "freigeben":
        return _freigeben(ctx, person, name, b.get("freigabe_code"))
    return _verwerfen(ctx, name)


def runde(ctx):
    """Die Schmiede hat keine Runde (TAKT_S = None, superhirn.runden ruft sie nie). Es gibt sie nur, damit die
    Schnittstelle vollständig ist: Sie tut nie etwas, ausgeschaltet erst recht nicht."""
    return None


def _liste(ctx, rolle):
    with _sperre:
        alle = _alle(ctx)
    aktiv = [m for m in alle if m.get("status") == "aktiv"]
    andere = [m for m in alle if m.get("status") != "aktiv"] if rolle == "haupt" else []
    zeilen = [_t("%s: %s Eingabe: %s.%s", "%s: %s Input: %s.%s") % (
        m["name"], m.get("zweck", ""), _felder(m.get("eingabe_schema") or {}),
        _t(" (%d× genutzt)", " (used %d×)") % m["nutzungen"] if m.get("nutzungen") else "")
        for m in aktiv]
    for m in andere:
        t = m.get("testergebnis") or {}
        zeilen.append(_t("%s [%s, Tests %s von %s]: %s", "%s [%s, tests %s of %s]: %s") % (
            m["name"], _status_wort(m.get("status")), t.get("bestanden", 0), t.get("gesamt", len(m.get("tests") or [])),
            m.get("zweck", "")))
    if not zeilen:
        return {"meldung": _t("Noch keine eigenen Werkzeuge.", "No tools of my own yet."), "werkzeuge": []}
    kopf = _t("Eigene Werkzeuge (%d von höchstens %d aktiv):", "My own tools (%d of at most %d active):") % (
        len(aktiv), MAX_AKTIV)
    return {"meldung": kopf + "\n" + "\n".join(zeilen),
            "werkzeuge": [{"name": m["name"], "zweck": m.get("zweck", ""), "status": m.get("status"),
                           "eingabe_schema": m.get("eingabe_schema") or {}} for m in aktiv + andere]}


def _vorschlag(ctx, person, b):
    bedarf = " ".join(str(b.get("bedarf") or "").split())
    if len(bedarf) < 10:
        return {"meldung": _t("Was soll das Werkzeug können? Beschreib den Bedarf in einem Satz (bedarf).",
                              "What should the tool be able to do? Describe the need in one sentence (bedarf).")}
    if len(bedarf) > MAX_BEDARF:
        return {"meldung": _t("Der Bedarf ist zu lang (höchstens %d Zeichen).",
                              "The need is too long (at most %d characters).") % MAX_BEDARF}
    roh = b.get("beispiele") or []
    if isinstance(roh, str):
        roh = [roh]
    beispiele = [" ".join(str(x).split())[:300] for x in roh if str(x).strip()][:8] if isinstance(roh, list) else []
    with _sperre:
        alle = _alle(ctx)
        if sum(1 for m in alle if m.get("status") == "aktiv") >= MAX_AKTIV:
            return {"meldung": _t("Es sind schon %d Werkzeuge aktiv, mehr gehen nicht. Verwirf erst eins.",
                                  "%d tools are already active, no more are possible. Discard one first.")
                    % MAX_AKTIV}
        if sum(1 for m in alle if m.get("status") != "aktiv") >= MAX_ENTWUERFE:
            return {"meldung": _t("Es liegen schon %d Entwürfe herum. Gib sie frei oder verwirf welche.",
                                  "There are already %d drafts waiting. Approve or discard some of them.")
                    % MAX_ENTWUERFE}
        if _zaehler(ctx) >= MAX_VORSCHLAEGE_TAG:
            return {"meldung": _t("Heute habe ich schon %d Werkzeuge versucht, morgen wieder.",
                                  "I have already tried %d tools today, more tomorrow.") % MAX_VORSCHLAEGE_TAG}
    if not _bau_sperre.acquire(blocking=False):
        return {"meldung": _t("Ich baue gerade schon an einem Werkzeug. Sobald es fertig ist, kommt ein Push.",
                              "I am already building a tool. As soon as it is done, a push will come.")}
    try:
        with _sperre:
            _zaehler(ctx, erhoehen=True)
    except Exception:
        _bau_sperre.release()
        raise
    ctx.log("Schmiede: Vorschlag von", person, "-", bedarf[:120])
    if IM_HINTERGRUND:
        try:
            threading.Thread(target=_bauen_hintergrund, args=(ctx, person, bedarf, beispiele), daemon=True,
                             name="schmiede-bauen").start()
        except Exception:
            _bau_sperre.release()
            raise
        return {"meldung": _t("Ich baue mir das Werkzeug jetzt und teste es abgeschottet. Das dauert ein bis drei "
                              "Minuten. Wenn der Entwurf steht, bekommst du einen Push mit dem Freigabe-Code; vorher "
                              "ist es nicht aktiv.",
                              "I am building the tool now and testing it in isolation. That takes one to three "
                              "minutes. When the draft is ready, you will get a push with the approval code; until "
                              "then it is not active.")}
    try:
        return {"meldung": _bauen(ctx, person, bedarf, beispiele)}
    finally:
        _bau_sperre.release()


def _freigeben(ctx, person, name, code_wort):
    with _sperre:
        m = _meta_laden(ctx, name)
        if not m:
            return {"meldung": _t("Ein Werkzeug „%s“ gibt es nicht.", "There is no tool “%s”.") % name}
        st = m.get("status")
        if st == "aktiv":
            return {"meldung": _t("„%s“ ist schon aktiv.", "“%s” is already active.") % name}
        if st == "gesperrt":
            return {"meldung": _t("„%s“ ist nach %d falschen Codes gesperrt. Verwirf es und lass es neu bauen.",
                                  "“%s” is locked after %d wrong codes. Discard it and have it built again.") % (
                name, FALSCHE_CODES)}
        if st != "entwurf" or not m.get("freigabe_hash"):
            return {"meldung": _t("„%s“ hat die Tests nicht bestanden und lässt sich nicht freigeben. Verwerfen oder "
                                  "neu vorschlagen.",
                                  "“%s” did not pass its tests and cannot be approved. Discard it or propose it "
                                  "again.") % name}
        ziffern = re.sub(r"\D", "", str(code_wort or ""))
        if not ziffern:
            return {"meldung": _t("Nenn mir den vierstelligen Freigabe-Code aus dem Push.",
                                  "Tell me the four-digit approval code from the push.")}
        if not secrets.compare_digest(_code_hash(m.get("freigabe_salz", ""), ziffern), m["freigabe_hash"]):
            m["fehlversuche"] = int(m.get("fehlversuche") or 0) + 1
            if m["fehlversuche"] >= FALSCHE_CODES:
                m["status"] = "gesperrt"
            _meta_speichern(ctx, name, m)
            ctx.log("Schmiede: falscher Freigabe-Code für", name, "(%d)" % m["fehlversuche"])
            if m["status"] == "gesperrt":
                return {"meldung": _t("Der Code stimmt nicht. „%s“ ist jetzt gesperrt.",
                                      "The code is wrong. “%s” is now locked.") % name}
            return {"meldung": _t("Der Code stimmt nicht (noch %d Versuche).", "The code is wrong (%d attempts left).")
                    % (FALSCHE_CODES - m["fehlversuche"])}
        code = _code_laden(ctx, name)
        if code is None or _sha(code) != m.get("sha256"):
            return {"meldung": _t("Der Code von „%s“ wurde seit den Tests verändert. Ich gebe ihn nicht frei.",
                                  "The code of “%s” has changed since the tests. I will not approve it.") % name}
        if sum(1 for x in _alle(ctx) if x.get("status") == "aktiv") >= MAX_AKTIV:
            return {"meldung": _t("Es sind schon %d Werkzeuge aktiv. Verwirf erst eins.",
                                  "%d tools are already active. Discard one first.") % MAX_AKTIV}
        m["status"] = "aktiv"
        m["freigegeben"] = ctx.jetzt()
        m["freigegeben_von"] = person
        for k in ("freigabe_hash", "freigabe_salz", "fehlversuche"):
            m.pop(k, None)
        _meta_speichern(ctx, name, m)
    ctx.log("Schmiede: %s freigegeben" % name)
    return {"meldung": _t("„%s“ ist freigegeben und gehört jetzt zu meinen Werkzeugen: %s Eingabe: %s.",
                          "“%s” is approved and now belongs to my tools: %s Input: %s.") % (
        name, m.get("zweck", ""), _felder(m.get("eingabe_schema") or {}))}


def _verwerfen(ctx, name):
    with _sperre:
        m = _meta_laden(ctx, name)
        if not m:
            return {"meldung": _t("Ein Werkzeug „%s“ gibt es nicht.", "There is no tool “%s”.") % name}
        ziel = os.path.join(_ordner(ctx), ".verworfen")
        os.makedirs(ziel, mode=0o700, exist_ok=True)
        stempel = time.strftime("%Y%m%d-%H%M%S", time.localtime(ctx.jetzt()))
        os.replace(_werkzeug_ordner(ctx, name), os.path.join(ziel, "%s-%s-%s" % (name, stempel,
                                                                                 uuid.uuid4().hex[:4])))
    ctx.log("Schmiede: %s verworfen (%s)" % (name, m.get("status")))
    return {"meldung": _t("„%s“ ist verworfen%s.", "“%s” is discarded%s.") % (
        name, _t(" und läuft nicht mehr", " and no longer runs") if m.get("status") == "aktiv" else "")}


def _zeigen(ctx, rolle, name):
    with _sperre:
        m = _meta_laden(ctx, name)
        code = _code_laden(ctx, name) if m else None
    if not m or (rolle != "haupt" and m.get("status") != "aktiv"):
        return {"meldung": _t("Ein Werkzeug „%s“ gibt es nicht.", "There is no tool “%s”.") % name}
    t = m.get("testergebnis") or {}
    zeilen = [_t("Werkzeug „%s“ (%s): %s", "Tool “%s” (%s): %s") % (name, _status_wort(m.get("status")),
                                                                    m.get("zweck", "")),
              _t("Eingabe: %s", "Input: %s") % _felder(m.get("eingabe_schema") or {}),
              _t("Tests: %s von %s bestanden.", "Tests: %s of %s passed.") % (
                  t.get("bestanden", 0), t.get("gesamt", len(m.get("tests") or [])))]
    einzeln = {x.get("nr"): x for x in t.get("einzeln") or []}
    for i, x in enumerate(m.get("tests") or [], 1):
        e = einzeln.get(i) or {}
        zeilen.append("  %d. %s %s -> %s%s" % (i, "ok" if e.get("ok") else _t("FEHLER", "FAILED"),
                                               _kurz_json(x["eingabe"], 200), _kurz_json(x["erwartet"], 200),
                                               (" (%s)" % e["fehler"][:200]) if e.get("fehler") else ""))
    for p in m.get("probleme") or []:
        zeilen.append("  Problem: %s" % p)
    zeilen.append("Code:\n%s" % (code or _t("(fehlt)", "(missing)")))
    return {"meldung": "\n".join(zeilen), "code": code, "tests": m.get("tests"), "status": m.get("status")}


def _nutzen(ctx, person, name, eingabe):
    with _sperre:
        m = _meta_laden(ctx, name)
        code = _code_laden(ctx, name) if m else None
    if not m or m.get("status") != "aktiv":
        return {"meldung": _t("Ein aktives Werkzeug „%s“ gibt es nicht. Mit aktion liste siehst du alle.",
                              "There is no active tool “%s”. aktion liste shows all of them.") % name}
    if code is None or _sha(code) != m.get("sha256"):
        ctx.log("Schmiede: Code von %s weicht von der Freigabe ab, nicht ausgeführt" % name)
        return {"meldung": _t("Der Code von „%s“ weicht von der freigegebenen Fassung ab. Ich führe ihn nicht aus.",
                              "The code of “%s” differs from the approved version. I will not run it.") % name}
    if isinstance(eingabe, str):
        try:
            eingabe = json.loads(eingabe)
        except ValueError:
            return {"meldung": _t("eingabe muss ein JSON-Objekt sein.", "eingabe must be a JSON object.")}
    if eingabe is None:
        eingabe = {}
    fehler = eingabe_pruefen(m.get("eingabe_schema") or {}, eingabe)
    if fehler:
        return {"meldung": _t("%s Eingabe für „%s“: %s.", "%s Input for “%s”: %s.") % (
            fehler, name, _felder(m.get("eingabe_schema") or {}))}
    jetzt = time.monotonic()
    with _sperre:
        _nutzungen[:] = [t for t in _nutzungen if jetzt - t < 3600]
        if len(_nutzungen) >= NUTZUNGEN_STUNDE:
            return {"meldung": _t("Die Werkzeugschmiede hatte in der letzten Stunde %d Läufe, das reicht. Gleich "
                                  "wieder.",
                                  "The tool forge has had %d runs in the last hour, that is enough. Again shortly.")
                    % NUTZUNGEN_STUNDE}
        _nutzungen.append(jetzt)
    r = sandbox(code, {"modus": "nutzen", "eingabe": eingabe, "je_s": max(1, ZEITLIMIT_S - 3)}, ZEITLIMIT_S)
    with _sperre:
        m2 = _meta_laden(ctx, name)
        if m2:
            m2["nutzungen"] = int(m2.get("nutzungen") or 0) + 1
            m2["zuletzt"] = ctx.jetzt()
            if not r.get("ok"):
                m2["letzter_fehler"] = str(r.get("fehler") or "")[:300]
            _meta_speichern(ctx, name, m2)
    if not r.get("ok"):
        ctx.log("Schmiede: %s für %s gescheitert: %s" % (name, person, str(r.get("fehler"))[:200]))
        return {"meldung": _t("Das Werkzeug „%s“ ist gescheitert: %s", "The tool “%s” failed: %s") % (
            name, r.get("fehler"))}
    erg = r.get("ergebnis")
    return {"meldung": _t("Ergebnis von „%s“: %s", "Result of “%s”: %s") % (name, _kurz_json(erg, MAX_ERGEBNIS_ZEICHEN)),
            "ergebnis": erg}


# ---------------------------------------------------------------------------------------------- Ansicht für die Hauptperson

def _abfrage_wert(abfrage, schluessel):
    if isinstance(abfrage, (str, bytes)):
        abfrage = urllib.parse.parse_qs(abfrage.decode() if isinstance(abfrage, bytes) else abfrage)
    v = (abfrage or {}).get(schluessel) if isinstance(abfrage, dict) else None
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    return str(v or "")


SEITE = """<!doctype html><html lang="%(lang)s"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>%(titel)s</title><style>
:root{color-scheme:light dark;--g:#f4f4f2;--t:#1d1d1b;--r:#ccc;--ok:#2e7d32;--f:#c62828}
@media (prefers-color-scheme:dark){:root{--g:#16181c;--t:#e8e8e6;--r:#333}}
body{margin:0;padding:16px;background:var(--g);color:var(--t);font:15px/1.45 system-ui,sans-serif;max-width:900px}
pre{white-space:pre-wrap;word-break:break-word;border:1px solid var(--r);padding:10px;border-radius:6px;font-size:13px}
td{border-top:1px solid var(--r);padding:4px 6px;vertical-align:top;font-size:13px}table{border-collapse:collapse;width:100%%}
.ok{color:var(--ok)}.f{color:var(--f)}</style></head><body>
<h1>%(kopf)s</h1><p><b>Status:</b> %(status)s · <b>Tests:</b> %(tests)s</p>
<p>%(zweck)s</p><p><b>%(l_bedarf)s:</b> %(bedarf)s</p><p><b>%(l_eingabe)s:</b> %(felder)s</p>
<h2>Tests</h2><table>%(zeilen)s</table>%(probleme)s<h2>Code</h2><pre>%(code)s</pre>
<p>%(hinweis)s</p></body></html>"""


# Prüfbericht vor 0.7 (K5): Link läuft ab, falsches Token = 404 (zählt im Fernzugang als Fehlversuch), Kopfzeilen
ANSEHEN_S = 7 * 86400
SEITE_KOPFZEILEN = (
    ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
                                "frame-ancestors 'none'"),
    ("Cache-Control", "no-store"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("X-Robots-Tag", "noindex"),
)


def seite(pfad, abfrage, ctx, oeffentlich):
    """/schmiede/ansehen?name=…&t=… : Entwurf oder Werkzeug zum Durchsehen (nur mit dem Token aus dem Push).
    Ausgeschaltet antwortet die Schmiede auf keinen Pfad (None, die Brücke sagt dann 404)."""
    if not eingeschaltet():
        return None
    teile = str(pfad or "").split("?", 1)
    if teile[0].strip("/") != "schmiede/ansehen":
        return None
    im_pfad = teile[1] if len(teile) > 1 else ""
    name = _abfrage_wert(abfrage, "name") or _abfrage_wert(im_pfad, "name")
    token = _abfrage_wert(abfrage, "t") or _abfrage_wert(im_pfad, "t")
    with _sperre:
        m = _meta_laden(ctx, name)
        code = _code_laden(ctx, name) if m else None
    if not m or not token or not secrets.compare_digest(token, str(m.get("ansehen_token") or "")) \
            or ctx.jetzt() - float(m.get("erstellt") or 0) > ANSEHEN_S:
        return 404, "text/plain; charset=utf-8", _t("Nicht gefunden.", "Not found.").encode("utf-8")
    e = html.escape
    t = m.get("testergebnis") or {}
    einzeln = {x.get("nr"): x for x in t.get("einzeln") or []}
    zeilen = "".join("<tr><td class='%s'>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        "ok" if (einzeln.get(i) or {}).get("ok") else "f",
        "ok" if (einzeln.get(i) or {}).get("ok") else _t("Fehler", "Failed"),
        e(_kurz_json(x["eingabe"], 400)), e(_kurz_json(x["erwartet"], 400)),
        e(str((einzeln.get(i) or {}).get("fehler") or ""))) for i, x in enumerate(m.get("tests") or [], 1))
    probleme = "".join("<li>%s</li>" % e(p) for p in m.get("probleme") or [])
    hinweis = {"entwurf": _t("Freigeben: Sag „Werkzeug %s freigeben, Code …“ mit dem Code aus dem Push.",
                             "To approve, say “approve tool %s, code …” with the code from the push.") % m["name"],
               "aktiv": _t("Freigegeben, Jarvis nutzt es.", "Approved, Jarvis uses it.")}.get(
        m.get("status"), _t("Lässt sich nicht freigeben; verwerfen oder neu vorschlagen.",
                            "Cannot be approved; discard it or propose it again."))
    text = SEITE % {"lang": _t("de", "en"), "titel": _t("Werkzeug %s", "Tool %s") % e(m["name"]),
                    "kopf": _t("Werkzeug „%s“", "Tool “%s”") % e(m["name"]),
                    "status": e(str(_status_wort(m.get("status")))),
                    "tests": _t("%s von %s bestanden", "%s of %s passed") % (t.get("bestanden", 0), t.get("gesamt", 0)),
                    "zweck": e(m.get("zweck", "")), "l_bedarf": _t("Bedarf", "Need"), "bedarf": e(m.get("bedarf", "")),
                    "l_eingabe": _t("Eingabe", "Input"), "felder": e(_felder(m.get("eingabe_schema") or {})),
                    "zeilen": zeilen,
                    "probleme": ("<h2>%s</h2><ul>%s</ul>" % (_t("Probleme", "Problems"), probleme)) if probleme else "",
                    "code": e(code or _t("(fehlt)", "(missing)")), "hinweis": e(hinweis)}
    return 200, "text/html; charset=utf-8", text.encode("utf-8")


WERKZEUG_DE = {
    "beschreibung": (
        "Werkzeugschmiede: eigene kleine Rechen- und Textwerkzeuge, die du dir selbst geschrieben hast. Sie laufen "
        "abgeschottet (kein Netz, keine Dateien, kein Haus) und rechnen nur. aktion liste: deine Werkzeuge mit "
        "Eingabefeldern. nutzen: name + eingabe (Objekt nach den Feldern aus liste). zeigen: Code und Tests eines "
        "Werkzeugs. Nur die Hauptperson: vorschlag (bedarf = was das Werkzeug können soll, beispiele optional; baut im "
        "Hintergrund, testet und schickt der Hauptperson einen Push mit Freigabe-Code), freigeben (name + "
        "freigabe_code, den die Hauptperson aus dem Push nennt; denk dir nie einen aus), verwerfen (name). Schalten, "
        "Senden, Internet oder Dateien kann ein Schmiede-Werkzeug nicht. Ist die Schmiede in der Einrichtung "
        "ausgeschaltet, sagt jede Aktion das."),
    "schema": {"type": "object", "properties": {
        "aktion": {"type": "string", "enum": list(AKTIONEN)},
        "name": {"type": "string", "description": "Name des Werkzeugs (a-z, 0-9, _)"},
        "eingabe": {"type": "object", "description": "Eingabe für nutzen, Felder wie in liste"},
        "bedarf": {"type": "string", "description": "vorschlag: was das Werkzeug können soll"},
        "beispiele": {"type": "array", "items": {"type": "string"}, "description": "vorschlag: Beispielaufgaben"},
        "freigabe_code": {"type": "string", "description": "freigeben: vierstelliger Code aus dem Push an die "
                                                           "Hauptperson"}},
        "required": ["aktion"]},
}
WERKZEUG_EN = {
    "beschreibung": (
        "Tool forge: your own small calculation and text tools that you wrote yourself. They run in isolation (no "
        "network, no files, no house) and only calculate. aktion liste: your tools with their input fields. nutzen: "
        "name + eingabe (an object with the fields from liste). zeigen: code and tests of a tool. Only the main "
        "person: vorschlag (bedarf = what the tool should be able to do, beispiele optional; builds in the background, "
        "tests and sends the main person a push with an approval code), freigeben (name + freigabe_code, which the "
        "main person reads out from the push; never make one up), verwerfen (name). A forge tool cannot switch "
        "devices, send anything, reach the internet or access files. If the forge is switched off in the setup, every "
        "action says so."),
    "schema": {"type": "object", "properties": {
        "aktion": {"type": "string", "enum": list(AKTIONEN)},
        "name": {"type": "string", "description": "Name of the tool (a-z, 0-9, _)"},
        "eingabe": {"type": "object", "description": "Input for nutzen, fields as in liste"},
        "bedarf": {"type": "string", "description": "vorschlag: what the tool should be able to do"},
        "beispiele": {"type": "array", "items": {"type": "string"}, "description": "vorschlag: example tasks"},
        "freigabe_code": {"type": "string", "description": "freigeben: four-digit code from the push to the main "
                                                           "person"}},
        "required": ["aktion"]},
}
WERKZEUG = WERKZEUG_DE      # folgt setze_sprache()


def setze_sprache(sprache):
    """Sprache der Meldungen, Pushes, Seite, Problemtexte, Werkzeugbeschreibung und Modellaufträge ("de" oder "en")."""
    global SPRACHE, WERKZEUG, SYSTEM
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache
    WERKZEUG = WERKZEUG_EN if sprache == "en" else WERKZEUG_DE
    SYSTEM = SYSTEM_EN if sprache == "en" else SYSTEM_DE


# liste, zeigen, nutzen ändern nichts außerhalb der Sandbox. zeigen gibt Code und Tests wieder, die Claude aus dem
# Bedarf der Hauptperson geschrieben hat; im Zweifel als Quelle.
FREMDTEXT = {"art": "ziel", "nur_lesen": ("aktion", "liste", ["liste", "zeigen", "nutzen"]),
             "quelle_aktionen": ("aktion", "liste", ["zeigen"])}
# Aktionen, die nie über gemeinsame Lautsprecher laufen dürfen (seit 0.7; die Brücke prüft, das Modul deklariert nur).
# Die Schmiede hat keine: vorschlag/freigeben/verwerfen sind ohnehin nur für die Hauptperson und brauchen den Code aus
# ihrem Push, liste/zeigen/nutzen zeigen nur Werkzeuge, die die Hauptperson freigegeben hat (Entwürfe nur ihr selbst).
LAUTSPRECHER_PRIVAT = frozenset()
