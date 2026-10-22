"""Stocks module: indexes from their funds, your list, market hours. Sample quotes, no internet."""
import unittest
from datetime import datetime

import support  # noqa: F401  (stand-in panel library, paths)
from support import TempFiles

import config
import requests
from core.module import BoardInfo
from modules import stocks
from modules.stocks import Stocks

NOW = datetime(2026, 10, 22, 10, 44)

QUOTES = {   # symbol: (price, change, % change)
    "DIA": (423.15, 1.68, 0.40), "SPY": (592.10, 3.55, 0.60), "QQQ": (510.20, -1.02, -0.20),
    "AAPL": (231.40, 2.74, 1.20), "MSFT": (438.10, -2.20, -0.50), "BRK.A": (712345.0, 1200.0, 0.17),
}
T = 1792680000      # 2026-10-22 ~ morning, Eastern


class FakeFinnhub:
    def __init__(self, session="regular", fail=(), status_code=200):
        self.session, self.fail, self.status_code, self.calls = session, set(fail), status_code, []

    def get(self, url, params=None, **kw):
        self.calls.append((url.rsplit("/", 1)[-1], params.get("symbol")))
        status_code, fail = self.status_code, self.fail

        if url.endswith("market-status"):
            body = {"exchange": "US", "isOpen": self.session == "regular", "session": self.session, "holiday": None}
        else:
            sym = params["symbol"]
            if sym in fail:
                raise requests.ConnectionError("offline")
            c, d, dp = QUOTES.get(sym, (0, None, None))
            body = {"c": c, "d": d, "dp": dp, "t": T if c else 0}

        class Resp:
            def __init__(self):
                self.status_code = status_code

            def raise_for_status(self):
                if self.status_code >= 400:
                    resp = requests.Response()
                    resp.status_code = self.status_code
                    raise requests.HTTPError(response=resp)

            def json(self):
                return body
        return Resp()


def module(symbols=("AAPL", "MSFT"), per_page="1", data=None):
    m = Stocks(BoardInfo())
    m.settings = dict(m.settings, enabled=True, symbols=list(symbols), per_page=per_page)
    m.data = data
    return m


class TestStocksFetch(TempFiles):
    def setUp(self):
        super().setUp()
        self.fh = FakeFinnhub()
        self._saved_get = stocks.requests.get
        stocks.requests.get = self.fh.get
        config.save({"finnhub_api_key": "k123"}, config.SEC_PATH)

    def tearDown(self):
        stocks.requests.get = self._saved_get
        super().tearDown()

    def test_indexes_from_their_funds_then_your_list(self):
        m = module(("aapl", "MSFT", "AAPL"))
        m.refresh(NOW)
        d = m.data
        self.assertEqual([(q["label"], q["symbol"]) for q in d["indexes"]],
                         [("DOW", "DIA"), ("S&P", "SPY"), ("NASDAQ", "QQQ")])
        self.assertEqual([q["symbol"] for q in d["stocks"]], ["AAPL", "MSFT"])     # upper-cased, no repeats
        self.assertEqual(d["stocks"][0]["pct"], 1.20)
        self.assertEqual(d["session"], "regular")
        self.assertIsNone(m.last_error)

    def test_unknown_symbol_is_skipped_and_named(self):
        m = module(("AAPL", "NOPE"))
        m.refresh(NOW)
        self.assertEqual([q["symbol"] for q in m.data["stocks"]], ["AAPL"])
        self.assertIn("Not found: NOPE", m.last_error)

    def test_failed_quote_keeps_the_last_good_one(self):
        m = module(("AAPL",))
        m.refresh(NOW)
        self.fh.fail = {"AAPL"}
        m.refresh(NOW)
        self.assertEqual(m.data["stocks"][0]["price"], 231.40)
        self.assertIn("AAPL: no connection", m.last_error)

    def test_missing_or_bad_key(self):
        config.save({}, config.SEC_PATH)
        m = module()
        m.refresh(NOW)
        self.assertIn("Finnhub key", m.last_error)
        self.assertEqual(self.fh.calls, [])
        config.save({"finnhub_api_key": "bad"}, config.SEC_PATH)
        self.fh.status_code = 401
        m.refresh(NOW)
        self.assertIn("not accepted", m.last_error)

    def test_polls_every_minute_while_open_and_half_hourly_when_closed(self):
        m = module()
        m.refresh(NOW)
        self.assertEqual(m.fetch_interval(), 60)
        self.fh.session = None
        m.refresh(NOW)
        self.assertEqual(m.fetch_interval(), 1800)

    def test_editing_the_list_fetches_straight_away(self):
        m = module()
        m.wake.clear()
        m.configure(dict(m.settings, symbols=["AAPL", "NVDA"]))
        self.assertTrue(m.wake.is_set())


