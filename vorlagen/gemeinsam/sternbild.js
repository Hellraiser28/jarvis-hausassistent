/* Gedaechtnis als Sternbild (29.10.2026). Eine Quelle fuer HUD (PC-Fenster) und App; werkzeuge/sternbild_einbetten.py
   kopiert diese Datei samt sternbild.css zwischen die Marken STERNBILD-START/-ENDE beider Seiten.
   Canvas 2D, ruhig: hoechstens 10 Bilder je Sekunde beim Flimmern (33 ms bei Bewegung), Pause bei verborgener Seite, kein Dauerzeichnen ohne Grund.
   Alles Persoenliche geht nur mit textContent ins DOM (Eintraege sind Nutzertext, nie innerHTML). */
const Sternbild = (function () {
  const GOLD = 2.399963;                       // goldener Winkel
  const hash = (n) => { let h = (n * 2654435761) >>> 0; h ^= h >>> 15; h = Math.imul(h, 2246822519) >>> 0; return (h >>> 0) / 4294967295; };
  const el = (tag, klasse, text) => { const e = document.createElement(tag); if (klasse) e.className = klasse; if (text != null) e.textContent = text; return e; };

  function erzeuge(wurzel, o) {
    const tx = o.tx;
    let F = { haus: "#a9c4ff", privat: "#e3b866" }, RGB = "196,210,236", DIM = "168,180,202", AKZ = "169,196,255", BG = "7,10,18";
    let daten = null, ausgewaehlt = null, fokus = null, suche = "", seitTage = null, geladen = 0, lade = false, bearbeiten = false, sicher = false;
    let zahlText = "", sterne = [], haufen = [], breite = 0, hoehe = 0, dpr = 1;
    // Ruhe zuerst: Im Ruhezustand wird nur bei Aenderung gezeichnet (kein Dauerflimmern, Messung am NAS-Chromium: 60 Sterne
    // mit Flimmern kosteten dort ~0,5 s CPU je Sekunde). Nur ein gewaehlter Stern oder Suchtreffer pulsiert, mit 10 Bildern/s.
    const still = () => (o.ruhig && o.ruhig()) || !(ausgewaehlt || (suche && woerter().length && sterne.some(treffer)));
    const ansicht = { x: 0, y: 0, z: 1, zx: 0, zy: 0, zz: 1 };      // aktuelle und Ziel-Ansicht
    wurzel.textContent = "";
    const huelle = el("div", "sb");
    const kopf = el("div", "sb-kopf"), titel = el("h2", null, tx("sb_titel")), zahl = el("span", "sb-zahl");
    kopf.append(titel, zahl);
    const suchfeld = el("input", "sb-suche"); suchfeld.type = "search"; suchfeld.maxLength = 60; suchfeld.placeholder = tx("sb_suche");
    suchfeld.setAttribute("aria-label", tx("sb_suche")); suchfeld.autocomplete = "off"; suchfeld.enterKeyHint = "search";
    const bild = el("div", "sb-bild"), leinwand = el("canvas"), leer = el("div", "sb-leer");
    leinwand.setAttribute("role", "img"); leinwand.setAttribute("aria-label", tx("sb_aria"));
    bild.append(leinwand, leer);
    const zeit = el("div", "sb-zeit"), zeitText = el("span", "sb-zeit-text"), regler = el("input"), woche = el("button", "sb-woche", tx("sb_woche"));
    regler.type = "range"; regler.min = 0; regler.max = 30; regler.value = 30; regler.step = 1; regler.setAttribute("aria-label", tx("sb_zeitleiste"));
    woche.type = "button";
    zeit.append(regler, el("div", "sb-zeit-zeile")); zeit.lastChild.append(zeitText, woche);
    const chips = el("div", "sb-chips");
    const legende = el("div", "sb-legende");
    const li1 = el("span"), li2 = el("span"); li1.append(el("i", "haus"), tx("sb_haus")); li2.append(el("i", "privat"), tx("sb_privat"));
    legende.append(li1, li2);
    const hinweis = el("div", "sb-hinweis");
    const blatt = el("div", "sb-blatt"); blatt.hidden = true;
    huelle.append(kopf, suchfeld, bild, blatt, zeit, chips, legende, hinweis);
    wurzel.append(huelle);
    const g = leinwand.getContext("2d");
    // Farben kommen aus den CSS-Variablen der Seite (jedes Design setzt eigene, siehe sternbild.css); bei jedem Zeigen neu gelesen
    function farben() {
      const cs = getComputedStyle(huelle), v = (n) => (cs.getPropertyValue(n) || "").trim();
      const hex = (wert, fb) => { g.fillStyle = "#000000"; g.fillStyle = wert || fb; const a = g.fillStyle; g.fillStyle = "#ffffff"; g.fillStyle = wert || fb; return a === g.fillStyle && /^#[0-9a-f]{6}$/i.test(a) ? a : fb; };
      const rgb = (n, fb) => (/^\d{1,3},\s*\d{1,3},\s*\d{1,3}$/.test(v(n)) ? v(n).replace(/\s+/g, "") : fb);
      F = { haus: hex(v("--sb-haus"), F.haus), privat: hex(v("--sb-privat"), F.privat) };
      RGB = rgb("--sb-rgb", RGB); DIM = rgb("--sb-dim-rgb", DIM); AKZ = rgb("--sb-akz-rgb", AKZ); BG = rgb("--sb-bg-rgb", BG); schmutzig = true;
    }

    // ---------------------------------------------------------------- Layout (Einheitskreis, Kern in der Mitte)
    function layout() {
      sterne = (daten && daten.sterne) || [];
      const nach = {};
      sterne.forEach((s) => { (nach[s.thema] = nach[s.thema] || []).push(s); });
      const namen = ((daten && daten.themen) || []).map((t) => t.name).filter((n) => nach[n]);
      const gew = namen.map((n) => Math.sqrt(nach[n].length) + 0.9), summe = gew.reduce((a, b) => a + b, 0) || 1;
      haufen = []; let lauf = 0;
      namen.forEach((n, i) => {
        const w = gew[i], winkel = -Math.PI / 2 + 2 * Math.PI * (lauf + w / 2) / summe; lauf += w;
        const liste = nach[n].slice().sort((a, b) => a.id - b.id), k = liste.length;
        const bogen = 2 * Math.PI * 0.6 * w / summe;
        let r = Math.min(0.1 + 0.07 * Math.sqrt(k), bogen * 0.46, 0.3);
        const ring = namen.length === 1 ? 0 : 0.6 + (i % 2 ? 0.08 : -0.06);
        const cx = Math.cos(winkel) * ring, cy = Math.sin(winkel) * ring;
        liste.forEach((s, j) => {
          const a = j * GOLD + hash(s.id) * 0.5, rr = k === 1 ? 0 : r * Math.sqrt((j + 0.5) / k) * (0.88 + 0.24 * hash(s.id + 7));
          s.x = cx + Math.cos(a) * rr; s.y = cy + Math.sin(a) * rr;
        });
        const kanten = [];
        liste.forEach((s, j) => {
          if (!j) return;
          const nah = liste.slice(0, j).map((t) => [Math.hypot(t.x - s.x, t.y - s.y), t]).sort((a, b) => a[0] - b[0]);
          kanten.push([nah[0][1], s]);
          if (j > 2 && j % 3 === 0 && nah[1]) kanten.push([nah[1][1], s]);
        });
        haufen.push({ name: n, sterne: liste, kanten, cx, cy, r, winkel });
      });
    }

    // ---------------------------------------------------------------- Zustand: gefiltert, gedimmt
    const woerter = () => suche.toLowerCase().split(/\s+/).filter((w) => w.length >= 2);
    function filterAlpha(s) {                  // nur Zeitleiste und Suche machen einen Stern unantastbar, der Fokus nur dunkler
      let a = 1;
      if (seitTage != null && s.tage > seitTage) a *= 0.12;
      const w = woerter();
      if (w.length && !w.some((x) => s.text.toLowerCase().includes(x))) a *= 0.15;
      return a;
    }
    function sichtbarAlpha(s) {
      let a = filterAlpha(s);
      if (ausgewaehlt && s.thema !== ausgewaehlt.thema) a *= 0.28;
      else if (fokus && s.thema !== fokus) a *= 0.2;
      return a;
    }
    const treffer = (s) => { const w = woerter(); return w.length && w.some((x) => s.text.toLowerCase().includes(x)); };

    // ---------------------------------------------------------------- Zeichnen
    const sprites = {};
    function sprite(farbe) {
      if (sprites[farbe]) return sprites[farbe];
      const c = document.createElement("canvas"); c.width = c.height = 64; const x = c.getContext("2d");
      const v = x.createRadialGradient(32, 32, 0, 32, 32, 32);
      v.addColorStop(0, farbe + "ff"); v.addColorStop(0.18, farbe + "aa"); v.addColorStop(0.5, farbe + "28"); v.addColorStop(1, farbe + "00");
      x.fillStyle = v; x.fillRect(0, 0, 64, 64);
      return (sprites[farbe] = c);
    }
    const maß = () => Math.min(breite, hoehe) * 0.46;
    const zuBild = (px, py) => [breite / 2 + (px - ansicht.x) * maß() * ansicht.z, hoehe / 2 + (py - ansicht.y) * maß() * ansicht.z];
    function zeichnen(t) {
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, breite, hoehe);
      const m = maß() * ansicht.z, [kx, ky] = zuBild(0, 0), ruhig = still();
      // Kern: weicher Schein und der Ring wie im Gespraechs-Reiter
      const rk = Math.min(m * 0.2, Math.min(breite, hoehe) * 0.2);       // beim Hineinzoomen waechst der Kern nicht ins Bild
      const s0 = g.createRadialGradient(kx, ky, 0, kx, ky, rk);
      s0.addColorStop(0, "rgba(255,255,255,.95)"); s0.addColorStop(0.25, "rgba(" + AKZ + ",.5)"); s0.addColorStop(1, "rgba(" + AKZ + ",0)");
      g.fillStyle = s0; g.beginPath(); g.arc(kx, ky, rk, 0, 7); g.fill();
      g.strokeStyle = "rgba(" + RGB + ",.22)"; g.lineWidth = 1; g.beginPath(); g.arc(kx, ky, m * 1.06, 0, 7); g.stroke();
      // Linien je Sternbild und Bereich in einem Strich (wenige Zeichenaufrufe)
      haufen.forEach((h) => {
        ["haus", "privat"].forEach((b) => {
          const a = h.kanten.filter((k) => k[0].bereich === b && k[1].bereich === b);
          if (!a.length) return;
          const dim = Math.min(...a.map((k) => Math.min(sichtbarAlpha(k[0]), sichtbarAlpha(k[1]))));
          g.strokeStyle = F[b] + Math.round(Math.max(0.05, 0.34 * dim) * 255).toString(16).padStart(2, "0");
          g.lineWidth = ausgewaehlt && ausgewaehlt.thema === h.name ? 1.4 : 1; g.beginPath();
          a.forEach((k) => { const p = zuBild(k[0].x, k[0].y), q = zuBild(k[1].x, k[1].y); g.moveTo(p[0], p[1]); g.lineTo(q[0], q[1]); });
          g.stroke();
        });
        // gemischte Kanten (Haus und Privates in einem Sternbild) gedaempft in Grau
        const mix = h.kanten.filter((k) => k[0].bereich !== k[1].bereich);
        if (mix.length) {
          g.strokeStyle = "rgba(" + RGB + ",.18)"; g.lineWidth = 1; g.beginPath();
          mix.forEach((k) => { const p = zuBild(k[0].x, k[0].y), q = zuBild(k[1].x, k[1].y); g.moveTo(p[0], p[1]); g.lineTo(q[0], q[1]); });
          g.stroke();
        }
      });
      // Sterne
      sterne.forEach((s) => {
        const a = sichtbarAlpha(s), [px, py] = zuBild(s.x, s.y), farbe = F[s.bereich];
        const flimmer = 1;
        const r = (1.5 + 2.4 * s.hell) * (0.8 + 0.2 * Math.min(ansicht.z, 2)) * flimmer;
        g.globalAlpha = Math.min(1, (0.3 + 0.7 * s.hell) * a * flimmer);
        const sp = sprite(farbe), gr = r * 5.5;
        g.drawImage(sp, px - gr, py - gr, gr * 2, gr * 2);
        g.globalAlpha = Math.min(1, (0.55 + 0.45 * s.hell) * a);
        g.fillStyle = s.hell > 0.7 ? "#ffffff" : farbe; g.beginPath(); g.arc(px, py, r, 0, 7); g.fill();
        if (treffer(s) || s === ausgewaehlt) {
          g.globalAlpha = 1; g.strokeStyle = s === ausgewaehlt ? "#ffffff" : farbe; g.lineWidth = 1.5;
          g.beginPath(); g.arc(px, py, r + 5 + (ruhig ? 0 : 1.5 * Math.sin(t / 500)), 0, 7); g.stroke();
        }
      });
      g.globalAlpha = 1;
      // Namen der Sternbilder
      g.font = "600 " + (breite < 480 ? 10 : 11) + "px 'IBM Plex Sans Condensed', sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
      haufen.forEach((h) => {
        const a = ausgewaehlt ? (ausgewaehlt.thema === h.name ? 1 : 0.25) : fokus ? (fokus === h.name ? 1 : 0.25) : 0.78;
        const text = h.name.toUpperCase(), tb = g.measureText(text).width;
        // Name unter dem untersten Stern des Sternbilds, mittig zur Breite der Sterne, ganz im Bild
        let x0 = 1e9, x1 = -1e9, y1 = -1e9;
        h.sterne.forEach((s) => { const p = zuBild(s.x, s.y); x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); });
        const rx = (x0 + x1) / 2, ry = y1 + 20;
        if (ansicht.z > 1.15 && (rx - tb / 2 < 0 || rx + tb / 2 > breite || ry > hoehe - 6 || ry < 8 || a < 0.3)) return;   // herangezoomt: nur, was ganz im Bild liegt
        const px = Math.max(tb / 2 + 6, Math.min(breite - tb / 2 - 6, rx)), py = Math.min(hoehe - 10, ry);
        g.lineWidth = 3; g.strokeStyle = "rgba(" + BG + "," + (0.85 * a) + ")"; g.lineJoin = "round"; g.strokeText(text, px, py);   // Rand gegen Linien und Sterne dahinter
        g.fillStyle = "rgba(" + DIM + "," + a + ")"; g.fillText(text, px, py);
      });
    }

    // ---------------------------------------------------------------- Schleife (Flimmern 10 Bilder/s, Bewegung 30, Pause wenn verborgen)
    let schmutzig = true, schleife = 0, letzte = 0;
    function sichtbar() { return !document.hidden && wurzel.offsetParent !== null && breite > 0; }
    function takt(t) {
      schleife = 0;
      if (!sichtbar()) { schleife = setTimeout(() => (schleife = requestAnimationFrame(takt)), 600); return; }
      const bewegt = Math.abs(ansicht.zx - ansicht.x) + Math.abs(ansicht.zy - ansicht.y) + Math.abs(ansicht.zz - ansicht.z) > 0.001;
      if (bewegt) { const k = 0.2; ansicht.x += (ansicht.zx - ansicht.x) * k; ansicht.y += (ansicht.zy - ansicht.y) * k; ansicht.z += (ansicht.zz - ansicht.z) * k; schmutzig = true; }
      const wartezeit = still() ? 200 : 100;
      if ((schmutzig || !still()) && t - letzte >= (bewegt ? 33 : wartezeit)) { letzte = t; schmutzig = false; zeichnen(t); }
      schleife = requestAnimationFrame(takt);
    }
    function start() { if (!schleife) schleife = requestAnimationFrame(takt); schmutzig = true; }
    function groesse() {
      const b = leinwand.getBoundingClientRect(); dpr = Math.min(window.devicePixelRatio || 1, 2);
      breite = Math.round(b.width); hoehe = Math.round(b.height);
      leinwand.width = Math.max(1, Math.round(breite * dpr)); leinwand.height = Math.max(1, Math.round(hoehe * dpr)); schmutzig = true;
    }
    if (window.ResizeObserver) new ResizeObserver(groesse).observe(bild); else window.addEventListener("resize", groesse);

    // ---------------------------------------------------------------- Auswahl und Fokus
    function ziel() {
      const h = haufen.find((x) => x.name === (ausgewaehlt ? ausgewaehlt.thema : fokus));
      if (h) { ansicht.zx = h.cx; ansicht.zy = h.cy; ansicht.zz = Math.max(1.5, Math.min(3.2, 0.62 / (h.r + 0.05))); }
      else { ansicht.zx = ansicht.zy = 0; ansicht.zz = 1; }
      schmutzig = true;
    }
    function waehlen(s) { ausgewaehlt = s; bearbeiten = false; sicher = false; fokus = s ? s.thema : fokus; if (!s) fokus = null; ziel(); blattZeigen(); chipsZeichnen(); }
    function treffen(px, py) {
      let best = null, bd = Math.max(16, 7 + maß() * 0.03);
      sterne.forEach((s) => {
        if (filterAlpha(s) < 0.25) return;
        const [x, y] = zuBild(s.x, s.y), d = Math.hypot(x - px, y - py); if (d < bd) { bd = d; best = s; }
      });
      return best;
    }
    leinwand.addEventListener("click", (e) => {
      const b = leinwand.getBoundingClientRect(), s = treffen(e.clientX - b.left, e.clientY - b.top);
      if (s) waehlen(s === ausgewaehlt ? null : s); else if (ausgewaehlt || fokus) { fokus = null; waehlen(null); }
    });

    // ---------------------------------------------------------------- Bedienelemente
    function chipsZeichnen() {
      chips.textContent = "";
      ((daten && daten.themen) || []).forEach((t) => {
        const b = el("button", "sb-chip" + (fokus === t.name ? " an" : ""), t.name); b.type = "button";
        b.append(el("small", null, String(t.anzahl)));
        b.addEventListener("click", () => { ausgewaehlt = null; blatt.hidden = true; fokus = fokus === t.name ? null : t.name; ziel(); chipsZeichnen(); });
        chips.append(b);
      });
    }
    function zeitZeichnen() {
      const max = +regler.max, v = +regler.value, alle = v >= max, n = sterne.filter((s) => alle || s.tage <= v).length;
      seitTage = alle ? null : v;
      const d = new Date(Date.now() - v * 86400000).toLocaleDateString(o.loc || "de-DE", { day: "2-digit", month: "2-digit" });
      zeitText.textContent = (alle ? tx("sb_alles") : tx("sb_seit", d)) + " · " + (n === 1 ? tx("sb_sterne1") : tx("sb_sterne", n));
      woche.classList.toggle("an", v === 7 && max > 7); schmutzig = true;
    }
    regler.addEventListener("input", zeitZeichnen);
    woche.addEventListener("click", () => { regler.value = +regler.value === 7 ? regler.max : Math.min(7, regler.max); zeitZeichnen(); });
    suchfeld.addEventListener("input", () => {
      suche = suchfeld.value; schmutzig = true;
      const w = woerter();
      const n = w.length ? sterne.filter(treffer).length : 0;
      hinweis.textContent = w.length ? tx("sb_treffer", n) : "";
      zahl.textContent = w.length ? tx("sb_treffer", n) : zahlText;           // oben rechts, auch ohne Scrollen sichtbar
    });

    function zeile(k, v) { const z = el("div", "sb-z"); z.append(el("span", null, k), el("b", null, v)); return z; }
    function vorTagen(t) { return t < 1 ? tx("sb_heute") : t < 2 ? tx("sb_gestern") : tx("sb_vor_tagen", t); }
    function blattZeigen() {
      blatt.textContent = "";
      const s = ausgewaehlt; blatt.hidden = !s;
      if (!s) return;
      const zu = el("button", "sb-zu", "×"); zu.type = "button"; zu.setAttribute("aria-label", tx("sb_schliessen")); zu.addEventListener("click", () => waehlen(null));
      const farbe = el("i", s.bereich); const kopfz = el("div", "sb-blatt-kopf"); kopfz.append(farbe, el("span", null, s.thema), zu);
      blatt.append(kopfz);
      if (bearbeiten) {
        const f = el("textarea", "sb-feld"); f.value = s.text; f.maxLength = 500; f.rows = 4; f.setAttribute("aria-label", tx("sb_aendern"));
        const knoepfe = el("div", "sb-knoepfe"), ok = el("button", "sb-knopf an", tx("sb_speichern")), ab = el("button", "sb-knopf", tx("sb_abbrechen"));
        ok.type = ab.type = "button";
        ok.addEventListener("click", () => senden({ aktion: "aendern", id: s.id, text: f.value }));
        ab.addEventListener("click", () => { bearbeiten = false; blattZeigen(); });
        knoepfe.append(ok, ab); blatt.append(f, knoepfe); setTimeout(() => f.focus(), 30);
      } else {
        blatt.append(el("p", "sb-text", s.text));
        blatt.append(zeile(tx("sb_datum"), s.datum + " · " + vorTagen(s.tage)),
          zeile(tx("sb_quelle"), tx("sb_q_" + s.quelle) !== "sb_q_" + s.quelle ? tx("sb_q_" + s.quelle) : (s.quelle_text || s.quelle)),
          zeile(tx("sb_bereich"), s.bereich === "haus" ? (s.von ? tx("sb_bereich_haus_von", s.von) : tx("sb_bereich_haus")) : tx("sb_bereich_privat")));
        blatt.append(zeile(tx("sb_gebraucht"), s.nutzung > 0 ? tx("sb_gebraucht_wert", vorTagen(s.tage_genutzt == null ? s.tage : s.tage_genutzt), s.nutzung) : tx("sb_nie")));
        (s.frueher || []).slice(-2).forEach((f) => blatt.append(zeile(tx("sb_frueher") + " · " + f.datum, f.text)));
        if (sicher) {
          const k = el("div", "sb-knoepfe sb-sicher"); k.append(el("span", null, s.bereich === "haus" ? tx("sb_sicher_haus") : tx("sb_sicher")));
          const ja = el("button", "sb-knopf warn", tx("sb_ja")), nein = el("button", "sb-knopf", tx("sb_nein")); ja.type = nein.type = "button";
          ja.addEventListener("click", () => senden({ aktion: "vergessen", id: s.id })); nein.addEventListener("click", () => { sicher = false; blattZeigen(); });
          k.append(ja, nein); blatt.append(k);
        } else if (!s.aendern && !s.loeschen && s.bereich === "haus") {
          blatt.append(el("p", "sb-nur", s.von ? tx(s.von_haupt ? "sb_nur_urheber_haupt" : "sb_nur_urheber", s.von) : tx("sb_nur_haupt")));      // sehen ja, aendern nein
        } else if (s.aendern || s.loeschen) {
          const k = el("div", "sb-knoepfe");
          if (s.aendern) { const a = el("button", "sb-knopf", tx("sb_aendern")); a.type = "button"; a.addEventListener("click", () => { bearbeiten = true; blattZeigen(); }); k.append(a); }
          if (s.loeschen) { const v = el("button", "sb-knopf warn", tx("sb_vergessen")); v.type = "button"; v.addEventListener("click", () => { sicher = true; blattZeigen(); }); k.append(v); }
          blatt.append(k);
        }
      }
    }

    // ---------------------------------------------------------------- Daten
    function anwenden(r, ausAktion) {
      lade = false;
      if (!r || r.fehler || !Array.isArray(r.sterne)) {
        const t = (r && r.fehler) || tx("sb_fehler");
        if (daten) { hinweis.textContent = t; return; }           // schon Daten da: Sternbild bleibt, Meldung darunter
        leer.textContent = t; leer.hidden = false; return;
      }
      const alteId = ausgewaehlt && ausgewaehlt.id;
      daten = r; geladen = Date.now(); leer.hidden = r.sterne.length > 0; if (!r.sterne.length) leer.textContent = tx("sb_leer");
      layout();
      const max = Math.max(7, Math.min(365, Math.max(0, ...r.sterne.map((s) => s.tage < 9999 ? s.tage : 0))));
      const warAlle = +regler.value >= +regler.max; regler.max = max; if (warAlle || +regler.value > max) regler.value = max;
      ausgewaehlt = alteId ? sterne.find((s) => s.id === alteId) || null : null;
      if (fokus && !haufen.some((h) => h.name === fokus)) fokus = null;
      if (!ausgewaehlt) { if (alteId) fokus = null; bearbeiten = false; sicher = false; }
      else if (ausAktion && r.ok) { bearbeiten = false; sicher = false; }
      zahlText = (r.gesamt > r.sterne.length ? tx("sb_von", r.sterne.length, r.gesamt) : String(r.sterne.length));
      zahl.textContent = woerter().length ? tx("sb_treffer", sterne.filter(treffer).length) : zahlText;
      hinweis.textContent = r.meldung && ausAktion ? r.meldung : (r.gesamt > r.sterne.length ? tx("sb_mehr", r.sterne.length, r.gesamt) : "");
      ziel(); chipsZeichnen(); zeitZeichnen(); blattZeigen(); start();
    }
    function senden(a) {
      const p = o.rufen(a);
      if (p && p.then) p.then((r) => anwenden(r, true), () => anwenden(null, true));
    }
    function laden(erzwingen) {
      if (lade || (!erzwingen && geladen && Date.now() - geladen < 20000)) { start(); return; }
      lade = true; if (!daten) { leer.textContent = tx("sb_laden"); leer.hidden = false; }
      const p = o.rufen({ aktion: "liste" });
      if (p && p.then) p.then((r) => anwenden(r, false), () => anwenden(null, false));
    }
    farben(); groesse(); leer.textContent = tx("sb_laden");
    const ort = (id) => { const s = sterne.find((x) => x.id === id); if (!s) return null; const [x, y] = zuBild(s.x, s.y), b = leinwand.getBoundingClientRect(); return [b.left + x, b.top + y]; };
    return { ort, zeigen: () => { farben(); groesse(); laden(false); start(); }, ergebnis: (r) => anwenden(r, !!(r && r.meldung)), neuLaden: () => laden(true),
             daten: () => daten, texte: () => { titel.textContent = tx("sb_titel"); suchfeld.placeholder = tx("sb_suche"); } };
  }
  return { erzeuge };
})();
