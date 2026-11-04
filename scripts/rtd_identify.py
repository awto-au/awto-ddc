#!/usr/bin/env python3
"""Identify a Realtek RTD-scaler monitor: EDID + DDC/CI caps + scaler chip + SPI flash programming params.

usage: rtd_identify.py <bus>|--all [--json] [--no-isp]
  Order: EDID + ddcutil (MCU running) first, then ONE ISP session (halts MCU), then reset (monitor reboots).
  READ-ONLY: no flash/status/scaler-register writes (ISP entry 0x6F<-0x80, F4 index writes, SPI read ops, 0xEE reset only).
  --all    : every /dev/i2c-* where ISP slave 0x4A answers a read of reg 0x6F
  --no-isp : EDID + DDC only (does not halt the monitor)
Reuses rtd_isp_probe.Isp / rtd_flash_sector.Rtd for the ISP engine. Flash DB: re/flashdb/FlashSet_v3.8.json.
Log: ./tmp/logs/rtd_identify.log
"""
import argparse, glob, json, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P                                   # noqa: E402
from rtd_flash_sector import Rtd, T_READ, OP_RDSR, SR_PROT  # noqa: E402

# Product code = (reg0x00 << 4) | (reg0x0F >> 4). Only values we have seen are listed.
SCALER_TABLE = {0xCF2: "RTD2795T-family (exact suffix unconfirmed)"}
DDC_TIMEOUT = 15      # ddcutil getvcp/capabilities on DP-AUX: a few s worst case, 15 s = stall backstop; expiry -> field error
EDID_TIMEOUT = 10     # edid-decode on 128-256 B: instant; expiry -> field error


def log(s):   # file only: stdout is reserved for the report / JSON
    P.LOG.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}\n"); P.LOG.flush()


def run(cmd, timeout, data=None):
    try:
        r = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout)
        return r.returncode, r.stdout.decode(errors="replace") + r.stderr.decode(errors="replace")
    except FileNotFoundError:
        return 127, "not installed"
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s: {cmd[0]}"


# ---------------- EDID ----------------
def edid_path(bus):
    for d in glob.glob("/sys/class/drm/card*-*/ddc"):
        if Path(d).resolve().name == f"i2c-{bus}":
            return Path(d).parent / "edid"
    return None


def parse_edid(e: bytes) -> dict:
    o = {"bytes": len(e)}
    if len(e) < 128 or e[:8] != bytes.fromhex("00ffffffffffff00"):
        o["error"] = "no valid EDID header"; return o
    m = (e[8] << 8) | e[9]
    o["manufacturer"] = "".join(chr(((m >> s) & 31) + 64) for s in (10, 5, 0))
    o["product_code"] = f"0x{e[10] | e[11] << 8:04x}"
    o["serial_numeric"] = int.from_bytes(e[12:16], "little")
    o["week"], o["year"] = e[16], 1990 + e[17]
    o["version"] = f"{e[18]}.{e[19]}"
    o["size_cm"] = [e[21], e[22]]
    o["names"], o["serial_text"] = [], None
    for i in range(54, 126, 18):
        d = e[i:i + 18]
        if d[:3] == b"\0\0\0" and d[3] == 0xFC:
            o["names"].append(d[5:].split(b"\n")[0].decode("ascii", "replace").strip())
        elif d[:3] == b"\0\0\0" and d[3] == 0xFF:
            o["serial_text"] = d[5:].split(b"\n")[0].decode("ascii", "replace").strip()
        elif d[0] or d[1]:
            if "timing" in o:
                continue
            pc = (d[0] | d[1] << 8) / 100
            ha, hb = d[2] | (d[4] & 0xF0) << 4, d[3] | (d[4] & 0x0F) << 8
            va, vb = d[5] | (d[7] & 0xF0) << 4, d[6] | (d[7] & 0x0F) << 8
            mmw, mmh = d[12] | (d[14] & 0xF0) << 4, d[13] | (d[14] & 0x0F) << 8
            ht, vt = ha + hb, va + vb
            o["timing"] = {"preferred": f"{ha}x{va}", "pixel_clock_mhz": pc, "h_total": ht, "v_total": vt,
                           "refresh_hz": round(pc * 1e6 / (ht * vt), 3) if ht * vt else None}
            o["size_mm"] = [mmw, mmh]
    o["model"] = o["names"][0] if o["names"] else None
    return o


