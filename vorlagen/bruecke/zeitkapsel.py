"""Zeitkapsel (S10, Superhirn, seit 0.7): Botschaften an die Zukunft, an ein Datum oder ein Lebensereignis gebunden
(„wenn Kim 18 wird“, „in 5 Jahren“). Am Tag X kommt sie als Durchsage, Push oder beides.

Ehrlich zu „versiegelt“: Versiegelt heißt, Jarvis gibt den Inhalt vor dem Tag nicht heraus, auch nicht dem Absender
und auch nicht auf Nachfrage (liste nennt nur Eckdaten, archiv nur geöffnete Kapseln). Technisch liegt der Text lesbar
auf dem Rechner der Brücke (ctx.daten/zeitkapsel/kapseln.json, 0600, Ordner 0700). Wer Zugriff auf diesen Rechner hat
(die Hauptperson, ein Admin-Werkzeug), könnte ihn lesen. Es ist keine Verschlüsselung und kein Notar.

Aktionen (auftrag):
  neu      fuer (Name, Kennung oder „mich“/„me“), text, ausloeser {"datum": "JJJJ-MM-TT"} | {"in_jahren": N} |
           {"alter": N, "geburtstag": "JJJJ-MM-TT"}, kanal durchsage | push | beides, optional raum, ueberraschung
           (der Empfänger sieht in liste nicht, dass es sie gibt).
  liste    nur Eckdaten (Nr., für wen, von wem, angelegt, fällig, Länge, Weg), nie der Inhalt vor dem Öffnen.
  archiv   geöffnete Kapseln samt Inhalt, für Empfänger und Absender.
  loeschen nur wer sie angelegt hat (nr).

liste und archiv laufen nie über gemeinsame Lautsprecher (LAUTSPRECHER_PRIVAT, seit 0.7: Alexa, HA-Sprachkette und
Sprach-Satelliten hört jeder im Raum mit; die Brücke prüft das). neu bleibt per Sprache erlaubt.

runde(ctx) alle TAKT_S: fällige Kapseln im Fenster 09:00 bis 20:00 Ortszeit zustellen, nie nachts. Gegen doppeltes
Zustellen: Vor jedem Weg (Durchsage, Push) steht ein Vermerk „begonnen“ in der Datei. Findet eine spätere Runde einen
begonnenen Weg ohne Ergebnis (Absturz mitten in der Zustellung), gilt er als zugestellt: lieber einmal zu wenig als
doppelt. Scheitert ein Weg, versucht es die Runde stündlich wieder; nach zwei Tagen ist die Kapsel geöffnet, wenn
wenigstens ein Weg ankam, sonst kommt bei „nur Durchsage“ ein Push als Ersatz dazu.

Geburtstag am 29.02.: In Nicht-Schaltjahren öffnet die Kapsel am 01.03. (an dem Tag ist das Alter sicher erreicht).
Ebenso „in N Jahren“ von einem 29.02. aus. Gäste legen nie Kapseln an und bekommen keine.

Sprache (seit 0.7 im Release): Meldungen, Durchsage, Push und Werkzeugbeschreibung auf Deutsch oder Englisch
(setze_sprache(), wie quiz.py). Aktionsnamen, Kanalnamen und JSON-Schlüssel bleiben gleich. Der Anlass („zum 18.
Geburtstag“) wird beim Anlegen in der eingestellten Sprache gespeichert.

Python 3.8, nur Standardbibliothek, Import ohne Nebenwirkungen.
"""
import copy
import datetime as dt
import json
import os
import re
import threading
import time

NAME = "zeitkapsel"
RECHTE = "familie"
TAKT_S = 300

