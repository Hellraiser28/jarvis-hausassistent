/* Jarvis Haus 3D (seit 0.6: echtes 3D, dreh- und zoombar, gerade Waende):
   das Haus als Puppenhaus-Modell. Waende, Tueren, Fenster und Moebel kommen aus einem Plan in Metern (haus3d.json,
   erzeugt z. B. aus Saugroboter-Karten und einem Rundgang), Geraete leuchten warm, wenn sie laufen. Seit 01.11.2026
   oeffnet ein angetipptes Geraet ein Menue (Foto, Zustand, Bedienung je Art), wenn der Gastgeber steuern mitgibt.
   Seit 01.11.2026 abends "lebendiger wie im Reel": nachts warme Lichtinseln und Fensterschein, weiches Ueberblenden
   Tag/Nacht (Chip Mond), Kamerafahrt beim Oeffnen, Etagen schweben ein, Saugroboter mit Spur, Leinwand und Monitore
   zeigen Inhalt, Lautsprecher einen Pegel, unten eine Bedienleiste mit Szenen (opt.szenen) und Geraete-Kacheln.
   Braucht three.js r160 (three.min.js, MIT) als globales THREE.

   Nutzung:  const h = Haus3D.oeffnen(element, { laden, schliessen, sprache, daten, alle_s, drehen, wechsel, steuern, bild });
             wechsel = {text, klick}: Chip zur anderen Ansicht (Bild), nur wenn es beide gibt.
             steuern(entity_id, dienst, daten) -> Promise<{ok, meldung}> (POST /v1/grundriss/steuern); ohne: nur Anzeige.
             bild(name) -> Promise<url>: Geraetefoto (GET /v1/grundriss/bild/<name>).
             szenen = {liste: () => Promise<[{id, name}]>, starten: (id) => Promise<{ok, meldung}>}: Szenen in der Leiste.
             h.daten(json); h.waehlen("dg"); h.zu()
   daten = Antwort von GET /v1/grundriss mit Feld haus3d: {art: "haus3d", umriss: [x0, y0, x1, y1], etagen: {eg: {name,
           boden, hoehe, raeume: [{id, name, boden, poly}], oeffnungen: [{typ, von, bis}], treppen, moebel, geraete:
           [{id, name, symbol, x, y, z, entitaeten, an_von?, an_ab?, immer?}]}}}, dazu zustaende und sauger wie beim
           Puppenhaus. Plan: x nach Osten, y nach Sueden; in three.js wird y zu z, die Hoehe zu y. */
