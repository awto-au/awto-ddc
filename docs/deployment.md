# Firmware deployment and per-monitor EDID

## Rule

All AWTO monitors receive the **same firmware image**. The monitor's unique
identity is not a reason to rebuild the firmware. After the shared image is
verified, program that physical monitor's EDID separately.

Do not run three `build --unit` operations to deploy one release. Do not use
`flash --any-image` by itself for normal deployment: it leaves the EDID copied
from the shared image.

## Command

```sh
./dev.py deploy --unit 2 tmp/fw/AWT26110002-wb-p14ui28-be.bin
./dev.py deploy --unit 1 --force tmp/fw/AWT26110002-wb-p14ui28-be.bin
./dev.py deploy --unit 3 --force tmp/fw/AWT26110002-wb-p14ui28-be.bin
```

`--force` remains mandatory for working screens. The command resolves the
monitor from its current EDID before writing anything, then performs:

1. Validate that the image contains exactly one DP and two HDMI EDID tables.
2. Generate a per-monitor copy of only the 4 KiB sector containing those
   tables, plus the unmodified sector used as the write precondition.
3. Flash and read-back verify the same complete image.
4. Write the selected monitor's unique EDID sector using
   `--expect-current`, back it up, read it back, and re-protect the flash.

Generated sector files are retained under `tmp/fw/edid/`. Flash backups remain
under `tmp/flash-backups/`.

## Why sector `0x5000`, not `0x13000`

The factory firmware loaded EDIDs from slots in sector `0x13000`. Current AWTO
firmware serves three code-resident EDID tables. In the present image they are
all in sector `0x5000`; the deployment tool discovers and validates the sector
from the image instead of hard-coding it.

If the full-image step succeeds but the EDID step fails, the monitor may
temporarily report the serial compiled into the shared image. Do not identify
the monitor by that temporary serial and do not reflash the firmware. Use the
same physical bus reported by the failed deployment and retry only the EDID:

```sh
./dev.py edid --unit 3 --force --bus 21 tmp/fw/AWT26110002-wb-p14ui28-be.bin
```

`--bus` is for this recovery case: the operator is asserting that the physical
bus is still the monitor selected and logged before the shared-image flash.
