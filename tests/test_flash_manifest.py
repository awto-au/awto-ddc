"""On-device flash manifest (docs/flash-registry.md): scripts/flash_manifest.py + the flasher's use of it. Offline, FakeIsp."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_manifest as FM
import flash_state as S
import rtd_flash_image as I
import rtd_flash_sector as F
import test_flash_incremental as T
from test_flash_incremental import NIMG, SECTOR, FakeIsp

BLANK_AT = (3, 6, 9, 12, 15, 18, 21)       # blank image sectors: checked like any skipped sector
MAN = FM.MANIFEST_ADDR
LEGACY_SLOT = 512                          # fw/rtdfw/awto/nvram/nvram.c record slot size
LEGACY_MAGIC = 0xA7


@pytest.fixture(autouse=True)
def _log():
    lines: list[str] = []
    F.LOG = type("L", (), {"write": lambda s, x: lines.append(x), "flush": lambda s: None})()
    yield lines


class EvIsp(FakeIsp):
    """FakeIsp that records erase / program order."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.ev: list[tuple[str, int]] = []

    def erase_sector(self, addr):
        self.ev.append(("erase", addr))
        super().erase_sector(addr)

    def program_page(self, addr, data):
        self.ev.append(("prog", addr))
        super().program_page(addr, data)


def img_runs():
    b = bytearray(T.image())
    for i in BLANK_AT:
        b[i * SECTOR:(i + 1) * SECTOR] = b"\xff" * SECTOR
    return bytes(b)


def opts(tmp_path, **kw):
    return T.opts(tmp_path, device_manifest=True, **kw)


def dev_manifest(isp):
    return FM.parse(bytes(isp.flash[MAN:MAN + SECTOR]))


def run(isp, tmp_path, img=None, **kw):
    isp.ev.clear()
    isp.erased.clear()
    isp.reads = isp.crcs = 0
    assert I.flash(isp, img or img_runs(), opts(tmp_path, **kw)) == 0


def fresh(tmp_path):
    isp = EvIsp()
    for i in BLANK_AT:
        isp.flash[i * SECTOR:(i + 1) * SECTOR] = b"\xff" * SECTOR
    run(isp, tmp_path)
    return isp


# --- format ---------------------------------------------------------------------------------------------------

def test_crc32_is_iso_hdlc():
    assert FM.crc32(b"123456789") == FM.CRC32_CHECK == 0xCBF43926


def test_build_parse_roundtrip_and_layout():
    img = img_runs()
    sec = FM.build(img)
    m, _why = FM.parse(sec)
    assert m is not None and m.count == NIMG and m.matches(img) == list(range(NIMG))
    assert sec[0] != LEGACY_MAGIC and sec[LEGACY_SLOT] == 0xFF       # the old record log scans 512 B slots for 0xA7
    assert sec[FM.SKIP_AT:FM.SKIP_AT + 4] == b"\xff" * 4
    bad = bytearray(img)
    bad[5 * SECTOR] ^= 1
    assert 5 not in m.matches(bytes(bad))


@pytest.mark.parametrize("damage", ["erased", "no_valid", "torn_body", "torn_commit", "magic"])
def test_invalid_variants(damage):
    sec = bytearray(FM.build(img_runs()))
    if damage == "erased":
        sec = bytearray(b"\xff" * SECTOR)
    elif damage == "no_valid":
        sec[FM.COMMIT_AT:FM.COMMIT_AT + 4] = b"\xff" * 4
    elif damage == "torn_body":
        sec[FM.TABLE_AT + 8] ^= 0x01
    elif damage == "torn_commit":
        sec[FM.COMMIT_AT + 5] ^= 0x01
    else:
        sec[0] = 0x00
    assert FM.parse(bytes(sec))[0] is None


def test_commit_page_is_programmed_last():
    pg = FM.pages(FM.build(img_runs()))
    assert pg[-1][0] == FM.COMMIT_AT and all(o < FM.COMMIT_AT for o, _ in pg[:-1])


