/* Jarvis Foto-Grundriss (seit 30.10.2026): fotorealistisches Puppenhaus von oben. Nur Bilder und CSS, kein WebGL:
   je Etage ein Basisbild "Abend, alles aus", darueber Licht-Ebenen (Bild "an" bzw. farbiges Licht), jede auf ihr
   Raumpolygon maskiert (weiche Kante) und mit mix-blend-mode: lighten eingeblendet, sobald eine ihrer Entitaeten an ist.
   Dazu Roborock als Punkt, Temperaturen je Raum, Tippen auf einen Raum zeigt seine Geraete. Nur anzeigen.

   Nutzung:  const g = GrundrissFoto.oeffnen(element, { laden, bild: (name) => Promise<url>, schliessen, sprache, daten, wechsel });
             wechsel = {text, klick}: Chip zur anderen Ansicht (3D-Haus), seit 30.10.2026 nachts.
             g.daten(json); g.zu()
   daten = Antwort von GET /v1/grundriss mit Feld foto: {etagen: {eg: {basis, abbildung: {s, cx, cy, groesse}, ebenen: [
           {id, raum, bild, entitaeten}]}}}. Raumpolygone (Meter) aus grundriss; Bildpunkt = c + Meter * s.
   Seit 30.10.2026 auch foto.art "puppenhaus": je Etage ein fertiges Bild (leicht schraeg von oben)
   und Punkte in Bildkoordinaten: {etagen: {eg: {name, basis, raeume: [{id, name, x, y}], punkte: [{id, name, x, y,
   entitaeten, an_von?, an_ab?, immer?}]}}}, x/y = Anteil von Breite/Hoehe. Laufende Geraete leuchten warm. */
