## First flash change: replace Dahua boot splash with awto logo

User confirmed: monitor shows a Dahua logo splash at boot. Goal: replace it with an awto logo.

This is the FIRST flash WRITE (everything so far was volatile register/OSD writes). Flash write is the only
brick risk. Safeguards before any write:
- 3 full 1 MiB dumps already saved (~/vendors/realtek/analysis/dumps/). Take a 4th fresh dump of the target
  unit and diff against its earlier dump (must match) right before writing.
- Patch only the logo sector(s); keep everything else byte-identical. Sector = 4 KB.
- Realtek 16-bit additive checksum: recompute if the tool/boot checks it (Dizi0 notes). Verify whether THIS
  firmware checks it before relying on it.
- Write via our ISP path (rtd_isp_probe.py program path — not yet used for write) OR RTDCustomerTool. Read back
  and compare every written sector. Keep the original sector bytes to revert.
- ISP recovery survives a bad image (boot ROM). SOIC-8 clip on the Macronix chip as last resort.

To find (agent):
- The boot logo bitmap in the image. Dizi0 RTD2556 notes: logo in bank 06, enable byte 0x00015, boot-logo
  bypass flag; our bank6 (0x60000) is ~97% used 0x60000-0x66800 then tails off. Find: logo pixel format
  (1bpp? palette indices? width/height header), its exact offset+length, the palette, and the enable flag.
- Whether the logo is drawn via the OSD font/window path (then it's glyph/tile data) or a dedicated splash
  bitmap blitter. Cross-ref bank6 code that reads the region.
- The awto logo: get/make a monochrome or few-colour bitmap sized to the splash dimensions.

Deliverable: docs/boot-logo.md (format, offset, how it's drawn, checksum behaviour, exact patch plan + revert).
No write yet — plan for review first.