def test_cli_check(tmp_path, capsys, monkeypatch):
    img = tmp_path / "i.bin"
    img.write_bytes(img_runs())
    out = tmp_path / "m.bin"
    monkeypatch.setattr(sys, "argv", ["flash_manifest.py", "build", str(img), "--out", str(out)])
    assert FM.main() == 0
    monkeypatch.setattr(sys, "argv", ["flash_manifest.py", "check", str(out), "--image", str(img)])
    assert FM.main() == 0 and "24 sector(s) match" in capsys.readouterr().out


# --- flasher --------------------------------------------------------------------------------------------------

def test_first_flash_no_manifest_builds_diff_from_device_and_writes_manifest_last(tmp_path, _log):
    isp = EvIsp()
    for i in BLANK_AT:
        isp.flash[i * SECTOR:(i + 1) * SECTOR] = b"\xff" * SECTOR
    run(isp, tmp_path)
    assert any("no valid device manifest" in x for x in _log)
    m, _ = dev_manifest(isp)
    assert m is not None and m.matches(img_runs()) == list(range(NIMG))
    assert [e for e in isp.ev if e[0] == "erase"][0] == ("erase", MAN)   # invalidated before the first image erase
    last_img = max(i for i, e in enumerate(isp.ev) if e[1] < MAN)
    first_man_prog = min(i for i, e in enumerate(isp.ev) if e[0] == "prog" and e[1] >= MAN)
    assert first_man_prog > last_img                                 # manifest only after every image sector
    assert isp.ev[-1] == ("prog", MAN + FM.COMMIT_AT) and isp.ev[-2][1] < MAN + FM.COMMIT_AT   # valid-word page last


def test_noop_flash_reads_one_manifest_sector_and_writes_nothing(tmp_path, _log):
    isp = fresh(tmp_path)
    _log.clear()
    run(isp, tmp_path)
    assert isp.erased == [] and not any(e[0] == "prog" for e in isp.ev)
    assert S.STATS.sector_reads == 3                                 # read gate 2 + the manifest sector
    assert S.STATS.crc_runs == 1 and S.STATS.crc_sectors == NIMG      # EVERY skipped sector (blank ones too) is truth-checked
    text = "".join(_log)
    assert "device manifest unchanged (valid, identical): nothing written" in text
    assert re.search(rf"image {NIMG}, erased 0, programmed 0 \(0 pages\), skipped {NIMG}", text)


def test_one_sector_change_writes_that_sector_and_a_new_manifest(tmp_path):
    isp = fresh(tmp_path)
    new = bytearray(img_runs())
    new[7 * SECTOR + 5] ^= 0xFF
    run(isp, tmp_path, bytes(new))
    assert T.sector_set([a for a in isp.erased if a < MAN]) == [7]
    assert isp.erased.count(MAN) == 1                                # invalidated, then programmed into the blank sector
    m, _ = dev_manifest(isp)
    assert m.matches(bytes(new)) == list(range(NIMG))
    assert isp.ev[-1] == ("prog", MAN + FM.COMMIT_AT)


def test_stale_manifest_detected_by_truth_check_and_only_that_sector_rewritten(tmp_path, _log):
    isp = fresh(tmp_path)
    isp.flash[11 * SECTOR + 100] ^= 0x01                              # manifest still says "matches"
    _log.clear()
    run(isp, tmp_path)
    assert T.sector_set([a for a in isp.erased if a < MAN]) == [11]
    text = "".join(_log)
    assert "manifest stale at run sectors 0-23" in text and "1 sector(s) differ [11]" in text
    assert "STALE at 1 sector(s)" in text
    assert bytes(isp.flash[:NIMG * SECTOR]) == img_runs()


def test_stale_blank_sector_in_a_skipped_run_is_caught(tmp_path):
    isp = fresh(tmp_path)
    isp.flash[6 * SECTOR] = 0x00                                      # image sector 6 is blank; the device sector is not
    run(isp, tmp_path)
    assert T.sector_set([a for a in isp.erased if a < MAN]) == [6]


