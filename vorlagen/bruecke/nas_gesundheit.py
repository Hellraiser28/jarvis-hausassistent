"""Rechner kritisch? (seit 0.6) RAID und Platten des Rechners, auf dem die Bruecke laeuft, fuer eine Meldung an die
Hauptperson (Push, jeder Befund einmal je 24 Stunden; das Merken und Melden macht die Bruecke).

Optionaler Baustein fuer Linux mit Software-RAID (mdadm) und/oder smartmontools, z. B. ein NAS oder Heimserver. Unter
Windows und macOS, mit Hardware-RAID, ZFS oder btrfs-RAID findet er nichts; dann weglassen.

Zwei Quellen, beide auf dem Rechner selbst gemessen:
  /proc/mdstat   RAID-Zustand. Fehlt einem Array ein Mitglied ("_" in [UU]) oder ist eins als ausgefallen markiert
                 ("(F)") oder ist es nicht aktiv, ist das ein Befund. Arrays in NAS_SYSTEM_ARRAYS zaehlen nicht:
                 Synology legt md0 (DSM-System) und md1 (Swap) als RAID1 ueber alle Schaechte an, bei teilweise
                 bestueckten Schaechten zeigen sie immer z. B. [5/3] [UUU__]; das ist normal (dort
                 NAS_SYSTEM_ARRAYS=md0,md1).
  smartctl -H    Gesamturteil je Platte. "PASSED"/"OK" ist gesund, "FAILED" ein Befund; keine oder unlesbare Antwort
                 ist kein Befund (sonst meldet Jarvis einen Lesefehler als Plattenschaden).

Einstellungen in der Umgebung der Bruecke (.env), alle mit neutralem Standard:
  NAS_SYSTEM_ARRAYS=                       Arrays, die nicht zaehlen (mit Komma; Synology: md0,md1)
  NAS_PLATTEN=/dev/sd[a-z] /dev/nvme[0-9]  Muster der Platten fuer SMART (Synology: /dev/sata[0-9] /dev/sata[0-9][0-9])
  NAS_SMART_BEFEHL=sudo smartctl           smartctl braucht Root-Rechte (Synology: sudo /bin/smartctl)
Nur Python-Standardbibliothek (3.8)."""
import glob
import os
import re
import shlex
import subprocess

SYSTEM_ARRAYS = tuple(x.strip() for x in os.environ.get("NAS_SYSTEM_ARRAYS", "").split(",") if x.strip())
PLATTEN = os.environ.get("NAS_PLATTEN", "/dev/sd[a-z] /dev/nvme[0-9]").split()
SMART = shlex.split(os.environ.get("NAS_SMART_BEFEHL", "sudo smartctl"))
MDSTAT = "/proc/mdstat"


# Sprache der Befundtexte, die als Meldung bei der Person ankommen. Die Bruecke setzt sie beim Start aus der
# Einrichtung (antworten.json "sprache"), wie bei szenen.py.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


def raid_befunde(mdstat):
    """-> Liste (schluessel, text) fuer beschaedigte Daten-Arrays."""
    raus = []
    bloecke = re.split(r"\n(?=md\d+ :)", str(mdstat or ""))
    for b in bloecke:
        m = re.match(r"(md\d+) : (\S+)(.*)", b)
        if not m or m.group(1) in SYSTEM_ARRAYS:
            continue
        name, mitglieder = m.group(1), m.group(3)
        stand = re.search(r"\[(\d+)/(\d+)\] \[([U_]+)\]", b)
        ausgefallen = re.findall(r"(\S+?)\[\d+\]\(F\)", mitglieder)
        if stand and (int(stand.group(2)) < int(stand.group(1)) or "_" in stand.group(3)):
            raus.append(("raid:%s:fehlt" % name, _t(
                "Im RAID %s fehlt eine Platte (%s von %s aktiv). Die Daten liegen gerade ohne Spiegel.",
                "The RAID %s is missing a disk (%s of %s active). The data currently has no mirror.")
                % (name, stand.group(2), stand.group(1))))
        for platte in ausgefallen:
            raus.append(("raid:%s:%s" % (name, platte), _t("Im RAID %s ist %s als ausgefallen markiert.",
                                                            "In the RAID %s, %s is marked as failed.") % (name, platte)))
        if m.group(2) != "active":
            raus.append(("raid:%s:inaktiv" % name, _t("Das RAID %s ist nicht aktiv (%s).",
                                                      "The RAID %s is not active (%s).") % (name, m.group(2))))
    return raus


def smart_befund(platte, ausgabe):
    """-> (schluessel, text) bei FAILED, sonst None."""
    t = str(ausgabe or "")
    if re.search(r"overall-health self-assessment test result:\s*FAILED|SMART Health Status:\s*(FAIL|FAILED)", t, re.I):
        return ("smart:%s" % platte, _t("Die Platte %s meldet SMART: FEHLER. Sie kann bald ausfallen.",
                                        "The disk %s reports SMART: FAILED. It may fail soon.") % platte)
    return None


def platten():
    return sorted({p for muster in PLATTEN for p in glob.glob(muster)})


def lesen(smart=True):
    """Liest beides und gibt alle Befunde zurueck. smart=False nur RAID (billiger, fuer den 5-Minuten-Takt)."""
    try:
        with open(MDSTAT, encoding="utf-8") as f:
            befunde = raid_befunde(f.read())
    except OSError:
        befunde = []
    if smart:
        for p in platten():
            try:
                r = subprocess.run(SMART + ["-H", p], capture_output=True, text=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                continue
            b = smart_befund(p.rsplit("/", 1)[1], r.stdout)
            if b:
                befunde.append(b)
    return befunde
