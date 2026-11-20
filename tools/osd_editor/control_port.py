"""Control port of the monitor GUI (awto-ddc#276): Unix socket (0600, same uid), one JSON object per line, JSON-RPC style.
Connection threads parse and wait; requests run on the UI thread, device calls use the per-unit queues.
Protocol, commands, security and flash: docs/monitor-gui.md "Control port"."""
from __future__ import annotations

import json
import os
import queue
import socket
import struct
import sys
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

import monitor as MON
from PySide6.QtCore import QObject, Qt, QTimer, Signal

sys.path.insert(0, str(MON.ROOT / "scripts"))
import gui_client as GC
import kvm as KVM

PROTOCOL = 1
CODE_AT_START = GC.code_stamp()     # ping handshake: dev.py restarts an app whose code changed on disk (gui_client.stale_reason)
# A request waits for its chain of device calls (write + read back + save, each <= 5 s) plus queueing behind the other
# units' serialised ddc calls (<= 2 x 5 s): worst ~25 s, x1.8 = 45 s. Expiry: error reply; the jobs still finish in the app.
REQUEST_LIMIT_S = GC.SERVER_LIMIT_S
CONN_IDLE_S = 30            # a client sends its request right after connecting; a silent connection is dropped
LINE_MAX = 1 << 20          # one request line; larger is a broken client
IDLE_EXIT_S = 900           # headless app with no request for this long quits: it must not linger holding the unit queues
TAKEOVER_WAIT_S = 3         # a window app asks a headless one to quit and waits for its socket to go (quit is one event-loop turn)
EVENT_Q_MAX = 1000          # a subscriber that does not read is dropped, never blocks the UI


class PortError(Exception):
    pass


def parse_value(r: dict, v) -> int:
    """raw value from an int, a number string or an option label (case-insensitive); range / label checked"""
    if r["type"] == "int":
        try:
            raw = int(str(v), 0)
        except ValueError as e:
            raise PortError(f"{r['name']}: {v!r} is not a number ({r['min']}..{r['max']})") from e
        lo, hi = r["min"], r["max"]
    else:
        opts = r["options"] or ["off", "on"]
        s = str(v).strip().lower()
        alias = {"true": "on", "false": "off", "1": "on", "0": "off"} if r["type"] == "bool" else {}
        s = alias.get(s, s)
        hit = [i for i, o in enumerate(opts) if o.lower() == s or o.lower().split()[0] == s]
        if hit:
            raw = r["min"] + hit[0]
        else:
            try:
                raw = int(s, 0)
            except ValueError as e:
                raise PortError(f"{r['name']}: {v!r} is none of {opts}") from e
        lo, hi = r["min"], r["max"]
    if not lo <= raw <= hi:
        raise PortError(f"{r['name']}: {raw} outside {lo}..{hi}")
    return raw


def label_of(r: dict, raw: int | None) -> str | None:
    if raw is None or r["type"] == "int":
        return None
    opts = r["options"] or ["off", "on"]
    i = raw - r["min"]
    return opts[i] if 0 <= i < len(opts) else None


