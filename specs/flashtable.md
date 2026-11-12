# Spec: flashtable  (step 6, #65): SPI flash part table from datasheets
Status: TO WRITE (Sonnet). Kept (Dan 2026-11-07).

## Sources
- Datasheets in `~/vendors/<flash vendor>/` (download per the vendor-store rules): JEDEC id, status-register layout,
  protect bits, page size, erase sizes/opcodes, timings. Tag `derived` (datasheet = public fact; cite file + page).
- Which parts to support: the parts the vendor table lists (ids as facts, `sdk-value` until each datasheet is in the store)
  plus ours (unit flash JEDEC id: `rtd_flash_sector.JEDEC_OK`).

## Oracle
- Table vs datasheet citations (one row each). Detect path: fw_sim FlashDev with each id -> chosen parameters.
