"""Draws the race screens for a 64x32 RGB LED panel.
From itsposttime's utilities/race_render.py. Modified for the office board: unchanged so far.

Everything is drawn onto a 64x32 Pillow image. On the Pi that image goes
straight to the panel with matrix.SetImage(); here it can also be saved
as an enlarged LED-style preview, so what you see is what the panel shows.
"""
from datetime import datetime

from PIL import Image, ImageDraw

W, H = 64, 32

# Colors
WHITE = (255, 255, 255)
YELLOW = (255, 200, 0)
RED = (255, 30, 30)
GREEN = (0, 230, 60)
BLUE = (90, 150, 255)    # program numbers
DIM = (90, 90, 90)       # scratches, labels
BROWN = (180, 100, 40)   # dirt
GRAY = (150, 150, 150)   # time of day on the Big MTP view
BLACK = (0, 0, 0)

# Compact 3x5 pixel font (custom, so preview and panel match exactly)
GLYPHS = {
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
    "/": ["001", "001", "010", "100", "100"], ".": ["0", "0", "0", "0", "1"],
    "-": ["000", "000", "111", "000", "000"], " ": ["0", "0", "0", "0", "0"],
    "A": ["010", "101", "111", "101", "101"], "B": ["110", "101", "110", "101", "110"],
    "C": ["011", "100", "100", "100", "011"], "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"], "F": ["111", "100", "110", "100", "100"],
    "M": ["10001", "11011", "10101", "10001", "10001"], "P": ["110", "101", "110", "100", "100"],
    "R": ["110", "101", "110", "101", "101"], "S": ["011", "100", "010", "001", "110"],
    "T": ["111", "010", "010", "010", "010"], "U": ["101", "101", "101", "101", "111"],
    "W": ["10001", "10001", "10101", "11011", "10001"],
    # Track names and "TODAY" on the card screen. O is rounded so it doesn't read as 0.
    "G": ["011", "100", "101", "101", "011"], "L": ["100", "100", "100", "100", "111"],
    "N": ["1001", "1101", "1011", "1001", "1001"], "O": ["010", "101", "101", "101", "010"],
    "Y": ["101", "101", "010", "010", "010"], ":": ["0", "1", "0", "1", "0"],
    # Rest of the alphabet, so any Pick 5 name NYRA uses can be drawn
    "H": ["101", "101", "111", "101", "101"], "I": ["111", "010", "010", "010", "111"],
    "J": ["001", "001", "001", "101", "010"], "K": ["101", "101", "110", "101", "101"],
    "Q": ["010", "101", "101", "110", "011"], "V": ["101", "101", "101", "101", "010"],
    "X": ["101", "101", "010", "101", "101"], "Z": ["111", "001", "010", "100", "111"],
    # Small lowercase a/p after post times on the card screen (1:10p)
    "a": ["000", "011", "101", "101", "011"], "p": ["000", "110", "101", "110", "100"],
}


# Standard US saddle cloth colors: program number -> (background, number color)
SADDLE = {
    1: ((220, 0, 0), WHITE),        2: ((255, 255, 255), BLACK),
    3: ((0, 60, 255), WHITE),       4: ((255, 220, 0), BLACK),
    5: ((0, 150, 40), WHITE),       6: (BLACK, (255, 220, 0)),
    7: ((255, 110, 0), BLACK),      8: ((255, 100, 170), BLACK),
    9: ((0, 200, 200), BLACK),      10: ((130, 0, 200), WHITE),
    11: ((150, 150, 150), RED),     12: ((140, 255, 0), BLACK),
    13: ((120, 60, 20), WHITE),     14: ((120, 0, 30), (255, 220, 0)),
    15: ((190, 170, 110), BLACK),   16: ((60, 140, 220), RED),
    17: ((0, 0, 110), WHITE),       18: ((0, 80, 30), (255, 220, 0)),
    19: ((170, 190, 200), RED),     20: ((220, 0, 140), (255, 220, 0)),
}


def saddle_colors(program):
    digits = "".join(c for c in program if c.isdigit())
    return SADDLE.get(int(digits) if digits else 0, (DIM, WHITE))


def dimmed(c, f=0.3):
    return tuple(int(v * f) for v in c)


