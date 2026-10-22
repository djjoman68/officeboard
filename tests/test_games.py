"""MLB and NFL modules. Made-up games in the shape of ESPN's scoreboard feed, no internet."""
import unittest
from datetime import datetime, timedelta, timezone

import support  # noqa: F401  (stand-in panel library, paths)
from support import colours

import requests
from core.module import BoardInfo
from modules import games
from modules.games import Mlb, Nfl, parse_scoreboard, status_text

NOW = datetime(2026, 10, 22, 12, 0)


def utc(local):
    """A local time as ESPN writes it (UTC, 'Z')."""
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def event(away, home, start, state="pre", detail="", scores=("0", "0"), odds=None, eid="1"):
    comp = {"competitors": [{"homeAway": "home", "team": {"abbreviation": home}, "score": scores[1]},
                            {"homeAway": "away", "team": {"abbreviation": away}, "score": scores[0]}]}
    if odds is not None:
        comp["odds"] = [odds]
    return {"id": eid, "date": utc(start), "competitions": [comp],
            "status": {"type": {"state": state, "shortDetail": detail, "completed": state == "post"}}}


MLB_ODDS = {"provider": {"name": "DraftKings"}, "details": "MIL -161", "overUnder": 6.0, "spread": -1.5,
            "moneyline": {"home": {"close": {"odds": "-161"}, "open": {"odds": "-160"}},
                          "away": {"close": {"odds": "+133"}}}}
NFL_ODDS = {"provider": {"name": "DraftKings"}, "details": "CHI -3", "overUnder": 50.5, "spread": -3.0}


def mlb_day():
    return {"events": [
        event("TB", "MIL", NOW.replace(hour=20), odds=MLB_ODDS, eid="2"),
        event("NYY", "BOS", NOW.replace(hour=13), state="in", detail="Top 7th", scores=("3", "5"), eid="1"),
        event("LAD", "SF", NOW.replace(hour=9), state="post", detail="Final", scores=("4", "2"), eid="0"),
    ]}


def nfl_week():
    thu = NOW.replace(hour=20, minute=15)
    return {"events": [
        event("NE", "CHI", thu, odds=NFL_ODDS),
        event("SF", "ATL", thu + timedelta(days=3, hours=-7, minutes=-15), odds=dict(NFL_ODDS, details="SF -2.5", overUnder=49.5)),
        event("KC", "DEN", thu + timedelta(days=3), odds={"details": "EVEN", "overUnder": 44}),
        event("NYJ", "BUF", thu + timedelta(days=4), state="in", detail="5:21 - 3rd", scores=("10", "17")),
    ]}


def module(cls, body, **settings):
    m = cls(BoardInfo())
    m.settings = dict(m.settings, enabled=True, **settings)
    m.data = {"games": parse_scoreboard(body), "at": NOW}
    return m


class TestReading(unittest.TestCase):
    def test_games_sorted_with_teams_scores_and_odds(self):
        gs = parse_scoreboard(mlb_day())
        self.assertEqual([(g["away"]["abbr"], g["home"]["abbr"]) for g in gs], [("LAD", "SF"), ("NYY", "BOS"), ("TB", "MIL")])
        self.assertEqual(gs[1]["state"], "in")
        self.assertEqual((gs[1]["away"]["score"], gs[1]["home"]["score"]), ("3", "5"))
        self.assertEqual(gs[2]["start"], NOW.replace(hour=20))
        self.assertEqual(gs[2]["odds"]["ml_home"], "-161")       # closing line over the opening one
        self.assertEqual(gs[2]["odds"]["ml_away"], "+133")
        self.assertIsNone(gs[0]["odds"])

    def test_status_words(self):
        g = {"state": "in", "detail": "5:21 - 3rd"}
        self.assertEqual(status_text(g), "Q3 5:21")
        self.assertEqual(status_text({"state": "in", "detail": "Halftime"}), "HALFTIME")
        self.assertEqual(status_text({"state": "in", "detail": "Top 7th"}), "TOP 7TH")
        self.assertEqual(status_text({"state": "post", "detail": "Final/10"}), "FINAL/10")
        self.assertEqual(status_text({"state": "post", "detail": "Postponed"}), "PPD")

    def test_odd_feed_is_an_error_not_a_crash(self):
        with self.assertRaises(KeyError):
            parse_scoreboard({"events": [{"id": "x"}]})


