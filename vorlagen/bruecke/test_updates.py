#!/usr/bin/env python3
"""Baustein updates.py (Update-Zentrale, seit 0.6): Einstellungen aus der Umgebung, Auswahl der Container ueber
Dockhand, Kern-Schutz, Home-Assistant-Updates, optionaler Synology-Teil, Projektquelle und Release Notes, Gesundheit
nach dem Neuerstellen. Dockhand, Home Assistant, GitHub und Docker sind Attrappen, keine Netzzugriffe, keine Wirkung.
Den Ablauf des Einspielens (Zuruf, Kern nur mit Namen in der eigenen Nachricht, HA-Core mit Neustart und Rueckkehr)
prueft die Bruecke selbst."""
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import updates as up  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


# ---------------------------------------------------------------- Einstellungen aus der Umgebung
NAMEN = ("DOCKHAND_ADRESSE", "DOCKHAND_UMGEBUNG", "HA_ADRESSE", "DOCKER_BEFEHL", "UPDATES_DSM")
for k in NAMEN:                          # nur in diesem Testprozess
    os.environ.pop(k, None)
up = importlib.reload(up)
pruef("Standard: Dockhand lokal", up.DOCKHAND == "http://127.0.0.1:3000" and up.DOCKHAND_ENV == 1, up.DOCKHAND)
pruef("Standard: Home Assistant neutral", up.HA == "http://homeassistant.local:8123", up.HA)
pruef("Standard: docker ohne sudo", up.DOCKER == ["docker"], up.DOCKER)
pruef("Standard: Synology-Teil aus", up.DSM is False)
os.environ.update({"DOCKHAND_ADRESSE": "http://10.0.0.2:3866/", "DOCKHAND_UMGEBUNG": "3", "HA_ADRESSE": "http://10.0.0.3/",
                   "DOCKER_BEFEHL": "sudo /usr/local/bin/docker", "UPDATES_DSM": "1"})
up = importlib.reload(up)
pruef("Einstellung: Adressen ohne Schraegstrich am Ende", up.DOCKHAND == "http://10.0.0.2:3866" and up.HA == "http://10.0.0.3",
      (up.DOCKHAND, up.HA))
pruef("Einstellung: Umgebung, Docker-Befehl, DSM", up.DOCKHAND_ENV == 3 and up.DSM is True
      and up.DOCKER == ["sudo", "/usr/local/bin/docker"], (up.DOCKHAND_ENV, up.DOCKER))
for k in NAMEN:
    os.environ.pop(k, None)
up = importlib.reload(up)

# ---------------------------------------------------------------- Kern-Schutz
pruef("KERN: Datenbank und Kern-Dienste erkannt", up.KERN.search("PaperlessNGX-DB") and up.KERN.search("authentik-server")
      and up.KERN.search("immich_postgres") and up.KERN.search("ghcr.io/immich-app/immich-server:release")
      and not up.KERN.search("omnitools") and not up.KERN.search("x/omnitools:latest"))

# ---------------------------------------------------------------- Attrappen fuer Netz und Befehle
ANFRAGEN = []
NETZ = {}                      # Adresse -> (Code, Antwort); Code "weg" = nicht erreichbar


def urlopen_attrappe(req, timeout=None):
    ANFRAGEN.append({"url": req.full_url, "methode": req.get_method(), "daten": req.data,
                     "auth": req.get_header("Authorization"), "zeit": timeout})
    code, body = NETZ.get(req.full_url, (404, {}))
    if code == "weg":
        raise urllib.error.URLError("Verbindung abgelehnt")
    if code != 200:
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b"{}"))
    return io.BytesIO(json.dumps(body).encode())


BEFEHLE = []
AUSGABEN = []                  # nacheinander zurueckgegebene stdout-Texte; Ausnahme-Objekt = wird geworfen


def run_attrappe(befehl, **k):
    BEFEHLE.append(list(befehl))
    a = AUSGABEN.pop(0) if AUSGABEN else ""
    if isinstance(a, Exception):
        raise a
    return subprocess.CompletedProcess(befehl, 0, stdout=a, stderr="")