def draw_saddle(draw, x, y, program, scratched=False):
    """7x5 saddle-cloth badge with the program number centered."""
    bg, fg = saddle_colors(program)
    if scratched:
        bg, fg = dimmed(bg), dimmed(fg)
    if bg != BLACK:
        draw.rectangle([x, y, x + 6, y + 4], fill=bg)
    # In badges, a leading "1" (10-19) is drawn as a slim 1-pixel stroke so both
    # digits get a pixel of colored border instead of running into the badge edge.
    if len(program) == 2 and program[0] == "1":
        tx = x + 1
        draw.line([(tx, y), (tx, y + 4)], fill=fg)
        draw_text(draw, tx + 2, y, program[1], fg)
    else:
        draw_text(draw, x + (7 - text_width(program)) // 2, y, program, fg)


def text_width(s, scale=1, spacing=None):
    sp = scale if spacing is None else spacing
    s = [c for c in s if c in GLYPHS]
    return sum(len(GLYPHS[c][0]) * scale + sp for c in s) - sp if s else 0


def draw_text(draw, x, y, s, color, scale=1, spacing=None):
    sp = scale if spacing is None else spacing
    for c in s:
        g = GLYPHS.get(c)
        if g is None:
            continue
        for row, bits in enumerate(g):
            for col, b in enumerate(bits):
                if b == "1":
                    draw.rectangle([x + col * scale, y + row * scale,
                                    x + col * scale + scale - 1, y + row * scale + scale - 1], fill=color)
        x += len(g[0]) * scale + sp


def mtp_color(mtp):
    if mtp <= 3:
        return RED
    if mtp <= 10:
        return YELLOW
    return WHITE


def short_distance(d):
    """'6 1/2F' -> '6.5F', '6F' -> '6F'. Miles converted to furlongs (1 1/16M -> 8.5F)."""
    d = d.upper().replace(" ", "")
    unit = "M" if d.endswith("M") else "F"
    body = d[:-1]
    fracs = {"1/2": .5, "1/4": .25, "3/4": .75, "1/8": .125, "1/16": .0625, "3/8": .375, "5/8": .625, "7/8": .875, "3/16": .1875, "70Y": 0}
    whole, part = body, 0
    for f, v in fracs.items():
        if body.endswith(f) and body != f:
            whole, part = body[: -len(f)], v
            break
    try:
        val = float(whole or 0) + part
    except ValueError:
        return d[:4]
    if unit == "M":
        val *= 8
    s = f"{val:g}"
    return (s + "F")[:4]


SURFACE_COLORS = {"TRF": GREEN, "DRT": BROWN, "SYN": BLUE}


def short_surface(s):
    """NYRA's surface name -> TRF, DRT or SYN (synthetic: Poly, Tapeta, All Weather). Unknown -> ''."""
    s = s.lower()
    if "turf" in s:
        return "TRF"
    if "dirt" in s:
        return "DRT"
    if any(w in s for w in ("synth", "poly", "tapeta", "all weather", "all-weather")) or s.strip() == "aw":
        return "SYN"
    return ""


def display_odds(odds):
    """'6/1' -> '6', '33/1' -> '33'. Any other format (5/2, 9/2, 3/5) is left as is."""
    return odds[:-2] if odds.endswith("/1") else odds


def odds_color(odds, ml):
    """Green if the odds have drifted above the morning line, red if bet below it, white if equal or unknown."""
    now, morning = _odds_value(odds), _odds_value(ml)
    if now is None or morning is None or now == morning:
        return WHITE
    return GREEN if now > morning else RED


def _odds_value(s):
    try:
        a, b = s.split("/")
        return float(a) / float(b)
    except Exception:
        return None


PER_PAGE = 10


def active_horses(race):
    """Scratched horses are left off the board entirely."""
    return [h for h in race["horses"] if not h["odds"].upper().startswith("SCR")]


def page_count(race):
    """1 page for up to 10 active horses, 2 for 11-20."""
    return max(1, -(-len(active_horses(race)) // PER_PAGE))


def render_full_board(race, page=0):
    """Two columns of horses (5 rows each) plus a sidebar: MTP, distance, surface.
    Fields over 10 active horses are split into pages; the main loop flips between them."""
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)

    horses = active_horses(race)
    priced = [h for h in horses if _odds_value(h["odds"]) is not None]
    fav = min(priced, key=lambda h: _odds_value(h["odds"]))["program"] if priced else None

    page = page % page_count(race)
    for i, h in enumerate(horses[page * PER_PAGE:(page + 1) * PER_PAGE]):
        col, row = divmod(i, 5)
        x0, y = col * 26, 1 + row * 6
        scratched = h["odds"].upper().startswith("SCR")
        draw_saddle(d, x0, y, h["program"], scratched)
        if h["program"] == fav:
            d.point((x0 + 8, y + 2), fill=WHITE)   # favorite dot
        draw_text(d, x0 + 10, y, display_odds(h["odds"]), odds_color(h["odds"], h.get("ml", "")))

    # Sidebar (x 50-63)
    sx, sw = 51, 13
    mtp = race["mtp"]
    m = str(min(mtp, 99))
    draw_text(d, sx + (sw - text_width(m, 2, 1)) // 2, 1, m, mtp_color(mtp), scale=2, spacing=1)
    race_label = f"R{race['race']}"
    draw_text(d, sx + (sw - text_width(race_label)) // 2, 12, race_label, BLUE)
    dist = short_distance(race["distance"])
    draw_text(d, sx + (sw - text_width(dist)) // 2, 19, dist, WHITE)
    surf = short_surface(race["surface"])
    draw_text(d, sx + (sw - text_width(surf)) // 2, 25, surf, SURFACE_COLORS.get(surf, WHITE))
    return img


def short_time(hour, minute):
    """13, 10 -> '1:10p'; 11, 30 -> '11:30a'."""
    return f"{hour % 12 or 12}:{minute:02d}{'p' if hour >= 12 else 'a'}"


def render_big_mtp(race, now=None):
    """'RACE 5' top-left (blue), time of day top-right (gray), MTP number huge and
    centered, 'MTP' (dim) bottom-right beside it."""
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)
    draw_text(d, 1, 1, f"RACE {race['race']}", BLUE)
    now = now or datetime.now()
    clock = short_time(now.hour, now.minute)
    draw_text(d, W - text_width(clock), 1, clock, GRAY)
    mtp = race["mtp"]
    m = str(min(mtp, 99))
    draw_text(d, (W - text_width(m, 4)) // 2, 9, m, mtp_color(mtp), scale=4)
    draw_text(d, W - text_width("MTP"), 24, "MTP", DIM)      # bottom row aligned with the digits' base
    return img


CARD_ROWS = 4
TRACK_LABELS = {"saratoga": "SARATOGA", "belmont": "BELMONT"}
TRACK_COLORS = {"saratoga": (211, 58, 44), "belmont": (34, 139, 34)}   # Saratoga red, Belmont forest green


def short_post(post_time_iso):
    """'2026-10-02T13:10:00' -> '1:10p', '2026-10-02T11:30:00' -> '11:30a'."""
    return short_time(int(post_time_iso[11:13]), int(post_time_iso[14:16]))


def card_page_count(rows):
    return max(1, -(-len(rows) // CARD_ROWS))


def render_card(track, rows, page=0):
    """Today's card (columns: race x 0-6, time 10-30, distance 35-47, surface 53-63):
    header with the track name (Saratoga red, Belmont forest green), then 4 races
    per page - race number (blue), post time with a/p, distance, surface (DRT brown, TRF green, SYN blue).
    `rows` are the races still to come, next race first."""
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)
    draw_text(d, 1, 1, TRACK_LABELS.get(track, track.upper()), TRACK_COLORS.get(track, WHITE))
    draw_text(d, W - 1 - text_width("TODAY"), 1, "TODAY", DIM)

    page = page % card_page_count(rows)
    for i, r in enumerate(rows[page * CARD_ROWS:(page + 1) * CARD_ROWS]):
        y = 8 + i * 6
        num = r["race"]
        draw_text(d, 7 - text_width(num), y, num, BLUE)                    # right-aligned to x 6
        post = short_post(r["post_time"])
        draw_text(d, 31 - text_width(post), y, post, WHITE)                 # right-aligned to x 30
        draw_text(d, 35, y, short_distance(r["distance"]), WHITE)
        surf = short_surface(r["surface"])
        draw_text(d, W - text_width(surf), y, surf, SURFACE_COLORS.get(surf, WHITE))
    return img


PICK5_ROWS = 4
PICK5_SHORT = {"MANDATORY": "MAND"}    # "Mandatory Pay Pick 5" (Belmont, Oct 8 2026)


def pick5_page_count(seqs):
    return -(-len(seqs) // PICK5_ROWS)


def render_pick5(track, seqs, page=0):
    """Pick 5 page of the card screen: header with the track name and 'PICK 5', then one line
    per Pick 5 still to start - name (white), races (blue), first post time with a/p.
    Two or fewer get roomy spacing; up to 4 per page otherwise."""
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)
    draw_text(d, 1, 1, TRACK_LABELS.get(track, track.upper()), TRACK_COLORS.get(track, WHITE))
    draw_text(d, W - text_width("PICK 5"), 1, "PICK 5", DIM)

    rows = seqs[page * PICK5_ROWS:(page + 1) * PICK5_ROWS]
    pitch, top = (9, 10) if len(seqs) <= 2 else (6, 8)
    times = [short_post(s["post_time"]) for s in rows]
    legs = [f"{s['first']}-{s['last']}" for s in rows]
    right = max(map(text_width, times), default=0)
    legs_w = max(map(text_width, legs), default=0)
    # Names get whatever room is left; long ones are shortened to fit
    room = W - 1 - right - 3 - legs_w - 3
    labels = []
    for s in rows:
        # Plain "Pick 5" keeps its name; otherwise the first word ("MANDATORY PAY" -> MAND)
        label = s["label"] if s["label"] == "PICK 5" else s["label"].split()[0]
        label = "".join(c for c in PICK5_SHORT.get(label, label) if c in GLYPHS)
        while label and text_width(label) > room:
            label = label[:-1]
        labels.append(label)
    legs_x = 1 + max(map(text_width, labels), default=0) + 3
    for i, (label, leg, t) in enumerate(zip(labels, legs, times)):
        y = top + i * pitch
        draw_text(d, 1, y, label, WHITE)
        draw_text(d, legs_x, y, leg, BLUE)
        draw_text(d, W - text_width(t), y, t, WHITE)
    return img


def led_preview(img, dot=10):
    """Enlarge a 64x32 frame into an LED-panel-looking preview."""
    out = Image.new("RGB", (img.width * dot, img.height * dot), (12, 12, 12))
    d = ImageDraw.Draw(out)
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            c = px[x, y]
            if c == BLACK:
                c = (28, 28, 28)  # unlit LED
            d.ellipse([x * dot + 1, y * dot + 1, x * dot + dot - 2, y * dot + dot - 2], fill=c)
    return out
