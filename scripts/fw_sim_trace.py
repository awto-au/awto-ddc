#!/usr/bin/env python3
"""Register-WRITE trace of a mode change (4K60) in the fw_sim model, vendor image or ours (#26).

usage: fw_sim_trace.py vendor [IMG] [--mode 2160p60]            vendor Keil image, names from re/jxc-4k (fw_sim_vendor)
       fw_sim_trace.py ours BIN MAP [--mode 2160p60]            our SDCC image
  Runs the image with a stable HDMI source on D2 (same register models for both) until the mode state is ACTIVE (3) after
  DISPLAY_SETTING (2) (+ --tail instr). Logs every write to P0 P1 P5 P20 P30 P31 P37 P40 P45 (also those the source models
  handle), mode-state changes and calls of the M-domain / FRC / double-buffer / VGIP functions present in the image.
  TSV: seq instr fw_ms bank pc func+off kind addr reg idx value   (kind W | CALL | STATE; idx = data-port index for indexed ports)
  fw_ms = instr / 12.6 k (Timer2 time dilation T2_SCALE = 3 -> 4.2 k instr per fw ms x 3).
Log: tmp/logs/trace_<tag>.tsv (+ tmp/logs/fw_sim_trace_<tag>.log)
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import fw_regs  # noqa: E402

ROOT = S.ROOT
PAGES = (0x00, 0x01, 0x05, 0x45, 0x20, 0x30, 0x31, 0x37, 0x40)
PORTS = {0x2B: 0x2A, 0x31: 0x30, 0x34: 0x33, 0x61: 0x60, 0x6D: 0x6C}         # data reg -> address reg (page 0 indexed ports)
CALLS = ("ScalerMDomainControl", "ScalerMDomainMemorySettings", "ScalerMDomainSetDisplayFormat", "ScalerMDomainSetDisplayTimingGen",
         "ScalerMDomainMemoryConfig", "ScalerMDomainCalculateDclkDVtotal", "ScalerMDomainMemoryCheck", "ScalerFRCControl", "ScalerFRCEn",
         "ScalerFRCInitial", "ScalerFRCInputCtrl", "ScalerFRCDisplayCtrl", "ScalerMemoryReset", "ScalerMemoryInitial",
         "ScalerMemorySetFifoCapture", "ScalerMemoryFrameSyncSetDt", "ScalerMemorySetFIFOFreq", "ScalerMDomainDisplayTimingGenDBEnable",
         "ScalerGlobalDoubleBufferEnable", "ScalerGlobalDoubleBufferApply", "ScalerVgipDoubleBufferEnable", "ScalerVgipCaptureEnable",
         "ScalerDDomainBackgroundEnable", "ScalerDPLLFineTuneFrameSyncLineBuffer", "ScalerMeasureInputInfo", "ScalerFmtCnvFinalSetting",
         "ScalerFmtCnvInitialSetting", "ScalerMeasureUpdateOnlineMeasureResult", "ScalerMeasureInputActiveRegionChange",
         "ScalerVgipInputInitial", "ScalerMemoryFineTuneIVS2DVSDelay", "ScalerGlobalWatchDog", "ScalerMemorySetShiftOneLine")
TICKS_MS = 4200 * S.T2_SCALE


class Logger(S.Dev):
    """Write tap on ranges; chains to the source model that owns the address (HdmiInput, W1C, ...)."""

    def __init__(self, tr, addrs):
        self.tr, self.writes, self.chain = tr, tuple(sorted(addrs)), {}

    def on_write(self, m, a):
        self.tr.write(m, a)
        d = self.chain.get(a)
        if d:
            d.on_write(m, a)


class StateTap(S.Dev):
    def __init__(self, tr, a):
        self.tr, self.writes = tr, (a,)

    def on_write(self, m, a):
        self.tr.state(m, m.rd(a)[0])


class Trace:
    def __init__(self, tag, names):
        self.rows, self.tag, self.names, self.idx = [], tag, names, {}
        self.m = None
        self.seen_ds = False
        self.done_at = None

    def _pc(self, m):
        import re
        mt = re.search(r"Stop at 0x([0-9a-f]+)", m.last_out)
        bank = m.rd(0xFFFF)[0] & 15
        pc = int(mt.group(1), 16) if mt else -1
        cend = m.where.cend
        key = pc if pc < cend or bank == 0 else bank * S.BANK + pc
        fn = m.where(bank, pc)
        base = m.sym.get(fn, 0)
        return bank, pc, f"{fn.lstrip('_')}+0x{key - base:x}" if fn != "?" and key >= base else "?"

    def add(self, m, kind, addr, val, label=""):
        bank, pc, fo = self._pc(m)
        reg = label or self.names.get(addr, "?")
        idx = ""
        if kind == "W" and addr < 0x100 and addr in PORTS:
            idx = f"{self.idx.get(PORTS[addr], -1):02x}"
        self.rows.append((len(self.rows), m.instr, round(m.instr / TICKS_MS, 1), bank, f"{pc:04x}", fo, kind, f"{addr:04x}", reg, idx, f"{val:02x}"))

    def write(self, m, a):
        v = m.rd(a)[0]
        if a < 0x100 and a in PORTS.values():
            self.idx[a] = v
        self.add(m, "W", a, v)

    def state(self, m, v):
        self.add(m, "STATE", 0, v, S.MODE_NAMES[v & 0x1F] if (v & 0x1F) < len(S.MODE_NAMES) else "?")
        if (v & 0x1F) == 2:
            self.seen_ds = True
        if (v & 0x1F) == 3 and self.seen_ds and self.done_at is None:
            self.done_at = m.instr
            m.request_stop()

    def call(self, m, name):
        self.add(m, "CALL", 0, 0, name)


def run(kind: str, img_path: Path, map_path: Path | None, mode: str, max_instr: int, tail: int, tag: str):
    img = img_path.read_bytes()
    names = fw_regs.names()
    tr = Trace(tag, names)
    log = (ROOT / f"tmp/logs/fw_sim_trace_{tag}.log").open("w", buffering=1)
    devs, hdmi = S.video_devs(img, mode)
    taken = {a: d for d in devs for a in d.writes}
    ranges = {pg << 8 | i for pg in PAGES for i in range(256)}
    lg = Logger(tr, ranges - set(taken))
    if kind == "vendor":
        import fw_sim_vendor as V
        mp = V.make_map(img)
        extra = [lg]
        m = S.Machine(img, mp, "trace-vendor", log, [*devs, *extra], ncode=V.NCODE, ret_pc=V.find_ret(img))
        m.t2_scale = S.T2_SCALE
        V.vendor_stubs(m, hdmi)
        state_addr = 0xE22E
    else:
        m = S.Machine(img, map_path, "trace-" + tag, log, [*devs, lg])
        m.t2_scale = S.T2_SCALE
        S.video_stubs(m, hdmi)
        state_addr = m.addr("g_stModeInfo")
    for a, d in taken.items():                                      # source-model addresses: log, then the model
        if a in ranges:
            lg.chain[a] = d
            m.hook[("write", a)] = lg
    st = StateTap(tr, state_addr)
    m.hook[("write", state_addr)] = st
    m.s.send(f"break xram w 0x{state_addr:x}")
    for n in CALLS:
        if "_" + n in m.sym:
            m.stub(n, lambda m_, r, n=n: tr.call(m_, n))
    done = 0
    while done < max_instr and tr.done_at is None:
        m.run(1_000_000); done += 1_000_000
    if tr.done_at is not None:
        m.run(tail)
    out = ROOT / f"tmp/logs/trace_{tag}.tsv"
    out.write_text("seq\tinstr\tfw_ms\tbank\tpc\tfunc\tkind\taddr\treg\tidx\tvalue\n" + "\n".join("\t".join(map(str, r)) for r in tr.rows) + "\n")
    st_rows = [r for r in tr.rows if r[6] == "STATE"]
    print(f"{tag}: {len(tr.rows)} rows -> {out.relative_to(ROOT)}; ACTIVE at instr {tr.done_at}; mode states: "
          + " ".join(f"{r[1]}:{r[8]}" for r in st_rows if r[1] > 0)[:600])
    m.close()
    return 0 if tr.done_at else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=("vendor", "ours"))
    ap.add_argument("img", nargs="?")
    ap.add_argument("map", nargs="?")
    ap.add_argument("--mode", default="2160p60", choices=sorted(S.HdmiInput.MODES))
    ap.add_argument("--max-instr", type=int, default=150_000_000)
    ap.add_argument("--tail", type=int, default=2_000_000)
    ap.add_argument("--tag")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    if a.kind == "vendor":
        import fw_sim_vendor as V
        img = Path(a.img) if a.img else V.VENDOR_IMG
        return run("vendor", img, None, a.mode, a.max_instr, a.tail, a.tag or f"vendor_{a.mode}")
    b = Path(a.img)
    return run("ours", b, Path(a.map), a.mode, a.max_instr, a.tail, a.tag or f"{b.stem}_{a.mode}")


if __name__ == "__main__":
    sys.exit(main())
