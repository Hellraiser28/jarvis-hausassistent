#!/usr/bin/env python3
"""Baustein sprecher.py (Stimmerkennung, seit 0.6): Entscheidungsregeln, /v1/hoer-Merker, Anfragen an den Dienst.
Attrappe statt jarvis-sprecher (keine echten Profile, kein Modell, keine Netzzugriffe). Liegt der Dienst daneben
(spiegel/stack/sprecher/jarvis_sprecher.py), prueft der Test zusaetzlich dessen Zugang und Erlaubnisliste, ohne Modell."""
import asyncio
import importlib.util
import io
import json
import os
import sys
import types
import urllib.error
import urllib.parse
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import sprecher as sp  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


# ---------------------------------------------------------------- Regeln
R = {"anna": "haupt", "ben": "familie", "mia": "kind", "gast-1": "gast", "tom": "gast"}
U = "-unbekannt-"
E = lambda wer, stufe, wert=0.8: {"person": wer, "stufe": stufe, "wert": wert}   # noqa: E731
A = lambda *a, **k: sp.entscheiden("anwenden", *a, **k)[0]                        # noqa: E731
pruef("aus: nichts", sp.entscheiden("aus", "ha", "anna", E("mia", "sicher"), R, U) == ("anna", ""))
pruef("zeigen: nichts", sp.entscheiden("zeigen", "ha", "anna", E("mia", "sicher"), R, U)[0] == "anna")
# Befund 1: nie zu einer Person mit eigenen Daten (Familie hat Postfach, Dokumente, Gedaechtnis)
pruef("HA sicher Familie: Person bleibt", A("ha", "anna", E("ben", "sicher"), R, U) == "anna")
pruef("HA sicher Familie: Grund genannt", "Person bleibt" in sp.entscheiden("anwenden", "ha", "anna", E("ben", "sicher"), R, U)[1])
pruef("HA Familien-Geraet, Stimme der Hauptperson: bleibt", A("ha", "ben", E("anna", "sicher"), R, U) == "ben")
pruef("HA Kind auf dem Geraet der Hauptperson", A("ha", "anna", E("mia", "sicher"), R, U) == "mia")
pruef("HA Kind auf einem Familien-Geraet", A("ha", "ben", E("mia", "sicher"), R, U) == "mia")
pruef("HA Kinder-Geraet, Stimme der Hauptperson: bleibt Kind", A("ha", "mia", E("anna", "sicher"), R, U) == "mia")
pruef("HA Gast mit Profil auf dem Geraet der Hauptperson", A("ha", "anna", E("tom", "sicher"), R, U) == "tom")
pruef("HA sicher Hauptperson bestaetigt", sp.entscheiden("anwenden", "ha", "anna", E("anna", "sicher"), R, U)
      == ("anna", "Stimme bestätigt"))
pruef("HA fremd -> unbekannt", A("ha", "anna", E(None, "fremd", 0.1), R, U) == U)
pruef("HA unsicher bleibt", A("ha", "anna", E("ben", "unsicher", 0.5), R, U) == "anna")
pruef("HA Profil ohne Person -> unbekannt", A("ha", "anna", E("lea", "sicher"), R, U) == U)
pruef("ohne Ergebnis", A("ha", "anna", None, R, U) == "anna")
pruef("Rang nur nach unten: Gast wird nicht Kind", A("ha", "tom", E("mia", "sicher"), R, U) == "tom")
# streng: ohne sichere Erkennung wie fremd (Befund 4)
pruef("streng: ohne Ergebnis -> unbekannt", A("ha", "anna", None, R, U, streng=True) == U)
pruef("streng: zu kurz -> unbekannt", A("ha", "anna", E(None, "zu_kurz", 0), R, U, streng=True) == U)
pruef("streng: unsicher -> unbekannt", A("ha", "anna", E("anna", "unsicher", 0.5), R, U, streng=True) == U)
pruef("streng: sicher Hauptperson bleibt", A("ha", "anna", E("anna", "sicher"), R, U, streng=True) == "anna")
pruef("ohne streng: ohne_profile bleibt", A("ha", "anna", E(None, "ohne_profile", 0), R, U) == "anna")
# Befund 3: im Gastraum bleibt der Gast Gast
pruef("Gastraum: Stimme der Hauptperson bleibt Gast", A("ha", "gast-1", E("anna", "sicher"), R, U) == "gast-1")
pruef("Gastraum: fremde Stimme bleibt Gast", A("ha", "gast-1", E(None, "fremd", 0.1), R, U) == "gast-1")
pruef("Gastraum: streng ohne Ergebnis bleibt Gast", A("ha", "gast-1", None, R, U, streng=True) == "gast-1")
pruef("Gastraum: Kind hebt nicht an", A("ha", "gast-1", E("mia", "sicher"), R, U) == "gast-1")
# PC vorerst nie (Befund 1, ein Token koennte fremde Aufnahmen einspielen), App nie
for q in ("pc-sprache", "pc", "app", "app-extern", "webapp", "echtzeit-app"):
    pruef("%s: nie" % q, A(q, "anna", E("mia", "sicher"), R, U) == "anna"
          and A(q, "anna", E(None, "fremd"), R, U, streng=True) == "anna")
