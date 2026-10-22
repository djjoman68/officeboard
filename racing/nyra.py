"""Reads race data from NYRA's public racing pages (no API, no login).
From itsposttime's utilities/nyra.py. Modified for the office board: unchanged so far.

    current_race(html)  -> the race NYRA is currently counting down to
    racing_on(html, d)  -> whether the track page is counting down to a race on day d
    race_numbers(html)  -> the race numbers on the track page's race tabs (today's card)
    parse_race(html)    -> full detail for one race: post time, distance,
                           surface, and every horse's program number, odds, ML
    odds_live(race)     -> whether betting has opened on a race (odds moved off the morning line)
    race_finished(html) -> whether a race page has dropped its countdown (race official)
    pick5s(text)        -> the Pick 5s that start with a race, from its bet listing

How NYRA's pages move through a race (watched live, Belmont races 1-4, Oct 2 2026):
  all day      later races show odds equal to the morning line: betting on a race
               only opens once the race before it is over
  post time    countdown reaches 0 and stays there; nothing marks the start
  ~2 min after the off
               the post time is rewritten to the actual off time (1:43:00 -> 1:45:20).
               Not used: during a delay NYRA also shows passing post times
               (race 3, 2:16 -> 2:31:48), and the board once moved on too early.
  ~5-7 min after the off
               the NEXT race's odds go live (race 4 at ~2:38:30, race 3 off 2:31:48).
               The board moves to the next race here (Joe's call: surest signal).
  ~10 min after the off (official)
               the countdown disappears from the race page; the header moves to
               the next race within about a minute
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

NYRA_TZ = ZoneInfo("America/New_York")   # NYRA post times are Eastern
BASE_URL = "https://www.nyra.com"


def track_page_url(track):
    return f"{BASE_URL}/{track}/racing/"


def race_fragment_url(track, race_num):
    """Lightweight per-race page the NYRA site itself loads when you switch races."""
    return f"{BASE_URL}/{track}/rdl/race/?race={race_num}"


def race_page_url(track, race_num):
    """Full page for one race - fallback if the lightweight page ever changes."""
    return f"{BASE_URL}/{track}/racing/?race={race_num}"


def parse_post_time(value):
    """'2026-10-01T14:10:00' (Eastern, no zone) -> aware datetime."""
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=NYRA_TZ)


def minutes_to_post(post_time_iso, now=None):
    now = now or datetime.now(NYRA_TZ)
    secs = (parse_post_time(post_time_iso) - now).total_seconds()
    # Round up so "4 MTP" means post is within the next 4 minutes, like the tote board
    return max(0, int(-(-secs // 60)))


def current_race(html):
    """Race number and post time NYRA's page header is counting down to.
    Returns (race_number, post_time_iso) or (None, None) if nothing is upcoming."""
    soup = BeautifulSoup(html, "html.parser")
    badge = soup.find("span", class_="mtp-badge", attrs={"data-mtp-variant": "header"})
    if badge is None or not badge.get("data-post-time"):
        return None, None
    label = badge.find_previous_sibling("span")
    digits = "".join(c for c in (label.get_text() if label else "") if c.isdigit())
    if not digits:
        return None, None
    return digits, badge["data-post-time"]


def racing_on(html, day):
    """True if the track page is counting down to a race on `day` (an Eastern date).
    A track with no racing that day has no countdown, or one for a later day."""
    _, post_time = current_race(html)
    return bool(post_time) and parse_post_time(post_time).date() == day


def race_numbers(html):
    """Race numbers from the track page's race tabs, e.g. ['1', '2', ... '9']."""
    soup = BeautifulSoup(html, "html.parser")
    nums = set()
    for a in soup.find_all("a", attrs={"hx-get": True}):
        m = re.search(r"/rdl/race/\?race=(\d+)", a["hx-get"])
        if m:
            nums.add(m.group(1))
    return sorted(nums, key=int)


def runners(race):
    """Horses still in the race (scratches left out)."""
    return [h for h in race["horses"] if not h["odds"].upper().startswith("SCR")]


