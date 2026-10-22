"""Animated pictures of the four layouts, for choosing one (the scroll experiment, docs/plan.md step 3).

    python3 tools/compare_layouts.py

Writes previews/layout-a-ticker.gif, -b-split.gif, -c-roll.gif and -d-pages.gif. Each shows one turn
of Clock & weather (sample weather) and one turn of the Scroll demo (made-up stocks, a race, games),
using today's scroll speed and page flip settings.
"""
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests", "fakes"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, ROOT)
from rgbmatrix import RGBMatrix               # noqa: E402  (the stand-in)
from core import registry                     # noqa: E402
from core.display import Display              # noqa: E402
from core.pixels import led_preview           # noqa: E402
from test_clock import sample_data            # noqa: E402

GIF_FPS = 20
DOT = 5
CLOCK_SECONDS = 12
MAX_SECONDS = 130
LAYOUTS = [("a", "ticker"), ("b", "split"), ("c", "roll"), ("d", "pages")]

os.makedirs(os.path.join(ROOT, "previews"), exist_ok=True)
start = datetime.now().replace(second=0, microsecond=0)
for letter, lay in LAYOUTS:
    d = Display(matrix=RGBMatrix(), start_fetchers=False)
    cfg = registry.full_config()
    cfg["display"]["layout"] = lay
    for mod_id in cfg["modules"]["order"]:
        cfg["modules"][mod_id].update(enabled=mod_id in ("clock", "demo"), layout="board")
    cfg["modules"]["clock"]["seconds"] = CLOCK_SECONDS
    cfg["modules"]["demo"]["seconds"] = 3
    cfg["modules"]["order"] = ["clock", "demo"] + [i for i in cfg["modules"]["order"] if i not in ("clock", "demo")]
    cfg["sleep"]["enabled"], cfg["sleep"]["override"] = False, None
    d.apply_config(cfg)
    d.sleep_cfg = cfg["sleep"]
    d.modules["clock"].data = sample_data(start)
    total = min(MAX_SECONDS, d.modules["clock"].turn_length(start) + d.modules["demo"].turn_length(start))
    frames = [led_preview(d.step(start + timedelta(seconds=i / GIF_FPS), mono=i / GIF_FPS), dot=DOT)
              for i in range(int(total * GIF_FPS))]
    path = os.path.join(ROOT, "previews", f"layout-{letter}-{lay}.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=1000 // GIF_FPS, loop=0, optimize=True)
    print(f"{path}: {total:.0f}s, {os.path.getsize(path) // 1024} KB")
