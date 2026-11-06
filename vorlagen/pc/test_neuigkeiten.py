#!/usr/bin/env python3
"""Neu in dieser Version (PC-Client ab 16, Bestaetigung seit 23): Teile aus jarvis_pc.py lesen, ohne den Client zu laden
(der braucht Windows-Bibliotheken), dazu die HUD-Seite als Text.

(1) neuigkeiten_offen(): Neuinstallation zeigt nichts, ein Update zeigt, jede Version hat Punkte in beiden Sprachen.
(2) Api.neuigkeiten/neuigkeiten_gesehen (seit 23): Mit bestaetigt_spaeter=True gilt die Version erst nach
    "Verstanden" als gesehen, bis dahin kommt der Hinweis bei jedem Laden wieder (bis 22 merkte sich der Client die
    Version schon beim Abfragen, nach einem Update im Hintergrund ging der Hinweis so verloren). Eine HUD-Seite ohne
    Bestaetigung fragt ohne Argument und bekommt das alte Verhalten (nie Dauerschleife). Nur die laufende Version laesst
    sich bestaetigen.
(3) HUD: fragt auch ohne pywebviewready (sofort, nach 2 und 10 s), nur einmal je Seite, "Verstanden" bestaetigt,
    aeltere Clients ohne neuigkeiten_gesehen werden ohne Argument gefragt.
Laeuft im Repo (tests/ neben spiegel/pc/) und in der Release-Vorlage (neben jarvis_pc.py); die HUD-Pruefungen (3) nur
im Repo, denn die HUD-Vorlage entsteht erst nach diesem Test."""
import ast
import os
import re
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
for PC in (os.path.join(HIER, "..", "spiegel", "pc", "jarvis_pc.py"), os.path.join(HIER, "jarvis_pc.py")):
    if os.path.exists(PC):
        break
else:
    sys.exit("jarvis_pc.py nicht gefunden")
HUD = os.path.join(HIER, "..", "spiegel", "hud", "index.html")
quelle = open(PC, encoding="utf-8").read()
baum = ast.parse(quelle)
teile = [n for n in baum.body if (isinstance(n, ast.Assign) and any(isinstance(z, ast.Name) and z.id in (
    "NEUIGKEITEN", "VERSION") for z in n.targets)) or (isinstance(n, ast.FunctionDef) and n.name == "neuigkeiten_offen")]
api = next(n for n in baum.body if isinstance(n, ast.ClassDef) and n.name == "Api")
api_teile = [n for n in api.body if isinstance(n, ast.FunctionDef) and n.name in ("neuigkeiten", "neuigkeiten_gesehen")]
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


class Log:
    def __init__(self):
        self.zeilen = []

    def info(self, *a):
        self.zeilen.append(a[0] % a[1:] if len(a) > 1 else a[0])


def umgebung(einstellungen, sprache="de", fenster_ok=True):
    """Ausfuehrbare Teile mit Attrappen: E, Speichern (gezaehlt), Fensterpruefung."""
    u = {"E": einstellungen, "SPRACHE": sprache, "ABGELEHNT": {"fehler": "abgelehnt"}, "log": Log(), "gespeichert": [],
         "BESTAND": "zuletzt_version" in einstellungen or bool(einstellungen.get("desktop_symbol_angelegt"))}
    u["einstellungen_speichern"] = lambda: u["gespeichert"].append(dict(einstellungen))
    u["aus_dem_fenster"] = lambda name: fenster_ok
    exec(compile(ast.Module(body=teile, type_ignores=[]), PC, "exec"), u)
    klasse = ast.ClassDef(name="Api", bases=[], keywords=[], body=api_teile, decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[klasse], type_ignores=[])), PC, "exec"), u)
    return u


# ---- (1) neuigkeiten_offen
u = umgebung({})
V, ALLE = u["VERSION"], u["NEUIGKEITEN"]
pruef("Version ab 24 (Bestaetigung seit 23)", V >= 24, V)
pruef("Neuinstallation: nichts", u["neuigkeiten_offen"]() == [])
offen = umgebung({"desktop_symbol_angelegt": True})["neuigkeiten_offen"]()
pruef("Update von vor 16: aktuelle Version zuerst", [o["titel"] for o in offen][:1] == [ALLE[V]["titel"]])
pruef("schon gesehen: nichts", umgebung({"desktop_symbol_angelegt": True, "zuletzt_version": V})["neuigkeiten_offen"]() == [])
offen = umgebung({"zuletzt_version": V - 1}, "en")["neuigkeiten_offen"]()
pruef("englisch", offen and offen[0]["punkte"] == ALLE[V]["en"])
pruef("von %d auf %d: genau ein Eintrag" % (V - 1, V), len(umgebung({"zuletzt_version": V - 1})["neuigkeiten_offen"]()) == 1)
pruef("von 22 auf %d: ein Eintrag je Version" % V, len(umgebung({"zuletzt_version": 22})["neuigkeiten_offen"]()) == V - 22)
for v, n in sorted(ALLE.items()):
    pruef("Version %d hat de und en gleich viele Punkte" % v, len(n.get("de", [])) == len(n.get("en", [])) > 0)
pruef("aktuelle Version hat Neuigkeiten", V in ALLE)
text23 = " ".join(ALLE[23]["de"])
pruef("23 nennt das Symbol wie in der App", "Symbol" in text23 and "App" in text23, text23)
pruef("23 nennt die Taskleiste (de und en)", "Taskleiste" in ALLE[23]["de"][0] and "taskbar" in ALLE[23]["en"][0], ALLE[23]["en"][0])
pruef("23 sagt, woher das Symbol kommt (Setup, kein Download)", "Setup" in ALLE[23]["de"][0] and "setup" in ALLE[23]["en"][0],
      ALLE[23]["de"][0])
