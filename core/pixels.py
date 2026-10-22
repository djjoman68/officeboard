"""Drawing helpers. Every module draws a 64x32 Pillow image; the display copies it to the panel.

Drawing with Pillow (instead of straight onto the panel, as the plane tracker does) means the web UI
picture and the preview tool show exactly what the LEDs show, and modules can be tested on any
computer. Text uses the panel's own .bdf pixel fonts, read here directly.

The .bdf reader comes from itsposttime's utilities/idle_render.py. Modified for the office board.
"""
import os

from PIL import Image, ImageChops, ImageDraw

WIDTH, HEIGHT = 64, 32
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

# Short names for the fonts in fonts/
FONTS = {
    "tiny": "4x6.bdf",
    "small": "5x8.bdf",
    "regular": "6x13.bdf",
    "regular_bold": "6x13B.bdf",
    "regularplus": "7x13.bdf",
    "regularplus_bold": "7x13B.bdf",
    "large": "8x13.bdf",
    "large_bold": "8x13B.bdf",
}

WHITE = (255, 255, 255)
GRAY = (150, 150, 150)
DIM = (90, 90, 90)
BLACK = (0, 0, 0)
RED = (255, 30, 30)
GREEN = (0, 230, 60)
BLUE = (90, 150, 255)
YELLOW = (255, 200, 0)
ORANGE = (255, 120, 50)
CYAN = (0, 220, 220)
MAGENTA = (230, 0, 230)

_glyph_cache = {}


def blank():
    return Image.new("RGB", (WIDTH, HEIGHT), BLACK)


def _load_bdf(font):
    """{codepoint: (advance, (w, h, xoff, yoff), [(row_bits, n_bits), ...])}"""
    name = FONTS.get(font, font)
    if name in _glyph_cache:
        return _glyph_cache[name]
    glyphs, enc, adv, bbx, rows = {}, None, 0, None, None
    with open(os.path.join(FONT_DIR, name), encoding="latin-1") as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            key = parts[0]
            if rows is not None:
                if key == "ENDCHAR":
                    if enc is not None and enc >= 0 and bbx:
                        glyphs[enc] = (adv, bbx, rows)
                    rows = None
                else:
                    rows.append((int(key, 16), len(key) * 4))
            elif key == "ENCODING":
                enc = int(parts[1])
            elif key == "DWIDTH":
                adv = int(parts[1])
            elif key == "BBX":
                bbx = tuple(int(v) for v in parts[1:5])
            elif key == "BITMAP":
                rows = []
    _glyph_cache[name] = glyphs
    return glyphs


def _glyph(glyphs, ch):
    return glyphs.get(ord(ch)) or glyphs.get(0xFFFD) or glyphs.get(ord("?"))


def text_width(font, text):
    glyphs = _load_bdf(font)
    return sum(g[0] for g in (_glyph(glyphs, ch) for ch in text) if g)


def draw_text(img, font, x, y, color, text):
    """Same placement as the panel library's DrawText: y is the baseline. Returns the width drawn."""
    glyphs = _load_bdf(font)
    px = img.load()
    start = x
    for ch in text:
        g = _glyph(glyphs, ch)
        if g is None:
            continue
        adv, (w, h, xoff, yoff), rows = g
        top = y - h - yoff
        for r, (bits, n) in enumerate(rows):
            for c in range(w):
                if bits & (1 << (n - 1 - c)):
                    gx, gy = x + xoff + c, top + r
                    if 0 <= gx < img.width and 0 <= gy < img.height:
                        px[gx, gy] = color
        x += adv
    return x - start


def text_strip(font, pieces, height):
    """One long image of coloured text pieces [(text, colour), ...], for scrolling.
    The baseline sits so the font's capitals fill the strip."""
    width = max(1, sum(text_width(font, t) for t, _ in pieces))
    strip = Image.new("RGB", (width, height), BLACK)
    x, base = 0, height - 1 if height < 10 else height - 3
    for text, color in pieces:
        x += draw_text(strip, font, x, base, color, text)
    return strip


def marquee(img, strip, t, speed, y=0, x0=0, x1=WIDTH):
    """Scroll `strip` right to left through columns x0..x1 of `img`, `speed` pixels a second,
    `t` seconds after it started. It enters from the right edge and loops once fully gone."""
    span = x1 - x0
    offset = int(t * speed) % (strip.width + span)
    left = x0 + span - offset            # where the strip's first column is now
    src_l = max(0, x0 - left)
    src_r = min(strip.width, x1 - left)
    if src_r > src_l:
        img.paste(strip.crop((src_l, 0, src_r, strip.height)), (left + src_l, y))
    return img


def led_preview(img, dot=8):
    """Enlarge a 64x32 frame so it looks like the LED panel (round dots, unlit LEDs dark gray)."""
    big = img.convert("RGB").resize((img.width * dot, img.height * dot), Image.NEAREST)
    big = ImageChops.lighter(big, Image.new("RGB", big.size, (28, 28, 28)))
    return ImageChops.multiply(big, _dot_mask(img.width, img.height, dot))


_masks = {}


def _dot_mask(w, h, dot):
    key = (w, h, dot)
    if key not in _masks:
        cell = Image.new("RGB", (dot, dot), BLACK)
        ImageDraw.Draw(cell).ellipse([1, 1, dot - 2, dot - 2], fill=WHITE)
        mask = Image.new("RGB", (w * dot, h * dot), BLACK)
        for y in range(h):
            for x in range(w):
                mask.paste(cell, (x * dot, y * dot))
        _masks[key] = mask
    return _masks[key]
