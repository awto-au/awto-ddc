"""RL6449 memory map from fw/rl6449_memory.toml (#149 a): the one source for bank / XDATA / IRAM facts in the build scripts."""
import os, tomllib
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
FILE = ROOT / "fw/rl6449_memory.toml"
_M = tomllib.loads(FILE.read_text())

_C, _X, _I = _M["code"], _M["xdata"], _M["iram"]
BANK_SIZE = _C["bank_size"]
BANKS = _C["banks"]
CODE_BANKS = _C["code_banks"]
COMMON_END = _C["common_end"]
VECTORS_END = _C["vectors_end"]
RESID_END = _C["resid_end"]
BANK_REG = _C["bank_reg"]
RESERVED = {r["name"]: (r["addr"], r["size"]) for r in _C.get("reserved", [])}
XRAM = tuple(_X["pool"])
DDC_RAM = [tuple(w) for w in _X["ddc_ram"]]
DIRECT_END = _I["direct_end"]
ISEG_BASE = _I["iseg_base"]

for _n, (_a, _s) in RESERVED.items():                       # a reserved range must sit inside one bank
    assert _a // BANK_SIZE == (_a + _s - 1) // BANK_SIZE, f"{FILE}: reserved {_n} crosses a bank"
