#!/usr/bin/env python3
"""Sign Zeasn device-portal (deviceportal.zeasn.tv) queries for Philips monitor OTA firmware (awto-ddc#383).

Protocol (RE of Philips SmartControl 7.2.0; see /vendors/philips/smartcontrol/README.md):
  GET https://deviceportal.zeasn.tv/direct/component/update?brandId=74&push=true
      &deviceType=<model>&components=<BOM>=<FwVersion>,&ScalerIC=true&country&language=<lang>&sn&bcn&ruleMac=<mac>
  Header: Authorization: ZAuth <keyid>:<b64( HMAC-SHA1(secret_raw, "GET <url> <md5hex(body)>") )>
  Catalog (model list, no scaler/BOM): deviceType=PhilipsMonitorsOTA
      components=SmartControl_Monitors_OTA_JSON=<ver4>   (ver 0000 -> latest, >=current -> empty)
  Firmware query NEEDS a live monitor's scaler model + BOM string + FwVersion (read over DDC/CI). No offline index.

Key: `zeasn_deviceportal` section of ~/.config/awto/secrets.yaml (keyid=username, secret=password). Never embed in this public repo.

This script ONLY signs + prints URL(s) and the Authorization header as JSON. It does NOT fetch:
fetches go through the shared browser (playwrong), e.g.
  fetch(url, {headers:{Authorization: auth}})  in an in-page js call on origin https://deviceportal.zeasn.tv

usage:
  zeasn_portal.py catalog [--ver 0000]
  zeasn_portal.py fw --device <model> --bom <BOM> [--fwver 0] [--mac 00:00:00:00:00:00] [--lang en_US]
  zeasn_portal.py sign --url <full-url>
Output: JSON {url, auth} to stdout. Log: ./tmp/logs/zeasn_portal.log
"""
import argparse
import base64
import hashlib
import hmac
import json
import sys
from pathlib import Path

from _log import shared as _log_shared
from _repo import ROOT

LOG = ROOT / "tmp/logs/zeasn_portal.log"
BASE = "https://deviceportal.zeasn.tv/direct/component/update"
BRAND = "74"


def _key():
    import yaml
    sec = yaml.safe_load((Path.home() / ".config/awto/secrets.yaml").read_text()).get("zeasn_deviceportal")
    if not sec or not sec.get("username") or not sec.get("password"):
        raise SystemExit("zeasn_portal: add a zeasn_deviceportal section (username=keyid, password=secret) to secrets.yaml")
    return sec["username"], sec["password"]


def sign(url: str, method: str = "GET", body: str = "") -> str:
    """ZAuth header. secret is the raw UTF-8 string key (PJ b64_hmac_sha1); body hashed as lowercase md5 hex."""
    keyid, secret = _key()
    md5 = hashlib.md5(body.encode()).hexdigest().lower()
    msg = f"{method.upper()} {url} {md5}"
    mac = base64.b64encode(hmac.new(secret.encode(), msg.encode(), hashlib.sha1).digest()).decode()
    return f"ZAuth {keyid}:{mac}"


def catalog_url(ver4: str = "0000") -> str:
    return (f"{BASE}?brandId={BRAND}&push=true&deviceType=PhilipsMonitorsOTA"
            f"&components=SmartControl_Monitors_OTA_JSON={ver4}&ScalerIC=true&country&language&sn&bcn&ruleMac=00:00:00:00:00:00")


def fw_url(device: str, bom: str, fwver: str = "0", mac: str = "00:00:00:00:00:00", lang: str = "en_US") -> str:
    return (f"{BASE}?brandId={BRAND}&push=true&deviceType={device}"
            f"&components={bom}={fwver},&ScalerIC=true&country&language={lang}&sn&bcn&ruleMac={mac}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog")
    c.add_argument("--ver", default="0000")
    f = sub.add_parser("fw")
    f.add_argument("--device", required=True)
    f.add_argument("--bom", required=True)
    f.add_argument("--fwver", default="0")
    f.add_argument("--mac", default="00:00:00:00:00:00")
    f.add_argument("--lang", default="en_US")
    s = sub.add_parser("sign")
    s.add_argument("--url", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "catalog":
        url = catalog_url(a.ver)
    elif a.cmd == "fw":
        url = fw_url(a.device, a.bom, a.fwver, a.mac, a.lang)
    else:
        url = a.url
    out = {"url": url, "auth": sign(url)}
    _log_shared(LOG, echo="stderr").say(f"{a.cmd} url={url}")  # stdout stays clean JSON
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
