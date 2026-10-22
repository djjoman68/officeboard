"""Web UI for the office board - http://officeboard.local:8080

A small Flask app started alongside the display. It edits config/config.json and secrets.json; the
display picks up changes within a second (panel hardware settings after Restart).

From itsposttime's web/app.py. Modified for the office board: Modules page, board-wide display settings.
"""
import io
import os
import subprocess
import sys
import threading
import time

from flask import Flask, jsonify, render_template, request, send_file

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
import config  # noqa: E402
from core import registry, sleep  # noqa: E402
from core.pixels import led_preview  # noqa: E402
from web import wifi  # noqa: E402

SERVICE = "officeboard"
STATUS_DIR = "/dev/shm/officeboard" if os.path.isdir("/dev/shm") else os.path.join(BASE_DIR, ".cache")
STATUS_FILE = os.path.join(STATUS_DIR, "status.json")
FRAME_FILE = os.path.join(STATUS_DIR, "board.png")

app = Flask(__name__)


def _mask(v):
    return v[:4] + "****" + v[-4:] if isinstance(v, str) and len(v) > 8 else v


def _status():
    status = config.load(STATUS_FILE)
    if status:
        status["age_seconds"] = int(time.time() - os.path.getmtime(STATUS_FILE))
    return status or None


# ---------- pages ----------
@app.get("/")
def home():
    return render_template("index.html")


@app.get("/modules")
def modules_page():
    return render_template("modules.html")


@app.get("/config")
def config_page():
    return render_template("config.html")


@app.get("/logs")
def logs_page():
    return render_template("logs.html")


# ---------- API ----------
@app.get("/api/status")
def api_status():
    names = {i: d["name"] for i, d in registry.describe().items()}
    return jsonify({"status": _status(), "names": names})


@app.get("/panel")
def panel_page():
    """Pop-out window: just the panel picture, filling the window."""
    return render_template("panel.html")


@app.get("/board.png")
def board_png():
    """Latest picture of the panel, enlarged to look like the LEDs. ?dot=N sets the size of each LED
    in pixels (4-16, default 8): the pop-out window asks for bigger ones."""
    from PIL import Image
    if not os.path.exists(FRAME_FILE):
        return ("", 204)
    dot = config.clamp_int(request.args.get("dot", 8), 4, 16, 8)
    with Image.open(FRAME_FILE) as frame:
        img = led_preview(frame.convert("RGB"), dot=dot)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _modules_reply():
    cfg = registry.full_config()["modules"]
    info = registry.describe()
    live = (_status() or {}).get("modules", {})
    return {"modules": [dict(info[i], settings=cfg[i], status=live.get(i)) for i in cfg["order"]]}


@app.get("/api/modules")
def modules_get():
    return jsonify(_modules_reply())


@app.post("/api/modules")
def modules_save():
    """Body: {"order": [ids]} and/or {"settings": {id: {key: value}}}. Only the keys sent change."""
    data = request.get_json(force=True) or {}
    raw = config.load()
    mods = registry.modules_config(raw.get("modules"))
    if isinstance(data.get("order"), list):
        mods["order"] = data["order"]
    for mod_id, vals in (data.get("settings") or {}).items():
        if mod_id in registry.BY_ID and isinstance(vals, dict):
            mods[mod_id] = {**mods[mod_id], **vals}
    raw["modules"] = registry.modules_config(mods)
    try:
        config.save(raw)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify(dict(_modules_reply(), ok=True))


@app.get("/api/config")
def config_get():
    sec = config.load_secrets()
    full = registry.full_config()
    return jsonify({"config": {name: full[name] for name in config.SECTIONS},
                    "secrets": {k: _mask(v) for k, v in sec.items()}})


@app.post("/api/config")
def config_save():
    data = request.get_json(force=True) or {}
    try:
        sent = data.get("config") or {}
        if any(isinstance(sent.get(name), dict) for name in config.SECTIONS):
            raw = config.load()
            for name, normalize in config.SECTIONS.items():
                if isinstance(sent.get(name), dict):
                    raw[name] = normalize({**raw.get(name, {}), **sent[name]})
            config.save(raw)
        if isinstance(data.get("secrets"), dict):
            existing = config.load_secrets()
            for k, v in data["secrets"].items():
                if isinstance(v, str) and "****" in v:
                    continue          # unchanged masked value
                existing[k] = v.strip() if isinstance(v, str) else v
            config.save(existing, config.SEC_PATH)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.post("/api/sleep")
