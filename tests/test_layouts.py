"""The four layouts of the scroll experiment: pages, roll, full ticker, split."""
import unittest
from datetime import datetime

import support  # noqa: F401  (stand-in panel library, paths)
from support import colours

import config
from core import layouts, pixels
from core.module import BoardInfo, Module
from core.scheduler import Scheduler
from modules.clock import ClockWeather, condition
from modules.demo import ScrollDemo
from modules.paneltest import PanelTest
from test_clock import NOW, sample_data


def board(**display):
    return BoardInfo(config.normalize_display(display))


def colour_page(c):
    img = pixels.blank()
    img.paste(c, (0, 0, 64, 32))
    return img


class TestRoll(unittest.TestCase):
    def setUp(self):
        self.a, self.b = colour_page((255, 0, 0)), colour_page((0, 0, 255))

    def test_first_page_opens_without_sliding(self):
        self.assertEqual(layouts.roll([self.a, self.b], 0.1, 5).getpixel((0, 31)), (255, 0, 0))

    def test_next_page_slides_up_from_the_bottom(self):
        mid = layouts.roll([self.a, self.b], 5.25, 5)            # half way through the slide
        self.assertEqual(mid.getpixel((0, 0)), (255, 0, 0))     # old page leaving at the top
        self.assertEqual(mid.getpixel((0, 31)), (0, 0, 255))    # new page arriving at the bottom
        self.assertEqual(layouts.roll([self.a, self.b], 5.6, 5).getpixel((0, 0)), (0, 0, 255))

    def test_one_page_never_moves(self):
        self.assertIs(layouts.roll([self.a], 5.1, 5), self.a)


class TestTickers(unittest.TestCase):
    def setUp(self):
        self.strip = pixels.text_strip("large", [("HELLO WORLD", pixels.WHITE)], 13)

    def test_full_ticker_scrolls_with_a_dim_label(self):
        a = layouts.ticker(self.strip, 1, 24, label="Stocks")
        b = layouts.ticker(self.strip, 2, 24, label="Stocks")
        self.assertNotEqual(a.crop((0, 8, 64, 32)).tobytes(), b.crop((0, 8, 64, 32)).tobytes())
        self.assertEqual(a.crop((0, 0, 64, 7)).tobytes(), b.crop((0, 0, 64, 7)).tobytes())     # label stays
        self.assertIn(layouts.LABEL, colours(a))

    def test_split_keeps_the_bar_still(self):
        bar = pixels.Image.new("RGB", (64, 9), (0, 200, 0))
        a, b = layouts.split(bar, self.strip, 1, 24), layouts.split(bar, self.strip, 2, 24)
        self.assertEqual(a.getpixel((5, 4)), (0, 200, 0))
        self.assertEqual(a.crop((0, 0, 64, 10)).tobytes(), b.crop((0, 0, 64, 10)).tobytes())
        self.assertNotEqual(a.crop((0, 10, 64, 32)).tobytes(), b.crop((0, 10, 64, 32)).tobytes())

    def test_items_are_joined_with_dots(self):
        pieces = layouts.join_items([[("A", pixels.WHITE)], [("B", pixels.WHITE)]])
        self.assertEqual([t for t, _ in pieces][:3], ["A", "  •  ", "B"])

    def test_pass_time(self):
        self.assertEqual(layouts.pass_seconds(176, 24), 10)

    def test_text_page_picks_a_font_that_fits(self):
        big = layouts.text_page([[("DOW", pixels.WHITE)], [("42,315", pixels.WHITE)]])
        small = layouts.text_page([[("NYY @ LAD", pixels.WHITE)], [("8:08p", pixels.WHITE)],
                                   [("NYY -145", pixels.WHITE)], [("LAD +125", pixels.WHITE)]])
        self.assertGreater(big.getbbox()[3] - big.getbbox()[1], 20)      # two tall lines
        self.assertIsNotNone(small.crop((0, 24, 64, 32)).getbbox())      # fourth line fits


