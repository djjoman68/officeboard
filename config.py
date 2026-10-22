"""Settings: config/config.json and config/secrets.json, created on the Pi and never committed.

Same pattern as itsposttime: the web UI saves the JSON files and the display notices within a second.
This file knows the board-wide settings; each module declares its own settings (see core/module.py)
and core/registry.py merges them in.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE_DIR, "config", "config.json")
SEC_PATH = os.path.join(BASE_DIR, "config", "secrets.json")

PANEL_TYPES = ("", "FM6126A", "FM6127")
RGB_SEQUENCES = ("RGB", "RBG", "GRB", "GBR", "BRG", "BGR")

DEFAULT_DISPLAY = {
    "brightness": 80,             # %
    "fps": 50,                    # frames per second; scrolling needs 30+ to look smooth
    "page_seconds": 5,            # how long each page shows when a module has several
    "scroll_speed": 24,           # pixels per second for scrolling text
    "gpio_slowdown": 2,           # 2 for a Pi 3A+
    "hat_pwm_enabled": False,     # Bonnet PWM solder bridge installed
    "led_rgb_sequence": "RGB",
    "panel_type": "",             # "" for most panels; "FM6126A" if a P3 panel stays dark
    "multiplexing": 0,            # only for unusual panels
    "row_address_type": 0,        # only for unusual panels
}

# (min, max) for the numbers; anything outside is pulled back in range
_LIMITS = {
    "brightness": (1, 100), "fps": (10, 60), "page_seconds": (2, 60), "scroll_speed": (5, 80),
    "gpio_slowdown": (0, 5), "multiplexing": (0, 22), "row_address_type": (0, 5),
}


def clamp_int(value, lo, hi, default):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def normalize_display(raw):
    """Board-wide display settings with defaults filled in and every value made safe."""
    d = {**DEFAULT_DISPLAY, **(raw if isinstance(raw, dict) else {})}
    for key, (lo, hi) in _LIMITS.items():
        d[key] = clamp_int(d[key], lo, hi, DEFAULT_DISPLAY[key])
    d["hat_pwm_enabled"] = bool(d["hat_pwm_enabled"])
    if d["led_rgb_sequence"] not in RGB_SEQUENCES:
        d["led_rgb_sequence"] = "RGB"
    if d["panel_type"] not in PANEL_TYPES:
        d["panel_type"] = ""
    return {k: d[k] for k in DEFAULT_DISPLAY}


def load(path=None):
    try:
        with open(path or CFG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_secrets():
    return load(SEC_PATH)


def save(data, path=None):
    path = path or CFG_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def mtime():
    try:
        return os.path.getmtime(CFG_PATH)
    except OSError:
        return None


def ensure_files():
    """Create empty config files on first run so the web UI can load. Defaults fill in the rest."""
    if not os.path.exists(CFG_PATH):
        save({})
    if not os.path.exists(SEC_PATH):
        save({}, SEC_PATH)
