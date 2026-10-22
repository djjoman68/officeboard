# CLAUDE.md — Office board (modular LED panel)

Read this first every session, then `docs/plan.md`, which holds every decision made so far.

## Who you're working with

Joe owns this project. He doesn't write code: you do all the coding, and he makes the design calls.
- Explain changes in plain language. Lead with what changes on the panel or web page.
- Show visual changes before he has to imagine them: a preview image, or an animated GIF for scrolling.
- Ask before pushing to GitHub or creating anything there. Commit freely with clear messages.
- Don't change an agreed decision in `docs/plan.md` unless Joe asks. If one causes a problem, explain
  it and offer options. When Joe changes a decision, update the plan and note the date.

## What it is

Raspberry Pi 3A+ + 64x32 RGB LED panel, 3mm pitch, in Joe's office. Shows modules (clock/weather,
stocks, NYRA racing, MLB, NFL) that can each be turned on and off from a web UI at
`officeboard.local:8080`, and tests scrolling against static pages.

Built on the odds board, **itsposttime** (https://github.com/djjoman68/itsposttime; local copy in
`../itsposttime/itsposttime`), which is built on the plane tracker (c0wsaysmoo/plane-tracker-rgb-pi),
based on ColinWaddell/FlightTracker (GPL-3.0). Read itsposttime's CLAUDE.md before reusing its code:
its NYRA notes (page structure, race lifecycle, polling limits) apply here unchanged.

Repo: https://github.com/djjoman68/officeboard (public, created Oct 22 2026).

## Status

- Oct 22 2026: plan agreed (`docs/plan.md`). Repo created.
- Oct 22 2026: step 1 (foundation) built and tested offline: module system, scheduler, 50 fps display
  loop, web UI (Board, Modules, Settings, Logs), installer, Panel test module. Not yet run on the Pi.
- Oct 22 2026: step 2 built and tested offline: Clock & weather module (itsposttime's layout and
  sources), sleep mode (schedule, all-day days, Sleep now / Wake now).
- Oct 22 2026: step 3 built: four layouts (pages, roll, full ticker, split), board-wide or per module,
  Scroll demo module, comparison GIFs (`python3 tools/compare_layouts.py` -> previews/).
- Oct 22 2026: Joe picked **Roll** (layout C) for the board; it's the default. Design new modules'
  pages first (they roll); keep ticker_items too.
- Oct 22 2026: step 4 built: Stocks module (Finnhub; indexes via DIA/SPY/QQQ). Tested offline only.
- Oct 22 2026: step 5 built: NYRA module on itsposttime's racing code (racing/), rotation, near post
  (comes on at 3 MTP), take-over. Tested offline only.
- Oct 22 2026: steps 6 and 7 built together: MLB and NFL modules with odds, all from ESPN's scoreboard
  feed. Checked live on Joe's PC (NFL week 7). Every module in the plan is now built; next is running it
  on the Pi and the 3mm panel.
- Hardware: the P3 panel has not been tested yet. SETUP.md step 5 covers the FM6126A driver chip.

## Layout

| Path | Role |
|---|---|
| `officeboard.py` | Entry point; single-instance lock (/tmp/officeboard.lock); starts web UI subprocess |
| `config.py` | Board-wide settings (display, location, sleep), JSON load/save (config/config.json + secrets.json) |
| `core/module.py` | `Module` base class (fetch, pages, ticker_items, frame, hold, takeover, fields) and `Fetcher` thread |
| `core/registry.py` | `MODULE_CLASSES` list; merges every module's settings; planned modules can't be enabled |
| `core/scheduler.py` | Rotation: order, turn length, skip modules with nothing to show, hold, take-over. Pure logic |
| `core/display.py` | Panel options + main loop at `fps`; only changed frames go to the panel; status + frame to /dev/shm/officeboard |
| `core/pixels.py` | Pillow drawing with the .bdf fonts, `text_strip` + `marquee` for scrolling, `led_preview` |
| `core/layouts.py` | The four layouts: `roll`, `ticker`, `split`, `text_page`; `join_items` for ticker text |
| `core/sleep.py` | Sleep schedule, all-day days, Sleep now / Wake now overrides. Pure logic |
| `modules/clock.py` | Clock & weather: Tomorrow.io fetch + disk cache, one screen: itsposttime's top band, today's icon + high/low, today's sunrise/sunset; alerts; sleep screen |
| `modules/nws.py` | Severe weather alerts (from itsposttime) |
| `modules/stocks.py` | Stocks: Finnhub quotes + market status, Markets page, one page (or 3 rows) per stock |
| `modules/nyra.py` | NYRA module: card before the window, race in it, near post (takeover at hold_mtp), take-over mode |
| `racing/nyra.py`, `racing/feed.py`, `racing/render.py` | itsposttime's NYRA reader, polling feed (settings from the module) and race screens |
| `modules/games.py` | MLB (today, moneylines) and NFL (this week, spread + total) from ESPN: preview and score pages, team colours, logos (downloaded to .cache/logos) |
| `modules/demo.py` | Scroll demo: made-up stocks, race, games for comparing layouts; remove when real modules exist |
| `modules/paneltest.py` | Panel test module (opts out of layouts) |
| `modules/planned.py` | Stand-ins for modules not built yet (none left; kept for future ideas) |
| `web/` | Flask app on :8080. Modules page forms are built from each module's `fields` |
| `tools/preview.py` | preview.gif / preview.png of the rotation, simulated time |
| `tools/compare_layouts.py` | previews/layout-a..d GIFs: clock + scroll demo in each layout |
| `tools/dev.py` | Whole board on a computer with the fake panel, web UI on localhost:8080 |
| `tests/` | Offline tests with a fake `rgbmatrix` (tests/fakes) |

To add a module: subclass `Module` in modules/, give it `pages()` and `ticker_items()` (so every layout
works), list it in `core/registry.py` in place of its planned stand-in, add tests, and preview it.
`Module.frame` picks the layout; a module that draws its own way overrides `page_frame` (the clock) or
sets `supports_layouts = False` (the panel test).

## Working rules

- Test before committing: `python3 -m unittest discover tests` (no panel or internet needed).
- Visual changes: `python3 tools/preview.py` and show Joe the GIF (or a frame of it).
- This folder is its own git repo, separate from the pick5 repo in the parent folder.
- Never commit `config/*.json` (secrets, Pi settings) or team logos (.cache/logos; teams' trademarks).
- License is GPL-3.0. Keep credits in README.md. When copying a file from itsposttime or the plane
  tracker, keep its notes at the top and add "Modified for the office board".
- Keep NYRA polling gentle: use itsposttime's limits, never faster. The racing/ files and
  tests/test_nyra_reader.py are itsposttime's; fix NYRA page changes in both projects.
- Data sources are free tiers or unofficial feeds: cache results, poll no faster than needed, and keep
  showing the last good data when a fetch fails.
- The Pi runs one copy only (lock file + systemd).