def card_states(card, next_race, now=None):
    """Label each race on today's card 'done', 'next' or 'later'.

    Uses the race NYRA's header is counting down to when known, since a race can
    go off after its scheduled post time; otherwise falls back to the post times."""
    nums = [c["race"] for c in card]
    if next_race in nums:
        n = int(next_race)
        return ["done" if int(r) < n else "next" if int(r) == n else "later" for r in nums]
    now = now or datetime.now(NYRA_TZ)
    states, found = [], False
    for c in card:
        if parse_post_time(c["post_time"]) <= now:
            states.append("done")
        elif not found:
            states.append("next")
            found = True
        else:
            states.append("later")
    return states


def odds_live(race):
    """True once betting has opened on a race: until then NYRA shows every horse at its
    morning line. Two horses off their ML is enough (race 4 went from 0 to 10 of 12 at once)."""
    moved = [h for h in runners(race) if h["ml"] and h["odds"] != h["ml"]]
    return len(moved) >= 2


def race_finished(html):
    """True if a race page still lists its horses but has dropped its countdown,
    which NYRA does once the race is official."""
    soup = BeautifulSoup(html, "html.parser")
    has_horses = soup.find("div", attrs={"title": "Current Odds"}) is not None
    has_countdown = soup.find("span", class_="mtp-badge", attrs={"data-mtp-variant": "default"}) is not None
    return has_horses and not has_countdown


def pick5s(wagers):
    """Pick 5s listed on a race's bets line - only the race each one starts with lists it.
    'Exacta ($1), ..., Grand Slam (5-8), Late Pick 5 (.50) (5-9)' ->
    [{"name": "Late Pick 5", "label": "LATE", "first": "5", "last": "9"}]
    Any number per day, any name ("Early", "Late", plain "Pick 5", ...)."""
    found = []
    for item in re.split(r",\s*(?=[A-Za-z])", wagers or ""):
        m = re.match(r"\s*(.*?)\s*Pick\s*5\b[^()]*\([^)]*\)\s*\((\d+)\s*-\s*(\d+)\)", item)
        if m:
            prefix = m.group(1).strip()
            found.append({"name": f"{prefix} Pick 5".strip(), "label": prefix.upper() or "PICK 5",
                          "first": m.group(2), "last": m.group(3)})
    return found


def _wagers_text(soup):
    """The race's bets line (Exacta, Trifecta, ... Pick 5), or '' if the page has none."""
    for div in soup.find_all("div"):
        if div.find("div") is None and re.search(r"\b(Exacta|Trifecta|Pick\s*\d)\b", div.get_text()):
            return div.get_text(" ", strip=True)
    return ""


def parse_race(html):
    """Detail for the race shown on the page, or None if the page layout isn't recognized."""
    soup = BeautifulSoup(html, "html.parser")

    badge = soup.find("span", class_="mtp-badge", attrs={"data-mtp-variant": "default"})
    if badge is None or not badge.get("data-post-time"):
        return None
    block = badge.find_parent("div", class_=lambda c: c and "items-baseline" in c)
    if block is None or block.find("header") is None:
        return None

    race_num = block.find("header").get_text(strip=True).replace("Race", "").strip()

    distance_div = block.find("div", attrs={"title": True})
    distance = distance_div.get_text(strip=True) if distance_div else ""
    surface = ""
    if distance_div:
        nxt = distance_div.find_next_sibling("div")
        surface = nxt.get_text(strip=True) if nxt else ""

    horses = []
    for odds_div in soup.find_all("div", attrs={"title": "Current Odds"}):
        row = odds_div.find_parent("div", class_=lambda c: c and "items-start" in c)
        if row is None:
            continue
        num_div = row.find("div", class_=lambda c: c and "order-1" in c)
        ml_div = row.find("div", attrs={"title": "Morning Line Odds"})
        horses.append({
            "program": num_div.get_text(strip=True) if num_div else "?",
            "odds": odds_div.get_text(strip=True),
            "ml": ml_div.get_text(strip=True).replace("ML", "").strip() if ml_div else "",
        })

    return {
        "race": race_num,
        "post_time": badge["data-post-time"],
        "distance": distance,
        "surface": surface,
        "horses": horses,
        "pick5s": pick5s(_wagers_text(soup)),
    }
