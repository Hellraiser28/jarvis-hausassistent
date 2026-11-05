#!/usr/bin/env python3
"""Baustein nas_gesundheit.py (seit 0.6): RAID-Befunde aus /proc/mdstat, SMART-Gesamturteil, Einstellungen.
Beispieltexte statt des echten /proc/mdstat, eine kleine Attrappe statt smartctl, Testordner statt echter Platten."""
import importlib
import os
import shutil
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import nas_gesundheit as nasg  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


# ---------------------------------------------------------------- Einstellungen
NAMEN = ("NAS_SYSTEM_ARRAYS", "NAS_PLATTEN", "NAS_SMART_BEFEHL")
for k in NAMEN:                          # nur in diesem Testprozess
    os.environ.pop(k, None)
nasg = importlib.reload(nasg)
pruef("Standard: keine System-Arrays", nasg.SYSTEM_ARRAYS == ())
pruef("Standard: SATA/SAS und NVMe", nasg.PLATTEN == ["/dev/sd[a-z]", "/dev/nvme[0-9]"], nasg.PLATTEN)
pruef("Standard: smartctl mit sudo", nasg.SMART == ["sudo", "smartctl"], nasg.SMART)
os.environ.update({"NAS_SYSTEM_ARRAYS": "md0, md1", "NAS_PLATTEN": "/dev/sata[0-9] /dev/sata[0-9][0-9]",
                   "NAS_SMART_BEFEHL": "sudo /bin/smartctl"})
nasg = importlib.reload(nasg)
pruef("Synology: System-Arrays", nasg.SYSTEM_ARRAYS == ("md0", "md1"), nasg.SYSTEM_ARRAYS)
pruef("Synology: Platten und Befehl", nasg.PLATTEN == ["/dev/sata[0-9]", "/dev/sata[0-9][0-9]"]
      and nasg.SMART == ["sudo", "/bin/smartctl"], (nasg.PLATTEN, nasg.SMART))

# ---------------------------------------------------------------- RAID (Synology-Aufbau, System-Arrays ausgenommen)
BEISPIEL = """Personalities : [raid1]
md2 : active raid1 sata1p5[2] sata2p5[1]
      1000000000 blocks super 1.2 [2/2] [UU]

md5 : active raid1 sata3p3[0]
      2000000000 blocks super 1.2 [1/1] [U]

md1 : active raid1 sata1p2[0] sata3p2[2] sata2p2[1]
      2097088 blocks [5/3] [UUU__]

md0 : active raid1 sata1p1[0] sata3p1[2] sata2p1[1]
      8388544 blocks [5/3] [UUU__]

unused devices: <none>"""
pruef("Gesunder Stand: kein Befund, md0/md1 mit [UUU__] sind normal", nasg.raid_befunde(BEISPIEL) == [])
WEG = BEISPIEL.replace("md2 : active raid1 sata1p5[2] sata2p5[1]\n      1000000000 blocks super 1.2 [2/2] [UU]",
                       "md2 : active raid1 sata2p5[1]\n      1000000000 blocks super 1.2 [2/1] [_U]")
bf = nasg.raid_befunde(WEG)
pruef("Fehlende Platte in md2: Befund", [k for k, _ in bf] == ["raid:md2:fehlt"] and "md2" in bf[0][1]
      and "1 von 2" in bf[0][1], bf)
F = BEISPIEL.replace("sata1p5[2] sata2p5[1]", "sata1p5[2](F) sata2p5[1]").replace("[2/2] [UU]", "[2/1] [_U]", 1)
pruef("Als ausgefallen markiert: Befund mit Platte",
      [k for k, _ in nasg.raid_befunde(F)] == ["raid:md2:fehlt", "raid:md2:sata1p5"], nasg.raid_befunde(F))
INAKTIV = "Personalities : [raid1]\nmd3 : inactive sata2p6[0](S)\n      9765350144 blocks super 1.2\n"
pruef("Inaktives Daten-Array: Befund", [k for k, _ in nasg.raid_befunde(INAKTIV)] == ["raid:md3:inaktiv"])
pruef("Leer oder None: kein Befund", nasg.raid_befunde("") == [] and nasg.raid_befunde(None) == [])

# ---------------------------------------------------------------- RAID (allgemeines Linux: alle Arrays zaehlen)
nasg.SYSTEM_ARRAYS = ()
pruef("Ohne System-Arrays: md0/md1 mit fehlenden Mitgliedern sind Befunde",
      [k for k, _ in nasg.raid_befunde(BEISPIEL)] == ["raid:md1:fehlt", "raid:md0:fehlt"], nasg.raid_befunde(BEISPIEL))
