"""Stocks: the major indexes, then Joe's own list of stocks (docs/plan.md, module 2).

Quotes come from Finnhub's free tier (key under Settings). It has no index data, so the indexes come
from the funds that track them (DIA, SPY, QQQ), labelled DOW / S&P / NASDAQ and shown by % change only,
since a fund's price isn't the index level. Live during market hours; otherwise the last close and
that day's change, which is what Finnhub's quote gives after the bell.

Screens (designed for the Roll layout):
  Markets page: OPEN / PRE-MARKET / AFTER HOURS / CLOSED, then the three indexes with % change.
  One page per stock: symbol and % change, price, $ change and the quote's time.
  Or, with "Stocks per page" set to 3, compact rows of symbol and % change.
"""
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import config
from core import pixels
from core.module import Module

log = logging.getLogger("stocks")

FINNHUB = "https://finnhub.io/api/v1"
TIMEOUT = (5, 15)
ET = ZoneInfo("America/New_York")
INDEXES = [("DOW", "DIA"), ("S&P", "SPY"), ("NASDAQ", "QQQ")]
OPEN_SECONDS = 60             # quotes every minute while the market is open
CLOSED_SECONDS = 1800         # and every half hour otherwise (nothing changes)
DAY_OFF_SECONDS = 3 * 3600    # weekends and market holidays, while Stocks is skipped
MAX_STOCKS = 40               # keeps a refresh well inside the free tier's 60 calls a minute

UP, DOWN, FLAT = (0, 220, 80), (255, 60, 60), (255, 255, 255)
WHITE, DIM = pixels.WHITE, (110, 110, 110)
SESSIONS = ("pre-market", "regular", "post-market")
SESSION_LABELS = {"regular": ("MARKET OPEN", UP), "pre-market": ("PRE-MARKET", pixels.YELLOW),
                  "post-market": ("AFTER HOURS", pixels.YELLOW), None: ("MARKET CLOSED", DIM)}


def colour(change):
    if change is None or abs(change) < 0.005:
        return FLAT
    return UP if change > 0 else DOWN


def pct_text(pct):
    """▲1.20% / ▼0.35% / 0.00%"""
    if pct is None:
        return "--"
    arrow = "▲" if pct >= 0.005 else "▼" if pct <= -0.005 else ""
    return f"{arrow}{abs(pct):.2f}%"


def price_text(p):
    return f"{p:,.2f}" if p < 10000 else f"{p:,.0f}"


def change_text(d):
    """+2.74 / -2.20; whole dollars from 100 up (+1,200), so big moves still fit."""
    return f"{'+' if d >= 0 else '-'}{abs(d):,.2f}" if abs(d) < 100 else f"{'+' if d >= 0 else '-'}{abs(d):,.0f}"


def short_time(t, fmt):
    if fmt == "24hr":
        return f"{t.hour:02d}:{t.minute:02d}"
    return f"{t.hour % 12 or 12}:{t.minute:02d}{'a' if t.hour < 12 else 'p'}"


def guess_session(now_et):
    """Market session from the clock, for when Finnhub's market status can't be read.
    Doesn't know holidays (Finnhub's status does)."""
    if now_et.weekday() >= 5:
        return None
    minutes = now_et.hour * 60 + now_et.minute
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return "pre-market"
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return "regular"
    if 16 * 60 <= minutes < 20 * 60:
        return "post-market"
    return None


def parse_quote(symbol, body):
    """Finnhub /quote -> {symbol, price, change, pct, time}. None for an unknown symbol (Finnhub
    answers those with zeros)."""
    price = body.get("c")
    if not price:
        return None
    t = body.get("t")
    return {"symbol": symbol, "price": float(price), "change": float(body.get("d") or 0),
            "pct": float(body.get("dp") or 0),
            "time": datetime.fromtimestamp(t, ET).replace(tzinfo=None) if t else None}