class TestMlb(unittest.TestCase):
    def test_today_only_with_moneylines_for_both_teams(self):
        body = mlb_day()
        body["events"].append(event("HOU", "SEA", NOW + timedelta(days=1), odds=MLB_ODDS, eid="9"))
        m = module(Mlb, body)
        self.assertEqual(len(m.games(NOW)), 3)                          # tomorrow's game left out
        words = ["".join(t for t, _ in item) for item in m.ticker_items(NOW)]
        self.assertEqual(words[2], "TB @ MIL 8:00p TB +133 MIL -161 ")
        self.assertEqual(words[1], "NYY 3 BOS 5 TOP 7TH")

    def test_asks_espn_for_today(self):
        self.assertEqual(Mlb().params(NOW), {"dates": "20261022"})

    def test_pages(self):
        m = module(Mlb, mlb_day())
        final, live, upcoming = m.pages(NOW)
        self.assertIn(games.ODDS, colours(upcoming))                    # moneylines
        self.assertIn(games.LIVE, colours(live))                        # "TOP 7TH" in green
        self.assertIn(games.TRAILING, colours(live))                    # NYY behind 3-5
        self.assertIn(games.DIM, colours(final.crop((0, 25, 64, 32))))  # FINAL dim

    def test_odds_and_finals_can_be_turned_off(self):
        m = module(Mlb, mlb_day(), odds=False, finals=False)
        self.assertEqual(len(m.pages(NOW)), 2)
        self.assertNotIn(games.ODDS, colours(m.pages(NOW)[1]))

    def test_no_games_is_skipped(self):
        self.assertFalse(module(Mlb, {"events": []}).has_content(NOW))


class TestNfl(unittest.TestCase):
    def test_week_with_spread_and_total(self):
        m = module(Nfl, nfl_week())
        words = ["".join(t for t, _ in item) for item in m.ticker_items(NOW)]
        self.assertEqual(words[0], "NE @ CHI 8:15p CHI -3 O/U 50.5 ")
        self.assertEqual(words[1], "SF @ ATL SUN 1:00p SF -2.5 O/U 49.5 ")
        self.assertEqual(words[2], "KC @ DEN SUN 8:15p EVEN O/U 44 ")
        self.assertEqual(words[3], "NYJ 10 BUF 17 Q3 5:21")
        self.assertEqual(len(m.pages(NOW)), 4)

    def test_preview_page_fits(self):
        page = module(Nfl, nfl_week()).pages(NOW)[0]
        box = page.getbbox()
        self.assertGreaterEqual(box[0], 0)
        self.assertLessEqual(box[2], 64)
        self.assertIsNotNone(page.crop((0, 24, 64, 32)).getbbox())        # the O/U line


class FakeESPN:
    def __init__(self, body=None, status=200, offline=False):
        self.body, self.status, self.offline, self.calls = body, status, offline, []

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        if self.offline:
            raise requests.ConnectionError("offline")
        fake = self

        class Resp:
            status_code = fake.status

            def raise_for_status(self):
                if self.status_code >= 400:
                    resp = requests.Response()
                    resp.status_code = self.status_code
                    raise requests.HTTPError(response=resp)

            def json(self):
                return fake.body
        return Resp()


class TestFetching(unittest.TestCase):
    def setUp(self):
        self._saved = games.requests.get

    def tearDown(self):
        games.requests.get = self._saved

    def test_fetch_and_poll_faster_during_games(self):
        espn = FakeESPN(mlb_day())
        games.requests.get = espn.get
        m = Mlb()
        m.refresh(NOW)
        self.assertEqual(len(m.data["games"]), 3)
        self.assertIn("baseball/mlb/scoreboard", espn.calls[0][0])
        self.assertEqual(m.fetch_interval(), games.LIVE_SECONDS)          # a game is on

    def test_failures_keep_the_last_games(self):
        games.requests.get = FakeESPN(nfl_week()).get
        m = Nfl()
        m.refresh(NOW)
        games.requests.get = FakeESPN(offline=True).get
        m.refresh(NOW)
        self.assertEqual(len(m.data["games"]), 4)
        self.assertEqual(m.last_error, "no connection to ESPN")
        games.requests.get = FakeESPN(status=503).get
        m.refresh(NOW)
        self.assertIn("503", m.last_error)

    def test_quiet_when_nothing_is_on(self):
        m = Nfl()
        m.data = {"games": [], "at": NOW}
        self.assertEqual(m.fetch_interval(), games.IDLE_SECONDS)


if __name__ == "__main__":
    unittest.main()
