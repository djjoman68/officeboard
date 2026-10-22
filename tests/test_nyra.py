"""NYRA module: rotation, today's card, hold near post, take-over, sleep. No internet: a stand-in feed."""
import unittest
from datetime import datetime, timedelta

import support  # noqa: F401  (stand-in panel library, paths)
from support import TempFiles

import config
from core.display import Display
from core.module import BoardInfo, Module
from core.scheduler import Scheduler
from modules.nyra import Nyra
from racing import nyra
from racing import render as rr
from rgbmatrix import RGBMatrix
from test_nyra_reader import PAGE

SAMPLE_CARD = [  # Belmont, Oct 2 2026 (from itsposttime's tests)
    {"race": "1", "post_time": "2026-10-02T13:10:00", "distance": "7F", "surface": "Dirt", "runners": 9},
    {"race": "2", "post_time": "2026-10-02T13:43:00", "distance": "6 1/2F", "surface": "Turf", "runners": 7},
    {"race": "3", "post_time": "2026-10-02T14:16:00", "distance": "6 1/2F", "surface": "Turf", "runners": 7,
     "pick5s": [{"name": "Late Pick 5", "label": "LATE", "first": "3", "last": "7"}]},
    {"race": "4", "post_time": "2026-10-02T14:49:00", "distance": "6F", "surface": "Dirt", "runners": 13},
    {"race": "5", "post_time": "2026-10-02T15:23:00", "distance": "1 1/16M", "surface": "Turf", "runners": 16},
]
NOON = datetime(2026, 10, 2, 12, 0)


class FakeFeed:
    """Stands in for racing.feed.RaceFeed: the test sets what it 'read'."""

    def __init__(self, track="belmont", card=SAMPLE_CARD, next_race="3", race=None):
        self.track, self.card, self.next_race, self._race = track, card, next_race, race
        self.last_update = self.last_error = None
        self.refreshed = 0

    @property
    def race(self):
        return dict(self._race) if self._race else None

    def refresh_now(self):
        self.refreshed += 1

    def start(self):
        pass


def race_at(mtp):
    """The sample race with its post time `mtp` minutes from now."""
    post = (datetime.now(nyra.NYRA_TZ) + timedelta(minutes=mtp, seconds=-30)).replace(tzinfo=None)
    return dict(nyra.parse_race(PAGE), post_time=post.isoformat(timespec="seconds"), track="belmont")


def module(feed=None, **settings):
    m = Nyra(BoardInfo())
    m.feed = feed or FakeFeed()
    m.settings = dict(m.settings, enabled=True, **settings)
    return m


class Other(Module):
    id = name = "other"

    def __init__(self):
        super().__init__()
        self.settings["enabled"] = True


class TestRotation(unittest.TestCase):
    def test_no_racing_today_is_skipped(self):
        self.assertFalse(module(FakeFeed(track=None, card=[])).has_content(NOON))

    def test_card_before_the_race_window_from_card_start(self):
        m = module()
        self.assertFalse(m.has_content(NOON.replace(hour=8)))          # before 9am
        self.assertTrue(m.has_content(NOON))
        rows, seqs = m.card_screen(NOON)
        self.assertEqual([r["race"] for r in rows], ["3", "4", "5"])   # races still to come
        self.assertEqual([p["label"] for p in seqs], ["LATE"])
        pages = m.pages(NOON)
        self.assertEqual(pages[0].tobytes(), rr.render_card("belmont", rows, 0).tobytes())
        self.assertEqual(len(pages), 2)                                # 3 races on one page + the Pick 5 page

    def test_card_gone_once_racing_is_over(self):
        m = module(FakeFeed(next_race=None))
        self.assertFalse(m.has_content(NOON.replace(hour=18)))

    def test_race_board_in_the_window(self):
        m = module(FakeFeed(race=race_at(25)))
        pages = m.pages(NOON)
        race = dict(m.race(), mtp=25)
        self.assertEqual(pages[0].tobytes(), rr.render_full_board(race, 0).tobytes())
        m.settings["view"] = "big_mtp"
        self.assertEqual(len(m.pages(NOON)), 1)

    def test_ticker_text(self):
        words = ["".join(t for t, _ in i) for i in module(FakeFeed(race=race_at(7))).ticker_items(NOON)]
        self.assertEqual(words[0], "BEL R3 7 MTP")
        self.assertIn("#1 5/2", words)
        card_words = ["".join(t for t, _ in i) for i in module().ticker_items(NOON)]
        self.assertEqual(card_words[:2], ["BELMONT TODAY", "R3 2:16p 6.5F TRF"])