(function () {
  "use strict";
  const DE = { titel: "GRUNDRISS", stand: "Stand {0}", laedt: "Lade Grundriss …", keine: "Noch keine Bilder für den Foto-Grundriss.",
    an: "an", aus: "aus", weg: "nicht erreichbar", keine_geraete: "Keine Geräte in diesem Raum.", licht: "Licht {0}",
    sauger: "Saugroboter", schliessen: "Schließen", nur: "nur Anzeige · doppeltippen zum Vergrößern" };
  const EN = { titel: "FLOOR PLAN", stand: "As of {0}", laedt: "Loading floor plan …", keine: "No images for the photo floor plan yet.",
    an: "on", aus: "off", weg: "unavailable", keine_geraete: "No devices in this room.", licht: "Light {0}",
    sauger: "Robot vacuum", schliessen: "Close", nur: "view only · double-tap to zoom" };
  const ZUST = { on: ["an", "on"], off: ["aus", "off"], playing: ["spielt", "playing"], idle: ["bereit", "idle"],
    standby: ["Standby", "standby"], docked: ["in der Station", "docked"], cleaning: ["saugt", "cleaning"],
    heat: ["heizt", "heating"], auto: ["Automatik", "auto"], unavailable: ["nicht erreichbar", "unavailable"],
    inactive: ["inaktiv", "inactive"], ready: ["bereit", "ready"], run: ["läuft", "running"], finished: ["fertig", "finished"] };
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // Gleiche Regel wie die 3D-Ansicht: was zaehlt als "an"
  function istAn(eid, z) {
    if (!z) return false;
    const s = String(z.s || "").toLowerCase(), d = eid.split(".")[0];
    if (d === "media_player") return s === "playing" || s === "on" || s === "idle";
    if (d === "sensor") { const n = parseFloat(s); if (!isNaN(n) && /W$/.test(z.e || "")) return n > 3; return /^(run|läuft|laeuft)$/.test(s); }
    if (d === "climate") return s !== "off" && s !== "unavailable";
    return s === "on" || s === "playing" || s === "cleaning";
  }

  function maske(poly, ab, weich) {          // SVG-Maske des Raums, weiche Kante per Unschaerfe
    const G = ab.groesse, pts = poly.map((p) => (ab.cx + p[0] * ab.s).toFixed(1) + "," + (ab.cy + p[1] * ab.s).toFixed(1)).join(" ");
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${G} ${G}"><filter id="w" x="-10%" y="-10%" width="120%" height="120%">` +
      `<feGaussianBlur stdDeviation="${weich}"/></filter><polygon points="${pts}" fill="#fff" filter="url(#w)"/></svg>`;
    return 'url("data:image/svg+xml;utf8,' + encodeURIComponent(svg) + '")';
  }

  function oeffnen(el, opt) {
    opt = opt || {};
    const T = opt.sprache === "en" ? EN : DE, LOC = opt.sprache === "en" ? "en-GB" : "de-DE", SI = opt.sprache === "en" ? 1 : 0;
    el.innerHTML = "";
    el.classList.add("grfoto");
    const stil = document.createElement("style");
    stil.textContent = `
.grfoto{position:relative;overflow:hidden;background:radial-gradient(ellipse at 50% 40%,#141a26 0%,#06080d 75%);color:#e8ecf4;
  font-family:"IBM Plex Sans",system-ui,sans-serif;user-select:none;-webkit-user-select:none}
.grfoto .kopf{position:absolute;left:0;right:0;top:0;display:flex;align-items:center;gap:8px;padding:12px 14px;z-index:5;
  background:linear-gradient(#06080dee,#06080d00);pointer-events:none}
.grfoto .kopf>*{pointer-events:auto}
.grfoto .titel{font-family:"IBM Plex Sans Condensed",sans-serif;letter-spacing:.32em;font-size:13px;color:#a9c4ff;flex:1;white-space:nowrap}
.grfoto .titel small{display:block;letter-spacing:.06em;font-size:11px;color:#9aa6bc;margin-top:3px}
.grfoto .chips{display:flex;gap:6px}
.grfoto .chip{border:1px solid rgba(169,196,255,.28);border-radius:999px;padding:5px 11px;font-size:12px;color:#9aa6bc;
  background:rgba(12,17,29,.7);cursor:pointer;letter-spacing:.06em}
.grfoto .chip.aktiv{color:#06080d;background:#a9c4ff;border-color:#a9c4ff}
.grfoto .zu{width:34px;height:34px;border-radius:50%;border:1px solid rgba(169,196,255,.28);background:rgba(12,17,29,.7);
  color:#e8ecf4;font-size:18px;line-height:30px;text-align:center;cursor:pointer}
.grfoto .buehne{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);aspect-ratio:1/1;
  width:min(100%,calc(100% - 0px));max-height:100%;}
.grfoto .buehne img{position:absolute;inset:0;width:100%;height:100%;display:block;pointer-events:none;-webkit-user-drag:none}
.grfoto .ebene{mix-blend-mode:lighten;opacity:0;transition:opacity .9s ease;-webkit-mask-size:100% 100%;mask-size:100% 100%;
  -webkit-mask-repeat:no-repeat;mask-repeat:no-repeat}
.grfoto .ebene.an{opacity:1}
.grfoto svg.oben{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.grfoto .raum{fill:transparent;stroke:transparent;cursor:pointer}
.grfoto .raum.gewaehlt{stroke:rgba(169,196,255,.75);stroke-width:3;fill:rgba(169,196,255,.06)}
.grfoto .temp{font:500 22px "IBM Plex Sans Condensed",sans-serif;fill:#e8ecf4;paint-order:stroke;stroke:rgba(6,8,13,.75);stroke-width:5px;
  pointer-events:none;letter-spacing:.02em}
.grfoto .sauger circle.kern{fill:#a9c4ff}
.grfoto .sauger circle.puls{fill:none;stroke:#a9c4ff;stroke-width:3;transform-box:fill-box;transform-origin:center;animation:grpuls 2.2s ease-out infinite}
@keyframes grpuls{0%{transform:scale(.6);opacity:.9}100%{transform:scale(2.6);opacity:0}}
.grfoto .karte{position:absolute;left:12px;right:12px;bottom:12px;max-width:420px;margin:0 auto;padding:12px 14px;border-radius:14px;z-index:6;
  background:rgba(12,17,29,.93);border:1px solid rgba(169,196,255,.22);box-shadow:0 10px 30px #000a;transform:translateY(160%);transition:transform .25s}
.grfoto .karte.da{transform:none}
.grfoto .karte b{font-size:15px;font-weight:600}
.grfoto .karte ul{list-style:none;margin:8px 0 0;padding:0;font-size:13px}
.grfoto .karte li{display:flex;justify-content:space-between;gap:12px;padding:3px 0;border-top:1px solid rgba(169,196,255,.08)}
.grfoto .karte li span:last-child{color:#9aa6bc;white-space:nowrap}
.grfoto .karte li.an span:last-child{color:#f1d9a6}
.grfoto .karte .hinweis{font-size:10px;color:#6f7b92;margin-top:8px}
.grfoto .meldung{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#9aa6bc;font-size:14px;pointer-events:none;text-align:center;padding:24px}
.grfoto .buehne.ph{aspect-ratio:auto;overflow:hidden}
.grfoto .ph-welt{position:absolute;inset:0;transform-origin:0 0;transition:transform .35s ease}
.grfoto .ph-welt.zieht{transition:none}
.grfoto .ph-ebene{position:absolute;inset:0;cursor:pointer}
.grfoto .ph-punkt,.grfoto .ph-sauger{scale:calc(1 / var(--z,1))}
.grfoto .ph-glut{position:absolute;width:24%;aspect-ratio:1/1;transform:translate(-50%,-50%);border-radius:50%;pointer-events:none;
  background:radial-gradient(circle,rgba(255,200,130,.34) 0%,rgba(255,176,96,.14) 38%,rgba(255,176,96,0) 70%);mix-blend-mode:screen;
  opacity:0;transition:opacity 1.2s ease}
.grfoto .ph-glut.an{opacity:1}
.grfoto .ph-punkt{position:absolute;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;box-sizing:border-box;
  border:2px solid rgba(169,196,255,.6);background:rgba(6,8,13,.6);transition:border-color .6s,opacity .6s}
.grfoto .ph-punkt i{position:absolute;inset:5px;border-radius:50%;background:#9aa6bc;transition:background .6s,box-shadow .6s}
.grfoto .ph-punkt.an{border-color:#f1d9a6}
.grfoto .ph-punkt.an i{background:#ffd79a;box-shadow:0 0 12px #ffcf87}
.grfoto .ph-punkt.an::after{content:"";position:absolute;inset:-6px;border-radius:50%;border:2px solid #ffcf87;animation:grpuls 2.4s ease-out infinite}
.grfoto .ph-punkt.weg{opacity:.5;border-style:dashed}
.grfoto .ph-punkt.gewaehlt{border-color:#a9c4ff;box-shadow:0 0 0 3px rgba(169,196,255,.35)}
.grfoto .ph-sauger{position:absolute;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;background:#a9c4ff;box-shadow:0 0 14px #a9c4ff;
  transition:left 1.5s ease,top 1.5s ease}
.grfoto .ph-sauger::after{content:"";position:absolute;inset:-8px;border-radius:50%;border:2px solid #a9c4ff;animation:grpuls 2.2s ease-out infinite}`;
    el.appendChild(stil);
    const kopf = document.createElement("div"); kopf.className = "kopf";
    kopf.innerHTML = `<div class="titel">${T.titel}<small></small></div><div class="chips"></div>` +
      (opt.schliessen ? `<div class="zu" role="button" aria-label="${T.schliessen}">×</div>` : "");
    el.appendChild(kopf);
    if (opt.schliessen) kopf.querySelector(".zu").addEventListener("click", () => opt.schliessen());
    const buehne = document.createElement("div"); buehne.className = "buehne"; el.appendChild(buehne);
    const karte = document.createElement("div"); karte.className = "karte"; el.appendChild(karte);
    const meldung = document.createElement("div"); meldung.className = "meldung"; meldung.textContent = T.laedt; el.appendChild(meldung);

    let D = null, etage = null, aus = false, uhr = null, gewaehlt = null, aufgebaut = "", seite = 4 / 3;
    const PH = () => !!(D && D.foto && D.foto.art === "puppenhaus");
    const bilder = {};            // name -> url (einmal geholt)
    async function bildUrl(name) {
      if (bilder[name]) return bilder[name];
      const u = opt.bild ? await opt.bild(name) : name;
      if (u) bilder[name] = u;
      return u;
    }
    function groesse() {          // quadratische Buehne (Puppenhaus: Seitenverhaeltnis des Bilds), so gross wie moeglich
      const w = el.clientWidth, h = el.clientHeight - 56;
      if (PH()) {
        const b = Math.max(100, Math.min(w, h * seite));
        buehne.style.width = b + "px"; buehne.style.height = (b / seite) + "px";
      } else {
        const g = Math.max(100, Math.min(w, h));
        buehne.style.width = buehne.style.height = g + "px";
      }
      buehne.style.top = (56 + h / 2) + "px";
    }
    // ---------- Puppenhaus (seit 30.10.2026)
    function phAn(p, Z) {
      if (p.immer) return true;
      const e = p.an_von || p.entitaeten[0], z = Z[e];
      if (!z) return false;
      if (p.an_ab != null) { const n = parseFloat(z.s); return !isNaN(n) && n > p.an_ab; }
      return istAn(e, z);
    }
    function phWeg(p, Z) {
      if (p.immer) return false;
      const z = Z[p.an_von || p.entitaeten[0]];
      return !z || String(z.s).toLowerCase() === "unavailable";
    }
    function phRaumVon(F, p) {    // naechste Raummitte (Bild ist breiter als hoch: y etwas schwaecher gewichtet)
      let best = null, bd = 9;
      for (const r of F.raeume || []) { const d = Math.hypot(r.x - p.x, (r.y - p.y) * 0.75); if (d < bd) { bd = d; best = r; } }
      return best;
    }
    function phAufbauen() {
      const F = D.foto.etagen[etage];
      aufgebaut = etage + JSON.stringify(F);
      buehne.innerHTML = ""; buehne.classList.add("ph");
      const welt = document.createElement("div"); welt.className = "ph-welt"; buehne.appendChild(welt);
      const basis = document.createElement("img"); basis.alt = ""; welt.appendChild(basis);
      basis.onload = () => {
        if (basis.naturalWidth && basis.naturalHeight) { seite = basis.naturalWidth / basis.naturalHeight; groesse(); }
        try {                     // Hintergrund = Eckfarbe des Bilds, damit kein Kasten sichtbar wird
          const c = document.createElement("canvas"); c.width = c.height = 1;
          const x = c.getContext("2d"); x.drawImage(basis, 0, 0, 4, 4, 0, 0, 1, 1);
          const d = x.getImageData(0, 0, 1, 1).data; el.style.background = `rgb(${d[0]},${d[1]},${d[2]})`;
        } catch (e) { /* fremde Herkunft: Standardhintergrund */ }
      };
      bildUrl(F.basis).then((u) => { basis.src = u || ""; });
      const ebene = document.createElement("div"); ebene.className = "ph-ebene"; welt.appendChild(ebene);
      // Doppeltippen vergroessert (x2) um die Stelle, dann mit dem Finger verschieben; nochmal doppeltippen = ganz
      let z = 1, tx = 0, ty = 0, zug = null, gezogen = false;
      const setzen = () => {
        const W = buehne.clientWidth, H = buehne.clientHeight;
        tx = Math.min(0, Math.max(W - W * z, tx)); ty = Math.min(0, Math.max(H - H * z, ty));
        welt.style.transform = `translate(${tx}px,${ty}px) scale(${z})`; welt.style.setProperty("--z", z);
        buehne.style.touchAction = z > 1 ? "none" : "";
      };
      buehne.addEventListener("dblclick", (ev) => {
        const r = buehne.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
        if (z === 1) { z = 2; tx = x - x * z; ty = y - y * z; } else { z = 1; tx = ty = 0; }
        setzen(); ev.preventDefault();
      });
      buehne.addEventListener("pointerdown", (ev) => { if (z > 1) { zug = { x: ev.clientX, y: ev.clientY, tx, ty }; gezogen = false; welt.classList.add("zieht"); } });
      buehne.addEventListener("pointermove", (ev) => {
        if (!zug) return;
        const dx = ev.clientX - zug.x, dy = ev.clientY - zug.y;
        if (Math.abs(dx) + Math.abs(dy) > 6) gezogen = true;
        tx = zug.tx + dx; ty = zug.ty + dy; setzen();
      });
      const loslassen = () => { zug = null; welt.classList.remove("zieht"); };
      buehne.addEventListener("pointerup", loslassen); buehne.addEventListener("pointercancel", loslassen);
      const pos = (n, p) => { n.style.left = (p.x * 100) + "%"; n.style.top = (p.y * 100) + "%"; n.dataset.id = p.id; };
      for (const p of F.punkte || []) { const g = document.createElement("div"); g.className = "ph-glut"; pos(g, p); ebene.appendChild(g); }
      for (const p of F.punkte || []) {
        const m = document.createElement("div"); m.className = "ph-punkt"; pos(m, p); m.title = p.name;
        m.setAttribute("role", "button"); m.setAttribute("aria-label", p.name); m.innerHTML = "<i></i>"; ebene.appendChild(m);
      }
      const s = document.createElement("div"); s.className = "ph-sauger"; s.hidden = true; ebene.appendChild(s);
      ebene.addEventListener("click", (ev) => {
        if (gezogen) { gezogen = false; return; }         // Verschieben ist kein Tippen
        const m = ev.target.closest && ev.target.closest(".ph-punkt");
        if (m) { gewaehlt = gewaehlt === "p:" + m.dataset.id ? null : "p:" + m.dataset.id; karteZeigen(); return; }
        const r = ebene.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height;
        const raum = phRaumVon(F, { x, y });
        gewaehlt = raum && gewaehlt !== "r:" + raum.id ? "r:" + raum.id : null;
        karteZeigen();
      });
      groesse();
      zustaende();
    }
    function phZustaende() {
      const F = D.foto.etagen[etage], Z = D.zustaende || {};
      for (const p of F.punkte || []) {
        const an = phAn(p, Z), weg = phWeg(p, Z);
        buehne.querySelectorAll('[data-id="' + CSS.escape(p.id) + '"]').forEach((n) => {
          n.classList.toggle("an", an); n.classList.toggle("weg", weg && n.classList.contains("ph-punkt"));
          n.classList.toggle("gewaehlt", gewaehlt === "p:" + p.id && n.classList.contains("ph-punkt"));
        });
      }
      const s = buehne.querySelector(".ph-sauger"), S = D.sauger;
      const r = S && S.aktiv && S.etage === etage && (F.raeume || []).find((x) => x.id === S.raum);
      if (s) { s.hidden = !r; if (r) { s.style.left = (r.x * 100) + "%"; s.style.top = (r.y * 100) + "%"; } }
    }
    function phKarte() {
      const F = D.foto.etagen[etage], Z = D.zustaende || {};
      const zeile = (p) => {
        const werte = p.entitaeten.map((e) => zustandText(e, Z[e])).filter((t, i, a) => a.indexOf(t) === i).join(" · ");
        return `<li class="${phAn(p, Z) ? "an" : ""}"><span>${esc(p.name)}</span><span>${esc(p.immer && !werte ? T.an : werte)}</span></li>`;
      };
      let titel = "", liste = [];
      if (gewaehlt.startsWith("p:")) {
        const p = (F.punkte || []).find((x) => x.id === gewaehlt.slice(2)); if (!p) { gewaehlt = null; karte.classList.remove("da"); return; }
        const r = phRaumVon(F, p); titel = p.name + (r ? " · " + r.name : ""); liste = [p];
      } else {
        const r = (F.raeume || []).find((x) => x.id === gewaehlt.slice(2)); if (!r) { gewaehlt = null; karte.classList.remove("da"); return; }
        titel = r.name; liste = (F.punkte || []).filter((p) => { const q = phRaumVon(F, p); return q && q.id === r.id; });
      }
      karte.innerHTML = `<b>${esc(titel)}</b><ul>${liste.length ? liste.map(zeile).join("") : `<li><span>${T.keine_geraete}</span><span></span></li>`}</ul><div class="hinweis">${T.nur}</div>`;
      karte.classList.add("da");
      phZustaende();
    }
    function etagenListe() { return D && D.foto ? Object.keys(D.foto.etagen || {}) : []; }

    async function aufbauen() {
      if (PH()) return phAufbauen();
      buehne.classList.remove("ph");
      const F = D.foto.etagen[etage], E = (D.grundriss.etagen || []).find((e) => e.id === etage);
      if (!F || !E) return;
      aufgebaut = etage + JSON.stringify(F);
      buehne.innerHTML = "";
      const basis = document.createElement("img"); basis.alt = ""; buehne.appendChild(basis);
      basis.onload = () => {                // Hintergrund = Eckfarbe des Bilds, damit kein Kasten sichtbar wird
        try {
          const c = document.createElement("canvas"); c.width = c.height = 4;
          const x = c.getContext("2d"); x.drawImage(basis, 0, 0, 8, 8, 0, 0, 4, 4);
          const d = x.getImageData(0, 0, 1, 1).data;
          el.style.background = `rgb(${d[0]},${d[1]},${d[2]})`;
        } catch (e) { /* fremde Herkunft: Standardhintergrund */ }
      };
      basis.src = await bildUrl(F.basis) || "";
      const ab = F.abbildung, raumVon = {};
      for (const r of E.raeume) raumVon[r.id] = r;
      for (const eb of F.ebenen || []) {
        const r = raumVon[eb.raum];
        if (!r) continue;
        const im = document.createElement("img"); im.alt = ""; im.className = "ebene"; im.dataset.id = eb.id;
        const m = maske(r.polygon, ab, Math.max(4, ab.s * 0.12));
        im.style.webkitMaskImage = m; im.style.maskImage = m;
        buehne.appendChild(im);
        bildUrl(eb.bild).then((u) => { if (u) im.src = u; });
      }
      const G = ab.groesse;
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "oben"); svg.setAttribute("viewBox", `0 0 ${G} ${G}`);
      let inhalt = "";
      for (const r of E.raeume) {
        const pts = r.polygon.map((p) => (ab.cx + p[0] * ab.s).toFixed(1) + "," + (ab.cy + p[1] * ab.s).toFixed(1)).join(" ");
        inhalt += `<polygon class="raum" data-raum="${esc(r.id)}" points="${pts}"/>`;
        inhalt += `<text class="temp" data-temp="${esc(r.id)}" x="${(ab.cx + r.mitte[0] * ab.s).toFixed(1)}" y="${(ab.cy + r.mitte[1] * ab.s + 8).toFixed(1)}" text-anchor="middle"></text>`;
      }
      inhalt += `<g class="sauger" style="display:none"><circle class="puls" r="14"/><circle class="kern" r="9"/></g>`;
      svg.innerHTML = inhalt;
      svg.addEventListener("click", (ev) => {
        const p = ev.target.closest && ev.target.closest(".raum");
        if (!p) { karte.classList.remove("da"); gewaehlt = null; markieren(); return; }
        gewaehlt = gewaehlt === p.dataset.raum ? null : p.dataset.raum;
        markieren(); karteZeigen();
      });
      buehne.appendChild(svg);
      zustaende();
    }
    function markieren() { buehne.querySelectorAll(".raum").forEach((p) => p.classList.toggle("gewaehlt", p.dataset.raum === gewaehlt)); }
    function zustandText(eid, z) {
      if (!z) return T.weg;
      const s = String(z.s || ""), n = parseFloat(s);
      if (!isNaN(n) && isFinite(s)) return n.toLocaleString(LOC, { maximumFractionDigits: 1 }) + (z.e ? " " + z.e : "");
      const k = s.toLowerCase().replace(/^.*\./, "");
      return (ZUST[k] || [s, s])[SI];
    }
    function geraeteIm(raum) {
      return Object.entries((D.platzierung || {}).eintraege || {}).filter(([, p]) => p.etage === etage && p.raum === raum);
    }
    function karteZeigen() {
      if (!gewaehlt) { karte.classList.remove("da"); if (PH()) phZustaende(); return; }
      if (PH()) return phKarte();
      const E = D.grundriss.etagen.find((e) => e.id === etage), r = E.raeume.find((x) => x.id === gewaehlt), Z = D.zustaende || {};
      const liste = geraeteIm(gewaehlt).map(([eid, p]) => {
        const w = (p.werte || []).map((x) => Z[x]).find((x) => x && !isNaN(parseFloat(x.s)));
        return `<li class="${istAn(eid, Z[eid]) ? "an" : ""}"><span>${esc(p.name)}</span><span>${esc(zustandText(eid, Z[eid]) + (w ? " · " + zustandText("", w) : ""))}</span></li>`;
      }).join("");
      karte.innerHTML = `<b>${esc(r ? r.name : "")}</b>${liste ? "<ul>" + liste + "</ul>" : `<ul><li><span>${T.keine_geraete}</span><span></span></li></ul>`}<div class="hinweis">${T.nur}</div>`;
      karte.classList.add("da");
    }
    function raumTemperatur(raum) {
      const Z = D.zustaende || {};
      for (const [eid] of geraeteIm(raum)) {
        const z = Z[eid];
        if (z && z.a && z.a.current_temperature != null && eid.startsWith("climate.")) return z.a.current_temperature;
      }
      for (const [eid, p] of geraeteIm(raum)) {
        for (const w of [eid].concat(p.werte || [])) {
          const z = Z[w];
          if (z && z.e === "°C" && !/aussen|outdoor|garraum|backofen/i.test(w)) return parseFloat(z.s);
        }
      }
      return null;
    }
    function zustaende() {
      if (!D || !etage || !D.foto.etagen[etage]) return;
      if (PH()) {
        phZustaende();
        const st = new Date((D.zustand_stand || D.stand || Date.now() / 1000) * 1000);
        kopf.querySelector(".titel small").textContent = (D.foto.etagen[etage].name ? D.foto.etagen[etage].name + " · " : "") +
          T.stand.replace("{0}", st.toLocaleTimeString(LOC, { hour: "2-digit", minute: "2-digit" }));
        if (gewaehlt) phKarte();
        return;
      }
      const F = D.foto.etagen[etage], Z = D.zustaende || {}, ab = F.abbildung;
      for (const eb of F.ebenen || []) {
        const an = (eb.entitaeten || []).some((e) => istAn(e, Z[e]));
        const im = buehne.querySelector('.ebene[data-id="' + CSS.escape(eb.id) + '"]');
        if (im) im.classList.toggle("an", an);
      }
      buehne.querySelectorAll(".temp").forEach((t) => {
        const v = raumTemperatur(t.dataset.temp);
        t.textContent = v == null || isNaN(v) ? "" : v.toLocaleString(LOC, { maximumFractionDigits: 1 }) + "°";
      });
      const sg = buehne.querySelector(".sauger");
      if (sg) {
        const E = D.grundriss.etagen.find((e) => e.id === etage);
        const r = D.sauger && D.sauger.etage === etage && E.raeume.find((x) => x.id === D.sauger.raum);
        sg.style.display = r ? "" : "none";
        if (r) sg.setAttribute("transform", `translate(${(ab.cx + (r.mitte[0] + 0.5) * ab.s).toFixed(1)} ${(ab.cy + (r.mitte[1] + 0.6) * ab.s).toFixed(1)})`);
      }
      const st = new Date((D.zustand_stand || D.stand || Date.now() / 1000) * 1000);
      kopf.querySelector(".titel small").textContent = T.stand.replace("{0}", st.toLocaleTimeString(LOC, { hour: "2-digit", minute: "2-digit" }));
      if (gewaehlt) karteZeigen();
    }
    function chips() {
      const c = kopf.querySelector(".chips"); c.innerHTML = "";
      for (const id of etagenListe()) {
        const s = document.createElement("span"); s.className = "chip" + (id === etage ? " aktiv" : ""); s.textContent = id.toUpperCase();
        s.addEventListener("click", () => waehlen(id)); c.appendChild(s);
      }
      if (opt.wechsel) {           // zur anderen Ansicht (3D <-> Bild), nur wenn es beide gibt
        const w = document.createElement("span"); w.className = "chip"; w.textContent = opt.wechsel.text;
        w.addEventListener("click", () => opt.wechsel.klick()); c.appendChild(w);
      }
    }
    function waehlen(id) { etage = id; gewaehlt = null; karte.classList.remove("da"); chips(); aufbauen(); }
    function daten(d) {
      if (aus || !d) return;
      if (!d.ok || !d.foto || !Object.keys(d.foto.etagen || {}).length) { meldung.textContent = (d && d.fehler) || T.keine; D = d; return; }
      meldung.textContent = "";
      D = d;
      const liste = etagenListe();
      if (!etage || !liste.includes(etage)) { etage = liste.includes("eg") ? "eg" : liste[0]; chips(); }
      if (aufgebaut !== etage + JSON.stringify(D.foto.etagen[etage])) aufbauen(); else zustaende();
    }
    async function holen() { if (!opt.laden) return; try { daten(await opt.laden()); } catch (e) { if (!D) meldung.textContent = String(e.message || e); } }
    const ro = window.ResizeObserver ? new ResizeObserver(groesse) : null;
    if (ro) ro.observe(el); else addEventListener("resize", groesse);
    groesse();
    if (opt.daten) daten(opt.daten); else holen();
    if (opt.laden) uhr = setInterval(() => { if (!document.hidden) holen(); }, (opt.alle_s || 10) * 1000);
    return {
      daten, waehlen,
      raum: (id) => { gewaehlt = id; markieren(); karteZeigen(); },
      info: () => ({ etage, puppenhaus: PH(), punkte: [...buehne.querySelectorAll(".ph-punkt")].map((x) => x.dataset.id +
          (x.classList.contains("an") ? ":an" : x.classList.contains("weg") ? ":weg" : ":aus")),
        karte: karte.classList.contains("da") ? karte.textContent : "",
        ebenen: [...buehne.querySelectorAll(".ebene")].map((x) => x.dataset.id + (x.classList.contains("an") ? ":an" : ":aus")),
        temperaturen: [...buehne.querySelectorAll(".temp")].map((t) => t.textContent).filter(Boolean),
        sauger: !!(buehne.querySelector(".sauger") && buehne.querySelector(".sauger").style.display !== "none") }),
      zu() { aus = true; clearInterval(uhr); if (ro) ro.disconnect(); el.innerHTML = ""; el.classList.remove("grfoto");
        if (opt.freigeben) for (const u of Object.values(bilder)) opt.freigeben(u); },
    };
  }
  window.GrundrissFoto = { oeffnen, version: "1.0", _istAn: istAn };
})();
