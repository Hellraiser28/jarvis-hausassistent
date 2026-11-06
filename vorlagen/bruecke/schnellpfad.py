"""Schnellpfad ohne Gehirn (seit 0.7).

Vorbild: Heliox-OS ("Quick answers": eingebaute Befehle ohne Modellaufruf) und AnaaySampat/jarvis (direkter Weg fuer
einfache Fragen). Uhrzeit, Datum, Wochentag, "wie viele Tage bis ...", Rechnen, Einheiten umrechnen, Wuerfel, Muenze und
Zufallszahl beantwortet die Bruecke selbst: keine Kosten, Antwort in Millisekunden.

Grundsatz: nur, wenn die GANZE Aeusserung einem Muster entspricht. Alles andere, auch "wie spaet ist es in Tokio" oder
"rechne mir aus, ob sich das lohnt", geht wie bisher ans Gehirn. Kein eval: Zahlen und Rechenzeichen werden einzeln
erkannt.

Zweisprachig (seit 0.7): Die Bruecke setzt die Sprache beim Start (setze_sprache, aus antworten.json "sprache").
Auf Deutsch erkennt der Schnellpfad deutsche Aeusserungen ("wie spaet ist es", "was ist 17 mal 23", "wie viele Tage
bis Weihnachten"), auf Englisch englische ("what time is it", "what's 17 times 23", "how many days until Christmas").
Die Antwort kommt in der eingestellten Sprache, eine Aeusserung in der anderen Sprache geht ans Gehirn.
Zahlen je Sprache: Deutsch mit Dezimalkomma und Tausenderpunkt ("12,5", "1.000"), Englisch mit Dezimalpunkt und
Tausenderkomma ("12.5", "1,000"); ein Komma, das im Englischen kein Tausendertrenner ist ("12,5"), geht ans Gehirn.
Uhrzeit: Deutsch "Es ist 14:32 Uhr.", Englisch "It's 2:32 PM." (UHR_12H_EN = False: "It's 14:32.").
Feste je Sprache: Weihnachten ist im Deutschen der 24.12., Christmas im Englischen der 25.12. Reine Zahlendaten wie
"12/24" versteht das Englische bewusst nicht (Monat/Tag oder Tag/Monat?); "December 24", "24th of December" und
"2026-12-24" schon.
"""
import datetime as dt
import math
import random
import re

# Sprache der Antworten (seit 0.7). Die Bruecke setzt sie beim Start aus der Einrichtung (antworten.json "sprache"),
# wie bei verhalten.py und szenen.py.
SPRACHE = "de"
UHR_12H_EN = True          # Englisch: Uhrzeit mit AM/PM; False: 24 Stunden


def setze_sprache(sprache):
    global SPRACHE
    if sprache not in ("de", "en"):
        raise ValueError("sprache ist de oder en")
    SPRACHE = sprache


def _t(de, en):
    return en if SPRACHE == "en" else de


WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember"]
MONAT_NR = {m.lower(): i + 1 for i, m in enumerate(MONATE)}
MONAT_NR.update({"maerz": 3, "jan": 1, "feb": 2, "mär": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
                 "okt": 10, "nov": 11, "dez": 12})
FESTE = {"weihnachten": (12, 24, "Weihnachten"), "heiligabend": (12, 24, "Heiligabend"),
         "silvester": (12, 31, "Silvester"), "neujahr": (1, 1, "Neujahr"), "halloween": (10, 31, "Halloween"),
         "nikolaus": (12, 6, "Nikolaus"), "valentinstag": (2, 14, "Valentinstag")}

ZAHL = r"-?\d+(?:[.,]\d+)?"
ANREDE = re.compile(r"^(?:(?:hey|hallo|okay|ok|hi)\s+)?jarvis[\s,:!.]*", re.I)
HOEFLICH = re.compile(r"[\s,]*(?:bitte|doch|eigentlich|gerade|jetzt|denn)\b|[\s,]*\bmal\b(?!\s*-?\d)", re.I)


def _normal(text):
    t = ANREDE.sub("", str(text or "").strip())
    t = re.sub(r"[?!.。]+$", "", t.strip()).strip()
    t = re.sub(r"\s+", " ", t).lower()
    return t


def _ohne_fuellwoerter(t):
    return re.sub(r"\s+", " ", HOEFLICH.sub("", t)).strip()


def _zahl(s):
    s = s.replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):        # 1.000 = tausend
        s = s.replace(".", "")
    return float(s)


