"""Postfach (seit 0.4): Jarvis liest das Postfach der Hauptperson per IMAP und darf Mails
verschieben, nie loeschen. Python 3.8, nur Standardbibliothek.

Zugang: JSON-Datei (600) {"server", "port", "benutzer", "passwort"} ausserhalb des Repos (bei IMAP-Anbietern
mit Zwei-Faktor-Anmeldung ein App-Passwort). Gelesen wird nur mit EXAMINE und BODY.PEEK: Jarvis aendert keinen Gelesen-Status.
Verschoben wird mit UID MOVE (RFC 6851); Ziele, die einem Loeschen gleichkommen (Papierkorb, \\Trash), lehnt das
Modul ab. Kennung einer Mail fuer das Gehirn: "<Ordner>:<UID>".
"""
import base64
import contextlib
import datetime as dt
import email
import email.header
import email.utils
import email.policy
import html
import imaplib
import json
import re
import socket
import ssl

ZEIT_S = 30
GROESSE_MAX = 25 * 1024 * 1024          # groessere Mails werden nicht geladen
TEXT_MAX = 4000
KOPF_MAX = 200                          # so viele neueste Mails je Ordner werden fuer eine Suche angesehen
VERBOTEN = re.compile(r"gel[öo]scht|papierkorb|trash|deleted|bin\b", re.I)


class Fehler(Exception):
    pass


# ------------------------------------------------------------------ IMAP-UTF-7 (RFC 3501, 5.1.3)

