#!/usr/bin/env python3
"""Watch front-panel key presses live by polling the scaler's ADC key registers over DDC/ISP.

usage: rtd_keywatch.py <bus> [--halt] [--secs N]
       rtd_keywatch.py <bus> --log --map MAP [--serial S] [--secs N] [--open] [--close] [--once] [--history]   (#39: firmware key log, no screen needed)
  --log: reads g_stAwtoKey (map symbol _g_stAwtoKey, 144 B) over debug slave 0x35, read-only except --open/--close (test cmd 0x41/0x42
         = key test screen). Prints the live raw A0/A1/P3.0 when they change and every new press-log entry (raw values, decoded key,
         key message, injected mark, firmware tick ms). Needs dbg_xdata / rtd_i2c_bridge / i2cbus (main tree: AWTO_DDC_MAIN).
Default: MCU left RUNNING; reads scaler regs via F4/F5 (index/data) at ISP 0x4A and decodes the
key bands from buttons.md. Press each physical button; the decoded key is printed when it changes.
--halt: enter ISP (stops MCU) first — only if the running read returns nothing (then presses may not
register, since the halted MCU is not scanning). --secs: watch duration (default 25).
Reads only; no writes except the F4 index byte. Bands: fw/awto/inputs.tsv key0 / key1 rows (the firmware's table, lo <= ADC < hi);
key masks: RL6449_Project.h AWTO_KM_<name>.
Log: ./tmp/logs/rtd_keywatch.log
"""
import os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
ADC_REG = {"key0": 0xFF09, "key1": 0xFF0A}           # ladder A0 / A1 result cells (regdb ADC_A0 / ADC_A1)


def load_bands(root=ROOT):
    """(mask, source reg, lo, hi, name) per key row of fw/awto/inputs.tsv; mask = AWTO_KM_<name> (#132 q9: one table)."""
    import re
    hdr = (root / "fw/sdk/Project/Header/RL6449_Project.h").read_text(errors="replace")
    km = {m.group(1): int(m.group(2), 0) for m in re.finditer(r"#define\s+AWTO_KM_(\w+)\s+(0x[0-9A-Fa-f]+)", hdr)}
    out = []
    for ln in (root / "fw/awto/inputs.tsv").read_text().splitlines():
        f = ln.split("\t")
        if ln.startswith("#") or len(f) < 6 or f[3] not in ADC_REG:
            continue
        out.append((km[f[0]], ADC_REG[f[3]], int(f[4], 0), int(f[5], 0), f[0]))
    return out


BANDS = load_bands()


def decode(a0, a1):
    hits = []
    for mask, reg, lo, hi, label in BANDS:
        v = a0 if reg == 0xFF09 else a1
        if lo <= v < hi:
            hits.append(label)
    return hits


SDK_NAMES = [(b[0], b[4]) for b in BANDS] + [(0x01, "POWER")]    # inputs.tsv order = front left to right, then POWER
MSG_NAMES = {0: "AUTO", 1: "UP", 2: "DOWN", 3: "MENU", 4: "SOURCE", 0xFF: "-"}
KEY_SZ, LOG_N, HDR = 8, 16, 16
POLL_S = 0.2        # a human presses <= ~5 keys/s and the ring holds 16: 0.2 s polls cannot lose an entry; one read = 6 blocks ~ 40 ms


def keys_of(mask):
    return "+".join(n for b, n in SDK_NAMES if mask & b) or "-"


def band_hint(a0, a1):
    """Which ladder band the raw values fall in."""
    h = [f"{'A0' if reg == 0xFF09 else 'A1'}-{n}" for _, reg, lo, hi, n in BANDS if lo <= (a0 if reg == 0xFF09 else a1) < hi]
    return ",".join(h) or "idle"