class TestModuleLayouts(unittest.TestCase):
    def test_board_setting_or_the_modules_own(self):
        m = ScrollDemo(board(layout="split"))
        self.assertEqual(m.layout(), "split")
        m.settings["layout"] = "roll"
        self.assertEqual(m.layout(), "roll")
        self.assertEqual(PanelTest(board(layout="ticker")).layout(), "pages")    # panel test opts out
        self.assertNotIn("layout", [f["key"] for f in PanelTest.all_fields()])

    def test_each_layout_draws(self):
        for lay in layouts.LAYOUTS:
            m = ScrollDemo(board(layout=lay))
            self.assertIsNotNone(m.frame(NOW, 3).getbbox(), lay)

    def test_turn_stretches_to_fit_everything(self):
        m = ScrollDemo(board(layout="pages", page_seconds=5))
        self.assertEqual(m.turn_length(NOW), len(m.pages(NOW)) * 5)          # every page once
        m = ScrollDemo(board(layout="ticker", scroll_speed=24))
        strip = m._ticker_strip(NOW, "ticker")
        self.assertAlmostEqual(m.turn_length(NOW), (strip.width + 64) / 24)    # all the way past once
        self.assertGreater(m.turn_length(NOW), 20)

    def test_scheduler_waits_for_the_ticker_to_finish(self):
        demo = ScrollDemo(board(layout="ticker"))
        demo.settings = dict(demo.settings, enabled=True, seconds=10)

        class Other(Module):
            id = name = "other"
        other = Other()
        other.settings["enabled"] = True
        s = Scheduler()
        s.pick([demo, other], NOW, 0)
        self.assertEqual(s.pick([demo, other], NOW, 15)[0].id, "demo")           # still scrolling
        self.assertEqual(s.pick([demo, other], NOW, demo.turn_length(NOW) + 0.1)[0].id, "other")

    def test_module_without_ticker_text_falls_back_to_pages(self):
        class PagesOnly(Module):
            id = name = "pagesonly"

            def pages(self, now):
                return [colour_page((0, 255, 0))]
        m = PagesOnly(board(layout="ticker"))
        self.assertEqual(m.frame(NOW, 1).getpixel((0, 0)), (0, 255, 0))


class TestClockLayouts(unittest.TestCase):
    def clock(self, lay):
        m = ClockWeather(board(layout=lay))
        m.data = sample_data()
        m.board.status_bar = m.status_bar          # as the display sets it
        return m

    def test_ticker_text(self):
        words = " | ".join("".join(t for t, _ in item) for item in self.clock("ticker").ticker_items(NOW))
        self.assertEqual(words, "10:44 | THU OCT 22 | 72° CLEAR | TODAY 73/61 MOSTLY CLEAR | FRI 66/58 RAIN | "
                                "↑ 7:09a  ↓ 6:14p")
        split_words = " ".join(t for item in self.clock("split").ticker_items(NOW) for t, _ in item)
        self.assertNotIn("10:44", split_words)                    # the top bar has the time

    def test_split_top_bar_has_time_and_temperature(self):
        img = self.clock("split").frame(NOW, 2)
        self.assertIsNotNone(img.crop((0, 0, 30, 9)).getbbox())
        self.assertIsNotNone(img.crop((44, 0, 64, 9)).getbbox())

    def test_roll_pages_are_forecast_then_sun(self):
        self.assertEqual(len(self.clock("roll").pages(NOW)), 2)

    def test_roll_keeps_sun_at_the_end_of_the_turn_and_slides_it_in(self):
        m = self.clock("roll")
        m.settings = dict(m.settings, seconds=20, sun_seconds=6)
        forecast, sliding, sun = m.frame(NOW, 13), m.frame(NOW, 14.25), m.frame(NOW, 15)
        self.assertEqual(forecast.tobytes(), m.page_frame(NOW, 13).tobytes())
        self.assertEqual(sun.tobytes(), m.page_frame(NOW, 15).tobytes())
        self.assertNotIn(sliding.tobytes(), (forecast.tobytes(), sun.tobytes()))
        self.assertEqual(m.turn_length(NOW), 20)

    def test_roll_is_the_default(self):
        self.assertEqual(config.normalize_display({})["layout"], "roll")
        self.assertEqual(config.normalize_display({"layout": "zigzag"})["layout"], "roll")

    def test_condition_words(self):
        self.assertEqual(condition(1101), "PARTLY CLOUDY")
        self.assertEqual(condition(10001), "CLEAR")                # night variant
        self.assertEqual(condition(4204), "RAIN")                 # mixed code: its group
        self.assertEqual(condition(None), "")


if __name__ == "__main__":
    unittest.main()
