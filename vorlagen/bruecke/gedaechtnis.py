"""Gedaechtnis je Person (seit 0.4, 28.10.2026).

daten/gedaechtnis.json (600): {"version": 1, "naechste": n, "eintraege": [
    {"id": 7, "bereich": "haus"|"<person>", "text": "...", "datum": "TT.MM.JJJJ HH:MM", "quelle": "merken"|"gelernt"|
     "import"|"uebernommen"|"app", "von": "<letzte Aenderung>", "autor": "<Urheber, bleibt>", "frueher": [{"text": "...", "datum": "..."}]}]}
"haus" sieht jeder, "<person>" nur diese Person. Mehrere Prozesse schreiben (Bruecke, Werkzeug-Server, naechtliches
Lernen): jede Aenderung unter einer Dateisperre, geschrieben wird atomar.

TXT-Liste fuer die Person (auf Zuruf als Datei, geaendert zurueck als Anhang):
    [12] 23.10.2026 | Text          vorhandener Eintrag: Text aendern, Zeile loeschen oder in den anderen Abschnitt setzen
    - Text                          neuer Eintrag
Die Abschnitte "## Haus" und "## Nur fuer <Name>" bestimmen den Bereich.

Aendern und Loeschen (seit 0.6): Eigenes darf die Person immer. Einen Haus-Eintrag aendern oder loeschen nur, wer ihn
gemerkt hat ("autor", bei alten Eintraegen "von") und die Hauptperson; alle anderen sehen ihn nur. Die Regel steht in
bearbeitbar() und gilt fuer jeden Weg: Werkzeuge (vergessen, Gedaechtnis-Liste), Sternbild-Endpunkt, naechtliches Lernen.
Die Aufrufer geben dafuer haupt (personen.haupt) mit; ohne haupt darf nur der Urheber (sicherer Standard).

Nutzung (seit 0.6): daten/gedaechtnis_nutzung.json (600) {"version": 1, "eintraege": {"<id>": {"zuletzt": "TT.MM.JJJJ HH:MM",
"n": Anzahl}}}. Bewusst eine eigene Datei: gedaechtnis.json aendert die Aenderungszeit, und daran starten warme Gehirne neu
(stand()); ein Lesezugriff darf das nicht ausloesen. Gezaehlt wird, wenn (a) das Gehirn per Werkzeug "gedaechtnis" gezielt nach
einem Begriff gesucht hat (die Treffer), oder (b) seine Antwort einen Eintrag erkennbar aufgreift (mindestens zwei
Inhaltswoerter des Eintrags stehen in der Antwort). "Im Kontext" allein zaehlt nicht: Der Systemprompt enthaelt bei jeder Frage
die neuesten Eintraege, das sagt nichts ueber Nutzung. Hoechstens eine Zaehlung je Eintrag und Stunde, ein Schreibvorgang je
Aufruf und nur bei Aenderung.
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
NUTZUNG = "gedaechtnis_nutzung.json"
NUTZUNG_ABSTAND_MIN = 60


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


def bearbeitbar(e, person, haupt=None):
    """Darf die Person diesen Eintrag aendern oder loeschen? Eigenes ja; Haus nur der Urheber ("von") und die Hauptperson
    (haupt = Kennung der Hauptperson, personen.haupt). Urheber ist "autor" (bleibt, auch wenn die Hauptperson den Text aendert),
    bei alten Eintraegen "von". Ohne beides nur die Hauptperson."""
    if not sichtbar(e, person):
        return False
    if e.get("bereich") != "haus":
        return True
    autor = e.get("autor") or e.get("von")
    return (autor is not None and autor == person) or (haupt is not None and person == haupt)


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
                               "von": von, "autor": von})
        _speichern(daten, g)
        return n


def ersetzen(daten, nr, text, person, quelle="gelernt", haupt=None):
    """Text eines Eintrags ersetzen, den die Person aendern darf (bearbeitbar, seit 0.6), der alte Text bleibt unter
    "frueher" stehen. Gelerntes (quelle "gelernt") ersetzt nur Eintraege im Bereich der Person, nie Haus-Eintraege."""
    text = _sauber(text)
    with _gesperrt(daten):
        g = laden(daten)
        for e in g["eintraege"]:
            if e["id"] == nr and bearbeitbar(e, person, haupt):
                if quelle == "gelernt" and e["bereich"] != person:
                    return False
                if not text or text == e["text"]:
                    return False
                e.setdefault("autor", e.get("von"))          # Urheber merken, bevor "von" auf den Aendernden springt
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


def vergessen(daten, person, text, haupt=None):
    """Sichtbare Eintraege mit diesem Text entfernen; Anzahl. Mindestens VERGESSEN_MIN Zeichen und hoechstens
    VERGESSEN_MAX Treffer, sonst Fehler (genauer sagen oder die Liste bearbeiten): ein einzelnes "e" leerte sonst
    das ganze Haus-Gedaechtnis. Seit 0.6 nur, was die Person auch aendern darf (bearbeitbar); gehoert alles Gefundene
    anderen, kommt ein Fehler."""
    return vergessen_ex(daten, person, text, haupt)[0]


def vergessen_ex(daten, person, text, haupt=None):
    """Wie vergessen, liefert (entfernt, gesperrt): gesperrt sind Treffer, die der Person nicht gehoeren."""
    t = str(text or "").lower().strip()
    if len(t) < VERGESSEN_MIN:
        raise Fehler(_t("Sag genauer, was ich vergessen soll.", "Tell me more precisely what to forget."))
    with _gesperrt(daten):
        g = laden(daten)
        treffer = [e for e in g["eintraege"] if sichtbar(e, person) and t in e["text"].lower()]
        if len(treffer) > VERGESSEN_MAX:
            raise Fehler(_t("Das passt auf %d Einträge. Sag es genauer, oder lass dir die Liste geben.",
                            "That matches %d entries. Be more specific, or ask for the list.") % len(treffer))
        frei = [e for e in treffer if bearbeitbar(e, person, haupt)]
        if treffer and not frei:
            raise Fehler(_t("Das steht für alle im Haus im Gedächtnis und stammt nicht von dir. Löschen dürfen es nur, "
                            "wer es gemerkt hat, und die Hauptperson.",
                            "That is in the memory for everyone in the house and was not saved by you. Only the person "
                            "who saved it and the main person may delete it."))
        if frei:
            weg = {e["id"] for e in frei}
            g["eintraege"] = [e for e in g["eintraege"] if e["id"] not in weg]
            _speichern(daten, g)
        return len(frei), len(treffer) - len(frei)


# ------------------------------------------------------------------ Nutzung (seit 0.6)
def nutzung_laden(daten):
    try:
        n = json.load(open(os.path.join(daten, NUTZUNG), encoding="utf-8"))
        if isinstance(n, dict) and isinstance(n.get("eintraege"), dict):
            return n
    except (OSError, ValueError):
        pass
    return {"version": 1, "eintraege": {}}


def genutzt(daten, ids, jetzt=None):
    """Eintraege als gebraucht vermerken (siehe Modulkopf). Ein Schreibvorgang unter der Gedaechtnis-Sperre, atomar, nur wenn
    sich etwas aendert; je Eintrag hoechstens eine Zaehlung je NUTZUNG_ABSTAND_MIN. Unbekannte Nummern werden ignoriert und
    beim Schreiben aus der Datei geraeumt (geloeschte Eintraege). Gibt die Zahl der gezaehlten Eintraege zurueck."""
    ids = {i for i in (ids or []) if isinstance(i, int) and not isinstance(i, bool)}
    if not ids:
        return 0
    jetzt = jetzt or dt.datetime.now()
    with _gesperrt(daten):
        g = laden(daten)
        da = {e["id"] for e in g["eintraege"]}
        nz = nutzung_laden(daten)
        gezaehlt = 0
        for i in sorted(ids & da):
            r = nz["eintraege"].get(str(i)) or {"n": 0}
            z = _zeit(r.get("zuletzt"))
            if z and (jetzt - z) < dt.timedelta(minutes=NUTZUNG_ABSTAND_MIN):
                continue
            nz["eintraege"][str(i)] = {"zuletzt": jetzt.strftime("%d.%m.%Y %H:%M"), "n": int(r.get("n", 0)) + 1}
            gezaehlt += 1
        if gezaehlt:
            nz["eintraege"] = {k: v for k, v in nz["eintraege"].items() if k.isdigit() and int(k) in da}
            pfad = os.path.join(daten, NUTZUNG)
            fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(nz, f, ensure_ascii=False)
            _ersetzen_atomar(pfad + ".neu", pfad)
        return gezaehlt


def _inhaltswoerter(text, ausser=()):
    return {w[:6] for w in WORT.findall(str(text).lower()) if w not in STOPP and not any(w.startswith(a) for a in ausser)}


def verwendet(eintraege, antwort, ausser=()):
    """Ids der Eintraege, die die Antwort erkennbar aufgreift: mindestens zwei Inhaltswoerter des Eintrags (je sechs Zeichen
    Wortanfang, damit Beugung nicht stoert) stehen in der Antwort, bei Eintraegen mit nur einem Inhaltswort dieses eine.
    Namen (ausser) zaehlen nicht, sie stehen in fast jeder Antwort. Eine Heuristik ohne KI: Sie sieht Woerter, nicht Sinn."""
    a = _inhaltswoerter(str(antwort)[:4000], ausser)
    if not a:
        return []
    treffer = []
    for e in eintraege:
        w = _inhaltswoerter(e["text"], ausser)
        if w and len(w & a) >= min(2, len(w)):
            treffer.append(e["id"])
    return treffer


def genutzt_aus_antwort(daten, person, antwort, namen=None, jetzt=None):
    """Nach einer Antwort: gebrauchte Eintraege der Person (Haus und Eigenes) vermerken. Liest nur, schreibt nur bei Treffern."""
    ausser = {w for n in (namen or {}).values() for w in re.findall(r"[a-zäöüß]{3,}", str(n).lower())}
    ids = verwendet(fuer_person(daten, person), antwort, ausser)
    return genutzt(daten, ids, jetzt) if ids else 0


# ------------------------------------------------------------------ Sternbild (seit 0.6)
# Ansicht "Gedaechtnis" in App und PC-Fenster: jeder sichtbare Eintrag ist ein Stern, Themen werden ohne KI aus dem
# Text abgeleitet (Stichwortliste, danach Woerter, die in mindestens zwei Eintraegen vorkommen). Alles hier arbeitet
# nur auf fuer_person(): was die Person nicht sehen darf, kommt nie in die Themenbildung oder in die Antwort.
# Stichwoerter sind Wortanfaenge (kleingeschrieben), je Sprache eine eigene Liste: deutsche Kurzstaemme wie "abo" oder
# "bad" trafen sonst englische Woerter ("about", "bad"). Es gilt die Liste der eingestellten Sprache (SPRACHE). Kurze
# Stichwoerter (bis drei Zeichen) zaehlen nur am Wortanfang, mit Leerzeichen dahinter nur als ganzes Wort ("son " trifft
# nicht "sonntag"); ein Leerzeichen davor verlangt auch bei laengeren den Wortanfang (" band" nicht in "husband").
# Die Listen sind bewusst allgemein gehalten; eigene Geraete- oder Markennamen lassen sich ergaenzen.
STERNE_MAX = 600
THEMEN = (     # (Name deutsch = Schluessel, Name englisch, Stichwoerter deutsch, Stichwoerter englisch)
    ("Essen & Trinken", "Food & Drink",
     ("essen", "koch", "rezept", "pizza", "pasta", "kuchen", "frühstück", "abendbrot", "mittag", "vegetar", "gericht",
      "trink", "kaffee", "tee ", "milch", "brot", "schokol", "eis ", "obst", "gemüse", "lecker", "schmeckt", "snack",
      "bier", "wein"),
     ("food", "cook", "recipe", "pizza", "pasta", "cake", "breakfast", "lunch", "dinner", "vegetarian", "vegan", "dish",
      "drink", "coffee", "tea ", "milk", "bread", "chocolate", "ice cream", "fruit", "vegetable", "tasty", "delicious",
      "snack", "beer", "wine", "eat ")),
    ("Musik & Medien", "Music & Media",
     ("musik", "lied", "song", "spotify", "radio", "album", "band", "film", "serie", "netflix", "plex", "jellyfin",
      "hörspiel", "podcast", "verstärker", "lautsprecher", "fernseh", "tv", "kino", "playlist", "youtube"),
     ("music", "song", "spotify", "radio", "album", " band", "film", "movie", "series", "netflix", "plex", "jellyfin",
      "audiobook", "podcast", "receiver", "speaker", "tv", "cinema", "playlist", "youtube")),
    ("Haus & Geräte", "Home & Devices",
     ("licht", "lampe", "heizung", "thermostat", "wohnzimmer", "schlafzimmer", "küche", "keller", "bad", "flur", "garten",
      "waschmaschine", "trockner", "saug", "steckdose", "fenster", "tür", "rollo", "strom", "kessel", "wärme", "zimmer",
      "gerät", "haus", "spülmaschine", "geschirr"),
     ("light", "lamp", "heating", "thermostat", "living room", "bedroom", "kitchen", "basement", "bathroom", "hallway",
      "garden", "washing machine", "dryer", "vacuum", "socket", "window", "door", "blinds", " power", "boiler", "device",
      "house", "dishwasher")),
    ("Familie & Freunde", "Family & Friends",
     ("kind", "tochter", "sohn", "oma", "opa", "mama", "papa", "bruder", "schwester", "freund", "geburtstag", "familie",
      "hochzeit", "tante", "onkel", "besuch"),
     ("child", "kids", "daughter", "son ", "grandma", "grandpa", "mom ", "dad ", "brother", "sister", "friend",
      "birthday", "family", "wedding", "aunt", "uncle", "visit")),
    ("Termine & Alltag", "Appointments & Everyday",
     ("termin", "erinnerung", "urlaub", "ferien", "schule", "kita", "müll", "tonne", "wochenende", "wecker", "schicht",
      "arbeit", "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag", "morgens", "abends",
      "uhr"),
     ("appointment", "reminder", "vacation", "holiday", "school", "daycare", "trash", "garbage", "bin ", "weekend",
      "alarm", "shift", " work", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "morning",
      "evening", "o'clock")),
    ("Auto & Unterwegs", "Car & Travel",
     ("auto", "reifen", "tüv", "werkstatt", "tanken", "bahn", "zug", "fahrrad", "route", "navi", "fahren", "stau",
      "flug", "reise"),
     ("car ", "cars", "tire", "tyre", "garage", "fuel", "petrol", "train ", "bike", "bicycle", "route", " drive",
      "traffic", "flight", "travel", " trip")),
    ("Technik & Homelab", "Tech & Homelab",
     ("nas", "server", "docker", "home assistant", "handy", "pc", "laptop", "router", "netzwerk", "homelab", "backup",
      "update", "wlan", "app", "software", "computer", "drucker"),
     ("nas", "server", "docker", "home assistant", "phone", "pc", "laptop", "router", "network", "homelab", "backup",
      "update", "wifi", "wi-fi", "app", "software", "computer", "printer")),
    ("Einkauf & Geld", "Shopping & Money",
     ("einkauf", "kaufen", "gekauft", "bestell", "preis", "euro", "€", "abo", "rechnung", "versicherung", "konto",
      "spar", "bezahl", "kosten"),
     ("shopping", "buy", "bought", " order", "price", "euro", "dollar", "€", "subscription", "invoice", "bill ",
      "insurance", "bank account", "saving", "pay", "cost")),
    ("Gesundheit & Sport", "Health & Sport",
     ("arzt", "ärzt", "medik", "allerg", "sport", "laufen", "schlaf", "gewicht", "training", "yoga", "gesund"),
     ("doctor", "medic", "allerg", "sport", "running", "sleep", "weight", "training", "gym", "yoga", "health",
      "fitness")),
    ("Vorlieben", "Preferences",
     ("mag ", "mögen", "liebt", "lieblings", "hasst", "bevorzugt", "gewohn", "möchte", "will ", "gern"),
     ("likes", "loves", "favorite", "favourite", "hates", "prefer", "habit", "would like", "wants", "enjoys")),
)
THEMA_GEWICHT = {"Vorlieben": 0.5, "Termine & Alltag": 0.6}   # Zeitworte allein sind schwache Hinweise
THEMA_SONST = "Sonstiges"
THEMA_SONST_EN = "Other"
_THEMA_EN = {t[0]: t[1] for t in THEMEN}
STOPP = frozenset("""
aber alle allem allen aller alles also auch dass dein deine denn dies diese diesem diesen dieser dieses doch dort durch
eine einem einen einer eines einmal erst etwas euch fuer gegen habe haben hatte hier ihre ihrem ihren immer jarvis
jetzt kann kein keine mein meine mich mehr muss nach nicht noch nur oder sehr sein seine sind soll sollen sonst
über unter viel vom von wann warum weil wenn werden wieder wird wurde wuerde würde zum zur zwischen
about after again always another because before being could every never other should still their there these those
today under until where which while would really maybe often usually something things
""".split())
WORT = re.compile(r"[a-zäöüß]{5,}")


def _thema_name(thema):
    """Anzeigename eines Themas in der eingestellten Sprache (die Liste fuehrt die deutschen Namen als Schluessel)."""
    if SPRACHE != "en":
        return thema
    return THEMA_SONST_EN if thema == THEMA_SONST else _THEMA_EN.get(thema, thema)


def _thema_stichwort(text):
    """Deutscher Themen-Schluessel mit den meisten Stichwort-Treffern (Liste der eingestellten Sprache), sonst None."""
    t = " " + text.lower() + " "
    best, punkte = None, 0.0
    for name, _en, stamm_de, stamm_en in THEMEN:
        stamm = stamm_en if SPRACHE == "en" else stamm_de
        n = sum(1 for s in stamm if ((" " + s) in t if len(s.strip()) <= 3 and s != "€" else s in t))
        n *= THEMA_GEWICHT.get(name, 1)
        if n > punkte:
            best, punkte = name, n
    return best


def themen_ableiten(eintraege):
    """{id: Thema} nur aus den uebergebenen (also sichtbaren) Eintraegen: Stichwortliste, sonst ein Wort, das in
    mindestens zwei Eintraegen vorkommt (das haeufigste, bei Gleichstand das alphabetisch erste), sonst Sonstiges.
    Die Themennamen kommen in der eingestellten Sprache (SPRACHE)."""
    ergebnis, rest = {}, []
    for e in eintraege:
        t = _thema_stichwort(e["text"])
        if t:
            ergebnis[e["id"]] = _thema_name(t)
        else:
            rest.append(e)
    woerter = {e["id"]: set(w for w in WORT.findall(e["text"].lower()) if w not in STOPP) for e in rest}
    haeufig = {}
    for ws in woerter.values():
        for w in ws:
            haeufig[w] = haeufig.get(w, 0) + 1
    for e in rest:
        gute = [(-haeufig[w], w) for w in woerter[e["id"]] if haeufig[w] >= 2]
        ergebnis[e["id"]] = min(gute)[1].capitalize() if gute else _thema_name(THEMA_SONST)
    return ergebnis


def _zeit(datum):
    try:
        return dt.datetime.strptime(datum, "%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        try:
            return dt.datetime.strptime(datum, "%d.%m.%Y")
        except (TypeError, ValueError):
            return None


QUELLEN_NAMEN = {"merken": "gemerkt", "gelernt": "nachts gelernt", "import": "per Liste", "uebernommen": "übernommen",
                 "app": "in der App geändert"}
QUELLEN_NAMEN_EN = {"merken": "saved", "gelernt": "learned overnight", "import": "via the list",
                    "uebernommen": "carried over", "app": "changed in the app"}


def sternbild(daten, person, namen, darf_aendern=True, darf_loeschen=True, jetzt=None, haupt=None):
    """Daten fuer die Sternbild-Ansicht der Person (nur Haus und Eigenes). Helligkeit "hell" 0.3-1.0 nach dem juengsten von
    Aenderungsdatum und letzter Nutzung (siehe Modulkopf), dazu ein kleiner Zuschlag fuer oft Gebrauchtes (bis +0.1).
    Die Flags aendern/loeschen sagen, ob die Person diesen Stern bearbeiten darf: Recht an sich (darf_*) und bearbeitbar().
    Maximal STERNE_MAX, die neuesten."""
    jetzt = jetzt or dt.datetime.now()
    alle = fuer_person(daten, person)
    eintraege = alle[-STERNE_MAX:]
    nutzung = nutzung_laden(daten)["eintraege"]
    thema = themen_ableiten(eintraege)
    quellen = QUELLEN_NAMEN_EN if SPRACHE == "en" else QUELLEN_NAMEN
    sonst = _thema_name(THEMA_SONST)
    sterne = []
    for e in eintraege:
        z = _zeit(e.get("datum"))
        tage = max(0, (jetzt - z).days) if z else 9999
        nu = nutzung.get(str(e["id"])) or {}
        zn = _zeit(nu.get("zuletzt"))
        tage_n = max(0, (jetzt - zn).days) if zn else None
        ref = min(tage, tage_n) if tage_n is not None else tage
        n = int(nu.get("n", 0) or 0)
        von = e.get("autor") or e.get("von")             # gezeigt wird der Urheber
        frei = bearbeitbar(e, person, haupt)
        sterne.append({
            "id": e["id"], "text": e["text"], "datum": e.get("datum", ""), "tage": min(tage, 9999),
            "genutzt": nu.get("zuletzt", "") if zn else "", "tage_genutzt": tage_n, "nutzung": n,
            "hell": round(min(1.0, (0.3 + 0.7 * (2.718281828 ** (-ref / 60.0)) if ref < 9999 else 0.3) + min(0.1, 0.025 * n)), 3),
            "quelle": e.get("quelle", ""), "quelle_text": quellen.get(e.get("quelle"), e.get("quelle", "")),
            "bereich": "haus" if e["bereich"] == "haus" else "privat", "thema": thema[e["id"]],
            "von": namen.get(von, von) if e["bereich"] == "haus" and von and von != person else "",
            "von_haupt": bool(haupt is not None and von == haupt and e["bereich"] == "haus"),
            "frueher": [{"text": f.get("text", ""), "datum": f.get("datum", "")} for f in (e.get("frueher") or [])][-3:],
            "aendern": bool(darf_aendern and frei), "loeschen": bool(darf_loeschen and frei)})
    groessen = {}
    for s in sterne:
        groessen[s["thema"]] = groessen.get(s["thema"], 0) + 1
    themen = sorted(groessen.items(), key=lambda x: (x[0] == sonst, -x[1], x[0]))
    return {"person": namen.get(person, person), "sterne": sterne, "themen": [{"name": n, "anzahl": a} for n, a in themen],
            "gesamt": len(alle), "haus": sum(1 for s in sterne if s["bereich"] == "haus"),
            "privat": sum(1 for s in sterne if s["bereich"] == "privat"), "jetzt": jetzt.strftime("%d.%m.%Y %H:%M")}


def vergessen_nr(daten, person, nr, haupt=None):
    """Genau einen sichtbaren Eintrag nach Nummer entfernen (Sternbild). True, wenn er da war. Fremde und unbekannte
    Nummern aendern nichts."""
    with _gesperrt(daten):
        g = laden(daten)
        e = next((x for x in g["eintraege"] if x["id"] == nr and bearbeitbar(x, person, haupt)), None)
        if not e:
            return False
        g["eintraege"] = [x for x in g["eintraege"] if x is not e]
        _speichern(daten, g)
        return True


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


def import_vergleich(daten, person, txt, namen, haupt=None):
    """Was die zurueckgeschickte Liste aendern wuerde. Nur Eintraege, die die Person sieht; fremde Nummern zaehlen
    als unbekannt und werden nicht angefasst. Seit 0.6 landen Aenderungen und Loeschungen an Eintraegen, die die Person
    nicht aendern darf (bearbeitbar), unter "gesperrt"."""
    vorhanden = {e["id"]: e for e in fuer_person(daten, person)}
    gesehen, geaendert, neu_, unbekannt, gesperrt = set(), [], [], [], []
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
            if (text != e["text"] or bereich != e["bereich"]) and not bearbeitbar(e, person, haupt):
                gesperrt.append(nr)             # seit 0.6: fremde Haus-Eintraege bleiben, wie sie sind
            elif text != e["text"] or bereich != e["bereich"]:
                geaendert.append({"id": nr, "alt": e["text"], "neu": text, "bereich_alt": e["bereich"],
                                  "bereich": bereich})
            continue
        m = NEU.match(z)
        if m and _sauber(m.group(1)):
            neu_.append({"bereich": bereich, "text": _sauber(m.group(1))})
    geloescht = [{"id": nr, "text": e["text"]} for nr, e in vorhanden.items() if nr not in gesehen]
    gesperrt += [x["id"] for x in geloescht if not bearbeitbar(vorhanden[x["id"]], person, haupt)]
    geloescht = [x for x in geloescht if bearbeitbar(vorhanden[x["id"]], person, haupt)]
    return {"geaendert": geaendert, "geloescht": geloescht, "neu": neu_, "unbekannt": unbekannt,
            "gesperrt": sorted(set(gesperrt))}


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
    if v.get("gesperrt"):
        zeilen.append(_t("nicht angefasst (Haus-Einträge, die nicht von dir sind; ändern oder löschen dürfen nur, wer sie "
                         "gemerkt hat, und die Hauptperson): %s",
                         "left untouched (house entries that are not yours; only the person who saved them and the main "
                         "person may change or delete them): %s") % ", ".join(map(str, v["gesperrt"])))
    return "\n".join(zeilen) or _t("Keine Änderungen.", "No changes.")


def import_uebernehmen(daten, person, v, haupt=None):
    """Aenderungen aus import_vergleich anwenden; (geaendert, geloescht, neu, uebersprungen). Ein Eintrag, der sich
    seit der Ausgabe geaendert hat (etwa nachts gelernt), wird weder ueberschrieben noch geloescht, sondern
    uebersprungen; ebenso neue Eintraege, wenn das Gedaechtnis voll ist. Seit 0.6 nur, was die Person aendern darf
    (bearbeitbar): auch ein gefaelschter Vergleich aendert keine fremden Haus-Eintraege."""
    with _gesperrt(daten):
        g = laden(daten)
        nach_id = {e["id"]: e for e in g["eintraege"] if bearbeitbar(e, person, haupt)}
        a = l_ = n_ = ueber = 0
        for x in v.get("geaendert", []):
            e = nach_id.get(x["id"])
            if not e or x["bereich"] not in ("haus", person):
                continue
            if e["text"] != x.get("alt") or e["bereich"] != x.get("bereich_alt"):
                ueber += 1
                continue
            e.setdefault("autor", e.get("von"))
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
                                       "datum": _jetzt(), "quelle": "import", "von": person, "autor": person})
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
                                   "datum": datum, "quelle": "uebernommen", "von": standard, "autor": standard})
            g["naechste"] += 1
            n += 1
        _speichern(daten, g)
        return n
