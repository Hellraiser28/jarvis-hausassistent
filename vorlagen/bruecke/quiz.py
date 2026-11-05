"""Familien-Quizshow auf dem Beamer (seit 01.11.2026, im Release seit 0.6). Reine Logik, Python 3.8, ohne Netz und
ohne Ton.

Fuer das Quiz soll eine vernuenftige, klare Moderatorenstimme klingen, und das geht vorab. Deshalb liegt alles vorher
bereit (angelegt von einem Vorbereitungsskript, z. B. werkzeuge/quiz_vorbereiten.py):

  <daten>/quiz/fragen.json          Katalog: je Frage id, stufe (kind/erwachsen), kategorie, frage, antworten (4),
                                    richtig (A-D), wusstest, schwierigkeit (1-5), bei Fangfragen fang und typ.
                                    Erzeugt von Claude, zweiter unabhaengiger Durchgang prueft.
  <daten>/quiz/ton/<id>-frage.mp3   Frage samt A bis D, Moderatorenstimme (vorab erzeugt, z. B. mit einem lokalen
  <daten>/quiz/ton/<id>-loesung.mp3 Sprachprogramm auf einem PC; entworfene Stimme, keine Klonstimme einer echten
                                    Person); feste Saetze als fest-<schluessel>.mp3 (FEST)
  <daten>/quiz/namen.json           Namen fuer die festen Ansagen „X, jetzt bist du dran“ und „Gewonnen hat X“
                                    (seit 0.6 konfigurierbar, siehe setze_namen; ohne Datei keine)
  <daten>/quiz/spiel.json           Spielstand, damit es ueber mehrere Gespraeche geht (dieses Modul)
  <daten>/quiz/gespielt.json        schon gestellte Fragen, die naechste Runde nimmt zuerst neue

Fairness: Jeder Spieler bekommt Fragen seiner Stufe (Standard erwachsen fuer alle; kind nur auf Wunsch). Modus reihum
(Standard): die Fragen gehen abwechselnd an die Spieler, nur der Spieler am Zug antwortet. Modus alle: alle antworten auf
jede Frage, nur wenn alle dieselbe Stufe haben. Ein Punkt je richtiger Antwort, gleich fuer alle.
Die richtige Antwort steht erst nach dem Aufloesen im Spielstand-Auszug fuer Anzeige und Gehirn (nie vorher verraten).
Sprache (seit 0.6 im Release): feste Ansagen, Meldungen und Anzeige auf Deutsch oder Englisch (setze_sprache(), wie
szenen.py). Der Fragenkatalog bleibt Daten in der Sprache, in der er angelegt wurde; die Moderatorenstimme vorab in
derselben Sprache erzeugen.
"""
import fcntl
import json
import os
import random
import re
import time
from contextlib import contextmanager
from datetime import datetime

ORDNER = "quiz"
KATALOG, SPIEL, GESPIELT, TON, NAMEN = "fragen.json", "spiel.json", "gespielt.json", "ton", "namen.json"
STUFEN = ("kind", "erwachsen")
KATEGORIEN = ("Tiere", "Natur", "Erdkunde", "Geschichte", "Sport", "Film & Musik", "Essen", "Wissenschaft",
              "Allgemeinwissen")
KATEGORIE_EN = {"Tiere": "Animals", "Natur": "Nature", "Erdkunde": "Geography", "Geschichte": "History", "Sport": "Sports",
                "Film & Musik": "Film & Music", "Essen": "Food", "Wissenschaft": "Science",
                "Allgemeinwissen": "General knowledge"}           # nur fuer die Anzeige; im Katalog stehen die deutschen
KURZ = {"Tiere": "tiere", "Natur": "natur", "Erdkunde": "erdkunde", "Geschichte": "geschichte", "Sport": "sport",
        "Film & Musik": "film-musik", "Essen": "essen", "Wissenschaft": "wissenschaft", "Allgemeinwissen": "allgemein"}
KATEGORIE_ALIAS = {"tier": "Tiere", "natur": "Natur", "pflanze": "Natur", "erdkunde": "Erdkunde", "geografie": "Erdkunde",
                   "geographie": "Erdkunde", "laender": "Erdkunde", "geschichte": "Geschichte", "sport": "Sport",
                   "film": "Film & Musik", "musik": "Film & Musik", "kino": "Film & Musik", "essen": "Essen",
                   "kochen": "Essen", "trinken": "Essen", "wissenschaft": "Wissenschaft", "technik": "Wissenschaft",
                   "weltall": "Wissenschaft", "allgemein": "Allgemeinwissen"}
