#!/usr/bin/env python3
"""Baustein kalender_abo.py (private iCal-Kalender abonnieren, seit 0.7). Beispiel: ein Schichtplan aus einer
Schicht-App, die in einen Google-Kalender exportiert. Prueft Konfiguration, Rechte der Adressdatei, nur https, keine
privaten/lokalen Ziele (auch nach Weiterleitung), Groessenlimit, Schutz der letzten guten Datei, keine Adresse in
Fehlertexten, alle_holen und die Texte auf Englisch. Abruf und DNS sind Attrappen; die Bindung an die gepruefte
Adresse wird gegen einen Socket auf 127.0.0.1 geprueft (kein Netz nach draussen)."""
import io
import json
import os
import re
import socket
import stat
import sys
import tempfile
import threading
import urllib.error
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import kalender_abo as ka  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:300]) if info and not bed else ""))


T = tempfile.mkdtemp(prefix="kalender-abo-")
ADR = os.path.join(T, "schichtplan_ical")
AUSGABE = os.path.join(T, "ausgabe")
os.makedirs(AUSGABE)
ZIEL = os.path.join(AUSGABE, "schichtplan.ics")
SCHLUESSEL = "0123456789abcdef0123456789abcdef"
GEHEIM = ("https://calendar.google.com/calendar/ical/abc123%40group.calendar.google.com/private-" + SCHLUESSEL
          + "/basic.ics")
