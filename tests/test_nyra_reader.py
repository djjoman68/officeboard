"""NYRA reader, race screens and race feed: itsposttime's tests, carried over with its code.
From itsposttime's tests/test_board.py. Modified for the office board: the feed takes its settings from
a function (the NYRA module's), and the display-loop tests are replaced by tests/test_nyra.py.

No internet: a synthetic sample page (tests/fixtures/race_page.html) stands in for nyra.com.
"""
import os
import re
import unittest
from datetime import datetime, timedelta

import support  # noqa: F401  (stand-in panel library, paths)

from racing import nyra
from racing import render as rr

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = open(os.path.join(HERE, "fixtures", "race_page.html"), encoding="utf-8").read()
SETTINGS = {"track": "auto", "window_minutes": 90, "poll_seconds": 20}


class TestNyraReader(unittest.TestCase):
    def test_current_race(self):
        self.assertEqual(nyra.current_race(PAGE), ("3", "2026-10-01T15:12:00"))

    def test_parse_race(self):
        r = nyra.parse_race(PAGE)
        self.assertEqual((r["race"], r["distance"], r["surface"]), ("3", "1 1/16M", "Turf"))
        self.assertEqual([h["program"] for h in r["horses"]], ["1", "2", "3", "4"])
        self.assertEqual(r["horses"][0], {"program": "1", "odds": "5/2", "ml": "3/1"})
        self.assertEqual(r["horses"][2]["odds"], "SCR")

    def test_mtp_rounds_up_and_uses_eastern_time(self):
        post = "2026-10-01T15:12:00"
        now = nyra.parse_post_time(post) - timedelta(minutes=3, seconds=10)
        self.assertEqual(nyra.minutes_to_post(post, now=now), 4)
        self.assertEqual(nyra.minutes_to_post(post, now=now + timedelta(hours=1)), 0)

    def test_unrecognized_page(self):
        self.assertIsNone(nyra.parse_race("<html>maintenance</html>"))
        self.assertEqual(nyra.current_race("<html></html>"), (None, None))


