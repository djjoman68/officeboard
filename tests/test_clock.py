"""Clock & weather module and sleep mode. Sample weather, no internet."""
import json
import os
import unittest
from datetime import datetime, timedelta

import support  # noqa: F401  (stand-in panel library, paths)
from support import colours
from support import TempFiles

import config
import requests
from core import pixels, sleep
from core.display import Display
from core.module import BoardInfo
from modules import clock
from rgbmatrix import RGBMatrix

NOW = datetime(2026, 10, 22, 10, 44)          # a Thursday morning


def sample_data(now=NOW, alerts=()):
    days = []
    for i, (code, lo, hi, moon) in enumerate([(1100, 61, 73, 3), (4001, 58, 66, 3), (1000, 55, 70, 4)]):
        d = now.date() + timedelta(days=i)
        days.append({"date": d, "code": code, "min": lo, "max": hi, "moon": moon,
                     "sunrise": datetime(d.year, d.month, d.day, 7, 9), "sunset": datetime(d.year, d.month, d.day, 18, 14)})
    return {"key": ("40.72,-73.70", "imperial"), "current": {"temp": 72.4, "humidity": 40, "code": 10000},
            "current_at": now, "days": days, "days_at": now, "alerts": list(alerts)}


def module(data=None, **location):
    m = clock.ClockWeather(BoardInfo(location=config.normalize_location(location)))
    m.data = data
    return m


class TestClockScreens(unittest.TestCase):
    def test_time_text(self):
        self.assertEqual(clock.time_text(datetime(2026, 1, 1, 9, 5), "12hr"), " 9:05")
        self.assertEqual(clock.time_text(datetime(2026, 1, 1, 21, 5), "12hr"), " 9:05")
        self.assertEqual(clock.time_text(datetime(2026, 1, 1, 21, 5), "24hr"), "21:05")
        self.assertEqual(clock.short_time(datetime(2026, 1, 1, 18, 14), "12hr"), "6:14p")
        self.assertEqual(clock.short_time(datetime(2026, 1, 1, 7, 9), "24hr"), "07:09")

    def test_clock_colour_day_night_unknown(self):
        m = module(sample_data())
        self.assertEqual(m.clock_colour(NOW), clock.CLOCK_DAY)
        self.assertEqual(m.clock_colour(NOW.replace(hour=20)), clock.CLOCK_NIGHT)
        self.assertEqual(module(None).clock_colour(NOW), clock.CLOCK_UNKNOWN)

    def test_todays_sunrise_and_sunset(self):
        m = module(sample_data())
        today = (datetime(2026, 10, 22, 7, 9), datetime(2026, 10, 22, 18, 14))
        self.assertEqual(m.today_sun(NOW), today)
        self.assertEqual(m.today_sun(NOW.replace(hour=19)), today)      # still today's after sunset
        self.assertIsNone(module(None).today_sun(NOW))

    def test_one_screen_with_todays_weather_and_sun(self):
        """Joe's one-page design (Oct 22 2026): time, temperature, date; today's icon, high and low;
        today's sunrise and sunset. No other days, no second screen."""
        m = module(sample_data())
        self.assertEqual(len(m.pages(NOW)), 1)
        img = m.draw(NOW)
        self.assertIsNotNone(img.crop((0, 0, 40, 12)).getbbox())       # clock
        self.assertIsNotNone(img.crop((40, 0, 64, 6)).getbbox())       # temperature
        self.assertIsNotNone(img.crop((40, 6, 64, 12)).getbbox())      # date
        middle, bottom = colours(img.crop((0, 12, 64, 22))), colours(img.crop((0, 22, 64, 32)))
        self.assertIn(clock.TEMP_MAX, middle)                          # today's high...
        self.assertIn(clock.TEMP_MIN, middle)                          # ...and low
        self.assertIn(clock.SUNRISE, bottom)
        self.assertIn(clock.SUNSET, bottom)
        self.assertNotIn(clock.DAY_NAME, colours(img))                 # no day names: today only

    def test_same_screen_all_turn(self):
        m = module(sample_data())
        self.assertEqual(m.frame(NOW, 2).tobytes(), m.frame(NOW, 15).tobytes())

    def test_without_weather_the_clock_still_shows(self):
        m = module(None)
        self.assertTrue(m.has_content(NOW))
        img = m.frame(NOW, 0)
        self.assertIn(clock.CLOCK_UNKNOWN, colours(img))         # red clock and ":("
        self.assertIsNone(img.crop((0, 12, 64, 32)).getbbox())         # no forecast

    def test_alert_shrinks_the_clock(self):
        m = module(sample_data(alerts=[{"text": "TORN WRN", "color": "red"}]))
        img = m.frame(NOW, 0)
        self.assertIn(clock.ALERT_COLOURS["red"], colours(img))
        self.assertNotIn(clock.CLOCK_DAY, colours(img.crop((0, 7, 40, 12))))   # small clock, top rows only
        m.board.location["weather_alerts"] = False
        self.assertNotIn(clock.ALERT_COLOURS["red"], colours(m.frame(NOW, 0)))

    def test_sleep_screen_is_time_and_date_only(self):
        img = module(sample_data()).sleep_frame(NOW)
        self.assertIn(clock.CLOCK_DAY, colours(img))
        self.assertIn(clock.SLEEP_DATE, colours(img))
        self.assertNotIn(clock.DAY_NAME, colours(img))

    def test_frames_are_reused_within_the_minute(self):
        m = module(sample_data())
        self.assertIs(m.frame(NOW, 1), m.frame(NOW + timedelta(seconds=20), 2))


