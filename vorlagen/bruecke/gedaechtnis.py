"""Gedaechtnis je Person (seit 0.4, 28.10.2026).

daten/gedaechtnis.json (600): {"version": 1, "naechste": n, "eintraege": [
    {"id": 7, "bereich": "haus"|"<person>", "text": "...", "datum": "TT.MM.JJJJ HH:MM", "quelle": "merken"|"gelernt"|
     "import"|"uebernommen", "von": "<person>", "frueher": [{"text": "...", "datum": "..."}]}]}
"haus" sieht jeder, "<person>" nur diese Person. Mehrere Prozesse schreiben (Bruecke, Werkzeug-Server, naechtliches
Lernen): jede Aenderung unter einer Dateisperre, geschrieben wird atomar.

TXT-Liste fuer die Person (auf Zuruf als Datei, geaendert zurueck als Anhang):
    [12] 23.10.2026 | Text          vorhandener Eintrag: Text aendern, Zeile loeschen oder in den anderen Abschnitt setzen
    - Text                          neuer Eintrag
Die Abschnitte "## Haus" und "## Nur fuer <Name>" bestimmen den Bereich.
"""
import contextlib
import datetime as dt
import json
import os
import re
import time

DATEI = "gedaechtnis.json"
SPERRE = "gedaechtnis.lock"
TEXT_MAX = 500
VERGESSEN_MIN, VERGESSEN_MAX = 4, 3
EINTRAEGE_MAX = 2000
KONTEXT_MAX = 6000
ZEILE = re.compile(r"^\[(\d{1,6})\]\s*(?:\d{2}\.\d{2}\.\d{4}(?: \d{2}:\d{2})?\s*\|\s*)?(.*)$")
NEU = re.compile(r"^[-*•]\s*(.+)$")


# Sprache der Texte, die die Person direkt sieht (seit 0.4 im Release). Die Bruecke setzt sie beim Start aus
# der Einrichtung (antworten.json "sprache"), wie bei verhalten.py und oberflaeche.py.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de

# Was das naechtliche Lernen nie von sich aus merkt : Kennwoerter und Zugangsdaten, Gesundheit,
# Inhalte aus Mails und Nachrichten. Fuer ausdrueckliches "merk dir" gilt das nicht (ausser Kennwoertern).
TABU_LERNEN = re.compile(
    r"\[kennwort|kennwort|passwort|password|pin\b|tan\b|token|api[- ]?key|schl[üu]ssel|zugangsdaten|iban|\bbic\b|"
    r"kreditkarte|krank|diagnose|medikament|arzt|ärzt|therapie|blutdruck|blutzucker|schwanger|depress|tablette|"
    r"symptom|krankenhaus|klinik|operation|e-mail von|mail von|newsletter|laut der mail|in der mail|"
    r"passcode|credit card|\bsick|illness|diagnos|medication|medicine|doctor|therapy|blood pressure|"
    r"blood sugar|pregnan|hospital|surgery|from the e-?mail|in the e-?mail|according to the e-?mail|credential|"
    r"health|therap|prescri|medical|login",
    re.I)


class Fehler(Exception):
    pass


def _sperren(fd):
    """Exklusive Dateisperre: flock unter Linux und macOS, msvcrt unter Windows (wie bilddienst.py)."""
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)
    except ImportError:                 # Windows: LK_LOCK versucht es etwa 10 s lang, dann OSError
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        except OSError:
            raise Fehler("Die Datei ist gerade gesperrt, bitte gleich noch einmal versuchen.")


def _entsperren(fd):
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
    except ImportError:                 # Windows: vor dem Schliessen ausdruecklich freigeben
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def _ersetzen_atomar(neu, pfad):
    """os.replace; unter Windows kurz wiederholen, falls gerade ein Leser die Datei offen hat."""
    for i in range(20):
        try:
            os.replace(neu, pfad)
            return
        except PermissionError:
            if os.name != "nt" or i == 19:
                raise
            time.sleep(0.05)


def _jetzt():
    return dt.datetime.now().strftime("%d.%m.%Y %H:%M")


def _sauber(text):
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()
    return re.sub(r"\s{2,}", " ", t)[:TEXT_MAX]


