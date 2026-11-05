"""Offene Faeden (seit 0.6, "Jarvis fasst nach").

Was im Gespraech offen geblieben ist ("Ich ruf morgen beim Handwerker an", "Bestell das spaeter", "Sag Bescheid, wenn
die Bahn wieder faehrt", eine Frage, die Jarvis nicht beantworten konnte), als Liste je Person. Jarvis fragt zum
passenden Zeitpunkt nach und hakt ab, wenn es erledigt ist.

Woher die Faeden kommen:
- ausdruecklich per Werkzeug offene_faeden, wenn die Person es sagt (quelle "werkzeug")
- wer eine naechtliche Lern-Auswertung des Verlaufs hat: dort im selben Claude-Aufruf, nur aus den eigenen Worten der
  Person (quelle "gelernt")

Nachfassen (Regeln hier, Wege in der Bruecke): im naechsten passenden Gespraech (App, Web-App, PC; nie ueber Echos,
Voice PE oder die HA-Sprachkette, dort kann jeder mithoeren, erst mit Stimmerkennung) und im Briefing, oder, nur wenn
die Person es will, einmal am Tag per Push (Standard aus, 18 Uhr). Nie in der Nachtruhe. Hoechstens ein
Nachfassen je Faden und Tag, hoechstens je_tag Faeden je Person und Tag (Standard 1, per Zuruf 1-3).
Ein Faden verfaellt verfall_tage nach seiner Faelligkeit (Standard 14, je Person einstellbar). Vorher fragt Jarvis
einmal abschliessend "Soll ich ... fallen lassen?" (Phase "abschluss", ab ABSCHLUSS_VORLAUF Tage vor dem Verfall oder
nach NACHFRAGEN_MAX Nachfragen). Ja (Knopf oder Antwort) verwirft ihn, "noch wichtig" verschiebt ihn, sonst verfaellt
er zur Frist.

daten/faeden.json (600): {"version": 1, "naechste": n, "faeden": [
    {"id": 3, "person": "mia", "text": "Handwerker wegen der Heizung anrufen", "art": "vorhaben"|"warten"|"frage",
     "faellig": "JJJJ-MM-TT", "angelegt": "JJJJ-MM-TT HH:MM", "quelle": "gelernt"|"werkzeug", "status": "offen"|
     "erledigt"|"verworfen"|"verfallen", "gefragt": ["JJJJ-MM-TT", ...], "angeboten": {"datum": "...", "n": 1},
     "geschlossen": "JJJJ-MM-TT HH:MM"}],
 "einstellungen": {"<person>": {"nachfassen": "an", "push": "aus", "push_stunde": 18, "verfall_tage": 14,
                                "push_tag": "JJJJ-MM-TT"}}}
Mehrere Prozesse schreiben (Bruecke, Werkzeug-Server, naechtliches Lernen): jede Aenderung unter einer Dateisperre,
geschrieben wird atomar. Nur Python-Standardbibliothek (NAS-Python 3.8).
"""
import contextlib
import datetime as dt
import json
import os
import re

DATEI = "faeden.json"
SPERRE = "faeden.lock"
TEXT_MAX = 200
OFFEN_MAX = 30                 # je Person; darueber nimmt Jarvis keine neuen an, bis etwas erledigt ist
NACHFRAGEN_MAX = 3             # danach nur noch die abschliessende Frage, dann ruht der Faden bis zum Verfall
ABSCHLUSS_VORLAUF = 3          # so viele Tage vor dem Verfall kommt die abschliessende Frage
ANGEBOTEN_MAX = 3              # so oft am Tag bekommt das Gehirn einen Faden angeboten, ohne dass es nachfragt
AUFHEBEN_TAGE = 60             # geschlossene Faeden so lange behalten (fuer "was war noch offen?"), dann weg
ARTEN = ("vorhaben", "warten", "frage")
# Standard fuer alle (auch Familie): Nachfassen an, 1 Faden je Tag, Push aus (18 Uhr, wenn eingeschaltet)
STANDARD = {"nachfassen": "an", "je_tag": 1, "push": "aus", "push_stunde": 18, "verfall_tage": 14}
GRENZEN = {"je_tag": (1, 3), "push_stunde": (6, 22), "verfall_tage": (1, 90)}
# Ueber diese Quellen kann jeder im Haus mitreden oder mithoeren: kein Nachfassen, kein Werkzeug, nichts im Briefing.
OFFEN_SPRACHE = ("alexa", "test-alexa", "ha", "test-ha", "voice", "voice-pe")
MONATE_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


