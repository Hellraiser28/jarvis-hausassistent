#!/usr/bin/env python3
"""Jarvis-Sprecher (seit 0.6): erkennt an der Stimme, wer spricht.

Modell: ERes2Net (3D-Speaker, VoxCeleb, 16 kHz) ueber sherpa-onnx. Versuch auf echten Handyaufnahmen mit zwei
Testpersonen: 0,78-0,81 zum eigenen Profil, 0,00-0,03 zum jeweils anderen, Piper-Stimme hoechstens 0,14.
VORSICHT: Stimmklone (Programme zum Nachbilden einer Stimme) erreichen 0,64-0,77 und gehen als die Person durch. Die
Stimme ist deshalb nie ein Kennwort-Ersatz; die Bruecke wechselt nach der Stimme nur in Rollen ohne fremde Privatdaten
(unbekannt oder Gast).

Zwei Schnittstellen:
- HTTP nur fuer die Bruecke (Standard 127.0.0.1:10320, im Stack network_mode host), jede Anfrage ausser /gesund mit
  Kopfzeile X-Sprecher-Token (SPRECHER_TOKEN oder SPRECHER_TOKEN_DATEI; ohne Token lehnt der Dienst alles ab):
    POST /erkennen            WAV -> {person, wert, stufe: sicher|unsicher|fremd|zu_kurz|ohne_profile, werte}
    POST /anlernen?person=id  WAV (mindestens 2 s, nicht stumm) -> {proben}; hoechstens 30 Proben je Person
    POST /vergessen?person=id -> Profil geloescht
    GET  /profile             -> {personen: {id: proben}, modell, schwellen}
    GET  /zuletzt?text=...    -> letzte Erkennung der Wyoming-Durchreiche zu genau diesem Text, mit client (IP)
    GET  /gesund
- Wyoming-Durchreiche (Standard 0.0.0.0:10310, nur fuer die Adressen in SPRECHER_ERLAUBT; dort die Adresse von Home
  Assistant eintragen, Standard ist nur 127.0.0.1): alle Ereignisse gehen unveraendert zu jarvis-ohr (OHR) und zurueck;
  nebenbei sammelt sie das Audio und erkennt nach audio-stop den Sprecher. Die Durchreiche laeuft auch ohne Modell
  (dann ohne Erkennung), damit die Spracherkennung von HA nie davon abhaengt.

Profile (Stimm-Merkmale, keine Aufnahmen) liegen als JSON in SPRECHER_PROFILE. Das sind biometrische Daten: nur auf
dem eigenen Rechner, nicht ins Git, nicht in Ausgaben; angelernt wird nur mit ausdruecklicher Zustimmung der Person.
Ordner 700, Dateien 600 (profil_ordner, _speichern).
Unabhaengige Pruefung eingearbeitet: Token, Groessengrenzen, Erlaubnisliste, Ablage des Ergebnisses unabhaengig vom
Verbindungsende, stumme und doppelte Anlern-Aufnahmen abgelehnt.
SPRECHER_SPRACHE=de|en: Sprache der Fehlertexte, die ueber die Bruecke bei der Person ankommen (Standard de).
"""
import asyncio
import collections
import hashlib
import hmac
import http.server
import io
import json
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import wave

try:
    import numpy as np
except ImportError:      # venv kaputt/offline beim Start: Durchreiche laeuft trotzdem (Befund 6)
    np = None

MODELL = os.environ.get("SPRECHER_MODELL", "/modell/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx")
PROFILE = os.environ.get("SPRECHER_PROFILE", "/profile")
OHR = os.environ.get("OHR", "127.0.0.1:10300")
HTTP = os.environ.get("SPRECHER_HTTP", "127.0.0.1:10320")
WYOMING = os.environ.get("SPRECHER_WYOMING", "0.0.0.0:10310")
TOKEN = os.environ.get("SPRECHER_TOKEN", "")
if not TOKEN and os.environ.get("SPRECHER_TOKEN_DATEI"):     # Datei statt Variable (Stack ohne .env)
    try:
        TOKEN = open(os.environ["SPRECHER_TOKEN_DATEI"], encoding="utf-8").read().strip()
    except OSError:
        TOKEN = ""