AKTIONEN = ("liste", "neu", "archiv", "loeschen")
# Aktionen, die nie ueber gemeinsame Lautsprecher laufen duerfen (seit 0.7, Claude-Security-Fund F1): liste nennt
# private Eckdaten, archiv liest Botschaften vor. Das Modul deklariert es nur, die Bruecke prueft.
LAUTSPRECHER_PRIVAT = frozenset({"liste", "archiv"})
KANAELE = ("durchsage", "push", "beides")
FENSTER = (9, 20)                   # zustellen von 09:00 bis vor 20:00 Ortszeit
MAX_OFFEN_JE_PERSON = 50
MAX_TEXT = 1500
MAX_JAHRE = 100
MAX_ALTER = 120
JE_RUNDE = 5                        # höchstens so viele Kapseln je Runde (keine Durchsage-Lawine)
WIEDERHOLEN_S = 3600
ERSATZ_NACH_S = 2 * 86400
RAUM_STANDARD = "wohnzimmer"        # Standardraum fuer die Durchsage, wenn es ihn gibt; sonst ueberall
NICHT_GESPIELT = ("keiner", "abgelehnt", "nachtruhe", "false", "none", "")
ICH = ("mich", "mir", "ich", "selbst", "mich selbst", "mir selbst", "me", "myself")
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember")
WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
MONATE_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December")
MONATE_EN_KURZ = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WOCHENTAGE_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Sprache der Texte, die die Familie hoert oder liest. Die Bruecke setzt sie beim Start aus der Einrichtung
# (antworten.json "sprache"), wie bei quiz.py und szenen.py.
SPRACHE = "de"

_sperre = threading.Lock()          # Datei lesen, ändern, schreiben
_runde_sperre = threading.Lock()    # höchstens eine Runde gleichzeitig


def _t(de, en):
    return en if SPRACHE == "en" else de


# ---------------------------------------------------------------------------------------------- Datei

def _pfad(ctx):
    o = os.path.join(ctx.daten, "zeitkapsel")
    os.makedirs(o, mode=0o700, exist_ok=True)
    return os.path.join(o, "kapseln.json")


def _laden(ctx):
    try:
        with open(_pfad(ctx), encoding="utf-8") as f:
            d = json.load(f)
        return [k for k in d if isinstance(k, dict)] if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _speichern(ctx, liste):
    pfad = _pfad(ctx)
    neu = pfad + ".neu"
    fd = os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=1)
    os.chmod(neu, 0o600)
    os.replace(neu, pfad)


def _aendern(ctx, nr, fn):
    """Eine Kapsel unter der Sperre frisch laden, fn(kapsel) anwenden, speichern. -> Kopie oder None (gelöscht)."""
    with _sperre:
        liste = _laden(ctx)
        for k in liste:
            if k.get("nr") == nr:
                fn(k)
                _speichern(ctx, liste)
                return json.loads(json.dumps(k))
    return None


# ---------------------------------------------------------------------------------------------- Datum

def _datum_lesen(s):
    s = str(s or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s) or None
    if m:
        j, mo, t = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
        if not m:
            return None
        t, mo, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return dt.date(j, mo, t)
    except ValueError:
        return None


def _plus_jahre(d, n):
    """d + n Jahre; ein 29.02. wird in Nicht-Schaltjahren zum 01.03."""
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return dt.date(d.year + n, 3, 1)


def _ganzzahl(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, str) and re.fullmatch(r"\s*\d{1,4}\s*", x):
        return int(x)
    return None


def _heute(ctx):
    lt = time.localtime(ctx.jetzt())
    return dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday)


def _tag(ts):
    lt = time.localtime(float(ts))
    return dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday)


def _lang(d):
    if SPRACHE == "en":
        return "%s, %d %s %d" % (WOCHENTAGE_EN[d.weekday()], d.day, MONATE_EN[d.month - 1], d.year)
    return "%s, %d. %s %d" % (WOCHENTAGE[d.weekday()], d.day, MONATE[d.month - 1], d.year)


def _mittel(d):
    if SPRACHE == "en":
        return "%d %s %d" % (d.day, MONATE_EN[d.month - 1], d.year)
    return "%d. %s %d" % (d.day, MONATE[d.month - 1], d.year)


def _kurz(d):
    if SPRACHE == "en":
        return "%d %s %04d" % (d.day, MONATE_EN_KURZ[d.month - 1], d.year)
    return "%02d.%02d.%04d" % (d.day, d.month, d.year)


