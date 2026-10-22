"""The main loop: asks the scheduler which module has the panel, gets that module's picture for this
moment, and copies it to the LEDs, up to `fps` times a second.

itsposttime's loop (from the plane tracker) ran at 10 frames a second with each screen drawing straight
onto the panel. Scrolling needs 30-60 frames a second, so this loop is new: modules draw Pillow images
and only changed frames are sent to the panel. Panel options are carried over from itsposttime.
"""
import json
import logging
import os
import tempfile
import time
from datetime import datetime

import config
from core import pixels, registry, sleep
from core.module import BoardInfo, Fetcher
from core.scheduler import Scheduler

log = logging.getLogger("display")

# Status + latest frame for the web UI, kept in RAM (/dev/shm) to spare the SD card
STATUS_DIR = "/dev/shm/officeboard" if os.path.isdir("/dev/shm") else os.path.join(config.BASE_DIR, ".cache")
STATUS_FILE = os.path.join(STATUS_DIR, "status.json")
FRAME_FILE = os.path.join(STATUS_DIR, "board.png")

CONFIG_CHECK_SECONDS = 1
STATUS_SECONDS = 2
ERROR_LOG_SECONDS = 60


def _atomic_write(path, write_fn):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    os.close(fd)
    write_fn(tmp)
    os.replace(tmp, path)


def _iso(t):
    return t.isoformat(timespec="minutes") if t else None


def _write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_matrix(display):
    """The panel, with itsposttime's proven options plus the settings a P3 panel may need."""
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    options = RGBMatrixOptions()
    options.hardware_mapping = "adafruit-hat-pwm" if display["hat_pwm_enabled"] else "adafruit-hat"
    options.rows = 32
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    options.row_address_type = display["row_address_type"]
    options.multiplexing = display["multiplexing"]
    options.pwm_bits = 11
    options.brightness = display["brightness"]
    options.pwm_lsb_nanoseconds = 160
    options.led_rgb_sequence = display["led_rgb_sequence"]
    options.pixel_mapper_config = ""
    if display["panel_type"]:
        options.panel_type = display["panel_type"]
    options.show_refresh_rate = 0
    options.gpio_slowdown = display["gpio_slowdown"]
    options.disable_hardware_pulsing = True
    options.drop_privileges = True
    options.limit_refresh_rate_hz = 120
    return RGBMatrix(options=options)


