"""Kalender-Abos (seit 0.7): private Kalender als iCal-Datei holen und dem Kalender-Leser von Jarvis hinlegen.

Beispiel: Eine Schicht-App exportiert den Schichtplan in einen Google-Kalender „Schichtplan“. Dessen „Privatadresse im
iCal-Format“ (Google Kalender: Einstellungen des Kalenders -> Kalender integrieren) ist ein geheimer Link: Wer ihn
kennt, liest den ganzen Kalender. Deshalb steht er nicht in der Konfiguration, sondern in einer eigenen Datei mit
Rechten 600, und keine Meldung nennt ihn. Jeder andere Anbieter mit einer https-Adresse geht genauso (Nextcloud,
Outlook, iCloud, die Export-Adresse einer App).

Konfiguration daten/kalender_abos.json (nicht im Repo), Name -> Datei mit der Adresse (relativ = neben der
Konfiguration):

    {"schichtplan": "/home/jarvis/.config/jarvis/schichtplan_ical",
     "verein": "verein_ical"}

Der Name wird zum Dateinamen <name>.ics im Zielordner, den der Kalender-Leser von Jarvis liest (dort wird er zum
Kalendernamen). Erlaubt sind a-z, 0-9, _ und -, hoechstens 40 Zeichen. Hinweis: Der Kalender-Leser der Vorlage
behandelt Kalender, deren Name mit „arbeit“ beginnt, als Schichtkalender, bei dem der Titel die Arbeitszeit ist und die
Uhrzeit nur ein Platzhalter. Ein Abo mit echten Uhrzeiten (wie der Schichtplan aus der App) bekommt deshalb einen
anderen Namen. Ohne Konfiguration ist die Funktion aus.

Regeln beim Abruf:
  - nur https. Abgelehnt werden http, Zugangsdaten in der Adresse, Heimnetz-Namen (localhost, einteilige Namen, .lan,
    .local, .home.arpa ...) und jedes Ziel, das auf eine private, lokale, loopback- oder link-local-Adresse aufloest
    (jede aufgeloeste Adresse wird geprueft). Die Verbindung geht an genau die gepruefte Adresse (kein zweites DNS),
    das Zertifikat wird gegen den Namen geprueft, Proxys aus der Umgebung gelten nicht.
  - Weiterleitungen folgt der Baustein selbst, hoechstens MAX_WEITERLEITUNGEN, und prueft jedes Ziel wie oben.
  - hoechstens MAX_BYTES; die Antwort muss eine Kalenderdatei sein (beginnt mit BEGIN:VCALENDAR, enthaelt
    END:VCALENDAR).
  - Die Zieldatei wird nur bei Aenderung ersetzt, atomar und mit Rechten 600. Eine kaputte oder fremde Antwort
    ueberschreibt nie die letzte gute Datei.
  - Fehlermeldungen nennen nie die Adresse (auch nicht den Rechnernamen), nur den Namen des Abos und die Art des
    Fehlers.

Die Bruecke ruft alle_holen() im Hintergrund (TAKT_S, alle 30 Minuten). Wer den Plan in der App aendert, exportiert
dort neu; der naechste Abruf uebernimmt es. Abruf (oeffnen) und DNS (aufloesen) lassen sich fuer Tests einspritzen.
Python 3.8, nur Standardbibliothek, Import ohne Nebenwirkungen.
"""
import functools
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import stat
import time
import urllib.error
import urllib.parse
import urllib.request

KONFIG = "kalender_abos.json"
TAKT_S = 1800
MAX_BYTES = 5 * 1024 * 1024
MAX_ADRESSE = 2000
MAX_WEITERLEITUNGEN = 5
ZEITLIMIT_S = 30
NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
KOPF = {"User-Agent": "jarvis-kalender-abo/1", "Accept": "text/calendar, */*;q=0.5", "Accept-Encoding": "identity"}
GESPERRTE_NETZE = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24",
    "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
    "224.0.0.0/4", "240.0.0.0/4", "255.255.255.255/32",
    "::/128", "::1/128", "::ffff:0:0/96", "64:ff9b::/96", "64:ff9b:1::/48", "100::/64", "2001::/32",
    "2001:db8::/32", "2002::/16", "fc00::/7", "fe80::/10", "fec0::/10", "ff00::/8"))