pruef("23 nennt das Bestaetigen mit Verstanden (de und en)", "Verstanden" in text23 and "Got it" in " ".join(ALLE[23]["en"]))
# Englisch ohne deutsche Reste
for v in (23, 24, 25):
    en = " ".join(ALLE[v]["en"])
    pruef("Version %d englisch ohne Umlaute und deutsche Woerter" % v,
          not re.search(r"[äöüÄÖÜß]|\b(und|nicht|ist|Bitte|der|die|das)\b", en), en)

# ---- (2) Api.neuigkeiten / neuigkeiten_gesehen
E = {"zuletzt_version": V - 1, "desktop_symbol_angelegt": True}
u = umgebung(E)
a = u["Api"]()
r = a.neuigkeiten(True)
pruef("Update, neues HUD: Punkte da", r["version"] == V and len(r["punkte"]) == 1, r)
pruef("Update, neues HUD: noch nicht als gesehen gemerkt", E["zuletzt_version"] == V - 1 and not u["gespeichert"], E)
r = a.neuigkeiten(True)
pruef("Neu geladen ohne Verstanden: kommt wieder", len(r["punkte"]) == 1, r)
pruef("Verstanden mit falscher Version: nein", a.neuigkeiten_gesehen(V + 1) is False and E["zuletzt_version"] == V - 1)
pruef("Verstanden mit der Version als Text: nein", a.neuigkeiten_gesehen(str(V)) is False and E["zuletzt_version"] == V - 1)
pruef("Verstanden mit True: nein", a.neuigkeiten_gesehen(True) is False and E["zuletzt_version"] == V - 1)
pruef("Verstanden mit der laufenden Version: ja, gemerkt", a.neuigkeiten_gesehen(V) is True and E["zuletzt_version"] == V
      and len(u["gespeichert"]) == 1, E)
pruef("danach: nichts mehr (nicht doppelt)", a.neuigkeiten(True)["punkte"] == [])
pruef("zweites Verstanden: kein weiteres Speichern", a.neuigkeiten_gesehen(V) is True and len(u["gespeichert"]) == 1)

E = {"zuletzt_version": V - 1}
u = umgebung(E)
r = u["Api"]().neuigkeiten()
pruef("alte HUD-Seite (ohne Argument): Punkte und sofort gemerkt", len(r["punkte"]) == 1 and E["zuletzt_version"] == V
      and len(u["gespeichert"]) == 1, (r, E))
E = {"zuletzt_version": V - 1}
u = umgebung(E)
u["Api"]().neuigkeiten("ja")
pruef("nur True verschiebt das Merken", E["zuletzt_version"] == V, E)

E = {}
u = umgebung(E)
r = u["Api"]().neuigkeiten(True)
pruef("Neuinstallation: keine Punkte, Version trotzdem gemerkt (Bestand fuer spaeter)",
      r["punkte"] == [] and E.get("zuletzt_version") == V, (r, E))

E = {"zuletzt_version": V - 1}
u = umgebung(E, fenster_ok=False)
a = u["Api"]()
pruef("fremde Seite: abgelehnt", a.neuigkeiten(True) == {"fehler": "abgelehnt"} and a.neuigkeiten_gesehen(V) == {
    "fehler": "abgelehnt"} and E["zuletzt_version"] == V - 1)

# ---- (3) HUD-Seite (nur im Repo)
if os.path.exists(HUD):
    hud = open(HUD, encoding="utf-8").read()
    m = re.search(r"const NEU = \{.*?\n(async function neuigkeitenZeigen\(\) \{.*?\n\})\n(.*?)setTimeout\(zahnradPruefen", hud, re.S)
    pruef("HUD: Block gefunden", bool(m))
    if m:
        fn, rest = m.group(1), m.group(2)
        pruef("HUD: fragt nur einmal je Seite", "NEU.gefragt" in fn and re.search(r"if \(!a \|\| !a\.neuigkeiten \|\| NEU\.gefragt\) return;", fn))
        pruef("HUD: neuer Client mit Bestaetigung, alter ohne Argument",
              "a.neuigkeiten_gesehen ? a.neuigkeiten(true) : a.neuigkeiten()" in fn)
        pruef("HUD: Fehler oder Ablehnung erlauben einen neuen Versuch", fn.count("NEU.gefragt = false") == 2)
        pruef("HUD: auf pywebviewready", 'window.addEventListener("pywebviewready", neuigkeitenZeigen);' in rest)
        pruef("HUD: Rueckfall ohne Ereignis (sofort, 2 s, 10 s)", re.search(r"^neuigkeitenZeigen\(\);$", rest, re.M)
              and "setTimeout(neuigkeitenZeigen, 2000);" in rest and "setTimeout(neuigkeitenZeigen, 10000);" in rest)
        pruef("HUD: Verstanden bestaetigt die gezeigte Version",
              re.search(r'\$\("neu-ok"\)\.addEventListener\("click".*?a\.neuigkeiten_gesehen\(NEU\.version\)', rest, re.S))
    pruef("HUD: #neu bleibt im Design Kern sichtbar", ":not(#neu)" in hud)
    pruef("HUD: Knopf Verstanden de und en", '"neu_ok": "Verstanden"' in hud and '"neu_ok": "Got it"' in hud)
else:
    print("Hinweis: keine HUD-Seite unter %s, HUD-Pruefungen entfallen (Release-Vorlage)" % HUD)

print("Neuigkeiten: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
