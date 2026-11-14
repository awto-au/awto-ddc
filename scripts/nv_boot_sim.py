#!/usr/bin/env python3
"""Boot the sim with real NVRAM pages (dumps of bank 15 pages 11-12) and read the SDK store state after boot.

usage: nv_boot_sim.py BIN MAP PAGE11.bin PAGE12.bin [NAME:HEXADDR:LEN ...]   (extra XDATA reads, e.g. rec:EE91:52)
  The sim serves flash reads from the image (0xFF beyond it): pages go at 0xFB000 / 0xFC000 (RL6449_Project.h
  _SYSTEM_EEPROM_EMULATION_FLASH_BANK 15, pages 11-12). Prints the SDK page tables, the NV gate counters and disp_rotate.
Log: ./tmp/logs/nv_boot_sim.log
"""
import os, sys, time
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "scripts"))
import fw_sim as S  # noqa: E402

LOG = ROOT / "tmp/logs/nv_boot_sim.log"
PAGE11, PAGE12, FLASH = 0xFB000, 0xFC000, 0x100000
BOOT_INSTR = 160_000_000            # boot to ACTIVE budget, as boot_sim
MODE_ACTIVE = 3


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


def main() -> int:
    binp, mapp, p11, p12 = map(Path, sys.argv[1:5])
    img = bytearray(binp.read_bytes())
    img += b"\xff" * (FLASH - len(img))
    img[PAGE11:PAGE11 + 0x1000] = p11.read_bytes()
    img[PAGE12:PAGE12 + 0x1000] = p12.read_bytes()
    out = ROOT / "tmp/scratch" / f"{binp.stem}-nv.bin"
    out.write_bytes(img)
    bus = S.SimBus(out, mapp.resolve(), "nvboot-" + binp.stem, None, boot=False, devs=[], video="1080p60")
    m = bus.m
    ok = bus.run_until_mode(MODE_ACTIVE, BOOT_INSTR)
    say(f"{binp.name} + {p11.name} / {p12.name}: ACTIVE {ok}")
    pg, ad = m.addr("g_pucFlashPageArr"), m.addr("g_pusFlashAddrArr")
    say(f"g_pucFlashPageArr[0] = {m.rd(pg)[0]}; g_pusFlashAddrArr[0] = {int.from_bytes(m.rd(ad, 2), 'big')} (big-endian build)")
    nv = m.rd(m.addr("g_stAwtoNv"), 22)
    say(f"g_stAwtoNv: {nv.hex(' ')} (magic, mask, why, inDdc, defer, flush, itemWr, ops, stable, ddcIdle, erase, bytes)")
    # settings.c statics (not in the map): addresses from tmp/sdcc-port/asm_bank/awto_settings_settings.rst of THIS image
    for arg in sys.argv[5:]:
        name, a, n = arg.split(":")
        say(f"{name} @{a}: {m.rd(int(a, 16), int(n)).hex(' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