class TestDesignRules(unittest.TestCase):
    """The display rules Joe signed off on. Change only if he asks."""

    def test_mtp_colors(self):
        self.assertEqual(rr.mtp_color(11), rr.WHITE)
        self.assertEqual(rr.mtp_color(10), rr.YELLOW)
        self.assertEqual(rr.mtp_color(4), rr.YELLOW)
        self.assertEqual(rr.mtp_color(3), rr.RED)
        self.assertEqual(rr.mtp_color(0), rr.RED)

    def test_odds_vs_morning_line(self):
        self.assertEqual(rr.odds_color("6/1", "12/1"), rr.RED)     # bet down
        self.assertEqual(rr.odds_color("33/1", "20/1"), rr.GREEN)  # drifting out
        self.assertEqual(rr.odds_color("9/2", "9/2"), rr.WHITE)
        self.assertEqual(rr.odds_color("EVN", "2/1"), rr.WHITE)    # unknown format

    def test_drop_slash_one(self):
        self.assertEqual(rr.display_odds("6/1"), "6")
        self.assertEqual(rr.display_odds("33/1"), "33")
        self.assertEqual(rr.display_odds("9/2"), "9/2")
        self.assertEqual(rr.display_odds("3/10"), "3/10")

    def test_surface_and_distance(self):
        self.assertEqual(rr.short_surface("Turf"), "TRF")
        self.assertEqual(rr.short_surface("Dirt"), "DRT")
        for name in ("Synthetic", "Poly", "Polytrack", "Tapeta", "All Weather"):
            self.assertEqual(rr.short_surface(name), "SYN")
        self.assertEqual(rr.SURFACE_COLORS["SYN"], rr.BLUE)
        self.assertEqual(rr.short_surface("Snow"), "")                 # unknown: show nothing rather than guess
        self.assertEqual(rr.short_distance("6 1/2F"), "6.5F")
        self.assertEqual(rr.short_distance("1 1/16M"), "8.5F")

    def test_scratches_omitted_and_paging(self):
        race = nyra.parse_race(PAGE)
        self.assertEqual([h["program"] for h in rr.active_horses(race)], ["1", "2", "4"])
        big = {"horses": [{"program": str(i), "odds": "5/1", "ml": "5/1"} for i in range(1, 13)]}
        self.assertEqual(rr.page_count(race), 1)
        self.assertEqual(rr.page_count(big), 2)

    def test_big_mtp_shows_race_and_time_of_day(self):
        race = dict(nyra.parse_race(PAGE), race="12", mtp=25)
        img = rr.render_big_mtp(race, now=datetime(2026, 10, 8, 12, 47))
        self.assertEqual(rr.short_time(12, 47), "12:47p")
        self.assertEqual(rr.short_time(0, 5), "12:05a")
        # Widest top row: "RACE 12" (blue, from x 1) and "12:47p" (gray, ending at x 63) leave a clear gap
        race_end = 1 + rr.text_width("RACE 12")
        clock_start = rr.W - rr.text_width("12:47p")
        self.assertGreater(clock_start - race_end, 10)
        self.assertEqual(img.getpixel((clock_start + 1, 1)), rr.GRAY)  # top of the "1" in 12:47p
        self.assertEqual(img.getpixel((1, 1)), rr.BLUE)               # "R" of RACE
        self.assertIsNotNone(img.crop((rr.W - 13, 24, rr.W, 29)).getbbox())   # MTP label bottom-right

    def test_screens_render(self):
        race = dict(nyra.parse_race(PAGE), mtp=8)
        for img in (rr.render_full_board(race), rr.render_big_mtp(race)):
            self.assertEqual(img.size, (64, 32))
            self.assertIsNotNone(img.getbbox())


def track_page(post_time, races=3, track="belmont"):
    """Bare-bones NYRA track page: the header countdown (if any) and the race tabs."""
    badge = (f'<span>Race 2 - </span><span class="mtp-badge" data-mtp-variant="header" '
             f'data-post-time="{post_time}">5</span>') if post_time else ""
    tabs = "".join(f'<a hx-get="/{track}/rdl/race/?race={n}">{n}</a>' for n in range(1, races + 1))
    return f"<html><body><div>{badge}</div><nav>{tabs}</nav></body></html>"


class TestTodaysCard(unittest.TestCase):
    CARD = [{"race": "1", "post_time": "2026-10-02T13:10:00"},
            {"race": "2", "post_time": "2026-10-02T13:40:00"},
            {"race": "3", "post_time": "2026-10-02T14:10:00"}]

    def test_racing_today(self):
        day = datetime(2026, 10, 2).date()
        self.assertTrue(nyra.racing_on(track_page("2026-10-02T13:10:00"), day))
        self.assertFalse(nyra.racing_on(track_page("2026-10-03T13:10:00"), day))   # next racing day
        self.assertFalse(nyra.racing_on(track_page(None), day))                    # dark track

    def test_race_numbers(self):
        self.assertEqual(nyra.race_numbers(track_page(None, races=10)), [str(n) for n in range(1, 11)])

    def test_states_follow_the_header_countdown(self):
        # Race 2 is late going off: still "next" even though its post time has passed
        late = nyra.parse_post_time("2026-10-02T13:45:00")
        self.assertEqual(nyra.card_states(self.CARD, "2", now=late), ["done", "next", "later"])

    def test_states_fall_back_to_post_times(self):
        t = nyra.parse_post_time
        self.assertEqual(nyra.card_states(self.CARD, None, now=t("2026-10-02T13:30:00")), ["done", "next", "later"])
        self.assertEqual(nyra.card_states(self.CARD, None, now=t("2026-10-02T18:00:00")), ["done"] * 3)

    def test_auto_follows_the_track_racing_today_and_reads_its_card(self):
        from racing import feed as racefeed
        post = (datetime.now(nyra.NYRA_TZ) + timedelta(minutes=1)).replace(tzinfo=None).isoformat(timespec="seconds")
        pages = {nyra.track_page_url("saratoga"): track_page(None, track="saratoga"),
                 nyra.track_page_url("belmont"): track_page(post)}
        saved = racefeed.CARD_FETCH_GAP
        racefeed.CARD_FETCH_GAP = 0
        try:
            feed = racefeed.RaceFeed(lambda: dict(SETTINGS, track="auto"), start=False)
            feed._get = lambda url: pages.get(url, PAGE)     # every race page is the sample race
            feed._next_race_betting = lambda *args: False    # (so the "next race" isn't betting yet)
            feed._cycle()
        finally:
            racefeed.CARD_FETCH_GAP = saved
        self.assertEqual(feed.track, "belmont")
        self.assertEqual(len(feed.card), 3)
        self.assertEqual(feed.card[0], {"race": "3", "post_time": "2026-10-01T15:12:00",
                                        "distance": "1 1/16M", "surface": "Turf", "runners": 3,
                                        "pick5s": [{"name": "Late Pick 5", "label": "LATE", "first": "3", "last": "7"}]})
        self.assertEqual(feed.next_race, "2")
        self.assertEqual(feed.race["track"], "belmont")


