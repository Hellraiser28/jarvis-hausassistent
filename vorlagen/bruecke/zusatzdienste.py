"""Zusatzdienste fuer Dateien (seit 0.3.3, 26.10.2026): welcher Bildanbieter, welcher Umwandler, mit welchem Zugang.

Quelle ist die .env des Jarvis-Rechners (das Setup schreibt sie). Jeder Zugang steht dort entweder selbst (NAME=...) oder
als Pfad zu einer Datei, die nur ihn enthaelt (NAME_DATEI=/pfad), so muss er nicht ein zweites Mal kopiert werden.
Zugaenge verlassen dieses Modul nur in Richtung des jeweiligen Dienstes, nie in Antworten.

  BILD_DIENST=cloudflare|openai|gemini|aus   CLOUDFLARE_KONTO, CLOUDFLARE_TOKEN   GEMINI_SCHLUESSEL_BILDER (bezahlt)
  OPENAI_SCHLUESSEL (bezahlt)  OPENAI_BILDMODELL, OPENAI_BILDMODELL_GENAU, OPENAI_BILDQUALITAET (low|medium|high)
  BILD_TAGESLIMIT=9000                  (Neurons je Tag bei Cloudflare, gratis sind 10.000)
  TRANSMUTE_ADRESSE=http://...:3313     TRANSMUTE_SCHLUESSEL
"""
import os


def _env_datei(basis):
    werte = {}
    try:
        with open(os.path.join(basis, ".env"), encoding="utf-8") as f:
            for z in f:
                z = z.strip()
                if z and not z.startswith("#") and "=" in z:
                    k, v = z.split("=", 1)
                    werte[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return werte


def _wert(e, name):
    """NAME aus der .env, sonst aus der Datei in NAME_DATEI: entweder nur der Wert (eine Zeile) oder, wie die Dateien
    unter geheim\\ der Bauanleitung, Zeilen NAME=wert (Kommentare mit #, Leerzeichen und Anfuehrungszeichen egal)."""
    if e.get(name):
        return e[name]
    pfad = e.get(name + "_DATEI")
    if not pfad:
        return ""
    try:
        with open(os.path.expanduser(pfad), encoding="utf-8-sig") as f:
            zeilen = [z.strip() for z in f if z.strip() and not z.strip().startswith("#")]
    except OSError:
        return ""
    for z in zeilen:
        if "=" in z and z.split("=", 1)[0].strip() == name:
            return z.split("=", 1)[1].strip().strip('"').strip("'")
    return zeilen[0] if len(zeilen) == 1 and "=" not in zeilen[0] else ""


def lesen(basis):
    e = _env_datei(basis)
    cf_konto, cf_token = _wert(e, "CLOUDFLARE_KONTO"), _wert(e, "CLOUDFLARE_TOKEN")
    gemini = _wert(e, "GEMINI_SCHLUESSEL_BILDER")
    openai = _wert(e, "OPENAI_SCHLUESSEL")
    dienst = (e.get("BILD_DIENST") or ("cloudflare" if cf_konto and cf_token else "aus")).lower()
    try:
        limit = int(e.get("BILD_TAGESLIMIT") or 9000)
    except ValueError:
        limit = 9000
    return {
        "bild": {"dienst": dienst, "cf_konto": cf_konto, "cf_token": cf_token, "gemini_schluessel": gemini,
                 "openai_schluessel": openai, "openai_modell": e.get("OPENAI_BILDMODELL", ""),
                 "openai_modell_genau": e.get("OPENAI_BILDMODELL_GENAU", ""),
                 "openai_qualitaet": e.get("OPENAI_BILDQUALITAET", "") if e.get("OPENAI_BILDQUALITAET", "") in
                 ("low", "medium", "high") else "",
                 "tageslimit": max(0, min(limit, 10000)) if dienst == "cloudflare" else limit},
        "transmute": {"adresse": str(e.get("TRANSMUTE_ADRESSE") or "").rstrip("/"),
                      "schluessel": _wert(e, "TRANSMUTE_SCHLUESSEL")},
    }


def uebersicht(basis):
    """Was eingerichtet ist, ohne Zugaenge (fuer Faehigkeiten, Zahnrad, Selbsttest)."""
    c = lesen(basis)
    b, t = c["bild"], c["transmute"]
    bild_bereit = (b["dienst"] == "cloudflare" and bool(b["cf_konto"] and b["cf_token"])) or \
                  (b["dienst"] == "gemini" and bool(b["gemini_schluessel"])) or \
                  (b["dienst"] == "openai" and bool(b["openai_schluessel"]))
    return {"pdf": True, "bild": b["dienst"] if bild_bereit else "aus",
            "umwandeln": "transmute" if t["adresse"] and t["schluessel"] else "aus"}
