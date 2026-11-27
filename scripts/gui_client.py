#!/usr/bin/env python3
"""Client of the monitor GUI's control port (awto-ddc#276, docs/monitor-gui.md "Control port"): connect, send, timeout, JSON.
dev.py's ddc / settings / kvm / synclog / note / i2c / flash commands and `dev.py gui` are thin wrappers around this module:
they never touch a bus themselves. No app answering = start it headless, poll its socket up to START_WAIT_S, then fail naming the app's log."""
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

from _repo import ROOT

PROTOCOL = 1
ROUTED = ("ddc", "settings", "synclog", "note", "kvm", "i2c", "flash")
# Server side: one request waits for its chain of device calls (write + read back + save, each <= 5 s) plus queueing behind
# other units' serialised ddc calls (<= 2 x 5 s): worst ~25 s, x1.8 = 45 s. Expiry: error reply, the jobs finish in the app.
SERVER_LIMIT_S = 45
CLIENT_LIMIT_S = SERVER_LIMIT_S + 5      # the server always answers within its limit; +5 s = a reply in flight
PING_S = 2                               # a ping is answered on the UI thread's next turn (ms); 2 s = the UI thread is stuck
# Wait for the headless app to answer its socket after the launch. What: run.py -> Qt import -> MonitorPage -> port listening.
# Measured 2026-11-20, 5 starts each (awto-ddc#276 follow-up): warm 0.31 s max; cold (page cache of the venv, Python, repo evicted with
# posix_fadvise DONTNEED) 0.40 s max; cold + all cores busy 1.11 s max. 1.25 x 1.11 = 1.4 s, below the 3 s floor: the floor wins
# (a loaded dev box was ~11 load average at the time; the floor leaves 2.7x over the slowest). Expiry: error naming START_LOG.
START_WAIT_S = float(os.environ.get("AWTO_GUI_START_WAIT_S", "3"))   # env: tests only
START_POLL_S = 0.1                       # poll pace of the socket while the app starts (a ping costs ~1 ms)
START_LOG = ROOT / "tmp" / "logs" / "gui-headless.log"
FLASH_SILENCE_S = 60                     # flash client: no event for this long = a WARN line (the flash is never stopped by the client)
QUIT_WAIT_S = 3                          # a quitting app closes its socket within ~1 s (Qt event loop exit); expiry: start anyway
FLASH_STATUS_S = 5                       # flash client: cross-check the job state when no event arrived (events may be missed)


# synclog job limit, sized from the request (awto-ddc#358): 1.25 x (SYNC_BASE_S + entries / DRAM_RATE). See synclog_limit.
SYNC_BASE_S = 2.2                        # fixed cost of one synclog job: dev.py + map + link on/off + header + decode (docs/monitor-gui.md "Job limits")
DRAM_RATE = 77.0                         # DDR log entries/s over the debug link (one 16 B burst each; measured: docs/monitor-gui.md "Job limits")
LIMIT_MULT = 1.25
HDR = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"


def hdr_int(name: str, default: int) -> int:
    import re
    try:
        m = re.search(rf"^#define\s+{name}\s+(\d+)", HDR.read_text(), re.MULTILINE)
    except OSError:
        return default
    return int(m.group(1)) if m else default


def synclog_entries(args: list[str]) -> tuple[int, str]:
    """(DDR entries a `dev.py synclog ARGS` read may fetch at most, what decides it)"""
    x = list(args)
    if "--dram" in x:
        if any(f in x for f in ("--all", "--boot", "--since")):
            return hdr_int("AWTO_DLOG_SLOTS", 32768), "--all / --boot / --since: up to the whole DDR ring (AWTO_DLOG_SLOTS)"
        last = _take(x, "--last")
        return (int(last), "--last") if last not in (None, True) and str(last).isdigit() else (64, "--dram default --last 64")
    if "--whole" in x:
        return hdr_int("AWTO_SYNC_N", 88), "--whole: the ring view (AWTO_SYNC_N)"
    return hdr_int("AWTO_SYNC_WRAP", 176) - 1, "one episode: up to the seq window (AWTO_SYNC_WRAP - 1) from the DDR"


