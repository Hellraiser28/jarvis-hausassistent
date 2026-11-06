package de.homelab.jarvis;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Teilen an Jarvis (seit 4.15, Ideen-Paket 05.11.2026, A1): reine Regeln ohne Android, damit sie sich auf einer normalen
 * JVM pruefen lassen (tools/app_regeln_test.sh). Was geteilt wird, ist fremder Text aus einer anderen App; er landet nur
 * vorbereitet im Eingabefeld, abschicken muss die Person selbst. Keine Lambdas (Bau ohne Gradle).
 */
final class TeilenRegeln {
    private TeilenRegeln() {
    }

    /** So viel geteilter Text kommt hoechstens ins Eingabefeld (Rest mit "…" abgeschnitten). */
    static final int TEXT_MAX = 1500;
    /** Laengste Kante des aufbereiteten Bildes, wie BILD_KANTE in app.html (Claude-Bildgroesse). */
    static final int BILD_KANTE = 1568;
    static final Pattern LINK = Pattern.compile("(?i)\\bhttps?://[^\\s<>\"]+");

    /** Leerraum jeder Art (auch Zeilenumbrueche, geschuetzte Leerzeichen) zu einem Leerzeichen, Steuer-, Format- und
     *  Richtungszeichen weg (U+202E tarnt sonst Text, wie bei sichererName), vorne und hinten getrimmt. */
    static String sauber(String s) {
        if (s == null) return "";
        return s.replaceAll("[\\s\\p{Z}]+", " ").replaceAll("\\p{C}+", "").trim();
    }

    /** Hoechstens max Zeichen, ohne ein Ersatzpaar (Emoji) zu zerschneiden; gekuerzt endet es auf "…". */
    static String kappen(String s, int max) {
        if (s == null) return "";
        if (s.length() <= max) return s;
        int ende = Math.max(0, max - 1);
        if (ende > 0 && Character.isHighSurrogate(s.charAt(ende - 1))) ende--;
        return s.substring(0, ende) + "…";
    }

    /**
     * Text fuer das Eingabefeld aus EXTRA_TEXT und EXTRA_SUBJECT. Steckt ein Link darin, steht "Was ist das?" davor; ist
     * der Text nur ein Link, kommt der Betreff (bei Browsern der Seitentitel) dazu. Ohne Link bleibt der Text, wie er
     * ist (mit Betreff davor, wenn der etwas Neues sagt). Leer, wenn nichts Brauchbares geteilt wurde.
     */
    static String eingabe(String text, String betreff, boolean englisch) {
        String t = sauber(text), b = sauber(betreff);
        if (t.isEmpty()) {
            t = b;
            b = "";
        }
        if (t.isEmpty()) return "";
        if (!b.isEmpty() && klein(t).contains(klein(b))) b = "";
        Matcher m = LINK.matcher(t);
        String aus;
        if (m.find()) {
            String frage = englisch ? "What is this?" : "Was ist das?";
            boolean nurLink = t.equals(m.group());
            String kern = nurLink && !b.isEmpty() ? b + " – " + t : t;
            aus = klein(kern).startsWith(klein(frage)) ? kern : frage + " " + kern;
        } else {
            aus = b.isEmpty() ? t : b + " – " + t;
        }
        return kappen(aus, TEXT_MAX);
    }

    static String klein(String s) {
        return s.toLowerCase(java.util.Locale.ROOT);
    }

    /** Nur content:// eines fremden Anbieters (wie MainActivity.sichereAdresse fuer Auswahl-Dialoge): nie file://, nie
     *  die eigenen Anbieter der App (sonst koennte eine untergeschobene Adresse private Dateien der App lesen). */
    static boolean fremdeInhaltsAdresse(String schema, String anbieter, String paket) {
        if (!"content".equals(schema) || anbieter == null || anbieter.isEmpty() || paket == null) return false;
        return !anbieter.equals(paket) && !anbieter.startsWith(paket + ".");
    }

    /** Anzeigename des Anhangs (hoechstens 120 Zeichen wie in app.html); ohne Namen "Bild.jpg" bzw. "image.jpg". */
    static String bildName(String anzeige, boolean englisch) {
        String n = sauber(anzeige);
        if (n.isEmpty()) return englisch ? "image.jpg" : "Bild.jpg";
        return n.length() > 120 ? n.substring(n.length() - 120) : n;
    }

    /** Zielgroesse beim Verkleinern: laengste Kante hoechstens kante, nie vergroessern, gerundet wie in app.html. */
    static int[] zielGroesse(int breite, int hoehe, int kante) {
        if (breite <= 0 || hoehe <= 0 || kante <= 0) return new int[]{0, 0};
        double f = Math.min(1.0, kante / (double) Math.max(breite, hoehe));
        return new int[]{Math.max(1, (int) Math.round(breite * f)), Math.max(1, (int) Math.round(hoehe * f))};
    }

    /** inSampleSize fuer BitmapFactory (Android 8): groesste Zweierpotenz, nach der die laengste Kante noch >= kante ist. */
    static int stichprobe(int breite, int hoehe, int kante) {
        if (breite <= 0 || hoehe <= 0 || kante <= 0) return 1;
        int s = 1, lang = Math.max(breite, hoehe);
        while (lang / (s * 2) >= kante && s < 64) s *= 2;
        return s;
    }

    /** Typ des Originals fuer die Bruecke: nur ein konkreter Bildtyp (kein "image/*"), sonst leer. */
    static String originalTyp(String typ) {
        if (typ == null) return "";
        String t = typ.trim().toLowerCase(java.util.Locale.ROOT);
        return t.matches("image/[a-z0-9.+-]+") ? t : "";
    }
}
