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
- `DPCDDB.bin`, `IPDB.bin`: not looked at. `GPIO.bin`: see below.
- Version-3 `DB.bin` (RTD2172, RTD2186): header `{magic, 3, 0x238, ...}`, different record layout (4-byte tags, no `g/o/k/t`).

# `GPIO.bin` pin database

- Source: `RTDScaler/<chip>/GPIO.bin` (V3.8; 26-49 KB). Parser: `scripts/rtd_gpio_parse.py <GPIO.bin> <out.tsv>`; outputs `~/vendors/realtek/analysis/regdb/<chip>.gpio.tsv` (outside git).
- Method: static analysis only. Strings in `PlugIn_GPIO.dll` are MFC/ATL boilerplate, no field names. Decoded from bytes, cross-checked against the `DB.bin` TSVs.
- Not the DB.bin container: same magic, but version 2 and no offset table / string pool. The file is a plain dump of C struct arrays; `0xCD` bytes are MSVC debug-fill padding. [fw]
- Scope: all 8 shipped chips parse to EOF with 0 trailing bytes (7 requested + RTD2797PM-VDL). [fw]

## Header [fw]

| Off | Size | Meaning |
|---|---|---|
| 0x00 | u32 | magic `0x99552277` |
| 0x04 | u32 | version = 2 |
| 0x08 | 100 B | UTF-16 chip tag (`RL6449` = RTD2795T, `RL6432` = RTD2785TM/2775TM, `RL6410` = RTD2797UPM/PM, `RL6193` = RTD2776B, `RL6463` = RTD2525AR, `RL6369` = RTD2537T) |
| 0x6C | u32 x2 | two numbers (RTD2795T: 49, 483); meaning unknown [?] |
| 0x74 | 8 B | uninitialised bytes [fw: differ per file, no structure] |
| 0x7C | u16 | pin count, then pin records from 0x7E |

## Conventions [fw]

- Strings: fixed 100-byte UTF-16LE buffers (50 chars); text ends at the first NUL, the rest is garbage (zeros, or `0xFE` fill in the timer names).
- Register reference = 4 bytes: `u16 addr`, `u8 mask`, `u8 shift`. `addr` is the `CRxxxx` 16-bit address used by DB.bin (page<<8 | reg).
  - `mask` is an AND-mask that clears the field (`mask = ~field`); bit range = zero bits of mask, `shift` = low bit.
  - `mask=0, shift=0` = whole byte (7:0). `addr=0` = not present.
  - Evidence: every pull/drive/mode ref in RTD2795T has `shift == lowest zero bit of mask` (0 violations of 327 refs); 311/327 refs equal a DB.bin FIELD's address and exact bit range, the other 16 are whole-byte port registers (`0xFFE2` etc.) that DB.bin splits differently.
- Section order is fixed; the counts differ per chip (table below). Counts are `u16` for sections 1-3 and 11, `u8` for 4-10 and 12.

## Sections [fw unless tagged]

| # | Section | Count | Record |
|---|---|---|---|
| 1 | pins | u16 | 376 B (below) |
| 2 | SPI drive strength | u16 | 214 B: pin name(100), signal name(100), ref, 10 B `08 00 01 02 03 04 05 06 00 cd` [?] |
| 3 | SPI slew rate | u16 | 206 B: pin name(100), signal name(100), ref, `00 01` [?] |
| 4-7 | four pin-pair lists | u8 | `id u8`, `0xCD`, pin A(100), pin B(100) |
| 8 | ADC singles | u8 | `id u8`, `0xCD`, port name(100), ref (whole byte) |
| 9 | ports | u8 | port name(100), ref, `01 00` [?] |
| 10 | timers | u8 | timer name(100), port name(100) |
| 11 | PWM channels | u16 | `id u8`, `0xCD`, 10 refs, `01 00` (refs 1-2 are followed by `00 01` [?]) |
| 12 | Schmitt-trigger registers | u8 | n x `u16 addr` |

- Section 2: refs point at the SPI pad drive-strength fields (`0x10C2` on RTD2795T; DB.bin: 3-bit, 2 mA..5.5 mA). The `08` is the number of codes [guess].
- Section 3: refs point at slew fields (`0x1080` USB_SPI, `0x1081` SPI; DB.bin "Slew Rate Control - SPI_SCLK").
- Sections 4-7 (pairs): lists of two port pins that form a two-wire function. Section 4 on RTD2795T = (P6.0, P6.1), DB.bin calls Pin149/Pin150 `iicscl1`/`iicsda1`. [fw for that pair]
  - Which function each of the four lists is (I2C master 1/2, DDC, ...) not established [?]. Empty lists occur (count 0, RTD2525AR list 2). `id` is a record label, `0xCD` = unset.
