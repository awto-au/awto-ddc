#!/usr/bin/env python3
"""Return-value equivalence of the arith shim (#68): reference image vs mixed image, every call (awto-ddc#65).

usage: mixed_call_values.py REF.bin REF.map MIX.bin MIX.map [--modes 1080p60 2160p60] [--vectors specs/vectors/arith.tsv]
  1. Capture: run REF in fw_sim (stable HDMI source) to ACTIVE per mode; every call of ScalerComputeDwordMulDiv /
     ScalerComputeDwordPowDiv is recorded (args at entry).
  2. Replay: each captured call (deduplicated) and each spec vector row runs on REF and on MIX by direct invocation
     (args set, return address = trap, bank register set); the return values are compared with each other
     (and with the vector's expected value).
  ABI (sdcccall 1, BE image): arg 1 in A:B:DPH:DPL (MSB first), later args in <fn>_PARM_n (XDATA, BE); result in A:B:DPH:DPL.
  Exit 1 on any difference. Log: tmp/logs/mixed_call_values.log; TSV tmp/logs/mixed_call_values.tsv
"""
import argparse, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402

ROOT = S.ROOT
FNS = {"muldiv": "ScalerComputeDwordMulDiv", "shldiv": "ScalerComputeDwordPowDiv"}
CALL_RUN_INSTR = 3_000_000       # slow regime <= 20,000 cycles on the target (spec arith); 150x margin is fine for a sim that stops at the trap
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    LOG.write(line + "\n"); LOG.flush()


def parm_addrs(m, fn):
    try:
        return [m.addr(f"{fn}_PARM_2"), m.addr(f"{fn}_PARM_3")]
    except S.SimError:
        return None


def capture(binp, mapp, mode, max_instr=150_000_000):
    """Calls of both functions from reset to ACTIVE: set of (fn, a, b_or_k, c)."""
    bus = S.SimBus(binp, mapp, tag=f"mcv-cap-{mode}", video=mode, boot=False)
    m, calls = bus.m, []

    for key, fn in FNS.items():
        pa = parm_addrs(m, fn)
        if pa is None or "_" + fn not in m.sym:   # no caller in the firmware: pruned from the image
            continue
        p2, p3 = pa

        def hook(m_, r, key=key, p2=p2, p3=p3):
            a = r["acc"] << 24 | r["b"] << 16 | r["dptr"]
            b = m_.rd(p2, 4 if key == "muldiv" else 1)
            c = int.from_bytes(m_.rd(p3, 4), "big")
            calls.append((key, a, int.from_bytes(b, "big"), c))
        m.stub(fn, hook)
    used = 0
    while used < max_instr and not (bus.mode_state() == 3 and used > 0):
        m.run(1_000_000); used += 1_000_000
    m.run(2_000_000)
    m.close()
    return calls