def zahl_text(x, stellen=6):
    """Ohne nutzlose Nullen. Deutsch: Komma als Dezimalzeichen, Tausender mit Punkt; Englisch: Punkt und Komma."""
    x = float(x)
    if math.isinf(x) or math.isnan(x):
        return _t("unendlich", "infinity")
    r = round(x, stellen)
    vz = "-" if r < 0 else ""
    ganz, _, rest = ("%.*f" % (stellen, abs(r))).partition(".")
    rest = rest.rstrip("0")
    if int(ganz) == 0 and not rest:
        return "0"
    if SPRACHE == "en":
        return vz + "{:,}".format(int(ganz)) + ("." + rest if rest else "")
    return vz + "{:,}".format(int(ganz)).replace(",", ".") + ("," + rest if rest else "")


# ---------------------------------------------------------------- Uhrzeit und Datum

UHRZEIT = re.compile(r"(?:wie spät ist es|wie viel uhr (?:ist es|haben wir)|wieviel uhr (?:ist es|haben wir)|"
                     r"(?:sag mir )?(?:die )?uhrzeit|was ist die uhrzeit|wie spät haben wir)")
HEUTE = re.compile(r"(?:welcher (?:wochen)?tag ist heute|welchen (?:wochen)?tag haben wir(?: heute)?|"
                   r"der wievielte ist heute|den wievielten haben wir(?: heute)?|welches datum (?:ist|haben wir)(?: heute)?|"
                   r"was ist heute für ein (?:tag|datum|wochentag)|(?:das )?(?:heutige )?datum|was für ein tag ist heute)")
MORGEN = re.compile(r"(?:welcher (?:wochen)?tag ist morgen|der wievielte ist morgen|was ist morgen für ein (?:tag|datum))")


def _datum_lang(d, mit_jahr=True):
    return "%s, der %d. %s%s" % (WOCHENTAGE[d.weekday()], d.day, MONATE[d.month - 1], " %d" % d.year if mit_jahr else "")


def _datum_aus(s, heute):
    """'24.12.', '24.12.2026', '24. dezember', '24. dezember 2027' -> date (naechstes Vorkommen ohne Jahr)."""
    s = s.strip().rstrip(".")
    m = re.fullmatch(r"(\d{1,2})\.\s*(\d{1,2})\.?\s*(\d{2,4})?", s)
    if not m:
        m2 = re.fullmatch(r"(\d{1,2})\.?\s*([a-zäö]+)\.?\s*(\d{4})?", s)
        if not m2 or m2.group(2) not in MONAT_NR:
            return None
        tag, monat, jahr = int(m2.group(1)), MONAT_NR[m2.group(2)], m2.group(3)
    else:
        tag, monat, jahr = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        if jahr:
            j = int(jahr)
            j = j + 2000 if j < 100 else j
            return dt.date(j, monat, tag)
        d = dt.date(heute.year, monat, tag)
        return d if d >= heute else dt.date(heute.year + 1, monat, tag)
    except ValueError:
        return None


def _ziel_datum(ziel, heute):
    """(Datum, Name) fuer 'weihnachten', 'den 24.12.', 'zum 3. januar' ..."""
    z = re.sub(r"^(?:zu[mr]?|den|dem|an|am)\s+", "", ziel.strip())
    z = re.sub(r"^(?:zu[mr]?|den|dem)\s+", "", z)
    if z in FESTE:
        monat, tag, name = FESTE[z]
        d = dt.date(heute.year, monat, tag)
        if d < heute:
            d = dt.date(heute.year + 1, monat, tag)
        return d, name
    d = _datum_aus(z, heute)
    return (d, "zum %d. %s" % (d.day, MONATE[d.month - 1])) if d else (None, None)


TAGE_BIS = re.compile(r"wie ?viele tage (?:sind es |ist es |noch )*(?:noch )?bis (?P<ziel>.+)")
WOCHENTAG_VON = re.compile(r"(?:welcher wochentag ist|was für ein (?:wochen)?tag ist|auf welchen (?:wochen)?tag fällt)"
                           r" (?:der |die )?(?P<d>.+)")


# ---------------------------------------------------------------- Rechnen

# Kein ":" (10:30 ist eine Uhrzeit) und kein "und" (zu vieldeutig); "-" nur zwischen Ziffern
OPS = {"plus": "+", "+": "+", "minus": "-", "-": "-", "weniger": "-", "mal": "*", "x": "*", "*": "*",
       "×": "*", "geteilt durch": "/", "durch": "/", "/": "/", "hoch": "^", "^": "^"}
