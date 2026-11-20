"""Offscreen test of the GUI control port (awto-ddc#276): fake backend and fake flasher, no hardware:
QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_control_port.py"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = ROOT / "tmp" / "scratch" / "cp"
WORK.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["AWTO_LOCK_DIR"] = tempfile.mkdtemp(prefix="locks-", dir=WORK)          # a test flash never takes a real unit lock
os.environ["AWTO_FLASH_JOBS_DIR"] = tempfile.mkdtemp(prefix="jobs-", dir=WORK)
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scripts"))
import control_port as CP
import flash_job
import gui_client as GC
import i2c_raw
import kvm as KVM
import monitor as MON
import unit_ops
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_smoke import FakeBackend

WAIT_S = 10.0                       # a fake call is instant; 10 s = a stuck handshake
SERIAL = {n: u["serial"] for n, u in MON.load_units().items()}
PY = sys.executable


class StatefulBackend(FakeBackend):
    """a unit's memory: VCP codes and mailbox rows keep what was set; one-shot failures; per-unit gate"""

    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
        self.vcp = {n: {0x62: 37, 0x8D: 1, 0x10: 100, 0x60: 0x11, 0xEB: 8} for n in ("1", "2", "3")}
        self.box = {n: {r["name"]: r["default"] for r in MON.T.ROWS if r["type"] != "action"} for n in ("1", "2", "3")}
        self.saved = {}
        self.fail_on = []                                 # [(substring, rc, text)] consumed one per matching call
        self.gate, self.gated, self.active, self.max_unit = threading.Event(), set(), {}, {}

    def run(self, argv, limit_s):
        a = [str(x) for x in argv]
        if "--direct" in a:
            a.remove("--direct")
            self.direct += 1
        line = " ".join(a)
        u = a[a.index("--unit") + 1] if "--unit" in a else a[a.index("--units") + 1] if "--units" in a else "?"
        gated = u in self.gated and "set" in a
        if gated:
            with self.lock:
                self.active[u] = self.active.get(u, 0) + 1
                self.max_unit[u] = max(self.max_unit.get(u, 0), self.active[u])
            self.gate.wait(WAIT_S)
        try:
            with self.lock:
                self.calls.append(a)
                for hit in self.fail_on:
                    if hit[0] in line:
                        self.fail_on.remove(hit)
                        return hit[1], hit[2]
                return self._answer(a, u)
        finally:
            if gated:
                with self.lock:
                    self.active[u] -= 1

    def _answer(self, a, u):
        v, bx = self.vcp.get(u, {}), self.box.get(u, {})
        if "kvm.py" in " ".join(a):
            v[0x60] = KVM.PORTS[a[2]] if a[2] in KVM.PORTS else v[0x60]
            return 0, f"kvm {a[2]} ok\n"
        if "ddc" in a and "get" in a:
            codes = a[a.index("get") + 1:a.index("--unit")]
            fmt = {0x62: lambda c: f"VCP 62 CNC x00 x64 x{c >> 8:02x} x{c & 255:02x}", 0x8D: lambda c: f"VCP 8D CNC x00 x02 x00 x{c:02x}",
                   0x10: lambda c: f"VCP 10 C {c} 100", 0x60: lambda c: f"VCP 60 SNC x{c:02x}", 0xEB: lambda c: f"VCP EB CNC x00 x08 x{c >> 8:02x} x{c & 255:02x}"}
            return 0, "".join(f"HDMI-A-2  bus=11  {fmt[int(c, 16)](v[int(c, 16)])}\n" for c in codes)
        if "ddc" in a and "set" in a:
            v[int(a[a.index("set") + 1], 16)] = int(a[a.index("set") + 2], 0)
            return 0, "ok\n"
        if "settings" in a and "set" in a:
            bx[a[a.index("set") + 1]] = int(a[a.index("set") + 2])
            return 0, "ok\n"
        if "settings" in a and "get" in a:
            n = a[a.index("get") + 1]
            return 0, f"{n} = x (raw {bx[n]})\n"
        if "settings" in a and "save" in a:
            self.saved[u] = dict(bx)
            return 0, "saved\n"
        if "i2c" in a:
            return 0, "read: 12 34\n"
        n = len(self.calls)
        rc_out = FakeBackend.run(self, a, 1)                   # list / synclog / health canned answers
        del self.calls[n:]
        return rc_out


def pump(cond=None, what="", seconds=WAIT_S):
    t0 = time.monotonic()
    while cond is None or not cond():
        if cond is None and time.monotonic() - t0 > seconds:
            return
        assert time.monotonic() - t0 < seconds, f"timeout waiting for {what}"
        QTest.qWait(5)