pruef("test-ha zaehlt wie ha", A("test-ha", "anna", E(None, "fremd", 0.1), R, U) == U)

# ---------------------------------------------------------------- Sprache
try:
    sp.setze_sprache("fr")
    pruef("Sprache: fr abgelehnt", False)
except ValueError:
    pruef("Sprache: fr abgelehnt", True)
sp.setze_sprache("en")
pruef("Englisch: bestaetigt", sp.entscheiden("anwenden", "ha", "anna", E("anna", "sicher"), R, U)[1] == "Voice confirmed")
pruef("Englisch: fremde Stimme", sp.entscheiden("anwenden", "ha", "anna", E(None, "fremd"), R, U) == (U, "unknown voice"))
pruef("Englisch: ohne Stufe", sp.entscheiden("anwenden", "ha", "anna", None, R, U)[1] == "Voice none, device stays")
try:
    sp.anlernen("Anna Groß", b"RIFF")
    pruef("Englisch: Namensfehler", False)
except sp.Fehler as e:
    pruef("Englisch: Namensfehler", str(e) == "Invalid person name.", e)
sp.setze_sprache("de")
pruef("Deutsch: ohne Stufe", sp.entscheiden("anwenden", "ha", "anna", None, R, U)[1] == "Stimme keine, Gerät bleibt")

# ---------------------------------------------------------------- /v1/hoer-Merker
uhr = [1000.0]
sp.hoer_merken("g1", "Licht an!", E("ben", "sicher"), uhr=lambda: uhr[0])
pruef("hoer: anderer Text nicht", sp.hoer_finden("g1", "Licht aus", uhr=lambda: uhr[0]) is None)
pruef("hoer: gleicher Text (Satzzeichen, Umlaute egal)",
      (sp.hoer_finden("g1", "licht an", uhr=lambda: uhr[0]) or {}).get("person") == "ben")
pruef("hoer: nur einmal", sp.hoer_finden("g1", "licht an", uhr=lambda: uhr[0]) is None)
sp.hoer_merken("g1", "Licht an", E("ben", "sicher"), uhr=lambda: uhr[0])
uhr[0] += sp.HOER_MAX_S + 1
pruef("hoer: abgelaufen", sp.hoer_finden("g1", "Licht an", uhr=lambda: uhr[0]) is None)
sp.hoer_merken("g1", "Licht an", E("ben", "sicher"), uhr=lambda: uhr[0])
pruef("hoer: anderes Geraet", sp.hoer_finden("g2", "Licht an", uhr=lambda: uhr[0]) is None)
sp.hoer_merken(None, "Musik", E("anna", "sicher"), uhr=lambda: uhr[0])
pruef("hoer: ohne Besitzer gilt haupt", (sp.hoer_finden("haupt", "Musik", uhr=lambda: uhr[0]) or {}).get("person") == "anna")
sp.hoer_merken("g3", "Musik", None, uhr=lambda: uhr[0])
sp.hoer_merken("g3", "", E("anna", "sicher"), uhr=lambda: uhr[0])
pruef("hoer: ohne Ergebnis oder Text nichts gemerkt", "g3" not in sp._hoer)
pruef("Vergleich: Umlaute und Satzzeichen", sp.vergleich("Mach's Licht   AN, bitte!") == "mach s licht an bitte"
      and sp.vergleich("Grün") == "grun")

# ---------------------------------------------------------------- Anfragen an den Dienst (Attrappe)
ANFRAGEN = []
DIENST = {}                    # Pfad -> (Code, Antwort); Code "weg" = nicht erreichbar


class Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def attrappe(req, timeout=None):
    if not req.full_url.startswith(sp.URL + "/"):
        raise AssertionError("fremde Adresse im Test: %s" % req.full_url)
    u = urllib.parse.urlsplit(req.full_url)
    ANFRAGEN.append({"pfad": u.path, "q": urllib.parse.parse_qs(u.query), "methode": req.get_method(), "daten": req.data,
                     "token": req.get_header("X-sprecher-token"), "typ": req.get_header("Content-type")})
    code, body = DIENST.get(u.path, (404, {"fehler": "unbekannt"}))
    if code == "weg":
        raise urllib.error.URLError("Verbindung abgelehnt")
    if code != 200:
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(json.dumps(body).encode()))
    return Antwort(json.dumps(body).encode())


urllib.request.urlopen = attrappe
sp.TOKEN = "sprecher-test"

DIENST["/erkennen"] = (200, E("ben", "sicher"))
r = sp.erkennen(b"RIFF-schein-wav")
a = ANFRAGEN[-1]
pruef("erkennen: Ergebnis", r == E("ben", "sicher"), r)
pruef("erkennen: POST mit WAV und Token", a["methode"] == "POST" and a["daten"] == b"RIFF-schein-wav"
      and a["token"] == "sprecher-test" and a["typ"] == "audio/wav", a)
DIENST["/erkennen"] = ("weg", None)
pruef("erkennen: Dienst weg -> None (Frage laeuft wie bisher)", sp.erkennen(b"RIFF") is None)
DIENST["/erkennen"] = (500, {"fehler": "kaputt"})
pruef("erkennen: Fehler -> None", sp.erkennen(b"RIFF") is None)

zeit = [100.0]
weiter = lambda s: zeit.__setitem__(0, zeit[0] + s)           # noqa: E731
DIENST["/zuletzt"] = (200, {"person": "mia", "stufe": "sicher", "wert": 0.8, "client": "10.0.0.5"})
n = len(ANFRAGEN)
r = sp.zuletzt("Mach das Licht an", client="10.0.0.5", uhr=lambda: zeit[0], schlaf=weiter)
pruef("zuletzt: passendes Geraet", r and r["person"] == "mia" and len(ANFRAGEN) == n + 1, r)
q = ANFRAGEN[-1]["q"]
pruef("zuletzt: GET mit Text und max_s", ANFRAGEN[-1]["methode"] == "GET" and q.get("text") == ["Mach das Licht an"]
      and q.get("max_s") == ["20"] and ANFRAGEN[-1]["token"] == "sprecher-test", ANFRAGEN[-1])
n = len(ANFRAGEN)
r = sp.zuletzt("Mach das Licht an", client="10.0.0.9", uhr=lambda: zeit[0], schlaf=weiter)
pruef("zuletzt: anderes Geraet zaehlt nicht (Befund 5)", r is None)
pruef("zuletzt: wartet und fragt mehrmals (Befund 4)", len(ANFRAGEN) - n >= 4, len(ANFRAGEN) - n)
pruef("zuletzt: ohne client jedes Geraet", (sp.zuletzt("x", uhr=lambda: zeit[0], schlaf=weiter) or {}).get("client") == "10.0.0.5")
DIENST["/zuletzt"] = (404, {"fehler": "nichts passendes"})
pruef("zuletzt: nichts passendes -> None", sp.zuletzt("Etwas anderes", warten_s=0, uhr=lambda: zeit[0], schlaf=weiter) is None)
DIENST["/zuletzt"] = ("weg", None)
n = len(ANFRAGEN)
pruef("zuletzt: Dienst weg -> sofort None", sp.zuletzt("x", uhr=lambda: zeit[0], schlaf=weiter) is None and len(ANFRAGEN) == n + 1)

DIENST["/anlernen"] = (200, {"ok": True, "person": "mia", "proben": 5})
r = sp.anlernen("mia", b"RIFF" + b"x" * 5000)
a = ANFRAGEN[-1]
pruef("anlernen: Person und WAV gehen an den Dienst", r["proben"] == 5 and a["q"].get("person") == ["mia"]
      and len(a["daten"]) == 5004 and a["methode"] == "POST", a)
n = len(ANFRAGEN)
for name in ("Mia", "ph il", "", None, "1abc", "a" * 25, "../mia"):
    try:
        sp.anlernen(name, b"RIFF")
        pruef("anlernen: Name %r abgelehnt" % (name,), False)
    except sp.Fehler as e:
        pruef("anlernen: Name %r abgelehnt" % (name,), str(e) == "Ungültiger Personenname." and e.erreichbar, e)
pruef("anlernen: falscher Name ohne Anfrage", len(ANFRAGEN) == n)
DIENST["/anlernen"] = (400, {"fehler": "Zu kurz zum Anlernen (mindestens 2 s)."})
try:
    sp.anlernen("mia", b"RIFF")
    pruef("anlernen: Text des Dienstes", False)