urllib.request.urlopen = urlopen_attrappe
up.subprocess.run = run_attrappe
up.time.sleep = lambda s: None

# ---------------------------------------------------------------- Dockhand
PRUEFUNG = up.DOCKHAND + "/api/containers/check-updates?env=1"
NETZ[PRUEFUNG] = (200, {"total": 97, "results": [
    {"containerId": "c1", "containerName": "omnitools", "imageName": "x/omnitools:latest", "hasUpdate": True},
    {"containerId": "c2", "containerName": "immich_server", "imageName": "ghcr.io/immich-app/immich-server:release",
     "hasUpdate": True},
    {"containerId": "c3", "containerName": "aktuell", "imageName": "x/aktuell", "hasUpdate": False},
    {"containerId": "c4", "containerName": "system", "imageName": "x/s", "hasUpdate": True, "systemContainer": True},
    {"containerId": "c5", "containerName": "gesperrt", "imageName": "x/g", "hasUpdate": True, "updateDisabled": True},
    {"containerId": "c6", "containerName": "fest", "imageName": "x/f@sha256:ab", "hasUpdate": True, "pinnedToDigest": True},
    {"containerId": "c7", "containerName": "lokal", "imageName": "eigenbau", "hasUpdate": True, "isLocalImage": True}]})
c, gesamt = up.container("dh-token")
a = ANFRAGEN[-1]
pruef("Container: nur echte Updates, ohne System/gesperrt/fest/lokal", [x["name"] for x in c] == ["omnitools", "immich_server"]
      and gesamt == 97, c)
pruef("Container: Kern markiert", [x["kern"] for x in c] == [False, True], c)
pruef("Container: Felder", c[0] == {"id": "c1", "name": "omnitools", "image": "x/omnitools:latest", "kern": False}, c[0])
pruef("Dockhand: POST mit leerem Inhalt, Bearer, Umgebung", a["url"] == PRUEFUNG and a["methode"] == "POST"
      and a["daten"] == b"" and a["auth"] == "Bearer dh-token" and a["zeit"] == 300, a)
NETZ[up.DOCKHAND + "/api/containers/batch-update?env=1"] = (200, {"results": []})
up._dh("/api/containers/batch-update?env=%d" % up.DOCKHAND_ENV, "dh-token", "POST", {"containerIds": ["c1"]}, zeit=1800)
pruef("Dockhand: Daten als JSON", json.loads(ANFRAGEN[-1]["daten"]) == {"containerIds": ["c1"]})
NETZ[PRUEFUNG] = (401, {})
try:
    up.container("falsch")
    pruef("Dockhand: HTTP-Fehler", False)
except up.Fehler as e:
    pruef("Dockhand: HTTP-Fehler", str(e) == "Dockhand antwortet mit HTTP 401.", e)
NETZ[PRUEFUNG] = ("weg", None)
try:
    up.container("dh-token")
    pruef("Dockhand: nicht erreichbar", False)
except up.Fehler as e:
    pruef("Dockhand: nicht erreichbar", str(e) == "Dockhand ist nicht erreichbar (URLError).", e)
up.setze_sprache("en")
try:
    up.container("dh-token")
    pruef("Dockhand: englisch", False)
except up.Fehler as e:
    pruef("Dockhand: englisch", str(e) == "Dockhand is not reachable (URLError).", e)
up.setze_sprache("de")
try:
    up.setze_sprache("fr")
    pruef("Sprache: fr abgelehnt", False)
except ValueError:
    pruef("Sprache: fr abgelehnt", True)
SELBST = up.DOCKHAND + "/api/self-update/check"
NETZ[SELBST] = (200, {"updateAvailable": True, "currentVersion": "1.0.1", "latestVersion": "1.0.2"})
pruef("Dockhand selbst: Update", (up.dockhand_selbst("dh-token") or {}).get("latestVersion") == "1.0.2"
      and ANFRAGEN[-1]["methode"] == "GET")
