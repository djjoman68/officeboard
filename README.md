# Office Board

A Raspberry Pi and a small 64x32 RGB LED panel (3mm pitch) for the office. It rotates through
modules you turn on and off from a web page:

- **Clock & weather**: date, time, current weather, sunrise and sunset
- **Stocks**: major indexes plus your own list of stocks
- **NYRA racing**: next race, minutes to post and live odds for Saratoga or Belmont Park
- **MLB**: today's games with moneylines, then live scores
- **NFL**: this week's games with spread and total, then live scores

It also tests scrolling text against static pages, to see which reads better on a small panel.
A sleep mode shows just the clock and date at a dimmer brightness on a schedule.

**Status:** foundation built (Oct 2026): module system, smooth-scrolling display loop, web UI with a
Modules page, and a Panel test module. The data modules come next. See [docs/plan.md](docs/plan.md).

## Web UI

`http://officeboard.local:8080`
- **Board**: live picture of the panel and which modules are in rotation
- **Modules**: turn each module on or off, change the order, and edit its settings
- **Settings**: brightness, page flip, scroll speed, panel hardware, Wi-Fi, restart and shut down
- **Logs**: recent service output

## Install

See **[SETUP.md](SETUP.md)**: blank SD card to running board, step by step.

## Try it without the Pi

    python tools/dev.py        # whole board with a pretend panel: http://localhost:8080
    python tools/preview.py    # writes preview.gif, an LED-style animation of the panel
    python -m unittest discover tests

## Project layout

| Path | What it is |
|---|---|
| `officeboard.py` | Entry point |
| `install.sh` | Installer and auto-start service |
| `config.py`, `config/` | Settings (`config.json`, `secrets.json` are created on the Pi, not stored in git) |
| `core/display.py` | Main loop: draws the module whose turn it is, up to 60 frames a second |
| `core/scheduler.py` | Whose turn it is: rotation order, turn length, hold and take-over |
| `core/module.py` | What every module is made of: fetcher, pages / ticker, settings |
| `core/registry.py` | The list of modules |
| `core/pixels.py` | Drawing: pixel fonts, scrolling, LED-style pictures |
| `modules/` | The modules |
| `web/` | Web UI |
| `tools/` | Preview and try-it-on-a-computer tools |

## Hardware

Raspberry Pi 3A+, Adafruit RGB Matrix Bonnet, 64x32 HUB75 panel (P3, about 7.5x3.8 in),
5V 4A power supply, microSD card.

## Credits and license

Built on [It's Post Time](https://github.com/djjoman68/itsposttime), the LED odds board, which is
built on the plane tracker by **c0wsaysmoo**
([plane-tracker-rgb-pi](https://github.com/c0wsaysmoo/plane-tracker-rgb-pi)), based on
**Colin Waddell's** [FlightTracker](https://github.com/ColinWaddell/FlightTracker).

The pixel fonts, web UI, installer and Wi-Fi settings come from those projects; files copied from
them say so at the top.

Panel driver: [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix), installed
separately during setup.

Released under the **GNU General Public License v3.0**, the same license as FlightTracker.
See [LICENSE](LICENSE).

Race data is read from nyra.com for personal, non-commercial display.