GEMISCHT = ("", "gemischt", "alle", "alles", "egal", "bunt", "querbeet", "zufall", "durcheinander")
BUCHSTABEN = "ABCD"
MODI = ("reihum", "alle")
STANDARD_STUFE = {}                               # seit 03.11.2026: alle erwachsen, auch Jugendliche; Kinderfragen
#                                                 nur auf ausdruecklichen Wunsch, z. B. "Mia (kind)" oder stufe kind
MAX_SPIELER, MAX_ANZAHL, STANDARD_ANZAHL = 6, 15, 5
MAX_NAMEN = 12
SEKUNDEN = {"kind": 45, "erwachsen": 30}          # Zeitbalken auf der Leinwand (nur Anzeige, niemand wird abgebrochen)
# Fangfragen (seit 04.11.2026): Fragen, die so einfach sind, dass sie es eben wieder nicht sind, wie am Anfang
# von „Wer wird Millionär“. Katalogfeld fang: true und typ. Je Runde fuer alle gleich: Runde 1 immer, Runde 2 mit 50 %,
# danach mit 20 % eine Fangfrage, solange es ungespielte gibt. Vor dem Aufloesen erfaehrt niemand, dass es eine ist.
FANG_TYPEN = ("falle", "wortspiel", "irrtum")
FANG_ANTEIL = (1.0, 0.5, 0.2)
PAUSE = "fest-pause"                            # 0,6 s Stille zwischen den Teilen einer Ansage
TAKT_FELDER = ("auf_ab", "antw_ab", "aufdecken_ab", "mund", "mund_hz", "mund_ab")   # Unix-Zeiten bzw. Huellkurve
SPANNUNG_S = 2.5                                  # so lange leuchtet die eingeloggte Antwort orange, bevor aufgedeckt wird
MUND_HZ = 20                                      # Werte je Sekunde der Huellkurve (0-9a-f)

# Sprache der festen Ansagen, Meldungen und der Anzeige.
SPRACHE = "de"


def _t(de, en):
    return en if SPRACHE == "en" else de


# Feste Saetze der Moderatorenstimme (Schluessel -> Text); das Vorbereitungsskript legt fest-<schluessel>.mp3 an.
FEST_DE = {
    "begruessung": "Herzlich willkommen zur Familien-Quizshow! Ich stelle die Fragen, ihr sucht die richtige Antwort. "
                   "Viel Spaß und viel Glück!",
    "zeit": "Die Zeit läuft!",
    "alle": "Diese Frage ist für alle!",
    "letzte": "Und jetzt kommt die letzte Frage!",
    "richtig1": "Richtig! Super gemacht.",
    "richtig2": "Ganz genau, das stimmt!",
    "richtig3": "Jawohl, richtig!",
    "falsch1": "Leider nicht ganz.",
    "falsch2": "Oh, knapp daneben.",
    "ende": "Das war die letzte Frage. Und jetzt der Punktestand!",
    "gleichstand": "Gleichstand an der Spitze! Herzlichen Glückwunsch an die Gewinner!",
    "unentschieden": "Unentschieden! Ihr seid alle gleich gut. Herzlichen Glückwunsch an alle!",
    "danke": "Danke fürs Mitspielen! Bis zum nächsten Mal.",
}
FEST_EN = {
    "begruessung": "Welcome to the family quiz show! I ask the questions, you find the right answer. "
                   "Have fun and good luck!",
    "zeit": "The clock is ticking!",
    "alle": "This question is for everyone!",
    "letzte": "And now here comes the last question!",
    "richtig1": "Correct! Well done.",
    "richtig2": "Exactly, that's right!",
    "richtig3": "Yes indeed, correct!",
    "falsch1": "Not quite, unfortunately.",
    "falsch2": "Oh, just missed.",
    "ende": "That was the last question. And now the scores!",
    "gleichstand": "A tie at the top! Congratulations to the winners!",
    "unentschieden": "It's a draw! You are all equally good. Congratulations to everyone!",
    "danke": "Thanks for playing! See you next time.",
}
# Ansagen mit Namen: (Erwachsene, Kinder). Kinder bekommen die kindgerechte Fassung.
DRAN = {"de": ("%s, diese Frage ist für dich.", "%s, jetzt bist du dran!"),
        "en": ("%s, this question is for you.", "%s, it's your turn now!")}
SIEGER = {"de": ("Gewonnen hat %s! Herzlichen Glückwunsch!", "Gewonnen hat %s! Herzlichen Glückwunsch, das hast du toll gemacht!"),
          "en": ("%s wins! Congratulations!", "%s wins! Congratulations, you did great!")}
# Namen mit festen Ansagen (dran_<name>, sieger_<name>), seit 0.6 konfigurierbar statt fest im Code: setze_namen() oder
# <daten>/quiz/namen.json {"namen": ["Anna", "Ben", "Mia"], "kinder": ["Mia"]} ueber namen_laden(). Standard: keine.
# Fuer andere Namen faellt „X, diese Frage ist für dich“ ohne vorab erzeugte Datei still weg, und den Sieger spricht
# Jarvis' eigene Stimme (Pflichtteil, siehe ansage_planen).
FAMILIE = ()
KINDER = ()
FEST = {}


def _name_schluessel(name):
    return norm(name).replace(" ", "_")


def _fest_bauen():
    """FEST neu fuellen (gleiches Objekt): feste Saetze der Sprache plus dran_/sieger_ je Name."""
    FEST.clear()
    FEST.update(FEST_EN if SPRACHE == "en" else FEST_DE)
    for n in FAMILIE:
        kind = 1 if n in KINDER else 0
        FEST["dran_" + _name_schluessel(n)] = DRAN[SPRACHE][kind] % n
        FEST["sieger_" + _name_schluessel(n)] = SIEGER[SPRACHE][kind] % n


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache
    _fest_bauen()