def synclog_limit(args: list[str]) -> tuple[float, str]:
    """(limit s, the arithmetic) of one synclog job"""
    n, why = synclog_entries(args)
    lim = round(LIMIT_MULT * (SYNC_BASE_S + n / DRAM_RATE), 1)
    return lim, f"{LIMIT_MULT} x ({SYNC_BASE_S} s + {n} entries / {DRAM_RATE:g} per s) = {lim} s ({why})"


def request_limit_s(method: str, params: dict) -> float:
    """server wait for one request: SERVER_LIMIT_S, or for a synclog its sized job limit + SERVER_LIMIT_S (queueing as any request)"""
    if method == "synclog":
        return synclog_limit(["--whole"] if params.get("whole", True) else [])[0] + SERVER_LIMIT_S
    if method == "passthrough" and params.get("name") == "synclog":
        return synclog_limit([str(a) for a in params.get("args", [])])[0] + SERVER_LIMIT_S
    return SERVER_LIMIT_S


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
        self.buf = b""                       # own line buffer: a makefile() reader is dead after its first timeout (OSError on the next read)

    def close(self):
        self.s.close()

    def readline(self) -> bytes:
        """one line, b"" when the peer closed; TimeoutError after the socket timeout with the buffer kept (the next call continues)"""
        while b"\n" not in self.buf:
            chunk = self.s.recv(65536)
            if not chunk:
                rest, self.buf = self.buf, b""
                return rest
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line + b"\n"

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def call(self, method: str, params: dict | None = None) -> dict:
        """one request, one reply: {"ok", "result" | "error", "elapsed_ms", ...}"""
        self.n += 1
        self.s.sendall(json.dumps({"id": self.n, "method": method, "params": params or {}}).encode() + b"\n")
        try:
            line = self.readline()
        except TimeoutError as e:
            raise GuiError(f"{method}: no reply in {self.timeout} s") from e
        if not line:
            raise GuiError(f"{method}: the app closed the connection")
        return json.loads(line)

    def events(self):
        """after subscribe(): yields event dicts until the connection ends; None on a read timeout"""
        while True:
            try:
                line = self.readline()
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


def code_stamp(root: Path | None = None) -> str:
    """12 hex of (path, mtime, size) of the code the app and its workers run: dev.py, scripts/*.py, tools/osd_editor/*.py"""
    import hashlib
    r = Path(root or ROOT)
    h = hashlib.sha1()
    for p in [r / "dev.py", *sorted((r / "scripts").glob("*.py")), *sorted((r / "tools/osd_editor").glob("*.py"))]:
        try:
            st = p.stat()
        except OSError:
            continue
        h.update(f"{p.relative_to(r)}:{st.st_mtime_ns}:{st.st_size}\n".encode())
    return h.hexdigest()[:12]


GIT_LIMIT_S = 2                          # local `git rev-parse` ~5 ms; 2 s = a cold exec on a loaded box (as _repo.py). Expiry: head "?"
META = ("ping", "list", "state", "jobs", "flash_status", "subscribe", "quit")   # port queries that run no unit code: served by any tree's app


class GuiRefused(GuiError):
    pass


