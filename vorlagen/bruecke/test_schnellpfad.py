#!/usr/bin/env python3
"""Baustein schnellpfad.py (einfache Fragen ohne Gehirn, seit 0.7): Uhrzeit, Datum, Tage bis, Wochentag, Rechnen,
Prozent, Wurzel, Einheiten, Wuerfel, Muenze, Zufallszahl auf Deutsch und Englisch; alles andere geht ans Gehirn (None).
Feste Uhrzeit und fester Zufall, keine Netzzugriffe."""
import datetime as dt
import os
import random
import re
import sys
import time

HIER = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(os.path.dirname(HIER), "bruecke"), HIER):
    sys.path.insert(0, p)
import schnellpfad as snp  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    ok, fehler = (ok + 1, fehler) if bed else (ok, fehler + 1)
    print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:300]) if info and not bed else ""))


J = dt.datetime(2026, 11, 6, 14, 32)          # Freitag


def sp(text, seed=1, jetzt=J):
    return snp.antwort(text, jetzt, random.Random(seed))


# ================================================================ Deutsch
pruef("S1 Uhrzeit in drei Formen", sp("Wie spät ist es?") == sp("Jarvis, wie spät ist es eigentlich?")
      == sp("Hey Jarvis wie viel Uhr ist es") == "Es ist 14:32 Uhr.", sp("Wie spät ist es?"))
pruef("S2 heute und morgen", sp("Welcher Tag ist heute?") == "Heute ist Freitag, der 6. November 2026."
      and sp("Der wievielte ist heute?") == sp("Welcher Tag ist heute?")
      and sp("Welcher Tag ist morgen?") == "Morgen ist Samstag, der 7. November.", sp("Welcher Tag ist morgen?"))
pruef("S3 Tage bis Weihnachten und bis 24.12.", sp("Wie viele Tage noch bis Weihnachten?").startswith("Noch 48 Tage bis Weihnachten")
      and sp("wieviele tage bis zum 24.12.").startswith("Noch 48 Tage") and "Donnerstag" in sp("wieviele tage bis zum 24.12."),
      (sp("Wie viele Tage noch bis Weihnachten?"), sp("wieviele tage bis zum 24.12.")))
pruef("S3b Ziel im naechsten Jahr nennt das Jahr, morgen und heute eigene Saetze",
      "2027" in (sp("Wie viele Tage bis Neujahr?") or "") and "morgen" in (sp("Wie viele Tage bis zum 7.11.?") or "")
      and sp("Wie viele Tage bis zum 6.11.?") == "Das ist heute!", (sp("Wie viele Tage bis Neujahr?"), sp("Wie viele Tage bis zum 7.11.?")))
pruef("S4 Wochentag eines Datums, auch vergangen", sp("Welcher Wochentag ist der 24.12.?") == "Der 24. Dezember 2026 ist ein Donnerstag."
      and sp("Welcher Wochentag ist der 1.1.2026") == "Der 1. Januar 2026 war ein Donnerstag."
      and sp("Auf welchen Tag fällt Silvester?") == "Der 31. Dezember 2026 ist ein Donnerstag.",
      (sp("Welcher Wochentag ist der 1.1.2026"),))
pruef("S5 Rechnen mit deutschem Komma und Tausenderpunkt",
      sp("Was ist 17 mal 23?") == "17 mal 23 ist 391." and sp("wie viel ist 12,5 plus 3") == "12,5 plus 3 ist 15,5."
      and sp("2 hoch 10") == "2 hoch 10 ist 1.024." and sp("10 geteilt durch 4") == "10 geteilt durch 4 ist 2,5."
      and sp("7 - 3") == "7 minus 3 ist 4." and sp("Was ist bitte 3 mal 4") == "3 mal 4 ist 12."
      and sp("1.000 mal 3") == "1.000 mal 3 ist 3.000." and sp("3 minus 5") == "3 minus 5 ist -2.",
      [sp(x) for x in ("2 hoch 10", "7 - 3", "1.000 mal 3", "3 minus 5")])
