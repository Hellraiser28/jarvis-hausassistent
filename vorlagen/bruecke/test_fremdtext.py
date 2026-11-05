#!/usr/bin/env python3
"""Baustein fremdtext.py (Fremdtext-Sperre, seit 0.6): nach Mail, Webtext, Dokument, Anhang oder PC-Bildschirm in einer
Frage keine Ziele mehr (schalten, senden, merken, umstellen, Homelab, PC), die naechste Frage ist frei. Prueft
Einordnung, Zustand je Gehirn-Prozess, Rueckfrage (Deutsch und Englisch) und die Suche nach dem Gehirn-Prozess.
Testordner, die Datei der laufenden Frage schreibt der Test selbst (Format wie ausgabe.aktiv_schreiben), keine
Netzzugriffe."""
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import fremdtext as ft  # noqa: E402

T = tempfile.mkdtemp(prefix="fremdtext-")
AKTIV = os.path.join(T, "ablage", "aktiv")
os.makedirs(AKTIV)
ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:200]) if info and not bed else ""))


def neue_frage(pid, anfrage=None, fremd=""):
    """Wie die Bruecke vor jeder Frage: daten/ablage/aktiv/<pid>.json mit anfrage, zeit und fremd."""
    json.dump({"besitzer": "haupt", "anfrage": secrets.token_hex(8) if anfrage is None else anfrage, "zeit": time.time(),
               "fremd": fremd}, open(os.path.join(AKTIV, "%d.json" % pid), "w"))
    time.sleep(0.01)                     # eigene Startzeit je Frage (Laeufe ohne Fragenden unterscheiden sich daran)


# ---------------------------------------------------------------- Einordnung
pruef("Quelle: postfach", ft.ist_quelle("postfach") and ft.ist_quelle("mcp__jarvis__postfach"))
pruef("Quelle: dokumente, nachrichten, briefing", all(ft.ist_quelle(x) for x in ("dokumente", "nachrichten", "briefing")))
pruef("Quelle: Websuche und Webseite", ft.ist_quelle("WebSearch") and ft.ist_quelle("WebFetch"))
pruef("Quelle: PC-Bildschirm (Snapshot, Screenshot, Clipboard, Shell, Scrape)",
      all(ft.ist_quelle("mcp__pc__" + x) for x in ("Snapshot", "Screenshot", "Clipboard", "Shell", "Scrape")))
pruef("Quelle: unbekanntes PC-Werkzeug zaehlt (im Zweifel ja)", ft.ist_quelle("mcp__pc__Irgendwas"))
pruef("Keine Quelle: PC-Klick, Tippen, Scrollen", not any(ft.ist_quelle("mcp__pc__" + x) for x in ("Click", "Type", "Scroll")))
pruef("Keine Quelle: geraet_steuern, wetter", not any(ft.ist_quelle(x) for x in ("geraet_steuern", "wetter")))
pruef("Quelle: termine (Kalendertexte) und updates (Release Notes)",
      ft.ist_quelle("termine") and ft.ist_quelle("mcp__jarvis__updates"))
pruef("Ziel: homelab_auftrag, geraet_steuern, nachricht, merken, verhalten, handy, ankunft",
      all(ft.ist_ziel(x) for x in ("homelab_auftrag", "geraet_steuern", "nachricht", "merken", "verhalten", "handy", "ankunft",
                                   "mcp__jarvis__szenen")))
pruef("Ziel: jedes PC-Werkzeug", ft.ist_ziel("mcp__pc__Click") and ft.ist_ziel("mcp__pc__Snapshot"))
pruef("Kein Ziel: lesen (wetter, termine, postfach)", not any(ft.ist_ziel(x) for x in ("wetter", "termine", "postfach", "", None)))
pruef("Quellen und Ziele ueberschneiden sich nur bei updates (Release Notes lesen, dann einspielen)",
      ft.QUELLEN & ft.ZIELE == {"updates"}, ft.QUELLEN & ft.ZIELE)
pruef("Jede Quelle hat einen Klartext (de und en)", all(q in ft.NAMEN and q in ft.NAMEN_EN for q in ft.QUELLEN | ft.QUELLEN_EINGEBAUT)
      and set(ft.NAMEN) == set(ft.NAMEN_EN))

# Werkzeuge mit Wirkung (schalten, senden, schreiben, anlegen, Push, Durchsage): aus den Bausteinen der Bauanleitung und
# der Vorlage des Werkzeug-Servers (Pruefung 05.11.2026). Jedes muss nach fremdem Text gesperrt sein.
WIRKUNG = ("durchsage", "gastzugang", "gast_wlan", "gast_wlan_qr", "offene_faeden", "grundriss", "handy_suchen",
           "brief_ablegen", "fristen", "einkaufsliste", "freigabe_anfordern", "faehigkeit_wuenschen", "aufgaben", "notizen",
           "erinnerungen", "erinnern", "ankunft", "szenen", "leinwand", "quiz", "fernsehen", "merken", "vergessen",
           "gedaechtnis_datei", "oberflaeche", "verhalten", "updates", "routine", "handy", "handy_apps", "handy_bedienen",
           "homelab_auftrag", "nachricht", "termin_eintragen", "geraet_steuern", "saugroboter", "musik", "radio",
           "vorlesen", "hoerspiel", "morgenradio", "quelle_hinzufuegen", "quelle_entfernen")