LINUX = """Personalities : [raid1] [raid6] [raid5] [raid4]
md127 : active raid5 sdd1[3] sdc1[1] sdb1[0]
      3906764800 blocks super 1.2 level 5, 512k chunk, algorithm 2 [3/3] [UUU]
      bitmap: 0/15 pages [0KB], 65536KB chunk

md0 : active raid1 nvme1n1p1[1] nvme0n1p1[0]
      499975168 blocks super 1.2 [2/2] [UU]

unused devices: <none>"""
pruef("Linux mit RAID5 und Bitmap-Zeile: kein Befund", nasg.raid_befunde(LINUX) == [])
L2 = LINUX.replace("sdc1[1] sdb1[0]", "sdc1[1](F) sdb1[0]").replace("[3/3] [UUU]", "[3/2] [U_U]")
pruef("Linux: ausgefallene Platte im RAID5", [k for k, _ in nasg.raid_befunde(L2)] == ["raid:md127:fehlt", "raid:md127:sdc1"],
      nasg.raid_befunde(L2))

# ---------------------------------------------------------------- SMART
pruef("SMART PASSED: kein Befund",
      nasg.smart_befund("sda", "SMART overall-health self-assessment test result: PASSED") is None)
pruef("SMART Health Status OK: kein Befund", nasg.smart_befund("sdc", "SMART Health Status: OK") is None)
b = nasg.smart_befund("sdb", "SMART overall-health self-assessment test result: FAILED!")
pruef("SMART FAILED: Befund", b and b[0] == "smart:sdb" and "sdb" in b[1], b)
pruef("SMART Health Status FAILED (SAS): Befund", (nasg.smart_befund("sdd", "SMART Health Status: FAILED") or [""])[0]
      == "smart:sdd")
pruef("Keine Antwort: kein Befund (kein Alarm wegen Lesefehler)", nasg.smart_befund("sdb", "") is None
      and nasg.smart_befund("sdb", None) is None and nasg.smart_befund("sdb", "Read NVMe Identify Controller failed") is None)

# ---------------------------------------------------------------- Sprache
try:
    nasg.setze_sprache("fr")
    pruef("Sprache: fr abgelehnt", False)
except ValueError:
    pruef("Sprache: fr abgelehnt", True)
nasg.setze_sprache("en")
pruef("Englisch: RAID", nasg.raid_befunde(WEG)[0][1].startswith("The RAID md2 is missing a disk (1 of 2 active)"),
      nasg.raid_befunde(WEG))
pruef("Englisch: SMART", nasg.smart_befund("sdb", "SMART Health Status: FAILED")[1]
      == "The disk sdb reports SMART: FAILED. It may fail soon.")
pruef("Englisch: Schluessel unveraendert", [k for k, _ in nasg.raid_befunde(INAKTIV)] == ["raid:md3:inaktiv"])
nasg.setze_sprache("de")

# ---------------------------------------------------------------- lesen() mit Attrappen
T = tempfile.mkdtemp(prefix="nas-test-")
for n in ("sda", "sdb", "sdc"):
    open(os.path.join(T, n), "w").close()
nasg.MDSTAT = os.path.join(T, "mdstat")
open(nasg.MDSTAT, "w", encoding="utf-8").write(WEG)
nasg.SYSTEM_ARRAYS = ("md0", "md1")
nasg.PLATTEN = [os.path.join(T, "sd[a-z]"), os.path.join(T, "sd[ab]")]
SKRIPT = os.path.join(T, "smart_attrappe.py")
open(SKRIPT, "w", encoding="utf-8").write(
    "import sys\n"
    "p = sys.argv[-1]\n"
    "open(p + '.gefragt', 'w').write(' '.join(sys.argv[1:]))\n"
    "print('SMART overall-health self-assessment test result: ' + ('FAILED!' if p.endswith('sdb') else 'PASSED'))\n"
    "if p.endswith('sdc'):\n"
    "    sys.exit(4)\n")
nasg.SMART = [sys.executable, SKRIPT]
pruef("Platten: Muster ohne Doppelte", nasg.platten() == [os.path.join(T, n) for n in ("sda", "sdb", "sdc")], nasg.platten())
pruef("Nur RAID (5-Minuten-Takt)", [k for k, _ in nasg.lesen(smart=False)] == ["raid:md2:fehlt"]
      and not os.path.exists(os.path.join(T, "sda.gefragt")))
pruef("RAID und SMART", [k for k, _ in nasg.lesen()] == ["raid:md2:fehlt", "smart:sdb"], nasg.lesen())
pruef("smartctl mit -H und Plattenpfad", open(os.path.join(T, "sda.gefragt")).read() == "-H " + os.path.join(T, "sda"))
nasg.MDSTAT = os.path.join(T, "fehlt")
nasg.SMART = [os.path.join(T, "kein-smartctl")]
pruef("Ohne mdstat und ohne smartctl: kein Befund, kein Absturz", nasg.lesen() == [])
shutil.rmtree(T)
print("NAS-Gesundheit: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
