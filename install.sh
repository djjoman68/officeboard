#!/bin/bash
# Office board installer. Run from inside the officeboard folder:   bash install.sh
# From itsposttime's install.sh. Modified for the office board.
# Safe to run again after updating the files.
#   bash install.sh --uninstall    removes the auto-start service (leaves your files)
set -e

SERVICE=officeboard
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="$(whoami)"

say()  { echo -e "\n\033[1;33m==> $*\033[0m"; }
ok()   { echo -e "    \033[1;32mOK\033[0m  $*"; }
fail() { echo -e "\n\033[1;31mSTOP: $*\033[0m\n"; exit 1; }

if [ "$1" == "--uninstall" ]; then
  say "Removing the $SERVICE service"
  sudo systemctl disable --now "$SERVICE" 2>/dev/null || true
  sudo rm -f "/etc/systemd/system/$SERVICE.service" "/etc/sudoers.d/$SERVICE"
  sudo systemctl daemon-reload
  ok "Service removed. Your files in $APP_DIR were left alone."
  exit 0
fi

[ "$EUID" -eq 0 ] && fail "Run this as your normal user, not with sudo:   bash install.sh"

say "1/7  Checking the LED panel library"
python3 -c "import rgbmatrix" 2>/dev/null \
  || fail "The rgbmatrix library isn't installed yet. Finish the panel setup steps in SETUP.md (and the panel test) first."
ok "rgbmatrix library found"

say "2/7  Installing Python packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-requests python3-bs4 python3-flask python3-pil
python3 -c "import requests, bs4, flask, PIL, zoneinfo" || fail "A Python package failed to install."
ok "requests, beautifulsoup4, flask, pillow"

say "3/7  Letting Python drive the panel smoothly"
PY_REAL="$(readlink -f "$(command -v python3)")"
sudo setcap 'cap_sys_nice=eip' "$PY_REAL"
ok "realtime priority allowed for $PY_REAL"

say "4/7  Checking for anything else that auto-starts the board"
if crontab -l 2>/dev/null | grep -q "officeboard"; then
  crontab -l | grep -v "officeboard" | crontab -
  ok "removed an old crontab entry (prevents two copies fighting over the panel)"
else
  ok "no crontab entries"
fi
for other in its-a-plane odds-board; do
  if systemctl list-unit-files 2>/dev/null | grep -q "^$other.service"; then
    echo "    NOTE: the '$other' service is installed on this Pi. Only one program can drive the panel."
    echo "          Disable it with:  sudo systemctl disable --now $other"
  fi
done

say "5/7  Creating the auto-start service"
chmod +x "$APP_DIR/officeboard.py"
sudo tee "/etc/systemd/system/$SERVICE.service" > /dev/null << UNIT
[Unit]
Description=LED Office Board
Wants=network-online.target
After=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/officeboard.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE" > /dev/null 2>&1
ok "service installed and set to start on boot"

say "6/7  Letting the web page restart, shut down and change Wi-Fi"
# Only these commands, as root, without a password - everything else still asks for it.
SYSTEMCTL="$(command -v systemctl)"
NMCLI="$(command -v nmcli || true)"
RULES="$RUN_USER ALL=(root) NOPASSWD: $SYSTEMCTL restart $SERVICE, $SYSTEMCTL poweroff"
[ -n "$NMCLI" ] && RULES="$RULES, $NMCLI"
TMP_RULES="$(mktemp)"
echo "# Office board web page (installed by install.sh)" > "$TMP_RULES"
echo "$RULES" >> "$TMP_RULES"
# Check the rule before installing it: a broken sudoers file can lock out sudo entirely
sudo visudo -cf "$TMP_RULES" > /dev/null || fail "The permission rule didn't pass the system's check. Nothing was changed."
sudo install -m 0440 -o root -g root "$TMP_RULES" "/etc/sudoers.d/$SERVICE"
rm -f "$TMP_RULES"
ok "restart and shut down allowed${NMCLI:+, Wi-Fi changes allowed}"
[ -z "$NMCLI" ] && echo "    NOTE: NetworkManager (nmcli) isn't installed, so Settings -> Wi-Fi won't be available."

say "7/7  Starting the board"
sudo systemctl restart "$SERVICE"
sleep 8
if systemctl is-active --quiet "$SERVICE"; then
  ok "running"
  echo
  echo "    Open the web page:   http://$(hostname).local:8080"
  echo "    The panel shows the Panel test. Turn modules on and off on the Modules page."
  echo
else
  echo
  sudo journalctl -u "$SERVICE" -n 30 --no-pager
  fail "The service didn't stay running. The log above shows why - copy it into the chat for help."
fi