OP_RX = r"(?:geteilt durch|plus|minus|weniger|mal|durch|hoch|[x×*/^+-])"
RECHNEN = re.compile(r"(?:(?:was|wie ?viel) (?:ist|sind|ergibt|ergeben|macht)|was ergibt|rechne|berechne|"
                     r"was gibt)?\s*(?P<a>%s)\s*(?P<op>%s)\s*(?P<b>%s)\s*(?:ist|sind|ergibt|gleich|=)?" % (ZAHL, OP_RX, ZAHL))
PROZENT = re.compile(r"(?:(?:was|wie ?viel) (?:ist|sind|macht)|rechne|berechne)?\s*(?P<p>%s)\s*(?:prozent|%%) (?:von|aus) "
                     r"(?P<n>%s)" % (ZAHL, ZAHL))
WURZEL = re.compile(r"(?:(?:was|wie ?viel) ist (?:die )?)?(?:quadrat)?wurzel (?:aus|von) (?P<n>%s)" % ZAHL)


def _rechnen(a, op, b, ops=None, zahl=None):
    ops, zahl = ops or OPS, zahl or _zahl
    a, b = zahl(a), zahl(b)
    o = ops[op]
    if o == "+":
        return a + b
    if o == "-":
        return a - b
    if o == "*":
        return a * b
    if o == "/":
        if b == 0:
            raise ZeroDivisionError
        return a / b
    if abs(b) > 100 or (abs(a) > 1e6 and b > 3):
        raise OverflowError
    return a ** b


# ---------------------------------------------------------------- Einheiten

# Name -> (Groesse, Faktor zur Grundeinheit, Anzeige Einzahl, Anzeige Mehrzahl)
EINHEITEN = {
    "km": ("laenge", 1000.0, "Kilometer", "Kilometer"), "kilometer": ("laenge", 1000.0, "Kilometer", "Kilometer"),
    "m": ("laenge", 1.0, "Meter", "Meter"), "meter": ("laenge", 1.0, "Meter", "Meter"),
    "cm": ("laenge", 0.01, "Zentimeter", "Zentimeter"), "zentimeter": ("laenge", 0.01, "Zentimeter", "Zentimeter"),
    "mm": ("laenge", 0.001, "Millimeter", "Millimeter"), "millimeter": ("laenge", 0.001, "Millimeter", "Millimeter"),
    "meile": ("laenge", 1609.344, "Meile", "Meilen"), "meilen": ("laenge", 1609.344, "Meile", "Meilen"),
    "zoll": ("laenge", 0.0254, "Zoll", "Zoll"), "inch": ("laenge", 0.0254, "Zoll", "Zoll"),
    "fuß": ("laenge", 0.3048, "Fuß", "Fuß"), "fuss": ("laenge", 0.3048, "Fuß", "Fuß"),
    "kg": ("masse", 1.0, "Kilogramm", "Kilogramm"), "kilo": ("masse", 1.0, "Kilogramm", "Kilogramm"),
    "kilogramm": ("masse", 1.0, "Kilogramm", "Kilogramm"), "g": ("masse", 0.001, "Gramm", "Gramm"),
    "gramm": ("masse", 0.001, "Gramm", "Gramm"), "lbs": ("masse", 0.45359237, "Pound", "Pounds"),
    "pound": ("masse", 0.45359237, "Pound", "Pounds"), "pounds": ("masse", 0.45359237, "Pound", "Pounds"),
    "unze": ("masse", 0.028349523125, "Unze", "Unzen"), "unzen": ("masse", 0.028349523125, "Unze", "Unzen"),
    "liter": ("volumen", 1.0, "Liter", "Liter"), "l": ("volumen", 1.0, "Liter", "Liter"),
    "ml": ("volumen", 0.001, "Milliliter", "Milliliter"), "milliliter": ("volumen", 0.001, "Milliliter", "Milliliter"),
    "gallone": ("volumen", 3.785411784, "Gallone", "Gallonen"), "gallonen": ("volumen", 3.785411784, "Gallone", "Gallonen"),
    "km/h": ("tempo", 1 / 3.6, "km/h", "km/h"), "mph": ("tempo", 0.44704, "mph", "mph"),
    "grad celsius": ("temp", "c", "Grad Celsius", "Grad Celsius"), "celsius": ("temp", "c", "Grad Celsius", "Grad Celsius"),
    "°c": ("temp", "c", "Grad Celsius", "Grad Celsius"),
    "grad fahrenheit": ("temp", "f", "Grad Fahrenheit", "Grad Fahrenheit"),
    "fahrenheit": ("temp", "f", "Grad Fahrenheit", "Grad Fahrenheit"), "°f": ("temp", "f", "Grad Fahrenheit", "Grad Fahrenheit"),
}
_E_RX = "|".join(sorted((re.escape(k) for k in EINHEITEN), key=len, reverse=True))
UMRECHNEN = re.compile(r"(?:(?:wie ?viele?|was) (?:sind|ist|macht|ergeben)|rechne|wandle|umrechnen)?\s*(?P<n>%s)\s*"
                       r"(?P<von>%s) (?:in|zu|nach|sind wie ?viele?) (?P<nach>%s)(?: um| sind das| umrechnen| um\b)?"
                       % (ZAHL, _E_RX, _E_RX))


