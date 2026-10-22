"""MLB and NFL: games, live scores and betting odds from ESPN's free scoreboard feed (docs/plan.md,
modules 4 and 5, build steps 6 and 7).

ESPN's feed (unofficial, no key) has each game's teams, start time, status and score, plus DraftKings
odds: the moneyline for each team, the spread and the total. One source covers both leagues.

  MLB: every game today, odds = moneyline for both teams ("TB +133" / "MIL -161").
  NFL: every game this week (ESPN's current week, Thursday to Monday), odds = spread and total
       ("CHI -3" / "O/U 50.5").

Screens (designed for the Roll layout), one page per game:
  before it starts  teams, start time, the odds
  playing / final   a two-line scoreboard (the leader bright, the other dimmed) and the inning, quarter
                    or FINAL
"""
import logging
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urlparse

import requests
from PIL import Image, ImageEnhance

import config
from core import pixels
from core.module import Module

log = logging.getLogger("games")

ESPN = "https://site.api.espn.com/apis/site/v2/sports"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal LED display)"}
TIMEOUT = (5, 15)
LIVE_SECONDS = 60          # while a game is on
SOON_SECONDS = 600         # games still to come today / this week
IDLE_SECONDS = 1800        # nothing on soon (or no games at all)

WHITE, DIM, ODDS, LIVE = pixels.WHITE, (110, 110, 110), pixels.YELLOW, (0, 220, 80)
TRAILING = (140, 140, 140)
TIME = (160, 160, 160)     # start time on the pre-game screen
BOTTOM_GAP = 4             # pixels kept between the start time and the total
DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")

# Team logos: fetched from ESPN's image server the first time a team plays, kept on the Pi in
# .cache/logos (never in git: they're the teams' trademarks), drawn at LOGO x LOGO.
LOGO = 13
LOGO_BRIGHTNESS, LOGO_CONTRAST = 1.7, 1.2
LOGO_DIR = os.path.join(config.BASE_DIR, ".cache", "logos")
LOGO_HOSTS = ("a.espncdn.com",)
LOGO_MAX_BYTES = 2_000_000
LOGO_RETRY_SECONDS = 6 * 3600      # after a failed download
MIN_LUM = 90                        # dimmest team colour allowed for letters


def _local(iso):
    """ESPN's UTC start time ("2026-10-23T00:15Z") as local time without a zone."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


def _line(side):
    """The current line for one side of a market: the closing number if there is one, else the opening."""
    side = side or {}
    for key in ("close", "current", "open"):
        if side.get(key, {}).get("odds"):
            return side[key]["odds"]
    return None


def parse_odds(competition):
    """{"details", "spread", "total", "ml_home", "ml_away"} from the first bookmaker listed, or None."""
    books = competition.get("odds") or []
    if not books:
        return None
    o = books[0]
    ml = o.get("moneyline") or {}
    out = {"details": o.get("details"), "spread": o.get("spread"), "total": o.get("overUnder"),
           "ml_home": _line(ml.get("home")), "ml_away": _line(ml.get("away"))}
    return out if any(v not in (None, "") for v in out.values()) else None


def _team(c):
    t = c["team"]
    return {"abbr": t["abbreviation"], "score": c.get("score"),
            "color": t.get("color"), "alt": t.get("alternateColor"),
            "logo_url": t.get("logoDark") or t.get("logo")}


def parse_scoreboard(body):
    """ESPN scoreboard -> games sorted by start time."""
    games = []
    for e in body.get("events", []):
        comp = e["competitions"][0]
        teams = {c["homeAway"]: _team(c) for c in comp["competitors"]}
        if "home" not in teams or "away" not in teams:
            continue
        status = e.get("status", {}).get("type", {})
        games.append({
            "id": e.get("id"), "start": _local(e["date"]),
            "state": status.get("state", "pre"),                     # pre, in or post
            "detail": status.get("shortDetail", ""),
            "completed": status.get("completed", False),
            "home": teams["home"], "away": teams["away"],
            "odds": parse_odds(comp),
        })
    return sorted(games, key=lambda g: g["start"])


def short_time(t, fmt):
    if fmt == "24hr":
        return f"{t.hour:02d}:{t.minute:02d}"
    return f"{t.hour % 12 or 12}:{t.minute:02d}{'a' if t.hour < 12 else 'p'}"


def status_text(game):
    """What's happening, short and upper case: TOP 7TH, Q3 5:21, HALFTIME, FINAL, FINAL/10, PPD."""
    detail = (game["detail"] or "").upper()
    if game["state"] == "in":
        # NFL: "5:21 - 3RD" -> "Q3 5:21"
        if " - " in detail:
            clock, period = detail.split(" - ", 1)
            q = {"1ST": "Q1", "2ND": "Q2", "3RD": "Q3", "4TH": "Q4"}.get(period.strip(), period.strip())
            return f"{q} {clock.strip()}"
        return detail
    if game["state"] == "post" and "POSTPONED" in detail:
        return "PPD"
    return detail


