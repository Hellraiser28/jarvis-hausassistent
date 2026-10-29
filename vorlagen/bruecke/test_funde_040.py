#!/usr/bin/env python3
"""Funde der unabhaengigen Pruefung von 0.4 (Release-Module): TLS mit Zertifikatspruefung, Personen ohne Ausweichen
auf die Hauptperson, Besitz und genaue Namen bei Szenen, Grenzen beim Vergessen, Kontext-Budget, Import-Konflikte,
Fristen-Obergrenze, MIME-Typ, Dateisperre unter Windows. Ohne Netz, Testordner statt echter Daten."""
import json
import os
import shutil
import ssl
import sys
import tempfile
import types

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HIER), "bruecke"))
import briefe  # noqa: E402
import gedaechtnis as gd  # noqa: E402
import personen as pe  # noqa: E402
import postfach  # noqa: E402
import szenen as sz  # noqa: E402

T = tempfile.mkdtemp(prefix="funde-test-")
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    if bed:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name, str(info)[:300])


def wirft(f, *a, **k):
    try:
        f(*a, **k)
    except Exception as e:      # noqa: BLE001 - hier zaehlt nur, dass und was geworfen wird
        return "%s: %s" % (type(e).__name__, e)
    return ""


# ---------------------------------------------------------------- Fund 1: TLS
k = postfach.tls_kontext()
pruef("TLS: Zertifikat wird geprueft", k.verify_mode == ssl.CERT_REQUIRED)
pruef("TLS: Hostname wird geprueft", k.check_hostname is True)
gesehen = {}


class Attrappe(postfach._IMAP):
    def __init__(self, host, port, ssl_context=None):
        gesehen["kontext"] = ssl_context
        raise OSError("kein Netz im Test")


echt = postfach._IMAP
postfach._IMAP = Attrappe
pruef("TLS: verbunden() uebergibt einen pruefenden Kontext",
      "nicht erreichbar" in wirft(lambda: postfach.verbunden({"server": "x", "port": 993}).__enter__())
      and gesehen.get("kontext") is not None and gesehen["kontext"].verify_mode == ssl.CERT_REQUIRED)
postfach._IMAP = echt
class AttrappeOhneTLS(postfach._IMAP):
    def __init__(self, host, port, ssl_context=None):
        raise ssl.SSLError(1, "WRONG_VERSION_NUMBER")


postfach._IMAP = AttrappeOhneTLS
pruef("TLS: Server ohne TLS heisst nicht 'Zertifikat ungueltig'",
      "Keine sichere Verbindung" in wirft(lambda: postfach.verbunden({"server": "x", "port": 143}).__enter__()))
postfach._IMAP = echt
import contextlib  # noqa: E402
echt_verbunden, echt_finden, echt_teilen = postfach.verbunden, postfach.ordner_finden, postfach._id_teilen
postfach.verbunden = contextlib.contextmanager(lambda z: (yield object()))
postfach.ordner_finden = lambda m, w: ({"name": "Spamverdacht", "roh": "Spam", "flags": {"\\Junk"}} if "spam" in w.lower()
                                       else {"name": "Posteingang", "roh": "INBOX", "flags": set()})
postfach._id_teilen = lambda k: ("posteingang", 5)
pruef("Spam: ohne Nennung abgelehnt", "Spam-Ordner verschiebe ich nur" in wirft(postfach.verschieben, {}, "INBOX:5", "Spam"))
pruef("Spam: mit spam_erlaubt geht es an der Pruefung vorbei",
      "Spam-Ordner" not in wirft(postfach.verschieben, {}, "INBOX:5", "Spam", spam_erlaubt=True))
postfach.verbunden, postfach.ordner_finden, postfach._id_teilen = echt_verbunden, echt_finden, echt_teilen
pruef("TLS: kein globaler Socket-Standard mehr", "setdefaulttimeout(" not in open(postfach.__file__, encoding="utf-8").read())