def sample_data(session="regular", symbols=("AAPL", "MSFT")):
    """Made-up quotes, also used by tools/preview.py."""
    def q(sym, label=None):
        c, d, dp = QUOTES[sym]
        out = {"symbol": sym, "price": c, "change": d, "pct": dp, "time": datetime(2026, 10, 22, 10, 43)}
        return dict(out, label=label) if label else out
    return {"session": session, "holiday": None,
            "indexes": [q("DIA", "DOW"), q("SPY", "S&P"), q("QQQ", "NASDAQ")],
            "stocks": [q(s) for s in symbols]}


class TestStocksScreens(unittest.TestCase):
    def data(self, session="regular", symbols=("AAPL", "MSFT")):
        return sample_data(session, symbols)

    def test_markets_page_then_one_page_per_stock(self):
        m = module(data=self.data())
        pages = m.pages(NOW)
        self.assertEqual(len(pages), 3)
        markets = set(pages[0].getdata())
        self.assertIn(stocks.UP, markets)            # DOW, S&P up
        self.assertIn(stocks.DOWN, markets)          # NASDAQ down
        self.assertIn(stocks.UP, set(pages[1].getdata()))      # AAPL up
        self.assertIn(stocks.DOWN, set(pages[2].getdata()))    # MSFT down

    def test_three_per_page(self):
        m = module(("AAPL", "MSFT", "AAPL"), per_page="3", data=self.data())
        self.assertEqual(len(m.pages(NOW)), 2)
        m = module(("AAPL", "MSFT", "BRK.A", "AAPL"), per_page="3",
                   data=self.data(symbols=("AAPL", "MSFT", "BRK.A")))
        self.assertEqual(len(m.pages(NOW)), 2)                  # markets + one page of 3

    def test_session_label(self):
        for session, colour in (("regular", stocks.UP), ("pre-market", stocks.pixels.YELLOW), (None, stocks.DIM)):
            page = module(data=self.data(session)).pages(NOW)[0]
            self.assertIn(colour, set(page.crop((0, 0, 64, 7)).getdata()), session)

    def test_big_prices_still_fit(self):
        m = module(("BRK.A",), data=self.data(symbols=("BRK.A",)))
        page = m.pages(NOW)[1]
        self.assertLess(page.getbbox()[2], 65)

    def test_text(self):
        self.assertEqual(stocks.pct_text(1.2), "▲1.20%")
        self.assertEqual(stocks.pct_text(-0.351), "▼0.35%")
        self.assertEqual(stocks.pct_text(0), "0.00%")
        self.assertEqual(stocks.price_text(712345.0), "712,345")
        self.assertEqual(stocks.change_text(-2.2), "-2.20")
        self.assertEqual(stocks.change_text(1200.0), "+1,200")

    def test_ticker_items(self):
        words = [" ".join(t.strip() for t, _ in item) for item in module(data=self.data()).ticker_items(NOW)]
        self.assertEqual(words, ["DOW ▲0.40%", "S&P ▲0.60%", "NASDAQ ▼0.20%", "AAPL 231.40 ▲1.20%",
                                 "MSFT 438.10 ▼0.50%"])

    def test_nothing_fetched_yet_is_skipped(self):
        self.assertFalse(module().has_content(NOW))

    def test_market_hours_guess(self):
        et = lambda h, m, day=22: datetime(2026, 10, day, h, m)      # noqa: E731  (Oct 22 2026 is a Thursday)
        self.assertEqual(stocks.guess_session(et(9, 29)), "pre-market")
        self.assertEqual(stocks.guess_session(et(9, 30)), "regular")
        self.assertEqual(stocks.guess_session(et(16, 0)), "post-market")
        self.assertIsNone(stocks.guess_session(et(21, 0)))
        self.assertIsNone(stocks.guess_session(et(12, 0, day=24)))     # Saturday


if __name__ == "__main__":
    unittest.main()
