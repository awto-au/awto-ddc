# Realtek RTDCustomerTool `DB.bin` register database

- Source: `RTDScaler/<chip>/DB.bin` from RTDCustomerTool V3.8 (vendor data, kept outside git).
- Parser: `scripts/rtd_db_parse.py <DB.bin> <out.tsv>`; output TSVs live in `~/vendors/realtek/analysis/regdb/`.
- Tags: [fw] derived from file bytes, confirmed on many records; [guess] plausible, unconfirmed; [?] unknown.
- Method: static analysis only. Nothing was run.
- Scope: format version 1 (RTD2795T/2785TM/2775TM/2776B/2797UPM/2525AR/2537T). RTD2172/RTD2186 are version 3 and not decoded.

## File map [fw]

| Region | Offset | Content |
|---|---|---|
| header | 0x000 | u32 magic `0x99552277`, u32 version (1), u32 `hdr_size` (0x400), then `(hdr_size-8)/4` u32 table entries |
| preamble | `hdr_size` | 5 u32 (20 B) |
| stream | `hdr_size+0x14` | chain of registers: tail, field x N, tail, field x N, ... |
| pool | end of last field | NUL-terminated strings, all pointers = `pool_base + value` |
| post-pool | `pool_base + final kt` | group table + binary data (partly understood) |

- All little-endian. Everything in the stream is 36-byte aligned records; no padding.
- `pool_base` = file offset immediately after the last field record. [fw]
- The last field's `kt` value (e.g. `0x273f18` on RTD2795T) equals the pool size, i.e. the offset of the post-pool binary. [fw]
- No per-page index is needed: addresses are explicit in each tail (below).

## Header offset table [?]

- Entries are zero or file offsets pointing at register boundaries inside the stream (a tail or a first field).
- Index-to-page mapping not worked out (RTD2795T: 92 non-zero entries, 32 hit a field start, 21 hit a tail, rest hit neither).
- Not needed by the parser.

## Preamble (5 x u32) [fw/?]

- `[0..3]`: four stream offsets [?] (RTD2795T: 0x147018, 0x148218, 0x14b68c, 0x152388).
- `[4]`: group id of the first register (RTD2795T: 0x0d = "Chip Control Part1"). [fw]
- The first tail then starts at `hdr_size+0x14`.

## Register = tail + fields [fw]

- A register is described by a 36-byte **tail** placed BEFORE its field records.
- Then `nf` 36-byte **field** records, MSB field first.
- The `nf` in the tail equals the actual field count on all 12,250 RTD2795T registers. [fw]
- Chain ends when the byte after the last field is neither a field nor a tail; that offset is `pool_base`.

### Tail (36 B)