def ordnungszahl_en(n):
    """1 -> 1st, 2 -> 2nd, 3 -> 3rd, 11 -> 11th, 21 -> 21st."""
    if 10 <= n % 100 <= 20:
        return "%dth" % n
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def faelligkeit(ausloeser, heute):
    """-> (datum, anlass) oder ValueError mit einem Satz für die Person."""
    a = ausloeser
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except ValueError:
            a = {"datum": a}
    if not isinstance(a, dict) or not any(s in a for s in ("datum", "in_jahren", "alter")):
        raise ValueError(_t("Wann soll sie sich öffnen? ausloeser: {datum: JJJJ-MM-TT}, {in_jahren: N} oder "
                            "{alter: N, geburtstag: JJJJ-MM-TT}.",
                            "When should it open? ausloeser: {datum: YYYY-MM-DD}, {in_jahren: N} or "
                            "{alter: N, geburtstag: YYYY-MM-DD}."))
    if "datum" in a:
        d = _datum_lesen(a["datum"])
        if d is None:
            raise ValueError(_t("Das Datum „%s“ verstehe ich nicht (JJJJ-MM-TT, ein Tag, den es gibt).",
                                "I don't understand the date “%s” (YYYY-MM-DD, a day that exists).") %
                             str(a["datum"])[:20])
        anlass = ""
    elif "in_jahren" in a:
        n = _ganzzahl(a["in_jahren"])
        if n is None or not 1 <= n <= MAX_JAHRE:
            raise ValueError(_t("in_jahren muss eine ganze Zahl von 1 bis %d sein.",
                                "in_jahren must be a whole number from 1 to %d.") % MAX_JAHRE)
        d = _plus_jahre(heute, n)
        if n == 1:
            anlass = _t("ein Jahr nach dem Versiegeln", "one year after sealing")
        else:
            anlass = _t("%d Jahre nach dem Versiegeln", "%d years after sealing") % n
    else:
        n = _ganzzahl(a["alter"])
        if n is None or not 1 <= n <= MAX_ALTER:
            raise ValueError(_t("alter muss eine ganze Zahl von 1 bis %d sein.",
                                "alter must be a whole number from 1 to %d.") % MAX_ALTER)
        geb = _datum_lesen(a.get("geburtstag"))
        if geb is None:
            raise ValueError(_t("Für ein Alter brauche ich den Geburtstag (geburtstag als JJJJ-MM-TT).",
                                "For an age I need the birthday (geburtstag as YYYY-MM-DD)."))
        if geb > heute:
            raise ValueError(_t("Der Geburtstag liegt in der Zukunft.", "The birthday is in the future."))
        d = _plus_jahre(geb, n)
        anlass = _t("zum %d. Geburtstag" % n, "for the %s birthday" % ordnungszahl_en(n))
        if d <= heute:
            raise ValueError(_t("Das Alter %d ist schon erreicht (%s).", "The age %d has already been reached (%s).")
                             % (n, _kurz(d)))
    if d <= heute:
        raise ValueError(_t("Der Tag muss in der Zukunft liegen, frühestens morgen.",
                            "The day must be in the future, tomorrow at the earliest."))
    if d > _plus_jahre(heute, MAX_JAHRE):
        raise ValueError(_t("Höchstens %d Jahre in die Zukunft.", "At most %d years into the future.") % MAX_JAHRE)
    return d, anlass


# ---------------------------------------------------------------------------------------------- Personen, Texte

def _rolle(ctx, person):
    return (ctx.personen().get(person) or {}).get("rolle")


def _person_finden(ctx, wer, fragender):
    w = " ".join(str(wer or "").split()).lower()
    if w in ICH:
        return fragender
    for k, e in ctx.personen().items():
        if e.get("rolle") in ("haupt", "familie") and w and w in (str(k).lower(), str(e.get("name") or "").lower()):
            return k
    return None


def _familie_namen(ctx):
    return ", ".join(e.get("name") or k for k, e in ctx.personen().items() if e.get("rolle") in ("haupt", "familie"))


def _text_saeubern(t):
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(t or "")).replace("\r", "")
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _raeume(ctx):
    try:
        return dict((ctx.raeume() or {}).get("raeume") or {})
    except Exception:
        return {}


def _raum_name(ctx, raum):
    if raum == "ueberall":
        return _t("überall", "everywhere")
    return (_raeume(ctx).get(raum) or {}).get("name") or raum


def _weg_text(ctx, k):
    if SPRACHE == "en":
        d = "as an announcement %s" % ("everywhere" if k.get("raum") == "ueberall"
                                       else "in the room " + _raum_name(ctx, k.get("raum")))
        return {"durchsage": d, "push": "by push", "beides": d + " and by push"}.get(k.get("kanal"), "?")
    d = "als Durchsage %s" % ("überall" if k.get("raum") == "ueberall" else "im Raum " + _raum_name(ctx, k.get("raum")))
    return {"durchsage": d, "push": "per Push", "beides": d + " und per Push"}.get(k.get("kanal"), "?")


