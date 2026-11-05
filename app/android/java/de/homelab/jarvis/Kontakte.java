package de.homelab.jarvis;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.provider.ContactsContract;

import java.util.ArrayList;

/**
 * Telefonbuch-Suche fuer "Ruf Anna an" und WhatsApp an einen Kontakt (seit 30.10.2026). Das Telefonbuch bleibt auf
 * dem Handy: Gesucht wird hier, das Ergebnis (Name, Art, Nummer) zeigt nur die Karte in der App; zur Bruecke geht nichts
 * davon. Auswahl- und Sperrregeln stehen in BedienRegeln (kontaktWahl, nummerWahl, nummerGesperrt) und sind dort ohne
 * Android getestet. Keine Lambdas (Bau ohne Gradle).
 */
final class Kontakte {
    private Kontakte() {
    }

    static final class Treffer {
        String name = "", nummer = "", art = "", fehler = null;
    }

    static boolean erlaubt(Context c) {
        return c.checkSelfPermission(Manifest.permission.READ_CONTACTS) == PackageManager.PERMISSION_GRANTED;
    }

    /** Genau ein Kontakt mit genau einer gewaehlten Nummer, sonst ein Fehlertext (nie raten). */
    static Treffer suchen(Context c, String gesucht) {
        Treffer t = new Treffer();
        if (!erlaubt(c)) {
            t.fehler = "Jarvis darf die Kontakte noch nicht lesen. Bitte erlauben und nochmal fragen.";
            return t;
        }
        ArrayList<Long> ids = new ArrayList<Long>();
        ArrayList<String> namen = new ArrayList<String>();
        ArrayList<long[]> zeilenId = new ArrayList<long[]>();
        ArrayList<String> nummern = new ArrayList<String>();
        ArrayList<Integer> typen = new ArrayList<Integer>();
        ArrayList<Boolean> haupt = new ArrayList<Boolean>();
        ArrayList<String> labels = new ArrayList<String>();
        Cursor cur = null;
        try {
            cur = c.getContentResolver().query(ContactsContract.CommonDataKinds.Phone.CONTENT_URI, new String[]{
                    ContactsContract.CommonDataKinds.Phone.CONTACT_ID, ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                    ContactsContract.CommonDataKinds.Phone.NUMBER, ContactsContract.CommonDataKinds.Phone.TYPE,
                    ContactsContract.CommonDataKinds.Phone.LABEL, ContactsContract.CommonDataKinds.Phone.IS_SUPER_PRIMARY},
                    null, null, null);
            while (cur != null && cur.moveToNext()) {
                long id = cur.getLong(0);
                if (!ids.contains(id)) {
                    ids.add(id);
                    namen.add(cur.getString(1) == null ? "" : cur.getString(1));
                }
                zeilenId.add(new long[]{id});
                nummern.add(cur.getString(2) == null ? "" : cur.getString(2));
                typen.add(cur.getInt(3));
                labels.add(String.valueOf(ContactsContract.CommonDataKinds.Phone.getTypeLabel(c.getResources(), cur.getInt(3),
                        cur.getString(4))));
                haupt.add(cur.getInt(5) != 0);
            }
        } catch (RuntimeException e) {
            t.fehler = "Das Telefonbuch ließ sich nicht lesen.";
            return t;
        } finally {
            if (cur != null) cur.close();
        }
        int k = BedienRegeln.kontaktWahl(namen.toArray(new String[0]), gesucht);
        if (k == -1) {
            t.fehler = "Keinen Kontakt „" + gesucht + "“ gefunden.";
            return t;
        }
        if (k == -2) {
            t.fehler = "Mehrere Kontakte passen zu „" + gesucht + "“. Sag bitte den ganzen Namen.";
            return t;
        }
        long id = ids.get(k);
        ArrayList<Integer> zeilen = new ArrayList<Integer>();
        ArrayList<String> gesehen = new ArrayList<String>();       // dieselbe Nummer aus zwei Rohkontakten nur einmal
        for (int i = 0; i < zeilenId.size(); i++) {
            if (zeilenId.get(i)[0] != id) continue;
            String norm = BedienRegeln.nummerNorm(nummern.get(i));
            if (gesehen.contains(norm)) continue;
            gesehen.add(norm);
            zeilen.add(i);
        }
        int[] ty = new int[zeilen.size()];
        boolean[] ha = new boolean[zeilen.size()];
        for (int i = 0; i < zeilen.size(); i++) {
            ty[i] = typen.get(zeilen.get(i));
            ha[i] = haupt.get(zeilen.get(i));
        }
        int n = BedienRegeln.nummerWahl(ty, ha);
        if (n < 0) {
            t.fehler = n == -1 ? "Der Kontakt hat keine Nummer." : "Der Kontakt hat mehrere Nummern. Sag bitte, welche (Handy, privat …).";
            return t;
        }
        int z = zeilen.get(n);
        t.name = namen.get(k);
        t.nummer = nummern.get(z);
        t.art = labels.get(z);
        if (!BedienRegeln.kontaktNummerErlaubt(t.nummer)) {
            t.fehler = "Diese Nummer (Mehrwert, Kurzwahl o. ä.) wählt Jarvis nicht.";
        }
        return t;
    }
}