@contextlib.contextmanager
def _gesperrt(daten):
    os.makedirs(daten, exist_ok=True)
    fd = os.open(os.path.join(daten, SPERRE), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        _sperren(fd)
        try:
            yield
        finally:
            _entsperren(fd)
    finally:
        os.close(fd)


def laden(daten):
    try:
        g = json.load(open(os.path.join(daten, DATEI), encoding="utf-8"))
        if isinstance(g, dict) and isinstance(g.get("eintraege"), list):
            g.setdefault("naechste", 1 + max([e.get("id", 0) for e in g["eintraege"]] or [0]))
            return g
    except (OSError, ValueError):
        pass
    return {"version": 1, "naechste": 1, "eintraege": []}


def _speichern(daten, g):
    pfad = os.path.join(daten, DATEI)
    fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
    _ersetzen_atomar(pfad + ".neu", pfad)


def stand(daten):
    """Aenderungszeit (warme Gehirne starten neu, wenn sich das Gedaechtnis geaendert hat)."""
    try:
        return os.path.getmtime(os.path.join(daten, DATEI))
    except OSError:
        return 0


def sichtbar(e, person):
    return e.get("bereich") in ("haus", person)


def neu(daten, text, bereich, von, quelle="merken"):
    """Neuer Eintrag; gibt die Nummer zurueck (oder 0, wenn leer oder schon wortgleich vorhanden)."""
    text = _sauber(text)
    if not text:
        return 0
    with _gesperrt(daten):
        g = laden(daten)
        for e in g["eintraege"]:
            if e["bereich"] == bereich and e["text"].lower() == text.lower():
                return 0
        if len(g["eintraege"]) >= EINTRAEGE_MAX:
            raise Fehler(_t("Das Gedächtnis ist voll (%d Einträge). Lass erst ältere vergessen.",
                            "The memory is full (%d entries). Forget older ones first.") % EINTRAEGE_MAX)
        n = g["naechste"]
        g["naechste"] = n + 1
        g["eintraege"].append({"id": n, "bereich": bereich, "text": text, "datum": _jetzt(), "quelle": quelle,
                               "von": von})
        _speichern(daten, g)
        return n


def ersetzen(daten, nr, text, person, quelle="gelernt"):
    """Text eines sichtbaren Eintrags ersetzen, der alte Text bleibt unter "frueher" stehen. Gelerntes (quelle
    "gelernt") ersetzt nur Eintraege im Bereich der Person, nie Haus-Eintraege."""
    text = _sauber(text)
    with _gesperrt(daten):
        g = laden(daten)
        for e in g["eintraege"]:
            if e["id"] == nr and sichtbar(e, person):
                if quelle == "gelernt" and e["bereich"] != person:
                    return False
                if not text or text == e["text"]:
                    return False
                e.setdefault("frueher", []).append({"text": e["text"], "datum": e["datum"]})
                e["frueher"] = e["frueher"][-3:]
                e.update(text=text, datum=_jetzt(), quelle=quelle, von=person)
                _speichern(daten, g)
                return True
    return False


def fuer_person(daten, person):
    return [e for e in laden(daten)["eintraege"] if sichtbar(e, person)]


def fuer_kontext(daten, person, namen, max_zeichen=KONTEXT_MAX):
    """Gedaechtnistext fuer den Systemprompt: Haus und Privates der Person. Das Platzbudget gilt fuer beide Abschnitte
    gemeinsam, die neuesten Eintraege zuerst. Haus-Eintraege anderer Personen tragen ihren Urheber."""
    eintraege = fuer_person(daten, person)
    zeilen = {"haus": [], "privat": []}
    rest = max_zeichen
    for e in reversed(eintraege):
        von = e.get("von")
        wer = " (%s)" % namen.get(von, von) if e["bereich"] == "haus" and von and von != person else ""
        zeile = "- %s%s: %s" % (e["datum"], wer, e["text"])
        if rest - len(zeile) < 0:
            break
        zeilen["haus" if e["bereich"] == "haus" else "privat"].insert(0, zeile)
        rest -= len(zeile) + 1
    gezeigt = len(zeilen["haus"]) + len(zeilen["privat"])
    teile = []
    for titel, schl in ((_t("Haus (für alle im Haushalt)", "House (everyone in the household)"), "haus"),
                        (_t("Nur für %s", "Only for %s") % namen.get(person, person), "privat")):
        if zeilen[schl]:
            teile.append("## %s\n%s" % (titel, "\n".join(zeilen[schl])))
    text = "\n\n".join(teile)
    if len(eintraege) > gezeigt:
        text += _t("\n(Ältere Einträge stehen nicht hier: bei Bedarf gedaechtnis mit suche aufrufen.)",
                   "\n(Older entries are not listed here: call gedaechtnis with suche if needed.)")
    return text


def suchen(daten, person, suche=None, anzahl=40):
    eintraege = fuer_person(daten, person)
    if suche:
        woerter = [w for w in re.split(r"\W+", suche.lower()) if len(w) > 2] or [suche.lower()]
        eintraege = [e for e in eintraege if any(w in e["text"].lower() for w in woerter)]
    return eintraege[-anzahl:]


def vergessen(daten, person, text):
    """Sichtbare Eintraege mit diesem Text entfernen; Anzahl. Mindestens VERGESSEN_MIN Zeichen und hoechstens
    VERGESSEN_MAX Treffer, sonst Fehler (genauer sagen oder die Liste bearbeiten): ein einzelnes "e" leerte sonst
    das ganze Haus-Gedaechtnis."""
    t = str(text or "").lower().strip()
    if len(t) < VERGESSEN_MIN:
        raise Fehler(_t("Sag genauer, was ich vergessen soll.", "Tell me more precisely what to forget."))
    with _gesperrt(daten):
        g = laden(daten)
        treffer = [e for e in g["eintraege"] if sichtbar(e, person) and t in e["text"].lower()]
        if len(treffer) > VERGESSEN_MAX:
            raise Fehler(_t("Das passt auf %d Einträge. Sag es genauer, oder lass dir die Liste geben.",
                            "That matches %d entries. Be more specific, or ask for the list.") % len(treffer))
        if treffer:
            weg = {e["id"] for e in treffer}
            g["eintraege"] = [e for e in g["eintraege"] if e["id"] not in weg]
            _speichern(daten, g)
        return len(treffer)


def export_txt(daten, person, namen):
    eintraege = fuer_person(daten, person)
    name = namen.get(person, person)
    kopf = [_t("# Jarvis-Gedächtnis für %s, Stand %s", "# Jarvis memory for %s, as of %s") % (name, _jetzt()),
            _t("# Ändern: Text hinter dem Datum anpassen. Löschen: Zeile löschen. Neu: Zeile mit \"- \" beginnen.",
               "# Change: edit the text after the date. Delete: remove the line. New: start a line with \"- \"."),
            _t("# Verschieben: Zeile in den anderen Abschnitt setzen. Dann die Datei an Jarvis zurückschicken.",
               "# Move: put the line into the other section. Then send the file back to Jarvis."),
            _t("# \"Haus\" sehen alle im Haushalt, den zweiten Abschnitt nur du.",
               "# Everyone in the household sees \"House\", only you see the second section."), ""]
    teile = []
    for titel, schl in ((_t("Haus", "House"), "haus"), (_t("Nur für %s", "Only for %s") % name, person)):
        teile.append("## " + titel)
        teile += ["[%d] %s | %s" % (e["id"], e["datum"], e["text"]) for e in eintraege if e["bereich"] == schl]
        teile.append("")
    return "\n".join(kopf + teile)


def _bereich_aus(titel, person, namen):
    t = titel.strip().lower()
    if t.startswith(("haus", "house", "home")):
        return "haus"
    if t.startswith(("nur", "only")):
        return person
    return None


def import_vergleich(daten, person, txt, namen):
    """Was die zurueckgeschickte Liste aendern wuerde. Nur Eintraege, die die Person sieht; fremde Nummern zaehlen
    als unbekannt und werden nicht angefasst."""
    vorhanden = {e["id"]: e for e in fuer_person(daten, person)}
    gesehen, geaendert, neu_, unbekannt = set(), [], [], []
    bereich = None
    for roh in str(txt).replace("\r", "").split("\n"):
        z = roh.strip()
        if not z or z.startswith("# ") or z == "#":
            continue
        if z.startswith("##"):
            bereich = _bereich_aus(z.lstrip("#"), person, namen)
            continue
        if bereich is None:
            continue
        m = ZEILE.match(z)
        if m:
            nr, text = int(m.group(1)), _sauber(m.group(2))
            if nr not in vorhanden:
                unbekannt.append(nr)
                continue
            gesehen.add(nr)
            e = vorhanden[nr]
            if not text:
                continue
            if text != e["text"] or bereich != e["bereich"]:
                geaendert.append({"id": nr, "alt": e["text"], "neu": text, "bereich_alt": e["bereich"],
                                  "bereich": bereich})
            continue
        m = NEU.match(z)
        if m and _sauber(m.group(1)):
            neu_.append({"bereich": bereich, "text": _sauber(m.group(1))})
    geloescht = [{"id": nr, "text": e["text"]} for nr, e in vorhanden.items() if nr not in gesehen]
    return {"geaendert": geaendert, "geloescht": geloescht, "neu": neu_, "unbekannt": unbekannt}


def vergleich_text(v, namen, person):
    def ber(b):
        return _t("Haus", "house") if b == "haus" else _t("nur %s", "only %s") % namen.get(person, person)
    zeilen = []
    for x in v["geaendert"]:
        verschoben = _t(" (jetzt %s)", " (now %s)") % ber(x["bereich"]) if x["bereich"] != x["bereich_alt"] else ""
        zeilen.append(_t("geändert [%d]%s: %s", "changed [%d]%s: %s") % (x["id"], verschoben, x["neu"]))
    zeilen += [_t("gelöscht [%d]: %s", "deleted [%d]: %s") % (x["id"], x["text"]) for x in v["geloescht"]]
    zeilen += [_t("neu (%s): %s", "new (%s): %s") % (ber(x["bereich"]), x["text"]) for x in v["neu"]]
    if v["unbekannt"]:
        zeilen.append(_t("ignoriert (Nummern, die es für dich nicht gibt): %s",
                         "ignored (numbers that do not exist for you): %s") % ", ".join(map(str, v["unbekannt"])))
    return "\n".join(zeilen) or _t("Keine Änderungen.", "No changes.")


def import_uebernehmen(daten, person, v):
    """Aenderungen aus import_vergleich anwenden; (geaendert, geloescht, neu, uebersprungen). Ein Eintrag, der sich
    seit der Ausgabe geaendert hat (etwa nachts gelernt), wird weder ueberschrieben noch geloescht, sondern
    uebersprungen; ebenso neue Eintraege, wenn das Gedaechtnis voll ist."""
    with _gesperrt(daten):
        g = laden(daten)
        nach_id = {e["id"]: e for e in g["eintraege"] if sichtbar(e, person)}
        a = l_ = n_ = ueber = 0
        for x in v.get("geaendert", []):
            e = nach_id.get(x["id"])
            if not e or x["bereich"] not in ("haus", person):
                continue
            if e["text"] != x.get("alt") or e["bereich"] != x.get("bereich_alt"):
                ueber += 1
                continue
            if x["neu"] != e["text"]:
                e.setdefault("frueher", []).append({"text": e["text"], "datum": e["datum"]})
                e["frueher"] = e["frueher"][-3:]
            e.update(text=_sauber(x["neu"]), bereich=x["bereich"], datum=_jetzt(), quelle="import", von=person)
            a += 1
        weg = set()
        for x in v.get("geloescht", []):
            e = nach_id.get(x["id"])
            if e and e["text"] == x.get("text"):
                weg.add(x["id"])
            elif e:
                ueber += 1
        g["eintraege"] = [e for e in g["eintraege"] if e["id"] not in weg]
        l_ = len(weg)
        for x in v.get("neu", []):
            if x["bereich"] in ("haus", person) and _sauber(x["text"]):
                if len(g["eintraege"]) >= EINTRAEGE_MAX:
                    ueber += 1
                    continue
                g["eintraege"].append({"id": g["naechste"], "bereich": x["bereich"], "text": _sauber(x["text"]),
                                       "datum": _jetzt(), "quelle": "import", "von": person})
                g["naechste"] += 1
                n_ += 1
        _speichern(daten, g)
        return a, l_, n_, ueber


def migrieren(daten, zuordnung, standard):
    """Einmalig aus dem alten gedaechtnis.md (Zeilen "- TT.MM.JJJJ HH:MM: Text"): zuordnung {Zeilennummer ab 1:
    bereich}, sonst standard. Tut nichts, wenn gedaechtnis.json schon Eintraege hat. Anzahl uebernommen."""
    alt = os.path.join(daten, "gedaechtnis.md")
    with _gesperrt(daten):
        g = laden(daten)
        if g["eintraege"] or not os.path.exists(alt):
            return 0
        n = 0
        for i, z in enumerate([z for z in open(alt, encoding="utf-8") if z.strip()], 1):
            m = re.match(r"^- (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}): (.*)$", z.strip())
            datum, text = (m.group(1), m.group(2)) if m else (_jetzt(), z.strip().lstrip("- "))
            g["eintraege"].append({"id": g["naechste"], "bereich": zuordnung.get(i, standard), "text": _sauber(text),
                                   "datum": datum, "quelle": "uebernommen", "von": standard})
            g["naechste"] += 1
            n += 1
        _speichern(daten, g)
        return n
