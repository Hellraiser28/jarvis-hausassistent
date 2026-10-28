"""Briefe und Fristen (seit 0.4): fotografierte Briefe nach Paperless (mit dem Zugang der
Person, die fragt, damit der Brief ihr gehoert), Fristen daraus mit Erinnerung, "Welche Fristen laufen?".

Paperless-API (getestet mit 3.3.4): POST /api/documents/post_document/ (multipart, liefert die Kennung der Aufgabe),
GET /api/tasks/?task_id=... (related_document, sobald verarbeitet), GET /api/documents/<id>/download/. Fristen in
daten/fristen.json (600) unter Dateisperre. Python 3.8, nur Standardbibliothek.
"""
import datetime as dt
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager

PAPERLESS = os.environ.get("PAPERLESS_ADRESSE", "http://127.0.0.1:8000").rstrip("/")  # Basis-URL
DATEI = "fristen.json"
MAX_FRISTEN = 300
VORLAUF_TAGE = 3                 # Erinnerung drei Tage vor der Frist um 9 Uhr
MAX_DATEI = 40 * 1024 * 1024


class Fehler(Exception):
    pass


def _anfrage(token, methode, pfad, daten=None, typ=None, zeit=30, roh=False):
    k = {"Authorization": "Token " + token, "Accept": "application/json"}
    if typ:
        k["Content-Type"] = typ
    r = urllib.request.Request(PAPERLESS + pfad, data=daten, headers=k, method=methode)
    try:
        with urllib.request.urlopen(r, timeout=zeit) as a:
            inhalt = a.read()
            return (inhalt, a.headers) if roh else (json.loads(inhalt) if inhalt.strip() else None)
    except urllib.error.HTTPError as e:
        raise Fehler("Paperless antwortet mit HTTP %d." % e.code)
    except (OSError, ValueError) as e:
        raise Fehler("Paperless ist nicht erreichbar (%s)." % type(e).__name__)