def _fuer_wen(ctx, k, fragender):
    if k["fuer"] == k["von"]:
        return _t("dich selbst", "yourself") if k["von"] == fragender else \
            _t("%s selbst", "%s themselves") % ctx.person_name(k["von"])
    return _t("dich", "you") if k["fuer"] == fragender else ctx.person_name(k["fuer"])


def _anlass_text(k):
    return " (%s)" % k["anlass"] if k.get("anlass") else ""


def _eckdaten(ctx, k, fragender):
    teile = [_t("Nr. %d", "No. %d") % k["nr"]]
    if k["von"] == fragender:
        teile.append(_t("für %s", "for %s") % _fuer_wen(ctx, k, fragender))
    else:
        teile.append(_t("von %s", "from %s") % ctx.person_name(k["von"]))
    teile.append(_t("angelegt am %s", "created on %s") % _kurz(_tag(k["angelegt"])))
    teile.append(_t("öffnet sich am %s%s", "opens on %s%s") % (_kurz(_datum_lesen(k["faellig"])), _anlass_text(k)))
    teile.append(_t("%d Zeichen", "%d characters") % len(k.get("text") or ""))
    if k["von"] == fragender:
        teile.append(_weg_text(ctx, k))
        if k.get("ueberraschung"):
            teile.append(_t("Überraschung", "surprise"))
    return ", ".join(teile)


# ---------------------------------------------------------------------------------------------- Werkzeug

def auftrag(b, person, ctx):
    """Werkzeug zeitkapsel. b = Argumente (aktion, fuer, text, ausloeser, kanal, raum, ueberraschung, nr)."""
    b = b if isinstance(b, dict) else {}
    if _rolle(ctx, person) not in ("haupt", "familie"):
        return {"meldung": _t("Zeitkapseln gibt es nur für die Familie.", "Time capsules are only for the family.")}
    aktion = b.get("aktion")
    if aktion is None:
        aktion = "liste"
    if aktion not in AKTIONEN:
        return {"meldung": _t("aktion muss eine von %s sein.", "aktion must be one of %s.") % ", ".join(AKTIONEN)}
    if aktion == "neu":
        return _neu(ctx, person, b)
    if aktion == "liste":
        return _liste(ctx, person)
    if aktion == "archiv":
        return _archiv(ctx, person, b.get("nr"))
    return _loeschen(ctx, person, b.get("nr"))


def _neu(ctx, person, b):
    fuer = _person_finden(ctx, b.get("fuer"), person)
    if not fuer:
        return {"meldung": _t("Für wen ist die Zeitkapsel? Ich kenne: %s (oder „mich“).",
                              "Who is the time capsule for? I know: %s (or “me”).") % _familie_namen(ctx)}
    text = _text_saeubern(b.get("text"))
    if not text:
        return {"meldung": _t("Was soll in der Zeitkapsel stehen?", "What should the time capsule say?")}
    if len(text) > MAX_TEXT:
        return {"meldung": _t("Die Botschaft ist zu lang (%d Zeichen, höchstens %d).",
                              "The message is too long (%d characters, at most %d).") % (len(text), MAX_TEXT)}
    heute = _heute(ctx)
    try:
        faellig, anlass = faelligkeit(b.get("ausloeser"), heute)
    except ValueError as e:
        return {"meldung": str(e)}
    kanal = b.get("kanal") or "beides"
    if kanal not in KANAELE:
        return {"meldung": _t("kanal muss durchsage, push oder beides sein.",
                              "kanal must be durchsage (announcement), push or beides (both).")}
    raum = ""
    if kanal in ("durchsage", "beides"):
        raeume = _raeume(ctx)
        raum = str(b.get("raum") or "").strip().lower() or (RAUM_STANDARD if RAUM_STANDARD in raeume else "ueberall")
        if raum != "ueberall" and raum not in raeume:
            return {"meldung": _t("Den Raum „%s“ kenne ich nicht. Möglich: %s oder ueberall.",
                                  "I don't know the room “%s”. Possible: %s or ueberall (everywhere).") % (
                raum, ", ".join(sorted(raeume)))}
    with _sperre:
        liste = _laden(ctx)
        if sum(1 for k in liste if k.get("von") == person and k.get("status") == "versiegelt") >= MAX_OFFEN_JE_PERSON:
            return {"meldung": _t("Du hast schon %d versiegelte Zeitkapseln, mehr gehen nicht.",
                                  "You already have %d sealed time capsules, no more are possible.")
                    % MAX_OFFEN_JE_PERSON}
        k = {"nr": max([int(x.get("nr") or 0) for x in liste] + [0]) + 1, "von": person, "fuer": fuer, "text": text,
             "angelegt": ctx.jetzt(), "faellig": faellig.isoformat(), "anlass": anlass,
             "ausloeser": b.get("ausloeser") if isinstance(b.get("ausloeser"), dict) else {"datum": faellig.isoformat()},
             "kanal": kanal, "raum": raum, "ueberraschung": b.get("ueberraschung") is True, "status": "versiegelt",
             "zustellung": {}}
        liste.append(k)
        _speichern(ctx, liste)
    ctx.log("Zeitkapsel Nr. %d angelegt (von %s für %s, fällig %s)" % (k["nr"], person, fuer, k["faellig"]))
    m = _t("Versiegelt: Zeitkapsel Nr. %d für %s. Sie öffnet sich am %s%s zwischen %d und %d Uhr, %s. Den Inhalt gebe "
           "ich vorher nicht heraus, auch dir nicht.",
           "Sealed: time capsule no. %d for %s. It opens on %s%s between %d:00 and %d:00, %s. I won't reveal the "
           "content before then, not even to you.") % (
        k["nr"], _fuer_wen(ctx, k, person), _lang(faellig), " (%s)" % anlass if anlass else "", FENSTER[0], FENSTER[1],
        _weg_text(ctx, k))
    if k["ueberraschung"] and fuer != person:
        m += _t(" %s sieht vorher nicht, dass es sie gibt.", " %s won't see beforehand that it exists.") \
            % ctx.person_name(fuer)
    return {"meldung": m, "nr": k["nr"], "faellig": k["faellig"]}


