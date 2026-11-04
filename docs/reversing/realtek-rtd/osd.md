# RTD2795-class OSD: hardware facts and host-driven access

Tags: `[spec from regdb]` = RTD2795T-CG register DB (`re/regdb/`); `[measured]` = our bus 20 test 2026-11-04; `[oss-understood]` = sequence understood from public sources, re-derived, not copied; `[guess]` = unverified.
Code: `scripts/rtd_osd.py` (clean-room; imports `rtd_isp_probe`). Log: `tmp/logs/rtd_osd.log`.

## Access path
- ISP session: `0x6F=0x80` at I2C 0x4A, scaler regs via `F4=index`, `F5=data` [measured].
- Page select = scaler reg `0x9F`; 16-bit reg `0xPPRR` = page `PP`, index `RR` [spec from regdb].
- OSD ports `0x90-0x94` (page 0) reach through F4/F5: write/read-back of `0x90`/`0x91` verified [measured].
- Direct subaddress path (`0x90..0x94` as ISP regs at 0x4A) not tried: those subaddresses belong to the ISP block (`0x60-0x6F` SPI engine, `0xEE`).
- After reset, firmware state: `0x93=0x00`, `0x94=0x80` leftover, `0x3A02` osd_en=1 (firmware OSD running) [measured].

## OSD access port (page 0) [spec from regdb]
| reg | name | fields |
|---|---|---|
| 0x90 | OSD_ADR_PORT_MSB | [6:0] addr MSB (15-bit word address) |
| 0x91 | OSD_ADR_PORT_LSB | [7:0] addr LSB |
| 0x92 | OSD_DATA_PORT | data |
| 0x93 | OSD_MISC_PORT | [7] db_enable (reset 1), [5] sram_read_select (0=M1, 1=M2) |
| 0x94 | OSD_WRITE_OPTION | [7:5] bytesel 001=B0 010=B1 100=B2 111=all 000=reset; [3:2] sram_sel 00=window regs, 10=font select + font map SRAM |

- Must write `0x94=0x00` (and sram_sel 00) before clearing osd_en (SRAM CS otherwise stuck high).
- Every OSD entry is a 3-byte word (Byte0, Byte1, Byte2); regdb names them LSB/MSB/HSB.
- Write: `0x94 = bytesel<<5 | sram_sel<<2`; `0x90/0x91 = word addr`; three data-port writes with bytesel=111 [measured: write+read-back of window word 0x120 exact].
- Read-back: select one plane (bytesel one-hot), set address, read data port; address auto-increments per data access [measured: +1 per single-plane read].
- Window SRAM read-back works [measured]. Font SRAM read-back returned zeros for all combos tried (sram_read_select 0/1, any plane, sram_sel 01/10/11) [measured]: font SRAM is not verifiable by read-back from this path [guess: write-only or different read mechanism].

## Window control block (sram_sel=00) [spec from regdb]
- Indexed through the same ports: word index = `port_idx` in regdb (decimal 256 = 0x100).
- WINn base word: n=0..9 at `0x100 + 4*n` (WIN0 0x100, WIN1 0x104, ... WIN9 0x124).
- Extended sets: WIN4_1..4_8 from 0x200 step 4, WIN5_1..5_8 from 0x220 step 4 (more words per window: ADR4..ADR10 exist for WIN4/5, ADR5-8 only on a few).
- Per window word layout (bytes B0=LSB, B1=MSB, B2=HSB):

| word | B0 | B1 | B2 |
|---|---|---|---|
| ADR0 | [7]sha_color[4] [6]bor_color[4] [5:3]eff_width-1 [2:0]eff_height-1 | [7:4]sha_color[3:0] [3:0]bor_color[3:0] | [7:5]gradient polarity RGB [4:3]gra_step [2:0]gra enable RGB (WIN0 only; WIN1+ reserved) |
| ADR1 | [7:4]hor_sta[11:8] [3:0]ver_sta[11:8] | hor_sta[7:0] | ver_sta[7:0] |
| ADR2 | [7:4]hor_end[11:8] [3:0]ver_end[11:8] | hor_end[7:0] | ver_end[7:0] |
| ADR3 | [7]sha_color[5] [6]bor_color[5] [5]win_color[5] [4]gra_sat_en [3]gra_rev_en [2]osd_delay_sel [0]gra_level_ext | [7:5]gra_level [4:0]win_color[4:0] | [7]blend_en [6]gra_en [5]gra_dir [4]eff_en [3:1]eff_opt [0]win_en |

