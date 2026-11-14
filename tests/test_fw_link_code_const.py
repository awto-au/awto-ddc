"""Linked-image regressions for #149/#205; no compiler or monitor required."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fw_link_check as L
from fw_link_check_test import Img, stub
import fw_gates as G


def font_image(reader_bank=0, const_bank=1, wrapper=False, movc=True, tail=False):
    """__code pointer setup/spill, then _font_blob's DPTR/MOVC in another bank.

    The halves use R6/R7 (not the generic ABI's R1/R2); a spill and >30 source
    lines separate the symbol from the call. The reader has no const immediate.
    Another const at the same 16-bit address prevents numeric-bank guessing.
    """
    im = Img()
    blob = 0x6000 if const_bank != 'C' else 0x800
    ka = (const_bank << 16) + blob if const_bank != 'C' else blob
    im.add('_font_blob_spleen', ka, [(b'\x04\xde', '')], data=True)
    if const_bank != 'C':
        im.add('_unrelated', ((1 - const_bank) << 16) + blob, [(b'\x73\x5f', '')], data=True)
    ra = 0x900 if reader_bank == 'C' else (reader_bank << 16) + 0x5100
    reader = [(b'\x8e\x82', 'mov dpl,r6'), (b'\x8f\x83', 'mov dph,r7')]
    if movc:
        reader += [(b'\xe4', 'clr a'), (b'\x93', 'movc a,@a+dptr')]
    reader += [(b'\x22', 'ret')]
    im.add('_font_blob', ra, reader, params='const BYTE __code *blob')
    if reader_bank == 'C':
        target = ra
    else:
        stub(im, 'font_blob', 0x300, ra & 0xffff, reader_bank)
        target = 0x300
    if wrapper:
        im.add('_forward', 0xa00, [(bytes([0x12, target >> 8, target & 255]), 'lcall __bs_font_blob'),
                                 (b'\x22', 'ret')], params='const BYTE __code *blob')
        target = 0xa00
    load = [(bytes([0x7e, blob & 255]), 'mov r6,#_font_blob_spleen'),
            (bytes([0x7f, blob >> 8]), 'mov r7,#(_font_blob_spleen >> 8)'),
            (b'\x90\xd7\x00', 'mov dptr,#_font_blob_PARM_1'),
            (b'\xee', 'mov a,r6'), (b'\xf0', 'movx @dptr,a')]
    load += [(b'\x00', 'nop')] * 35
    op = 0x02 if tail else 0x12
    load += [(bytes([op, target >> 8, target & 255]), ('ljmp' if tail else 'lcall') + ' __bs_font_blob')]
    if not tail:
        load += [(b'\x22', 'ret')]
    im.add('_osd_font_load', 0x15000, load)
    return im


def linked(im, tmp_path, required=True):
    b, m, asm = im.files(tmp_path)
    image, findings = L.run(b, m, '', 0x5000, log=lambda _: None, asm_dir=asm, require_rst=required)
    return image, findings, (b, m, asm)


@pytest.mark.parametrize('wrapper,tail', [(False, False), (True, False), (False, True), (True, True)])
def test_split_font_rejected(tmp_path, wrapper, tail):
    image, findings, _ = linked(font_image(wrapper=wrapper, tail=tail), tmp_path)
    # Demonstrate the precise blind spot: both previous checks accept these bytes/listings.
    assert not L.check(image)
    assert not L.asm_const_ptr(image, tmp_path / 'asm')
    assert {f['kind'] for f in findings} == {'code_const_xbank'}
    assert findings[0]['src'] == '_font_blob'
    assert '_font_blob_spleen (bank 1)' in findings[0]['det']
    assert '_osd_font_load supplies' in findings[0]['det']


@pytest.mark.parametrize('reader_bank,const_bank,wrapper,movc', [
    (1, 1, False, True),       # current font co-location
    (1, 1, True, True),        # common wrapper, then switch back to bank 1
    (0, 'C', False, True),     # common ROM readable in any bank
    ('C', 1, False, True),     # common reader inherits bank 1
    ('C', 1, True, True),      # common wrapper preserves bank 1
    (0, 1, False, False),      # DMA-only consumer, no CPU code read
])
def test_supported_pointer_access(tmp_path, reader_bank, const_bank, wrapper, movc):
    _, findings, _ = linked(font_image(reader_bank, const_bank, wrapper, movc), tmp_path)
    assert not findings


def test_direct_symbol_read_uses_identity_not_overlapping_offsets(tmp_path):
    im = font_image(reader_bank=1)
    im.add('_direct', 0x5200, [(b'\x90\x60\x00', 'mov dptr,#_font_blob_spleen'),
                             (b'\xe4', 'clr a'), (b'\x93', 'movc a,@a+dptr'), (b'\x22', 'ret')])
    _, findings, _ = linked(im, tmp_path)
    assert {f['kind'] for f in findings} == {'code_const_xbank'}
    assert findings[0]['src'] == '_direct'


def test_static_font_symbols_need_not_appear_in_map(tmp_path):
    im = font_image()
    im.map = '\n'.join(l for l in im.map.splitlines() if not l.startswith('C:')) + '\n'
    _, findings, _ = linked(im, tmp_path)
    assert {f['kind'] for f in findings} == {'code_const_xbank'}
    assert findings[0]['src'] == '_font_blob'
    assert '_font_blob_spleen' in findings[0]['det']


@pytest.mark.parametrize('target_bank', [0, 1, 'C'])
def test_symbolic_pointer_table_targets(tmp_path, target_bank):
    im = font_image(reader_bank=1)
    ka = 0xb00 if target_bank == 'C' else (target_bank << 16) + 0x7000
    im.add('_glyph_data', ka, [(b'\x01\x02', '')], data=True)
    # Replace the font table with a linked BE pointer and its symbolic directive.
    word = (ka & 0xffff).to_bytes(2, 'big')
    im.img[0x16000:0x16002] = word
    im.rst = [l.replace('04 DE', ' '.join(f'{x:02X}' for x in word))
               .replace('.db 0x4, 0xde', '.dw _glyph_data') for l in im.rst]
    _, findings, _ = linked(im, tmp_path)
    assert bool(findings) == (target_bank == 0)
    if findings:
        assert findings[0]['kind'] == 'code_const_xbank'
        assert '_glyph_data (bank 0)' in findings[0]['det']


def test_xdata_pointer_does_not_supply_a_rom_address(tmp_path):
    im = font_image(reader_bank=1)
    im.add('_ram_reader', 0x5200, [(b'\x90\x70\x00', 'mov dptr,#_local_lut'),
                                 (b'\xe4', 'clr a'), (b'\x93', 'movc a,@a+dptr'), (b'\x22', 'ret')],
           params='BYTE __xdata *buffer')
    im.add('_local_lut', 0x7000, [(b'\x01\x02', '')], data=True)
    stub(im, 'ram_reader', 0x340, 0x5200, 0)
    im.add('_ram_caller', 0x15200, [(b'\x7e\x00', 'mov r6,#_font_blob_spleen'),
                                  (b'\x12\x03\x40', 'lcall __bs_ram_reader'), (b'\x22', 'ret')])
    _, findings, _ = linked(im, tmp_path)
    assert not findings


def test_unknown_signature_and_recursive_wrapper_do_not_hide_pointer(tmp_path):
    im = font_image(wrapper=True)
    im.rst = [l for l in im.rst if 'void forward(' not in l]
    # A self edge exercises termination without imposing an arbitrary depth cutoff.
    im.add('_cycle', 0xb00, [(b'\x12\x0b\x00', 'lcall _cycle'),
                           (b'\x12\x03\x00', 'lcall __bs_font_blob'), (b'\x22', 'ret')],
           params='const BYTE __code *blob')
    _, findings, _ = linked(im, tmp_path)
    assert {f['kind'] for f in findings} == {'code_const_xbank'}


def test_stale_listing_does_not_pass_gate(tmp_path):
    im = font_image(reader_bank=1)
    im.rst = [l.replace('015100', '015104') for l in im.rst]
    _, findings, _ = linked(im, tmp_path)
    assert 'kind_stale' in {f['kind'] for f in findings}


def test_gate_requires_listings_and_records_failure(tmp_path, monkeypatch):
    _, _, (b, m, asm) = linked(font_image(), tmp_path)
    monkeypatch.setattr(G, 'ROOT', Path(L.__file__).resolve().parents[1])
    cmd = G.gates(b, m, '', tmp_path)['link']
    assert '--require-rst' in cmd
    # Use this fixture's actual linked listings, not the default build directory.
    cmd[cmd.index('--asm') + 1] = asm
    cmd[cmd.index('--save') + 1] = tmp_path / 'findings.txt'
    res = {}
    G.run('link', cmd, tmp_path / 'link.log', res, lambda _: None)
    assert res['link'][0] == 1
    assert 'code_const_xbank' in (tmp_path / 'findings.txt').read_text()
    monkeypatch.setattr(G, 'gates', lambda *args: {'link': cmd})
    monkeypatch.setattr(G, 'skips', lambda *args: {})
    monkeypatch.setattr(sys, 'argv', ['fw_gates.py', str(b), '--tree', str(tmp_path)])
    assert G.main() == 1
    record = json.loads(b.with_suffix('.gates.json').read_text())
    assert record['complete'] is True
    assert record['gates']['link']['result'] == 'FAIL'
    # Removing the listings must not downgrade the gate to the old numeric heuristics.
    (asm / 'x.rst').unlink()
    G.run('link', cmd, tmp_path / 'missing.log', res, lambda _: None)
    assert res['link'][0] == 1
    assert 'code_const_source' in (tmp_path / 'findings.txt').read_text()


def test_current_font_placement_is_preserved():
    rows = [l.split('\t') for l in (Path(L.__file__).resolve().parents[1] / 'fw/bank_layout.tsv').read_text().splitlines()]
    banks = {r[1]: r[2] for r in rows if len(r) == 5 and (r[1] == '_font_blob' or r[1].startswith('_font_blob_'))}
    assert len(banks) == 8
    assert set(banks.values()) == {'10'}