class TestNearPostAndTakeOver(unittest.TestCase):
    def pick(self, m, at):
        other = Other()
        s = Scheduler()
        s.pick([other, m], NOON, 0)                     # the other module's turn
        return s, other, s.pick([other, m], NOON, at)[0].id

    def test_twenty_minutes_out_waits_its_turn(self):
        self.assertEqual(self.pick(module(FakeFeed(race=race_at(20))), 1)[2], "other")

    def test_three_mtp_comes_on_and_stays(self):
        m = module(FakeFeed(race=race_at(3)))
        s, other, now_on = self.pick(m, 1)
        self.assertEqual(now_on, "nyra")
        self.assertEqual(s.pick([other, m], NOON, 300)[0].id, "nyra")       # still there 5 minutes later
        m.feed._race = None                                                  # board moved on
        self.assertEqual(s.pick([other, m], NOON, 301)[0].id, "other")

    def test_near_post_can_be_turned_off_or_moved(self):
        self.assertEqual(self.pick(module(FakeFeed(race=race_at(3)), hold=False), 1)[2], "other")
        self.assertEqual(self.pick(module(FakeFeed(race=race_at(5)), hold_mtp=5), 1)[2], "nyra")

    def test_take_over_holds_the_whole_window(self):
        self.assertEqual(self.pick(module(FakeFeed(race=race_at(60)), takeover=True), 1)[2], "nyra")
        # before the window (just the card): rotation as usual
        self.assertEqual(self.pick(module(takeover=True), 1)[2], "other")

    def test_changing_track_or_turning_on_refreshes_the_feed(self):
        m = module()
        m.configure(dict(m.settings, track="saratoga"))
        m.configure(dict(m.settings, enabled=False))
        self.assertEqual(m.feed.refreshed, 2)


class TestOnTheBoard(TempFiles):
    def board(self, feed, **nyra_settings):
        config.save({"sleep": {"enabled": True, "start": "00:00", "end": "23:59"},
                     "modules": {"nyra": dict({"enabled": True, "takeover": True}, **nyra_settings),
                                 "paneltest": {"enabled": False}}})
        d = Display(matrix=RGBMatrix(), start_fetchers=False)
        d.modules["nyra"].feed = feed
        return d

    def test_sleep_beats_take_over(self):
        d = self.board(FakeFeed(race=race_at(10)))
        d.step(NOON, 0.0)
        self.assertTrue(d.asleep)
        self.assertIsNone(d.current)

    def test_status_for_todays_card(self):
        d = self.board(FakeFeed())
        d.modules["nyra"].settings["enabled"] = True
        st = d.modules["nyra"].status()
        self.assertEqual(st["track"], "belmont")
        self.assertEqual([c["state"] for c in st["card"]][:3], ["done", "done", "next"])

    def test_feed_idles_while_the_module_is_off(self):
        from racing.feed import IDLE_CHECK_SECONDS, RaceFeed
        feed = RaceFeed(lambda: None, start=False)
        feed._get = lambda url: self.fail("no polling while off")
        self.assertEqual(feed._cycle(), IDLE_CHECK_SECONDS)
        self.assertIsNone(feed.track)


if __name__ == "__main__":
    unittest.main()