except sp.Fehler as e:
    pruef("anlernen: Text des Dienstes", str(e) == "Zu kurz zum Anlernen (mindestens 2 s)." and e.erreichbar, e)
DIENST["/anlernen"] = (500, {})
try:
    sp.anlernen("mia", b"RIFF")
    pruef("anlernen: HTTP-Fehler ohne Text", False)
except sp.Fehler as e:
    pruef("anlernen: HTTP-Fehler ohne Text", str(e) == "Stimmerkennung antwortet mit 500." and e.erreichbar, e)
DIENST["/anlernen"] = ("weg", None)
try:
    sp.anlernen("mia", b"RIFF")
    pruef("anlernen: Dienst weg (Bruecke antwortet 503)", False)
except sp.Fehler as e:
    pruef("anlernen: Dienst weg (Bruecke antwortet 503)", e.erreichbar is False and "URLError" in str(e), e)

DIENST["/vergessen"] = (200, {"ok": True})
r = sp.vergessen("ben")
a = ANFRAGEN[-1]
pruef("vergessen: POST mit Person", r == {"ok": True} and a["methode"] == "POST" and a["q"].get("person") == ["ben"], a)
try:
    sp.vergessen("Ben")
    pruef("vergessen: falscher Name", False)
except sp.Fehler:
    pruef("vergessen: falscher Name", True)
DIENST["/profile"] = (200, {"personen": {"anna": 4, "ben": 3}})
pruef("profile: Liste", sp.profile() == {"personen": {"anna": 4, "ben": 3}} and ANFRAGEN[-1]["methode"] == "GET")
pruef("Token geht bei jeder Anfrage mit", {a["token"] for a in ANFRAGEN} == {"sprecher-test"}, {a["token"] for a in ANFRAGEN})

