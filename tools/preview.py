"""Make LED-style pictures of the board, no panel needed.

    python3 tools/preview.py                 # 30 seconds of the rotation with today's settings
    python3 tools/preview.py 8               # or any number of seconds

Runs the real display loop on the stand-in panel with simulated time, and writes:
  preview.gif   animated, for scrolling and page changes
  preview.png   a sheet of each screen: clock & weather, sunrise/sunset, an alert, sleep mode, panel test,
                stocks, NYRA, MLB, NFL
The clock uses made-up sample weather unless the board has fetched real weather; stocks use sample quotes; NYRA a sample card and race; games
are made up.
"""
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests", "fakes"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, ROOT)
from PIL import Image, ImageDraw               # noqa: E402
from rgbmatrix import RGBMatrix               # noqa: E402  (the stand-in)
from core.display import Display              # noqa: E402
from core.pixels import led_preview           # noqa: E402
from test_clock import sample_data            # noqa: E402
import test_stocks                            # noqa: E402
import test_nyra                              # noqa: E402
import test_games                             # noqa: E402

GIF_FPS = 25        # GIFs can't go much faster; the panel itself runs at the fps setting
DOT = 6

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30
d = Display(matrix=RGBMatrix(), start_fetchers=False)
d.board.fps = d.board.display["fps"]          # show the target rate in the panel test
clock = d.modules["clock"]
start = datetime.now().replace(second=0, microsecond=0)
if not clock.data:
    clock.data = sample_data(start)
d.sleep_cfg = dict(d.sleep_cfg, enabled=False, override=None)    # the animation shows the rotation

frames = []
for i in range(int(seconds * GIF_FPS)):
    t = i / GIF_FPS
    frames.append(led_preview(d.step(start + timedelta(seconds=t), mono=t), dot=DOT))
frames[0].save("preview.gif", save_all=True, append_images=frames[1:], duration=1000 // GIF_FPS, loop=0)

# One picture of each screen
data = clock.data
screens = [("Clock & weather (today, one screen)", clock.draw(start)),
           ("Severe weather alert", clock.draw(start, {"text": "TSTM WRN", "color": "orange"})),
           ("Sleep mode", clock.sleep_frame(start)),
           ("Panel test", d.modules["paneltest"].frame(start, 2.5))]
stocks = d.modules["stocks"]
stocks.data = test_stocks.sample_data(symbols=("AAPL", "MSFT", "BRK.A"))
stocks.settings = dict(stocks.settings, symbols=["AAPL", "MSFT", "BRK.A"], per_page="1")
pages = stocks.pages(start)
screens += [("Stocks: markets (sample quotes)", pages[0]), ("Stocks: one per page", pages[1]),
            ("Stocks: one per page, falling", pages[2]), ("Stocks: one per page, big price", pages[3])]
stocks.settings["per_page"] = "3"
screens.append(("Stocks: three per page", stocks.pages(start)[1]))
stocks.data = test_stocks.sample_data(session=None)
screens.append(("Stocks: after the close", stocks.pages(start)[0]))
racing = d.modules["nyra"]
racing.feed = test_nyra.FakeFeed()
noon = test_nyra.NOON
card_pages = racing.pages(noon)
screens += [("NYRA: today's card (sample)", card_pages[0]), ("NYRA: Pick 5s still to start", card_pages[-1])]
racing.feed = test_nyra.FakeFeed(race=test_nyra.race_at(8))
screens.append(("NYRA: race board, 8 MTP", racing.pages(start)[0]))
racing.settings = dict(racing.settings, view="big_mtp")
screens.append(("NYRA: big MTP view", racing.pages(start)[0]))
mlb = test_games.module(test_games.Mlb, test_games.mlb_day())
final, live, upcoming = mlb.pages(test_games.NOW)
screens += [("MLB: before the game, moneylines (sample)", upcoming), ("MLB: live score", live), ("MLB: final", final)]
nfl = test_games.module(test_games.Nfl, test_games.nfl_week())
nfl_pages = nfl.pages(test_games.NOW)
screens += [("NFL: before the game, spread and total (sample)", nfl_pages[0]), ("NFL: live score", nfl_pages[3])]
pad, cap = 16, 22
tiles = [(title, led_preview(img, dot=DOT)) for title, img in screens]
w = tiles[0][1].width + 2 * pad
sheet = Image.new("RGB", (w, sum(t.height + cap + pad for _, t in tiles) + pad), (245, 245, 245))
draw, y = ImageDraw.Draw(sheet), pad
for title, tile in tiles:
    draw.text((pad, y + 5), title, fill=(30, 30, 30))
    sheet.paste(tile, (pad, y + cap))
    y += tile.height + cap + pad
sheet.save("preview.png")
print(f"Wrote preview.gif ({len(frames)} frames, {seconds:g}s) and preview.png ({len(screens)} screens)")
