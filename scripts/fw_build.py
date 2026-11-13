#!/usr/bin/env python3
"""Build the RL6449 firmware image with SDCC: port -> EDID -> asm -> RAM overlay -> banks -> link -> bin.

usage: fw_build.py --serial AWT26110003 [--skip-compile] [--common 0x5000]
  output: tmp/fw/<serial>/fw.ihx, fw.map, fw.bin (bank k at file offset k*64 KiB), build.json
  --skip-compile  reuse tmp/sdcc-port/asm (skip port/EDID/compile)
Memory (SDK + board, awto-ddc#8):
- XDATA window 0xD700-0xF6FF; fixed DDC RAM for D0-D3 at E080/E280/E480/E680 (+256 B each) splits it
  into holes; module XSEG areas are distributed over the holes (sdld cannot split one area).
- Code: common [0, COMMON) copied into every bank; BANK<n> linked at n*0x10000 + COMMON.
Log: ./tmp/logs/fw_build.log
"""
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402
import sdcc_link  # noqa: E402
import sdcc_tools as T  # noqa: E402

ROOT = repo_root()
LOG = None
XRAM = (0xD700, 0xF6B0)                                       # SDK XDATA end 0xF700 less safe block 0xF6B0 (32 B) + diag 0xF6D0 (48 B)
EDID_RAM = [(0xE080, 0xE180), (0xE280, 0xE380), (0xE480, 0xE580), (0xE680, 0xE780)]   # Mcu.c MCU_DDCRAM_D0..D3, 256 B each
BANK = 0x10000
NBANKS = 14                                                   # banks 14-15 = data (#8)
# Step timeouts = stall guards; measured: port 15 s, compile --asm 64 s worst file (whole run ~70 s), overlay 10 s,
# bank 5 s, link 20 s (first runs 2026-11-04). 3x cold worst case per awto-dan#53.
TIMEOUT = {"port": 60, "edid": 60, "asm": 240, "overlay": 60, "isr": 60, "bank": 60, "link": 120}
LIB_UV2 = "Kernel/Scaler/RL6449_Series_Scaler/Lib/RL6449_Series_Lib.Uv2"   # Realtek ships it as a .LIB
ASM = ROOT / "tmp/sdcc-port/asm"
SEL = ROOT / "tmp/sdcc-port/asm_sel"


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


def run(step, cmd):
    log(f"[{step}] {' '.join(map(str, cmd))}")
    env = dict(os.environ, PYTHONHASHSEED="0")              # set iteration order -> reproducible bank packing
    r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=TIMEOUT[step], cwd=ROOT, env=env)
    LOG.write(r.stdout + r.stderr); LOG.flush()
    if r.returncode:
        print((r.stdout + r.stderr)[-3000:])
        sys.exit(f"[{step}] failed rc={r.returncode}")
    return r.stdout


def holes():
    h, cur = [], XRAM[0]
    for a, b in sorted(EDID_RAM):
        if a > cur:
            h.append((cur, a))
        cur = max(cur, b)
    if cur < XRAM[1]:
        h.append((cur, XRAM[1]))
    return h


def area_sizes(rel: Path) -> dict:
    s = {}
    for m in re.finditer(r"^A (\w+) size (\w+)", rel.read_text(errors="replace"), re.M):
        s[m.group(1)] = s.get(m.group(1), 0) + int(m.group(2), 16)
    return s


LIB_XSEG_MARGIN = 64      # SDCC lib XSEG (e.g. _mullong/_divulong params); post-link check catches overrun


def check_xdata(mp: str, hs):
    """Every XDATA area must lie inside one hole (EDID DDC RAM between holes is hardware-owned)."""
    bad = []
    for m in re.finditer(r"^(X\w*SEG\d*)\s+([0-9A-F]{8})\s+([0-9A-F]{8})", mp, re.M):
        a, n = int(m.group(2), 16), int(m.group(3), 16)
        if n and not any(lo <= a and a + n <= hi for lo, hi in hs):
            bad.append(f"{m.group(1)} 0x{a:04x}+{n}")
    if bad:
        sys.exit(f"XDATA outside holes {[(hex(a), hex(b)) for a, b in hs]}: {sorted(set(bad))}")


