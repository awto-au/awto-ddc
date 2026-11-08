#!/usr/bin/env python3
"""Drive and read our OSD menu over I2C (awto-ddc#67): state | key K | hold KEYS MS | open PAGE | select ITEM | set ITEM V |
get ITEM | back | close | walk.

usage: menu_cli.py (--bus N --serial S | --sim BIN) --map MAP CMD [ARGS] [--png DIR]
  State: struct menu_diag (awto-rtdfw menu.h) at map symbol _menu_diag, read byte-wise over debug slave 0x35.
  Commands: mailbox _vcp_box cmd 3 (= VCP 0xE4 over DDC/CI): KEY (through the firmware key path), HOLD (raw key mask
  for a time: long press / combinations), OPEN page, SELECT item, SET value, BACK, CLOSE.
  Names: pages = settings/pages.tsv groups (or main), items = registry names, keys = menu right left exit power,
  holds = '+'-joined keys (menu+left).
  walk: every page by OPEN and by keys, every entry by SELECT and by Right; each state is checked against the registry
  (page, parent, entry count, cursor, item id / sub-page, value = settings get). --png DIR (sim only): one render per page.
Exit 1 on a failed check. Log: ./tmp/logs/menu_cli.log
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings_cli as C  # noqa: E402
import settings_table as T  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/menu_cli.log"
MAIN = 0xFE
OPS = dict(key=1, open=2, select=3, set=4, back=5, close=6, enter=7, hold=8)
KEYS = dict(menu=0, right=1, left=2, exit=3)
MASK = dict(power=0x01, menu=0x02, right=0x04, left=0x08, exit=0x10)
FIELDS = ["magic", "version", "open", "page", "cursor", "item_id", "item_page", "mode", "top", "val_lo", "val_hi",
          "redraw_lo", "redraw_hi", "last_key", "pending", "n", "parent", "seq"]
READS = 5                # torn-read retries: the firmware updates the struct from its main loop, the host reads async
SETTLE_S = 0.25          # HOLD only (sim): no state change to wait for until the long-press time is up
KEY_S = 0.47             # KEY: wait for menu_diag.seq to move. Same bound as settings_cli.MAILBOX_S (one OSD draw class)


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def page_of(name: str) -> int:
    if name == "main":
        return MAIN
    for i, p in enumerate(T.PAGES):
        if p["group"] == name or str(i) == name:
            return i
    raise SystemExit(f"no page {name!r}: main or one of {[p['group'] for p in T.PAGES]}")


def entries(page: int) -> list[int]:
    if page == MAIN:
        return [0x80 | i for i, p in enumerate(T.PAGES) if p["parent"] == 0xFF]
    return T.PAGES[page]["entries"]


class Menu:
    def __init__(self, box: C.Box, map_text: str, sim: bool):
        self.box, self.sim = box, sim
        self.addr = C.xaddr(map_text, "menu_diag")

    def state(self) -> dict:
        for _ in range(READS):
            q0 = self.box.xrd(self.addr + 17, 1)[0]
            b = self.box.xrd(self.addr, len(FIELDS))
            if not q0 & 1 and b[17] == q0:
                break
            if self.sim:
                self.box.bus.wait(0.002)
        else:
            raise SystemExit(f"menu_diag kept changing over {READS} reads")
        s = dict(zip(FIELDS, b))
        if s["magic"] != ord("M"):
            raise SystemExit(f"menu_diag at 0x{self.addr:04X}: magic 0x{s['magic']:02X}, not 'M': the menu has not run yet "
                             "(open it first: `open main`) or the image has no menu")
        s["value"] = int.from_bytes(bytes([s["val_lo"], s["val_hi"]]), "little", signed=True)
        s["redraws"] = s["redraw_lo"] | s["redraw_hi"] << 8
        return s

    def now(self) -> float:
        return self.box.bus.now() if self.sim else time.monotonic()

    def cmd(self, op: str, arg: int = 0):
        s0 = self.box.xrd(self.addr + 17, 1)[0] if op == "key" else 0
        self.box.call(3, OPS[op], arg)
        if op == "key":
            # the mailbox acks when the key message is queued; the OSD handler consumes it on a later main-loop pass and
            # menu_diag.seq (bumped by every handled key) is the completion signal
            t0 = self.now()
            while True:
                q = self.box.xrd(self.addr + 17, 1)[0]
                if q != s0 and not q & 1:
                    break
                if self.now() - t0 > KEY_S:
                    say(f"WARN key {arg}: menu_diag.seq unchanged after {self.now() - t0:.2f} s (limit {KEY_S} s)")
                    break
                if self.sim:
                    self.box.bus.wait(0.001)
            self.lat = max(getattr(self, "lat", 0.0), self.now() - t0)
        elif self.sim and op == "hold":
            self.box.bus.wait(SETTLE_S)

    @staticmethod
    def show(s: dict) -> str:
        pg = "main" if s["page"] == MAIN else T.PAGES[s["page"]]["group"] if s["page"] < len(T.PAGES) else s["page"]
        it = (T.BY_ID[s["item_id"]]["name"] if s["item_id"] in T.BY_ID else "-") if s["item_page"] == 0xFF \
            else f"page {T.PAGES[s['item_page']]['group']}" if s["item_page"] < len(T.PAGES) else "-"
        mode = {0: "list", 1: "edit", 2: "armed"}.get(s["mode"], s["mode"])
        return (f"open={s['open']} page={pg} cursor={s['cursor']}/{s['n']} item={it} value={s['value']} mode={mode} "
                f"top={s['top']} redraws={s['redraws']} last_key={s['last_key']} pending={s['pending']}")


def item_arg(name: str) -> int:
    if name.startswith("page:"):
        return 0x80 | page_of(name[5:])
    return C.row_of(name)["id"]


def walk(m: Menu, png: Path | None, render) -> int:
    fails = 0

    def check(what, ok, s):
        nonlocal fails
        fails += not ok
        if not ok:
            say(f"FAIL {what}: {Menu.show(s)}")
    pages = [MAIN] + list(range(len(T.PAGES)))
    for p in pages:
        m.cmd("open", p)
        s = m.state()
        ent = entries(p)
        parent = 0xFF if p == MAIN else T.PAGES[p]["parent"]
        check(f"open page {p}", s["open"] == 1 and s["page"] == p and s["n"] == len(ent) and s["parent"] == parent, s)
        if render and png:
            render(png / f"walk_{'main' if p == MAIN else T.PAGES[p]['group']}.png")
        for k, e in enumerate(ent):
            r0 = s["redraws"]
            m.cmd("select", e if e & 0x80 else T.ROWS[e]["id"])
            s = m.state()
            if e & 0x80:
                ok = s["cursor"] == k and s["item_page"] == e & 0x7F and s["item_id"] == 0
            else:
                row = T.ROWS[e]
                ok = s["cursor"] == k and s["item_id"] == row["id"] and s["item_page"] == 0xFF
                if ok and row["type"] != "action" and "ro" not in row["flags"]:
                    ok = s["value"] == m.box.get_row(row)
            check(f"select page {p} entry {k}", ok and s["redraws"] != r0, s)
        say(f"page {'main' if p == MAIN else T.PAGES[p]['group']}: {len(ent)} entries checked")
    # keys: Right through the top list wraps back to 0; Menu enters the first page, Exit returns to it
    m.cmd("open", MAIN)
    n = len(entries(MAIN))
    for k in range(1, n + 1):
        m.cmd("key", KEYS["right"])
        s = m.state()
        check(f"key right {k}", s["cursor"] == k % n and s["last_key"] == KEYS["right"], s)
    m.cmd("key", KEYS["menu"])
    s = m.state()
    check("key menu enters page 0", s["page"] == 0 and s["cursor"] == 0, s)
    m.cmd("key", KEYS["exit"])
    s = m.state()
    check("key exit back to main", s["page"] == MAIN and s["cursor"] == 0, s)
    m.cmd("close")
    s = m.state()
    check("close", s["open"] == 0, s)
    say(f"key latency (ack to seq change), max {getattr(m, 'lat', 0.0) * 1000:.1f} ms")
    say(f"walk: {'PASS' if not fails else f'{fails} FAIL'} ({len(pages)} pages, {sum(len(entries(p)) for p in pages)} entries)")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--serial")
    ap.add_argument("--sim", type=Path)
    ap.add_argument("--map", required=True)
    ap.add_argument("--png", type=Path, help="sim: render each page to this directory during walk")
    ap.add_argument("--hl", type=int, choices=(0, 1), help="sim: selected-row look (ui_hl_style: 0 red bar, 1 red marker + underline, #87)")
    ap.add_argument("cmd", choices=["state", "key", "hold", "open", "select", "set", "get", "back", "close", "enter", "walk"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    render, session = None, None
    if a.sim and a.png:
        import osd_render as R
        session = R.Session(a.sim, Path(a.map), "1080p60")
        session.boot()
        bus = session.bus
        render = lambda out: R.save(session.snap(), out, "grey", 2)       # noqa: E731
        a.png.mkdir(parents=True, exist_ok=True)
    elif a.sim:
        import fw_sim
        bus = fw_sim.SimBus(a.sim, Path(a.map))
    else:
        if a.bus is None or not a.serial:
            raise SystemExit("need --bus N --serial S (dev.py menu --unit N fills them) or --sim BIN")
        bus, _ = C.open_bus(a)
    mt = Path(a.map).read_text(errors="replace")
    if a.sim and a.hl is not None:
        bus.m.wr(bus.addr("ui_hl_style"), bytes([a.hl]))
    m = Menu(C.Box(bus, mt, bool(a.sim)), mt, bool(a.sim))
    try:
        if a.cmd == "walk":
            return walk(m, a.png, render)
        if a.cmd == "key":
            m.cmd("key", KEYS[a.args[0]])
        elif a.cmd == "hold":
            mask = 0
            for k in a.args[0].split("+"):
                mask |= MASK[k]
            ms = int(a.args[1]) if len(a.args) > 1 else 3000
            m.cmd("hold", (ms // 50) << 5 | mask)
        elif a.cmd == "open":
            m.cmd("open", page_of(a.args[0] if a.args else "main"))
        elif a.cmd == "select":
            m.cmd("select", item_arg(a.args[0]))
        elif a.cmd == "set":
            r = C.row_of(a.args[0])
            m.cmd("open", r["page"])
            m.cmd("select", r["id"])
            m.cmd("set", C.parse_value(r, a.args[1]) & 0xFFFF)
        elif a.cmd == "get":
            r = C.row_of(a.args[0])
            say(C.show(r, m.box.get_row(r)))
            return 0
        elif a.cmd in ("back", "close", "enter"):
            m.cmd(a.cmd)
        say(Menu.show(m.state()))
        return 0
    finally:
        bus.close()


if __name__ == "__main__":
    sys.exit(main())