# Wer an die Durchreiche darf: die Adresse von Home Assistant (und 127.0.0.1 fuer lokale Tests), mit Komma getrennt
ERLAUBT = {x.strip() for x in os.environ.get("SPRECHER_ERLAUBT", "127.0.0.1").split(",") if x.strip()}
SICHER = float(os.environ.get("SCHWELLE_SICHER", "0.55"))   # ab hier: diese Person (und deutlich vor der zweiten)
FREMD = float(os.environ.get("SCHWELLE_FREMD", "0.35"))     # darunter: niemand aus dem Haushalt
ABSTAND = float(os.environ.get("ABSTAND", "0.12"))          # Vorsprung vor der zweitbesten Person fuer "sicher"
MIN_S, ANLERN_MIN_S, MAX_S = 1.0, 2.0, 30.0
# Seit 06.11.2026: ein Stimm-Merkmal aus hoechstens 10 s. Das Modell brauchte fuer 30 s am Stueck so viel Speicher, dass
# zwei Anlern-Aufrufe hintereinander die 512-MB-Grenze rissen (Kernel beendete den Dienst, das zweite Profil fehlte).
# Laengere Aufnahmen tragen weiter voll bei: anlernen() zerlegt sie zusaetzlich in 3-s-Stuecke.
VEKTOR_MAX_S = 10.0
STUMM_RMS = 0.004                                           # leiser als das: Mikrofon belegt oder nichts gesagt
MAX_PROBEN = 30
WAV_MAX = 6 * 1024 * 1024
DATEN_MAX, NUTZ_MAX = 64 * 1024, 2 * 1024 * 1024           # Grenzen je Wyoming-Ereignis
NAME = re.compile(r"[a-z0-9_-]{1,40}")
SPRACHE = "en" if os.environ.get("SPRECHER_SPRACHE", "de") == "en" else "de"


def _t(de, en):
    """Texte, die ueber die Bruecke bei der Person ankommen (wie _t in den Modulen der Bruecke); das Protokoll bleibt
    deutsch."""
    return en if SPRACHE == "en" else de


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def profil_ordner(pfad):
    """Ordner der Stimmprofile (biometrische Daten) nur fuer den Besitzer: neu mit 700. Einen vorhandenen Ordner setzt
    der Dienst nur dann auf 700, wenn er ihm gehoert (ein eingehaengter Ordner eines anderen Kontos bleibt, wie er ist;
    das steht dann im Protokoll). Gibt die Rechte danach zurueck (z. B. 0o700) oder None, wenn sie unbekannt sind."""
    os.makedirs(pfad, mode=0o700, exist_ok=True)
    try:
        st = os.stat(pfad)
        eigen = not hasattr(os, "getuid") or st.st_uid == os.getuid()
        if eigen and st.st_mode & 0o077:
            os.chmod(pfad, 0o700)
        elif st.st_mode & 0o077:
            log("Profil-Ordner gehoert einem anderen Konto und ist fuer andere lesbar, bitte auf 700 setzen:", pfad)
        return os.stat(pfad).st_mode & 0o777
    except OSError as e:
        log("Rechte des Profil-Ordners nicht pruefbar:", type(e).__name__)
        return None