def _liste(ctx, person):
    with _sperre:
        alle = _laden(ctx)
    eigene = [k for k in alle if k.get("von") == person and k.get("status") == "versiegelt"]
    fuer_mich = [k for k in alle if k.get("fuer") == person and k.get("von") != person
                 and k.get("status") == "versiegelt" and not k.get("ueberraschung")]
    offen = [k for k in alle if k.get("status") == "geoeffnet" and person in (k.get("von"), k.get("fuer"))]
    zeilen = []
    if eigene:
        zeilen.append(_t("Von dir versiegelt (%d):", "Sealed by you (%d):") % len(eigene))
        zeilen += ["- " + _eckdaten(ctx, k, person) for k in sorted(eigene, key=lambda k: k["faellig"])]
    if fuer_mich:
        zeilen.append(_t("Für dich versiegelt (%d):", "Sealed for you (%d):") % len(fuer_mich))
        zeilen += ["- " + _eckdaten(ctx, k, person) for k in sorted(fuer_mich, key=lambda k: k["faellig"])]
    if offen:
        zeilen.append(_t("Geöffnet im Archiv: %d.", "Opened, in the archive: %d.") % len(offen))
    if not zeilen:
        return {"meldung": _t("Keine Zeitkapseln.", "No time capsules."), "kapseln": []}
    meta = [{"nr": k["nr"], "von": k["von"], "fuer": k["fuer"], "angelegt": _tag(k["angelegt"]).isoformat(),
             "faellig": k["faellig"], "laenge": len(k.get("text") or ""), "status": k["status"]}
            for k in eigene + fuer_mich]
    return {"meldung": "\n".join(zeilen) + _t("\nDen Inhalt versiegelter Kapseln gebe ich vor dem Tag nicht heraus.",
                                              "\nI won't reveal the content of sealed capsules before the day."),
            "kapseln": meta}


def _sichtbar(k, person):
    """Darf person von dieser Kapsel wissen (Absender, oder Empfänger ohne Überraschung bzw. nach dem Öffnen)?"""
    if k.get("von") == person:
        return True
    return k.get("fuer") == person and (k.get("status") == "geoeffnet" or not k.get("ueberraschung"))


