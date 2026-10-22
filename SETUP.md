# Setting up the Office Board

Adapted from itsposttime's setup guide: the same proven steps, renamed for the office board.

About an hour, mostly waiting on installs. You'll type commands, but you won't write any code.
Commands go in a terminal on the Pi (step 3 shows how to get one). Copy and paste them exactly.

Parts: Raspberry Pi 3A+, Adafruit RGB Matrix Bonnet, 64x32 HUB75 panel (3mm pitch), 5V 4A power supply,
microSD card (16GB+), heatsink, 2x20 header extender.

---

## 1. Prepare the microSD card (on your computer)

1. Install **Raspberry Pi Imager** from raspberrypi.com/software and open it.
2. Device: **Raspberry Pi 3**. OS: **Raspberry Pi OS (other) -> Raspberry Pi OS Lite (64-bit)**. Storage: your card.
3. When it asks about OS customisation, choose **Edit settings** and fill in:
   - Hostname: `officeboard`
   - Username and password: pick your own (the examples below use `joe`)
   - Wi-Fi name and password
   - Time zone: **America/New_York**
   - Services tab: turn on **Enable SSH** (password authentication)
4. Write the card, put it in the Pi.

## 2. Put the hardware together

1. Stick the heatsink on the Pi's processor.
2. Press the header extender onto the Pi's pins, then the Bonnet onto the extender.
3. Connect the panel's ribbon cable to the Bonnet and to the panel's **input** side (arrows on the
   panel point away from the input).
4. Connect the panel's power leads to the Bonnet's screw terminals (red to +, black to -).
5. Plug the 5V 4A supply into the **Bonnet's** barrel jack. It powers the Pi too, so don't also
   plug the Pi in by USB.

Give it 2 minutes to boot the first time.

## 3. Connect to the Pi

On Windows, open **PowerShell** (on a Mac, **Terminal**) and type, using your username:

    ssh joe@officeboard.local

Type `yes` if asked, then your password. You're now typing on the Pi.
(MobaXterm, which the plane tracker guide recommends, works too.)

## 4. Panel library (same proven steps as the plane tracker)

Install the build tools and the panel library:

    sudo apt-get update
    sudo apt-get install -y git python3-dev python3-pip python3-pillow cython3 python3-setuptools build-essential unzip
    cd ~
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
    cd rpi-rgb-led-matrix
    make

Give the Pi 3A+ more working memory for the next step (otherwise it can crash mid-install):

    sudo apt-get install -y dphys-swapfile
    sudo dphys-swapfile swapoff
    echo "CONF_SWAPSIZE=512" | sudo tee /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon

Run Adafruit's Bonnet setup:

    cd ~
    sudo pip3 install adafruit-python-shell --break-system-packages
    wget https://github.com/adafruit/Raspberry-Pi-Installer-Scripts/raw/main/rgb-matrix.py
    python3 -m venv --system-site-packages env
    source env/bin/activate
    sudo -E env PATH=$PATH python3 rgb-matrix.py

When the script asks:
- Interface board: **Bonnet** (option 1)
- **Convenience** (choose Quality only if you soldered the GPIO 4-18 bridge)
- Let it reboot when it finishes, then reconnect (step 3).

Make the library available everywhere:

    sudo cp -r ~/env/lib/python3.*/site-packages/rgbmatrix /usr/lib/python3/dist-packages/
    python3 -c "import rgbmatrix; print('ok')"

You must see `ok`. If not, stop and ask for help.

## 5. Test the panel

    cd ~/rpi-rgb-led-matrix/examples-api-use
    make
    sudo ./demo -D 1 runtext.ppm --led-rows=32 --led-cols=64 --led-limit-refresh=60 --led-slowdown-gpio=2 --led-gpio-mapping=adafruit-hat

You should see scrolling "HELLO WORLD". Press Ctrl+C to stop.

**Panel stays dark or shows garbage?** Many 3mm panels use a different driver chip. Try the same
command with `--led-panel-type=FM6126A` added on the end. If that works, set
**Settings -> Panel driver chip -> FM6126A** after step 6.

If the picture is still broken or in the wrong place, reseat the Bonnet and try again. Don't continue
until this works. (Colors swapped? That's fine - fix it later under Settings -> LED color order.)

## 6. Install the office board

Download the project from GitHub:

    cd ~
    git clone https://github.com/djjoman68/officeboard.git
    cd officeboard
    bash install.sh

The installer checks the panel library, installs what it needs, sets up auto-start, and starts the
board. It ends by printing the web address.

Optional: turn the extra memory back off to spare the SD card:

    sudo dphys-swapfile swapoff
    sudo systemctl disable dphys-swapfile

## 7. First look

Open **http://officeboard.local:8080** on your phone or computer.
- The panel shows the **Panel test**: eight colour bars (red, green, blue, white, yellow, cyan,
  magenta, gray) and scrolling text with the frame rate.
- If you needed FM6126A in step 5: **Settings -> Panel driver chip -> FM6126A**, Save, Restart display.
- Check every bar shows its colour and no rows are dark. Wrong colours: Settings -> LED color order.
- **Modules** lists everything planned. Modules arrive as they're built; turn them on there.

---

## Handy commands (on the Pi)

    sudo systemctl status officeboard      # is it running?
    sudo systemctl restart officeboard     # restart it
    sudo systemctl stop officeboard        # stop it (e.g. to run it by hand)
    sudo shutdown -h now                   # turn the Pi off safely (or Settings -> Shut down)
    journalctl -u officeboard -n 50        # recent log lines (also on the web Logs page)

## Updating to a new version

After new changes are pushed to GitHub:

    cd ~/officeboard
    git pull
    bash install.sh

Your settings and API keys are kept (they're never stored in git).

## If something's wrong

- **Web page won't load:** wait a minute after power-up; check `sudo systemctl status officeboard`.
- **Panel dark or garbled:** Settings -> Panel driver chip -> FM6126A, Save, Restart display.
- **Panel flickers:** Settings -> GPIO slowdown, try 3 or 4, Save, Restart display.
- **Colors wrong:** Settings -> LED color order (RBG is the common fix).
- **Scrolling looks jerky:** the Board page shows the frame rate; it should be close to the Settings value.
- **Anything else:** copy the output of `journalctl -u officeboard -n 50` into the chat.
