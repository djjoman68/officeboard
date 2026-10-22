"""What every module is made of.

A module has three parts:
  - a fetcher: `fetch()` runs in a background thread every `fetch_interval()` seconds and returns
    the module's data. A failed fetch keeps the last good data and records the error.
  - a renderer: `pages()` returns static 64x32 screens; `ticker_items()` returns short text pieces
    for scrolling (used from step 3). `frame()` turns either into the picture for this moment.
  - settings: `fields` lists the module's own options. Every module also gets "enabled" and
    "seconds" (how long its turn lasts). The web UI's Modules page builds its forms from these.

Modules only draw Pillow images (core/pixels.py), so they never touch the panel library and can be
tested and previewed on any computer.
"""
import logging
import threading
from datetime import datetime

import config
from core import layouts, pixels

log = logging.getLogger("module")

TEXT_MAX = 200
LIST_MAX = 50


class BoardInfo:
    """What a module may want to know about the board: display and location settings, and the
    measured frame rate."""

    def __init__(self, display=None, location=None):
        self.display = display or config.normalize_display({})
        self.location = location or config.normalize_location({})
        self.fps = 0.0
        self.status_bar = None        # set by the display: draws the split layout's top bar

    def top_bar(self, now):
        """The split layout's top bar (64x9): the clock module's time and temperature when there is
        one, else just the time."""
        if self.status_bar:
            try:
                return self.status_bar(now)
            except Exception:
                log.exception("top bar failed")
        img = pixels.Image.new("RGB", (pixels.WIDTH, layouts.BAR_HEIGHT), pixels.BLACK)
        pixels.draw_text(img, "small", 1, 7, pixels.GRAY, f"{now.hour % 12 or 12}:{now.minute:02d}")
        return img


def normalize_field(field, value):
    """One setting made safe, falling back to the field's default."""
    kind, default = field["type"], field["default"]
    if kind == "int":
        return config.clamp_int(value, field.get("min", -10**9), field.get("max", 10**9), default)
    if kind == "bool":
        return value if isinstance(value, bool) else default
    if kind == "select":
        return value if value in [o[0] for o in field["options"]] else default
    if kind == "list":
        if not isinstance(value, list):
            return list(default)
        out = []
        for v in value:
            v = str(v).strip()[:TEXT_MAX]
            if v and v not in out:
                out.append(v)
        return out[:LIST_MAX]
    # text
    return str(value).strip()[:TEXT_MAX] if isinstance(value, str) else default


