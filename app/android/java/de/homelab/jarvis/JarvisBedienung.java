package de.homelab.jarvis;

import android.accessibilityservice.AccessibilityService;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Handy-Steuerung Stufe 2 (PROTOTYP, 29.10.2026, Standard aus): Bedienungshilfe, die Befehle des Bedien-Gehirns
 * ausfuehrt. Nach der Pruefung vom 29.10.2026 (H2, M1, M2, N2, N4, N8):
 * - Nur Apps der Positivliste (BedienRegeln.ERLAUBTE_APPS); SMS, Mail, Messenger, Browser, Banking, Passwort-Apps,
 *   Einstellungen, Jarvis selbst nie.
 * - Ziel wird VOR der Bestaetigung aufgeloest: nur ein einziger exakter Treffer, sonst Ablehnung. Endgueltig-Pruefung
 *   auf Element, klickbarem Vorfahren, allen dessen Nachkommen und den viewIdResourceName; ohne klickbaren Vorfahren
 *   keine Geste, sondern Ablehnung.
 * - JEDER Befehl wird per Overlay bestaetigt; das Overlay nennt App, vollen Text und Beschreibung des Elements bzw.
 *   die wirklich gefundene App. Nach der Bestaetigung werden App, FLAG_SECURE und Element erneut geprueft.
 * - Fenster mit FLAG_SECURE (takeScreenshotOfWindow, ab Android 14), Passwort-, Code-, PIN- und Zahlenfelder und
 *   offene Bestaetigungsdialoge: nie lesen bzw. nie bedienen.
 * Bewusst NICHT isAccessibilityTool. Keine Lambdas (Bau ohne Gradle).
 */
public class JarvisBedienung extends AccessibilityService {
    static volatile JarvisBedienung aktiv;
    static volatile boolean gestoppt = false;
    static volatile Runnable beimStopp;            // MainActivity meldet den Not-Aus an die Bruecke

    View notAus;
    volatile long bis = 0;                         // N3: Ablaufzeit des laufenden Befehls (Unix-Sekunden)

    /** N2: jede neue Kette beginnt ungestoppt; der Not-Aus gilt bis zum Ende seiner Kette. */
    static void ketteBeginnt() {
        gestoppt = false;
    }

    @Override
    protected void onServiceConnected() {
        aktiv = this;
    }

    @Override
    public boolean onUnbind(Intent intent) {
        notAusWeg();
        aktiv = null;
        return super.onUnbind(intent);
    }

    @Override
    public void onDestroy() {
        notAusWeg();
        aktiv = null;
        super.onDestroy();
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // bewusst leer: der Dienst beobachtet nichts von sich aus, er handelt nur auf einen bestaetigten Befehl
    }

    @Override
    public void onInterrupt() {
    }

    /** N8: Schalter in der App aus = Bedienungshilfe ganz abschalten (muss danach in Android neu eingeschaltet werden). */
    void abschalten() {
        gestoppt = true;
        notAusWeg();
        disableSelf();
    }

    // ------------------------------------------------------------ Not-Aus und Bestaetigung