def split_xseg(asm_dir: Path):
    """Rename each module's XSEG to XSEG<k> so each hole gets a set of modules (first fit, largest first)."""
    hs = sorted(holes(), key=lambda h: h[0] - h[1])           # largest hole first = default XSEG/XISEG
    free = [b - a for a, b in hs]
    rels = sorted(asm_dir.glob("*.rel"))
    sizes = {r: area_sizes(r).get("XSEG", 0) for r in rels}
    # hole 0 also takes XISEG and SDCC library XSEG (helper params, not in these rels): reserve both
    free[0] -= sum(area_sizes(r).get("XISEG", 0) for r in rels) + LIB_XSEG_MARGIN
    assign = {}
    for r in sorted(rels, key=lambda r: -sizes[r]):
        if not sizes[r]:
            continue
        k = next((i for i, f in enumerate(free) if f >= sizes[r]), None)
        if k is None:
            sys.exit(f"XDATA does not fit holes {[hex(a) for a, _ in hs]}: free={free}, need {sizes[r]} for {r.stem}")
        free[k] -= sizes[r]; assign[r] = k
    moved = []
    for r, k in assign.items():
        if k:
            asm = r.with_suffix(".asm")
            asm.write_text(asm.read_text().replace("\t.area XSEG    (XDATA)", f"\t.area XSEG{k}   (XDATA)"))
            moved.append(asm)
    log(f"XDATA holes {[(hex(a), hex(b)) for a, b in hs]}; free after placement {free}")
    return hs, moved


def select_lib():
    """Project asm + only the Lib modules needed to resolve its globals (like a linker pulling from a .LIB)."""
    import shutil
    if SEL.exists():
        shutil.rmtree(SEL)
    SEL.mkdir(parents=True)
    proj = sorted(ASM.glob("*.asm"))
    lib = sorted((ASM / Path(LIB_UV2).parent).rglob("*.asm"))
    globl = lambda t: set(re.findall(r"^\s+\.globl\s+(\w+)", t, re.M))
    defs = lambda t: globl(t) & set(re.findall(r"^(\w+)::?\s*$", t, re.M))     # SDCC: `_f:` + .globl
    refs = lambda t: globl(t) - defs(t)
    lib_def = {}
    for p in lib:
        for d in defs(p.read_text(errors="replace")):
            lib_def.setdefault(d, p)
    have, need, take = set(), set(), []
    for p in proj:
        t = p.read_text(errors="replace"); have |= defs(t); need |= refs(t)
    work = sorted(need - have)
    while work:
        x = work.pop()
        p = lib_def.get(x)
        if p is None or p in take:
            continue
        take.append(p)
        t = p.read_text(errors="replace"); have |= defs(t)
        work += sorted(refs(t) - have)
    for p in proj + take:
        if (SEL / p.name).exists():
            sys.exit(f"module name clash in selection: {p.name}")
        shutil.copy2(p, SEL / p.name)
    log(f"lib: {len(take)}/{len(lib)} modules selected: {', '.join(q.stem for q in take)}")


VEC_END = 0x53                                                # vectors 0..9 (0x03 + 8n, 3 B each)


