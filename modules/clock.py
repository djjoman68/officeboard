"""Clock & weather: time, date, temperature, 3-day forecast, sunrise and sunset, severe weather alerts.

The layout is itsposttime's clock & weather screen, which Joe signed off on there (itself from the plane
tracker): big clock top-left (orange by day, blue at night, red if sunrise/sunset are unknown),
temperature top-right (white to blue with humidity), date below it coloured by the moon phase, and a
3-day forecast with icons underneath. Near the end of each turn the forecast area shows the next
sunrise and sunset instead (itsposttime's sun panel). Severe weather alerts shrink the clock and show
under it, a new alert every 4 seconds.

Also draws the sleep mode screen: time and date only.

Weather comes from Tomorrow.io (free key, Settings page) and alerts from the National Weather Service,
the same sources as itsposttime. Current conditions every 10 minutes, the forecast every hour, so a
free key's daily allowance is far from used up.
"""
import json
import logging
import os
from datetime import date, datetime, timedelta

import requests
from PIL import Image

import config
from core import layouts, pixels
from core.module import Module
from modules import nws

log = logging.getLogger("clock")

TOMORROW_URL = "https://api.tomorrow.io/v4"
TIMEOUT = (5, 20)
FETCH_SECONDS = 600                 # current conditions and alerts
FORECAST_SECONDS = 3600             # daily forecast, sunrise and sunset
STALE_SECONDS = 7200                # keep showing old weather this long when fetches fail
CACHE_FILE = os.path.join(config.BASE_DIR, ".cache", "weather.json")
ICON_DIR = os.path.join(config.BASE_DIR, "icons")
ICON_SIZE = 10
ALERT_SECONDS = 4

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Colours carried over from itsposttime's screens
CLOCK_DAY = (254, 167, 39)
CLOCK_NIGHT = (40, 183, 246)
CLOCK_UNKNOWN = (255, 0, 0)
TEMP_DRY = (255, 255, 255)
TEMP_HUMID = (12, 70, 230)
DAY_NAME = (236, 65, 123)
TEMP_MAX = (255, 113, 66)
TEMP_MIN = (66, 164, 244)
SUNRISE = (255, 214, 90)
SUNSET = (255, 120, 50)
ALERT_COLOURS = {"red": (255, 80, 80), "orange": (254, 167, 39), "yellow": (255, 255, 0)}
PURPLE, LILAC, GREY, WHITE = (143, 37, 170), (199, 146, 212), (192, 192, 192), (255, 255, 255)
MOON = [(PURPLE, PURPLE), (PURPLE, LILAC), (PURPLE, WHITE), (LILAC, WHITE),
        (GREY, GREY), (WHITE, LILAC), (WHITE, PURPLE), (LILAC, PURPLE)]
SLEEP_DATE = (150, 150, 150)