fehlt = [w for w in WIRKUNG if not (ft.ist_ziel(w) and ft.ist_ziel("mcp__jarvis__" + w))]
pruef("Jedes Werkzeug mit Wirkung ist ein Ziel", not fehlt, fehlt)
pruef("bild_erzeugen ist Ziel (Kosten, Daten an Dritte), bild_bearbeiten nicht (arbeitet am fremden Anhang)",
      ft.ist_ziel("bild_erzeugen") and ft.ist_ziel("bild_erzeugen", {"beschreibung": "x"}) and not ft.ist_ziel("bild_bearbeiten"))
# LESEND im Modul: lesende Werkzeuge und die Datei-Werkzeuge, deren Ergebnis nur an das fragende Geraet geht.
frei = sorted(w for w in ft.LESEND if ft.ist_ziel(w) or ft.ist_ziel("mcp__jarvis__" + w, {}))
pruef("LESEND: keine Ziele, auch nicht mit args", not frei, frei)
pruef("LESEND, ZIELE und QUELLEN sind getrennt (nur updates ist Quelle und Ziel)",
      not (ft.LESEND & ft.ZIELE) and not (ft.LESEND & ft.QUELLEN), (ft.LESEND & ft.ZIELE, ft.LESEND & ft.QUELLEN))
pruef("Unbekanntes eigenes Werkzeug: Ziel (im Zweifel sperren)", ft.ist_ziel("mcp__jarvis__neu_erfunden")
      and ft.ist_ziel("neu_erfunden") and ft.ist_ziel("neu_erfunden", {"aktion": "zeigen"}) and not ft.ist_quelle("neu_erfunden"))
pruef("Postfach und Rezepte ohne args wie bisher kein Ziel (sie sind Quellen)",
      not ft.ist_ziel("postfach") and not ft.ist_ziel("rezepte"))
pruef("NUR_LESEN nennt nur bekannte Werkzeuge mit Parameter, Standard und Lese-Aktionen",
      all(w in ft.ZIELE | ft.QUELLEN and len(e) == 3 and e[0] and isinstance(e[2], frozenset) and e[2]
          for w, e in ft.NUR_LESEN.items()))

# ---------------------------------------------------------------- Einordnung je Aktion (args)
LESEN_JE_AKTION = [("einkaufsliste", {"aktion": "zeigen"}), ("einkaufsliste", {}), ("erinnerungen", {"aktion": "liste"}),
                   ("aufgaben", {"aktion": "zeigen"}), ("notizen", {"aktion": "suchen", "suche": "x"}),
                   ("notizen", {"aktion": "tagebuch_lesen"}), ("notizen", {"aktion": "letzte"}),
                   ("offene_faeden", {"aktion": "liste"}), ("offene_faeden", {"aktion": "alle"}),
                   ("fristen", {"aktion": "liste"}), ("fristen", {"aktion": "alle"}), ("routine", {"aktion": "status"}),
                   ("verhalten", {"aktion": "zeigen"}), ("oberflaeche", {"aktion": "zeigen"}),
                   ("updates", {"aktion": "liste"}), ("updates", {"aktion": "neuigkeiten", "name": "x"}),
                   ("updates", {"aktion": "status"}), ("szenen", {"aktion": "liste"}), ("ankunft", {"aktion": "liste"}),
                   ("gastzugang", {"aktion": "liste"}), ("saugroboter", {"aktion": "status"}),
                   ("musik", {"suche": "x", "aktion": "suchen"}), ("nachricht", {"aktion": "kontakte"}),
                   ("fernsehen", {"aktion": "apps"}), ("leinwand", {"aktion": "status"}), ("quiz", {"aktion": "stand"}),
                   ("quiz", {}), ("grundriss", {"aktion": "wo", "geraet": "x"}), ("handy_suchen", {"aktion": "wo"}),
                   ("gedaechtnis_datei", {"aktion": "ausgeben"}), ("hoerspiel", {}), ("morgenradio", {"aktion": "inhalt"}),
                   ("mcp__jarvis__einkaufsliste", {"aktion": "zeigen"}),
                   ("postfach", {"aktion": "lesen", "mail": "x"}), ("postfach", {"aktion": "wachen"}),
                   ("rezepte", {"aktion": "details", "suche": "x"})]
