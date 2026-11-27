🤖 Dan 2026-11-25 asks: is the scene data DRAM filled via HDMI or DP video input? Options for the per-map scene (E1M1 1,662,976 B, E1M9 2,469,888 B; zipped 334 KB to 612 KB):

- **A. Video input (HDMI or DP) as a data frame.** Host shows the scene as pixels; the scaler captures the frame into DDR with no CPU cost.
  - One 1080p RGB frame is about 6.2 MB (1920 x 1080 x 3), so a whole scene fits in one frame.
  - Needs a lossless capture path: no colour matrix, scaler, dither or chroma conversion, RGB 4:4:4 at 8 bit. Unverified.
  - The data lands at the capture-buffer address, not at Doom's DDR addresses (A6010, 140010, 160010, 800010); either move Doom's layout or copy within DDR.
  - Check: one run on unit 3, known pattern in, DDR read back over the debug link, compare bytes.
- **B. Debug link / DDC-CI I2C.** Needs no video mode, but link rate bounds it: 1 Mbit/s is at most about 111 KB/s, so the unzipped scene takes at least 15 s to 23 s per map. Zipped adds a decompress on the 8051.
- **C. Flash.** Not an option: 2 spare banks (131,072 B) against 1.66 to 2.47 MB.

Recommendation: A, gated on the byte-exact capture check; B as the fallback. Decision for Dan: A, B or both.