NETZ[SELBST] = (200, {"updateAvailable": True, "versionOnly": True})
pruef("Dockhand selbst: nur Versionsnummer zaehlt nicht", up.dockhand_selbst("dh-token") is None)
NETZ[SELBST] = (500, {})
pruef("Dockhand selbst: Fehler -> None", up.dockhand_selbst("dh-token") is None)

# ---------------------------------------------------------------- Home Assistant
NETZ[up.HA + "/api/states"] = (200, [
    {"entity_id": "update.home_assistant_core_update", "state": "on",
     "attributes": {"title": "Home Assistant Core", "installed_version": "2026.10.4", "latest_version": "2026.11.0",
                    "release_url": "https://example.org/rel", "release_summary": "x" * 900, "supported_features": 15}},
    {"entity_id": "update.hacs_update", "state": "on",
     "attributes": {"friendly_name": "HACS", "installed_version": "2.0", "latest_version": "2.1", "supported_features": 1}},
    {"entity_id": "update.aktuell", "state": "off", "attributes": {}},
    {"entity_id": "sensor.update_zaehler", "state": "on", "attributes": {}}])
h = up.ha("ha-token")
pruef("HA: nur update.* mit Stand on", [x["id"] for x in h] == ["update.home_assistant_core_update", "update.hacs_update"], h)
pruef("HA: Sicherung aus supported_features (Bit 8)", [x["sicherung"] for x in h] == [True, False], h)
pruef("HA: Titel, Versionen, gekuerzte Zusammenfassung", h[0]["titel"] == "Home Assistant Core" and h[1]["titel"] == "HACS"
      and h[0]["installiert"] == "2026.10.4" and h[0]["neu"] == "2026.11.0" and len(h[0]["zusammenfassung"]) == 600
      and h[1]["url"] == "", h)
pruef("HA: Adresse aus der Einstellung, Bearer", ANFRAGEN[-1]["url"] == "http://homeassistant.local:8123/api/states"
      and ANFRAGEN[-1]["auth"] == "Bearer ha-token", ANFRAGEN[-1])
NETZ[up.HA + "/api/services/update/install"] = (200, [])
up._ha("/api/services/update/install", "ha-token", {"entity_id": "update.hacs_update", "backup": True}, zeit=60)
pruef("HA: Dienstaufruf als POST mit JSON", ANFRAGEN[-1]["methode"] == "POST"
      and json.loads(ANFRAGEN[-1]["daten"]) == {"entity_id": "update.hacs_update", "backup": True})

# ---------------------------------------------------------------- Optionaler Synology-Teil
T = tempfile.mkdtemp(prefix="updates-test-")
INFO = os.path.join(T, "synoinfo.conf")
open(INFO, "w", encoding="utf-8").write('upnpmodelname="x"\npkg_autoupdate_all="yes"\n')
BEFEHLE.clear()
pruef("DSM aus: keine Abfrage", up.dsm() is None and not BEFEHLE)
pruef("DSM aus: Pakete nie automatisch", up.pakete_automatisch(INFO) is False)
up.DSM = True
AUSGABEN[:] = [json.dumps({"success": True, "data": {"update": {"available": True, "version": "DSM 7.4.2"}}})]
d = up.dsm()
pruef("DSM an: Update gemeldet", d == {"verfuegbar": True, "version": "DSM 7.4.2"}, d)
pruef("DSM an: nur die Abfrage check", BEFEHLE and BEFEHLE[-1][-3:] == ["api=SYNO.Core.Upgrade.Server", "method=check",
                                                                      "version=4"], BEFEHLE)