- Section 8: always 4 records, ports P3.7/P4.0/P4.1/P4.2 on RTD2795T -> `0xFF09..0xFF0C` = `ADC_A0..A3_CONVERT_RESULT` (Pin94-97 `a_adc*` in DB.bin). [fw]
- Section 9: `0xFE60`/`0xFE61` bit per port = `PORT_READ_CONTROL` "Source Selection for Px Read Back". [fw]
- Section 10: 4 timers (T0, T1, T2, T2EX) -> the port pin each is on. [guess: pin choice per chip; names fw]
- Section 11: always 10 refs in this order: `PWM_CK_SEL`, `PWM_CK`, `PWMnH_DUT`, `PWMnL_DUT`, `PWM_DUT_TYPE`, `PWM_M`, `PWMn_N_MSB`, `PWMn_N_LSB`, `PWM_EN`, `PWM_I2C_CLOCK_STOP` (DB.bin names match all 10 on RTD2795T). [fw]
- Section 12: RTD2795T has 0; others list `0x1076..0x1079` (`PIN_SCHMITT_CTRLn`). [fw]

| Chip | pins | SPI | pair recs | ports | PWM | Schmitt |
|---|---|---|---|---|---|---|
| RTD2795T | 77 | 13 | 6 | 10 | 6 | 0 |
| RTD2785TM / 2775TM | 89 | 13 | 7 | 12 | 6 | 2 |
| RTD2776B | 109 | 13 | 10 | 14 | 6 | 3 |
| RTD2797UPM | 105 | 13 | 8 | 14 | 6 | 3 |
| RTD2525AR | 56 | 8 | 7 | 7 | 4 | 4 |
| RTD2537T | 55 | 8 | 7 | 7 | 6 | 2 |

## Pin record (376 B)

| Off | Size | Meaning |
|---|---|---|
| 0 | 100 | package pin (`Pin149`; BGA ball letters like `Pin_AL` on RTD2776B/2797) [fw] |
| 100 | 100 | port name (`P6.0`, `PA.7`) [fw] |
| 200 | 100 | pad supply (`5V`, `3.3V`) [fw] |
| 300+0 | u8 | alt-function flags; bit0 set when an override below exists [?] |
| 300+4 | ref | "priority override" enable bit (`0x1002` bit 7 `ddcvga`, `0x1020` bit 7 `i2c_1`, `0x1024` bit 7 `usb_spi_en`); DB.bin text `<Priority>PinN ... 1: iicscl1` [fw] |
| 300+8 | 9 B | one-hot: index of the override function class (0 = DDC-VGA, 2 = I2C1, 4 = USB SPI on RTD2795T) [guess] |
| 300+20 | u8 | capability flags: bit0 input, bit1 push-pull output, bit2 open-drain output [fw: Pin74 AUX pad = 0x05, DB.bin lists in + OD only]; bits 4-7 = pin has PWM0..3 function [guess] |
| 300+21 | u16 | bitmap [?] |
| 300+24 | ref | pin-mode field (3 bits, `p4d0` etc.); code 0 = input [fw] |
| 300+30 | u8 x2 | mode code for push-pull / open-drain output (1 / 2 in every pin checked) [fw] |
| 300+32 | 12 B | PWM0..5: (push-pull code, open-drain code) pair, 3/4 when the pin can output that PWM, else 0 [fw: Pin150 -> pwm1=3/4, matches DB.bin `011: pwm1`] |
| 300+44 | 10 B | other mode codes by function slot (slot 0 = `a_adc*`, 2/3 = `int0`/`int1`, 6-9 = `test4b_out0..3` on RTD2795T P3.7/P4.0) [guess: slot meaning] |
| 300+56 | ref | port data bit (`0xFFE2` = PORT1_PIN_REG bit 0 = P1.0; ports P4+ use `0xFE00+n` bit 0) [fw] |
| 300+60 | ref | drive-strength field [fw] |
| 300+68 | ref | pull-up / pull-down field [fw] |
| 300+73 | u8 x2 | pull code for pull-up / pull-down; `0xFF` = unsupported [fw: 1-bit pull fields give `01 ff`] |
| 300+75 | u8 | `0xCD` pad |

- Cross-check vs DB.bin TSV (RTD2795T): the DB.bin description of the drive, pull, mode and priority field names the pin in 250 of 250 refs. Other chips: 2785TM 238/244, 2776B 339/354, 2797UPM 338/338, 2525AR 159/159, 2537T 153/160; the misses are wording differences in DB.bin (not checked one by one).
- Same port on RTD2795T vs RTD2785TM: data register + bit identical on 77/77; mode register 65/77; drive/pull registers differ (different pin-share layout per die).

## Not decoded

- Header `u32 x2` at 0x6C, the 8 unknown bytes at 0x74.
- Pair list meaning (which of the four is which function) and record `id` semantics.
- Pin record: flag bits 1-7 beyond the three direction bits, the u16 bitmap at +21, slot meaning at +44..+53, the 9-byte one-hot at +8.
- `01 00`, `00 01`, `08 00 01..06` filler words in sections 2, 3, 9, 11.