KAL = (b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nDTSTART:20261109T044000Z\r\nDTEND:20261109T124000Z\r\n"
       b"SUMMARY:Frueh\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20261107\r\nDTEND;VALUE=DATE:20261108\r\n"
       b"SUMMARY:Frei\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
OEFFENTLICH = {"calendar.google.com": ["142.250.185.78", "2a00:1450:4001:82a::200e"], "cdn.example.net": ["93.184.216.34"],
               "kalender.example.org": ["93.184.216.35"], "intern.example.net": ["192.168.1.20"]}
aufgeloest = []


def aufl(tabelle=None):
    tab = dict(OEFFENTLICH, **(tabelle or {}))

    def aufloesen(host):
        aufgeloest.append(host)
        if host not in tab:
            raise socket.gaierror(-2, "Name or service not known: " + host)
        return tab[host]
    return aufloesen


def adresse(url, rechte=0o600, pfad=ADR):
    with open(pfad, "w") as f:
        f.write(url + "\n")
    os.chmod(pfad, rechte)


class Antwort(io.BytesIO):
    pass


def liefert(daten, weiter=None):
    """oeffnen-Attrappe: weiter = {url: (code, Location)} fuer Weiterleitungen, sonst die Daten."""
    gesehen = []

    def oeffnen(req, timeout=None):
        gesehen.append((req.full_url, req.get_header("User-agent"), timeout))
        if weiter and req.full_url in weiter:
            code, ziel = weiter[req.full_url]
            raise urllib.error.HTTPError(req.full_url, code, "Moved " + req.full_url,
                                         {"Location": ziel} if ziel is not None else {}, None)
        return Antwort(daten)
    return oeffnen, gesehen


def wirft(fehlerobjekt):
    def oeffnen(req, timeout=None):
        raise fehlerobjekt
    return oeffnen


def fehlertext(**kw):
    kw.setdefault("aufloesen", aufl())
    try:
        ka.holen(ADR, ZIEL, **kw)
    except ka.AboFehler as e:
        return str(e)
    except Exception as e:                       # noqa: BLE001
        return "ANDERER FEHLER %s %s" % (type(e).__name__, e)
    return None


def ohne_adresse(t):
    return t is not None and not t.startswith("ANDERER") and "private-" not in t and SCHLUESSEL not in t \
        and "google" not in t and "example" not in t and "://" not in t


# ---------------------------------------------------------------- Konfiguration
K = os.path.join(T, "kalender_abos.json")
pruef("K1 ohne Konfiguration: Funktion aus", ka.konfig_laden(K) == ({}, []))
open(K, "w").write("{kaputt")
try:
    ka.konfig_laden(K)
    pruef("K2 kaputte Konfiguration: Fehler", False)
except ka.AboFehler as e:
    pruef("K2 kaputte Konfiguration: Fehler", "unlesbar" in str(e), str(e))
json.dump(["schichtplan"], open(K, "w"))
try:
    ka.konfig_laden(K)
    pruef("K3 Liste statt Objekt: Fehler", False)
except ka.AboFehler as e:
    pruef("K3 Liste statt Objekt: Fehler", "kein Objekt" in str(e), str(e))
json.dump({"schichtplan": "schichtplan_ical", "Verein": "x", "../boese": "x", "ok-2": "/abs/pfad", "leer": "",
           "zahl": 7, "x" * 41: "y"}, open(K, "w"))
abos, abgelehnt = ka.konfig_laden(K)
pruef("K4 Namen nur a-z 0-9 _ -, relative Pfade neben der Konfiguration", abos == {"schichtplan": ADR, "ok-2": "/abs/pfad"}
      and sorted(abgelehnt) == sorted(["Verein", "../boese", "leer", "zahl", "x" * 40]), (abos, abgelehnt))

# ---------------------------------------------------------------- Adressdatei
oeffnen, gesehen = liefert(KAL)
pruef("A1 ohne Adressdatei: verstaendlicher Fehler", fehlertext(oeffnen=oeffnen) == "keine Adresse hinterlegt")
adresse(GEHEIM, 0o644)
pruef("A2 Adressdatei fuer andere lesbar: abgelehnt, nichts abgerufen",
      fehlertext(oeffnen=oeffnen) == "Adressdatei ist für andere lesbar (Rechte 600 setzen)" and gesehen == [], gesehen)
os.chmod(ADR, 0o640)
pruef("A3 auch nur Gruppe lesbar: abgelehnt", fehlertext(oeffnen=oeffnen) == "Adressdatei ist für andere lesbar (Rechte 600 setzen)")
os.remove(ADR)
os.mkdir(ADR)
pruef("A4 Verzeichnis statt Datei: abgelehnt", fehlertext(oeffnen=oeffnen) == "Adressdatei ist keine normale Datei"
      and not os.path.exists(ZIEL))
os.rmdir(ADR)

# ---------------------------------------------------------------- Adressen: nur https, nichts im Heimnetz
SCHLECHT = {"http://calendar.example.org/k.ics": "nur https-Adressen", "ftp://kalender.example.org/k.ics": "nur https-Adressen",
            "file:///etc/passwd": "nur https-Adressen", "kaputt": "nur https-Adressen",
            "https://localhost/k.ics": "Ziel im Heimnetz abgelehnt", "https://127.0.0.1/k.ics": "Ziel im Heimnetz abgelehnt",
            "https://[::1]/k.ics": "Ziel im Heimnetz abgelehnt", "https://192.168.1.10/k.ics": "Ziel im Heimnetz abgelehnt",
            "https://10.1.2.3:8443/k.ics": "Ziel im Heimnetz abgelehnt", "https://nas/k.ics": "Ziel im Heimnetz abgelehnt",
            "https://router.fritz.box/k.ics": "Ziel im Heimnetz abgelehnt", "https://drucker.local/k.ics": "Ziel im Heimnetz abgelehnt",
            "https://server.home.arpa/k.ics": "Ziel im Heimnetz abgelehnt", "https://[fe80::1]/k.ics": "Ziel im Heimnetz abgelehnt",
            "https://169.254.169.254/latest": "Ziel im Heimnetz abgelehnt", "https://0.0.0.0/k.ics": "Ziel im Heimnetz abgelehnt",
            "https://user:pw@kalender.example.org/k.ics": "keine Zugangsdaten in der Adresse",
            "https://kalender.example.org@10.0.0.1/k.ics": "keine Zugangsdaten in der Adresse",
            "https://kalender.example.org:99999/k.ics": "Adresse hat nicht die erwartete Form",
            "https://kalender.example.org/k.ics x": "Adresse hat nicht die erwartete Form",
            "https://intern.example.net/k.ics": "Ziel im Heimnetz abgelehnt",
            "https://unbekannt.example.net/k.ics": "Name nicht auflösbar"}
falsch = []
for url, erwartet in SCHLECHT.items():
    adresse(url)
    oeffnen, gesehen = liefert(KAL)
    t = fehlertext(oeffnen=oeffnen)
    if t != erwartet or gesehen or not ohne_adresse(t):
        falsch.append((url, t, gesehen))
pruef("U1 %d schlechte Adressen abgelehnt, nichts abgerufen, Fehler ohne Adresse" % len(SCHLECHT), not falsch, falsch)
AUFGELOEST_SCHLECHT = {"privat": ["10.0.0.5"], "gemischt": ["93.184.216.34", "192.168.1.2"], "link-local v6": ["fe80::1%eth0"],
                       "v4 in v6": ["::ffff:127.0.0.1"], "CGNAT": ["100.64.1.1"], "link-local v4": ["169.254.1.1"],
                       "ULA": ["fd00::5"], "Doku-Netz": ["203.0.113.7"], "leer": [], "Unsinn": ["kein-ip"]}
falsch = []
adresse("https://kalender.example.org/abo.ics")
for name, ips in AUFGELOEST_SCHLECHT.items():
    oeffnen, gesehen = liefert(KAL)
    t = fehlertext(oeffnen=oeffnen, aufloesen=aufl({"kalender.example.org": ips}))
    if t not in ("Ziel im Heimnetz abgelehnt", "Name nicht auflösbar") or gesehen:
        falsch.append((name, t))
pruef("U2 Name loest privat/lokal/link-local auf (auch nur eine von mehreren Adressen): abgelehnt", not falsch, falsch)
pruef("U3 Pruefung der Adressen direkt", ka.adresse_erlaubt("93.184.216.34") and ka.adresse_erlaubt("2606:4700:4700::1111")
      and not any(ka.adresse_erlaubt(a) for a in ("127.0.0.1", "10.0.0.1", "172.16.5.4", "192.168.0.1", "fe80::1",
                                                  "fe80::1%eth0", "::1", "::ffff:8.8.8.8", "2002::1", "224.0.0.1", "")))

# ---------------------------------------------------------------- Abruf: jede https-Adresse, nicht nur Google
adresse("https://kalender.example.org/abo.ics")
oeffnen, gesehen = liefert(KAL)
erg = ka.holen(ADR, ZIEL, oeffnen=oeffnen, aufloesen=aufl())
pruef("H1 andere https-Adresse (nicht Google): geschrieben, 2 Termine", erg == (True, 2) and gesehen[0][0]
      == "https://kalender.example.org/abo.ics" and gesehen[0][1] == "jarvis-kalender-abo/1", (erg, gesehen))
pruef("H1b Zeitlimit wird mitgegeben", 0 < gesehen[0][2] <= ka.ZEITLIMIT_S, gesehen)
os.remove(ZIEL)
adresse(GEHEIM)
oeffnen, gesehen = liefert(KAL)
aufgeloest.clear()
erg = ka.holen(ADR, ZIEL, oeffnen=oeffnen, aufloesen=aufl())
pruef("H2 Google-Adresse: abgerufen wird genau die hinterlegte Adresse", erg == (True, 2) and [g[0] for g in gesehen] == [GEHEIM]
      and aufgeloest == ["calendar.google.com"], (erg, gesehen, aufgeloest))
pruef("H3 Datei nur fuer den Besitzer (600), Inhalt unveraendert, keine Zwischendatei",
      stat.S_IMODE(os.stat(ZIEL).st_mode) == 0o600 and open(ZIEL, "rb").read() == KAL
      and not [n for n in os.listdir(AUSGABE) if n != "schichtplan.ics"], os.listdir(AUSGABE))
m = os.stat(ZIEL).st_mtime_ns
os.utime(ZIEL, ns=(m - 10 ** 9, m - 10 ** 9))
erg = ka.holen(ADR, ZIEL, oeffnen=liefert(KAL)[0], aufloesen=aufl())
pruef("H4 gleicher Inhalt: nicht neu geschrieben", erg == (False, 2) and os.stat(ZIEL).st_mtime_ns == m - 10 ** 9, erg)
adresse("https://[2606:4700:4700::1111]/k.ics")
pruef("H5 oeffentliche IPv6-Adresse in der URL erlaubt (ohne DNS)",
      ka.holen(ADR, ZIEL, oeffnen=liefert(KAL)[0], aufloesen=aufl()) == (False, 2))
adresse(GEHEIM)

# ---------------------------------------------------------------- Kaputte Antworten
for name, daten in (("HTML-Seite", b"<html>Anmelden</html>"), ("leer", b""), ("abgeschnitten", KAL[:60]),
                    ("Kalender nur mittendrin", b"<html>" + KAL), ("ohne Ende", KAL.replace(b"END:VCALENDAR", b""))):
    t = fehlertext(oeffnen=liefert(daten)[0])
    pruef("F1 kaputte Antwort (%s): Fehler, alte Datei bleibt" % name,
          t == "Antwort ist keine Kalenderdatei" and open(ZIEL, "rb").read() == KAL, t)
gross = b"BEGIN:VCALENDAR\r\n" + b"X" * (ka.MAX_BYTES + 10) + b"END:VCALENDAR\r\n"
t = fehlertext(oeffnen=liefert(gross)[0])
pruef("F2 zu gross: Fehler, alte Datei bleibt", t == "Antwort größer als 5 MB" and open(ZIEL, "rb").read() == KAL, t)
mit_bom = b"\xef\xbb\xbf" + KAL.replace(b"Frueh", b"Spaet")
pruef("F3 Kalender mit BOM wird angenommen", ka.holen(ADR, ZIEL, oeffnen=liefert(mit_bom)[0], aufloesen=aufl()) == (True, 2)
      and open(ZIEL, "rb").read() == mit_bom)
KAL2 = KAL.replace(b"SUMMARY:Frueh", b"SUMMARY:Nacht")
pruef("F4 geaenderter Plan wird uebernommen", ka.holen(ADR, ZIEL, oeffnen=liefert(KAL2)[0], aufloesen=aufl()) == (True, 2)
      and open(ZIEL, "rb").read() == KAL2)
open(ZIEL + ".neu", "w").write("Rest")
os.chmod(ZIEL + ".neu", 0o644)
pruef("F5 Rest eines abgebrochenen Laufs stoert nicht", ka.holen(ADR, ZIEL, oeffnen=liefert(KAL)[0], aufloesen=aufl())
      == (True, 2) and not os.path.exists(ZIEL + ".neu") and stat.S_IMODE(os.stat(ZIEL).st_mode) == 0o600)

# ---------------------------------------------------------------- Fehlertexte nennen nie die Adresse
falsch = []
for name, f in (("HTTP 404", urllib.error.HTTPError(GEHEIM, 404, "Not Found " + GEHEIM, {}, None)),
                ("HTTP 500", urllib.error.HTTPError(GEHEIM, 500, GEHEIM, {"X": GEHEIM}, None)),
                ("URLError", urllib.error.URLError("getaddrinfo failed for " + GEHEIM)),
                ("URLError Zeit", urllib.error.URLError(socket.timeout("timed out " + GEHEIM))),
                ("Zeitueberschreitung", socket.timeout("timed out " + GEHEIM)),
                ("OSError", OSError("kaputt " + GEHEIM)), ("ValueError", ValueError(GEHEIM)),
                ("Verbindung abgelehnt", ConnectionRefusedError(111, GEHEIM))):
    t = fehlertext(oeffnen=wirft(f))
    if not ohne_adresse(t):
        falsch.append((name, t))
pruef("E1 Fehlertexte ohne Adresse, Rechnernamen und Schluessel", not falsch, falsch)
pruef("E2 HTTP-Code und Fehlerart stehen im Text",
      fehlertext(oeffnen=wirft(urllib.error.HTTPError(GEHEIM, 404, "x", {}, None))) == "Server antwortet mit 404"
      and fehlertext(oeffnen=wirft(socket.timeout("x"))) == "Zeitüberschreitung"
      and fehlertext(oeffnen=wirft(urllib.error.URLError(ConnectionRefusedError()))) == "Verbindung abgelehnt"
      and fehlertext(oeffnen=wirft(urllib.error.URLError("x"))) == "nicht erreichbar (str)")
pruef("E3 nach allen Fehlern: letzte gute Datei unveraendert", open(ZIEL, "rb").read() == KAL)

# ---------------------------------------------------------------- Weiterleitungen
CDN = "https://cdn.example.net/k.ics"
oeffnen, gesehen = liefert(KAL2, {GEHEIM: (302, CDN)})
aufgeloest.clear()
erg = ka.holen(ADR, ZIEL, oeffnen=oeffnen, aufloesen=aufl())
pruef("W1 Weiterleitung zu oeffentlichem https-Ziel: gefolgt, beide Namen geprueft", erg == (True, 2)
      and [g[0] for g in gesehen] == [GEHEIM, CDN] and aufgeloest == ["calendar.google.com", "cdn.example.net"],
      (erg, gesehen, aufgeloest))
oeffnen, gesehen = liefert(KAL, {GEHEIM: (301, "/calendar/ical/neu.ics")})
erg = ka.holen(ADR, ZIEL, oeffnen=oeffnen, aufloesen=aufl())
pruef("W2 relative Weiterleitung wird aufgeloest", erg == (True, 2)
      and gesehen[1][0] == "https://calendar.google.com/calendar/ical/neu.ics", gesehen)
falsch = []
for ziel, erwartet in (("http://cdn.example.net/k.ics", "nur https-Adressen"),
                       ("https://10.0.0.1/k.ics", "Ziel im Heimnetz abgelehnt"),
                       ("https://localhost:8123/api", "Ziel im Heimnetz abgelehnt"),
                       ("https://intern.example.net/k.ics", "Ziel im Heimnetz abgelehnt"),
                       ("https://[::ffff:192.168.1.1]/k.ics", "Ziel im Heimnetz abgelehnt"),
                       ("file:///etc/passwd", "nur https-Adressen"), (None, "Weiterleitung ohne Ziel"),
                       ("  ", "Weiterleitung ohne Ziel")):
    for code in (302, 307):
        oeffnen, gesehen = liefert(KAL2, {GEHEIM: (code, ziel)})
        t = fehlertext(oeffnen=oeffnen)
        if t != erwartet or len(gesehen) != 1 or open(ZIEL, "rb").read() != KAL or not ohne_adresse(t):
            falsch.append((ziel, code, t, len(gesehen)))
pruef("W3 Weiterleitung zu http, Heimnetz oder ohne Ziel: abgelehnt, nicht abgerufen, alte Datei bleibt", not falsch, falsch)
kette = {GEHEIM: (302, "https://cdn.example.net/1")}
kette.update({"https://cdn.example.net/%d" % i: (302, "https://cdn.example.net/%d" % (i + 1)) for i in range(1, 20)})
oeffnen, gesehen = liefert(KAL2, kette)
t = fehlertext(oeffnen=oeffnen)
pruef("W4 zu viele Weiterleitungen: abgebrochen nach %d Abrufen" % (ka.MAX_WEITERLEITUNGEN + 1),
      t == "zu viele Weiterleitungen" and len(gesehen) == ka.MAX_WEITERLEITUNGEN + 1 and open(ZIEL, "rb").read() == KAL,
      (t, len(gesehen)))

# ---------------------------------------------------------------- alle_holen
ADR2 = os.path.join(T, "verein_ical")
json.dump({"schichtplan": ADR, "verein": "verein_ical", "fehlt": "gibts_nicht", "Böse": "x"}, open(K, "w"))
adresse("https://kalender.example.org/verein.ics", pfad=ADR2)
os.remove(ZIEL)
logs = []
oeffnen = liefert(KAL)[0]
erg = ka.alle_holen(K, AUSGABE, oeffnen=oeffnen, aufloesen=aufl(), log=lambda *a: logs.append(" ".join(map(str, a))))
pruef("L1 alle Abos geholt, Fehler einzeln, ungueltiger Name gemeldet",
      erg == {"schichtplan": {"geaendert": True, "termine": 2}, "verein": {"geaendert": True, "termine": 2},
              "fehlt": {"fehler": "keine Adresse hinterlegt"}, "Böse": {"fehler": "Name nicht erlaubt (a-z, 0-9, _ und -)"}}
      and sorted(os.listdir(AUSGABE)) == ["schichtplan.ics", "verein.ics"], (erg, os.listdir(AUSGABE)))
pruef("L2 Log nennt Namen und Fehlerart, nie eine Adresse", logs and all(ohne_adresse(z) for z in logs)
      and any("Kalender-Abo fehlt: keine Adresse hinterlegt" == z for z in logs), logs)
erg = ka.alle_holen(K, AUSGABE, oeffnen=oeffnen, aufloesen=aufl())
pruef("L3 zweiter Lauf: nichts geaendert", erg["schichtplan"] == {"geaendert": False, "termine": 2}
      and erg["verein"] == {"geaendert": False, "termine": 2})
erg = ka.alle_holen(K, os.path.join(T, "gibts_nicht"), oeffnen=oeffnen, aufloesen=aufl())
pruef("L4 Zielordner fehlt: jedes Abo meldet es, nichts angelegt", erg["schichtplan"] == {"fehler": "Zielordner fehlt"}
      and not os.path.exists(os.path.join(T, "gibts_nicht")), erg)
pruef("L5 ohne Konfiguration: nichts zu tun", ka.alle_holen(os.path.join(T, "fehlt.json"), AUSGABE, oeffnen=oeffnen) == {})
pruef("L6 Beispielname ist kein 'arbeit…' (der Kalender-Leser der Vorlage behandelt die als Platzhalter-Schichten)",
      not "schichtplan".startswith("arbeit") and "arbeit" in ka.__doc__)

# ---------------------------------------------------------------- Bindung an die gepruefte Adresse (nur 127.0.0.1)
NAME_X = "kalender.example.invalid"


def lauscher():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(5)
    s.settimeout(10)
    empfangen = []

    def annehmen():
        try:
            c, _ = s.accept()
            c.settimeout(5)
            empfangen.append(c.recv(4096))
            c.close()
        except OSError:
            pass
        finally:
            s.close()
    th = threading.Thread(target=annehmen, daemon=True)
    th.start()
    return s.getsockname()[1], empfangen, th


alt_proxy = {k: os.environ.get(k) for k in ("https_proxy", "HTTPS_PROXY", "no_proxy")}
os.environ.update({"https_proxy": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "no_proxy": ""})
port, empfangen, th = lauscher()
try:
    ka._oeffner(["127.0.0.1"]).open(urllib.request.Request("https://%s:%d/k.ics" % (NAME_X, port)), timeout=10)
    erg = "kein Fehler"
except Exception as e:                           # noqa: BLE001 - der Lauscher spricht kein TLS
    erg = type(e).__name__
th.join(10)
pruef("P1 Verbindung geht an die gepruefte Adresse (kein DNS, kein Proxy aus der Umgebung), TLS mit dem Namen (SNI)",
      len(empfangen) == 1 and NAME_X.encode() in empfangen[0] and erg != "kein Fehler", (erg, empfangen[:1]))
port, empfangen, th = lauscher()
try:
    ka._oeffner(["127.0.0.1"]).open("http://127.0.0.1:%d/k.ics" % port, timeout=5)
    erg = "kein Fehler"
except urllib.error.URLError as e:
    erg = str(e.reason)
th.join(0.5)
pruef("P2 der Oeffner selbst spricht kein http", erg == "nur https" and not empfangen, (erg, empfangen))
# Ganzer Weg ueber holen() ohne eingespritztes oeffnen: Adresspruefung fuer diesen einen Fall auf 127.0.0.1 erlaubt
echt_erlaubt = ka.adresse_erlaubt
ka.adresse_erlaubt = lambda ip: ip == "127.0.0.1"
port, empfangen, th = lauscher()
adresse("https://%s:%d/k.ics" % (NAME_X, port))
aufgeloest.clear()
t = fehlertext(aufloesen=aufl({NAME_X: ["127.0.0.1"]}), timeout=10)
th.join(10)
ka.adresse_erlaubt = echt_erlaubt
for k, v in alt_proxy.items():
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v
pruef("P3 holen() ohne Attrappe: genau eine Aufloesung, Verbindung an diese Adresse, Fehler ohne Namen",
      aufgeloest == [NAME_X] and len(empfangen) == 1 and NAME_X.encode() in empfangen[0] and t is not None
      and ohne_adresse(t) and NAME_X not in t and open(ZIEL, "rb").read() == KAL, (t, aufgeloest))
pruef("P4 Adresspruefung danach wieder streng", not ka.adresse_erlaubt("127.0.0.1"))

# ---------------------------------------------------------------- Englisch
try:
    ka.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", True)
ka.setze_sprache("en")
en = []
os.remove(ADR)
en.append(fehlertext(oeffnen=liefert(KAL)[0]))
adresse(GEHEIM, 0o644)
en.append(fehlertext(oeffnen=liefert(KAL)[0]))
for url in ("http://kalender.example.org/k.ics", "https://192.168.1.10/k.ics", "https://user:pw@kalender.example.org/k.ics",
            "https://unbekannt.example.net/k.ics"):
    adresse(url)
    en.append(fehlertext(oeffnen=liefert(KAL)[0]))
adresse(GEHEIM)
en += [fehlertext(oeffnen=wirft(urllib.error.HTTPError(GEHEIM, 404, "x", {}, None))),
       fehlertext(oeffnen=wirft(socket.timeout("x"))), fehlertext(oeffnen=wirft(urllib.error.URLError("x"))),
       fehlertext(oeffnen=liefert(b"<html>")[0]), fehlertext(oeffnen=liefert(gross)[0]),
       fehlertext(oeffnen=liefert(KAL, {GEHEIM: (302, None)})[0]), fehlertext(oeffnen=liefert(KAL2, kette)[0])]
erwartet = ["no address stored", "address file is readable by others (set permissions to 600)", "only https addresses",
            "target in the home network refused", "no credentials in the address", "name does not resolve",
            "server responded with 404", "timeout", "not reachable (str)", "response is not a calendar file",
            "response larger than 5 MB", "redirect without target", "too many redirects"]
pruef("EN: Fehlertexte englisch", en == erwartet, [x for x in zip(en, erwartet) if x[0] != x[1]])
erg = ka.alle_holen(K, AUSGABE, oeffnen=liefert(KAL)[0], aufloesen=aufl())
pruef("EN: alle_holen", erg["Böse"] == {"fehler": "name not allowed (a-z, 0-9, _ and -)"}
      and erg["fehlt"] == {"fehler": "no address stored"}, erg)
deutsch = [m for m in en + [erg["Böse"]["fehler"]] if re.search(r"[äöüÄÖÜß]|\b(nicht|keine?|Adresse|Datei|Ziel|ist)\b", m)]
pruef("EN: kein deutscher Rest", not deutsch, deutsch)
ka.setze_sprache("de")
pruef("Zurueck auf Deutsch", fehlertext(oeffnen=liefert(b"x")[0]) == "Antwort ist keine Kalenderdatei")

import shutil  # noqa: E402
shutil.rmtree(T, ignore_errors=True)
print("Kalender-Abo: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