def test_aborted_flash_leaves_the_manifest_invalid(tmp_path):
    isp = fresh(tmp_path)
    new = bytearray(img_runs())
    new[2 * SECTOR] ^= 0xFF
    new[10 * SECTOR] ^= 0xFF
    isp.corrupt = {2 * SECTOR}
    with pytest.raises(RuntimeError):
        I.flash(isp, bytes(new), opts(tmp_path))
    assert dev_manifest(isp)[0] is None and bytes(isp.flash[MAN:MAN + SECTOR]) == b"\xff" * SECTOR
    isp.corrupt = set()
    run(isp, tmp_path, bytes(new))                                    # no manifest: diff from the device, then manifest
    assert bytes(isp.flash[:NIMG * SECTOR]) == bytes(new) and dev_manifest(isp)[0] is not None


def test_manifest_for_another_sector_count_is_not_used(tmp_path, _log):
    isp = EvIsp(tail=b"\xff" * SECTOR)
    small = T.image(1, 10)
    assert I.flash(isp, small, opts(tmp_path)) == 0
    _log.clear()
    run(isp, tmp_path, img_runs())
    assert any("covers 10 sectors" in x for x in _log)
    assert dev_manifest(isp)[0].count == NIMG


def test_volatile_sector_is_read_and_compared_every_flash(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "VOLATILE_RANGES", ((5 * SECTOR, 6 * SECTOR, "test settings"),))
    isp = fresh(tmp_path)
    run(isp, tmp_path)
    assert S.STATS.sector_reads == 4                                  # gate 2 + manifest + the volatile sector
    isp.flash[5 * SECTOR + 9] ^= 0xFF                                 # firmware wrote it at runtime
    run(isp, tmp_path)
    assert T.sector_set([a for a in isp.erased if a < MAN]) == [5]


def test_manifest_write_failure_is_not_fatal(tmp_path, _log):
    class Bad(EvIsp):
        def program_page(self, addr, data):
            if addr >= MAN:
                raise TimeoutError("engine busy")
            super().program_page(addr, data)
    isp = Bad()
    assert I.flash(isp, img_runs(), opts(tmp_path)) == 0
    assert dev_manifest(isp)[0] is None and any("NOT written" in x for x in _log)
    assert bytes(isp.flash[:NIMG * SECTOR]) == img_runs()


def test_without_crc_engine_truth_check_reads_the_skipped_runs(tmp_path):
    isp = fresh(tmp_path)
    isp.crc_broken = True
    isp.flash[11 * SECTOR + 100] ^= 0x01
    run(isp, tmp_path)
    assert T.sector_set([a for a in isp.erased if a < MAN]) == [11]
    assert S.STATS.sector_reads >= NIMG - len(BLANK_AT)


def test_summary_lines(tmp_path, _log):
    """Example lines (first flash, no-op, one-sector change, stale) are printed with `pytest -s -k summary_lines`."""
    isp = EvIsp()
    for i in BLANK_AT:
        isp.flash[i * SECTOR:(i + 1) * SECTOR] = b"\xff" * SECTOR
    steps = []

    def step(name, img=None):
        _log.clear()
        run(isp, tmp_path, img)
        steps.append((name, [x.strip().split(" ", 1)[1] for x in _log if "SUMMARY: sectors" in x or "SUMMARY: diff" in x
                             or "SUMMARY: device" in x]))
    step("first flash (no manifest)")
    step("no-op flash")
    new = bytearray(img_runs())
    new[7 * SECTOR] ^= 1
    step("one-sector change", bytes(new))
    isp.flash[11 * SECTOR + 3] ^= 1
    step("stale manifest", bytes(new))
    for name, lines in steps:
        print(f"## {name}")
        print("\n".join(lines))
    sec = {n: [l for l in ls if l.startswith("SUMMARY: sectors")][0] for n, ls in steps}
    for line in sec.values():
        nimg, erased, prog, _pg, skipped = map(int, re.search(
            r"image (\d+), erased (\d+), programmed (\d+) \((\d+) pages\), skipped (\d+)", line).groups())
        assert erased + skipped == nimg and prog <= erased