# Sprache der Texte, die die Person direkt sieht (seit 0.6 im Release). Die Bruecke setzt sie beim Start aus
# der Einrichtung (antworten.json "sprache"), wie bei verhalten.py und szenen.py. Auch der Ja-Knopf folgt ihr: Die
# Bruecke vergleicht die Antwort mit dem Knopftext, den sie selbst ausgegeben hat.
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


def _tag_kurz(d):
    """Datum in Texten: 03.11. bzw. 3 Nov (ohne Locale)."""
    return "%d %s" % (d.day, MONATE_EN[d.month - 1]) if SPRACHE == "en" else d.strftime("%d.%m.")


def quelle_gesperrt(quelle):
    q = str(quelle or "").lower()
    return q in OFFEN_SPRACHE or q.startswith(("alexa", "ha-", "voice"))


class Fehler(Exception):
    pass


def _tag(jetzt):
    return jetzt.strftime("%Y-%m-%d")


def _sauber(text):
    t = re.sub(r"⟦[^⟦⟧]*⟧", " ", str(text or ""))                    # keine Marken (⟦faden: …⟧) im Text
    t = re.sub(r"[\x00-\x1f\x7f⟦⟧]+", " ", t).strip()
    return re.sub(r"\s{2,}", " ", t)[:TEXT_MAX]


