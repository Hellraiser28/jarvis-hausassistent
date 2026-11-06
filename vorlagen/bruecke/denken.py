"""Denkauftraege ohne Gespraech (seit 0.7, Superhirn).

Ein Aufruf von Claude Code im Druckmodus (claude -p), ohne Projektkontext und ohne Werkzeuge, ausser ein Aufrufer
erlaubt ausdruecklich WebSearch. Der Befehl ist einstellbar: JARVIS_DENKEN_BEFEHL (Standard: claude aus dem PATH). Ein
eigenes Hilfsskript davor (z. B. eines, das einen API-Schluessel nur fuer diesen Aufruf setzt) darf Hinweiszeilen mit
"[claude-api]" ausgeben; die werden gesondert gewertet (siehe _aufruf). Ein gesetzter ANTHROPIC_API_KEY wird
durchgereicht, sonst nutzt claude seine eigene Anmeldung.
Kosten landen wie bei den Gehirnen in daten/kosten.jsonl (quelle "superhirn:<zweck>"), sodass das Werkzeug kosten sie
mitzaehlt. Ein Tageslimit (SUPERHIRN_TAGESLIMIT_USD, Standard 2 $) schuetzt das Guthaben vor einer Endlosschleife.

Haertung nach den Sicherheitspruefungen vor 0.7:
  M2  claude startet wie das Basis-Gehirn: nur Projekt-Einstellungen (in einem leeren Ordner: keine Plugins, keine
      Hooks), keine MCP-Server (--strict-mcp-config mit leerer Liste), --permission-mode dontAsk, nur die erlaubten
      Werkzeuge (--tools/--allowedTools), minimale Umgebung (nichts aus der Umgebung der Bruecke). WebFetch ist nicht
      mehr erlaubt: es holt Adressen vom NAS aus und koennte damit das Heimnetz erreichen.
  K7  Der Auftrag geht ueber die Standardeingabe, nie in die Befehlszeile: die ist fuer alle Prozesse auf dem Rechner
      lesbar (/proc/<pid>/cmdline).
  K12 Fuer ein eigenes Hilfsskript: CLAUDE_API_OHNE_ABO=1 bittet es, nicht auf eine geteilte Abo-Anmeldung
      auszuweichen; meldet es "[claude-api] ... kein Rueckfall auf das Abo", scheitert der Aufruf ohne Kosten.
  M3  Das Tageslimit ist fail-closed: Vor jedem Aufruf wird unter Sperre (Faden + Datei) der Hoechstbetrag der Stufe
      reserviert (daten/denken_reserviert.json), danach mit den echten Kosten verrechnet. Ohne Kostenangabe (Zeitueber-
      schreitung, kein JSON) bleibt die Reservierung fuer den Tag stehen. Unlesbare Kosten- oder Reservierungsdatei:
      ablehnen. Zeitueberschreitung beendet die ganze Prozessgruppe (claude-api.sh startet claude ohne exec).

Tests setzen ERSATZ = callable(auftrag, system, modell, werkzeuge) -> text; dann laeuft nichts nach aussen.
Python 3.8, nur Standardbibliothek.
"""
import contextlib
import datetime as dt
import fcntl
import json
import os
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading

