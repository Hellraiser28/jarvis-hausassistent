package de.homelab.jarvis;

import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

/**
 * Schnelleinstellungs-Kachel "Jarvis" (seit 4.15, Ideen-Paket 05.11.2026, A2): Antippen oeffnet die App, die sofort
 * zuhoert wie nach einem Tipp aufs Mikrofon (MainActivity.ZUHOEREN_AKTION, die Seite entscheidet ueber onKachel).
 * Bei gesperrtem Handy erst entsperren (kein Mikrofon vom Sperrbildschirm aus). Ab Android 14 verlangt
 * startActivityAndCollapse einen PendingIntent, darunter geht der Intent. Keine Lambdas (Bau ohne Gradle).
 */
public class JarvisKachel extends TileService {
    @Override
    public void onStartListening() {
        Tile t = getQsTile();
        if (t == null) return;
        t.setState(Tile.STATE_INACTIVE);       // kein Schalter, nur ein Startknopf
        t.setLabel("Jarvis");
        t.updateTile();
    }

    @Override
    public void onClick() {
        if (isLocked()) {
            unlockAndRun(new Runnable() {
                public void run() {
                    oeffnen();
                }
            });
        } else {
            oeffnen();
        }
    }

    void oeffnen() {
        Intent i = new Intent(this, MainActivity.class).setAction(MainActivity.ZUHOEREN_AKTION)
                .putExtra("intern", MainActivity.INTERN)             // nur die Kachel darf das Zuhoeren ausloesen
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (Build.VERSION.SDK_INT >= 34) {
            startActivityAndCollapse(PendingIntent.getActivity(this, 11, i,
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        } else {
            startActivityAndCollapse(i);
        }
    }
}