def _archiv(ctx, person, nr):
    with _sperre:
        alle = _laden(ctx)
    nr = _ganzzahl(nr)
    if nr is not None:
        k = next((x for x in alle if x.get("nr") == nr and _sichtbar(x, person)), None)
        if not k:
            return {"meldung": _t("Eine Zeitkapsel Nr. %d finde ich nicht.",
                                  "I can't find a time capsule no. %d.") % nr}
        if k.get("status") != "geoeffnet":
            return {"meldung": _t("Zeitkapsel Nr. %d ist noch versiegelt und öffnet sich am %s. Vorher gebe ich den "
                                  "Inhalt nicht heraus.",
                                  "Time capsule no. %d is still sealed and opens on %s. I won't reveal the content "
                                  "before then.") % (nr, _kurz(_datum_lesen(k["faellig"])))}
        auswahl = [k]
    else:
        auswahl = sorted((x for x in alle if x.get("status") == "geoeffnet" and person in (x.get("von"), x.get("fuer"))),
                         key=lambda x: -float(x.get("geoeffnet_am") or 0))[:10]
    if not auswahl:
        return {"meldung": _t("Im Archiv liegt noch keine geöffnete Zeitkapsel.",
                              "There is no opened time capsule in the archive yet.")}
    teile = [_t("Zeitkapsel Nr. %d von %s für %s, versiegelt am %s, geöffnet am %s:\n„%s“",
                "Time capsule no. %d from %s for %s, sealed on %s, opened on %s:\n“%s”") % (
        k["nr"], ctx.person_name(k["von"]), ctx.person_name(k["fuer"]), _kurz(_tag(k["angelegt"])),
        _kurz(_tag(k.get("geoeffnet_am") or ctx.jetzt())), k["text"]) for k in auswahl]
    return {"meldung": "\n\n".join(teile)}


def _loeschen(ctx, person, nr):
    nr = _ganzzahl(nr)
    if nr is None:
        return {"meldung": _t("Welche Zeitkapsel? Nenn mir die Nummer (nr) aus der Liste.",
                              "Which time capsule? Tell me the number (nr) from the list.")}
    with _sperre:
        liste = _laden(ctx)
        k = next((x for x in liste if x.get("nr") == nr), None)
        if not k or not _sichtbar(k, person):
            return {"meldung": _t("Eine Zeitkapsel Nr. %d finde ich nicht.",
                                  "I can't find a time capsule no. %d.") % nr}
        if k.get("von") != person:
            return {"meldung": _t("Löschen kann nur, wer sie angelegt hat (%s).",
                                  "Only the person who created it can delete it (%s).") % ctx.person_name(k["von"])}
        liste = [x for x in liste if x.get("nr") != nr]
        _speichern(ctx, liste)
    ctx.log("Zeitkapsel Nr. %d gelöscht von %s" % (nr, person))
    return {"meldung": _t("Zeitkapsel Nr. %d für %s ist gelöscht.", "Time capsule no. %d for %s is deleted.") % (
        nr, _fuer_wen(ctx, k, person))}


# ---------------------------------------------------------------------------------------------- Zustellen

def _wege(k):
    w = {"durchsage": ["durchsage"], "push": ["push"], "beides": ["durchsage", "push"]}.get(k.get("kanal"), ["push"])
    if k.get("ersatz_push") and "push" not in w:
        w = w + ["push"]
    return w


def _erledigt(z):
    """Ein Weg gilt als erledigt, wenn er ankam oder begonnen, aber nie abgeschlossen wurde (Absturz)."""
    return bool(z) and (z.get("ok") is True or ("start" in z and "ok" not in z))


def rahmen(ctx, k):
    """Gesprochener Anfang: „Eine Zeitkapsel von Alex, versiegelt am 6. November 2026, für Kim.“"""
    von = ctx.person_name(k["von"])
    versiegelt = _mittel(_tag(k["angelegt"]))
    if k["fuer"] == k["von"]:
        return _t("Eine Zeitkapsel von %s an sich selbst, versiegelt am %s.",
                  "A time capsule from %s to themselves, sealed on %s.") % (von, versiegelt)
    return _t("Eine Zeitkapsel von %s, versiegelt am %s, für %s.", "A time capsule from %s, sealed on %s, for %s.") % (
        von, versiegelt, ctx.person_name(k["fuer"]))