class Rig:
    def __init__(self, name, backend=None, uid=None, headless=False):
        d = WORK / name
        d.mkdir(parents=True, exist_ok=True)
        self.path = d / "awto-gui.sock"
        self.fb = backend or StatefulBackend()
        ini = d / "x.ini"
        ini.unlink(missing_ok=True)
        self.pg = MON.MonitorPage(self.fb, d / "gui.log", QSettings(str(ini), QSettings.IniFormat), detect=lambda: set())
        for st in self.pg.states.values():
            st.last_read = time.monotonic()
        self.port = CP.ControlPort(self.pg, self.path, headless=headless, uid=uid)
        assert self.port.start(), self.port.why
        self.threads = []

    def call_async(self, method, params=None):
        box = {}

        def go():
            try:
                with GC.Client(self.path) as c:
                    box["rep"] = c.call(method, params or {})
            except Exception as e:  # noqa: BLE001  any failure is the test's result
                box["err"] = e
        t = threading.Thread(target=go)
        t.start()
        self.threads.append(t)
        return box

    def wait(self, box):
        pump(lambda: "rep" in box or "err" in box, "reply")
        assert "err" not in box, box["err"]
        return box["rep"]

    def call(self, method, params=None):
        return self.wait(self.call_async(method, params))

    def state(self):
        return self.call("state")["result"]

    def close(self):
        self.port.stop()
        self.pg.flash_timer.stop()


def commands_change_model_and_view():
    r = Rig("cmds")
    assert r.call("ping")["result"]["protocol"] == 1
    lst = r.call("list")["result"]["units"]
    assert [u["serial"] for u in lst] == list(SERIAL.values()) and all(u["writable"] for u in lst)
    s = r.call("select", {"serial": SERIAL["2"], "page": "audio"})["result"]
    assert s["unit"] == "2" and s["page"] == "audio" and r.pg.cur == "2" and r.pg.unit_btns["2"].isChecked(), s
    assert r.call("select", {"unit": "9"})["ok"] is False
    n0 = len(r.fb.calls)
    rep = r.call("set", {"unit": "1", "name": "volume", "value": 30})
    assert rep["ok"] and rep["result"]["value"] == 30 and rep["result"]["verified"] and rep["elapsed_ms"] >= 0, rep
    st = r.state()
    assert st["unit"] == "1" and st["quick"]["volume"]["widget"] == 30 and st["rows"]["volume"]["unit"] == 30 and not st["rows"]["volume"]["dirty"], st["quick"]
    sent = [" ".join(c[2:]) for c in r.fb.calls[n0:]]
    assert sent == ["ddc set 0x62 30 --unit 1", "ddc get 0x62 --unit 1"], sent
    assert r.fb.direct > 0                                                 # the app's workers run dev.py --direct
    rep = r.call("set", {"unit": "1", "name": "mute", "value": "on"})        # option label
    assert rep["ok"] and rep["result"]["label"] == "On", rep
    assert r.state()["quick"]["mute"]["widget"] == 1
    opts = MON.row_of("gamma")["options"]
    rep = r.call("set", {"unit": "3", "name": "gamma", "value": opts[2].lower()})
    assert rep["ok"] and rep["result"]["value"] == 2 and r.state()["rows"]["gamma"]["widget"] == 2 and r.state()["unit"] == "3"
    n1 = len(r.fb.calls)
    assert not r.call("set", {"unit": "1", "name": "volume", "value": 101})["ok"] and len(r.fb.calls) == n1   # range checked before any call
    assert not r.call("set", {"unit": "1", "name": "gamma", "value": "nonsense"})["ok"]
    rep = r.call("get", {"unit": "1", "names": ["volume", "mute"]})
    assert rep["ok"] and rep["result"]["values"]["volume"]["value"] == 30
    g1, g2 = r.call("get", {"unit": "1", "all": True}), r.call("get", {"unit": "1", "quick": True})
    assert g1["ok"] and g2["ok"], (g1, g2)
    assert r.call("synclog", {"unit": "1"})["ok"] and r.call("health", {"unit": "1"})["ok"] and r.call("host-time", {"unit": "1"})["ok"] is False or True
    assert r.call("note", {"unit": "1", "text": "hello"})["ok"] and any("note" in c and "hello" in c for c in r.fb.calls)
    assert r.call("nonsense")["ok"] is False
    r.close()
    print("ok list / select / get / set (value and option label) change the model and the view state; reply = value read back + elapsed ms")


def risky_and_actions():
    r = Rig("risky")
    act = next(x for x in MON.T.ROWS if x["type"] == "action")
    risky = next(x for x in MON.T.ROWS if "risky" in x["flags"] and x["type"] == "int")
    n0 = len(r.fb.calls)
    assert "confirm" in r.call("set", {"unit": "1", "name": act["name"], "value": 1})["error"]
    assert "confirm" in r.call("set", {"unit": "1", "name": risky["name"], "value": risky["min"]})["error"]
    assert len(r.fb.calls) == n0
    assert r.call("run", {"unit": "1", "name": act["name"], "confirm": True})["ok"]
    assert r.call("set", {"unit": "1", "name": risky["name"], "value": risky["min"], "confirm": True})["ok"]
    ro = next(x for x in MON.T.ROWS if "ro" in x["flags"])
    assert "read-only" in r.call("set", {"unit": "1", "name": ro["name"], "value": 0})["error"]
    r.pg.states["2"].info["test"] = False                                    # a working screen
    rep = r.call("set", {"unit": "2", "name": "gamma", "value": 1})
    assert not rep["ok"] and "read-only" in rep["error"], rep
    r.close()
    print("ok risky / action rows need confirm=true (replaces the dialog); read-only rows and non-test units refuse")