class Invoker:
    def __init__(self, binp, mapp, tag):
        img = Path(binp).read_bytes()
        self.m = S.Machine(img, Path(mapp), tag, None, [S.FlashDev(img)])
        self.trap = self.m.sym["_main"] & 0xFFFF
        self.m.s.send(f"break 0x{self.trap:x}")
        self.m.flush()
        self.p = {k: parm_addrs(self.m, f) for k, f in FNS.items()}
        self.p = {k: v for k, v in self.p.items() if v is not None and "_" + FNS[k] in self.m.sym}
        self.call("muldiv", 1, 1, 1)               # cold CPU (no C startup run): the first call returned stale RAM (0x8000 for 0*0/1)

    def call(self, key, a, b, c):
        m, fn = self.m, FNS[key]
        v = m.sym["_" + fn]
        m.wr(0xFFFF, bytes([v >> 16 & 15]))
        m.wr(self.p[key][0], b.to_bytes(4 if key == "muldiv" else 1, "big"))
        m.wr(self.p[key][1], c.to_bytes(4, "big"))
        m.wr(0x80, bytes([self.trap & 255, self.trap >> 8]), "iram")      # return address (low, high)
        m.put("set memory sfr 0x81 0x81")                                   # SP: 2 bytes pushed
        m.put(f"set memory sfr 0x82 0x{a & 255:x}"); m.put(f"set memory sfr 0x83 0x{a >> 8 & 255:x}")
        m.put(f"set memory sfr 0xf0 0x{a >> 16 & 255:x}"); m.put(f"set memory sfr 0xe0 0x{a >> 24 & 255:x}")
        m.put(f"pc 0x{v & 0xFFFF:x}")
        m.flush()
        used = 0
        while used < CALL_RUN_INSTR:
            out = m.run(100_000); used += 100_000
            st = re.search(r"Stop at 0x([0-9a-f]+)", out)
            if st and int(st.group(1), 16) == self.trap:
                break
        else:
            raise S.SimError(f"{fn} did not return within {CALL_RUN_INSTR} instr")
        m.flush()
        info = m.cmd("info registers")
        acc, b_, dp = (int(re.search(rx, info).group(1), 16) for rx in (r"ACC= 0x([0-9a-f]{2})", r"B= 0x([0-9a-f]{2})", r"DPTR= 0x([0-9a-f]{4})"))
        s = bytes([dp & 255, dp >> 8, b_, acc])                             # DPL DPH B A
        return s[3] << 24 | s[2] << 16 | s[1] << 8 | s[0]

    def close(self):
        self.m.close()


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("ref_bin"); ap.add_argument("ref_map"); ap.add_argument("mix_bin"); ap.add_argument("mix_map")
    ap.add_argument("--modes", nargs="+", default=["1080p60", "2160p60"])
    ap.add_argument("--vectors", default=str(ROOT / "specs/vectors/arith.tsv"))
    ap.add_argument("--vector-step", type=int, default=1, help="use every Nth vector row")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/mixed_call_values.log").open("a")
    work, expect = {}, {}
    for mode in a.modes:
        calls = capture(a.ref_bin, a.ref_map, mode)
        log(f"capture {mode}: {len(calls)} calls, {len(set(calls))} distinct "
            f"(muldiv {sum(c[0] == 'muldiv' for c in calls)}, shldiv {sum(c[0] == 'shldiv' for c in calls)})")
        for c in calls:
            work.setdefault(c, f"call:{mode}")
    rows = [l.split("\t") for l in Path(a.vectors).read_text().splitlines() if l and not l.startswith("#")]
    for r in rows[::a.vector_step]:
        key = (r[0], int(r[1], 16), int(r[2], 16), int(r[3], 16))
        work.setdefault(key, "vector")
        expect[key] = int(r[4], 16)
    ref, mix = Invoker(a.ref_bin, a.ref_map, "mcv-ref"), Invoker(a.mix_bin, a.mix_map, "mcv-mix")
    gone = {k for k in FNS if k not in ref.p or k not in mix.p}
    if gone:
        log(f"not in both images (no caller, pruned): {sorted(gone)}; their rows are skipped")
    work = {k: v for k, v in work.items() if k[0] not in gone}
    bad, n_exp = [], 0
    out = (ROOT / "tmp/logs/mixed_call_values.tsv").open("w")
    out.write("fn\ta\tb_or_k\tc\tref\tmixed\texpected\tsource\n")
    for i, (key, src) in enumerate(sorted(work.items())):
        r, x = ref.call(*key), mix.call(*key)
        e = expect.get(key)
        out.write(f"{key[0]}\t{key[1]:08x}\t{key[2]:08x}\t{key[3]:08x}\t{r:08x}\t{x:08x}\t{'' if e is None else f'{e:08x}'}\t{src}\n")
        if r != x or (e is not None and x != e):
            bad.append((key, r, x, e))
        n_exp += e is not None
        if i % 200 == 0:
            log(f"progress {i}/{len(work)} differences {len(bad)}")
    out.close(); ref.close(); mix.close()
    log(f"RESULT {len(work)} calls ({sum(1 for s in work.values() if s != 'vector')} captured, {n_exp} with spec expectation): "
        f"{len(bad)} differences")
    for key, r, x, e in bad[:20]:
        log(f"DIFF {key[0]} a={key[1]:08x} b={key[2]:08x} c={key[3]:08x} ref={r:08x} mixed={x:08x} expected={e}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