(function () {
  "use strict";
  const DE = { titel: "HAUS", stand: "Stand {0}", laedt: "Baue das Haus auf …", keine: "Noch kein 3D-Plan vom Haus.",
    kein_gl: "Dieses Gerät kann kein WebGL – nimm die Bildansicht.", an: "an", aus: "aus", weg: "nicht erreichbar",
    keine_geraete: "Keine Geräte in diesem Raum.", schliessen: "Schließen", waende: "Wände",
    nur: "nur Anzeige · ziehen dreht · zwei Finger oder Mausrad zoomt", sauger: "Saugroboter unterwegs",
    laufen: "{0} von {1} Geräten an", draussen: "{0} °C draußen",
    bedienen: "Gerät antippen bedient · ziehen dreht · zwei Finger oder Mausrad zoomt", nur_anzeige: "Bedienen geht in der App.",
    ein: "Ein", aus_k: "Aus", wirklich: "Wirklich aus?", lautstaerke: "Lautstärke", quelle: "Quelle", modus: "Modus",
    luefter: "Lüfter", saugen: "Saugen", pause: "Pause", heim: "Zur Station", finden: "Finden", akku: "Akku",
    soll: "Soll", ist: "Ist", stumm: "Stumm", laut: "Ton an", sendet: "Sende …", spielt: "Läuft:",
    nacht: "Nachtansicht", szene_laeuft: "Szene läuft …", halten: "lange drücken: alle Funktionen" };
  const EN = { titel: "HOUSE", stand: "As of {0}", laedt: "Building the house …", keine: "No 3D plan of the house yet.",
    kein_gl: "This device has no WebGL – use the picture view.", an: "on", aus: "off", weg: "unavailable",
    keine_geraete: "No devices in this room.", schliessen: "Close", waende: "Walls",
    nur: "view only · drag to rotate · pinch or wheel to zoom", sauger: "Robot vacuum on the move",
    laufen: "{0} of {1} devices on", draussen: "{0} °C outside",
    bedienen: "tap a device to control · drag to rotate · pinch or wheel to zoom", nur_anzeige: "Control it in the app.",
    ein: "On", aus_k: "Off", wirklich: "Really off?", lautstaerke: "Volume", quelle: "Source", modus: "Mode",
    luefter: "Fan", saugen: "Clean", pause: "Pause", heim: "Dock", finden: "Locate", akku: "Battery",
    soll: "Target", ist: "Now", stumm: "Mute", laut: "Unmute", sendet: "Sending …", spielt: "Playing:",
    nacht: "Night view", szene_laeuft: "Scene running …", halten: "long press: all controls" };
  const ZUST = { on: ["an", "on"], off: ["aus", "off"], playing: ["spielt", "playing"], idle: ["bereit", "idle"],
    standby: ["Standby", "standby"], docked: ["in der Station", "docked"], cleaning: ["saugt", "cleaning"],
    heat: ["heizt", "heating"], auto: ["Automatik", "auto"], unavailable: ["nicht erreichbar", "unavailable"],
    inactive: ["inaktiv", "inactive"], ready: ["bereit", "ready"], run: ["läuft", "running"], finished: ["fertig", "finished"],
    cool: ["kühlt", "cooling"], dry: ["entfeuchtet", "drying"], fan_only: ["lüftet", "fan"], returning: ["fährt heim", "returning"] };
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // Gleiche Regel wie Puppenhaus und alte 3D-Ansicht: was zaehlt als "an"
  function istAn(eid, z) {
    if (!z) return false;
    const s = String(z.s || "").toLowerCase(), d = eid.split(".")[0];
    if (d === "media_player") return s === "playing" || s === "on" || s === "idle";
    if (d === "sensor") { const n = parseFloat(s); if (!isNaN(n) && /W$/.test(z.e || "")) return n > 3; return /^(run|läuft|laeuft)$/.test(s); }
    if (d === "climate") return s !== "off" && s !== "unavailable";
    return s === "on" || s === "playing" || s === "cleaning";
  }
  function geraetAn(g, Z) {
    if (g.immer) return true;
    const e = g.an_von || g.entitaeten[0], z = Z[e];
    if (!z) return false;
    if (g.an_ab != null) { const n = parseFloat(z.s); return !isNaN(n) && n > g.an_ab; }
    return istAn(e, z);
  }
  function geraetWeg(g, Z) {
    if (g.immer) return false;
    const z = Z[g.an_von || g.entitaeten[0]];
    return !z || String(z.s).toLowerCase() === "unavailable";
  }
  function imPoly(poly, x, y) {
    let d = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [x1, y1] = poly[j], [x2, y2] = poly[i];
      if ((y1 > y) !== (y2 > y) && x < (x2 - x1) * (y - y1) / (y2 - y1) + x1) d = !d;
    }
    return d;
  }
  function mitte(poly) {       // Flaechenschwerpunkt (fuer L-Formen besser als der Mittelwert der Ecken)
    let a = 0, cx = 0, cy = 0;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const f = poly[j][0] * poly[i][1] - poly[i][0] * poly[j][1];
      a += f; cx += (poly[j][0] + poly[i][0]) * f; cy += (poly[j][1] + poly[i][1]) * f;
    }
    if (Math.abs(a) < 1e-9) return [poly[0][0], poly[0][1]];
    const m = [cx / (3 * a), cy / (3 * a)];
    return imPoly(poly, m[0], m[1]) ? m : [poly[0][0] + 0.5, poly[0][1] + 0.5];
  }

  /* Waende aus den Raumkanten: jede Kante ist eine Wand, gemeinsame Kanten nur einmal. Nur waagerechte und senkrechte
     Kanten (im Haus gibt es keine schraegen Waende). Oeffnungen schneiden die Wand: Tuer/Durchgang ganz, Fenster
     lassen Bruestung und Sturz stehen. Ergebnis: Stuecke {lage: "h"|"v", k, a, b, unten, oben, aussen, dicke, art}. */
  function waendeBerechnen(E, umriss) {
    const r2 = (v) => Math.round(v * 100) / 100, linien = new Map();
    const dazu = (lage, k, a, b) => {
      const key = lage + ":" + r2(k);
      if (!linien.has(key)) linien.set(key, { lage, k: r2(k), iv: [] });
      linien.get(key).iv.push([Math.min(a, b), Math.max(a, b)]);
    };
    for (const r of E.raeume || []) {
      const p = r.poly || [];
      for (let i = 0; i < p.length; i++) {
        const a = p[i], b = p[(i + 1) % p.length];
        if (Math.abs(a[1] - b[1]) < 1e-6) dazu("h", a[1], a[0], b[0]);
        else if (Math.abs(a[0] - b[0]) < 1e-6) dazu("v", a[0], a[1], b[1]);
      }
    }
    const [X0, Y0, X1, Y1] = umriss, nah = (u, v) => Math.abs(u - v) < 0.03, UE = etagenUmriss(E, umriss);
    const stuecke = [];
    for (const L of linien.values()) {
      L.iv.sort((p, q) => p[0] - q[0]);
      const ganz = [];
      for (const iv of L.iv) {
        const z = ganz[ganz.length - 1];
        if (z && iv[0] <= z[1] + 0.02) z[1] = Math.max(z[1], iv[1]); else ganz.push(iv.slice());
      }
      let aussen = null;
      if (L.lage === "h" && nah(L.k, Y0)) aussen = "nord";
      if (L.lage === "h" && nah(L.k, Y1)) aussen = "sued";
      if (L.lage === "v" && nah(L.k, X0)) aussen = "west";
      if (L.lage === "v" && nah(L.k, X1)) aussen = "ost";
      if (!aussen && L.lage === "h" && nah(L.k, UE[1])) aussen = "nord";
      if (!aussen && L.lage === "h" && nah(L.k, UE[3])) aussen = "sued";
      if (!aussen && L.lage === "v" && nah(L.k, UE[0])) aussen = "west";
      if (!aussen && L.lage === "v" && nah(L.k, UE[2])) aussen = "ost";
      const dicke = aussen ? 0.3 : 0.12;
      // Gelaender (Treppenauge) ersetzen die Wand auf ihrer Linie, "offen" schneidet ohne Sturz
      // Dachfenster sitzen in der Schraege, nicht in der Wand: sie schneiden nichts
      const alle = (E.oeffnungen || []).filter((o) => o.typ !== "dachfenster").concat((E.gelaender || []).map((l) => ({ typ: "offen", von: l[0], bis: l[1] })));
      const oeff = alle.filter((o) => {
        const h = Math.abs(o.von[1] - o.bis[1]) < 1e-6, v = Math.abs(o.von[0] - o.bis[0]) < 1e-6;
        return L.lage === "h" ? h && nah(o.von[1], L.k) : v && nah(o.von[0], L.k);
      }).map((o) => {
        const i = L.lage === "h" ? 0 : 1;
        return Object.assign({}, o, { a: Math.min(o.von[i], o.bis[i]), b: Math.max(o.von[i], o.bis[i]) });
      }).sort((p, q) => p.a - q.a);
      for (const [a0, b0] of ganz) {
        let a = a0;
        for (const o of oeff) {
          if (o.b <= a || o.a >= b0) continue;
          if (o.a > a) stuecke.push({ lage: L.lage, k: L.k, a, b: o.a, unten: 0, oben: null, aussen, dicke, art: "wand" });
          const oa = Math.max(o.a, a), ob = Math.min(o.b, b0);
          if (o.typ === "fenster" || o.typ === "gaube") {
            const br = o.bruestung != null ? o.bruestung : 0.9, st = o.sturz != null ? o.sturz : 2.1;
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, unten: 0, oben: br, aussen, dicke, art: "wand" });
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, unten: br, oben: st, aussen, dicke, art: "glas" });
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, unten: st, oben: null, aussen, dicke, art: "wand" });
          } else if (o.typ === "terrassentuer") {
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, unten: 0.02, oben: 2.2, aussen, dicke, art: "glas" });
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, unten: 2.2, oben: null, aussen, dicke, art: "wand" });
          } else if (o.typ === "haustuer") {
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, unten: 0, oben: 2.15, aussen, dicke: 0.08, art: "tuerblatt", tor: ob - oa > 1.8 });
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, unten: 2.15, oben: null, aussen, dicke, art: "wand" });
          } else if (o.typ === "tuer") {
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, unten: 2.05, oben: null, aussen, dicke, art: "wand" });
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, art: "tuer", aussen, dicke, unten: 0, oben: 2.0, gegen: o.gegenseite === true });
          } else if (o.typ === "offen") {
            /* nichts: Treppenauge, Gelaender kommt extra */
          } else if (o.typ === "durchgang") {
            stuecke.push({ lage: L.lage, k: L.k, a: oa, b: ob, unten: 2.2, oben: null, aussen, dicke, art: "wand" });
          }
          a = Math.max(a, o.b);
        }
        if (a < b0 - 0.01) stuecke.push({ lage: L.lage, k: L.k, a, b: b0, unten: 0, oben: null, aussen, dicke, art: "wand" });
      }
    }
    return stuecke.filter((s) => s.b - s.a > 0.02);
  }

  // Umriss eines Geschosses: Hausumriss plus Anbauten (z. B. die Garage am Keller), fuer Aussenwaende, Sockel und Kamera
  function etagenUmriss(E, umriss) {
    const u = umriss.slice();
    for (const r of (E && E.raeume) || []) for (const p of r.poly || []) {
      u[0] = Math.min(u[0], p[0]); u[1] = Math.min(u[1], p[1]); u[2] = Math.max(u[2], p[0]); u[3] = Math.max(u[3], p[1]);
    }
    return u;
  }

  // Gauben: senkrechte Fenster an einer Traufseite; dahinter gilt bis zur Decke die volle Raumhoehe
  function gaubenZonen(E, umriss) {
    if (!E.traufen || !E.kniestock) return [];
    const t = Math.tan((E.dachneigung || 40) * Math.PI / 180), tief = ((E.hoehe || 2.6) - E.kniestock) / t + 0.05, z = [];
    const k = (v, w) => Math.abs(v - w) < 0.05;
    for (const o of E.oeffnungen || []) {
      if (o.typ !== "gaube") continue;
      const xa = Math.min(o.von[0], o.bis[0]) - 0.15, xb = Math.max(o.von[0], o.bis[0]) + 0.15;
      const ya = Math.min(o.von[1], o.bis[1]) - 0.15, yb = Math.max(o.von[1], o.bis[1]) + 0.15;
      if (k(o.von[1], umriss[3]) && k(o.bis[1], umriss[3])) z.push([xa, umriss[3] - tief, xb, umriss[3] + 1]);
      else if (k(o.von[1], umriss[1]) && k(o.bis[1], umriss[1])) z.push([xa, umriss[1] - 1, xb, umriss[1] + tief]);
      else if (k(o.von[0], umriss[2]) && k(o.bis[0], umriss[2])) z.push([umriss[2] - tief, ya, umriss[2] + 1, yb]);
      else if (k(o.von[0], umriss[0]) && k(o.bis[0], umriss[0])) z.push([umriss[0] - 1, ya, umriss[0] + tief, yb]);
    }
    return z;
  }

  // Deckenhoehe ueber dem Punkt (Dachgeschoss: Kniestock an den Traufen, dann Dachschraege bis zur Decke)
  function hoeheBei(E, umriss, x, y) {
    const H = E.hoehe || 2.6;
    if (!E.traufen || !E.kniestock) return H;
    if (y != null && gaubenZonen(E, umriss).some((g) => x >= g[0] && x <= g[2] && y >= g[1] && y <= g[3])) return H;
    const t = Math.tan((E.dachneigung || 40) * Math.PI / 180);
    let d = 99;
    if (E.traufen.includes("west")) d = Math.min(d, x - umriss[0]);
    if (E.traufen.includes("ost")) d = Math.min(d, umriss[2] - x);
    if (y != null && E.traufen.includes("nord")) d = Math.min(d, y - umriss[1]);
    if (y != null && E.traufen.includes("sued")) d = Math.min(d, umriss[3] - y);
    return Math.min(H, E.kniestock + Math.max(0, d) * t);
  }

  // ------------------------------------------------------------------ Texturen (aus Code, keine Bilddateien)
  function leinwand(w, h, malen) {
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    malen(c.getContext("2d"), w, h);
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
    return t;
  }
  function zufall(s) { return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }
  function maserung(x, x0, y0, w, h, r, c) {                    // Laengsmaserung mit leichten Wellen und ein paar Aesten
    for (let k = 0; k < w / 3; k++) {
      const px = x0 + r() * w, d = 0.04 + r() * 0.1, hell = r() > 0.5;
      x.strokeStyle = hell ? `rgba(${c[0] + 30},${c[1] + 26},${c[2] + 18},${d})` : `rgba(${c[0] * 0.55 | 0},${c[1] * 0.5 | 0},${c[2] * 0.45 | 0},${d})`;
      x.lineWidth = 0.6 + r() * 2.2; x.beginPath(); x.moveTo(px, y0);
      const f = 0.004 + r() * 0.01, a = 2 + r() * 6;
      for (let yy = 0; yy <= h; yy += 24) x.lineTo(px + Math.sin((y0 + yy) * f) * a, y0 + yy);
      x.stroke();
    }
    for (let k = 0; k < h / 500; k++) if (r() > 0.4) {
      const ax = x0 + r() * w, ay = y0 + r() * h;
      for (let q = 0; q < 4; q++) { x.strokeStyle = `rgba(${c[0] * 0.45 | 0},${c[1] * 0.4 | 0},${c[2] * 0.35 | 0},${0.25 - q * 0.05})`; x.lineWidth = 1.2; x.beginPath(); x.ellipse(ax, ay, 4 + q * 5, 10 + q * 9, 0, 0, 7); x.stroke(); }
    }
  }
  // Eigene, bunte Motive fuer Poster (keine fremden Bilder) und ein Sternteppich fuers Kinderzimmer
  const POSTERTEX = {};
  function posterTex(seed) {
    if (POSTERTEX[seed]) return POSTERTEX[seed];
    return (POSTERTEX[seed] = leinwand(256, 360, (x, w, h) => {
      const r = zufall(seed * 97 + 13), hue = Math.floor(r() * 360), h2 = (hue + 40 + r() * 80) % 360;
      const gr = x.createLinearGradient(0, 0, w * 0.3, h);
      gr.addColorStop(0, `hsl(${hue},70%,62%)`); gr.addColorStop(1, `hsl(${h2},65%,28%)`);
      x.fillStyle = gr; x.fillRect(0, 0, w, h);
      x.fillStyle = `hsla(${(hue + 180) % 360},85%,78%,.9)`; x.beginPath(); x.arc(w * (0.3 + r() * 0.4), h * (0.22 + r() * 0.12), 34 + r() * 26, 0, 7); x.fill();
      for (let k = 0; k < 3; k++) {
        x.fillStyle = `hsla(${(h2 + k * 25) % 360},60%,${18 + k * 10}%,.85)`; x.beginPath(); x.moveTo(0, h);
        for (let xx = 0; xx <= w; xx += 16) x.lineTo(xx, h * (0.55 + k * 0.12) + Math.sin(xx * (0.02 + r() * 0.01) + k * 2) * (14 + r() * 10));
        x.lineTo(w, h); x.closePath(); x.fill();
      }
      x.fillStyle = "rgba(255,255,255,.85)"; for (let k = 0; k < 14; k++) x.fillRect(r() * w, r() * h * 0.45, 2, 2);
      x.fillStyle = "rgba(255,255,255,.9)"; x.fillRect(16, h - 26, 70 + r() * 60, 6); x.fillRect(16, h - 16, 40 + r() * 40, 4);
    }));
  }
  let STERNTEX = null;
  function sternTex() {
    return STERNTEX || (STERNTEX = leinwand(512, 512, (x, w, h) => {
      const r = zufall(23);
      x.fillStyle = "#a6a9ae"; x.fillRect(0, 0, w, h);
      for (let k = 0; k < 9000; k++) { const v = 150 + (r() - 0.5) * 50; x.fillStyle = `rgba(${v | 0},${v | 0},${v + 3 | 0},.25)`; x.fillRect(r() * w, r() * h, 2, 2); }
      x.fillStyle = "#f3f1ec";
      for (let j = 0; j < 6; j++) for (let i = 0; i < 6; i++) {
        const cx = (i + 0.5 + (j % 2) * 0.5) * w / 6, cy = (j + 0.5) * h / 6, R = 22, dreh = r();
        x.beginPath();
        for (let q = 0; q < 10; q++) { const a = dreh + q * Math.PI / 5, rr = q % 2 ? R * 0.45 : R; x.lineTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr); }
        x.closePath(); x.fill();
      }
    }));
  }
  const HOLZTEX = {}, STOFFTEX = {};
  function holzTex(hex) {                                         // Holz fuer Moebel, eine Kachel = 1 m x 1 m
    if (HOLZTEX[hex]) return HOLZTEX[hex];
    const c = hexRgb(hex);
    return (HOLZTEX[hex] = leinwand(512, 512, (x, w, h) => { const r = zufall(hex % 997 + 13); x.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; x.fillRect(0, 0, w, h); maserung(x, 0, 0, w, h, r, c); }));
  }
  function stoffTex(hex) {                                        // Webstoff, eine Kachel = 25 cm
    if (STOFFTEX[hex]) return STOFFTEX[hex];
    const c = hexRgb(hex);
    const t = leinwand(128, 128, (x, w, h) => {
      const r = zufall(hex % 991 + 7);
      x.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; x.fillRect(0, 0, w, h);
      for (let i = 0; i < w; i += 2) { x.fillStyle = `rgba(0,0,0,${0.05 + r() * 0.05})`; x.fillRect(i, 0, 1, h); }
      for (let j = 0; j < h; j += 2) { x.fillStyle = `rgba(255,255,255,${0.03 + r() * 0.04})`; x.fillRect(0, j, w, 1); }
      flecken(x, w, h, r, 500, c, 24, 1.5, 0.25);
    });
    t.repeat.set(4, 4);
    return (STOFFTEX[hex] = t);
  }
  // Rauschen fuer Oberflaechen: viele kleine halbdurchsichtige Flecken in Abstufungen der Grundfarbe
  function flecken(x, w, h, r, n, rgb, streu, groesse, alpha) {
    for (let k = 0; k < n; k++) {
      const v = (r() - 0.5) * streu;
      x.fillStyle = `rgba(${rgb[0] + v | 0},${rgb[1] + v | 0},${rgb[2] + v | 0},${alpha})`;
      const g = groesse * (0.5 + r()); x.fillRect(r() * w, r() * h, g, g);
    }
  }
  const hexRgb = (h) => [(h >> 16) & 255, (h >> 8) & 255, h & 255];
  const TEX = {
    fliese_dunkel: () => leinwand(512, 512, (x, w, h) => {      // 60er Schieferfliesen, eine Kachel = 2 x 2 Fliesen
      const r = zufall(7);
      for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) {
        const g = 50 + Math.floor(r() * 12), x0 = i * 256, y0 = j * 256;
        x.fillStyle = `rgb(${g},${g + 2},${g + 5})`; x.fillRect(x0, y0, 256, 256);
        x.save(); x.beginPath(); x.rect(x0, y0, 256, 256); x.clip();
        flecken(x, 256, 256, r, 0, [g, g, g], 0, 0, 0);
        for (let k = 0; k < 900; k++) { const v = g + (r() - 0.5) * 22; x.fillStyle = `rgba(${v | 0},${v + 1 | 0},${v + 4 | 0},.35)`; const q = 1 + r() * 5; x.fillRect(x0 + r() * 256, y0 + r() * 256, q, q); }
        for (let k = 0; k < 7; k++) {                                // Schieferadern
          x.strokeStyle = `rgba(${g + 18},${g + 20},${g + 24},${0.08 + r() * 0.1})`; x.lineWidth = 0.6 + r() * 1.6; x.beginPath();
          let px = x0 + r() * 256, py = y0; x.moveTo(px, py);
          for (let t = 0; t < 8; t++) { px += (r() - 0.5) * 60; py += 32; x.lineTo(px, py); }
          x.stroke();
        }
        x.restore();
      }
      x.fillStyle = "#1f2226"; x.fillRect(0, 0, w, 3); x.fillRect(0, 255, w, 3); x.fillRect(0, 0, 3, h); x.fillRect(255, 0, 3, h);
    }),
    putz: () => leinwand(256, 256, (x, w, h) => {               // Innenputz, fast weiss, ganz leicht gekoernt
      const r = zufall(5);
      x.fillStyle = "#ece7df"; x.fillRect(0, 0, w, h);
      flecken(x, w, h, r, 2600, [236, 231, 223], 14, 2, 0.35);
    }),
    // Im Stil "bild" wirken die Boeden liebevoller: Laminat mit 4 schmalen Dielen je Kachel
    // (0,8 x 1,6 m, Dielen 20 cm breit, 0,86-1,33 m lang), versetzt, jede Diele in eigenem Ton, Fugen mit heller Fase
    holz: () => leinwand(1024, 2048, (x, w, h) => {
      const r = zufall(11), n = 4, bw = w / n;
      for (let i = 0; i < n; i++) {
        let y = -Math.floor(r() * 1400);
        while (y < h) {
          const l = 1100 + Math.floor(r() * 600), g = r(), k = (r() - 0.5) * 12;      // mittelbraune Eiche wie Bildansicht
          const c = [164 + g * 20 + k | 0, 120 + g * 16 + k * 0.7 | 0, 80 + g * 12 + k * 0.4 | 0], x0 = i * bw;
          const gr = x.createLinearGradient(x0, y, x0 + bw * 0.4, y + l);
          gr.addColorStop(0, `rgb(${c[0] + 6},${c[1] + 5},${c[2] + 4})`); gr.addColorStop(1, `rgb(${c[0] - 9},${c[1] - 8},${c[2] - 6})`);
          x.fillStyle = gr; x.fillRect(x0, y, bw, l);
          maserung(x, x0, y, bw, l, r, c);
          x.fillStyle = "rgba(52,34,18,.75)"; x.fillRect(x0, y, bw, 2);
          x.fillStyle = "rgba(255,238,210,.2)"; x.fillRect(x0, y + 2, bw, 1);
          y += l;
        }
        x.fillStyle = "rgba(52,34,18,.7)"; x.fillRect(i * bw, 0, 2, h);
        x.fillStyle = "rgba(255,238,210,.18)"; x.fillRect(i * bw + 2, 0, 1, h);
      }
    }),
    beton: () => leinwand(512, 512, (x, w, h) => {              // Estrich/Beton mit Flecken und feinen Poren
      const r = zufall(3);
      // seit 04.11.2026: hell und glatt wie der polierte Estrich der Bildansicht, weiche Wolken statt dunkler Flecken
      x.fillStyle = "#7c7f83"; x.fillRect(0, 0, w, h);
      for (let k = 0; k < 70; k++) { const v = 136 + (r() - 0.5) * 26; x.fillStyle = `rgba(${v | 0},${v | 0},${v + 3 | 0},.11)`; x.beginPath(); x.arc(r() * w, r() * h, 30 + r() * 90, 0, 7); x.fill(); }
      flecken(x, w, h, r, 2600, [128, 131, 135], 26, 2, 0.18);
    }),
    glut: () => {                                                // weicher Lichtpunkt fuer Geraete
      const c = document.createElement("canvas"); c.width = c.height = 128;
      const x = c.getContext("2d"), g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
      g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.18, "rgba(255,255,255,.85)"); g.addColorStop(0.45, "rgba(255,255,255,.25)"); g.addColorStop(1, "rgba(255,255,255,0)");
      x.fillStyle = g; x.fillRect(0, 0, 128, 128);
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
    },
    ledschein: () => {                                           // Lichtschein unter der LED-Linie: oben warm, nach unten aus
      const c = document.createElement("canvas"); c.width = 4; c.height = 128;
      const x = c.getContext("2d"), g = x.createLinearGradient(0, 0, 0, 128);
      g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.12, "rgba(255,255,255,.55)"); g.addColorStop(0.45, "rgba(255,255,255,.16)"); g.addColorStop(1, "rgba(255,255,255,0)");
      x.fillStyle = g; x.fillRect(0, 0, 4, 128);
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
    },
    ring: () => {
      const c = document.createElement("canvas"); c.width = c.height = 128;
      const x = c.getContext("2d"); x.strokeStyle = "rgba(255,255,255,.9)"; x.lineWidth = 6; x.beginPath(); x.arc(64, 64, 52, 0, 7); x.stroke();
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
    },
  };
  const BODEN_KACHEL = { fliese_dunkel: 1.2, holz: 0.8, beton: 2.0 };   // Meter je Texturkachel (Breite)

  // ------------------------------------------------------------------ Moebel (einfach, aber erkennbar)
  const FARBE = { anthrazit: 0x3a3d42, eiche_hell: 0xc9a476, eiche: 0xb48a58, holz: 0xa8794d, weiss: 0xe9e7e2, grau: 0x7f838a,
    grau_hell: 0xb9bcc0, schwarz: 0x1c1e21, metall: 0xa7acb2, beige: 0xd8c7a8, stoff: 0x80848b, rot: 0x9a3b33, blau: 0x5b78a6,
    rosa: 0xd9a3b5, gruen: 0x4f7a4a, tafel: 0x24332b, gelb: 0xd8b23a, karton: 0xb8946a, wand: 0xe2ddd4, stoff_hell: 0xa3a7ad, stoff_weiss: 0xece9e3,
    stoff_sofa: 0x86888c, stoff_dunkel: 0x3c3f44, blatt: 0x5f8a4e, braun_glas: 0x5a3416, glas_weiss: 0xdfe6e8, stoff_braun: 0x6e5a4c,
    kupfer: 0xb8743a, band: 0xa98758, stoff_gelb: 0xe0a83a, stoff_tuerkis: 0x52b4bd, stoff_rosa: 0xe58fb3, stoff_gruen: 0x8cc26a };
  // Kasten mit leicht gerundeten Kanten (Fase ueber eine Extrusion mit Bevel), nach Massen zwischengespeichert. UVs liegen in
  // Metern, die Holz- und Stofftexturen kacheln deshalb massstaeblich. Sehr duenne Teile bleiben einfache Quader.
  const RUND = new Map();
  function rundBox(w, h, d, rmax) {          // rmax (seit 03.11.2026): groesserer Radius fuer Polster und Kissen
    const m = Math.min(w, h, d);
    if (m < 0.03) return new THREE.BoxGeometry(w, h, d);
    const key = w.toFixed(3) + "|" + h.toFixed(3) + "|" + d.toFixed(3) + "|" + (rmax || 0);
    if (RUND.has(key)) return RUND.get(key);
    const rr = Math.min(rmax || 0.014, m * (rmax ? 0.4 : 0.22)), bs = rr * 0.6, cr = rr * 0.4, hw = w / 2 - bs, hh = h / 2 - bs, sh = new THREE.Shape();
    sh.moveTo(-hw + cr, -hh); sh.lineTo(hw - cr, -hh); sh.absarc(hw - cr, -hh + cr, cr, -Math.PI / 2, 0, false);
    sh.lineTo(hw, hh - cr); sh.absarc(hw - cr, hh - cr, cr, 0, Math.PI / 2, false);
    sh.lineTo(-hw + cr, hh); sh.absarc(-hw + cr, hh - cr, cr, Math.PI / 2, Math.PI, false);
    sh.lineTo(-hw, -hh + cr); sh.absarc(-hw + cr, -hh + cr, cr, Math.PI, Math.PI * 1.5, false);
    const tiefe = Math.max(0.001, d - 2 * rr);
    const geo = new THREE.ExtrudeGeometry(sh, { depth: tiefe, bevelEnabled: true, bevelThickness: rr, bevelSize: bs, bevelSegments: rmax ? 4 : 2, curveSegments: rmax ? 5 : 3 });
    geo.translate(0, 0, -tiefe / 2);
    RUND.set(key, geo);
    return geo;
  }
  // Mehrere Geometrien (gleiche Attribute position/normal/uv) zu einer ohne Index zusammenfuegen (seit 03.11.2026)
  function verschmelzen(geos) {
    const teile = geos.map((g) => (g.index ? g.toNonIndexed() : g)), out = new THREE.BufferGeometry();
    for (const n of ["position", "normal", "uv"]) {
      const len = teile.reduce((s, g) => s + g.attributes[n].array.length, 0), arr = new Float32Array(len);
      let o = 0;
      for (const g of teile) { arr.set(g.attributes[n].array, o); o += g.attributes[n].array.length; }
      out.setAttribute(n, new THREE.BufferAttribute(arr, teile[0].attributes[n].itemSize));
    }
    out.computeBoundingSphere();
    return out;
  }
  // Dunkle Schieferfliesen an der Wand, Textur wie der Badboden, je Flaechengroesse
  const FLIESE_MAT = {};
  function fliesenMat(w, h) {
    const k = w.toFixed(2) + "x" + h.toFixed(2);
    if (!FLIESE_MAT[k]) {
      const tx = TEX.fliese_dunkel(); tx.repeat.set(w / 1.2, h / 1.2);
      FLIESE_MAT[k] = new THREE.MeshStandardMaterial({ name: "m:fliese_wand", map: tx, roughness: 0.34, envMapIntensity: 0.9 });
    }
    return FLIESE_MAT[k];
  }
  function imPoly(x, y, poly) {                 // Punkt im Raumumriss (Strahlverfahren)
    let drin = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const a = poly[i], c = poly[j];
      if ((a[1] > y) !== (c[1] > y) && x < (c[0] - a[0]) * (y - a[1]) / (c[1] - a[1]) + a[0]) drin = !drin;
    }
    return drin;
  }
  // Filigranes (Fahrrad, Laufrad, Roller) bekommt keine Foto-Projektion: Geminis Rahmen und Speichen liegen nie genau auf
  // dem Modell, das gab helle Geisterbilder auf dem Boden (04.11.2026). Eigenes Material je Ursprungsmaterial, damit es beim
  // Verschmelzen der Moebel nach Material in einem eigenen Topf landet.
  const KEIN_PJ = new WeakMap();
  function keinPj(g) {
    g.traverse((o) => {
      if (!o.isMesh || Array.isArray(o.material)) return;
      let k = KEIN_PJ.get(o.material);
      if (!k) {
        k = o.material.clone();
        delete k.onBeforeCompile; delete k.customProgramCacheKey;
        k.userData = Object.assign({}, k.userData, { keinPj: true }); delete k.userData.pj;
        KEIN_PJ.set(o.material, k);
      }
      o.material = k;
    });
  }
  function moebelBauen(m, mat) {
    const g = new THREE.Group(), b = m.b, t = m.t, f = m.farbe || "", BS = !!mat.bild;   // BS: Stil "bild" (mehr Detail)
    const K = (w, h, d, farbe, x, y, z, extra) => {
      const me = new THREE.Mesh(rundBox(w, h, d), typeof farbe === "object" ? farbe : mat(farbe, extra));
      me.position.set(x, y + h / 2, z); me.castShadow = me.receiveShadow = true; g.add(me); return me;
    };
    const P = (w, h, d, farbe, x, y, z, r) => {          // Polster: weiche Kanten
      const me = new THREE.Mesh(rundBox(w, h, d, r || 0.05), mat(farbe));
      me.position.set(x, y + h / 2, z); me.castShadow = me.receiveShadow = true; g.add(me); return me;
    };
    const fuge = (w, h, x, y, z) => K(w, h, 0.006, "schwarz", x, y, z);     // Fuge zwischen Fronten (grifflos)
    const pflanze = (x, y, z, gr) => {                     // kleine Topfpflanze als Dekor
      const q = gr || 1;
      const topf = new THREE.Mesh(new THREE.CylinderGeometry(0.055 * q, 0.045 * q, 0.09 * q, 14), mat("weiss")); topf.position.set(x, y + 0.045 * q, z); topf.castShadow = true; g.add(topf);
      for (let i = 0; i < 5; i++) {
        const bl = new THREE.Mesh(new THREE.IcosahedronGeometry(0.045 * q, 0), mat("blatt"));
        bl.position.set(x + Math.cos(i * 1.3) * 0.035 * q, y + (0.12 + (i % 3) * 0.03) * q, z + Math.sin(i * 1.3) * 0.035 * q); bl.castShadow = true; g.add(bl);
      }
    };
    const Z = (r, h, farbe, x, y, z, seg) => {
      const me = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, seg || 16), mat(farbe));
      me.position.set(x, y + h / 2, z); me.castShadow = me.receiveShadow = true; g.add(me); return me;
    };
    // Stil "bild": Bettzeug in Lagen. Die Decke faellt ueber die
    // Kanten und ist oben umgeschlagen, ein Plaid haengt ueber dem Fussende, bauschige Kissen. Kopfende bei -z.
    const bettzeug = (bb, tt, oben, decke, plaid, nKissen, z0) => {
      const zd = z0 || 0, dl = tt * 0.74, dz = zd + tt / 2 - dl / 2 + 0.01;
      P(bb + 0.05, 0.08, dl, decke, 0, oben - 0.02, dz, 0.04);
      for (const sx of [-1, 1]) P(0.035, 0.22, dl - 0.04, decke, sx * (bb / 2 + 0.02), oben - 0.22, dz, 0.017);
      P(bb + 0.05, 0.22, 0.035, decke, 0, oben - 0.22, zd + tt / 2 + 0.02, 0.017);
      P(bb + 0.03, 0.035, 0.2, "stoff_weiss", 0, oben + 0.05, dz - dl / 2 + 0.11, 0.017);
      if (plaid) {
        const pl = tt * 0.26, pz = zd + tt / 2 - pl / 2 + 0.03;
        P(bb + 0.1, 0.035, pl, plaid, 0, oben + 0.06, pz, 0.017);
        for (const sx of [-1, 1]) P(0.03, 0.3, pl, plaid, sx * (bb / 2 + 0.06), oben - 0.22, pz, 0.014);
        P(bb + 0.1, 0.28, 0.03, plaid, 0, oben - 0.2, zd + tt / 2 + 0.05, 0.014);
      }
      const kb = nKissen > 1 ? bb / 2 - 0.1 : Math.min(bb - 0.25, 0.75);
      for (let i = 0; i < nKissen; i++) {
        const k = P(kb, 0.16, 0.42, "stoff_weiss", nKissen > 1 ? (i ? 1 : -1) * bb / 4 : 0, oben - 0.02, zd - tt / 2 + 0.3, 0.075);
        k.rotation.x = -0.18;
      }
    };
    const kopfteil = (bb, hh, z, farbe, y0) => {          // gepolstert, senkrechte Steppfelder
      const n = Math.max(3, Math.round(bb / 0.22)), w = bb / n;
      for (let i = 0; i < n; i++) P(w - 0.008, hh, 0.08, farbe, -bb / 2 + (i + 0.5) * w, y0 || 0, z, 0.035);
    };
    const bank = (bb, tt) => {                            // Polsterbank am Fussende ("mit": "bank")
      const w = bb * 0.78, z = tt / 2 + 0.3;
      P(w, 0.14, 0.4, "stoff_dunkel", 0, 0.32, z, 0.04);
      for (let i = 1; i < 4; i++) K(0.006, 0.006, 0.36, "schwarz", -w / 2 + i * w / 4, 0.46, z);
      for (const [a, c] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) K(0.035, 0.32, 0.035, "schwarz", a * (w / 2 - 0.05), 0, z + c * 0.15);
    };
    const kuscheltiere = (bb, y, z) => {                  // Kuscheltiere am Kopfende ("mit": "kuscheltiere")
      const farben = ["stoff_rosa", "stoff_tuerkis", "stoff_gelb", "stoff_gruen"];
      for (let i = 0; i < 4; i++) {
        const x = -bb / 2 + 0.2 + i * (bb - 0.4) / 3, q = 0.8 + (i % 2) * 0.25, fm = mat(farben[i]);
        const kugel = (rr, px, py, pz) => { const k = new THREE.Mesh(new THREE.SphereGeometry(rr * q, 16, 12), fm); k.position.set(x + px * q, y + py * q, z + pz * q); k.castShadow = true; g.add(k); };
        kugel(0.09, 0, 0.08, 0); kugel(0.075, 0, 0.21, 0.01); kugel(0.03, -0.055, 0.28, 0); kugel(0.03, 0.055, 0.28, 0);
        kugel(0.035, -0.08, 0.06, 0.04); kugel(0.035, 0.08, 0.06, 0.04);
      }
    };
    const schrankTueren = (hh, n, farbe) => {             // Korpus, Tueren mit Schattenfuge, Kassette und Knopf, Sockel
      const fb = farbe || korpus;
      K(b, hh, t - 0.02, fb, 0, 0, -0.01);
      K(b - 0.02, 0.06, 0.01, "schwarz", 0, 0, t / 2 - 0.015);
      const w = (b - 0.01) / n;
      for (let i = 0; i < n; i++) {
        const x = -b / 2 + 0.005 + (i + 0.5) * w;
        K(w - 0.005, hh - 0.08, 0.018, fb, x, 0.07, t / 2 - 0.006);
        for (const yy of [0.2, hh - 0.2]) K(w - 0.14, 0.012, 0.006, fb, x, yy, t / 2 + 0.006);
        for (const sx of [-1, 1]) K(0.012, hh - 0.42, 0.006, fb, x + sx * (w / 2 - 0.075), 0.2, t / 2 + 0.006);
        const kn = new THREE.Mesh(new THREE.SphereGeometry(0.017, 12, 8), mat("metall"));
        kn.position.set(x + (i % 2 ? -1 : 1) * (w / 2 - 0.05), hh * 0.5, t / 2 + 0.02); kn.castShadow = true; g.add(kn);
        if (i) K(0.004, hh - 0.08, 0.004, "schwarz", -b / 2 + 0.005 + i * w, 0.07, t / 2 + 0.003);
      }
    };
    const korpus = /^weiss/.test(f) ? "weiss" : /^grau_hell/.test(f) ? "grau_hell" : /^grau/.test(f) ? "grau" : /^eiche_hell/.test(f) ? "eiche_hell" :
      /^eiche/.test(f) ? "eiche" : /^holz/.test(f) ? "holz" : /^metall/.test(f) ? "metall" : /^schwarz/.test(f) ? "schwarz" : "anthrazit";
    const platte = /_holz$|eiche$|_eiche$/.test(f) ? (/eiche/.test(f) ? "eiche" : "holz") : korpus;
    const bild = (w, h, x, y, z) => {            // Bildschirm: leuchtet, wenn das verknuepfte Geraet an ist
      const s = K(w, h, 0.012, mat("bild"), x, y, z); s.userData.bildschirm = true; s.castShadow = false; return s;
    };
    const stuhl = (x, z, dreh, farbe, gr) => {
      const s = new THREE.Group(), q = gr || 1, mm = mat(farbe || "schwarz");
      const k = (w, h, d, px, py, pz, mx) => { const e = new THREE.Mesh(BS && mx ? rundBox(w * q, h * q, d * q, 0.03) : new THREE.BoxGeometry(w * q, h * q, d * q), mx || mm); e.position.set(px * q, (py + h / 2) * q, pz * q); e.castShadow = true; s.add(e); return e; };
      if (BS && (farbe || "schwarz") === "schwarz") {     // Stil "bild": Polsterstuhl, Sitz und Ruecken in dunklem Stoff, Beine schwarz
        const stoff = mat("stoff_dunkel");
        k(0.44, 0.08, 0.44, 0, 0.42, 0.01, stoff); k(0.42, 0.46, 0.07, 0, 0.46, -0.19, stoff).rotation.x = -0.1;
        for (const [a, c] of [[-0.18, -0.17], [0.18, -0.17], [-0.18, 0.18], [0.18, 0.18]]) k(0.025, 0.42, 0.025, a, 0, c);
      } else {
        k(0.44, 0.05, 0.44, 0, 0.43, 0); k(0.44, 0.42, 0.05, 0, 0.48, -0.2);
        for (const [a, c] of [[-0.19, -0.19], [0.19, -0.19], [-0.19, 0.19], [0.19, 0.19]]) k(0.035, 0.43, 0.035, a, 0, c);
      }
      s.position.set(x, 0, z); s.rotation.y = dreh; g.add(s);
    };
    switch (m.typ) {
      case "hochschrank": {
        K(b, m.hoehe || 2.2, t, korpus, 0, 0, 0);
        if (m.mit === "backofen") { K(b * 0.8, 0.5, 0.02, "schwarzglas", 0, 0.95, t / 2); K(b * 0.8, 0.38, 0.02, "schwarzglas", 0, 0.45, t / 2); }
        if (m.mit === "kuehlschrank") { K(0.02, 1.2, 0.03, "metall", b * 0.38, 0.6, t / 2 + 0.02); K(0.02, 0.6, 0.03, "metall", b * 0.38, 1.45, t / 2 + 0.02); }
        if (BS) {                     // grifflose Fronten: Fugen, dunkler Sockel
          const h = m.hoehe || 2.2;
          K(b - 0.01, 0.09, 0.008, "schwarz", 0, 0, t / 2 + 0.002);
          if (b > 0.65 && m.mit !== "backofen") fuge(0.005, h - 0.14, 0, 0.11, t / 2 + 0.003);
          fuge(b - 0.01, 0.005, 0, m.mit === "backofen" ? 1.48 : 1.3, t / 2 + 0.003);
        }
        break;
      }
      case "kuechenzeile": case "insel": {
        K(b, 0.86, t, korpus, 0, 0, 0);
        K(b + 0.02, 0.04, t + (m.typ === "insel" ? 0.1 : 0.03), BS ? "eiche_hell" : "holz", 0, 0.86, m.typ === "insel" ? 0 : 0.015);
        if (BS) {                     // Schubladenfugen und Sockel auf der Vorderseite (bei der Insel auf beiden Seiten)
          for (const sz of m.typ === "insel" ? [-1, 1] : [1]) {
            const z = sz * (t / 2 + 0.003);
            K(b - 0.01, 0.09, 0.008, "schwarz", 0, 0, sz * (t / 2 + 0.001));
            fuge(b - 0.01, 0.005, 0, 0.38, z); fuge(b - 0.01, 0.005, 0, 0.62, z);
            const n = Math.max(1, Math.round(b / 0.6));
            for (let i = 1; i < n; i++) fuge(0.005, 0.74, -b / 2 + i * b / n, 0.1, z);
          }
        }
        if (m.mit === "spuele" && BS) {          // seit 04.11.2026: schwarze Granitspuele, Ablauf, schwarze Bogenarmatur
          K(0.62, 0.014, 0.46, "schwarz", 0, 0.9, 0.04); K(0.5, 0.004, 0.36, "schwarzglas", 0, 0.912, 0.05);
          Z(0.025, 0.004, "metall", 0.12, 0.914, 0.08, 16);
          Z(0.02, 0.36, "schwarz", 0, 0.9, -0.2, 12);
          const ar = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.014, 8, 16, Math.PI), mat("schwarz")); ar.rotation.y = Math.PI / 2; ar.position.set(0, 1.26, -0.1); ar.castShadow = true; g.add(ar);
          Z(0.012, 0.08, "schwarz", 0, 1.18, 0.0, 10);
        } else if (m.mit === "spuele") { K(0.75, 0.012, 0.42, "metall", 0, 0.9, 0.02); Z(0.015, 0.32, "metall", 0, 0.9, -0.2); }
        if (m.mit === "kochfeld") {
          K(0.78, 0.012, 0.5, "schwarzglas", 0, 0.9, 0);
          if (BS) {                                // vier Kochzonen und Bedienleiste
            for (const [x, z, rr] of [[-0.19, -0.11, 0.09], [0.19, -0.11, 0.07], [-0.19, 0.11, 0.07], [0.19, 0.11, 0.09]]) {
              const zo = new THREE.Mesh(new THREE.TorusGeometry(rr, 0.003, 4, 40), mat("grau")); zo.rotation.x = Math.PI / 2; zo.position.set(x, 0.913, z); g.add(zo);
            }
            K(0.3, 0.002, 0.03, "grau", 0, 0.912, 0.215);
          }
        }
        break;
      }
      case "haengeschrank": K(b, 0.7, t, "glas", 0, m.z || 1.45, 0); K(b, 0.03, t, korpus, 0, (m.z || 1.45) + 0.7, 0); break;
      case "regal": case "bucherregal": {
        const h = m.hoehe || 1.9, n = Math.max(3, Math.round(h / 0.38));
        K(0.03, h, t, korpus, -b / 2 + 0.015, 0, 0); K(0.03, h, t, korpus, b / 2 - 0.015, 0, 0); K(b, 0.02, 0.02, korpus, 0, 0, -t / 2 + 0.01);
        const r = zufall(Math.round(Math.abs(m.x * 100 + m.y * 7)) + 5);
        for (let i = 0; i <= n; i++) {
          const y = i * (h - 0.03) / n; K(b - 0.06, 0.025, t, korpus, 0, y, 0);
          if (i < n && m.typ === "bucherregal") {
            let x = -b / 2 + 0.06;
            while (x < b / 2 - 0.08) { const w = 0.025 + r() * 0.03, hh = 0.2 + r() * 0.1; K(w, hh, t * 0.75, ["rot", "blau", "schwarz", "beige", "gruen", "grau"][Math.floor(r() * 6)], x + w / 2, y + 0.025, 0); x += w + 0.004; }
          } else if (i < n && i > 0) {
            if (BS && korpus === "metall") {        // seit 04.11.2026: im Metallregal Kartons mit Klebeband wie in der Bildansicht
              for (let k = 0; k < 2; k++) if (r() > 0.2) {
                const kb = Math.min(0.45, (b - 0.2) / 2.2) + r() * 0.08, kh = 0.2 + r() * 0.1, x = -b / 2 + 0.08 + kb / 2 + k * (b - 0.16 - kb);
                K(kb, kh, t * 0.85, "karton", x, y + 0.025, 0); K(kb + 0.004, 0.003, 0.05, "band", x, y + 0.025 + kh, 0);
              }
            } else
            for (let k = 0; k < 3; k++) K(0.12 + r() * 0.1, 0.12 + r() * 0.14, t * 0.6, ["beige", "grau", "weiss", "holz"][Math.floor(r() * 4)], -b / 2 + 0.15 + k * (b - 0.3) / 2.4, y + 0.025, 0);
          }
        }
        break;
      }
      case "schrank": if (BS) { schrankTueren(m.hoehe || 1.9, Math.max(2, Math.round(b / 0.6))); break; } K(b, m.hoehe || 1.9, t, korpus, 0, 0, 0); break;
      case "garderobe": K(b, 1.8, t, korpus, 0, 0, 0); break;
      case "esstisch": {
        K(b, 0.04, t, korpus, 0, 0.72, 0);
        if (BS) {                     // Kufengestell aus schwarzem Stahl an beiden Enden, Platte in Holz mit Mittelfuge
          for (const a of [-1, 1]) {
            const x = a * (b / 2 - 0.16);
            K(0.05, 0.03, t - 0.12, "schwarz", x, 0, 0); K(0.05, 0.03, t - 0.12, "schwarz", x, 0.69, 0);
            K(0.05, 0.69, 0.05, "schwarz", x, 0, -(t / 2 - 0.085)); K(0.05, 0.69, 0.05, "schwarz", x, 0, t / 2 - 0.085);
          }
          if (b > 1.4) K(0.006, 0.002, t, "schwarz", 0, 0.761, 0);
        } else
        for (const [a, c] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) K(0.06, 0.72, 0.06, korpus, a * (b / 2 - 0.1), 0, c * (t / 2 - 0.1));
        const n = m.stuehle || 0, je = Math.ceil(n / 2);
        for (let i = 0; i < n; i++) {
          const seite = i < je ? 1 : -1, k = i % je, x = -b / 2 + (k + 0.5) * b / je;
          stuhl(x, seite * (t / 2 + 0.22), seite > 0 ? Math.PI : 0, m.stuhlfarbe || "schwarz");
        }
        // "kopf" = Stuehle an den Kopfenden (1 oder 2), Blick zum Tisch
        for (let i = 0; i < Math.min(2, Math.max(0, m.kopf || 0)); i++) {
          const a = i === 0 ? 1 : -1;
          stuhl(a * (b / 2 + 0.2), 0, a > 0 ? -Math.PI / 2 : Math.PI / 2, m.stuhlfarbe || "schwarz");
        }
        break;
      }
      case "schreibtisch": {
        K(b, 0.04, t, korpus, 0, 0.72, 0);
        K(0.04, 0.72, t - 0.04, korpus, -b / 2 + 0.03, 0, 0); K(0.04, 0.72, t - 0.04, korpus, b / 2 - 0.03, 0, 0);
        const n = m.monitore || 0;
        for (let i = 0; i < n; i++) {
          const x = (i - (n - 1) / 2) * 0.58, w = 0.55, dreh = (i - (n - 1) / 2) * 0.32;
          const mo = new THREE.Group();
          const rahmen = new THREE.Mesh(new THREE.BoxGeometry(w, 0.33, 0.03), mat("schwarz")); rahmen.position.y = 0.2; rahmen.castShadow = true; mo.add(rahmen);
          const sch = new THREE.Mesh(new THREE.BoxGeometry(w - 0.03, 0.3, 0.004), mat("bild")); sch.position.set(0, 0.2, 0.017); sch.userData.bildschirm = true; mo.add(sch);
          const fuss = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.12, 0.04), mat("schwarz")); fuss.position.y = 0.0; mo.add(fuss);
          mo.position.set(x, 0.82, -t / 2 + 0.18 + Math.abs(dreh) * 0.12); mo.rotation.y = -dreh; g.add(mo);
        }
        K(0.45, 0.02, 0.15, "schwarz", 0, 0.76, 0.1);
        // "unten" = [links, rechts] aus Sicht der Person am Tisch (lokal +z), z. B. ["pc", "nas"]
        const unten = Array.isArray(m.unten) ? m.unten : [];
        unten.slice(0, 2).forEach((art, i) => {
          const seite = i === 0 ? -1 : 1, rand = seite * (b / 2 - 0.07);
          if (art === "pc") {                       // Midi-Tower, Front mit Glasstreifen und Einschalter
            const w = 0.21, h = 0.46, d = 0.45, cx = rand - seite * w / 2;
            K(w, h, d, "schwarz", cx, 0.02, 0);
            K(w - 0.04, h - 0.08, 0.006, "schwarzglas", cx, 0.06, d / 2 + 0.003);
            K(0.02, 0.02, 0.006, "metall", cx, h - 0.03, d / 2 + 0.004);
          } else if (art === "nas") {               // NAS mit 5 Schaechten: schwarz, fuenf Laufwerksschaechte vorn
            const w = 0.2, h = 0.17, d = 0.23, cx = rand - seite * w / 2;
            K(w, h, d, "schwarz", cx, 0.02, 0.06);
            for (let j = 0; j < 5; j++) K(0.032, 0.12, 0.005, "anthrazit", cx - 0.076 + j * 0.038, 0.035, 0.06 + d / 2 + 0.002);
          }
        });
        break;
      }
      case "epiano": {
        // E-Piano: Keyboard auf X-Staender
        // mit Notenpult, davor eine Bank; gespielt wird von lokal +z
        const w = Math.min(b, 1.3), zk = -t / 2 + 0.17, zb = zk + 0.62;
        for (const dz of [-0.07, 0.07]) for (const r of [-0.62, 0.62]) {
          const st = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.9, 0.03), mat("schwarz"));
          st.position.set(0, 0.37, zk + dz); st.rotation.z = r; st.castShadow = true; g.add(st);
        }
        for (const sx of [-1, 1]) K(0.04, 0.03, 0.38, "schwarz", sx * 0.32, 0.68, zk);
        K(w, 0.11, 0.32, "schwarz", 0, 0.71, zk);
        const kw = 0.0235, nw = Math.floor((w - 0.12) / kw), x0 = -nw * kw / 2;
        K(nw * kw, 0.022, 0.15, "weiss", 0, 0.8, zk + 0.075);
        for (let i = 0; i < nw - 1; i++) if ([1, 1, 0, 1, 1, 1, 0][i % 7]) K(0.012, 0.014, 0.09, "schwarz", x0 + (i + 1) * kw, 0.822, zk + 0.045);
        K(nw * kw, 0.02, 0.09, "anthrazit", 0, 0.8, zk - 0.1);
        const pult = K(0.62, 0.24, 0.012, "schwarz", 0, 0.83, zk - 0.13); pult.rotation.x = -0.22;
        for (const sx of [-1, 1]) for (const sz of [-1, 1]) K(0.035, 0.47, 0.035, "schwarz", sx * 0.26, 0, zb + sz * 0.11);
        P(0.62, 0.06, 0.32, "schwarz", 0, 0.47, zb, 0.03);
        break;
      }
      case "buerostuhl": {
        Z(0.03, 0.42, "schwarz", 0, 0.02, 0, 8); K(0.5, 0.06, 0.48, "schwarz", 0, 0.44, 0); K(0.46, 0.55, 0.06, "schwarz", 0, 0.5, -0.22);
        K(0.55, 0.03, 0.06, "metall", 0, 0.0, 0); K(0.06, 0.03, 0.55, "metall", 0, 0.0, 0);
        break;
      }
      case "sideboard": case "kommode": case "lowboard": {
        const h = m.hoehe || (m.typ === "kommode" ? 0.9 : m.typ === "lowboard" ? 0.48 : 0.75);
        if (BS) {                     // seit 04.11.2026: Tueren und Schubladen mit Schattenfuge und Metallgriffen, Sockel
          const front = /_anthrazit$/.test(f) ? "anthrazit" : korpus, sock = 0.06, zf = t / 2 + 0.004;
          K(b, h - 0.03, t - 0.02, korpus, 0, 0, -0.01); K(b + 0.01, 0.03, t + 0.01, platte, 0, h - 0.03, 0);
          K(b - 0.04, sock, 0.01, "schwarz", 0, 0, t / 2 - 0.03);
          const fh = h - 0.03 - sock - 0.008, y0 = sock + 0.004;
          K(b - 0.02, fh + 0.004, 0.004, "schwarz", 0, y0 - 0.002, t / 2 - 0.004);
          const feld = (x0, w, y, hh, art) => {
            K(w - 0.006, hh - 0.006, 0.018, front, x0 + w / 2, y + 0.003, zf);
            if (art === "schub") K(Math.min(0.18, w * 0.45), 0.014, 0.02, "metall", x0 + w / 2, y + hh - 0.07, zf + 0.018);
            else K(0.014, Math.min(0.18, hh * 0.4), 0.02, "metall", art === "links" ? x0 + w - 0.05 : x0 + 0.05, y + hh / 2 - 0.05, zf + 0.018);
          };
          if (m.typ === "kommode") { const nn = Math.max(3, Math.round(fh / 0.24)); for (let j = 0; j < nn; j++) feld(-b / 2 + 0.01, b - 0.02, y0 + j * fh / nn, fh / nn, "schub"); }
          else if (b >= 1.2) {
            const wt = (b - 0.02) * 0.3, wm = b - 0.02 - 2 * wt, x0 = -b / 2 + 0.01;
            feld(x0, wt, y0, fh, "links"); feld(x0 + wt + wm, wt, y0, fh, "rechts");
            for (let j = 0; j < 3; j++) feld(x0 + wt, wm, y0 + j * fh / 3, fh / 3, "schub");
          } else { const nn = Math.max(1, Math.round(b / 0.5)), w = (b - 0.02) / nn; for (let i = 0; i < nn; i++) feld(-b / 2 + 0.01 + i * w, w, y0, fh, i % 2 ? "rechts" : "links"); }
          break;
        }
        K(b, h - 0.03, t, korpus, 0, 0.0, 0); K(b + 0.01, 0.03, t + 0.01, platte, 0, h - 0.03, 0);
        const n = Math.max(2, Math.round(b / 0.45));
        for (let i = 1; i < n; i++) K(0.008, h - 0.1, 0.01, "schwarz", -b / 2 + i * b / n, 0.04, t / 2 + 0.002);
        break;
      }
      case "getraenkekuehlschrank":
        if (BS) {                     // Glastuer mit beleuchtetem Innenraum, Boeden und Flaschen
          const h = m.hoehe || 0.85;
          K(b, h, 0.03, "schwarz", 0, 0, -t / 2 + 0.015); K(0.03, h, t, "schwarz", -b / 2 + 0.015, 0, 0); K(0.03, h, t, "schwarz", b / 2 - 0.015, 0, 0);
          K(b, 0.06, t, "schwarz", 0, 0, 0); K(b, 0.04, t, "schwarz", 0, h - 0.04, 0);
          K(b - 0.07, h - 0.12, 0.005, "kuehlglas", 0, 0.06, -t / 2 + 0.035);
          const r = zufall(Math.round(Math.abs(m.x * 37 + m.y * 11)) + 9), nb = Math.max(2, Math.round((h - 0.12) / 0.22));
          for (let j = 0; j < nb; j++) {
            const y = 0.06 + j * (h - 0.12) / nb;
            K(b - 0.07, 0.008, t - 0.08, "metall", 0, y, 0);
            for (let x = -b / 2 + 0.07; x < b / 2 - 0.06; x += 0.055)
              Z(0.022, 0.15 + r() * 0.04, ["gruen", "braun_glas", "rot", "gelb", "glas_weiss"][Math.floor(r() * 5)], x, y + 0.008, -0.02 + r() * 0.06, 8);
          }
          K(b - 0.04, h - 0.06, 0.012, "glas", 0, 0.04, t / 2 - 0.006);
          K(0.015, 0.4, 0.02, "metall", b / 2 - 0.05, h * 0.35, t / 2 + 0.01);
          break;
        }
        K(b, 0.85, t, "schwarz", 0, 0, 0); K(b - 0.06, 0.75, 0.01, "kuehlglas", 0, 0.06, t / 2 + 0.005); break;
      case "kratzbaum": {
        Z(0.05, 1.5, "beige", -0.12, 0, -0.1, 10); Z(0.05, 1.1, "beige", 0.14, 0, 0.1, 10);
        K(0.5, 0.04, 0.5, "beige", 0, 0, 0); K(0.38, 0.05, 0.32, "beige", -0.05, 0.6, -0.05); K(0.36, 0.05, 0.3, "beige", 0.07, 1.1, 0.07); K(0.34, 0.05, 0.3, "beige", -0.1, 1.5, -0.08);
        break;
      }
      case "ecksofa": {
        // langer Teil an der Rueckseite (lokal -z), Arm an der Ecke ueber die volle Tiefe; ecke als Himmelsrichtung
        const th = (m.drehung || 0) * Math.PI / 180, plusX = [Math.cos(th), -Math.sin(th)];       // Welt-Richtung von lokal +x
        const ziel = { ost: [1, 0], west: [-1, 0], nord: [0, -1], sued: [0, 1] }[m.ecke] || [1, 0];
        const s = plusX[0] * ziel[0] + plusX[1] * ziel[1] >= 0 ? 1 : -1, tief = 0.95, stoff = "stoff";
        if (BS) {                     // Stil "bild": Polstersofa mit einzelnen Sitz- und Rueckenkissen, Armlehnen, schwarze Fuesse
          const SO = "stoff_sofa", L0 = 0.18, sk = tief - L0 - 0.02;            // L0: Tiefe der Lehne
          for (const [x, z] of [[-b / 2 + 0.06, -t / 2 + 0.06], [b / 2 - 0.06, -t / 2 + 0.06], [s * (b / 2 - 0.06), t / 2 - 0.06], [s * (b / 2 - tief + 0.06), t / 2 - 0.06], [-s * (b / 2 - 0.06), -t / 2 + tief - 0.06]])
            K(0.05, 0.06, 0.05, "schwarz", x, 0, z);
          P(b, 0.24, tief, SO, 0, 0.05, -t / 2 + tief / 2, 0.03); P(tief, 0.24, t - tief + 0.02, SO, s * (b / 2 - tief / 2), 0.05, tief / 2 - 0.01, 0.03);
          P(b, 0.36, L0, SO, 0, 0.29, -t / 2 + L0 / 2, 0.06); P(L0, 0.36, t - L0, SO, s * (b / 2 - L0 / 2), 0.29, L0 / 2, 0.06);
          P(0.2, 0.22, tief, SO, -s * (b / 2 - 0.1), 0.29, -t / 2 + tief / 2, 0.07);                       // Armlehne am offenen Ende
          P(tief - L0, 0.22, 0.2, SO, s * (b / 2 - L0 - (tief - L0) / 2), 0.29, t / 2 - 0.1, 0.07);        // Armlehne am Ende des Schenkels
          const lang = b - tief - 0.2, nl = Math.max(1, Math.round(lang / 0.75)), kb = lang / nl;
          for (let i = 0; i < nl; i++) {
            const x = -s * (b / 2 - 0.2) + s * (i + 0.5) * kb;
            P(kb - 0.02, 0.15, sk, SO, x, 0.29, -t / 2 + L0 + sk / 2 + 0.01, 0.06);
            P(kb - 0.04, 0.38, 0.15, SO, x, 0.4, -t / 2 + L0 + 0.06, 0.07).rotation.x = -0.16;
          }
          const ex = s * (b / 2 - L0 - (tief - L0) / 2);                                                 // Eckplatz
          P(tief - L0 - 0.02, 0.15, sk, SO, ex, 0.29, -t / 2 + L0 + sk / 2 + 0.01, 0.06);
          P(tief - L0 - 0.04, 0.38, 0.15, SO, ex, 0.4, -t / 2 + L0 + 0.06, 0.07).rotation.x = -0.16;
          const kurz = t - tief - 0.2, nk = Math.max(1, Math.round(kurz / 0.75)), kt = kurz / nk;
          for (let i = 0; i < nk; i++) {
            const z = -t / 2 + tief + (i + 0.5) * kt;
            P(sk, 0.15, kt - 0.02, SO, ex, 0.29, z, 0.06);
            P(0.15, 0.38, kt - 0.04, SO, s * (b / 2 - L0 - 0.06), 0.4, z, 0.07).rotation.z = -s * 0.16;
          }
          break;
        }
        K(b, 0.42, tief, stoff, 0, 0, -t / 2 + tief / 2); K(tief, 0.42, t - tief, stoff, s * (b / 2 - tief / 2), 0, tief / 2);
        K(b, 0.42, 0.2, stoff, 0, 0.42, -t / 2 + 0.1); K(0.2, 0.42, t, stoff, s * (b / 2 - 0.1), 0.42, 0);
        K(0.2, 0.2, tief, stoff, -s * (b / 2 - 0.1), 0.42, -t / 2 + tief / 2);
        for (let i = 0; i < 3; i++) K((b - tief - 0.2) / 3 - 0.03, 0.1, tief - 0.25, "stoff_hell", -s * (b / 2 - 0.2) + s * (i + 0.5) * ((b - tief - 0.2) / 3), 0.42, -t / 2 + 0.2 + (tief - 0.25) / 2);
        K(tief - 0.25, 0.1, t - tief - 0.05, "stoff_hell", s * (b / 2 - 0.2 - (tief - 0.25) / 2), 0.42, tief / 2 + 0.02);
        break;
      }
      case "couchtisch":
        if (BS) {                     // Holztisch auf vier Beinen mit Ablage, Pflanze obenauf
          const holz = /eiche|holz/.test(korpus) ? korpus : "eiche";
          K(b, 0.05, t, holz, 0, 0.36, 0); K(b - 0.08, 0.03, t - 0.08, holz, 0, 0.08, 0);
          for (const [a, c] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) K(0.06, 0.36, 0.06, holz, a * (b / 2 - 0.05), 0, c * (t / 2 - 0.05));
          pflanze(b * 0.12, 0.41, -t * 0.05, 1.1);
          break;
        }
        K(b, 0.05, t, korpus, 0, 0.36, 0); K(b - 0.1, 0.36, t - 0.1, "anthrazit", 0, 0, 0); break;
      case "leinwand": { const h = m.hoehe || 1.4; K(b + 0.06, 0.05, 0.06, "schwarz", 0, (m.z || 1) + h, 0); bild(b, h, 0, m.z || 1, 0.03).userData.leinwand = true; break; }
      case "standbox": K(0.24, 1.05, 0.3, "schwarz", 0, 0, 0); Z(0.06, 0.01, "grau", 0, 0.8, 0.151, 12).rotation.x = Math.PI / 2; break;
      case "beamer": K(m.b || 0.38, 0.13, m.t || 0.32, "weiss", 0, m.z || 2.45, 0);
        if ((m.z || 2.45) > 1.5) K(0.02, 0.15, 0.02, "weiss", 0, (m.z || 2.45) + 0.13, 0);   // Deckenhalter nur oben
        break;
      case "teppich": {
        // "farbe": "sterne" = grauer Teppich mit weissen Sternen (z. B. Kinderzimmer)
        const tm = /^sterne/.test(f) ? new THREE.MeshStandardMaterial({ name: "m:teppich_sterne", map: sternTex(), roughness: 0.98, envMapIntensity: 0.3 }) : mat(f || "grau_hell");
        if (m.rund) { const r = new THREE.Mesh(new THREE.CylinderGeometry(b / 2, b / 2, 0.014, 48), tm); r.position.y = 0.007; r.receiveShadow = true; g.add(r); }
        else { const r = K(b, 0.012, t, tm, 0, 0, 0); r.castShadow = false; }
        break;
      }
      case "poster": {                // seit 04.11.2026: Bild an der Wand, schwarzer Rahmen, eigenes buntes Motiv; z = Unterkante
        const h = m.hoehe || 0.7, z = m.z != null ? m.z : 1.2;
        K(b, h, 0.02, "schwarz", 0, z, 0);
        const p = new THREE.Mesh(new THREE.PlaneGeometry(b - 0.04, h - 0.04), new THREE.MeshStandardMaterial({ name: "m:poster",
          map: posterTex(Math.round(Math.abs(m.x * 53 + m.y * 29)) + 1), roughness: 0.45, envMapIntensity: 0.5 }));
        p.position.set(0, z + h / 2, 0.011); g.add(p);
        break;
      }
      case "pflanze": {
        Z(0.15, 0.32, "anthrazit", 0, 0, 0, 14);
        const k = new THREE.Mesh(new THREE.IcosahedronGeometry(0.32, 1), mat("gruen")); k.position.y = 0.72; k.scale.set(1, 1.3, 1); k.castShadow = true; g.add(k);
        break;
      }
      case "eckwanne": {
        // Eckwanne mit runder Front (Viertelellipse von Wand zu Wand), Ecke bei lokal
        // -x/-z an den Waenden, weisser Rand, Becken folgt der Form, Schuerze schwarz mit senkrechten Lamellen, Wandarmatur
        // mit Handbrause, dahinter auf beiden Waenden dunkle Fliesen bis 1,15 m.
        const H = 0.58, RAND = 0.04, rim = 0.1, ax = -b / 2, az = -t / 2, N = 32, TIEF = 0.42;
        const S2 = (u, v) => new THREE.Vector2(ax + u, -(az + v));        // (u, v) ab der Ecke -> Shape-Koordinaten (x, -z)
        const aussenUV = [[0, 0]];
        for (let i = 0; i <= N; i++) { const th = (i / N) * Math.PI / 2; aussenUV.push([b * Math.cos(th), t * Math.sin(th)]); }
        const bi = b - rim, ti = t - rim, rc = 0.2;
        const th0 = Math.asin(Math.min(0.95, rim / ti)), th1 = Math.acos(Math.min(0.95, rim / bi));
        const innenUV = [];
        for (let i = 0; i <= N; i++) { const th = th0 + (th1 - th0) * i / N; innenUV.push([bi * Math.cos(th), ti * Math.sin(th)]); }
        for (let i = 0; i <= 8; i++) { const w = Math.PI + (Math.PI / 2) * i / 8; innenUV.push([rim + rc + rc * Math.cos(w), rim + rc + rc * Math.sin(w)]); }
        const form = (mitLoch) => {
          const sh = new THREE.Shape(aussenUV.map((p) => S2(p[0], p[1])));
          if (mitLoch) sh.holes.push(new THREE.Path(innenUV.map((p) => S2(p[0], p[1]))));
          return sh;
        };
        const fest = (geo, farbe) => { const me = new THREE.Mesh(geo, typeof farbe === "object" ? farbe : mat(farbe)); me.castShadow = me.receiveShadow = true; g.add(me); return me; };
        const schuerze = new THREE.ExtrudeGeometry(form(true), { depth: H - RAND, bevelEnabled: false });
        schuerze.rotateX(-Math.PI / 2);
        fest(schuerze, BS ? "schwarz" : "weiss");
        const randG = new THREE.ExtrudeGeometry(form(true), { depth: RAND, bevelEnabled: false });
        randG.rotateX(-Math.PI / 2); randG.translate(0, H - RAND, 0);
        fest(randG, "weiss");
        // Becken: Wand als Band vom Rand nach unten, unten zur Mitte eingezogen; Boden als Flaeche. Normalen nach innen.
        const cu = innenUV.reduce((q, p) => q + p[0], 0) / innenUV.length, cv = innenUV.reduce((q, p) => q + p[1], 0) / innenUV.length;
        const unten = innenUV.map((p) => [cu + (p[0] - cu) * 0.8, cv + (p[1] - cv) * 0.8]);
        const yo = H - 0.004, yu = H - TIEF, pos = [], nor = [], uvs = [];
        const W3 = (p, y) => [ax + p[0], y, az + p[1]];
        for (let i = 0; i < innenUV.length; i++) {
          const k2 = (i + 1) % innenUV.length, a = W3(innenUV[i], yo), c = W3(innenUV[k2], yo), d = W3(unten[k2], yu), e = W3(unten[i], yu);
          const v1 = new THREE.Vector3(c[0] - a[0], c[1] - a[1], c[2] - a[2]), v2 = new THREE.Vector3(e[0] - a[0], e[1] - a[1], e[2] - a[2]);
          const n = new THREE.Vector3().crossVectors(v1, v2).normalize();
          const zurMitte = new THREE.Vector3(ax + cu - a[0], 0, az + cv - a[2]);
          const tris = n.dot(zurMitte) >= 0 ? [a, c, d, a, d, e] : [a, d, c, a, e, d];
          if (n.dot(zurMitte) < 0) n.negate();
          for (const q of tris) { pos.push(q[0], q[1], q[2]); nor.push(n.x, n.y, n.z); uvs.push(0, 0); }
        }
        const wandG = new THREE.BufferGeometry();
        wandG.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
        wandG.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
        wandG.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
        fest(wandG, "weiss").castShadow = false;
        const bodenG = new THREE.ShapeGeometry(new THREE.Shape(unten.map((p) => S2(p[0], p[1]))));
        bodenG.rotateX(-Math.PI / 2); bodenG.translate(0, yu, 0);
        fest(bodenG, "weiss").castShadow = false;
        if (BS) {
          // Lamellen der Schuerze entlang der runden Front
          const bogen = (Math.PI / 4) * (b + t), n = Math.max(12, Math.round(bogen / 0.055));
          for (let i = 0; i < n; i++) {
            const th = ((i + 0.5) / n) * Math.PI / 2, x = ax + b * Math.cos(th), z = az + t * Math.sin(th);
            const tx = -b * Math.sin(th), tz = t * Math.cos(th), nx = t * Math.cos(th), nz = b * Math.sin(th), nl = Math.hypot(nx, nz);
            const la = new THREE.Mesh(new THREE.BoxGeometry(0.034, H - RAND - 0.05, 0.012), mat("anthrazit"));
            la.position.set(x + (nx / nl) * 0.004, 0.025 + (H - RAND - 0.05) / 2, z + (nz / nl) * 0.004);
            la.rotation.y = -Math.atan2(tz, tx); la.castShadow = la.receiveShadow = true; g.add(la);
          }
          // Wandarmatur mit Handbrause an der Wand lokal -z
          K(0.18, 0.05, 0.05, "metall", ax + 0.55, H + 0.24, az + 0.035);
          K(0.03, 0.03, 0.13, "metall", ax + 0.55, H + 0.23, az + 0.11);
          K(0.035, 0.035, 0.035, "metall", ax + 0.47, H + 0.25, az + 0.07);
          K(0.04, 0.2, 0.04, "metall", ax + 0.78, H + 0.12, az + 0.05);
        }
        // Fliesenband auf beiden Wandseiten
        const FH = 1.15, f1 = new THREE.Mesh(new THREE.BoxGeometry(b, FH, 0.012), fliesenMat(b, FH));
        f1.position.set(ax + b / 2, FH / 2, az + 0.006); f1.receiveShadow = true; g.add(f1);
        const f2 = new THREE.Mesh(new THREE.BoxGeometry(t, FH, 0.012), fliesenMat(t, FH));
        f2.position.set(ax + 0.006, FH / 2, az + t / 2); f2.rotation.y = Math.PI / 2; f2.receiveShadow = true; g.add(f2);
        break;
      }
      case "wc":
        if (BS) { P(0.36, 0.22, 0.5, "weiss", 0, 0.2, 0.03, 0.09); P(0.37, 0.035, 0.5, "weiss", 0, 0.42, 0.03, 0.06); K(0.4, 0.42, 0.06, "weiss", 0, 0.12, -0.24); break; }  // wandhaengend (Foto)
        K(0.36, 0.4, 0.5, "weiss", 0, 0, 0.03); K(0.36, 0.06, 0.52, "weiss", 0, 0.4, 0.03); K(0.38, 0.3, 0.12, "weiss", 0, 0.5, -0.24); break;
      case "dusche": {
        K(b, 0.03, t, "anthrazit", 0, 0, 0);
        K(b, 2.0, 0.01, "glas", 0, 0.03, t / 2); K(0.01, 2.0, t * 0.6, "glas", b / 2, 0.03, t * 0.2);
        Z(0.012, 0.9, "metall", -b / 2 + 0.15, 1.1, -t / 2 + 0.06);
        break;
      }
      case "waschtisch": {
        if (BS) {          // schwebend, zwei Auszuege, Platte mit Becken, Spiegelschrank, Fliesen
          K(b, 0.5, t, "weiss", 0, 0.34, 0);
          fuge(b - 0.03, 0.006, 0, 0.59, t / 2 + 0.002);
          K(b + 0.02, 0.04, t + 0.02, "weiss", 0, 0.84, 0.01);
          K(b * 0.6, 0.008, t * 0.5, "grau_hell", 0, 0.881, 0.04);
          K(0.03, 0.12, 0.03, "metall", 0, 0.88, -t / 2 + 0.07); K(0.026, 0.026, 0.11, "metall", 0, 0.98, -t / 2 + 0.11);
          const fb = new THREE.Mesh(new THREE.BoxGeometry(b + 0.12, 0.36, 0.012), fliesenMat(b + 0.12, 0.36));
          fb.position.set(0, 0.88 + 0.18, -t / 2 + 0.006); fb.receiveShadow = true; g.add(fb);
          if (m.spiegel) { K(b + 0.08, 0.66, 0.13, "weiss", 0, 1.24, -t / 2 + 0.065); K(b + 0.04, 0.62, 0.01, "spiegel", 0, 1.26, -t / 2 + 0.135); }
          break;
        }
        K(b, 0.45, t, "weiss", 0, 0.4, 0); K(b * 0.7, 0.02, t * 0.6, "weiss", 0, 0.85, 0.02);
        if (m.spiegel) K(b + 0.1, 0.75, 0.03, "spiegel", 0, 1.05, -t / 2 + 0.02);
        break;
      }
      case "bett": case "kinderbett": case "doppelbett": {
        const kind = m.typ === "kinderbett", rahmen = /^grau/.test(korpus) ? "stoff" : korpus;
        if (BS) {                     // Stil "bild": Bettzeug in Lagen (Decke, Plaid am Fussende, weiche Kissen), Kopfteil gepolstert
          const dop = m.typ === "doppelbett", hR = kind ? 0.22 : 0.3, hM = 0.18, oben = hR + hM;
          const decke = dop ? "beige" : kind ? "stoff_weiss" : "stoff_hell", plaid = dop ? "stoff_braun" : kind ? "rosa" : "stoff_sofa";
          if (rahmen === "stoff") P(b, hR, t, "stoff", 0, 0, 0, 0.04); else K(b, hR, t, rahmen, 0, 0, 0);
          P(b - 0.06, hM, t - 0.08, "stoff_weiss", 0, hR, 0.02, 0.04);                                   // Matratze
          bettzeug(b - 0.06, t - 0.08, oben, decke, plaid, dop ? 2 : 1, 0.02);
          if (dop) {
            K(b + 0.12, 1.0, 0.08, "eiche", 0, 0.0, -t / 2 - 0.02);
            kopfteil(b - 0.1, 0.46, -t / 2 + 0.05, "stoff_dunkel", 0.5);
            for (const x of [-b / 4, b / 4]) P(b / 2 - 0.34, 0.14, 0.16, "stoff_braun", x, oben + 0.1, -t / 2 + 0.52, 0.06).rotation.x = -0.4;
          } else kopfteil(b, kind ? 0.6 : 0.8, -t / 2 + 0.04, rahmen === "stoff" ? "stoff" : rahmen);
          if (kind) for (let i = 0; i < 9; i++) K(0.025, 0.3, 0.025, rahmen, -b / 2 + 0.1 + i * (b - 0.2) / 8, hR, t / 2 - 0.02);
          if (m.mit === "kuscheltiere") kuscheltiere(b - 0.1, oben + 0.04, -t / 2 + 0.62);
          if (m.mit === "bank") bank(b, t);
          break;
        }
        K(b, kind ? 0.25 : 0.32, t, rahmen, 0, 0, 0);
        K(b - 0.08, 0.17, t - 0.08, "stoff_weiss", 0, kind ? 0.25 : 0.32, 0.02);
        K(b - 0.04, 0.05, t * 0.6, m.typ === "doppelbett" ? "rot" : kind ? "rosa" : "blau", 0, kind ? 0.42 : 0.49, t * 0.18);
        const kissen = m.typ === "doppelbett" ? [-b / 4, b / 4] : [0];
        for (const x of kissen) K(m.typ === "doppelbett" ? b / 2 - 0.12 : b - 0.25, 0.1, 0.32, "stoff_weiss", x, kind ? 0.42 : 0.49, -t / 2 + 0.24);
        if (m.typ === "doppelbett") K(b + 0.12, 1.0, 0.08, "eiche", 0, 0.0, -t / 2 - 0.02);
        else K(b, kind ? 0.6 : 0.7, 0.05, rahmen, 0, 0, -t / 2 + 0.025);
        if (kind) for (let i = 0; i < 9; i++) K(0.025, 0.3, 0.025, rahmen, -b / 2 + 0.1 + i * (b - 0.2) / 8, 0.25, t / 2 - 0.02);
        break;
      }
      case "bodenbett": {      // Bodenbett: Rahmen knapp ueber dem Boden, Matratze, Gitter an Laengsseite und Fussende
        const rahmen = korpus;
        K(b, 0.08, t, rahmen, 0, 0, 0);
        if (BS) {                     // seit 04.11.2026: Bettzeug wie bei den anderen Betten, laengs zur x-Achse
          P(b - 0.08, 0.16, t - 0.08, "stoff_weiss", 0, 0.08, 0, 0.04);
          const vor = g.children.length;
          bettzeug(t - 0.12, b - 0.12, 0.24, "stoff_weiss", "rosa", 1, 0);
          const q = new THREE.Group(); q.rotation.y = Math.PI / 2;
          for (const c of g.children.slice(vor)) q.add(c);
          g.add(q);
        } else {
          K(b - 0.08, 0.16, t - 0.08, "weiss", 0, 0.08, 0);
          K(b - 0.1, 0.05, t * 0.6, "rosa", 0, 0.24, t * 0.15); K(0.55, 0.1, 0.32, "weiss", -b / 2 + 0.35, 0.24, -t / 2 + 0.24);
        }
        K(b, 0.04, 0.04, rahmen, 0, 0.42, t / 2 - 0.02); K(0.04, 0.04, t, rahmen, b / 2 - 0.02, 0.42, 0);
        for (let i = 0; i <= 12; i++) K(0.025, 0.34, 0.025, rahmen, -b / 2 + 0.05 + i * (b - 0.1) / 12, 0.08, t / 2 - 0.02);
        for (let i = 0; i <= 6; i++) K(0.025, 0.34, 0.025, rahmen, b / 2 - 0.02, 0.08, -t / 2 + 0.05 + i * (t - 0.1) / 6);
        break;
      }
      case "kallax": {
        const h = m.hoehe || 1.47, nx = Math.max(1, Math.round(b / 0.39)), ny = Math.max(1, Math.round(h / 0.39));
        K(b, h, t * 0.25, korpus, 0, 0, -t * 0.375);
        for (let i = 0; i <= nx; i++) K(0.03, h, t, korpus, -b / 2 + i * (b / nx), 0, 0);
        for (let j = 0; j <= ny; j++) K(b, 0.03, t, korpus, 0, j * (h - 0.03) / ny, 0);
        const r = zufall(Math.round(Math.abs(m.x * 31 + m.y * 17)) + 3);
        for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) if (r() > 0.35) K(0.18 + r() * 0.1, 0.12 + r() * 0.14, 0.2, ["rot", "blau", "rosa", "gruen", "beige", "grau"][Math.floor(r() * 6)], -b / 2 + (i + 0.5) * (b / nx), j * (h - 0.03) / ny + 0.03, 0.02);
        break;
      }
      case "fernseher": {
        const h = m.hoehe || 0.65, z = m.z || 0.8;
        K(b, h, 0.05, "schwarz", 0, z, 0); bild(b - 0.03, h - 0.03, 0, z + 0.015, 0.03);
        K(0.3, 0.02, 0.18, "schwarz", 0, z - 0.06, 0); K(0.05, 0.06, 0.05, "schwarz", 0, z - 0.05, 0);
        break;
      }
      case "katzenklo": K(b, 0.17, t, "grau", 0, 0, 0); K(b - 0.04, 0.26, t - 0.04, "grau_hell", 0, 0.17, 0); K(0.2, 0.18, 0.01, "schwarz", 0, 0.12, t / 2 - 0.01); break;
      case "wandregal": {
        const z = m.z || 1.6, h = m.hoehe || 0.3;
        K(b, 0.025, t, korpus, 0, z, 0); K(b, 0.025, t, korpus, 0, z + h, 0); K(b, h, 0.02, korpus, 0, z, -t / 2 + 0.01);
        K(0.025, h, t, korpus, -b / 2 + 0.0125, z, 0); K(0.025, h, t, korpus, b / 2 - 0.0125, z, 0);
        break;
      }
      case "klavier": K(b, 1.2, t, "schwarz", 0, 0, 0); K(b - 0.1, 0.05, 0.22, "weiss", 0, 0.72, t / 2 + 0.11); K(b - 0.1, 0.02, 0.06, "schwarz", 0, 0.77, t / 2 + 0.03); break;
      case "tafel":
        if (BS) {                     // seit 04.11.2026: Staffelei, rosa A-Gestell, Kreidetafel, Papierrolle, Ablage mit Kreide
          const bein = (x, z, neig) => { const e = new THREE.Mesh(new THREE.BoxGeometry(0.035, 1.25, 0.035), mat("rosa")); e.position.set(x, 0.6, z); e.rotation.x = neig; e.castShadow = true; g.add(e); };
          for (const x of [-b / 2 + 0.03, b / 2 - 0.03]) { bein(x, 0.08, -0.14); bein(x, -0.08, 0.14); }
          const tf = new THREE.Mesh(new THREE.BoxGeometry(b - 0.06, 0.58, 0.018), mat("tafel")); tf.position.set(0, 0.86, 0.06); tf.rotation.x = -0.14; tf.castShadow = true; g.add(tf);
          const rolle = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, b - 0.04, 14), mat("weiss")); rolle.rotation.z = Math.PI / 2; rolle.position.set(0, 1.19, 0.02); g.add(rolle);
          K(b - 0.04, 0.02, 0.09, "rosa", 0, 0.5, 0.12);
          ["rot", "gelb", "blau", "weiss"].forEach((c, i) => { const k = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.07, 6), mat(c)); k.rotation.z = Math.PI / 2; k.position.set(-0.15 + i * 0.1, 0.53, 0.12); g.add(k); });
          break;
        }
        K(b, 0.85, 0.03, "tafel", 0, 0.5, 0); K(0.04, 1.4, 0.04, "rosa", -b / 2, 0, 0.05); K(0.04, 1.4, 0.04, "rosa", b / 2, 0, 0.05); break;
      case "kindertisch": {
        K(b, 0.03, t, "weiss", 0, 0.5, 0);
        for (const [a, c] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) K(0.04, 0.5, 0.04, "weiss", a * (b / 2 - 0.05), 0, c * (t / 2 - 0.05));
        for (let i = 0; i < (m.stuehle || 0); i++) stuhl((i ? 1 : -1) * (b / 2 + 0.18), 0, (i ? -1 : 1) * Math.PI / 2, i ? "rosa" : "blau", 0.65);
        if (BS) {                     // Malpapier und Stiftebecher
          K(0.21, 0.004, 0.29, "weiss", -0.08, 0.53, 0.02).rotation.y = 0.2;
          Z(0.03, 0.07, "rosa", b / 2 - 0.12, 0.53, -t / 2 + 0.12, 12);
          ["rot", "blau", "gelb", "gruen"].forEach((c, i) => Z(0.004, 0.11, c, b / 2 - 0.13 + (i % 2) * 0.015, 0.56, -t / 2 + 0.11 + (i > 1 ? 0.015 : 0), 5));
        }
        break;
      }
      case "kleiderschrank": if (BS) { schrankTueren(m.hoehe || 2.0, Math.max(2, Math.round(b / 0.55))); break; } K(b, m.hoehe || 2.0, t, korpus, 0, 0, 0); K(0.02, 1.2, 0.03, "eiche", -0.05, 0.5, t / 2 + 0.01); K(0.02, 1.2, 0.03, "eiche", 0.05, 0.5, t / 2 + 0.01); break;
      case "wandschrank": K(b, m.hoehe || 1.0, t, korpus, 0, 0, 0); break;
      case "nachttisch":
        if (BS) {                     // Schublade mit Griff, darunter offenes Fach
          K(b, 0.48, t, korpus, 0, 0, 0);
          K(b - 0.03, 0.15, 0.016, korpus, 0, 0.3, t / 2 + 0.006); K(b - 0.02, 0.004, 0.004, "schwarz", 0, 0.295, t / 2 + 0.002);
          K(0.12, 0.012, 0.02, "metall", 0, 0.37, t / 2 + 0.022); K(b - 0.06, 0.2, 0.004, "schwarz", 0, 0.06, t / 2 + 0.001);
          break;
        }
        K(b, 0.45, t, korpus, 0, 0, 0); break;
      case "spiegelschrank": {
        const h = m.hoehe || 2.2;
        if (BS) {                     // seit 04.11.2026: Schwebetuerenschrank - Eichenrahmen, Spiegeltuer und dunkle Tuer mit
          const holz = platte === korpus ? "eiche" : platte, dw = b / 2 + 0.02;   // Spiegelstreifen, Alu-Profile, Laufschiene
          K(b, h, t - 0.06, korpus, 0, 0, -0.03);
          K(b, 0.05, t, holz, 0, h - 0.05, 0); K(b, 0.07, t, holz, 0, 0, 0);
          for (const sx of [-1, 1]) K(0.035, h, t, holz, sx * (b / 2 - 0.0175), 0, 0);
          K(b - 0.06, 0.02, 0.05, "metall", 0, h - 0.075, t / 2 - 0.035);
          const tuer = (x, z, voll) => {
            K(dw - 0.06, h - 0.16, 0.02, voll ? "spiegel" : korpus, x, 0.08, z);
            if (!voll) K((dw - 0.06) * 0.34, h - 0.4, 0.006, "spiegel", x, 0.2, z + 0.012);
            for (const sx of [-1, 1]) K(0.018, h - 0.15, 0.03, "metall", x + sx * (dw - 0.06) / 2, 0.075, z);
            K(dw - 0.04, 0.02, 0.03, "metall", x, 0.075, z); K(dw - 0.04, 0.02, 0.03, "metall", x, h - 0.095, z);
          };
          tuer(-b / 4 + 0.015, t / 2 - 0.02, true); tuer(b / 4 - 0.015, t / 2 - 0.05, false);
          break;
        }
        K(b, h, t, korpus, 0, 0, 0); K(b * 0.62, h - 0.1, 0.02, "spiegel", 0, 0.05, t / 2 + 0.005);
        K(b - 0.04, 0.3, 0.04, "eiche", 0, 0.85, t / 2 + 0.02);
        break;
      }
      case "klimageraet": K(b, 0.75, t, "weiss", 0, 0, 0); K(b * 0.8, 0.3, 0.01, "grau", 0, 0.35, t / 2 + 0.003); Z(0.06, 0.6, "weiss", 0, 0.75, -t / 2 + 0.08, 10); break;
      case "werkbank":
        if (BS) {                     // seit 04.11.2026: Eichenplatte, Gestell, Schubladenblock, Lochwand mit Werkzeug dahinter
          K(b, 0.05, t, "eiche", 0, 0.85, 0);
          for (const [a, c] of [[-1, -1], [-1, 1]]) K(0.05, 0.85, 0.05, "anthrazit", a * (b / 2 - 0.05), 0, c * (t / 2 - 0.05));
          K(0.45, 0.8, t - 0.06, "anthrazit", b / 2 - 0.25, 0.04, 0);
          for (let j = 0; j < 4; j++) { K(0.42, 0.004, 0.004, "schwarz", b / 2 - 0.25, 0.04 + (j + 1) * 0.2, t / 2 - 0.028); K(0.12, 0.012, 0.02, "metall", b / 2 - 0.25, 0.04 + j * 0.2 + 0.15, t / 2 - 0.02); }
          K(b - 0.55, 0.03, t - 0.1, "eiche", -0.22, 0.18, 0);
          K(b, 0.7, 0.018, "grau_hell", 0, 1.02, -t / 2 + 0.01);
          const r = zufall(Math.round(Math.abs(m.x * 41 + m.y * 13)) + 7);
          for (let i = 0; i < 16; i++) {
            const w = 0.025 + r() * 0.05, hh = 0.1 + r() * 0.18;
            K(w, hh, 0.02, ["rot", "gelb", "schwarz", "metall", "blau", "gruen"][Math.floor(r() * 6)], -b / 2 + 0.1 + i * (b - 0.2) / 15, 1.08 + r() * (0.62 - hh), -t / 2 + 0.03);
          }
          K(0.38, 0.16, 0.2, "rot", -b / 2 + 0.35, 0.9, 0.0); K(0.2, 0.12, 0.14, "gelb", -0.05, 0.9, 0.05);
          break;
        }
        K(b, 0.05, t, "holz", 0, 0.85, 0); for (const [a, c] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) K(0.06, 0.85, 0.06, "metall", a * (b / 2 - 0.06), 0, c * (t / 2 - 0.06)); K(b, 0.03, t - 0.1, "holz", 0, 0.2, 0); break;
      case "schacht": K(b, m.hoehe || 2.6, t, "wand", 0, 0, 0); break;   // Kamin- oder Installationsschacht in Wandfarbe
      case "kiste": {          // Karton oder verpackte Ware (farbe blau = Folienpaket), optional auf Palette, stapelbar per z
        const z0 = m.z || 0, h = m.hoehe || 0.5, pal = m.mit === "palette" ? 0.14 : 0;
        if (pal) K(b, pal, t, "holz", 0, z0, 0);
        const kf = ["blau", "grau", "gelb", "weiss", "schwarz"].includes(f) ? f : "karton";
        K(b - (pal ? 0.04 : 0), h, t - (pal ? 0.04 : 0), kf, 0, z0 + pal, 0);
        if (BS && kf === "karton") {   // seit 04.11.2026: Klebeband ueber Deckel und Stirnseite, Etikett
          K(b - (pal ? 0.04 : 0) + 0.004, 0.003, 0.06, "band", 0, z0 + pal + h, 0);
          K(0.06, Math.min(0.12, h * 0.4), 0.003, "band", 0, z0 + pal + h - Math.min(0.12, h * 0.4), (t - (pal ? 0.04 : 0)) / 2 + 0.001);
          if (b > 0.35) K(0.14, 0.09, 0.002, "weiss", -b / 4, z0 + pal + h * 0.45, (t - (pal ? 0.04 : 0)) / 2 + 0.002);
        }
        break;
      }
      case "gartenstuehle": {  // gestapelte Gartenstuehle mit Auflagen
        for (let i = 0; i < 4; i++) { K(b, 0.035, t, "schwarz", 0, 0.12 + i * 0.13, 0); K(b - 0.06, 0.05, t - 0.06, "rot", 0, 0.155 + i * 0.13, 0); }
        for (const [a, c] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) K(0.03, 0.66, 0.03, "schwarz", a * (b / 2 - 0.03), 0, c * (t / 2 - 0.03));
        break;
      }
      case "roller": K(0.13, 0.03, t - 0.1, "rot", 0, 0.07, 0); K(0.03, 0.72, 0.03, "rot", 0, 0.08, t / 2 - 0.08); K(0.34, 0.03, 0.03, "schwarz", 0, 0.8, t / 2 - 0.08); break;
      case "fahrrad": case "laufrad": {
        if (BS) {                     // seit 04.11.2026: Reifen, Felgen mit Speichen, Rahmenrohre, Kettenblatt, Sattel, Lenker
          const rf = /^(rot|blau|gruen|gelb|schwarz|grau|weiss)$/.test(f) ? f : "rot";
          const rohr = (x1, y1, x2, y2, rr, farbe, zz) => {
            const c = new THREE.Mesh(new THREE.CylinderGeometry(rr, rr, Math.hypot(x2 - x1, y2 - y1), 8), mat(farbe));
            c.position.set((x1 + x2) / 2, (y1 + y2) / 2, zz || 0); c.rotation.z = Math.atan2(-(x2 - x1), y2 - y1); c.castShadow = true; g.add(c);
          };
          for (const x of [-0.5, 0.5]) {
            const re = new THREE.Mesh(new THREE.TorusGeometry(0.31, 0.024, 8, 32), mat("schwarz")); re.position.set(x, 0.34, 0); re.castShadow = true; g.add(re);
            const fe = new THREE.Mesh(new THREE.TorusGeometry(0.28, 0.008, 6, 32), mat("metall")); fe.position.set(x, 0.34, 0); g.add(fe);
            for (let i = 0; i < 12; i++) { const sp = new THREE.Mesh(new THREE.CylinderGeometry(0.0025, 0.0025, 0.56, 3), mat("metall")); sp.position.set(x, 0.34, 0); sp.rotation.z = i * Math.PI / 12; g.add(sp); }
            const na = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.1, 10), mat("metall")); na.rotation.x = Math.PI / 2; na.position.set(x, 0.34, 0); g.add(na);
          }
          rohr(-0.05, 0.3, -0.15, 0.82, 0.018, rf); rohr(-0.15, 0.8, 0.38, 0.84, 0.018, rf); rohr(-0.05, 0.3, 0.41, 0.68, 0.02, rf);
          rohr(-0.5, 0.34, -0.05, 0.3, 0.012, rf, 0.05); rohr(-0.5, 0.34, -0.15, 0.8, 0.012, rf, 0.05);
          rohr(0.38, 0.86, 0.42, 0.66, 0.022, rf); rohr(0.42, 0.66, 0.5, 0.34, 0.014, "metall");
          rohr(0.37, 0.86, 0.36, 0.98, 0.014, "schwarz");
          const le = new THREE.Mesh(new THREE.CylinderGeometry(0.013, 0.013, 0.52, 8), mat("schwarz")); le.rotation.x = Math.PI / 2; le.position.set(0.35, 0.98, 0); g.add(le);
          rohr(-0.15, 0.82, -0.17, 0.9, 0.012, "metall"); K(0.24, 0.05, 0.1, "schwarz", -0.2, 0.89, 0);
          const kb = new THREE.Mesh(new THREE.TorusGeometry(0.09, 0.008, 6, 24), mat("metall")); kb.position.set(-0.05, 0.3, 0.05); g.add(kb);
          for (const sz of [-1, 1]) K(0.09, 0.02, 0.05, "schwarz", -0.05 + sz * 0.14, 0.24 + sz * 0.1, sz * 0.12);
          break;
        }
        for (const x of [-0.5, 0.5]) { const r = new THREE.Mesh(new THREE.TorusGeometry(0.33, 0.025, 8, 24), mat("schwarz")); r.position.set(x, 0.34, 0); r.castShadow = true; g.add(r); }
        const st = K(1.0, 0.035, 0.035, "rot", 0, 0.52, 0); st.rotation.z = 0.15; K(0.04, 0.4, 0.04, "rot", -0.15, 0.4, 0); K(0.2, 0.04, 0.08, "schwarz", -0.15, 0.82, 0); K(0.04, 0.5, 0.45, "schwarz", 0.42, 0.55, 0);
        break;
      }
      case "heizung":
        if (BS) {                     // seit 04.11.2026: Gastherme mit Display und Abgasrohr, Kupferleitungen nach unten
          K(b, 0.72, t, "weiss", 0, 1.0, 0); K(b * 0.55, 0.09, 0.008, "schwarzglas", 0, 1.1, t / 2 + 0.004);
          K(b - 0.04, 0.004, 0.004, "grau_hell", 0, 1.22, t / 2 + 0.002);
          Z(0.06, 0.3, "weiss", 0, 1.72, 0, 16);
          [[-0.13, "kupfer"], [-0.05, "kupfer"], [0.03, "metall"], [0.11, "kupfer"]].forEach(([x, c]) => Z(0.013, 1.0, c, x, 0, 0.02, 8));
          Z(0.12, 0.3, "rot", b / 2 + 0.16, 0.15, 0, 18);
          break;
        }
        K(b, 0.72, t, "weiss", 0, 1.0, 0); K(0.06, 1.0, 0.06, "metall", -0.1, 0, 0); K(0.06, 1.0, 0.06, "metall", 0.1, 0, 0); break;
      case "speicher":
        if (BS) {                     // Warmwasserspeicher: Sockel, Kuppel, Anschluesse in Kupfer, Thermometer
          Z(b / 2 - 0.02, 0.06, "grau", 0, 0, 0, 32); Z(b / 2, 1.42, "weiss", 0, 0.06, 0, 32);
          const ku = new THREE.Mesh(new THREE.SphereGeometry(b / 2, 32, 10, 0, Math.PI * 2, 0, Math.PI / 2), mat("weiss")); ku.scale.y = 0.3; ku.position.y = 1.48; ku.castShadow = true; g.add(ku);
          for (const x of [-0.08, 0.08]) Z(0.014, 0.8, "kupfer", x, 1.55, 0, 8);
          const th = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.02, 20), mat("grau")); th.rotation.x = Math.PI / 2; th.position.set(0, 0.9, b / 2 + 0.005); g.add(th);
          break;
        }
        Z(b / 2, 1.6, "weiss", 0, 0, 0, 24); break;
      case "truhe":
        if (BS) {                     // Gefriertruhe: Korpus, Sockel, Deckel mit Fuge, Griffmulde
          K(b - 0.04, 0.06, t - 0.04, "grau", 0, 0, 0); K(b, 0.76, t, "weiss", 0, 0.05, 0);
          K(b + 0.012, 0.07, t + 0.012, "weiss", 0, 0.81, 0); K(b + 0.006, 0.004, 0.004, "grau", 0, 0.81, t / 2 + 0.007);
          K(0.24, 0.035, 0.03, "grau_hell", 0, 0.775, t / 2 + 0.02); K(0.07, 0.02, 0.004, "grau", b / 2 - 0.12, 0.6, t / 2 + 0.003);
          break;
        }
        K(b, 0.85, t, "weiss", 0, 0, 0); K(b, 0.04, t, "grau_hell", 0, 0.85, 0); break;
      case "waschmaschine": case "trockner": {
        if (BS) {                     // seit 04.11.2026: Bullauge mit Chromring, Bedienblende, Display, Drehknopf, Schublade
          K(b, 0.85, t, "weiss", 0, 0, 0);
          K(b - 0.03, 0.11, 0.012, "weiss", 0, 0.72, t / 2 + 0.004);
          K(0.17, 0.06, 0.01, "grau_hell", -b / 2 + 0.12, 0.745, t / 2 + 0.011);
          K(0.13, 0.035, 0.004, "schwarzglas", 0.06, 0.758, t / 2 + 0.011);
          const kn = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.028, 0.02, 20), mat("metall")); kn.rotation.x = Math.PI / 2; kn.position.set(b / 2 - 0.09, 0.775, t / 2 + 0.02); g.add(kn);
          const ring = new THREE.Mesh(new THREE.TorusGeometry(0.175, 0.026, 10, 36), mat("metall")); ring.position.set(0, 0.4, t / 2 + 0.016); ring.castShadow = true; g.add(ring);
          const gl = new THREE.Mesh(new THREE.CircleGeometry(0.155, 36), mat(m.typ === "trockner" ? "grau" : "schwarzglas")); gl.position.set(0, 0.4, t / 2 + 0.013); g.add(gl);
          K(0.035, 0.09, 0.022, "grau_hell", 0.2, 0.355, t / 2 + 0.02);
          K(b - 0.04, 0.05, 0.008, "grau_hell", 0, 0.01, t / 2 + 0.002);
          break;
        }
        K(b, 0.85, t, "weiss", 0, 0, 0);
        const tr = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.03, 24), mat(m.typ === "trockner" ? "grau" : "schwarzglas"));
        tr.rotation.x = Math.PI / 2; tr.position.set(0, 0.45, t / 2 + 0.01); g.add(tr);
        K(b - 0.04, 0.08, 0.01, "grau_hell", 0, 0.74, t / 2 + 0.003);
        break;
      }
      default: K(b, 0.6, t, korpus, 0, 0, 0);
    }
    if (m.typ === "laufrad") g.scale.setScalar(0.55);   // Kinderrad: Fahrradmodell verkleinert
    if (m.typ === "fahrrad" || m.typ === "laufrad" || m.typ === "roller") keinPj(g);
    // Waschmaschine/Trockner lassen sich stapeln (z = Oberkante der unteren Maschine)
    g.position.set(m.x, m.typ === "waschmaschine" || m.typ === "trockner" ? (m.z || 0) : 0, m.y);
    g.rotation.y = (m.drehung || 0) * Math.PI / 180;
    g.userData.geraet = m.geraet || null;
    return g;
  }

  // ------------------------------------------------------------------ Ansicht
  function oeffnen(el, opt) {
    opt = opt || {};
    const T = opt.sprache === "en" ? EN : DE, LOC = opt.sprache === "en" ? "en-GB" : "de-DE", SI = opt.sprache === "en" ? 1 : 0;
    el.innerHTML = "";
    el.classList.add("haus3d");
    const stil = document.createElement("style");
    stil.textContent = `
.haus3d.bild{background:radial-gradient(ellipse at 50% 40%,#25272c 0%,#131417 55%,#08090b 100%)}
.haus3d{position:relative;overflow:hidden;background:radial-gradient(ellipse at 50% 38%,#1a2233 0%,#0b0f18 55%,#05070b 100%);color:#e8ecf4;
  font-family:"IBM Plex Sans",system-ui,sans-serif;user-select:none;-webkit-user-select:none;touch-action:none}
.haus3d canvas{position:absolute;inset:0;width:100%!important;height:100%!important;display:block;outline:none}
.haus3d .kopf{position:absolute;left:0;right:0;top:0;display:flex;align-items:center;gap:8px;padding:12px 14px;z-index:5;
  background:linear-gradient(#05070bee,#05070b00);pointer-events:none}
.haus3d .kopf>*{pointer-events:auto}
.haus3d .titel{font-family:"IBM Plex Sans Condensed",sans-serif;letter-spacing:.32em;font-size:13px;color:#a9c4ff;flex:1;white-space:nowrap}
.haus3d .titel small{display:block;letter-spacing:.06em;font-size:11px;color:#9aa6bc;margin-top:3px}
.haus3d .chips{display:flex;gap:6px}
.haus3d .chip{border:1px solid rgba(169,196,255,.28);border-radius:999px;padding:5px 11px;font-size:12px;color:#9aa6bc;
  background:rgba(12,17,29,.7);cursor:pointer;letter-spacing:.06em}
.haus3d .chip.aktiv{color:#06080d;background:#a9c4ff;border-color:#a9c4ff}
.haus3d .zu{width:34px;height:34px;border-radius:50%;border:1px solid rgba(169,196,255,.28);background:rgba(12,17,29,.7);
  color:#e8ecf4;font-size:18px;line-height:30px;text-align:center;cursor:pointer}
.haus3d .lbl{position:absolute;left:0;top:0;transform:translate(-50%,-50%);font:600 10px "IBM Plex Sans Condensed",sans-serif;letter-spacing:.18em;
  text-transform:uppercase;color:rgba(232,236,244,.82);text-shadow:0 1px 4px #000,0 0 10px #000;pointer-events:none;white-space:nowrap;z-index:3;transition:opacity .3s}
.haus3d .lbl.temp{font-size:12px;letter-spacing:.04em;color:#f1d9a6;text-transform:none;margin-top:14px}
.haus3d .karte{position:absolute;left:12px;right:12px;bottom:12px;max-width:420px;margin:0 auto;padding:12px 14px;border-radius:14px;z-index:6;
  background:rgba(12,17,29,.93);border:1px solid rgba(169,196,255,.22);box-shadow:0 10px 30px #000a;transform:translateY(160%);transition:transform .25s}
.haus3d .karte.da{transform:none}
.haus3d .karte b{font-size:15px;font-weight:600}
.haus3d .karte ul{list-style:none;margin:8px 0 0;padding:0;font-size:13px}
.haus3d .karte li{display:flex;justify-content:space-between;gap:12px;padding:3px 0;border-top:1px solid rgba(169,196,255,.08)}
.haus3d .karte li span:last-child{color:#9aa6bc;white-space:nowrap}
.haus3d .karte li.an span:last-child{color:#f1d9a6}
.haus3d .karte .hinweis{font-size:10px;color:#6f7b92;margin-top:8px}
.haus3d .karte{max-height:62%;overflow-y:auto;touch-action:pan-y;-webkit-user-select:none}
.haus3d .karte li[data-g]{cursor:pointer}
.haus3d .karte .gkopf{display:flex;gap:12px;align-items:center}
.haus3d .karte .gkopf div{flex:1;min-width:0}
.haus3d .karte .gkopf small{display:block;color:#9aa6bc;font-size:12px;margin-top:2px}
.haus3d .karte .foto{width:58px;height:58px;flex:none;object-fit:cover;border-radius:10px;border:1px solid rgba(169,196,255,.2);background:#0c111d}
.haus3d .karte .ent{border-top:1px solid rgba(169,196,255,.08);margin-top:9px;padding-top:8px;font-size:13px}
.haus3d .karte .ent .ez{display:flex;justify-content:space-between;gap:10px}
.haus3d .karte .ent .ez span:last-child{color:#9aa6bc;white-space:nowrap}
.haus3d .karte .ent.an .ez span:last-child{color:#f1d9a6}
.haus3d .karte .titelz{color:#9aa6bc;font-size:12px;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.haus3d .karte .kn{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px;align-items:center}
.haus3d .karte button{background:rgba(169,196,255,.1);border:1px solid rgba(169,196,255,.25);color:#e8ecf4;border-radius:10px;
  padding:7px 11px;font:500 12px "IBM Plex Sans",system-ui,sans-serif;cursor:pointer;min-width:42px;min-height:34px}
.haus3d .karte button:active{transform:scale(.96)}
.haus3d .karte button.an{background:#f1d9a6;color:#14100a;border-color:#f1d9a6}
.haus3d .karte button.warn{background:#5a2a20;border-color:#d0805f;color:#ffd9c9}
.haus3d .karte button svg{width:15px;height:15px;vertical-align:-3px;fill:currentColor}
.haus3d .karte label{display:block;color:#9aa6bc;font-size:11px;margin-top:7px}
.haus3d .karte input[type=range]{width:100%;accent-color:#a9c4ff;margin:4px 0 0}
.haus3d .karte select{background:#0c111d;color:#e8ecf4;border:1px solid rgba(169,196,255,.25);border-radius:8px;padding:6px 8px;font-size:12px;max-width:100%}
.haus3d .karte .wert{font-size:19px;font-weight:600;min-width:70px;text-align:center}
.haus3d .karte .meld{font-size:11px;color:#9aa6bc;min-height:14px;margin-top:8px}
.haus3d .karte .meld.nein{color:#ffb4a0}
.haus3d .leiste{position:absolute;left:0;right:0;bottom:10px;display:flex;gap:8px;overflow-x:auto;padding:2px 12px;z-index:5;
  scrollbar-width:none;touch-action:pan-x;transition:opacity .25s}
.haus3d .leiste::-webkit-scrollbar{display:none}
.haus3d .karte.da~.leiste{opacity:0;pointer-events:none}
.haus3d .kachel{flex:none;display:flex;align-items:center;gap:8px;min-width:118px;max-width:160px;padding:8px 10px;border-radius:14px;
  background:rgba(12,17,29,.88);border:1px solid rgba(169,196,255,.18);color:#e8ecf4;font:500 12px "IBM Plex Sans",system-ui,sans-serif;
  cursor:pointer;text-align:left;box-shadow:0 6px 18px #0008;-webkit-tap-highlight-color:transparent}
.haus3d .kachel:active{transform:scale(.97)}
.haus3d .kachel b{display:block;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:110px}
.haus3d .kachel small{display:block;color:#9aa6bc;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:110px}
.haus3d .kachel .sym{width:28px;height:28px;flex:none;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(169,196,255,.12)}
.haus3d .kachel .sym svg{width:16px;height:16px;fill:#cfd8ea}
.haus3d .kachel.an{background:linear-gradient(135deg,rgba(214,112,38,.95),rgba(150,66,22,.95));border-color:#f3a25a}
.haus3d .kachel.an small{color:#ffe1c2}.haus3d .kachel.an .sym{background:rgba(255,255,255,.18)}.haus3d .kachel.an .sym svg{fill:#fff}
.haus3d .kachel.warn{background:#5a2a20;border-color:#d0805f}
.haus3d .kachel.szene{min-width:0;flex-direction:column;gap:4px;padding:8px 13px;text-align:center}
.haus3d .kachel.szene .sym{background:rgba(169,196,255,.16)}
.haus3d .kachel.laeuft{border-color:#a9c4ff;box-shadow:0 0 0 2px #a9c4ff55}
.haus3d .leistenhinweis{position:absolute;left:50%;bottom:76px;transform:translateX(-50%);padding:6px 12px;border-radius:999px;
  background:rgba(12,17,29,.92);border:1px solid rgba(169,196,255,.22);color:#e8ecf4;font-size:12px;z-index:6;opacity:0;transition:opacity .3s;
  pointer-events:none;max-width:86%;text-align:center}
.haus3d .leistenhinweis.da{opacity:1}
.haus3d .chip.mond{font-size:13px;padding:4px 10px}
.haus3d .fuss{position:absolute;left:14px;bottom:10px;font-size:11px;color:#6f7b92;letter-spacing:.06em;pointer-events:none;z-index:2}
.haus3d .meldung{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#9aa6bc;font-size:14px;pointer-events:none;text-align:center;padding:24px;z-index:4}
.haus3d .karte.da~.fuss{opacity:0}
@media (max-width:540px){.haus3d .kopf{flex-wrap:wrap;row-gap:8px}.haus3d .titel{flex:1 1 calc(100% - 50px)}
  .haus3d .chips{order:3;flex-basis:100%}.haus3d .chip{padding:5px 10px;font-size:11px}}`;
    el.appendChild(stil);
    const kopf = document.createElement("div"); kopf.className = "kopf";
    kopf.innerHTML = `<div class="titel">${T.titel}<small></small></div><div class="chips"></div>` +
      (opt.schliessen ? `<div class="zu" role="button" aria-label="${T.schliessen}">×</div>` : "");
    el.appendChild(kopf);
    if (opt.schliessen) kopf.querySelector(".zu").addEventListener("click", () => opt.schliessen());
    const ebeneLbl = document.createElement("div"); el.appendChild(ebeneLbl);
    const karte = document.createElement("div"); karte.className = "karte"; el.appendChild(karte);
    const fuss = document.createElement("div"); fuss.className = "fuss"; fuss.textContent = opt.steuern ? T.bedienen : T.nur; el.appendChild(fuss);
    // Bedienleiste wie im Reel (seit 01.11.2026 abends): nur, wenn der Gastgeber schalten kann; ersetzt dann die Fusszeile
    const leiste = document.createElement("div"); leiste.className = "leiste"; leiste.hidden = !opt.steuern; el.appendChild(leiste);
    const leistenHinweis = document.createElement("div"); leistenHinweis.className = "leistenhinweis"; el.appendChild(leistenHinweis);
    if (opt.steuern) fuss.hidden = true;
    const meldung = document.createElement("div"); meldung.className = "meldung"; meldung.textContent = T.laedt; el.appendChild(meldung);

    let r;
    try {
      r = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch (e) { r = null; }
    if (!r || !r.getContext()) {
      meldung.textContent = T.kein_gl;
      return { daten() {}, waehlen() {}, info: () => ({ webgl: false }), zu() { el.innerHTML = ""; el.classList.remove("haus3d"); } };
    }
    const handy = Math.min(screen.width, screen.height) < 600;
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, handy ? 1.75 : 1.5));
    r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.outputColorSpace = THREE.SRGBColorSpace; r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 1.05;
    el.insertBefore(r.domElement, kopf);
    const szene = new THREE.Scene();
    szene.fog = new THREE.Fog(0x0b0f18, 30, 70);
    const kam = new THREE.PerspectiveCamera(36, 1, 0.1, 200);

    // Umgebungslicht fuer die Materialien (Spiegelungen, weiches Licht von allen Seiten): ein heller Raum mit Leuchtflaechen,
    // einmal zu einer Umgebungskarte vorgerechnet (Prinzip RoomEnvironment aus three.js, ohne Zusatzdatei)
    try {
      const pm = new THREE.PMREMGenerator(r), es = new THREE.Scene();
      const raumU = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial({ side: THREE.BackSide, color: 0x8f8a84, roughness: 1 }));
      raumU.scale.set(28, 12, 28); raumU.position.y = 5.5; es.add(raumU); es.add(new THREE.AmbientLight(0xffffff, 0.6));
      const flaeche = (x, y, z, w, h, d, st) => { const q = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), new THREE.MeshBasicMaterial({ color: new THREE.Color(st, st * 0.97, st * 0.92) })); q.position.set(x, y, z); es.add(q); };
      flaeche(0, 11.3, 0, 9, 0.1, 9, 4); flaeche(-13.8, 6, 0, 0.1, 5, 9, 2.2); flaeche(13.8, 6, -3, 0.1, 4, 6, 1.4); flaeche(0, 5, 13.8, 9, 4, 0.1, 1.1);
      szene.environment = pm.fromScene(es, 0.04).texture; pm.dispose();
    } catch (e) { /* ohne Umgebungskarte geht es auch, nur flacher */ }
    // Grundlicht: Himmel und Sonne; Staerke, Farbe und Richtung setzt lichtSetzen() nach dem echten Sonnenstand
    const himmel = new THREE.HemisphereLight(0x8fa6d6, 0x2a2017, 0.35); szene.add(himmel);
    const sonne = new THREE.DirectionalLight(0xffe2bd, 1.35);
    sonne.position.set(-6, 14, 9); sonne.castShadow = true;
    sonne.shadow.mapSize.set(handy ? 1024 : 2048, handy ? 1024 : 2048);
    Object.assign(sonne.shadow.camera, { left: -8, right: 8, top: 8, bottom: -8, near: 1, far: 40 });
    sonne.shadow.bias = -0.0004; sonne.shadow.normalBias = 0.02; sonne.shadow.radius = 4;
    szene.add(sonne); szene.add(sonne.target);

    const MATS = {};
    function mat(name, extra) {
      if (name && name.isMaterial) return name;
      const key = name + (extra ? JSON.stringify(extra) : "");
      if (MATS[key]) return MATS[key];
      let m;
      if (name === "glas") m = new THREE.MeshStandardMaterial({ color: 0xcfe0f2, transparent: true, opacity: 0.16, roughness: 0.02, metalness: 0, depthWrite: false, envMapIntensity: 1.4 });
      else if (name === "kuehlglas") m = new THREE.MeshStandardMaterial({ color: 0xcfe6ff, emissive: 0x9cc6ff, emissiveIntensity: 0.6, roughness: 0.2 });
      else if (name === "schwarzglas") m = new THREE.MeshStandardMaterial({ color: 0x0c0d0f, roughness: 0.06, metalness: 0.1, envMapIntensity: 1.3 });
      else if (name === "spiegel") m = new THREE.MeshStandardMaterial({ color: 0xc9d1d9, roughness: 0.03, metalness: 1, envMapIntensity: 1.2 });
      else if (name === "wasser") m = new THREE.MeshStandardMaterial({ color: 0xdfeaf2, roughness: 0.08, envMapIntensity: 1.2 });
      else if (name === "bild") m = new THREE.MeshStandardMaterial({ color: 0x0a0c10, roughness: 0.12, emissive: 0x000000, envMapIntensity: 1.2 });
      else if (name === "eiche" || name === "eiche_hell" || name === "holz")         // Holz mit Maserung
        m = new THREE.MeshStandardMaterial({ map: holzTex(FARBE[name]), roughness: 0.55, envMapIntensity: 0.7 });
      else if (/^stoff/.test(name) || ["rot", "rosa", "blau", "gruen", "beige"].includes(name))   // Polster, Bettzeug
        m = new THREE.MeshStandardMaterial({ map: stoffTex(FARBE[name] != null ? FARBE[name] : FARBE.stoff), roughness: 0.96, envMapIntensity: 0.35 });
      else if (name === "metall") m = new THREE.MeshStandardMaterial({ color: 0xb9bdc3, roughness: 0.3, metalness: 0.9, envMapIntensity: 1 });
      else if (name === "kupfer") m = new THREE.MeshStandardMaterial({ color: FARBE.kupfer, roughness: 0.32, metalness: 0.85, envMapIntensity: 1 });
      else if (name === "karton") m = new THREE.MeshStandardMaterial({ color: FARBE.karton, roughness: 0.92, envMapIntensity: 0.3 });
      else {                                                  // Lack und Kunststoff: glatt, leichte Spiegelung
        const glatt = { weiss: 0.38, schwarz: 0.42, anthrazit: 0.48, grau: 0.5, grau_hell: 0.45, tafel: 0.85, wand: 0.92 }[name];
        m = new THREE.MeshStandardMaterial({ color: FARBE[name] != null ? FARBE[name] : 0x888888, roughness: glatt != null ? glatt : 0.6, envMapIntensity: 0.75 });
      }
      m.name = "m:" + name;          // Name fuer den Blender-Export (Materialien dort gezielt ersetzen)
      MATS[key] = m;
      return m;
    }
    const PUTZ = TEX.putz(); PUTZ.repeat.set(0.5, 0.5);
    const WAND = new THREE.MeshStandardMaterial({ name: "wand", map: PUTZ, roughness: 0.93, envMapIntensity: 0.45 });
    // seit 03.11.2026: weiss verputzte Raeume ("wand": "hell" im Plan, z. B. ein Bad)
    const WAND_HELL = new THREE.MeshStandardMaterial({ name: "wand_hell", map: PUTZ, color: 0xf1efea, roughness: 0.93, envMapIntensity: 0.45 });
    const WAND_GRAU = new THREE.MeshStandardMaterial({ name: "wand_grau", map: PUTZ, color: 0xaaaeb5, roughness: 0.92, envMapIntensity: 0.45 });
    const KANTE = new THREE.MeshStandardMaterial({ name: "kante", color: 0xf4f0ea, roughness: 0.85, envMapIntensity: 0.45 });   // Schnittkante der Wand
    const TUERBLATT = new THREE.MeshStandardMaterial({ color: 0x2c2f34, roughness: 0.6 });
    // seit 04.11.2026: Tore ueber 1,8 m (Garage) im Stil "bild" weiss mit waagrechten Paneelen wie in der Bildansicht
    const TORTEX = leinwand(64, 256, (x, w, h) => {
      x.fillStyle = "#eceae6"; x.fillRect(0, 0, w, h);
      for (const y of [0, 128]) { x.fillStyle = "rgba(90,92,96,.55)"; x.fillRect(0, y, w, 3); x.fillStyle = "rgba(255,255,255,.7)"; x.fillRect(0, y + 3, w, 2); }
    });
    TORTEX.repeat.set(1, 1);
    const GARAGENTOR = new THREE.MeshStandardMaterial({ name: "garagentor", map: TORTEX, roughness: 0.5, envMapIntensity: 0.6 });
    // Fensterglas als eigenes Material: Tageshelligkeit und Nachtglimmen nur fuer Fenster, nicht fuer Vitrinen, Duschwand,
    // Gelaender und Kuehlschranktuer (Pruefung 03.11.2026, Befund 12)
    const GLAS = mat("glas").clone(); GLAS.name = "fensterglas";
    // Stil "bild": Optik einer gezeichneten Hausansicht - anthrazitfarbene Waende, dunkle Schnittkante,
    // warme LED-Linie oben an jeder Wand mit weichem Schein nach unten, tagsueber hell leuchtende Fenster.
    // opt.stil = "hell" gibt das helle Haus von vorher zurueck.
    const BILD = opt.stil !== "hell";
    mat.bild = BILD;                  // moebelBauen liest den Stil hierueber
    if (BILD) {
      el.classList.add("bild"); szene.fog.color.setHex(0x0e0f12);
      WAND.color.setHex(0x4f545b); KANTE.color.setHex(0x1c1d20); KANTE.roughness = 0.7;
      mat("wand").color.setHex(0x4f5156);
    }
    const LED = new THREE.MeshBasicMaterial({ name: "led", color: new THREE.Color(1.0, 0.87, 0.68), toneMapped: false });
    const LEDSCHEIN = new THREE.MeshBasicMaterial({ name: "ledschein", map: TEX.ledschein(), color: 0xffc58f, transparent: true, opacity: 0.3,
      depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false, side: THREE.DoubleSide });
    const LEDGEO = new THREE.BoxGeometry(1, 0.018, 0.012), SCHEINGEO = new THREE.PlaneGeometry(1, 0.34);
    const BODEN = {};
    function bodenMat(art) {
      if (BODEN[art]) return BODEN[art];
      const f = TEX[art] || TEX.beton, t = f(), k = BODEN_KACHEL[art] || 2;
      t.repeat.set(1 / k, art === "holz" ? 1 / (k * 2) : 1 / k);
      return (BODEN[art] = new THREE.MeshStandardMaterial({ name: "boden:" + art, map: t, roughness: art === "fliese_dunkel" ? 0.32 : art === "holz" ? 0.5 : 0.42,
        metalness: 0, envMapIntensity: art === "fliese_dunkel" ? 0.9 : art === "beton" ? 0.7 : 0.6 }));
    }
    const GLUT = TEX.glut(), RING = TEX.ring();
    // Lichtinsel am Boden (Nacht): weicher warmer Kreis; Spur des Saugroboters: kleine Scheiben
    const POOL = leinwand(128, 128, (x, w, h) => {
      const gr = x.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
      gr.addColorStop(0, "rgba(255,214,160,1)"); gr.addColorStop(0.35, "rgba(255,190,120,.55)"); gr.addColorStop(1, "rgba(255,170,90,0)");
      x.fillStyle = gr; x.fillRect(0, 0, w, h);
    });
    POOL.wrapS = POOL.wrapT = THREE.ClampToEdgeWrapping;
    const POOLGEO = new THREE.PlaneGeometry(1, 1), SPURGEO = new THREE.CircleGeometry(0.06, 12).rotateX(-Math.PI / 2);
    const INHALT = {}, LIVEBILD = {};     // LIVEBILD: Titelbilder (eigener Speicher, FOTO steht weiter unten)
    function farbtonVon(t) { let h = 0; for (const c of String(t)) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }
    function inhaltTex(zeile1, zeile2, art, bild, logo) {  // Bild auf Leinwand/Fernseher/Monitor, je Text einmal gezeichnet
      const k = art + "|" + zeile1 + "|" + zeile2 + "|" + (bild || "");
      if (INHALT[k]) return INHALT[k];
      const t = leinwand(512, 288, (x, w, h) => {
        if (art === "pc") {
          x.fillStyle = "#0d1422"; x.fillRect(0, 0, w, h);
          x.fillStyle = "#16233a"; x.fillRect(0, 0, w, 22);
          const r = zufall(7);
          for (let i = 0; i < 16; i++) {
            const y = 34 + i * 15, ein = 14 + (r() * 4 | 0) * 14;
            for (let s = 0, xx = ein; s < 3 && xx < w - 40; s++) {
              const l = 30 + r() * 120;
              x.fillStyle = ["#6fa8ff", "#f1d9a6", "#9ce0b0", "#c7a5ff", "#8b97ad"][r() * 5 | 0];
              x.globalAlpha = 0.85; x.fillRect(xx, y, l, 7); xx += l + 10;
            }
          }
          x.globalAlpha = 1;
          return;
        }
        const hue = farbtonVon(zeile1 + zeile2);
        const gr = x.createLinearGradient(0, 0, w, h);
        gr.addColorStop(0, `hsl(${hue},55%,30%)`); gr.addColorStop(1, `hsl(${(hue + 40) % 360},60%,12%)`);
        x.fillStyle = gr; x.fillRect(0, 0, w, h);
        const vg = x.createRadialGradient(w * 0.7, h * 0.3, 10, w * 0.6, h * 0.5, w * 0.8);
        vg.addColorStop(0, "rgba(255,255,255,.18)"); vg.addColorStop(1, "rgba(0,0,0,.35)");
        x.fillStyle = vg; x.fillRect(0, 0, w, h);
        x.fillStyle = "rgba(255,255,255,.92)";
        x.beginPath(); x.moveTo(36, h - 92); x.lineTo(36, h - 52); x.lineTo(70, h - 72); x.closePath(); x.fill();
        x.font = "700 46px 'IBM Plex Sans', system-ui, sans-serif"; x.textBaseline = "alphabetic";
        const kurz = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
        x.fillText(kurz(zeile1 || "", 18), 86, h - 54);
        if (zeile2) { x.font = "400 26px 'IBM Plex Sans', system-ui, sans-serif"; x.fillStyle = "rgba(255,255,255,.78)"; x.fillText(kurz(zeile2, 32), 36, h - 16); }
      });
      t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
      const n = Object.keys(INHALT); if (n.length > 24) { INHALT[n[0]].dispose(); delete INHALT[n[0]]; }
      INHALT[k] = t;
      // Standbild auf Beamer und Fernseher, wenn sie laufen: Titelbild des Players von der
      // Bruecke (Name ohne Adresse, kommt wie die Geraetefotos ueber opt.bild). Bis es da ist, bleibt die Textfassung.
      if (bild && opt.bild) {
        if (!LIVEBILD[bild]) LIVEBILD[bild] = Promise.resolve(opt.bild(bild)).catch(() => null);
        LIVEBILD[bild].then((u) => {
          if (!u || INHALT[k] !== t) return;
          const im = new Image();
          im.onload = () => {
            if (INHALT[k] !== t || !im.width) return;
            const c = t.image, x = c.getContext("2d"), w = c.width, h = c.height;
            if (logo) {                    // seit 03.11.2026: App-Logo (Box meldet kein Bild): klein und mittig, Name darunter
              x.fillStyle = "#0b0d11"; x.fillRect(0, 0, w, h);
              x.save(); x.filter = "blur(36px) saturate(1.5) brightness(0.55)"; x.globalAlpha = 0.9;
              x.drawImage(im, w * 0.15, -h * 0.4, w * 0.7, w * 0.7); x.restore();
              const g = Math.round(h * 0.5), lx = (w - g) / 2, ly = h * 0.13;
              x.save(); x.beginPath();
              if (x.roundRect) x.roundRect(lx, ly, g, g, g * 0.18); else x.rect(lx, ly, g, g);
              x.clip(); x.drawImage(im, lx, ly, g, g); x.restore();
              const zl = zeile2 || zeile1 || "";
              if (zl) {
                x.fillStyle = "rgba(255,255,255,.95)"; x.font = "600 28px 'IBM Plex Sans', system-ui, sans-serif";
                x.textAlign = "center"; x.textBaseline = "alphabetic";
                x.fillText(zl.length > 30 ? zl.slice(0, 29) + "…" : zl, w / 2, h - 30); x.textAlign = "start";
              }
              t.needsUpdate = true;
              weck();
              return;
            }
            const voll = Math.max(w / im.width, h / im.height), ganz = Math.min(w / im.width, h / im.height);
            x.save(); x.filter = "blur(14px) brightness(0.5)";               // Hintergrund: dasselbe Bild, weich und dunkel
            x.drawImage(im, (w - im.width * voll) / 2, (h - im.height * voll) / 2, im.width * voll, im.height * voll);
            x.restore();
            x.drawImage(im, (w - im.width * ganz) / 2, (h - im.height * ganz) / 2, im.width * ganz, im.height * ganz);
            const zeile = zeile2 || zeile1 || "";
            if (zeile) {
              const v = x.createLinearGradient(0, h * 0.62, 0, h);
              v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, "rgba(0,0,0,.8)");
              x.fillStyle = v; x.fillRect(0, h * 0.62, w, h * 0.38);
              x.fillStyle = "rgba(255,255,255,.95)"; x.font = "600 28px 'IBM Plex Sans', system-ui, sans-serif";
              x.textBaseline = "alphabetic"; x.fillText(zeile.length > 34 ? zeile.slice(0, 33) + "…" : zeile, 22, h - 20);
            }
            t.needsUpdate = true;
            weck();
          };
          im.src = u;
        });
      }
      return t;
    }
    // Kontaktschatten auf dem Boden, je Raum einmal vorgerechnet: dunkle, weiche Saeume an den Waenden und unter den
    // Moebeln (Ersatz fuer Umgebungsverdeckung, ohne Nachbearbeitung). Die Bodenform hat UVs in Metern (x, -y).
    function bodenMitAO(ra, E) {
      const basis = bodenMat(ra.boden || "beton");
      try {
        const xs = ra.poly.map((p) => p[0]), ys = ra.poly.map((p) => p[1]);
        const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), W = x1 - x0, H = y1 - y0;
        if (W <= 0 || H <= 0) return basis;
        const ppm = Math.min(48, 900 / Math.max(W, H)), cw = Math.max(16, Math.ceil(W * ppm)), ch = Math.max(16, Math.ceil(H * ppm));
        const c = document.createElement("canvas"); c.width = cw; c.height = ch;
        const x = c.getContext("2d"), weg = 4000; x.fillStyle = "#fff"; x.fillRect(0, 0, cw, ch);
        const P = (px, py) => [(px - x0) * ppm - weg, (py - y0) * ppm];
        x.shadowOffsetX = weg; x.shadowColor = "rgba(0,0,0,0.7)"; x.shadowBlur = 0.25 * ppm;
        x.strokeStyle = "#000"; x.lineWidth = 0.12 * ppm; x.beginPath();
        ra.poly.forEach((p, i) => { const q = P(p[0], p[1]); if (i) x.lineTo(q[0], q[1]); else x.moveTo(q[0], q[1]); });
        x.closePath(); x.stroke();
        x.shadowColor = "rgba(0,0,0,0.55)"; x.shadowBlur = 0.14 * ppm; x.fillStyle = "#000";
        for (const m of E.moebel || []) {
          if ((m.z || 0) > 0.3 || m.typ === "teppich" || !imPoly(ra.poly, m.x, m.y)) continue;
          const q = P(m.x, m.y); x.save(); x.translate(q[0], q[1]); x.rotate(-(m.drehung || 0) * Math.PI / 180);
          x.fillRect(-m.b * ppm * 0.48, -m.t * ppm * 0.48, m.b * ppm * 0.96, m.t * ppm * 0.96); x.restore();
        }
        const t = new THREE.CanvasTexture(c);
        t.repeat.set(1 / W, 1 / H); t.offset.set(-x0 / W, y1 / H);
        const m = basis.clone(); m.aoMap = t; m.aoMapIntensity = 1;
        return m;
      } catch (e) { return basis; }
    }

    let D = null, H3 = null, etage = null, aus = false, uhr = null, gewaehlt = null, aufgebaut = "", wandTief = false;
    const welt = {};            // etage -> {gruppe, seiten: {nord,sued,ost,west,innen}, geraete: [...], raeume: [...], lichter, boden}
    const K = { az: 0.55, pol: 0.9, dist: 16, ziel: new THREE.Vector3(0, 0.6, 0), soll: null };

    // ---------------------------------------------------------------- Aufbau einer Etage
    function etageBauen(eid) {
      const E = H3.etagen[eid], U = H3.umriss, UE = etagenUmriss(E, U), g = new THREE.Group(), y0 = E.boden || 0;
      g.position.y = y0;
      const seiten = { nord: new THREE.Group(), sued: new THREE.Group(), ost: new THREE.Group(), west: new THREE.Group(), innen: new THREE.Group() };
      for (const s of Object.values(seiten)) g.add(s);
      // Sockel: das Haus steht auf einer dunklen Platte, das liest sich als Modell
      const sockel = new THREE.Mesh(new THREE.BoxGeometry(UE[2] - UE[0] + 0.5, 0.22, UE[3] - UE[1] + 0.5),
        new THREE.MeshStandardMaterial({ color: BILD ? 0x1b1c1f : 0x161b26, roughness: 0.9 }));
      sockel.position.set((UE[0] + UE[2]) / 2, -0.115, (UE[1] + UE[3]) / 2); sockel.receiveShadow = true; g.add(sockel);
      // Boeden je Raum (Loecher fuer das Treppenauge)
      const raeume = [];
      const glows = [];
      for (const ra of E.raeume || []) {
        // Form mit (x, -y), dann um -90 Grad kippen: Plan-y wird zu z (Sueden = zur Kamera), die Flaeche zeigt nach oben
        const geo = new THREE.ShapeGeometry(new THREE.Shape(ra.poly.map((p) => new THREE.Vector2(p[0], -p[1]))));
        geo.rotateX(-Math.PI / 2);
        const me = new THREE.Mesh(geo, bodenMitAO(ra, E));
        me.position.y = (ra.stufe || 0) + 0.001; me.receiveShadow = true; me.userData.raum = ra.id; g.add(me);
        const m = mitte(ra.poly);
        // Raumlicht: warmes Deckenlicht, Staerke nach Flaeche
        let fl = 0; for (let i = 0, j = ra.poly.length - 1; i < ra.poly.length; j = i++) fl += (ra.poly[j][0] + ra.poly[i][0]) * (ra.poly[j][1] - ra.poly[i][1]);
        fl = Math.abs(fl / 2);
        const li = new THREE.PointLight(BILD ? 0xffdcb8 : 0xffc68a, Math.min(14, 2.5 + fl * 0.55), Math.sqrt(fl) * 2.2 + 1.5, 1.6);
        li.position.set(m[0], hoeheBei(E, U, m[0], m[1]) - 0.35, m[1]); li.userData.basis = li.intensity; li.userData.raumlicht = true; g.add(li);
        // Nachts wie im Reel: Schein um die Deckenleuchte und eine warme Lichtinsel am Boden (Stimmung, kein echter Lampenzustand)
        const schein = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLUT, color: 0xffb46a, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
        schein.position.copy(li.position); schein.scale.setScalar(0.9 + Math.sqrt(fl) * 0.24); g.add(schein);
        const insel = new THREE.Mesh(POOLGEO, new THREE.MeshBasicMaterial({ map: POOL, color: 0xffa860, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
        insel.rotation.x = -Math.PI / 2; insel.position.set(m[0], (ra.stufe || 0) + 0.012, m[1]); insel.scale.setScalar(0.9 + Math.sqrt(fl) * 0.55); insel.renderOrder = 2; g.add(insel);
        glows.push({ schein, insel, staerke: 0.8 + ((ra.id.length * 7) % 5) / 12 });
        raeume.push({ id: ra.id, name: ra.name, poly: ra.poly, mitte: m, boden: me, ohne_name: ra.ohne_name, stufe: ra.stufe || 0 });
      }
      // Waende
      const stuecke = waendeBerechnen(E, U), wandzahl = stuecke.length;
      const helleRaeume = (E.raeume || []).filter((ra) => ra.wand === "hell" && Array.isArray(ra.poly));
      // seit 04.11.2026: Raeume mit Estrichboden (Keller, Garage) haben im Stil "bild" hellgraue Waende wie die Bildansicht
      const grauRaeume = BILD ? (E.raeume || []).filter((ra) => ra.boden === "beton" && ra.wand !== "hell" && Array.isArray(ra.poly)) : [];
      const leds = { nord: [], sued: [], ost: [], west: [], innen: [] }, scheine = [];
      const ledTeile = { nord: [], sued: [], ost: [], west: [], innen: [] }, scheinTeile = { nord: [], sued: [], ost: [], west: [], innen: [] };
      let ledZahl = 0;
      for (const s of stuecke) {
        const art = s.art, tief = s.dicke;
        // Profil in der Wandebene: u entlang der Wand, v = Hoehe; oben folgt im DG der Dachschraege
        const unten = s.unten || 0, uPunkte = [s.a];
        if (E.traufen && s.oben == null) {
          for (let u = Math.ceil(s.a * 4) / 4; u < s.b; u += 0.25) if (u > s.a) uPunkte.push(u);
          for (const z of gaubenZonen(E, U)) for (const v of s.lage === "h" ? [z[0], z[2]] : [z[1], z[3]])
            for (const w of [v - 0.001, v + 0.001]) if (w > s.a && w < s.b) uPunkte.push(w);
          uPunkte.sort((p, q) => p - q);
        }
        uPunkte.push(s.b);
        const hoch = (u) => { const hb = s.lage === "h" ? hoeheBei(E, U, u, s.k) : hoeheBei(E, U, s.k, u); return s.oben != null ? Math.min(s.oben, hb) : hb; };
        // Anbauteile in Wandkoordinaten (x entlang der Wand, y Hoehe, z quer): Gruppe liegt wie das Wandstueck
        const anbau = () => { const q = new THREE.Group(); if (s.lage === "h") q.position.set(0, 0, s.k); else { q.rotation.y = -Math.PI / 2; q.position.set(s.k, 0, 0); } (s.aussen ? seiten[s.aussen] : seiten.innen).add(q); return q; };
        const leiste = (q, w, h, d, x, y, z, farbe) => { const e = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(farbe || "weiss")); e.position.set(x, y, z); e.castShadow = e.receiveShadow = true; q.add(e); return e; };
        // Innenseite einer Aussenwand in Wandkoordinaten (+z oder -z); Innenwaende haben zwei Innenseiten
        const innen = s.aussen ? ({ nord: 1, sued: -1, west: -1, ost: 1 }[s.aussen]) : 0;
        if (art === "tuer") {         // offene Tuer: Blatt um 80 Grad in den Raum gedreht, Zarge als Rahmen, Drueckergarnitur
          const w = s.b - s.a, blatt = new THREE.Mesh(new THREE.BoxGeometry(w - 0.06, 2.0, 0.04), mat("weiss"));
          blatt.geometry.translate((w - 0.06) / 2, 1.0, 0); blatt.castShadow = true;
          const piv = new THREE.Group(); piv.add(blatt);
          for (const sz of [-1, 1]) { const dr = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.018, 0.018), mat("metall")); dr.position.set(w - 0.06 - 0.1, 1.05, sz * 0.045); piv.add(dr); }
          const za = anbau(), zt = tief + 0.03;
          leiste(za, 0.05, 2.03, zt, s.a + 0.025, 1.015, 0); leiste(za, 0.05, 2.03, zt, s.b - 0.025, 1.015, 0); leiste(za, w, 0.05, zt, (s.a + s.b) / 2, 2.025, 0);
          // Anschlag immer am Anfang der Oeffnung; "gegenseite" schwenkt das Blatt auf die
          // andere Wandseite
          const sw = s.gegen ? -1 : 1;
          if (s.lage === "h") { piv.position.set(s.a + 0.03, 0, s.k); piv.rotation.y = -1.35 * sw; }
          else { piv.position.set(s.k, 0, s.a + 0.03); piv.rotation.y = -Math.PI / 2 + 1.35 * sw; }
          (s.aussen ? seiten[s.aussen] : seiten.innen).add(piv);
          continue;
        }
        if (hoch(s.a) <= unten + 0.01 && hoch(s.b) <= unten + 0.01) continue;
        const pts = [new THREE.Vector2(s.a, unten), new THREE.Vector2(s.b, unten)];
        for (let i = uPunkte.length - 1; i >= 0; i--) pts.push(new THREE.Vector2(uPunkte[i], Math.max(unten + 0.01, hoch(uPunkte[i]))));
        const geo = new THREE.ExtrudeGeometry(new THREE.Shape(pts), { depth: tief, bevelEnabled: false, steps: 1 });
        geo.translate(0, 0, -tief / 2);
        const mm = art === "glas" ? GLAS : art === "tuerblatt" ? (s.tor && BILD ? GARAGENTOR : TUERBLATT) : [WAND, KANTE];
        const me = new THREE.Mesh(geo, mm);
        if (s.lage === "h") { me.position.set(0, 0, s.k); }
        else { me.rotation.y = -Math.PI / 2; me.position.set(s.k, 0, 0); }
        me.castShadow = art !== "glas"; me.receiveShadow = true;
        (s.aussen ? seiten[s.aussen] : seiten.innen).add(me);
        // Auf der Seite eines hellen Raums eine weisse Putzflaeche mit dem Umriss des
        // Wandstuecks; die Wand selbst bleibt fuer den Nachbarraum wie sie ist und senkt sich mit ihr ab.
        if (art === "wand") for (const [liste, wm] of [[helleRaeume, WAND_HELL], [grauRaeume, WAND_GRAU]]) if (liste.length) for (const sz of [1, -1]) {
          // Abschnittsweise: Aussenwaende laufen als ein Stueck an mehreren Raeumen entlang (5-cm-Raster entlang der Wand)
          const d = tief / 2 + 0.05, laeufe = [];
          const drin = (u) => { const px = s.lage === "h" ? u : s.k - sz * d, py = s.lage === "h" ? s.k + sz * d : u; return liste.some((ra) => imPoly(px, py, ra.poly)); };
          let start = null;
          for (let u = s.a; u < s.b + 0.05; u += 0.05) {
            const uu = Math.min(u, s.b), ja = drin(Math.min(Math.max(uu, s.a + 0.01), s.b - 0.01));
            if (ja && start === null) start = uu;
            if (!ja && start !== null) { laeufe.push([start, uu]); start = null; }
          }
          if (start !== null) laeufe.push([start, s.b]);
          for (const [u0, u1] of laeufe) {
            if (u1 - u0 < 0.05) continue;
            const pp = [new THREE.Vector2(u0, unten), new THREE.Vector2(u1, unten)];
            for (const u of [u1, ...uPunkte.filter((v) => v > u0 && v < u1).sort((p, q) => q - p), u0]) pp.push(new THREE.Vector2(u, Math.max(unten + 0.01, hoch(u))));
            const fg = new THREE.ShapeGeometry(new THREE.Shape(sz > 0 ? pp : pp.map((p) => new THREE.Vector2(-p.x, p.y))));
            if (sz < 0) { fg.scale(-1, 1, 1); const nr = fg.attributes.normal.array; for (let i = 2; i < nr.length; i += 3) nr[i] = -1; }
            fg.translate(0, 0, sz * (tief / 2 + 0.002));
            const pm = new THREE.Mesh(fg, wm); pm.receiveShadow = true;
            if (s.lage === "h") pm.position.set(0, 0, s.k); else { pm.rotation.y = -Math.PI / 2; pm.position.set(s.k, 0, 0); }
            (s.aussen ? seiten[s.aussen] : seiten.innen).add(pm);
          }
        }
        const w = s.b - s.a, mitteU = (s.a + s.b) / 2;
        if (art === "glas" && s.oben != null) {           // Fensterrahmen (weiss), Pfosten bei breiten Fenstern, innen Fensterbank
          const q = anbau(), ob = Math.min(s.oben, hoch(mitteU)), un = unten, rt = tief * 0.6;
          if (ob - un > 0.15) {
            leiste(q, 0.06, ob - un, rt, s.a + 0.03, (un + ob) / 2, 0); leiste(q, 0.06, ob - un, rt, s.b - 0.03, (un + ob) / 2, 0);
            leiste(q, w, 0.06, rt, mitteU, ob - 0.03, 0); leiste(q, w, 0.06, rt, mitteU, un + 0.03, 0);
            if (w > 1.05) leiste(q, 0.05, ob - un, rt * 0.8, mitteU, (un + ob) / 2, 0);
            if (innen && un > 0.15) leiste(q, w + 0.08, 0.03, 0.22, mitteU, un - 0.015, innen * (tief / 2 + 0.1), "weiss");
          }
        }
        if (art === "wand" && !unten && hoch(mitteU) > 0.3 && w > 0.08) {     // Sockelleisten auf den Innenseiten
          const q = anbau();
          for (const sz of innen ? [innen] : [-1, 1]) leiste(q, w, 0.07, 0.012, mitteU, 0.035, sz * (tief / 2 + 0.006), "weiss");
        }
        // Stil "bild": LED-Linie an der Oberkante jeder vollen Wand (nicht unter Fenstern), je Innenseite; im DG folgt sie
        // der Dachschraege Abschnitt fuer Abschnitt. An einer abgesenkten Wand wird sie ausgeblendet (waendeAnpassen).
        if (BILD && art === "wand" && s.oben == null && w > 0.05) {
          // Abschnitte gleicher Neigung zusammenfassen (im DG liegt alle 25 cm ein Stuetzpunkt), dann je Wandseite sammeln;
          // nach dem Wandbau wird alles zu einer Geometrie je Seite verschmolzen (sonst Hunderte Zeichenaufrufe im DG)
          const q = new THREE.Object3D(), seite = s.aussen || "innen";      // Lage wie anbau(), aber ohne leere Gruppe
          if (s.lage === "h") q.position.set(0, 0, s.k); else { q.rotation.y = -Math.PI / 2; q.position.set(s.k, 0, 0); }
          q.updateMatrix();
          const abschnitte = [];
          for (let i = 0; i + 1 < uPunkte.length; i++) {
            const ua = uPunkte[i], ub = uPunkte[i + 1];
            if (ub - ua < 0.01) continue;
            const ha = hoch(ua), hb = hoch(ub), wi = Math.atan2(hb - ha, ub - ua), vor = abschnitte[abschnitte.length - 1];
            if (vor && Math.abs(vor.wi - wi) < 0.002 && Math.abs(vor.ub - ua) < 0.02) { vor.ub = ub; vor.hb = hb; } else abschnitte.push({ ua, ub, ha, hb, wi });
          }
          for (const sz of innen ? [innen] : [-1, 1]) for (const a of abschnitte) {
            const L = Math.hypot(a.ub - a.ua, a.hb - a.ha), mx = (a.ua + a.ub) / 2, my = (a.ha + a.hb) / 2;
            const li = new THREE.Object3D(); li.scale.x = L; li.position.set(mx, my - 0.011, sz * (tief / 2 + 0.006)); li.rotation.z = a.wi; li.updateMatrix();
            const sc = new THREE.Object3D(); sc.scale.x = L; sc.position.set(mx, my - 0.02 - 0.17, sz * (tief / 2 + 0.009));
            if (sz < 0) sc.rotation.set(0, Math.PI, -a.wi); else sc.rotation.z = a.wi;
            sc.updateMatrix();
            ledTeile[seite].push(LEDGEO.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(q.matrix, li.matrix)));
            scheinTeile[seite].push(SCHEINGEO.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(q.matrix, sc.matrix)));
            ledZahl++;
          }
        }
      }
      // LED-Linien und Scheine je Wandseite zu je einer Geometrie verschmelzen (ein Zeichenaufruf statt Hunderter)
      for (const seite of Object.keys(ledTeile)) if (ledTeile[seite].length) {
        const a = new THREE.Mesh(verschmelzen(ledTeile[seite]), LED); seiten[seite].add(a); leds[seite].push(a);
        const b2 = new THREE.Mesh(verschmelzen(scheinTeile[seite]), LEDSCHEIN); b2.renderOrder = 3; seiten[seite].add(b2); scheine.push(b2);
        for (const x of ledTeile[seite].concat(scheinTeile[seite])) x.dispose();
      }
      // Treppen und Gelaender
      // Gewendelte Stufen (seit 01.11.2026): Jede Stufe ist ein Keil vom Drehpunkt (innere Ecke) bis an den Rand des
      // Rechtecks, die Winkel laufen gleichmaessig von der Richtung "start" zur Richtung "ende" (nord = -y, ost = +x).
      function wendelBauen(tr, ziel) {
        const [x0, y0, x1, y1] = tr.rechteck, [px, py] = tr.drehpunkt, n = tr.stufen || 4, sh = tr.hoehe / n;
        const winkel = { ost: 0, sued: Math.PI / 2, west: Math.PI, nord: -Math.PI / 2 };
        let a0 = winkel[tr.start], a1 = winkel[tr.ende];
        while (a1 - a0 > Math.PI) a1 -= 2 * Math.PI;
        while (a0 - a1 > Math.PI) a1 += 2 * Math.PI;
        const strahl = (a) => {         // Schnitt des Strahls vom Drehpunkt mit dem Rechteckrand
          const dx = Math.cos(a), dy = Math.sin(a);
          let t = Infinity;
          if (dx > 1e-9) t = Math.min(t, (x1 - px) / dx); else if (dx < -1e-9) t = Math.min(t, (x0 - px) / dx);
          if (dy > 1e-9) t = Math.min(t, (y1 - py) / dy); else if (dy < -1e-9) t = Math.min(t, (y0 - py) / dy);
          return [px + dx * t, py + dy * t];
        };
        const ecken = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].filter(([ex, ey]) => Math.hypot(ex - px, ey - py) > 1e-6)
          .map(([ex, ey]) => ({ p: [ex, ey], a: Math.atan2(ey - py, ex - px) }));
        for (let i = 0; i < n; i++) {
          const wa = a0 + (a1 - a0) * i / n, wb = a0 + (a1 - a0) * (i + 1) / n, lo = Math.min(wa, wb), hi = Math.max(wa, wb);
          const zw = ecken.filter((e) => [e.a, e.a + 2 * Math.PI, e.a - 2 * Math.PI].some((w) => w > lo + 1e-6 && w < hi - 1e-6))
            .sort((p, q) => (wb > wa ? 1 : -1) * (p.a - q.a)).map((e) => e.p);
          const poly = [[px, py], strahl(wa), ...zw, strahl(wb)];
          const form = new THREE.Shape(poly.map(([x, y]) => new THREE.Vector2(x, -y)));
          const geo = new THREE.ExtrudeGeometry(form, { depth: (tr.z0 || 0) + sh * (i + 1), bevelEnabled: false, steps: 1 });
          geo.rotateX(-Math.PI / 2);
          const st = new THREE.Mesh(geo, BILD ? mat("weiss") : i % 2 ? bodenMat("fliese_dunkel") : mat("anthrazit"));
          st.castShadow = st.receiveShadow = true; ziel.add(st);
          if (BILD) {                 // Trittstufe aus Eiche obenauf
            const tg2 = new THREE.ExtrudeGeometry(form, { depth: 0.035, bevelEnabled: false, steps: 1 }); tg2.rotateX(-Math.PI / 2);
            const tp = new THREE.Mesh(tg2, mat("eiche")); tp.position.y = (tr.z0 || 0) + sh * (i + 1) - 0.033;
            tp.castShadow = tp.receiveShadow = true; ziel.add(tp);
          }
        }
      }
      for (const tr of E.treppen || []) {
        if (tr.art === "podest") {            // seit 01.11.2026: massives Podest bis zur angegebenen Hoehe
          const [x0, y0, x1, y1] = tr.rechteck;
          const p = new THREE.Mesh(new THREE.BoxGeometry(x1 - x0, tr.hoehe, y1 - y0), bodenMat("fliese_dunkel"));
          p.position.set((x0 + x1) / 2, tr.hoehe / 2, (y0 + y1) / 2); p.castShadow = p.receiveShadow = true; g.add(p);
          continue;
        }
        if (tr.art === "wendel") {            // gewendelte Stufen: Keile um den Drehpunkt, begrenzt vom Rechteck
          wendelBauen(tr, g);
          continue;
        }
        const dx = tr.bis[0] - tr.von[0], dz = tr.bis[1] - tr.von[1], L = Math.hypot(dx, dz), n = tr.stufen || 14;
        const z0 = tr.z0 || 0;
        const tg = new THREE.Group(); tg.position.set(tr.von[0], 0, tr.von[1]); tg.rotation.y = Math.atan2(dx, dz);
        const sh = tr.hoehe / n;
        for (let i = 0; i < n; i++) {
          const st = new THREE.Mesh(new THREE.BoxGeometry(tr.breite, z0 + sh * (i + 1), L / n), BILD ? mat("weiss") : i % 2 ? bodenMat("fliese_dunkel") : mat("anthrazit"));
          st.position.set(0, (z0 + sh * (i + 1)) / 2, (i + 0.5) * L / n); st.castShadow = st.receiveShadow = true; tg.add(st);
          if (BILD) {                 // Trittstufe aus Eiche, leicht ueberstehend (wie in der Bildansicht)
            const tp = new THREE.Mesh(new THREE.BoxGeometry(tr.breite + 0.02, 0.035, L / n + 0.025), mat("eiche"));
            tp.position.set(0, z0 + sh * (i + 1) - 0.0165, (i + 0.5) * L / n + 0.012); tp.castShadow = tp.receiveShadow = true; tg.add(tp);
          }
        }
        const richtung = { sued: [0, 1], nord: [0, -1], ost: [1, 0], west: [-1, 0] }[tr.gelaender];
        if (richtung) {                 // Gelaender auf der genannten Seite: lokal +x zeigt in der Welt nach (cos, -sin)
          const th = tg.rotation.y, x = Math.sign(Math.cos(th) * richtung[0] - Math.sin(th) * richtung[1] || 1) * (tr.breite / 2 - 0.03);
          for (let i = 0; i <= n; i++) {
            const st = new THREE.Mesh(new THREE.BoxGeometry(0.025, 0.9, 0.025), mat("weiss"));
            st.position.set(x, z0 + sh * i + 0.45, i * L / n); st.castShadow = true; tg.add(st);
          }
          const hl = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, Math.hypot(L, tr.hoehe)), mat(BILD ? "eiche" : "schwarz"));
          hl.position.set(x, z0 + tr.hoehe / 2 + 0.92, L / 2); hl.rotation.x = -Math.atan2(tr.hoehe, L); tg.add(hl);
        }
        g.add(tg);
      }
      for (const lin of E.gelaender || []) {
        const [a, b] = lin, len = Math.hypot(b[0] - a[0], b[1] - a[1]);
        const gl = new THREE.Mesh(new THREE.BoxGeometry(len, 0.05, 0.05), mat("schwarz"));
        gl.position.set((a[0] + b[0]) / 2, 0.92, (a[1] + b[1]) / 2); gl.rotation.y = -Math.atan2(b[1] - a[1], b[0] - a[0]); g.add(gl);
        const sp = new THREE.Mesh(new THREE.BoxGeometry(len, 0.86, 0.01), mat("glas"));
        sp.position.set((a[0] + b[0]) / 2, 0.45, (a[1] + b[1]) / 2); sp.rotation.y = gl.rotation.y; g.add(sp);
      }
      // Moebel. Seit 03.11.2026 werden alle festen Teile je Material (und Schattenwurf) zu einer Geometrie verschmolzen:
      // die Moebel des Stils "bild" bestehen aus vielen Teilen, auf dem Handy zaehlt jeder Zeichenaufruf. Bildschirme
      // bleiben einzeln, weil sie ihr Bild wechseln.
      const bildschirme = [], eimer = new Map();
      for (const m of E.moebel || []) {
        const mo = moebelBauen(m, mat);
        const raum = raeume.find((x) => imPoly(x.poly, m.x, m.y));
        if (raum && raum.stufe) mo.position.y += raum.stufe;
        if (m.geraet) mo.traverse((o) => { if (o.userData.bildschirm) { o.material = o.material.clone(); bildschirme.push({ mesh: o, geraet: m.geraet, leinwand: !!o.userData.leinwand }); } });
        mo.updateMatrixWorld(true);              // noch ohne Elterngruppe: matrixWorld liegt im Etagen-Bezug
        const weg = [];
        mo.traverse((o) => {
          if (!o.isMesh || o.userData.bildschirm || Array.isArray(o.material) || !o.geometry.attributes.uv || !o.geometry.attributes.normal) return;
          const k = o.material.uuid + (o.castShadow ? "|s" : "");
          if (!eimer.has(k)) eimer.set(k, { mat: o.material, geos: [], schatten: o.castShadow });
          eimer.get(k).geos.push(o.geometry.clone().applyMatrix4(o.matrixWorld)); weg.push(o);
        });
        for (const o of weg) o.parent.remove(o);
        g.add(mo);
      }
      for (const e of eimer.values()) {
        const me = new THREE.Mesh(verschmelzen(e.geos), e.mat);
        me.castShadow = e.schatten; me.receiveShadow = true; g.add(me);
        for (const x of e.geos) x.dispose();
      }
      // Geraete: Lichtpunkt (Sprite), Ring zum Pulsieren, kleines warmes Licht wenn an
      const geraete = [];
      for (const ge of E.geraete || []) {
        const p = new THREE.Vector3(ge.x, ge.z != null ? ge.z : 1, ge.y);
        const kern = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLUT, color: 0x9aa6bc, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending, toneMapped: false }));
        kern.position.copy(p); kern.scale.setScalar(0.32); kern.renderOrder = 10; kern.userData.gid = ge.id; g.add(kern);
        const ring = new THREE.Sprite(new THREE.SpriteMaterial({ map: RING, color: 0xffcf87, transparent: true, depthWrite: false, depthTest: false, opacity: 0, toneMapped: false }));
        ring.position.copy(p); ring.scale.setScalar(0.4); ring.renderOrder = 11; g.add(ring);
        const li = new THREE.PointLight(0xffb15c, 0, 2.6, 1.8); li.position.copy(p).add(new THREE.Vector3(0, 0.15, 0)); g.add(li);
        let pegel = null;                // Lautsprecher: kleiner Pegel ueber dem Geraet, solange Musik laeuft
        if (ge.symbol === "lautsprecher") {
          pegel = new THREE.Group(); pegel.position.copy(p).add(new THREE.Vector3(0, 0.3, 0)); pegel.visible = false;
          for (let i = 0; i < 5; i++) {
            const st = new THREE.Mesh(new THREE.BoxGeometry(0.035, 1, 0.035), new THREE.MeshBasicMaterial({ color: i < 3 ? 0xffb15c : 0xffd79a, toneMapped: false, transparent: true, opacity: 0.9 }));
            st.position.x = (i - 2) * 0.05; st.scale.y = 0.05; st.userData.phase = i * 1.7; pegel.add(st);
          }
          g.add(pegel);
        }
        geraete.push({ g: ge, kern, ring, licht: li, an: false, weg: false, wert: 0, verdeckt: false, pegel, spielt: false });
      }
      // Saugroboter (faehrt, wenn er saugt)
      const sauger = new THREE.Group();
      const sk = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.09, 28), mat("schwarz")); sk.position.y = 0.045; sk.castShadow = true; sauger.add(sk);
      const sl = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.03, 16), new THREE.MeshStandardMaterial({ color: 0x0b0f18, emissive: 0xa9c4ff, emissiveIntensity: 1.6 }));
      sl.position.y = 0.1; sauger.add(sl);
      const sg = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLUT, color: 0xa9c4ff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
      sg.scale.setScalar(0.9); sg.position.y = 0.1; sauger.add(sg);
      sauger.visible = false; g.add(sauger);
      const spur = new THREE.InstancedMesh(SPURGEO, new THREE.MeshBasicMaterial({ color: 0xa9c4ff, transparent: true, opacity: 0.35, depthWrite: false, blending: THREE.AdditiveBlending }), 48);
      spur.count = 0; spur.frustumCulled = false; g.add(spur);
      g.userData.y0 = y0;
      szene.add(g);
      const wandteile = [];
      for (const s of Object.values(seiten)) s.traverse((o) => { if (o.isMesh && o.material !== GLAS && o.material !== LED && o.material !== LEDSCHEIN) wandteile.push(o); });
      return { gruppe: g, seiten, raeume, geraete, bildschirme, sauger, wandzahl, E, wandteile, glows, spur, spurPunkte: [], spurZeit: 0, leds, scheine, ledZahl };
    }

    // ---------------------------------------------------------------- Beschriftungen (HTML, damit sie scharf bleiben)
    let labels = [];
    function labelsBauen() {
      ebeneLbl.innerHTML = ""; labels = [];
      const W = welt[etage]; if (!W) return;
      for (const ra of W.raeume) {
        if (ra.ohne_name) continue;
        const d = document.createElement("div"); d.className = "lbl"; d.textContent = ra.name; ebeneLbl.appendChild(d);
        labels.push({ el: d, p: new THREE.Vector3(ra.mitte[0], (W.E.boden || 0) + ra.stufe + 0.05, ra.mitte[1]) });
      }
    }
    const v3 = new THREE.Vector3();
    function labelsSetzen() {
      const w = el.clientWidth, h = el.clientHeight;
      for (const l of labels) {
        v3.copy(l.p).project(kam);
        const sicht = v3.z < 1 && Math.abs(v3.x) < 1.1 && Math.abs(v3.y) < 1.1;
        l.el.style.opacity = sicht ? "1" : "0";
        if (sicht) l.el.style.transform = `translate(-50%,-50%) translate(${((v3.x + 1) / 2 * w).toFixed(1)}px,${((1 - v3.y) / 2 * h).toFixed(1)}px)`;
      }
    }

    // ---------------------------------------------------------------- Kamera
    // Abstand so, dass das ganze Geschoss ins Bild passt. Seit 03.11.2026 ueber die echte Projektion der Hausecken im
    // Zielblickwinkel statt ueber den Umkreis: im Hochformat (Handy) fuellt das Haus so die Breite, vorher blieb fast die
    // Haelfte leer. Drei Naeherungsschritte reichen (der Bildausschnitt waechst fast linear mit dem Abstand).
    const PRUEFKAM = new THREE.PerspectiveCamera(36, 1, 0.1, 200), PV = new THREE.Vector3();
    function passend(az, pol) {
      const a = Math.max(0.3, el.clientWidth / Math.max(1, el.clientHeight)), E = H3 && H3.etagen[etage];
      const U = E ? etagenUmriss(E, H3.umriss) : H3 ? H3.umriss : [-4.5, -4.1, 4.5, 4.1];
      const rad = Math.hypot(U[2] - U[0], U[3] - U[1]) / 2 + 0.6, f = Math.tan(kam.fov * Math.PI / 360);
      let d = Math.max(rad / f, rad / (f * a)) * (a < 1 ? 0.8 : 0.68);
      const y0 = (E && E.boden) || 0, y1 = y0 + ((E && E.hoehe) || 2.5), ecken = [];
      for (const x of [U[0], U[2]]) for (const z of [U[1], U[3]]) for (const y of [y0 - 0.2, y1]) ecken.push(new THREE.Vector3(x, y, z));
      const A = az == null ? 0.55 : az, P = pol == null ? 0.92 : pol, ziel = K.ziel;
      PRUEFKAM.fov = kam.fov; PRUEFKAM.aspect = a; PRUEFKAM.updateProjectionMatrix();
      try {
        for (let i = 0; i < 3; i++) {
          PRUEFKAM.position.set(ziel.x + d * Math.sin(P) * Math.sin(A), ziel.y + d * Math.cos(P), ziel.z + d * Math.sin(P) * Math.cos(A));
          PRUEFKAM.lookAt(ziel); PRUEFKAM.updateMatrixWorld(); PRUEFKAM.matrixWorldInverse.copy(PRUEFKAM.matrixWorld).invert();
          let mx = 0, my = 0;
          for (const e of ecken) { PV.copy(e).project(PRUEFKAM); mx = Math.max(mx, Math.abs(PV.x)); my = Math.max(my, Math.abs(PV.y)); }
          if (!isFinite(mx) || !isFinite(my) || mx <= 0) break;
          d *= Math.max(mx / 0.92, my / (a < 1 ? 0.78 : 0.86));     // Rand: Hochformat oben Platz fuer Kopf und Knoepfe
        }
      } catch (e) { /* Rueckfall: Umkreis */ }
      return Math.max(4, Math.min(60, d));
    }
    function kamSetzen() {
      const sp = Math.sin(K.pol);
      kam.position.set(K.ziel.x + K.dist * sp * Math.sin(K.az), K.ziel.y + K.dist * Math.cos(K.pol), K.ziel.z + K.dist * sp * Math.cos(K.az));
      kam.lookAt(K.ziel);
    }
    function groesse() {
      const w = el.clientWidth || 300, h = el.clientHeight || 300;
      r.setSize(w, h, false); kam.aspect = w / h; kam.updateProjectionMatrix(); weck();
    }

    // ---------------------------------------------------------------- Waende zur Kamera hin absenken (Puppenhaus-Blick)
    function waendeAnpassen(dt) {
      const W = welt[etage]; if (!W) return false;
      const hx = Math.sin(K.az), hz = Math.cos(K.az), N = { sued: [0, 1], nord: [0, -1], ost: [1, 0], west: [-1, 0] };
      let bewegt = false;
      for (const [s, n] of Object.entries(N)) {
        const d = n[0] * hx + n[1] * hz, t = Math.max(0, Math.min(1, (d - 0.12) / 0.4));
        const soll = wandTief ? 0.16 : 1 - 0.84 * t, gr = W.seiten[s];
        const neu = gr.scale.y + (soll - gr.scale.y) * Math.min(1, dt * 7);
        if (Math.abs(neu - gr.scale.y) > 0.002) { gr.scale.y = neu; bewegt = true; } else gr.scale.y = soll;
      }
      const ins = W.seiten.innen, sollI = wandTief ? 0.38 : 1, neuI = ins.scale.y + (sollI - ins.scale.y) * Math.min(1, dt * 7);
      if (Math.abs(neuI - ins.scale.y) > 0.002) { ins.scale.y = neuI; bewegt = true; } else ins.scale.y = sollI;
      // LED-Linie und Schein nur an (fast) voller Wand, abgesenkt wuerden sie flachgedrueckt (Pruefung 03.11., Befund 12)
      for (const m of Object.values(W.leds || {}).flat().concat(W.scheine || [])) m.visible = !m.parent || m.parent.scale.y > 0.92;
      return bewegt;
    }

    // Leuchtpunkte hinter einer Wand (von der Kamera aus gesehen) nur gedimmt zeigen, sonst wirken sie wie im Nachbarraum
    const sichtStrahl = new THREE.Raycaster(), pw = new THREE.Vector3(), rw = new THREE.Vector3();
    let sichtZeit = 0;
    function verdeckungPruefen(W) {
      for (const x of W.geraete) {
        x.kern.getWorldPosition(pw);
        rw.copy(pw).sub(kam.position); const d = rw.length(); rw.normalize();
        sichtStrahl.set(kam.position, rw); sichtStrahl.far = d - 0.2;
        x.verdeckt = sichtStrahl.intersectObjects(W.wandteile, false).length > 0;
      }
    }

    // ---------------------------------------------------------------- Tageslicht (seit 01.11.2026)
    // Sonnenstand nach der NOAA-Naeherung fuer die eingestellte Lage (Standard Mitte NRW); Planoben gilt als Norden, ein
    // abweichender Nordwinkel kommt aus haus3d.json (nordwinkel, Grad im Uhrzeigersinn). opt.zeit "tag"/"nacht" zwingt es.
    function sonnenstand(d, lat, lon) {
      const rad = Math.PI / 180, j = d.getUTCFullYear(), tag = (Date.UTC(j, d.getUTCMonth(), d.getUTCDate()) - Date.UTC(j, 0, 0)) / 864e5;
      const std = d.getUTCHours() + d.getUTCMinutes() / 60, g = 2 * Math.PI / 365 * (tag - 1 + (std - 12) / 24);
      const dekl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
      const zgl = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
      const ha = ((std * 60 + zgl + 4 * lon) / 4 - 180) * rad, phi = lat * rad;
      const zen = Math.acos(Math.max(-1, Math.min(1, Math.sin(phi) * Math.sin(dekl) + Math.cos(phi) * Math.cos(dekl) * Math.cos(ha))));
      let az = Math.acos(Math.max(-1, Math.min(1, (Math.sin(phi) * Math.cos(zen) - Math.sin(dekl)) / (Math.cos(phi) * Math.sin(zen) || 1e-6)))) / rad;
      az = ha > 0 ? (az + 180) % 360 : (540 - az) % 360;
      return { hoehe: 90 - zen / rad, azimut: az };
    }
    let tagwert = -1, lichtAnim = null, lichtAkt = null, nachtModus = false;
    function lichtZiel() {
      const lage = (H3 && H3.lage) || {}, z = nachtModus ? "nacht" : opt.zeit;
      const st = z === "tag" ? { hoehe: 42, azimut: 205 } : z === "nacht" ? { hoehe: -25, azimut: 0 } : sonnenstand(new Date(), lage.breite || 51.5, lage.laenge || 7.5);
      const t = Math.max(0, Math.min(1, (st.hoehe + 3) / 12));             // 0 Nacht, 1 Tag, dazwischen Daemmerung
      const rad = Math.PI / 180, az = (st.azimut - ((H3 && H3.nordwinkel) || 0)) * rad, el = Math.max(6, st.hoehe) * rad, y0 = (H3 && H3.etagen[etage] && H3.etagen[etage].boden) || 0;
      if (t > 0) return { t, pos: new THREE.Vector3(Math.sin(az) * Math.cos(el) * 20, y0 + Math.sin(el) * 20, -Math.cos(az) * Math.cos(el) * 20),
        farbe: new THREE.Color(st.hoehe < 12 ? 0xffc58f : 0xfff1df), staerke: 0.35 + 3.0 * t, y0 };
      return { t, pos: new THREE.Vector3(-8, y0 + 16, 6), farbe: new THREE.Color(0x9fb4ff), staerke: 0.32, y0 };   // Mondlicht: schwach, kuehl
    }
    // Tag/Nacht gleitet seit 01.11.2026 abends ueber knapp 2 s (wie ein Daemmerungsschnitt), Etagenwechsel setzt sofort
    function lichtSetzen() {
      const ziel = lichtZiel();
      if (Math.abs(ziel.t - tagwert) < 0.01 && etage === sonne.userData.etage) return;
      const sofort = tagwert < 0 || etage !== sonne.userData.etage || !lichtAkt;
      tagwert = ziel.t; sonne.userData.etage = etage;
      if (sofort) { lichtAnim = null; lichtAkt = ziel; lichtAnwenden(ziel); return; }
      lichtAnim = { von: lichtAkt, nach: ziel, start: performance.now() };
      weck();
    }
    function lichtAnwenden(z) {
      const t = z.t, n = 1 - t;
      // seit 04.11.2026: Etage mit ueberwiegend Estrichboden (Keller) im Stil "bild" neutral statt warm, wie die Bildansicht
      const raL = (welt[etage] && welt[etage].E.raeume) || [], keller = BILD && raL.length > 0 && raL.filter((x) => x.boden === "beton").length * 2 > raL.length;
      sonne.position.copy(z.pos); sonne.color.copy(z.farbe); sonne.intensity = z.staerke;
      sonne.target.position.set(0, z.y0, 0);
      // Nacht wie im Reel: kuehles, dunkelblaues Grundlicht, davon heben sich die warmen Lichtinseln ab
      himmel.color.setHex(t > 0.5 ? 0xc4d8f5 : 0x3e5294); himmel.groundColor.setHex(t > 0.5 ? 0x5a4a3a : 0x10131c); himmel.intensity = 0.1 + 0.22 * t + 0.16 * n;
      // Im Stil "bild" auch abends warmes, gleichmaessiges
      // Grundlicht wie in der Bildansicht statt des kuehlen Reel-Blaus; Fronten und Polster saufen nicht mehr ab
      if (BILD) { himmel.color.setHex(t > 0.5 ? 0xc4d8f5 : keller ? 0xe2e5ea : 0xe9d9c4); himmel.groundColor.setHex(t > 0.5 ? 0x5a4a3a : 0x3b3228); himmel.intensity = 0.1 + 0.22 * t + 0.5 * n; }
      r.toneMappingExposure = 1.0 + 0.04 * n;
      GLAS.emissive.setHex(0xffb168); GLAS.emissiveIntensity = 0.55 * n;          // Fenster glimmen nachts warm
      if (BILD) {                    // Stil "bild": tagsueber helle Fensterflaechen wie in der Bildansicht, LED-Schein nachts kraeftiger
        GLAS.emissive.setRGB(1.0 * t + 1.0 * n, 0.98 * t + 0.69 * n, 0.95 * t + 0.41 * n); GLAS.emissiveIntensity = 0.85 * t + 0.55 * n;
        GLAS.opacity = 0.16 + 0.5 * t;
        LEDSCHEIN.opacity = 0.28 + 0.2 * n;
      }
      szene.traverse((o) => {
        if (o.isPointLight && o.userData.raumlicht) o.intensity = o.userData.basis * (0.12 + 0.6 * n);
        const ms = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
        for (const m of ms) if (m && m.envMapIntensity != null) {
          if (m.userData.env == null) m.userData.env = m.envMapIntensity;
          m.envMapIntensity = m.userData.env * (BILD ? 0.55 + 0.2 * t : 0.22 + 0.53 * t);
        }
      });
      for (const W of Object.values(welt)) for (const gw of W.glows || []) {
        gw.schein.material.opacity = 0.7 * n * gw.staerke; gw.insel.material.opacity = (keller ? 0.2 : 0.55) * n * gw.staerke;
        gw.schein.visible = gw.insel.visible = n > 0.02;
      }
    }

    // ---------------------------------------------------------------- Zustaende
    function zustaende() {
      if (!D || !etage || !welt[etage]) return;
      const W = welt[etage], Z = D.zustaende || {};
      const an = {};
      for (const x of W.geraete) { x.an = geraetAn(x.g, Z); x.weg = geraetWeg(x.g, Z); an[x.g.id] = x.an; }
      for (const b of W.bildschirme) {
        const m = b.mesh.material, ein = !!an[b.geraet];
        // seit 01.11.2026 abends: an zeigt der Bildschirm Inhalt (App und Titel bzw. Code am PC) statt nur Licht
        const tex = ein ? bildschirmInhalt(W, b, Z) : null, hatte = !!m.emissiveMap;
        m.emissiveMap = tex; m.map = tex;
        if (hatte !== !!tex) m.needsUpdate = true;
        m.emissive.setHex(tex ? 0xffffff : ein ? (b.leinwand ? 0xdfe6ff : 0x5d86ff) : 0x000000);
        m.emissiveIntensity = tex ? 0.95 : ein ? (b.leinwand ? 0.9 : 0.8) : 0;
        m.color.setHex(tex ? 0xffffff : ein && b.leinwand ? 0xf2f4f8 : b.leinwand ? 0xd9dbdf : 0x0a0c10);
      }
      for (const x of W.geraete) {
        x.spielt = x.g.entitaeten.some((e) => /^media_player\./.test(e) && Z[e] && Z[e].s === "playing");
        if (x.pegel) x.pegel.visible = x.spielt;
      }
      const S = D.sauger, ra = S && S.aktiv && S.etage === etage && W.raeume.find((x) => x.id === S.raum);
      W.sauger.visible = !!ra; W.sauger.userData.raum = ra || null;
      const st = new Date((D.zustand_stand || D.stand || Date.now() / 1000) * 1000);
      const alle = Object.values(welt).flatMap((x) => x.geraete), laufen = alle.filter((x) => geraetAn(x.g, Z)).length;
      const aussen = Object.keys(Z).find((k) => /aussentemperatur/.test(k)), at = aussen ? parseFloat(Z[aussen].s) : NaN;
      kopf.querySelector(".titel small").textContent = (W.E.name ? W.E.name + " · " : "") +
        T.laufen.replace("{0}", laufen).replace("{1}", alle.length) + (isFinite(at) ? " · " + T.draussen.replace("{0}", at.toLocaleString(LOC, { maximumFractionDigits: 1 })) : "") +
        " · " + T.stand.replace("{0}", st.toLocaleTimeString(LOC, { hour: "2-digit", minute: "2-digit" }));
      lichtSetzen();
      leisteZeigen(true);
      if (gewaehlt) karteZeigen(true);
      weck();
    }
    function bildschirmInhalt(W, b, Z) {
      const dev = W.geraete.find((x) => x.g.id === b.geraet); if (!dev) return null;
      if (dev.g.symbol === "pc") return inhaltTex("", "", "pc");
      // Leinwand und Fernseher: Mediaplayer des Geraets, bei der Leinwand auch Zuspieler im TV-Board (Symbol tv, <= 1,5 m)
      const p = b.mesh.getWorldPosition(new THREE.Vector3());
      const nah = W.geraete.filter((x) => x !== dev && x.g.symbol === "tv" && Math.hypot(x.g.x - p.x, x.g.y - p.z) < 1.5);
      const ents = dev.g.entitaeten.concat(...nah.map((x) => x.g.entitaeten)).filter((e) => /^media_player\./.test(e));
      let best = null;
      for (const e of ents) {
        const z = Z[e]; if (!z || !/^(playing|paused|on|idle)$/.test(z.s)) continue;
        const a = z.a || {}, eins = a.app_name || a.source || "", zwei = [a.media_title, a.media_artist].filter(Boolean).join(" · ");
        const wert = (z.s === "playing" ? 4 : 0) + (zwei ? 2 : 0) + (eins ? 1 : 0) + (a.bild ? 2 : 0);   // mit Titelbild bevorzugt
        if (!best || wert > best.wert) best = { wert, eins: eins || z.n || dev.g.name, zwei, bild: a.bild || "", logo: a.logo === true };
      }
      return best ? inhaltTex(best.eins, best.zwei, "tv", best.bild, best.logo) : inhaltTex(dev.g.name, "", "tv");
    }
    // ---------------------------------------------------------------- Bedienleiste (wie im Reel)
    const SYM = {
      tv: '<svg viewBox="0 0 24 24"><path d="M3 5h18v11H3zM8 19h8v2H8z"/></svg>',
      lautsprecher: '<svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9zm13.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4z"/></svg>',
      sauger: '<svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 4a2 2 0 1 1 0 4 2 2 0 0 1 0-4z"/></svg>',
      klima: '<svg viewBox="0 0 24 24"><path d="M11 2h2v20h-2zM2 11h20v2H2zM5 5l1.4-1.4 13.2 13.2L18.2 18.2zM18.2 3.6l1.4 1.4L6.4 18.2 5 16.8z"/></svg>',
      heizung: '<svg viewBox="0 0 24 24"><path d="M12 2c3 4 6 6 6 11a6 6 0 0 1-12 0c0-3 2-5 3-7 1 3 3 3 3 6 1-2 1-4 0-10z"/></svg>',
      pc: '<svg viewBox="0 0 24 24"><path d="M2 4h20v12H2zM9 18h6v2H9z"/></svg>',
      szene: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
      punkt: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/></svg>' };
    const SCHALTBAR = /^(media_player|switch|light|vacuum|climate|water_heater)\./;
    let szenenListe = [], szeneLaeuft = null, leisteRuhe = 0, hinweisUhr = 0, leisteWarn = { id: "", bis: 0 };
    function leistenMeldung(t) {
      leistenHinweis.textContent = t; leistenHinweis.classList.add("da");
      clearTimeout(hinweisUhr); hinweisUhr = setTimeout(() => leistenHinweis.classList.remove("da"), 3200);
    }
    function hauptEntitaet(g) {            // was ein Tippen auf die Kachel schaltet
      const e = g.entitaeten;
      return e.find((x) => /^media_player\./.test(x)) || e.find((x) => /^(switch|light)\./.test(x)) || e.find((x) => SCHALTBAR.test(x)) || null;
    }
    function leisteZeigen(vonDaten) {
      if (!opt.steuern || !D || !etage || !welt[etage]) return;
      if (vonDaten && performance.now() - leisteRuhe < 4000) return;
      const Z = D.zustaende || {}, W = welt[etage];
      let h = "";
      for (const sz of szenenListe.slice(0, 8))
        h += `<div class="kachel szene${szeneLaeuft === sz.id ? " laeuft" : ""}" data-szene="${esc(sz.id)}"><span class="sym">${SYM.szene}</span><b>${esc(sz.name)}</b></div>`;
      for (const x of W.geraete) {
        const e = hauptEntitaet(x.g); if (!e) continue;
        const z = Z[e], an = istAn(e, z), warn = leisteWarn.id === x.g.id && performance.now() < leisteWarn.bis;
        h += `<div class="kachel${warn ? " warn" : an ? " an" : ""}" data-g="${esc(x.g.id)}" title="${esc(T.halten)}"><span class="sym">${SYM[x.g.symbol] || SYM.punkt}</span>` +
          `<span><b>${esc(x.g.name)}</b><small>${esc(warn ? T.wirklich : zustandText(e, z))}</small></span></div>`;
      }
      leiste.innerHTML = h;
    }
    async function kachelTippen(gid) {
      const W = welt[etage], x = W && W.geraete.find((q) => q.g.id === gid); if (!x) return;
      const e = hauptEntitaet(x.g), dom = e.split(".")[0], z = (D.zustaende || {})[e], an = istAn(e, z);
      if (!/^(media_player|switch|light)$/.test(dom)) { gewaehlt = "g:" + gid; karteZeigen(); weck(); return; }   // Sauger, Klima: Menue
      if (dom === "switch" && an && !(leisteWarn.id === gid && performance.now() < leisteWarn.bis)) {
        leisteWarn = { id: gid, bis: performance.now() + 4000 }; leisteZeigen(); setTimeout(() => leisteZeigen(), 4100); return;
      }
      leisteWarn = { id: "", bis: 0 };
      leistenMeldung(T.sendet);
      let r; try { r = await opt.steuern(e, an ? "turn_off" : "turn_on"); } catch (ex) { r = { ok: false, meldung: String(ex && ex.message || ex) }; }
      leistenMeldung((r && r.meldung) || "");
      leisteRuhe = 0; setTimeout(() => { if (!aus) holen(); }, 1200);
    }
    async function szeneStarten(id) {
      if (!opt.szenen || szeneLaeuft) return;
      szeneLaeuft = id; leisteZeigen(); leistenMeldung(T.szene_laeuft);
      let r; try { r = await opt.szenen.starten(id); } catch (ex) { r = { ok: false, meldung: String(ex && ex.message || ex) }; }
      szeneLaeuft = null; leisteZeigen(); leistenMeldung((r && r.meldung) || "");
      setTimeout(() => { if (!aus) holen(); }, 1500);
    }
    let druck = null;
    leiste.addEventListener("pointerdown", (ev) => {
      leisteRuhe = performance.now();
      const k = ev.target.closest(".kachel"); if (!k) return;
      druck = { k, x: ev.clientX, lang: false, uhr: setTimeout(() => {          // lange druecken: volles Menue
        druck.lang = true; if (k.dataset.g) { gewaehlt = "g:" + k.dataset.g; karteZeigen(); weck(); }
      }, 480) };
    });
    const druckEnde = () => { if (druck) clearTimeout(druck.uhr); };
    leiste.addEventListener("pointerup", druckEnde); leiste.addEventListener("pointercancel", () => { druckEnde(); druck = null; });
    leiste.addEventListener("pointermove", (ev) => { if (druck && Math.abs(ev.clientX - druck.x) > 10) { clearTimeout(druck.uhr); druck.verschoben = true; } });
    leiste.addEventListener("click", (ev) => {
      const k = ev.target.closest(".kachel"); const d = druck; druck = null;
      if (!k || (d && (d.lang || d.verschoben))) return;
      if (k.dataset.szene) szeneStarten(k.dataset.szene); else if (k.dataset.g) kachelTippen(k.dataset.g);
    });
    if (opt.szenen) Promise.resolve(opt.szenen.liste()).then((l) => { szenenListe = Array.isArray(l) ? l.filter((x) => x && x.id && x.name) : []; leisteZeigen(); }).catch(() => {});
    function zustandText(eid, z) {
      if (!z) return T.weg;
      const s = String(z.s || ""), n = parseFloat(s);
      if (!isNaN(n) && isFinite(s)) return n.toLocaleString(LOC, { maximumFractionDigits: 1 }) + (z.e ? " " + z.e : "");
      const k = s.toLowerCase().replace(/^.*\./, "");
      return (ZUST[k] || [s, s])[SI];
    }
    function raumVon(W, x, y) { return W.raeume.find((ra) => imPoly(ra.poly, x, y)) || null; }
    // ---------------------------------------------------------------- Karte und Geraete-Menue (seit 01.11.2026)
    // Raum: Liste der Geraete (antippen oeffnet das Geraet). Geraet: Foto, Zustand und je Entitaet die Bedienung, die
    // ihre Art hergibt. Geschaltet wird nur ueber opt.steuern (Bruecke: feste Liste, Jarvis-Regeln); ohne nur Anzeige.
    const FOTO = {}, SVG = {
      power: '<svg viewBox="0 0 24 24"><path d="M11 2h2v10h-2zM6.3 5.3l1.4 1.4A7 7 0 1 0 16.3 6.7l1.4-1.4A9 9 0 1 1 6.3 5.3z"/></svg>',
      zurueck: '<svg viewBox="0 0 24 24"><path d="M6 6h2v12H6zM9.5 12 18 6v12z"/></svg>',
      spiel: '<svg viewBox="0 0 24 24"><path d="M7 5v14l6-7zM14 5h3v14h-3z"/></svg>',
      vor: '<svg viewBox="0 0 24 24"><path d="M16 6h2v12h-2zM6 6l8.5 6L6 18z"/></svg>',
      stumm: '<svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9zm13.6 3 2.7-2.7-1.4-1.4-2.7 2.7-2.7-2.7-1.4 1.4 2.7 2.7-2.7 2.7 1.4 1.4 2.7-2.7 2.7 2.7 1.4-1.4z"/></svg>' };
    let menueRuhe = 0, bestaetigen = { e: "", bis: 0 }, meldText = "", meldNein = false;
    const zahl = (v, d) => Number(v).toLocaleString(LOC, { maximumFractionDigits: d == null ? 1 : d });
    const knopf = (e, d, inhalt, extra) => `<button data-e="${esc(e)}" data-d="${esc(d)}"${extra || ""}>${inhalt}</button>`;
    function fotoLaden(name, img) {
      if (!opt.bild || !name) return;
      if (!FOTO[name]) FOTO[name] = Promise.resolve(opt.bild(name)).catch(() => null);
      FOTO[name].then((u) => { if (u && img.isConnected) { img.onload = () => { img.hidden = false; }; img.src = u; } });
    }
    function bedienung(e, z) {
      const dom = e.split(".")[0], a = (z && z.a) || {}, s = String((z && z.s) || ""), frei = !!opt.steuern && z && s !== "unavailable";
      let h = "";
      if (dom === "media_player") {
        const f = a.supported_features, kann = (bit) => f == null || (f & bit) !== 0, an = s !== "off" && s !== "standby" && s !== "unavailable";
        if (a.media_title) h += `<div class="titelz">${esc(T.spielt)} ${esc(a.media_title)}${a.media_artist ? " · " + esc(a.media_artist) : ""}</div>`;
        if (frei) {
          h += '<div class="kn">' + knopf(e, an ? "turn_off" : "turn_on", SVG.power + " " + (an ? T.aus_k : T.ein), an ? ' class="an"' : "");
          if (an && kann(16)) h += knopf(e, "media_previous_track", SVG.zurueck, ' aria-label="zurück"');
          if (an && kann(1 | 16384)) h += knopf(e, "media_play_pause", SVG.spiel, ' aria-label="Play/Pause"');
          if (an && kann(32)) h += knopf(e, "media_next_track", SVG.vor, ' aria-label="weiter"');
          if (an && kann(8) && a.is_volume_muted != null)
            h += `<button data-e="${esc(e)}" data-d="volume_mute" data-k="is_volume_muted" data-v="${a.is_volume_muted ? "false" : "true"}"${a.is_volume_muted ? ' class="an"' : ""}>${SVG.stumm} ${a.is_volume_muted ? T.laut : T.stumm}</button>`;
          h += "</div>";
          if (an && kann(4) && a.volume_level != null)
            h += `<label>${T.lautstaerke} <b data-zeige="${esc(e)}">${Math.round(a.volume_level * 100)}</b></label><input type="range" min="0" max="100" step="1" value="${Math.round(a.volume_level * 100)}" data-e="${esc(e)}" data-d="volume_set" data-k="volume_level" data-teiler="100">`;
          if (an && kann(2048) && Array.isArray(a.source_list) && a.source_list.length)
            h += `<label>${T.quelle}</label><select data-e="${esc(e)}" data-d="select_source" data-k="source">` +
              (a.source && !a.source_list.includes(a.source) ? `<option selected>${esc(a.source)}</option>` : "") +
              a.source_list.map((q) => `<option${q === a.source ? " selected" : ""}>${esc(q)}</option>`).join("") + "</select>";
        }
      } else if (dom === "switch" || dom === "light") {
        if (frei) {
          const an = s === "on", warnen = an && bestaetigen.e === e && performance.now() < bestaetigen.bis;
          h += '<div class="kn">' + (an ? knopf(e, warnen ? "turn_off" : "_bestaetigen", SVG.power + " " + (warnen ? T.wirklich : T.aus_k), warnen ? ' class="warn"' : ' class="an"')
            : knopf(e, "turn_on", SVG.power + " " + T.ein)) + "</div>";
          if (dom === "light" && an && a.brightness != null)
            h += `<label>%</label><input type="range" min="1" max="100" value="${Math.round(a.brightness / 2.55)}" data-e="${esc(e)}" data-d="turn_on" data-k="brightness_pct">`;
        }
      } else if (dom === "vacuum") {
        if (a.battery_level != null) h += `<div class="titelz">${T.akku} ${zahl(a.battery_level, 0)} %</div>`;
        if (frei) h += '<div class="kn">' + knopf(e, "start", T.saugen, s === "cleaning" ? ' class="an"' : "") + knopf(e, "pause", T.pause) +
          knopf(e, "return_to_base", T.heim) + knopf(e, "locate", T.finden) + "</div>";
      } else if (dom === "climate" || dom === "water_heater") {
        const lo = dom === "climate" ? 5 : 40, hi = dom === "climate" ? 32 : 60, step = a.target_temp_step || (dom === "climate" ? 0.5 : 1);
        if (a.current_temperature != null) h += `<div class="titelz">${T.ist} ${zahl(a.current_temperature)} °C</div>`;
        if (frei && typeof a.temperature === "number") {
          const min = Math.max(lo, a.min_temp || lo), max = Math.min(hi, a.max_temp || hi);
          h += `<div class="kn"><button data-e="${esc(e)}" data-d="set_temperature" data-k="temperature" data-v="${Math.max(min, a.temperature - step)}">−</button>` +
            `<span class="wert">${zahl(a.temperature)} °C</span>` +
            `<button data-e="${esc(e)}" data-d="set_temperature" data-k="temperature" data-v="${Math.min(max, a.temperature + step)}">+</button></div>`;
        }
        if (frei && dom === "climate" && Array.isArray(a.hvac_modes) && a.hvac_modes.length)
          h += `<label>${T.modus}</label><select data-e="${esc(e)}" data-d="set_hvac_mode" data-k="hvac_mode">` +
            a.hvac_modes.map((m) => `<option value="${esc(m)}"${m === s ? " selected" : ""}>${esc((ZUST[m] || [m, m])[SI])}</option>`).join("") + "</select>";
        if (frei && dom === "climate" && Array.isArray(a.fan_modes) && a.fan_modes.length)
          h += `<label>${T.luefter}</label><select data-e="${esc(e)}" data-d="set_fan_mode" data-k="fan_mode">` +
            a.fan_modes.map((m) => `<option${m === a.fan_mode ? " selected" : ""}>${esc(m)}</option>`).join("") + "</select>";
      }
      return h;
    }
    function karteZeigen(vonDaten) {
      const W = welt[etage];
      if (!gewaehlt || !W) { karte.classList.remove("da"); karte.dataset.fuer = ""; return; }
      // waehrend jemand am Menue dreht oder waehlt, nicht unter dem Finger neu aufbauen
      if (vonDaten && karte.dataset.fuer === gewaehlt && performance.now() - menueRuhe < 6000) return;
      const Z = D.zustaende || {};
      const zeile = (x) => {
        const werte = x.g.entitaeten.map((e) => zustandText(e, Z[e])).filter((t, i, a) => a.indexOf(t) === i).join(" · ");
        return `<li class="${x.an ? "an" : ""}" data-g="${esc(x.g.id)}"><span>${esc(x.g.name)}</span><span>${esc(x.g.immer && !werte ? T.an : werte)}</span></li>`;
      };
      if (gewaehlt.startsWith("g:")) {
        const x = W.geraete.find((q) => q.g.id === gewaehlt.slice(2)); if (!x) { gewaehlt = null; karte.classList.remove("da"); return; }
        const ra = raumVon(W, x.g.x, x.g.y);
        const teile = x.g.entitaeten.map((e) => {
          const z = Z[e], an = istAn(e, z);
          return `<div class="ent${an ? " an" : ""}"><div class="ez"><span>${esc((z && z.n) || e)}</span><span>${esc(zustandText(e, z))}</span></div>${bedienung(e, z)}</div>`;
        }).join("");
        karte.innerHTML = `<div class="gkopf"><img class="foto" alt="" hidden><div><b>${esc(x.g.name)}</b><small>${esc(ra ? ra.name : "")}${x.an ? " · " + T.an : ""}</small></div></div>${teile}` +
          (opt.steuern ? `<div class="meld${meldNein ? " nein" : ""}">${esc(meldText)}</div>` : `<div class="hinweis">${T.nur_anzeige}</div>`);
        fotoLaden(x.g.foto, karte.querySelector(".foto"));
      } else {
        const ra = W.raeume.find((q) => q.id === gewaehlt.slice(2)); if (!ra) { gewaehlt = null; karte.classList.remove("da"); return; }
        const liste = W.geraete.filter((x) => imPoly(ra.poly, x.g.x, x.g.y));
        karte.innerHTML = `<b>${esc(ra.name)}</b><ul>${liste.length ? liste.map(zeile).join("") : `<li><span>${T.keine_geraete}</span><span></span></li>`}</ul>`;
      }
      if (karte.dataset.fuer !== gewaehlt) { meldText = ""; meldNein = false; }
      karte.dataset.fuer = gewaehlt;
      karte.classList.add("da");
    }
    async function senden(e, d, k, v) {
      if (!opt.steuern) return;
      meldText = T.sendet; meldNein = false;
      const m = karte.querySelector(".meld"); if (m) { m.textContent = meldText; m.classList.remove("nein"); }
      let r;
      try { r = await opt.steuern(e, d, k ? { [k]: v } : undefined); } catch (ex) { r = { ok: false, meldung: String(ex && ex.message || ex) }; }
      meldText = (r && r.meldung) || ""; meldNein = !(r && r.ok);
      menueRuhe = 0; karteZeigen();
      setTimeout(() => { if (!aus) holen(); }, 1200);
    }
    const merkeRuhe = () => { menueRuhe = performance.now(); };
    karte.addEventListener("pointerdown", merkeRuhe); karte.addEventListener("input", (ev) => {
      merkeRuhe();
      const t = ev.target, b = t.dataset && t.dataset.e && karte.querySelector(`b[data-zeige="${CSS.escape(t.dataset.e)}"]`);
      if (b) b.textContent = t.value;
    });
    karte.addEventListener("click", (ev) => {
      const li = ev.target.closest("li[data-g]");
      if (li) { gewaehlt = "g:" + li.dataset.g; karteZeigen(); weck(); return; }
      const b = ev.target.closest("button[data-e]"); if (!b) return;
      if (b.dataset.d === "_bestaetigen") { bestaetigen = { e: b.dataset.e, bis: performance.now() + 4000 }; karteZeigen(); setTimeout(() => karteZeigen(), 4100); return; }
      bestaetigen = { e: "", bis: 0 };
      const v = b.dataset.v == null ? undefined : JSON.parse(b.dataset.v);
      senden(b.dataset.e, b.dataset.d, b.dataset.k, v);
    });
    karte.addEventListener("change", (ev) => {
      const t = ev.target; if (!t.dataset || !t.dataset.e) return;
      let v = t.value;
      if (t.type === "range") v = Number(v) / (Number(t.dataset.teiler) || 1);
      senden(t.dataset.e, t.dataset.d, t.dataset.k, v);
    });

    // ---------------------------------------------------------------- Etagen
    function chips() {
      const c = kopf.querySelector(".chips"); c.innerHTML = "";
      const ord = ["kg", "eg", "og", "dg"].filter((x) => H3.etagen[x]);
      for (const id of ord) {
        const s = document.createElement("span"); s.className = "chip" + (id === etage ? " aktiv" : ""); s.textContent = id.toUpperCase();
        s.addEventListener("click", () => waehlen(id)); c.appendChild(s);
      }
      const mo = document.createElement("span"); mo.className = "chip mond" + (nachtModus ? " aktiv" : ""); mo.textContent = "☾"; mo.title = T.nacht;
      mo.setAttribute("aria-label", T.nacht);
      mo.addEventListener("click", () => { nachtModus = !nachtModus; mo.classList.toggle("aktiv", nachtModus); lichtSetzen(); weck(); }); c.appendChild(mo);
      const w = document.createElement("span"); w.className = "chip" + (wandTief ? " aktiv" : ""); w.textContent = T.waende;
      w.title = T.waende; w.addEventListener("click", () => { wandTief = !wandTief; w.classList.toggle("aktiv", wandTief); weck(); }); c.appendChild(w);
      if (opt.wechsel) {           // zur anderen Ansicht (3D <-> Bild), nur wenn es beide gibt
        const w = document.createElement("span"); w.className = "chip"; w.textContent = opt.wechsel.text;
        w.addEventListener("click", () => opt.wechsel.klick()); c.appendChild(w);
      }
    }
    let etagenAnim = null;
    function waehlen(id) {
      if (!H3 || !H3.etagen[id]) return;
      const vorher = etage;
      etage = id; gewaehlt = null; karte.classList.remove("da");
      for (const [k, W] of Object.entries(welt)) W.gruppe.visible = k === id;
      if (vorher && vorher !== id && welt[id]) {      // neue Etage schwebt von oben (hoeher) bzw. unten ein
        const W = welt[id], hoch = (H3.etagen[id].boden || 0) > (H3.etagen[vorher].boden || 0);
        etagenAnim = { W, von: hoch ? 2.4 : -2.4, start: performance.now() };
        W.gruppe.position.y = W.gruppe.userData.y0 + etagenAnim.von;
      }
      const E = H3.etagen[id];
      const UE = etagenUmriss(E, H3.umriss);
      K.soll = Object.assign(K.soll || {}, { ziel: new THREE.Vector3((UE[0] + UE[2]) / 2, (E.boden || 0) + 0.6, (UE[1] + UE[3]) / 2) });
      tagwert = -1;                     // Sonne fuer die neue Etage neu setzen (lichtSetzen), nicht auf eine feste Richtung
      pjEtage(id);
      chips(); labelsBauen(); zustaende(); leisteZeigen(); weck();
    }
    // ---------------------------------------------------------------- Foto-Projektion (seit 0.6, optional: "die 3D-Ansicht
    // von der Optik der Moebel, Boeden etc. der Bildansicht genau nachempfinden"). Die Bildansicht ist ein Gemini-Bild, das aus
    // genau einer Kamera dieses Modells entstanden ist. Diese Bilder werden aus ihrer Kamera auf die Geometrie projiziert
    // (bis zu 4 je Etage, gewichtet nach Blickwinkel). Eine Tiefenkarte je Bild sorgt dafuer, dass nur Flaechen Farbe bekommen,
    // die in dem Bild wirklich zu sehen waren. Daten: D.projektion = {eg: [{bild, kamera: {az, pol, dist, ziel: [x, y, z]}}]}.
    const PJ_MAX = 4, PJ_NAH = 1, PJ_FERN = 40;
    const PJ_LEER = new THREE.DataTexture(new Uint8Array([0, 0, 0, 255]), 1, 1); PJ_LEER.needsUpdate = true;
    const PJU = { pjAn: { value: new THREE.Vector4() }, pjStaerke: { value: opt.projektion_staerke == null ? 1 : +opt.projektion_staerke } };
    for (let i = 0; i < PJ_MAX; i++) {
      PJU["pjTex" + i] = { value: PJ_LEER }; PJU["pjDep" + i] = { value: PJ_LEER };
      PJU["pjMat" + i] = { value: new THREE.Matrix4() }; PJU["pjPos" + i] = { value: new THREE.Vector3() };
    }
    const PJ_FRAG_KOPF = "varying vec3 vPjW;\nvarying vec3 vPjN;\nuniform vec4 pjAn;\nuniform float pjStaerke;\n" +
      [0, 1, 2, 3].map((i) => `uniform sampler2D pjTex${i};\nuniform sampler2D pjDep${i};\nuniform mat4 pjMat${i};\nuniform vec3 pjPos${i};\n`).join("") +
      `float pjLin(float z) { return 2.0 * ${PJ_NAH.toFixed(1)} * ${PJ_FERN.toFixed(1)} / (${(PJ_FERN + PJ_NAH).toFixed(1)} - (2.0 * z - 1.0) * ${(PJ_FERN - PJ_NAH).toFixed(1)}); }
void pjEin(sampler2D tx, sampler2D dp, mat4 m, vec3 p, inout vec3 sum, inout float ws, inout float wm) {
  vec4 c = m * vec4(vPjW, 1.0);
  if (c.w <= 0.0) return;
  vec3 nd = c.xyz / c.w; vec2 uv = nd.xy * 0.5 + 0.5;
  if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) return;
  float zf = pjLin(nd.z * 0.5 + 0.5);
  if (abs(zf - pjLin(texture(dp, uv).r)) > 0.06) return;
  float fa = abs(dot(normalize(vPjN), normalize(p - vPjW)));
  float rand = smoothstep(0.0, 0.03, min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y)));
  // Saum hinter Objektkanten: liegt in diesem Bild ganz in der Naehe etwas deutlich Naeheres, hat Gemini das Objekt hier
  // oft etwas groesser gezeichnet - die Farbe gehoert dann nicht zu diesem Punkt (sonst "verschmiert" sie beim Drehen)
  // Seit 04.11. nachmittags weich ueber zwei Abstaende (sonst kantige Raender) und nur fuer die AUSWAHL des Bildes, nicht
  // fuer die Deckkraft: liegt ein Punkt in allen Bildern im Saum, bleibt er trotzdem Bildfarbe statt heller 3D-Grundfarbe.
  float nahA = 1e9, nahB = 1e9;
  for (int i = 0; i < 8; i++) {
    float a = float(i) * 0.7853982 + 0.3927;
    vec2 o = vec2(cos(a), sin(a) * 1.333);
    nahA = min(nahA, pjLin(texture(dp, uv + o * 0.006).r));
    nahB = min(nahB, pjLin(texture(dp, uv + o * 0.013).r));
  }
  float saum = (1.0 - smoothstep(0.15, 0.45, zf - nahA)) * (1.0 - 0.6 * smoothstep(0.15, 0.45, zf - nahB));
  float abdeckung = fa * fa * rand;
  // blickwinkelabhaengig: das Bild, dessen Kamera der aktuellen am naechsten ist, bekommt fast alles (sonst Doppelbilder,
  // weil Geminis Ansichten nie ganz deckungsgleich sind); aus jeder Projektor-Kamera erscheint genau ihr Bild
  float nah = dot(normalize(p - vPjW), normalize(cameraPosition - vPjW));
  float w = abdeckung * max(saum, 0.01) * exp(30.0 * (nah - 1.0));
  sum += texture(tx, uv).rgb * w; ws += w; wm = max(wm, abdeckung);
}
`;
    const PJ_FRAG_ENDE = `
if (pjAn.x + pjAn.y + pjAn.z + pjAn.w > 0.0) {
  vec3 pjS = vec3(0.0); float pjWs = 0.0, pjWm = 0.0;
  if (pjAn.x > 0.5) pjEin(pjTex0, pjDep0, pjMat0, pjPos0, pjS, pjWs, pjWm);
  if (pjAn.y > 0.5) pjEin(pjTex1, pjDep1, pjMat1, pjPos1, pjS, pjWs, pjWm);
  if (pjAn.z > 0.5) pjEin(pjTex2, pjDep2, pjMat2, pjPos2, pjS, pjWs, pjWm);
  if (pjAn.w > 0.5) pjEin(pjTex3, pjDep3, pjMat3, pjPos3, pjS, pjWs, pjWm);
  if (pjWs > 0.0) gl_FragColor.rgb = mix(gl_FragColor.rgb, pjS / pjWs, pjStaerke * clamp(pjWm * 2.5, 0.0, 1.0));
}
`;
    function pjMaterial(m) {
      if (!m || m.userData.pj || m.userData.keinPj || !(m.isMeshStandardMaterial || m.isMeshPhysicalMaterial)) return;
      if (m.transparent || m === GLAS || m.name === "fensterglas") return;
      m.userData.pj = true;
      const alt = m.onBeforeCompile;
      m.onBeforeCompile = (sh, rr) => {
        if (alt) alt(sh, rr);
        Object.assign(sh.uniforms, PJU);
        sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vPjW;\nvarying vec3 vPjN;")
          .replace("#include <project_vertex>", "#include <project_vertex>\n{ mat4 pjM = modelMatrix;\n#ifdef USE_INSTANCING\npjM = modelMatrix * instanceMatrix;\n#endif\n" +
            "vPjW = (pjM * vec4(transformed, 1.0)).xyz; vPjN = normalize(mat3(pjM) * objectNormal); }");
        sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\n" + PJ_FRAG_KOPF)
          .replace("#include <colorspace_fragment>", "#include <colorspace_fragment>\n" + PJ_FRAG_ENDE);
      };
      const altKey = m.customProgramCacheKey ? m.customProgramCacheKey.bind(m) : () => "";
      m.customProgramCacheKey = () => altKey() + "|pj1";
      m.needsUpdate = true;
    }
    // Bildschirme (Leinwand, Fernseher, Monitore) bleiben aussen vor: sonst deckt das Foto den Inhalt zu, den der Bildschirm
    // zeigt, wenn er an ist (Plex-Titel, App-Logo, Code am PC). 
    function pjAlle() { for (const W of Object.values(welt)) W.gruppe.traverse((o) => { if (o.isMesh && !o.userData.bildschirm) [].concat(o.material).forEach(pjMaterial); }); }
    const pjCache = {};                 // etage -> {bilder: [{tex, k, kam}], tiefe: [rt], fertig}
    let pjEtageAkt = null;
    function pjKamera(k) {
      const c = new THREE.PerspectiveCamera(36, 4 / 3, PJ_NAH, PJ_FERN), z = k.ziel || [0, 0, 0], sp = Math.sin(k.pol);
      c.position.set(z[0] + k.dist * sp * Math.sin(k.az), z[1] + k.dist * Math.cos(k.pol), z[2] + k.dist * sp * Math.cos(k.az));
      c.lookAt(new THREE.Vector3(z[0], z[1], z[2])); c.updateMatrixWorld(); c.updateProjectionMatrix();
      return c;
    }
    const PJ_TIEFENMAT = new THREE.MeshBasicMaterial({ colorWrite: false, side: THREE.DoubleSide });
    function pjTiefe(W, cam, az) {        // Tiefenkarte aus Sicht des Projektors, mit den Wandhoehen, die diese Kamera hatte
      const rt = new THREE.WebGLRenderTarget(2048, 1536);
      rt.depthTexture = new THREE.DepthTexture(2048, 1536); rt.depthTexture.type = THREE.UnsignedIntType;
      const N = { sued: [0, 1], nord: [0, -1], ost: [1, 0], west: [-1, 0] }, alt = {}, versteckt = [];
      for (const [s, n] of Object.entries(N)) {
        const gr = W.seiten[s]; alt[s] = gr.scale.y;
        const d = n[0] * Math.sin(az) + n[1] * Math.cos(az), t = Math.max(0, Math.min(1, (d - 0.12) / 0.4));
        gr.scale.y = 1 - 0.84 * t;
      }
      const altI = W.seiten.innen.scale.y; W.seiten.innen.scale.y = 1;
      const altY = W.gruppe.position.y; W.gruppe.position.y = W.gruppe.userData.y0;
      W.gruppe.traverse((o) => {
        const m = o.material, weg = o.isSprite || o.isInstancedMesh || o.isLine || o.isPoints ||
          (m && [].concat(m).some((q) => q.transparent || q === LED || q === LEDSCHEIN || q === GLAS || q.blending === THREE.AdditiveBlending));
        if (weg && o.visible) { o.visible = false; versteckt.push(o); }
      });
      if (W.sauger.visible) { W.sauger.visible = false; versteckt.push(W.sauger); }
      const altOv = szene.overrideMaterial, altFog = szene.fog;
      szene.overrideMaterial = PJ_TIEFENMAT; szene.fog = null;
      szene.updateMatrixWorld(true);
      r.setRenderTarget(rt); r.clear(); r.render(szene, cam); r.setRenderTarget(null);
      szene.overrideMaterial = altOv; szene.fog = altFog;
      versteckt.forEach((o) => { o.visible = true; });
      for (const s of Object.keys(N)) W.seiten[s].scale.y = alt[s];
      W.seiten.innen.scale.y = altI; W.gruppe.position.y = altY;
      return rt;
    }
    function pjAnwenden(id) {
      const P = id && pjCache[id], an = [0, 0, 0, 0];
      if (P && P.fertig && welt[id]) {
        if (!P.tiefe) P.tiefe = P.bilder.map((b) => (b ? pjTiefe(welt[id], b.kam, b.k.az) : null));
        P.bilder.forEach((b, i) => {
          if (!b || i >= PJ_MAX) return;
          PJU["pjTex" + i].value = b.tex; PJU["pjDep" + i].value = P.tiefe[i].depthTexture;
          PJU["pjMat" + i].value.multiplyMatrices(b.kam.projectionMatrix, b.kam.matrixWorldInverse);
          PJU["pjPos" + i].value.copy(b.kam.position); an[i] = 1;
        });
      }
      PJU.pjAn.value.set(an[0], an[1], an[2], an[3]);
      weck();
    }
    function pjEtage(id) {
      pjEtageAkt = id;
      const liste = ((D && D.projektion) || {})[id] || [];
      if (!liste.length || !opt.bild) { pjAnwenden(null); return; }
      if (!pjCache[id]) {
        const P = pjCache[id] = { bilder: [], fertig: false };
        Promise.all(liste.slice(0, PJ_MAX).map((p) => Promise.resolve(opt.bild(p.bild)).then((u) => new Promise((ok) => {
          if (!u) return ok(null);
          new THREE.TextureLoader().load(u, (tex) => {
            tex.colorSpace = THREE.NoColorSpace; tex.anisotropy = Math.min(8, r.capabilities.getMaxAnisotropy());
            ok({ tex, k: p.kamera, kam: pjKamera(p.kamera) });
          }, undefined, () => ok(null));
        })).catch(() => null))).then((b) => { P.bilder = b; P.fertig = true; if (pjEtageAkt === id) pjAnwenden(id); });
      }
      pjAnwenden(pjCache[id].fertig ? id : null);
    }

    function aufbauen() {
      for (const W of Object.values(welt)) { szene.remove(W.gruppe); W.gruppe.traverse((o) => { if (o.geometry) o.geometry.dispose(); }); }
      for (const k of Object.keys(pjCache)) { (pjCache[k].tiefe || []).forEach((t) => t && t.dispose()); delete pjCache[k]; }
      for (const k of Object.keys(welt)) delete welt[k];
      for (const eid of Object.keys(H3.etagen)) welt[eid] = etageBauen(eid);
      pjAlle();
      aufgebaut = JSON.stringify(H3);
      if (!etage || !welt[etage]) etage = welt.eg ? "eg" : Object.keys(welt)[0];
      K.dist = passend() * 2.3; K.az = 1.8; K.pol = 0.32;          // Kamerafahrt beim Oeffnen (seit 01.11.2026 abends weiter und ruhiger)
      K.soll = { dist: passend(), az: 0.55, pol: 0.92, tempo: 1.35 };
      waehlen(etage);
    }

    // ---------------------------------------------------------------- Bedienung (Maus, Touch)
    const zeiger = new Map();
    let zug = null, ruhe = performance.now(), bewegt = 0, letzteTipp = 0;
    const cv = r.domElement;
    const zugStart = (knopf, shift) => ({ az: K.az, pol: K.pol, dist: K.dist, ziel: K.ziel.clone(), start: [...zeiger.values()].map((p) => ({ ...p })), knopf, shift });
    cv.addEventListener("pointerdown", (e) => {
      cv.setPointerCapture(e.pointerId);
      zeiger.set(e.pointerId, { x: e.clientX, y: e.clientY });
      zug = zugStart(e.button, e.shiftKey); bewegt = 0; ruhe = performance.now(); K.soll = null; weck();
    });
    cv.addEventListener("pointermove", (e) => {
      if (!zeiger.has(e.pointerId) || !zug) return;
      zeiger.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const p = [...zeiger.values()], s = zug.start;
      if (p.length === 1 && s.length === 1) {
        const dx = p[0].x - s[0].x, dy = p[0].y - s[0].y;
        bewegt = Math.max(bewegt, Math.abs(dx) + Math.abs(dy));
        if (zug.knopf === 2 || zug.shift) verschieben(dx, dy);
        else { K.az = zug.az - dx * 0.007; K.pol = Math.max(0.12, Math.min(1.32, zug.pol - dy * 0.005)); }
      } else if (p.length >= 2 && s.length >= 2) {
        const d0 = Math.hypot(s[0].x - s[1].x, s[0].y - s[1].y), d1 = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
        K.dist = Math.max(3, Math.min(60, zug.dist * d0 / Math.max(1, d1)));
        verschieben(((p[0].x + p[1].x) - (s[0].x + s[1].x)) / 2, ((p[0].y + p[1].y) - (s[0].y + s[1].y)) / 2);
        bewegt = 99;
      } else zug = zugStart(0, false);
      ruhe = performance.now(); weck();
    });
    function verschieben(dx, dy) {
      const f = zug.dist * 0.0015, rechts = new THREE.Vector3(Math.cos(K.az), 0, -Math.sin(K.az)), vor = new THREE.Vector3(Math.sin(K.az), 0, Math.cos(K.az));
      K.ziel.copy(zug.ziel).addScaledVector(rechts, -dx * f).addScaledVector(vor, -dy * f);
      const U = etagenUmriss(H3.etagen[etage], H3.umriss); K.ziel.x = Math.max(U[0] - 2, Math.min(U[2] + 2, K.ziel.x)); K.ziel.z = Math.max(U[1] - 2, Math.min(U[3] + 2, K.ziel.z));
    }
    const ende = (e) => {
      if (zeiger.has(e.pointerId) && bewegt < 6 && zeiger.size === 1 && e.type === "pointerup") tippen(e);
      zeiger.delete(e.pointerId);
      zug = zeiger.size ? zugStart(0, false) : null;
    };
    cv.addEventListener("pointerup", ende); cv.addEventListener("pointercancel", ende);
    cv.addEventListener("contextmenu", (e) => e.preventDefault());
    cv.addEventListener("wheel", (e) => { e.preventDefault(); K.dist = Math.max(3, Math.min(60, K.dist * Math.exp(e.deltaY * 0.0012))); K.soll = null; ruhe = performance.now(); weck(); }, { passive: false });
    const ray = new THREE.Raycaster();
    function tippen(e) {
      const b = cv.getBoundingClientRect(), W = welt[etage]; if (!W) return;
      const jetzt = performance.now(), doppelt = jetzt - letzteTipp < 320; letzteTipp = jetzt;
      const nd = new THREE.Vector2(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
      ray.setFromCamera(nd, kam);
      // Geraete zuerst: naechster Lichtpunkt unter 30 px
      let gid = null, best = 30;
      for (const x of W.geraete) {
        const v = x.kern.getWorldPosition(new THREE.Vector3()).project(kam);
        const d = Math.hypot((v.x + 1) / 2 * b.width - (e.clientX - b.left), (1 - v.y) / 2 * b.height - (e.clientY - b.top));
        if (d < best && v.z < 1) { best = d; gid = x.g.id; }
      }
      const boden = ray.intersectObjects(W.raeume.map((x) => x.boden), false)[0];
      if (doppelt && boden) {           // Doppeltippen: dorthin heranfahren
        K.soll = { ziel: new THREE.Vector3(boden.point.x, (W.E.boden || 0) + 0.6, boden.point.z), dist: Math.max(5, K.dist * 0.55) };
        weck(); return;
      }
      if (gid) gewaehlt = gewaehlt === "g:" + gid ? null : "g:" + gid;
      else if (boden) gewaehlt = gewaehlt === "r:" + boden.object.userData.raum ? null : "r:" + boden.object.userData.raum;
      else gewaehlt = null;
      karteZeigen(); weck();
    }

    // ---------------------------------------------------------------- Bildschleife (nur wenn sich etwas bewegt)
    let laeuft = false, letzte = performance.now(), rafId = 0, bilder = 0, bildZeit = performance.now(), fps = 0, uhrzeit = 0;
    function weck() { if (!laeuft && !aus && !document.hidden) { laeuft = true; rafId = requestAnimationFrame(bild); } }
    function bild(t) {
      laeuft = false;
      if (aus || document.hidden) return;
      const dt = Math.min(0.1, (t - letzte) / 1000); letzte = t; uhrzeit += dt;
      bilder++; if (t - bildZeit > 1000) { fps = bilder * 1000 / (t - bildZeit); bilder = 0; bildZeit = t; }
      let weiter = false;
      if (K.soll) {                     // weich zum Ziel (Etagenwechsel, Anflug, Doppeltippen)
        const k = Math.min(1, dt * (K.soll.tempo || 3.2));
        if (K.soll.ziel) K.ziel.lerp(K.soll.ziel, k);
        if (K.soll.dist != null) K.dist += (K.soll.dist - K.dist) * k;
        if (K.soll.az != null) K.az += (K.soll.az - K.az) * k;
        if (K.soll.pol != null) K.pol += (K.soll.pol - K.pol) * k;
        const fertig = (!K.soll.ziel || K.ziel.distanceTo(K.soll.ziel) < 0.01) && (K.soll.dist == null || Math.abs(K.soll.dist - K.dist) < 0.02) &&
          (K.soll.az == null || Math.abs(K.soll.az - K.az) < 0.002) && (K.soll.pol == null || Math.abs(K.soll.pol - K.pol) < 0.002);
        if (fertig) K.soll = null; else weiter = true;
      }
      if (lichtAnim) {                  // Tag/Nacht weich ueberblenden
        const k = Math.min(1, (performance.now() - lichtAnim.start) / 1800), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        const a = lichtAnim.von, b = lichtAnim.nach;
        lichtAnwenden({ t: a.t + (b.t - a.t) * e, pos: a.pos.clone().lerp(b.pos, e), farbe: a.farbe.clone().lerp(b.farbe, e),
          staerke: a.staerke + (b.staerke - a.staerke) * e, y0: b.y0 });
        if (k >= 1) { lichtAkt = b; lichtAnim = null; } else weiter = true;
      }
      if (etagenAnim) {                 // Etage schwebt ein (0,7 s, weich auslaufend)
        const k = Math.min(1, (performance.now() - etagenAnim.start) / 700), e = 1 - Math.pow(1 - k, 3), Wg = etagenAnim.W.gruppe;
        Wg.position.y = Wg.userData.y0 + etagenAnim.von * (1 - e);
        if (k >= 1) etagenAnim = null; else weiter = true;
      }
      if (opt.drehen && !zug && !K.soll && t - ruhe > 20000) { K.az += dt * 0.05; weiter = true; }
      kamSetzen();
      if (waendeAnpassen(dt)) weiter = true;
      const W = welt[etage];
      if (W && t - sichtZeit > 200) { sichtZeit = t; verdeckungPruefen(W); }
      if (W) {
        for (const x of W.geraete) {                 // weiches Ueberblenden, Puls beim Laufen
          const ziel = x.an ? 1 : 0; x.wert += (ziel - x.wert) * Math.min(1, dt * 3);
          if (Math.abs(ziel - x.wert) > 0.01) weiter = true;
          const puls = x.an ? (uhrzeit * 0.45) % 1 : 0;
          x.kern.material.color.setHex(x.an ? 0xffa94d : x.weg ? 0x3a4256 : 0x6f7f9e);
          x.kern.material.opacity = (x.weg ? 0.45 : 0.75 + 0.25 * x.wert) * (x.verdeckt ? 0.22 : 1);
          x.kern.scale.setScalar((0.22 + 0.16 * x.wert) * (gewaehlt === "g:" + x.g.id ? 1.5 : 1));
          x.ring.material.opacity = x.an && !x.verdeckt ? 0.7 * (1 - puls) : 0; x.ring.scale.setScalar(0.3 + puls * 0.7);
          x.licht.intensity = 2.2 * x.wert;
          if (x.an) weiter = true;
        }
        if (W.sauger.visible && W.sauger.userData.raum) {
          const m = W.sauger.userData.raum.mitte, a = uhrzeit * 0.35;
          W.sauger.position.set(m[0] + Math.cos(a) * 0.7, W.sauger.userData.raum.stufe + 0.01, m[1] + Math.sin(a * 1.3) * 0.5);
          if (uhrzeit - W.spurZeit > 0.15) {           // Spur: alle 0,15 s ein Punkt, aeltere werden kleiner
            W.spurZeit = uhrzeit; W.spurPunkte.unshift(W.sauger.position.clone()); if (W.spurPunkte.length > 48) W.spurPunkte.pop();
            const o = new THREE.Object3D();
            W.spurPunkte.forEach((pt, i) => { o.position.set(pt.x, pt.y + 0.006, pt.z); o.scale.setScalar(1 - i / 52); o.updateMatrix(); W.spur.setMatrixAt(i, o.matrix); });
            W.spur.count = W.spurPunkte.length; W.spur.instanceMatrix.needsUpdate = true;
          }
          weiter = true;
        } else if (W.spur.count) { W.spur.count = 0; W.spurPunkte.length = 0; }
        for (const x of W.geraete) if (x.pegel && x.pegel.visible) {
          x.pegel.children.forEach((st, i) => { st.scale.y = 0.04 + 0.16 * Math.abs(Math.sin(uhrzeit * (2.3 + i * 0.7) + st.userData.phase) * Math.cos(uhrzeit * 1.1 + i)); st.position.y = st.scale.y / 2; });
          x.pegel.quaternion.copy(kam.quaternion);
          weiter = true;
        }
      }
      r.render(szene, kam);
      labelsSetzen();
      // laufende Geraete pulsieren: 15 Bilder/s reichen, nach 2 Minuten ohne Bedienung nur noch 8 (Akku, Wandbildschirm)
      if (weiter || zug) {
        const still = t - ruhe > 120000;
        laeuft = true;
        if (still || (!zug && !K.soll)) setTimeout(() => { if (!aus) rafId = requestAnimationFrame(bild); }, still ? 125 : 66);
        else rafId = requestAnimationFrame(bild);
      }
    }
    const sichtbar = () => { if (!document.hidden) weck(); };
    document.addEventListener("visibilitychange", sichtbar);

    // ---------------------------------------------------------------- Daten
    function daten(d) {
      if (aus || !d) return;
      if (!d.ok || !d.haus3d || !Object.keys(d.haus3d.etagen || {}).length) { meldung.textContent = (d && d.fehler) || T.keine; D = d; return; }
      meldung.textContent = "";
      D = d;
      if (aufgebaut !== JSON.stringify(d.haus3d)) { H3 = d.haus3d; aufbauen(); }
      else zustaende();
    }
    async function holen() { if (!opt.laden) return; try { daten(await opt.laden()); } catch (e) { if (!D) meldung.textContent = String(e.message || e); } }
    const ro = window.ResizeObserver ? new ResizeObserver(groesse) : null;
    if (ro) ro.observe(el); else addEventListener("resize", groesse);
    groesse();
    if (opt.daten) daten(opt.daten); else holen();
    if (opt.laden) uhr = setInterval(() => { if (!document.hidden) holen(); }, (opt.alle_s || 10) * 1000);
    return {
      daten, waehlen,
      raum: (id) => { gewaehlt = "r:" + id; karteZeigen(); weck(); },
      geraet: (id) => { gewaehlt = "g:" + id; karteZeigen(); weck(); },
      kamera: (k) => { Object.assign(K, k || {}); K.soll = null; weck(); },
      waende: (tief) => { wandTief = !!tief; chips(); weck(); },
      info: () => {
        const W = welt[etage];
        return { webgl: true, etage, fps: Math.round(fps), waende: W ? W.wandzahl : 0,
          geraete: W ? W.geraete.map((x) => x.g.id + (x.an ? ":an" : x.weg ? ":weg" : ":aus")) : [],
          verdeckt: W ? W.geraete.filter((x) => x.verdeckt).map((x) => x.g.id) : [],
          bildschirme: W ? W.bildschirme.map((b) => b.geraet + ":" + (b.mesh.material.emissiveIntensity > 0 ? "an" : "aus")) : [],
          sauger: !!(W && W.sauger.visible), karte: karte.classList.contains("da") ? karte.textContent : "",
          kamera: { az: +K.az.toFixed(3), pol: +K.pol.toFixed(3), dist: +K.dist.toFixed(2) },
          nacht: nachtModus, tagwert: +(lichtAkt ? lichtAkt.t : -1).toFixed(2), leiste: leiste.querySelectorAll(".kachel").length,
          pegel: W ? W.geraete.filter((x) => x.pegel && x.pegel.visible).map((x) => x.g.id) : [],
          stil: BILD ? "bild" : "hell", leds: W ? W.ledZahl || 0 : 0,
          aufrufe: r.info.render.calls, dreiecke: r.info.render.triangles };
      },
      zu() {
        aus = true; clearInterval(uhr); cancelAnimationFrame(rafId); if (ro) ro.disconnect();
        document.removeEventListener("visibilitychange", sichtbar);
        szene.traverse((o) => { if (o.geometry) o.geometry.dispose(); });
        for (const m of Object.values(MATS).concat(Object.values(BODEN), [WAND, KANTE, TUERBLATT])) { if (m.map) m.map.dispose(); m.dispose(); }
        GLUT.dispose(); RING.dispose(); r.dispose(); if (r.forceContextLoss) r.forceContextLoss();
        el.innerHTML = ""; el.classList.remove("haus3d");
      },
    };
  }
  window.Haus3D = { oeffnen, version: "1.0", _waende: waendeBerechnen, _istAn: istAn, _hoehe: hoeheBei };
})();