# Namen, die nie ins Internet gehoeren. Die eigene Domain, die im Heimnetz auf eine private Adresse aufloest, faengt
# die Adresspruefung ab.
GESPERRTE_NAMEN = ("localhost", "localdomain", "local", "lan", "home", "internal", "intranet", "home.arpa", "fritz.box")

# Sprache der Meldungen (seit 0.7). Die Bruecke setzt sie beim Start aus der Einrichtung (antworten.json "sprache").
SPRACHE = "de"


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


class AboFehler(Exception):
    """Fehler bei einem Abo. Der Text nennt nie die Adresse."""


# ---------------------------------------------------------------- Konfiguration

def konfig_laden(pfad):
    """-> (abos, abgelehnt): abos = {name: Pfad der Adressdatei}, abgelehnt = Namen, die nicht erlaubt sind.
    Ohne Datei ({}, []) (Funktion aus). Kaputte Datei: AboFehler."""
    try:
        with open(pfad, encoding="utf-8") as f:
            roh = json.load(f)
    except FileNotFoundError:
        return {}, []
    except (OSError, ValueError):
        raise AboFehler(_t("Konfiguration der Kalender-Abos unlesbar", "calendar subscription config unreadable")) \
            from None
    if not isinstance(roh, dict):
        raise AboFehler(_t("Konfiguration der Kalender-Abos ist kein Objekt (Name -> Adressdatei)",
                           "calendar subscription config is not an object (name -> address file)"))
    abos, abgelehnt = {}, []
    basis = os.path.dirname(os.path.abspath(pfad))
    for name, datei in roh.items():
        if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(datei, str) or not datei.strip():
            abgelehnt.append(str(name)[:40])
            continue
        abos[name] = os.path.join(basis, os.path.expanduser(datei.strip()))
    return abos, abgelehnt


def _adresse_lesen(adresse_datei):
    """Adresse aus der Datei. Die Datei muss eine normale Datei sein und darf (wo es Unix-Rechte gibt) nur fuer den
    Besitzer lesbar sein (600). Geprueft am offenen Dateideskriptor, nicht vorher am Namen."""
    try:
        fd = os.open(adresse_datei, os.O_RDONLY)
    except FileNotFoundError:
        raise AboFehler(_t("keine Adresse hinterlegt", "no address stored")) from None
    except OSError:
        raise AboFehler(_t("Adressdatei unlesbar", "address file unreadable")) from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise AboFehler(_t("Adressdatei ist keine normale Datei", "address file is not a regular file"))
        if os.name == "posix" and st.st_mode & 0o077:
            raise AboFehler(_t("Adressdatei ist für andere lesbar (Rechte 600 setzen)",
                               "address file is readable by others (set permissions to 600)"))
        roh = b""
        while len(roh) <= MAX_ADRESSE:
            stueck = os.read(fd, MAX_ADRESSE + 1 - len(roh))
            if not stueck:
                break
            roh += stueck
    except OSError:
        raise AboFehler(_t("Adressdatei unlesbar", "address file unreadable")) from None
    finally:
        os.close(fd)
    try:
        return roh.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise AboFehler(_t("Adresse hat nicht die erwartete Form", "address does not have the expected form")) from None


# ---------------------------------------------------------------- Adresspruefung (wie bei der Welt-Wache)

def adresse_erlaubt(ip):
    """Nur oeffentlich erreichbare Unicast-Adressen."""
    try:
        a = ipaddress.ip_address(str(ip).split("%", 1)[0])
    except ValueError:
        return False
    if "%" in str(ip):                               # Zonen-Angabe gibt es nur bei link-local
        return False
    if any(a in n for n in GESPERRTE_NETZE if n.version == a.version):
        return False
    if (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified
            or not a.is_global):
        return False
    return not (a.version == 6 and (a.ipv4_mapped is not None or a.sixtofour is not None or a.teredo is not None))