- Colour indices are 6 bits into the 64-entry LUT.
- Geometry effective at Vsync when global double buffer on; `win_en` byte excluded from double buffering.
- Measured firmware WIN0 (boot state) [measured]: ADR1 = 00 00 04, ADR2 = 00 9C 50, ADR3 = 00 04 81 -> start (0,4), end (156,80), colour 4, win_en+blend. Confirms the table (B0 high nibbles, B1 horizontal, B2 vertical).
- Window priority vs font: `FRAME_CTRL_07/08` winN_higher_font bits (win3 0x3A07[0], win4 [1], win2 0x3A08[7], win8 [5], win9 [6]); win7 mask option 0x3A07[3].

## Frame control (page 0x3A) [spec from regdb]
| reg | fields |
|---|---|
| 0x3A00 | vert_delay1[10:3] (unit 1 line) |
| 0x3A01 | hori_delay1[9:2] (unit 4 px, or 1 px if 0x3A06[4]) |
| 0x3A02 | [7:6]hori_delay1[1:0] [5:3]vert_delay1[2:0] [2:1]disp_zone [0]osd_en |
| 0x3A03-05 | second delay set (delay2), selected per window by osd_delay_sel |
| 0x3A06 | [4]hori_delay_step_sel [3:2]/[1:0] delay bits 11:10 |
| 0x3A0A | [3:2]alpha_blend_type [1]db_width [0]db_height (2x scale of whole OSD) |
| 0x3A0B | [7:6]f_dl_swap [2]hw_rotate_en [0]rotation (font download rotation) |
| 0x3A0C | fs_base[7:0] |
| 0x3A0D | [7:4]fs_base[11:8] [3:0]font_base[3:0] |
| 0x3A0E | font_base[11:4] |
| 0x3A0F-0x3A14.. | vlc_N: 4-bit values for VLC-compressed font decode |
- Other: `0x01DC[3]` osd_clken (reads 1 at boot), `0x002B` OSD_REF_DEN, `0x006C`/`0x008F` alpha_blending_level, `0x3A07[2]` f4b_color_sel.
- Firmware boot values [measured]: `0x3A00=0x02 0x3A01=0x6C 0x3A0C=0x19 0x3A0D=0x01 0x3A0E=0x3F 0x3A0A=0x0B` -> fs_base=0x019, font_base=0x3F1, double width+height+alpha type 10.

## Palette
- 64 entries x 24 bit: page 0 `0x6E` = `0x80 | index` (lut_acc_en + 6-bit address), then bytes to `0x6F` (COLOR_LUT_PORT, write-only) [spec from regdb].
- Byte order R,G,B per entry and write-pointer behaviour [guess]; library re-writes `0x6E` per entry and clears it after.
- Window/font colour fields are indices into this LUT; 1-bit font fg/bg indices only 4 bits each in the char entry [oss-understood].

## Font select / font map SRAM (sram_sel=10)
- Two regions, pointed to by `fs_base` (font select = text map) and `font_base` (glyph bitmaps), 12-bit each (word units) [spec from regdb for the pointers; structure is oss-understood].
- Glyph, 1 bit/pixel, 12x18 cell = 216 bits = 9 words; glyph N at `font_base + 9*N` [oss-understood; pack order of lines within the 24-bit word is a guess, `--pack 0|1|2` in the tool].
- Map: per text row a row-command word then one word per character, then terminator [oss-understood].
  - Row command (height, width, length) in B0/B1/B2 [guess: our library writes 18,12,N].
  - Character word: B0 = (bg<<4)|fg colour index, B1 = glyph index, B2 = 0 [guess].
- M1/M2 SRAM must be written together (regdb sram_sel note): the 3-byte all-planes write does this.

## draw-test sequence (what `rtd_osd.py <bus> draw-test` writes)
1. `0x6E/0x6F`: LUT[1]=00 00 A0 (window blue), LUT[2]=FF FF FF (text fg), LUT[3]=C0 00 00 (text bg).
2. `0x93=0x00` (db_enable off), `0x01DC |= 0x08` (osd_clken).
3. `0x94=0xE8` (all planes, font SRAM). Glyph words for " HELO" at word 0x100 + 9*idx.
4. `0x3A0C=0x00`, `0x3A0D=0x00`, `0x3A0E=0x10` (fs_base=0, font_base=0x100).
5. Map at word 0: row cmd (18,12,5), 5 char words (0x32, idx, 0), terminator.
6. `0x94=0xE0` (window SRAM): WIN0 words 0x100..0x103: start (0,0), end (68,40), colour 1, win_en.
7. `0x3A00=0x08`, `0x3A01=0x20` (OSD origin ~ (128 px, 64 lines)); `0x3A02 |= 1`.
- Expected visible: a blue rectangle (high confidence: window layout matches the measured firmware window). Text visible only if the map row-command and char-word guesses are right.
- Reset (0xEE=0x02) at the end reboots the monitor and discards all of it.
