# Office board — plan

Agreed with Joe, Oct 22 2026. This is the outline we build from. When a decision changes, update
this file and note the date.

## What it is

A Raspberry Pi 3A+ and a 64x32 RGB LED panel with a **3mm pitch** (about 7.5 x 3.8 in) for Joe's
office. Built on the same foundation as the odds board
([itsposttime](https://github.com/djjoman68/itsposttime)), but showing several kinds of data, each as
a **module** that can be turned on and off from a web UI. It also tests whether **scrolling** presents
information better than static pages.

- Name: **office board**. Address: `officeboard.local` (web UI on port 8080).
- Repo: public, `djjoman68/officeboard`, GPL-3.0 (required: it reuses GPL code).

## What carries over from itsposttime

Copied as-is or nearly so:
- Panel setup (rpi-rgb-led-matrix), one-copy lock file, systemd service, install.sh
- Config pattern: `config/config.json` + `config/secrets.json`, created on the Pi, never committed,
  web UI changes picked up live
- Flask web UI shell: Board (live picture of the panel), Settings, Wi-Fi, Restart, Shut down, Logs, and
  the sudoers rule for root actions
- Fake `rgbmatrix` for offline tests; the preview tool
- `nyra.py` and the race feed, reused unchanged (keep its polling limits)
- Fonts, weather icons, the clock/date/forecast/sun drawing

Rewritten: **the main loop**. itsposttime's screens are mixins that step aside when a race is on.
That works for two modes, not six. The office board uses a module system instead.

## Module system

Each module has three parts:

| Part | Job |
|---|---|
| **Fetcher** | Background thread on its own schedule; keeps the latest data in a cache. A failed fetch keeps the last good data and reports the error to the web UI. |
| **Renderer** | Turns the data into **pages** (static screens) and **ticker items** (short text pieces for scrolling). Every module provides both, so presentation can be compared. |
| **Settings** | On/off, how long its turn lasts, and its own options, all in the web UI. |

A **scheduler** rotates through enabled modules in the order Joe sets. A module with nothing to show
(no games, no racing, market data unavailable) is skipped. Modules can ask to **hold** or **take over**
the panel (see NYRA).

Web UI **Modules** page: on/off toggle, drag to reorder, turn length, a settings panel per module,
and each module's last update time and error.

## Scroll experiment

Do this early: it shapes how every module draws.

- itsposttime's loop runs at 10 frames per second, fine for static screens but choppy for scrolling.
  Smooth scrolling needs about 30-60 fps with 1-pixel steps, so the new loop needs a faster draw path.
- Layouts to compare:
  - **A. Full ticker**: one large line scrolling right to left across the panel.
  - **B. Split**: fixed top bar (time + temperature), ticker scrolling underneath.
  - **C. Vertical roll**: pages slide up like a departures board.
  - **D. Pages**: static screens that rotate (today's approach).
- Selectable for the whole board and per module.
- Preview tool makes **animated GIFs** of each layout so Joe can compare before using the panel.
- Readability: a small font fits about 10 characters across 64 pixels. Scroll speed adjustable.

## Modules

### 1. Clock, date, weather, sun
- Date, time, current weather, today's forecast, sunrise and sunset.
- Port of itsposttime's idle screens (Tomorrow.io + NWS alerts). Open-Meteo is a free, no-key option
  if needed.

### 2. Stocks
- Always shows the **major indexes**: Dow, S&P 500, Nasdaq.
- Then Joe's own list of individual stocks, edited in the web UI (add, remove, reorder).
- Live during market hours (9:30-4:00 ET); otherwise last close and the day's change.
- Source: Finnhub free tier for stocks. Its free tier has no index data, so indexes come from the
  matching funds (DIA, SPY, QQQ), labeled DOW / S&P / NASDAQ and led by % change. Yahoo for real
  index numbers is a possible later fallback (unofficial, can break).

### 3. NYRA racing
- Uses itsposttime's `nyra.py` and race feed.
- **Rotation mode (default)**: on race days NYRA takes its turn like any other module. Its turn shows
  the next race: odds board or big MTP (same Full/Big MTP setting as itsposttime). Before the first
  race's window: today's card and Pick 5s. In scroll mode, a ticker line ("BEL R5 · 7 MTP · #3 5/2 fav").
  No racing today: skipped.
- **Hold near post**: in rotation mode, at **3 MTP or less** NYRA keeps the panel until the race goes
  off (or the next race's odds go live, itsposttime's move-on signal). On/off switch and adjustable
  cutoff in the web UI. Default: on, 3 minutes.
- **Take over panel** (switch, default off): itsposttime's behavior. From `race_window_minutes` (90)
  before post the race board holds the panel until the day's racing ends; paging, card, Pick 5s, MTP
  colors and polling carry over. Other modules pause and come back after.

### 4. MLB
- **All games today.**
- Before first pitch: teams, start time, **moneyline only** ("NYY @ BOS 7:10p · NYY -145 / BOS +125").
  Both teams' prices by default; favorite-only is a possible shorter option.
- During and after: score, inning, FINAL.
- Source: statsapi.mlb.com (free, official) for games; odds from ESPN's scoreboard feed.
- Off-season: skipped.

### 5. NFL
- **All games this week**: Thursday through Monday night (ESPN's week), rolls over Tuesday morning.
- Before kickoff: teams, day/time, **spread and total** ("NYJ @ BUF 1:00p · BUF -6.5 · O/U 44.5").
- During and after: score, quarter, FINAL.
- Source: ESPN's scoreboard feed (free, unofficial), which usually includes spread, total and moneyline.
- Off-season: skipped.

To verify before building 4 and 5: ESPN's feed reliably has MLB moneylines and NFL spread/total. If
not, The Odds API (free tier, about 500 calls/month) is the fallback.

## Sleep mode

The board runs all hours. Sleep mode switches the panel to **clock and date only** at its own
brightness.
- Schedule: start and end time; optional day selection (e.g. all day on weekends).
- Own brightness slider, separate from daytime; 0 turns the panel off.
- Sleep now / Wake now buttons on the Board page, lasting until the next scheduled change.
- Replaces itsposttime's night-brightness setting.
- Sleep beats NYRA take-over (a race during sleep hours is not shown).
- Sleep screen: time and date only, no weather.

## Hardware

- Raspberry Pi 3A+, Adafruit RGB Matrix Bonnet, 64x32 HUB75 panel **P3**, 5V 4A supply.
- First step on hardware: a plain panel test. Some P3 panels use the FM6126A driver chip and need
  `led-panel-type=FM6126A` to light up; this becomes a setting if so.
- The panel is small: fonts and layouts get checked on the real panel early.

## Build order

Each step ends with a preview (image or GIF) for Joe to approve.

1. **Foundation**: copy the carried-over pieces, module system, scheduler, fast draw loop, Modules page.
   **Done Oct 22 2026.** Notes: modules draw Pillow images, so the web picture and previews match the
   LEDs exactly. Includes a Panel test module (colour bars + scrolling text with the frame rate) for
   checking the P3 panel. Reordering uses up/down buttons rather than drag (works the same on a phone).
   Web UI has a plain placeholder look; its style is Joe's call later.
2. **Clock/weather module**: proves the framework; includes sleep mode.
   **Done Oct 22 2026.** Same layout and colours as itsposttime's clock & weather screen, same sources
   (Tomorrow.io: current every 10 min, forecast hourly; NWS alerts every 10 min), and weather saved to disk
   so it shows straight after a restart. Choices made while building, open to change:
   - Sunrise/sunset show for the last 6 seconds of each clock turn (adjustable, 0 = off), replacing the
     forecast, instead of itsposttime's last 15 seconds of every minute (turns are shorter than a minute).
   - Location, units, clock format, Tomorrow.io key and alerts are board-wide Settings, since other
     modules (games, races) show times too. A separate free Tomorrow.io key from the odds board's is
     suggested.
   - itsposttime's hourly forecast mode wasn't carried over (daily only).
   - Sleep: "asleep all day on" chosen days, on top of the nightly window. Sleep now / Wake now last
     until the schedule's next change, or a day when there's no schedule; "Back to schedule" cancels.
     The sleep screen is a centred clock (orange by day, blue at night) with the date in gray.
   - Clock & weather is on by default and first in the rotation; the Panel test stays on too.
3. **Scroll experiment**: GIF previews of layouts A-D, then the real panel. Joe picks.
4. **Stocks**.
5. **NYRA**: rotation, hold near post, take over.
6. **MLB + NFL** schedules and scores.
7. **Odds** on MLB and NFL.

## Still open

- Which scroll layout(s) win: decided in step 3.
- Joe's stock list: entered in the web UI once step 4 is built.
- MLB moneyline: both teams or favorite only (default both).
