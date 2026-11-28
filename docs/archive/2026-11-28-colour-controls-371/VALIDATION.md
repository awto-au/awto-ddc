# Validation record - colour controls #371

Base: `3326a1d6f78e7c676947bf7d82f35eb6d9f7166e`, also the remote main on the final freshness check, 28 November 2026.

## Results

| Check | Result |
|---|---|
| New full-image RGB regression | Pass, 1,452 assertions |
| Dropped-RGB mutation | Detected: first DDC case fails when the SDK RGB write is suppressed |
| Preset coefficient regression | All 19 assertions pass; five distinct coefficient triples |
| Native SDK-store/settings test | Pass, 125 rows, 48-byte aux block; includes equal-value prepare/store/apply contract |
| GUI colour dependency test | Pass: RGB and preset updates, same-unit reads, refusal |
| Existing live-slider suite | All 13 scenarios pass |
| DDC/CI regression | Pass, zero retried requests |
| Menu walk | Pass, 16 pages, 46 of 140 entries selected by the quick sweep |
| Firmware link validation | Zero problem findings, including ISR banking proofs |
| Generated settings table | Current; schema unchanged, 0x5B82 |
| Python syntax / patch whitespace | Pass |
| Additional pytest checks | 20 passed, 1 blocked creating an AF_UNIX socket (EPERM in this environment) |
| Broad GUI hotkey suite | Same first hotkey assertion failure on original main and patched GUI (`got == []`) |
| Runtime ISR gate | Blocked: installed ucsim cannot load bank 0; no successful runtime ISR result claimed |

This is not a complete green normal/extensive gate record. It is a review patch, not an approved deployment image.

## Firmware build and reproduction

The local validation image used SDCC 4.6.4 from the available awto-sdcc source snapshot, big-endian and Keil register ABI (`AWTO_SDCC_BE=1`, `AWTO_SDCCCALL=3`). The local compiler installation is unstamped; its source checkout identifies itself as `8ebdd1a` (snapshot pinned to awto-sdcc `8977d27`). Project compilation: 150 C files succeeded; library compilation: 261 C files succeeded. The warning policy has no unreviewed sites.

The ordinary build in this environment exposed a generated-object naming collision between `RL6449_Series_ColorOutputGammaChannelCtrl` and `RL6449_Series_ColorOutputGammaAdjust` after ASlink map-name truncation. The supplied `validate_build.py` is a local validation wrapper that shortens those two generated object basenames and copies their matching listings. It changes no firmware source and retains the normal layout/size/link checks. It is not part of the proposed repository patch. The generated bank and XDATA maps were not included in the patch, to avoid carrying local compiler/layout churn. Rebuild and run the project's full gates in the normal development toolchain before merging.

Image tested: 983040 bytes; SHA-256 `2412a6e5acb486d86aea2d116c2b81b5e5f9a5a0fcf837488fc20b3d92f16185`.
Linked IRAM stack starts at 0x80 with 128 bytes available; residual common areas end at 0x88d, below 0x890. The link checker reports zero findings. The image is not included in the review bundle.

After applying the patch to the base revision and building a big-endian image:

```sh
export AWTO_SDCC_BE=1 AWTO_SDCCCALL=3 AWTO_SIM_CORE=fast
python scripts/rgb_controls_sim.py IMAGE.bin IMAGE.map
python scripts/ctemp_sim.py IMAGE.bin IMAGE.map
python scripts/fw_gates.py IMAGE --only ddc,menu,link --tree .
QT_QPA_PLATFORM=offscreen python tools/osd_editor/test_colour_controls.py
QT_QPA_PLATFORM=offscreen python tools/osd_editor/test_live_sliders.py
python scripts/settings_gen.py --tree . --check
```

`IMAGE` denotes the path without an extension for the gate runner. Use the normal installed compiler through `AWTO_SDCC_BIN` when required. `rgb_controls_sim.py` defaults its byte-order environment to big-endian because its structure decoding is for that image format.

Native settings/storage check:

```sh
gcc -std=gnu11 -Wall -Wextra -Ifw/rtdfw/awto/include -Ifw/rtdfw/awto/settings \
  fw/rtdfw/tests/host/test_nvstore.c fw/rtdfw/awto/settings/settings.c \
  fw/rtdfw/awto/settings/set_table.c fw/rtdfw/awto/nvram/nvram.c -o /tmp/test_nvstore
/tmp/test_nvstore
```

The RGB simulator covers all five factory presets, each RGB channel and values 0, 1, 127, 254, 255 plus that preset's equal current value through DDC/CI, paged settings mailbox and OSD MO_SET. It checks mode, raw gains, unchanged channels, both readback paths and coefficient writes. Additional checks exercise actual OSD key editing, pending User round trips, save plus fresh simulator boots, saved User recall after reboot in a factory preset, equal-User write wear, reset behaviour and injected refusal without mode/gain side effects. NOR bytes survive reboot; item serialization and load/save execute in the firmware. These are simulated flash operations only.

Optical colour accuracy, per-unit CCT/tolerance and sRGB compliance remain unmeasured. No gain values were invented or changed. No physical monitor was accessed.
