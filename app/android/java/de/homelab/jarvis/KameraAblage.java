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
import java.util.List;

/**
 * Seit 4.3: Ablage fuer "Foto aufnehmen". Die Kamera-App schreibt das Foto in voller Aufloesung hierher (ohne
 * EXTRA_OUTPUT gaebe sie nur ein kleines Vorschaubild zurueck, zu klein fuer Text auf einem Zettel), danach liest die
 * WebView es wie eine ausgewaehlte Datei. Genau eine Datei im Cache-Ordner, nie etwas anderes; nicht exportiert, die
 * Kamera bekommt nur fuer diesen einen Aufruf Schreibrecht (FLAG_GRANT_WRITE_URI_PERMISSION). Eigene kleine Klasse,
 * weil die App ohne AndroidX (FileProvider) gebaut wird.
 */
public class KameraAblage extends ContentProvider {
    static final String DATEI = "kamera.jpg";

    /** Seit 4.4 (0.3.3): Dateien von Jarvis aus cache/ausgabe/<Kennung>/<Name>, nur lesend. */
    static Uri ausgabeAdresse(String paket, String kennung, String name) {
        return new Uri.Builder().scheme("content").authority(paket + ".kamera").appendPath("ausgabe")
                .appendPath(kennung).appendPath(name).build();
    }

    File ausgabeDatei(Uri uri) {
        List<String> t = uri.getPathSegments();
        if (t.size() != 3 || !"ausgabe".equals(t.get(0)) || !t.get(1).matches("a[0-9a-f]{24}")) return null;
        String name = t.get(2);
        if (name.contains("/") || name.contains("\\") || name.startsWith(".")) return null;
        File f = new File(new File(new File(getContext().getCacheDir(), "ausgabe"), t.get(1)), name);
        return f.isFile() ? f : null;
    }

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
        File aus = ausgabeDatei(uri);
        if (aus != null) {
            if (modus.contains("w")) throw new FileNotFoundException("nur lesen");
            return ParcelFileDescriptor.open(aus, ParcelFileDescriptor.MODE_READ_ONLY);
        }
        if (uri.getPathSegments().size() != 1 || !DATEI.equals(uri.getLastPathSegment())) throw new FileNotFoundException(uri.toString());
        return ParcelFileDescriptor.open(datei(), ParcelFileDescriptor.parseMode(modus));
    }

    @Override
    public String getType(Uri uri) {
        File aus = ausgabeDatei(uri);
        if (aus != null) {
            String n = aus.getName(), e = n.contains(".") ? n.substring(n.lastIndexOf('.') + 1).toLowerCase() : "";
            String t = android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(e);
            return t != null ? t : "application/octet-stream";
        }
        return "image/jpeg";
    }

    @Override
    public Cursor query(Uri uri, String[] spalten, String auswahl, String[] werte, String sortierung) {
        File aus = ausgabeDatei(uri);
        if (aus != null) {
            MatrixCursor c = new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
            c.addRow(new Object[]{aus.getName(), aus.length()});
            return c;
        }
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
