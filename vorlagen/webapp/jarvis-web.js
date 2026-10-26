/* Jarvis als Web-App (seit 25.10.2026): iPhone, iPad und jeder Browser im Heimnetz, ohne App Store.
   Die Bruecke liefert unter /app die Oberflaeche der Android-App (app.html) mit diesem Skript aus. Es bildet die
   Java-Schnittstelle window.Jarvis nach, mit fetch gegen die Bruecke (gleicher Ursprung, also nur dort gueltig).
   - Kopplung mit Kopplungscode (oder Link .../app#code=ABCD-EFGH); das Geraete-Token liegt nur im Speicher dieses
     Browsers (localStorage), Neu koppeln loescht es. Die Bruecke legt es als Web-App-Geraet an: nur im Heimnetz,
     kein Fernzugang, keine PC-Steuerung (die Seite kommt per HTTP, der Speicher haengt nur an Adresse und Port).
   - iPhone/iPad: Web-Apps auf dem Home-Bildschirm haben einen eigenen Speicher, Safari gibt ihnen das Token nicht
     mit. Deshalb erst "Zum Home-Bildschirm", dann dort oeffnen und koppeln; im Safari-Tab steht ein Hinweis.
   - Sprechen: das Diktier-Mikrofon der Tastatur (iPhone: Mikrofon unten rechts). Eigene Aufnahme im Browser braucht
     HTTPS, die Bruecke im Heimnetz spricht HTTP.
   - Antworten spricht die Bruecke (/v1/sprich, WAV). iOS spielt Ton erst nach einer Beruehrung: ein Audio-Element
     wird beim ersten Tippen freigeschaltet und dann wiederverwendet.
   - Proben: Adresse mit ?test=1 schickt Fragen unter der Quelle test-webapp (Werkzeuge mit Wirkung nur trocken). */
