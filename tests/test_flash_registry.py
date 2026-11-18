"""Per-unit flash registry (docs/flash-registry.md): offline, FakeIsp from test_flash_incremental. No hardware."""
from __future__ import annotations

import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_flash_incremental as T  # noqa: E402
from test_flash_incremental import FakeIsp, SECTOR, NIMG, opts  # noqa: E402
import flash_state as S  # noqa: E402
import rtd_flash_image as I  # noqa: E402
import rtd_flash_sector as F  # noqa: E402

BLANK_AT = (3, 6, 9, 12, 15, 18, 21)       # blank image sectors split the unchanged sectors into 8 runs
SAMPLE_SEED = 7                            # opts() seed: pick_runs sees the same rng state in flash()
MANIFEST = "AWT0-flash-state.json"


@pytest.fixture(autouse=True)
def _log():
    lines: list[str] = []
    F.LOG = type("L", (), {"write": lambda s, x: lines.append(x), "flush": lambda s: None})()
    yield lines


def img_runs():
    b = bytearray(T.image())
    for i in BLANK_AT:
        b[i * SECTOR:(i + 1) * SECTOR] = b"\xff" * SECTOR
    return bytes(b)


def state(tmp_path):
    return S.FlashState.load(tmp_path / MANIFEST, "AWT0")


def first(tmp_path, isp=None, **kw):
    isp = isp or FakeIsp()
    for i in BLANK_AT:
        isp.flash[i * SECTOR:(i + 1) * SECTOR] = b"\xff" * SECTOR
    assert I.flash(isp, img_runs(), opts(tmp_path, **kw)) == 0
    isp.erased.clear()
    return isp


def second(isp, tmp_path, **kw):
    isp.reads = isp.crcs = 0
    assert I.flash(isp, img_runs(), opts(tmp_path, **kw)) == 0
    return S.STATS


def unsampled_run():
    runs = S._runs([i for i in range(NIMG) if i not in BLANK_AT])
    todo = S.pick_runs(runs, random.Random(SAMPLE_SEED), S.DRIFT_SAMPLE_RUNS)
    return [r for r in runs if r not in todo][0]


def test_registry_hit_reads_only_the_gate_and_samples_crc_runs(tmp_path):
    isp = first(tmp_path)
    st = second(isp, tmp_path)
    assert isp.reads == 2 and st.sector_reads == 2          # read gate only: no unchanged sector is read
    assert (st.crc_runs, st.crc_runs_total) == (S.DRIFT_SAMPLE_RUNS, 8)
    assert isp.erased == []
    assert state(tmp_path).verified_how.startswith("final CRC over 8 run(s)")   # the end-of-run CRC covers the whole image


def test_verify_all_and_no_registry_check_every_run(tmp_path):
    isp = first(tmp_path)
    assert second(isp, tmp_path, verify_all=True).crc_runs == 8
    assert second(isp, tmp_path, no_registry=True).crc_runs == 8


def test_volatile_sector_always_read_and_compared(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "VOLATILE_RANGES", ((5 * SECTOR, 6 * SECTOR, "test settings"),))
    isp = first(tmp_path)
    st = second(isp, tmp_path)
    assert st.sector_reads == 3                             # gate 2 + the volatile sector
    isp.flash[5 * SECTOR + 9] ^= 0xFF                       # firmware changed it at runtime: registry says "match"
    isp.erased.clear()
    second(isp, tmp_path)
    assert T.sector_set(isp.erased) == [5]                  # found without any drift guard
    assert bytes(isp.flash[5 * SECTOR:6 * SECTOR]) == img_runs()[5 * SECTOR:6 * SECTOR]


def test_no_registry_ignores_volatile_rule(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "VOLATILE_RANGES", ((5 * SECTOR, 6 * SECTOR, "test settings"),))
    isp = first(tmp_path)
    assert second(isp, tmp_path, no_registry=True).sector_reads == 2


def test_drift_in_sampled_run_falls_back_to_full_read(tmp_path, _log):
    isp = first(tmp_path)
    isp.flash[1 * SECTOR + 3] ^= 0x01                       # first run is always sampled
    isp.reads = 0
    assert I.flash(isp, img_runs(), opts(tmp_path)) == 0
    assert T.sector_set(isp.erased) == [1]
    assert isp.reads > 2                                    # image region read back
    assert any("registry untrusted -> full readback" in x for x in _log)
    assert state(tmp_path).how[2] == S.HOW_READ


def test_drift_in_unsampled_run_is_caught_by_the_final_crc(tmp_path):
    a, _b = unsampled_run()
    isp = first(tmp_path)
    isp.flash[a * SECTOR + 1] ^= 0x01
    with pytest.raises(RuntimeError, match="CRC mismatch"):
        I.flash(isp, img_runs(), opts(tmp_path))
    st = state(tmp_path)
    assert st.source == "write-failed" and st.sectors[a] is None and st.how[a] is None
    assert I.flash(isp, img_runs(), opts(tmp_path)) == 0    # untrusted registry: every run checked, sector repaired
    assert bytes(isp.flash[:NIMG * SECTOR]) == img_runs()


