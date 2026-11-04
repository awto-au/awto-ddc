# rtd_headless - draft headless host for RTDCustomerTool plugins

- Findings and verdict: `docs/rtdtool-headless-feasibility.md`. Status: **draft, compiled only, never run**.
- Build (i686 mingw, same toolchain as `scripts/rtd_comm_shim/build.py`):
  `i686-w64-mingw32-gcc -O2 -Wall -o rtd_host.exe host.c -luser32 -lws2_32 -static-libgcc`
- Install: copy `rtd_host.exe` into the tool root (next to `Comm.dll`, `PlugIn\`, `Comm\`). Plugins resolve `Comm.dll`, `ISPToolSetting.ini` and write `VersionResult.txt` relative to the EXE directory.
- Prereqs:
  - `Comm\Comm_LinuxI2C.dll` (shim) plus `rtd_i2c_bridge.py real <bus>` listening on 127.0.0.1:17420.
  - Shim `GetCommID` must return 7, 9 or 10 (currently 0xAB0BB): ISP `InitialComm` only selects ids 1..10.
  - Remove or keep out of `Comm\` other transports that share the chosen id.
- Commands:
  - `rtd_host version` - ISP `InitialComm` + `ReadVersionExport`, prints `VersionResult.txt`.
  - `rtd_host rdreg <hex>` / `rdmcu <hex>` - `Comm.dll` register read through the `CRsComm` object.
  - `rtd_host copybank` / `combine` - ISP copy-bank / combine version reads; need `RTD_HOST_ALLOW_WRITE=1` (factory-mode toggle).
  - `rtd_host plugin PlugIn_NewEDID click:<id> wait:500 dump` - experimental: hidden dialog, post button clicks, print control text.
- Env: `RTD_HOST_COMMID`, `RTD_HOST_DIRECT=1` (I2C primitives over the bridge from this process), `RTD_HOST_SCALER_FILE`, `RTD_BRIDGE_PORT`.
- Not exposed on purpose: `ExecuteIsp` (flash write), `UpdateCombineVersionExport`.
