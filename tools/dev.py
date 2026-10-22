"""Run the whole board on a computer, with a pretend panel, to try the web UI without the Pi.

    python tools/dev.py          then open http://localhost:8080

Uses config/ in this folder like the Pi does, and puts the panel picture in .cache/.
Restart, Shut down, Wi-Fi and Logs only work on the Pi.
"""
import logging
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests", "fakes"))
sys.path.insert(0, ROOT)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("werkzeug").setLevel(logging.WARNING)

import config                         # noqa: E402
from core.display import Display      # noqa: E402
from rgbmatrix import RGBMatrix       # noqa: E402  (the stand-in)
from web.app import app               # noqa: E402

config.ensure_files()
threading.Thread(target=Display(matrix=RGBMatrix()).run, daemon=True).start()
print("Office board (pretend panel) on http://localhost:8080")
app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False)
