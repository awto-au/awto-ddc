## Feature request (Dan): on-screen button-name readout
When a front-panel button is pressed, show the NAME of that button at the BOTTOM of the OSD.

Why: live confirmation of each key's label (we inferred POWER / MENU-ENTER / 2x ADJUST / SOURCE-EXIT / 1 unknown
from firmware; this proves them on hardware), and the first real use of the PC-driven OSD.

Pieces (both nearly in hand):
- Read the pressed key: ADC key register path from buttons.md — key_scan_adc (bank6 0x3944) reads ADC_A0/A1
  (scaler 0xFF09/0xFF0A); bands map to 6 keys. From the PC we can poll those two scaler regs via the ISP
  F4/F5 window and apply the same voltage bands (no firmware needed to tell us the key).
- Draw the name: rtd_osd.py (clean-room OSD lib, in progress) writes glyphs into a bottom OSD window.

Loop (host, firmware running): poll ADC regs -> decode band -> if key changed, write the label string into a
bottom OSD window and show it; blank after release/timeout. Must coexist with the firmware's own key read +
OSD (shared regs) — if that fights, fall back to: halt MCU during the demo (monitor is then host-only).

Labels to show (confirm/relabel as pressed): POWER, MENU, ADJ-, ADJ+, SOURCE, KEY? (unknown 0x02).
Open: does host polling of the ADC regs disturb the firmware's own key handling? test.
