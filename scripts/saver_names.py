"""Saver names and VCP 0xEB values from fw/awto/savers.tsv (the same file generates the firmware defines).

Library: SAVERS (rows), vcp(name) -> int, names() -> list of names that have a VCP value.
"""
from pathlib import Path

from _repo import ROOT

TSV = ROOT / "fw/awto/savers.tsv"


def _num(s):
    return None if s == "-" else int(s)


def load(path=TSV):
    rows = []
    for ln in Path(path).read_text().splitlines():
        if not ln.strip() or ln.startswith(("#", "name\t")):
            continue
        name, macro, run, vcp, note = (ln.split("\t") + [""])[:5]
        rows.append({"name": name, "macro": macro, "run": _num(run), "vcp": _num(vcp), "note": note})
    return rows


SAVERS = load()


def names():
    return [r["name"] for r in SAVERS if r["vcp"] is not None]


def vcp(name):
    for r in SAVERS:
        if r["name"] == name and r["vcp"] is not None:
            return r["vcp"]
    raise KeyError(f"no saver '{name}' with a VCP 0xEB value; have {names()}")
