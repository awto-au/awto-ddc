#!/usr/bin/env python3
"""#157 in fw_sim: host time over DDC/CI (table write VCP 0xE9), console title row, ring lines, host-side conversion.

usage: AWTO_SIM_CORE=fast host_time_sim.py BIN [--map MAP]
- Boot 1080p60 with the console auto-open (firmware default); the ring header must be the firmware's own ('SY', #158).
- Title row (map row 0): "AWTO DIAGNOSTICS  FW <tag>" + "PANEL nnnn.nnh  UP nnnn.nnh  HOST --:--:--" before a sync.
- Sync 1 (2026-11-12T08:45:10.250+11:00): HOST ticks from it; ring D7 "host time ..." + D8 "(fw +N ms, first ...)"; the
  console log pane shows the line; get VCP E9 = syncs 1, drift 0; sync_log.stamp puts the host time on the lines.
- Sync 2 on time: no ring line, syncs 2, |drift| small. Sync 3 5 s ahead: D7 + D8 (drift) + D9 "drift +5xxx ms".
- Changed cells only: OSD writes of one idle title tick vs the full title draw; no other row written in that second.
  STALE: last sync moved 200 s back. UP: wrap count + 32 (2 097 152 ms) shows as 0000.58h.
- Pages (images with AWTO_CON_GPIO, map symbol _AwtoConLogTail): main = event log, host time + fw ms on one row, no GPIO table;
  test cmd 0x43 = GPIO page (table + input changes, no sync lines); text + PNG of both: --out (default tmp/console_pages).
Exit 1 on a failed check. Log: tmp/logs/host_time_sim.log
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D  # noqa: E402
import fw_sim as S  # noqa: E402
import host_time as HT  # noqa: E402
import osd_model as M  # noqa: E402
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402
import sync_log as SL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/host_time_sim.log"
VCP = 0xE9
OFS = 44                                                    # +11:00 in 15 min units (AEDT)
T0 = dt.datetime(2026, 11, 12, 8, 45, 10, 250000, dt.timezone(dt.timedelta(hours=11)))
CMD_S = 1.0         # test cmd -> console page drawn: one full draw (~0.3 s sim, boot_sim) x ~3
CON_S = 4.0         # console auto-open after ACTIVE: settled + one pass (sync_sim sees it within 1 s) x4 for the boot console
TICK_S = 1.25       # title refresh AWTO_TITLE_MS 1 s x1.25


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


class Sim:
    def __init__(self, binp: Path, mapp: Path):
        self.model = M.OsdModel()
        self.model.img = binp.read_bytes()
        self.eng = D.DdcEngine()
        self.bus = S.SimBus(binp, mapp, "htsim-" + binp.stem, None, boot=False, devs=[self.model, self.eng], video="1080p60")
        self.m = self.bus.m
        self.mccs = D.Mccs(self.bus, self.eng)
        self.rows = SL.load_rows(SL.tsv_for(mapp))
        self.a_ht, self.a_sync = self.m.addr("g_stAwtoHt"), self.m.addr("g_stAwtoSync")
        self.fails = 0
        self.base = None                                    # glyph id of ' ' (ids = ASCII - 0x20 + base, font.c font_ids)

    def check(self, ok: bool, what: str, detail: str = ""):
        say(f"  {'PASS' if ok else 'FAIL'} {what}" + (f": {detail}" if detail else ""))
        self.fails += not ok

    def boot(self):
        used = 0
        while used < 160_000_000 and self.bus.diag()["stage"] < 8:
            self.m.run(1_000_000); used += 1_000_000
        if not self.bus.run_until_mode(3):
            raise SystemExit("never reached ACTIVE")
        say(f"ACTIVE at fw {self.bus.now():.3f} s")

    def text(self) -> list[str]:
        st = self.model.snapshot(self.m, 0)
        rows = M.layout_rows(st, M.frame_geometry(st))
        cs = rows[0]["chars"] if rows else []
        if self.base is None and len(cs) > 4 and all(c["kind"] == "1bit" for c in cs[1:5]):
            b = cs[1]["id"] - (ord("A") - 0x20)                            # title starts " AWTO"
            if [c["id"] - b + 0x20 for c in cs[2:5]] == [ord(x) for x in "WTO"]:
                self.base = b                                              # only from a drawn title (#162 s3: draw timing moved)
        b = self.base or 0
        return ["".join(chr(c["id"] - b + 0x20) if c["kind"] == "1bit" and 0 <= c["id"] - b < 95 else " " for c in r["chars"])
                for r in rows]

    def title(self) -> str:
        t = self.text()
        return t[0].rstrip() if t else ""

    def ht(self) -> dict:
        return SL.ht_decode(bytes(self.m.rd(self.a_ht, SL.HT_SIZE)))

    def fw32(self) -> int:
        return SL.fw_now(self.ht(), int.from_bytes(self.m.rd(0xF6D0 + SL.DIAG_T2, 2), "big"))

    def ring(self):
        raw = bytes(SL.read_ring(self.m.rd, self.a_sync))
        return raw, SL.decode(raw, self.rows, whole=True)

    def send(self, t: dt.datetime) -> float:
        e = int(t.timestamp())
        ms = int(round((t.timestamp() - e) * 1000))
        t_send = self.bus.now()
        self.mccs.tx(HT.packet(t.timestamp(), OFS)[1:-1], reply=False)    # host_time.py's own encoding (len, chk: Mccs.tx)
        say(f"sent host time {t.isoformat(timespec='milliseconds')} (unix {e}.{ms:03d}) at fw {self.bus.now():.3f} s")
        return t_send                                      # fw time the request was queued (not the end of the reply wait)

    def get(self):
        return self.mccs.get(VCP)

    def cmd(self, c: int):
        self.m.wr(self.m.addr("g_stAwtoDiag") + T.TESTCMD_OFF, bytes([c]))   # RAM: the DDC/CI engine owns the host channel here
        self.bus.wait(CMD_S)

    def dump(self, out: Path, name: str) -> list[str]:
        """Text of the shown rows -> out/name.txt, render -> out/name.png"""
        t = self.text()
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.txt").write_text("\n".join(r.rstrip() for r in t) + "\n")
        R.render_snap(self.model.snapshot(self.m, 0), "black", 1).save(out / f"{name}.png")
        say(f"  page {name}: {out / name}.txt / .png")
        return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/console_pages")
    a = ap.parse_args()
    mapp = a.map or a.bin.with_suffix(".map")
    if " _g_stAwtoHt " not in mapp.read_text(errors="replace"):
        say(f"SKIP {a.bin.name}: no _g_stAwtoHt (image without #157)")
        return 0
    say(f"=== host_time_sim {a.bin.name} ===")
    s = Sim(a.bin, mapp)
    s.boot()
    t_end = s.bus.now() + CON_S
    while "AWTO DIAGNOSTICS" not in s.title() and s.bus.now() < t_end:
        s.bus.wait(0.25)
    s.bus.wait(TICK_S)                                      # console draw done: a request queued mid-draw is served late
    ti = s.title()
    say(f"title: {ti!r}")
    s.check("AWTO DIAGNOSTICS  FW " in ti, "console open, title FW tag")
    m = re.search(r"PANEL (\d{4}\.\d{2})h  UP (\d{4}\.\d{2})h  HOST (\S+)", ti)
    s.check(bool(m), "title live fields", m.group(0) if m else ti)
    s.check(bool(m) and m.group(3) == "--:--:--", "HOST before the first sync = --:--:--")
    raw, (h, _) = s.ring()
    s.check(raw[0:2] == b"SY" and raw[2] == 3 and raw[12] * SL.EV + SL.HDR == len(raw), "ring header written by the firmware (#158)", raw[:SL.HDR].hex(" "))
    g = s.get()
    s.check(g is not None and g["max"] == 0, "get E9 before a sync: syncs 0", str(g))

    # sync 1
    n0 = h["seq"]
    t_s = s.send(T0)
    s.bus.wait(TICK_S)
    ht = s.ht()
    s.check(ht["syncs"] == 1 and ht["epoch"] == int(T0.timestamp()) and ht["frac"] == 250 and ht["ofs"] == OFS,
            "g_stAwtoHt stored", str(ht))
    exp = T0 + dt.timedelta(seconds=s.bus.now() - t_s)
    ti = s.title()
    hm = re.search(r"HOST (\d\d:\d\d:\d\d)", ti)
    got = dt.datetime.strptime(hm.group(1), "%H:%M:%S").time() if hm else None
    lag = ((exp.hour * 3600 + exp.minute * 60 + exp.second) - (got.hour * 3600 + got.minute * 60 + got.second)) if got else 99
    s.check(got is not None and 0 <= lag <= 1, "HOST ticks from the sync (0..1 s behind: 1 s refresh)",
            f"{hm.group(1) if hm else '-'} vs host {exp.time().isoformat('seconds')}")
    raw, (h, lines) = s.ring()
    new = lines[-((h["seq"] - n0) % h["wrap"]):] if h["seq"] != n0 else []
    say("ring lines: " + " | ".join(new))
    s.check(any("host time 2026-11-12T08:45:10+11:00" in x for x in new), "ring: host time line")
    s.check(any("(fw +" in x and "first host sync since boot" in x for x in new), "ring: fw ms line (first sync)")
    s.check(sum(("host time" in x) or ("(fw +" in x) for x in new) == 2, "ring: 2 entries for the first sync")
    scr = s.text()
    s.check(any("host time 2026-11-12T08:45:10+11:00" in r for r in scr), "console log pane shows the host time line")
    pages = "_AwtoConLogTail" in mapp.read_text(errors="replace")
    if pages:
        s.check(any("host time 2026-11-12T08:45:10+11:00 (fw +" in r and "first host sync since boot)" in r for r in scr),
                "main page: host time and fw ms on one row", next((r.strip() for r in scr if "host time" in r), ""))
        s.check(not any("GPIO INPUT" in r for r in scr), "main page: no GPIO table")
    g = s.get()
    s.check(g is not None and g["max"] == 1 and g["cur"] == 0, "get E9: syncs 1, drift 0", str(g))
    st = SL.stamp(h, lines, s.ht(), int.from_bytes(s.m.rd(0xF6D0 + SL.DIAG_T2, 2), "big"))
    hl = next((x for x in st if "host time 2026" in x), "")
    say(f"stamped: {hl}")
    s.check(hl.startswith("2026-11-12T08:45:10."), "sync_log.stamp: the sync line at its host time", hl[:31])
    if not hl.startswith("2026-11-12T08:45:10."):
        for ev, u in list(zip(h["events"], SL.unwrap(h["events"], s.fw32())))[:14]:
            say(f"    ev {ev[0]:02X} {ev[1]:02X} ms16 {ev[2]} v {ev[3]:08X} -> {u}")
    s.check(all(not x.startswith(" " * 31) for x in st[-6:]), "sync_log.stamp: recent lines stamped")

    # sync 2: on time
    n0 = h["seq"]
    t2 = T0 + dt.timedelta(seconds=s.bus.now() - t_s)
    s.send(t2)
    s.bus.wait(0.2)
    raw, (h, _) = s.ring()
    g = s.get()
    s.check(h["seq"] == n0, "sync 2 on time: no ring line", f"{(h['seq'] - n0) % h["wrap"]} new")
    s.check(g is not None and g["max"] == 2 and abs(g["cur"] - (g["cur"] >> 15) * 65536) < 50, "get E9: syncs 2, |drift| < 50 ms", str(g))

    # sync 3: host 5 s ahead
    n0 = h["seq"]
    s.send(T0 + dt.timedelta(seconds=s.bus.now() - t_s + 5))
    s.bus.wait(0.2)
    raw, (h, lines) = s.ring()
    new = lines[-((h["seq"] - n0) % h["wrap"]):] if h["seq"] != n0 else []
    say("ring lines: " + " | ".join(new))
    d = next((int(x.group(1)) for x in (re.search(r"drift \+(\d+) ms", y) for y in new) if x), None)
    s.check(len(new) == 3 and d is not None and 4950 <= d <= 5050, "sync 3 (+5 s): host / fw / drift lines", f"drift {d}")
    s.check(any("host sync after a drift" in x for x in new), "ring: fw line says drift")
    g = s.get()
    s.check(g is not None and 4950 <= g["cur"] <= 5050, "get E9: drift ~ +5000 ms", str(g))

    # changed cells only: OSD writes in one idle tick vs the whole title
    s.bus.wait(TICK_S)
    st = s.model.snapshot(s.m, 0)
    fs = M.frame_geometry(st)["fs_base"]
    s.model.trace, s.model.trace_on = [], True
    s.bus.wait(1.0)
    s.model.trace_on = False
    cells = sorted({ad - fs for w, ad, _ in s.model.trace if (w >> 2) & 3 == M.SRAM_FONT and fs <= ad < fs + 120})
    rows = collections.Counter((ad - fs) // 120 for w, ad, _ in s.model.trace if (w >> 2) & 3 == M.SRAM_FONT and ad >= fs)
    say(f"title cells written in 1 s idle (one tick): {cells} ({len(s.model.trace)} OSD data writes in all, per map row "
        f"{dict(sorted(rows.items()))})")
    s.check(0 < len(cells) <= 8 and all(c >= 60 for c in cells), "idle tick redraws only changed title cells (not 48)", str(cells))
    if pages:
        s.check(set(rows) <= {0} and len(s.model.trace) <= 3 * 8, "idle 1 s: no OSD write outside the changed title cells",
                f"{len(s.model.trace)} writes, rows {sorted(rows)}")

    # STALE: the last sync 200 s ago
    fw = s.fw32()
    s.m.wr(s.a_ht + 8, ((fw - 200_000) & 0xFFFFFFFF).to_bytes(4, "big"))
    s.bus.wait(TICK_S)
    ti = s.title()
    s.check("STALE" in ti, "HOST marked STALE after 3 min without a sync", ti[60:])

    # UP from the 32-bit count: + 32 wraps
    ht = s.ht()
    s.m.wr(s.a_ht + 14, (ht["up_hi"] + 32).to_bytes(2, "big"))
    s.bus.wait(TICK_S)
    fw = s.fw32()
    exp = f"UP {fw // 36000 // 100:04d}.{fw // 36000 % 100:02d}h"
    ti = s.title()
    s.check(exp in ti, f"UP hour meter from the 32-bit ms count ({fw} ms)", ti[60:])
    say(f"title: {ti!r}")

    if pages:                                           # both pages: text + PNG; the GPIO page has no sync lines
        main_t = s.dump(a.out, f"{a.bin.stem}.main")
        s.check(any("EVENT LOG" in r for r in main_t[:4]), "main page: event log heading")
        s.cmd(0x43)
        g = s.dump(a.out, f"{a.bin.stem}.gpio")
        s.check(any("GPIO INPUT DIAGNOSTICS" in r for r in g[:4]) and any("INPUT CHANGES" in r for r in g[:4]),
                "GPIO page (test cmd 0x43): table + input change list", g[2].strip() if len(g) > 2 else "")
        s.check("GPIO INPUTS  FW " in g[0] and "HOST" not in g[0], "GPIO page: own title row (no live fields)")
        s.check(not any(("host time" in r) or ("mode ACTIVE" in r) or ("-> ACTIVE:" in r) for r in g), "GPIO page: no sync / power lines")
        s.cmd(0x44)
        s.check(s.m.rd(s.m.addr("g_stAwtoGpio") + 3)[0] == 0, "test cmd 0x44 closes the console")
    say(f"=== {a.bin.name}: {'ALL PASS' if not s.fails else f'{s.fails} FAIL'} ===")
    return 1 if s.fails else 0


if __name__ == "__main__":
    sys.exit(main())
