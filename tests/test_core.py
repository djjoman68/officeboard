"""Run with:  python3 -m unittest discover tests

No LED panel or internet needed: a fake rgbmatrix module stands in for the panel.
"""
import json
import os
import unittest
from datetime import datetime

import support
from support import TempFiles

import config
from core import pixels, registry
from core.display import NOTHING_ON, Display
from core.module import BoardInfo, Module
from core.scheduler import Scheduler
from rgbmatrix import RGBMatrix

NOW = datetime(2026, 10, 22, 10, 0, 0)


class Fake(Module):
    """A module whose answers the test controls."""

    def __init__(self, mod_id, seconds=10, enabled=True, content=True):
        self.id = self.name = mod_id
        super().__init__()
        self.settings = dict(self.settings, enabled=enabled, seconds=seconds)
        self.content, self.holding, self.taking = content, False, False

    def has_content(self, now):
        return self.content

    def hold(self, now):
        return self.holding

    def takeover(self, now):
        return self.taking


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = Fake("a", 10), Fake("b", 5), Fake("c", 8)
        self.mods = [self.a, self.b, self.c]
        self.s = Scheduler()

    def at(self, t):
        m, turn = self.s.pick(self.mods, NOW, t)
        return (m.id if m else None), round(turn, 1)

    def test_takes_turns_in_order_for_each_turn_length(self):
        self.assertEqual(self.at(0), ("a", 0))
        self.assertEqual(self.at(9.9), ("a", 9.9))
        self.assertEqual(self.at(10), ("b", 0))
        self.assertEqual(self.at(15), ("c", 0))
        self.assertEqual(self.at(23), ("a", 0))

    def test_skips_modules_off_or_with_nothing_to_show(self):
        self.b.settings["enabled"] = False
        self.c.content = False
        self.assertEqual(self.at(0), ("a", 0))
        self.assertEqual(self.at(10), ("a", 10))      # the only one left keeps the panel

    def test_module_turned_off_mid_turn_hands_over_at_once(self):
        self.at(0)
        self.a.settings["enabled"] = False
        self.assertEqual(self.at(3), ("b", 0))

    def test_hold_keeps_the_panel_past_the_turn(self):
        self.at(0)
        self.a.holding = True
        self.assertEqual(self.at(30), ("a", 30))
        self.a.holding = False
        self.assertEqual(self.at(31), ("b", 0))

    def test_takeover_wins_then_rotation_resumes_after_it(self):
        self.at(0)
        self.c.taking = True
        self.assertEqual(self.at(2), ("c", 0))
        self.assertEqual(self.at(200), ("c", 198))
        self.c.taking = False
        self.assertEqual(self.at(201), ("a", 0))

    def test_nothing_to_show(self):
        for m in self.mods:
            m.settings["enabled"] = False
        self.assertEqual(self.at(0), (None, 0))

    def test_a_broken_module_is_skipped(self):
        def boom(now):
            raise RuntimeError("bad data")
        self.a.has_content = boom
        self.assertEqual(self.at(0), ("b", 0))


class TestSettings(unittest.TestCase):
    def test_display_values_are_made_safe(self):
        d = config.normalize_display({"brightness": 500, "fps": "fast", "panel_type": "XYZ", "led_rgb_sequence": "RGB"})
        self.assertEqual((d["brightness"], d["fps"], d["panel_type"]), (100, 50, ""))

    def test_module_order_drops_unknown_and_adds_new(self):
        order = registry.modules_config({"order": ["paneltest", "gone", "nfl", "nfl"]})["order"]
        self.assertEqual(order[:2], ["paneltest", "nfl"])
        self.assertEqual(sorted(order), sorted(registry.DEFAULT_ORDER))

    def test_planned_modules_cannot_be_turned_on(self):
        from modules.planned import _planned
        later = _planned("later", "Later", "A module still to come.", 9)
        self.assertFalse(later.normalize({"enabled": True})["enabled"])

    def test_panel_test_is_on_by_default_and_settings_are_checked(self):
        mods = registry.modules_config({"paneltest": {"seconds": 1, "message": 42}})
        self.assertTrue(mods["paneltest"]["enabled"])
        self.assertEqual(mods["paneltest"]["seconds"], 3)              # minimum turn
        self.assertEqual(mods["paneltest"]["message"], "OFFICE BOARD")  # not text: default

    def test_list_settings(self):
        from core.module import normalize_field
        f = {"key": "x", "type": "list", "default": []}
        self.assertEqual(normalize_field(f, [" aapl ", "", "MSFT", "aapl"]), ["aapl", "MSFT"])
        self.assertEqual(normalize_field(f, "AAPL"), [])


