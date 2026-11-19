# ddcui (Qt GUI for ddcutil)

- Upstream: https://github.com/rockowitz/ddcui, built from master (0.7.0 dev, 317 commits past v0.6.0; needs Qt6 >= 6.7, libddcutil >= 2.2.7).
- Host: ddcutil / libddcutil 3.0.2 (rpm, `libddcutil.so.5`); no `libddcutil-devel`, no ddcui rpm. Nothing installed system-wide.

## Where
- Binary: `~/.local/bin/ddcui` (prefix `~/.local`); links system `libddcutil.so.5`.
- Menu entry: `~/.local/share/applications/ddcui.desktop`, name "ddcui: monitor DDC control".
- Build tree (untracked): `tmp/tools/ddcui/` = `src/` (ddcui), `ddcutil-src/` (tag v3.0.2, headers only), `ddcutil-priv/` (copied headers + `ddcutil_macros.h` 3.0.2 + `libddcutil.so` symlink + private `ddcutil.pc`).
- Access: `/dev/i2c-N` are root-owned with a per-user ACL (`getfacl /dev/i2c-11` shows `user:dan:rw-`); no `i2c` group needed. Same access as `dev.py`.

## Launch
- `ddcui` (or `~/.local/bin/ddcui`), or the app-menu entry.
- Headless check: `QT_QPA_PLATFORM=offscreen ddcui --help`.

## Safe use
- Reads only. Do not move sliders, press buttons or edit values: every control writes a VCP feature.
- Never touch write-only / action codes (04 factory reset, 05 reset luminance/contrast, 08 reset colour, 0x60 input select, 0xD6 power, 0xE1+ manufacturer) on any screen.
- Philips 288E2 is Dan's primary display: reads only.
- Identify monitors by model/serial, not bus number (buses change on reboot). AWT units: serials in `scripts/devices.json` (`AWT26110001..3`); tests only on the `test` unit.
- ddcui scans every bus on start; AWT units may be slow or not answer (flash/ISP in progress): close ddcui before `dev.py flash`.

## Rebuild
```
cd tmp/tools/ddcui
git -C src pull
PKG_CONFIG_PATH=$PWD/ddcutil-priv/lib/pkgconfig cmake -S src -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$HOME/.local
cmake --build build -j8 && cmake --install build
```
- Then re-apply the desktop entry (install writes `com.ddcutil.ddcui.desktop`; ours is `ddcui.desktop`, absolute Exec) and delete `~/.local/share/metainfo/com.ddcutil.ddcui.metainfo.xml`.
- If libddcutil's soname changes: re-point `ddcutil-priv/lib/libddcutil.so` and refresh the headers from the matching ddcutil tag.
- Install also drops `~/.local/lib/modules-load.d/ddcui.conf` (`i2c-dev`); unused by systemd there, harmless.
