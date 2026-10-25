"""QR-Code fuer die Setup-Seite "Jarvis aufs Handy" (seit 25.10.2026): fester Link auf die App im neuesten GitHub-Release.
Erzeugen: python3 app_qr.py <adresse> <ziel.bmp>   (braucht qrcode und Pillow; bauen.sh ruft es in einem Container auf)
Dunkle Module auf Weiss, damit jede Handykamera ihn liest, 24-Bit-BMP fuer NSIS."""
import sys

import qrcode

adresse, ziel = sys.argv[1], sys.argv[2]
q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=3)
q.add_data(adresse)
q.make(fit=True)
q.make_image(fill_color="black", back_color="white").convert("RGB").save(ziel, "BMP")
print("QR:", ziel, q.version, adresse)
