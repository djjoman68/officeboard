"""Which module has the panel right now.

Modules take turns in Joe's order, each for its "seconds" setting. A module that's off or has
nothing to show is skipped. A module can keep the panel past its turn (`hold`, e.g. NYRA at 3 MTP)
or take it from the rotation entirely (`takeover`). Pure logic: times are passed in, so it's tested
without waiting.
"""
import logging

log = logging.getLogger("scheduler")


def _ask(module, method, now):
    """A module's answer, treating any error as 'no' so one broken module can't stop the board."""
    try:
        return bool(getattr(module, method)(now))
    except Exception as e:
        log.warning("%s.%s failed: %s", module.id, method, e)
        return False


class Scheduler:
    def __init__(self):
        self.current = None        # id of the module on the panel
        self.started = 0.0         # when its turn began (monotonic seconds)

    def pick(self, modules, now, mono):
        """(module, seconds into its turn) for this moment, or (None, 0) when nothing can show.
        `modules` is every module in rotation order; `now` the time of day; `mono` a steady clock."""
        live = [m for m in modules if m.enabled and _ask(m, "has_content", now)]
        if not live:
            self.current = None
            return None, 0.0

        for m in live:
            if _ask(m, "takeover", now):
                return self._show(m, mono)

        cur = next((m for m in live if m.id == self.current), None)
        if cur is not None:
            elapsed = mono - self.started
            if elapsed < cur.settings["seconds"] or len(live) == 1 or _ask(cur, "hold", now):
                return cur, elapsed
        return self._show(self._after(modules, live), mono)

    def _after(self, modules, live):
        """The next live module after the current one in rotation order (the first if none is current)."""
        ids = [m.id for m in modules]
        if self.current not in ids:
            return live[0]
        start = ids.index(self.current)
        live_ids = {m.id for m in live}
        for step in range(1, len(modules) + 1):
            m = modules[(start + step) % len(modules)]
            if m.id in live_ids:
                return m
        return live[0]

    def _show(self, module, mono):
        if module.id != self.current:
            self.current, self.started = module.id, mono
        return module, mono - self.started
