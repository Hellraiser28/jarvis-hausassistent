#!/usr/bin/env python3
"""Hook des Basis-Gehirns fuer die Fremdtext-Sperre (seit 0.6, siehe bruecke/fremdtext.py).

  fremdtext_hook.py vorher [de|en]   PreToolUse: PC-Werkzeuge (mcp__pc__*) sperren, wenn die laufende Frage fremden
                                     Text hat
  fremdtext_hook.py nachher [de|en]  PostToolUse: nach Websuche und lesenden PC-Werkzeugen die Frage als befleckt
                                     markieren

Das zweite Argument ist die Sprache der Meldungen (setze_sprache), ohne Angabe Deutsch.
Die Werkzeuge des eigenen Servers (mcp__jarvis__*) prueft jarvis_mcp selbst; dieser Hook deckt ab, was nicht ueber
jarvis_mcp laeuft. Eingabe: JSON des Hooks auf stdin (tool_name, tool_input als args fuer ist_ziel und ist_quelle).
Gesperrt wird mit permissionDecision "deny"; der
Grund geht ans Gehirn, das dann nachfragt.

Im Zweifel sperren (fail-closed), aber nur, solange eine Frage laeuft (fremdtext.laufende_frage): Der Hook ist nur
fuer PC-Werkzeuge eingetragen, und die Bruecke schreibt vor jeder Frage daten/ablage/aktiv/<pid>.json. Liegt dort
keine frische Datei, fuehrt gerade kein Gespraech dieses Werkzeug aus (Selbsttest, Kommandozeile); dann gibt er frei
wie bisher. Laeuft eine Frage und ist die Eingabe unlesbar, fehlt der Werkzeugname, findet der Hook den Gehirn-Prozess
nicht, ist die Datei seiner Frage unlesbar oder scheitert die Pruefung selbst, sperrt er: Eine Frage, die er nicht
zuordnen kann, koennte fremden Text gelesen haben.

Rueckgaben (Hook-Referenz von Claude Code, Stand 05.11.2026, Abschnitt "Exit code output"):
  vorher   immer 0, gesperrt wird ueber das JSON auf stdout. Stuerzt der Hook ab (Rueckgabe 1), wertet Claude Code das
           als "non-blocking error" und fuehrt das Werkzeug trotzdem aus, ausser der Hook-Eintrag hat
           "onFailure": "block" (ab Claude Code 2.1.295).
  nachher  0, wenn markiert oder nichts zu markieren ist. Scheitert das Markieren, 2 mit dem Grund auf stderr: Bei
           PostToolUse zeigt Claude Code dann die Standardfehlerausgabe dem Gehirn (das Werkzeug ist schon gelaufen).
           Jede andere Rueckgabe ungleich 0 waere nur ein Hinweis im Protokoll, den das Gehirn nie sieht.
"""
import json
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
BASIS = os.path.dirname(HIER)
# fremdtext.py: neben dem Hook (Vorlagen, einrichtung/ im Projekt: Hook, Modul und Test liegen dort zusammen, und der
# Test prueft genau diese Fassung) oder sonst unter ../bruecke (fertiges Jarvis, Hook in werkzeuge/). Mit python -I steht
# der eigene Ordner nicht von selbst im Suchpfad.
sys.path[:0] = [HIER, os.path.join(BASIS, "bruecke")]
try:
    import fremdtext as ft  # noqa: E402
    MODUL_FEHLT = ""
except Exception as e:                               # kaputte Installation: unten sperren statt abstuerzen
    ft = None
    MODUL_FEHLT = type(e).__name__

DATEN = os.environ.get("JARVIS_DATEN") or os.path.join(BASIS, "daten")
OHNE_MODUL = ("GESPERRT (Fremdtext-Prüfung nicht möglich): fremdtext.py fehlt oder ist kaputt (%s). Führ das nicht aus "
              "und sag der Person, dass die Prüfung ausgefallen ist. / BLOCKED (untrusted-text check unavailable): "
              "fremdtext.py is missing or broken (%s). Do not carry it out, tell the person the check has failed.")


