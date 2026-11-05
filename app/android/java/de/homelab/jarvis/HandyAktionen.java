package de.homelab.jarvis;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.provider.AlarmClock;
import android.provider.Settings;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Calendar;
import java.util.List;
import java.util.Locale;

/**
 * Handy-Steuerung Stufe 1 (Prototyp, 29.10.2026): Systemaktionen ueber Android-Intents, ohne Bedienungshilfe.
 * Die Bruecke schickt sie im Feld "handy" der Antwort, nur an das Geraet, das gefragt hat (bruecke/handy.py prueft
 * und normalisiert). Ausgefuehrt wird jede Aktion erst nach einem Tipp der Person auf AUSFUEHREN (MainActivity,
 * Vorgabe 29.10.2026). Was das Handy verlaesst, ist hier nur ein Entwurf: ACTION_DIAL statt ACTION_CALL, SMS und WhatsApp
 * mit vorbefuelltem Text, abschicken muss der Mensch. Keine Lambdas (Bau ohne Gradle).
 */
final class HandyAktionen {
    private HandyAktionen() {
    }

    /** Seit 03.11.2026 ("wie Gemini"): nur diese Aktionen fuehrt die App ohne Tipp aus, und nur, wenn die Bruecke sie
     *  als "sofort" markiert hat und der Schalter "Harmloses sofort" an ist. Nie: Anruf, SMS, WhatsApp. */
    static final List<String> SOFORT = Arrays.asList("app", "wecker", "timer", "navigation", "einstellungen",
            "taschenlampe", "lautstaerke");