REALTIME = {"data": {"values": {"temperature": 72.4, "humidity": 40, "weatherCode": 1000}}}
FORECAST = {"data": {"timelines": [{"intervals": [
    {"startTime": "2026-10-21T06:00:00-04:00", "values": {"temperatureMin": 50, "temperatureMax": 60,
     "weatherCodeFullDay": 1000, "sunriseTime": "2026-10-21T11:08:00Z", "sunsetTime": "2026-10-21T22:15:00Z", "moonPhase": 2}},
    {"startTime": "2026-10-22T06:00:00-04:00", "values": {"temperatureMin": 61, "temperatureMax": 73,
     "weatherCodeFullDay": 1100, "sunriseTime": "2026-10-22T11:09:00Z", "sunsetTime": "2026-10-22T22:14:00Z", "moonPhase": 3}},
]}]}}


class FakeHTTP:
    """Stands in for requests.get/post: answers by URL, or fails."""

    def __init__(self, fail=()):
        self.fail, self.calls = set(fail), []

    def reply(self, url, **kw):
        self.calls.append(url)
        name = "realtime" if "realtime" in url else "timelines" if "timelines" in url else "alerts"
        if name in self.fail:
            raise requests.ConnectionError("offline")
        body = {"realtime": REALTIME, "timelines": FORECAST, "alerts": {"features": [
            {"properties": {"severity": "Severe", "event": "Tornado Warning"}},
            {"properties": {"severity": "Minor", "event": "Frost Advisory"}}]}}[name]

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return body
        return Resp()