def _umrechnen_wert(n, von, nach, einheiten):
    """-> (Ergebnis, Stellen, Einheit von, Einheit nach) oder None (andere Groesse oder gleiche Einheit)."""
    gv, fv, ev, mv = einheiten[von]
    gn, fn, en, mn = einheiten[nach]
    if gv != gn or von == nach:
        return None
    if gv == "temp":
        c = n if fv == "c" else (n - 32) * 5 / 9
        r = c if fn == "c" else c * 9 / 5 + 32
    else:
        r = n * fv / fn
    stellen = 2 if abs(r) >= 1 else 4
    a = ev if abs(n) == 1 else mv
    b = en if abs(round(r, stellen)) == 1 else mn
    return r, stellen, a, b


def _umrechnen(n, von, nach):
    w = _umrechnen_wert(n, von, nach, EINHEITEN)
    if w is None:
        return None
    r, stellen, a, b = w
    return "%s %s %s %s %s." % (zahl_text(n), a, "ist" if abs(n) == 1 else "sind", zahl_text(r, stellen), b)


# ---------------------------------------------------------------- Zufall

ZAHLWORT = {"einen": 1, "ein": 1, "nen": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5}
WUERFEL = re.compile(r"(?:wirf|roll|würfel|würfle) (?P<n>einen|ein|nen|zwei|drei|vier|fünf|\d) würfel|würfel|würfle")
MUENZE = re.compile(r"(?:wirf|werf|wirf mir) (?:eine |ne )?münze|kopf oder zahl")
ZUFALL = re.compile(r"(?:nenn mir |gib mir |sag mir )?(?:eine )?zufallszahl (?:zwischen|von) (?P<a>-?\d+) (?:und|bis) (?P<b>-?\d+)")


# ---------------------------------------------------------------- Englisch (seit 0.7)
# Gleicher Aufbau wie oben, eigene Muster, Woerter und Zahlformate. Aktionsnamen gibt es hier keine; die Antworten
# entstehen in _antwort_en.

WOCHENTAGE_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONATE_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
MONAT_NR_EN = {m.lower(): i + 1 for i, m in enumerate(MONATE_EN)}
MONAT_NR_EN.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
                    "oct": 10, "nov": 11, "dec": 12})
_NEUJAHR = (1, 1, "New Year's Day")
_SILVESTER = (12, 31, "New Year's Eve")
_VALENTIN = (2, 14, "Valentine's Day")
FESTE_EN = {"christmas": (12, 25, "Christmas"), "christmas day": (12, 25, "Christmas Day"), "xmas": (12, 25, "Christmas"),
            "christmas eve": (12, 24, "Christmas Eve"), "new year's eve": _SILVESTER, "new years eve": _SILVESTER,
            "new year": _NEUJAHR, "new year's": _NEUJAHR, "new years": _NEUJAHR, "new year's day": _NEUJAHR,
            "new years day": _NEUJAHR, "halloween": (10, 31, "Halloween"), "valentine's day": _VALENTIN,
            "valentines day": _VALENTIN, "valentine's": _VALENTIN}

ANREDE_EN = re.compile(r"^(?:(?:hey|hello|hi|okay|ok)\s+)?jarvis[\s,:!.]*", re.I)
HOEFLICH_EN = re.compile(r"[\s,]*\b(?:please|right now|now|currently|exactly|actually|just)\b", re.I)


def _normal_en(text):
    t = ANREDE_EN.sub("", str(text or "").strip().replace("’", "'").replace("‘", "'"))
    t = re.sub(r"[?!.。]+$", "", t.strip()).strip()
    t = re.sub(r"\s+", " ", t).lower()
    return t


def _ohne_fuellwoerter_en(t):
    return re.sub(r"\s+", " ", HOEFLICH_EN.sub("", t)).strip()


def _zahl_en(s):
    """Englisch: Punkt als Dezimalzeichen, Komma nur als Tausendertrenner (1,000). '12,5' -> ValueError (ans Gehirn)."""
    s = s.replace(" ", "")
    if "," in s:
        if not re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
            raise ValueError("Komma ohne Tausender")
        s = s.replace(",", "")
    return float(s)