def message_frame(*lines):
    """Small centred text, for "nothing on" and errors."""
    img = pixels.blank()
    y = 16 - 5 * len(lines) + 8
    for text, colour in lines:
        pixels.draw_text(img, "tiny", max(0, (64 - pixels.text_width("tiny", text)) // 2), y, colour, text)
        y += 9
    return img


NOTHING_ON = message_frame(("NO MODULES ON", pixels.GRAY), ("SEE WEB PAGE", pixels.DIM))


class Display:
    def __init__(self, matrix=None, start_fetchers=True):
        cfg = registry.full_config()
        self.board = BoardInfo(cfg["display"], cfg["location"])
        self.sleep_cfg = cfg["sleep"]
        self.asleep = False
        self.matrix = matrix or make_matrix(cfg["display"])
        self.canvas = self.matrix.CreateFrameCanvas()
        self.modules = registry.build(self.board)
        self.order = []
        self.scheduler = Scheduler()
        self.current = None
        self.turn = 0.0
        self.last_image = pixels.blank()
        self._last_bytes = None
        self._last_saved = None
        self._errors = {}                 # module id -> when its last drawing error was logged
        self._config_mtime = config.mtime()
        self.apply_config(cfg)
        if start_fetchers:
            for m in self.modules.values():
                if m.fetch_seconds:
                    Fetcher(m).start()

    # ---------- settings ----------
    def apply_config(self, cfg):
        """Settings that apply live: brightness, frame rate, paging, scroll speed, location, sleep, and
        every module's. Panel hardware settings (GPIO slowdown, panel type, ...) need a restart."""
        location_changed = cfg["location"] != self.board.location
        self.board.display = cfg["display"]
        self.board.location = cfg["location"]
        self.sleep_cfg = cfg["sleep"]
        for mod_id, m in self.modules.items():
            m.configure(cfg["modules"][mod_id])
            if location_changed and m.fetch_seconds:
                m.wake.set()                 # new place or units: fetch again now
        self.order = [self.modules[i] for i in cfg["modules"]["order"]]

    def _set_brightness(self):
        if self.asleep:
            wanted = max(1, self.sleep_cfg["brightness"])
        else:
            wanted = self.board.display["brightness"]
        if self.matrix.brightness != wanted:
            self.matrix.brightness = wanted

    def check_config(self):
        mtime = config.mtime()
        if mtime != self._config_mtime:
            self._config_mtime = mtime
            self.apply_config(registry.full_config())

    # ---------- one frame ----------
    def step(self, now=None, mono=None):
        now = now or datetime.now()
        mono = time.monotonic() if mono is None else mono
        self.asleep = sleep.asleep(now, self.sleep_cfg)
        self._set_brightness()
        if self.asleep:
            # Sleep beats everything, NYRA take-over included: time and date only, or nothing at 0%
            self.current, self.turn = None, 0.0
            img = self._sleep_frame(now)
        else:
            module, t = self.scheduler.pick(self.order, now, mono)
            self.current, self.turn = module, t
            img = NOTHING_ON if module is None else self._draw(module, now, t)
        data = img.tobytes()
        if data != self._last_bytes:
            self.canvas.SetImage(img)
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            self._last_bytes = data
            self.last_image = img
        return img

    def _sleep_frame(self, now):
        if self.sleep_cfg["brightness"] == 0:
            return pixels.blank()
        key = now.strftime("%Y-%m-%d %H:%M")
        if getattr(self, "_sleep_key", None) != key:
            try:
                self._sleep_img = self.modules["clock"].sleep_frame(now)
            except Exception:
                log.exception("sleep screen failed")
                self._sleep_img = pixels.blank()
            self._sleep_key = key
        return self._sleep_img

    def _draw(self, module, now, t):
        try:
            img = module.frame(now, t)
            if img is None:
                return pixels.blank()
            if img.size != (pixels.WIDTH, pixels.HEIGHT) or img.mode != "RGB":
                img = img.convert("RGB").crop((0, 0, pixels.WIDTH, pixels.HEIGHT))
            return img
        except Exception as e:
            if time.monotonic() - self._errors.get(module.id, -ERROR_LOG_SECONDS) >= ERROR_LOG_SECONDS:
                log.exception("%s: drawing failed", module.id)
                self._errors[module.id] = time.monotonic()
            module.last_error = f"Drawing failed: {type(e).__name__}: {e}"
            return message_frame((module.name.upper()[:15], pixels.WHITE), ("ERROR", pixels.RED))

    # ---------- for the web UI ----------
    def write_status(self):
        now = datetime.now()
        status = {
            "module": self.current.id if self.current else None,
            "module_name": self.current.name if self.current else None,
            "turn_seconds": round(self.turn, 1),
            "fps": round(self.board.fps, 1),
            "asleep": self.asleep,
            "sleep_until": _iso(sleep.until(now, self.sleep_cfg)),
            "sleep_override": sleep.active_override(now, self.sleep_cfg),
            "modules": {i: dict(m.status(), has_content=bool(m.enabled and self._has_content(m, now)))
                        for i, m in self.modules.items()},
            "written": now.isoformat(timespec="seconds"),
        }
        try:
            _atomic_write(STATUS_FILE, lambda p: _write_text(p, json.dumps(status)))
            if self.last_image is not self._last_saved:
                frame = self.last_image
                _atomic_write(FRAME_FILE, lambda p: frame.save(p, format="PNG"))
                self._last_saved = frame
        except Exception as e:
            log.warning("status write failed: %s", e)

    @staticmethod
    def _has_content(m, now):
        try:
            return m.has_content(now)
        except Exception:
            return False

    # ---------- the loop ----------
    def run(self):
        print("Press CTRL-C to stop")
        next_frame = time.monotonic()
        next_config = next_status = next_frame
        frames, fps_since = 0, next_frame
        try:
            while True:
                mono = time.monotonic()
                if mono >= next_config:
                    self.check_config()
                    next_config = mono + CONFIG_CHECK_SECONDS
                self.step(mono=mono)
                frames += 1
                if mono - fps_since >= 1:
                    self.board.fps = frames / (mono - fps_since)
                    frames, fps_since = 0, mono
                if mono >= next_status:
                    self.write_status()
                    next_status = mono + STATUS_SECONDS
                # Keep a steady pace; if a frame ran late, carry on rather than rush to catch up
                next_frame += 1 / self.board.display["fps"]
                delay = next_frame - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_frame = time.monotonic()
        except KeyboardInterrupt:
            print("Exiting")