class ControlPort(QObject):
    request = Signal(object, object)

    def __init__(self, page: MON.MonitorPage, path: Path | None = None, headless: bool = False, uid: int | None = None,
                 idle_exit_s: float | None = IDLE_EXIT_S, on_quit=None):
        super().__init__(page)
        self.page, self.path = page, Path(path or GC.socket_path())
        self.headless, self.uid = headless, os.getuid() if uid is None else uid
        self.idle_exit_s, self.on_quit = idle_exit_s, on_quit
        self.srv: socket.socket | None = None
        self.ident: tuple[int, int] | None = None        # (st_dev, st_ino) of our bound socket file
        self.why = ""
        self.subs: list[queue.Queue] = []
        self.sub_lock = threading.Lock()
        self.last_request = time.monotonic()
        self.stopping = False
        self.request.connect(self._dispatch, Qt.QueuedConnection)
        page.listeners.append(self._fan_out)
        self.idle = QTimer(self)
        self.idle.setInterval(30_000)                    # idle check pace; the exit limit itself is IDLE_EXIT_S
        self.idle.timeout.connect(self._idle_tick)

    # --- socket lifecycle
    def start(self) -> bool:
        """bind the socket; False (reason in self.why) when another app instance owns it"""
        self.why = ""
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.path.exists():
            peer = GC.try_call(self.path, "ping", {}, timeout=GC.PING_S)
            if peer and peer.get("ok"):
                if not (peer["result"].get("headless") and not self.headless):
                    self.why = f"control port {self.path} is served by pid {peer['result'].get('pid')}"
                    return False
                GC.try_call(self.path, "quit", {}, timeout=GC.PING_S)         # a window takes over from the headless app
                t0 = time.monotonic()
                while GC.try_call(self.path, "ping", {}, timeout=GC.PING_S) and time.monotonic() - t0 < TAKEOVER_WAIT_S:
                    QTimer.singleShot(0, lambda: None)
                    threading.Event().wait(0.05)
                if GC.try_call(self.path, "ping", {}, timeout=GC.PING_S):
                    self.why = f"headless app pid {peer['result'].get('pid')} still serves {self.path} {TAKEOVER_WAIT_S} s after quit was asked"
                    return False
        # bind to a private temp name, chmod, then atomic rename: the final path is never missing or world-open,
        # and a late unlink by the old app cannot hit our socket (stop() checks the inode)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.unlink(missing_ok=True)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o177)
        try:
            s.bind(str(tmp))
            os.chmod(tmp, 0o600)
            st = tmp.stat()
            os.rename(tmp, self.path)
        except BaseException:
            s.close()
            tmp.unlink(missing_ok=True)
            raise
        finally:
            os.umask(old)
        self.ident = (st.st_dev, st.st_ino)
        s.listen(16)
        self.srv = s
        threading.Thread(target=self._accept, name="gui-port-accept", daemon=True).start()
        if self.headless and self.idle_exit_s:
            self.idle.start()
        self.page.say(f"control port listening on {self.path}{' (headless)' if self.headless else ''}")
        return True

    def stop(self):
        self.stopping = True
        self.idle.stop()
        if self.srv:
            try:
                self.srv.close()
            finally:
                self.srv = None
        try:
            st = self.path.stat()
            if self.ident == (st.st_dev, st.st_ino):
                self.path.unlink()                           # only our own socket: a successor may already own the path
        except FileNotFoundError:
            pass

    def _accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except (OSError, AttributeError):
                return
            threading.Thread(target=self._serve, args=(c,), name="gui-port-conn", daemon=True).start()

    def _peer_ok(self, c: socket.socket) -> bool:
        _pid, uid, _gid = struct.unpack("3i", c.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        return uid == self.uid

    def _serve(self, c: socket.socket):
        with c:
            try:
                if not self._peer_ok(c):
                    c.sendall(b'{"ok": false, "error": "refused: peer is not the user running the app"}\n')
                    self.page.say("control port: connection from another user refused")
                    return
                c.settimeout(CONN_IDLE_S)
                f = c.makefile("rwb")
                for line in iter(lambda: f.readline(LINE_MAX), b""):
                    self.last_request = time.monotonic()
                    try:
                        req = json.loads(line)
                        if not isinstance(req, dict) or "method" not in req:
                            raise ValueError("need an object with a method")
                    except ValueError as e:
                        f.write(json.dumps({"ok": False, "error": f"bad request: {e}"}).encode() + b"\n")
                        f.flush()
                        continue
                    if req["method"] == "subscribe":
                        self._stream(c, f, req)
                        return
                    fut: Future = Future()
                    self.request.emit(req, fut)
                    t0 = time.monotonic()
                    try:
                        rep = fut.result(REQUEST_LIMIT_S)
                    except FutureTimeout:
                        rep = {"id": req.get("id"), "ok": False, "elapsed_ms": int((time.monotonic() - t0) * 1000),
                               "error": f"timed out after {REQUEST_LIMIT_S} s in the app (its jobs keep running)"}
                    f.write(json.dumps(rep).encode() + b"\n")
                    f.flush()
            except (OSError, ValueError):
                return                                   # client went away or idled out

    def _stream(self, c, f, req):
        q: queue.Queue = queue.Queue(EVENT_Q_MAX)
        with self.sub_lock:
            self.subs.append(q)
        try:
            f.write(json.dumps({"id": req.get("id"), "ok": True, "result": {"subscribed": True}}).encode() + b"\n")
            f.flush()
            c.settimeout(None)
            while not self.stopping:
                try:
                    ev = q.get(timeout=1)
                except queue.Empty:
                    continue
                if ev is None:
                    return
                f.write(json.dumps(ev).encode() + b"\n")
                f.flush()
        except OSError:
            return
        finally:
            with self.sub_lock:
                self.subs.remove(q)

    def _fan_out(self, ev: dict):
        ev = {**ev, "t": MON.isostamp.now()}
        with self.sub_lock:
            for q in self.subs:
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    pass                                     # a stuck subscriber loses events, never stalls the UI

    def _idle_tick(self):
        busy = any(st.pending for st in self.page.states.values()) or bool(self.page.flash_running())
        if not busy and time.monotonic() - self.last_request > self.idle_exit_s:
            self.page.say(f"headless: no request for {self.idle_exit_s} s, exiting")
            self._quit()

    def _quit(self):
        self.stop()
        if self.on_quit:
            self.on_quit()

    # --- UI-thread dispatch
    def _dispatch(self, req: dict, fut: Future):
        t0 = time.monotonic()
        rid = req.get("id")

        def finish(result=None, error=None, **extra):
            body = {"id": rid, "ok": error is None, "elapsed_ms": int((time.monotonic() - t0) * 1000), **extra}
            if error is None:
                body["result"] = result if result is not None else {}
            else:
                body["error"] = error
                if result is not None:
                    body["result"] = result
            if not fut.done():
                fut.set_result(body)

        try:
            fn = getattr(self, "m_" + str(req["method"]).replace("-", "_"), None)
            if fn is None:
                raise PortError(f"unknown method {req['method']!r}: see docs/monitor-gui.md 'Control port'")
            fn(req.get("params") or {}, finish)
        except PortError as e:
            finish(error=str(e))
        except Exception as e:  # noqa: BLE001  a handler bug is an error reply, never a dead app
            finish(error=f"internal error: {e!r}")

    # --- helpers
    def unit_of(self, p: dict, write: bool = False) -> str:
        """unit of a request. write=True: an explicit unit or serial is required, never the window's selection (a client that
        sent none must not hit whichever unit another client or the user selected)"""
        pg = self.page
        if write and p.get("serial") is None and p.get("unit") is None:
            raise PortError("a write needs an explicit unit or serial (the window's selected unit is never assumed)")
        if p.get("serial"):
            hit = [n for n, st in pg.states.items() if st.info["serial"] == p["serial"]]
            if not hit:
                raise PortError(f"no unit with serial {p['serial']!r}")
            return hit[0]
        n = str(p["unit"]) if p.get("unit") is not None else pg.cur
        if n not in pg.states:
            raise PortError(f"unknown unit {n!r}: have {list(pg.states)}")
        return n

    def focus(self, n: str):
        """the window follows the port: the unit it acts on becomes the selected one"""
        if n != self.page.cur:
            self.page.select_unit(n, read=False)

    def started(self, jid):
        if jid is None:
            raise PortError(self.page.refused or "not started")

    def row(self, name: str) -> dict:
        try:
            return MON.row_of(name)
        except StopIteration:
            raise PortError(f"unknown setting {name!r}: ./dev.py settings rows lists them") from None

    def reads(self, n: str, names: list[str], then):
        """read each registry row back from the unit in turn; then(values dict, error or None)"""
        out: dict = {}
        it = iter(names)

        def nxt(*_):
            name = next(it, None)
            if name is None:
                return then(out, None)
            r = self.row(name)
            self.page.states[n].values.pop(name, None)       # a read that returns nothing must not look verified
            self.started(self.page._readback(n, name, r, after=lambda rc, o, s, name=name: got(name, rc, o)))

        def got(name, rc, o):
            v = self.page.states[n].values.get(name)
            if rc != 0 or v is None:
                return then(out, f"read back of {name} failed: {MON.reason_line(o)}")
            out[name] = v
            nxt()

        try:
            nxt()
        except PortError as e:
            then(out, str(e))

    def shown(self, name: str, v):
        r = self.row(name)
        return {"value": v, "label": label_of(r, v)}

    # --- methods
    def m_ping(self, p, done):
        done({"pid": os.getpid(), "headless": self.headless, "protocol": PROTOCOL, "socket": str(self.path),
              "root": str(GC.ROOT), "code": CODE_AT_START})

    def m_quit(self, p, done):
        fl = self.page.flash_running()
        if fl:
            why = "; ".join(f"unit {n}: {self.page.flash_why(n)}" for n in fl)
            raise PortError(f"refusing to quit: a flash is running on unit(s) {', '.join(fl)} ({why}); it would continue detached, "
                            f"but the app does not close while it is followed. `dev.py gui jobs` shows what the app believes")
        done({"quitting": True})
        QTimer.singleShot(0, self._quit)

    def m_list(self, p, done):
        done({"cur": self.page.cur, "units": [self.unit_info(n) for n in self.page.states]})

    def unit_info(self, n: str) -> dict:
        st = self.page.states[n]
        return {"unit": n, "serial": st.info["serial"], "input": st.info.get("input"), "test": bool(st.info.get("test")),
                "writable": st.writable, "status": st.dot(), "detected": st.detected, "pending": st.pending,
                "flashing": st.flash or None,
                "flash_percent": st.track.progress.percent() if st.track is not None and st.track.progress.rc is None else None, "last_read": st.last_read_iso or None, "unknown": st.unknown}

    def m_select(self, p, done):
        n = self.unit_of(p)
        self.page.select_unit(n, read=False)
        if p.get("page") is not None:
            names = {v.lower(): k for k, v in MON.PAGES.items()}
            key = str(p["page"]).lower()
            idx = names.get(key, int(key) if key.isdigit() else None)
            if idx not in MON.PAGES:
                raise PortError(f"unknown page {p['page']!r}: {list(MON.PAGES.values())}")
            self.page._select_node(f"page:{idx}")
        if p.get("row"):
            self.row(p["row"])
            self.page._select_node(f"row:{p['row']}")
        done(self.dump())

    def m_state(self, p, done):
        done(self.dump())

    def dump(self) -> dict:
        pg = self.page
        st = pg.states[pg.cur]
        rows = {}
        for name, sr in pg.all_rows.items():
            if isinstance(sr, MON.ActionRow):
                rows[name] = {"action": True, "enabled": sr.btn.isEnabled()}
                continue
            rows[name] = {"widget": sr.raw(), "unit": st.values.get(name), "dirty": bool(sr.dirty), "shown": sr.cur.text(),
                          "enabled": sr.w.isEnabled()}
        quick = {k: {"widget": sr.raw(), "enabled": sr.w.isEnabled()} for k, sr in pg.quick.items()}
        quick["input"] = {"widget": pg.inp.currentIndex(), "text": pg.inp.currentText(), "enabled": pg.inp.isEnabled()}
        quick["screensaver"] = {"widget": pg.saver.currentData(), "text": pg.saver.currentText(), "enabled": pg.saver.isEnabled()}
        pidx = pg.stack.currentIndex()
        return {"unit": pg.cur, "serial": st.info["serial"], "writable": st.writable, "status": st.dot(),
                "page": MON.PAGES[pidx], "node": st.node, "mode": pg.state.text(), "banner": pg.banner.text() if pg.banner.isVisibleTo(pg) else "",
                "unit_shows": pg.now_state.text(), "pending": st.pending, "flashing": st.flash or None, "quick": quick, "rows": rows,
                "units": [self.unit_info(n) for n in pg.states], "output_tail": st.out[-400:]}

    def m_get(self, p, done):
        n = self.unit_of(p)
        self.focus(n)
        if p.get("all"):
            return self._job(done, self.page.get_all(n, after=lambda rc, o, s: done(
                {"values": dict(self.page.states[n].values), "output": o, "rc": rc} if rc == 0 else None,
                None if rc == 0 else MON.reason_line(o))))
        if p.get("quick"):
            return self._job(done, self.page.quick_get(n, after=lambda rc, o, s: done(
                {"values": {k: v for k, v in self.page.states[n].values.items() if k in MON.QUICK_VCP}} if rc == 0 else None,
                None if rc == 0 else MON.reason_line(o))))
        names = p.get("names") or [p["name"]]

        def then(vals, err):
            res = {"values": {k: self.shown(k, v) for k, v in vals.items()}}
            if len(vals) == 1 and len(names) == 1:
                res.update(self.shown(names[0], vals[names[0]]))
            done(res if err is None else None, err)
        self.reads(n, names, then)

    def _job(self, done, jid):
        if jid is None:
            done(error=self.page.refused or "not started")

    def m_set(self, p, done):
        n, name = self.unit_of(p, write=True), p["name"]
        r = self.row(name)
        if "ro" in r["flags"]:
            raise PortError(f"{name} is read-only")
        action = r["type"] == "action"
        if (action or "risky" in r["flags"]) and not p.get("confirm"):
            raise PortError(f"{name} is {'an action' if action else 'risky'}: send confirm=true (the GUI's dialog)"
                            + (" (needs a reboot)" if "reboot" in r["flags"] else ""))
        v = 1 if action else parse_value(r, p["value"])
        if name in MON.BACKLIGHT_ROWS and v == 0 and not p.get("confirm"):
            raise PortError(f"{name} 0 = black screen: send confirm=true ({MON.BL_ZERO_ASK}); any value 1..100 needs none")
        pg = self.page
        self.focus(n)
        sr = pg.quick[name] if name in MON.VCP_ROW else pg.all_rows[name]
        sr.set_value(v)

        def wrote(rc, out, secs):
            if rc != 0:
                return done({"rc": rc, "output": out}, f"{name}: device call failed: {MON.reason_line(out)} (view back at the unit's value)")
            if action:
                return done({"name": name, "ran": True, "output": out, "rc": rc})

            def then(vals, err):
                got = vals.get(name)
                res = {"name": name, "wrote": v, **self.shown(name, got), "verified": got == v}
                if err:
                    return done(res, err)
                done(res, None if got == v else f"{name}: wrote {v}, unit reports {got}")
            self.reads(n, [name], then)
        jid = pg.set_row(sr, confirmed=bool(p.get("confirm")), after=wrote, readback=False)
        self._job(done, jid)

    m_run = m_set

    def m_drag(self, p, done):
        """scripted slider drag through the live path: NAME from FROM to TO in `steps` valueChanged events `step_ms` apart (then released);
        replies with the writes-per-drag summary. A backlight drag is clamped at MON.BL_MIN like the slider"""
        n, name = self.unit_of(p, write=True), p["name"]
        r = self.row(name)
        if not MON.live_row(r):
            raise PortError(f"{name} is not a live row")
        a, b = int(p["from"]), int(p["to"])
        steps, step_ms = int(p.get("steps", 100)), int(p.get("step_ms", 5))
        lo = MON.BL_MIN if name in MON.BACKLIGHT_ROWS else r["min"]
        if not (lo <= min(a, b) and max(a, b) <= r["max"]) or steps < 1:
            raise PortError(f"{name}: drag {a}..{b} outside {lo}..{r['max']}")
        pg, lw = self.page, self.page.live_writer
        self.focus(n)
        sr = pg.quick[name] if name in pg.quick else pg.all_rows[name]
        if not (st := pg.states[n]).writable or st.flash:
            raise PortError(pg.refused or f"unit {n} is read-only or flashing")
        vals = [round(a + (b - a) * i / steps) for i in range(steps + 1)]

        def finished(res):
            if res["unit"] == n and res["name"] == name:
                lw.listeners.remove(finished)
                done(res, res["error"] or None)
        lw.listeners.append(finished)
        lw.hold(n, name, a)
        it = iter(vals)

        def tick():
            v = next(it, None)
            if v is None:
                return lw.release(n, name, b)
            sr.set_value(v)
            lw.change(n, name, v, a)
            QTimer.singleShot(step_ms, tick)
        tick()

    def m_save(self, p, done):
        n = self.unit_of(p, write=True)
        self.focus(n)
        names = list(p.get("verify") or [])

        def saved(rc, out, secs):
            if rc != 0:
                return done({"rc": rc, "output": out}, f"settings save failed: {MON.reason_line(out)}")

            def then(vals, err):
                res = {"saved": True, "verified": {k: self.shown(k, v) for k, v in vals.items()}}
                done(res, err)
            self.reads(n, names, then)
        self._job(done, self.page.save(n, after=saved))

    def m_kvm(self, p, done):
        n = self.unit_of(p, write=True)
        raw = str(p["target"])
        t = raw.replace("-", "").replace("_", "")
        t = {k.lower(): k for k in KVM.PORTS}.get(t.lower(), t.lower())
        if t not in KVM.PORTS and t not in ("next", "here"):
            raise PortError(f"kvm target {raw!r}: one of {sorted(KVM.PORTS)}, next, here")
        pg = self.page
        self.focus(n)
        r = self.row("input")
        want = r["option_vcp"].index(KVM.PORTS[t]) if t in KVM.PORTS else None
        old = pg.inp.currentIndex()
        if want is not None:
            pg.inp.setCurrentIndex(want)
            pg.inp_touched = True

        def switched(rc, out, secs):
            if rc != 0:
                pg.inp.setCurrentIndex(old)
                pg.inp_touched = False
                pg._quick_state(n)
                return done({"rc": rc, "output": out}, f"kvm {t} failed: {MON.reason_line(out)} (view back at {pg.inp.currentText()})")

            def then(vals, err):
                pg.inp_touched = False
                got = vals.get("input")
                pg._quick_state(n)
                res = {"target": t, "wrote": want, **self.shown("input", got), "verified": None if want is None else got == want}
                if err:
                    return done(res, err)
                done(res, None if want is None or got == want else f"kvm {t}: unit reports input {got}, expected {want}")
            self.reads(n, ["input"], then)
        self._job(done, pg.input_select(t, n, after=switched))

    def m_saver(self, p, done):
        n = self.unit_of(p, write=True)
        names = {lab.lower(): v for lab, v in MON.SAVER_NOW}
        key = "stop" if p.get("stop") else str(p.get("name", "")).lower()
        v = names.get(key, int(key) if key.isdigit() else None)
        if v is None or v not in names.values():
            raise PortError(f"saver {p.get('name')!r}: one of {list(names)} or a VCP value")
        label = next(lab for lab, val in MON.SAVER_NOW if val == v)
        self.focus(n)
        self.page.saver.setCurrentText(label)

        def wrote(rc, out, secs):
            if rc != 0:
                return done({"rc": rc, "output": out}, f"screensaver {label} failed: {MON.reason_line(out)}")

            def then(vals, err):
                got = vals.get("screensaver_now")
                done({"saver": label, "wrote": v, "value": got, "verified": got == v}, err or (None if got == v else f"unit reports {got}"))
            self.reads(n, ["screensaver_now"], then)
        self._job(done, self.page._saver(v, label, n, after=wrote))

    def _plain(self, done, jid_or_none):
        self._job(done, jid_or_none)

    def _out(self, done, what: str):
        def cb(rc, out, secs):
            done({"rc": rc, "output": out}, None if rc == 0 else f"{what} failed (rc {rc}): {MON.reason_line(out)}")
        return cb

    def m_health(self, p, done):
        n = self.unit_of(p)
        self.focus(n)
        self._plain(done, self.page.health(n, after=self._out(done, "health")))

    def m_synclog(self, p, done):
        n = self.unit_of(p)
        self.focus(n)
        self._plain(done, self.page.sync_log(n, whole=bool(p.get("whole", True)), after=self._out(done, "synclog")))

    def m_host_time(self, p, done):
        n = self.unit_of(p, write=True)
        self._plain(done, self.page.host_time(n, after=self._out(done, "host time")))

    def m_note(self, p, done):
        n = self.unit_of(p, write=True)
        self._plain(done, self.page.note(str(p["text"]), n, bool(p.get("open_console")), after=self._out(done, "note")))

    def m_vcp(self, p, done):
        op = p.get("op", "get")
        n = self.unit_of(p, write=op != "get")
        pg, dp = self.page, (["--dp"] if p.get("link") == "dp" else [])
        if op == "get":
            codes = [str(c) for c in p["codes"]]
            return self._plain(done, pg.run(f"vcp get {' '.join(codes)}", pg.dev("ddc", "get", *codes, *dp, unit=n),
                                            lambda rc, out: pg._vcp_got(n, out), "ddcmany", unit=n, after=lambda rc, o, s: done(
                                                {"rc": rc, "output": o, "values": [m.groups() for m in map(MON.VCP_GET_RE.search, o.splitlines()) if m]}
                                                if rc == 0 else {"rc": rc, "output": o}, None if rc == 0 else MON.reason_line(o))))
        if op != "set":
            raise PortError("vcp: op get | set")
        code, val = str(p["code"]), str(p["value"])
        u, backend = pg.states[n].info, pg.queues.backend

        def slow_set(why: str):                              # the old path, said out loud: the in-process write failed (not silent)
            pg.say(f"unit {n} vcp set {code} = {val}: in-process write failed ({why}); falling back to dev.py ddc set")
            self._plain(done, pg.run(f"vcp set {code} = {val}", pg.dev("ddc", "set", code, val, *dp, unit=n), None, "ddc", unit=n, after=wrote))

        def wrote(rc, out, secs):
            if rc != 0 or not p.get("readback"):
                return done({"rc": rc, "output": out}, None if rc == 0 else f"vcp set failed: {MON.reason_line(out)}")
            c = int(code, 16)

            def rb():
                rc2, o2 = backend.live_get(u, c, None)
                return rc2, (f"VCP {c:02X} C {o2.split()[1]} {o2.split()[3]}" if rc2 == 0 else o2)
            jid = pg.live_call(f"vcp readback {code}", rb, lambda rc2, o2, s2: (pg._vcp_got(n, o2) if rc2 == 0 else None, done(
                {"rc": rc2, "output": o2, "wrote": val}, None if rc2 == 0 else MON.reason_line(o2))), unit=n)
            self._job(done, jid)

        def fast(rc, out, secs):
            if rc != 0:
                return slow_set(out.strip())
            wrote(0, out, secs)
        try:
            c, v = int(code, 16), int(val, 0)
        except ValueError:
            return slow_set("code / value not a number")
        if p.get("link") == "dp":
            return slow_set("dp link: the old path resolves the DP AUX bus")
        self._job(done, pg.live_call(f"vcp set {code} = {val}", lambda: backend.live_set(u, c, v, None, False), fast, unit=n))

    def m_i2c(self, p, done):
        """raw I2C on the unit: addr (7-bit), write = byte list, read = count (both: write, repeated start, read)"""
        n, pg = self.unit_of(p, write=bool(p.get("write"))), self.page
        args = [str(p["addr"]), *[str(b) for b in p.get("write", [])]]
        if p.get("read"):
            args += ["--read", str(int(p["read"]))]
        if p.get("link") == "dp":
            args.append("--dp")
        self._plain(done, pg.run(f"i2c {' '.join(args)}", pg.dev("i2c", *args, unit=n), None, "i2c", unit=n, after=self._out(done, "i2c")))

    def m_passthrough(self, p, done):
        """a dev.py device command the port does not model: runs as the unit's queued job (ddc list / sleep, settings defaults, ...)"""
        n, pg = self.unit_of(p, write=True), self.page
        name = p["name"]
        if name not in GC.ROUTED:
            raise PortError(f"passthrough: {name!r} is not a routed command {sorted(GC.ROUTED)}")
        args = [str(a) for a in p.get("args", [])]
        limit = {"settings": "list", "synclog": "synclog", "note": "synclog", "ddc": "ddcmany"}.get(name, "one")
        self.focus(n)
        self._plain(done, pg.run(f"{name} {' '.join(args)}", pg.dev(name, *args, unit=n), None, limit, unit=n, after=self._out(done, name)))

    def m_flash(self, p, done):
        """async: replies with the job at once; progress and the result stream as flash / flash_done events (see flash_status)"""
        n = self.unit_of(p, write=True)
        try:
            job = self.page.flash_start(n, [str(a) for a in p.get("args", [])])
        except ValueError as e:
            raise PortError(str(e)) from None
        self.focus(n)
        done({"job": {k: job[k] for k in ("id", "pid", "started", "log")}, "unit": n, "async": True})

    def m_jobs(self, p, done):
        """the app's belief about flash jobs, re-derived from the job files + wrapper pids at this call (stale ones are closed first)"""
        done({"jobs": self.page.flash_jobs()})

    def m_flash_status(self, p, done):
        n = self.unit_of(p)
        st = self.page.flash_status(n)
        done(st if st is not None else {"done": True, "job": None, "note": "no flash job for this unit"})
