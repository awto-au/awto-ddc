"""Offline fixtures assembled directly from delay.c's naked routines.

This deliberately small assembler covers only the instructions in those routines;
unknown source is an error. It needs neither the proprietary SDK nor SDCC.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALL, BASE, LOG, BANK = 0x30, 0x31, 0xD100, 0x32
PAD = 0x0006
NAMES = ('AwtoDelayLoops', 'AwtoDelayXus', 'AwtoDelayEnd', 'AwtoDelayCnt', 'AwtoDelayLong')
SYMS = {name: 0x1000 + 0x100 * i for i, name in enumerate(NAMES)}
DIRECT = {'psw': 0xD0, 'acc': 0xE0, 'b': 0xF0, 'dpl': 0x82, 'dph': 0x83, 'sp': 0x81,
          '_d_isr_g_ucDelay5usN_Call': CALL, '_d_isr_g_ucDelayXusN_Base': BASE,
          '_d_isr_bs_cur': BANK, '_isr_g_stAwtoDlyLong': LOG}
header = (ROOT / 'fw/sdk/Project/Header/RL6449_Project.h').read_text()
CONSTS = {name: int(re.search(r'#define\s+' + name + r'\s+(\d+)', header)[1])
          for name in ('AWTO_DLY_PASS_CNT', 'AWTO_DLY_SLACK_TICKS')}


def program():
    source = (ROOT / 'fw/timer/delay.c').read_text()
    image = bytearray(65536)
    for name, start in SYMS.items():
        body = re.search(r'void ' + name + r'\(void\).*?__asm(.*?)__endasm', source, re.S)[1]
        lines = [s.strip() for s in body.splitlines() if s.strip()]
        labels = {}

        def value(s):
            s = s.strip().removeprefix('#')
            if s in DIRECT: return DIRECT[s]
            if s.removeprefix('_') in SYMS: return SYMS[s.removeprefix('_')]
            if s in CONSTS: return CONSTS[s]
            if s == '(255 - AWTO_DLY_SLACK_TICKS)': return 255 - CONSTS['AWTO_DLY_SLACK_TICKS']
            return int(s, 0)

        for passno in range(2):
            pc = start
            for line in lines:
                if line.endswith(':'):
                    labels[line[:-1]] = pc
                    continue
                op, *rest = line.split(None, 1)
                args = [a.strip() for a in rest[0].split(',')] if rest else []
                b = []
                if op in ('push', 'pop'): b = [0xC0 if op == 'push' else 0xD0, value(args[0])]
                elif op == 'ret': b = [0x22]
                elif op == 'djnz':
                    reg = re.fullmatch(r'r([0-7])', args[0])
                    b = [0xD8 + int(reg[1])] if reg else [0xD5, value(args[0])]
                    b += [(labels.get(args[1], 0) - pc - len(b) - 1) & 255]
                elif op == 'mov':
                    dst, src = args
                    if dst == 'dptr': b = [0x90, value(src) >> 8, value(src) & 255]
                    elif dst == 'a' and src == '@r0': b = [0xE6]
                    elif dst == 'a' and src == 'r7': b = [0xEF]
                    elif dst == 'r7' and src == 'a': b = [0xFF]
                    elif dst == 'r0' and src == 'a': b = [0xF8]
                    elif dst == 'a': b = [0xE5, value(src)]
                    elif dst == 'r7': b = [0xAF, value(src)]
                    elif src == 'a': b = [0xF5, value(dst)]
                    else: b = [0x85, value(src), value(dst)]
                elif op in ('ljmp', 'lcall'): b = [0x02 if op == 'ljmp' else 0x12, value(args[0]) >> 8, value(args[0]) & 255]
                elif op in ('jnc', 'jc', 'sjmp'): b = [{'jnc': 0x50, 'jc': 0x40, 'sjmp': 0x80}[op], (labels.get(args[0], 0) - pc - 2) & 255]
                elif op == 'clr' and args == ['c']: b = [0xC3]
                elif op in ('add', 'subb') and args[0] == 'a':
                    src = args[1]
                    if src == 'r7': b = [0x9F]  # subb a,r7
                    elif src.startswith('#'): b = [0x24 if op == 'add' else 0x94, value(src)]
                    else: b = [0x25 if op == 'add' else 0x95, value(src)]
                elif op == 'xch' and args == ['a', 'b']: b = [0xC5, 0xF0]
                elif op == 'mul' and args == ['ab']: b = [0xA4]
                elif op == 'inc': b = [0xA3] if args == ['dptr'] else [0x04] if args == ['a'] else []
                elif op == 'dec' and args == ['r0']: b = [0x18]
                elif op == 'movx': b = [0xE0] if args == ['a', '@dptr'] else [0xF0] if args == ['@dptr', 'a'] else []
                elif op == 'cjne' and args[:2] == ['a', '#0xFF']: b = [0xB4, 0xFF, (labels.get(args[2], 0) - pc - 3) & 255]
                else: raise ValueError(f'unsupported delay fixture instruction: {line}')
                assert b, line
                if passno: image[pc:pc+len(b)] = bytes(b)
                pc += len(b)
    # Timer2 ISR saves and uses R7, like nested firmware delays. Its entry sees
    # the interrupted counter and return PC; equality therefore checks IRQ timing.
    image[0x2B:0x2B+12] = bytes.fromhex('c0077f03dffed007c2cf32') + bytes([0])
    for vector in (0x0B, 0x1B):
        image[vector:vector+9] = bytes.fromhex('c0077f03dffed00732')
    return bytes(image)