class TestWeatherFetching(TempFiles):
    def setUp(self):
        super().setUp()
        self.http = FakeHTTP()
        self._saved_http = (clock.requests.get, clock.requests.post, clock.nws.requests.get)
        clock.requests.get = clock.requests.post = clock.nws.requests.get = self.http.reply
        config.save({"key": 1}, config.SEC_PATH)
        config.save({"tomorrow_api_key": "abc123"}, config.SEC_PATH)
        self.m = module(None, weather_location="40.72,-73.70")

    def tearDown(self):
        clock.requests.get, clock.requests.post, clock.nws.requests.get = self._saved_http
        super().tearDown()

    def test_parses_the_forecast_from_today_on(self):
        days = clock.parse_forecast(FORECAST, NOW.date())
        self.assertEqual([d["date"].day for d in days], [22])
        self.assertEqual((days[0]["min"], days[0]["max"], days[0]["code"], days[0]["moon"]), (61, 73, 1100, 3))
        expected = datetime.fromisoformat("2026-10-22T11:09:00+00:00").astimezone().replace(tzinfo=None)
        self.assertEqual(days[0]["sunrise"], expected)

    def test_fetch_gets_current_forecast_and_severe_alerts(self):
        self.m.refresh(NOW)
        d = self.m.data
        self.assertEqual(d["current"]["temp"], 72.4)
        self.assertEqual(len(d["days"]), 1)
        self.assertEqual(d["alerts"], [{"text": "TORN WRN", "color": "red"}])   # tornado: always red
        self.assertIsNone(self.m.last_error)
        self.assertTrue(os.path.exists(clock.CACHE_FILE))

    def test_forecast_fetched_hourly_not_every_time(self):
        self.m.refresh(NOW)
        self.m.refresh(NOW + timedelta(minutes=10))
        self.assertEqual(sum("timelines" in c for c in self.http.calls), 1)
        self.m.refresh(NOW + timedelta(minutes=61))
        self.assertEqual(sum("timelines" in c for c in self.http.calls), 2)

    def test_partial_failure_keeps_old_data_and_says_so(self):
        self.m.refresh(NOW)
        self.http.fail = {"realtime"}
        self.m.refresh(NOW + timedelta(minutes=10))
        self.assertEqual(self.m.data["current"]["temp"], 72.4)          # last good reading kept
        self.assertIn("current weather: no connection", self.m.last_error)

    def test_missing_key_or_location_explains_where_to_add_them(self):
        config.save({}, config.SEC_PATH)
        self.m.refresh(NOW)
        self.assertIn("Settings", self.m.last_error)
        self.assertEqual(self.http.calls, [])

    def test_everything_failing_is_an_error(self):
        self.http.fail = {"realtime", "timelines", "alerts"}
        self.m.refresh(NOW)
        self.assertIsNone(self.m.data)
        self.assertIn("no connection", self.m.last_error)

    def test_restart_shows_cached_weather(self):
        self.m.refresh(NOW)
        again = clock.ClockWeather()
        self.assertIsNotNone(again.data)
        cached = clock.load_cache()
        self.assertEqual(cached["days"][0]["date"], NOW.date())
        self.assertEqual(cached["key"], ("40.72,-73.70", "imperial"))

    def test_rate_limit_message(self):
        resp = requests.Response()
        resp.status_code = 429
        self.assertIn("free limit", clock.ClockWeather._why(requests.HTTPError(response=resp)))


def sleep_cfg(**kw):
    return config.normalize_sleep(dict({"enabled": True, "start": "18:00", "end": "07:00"}, **kw))


class TestSleepSchedule(unittest.TestCase):
    def test_overnight_window(self):
        cfg = sleep_cfg()
        self.assertFalse(sleep.scheduled(NOW, cfg))
        self.assertTrue(sleep.scheduled(NOW.replace(hour=18), cfg))
        self.assertTrue(sleep.scheduled(NOW.replace(hour=6, minute=59), cfg))
        self.assertFalse(sleep.scheduled(NOW.replace(hour=7), cfg))
        self.assertFalse(sleep.scheduled(NOW.replace(hour=20), sleep_cfg(enabled=False)))

    def test_daytime_window(self):
        cfg = sleep_cfg(start="12:00", end="13:00")
        self.assertTrue(sleep.scheduled(NOW.replace(hour=12, minute=30), cfg))
        self.assertFalse(sleep.scheduled(NOW.replace(hour=13), cfg))

    def test_all_day_on_weekends(self):
        cfg = sleep_cfg(all_day=["sat", "sun"])
        saturday_noon = datetime(2026, 10, 24, 12, 0)
        self.assertTrue(sleep.scheduled(saturday_noon, cfg))
        self.assertEqual(sleep.next_change(saturday_noon, cfg), datetime(2026, 10, 26, 7, 0))   # Monday 7am

    def test_next_change(self):
        cfg = sleep_cfg()
        self.assertEqual(sleep.next_change(NOW, cfg), datetime(2026, 10, 22, 18, 0))
        self.assertEqual(sleep.next_change(NOW.replace(hour=22), cfg), datetime(2026, 10, 23, 7, 0))
        self.assertIsNone(sleep.until(NOW, sleep_cfg(enabled=False)))

    def test_wake_now_lasts_until_the_schedule_wakes_anyway(self):
        night = NOW.replace(hour=22)
        cfg = sleep.override(night, sleep_cfg(), "wake")
        self.assertFalse(sleep.asleep(night, cfg))
        self.assertEqual(sleep.until(night, cfg), datetime(2026, 10, 23, 7, 0))
        self.assertFalse(sleep.asleep(datetime(2026, 10, 23, 8, 0), cfg))            # schedule again: awake
        self.assertTrue(sleep.asleep(datetime(2026, 10, 23, 19, 0), cfg))            # and asleep next night

    def test_sleep_now_until_the_evening_then_schedule(self):
        cfg = sleep.override(NOW, sleep_cfg(), "sleep")
        self.assertTrue(sleep.asleep(NOW, cfg))
        self.assertEqual(sleep.active_override(NOW, cfg), "sleep")
        self.assertTrue(sleep.asleep(NOW.replace(hour=19), cfg))                     # schedule takes over
        self.assertIsNone(sleep.active_override(NOW.replace(hour=19), cfg))

    def test_sleep_now_without_a_schedule_lasts_a_day_and_can_be_cancelled(self):
        cfg = sleep.override(NOW, sleep_cfg(enabled=False), "sleep")
        self.assertTrue(sleep.asleep(NOW + timedelta(hours=23), cfg))
        self.assertFalse(sleep.asleep(NOW + timedelta(hours=25), cfg))
        cancelled = sleep.override(NOW, cfg, "schedule")
        self.assertFalse(sleep.asleep(NOW, cancelled))

    def test_settings_are_made_safe(self):
        cfg = config.normalize_sleep({"start": "25:99", "all_day": ["sun", "xyz", "mon"], "brightness": -5,
                                      "override": "sleep", "override_until": "not a time"})
        self.assertEqual((cfg["start"], cfg["all_day"], cfg["brightness"], cfg["override"]),
                         ("18:00", ["mon", "sun"], 0, None))