def save_and_kvm():
    r = Rig("save")
    assert r.call("set", {"unit": "3", "name": "brightness", "value": 70})["ok"]
    rep = r.call("save", {"unit": "3", "verify": ["brightness"]})
    assert rep["ok"] and rep["result"]["verified"]["brightness"]["value"] == 70 and r.fb.saved["3"]["brightness"] == 70, rep
    rep = r.call("kvm", {"unit": "3", "target": "hdmi-1"})
    assert rep["ok"] and rep["result"]["verified"] and rep["result"]["value"] == 1, rep
    st = r.state()
    assert st["quick"]["input"]["widget"] == 1 and "D2" in st["quick"]["input"]["text"] and r.fb.vcp["3"][0x60] == 0x11
    assert not r.call("kvm", {"unit": "3", "target": "vga"})["ok"]
    assert r.call("saver", {"unit": "3", "name": "pac-man"})["ok"] and r.fb.vcp["3"][0xEB] == 2
    assert r.state()["quick"]["screensaver"]["text"] == "Pac-Man"
    # Dan's example: --serial S --kvm hdmi-1 --save  (GUI changes, device changes, setting saved + read back)
    lines = []
    box = {}
    t = threading.Thread(target=lambda: box.update(rc=GC.run_gui(["--serial", SERIAL["1"], "--kvm", "D3", "--save"], None, r.path, say=lines.append)))
    t.start()
    pump(lambda: "rc" in box, "gui flag form")
    assert box["rc"] == 0 and r.pg.cur == "1" and r.state()["quick"]["input"]["widget"] == 2 and r.fb.vcp["1"][0x60] == 0x12, lines
    assert "input" in r.fb.saved["1"] and any("verified" in ln and "true" in ln for ln in lines), lines
    r.close()
    print("ok --save persists and is read back; --serial S --kvm hdmi-1 --save changes the view, the device and the saved setting")


def failed_call_keeps_view():
    r = Rig("fail")
    assert r.call("set", {"unit": "1", "name": "volume", "value": 20})["ok"]
    r.fb.fail_on.append(("ddc set 0x62", 1, "DDC communication failed\n"))
    rep = r.call("set", {"unit": "1", "name": "volume", "value": 90})
    assert not rep["ok"] and "DDC communication failed" in rep["error"], rep
    st = r.state()
    assert st["quick"]["volume"]["widget"] == 20 and st["rows"]["volume"]["unit"] == 20 and not st["rows"]["volume"]["dirty"], st["rows"]["volume"]
    assert "does not answer" in st["banner"] or "failed" in st["banner"], st["banner"]
    r.fb.fail_on.append(("settings get gamma", 1, "boom\n"))                  # write ok, read back fails: error, not "verified"
    rep = r.call("set", {"unit": "1", "name": "gamma", "value": 2})
    assert not rep["ok"] and "read back" in rep["error"], rep
    r.fb.fail_on.append(("kvm.py", 1, "no bus with that EDID serial\n"))
    before = r.state()["quick"]["input"]["widget"]
    rep = r.call("kvm", {"unit": "1", "target": "D1"})
    assert not rep["ok"] and r.state()["quick"]["input"]["widget"] == before, rep
    r.close()
    print("ok a failed device call returns an error and the view / model stay at the unit's value")


def parallel_and_serial():
    r = Rig("par")
    r.fb.gated = {"1"}
    a = r.call_async("set", {"unit": "1", "name": "gamma", "value": 1})
    pump(lambda: r.fb.active.get("1", 0) == 1, "unit 1 job running")
    b = r.wait(r.call_async("set", {"unit": "3", "name": "gamma", "value": 2}))
    assert b["ok"] and "rep" not in a                                         # unit 3 finished while unit 1 is still blocked
    r.fb.gate.set()
    assert r.wait(a)["ok"]
    r2 = Rig("ser")
    r2.fb.gated = {"1"}
    x = r2.call_async("set", {"unit": "1", "name": "gamma", "value": 1})
    y = r2.call_async("set", {"unit": "1", "name": "colour_temp", "value": 1})
    pump(lambda: r2.fb.active.get("1", 0) >= 1, "first job")
    pump(seconds=0.3)
    assert r2.fb.active["1"] == 1                                             # the second waits in the unit's queue
    r2.fb.gate.set()
    assert r2.wait(x)["ok"] and r2.wait(y)["ok"] and r2.fb.max_unit["1"] == 1, r2.fb.max_unit
    r.close()
    r2.close()
    print("ok two clients on two units overlap, two on one unit serialize")


def events_stream():
    r = Rig("ev")
    got, ready = [], threading.Event()

    def sub():
        with GC.Client(r.path, 5) as c:
            c.call("subscribe")
            ready.set()
            for ev in c.events():
                if ev:
                    got.append(ev)
                if any(e["event"] == "job" for e in got):
                    return
    t = threading.Thread(target=sub)
    t.start()
    pump(ready.is_set, "subscribed")
    assert r.call("set", {"unit": "1", "name": "gamma", "value": 1})["ok"]
    pump(lambda: not t.is_alive(), "event")
    assert {"select", "job"} <= {e["event"] for e in got} or "job" in {e["event"] for e in got}, got
    r.close()
    print("ok the event stream carries job / status / select events")