class Stocks(Module):
    id = "stocks"
    name = "Stocks"
    description = "Major indexes, then your own list of stocks."
    default_seconds = 15
    fetch_seconds = OPEN_SECONDS
    fields = [
        {"key": "symbols", "label": "Your stocks", "type": "list", "default": [],
         "hint": f"Ticker symbols like AAPL, in the order you want them shown. Up to {MAX_STOCKS}."},
        {"key": "per_page", "label": "Stocks per page", "type": "select", "default": "1",
         "options": [["1", "1, big (symbol, price, change)"], ["3", "3, compact (symbol and % change)"]]},
        {"key": "skip_closed", "label": "Skip weekends and market holidays", "type": "bool", "default": True,
         "hint": "Stocks drops out of the rotation from Saturday to Sunday, and on days the market is closed."},
    ]

    def __init__(self, board=None):
        super().__init__(board)
        self._pages_key = None

    # ---------- fetching ----------
    def symbols(self):
        out = []
        for s in self.settings["symbols"]:
            s = s.strip().upper()
            if s and s not in out:
                out.append(s)
        return out[:MAX_STOCKS]

    def fetch_interval(self):
        session = (self.data or {}).get("session")
        if session in ("regular", "pre-market", "post-market"):
            return OPEN_SECONDS
        if self.market_day_off(self.last_update or datetime.now()):
            return DAY_OFF_SECONDS              # not shown anyway: just keep the last close fresh-ish
        return CLOSED_SECONDS

    def fetch(self, now):
        key = config.load_secrets().get("finnhub_api_key", "").strip()
        if not key:
            raise ValueError("Add a Finnhub key under Settings (free at finnhub.io)")
        prev = self.data or {}
        old = {q["symbol"]: q for q in prev.get("indexes", []) + prev.get("stocks", [])}
        problems, unknown = [], []

        try:
            r = requests.get(f"{FINNHUB}/stock/market-status", params={"exchange": "US", "token": key},
                             timeout=TIMEOUT)
            r.raise_for_status()
            status = r.json()
            session = status.get("session") if status.get("session") in SESSIONS else None
            holiday = status.get("holiday")
        except Exception as e:
            if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code in (401, 403):
                raise ValueError("Finnhub key not accepted: check it under Settings")
            session, holiday = guess_session(datetime.now(ET)), None

        def quote(symbol):
            try:
                r = requests.get(f"{FINNHUB}/quote", params={"symbol": symbol, "token": key}, timeout=TIMEOUT)
                if r.status_code == 429:
                    time.sleep(1)
                    r = requests.get(f"{FINNHUB}/quote", params={"symbol": symbol, "token": key}, timeout=TIMEOUT)
                r.raise_for_status()
                q = parse_quote(symbol, r.json())
                if q is None:
                    unknown.append(symbol)
                return q
            except Exception as e:
                problems.append(f"{symbol}: {self._why(e)}")
                return old.get(symbol)            # last good quote

        indexes = []
        for label, fund in INDEXES:
            q = quote(fund)
            if q:
                indexes.append(dict(q, label=label))
        stocks = [q for q in (quote(s) for s in self.symbols()) if q]

        if not indexes and not stocks and problems:
            raise RuntimeError("; ".join(problems[:3]))
        notes = []
        if unknown:
            notes.append("Not found: " + ", ".join(unknown))
        if problems:
            notes.append("; ".join(problems[:3]))
        self.warning = " · ".join(notes) or None
        return {"session": session, "holiday": holiday, "indexes": indexes, "stocks": stocks}

    @staticmethod
    def _why(e):
        if isinstance(e, requests.HTTPError) and e.response is not None:
            return {401: "key not accepted", 403: "not in Finnhub's free plan",
                    429: "too many requests, will retry"}.get(e.response.status_code, f"error {e.response.status_code}")
        if isinstance(e, requests.ConnectionError):
            return "no connection"
        return str(e) or type(e).__name__

    def configure(self, settings):
        old = self.settings.get("symbols")
        super().configure(settings)
        if self.settings["symbols"] != old:
            self.wake.set()                      # new list: fetch now

    # ---------- screens ----------
    def market_day_off(self, now):
        """A weekend or a market holiday (Finnhub says so and nothing is trading)."""
        data = self.data or {}
        return now.weekday() >= 5 or bool(data.get("holiday") and not data.get("session"))

    def has_content(self, now):
        """Skipped with nothing fetched yet, and on weekends and market holidays (Joe, Oct 24 2026:
        the setting is on by default)."""
        if self.settings["skip_closed"] and self.market_day_off(now):
            return False
        return bool(self.data and (self.data["indexes"] or self.data["stocks"]))

    def _wanted(self):
        """Quotes for the symbols in the list now, in its order (the data may lag a just-edited list)."""
        by_symbol = {q["symbol"]: q for q in (self.data or {}).get("stocks", [])}
        return [by_symbol[s] for s in self.symbols() if s in by_symbol]

    def pages(self, now):
        data = self.data or {}
        key = (id(self.data), tuple(self.symbols()), self.settings["per_page"], self.board.location["clock_format"])
        if key != self._pages_key:
            pages = []
            if data.get("indexes"):
                pages.append(self.markets_page(data))
            stocks = self._wanted()
            if self.settings["per_page"] == "3":
                pages += [self.rows_page(stocks[i:i + 3]) for i in range(0, len(stocks), 3)]
            else:
                pages += [self.stock_page(q) for q in stocks]
            self._pages, self._pages_key = pages, key
        return self._pages

    def markets_page(self, data):
        img = pixels.blank()
        label, label_colour = SESSION_LABELS.get(data.get("session"), SESSION_LABELS[None])
        if data.get("holiday") and not data.get("session"):
            label = "HOLIDAY"
        pixels.draw_text(img, "tiny", (64 - pixels.text_width("tiny", label)) // 2, 6, label_colour, label)
        self._rows(img, [(q["label"], q["pct"]) for q in data["indexes"]], first=15, step=8)
        return img

    def rows_page(self, quotes):
        img = pixels.blank()
        self._rows(img, [(q["symbol"], q["pct"]) for q in quotes], first=9, step=11)
        return img

    @staticmethod
    def _rows(img, rows, first, step):
        """Name on the left, % change on the right, one row each, baselines `step` apart."""
        for i, (name, pct) in enumerate(rows):
            y = first + i * step
            pixels.draw_text(img, "small", 1, y, WHITE, name)
            text = pct_text(pct)
            pixels.draw_text(img, "small", 64 - pixels.text_width("small", text), y, colour(pct), text)

    def stock_page(self, q):
        """Symbol and % change on top, price in the middle, $ change and the quote's time below."""
        img = pixels.blank()
        c = colour(q["change"])
        pixels.draw_text(img, "regular_bold", 1, 10, WHITE, q["symbol"][:5])
        pct = pct_text(q["pct"])
        pixels.draw_text(img, "small", 64 - pixels.text_width("small", pct), 9, c, pct)
        price = price_text(q["price"])
        font = "regular" if pixels.text_width("regular", price) <= 63 else "small"
        pixels.draw_text(img, font, 1, 22, WHITE, price)
        used = 1 + pixels.draw_text(img, "small", 1, 31, c, change_text(q["change"]))
        if q.get("time"):
            when = short_time(q["time"], self.board.location["clock_format"])
            x = 64 - pixels.text_width("tiny", when)
            if x > used + 2:                  # the time only if it fits beside the change
                pixels.draw_text(img, "tiny", x, 31, DIM, when)
        return img

    def ticker_items(self, now):
        data = self.data or {}
        items = [[(q["label"] + " ", WHITE), (pct_text(q["pct"]), colour(q["pct"]))] for q in data.get("indexes", [])]
        for q in self._wanted():
            items.append([(q["symbol"] + " ", WHITE), (price_text(q["price"]) + " ", WHITE),
                          (pct_text(q["pct"]), colour(q["change"]))])
        return items