gesperrt_lesen = [(w, a) for w, a in LESEN_JE_AKTION if ft.ist_ziel(w, a)]
pruef("Lese-Aktionen sind mit args kein Ziel", not gesperrt_lesen, gesperrt_lesen)
SCHREIBEN_JE_AKTION = [("einkaufsliste", {"aktion": "hinzufuegen"}), ("einkaufsliste", {"aktion": "abhaken"}),
                       ("einkaufsliste", {"aktion": "entfernen"}), ("erinnerungen", {"aktion": "loeschen"}),
                       ("aufgaben", {"aktion": "neu"}), ("aufgaben", {"aktion": "erledigt"}), ("notizen", {}),
                       ("notizen", {"aktion": "tagebuch"}), ("offene_faeden", {"aktion": "neu"}),
                       ("offene_faeden", {"aktion": "einstellen"}), ("fristen", {"aktion": "erledigt"}),
                       ("routine", {"aktion": "an"}), ("routine", {"aktion": "jetzt"}), ("verhalten", {"aktion": "aendern"}),
                       ("oberflaeche", {"aktion": "vorschau"}), ("updates", {"aktion": "einspielen", "name": "alle"}),
                       ("szenen", {"aktion": "starten"}), ("szenen", {"aktion": "entwurf"}), ("ankunft", {}),
                       ("gastzugang", {"aktion": "anlegen"}), ("saugroboter", {"aktion": "finden"}), ("musik", {"suche": "x"}),
                       ("nachricht", {"aktion": "senden"}), ("nachricht", {}), ("fernsehen", {}),
                       ("leinwand", {"aktion": "zeigen"}), ("quiz", {"aktion": "start"}), ("grundriss", {"aktion": "verschieben"}),
                       ("handy_suchen", {}), ("gedaechtnis_datei", {"aktion": "uebernehmen"}), ("hoerspiel", {"aktion": "abspielen"}),
                       ("postfach", {"aktion": "verschieben"}), ("postfach", {"aktion": "beobachten"}),
                       ("postfach", {"aktion": "wache_loeschen"}), ("rezepte", {"aktion": "auf_liste"}),
                       ("einkaufsliste", {"aktion": "irgendwas"}), ("einkaufsliste", {"aktion": 7}),
                       ("geraet_steuern", {"entity_id": "x"}), ("merken", {"text": "x"}), ("handy", {"aktion": "wecker"})]
frei_schreiben = [(w, a) for w, a in SCHREIBEN_JE_AKTION if not ft.ist_ziel(w, a)]
pruef("Schreib- und unbekannte Aktionen sind mit args Ziel", not frei_schreiben, frei_schreiben)
pruef("Ohne args: ganzes Werkzeug wie bisher (einkaufsliste, updates Ziel)",
      ft.ist_ziel("einkaufsliste") and ft.ist_ziel("updates") and ft.ist_ziel("einkaufsliste", None))
pruef("Quelle je Aktion: updates nur mit neuigkeiten, ohne args ganz",
      ft.ist_quelle("updates", {"aktion": "neuigkeiten", "name": "x"}) and not ft.ist_quelle("updates", {"aktion": "liste"})
      and not ft.ist_quelle("updates", {}) and not ft.ist_quelle("updates", {"aktion": "einspielen"})
      and ft.ist_quelle("updates"))
pruef("Quelle: postfach bleibt in jeder Aktion Quelle, termine auch mit args",
      ft.ist_quelle("postfach", {"aktion": "verschieben"}) and ft.ist_quelle("postfach", {"aktion": "lesen"})
      and ft.ist_quelle("termine", {"tage": 2}))

# Wo die Werkzeugliste der Vorlage daneben liegt (Arbeitsstand): jedes Werkzeug ist ausdruecklich eingeordnet.
VORLAGE = os.path.join(os.path.dirname(HIER), "werkzeuge", "jarvis_mcp.py")
if os.path.isfile(VORLAGE):
    import ast
    baum = ast.parse(open(VORLAGE, encoding="utf-8").read())
    namen = {k.value for n in ast.walk(baum) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
             and any(getattr(z, "id", "") == "WERKZEUGE" for z in n.targets)
             for k in n.value.keys if isinstance(k, ast.Constant)}
    offen = sorted(w for w in namen if w not in ft.ZIELE | ft.QUELLEN | ft.LESEND)
    pruef("Vorlage des Werkzeug-Servers: alle %d Werkzeuge eingeordnet" % len(namen), len(namen) >= 20 and not offen, offen)

# Gegenprobe gegen die Bauanleitung (deutsch und englisch), wo sie liegt: Arbeitsstand ../release, Vorlagen ../..,
# Projekt der Person ../ (die Tests liegen dort in einrichtung/). Jedes in "### Bausteine" bzw. "### Building blocks"
# genannte Werkzeug ist ausdruecklich eingeordnet; ein neues faellt so auf, bis es eingeordnet ist.
ANLEITUNGEN = []
for ordner in (os.path.join(os.path.dirname(HIER), "release"), os.path.dirname(os.path.dirname(HIER)),
               os.path.dirname(HIER)):
    for datei in ("EINRICHTUNG.md", "EINRICHTUNG.en.md"):
        pfad = os.path.realpath(os.path.join(ordner, datei))
        if os.path.isfile(pfad) and pfad not in ANLEITUNGEN:
            ANLEITUNGEN.append(pfad)
for anleitung in ANLEITUNGEN:
    text = open(anleitung, encoding="utf-8").read()
    m = re.search(r"^### (Bausteine|Building blocks)\s*$", text, re.M)
    if not m:
        continue
    b = text.find("\n### ", m.end())
    abschnitt = re.sub(r"\s+", " ", text[m.start():b if b > 0 else None])
    genannt = set()
    for m in re.finditer(r"(?:Werkzeuge?|[Tt]ools?):? ((?:`[a-z_]+(?:\([^`]*\))?`(?:, | und | oder | and | or )?)+)",
                         abschnitt):
        genannt |= set(re.findall(r"`([a-z_]+)", m.group(1)))
    offen = sorted(w for w in genannt if w not in ft.ZIELE | ft.QUELLEN | ft.LESEND)
    pruef("Bauanleitung %s: alle %d Werkzeuge der Bausteine eingeordnet" % (os.path.basename(anleitung), len(genannt)),
          len(genannt) >= 20 and not offen, offen or genannt)
if not ANLEITUNGEN:
    print("(Bauanleitung nicht gefunden, Gegenprobe uebersprungen)")

