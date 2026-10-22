"""Shared test setup: the stand-in panel library, and settings/status files in a temporary folder so
tests never touch config/ or /dev/shm."""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "fakes"))
sys.path.insert(0, ROOT)

import config            # noqa: E402
from core import display  # noqa: E402


class TempFiles(unittest.TestCase):
    """Points config and status files at a fresh temporary folder for each test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = (config.CFG_PATH, config.SEC_PATH, display.STATUS_FILE, display.FRAME_FILE)
        config.CFG_PATH = os.path.join(self.tmp, "config.json")
        config.SEC_PATH = os.path.join(self.tmp, "secrets.json")
        display.STATUS_FILE = os.path.join(self.tmp, "status.json")
        display.FRAME_FILE = os.path.join(self.tmp, "board.png")
        try:
            from web import app as web
            self.web = web
            self._saved_web = (web.STATUS_FILE, web.FRAME_FILE)
            web.STATUS_FILE, web.FRAME_FILE = display.STATUS_FILE, display.FRAME_FILE
        except ImportError:          # Flask not installed: web tests are skipped
            self.web = None

    def tearDown(self):
        config.CFG_PATH, config.SEC_PATH, display.STATUS_FILE, display.FRAME_FILE = self._saved
        if self.web:
            self.web.STATUS_FILE, self.web.FRAME_FILE = self._saved_web
        shutil.rmtree(self.tmp, ignore_errors=True)
