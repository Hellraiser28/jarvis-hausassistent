"""Familienrunde (S3, Superhirn, seit 0.7): Jarvis fragt mehrere Personen und verkuendet das Ergebnis.

"Was essen wir Samstag?" - Jarvis schickt jeder Person einen Push mit Einmal-Link auf eine kleine Abstimmseite
(reines HTML-Formular, kein JavaScript), erinnert Saeumige zur Halbzeit einmal, schliesst bei Fristende oder wenn alle
abgestimmt haben, schickt das Ergebnis per Push an alle und sagt es auf Wunsch im Raum an. Gleichstand nach fester Regel.

Feste Antworten statt Freitext: Die Stimmen anderer Personen sind Zahlen (Index der Option), nie Text. So gelangt nichts,
was jemand anderes geschrieben hat, ins Gehirn. Aus demselben Grund zeigt "stand" bei Runden, die jemand anderes
gestartet hat, weder Frage noch Antworten (die stammen von dieser anderen Person), nur Nummer, Frist und ob man schon
abgestimmt hat. Wer eine Runde startet, sieht seine eigenen Texte, wer abgestimmt hat, und am Ende das Ergebnis.
Zwischenstaende gibt es nicht (geheime Wahl bis zum Schluss).

daten/familienrunde.json (0600), eine Liste:
    [{"nr": 3, "ersteller": "alex", "frage": "...", "optionen": ["Pizza", "Pasta"], "gleichstand": "fragende_person",
      "ansage": "wohnzimmer", "start": 1793000000.0, "frist": 1793007200.0, "erinnert": false,
      "teilnehmer": [{"person": "sam", "token": "<22 Zeichen>", "stimme": null, "zeit": null, "zugestellt": true}],
      "status": "offen" | "beendet" | "abgebrochen", "schluss": null, "ergebnis": null}]

Tokens (secrets.token_urlsafe(16), 128 Bit) gelten bis 24 h nach Schluss; dann leert runde() sie, nach 7 Tagen faellt
die Runde ganz weg. Vergleich mit hmac.compare_digest.

Sprache (seit 0.7 im Release): setze_sprache("de"|"en") stellt Meldungen, Pushes, Durchsage, die Abstimmseite und
WERKZEUG um. Aktionsnamen, Parameter und JSON-Schluessel bleiben gleich; Sicherheitskopfzeilen und Token-Pruefung
haengen nicht von der Sprache ab.
Schnittstelle (superhirn.py): auftrag(b, person, ctx), runde(ctx), seite(pfad, abfrage, ctx, oeffentlich).
Python 3.8, nur Standardbibliothek, Import ohne Nebenwirkungen.
"""
import datetime as dt
import hmac
import html
import json
import os
import random
import re
import secrets
import threading

NAME = "familienrunde"
RECHTE = "familie"                     # Familie ja, Gaeste nie (auch nicht als Teilnehmer)
TAKT_S = 60                            # runde(ctx): Erinnerung, Schluss, Ergebnis
# Keine Aktion ist privat genug fuer eine Lautsprecher-Sperre: stand nennt bei fremden Runden keine Texte (siehe oben).
LAUTSPRECHER_PRIVAT = frozenset()

DATEI = "familienrunde.json"
PFAD = "runde/"                        # Seite: ctx.oeffentlich("runde/<token>")
MAX_OFFEN_JE_PERSON = 5
MAX_GESPEICHERT = 100                  # Schutz gegen eine volllaufende Datei
FRIST_MIN, FRIST_MAX, FRIST_STANDARD = 10, 2880, 120
OPTIONEN_MIN, OPTIONEN_MAX = 2, 6
FRAGE_MAX, OPTION_MAX = 200, 60
GLEICHSTAND = ("fragende_person", "zufall")
TOKEN_NACH_SCHLUSS_S = 24 * 3600       # Link zeigt noch das Ergebnis, danach 404
AUFBEWAHREN_S = 7 * 86400              # beendete Runden fuer "stand", danach weg
MAX_FORMULAR = 1024                    # Bytes im POST-Body, mehr nimmt die Bruecke nicht an
ROLLEN = ("haupt", "familie")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{22}$")
ZUFALL = random.SystemRandom()         # Tests ersetzen das durch ein Objekt mit choice()
# Kennung der Runden mit Rezeptideen aus ctx.rezept_ideen. Der Wert bleibt "mealie" (Datenformat wie bisher): An ihm
# haengt, dass stand die Titel (fremder Text) nie nennt; ein neuer Wert liesse aeltere Runden durchrutschen.
QUELLE_REZEPTE = "mealie"

