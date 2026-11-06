package de.homelab.jarvis;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;

/**
 * Teilen an Jarvis (seit 4.15, Ideen-Paket 05.11.2026, A1). Nimmt ACTION_SEND (text/plain, image/*) aus dem
 * Teilen-Menue anderer Apps an und reicht es an die eine MainActivity in Jarvis' eigener Aufgabe weiter (laeuft sie schon,
 * per onNewIntent). Direkt auf der MainActivity entstuende sonst eine zweite Jarvis-Instanz in der Aufgabe der teilenden
 * App (launchMode singleTop). Ohne Oberflaeche (Theme.NoDisplay), beendet sich sofort.
 * Gesendet wird hier nichts: die App legt Text und Bild nur bereit, abschicken muss die Person selbst.
 * Bilder nur als content:// eines fremden Anbieters; das Leserecht der teilenden App wird an die MainActivity
 * weitergegeben (FLAG_GRANT_READ_URI_PERMISSION). Laesst es sich nicht weitergeben, kommt nur der Text an.
 */
public class TeilenEmpfang extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        try {
            weiterreichen(getIntent());
        } catch (RuntimeException ignored) {
            // kaputte Extras einer fremden App (BadParcelableException u. a.): dann eben nichts
        }
        finish();
    }

    void weiterreichen(Intent ein) {
        if (ein == null || !Intent.ACTION_SEND.equals(ein.getAction())) return;
        Intent weiter = new Intent(this, MainActivity.class).setAction(MainActivity.TEILEN_AKTION)
                .putExtra("intern", MainActivity.INTERN)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        CharSequence text = ein.getCharSequenceExtra(Intent.EXTRA_TEXT);
        CharSequence betreff = ein.getCharSequenceExtra(Intent.EXTRA_SUBJECT);
        if (text != null) weiter.putExtra("text", TeilenRegeln.kappen(text.toString(), 4 * TeilenRegeln.TEXT_MAX));
        if (betreff != null) weiter.putExtra("betreff", TeilenRegeln.kappen(betreff.toString(), 300));
        String typ = ein.getType();
        Uri bild = null;
        if (typ != null && typ.startsWith("image/")) {
            Object o = ein.getParcelableExtra(Intent.EXTRA_STREAM);
            if (o instanceof Uri) bild = (Uri) o;
            ClipData c = ein.getClipData();
            if (bild == null && c != null && c.getItemCount() > 0) bild = c.getItemAt(0).getUri();
        }
        if (bild != null) {
            if (TeilenRegeln.fremdeInhaltsAdresse(bild.getScheme(), bild.getAuthority(), getPackageName())) {
                Intent mitBild = new Intent(weiter).putExtra("bild", bild).putExtra("typ", typ)
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                mitBild.setClipData(ClipData.newRawUri("", bild));
                try {
                    startActivity(mitBild);
                    return;
                } catch (SecurityException e) {
                    // Leserecht laesst sich nicht weitergeben: unten ohne Bild, mit Hinweis
                }
            }
            weiter.putExtra("bild_fehlt", true);
        }
        startActivity(weiter);
    }
}
