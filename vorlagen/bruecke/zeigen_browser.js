// Zeig's mir (S6, seit 0.7) im echten Browser (Headless-Chrome). Aufruf aus tests/test_sh_zeigen.py (Browserteil,
// nur mit --browser). Der Testserver liefert die Seiten ueber zeigen.seite() mit zeigen.SEITE_KOPFZEILEN aus,
// unter /ohne-kopf/ dieselben Seiten ohne Kopfzeilen (dann wirkt nur die eingesetzte <meta>-CSP).
// Argumente: basis (http://172.17.0.1:<port>/), ausgabeordner, id der Beispielseite, id der Gegenprobe.
const puppeteer = require("puppeteer");
const [, , basis, aus, id, boese] = process.argv;
const warte = (ms) => new Promise((r) => setTimeout(r, ms));
let ok = 0, fehler = 0;
function pruef(name, bed, info) {
  if (bed) ok++; else fehler++;
  console.log((bed ? "OK     " : "FEHLER ") + name + (bed || info === undefined ? "" : " | " + JSON.stringify(info).slice(0, 300)));
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium-browser",
    args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  async function oeffnen(pfad, breite, hoehe, skala) {
    const page = await browser.newPage();
    const s = { page, skriptfehler: [], konsole: [], anfragen: [] };
    page.on("pageerror", (e) => s.skriptfehler.push(e.message));
    page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") s.konsole.push(m.text()); });
    page.on("request", (r) => s.anfragen.push(r.url()));
    const mobil = (skala || 1) > 1;
    await page.setViewport({ width: breite, height: hoehe, deviceScaleFactor: skala || 1, isMobile: mobil, hasTouch: mobil });
    s.antwort = await page.goto(basis + pfad, { waitUntil: "load", timeout: 30000 });
    await warte(700);
    return s;
  }
  const bild = (p, n) => (aus ? p.screenshot({ path: aus + "/" + n + ".png" }) : null);
  const lage = (p) => p.evaluate(() => ({
    titel: document.title, svg: !!document.querySelector("svg#szene"), origin: String(self.origin),
    breit: document.documentElement.scrollWidth, innen: window.innerWidth,
    hoch: document.documentElement.scrollHeight, innenHoch: window.innerHeight,
    schrift: parseFloat(getComputedStyle(document.body).fontSize),
    druck: document.getElementById("druckanzeige").textContent,
    lava: Number(document.getElementById("lavaspiegel").getAttribute("height")),
    kreise: document.querySelectorAll("#teilchen circle").length,
    strom: Number(document.getElementById("strom1").getAttribute("stroke-dashoffset")),
    status: document.getElementById("status").textContent,
    meta: !!document.querySelector('meta[http-equiv="Content-Security-Policy"]') }));
  const sauber = (s, wer) => {
    pruef(wer + ": keine Skriptfehler", s.skriptfehler.length === 0, s.skriptfehler);
    pruef(wer + ": keine CSP-Verstoesse in der Konsole", !s.konsole.some((t) => /Content Security Policy|Refused to/.test(t)), s.konsole);
    pruef(wer + ": nur die Seite selbst geladen", s.anfragen.length === 1, s.anfragen);
  };

  // ---------- 1 Beamer 16:9
  let s = await oeffnen("zeigen/" + id, 1280, 720);
  const kopf = s.antwort.headers();
  pruef("Beamer: HTTP 200 als text/html", s.antwort.status() === 200 && /^text\/html/.test(kopf["content-type"] || ""), [s.antwort.status(), kopf["content-type"]]);
  pruef("Beamer: CSP-Kopfzeile mit connect-src 'none' und sandbox", /connect-src 'none'/.test(kopf["content-security-policy"] || "")
    && /sandbox allow-scripts/.test(kopf["content-security-policy"] || ""), kopf["content-security-policy"]);
  let l = await lage(s.page);
  pruef("Beamer: Titel und SVG da", l.titel === "Wie funktioniert ein Vulkan?" && l.svg, l);
  pruef("Beamer: eigener leerer Ursprung (sandbox)", l.origin === "null", l.origin);
  pruef("Beamer: CSP auch als <meta> eingesetzt", l.meta, l);
  pruef("Beamer: passt in 1280x720 (keine Scrollleisten)", l.breit <= l.innen && l.hoch <= l.innenHoch, l);
  pruef("Beamer: Startzustand Druck 20 %", l.druck === "Druck: 20 %" && l.lava === 60 && l.kreise === 0, l);
  await bild(s.page, "zeigen-1-beamer-start");
  await s.page.focus("#druck");
  for (let i = 0; i < 40; i++) await s.page.keyboard.press("ArrowRight");
  await warte(200);
  l = await lage(s.page);
  pruef("Beamer: Regler per Tastatur hebt die Lava (Druck 60 %)", l.druck === "Druck: 60 %" && l.lava === 180 && /Druck steigt/.test(l.status), l);
  await bild(s.page, "zeigen-2-beamer-druck");
  await s.page.click("#los");
  await warte(900);
  l = await lage(s.page);
  pruef("Beamer: Knopf Ausbruch startet die Simulation", l.kreise > 0 && /Ausbruch/.test(l.status) && l.druck === "Druck: 100 %", l);
  await bild(s.page, "zeigen-3-beamer-ausbruch");
  await warte(1800);
  l = await lage(s.page);
  pruef("Beamer: Lava fliesst den Berg hinunter", l.strom < 100, l.strom);
  await s.page.click("#neu");
  await warte(300);
  l = await lage(s.page);
  pruef("Beamer: Zuruecksetzen", l.kreise === 0 && l.strom === 300 && l.druck === "Druck: 20 %", l);
  sauber(s, "Beamer");
  await s.page.close();

  // ---------- 2 Handy hochkant, Finger
  s = await oeffnen("zeigen/" + id, 390, 844, 2);
  l = await lage(s.page);
  pruef("Handy: keine waagrechte Scrollleiste", l.breit <= l.innen, l);
  pruef("Handy: Schrift mindestens 18 px", l.schrift >= 18, l.schrift);
  await bild(s.page, "zeigen-4-handy");
  await s.page.tap("#los");
  await warte(700);
  l = await lage(s.page);
  pruef("Handy: Antippen startet den Ausbruch", l.kreise > 0, l);
  sauber(s, "Handy");
  await s.page.close();

  // ---------- 3 zeigen/aktuell (Leinwand) zeigt dieselbe Seite
  s = await oeffnen("zeigen/aktuell", 1280, 720);
  l = await lage(s.page);
  pruef("Leinwand: zeigen/aktuell liefert die zuletzt gezeigte Seite", l.titel === "Wie funktioniert ein Vulkan?" && l.svg, l);
  sauber(s, "Leinwand");
  await s.page.close();

  // ---------- 4 Gegenprobe: eine boese Seite (am Pruefer vorbei abgelegt) kommt nicht nach aussen
  const gegen = async (pfad) => {
    const g = await oeffnen(pfad, 800, 600);
    await g.page.waitForFunction(() => document.getElementById("erg").textContent.length > 2, { timeout: 8000 });
    const e = await g.page.evaluate(() => JSON.parse(document.getElementById("erg").textContent));
    await g.page.close();
    return e;
  };
  let e = await gegen("zeigen/" + boese);
  pruef("Gegenprobe: fetch, XMLHttpRequest und Bild nach aussen gesperrt", e.fetch === "gesperrt" && e.xhr === "gesperrt" && e.bild === "gesperrt", e);
  pruef("Gegenprobe: localStorage und Cookie gesperrt (sandbox, Token der Web-App unerreichbar)", e.speicher === "gesperrt" && e.cookie === "gesperrt" && e.origin === "null", e);
  e = await gegen("ohne-kopf/zeigen/" + boese);
  pruef("Gegenprobe ohne Kopfzeile: die <meta>-CSP sperrt das Netz trotzdem", e.fetch === "gesperrt" && e.xhr === "gesperrt" && e.bild === "gesperrt", e);
  pruef("Gegenprobe ohne Kopfzeile: Speicher offen, die sandbox kommt nur per Kopfzeile", e.speicher === "offen", e);

  await browser.close();
  console.log("BROWSER " + ok + " ok, " + fehler + " Fehler");
  process.exit(fehler ? 1 : 0);
})().catch((x) => { console.log("FEHLER Browserlauf abgebrochen | " + String(x && x.stack || x).slice(0, 400)); process.exit(1); });
