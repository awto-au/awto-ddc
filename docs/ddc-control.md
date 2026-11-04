# DDC/CI control (3x JXC 4K monitors)

## Usage
- `scripts/ddc_ctl.py list` - connector, bus, model, brightness, power (0xD6 sl)
- `scripts/ddc_ctl.py sleep|wake [--monitor CONNECTOR|all]`
- `scripts/ddc_ctl.py brightness N [--monitor ...]` (0-100)
- `scripts/ddc_ctl.py get CODE` - read a VCP code on all monitors (e.g. `get 0x10`)
- Log: `tmp/logs/ddc_ctl.log`, `tmp/logs/ddc_idle.log`

## Identity
- All units report EDID `JXC:4K MONITOR:demoset-1`; DRM connector is the identity (currently `card0-DP-3`, `card1-DP-4`, `card1-HDMI-A-3`).
- I2C bus numbers change on reboot/re-enumeration; resolved on every run from `ddcutil detect --brief`.

## Idle hook
- `scripts/ddc_idle.py` runs `gdbus monitor --session --dest org.gnome.ScreenSaver` (no Python dbus bindings installed).
- `ActiveChanged(true)` -> `ddc_ctl.py sleep`; `false` -> `wake`. Every transition logged.
- GNOME has no external idle-command setting; this triggers on screen blank/lock (the ScreenSaver active state), not raw idle.
- Unit: `systemd/ddc-idle.service` (not installed by default):
  - `mkdir -p ~/.config/systemd/user && cp systemd/ddc-idle.service ~/.config/systemd/user/`
  - `systemctl --user daemon-reload && systemctl --user enable --now ddc-idle.service`
  - Remove: `systemctl --user disable --now ddc-idle.service`
  - Check: `journalctl --user -u ddc-idle -f`

## Measured facts (2026-11-04)
- Power `0xD6`: `4` = standby (reads back sl=0x02, DDC keeps answering); `1` = on (sl=0x01). `2` ignored.
- Use `--noverify` on writes: ddcutil verify fails on 0xD6 (read-back differs).
- Brightness `0x10` 0-100; 0 only dims, not fully dark.
- Answering codes: contrast `0x12`, colour preset `0x14`, RGB gain `0x16/0x18/0x1A`, volume `0x62`, sharpness `0x87` (0-4).
- Capabilities string lists only vcp(02); the firmware answers more.
- Input select `0x60` reads unreliably: not written by the tool.
- Call timing (this machine): getvcp 0.14-0.29 s, setvcp 0.1-0.2 s, detect 0.34-0.39 s.
  - Worst seen 1.37 s (getvcp read-back right after a power change; 0.7-0.8 s on detect/set while waking).
  - Per-call timeout 4.5 s (~3x worst) in `ddc_ctl.py`; expiry logs op, limit, elapsed.
- `sleep`/`wake` of one monitor = detect + set + read-back, about 2-3 s.

## Quirks
- ISP (I2C 0x4A) and flash are out of scope here; see the reversing docs.
- Brightness 0 is not off; use `sleep` to blank.
- A sleeping panel may be slow on the next DDC call (see worst case above).