# ---------- team colours and logos (Joe's pick, Oct 22 2026: brighter logos + team-colour letters) ----------
def _rgb(hexcode):
    try:
        h = (hexcode or "").lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else None
    except ValueError:
        return None


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def team_colour(team):
    """The brighter of a team's two colours, lifted so it shows on LEDs (many teams' main colour is
    a navy that barely lights). White if ESPN gives none."""
    options = [c for c in (_rgb(team.get("color")), _rgb(team.get("alt"))) if c]
    if not options:
        return WHITE
    c = max(options, key=_lum)
    if _lum(c) < MIN_LUM:
        f = MIN_LUM / max(1.0, _lum(c))
        c = tuple(min(255, int(v * f) + (40 if _lum(c) < 5 else 0)) for v in c)
    return c


def process_logo(img):
    """A logo from ESPN (big PNG, see-through background) as a LOGO x LOGO tile on black, brightened
    so it isn't dim on the LEDs."""
    img = img.convert("RGBA")
    box = img.getbbox()
    if box:
        img = img.crop(box)
    img.thumbnail((LOGO, LOGO), Image.LANCZOS)
    tile = Image.new("RGB", (LOGO, LOGO), (0, 0, 0))
    tile.paste(img, ((LOGO - img.width) // 2, (LOGO - img.height) // 2), img)
    return ImageEnhance.Contrast(ImageEnhance.Brightness(tile).enhance(LOGO_BRIGHTNESS)).enhance(LOGO_CONTRAST)


def _centre(img, font, y, pieces):
    width = sum(pixels.text_width(font, t) for t, _ in pieces)
    x = max(0, (pixels.WIDTH - width) // 2)
    for text, colour in pieces:
        x += pixels.draw_text(img, font, x, y, colour, text)


class Games(Module):
    """One league's games. Subclasses set the league, which games to ask for, and how odds read."""
    league_path = ""
    default_seconds = 20
    fetch_seconds = SOON_SECONDS

    fields = [
        {"key": "odds", "label": "Show betting odds", "type": "bool", "default": True,
         "hint": "DraftKings lines from ESPN, shown before each game starts."},
        {"key": "finals", "label": "Show finished games", "type": "bool", "default": True},
        {"key": "logos", "label": "Show team logos", "type": "bool", "default": True,
         "hint": "On the score screens, beside each team. Downloaded from ESPN the first time a team plays."},
    ]

    def __init__(self, board=None):
        super().__init__(board)
        self._pages_key = None
        self._logos = {}               # abbreviation -> tile
        self._logo_failed = {}         # abbreviation -> when its download last failed

    # ---------- logos ----------
    def league(self):
        return self.league_path.split("/")[-1]

    def logo_path(self, abbr):
        safe = "".join(ch for ch in abbr.upper() if ch.isalnum())
        return os.path.join(LOGO_DIR, f"{self.league()}-{safe}.png")

    def logo(self, team):
        """The team's 13x13 logo tile, or None (not downloaded yet, or logos turned off)."""
        if not self.settings["logos"]:
            return None
        abbr = team["abbr"]
        if abbr not in self._logos:
            path = self.logo_path(abbr)
            if not os.path.exists(path):
                return None
            try:
                with Image.open(path) as f:
                    self._logos[abbr] = f.convert("RGB")
            except OSError:
                return None
        return self._logos[abbr]

    def fetch_logos(self, games):
        """Download any missing logos (in the background fetcher, never while drawing)."""
        if not self.settings["logos"]:
            return
        teams = {t["abbr"]: t for g in games for t in (g["away"], g["home"])}
        for abbr, team in teams.items():
            path = self.logo_path(abbr)
            if os.path.exists(path) or time.time() - self._logo_failed.get(abbr, 0) < LOGO_RETRY_SECONDS:
                continue
            url = team.get("logo_url") or ""
            if urlparse(url).hostname not in LOGO_HOSTS:
                self._logo_failed[abbr] = time.time()
                continue
            try:
                r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                r.raise_for_status()
                if len(r.content) > LOGO_MAX_BYTES:
                    raise ValueError("logo file too big")
                with Image.open(BytesIO(r.content)) as img:
                    tile = process_logo(img)
                os.makedirs(LOGO_DIR, exist_ok=True)
                tile.save(path)
                self._pages_key = None          # redraw with the new logo
            except Exception as e:
                log.info("%s logo for %s not available: %s", self.league(), abbr, e)
                self._logo_failed[abbr] = time.time()

    # ---------- fetching ----------
    def params(self, now):
        return {}

    def fetch(self, now):
        try:
            r = requests.get(f"{ESPN}/{self.league_path}/scoreboard", params=self.params(now),
                             headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            games = parse_scoreboard(r.json())
        except requests.HTTPError as e:
            raise RuntimeError(f"ESPN answered with error {e.response.status_code if e.response is not None else '?'}")
        except requests.ConnectionError:
            raise RuntimeError("no connection to ESPN")
        except (KeyError, ValueError, TypeError) as e:
            raise RuntimeError(f"ESPN's scoreboard layout not recognized ({e})")
        self.fetch_logos(games)
        return {"games": games, "at": now}

    def fetch_interval(self):
        games = (self.data or {}).get("games", [])
        if any(g["state"] == "in" for g in games):
            return LIVE_SECONDS
        now = datetime.now()
        if any(g["state"] == "pre" and g["start"] - now < timedelta(hours=1) for g in games):
            return LIVE_SECONDS                   # a game is about to start
        if any(g["state"] == "pre" for g in games):
            return SOON_SECONDS
        return IDLE_SECONDS

    # ---------- which games ----------
    def games(self, now):
        games = (self.data or {}).get("games", [])
        if not self.settings["finals"]:
            games = [g for g in games if g["state"] != "post"]
        return games

    def has_content(self, now):
        return bool(self.games(now))

    # ---------- odds (per league) ----------
    def odds_lines(self, game):
        """Up to two lines of odds: [(text, colour), ...] each."""
        return []

    # ---------- screens ----------
    def when(self, game, now, short_day=False, compact=False):
        """8:15p today, else SUN 1:00p. Sharing the bottom line with the total: SU 1p / SU 4:25p."""
        t = short_time(game["start"], self.board.location["clock_format"])
        if compact and t.endswith((":00a", ":00p")):
            t = t[:-4] + t[-1]
        if game["start"].date() == now.date():
            return t
        day = DAYS[game["start"].weekday()]
        return f"{day[:2] if short_day else day} {t}"

    def pages(self, now):
        games = self.games(now)
        key = (id(self.data), self.settings["odds"], self.settings["finals"], self.settings["logos"],
               self.board.location["clock_format"], now.date())
        if key != self._pages_key:
            self._pages = [self.preview_page(g, now) if g["state"] == "pre" else self.score_page(g) for g in games]
            self._pages_key = key
        return self._pages

    def _team_rows(self, img, game, right):
        """Away team on top, home below: logo, name in team colour, and on the right `right[side]`
        ((text, colour, font) or None): the score, or the odds before the game."""
        for top, side in ((0, "away"), (13, "home")):
            team = game[side]
            tile = self.logo(team)
            x = 2
            if tile is not None:
                img.paste(tile, (0, top))
                x = LOGO + 3
            pixels.draw_text(img, "regular", x, top + 10, team_colour(team), team["abbr"])
            if right.get(side):
                text, colour, font = right[side]
                y = top + 10 if font == "regular" else top + 9
                pixels.draw_text(img, font, 63 - pixels.text_width(font, text), y, colour, text)

    def preview_page(self, game, now):
        """Before the game, laid out like the score screen: each team's logo and name with its odds on
        the right (NFL spread, MLB moneyline), then the start time (and NFL total) on the bottom line."""
        img = pixels.blank()
        show = self.settings["odds"] and game.get("odds")
        odds = self.row_odds(game) if show else {}
        self._team_rows(img, game, {s: (t, ODDS, "small") for s, t in odds.items() if t})
        extra = self.bottom_odds(game) if show else None
        when = self.when(game, now, short_day=bool(extra), compact=bool(extra))
        if extra:
            # Time on the left, the total on the right ("O/U49.5"); just the number if they'd touch
            pieces = [("O/U", DIM), (extra, ODDS)]
            if pixels.text_width("tiny", when) + pixels.text_width("tiny", "O/U" + extra) + BOTTOM_GAP > pixels.WIDTH:
                pieces = [(extra, ODDS)]
            pixels.draw_text(img, "tiny", 0, 31, TIME, when)
            x = pixels.WIDTH - sum(pixels.text_width("tiny", t) for t, _ in pieces)
            for text, colour in pieces:
                x += pixels.draw_text(img, "tiny", x, 31, colour, text)
        else:
            _centre(img, "tiny", 31, [(when, TIME)])
        return img

    def score_page(self, game):
        """Two-line scoreboard: logo, team in its colour, score (the leader's bright, the other's dimmed),
        then the inning, quarter or FINAL."""
        img = pixels.blank()
        away, home = game["away"], game["home"]
        try:
            a, h = int(away["score"] or 0), int(home["score"] or 0)
        except ValueError:
            a = h = 0
        self._team_rows(img, game, {"away": (str(a), WHITE if a >= h else TRAILING, "regular"),
                                    "home": (str(h), WHITE if h >= a else TRAILING, "regular")})
        status = status_text(game)
        _centre(img, "tiny", 31, [(status, LIVE if game["state"] == "in" else DIM)])
        return img

    # ---------- odds on the pre-game screen (per league) ----------
    def row_odds(self, game):
        """{"away": "+3", "home": "-3"}: each team's number, shown on its row."""
        return {}

    def bottom_odds(self, game):
        """A number for the bottom line beside the time (the NFL total), or None."""
        return None

    def ticker_items(self, now):
        items = []
        for g in self.games(now):
            if g["state"] == "pre":
                item = [(f"{g['away']['abbr']} @ {g['home']['abbr']} ", WHITE), (self.when(g, now) + " ", DIM)]
                if self.settings["odds"] and g.get("odds"):
                    for line in self.odds_lines(g):
                        item += line + [(" ", WHITE)]
            else:
                item = [(f"{g['away']['abbr']} {g['away']['score']} ", WHITE),
                        (f"{g['home']['abbr']} {g['home']['score']} ", WHITE),
                        (status_text(g), LIVE if g["state"] == "in" else DIM)]
            items.append(item)
        return items


class Mlb(Games):
    id = "mlb"
    name = "MLB"
    description = "Today's games with moneylines, then live scores."
    league_path = "baseball/mlb"

    def params(self, now):
        return {"dates": now.strftime("%Y%m%d")}       # ESPN's default is the next day with games

    def games(self, now):
        return [g for g in super().games(now) if g["start"].date() == now.date() or g["state"] == "in"]

    def odds_lines(self, game):
        o = game["odds"]
        lines = []
        for side in ("away", "home"):
            price = o.get(f"ml_{side}")
            if price:
                lines.append([(game[side]["abbr"] + " ", team_colour(game[side])), (price, ODDS)])
        return lines

    def row_odds(self, game):
        """Each team's moneyline on its own row: TB +133 / MIL -161."""
        o = game["odds"]
        return {side: o.get(f"ml_{side}") for side in ("away", "home")}


class Nfl(Games):
    id = "nfl"
    name = "NFL"
    description = "This week's games with spread and total, then live scores."
    league_path = "football/nfl"

    def odds_lines(self, game):
        o = game["odds"]
        lines = []
        if o.get("details"):
            details = o["details"].upper()                           # "CHI -3", or "EVEN"
            abbr, _, line = details.partition(" ")
            team = next((game[s] for s in ("away", "home") if game[s]["abbr"] == abbr), None)
            lines.append([(abbr + " ", team_colour(team)), (line, ODDS)] if team and line else [(details, ODDS)])
        if o.get("total") is not None:
            lines.append([("O/U ", DIM), (f"{o['total']:g}", ODDS)])
        return lines

    def row_odds(self, game):
        """The spread on the favourite's row only (Joe, Oct 22 2026): CHI -3. A pick'em shows PK on the
        home team's row."""
        details = (game["odds"].get("details") or "").upper().strip()
        if details in ("EVEN", "PK", "PICK"):
            return {"home": "PK"}
        abbr, _, line = details.partition(" ")
        try:
            points = abs(float(line))
        except ValueError:
            return {}
        sides = {game[s]["abbr"]: s for s in ("away", "home")}
        if abbr not in sides:
            return {}
        return {sides[abbr]: f"-{points:g}"}

    def bottom_odds(self, game):
        total = game["odds"].get("total") if game.get("odds") else None
        return f"{total:g}" if total is not None else None