HELFER = os.environ.get("JARVIS_DENKEN_BEFEHL") or shutil.which("claude") or "claude"
MODELLE = {"schnell": "claude-haiku-5-5", "normal": "claude-sonnet-5-5", "gruendlich": "claude-opus-5-5"}
ERLAUBTE_WERKZEUGE = ("WebSearch",)
TAGESLIMIT_USD = float(os.environ.get("SUPERHIRN_TAGESLIMIT_USD", "2.0"))
# Reservierung je Aufruf: die realistische Hoechstkosten EINES Aufrufs, damit keiner teurer wird als reserviert
# (Nachpruefung, M3: bei --max-turns 1 greift --max-budget-usd nicht, eine lange Antwort kann die
# Reservierung sonst uebersteigen). "normal" (Sonnet) deckt die ueblichen JSON- und Code-Antworten (Schmiede bis 400
# Zeilen, Lernkarten, Abenteuer-Plan: je grob 0,10 bis 0,20 $). Groessere oder kleinere Einzelfaelle geben eine eigene
# reserve_usd mit: zeigen 1,20 $ (HTML bis 250 KB, zeigen.py), Kabinett-Stimmen 0,15 $ (kabinett.py). gruendlich (Opus)
# wird derzeit von keinem Modul genutzt. Die Reservierung wird nach dem Aufruf sofort durch die echten Kosten ersetzt;
# ein hoher Wert kostet nur Gleichzeitigkeit gegen das Tageslimit, kein Geld.
RESERVE_USD = {"schnell": 0.08, "normal": 0.50, "gruendlich": 1.00}
WEB_ZUSCHLAG_USD = 0.15
UNLESBAR_USD = RESERVE_USD["normal"]   # unlesbare Superhirn-Zeile von heute: so viel zaehlt sie
RESERVIERT = "denken_reserviert.json"
ERSATZ = None                     # Tests: callable(auftrag, system, modell, werkzeuge) -> text
_sperre = threading.Lock()
SPRACHE = "de"                    # seit 0.7: Meldungen an Menschen Deutsch oder Englisch (setze_sprache)


def setze_sprache(sprache):
    """Sprache der Meldungen: "de" oder "en" (die Bruecke ruft das beim Start, superhirn.setze_sprache tut es mit)."""
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


class Abgelehnt(RuntimeError):
    """Tageslimit erreicht, Buchfuehrung unlesbar oder Aufruf nicht erlaubt."""


class _Fehlschlag(RuntimeError):
    """Aufruf gescheitert; kosten bekannt (float) oder unbekannt (None)."""

    def __init__(self, text, kosten=None, weg="?"):
        RuntimeError.__init__(self, text)
        self.kosten, self.weg = kosten, weg


def json_aus(text):
    """Erstes JSON-Objekt (oder -Feld) aus einer Antwort; Claude schreibt manchmal Text oder ```json drumherum."""
    t = str(text or "")
    for auf, zu in (("{", "}"), ("[", "]")):
        a, b = t.find(auf), t.rfind(zu)
        if a >= 0 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except ValueError:
                continue
    raise ValueError("kein JSON in der Antwort")


