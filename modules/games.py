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
from datetime import datetime, timedelta

import requests

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
DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


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


def parse_scoreboard(body):
    """ESPN scoreboard -> games sorted by start time."""
    games = []
    for e in body.get("events", []):
        comp = e["competitions"][0]
        teams = {c["homeAway"]: {"abbr": c["team"]["abbreviation"], "score": c.get("score")}
                 for c in comp["competitors"]}
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
    ]

    def __init__(self, board=None):
        super().__init__(board)
        self._pages_key = None

    # ---------- fetching ----------
    def params(self, now):
        return {}

    def fetch(self, now):
        try:
            r = requests.get(f"{ESPN}/{self.league_path}/scoreboard", params=self.params(now),
                             headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return {"games": parse_scoreboard(r.json()), "at": now}
        except requests.HTTPError as e:
            raise RuntimeError(f"ESPN answered with error {e.response.status_code if e.response is not None else '?'}")
        except requests.ConnectionError:
            raise RuntimeError("no connection to ESPN")
        except (KeyError, ValueError, TypeError) as e:
            raise RuntimeError(f"ESPN's scoreboard layout not recognized ({e})")

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
    def when(self, game, now):
        t = short_time(game["start"], self.board.location["clock_format"])
        return t if game["start"].date() == now.date() else f"{DAYS[game['start'].weekday()]} {t}"

    def pages(self, now):
        games = self.games(now)
        key = (id(self.data), self.settings["odds"], self.settings["finals"],
               self.board.location["clock_format"], now.date())
        if key != self._pages_key:
            self._pages = [self.preview_page(g, now) if g["state"] == "pre" else self.score_page(g) for g in games]
            self._pages_key = key
        return self._pages

    def preview_page(self, game, now):
        """Teams, start time, then up to two lines of odds."""
        img = pixels.blank()
        _centre(img, "small", 7, [(game["away"]["abbr"], WHITE), (" @ ", DIM), (game["home"]["abbr"], WHITE)])
        _centre(img, "tiny", 15, [(self.when(game, now), DIM)])
        lines = self.odds_lines(game) if self.settings["odds"] and game.get("odds") else []
        for y, line in zip((23, 31), lines):
            _centre(img, "small", y, line)
        return img

    def score_page(self, game):
        """Two-line scoreboard, the leader bright, then the inning, quarter or FINAL."""
        img = pixels.blank()
        away, home = game["away"], game["home"]
        try:
            a, h = int(away["score"] or 0), int(home["score"] or 0)
        except ValueError:
            a = h = 0
        for y, team, mine, theirs in ((11, away, a, h), (23, home, h, a)):
            colour = WHITE if mine >= theirs else TRAILING
            pixels.draw_text(img, "regular", 2, y, colour, team["abbr"])
            score = str(mine)
            pixels.draw_text(img, "regular", 62 - pixels.text_width("regular", score), y, colour, score)
        status = status_text(game)
        _centre(img, "tiny", 31, [(status, LIVE if game["state"] == "in" else DIM)])
        return img

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
                lines.append([(game[side]["abbr"] + " ", WHITE), (price, ODDS)])
        return lines


class Nfl(Games):
    id = "nfl"
    name = "NFL"
    description = "This week's games with spread and total, then live scores."
    league_path = "football/nfl"

    def odds_lines(self, game):
        o = game["odds"]
        lines = []
        if o.get("details"):
            lines.append([(o["details"].upper(), ODDS)])            # "CHI -3", or "EVEN"
        if o.get("total") is not None:
            lines.append([("O/U ", DIM), (f"{o['total']:g}", ODDS)])
        return lines