# ---------------------------------------------------------------- Zustand je Gehirn-Prozess
P = 4242424
pruef("Ohne laufende Frage: nicht markiert", ft.markieren(T, P, "postfach") is False and ft.befleckt(T, P, "merken") == "")
neue_frage(P)
pruef("Neue Frage: frei", ft.befleckt(T, P, "geraet_steuern") == "")
pruef("Mail gelesen: markiert", ft.markieren(T, P, "mcp__jarvis__postfach") is True)
pruef("Danach geraet_steuern gesperrt (nennt die Mail)", ft.befleckt(T, P, "geraet_steuern") == "Mail")
pruef("Danach PC gesperrt", ft.befleckt(T, P, "mcp__pc__Click") == "Mail")
pruef("Marke ohne Reste geschrieben", sorted(os.listdir(AKTIV)) == ["%d.fremd" % P, "%d.json" % P], os.listdir(AKTIV))
neue_frage(P)
pruef("Naechste Frage: wieder frei", ft.befleckt(T, P, "geraet_steuern") == "" and ft.befleckt(T, P, "mcp__pc__Click") == "")
ft.markieren(T, P, "mcp__pc__Snapshot")
pruef("PC-Bildschirm: weitere PC-Schritte frei", ft.befleckt(T, P, "mcp__pc__Click") == "")
pruef("PC-Bildschirm: geraet_steuern gesperrt", ft.befleckt(T, P, "geraet_steuern") == "PC-Bildschirm")
ft.markieren(T, P, "WebSearch")
pruef("PC-Bildschirm + Websuche: PC gesperrt (Web)", ft.befleckt(T, P, "mcp__pc__Click") == "Websuche")
pruef("Beide Arten bleiben stehen", set(ft.befleckt(T, P, "merken").split(", ")) == {"PC-Bildschirm", "Websuche"})
neue_frage(P, fremd="Anhang")
pruef("Anhang: von Anfang an gesperrt, auch der PC", ft.befleckt(T, P, "nachricht") == "Anhang" and
      ft.befleckt(T, P, "mcp__pc__Type") == "Anhang")
neue_frage(P)
ft.markieren(T, P, "dokumente")
mk = json.load(open(os.path.join(AKTIV, "%d.fremd" % P)))
mk["gesetzt"] = time.time() - ft.GUELTIG_S - 5
json.dump(mk, open(os.path.join(AKTIV, "%d.fremd" % P), "w"))
pruef("Uralte Marke zaehlt nicht mehr", ft.befleckt(T, P, "merken") == "")
neue_frage(P, anfrage="")
ft.markieren(T, P, "nachrichten")
pruef("Lauf ohne Fragenden (Routine): gesperrt", ft.befleckt(T, P, "vorlesen") == "Nachrichten")
neue_frage(P, anfrage="")
pruef("Naechster Lauf ohne Fragenden: frei (Startzeit unterscheidet)", ft.befleckt(T, P, "vorlesen") == "")
neue_frage(P)
ft.markieren(T, P, "mcp__jarvis__unbekannt")
pruef("Unbekannte Art: als fremder Text benannt", ft.befleckt(T, P, "merken") == "fremder Text")
open(os.path.join(AKTIV, "%d.json" % P), "w").write("kaputt")
pruef("Kaputte frische Datei der laufenden Frage: gesperrt wie im Hook, keine Marke",
      ft.befleckt(T, P, "merken") == "Datei der laufenden Frage unlesbar" and ft.markieren(T, P, "postfach") is False)
ALT_P = time.time() - ft.GUELTIG_S - 60
os.utime(os.path.join(AKTIV, "%d.json" % P), (ALT_P, ALT_P))
pruef("Kaputte alte Datei (kein laufendes Gespraech): keine Sperre", ft.befleckt(T, P, "merken") == "")
os.remove(os.path.join(AKTIV, "%d.json" % P))
pruef("Fehlende Datei: keine Sperre", ft.befleckt(T, P, "merken") == "")
r = ft.rueckfrage("Mail")
pruef("Rueckfrage nennt Quelle und verlangt Nachfrage", r.startswith("GESPERRT (Fremdtext-Sperre)") and "(Mail)" in r and "frag" in r, r)
pruef("Rueckfrage ohne Quelle", "(fremder Text)" in ft.rueckfrage(""))
neue_frage(P)
ft.markieren(T, P, "termine")
pruef("Kalender gelesen: termin_eintragen gesperrt (nennt den Kalender)", ft.befleckt(T, P, "termin_eintragen") == "Kalender")
neue_frage(P)
pruef("updates: erster Aufruf frei", ft.befleckt(T, P, "updates") == "")
ft.markieren(T, P, "mcp__jarvis__updates")
pruef("updates: nach Release Notes ist ein weiterer Aufruf (einspielen) gesperrt",
      ft.befleckt(T, P, "updates") == "Release Notes" and ft.befleckt(T, P, "geraet_steuern") == "Release Notes")


def aufruf(pid, name, args):
    """Wie die Aufrufstelle im Werkzeug-Server: ist_ziel(n, args) und befleckt sperren, sonst laeuft das Werkzeug; liefert
    es fremden Text (ist_quelle(n, args)), wird markiert. -> "gesperrt (<Quelle>)" oder "lief"."""
    if ft.ist_ziel(name, args):
        quelle = ft.befleckt(T, pid, name)
        if quelle:
            return "gesperrt (%s)" % quelle
    if ft.ist_quelle(name, args):
        ft.markieren(T, pid, name)
    return "lief"


