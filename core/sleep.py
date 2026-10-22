"""Sleep mode: when the panel shows only the clock and date, at its own brightness.

The schedule: asleep every day from `start` to `end` (an `end` earlier than `start` means the next
morning), and all day on the days in `all_day`. The Board page's Sleep now / Wake now buttons override
the schedule until its next change. Pure logic: the time is passed in.
"""
from datetime import datetime, timedelta

import config

LOOKAHEAD_DAYS = 8


def _minutes(hhmm):
    t = datetime.strptime(hhmm, "%H:%M")
    return t.hour * 60 + t.minute


def scheduled(now, cfg):
    """Whether the schedule alone says asleep at `now`."""
    if not cfg["enabled"]:
        return False
    if config.DAYS[now.weekday()] in cfg["all_day"]:
        return True
    start, end, t = _minutes(cfg["start"]), _minutes(cfg["end"]), now.hour * 60 + now.minute
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end


def next_change(now, cfg):
    """When the schedule next flips between asleep and awake, or None if it never does.
    A schedule that's switched off counts as on here, so the buttons still know when to give way."""
    cfg = dict(cfg, enabled=True)
    state = scheduled(now, cfg)
    t = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = now + timedelta(days=LOOKAHEAD_DAYS)
    while t <= end:
        if scheduled(t, cfg) != state:
            return t
        t += timedelta(minutes=1)
    return None


def active_override(now, cfg):
    """"sleep" or "wake" while a button's override is running, else None."""
    if cfg["override"] and cfg["override_until"] and now < datetime.fromisoformat(cfg["override_until"]):
        return cfg["override"]
    return None


def asleep(now, cfg):
    """Whether the panel sleeps at `now`: a Sleep now / Wake now override if one is running,
    else the schedule."""
    ov = active_override(now, cfg)
    return ov == "sleep" if ov else scheduled(now, cfg)


def until(now, cfg):
    """When the current state (asleep or awake) ends, for the Board page. None if not known."""
    if active_override(now, cfg):
        return datetime.fromisoformat(cfg["override_until"])
    return next_change(now, cfg) if cfg["enabled"] else None


def override(now, cfg, action):
    """New sleep settings after a button: "sleep", "wake", or "schedule" (cancel the override).
    The override lasts until the schedule next changes, or a day when there's no schedule."""
    cfg = dict(cfg)
    if action not in ("sleep", "wake"):
        cfg["override"], cfg["override_until"] = None, None
        return cfg
    ends = (next_change(now, cfg) if cfg["enabled"] else None) or now + timedelta(days=1)
    cfg["override"], cfg["override_until"] = action, ends.isoformat(timespec="minutes")
    return cfg
