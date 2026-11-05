package de.homelab.jarvis;

import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Regeln der Handy-Bedienung (Stufe 2) ohne Android-Abhaengigkeit, damit sie sich auf einer normalen JVM pruefen
 * lassen (tools/bedienregeln_test). Seit der Pruefung vom 29.10.2026 (H2, M1, M2). Dieselben Listen stehen in
 * bruecke/handy.py (dort zweite Linie, hier massgeblich). Keine Lambdas (Bau ohne Gradle).
 */
final class BedienRegeln {
    private BedienRegeln() {
    }

    /** M1: Positivliste. Nur hier bedient Jarvis. Ausdruecklich NICHT: SMS-, Mail-, Messenger-Apps, Browser. */
    static final String[] ERLAUBTE_APPS = {
            "com.google.android.deskclock", "com.sec.android.app.clockpackage",
            "com.spotify.music", "com.google.android.apps.youtube.music",
            "com.google.android.apps.maps", "de.hafas.android.db",
            "com.google.android.calendar", "com.samsung.android.calendar",
            "com.google.android.keep", "com.google.android.apps.photos"};
    static final String[] NIE_APPS = {
            "com.google.android.apps.messaging", "com.samsung.android.messaging", "com.android.mms",
            "com.google.android.gm", "com.microsoft.office.outlook", "com.samsung.android.email.provider",
            "de.gmx.mobile.android.mail", "de.web.mobile.android.mail", "com.whatsapp", "com.whatsapp.w4b",
            "org.telegram.messenger", "org.thoughtcrime.securesms", "com.android.chrome", "org.mozilla.firefox",
            "com.sec.android.app.sbrowser", "com.brave.browser", "com.microsoft.emmx", "com.opera.browser",
            // A: Alexa-App (Drop In = Live-Ton, Smart-Home-Kacheln, Routinen), Smart-Home-, Kamera-, Babyfon-Apps
            "com.amazon.dee.app", "com.google.android.apps.chromecast.app", "io.homeassistant.companion.android",
            "com.xiaomi.smarthome"};   // Babyfon-Apps sperrt SPERR_MUSTER (avent, babyphon)
    static final String[] SPERR_PAKETE = {
            "de.homelab.jarvis", "com.android.settings", "com.samsung.android.settings", "com.google.android.settings",
            "com.android.permissioncontroller", "com.google.android.permissioncontroller", "com.android.packageinstaller",
            "com.google.android.packageinstaller", "com.android.vending", "com.google.android.gms", "com.android.systemui",
            "com.android.keyguard", "com.google.android.apps.walletnfcrel", "com.samsung.android.spay",
            "com.paypal.android.p2pmobile", "com.x8bit.bitwarden", "com.agilebits.onepassword",
            "keepass2android.keepass2android", "com.kunzisoft.keepass", "com.lastpass.lpandroid", "com.dashlane",
            "proton.android.pass", "com.google.android.apps.authenticator2", "com.azure.authenticator", "com.authy.authy",
            "com.beemdevelopment.aegis", "org.fedorahosted.freeotp", "com.twofasapp",
            "com.starfinanz.smob.android.sfinanzstatus", "com.starfinanz.mobile.android.pushtan", "de.sparkasse",
            "de.dkb.portalapp", "de.comdirect", "de.ingdiba", "de.number26", "de.consorsbank", "de.postbank",
            "de.commerzbanking", "de.fiducia", "de.volksbank", "de.traderepublic", "com.c24.bank", "de.deutschebank"};
    static final Pattern SPERR_MUSTER = Pattern.compile(
            "(bank|finanz|wallet|\\bpay|pay\\b|pushtan|\\btan\\b|authenticator|authy|\\botp|otp\\b|passwor|keepass|vault|"
            + "bitwarden|1password|lastpass|keychain|crypto|krypto|broker|trading|depot|\\bmail|mail\\b|messag|\\bsms|browser|avent|babyphon|babyfon)",
            Pattern.CASE_INSENSITIVE);

