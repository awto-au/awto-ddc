#!/usr/bin/env python3
"""Read live GPIO pin levels + modes over ISP (MCU halted, then reset). Pin roles by state diff (#7).

usage: rtd_gpio_live.py <bus> --serial AWT2611000N --label on|standby
  Reads every regdb GPIO pin: data reg (0xFFE2/E3 bit, 0xFE00..FE3x) with PORT_READ_CONTROL (FE60/FE61)
  as found and then with 0x00 (read-control probe), and the pin-share mode reg (page 10).
  Writes: page-select 0x9F, FE60/FE61 (restored), final reset 0xEE. Never touches pin data/mode regs.
  Out: tmp/regs/<serial>-gpio-<label>-<YYYYMMDD-HHMMSS>.json ; diff: rtd_gpio_live.py --diff a.json b.json
Log: ./tmp/logs/rtd_gpio_live.log
"""
import argparse, csv, json, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P
from rtd_osd import Osd

GPIO_TSV = Path.home() / "vendors/realtek/analysis/regdb/RTD2795T-CG.gpio.tsv"
RC = (0xFE60, 0xFE61)


def pins():
    out = []
    with GPIO_TSV.open() as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["table"] != "PIN" or not r["data_reg"].startswith("0x"):
                continue
            bit = int(r["data_bits"].split(":")[0]) if r["data_bits"] else 0
            out.append((r["pin"], r["port"], int(r["data_reg"], 16), bit, int(r["mode_reg"], 16) if r["mode_reg"].startswith("0x") else None))
    return out


def diff(a: str, b: str) -> int:
    A, B = json.load(open(a)), json.load(open(b))
    print(f"{'pin':8} {'port':6} {'mode':>5} {A['label']:>8}(as/rc0) {B['label']:>8}(as/rc0)")
    for k in A["pins"]:
        x, y = A["pins"][k], B["pins"][k]
        if (x["as"], x["rc0"]) != (y["as"], y["rc0"]) or x["mode"] != y["mode"]:
            print(f"{k:8} {x['port']:6} {x['mode']!s:>5} {x['as']}/{x['rc0']} -> {y['as']}/{y['rc0']} (mode {y['mode']})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int, nargs="?")
    ap.add_argument("--serial")
    ap.add_argument("--label")
    ap.add_argument("--diff", nargs=2)
    a = ap.parse_args()
    if a.diff:
        return diff(*a.diff)
    root = P.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (root / "tmp/regs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp/logs/rtd_gpio_live.log").open("a")
    P.log(f"=== gpio live bus={a.bus} serial={a.serial} label={a.label} ===")
    table = pins()
    o = Osd(a.bus)
    res = {"serial": a.serial, "label": a.label, "time": isostamp.now(), "pins": {}}
    o.enter()
    try:
        saved = [o.rd(r) for r in RC]
        res["read_ctrl_saved"] = saved
        for mode in ("as", "rc0"):
            if mode == "rc0":
                for r in RC:
                    o.wr(r, 0x00)
            for pin, port, reg, bit, mreg in table:
                d = res["pins"].setdefault(pin, {"port": port, "reg": hex(reg), "bit": bit, "mode": None})
                d[mode] = (o.rd(reg) >> bit) & 1
                if mode == "as" and mreg is not None:
                    d["mode"] = o.rd(mreg) & 7
        for r, v in zip(RC, saved):
            o.wr(r, v)
    finally:
        o.reset()
    f = root / "tmp/regs" / f"{a.serial}-gpio-{a.label}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    f.write_text(json.dumps(res, indent=1))
    P.log(f"saved {f}")
    print(f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