# Kopfzeilen, die die Bruecke zu jeder Antwort von seite() schickt (siehe superhirn.seite)
CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
KOPFZEILEN = (
    ("Content-Security-Policy", CSP),
    ("Cache-Control", "no-store"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("X-Robots-Tag", "noindex"),
)
SEITE_KOPFZEILEN = KOPFZEILEN          # gleicher Name wie in zeigen.py

_SCHEMA = {
    "type": "object",
    "properties": {
        "aktion": {"type": "string", "enum": ["neu", "stand", "abbrechen"]},
        "frage": {"type": "string"},
        "optionen": {"type": "array", "items": {"type": "string"}, "minItems": OPTIONEN_MIN,
                     "maxItems": OPTIONEN_MAX},
        "personen": {"type": "array", "items": {"type": "string"}},
        "frist_minuten": {"type": "integer", "minimum": FRIST_MIN, "maximum": FRIST_MAX},
        "gleichstand": {"type": "string", "enum": list(GLEICHSTAND)},
        "ansage": {"type": "string"},
        "nr": {"type": "integer"},
        # seit 0.7: Rezeptideen aus der Rezeptsammlung der Bruecke (ctx.rezept_ideen, z. B. Mealie) als Antworten
        "optionen_aus": {"type": "string", "enum": ["rezepte"]},
        "rezept_suche": {"type": "string"},
        "anzahl": {"type": "integer", "minimum": OPTIONEN_MIN, "maximum": OPTIONEN_MAX},
    },
}
WERKZEUG_DE = {
    "beschreibung": (
        "Familienrunde: Jarvis fragt mehrere Familienmitglieder per Push mit Link auf eine Abstimmseite (nur feste "
        "Antworten, keine Freitexte), erinnert Säumige zur Halbzeit einmal und verkündet das Ergebnis per Push an alle, "
        "auf Wunsch auch als Durchsage, z. B. „Frag alle, ob wir Samstag Pizza, Pasta oder Salat essen“. aktion neu mit "
        "frage, optionen (2–6 kurze feste Antworten), personen (Namen; „alle“ = die ganze Familie; die fragende Person "
        "stimmt nur mit ab, wenn sie selbst genannt ist oder bei „alle“), frist_minuten (10–2880, Standard 120), "
        "gleichstand fragende_person (deren Stimme entscheidet, sonst das Los; Standard) oder zufall, ansage (Raum für "
        "eine Durchsage des Ergebnisses, optional). aktion stand (eigene und laufende Runden, nr optional), abbrechen "
        "(nr, nur wer die Runde gestartet hat). Gäste machen nie mit. Wer was gewählt hat, erfährst du nicht, nur "
        "Zahlen und wer schon abgestimmt hat. Geht es ums Essen, setz optionen_aus rezepte statt optionen: Dann holt "
        "die Runde selbst anzahl (2–6, Standard 4) zufällige Rezeptideen aus der Rezeptsammlung, optional passend zu "
        "rezept_suche (z. B. „Pasta“); die Titel stehen auf der Abstimmseite und im Push an die fragende Person, nicht "
        "in deiner Antwort."),
    "schema": _SCHEMA,
}
WERKZEUG_EN = {
    "beschreibung": (
        "Family vote: Jarvis asks several family members by push with a link to a voting page (fixed answers only, no "
        "free text), reminds those who haven't voted once at half-time and announces the result by push to everyone, "
        "on request also as an announcement, e.g. “Ask everyone whether we're having pizza, pasta or salad on "
        "Saturday”. aktion neu with frage, optionen (2–6 short fixed answers), personen (names; “everyone” = the whole "
        "family; the asking person only votes if they name themselves or with “everyone”), frist_minuten (10–2880, "
        "default 120), gleichstand fragende_person (their vote decides, otherwise a draw; default) or zufall, ansage "
        "(room for an announcement of the result, optional). aktion stand (own and running votes, nr optional), "
        "abbrechen (nr, only whoever started the vote). Guests never take part. You won't learn who chose what, only "
        "numbers and who has already voted. If it's about food, set optionen_aus rezepte instead of optionen: the vote "
        "then fetches anzahl (2–6, default 4) random recipe ideas from the recipe collection itself, optionally "
        "matching rezept_suche (e.g. “pasta”); the titles appear on the voting page and in the push to the asking "
        "person, not in your answer."),
    "schema": _SCHEMA,
}
WERKZEUG = WERKZEUG_DE                 # folgt setze_sprache()
# Ziel (verschickt Pushes, Durchsage); nur "stand" liest. stand liefert keinen fremden Text (siehe oben).
FREMDTEXT = {"art": "ziel", "nur_lesen": ("aktion", "stand", ["stand"])}

WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
WOCHENTAGE_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONATE_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# Wer bei personen fuer die ganze Familie bzw. fuer die fragende Person steht (beide Sprachen, nach _norm)
ALLE_WOERTER = ("alle", "alle zusammen", "familie", "die familie", "jeder",
                "all", "all of us", "everyone", "everybody", "family", "the family")
ICH_WOERTER = ("ich", "mich", "mir", "me", "myself")
_sperre = threading.Lock()             # Datei: laden, aendern, speichern
_lauf = threading.Lock()               # runde() nie doppelt

# Sprache der Texte, die Menschen sehen oder hoeren (seit 0.7 im Release). Die Bruecke setzt sie beim Start aus der
# Einrichtung (antworten.json "sprache").
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE, WERKZEUG
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache
    WERKZEUG = WERKZEUG_EN if sprache == "en" else WERKZEUG_DE


def _t(de, en):
    return en if SPRACHE == "en" else de


# ---------------------------------------------------------------------------------------------- Hilfen
def _log(ctx, *a):
    try:
        ctx.log("Familienrunde:", *a)
    except Exception:
        pass


def _text(s, laenge):
    """Einzeilig, ohne Steuer- und Richtungszeichen, gekuerzt."""
    s = re.sub(r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩]", " ", str(s if s is not None else ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= laenge else s[:laenge - 1].rstrip() + "…"


def _norm(s):
    s = str(s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _zahl(x, standard):
    if isinstance(x, bool):
        return standard
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return standard


def _zitat(s):
    """„…“ bzw. “…”"""
    return _t("„%s“", "“%s”") % s


def _genitiv(name):
    """Alex' / Toms Stimme bzw. Alex's / Tom's vote."""
    if SPRACHE == "en":
        return name + "'s"
    return name + ("'" if name[-1:].lower() in ("s", "ß", "x", "z") else "s")


def wann(ts, jetzt):
    """'heute 18:00 Uhr', 'morgen 09:30 Uhr', 'Samstag, 07.11., 18:00 Uhr' bzw. 'today at 18:00',
    'Saturday 7 Nov at 18:00' (Ortszeit)."""
    d = dt.datetime.fromtimestamp(ts)
    tage = (d.date() - dt.datetime.fromtimestamp(jetzt).date()).days
    if SPRACHE == "en":
        tag = {0: "today", 1: "tomorrow", -1: "yesterday"}.get(tage) or "%s %d %s" % (
            WOCHENTAGE_EN[d.weekday()], d.day, MONATE_EN[d.month - 1])
        return "%s at %s" % (tag, d.strftime("%H:%M"))
    tag = {0: "heute", 1: "morgen", -1: "gestern"}.get(tage) or "%s, %s" % (WOCHENTAGE[d.weekday()],
                                                                          d.strftime("%d.%m."))
    return "%s %s Uhr" % (tag, d.strftime("%H:%M"))


def _pfad(daten):
    return os.path.join(daten, DATEI)


def _laden(daten):
    try:
        with open(_pfad(daten), encoding="utf-8") as f:
            roh = json.load(f)
    except OSError:
        return []
    except ValueError:
        try:                                        # kaputte Datei nicht still ueberschreiben
            os.replace(_pfad(daten), _pfad(daten) + ".kaputt")
        except OSError:
            pass
        return []
    return [r for r in (roh if isinstance(roh, list) else []) if _gueltig(r)]


def _gueltig(r):
    try:
        return (isinstance(r, dict) and isinstance(r["nr"], int) and isinstance(r["ersteller"], str)
                and isinstance(r["optionen"], list) and isinstance(r["teilnehmer"], list)
                and r["status"] in ("offen", "beendet", "abgebrochen") and float(r["frist"]) > 0
                and all(isinstance(t, dict) and isinstance(t.get("person"), str) for t in r["teilnehmer"]))
    except (KeyError, TypeError, ValueError):
        return False


def _speichern(daten, liste):
    pfad = _pfad(daten)
    fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=1)
    os.chmod(pfad + ".neu", 0o600)
    os.replace(pfad + ".neu", pfad)


def _rolle(ctx, person):
    try:
        return (ctx.personen().get(person) or {}).get("rolle")
    except Exception:
        return None


def _name(ctx, person):
    try:
        return _text(ctx.person_name(person), 40) or person
    except Exception:
        return person


def _personen_aufloesen(ctx, namen, ersteller):
    """Namen -> Liste von Personen-IDs (haupt/familie). (ids, fehlertext)."""
    if isinstance(namen, str):
        namen = [n for n in re.split(r"[,;]| und | and ", namen) if n.strip()]
    if not isinstance(namen, list):
        namen = []
    alle = ctx.personen()
    familie = [p for p, d in alle.items() if (d or {}).get("rolle") in ROLLEN]
    if not namen:                                   # nie stillschweigend die ganze Familie anpingen
        return [], _t("Wen soll ich fragen? Nenn mir Namen oder „alle“.", "Who should I ask? Give me names or “everyone”.")
    if any(_norm(n) in ALLE_WOERTER for n in namen if isinstance(n, str)):
        return sorted(familie, key=lambda p: (p != ersteller, p)), ""
    ids, unbekannt, gaeste = [], [], []
    for n in namen[:12]:
        k = _norm(n)
        if k in ICH_WOERTER:
            treffer = [ersteller]
        else:
            treffer = [p for p, d in alle.items() if _norm(p) == k or _norm((d or {}).get("name")) == k]
        if len(treffer) != 1:
            unbekannt.append(_text(n, 30))
            continue
        p = treffer[0]
        if (alle.get(p) or {}).get("rolle") not in ROLLEN:
            gaeste.append(_text(n, 30))
            continue
        if p not in ids:
            ids.append(p)
    if gaeste:
        return [], _t("Gäste machen bei Familienrunden nicht mit (%s).",
                      "Guests don't take part in family votes (%s).") % ", ".join(gaeste)
    if unbekannt:
        return [], _t("Wen meinst du mit %s? Ich kenne: %s.", "Who do you mean by %s? I know: %s.") % (
            ", ".join(_zitat(u) for u in unbekannt), ", ".join(_name(ctx, p) for p in sorted(familie)))
    return ids, ""


def _raum(ctx, ansage):
    """Raum-ID aus raeume.json (ID, Name oder Alias) oder ("", fehler)."""
    a = _norm(ansage)
    if not a:
        return "", ""
    try:
        raeume = (ctx.raeume() or {}).get("raeume") or {}
    except Exception:
        raeume = {}
    for rid, r in raeume.items():
        r = r or {}
        alias = r.get("alias") or []
        if isinstance(alias, str):
            alias = [alias]
        if a in [_norm(rid), _norm(r.get("name")), _norm(r.get("bereich"))] + [_norm(x) for x in alias]:
            return rid, ""
    namen = [str((r or {}).get("name") or rid) for rid, r in raeume.items()]
    return "", _t("Den Raum „%s“ kenne ich nicht. Möglich: %s.", "I don't know the room “%s”. Possible: %s.") % (
        _text(ansage, 30), ", ".join(namen) or _t("keiner", "none"))


def _link(ctx, token):
    return ctx.oeffentlich(PFAD + token)


def _tag(nr, art=""):
    """Push-tag je Runde und Art. Die HA-App ersetzt eine Meldung mit gleichem tag: Erinnerung, Abbruch und Ergebnis
    sollen den alten Abstimm-Link ersetzen, die Rezeptideen duerfen ihn nicht verdraengen."""
    return "familienrunde-%d%s" % (int(nr), "-" + art if art else "")


def _push(ctx, person, titel, text, klick=None, tag="familienrunde"):
    try:
        return bool(ctx.push(person, titel, text, klick=klick, tag=tag))
    except Exception as x:
        _log(ctx, "Push an", person, "fehlgeschlagen:", type(x).__name__)
        return False


# ---------------------------------------------------------------------------------------------- Auswertung
def auswerten(r):
    """Ergebnis einer Runde: gewinner (Index oder None), stimmen je Option, abgegeben, entscheid
    (mehrheit | fragende_person | zufall | zufall_ersatz | keine_stimmen), spitze (Indizes beim Gleichstand)."""
    n = len(r["optionen"])
    stimmen = [0] * n
    for t in r["teilnehmer"]:
        s = t.get("stimme")
        if isinstance(s, int) and not isinstance(s, bool) and 0 <= s < n:
            stimmen[s] += 1
    abgegeben = sum(stimmen)
    erg = {"stimmen": stimmen, "abgegeben": abgegeben, "teilnehmer": len(r["teilnehmer"]), "gewinner": None,
           "entscheid": "keine_stimmen", "spitze": []}
    if not abgegeben:
        return erg
    hoch = max(stimmen)
    spitze = [i for i, c in enumerate(stimmen) if c == hoch]
    erg["spitze"] = spitze
    if len(spitze) == 1:
        erg.update(gewinner=spitze[0], entscheid="mehrheit")
        return erg
    if r.get("gleichstand") == "fragende_person":
        eigene = next((t.get("stimme") for t in r["teilnehmer"] if t.get("person") == r["ersteller"]), None)
        if eigene in spitze:
            erg.update(gewinner=eigene, entscheid="fragende_person")
            return erg
        erg.update(gewinner=ZUFALL.choice(spitze), entscheid="zufall_ersatz")
        return erg
    erg.update(gewinner=ZUFALL.choice(spitze), entscheid="zufall")
    return erg


def ergebnis_text(ctx, r, kurz=False):
    """Ergebnis als Satz (fuer Push, Seite und stand des Erstellers)."""
    e = r.get("ergebnis") or auswerten(r)
    opt = r["optionen"]
    if e["gewinner"] is None:
        return _t("Bei „%s“ hat niemand abgestimmt.", "Nobody voted on “%s”.") % r["frage"]
    g = opt[e["gewinner"]]
    zeile = "%s: %s" % (_zitat(r["frage"]), g)
    if e["entscheid"] == "mehrheit":
        zeile += _t(" (%d von %d Stimmen).", " (%d of %d votes).") % (e["stimmen"][e["gewinner"]], e["abgegeben"])
    else:
        gleich = _t(" und ", " and ").join(opt[i] for i in e["spitze"])
        wer = _name(ctx, r["ersteller"])
        zeile += _t(". Gleichstand zwischen %s, %s.", ". Tie between %s, %s.") % (gleich, {
            "fragende_person": _t("%s Stimme entscheidet", "%s vote decides") % _genitiv(wer),
            "zufall": _t("das Los entscheidet", "a draw decides"),
            "zufall_ersatz": _t("%s hat für keine davon gestimmt, also entscheidet das Los",
                                "%s voted for none of them, so a draw decides") % wer,
        }[e["entscheid"]])
    if kurz:
        return zeile
    verteilung = ", ".join("%s %d" % (o, e["stimmen"][i]) for i, o in enumerate(opt))
    return _t("%s Stimmen: %s. Abgestimmt haben %d von %d.", "%s Votes: %s. %d of %d voted.") % (
        zeile, verteilung, e["abgegeben"], e["teilnehmer"])


# ---------------------------------------------------------------------------------------------- Werkzeug
def auftrag(b, person, ctx):
    """Werkzeug familienrunde: aktion neu | stand | abbrechen. -> {"meldung": str, ...}"""
    b = b if isinstance(b, dict) else {}
    if _rolle(ctx, person) not in ROLLEN:
        return {"meldung": _t("Familienrunden gibt es nur für die Familie.", "Family votes are only for the family.")}
    aktion = b.get("aktion")
    aktion = "stand" if aktion is None or aktion == "" else str(aktion)
    if aktion == "neu":
        return _neu(b, person, ctx)
    if aktion == "stand":
        return {"meldung": _stand(b, person, ctx)}
    if aktion == "abbrechen":
        return {"meldung": _abbrechen(b, person, ctx)}
    return {"meldung": _t("aktion muss neu, stand oder abbrechen sein.", "aktion must be neu, stand or abbrechen.")}


def _neu(b, person, ctx):
    jetzt = ctx.jetzt()
    frage = _text(b.get("frage"), FRAGE_MAX)
    if not frage:
        return {"meldung": _t("Was soll ich fragen?", "What should I ask?")}
    # Seit 0.7: Antworten aus der Rezeptsammlung der Bruecke (ctx.rezept_ideen). Die Titel sind fremder Text (Rezepte
    # kommen auch aus dem Netz): Sie gehen auf die Abstimmseite und in Pushes, nie in die Antwort ans Gehirn (sonst
    # umginge das die Fremdtext-Sperre, unter der das Werkzeug rezepte steht).
    aus_rezepten = str(b.get("optionen_aus") or "") == "rezepte"
    if aus_rezepten:
        wunsch = max(OPTIONEN_MIN, min(OPTIONEN_MAX, _zahl(b.get("anzahl"), 4) if b.get("anzahl") is not None else 4))
        try:
            ideen = ctx.rezept_ideen(wunsch, _text(b.get("rezept_suche"), 40) or None)
        except Exception as x:
            _log(ctx, "Rezeptideen:", type(x).__name__)
            ideen = []
        roh, gesehen = [], set()
        for o in ideen if isinstance(ideen, list) else []:
            t = _text(o, OPTION_MAX)
            if t and _norm(t) not in gesehen:
                gesehen.add(_norm(t))
                roh.append(t)
        roh = roh[:wunsch]
        if len(roh) < OPTIONEN_MIN:
            return {"meldung": _t("Aus der Rezeptsammlung kamen gerade zu wenige Rezeptideen. Nenn mir die Antworten "
                                  "lieber selbst.",
                                  "Too few recipe ideas came from the recipe collection just now. Better give me the "
                                  "answers yourself.")}
    else:
        roh = b.get("optionen")
    if isinstance(roh, str):
        roh = [x for x in re.split(r"[,;/|]", roh)]
    optionen = [_text(o, OPTION_MAX) for o in (roh if isinstance(roh, list) else []) if isinstance(o, (str, int, float))
                and not isinstance(o, bool)]
    optionen = [o for o in optionen if o]
    if not OPTIONEN_MIN <= len(optionen) <= OPTIONEN_MAX:
        return {"meldung": _t("Ich brauche %d bis %d feste Antworten (keine Freitexte).",
                              "I need %d to %d fixed answers (no free text).") % (OPTIONEN_MIN, OPTIONEN_MAX)}
    if len({_norm(o) for o in optionen}) != len(optionen):
        return {"meldung": _t("Zwei Antworten sind gleich, bitte jede nur einmal.",
                              "Two answers are the same, please give each one only once.")}
    gleichstand = str(b.get("gleichstand") or "fragende_person")
    if gleichstand not in GLEICHSTAND:
        return {"meldung": _t("gleichstand muss fragende_person oder zufall sein.",
                              "gleichstand must be fragende_person or zufall.")}
    frist_wunsch = _zahl(b.get("frist_minuten"), FRIST_STANDARD) if b.get("frist_minuten") is not None \
        else FRIST_STANDARD
    frist = max(FRIST_MIN, min(FRIST_MAX, frist_wunsch))
    raum, fehler = _raum(ctx, b.get("ansage"))
    if fehler:
        return {"meldung": fehler}
    ids, fehler = _personen_aufloesen(ctx, b.get("personen"), person)
    if fehler:
        return {"meldung": fehler}
    if not ids:
        return {"meldung": _t("Wen soll ich fragen?", "Who should I ask?")}
    if ids == [person]:
        return {"meldung": _t("Wen soll ich außer dir fragen?", "Who should I ask besides you?")}
    with _sperre:
        liste = _aufraeumen(_laden(ctx.daten), jetzt)
        if sum(1 for r in liste if r["ersteller"] == person and r["status"] == "offen") >= MAX_OFFEN_JE_PERSON:
            return {"meldung": _t("Du hast schon %d offene Runden. Warte eine ab oder brich eine ab.",
                                  "You already have %d open votes. Wait for one to finish or cancel one.")
                    % MAX_OFFEN_JE_PERSON}
        if len(liste) >= MAX_GESPEICHERT:
            return {"meldung": _t("Gerade sind zu viele Runden gespeichert, versuch es später noch einmal.",
                                  "Too many votes are stored right now, try again later.")}
        nr = max([r["nr"] for r in liste] + [0]) + 1
        vergeben = {t.get("token") for r in liste for t in r["teilnehmer"]}
        teilnehmer = []
        for p in ids:
            t = secrets.token_urlsafe(16)
            while t in vergeben:
                t = secrets.token_urlsafe(16)
            vergeben.add(t)
            teilnehmer.append({"person": p, "token": t, "stimme": None, "zeit": None, "zugestellt": False})
        r = {"nr": nr, "ersteller": person, "frage": frage, "optionen": optionen, "gleichstand": gleichstand,
             "ansage": raum, "start": jetzt, "frist": jetzt + frist * 60, "erinnert": False,
             "teilnehmer": teilnehmer, "status": "offen", "schluss": None, "ergebnis": None,
             "quelle": QUELLE_REZEPTE if aus_rezepten else ""}
        liste.append(r)
        _speichern(ctx.daten, liste)
    wer = _name(ctx, person)
    bis = wann(r["frist"], jetzt)
    zugestellt = {}
    for t in teilnehmer:
        text = (_t("%s fragt: %s Antippen zum Abstimmen (bis %s).", "%s asks: %s Tap to vote (until %s).")
                % (wer, frage, bis) if t["person"] != person
                else _t("Deine Runde: %s Antippen zum Abstimmen (bis %s).", "Your vote: %s Tap to vote (until %s).")
                % (frage, bis))
        zugestellt[t["person"]] = _push(ctx, t["person"], _t("Familienrunde", "Family vote"), text,
                                        klick=_link(ctx, t["token"]), tag=_tag(nr))
    with _sperre:
        liste = _laden(ctx.daten)
        for x in liste:
            if x["nr"] == nr:
                for t in x["teilnehmer"]:
                    t["zugestellt"] = bool(zugestellt.get(t["person"]))
                _speichern(ctx.daten, liste)
                break
    erreicht = [p for p in ids if zugestellt.get(p)]
    if not erreicht:
        with _sperre:
            liste = [x for x in _laden(ctx.daten) if x["nr"] != nr]
            _speichern(ctx.daten, liste)
        return {"meldung": _t("Ich konnte niemanden erreichen (kein Push-Kanal), die Runde habe ich wieder verworfen.",
                              "I couldn't reach anyone (no push channel), so I dropped the vote again.")}
    andere = [_name(ctx, p) for p in ids if p != person]
    if aus_rezepten:          # Titel nur per Push an die fragende Person, nicht in die Antwort (fremder Text)
        _push(ctx, person, _t("Familienrunde: Rezeptideen", "Family vote: recipe ideas"),
              _t("Zur Wahl für „%s“: %s.", "To choose from for “%s”: %s.") % (frage, " / ".join(optionen)),
              tag=_tag(nr, "ideen"))
        auswahl = _t("%d Rezeptideen aus der Rezeptsammlung, die Liste kommt per Push",
                     "%d recipe ideas from the recipe collection, the list comes by push") % len(optionen)
    else:
        auswahl = " / ".join(optionen)
    teile = [_t("Ich frage %s: „%s“ (%s), Antworten bis %s.", "I'm asking %s: “%s” (%s), answers until %s.") % (
        _t(" und ", " and ").join(([", ".join(andere[:-1]), andere[-1]] if len(andere) > 1 else andere))
        or _t("dich", "you"), frage, auswahl, bis)]
    if person in ids and andere:
        teile.append(_t("Du bekommst auch einen Link zum Abstimmen.", "You'll get a voting link too."))
    if frist != frist_wunsch:
        teile.append(_t("Die Frist habe ich auf %d Minuten gesetzt (erlaubt %d bis %d).",
                        "I set the deadline to %d minutes (allowed %d to %d).") % (frist, FRIST_MIN, FRIST_MAX))
    if gleichstand == "zufall":
        teile.append(_t("Bei Gleichstand entscheidet das Los.", "If there's a tie, a draw decides."))
    elif person in ids:
        teile.append(_t("Bei Gleichstand entscheidet deine Stimme.", "If there's a tie, your vote decides."))
    else:
        teile.append(_t("Du stimmst selbst nicht mit ab, bei Gleichstand entscheidet deshalb das Los.",
                        "You're not voting yourself, so if there's a tie, a draw decides."))
    if raum:
        teile.append(_t("Das Ergebnis sage ich zusätzlich im Raum %s an.",
                        "I'll also announce the result in the room %s.") % _raumname(ctx, raum))
    fehlt = [_name(ctx, p) for p in ids if not zugestellt.get(p)]
    if fehlt:
        teile.append(_t("Nicht erreicht (kein Push-Kanal): %s.", "Not reached (no push channel): %s.") % ", ".join(fehlt))
    teile.append(_t("(Nr. %d)", "(No. %d)") % nr)
    _log(ctx, "Runde Nr.", nr, "von", person, "mit", len(ids), "Teilnehmern")
    return {"meldung": " ".join(teile), "nr": nr}


def _raumname(ctx, rid):
    try:
        return str(((ctx.raeume() or {}).get("raeume") or {}).get(rid, {}).get("name") or rid)
    except Exception:
        return rid


def _stand(b, person, ctx):
    jetzt = ctx.jetzt()
    nr = _zahl(b.get("nr"), 0)
    with _sperre:
        liste = _laden(ctx.daten)
    eigene = [r for r in liste if (r["ersteller"] == person or any(t["person"] == person for t in r["teilnehmer"]))
              and (not nr or r["nr"] == nr)]
    if not eigene:
        return (_t("Da ist keine passende Familienrunde.", "There's no matching family vote.") if nr
                else _t("Keine Familienrunden.", "No family votes."))
    zeilen = []
    for r in sorted(eigene, key=lambda x: x["nr"]):
        ich = next((t for t in r["teilnehmer"] if t["person"] == person), None)
        if r["ersteller"] == person:
            if r["status"] == "offen":
                ja = [_name(ctx, t["person"]) for t in r["teilnehmer"] if t.get("stimme") is not None]
                nein = [_name(ctx, t["person"]) for t in r["teilnehmer"] if t.get("stimme") is None]
                zeilen.append(_t("Nr. %d (offen bis %s): %s (%s) – abgestimmt %d von %d%s%s. Ergebnis erst zum "
                                 "Schluss.",
                                 "No. %d (open until %s): %s (%s) – %d of %d voted%s%s. Result only at the end.")
                              % (r["nr"], wann(r["frist"], jetzt), _zitat(r["frage"]),
                                 _t("Rezeptideen aus der Rezeptsammlung", "recipe ideas from the recipe collection")
                                 if r.get("quelle") == QUELLE_REZEPTE else " / ".join(r["optionen"]),
                                 len(ja), len(r["teilnehmer"]),
                                 (" (%s)" % ", ".join(ja)) if ja else "",
                                 (_t("; fehlt noch: %s", "; still missing: %s") % ", ".join(nein)) if nein else ""))
            elif r["status"] == "abgebrochen":
                zeilen.append(_t("Nr. %d (abgebrochen): %s.", "No. %d (cancelled): %s.") % (r["nr"],
                                                                                          _zitat(r["frage"])))
            elif r.get("quelle") == QUELLE_REZEPTE:  # Gewinner ist ein Rezepttitel (fremder Text): nur per Push
                zeilen.append(_t("Nr. %d (beendet): %s, das Ergebnis kam per Push.",
                                 "No. %d (finished): %s, the result came by push.") % (r["nr"], _zitat(r["frage"])))
            else:
                zeilen.append(_t("Nr. %d (beendet): %s", "No. %d (finished): %s") % (r["nr"], ergebnis_text(ctx, r)))
            continue
        # Runde einer anderen Person: deren Frage und Antworten sind fremder Text -> nur Eckdaten
        wer = _name(ctx, r["ersteller"])
        if r["status"] == "offen":
            zeilen.append(_t("Nr. %d von %s, offen bis %s – %s.", "No. %d from %s, open until %s – %s.") % (
                r["nr"], wer, wann(r["frist"], jetzt),
                _t("du hast abgestimmt (ändern geht über den Link)", "you have voted (you can change it via the link)")
                if ich and ich.get("stimme") is not None
                else _t("du hast noch nicht abgestimmt (Link per Push)", "you haven't voted yet (link by push)")))
        elif r["status"] == "abgebrochen":
            zeilen.append(_t("Nr. %d von %s wurde abgebrochen.", "No. %d from %s was cancelled.") % (r["nr"], wer))
        else:
            zeilen.append(_t("Nr. %d von %s ist beendet, das Ergebnis kam per Push.",
                             "No. %d from %s has finished, the result came by push.") % (r["nr"], wer))
    return "\n".join(zeilen)


def _abbrechen(b, person, ctx):
    jetzt = ctx.jetzt()
    nr = _zahl(b.get("nr"), 0)
    with _sperre:
        liste = _laden(ctx.daten)
        offen = [r for r in liste if r["ersteller"] == person and r["status"] == "offen"]
        if not nr:
            if len(offen) != 1:
                return (_t("Welche Runde? Sag mir die Nummer.", "Which vote? Tell me the number.") if offen
                        else _t("Du hast keine offene Runde.", "You have no open vote."))
            nr = offen[0]["nr"]
        r = next((x for x in liste if x["nr"] == nr), None)
        if r is None or (r["ersteller"] != person and not any(t["person"] == person for t in r["teilnehmer"])):
            return _t("Da ist keine passende Familienrunde.", "There's no matching family vote.")
        if r["ersteller"] != person:
            return _t("Abbrechen kann nur, wer die Runde gestartet hat (%s).",
                      "Only whoever started the vote can cancel it (%s).") % _name(ctx, r["ersteller"])
        if r["status"] != "offen":
            return _t("Die Runde Nr. %d ist schon vorbei.", "Vote no. %d is already over.") % nr
        r["status"], r["schluss"] = "abgebrochen", jetzt
        _speichern(ctx.daten, liste)
        empfaenger = [t["person"] for t in r["teilnehmer"] if t["person"] != person]
        frage = r["frage"]
    for p in empfaenger:
        _push(ctx, p, _t("Familienrunde", "Family vote"),
              _t("%s hat die Runde „%s“ abgebrochen.", "%s cancelled the vote “%s”.") % (_name(ctx, person), frage),
              tag=_tag(nr))
    _log(ctx, "Runde Nr.", nr, "abgebrochen")
    return _t("Runde Nr. %d abgebrochen%s.", "Vote no. %d cancelled%s.") % (
        nr, _t(", die anderen wissen Bescheid", ", the others have been told") if empfaenger else "")


# ---------------------------------------------------------------------------------------------- Hintergrund
def _aufraeumen(liste, jetzt):
    """Tokens 24 h nach Schluss leeren, Runden nach 7 Tagen entfernen (aendert liste)."""
    rest = []
    for r in liste:
        if r["status"] != "offen" and r.get("schluss"):
            if jetzt >= r["schluss"] + AUFBEWAHREN_S:
                continue
            if jetzt >= r["schluss"] + TOKEN_NACH_SCHLUSS_S:
                for t in r["teilnehmer"]:
                    t["token"] = ""
        rest.append(r)
    return rest


def runde(ctx):
    """Aus dem Hintergrund (TAKT_S): Halbzeit-Erinnerung, Schluss, Ergebnis, Aufraeumen. Wirft nie."""
    if not _lauf.acquire(blocking=False):
        return
    try:
        _runde(ctx)
    except Exception as x:
        _log(ctx, "Fehler in runde:", type(x).__name__, x)
    finally:
        _lauf.release()


def _runde(ctx):
    jetzt = ctx.jetzt()
    erinnern, fertig = [], []
    with _sperre:
        liste = _laden(ctx.daten)
        vorher = json.dumps(liste, sort_keys=True)
        for r in liste:
            if r["status"] != "offen":
                continue
            alle = all(t.get("stimme") is not None for t in r["teilnehmer"])
            if jetzt >= r["frist"] or alle:
                r["status"], r["schluss"] = "beendet", jetzt
                r["ergebnis"] = auswerten(r)
                fertig.append(json.loads(json.dumps(r)))
            elif not r.get("erinnert") and jetzt >= r["start"] + (r["frist"] - r["start"]) / 2.0:
                r["erinnert"] = True
                erinnern.append(json.loads(json.dumps(r)))
        liste = _aufraeumen(liste, jetzt)
        if json.dumps(liste, sort_keys=True) != vorher:
            _speichern(ctx.daten, liste)
    for r in erinnern:
        wer = _name(ctx, r["ersteller"])
        for t in r["teilnehmer"]:
            if t.get("stimme") is None and t.get("token"):
                text = (_t("%s wartet noch auf deine Stimme: %s Antippen zum Abstimmen (bis %s).",
                           "%s is still waiting for your vote: %s Tap to vote (until %s).") % (
                    wer, r["frage"], wann(r["frist"], jetzt)) if t["person"] != r["ersteller"]
                    else _t("Du hast in deiner eigenen Runde noch nicht abgestimmt: %s (bis %s).",
                            "You haven't voted in your own vote yet: %s (until %s).") % (
                        r["frage"], wann(r["frist"], jetzt)))
                _push(ctx, t["person"], _t("Familienrunde: Erinnerung", "Family vote: reminder"), text,
                      klick=_link(ctx, t["token"]), tag=_tag(r["nr"]))
        _log(ctx, "Runde Nr.", r["nr"], "Erinnerung verschickt")
    for r in fertig:
        text = ergebnis_text(ctx, r)
        empfaenger = [t["person"] for t in r["teilnehmer"]]
        if r["ersteller"] not in empfaenger:
            empfaenger.append(r["ersteller"])
        for p in empfaenger:
            _push(ctx, p, _t("Familienrunde: Ergebnis", "Family vote: result"), text, tag=_tag(r["nr"]))
        if r.get("ansage") and r["ergebnis"]["gewinner"] is not None:
            try:
                ctx.durchsage(r["ansage"], _t("Die Familienrunde ist entschieden. ", "The family vote is decided. ")
                              + ergebnis_text(ctx, r, kurz=True))
            except Exception as x:
                _log(ctx, "Durchsage fehlgeschlagen:", type(x).__name__)
        _log(ctx, "Runde Nr.", r["nr"], "beendet:", r["ergebnis"]["entscheid"])


# ---------------------------------------------------------------------------------------------- Seite
SEITE_HTML = """<!doctype html><html lang="@SPRACHE@"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>@TITEL@</title><style>
html,body{margin:0;background:#070a12;color:#e8ecf4;font-family:system-ui,-apple-system,sans-serif}
main{box-sizing:border-box;max-width:520px;margin:0 auto;padding:28px 16px;display:flex;flex-direction:column;gap:16px}
h1{margin:0;font-size:13px;font-weight:600;letter-spacing:.16em;color:#9aa6bc}
h2{margin:0;font-size:22px;line-height:1.3;font-weight:600}
form{display:flex;flex-direction:column;gap:10px;margin:0}
button{font:inherit;font-size:18px;padding:14px 16px;border-radius:12px;border:1px solid #2a3550;background:#111829;
color:#e8ecf4;text-align:left;cursor:pointer}
button.gewaehlt{border-color:#4f8cff;background:#14254a}
p{margin:0;font-size:15px;line-height:1.45;color:#9aa6bc}
p.danke{color:#7fd6a4}p.fehler{color:#ff9a8a}p.ergebnis{font-size:18px;color:#e8ecf4}
</style></head><body><main><h1>@KOPF@</h1>
@INHALT@
</main></body></html>"""


def _e(s):
    return html.escape(str(s), quote=True)


def _html(inhalt):
    # Platzhalter statt %-Formatierung (das CSS enthaelt %); inhalt ist bereits escaped. Die festen Platzhalter zuerst,
    # @INHALT@ zuletzt: so wird nie ein Platzhalter in Text von Personen ersetzt.
    seite = (SEITE_HTML.replace("@SPRACHE@", _t("de", "en"))
             .replace("@TITEL@", _t("Familienrunde", "Family vote"))
             .replace("@KOPF@", _t("FAMILIENRUNDE", "FAMILY VOTE")))
    return seite.replace("@INHALT@", inhalt).encode("utf-8")


def _nicht_gueltig():
    return 404, "text/plain; charset=utf-8", _t("Nicht (mehr) gültig.", "Not valid (any more).").encode("utf-8")


def _finden(liste, token):
    """(runde, teilnehmer) zum Token; jeder Vergleich in konstanter Zeit."""
    gefunden = None
    kandidat = token.encode("ascii")
    for r in liste:
        for t in r["teilnehmer"]:
            gespeichert = t.get("token") or ""
            if TOKEN.match(gespeichert) and hmac.compare_digest(gespeichert.encode("ascii"), kandidat):
                gefunden = (r, t)
    return gefunden


def _formular(r, t, jetzt):
    knoepfe = []
    for i, o in enumerate(r["optionen"]):
        gewaehlt = t.get("stimme") == i
        knoepfe.append('<button type="submit" name="wahl" value="%d"%s>%s%s</button>' % (
            i, ' class="gewaehlt"' if gewaehlt else "", _e(o), " ✓" if gewaehlt else ""))
    abgestimmt = sum(1 for x in r["teilnehmer"] if x.get("stimme") is not None)
    return ('<form method="post">%s</form><p>%s</p>'
            % ("".join(knoepfe), _t("Du kannst deine Stimme bis %s ändern. Abgestimmt: %d von %d.",
                                    "You can change your vote until %s. Voted: %d of %d.")
               % (_e(wann(r["frist"], jetzt)), abgestimmt, len(r["teilnehmer"]))))


def seite(pfad, abfrage, ctx, oeffentlich):
    """Abstimmseite /runde/<token>. -> (code, content_type, bytes) oder None (nicht diese Seite).
    abfrage: dict der Felder (GET: Query, POST: Formular) plus "_methode" ("GET"|"POST"), von der Bruecke gesetzt.
    Nur POST mit gueltigem Feld wahl zaehlt als Stimme. Wirft nie."""
    p = str(pfad or "").split("?", 1)[0].lstrip("/")
    if not p.startswith(PFAD):
        return None
    try:
        return _seite(p[len(PFAD):], abfrage if isinstance(abfrage, dict) else {}, ctx)
    except Exception as x:
        _log(ctx, "Seite:", type(x).__name__)
        return 500, "text/plain; charset=utf-8", _t("Gerade nicht verfügbar.", "Not available right now.").encode("utf-8")


def _feld(abfrage, name):
    v = abfrage.get(name)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    return v if isinstance(v, str) else None


def _seite(token, abfrage, ctx):
    if not TOKEN.match(token):
        return _nicht_gueltig()
    jetzt = ctx.jetzt()
    post = _feld(abfrage, "_methode") == "POST"
    hinweis = ""
    with _sperre:
        liste = _laden(ctx.daten)
        treffer = _finden(liste, token)
        if treffer is None:
            return _nicht_gueltig()
        r, t = treffer
        if r["status"] != "offen" and jetzt >= (r.get("schluss") or 0) + TOKEN_NACH_SCHLUSS_S:
            return _nicht_gueltig()
        offen = r["status"] == "offen" and jetzt < r["frist"]
        code = 200
        if post and offen:
            wahl = _feld(abfrage, "wahl") or ""
            if re.fullmatch(r"[0-9]", wahl) and int(wahl) < len(r["optionen"]):
                t["stimme"], t["zeit"] = int(wahl), jetzt
                _speichern(ctx.daten, liste)
                hinweis = ('<p class="danke">%s</p>'
                           % (_t("Danke, %s! Deine Stimme für „%s“ ist gezählt.",
                                 "Thanks, %s! Your vote for “%s” has been counted.")
                              % (_e(_name(ctx, t["person"])), _e(r["optionen"][t["stimme"]]))))
            else:
                code = 400
                hinweis = '<p class="fehler">%s</p>' % _t("Diese Antwort gibt es nicht, bitte einen der Knöpfe nehmen.",
                                                          "That answer doesn't exist, please use one of the buttons.")
        elif post:
            code = 409
            hinweis = '<p class="fehler">%s</p>' % _t("Die Abstimmung ist schon vorbei, deine Stimme zählt nicht mehr.",
                                                      "The vote is already over, your vote no longer counts.")
        r = json.loads(json.dumps(r))
        t = next(x for x in r["teilnehmer"] if x.get("token") == t.get("token"))
    wer = _name(ctx, r["ersteller"])
    kopf = "<p>%s</p><h2>%s</h2>" % (_e((_t("%s fragt:", "%s asks:") % wer) if r["ersteller"] != t["person"]
                                        else _t("Deine Runde:", "Your vote:")), _e(r["frage"]))
    if r["status"] == "abgebrochen":
        rumpf = "<p class=\"ergebnis\">%s</p>" % _e(_t("%s hat die Runde abgebrochen.", "%s cancelled the vote.") % wer)
    elif not offen:
        if r["status"] == "beendet":
            rumpf = '<p class="ergebnis">%s</p>' % _e(ergebnis_text(ctx, r))
        else:                                       # Frist vorbei, runde() hat noch nicht ausgewertet
            rumpf = "<p>%s</p>" % _t("Die Abstimmung ist vorbei. Das Ergebnis kommt gleich per Push.",
                                     "The vote is over. The result is coming by push shortly.")
        if t.get("stimme") is not None:
            rumpf += "<p>%s</p>" % (_t("Deine Stimme: %s.", "Your vote: %s.") % _e(r["optionen"][t["stimme"]]))
    else:
        rumpf = _formular(r, t, jetzt)
    return code, "text/html; charset=utf-8", _html(kopf + hinweis + rumpf)
