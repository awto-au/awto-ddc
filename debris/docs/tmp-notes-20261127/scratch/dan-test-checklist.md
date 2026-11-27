# Dan test checklist: origin/main 48ea533d, image tag `dantest`

Images: AWT26110001-dantest-be, AWT26110002-dantest-be, AWT26110003-dantest-be (unit 3 = f5f2b83ba575).
All units muted (VCP 0x8D=1), console_mode Always on units 2 and 3, unit 3 Rotate 180.

## 1. Unit 3 diag screen (notes, log keep)
- `./dev.py note --unit 3 --open-console 'note A'`, then `./dev.py note --unit 3 'note B'`, `'note C'`.
- Look: A, B, C all show with full text; older notes keep text.
- Reopen / sleep-wake / switch input (`./dev.py kvm ...` or monitor SOURCE key): log is NOT wiped.
- Check: `./dev.py synclog --unit 3` lists the notes.

## 2. Colour temperature presets (VCP 0x14)
- White screen on the unit. `./dev.py ddc --unit N set 0x14 <val>` for 5000, 6500, 7500, 9300 (use the unit's value codes: `./dev.py ddc --unit N get 0x14`).
- Look: each step visibly different; 9300K clearly bluer than 5800K/5000K.

## 3. GUI status line + Unit log tab
- Restart the window from main: `python tools/osd_editor/run.py --monitor` (repo /mnt/2tb/git/awto-ddc).
- Look: bottom status line shows CPU / PLL / SPI / PWM / fw tag (`dantest`); Unit log tab fills.
- Monitor's awto menu, Information page: clocks shown.

## 4. DDC/CI follows the selected port
- `./dev.py ddc --unit N set 0x60 <port value>` (or `./dev.py kvm`), then `./dev.py ddc --unit N get 0x10`.
- Look: DDC answers on the new port right after select; no manual link switch.

## 5. Health monitor row / sync log
- `./dev.py health --unit N`: monitor row = longest stall per class at 0.1 ms with site id.
- `./dev.py synclog --unit N`: 'micro-delay long block' FD lines present.

## 6. HDMI lock (faster, 2.9 ms block only on retry)
- On HDMI at 4K60: switch inputs back and forth, sleep/wake (`./dev.py ddc --unit N sleep` / `wake`).
- Look: any no-picture after input switch or wake = report with unit, port, time.

## 7. Live sliders and settings
- awto menu: move brightness / contrast / colour sliders; picture changes while moving, value persists after leaving the page.
- `./dev.py settings --unit N list`; set one, `save`, power cycle, check it stays.