# Tagesabschluss (Routine ohne Fragenden): Termine, dann Einkaufsliste zeigen und Erinnerungen auflisten
neue_frage(P, anfrage="")
ablauf = [aufruf(P, "mcp__jarvis__termine", {"tage": 1}), aufruf(P, "mcp__jarvis__einkaufsliste", {"aktion": "zeigen"}),
          aufruf(P, "mcp__jarvis__erinnerungen", {"aktion": "liste"}), aufruf(P, "mcp__jarvis__einkaufsliste", {})]
pruef("Tagesabschluss: termine, einkaufsliste zeigen, erinnerungen liste laufen durch", ablauf == ["lief"] * 4, ablauf)
pruef("Tagesabschluss: die Frage ist trotzdem befleckt, Schreiben bleibt gesperrt",
      aufruf(P, "mcp__jarvis__einkaufsliste", {"aktion": "hinzufuegen", "artikel": ["Milch"]}) == "gesperrt (Kalender)"
      and aufruf(P, "mcp__jarvis__erinnerungen", {"aktion": "loeschen", "suche": "x"}) == "gesperrt (Kalender)")
neue_frage(P)
ablauf = [aufruf(P, "updates", {"aktion": "liste"}), ft.befleckt(T, P, "merken"),
          aufruf(P, "updates", {"aktion": "neuigkeiten", "name": "x"}),
          aufruf(P, "updates", {"aktion": "status"}), aufruf(P, "updates", {"aktion": "einspielen", "name": "x"})]
pruef("updates je Aktion: liste markiert nicht, neuigkeiten markiert, status frei, einspielen gesperrt",
      ablauf == ["lief", "", "lief", "lief", "gesperrt (Release Notes)"], ablauf)
neue_frage(P)
ablauf = [aufruf(P, "postfach", {"aktion": "neu"}), aufruf(P, "postfach", {"aktion": "lesen", "mail": "INBOX:1"}),
          aufruf(P, "postfach", {"aktion": "verschieben", "mail": "INBOX:1", "ziel": "Archiv"})]
pruef("postfach je Aktion: lesen nach lesen frei, verschieben nach Mail gesperrt",
      ablauf == ["lief", "lief", "gesperrt (Mail)"], ablauf)
neue_frage(P)
pruef("postfach verschieben ohne fremden Text: frei", aufruf(P, "postfach", {"aktion": "verschieben"}) == "lief")

# ---------------------------------------------------------------- Laeuft gerade eine Frage? (fuer den Hook)
L = tempfile.mkdtemp(prefix="fremdtext-lauf-")
LA = os.path.join(L, "ablage", "aktiv")
pruef("Laufende Frage: ohne Ordner keine", ft.laufende_frage(L) is False)
os.makedirs(LA)
pruef("Laufende Frage: leerer Ordner keine", ft.laufende_frage(L) is False)
json.dump({"anfrage": "x", "zeit": time.time() - ft.GUELTIG_S - 60}, open(os.path.join(LA, "77.json"), "w"))
open(os.path.join(LA, "77.fremd"), "w").write("{}")
pruef("Laufende Frage: alte Frage eines warmen Gehirns zaehlt nicht", ft.laufende_frage(L) is False)
json.dump({"anfrage": "y", "zeit": time.time()}, open(os.path.join(LA, "78.json"), "w"))
pruef("Laufende Frage: frische Frage", ft.laufende_frage(L) is True)
os.remove(os.path.join(LA, "78.json"))
open(os.path.join(LA, "79.json"), "w").write("kaputt")
pruef("Laufende Frage: unlesbare frische Datei zaehlt (Aenderungszeit)", ft.laufende_frage(L) is True)
ALT = time.time() - ft.GUELTIG_S - 60
os.utime(os.path.join(LA, "79.json"), (ALT, ALT))
pruef("Laufende Frage: unlesbare alte Datei zaehlt nicht", ft.laufende_frage(L) is False)
if hasattr(os, "geteuid") and os.geteuid() != 0:          # root liest jeden Ordner
    os.chmod(LA, 0)
    pruef("Laufende Frage: unlesbarer Ordner zaehlt als laufend (im Zweifel sperren)", ft.laufende_frage(L) is True)
    os.chmod(LA, 0o700)
pruef("Frage lesbar: kaputte Datei nein, fehlende nein", not ft.frage_lesbar(L, 79) and not ft.frage_lesbar(L, 78)
      and ft.frage_lesbar(L, 77))

# ---------------------------------------------------------------- Gehirn-Prozess finden (Hook laeuft als Kind von claude)
ICH = os.getpid()
neue_frage(ICH)
pruef("Gehirn: eigener Prozess mit laufender Frage", ft.gehirn_pid(T, ICH) == ICH)
pruef("Gehirn: Unsinn und Prozess 1 -> None", ft.gehirn_pid(T, 1) is None and ft.gehirn_pid(T, 0) is None)


def frage_mit(pid, **felder):
    eintrag = {"besitzer": "haupt", "anfrage": secrets.token_hex(8), "zeit": time.time(), "fremd": ""}
    eintrag.update(felder)
    json.dump(eintrag, open(os.path.join(AKTIV, "%d.json" % pid), "w"))