    /** M2: Endgueltiges (Wortstaemme und kurze Bestaetigungen), wie ENDGUELTIG in bruecke/handy.py. */
    static final Pattern ENDGUELTIG = Pattern.compile(
            "(?<![a-zäöüß])(send\\w*|absend\\w*|abschick\\w*|verschick\\w*|schick\\w*|post|posten|teilen|share|"
            + "bezahl\\w*|zahl(en|ung)\\w*|pay\\w*|kauf\\w*|buy|bestell\\w*|order|überweis\\w*|ueberweis\\w*|transfer\\w*|"
            + "lösch\\w*|loesch\\w*|delete\\w*|entfern\\w*|remove\\w*|deinstall\\w*|uninstall\\w*|install\\w*|anruf\\w*|call|"
            + "wählen|waehlen|abonnier\\w*|subscribe\\w*|zulassen|allow\\w*|erlaub\\w*|akzeptier\\w*|accept\\w*|bestätig\\w*|"
            + "bestaetig\\w*|confirm\\w*|zurücksetz\\w*|zuruecksetz\\w*|reset\\w*|abmeld\\w*|logout|log out|sign out|ok|okay|ja|"
            + "yes|weiter|next|fertig|done|buch\\w*|book\\w*|veröffentlich\\w*|veroeffentlich\\w*|publish\\w*|archivier\\w*|"
            + "archive\\w*|kündig\\w*|kuendig\\w*|cancel\\w*|weiterleit\\w*|forward\\w*|hochlad\\w*|upload\\w*|submit\\w*|"
            + "einreich\\w*|unterschreib\\w*|sign|freigeb\\w*|speicher\\w*|save|übernehm\\w*|uebernehm\\w*|apply|verbind\\w*|"
            + "connect\\w*|pair\\w*|koppel\\w*|starten|start|drop ?in|kamera\\w*|camera\\w*|entsperr\\w*|unlock\\w*|ausführ\\w*|"
            + "ausfuehr\\w*|execute\\w*|run|einschalt\\w*|ausschalt\\w*|anschalt\\w*|abschalt\\w*|turn on|turn off|switch on|"
            + "switch off|aktivier\\w*|deaktivier\\w*|activate\\w*|deactivate\\w*|papierkorb|trash|verlass\\w*|leave|leeren|leere|"
            + "empty|verwerf\\w*|verwirf\\w*|discard\\w*|hinzufüg\\w*|hinzufueg\\w*|add)(?![a-zäöüß])",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
    /** M2: Code-, PIN-, Passwort- und Bankfelder, nie lesen oder fuellen. */
    static final Pattern CODE_FELD = Pattern.compile(
            "(pin|passwor|kennwort|passcode|code|otp|\\btan\\b|cvc|cvv|iban|geheim|sicherheits|secret|verification|"
            + "bestätigungs|bestaetigungs)", Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

    private static final Pattern FORMAT = Pattern.compile(
            "[\\u00ad\\u061c\\u180e\\u200b-\\u200f\\u202a-\\u202e\\u2060-\\u2064\\u2066-\\u206f\\ufeff\\ufff9-\\ufffb"
            + "\\x{E0000}-\\x{E007F}]");
    private static final Pattern STEUER = Pattern.compile("[\\x00-\\x1f\\x7f-\\x9f\\u2028\\u2029]");
    private static final Pattern LEER = Pattern.compile("[\\s\\u00a0\\u2007\\u202f]+");

    /** Formatzeichen weg, Steuerzeichen zu Leerzeichen, Leerraum (auch geschuetzter) zusammengefasst. */
    static String sauber(CharSequence c) {
        if (c == null) return "";
        String s = FORMAT.matcher(c).replaceAll("");
        s = STEUER.matcher(s).replaceAll(" ");
        return LEER.matcher(s).replaceAll(" ").trim();
    }

    /** A: haeufige kyrillische und griechische Doppelgaenger -> Lateinisch (gleiche Tabelle wie in handy.py). */
    static final String HOMO_VON = "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u043a\u043c\u0442\u0432\u043d\u0456\u0441\u0458\u0455\u0501\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0406\u0408\u0405\u03b1\u03bf\u03bd\u03c1\u03c4\u03b9\u03ba\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7";
    static final String HOMO_NACH = "aeopcyxkmtbhicjsdABEKMHOPCTXIJSaovptikABEZHIKMNOPTYX";

    /** Vergleichsform: Formatzeichen weg, NFKC (Vollbreite u. a.), Doppelgaenger, Trenner (_ : / . -) zu Leerzeichen,
     *  Leerraum zusammengefasst, klein. Nur fuer Vergleiche. */
    static String woerter(CharSequence c) {
        if (c == null) return "";
        String s = java.text.Normalizer.normalize(FORMAT.matcher(c).replaceAll(""), java.text.Normalizer.Form.NFKC);
        StringBuilder b = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            int j = HOMO_VON.indexOf(ch);
            b.append(j >= 0 ? HOMO_NACH.charAt(j) : ch);
        }
        return sauber(b.toString().replaceAll("[_:/.\\-]+", " ")).toLowerCase(Locale.ROOT);
    }

    /** A: Schalter-Elemente (an/aus) tippt Jarvis nie an. */
    static boolean schalterKlasse(CharSequence klasse) {
        String k = klasse == null ? "" : klasse.toString();
        return k.contains("Switch") || k.contains("ToggleButton") || k.contains("CheckBox") || k.contains("RadioButton")
                || k.contains("CompoundButton") || k.contains("CheckedTextView") || k.contains("Chip");
    }

    static boolean endgueltig(CharSequence c) {
        return c != null && ENDGUELTIG.matcher(woerter(c)).find();
    }

    static boolean codeFeld(CharSequence c) {
        return c != null && CODE_FELD.matcher(woerter(c)).find();
    }

    static boolean paketGesperrt(CharSequence paket) {
        String p = paket == null ? "" : paket.toString().trim().toLowerCase(Locale.ROOT);
        if (p.isEmpty()) return true;
        for (String s : SPERR_PAKETE) if (p.equals(s) || p.startsWith(s + ".")) return true;
        for (String s : NIE_APPS) if (p.equals(s) || p.startsWith(s + ".")) return true;
        return SPERR_MUSTER.matcher(p).find();
    }

    static boolean paketErlaubt(CharSequence paket) {
        String p = paket == null ? "" : paket.toString().trim().toLowerCase(Locale.ROOT);
        for (String s : ERLAUBTE_APPS) if (p.equals(s)) return !paketGesperrt(p);
        return false;
    }

    /** H2: genau ein exakter Treffer (Gross-/Kleinschreibung und Leerraum egal). >=0 Index, -1 keiner, -2 mehrere. */
    static int einzigerTreffer(String[] texte, String ziel) {
        String z = woerter(ziel);
        if (z.isEmpty()) return -1;
        int treffer = -1;
        for (int i = 0; i < texte.length; i++) {
            if (texte[i] != null && woerter(texte[i]).equals(z)) {
                if (treffer >= 0) return -2;
                treffer = i;
            }
        }
        return treffer;
    }

    // ------------------------------------------------------------ Anruf und WhatsApp nach Ja (seit 30.10.2026)

    /** Kontakt nach Namen: genau ein exakter Anzeigename, sonst genau einer, dessen Vorname passt (bei einem Wort).
     *  >=0 Index in namen (Liste verschiedener Anzeigenamen), -1 keiner, -2 mehrdeutig. */
    static int kontaktWahl(String[] namen, String gesucht) {
        int exakt = einzigerTreffer(namen, gesucht);
        if (exakt != -1) return exakt;
        String g = woerter(gesucht);
        if (g.isEmpty() || g.contains(" ")) return -1;
        int treffer = -1;
        for (int i = 0; i < namen.length; i++) {
            String n = woerter(namen[i]);
            if (n.equals(g) || n.startsWith(g + " ")) {
                if (treffer >= 0) return -2;
                treffer = i;
            }
        }
        return treffer;
    }

    /** Nummer eines Kontakts: die Hauptnummer, sonst die einzige Mobilnummer (typ 2), sonst die einzige Nummer.
     *  >=0 Index, -2 mehrdeutig, -1 keine. */
    static int nummerWahl(int[] typen, boolean[] haupt) {
        if (typen.length == 0) return -1;
        int h = -1, mobil = -1, nMobil = 0, nHaupt = 0;
        for (int i = 0; i < typen.length; i++) {
            if (haupt[i]) { h = i; nHaupt++; }
            if (typen[i] == 2) { mobil = i; nMobil++; }
        }
        if (nHaupt == 1) return h;
        if (nMobil == 1) return mobil;
        return typen.length == 1 ? 0 : -2;
    }

    /** Mehrwert-, Auskunfts-, Kurzwahl- und Satellitennummern (wie _nummer in bruecke/handy.py); 110/112 frei. */
    static boolean nummerGesperrt(String roh) {
        String s = roh == null ? "" : roh.replaceAll("^\\s*(\\+|00)\\s*49\\s*\\(\\s*0\\s*\\)", "+49").replaceAll("[\\s/().-]", "");
        if (s.startsWith("00")) s = "+" + s.substring(2);
        if (!s.matches("\\+?[0-9]{3,20}")) return true;
        if (s.equals("110") || s.equals("112")) return false;
        if (s.startsWith("+490")) s = "+49" + s.substring(4);   // M1: "+49 0900", "+49-(0)900", "0049 0900"
        String national = s.startsWith("+49") ? "0" + s.substring(3) : s;
        if (national.matches("0(900|137|138|180|19[0-4]|199|700|118|12\\d|11[0-9]{3,}).*")) return true;
        if (s.matches("\\+(1(900|976)|44(9|87|70)|43(9|8[12])|41(90)|33(8[19])|39(89)|31(90)|88[0-9]|87[0-9]|979|808).*")) return true;
        return !s.startsWith("+") && !s.startsWith("0");      // Kurzwahlen
    }

    static String ziffern(CharSequence c) {
        return c == null ? "" : c.toString().replaceAll("[^0-9]", "");
    }

    /** N5: ganze Nummer international ohne + (0171… -> 49171…, 0049… -> 49…, +49 0171 -> 49171…). */
    static String nummerNorm(CharSequence c) {
        String roh = c == null ? "" : c.toString().trim();
        String z = ziffern(roh);
        if (roh.startsWith("+")) {
            if (z.startsWith("490")) z = "49" + z.substring(3);
            return z;
        }
        if (z.startsWith("00")) {
            z = z.substring(2);
            return z.startsWith("490") ? "49" + z.substring(3) : z;
        }
        if (z.startsWith("0")) return "49" + z.substring(1);
        return z;
    }

    /** M2/N2: Direkt waehlen nach Ja nur fuer deutsche Nummern, nie Notruf und nie gesperrte Nummern. */
    static boolean jaNummerErlaubt(String nummer) {
        if (nummer == null || nummerGesperrt(nummer)) return false;
        String n = nummerNorm(nummer);
        return n.startsWith("49") && !n.equals("49110") && !n.equals("49112") && n.length() >= 8;
    }

    /** Fuer Nummern aus dem Telefonbuch: nie Notruf per Ja (dort Waehlfeld), gesperrte nie. */
    static boolean kontaktNummerErlaubt(String nummer) {
        if (nummer == null || nummerGesperrt(nummer)) return false;
        String z = ziffern(nummer), n = nummerNorm(nummer);
        return !z.equals("110") && !z.equals("112") && !n.equals("49110") && !n.equals("49112");
    }

    /** Vor dem Tippen auf Senden in WhatsApp: Im Chat-Kopf steht genau der bestaetigte Empfaenger (Name gleich oder
     *  dieselben letzten 9 Ziffern), es gibt genau ein Eingabefeld, und darin steht genau der bestaetigte Text. */
    static boolean chatPasst(String[] kopf, String name, String nummer, String[] felder, String text) {
        if (felder == null || felder.length != 1 || felder[0] == null || text == null) return false;
        // genau der Text, nur Rand-Leerraum egal (ein unsichtbarer Rest oder ein Umbruch = Abbruch)
        if (!felder[0].trim().equals(text.trim()) || text.trim().isEmpty()) return false;
        String n = sauber(name), z = nummerNorm(nummer);    // Name streng: ein Ersatzzeichen im Kopf = Abbruch
        for (String k : kopf) {
            if (k == null) continue;
            if (!n.isEmpty() && sauber(k).equalsIgnoreCase(n)) return true;
            String ks = sauber(k);                          // WhatsApp setzt Richtungszeichen um Nummern
            if (z.length() >= 8 && ks.matches("[+0-9 ()/-]{6,}") && nummerNorm(ks).equals(z)) return true;   // ganze Nummer
        }
        return false;
    }

    /** Der Senden-Knopf von WhatsApp (ID oder Beschreibung), sonst nichts. */
    static boolean sendeKnopf(String viewId, String beschreibung) {
        if ("com.whatsapp:id/send".equals(viewId) || "com.whatsapp.w4b:id/send".equals(viewId)) return true;
        String b = woerter(beschreibung);
        return viewId == null && (b.equals("senden") || b.equals("send"));
    }

    static boolean whatsapp(CharSequence paket) {
        return "com.whatsapp".contentEquals(paket == null ? "" : paket) || "com.whatsapp.w4b".contentEquals(paket == null ? "" : paket);
    }

    /** M4: Index der Aktion mit genau dieser Nonce in der neuesten Karte, sonst -1 (veraltet oder fremd). */
    static int indexFuerNonce(String[] nonces, String nonce) {
        if (nonce == null || !nonce.matches("[0-9a-f]{16}")) return -1;
        for (int i = 0; i < nonces.length; i++) if (nonce.equals(nonces[i])) return i;
        return -1;
    }
}