def sperren(grund):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": grund}}, ensure_ascii=False))


def eingabe():
    """-> (Werkzeugname, Grund, Argumente). Grund "eingabe": stdin unlesbar oder kein JSON-Objekt; "name": kein
    Werkzeugname. Argumente: tool_input, wenn es ein Objekt ist, sonst None (dann zaehlt das ganze Werkzeug)."""
    try:
        e = json.load(sys.stdin)
    except (ValueError, AttributeError, OSError, TypeError):      # auch UnicodeDecodeError (ValueError), stdin None
        return "", "eingabe", None
    if not isinstance(e, dict):
        return "", "eingabe", None
    w, args = e.get("tool_name"), e.get("tool_input")
    args = args if isinstance(args, dict) else None
    return (w, "", args) if isinstance(w, str) and w else ("", "name", args)


def vorher(werkzeug, grund, args=None):
    if werkzeug and not ft.ist_ziel(werkzeug, args):
        return 0
    try:
        if not werkzeug:
            # Ohne Namen weiss der Hook nicht, was laufen soll. Er ist nur fuer PC-Werkzeuge eingetragen, also sperren,
            # solange eine Frage laeuft; ohne Gespraech wie bisher frei.
            if ft.laufende_frage(DATEN):
                sperren(ft.pruefung_aus(grund))
            return 0
        pid = ft.gehirn_pid(DATEN, os.getppid())
        if pid is None:
            # Kein Gehirn gefunden (z. B. ohne /proc ueber eine Shell gestartet): Ob diese Frage fremden Text hat, ist
            # unbekannt. Laeuft irgendeine Frage, sperren; sonst ist es kein Gespraech, also frei.
            if ft.laufende_frage(DATEN):
                sperren(ft.pruefung_aus("pid"))
            return 0
        if not ft.frage_lesbar(DATEN, pid):          # Datei da, aber unlesbar: Marke und Anhang unbekannt
            sperren(ft.pruefung_aus("frage"))
            return 0
        quelle = ft.befleckt(DATEN, pid, werkzeug)
    except Exception as e:                           # fail-closed: lieber nachfragen als blind ausfuehren
        sperren(ft.pruefung_aus(type(e).__name__))
        return 0
    if quelle:
        sperren(ft.rueckfrage(quelle))
    return 0


def nachher(werkzeug, grund, args=None):
    # Ohne Namen zaehlt das Ergebnis als Quelle (eingetragen ist der Hook fuer Websuche, Webabruf und PC-Werkzeuge).
    if werkzeug and not ft.ist_quelle(werkzeug, args):
        return 0
    try:
        pid = ft.gehirn_pid(DATEN, os.getppid())
        if pid is not None:
            if ft.markieren(DATEN, pid, werkzeug):
                return 0
            grund = "frage"                          # Datei der laufenden Frage gerade unlesbar
        elif not ft.laufende_frage(DATEN):
            return 0                                 # kein Gespraech: nichts zu markieren
        else:
            grund = "pid"
    except Exception as e:
        grund = type(e).__name__
    # Nicht still verschlucken: Rueckgabe 2 zeigt das dem Gehirn (PostToolUse), damit es den Rest der Frage als gesperrt
    # behandelt. Die Sperre im Werkzeug-Server greift ohne Marke nicht.
    sys.stderr.write(ft.marke_fehlt(grund) + "\n")
    return 2


def main():
    modus = sys.argv[1] if len(sys.argv) > 1 else ""
    werkzeug, grund, args = eingabe()
    if ft is None:
        if modus == "vorher":
            sperren(OHNE_MODUL % (MODUL_FEHLT, MODUL_FEHLT))
            return 0
        if modus == "nachher":
            sys.stderr.write(OHNE_MODUL % (MODUL_FEHLT, MODUL_FEHLT) + "\n")
            return 2
        return 0
    if len(sys.argv) > 2 and sys.argv[2] in ("de", "en"):
        ft.setze_sprache(sys.argv[2])
    if modus == "vorher":
        return vorher(werkzeug, grund, args)
    if modus == "nachher":
        return nachher(werkzeug, grund, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