def sleep_now():
    """Board page buttons. Body: {"action": "sleep" | "wake" | "schedule"}. Lasts until the schedule's
    next change (a day without a schedule); "schedule" cancels it."""
    from datetime import datetime
    action = (request.get_json(force=True) or {}).get("action")
    raw = config.load()
    raw["sleep"] = config.normalize_sleep(sleep.override(datetime.now(), config.normalize_sleep(raw.get("sleep")), action))
    try:
        config.save(raw)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "sleep": raw["sleep"]})


def _sudo_allowed(cmd):
    """Whether install.sh's sudoers rule lets this exact command run without a password.
    (`sudo -l cmd` checks without running it; -n means never stop to ask for a password.)"""
    try:
        return subprocess.run(["sudo", "-n", "-l"] + cmd, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _sudo_later(cmd, error):
    """Run an allowed command a moment after the page gets its reply, or explain why not."""
    if not _sudo_allowed(cmd):
        return jsonify({"ok": False, "error": error}), 500

    def _do():
        time.sleep(1)
        subprocess.run(["sudo", "-n"] + cmd, capture_output=True)
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/restart")
def api_restart():
    return _sudo_later(["systemctl", "restart", SERVICE],
                       "The Pi wouldn't allow it. Run 'bash install.sh' again on the Pi to fix this.")


@app.post("/api/shutdown")
def api_shutdown():
    """Shut the Pi down so it can be unplugged without risking the SD card."""
    return _sudo_later(["systemctl", "poweroff"],
                       "The Pi wouldn't allow it. Run 'bash install.sh' again on the Pi, "
                       "or connect and type: sudo shutdown -h now")


# ---------- Wi-Fi (see web/wifi.py) ----------
def _wifi(fn):
    try:
        return jsonify(fn())
    except wifi.WifiError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.get("/api/wifi")
def wifi_status():
    try:
        return jsonify(dict(wifi.status(), last_switch=wifi.last_switch()))
    except wifi.WifiError as e:
        return jsonify({"available": False, "error": str(e), "last_switch": wifi.last_switch()})


@app.get("/api/wifi/scan")
def wifi_scan():
    return _wifi(lambda: {"ok": True, "networks": wifi.scan()})


@app.post("/api/wifi/add")
def wifi_add():
    d = request.get_json(force=True) or {}

    def go():
        name = wifi.add(d.get("ssid"), d.get("password"), d.get("security", ""))
        if d.get("switch"):
            wifi.switch(name)
        return {"ok": True, "name": name}
    return _wifi(go)


@app.post("/api/wifi/switch")
def wifi_switch():
    name = (request.get_json(force=True) or {}).get("name", "")

    def go():
        wifi.switch(name)
        return {"ok": True}
    return _wifi(go)


@app.post("/api/wifi/forget")
def wifi_forget():
    name = (request.get_json(force=True) or {}).get("name", "")

    def go():
        wifi.forget(name)
        return {"ok": True}
    return _wifi(go)


@app.get("/api/system")
def api_system():
    out = {}
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            out["cpu_temp_c"] = round(int(f.read().strip()) / 1000, 1)
    except Exception:
        out["cpu_temp_c"] = None
    try:
        with open("/proc/uptime") as f:
            out["uptime_secs"] = int(float(f.read().split()[0]))
    except Exception:
        out["uptime_secs"] = None
    return jsonify(out)


@app.get("/api/logs")
def api_logs():
    n = str(min(int(request.args.get("n", 200)), 2000))
    try:
        r = subprocess.run(["journalctl", "-u", f"{SERVICE}.service", "--no-pager", "-o", "short-iso", "-n", n],
                           capture_output=True, text=True, timeout=10)
        return jsonify({"lines": r.stdout.splitlines(), "error": None})
    except Exception as e:
        return jsonify({"lines": [], "error": str(e)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
