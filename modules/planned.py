"""Modules agreed in docs/plan.md but not built yet. They appear on the web UI's Modules page as
"coming in step N" and can't be turned on. Each is replaced by its real module when built."""
from core.module import Module


def _planned(mod_id, name, description, step):
    return type(f"Planned_{mod_id}", (Module,), {
        "id": mod_id, "name": name, "description": description, "built": False, "step": step,
    })


Mlb = _planned("mlb", "MLB", "Today's games with moneylines, then live scores.", 6)
Nfl = _planned("nfl", "NFL", "This week's games with spread and total, then live scores.", 6)

PLANNED = [Mlb, Nfl]