_WAS_EN = r"(?:what|how much) (?:is|are)|what's|whats"
UHRZEIT_EN = re.compile(r"(?:what time is it|what time it is|what's the time|whats the time|what is the time|"
                        r"(?:tell me )?the time|time|(?:do you know|can you tell me|could you tell me) "
                        r"(?:the time|what time it is)|have you got the time)")
HEUTE_EN = re.compile(r"(?:what day is (?:it|today)(?: today)?|(?:what's|whats|what is) (?:the date|today's date|"
                      r"todays date|today)(?: today)?|which day is (?:it|today)|what date is it(?: today)?|"
                      r"what day of the week is it(?: today)?|(?:today's|todays|the) date|date)")
MORGEN_EN = re.compile(r"(?:what day is (?:it )?tomorrow|(?:what's|whats|what is) (?:the date )?tomorrow|"
                       r"(?:what's|whats|what is) tomorrow's date|what date is (?:it )?tomorrow|which day is tomorrow|"
                       r"what day of the week is (?:it )?tomorrow)")
TAGE_BIS_EN = re.compile(r"(?:how many (?:more )?days (?:are there |is it |are left |left |remain |remaining |"
                         r"do we have |to go )*(?:until|till|til|to|before)|how long (?:is it )?(?:until|till|til))"
                         r" (?P<ziel>.+)")
WOCHENTAG_VON_EN = re.compile(r"(?:(?:what|which) day(?: of the week)? (?:is|was|will be)|what weekday (?:is|was)|"
                              r"on (?:what|which) day (?:is|was)|(?:what|which) day(?: of the week)? does)"
                              r" (?P<d>.+?)(?: fall on| fall| land on)?")

OPS_EN = {"plus": "+", "+": "+", "minus": "-", "-": "-", "times": "*", "multiplied by": "*", "x": "*", "*": "*",
          "×": "*", "divided by": "/", "/": "/", "to the power of": "^", "^": "^"}
OP_RX_EN = r"(?:multiplied by|divided by|to the power of|plus|minus|times|[x×*/^+-])"
RECHNEN_EN = re.compile(r"(?:%s|what does|what do|calculate|compute|work out)?\s*(?P<a>%s)\s*(?P<op>%s)\s*(?P<b>%s)"
                        r"\s*(?:equals?|is|make|makes|=)?" % (_WAS_EN, ZAHL, OP_RX_EN, ZAHL))
PROZENT_EN = re.compile(r"(?:%s|calculate|compute)?\s*(?P<p>%s)\s*(?:percent|per cent|%%) of (?P<n>%s)"
                        % (_WAS_EN, ZAHL, ZAHL))
WURZEL_EN = re.compile(r"(?:(?:%s) )?(?:the )?(?:square )?root of (?P<n>%s)" % (_WAS_EN, ZAHL))

_L, _G, _V = "laenge", "masse", "volumen"
EINHEITEN_EN = {}
for _namen, _eintrag in (
        (("km", "kilometer", "kilometers", "kilometre", "kilometres"), (_L, 1000.0, "kilometer", "kilometers")),
        (("m", "meter", "meters", "metre", "metres"), (_L, 1.0, "meter", "meters")),
        (("cm", "centimeter", "centimeters", "centimetre", "centimetres"), (_L, 0.01, "centimeter", "centimeters")),
        (("mm", "millimeter", "millimeters", "millimetre", "millimetres"), (_L, 0.001, "millimeter", "millimeters")),
        (("mi", "mile", "miles"), (_L, 1609.344, "mile", "miles")),
        (("inch", "inches"), (_L, 0.0254, "inch", "inches")),
        (("ft", "foot", "feet"), (_L, 0.3048, "foot", "feet")),
        (("yd", "yard", "yards"), (_L, 0.9144, "yard", "yards")),
        (("kg", "kilo", "kilos", "kilogram", "kilograms", "kilogramme", "kilogrammes"), (_G, 1.0, "kilogram", "kilograms")),
        (("g", "gram", "grams", "gramme", "grammes"), (_G, 0.001, "gram", "grams")),
        (("lb", "lbs", "pound", "pounds"), (_G, 0.45359237, "pound", "pounds")),
        (("oz", "ounce", "ounces"), (_G, 0.028349523125, "ounce", "ounces")),
        (("l", "liter", "liters", "litre", "litres"), (_V, 1.0, "liter", "liters")),
        (("ml", "milliliter", "milliliters", "millilitre", "millilitres"), (_V, 0.001, "milliliter", "milliliters")),
        (("gal", "gallon", "gallons"), (_V, 3.785411784, "gallon", "gallons")),
        (("km/h", "kph", "kilometers per hour", "kilometres per hour"), ("tempo", 1 / 3.6, "km/h", "km/h")),
        (("mph", "miles per hour"), ("tempo", 0.44704, "mph", "mph")),
        (("celsius", "degree celsius", "degrees celsius", "°c"), ("temp", "c", "degree Celsius", "degrees Celsius")),
        (("fahrenheit", "degree fahrenheit", "degrees fahrenheit", "°f"),
         ("temp", "f", "degree Fahrenheit", "degrees Fahrenheit"))):
    for _n in _namen:
        EINHEITEN_EN[_n] = _eintrag
