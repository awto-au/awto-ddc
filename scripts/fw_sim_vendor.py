#!/usr/bin/env python3
"""Run the VENDOR (Keil, 8051 banked) firmware image in fw_sim's ucsim model; names from re/jxc-4k (#26).

usage: fw_sim_vendor.py IMG [--mode 2160p60] [--max-instr 150000000] [--trace-writes] [--blockers]
  Banking = same as ours: XDATA 0xFFFF selects the 64 KiB bank (ucsim banker), common area 0x0000..0x28C5 identical in banks
  0..6 (Keil ?B_SWITCH thunks live there), banks 7..13 empty, 14/15 settings. Code banks = 7.
  Names: scripts/ghidra_names_merge.py output (tmp/names_merged_bank<N>.tsv, from re/jxc-4k) -> synthetic map
  tmp/fwsim/vendor/vendor.map (C: functions, X: globals); no vendor bytes are written outside tmp/.
Library: vendor_machine(img_path, mode) -> Machine with the same register models as ours (regdb reset values, Flash port, HdmiInput).
Log: tmp/logs/fw_sim_vendor_<mode>.log
"""
import argparse, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402

ROOT, NCODE, COMMON_END = S.ROOT, 7, 0x28C6
POWER_NORMAL = 2                # vendor g_stPowerInfo high nibble: 2 = NORMAL, 3 = SAVING (SysSourceDetectPort cae0/cad2 branches)
VENDOR_IMG = Path.home() / "vendors/realtek/analysis/dumps/jxc-4k-flash-AWT26110003-20261104-201610.bin"


def make_map(img: bytes) -> Path:
    """tmp/fwsim/vendor/vendor.map from the merged RE names (regenerated each run; derived artifact)."""
    subprocess.run([sys.executable, str(ROOT / "scripts/ghidra_names_merge.py")], check=True, capture_output=True)
    lines, seen = [], set()
    for bank in range(NCODE):
        for l in (ROOT / f"tmp/names_merged_bank{bank}.tsv").read_text().splitlines():
            f = l.split("\t")
            if len(f) < 3 or l.startswith("#"):
                continue
            sp, _, ad = f[0].partition(":")
            a, name = int(ad, 16), re.sub(r"\W", "_", f[1])
            if sp == "CODE":
                if a < COMMON_END and bank != 0:
                    continue
                key, v = ("C", bank, a), (bank << 16 | a) if a >= COMMON_END else a
            elif sp == "EXTMEM":
                key, v = ("X", a), a
                if key in seen:
                    continue
            else:
                continue
            seen.add(key)
            lines.append(f"{'C' if sp == 'CODE' else 'X'}: {v:08X} _{name}")
    for l in (ROOT / "re/jxc-4k/ghidra_globals.tsv").read_text().splitlines() + (ROOT / "re/jxc-4k/ghidra_globals_hand.tsv").read_text().splitlines():
        f = l.split("\t")
        if len(f) >= 3 and f[0].startswith("EXTMEM:") and ("X", int(f[0][7:], 16)) not in seen:
            seen.add(("X", int(f[0][7:], 16)))
            lines.append(f"X: {int(f[0][7:], 16):08X} _{f[1]}")
    d = ROOT / "tmp/fwsim/vendor"
    d.mkdir(parents=True, exist_ok=True)
    (d / "vendor.map").write_text("\n".join(lines) + "\n")
    return d / "vendor.map"


def find_ret(img: bytes) -> int:
    """Address of a RET in the common area: 0x0006 (after the LJMP at 0x0003, vector padding)."""
    assert img[6] == 0x22
    return 6


def vendor_machine(img_path: Path, mode: str, log=None, extra_devs=()):
    img = Path(img_path).read_bytes()
    devs, hdmi = S.video_devs(img, mode)
    m = S.Machine(img, make_map(img), "vendor-" + mode, log, [*devs, *extra_devs], ncode=NCODE, ret_pc=find_ret(img))
    m.t2_scale = S.T2_SCALE
    vendor_stubs(m, hdmi)
    return m, hdmi


def stub_at(m, bank: int, pc: int, name: str, fn):
    """Stub a vendor function that has no RE name yet (or give it one): sym entry then Machine.stub."""
    m.sym["_" + name] = bank << 16 | pc
    m.stub(name, fn)


def vendor_stubs(m, hdmi):
    """Vendor counterparts of fw_sim.video_stubs (Keil: bit result in carry, first byte arg R7, second R5, byte result R7)."""
    D2 = S.D2_INPUT_PORT
    pre = lambda m, r: {"carry": r["r"][7] == D2, "r7": int(r["r"][7] == D2)}     # result read from R7 by SysSourceDetectPort
    stub_at(m, 5, 0xFCD9, "ScalerTMDSPSPreDetect", pre)
    stub_at(m, 5, 0xFCE9, "ScalerTMDSNormalPreDetect", pre)

    def scan(m, r):
        if r["r"][7] != D2 or (m.rd(m.addr("g_stPowerInfo"))[0] >> 4) != POWER_NORMAL:     # PS: no scan, SysSourceJudge wakes the power
            return {"r7": S.SOURCE_NONE}
        m.wr(m.addr("g_usInputPixelClk"), hdmi.PCLK.to_bytes(2, "big"))        # Keil: big-endian
        return {"r7": S.SOURCE_HDMI}
    stub_at(m, 5, 0xF97B, "ScalerTMDSScanInputPort", scan)
    stub_at(m, 5, 0xF85F, "ScalerTMDSStableDetect", lambda m, r: {"carry": r["r"][7] == D2, "r7": int(r["r"][7] == D2)})   # (port R7, source type R5)
    return m


def pc_hist(m, n=60, step=1009):
    from collections import Counter
    h = Counter()
    for i in range(n):
        out = m.run(step + (i % 2) * 502)
        mt = re.search(r"Stop at 0x([0-9a-f]+)", out)
        if mt:
            pc = int(mt.group(1), 16)
            h[(m.rd(0xFFFF)[0] & 15, pc, m.where(m.rd(0xFFFF)[0] & 15, pc))] += 1
    return h


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("img", nargs="?", default=str(VENDOR_IMG))
    ap.add_argument("--mode", default="2160p60", choices=sorted(S.HdmiInput.MODES))
    ap.add_argument("--max-instr", type=int, default=100_000_000)
    a = ap.parse_args()
    log = (ROOT / f"tmp/logs/fw_sim_vendor_{a.mode}.log").open("w", buffering=1)
    m, _ = vendor_machine(Path(a.img), a.mode, log)
    ma = m.addr("g_stModeInfo")
    done, last = 0, None
    while done < a.max_instr:
        m.run(1_000_000); done += 1_000_000
        ms = m.rd(ma)[0] & 0x1F
        bank = m.rd(0xFFFF)[0] & 15
        out = m.last_out
        pc = re.search(r"Stop at 0x([0-9a-f]+)", out)
        line = f"{done // 1_000_000}M mode_state={ms} bank={bank} pc={pc.group(1) if pc else '?'}"
        print(line); log.write(line + "\n")
        if ms == 3:
            break
    m.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
