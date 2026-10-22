"""Web UI tests: Modules page, settings, Restart / Shut down and Wi-Fi.
The Restart, Shut down and Wi-Fi tests come from itsposttime (Modified for the office board)."""
import json
import unittest

import support  # noqa: F401  (stand-in panel library, paths)
from support import TempFiles

import config

try:
    import flask  # noqa: F401
except ImportError:
    raise unittest.SkipTest("Flask isn't installed on this computer")


class TestModulesPage(TempFiles):
    def setUp(self):
        super().setUp()
        self.c = self.web.app.test_client()

    def test_lists_every_module_in_order_with_its_form(self):
        mods = self.c.get("/api/modules").get_json()["modules"]
        ids = [m["id"] for m in mods]
        self.assertEqual(ids, ["clock", "stocks", "nyra", "mlb", "nfl", "demo", "paneltest"])
        pt = mods[-1]
        self.assertTrue(pt["built"] and pt["settings"]["enabled"])
        self.assertIn("message", [f["key"] for f in pt["fields"]])
        self.assertEqual((mods[2]["id"], mods[2]["built"], mods[2]["step"]), ("nyra", False, 5))

    def test_toggle_reorder_and_settings_save(self):
        r = self.c.post("/api/modules", json={"settings": {"paneltest": {"enabled": False}}}).get_json()
        self.assertTrue(r["ok"])
        self.assertFalse(r["modules"][-1]["settings"]["enabled"])
        self.c.post("/api/modules", json={"order": ["paneltest", "clock"]})
        self.c.post("/api/modules", json={"settings": {"paneltest": {"message": "HELLO", "seconds": 30}}})
        saved = config.load()["modules"]
        self.assertEqual(saved["order"][:2], ["paneltest", "clock"])
        self.assertEqual(len(saved["order"]), 7)
        self.assertEqual((saved["paneltest"]["message"], saved["paneltest"]["seconds"]), ("HELLO", 30))
        self.assertFalse(saved["paneltest"]["enabled"])             # earlier change kept

    def test_planned_module_stays_off(self):
        r = self.c.post("/api/modules", json={"settings": {"nfl": {"enabled": True}}}).get_json()
        self.assertFalse(next(m for m in r["modules"] if m["id"] == "nfl")["settings"]["enabled"])

    def test_pages_load(self):
        for url in ("/", "/modules", "/config", "/logs"):
            r = self.c.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertIn(b"Office Board", r.data)


class TestSettingsPage(TempFiles):
    def setUp(self):
        super().setUp()
        self.c = self.web.app.test_client()

    def test_display_settings_save_and_are_checked(self):
        self.c.post("/api/config", json={"config": {"display": {"brightness": 55, "fps": 999}}})
        d = self.c.get("/api/config").get_json()["config"]["display"]
        self.assertEqual((d["brightness"], d["fps"]), (55, 60))

    def test_secrets_are_masked_and_kept(self):
        self.c.post("/api/config", json={"secrets": {"some_key": "abcd1234efgh5678"}})
        shown = self.c.get("/api/config").get_json()["secrets"]["some_key"]
        self.assertEqual(shown, "abcd****5678")
        self.c.post("/api/config", json={"secrets": {"some_key": shown}})      # unchanged field sent back
        self.assertEqual(config.load_secrets()["some_key"], "abcd1234efgh5678")

    def test_panel_picture(self):
        self.assertEqual(self.c.get("/board.png").status_code, 204)          # display not running yet
        from core.display import Display
        from rgbmatrix import RGBMatrix
        d = Display(matrix=RGBMatrix(), start_fetchers=False)
        d.step()
        d.write_status()
        r = self.c.get("/board.png")
        self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
        s = self.c.get("/api/status").get_json()["status"]
        self.assertEqual(s["module"], "clock")


class TestShutdownButton(unittest.TestCase):
    """Settings -> Shut down / Restart display: run only commands install.sh's sudoers rule allows,
    and never on this computer."""

    def _press(self, sudo_ok, url="/api/shutdown"):
        import subprocess
        import threading
        from web import app as web
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0 if sudo_ok else 1)

        class NowThread:                 # run the power-off step straight away instead of in the background
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                self.target()

        saved = web.subprocess.run, web.threading.Thread, web.time.sleep
        web.subprocess.run, web.threading.Thread, web.time.sleep = fake_run, NowThread, lambda s: None
        try:
            r = web.app.test_client().post(url)
        finally:
            web.subprocess.run, web.threading.Thread, web.time.sleep = saved
        self.assertIs(threading.Thread, saved[1])
        return r, calls

    def test_powers_off_when_allowed(self):
        r, calls = self._press(sudo_ok=True)
        self.assertEqual(r.get_json(), {"ok": True})
        self.assertEqual(calls, [["sudo", "-n", "-l", "systemctl", "poweroff"], ["sudo", "-n", "systemctl", "poweroff"]])

    def test_explains_when_not_allowed(self):
        r, calls = self._press(sudo_ok=False)
        self.assertEqual(r.status_code, 500)
        self.assertIn("bash install.sh", r.get_json()["error"])
        self.assertEqual(calls, [["sudo", "-n", "-l", "systemctl", "poweroff"]])

    def test_restart(self):
        r, calls = self._press(sudo_ok=True, url="/api/restart")
        self.assertEqual(r.get_json(), {"ok": True})
        self.assertEqual(calls[-1], ["sudo", "-n", "systemctl", "restart", "officeboard"])
        r, calls = self._press(sudo_ok=False, url="/api/restart")
        self.assertEqual((r.status_code, len(calls)), (500, 1))