def git_head(root: Path | None = None) -> str:
    """short HEAD of a tree ('?' when git does not answer)"""
    try:
        r = subprocess.run(["git", "-C", str(root or ROOT), "rev-parse", "--short=10", "HEAD"], capture_output=True, text=True,
                           timeout=GIT_LIMIT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return "?"
    return r.stdout.strip() or "?"


def tree_of(ping: dict) -> str:
    return f"{ping.get('root', '?')} @{ping.get('head', '?')}"


def stale_reason(ping: dict, root: Path | None = None) -> str | None:
    """why the running app is not the caller's (None = same tree, same code): every tree uses the one per-user app (awto-ddc#358)"""
    r = Path(root or ROOT)
    app_root = ping.get("root")
    if not app_root or not ping.get("code"):
        return "no version in its ping (older than the handshake)"
    if not Path(app_root).is_dir():
        return f"its tree {app_root} is gone (deleted worktree)"
    if Path(app_root).resolve() != r.resolve():
        return "it runs another tree"
    if ping["code"] != code_stamp(r):
        return "its code changed on disk since it started"
    return None


def client_log(line: str) -> None:
    """one line per tree decision (restart / refuse / served by another tree) in the caller's tmp/logs/gui-client.log"""
    import isostamp
    log = ROOT / "tmp" / "logs" / "gui-client.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(f"{isostamp.now()} pid {os.getpid()} {line}\n")
    except OSError:
        pass


def check_tree(path: Path, strict: bool = True, say=print) -> bool:
    """compare the live app's tree with the caller's. Same = nothing. Differs + idle = quit it (True: caller starts its own).
    Differs + busy = GuiRefused naming both trees and the jobs (strict), or one line and served as is (META queries)."""
    r = try_call(path, "ping", {})
    if not (r and r.get("ok")):
        return False
    ping = r["result"]
    why = stale_reason(ping, ROOT)
    if not why:
        return False
    mine = f"{ROOT} @{git_head(ROOT)}"
    busy = ping.get("busy") or []
    q = None if busy else try_call(path, "quit", {"idle_only": True}, timeout=PING_S)
    if busy or not q or not q.get("ok"):
        what = "; ".join(busy) if busy else (q.get("error") if q else "no reply to quit")
        line = (f"gui: the shared app (pid {ping.get('pid')}) runs {tree_of(ping)}, this call is from {mine} ({why}); it is busy: {what}")
        if not strict:
            client_log(line + "; read-only query served by that app")
            say(line + "; read-only query served by that app")
            return False
        client_log(line + "; refused")
        raise GuiRefused(line + ". Refused: nothing was run. Wait for it, or isolate a tree with AWTO_GUI_SOCKET")
    line = f"gui: restarting the app from {mine}: {why} (was pid {ping.get('pid')}, {tree_of(ping)})"
    client_log(line)
    say(line)
    t0 = time.monotonic()
    while app_live(path) and time.monotonic() - t0 < QUIT_WAIT_S:
        time.sleep(START_POLL_S)
    return True


def app_live(path: Path | None = None) -> bool:
    r = try_call(Path(path or socket_path()), "ping", {})
    return bool(r and r.get("ok"))


def default_launcher(path: Path):
    """start the app headless and detached: run.py --headless (QT_QPA_PLATFORM=offscreen), output to START_LOG; returns the Popen"""
    hook = os.environ.get("AWTO_GUI_LAUNCHER")              # tests only: any command replaces the real app
    run_py = ROOT / "tools" / "osd_editor" / "run.py"
    cmd = hook.split() if hook else [sys.executable, str(run_py), "--headless"]
    START_LOG.parent.mkdir(parents=True, exist_ok=True)
    with START_LOG.open("a") as lf:
        return subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True,
                         env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "AWTO_GUI_SOCKET": str(path)})


