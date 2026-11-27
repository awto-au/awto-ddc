Title: OSD diagnostics console does not scroll (unit 3, rotdef3)

- Seen by Dan 2026-11-13 ~13:55+11:00 during the speaker ear test on unit 3 (image `AWT26110003-wb-p14ui-rotdef3-be`, Rotate 180 + OSD rotated).
- Dan: "the scroll does not work".
- Console opened by test cmd 0x26 (held); lines from VCP 0x63 step/tone announces (`audio test N/6: ...`, `audio test N: F Hz`), about 25 lines in 70 s.
- Open: does scroll fail only with the OSD rotated 180 (mirrored map / turned glyphs, rot5)? A/B on Rotate 0 vs 180.
- Clear now exists: `./dev.py diag-clear --unit N` (test cmd 0x27).
