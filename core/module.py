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
from core import pixels

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
        return [
            {"key": "enabled", "label": "On", "type": "bool", "default": cls.default_enabled},
            {"key": "seconds", "label": "Turn length (seconds)", "type": "int",
             "default": cls.default_seconds, "min": 3, "max": 600},
        ] + list(cls.fields)

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

    def frame(self, now, t):
        """The picture `t` seconds into this module's turn. Pages flip every page_seconds,
        always starting from the first page."""
        pages = self.pages(now)
        if not pages:
            return pixels.blank()
        return pages[int(t // self.board.display["page_seconds"]) % len(pages)]

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