frage_mit(ICH, zeit=time.time() - ft.GUELTIG_S - 60)
pruef("Gehirn: veraltete Datei (PID vielleicht laengst vergeben) zaehlt nicht", ft.gehirn_pid(T, ICH) is None)
open(os.path.join(AKTIV, "%d.json" % ICH), "w").write("kaputt")
pruef("Gehirn: unlesbare frische Datei zaehlt (der Hook sperrt dann)", ft.gehirn_pid(T, ICH) == ICH)
ALT_ICH = time.time() - ft.GUELTIG_S - 60
os.utime(os.path.join(AKTIV, "%d.json" % ICH), (ALT_ICH, ALT_ICH))
pruef("Gehirn: unlesbare alte Datei zaehlt nicht", ft.gehirn_pid(T, ICH) is None)
START = ft.prozess_start(ICH)
if START is not None:                                  # nur mit /proc
    frage_mit(ICH, prozess_start=START + 1)
    pruef("Gehirn: falsche Startzeit (fremder Prozess mit derselben PID) zaehlt nicht", ft.gehirn_pid(T, ICH) is None)
    frage_mit(ICH, prozess_start=START)
    pruef("Gehirn: passende Startzeit", ft.gehirn_pid(T, ICH) == ICH)
    try:
        import ausgabe
        ausgabe.aktiv_schreiben(T, ICH, "haupt", "pruefung42")
        a = json.load(open(os.path.join(AKTIV, "%d.json" % ICH)))
        pruef("ausgabe.aktiv_schreiben schreibt dieselbe Startzeit mit", a.get("prozess_start") == START
              and ausgabe.prozess_start(ICH) == START and ft.gehirn_pid(T, ICH) == ICH, a)
    except ImportError:
        print("(ausgabe.py nicht daneben, Pruefung der Startzeit beim Schreiben uebersprungen)")
else:
    pruef("Ohne /proc: keine Startzeit, Verhalten wie bisher", ft.prozess_start(ICH) is None)
neue_frage(ICH)
if os.path.exists("/proc/self/stat"):                 # die Elternkette gibt es nur ueber /proc (Linux)
    code = ("import sys, os; sys.path.insert(0, %r); import fremdtext as ft; print(ft.gehirn_pid(%r, os.getpid()))"
            % (os.path.dirname(ft.__file__), T))
    kind = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, timeout=30)
    pruef("Gehirn: aus einem Kindprozess gefunden", kind.stdout.strip() == str(ICH), kind.stdout + kind.stderr)
    kind = subprocess.run(["/bin/sh", "-c", "%s -I -B -c %s" % (sys.executable, json.dumps(code))], capture_output=True,
                          text=True, timeout=30)
    pruef("Gehirn: auch ueber eine Shell dazwischen", kind.stdout.strip() == str(ICH), kind.stdout + kind.stderr)
    frage_mit(ICH, zeit=time.time() - ft.GUELTIG_S - 60)
    kind = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, timeout=30)
    pruef("Gehirn: aus dem Kindprozess, veraltete Datei des Elternprozesses -> keiner", kind.stdout.strip() == "None",
          kind.stdout + kind.stderr)
    frage_mit(ICH, prozess_start=START + 1)
    kind = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, timeout=30)
    pruef("Gehirn: aus dem Kindprozess, falsche Startzeit des Elternprozesses -> keiner", kind.stdout.strip() == "None",
          kind.stdout + kind.stderr)
    os.remove(os.path.join(AKTIV, "%d.json" % ICH))
    kind = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, timeout=30)
    pruef("Gehirn: ohne laufende Frage keiner", kind.stdout.strip() == "None", kind.stdout + kind.stderr)

# ---------------------------------------------------------------- Hook (fremdtext_hook.py) als eigener Prozess
# Arbeitsstand: werkzeuge/fremdtext_hook.py, in den Vorlagen liegt er neben fremdtext.py.
BASIS = os.path.dirname(HIER)
HOOK = next((h for h in (os.path.join(BASIS, "werkzeuge", "fremdtext_hook.py"),
                         os.path.join(BASIS, "bruecke", "fremdtext_hook.py"), os.path.join(HIER, "fremdtext_hook.py"))
             if os.path.isfile(h)), None)