(function () {
  "use strict";
  const WEB_VERSION = "4.3";
  // Texte kommen aus dem Woerterbuch der Oberflaeche (tx, seit 4.2); die Schicht laeuft vor ihr, fragt also erst spaeter
  const T = (k, ...w) => (typeof window.tx === "function" ? window.tx(k, ...w) : k);
  const L = (k, v) => {
    try {
      if (v === undefined) return localStorage.getItem(k);
      if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v);
    } catch (e) { /* privater Modus: dann ohne Speicher */ }
    return null;
  };
  const QUELLE = /[?&]test=1(&|$)/.test(location.search) ? "test-webapp" : "app";
  const DIREKT = /^(image\/(jpeg|png|webp|gif)|application\/pdf|audio\/[a-z0-9.+-]+|video\/(mp4|webm)|text\/(plain|csv))$/;
  const dateien = {};               // seit 0.3.3: Kennung -> {url, name, typ, blob} der Dateien von Jarvis
  const tok = () => L("jarvis-token");
  const zufall = () => Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
  async function ruf(methode, pfad, body, alsBlob) {
    const kopf = { "Content-Type": "application/json" };
    if (tok()) kopf.Authorization = "Bearer " + tok();
    const r = await fetch(pfad, { method: methode, headers: kopf, body: body ? JSON.stringify(body) : undefined, cache: "no-store" });
    if (!r.ok) { const e = new Error("HTTP " + r.status); e.code = r.status; throw e; }
    return alsBlob ? r.blob() : r.json();
  }
  const rueck = (name, ...a) => { try { if (typeof window[name] === "function") window[name](...a); } catch (e) { console.error(e); } };
  function geraetName() {
    const u = navigator.userAgent;
    return (/iPad/.test(u) ? "iPad" : /iPhone/.test(u) ? "iPhone" : /Android/.test(u) ? "Android" : "Browser") + " (Web-App)";
  }

  // Ton: ein Element fuer alles, beim ersten Tippen freigeschaltet (iOS-Regel fuer Wiedergabe ohne Beruehrung)
  const ton = new Audio();
  let frei = false, laeuft = 0;
  function freischalten() {
    if (frei) return;
    frei = true;
    ton.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
    ton.play().catch(() => {});
  }
  document.addEventListener("touchend", freischalten, { passive: true });
  document.addEventListener("click", freischalten);

  async function sprechen(text, nr) {
    try {
      const wav = await ruf("POST", "/v1/sprich", { text: text.slice(0, 2000) }, true);
      if (nr !== laeuft) return;
      const alt = ton.src;
      ton.src = URL.createObjectURL(wav);
      if (alt.startsWith("blob:")) URL.revokeObjectURL(alt);
      ton.onended = () => { if (nr === laeuft) rueck("onStatus", "bereit"); };
      rueck("onStatus", "spricht");
      await ton.play();
    } catch (e) {
      rueck("onStatus", "bereit");
    }
  }

  async function frage(text, quelle, anhang) {
    const nr = ++laeuft, anfrage = zufall(), t0 = Date.now();
    let fertig = false;
    rueck("onStatus", "denkt");
    (async () => {                      // Zwischenstand: welches Werkzeug laeuft gerade
      while (!fertig) {
        await new Promise((r) => setTimeout(r, 800));
        if (fertig) break;
        try { const z = await ruf("GET", "/v1/zwischen/" + anfrage); if (!fertig) rueck("onWerkzeug", z.werkzeug || ""); } catch (e) { /* egal */ }
      }
    })();
    try {
      const a = await ruf("POST", "/v1/frage", { text, quelle: quelle || QUELLE, geraet: geraetName(), anfrage, anhang });
      fertig = true;
      rueck("onWerkzeug", "");
      if (nr !== laeuft) return;
      const antwort = String(a.antwort || "");
      rueck("onAntwort", antwort, (Date.now() - t0) / 1000, null, false);   // Text immer, die Stimme kommt dazu
      if (Array.isArray(a.dateien) && a.dateien.length) rueck("onDateien", a.dateien);   // seit 0.3.3
      if (W.stimmeAn() && antwort) sprechen(antwort, nr); else rueck("onStatus", "bereit");
    } catch (e) {
      fertig = true;
      rueck("onFehler", e.code === 413 ? T("anhang_gross", 15)
        : T(e.code === 401 ? "web_401" : e.code === 429 ? "web_429" : "web_weg", e.message));
    }
  }

  const W = {
    gekoppelt: () => !!tok(),
    stimmeAn: () => L("jarvis-stimme") !== "0",
    stimme: (an) => { L("jarvis-stimme", an ? "1" : "0"); },
    frage: (t) => { frage(String(t)); },
    // seit 0.3.2: Datei im Gespraech (app.html bereitet sie vor: Bild verkleinert, Ton als WAV)
    originalAlsDaten: true,             // seit 0.3.3: app.html legt das Original (bis 50 MB) als Base64 bei
    frageMitAnhang: (t, anhang) => {
      try { frage(String(t || ""), undefined, JSON.parse(anhang)); }
      catch (e) { rueck("onFehler", T("anhang_fehler", e.message)); }
    },
    // seit 0.3.2 (Pruefbericht 0.3.1, Fund 11): immer Quelle meldung, Titel als JSON-Zeichenkette
    frageMeldung: (titel) => frage(T("web_schlagzeile", JSON.stringify(String(titel).slice(0, 300))), "meldung"),
    hoeren: () => {
      rueck("onStatus", "bereit");
      rueck("onHinweis", T("web_diktat"));
      setTimeout(() => { const e = document.getElementById("eingabe"); if (e) e.focus(); }, 30);
    },
    stopp: () => { laeuft++; try { ton.pause(); } catch (e) { /* egal */ } rueck("onStatus", "bereit"); },
    zustand: async () => {
      try { rueck("onZustand", await ruf("GET", "/v1/zustand")); rueck("onVerbindung", "heimnetz"); }
      catch (e) { if (!e.code) rueck("onVerbindung", "offline"); }
    },
    lage: async () => { try { rueck("onLage", await ruf("GET", "/v1/lage")); } catch (e) { /* egal */ } },
    faehigkeiten: async () => { try { rueck("onFaehigkeiten", await ruf("GET", "/v1/faehigkeiten")); } catch (e) { /* egal */ } },
    einstellungen: async (auftrag) => {
      try { rueck("onEinstellungen", await ruf("POST", "/v1/einstellungen", JSON.parse(auftrag || "{}"))); }
      catch (e) { rueck("onEinstellungen", { fehler: e.code === 404 ? T("web_zahnrad_alt") : T("web_fehler", e.message) }); }
    },
    info: () => JSON.stringify({ version: "Web-App " + WEB_VERSION, fassung: "", verbindung: "heimnetz", adresse: location.host,
      geraet: L("jarvis-geraet") || "–", lan: location.host, netz: T("web_nur_heimnetz"), update: T("web_update") }),
    start: async () => {
      let art = "offline";
      try { if ((await fetch("/v1/gesund", { cache: "no-store" })).ok) art = "heimnetz"; } catch (e) { /* offline */ }
      rueck("onStart", art);
    },
    pruefen: () => {},
    koppeln: (code) => W.koppeln2(code, ""),
    koppeln2: async (code) => {
      try {
        const r = await fetch("/v1/koppeln", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: String(code).trim().toUpperCase(), name: geraetName(), webapp: true }) });
        const a = await r.json().catch(() => ({}));
        if (!r.ok || !a.token) throw new Error(a.fehler || "HTTP " + r.status);
        L("jarvis-token", a.token);
        L("jarvis-geraet", a.geraet || "");
        rueck("onGekoppelt", true);
      } catch (e) {
        rueck("onGekoppelt", false, T("web_abgelehnt", e.message));
      }
    },
    koppelLink: () => {                 // .../app#code=ABCD-EFGH: Code ins Feld, Adresse ist diese Bruecke
      const m = location.hash.match(/code=([A-Za-z0-9-]{4,16})/);
      if (!m) return "";
      history.replaceState(null, "", location.pathname + location.search);
      return JSON.stringify({ adresse: location.host, code: m[1] });
    },
    heimAdresse: () => location.host,
    entkoppeln: () => { L("jarvis-token", null); L("jarvis-geraet", null); },
    echtzeitToken: () => rueck("onEchtzeitToken", { fehler: T("web_echtzeit") }),
    echtzeitFrage: () => {},
    echtzeitVerlauf: () => {},
    updatePruefen: () => rueck("onUpdate", { code: 0, installiert: 0, installiertName: "Web-App " + WEB_VERSION }),
    // Kopplungshinweis als Schluessel des Woerterbuchs: am iPhone im Safari-Tab erst "Zum Home-Bildschirm"
    koppelHinweis: () => {
      const ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
      const eigenesFenster = navigator.standalone === true || window.matchMedia("(display-mode: standalone)").matches;
      return ios && !eigenesFenster ? "koppel_web_ios" : "koppel_web";
    },
    updateLaden: () => {},
    // seit 0.3.3: Dateien von Jarvis, mit Token als Blob geholt (nie ein Link mit Token). Oeffnen, Teilen und Speichern
    // laufen danach direkt im Klick, sonst blockt der Browser sie.
    dateiLaden: async (k, name, typ) => {
      try {
        const roh = await ruf("GET", "/v1/datei/" + k, undefined, true);
        // seit 0.3.4 (Pruefbericht 0.3.3, Fund 12): neu verpacken, nur bekannte Typen behalten; ein blob: im Ursprung
        // der Web-App traegt die Sandbox-Kopfzeilen der Bruecke nicht mehr
        const t = DIREKT.test(roh.type) ? roh.type : "application/octet-stream";
        const b = new Blob([roh], { type: t });
        const url = URL.createObjectURL(b);
        dateien[k] = { url, name: String(name || "datei"), typ: t, blob: b };
        rueck("onDateiBereit", k, /^image\/(jpeg|png|webp|gif)$/.test(t) ? url : "", true);
      } catch (e) {
        rueck("onDateiBereit", k, "", false, e.code === 404 ? T("datei_fehlt") : T("web_fehler", e.message));
      }
    },
    dateiOeffnen: (k) => { const d = dateien[k]; if (d && DIREKT.test(d.typ)) window.open(d.url, "_blank", "noopener"); },
    dateiSpeichern: (k) => {
      const d = dateien[k];
      if (!d) return;
      const a = document.createElement("a");
      a.href = d.url; a.download = d.name;
      document.body.appendChild(a); a.click(); a.remove();
    },
    dateiTeilen: (k) => {
      const d = dateien[k];
      if (!d) return;
      const f = new File([d.blob], d.name, { type: d.typ });
      if (navigator.canShare && navigator.canShare({ files: [f] })) navigator.share({ files: [f], title: d.name }).catch(() => {});
      else W.dateiSpeichern(k);          // Rechner ohne Teilen-Menue: herunterladen
    },
  };
  window.Jarvis = W;
  if (L("text-immer") === null) L("text-immer", "1");   // Web-App: Antworten immer auch als Text

  // Was es hier nicht gibt, ausblenden: Echtzeit, App-Update, Adressfeld der Kopplung (die Adresse ist diese Seite)
  document.documentElement.classList.add("webapp");
  const stil = document.createElement("style");
  stil.textContent = "html.webapp #p-echtzeit, html.webapp #u-knopf, html.webapp #adresse { display: none !important; }";
  document.head.appendChild(stil);
  const echtzeitZeile = document.getElementById("m-echtzeit");
  if (echtzeitZeile && echtzeitZeile.closest(".m-zeile")) echtzeitZeile.closest(".m-zeile").style.display = "none";
  // Kopplungshinweis setzt die Oberflaeche (texteAnwenden) ueber koppelHinweis()
})();