def setze_namen(namen, kinder=()):
    """Namen fuer die festen Ansagen (hoechstens MAX_NAMEN, ohne Doppelte); kinder: wer davon die kindgerechte Fassung
    bekommt. Gibt die uebernommenen Namen zurueck."""
    global FAMILIE, KINDER
    namen = [namen] if isinstance(namen, str) else list(namen or [])
    kinder = [kinder] if isinstance(kinder, str) else list(kinder or [])
    liste = []
    for n in namen:
        n = _sauber(n, 20).strip(" .!?")
        if n and norm(n) and norm(n) not in [norm(x) for x in liste]:
            liste.append(n)
    FAMILIE = tuple(liste[:MAX_NAMEN])
    k = set(norm(x) for x in kinder)
    KINDER = tuple(n for n in FAMILIE if norm(n) in k)
    _fest_bauen()
    return FAMILIE


def namen_laden(daten):
    """<daten>/quiz/namen.json lesen und setzen; fehlt die Datei oder taugt sie nicht, gilt der Standard (keine Namen)."""
    try:
        d = json.load(open(os.path.join(ordner(daten), NAMEN), encoding="utf-8"))
        namen, kinder = d.get("namen") or [], d.get("kinder") or []
        if not isinstance(namen, list) or not isinstance(kinder, list):
            raise ValueError("keine Listen")
    except (OSError, ValueError, AttributeError):
        namen, kinder = [], []
    return setze_namen([n for n in namen if isinstance(n, str)], [n for n in kinder if isinstance(n, str)])


def ordner(daten):
    return os.path.join(daten, ORDNER)