del _namen, _eintrag, _n
_E_RX_EN = "|".join(sorted((re.escape(k) for k in EINHEITEN_EN), key=len, reverse=True))
UMRECHNEN_EN = re.compile(r"(?:%s|how many|convert)?\s*(?P<n>%s)\s*(?P<von>%s) (?:in|to|into) (?P<nach>%s)"
                          % (_WAS_EN, ZAHL, _E_RX_EN, _E_RX_EN))
UMRECHNEN2_EN = re.compile(r"how many (?P<nach>%s) (?:are|is) (?:there )?(?:in )?(?P<n>%s)\s*(?P<von>%s)"
                           % (_E_RX_EN, ZAHL, _E_RX_EN))

ZAHLWORT_EN = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
WUERFEL_EN = re.compile(r"(?:roll|throw|toss) (?:me )?(?P<n>a|an|one|two|three|four|five|\d) (?:die|dice)|"
                        r"(?:roll|throw) (?:me )?(?:the |a )?(?:die|dice)|dice roll")
MUENZE_EN = re.compile(r"(?:flip|toss|throw) (?:me )?(?:a |the )?coin|heads or tails|coin (?:flip|toss)")
ZUFALL_EN = re.compile(r"(?:(?:give|tell) me |pick |say )?(?:a )?random number (?:between|from) (?P<a>-?\d+) "
                       r"(?:and|to) (?P<b>-?\d+)")


def _uhr_en(jetzt):
    if not UHR_12H_EN:
        return "It's %d:%02d." % (jetzt.hour, jetzt.minute)
    return "It's %d:%02d %s." % (jetzt.hour % 12 or 12, jetzt.minute, "AM" if jetzt.hour < 12 else "PM")


def _datum_en(d, mit_jahr=True):
    return "%s %d%s" % (MONATE_EN[d.month - 1], d.day, ", %d" % d.year if mit_jahr else "")


def _datum_lang_en(d, mit_jahr=True):
    return "%s, %s" % (WOCHENTAGE_EN[d.weekday()], _datum_en(d, mit_jahr))


def _datum_aus_en(s, heute):
    """'december 24', 'dec 24th', 'december 24, 2027', '24 december', '24th of december 2027', '2026-12-24' -> date
    (naechstes Vorkommen ohne Jahr). Zahlendaten mit / oder . -> None (Monat/Tag oder Tag/Monat?)."""
    s = re.sub(r"\s+", " ", s.replace(",", " ")).strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        jahr, monat, tag = m.group(1), int(m.group(2)), int(m.group(3))
    else:
        m = (re.fullmatch(r"([a-z]+)\.? (\d{1,2})(?:st|nd|rd|th)?(?: (\d{4}))?", s)
             or re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)? (?:of )?([a-z]+)\.?(?: (\d{4}))?", s))
        if not m:
            return None
        a, b, jahr = m.group(1), m.group(2), m.group(3)
        wort, zahl = (a, b) if a.isalpha() else (b, a)
        if wort not in MONAT_NR_EN:
            return None
        monat, tag = MONAT_NR_EN[wort], int(zahl)
    try:
        if jahr:
            return dt.date(int(jahr), monat, tag)
        d = dt.date(heute.year, monat, tag)
        return d if d >= heute else dt.date(heute.year + 1, monat, tag)
    except ValueError:
        return None


def _ziel_datum_en(ziel, heute):
    """(Datum, Name ohne Jahr, Name mit Jahr) fuer 'christmas', 'december 24', 'the 3rd of january' ..."""
    z = ziel.strip()
    for _ in range(2):
        z = re.sub(r"^(?:the|on|to|until)\s+", "", z)
    if z in FESTE_EN:
        monat, tag, name = FESTE_EN[z]
        d = dt.date(heute.year, monat, tag)
        if d < heute:
            d = dt.date(heute.year + 1, monat, tag)
        return d, name, "%s %d" % (name, d.year)
    d = _datum_aus_en(z, heute)
    return (d, _datum_en(d, False), _datum_en(d)) if d else (None, None, None)