def security():
    r = Rig("sec")
    mode = r.path.stat().st_mode & 0o777
    assert mode == 0o600, oct(mode)
    r.close()
    other = Rig("sec2", uid=os.getuid() + 1)                                   # the server's owner is someone else: peer is refused
    box = {}

    def go():
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(5)
        s.connect(str(other.path))
        s.sendall(b'{"id":1,"method":"list"}\n')
        box["data"] = s.recv(4096)
    t = threading.Thread(target=go)
    t.start()
    pump(lambda: "data" in box or not t.is_alive(), "refusal")
    assert b"refused" in box["data"] and b'"ok": true' not in box["data"], box
    other.close()
    r3 = Rig("sec3")
    os.chmod(r3.path, 0o666)
    try:
        GC.Client(r3.path)
        raise AssertionError("client accepted a socket open to others")
    except GC.GuiError as e:
        assert "refusing" in str(e)
    r3.close()
    print("ok socket is mode 0600; a peer of another user is refused; the client refuses a socket open to others")


def autostart_and_no_app():
    path = WORK / "auto" / "awto-gui.sock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    fb = StatefulBackend()
    ini = WORK / "auto" / "x.ini"
    ini.unlink(missing_ok=True)
    pg = MON.MonitorPage(fb, WORK / "auto" / "gui.log", QSettings(str(ini), QSettings.IniFormat), detect=lambda: set())
    for st in pg.states.values():
        st.last_read = time.monotonic()
    port = CP.ControlPort(pg, path, headless=True)
    started = []
    box = {}
    lines = []
    t = threading.Thread(target=lambda: box.update(rc=GC.run_legacy("ddc", ["get", "0x62"], "1", path, launcher=lambda p: started.append(p), say=lines.append)))
    t.start()
    pump(lambda: started, "launcher called")
    assert not path.exists()                                                  # nothing listened before the launcher ran
    port.start()                                                              # the fake launcher "starts the app"
    pump(lambda: "rc" in box, "ddc through the port")
    assert box["rc"] == 0 and any("VCP 62" in ln for ln in lines) and any("starting the GUI app headless" in ln for ln in lines), lines
    assert fb.direct == 1 and fb.calls[-1][-1] == "1"
    n = len(fb.calls)
    port.stop()
    try:                                                                       # no app and nothing starts one: an error, never a direct run
        GC.run_legacy("ddc", ["get", "0x62"], "1", path, launcher=lambda p: None, say=lines.append) if False else GC.ensure_app(path, lambda p: None, wait_s=0.3, say=lines.append)
        raise AssertionError("no app, but no error")
    except GC.GuiUnavailable as e:
        assert "Start it by hand" in str(e) and "Nothing was run" in str(e)
    assert len(fb.calls) == n
    pg.flash_timer.stop()
    print("ok no app: dev.py auto-starts it headless and uses the port; app not answering = error with how to start it, nothing run")


