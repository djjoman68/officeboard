"""The list of modules, and the full settings with every module's defaults filled in.

To add a module: write it in modules/, then list it in MODULE_CLASSES (replacing its planned stand-in).
"""
import config
from modules.clock import ClockWeather
from modules.demo import ScrollDemo
from modules.paneltest import PanelTest
from modules.planned import Mlb, Nfl, Nyra
from modules.stocks import Stocks

MODULE_CLASSES = [ClockWeather, Stocks, Nyra, Mlb, Nfl, ScrollDemo, PanelTest]
BY_ID = {cls.id: cls for cls in MODULE_CLASSES}
DEFAULT_ORDER = [cls.id for cls in MODULE_CLASSES]


def modules_config(raw):
    """{"order": [ids], <id>: settings} with unknown ids dropped and new modules added at the end."""
    raw = raw if isinstance(raw, dict) else {}
    saved = raw.get("order") if isinstance(raw.get("order"), list) else []
    order = [i for i in dict.fromkeys(saved) if i in BY_ID]
    order += [i for i in DEFAULT_ORDER if i not in order]
    out = {"order": order}
    for mod_id, cls in BY_ID.items():
        out[mod_id] = cls.normalize(raw.get(mod_id))
    return out


def full_config(raw=None):
    raw = config.load() if raw is None else raw
    out = {name: normalize(raw.get(name)) for name, normalize in config.SECTIONS.items()}
    out["modules"] = modules_config(raw.get("modules"))
    return out


def build(board):
    """One instance of every module, keyed by id."""
    return {cls.id: cls(board) for cls in MODULE_CLASSES}


def describe():
    """What the web UI needs to draw each module's card and settings form."""
    return {cls.id: {
        "id": cls.id, "name": cls.name, "description": cls.description,
        "built": cls.built, "step": cls.step, "fields": cls.all_fields(),
    } for cls in MODULE_CLASSES}