# ---------------------------------------------------------------- Buchfuehrung (M3)
@contextlib.contextmanager
def _buchsperre(daten):
    """Faden- und Dateisperre um Pruefen + Reservieren (mehrere Faeden der Bruecke, im Notfall auch Prozesse)."""
    with _sperre:
        fd = os.open(os.path.join(daten, ".denken.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _gebucht_heute(daten, tag):
    s = 0.0
    try:
        f = open(os.path.join(daten, "kosten.jsonl"), encoding="utf-8")
    except FileNotFoundError:
        return 0.0
    except OSError as e:
        raise Abgelehnt(_t("Kostenbuch nicht lesbar (%s), deshalb denke ich vorsichtshalber nicht nach.",
                           "Cost ledger not readable (%s), so to be safe I won't think about it.") % type(e).__name__)
    with f:
        try:
            for z in f:
                if '"superhirn:' not in z or tag not in z:
                    continue
                try:
                    x = json.loads(z)
                except ValueError:
                    s += UNLESBAR_USD                       # halbe oder kaputte Zeile: lieber zu viel zaehlen
                    continue
                if str(x.get("zeit", "")).startswith(tag) and str(x.get("quelle", "")).startswith("superhirn:"):
                    c = x.get("total_cost_usd")
                    if isinstance(c, (int, float)) and not isinstance(c, bool) and c >= 0:
                        s += c
                    else:
                        s += UNLESBAR_USD
        except (OSError, UnicodeDecodeError) as e:
            raise Abgelehnt(_t("Kostenbuch nicht lesbar (%s), deshalb denke ich vorsichtshalber nicht nach.",
                               "Cost ledger not readable (%s), so to be safe I won't think about it.")
                            % type(e).__name__)
    return s


def _reservierungen(daten):
    try:
        with open(os.path.join(daten, RESERVIERT), encoding="utf-8") as f:
            r = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, UnicodeDecodeError) as e:
        raise Abgelehnt(_t("Reservierungen fürs Nachdenken nicht lesbar (%s), deshalb denke ich vorsichtshalber nicht "
                           "nach.", "Reservations for thinking not readable (%s), so to be safe I won't think about "
                           "it.") % type(e).__name__)
    if not isinstance(r, dict):
        raise Abgelehnt(_t("Reservierungen fürs Nachdenken unlesbar, deshalb denke ich vorsichtshalber nicht nach.",
                           "Reservations for thinking unreadable, so to be safe I won't think about it."))
    return r


def _reservierungen_speichern(daten, r):
    ziel = os.path.join(daten, RESERVIERT)
    tmp = ziel + ".tmp%d" % os.getpid()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        json.dump(r, f)
    os.replace(tmp, ziel)


def heute_ausgegeben(daten, jetzt=None):
    """Gebuchte Superhirn-Kosten heute plus offene Reservierungen von heute. Wirft Abgelehnt, wenn etwas unlesbar ist."""
    tag = (jetzt or dt.datetime.now()).strftime("%Y-%m-%d")
    offen = sum(float(v.get("betrag") or 0) for v in _reservierungen(daten).values()
                if isinstance(v, dict) and str(v.get("tag")) == tag)
    return _gebucht_heute(daten, tag) + offen


def _reservieren(daten, zweck, betrag):
    tag = dt.datetime.now().strftime("%Y-%m-%d")
    with _buchsperre(daten):
        r = _reservierungen(daten)
        r = {k: v for k, v in r.items() if isinstance(v, dict) and str(v.get("tag")) == tag}   # alte Tage weg
        stand = _gebucht_heute(daten, tag) + sum(float(v.get("betrag") or 0) for v in r.values())
        if stand + betrag > TAGESLIMIT_USD:
            raise Abgelehnt(_t("Tageslimit fürs Nachdenken erreicht (%.2f von %.2f $). Morgen wieder.",
                               "Daily limit for thinking reached ($%.2f of $%.2f). Back tomorrow.")
                            % (stand, TAGESLIMIT_USD))
        rid = secrets.token_hex(6)
        r[rid] = {"tag": tag, "betrag": round(betrag, 4), "zweck": str(zweck or "?")[:40],
                  "zeit": dt.datetime.now().isoformat(timespec="seconds"), "status": "laeuft"}
        _reservierungen_speichern(daten, r)
    return rid


def _verrechnen(daten, rid, zweck, modell, weg, kosten):
    """Reservierung durch die echten Kosten ersetzen (Zeile in kosten.jsonl)."""
    zeile = {"zeit": dt.datetime.now().isoformat(timespec="seconds"), "quelle": "superhirn:" + str(zweck or "?")[:40],
             "modus": "denken", "weg": weg, "modell": modell, "total_cost_usd": round(max(0.0, float(kosten or 0)), 6)}
    with _buchsperre(daten):
        fd = os.open(os.path.join(daten, "kosten.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with open(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(zeile, ensure_ascii=False) + "\n")
        r = _reservierungen(daten)
        r.pop(rid, None)
        _reservierungen_speichern(daten, r)


def _stehen_lassen(daten, rid, grund):
    """Kosten unbekannt: Reservierung zaehlt fuer heute weiter (fail-closed)."""
    try:
        with _buchsperre(daten):
            r = _reservierungen(daten)
            if rid in r:
                r[rid]["status"] = "unklar: " + str(grund)[:60]
                _reservierungen_speichern(daten, r)
    except Exception:                 # Reservierung steht ohnehin schon in der Datei
        pass


# ---------------------------------------------------------------- Aufruf (M2, K7)
def _umgebung(tmp):
    env = {"HOME": os.environ.get("HOME") or os.path.expanduser("~"), "PATH": "/usr/local/bin:/usr/bin:/bin",
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TMPDIR": tmp, "CLAUDE_API_AUFRUFER": "jarvis-denken",
           "CLAUDE_API_STDIN": "1",
           # K12: ein eigenes Hilfsskript soll nicht auf eine geteilte Abo-Anmeldung ausweichen (siehe Kopf)
           "CLAUDE_API_OHNE_ABO": "1"}
    for k in ("TZ", "USER", "LOGNAME", "ANTHROPIC_API_KEY"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def argumente(modell, werkzeuge, system, budget=None):
    """Befehlszeile ohne den Auftrag (der kommt ueber die Standardeingabe). budget: --max-budget-usd = die Reservierung,
    damit kein Aufruf mehr kostet als reserviert (sonst ueberzogen parallele Aufrufe das Tageslimit um die Differenz)."""
    args = [HELFER, "-p", "--model", modell, "--output-format", "json", "--no-session-persistence",
            "--setting-sources", "project", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--permission-mode", "dontAsk", "--max-turns", "8" if werkzeuge else "1", "--tools", ",".join(werkzeuge)]
    if budget:
        args += ["--max-budget-usd", "%.4f" % budget]
    if system:
        args += ["--system-prompt", system]
    if werkzeuge:
        args += ["--allowedTools"] + list(werkzeuge)            # variadisch, deshalb zuletzt
    return args


def _gruppe_beenden(p):
    for sig, warte in ((signal.SIGTERM, 3), (signal.SIGKILL, 5)):
        try:
            os.killpg(p.pid, sig)
        except OSError:
            return
        try:
            p.wait(timeout=warte)
            return
        except subprocess.TimeoutExpired:
            continue


def _aufruf(auftrag, system, modell, werkzeuge, timeout, budget=None):
    """-> (text, kosten_usd, weg). Wirft _Fehlschlag (mit kosten, falls Claude sie noch gemeldet hat)."""
    with tempfile.TemporaryDirectory(prefix="jarvis-denken-") as basis:
        arbeit, tmp = os.path.join(basis, "leer"), os.path.join(basis, "tmp")
        os.mkdir(arbeit, 0o700)
        os.mkdir(tmp, 0o700)
        p = subprocess.Popen(argumente(modell, werkzeuge, system, budget), cwd=arbeit, env=_umgebung(tmp),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
        try:
            aus, _ = p.communicate(auftrag, timeout=timeout)
        except subprocess.TimeoutExpired:
            _gruppe_beenden(p)
            raise _Fehlschlag(_t("Claude hat nicht rechtzeitig geantwortet (%d s)",
                                 "Claude did not answer in time (%d s)") % timeout)
        except BaseException:
            _gruppe_beenden(p)
            raise
    # N1: nur eigene Meldungen eines Hilfsskripts werten, nicht den Modelltext. Ein Hilfsskript schreibt seine Hinweise
    # als Zeile "[claude-api] …", die JSON-Antwort beginnt mit "{". Sonst braechte ein Satz aus einer beobachteten
    # Webseite ("kein Rueckfall auf das Abo") die Buchung durcheinander (0 $, Reservierung weg, stuendlich wiederholt).
    helfer_zeilen = [z for z in aus.splitlines() if z.startswith("[claude-api]")]
    if any("kein Rueckfall auf das Abo" in z for z in helfer_zeilen):   # K12: API nicht nutzbar, nichts ausgegeben
        raise _Fehlschlag(_t("API-Guthaben gerade nicht nutzbar (kein Rückfall aufs Abo)",
                             "API credit not usable right now (no fallback to the subscription)"), 0.0, "api")
    weg = "abo" if any("API nicht nutzbar" in z for z in helfer_zeilen) else "api"
    zeilen = [z for z in aus.splitlines() if z.startswith("{")]
    if not zeilen:
        raise _Fehlschlag(_t("keine Antwort von Claude (rc=%d)", "no answer from Claude (rc=%d)") % p.returncode,
                          None, weg)
    try:
        d = json.loads(zeilen[-1])
    except ValueError:
        raise _Fehlschlag(_t("unlesbare Antwort von Claude (rc=%d)", "unreadable answer from Claude (rc=%d)")
                          % p.returncode, None, weg)
    k = d.get("total_cost_usd")
    kosten = float(k) if isinstance(k, (int, float)) and not isinstance(k, bool) else None
    if d.get("is_error"):
        raise _Fehlschlag(_t("Claude meldet einen Fehler: %s", "Claude reports an error: %s")
                          % str(d.get("result") or d.get("subtype") or "?")[:200],
                          kosten, weg)
    if kosten is None:
        raise _Fehlschlag(_t("Claude hat keine Kosten gemeldet", "Claude reported no costs"), None, weg)
    return str(d.get("result") or ""), kosten, weg


# Kurze JSON-Stellungnahmen (Kabinett-Stimme: empfehlung + begruendung bis 800 Zeichen + Gegenrede + offene Fragen,
# grob 800 Ausgabe-Tokens, Sonnet ~ 0,05 $) reservieren weniger, damit vier gleichzeitige Stimmen nicht die vollen 2 $
# belegen (Nachpruefung, Punkt 2). Wird als reserve_usd uebergeben; wirkt zugleich als --max-budget-usd.
RESERVE_KURZ_USD = 0.15


def denken(auftrag, system="", stufe="normal", werkzeuge=(), zweck="", daten=None, timeout=300, reserve_usd=None):
    """Ein Denkauftrag -> Antworttext. stufe: schnell | normal | gruendlich. werkzeuge: Teilmenge von
    ERLAUBTE_WERKZEUGE (Standard keine). daten: Datenordner fuer Kosten und Tageslimit (None: ohne Buchfuehrung).
    reserve_usd: eigene Reservierung (realistische Hoechstkosten dieses Aufrufs) statt der Stufen-Reservierung; muss
    die erwartete Antwort wirklich decken, sonst ueberzieht der Aufruf das Tageslimit um die Differenz."""
    modell = MODELLE.get(stufe, MODELLE["normal"])
    werkzeuge = tuple(w for w in werkzeuge if w in ERLAUBTE_WERKZEUGE)
    if ERSATZ is not None:
        return str(ERSATZ(auftrag, system, modell, werkzeuge))
    rid = None
    grund = float(reserve_usd) if reserve_usd is not None else RESERVE_USD.get(stufe, RESERVE_USD["normal"])
    budget = grund + (WEB_ZUSCHLAG_USD if werkzeuge else 0.0)
    if daten:
        rid = _reservieren(daten, zweck, budget)
    try:
        text, kosten, weg = _aufruf(auftrag, system, modell, werkzeuge, timeout, budget)
    except _Fehlschlag as e:
        if daten:
            if e.kosten is not None:
                _verrechnen(daten, rid, zweck, modell, e.weg, e.kosten)
            else:
                _stehen_lassen(daten, rid, e)
        raise RuntimeError(str(e))
    except BaseException as e:
        if daten:
            _stehen_lassen(daten, rid, type(e).__name__)
        raise
    if daten:
        _verrechnen(daten, rid, zweck, modell, weg, kosten)
    return text


def denken_json(auftrag, system="", stufe="normal", werkzeuge=(), zweck="", daten=None, timeout=300, reserve_usd=None):
    """Wie denken, Antwort als JSON (zwei Versuche)."""
    letzte = None
    for versuch in (1, 2):
        text = denken(auftrag if versuch == 1 else auftrag + "\n\nAntworte NUR mit gueltigem JSON, ohne Text drumherum.",
                      system, stufe, werkzeuge, zweck, daten, timeout, reserve_usd)
        try:
            return json_aus(text)
        except ValueError as e:
            letzte = e
    raise RuntimeError(_t("Claude lieferte zweimal kein lesbares JSON (%s): %s",
                          "Claude returned no readable JSON twice (%s): %s") % (zweck, letzte))