# ---------------------------------------------------------------- Fund 2 und 10: Personen
D = os.path.join(T, "p")
os.makedirs(D)
pruef("Personen: ohne Datei nur die Hauptperson", pe.laden(D) == pe.STANDARD)
open(os.path.join(D, "personen.json"), "w").write('{"alex": {"rolle": "haupt"},}')
P = pe.laden(D)
pruef("Personen: kaputte Datei heisst niemand", P == {} and pe.haupt(P) is None, P)
pruef("Personen: kaputte Datei, Hauptschluessel ohne Person", pe.fuer_geraet(P, [], "haupt") is None)
pruef("Personen: niemand darf etwas", not pe.darf(P, None, "wetter") and not pe.ist_haupt(P, None) and pe.name(P, None) == "")
json.dump({"sam": {"name": "Sam", "rolle": "familie"}}, open(os.path.join(D, "personen.json"), "w"))
pruef("Personen: ohne Hauptperson heisst niemand", pe.laden(D) == {})
json.dump({"alex": {"name": "Alex", "rolle": "haupt"}, "sam": {"name": "Sam", "rolle": "familie"}},
          open(os.path.join(D, "personen.json"), "w"))
P = pe.laden(D)
G = [{"id": "aa11bb", "person": "sam"}, {"id": "cc22dd", "person": "kim"}, {"id": "dd33ee"}]
pruef("Personen: Geraet mit unbekannter Person bekommt niemanden", pe.fuer_geraet(P, G, "cc22dd") is None)
pruef("Personen: Geraet ohne Person ist die Hauptperson", pe.fuer_geraet(P, G, "dd33ee") == "alex")
pruef("Personen: Familie aendert keine Nachrichtenquellen", not pe.darf(P, "sam", "nachrichtenquellen"))

# ---------------------------------------------------------------- Fund 3 und 18: Szenen
S = os.path.join(T, "s")
os.makedirs(S)
LICHT = {"werkzeug": "geraet_steuern", "argumente": {"entity_id": "light.flur", "dienst": "turn_off"}}
a, _ = sz.speichern(S, "Gute Nacht", [LICHT], "alex")
kino, _ = sz.speichern(S, "Kino", [LICHT], "sam")
pruef("Szenen: fremde Szene gleichen Namens nicht ersetzen", "jemand anderes" in wirft(sz.speichern, S, "gute nacht", [LICHT], "sam"))
pruef("Szenen: Hauptperson darf ersetzen", sz.speichern(S, "Kino", [LICHT, LICHT], "alex", haupt=True)[1] is False)
pruef("Szenen: fremde nicht loeschen", "jemand anderes" in wirft(sz.loeschen, S, "Gute Nacht", "sam"))
pruef("Szenen: fremde nicht umbenennen", "jemand anderes" in wirft(sz.umbenennen, S, a["id"], "x", "sam"))
pruef("Szenen: fremden Schritt nicht entfernen", "jemand anderes" in wirft(sz.schritt_entfernen, S, a["id"], 1, "sam"))
pruef("Szenen: Loeschen trifft nur genaue Namen", sz.loeschen(S, "Kinoabend", "sam") is None
      and any(x["name"] == "Kino" for x in sz.laden(S)))
pruef("Szenen: Starten findet weiter Namensteile", sz.finden(sz.laden(S), "Gute Nacht bitte")["id"] == a["id"])
pruef("Szenen: Schrittnummer kein Absturz", "gibt es nicht" in wirft(sz.schritt_entfernen, S, kino["id"], "zwei", "sam"))
pruef("Szenen: sekunden als Text", "Zahl" in wirft(sz.schritte_pruefen, [{"werkzeug": "warten", "argumente": {"sekunden": "lang"}}]))
pruef("Szenen: daten kein Objekt", "Objekt" in wirft(sz.schritte_pruefen, [{"werkzeug": "geraet_steuern", "argumente": {
    "entity_id": "light.x", "dienst": "turn_on", "daten": "hell"}}]))
