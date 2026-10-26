package de.homelab.jarvis;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * Seit 4.3: Ablage fuer "Foto aufnehmen". Die Kamera-App schreibt das Foto in voller Aufloesung hierher (ohne
 * EXTRA_OUTPUT gaebe sie nur ein kleines Vorschaubild zurueck, zu klein fuer Text auf einem Zettel), danach liest die
 * WebView es wie eine ausgewaehlte Datei. Genau eine Datei im Cache-Ordner, nie etwas anderes; nicht exportiert, die
 * Kamera bekommt nur fuer diesen einen Aufruf Schreibrecht (FLAG_GRANT_WRITE_URI_PERMISSION). Eigene kleine Klasse,
 * weil die App ohne AndroidX (FileProvider) gebaut wird.
 */
public class KameraAblage extends ContentProvider {
    static final String DATEI = "kamera.jpg";

    static Uri adresse(String paket) {
        return Uri.parse("content://" + paket + ".kamera/" + DATEI);
    }

    File datei() {
        return new File(getContext().getCacheDir(), DATEI);
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String modus) throws FileNotFoundException {
        if (!DATEI.equals(uri.getLastPathSegment())) throw new FileNotFoundException(uri.toString());
        return ParcelFileDescriptor.open(datei(), ParcelFileDescriptor.parseMode(modus));
    }

    @Override
    public String getType(Uri uri) {
        return "image/jpeg";
    }

    @Override
    public Cursor query(Uri uri, String[] spalten, String auswahl, String[] werte, String sortierung) {
        if (!DATEI.equals(uri.getLastPathSegment())) return null;
        MatrixCursor c = new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
        File f = datei();
        String name = "Foto-" + new java.text.SimpleDateFormat("yyyy-MM-dd-HHmm", java.util.Locale.ROOT)
                .format(new java.util.Date(f.lastModified())) + ".jpg";
        c.addRow(new Object[]{name, f.length()});
        return c;
    }

    @Override
    public Uri insert(Uri uri, ContentValues werte) {
        return null;
    }

    @Override
    public int delete(Uri uri, String auswahl, String[] werte) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues werte, String auswahl, String[] auswahlWerte) {
        return 0;
    }
}