def pcm_zu_float(pcm, rate, breite, kanaele):
    """Rohes PCM (8/16/24/32 bit) -> float32 mono 16 kHz."""
    import soxr
    if breite == 2:
        x = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768
    elif breite == 3:                   # 24 bit, z. B. Aufnahmen aus Audio-Programmen (seit 06.11.2026)
        b3 = np.frombuffer(pcm[: len(pcm) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b3[:, 0] | (b3[:, 1] << 8) | (b3[:, 2] << 16)
        x = (v - ((v & 0x800000) << 1)).astype(np.float32) / 8388608
    elif breite == 4:
        x = np.frombuffer(pcm[: len(pcm) // 4 * 4], dtype="<i4").astype(np.float32) / 2147483648
    elif breite == 1:
        x = (np.frombuffer(pcm, dtype=np.uint8).astype(np.float32) - 128) / 128
    else:
        raise ValueError(_t("Sample-Breite %d", "Sample width %d") % breite)
    if kanaele > 1:
        x = x[: len(x) // kanaele * kanaele].reshape(-1, kanaele).mean(axis=1)
    if rate != 16000:
        x = soxr.resample(x, rate, 16000)
    return np.ascontiguousarray(x, dtype=np.float32)


def wav_zu_float(roh):
    with wave.open(io.BytesIO(roh)) as w:
        return pcm_zu_float(w.readframes(w.getnframes()), w.getframerate(), w.getsampwidth(), w.getnchannels())


def norm(v):
    v = np.asarray(v, dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


class Erkenner:
    def __init__(self):
        import sherpa_onnx
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=MODELL, num_threads=2, debug=False)
        self.ex = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        self.s = threading.Lock()
        self.zuletzt_angelernt = collections.deque(maxlen=20)     # Pruefsummen: doppelte Uploads (App-Wiederholung)
        profil_ordner(PROFILE)
        self.profile = {}
        for n in os.listdir(PROFILE):
            if n.endswith(".json") and NAME.fullmatch(n[:-5]):
                try:
                    d = json.load(open(os.path.join(PROFILE, n), encoding="utf-8"))
                    if d.get("modell") == os.path.basename(MODELL) and d.get("proben"):
                        self.profile[n[:-5]] = np.array(d["proben"], dtype=np.float32)
                except (OSError, ValueError):
                    log("Profil unlesbar:", n)
        log("Profile:", {p: len(v) for p, v in self.profile.items()})

    def vektor(self, x):
        with self.s:
            st = self.ex.create_stream()
            st.accept_waveform(16000, x[: int(VEKTOR_MAX_S * 16000)])
            st.input_finished()
            return norm(self.ex.compute(st))

    def _speichern(self, person):
        pfad = os.path.join(PROFILE, person + ".json")
        tmp = pfad + ".neu"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)      # gleich mit 600, nie kurz lesbar
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"modell": os.path.basename(MODELL), "zeit": int(time.time()),
                       "proben": [[round(float(z), 6) for z in v] for v in self.profile[person]]}, f)
        os.replace(tmp, pfad)

    def anlernen(self, person, x, roh=b""):
        if not NAME.fullmatch(person or ""):
            raise ValueError(_t("Ungültiger Personenname.", "Invalid person name."))
        if len(x) < ANLERN_MIN_S * 16000:
            raise ValueError(_t("Zu kurz zum Anlernen (mindestens %d s).",
                                "Too short to learn from (at least %d s).") % ANLERN_MIN_S)
        if float(np.sqrt(np.mean(np.square(x)))) < STUMM_RMS:
            raise ValueError(_t("Zu leise. Ist das Mikrofon frei? Bitte noch einmal deutlich sprechen.",
                                "Too quiet. Is the microphone free? Please speak clearly once more."))
        pruef = hashlib.sha256(person.encode() + b"\x00" + roh).hexdigest()
        if roh and (person, pruef) in self.zuletzt_angelernt:
            return len(self.profile.get(person, []))           # dieselbe Aufnahme schon gespeichert
        x = x[: int(MAX_S * 16000)]
        neu = [self.vektor(x)]
        n = int(3 * 16000)                     # lange Aufnahme: zusaetzlich 3-s-Stuecke (robuster gegen kurze Befehle)
        neu += [self.vektor(x[i:i + n]) for i in range(0, len(x) - n + 1, n)] if len(x) >= 2 * n else []
        with self.s:
            alt = self.profile.get(person)
            p = np.vstack([alt, np.array(neu)]) if alt is not None else np.array(neu)
            self.profile[person] = p[-MAX_PROBEN:]
            self._speichern(person)
            if roh:
                self.zuletzt_angelernt.append((person, pruef))
            return len(self.profile[person])

    def vergessen(self, person):
        with self.s:
            self.profile.pop(person, None)
            for e in [e for e in self.zuletzt_angelernt if e[0] == person]:   # danach darf sie wieder angelernt werden
                self.zuletzt_angelernt.remove(e)
            try:
                os.remove(os.path.join(PROFILE, person + ".json"))
            except OSError:
                pass

    def erkennen(self, x):
        s = len(x) / 16000
        if s < MIN_S:
            return {"person": None, "wert": 0.0, "stufe": "zu_kurz", "sekunden": round(s, 2), "werte": {}}
        with self.s:
            profile = {p: norm(v.mean(axis=0)) for p, v in self.profile.items()}
        if not profile:
            return {"person": None, "wert": 0.0, "stufe": "ohne_profile", "sekunden": round(s, 2), "werte": {}}
        e = self.vektor(x[: int(MAX_S * 16000)])
        werte = {p: round(float(np.dot(e, v)), 3) for p, v in profile.items()}
        reihe = sorted(werte.items(), key=lambda kv: -kv[1])
        best, wert = reihe[0]
        zweit = reihe[1][1] if len(reihe) > 1 else -1.0
        if wert < FREMD:
            stufe, person = "fremd", None
        elif wert >= SICHER and wert - zweit >= ABSTAND:
            stufe, person = "sicher", best
        else:
            stufe, person = "unsicher", best
        return {"person": person, "wert": wert, "stufe": stufe, "sekunden": round(s, 2), "werte": werte}


E = None                                        # wird im Hintergrund geladen; die Durchreiche laeuft auch ohne
ZULETZT = collections.deque(maxlen=30)          # Ergebnisse der Wyoming-Durchreiche


def vergleich(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def senden(self, code, d):
        b = json.dumps(d, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def zugang(self):
        t = self.headers.get("X-Sprecher-Token", "")
        return bool(TOKEN) and hmac.compare_digest(t.encode("utf-8", "replace"), TOKEN.encode())

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/gesund":
            return self.senden(200, {"ok": True, "erkennung": E is not None})
        if not self.zugang():
            return self.senden(403, {"fehler": _t("kein Zugang", "no access")})
        if E is None:
            return self.senden(503, {"fehler": _t("Modell lädt noch oder fehlt", "model still loading or missing")})
        if u.path == "/profile":
            return self.senden(200, {"personen": {p: len(v) for p, v in E.profile.items()}, "modell": os.path.basename(MODELL),
                                     "schwellen": {"sicher": SICHER, "fremd": FREMD, "abstand": ABSTAND}})
        if u.path == "/zuletzt":
            text = vergleich((q.get("text") or [""])[0])
            try:
                max_s = min(60.0, float((q.get("max_s") or ["20"])[0]))
            except ValueError:
                max_s = 20.0
            for e in reversed(list(ZULETZT)):          # Kopie: die Durchreiche haengt parallel an
                if time.time() - e["zeit"] > max_s:
                    break
                if text and e["vergleich"] == text:
                    return self.senden(200, {k: v for k, v in e.items() if k != "vergleich"})
            return self.senden(404, {"fehler": "nichts passendes"})
        self.senden(404, {"fehler": "unbekannt"})

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > WAV_MAX:
            return self.senden(400 if n < 0 else 413, {"fehler": _t("ungültige Länge", "invalid length")})
        roh = self.rfile.read(n) if n else b""
        if not self.zugang():
            return self.senden(403, {"fehler": _t("kein Zugang", "no access")})
        if E is None:
            return self.senden(503, {"fehler": _t("Modell lädt noch oder fehlt", "model still loading or missing")})
        person = (q.get("person") or [""])[0]
        try:
            if u.path == "/erkennen":
                t = time.time()
                r = E.erkennen(wav_zu_float(roh))
                r["ms"] = int((time.time() - t) * 1000)
                return self.senden(200, r)
            if u.path == "/anlernen":
                return self.senden(200, {"ok": True, "person": person, "proben": E.anlernen(person, wav_zu_float(roh), roh)})
            if u.path == "/vergessen":
                if not NAME.fullmatch(person):
                    raise ValueError(_t("Ungültiger Personenname.", "Invalid person name."))
                E.vergessen(person)
                return self.senden(200, {"ok": True})
        except (ValueError, wave.Error, EOFError) as e:
            return self.senden(400, {"fehler": str(e)})
        self.senden(404, {"fehler": "unbekannt"})


# ------------------------------------------------------------------ Wyoming-Durchreiche (fuer Home Assistant)
class Zuviel(Exception):
    pass


async def ereignis(r):
    zeile = await r.readline()
    if not zeile:
        return None
    if len(zeile) > DATEN_MAX:
        raise Zuviel("Kopfzeile zu lang")
    kopf = json.loads(zeile)
    dl, pl = int(kopf.get("data_length") or 0), int(kopf.get("payload_length") or 0)
    if not 0 <= dl <= DATEN_MAX or not 0 <= pl <= NUTZ_MAX:
        raise Zuviel("Ereignis zu groß")
    roh = zeile
    daten = dict(kopf.get("data") or {})
    if dl:
        db = await r.readexactly(dl)
        roh += db
        daten.update(json.loads(db))
    nutz = b""
    if pl:
        nutz = await r.readexactly(pl)
        roh += nutz
    return kopf.get("type"), daten, nutz, roh


async def ablegen(zukunft, text, client):
    """Ergebnis zum Text ablegen, unabhaengig davon, ob die Verbindung schon zu ist (Pruefung, Befund 4)."""
    try:
        r = await asyncio.wait_for(zukunft, 10)
        ZULETZT.append(dict(r, zeit=time.time(), text=text[:200], vergleich=vergleich(text), client=client))
        log("Wyoming:", r["stufe"], r["person"] or "-", r["wert"], "%.1fs" % r["sekunden"], client)
    except Exception as x:                              # Erkennung darf die Durchreiche nie stoeren
        log("Erkennung fehlgeschlagen:", type(x).__name__)


async def durchreiche(cr, cw):
    client = (cw.get_extra_info("peername") or ("?",))[0]
    if client not in ERLAUBT:
        log("Wyoming: abgelehnt", client)
        cw.close()
        return
    host, port = OHR.rsplit(":", 1)
    try:
        ur, uw = await asyncio.open_connection(host, int(port))
    except OSError as e:
        log("Ohr nicht erreichbar:", e)
        cw.close()
        return
    loop = asyncio.get_running_loop()
    zustand = {"fmt": None, "pcm": bytearray(), "zukunft": None}

    async def hin():
        while True:
            e = await ereignis(cr)
            if e is None:
                break
            typ, d, nutz, roh = e
            if typ == "audio-start":
                zustand.update(fmt=(d.get("rate", 16000), d.get("width", 2), d.get("channels", 1)), pcm=bytearray(), zukunft=None)
            elif typ == "audio-chunk" and zustand["fmt"] and len(zustand["pcm"]) < MAX_S * 16000 * 4:
                zustand["pcm"] += nutz
            elif typ == "audio-stop" and zustand["fmt"] and zustand["pcm"] and E is not None:
                pcm, fmt = bytes(zustand["pcm"]), zustand["fmt"]
                zustand["zukunft"] = loop.run_in_executor(None, lambda: E.erkennen(pcm_zu_float(pcm, *fmt)))
            uw.write(roh)
            await uw.drain()

    async def zurueck():
        while True:
            e = await ereignis(ur)
            if e is None:
                break
            typ, d, nutz, roh = e
            if typ == "transcript" and zustand["zukunft"] is not None:     # vor dem Weitergeben: HA schliesst sofort
                asyncio.ensure_future(ablegen(zustand["zukunft"], str(d.get("text") or ""), client))
                zustand["zukunft"] = None
            cw.write(roh)
            await cw.drain()

    aufgaben = [asyncio.ensure_future(hin()), asyncio.ensure_future(zurueck())]
    try:
        await asyncio.wait(aufgaben, return_when=asyncio.FIRST_COMPLETED)
        await asyncio.sleep(0.5)                        # letzte Antwort von jarvis-ohr noch durchlassen
    except Exception:
        pass
    finally:
        for a in aufgaben:
            a.cancel()
            if a.done() and not a.cancelled() and a.exception():
                log("Wyoming:", type(a.exception()).__name__)
        for w in (uw, cw):
            try:
                w.close()
            except Exception:
                pass


def modell_laden():
    global E
    if np is None:
        log("Ohne numpy/sherpa-onnx: nur Durchreiche, keine Erkennung")
        return
    try:
        E = Erkenner()
        log("Erkennung bereit, Modell", os.path.basename(MODELL))
    except Exception as e:                              # Durchreiche bleibt, nur ohne Erkennung
        log("Modell nicht geladen:", type(e).__name__, e)


def main():
    if not TOKEN:
        log("WARNUNG: SPRECHER_TOKEN fehlt, die HTTP-Schnittstelle lehnt alles ab (Durchreiche laeuft)")
    threading.Thread(target=modell_laden, daemon=True).start()
    h, p = HTTP.rsplit(":", 1)
    srv = http.server.ThreadingHTTPServer((h, int(p)), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log("HTTP auf", HTTP, "| Wyoming auf", WYOMING, "-> Ohr", OHR, "| erlaubt", ",".join(sorted(ERLAUBT)))
    wh, wp = WYOMING.rsplit(":", 1)

    async def laufen():
        server = await asyncio.start_server(durchreiche, wh, int(wp))
        async with server:
            await server.serve_forever()

    asyncio.run(laufen())


if __name__ == "__main__":
    main()