def _ist_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _name_gesperrt(host):
    h = host.lower().rstrip(".")
    if not h:
        return True
    if _ist_ip(h):
        return False                                 # Adressen prueft adresse_erlaubt
    if "." not in h:                                 # einteilige Namen sind Heimnetz ("nas", "router")
        return True
    return any(h == n or h.endswith("." + n) for n in GESPERRTE_NAMEN)


def url_pruefen(url):
    """Form pruefen (ohne DNS). -> (url, host, port). AboFehler bei allem ausser https, mit Zugangsdaten, Heimnetz."""
    u = str(url or "").strip()
    if not u or len(u) > MAX_ADRESSE or re.search(r"[\x00-\x20\x7f]", u):
        raise AboFehler(_t("Adresse hat nicht die erwartete Form", "address does not have the expected form"))
    try:
        t = urllib.parse.urlsplit(u)
        port = t.port
    except ValueError:
        raise AboFehler(_t("Adresse hat nicht die erwartete Form", "address does not have the expected form")) from None
    if t.scheme.lower() != "https":
        raise AboFehler(_t("nur https-Adressen", "only https addresses"))
    if t.username is not None or t.password is not None or "@" in t.netloc:
        raise AboFehler(_t("keine Zugangsdaten in der Adresse", "no credentials in the address"))
    host = (t.hostname or "").rstrip(".")
    if not host:
        raise AboFehler(_t("Adresse hat nicht die erwartete Form", "address does not have the expected form"))
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise AboFehler(_t("Adresse hat nicht die erwartete Form",
                               "address does not have the expected form")) from None
    host = host.lower()
    if port is not None and not 0 < port < 65536:
        raise AboFehler(_t("Adresse hat nicht die erwartete Form", "address does not have the expected form"))
    if _name_gesperrt(host) or (_ist_ip(host) and not adresse_erlaubt(host)):
        raise AboFehler(_t("Ziel im Heimnetz abgelehnt", "target in the home network refused"))
    netloc = ("[%s]" % host if ":" in host else host) + (":%d" % port if port else "")
    return urllib.parse.urlunsplit(("https", netloc, t.path or "/", t.query, "")), host, port


def _aufloesen(host):
    """Host -> Liste von Adressen (Text). Tests ersetzen diese Funktion."""
    return [i[4][0] for i in socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM)]


def adresse_pruefen(host, aufloesen=None):
    """Loest host auf und prueft JEDE Adresse. -> Liste der Adressen fuer die Verbindung (IPv4 zuerst).
    Abgelehnt, wenn eine einzige Adresse privat/lokal ist."""
    if _ist_ip(host):
        adressen = [host]
    else:
        try:
            adressen = list(dict.fromkeys(str(a) for a in (aufloesen or _aufloesen)(host)))
        except (OSError, UnicodeError, ValueError):
            raise AboFehler(_t("Name nicht auflösbar", "name does not resolve")) from None
    if not adressen:
        raise AboFehler(_t("Name nicht auflösbar", "name does not resolve"))
    if not all(adresse_erlaubt(a) for a in adressen):
        raise AboFehler(_t("Ziel im Heimnetz abgelehnt", "target in the home network refused"))
    return sorted(adressen, key=lambda a: ":" in a)


# ---------------------------------------------------------------- Abruf mit festgelegter Adresse

class _PinTLS(http.client.HTTPSConnection):
    """Verbindet mit einer der vorher geprueften Adressen statt erneut aufzuloesen; Zertifikat gegen den Namen."""

    def __init__(self, host, ips=(), **kw):
        http.client.HTTPSConnection.__init__(self, host, **kw)
        self._ips = list(ips)

    def connect(self):
        letzter = None
        for ip in self._ips:
            try:
                roh = socket.create_connection((ip, self.port), self.timeout)
            except OSError as e:
                letzter = e
                continue
            try:
                self.sock = self._context.wrap_socket(roh, server_hostname=self.host)
            except BaseException:
                roh.close()
                raise
            return
        raise letzter or OSError("keine Adresse")