pruef("Szenen: Beschreibung uebersteht kaputte daten", sz.beschreibung({"werkzeug": "geraet_steuern", "argumente": {
    "entity_id": "light.x", "dienst": "turn_on", "daten": [1]}}, {}) == "light.x: an")
abend, _ = sz.speichern(S, "Abend", [LICHT], "sam")
pruef("Szenen: fremden Namen nicht ueber ersetzt uebernehmen",
      "gibt es schon" in wirft(sz.speichern, S, "Gute Nacht", [LICHT], "sam", ersetzt=abend["id"]))
pruef("Szenen: ersetzt einer verschwundenen Szene", "nicht mehr" in wirft(sz.speichern, S, "X", [LICHT], "sam", ersetzt="s000000"))
pruef("Szenen: eigene Szene ueber ersetzt umbenennen geht", sz.speichern(S, "Abendruhe", [LICHT], "sam", ersetzt=abend["id"])[0]["name"] == "Abendruhe")
pruef("Szenen: zwei gleiche Namen findet finden nicht", sz.finden([{"id": "s1", "name": "A"}, {"id": "s2", "name": "a"}], "a") is None)
fa = {x["name"]: x for x in sz.fuer_app(sz.laden(S), {}, "sam", False, {"alex": "Alex", "sam": "Sam"})}
pruef("Szenen: App sieht aendern je Person", fa["Kino"]["aendern"] is True and fa["Gute Nacht"]["aendern"] is False, fa)
pruef("Szenen: App bekommt den Namen, nicht die Kennung", fa["Gute Nacht"]["von"] == "Alex", fa)
pruef("Szenen: ohne Person darf niemand aendern", not sz.darf_aendern(a, None) and not sz.darf_aendern(a, ""))

# ---------------------------------------------------------------- Fund 11, 14, 17: Gedaechtnis
M = os.path.join(T, "m")
os.makedirs(M)
for i in range(5):
    gd.neu(M, "Haus-Eintrag %d mit e" % i, "haus", "alex")
pruef("Vergessen: zu kurz", "genauer" in wirft(gd.vergessen, M, "sam", "e"))
pruef("Vergessen: zu viele Treffer", "5 Einträge" in wirft(gd.vergessen, M, "sam", "Haus-Eintrag"))
pruef("Vergessen: genauer geht", gd.vergessen(M, "sam", "Haus-Eintrag 3") == 1 and len(gd.laden(M)["eintraege"]) == 4)
gd.neu(M, "Sam mag Tee", "sam", "sam")
k = gd.fuer_kontext(M, "sam", {"alex": "Alex", "sam": "Sam"}, max_zeichen=90)
pruef("Kontext: das Neueste (privat) bleibt bei knappem Platz", "Sam mag Tee" in k, k)
pruef("Kontext: Haus-Eintrag anderer mit Urheber", "(Alex): Haus-Eintrag 4" in k, k)
pruef("Kontext: eigene Haus-Eintraege ohne Urheber", "(Alex)" not in gd.fuer_kontext(M, "alex", {"alex": "Alex", "sam": "Sam"}))
hausnr = gd.laden(M)["eintraege"][0]["id"]
pruef("Mitlernen ersetzt keine Haus-Eintraege", gd.ersetzen(M, hausnr, "gelernt anders", "sam") is False
      and gd.ersetzen(M, hausnr, "von Hand geaendert", "sam", quelle="import") is True)
txt = gd.export_txt(M, "sam", {"sam": "Sam"})
v = gd.import_vergleich(M, "sam", txt.replace("Sam mag Tee", "Sam mag Kaffee"), {"sam": "Sam"})
nr = v["geaendert"][0]["id"]
gd.ersetzen(M, nr, "Sam mag gruenen Tee", "sam")          # nachts dazwischen gelernt
r = gd.import_uebernehmen(M, "sam", v)
pruef("Import: Konflikt wird uebersprungen", r == (0, 0, 0, 1), r)
pruef("Import: gelernter Text bleibt", any(e["text"] == "Sam mag gruenen Tee" for e in gd.laden(M)["eintraege"]))
alt_max = gd.EINTRAEGE_MAX
gd.EINTRAEGE_MAX = len(gd.laden(M)["eintraege"])
pruef("Gedaechtnis voll: neu wirft, statt Altes zu loeschen", "voll" in wirft(gd.neu, M, "noch einer", "sam", "sam"))
gd.EINTRAEGE_MAX = alt_max

