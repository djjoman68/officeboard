"""Make an LED-style animated picture of the board, no panel needed.

    python3 tools/preview.py                 # 20 seconds of the rotation with today's settings
    python3 tools/preview.py 8               # or any number of seconds

Runs the real display loop on the stand-in panel with simulated time and writes preview.gif
(animated, for scrolling) and preview.png (the first frame) in the current folder.
"""
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests", "fakes"))
sys.path.insert(0, ROOT)
from rgbmatrix import RGBMatrix               # noqa: E402  (the stand-in)
from core.display import Display              # noqa: E402
from core.pixels import led_preview           # noqa: E402

GIF_FPS = 25        # GIFs can't go much faster; the panel itself runs at the fps setting
DOT = 6

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20
d = Display(matrix=RGBMatrix(), start_fetchers=False)
d.board.fps = d.board.display["fps"]          # show the target rate in the panel test
start = datetime.now()
frames = []
for i in range(int(seconds * GIF_FPS)):
    t = i / GIF_FPS
    frames.append(led_preview(d.step(start + timedelta(seconds=t), mono=t), dot=DOT))

frames[0].save("preview.png")
frames[0].save("preview.gif", save_all=True, append_images=frames[1:], duration=1000 // GIF_FPS, loop=0)
print(f"Wrote preview.gif ({len(frames)} frames, {seconds:g}s) and preview.png")