def _datum(s):
    try:
        return dt.datetime.strptime(str(s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@contextlib.contextmanager
def _gesperrt(daten):
    os.makedirs(daten, exist_ok=True)
    fd = os.open(os.path.join(daten, SPERRE), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        except ImportError:          # Windows: ohne Sperre (schreiben Bruecke und Werkzeug-Server im selben Moment,
            pass                     # kann eine der beiden Aenderungen verloren gehen)
        yield
    finally:
        os.close(fd)


def laden(daten):
    try:
        d = json.load(open(os.path.join(daten, DATEI), encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("faeden"), list):
            d.setdefault("naechste", 1 + max([f.get("id", 0) for f in d["faeden"]] or [0]))
            d.setdefault("einstellungen", {})
            return d
    except (OSError, ValueError):
        pass
    return {"version": 1, "naechste": 1, "faeden": [], "einstellungen": {}}


def _speichern(daten, d):
    pfad = os.path.join(daten, DATEI)
    fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(pfad + ".neu", pfad)


# ---------------------------------------------------------------- Einstellungen je Person

def einstellungen(daten, person, d=None):
    e = dict(STANDARD)
    e.update(((d or laden(daten))["einstellungen"].get(person) or {}))
    return e


def einstellen(daten, person, **aenderung):
    """nachfassen an/aus, je_tag 1-3, push an/aus, push_stunde 6-22, verfall_tage 1-90. Sonst Fehler."""
    neu = {}
    for k, v in aenderung.items():
        if v is None:
            continue
        if k in ("nachfassen", "push"):
            v = {"ja": "an", "true": "an", "ein": "an", "nein": "aus", "false": "aus"}.get(str(v).lower(), str(v).lower())
            if v not in ("an", "aus"):
                raise Fehler(_t("%s ist an oder aus.", "%s is an (on) or aus (off).") % k)
        elif k in GRENZEN:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise Fehler(_t("%s ist eine ganze Zahl.", "%s is a whole number.") % k)
            a, b = GRENZEN[k]
            if not a <= v <= b:
                raise Fehler(_t("%s geht von %d bis %d.", "%s goes from %d to %d.") % (k, a, b))
        else:
            raise Fehler(_t("Unbekannte Einstellung %s. Möglich: %s.", "Unknown setting %s. Possible: %s.")
                         % (k, ", ".join(STANDARD)))
        neu[k] = v
    if not neu:
        raise Fehler(_t("Keine Änderung angegeben.", "No change given."))
    with _gesperrt(daten):
        d = laden(daten)
        d["einstellungen"].setdefault(person, {}).update(neu)
        _speichern(daten, d)
        return einstellungen(daten, person, d)


# ---------------------------------------------------------------- Faeden

def _verfall(f, e):
    """Datum, ab dem ein offener Faden verfaellt: verfall_tage nach der Faelligkeit (ohne Faelligkeit: nach Anlage)."""
    basis = _datum(f.get("faellig")) or _datum(f.get("angelegt")) or dt.date.today()
    return basis + dt.timedelta(days=int(e["verfall_tage"]))


def _ist_offen(f, e, heute):
    return f.get("status") == "offen" and heute <= _verfall(f, e)


def _aehnlich(a, b):
    a, b = a.lower().strip(" ."), b.lower().strip(" .")
    return a == b or (len(a) > 12 and len(b) > 12 and (a in b or b in a))


def neu(daten, person, text, faellig=None, art="vorhaben", quelle="werkzeug", jetzt=None):
    """Neuer Faden; gibt die Nummer zurueck, 0 wenn leer oder schon (aehnlich) offen. Ohne Faelligkeit fasst Jarvis
    am naechsten Tag nach. Zu viele offene: Fehler."""
    jetzt = jetzt or dt.datetime.now()
    text = _sauber(text)
    if len(text) < 4:
        return 0
    art = art if art in ARTEN else "vorhaben"
    tag = _datum(faellig)
    if not tag or tag < jetzt.date():
        tag = jetzt.date() + dt.timedelta(days=1)
    with _gesperrt(daten):
        d = laden(daten)
        e = einstellungen(daten, person, d)
        offen = [f for f in d["faeden"] if f.get("person") == person and _ist_offen(f, e, jetzt.date())]
        if any(_aehnlich(f["text"], text) for f in offen):
            return 0
        if len(offen) >= OFFEN_MAX:
            raise Fehler(_t("Schon %d offene Fäden. Hak erst ein paar ab.",
                            "Already %d open threads. Tick a few off first.") % OFFEN_MAX)
        n = d["naechste"]
        d["naechste"] = n + 1
        d["faeden"].append({"id": n, "person": person, "text": text, "art": art, "faellig": tag.isoformat(),
                            "angelegt": jetzt.strftime("%Y-%m-%d %H:%M"), "quelle": quelle, "status": "offen",
                            "gefragt": []})
        _speichern(daten, d)
        return n


def offen(daten, person, jetzt=None):
    """Offene Faeden der Person (Verfallene zaehlen nicht mehr), nach Faelligkeit."""
    jetzt = jetzt or dt.datetime.now()
    d = laden(daten)
    e = einstellungen(daten, person, d)
    return sorted([f for f in d["faeden"] if f.get("person") == person and _ist_offen(f, e, jetzt.date())],
                  key=lambda f: (f.get("faellig") or "", f["id"]))


def alle(daten, person):
    return [f for f in laden(daten)["faeden"] if f.get("person") == person]


def finden(liste, wer):
    """Faden aus einer Liste: Nummer (12, "12", "Nr. 12") oder eindeutiges Stichwort. None, wenn nicht eindeutig."""
    s = str(wer if wer is not None else "").strip()
    m = re.fullmatch(r"(?:nr\.?\s*|#)?(\d{1,6})", s, re.I)
    if m:
        return next((f for f in liste if f["id"] == int(m.group(1))), None)
    s = s.lower()
    if len(s) < 3:
        return None
    treffer = [f for f in liste if s in f["text"].lower()]
    return treffer[0] if len(treffer) == 1 else None


def schliessen(daten, person, wer, status="erledigt", jetzt=None):
    """Einen offenen Faden der Person abhaken (erledigt) oder verwerfen; gibt den Faden zurueck oder None."""
    if status not in ("erledigt", "verworfen"):
        raise Fehler(_t("status ist erledigt oder verworfen.", "status is erledigt (done) or verworfen (dropped)."))
    jetzt = jetzt or dt.datetime.now()
    with _gesperrt(daten):
        d = laden(daten)
        e = einstellungen(daten, person, d)
        f = finden([f for f in d["faeden"] if f.get("person") == person and _ist_offen(f, e, jetzt.date())], wer)
        if not f:
            return None
        f.update(status=status, geschlossen=jetzt.strftime("%Y-%m-%d %H:%M"))
        _speichern(daten, d)
        return dict(f)


def pflegen(daten, jetzt=None):
    """Verfallene als verfallen markieren, lange Geschlossene entfernen. (verfallen, entfernt)."""
    jetzt = jetzt or dt.datetime.now()
    grenze = (jetzt - dt.timedelta(days=AUFHEBEN_TAGE)).strftime("%Y-%m-%d")
    with _gesperrt(daten):
        d = laden(daten)
        v = 0
        for f in d["faeden"]:
            if f.get("status") == "offen" and jetzt.date() > _verfall(f, einstellungen(daten, f.get("person"), d)):
                f.update(status="verfallen", geschlossen=jetzt.strftime("%Y-%m-%d %H:%M"))
                v += 1
        vorher = len(d["faeden"])
        d["faeden"] = [f for f in d["faeden"] if f.get("status") == "offen" or (f.get("geschlossen") or "") >= grenze]
        weg = vorher - len(d["faeden"])
        if v or weg:
            _speichern(daten, d)
        return v, weg


# ---------------------------------------------------------------- Nachfassen

def _heute_gefragt(f, heute):
    return heute in (f.get("gefragt") or []) or f.get("abschluss_gefragt") == heute


def phase(f, e, heute):
    """"nachfassen", "abschluss" (einmal fragen, ob er fallen soll) oder None (nichts mehr fragen, wartet auf Verfall)."""
    if f.get("abschluss_gefragt"):
        return None
    spaet = heute >= _verfall(f, e) - dt.timedelta(days=ABSCHLUSS_VORLAUF)
    if spaet or len(f.get("gefragt") or []) >= NACHFRAGEN_MAX:
        return "abschluss"
    return "nachfassen"


def _faellig_fuer(d, person, jetzt):
    e = einstellungen(None, person, d)
    heute = _tag(jetzt)
    liste = [f for f in d["faeden"] if f.get("person") == person and _ist_offen(f, e, jetzt.date())]
    schon = sum(1 for f in d["faeden"] if f.get("person") == person and _heute_gefragt(f, heute))
    if schon >= e["je_tag"]:
        return []
    raus = []
    # Wer am laengsten nicht gefragt wurde, kommt zuerst (bei 1 Faden je Tag wechseln sie sich ab), dann nach Faelligkeit
    for f in sorted(liste, key=lambda f: (max(f.get("gefragt") or [""]), f.get("faellig") or "", f["id"])):
        ph = phase(f, e, jetzt.date())
        if ph and (f.get("faellig") or "") <= heute and not _heute_gefragt(f, heute):
            f["phase"], f["verfaellt"] = ph, _verfall(f, e).isoformat()     # nur fuer den Aufrufer, nie gespeichert
            raus.append(f)
    return raus[:e["je_tag"] - schon]


def _ohne_phase(d):
    for f in d["faeden"]:
        f.pop("phase", None)
        f.pop("verfaellt", None)


def zum_nachfassen(daten, person, jetzt=None, nachtruhe=False):
    """Der Faden, den das Gehirn bei dieser Frage anbieten darf, oder None. Zaehlt das Angebot (hoechstens
    ANGEBOTEN_MAX am Tag, damit ein Faden, zu dem es nie passt, nicht jede Frage begleitet)."""
    if nachtruhe:
        return None
    jetzt = jetzt or dt.datetime.now()
    heute = _tag(jetzt)
    with _gesperrt(daten):
        d = laden(daten)
        if einstellungen(daten, person, d)["nachfassen"] != "an":
            return None
        for f in _faellig_fuer(d, person, jetzt):
            a = f.get("angeboten") or {}
            n = a.get("n", 0) if a.get("datum") == heute else 0
            if n >= ANGEBOTEN_MAX:
                continue
            f["angeboten"] = {"datum": heute, "n": n + 1}
            kopie = dict(f)
            _ohne_phase(d)
            _speichern(daten, d)
            return kopie
    return None


def _als_gefragt(f, ph, heute):
    if ph == "abschluss":
        f["abschluss_gefragt"] = heute
    else:
        f["gefragt"] = (f.get("gefragt") or []) + [heute]


def gefragt(daten, person, nr, jetzt=None, ph="nachfassen"):
    """Jarvis hat nachgefragt (Marke in der Antwort oder Push): fuer heute erledigt; bei ph "abschluss" ist die
    abschliessende Frage gestellt. False, wenn der Faden nicht der Person gehoert, nicht offen ist oder heute schon
    gefragt wurde."""
    jetzt = jetzt or dt.datetime.now()
    heute = _tag(jetzt)
    with _gesperrt(daten):
        d = laden(daten)
        e = einstellungen(daten, person, d)
        for f in d["faeden"]:
            if f["id"] == nr and f.get("person") == person and _ist_offen(f, e, jetzt.date()):
                if _heute_gefragt(f, heute):
                    return False
                _als_gefragt(f, ph, heute)
                _speichern(daten, d)
                return True
    return False


def fuer_push(daten, personen, jetzt=None, nachtruhe=False):
    """Einmal am Tag je Person mit push an, ab push_stunde, nie in der Nachtruhe: [(person, [faeden])]. Markiert die
    Faeden als gefragt und den Tag als erledigt (auch ohne faellige Faeden, damit nicht alle 30 s gelesen wird)."""
    if nachtruhe:
        return []
    jetzt = jetzt or dt.datetime.now()
    heute = _tag(jetzt)
    raus = []
    with _gesperrt(daten):
        d = laden(daten)
        geaendert = False
        for person in personen:
            e = einstellungen(daten, person, d)
            if e["push"] != "an" or e["nachfassen"] != "an" or jetzt.hour < e["push_stunde"] or e.get("push_tag") == heute:
                continue
            d["einstellungen"].setdefault(person, {})["push_tag"] = heute
            geaendert = True
            liste = _faellig_fuer(d, person, jetzt)
            for f in liste:
                _als_gefragt(f, f["phase"], heute)
            if liste:
                raus.append((person, [dict(f) for f in liste]))
        _ohne_phase(d)
        if geaendert:
            _speichern(daten, d)
    return raus


# ---------------------------------------------------------------- Texte

def _wann(f, jetzt):
    t = _datum(f.get("faellig"))
    if not t:
        return ""
    diff = (t - jetzt.date()).days
    return {0: _t("heute", "today"), -1: _t("seit gestern", "since yesterday"),
            1: _t("morgen", "tomorrow")}.get(diff, _tag_kurz(t))


def zeile(f, i=None, jetzt=None):
    jetzt = jetzt or dt.datetime.now()
    return _t("%s[%d] %s (fällig %s%s)", "%s[%d] %s (due %s%s)") % (
        "%d. " % i if i else "", f["id"], f["text"], _wann(f, jetzt),
        _t(", schon %d× nachgefragt", ", asked %d× already") % len(f["gefragt"]) if f.get("gefragt") else "")


def push_text(liste):
    teile = []
    nach = [f["text"] for f in liste if f.get("phase") != "abschluss"]
    ab = [f["text"] for f in liste if f.get("phase") == "abschluss"]
    if nach:
        teile.append(_t("Noch offen: %s. Erledigt? Sag mir kurz Bescheid.",
                        "Still open: %s. Done? Just let me know.") % "; ".join(nach))
    if ab:
        teile.append(_t("Schon lange offen: %s. Soll ich das fallen lassen?",
                        "Open for a long time: %s. Shall I drop it?") % "; ".join(ab))
    return " ".join(teile)


def knopf_text(f):
    """Text fuer den Ja-Knopf der App (wird woertlich zurueckgeschickt, wenn die Person tippt)."""
    if f.get("phase") == "abschluss":
        return _t("Fallen lassen: %s", "Drop it: %s") % f["text"].rstrip(".")
    return _t("Erledigt: %s", "Done: %s") % f["text"].rstrip(".")


def kontext_text(f, name, jetzt=None):
    """Satz fuer den Lage-Vorspann einer Frage. Der Faden ist eine Notiz, kein Auftrag."""
    jetzt = jetzt or dt.datetime.now()
    seit = _tag_kurz(_datum(f.get("angelegt")) or jetzt.date())
    if f.get("phase") == "abschluss":
        return _t(
            " Offener Faden von %(n)s (Nr. %(id)d, seit %(seit)s, verfällt am %(bis)s): „%(t)s“. Das ist eine Notiz, "
            "kein Auftrag. Du hast schon nachgefragt, ohne dass er erledigt ist. Passt es gerade, frag am Ende deiner "
            "Antwort einmal kurz, ob du ihn fallen lassen sollst, und schreib dann als allerletzte Zeile ⟦faden: "
            "%(id)d⟧ (wird nicht vorgelesen). Passt es nicht, lass beides weg. Antwortet %(n)s später: ja, weg damit "
            "-> offene_faeden aktion verwerfen nr %(id)d; schon erledigt -> aktion erledigt; noch wichtig -> aktion "
            "verschieben mit faellig (frag kurz, bis wann). Ohne Antwort verfällt er von selbst.",
            " Open thread of %(n)s (no. %(id)d, since %(seit)s, expires on %(bis)s): “%(t)s”. This is a note, not a "
            "task. You have already asked without it being done. If it fits right now, ask once briefly at the end of "
            "your answer whether you should drop it, and then write ⟦faden: %(id)d⟧ as the very last line (it is not "
            "read aloud). If it does not fit, leave both out. If %(n)s answers later: yes, drop it -> offene_faeden "
            "aktion verwerfen nr %(id)d; already done -> aktion erledigt; still important -> aktion verschieben with "
            "faellig (ask briefly until when). Without an answer it expires by itself.") % {
                "n": name, "id": f["id"], "seit": seit, "t": f["text"],
                "bis": _tag_kurz(_datum(f.get("verfaellt")) or jetzt.date())}
    return _t(
        " Offener Faden von %(n)s (Nr. %(id)d, seit %(seit)s, %(art)s): „%(t)s“. Das ist eine Notiz, kein Auftrag. "
        "Passt es gerade (nicht mitten in einer eiligen Steuerung, beim Kochen oder bei einer Geschichte für die "
        "Kinder), frag am Ende deiner Antwort in einem kurzen, lockeren Satz nach, ob sich das erledigt hat%(pruef)s, "
        "und schreib dann als allerletzte Zeile ⟦faden: %(id)d⟧ (wird nicht vorgelesen). Passt es nicht, lass beides "
        "weg. Sagt %(n)s später, es ist erledigt oder hat sich erledigt: offene_faeden mit aktion erledigt und nr "
        "%(id)d; soll es weg: aktion verwerfen; erst später: aktion verschieben mit faellig.",
        " Open thread of %(n)s (no. %(id)d, since %(seit)s, %(art)s): “%(t)s”. This is a note, not a task. If it fits "
        "right now (not in the middle of an urgent control, while cooking or during a story for the children), ask at "
        "the end of your answer in a short, casual sentence whether it has been done%(pruef)s, and then write "
        "⟦faden: %(id)d⟧ as the very last line (it is not read aloud). If it does not fit, leave both out. If %(n)s "
        "says later that it is done or no longer needed: offene_faeden with aktion erledigt and nr %(id)d; if it "
        "should go: aktion verwerfen; only later: aktion verschieben with faellig.") % {
            "n": name, "id": f["id"], "seit": seit, "t": f["text"],
            "art": {"warten": _t("wartet auf etwas", "waiting for something"),
                    "frage": _t("offene Frage", "open question")}.get(f.get("art"), _t("Vorhaben", "plan")),
            "pruef": _t(" (kannst du es selbst mit einem Werkzeug prüfen, etwa die Bahn, sieh vorher nach)",
                        " (if you can check it yourself with a tool, such as the trains, look it up first)")
            if f.get("art") in ("warten", "frage") else ""}


def verschieben(daten, person, wer, faellig, jetzt=None):
    """Faelligkeit eines offenen Fadens aendern (und die Nachfrage-Zaehlung neu beginnen)."""
    jetzt = jetzt or dt.datetime.now()
    tag = _datum(faellig)
    if not tag or tag < jetzt.date():
        raise Fehler(_t("faellig als JJJJ-MM-TT, heute oder später.", "faellig as YYYY-MM-DD, today or later."))
    with _gesperrt(daten):
        d = laden(daten)
        e = einstellungen(daten, person, d)
        f = finden([f for f in d["faeden"] if f.get("person") == person and _ist_offen(f, e, jetzt.date())], wer)
        if not f:
            return None
        f.update(faellig=tag.isoformat(), gefragt=[])
        f.pop("abschluss_gefragt", None)
        _speichern(daten, d)
        return dict(f)


MARKE = re.compile(r"[ \t]*\n?[ \t]*⟦\s*faden\s*:\s*(\d{1,6})\s*⟧[ \t]*", re.I)


def marke_aus(antwort):
    """⟦faden: N⟧ aus Text und Stimme nehmen; (Text, [Nummern]). Die Bruecke wertet nur die angebotene Nummer."""
    s = str(antwort or "")
    nummern = [int(m.group(1)) for m in MARKE.finditer(s)]
    return (MARKE.sub("\n", s).strip() if nummern else antwort), nummern
