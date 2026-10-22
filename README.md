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

**Status:** planning. See [docs/plan.md](docs/plan.md).

## Hardware

Raspberry Pi 3A+, Adafruit RGB Matrix Bonnet, 64x32 HUB75 panel (P3, about 7.5x3.8 in),
5V 4A power supply, microSD card.

## Credits and license

Built on [It's Post Time](https://github.com/djjoman68/itsposttime), the LED odds board, which is
built on the plane tracker by **c0wsaysmoo**
([plane-tracker-rgb-pi](https://github.com/c0wsaysmoo/plane-tracker-rgb-pi)), based on
**Colin Waddell's** [FlightTracker](https://github.com/ColinWaddell/FlightTracker).

Panel driver: [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix), installed
separately during setup.

Released under the **GNU General Public License v3.0**, the same license as FlightTracker.
See [LICENSE](LICENSE).

Race data is read from nyra.com for personal, non-commercial display.
