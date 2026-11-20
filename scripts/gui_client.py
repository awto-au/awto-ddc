#!/usr/bin/env python3
"""Client of the monitor GUI's control port (awto-ddc#276, docs/monitor-gui.md "Control port"): connect, send, timeout, JSON.
dev.py's ddc / settings / kvm / synclog / note / i2c / flash commands and `dev.py gui` are thin wrappers around this module:
they never touch a bus themselves. No app answering = start it headless, wait START_WAIT_S, then fail with how to start it."""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
PROTOCOL = 1
ROUTED = ("ddc", "settings", "synclog", "note", "kvm", "i2c", "flash")
# Server side: one request waits for its chain of device calls (write + read back + save, each <= 5 s) plus queueing behind
# other units' serialised ddc calls (<= 2 x 5 s): worst ~25 s, x1.8 = 45 s. Expiry: error reply, the jobs finish in the app.
SERVER_LIMIT_S = 45
CLIENT_LIMIT_S = SERVER_LIMIT_S + 5      # the server always answers within its limit; +5 s = a reply in flight
PING_S = 2                               # a ping is answered on the UI thread's next turn (ms); 2 s = the UI thread is stuck
START_WAIT_S = float(os.environ.get("AWTO_GUI_START_WAIT_S", "5"))   # env: tests only. Headless start measured 0.3 s warm (2026-11-20); 5 s covers a cold PySide6 import
START_POLL_S = 0.1                       # poll pace of the socket while the app starts
FLASH_SILENCE_S = 60                     # flash client: no event for this long = a WARN line (the flash is never stopped by the client)
FLASH_STATUS_S = 5                       # flash client: cross-check the job state when no event arrived (events may be missed)


class GuiError(Exception):
    pass


class GuiUnavailable(GuiError):
    pass


class PortCannotCarry(GuiError):
    pass


def socket_path() -> Path:
    env = os.environ.get("AWTO_GUI_SOCKET")
    if env:
        return Path(env)
    run = os.environ.get("XDG_RUNTIME_DIR")
    return Path(run) / "awto-gui.sock" if run else ROOT / "tmp" / "run" / "awto-gui.sock"


def check_socket(path: Path) -> None:
    """refuse a socket that is not ours or is open to others (a planted socket would receive our commands)"""
    st = path.stat()
    if not stat.S_ISSOCK(st.st_mode):
        raise GuiError(f"{path} is not a socket")
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise GuiError(f"{path}: owner uid {st.st_uid} mode {stat.S_IMODE(st.st_mode):04o}; refusing (need our uid, mode 0600)")


class Client:
    def __init__(self, path: Path | None = None, timeout: float = CLIENT_LIMIT_S):
        self.path = Path(path or socket_path())
        self.timeout = timeout
        self.n = 0
        try:
            check_socket(self.path)
        except FileNotFoundError as e:
            raise GuiUnavailable(f"no control port at {self.path}") from e
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(timeout)
        try:
            self.s.connect(str(self.path))
        except OSError as e:
            self.s.close()
            raise GuiUnavailable(f"control port {self.path} does not answer: {e}") from e
        self.f = self.s.makefile("rwb")

    def close(self):
        try:
            self.f.close()
        finally:
            self.s.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def call(self, method: str, params: dict | None = None) -> dict:
        """one request, one reply: {"ok", "result" | "error", "elapsed_ms", ...}"""
        self.n += 1
        self.f.write(json.dumps({"id": self.n, "method": method, "params": params or {}}).encode() + b"\n")
        self.f.flush()
        try:
            line = self.f.readline()
        except TimeoutError as e:
            raise GuiError(f"{method}: no reply in {self.timeout} s") from e
        if not line:
            raise GuiError(f"{method}: the app closed the connection")
        return json.loads(line)

    def events(self):
        """after subscribe(): yields event dicts until the connection ends; None on a read timeout"""
        while True:
            try:
                line = self.f.readline()
            except TimeoutError:
                yield None
                continue
            if not line:
                return
            yield json.loads(line)


def try_call(path: Path, method: str, params: dict, timeout: float = PING_S) -> dict | None:
    try:
        with Client(path, timeout) as c:
            return c.call(method, params)
    except (GuiError, OSError, ValueError):
        return None


