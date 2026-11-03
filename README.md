# awto-ddc

Tools and notes for controlling monitors over DDC/CI and for Realtek RTD scaler ISP (flash dump, fingerprint, firmware RE).

## Layout
- `scripts/rtd_isp_probe.py`: ISP over DDC (I2C 0x4A): JEDEC read, read-only flash dump
- `scripts/rtd_dump_info.py`: fingerprint + diff flash dumps (banks, 8051 vectors, EDID, caps string)
- `scripts/i2c_bench.py`: `/dev/i2c-N` read throughput per bus and read size
- `scripts/rtd_i2c_bridge.py` + `scripts/rtd_comm_shim/`: run Realtek's Windows tool under Wine against an emulated scaler (`emu`) or a real bus (`real`, writes blocked by default)
- `docs/monitors/`: per-monitor fingerprints and measurements
- `docs/reversing/realtek-rtd/`: ISP register table with confidence tags

## Not in this repo
- Vendor binaries, flash dumps, Ghidra projects: `~/vendors/realtek/` (analysis helpers in its `scripts/`)
- Origin: moved from awto-dan (issue #86 is now awto-ddc#1)
