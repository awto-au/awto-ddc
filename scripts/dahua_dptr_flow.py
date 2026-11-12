#!/usr/bin/env python3
"""DPTR constant propagation over the Dahua firmware banks (resolves the '?' MOVX sites of the register audit).

usage: import dahua_dptr_flow as F; fl = F.Flow(bank_bytes_by_index); fl.site_state(bank, func_addr, insn_addr)
- Forward dataflow per function over the raw bank image (scripts/dis51.py opcode table); state = DPTR as
  int (constant) | ('E', d) (entry DPTR + d, used for helper summaries) | None + reason.
- LCALL/ACALL: summary of the callee (constant DPTR at all RETs, or entry-relative `INC DPTR; RET` helpers);
  otherwise DPTR is unknown after the call (reason 'call').
- Not handled: MOVX @Ri (page in P2), DPTR computed from A/Rn/direct (reason 'compute'), pointer parameters (reason 'entry').
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dis51  # noqa: E402

COMMON = 0x2586          # bank-private code starts here; below it every bank holds the same bytes
MAXSTEP = 6000           # per function walk; the largest Keil function here is ~2000 insns


def _length(op):
    return dis51.T[op][1]


class U:
    """unknown DPTR with the reason it is unknown"""
    def __init__(self, why): self.why = why
    def __eq__(self, o): return isinstance(o, U) and o.why == self.why
    def __hash__(self): return hash(self.why)
    def __repr__(self): return f"?{self.why}"


ENTRY = ("E", 0)


def _join(a, b):
    if a == b:
        return a
    return U("join")


def _add(v, d):
    if isinstance(v, int):
        return (v + d) & 0xFFFF
    if isinstance(v, tuple):
        return ("E", v[1] + d)
    return v


class Flow:
    def __init__(self, banks):
        self.banks = banks              # {bank: bytes}
        self.sum_cache = {}             # (bank_key, addr) -> summary
        self.fn_cache = {}              # (bank_key, entry) -> {insn: state}
        self.calls = {}                 # (bank_key, target) -> {(bank, pc): DPTR state} at each LCALL/ACALL/LJMP/AJMP into target
        self.edges = {}                 # same for every other control-flow edge (SJMP, Jcc, fall-through) into target

    def _img(self, bank, addr):
        """(key, bytes): common area is read from bank 0"""
        if addr < COMMON:
            return 0, self.banks[0]
        return bank, self.banks[bank]

    def _step(self, buf, pc, st, bank, depth):
        """returns (next_pcs, new_state, is_ret)"""
        op = buf[pc]
        n = _length(op)
        b = buf[pc:pc + n]
        nxt = pc + n
        # --- DPTR effects
        if op == 0x90:
            st = (b[1] << 8) | b[2]
        elif op == 0xA3:
            st = _add(st, 1)
        elif op == 0x75 and b[1] in (0x82, 0x83):
            if b[1] == 0x83:           # DPH
                st = U("compute") if not isinstance(st, int) else ((b[2] << 8) | (st & 0xFF))
            else:                      # DPL
                st = U("compute") if not isinstance(st, int) else ((st & 0xFF00) | b[2])
        elif op in (0xF5, 0xC5, 0x05, 0x15, 0x42, 0x43, 0x52, 0x53, 0x62, 0x63, 0xD0, 0xD5, 0x86, 0x87, 0x75) or 0x88 <= op <= 0x8F:
            dst = b[1] if len(b) > 1 else None
            if op == 0x75:
                dst = b[1]
            if op in (0xD0, 0xF5, 0xC5, 0x05, 0x15, 0x42, 0x52, 0x62, 0x43, 0x53, 0x63, 0xD5, 0x86, 0x87) or 0x88 <= op <= 0x8F:
                if dst in (0x82, 0x83):
                    st = U("compute")
        elif op == 0x85:               # MOV dst,src : bytes src,dst
            if b[2] in (0x82, 0x83):
                st = U("compute")
        elif op == 0xC0 and b[1] in (0x82, 0x83):
            # bank-switch dispatcher (PUSH DPL/DPH; LJMP 20xx): control leaves, DPTR after the call is unknown
            return [], U("bankcall"), True
        # --- control flow
        rel = lambda r: (nxt + (r - 256 if r > 127 else r)) & 0xFFFF
        if op == 0x22 or op == 0x32:
            return [], st, True
        if op == 0x02:
            return [(b[1] << 8) | b[2]], st, False
        if op == 0x80:
            return [rel(b[1])], st, False
        if op == 0x73:
            return [], st, False
        if op & 0x1F == 0x01:          # AJMP
            return [(nxt & 0xF800) | ((op >> 5) << 8) | b[1]], st, False
        if op == 0x12 or op & 0x1F == 0x11:   # LCALL / ACALL
            tgt = ((b[1] << 8) | b[2]) if op == 0x12 else (nxt & 0xF800) | ((op >> 5) << 8) | b[1]
            eff = self.summary(bank, tgt, depth + 1)
            if eff is None:
                st = U("call")
            elif isinstance(eff, int):
                st = eff
            else:
                st = _add(st, eff[1]) if not isinstance(st, U) else st
            return [nxt], st, False
        if op in (0x40, 0x50, 0x60, 0x70, 0xD8, 0xD9, 0xDA, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF):
            return [nxt, rel(b[1])], st, False
        if op in (0x10, 0x20, 0x30, 0xD5) or 0xB4 <= op <= 0xBF:
            return [nxt, rel(b[2])], st, False
        return [nxt], st, False

    def walk(self, bank, entry, init, depth=0, record=False):
        """dataflow from entry; returns ({insn_addr: state_before}, [ret states])"""
        key, buf = self._img(bank, entry)
        states = {entry: init}
        work = [entry]
        rets = []
        steps = 0
        while work and steps < MAXSTEP:
            pc = work.pop()
            steps += 1
            if pc >= len(buf):
                continue
            st = states[pc]
            if record:
                op = buf[pc]
                if op in (0x12, 0x02) or op & 0x1F in (0x11, 0x01):     # LCALL/ACALL and LJMP/AJMP (Keil tail calls)
                    tgt = ((buf[pc + 1] << 8) | buf[pc + 2]) if op in (0x12, 0x02) else ((pc + 2) & 0xF800) | ((op >> 5) << 8) | buf[pc + 1]
                    self.calls.setdefault((tgt if tgt < COMMON else bank, tgt), {})[(bank, pc)] = (st, entry)
            try:
                nexts, nst, is_ret = self._step(buf, pc, st, bank, depth)
            except Exception:
                continue
            if is_ret:
                rets.append(nst)
            for t in nexts:
                if t >= len(buf):
                    continue
                if record:
                    self.edges.setdefault((t if t < COMMON else bank, t), {})[(bank, pc)] = (nst, entry)
                if t in states:
                    j = _join(states[t], nst)
                    if j != states[t]:
                        states[t] = j
                        work.append(t)
                else:
                    states[t] = nst
                    work.append(t)
        return states, rets

    def summary(self, bank, addr, depth=0):
        """DPTR effect of calling addr: int (constant after), ('E', d) (entry + d) or None (unknown)"""
        key, _ = self._img(bank, addr)
        ck = (key if addr >= COMMON else 0, addr)
        if ck in self.sum_cache:
            return self.sum_cache[ck]
        if depth > 6:
            return None
        self.sum_cache[ck] = None                 # recursion guard
        _, rets = self.walk(bank, addr, ENTRY, depth)
        res = None
        if rets:
            r0 = rets[0]
            if all(r == r0 for r in rets) and not isinstance(r0, U):
                res = r0
        self.sum_cache[ck] = res
        return res

    def function(self, bank, entry):
        key, _ = self._img(bank, entry)
        ck = (key if entry >= COMMON else 0, entry)
        if ck not in self.fn_cache:
            states, _ = self.walk(bank, entry, ENTRY, record=True)
            self.fn_cache[ck] = states
        return self.fn_cache[ck]

    def site_state(self, bank, func_addr, insn):
        """DPTR state before the MOVX at insn: int | ("E", d) (function-entry DPTR + d: pointer set by the caller) | U | None (not reached)"""
        return self.function(bank, func_addr).get(insn)

    def opcode(self, bank, insn):
        _, buf = self._img(bank, insn)
        return buf[insn]

    def caller_states(self, bank, target):
        """control-flow edges into target seen so far: {(bank, pc): (DPTR state, entry of the walked function)}; run function() on all entries first"""
        k = (target if target < COMMON else bank, target)
        d = dict(self.edges.get(k, {}))
        d.update(self.calls.get(k, {}))
        return d

    def raw_callers(self, bank, target):
        """LCALL/LJMP target found by a byte scan, outside the walked code: {(bank, pc): DPTR const or None}.
        Const only when the previous instruction is MOV DPTR,#imm16 (the Keil pattern before a helper call)."""
        out = {}
        pat = [bytes([op, target >> 8, target & 0xFF]) for op in (0x12, 0x02)]
        scan = [(0, 0, COMMON)] + [(bank, COMMON, len(self.banks[bank]))]
        if target >= COMMON:
            scan = [(bank, COMMON, len(self.banks[bank]))]
        elif True:
            scan = [(0, 0, COMMON)] + [(b, COMMON, len(self.banks[b])) for b in self.banks]
        for b, lo, hi in scan:
            img = self.banks[b]
            for pt in pat:
                i = img.find(pt, lo)
                while 0 <= i < hi:
                    prev = img[i - 3:i]
                    out[(b, i)] = ((prev[1] << 8) | prev[2]) if len(prev) == 3 and prev[0] == 0x90 else None
                    i = img.find(pt, i + 1)
        return out

    def entry_values(self, bank, fa, depth=0, seen=frozenset()):
        """(set of constant DPTR values at entry of fa over all callers, number of callers that are not constant, number of callers).
        A caller whose DPTR is itself 'its own entry + d' is resolved through that caller's callers (depth <= 4)."""
        vals, unk, cs = set(), 0, self.caller_states(bank, fa)
        extra = {k: v for k, v in self.raw_callers(bank, fa).items() if k not in cs}
        for st in extra.values():       # callers in code the walk never reached (no Ghidra function around them)
            if st is None:
                unk += 1
            else:
                vals.add(st)
        for (cb, pc), (st, fe) in cs.items():
            if isinstance(st, int):
                vals.add(st)
            elif isinstance(st, tuple) and depth < 4 and (cb, fe) not in seen and (cb, fe) != (bank, fa):
                sv, su, sn = self.entry_values(cb, fe, depth + 1, seen | {(cb, fe)})
                if su or not sn:
                    unk += 1
                else:
                    vals |= {(v + st[1]) & 0xFFFF for v in sv}
            else:
                unk += 1
        return vals, unk, len(cs) + len(extra)
