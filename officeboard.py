#!/usr/bin/python3
"""Office board - entry point.

Starts the web UI in the background, then runs the display loop.
Only one copy can run at a time: a second copy (for example started by hand while the service runs)
exits immediately instead of fighting over the panel's GPIO.

From itsposttime's odds-board.py. Modified for the office board.
"""
import atexit
import fcntl
import logging
import os
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

LOCK_FILE = "/tmp/officeboard.lock"


def single_instance():
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("The office board is already running (probably as the officeboard service). "
              "Use 'sudo systemctl stop officeboard' first if you want to run it by hand.")
        sys.exit(1)
    return lock   # keep the file open for the life of the process


if __name__ == "__main__":
    _lock = single_instance()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base_dir)

    import config
    config.ensure_files()

    web_app = os.path.join(base_dir, "web", "app.py")
    if os.path.exists(web_app):
        web = subprocess.Popen([sys.executable, web_app])
        atexit.register(web.terminate)

    from core.display import Display
    Display().run()
