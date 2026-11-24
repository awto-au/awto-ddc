"""Native delay equivalence with no full firmware/toolchain dependency."""
import json
import subprocess
from pathlib import Path

import pytest

from delay_program import ROOT, program


def check_current_delay_sequences(tmp_path):
    model = json.loads((ROOT / 'scripts/dw8051_model.json').read_text())
    image = tmp_path / 'delay.bin'
    image.write_bytes(program())
    tables = tmp_path / 'model.bin'
    tables.write_bytes(bytes(model['cycles']) + bytes(model['oplen']))
    exe = tmp_path / 'counted-ffwd-check'
    subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-o', str(exe),
                    str(ROOT / 'tests/counted_ffwd_check.c')], check=True, capture_output=True)
    result = subprocess.run([str(exe), str(image), str(tables)], check=True,
                            capture_output=True, text=True, timeout=180)
    print(result.stdout)


def _core(code, pc=0x1000):
    import fastmachine as F
    c = F.Core(code)
    model = json.loads(F.MODEL_JSON.read_text())
    c.set_dw(model)
    c.set_fetch(model)
    c.xram[0xFDA0] = 1
    c.p.pc = pc
    return c


def _state(c):
    import ctypes
    return (bytes(c.p), bytes(c.iram), bytes(c.sfr), bytes(c.xram),
            bytes(c.opcount), bytes(c.cycop), bytes(c.lacc), bytes(c.lmiss),
            bytes(c.xacc), bytes(c.cnt))


@pytest.mark.parametrize('kind', ('register', 'direct', 'sfr', 'body', '8052', 'counter', 'level', 'edge', 'uncached', 'no-fetch', 'breakpoint', 'irq-inhibit', 'pending-irq'))
@pytest.mark.parametrize('offset', (0, 13, 14, 15))
def test_fallbacks_fetch_boundaries_and_pending_interrupts(kind, offset):
    import fastmachine as F
    image = bytearray(program())
    pc = 0x2000 + offset
    loop = bytes.fromhex('d506fd') if kind == 'direct' else bytes.fromhex('d5e0fd') if kind == 'sfr' else bytes.fromhex('00dffd') if kind == 'body' else bytes.fromhex('dffe')
    image[pc:pc+len(loop)+1] = loop + b'\x22'
    c = _core(bytes(image), pc)
    try:
        c.iram[7] = c.iram[6] = c.sfr[0x60] = 0
        if kind == '8052': c.set_dw(None)
        if kind == 'counter': c.sfr_write(0x89, 0x05)
        if kind == 'level': c.sfr_write(0xB0, 0xFB)
        if kind == 'edge':
            c.sfr_write(0xC8, 0x0C)
            c.sfr_write(0x90, 0xFD)
        if kind == 'uncached': c.xram[0xFDA0] = 0
        if kind == 'no-fetch': c.set_fetch(None)
        if kind == 'breakpoint': c.pch[pc] = 1
        if kind in ('pending-irq', 'irq-inhibit'):
            c.sfr_write(0xA8, 0xA0)
            c.sfr_write(0xC8, 0x80)
        snap = c.snap()
        states = []
        for enabled in (False, True):
            c.restore(snap)
            # Per-line fetch statistics live outside the snapshot structure.
            import ctypes
            ctypes.memset(ctypes.addressof(c.lacc), 0, ctypes.sizeof(c.lacc))
            ctypes.memset(ctypes.addressof(c.lmiss), 0, ctypes.sizeof(c.lmiss))
            c.set_counted_ffwd(enabled)
            for chunk in (1, 2, 7, 127, 256, 1000):
                c.run(chunk)
                states.append((enabled, chunk, _state(c)))
        assert [s[2] for s in states[:6]] == [s[2] for s in states[6:]]
    finally:
        c.free()


def test_zero_really_wraps_256_and_obeys_budget():
    image = bytearray(65536)
    image[0x1000:0x1003] = bytes.fromhex('dffe00')
    c = _core(bytes(image))
    try:
        c.iram[7] = 0
        c.run(255)
        assert c.p.pc == 0x1000 and c.iram[7] == 1 and c.p.instr == 255
        c.run(1)
        assert c.p.pc == 0x1002 and c.iram[7] == 0 and c.p.instr == 256
        assert c.opcount[0xDF] == 256
    finally:
        c.free()


@pytest.mark.parametrize('ratio', (256, 512, 768, 1024, 1280))
def test_flash_dividers_change_between_run_chunks(ratio):
    image = bytearray(65536)
    image[0x100F:0x1012] = bytes.fromhex('dffe00')
    c = _core(bytes(image), 0x100F)
    try:
        snap = c.snap()
        results = []
        for on in (False, True):
            c.restore(snap)
            import ctypes
            ctypes.memset(ctypes.addressof(c.lacc), 0, ctypes.sizeof(c.lacc))
            ctypes.memset(ctypes.addressof(c.lmiss), 0, ctypes.sizeof(c.lmiss))
            c.set_counted_ffwd(on)
            for n, fetch_ratio in ((1, ratio), (77, 1280), (127, 512), (51, ratio)):
                c.L.core_set_fetch_ratio(c.h, fetch_ratio)
                c.run(n)
                results.append(_state(c))
        assert results[:4] == results[4:]
    finally:
        c.free()


def test_sanitizer_observes_every_instruction(tmp_path):
    """Enabled instrumentation must not lose commits or IRAM accesses to batching."""
    source = tmp_path / 'san.c'
    source.write_text('''
#include <assert.h>
#include "scripts/mcs51_core.c"
int main(void) {
    uint8_t code[] = {0xD5, 0x30, 0xFD}, cyc[256] = {0};
    uint64_t stats[6];
    cyc[0xD5] = 3;
    core_t *c = core_new(code, sizeof code);
    core_set_dw(c, 1, cyc, 2, 4, 4, 12, 4);
    core_reset(c);
    assert(core_san_enable(c) == 0);
    core_set_counted_ffwd(c, 1);
    assert(core_run(c, 200) == R_DONE);
    core_san_stats(c, stats);
    assert(c->p.instr == 200 && c->iram[0x30] == 56);
    assert(stats[0] == 201 && stats[1] == 400);
    core_free(c);
}
''')
    exe = tmp_path / 'san-check'
    subprocess.run(['gcc', '-O2', '-DSDCC_SAN', '-I', str(ROOT), '-o', str(exe), str(source)],
                   check=True, capture_output=True)
    subprocess.run([str(exe)], check=True, capture_output=True)
