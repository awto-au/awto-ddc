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