def norm(s):
    s = str(s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("&", " und ")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _sauber(t, n):
    t = re.sub(r"[\x00-\x1f<>]", " ", str(t or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n]


_fest_bauen()


def kategorie_anzeige(kategorie):
    """Kategorie fuer Anzeige und Meldungen in der eingestellten Sprache."""
    return KATEGORIE_EN.get(kategorie, kategorie) if SPRACHE == "en" else kategorie


# ---------------------------------------------------------------- Katalog
def frage_pruefen(f):
    """Eine Frage in feste Form bringen; ValueError mit Grund, wenn sie nicht taugt."""
    if not isinstance(f, dict):
        raise ValueError("keine Frage")
    fid = str(f.get("id") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,40}", fid):
        raise ValueError("id %r ungueltig" % fid)
    if f.get("stufe") not in STUFEN:
        raise ValueError("stufe %r ungueltig" % f.get("stufe"))
    if f.get("kategorie") not in KATEGORIEN:
        raise ValueError("kategorie %r ungueltig" % f.get("kategorie"))
    frage = _sauber(f.get("frage"), 300)
    if len(frage) < 8:
        raise ValueError("frage zu kurz")
    a = f.get("antworten")
    if not isinstance(a, list) or len(a) != 4:
        raise ValueError("es braucht genau 4 Antworten")
    a = [_sauber(x, 120) for x in a]
    if not all(a) or len(set(norm(x) for x in a)) != 4:
        raise ValueError("Antworten leer oder doppelt")
    r = str(f.get("richtig") or "").strip().upper()
    if r not in BUCHSTABEN or len(r) != 1:
        raise ValueError("richtig %r ungueltig" % f.get("richtig"))
    try:                                          # seit 01.11.2026 abends: 1 leicht bis 5 schwer, je Stufe (fehlt: 3)
        sw = int(f.get("schwierigkeit", 3))
    except (TypeError, ValueError):
        raise ValueError("schwierigkeit %r ungueltig" % (f.get("schwierigkeit"),))
    if not 1 <= sw <= 5 or isinstance(f.get("schwierigkeit"), bool):
        raise ValueError("schwierigkeit %r ungueltig" % (f.get("schwierigkeit"),))
    aus = {"id": fid, "stufe": f["stufe"], "kategorie": f["kategorie"], "frage": frage, "antworten": a, "richtig": r,
           "wusstest": _sauber(f.get("wusstest"), 300), "schwierigkeit": sw}
    if f.get("fang") is True:                     # seit 04.11.2026; ohne fang bleibt die Frage wie bisher
        typ = f.get("typ") or "falle"
        if typ not in FANG_TYPEN:
            raise ValueError("typ %r ungueltig" % (typ,))
        aus["fang"], aus["typ"] = True, typ
    return aus


def katalog_laden(daten):
    """Gueltige Fragen aus <daten>/quiz/fragen.json (ungueltige und doppelte ids fallen still weg)."""
    try:
        roh = json.load(open(os.path.join(ordner(daten), KATALOG), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    aus, ids = [], set()
    for f in (roh.get("fragen") if isinstance(roh, dict) else roh) or []:
        try:
            g = frage_pruefen(f)
        except ValueError:
            continue
        if g["id"] not in ids:
            ids.add(g["id"])
            aus.append(g)
    return aus


def _json_schreiben(pfad, inhalt):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    neu = pfad + ".neu"
    with open(neu, "w", encoding="utf-8") as f:
        json.dump(inhalt, f, ensure_ascii=False, indent=1)
    os.replace(neu, pfad)


def katalog_speichern(daten, fragen):
    _json_schreiben(os.path.join(ordner(daten), KATALOG), {"version": 1, "fragen": fragen})


def woerter(s):
    return set(w for w in norm(s).split() if len(w) > 2)


def aehnlich(a, b, grenze=0.75):
    """Fast gleiche Frage (Doppelte vermeiden): gleicher Text oder grosse Wortueberdeckung."""
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    wa, wb = woerter(a), woerter(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / float(len(wa | wb)) >= grenze


def zaehlen(katalog):
    """{(stufe, kategorie): anzahl}"""
    z = {}
    for f in katalog:
        z[(f["stufe"], f["kategorie"])] = z.get((f["stufe"], f["kategorie"]), 0) + 1
    return z


def kategorie_finden(text):
    """Kategorie aus freiem Text; None heisst gemischt; False heisst unbekannt."""
    n = norm(text)
    if n in GEMISCHT:
        return None
    for k in KATEGORIEN:
        if norm(k) == n:
            return k
    for wort, k in KATEGORIE_ALIAS.items():
        if wort in n:
            return k
    return False


def stufe_finden(text):
    n = norm(text)
    if n.startswith("kind") or n in ("leicht", "einfach", "klein"):
        return "kind"
    if n.startswith("erwachsen") or n in ("schwer", "gross", "normal"):
        return "erwachsen"
    return None


# ---------------------------------------------------------------- Spieler und Ziehen
def spieler_lesen(spieler, stufen=None):
    """Spielerliste aus ["Mia", "Ben"], [{"name", "stufe"}] oder "Mia (kind), Ben". stufen: {name: stufe}.
    Gibt (liste, fehler) zurueck; Standardstufe: erwachsen fuer alle, kind nur ausdruecklich."""
    if isinstance(spieler, str):
        spieler = [x for x in re.split(r"\s*(?:,|;|\bund\b|&)\s*", spieler) if x.strip()]
    stufen = {norm(k): v for k, v in (stufen or {}).items()} if isinstance(stufen, dict) else {}
    aus, gesehen = [], set()
    for s in spieler or []:
        st = None
        if isinstance(s, dict):
            name, st = s.get("name"), s.get("stufe")
        else:
            m = re.match(r"^\s*(.*?)\s*[\(:]\s*(kind|kinder|erwachsen\w*|leicht|schwer)\s*\)?\s*$", str(s), re.I)
            name, st = (m.group(1), m.group(2)) if m else (s, None)
        name = _sauber(name, 20).strip(" .!?")
        if not name:
            continue
        name = name[0].upper() + name[1:]
        if norm(name) in gesehen:
            continue
        gesehen.add(norm(name))
        st = stufe_finden(st) if st else None
        st = st or stufe_finden(stufen.get(norm(name))) or STANDARD_STUFE.get(norm(name), "erwachsen")
        aus.append({"name": name, "stufe": st, "punkte": 0})
    if not aus:
        return [], _t("Wer spielt mit? Zum Beispiel: Anna, Ben und Mia.", "Who is playing? For example: Anna, Ben and Mia.")
    if len(aus) > MAX_SPIELER:
        return [], _t("Höchstens %d Spieler.", "At most %d players.") % MAX_SPIELER
    return aus, None


def ziel_schwierigkeit(runde, runden):
    """Wie bei „Wer wird Millionär“: die Runden steigen von leicht (1) nach schwer (5) an. runde ab 0."""
    if runden <= 1:
        return 3
    return 1 + int(round(4.0 * runde / (runden - 1)))


def ziehen(katalog, spieler, kategorie, anzahl, modus, gespielt=(), zufall=None):
    """Fragen fuer ein ganzes Spiel vorab ziehen: [{"fuer": name|None, "frage": {...}}] und ein Hinweis (oder "").
    Zuerst ungespielte Fragen der Kategorie, dann aus anderen Kategorien, zuletzt schon gespielte; innerhalb davon die
    Frage, deren Schwierigkeit der Runde am naechsten liegt (je Spieler in seiner Stufe aufsteigend).
    Fangfragen (seit 04.11.2026): Ob eine Runde mit einer Fangfrage beginnt, entscheidet FANG_ANTEIL einmal je Runde fuer
    alle Spieler gleich. Genommen werden nur ungespielte Fangfragen der gewaehlten Kategorie; fehlen sie, kommt eine
    normale Frage. Normale Ziehungen lassen Fangfragen aus, damit ihr Anteil gesteuert bleibt. Ohne Fangfragen im
    Katalog verhaelt sich alles wie vorher, auch der Zufall."""
    zufall = zufall or random.Random()
    gespielt = set(gespielt or ())
    genommen, hinweise = set(), []
    mit_fang = any(f.get("fang") for f in katalog)

    def naechste(pool, ziel):
        abstand = min(abs(f.get("schwierigkeit", 3) - ziel) for f in pool)
        return zufall.choice([f for f in pool if abs(f.get("schwierigkeit", 3) - ziel) == abstand])

    def fang_runde(runde):
        if not mit_fang:
            return False
        p = FANG_ANTEIL[min(runde, len(FANG_ANTEIL) - 1)]
        return p >= 1 or zufall.random() < p

    def eine(stufe, ziel, fang=False):
        stufen = [f for f in katalog if f["stufe"] == stufe and f["id"] not in genommen]
        if fang:
            pool = [f for f in stufen if f.get("fang") and f["id"] not in gespielt
                    and (not kategorie or f["kategorie"] == kategorie)]
            if pool:
                f = naechste(pool, ziel)
                genommen.add(f["id"])
                return f
        basis = [f for f in stufen if not f.get("fang")] or stufen
        for pool, merke in (([f for f in basis if (not kategorie or f["kategorie"] == kategorie) and f["id"] not in gespielt], None),
                            ([f for f in basis if f["id"] not in gespielt], "andere Kategorien"),
                            ([f for f in basis if not kategorie or f["kategorie"] == kategorie], "schon gespielte"),
                            (basis, "schon gespielte")):
            if pool:
                if merke and merke not in hinweise and (kategorie or merke == "schon gespielte"):
                    hinweise.append(merke)
                f = naechste(pool, ziel)
                genommen.add(f["id"])
                return f
        return None

    slots = []
    for runde in range(anzahl):
        ziel = ziel_schwierigkeit(runde, anzahl)
        fang = fang_runde(runde)
        if modus == "alle":
            f = eine(spieler[0]["stufe"], ziel, fang)
            if not f:
                break
            slots.append({"fuer": None, "frage": f})
        else:
            for s in spieler:
                f = eine(s["stufe"], ziel, fang)
                if not f:
                    break
                slots.append({"fuer": s["name"], "frage": f})
            else:
                continue
            break
    if modus != "alle":          # nur volle Runden, damit jeder gleich viele Fragen hat
        voll = len(slots) - len(slots) % len(spieler)
        slots = slots[:voll]
    h = ""
    if "andere Kategorien" in hinweise:
        h = _t("In der Kategorie %s gab es nicht genug neue Fragen, ich habe mit anderen ergänzt.",
               "There were not enough new questions in the category %s, I filled up with others.") % kategorie_anzeige(kategorie)
    elif "schon gespielte" in hinweise:
        h = _t("Es sind auch schon gespielte Fragen dabei, der Vorrat an neuen ist aufgebraucht.",
               "Some questions have been played before, the supply of new ones is used up.")
    return slots, h


def neu(katalog, spieler, kategorie=None, anzahl=None, modus=None, gespielt=(), zufall=None, ton="auto", jetzt=None):
    """Neues Spiel; (zustand, None) oder ({}, fehler). spieler aus spieler_lesen(). ton: Tonweg, den das Werkzeug
    mitgibt (z. B. auto, leinwand, wohnzimmer, aus); dieses Modul merkt ihn nur."""
    if not katalog:
        return {}, _t("Es gibt noch keine Quizfragen. Die Hauptperson kann sie anlegen (Katalog daten/quiz/fragen.json).",
                      "There are no quiz questions yet. The main person can create them (catalogue daten/quiz/fragen.json).")
    try:
        anzahl = int(anzahl or STANDARD_ANZAHL)
    except (TypeError, ValueError):
        anzahl = STANDARD_ANZAHL
    anzahl = max(1, min(MAX_ANZAHL, anzahl))
    stufen = set(s["stufe"] for s in spieler)
    modus = modus if modus in MODI else "reihum"
    hinweis = ""
    if modus == "alle" and len(stufen) > 1:
        modus, hinweis = "reihum", _t("Bei Kinder- und Erwachsenenfragen gemischt geht es reihum, damit jeder Fragen seiner "
                                      "Stufe bekommt.",
                                      "With children's and adults' questions mixed it goes in turns, so that everyone "
                                      "gets questions of their level.")
    slots, h = ziehen(katalog, spieler, kategorie, anzahl, modus, gespielt, zufall)
    if not slots:
        return {}, _t("Für diese Spieler gibt es gerade keine passenden Fragen.",
                      "There are no suitable questions for these players right now.")
    if len(slots) < (anzahl if modus == "alle" else anzahl * len(spieler)):
        h = (h + " " if h else "") + _t("Es reichen nur %d Fragen.", "There are only enough questions for %d.") % len(slots)
    jetzt = jetzt or time.time()
    for s in slots:
        s.update({"antworten": {}, "aufgeloest": False, "sekunden": SEKUNDEN[s["frage"]["stufe"]]})
    runden = len(slots) if modus == "alle" else len(slots) // len(spieler)
    z = {"version": 1, "id": "%x" % int(jetzt * 1000), "start": datetime.fromtimestamp(jetzt).isoformat(timespec="seconds"),
         "kategorie": kategorie or None, "modus": modus, "ton": ton, "spieler": spieler, "fragen": slots, "nr": 0,
         "phase": "frage", "seit": int(jetzt), "hinweis": " ".join(x for x in (hinweis, h) if x),
         "runden": runden, "leiter": [ziel_schwierigkeit(r, runden) for r in range(runden)]}
    return z, None


def runde(z):
    """Aktuelle Runde ab 1 (reihum: jeder Spieler eine Frage je Runde)."""
    je = 1 if z.get("modus") == "alle" else max(1, len(z.get("spieler") or []))
    return z.get("nr", 0) // je + 1


# ---------------------------------------------------------------- Spielzuege
def aktuell(z):
    return z["fragen"][z["nr"]] if z and 0 <= z.get("nr", -1) < len(z.get("fragen") or []) else None


def erwartet(z):
    s = aktuell(z)
    if not s:
        return []
    return [s["fuer"]] if s.get("fuer") else [x["name"] for x in z["spieler"]]


def spieler_finden(z, wer):
    n = norm(wer)
    for s in z["spieler"]:
        if norm(s["name"]) == n:
            return s["name"]
    for s in z["spieler"]:                          # „die Mia“, „Papa Ben“
        if n and norm(s["name"]) in n.split():
            return s["name"]
    return None


GESPROCHEN = {"A": ("a", "ah", "aa"), "B": ("b", "be", "bee", "beh"), "C": ("c", "ce", "ze", "tse", "zeh", "cee", "tseh"),
              "D": ("d", "de", "dee", "deh")}


def buchstabe_finden(eingabe, antworten=None):
    """„B“, „b)“, „Antwort B“, „Be“ oder der Antworttext selbst -> Buchstabe; None, wenn es nicht eindeutig ist."""
    voll = norm(eingabe)
    n = voll
    for w in ("antwort", "ich", "sage", "sagt", "nehme", "nimmt", "glaube", "tippe", "ist", "die", "der", "das", "es"):
        n = re.sub(r"\b%s\b" % w, " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    erstes = n.split()[0] if n else ""
    for b, formen in GESPROCHEN.items():
        if n in formen or voll in formen or (erstes in formen and len(n.split()) <= 3):
            return b
    if antworten:
        na = [norm(a) for a in antworten]
        for k in (voll, n):
            treffer = [i for i, a in enumerate(na) if a == k]
            if len(treffer) == 1:
                return BUCHSTABEN[treffer[0]]
        for k in (voll, n):
            if len(k) >= 3:
                treffer = [i for i, a in enumerate(na) if k in a or a in k]
                if len(treffer) == 1:
                    return BUCHSTABEN[treffer[0]]
    return None


def antworten(z, wer, eingabe):
    """Antwort eintragen. -> (zustand, meldung, alle_da). Ueberschreiben geht, bis die Frage aufgeloest ist."""
    s = aktuell(z)
    if not s or z.get("phase") == "ende":
        return z, _t("Es läuft gerade kein Quiz.", "No quiz is running right now."), False
    if s.get("aufgeloest"):
        return z, _t("Diese Frage ist schon aufgelöst. Weiter geht es mit der nächsten Frage.",
                     "This question is already resolved. On to the next question."), False
    soll = erwartet(z)
    name = spieler_finden(z, wer) if wer else (soll[0] if len(soll) == 1 else None)
    if not name:
        return z, (_t("Wer hat geantwortet? Es spielen %s.", "Who answered? Playing: %s.")
                   % ", ".join(x["name"] for x in z["spieler"])), False
    if name not in soll:
        return z, _t("Diese Frage ist für %s. %s ist gleich dran.", "This question is for %s. %s is up next.") % (
            soll[0], name), False
    b = buchstabe_finden(eingabe, s["frage"]["antworten"])
    if not b:
        return z, _t("Welche Antwort meint %s? Bitte A, B, C oder D.", "Which answer does %s mean? Please A, B, C or D.") % name, False
    neu_z = json.loads(json.dumps(z))
    neu_z["fragen"][z["nr"]]["antworten"][name] = b
    da = all(n in neu_z["fragen"][z["nr"]]["antworten"] for n in soll)
    return neu_z, _t("%s nimmt %s.", "%s takes %s.") % (name, b), da


def aufloesen(z):
    """-> (zustand, ergebnis). Punkte: +1 je richtiger Antwort; zweimal aufloesen zaehlt nicht doppelt."""
    s = aktuell(z)
    if not s:
        return z, None
    f = s["frage"]
    neu_z = json.loads(json.dumps(z))
    ns = neu_z["fragen"][z["nr"]]
    treffer = [n for n, b in s["antworten"].items() if b == f["richtig"]]
    if not s.get("aufgeloest"):
        for sp in neu_z["spieler"]:
            if sp["name"] in treffer:
                sp["punkte"] += 1
        ns["aufgeloest"] = True
        neu_z["phase"] = "aufgeloest"
    erg = {"richtig": f["richtig"], "text": f["antworten"][BUCHSTABEN.index(f["richtig"])], "wusstest": f["wusstest"],
           "treffer": treffer, "daneben": [n for n, b in s["antworten"].items() if b != f["richtig"]],
           "ohne": [n for n in erwartet(z) if n not in s["antworten"]]}
    return neu_z, erg


def weiter(z, jetzt=None):
    """Naechste Frage. -> (zustand, meldung oder None). Erst nach dem Aufloesen; nach der letzten: Ende."""
    s = aktuell(z)
    if not s or z.get("phase") == "ende":
        return z, _t("Es läuft gerade kein Quiz.", "No quiz is running right now.")
    if not s.get("aufgeloest"):
        return z, _t("Die Frage ist noch offen. Erst antworten oder auflösen.",
                     "The question is still open. Answer or resolve it first.")
    neu_z = dict(z)
    if z["nr"] + 1 >= len(z["fragen"]):
        neu_z["phase"] = "ende"
        return neu_z, None
    neu_z.update(nr=z["nr"] + 1, phase="frage", seit=int(jetzt or time.time()))
    return neu_z, None


def beenden(z):
    return dict(z, phase="ende") if z else z


def rangliste(z):
    return sorted(((s["name"], s["punkte"]) for s in z.get("spieler") or []), key=lambda x: -x[1])


def sieger(z):
    r = rangliste(z)
    if not r:
        return []
    beste = r[0][1]
    return [n for n, p in r if p == beste]


def stand_text(z):
    return ", ".join("%s %d" % (n, p) for n, p in rangliste(z)) + "."


def ist_letzte(z):
    return z.get("nr", 0) + 1 >= len(z.get("fragen") or [])


# ---------------------------------------------------------------- Texte und Ansagen
def frage_sprechtext(f):
    return "%s A: %s. B: %s. C: %s. D: %s." % (f["frage"], *[a.rstrip(".") for a in f["antworten"]])


def loesung_sprechtext(f):
    b = f["richtig"]
    t = _t("Richtig ist %s: %s.", "The correct answer is %s: %s.") % (b, f["antworten"][BUCHSTABEN.index(b)].rstrip("."))
    return (t + " " + f["wusstest"]) if f.get("wusstest") else t


def ton_name(fid, teil):
    return "%s-%s" % (fid, teil)


def ansage(z, was, erg=None, zufall=None):
    """Teile einer Ansage als [(schluessel, text, pflicht)]; schluessel ist der Dateistamm unter quiz/ton/.
    was: start, frage, loesung, ende. Pflichtteile (Frage, Loesung, Sieger) muessen vorab vorhanden sein, sonst spricht
    Jarvis' eigene Stimme das Ganze; fehlt nur ein Zusatz (z. B. „Oma, du bist dran“), faellt er still weg."""
    zufall = zufall or random.Random()
    teile = []
    s = aktuell(z)
    if was in ("start", "frage") and s:
        if was == "start":
            teile.append(("fest-begruessung", FEST["begruessung"], False))
        if ist_letzte(z) and len(z["fragen"]) > 1:
            teile.append(("fest-letzte", FEST["letzte"], False))
        if s.get("fuer"):
            k = "dran_" + _name_schluessel(s["fuer"])
            teile.append(("fest-" + k, FEST.get(k) or DRAN[SPRACHE][0] % s["fuer"], False))
        elif len(z["spieler"]) > 1:
            teile.append(("fest-alle", FEST["alle"], False))
        teile.append((ton_name(s["frage"]["id"], "frage"), frage_sprechtext(s["frage"]), True))
        teile.append(("fest-zeit", FEST["zeit"], False))
    elif was == "loesung" and s and erg:
        if erg["treffer"] and not erg["daneben"] and not erg["ohne"]:
            k = zufall.choice(("richtig1", "richtig2", "richtig3"))
            teile.append(("fest-" + k, FEST[k], False))
        elif not erg["treffer"] and (erg["daneben"] or erg["ohne"]):
            k = zufall.choice(("falsch1", "falsch2"))
            teile.append(("fest-" + k, FEST[k], False))
        teile.append((ton_name(s["frage"]["id"], "loesung"), loesung_sprechtext(s["frage"]), True))
    elif was == "ende":
        teile.append(("fest-ende", FEST["ende"], False))
        sg = sieger(z)
        if len(sg) == len(z["spieler"]) and len(sg) > 1:
            teile.append(("fest-unentschieden", FEST["unentschieden"], True))
        elif len(sg) > 1:
            teile.append(("fest-gleichstand", FEST["gleichstand"], True))
        elif sg:
            k = "sieger_" + _name_schluessel(sg[0])
            teile.append(("fest-" + k, FEST.get(k) or SIEGER[SPRACHE][0] % sg[0], True))
        teile.append(("fest-danke", FEST["danke"], False))
    return teile


def ansage_planen(teile, vorhanden):
    """-> (dateistaemme oder None, text). vorhanden: Funktion stamm -> bool. Fehlt ein Pflichtteil, None: dann spricht
    Jarvis den ganzen Text mit der eigenen Stimme (Stimmen nicht mischen)."""
    text = " ".join(t for _, t, _ in teile)
    staemme = []
    for k, _, pflicht in teile:
        if vorhanden(k):
            if staemme:
                staemme.append(PAUSE)
            staemme.append(k)
        elif pflicht:
            return None, text
    if staemme and not vorhanden(PAUSE):
        staemme = [x for x in staemme if x != PAUSE]
    return (staemme or None), text


# ---------------------------------------------------------------- Ton auswerten (Mund der Moderatorin, Antworten im Takt)
def _pegel(pcm, rate, fenster_s, schritt=4):
    """Mittlerer Betrag je Fenster (16 bit mono), jeder schritt-te Wert reicht dafuer."""
    pcm = pcm[:len(pcm) // 2 * 2]
    if not pcm:
        return []
    w = memoryview(pcm).cast("h")
    n = max(1, int(rate * fenster_s))
    aus = []
    for a in range(0, len(w), n):
        teil = w[a:a + n:schritt]
        aus.append(sum(abs(x) for x in teil) / float(max(1, len(teil))))
    return aus


def huelle(pcm, rate, hz=MUND_HZ):
    """Lautstaerke-Huellkurve, hz Werte je Sekunde als Zeichen 0-9a-f (0 still, f laut), auf das 95-%-Perzentil bezogen.
    Die Leinwand liest damit den Mund der Moderatorin ab (Web-Audio-Analyse ginge nicht: die Datei kommt von einer
    anderen Herkunft, der Analyser saehe nur Nullen)."""
    p = _pegel(pcm, rate, 1.0 / hz)
    if not p:
        return ""
    ref = sorted(p)[int(len(p) * 0.95)] or 1.0
    return "".join("0123456789abcdef"[min(15, int(15 * min(1.0, v / ref) ** 0.7 + 0.5))] for v in p)


def pausen_teile(pcm, rate, n=4, min_s=0.35):
    """Beginn der Teile nach den n laengsten Pausen (Sekunden ab Anfang), in zeitlicher Folge; None, wenn es nicht so
    viele deutliche Pausen gibt. Eine Frageansage ist Frage, A, B, C, D mit 0,5 bis 0,8 s Pause dazwischen
    (so legt das Vorbereitungsskript sie an), Pausen zwischen Woertern sind kuerzer."""
    p = _pegel(pcm, rate, 0.01)
    if len(p) < 10:
        return None
    schwelle = max(150.0, 0.04 * sorted(p)[int(len(p) * 0.95)])
    laeufe, start = [], None
    for i, v in enumerate(p + [schwelle * 10]):
        if v < schwelle and start is None:
            start = i
        elif v >= schwelle and start is not None:
            if start > 0 and i < len(p) and (i - start) * 0.01 >= min_s:
                laeufe.append((i - start, start, i))
            start = None
    if len(laeufe) < n:
        return None
    return [round(ende * 0.01, 2) for _, _, ende in sorted(sorted(laeufe, reverse=True)[:n], key=lambda x: x[1])]


# ---------------------------------------------------------------- Anzeige (Leinwand, art quiz)
def anzeige(z, jetzt=None):
    """Inhalt fuer die Leinwand. Die richtige Antwort steht erst nach dem Aufloesen drin."""
    jetzt = jetzt or time.time()
    s = aktuell(z) or {}
    f = s.get("frage") or {}
    auf = bool(s.get("aufgeloest"))
    ende = z.get("phase") == "ende"
    sp = []
    for x in z.get("spieler") or []:
        w = (s.get("antworten") or {}).get(x["name"])
        e = {"name": x["name"], "punkte": x["punkte"], "dran": (not ende) and (s.get("fuer") in (None, x["name"])),
             "hat": bool(w)}
        if auf and w:
            e["wahl"], e["ok"] = w, w == f.get("richtig")
        sp.append(e)
    a = {"art": "quiz", "titel": _t("Familien-Quiz", "Family Quiz"),
         "unter": kategorie_anzeige(z.get("kategorie")) or _t("Gemischt", "Mixed"), "phase": z.get("phase", "frage"),
         "nr": z.get("nr", 0) + 1, "gesamt": len(z.get("fragen") or []), "spieler": sp,
         "runde": min(runde(z), z.get("runden") or 1), "runden": z.get("runden") or 1, "leiter": list(z.get("leiter") or [3]),
         "schluessel": "%s:%s:%s" % (z.get("id", ""), z.get("nr", 0), z.get("phase", ""))}
    if str(z.get("ton_url") or "").startswith("https://"):     # die Leinwand spielt die Ansage selbst ab (seit 01.11.2026)
        a["ton"], a["ton_ab"] = z["ton_url"], z.get("ton_ab") or 0
    # Zeitmarken der Ansage (seit 01.11.2026 abends, Buehne wie bei „Wer wird Millionär“): wann die Frage erscheint, wann
    # die Antworten (passend zur Ansage), wann aufgedeckt wird, und die Lautstaerke-Huellkurve fuer den Mund der Moderatorin
    for k in TAKT_FELDER:
        if (z.get("takt") or {}).get(k) not in (None, "", []):
            a[k] = z["takt"][k]
    if ende:
        a["sieger"] = sieger(z)
        a["rangliste"] = [{"name": n, "punkte": p} for n, p in rangliste(z)]
        return a
    # seit 0: die Uhr laeuft noch nicht (die Ansage kommt erst, wenn die Leinwand auf der Box ist)
    a.update({"frage": f.get("frage", ""), "antworten": list(f.get("antworten") or []), "fuer": s.get("fuer") or "",
              "stufe": f.get("stufe", ""), "seit": int(z["seit"]) if z.get("seit") is not None else int(jetzt),
              "sekunden": int(s.get("sekunden") or 0), "schwierigkeit": f.get("schwierigkeit", 3)})
    if auf:
        a["richtig"], a["wusstest"] = f.get("richtig", ""), f.get("wusstest", "")
    return a


# ---------------------------------------------------------------- Ablage
def zustand_laden(daten):
    try:
        z = json.load(open(os.path.join(ordner(daten), SPIEL), encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(z, dict) or not z.get("fragen") or not z.get("spieler"):
        return {}
    return z


def zustand_speichern(daten, z):
    _json_schreiben(os.path.join(ordner(daten), SPIEL), z or {})


def gespielt_laden(daten):
    try:
        g = json.load(open(os.path.join(ordner(daten), GESPIELT), encoding="utf-8"))
        return [str(x) for x in g][-3000:] if isinstance(g, list) else []
    except (OSError, ValueError):
        return []


def gespielt_merken(daten, ids):
    g = [x for x in gespielt_laden(daten) if x not in ids] + list(ids)
    _json_schreiben(os.path.join(ordner(daten), GESPIELT), g[-3000:])


@contextmanager
def sperre(daten):
    """Ein Spielzug zur Zeit (App und Sprachgeraet koennten gleichzeitig antworten)."""
    os.makedirs(ordner(daten), exist_ok=True)
    with open(os.path.join(ordner(daten), "spiel.lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def ton_pfad(daten, stamm):
    return os.path.join(ordner(daten), TON, stamm + ".mp3")


def ton_vorhanden(daten, stamm):
    try:
        return re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", stamm) is not None and os.path.getsize(ton_pfad(daten, stamm)) > 200
    except OSError:
        return False
