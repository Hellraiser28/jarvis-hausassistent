package de.homelab.jarvis;

/**
 * Sprech-Visualizer (seit 4.15, Ideen-Paket 05.11.2026, A4): Pegel aus der Wellenform, die android.media.audiofx.Visualizer
 * an der Wiedergabe liefert (8 Bit ohne Vorzeichen, Mitte 128). Der Visualizer laeuft im Modus "wie gespielt", der Wert
 * haengt also von der Medienlautstaerke ab; eine gleitende Spitze gleicht das aus, damit der Kranz bei leiser und lauter
 * Wiedergabe gleich deutlich pulsiert. Ohne Android, geprueft mit tools/app_regeln_test.sh. Keine Lambdas.
 */
final class StimmPegel {
    /** Die Spitze sinkt je Messwert um 1,5 % (bei 18 Werten/s nach gut 2 s auf die Haelfte). */
    static final double ABKLINGEN = 0.985;
    /** Untergrenze der Spitze: sehr leise Wiedergabe wird nicht beliebig hochgezogen (Rauschen bliebe Rauschen). */
    static final double BODEN = 0.04;
    /** Darunter gilt es als Stille (digitale Pausen der Stimme sind exakt 128). */
    static final double STILLE = 0.004;

    double spitze = 0;

    /** Effektivwert der Wellenform, 0..1 (1 = Vollaussteuerung). */
    static double rms(byte[] welle) {
        if (welle == null || welle.length == 0) return 0;
        double summe = 0;
        for (byte b : welle) {
            int v = (b & 0xff) - 128;
            summe += (double) v * v;
        }
        return Math.min(1.0, Math.sqrt(summe / welle.length) / 128.0);
    }

    /** Naechster Pegel 0..1 fuer die Oberflaeche: relativ zur gleitenden Spitze, mit Wurzel wie die Huelle in
     *  MainActivity.huelle (leise Silben bleiben sichtbar). */
    float naechster(byte[] welle) {
        double r = rms(welle);
        spitze = Math.max(r, spitze * ABKLINGEN);
        if (r < STILLE) return 0f;
        return (float) Math.min(1.0, Math.sqrt(r / Math.max(spitze, BODEN)));
    }
}