def edid_report(bus):
    p = edid_path(bus)
    raw = None
    if p and p.exists():
        raw = p.read_bytes()
        src = str(p)
    if not raw:
        return {"error": "no kernel EDID for this bus (not a DRM connector DDC)"}
    o = parse_edid(raw); o["source"] = src
    rc, out = run(["edid-decode", "-c"], EDID_TIMEOUT, raw)
    if rc == 127:
        o["conformity"] = "edid-decode not installed"
    else:
        tail = re.split(r"\n(?=EDID conformity)", out)[-1].strip() if "EDID conformity" in out else out.strip()[-300:]
        o["conformity"] = tail.splitlines()[0] if tail else out[-200:]
        k = re.search(r"^(Warnings|Failures):", out, re.M)
        o["conformity_detail"] = [l.strip() for l in out[k.start():].splitlines()[:-1] if l.strip()][:20] if k else []
    return o


# ---------------- DDC/CI (MCU running) ----------------
def ddc_report(bus):
    o = {}
    for code, key in (("c8", "controller_type"), ("c9", "firmware_level"), ("df", "mccs_version")):
        rc, out = run(["ddcutil", "--bus", str(bus), "getvcp", code, "--brief"], DDC_TIMEOUT)
        if rc == 127:
            return {"error": "ddcutil not installed"}
        m = re.search(r"VCP\s+[0-9A-Fa-f]{2}\s+\w+\s+x([0-9a-f]{2})\s+x([0-9a-f]{2})\s+x([0-9a-f]{2})\s+x([0-9a-f]{2})", out)
        if m:   # brief format: VCP code type mh ml sh sl (hex bytes; sh/sl = current value)
            mh, ml, sh, sl = (int(x, 16) for x in m.groups())
            o[key] = {"max": mh << 8 | ml, "current": sh << 8 | sl, "raw_hex": f"{mh:02x}{ml:02x} {sh:02x}{sl:02x}"}
        else:
            o[key] = {"error": out.strip().splitlines()[-1] if out.strip() else f"rc={rc}"}
    rc, out = run(["ddcutil", "--bus", str(bus), "capabilities"], DDC_TIMEOUT * 2)
    if rc != 0:
        o["capabilities"] = {"error": out.strip()[-200:]}
    else:
        mm = re.search(r"MCCS version:\s*(\S+)", out); md = re.search(r"Model:\s*(.+)", out)
        feats = re.findall(r"^\s+Feature: ([0-9A-F]{2}) \((.*?)\)", out, re.M)
        o["capabilities"] = {"model": md.group(1).strip() if md else None, "mccs": mm.group(1) if mm else None,
                             "features": {c: n for c, n in feats}}
    return o


# ---------------- flash DB ----------------
def flashdb(jedec: bytes):
    db = json.load(open(P.repo_root() / "re" / "flashdb" / "FlashSet_v3.8.json"))
    return [c for c in db["chips"] if c["jedec"] == jedec.hex()]


def decode_prot(sr, chip):
    bits = sr & SR_PROT
    d = {"sr": f"0x{sr:02x}", "srwd": bool(sr & 0x80), "bp": (sr >> 2) & 7, "wel": bool(sr & 2), "wip": bool(sr & 1),
         "masked_0x9c": f"0x{bits:02x}"}
    d["state"] = "UNPROTECTED (SRWD=0, BP=0)" if bits == 0 else "PROTECTED (SRWD/BP bits set)"
    if chip:
        dis = int(chip["disable_wp_sr"][0], 16); en = int(chip["enable_wp_sr"][0], 16)
        d["matches_db_unprotect"] = (sr & 0xFF) == dis
        d["matches_db_protect"] = (sr & 0xFF) == en
    return d


