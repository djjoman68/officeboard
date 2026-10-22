"""The four ways a module can present itself, for the scroll experiment (docs/plan.md, step 3).

  pages   static screens that flip every page_seconds (itsposttime's way)
  roll    the same screens, each sliding up into place like a departures board
  ticker  one large line of text scrolling right to left across the whole panel
  split   a fixed top bar (time and temperature) with a line of text scrolling underneath

A module supplies pages (`pages()`) and ticker items (`ticker_items()`); these functions turn them
into the picture for one moment. Ticker items are lists of (text, colour) pieces.
"""
from core import pixels

LAYOUTS = ("pages", "roll", "ticker", "split")
LAYOUT_NAMES = {"pages": "Pages", "roll": "Roll (pages slide up)", "ticker": "Full ticker",
                "split": "Split (top bar + ticker)"}

ROLL_SECONDS = 0.5                 # how long a page takes to slide into place
TICKER_FONT, TICKER_HEIGHT = "large", 13
SPLIT_FONT, SPLIT_HEIGHT = "regular", 13
BAR_HEIGHT = 9                     # split layout: rows 0-8 for the top bar, row 9 a dim rule
SEPARATOR = ("  •  ", pixels.DIM)
LABEL = (110, 110, 110)


def join_items(items):
    """All of a module's ticker items as one run of pieces, with a dim dot between items."""
    pieces = []
    for i, item in enumerate(items):
        if i:
            pieces.append(SEPARATOR)
        pieces.extend(item)
    pieces.append(("     ", pixels.BLACK))       # a gap before it comes round again
    return pieces


def pass_seconds(strip_width, speed, span=pixels.WIDTH):
    """Time for a strip to scroll all the way through, entering on the right and leaving on the left."""
    return (strip_width + span) / max(1, speed)


def roll(pages, t, page_seconds):
    """Pages in turn; at each change the next page pushes the last one up and out."""
    if not pages:
        return pixels.blank()
    n = len(pages)
    i = int(t // page_seconds) % n
    into = t - (t // page_seconds) * page_seconds
    if n == 1 or into >= ROLL_SECONDS or t < page_seconds:
        return pages[i]
    shift = int(pixels.HEIGHT * into / ROLL_SECONDS)        # 0..31 rows moved so far
    img = pixels.blank()
    img.paste(pages[(i - 1) % n], (0, -shift))
    img.paste(pages[i], (0, pixels.HEIGHT - shift))
    return img


def ticker(strip, t, speed, label=None):
    """Full ticker: the line centred top to bottom, with the module's name small and dim above it."""
    img = pixels.blank()
    if label:
        pixels.draw_text(img, "tiny", 1, 6, LABEL, label.upper())
    y = (pixels.HEIGHT - strip.height) // 2 + (3 if label else 0)
    return pixels.marquee(img, strip, t, speed, y=y)


def split(bar, strip, t, speed):
    """Split: the top bar (already drawn, 64x9), a dim rule, and the line scrolling underneath."""
    img = pixels.blank()
    img.paste(bar, (0, 0))
    img.paste((40, 40, 40), (0, BAR_HEIGHT, pixels.WIDTH, BAR_HEIGHT + 1))
    area = pixels.HEIGHT - BAR_HEIGHT - 1
    y = BAR_HEIGHT + 1 + (area - strip.height) // 2
    return pixels.marquee(img, strip, t, speed, y=y)


def text_page(lines):
    """A page of up to four lines of (text, colour) pieces, in the biggest font that fits."""
    for font, height, max_lines in (("regular", 13, 2), ("small", 8, 3), ("tiny", 6, 4)):
        if len(lines) <= max_lines and all(sum(pixels.text_width(font, t) for t, _ in ln) <= pixels.WIDTH
                                          for ln in lines):
            break
    img = pixels.blank()
    gap = (pixels.HEIGHT - height * len(lines)) // (len(lines) + 1)
    y = gap
    for ln in lines:
        width = sum(pixels.text_width(font, t) for t, _ in ln)
        x = max(0, (pixels.WIDTH - width) // 2)
        for text, colour in ln:
            x += pixels.draw_text(img, font, x, y + height - (3 if height == 13 else 1), colour, text)
        y += height + gap
    return img
