"""Update-Zentrale (seit 0.6): Container (ueber Dockhand), Home Assistant (Core, OS, Supervisor, Add-ons, HACS) und,
wenn eingeschaltet, Synology DSM in einem Blick; einspielen nur auf Zuruf. Python 3.8, nur Standardbibliothek.

Container: Dockhands eigene Pruefung (POST /api/containers/check-updates, ~4 s fuer ~100 Container) und Neuerstellung
mit allen Einstellungen (POST /api/containers/batch-update). Home Assistant: update.*-Entitaeten, einspielen mit
update.install und Sicherung.

Einstellungen in der Umgebung der Bruecke (.env), alle mit neutralem Standard:
  DOCKHAND_ADRESSE=http://127.0.0.1:3000   Basis-URL von Dockhand (Token liest die Bruecke aus einer Datei)
  DOCKHAND_UMGEBUNG=1                      Kennung der Docker-Umgebung in Dockhand
  HA_ADRESSE=http://homeassistant.local:8123
  DOCKER_BEFEHL=docker                     z. B. "sudo /usr/local/bin/docker" auf einem Synology-NAS
  UPDATES_DSM=0                            1 = optionaler Synology-Teil (siehe unten)

Optionaler Teil Synology DSM (UPDATES_DSM=1, nur auf einem Synology-NAS mit sudo-Recht fuer synowebapi): das
DSM-Systemupdate nur melden (SYNO.Core.Upgrade.Server check, reine Abfrage), nie einspielen. Paket-Updates spielt DSM
selbst ein, wenn pkg_autoupdate_all eingeschaltet ist; deshalb kein synopkg checkupdateall (koennte sofort einspielen).
"""
import json
import os
import re
import shlex
import subprocess
import time
import urllib.error
import urllib.request

DOCKHAND = os.environ.get("DOCKHAND_ADRESSE", "http://127.0.0.1:3000").rstrip("/")
DOCKHAND_ENV = int(os.environ.get("DOCKHAND_UMGEBUNG", "1") or 1)
HA = os.environ.get("HA_ADRESSE", "http://homeassistant.local:8123").rstrip("/")
DOCKER = shlex.split(os.environ.get("DOCKER_BEFEHL", "docker")) or ["docker"]
DSM = os.environ.get("UPDATES_DSM", "0") == "1"
# Container mit eigener Datenbank und Kern-Dienste: einspielen nur, wenn die Person sie in ihrer Nachricht nennt
# ("Container mit eigener Datenbank oder Kern-Dienste nur, wenn du sie ausdruecklich nennst"). An die eigenen Dienste
# anpassen.
KERN = re.compile(r"authentik|vaultwarden|pihole|pi-hole|dockhand|kopia|backup|postgres|mariadb|mysql|mongo|redis|"
                  r"valkey|[-_]db\b|db[-_]|database|paperless|immich|nextcloud|forgejo|gitea|mailarchiver|ntfy|"
                  r"homeassistant|jarvis|matrix|synapse|traefik|caddy|nginx", re.I)


# Sprache der Texte, die die Person sieht (Fehlermeldungen in der Antwort). Die Bruecke setzt sie beim Start aus der
# Einrichtung (antworten.json "sprache"), wie bei szenen.py.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


class Fehler(Exception):
    pass