def _umrechnen_en(n, von, nach):
    w = _umrechnen_wert(n, von, nach, EINHEITEN_EN)
    if w is None:
        return None
    r, stellen, a, b = w
    return "%s %s is %s %s." % (zahl_text(n), a, zahl_text(r, stellen), b)


def _antwort_en(text, jetzt, zufall):
    t = _normal_en(text)
    if not t or len(t) > 80:
        return None
    k = _ohne_fuellwoerter_en(t)
    heute = jetzt.date()
    for kandidat in (t, k):
        if UHRZEIT_EN.fullmatch(kandidat):
            return _uhr_en(jetzt)
        if HEUTE_EN.fullmatch(kandidat):
            return "Today is %s." % _datum_lang_en(heute)
        if MORGEN_EN.fullmatch(kandidat):
            return "Tomorrow is %s." % _datum_lang_en(heute + dt.timedelta(days=1), mit_jahr=False)
        m = TAGE_BIS_EN.fullmatch(kandidat)
        if m:
            d, name, name_jahr = _ziel_datum_en(m.group("ziel"), heute)
            if d is None:
                return None
            n = (d - heute).days
            if n == 0:
                return "That's today!"
            if n == 1:
                return "Just one more sleep, %s is tomorrow." % name
            return "%d days until %s, which is a %s." % (n, name_jahr if d.year != heute.year else name,
                                                         WOCHENTAGE_EN[d.weekday()])
        m = WOCHENTAG_VON_EN.fullmatch(kandidat)
        if m:
            d, _, _ = _ziel_datum_en(m.group("d"), heute)
            if d is None:
                return None
            return "%s %s a %s." % (_datum_en(d), "was" if d < heute else "is", WOCHENTAGE_EN[d.weekday()])
        m = PROZENT_EN.fullmatch(kandidat)
        if m:
            p, n = _zahl_en(m.group("p")), _zahl_en(m.group("n"))
            return "%s percent of %s is %s." % (zahl_text(p), zahl_text(n), zahl_text(p * n / 100, 4))
        m = WURZEL_EN.fullmatch(kandidat)
        if m:
            n = _zahl_en(m.group("n"))
            if n < 0:
                return "I don't take square roots of negative numbers, that gets imaginary."
            return "The square root of %s is %s." % (zahl_text(n), zahl_text(math.sqrt(n), 4))
        m = UMRECHNEN_EN.fullmatch(kandidat) or UMRECHNEN2_EN.fullmatch(kandidat)
        if m:
            return _umrechnen_en(_zahl_en(m.group("n")), m.group("von"), m.group("nach"))
        m = RECHNEN_EN.fullmatch(kandidat)
        if m and (m.group("op") != "-" or re.search(r"\d\s+-\s+-?\d|\d-\d", kandidat)):
            try:
                r = _rechnen(m.group("a"), m.group("op"), m.group("b"), OPS_EN, _zahl_en)
            except ZeroDivisionError:
                return "Even I can't divide by zero."
            except OverflowError:
                return None
            wort = {"+": "plus", "-": "minus", "*": "times", "/": "divided by", "^": "to the power of"}[OPS_EN[m.group("op")]]
            return "%s %s %s is %s." % (zahl_text(_zahl_en(m.group("a"))), wort, zahl_text(_zahl_en(m.group("b"))),
                                        zahl_text(r, 4))
        m = WUERFEL_EN.fullmatch(kandidat)
        if m:
            n = m.group("n")
            n = int(n) if n and n.isdigit() else ZAHLWORT_EN.get(n or "a", 1)
            if not 1 <= n <= 5:
                return None
            w = [zufall.randint(1, 6) for _ in range(n)]
            if n == 1:
                return "You rolled a %d." % w[0]
            return "%s and %d, %d in total." % (", ".join(str(x) for x in w[:-1]), w[-1], sum(w))
        if MUENZE_EN.fullmatch(kandidat):
            return zufall.choice(["Heads.", "Tails."])
        m = ZUFALL_EN.fullmatch(kandidat)
        if m:
            a, b = sorted((int(m.group("a")), int(m.group("b"))))
            if b - a > 10 ** 9:
                return None
            return "%d." % zufall.randint(a, b)
    return None


# ---------------------------------------------------------------- Einstieg