# ---------------- ISP session ----------------
def isp_report(bus):
    o = {"isp_slave": "0x4A (8-bit write addr 0x94)"}
    isp = Rtd(bus)
    isp.write(0x6F, 0x80)
    if not isp.read(0x6F) & 0x80:
        return {"error": "ISP mode not enabled (reg 0x6F bit7 clear)"}
    try:
        def srd(r):
            isp.write(0xF4, r); return isp.read(0xF5)
        id_reg, r0f, r23 = srd(0x00), srd(0x0F), srd(0x23)
        code = (id_reg << 4) | (r0f >> 4)
        o["scaler"] = {"reg_0x00": f"0x{id_reg:02x}", "reg_0x0f": f"0x{r0f:02x}", "reg_0x23": f"0x{r23:02x}",
                       "product_code": f"0x{code:03x}", "version_nibble": r0f & 0xF,
                       "name": SCALER_TABLE.get(code, "unknown (not in table)")}
        jid = isp.common(T_READ, 0x9F, nr=3).to_bytes(3, "big")
        sr = isp.common(T_READ, OP_RDSR, nr=1)
        chips = flashdb(jid)
        fl = {"jedec": jid.hex(), "mfr": f"0x{jid[0]:02x}", "type": f"0x{jid[1]:02x}", "cap": f"0x{jid[2]:02x}",
              "size_from_cap_bytes": 1 << jid[2], "db_matches": len(chips)}
        if chips:
            c = chips[0]
            fl["db"] = {k: c[k] for k in ("name", "size_bytes", "bank_count", "sr_byte_count", "swren_name",
                                          "swren_every_page", "autodetect", "dev_id")}
            fl["db"]["swren"] = c["swren_name"]
            fl["db"]["engine_opcodes"] = {k: c[k] for k in ("sr2_read_op", "sr3_read_op", "sr3_write_op",
                                                            "sr4_read_op", "sr4_write_op")}
            fl["db"]["unprotect_disable_wp_sr"] = c["disable_wp_sr"]
            fl["db"]["protect_enable_wp_sr"] = c["enable_wp_sr"]
            fl["db"]["names_all_matches"] = [x["name"] for x in chips]
            fl["erase_model"] = ("DB has no erase fields; flash tooling here uses 4 KiB sector erase op 0x20, "
                                 "256 B page program op 0x02 (rtd_flash_sector.py)")
        fl["status"] = decode_prot(sr, chips[0] if chips else None)
        o["flash"] = fl
    finally:
        try:
            isp.write(0xEE, 0x02)
        except OSError:
            pass  # expected: scaler resets mid-transfer
        log("reset scaler MCU (0xEE <- 0x02): monitor reboots")
    return o


def isp_answers(bus):
    try:
        Rtd(bus).read(0x6F); return True
    except OSError:
        return False


def identify(bus, isp=True):
    log(f"identify bus={bus} isp={isp}")
    r = {"bus": bus, "edid": edid_report(bus), "ddc": ddc_report(bus)}   # MCU still running
    if isp:
        try:
            r["isp"] = isp_report(bus)                                  # halts MCU; reset at end
        except (OSError, TimeoutError) as e:
            r["isp"] = {"error": f"{type(e).__name__}: {e}"}
    return r