# ---------------------------------------------------------------- Dienst jarvis-sprecher (nur, wenn er daneben liegt)
DIENST_DATEI = os.path.join(os.path.dirname(HIER), "spiegel", "stack", "sprecher", "jarvis_sprecher.py")
if os.path.isfile(DIENST_DATEI):
    for k in ("SPRECHER_ERLAUBT", "SPRECHER_TOKEN", "SPRECHER_TOKEN_DATEI", "SPRECHER_SPRACHE"):
        os.environ.pop(k, None)
    spec = importlib.util.spec_from_file_location("jarvis_sprecher_test", DIENST_DATEI)
    js = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(js)
    protokoll = []
    js.log = lambda *a: protokoll.append(a)
    pruef("Dienst: Erlaubnisliste ohne Einstellung nur 127.0.0.1", js.ERLAUBT == {"127.0.0.1"}, js.ERLAUBT)
    pruef("Dienst: ohne Token kein Zugang", js.TOKEN == "" and not js.H.zugang(
        types.SimpleNamespace(headers={"X-Sprecher-Token": ""})))
    pruef("Dienst: gleicher Vergleich wie die Bruecke", js.vergleich("Grün, bitte!") == sp.vergleich("Grün, bitte!"))

    class Anfrage(js.H):
        def __init__(self, pfad, kopf=None, body=b""):
            self.path, self.headers, self.rfile, self.antworten = pfad, dict(kopf or {}), io.BytesIO(body), []

        def senden(self, code, d):
            self.antworten.append((code, d))

    def get(pfad, kopf=None):
        a = Anfrage(pfad, kopf)
        a.do_GET()
        return a.antworten[-1]

    def post(pfad, body=b"", kopf=None):
        a = Anfrage(pfad, dict({"Content-Length": str(len(body))}, **(kopf or {})), body)
        a.do_POST()
        return a.antworten[-1]

    pruef("Dienst: /gesund ohne Token", get("/gesund") == (200, {"ok": True, "erkennung": False}))
    pruef("Dienst: /profile ohne Token 403", get("/profile")[0] == 403)
    pruef("Dienst: /anlernen ohne Token 403", post("/anlernen?person=mia", b"RIFF")[0] == 403)
    js.TOKEN = "dienst-test"
    MIT = {"X-Sprecher-Token": "dienst-test"}
    pruef("Dienst: falsches Token 403", get("/profile", {"X-Sprecher-Token": "falsch"})[0] == 403)
    pruef("Dienst: ohne Modell 503", get("/profile", MIT) == (503, {"fehler": "Modell lädt noch oder fehlt"}))
    pruef("Dienst: zu gross 413", post("/erkennen", kopf=dict(MIT, **{"Content-Length": str(js.WAV_MAX + 1)}))[0] == 413)
    pruef("Dienst: Laenge kaputt 400", post("/erkennen", kopf=dict(MIT, **{"Content-Length": "viel"}))[0] == 400)
    js.SPRACHE = "en"
    pruef("Dienst: Englisch", get("/profile") == (403, {"fehler": "no access"}))
    js.SPRACHE = "de"
    js.E = types.SimpleNamespace(profile={})                 # Attrappe: Modell geladen, keine Profile
    jetzt = js.time.time()
    js.ZULETZT.append({"person": "mia", "stufe": "sicher", "wert": 0.8, "zeit": jetzt - 100, "text": "Licht an",
                       "vergleich": "licht an", "client": "10.0.0.5"})
    pruef("Dienst: zu alte Erkennung zaehlt nicht", get("/zuletzt?text=Licht+an", MIT)[0] == 404)
    js.ZULETZT.append({"person": "mia", "stufe": "sicher", "wert": 0.8, "zeit": jetzt, "text": "Licht an!",
                       "vergleich": "licht an", "client": "10.0.0.5"})
    c, d = get("/zuletzt?text=Licht%20an", MIT)
    pruef("Dienst: /zuletzt mit client, ohne Vergleichsfeld", c == 200 and d["client"] == "10.0.0.5"
          and "vergleich" not in d and d["person"] == "mia", (c, d))
    pruef("Dienst: anderer Text 404", get("/zuletzt?text=Licht+aus", MIT)[0] == 404)
    pruef("Dienst: /vergessen falscher Name 400", post("/vergessen?person=Mia", kopf=MIT)[0] == 400)
    js.E = None

    class Schreiber:
        geschlossen = False

        def get_extra_info(self, k):
            return ("10.0.0.9", 50000)

        def close(self):
            self.geschlossen = True

    w = Schreiber()
    asyncio.run(js.durchreiche(None, w))
    pruef("Dienst: Durchreiche lehnt fremde Adresse ab", w.geschlossen and any("abgelehnt" in str(x) for x in protokoll),
          protokoll)

    async def lies(roh):
        r = asyncio.StreamReader()
        r.feed_data(roh)
        r.feed_eof()
        return await js.ereignis(r)

    daten = json.dumps({"rate": 16000}).encode()
    roh = json.dumps({"type": "audio-start", "data_length": len(daten), "payload_length": 4}).encode() + b"\n" + daten + b"PCM!"
    e = asyncio.run(lies(roh))
    pruef("Dienst: Wyoming-Ereignis gelesen", e and e[0] == "audio-start" and e[1] == {"rate": 16000} and e[2] == b"PCM!"
          and e[3] == roh, e)
    pruef("Dienst: Wyoming-Ende", asyncio.run(lies(b"")) is None)
    try:
        asyncio.run(lies(json.dumps({"type": "audio-chunk", "payload_length": js.NUTZ_MAX + 1}).encode() + b"\n"))
        pruef("Dienst: zu grosses Ereignis abgelehnt", False)
    except js.Zuviel:
        pruef("Dienst: zu grosses Ereignis abgelehnt", True)

    if os.name == "posix":
        # Profil-Ordner (biometrische Daten, Pruefung 05.11.2026): neu 700 auch bei Umask 0, vorhandener eigener auf 700
        import shutil
        import stat
        import tempfile
        tmp = tempfile.mkdtemp(prefix="sprecher-profile-")
        alte_umask = os.umask(0)
        try:
            neu = os.path.join(tmp, "profile")
            r = js.profil_ordner(neu)
            pruef("Dienst: neuer Profil-Ordner 700 (Umask 0)", r == 0o700 and stat.S_IMODE(os.stat(neu).st_mode) == 0o700,
                  oct(os.stat(neu).st_mode))
            os.chmod(neu, 0o755)
            r = js.profil_ordner(neu)
            pruef("Dienst: eigener vorhandener Ordner wird 700", r == 0o700 and stat.S_IMODE(os.stat(neu).st_mode) == 0o700,
                  oct(os.stat(neu).st_mode))
            os.chmod(neu, 0o750)
            protokoll.clear()
            echt_getuid = js.os.getuid
            js.os.getuid = lambda: echt_getuid() + 1          # so tun, als gehoere er einem anderen Konto
            try:
                r = js.profil_ordner(neu)
            finally:
                js.os.getuid = echt_getuid
            pruef("Dienst: fremder Ordner bleibt, steht im Protokoll", r == 0o750
                  and any("anderen Konto" in str(x) for x in protokoll), (oct(r or 0), protokoll))
        finally:
            os.umask(alte_umask)
            shutil.rmtree(tmp, ignore_errors=True)

print("Sprecher: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
