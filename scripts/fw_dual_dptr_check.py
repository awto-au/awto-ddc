#!/usr/bin/env python3
"""Fail closed on unverified ISR preservation in the actual assembly link inputs.

Checks canonical SDCC/DW8051 entry saves, selector reset before body/calls, and
balanced restoration on every reachable exit. Empty vector RETIs are the only
automatic exception. Unknown assembly/control flow requires explicit review.
Library-only interrupt entry points and binary-only objects are not accepted.
"""
import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
import tempfile


@dataclass
class Routine:
    path: Path
    name: str
    code: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)


def operand(text):
    text = re.sub(r'\s+', '', text.lower())
    aliases = {'dps': '0x86', 'dpl1': '0x84', 'dph1': '0x85',
               '134': '0x86', '132': '0x84', '133': '0x85'}
    return ','.join(aliases.get(part, part) for part in text.split(','))


def check_compiler(sdcc, flags):
    """An older --dual-dptr compiler must not silently pick a 16-byte frame."""
    with tempfile.TemporaryDirectory(prefix='awto-dual-dptr-') as work:
        source = Path(work) / 'option.c'
        source.write_text('#if !defined(__SDCC_MCS51_DUAL_DPTR) || __SDCC_MCS51_DUAL_DPTR != 1\n'
                          '#error dual-DPTR firmware requires the compiler-defined option macro (awto-sdcc#88)\n'
                          '#endif\n')
        p = subprocess.run([sdcc, '-mmcs51', *flags, '-E', str(source)],
                           capture_output=True, text=True, timeout=30)
        if p.returncode:
            raise ValueError(f'compiler option macro check failed:\n{p.stdout}{p.stderr}')


def routines(path):
    """Named labels delimit routines; numeric/$ labels stay within the routine.

    Named internal labels may cause conservative rejections, rather than
    allowing a path whose register preservation cannot be established.
    """
    result, cur, code_area = [], None, False
    for line_no, raw in enumerate(path.read_text().splitlines(), 1):
        text = raw.split(';', 1)[0].strip()
        if not text:
            continue
        if text.startswith('.area'):
            code_area = 'CODE' in text.upper()
            cur = None
            continue
        if not code_area:
            continue
        if text.startswith('.org'):
            origin = int(text.split(None, 1)[1], 0)
            cur = Routine(path, f'vector@0x{origin:04x}')
            result.append(cur)
            continue
        m = re.match(r'^([\w.$]+)::?\s*(.*)$', text)
        if m:
            label, text = m.groups()
            if cur is None or not (label[0].isdigit() or '$' in label):
                cur = Routine(path, label)
                result.append(cur)
            cur.labels[label.lower()] = len(cur.code)
        if not text or '=' in text or text.startswith(('.globl', '.module', '.optsdcc')):
            continue
        if cur is None:
            cur = Routine(path, f'<unlabelled:{line_no}>')
            result.append(cur)
        parts = text.split(None, 1)
        cur.code.append((parts[0].lower(), operand(parts[1]) if len(parts) == 2 else '', line_no))
    return result


def check(r):
    code = r.code
    if len(code) == 1 and code[0][:2] == ('reti', ''):
        return 'empty RETI: no DPTR/register use or calls'
    start = int(bool(code and code[0][:2] == ('clr', 'ea')))
    prefix = [('push', '0x86'), ('push', '0x84'), ('push', '0x85'), ('mov', '0x86,#0')]
    if [x[:2] for x in code[start:start + 4]] != prefix:
        raise ValueError('entry must save DPS/DPL1/DPH1 and select DPTR0 before the body')
    work = [(start + 4, ('0x86', '0x84', '0x85'), 0)]
    seen, at, exits = set(), {}, 0
    while work:
        pc, stack, restored = work.pop()
        state = (pc, stack, restored)
        if state in seen:
            continue
        seen.add(state)
        if pc >= len(code):
            raise ValueError('falls out of the handler without RETI')
        if pc in at and at[pc] != (stack, restored):
            raise ValueError(f'line {code[pc][2]}: conflicting stack states at branch merge')
        at[pc] = (stack, restored)
        op, arg, line = code[pc]
        if op == 'reti':
            if stack or restored != 3:
                raise ValueError(f'line {line}: exit without complete DPH1/DPL1/DPS restoration')
            exits += 1
            continue
        if restored and op != 'pop' and (op, arg) != ('setb', 'ea'):
            raise ValueError(f'line {line}: work/branch after restoring alternate registers')
        if op == 'push':
            stack = (*stack, 'body')
        elif op == 'pop':
            if not stack:
                raise ValueError(f'line {line}: stack underflow')
            if stack[-1] != 'body':
                if arg != stack[-1]:
                    raise ValueError(f'line {line}: expected pop {stack[-1]}, got {arg}')
                restored += 1
            stack = stack[:-1]
        elif op == 'ret' or op.startswith('.') or (op in ('inc', 'dec', 'mov', 'xch') and arg.split(',')[0] in ('sp', '0x81', '129')):
            raise ValueError(f'line {line}: unsupported ISR instruction {op} {arg}')
        if op in ('ljmp', 'ajmp', 'sjmp', 'jmp', 'jz', 'jnz', 'jc', 'jnc', 'jb', 'jnb', 'jbc', 'djnz', 'cjne'):
            target = arg.split(',')[-1]
            if target not in r.labels:
                raise ValueError(f'line {line}: branch outside verified routine: {target}')
            work.append((r.labels[target], stack, restored))
            if op in ('ljmp', 'ajmp', 'sjmp', 'jmp'):
                continue
        work.append((pc + 1, stack, restored))
    if not exits:
        raise ValueError('no verified interrupt exit')
    return f'{exits} verified exit(s), +3 stack bytes'


def audit(paths):
    all_routines = [r for path in paths for r in routines(path)]
    # Also require preservation for an entry reached by a vector, even when a
    # hand-written wrapper tail-jumps and contains no RETI of its own.
    targets = {arg for r in all_routines if r.name.startswith('vector@') and r.name != 'vector@0x0000'
               for op, arg, _ in r.code if op in ('ljmp', 'ajmp')}
    names = {r.name.lower() for r in all_routines}
    errors, checked = [], []
    for name in sorted(targets - names):
        errors.append(f'vector target {name}: no assembly in link inputs')
    for r in all_routines:
        isr = r.name.lower() in targets or any(op == 'reti' or (op in ('ljmp', 'ajmp') and arg == 'sdcc_atomic_maybe_rollback')
                                              for op, arg, _ in r.code)
        if not isr:
            continue
        try:
            checked.append(f'{r.path.name}:{r.name}: {check(r)}')
        except ValueError as e:
            errors.append(f'{r.path.name}:{r.name}: {e}')
    if not checked and not errors:
        errors.append('no interrupt handlers/vectors found in link inputs')
    return checked, errors


def check_link_inputs(rels):
    paths = []
    for rel in rels:
        asm = Path(rel).with_suffix('.asm')
        if not asm.is_file():
            raise ValueError(f'{rel}: assembly missing for linked object')
        paths.append(asm)
    checked, errors = audit(paths)
    if errors:
        raise ValueError('\n'.join(errors))
    return checked


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('asm', nargs='+', type=Path)
    a = ap.parse_args()
    checked, errors = audit(a.asm)
    print('\n'.join(checked + [f'FAIL {e}' for e in errors]))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
