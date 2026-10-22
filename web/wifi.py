"""Copied from itsposttime (the LED odds board). Modified for the office board: unchanged so far.

Wi-Fi networks for the Settings page, through NetworkManager's nmcli (Raspberry Pi OS).

    status()             -> current network, signal, saved networks
    scan()               -> networks in range, strongest first
    add(ssid, password)  -> save a network; the Pi joins it whenever it's in range
    forget(name)         -> delete a saved network (never the one in use)
    switch(name)         -> join a saved network now, in the background; if it can't,
                            go back to the previous network. last_switch() reports how it went.

Runs nmcli as root through the sudoers rule install.sh writes (no password, nmcli only).
Adding a network never disconnects anything; only switch() changes the connection.
"""
import subprocess
import threading
import time

NMCLI = ["sudo", "-n", "nmcli"]
SWITCH_WAIT = 45               # seconds to try joining before going back


class WifiError(Exception):
    pass


def _run(args, timeout=30):
    try:
        r = subprocess.run(NMCLI + args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise WifiError("Wi-Fi settings need NetworkManager (nmcli), which wasn't found on this Pi.")
    except subprocess.TimeoutExpired:
        raise WifiError("The Pi's Wi-Fi tool didn't answer in time. Try again.")
    if r.returncode != 0 and "password is required" in r.stderr:
        raise WifiError("The Pi wouldn't allow Wi-Fi changes. Run 'bash install.sh' again on the Pi to fix this.")
    if r.returncode != 0:
        raise WifiError((r.stderr or r.stdout).strip().replace("Error: ", "") or f"nmcli failed ({r.returncode})")
    return r.stdout


def _split(line):
    """nmcli -t output: fields split on ':', with literal ':' and '\\' escaped by a backslash."""
    fields, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur, esc = cur + ch, False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            fields.append(cur)
            cur = ""
        else:
            cur += ch
    fields.append(cur)
    return fields


def _rows(args):
    return [_split(line) for line in _run(["-t"] + args).splitlines() if line]


def _device():
    """(wifi device name, its active connection name or '')."""
    for dev, kind, _state, conn in _rows(["-f", "DEVICE,TYPE,STATE,CONNECTION", "device"]):
        if kind == "wifi":
            return dev, "" if conn in ("", "--") else conn
    raise WifiError("No Wi-Fi adapter found on this Pi.")


def _saved(active):
    nets = []
    for name, kind in _rows(["-f", "NAME,TYPE", "connection", "show"]):
        if kind in ("802-11-wireless", "wifi"):
            ssid = _run(["-e", "no", "-g", "802-11-wireless.ssid", "connection", "show", name]).strip()
            nets.append({"name": name, "ssid": ssid or name, "active": name == active})
    return nets


def status():
    _dev, active = _device()
    current, signal = None, None
    for in_use, ssid, sig in _rows(["-f", "IN-USE,SSID,SIGNAL", "device", "wifi", "list", "--rescan", "no"]):
        if in_use.strip() == "*":
            current, signal = ssid, int(sig or 0)
    return {"available": True, "current": current, "signal": signal, "saved": _saved(active)}


def scan():
    """Networks in range, one entry per name (strongest signal), strongest first."""
    best = {}
    for ssid, sig, security in _rows(["-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"]):
        if not ssid:
            continue                 # hidden network; can still be added by typing its name
        sig = int(sig or 0)
        if ssid not in best or sig > best[ssid]["signal"]:
            best[ssid] = {"ssid": ssid, "signal": sig, "security": "" if security in ("", "--") else security}
    return sorted(best.values(), key=lambda n: -n["signal"])


def add(ssid, password, security=""):
    """Save a network (or update the password of one already saved). Doesn't switch to it."""
    ssid, password = (ssid or "").strip(), password or ""
    if not ssid:
        raise WifiError("Enter the network name.")
    if password and not 8 <= len(password) <= 63:
        raise WifiError("Wi-Fi passwords are 8 to 63 characters.")
    dev, active = _device()
    sec = []
    if password:
        # WPA3-only networks need SAE; everything else (WPA2, WPA2/WPA3 mixed) takes WPA-PSK
        key_mgmt = "sae" if "WPA3" in security and "WPA2" not in security else "wpa-psk"
        sec = ["wifi-sec.key-mgmt", key_mgmt, "wifi-sec.psk", password]
    existing = next((n["name"] for n in _saved(active) if n["ssid"] == ssid), None)
    if existing:
        _run(["connection", "modify", existing] + (sec or ["remove", "802-11-wireless-security"]))
        return existing
    _run(["connection", "add", "type", "wifi", "con-name", ssid, "ifname", dev, "ssid", ssid,
          "connection.autoconnect", "yes"] + sec)
    return ssid


def forget(name):
    _dev, active = _device()
    if name == active:
        raise WifiError("That's the network the board is using right now. Switch to another one first.")
    _run(["connection", "delete", name])


_last_switch = {}
_lock = threading.Lock()


def last_switch():
    with _lock:
        return dict(_last_switch)


def _set_switch(**kw):
    with _lock:
        _last_switch.clear()
        _last_switch.update(kw, at=time.strftime("%H:%M:%S"))


def _do_switch(name, previous):
    try:
        _run(["--wait", str(SWITCH_WAIT), "connection", "up", name], timeout=SWITCH_WAIT + 15)
        _set_switch(name=name, state="ok")
    except WifiError as e:
        back = False
        if previous:
            try:
                _run(["connection", "up", previous], timeout=SWITCH_WAIT + 15)
                back = True
            except WifiError:
                pass
        _set_switch(name=name, state="failed", error=str(e), previous=previous if back else None)


def switch(name, background=True):
    """Join a saved network now. Runs in the background because the page's own
    connection may drop; if joining fails, rejoins the previous network."""
    _dev, previous = _device()
    if name == previous:
        raise WifiError(f"Already connected to {name}.")
    _set_switch(name=name, state="switching", previous=previous)
    if background:
        threading.Thread(target=_do_switch, args=(name, previous), daemon=True).start()
    else:
        _do_switch(name, previous)
