#!/usr/bin/env python3
"""Benchmark an existing Doom checkpoint without rebuilding its firmware.

Needs the checkpoint sources with doom-integration.patch applied, its current/
artifacts, and the original shareware IWAD. Does not modify those inputs.
"""
import argparse
import ctypes
import hashlib
import json
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--doom-root', type=Path, required=True)
    ap.add_argument('--image-dir', type=Path, required=True)
    ap.add_argument('--wad', type=Path, required=True)
    ap.add_argument('--result', type=Path, required=True)
    ap.add_argument('--repeat', type=int, default=5)
    ap.add_argument('--frames', type=int, default=3)
    args = ap.parse_args()
    sys.path.insert(0, str(args.doom_root.resolve() / 'scripts'))
    import fastmachine as F
    import doom_renderer as R
    # Count batched iterations in a temporary benchmark-only build. This does
    # not add counters or an ABI to the production integration patch.
    profile_dir = tempfile.TemporaryDirectory()
    profile_root = Path(profile_dir.name)
    source = F.SRC.read_text()
    result_core_sha = hashlib.sha256(source.encode()).hexdigest()
    source = source.replace('static void counted_ffwd(core_t *c,',
        'static uint64_t profile_skipped;\nuint64_t core_profile_skipped(void) { return profile_skipped; }\nstatic void counted_ffwd(core_t *c,')
    source = source.replace('    c->iram[addr] -= n;', '    profile_skipped += n;\n    c->iram[addr] -= n;')
    F.SRC = profile_root / 'mcs51_core.c'
    F.SRC.write_text(source)
    shutil.copyfile(args.doom_root / 'scripts/mcs51_ddr.h', profile_root / 'mcs51_ddr.h')
    F.SO = profile_root / 'mcs51_core.so'
    original_core = F.Core
    captured = {}

    class Capture(original_core):
        def free(self):
            if self.h:
                h = hashlib.sha256()
                for v in (bytes(self.p), bytes(self.iram), bytes(self.sfr), bytes(self.xram),
                          bytes(self.opcount), bytes(self.cycop), bytes(self.lacc), bytes(self.lmiss),
                          bytes(self.cnt), bytes(self.ddr_mem())):
                    h.update(v)
                captured['state_sha256'] = h.hexdigest()
                if hasattr(self.L, 'core_profile_skipped'):
                    self.L.core_profile_skipped.restype = ctypes.c_uint64
                    captured['profile_skipped'] = self.L.core_profile_skipped()
                captured['ddr_stats'] = [self.ddr_stats(i) for i in range(2)]
            super().free()

    F.Core = Capture
    rows = {'off': [], 'native': []}
    model = args.doom_root / 'scripts/dw8051_model.json'
    result = dict(core_sha256=result_core_sha, frames=args.frames, repeat=args.repeat,
                  image_sha256=hashlib.sha256((args.image_dir/'doom_renderer.bin').read_bytes()).hexdigest(),
                  model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
                  wad_sha256=hashlib.sha256(args.wad.read_bytes()).hexdigest())
    reference = None
    with tempfile.TemporaryDirectory() as td:
        directory = Path(td)
        for source in args.image_dir.iterdir():
            if source.suffix in ('.bin','.ihx','.map','.json'): shutil.copyfile(source,directory/source.name)
        pose = json.loads((args.doom_root / 'examples/doom-switch-pose.json').read_text())
        scene = json.loads((args.doom_root / 'examples/doom-switch-scene.json').read_text())
        commands = [{} for _ in range(args.frames)]
        if args.frames > 1: commands[1] = {'buttons': 1}
        # Alternate first mode per round to reduce drift/temperature bias.
        for repeat in range(args.repeat):
            for mode in (('off','native') if repeat % 2 == 0 else ('native','off')):
                base_init = Capture.__init__
                def setup(self, image, on=(mode == 'native')):
                    original_core.__init__(self, image)
                    self.set_counted_ffwd(on)
                Capture.__init__ = setup
                start_cpu = time.process_time()
                r, _ = R.simulate(args.wad, directory, frames=args.frames, commands=commands,
                                   initial_pose=pose, scene=scene, save_frames=False, latency=64)
                cpu = time.process_time() - start_cpu
                Capture.__init__ = base_init
                stable = {k:v for k,v in r.items() if k != 'host_seconds'}
                stable['captured'] = {k:v for k,v in captured.items() if k != 'profile_skipped'}
                if reference is None: reference = stable
                assert stable == reference, f'Doom state/timing differs: {mode}'
                rows[mode].append(dict(simulation_wall_s=r['host_seconds'], whole_process_cpu_s=cpu,
                                       state_sha256=captured['state_sha256'], profile_skipped=captured.get('profile_skipped')))
                print(repeat,mode,r['host_seconds'],flush=True)
    result['samples'] = rows
    result['equivalence_sha256'] = hashlib.sha256(json.dumps(reference,sort_keys=True).encode()).hexdigest()
    result['equivalent'] = {k:reference[k] for k in (
        'width','height','instructions','cpu_clk','model_ms','bank_switches',
        'stack_high','stack_wraps','ddr','ddr_latency_clk','ready_drop_every',
        'startup_clk','captured')}
    result['frame_cpu_clk'] = [f['cpu_clk'] for f in reference['frames']]
    result['speedup'] = statistics.median(v['simulation_wall_s'] for v in rows['off']) / statistics.median(v['simulation_wall_s'] for v in rows['native'])
    args.result.parent.mkdir(parents=True,exist_ok=True)
    args.result.write_text(json.dumps(result,indent=2)+'\n')
    print('Doom host speedup',result['speedup'],flush=True)
    profile_dir.cleanup()


if __name__ == '__main__': main()
