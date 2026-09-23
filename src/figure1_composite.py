"""
Figure 1 for the Puʻuwaʻawaʻa SDM paper: study-area map (panel A) above three
site photographs (panels B to D), 170 mm wide at 600 dpi.

The map and photographs are not in this repository; contact the authors for
them. Expected files:
    Panel_A_final.pdf     map exported from GIS
    Picture1.png          B  fence line between paddocks
    DSCN1878 (1).JPG      C  cattle in nonnative grassland with rock walls
    DSCN1839.JPG          D  dry-stack lava rock paddock wall

Requires poppler (pdftoppm) and Pillow.

    python src/figure1_composite.py INPUT_DIR figures
"""
import os
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
os.makedirs(OUT, exist_ok=True)

DPI = 600
W = round(170 / 25.4 * DPI)          # page width in pixels
GAP = round(2 / 25.4 * DPI)          # 2 mm gutter
PHOTOS = [("Picture1.png", "B"), ("DSCN1878 (1).JPG", "C"), ("DSCN1839.JPG", "D")]
FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]

# Panel A: rasterize the vector map at high resolution, then fit to full width
tmp = os.path.join(OUT, "_panelA")
subprocess.run(["pdftoppm", "-r", "1200", "-png", "-singlefile",
                os.path.join(SRC, "Panel_A_final.pdf"), tmp], check=True)
m = Image.open(tmp + ".png").convert("RGB")
os.remove(tmp + ".png")
mh = round(W * m.height / m.width)
m = m.resize((W, mh), Image.LANCZOS)

pw = (W - 2 * GAP) // 3
ph = round(pw * 3 / 4)
canvas = Image.new("RGB", (W, mh + GAP + ph), "white")
canvas.paste(m, (0, 0))

font_path = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
font = ImageFont.truetype(font_path, round(pw * 0.075)) if font_path else ImageFont.load_default()

x = 0
for fname, label in PHOTOS:
    im = Image.open(os.path.join(SRC, fname)).convert("RGB")
    r = im.width / im.height                     # centre-crop to 4:3
    if r > 4 / 3:
        nw = round(im.height * 4 / 3)
        im = im.crop(((im.width - nw) // 2, 0, (im.width - nw) // 2 + nw, im.height))
    elif r < 4 / 3:
        nh = round(im.width * 3 / 4)
        im = im.crop((0, (im.height - nh) // 2, im.width, (im.height - nh) // 2 + nh))
    im = im.resize((pw, ph), Image.LANCZOS)
    dr = ImageDraw.Draw(im)
    pad = round(pw * 0.02)
    bb = dr.textbbox((0, 0), label, font=font)
    dr.rectangle((pad, pad, pad + bb[2] - bb[0] + 2 * pad, pad + bb[3] - bb[1] + 2 * pad), fill="white")
    dr.text((2 * pad - bb[0], 2 * pad - bb[1]), label, font=font, fill="black")
    canvas.paste(im, (x, mh + GAP))
    x += pw + GAP

canvas.save(os.path.join(OUT, "Figure_1_map_photos.tif"), dpi=(DPI, DPI), compression="tiff_lzw")
canvas.save(os.path.join(OUT, "Figure_1_map_photos.pdf"), resolution=DPI)
print("wrote Figure_1_map_photos (.tif, .pdf)")