if HOOK:
    H = tempfile.mkdtemp(prefix="fremdtext-hook-")
    HA = os.path.join(H, "ablage", "aktiv")
    os.makedirs(HA)
    UMG = dict(os.environ, JARVIS_DATEN=H)

    def hook(modus, eingabe, *weitere):
        """Hook direkt als Kind dieses Prozesses: sein Elternprozess ist der Test (gefunden auch ohne /proc)."""
        roh = (json.dumps(eingabe) if isinstance(eingabe, dict) else eingabe)
        roh = roh.encode("utf-8") if isinstance(roh, str) else roh
        p = subprocess.run([sys.executable, "-I", "-B", HOOK, modus] + list(weitere), input=roh, capture_output=True,
                           env=UMG, timeout=30)
        return p.returncode, p.stdout.decode("utf-8", "replace").strip(), p.stderr.decode("utf-8", "replace").strip()

    def gesperrt(aus):
        """Begruendung der Sperre (permissionDecision deny) oder ""."""
        try:
            d = json.loads(aus)["hookSpecificOutput"]
            return d["permissionDecisionReason"] if d["permissionDecision"] == "deny" and \
                d["hookEventName"] == "PreToolUse" else ""
        except (ValueError, KeyError, TypeError):
            return ""

    def hook_frage(pid, alter=0.0):
        json.dump({"besitzer": "haupt", "anfrage": secrets.token_hex(8), "zeit": time.time() - alter, "fremd": ""},
                  open(os.path.join(HA, "%d.json" % pid), "w"))

    def hook_leeren():
        for n in os.listdir(HA):
            pfad = os.path.join(HA, n)
            (os.rmdir if os.path.isdir(pfad) else os.remove)(pfad)

    ICH = os.getpid()
    hook_frage(ICH)
    rc, aus, err = hook("vorher", {"tool_name": "mcp__pc__Click"})
    pruef("Hook vorher: freie Frage, PC-Klick laeuft (keine Ausgabe)", rc == 0 and aus == "", (rc, aus, err))
    rc, aus, err = hook("nachher", {"tool_name": "WebSearch"})
    pruef("Hook nachher: Websuche markiert", rc == 0 and err == "" and ft.befleckt(H, ICH, "merken") == "Websuche",
          (rc, aus, err))
    rc, aus, err = hook("vorher", {"tool_name": "mcp__pc__Type"})
    pruef("Hook vorher: nach der Websuche PC gesperrt, mit Rueckfrage", rc == 0
          and gesperrt(aus).startswith("GESPERRT (Fremdtext-Sperre)") and "(Websuche)" in gesperrt(aus), aus)
    rc, aus, err = hook("vorher", {"tool_name": "mcp__pc__Type", "tool_input": {"text": "hallo"}})
    pruef("Hook vorher: mit tool_input (args) ebenso gesperrt", rc == 0 and "(Websuche)" in gesperrt(aus), (rc, aus, err))
    rc, aus, err = hook("vorher", {"tool_name": "mcp__pc__Type"}, "en")
    pruef("Hook vorher: Sprache als zweites Argument", gesperrt(aus).startswith("BLOCKED (untrusted-text lock)")
          and "(web search)" in gesperrt(aus), aus)
    hook_frage(ICH)
    rc, aus, err = hook("nachher", {"tool_name": "mcp__pc__Click"})
    pruef("Hook nachher: Klick markiert nichts", rc == 0 and ft.befleckt(H, ICH, "merken") == "", (rc, aus, err))
    rc, aus, err = hook("vorher", "kaputt{")
    pruef("Hook vorher: unlesbare Eingabe bei laufender Frage gesperrt", rc == 0
          and gesperrt(aus).startswith("GESPERRT (Fremdtext-Prüfung nicht möglich)") and "unlesbar" in gesperrt(aus), aus)
    rc, aus, err = hook("vorher", b"\xff\xfe\x00{")
    pruef("Hook vorher: kaputte Kodierung gesperrt", rc == 0 and "nicht möglich" in gesperrt(aus), (rc, aus, err))
    rc, aus, err = hook("vorher", "")
    pruef("Hook vorher: leere Eingabe gesperrt", rc == 0 and "nicht möglich" in gesperrt(aus), (rc, aus, err))
    rc, aus, err = hook("vorher", "[1, 2]")
    pruef("Hook vorher: kein JSON-Objekt gesperrt", rc == 0 and "unlesbar" in gesperrt(aus), aus)
    rc, aus, err = hook("vorher", {"tool_name": ""})
    pruef("Hook vorher: leerer Werkzeugname gesperrt", rc == 0 and "kein Werkzeugname" in gesperrt(aus), aus)
    rc, aus, err = hook("vorher", {"tool_name": None, "tool_input": {}})
    pruef("Hook vorher: Werkzeugname fehlt gesperrt", rc == 0 and "kein Werkzeugname" in gesperrt(aus), aus)
    rc, aus, err = hook("nachher", "kaputt{")
    pruef("Hook nachher: unlesbare Eingabe markiert vorsichtshalber", rc == 0
          and ft.befleckt(H, ICH, "merken") == "fremder Text", (rc, aus, err))

    hook_leeren()
    hook_frage(4242424)                       # laeuft fuer ein anderes Gehirn, dieses hier findet der Hook nicht
    rc, aus, err = hook("vorher", {"tool_name": "mcp__pc__Click"})
    pruef("Hook vorher: kein Gehirn gefunden, eine Frage laeuft -> gesperrt", rc == 0
          and "Gehirn-Prozess nicht gefunden" in gesperrt(aus), (rc, aus, err))
    rc, aus, err = hook("nachher", {"tool_name": "WebFetch"})
    pruef("Hook nachher: kein Gehirn gefunden, eine Frage laeuft -> Rueckgabe 2, Grund auf stderr", rc == 2 and aus == ""
          and err.startswith("GESPERRT (Fremdtext-Sperre)") and "Gehirn-Prozess nicht gefunden" in err, (rc, aus, err))
    rc, aus, err = hook("nachher", {"tool_name": "WebFetch"}, "en")
    pruef("Hook nachher: Meldung englisch", rc == 2 and err.startswith("BLOCKED (untrusted-text lock)")
          and "brain process not found" in err, err)
    hook_leeren()
    hook_frage(4242424, alter=ft.GUELTIG_S + 60)    # warmes Gehirn, seine letzte Frage ist lange vorbei
    rc, aus, err = hook("vorher", {"tool_name": "mcp__pc__Click"})
    pruef("Hook vorher: kein Gehirn, keine laufende Frage -> frei wie bisher", rc == 0 and aus == "", (rc, aus, err))
    rc, aus, err = hook("vorher", "kaputt{")
    pruef("Hook vorher: unlesbare Eingabe ohne laufende Frage -> frei", rc == 0 and aus == "", (rc, aus, err))
    rc, aus, err = hook("vorher", {"tool_name": ""})
    pruef("Hook vorher: leerer Name ohne laufende Frage -> frei", rc == 0 and aus == "", (rc, aus, err))
    rc, aus, err = hook("nachher", {"tool_name": "WebSearch"})
    pruef("Hook nachher: ohne laufende Frage nichts zu markieren (0)", rc == 0 and err == "", (rc, aus, err))
    hook_leeren()
    rc, aus, err = hook("vorher", "kaputt{")
    pruef("Hook vorher: leerer Ordner -> frei", rc == 0 and aus == "", (rc, aus, err))

    hook_frage(ICH)
    os.mkdir(os.path.join(HA, "%d.fremd" % ICH))   # die Marke laesst sich nicht schreiben
    rc, aus, err = hook("nachher", {"tool_name": "WebSearch"})
    pruef("Hook nachher: Markieren scheitert -> Rueckgabe 2, nicht verschluckt", rc == 2 and "fehlgeschlagen" in err,
          (rc, aus, err))
    hook_leeren()
    open(os.path.join(HA, "%d.json" % ICH), "w").write("kaputt")
    rc, aus, err = hook("nachher", {"tool_name": "mcp__pc__Snapshot"})
    pruef("Hook nachher: Datei der laufenden Frage unlesbar -> Rueckgabe 2", rc == 2
          and "Datei der laufenden Frage unlesbar" in err, (rc, aus, err))
    rc, aus, err = hook("vorher", {"tool_name": "mcp__pc__Click"})
    pruef("Hook vorher: Datei der laufenden Frage unlesbar -> gesperrt", rc == 0
          and "Datei der laufenden Frage unlesbar" in gesperrt(aus), (rc, aus, err))
    rc, aus, err = hook("unbekannt", {"tool_name": "mcp__pc__Click"})
    pruef("Hook: unbekannter Modus tut nichts", rc == 0 and aus == "" and err == "", (rc, aus, err))