    /** Fuehrt eine Aktion aus. null = gestartet, sonst ein kurzer Fehlertext fuer die Karte. */
    static String ausfuehren(Activity c, JSONObject a) {
        String art = a.optString("art");
        try {
            if ("wecker".equals(art)) {
                Intent i = new Intent(AlarmClock.ACTION_SET_ALARM)
                        .putExtra(AlarmClock.EXTRA_HOUR, a.optInt("stunde"))
                        .putExtra(AlarmClock.EXTRA_MINUTES, a.optInt("minute"))
                        .putExtra(AlarmClock.EXTRA_SKIP_UI, true);
                if (!a.optString("text").isEmpty()) i.putExtra(AlarmClock.EXTRA_MESSAGE, a.optString("text"));
                JSONArray tage = a.optJSONArray("tage");
                if (tage != null && tage.length() > 0) {
                    ArrayList<Integer> t = new ArrayList<Integer>();
                    for (int k = 0; k < tage.length(); k++) t.add(wochentag(tage.optString(k)));
                    i.putExtra(AlarmClock.EXTRA_DAYS, t);
                }
                c.startActivity(i);
                return null;
            }
            if ("timer".equals(art)) {
                Intent i = new Intent(AlarmClock.ACTION_SET_TIMER)
                        .putExtra(AlarmClock.EXTRA_LENGTH, a.optInt("sekunden"))
                        .putExtra(AlarmClock.EXTRA_SKIP_UI, true);
                if (!a.optString("text").isEmpty()) i.putExtra(AlarmClock.EXTRA_MESSAGE, a.optString("text"));
                c.startActivity(i);
                return null;
            }
            if ("app".equals(art)) {
                Intent i = appStarten(c, a.optString("app"));
                if (i == null) return "App „" + a.optString("app") + "“ nicht gefunden.";
                c.startActivity(i);
                return null;
            }
            if ("anruf".equals(art)) {
                c.startActivity(new Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + Uri.encode(a.optString("nummer")))));
                return null;
            }
            if ("sms".equals(art)) {
                Intent i = new Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:" + Uri.encode(a.optString("nummer"))))
                        .putExtra("sms_body", a.optString("text"));
                c.startActivity(i);
                return null;
            }
            if ("whatsapp".equals(art)) {
                String nr = international(a.optString("nummer"));
                Intent i;
                if (!nr.isEmpty()) {
                    i = new Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/" + nr + "?text=" + Uri.encode(a.optString("text"))));
                } else {        // ohne Nummer: WhatsApp fragt selbst nach dem Kontakt, Text ist schon drin
                    i = new Intent(Intent.ACTION_SEND).setType("text/plain").setPackage("com.whatsapp")
                            .putExtra(Intent.EXTRA_TEXT, a.optString("text"));
                }
                try {
                    c.startActivity(i);
                } catch (ActivityNotFoundException e) {
                    if (!nr.isEmpty()) throw e;
                    c.startActivity(i.setPackage("com.whatsapp.w4b"));       // WhatsApp Business
                }
                return null;
            }
            if ("navigation".equals(art)) {
                String ziel = a.optString("ziel"), modus = a.optString("modus", "d");
                Intent i = "transit".equals(modus)
                        ? new Intent(Intent.ACTION_VIEW, Uri.parse("https://www.google.com/maps/dir/?api=1&travelmode=transit&destination="
                        + Uri.encode(ziel)))
                        : new Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=" + Uri.encode(ziel) + "&mode=" + modus));
                try {
                    c.startActivity(i);
                } catch (ActivityNotFoundException e) {
                    c.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("geo:0,0?q=" + Uri.encode(ziel))));
                }
                return null;
            }
            if ("taschenlampe".equals(art)) {           // seit 03.11.2026; setTorchMode braucht keine Kamera-Freigabe
                try {
                    android.hardware.camera2.CameraManager cm =
                            (android.hardware.camera2.CameraManager) c.getSystemService(Context.CAMERA_SERVICE);
                    for (String id : cm.getCameraIdList()) {
                        Boolean blitz = cm.getCameraCharacteristics(id)
                                .get(android.hardware.camera2.CameraCharacteristics.FLASH_INFO_AVAILABLE);
                        if (blitz != null && blitz) {
                            cm.setTorchMode(id, a.optBoolean("an"));
                            return null;
                        }
                    }
                    return "Dieses Handy hat keine Taschenlampe.";
                } catch (Exception e) {
                    return "Die Taschenlampe ist gerade belegt (Kamera offen?).";
                }
            }
            if ("lautstaerke".equals(art)) {            // seit 03.11.2026: Medienlautstaerke (Musik, Videos, Jarvis)
                android.media.AudioManager am = (android.media.AudioManager) c.getSystemService(Context.AUDIO_SERVICE);
                int st = android.media.AudioManager.STREAM_MUSIC, zeigen = android.media.AudioManager.FLAG_SHOW_UI;
                if (a.has("prozent")) {
                    am.setStreamVolume(st, Math.round(am.getStreamMaxVolume(st) * a.optInt("prozent") / 100f), zeigen);
                    return null;
                }
                String m = a.optString("modus");
                int richtung = "lauter".equals(m) ? android.media.AudioManager.ADJUST_RAISE
                        : "leiser".equals(m) ? android.media.AudioManager.ADJUST_LOWER
                        : "stumm".equals(m) ? android.media.AudioManager.ADJUST_MUTE : android.media.AudioManager.ADJUST_UNMUTE;
                am.adjustStreamVolume(st, richtung, zeigen);
                if (richtung == android.media.AudioManager.ADJUST_RAISE || richtung == android.media.AudioManager.ADJUST_LOWER)
                    am.adjustStreamVolume(st, richtung, 0);         // zwei Stufen, eine allein hoert man kaum
                return null;
            }
            if ("einstellungen".equals(art)) {
                try {
                    c.startActivity(new Intent(einstellung(a.optString("seite"))));
                } catch (ActivityNotFoundException e) {
                    c.startActivity(new Intent(Settings.ACTION_SETTINGS));
                }
                return null;
            }
            return "Unbekannte Aktion.";
        } catch (ActivityNotFoundException e) {
            return "Dafür ist auf diesem Handy keine App da.";
        } catch (SecurityException e) {
            return "Android hat das abgelehnt.";
        }
    }

    static int wochentag(String t) {
        if ("mo".equals(t)) return Calendar.MONDAY;
        if ("di".equals(t)) return Calendar.TUESDAY;
        if ("mi".equals(t)) return Calendar.WEDNESDAY;
        if ("do".equals(t)) return Calendar.THURSDAY;
        if ("fr".equals(t)) return Calendar.FRIDAY;
        if ("sa".equals(t)) return Calendar.SATURDAY;
        return Calendar.SUNDAY;
    }

    /** wa.me will die Nummer international ohne + und 00; eine deutsche 0 am Anfang wird zu 49 (Annahme: Inland). */
    static String international(String n) {
        n = n == null ? "" : n.replaceAll("[^0-9+]", "");
        if (n.startsWith("+")) return n.substring(1);
        if (n.startsWith("00")) return n.substring(2);
        if (n.startsWith("0")) return "49" + n.substring(1);
        return n;
    }

    static String einstellung(String seite) {
        if ("wlan".equals(seite)) return Settings.ACTION_WIFI_SETTINGS;
        if ("bluetooth".equals(seite)) return Settings.ACTION_BLUETOOTH_SETTINGS;
        if ("ton".equals(seite)) return Settings.ACTION_SOUND_SETTINGS;
        if ("akku".equals(seite)) return Intent.ACTION_POWER_USAGE_SUMMARY;
        if ("display".equals(seite)) return Settings.ACTION_DISPLAY_SETTINGS;
        if ("standort".equals(seite)) return Settings.ACTION_LOCATION_SOURCE_SETTINGS;
        if ("benachrichtigungen".equals(seite)) return "android.settings.ALL_APPS_NOTIFICATION_SETTINGS";
        if ("nicht_stoeren".equals(seite)) return "android.settings.ZEN_MODE_SETTINGS";
        if ("datum".equals(seite)) return Settings.ACTION_DATE_SETTINGS;
        if ("sprache".equals(seite)) return Settings.ACTION_LOCALE_SETTINGS;
        if ("speicher".equals(seite)) return Settings.ACTION_INTERNAL_STORAGE_SETTINGS;
        if ("apps".equals(seite)) return Settings.ACTION_APPLICATION_SETTINGS;
        if ("datennutzung".equals(seite)) return Settings.ACTION_DATA_USAGE_SETTINGS;
        return Settings.ACTION_SETTINGS;
    }

    /** Woerter zum Vergleichen (seit 03.11.2026): ohne Akzente und Satzzeichen, ohne Fuellwoerter wie "App", "die",
     *  "mein". "Die DM-App" und "Mein dm" werden beide zu [dm]. */
    static List<String> woerter(String s) {
        String n = java.text.Normalizer.normalize(s == null ? "" : s, java.text.Normalizer.Form.NFD)
                .replaceAll("\\p{M}", "").toLowerCase(Locale.ROOT).replace("ß", "ss");
        List<String> w = new ArrayList<String>();
        for (String t : n.split("[^a-z0-9]+")) {
            if (t.isEmpty() || Arrays.asList("die", "der", "das", "meine", "meinen", "mein", "my", "the", "app", "apps",
                    "oeffne", "starte").contains(t)) continue;
            w.add(t);
        }
        return w;
    }

    /** Ein Wort aus dem Namen (Fuellwoerter weg); ist sonst nichts uebrig, der ganze Name klein ohne Leerraum. */
    static String kompakt(String s) {
        StringBuilder b = new StringBuilder();
        for (String t : woerter(s)) b.append(t);
        return b.length() > 0 ? b.toString() : (s == null ? "" : s.replaceAll("\\s+", "").toLowerCase(Locale.ROOT));
    }

    /** Aehnlichkeit 0..1 nach Levenshtein, fuer Tipp- und Hoerfehler ("Spotifei"). */
    static double aehnlich(String a, String b) {
        int[] v = new int[b.length() + 1];
        for (int j = 0; j <= b.length(); j++) v[j] = j;
        for (int i = 1; i <= a.length(); i++) {
            int links = i, diag = i - 1;
            v[0] = i;
            for (int j = 1; j <= b.length(); j++) {
                int oben = v[j];
                links = Math.min(Math.min(oben + 1, links + 1), diag + (a.charAt(i - 1) == b.charAt(j - 1) ? 0 : 1));
                diag = oben;
                v[j] = links;
            }
        }
        int m = Math.max(a.length(), b.length());
        return m == 0 ? 0 : 1.0 - (double) v[b.length()] / m;
    }

    /** Guete eines Treffers fuer den gesagten Namen: 10 gleicher Name, 9 Paketname endet so, 6.5 alle gesagten Woerter
     *  stehen in Name oder Paketname (Google Maps -> com.google.android.apps.maps), 4..6 Name enthaelt bzw. ist enthalten
     *  (je mehr Ueberdeckung, desto besser), 3 im Paketnamen, 1..2 sehr aehnlich. 0 = kein Treffer. */
    static final List<String> PAKET_ALLGEMEIN = Arrays.asList("com", "de", "org", "net", "android", "apps", "app",
            "mobile", "client", "release");

    static double guete(String label, String paket, String name) {
        String n = kompakt(name), l = kompakt(label), p = paket == null ? "" : paket.toLowerCase(Locale.ROOT);
        String letzt = p.substring(p.lastIndexOf('.') + 1);
        if (n.isEmpty()) return 0;
        if (l.equals(n)) return 10;
        if (letzt.equals(n)) return 9;
        List<String> sw = woerter(name), lw = woerter(label), pw = new ArrayList<>(Arrays.asList(p.split("\\.")));
        pw.removeAll(PAKET_ALLGEMEIN);    // "android" steckt in fast jedem Paketnamen (Pruefung 03.11., Befund 9)
        int treffer = 0;
        for (String t : sw) if (lw.contains(t) || pw.contains(t) || (t.length() >= 3 && l.contains(t))) treffer++;
        double anteil = sw.isEmpty() ? 0 : (double) treffer / sw.size(), g = anteil >= 1 ? 6.5 : anteil * 5;
        if (n.length() >= 3 && l.length() >= 3 && (l.contains(n) || n.contains(l)))
            g = Math.max(g, 4 + 2.0 * Math.min(l.length(), n.length()) / Math.max(l.length(), n.length()));
        if (g < 3 && n.length() >= 3 && p.replace(".", "").contains(n)) g = 3;
        if (g < 1) {
            double ae = aehnlich(l, n);
            if (ae >= 0.75) g = 1 + ae;
        }
        return g;
    }

    /** Ab dieser Guete oeffnet "Harmloses sofort" eine App ohne Tipp; darunter (nur Paketname oder bloss aehnlich)
     *  bleibt die Karte stehen (Pruefung 03.11., Befund 9: "Android Auto" haette irgendeine Google-App geoeffnet). */
    static final double SOFORT_MIN_GUETE = 4;

    /** Beste Guete unter den startbaren Apps fuer diesen Namen (0 = nichts). */
    static double besteGuete(Context c, String name) {
        PackageManager pm = c.getPackageManager();
        double best = 0;
        for (ResolveInfo r : pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0)) {
            if (r.activityInfo == null || c.getPackageName().equals(r.activityInfo.packageName)) continue;
            best = Math.max(best, guete(String.valueOf(r.loadLabel(pm)), r.activityInfo.packageName, name));
        }
        return best;
    }

    /** Startbare App nach Namen, seit 03.11.2026 tolerant (kompakt, Paketname, Aehnlichkeit). Braucht die
     *  <queries>-Angabe fuer MAIN/LAUNCHER im Manifest (Android 11+). */
    static Intent appStarten(Context c, String name) {
        PackageManager pm = c.getPackageManager();
        Intent start = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        List<ResolveInfo> alle = pm.queryIntentActivities(start, 0);
        ResolveInfo treffer = null;
        double guete = 0;
        for (ResolveInfo r : alle) {
            if (r.activityInfo == null || c.getPackageName().equals(r.activityInfo.packageName)) continue;
            double g = guete(String.valueOf(r.loadLabel(pm)), r.activityInfo.packageName, name);
            if (g > guete) {
                guete = g;
                treffer = r;
            }
        }
        if (treffer == null) return null;
        return new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
                .setClassName(treffer.activityInfo.packageName, treffer.activityInfo.name)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    }

    /** Paketname der App, die appStarten oeffnen wuerde (fuer die Sperrliste der Stufe 2), sonst "". */
    static String paketFuer(Context c, String name) {
        Intent i = appStarten(c, name);
        return i == null || i.getComponent() == null ? "" : i.getComponent().getPackageName();
    }
}