def log_mode(a, root, io=None):
    """io = an already open bus (fw_sim SimBus in keys_sim.py); default: the real unit on <bus>."""
    import re
    import dbg_xdata as X
    import i2cbus
    import rtd_i2c_bridge as B
    mp = Path(a[a.index("--map") + 1]).read_text(errors="replace")
    m = re.search(r"^D:\s+([0-9A-F]{8})\s+_g_stAwtoKey\b", mp, re.M)
    if not m:
        sys.exit("_g_stAwtoKey not in the map: image without the #39 key log")
    base = int(m.group(1), 16)
    bus = int(a[0])
    if "--serial" in a and io is None:
        i2cbus.require_unit(bus, a[a.index("--serial") + 1])
    secs = float(a[a.index("--secs") + 1]) if "--secs" in a else 25.0
    wr = "--open" in a or "--close" in a
    own = io is None
    io = io or B.Real(bus, allow_write=wr, regread=True)
    lf = (root / "tmp" / "logs" / "rtd_keywatch.log").open("a", buffering=1)

    def say(s):
        line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
        print(line, flush=True)
        lf.write(line + "\n")

    if wr:
        v = 0x41 if "--open" in a else 0x42
        d = X.diag_base if hasattr(X, "diag_base") else None
        mdiag = re.search(r"^D:\s+([0-9A-F]{8})\s+_isr_g_stAwtoDiag\b", mp, re.M)
        tc = (int(mdiag.group(1), 16) if mdiag else 0xF6D0) + 0x28
        ok = io.write(X.DEV8, 0x01, bytes([tc >> 8])) and io.write(X.DEV8, 0x03, bytes([v])) and io.write(X.DEV8, 0x3B, bytes([tc & 0xFF]))
        say(f"test cmd 0x{v:02X} (key test screen {'open' if v == 0x41 else 'close'}) {'sent' if ok else 'NAK'}")
    seen, last, t0 = None, None, time.time()
    while True:
        raw = X.read_blocks(io, base, HDR + KEY_SZ * LOG_N)
        if raw is None or raw[:2] != b"KY":
            say(f"read failed or no key block at 0x{base:04X} (magic {raw[:2] if raw else None}; the block is created at the first key scan)")
        else:
            cnt, a0, a1, p30, mask, msg, flags = raw[5], raw[6], raw[7], raw[8], raw[9], raw[10], raw[11]
            if seen is None:
                seen = (cnt - LOG_N) & 0xFF if "--history" in a else cnt      # --history: the ring as it stands; else only presses from now on
                say(f"key block ok: screen {'OPEN' if raw[3] else 'closed'}, {cnt} presses logged so far")
            live = (a0, a1, p30, mask)
            if live != last:
                say(f"live A0=0x{a0:02X} A1=0x{a1:02X} P3.0={p30 & 1} bands {band_hint(a0, a1)} -> key {keys_of(mask)} msg {MSG_NAMES.get(msg, msg)} "
                    f"rep={flags & 1}{(flags >> 1) & 1} hold={(flags >> 2) & 1}{' INJ' if flags & 0x80 else ''}")
                last = live
            for n in range(seen, seen + ((cnt - seen) & 0xFF)):
                e = raw[HDR + KEY_SZ * (n & (LOG_N - 1)):][:KEY_SZ]
                if e[0] != (n & 0xFF) or (e[6] == 0 and e[7] == 0xFF):
                    continue                                    # empty / overwritten slot
                say(f"PRESS #{e[0]} t={e[1] << 8 | e[2]} ms A0=0x{e[3]:02X} A1=0x{e[4]:02X} P3.0={e[5] & 1} bands {band_hint(e[3], e[4])} -> "
                    f"key {keys_of(e[6]) if e[6] else 'msg-only'} msg {MSG_NAMES.get(e[7], e[7])}{' INJECTED' if e[5] & 0x80 else ''}")
            seen = cnt
        if "--once" in a or time.time() - t0 >= secs:
            break
        time.sleep(POLL_S)
    if own:
        io.close()
    return 0


def main() -> int:
    root = P.repo_root()
    if "--log" in sys.argv:
        for d in (Path(os.environ.get("AWTO_DDC_MAIN", "/mnt/2tb/git/awto-ddc")) / "scripts",):
            if d.exists() and str(d) not in sys.path:
                sys.path.append(d.as_posix())
        (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
        return log_mode(sys.argv[1:], root)
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp" / "logs" / "rtd_keywatch.log").open("a")
    bus = int(sys.argv[1])
    secs = int(sys.argv[sys.argv.index("--secs") + 1]) if "--secs" in sys.argv else 25
    isp = P.Isp(bus)
    if "--halt" in sys.argv:
        isp.write(0x6F, 0x80)
        P.log("MCU halted (ISP)")
    P.log(f"keywatch bus={bus} secs={secs}: press each button now")

    def rd(r):
        isp.write(0xF4, r); return isp.read(0xF5)

    last = None
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            a0, a1 = rd(0xFF09), rd(0xFF0A)
            p30 = isp.read(0x25)  # P3.x port snapshot (POWER = P3.0); reg per buttons.md note
        except OSError as e:
            P.log(f"read error {e}"); break
        key = decode(a0, a1)
        state = (a0, a1, tuple(key))
        if state != last:
            P.log(f"A0=0x{a0:02x} A1=0x{a1:02x} P3=0x{p30:02x} -> {key or 'idle'}")
            last = state
    P.log("keywatch done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
