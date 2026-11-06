#!/usr/bin/env python3
"""Register-WRITE trace from RESET to ACTIVE (4K60 or other mode) in the fw_sim model, vendor image or ours (#26).

usage: fw_sim_trace.py vendor [IMG] [--mode 2160p60]            vendor Keil image, names from re/jxc-4k (fw_sim_vendor)
       fw_sim_trace.py ours BIN MAP [--mode 2160p60]            our SDCC image
  Runs the image with a stable HDMI source on D2 (same register models for both) from reset until the mode state is ACTIVE (3)
  after DISPLAY_SETTING (2) (+ --tail instr). Logs EVERY write to the scaler/MCU register space (all regdb pages, plus the
  constant-address MOVX writes found in the image; also those the source models handle), SFR writes (ports/IE/IP/PCON/..),
  mode-state changes and calls of the M-domain / FRC / double-buffer / VGIP functions present in the image.
  Indexed ports (reg_type 2/3/6 in the regdb: 2A/2B display format, 30/31 FIFO window, 33/34 SF, DPCD, SCDC, ...) are
  decoded: idx = value of the port's address register(s) at the data write (+N = Nth data write since, auto-increment).
  TSV: seq instr fw_ms bank pc func+off kind addr reg idx value phase   (kind W | SFR | CALL | STATE)
  phase = boot (INITIAL/POWER_OFF) | search | ds (DISPLAY_SETTING) | active | other; fw_ms = instr / 12.6 k (T2_SCALE = 3).
Log: tmp/logs/trace_<tag>.tsv.gz (+ tmp/logs/fw_sim_trace_<tag>.log)
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import fw_regs  # noqa: E402

ROOT = S.ROOT
RAM = range(0xD700, 0xF700)                  # firmware XDATA RAM (fw_sim.regdb_cells)
# data reg -> address reg(s) (high..low), as scripts/rtd_reg_dump.PORT_ADDR plus the ports it skips
PORTS = {0x0025: (0x24,), 0x002B: (0x2A,), 0x0031: (0x30,), 0x0034: (0x33,), 0x005D: (0x5C,), 0x0061: (0x60,), 0x0065: (0x64,),
         0x008E: (0x8D,), 0x07CF: (0x7CE,), 0x07D3: (0x7D2,), 0x15A4: (0x15A3,), 0x2AAD: (0x2AAC,), 0x2AFC: (0x2AFB,),
         0x4025: (0x4024,), 0x68AD: (0x68AC,), 0x68FC: (0x68FB,), 0x713A: (0x7139,), 0x723A: (0x7239,), 0x71CA: (0x71C9,),
         0x72CA: (0x72C9,), 0xB7C4: (0xB7C1, 0xB7C2, 0xB7C3), 0xBAC4: (0xBAC1, 0xBAC2, 0xBAC3), 0x0069: (0x68,), 0x006D: (0x6C,)}
ADDR_REGS = {a: d for d, al in PORTS.items() for a in al}
SFR_WATCH = (0x80, 0x90, 0xA0, 0xB0, 0x87, 0xA8, 0xB8, 0x98, 0x99, 0xC8, 0x88, 0x89)
SFR_NAMES = {0x80: "P0", 0x90: "P1", 0xA0: "P2", 0xB0: "P3", 0x87: "PCON", 0xA8: "IE", 0xB8: "IP", 0x98: "SCON", 0x99: "SBUF", 0xC8: "T2CON", 0x88: "TCON", 0x89: "TMOD"}
PHASE = {"INITIAL": "boot", "POWER_OFF": "boot", "SEARCH": "search", "DISPLAY_SETTING": "ds", "ACTIVE": "active"}
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

    def on_swrite(self, m, a):
        self.tr.sfr(m, a)


class StateTap(S.Dev):
    def __init__(self, tr, a):
        self.tr, self.writes = tr, (a,)

    def on_write(self, m, a):
        self.tr.state(m, m.rd(a)[0])


class Trace:
    def __init__(self, tag, names):
        self.rows, self.tag, self.names, self.idx = [], tag, names, {}
        self.phase, self.nwr = "boot", {}
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
        if kind == "W" and addr in PORTS:
            base = int.from_bytes(bytes(self.idx.get(x, 0) for x in PORTS[addr]), "big")
            n = self.nwr.get(addr, 0)
            idx = f"{base:02x}" + (f"+{n}" if n else "")
            self.nwr[addr] = n + 1
        self.rows.append((len(self.rows), m.instr, round(m.instr / TICKS_MS, 1), bank, f"{pc:04x}", fo, kind, f"{addr:04x}", reg, idx, f"{val:02x}", self.phase))

    def write(self, m, a):
        v = m.rd(a)[0]
        if a in ADDR_REGS:
            self.idx[a] = v
            self.nwr[ADDR_REGS[a]] = 0
        self.add(m, "W", a, v)

    def sfr(self, m, a):
        self.add(m, "SFR", a, m.rd(a, 1, "sfr")[0], SFR_NAMES.get(a, f"SFR_{a:02X}"))

    def state(self, m, v):
        nm = S.MODE_NAMES[v & 0x1F] if (v & 0x1F) < len(S.MODE_NAMES) else "?"
        self.phase = PHASE.get(nm, "other") if not (nm == "POWER_OFF" and self.phase != "boot") else "other"
        self.add(m, "STATE", 0, v, nm)
        if (v & 0x1F) == 2:
            self.seen_ds = True
        if (v & 0x1F) == 3 and self.seen_ds and self.done_at is None:
            self.done_at = m.instr
            m.request_stop()

    def call(self, m, name):
        self.add(m, "CALL", 0, 0, name)


def reg_space(img: bytes) -> set[int]:
    """XDATA addresses to tap: every regdb register with a writable field (outside firmware RAM) + constant-address MOVX
    writes found in the image + indexed-port registers. ucsim takes at most ~8 k event breakpoints (more hangs it), so
    read-only registers are not tapped. The bank register 0xFFFF is the banker's."""
    import csv, gzip
    s = set()
    with gzip.open(ROOT / "re/regdb/RTD2795T-CG.tsv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["kind"] == "FIELD" and r["address"].startswith("0x") and r["access"] not in ("R", "RO"):
                s.add(int(r["address"], 16))
    s |= set(fw_regs.candidates(img)[1]) | set(PORTS) | set(ADDR_REGS)
    s = {a for a in s if a not in RAM and a != 0xFFFF and a < 0x10000}
    assert len(s) < 8000, len(s)
    return s


def run(kind: str, img_path: Path, map_path: Path | None, mode: str, max_instr: int, tail: int, tag: str):
    img = img_path.read_bytes()
    names = fw_regs.names()
    import csv, gzip
    with gzip.open(ROOT / "re/regdb/RTD2795T-CG.tsv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["kind"] == "REG" and r["address"].startswith("0x"):
                names[int(r["address"], 16)] = f"P{int(r['address'], 16) >> 8:X}_{int(r['address'], 16) & 255:02X} {r['register']}"
    tr = Trace(tag, names)
    log = (ROOT / f"tmp/logs/fw_sim_trace_{tag}.log").open("w", buffering=1)
    devs, hdmi = S.video_devs(img, mode)
    taken = {a: d for d in devs for a in d.writes}
    ranges = reg_space(img)
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
    for a in SFR_WATCH:
        m.s.send(f"break sfr w 0x{a:x}")
        m.hook[("swrite", a)] = lg
    for n in CALLS:
        if "_" + n in m.sym:
            m.stub(n, lambda m_, r, n=n: tr.call(m_, n))
    done = 0
    while done < max_instr and tr.done_at is None:
        m.run(1_000_000); done += 1_000_000
    if tr.done_at is not None:
        m.run(tail)
    import gzip
    out = ROOT / f"tmp/logs/trace_{tag}.tsv.gz"
    with gzip.open(out, "wt") as f:
        f.write("seq\tinstr\tfw_ms\tbank\tpc\tfunc\tkind\taddr\treg\tidx\tvalue\tphase\n" + "\n".join("\t".join(map(str, r)) for r in tr.rows) + "\n")
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
