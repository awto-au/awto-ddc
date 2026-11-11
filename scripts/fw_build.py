#!/usr/bin/env python3
"""Build the RL6449 firmware image with SDCC: port -> EDID -> asm -> RAM overlay -> banks -> link -> bin.

usage: fw_build.py --serial AWT26110003 [--skip-compile] [--common 0x5000]
  output: tmp/fw/<serial>/fw.ihx, fw.map, fw.bin (bank k at file offset k*64 KiB), build.json
  --skip-compile  reuse tmp/sdcc-port/asm (skip port/EDID/compile)
  --layout FILE   sticky flash layout (fw/bank_layout.tsv, scripts/sdcc_layout.py): fixed slot per chunk, reused
                  between builds so a small edit rewrites few 4 KiB sectors (#12); missing/empty file = create it
  --src-patch F   JSON [{file, old, new}] applied to tmp/sdcc-port/src after `port` (measurement edits, no SDK change)
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
import msg_table as MT  # noqa: E402

ROOT = repo_root()
LOG = None
XRAM = (0xD700, 0xF6B0)                                       # SDK XDATA end 0xF700 less the 48 B diag block and 32 B watchdog record (RL6449_Project.h)
EDID_RAM = [(0xE080, 0xE180), (0xE280, 0xE380), (0xE480, 0xE580), (0xE680, 0xE780)]   # Mcu.c MCU_DDCRAM_D0..D3, 256 B each
BANK = 0x10000
NBANKS = 14                                                   # banks 14-15 = data (#8)
# Step timeouts = stall guards; measured: port 15 s, compile --asm 64 s worst file (whole run ~70 s), overlay 10 s,
# bank 5 s, link 20 s (first runs 2026-11-04). 3x cold worst case per awto-dan#53.
TIMEOUT = {"port": 60, "edid": 60, "asm": 240, "overlay": 60, "isr": 60, "bank": 60, "link": 120}
LIB_UV2 = "Kernel/Scaler/RL6449_Series_Scaler/Lib/RL6449_Series_Lib.Uv2"   # Realtek ships it as a .LIB
WORK_DIR = ROOT / "tmp/sdcc-port"
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


def apply_src_patch(p: Path):
    """Measurement edits on the derived tree (tmp/sdcc-port/src); each old string must occur exactly once."""
    for e in json.loads(p.read_text()):
        f = ROOT / "tmp/sdcc-port/src" / e["file"]
        t = f.read_text(errors="replace")
        if t.count(e["old"]) != 1:
            sys.exit(f"src-patch: {e['file']}: old text found {t.count(e['old'])}x")
        f.write_text(t.replace(e["old"], e["new"]))
        log(f"src-patch applied: {e['file']}")


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


def check_layout(mp: str, pins: dict, layout: str):
    """Every pinned area sits at its slot; residual areas (vectors/HOME/GSINIT/library/XINIT) end below resid_end."""
    got, want = {}, {}                                       # the map prints area names cut to 32 chars
    for m in re.finditer(r"^((?:CH|ST)\S*)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =", mp, re.M):
        got.setdefault(m.group(1)[:32], []).append(int(m.group(2), 16))
    for n, v in pins.items():
        want.setdefault(n[:32], []).append(v)
    bad = [n for n in want if sorted(want[n]) != sorted(got.get(n, []))]
    if bad:
        sys.exit(f"layout: {len(bad)} areas not at their slot in the map: {bad[:5]}")
    end = 0
    for m in re.finditer(r"^(HOME|GSINIT\d*|GSFINAL|CSEG|CONST|XINIT)\s+([0-9A-F]{8})\s+([0-9A-F]{8})", mp, re.M):
        lo, n = int(m.group(2), 16), int(m.group(3), 16)
        if n and lo < BANK:
            end = max(end, lo + n)
    resid = int(next((l.split()[1] for l in Path(layout).read_text().splitlines() if l.startswith("#resid_end")), "0"), 0)
    log(f"layout: {len(pins)} areas at their slots; residual areas end 0x{end:x} (resid_end 0x{resid:x})")
    if end > resid:
        sys.exit(f"layout: residual areas end 0x{end:x} > resid_end 0x{resid:x}: raise --resid-end (relayout)")


def promote_layout(new: Path, tracked: Path):
    """Copy the layout sdcc_bank wrote onto the tracked file, only called after link + check_layout passed (#51.4)."""
    t = new.read_text()
    if not tracked.exists() or tracked.read_text() != t:
        tracked.write_text(t)
        log(f"layout promoted: {tracked}")


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


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--skip-compile", action="store_true")
    ap.add_argument("--common", type=lambda x: int(x, 0), default=0x5000)
    ap.add_argument("--layout", default="fw/bank_layout.tsv",
                    help="sticky layout (default: the tracked, proven one); '' = no layout, first-fit packing")
    ap.add_argument("--cluster", choices=["module", "fn"], default="",
                    help="call-graph bank placement; only valid while a layout is being created (missing/empty --layout file)")
    ap.add_argument("--cluster-weights", default="", help="passed to sdcc_bank (measured call counts, fw/cluster_weights.json)")
    ap.add_argument("--pin-common", default="_AwtoPutStr",
                    help="passed to sdcc_bank (comma list of fns forced into common; OSD string helper must remain common because callers pass bank-local literals)")
    ap.add_argument("--src-patch", default="")
    # 0xc38: the --keil-compat /0 wrappers (_divulong_keil etc.) end the library at 0xc12 (awto-sdcc#36)
    ap.add_argument("--resid-end", default="0xc38", help="passed to sdcc_bank: common bytes kept for vectors/library before "
                    "the chunk slots; a different value needs a new layout file")
    a = ap.parse_args(argv)
    if a.cluster:
        import sdcc_layout
        if not a.layout or sdcc_layout.Layout.load(ROOT / a.layout).rows:
            sys.exit(f"--cluster only applies while creating a layout: --layout {a.layout!r} is "
                     f"{'unset' if not a.layout else 'an existing layout (delete it to re-cluster)'}; nothing done")
    return a


def main() -> int:
    global LOG
    a = parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/fw_build.log").open("a")
    py = sys.executable
    log(f"byte order: {'BIG-endian (--big-endian, Keil order)' if T.BIG_ENDIAN else 'little-endian (default)'}, lib {T.LIB}")
    if not a.skip_compile:
        run("port", [py, "scripts/keil2sdcc.py", "port"])
        if a.src_patch:
            apply_src_patch(Path(a.src_patch))
        run("edid", [py, "scripts/fw_edid_tables.py", "--serial", a.serial])
        run("asm", [py, "scripts/keil2sdcc.py", "compile", "STD_FW_1P.Uv2", "--target", "RL6449_Project", "--asm"])
        run("asm", [py, "scripts/keil2sdcc.py", "compile", LIB_UV2, "--asm"])
        # #66: every policy row must still match a warning of this build (stale rows fail), every warning a row
        run("edid", [py, "scripts/warn_policy_check.py", WORK_DIR / "warnings-STD_FW_1P.txt",
                     WORK_DIR / f"warnings-{Path(LIB_UV2).stem}.txt"])
    run("asm", [py, "scripts/keil2sdcc.py", "awto"])         # clean tree + shim (#68); no-op without clean sources
    select_lib()
    run("overlay", [py, "scripts/sdcc_overlay.py", "--asm", SEL])
    run("isr", [py, "scripts/sdcc_isr_libs.py"])              # ISR-private non-reentrant lib helpers (#19)
    new_layout = ROOT / "tmp/sdcc-port/bank_layout.new.tsv"
    new_layout.unlink(missing_ok=True)                        # only this run's output may be promoted
    run("bank", [py, "scripts/sdcc_bank.py", "--common-max", hex(a.common), "--banks", NBANKS,
                 *(["--layout", a.layout, "--layout-out", new_layout] if a.layout else []),
                 *(["--cluster", a.cluster] if a.cluster else []),
                 *(["--cluster-weights", a.cluster_weights] if a.cluster_weights else []),
                 *(["--pin-common", pin] if (pin := ",".join(x for x in (a.pin_common, (ROOT / "tmp/sdcc-port/pin_common.txt").read_text().strip()
                                                                         if (ROOT / "tmp/sdcc-port/pin_common.txt").exists() else "") if x)) else []),
                 *(["--resid-end", a.resid_end] if a.resid_end else [])])
    bank_dir = ROOT / "tmp/sdcc-port/asm_bank"
    # C runtime overrides (lib % never returns on divisor 0): compile to asm, linked ahead of mcs51.lib
    # crt_mod0/crt_divulong/crt_memcpy are Keil-register (--sdcccall 3) versions only; the level-0 versions are deleted (awto-sdcc#7 C5)
    if T.SDCCCALL != "3":
        sys.exit("fw_build: the C runtime overrides (fw/sdcc/crt_*.c) need AWTO_SDCCCALL=3 (Keil registers)")
    crts = ("crt_mod0", "crt_divulong", "crt_memcpy")
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
    used = sorted({int(m) for r in rels for m in re.findall(r"^A BANK(\d+) ", r.read_text(errors="replace"), re.M)})
    pins = {}
    if a.layout:                                             # one area per chunk/stub, each pinned to its slot
        ab = json.loads((ROOT / "tmp/sdcc-port/area_bases.json").read_text())
        used, pins = ab["banks"], ab["areas"]
    xsegs = {int(m) for r in rels for m in re.findall(r"^A XSEG(\d+) ", r.read_text(errors="replace"), re.M)}
    # trunk sdld: area base = -a (asxxxx 5.50; -b gone); a base for an undefined area is an error
    wl = [] if pins else [f"-Wl-aBANK{n}=0x{n * BANK + a.common:x}" for n in used]
    wl += [f"-Wl-a{n}=0x{v:x}" for n, v in sorted(pins.items())]
    wl += [f"-Wl-aXSEG{k}=0x{hs[k][0]:x}" for k in range(1, len(hs)) if k in xsegs]
    wl += [f"-Wl-aHOME=0x{VEC_END:x}"]
    cmd = [T.tool("sdcc"), "-mmcs51", "--model-large", *T.CFLAGS_EXTRA, "--code-loc", "0", "--code-size", "0x100000",
           # --xram-size = all holes: sdld's -M summary sums every XDATA area (check_xdata checks each hole); libs: sdcc_link
           "--xram-loc", hex(hs[0][0]), "--xram-size", hex(sum(b - a for a, b in hs)), "--iram-size", "256",
           *wl, "-o", out / "fw.ihx", *rels]
    log(f"[link] {' '.join(map(str, cmd[:20]))} ... ({len(rels)} rels)")
    r, iram = sdcc_link.link(cmd, out / "fw.ihx", rels)
    LOG.write(r.stdout + r.stderr)
    undef = sorted(set(re.findall(r"Undefined Global '?(\w+)'?", r.stdout + r.stderr)))
    if r.returncode or undef:                                # undefined = resolves to 0 (#17 ar7, #18 lcall 0)
        print((r.stdout + r.stderr)[-3000:])
        sys.exit(f"[link] failed{' (undefined: ' + ', '.join(undef) + ')' if undef else ''}")
    log(f"IRAM: {iram}")
    check_xdata((out / "fw.map").read_text(errors="replace"), hs)
    if pins:
        check_layout((out / "fw.map").read_text(errors="replace"), pins, new_layout)
        promote_layout(new_layout, ROOT / a.layout)   # absolute a.layout wins in the join
    mem = parse_ihx(out / "fw.ihx")
    common_end = max((x for x in mem if x < a.common), default=0) + 1
    nb = max(max(used) + 1, MT.MSG_BANK + 1)                 # image must reach the message block (#56)
    clash = sorted(x for x in mem if MT.MSG_ADDR <= x < MT.MSG_ADDR + MT.MSG_SIZE)
    if clash:
        sys.exit(f"message table region 0x{MT.MSG_ADDR:x}+0x{MT.MSG_SIZE:x} holds code/data: first byte at 0x{clash[0]:x}")
    img = bytearray(b"\xff" * (nb * BANK))
    for k in range(nb):
        for x in range(common_end):
            if x in mem:
                img[k * BANK + x] = mem[x]
    for x, v in mem.items():                                 # banked bytes (bank 0's sit at [common, 64K))
        if x >= a.common:
            img[x] = v
    blk = MT.build(MT.rows_from_tsv((ROOT / "fw/msgids.tsv").read_text()))   # enabled ids of this build's port step
    img[MT.MSG_ADDR:MT.MSG_ADDR + len(blk)] = blk
    minfo = MT.parse(blk)
    (out / "msgtable.bin").write_bytes(blk)
    log(f"msgtable: {minfo['count']} ids, {len(blk)} B of {MT.MSG_SIZE} at 0x{MT.MSG_ADDR:x}, hash {minfo['hash']}")
    (out / "fw.bin").write_bytes(img)
    rep = {"serial": a.serial, "common_end": common_end, "common_max": a.common, "banks": used,
           "bin_bytes": len(img),
           "msgtable": {"addr": MT.MSG_ADDR, "bytes": len(blk), "ids": minfo["count"], "hash": minfo["hash"]}, "xdata_holes": [(hex(x), hex(y)) for x, y in hs], "iram": iram,
           "sdcccall": int(T.SDCCCALL), "compiler": T.stamp()}
    (out / "build.json").write_text(json.dumps(rep, indent=1))
    log(f"image {out / 'fw.bin'}: {nb} banks, common 0x{common_end:x}/0x{a.common:x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