def _senden(ctx, k, weg):
    """-> (ok, fehler)"""
    try:
        if weg == "durchsage":
            r = ctx.durchsage(k.get("raum") or "ueberall", rahmen(ctx, k) + " " + k["text"])
            ok = bool(r) and str(r).strip().lower() not in NICHT_GESPIELT
            return ok, "" if ok else "Durchsage nicht abgespielt (%s)" % r
        titel = (_t("Zeitkapsel von dir selbst", "Time capsule from yourself") if k["fuer"] == k["von"]
                 else _t("Zeitkapsel von %s", "Time capsule from %s") % ctx.person_name(k["von"]))
        ok = bool(ctx.push(k["fuer"], titel, _t("Versiegelt am %s%s.\n\n%s", "Sealed on %s%s.\n\n%s") % (
            _mittel(_tag(k["angelegt"])), _anlass_text(k), k["text"]), tag="zeitkapsel"))
        return ok, "" if ok else "Push nicht zugestellt"
    except Exception as x:
        return False, ("%s: %s" % (type(x).__name__, x))[:200]


def _zustellen(ctx, nr, jetzt):
    k = _aendern(ctx, nr, lambda x: x.setdefault("erster_versuch", jetzt))
    if k is None:
        return
    for weg in _wege(k):
        z = (k.get("zustellung") or {}).get(weg) or {}
        if _erledigt(z):
            if "ok" not in z and not z.get("unklar_vermerkt"):
                ctx.log("Zeitkapsel Nr. %d: %s war begonnen, aber ohne Ergebnis; gilt als zugestellt" % (nr, weg))
                k = _aendern(ctx, nr, lambda x, w=weg: x["zustellung"][w].__setitem__("unklar_vermerkt", True)) or k
            continue

        def beginnen(x, w=weg):
            x.setdefault("zustellung", {})[w] = {"start": jetzt}
        if _aendern(ctx, nr, beginnen) is None:
            return                                       # inzwischen gelöscht
        ok, fehler = _senden(ctx, k, weg)

        def ergebnis(x, w=weg, ok=ok, fehler=fehler):
            x.setdefault("zustellung", {})[w] = {"start": jetzt, "ok": ok, "zeit": ctx.jetzt(), "fehler": fehler}
        k = _aendern(ctx, nr, ergebnis)
        if k is None:
            return
        if not ok:
            ctx.log("Zeitkapsel Nr. %d: %s ging nicht (%s)" % (nr, weg, fehler))

    def abschluss(x):
        wege = _wege(x)
        zs = x.get("zustellung") or {}
        erledigt = [w for w in wege if _erledigt(zs.get(w))]
        if len(erledigt) == len(wege):
            x["status"], x["geoeffnet_am"] = "geoeffnet", jetzt
            return
        x["naechster_versuch"] = jetzt + WIEDERHOLEN_S
        if jetzt - float(x.get("erster_versuch") or jetzt) >= ERSATZ_NACH_S:
            if erledigt:
                x["status"], x["geoeffnet_am"], x["teilweise"] = "geoeffnet", jetzt, True
            elif "push" not in wege:
                x["ersatz_push"], x["naechster_versuch"] = True, 0
    k = _aendern(ctx, nr, abschluss)
    if k and k.get("status") == "geoeffnet":
        ctx.log("Zeitkapsel Nr. %d geöffnet (%s)" % (nr, ", ".join(
            w for w in _wege(k) if (k.get("zustellung") or {}).get(w, {}).get("ok"))))


def runde(ctx):
    """Alle TAKT_S aus dem Hintergrund: fällige Kapseln im Fenster zustellen. Wirft nie."""
    if not _runde_sperre.acquire(blocking=False):
        return
    try:
        jetzt = ctx.jetzt()
        lt = time.localtime(jetzt)
        if not FENSTER[0] <= lt.tm_hour < FENSTER[1]:
            return
        heute = dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday).isoformat()
        with _sperre:
            faellige = [k for k in _laden(ctx) if k.get("status") == "versiegelt"
                        and str(k.get("faellig") or "9999") <= heute
                        and float(k.get("naechster_versuch") or 0) <= jetzt]
        faellige.sort(key=lambda k: (k.get("faellig"), k.get("angelegt") or 0))
        for k in faellige[:JE_RUNDE]:
            try:
                _zustellen(ctx, k.get("nr"), jetzt)
            except Exception as x:
                ctx.log("Zeitkapsel Nr. %s:" % k.get("nr"), type(x).__name__, x)
    except Exception as x:
        try:
            ctx.log("Zeitkapsel-Runde:", type(x).__name__, x)
        except Exception:
            pass
    finally:
        _runde_sperre.release()


