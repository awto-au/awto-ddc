#!/usr/bin/env python3
"""Build variant of one image: which gates' expectations apply (docs/gates-report.md, "Variants").

usage: image_variant.py IMAGE_STEM      prints the variant as JSON
Source: tmp/fw/<stem>.build.json ("defines", written by scripts/fwimage.py); an image without one: map symbols (hwtest), default clock.
  hwtest   -D _AWTO_OSD_HWTEST (test ops; never promotes the tracked layouts, #268)
  t0ev     -D _AWTO_T0EV_TEST (Timer0 event test hooks, wdt_test t0_* / prio_*; never promotes the tracked layouts)
  clock    MCU MHz of the image (-D AWTO_CLOCK_MHZ=N, default DEFAULT_CLOCK_MHZ)
  variant  hwtest or clock != default: the build never promotes the tracked bank / XDATA layouts (#268); the XDATA layout it linked with is
           tmp/fw/<stem>.xdata_layout.tsv (layout), which the xlayout gate checks instead of the tracked file
"""
import json
import re
import sys
from pathlib import Path

DEFAULT_CLOCK_MHZ = 350            # Project_Option.h AWTO_CLOCK_MHZ default (docs/clock-sweep.md "Chosen default")
HWTEST_SYMBOL = " _g_stAwtoOsdHw"  # fallback for an image without build.json


def parse_defines(defines) -> dict:
    """['_AWTO_OSD_HWTEST', 'AWTO_CLOCK_MHZ=175'] -> {'hwtest': True, 'clock': 175}."""
    d = {str(x).removeprefix("-D").split("=")[0]: (str(x).removeprefix("-D").split("=", 1) + [""])[1] for x in defines}
    v = {"hwtest": "_AWTO_OSD_HWTEST" in d,
         "t0ev": "_AWTO_T0EV_TEST" in d,
         "clock": int(d["AWTO_CLOCK_MHZ"]) if re.fullmatch(r"\d+", d.get("AWTO_CLOCK_MHZ", "")) else DEFAULT_CLOCK_MHZ}
    return {**v, "variant": v["hwtest"] or v["t0ev"] or v["clock"] != DEFAULT_CLOCK_MHZ}


def of_image(bin_path: Path) -> dict:
    b = Path(bin_path)
    bj = b.with_name(b.stem + ".build.json")
    if bj.is_file():
        v = parse_defines(json.loads(bj.read_text()).get("defines", []))
    else:
        m = b.with_suffix(".map")
        v = {"hwtest": m.is_file() and HWTEST_SYMBOL in m.read_text(errors="replace"), "clock": DEFAULT_CLOCK_MHZ}
    v["variant"] = v.get("variant", v["hwtest"])
    lay = b.with_name(b.stem + ".xdata_layout.tsv")
    v["layout"] = str(lay) if (v["variant"] and lay.is_file()) else ""
    return v


if __name__ == "__main__":
    p = Path(sys.argv[1])
    print(json.dumps(of_image(p if p.suffix == ".bin" else p.with_suffix(".bin"))))