def _dh(pfad, token, methode="GET", daten=None, zeit=60):
    body = json.dumps(daten).encode() if daten is not None else (b"" if methode == "POST" else None)
    r = urllib.request.Request(DOCKHAND + pfad, method=methode, data=body,
                               headers={"Authorization": "Bearer " + token, "Accept": "application/json",
                                        "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(r, timeout=zeit))
    except urllib.error.HTTPError as e:
        raise Fehler(_t("Dockhand antwortet mit HTTP %d.", "Dockhand answered with HTTP %d.") % e.code)
    except OSError as e:
        raise Fehler(_t("Dockhand ist nicht erreichbar (%s).", "Dockhand is not reachable (%s).") % type(e).__name__)


def container(token):
    """Frische Pruefung ueber Dockhand: [{"id", "name", "image"}] mit Update, ohne gesperrte/lokale/System-Container."""
    e = _dh("/api/containers/check-updates?env=%d" % DOCKHAND_ENV, token, "POST", zeit=300)
    return [{"id": x["containerId"], "name": x["containerName"], "image": x.get("imageName", ""), "kern": bool(KERN.search(x["containerName"] + " " + x.get("imageName", "")))}
            for x in e.get("results") or [] if x.get("hasUpdate") and not x.get("systemContainer")
            and not x.get("updateDisabled") and not x.get("pinnedToDigest") and not x.get("isLocalImage")], e.get("total", 0)


def dockhand_selbst(token):
    try:
        s = _dh("/api/self-update/check", token)
    except Fehler:
        return None
    return s if s.get("updateAvailable") and not s.get("versionOnly") else None


def _ha(pfad, token, daten=None, zeit=30):
    r = urllib.request.Request(HA + pfad, data=json.dumps(daten).encode() if daten is not None else None,
                               headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=zeit))


def ha(token):
    """Anstehende HA-Updates: [{"id", "titel", "installiert", "neu", "url", "sicherung"}]"""
    erg = []
    for s in _ha("/api/states", token):
        if s["entity_id"].startswith("update.") and s["state"] == "on":
            a = s["attributes"]
            erg.append({"id": s["entity_id"], "titel": a.get("title") or a.get("friendly_name") or s["entity_id"],
                        "installiert": a.get("installed_version"), "neu": a.get("latest_version"),
                        "url": a.get("release_url") or "", "zusammenfassung": (a.get("release_summary") or "")[:600],
                        "sicherung": bool(int(a.get("supported_features") or 0) & 8)})
    return erg


def dsm():
    """Optionaler Synology-Teil: DSM-Systemupdate nur melden. {"verfuegbar": bool, "version": str} oder None, wenn die
    Abfrage scheitert oder der Teil aus ist (UPDATES_DSM)."""
    if not DSM:
        return None
    try:
        p = subprocess.run(["sudo", "/usr/syno/bin/synowebapi", "--exec", "api=SYNO.Core.Upgrade.Server", "method=check",
                            "version=4"], capture_output=True, text=True, timeout=120)
        d = json.loads(p.stdout)
    except (subprocess.SubprocessError, ValueError, OSError):
        return None
    u = (d.get("data") or {}).get("update") or {}
    if not d.get("success"):
        return None
    return {"verfuegbar": bool(u.get("available")), "version": str(u.get("version") or u.get("version_details") or "")[:80]}


def pakete_automatisch(datei="/etc/synoinfo.conf"):
    """Optionaler Synology-Teil: aktualisiert DSM seine Pakete selbst? Ohne UPDATES_DSM immer False."""
    if not DSM:
        return False
    try:
        return any(z.strip() == 'pkg_autoupdate_all="yes"' for z in open(datei, encoding="utf-8"))
    except OSError:
        return False


def quelle_des_images(image):
    """GitHub-Repo aus dem OCI-Label org.opencontainers.image.source (oder None)."""
    try:
        p = subprocess.run(DOCKER + ["image", "inspect", image, "--format", "{{json .Config.Labels}}"],
                           capture_output=True, text=True, timeout=30)
        lab = json.loads(p.stdout.strip() or "{}") or {}
    except (subprocess.SubprocessError, ValueError, OSError):
        return None
    q = lab.get("org.opencontainers.image.source") or lab.get("org.label-schema.vcs-url") or ""
    m = re.match(r"https?://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?/?$", q)
    return m.group(1) if m else None


def neuigkeiten(repo, anzahl=2):
    """Die letzten Release Notes eines GitHub-Repos (Text gekuerzt, fremder Text)."""
    r = urllib.request.Request("https://api.github.com/repos/%s/releases?per_page=%d" % (repo, anzahl),
                               headers={"User-Agent": "jarvis-hausassistent/0.6", "Accept": "application/vnd.github+json"})
    try:
        rel = json.load(urllib.request.urlopen(r, timeout=20))
    except (OSError, ValueError):
        raise Fehler(_t("GitHub ist gerade nicht erreichbar.", "GitHub is not reachable right now."))
    return [{"version": x.get("tag_name"), "datum": (x.get("published_at") or "")[:10],
             "text": re.sub(r"\n{3,}", "\n\n", x.get("body") or "")[:2500]} for x in rel]


def gesund(name, warten=120):
    """Nach dem Neuerstellen: laeuft der Container (und ist er gesund, wenn er einen Healthcheck hat)?"""
    ende = time.time() + warten
    zustand = ""
    while time.time() < ende:
        try:
            p = subprocess.run(DOCKER + ["inspect", name, "--format",
                                         "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}"],
                               capture_output=True, text=True, timeout=20)
            zustand = p.stdout.strip()
        except subprocess.SubprocessError:
            zustand = ""
        status, _, health = zustand.partition("|")
        if status == "running" and health in ("", "healthy"):
            return True, zustand
        if status in ("exited", "dead"):
            return False, zustand
        time.sleep(10)
    return False, zustand or _t("unbekannt", "unknown")