WERKZEUG_DE = {
    "beschreibung": (
        "Zeitkapsel: eine Botschaft an die Zukunft, versiegelt bis zu einem Tag oder Lebensereignis. aktion neu: fuer "
        "(Name oder „mich“), text (die Botschaft), ausloeser {datum: JJJJ-MM-TT} oder {in_jahren: N} oder {alter: N, "
        "geburtstag: JJJJ-MM-TT}, kanal durchsage|push|beides (Standard beides), raum optional (Raum-ID oder "
        "ueberall), ueberraschung true, wenn der Empfänger vorher nicht sehen soll, dass es sie gibt. liste: nur "
        "Eckdaten, nie den Inhalt. archiv: geöffnete Kapseln mit Inhalt (nr optional). loeschen: nr, nur wer sie "
        "angelegt hat. Den Inhalt einer versiegelten Kapsel gibt es vor dem Tag nie, auch nicht für den Absender; "
        "wiederhole den Text beim Anlegen nicht und merk ihn dir nicht. Zugestellt wird am Tag zwischen 9 und 20 Uhr."),
    "schema": {"type": "object", "properties": {
        "aktion": {"type": "string", "enum": list(AKTIONEN)},
        "fuer": {"type": "string", "description": "Empfänger: Name, Kennung oder „mich“"},
        "text": {"type": "string", "description": "die Botschaft (höchstens 1500 Zeichen)"},
        "ausloeser": {"type": "object", "properties": {
            "datum": {"type": "string", "description": "JJJJ-MM-TT"},
            "in_jahren": {"type": "integer"},
            "alter": {"type": "integer", "description": "mit geburtstag"},
            "geburtstag": {"type": "string", "description": "JJJJ-MM-TT"}}},
        "kanal": {"type": "string", "enum": list(KANAELE)},
        "raum": {"type": "string"},
        "ueberraschung": {"type": "boolean"},
        "nr": {"type": "integer", "description": "archiv, loeschen"}},
        "required": ["aktion"]},
}
WERKZEUG_EN = {
    "beschreibung": (
        "Time capsule: a message to the future, sealed until a day or a life event. aktion neu: fuer (name or "
        "\"me\"), text (the message), ausloeser {datum: YYYY-MM-DD} or {in_jahren: N} or {alter: N, geburtstag: "
        "YYYY-MM-DD}, kanal durchsage (announcement)|push|beides (both, the default), raum optional (room id or "
        "ueberall for everywhere), ueberraschung true if the recipient should not see beforehand that it exists. "
        "liste: only key facts, never the content. archiv: opened capsules with their content (nr optional). "
        "loeschen: nr, only the person who created it. The content of a sealed capsule is never available before the "
        "day, not even to the sender; do not repeat the text when creating it and do not memorise it. Delivery is on "
        "the day between 9:00 and 20:00. Answer the person in English."),
    "schema": {"type": "object", "properties": {
        "aktion": {"type": "string", "enum": list(AKTIONEN)},
        "fuer": {"type": "string", "description": "Recipient: name, id or \"me\""},
        "text": {"type": "string", "description": "the message (at most 1500 characters)"},
        "ausloeser": {"type": "object", "properties": {
            "datum": {"type": "string", "description": "YYYY-MM-DD"},
            "in_jahren": {"type": "integer"},
            "alter": {"type": "integer", "description": "with geburtstag"},
            "geburtstag": {"type": "string", "description": "YYYY-MM-DD"}}},
        "kanal": {"type": "string", "enum": list(KANAELE)},
        "raum": {"type": "string"},
        "ueberraschung": {"type": "boolean"},
        "nr": {"type": "integer", "description": "archiv, loeschen"}},
        "required": ["aktion"]},
}
WERKZEUG = copy.deepcopy(WERKZEUG_DE)          # setze_sprache tauscht den Inhalt (gleiches Objekt)
# archiv gibt Text wieder, den eine andere Person geschrieben hat: lesend, aber Quelle (Einbau-Zettel).
FREMDTEXT = {"art": "ziel", "nur_lesen": ("aktion", "liste", ["liste", "archiv"]),
             "quelle_aktionen": ("aktion", "liste", ["archiv"])}


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache
    neu = copy.deepcopy(WERKZEUG_EN if sprache == "en" else WERKZEUG_DE)
    WERKZEUG.clear()
    WERKZEUG.update(neu)