| Off | Size | Meaning |
|---|---|---|
| 0 | u32 | pool ptr: register name [fw] |
| 4 | u16 | register address, 16-bit = `page<<8 \| reg` (the tool's `CRxxxx`) [fw] |
| 6 | u16 | address again (equal on all but one RTD2795T register, a port register) [fw] |
| 8 | u16 | port index (0 for direct registers) [fw] |
| 10 | u16 | port index again [fw] |
| 12 | u32 | filler; 0 on RTD2795T, tag chars on RTD2785 [guess: constant per chip] |
| 16 | u32 | register type: 1 = direct; 2/3/4/6 = indirect port register (kind of port) [fw/guess] |
| 20 | 8 B | filler tag text (RTD2795T: UTF-16 `\Use`; RTD2785: `\row`) [fw] |
| 28 | u16 | field count of this register [fw] |
| 30 | u16 | filler tag (RTD2795T `s`; RTD2785 `i`) [fw] |
| 32 | u32 | pool ptr: name of this register's first field [fw] |

### Field (36 B)

| Off | Size | Meaning |
|---|---|---|
| 0 | 2 x u32 | `ffffffff ffffffff` normally. Otherwise (lo, hi) bit range of the full logical value this slice belongs to (e.g. 8..15 for the high byte of a 16-bit field spread over several registers) [guess; 5,276 RTD2795T fields, fits "High Byte [11:8]" style text] |
| 8 | u8 | bit_low [fw] |
| 9 | u8 | bit_high [fw] |
| 10 | u16 | filler tag (`g` on RTD2795T, `B` on RTD2785) [fw] |
| 12 | u32 | access code, see below [fw/guess] |
| 16 | u16 | reset value of the field (not shifted to its position) [fw: ID_REG id=0xCF, id_02=0x21, HDMI rr_req_status=0x07; guess on meaning] |
| 18 | u16 | filler tag (`o` / `n`) [fw] |
| 20 | u32 | pool ptr: description text (`\r` = newline) [fw] |
| 24 | u32 | pool ptr: reset-group / write-enable text (e.g. `Gp_vv_2:ff0:rst_n=sca_rst_out_n`, `Gp_vv_0_wen:reg=false`, `WportRport`; often empty) [fw/?] |
| 28 | 4 B | filler tags (`kt` / `nf`) [fw] |
| 32 | u32 | `kt`, see below |

- `kt` on a non-last field = pool ptr to the NEXT field's name. [fw]
- `kt` on the last field = **group id of the NEXT register** (same shape as the tail's next-name trick). [fw]
- Group id of the first register comes from preamble `[4]`.
- The very last field's `kt` is the pool size (no next register). [fw]
- Field name pointers: first field from the tail `[32]`, others from the previous field's `kt`.

### Tag/filler words [fw]

- The 16-bit tag words (`g o k t`, `\Use`, `s`) are constants per chip, not semantic.
- The parser learns them from the first tail+field at `hdr_size+0x14` and uses them as the record recognisers.

### Access code (field +12) [guess]

- 1 = R (9,730 RTD2795T fields: Reserved bits, status).
- 3 = RW (15,140 incl. 151 reported as W1C).
- 2 = W / data-port (129; "Access Port", `WportRport` FIFOs).
- 4 = RW with double-buffer (1,082; descriptions mention double buffer).
- Bit mask reading (bit0 R, bit1 W, bit2 double-buffered) fits all four codes. [guess]
- "W1C" in the TSV is inferred from the description text "Write 1 Clear", not from the code.

## Addresses [fw]

- Address is the u16 in the tail; no arithmetic needed.
- Page = high byte. RTD2795T checks:
  - `ID_REG` = 0x0000, `HOST_CTRL` = 0x0001, `ID_REG_02` = 0x000F (description of ID_REG says "LSB in REG_0x000F").
  - `XDATA_BANK_SEL` = 0xFFFE, `PBANK_SWITCH` = 0xFFFF (its description says "Pbank_switch (0xFFFF)").
  - Every direct (type 1) register falls on a non-zero `PGxx_TypeArry` slot in `ReadAll.txt`: 9,209 of 9,209.
  - The 94 TypeArry slots with no register are exactly `0x9F` of each page (PageSelect=159, handled by the tool).
- Indirect port registers carry the data-port address in `addr` plus the index in `port idx`; e.g. `SD_DATA_PORT_M1` 0x0025 with `V_SD_INIT_M1` at index 0, etc.
- Port register identity is not unique on (addr, port idx, type): 262 repeats on RTD2795T. Several port pages share an index range; the selecting register is not recorded. [?]

## Groups [fw/?]

- Group id (above) is global per DB: same id means same group name across pages, 0 conflicts over 190 ids (RTD2795T).
- Per page, runs of equal group id in stream order line up 1:1 with the `PGxx_Name` list in `ReadAll.txt` on 85 of 95 RTD2795T pages. [fw]
- Remaining pages: counts differ by 1 to 3 (adjacent names sharing an id, ids never seen elsewhere); groups left blank unless the id was learned on another page.
- Group table in the post-pool region: alphabetical `name (Page N)` strings at RTD2795T file offset 0x3c34a4 (347 entries, ends at the pool end 0x3c66b4). Group ids are not a simple index into it (about 75% of ids resolve if `M1 X` aliases of an existing `X` are dropped) [?].

## Not decoded

- Post-pool binary after the group table: records of pool pointers (RTD2795T: 0x3c66b4 to EOF, 147 KB). Likely mapping tables / CRC / DPCD cross-refs. [?]
- Register-level description text: none stored; only field descriptions.
- `DPCDDB.bin`, `IPDB.bin`, `GPIO.bin`: not looked at.
- Version-3 `DB.bin` (RTD2172, RTD2186): header `{magic, 3, 0x238, ...}`, different record layout (4-byte tags, no `g/o/k/t`).
