"""Gemeinsame Attrappe fuer die Superhirn-Module (seit 0.7): ein Kontext ctx wie ihn die Bruecke spaeter liefert,
ohne Netz, ohne Home Assistant, ohne Claude. Alles, was ein Modul nach aussen tut, wird aufgezeichnet.

    import sh_attrappe
    ctx = sh_attrappe.Kontext(antworten={"kabinett": '{"...": 1}'})    # denken() liefert je zweck eine Antwort
    modul.auftrag({"aktion": "neu", ...}, "alex", ctx)
    ctx.pushes, ctx.durchsagen, ctx.dienste, ctx.gedacht ...
"""
import json
import os
import shutil
import tempfile
import time


class Kontext:
    def __init__(self, antworten=None, zustaende=None, personen=None, jetzt=None, raeume=None):
        self.daten = tempfile.mkdtemp(prefix="sh-test-")
        self._antworten = dict(antworten or {})      # zweck -> str | callable(auftrag, system, stufe) | list (der Reihe nach)
        self.zustaende = dict(zustaende or {})        # entity_id -> {"state": ..., "attributes": {...}}
        self._personen = personen or {"alex": {"name": "Alex", "rolle": "haupt"},
                                      "sam": {"name": "Sam", "rolle": "familie"},
                                      "kim": {"name": "Kim", "rolle": "familie"},
                                      "gast1": {"name": "Gast", "rolle": "gast"}}
        self._jetzt = jetzt
        self._raeume = raeume or {"version": 1, "raeume": {
            "wohnzimmer": {"name": "Wohnzimmer", "bereich": "Wohnzimmer", "ausgabe": [],
                           "licht": ["light.wohnzimmer_decke", "light.wohnzimmer_stehlampe"]},
            "kueche": {"name": "Küche", "bereich": "Küche", "ausgabe": [], "licht": ["light.kueche"]},
            "flur": {"name": "Flur", "bereich": "Flur", "ausgabe": [], "licht": ["light.flur"]}}}
        self.pushes, self.durchsagen, self.dienste, self.gedacht, self.logs, self.abgelegt = [], [], [], [], [], []
        self.leinwand = []
        self.fremd = ""        # Fremdarten der laufenden Frage, wie ShKontext.fremd ("" = sauber)

    # ------------------------------------------------------------ Zeit, Personen, Raeume
    def jetzt(self):
        return self._jetzt if self._jetzt is not None else time.time()

    def personen(self):
        return dict(self._personen)

    def person_name(self, person):
        return (self._personen.get(person) or {}).get("name") or person

    def raeume(self):
        """Wie daten/raeume.json (version, raeume{id: {name, alias, bereich, ausgabe}}, geraete) – OHNE Lampen."""
        r = json.loads(json.dumps(self._raeume))
        for v in r["raeume"].values():
            v.pop("licht", None)
        return r

    rezepte = ["Lasagne", "Pizza Margherita", "Linsensuppe", "Chili sin Carne", "Pfannkuchen", "Pasta Carbonara"]

    def rezept_ideen(self, anzahl, suche=None):
        """Zufaellige Rezepttitel (z. B. aus Mealie, falls die Bruecke eine Rezeptquelle hat); hier fest und ohne Zufall."""
        l = [r for r in self.rezepte if not suche or suche.lower() in r.lower()] or list(self.rezepte)
        return l[:anzahl]

    def raum_lichter(self, raum):
        """Lampen (light.*) im HA-Bereich des Raums; die Bruecke fragt dafuer HA (area_entities)."""
        return list((self._raeume["raeume"].get(raum) or {}).get("licht") or [])

    # ------------------------------------------------------------ Denken (Claude)
    def denken(self, auftrag, system="", stufe="normal", werkzeuge=(), zweck="", reserve_usd=None):
        self.gedacht.append({"zweck": zweck, "stufe": stufe, "werkzeuge": tuple(werkzeuge), "auftrag": auftrag,
                             "system": system, "reserve_usd": reserve_usd})
        a = self._antworten.get(zweck)
        if a is None:
            raise AssertionError("Attrappe: keine Antwort fuer zweck=%r" % zweck)
        if isinstance(a, list):
            if not a:
                raise AssertionError("Attrappe: Antworten fuer %r aufgebraucht" % zweck)
            a = a.pop(0)
        return a(auftrag, system, stufe) if callable(a) else str(a)

    def denken_json(self, auftrag, system="", stufe="normal", werkzeuge=(), zweck="", reserve_usd=None):
        import denken as dk
        return dk.json_aus(self.denken(auftrag, system, stufe, werkzeuge, zweck, reserve_usd))

    # ------------------------------------------------------------ nach aussen
    def push(self, person, titel, text, klick=None, tag="jarvis"):
        self.pushes.append({"person": person, "titel": titel, "text": text, "klick": klick, "tag": tag})
        return True

    def durchsage(self, ziel, text):
        self.durchsagen.append({"ziel": ziel, "text": text})
        return "durchsage"

    def ha_zustand(self, entity_id):
        if entity_id not in self.zustaende:
            raise KeyError(entity_id)
        return dict(self.zustaende[entity_id], entity_id=entity_id)

    def ha_dienst(self, domain, dienst, daten):
        self.dienste.append((domain, dienst, dict(daten or {})))

    def leinwand_text(self, titel, text="", punkte=None):
        self.leinwand.append({"titel": titel, "text": text, "punkte": list(punkte or [])})
        return "gezeigt"

    def ablegen(self, roh, name, typ, person):
        kennung = "a%024x" % (len(self.abgelegt) + 1)
        self.abgelegt.append({"kennung": kennung, "name": name, "typ": typ, "person": person, "groesse": len(roh)})
        return kennung

    def datei_holen(self, kennung):
        for d in getattr(self, "dateien", []):
            if d["kennung"] == kennung:
                return d["roh"], d["typ"]
        raise KeyError(kennung)

    def oeffentlich(self, pfad):
        return "https://jarvis.test.invalid/" + pfad.lstrip("/")

    def lan(self, pfad):
        return "http://192.0.2.64:8770/" + pfad.lstrip("/")

    def log(self, *a):
        self.logs.append(" ".join(str(x) for x in a))

    def aufraeumen(self):
        shutil.rmtree(self.daten, ignore_errors=True)


