# Spec: settings  (our design, not ported; #65 + awto-ddc "Settings registry" issue)
Status: TO WRITE (Sonnet, with Dan's setting list). No SDK source: everything here is our design (`derived`) or a public
standard (MCCS VCP codes).

## Scope
- One registry: `awto-rtdfw/settings/registry.tsv` (format in its header) -> generated `set_table`, OSD pages (`osd.h`),
  VCP map (DDC/CI), NVRAM layout + `set_schema` (`nvram.h`), awto-ddc dev.py settings, `docs/settings.md`.
- Everything is a setting, more rather than less: every OSD item, every factory item, every tunable we expose.
- Generator: clean-tree tool (`tools/gen_settings.py`), host-tested; schema version = hash of stored rows' (id, slot, type, range).

## Recovery (must hold; a bad setting never bricks the unit)
- Boot key combination held at power-on -> defaults before anything is applied (keys and hold time: to define).
- DDC/CI VCP 0x04 and the debug-slave command -> defaults.
- SF_RISKY rows auto-revert after SET_CONFIRM_MS without a confirm key.
- NVRAM check or schema mismatch -> defaults.

## Oracle
- Host: generator output stable; every row round-trips NVRAM; clamp/step rules.
- Sim: VCP 0x04 over the simulated DDC -> all rows at default; boot with the key model held -> defaults.
