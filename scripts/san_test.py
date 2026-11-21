#!/usr/bin/env python3
"""sdcc_san self-test: builds fw/sansim/*.c with sdcc, runs each on the -DSDCC_SAN core, checks the findings (docs/sanitizer.md).

usage: san_test.py [name ...]      exit 0 only if every case passes
- Image: plain sdcc build (--model-large, --xram-loc 0xE000 = inside the sanitizer's XDATA pool 0xD000..0xF7FF), 8052 timing, T0 ISR.
- Run: RUN_INSTR instructions per case (T0 reloads 0xFF00: an IRQ about every 256 cycles).
Log: tmp/logs/san_test.log; scratch: tmp/scratch/san/<name>
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ["AWTO_SIM_SAN"] = str(HERE.parent / "tmp/scratch/san")
import fastmachine as FM
import sdcc_san
import sdcc_tools as T

ROOT = HERE.parent
SRC = ROOT / "fw/sansim"
WORK = ROOT / "tmp/scratch/san"
RUN_INSTR = 400_000      # ~1500 IRQs at one per ~256 cycles; enough for every interleave below, < 1 s per case
BUILD_TMO = 60           # sdcc compile+link of a 15-line file: < 2 s; 60 s = host-process stall limit

# case -> list of (class, symbol, level) that must be present, and (class, symbol) that must be absent
CASES = {
    "a_conflict": ([("A-conflict", "_g_flag", "did")], [("A-conflict", "_g_guarded")]),
    "b_lost": ([("B-lost-update", "_g_cnt", "did")], []),
    "b_could": ([("B-lost-update", "_g_cnt", "could")], [("B-lost-update", "_g_cnt", "did")]),
    "c_torn": ([("C-torn", "_g_v", "did")], []),
    "d_clobber": ([("D-clobber", "_g_scratch", "did")], []),
    "e_guarded": ([], [("A-conflict", "_g_cnt"), ("B-lost-update", "_g_cnt"), ("B-lost-update", "_g_two"), ("C-torn", "_g_two"), ("D-clobber", "_g_two")]),
}


def ihx_bin(p: Path) -> bytes:
    mem = {}
    for ln in p.read_text().splitlines():
        if ln.startswith(":") and ln[7:9] == "00":
            n, a = int(ln[1:3], 16), int(ln[3:7], 16)
            for i in range(n):
                mem[a + i] = int(ln[9 + 2 * i:11 + 2 * i], 16)
    out = bytearray(b"\xFF" * (max(mem) + 1))
    for a, v in mem.items():
        out[a] = v
    return bytes(out)


class Rig:
    """The slice of FastMachine that sdcc_san needs (a plain image has no bank stubs, so FastMachine itself does not fit)."""

    def __init__(self, img, map_text, tag):
        import fw_sim as S
        self.core, self.map_text, self.tag = FM.Core(img), map_text, tag
        self.sym, self.where = S.parse_map(map_text, img, 1)
        self.core.reset()
        self.core.iram[:] = FM.ucsim_iram()
        self.core.san_enable()
        av, an = sdcc_san.xdata_syms(map_text)
        self.sym_data = lambda: dict(zip(an, av))


def build(name: str) -> Path:
    w = WORK / name
    w.mkdir(parents=True, exist_ok=True)
    ihx = w / "out.ihx"
    ihx.unlink(missing_ok=True)
    r = subprocess.run([T.tool("sdcc"), "-mmcs51", "--model-large", "--std-sdcc11", "--opt-code-size", "--xram-loc", "0xE000", *T.CFLAGS_EXTRA,
                        f"-L{T.LIB}", "-o", str(ihx), str(SRC / f"{name}.c")], capture_output=True, text=True, timeout=BUILD_TMO, check=False)
    if r.returncode or not ihx.exists():
        sys.exit(f"{name}: build failed\n{r.stdout[-800:]}{r.stderr[-800:]}")
    return ihx


def one(name: str, log) -> bool:
    want, absent = CASES[name]
    ihx = build(name)
    rig = Rig(ihx_bin(ihx), ihx.with_suffix(".map").read_text(errors="replace"), name)
    rig.core.run(RUN_INSTR)
    rows = sdcc_san.finalise(rig, None)
    sdcc_san.write(rows, WORK / f"{name}.san.tsv")
    ok = True
    for cls, sym, lvl in want:
        hit = [r for r in rows if r["cls"] == cls and r["symbol"].lstrip("~").split("+")[0] == sym and r["level"] == lvl]
        log.write(f"{name}: want {cls} {sym} {lvl}: {'ok' if hit else 'MISSING'}\n")
        ok &= bool(hit)
    for cls, sym, *lvl in absent:
        hit = [r for r in rows if r["cls"] == cls and r["symbol"].lstrip("~").split("+")[0] == sym and (not lvl or r["level"] == lvl[0])]
        log.write(f"{name}: absent {cls} {sym} {lvl}: {'ok' if not hit else 'UNEXPECTED ' + str(hit[0])}\n")
        ok &= not hit
    log.write(f"{name}: irqs={rig.core.p.nirq} instr={rig.core.p.instr} rows={len(rows)}\n")
    print(f"{'PASS' if ok else 'FAIL'} {name} (irqs {rig.core.p.nirq}, {len(rows)} findings)", flush=True)
    return ok


def main() -> int:
    names = sys.argv[1:] or list(CASES)
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    with (ROOT / "tmp/logs/san_test.log").open("w", buffering=1) as log:
        res = [one(n, log) for n in names]
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