# ---------------------------------------------------------------- Fund 11 und 19: Briefe
import datetime as dt  # noqa: E402
F = os.path.join(T, "f")
os.makedirs(F)
briefe.MAX_FRISTEN = 3
morgen = dt.date.today() + dt.timedelta(days=1)
e1 = briefe.neu(F, "sam", morgen, "eins")
briefe.neu(F, "sam", morgen, "zwei")
briefe.neu(F, "sam", morgen, "drei")
pruef("Fristen: offene fallen nie weg", "offene Fristen" in wirft(briefe.neu, F, "sam", morgen, "vier") and len(briefe.laden(F)) == 3)
briefe.erledigt(F, "sam", e1["id"])
briefe.neu(F, "sam", morgen, "vier")
pruef("Fristen: erledigte machen Platz", sorted(x["was"] for x in briefe.laden(F)) == ["drei", "vier", "zwei"])
koerper, _ = briefe._multipart([], ("a.pdf", "text/html\r\nX-Boese: 1", b"%PDF"))
pruef("Multipart: MIME-Typ geprueft", b"X-Boese" not in koerper and b"Content-Type: application/octet-stream" in koerper)
koerper, _ = briefe._multipart([], ("a.pdf", "application/pdf", b"%PDF"))
pruef("Multipart: gueltiger MIME-Typ bleibt", b"Content-Type: application/pdf" in koerper)

# ---------------------------------------------------------------- Fund 6: Sperre unter Windows (nachgestellt)
aufrufe = []
fcntl_echt = sys.modules.get("fcntl")
import builtins  # noqa: E402
imp_echt = builtins.__import__


def ohne_fcntl(name, *a, **k):
    if name == "fcntl":
        raise ImportError("Windows")
    return imp_echt(name, *a, **k)


sys.modules["msvcrt"] = types.SimpleNamespace(LK_LOCK=1, LK_UNLCK=2, locking=lambda fd, art, n: aufrufe.append((art, n)))
builtins.__import__ = ohne_fcntl
try:
    for m in (gd, sz, briefe):
        os.makedirs(os.path.join(T, "w"), exist_ok=True)
        with m._gesperrt(os.path.join(T, "w")):
            pass
    def besetzt(fd, art, n):
        raise OSError(36, "Resource deadlock avoided")
    sys.modules["msvcrt"].locking = besetzt
    besetzt_fehler = []
    for m in (gd, sz, briefe):        # Deskriptor immer schliessen, sonst scheitert unter Windows das Aufraeumen (WinError 32)
        fd = os.open(os.path.join(T, "sperre"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            besetzt_fehler.append(wirft(m._sperren, fd))
        finally:
            os.close(fd)
finally:
    builtins.__import__ = imp_echt
    del sys.modules["msvcrt"]
pruef("Sperre: ohne fcntl ueber msvcrt, mit Freigabe (gedaechtnis, szenen, briefe)", aufrufe == [(1, 1), (2, 1)] * 3, aufrufe)
pruef("Sperre: besetzt heisst Fehler des Moduls, kein roher OSError",
      all(f.startswith("Fehler: Die Datei ist gerade gesperrt") for f in besetzt_fehler), besetzt_fehler)
pruef("Module laden ohne fcntl-Import oben", all("\nimport fcntl" not in open(m.__file__, encoding="utf-8").read()
                                                 for m in (gd, sz, briefe)))

shutil.rmtree(T)
print("Funde 0.4: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
