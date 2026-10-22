"""Scroll demo: made-up stocks, a race and games, shaped like the modules still to come, so the four
layouts can be compared on real content before those modules exist (docs/plan.md, step 3).

Everything here is sample data, and the panel says so. Off by default; remove once the real modules
are built.
"""
from core import layouts, pixels
from core.module import Module

UP, DOWN, BLUE, YELLOW, DIM, WHITE = (0, 220, 80), (255, 60, 60), pixels.BLUE, pixels.YELLOW, pixels.DIM, pixels.WHITE

STOCKS = [("DOW", "42,315", "+0.4%"), ("S&P", "5,921", "+0.6%"), ("NASDAQ", "19,103", "-0.2%"),
          ("AAPL", "231.40", "+1.2%"), ("MSFT", "438.10", "-0.5%")]


def _change(pct):
    return (("▲" if pct.startswith("+") else "▼") + pct[1:], UP if pct.startswith("+") else DOWN)


class ScrollDemo(Module):
    id = "demo"
    name = "Scroll demo"
    description = "Made-up stocks, a race and games, for comparing layouts until the real modules exist."
    default_enabled = False
    default_seconds = 20

    def ticker_items(self, now):
        items = [[("SAMPLE DATA", DIM)]]
        for name, price, pct in STOCKS:
            items.append([(name + " ", WHITE), (price + " ", WHITE), _change(pct)])
        items.append([("BEL R5 ", BLUE), ("7 MTP ", YELLOW), ("#3 5/2 FAV", WHITE)])
        items.append([("NYY @ LAD 8:08p ", WHITE), ("NYY -145 / LAD +125", YELLOW)])
        items.append([("NYJ @ BUF SUN 1:00p ", WHITE), ("BUF -6.5 ", YELLOW), ("O/U 44.5", YELLOW)])
        return items

    def pages(self, now):
        key = "pages"
        if getattr(self, "_pages_key", None) != key:
            pages = []
            for name, price, pct in STOCKS:
                pages.append(layouts.text_page([[(name, WHITE)], [(price + " ", WHITE), _change(pct)]]))
            pages.append(layouts.text_page([[("BELMONT R5", BLUE)], [("7 MTP", YELLOW)], [("#3 5/2 FAV", WHITE)]]))
            pages.append(layouts.text_page([[("NYY @ LAD", WHITE)], [("8:08p", DIM)], [("NYY -145", YELLOW)],
                                            [("LAD +125", YELLOW)]]))
            pages.append(layouts.text_page([[("NYJ @ BUF", WHITE)], [("SUN 1:00p", DIM)], [("BUF -6.5", YELLOW)],
                                            [("O/U 44.5", YELLOW)]]))
            self._pages, self._pages_key = pages, key
        return self._pages
