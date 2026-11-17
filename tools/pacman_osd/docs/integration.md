# Firmware integration boundary

There is no automatic boot hook or physical transport in this package.

For a future app build in the monitor firmware:

1. Add `src/pm_osd.c` and `generated/pm_assets.c` to an isolated app build with
   `include/` and `generated/` on its include path. `PM_CODE` and `PM_XDATA`
   select SDCC code/XDATA spaces. Compile and inspect the actual map and stack;
   the host build is not proof of the monitor ABI or code-bank placement.
2. Supply `pm_hw_word` through the existing OSD owner's synchronous writer.
   `pm_rtd_word` is an optional adapter using external `pm_bus_write`; it is
   not connected to the hardware here. Calls must not interleave with menu,
   popup, interrupt, or debug-port writes. The API is non-reentrant and should
   run in the app/main-loop context, not an ISR.
3. Save/restore the OSD owner state and reserve the SRAM range explicitly.
   Row base = 0, FS base = 37, font base = 1045, last used word = 4131.
   Use one-bit 12x18 storage, variable row height 12, width 12, compression off
   for expanded uploads, normal rotation, and writes to all byte planes/M1+M2.
   The font high-base bits and active font format must agree with this layout.
4. Install the palette from `generated/manifest.json`; index 1 is opaque black
   and index 0 remains transparent. Position/scale the OSD with the established
   driver. Clear `0x94` before disabling the OSD as required by the register DB.
5. Call `pm_load` once. Update actor pixel coordinates with `pm_actor_smooth`,
   modify background with `pm_eat`/`pm_background`, and call `pm_flush` once per
   app tick. Align the write batch to the established VSync/blanking mechanism;
   the current code supplies no tear-free or atomic-update guarantee.
6. Run the actual SDCC image under the existing `fw_sim.Machine` + `OsdModel`
   first. The included standalone diagnostic validates its own 8051 writer;
   it does not validate the C compiler, bank trampolines, RTD timing, interrupts,
   vendor firmware coexistence, or a hardware integration.

Before enabling smooth movement for a full game, implement pixel compositing
or prove a separate overlay-layer approach for the multi-colour overlap cases.
Layer B's position controls may be useful for a single moving layer, but they
do not establish five independently positioned sprites. Hardware rotation
must be tested with the intended source/destination geometry; global rotation
is not a substitute for independent Pac-Man orientation.
