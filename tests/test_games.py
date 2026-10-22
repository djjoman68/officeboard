"""MLB and NFL modules. Made-up games in the shape of ESPN's scoreboard feed, no internet."""
import os
import unittest
from datetime import datetime, timedelta, timezone

import support  # noqa: F401  (stand-in panel library, paths)
from support import colours

import requests
from core.module import BoardInfo
from modules import games
from modules.games import Mlb, Nfl, parse_scoreboard, status_text

NOW = datetime(2026, 10, 22, 12, 0)


def setUpModule():
    """Never use logos this computer has downloaded: every test starts with none."""
    import tempfile
    global _saved_logo_dir, _tmp_logo_dir
    _saved_logo_dir, _tmp_logo_dir = games.LOGO_DIR, tempfile.mkdtemp()
    games.LOGO_DIR = os.path.join(_tmp_logo_dir, "logos")


def tearDownModule():
    import shutil
    games.LOGO_DIR = _saved_logo_dir
    shutil.rmtree(_tmp_logo_dir, ignore_errors=True)


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


def png(colour=(220, 30, 30), size=(100, 50)):
    """A made-up logo: a coloured block on a see-through background, as PNG bytes."""
    from io import BytesIO
    from PIL import Image
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    img.paste(colour + (255,), (50, 75, 50 + size[0], 75 + size[1]))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class FakeCDN(FakeESPN):
    """ESPN's scoreboard plus its image server."""

    def __init__(self, body):
        super().__init__(body)
        self.images = 0

    def get(self, url, params=None, **kw):
        if "espncdn" not in url:
            return super().get(url, params, **kw)
        self.images += 1
        content = png()

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass
        r = Resp()
        r.content = content
        return r


def with_logos(body):
    for e in body["events"]:
        for c in e["competitions"][0]["competitors"]:
            abbr = c["team"]["abbreviation"].lower()
            c["team"].update(color="0b1c3a", alternateColor="e64100",
                             logoDark=f"https://a.espncdn.com/i/teamlogos/nfl/500-dark/scoreboard/{abbr}.png")
    return body


class TestTeamLook(support.TempFiles):
    """Joe's pick (Oct 22 2026): brighter logos on the score screens, team names in team colours."""

    def setUp(self):
        super().setUp()
        self._saved_get = games.requests.get

    def tearDown(self):
        games.requests.get = self._saved_get
        super().tearDown()

    def test_team_colour_is_the_brighter_one_lifted_for_leds(self):
        self.assertEqual(games.team_colour({"color": "0b1c3a", "alt": "e64100"}), (230, 65, 0))     # Bears orange
        self.assertEqual(games.team_colour({"color": "0c2340", "alt": "ffffff"}), (255, 255, 255))  # navy + white
        dark = games.team_colour({"color": "13294b", "alt": "000000"})
        self.assertGreaterEqual(games._lum(dark), games.MIN_LUM - 1)
        self.assertEqual(games.team_colour({}), games.WHITE)

    def test_logo_tile(self):
        from io import BytesIO
        from PIL import Image
        tile = games.process_logo(Image.open(BytesIO(png())))
        self.assertEqual(tile.size, (games.LOGO, games.LOGO))
        self.assertEqual(tile.getpixel((0, 0)), (0, 0, 0))                     # background black
        r, g, b = tile.getpixel((6, 6))
        self.assertGreater(r, 200)                                              # the logo, brightened

    def test_logos_download_once_and_show_on_the_score_screen(self):
        cdn = FakeCDN(with_logos(nfl_week()))
        games.requests.get = cdn.get
        m = Nfl()
        m.refresh(NOW)
        self.assertEqual(cdn.images, 8)                                        # 8 teams
        m.refresh(NOW)
        self.assertEqual(cdn.images, 8)                                        # kept, not downloaded again
        live = m.pages(NOW)[3]                                                 # NYJ @ BUF, in progress
        self.assertGreater(live.getpixel((6, 6))[0], 200)                      # NYJ logo top-left
        self.assertIn((230, 65, 0), colours(live))                             # names in team colour

    def test_logos_off(self):
        cdn = FakeCDN(with_logos(nfl_week()))
        games.requests.get = cdn.get
        m = Nfl()
        m.settings["logos"] = False
        m.refresh(NOW)
        self.assertEqual(cdn.images, 0)
        self.assertIsNone(m.pages(NOW)[3].crop((0, 0, 2, 26)).getbbox())    # nothing where logos go

    def test_only_espns_image_server_and_failures_wait(self):
        body = with_logos(nfl_week())
        body["events"][0]["competitions"][0]["competitors"][0]["team"]["logoDark"] = "https://example.com/x.png"
        cdn = FakeCDN(body)
        games.requests.get = cdn.get
        m = Nfl()
        m.refresh(NOW)
        self.assertEqual(cdn.images, 7)                                        # CHI's odd link skipped
        m.refresh(NOW)
        self.assertEqual(cdn.images, 7)                                        # and not retried for 6 hours

    def test_preview_page_uses_team_colours(self):
        m = module(Nfl, with_logos(nfl_week()))
        self.assertIn((230, 65, 0), colours(m.pages(NOW)[0]))

    def test_preview_page_has_logos_too(self):
        cdn = FakeCDN(with_logos(nfl_week()))
        games.requests.get = cdn.get
        m = Nfl()
        m.refresh(NOW)
        upcoming = m.pages(NOW)[0]                                             # NE @ CHI, not started
        self.assertGreater(upcoming.getpixel((6, 6))[0], 200)                  # NE logo top-left
        self.assertGreater(upcoming.getpixel((6, 19))[0], 200)                 # CHI logo below