pruef("S6 durch null, Prozent, Wurzel", sp("100 geteilt durch 0") == "Durch null teilen kann nicht mal ich."
      and sp("20 Prozent von 80") == "20 Prozent von 80 sind 16." and sp("Wurzel aus 144") == "Die Wurzel aus 144 ist 12."
      and sp("2 hoch 1000") is None, sp("2 hoch 1000"))
pruef("S7 Einheiten", sp("Was sind 5 Meilen in Kilometer?") == "5 Meilen sind 8,05 Kilometer."
      and sp("100 Fahrenheit in Celsius") == "100 Grad Fahrenheit sind 37,78 Grad Celsius."
      and sp("1 Zoll in Zentimeter") == "1 Zoll ist 2,54 Zentimeter." and sp("5 kg in Meter") is None,
      [sp("1 Zoll in Zentimeter"), sp("5 kg in Meter")])
w1 = [sp("Wirf einen Würfel", s) for s in range(40)]
w2 = sp("Wirf zwei Würfel", 3)
pruef("S8 Wuerfel, Muenze, Zufallszahl", all(x in ["Eine %d." % i for i in range(1, 7)] for x in w1) and len(set(w1)) == 6
      and w2.endswith(", zusammen %d." % sum(int(z) for z in w2.split(",")[0].split(" und ")))
      and {sp("Wirf eine Münze", s) for s in range(20)} == {"Kopf.", "Zahl."}
      and all(1 <= int(sp("Zufallszahl zwischen 1 und 6", s)[:-1]) <= 6 for s in range(30)), (set(w1), w2))
NEIN = ["Wie spät ist es in Tokio?", "Wie viele Tage bis zu meinem Geburtstag?", "wirf", "10:30", "3 und 4",
        "Rechne mir aus, ob sich das lohnt", "Was ist 5 - mehr?", "Mach das Licht an", "Erinner mich um 10:30",
        "Wie viel Uhr ist es, und wie wird das Wetter?", "30 Grad in Fahrenheit", "Stell einen Timer auf 10 Minuten",
        "Was ist 2 mal 3 und mach dann das Licht an", "Wie spät ist es morgen früh beim Sonnenaufgang?", "", None,
        "Wie spät ist es?" * 10, "Welcher Tag ist heute in einer Woche?", "Was kostet 1 kg Kaffee in Euro?",
        "Welcher Wochentag ist der 31.2.?", "Würfel Kim eine Aufgabe zu", "Zufallszahl zwischen 1 und 99999999999",
        "What time is it?", "What's 17 times 23?", "How many days until Christmas?"]
treffer = [(x, sp(x)) for x in NEIN if sp(x) is not None]
pruef("S9 alles andere geht ans Gehirn (%d Gegenproben, auch englische Saetze)" % len(NEIN), not treffer, treffer)
s0 = time.perf_counter()
for i in range(1000):
    snp.antwort("Was ist %d mal 7?" % i, J)
dauer = time.perf_counter() - s0
pruef("S10 schnell: 1000 Fragen in %.2f s" % dauer, dauer < 2.0)
pruef("S11 Zahlformat deutsch", snp.zahl_text(1234567.5) == "1.234.567,5" and snp.zahl_text(-0.25) == "-0,25"
      and snp.zahl_text(0.0000001) == "0" and snp.zahl_text(float("inf")) == "unendlich")
pruef("S12 Symbole sind sprachneutral, Antwort deutsch", sp("17 * 23") == "17 mal 23 ist 391." and sp("2^10") == "2 hoch 10 ist 1.024.")

# ================================================================ Englisch
try:
    snp.setze_sprache("fr")
    pruef("Fremde Sprache abgelehnt", False)
except ValueError:
    pruef("Fremde Sprache abgelehnt", True)
