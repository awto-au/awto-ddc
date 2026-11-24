#!/usr/bin/env python3
"""Offline host timing, not simulated FPS. Run from any checkout.

python scripts/bench_counted_ffwd.py --out tmp/ffwd-review/bench.json
Optional --reference-source old/mcs51_core.c also times the pre-change core.
Compilation, warmup, restoring and state hashing are outside timed intervals.
"""
import argparse
import ctypes
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'tests'))
from delay_program import program, SYMS, CALL, BASE
import fastmachine as F


def reference_library(source, directory):
    so = Path(directory) / 'reference.so'
    subprocess.run(['gcc', '-O2', '-shared', '-fPIC', '-o', str(so), str(source)],
                   check=True, capture_output=True)
    current = F.lib()
    old = ctypes.CDLL(str(so))
    for name in dir(current):
        if name.startswith('core_') and hasattr(old, name):
            getattr(old, name).argtypes = getattr(current, name).argtypes
            getattr(old, name).restype = getattr(current, name).restype
    # The old core predates the switch; constructing Core must remain possible.
    if not hasattr(old, 'core_set_counted_ffwd'): old.core_set_counted_ffwd = lambda *args: None
    return old


def state(c):
    h = hashlib.sha256()
    for v in (bytes(c.p), bytes(c.iram), bytes(c.sfr), bytes(c.xram), bytes(c.opcount), bytes(c.cycop), bytes(c.lacc), bytes(c.lmiss)):
        h.update(v)
    return h.hexdigest()


def measure(img, enabled, instructions, repeat, library):
    previous = F._LIB
    F._LIB = library
    try: c = F.Core(img)
    finally: F._LIB = previous
    try:
        model = json.loads(F.MODEL_JSON.read_text())
        c.set_dw(model); c.set_fetch(model); c.reset()
        c.set_counted_ffwd(enabled)
        c.xram[0xFDA0] = 1
        c.L.core_set_fetch_ratio(c.h, 768)
        c.run(10000)  # identical instruction warmup for all modes
        snap = c.snap()
        wall, cpu, digests = [], [], []
        for _ in range(repeat):
            c.restore(snap)
            ctypes.memset(ctypes.addressof(c.lacc), 0, ctypes.sizeof(c.lacc))
            ctypes.memset(ctypes.addressof(c.lmiss), 0, ctypes.sizeof(c.lmiss))
            w, p = time.perf_counter(), time.process_time()
            c.run(instructions)
            cpu.append(time.process_time() - p); wall.append(time.perf_counter() - w)
            digests.append(state(c))
        assert len(set(digests)) == 1
        return dict(wall_s=wall, cpu_s=cpu, median_wall_s=statistics.median(wall),
                    median_cpu_s=statistics.median(cpu), state_sha256=digests[0],
                    instr=c.p.instr, cycles=c.p.cycles, clk=c.p.clk)
    finally: c.free()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--instructions', type=int, default=10000000)
    ap.add_argument('--repeat', type=int, default=7)
    ap.add_argument('--reference-source', type=Path)
    args = ap.parse_args()
    current = F.lib()
    results = dict(instructions_per_sample=args.instructions, repeat=args.repeat,
                   python=sys.version, platform=platform.platform(), processor=platform.processor(),
                   gcc=subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0],
                   core_sha256=hashlib.sha256(F.SRC.read_bytes()).hexdigest(), workloads={})
    with tempfile.TemporaryDirectory() as td:
        old = reference_library(args.reference_source, td) if args.reference_source else None
        for name, routine, count in [('loops-1','AwtoDelayLoops',1), ('loops-4','AwtoDelayLoops',4),
                    ('loops-29','AwtoDelayLoops',29), ('loops-109','AwtoDelayLoops',109),
                    ('loops-255','AwtoDelayLoops',255), ('loops-zero','AwtoDelayLoops',0),
                    ('xus-29x64','AwtoDelayXus',64), ('gap-29','AwtoDelayCnt',29),
                    ('no-eligible-loop',None,0)]:
            image = bytearray(program())
            if routine:
                entry = SYMS[routine]
                body = bytes([0x75, CALL, count, 0x75, BASE, 29, 0x7E, count,
                              0x12, entry >> 8, entry & 255, 0x80, 0xF3])
            else:
                # MOVX/ALU/back-branch work must remain interpreted.
                body = bytes.fromhex('900100e004f0a3740780f5')
            image[:3] = bytes.fromhex('020200')
            image[0x200:0x200+len(body)] = body
            row = {}
            # Alternate order across workloads; retain each actual timing sample.
            modes = [('off',False,current), ('native',True,current)]
            if old: modes.insert(0, ('original',False,old))
            for sample in range(args.repeat):
                order = modes[sample % len(modes):] + modes[:sample % len(modes)]
                for mode, on, lib in order:
                    value = measure(bytes(image),on,args.instructions,1,lib)
                    if mode not in row:
                        row[mode] = value
                    else:
                        assert value['state_sha256'] == row[mode]['state_sha256']
                        row[mode]['wall_s'] += value['wall_s']
                        row[mode]['cpu_s'] += value['cpu_s']
            for value in row.values():
                value['median_wall_s'] = statistics.median(value['wall_s'])
                value['median_cpu_s'] = statistics.median(value['cpu_s'])
            assert len({v['state_sha256'] for v in row.values()}) == 1, name
            row['speedup_vs_off'] = row['off']['median_wall_s']/row['native']['median_wall_s']
            if old: row['speedup_vs_original'] = row['original']['median_wall_s']/row['native']['median_wall_s']
            results['workloads'][name] = row
            print(name, f"{row['speedup_vs_off']:.3f}x", flush=True)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(results,indent=2)+'\n')


if __name__ == '__main__': main()