class TestSleepOnThePanel(TempFiles):
    def board(self, **sleep_settings):
        config.save({"sleep": dict({"enabled": True, "start": "18:00", "end": "07:00", "brightness": 10},
                                   **sleep_settings)})
        d = Display(matrix=RGBMatrix(), start_fetchers=False)
        d.modules["clock"].data = sample_data()
        return d

    def test_asleep_shows_time_and_date_dimmed(self):
        d = self.board()
        img = d.step(NOW.replace(hour=22), 0.0)
        self.assertTrue(d.asleep)
        self.assertIsNone(d.current)
        self.assertEqual(d.matrix.brightness, 10)
        self.assertIn(clock.SLEEP_DATE, colours(img))
        self.assertNotIn(clock.DAY_NAME, colours(img))
        d.step(NOW, 1.0)                                       # morning: back to the rotation
        self.assertFalse(d.asleep)
        self.assertEqual(d.matrix.brightness, 80)
        self.assertEqual(d.current.id, "clock")

    def test_zero_brightness_is_a_dark_panel(self):
        d = self.board(brightness=0)
        self.assertIsNone(d.step(NOW.replace(hour=22), 0.0).getbbox())

    def test_status_says_asleep_until_when(self):
        d = self.board()
        d.step(datetime.now().replace(hour=22, minute=0), 0.0)
        d.asleep = True
        d.write_status()
        from core import display as disp
        with open(disp.STATUS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        self.assertIn("sleep_until", s)


class TestSleepWebPage(TempFiles):
    def setUp(self):
        super().setUp()
        try:
            import flask  # noqa: F401
        except ImportError:
            self.skipTest("Flask isn't installed")
        self.c = self.web.app.test_client()

    def test_buttons(self):
        r = self.c.post("/api/sleep", json={"action": "sleep"}).get_json()
        self.assertEqual(r["sleep"]["override"], "sleep")
        self.assertEqual(config.load()["sleep"]["override"], "sleep")
        self.c.post("/api/sleep", json={"action": "schedule"})
        self.assertIsNone(config.load()["sleep"]["override"])

    def test_settings_sections_save(self):
        self.c.post("/api/config", json={"config": {
            "location": {"weather_location": "40.72, -73.70", "clock_format": "24hr"},
            "sleep": {"enabled": True, "all_day": ["sat", "sun"], "start": "19:30"}}})
        d = self.c.get("/api/config").get_json()["config"]
        self.assertEqual(d["location"]["weather_location"], "40.72,-73.70")
        self.assertEqual(d["location"]["clock_format"], "24hr")
        self.assertEqual((d["sleep"]["all_day"], d["sleep"]["start"]), (["sat", "sun"], "19:30"))
        self.assertEqual(d["display"]["brightness"], 80)


if __name__ == "__main__":
    unittest.main()