def test_verify_all_catches_the_same_drift_before_any_write(tmp_path):
    a, _b = unsampled_run()
    isp = first(tmp_path)
    isp.flash[a * SECTOR + 1] ^= 0x01
    assert I.flash(isp, img_runs(), opts(tmp_path, verify_all=True)) == 0
    assert T.sector_set(isp.erased) == [a]


def test_aborted_flash_marks_sectors_unknown_and_distrusts_registry(tmp_path, _log):
    isp = first(tmp_path)
    new = bytearray(img_runs())
    new[2 * SECTOR] ^= 0xFF
    new[10 * SECTOR] ^= 0xFF
    isp.corrupt = {2 * SECTOR}
    with pytest.raises(RuntimeError):
        I.flash(isp, bytes(new), opts(tmp_path))
    st = state(tmp_path)
    assert not st.trusted, st.source
    assert st.sectors[2] is None and st.how[2] is None
    isp.corrupt = set()
    assert I.flash(isp, bytes(new), opts(tmp_path)) == 0
    assert any("registry not trusted" in x for x in _log)
    assert S.STATS.crc_runs == S.STATS.crc_runs_total


def test_registry_rebuild_reads_once_and_then_writes_only_the_difference(tmp_path):
    isp = first(tmp_path)
    (tmp_path / MANIFEST).unlink()                          # lost tmp/ dir
    isp.flash[7 * SECTOR] ^= 0xFF
    isp.erased.clear()
    st = second(isp, tmp_path, registry_rebuild=True)
    assert T.sector_set(isp.erased) == [7]
    assert st.sector_reads >= S.FLASH_SECTORS and st.crc_runs == 0   # whole flash read; no drift guard needed
    reg = state(tmp_path)
    assert reg.how[100] == S.HOW_READ and reg.how[7] == S.HOW_WRITTEN and all(reg.sectors)
    assert reg.trusted and reg.image_sha256 == S.sha(img_runs())


def test_rebuild_without_crc_engine_verifies_by_second_read(tmp_path):
    isp = first(tmp_path)
    isp.crc_broken = True
    (tmp_path / MANIFEST).unlink()
    isp.reads = 0
    assert I.flash(isp, img_runs(), opts(tmp_path, registry_rebuild=True)) == 0
    assert isp.reads >= 2 * (S.FLASH_SECTORS // 16)


def test_rebuild_refuses_an_unverified_read(tmp_path):
    isp = first(tmp_path)
    n = [0]
    orig = isp.read_flash

    def flaky(addr, k):
        d = bytearray(orig(addr, k))
        n[0] += 1
        if n[0] > 2:                                        # past the read gate (calibration reuses its data)
            d[0] ^= 1
        return bytes(d)
    isp.read_flash = flaky
    with pytest.raises(RuntimeError, match="registry rebuild"):
        I.flash(isp, img_runs(), opts(tmp_path, registry_rebuild=True))
    assert isp.erased == []


def test_summary_totals_add_up(tmp_path, _log):
    img = bytearray(img_runs())
    isp = first(tmp_path)
    for i in (2, 4):
        img[i * SECTOR] ^= 0xFF
    img[6 * SECTOR:7 * SECTOR] = b"\xa5" * SECTOR            # blank -> data
    img[8 * SECTOR:9 * SECTOR] = b"\xff" * SECTOR            # data -> blank: erase only
    _log.clear()
    assert I.flash(isp, bytes(img), opts(tmp_path)) == 0
    text = "".join(_log)
    m = re.search(r"sectors: image (\d+), erased (\d+), programmed (\d+) \((\d+) pages\), skipped (\d+)", text)
    nimg, erased, prog, pages, skipped = map(int, m.groups())
    assert (nimg, erased, prog, skipped) == (NIMG, 4, 3, NIMG - 4)
    assert erased + skipped == nimg and prog <= erased and 0 < pages <= prog * (SECTOR // 256)
    assert I.DONE.endswith(f"erased {erased} programmed {prog} skipped {skipped} of {nimg}")
    assert I.DONE.startswith(f"{erased}/{nimg} sectors changed, ")        # old prefix kept


def test_summary_nothing_to_write(tmp_path, _log):
    isp = first(tmp_path)
    _log.clear()
    I.flash(isp, img_runs(), opts(tmp_path))
    text = "".join(_log)
    assert re.search(rf"image {NIMG}, erased 0, programmed 0 \(0 pages\), skipped {NIMG}", text)
    assert f"{NIMG - 2} avoided" in text                    # only the read gate touched the device