def ensure_app(path: Path | None = None, launcher=default_launcher, wait_s: float | None = None, say=print, strict: bool = True) -> Path:
    """the caller's tree's app on `path`: started when none answers, replaced when another tree / stale code serves it (check_tree)"""
    path = Path(path or socket_path())
    if app_live(path):
        check_tree(path, strict, say)
        if app_live(path):
            return path                                # same tree, or busy and a META query (served as is)
    wait = START_WAIT_S if wait_s is None else wait_s
    say(f"gui: starting the GUI app headless ... (no app on {path}; waiting up to {wait:g} s, log {START_LOG})")
    proc = launcher(path)
    t0 = time.monotonic()
    while True:
        if app_live(path):
            say(f"gui: app up after {time.monotonic() - t0:.1f} s")
            return path
        died = proc.poll() if hasattr(proc, "poll") else None
        if died is not None and not app_live(path):              # the app process exited: no point waiting out the bound
            raise GuiUnavailable(f"gui: the app exited with rc {died} while starting; see its log {START_LOG}. Nothing was run on the unit.")
        if time.monotonic() - t0 >= wait:
            break
        time.sleep(START_POLL_S)
    raise GuiUnavailable(
        f"gui: the app did not answer on {path} within {wait:g} s; see its log {START_LOG}. Nothing was run on the unit. "
        f"Start it by hand to see why: python3 tools/osd_editor/run.py --headless (or without --headless for the window), then repeat.")


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
        if _take(x, "--map") or any(f in x for f in ("--dram", "--last", "--boot", "--all", "--since")):     # DRAM log reads: the port has no fields for them
            return [("passthrough", {**p, "name": "synclog", "args": extra_without(extra, "--unit", "--dp", "--force")})]
        return [("synclog", {**p, "whole": _flag(x, "--whole"), "json": _flag(x, "--json")})]
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
    if "writes" in res and "values" in res:
        return (f"drag {res['name']} {res['from']} -> {res['to']}: {res['values']} value changes, {res['writes']} writes sent, {res['saves']} saves, "
                f"{res['duration_s']} s, median write {res['median_write_ms']} ms, floor {res['floor_ms']} ms, read back {res['readback']}"
                f"{'  verified' if res['verified'] else '  NOT verified'}")
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
            with Client(path, request_limit_s(method, params) + CLIENT_LIMIT_S - SERVER_LIMIT_S) as c:
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
SUBCOMMANDS = ("ping", "list", "state", "select", "get", "set", "save", "kvm", "saver", "run", "health", "status", "synclog", "note", "host-time",
               "vcp", "i2c", "ddc", "drag", "flash-status", "jobs", "events", "quit")


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
    if default_unit and "serial" not in p and "unit" not in p and not (x and x[0] in ("ping", "list", "state", "quit", "events", "select", "jobs")):
        p["unit"] = default_unit                             # like every dev.py command: the first test unit, never a working screen
    if x and x[0] in SUBCOMMANDS:
        return [(*_command_form(x, p, confirm),)], opts
    return _flag_form(x, p, confirm), opts


def _command_form(x: list[str], p: dict, confirm: bool) -> tuple[str, dict]:
    c, a = x[0], x[1:]
    m = c.replace("-", "_")
    try:
        if c in ("ping", "list", "state", "quit", "health", "status", "host-time", "events", "jobs"):
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
        if c == "drag":
            steps, step_ms = _take(a, "--steps"), _take(a, "--step-ms")
            return "drag", {**p, "name": a[0], "from": a[1], "to": a[2], **({"steps": steps} if steps not in (None, True) else {}),
                            **({"step_ms": step_ms} if step_ms not in (None, True) else {})}
        if c == "save":
            return "save", {**p, "verify": a}
        if c == "kvm":
            return "kvm", {**p, "target": a[0]}
        if c == "saver":
            return "saver", {**p, **({"stop": True} if a == ["stop"] else {"name": a[0]})}
        if c == "synclog":
            return "synclog", {**p, "whole": "--whole" in a, "json": "--json" in a}
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


def format_jobs(jobs: list[dict]) -> str:
    """`dev.py gui jobs`: one line per flash job the app tracks (what it believes, re-derived from disk at the call)"""
    if not jobs:
        return "no flash jobs tracked by the app"
    head = f"{'unit':<5}{'job':<17}{'pid':<9}{'alive':<6}{'age s':<7}{'rc':<5}{'disk job':<17}{'disk rc':<8}log"
    rows = [f"{j['unit']:<5}{j['job']:<17}{j['pid']:<9}{'yes' if j['alive'] else 'no':<6}{j['age_s']:<7}{'-' if j['rc'] is None else j['rc']:<5}"
            f"{j['disk_job'] or '-':<17}{'-' if j['disk_rc'] is None else j['disk_rc']:<8}{j['log']}" for j in jobs]
    return "\n".join([head, *rows])


def run_gui(argv: list[str], default_unit: str | None = None, path: Path | None = None, launcher=default_launcher, say=print) -> int:
    reqs, opts = parse_gui(argv, default_unit)
    path = Path(path or socket_path())
    if not ([m for m, _ in reqs] == ["quit"] and app_live(path)):          # quit goes to whichever app runs: never start one to stop it
        path = ensure_app(path, launcher, say=say, strict=not all(m in META for m, _ in reqs))
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
            elif method == "jobs" and rep.get("ok"):
                say(format_jobs(rep["result"]["jobs"]))
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
