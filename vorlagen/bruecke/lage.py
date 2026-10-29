"""Reiter "Lage" im Design Observatorium (seit 0.5.1), Teil der Bruecke: Bausteine fuer system.json.

Der Reiter zeigt Termine (kalender.json), die Werte dieses Rechners (messer und volumes), Container, Sicherungen, den
PC und Jarvis selbst. Die Bruecke schreibt dafuer zusaetzliche Felder in system.json. Alle sind freiwillig, eine Karte
ohne Daten bleibt weg. Dieselben Daten gehen als Feld "system" in /v1/lage an die App (ab 4.9).

- volumes: [[Name, Prozent]], hoechstens 6 (volumes()).
- container: {laufend, gesamt, ungesund, neustart, tot, probleme: [Namen], gestoppt: [Namen]} (docker_lage() fuer
  Docker auf diesem Rechner, sonst container_eintrag() mit eigenen Zahlen). Gestoppt ist oft gewollt (Einmal-Jobs)
  und zaehlt nicht als Problem.
- sicherung: [{name, ok, alter_h}] (sicherung_eintrag(), die Quelle haengt von der Installation ab).
- pc: Werte vom PC-Client (ab Version 21), der sie alle 30 s an POST /v1/pc/werte schickt. pc_werte_pruefen() bringt
  sie in feste Form, pc_eintrag() gibt sie nur heraus, solange der PC verbunden ist und sie hoechstens 180 s alt sind.

Nur Python-Standardbibliothek (3.8)."""
import re
import shutil
import subprocess
import time

PC_MAX_ALTER = 180


def prozent(v):
    """Zahl auf 0..100 begrenzt und gerundet, alles andere None."""
    return round(max(0.0, min(100.0, float(v))), 1) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _text(s, laenge=60):
    return re.sub(r"[\x00-\x1f\x7f]", "", str(s)).strip()[:laenge]


def pc_werte_pruefen(b):
    """Werte des PC-Clients in feste Form bringen: nur bekannte Felder, Zahlen begrenzt, Texte kurz. Kein Objekt:
    ValueError (die Bruecke antwortet dann mit 400)."""
    if not isinstance(b, dict):
        raise ValueError("kein Objekt")
    w = {"cpu": prozent(b.get("cpu")), "ram": prozent(b.get("ram")), "ram_gib": None, "platten": [], "gpu": None}
    if isinstance(b.get("ram_gib"), (int, float)) and not isinstance(b["ram_gib"], bool) and 0 < b["ram_gib"] < 100000:
        w["ram_gib"] = round(float(b["ram_gib"]), 1)
    for p in (b.get("platten") or [])[:8] if isinstance(b.get("platten"), list) else []:
        if isinstance(p, list) and len(p) >= 2 and isinstance(p[0], str) and re.fullmatch(r"[A-Z]:", p[0]) and prozent(p[1]) is not None:
            gib = p[2] if len(p) > 2 and isinstance(p[2], (int, float)) and not isinstance(p[2], bool) and 0 < p[2] < 10 ** 6 else None
            w["platten"].append([p[0], prozent(p[1]), gib])
    g = b.get("gpu")
    if isinstance(g, dict):
        w["gpu"] = {"name": re.sub(r"[^\w .()+-]", "", str(g.get("name", "")))[:48], "last": prozent(g.get("last")),
                    "temp": prozent(g.get("temp")), "speicher": prozent(g.get("speicher"))}
    return w


def pc_eintrag(werte, zeit, pc_online, jetzt=None):
    """Feld "pc" fuer system.json: die geprueften Werte mit alter_s, oder None (PC getrennt, nie gemeldet, zu alt)."""
    jetzt = time.time() if jetzt is None else jetzt
    if not werte or not pc_online or not zeit or jetzt - zeit > PC_MAX_ALTER:
        return None
    return dict(werte, alter_s=int(max(0, jetzt - zeit)))


def volumes(pfade):
    """pfade: [(Anzeigename, Pfad)] -> [[Name, Prozent belegt]] fuer erreichbare Pfade, hoechstens 6."""
    aus = []
    for name, pfad in list(pfade)[:6]:
        try:
            u = shutil.disk_usage(pfad)
        except OSError:
            continue
        if u.total > 0:
            aus.append([_text(name, 40), round(100 * u.used / u.total)])
    return aus


def _anzahl(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def container_eintrag(laufend, gesamt, ungesund=0, neustart=0, tot=0, probleme=(), gestoppt=()):
    """Feld "container" fuer system.json aus eigenen Zahlen. probleme: Namen der ungesunden, neu startenden oder toten
    Container (hoechstens 20), gestoppt: Namen gestoppter Container (hoechstens 30)."""
    return {"laufend": _anzahl(laufend), "gesamt": _anzahl(gesamt), "ungesund": _anzahl(ungesund) or 0,
            "neustart": _anzahl(neustart) or 0, "tot": _anzahl(tot) or 0,
            "probleme": [_text(n) for n in list(probleme)[:20] if _text(n)],
            "gestoppt": [_text(n) for n in list(gestoppt)[:30] if _text(n)]}


def docker_auswerten(text):
    """Ausgabe von docker ps -a --format '{{.Names}}\\t{{.State}}\\t{{.Status}}' -> Feld "container"."""
    laufend = gesamt = 0
    ungesund, neustart, tot, gestoppt = [], [], [], []
    for zeile in text.splitlines():
        teile = zeile.split("\t")
        if len(teile) < 3 or not teile[0].strip():
            continue
        name, zustand, status = teile[0].strip(), teile[1].strip().lower(), teile[2].lower()
        gesamt += 1
        if zustand == "running":
            laufend += 1
            if "(unhealthy)" in status:
                ungesund.append(name)
        elif zustand == "restarting":
            neustart.append(name)
        elif zustand == "dead":
            tot.append(name)
        elif zustand in ("exited", "created"):
            gestoppt.append(name)
    return container_eintrag(laufend, gesamt, len(ungesund), len(neustart), len(tot), sorted(ungesund + neustart + tot),
                             sorted(gestoppt))


def docker_lage(befehl=("docker",), zeitlimit=10):
    """Container ueber die Docker-Kommandozeile zaehlen, befehl z. B. ("sudo", "/usr/bin/docker"). None, wenn Docker
    nicht erreichbar ist. Hoechstens einmal je Minute aufrufen, das reicht fuer den Reiter."""
    try:
        p = subprocess.run(list(befehl) + ["ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}"],
                           capture_output=True, text=True, timeout=zeitlimit)
    except (OSError, subprocess.SubprocessError):
        return None
    return docker_auswerten(p.stdout) if p.returncode == 0 else None


def sicherung_eintrag(name, ok, alter_h=None):
    """Ein Eintrag fuer "sicherung": ok nur bei True, alter_h = Stunden seit dem letzten Erfolg (oder None)."""
    a = round(float(alter_h)) if isinstance(alter_h, (int, float)) and not isinstance(alter_h, bool) and alter_h >= 0 else None
    return {"name": _text(name, 40), "ok": ok is True, "alter_h": a}