# ---------- data ----------
def _local(iso):
    """A UTC time from Tomorrow.io ("2026-10-22T11:09:00Z") as local time without a zone."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


def parse_realtime(body):
    v = body["data"]["values"]
    if v.get("temperature") is None:
        raise ValueError("no temperature in Tomorrow.io's reply")
    return {"temp": v["temperature"], "humidity": v.get("humidity"), "code": v.get("weatherCode")}


def parse_forecast(body, today):
    """Days from today on: date, icon code, low, high, sunrise, sunset, moon phase."""
    days = []
    for iv in body["data"]["timelines"][0]["intervals"]:
        v = iv["values"]
        day = datetime.fromisoformat(iv["startTime"].replace("Z", "+00:00")).date()
        if day < today:
            continue
        days.append({
            "date": day, "code": v.get("weatherCodeFullDay"),
            "min": v.get("temperatureMin"), "max": v.get("temperatureMax"),
            "sunrise": _local(v["sunriseTime"]) if v.get("sunriseTime") else None,
            "sunset": _local(v["sunsetTime"]) if v.get("sunsetTime") else None,
            "moon": v.get("moonPhase"),
        })
    if not days:
        raise ValueError("no forecast days in Tomorrow.io's reply")
    return days


def _encode(obj):
    if isinstance(obj, (datetime, date)):
        return {"__dt__": obj.isoformat(), "d": not isinstance(obj, datetime)}
    raise TypeError(type(obj))


def _decode(d):
    if "__dt__" in d:
        return date.fromisoformat(d["__dt__"]) if d["d"] else datetime.fromisoformat(d["__dt__"])
    return d


def save_cache(data, path=None):
    path = path or CACHE_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(data, key=list(data["key"])), f, default=_encode)
        os.replace(tmp, path)
    except Exception as e:
        log.warning("couldn't save the weather cache: %s", e)


def load_cache(path=None):
    path = path or CACHE_FILE
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f, object_hook=_decode)
        data["key"] = tuple(data["key"])
        return data
    except Exception:
        return None


# ---------- drawing helpers ----------
def time_text(now, fmt):
    """ 9:05 or 21:05 (itsposttime's clock: space-padded hour in 12-hour mode)."""
    return f"{now.hour % 12 or 12:2d}:{now.minute:02d}" if fmt == "12hr" else f"{now.hour:02d}:{now.minute:02d}"


def short_time(t, fmt):
    """7:09a / 6:14p, or 19:09 in 24-hour mode (itsposttime's sun panel)."""
    if fmt == "24hr":
        return f"{t.hour:02d}:{t.minute:02d}"
    return f"{t.hour % 12 or 12}:{t.minute:02d}{'a' if t.hour < 12 else 'p'}"


def blend(a, b, f):
    f = max(0.0, min(1.0, f))
    return tuple(int(x + (y - x) * f) for x, y in zip(a, b))


def centred(img, font, text, y, colour, x0=0, x1=64):
    w = pixels.text_width(font, text)
    pixels.draw_text(img, font, x0 + max(0, (x1 - x0 - w) // 2), y, colour, text)


# Tomorrow.io weather codes as short words for the scrolling layouts
CONDITIONS = {
    1000: "CLEAR", 1100: "MOSTLY CLEAR", 1101: "PARTLY CLOUDY", 1102: "MOSTLY CLOUDY", 1001: "CLOUDY",
    2000: "FOG", 2100: "LIGHT FOG", 4000: "DRIZZLE", 4001: "RAIN", 4200: "LIGHT RAIN", 4201: "HEAVY RAIN",
    5000: "SNOW", 5001: "FLURRIES", 5100: "LIGHT SNOW", 5101: "HEAVY SNOW", 6000: "FREEZING DRIZZLE",
    6001: "FREEZING RAIN", 6200: "LIGHT FREEZING RAIN", 6201: "HEAVY FREEZING RAIN", 7000: "SLEET",
    7101: "HEAVY SLEET", 7102: "LIGHT SLEET", 8000: "STORMS",
}
CONDITION_GROUPS = {1: "CLOUDY", 2: "FOG", 4: "RAIN", 5: "SNOW", 6: "FREEZING RAIN", 7: "SLEET", 8: "STORMS"}


def condition(code):
    """A word or two for a weather code ("PARTLY CLOUDY"); mixed codes fall back to their group."""
    if not isinstance(code, int):
        return ""
    code = code // 10 if code >= 10000 else code
    return CONDITIONS.get(code) or CONDITION_GROUPS.get(code // 1000, "")


_icons = {}


def icon(code):
    """Weather icon for a Tomorrow.io code, 10x10. 5-digit day/night codes fall back to the 4-digit one."""
    if code in _icons:
        return _icons[code]
    img = None
    for name in (code, (code // 10) if isinstance(code, int) and code >= 10000 else None):
        if name is None:
            continue
        try:
            img = Image.open(os.path.join(ICON_DIR, f"{name}.png")).convert("RGB")
            img.thumbnail((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
            break
        except (FileNotFoundError, OSError):
            img = None
    _icons[code] = img
    return img


class ClockWeather(Module):
    id = "clock"
    name = "Clock & weather"
    description = "Date, time, current weather, 3-day forecast, sunrise and sunset."
    default_enabled = True
    default_seconds = 20
    fetch_seconds = FETCH_SECONDS
    fields = [
        {"key": "sun_seconds", "label": "Sunrise & sunset at the end of each turn (seconds)", "type": "int",
         "default": 6, "min": 0, "max": 60, "hint": "Shown in place of the forecast. 0 never shows them."},
    ]

    def __init__(self, board=None):
        super().__init__(board)
        cached = load_cache()
        if cached and cached.get("current_at") and \
                (datetime.now() - cached["current_at"]).total_seconds() < STALE_SECONDS:
            self.data = cached                 # weather straight after a restart
        self._frame_key = None
        self._frame = None

    # ---------- fetching ----------
    def fetch(self, now):
        loc = self.board.location
        key = (loc["weather_location"], loc["units"])
        api_key = config.load_secrets().get("tomorrow_api_key", "").strip()
        if not loc["weather_location"] or not api_key:
            raise ValueError("Add the weather location and Tomorrow.io key under Settings")
        prev = self.data if self.data and self.data.get("key") == key else {}
        data = {"key": key, "current": None, "current_at": None, "days": [], "days_at": None, "alerts": []}
        problems = []

        def still_fresh(at, seconds):
            return at is not None and (now - at).total_seconds() < seconds

        try:
            r = requests.get(f"{TOMORROW_URL}/weather/realtime", timeout=TIMEOUT,
                             params={"location": key[0], "units": key[1], "apikey": api_key})
            r.raise_for_status()
            data["current"], data["current_at"] = parse_realtime(r.json()), now
        except Exception as e:
            problems.append(f"current weather: {self._why(e)}")
            if still_fresh(prev.get("current_at"), STALE_SECONDS):
                data["current"], data["current_at"] = prev["current"], prev["current_at"]

        if still_fresh(prev.get("days_at"), FORECAST_SECONDS) and prev["days_at"].date() == now.date():
            data["days"], data["days_at"] = prev["days"], prev["days_at"]
        else:
            try:
                r = requests.post(f"{TOMORROW_URL}/timelines", timeout=TIMEOUT, params={"apikey": api_key},
                                  headers={"Accept-Encoding": "gzip", "accept": "application/json"},
                                  json={"location": key[0], "units": key[1], "timezone": "auto",
                                        "dailyStartHour": 6, "timesteps": ["1d"],
                                        "fields": ["temperatureMin", "temperatureMax", "weatherCodeFullDay",
                                                   "sunriseTime", "sunsetTime", "moonPhase"],
                                        "endTime": (now + timedelta(days=4)).astimezone().isoformat()})
                r.raise_for_status()
                data["days"], data["days_at"] = parse_forecast(r.json(), now.date()), now
            except Exception as e:
                problems.append(f"forecast: {self._why(e)}")
                if prev.get("days"):
                    data["days"], data["days_at"] = [d for d in prev["days"] if d["date"] >= now.date()], \
                        prev["days_at"]

        if loc["weather_alerts"]:
            try:
                lat, lon = key[0].split(",")
                data["alerts"] = nws.fetch_alerts(lat, lon)
            except Exception as e:
                problems.append(f"weather alerts: {self._why(e)}")
                data["alerts"] = prev.get("alerts", [])

        if data["current"] is None and not data["days"] and problems:
            raise RuntimeError("; ".join(problems))
        self.warning = "; ".join(problems) or None
        save_cache(data)
        return data

    @staticmethod
    def _why(e):
        if isinstance(e, requests.HTTPError) and e.response is not None:
            code = e.response.status_code
            return {401: "Tomorrow.io key not accepted", 403: "Tomorrow.io key not accepted",
                    429: "Tomorrow.io's free limit reached, will retry"}.get(code, f"error {code}")
        if isinstance(e, requests.ConnectionError):
            return "no connection"
        return str(e) or type(e).__name__

    # ---------- reading the data ----------
    def _days(self, now):
        return [d for d in (self.data or {}).get("days", []) if d["date"] >= now.date()]

    def _today(self, now):
        return next((d for d in self._days(now) if d["date"] == now.date()), None)

    def clock_colour(self, now):
        today = self._today(now)
        if not today or not today["sunrise"] or not today["sunset"]:
            return CLOCK_UNKNOWN
        return CLOCK_DAY if today["sunrise"] <= now < today["sunset"] else CLOCK_NIGHT

    def sun_times(self, now):
        """(next sunrise, next sunset) after `now`, or None if not known."""
        days = self._days(now)
        rise = next((d["sunrise"] for d in days if d["sunrise"] and d["sunrise"] > now), None)
        sets = next((d["sunset"] for d in days if d["sunset"] and d["sunset"] > now), None)
        return (rise, sets) if rise and sets else None

    def alerts(self, now):
        if not self.board.location["weather_alerts"]:
            return []
        return (self.data or {}).get("alerts", [])

    # ---------- drawing ----------
    def has_content(self, now):
        return True             # the clock always has something to show, weather or not

    def pages(self, now):
        """The forecast screen, then sunrise and sunset."""
        alerts = self.alerts(now)
        alert = alerts[int(now.timestamp() // ALERT_SECONDS) % len(alerts)] if alerts else None
        key = (now.strftime("%Y-%m-%d %H:%M"), repr(alert), id(self.data), self.board.location["clock_format"])
        if getattr(self, "_pages_key", None) != key:
            self._pages = [self.draw(now, "forecast", alert)]
            if self.sun_times(now):
                self._pages.append(self.draw(now, "sun", alert))
            self._pages_key = key
        return self._pages

    def ticker_items(self, now):
        """For the scrolling layouts: alerts, the time (full ticker only; the split layout's top bar
        has it), the date, now, today, tomorrow, sunrise and sunset."""
        fmt = self.board.location["clock_format"]
        items = [[(a["text"], ALERT_COLOURS.get(a["color"], ALERT_COLOURS["orange"]))] for a in self.alerts(now)]
        if self.layout() == "ticker":
            items.append([(time_text(now, fmt).strip(), self.clock_colour(now))])
        items.append([(f"{DAYS[now.weekday()]} {MONTHS[now.month - 1]} {now.day}".upper(), WHITE)])
        current = (self.data or {}).get("current")
        if current:
            items.append([(f"{round(current['temp'])}°", blend(TEMP_DRY, TEMP_HUMID, (current.get("humidity") or 0) / 100)),
                          (f" {condition(current.get('code'))}", WHITE)])
        for i, day in enumerate(self._days(now)[:2]):
            if day["min"] is None or day["max"] is None:
                continue
            name = "TODAY" if day["date"] == now.date() else DAYS[day["date"].weekday()].upper()
            items.append([(name + " ", DAY_NAME), (f"{day['max']:.0f}", TEMP_MAX), ("/", pixels.DIM),
                          (f"{day['min']:.0f}", TEMP_MIN), (f" {condition(day['code'])}", WHITE)])
        sun = self.sun_times(now)
        if sun:
            items.append([("↑ ", SUNRISE), (short_time(sun[0], fmt), SUNRISE),
                          ("  ↓ ", SUNSET), (short_time(sun[1], fmt), SUNSET)])
        return items

    def status_bar(self, now):
        """The split layout's top bar: time on the left, temperature on the right."""
        bar = Image.new("RGB", (pixels.WIDTH, 9), pixels.BLACK)
        pixels.draw_text(bar, "small", 1, 7, self.clock_colour(now), time_text(now, self.board.location["clock_format"]).strip())
        current = (self.data or {}).get("current")
        if current:
            text = f"{round(current['temp'])}°"
            colour = blend(TEMP_DRY, TEMP_HUMID, (current.get("humidity") or 0) / 100)
            pixels.draw_text(bar, "small", 63 - pixels.text_width("small", text), 7, colour, text)
        return bar

    def frame(self, now, t):
        """Roll layout: as pages, but sunrise and sunset slide up over the forecast instead of
        appearing. Other layouts as for every module."""
        if self.layout() != "roll":
            return super().frame(now, t)
        img = self.page_frame(now, t)
        secs, sun_secs = self.settings["seconds"], self.settings["sun_seconds"]
        into = (t % secs) - (secs - sun_secs)
        if self.sun_times(now) and sun_secs and 0 <= into < layouts.ROLL_SECONDS:
            return layouts.slide(self.page_frame(now, t - into - 0.001), img, into)
        return img

    def turn_length(self, now):
        """The clock's turn is its own setting: sunrise and sunset share the turn with the forecast."""
        if self.layout() in ("pages", "roll"):
            return self.settings["seconds"]
        return super().turn_length(now)

    def page_frame(self, now, t):
        """Pages layout: the forecast screen, with sunrise and sunset for the last few seconds of the turn."""
        sun = self.sun_times(now)
        secs, sun_secs = self.settings["seconds"], self.settings["sun_seconds"]
        page = "sun" if sun and sun_secs and (t % secs) >= secs - sun_secs else "forecast"
        alerts = self.alerts(now)
        slot = int(now.timestamp() // ALERT_SECONDS) % len(alerts) if alerts else None
        key = (now.strftime("%Y-%m-%d %H:%M"), page, slot, id(self.data), self.board.location["clock_format"])
        if key != self._frame_key:
            self._frame = self.draw(now, page, alerts[slot] if alerts else None)
            self._frame_key = key
        return self._frame

    def draw(self, now, page, alert=None):
        img = pixels.blank()
        self._draw_top(img, now, alert)
        if page == "sun":
            self._draw_sun(img, now)
        else:
            self._draw_forecast(img, now)
        return img

    def _draw_top(self, img, now, alert):
        fmt = self.board.location["clock_format"]
        colour = self.clock_colour(now)
        if alert:
            centred(img, "small", time_text(now, fmt).strip(), 6, colour, 0, 40)
            centred(img, "tiny", alert["text"], 11, ALERT_COLOURS.get(alert["color"], ALERT_COLOURS["orange"]), 0, 40)
        else:
            pixels.draw_text(img, "large_bold", 0, 11, colour, time_text(now, fmt))

        current = (self.data or {}).get("current")
        if current:
            text = f"{round(current['temp'])}°"
            humidity = current.get("humidity")
            temp_colour = blend(TEMP_DRY, TEMP_HUMID, (humidity or 0) / 100)
        else:
            text, temp_colour = ":(", CLOCK_UNKNOWN
        centred(img, "small", text, 6, temp_colour, 40, 64)

        label = f"{MONTHS[now.month - 1]} {now.day:02d}"
        today = self._today(now)
        moon = today.get("moon") if today else None
        start, end = MOON[min(max(int(moon), 0), 7)] if moon is not None else (CLOCK_UNKNOWN, CLOCK_UNKNOWN)
        x = 40
        for i, ch in enumerate(label):
            x += pixels.draw_text(img, "tiny", x, 11, blend(start, end, i / (len(label) - 1)), ch)

    def _draw_forecast(self, img, now):
        width = 64 // 3
        offset = 1
        for day in self._days(now)[:3]:
            if day["min"] is None or day["max"] is None:
                offset += width
                continue
            name = DAYS[day["date"].weekday()]
            hi, lo = f"{day['max']:.0f}", f"{day['min']:.0f}"
            pixels.draw_text(img, "tiny", offset + (width - pixels.text_width("tiny", name)) // 2 + 1, 17,
                             DAY_NAME, name)
            ic = icon(day["code"])
            if ic is not None:
                img.paste(ic, (offset + (width - ICON_SIZE) // 2, 17))
            hi_w, lo_w = pixels.text_width("tiny", hi), pixels.text_width("tiny", lo)
            x = offset + (width - hi_w - lo_w - 1) // 2 + 1
            pixels.draw_text(img, "tiny", x, 32, TEMP_MAX, hi)
            pixels.draw_text(img, "tiny", x + hi_w, 32, TEMP_MIN, lo)
            offset += width

    def _draw_sun(self, img, now):
        rise, sets = self.sun_times(now)
        fmt = self.board.location["clock_format"]
        for y, arrow, word, when, colour in ((21, "↑", "RISE", rise, SUNRISE), (30, "↓", "SET", sets, SUNSET)):
            label = short_time(when, fmt)
            pixels.draw_text(img, "small", 3, y, colour, arrow)
            pixels.draw_text(img, "small", 11, y, WHITE, word)
            pixels.draw_text(img, "small", 63 - pixels.text_width("small", label), y, colour, label)

    def sleep_frame(self, now):
        """Sleep mode: time and date only."""
        img = pixels.blank()
        centred(img, "large_bold", time_text(now, self.board.location["clock_format"]).strip(), 16,
                self.clock_colour(now))
        label = f"{DAYS[now.weekday()]} {MONTHS[now.month - 1]} {now.day}".upper()
        centred(img, "small", label, 28, SLEEP_DATE)
        return img