snp.setze_sprache("en")
pruef("EN1 Uhrzeit in mehreren Formen, 12 Stunden", sp("What time is it?") == sp("Jarvis, what time is it?")
      == sp("Hey Jarvis what’s the time") == sp("what time is it now please") == sp("time") == "It's 2:32 PM."
      and sp("what time is it", jetzt=dt.datetime(2026, 11, 6, 0, 5)) == "It's 12:05 AM."
      and sp("what time is it", jetzt=dt.datetime(2026, 11, 6, 12, 0)) == "It's 12:00 PM.", sp("What time is it?"))
snp.UHR_12H_EN = False
uhr24 = sp("What time is it?")
snp.UHR_12H_EN = True
pruef("EN1b 24 Stunden abschaltbar", uhr24 == "It's 14:32.", uhr24)
pruef("EN2 heute und morgen", sp("What day is it today?") == sp("What's the date?") == sp("today's date")
      == "Today is Friday, November 6, 2026." and sp("What day is tomorrow?") == sp("what's tomorrow's date")
      == "Tomorrow is Saturday, November 7.", (sp("What's the date?"), sp("What day is tomorrow?")))
pruef("EN3 Tage bis (Christmas ist der 25.12.)", sp("How many days until Christmas?") == "49 days until Christmas, which is a Friday."
      and sp("how many days till december 24") == "48 days until December 24, which is a Thursday."
      and sp("how many days left until new year") == "56 days until New Year's Day 2027, which is a Friday."
      and sp("How many days until November 7?") == "Just one more sleep, November 7 is tomorrow."
      and sp("how many days until the 6th of november") == "That's today!"
      and sp("how long until halloween") == "359 days until Halloween 2027, which is a Sunday.",
      [sp(x) for x in ("How many days until Christmas?", "how many days left until new year", "how long until halloween")])
pruef("EN4 Wochentag eines Datums, auch vergangen", sp("What day of the week is December 24?") == "December 24, 2026 is a Thursday."
      and sp("What day was January 1, 2026?") == "January 1, 2026 was a Thursday."
      and sp("What day does Halloween fall on?") == "October 31, 2027 is a Sunday."
      and sp("which day is 2027-01-03") == "January 3, 2027 is a Sunday."
      and sp("what day of the week is christmas eve") == "December 24, 2026 is a Thursday.",
      [sp(x) for x in ("What day was January 1, 2026?", "What day does Halloween fall on?")])
pruef("EN5 Rechnen mit englischem Punkt und Tausenderkomma",
      sp("What's 17 times 23?") == "17 times 23 is 391." and sp("how much is 12.5 plus 3") == "12.5 plus 3 is 15.5."
      and sp("2 to the power of 10") == "2 to the power of 10 is 1,024." and sp("10 divided by 4") == "10 divided by 4 is 2.5."
      and sp("7 - 3") == "7 minus 3 is 4." and sp("what is 3 x 4 please") == "3 times 4 is 12."
      and sp("1,000 times 3") == "1,000 times 3 is 3,000." and sp("3 minus 5") == "3 minus 5 is -2."
      and sp("17 * 23") == "17 times 23 is 391.",
      [sp(x) for x in ("2 to the power of 10", "1,000 times 3", "what is 3 x 4 please")])
pruef("EN6 durch null, Prozent, Wurzel", sp("100 divided by 0") == "Even I can't divide by zero."
      and sp("20 percent of 80") == "20 percent of 80 is 16." and sp("square root of 144") == "The square root of 144 is 12."
      and sp("what's the square root of -4") == "I don't take square roots of negative numbers, that gets imaginary."
      and sp("2 to the power of 1000") is None, sp("2 to the power of 1000"))
pruef("EN7 Einheiten, auch 'how many X are in'", sp("What's 5 miles in kilometers?") == "5 miles is 8.05 kilometers."
      and sp("100 fahrenheit in celsius") == "100 degrees Fahrenheit is 37.78 degrees Celsius."
      and sp("1 inch in centimeters") == "1 inch is 2.54 centimeters."
      and sp("how many kilometers are in 5 miles") == "5 miles is 8.05 kilometers."
      and sp("convert 2 pounds to grams") == "2 pounds is 907.18 grams."
      and sp("1 degree celsius in fahrenheit") == "1 degree Celsius is 33.8 degrees Fahrenheit." and sp("5 kg in meters") is None,
      [sp(x) for x in ("1 inch in centimeters", "convert 2 pounds to grams", "5 kg in meters")])