    WindowManager.LayoutParams overlay(int breite, int lage) {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(breite, WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        lp.gravity = lage;
        return lp;
    }

    void notAusZeigen() {
        new Handler(Looper.getMainLooper()).post(new Runnable() { public void run() {
            if (notAus != null) return;
            Button b = new Button(JarvisBedienung.this);
            b.setText("■ JARVIS STOPP");
            b.setTextColor(Color.WHITE);
            b.setBackgroundColor(0xEEB00020);
            b.setOnClickListener(new View.OnClickListener() { public void onClick(View v) {
                gestoppt = true;
                notAusWeg();
                Runnable r = beimStopp;
                if (r != null) new Thread(r).start();
            }});
            WindowManager.LayoutParams lp = overlay(WindowManager.LayoutParams.WRAP_CONTENT, Gravity.TOP | Gravity.CENTER_HORIZONTAL);
            lp.y = 80;
            try {
                ((WindowManager) getSystemService(WINDOW_SERVICE)).addView(b, lp);
                notAus = b;
            } catch (RuntimeException ignored) {
            }
        }});
    }

    void notAusWeg() {
        new Handler(Looper.getMainLooper()).post(new Runnable() { public void run() {
            if (notAus == null) return;
            try {
                ((WindowManager) getSystemService(WINDOW_SERVICE)).removeView(notAus);
            } catch (RuntimeException ignored) {
            }
            notAus = null;
        }});
    }

    /** Overlay mit dem konkreten Schritt und ERLAUBEN/NEIN ueber der aktuellen App; ohne Antwort in 60 s: Nein. */
    boolean bestaetigen(final String text) {
        final CountDownLatch l = new CountDownLatch(1);
        final boolean[] ja = {false};
        final View[] fenster = {null};
        new Handler(Looper.getMainLooper()).post(new Runnable() { public void run() {
            LinearLayout box = new LinearLayout(JarvisBedienung.this);
            box.setOrientation(LinearLayout.VERTICAL);
            box.setBackgroundColor(0xF0140608);
            box.setPadding(40, 32, 40, 32);
            TextView t = new TextView(JarvisBedienung.this);
            t.setText("Jarvis möchte:\n" + text);
            t.setTextColor(Color.WHITE);
            t.setTextSize(17);
            box.addView(t);
            LinearLayout reihe = new LinearLayout(JarvisBedienung.this);
            Button nein = new Button(JarvisBedienung.this);
            nein.setText("NEIN");
            Button erlauben = new Button(JarvisBedienung.this);
            erlauben.setText("ERLAUBEN");
            erlauben.setTag("ja");
            reihe.addView(erlauben);                 // ERLAUBEN links, NEIN rechts (nicht unten rechts, wo man hintippt)
            reihe.addView(nein);
            erlauben.setEnabled(false);              // Tippsperre beim Einblenden gegen versehentliches Durchtippen
            nein.setEnabled(false);
            final Button e1 = erlauben, n1 = nein;
            new Handler(Looper.getMainLooper()).postDelayed(new Runnable() { public void run() {
                e1.setEnabled(true);
                n1.setEnabled(true);
            }}, 600);
            box.addView(reihe);
            View.OnClickListener k = new View.OnClickListener() { public void onClick(View v) {
                ja[0] = "ja".equals(v.getTag());
                l.countDown();
            }};
            nein.setOnClickListener(k);
            erlauben.setOnClickListener(k);
            try {
                ((WindowManager) getSystemService(WINDOW_SERVICE)).addView(box, overlay(WindowManager.LayoutParams.MATCH_PARENT, Gravity.CENTER));
                fenster[0] = box;
            } catch (RuntimeException e) {
                l.countDown();
            }
        }});
        try {
            l.await(30, TimeUnit.SECONDS);          // B: unter dem Warten der Bruecke (40 s)
        } catch (InterruptedException ignored) {
        }
        new Handler(Looper.getMainLooper()).post(new Runnable() { public void run() {
            if (fenster[0] != null) {
                try {
                    ((WindowManager) getSystemService(WINDOW_SERVICE)).removeView(fenster[0]);
                } catch (RuntimeException ignored) {
                }
            }
        }});
        return ja[0] && !gestoppt;
    }

    /** Bestaetigen lassen und danach N3 (Ablaufzeit) pruefen. null = weiter, sonst die Antwort fuer die Bruecke. */
    JSONObject frage(String text) {
        JSONObject nein = frage(text); if (nein != null) return nein;
        if (bis > 0 && System.currentTimeMillis() / 1000 > bis) return antwort("fehler", "Befehl abgelaufen, nichts ausgeführt");
        return null;
    }

    /** true, wenn das aktive Fenster nachweislich KEIN FLAG_SECURE hat (takeScreenshotOfWindow, API 34; ein
     *  sicheres Fenster liefert ERROR_TAKE_SCREENSHOT_SECURE_WINDOW). Das Bild wird sofort verworfen. Sonst false. */
    boolean sicheresFenster(AccessibilityNodeInfo wurzel) {
        if (android.os.Build.VERSION.SDK_INT < 34 || wurzel == null) return false;
        for (int versuch = 0; versuch < 2; versuch++) {
            final CountDownLatch l = new CountDownLatch(1);
            final int[] code = {-1};
            takeScreenshotOfWindow(wurzel.getWindowId(), getMainExecutor(), new TakeScreenshotCallback() {
                public void onSuccess(ScreenshotResult r) {
                    try {
                        r.getHardwareBuffer().close();
                    } catch (RuntimeException ignored) {
                    }
                    code[0] = 0;
                    l.countDown();
                }
                public void onFailure(int fehler) {
                    code[0] = fehler;
                    l.countDown();
                }
            });
            try {
                l.await(3, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                return false;
            }
            if (code[0] == 0) return true;
            if (code[0] != ERROR_TAKE_SCREENSHOT_INTERVAL_TIME_SHORT) return false;
            try {
                Thread.sleep(1100);
            } catch (InterruptedException e) {
                return false;
            }
        }
        return false;
    }

    // ------------------------------------------------------------ Pruefungen

    static String paket(AccessibilityNodeInfo w) {
        return w == null || w.getPackageName() == null ? "" : w.getPackageName().toString();
    }

    String appName(String paket) {
        try {
            PackageManager pm = getPackageManager();
            return pm.getApplicationLabel(pm.getApplicationInfo(paket, 0)) + " (" + paket + ")";
        } catch (Exception e) {
            return paket;
        }
    }

    /** Passwort, Zahlen-/PIN-Eingabe, oder Bezeichnung/Hinweis/ID nach Code, PIN, TAN, IBAN ... */
    static boolean codeFeld(AccessibilityNodeInfo n) {
        if (n == null) return false;
        if (n.isPassword()) return true;
        int typ = n.getInputType();
        int klasse = typ & InputType.TYPE_MASK_CLASS, variante = typ & InputType.TYPE_MASK_VARIATION;
        if (klasse == InputType.TYPE_CLASS_NUMBER) return true;                 // PINs, TANs, Codes
        if (klasse == InputType.TYPE_CLASS_TEXT && (variante == InputType.TYPE_TEXT_VARIATION_PASSWORD
                || variante == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD || variante == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD))
            return true;
        return n.isEditable() && (BedienRegeln.codeFeld(n.getHintText()) || BedienRegeln.codeFeld(n.getViewIdResourceName())
                || BedienRegeln.codeFeld(n.getContentDescription()));
    }

    static boolean endgueltig(AccessibilityNodeInfo n) {
        return n != null && (BedienRegeln.endgueltig(n.getText()) || BedienRegeln.endgueltig(n.getContentDescription())
                || BedienRegeln.endgueltig(n.getViewIdResourceName()));
    }

    /** Element, sein klickbarer Vorfahr und alle Nachkommen des Vorfahren: irgendwo etwas Endgueltiges? */
    static boolean endgueltigImUmfeld(AccessibilityNodeInfo n, AccessibilityNodeInfo k) {
        if (endgueltig(n) || endgueltig(k)) return true;
        ArrayDeque<AccessibilityNodeInfo> q = new ArrayDeque<AccessibilityNodeInfo>();
        q.add(k);
        int besucht = 0;
        while (!q.isEmpty() && besucht < 500) {
            besucht++;
            AccessibilityNodeInfo x = q.poll();
            if (endgueltig(x)) return true;
            for (int i = 0; i < x.getChildCount(); i++) if (x.getChild(i) != null) q.add(x.getChild(i));
        }
        return !q.isEmpty();                         // zu gross zum Pruefen: lieber nicht
    }

    static boolean schalter(AccessibilityNodeInfo x) {
        return x != null && (x.isCheckable() || BedienRegeln.schalterKlasse(x.getClassName()));
    }

    /** A: Element, klickbarer Vorfahr oder ein Nachkomme des Vorfahren ist ein Schalter (Smart-Home-Kachel, Toggle). */
    static boolean schalterImUmfeld(AccessibilityNodeInfo n, AccessibilityNodeInfo k) {
        if (schalter(n) || schalter(k)) return true;
        ArrayDeque<AccessibilityNodeInfo> q = new ArrayDeque<AccessibilityNodeInfo>();
        q.add(k);
        int besucht = 0;
        while (!q.isEmpty() && besucht < 500) {
            besucht++;
            AccessibilityNodeInfo x = q.poll();
            if (schalter(x)) return true;
            for (int i = 0; i < x.getChildCount(); i++) if (x.getChild(i) != null) q.add(x.getChild(i));
        }
        return !q.isEmpty();
    }

    /** M2: offener Bestaetigungsdialog (Standard-Dialogknoepfe oder Dialog-Klasse). Dann nur noch lesen/zurueck. */
    static boolean dialogOffen(AccessibilityNodeInfo w) {
        if (w == null) return false;
        CharSequence cls = w.getClassName();
        if (cls != null && cls.toString().contains("Dialog")) return true;
        return !w.findAccessibilityNodeInfosByViewId("android:id/button1").isEmpty()
                || !w.findAccessibilityNodeInfosByViewId("android:id/button2").isEmpty();
    }

    static ArrayList<AccessibilityNodeInfo> alle(AccessibilityNodeInfo w) {
        ArrayList<AccessibilityNodeInfo> aus = new ArrayList<AccessibilityNodeInfo>();
        ArrayDeque<AccessibilityNodeInfo> q = new ArrayDeque<AccessibilityNodeInfo>();
        if (w != null) q.add(w);
        while (!q.isEmpty() && aus.size() < 3000) {
            AccessibilityNodeInfo n = q.poll();
            aus.add(n);
            for (int i = 0; i < n.getChildCount(); i++) if (n.getChild(i) != null) q.add(n.getChild(i));
        }
        return aus;
    }

    static String beschriftung(AccessibilityNodeInfo n) {
        CharSequence t = n.getText() != null && n.getText().length() > 0 ? n.getText() : n.getContentDescription();
        return BedienRegeln.sauber(t);
    }

    static JSONObject antwort(String feld, Object wert) {
        try {
            return new JSONObject().put(feld, wert);
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    static JSONObject gesperrt(String grund) {
        try {
            return new JSONObject().put("gesperrt", true).put("grund", grund);
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    // ------------------------------------------------------------ Befehle

    /** Fuehrt einen Befehl aus: aufloesen, bestaetigen lassen, erneut pruefen, handeln. Ergebnis fuer /v1/handy/ergebnis. */
    JSONObject ausfuehren(JSONObject b) throws Exception {
        if (gestoppt) return antwort("gestoppt", true);
        bis = b.optLong("bis", 0);
        String befehl = b.optString("befehl");
        if ("fertig".equals(befehl)) {
            notAusWeg();
            return antwort("ok", true);
        }
        if ("home".equals(befehl)) {
            JSONObject nein = frage("Zum Startbildschirm wechseln"); if (nein != null) return nein;
            performGlobalAction(GLOBAL_ACTION_HOME);
            return nachher(900);
        }
        if ("oeffnen".equals(befehl)) {
            Intent i = HandyAktionen.appStarten(this, b.optString("app"));
            if (i == null || i.getComponent() == null) return antwort("fehler", "App nicht gefunden");
            String p = i.getComponent().getPackageName();
            if (!BedienRegeln.paketErlaubt(p)) return gesperrt("App nicht freigegeben");
            JSONObject nein = frage("App öffnen: " + appName(p)); if (nein != null) return nein;
            startActivity(i);
            return nachher(900);
        }
        AccessibilityNodeInfo wurzel = getRootInActiveWindow();
        String vorne = paket(wurzel);
        if (wurzel == null || !BedienRegeln.paketErlaubt(vorne)) return gesperrt("App nicht freigegeben");
        if (!sicheresFenster(wurzel)) return gesperrt("geschütztes Fenster");
        String app = appName(vorne);
        if ("zurueck".equals(befehl)) {
            JSONObject nein = frage("In " + app + " zurück"); if (nein != null) return nein;
            if (!vorne.equals(paket(getRootInActiveWindow()))) return antwort("fehler", "Bildschirm hat sich geändert");
            performGlobalAction(GLOBAL_ACTION_BACK);
            return nachher(900);
        }
        if ("lesen".equals(befehl)) {
            JSONObject nein = frage("Den Bildschirm von " + app + " lesen und an Jarvis schicken"); if (nein != null) return nein;
            return nachher(0);
        }
        if (dialogOffen(wurzel)) return gesperrt("Bestätigungsdialog offen");
        if ("tippen".equals(befehl)) return tippen(wurzel, vorne, app, b.optString("ziel"));
        if ("eingeben".equals(befehl)) return eingeben(wurzel, vorne, app, b.optString("feld"), b.optString("text"));
        if ("scrollen".equals(befehl)) {
            AccessibilityNodeInfo s = null;
            for (AccessibilityNodeInfo n : alle(wurzel)) {
                if (n.isScrollable() && n.isVisibleToUser()) {
                    s = n;
                    break;
                }
            }
            if (s == null) return antwort("fehler", "Nichts zum Scrollen");
            boolean hoch = "hoch".equals(b.optString("richtung"));
            JSONObject nein = frage("In " + app + " " + (hoch ? "nach oben" : "nach unten") + " scrollen"); if (nein != null) return nein;
            s.performAction(hoch ? AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD : AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
            return nachher(900);
        }
        return antwort("fehler", "Unbekannter Befehl");
    }

    JSONObject tippen(AccessibilityNodeInfo wurzel, String vorne, String app, String ziel) throws Exception {
        if (BedienRegeln.endgueltig(ziel)) return antwort("fehler", "Absenden und Ähnliches macht der Mensch");
        // H2: alle sichtbaren Elemente, deren Text ODER Beschreibung genau dem Ziel entspricht; nur genau eines
        AccessibilityNodeInfo n = null;
        for (AccessibilityNodeInfo x : alle(wurzel)) {
            if (!x.isVisibleToUser()) continue;
            if (BedienRegeln.einzigerTreffer(new String[]{BedienRegeln.sauber(x.getText()),
                    BedienRegeln.sauber(x.getContentDescription())}, ziel) == -1) continue;
            if (n != null) return antwort("fehler", "Mehrere Elemente heißen so, das ist mir zu unsicher");
            n = x;
        }
        if (n == null) return antwort("fehler", "Kein Element heißt genau so");
        if (codeFeld(n)) return gesperrt("Code- oder Passwortfeld");
        AccessibilityNodeInfo k = n;
        while (k != null && !k.isClickable()) k = k.getParent();
        if (k == null) return antwort("fehler", "Das Element ist nicht antippbar");        // keine Ersatz-Geste
        if (schalterImUmfeld(n, k)) return gesperrt("Schalter (an/aus) tippt Jarvis nicht an");
        if (endgueltigImUmfeld(n, k)) return antwort("fehler", "Das Element löst etwas Endgültiges aus, das macht der Mensch");
        String text = BedienRegeln.sauber(n.getText()), besch = BedienRegeln.sauber(n.getContentDescription());
        JSONObject nein = frage("In " + app + " antippen: „" + (text.isEmpty() ? besch : text) + "“"
                + (besch.isEmpty() || besch.equals(text) ? "" : "\nBeschreibung: „" + besch + "“"));
        if (nein != null) return nein;
        // N4: nach der Bestaetigung alles noch einmal pruefen
        AccessibilityNodeInfo jetzt = getRootInActiveWindow();
        if (!vorne.equals(paket(jetzt)) || !sicheresFenster(jetzt) || dialogOffen(jetzt) || !k.refresh()
                || !k.isVisibleToUser() || !n.refresh() || endgueltigImUmfeld(n, k) || schalterImUmfeld(n, k)
                || BedienRegeln.einzigerTreffer(new String[]{BedienRegeln.sauber(n.getText()),
                        BedienRegeln.sauber(n.getContentDescription())}, ziel) == -1)
            return antwort("fehler", "Bildschirm hat sich geändert, nichts angetippt");
        k.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        return nachher(900);
    }

    JSONObject eingeben(AccessibilityNodeInfo wurzel, String vorne, String app, String feldRoh, String text) throws Exception {
        String feld = BedienRegeln.sauber(feldRoh);
        AccessibilityNodeInfo f = null;
        int gefunden = 0;
        for (AccessibilityNodeInfo n : alle(wurzel)) {
            if (!n.isEditable() || !n.isVisibleToUser()) continue;
            if (feld.isEmpty() || feld.equalsIgnoreCase(BedienRegeln.sauber(n.getHintText()))
                    || feld.equalsIgnoreCase(BedienRegeln.sauber(n.getContentDescription()))) {
                gefunden++;
                f = n;
            }
        }
        if (gefunden == 0) return antwort("fehler", "Kein passendes Eingabefeld");
        if (gefunden > 1) return antwort("fehler", "Mehrere Eingabefelder passen, das ist mir zu unsicher");
        if (codeFeld(f)) return gesperrt("Code- oder Passwortfeld");
        String name = BedienRegeln.sauber(f.getHintText());
        JSONObject nein = frage("In " + app + (name.isEmpty() ? "" : " ins Feld „" + name + "“") + " eingeben:\n„" + text + "“");
        if (nein != null) return nein;
        AccessibilityNodeInfo jetzt = getRootInActiveWindow();
        if (!vorne.equals(paket(jetzt)) || !sicheresFenster(jetzt) || dialogOffen(jetzt) || !f.refresh() || codeFeld(f))
            return antwort("fehler", "Bildschirm hat sich geändert, nichts eingegeben");
        Bundle a = new Bundle();
        a.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
        f.performAction(AccessibilityNodeInfo.ACTION_FOCUS);
        if (!f.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, a)) return antwort("fehler", "Text ließ sich nicht setzen");
        return nachher(900);
    }

    /** Kurz warten, bis die Oberflaeche nachgezogen hat, dann den neuen Bildschirm (oder "gesperrt"). */
    JSONObject nachher(int warten) throws Exception {
        if (warten > 0) Thread.sleep(warten);
        if (gestoppt) return antwort("gestoppt", true);
        AccessibilityNodeInfo w = getRootInActiveWindow();
        if (w == null) return antwort("ok", true);
        String p = paket(w);
        if ("de.homelab.jarvis".equals(p))
            return antwort("bildschirm", new JSONObject().put("paket", p).put("elemente", new JSONArray()));
        if (!BedienRegeln.paketErlaubt(p)) return gesperrt("App nicht freigegeben");
        if (!sicheresFenster(w)) return gesperrt("geschütztes Fenster");
        return antwort("bildschirm", lesen(w));
    }

    /** Vereinfachter Bildschirm: sichtbare Texte und Beschreibungen, Art, tippbar. Nie Code-/Passwortfelder. */
    JSONObject lesen(AccessibilityNodeInfo w) throws Exception {
        JSONArray el = new JSONArray();
        for (AccessibilityNodeInfo n : alle(w)) {
            if (el.length() >= 200) break;
            if (!n.isVisibleToUser() || codeFeld(n)) continue;
            String t = beschriftung(n);
            if (t.isEmpty() && n.isEditable()) t = BedienRegeln.sauber(n.getHintText());
            if (t.isEmpty()) continue;
            String cls = n.getClassName() == null ? "" : n.getClassName().toString();
            String art = n.isEditable() ? "Feld" : cls.endsWith("Button") ? "Knopf" : cls.endsWith("ImageView") ? "Bild" : "Text";
            el.put(new JSONObject().put("art", art).put("text", t.length() > 200 ? t.substring(0, 200) : t)
                    .put("tippbar", n.isClickable() || (n.getParent() != null && n.getParent().isClickable())));
        }
        return new JSONObject().put("paket", paket(w)).put("elemente", el);
    }

    // ------------------------------------------------------------ WhatsApp senden nach gesprochenem Ja (30.10.2026)

    static String[] texte(java.util.List<AccessibilityNodeInfo> l) {
        String[] t = new String[l.size()];
        for (int i = 0; i < l.size(); i++) t[i] = l.get(i).getText() == null ? "" : l.get(i).getText().toString();
        return t;
    }

    /** Einzige Ausnahme von der Sperre fuer WhatsApp: Nach dem gesprochenen Ja hat MainActivity den Chat mit Text per
     *  wa.me geoeffnet. Hier wird hoechstens 10 s gewartet, bis WhatsApp vorne ist, dann geprueft, dass im Chat-Kopf genau
     *  der bestaetigte Empfaenger und im einzigen Eingabefeld genau der bestaetigte Text steht (BedienRegeln.chatPasst),
     *  und nur dann der eine Senden-Knopf getippt. Nichts davon geht an die Bruecke. IDs von WhatsApp sind ungeprueft
     *  (Geraetetest): passt etwas nicht, wird NICHT gesendet und die Person tippt selbst. */
    String whatsappSenden(String name, String nummer, String text) {
        for (int versuch = 0; versuch < 20; versuch++) {
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                return "abgebrochen";
            }
            AccessibilityNodeInfo w = getRootInActiveWindow();
            if (w == null || !BedienRegeln.whatsapp(w.getPackageName())) continue;
            String p = paket(w);
            java.util.List<AccessibilityNodeInfo> kopf = w.findAccessibilityNodeInfosByViewId(p + ":id/conversation_contact_name");
            java.util.List<AccessibilityNodeInfo> felder = w.findAccessibilityNodeInfosByViewId(p + ":id/entry");
            if (kopf.isEmpty() || felder.isEmpty()) continue;
            if (!BedienRegeln.chatPasst(texte(kopf), name, nummer, texte(felder), text))
                return "Im Chat stand nicht genau, was du bestätigt hast. Nichts gesendet.";
            java.util.List<AccessibilityNodeInfo> knopf = w.findAccessibilityNodeInfosByViewId(p + ":id/send");
            if (knopf.size() != 1 || !BedienRegeln.sendeKnopf(knopf.get(0).getViewIdResourceName(), null)
                    || !knopf.get(0).isVisibleToUser())
                return "Den Senden-Knopf habe ich nicht eindeutig gefunden. Bitte selbst senden.";
            // unmittelbar vor dem Tippen noch einmal: dasselbe Fenster, derselbe Inhalt
            AccessibilityNodeInfo jetzt = getRootInActiveWindow();
            if (jetzt == null || !p.equals(paket(jetzt)) || !felder.get(0).refresh() || !kopf.get(0).refresh()
                    || !knopf.get(0).refresh() || !knopf.get(0).isVisibleToUser()                         // N5
                    || !BedienRegeln.sendeKnopf(knopf.get(0).getViewIdResourceName(), null)
                    || !BedienRegeln.chatPasst(texte(kopf), name, nummer, texte(felder), text))
                return "Der Chat hat sich geändert. Nichts gesendet.";
            if (!knopf.get(0).performAction(AccessibilityNodeInfo.ACTION_CLICK)) return "Senden ging nicht. Bitte selbst senden.";
            return "";
        }
        return "WhatsApp hat den Chat nicht wie erwartet geöffnet. Nichts gesendet.";
    }
}