class Module:
    id = "module"
    name = "Module"
    description = ""
    built = True              # False for modules planned but not written yet
    step = None               # build-order step a planned module arrives in
    default_enabled = False
    default_seconds = 15
    fetch_seconds = None      # None: no background fetching
    fields = []               # the module's own settings, see normalize_field for types
    supports_layouts = True   # False for modules that draw their own way (the panel test)

    def __init__(self, board=None):
        self.board = board or BoardInfo()
        self.settings = self.normalize({})
        self.data = None
        self.last_update = None
        self.last_error = None
        self.warning = None
        self.wake = threading.Event()

    # ---------- settings ----------
    @classmethod
    def all_fields(cls):
        common = [
            {"key": "enabled", "label": "On", "type": "bool", "default": cls.default_enabled},
            {"key": "seconds", "label": "Turn length (seconds)", "type": "int",
             "default": cls.default_seconds, "min": 3, "max": 600,
             "hint": "At least long enough to show every page, or scroll everything past once."},
        ]
        if cls.supports_layouts:
            common.append({"key": "layout", "label": "Layout", "type": "select", "default": "board",
                           "options": [["board", "Same as the board (Settings)"]] +
                                      [[k, layouts.LAYOUT_NAMES[k]] for k in layouts.LAYOUTS]})
        return common + list(cls.fields)

    @classmethod
    def normalize(cls, raw):
        raw = raw if isinstance(raw, dict) else {}
        out = {f["key"]: normalize_field(f, raw.get(f["key"], f["default"])) for f in cls.all_fields()}
        if not cls.built:
            out["enabled"] = False
        return out

    def configure(self, settings):
        """New settings from the web UI. Wakes the fetcher if the module was just turned on."""
        was_on = self.enabled
        self.settings = self.normalize(settings)
        if self.enabled and not was_on:
            self.wake.set()

    @property
    def enabled(self):
        return self.built and self.settings["enabled"]

    # ---------- fetcher ----------
    def fetch(self, now):
        """Return fresh data. Runs in the background thread. Raise on failure."""
        return None

    def fetch_interval(self):
        return self.fetch_seconds

    def refresh(self, now=None):
        """Fetch once, keeping the last good data if it fails."""
        now = now or datetime.now()
        self.warning = None
        try:
            self.data = self.fetch(now)
            self.last_update = now
            self.last_error = self.warning     # a fetch that partly failed can say so here
        except Exception as e:
            # Modules raise ValueError/RuntimeError with a plain-language message; show other errors' type too
            plain = isinstance(e, (ValueError, RuntimeError)) and str(e)
            self.last_error = str(e) if plain else f"{type(e).__name__}: {e}"
            log.warning("%s: fetch failed: %s", self.id, self.last_error)

    # ---------- renderer ----------
    def has_content(self, now):
        """False makes the rotation skip this module (no data yet, no games today, ...)."""
        return self.fetch_seconds is None or self.data is not None

    def pages(self, now):
        """Static 64x32 screens for this turn."""
        return []

    def ticker_items(self, now):
        """Text pieces for scrolling layouts: a list of [(text, colour), ...] per item. From step 3."""
        return []

    def layout(self):
        """Which of the four layouts this module uses: its own setting, or the board's."""
        if not self.supports_layouts:
            return "pages"
        own = self.settings.get("layout", "board")
        return self.board.display["layout"] if own == "board" else own

    def frame(self, now, t):
        """The picture `t` seconds into this module's turn, in its layout. Scrolling layouts fall back
        to pages for a module with no ticker text."""
        lay = self.layout()
        if lay in ("ticker", "split"):
            strip = self._ticker_strip(now, lay)
            if strip is not None:
                speed = self.board.display["scroll_speed"]
                if lay == "ticker":
                    return layouts.ticker(strip, t, speed, label=self.name)
                return layouts.split(self.board.top_bar(now), strip, t, speed)
        if lay == "roll":
            return layouts.roll(self.pages(now), t, self.board.display["page_seconds"])
        return self.page_frame(now, t)

    def page_frame(self, now, t):
        """Pages layout: flip every page_seconds, always starting from the first page."""
        pages = self.pages(now)
        if not pages:
            return pixels.blank()
        return pages[int(t // self.board.display["page_seconds"]) % len(pages)]

    def _ticker_strip(self, now, lay):
        """The module's ticker items drawn as one long strip, redrawn only when the text changes."""
        items = self.ticker_items(now)
        if not items:
            return None
        if lay == "ticker":
            font, height = layouts.TICKER_FONT, layouts.TICKER_HEIGHT
        else:
            font, height = layouts.SPLIT_FONT, layouts.SPLIT_HEIGHT
        key = (repr(items), font)
        if getattr(self, "_strip_cache", (None,))[0] != key:
            self._strip_cache = (key, pixels.text_strip(font, layouts.join_items(items), height))
        return self._strip_cache[1]

    def turn_length(self, now):
        """How long this module's turn lasts: its "seconds" setting, stretched so every page shows once
        or the scrolling text goes all the way past once."""
        base = self.settings["seconds"]
        lay = self.layout()
        if lay in ("ticker", "split"):
            strip = self._ticker_strip(now, lay)
            if strip is not None:
                return max(base, layouts.pass_seconds(strip.width, self.board.display["scroll_speed"]))
        if self.supports_layouts:
            return max(base, len(self.pages(now)) * self.board.display["page_seconds"])
        return base

    def hold(self, now):
        """True keeps the panel past the end of the turn (NYRA near post time)."""
        return False

    def takeover(self, now):
        """True takes the panel from the rotation until it returns False (NYRA take-over mode)."""
        return False

    # ---------- for the web UI ----------
    def status(self):
        return {
            "last_update": self.last_update.isoformat(timespec="seconds") if self.last_update else None,
            "last_error": self.last_error,
        }


class Fetcher(threading.Thread):
    """Background thread that keeps one module's data fresh."""

    def __init__(self, module):
        super().__init__(daemon=True, name=f"fetch-{module.id}")
        self.module = module
        self.stopped = False

    def run(self):
        m = self.module
        while not self.stopped:
            if m.enabled:
                m.refresh()
                wait = m.fetch_interval() or 60
            else:
                wait = 5
            m.wake.wait(wait)
            m.wake.clear()