def app_live(path: Path | None = None) -> bool:
    r = try_call(Path(path or socket_path()), "ping", {})
    return bool(r and r.get("ok"))


def default_launcher(path: Path) -> None:
    """start the app headless and detached: run.py --headless (QT_QPA_PLATFORM=offscreen), output to tmp/logs/gui-headless.log"""
    hook = os.environ.get("AWTO_GUI_LAUNCHER")              # tests only: any command replaces the real app
    run_py = ROOT / "tools" / "osd_editor" / "run.py"
    cmd = hook.split() if hook else [sys.executable, str(run_py), "--headless"]
    logp = ROOT / "tmp" / "logs" / "gui-headless.log"
    logp.parent.mkdir(parents=True, exist_ok=True)
    with logp.open("a") as lf:
        subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True,
                         env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "AWTO_GUI_SOCKET": str(path)})


def ensure_app(path: Path | None = None, launcher=default_launcher, wait_s: float | None = None, say=print) -> Path:
    path = Path(path or socket_path())
    if app_live(path):
        return path
    wait = START_WAIT_S if wait_s is None else wait_s
    say(f"gui: no app answers on {path}; starting it headless (waiting up to {wait:g} s)")
    launcher(path)
    t0 = time.monotonic()
    while time.monotonic() - t0 < wait:
        if app_live(path):
            say(f"gui: app up after {time.monotonic() - t0:.1f} s")
            return path
        time.sleep(START_POLL_S)
    raise GuiUnavailable(
        f"gui: the app did not answer on {path} within {wait:g} s (log: tmp/logs/gui-headless.log). Nothing was run on the unit. "
        f"Start it by hand: python3 tools/osd_editor/run.py --headless (or without --headless for the window), then repeat.")


# --- legacy dev.py commands -> requests
def _take(extra: list[str], flag: str, default=None):
    if flag in extra:
        i = extra.index(flag)
        extra.pop(i)
        if i < len(extra) and not extra[i].startswith("--"):
            return extra.pop(i)
        return True
    return default


def _flag(extra: list[str], flag: str) -> bool:
    if flag in extra:
        extra.remove(flag)
        return True
    return False


def is_write(name: str, extra: list[str]) -> bool:
    x = list(extra)
    _take(x, "--read")
    a = [t for t in x if not t.startswith("--")]
    sub = a[0] if a else ""
    if name == "ddc":
        return sub in ("set", "sleep", "wake", "brightness")
    if name == "settings":
        return sub in ("set", "save", "defaults")
    if name == "i2c":
        return len(a) > 1
    return name in ("kvm", "note", "flash")


def translate(name: str, extra: list[str], unit: str) -> list[tuple[str, dict]]:
    """requests for a legacy dev.py command; PortCannotCarry for arguments the port has no field for"""
    x = list(extra)
    link = "dp" if _flag(x, "--dp") else "hdmi"
    if _flag(x, "--force"):
        raise PortCannotCarry("--force (a working screen): the port acts on test units only (devices.json test=true)")
    p = {"unit": unit, "link": link}
    if name == "ddc":
        sub = x[0] if x else ""
        if sub == "get" and 2 <= len(x) <= 9:
            return [("vcp", {**p, "op": "get", "codes": x[1:]})]
        if sub == "set" and len(x) == 3:
            return [("vcp", {**p, "op": "set", "code": x[1], "value": x[2]})]
        return [("passthrough", {**p, "name": "ddc", "args": x})]
    if name == "settings":
        confirm = _flag(x, "--no-confirm")
        if _take(x, "--map") or "--sim" in x:
            return [("passthrough", {**p, "name": "settings", "args": extra_without(extra, "--unit", "--dp", "--force")})]
        sub = x[0] if x else ""
        if sub == "list" and len(x) == 1:
            return [("get", {**p, "all": True})]
        if sub == "get" and len(x) == 2:
            return [("get", {**p, "name": x[1]})]
        if sub == "set" and len(x) == 3:
            return [("set", {**p, "name": x[1], "value": x[2], "confirm": confirm})]
        if sub == "save" and len(x) == 1:
            return [("save", p)]
        return [("passthrough", {**p, "name": "settings", "args": x})]
    if name == "synclog":
        if _take(x, "--map") or "--delta" in x:
            return [("passthrough", {**p, "name": "synclog", "args": extra_without(extra, "--unit", "--dp", "--force")})]
        return [("synclog", {**p, "whole": _flag(x, "--whole")})]
    if name == "note":
        if _take(x, "--map"):
            return [("passthrough", {**p, "name": "note", "args": extra_without(extra, "--unit", "--dp", "--force")})]
        openc = _flag(x, "--open-console")
        if len(x) != 1 or x[0].startswith("--"):
            raise PortCannotCarry("note: one TEXT argument (quote it)")
        return [("note", {**p, "text": x[0], "open_console": openc})]
    if name == "kvm":
        units = _take(x, "--units")
        _flag(x, "--verify")                                 # the port always reads the input back
        if not units or units is True:
            raise PortCannotCarry("kvm through the port needs --units N[,N]: it acts on test units only (devices.json test=true)")
        if len(x) != 1 or x[0].startswith("--"):
            raise PortCannotCarry(f"kvm: TARGET and --units only through the port; got {x}")
        return [("kvm", {"unit": u, "target": x[0]}) for u in units.split(",")]
    if name == "i2c":
        read = _take(x, "--read")
        if not x:
            raise PortCannotCarry("i2c: ADDR [BYTES...] [--read N]")
        return [("i2c", {**p, "addr": x[0], "write": x[1:], **({"read": int(read)} if read not in (None, True) else {})})]
    raise PortCannotCarry(f"{name} is not a port command")