AUSGABEN[:] = [json.dumps({"success": True, "data": {"update": {"available": False}}})]
pruef("DSM an: aktuell", up.dsm() == {"verfuegbar": False, "version": ""})
AUSGABEN[:] = [json.dumps({"success": False})]
pruef("DSM an: Abfrage abgelehnt -> None", up.dsm() is None)
AUSGABEN[:] = ["kein json"]
pruef("DSM an: unlesbar -> None", up.dsm() is None)
AUSGABEN[:] = [OSError("fehlt")]
pruef("DSM an: Befehl fehlt -> None", up.dsm() is None)
pruef("DSM an: Pakete automatisch", up.pakete_automatisch(INFO) is True)
open(INFO, "w", encoding="utf-8").write('pkg_autoupdate_all="no"\n')
pruef("DSM an: Pakete nicht automatisch", up.pakete_automatisch(INFO) is False)
pruef("DSM an: Datei fehlt", up.pakete_automatisch(os.path.join(T, "fehlt")) is False)
up.DSM = False

# ---------------------------------------------------------------- Projektquelle und Release Notes
for label, soll in (({"org.opencontainers.image.source": "https://github.com/beispiel/werkzeug"}, "beispiel/werkzeug"),
                    ({"org.label-schema.vcs-url": "https://github.com/beispiel/alt.git"}, "beispiel/alt"),
                    ({"org.opencontainers.image.source": "https://gitlab.com/beispiel/x"}, None),
                    (None, None)):
    AUSGABEN[:] = [json.dumps(label)]
    pruef("Quelle: %s" % soll, up.quelle_des_images("x/werkzeug:latest") == soll)
pruef("Quelle: ueber den eingestellten Docker-Befehl", BEFEHLE[-1][:3] == ["docker", "image", "inspect"], BEFEHLE[-1])
AUSGABEN[:] = [subprocess.TimeoutExpired("docker", 30)]
pruef("Quelle: Zeitueberschreitung -> None", up.quelle_des_images("x") is None)
REL = "https://api.github.com/repos/beispiel/werkzeug/releases?per_page=2"
NETZ[REL] = (200, [{"tag_name": "v2.0", "published_at": "2026-10-30T10:00:00Z", "body": "Neu\n\n\n\n\nBehoben" + "y" * 3000},
                   {"tag_name": "v1.9", "published_at": None, "body": None}])
n = up.neuigkeiten("beispiel/werkzeug")
pruef("Release Notes: Version, Datum, Text gekuerzt", n[0]["version"] == "v2.0" and n[0]["datum"] == "2026-10-30"
      and n[0]["text"].startswith("Neu\n\nBehoben") and len(n[0]["text"]) == 2500 and n[1]["text"] == "" and n[1]["datum"] == "", n)
NETZ[REL] = ("weg", None)
try:
    up.neuigkeiten("beispiel/werkzeug")
    pruef("Release Notes: GitHub weg", False)
except up.Fehler as e:
    pruef("Release Notes: GitHub weg", str(e) == "GitHub ist gerade nicht erreichbar.", e)

# ---------------------------------------------------------------- Gesundheit nach dem Neuerstellen
AUSGABEN[:] = ["running|starting", "running|healthy"]
pruef("gesund: wartet auf healthy", up.gesund("omnitools") == (True, "running|healthy"))
AUSGABEN[:] = ["running|"]
pruef("gesund: ohne Healthcheck reicht running", up.gesund("omnitools") == (True, "running|"))
AUSGABEN[:] = ["exited|"]
pruef("gesund: beendet", up.gesund("omnitools") == (False, "exited|"))
pruef("gesund: Docker-Befehl", BEFEHLE[-1][:3] == ["docker", "inspect", "omnitools"], BEFEHLE[-1])
pruef("gesund: ohne Zeit unbekannt", up.gesund("omnitools", warten=0) == (False, "unbekannt"))
up.setze_sprache("en")
pruef("gesund: englisch", up.gesund("omnitools", warten=0) == (False, "unknown"))
up.setze_sprache("de")

shutil.rmtree(T)
pruef("Keine fremde Adresse angefragt", all(a["url"].startswith((up.DOCKHAND + "/", up.HA + "/", "https://api.github.com/"))
                                            for a in ANFRAGEN), [a["url"] for a in ANFRAGEN])
print("Update-Zentrale: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