class FakeNmcli:
    """Stands in for NetworkManager: on HomeNet (profile "preconfigured"), Mars saved, neighbors in range."""

    def __init__(self, fail_up=()):
        self.calls, self.fail_up, self.active = [], set(fail_up), "preconfigured"
        self.saved = {"preconfigured": "HomeNet", "Mars": "Mars"}

    def __call__(self, cmd, **kw):
        import subprocess
        args = cmd[3:]                                   # after "sudo -n nmcli"
        self.calls.append(args)
        out, code = "", 0
        if args[:3] == ["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION"]:
            out = f"wlan0:wifi:connected:{self.active}\nlo:loopback:connected (externally):lo\n"
        elif args[:3] == ["-t", "-f", "NAME,TYPE"]:
            out = "".join(n.replace(":", "\\:") + ":802-11-wireless\n" for n in self.saved) + "lo:loopback\n"
        elif args[:3] == ["-e", "no", "-g"]:
            out = self.saved[args[-1]] + "\n"
        elif args[:3] == ["-t", "-f", "IN-USE,SSID,SIGNAL"]:
            out = f"*:{self.saved[self.active]}:72\n :Neighbor\\:5G:40\n"
        elif args[:3] == ["-t", "-f", "SSID,SIGNAL,SECURITY"]:
            out = "HomeNet:72:WPA2\nNeighbor\\:5G:40:WPA2 WPA3\nNeighbor\\:5G:55:WPA2 WPA3\n:30:WPA2\nCafe:20:--\nLab:35:WPA3\n"
        elif "up" in args:
            name = args[-1]
            if name in self.fail_up:
                out, code = "Error: Connection activation failed: Secrets were required, but not provided", 4
            else:
                self.active = name
        elif args[:2] == ["connection", "delete"]:
            del self.saved[args[2]]
        elif args[:2] == ["connection", "add"]:
            self.saved[args[args.index("con-name") + 1]] = args[args.index("ssid") + 1]
        return subprocess.CompletedProcess(cmd, code, stdout=out if code == 0 else "", stderr=out if code else "")


class TestWifiSettings(unittest.TestCase):
    def setUp(self):
        from web import wifi
        self.wifi, self.nm = wifi, FakeNmcli()
        self._saved_run = wifi.subprocess.run
        wifi.subprocess.run = self.nm

    def tearDown(self):
        self.wifi.subprocess.run = self._saved_run

    def test_explains_missing_permission(self):
        import subprocess

        def needs_password(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="sudo: a password is required\n")
        self.wifi.subprocess.run = needs_password
        with self.assertRaisesRegex(self.wifi.WifiError, "bash install.sh"):
            self.wifi.status()

    def test_reads_nmcli_escapes(self):
        self.assertEqual(self.wifi._split("Neighbor\\:5G:40"), ["Neighbor:5G", "40"])

    def test_status(self):
        self.assertEqual(self.wifi.status(), {"available": True, "current": "HomeNet", "signal": 72, "saved": [
            {"name": "preconfigured", "ssid": "HomeNet", "active": True},
            {"name": "Mars", "ssid": "Mars", "active": False}]})

    def test_scan_one_entry_per_network_strongest_first(self):
        self.assertEqual(self.wifi.scan(), [
            {"ssid": "HomeNet", "signal": 72, "security": "WPA2"},
            {"ssid": "Neighbor:5G", "signal": 55, "security": "WPA2 WPA3"},
            {"ssid": "Lab", "signal": 35, "security": "WPA3"},
            {"ssid": "Cafe", "signal": 20, "security": ""}])

    def test_add_saves_without_switching(self):
        self.wifi.add("Neighbor:5G", "correct horse", "WPA2 WPA3")
        add = self.nm.calls[-1]
        self.assertEqual(add[:2], ["connection", "add"])
        self.assertEqual(add[add.index("wifi-sec.key-mgmt") + 1], "wpa-psk")
        self.wifi.add("Lab", "correct horse", "WPA3")             # WPA3-only
        self.assertIn("sae", self.nm.calls[-1])
        self.wifi.add("Cafe", "", "")                              # open network: no security settings
        self.assertNotIn("wifi-sec.psk", self.nm.calls[-1])
        self.assertFalse(any("up" in c for c in self.nm.calls))
        self.assertEqual(self.nm.active, "preconfigured")

    def test_add_updates_a_saved_network(self):
        self.wifi.add("HomeNet", "new password")
        self.assertEqual(self.nm.calls[-1][:3], ["connection", "modify", "preconfigured"])

    def test_rejects_bad_input(self):
        with self.assertRaises(self.wifi.WifiError):
            self.wifi.add("Cafe", "short")
        with self.assertRaises(self.wifi.WifiError):
            self.wifi.add("  ", "long enough")
        with self.assertRaises(self.wifi.WifiError):
            self.wifi.forget("preconfigured")                     # the network in use

    def test_switch(self):
        self.wifi.switch("Mars", background=False)
        self.assertEqual((self.nm.active, self.wifi.last_switch()["state"]), ("Mars", "ok"))

    def test_failed_switch_goes_back(self):
        self.nm.fail_up = {"Mars"}
        self.wifi.switch("Mars", background=False)
        s = self.wifi.last_switch()
        self.assertEqual((s["state"], s["previous"], self.nm.active), ("failed", "preconfigured", "preconfigured"))
        self.assertIn("Secrets were required", s["error"])

    def test_web_endpoints(self):
        from web import app as web
        c = web.app.test_client()
        self.assertEqual(c.get("/api/wifi").get_json()["current"], "HomeNet")
        self.assertEqual(c.post("/api/wifi/add", json={"ssid": "Cafe", "password": ""}).get_json(), {"ok": True, "name": "Cafe"})
        r = c.post("/api/wifi/forget", json={"name": "preconfigured"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("using right now", r.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