else:
    print("(fremdtext_hook.py nicht gefunden, Hook-Pruefungen uebersprungen)")

# ---------------------------------------------------------------- Englisch
try:
    ft.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", True)
ft.setze_sprache("en")
neue_frage(P)
ft.markieren(T, P, "postfach")
ft.markieren(T, P, "mcp__pc__Snapshot")
pruef("EN: Klartext der Quellen", set(ft.befleckt(T, P, "merken").split(", ")) == {"e-mail", "PC screen"}
      and ft.befleckt(T, P, "mcp__pc__Click") == "e-mail", ft.befleckt(T, P, "merken"))
neue_frage(P, fremd="Anhang")
pruef("EN: Anhang", ft.befleckt(T, P, "nachricht") == "attachment")
r = ft.rueckfrage("e-mail")
pruef("EN: Rueckfrage", r.startswith("BLOCKED (untrusted-text lock): In this question you have read untrusted text (e-mail).")
      and "ask whether you should do it" in r and "%" not in r, r)
pruef("EN: Rueckfrage ohne Quelle", "(untrusted text)" in ft.rueckfrage(None))
ft.setze_sprache("de")
pruef("Zurueck auf Deutsch", ft.rueckfrage("Mail").startswith("GESPERRT"))

# Nachpruefung 05.11.2026 (M1-Rest): Lesen nur bei exaktem Namen, jede Abweichung ist Ziel
falsch = []
for w, (param, standard, lesend) in sorted(ft.NUR_LESEN.items()):
    for r in sorted(lesend):
        if ft.ist_ziel(w, {param: r}):
            falsch.append((w, r, "exakt gesperrt"))
        for abw in {r.upper(), r.capitalize(), " " + r, r + "\n"} - {r}:
            if not ft.ist_ziel(w, {param: abw}):
                falsch.append((w, abw, "Abweichung frei"))
    for schlecht in ("", " ", ["%s" % standard], 1):
        if not ft.ist_ziel(w, {param: schlecht}):
            falsch.append((w, schlecht, "leer/kein Text frei"))
    if ft.ist_ziel(w, {}) != (standard not in lesend) or ft.ist_ziel(w, {param: None}) != (standard not in lesend):
        falsch.append((w, None, "fehlende Aktion nicht wie Standard"))
    if not ft.ist_ziel(w, [param, standard]):
        falsch.append((w, "liste", "args ohne dict frei"))
pruef("Streng je Aktion: exakter Lesename frei, Schreibweise/Leerzeichen/leer/kein Text/kein dict gesperrt",
      not falsch, falsch[:6])
pruef("handy_suchen \"WO\" und musik \" suchen\" sind Ziel",
      all(ft.ist_ziel(w, {ft.NUR_LESEN[w][0]: a}) for w, a in (("handy_suchen", "WO"), ("musik", " suchen"))
          if w in ft.NUR_LESEN))
pruef("Quelle bleibt grosszuegig: updates \" Neuigkeiten\" ist Quelle",
      ft.ist_quelle("updates", {"aktion": " Neuigkeiten"}) is True)

print("Fremdtext-Sperre: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
