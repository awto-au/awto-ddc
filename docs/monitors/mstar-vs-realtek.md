# MStar vs Realtek monitor scalers

Research as of 2026-11-19. Web-only; no hardware, no GitHub writes.
Tags: `[web-fact]` sourced below, `[inference]` our reading, `[unknown]` not found. A failed fetch was not treated as absence.

## Answer

- **Older?** Realtek is older as a company: founded 1987-10 (Hsinchu) vs MStar 2002 (spun off 2002-05). `[web-fact]`
- **Scalers, who was first?** Not settled. Earliest dated Realtek monitor-scaler evidence: RTD2523 datasheet, 2004-03. MStar's display IC line existed at its 2002 spin-off, but no dated MStar scaler datasheet was found. Genesis (1987, Markham) was the dominant LCD-control IC vendor in 2004 `[web-fact]`.
- **Copied?** No evidence found of copying, licensing or direct Realtek-vs-MStar litigation (`[unknown]`: searches returned none).
- **Who sued whom:** Genesis won an ITC ruling against MStar in 2004 (LCD image patent). Realtek is suing MediaTek (MStar's parent since 2012) over patent-licensing abuse, not chip copying.
- **288E2:** the MStar claim is not sourced. No web source found naming the 288E2 scaler. `[unknown]`

## Company dates

| Date | Event | Tag | Source |
|---|---|---|---|
| 1987-10 | Realtek founded, Hsinchu | web-fact | https://en.wikipedia.org/wiki/Realtek ; https://www.realtek.com/Article/Milestone |
| 1987 | Genesis Microchip founded, Markham, Ontario | web-fact | https://en.wikipedia.org/wiki/Genesis_Microchip |
| 1998 | Realtek listed, TWSE | web-fact | https://en.wikipedia.org/wiki/Realtek |
| 2000 | Genesis buys Faroudja (Sage in 2002) | web-fact | https://en.wikipedia.org/wiki/Genesis_Microchip |
| 2002-05 | MStar spun off from System General Technology; display and RFID lines moved to MStar | web-fact | https://en.wikipedia.org/wiki/MStar |
| 2002-2003 | Genesis sues Smart ASIC, Reality, Trumpion, then MStar | web-fact | https://www.cens.com/cens/html/en/news/news_inner_7396.html |
| 2004-04-16 | ITC rules MStar infringed Genesis US 5,739,867 (LCD image method); Trumpion and Reality not infringing | web-fact | https://www.cens.com/cens/html/en/news/news_inner_7396.html ; https://en.wikipedia.org/wiki/MStar |
| 2007-12-11 | ST acquires Genesis | web-fact | https://en.wikipedia.org/wiki/Genesis_Microchip |
| 2012-06-22 | MediaTek tender offer for 40-48 % of MStar | web-fact | https://en.wikipedia.org/wiki/MStar |
| 2012-08-14 | Merger agreement announced; tentative effective 2013-01-01 | web-fact | https://www.mediatek.com/press-room/mediatek-inc-and-mstar-semiconductor-inc-announce-merger-agreement |
| 2020-10-14 | ITC investigation of MStar over DivX patents | web-fact | https://en.wikipedia.org/wiki/MStar |
| 2026-02-25 | Realtek antitrust case vs MediaTek, IPValue, Future Link survives summary judgment (N.D. Cal.) | web-fact | https://www.orrick.com/en/News/2026/02/Realtek-Secures-Key-Antitrust-Win-in-Smart-TV-Chip-Dispute |

Exact MediaTek completion date: `[unknown]` (only the 2012 announcement and 2013 tentative date were fetched).

## Scaler lineage

| Year | Realtek | MStar | Tag / source |
|---|---|---|---|
| 1993 | RTG3108 window accelerator (not a scaler) | - | web-fact: milestone page |
| 2002 | - | display IC line inherited at spin-off | web-fact: en.wikipedia.org/wiki/MStar |
| 2004-03 | RTD2523 datasheet rev 0.18: dual DDC incl. DDC/CI, zoom scaling, no external memory | - | web-fact (datasheet mirror, date from mirror page): https://datasheet4u.com/datasheets/Realtek/RTD2523/584370 |
| 2008 | RTD2485D "All-In-One LCD Monitor Controller" award | - | web-fact: milestone page |
| 2009 | RTD1073 media processor (TV/STB, not monitor) | - | web-fact: milestone page |
| 2015 | RTD2999 4K TV SoC | - | web-fact: milestone page |
| 2019 | RTD2893 8K decoder/processor | - | web-fact: milestone page |
| 2022 | RTD2892NND AI super-resolution IC | - | web-fact: milestone page |
| 2023-12-01 | - | MST9U13Q1: 4096x2160 monitor IC, DP 1.2a, HDMI 2.0, 32-bit MCU, RTE | web-fact (distributor page, updated 2023-12-01): https://www.globalsources.com/knowledge/mstar-ic-for-uhd-lcd-controller-boards/ |
| ? | RTD2023L, RTD2120, RTD2660/2662, RTD2785/2795 (datasheets exist) | TSUM56AL, MST9131, TSUMV59XU-Z1 (datasheets exist) | `[unknown]` dates: datasheet listings only, e.g. https://datasheet4u.com/datasheets/Realtek/RTD2120/646143 , https://datasheet4u.com/datasheets/Mstar/TSUM56AL/769321 |

Predecessors (not researched in this pass): Pixelworks, Sigma, Averlogic, Trumpion, Smart ASIC.
- Trumpion, Reality, Smart ASIC: named as Taiwanese LCD control IC vendors in the 2002-2004 Genesis suits `[web-fact]` (CENS link above).
- Genesis: >50 % world LCD-control IC share claimed in 2004 `[web-fact, CENS claim]`.
- Pixelworks, Sigma, Averlogic: `[unknown]`.

## Architecture: similarities and differences

Similarities
- Embedded 8051-class MCU runs the scaler config, OSD and keys. Realtek: `[web-fact]` RTD2120 listing "8051 Embedded Micro" (https://www.qdatasheet.com/pdf-view/RTD2120-Realtek, search snippet only). MStar: `[web-fact]` README "embedded 8051 microcontroller ... configure registers, monitor signal, keypad" (https://github.com/csurf/mstar). Repo: `docs/reversing/realtek-rtd/mcu-8051.md` (not read in this pass).
- External SPI flash holds firmware. MStar: SOIC-8 EEPROM/SPI flash, image sized to chip, 128k or 64k (csurf README). Realtek: repo docs (`docs/self-flash.md`, `docs/flash-layout.md`), not web-sourced.
- ISP over the DDC I2C bus. MStar: `[web-fact]` `flashrom -p mstarddc_spi:dev=/dev/i2c-1:0x49` (csurf README). Realtek: `[inference]` 0x4A per repo docs (`docs/ddc-control.md`, `docs/flash-burst.md`); no web source found, so `[unknown]` web-side.
- DDC/CI from the MCU. Realtek: `[web-fact]` RTD2523 datasheet. MStar: `[measured, repo]` `docs/monitors/README.md:99` reports VCP 0xC8 = MStar, controller 0x16, fw 1.0, on one monitor (a different unit from the one in `awto-ddc#1`, which is titled Realtek).

Differences (verified)
- Build tool: MStar firmware is a Keil uVision project `[web-fact]` (csurf README). Ours is SDCC `[repo]` (CLAUDE.md, awto-sdcc#36).
- Newer MStar parts move to a 32-bit MCU `[web-fact]` (MST9U13Q1 listing). RTD2120 is listed as an 8051 part `[web-fact]`; the 8051-to-later-core path for Realtek is `[unknown]`.
- Realtek ISP link: 0x4A `[repo]`; MStar: 0x49 with the flashrom "mstarddc_spi" driver `[web-fact]`.

Not verified on either side `[unknown]`
- Register map organisation: Realtek page/offset (8-bit) and MStar banks are both claims from our notes; no web datasheet confirmed either.
- "MSTAR" magic string in ISP; OSD architecture; ADC key scanning; DDC/CI factory-mode entry; firmware header format.

## Litigation, licences, shared IP

- Genesis v MStar, ITC 2004: `[web-fact]` patent on LCD image improvement; ITC ruled MStar infringed on 2004-04-16 (CENS link above). Final ruling and appeal outcome: `[unknown]`.
- Realtek v MediaTek (and IPValue, Future Link): `[web-fact]` antitrust over patent "bounty" licensing; not chip copying (Orrick link above).
- Realtek v MStar: `[unknown]` no record found.
- Shared third-party IP:
  - Genesis video IP (DCDi, MADi, scaling) and DisplayPort founders: `[web-fact]` Wikipedia Genesis. Whether MStar or Realtek licensed any: `[unknown]`.
  - DW8051 core is Synopsys IP `[web-fact]` (https://www.synopsys.com/dw/ipdir.php?c=DW8051). Whether either vendor licenses it: `[unknown]`.
- Clone products: none found `[unknown]`.

## 288E2 and 4K monitors circa 2023

- Philips 288E2 (288E2E/288E2UAE): panel Innolux M280DCA-E3B; scaler vendor not named in any fetched page (https://pcmonitors.info/reviews/philips-288e2uae-288e2e/, 2021-05-18). `[unknown]`
- Why MStar might be used: `[inference]` MStar sells 4K monitor ICs (MST9U13Q1) through agents at low unit cost (`$28 FOB, MOQ 100`, Global Sources listing). Not evidence that the 288E2 uses one.
- Brand scaler vendors (Dell, LG, Samsung, AOC, Philips/TPV, 2023): `[unknown]`.
  - One MStar agent's listing names AOC, Samsung, BenQ, ViewSonic, Lenovo, HKC as clients `[web-fact, supplier claim]` (Global Sources link above).
  - A Chinese CSDN article compares Realtek, MStar and Novatek (undated, unverified): https://wenku.csdn.net/doc/3z0y489jmz

## Open

- Date the first Realtek RTD25xx and MStar TSUM/MST monitor scalers from datasheet revisions (not from listing pages).
- Fetch the 288E2 teardown or service manual (documents.philips.com) for the scaler part number.
- Pixelworks, Sigma, Averlogic predecessors.
- Filing: none. Brief said no GitHub writes; findings above are not filed as issues.
