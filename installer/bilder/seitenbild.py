"""Seitenbild für Willkommens- und Abschlussseite des Setups (NSIS/MUI2: 164 x 314 px, 24-Bit-BMP).
Dunkler Grund, Reaktor aus jarvis.png (symbol.py des PC-Clients), Schriftzug darunter. Seit 24.10.2026 in den
Farben des Standard-Designs (Rot-Gold), vorher Cyan. Erzeugen: python3 seitenbild.py <jarvis.png> <ziel.bmp>
(braucht Pillow; das Bauskript ruft es nicht auf, die fertige BMP liegt im Repo)."""
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

B, H = 164, 314
ROT, GOLD = (255, 45, 61), (255, 194, 74)      # wie html.rot im HUD und das Symbol
GRUND, RASTER = (7, 2, 6), (40, 8, 14)
S = 4                                         # erst groß zeichnen, dann verkleinern (glatte Kanten)
bild = Image.new("RGB", (B * S, H * S), GRUND)
d = ImageDraw.Draw(bild)
for y in range(H * S):                        # leichter Verlauf nach unten
    t = y / (H * S)
    d.line([(0, y), (B * S, y)], fill=(int(7 + 22 * t), int(2 + 3 * t), int(6 + 8 * t)))
for x in range(0, B * S, 12 * S):             # feines HUD-Raster
    d.line([(x, 0), (x, H * S)], fill=RASTER)
for y in range(0, H * S, 12 * S):
    d.line([(0, y), (B * S, y)], fill=RASTER)

reaktor = Image.open(sys.argv[1]).convert("RGBA").resize((120 * S, 120 * S), Image.LANCZOS)
schein = Image.new("RGBA", bild.size, (0, 0, 0, 0))
ImageDraw.Draw(schein).ellipse([(B * S - 150 * S) // 2, 40 * S, (B * S + 150 * S) // 2, 190 * S], fill=ROT + (70,))
schein = schein.filter(ImageFilter.GaussianBlur(14 * S))
bild = Image.alpha_composite(bild.convert("RGBA"), schein)
bild.alpha_composite(reaktor, ((B * S - 120 * S) // 2, 55 * S))

d = ImageDraw.Draw(bild)
try:
    schrift = ImageFont.truetype("DejaVuSans-Bold.ttf", 15 * S)
    klein = ImageFont.truetype("DejaVuSans.ttf", 9 * S)
except OSError:
    schrift = klein = ImageFont.load_default()
# Seit 0.3.0 zweisprachig (das Bild gilt fuer beide Sprachen des Setups)
for text, f, y, farbe in (("J.A.R.V.I.S.", schrift, 205, GOLD), ("Hausassistent", klein, 228, ROT), ("Home assistant", klein, 241, ROT)):
    w = d.textlength(text, font=f)
    d.text(((B * S - w) / 2, y * S), text, font=f, fill=farbe)
d.line([(30 * S, 261 * S), (B * S - 30 * S, 261 * S)], fill=ROT, width=S)

bild.convert("RGB").resize((B, H), Image.LANCZOS).save(sys.argv[2], "BMP")
print("ok")
