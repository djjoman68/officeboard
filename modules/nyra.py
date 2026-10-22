"""NYRA racing: Saratoga or Belmont, using itsposttime's reader, feed and screens (docs/plan.md, module 3).

Rotation (the default): on race days NYRA takes its turn like any other module. Within the race window
(90 minutes before post) its turn shows the next race, as itsposttime's full odds board or big MTP;
before that, today's card and the Pick 5s still to start (not before `card_start`, 9am). No racing
today: skipped.

Hold near post (on by default): from 3 MTP the race board comes on and stays until the board moves on
to the next race (itsposttime's signal: the next race's odds go live, or the race is made official).

Take over (off by default): itsposttime's behaviour. From the race window the race board holds the
panel until the day's racing is over; the other modules pause.

Sleep mode beats both (core/display.py).
"""
from datetime import datetime, time as dtime

from core import pixels
from core.module import Module
from racing import nyra, render
from racing.feed import RaceFeed

TRACK_SHORT = {"saratoga": "SAR", "belmont": "BEL"}


class Nyra(Module):
    id = "nyra"
    name = "NYRA racing"
    description = "Next race, minutes to post and live odds at Saratoga or Belmont."
    default_seconds = 20
    fields = [
        {"key": "track", "label": "Track", "type": "select", "default": "auto",
         "options": [["auto", "Auto (whichever is racing today)"], ["saratoga", "Saratoga"], ["belmont", "Belmont Park"]]},
        {"key": "view", "label": "Race view", "type": "select", "default": "full",
         "options": [["full", "Full odds board"], ["big_mtp", "Big MTP"]]},
        {"key": "hold", "label": "Show the race board near post time", "type": "bool", "default": True,
         "hint": "From the minutes below, the race comes on and stays until the board moves to the next race."},
        {"key": "hold_mtp", "label": "Near post: minutes to post", "type": "int", "default": 3, "min": 1, "max": 15},
        {"key": "takeover", "label": "Take over the panel (like the odds board)", "type": "bool", "default": False,
         "hint": "From the race window below until the last race, only the race board shows."},
        {"key": "window_minutes", "label": "Race window (minutes before post)", "type": "int", "default": 90,
         "min": 5, "max": 180, "hint": "Inside it the odds are read and the race board shows; before it, today's card."},
        {"key": "poll_seconds", "label": "Odds refresh (seconds)", "type": "int", "default": 20, "min": 10, "max": 120,
         "hint": "Minimum 10. 20 is gentle on NYRA's site."},
        {"key": "card_start", "label": "Show today's card from", "type": "time", "default": "09:00"},
    ]

    def __init__(self, board=None):
        super().__init__(board)
        self.feed = RaceFeed(lambda: self.settings if self.enabled else None, start=False)
        self._pages_key = None

    def start(self):
        self.feed.start()

    def configure(self, settings):
        old = (self.enabled, self.settings.get("track"))
        super().configure(settings)
        if (self.enabled, self.settings["track"]) != old:
            self.feed.refresh_now()

    # ---------- what's on ----------
    def race(self, now=None):
        """The race in the window with its minutes to post, or None."""
        race = self.feed.race
        if race:
            race["mtp"] = nyra.minutes_to_post(race["post_time"])
        return race

    def card_screen(self, now):
        """(races still to come, Pick 5s still to start) for today's card, or None."""
        h, m = (int(x) for x in self.settings["card_start"].split(":"))
        if not self.feed.track or now.time() < dtime(h, m):
            return None
        card = list(self.feed.card)
        rows = [c for c, st in zip(card, nyra.card_states(card, self.feed.next_race)) if st != "done"]
        if not rows:
            return None
        upcoming = {r["race"] for r in rows}
        seqs = [dict(p, post_time=c["post_time"]) for c in card for p in c.get("pick5s", []) if c["race"] in upcoming]
        return rows, seqs

    def has_content(self, now):
        return bool(self.race(now) or self.card_screen(now))

    def _near_post(self, race):
        return bool(race) and self.settings["hold"] and race["mtp"] <= self.settings["hold_mtp"]

    def hold(self, now):
        return self._near_post(self.race(now))

    def takeover(self, now):
        """Take-over mode: the whole race window. Otherwise just near post (see the module notes)."""
        race = self.race(now)
        return bool(race) and (self.settings["takeover"] or self._near_post(race))

    # ---------- screens ----------
    def pages(self, now):
        race = self.race(now)
        screen = None if race else self.card_screen(now)
        key = (repr(race), repr(screen), self.settings["view"], self.feed.track, now.strftime("%H:%M"))
        if key != self._pages_key:
            if race:
                if self.settings["view"] == "big_mtp":
                    pages = [render.render_big_mtp(race, now=now)]
                else:
                    pages = [render.render_full_board(race, p) for p in range(render.page_count(race))]
            elif screen:
                rows, seqs = screen
                track = self.feed.track
                pages = [render.render_card(track, rows, p) for p in range(render.card_page_count(rows))]
                pages += [render.render_pick5(track, seqs, p) for p in range(render.pick5_page_count(seqs))]
            else:
                pages = []
            self._pages, self._pages_key = pages, key
        return self._pages

    def ticker_items(self, now):
        track = TRACK_SHORT.get(self.feed.track, "")
        race = self.race(now)
        if race:
            horses = render.active_horses(race)
            items = [[(f"{track} R{race['race']} ", render.BLUE), (f"{race['mtp']} MTP", render.mtp_color(race["mtp"]))]]
            items += [[(f"#{h['program']} ", pixels.WHITE), (render.display_odds(h["odds"]), render.odds_color(h["odds"], h["ml"]))]
                      for h in horses]
            return items
        screen = self.card_screen(now)
        if not screen:
            return []
        rows, seqs = screen
        items = [[(f"{render.TRACK_LABELS.get(self.feed.track, track)} TODAY", render.TRACK_COLORS.get(self.feed.track, pixels.WHITE))]]
        for r in rows:
            surface = render.short_surface(r["surface"])
            items.append([(f"R{r['race']} ", render.BLUE), (render.short_post(r["post_time"]) + " ", pixels.WHITE),
                          (render.short_distance(r["distance"]) + " ", pixels.WHITE),
                          (surface, render.SURFACE_COLORS.get(surface, pixels.WHITE))])
        for p in seqs:
            items.append([(f"{p['label']} PICK 5 ", pixels.WHITE), (f"{p['first']}-{p['last']} ", render.BLUE),
                          (render.short_post(p["post_time"]), pixels.WHITE)])
        return items

    # ---------- for the web UI ----------
    def status(self):
        card = list(self.feed.card)
        states = nyra.card_states(card, self.feed.next_race) if card else []
        race = self.race()
        return {
            "last_update": self.feed.last_update.isoformat(timespec="seconds") if self.feed.last_update else None,
            "last_error": self.feed.last_error,
            "track": self.feed.track,
            "race": race["race"] if race else None,
            "card": [dict(c, state=st, mtp=nyra.minutes_to_post(c["post_time"]) if st == "next" else None)
                     for c, st in zip(card, states)],
        }
