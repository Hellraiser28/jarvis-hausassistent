#!/usr/bin/env python3
"""Updates des PC-Clients ueber die Bruecke (seit 25, Claude Security 0.7, F9): nur mit dem Ed25519-Schluessel, der beim
Koppeln festgehalten wurde. Kein HMAC aus dem Token-Hash mehr, und kein Schluessel, der zur Laufzeit ueber HTTP kommt.
Teile aus jarvis_pc.py lesen, ohne den Client zu laden (der braucht Windows-Bibliotheken). Signiert wird mit
bruecke/ed25519.py. Laeuft im Repo (tests/ neben spiegel/pc/ und bruecke/) und in der Release-Vorlage (vorlagen/pc/ neben
vorlagen/bruecke/)."""
import ast
import hashlib
import hmac
import json
import os
import re
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
for PC in (os.path.join(HIER, "..", "spiegel", "pc", "jarvis_pc.py"), os.path.join(HIER, "jarvis_pc.py")):
    if os.path.exists(PC):
        break
else:
    sys.exit("jarvis_pc.py nicht gefunden")
sys.path.insert(0, os.path.join(HIER, "..", "bruecke"))
import ed25519  # noqa: E402

quelle = open(PC, encoding="utf-8").read()
baum = ast.parse(quelle)
NAMEN = ("update_signiert", "update_schluessel", "update_suchen", "_ed_x", "_ed_plus", "_ed_mal", "_ed_punkt", "_ed_pruefen")
WERTE = ("RELEASE_SCHLUESSEL", "_ED_P", "_ED_L", "_ED_D", "_ED_I", "_ED_G")
teile = [n for n in baum.body if (isinstance(n, ast.FunctionDef) and n.name in NAMEN) or (
    isinstance(n, ast.Assign) and any(isinstance(z, ast.Name) and z.id in WERTE for z in n.targets))]
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


TOKEN_HASH = hashlib.sha256(b"geraete-token-zum-test").hexdigest()
GEHEIM = hashlib.sha256(b"bruecken-schluessel-zum-test").digest()
OEFF = ed25519.oeffentlich(GEHEIM).hex()
CODE = b"VERSION = 99\nprint('neu')\n"
PRUEF = hashlib.sha256(CODE).hexdigest()


def umgebung(einstellungen, antwort):
    abrufe = []

    def bruecke_holen(pfad, zeit):
        abrufe.append(pfad)
        if pfad == "/v1/client/version":
            return json.dumps(antwort).encode()
        if pfad == "/v1/client/schluessel":        # die alte Laufzeit-Abholung: duerfte gar nicht mehr kommen
            return json.dumps({"ed25519": "ab" * 32}).encode()
        raise AssertionError("unerwarteter Abruf " + pfad)

    u = {"E": einstellungen, "re": re, "json": json, "hashlib": hashlib, "hmac": hmac, "TOKEN_HASH": TOKEN_HASH,
         "VERSION": 25, "tx": lambda de, en: de, "bruecke_holen": bruecke_holen, "abrufe": abrufe,
         "einstellungen_speichern": lambda: abrufe.append("GESPEICHERT")}
    exec(compile(ast.Module(body=teile, type_ignores=[]), PC, "exec"), u)
    return u


def versuch(einstellungen, antwort):
    u = umgebung(einstellungen, antwort)
    try:
        return u["update_suchen"](), u
    except ValueError as e:
        return "abgelehnt: %s" % e, u


sig = ed25519.signieren(GEHEIM, ed25519.code_nachricht(99, PRUEF)).hex()
mac = hmac.new(TOKEN_HASH.encode(), ("jarvis-code:" + PRUEF).encode(), hashlib.sha256).hexdigest()
GUT = {"version": 99, "sha256": PRUEF, "ed25519": sig}

erg, u = versuch({"update_schluessel": OEFF}, GUT)
pruef("festgehaltener Schluessel, gueltige Signatur: Update", isinstance(erg, tuple) and erg[0] == 99 and erg[1] == "bruecke"
      and erg[3] == PRUEF, erg)
pruef("dabei nur die Version abgefragt", u["abrufe"] == ["/v1/client/version"], u["abrufe"])
erg, _ = versuch({"update_schluessel": OEFF.upper()}, GUT)
pruef("Schluessel in Grossbuchstaben gilt", isinstance(erg, tuple), erg)

erg, _ = versuch({"update_schluessel": OEFF}, dict(GUT, ed25519="00" * 64))
pruef("falsche Signatur: abgelehnt", str(erg).startswith("abgelehnt") and "Signatur" in str(erg), erg)
erg, _ = versuch({"update_schluessel": OEFF}, dict(GUT, version=100))
pruef("Signatur fuer andere Version: abgelehnt", str(erg).startswith("abgelehnt"), erg)
erg, _ = versuch({"update_schluessel": OEFF}, {"version": 99, "sha256": PRUEF, "mac": mac})
pruef("festgehaltener Schluessel, nur HMAC: abgelehnt", str(erg).startswith("abgelehnt"), erg)

# F9: ohne festgehaltenen Schluessel kein Update, auch nicht mit gueltigem HMAC aus dem Token-Hash
for name, einst in (("kein Schluessel", {}), ("leerer Schluessel", {"update_schluessel": ""}),
                    ("kaputter Schluessel", {"update_schluessel": "xyz"}), ("63 Zeichen", {"update_schluessel": OEFF[:63]})):
    erg, u = versuch(einst, {"version": 99, "sha256": PRUEF, "mac": mac, "ed25519": sig})
    pruef("%s: abgelehnt, mit Hinweis aufs Setup" % name, str(erg).startswith("abgelehnt") and "Setup" in str(erg), erg)
    pruef("%s: kein Schluessel zur Laufzeit geholt oder gespeichert" % name,
          "/v1/client/schluessel" not in u["abrufe"] and "GESPEICHERT" not in u["abrufe"] and einst.get("update_schluessel",
                                                                                                         None) in (None, "", "xyz", OEFF[:63]),
          (u["abrufe"], einst))

# Quelltext: der alte Weg ist ganz weg
pruef("kein schluessel_holen mehr im Client", "def schluessel_holen" not in quelle and "schluessel_holen(" not in quelle)
fn = next(n for n in baum.body if isinstance(n, ast.FunctionDef) and n.name == "update_suchen")
text = ast.get_source_segment(quelle, fn)
pruef("update_suchen ohne HMAC und ohne TOKEN_HASH", "hmac" not in text and "TOKEN_HASH" not in text and '"mac"' not in text)
pruef("GitHub-Weg prueft weiter gegen RELEASE_SCHLUESSEL", "update_signiert(RELEASE_SCHLUESSEL" in text)

print("PC-Update: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