def _multipart(felder, datei):
    g = "jarvis" + secrets.token_hex(12)
    teile = []
    for k, v in felder:
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (g, k, v)).encode("utf-8"))
    name, mime, roh = datei
    sicher = re.sub(r"[^\w.\- ]", "_", name)[:100] or "brief"
    if not re.fullmatch(r"[a-z]{1,20}/[a-z0-9.+-]{1,60}", str(mime or "")):
        mime = "application/octet-stream"
    teile.append(("--%s\r\nContent-Disposition: form-data; name=\"document\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                  % (g, sicher, mime)).encode("utf-8") + roh + b"\r\n")
    teile.append(("--%s--\r\n" % g).encode())
    return b"".join(teile), "multipart/form-data; boundary=" + g


def hochladen(token, roh, name, mime, titel=None, korrespondent=None, dokumenttyp=None, tags=(), erstellt=None):
    """-> Kennung der Paperless-Aufgabe. Besitzer wird der Benutzer des Tokens."""
    if not roh or len(roh) > MAX_DATEI:
        raise Fehler("Die Datei ist leer oder größer als %d MB." % (MAX_DATEI // 1024 // 1024))
    felder = []
    if titel:
        felder.append(("title", str(titel)[:128]))
    if korrespondent:
        felder.append(("correspondent", int(korrespondent)))
    if dokumenttyp:
        felder.append(("document_type", int(dokumenttyp)))
    for t in tags or ():
        felder.append(("tags", int(t)))
    if erstellt:
        felder.append(("created", erstellt))
    koerper, typ = _multipart(felder, (name, mime, roh))
    a = _anfrage(token, "POST", "/api/documents/post_document/", koerper, typ, zeit=120)
    if not isinstance(a, str) or not re.fullmatch(r"[0-9a-f-]{36}", a):
        raise Fehler("Paperless hat den Brief nicht angenommen.")
    return a


def aufgabe(token, uuid):
    """-> (status, dokument_id oder None, meldung)"""
    l = _anfrage(token, "GET", "/api/tasks/?task_id=" + urllib.parse.quote(uuid)) or []
    if isinstance(l, dict):            # Paperless 3.x: Seite mit results, 2.x: Liste
        l = l.get("results") or []
    if not l:
        return "PENDING", None, ""
    t = l[0]
    # 3.x: status klein ("success"), Nummer in result_data.document_id / related_document_ids; 2.x: related_document
    erg = t.get("result_data") if isinstance(t.get("result_data"), dict) else {}
    doc = t.get("related_document") or erg.get("document_id") or (t.get("related_document_ids") or [None])[0]
    return (str(t.get("status") or "PENDING").upper(), int(doc) if str(doc or "").isdigit() else None,
            str(t.get("result") or erg.get("error") or erg or "")[:200])


def namen(token, art):
    """art: correspondents, document_types, tags -> {id: name}"""
    return {x["id"]: x["name"] for x in (_anfrage(token, "GET", "/api/%s/?page_size=1000" % art) or {}).get("results", [])}


def _n(s):
    s = str(s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def passend(liste, text):
    """Vorhandenen Eintrag zum Namen finden: genau, sonst eindeutig enthalten (in beide Richtungen, ab 4 Zeichen)."""
    t = _n(text)
    if not t:
        return None
    genau = [i for i, n in liste.items() if _n(n) == t]
    if genau:
        return genau[0]
    teil = [i for i, n in liste.items() if len(_n(n)) >= 4 and len(t) >= 4 and (t in _n(n) or _n(n) in t)]
    return teil[0] if len(teil) == 1 else None


def herunterladen(token, dok_id):
    """-> (roh, dateiname, mime) der archivierten Fassung (PDF), sonst das Original."""
    roh, kopf = _anfrage(token, "GET", "/api/documents/%d/download/" % int(dok_id), zeit=60, roh=True)
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', kopf.get("Content-Disposition") or "")
    name = urllib.parse.unquote(m.group(1)) if m else "dokument-%d.pdf" % int(dok_id)
    return roh, name, (kopf.get("Content-Type") or "application/pdf").split(";")[0]


# ---------------------------------------------------------------- Fristen
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


@contextmanager
def _gesperrt(daten):
    fd = os.open(os.path.join(daten, DATEI + ".sperre"), os.O_RDWR | os.O_CREAT, 0o600)
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
        d = json.load(open(os.path.join(daten, DATEI), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [f for f in (d.get("fristen") if isinstance(d, dict) else []) or [] if isinstance(f, dict) and f.get("id")]


def _schreiben(daten, liste):
    pfad = os.path.join(daten, DATEI)
    fd = os.open(pfad + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"fristen": liste}, f, ensure_ascii=False, indent=1)
    _ersetzen_atomar(pfad + ".neu", pfad)


def datum(s, heute=None):
    """JJJJ-MM-TT (oder TT.MM.JJJJ) -> date; nur von vor 60 Tagen bis in 3 Jahren."""
    s = str(s or "").strip()
    try:
        d = dt.datetime.strptime(s, "%d.%m.%Y").date() if "." in s else dt.date.fromisoformat(s[:10])
    except ValueError:
        raise Fehler("Datum „%s“ verstehe ich nicht (JJJJ-MM-TT)." % s)
    h = heute or dt.date.today()
    if not h - dt.timedelta(days=60) <= d <= h + dt.timedelta(days=3 * 366):
        raise Fehler("Das Datum %s liegt zu weit weg." % d.strftime("%d.%m.%Y"))
    return d


def erinnerung_wann(frist, jetzt=None):
    """Drei Tage vorher um 9 Uhr; ist das vorbei, in einer Stunde (auf volle 5 Minuten); ist die Frist vorbei, None."""
    j = jetzt or dt.datetime.now()
    if frist < j.date():
        return None
    w = dt.datetime.combine(frist - dt.timedelta(days=VORLAUF_TAGE), dt.time(9, 0))
    if w <= j:
        w = j + dt.timedelta(hours=1)
        w = w.replace(minute=w.minute - w.minute % 5, second=0, microsecond=0)
    return w


def neu(daten, person, frist, was, titel="", absender="", dokument=None, aufgabe_id="", erinnerung=""):
    e = {"id": "f" + secrets.token_hex(3), "person": person, "datum": frist.isoformat(), "was": str(was)[:160],
         "titel": str(titel or "")[:128], "absender": str(absender or "")[:80], "dokument": dokument,
         "aufgabe": aufgabe_id, "erinnerung": erinnerung, "erledigt": False,
         "angelegt": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with _gesperrt(daten):
        liste = laden(daten)
        liste.append(e)
        # Hoechstens MAX_FRISTEN: zuerst fallen erledigte weg (die aeltesten zuerst), offene nie
        while len(liste) > MAX_FRISTEN:
            alt = next((f for f in liste if f.get("erledigt")), None)
            if not alt:
                raise Fehler("Es gibt schon %d offene Fristen. Hak erst erledigte ab." % MAX_FRISTEN)
            liste.remove(alt)
        _schreiben(daten, liste)
    return e


def fuer(daten, person, alle=False, heute=None):
    """Offene Fristen der Person (bis 7 Tage ueberfaellig), nach Datum; alle=True auch erledigte und alte."""
    h = (heute or dt.date.today()) - dt.timedelta(days=7)
    l = [f for f in laden(daten) if f.get("person") == person and (alle or (not f.get("erledigt") and f["datum"] >= h.isoformat()))]
    return sorted(l, key=lambda f: f["datum"])


def dokument_nachtragen(daten, aufgabe_id, dok_id):
    with _gesperrt(daten):
        liste = laden(daten)
        for f in liste:
            if f.get("aufgabe") == aufgabe_id and not f.get("dokument"):
                f["dokument"] = dok_id
        _schreiben(daten, liste)


def erledigt(daten, person, wer):
    """wer: Kennung, Nummer aus der Liste (1, 2, ...) oder Text aus was/titel/absender. -> Eintrag oder None"""
    with _gesperrt(daten):
        liste = laden(daten)
        offen = [f for f in fuer(daten, person)]
        w = str(wer or "").strip()
        f = next((x for x in offen if x["id"] == w), None)
        if not f and w.isdigit() and 0 < int(w) <= len(offen):
            f = offen[int(w) - 1]
        if not f:
            t = [x for x in offen if _n(w) and _n(w) in _n(" ".join((x["was"], x["titel"], x["absender"])))]
            f = t[0] if len(t) == 1 else None
        if not f:
            return None
        for x in liste:
            if x["id"] == f["id"]:
                x["erledigt"] = True
                f = x
        _schreiben(daten, liste)
    return f


def zeile(f, nr=None):
    d = dt.date.fromisoformat(f["datum"])
    rest = (d - dt.date.today()).days
    wann = "heute" if rest == 0 else "morgen" if rest == 1 else "überfällig seit %d Tagen" % -rest if rest < 0 else "in %d Tagen" % rest
    return "%s%s (%s): %s%s%s" % ("%d. " % nr if nr else "", d.strftime("%d.%m.%Y"), wann, f["was"],
                                  " – %s" % f["absender"] if f.get("absender") else "",
                                  " [Dokument %s]" % f["dokument"] if f.get("dokument") else "")