class _PinHTTPS(urllib.request.HTTPSHandler):
    def __init__(self, ips):
        urllib.request.HTTPSHandler.__init__(self, context=ssl.create_default_context())
        self._ips = ips

    def https_open(self, req):
        return self.do_open(functools.partial(_PinTLS, ips=self._ips), req, context=self._context)


class _KeinHTTP(urllib.request.HTTPHandler):
    def http_open(self, req):
        raise urllib.error.URLError("nur https")


class _KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nicht selbst folgen: holen() prueft jedes Ziel neu."""

    def http_error_302(self, req, fp, code, msg, headers):
        return None
    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _oeffner(ips):
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _KeineWeiterleitung(), _KeinHTTP(),
                                       _PinHTTPS(ips))


def _grund(e):
    """Art des Fehlers ohne Text der Ausnahme (der koennte Adresse oder Rechnernamen enthalten)."""
    r = getattr(e, "reason", e)
    if isinstance(r, socket.timeout) or isinstance(e, socket.timeout):
        return _t("Zeitüberschreitung", "timeout")
    if isinstance(r, ssl.SSLCertVerificationError):
        return _t("Zertifikat ungültig", "invalid certificate")
    if isinstance(r, ssl.SSLError):
        return _t("TLS-Fehler", "TLS error")
    if isinstance(r, ConnectionRefusedError):
        return _t("Verbindung abgelehnt", "connection refused")
    return _t("nicht erreichbar (%s)", "not reachable (%s)") % type(r).__name__


def _schliessen(x):
    """Antwort oder HTTPError schliessen; ein HTTPError ohne Datenstrom laesst sich unter Python 3.8 nicht schliessen."""
    try:
        x.close()
    except Exception:                                # noqa: BLE001
        pass


def _abrufen(url, oeffnen, aufloesen, timeout):
    """-> Inhalt (bytes, hoechstens MAX_BYTES + 1). Jede Adresse, auch nach Weiterleitungen, wird geprueft."""
    ende = time.monotonic() + timeout
    aktuell = url
    for _ in range(MAX_WEITERLEITUNGEN + 1):
        adresse, host, _port = url_pruefen(aktuell)
        ips = adresse_pruefen(host, aufloesen)
        rest = ende - time.monotonic()
        if rest <= 0:
            raise AboFehler(_t("Zeitüberschreitung", "timeout"))
        req = urllib.request.Request(adresse, headers=KOPF)
        try:
            antwort = oeffnen(req, timeout=rest) if oeffnen else _oeffner(ips).open(req, timeout=rest)
        except urllib.error.HTTPError as e:
            try:
                ziel = (e.headers.get("Location") or "") if e.headers is not None else ""
            finally:
                _schliessen(e)
            if e.code in (301, 302, 303, 307, 308):
                if not str(ziel).strip():
                    raise AboFehler(_t("Weiterleitung ohne Ziel", "redirect without target")) from None
                aktuell = urllib.parse.urljoin(adresse, str(ziel).strip())
                continue
            raise AboFehler(_t("Server antwortet mit %d", "server responded with %d") % e.code) from None
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
            raise AboFehler(_grund(e)) from None
        try:
            status = int(getattr(antwort, "status", None) or 200)
            if not 200 <= status < 300:
                raise AboFehler(_t("Server antwortet mit %d", "server responded with %d") % status)
            return antwort.read(MAX_BYTES + 1)
        except (OSError, ValueError, http.client.HTTPException) as e:
            raise AboFehler(_grund(e)) from None
        finally:
            _schliessen(antwort)
    raise AboFehler(_t("zu viele Weiterleitungen", "too many redirects"))


def ist_kalender(daten):
    """Sieht wie eine iCal-Datei aus: beginnt (nach BOM und Leerraum) mit BEGIN:VCALENDAR, enthaelt END:VCALENDAR."""
    kopf = daten.lstrip().lstrip(b"\xef\xbb\xbf").lstrip()
    return kopf.startswith(b"BEGIN:VCALENDAR") and b"END:VCALENDAR" in daten


def holen(adresse_datei, ziel, oeffnen=None, aufloesen=None, timeout=ZEITLIMIT_S):
    """Ein Abo holen und nur bei Aenderung ersetzen. -> (geaendert, anzahl_termine). Wirft AboFehler.
    oeffnen(request, timeout=...) und aufloesen(host) -> [Adressen] ersetzen Tests; ohne oeffnen verbindet der
    Baustein selbst mit der geprueften Adresse."""
    url = _adresse_lesen(adresse_datei)
    daten = _abrufen(url, oeffnen, aufloesen, timeout)
    if len(daten) > MAX_BYTES:
        raise AboFehler(_t("Antwort größer als %d MB", "response larger than %d MB") % (MAX_BYTES // (1024 * 1024)))
    if not ist_kalender(daten):
        raise AboFehler(_t("Antwort ist keine Kalenderdatei", "response is not a calendar file"))
    anzahl = daten.count(b"BEGIN:VEVENT")
    try:
        with open(ziel, "rb") as f:
            if f.read(MAX_BYTES + 1) == daten:
                return False, anzahl
    except OSError:
        pass
    neu = ziel + ".neu"                      # endet nicht auf .ics: der Kalender-Leser liest es nie halb geschrieben
    try:
        os.unlink(neu)                       # Rest eines abgebrochenen Laufs (auch ein Link) weg, dann exklusiv neu
    except FileNotFoundError:
        pass
    try:
        fd = os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(daten)
        os.chmod(neu, 0o600)
        os.replace(neu, ziel)
    except OSError as e:
        try:
            os.unlink(neu)
        except OSError:
            pass
        raise AboFehler(_t("Zieldatei nicht schreibbar (%s)", "target file not writable (%s)") % type(e).__name__) \
            from None
    return True, anzahl


def alle_holen(konfig_pfad, zielordner, oeffnen=None, aufloesen=None, log=None, timeout=ZEITLIMIT_S):
    """Alle Abos aus der Konfiguration holen; ein Fehler haelt die anderen nicht auf.
    -> {name: {"geaendert": bool, "termine": n} oder {"fehler": Text}}. log(*teile) bekommt nur Name und Fehlerart."""
    log = log or (lambda *a: None)
    try:
        abos, abgelehnt = konfig_laden(konfig_pfad)
    except AboFehler as e:
        log("Kalender-Abos:", str(e))
        return {}
    ergebnis = {}
    for name in abgelehnt:
        ergebnis[name] = {"fehler": _t("Name nicht erlaubt (a-z, 0-9, _ und -)", "name not allowed (a-z, 0-9, _ and -)")}
        log("Kalender-Abo %s:" % name, ergebnis[name]["fehler"])
    if abos and not os.path.isdir(zielordner):
        log("Kalender-Abos:", _t("Zielordner fehlt", "target folder missing"))
        return dict(ergebnis, **{n: {"fehler": _t("Zielordner fehlt", "target folder missing")} for n in abos})
    for name, adresse_datei in sorted(abos.items()):
        try:
            geaendert, n = holen(adresse_datei, os.path.join(zielordner, name + ".ics"), oeffnen, aufloesen, timeout)
            ergebnis[name] = {"geaendert": geaendert, "termine": n}
            if geaendert:
                log("Kalender-Abo %s:" % name, _t("neu geholt, %d Termine", "updated, %d events") % n)
        except AboFehler as e:
            ergebnis[name] = {"fehler": str(e)}
            log("Kalender-Abo %s:" % name, str(e))
    return ergebnis