class TestCompactOdds(unittest.TestCase):
    """Odds sit on the team rows: the NFL spread on the favourite's row only, MLB moneylines on both. (Joe, Oct 22 2026)"""

    def test_nfl_spread_per_team(self):
        m = module(Nfl, nfl_week())
        g = m.games(NOW)
        self.assertEqual(m.row_odds(g[0]), {"home": "-3"})                         # CHI -3 at home: favourite only
        self.assertEqual(m.row_odds(g[1]), {"away": "-2.5"})                       # SF -2.5 on the road
        self.assertEqual(m.row_odds(g[2]), {"home": "PK"})                         # EVEN: once, home row
        self.assertEqual(m.bottom_odds(g[0]), "50.5")

    def test_mlb_moneyline_per_team(self):
        m = module(Mlb, mlb_day())
        g = next(x for x in m.games(NOW) if x["state"] == "pre")
        self.assertEqual(m.row_odds(g), {"away": "+133", "home": "-161"})
        self.assertIsNone(m.bottom_odds(g))

    def test_layout(self):
        m = module(Nfl, nfl_week())
        page = m.pages(NOW)[1]                                                  # SF @ ATL, Sunday
        self.assertIn(games.ODDS, colours(page.crop((40, 0, 64, 12))))          # SF -2.5 on the top row
        self.assertNotIn(games.ODDS, colours(page.crop((40, 13, 64, 25))))      # nothing for ATL, the underdog
        self.assertIn(games.TIME, colours(page.crop((0, 26, 30, 32))))          # SU 1p bottom left
        self.assertIn(games.ODDS, colours(page.crop((44, 26, 64, 32))))         # the total bottom right
        self.assertEqual(m.when(m.games(NOW)[1], NOW, short_day=True, compact=True), "SU 1p")
        self.assertEqual(m.when(m.games(NOW)[2], NOW, short_day=True, compact=True), "SU 8:15p")

    def test_unreadable_spread_shows_no_numbers(self):
        g = parse_scoreboard({"events": [event("NE", "CHI", NOW, odds={"details": "OFF"})]})[0]
        self.assertEqual(Nfl().row_odds(g), {})


if __name__ == "__main__":
    unittest.main()