def utf7_decode(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "&":
            j = s.index("-", i)
            if j == i + 1:
                out.append("&")
            else:
                b = s[i + 1:j].replace(",", "/")
                b += "=" * (-len(b) % 4)
                out.append(base64.b64decode(b).decode("utf-16-be"))
            i = j + 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def utf7_encode(s):
    out, puffer = [], []

    def leeren():
        if puffer:
            b = base64.b64encode("".join(puffer).encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            out.append("&" + b + "-")
            puffer.clear()
    for c in s:
        if 0x20 <= ord(c) <= 0x7e:
            leeren()
            out.append("&-" if c == "&" else c)
        else:
            puffer.append(c)
    leeren()
    return "".join(out)


# ------------------------------------------------------------------ Verbindung

def zugang_laden(pfad):
    try:
        k = json.load(open(pfad, encoding="utf-8"))
    except (OSError, ValueError):
        raise Fehler("Für das Postfach ist noch kein Zugang eingerichtet.")
    if not all(k.get(x) for x in ("server", "port", "benutzer", "passwort")):
        raise Fehler("Der Postfach-Zugang ist unvollständig.")
    return k


class _IMAP(imaplib.IMAP4_SSL):
    """IMAP ueber TLS mit Zeitgrenze je Verbindung (Python 3.8 kennt timeout= noch nicht). Kein globales
    socket.setdefaulttimeout: das waere zwischen Threads nicht sicher."""

    def _create_socket(self, timeout=None):
        sock = socket.create_connection((self.host, self.port), ZEIT_S)
        return self.ssl_context.wrap_socket(sock, server_hostname=self.host)


def tls_kontext():
    """Mit Pruefung von Zertifikat und Hostname. imaplib nimmt ohne ssl_context einen Kontext OHNE Pruefung
    (ssl._create_stdlib_context), dann koennte sich jeder auf dem Netzweg als Mailserver ausgeben."""
    return ssl.create_default_context()


@contextlib.contextmanager
def verbunden(zugang):
    try:
        m = _IMAP(zugang["server"], int(zugang["port"]), ssl_context=tls_kontext())
    except ssl.SSLCertVerificationError as e:
        raise Fehler("Das Zertifikat des Mailservers ist ungültig (%s). Ich melde mich dort nicht an." % type(e).__name__)
    except ssl.SSLError as e:
        raise Fehler("Keine sichere Verbindung zum Mailserver (%s). Stimmen Server und Port (IMAP über TLS, meist "
                     "993)?" % type(e).__name__)
    except (OSError, imaplib.IMAP4.error) as e:
        raise Fehler("Das Postfach ist gerade nicht erreichbar (%s)." % type(e).__name__)
    try:
        try:
            m.login(zugang["benutzer"], zugang["passwort"])
        except imaplib.IMAP4.error:
            raise Fehler("Die Anmeldung am Postfach wurde abgelehnt.")
        yield m
    finally:
        try:
            m.logout()
        except Exception:
            pass


def ordner(m):
    """[{"name": lesbar, "roh": IMAP-Name, "flags": set}]"""
    typ, daten = m.list()
    liste = []
    for z in daten or []:
        z = z.decode("utf-8", "replace") if isinstance(z, bytes) else str(z)
        f = re.match(r'\(([^)]*)\) (?:"[^"]*"|NIL) (.+)$', z)
        if not f:
            continue
        roh = f.group(2).strip().strip('"')
        liste.append({"name": "Posteingang" if roh.upper() == "INBOX" else utf7_decode(roh), "roh": roh,
                      "flags": set(f.group(1).split())})
    return liste


ALIAS = {"posteingang": "INBOX", "inbox": "INBOX", "eingang": "INBOX"}
FLAG = {"spam": "\\Junk", "junk": "\\Junk", "spamverdacht": "\\Junk", "gesendet": "\\Sent", "entwürfe": "\\Drafts",
        "entwuerfe": "\\Drafts", "archiv": "\\Archive"}


def ordner_finden(m, wunsch):
    w = str(wunsch or "").strip().lower()
    liste = ordner(m)
    if ALIAS.get(w):
        return next((o for o in liste if o["roh"].upper() == "INBOX"), {"name": "Posteingang", "roh": "INBOX", "flags": set()})
    for o in liste:
        if o["name"].lower() == w:
            return o
    if FLAG.get(w):
        for o in liste:
            if FLAG[w] in o["flags"]:
                return o
    treffer = [o for o in liste if w and w in o["name"].lower()]
    if len(treffer) == 1:
        return treffer[0]
    raise Fehler("Den Ordner „%s“ gibt es nicht. Vorhanden: %s" % (wunsch, ", ".join(o["name"] for o in liste)))


def spam_ordner(m):
    for o in ordner(m):
        if "\\Junk" in o["flags"] or o["name"].lower() in ("spamverdacht", "spam", "junk"):
            return o
    return None


def _quote(roh):
    return '"' + roh.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _waehlen(m, o):
    typ, d = m.select(_quote(o["roh"]), readonly=True)          # EXAMINE: nur lesen
    if typ != "OK":
        raise Fehler("Den Ordner „%s“ kann ich nicht öffnen." % o["name"])
    return int(d[0] or 0)


# ------------------------------------------------------------------ Lesen

def _dekodiere(wert):
    try:
        return str(email.header.make_header(email.header.decode_header(wert or "")))
    except Exception:
        return str(wert or "")


def _koepfe(m, o, uids):
    if not uids:
        return []
    typ, d = m.uid("FETCH", ",".join(str(u) for u in uids),
                   "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
    erg = []
    for teil in d or []:
        if not isinstance(teil, tuple):
            continue
        kopf = teil[0].decode("utf-8", "replace")
        uid = re.search(r"UID (\d+)", kopf)
        if not uid:
            continue
        msg = email.message_from_bytes(teil[1], policy=email.policy.compat32)
        try:
            datum = email.utils.parsedate_to_datetime(msg.get("Date")).astimezone().strftime("%d.%m.%Y %H:%M")
        except Exception:
            datum = ""
        erg.append({"id": "%s:%s" % (o["name"], uid.group(1)), "uid": int(uid.group(1)), "ordner": o["name"],
                    "von": _dekodiere(msg.get("From"))[:120], "betreff": _dekodiere(msg.get("Subject"))[:200],
                    "datum": datum, "gelesen": "\\Seen" in kopf,
                    "groesse": int((re.search(r"RFC822\.SIZE (\d+)", kopf) or [0, 0])[1])})
    return sorted(erg, key=lambda e: e["uid"], reverse=True)


def neueste(zugang, wo="posteingang", anzahl=10, nur_ungelesen=False):
    with verbunden(zugang) as m:
        o = ordner_finden(m, wo)
        _waehlen(m, o)
        typ, d = m.uid("SEARCH", "UNSEEN" if nur_ungelesen else "ALL")
        uids = [int(x) for x in (d[0] or b"").split()][-max(1, min(int(anzahl), 50)):]
        return _koepfe(m, o, uids)


def suchen(zugang, text, wo=None, tage=30):
    """Absender und Betreff durchsuchen (ohne wo: Posteingang und Spam). Nur die neuesten KOPF_MAX je Ordner."""
    seit = (dt.date.today() - dt.timedelta(days=max(1, min(int(tage or 30), 365)))).strftime("%d-%b-%Y")
    woerter = [w for w in re.split(r"\s+", str(text or "").lower()) if w]
    erg = []
    with verbunden(zugang) as m:
        if wo:
            ziele = [ordner_finden(m, wo)]
        else:
            ziele = [ordner_finden(m, "posteingang")] + [x for x in [spam_ordner(m)] if x]
        for o in ziele:
            _waehlen(m, o)
            typ, d = m.uid("SEARCH", "SINCE", seit)
            uids = [int(x) for x in (d[0] or b"").split()][-KOPF_MAX:]
            for k in _koepfe(m, o, uids):
                inhalt = (k["von"] + " " + k["betreff"]).lower()
                if all(w in inhalt for w in woerter):
                    erg.append(k)
    return sorted(erg, key=lambda e: (e["datum"][6:10], e["datum"][3:5], e["datum"][:2], e["datum"][11:]), reverse=True)[:20]


def _id_teilen(kennung):
    k = str(kennung or "")
    if ":" not in k or not k.rsplit(":", 1)[1].isdigit():
        raise Fehler("Diese Mail-Kennung verstehe ich nicht (erwartet Ordner:Nummer).")
    wo, uid = k.rsplit(":", 1)
    return wo, int(uid)


def _laden(m, kennung):
    wo, uid = _id_teilen(kennung)
    o = ordner_finden(m, wo)
    _waehlen(m, o)
    typ, d = m.uid("FETCH", str(uid), "(RFC822.SIZE)")
    groesse = int((re.search(rb"RFC822\.SIZE (\d+)", d[0] or b"") or [0, b"0"])[1]) if d and d[0] else 0
    if not groesse:
        raise Fehler("Diese Mail gibt es dort nicht (mehr).")
    if groesse > GROESSE_MAX:
        raise Fehler("Die Mail ist zu groß zum Lesen (%d MB)." % (groesse // 1048576))
    typ, d = m.uid("FETCH", str(uid), "(BODY.PEEK[])")                 # PEEK: Gelesen-Status bleibt
    roh = next((t[1] for t in d or [] if isinstance(t, tuple)), None)
    if not roh:
        raise Fehler("Die Mail ließ sich nicht laden.")
    return o, uid, email.message_from_bytes(roh, policy=email.policy.default)


def _text(msg):
    teil = msg.get_body(preferencelist=("plain", "html"))
    if teil is None:
        return ""
    try:
        t = teil.get_content()
    except Exception:
        t = teil.get_payload(decode=True) or b""
        t = t.decode("utf-8", "replace") if isinstance(t, bytes) else str(t)
    if teil.get_content_type() == "text/html":
        t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
        t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", t)
        t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _anhaenge(msg):
    liste = []
    for teil in msg.iter_attachments():
        name = teil.get_filename() or "anhang"
        roh = teil.get_payload(decode=True) or b""
        liste.append({"name": name[:120], "typ": teil.get_content_type(), "groesse": len(roh), "roh": roh})
    return liste


def lesen(zugang, kennung):
    with verbunden(zugang) as m:
        o, uid, msg = _laden(m, kennung)
        anh = _anhaenge(msg)
        return {"id": kennung, "von": _dekodiere(msg.get("From"))[:200], "an": _dekodiere(msg.get("To"))[:200],
                "betreff": _dekodiere(msg.get("Subject"))[:300], "datum": str(msg.get("Date") or "")[:60],
                "text": _text(msg)[:TEXT_MAX], "anhaenge": [{"nr": i + 1, "name": a["name"], "typ": a["typ"],
                                                              "groesse": a["groesse"]} for i, a in enumerate(anh)]}


def anhang(zugang, kennung, nr):
    with verbunden(zugang) as m:
        o, uid, msg = _laden(m, kennung)
        anh = _anhaenge(msg)
        if not 1 <= int(nr or 0) <= len(anh):
            raise Fehler("Diese Mail hat %d Anhänge." % len(anh))
        return anh[int(nr) - 1]


# ------------------------------------------------------------------ Verschieben (nie loeschen)

SPAM = re.compile(r"spam|junk", re.I)


def verschieben(zugang, kennung, ziel, spam_erlaubt=False):
    """Mail in einen anderen Ordner, nie in den Papierkorb. Den Spam-Ordner nur mit spam_erlaubt=True: das setzt die
    Bruecke nur, wenn die eigene Nachricht der Person ihn nennt (viele Anbieter loeschen dort nach einigen Tagen)."""
    with verbunden(zugang) as m:
        wo, uid = _id_teilen(kennung)
        quelle = ordner_finden(m, wo)
        z = ordner_finden(m, ziel)
        if "\\Trash" in z["flags"] or VERBOTEN.search(z["name"]):
            raise Fehler("In „%s“ verschiebe ich nichts, das käme einem Löschen gleich. Löschen darf ich nicht." % z["name"])
        if ("\\Junk" in z["flags"] or SPAM.search(z["name"])) and not spam_erlaubt:
            raise Fehler("In den Spam-Ordner verschiebe ich nur, wenn du ihn selbst nennst: viele Anbieter löschen dort "
                         "nach einigen Tagen.")
        if z["roh"] == quelle["roh"]:
            raise Fehler("Die Mail liegt schon in „%s“." % z["name"])
        typ, d = m.select(_quote(quelle["roh"]))                         # zum Verschieben schreibend oeffnen
        if typ != "OK":
            raise Fehler("Den Ordner „%s“ kann ich nicht öffnen." % quelle["name"])
        typ, d = m.uid("SEARCH", "UID", str(uid))
        if str(uid).encode() not in (d[0] or b"").split():
            raise Fehler("Diese Mail gibt es in „%s“ nicht (mehr)." % quelle["name"])
        typ, d = m.uid("MOVE", str(uid), _quote(z["roh"]))
        if typ != "OK":
            raise Fehler("Das Verschieben hat das Postfach abgelehnt.")
        # Die neue UID steht in der Zwischenantwort "* OK [COPYUID <validity> <alt> <neu>]"; imaplib legt sie unter
        # COPYUID ab, nicht in d (28.10.: der erste Verschiebetest fand sie deshalb nicht)
        _, cu = m.response("COPYUID")
        neu = re.search(rb"\d+ \d+ (\d+)", b" ".join(x for x in (cu or []) if isinstance(x, bytes)))
        return {"von": quelle["name"], "nach": z["name"], "neu": "%s:%s" % (z["name"], neu.group(1).decode()) if neu else ""}


# ------------------------------------------------------------------ Melden auf Zuruf

def hoechste_uids(zugang):
    """{Ordnername: hoechste UID} fuer Posteingang und Spam (Startpunkt einer Wache)."""
    erg = {}
    with verbunden(zugang) as m:
        for o in [ordner_finden(m, "posteingang")] + [x for x in [spam_ordner(m)] if x]:
            _waehlen(m, o)
            typ, d = m.uid("SEARCH", "ALL")
            uids = [int(x) for x in (d[0] or b"").split()]
            erg[o["name"]] = max(uids) if uids else 0
    return erg


def neue_seit(zugang, stand):
    """Koepfe neuer Mails seit stand {Ordner: UID} in Posteingang und Spam; liefert (koepfe, neuer_stand)."""
    neu, koepfe = dict(stand), []
    with verbunden(zugang) as m:
        for o in [ordner_finden(m, "posteingang")] + [x for x in [spam_ordner(m)] if x]:
            _waehlen(m, o)
            ab = int(stand.get(o["name"], 0)) + 1
            typ, d = m.uid("SEARCH", "UID", "%d:*" % ab)
            uids = [int(x) for x in (d[0] or b"").split() if int(x) >= ab][-50:]
            if uids:
                koepfe += _koepfe(m, o, uids)
                neu[o["name"]] = max(uids)
    return koepfe, neu