def race_page(race, post_time, official=False, betting=True):
    """The sample race page as race `race` with post time `post_time`.
    official: countdown gone. betting=False: every horse still at its morning line."""
    html = PAGE.replace("2026-10-01T15:12:00", post_time).replace(">Race 3</header>", f">Race {race}</header>")
    if official:
        html = re.sub(r'<span class="mtp-badge[^>]*data-mtp-variant="default"[^>]*>[^<]*</span>', "", html)
    if not betting:
        html = re.sub(r'(<div title="Current Odds">)(?!SCR)[^<]*(</div><div title="Morning Line Odds">ML ([^<]*)</div>)',
                      r"\g<1>\g<3>\g<2>", html)
    return html


class TestMovingOn(unittest.TestCase):
    """After a race is run the board moves on as soon as betting opens on the next race,
    instead of waiting ~10 minutes for NYRA to make it official (watched live at Belmont,
    Oct 2 2026: race 4's odds went live ~6 minutes after race 3 went off)."""

    def test_odds_live(self):
        self.assertTrue(nyra.odds_live(nyra.parse_race(PAGE)))
        self.assertFalse(nyra.odds_live(nyra.parse_race(race_page("4", "2026-10-01T15:42:00", betting=False))))

    def test_race_finished(self):
        self.assertFalse(nyra.race_finished(PAGE))
        self.assertTrue(nyra.race_finished(race_page("3", "2026-10-01T15:12:00", official=True)))
        self.assertFalse(nyra.race_finished("<html>maintenance</html>"))

    def _feed(self, pages):
        from racing import feed as racefeed
        self._saved = racefeed.CARD_FETCH_GAP
        racefeed.CARD_FETCH_GAP = 0
        feed = racefeed.RaceFeed(lambda: dict(SETTINGS, track="belmont"), start=False)
        feed._get = lambda url: pages[url]
        return feed

    def tearDown(self):
        from racing import feed as racefeed
        if hasattr(self, "_saved"):
            racefeed.CARD_FETCH_GAP = self._saved

    def _day(self):
        now = datetime.now(nyra.NYRA_TZ).replace(tzinfo=None)
        iso = lambda dt: dt.isoformat(timespec="seconds")
        post3 = now.replace(second=0) - timedelta(minutes=3)
        track = (f'<html><div><span>Race 3 - </span><span class="mtp-badge" data-mtp-variant="header" '
                 f'data-post-time="{iso(post3)}">0</span></div>'
                 '<a hx-get="/belmont/rdl/race/?race=3">3</a><a hx-get="/belmont/rdl/race/?race=4">4</a></html>')
        pages = {nyra.track_page_url("belmont"): track,
                 nyra.race_fragment_url("belmont", "3"): race_page("3", iso(post3)),
                 nyra.race_fragment_url("belmont", "4"): race_page("4", iso(post3 + timedelta(minutes=30)),
                                                                   betting=False)}
        return pages, post3, iso

    def test_moves_on_when_betting_opens_on_the_next_race(self):
        pages, post3, iso = self._day()
        feed = self._feed(pages)
        feed._cycle()
        self.assertEqual(feed.race["race"], "3")
        # Post time changes (a delay, or NYRA writing the off time) don't move the board on
        pages[nyra.race_fragment_url("belmont", "3")] = race_page("3", iso(post3 + timedelta(seconds=97)))
        feed._next_checked = 0
        feed._cycle()
        self.assertEqual((feed.race["race"], feed.finished), ("3", set()))
        # Race 4's odds go live: race 3 is over
        pages[nyra.race_fragment_url("belmont", "4")] = race_page("4", iso(post3 + timedelta(minutes=30)))
        feed._next_checked = 0
        self.assertEqual(feed._cycle(), 1)
        self.assertEqual(feed.finished, {"3"})
        feed._cycle()
        self.assertEqual((feed.race["race"], feed.next_race), ("4", "4"))

    def test_moves_on_when_the_race_is_official(self):
        pages, post3, iso = self._day()
        feed = self._feed(pages)
        feed._cycle()
        pages[nyra.race_fragment_url("belmont", "3")] = race_page("3", iso(post3), official=True)
        self.assertEqual(feed._cycle(), 1)
        feed._cycle()
        self.assertEqual(feed.race["race"], "4")