def human(r):
    L = [f"=== /dev/i2c-{r['bus']} ==="]
    e = r["edid"]
    L.append("[EDID]")
    if "error" in e:
        L.append(f"  error: {e['error']}")
    else:
        t = e.get("timing", {})
        L += [f"  manufacturer/model : {e['manufacturer']} / {e.get('model')}   product {e['product_code']}",
              f"  serial             : text={e.get('serial_text')} numeric={e['serial_numeric']}",
              f"  made               : week {e['week']} {e['year']}   EDID {e['version']}",
              f"  preferred timing   : {t.get('preferred')} @ {t.get('refresh_hz')} Hz  clk {t.get('pixel_clock_mhz')} MHz  "
              f"total {t.get('h_total')}x{t.get('v_total')}",
              f"  physical size      : {e.get('size_mm')} mm (base block cm {e['size_cm']})",
              f"  conformity         : {e.get('conformity')}"]
        L += [f"     {x}" for x in e.get("conformity_detail", [])[:8]]
    d = r["ddc"]
    L.append("[DDC/CI, MCU running]")
    if "error" in d:
        L.append(f"  error: {d['error']}")
    else:
        for k in ("controller_type", "firmware_level", "mccs_version"):
            v = d[k]
            L.append(f"  {k:<16} : " + (f"max/cur {v['raw_hex']}" if "raw_hex" in v else v["error"]))
        c = d["capabilities"]
        L.append("  capabilities       : " + (c["error"] if "error" in c else
                 f"model {c['model']} MCCS {c['mccs']}; VCP: " + ", ".join(f"{k}={v}" for k, v in c["features"].items())))
    i = r.get("isp")
    if i is None:
        return "\n".join(L)
    L.append("[Scaler / ISP]")
    if "error" in i:
        L.append(f"  error: {i['error']}")
        return "\n".join(L)
    s, f = i["scaler"], i["flash"]
    L += [f"  ISP slave          : {i['isp_slave']}",
          f"  ID_REG 0x00 / 0x0F : {s['reg_0x00']} / {s['reg_0x0f']}   reg 0x23 = {s['reg_0x23']}",
          f"  product code       : {s['product_code']}  version nibble {s['version_nibble']}  -> {s['name']}",
          "[SPI flash]",
          f"  JEDEC              : {f['jedec']} (mfr {f['mfr']} type {f['type']} cap {f['cap']} => {f['size_from_cap_bytes']} B)"]
    if "db" in f:
        db = f["db"]
        L += [f"  DB entry           : {db['name']} (matches: {db['names_all_matches']})",
              f"  size / banks       : {db['size_bytes']} B / {db['bank_count']} x 64 KiB   SR bytes {db['sr_byte_count']}",
              f"  SWREN              : {db['swren']} (every page: {db['swren_every_page']})",
              f"  unprotect (WRSR)   : {db['unprotect_disable_wp_sr']}   protect (WRSR): {db['protect_enable_wp_sr']}",
              f"  erase model        : {f['erase_model']}"]
    else:
        L.append("  DB entry           : none for this JEDEC")
    st = f["status"]
    L.append(f"  status reg (RDSR)  : {st['sr']}  SRWD={int(st['srwd'])} BP={st['bp']}  => {st['state']}"
             + (f"  [DB unprotect={st.get('matches_db_unprotect')} DB protect={st.get('matches_db_protect')}]"
                if "matches_db_unprotect" in st else ""))
    L.append("  (ISP session halted the MCU and reset the scaler: monitor reboots)")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bus", nargs="?", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-isp", action="store_true")
    a = ap.parse_args()
    if a.bus is None and not a.all:
        ap.error("give <bus> or --all")
    logdir = P.repo_root() / "tmp" / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    P.LOG = (logdir / "rtd_identify.log").open("a")
    if a.all:
        buses = sorted(int(x.rsplit("-", 1)[1]) for x in glob.glob("/dev/i2c-*"))
        buses = [b for b in buses if isp_answers(b)]
        log(f"--all: ISP slave answers on buses {buses}")
    else:
        buses = [a.bus]
    res = [identify(b, not a.no_isp) for b in buses]
    P.LOG.write(json.dumps(res) + "\n"); P.LOG.flush()
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for r in res:
            print(human(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