e1 = [sp("Roll a die", s) for s in range(40)]
e2 = sp("roll two dice", 3)
pruef("EN8 Wuerfel, Muenze, Zufallszahl", all(x in ["You rolled a %d." % i for i in range(1, 7)] for x in e1)
      and len(set(e1)) == 6 and re.fullmatch(r"\d and \d, \d+ in total\.", e2 or "")
      and int(e2.split(", ")[1].split()[0]) == sum(int(z) for z in e2.split(",")[0].split(" and "))
      and {sp("flip a coin", s) for s in range(20)} == {"Heads.", "Tails."} and sp("heads or tails") in ("Heads.", "Tails.")
      and all(1 <= int(sp("random number between 1 and 6", s)[:-1]) <= 6 for s in range(30)) and sp("roll 6 dice") is None,
      (set(e1), e2))
NEIN_EN = ["What time is it in Tokyo?", "How many days until my birthday?", "roll", "10:30", "3 and 4",
           "Work out whether it's worth it", "What is 5 - more?", "Turn on the light", "Remind me at 10:30",
           "What time is it, and what's the weather?", "30 degrees in fahrenheit", "Set a timer for 10 minutes",
           "What is 2 times 3 and then turn on the light", "What time is sunrise tomorrow?", "", None,
           "What time is it?" * 10, "What day is it in a week?", "How much is 1 kg of coffee in euros?",
           "What day is February 31?", "Roll Kim a chore", "Random number between 1 and 99999999999",
           "What day is the meeting?", "how many days until 12/24", "what's 1,5 times 3", "what time do the shops close",
           "the time machine", "date night ideas", "Wie spät ist es?", "Was ist 17 mal 23?", "Wie viele Tage bis Weihnachten?"]
treffer = [(x, sp(x)) for x in NEIN_EN if sp(x) is not None]
pruef("EN9 alles andere geht ans Gehirn (%d Gegenproben, auch deutsche Saetze und '12,5')" % len(NEIN_EN), not treffer,
      treffer)
s0 = time.perf_counter()
for i in range(1000):
    snp.antwort("What is %d times 7?" % i, J)
dauer = time.perf_counter() - s0
pruef("EN10 schnell: 1000 Fragen in %.2f s" % dauer, dauer < 2.0)
pruef("EN11 Zahlformat englisch", snp.zahl_text(1234567.5) == "1,234,567.5" and snp.zahl_text(-0.25) == "-0.25"
      and snp.zahl_text(float("inf")) == "infinity")
FRAGEN_EN = ["What time is it?", "What day is it today?", "What day is tomorrow?", "How many days until Christmas?",
             "how many days until new year", "How many days until November 7?", "how many days until november 6",
             "What day was January 1, 2026?", "What's 17 times 23?", "2 to the power of 10", "100 divided by 0",
             "20 percent of 80", "square root of 144", "what's the square root of -4", "What's 5 miles in kilometers?",
             "100 fahrenheit in celsius", "Roll a die", "roll two dice", "flip a coin", "random number between 1 and 6"]
rest = [(x, sp(x)) for x in FRAGEN_EN if not sp(x) or re.search(r"[äöüÄÖÜß]|\b(ist|sind|nicht|Bitte|bitte|Uhr|Tage|"
                                                                   r"bis|und|zusammen|Prozent|Wurzel|Eine)\b", sp(x))]
pruef("EN12 kein deutscher Rest in den englischen Antworten", not rest, rest)
snp.setze_sprache("de")
pruef("Zurueck auf Deutsch", sp("Wie spät ist es?") == "Es ist 14:32 Uhr." and sp("What time is it?") is None
      and snp.zahl_text(1234.5) == "1.234,5")

print("Schnellpfad: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