def pruefer():
    """Kleine Pruefhilfe wie in den uebrigen Tests: pruef(name, bedingung, info) und ergebnis() -> Exitcode."""
    stand = {"ok": 0, "fehler": 0}

    def pruef(name, bed, info=""):
        stand["ok" if bed else "fehler"] += 1
        print("%s %s%s" % ("OK    " if bed else "FEHLER", name, (" | " + str(info)[:300]) if info and not bed else ""),
              flush=True)

    def ergebnis(titel):
        print("\n%s: %d ok, %d Fehler" % (titel, stand["ok"], stand["fehler"]))
        return 1 if stand["fehler"] else 0
    return pruef, ergebnis


def live_wache():
    """Optional: Pruefsummen eines echten Datenordners vorher (JARVIS_LIVE_DATEN, z. B. der Datenordner des laufenden
    Jarvis auf demselben Rechner). Aufrufen gibt eine Funktion zurueck, die True liefert, wenn der Test dort nichts
    geaendert und keine der neue_namen NEU angelegt hat. Ohne JARVIS_LIVE_DATEN gibt es nichts zu bewachen: immer True."""
    import hashlib
    live = os.environ.get("JARVIS_LIVE_DATEN", "")
    if not live or not os.path.isdir(live):
        return lambda neue_namen=(): True
    namen = sorted(n for n in os.listdir(live) if os.path.isfile(os.path.join(live, n)))
    vorher = {n: hashlib.sha256(open(os.path.join(live, n), "rb").read()).hexdigest() for n in namen}

    def unveraendert(neue_namen=()):
        # Eine schon vorher vorhandene Datei prueft der Pruefsummenvergleich; verraeterisch ist nur, was NEU entsteht.
        nachher = {n: hashlib.sha256(open(os.path.join(live, n), "rb").read()).hexdigest() for n in namen
                   if os.path.exists(os.path.join(live, n))}
        return nachher == vorher and not any(n not in vorher and os.path.exists(os.path.join(live, n))
                                             for n in neue_namen)
    return unveraendert