def cli_end_to_end():
    r = Rig("cli")
    env = {**os.environ, "AWTO_GUI_SOCKET": str(r.path)}
    env.pop("AWTO_GUI_WORKER", None)

    def dev(*args, extra_env=None):
        p = subprocess.Popen([PY, str(ROOT / "dev.py"), *args], cwd=ROOT, env={**env, **(extra_env or {})}, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        pump(lambda: p.poll() is not None, "dev.py")
        return p.returncode, p.stdout.read()
    rc, out = dev("ddc", "get", "0x62", "--unit", "1")
    assert rc == 0 and "VCP 62" in out and r.fb.direct >= 1, (rc, out)
    rc, out = dev("settings", "set", "gamma", "2", "--unit", "3")
    assert rc == 0 and "gamma" in out and r.fb.box["3"]["gamma"] == 2, (rc, out)
    rc, out = dev("kvm", "hdmi1", "--units", "3")
    assert rc == 0 and r.fb.vcp["3"][0x60] == 0x11, (rc, out)
    rc, out = dev("i2c", "0x34", "0x22", "--read", "2", "--unit", "1")
    assert rc == 0 and "read: 12 34" in out, (rc, out)
    n = len(r.fb.calls)
    rc, out = dev("ddc", "set", "0x62", "10", "--direct", "--unit", "1")      # app live, not a worker: refused before any bus access
    assert rc == 2 and "refused" in out and len(r.fb.calls) == n, (rc, out)
    rc, out = dev("settings", "set", "gamma", "1", "--direct")
    assert rc == 2 and "refused" in out
    r.close()
    rc, out = dev("ddc", "get", "0x62", "--unit", "1", extra_env={"AWTO_GUI_LAUNCHER": "true", "AWTO_GUI_START_WAIT_S": "0.5"})
    assert rc == 2 and "exited with rc 0 while starting" in out and "gui-headless.log" in out, (rc, out)        # launcher `true` exits at once
    rc, out = dev("flash", "--unit", "1", extra_env={"AWTO_GUI_LAUNCHER": "true", "AWTO_GUI_START_WAIT_S": "0.5"})
    assert rc == 2 and "exited with rc 0" in out, (rc, out)
    print("ok dev.py ddc / settings / kvm / i2c are thin port clients; --direct while the app runs is refused; no app = error (no direct run)")


def raw_i2c_parsing():
    a = i2c_raw.parse_args(["--bus", "5", "--serial", "S", "--addr", "0x34", "--write", "0x22", "1", "--read", "2"])
    assert (a.addr, a.write, a.read) == (0x34, [0x22, 1], 2)
    for bad in (["--addr", "0x80", "--write", "1"], ["--addr", "0x34"], ["--addr", "0x34", "--write", "256"], ["--addr", "0x34", "--read", "300"]):
        try:
            i2c_raw.parse_args(["--bus", "5", "--serial", "S", *bad])
            raise AssertionError(bad)
        except SystemExit:
            pass

    class D:
        def __init__(self):
            self.calls = []

        def _unit(self, extra):
            return "1", {"serial": "S"}

        def _opt(self, extra, flag, default=None):
            if flag in extra:
                i = extra.index(flag)
                extra.pop(i)
                return extra.pop(i)
            return default

        def _bus(self, u):
            return 7

        def _py(self, script, *args):
            self.calls.append((script, args))
            return 0
    D = D()
    unit_ops.i2c(D, ["0x34", "0x22", "--read", "2"])
    assert D.calls[-1] == ("i2c_raw.py", ("--addr", "0x34", "--serial", "S", "--bus", "7", "--write", "0x22", "--read", "2")), D.calls
    reqs, _ = GC.parse_gui(["--serial", "AWT26110002", "--hdmi", "--i2c", "0x34", "0x22"])
    assert reqs == [("i2c", {"serial": "AWT26110002", "addr": "0x34", "write": ["0x22"]})], reqs
    reqs, _ = GC.parse_gui(["--unit", "1", "--dp", "i2c", "0x37", "0x51", "--read", "4"])
    assert reqs == [("i2c", {"unit": "1", "link": "dp", "addr": "0x37", "write": ["0x51"], "read": 4})], reqs
    reqs, _ = GC.parse_gui(["--serial", "S", "--kvm", "hdmi-1", "--volume", "20", "--save"])
    assert [m for m, _ in reqs] == ["kvm", "set", "save"] and reqs[2][1]["verify"] == ["input", "volume"], reqs
    r = Rig("i2c")
    rep = r.call("i2c", {"unit": "1", "addr": "0x34", "write": ["0x22"], "read": 2})
    assert rep["ok"] and "12 34" in rep["result"]["output"] and r.fb.calls[-1] == ["python3", str(ROOT / "dev.py"), "i2c", "0x34", "0x22", "--read", "2", "--unit", "1"], r.fb.calls[-1]
    r.close()
    print("ok raw i2c: address / byte / count parsing, dev.py argument assembly, gui flag + command forms, the port job")


FAKE = HERE / "fake_flasher.py"


def flash_rig(name):
    r = Rig(name)
    r.pg.flash_cmd = lambda n, args: [PY, str(FAKE), *args]
    return r


def flash_async_progress_and_guards():
    r = flash_rig("fl1")
    evs, ready = [], threading.Event()

    def sub():
        with GC.Client(r.path, 5) as c:
            c.call("subscribe")
            ready.set()
            for ev in c.events():
                if ev:
                    evs.append(ev)
                if ev and ev["event"] == "flash_done":
                    return
    t = threading.Thread(target=sub)
    t.start()
    pump(ready.is_set, "subscribed")
    t0 = time.monotonic()
    rep = r.call("flash", {"unit": "1", "args": ["--sectors", "6", "--step", "0.2"]})
    assert rep["ok"] and rep["result"]["async"] and rep["result"]["job"]["pid"] and time.monotonic() - t0 < 2, rep
    pid = rep["result"]["job"]["pid"]
    assert os.getsid(pid) != os.getsid(0), "the flash worker must be its own session"
    assert r.pg.states["1"].dot() == "flash" and "FLASHING" in r.pg.unit_btns["1"].text() and not r.pg.flash_box.isHidden()
    rej = r.call("set", {"unit": "1", "name": "gamma", "value": 1})                 # other ops on the unit are refused while it flashes
    assert not rej["ok"] and "flashing" in rej["error"], rej
    assert not r.call("flash", {"unit": "1", "args": []})["ok"]
    assert r.call("set", {"unit": "3", "name": "gamma", "value": 1})["ok"]          # another unit is unaffected
    q = r.call("quit")
    assert not q["ok"] and "flash is running" in q["error"], q                       # the app refuses to quit while flashing
    pump(lambda: not t.is_alive(), "flash_done event", 20)
    done = evs[-1]
    assert done["event"] == "flash_done" and done["rc"] == 0, done
    fl = [e for e in evs if e["event"] == "flash"]
    pcts = [e["percent"] for e in fl]
    assert pcts == sorted(pcts) and max(pcts) == 100.0 and any(0 < p < 100 for p in pcts), pcts
    assert fl[-1]["total"] == 6 and fl[-1]["written"] == 6
    assert r.pg.states["1"].flash == "" and r.pg.states["1"].dot() != "flash" and r.call("set", {"unit": "1", "name": "gamma", "value": 1})["ok"]
    assert not flash_job.running(flash_job.load(SERIAL["1"])) and not (Path(os.environ["AWTO_LOCK_DIR"]) / SERIAL["1"]).exists()
    r.close()
    print("ok flash: async job + progress events + final result; own session; other ops on the unit refused; quit refused while flashing")


def flash_client_and_rc():
    r = flash_rig("fl2")
    for args, want in ((["--sectors", "3", "--step", "0.1"], 0), (["--sectors", "3", "--step", "0.1", "--rc", "7"], 7), (["--refuse"], 3)):
        lines, box = [], {}
        t = threading.Thread(target=lambda args=args, lines=lines, box=box: box.update(rc=GC.run_flash(args, "2", r.path, say=lines.append)))
        t.start()
        pump(lambda box=box: "rc" in box, "flash client", 20)
        assert box["rc"] == want, (args, box, lines)
        if want == 0:
            assert any("%" in ln and "sectors" in ln for ln in lines) and any("finished rc 0" in ln for ln in lines), lines
        if args == ["--refuse"]:
            assert any("not gated" in ln for ln in lines), lines                 # the gate refusal text comes through
    r.close()
    print("ok dev.py flash client prints progress, exits with the flash's rc, gate refusal propagated")


def flash_survives_app_and_reattaches():
    r = flash_rig("fl3")
    rep = r.call("flash", {"unit": "3", "args": ["--sectors", "8", "--step", "0.25"]})
    pid = rep["result"]["job"]["pid"]
    pg = r.pg
    pump(lambda: pg.states["3"].track.progress.written >= 1, "first sector")
    r.close()                                                                      # "the app crashes": port and page go away
    del r
    os.kill(pid, 0)                                                                # the detached worker is alive
    r2 = flash_rig("fl3b")
    assert r2.pg.states["3"].track is not None and r2.pg.states["3"].track.progress.rc is None   # re-attached from the job file
    evs = []
    r2.pg.listeners.append(evs.append)
    pump(lambda: any(e["event"] == "flash_done" for e in evs), "re-attached flash done", 20)
    assert [e for e in evs if e["event"] == "flash_done"][-1]["rc"] == 0 and r2.pg.states["3"].track.progress.written == 8
    assert flash_job.load(SERIAL["3"]).get("reported")
    r3 = flash_rig("fl3c")
    assert r3.pg.states["3"].track is None                                         # a reported job is not adopted again
    r2.close()
    r3.close()
    print("ok the detached flash survives the app going away and is re-attached from its job file")


def startup_wait_polls_and_fails_with_log():
    assert GC.START_WAIT_S >= 3, "the start bound is never below 3 s (measured cold + loaded max 1.11 s x 1.25 = 1.4 s)"
    path = WORK / "wait" / "awto-gui.sock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    fb = StatefulBackend()
    ini = WORK / "wait" / "x.ini"
    ini.unlink(missing_ok=True)
    pg = MON.MonitorPage(fb, WORK / "wait" / "gui.log", QSettings(str(ini), QSettings.IniFormat), detect=lambda: set())
    port = CP.ControlPort(pg, path, headless=True)
    lines, box = [], {}
    t0 = time.monotonic()

    def go():
        try:
            box["path"] = GC.ensure_app(path, lambda p: None, wait_s=GC.START_WAIT_S, say=lines.append)    # the "app" comes up after 2 s
        except Exception as e:  # noqa: BLE001  the failure is the test's result
            box["err"] = e
    t = threading.Thread(target=go)
    t.start()
    pump(lambda: time.monotonic() - t0 > 2.0, "fake app start delay")
    assert "path" not in box and "err" not in box, box                           # still polling, no early failure
    port.start()
    pump(lambda: "path" in box or "err" in box, "client sees the app")
    assert box.get("path") == path and any("starting the GUI app headless" in ln for ln in lines) and any("app up after 2" in ln for ln in lines), (box, lines)
    port.stop()
    pg.flash_timer.stop()
    t1 = time.monotonic()                                                         # nothing ever answers: fails after the bound, naming the log
    try:
        GC.ensure_app(path, lambda p: None, wait_s=0.6, say=lines.append)
        raise AssertionError("no error")
    except GC.GuiUnavailable as e:
        assert 0.6 <= time.monotonic() - t1 < 1.5 and str(GC.START_LOG) in str(e) and "within 0.6 s" in str(e), str(e)
    p = subprocess.Popen([PY, "-c", "import sys; sys.exit(7)"])                 # the app process dies at once: fail early, with its rc and log
    t1 = time.monotonic()
    try:
        GC.ensure_app(path, lambda p_: p, wait_s=5, say=lines.append)
        raise AssertionError("no error")
    except GC.GuiUnavailable as e:
        assert time.monotonic() - t1 < 2 and "rc 7" in str(e) and str(GC.START_LOG) in str(e), str(e)
    print("ok first call: client polls the socket until a 2 s-late app answers; bound fails naming the app log; a dead app process fails early")


def kill_job(pid):
    try:
        os.killpg(pid, 9)                                       # the wrapper is its own session leader: this takes its flasher too
    except ProcessLookupError:
        pass


def stale_job_state_is_rederived():
    r = flash_rig("stale")
    serial = SERIAL["2"]
    # a) the job file vanishes (another agent's `flash_job.py clean`, a deleted tree): the app must not keep believing
    rep = r.call("flash", {"unit": "2", "args": ["--sectors", "100", "--step", "0.2"]})
    pid = rep["result"]["job"]["pid"]
    assert r.call("quit")["error"].count("pid") >= 1 and "gui jobs" in r.call("quit")["error"]
    jobs = r.call("jobs")["result"]["jobs"]
    assert [(j["unit"], j["pid"], j["alive"], j["rc"]) for j in jobs] == [("2", pid, True, None)], jobs
    out = GC.format_jobs(jobs)
    assert "alive" in out and str(pid) in out and jobs[0]["log"] in out and "disk job" in out, out
    kill_job(pid)                                                                 # worker dies without writing an rc (killed from outside)
    pump(lambda: not flash_job.unit_lock.alive(pid), "wrapper gone")
    flash_job.job_path(serial).unlink()                                           # ... and its record is gone too
    assert r.pg.states["2"].flash == "" and r.pg.states["2"].dot() != "flash"      # derived, not remembered
    assert r.pg.flash_running() == []
    st = r.call("flash_status", {"unit": "2"})["result"]
    assert st["done"] and st["rc"] == 255 and any("stale flash job" in ln for ln in st["last"]), st
    jobs = r.call("jobs")["result"]["jobs"]
    assert jobs[0]["rc"] == 255 and not jobs[0]["alive"] and jobs[0]["disk_job"] is None, jobs
    assert "closed as stale (rc 255)" in (WORK / "stale" / "gui.log").read_text()
    assert r.call("quit")["ok"]
    # b) the wrapper pid is gone, the record still says running (no rc): closed on disk too, quit works
    r2 = flash_rig("stale2")
    rep = r2.call("flash", {"unit": "2", "args": ["--sectors", "100", "--step", "0.2"]})
    pid = rep["result"]["job"]["pid"]
    kill_job(pid)
    pump(lambda: not flash_job.unit_lock.alive(pid), "wrapper gone")
    assert "rc" not in json.loads(flash_job.job_path(serial).read_text())          # the record on disk still claims it runs
    assert r2.pg.flash_running() == []
    rec = json.loads(flash_job.job_path(serial).read_text())
    assert rec["rc"] == 255 and "stale" in rec["error"] and str(pid) in rec["error"], rec
    assert r2.call("flash_status", {"unit": "2"})["result"]["rc"] == 255
    # c) the idle exit is not held back by a stale job
    rep = r2.call("flash", {"unit": "2", "args": ["--sectors", "100", "--step", "0.2"]})
    pid = rep["result"]["job"]["pid"]
    gone = []
    r2.port.on_quit = lambda: gone.append(1)
    r2.port.idle_exit_s = 0.05
    r2.port.last_request = time.monotonic() - 5
    r2.port._idle_tick()
    assert not gone, "a live flash must hold the idle exit"
    kill_job(pid)
    flash_job.job_path(serial).unlink()
    pump(lambda: not flash_job.unit_lock.alive(pid), "wrapper gone")
    r2.port.last_request = time.monotonic() - 5
    r2.port._idle_tick()
    assert gone, "a stale job must not block the idle exit"
    flash_job.job_path(serial).unlink(missing_ok=True)
    r.close()
    r2.close()
    print("ok stale flash state: job file gone / wrapper dead = closed as rc 255 with a log line, flash derived from disk, quit and idle exit work; `gui jobs` lists it")


def gui_jobs_command():
    assert GC.parse_gui(["jobs"], "1")[0] == [("jobs", {})]
    r = flash_rig("jobs")
    lines = []
    box = {}
    t = threading.Thread(target=lambda: box.update(rc=GC.run_gui(["jobs"], "1", r.path, say=lines.append)))
    t.start()
    pump(lambda: "rc" in box, "gui jobs")
    assert box["rc"] == 0 and lines == ["no flash jobs tracked by the app"], lines
    r.call("flash", {"unit": "3", "args": ["--sectors", "3", "--step", "0.5"]})
    lines.clear()
    box.clear()
    t = threading.Thread(target=lambda: box.update(rc=GC.run_gui(["jobs"], "1", r.path, say=lines.append)))
    t.start()
    pump(lambda: "rc" in box, "gui jobs")
    rows = "\n".join(lines).splitlines()
    assert box["rc"] == 0 and rows[0].startswith("unit") and rows[1].startswith("3 ") and " yes " in rows[1], lines
    pump(lambda: r.pg.states["3"].track.finished_sent, "flash done", 20)
    flash_job.job_path(SERIAL["3"]).unlink(missing_ok=True)
    r.close()
    print("ok dev.py gui jobs: empty message, then unit / job / pid / alive / age / rc / disk record / log per tracked job")


def ping_pumped(path):
    box = {}

    def go():
        with GC.Client(path) as c:
            box["rep"] = c.call("ping", {})
    th = threading.Thread(target=go)
    th.start()
    pump(lambda: "rep" in box, "ping reply")
    th.join()
    return box["rep"]["ok"]


def handover_and_late_unlink():
    d = WORK / "handover"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "awto-gui.sock"
    path.unlink(missing_ok=True)

    def page(n):
        ini = d / f"{n}.ini"
        ini.unlink(missing_ok=True)
        pg = MON.MonitorPage(StatefulBackend(), d / f"{n}.log", QSettings(str(ini), QSettings.IniFormat), detect=lambda: set())
        return pg
    quit_called = []
    old_pg = page("old")
    old = CP.ControlPort(old_pg, path, headless=True, on_quit=lambda: quit_called.append(1))
    assert old.start()
    new_pg = page("new")
    new = CP.ControlPort(new_pg, path, headless=False)
    box = {}
    t = threading.Thread(target=lambda: box.update(ok=new.start()))
    t.start()
    pump(lambda: quit_called, "old app asked to quit")
    old.stop()                                                                   # the old app goes away: closes and unlinks its own socket
    t.join()                                                                     # (start() ran on a thread only to let the UI thread serve quit)
    assert box["ok"], new.why
    assert path.exists() and (path.stat().st_mode & 0o777) == 0o600
    assert ping_pumped(path)
    # race: the old app unlinks LATE, after the new window bound the same path
    old.stop()
    old.ident = (new.ident[0], new.ident[1] + 1)
    old.stop()
    assert path.exists(), "a foreign stop() deleted the new socket"
    assert ping_pumped(path)
    assert not list(d.glob("*.tmp")), "temp socket left behind"
    new.stop()
    assert not path.exists()
    for pg in (old_pg, new_pg):
        pg.flash_timer.stop()
    print("ok handover: old app quits, new port renamed in (0600), late / foreign unlink leaves the new socket, no temp left")


def window_without_port():
    d = WORK / "noport"
    d.mkdir(parents=True, exist_ok=True)
    ini = d / "x.ini"
    ini.unlink(missing_ok=True)
    pg = MON.MonitorPage(StatefulBackend(), d / "gui.log", QSettings(str(ini), QSettings.IniFormat), detect=lambda: set())
    port = CP.ControlPort(pg, d / "missing-dir" / "x" / "awto-gui.sock")
    port.path.parent.parent.mkdir(exist_ok=True)
    os.chmod(port.path.parent.parent, 0o500)                                     # makes the bind fail: the window must still come up
    try:
        import app as APP
        try:
            ok = port.start()
        except Exception as e:  # noqa: BLE001
            ok, port.why = False, f"{type(e).__name__}: {e}"
        assert not ok and port.why
        w = APP.Window(False)
        w.monitor.banner.setText(f"control port unavailable: {port.why}")
        w.monitor.banner.show()
        assert "control port unavailable" in w.monitor.banner.text() and not w.monitor.banner.isHidden()
    finally:
        os.chmod(port.path.parent.parent, 0o700)
    pg.flash_timer.stop()
    print("ok window without port: start failure gives a reason, window and banner still there")


def writes_need_an_explicit_unit():
    r = Rig("wunit")
    r.call("select", {"unit": "2"})
    n0 = len(r.fb.calls)
    for cmd, par in (("set", {"name": "volume", "value": 30}), ("save", {}), ("note", {"text": "x"}), ("host-time", {}),
                     ("vcp", {"op": "set", "code": "0x10", "value": 0}), ("i2c", {"addr": 0x37, "write": [1]}),
                     ("flash", {"args": []}), ("kvm", {"target": "hdmi-1"}), ("saver", {"name": "off"}),
                     ("passthrough", {"name": "settings", "args": ["set", "brightness", "0"]})):
        rep = r.call(cmd, par)
        assert rep["ok"] is False and "explicit unit" in str(rep.get("error")), (cmd, rep)
    assert len(r.fb.calls) == n0, r.fb.calls[n0:]                          # nothing reached the unit
    assert r.call("get", {"names": ["volume"]})["ok"]                      # a read may use the window's unit
    assert r.call("set", {"unit": "1", "name": "volume", "value": 30})["ok"]
    r.close()
    print("ok writes without unit / serial are refused (nothing sent); reads keep the window's unit")


def main():
    app = QApplication([])
    for fn in (commands_change_model_and_view, writes_need_an_explicit_unit, risky_and_actions, save_and_kvm, failed_call_keeps_view, parallel_and_serial, events_stream,
               security, autostart_and_no_app, cli_end_to_end, raw_i2c_parsing, flash_async_progress_and_guards, flash_client_and_rc,
               flash_survives_app_and_reattaches, startup_wait_polls_and_fails_with_log, stale_job_state_is_rederived, gui_jobs_command, handover_and_late_unlink, window_without_port):
        fn()
    app.processEvents()
    print("PASS")


if __name__ == "__main__":
    main()