def antwort(text, jetzt=None, zufall=None):
    """Antworttext in der eingestellten Sprache oder None (dann fragt die Bruecke wie bisher das Gehirn)."""
    jetzt = jetzt or dt.datetime.now()
    zufall = zufall or random.Random()
    if SPRACHE == "en":
        try:
            return _antwort_en(text, jetzt, zufall)
        except (ValueError, OverflowError):
            return None                      # z. B. "12,5" im Englischen: lieber das Gehirn fragen
    return _antwort_de(text, jetzt, zufall)


def _antwort_de(text, jetzt, zufall):
    t = _normal(text)
    if not t or len(t) > 80:
        return None
    k = _ohne_fuellwoerter(t)
    heute = jetzt.date()
    for kandidat in (t, k):
        if UHRZEIT.fullmatch(kandidat):
            return "Es ist %d:%02d Uhr." % (jetzt.hour, jetzt.minute)
        if HEUTE.fullmatch(kandidat):
            return "Heute ist %s." % _datum_lang(heute)
        if MORGEN.fullmatch(kandidat):
            return "Morgen ist %s." % _datum_lang(heute + dt.timedelta(days=1), mit_jahr=False)
        m = TAGE_BIS.fullmatch(kandidat)
        if m:
            d, name = _ziel_datum(m.group("ziel"), heute)
            if d is None:
                return None
            n = (d - heute).days
            if n == 0:
                return "Das ist heute!"
            if n == 1:
                return "Nur noch einmal schlafen, morgen ist %s." % (name if not name.startswith("zum ") else name[4:])
            jahr = " %d" % d.year if d.year != heute.year else ""
            return "Noch %d Tage bis %s%s, das ist ein %s." % (n, name, jahr, WOCHENTAGE[d.weekday()])
        m = WOCHENTAG_VON.fullmatch(kandidat)
        if m:
            d, name = _ziel_datum(m.group("d"), heute)
            if d is None:
                return None
            war = "war" if d < heute else "ist"
            return "Der %d. %s %d %s ein %s." % (d.day, MONATE[d.month - 1], d.year, war, WOCHENTAGE[d.weekday()])
        m = PROZENT.fullmatch(kandidat)
        if m:
            r = _zahl(m.group("p")) * _zahl(m.group("n")) / 100
            return "%s Prozent von %s sind %s." % (zahl_text(_zahl(m.group("p"))), zahl_text(_zahl(m.group("n"))),
                                                   zahl_text(r, 4))
        m = WURZEL.fullmatch(kandidat)
        if m:
            n = _zahl(m.group("n"))
            if n < 0:
                return "Aus negativen Zahlen ziehe ich keine Wurzel, da wird's imaginär."
            return "Die Wurzel aus %s ist %s." % (zahl_text(n), zahl_text(math.sqrt(n), 4))
        m = UMRECHNEN.fullmatch(kandidat)
        if m:
            r = _umrechnen(_zahl(m.group("n")), m.group("von"), m.group("nach"))
            if r:
                return r
            return None
        m = RECHNEN.fullmatch(kandidat)
        if m and (m.group("op") != "-" or re.search(r"\d\s+-\s+-?\d|\d-\d", kandidat)):
            try:
                r = _rechnen(m.group("a"), m.group("op"), m.group("b"))
            except ZeroDivisionError:
                return "Durch null teilen kann nicht mal ich."
            except OverflowError:
                return None
            wort = {"+": "plus", "-": "minus", "*": "mal", "/": "geteilt durch", "^": "hoch"}[OPS[m.group("op")]]
            return "%s %s %s ist %s." % (zahl_text(_zahl(m.group("a"))), wort, zahl_text(_zahl(m.group("b"))),
                                         zahl_text(r, 4))
        m = WUERFEL.fullmatch(kandidat)
        if m:
            n = m.group("n")
            n = int(n) if n and n.isdigit() else ZAHLWORT.get(n or "einen", 1)
            if not 1 <= n <= 5:
                return None
            w = [zufall.randint(1, 6) for _ in range(n)]
            if n == 1:
                return "Eine %d." % w[0]
            return "%s und %d, zusammen %d." % (", ".join(str(x) for x in w[:-1]), w[-1], sum(w))
        if MUENZE.fullmatch(kandidat):
            return zufall.choice(["Kopf.", "Zahl."])
        m = ZUFALL.fullmatch(kandidat)
        if m:
            a, b = sorted((int(m.group("a")), int(m.group("b"))))
            if b - a > 10 ** 9:
                return None
            return "%d." % zufall.randint(a, b)
    return None
