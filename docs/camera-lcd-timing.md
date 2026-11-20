# Camera LCD timing (cam_frames)

Measures in the video itself how long after a restart the LCD shows a good picture, and whether a start-up flash exists. `./dev.py camframes capture|runs|analyse` (`scripts/cam_frames.py`).

## Setup (2026-11-20)

- Camera us48-port1-camera (Dahua IPC-HFW4631H-ZSA), RTSP over TCP, `-c copy` recording; login in env `AWTO_CAM_USER` / `AWTO_CAM_PASS` (or a `camera` section of `~/.config/awto/secrets.yaml`), never in a file.
- Sees unit 3 (top screen, AWT26110003): left diag console + right desktop; the VLC window of the camera's own picture sits top right (kept out of the ROI). Units 1 and 2 are not in frame (reset / note / sleep on them changed nothing in the video).
- ROI (fractions of the frame, same for main and sub stream): background `0.62,0.56,0.96,0.78` (flat desktop colour, clear of VLC window and head); console text `0.04,0.24,0.58,0.73`.
- Sub stream (704x576, 25 fps) and main stream (2592x1944) gave identical event frames in all 5 reset runs: the sub stream is enough.
- Clip starts 3 s before the trigger (GOP 50 = 2 s to the first IDR), 10 s after.

## Events (per run, frame = 40 ms)

| event | detector |
|---|---|
| last good picture | last frame with ROI luminance Y within 12 % of the pre-reset level |
| screen dark | first frame with Y < 0.6 x pre-reset |
| first light | first frame with Y above the dark floor by >= 8 and 10 % of the span |
| flash | frames between first light and the stable picture, Y > 1.25 x pre-reset and neutral colour (white / grey) |
| console text visible | green / cyan text pixels in the console ROI > 50 % of the final count |
| picture present (stable) | desktop colour back, (B-G)/Y >= half the pre-reset value, held 5 frames |
| settled | picture present + console text, held 10 frames |

- Picture = colour, not brightness: camera auto exposure drifts for ~3 s after a dark / white phase (Y 147 down to 83 with the same picture).
- Rolling shutter: a frame can show the old and new picture split at a scan line; transitions are +-1 frame.
- Camera and host clocks are not synchronised: only frame counts inside a clip are used.

## Results (2026-11-20, unit 3, image 93c6fd40, ISP warm reset, 25 fps sub stream, frames inside the video)

- Dark -> valid picture (desktop + console back, held 5 frames): 1360..1480 ms in 100 of 100 reset runs with the pin before ~1.3 s (median 1440 ms, +-40 ms frame quantisation); firmware ACTIVE (sync log): 1402..1475 ms. Firmware ACTIVE matches the LCD within one frame.
- Camera dark -> first light minus firmware pin-on (E1, ms after MCU boot) = 113..145 ms in every run: the camera's dark onset leads the firmware ms origin by the ~113 ms boot-reason time; spread = 1 frame.
- Default image (pin on at MCU boot + 15 ms): white flash, 5-6 frames (200-240 ms), 9 of 9 runs. Panel then shows black + console log from ~+0.4 s, desktop at 1.44 s.
- Knob, delay counted from power-up (`bl-sweep --ref powerup`, 3 runs per value; pin = MCU boot ms): 15 -> 5 / 5 / 6 flash frames; 91 (N = 20, 40, 60) -> 0 / 0 / 0 in all 9 runs; 101 (N = 80), 158 (N = 100, 140), 143 .. 1642 (coarse sweep, 3 runs each) -> 0 flash frames. No value >= 91 ms flashed.
- Delay from stream on (`--ref stream`, N = 0 / 100 / 300) and from ACTIVE (N = 0 .. 400, 21 runs): 0 flash frames in all runs.
- The flash is a panel start-up state, not tied to video: white from the backlight pin edge until ~200-240 ms later if the pin comes within the first ~100 ms after MCU boot; later pins show black (+ console once drawn). Reference event does not matter, absolute time after reset does.
- Sleep / wake (DDC/CI sleep, 3 s hold, wake; `--kind wake --ref powerup`, 3 runs per value): the monitor lights itself ~1.5 s after the sleep command (white flash 4 / 4 / 5 frames at N = 0, 0 frames at N = 200 / 400 / 1000), desktop returns 5.1-5.2 s after the sleep command. Same flash, same cure; the sleep-path events are timed from the sleep command, not the wake.

## Camera limits

- 25 fps = 40 ms per frame; rolling shutter splits a frame (old / new picture at a scan line): +-1 frame on every edge. A flash shorter than ~40 ms may fall between exposures or show as one partial frame; shorter than ~20 ms may be missed (exposure is ~1/50 s indoors).
- Auto exposure: a dark phase of 1-2 s lifts the screen from Y 21 to ~60 and a following picture is overexposed (Y 180 vs 74 pre-reset) for ~3 s; levels are only compared inside one restart, picture detection uses colour + a step (not a brightness level). A white flash reads Y 180-225, a lifted black screen <= 97 (FLASH_MIN_Y 140).
- Host and camera clocks are not synchronised: counts are inside the video; the alignment with the firmware log is dark -> first light vs E1 (see above), +-1 frame.
- Needs a tinted desktop (purple wallpaper) for the picture test; a neutral desktop falls back to the screen std (SD_FLAT) and is less reliable.
