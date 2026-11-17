# Current state

Draft graphics prototype, saved 2026-11-09. No monitor operation is needed to review it.

| Area | State | Evidence or remaining work |
| --- | --- | --- |
| Asset generation | Working offline | 343 resident glyphs, 4132 SRAM words, cached 3-pixel offsets |
| Portable C graphics renderer | Host-tested | SRAM layout, restoration, occlusion priority, phases, bounds, dirty overflow and reload |
| 8051 diagnostic app | Emulator-tested | Standalone display-list player; startup and all 96 frames match native C word-for-word |
| Negative control | Passed | Removing the MOVX data write is detected |
| HTML viewer | Prepared, JS logic tested | Canvas test-double pixels match the reference OSD model; full browser layout test blocked in the preparation environment |
| Actual C renderer on 8051 | Pending | Build with project SDCC and run under the existing firmware emulator |
| Firmware patch-app integration | Pending | App entry/exit, memory/ABI/banking, OSD ownership and VSync updates |
| Mixed-colour overlaps | Pending | Current fragments replace complete cells, then restore the background |
| Gameplay and controls | Pending | Current movement is a scripted graphics demonstration |
| Sound | Pending | Separate DAC/tone investigation; no audio implementation here |
| Hardware rotation/position controls | Documented, untested here | Prototype uses offline-generated orientations and offset glyphs |
| Physical monitor validation | Pending | No flash, ISP, reset, relay or DDC action performed |

Next step: compile the portable renderer into an isolated SDCC app and run that
actual image with the existing firmware emulator and OSD model. The included
8051 display-list player is a lower-level graphics diagnostic, not proof of
SDCC code generation or monitor integration. See docs/integration.md.
