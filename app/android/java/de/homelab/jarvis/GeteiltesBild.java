package de.homelab.jarvis;

import android.content.ContentResolver;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.ImageDecoder;
import android.graphics.Matrix;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Build;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * Teilen an Jarvis (seit 4.15, A1): ein geteiltes Bild so aufbereiten, wie app.html es mit einer gewaehlten Datei tut
 * (laengste Kante 1568, JPEG 85, weisser Grund statt Transparenz, Drehung laut EXIF). Java statt Seite, weil die Seite
 * sonst das ganze Foto (oft 5-10 MB) als Base64 durch evaluateJavascript bekaeme; so sind es einige hundert KB.
 * Eigene Klasse, damit ImageDecoder (Android 9) nur hier steht und Android 8 die MainActivity ohne ihn laedt.
 */
final class GeteiltesBild {
    private GeteiltesBild() {
    }

    static Bitmap laden(ContentResolver cr, Uri u) throws IOException {
        if (Build.VERSION.SDK_INT >= 28) return Neu.laden(cr, u);
        // Android 8: Groesse lesen, grob (Zweierpotenz) dekodieren, dann genau verkleinern und nach EXIF drehen
        BitmapFactory.Options o = new BitmapFactory.Options();
        o.inJustDecodeBounds = true;
        try (InputStream in = cr.openInputStream(u)) {
            if (in == null) throw new IOException("Bild nicht lesbar");
            BitmapFactory.decodeStream(in, null, o);
        }
        o.inSampleSize = TeilenRegeln.stichprobe(o.outWidth, o.outHeight, TeilenRegeln.BILD_KANTE);
        o.inJustDecodeBounds = false;
        Bitmap b;
        try (InputStream in = cr.openInputStream(u)) {
            b = in == null ? null : BitmapFactory.decodeStream(in, null, o);
        }
        if (b == null) throw new IOException("Bild nicht lesbar");
        int grad = 0;
        try (InputStream in = cr.openInputStream(u)) {
            if (in != null) {
                int r = new ExifInterface(in).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL);
                grad = r == ExifInterface.ORIENTATION_ROTATE_90 ? 90 : r == ExifInterface.ORIENTATION_ROTATE_180 ? 180
                        : r == ExifInterface.ORIENTATION_ROTATE_270 ? 270 : 0;
            }
        } catch (Exception ignored) {          // kein EXIF (PNG, WebP): dann eben nicht drehen
        }
        int[] z = TeilenRegeln.zielGroesse(b.getWidth(), b.getHeight(), TeilenRegeln.BILD_KANTE);
        Matrix m = new Matrix();
        m.postScale(z[0] / (float) b.getWidth(), z[1] / (float) b.getHeight());
        if (grad != 0) m.postRotate(grad);
        Bitmap aus = Bitmap.createBitmap(b, 0, 0, b.getWidth(), b.getHeight(), m, true);
        if (aus != b) b.recycle();
        return aus;
    }

    /** JPEG 85 wie in app.html; Transparenz wird weiss (JPEG kennt keine, sonst waere sie schwarz). */
    static byte[] alsJpeg(Bitmap b) {
        Bitmap q = b;
        if (b.hasAlpha()) {
            q = Bitmap.createBitmap(b.getWidth(), b.getHeight(), Bitmap.Config.ARGB_8888);
            Canvas c = new Canvas(q);
            c.drawColor(Color.WHITE);
            c.drawBitmap(b, 0, 0, null);
        }
        ByteArrayOutputStream o = new ByteArrayOutputStream();
        q.compress(Bitmap.CompressFormat.JPEG, 85, o);
        if (q != b) q.recycle();
        b.recycle();
        return o.toByteArray();
    }

    /** Android 9+: ImageDecoder verkleinert schon beim Dekodieren und beachtet die EXIF-Drehung selbst. */
    static final class Neu {
        private Neu() {
        }

        static Bitmap laden(ContentResolver cr, Uri u) throws IOException {
            return ImageDecoder.decodeBitmap(ImageDecoder.createSource(cr, u), new ImageDecoder.OnHeaderDecodedListener() {
                public void onHeaderDecoded(ImageDecoder d, ImageDecoder.ImageInfo info, ImageDecoder.Source s) {
                    int[] z = TeilenRegeln.zielGroesse(info.getSize().getWidth(), info.getSize().getHeight(), TeilenRegeln.BILD_KANTE);
                    if (z[0] > 0 && z[1] > 0) d.setTargetSize(z[0], z[1]);
                    d.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE);     // Bitmap.compress braucht ein Software-Bitmap
                }
            });
        }
    }
}