def write_vectors(bank_dir: Path):
    """SDCC emits ISR vectors only in main's file when the ISR prototypes are visible there; SysMain.c does not
    see them, so the first image had no vectors (hardware died at the first interrupt, #8). Generate them:
    reset + ljmp per ISR found in the banked asm, reti elsewhere; HOME is based after the table."""
    isr = {}
    for asm in bank_dir.glob("*.asm"):
        for name, n in re.findall(r"^;\s+\S+:\d+: void (\w+)\s*\(void\)\s*__interrupt\s*\(\s*(\d+)\s*\)", asm.read_text(errors="replace"), re.M):
            isr[int(n)] = "_" + name
    lines = ["\t.module awto_vectors", "\t.globl __sdcc_gsinit_startup"] + [f"\t.globl {v}" for v in isr.values()]
    lines += ["\t.area VECTORS (ABS,CODE)", "\t.org 0x0000", "\tljmp __sdcc_gsinit_startup"]
    for n in range((VEC_END - 3) // 8):
        lines += [f"\t.org 0x{3 + 8 * n:04x}", f"\tljmp {isr[n]}" if n in isr else "\treti"]
    (bank_dir / "awto_vectors.asm").write_text("\n".join(lines) + "\n")
    run("bank", [T.tool("sdas8051"), "-plosgffw", bank_dir / "awto_vectors.rel", bank_dir / "awto_vectors.asm"])
    log(f"vectors: { {hex(3 + 8 * n): v for n, v in sorted(isr.items())} }")


def parse_ihx(p: Path) -> dict:
    mem, base = {}, 0
    for line in p.read_text().split():
        n, addr, typ = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
        data = bytes.fromhex(line[9:9 + 2 * n])
        if typ == 0:
            for i, b in enumerate(data):
                mem[base + addr + i] = b
        elif typ == 4:
            base = int.from_bytes(data, "big") << 16
        elif typ == 2:
            base = int.from_bytes(data, "big") << 4
    return mem


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--skip-compile", action="store_true")
    ap.add_argument("--common", type=lambda x: int(x, 0), default=0x5000)
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/fw_build.log").open("a")
    py = sys.executable
    if "--dual-dptr" in T.CFLAGS_EXTRA:
        from fw_dual_dptr_check import check_compiler
        try:
            check_compiler(T.tool("sdcc"), T.CFLAGS_EXTRA)
        except ValueError as e:
            sys.exit(str(e))
    log(f"byte order: {'BIG-endian (--big-endian, Keil order)' if T.BIG_ENDIAN else 'little-endian (default)'}, lib {T.LIB}")
    if not a.skip_compile:
        run("port", [py, "scripts/keil2sdcc.py", "port"])
        run("edid", [py, "scripts/fw_edid_tables.py", "--serial", a.serial])
        run("asm", [py, "scripts/keil2sdcc.py", "compile", "STD_FW_1P.Uv2", "--target", "RL6449_Project", "--asm"])
        run("asm", [py, "scripts/keil2sdcc.py", "compile", LIB_UV2, "--asm"])
    select_lib()
    run("overlay", [py, "scripts/sdcc_overlay.py", "--asm", SEL])
    run("isr", [py, "scripts/sdcc_isr_libs.py"])              # ISR-private non-reentrant lib helpers (#19)
    run("bank", [py, "scripts/sdcc_bank.py", "--common-max", hex(a.common), "--banks", NBANKS])
    bank_dir = ROOT / "tmp/sdcc-port/asm_bank"
    # C runtime overrides (lib % never returns on divisor 0): compile to asm, linked ahead of mcs51.lib
    # crt_memcpy reads its PARMs little-endian: BE builds keep the library's BE memcpy (#24, #15)
    crts = ("crt_mod0", "crt_divulong") + (() if T.BIG_ENDIAN else ("crt_memcpy",))
    for c in crts:
        run("bank", [T.tool("sdcc"), "-mmcs51", "--model-large", *T.CFLAGS_EXTRA, "-S", "-o", bank_dir / f"{c}.asm",
                     ROOT / f"fw/sdcc/{c}.c"])
    for extra in (ROOT / "fw/sdcc/bank.asm", ROOT / "fw/sdcc/crt_xinit.asm", ROOT / "fw/sdcc/crt_rtd_startup.asm",
                  *(bank_dir / f"{c}.asm" for c in crts), ROOT / "tmp/sdcc-port/asm_ovl/__ovl.asm",
                  *sorted((ROOT / "tmp/sdcc-port/isr_libs").glob("*_isr*.asm"))):
        (bank_dir / extra.name).write_text(extra.read_text())
        run("bank", [T.tool("sdas8051"), "-plosgffw", bank_dir / extra.with_suffix(".rel").name, bank_dir / extra.name])
    write_vectors(bank_dir)
    hs, moved = split_xseg(bank_dir)
    if len(hs) - 1 > 4:                                      # crt_xinit.asm declares/clears XSEG1..4 only
        sys.exit(f"{len(hs)} XDATA holes: extend XSEG1..4 in fw/sdcc/crt_xinit.asm")
    for asm in moved:                                        # re-assemble modules whose XSEG was renamed
        run("bank", [T.tool("sdas8051"), "-plosgffw", asm.with_suffix(".rel"), asm])
    out = ROOT / "tmp/fw" / a.serial
    out.mkdir(parents=True, exist_ok=True)
    rels = sorted(bank_dir.glob("*.rel"))
    if "--dual-dptr" in T.CFLAGS_EXTRA:
        from fw_dual_dptr_check import check_link_inputs
        try:
            checked = check_link_inputs(rels)
        except ValueError as e:
            sys.exit(f"dual-DPTR ISR check failed:\n{e}")
        for handler in checked:
            log(f"dual-DPTR ISR: {handler}")
    used = sorted({int(m) for r in rels for m in re.findall(r"^A BANK(\d+) ", r.read_text(errors="replace"), re.M)})
    xsegs = {int(m) for r in rels for m in re.findall(r"^A XSEG(\d+) ", r.read_text(errors="replace"), re.M)}
    # trunk sdld: area base = -a (asxxxx 5.50; -b gone); a base for an undefined area is an error
    wl = [f"-Wl-aBANK{n}=0x{n * BANK + a.common:x}" for n in used]
    wl += [f"-Wl-aXSEG{k}=0x{hs[k][0]:x}" for k in range(1, len(hs)) if k in xsegs]
    wl += [f"-Wl-aHOME=0x{VEC_END:x}"]
    cmd = [T.tool("sdcc"), "-mmcs51", "--model-large", *T.CFLAGS_EXTRA, "--code-loc", "0", "--code-size", "0x100000",
           "--xram-loc", hex(hs[0][0]), "--xram-size", hex(hs[0][1] - hs[0][0]), "--iram-size", "256",
           f"-L{T.LIB}", *wl, "-o", out / "fw.ihx", *rels]
    log(f"[link] {' '.join(map(str, cmd[:20]))} ... ({len(rels)} rels)")
    r, iram = sdcc_link.link(cmd, out / "fw.ihx", rels)
    LOG.write(r.stdout + r.stderr)
    undef = sorted(set(re.findall(r"Undefined Global '?(\w+)'?", r.stdout + r.stderr)))
    if r.returncode or undef:                                # undefined = resolves to 0 (#17 ar7, #18 lcall 0)
        print((r.stdout + r.stderr)[-3000:])
        sys.exit(f"[link] failed{' (undefined: ' + ', '.join(undef) + ')' if undef else ''}")
    log(f"IRAM: {iram}")
    check_xdata((out / "fw.map").read_text(errors="replace"), hs)
    mem = parse_ihx(out / "fw.ihx")
    common_end = max((x for x in mem if x < a.common), default=0) + 1
    nb = max(used) + 1
    img = bytearray(b"\xff" * (nb * BANK))
    for k in range(nb):
        for x in range(common_end):
            if x in mem:
                img[k * BANK + x] = mem[x]
    for x, v in mem.items():                                 # banked bytes (bank 0's sit at [common, 64K))
        if x >= a.common:
            img[x] = v
    (out / "fw.bin").write_bytes(img)
    rep = {"serial": a.serial, "common_end": common_end, "common_max": a.common, "banks": used,
           "bin_bytes": len(img), "xdata_holes": [(hex(x), hex(y)) for x, y in hs], "iram": iram}
    (out / "build.json").write_text(json.dumps(rep, indent=1))
    log(f"image {out / 'fw.bin'}: {nb} banks, common 0x{common_end:x}/0x{a.common:x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