class TestFetching(unittest.TestCase):
    def test_failed_fetch_keeps_last_good_data(self):
        class Feed(Module):
            id = "feed"
            fetch_seconds = 60
            answer = "first"

            def fetch(self, now):
                if self.answer is None:
                    raise ConnectionError("site down")
                return self.answer

        m = Feed()
        self.assertFalse(m.has_content(NOW))       # nothing fetched yet: skipped
        m.refresh(NOW)
        self.assertEqual((m.data, m.last_error), ("first", None))
        m.answer = None
        m.refresh(NOW)
        self.assertEqual(m.data, "first")
        self.assertIn("site down", m.last_error)
        self.assertTrue(m.has_content(NOW))


class TestPixels(unittest.TestCase):
    def test_text_matches_the_font(self):
        img = pixels.blank()
        self.assertEqual(pixels.text_width("small", "ABC"), 15)
        self.assertEqual(pixels.draw_text(img, "small", 0, 7, pixels.WHITE, "ABC"), 15)
        self.assertIsNotNone(img.getbbox())

    def test_marquee_enters_from_the_right_and_loops(self):
        strip = pixels.Image.new("RGB", (10, 4), pixels.WHITE)

        def lit(t):                                 # 1 pixel a second keeps the sums exact
            return pixels.marquee(pixels.blank(), strip, t, speed=1).getbbox()
        self.assertIsNone(lit(0))                   # just off the right edge
        self.assertEqual(lit(5), (59, 0, 64, 4))    # 5 pixels in
        self.assertEqual(lit(39), (25, 0, 35, 4))
        self.assertEqual(lit(73), (0, 0, 1, 4))     # last column leaving on the left
        self.assertIsNone(lit(74))                  # gone: 64 + 10 pixels per pass
        self.assertEqual(lit(79), lit(5))           # and round again

    def test_led_preview_size(self):
        self.assertEqual(pixels.led_preview(pixels.blank(), dot=4).size, (256, 128))


class TestDisplayLoop(TempFiles):
    def make(self):
        """The board with only the panel test on, so frames are predictable."""
        config.save({"modules": {"clock": {"enabled": False}}})
        return Display(matrix=RGBMatrix(), start_fetchers=False)

    def test_panel_test_reaches_the_panel(self):
        d = self.make()
        img = d.step(NOW, mono=0.0)
        self.assertEqual(d.current.id, "paneltest")
        self.assertEqual(d.matrix.shown.tobytes(), img.tobytes())
        self.assertEqual(img.getpixel((0, 12)), (255, 0, 0))            # first colour bar

    def test_only_changed_frames_are_sent(self):
        d = self.make()
        d.order = []                                # nothing on: a still picture
        d.step(NOW, 0.0)
        d.step(NOW, 0.1)
        self.assertEqual(d.matrix.swaps, 1)
        self.assertEqual(d.last_image.tobytes(), NOTHING_ON.tobytes())

    def test_scrolling_moves_between_frames(self):
        d = self.make()
        a = d.step(NOW, 0.0)
        b = d.step(NOW, 2.0)
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_settings_change_applies_without_restart(self):
        d = self.make()
        d._config_mtime = None
        config.save({"display": {"brightness": 40}, "modules": {"paneltest": {"enabled": False}, "clock": {"enabled": False}}})
        d.check_config()
        d.step(NOW, 0.0)
        self.assertEqual(d.matrix.brightness, 40)
        self.assertIsNone(d.current)

    def test_drawing_error_shows_a_message_and_is_reported(self):
        d = self.make()
        pt = d.modules["paneltest"]
        pt.frame = lambda now, t: 1 / 0
        img = d.step(NOW, 0.0)
        self.assertIsNotNone(img.getbbox())
        self.assertIn("ZeroDivisionError", pt.last_error)

    def test_status_for_the_web_page(self):
        d = self.make()
        d.step(NOW, 0.0)
        d.write_status()
        from core import display as disp
        with open(disp.STATUS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        self.assertEqual((s["module"], s["module_name"]), ("paneltest", "Panel test"))
        self.assertTrue(s["modules"]["paneltest"]["has_content"])
        self.assertFalse(s["modules"]["mlb"]["has_content"])
        self.assertFalse(s["asleep"])
        self.assertTrue(os.path.exists(disp.FRAME_FILE))


if __name__ == "__main__":
    unittest.main()