SAMPLE_CARD = [  # Belmont, Oct 2 2026
    {"race": "1", "post_time": "2026-10-02T13:10:00", "distance": "7F", "surface": "Dirt", "runners": 9},
    {"race": "2", "post_time": "2026-10-02T13:43:00", "distance": "6 1/2F", "surface": "Turf", "runners": 7},
    {"race": "3", "post_time": "2026-10-02T14:16:00", "distance": "6 1/2F", "surface": "Turf", "runners": 7},
    {"race": "4", "post_time": "2026-10-02T14:49:00", "distance": "6F", "surface": "Dirt", "runners": 13},
    {"race": "5", "post_time": "2026-10-02T15:23:00", "distance": "1 1/16M", "surface": "Turf", "runners": 16},
]


class TestCardScreen(unittest.TestCase):
    def test_renders_four_races_a_page(self):
        self.assertEqual(rr.short_post("2026-10-02T13:10:00"), "1:10p")
        self.assertEqual(rr.short_post("2026-10-02T12:05:00"), "12:05p")
        self.assertEqual(rr.short_post("2026-10-02T11:30:00"), "11:30a")
        # Widest row stays in its columns: race 10 ends at x 6, "12:10p" spans x 10-30, distance starts at 35
        self.assertEqual(rr.text_width("10"), 7)
        self.assertEqual(rr.text_width("12:10p"), 21)
        self.assertEqual(rr.card_page_count(SAMPLE_CARD), 2)
        for page in (0, 1):
            img = rr.render_card("belmont", SAMPLE_CARD, page)
            self.assertEqual(img.size, (64, 32))
            self.assertIsNotNone(img.getbbox())
        # Page 2 has one race: nothing drawn below its row
        self.assertIsNone(rr.render_card("belmont", SAMPLE_CARD, 1).crop((0, 14, 64, 32)).getbbox())

    def test_track_names_fit(self):
        for name in rr.TRACK_LABELS.values():
            self.assertTrue(all(c in rr.GLYPHS for c in name + "TODAY:ap"))
            self.assertLess(rr.text_width(name) + 2 + rr.text_width("TODAY"), 63)
        self.assertEqual(rr.render_card("belmont", SAMPLE_CARD).getpixel((2, 1)), rr.TRACK_COLORS["belmont"])
        self.assertEqual(rr.render_card("saratoga", SAMPLE_CARD).getpixel((2, 1)), rr.TRACK_COLORS["saratoga"])