def extra_without(extra: list[str], *flags: str) -> list[str]:
    """extra minus the flags the port carries itself (--unit N is a field, not an argument)"""
    x = list(extra)
    for f in flags:
        _take(x, f) if f == "--unit" else _flag(x, f)
    return x


def format_reply(method: str, params: dict, rep: dict) -> str:
    res = rep.get("result") or {}
    if "output" in res and res["output"].strip():
        return res["output"].rstrip()
    if "values" in res and isinstance(res["values"], dict) and "name" not in res:
        return "\n".join(f"{k} = {v['label'] or v['value']} (raw {v['value']})" if isinstance(v, dict) else f"{k} = {v}"
                         for k, v in res["values"].items())
    if "name" in res and "value" in res:
        return f"{res['name']} = {res.get('label') or res['value']} (raw {res['value']})" + ("  verified" if res.get("verified") else "")
    return json.dumps(res)


def run_legacy(name: str, extra: list[str], unit: str, path: Path | None = None, launcher=default_launcher, say=print) -> int:
    """dev.py <name> through the port; prints what the direct command printed; returns its rc"""
    reqs = translate(name, extra, unit)
    path = ensure_app(path, launcher, say=say)
    rcs: list[int] = [0] * len(reqs)
    lines: list[str] = [""] * len(reqs)

    def one(i: int, method: str, params: dict):
        try:
            with Client(path) as c:
                rep = c.call(method, params)
        except GuiError as e:
            rcs[i], lines[i] = 1, f"gui: {e}"
            return
        ok = rep.get("ok")
        res = rep.get("result") or {}
        rcs[i] = 0 if ok else int(res.get("rc") or 1)
        text = format_reply(method, params, rep)
        lines[i] = text if ok else f"{text}\ngui: {rep.get('error')}".strip()
    ts = [threading.Thread(target=one, args=(i, m, p)) for i, (m, p) in enumerate(reqs)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    for ln in lines:
        say(ln)
    return max(rcs)


def run_flash(args: list[str], unit: str, path: Path | None = None, launcher=default_launcher, say=print) -> int:
    """dev.py flash through the port: async job, progress printed as events arrive, exit with the flash's rc.
    The client never stops the flash: Ctrl-C only detaches (the job runs on in the app)."""
    path = ensure_app(path, launcher, say=say)
    sub = Client(path, FLASH_STATUS_S)
    try:
        ack = sub.call("subscribe")
        if not ack.get("ok"):
            raise GuiError(f"subscribe refused: {ack.get('error')}")
        with Client(path) as c:
            rep = c.call("flash", {"unit": unit, "args": args})
        if not rep.get("ok"):
            say(f"flash: {rep.get('error')}")
            return 1
        job = rep["result"]["job"]
        say(f"flash: job {job['id']} started on unit {unit} (pid {job['pid']}); progress follows, the flash runs on if this client stops")
        last_ev = time.monotonic()
        for ev in sub.events():
            now = time.monotonic()
            if ev is None or ev.get("unit") != unit or ev.get("job") not in (None, job["id"]):
                if now - last_ev >= FLASH_SILENCE_S:
                    say(f"flash: WARN no progress for {FLASH_SILENCE_S} s (the flash is still owned by the app; not stopped)")
                    last_ev = now
                st = try_call(path, "flash_status", {"unit": unit})
                if st and st.get("ok") and st["result"].get("done"):
                    return _flash_end(st["result"], say)
                continue
            last_ev = now
            for ln in ev.get("lines", []):
                say(f"flash: {ln}")
            if ev["event"] == "flash":
                say(f"flash: {ev['phase']} {ev['percent']:.1f} % sectors {ev['written']}/{ev['total']} errors {ev['errors']} "
                    f"recoveries {ev['recoveries']} elapsed {ev['elapsed_s']:.0f} s" + (f" eta {ev['eta_s']:.0f} s" if ev.get("eta_s") else ""))
            elif ev["event"] == "flash_done":
                return _flash_end(ev, say)
        say("flash: the app closed the event stream; the flash job is detached and continues (flash_status shows it)")
        return 1
    finally:
        sub.close()


def _flash_end(ev: dict, say) -> int:
    say(f"flash: finished rc {ev['rc']} in {ev.get('elapsed_s', 0):.0f} s")
    return int(ev["rc"])


# --- `dev.py gui`
SUBCOMMANDS = ("ping", "list", "state", "select", "get", "set", "save", "kvm", "saver", "run", "health", "synclog", "note", "host-time",
               "vcp", "i2c", "ddc", "flash-status", "events", "quit")


def parse_gui(argv: list[str], default_unit: str | None = None) -> tuple[list[tuple[str, dict]], dict]:
    """`dev.py gui` arguments -> (requests, options). Two spellings:
    command form   gui [--serial S|--unit N] get volume | set mute on | kvm hdmi-1 | i2c 0x34 0x22 --read 2 ...
    flag form      gui --serial S --kvm hdmi-1 --save   (actions run in the order given; --save verifies what was set before it)"""
    x = list(argv)
    opts = {"json": _flag(x, "--json"), "timeout": _take(x, "--timeout")}
    p: dict = {}
    if (v := _take(x, "--serial")) not in (None, True):
        p["serial"] = v
    if (v := _take(x, "--unit")) not in (None, True):
        p["unit"] = v
    if _flag(x, "--dp"):
        p["link"] = "dp"
    _flag(x, "--hdmi")
    confirm = _flag(x, "--confirm")
    if default_unit and "serial" not in p and "unit" not in p and not (x and x[0] in ("ping", "list", "state", "quit", "events", "select")):
        p["unit"] = default_unit                             # like every dev.py command: the first test unit, never a working screen
    if x and x[0] in SUBCOMMANDS:
        return [(*_command_form(x, p, confirm),)], opts
    return _flag_form(x, p, confirm), opts


def _command_form(x: list[str], p: dict, confirm: bool) -> tuple[str, dict]:
    c, a = x[0], x[1:]
    m = c.replace("-", "_")
    try:
        if c in ("ping", "list", "state", "quit", "health", "host-time", "events"):
            return ("subscribe" if c == "events" else m), p
        if c == "select":
            q = dict(p)
            if (v := _take(a, "--page")) is not None:
                q["page"] = v
            if (v := _take(a, "--row")) is not None:
                q["row"] = v
            if a and a[0] in (str(n) for n in range(1, 10)):
                q["unit"] = a[0]
            return "select", q
        if c == "get":
            if a == ["--all"]:
                return "get", {**p, "all": True}
            if a == ["--quick"]:
                return "get", {**p, "quick": True}
            return "get", {**p, "names": a}
        if c in ("set", "run"):
            if c == "set" and len(a) != 2:
                raise PortCannotCarry("set NAME VALUE")
            return "set", {**p, "name": a[0], **({"value": a[1]} if len(a) > 1 else {}), "confirm": confirm}
        if c == "save":
            return "save", {**p, "verify": a}
        if c == "kvm":
            return "kvm", {**p, "target": a[0]}
        if c == "saver":
            return "saver", {**p, **({"stop": True} if a == ["stop"] else {"name": a[0]})}
        if c == "synclog":
            return "synclog", {**p, "whole": "--whole" in a}
        if c == "note":
            return "note", {**p, "text": a[0], "open_console": "--open-console" in a}
        if c == "vcp":
            return "vcp", {**p, "op": "get", "codes": a[1:]} if a[0] == "get" else {**p, "op": "set", "code": a[1], "value": a[2], "readback": True}
        if c == "i2c":
            r = _take(a, "--read")
            return "i2c", {**p, "addr": a[0], "write": a[1:], **({"read": int(r)} if r not in (None, True) else {})}
        if c == "ddc":
            return "passthrough", {**p, "name": "ddc", "args": a}
        if c == "flash-status":
            return "flash_status", p
    except IndexError as e:
        raise PortCannotCarry(f"gui {c}: missing argument") from e
    raise PortCannotCarry(f"gui {c}: unknown")


def _flag_form(x: list[str], p: dict, confirm: bool) -> list[tuple[str, dict]]:
    reqs: list[tuple[str, dict]] = []
    set_names: list[str] = []
    i = 0
    one = {"--volume": "volume", "--mute": "mute", "--brightness": "brightness"}
    while i < len(x):
        f = x[i]
        nxt = x[i + 1] if i + 1 < len(x) else None
        if f == "--kvm" and nxt:
            reqs.append(("kvm", {**p, "target": nxt}))
            set_names.append("input")
            i += 2
        elif f in one and nxt is not None:
            reqs.append(("set", {**p, "name": one[f], "value": nxt, "confirm": confirm}))
            set_names.append(one[f])
            i += 2
        elif f == "--set" and nxt and "=" in nxt:
            k, v = nxt.split("=", 1)
            reqs.append(("set", {**p, "name": k, "value": v, "confirm": confirm}))
            set_names.append(k)
            i += 2
        elif f == "--get" and nxt:
            reqs.append(("get", {**p, "names": [nxt]}))
            i += 2
        elif f == "--saver" and nxt:
            reqs.append(("saver", {**p, "name": nxt} if nxt != "stop" else {**p, "stop": True}))
            i += 2
        elif f == "--save":
            reqs.append(("save", {**p, "verify": list(dict.fromkeys(set_names))}))
            i += 1
        elif f in ("--health", "--synclog", "--state", "--list"):
            reqs.append((f[2:], p))
            i += 1
        elif f == "--i2c":
            j = i + 1
            args = []
            while j < len(x) and not (x[j].startswith("--") and not x[j].lstrip("-").isdigit()):
                args.append(x[j])
                j += 1
            r = None
            if j < len(x) and x[j] == "--read" and j + 1 < len(x):
                r, j = int(x[j + 1]), j + 2
            if not args:
                raise PortCannotCarry("--i2c ADDR [BYTES...] [--read N]")
            reqs.append(("i2c", {**p, "addr": args[0], "write": args[1:], **({"read": r} if r else {})}))
            i = j
        else:
            raise PortCannotCarry(f"gui: unknown argument {f!r}")
    if not reqs:
        raise PortCannotCarry("gui: nothing to do; see ./dev.py gui --help")
    return reqs


def run_gui(argv: list[str], default_unit: str | None = None, path: Path | None = None, launcher=default_launcher, say=print) -> int:
    reqs, opts = parse_gui(argv, default_unit)
    path = ensure_app(path, launcher, say=say)
    rc = 0
    if reqs[0][0] == "subscribe":
        with Client(path, None) as c:
            c.call("subscribe")
            for ev in c.events():
                if ev:
                    say(json.dumps(ev))
        return 0
    with Client(path, float(opts["timeout"]) if opts["timeout"] not in (None, True) else CLIENT_LIMIT_S) as c:
        for method, params in reqs:
            rep = c.call(method, params)
            if opts["json"]:
                say(json.dumps(rep))
            else:
                ms = rep.get("elapsed_ms")
                if rep.get("ok"):
                    say(f"ok {method} {json.dumps(rep.get('result'))} ({ms} ms)")
                else:
                    say(f"error {method}: {rep.get('error')} ({ms} ms)")
            if not rep.get("ok"):
                rc = 1
                break                                        # a failed step stops the sequence: --save must not follow a failed set
    return rc
