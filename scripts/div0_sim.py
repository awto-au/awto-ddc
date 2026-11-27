"""Divide-by-zero counter for fw_sim runs (awto-ddc#214): every division by 0 the firmware executes, with its caller.

- `--keil-div` helpers (`__divuint_keil` ... `__modslong_keil`, awto-sdcc runtime): watch stub on the entry; divisor = R4:R5
  (16 bit) / R0..R3 (32 bit) (awto-sdcc device/lib/mcs51-keil*/_div*.s); caller = the return address on the stack.
- Inline `DIV AB` with B = 0 (8-bit `/`, `%`): fast-core counter cnt[5], site cnt[6] (scripts/mcs51_core.c).
- A signed helper calls its unsigned core: hits whose caller is another helper are not counted twice.
Use: w = Div0Watch(machine) before the run; w.hits() -> [(caller, helper, count)].
"""
from __future__ import annotations

HELPERS = {"_divuint_keil": 16, "_moduint_keil": 16, "_divsint_keil": 16, "_modsint_keil": 16,
           "_divulong_keil": 32, "_modulong_keil": 32, "_divslong_keil": 32, "_modslong_keil": 32}
DIVAB = "DIV AB"


class Div0Watch:
    def __init__(self, m):
        self.m, self.n, self.helpers = m, {}, []
        for name, bits in HELPERS.items():
            if "_" + name in m.sym:
                m.stub(name, self._hook(name, bits))
                self.helpers.append(name)
        self.ab0 = self._ab()

    def _ab(self) -> tuple[int, int]:
        c = getattr(self.m, "core", None)
        return (int(c.cnt[5]), int(c.cnt[6])) if c is not None else (0, 0)

    def _hook(self, name: str, bits: int):
        def fn(m, r):
            y = r["r"][4] | r["r"][5] if bits == 16 else r["r"][0] | r["r"][1] | r["r"][2] | r["r"][3]
            if y:
                return
            c = m.core
            sp = c.sfr[0x01]
            ret = c.iram[sp] << 8 | c.iram[(sp - 1) & 0xFF]
            caller = m.where(c.xram[0xFFFF] & 15, ret)
            if caller.lstrip("_") in HELPERS:              # signed helper -> unsigned core: counted at the signed entry
                return
            k = (f"{caller} (ret 0x{ret:04X})", name)
            self.n[k] = self.n.get(k, 0) + 1
        return fn

    def hits(self) -> list[tuple[str, str, int]]:
        out = [(c, h, n) for (c, h), n in sorted(self.n.items())]
        n, site = self._ab()
        if n != self.ab0[0]:
            out.append((f"{self.m.where(site >> 16, site & 0xFFFF)} (pc 0x{site & 0xFFFF:04X} bank {site >> 16}, last)", DIVAB, n - self.ab0[0]))
        return out

    def total(self) -> int:
        return sum(n for _, _, n in self.hits())

    def mark(self) -> dict:
        """Snapshot for `since`: per-step attribution in a sweep."""
        return {"n": dict(self.n), "ab": self._ab()[0]}

    def since(self, mk: dict) -> list[tuple[str, str, int]]:
        out = [(c, h, n - mk["n"].get((c, h), 0)) for (c, h), n in sorted(self.n.items()) if n != mk["n"].get((c, h), 0)]
        n, site = self._ab()
        if n != mk["ab"]:
            out.append((f"{self.m.where(site >> 16, site & 0xFFFF)} (pc 0x{site & 0xFFFF:04X}, last)", DIVAB, n - mk["ab"]))
        return out