class TestPick5s(unittest.TestCase):
    """Pick 5s come from each race's bets line (only the race a Pick 5 starts with lists it).
    Any number per day, any name."""

    def test_reads_nyra_bet_lines(self):     # Belmont, Oct 8 2026, races 1 and 5
        self.assertEqual(nyra.pick5s("Exacta ($1), Trifecta (.50), Super (.10), Double ($1) 1 & 2, Pick 3 ($1) (1-3), "
                                     "Early Pick 5 (.50) (1-5) (UP TO $17,400 NYSBFOA)"),
                         [{"name": "Early Pick 5", "label": "EARLY", "first": "1", "last": "5"}])
        self.assertEqual(nyra.pick5s("Exacta ($1), Pick 3 ($1) (5-7), Grand Slam (5-8), Late Pick 5 (.50) (5-9)"),
                         [{"name": "Late Pick 5", "label": "LATE", "first": "5", "last": "9"}])
        self.assertEqual(nyra.pick5s("Exacta ($1), Pick 5 (.50) (3-7), Super Hi 5 (.10)")[0]["label"], "PICK 5")
        self.assertEqual(nyra.pick5s(""), [])
        self.assertEqual(nyra.parse_race(PAGE)["pick5s"][0]["first"], "3")

    def _seqs(self, *specs):
        return [{"label": lab, "first": a, "last": b, "post_time": f"2026-10-08T{t}:00"} for lab, a, b, t in specs]

    def test_pages(self):
        two = self._seqs(("EARLY", "1", "5", "13:10"), ("LATE", "5", "9", "15:23"))
        three = two + self._seqs(("PICK 5", "3", "7", "14:16"))
        five = three + self._seqs(("TWILIGHT", "6", "10", "16:00"), ("NIGHT", "7", "11", "16:30"))
        self.assertEqual([rr.pick5_page_count(x) for x in (two, three, five)], [1, 1, 2])
        for seqs in (two, three, five):
            for page in range(rr.pick5_page_count(seqs)):
                img = rr.render_pick5("belmont", seqs, page)
                self.assertEqual(img.size, (64, 32))
                self.assertIsNotNone(img.crop((0, 8, 64, 32)).getbbox())

    def test_mandatory_pay_shows_as_mand(self):      # Belmont, Oct 8 2026: three Pick 5s
        self.assertEqual(nyra.pick5s("Pick 3 ($1) (3-5), Mandatory Pay Pick 5 (.50) (3-7)")[0]["label"], "MANDATORY PAY")
        seqs = self._seqs(("EARLY", "1", "5", "13:10"), ("MANDATORY PAY", "3", "7", "14:16"), ("LATE", "5", "9", "15:23"))
        mand = rr.Image.new("RGB", (64, 32))
        rr.draw_text(rr.ImageDraw.Draw(mand), 1, 14, "MAND", rr.WHITE)
        self.assertEqual(rr.render_pick5("belmont", seqs).crop((0, 14, 20, 19)).tobytes(), mand.crop((0, 14, 20, 19)).tobytes())

    def test_long_names_are_shortened_to_fit(self):
        seqs = self._seqs(("SUPERCALIFRAGILISTIC", "10", "14", "12:10"))
        img = rr.render_pick5("saratoga", seqs)
        # The time still ends at the right edge, and the races still show in blue
        self.assertIn(rr.BLUE, [img.getpixel((x, y)) for x in range(64) for y in range(10, 15)])


if __name__ == "__main__":
    unittest.main()
