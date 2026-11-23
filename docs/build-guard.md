# dev.py build guard (#316)

- `./dev.py build` takes `tmp/locks/build.lock` in the main checkout (shared by every worktree): one build at a time per machine.
- A second build prints the holder (pid, tree, since) and waits up to `AWTO_BUILD_WAIT_S` (600 s), then exits without building.
- Start refused when `MemAvailable` < `AWTO_BUILD_MIN_AVAIL_MB` (12288).
- Measured 2026-11-23, warm ccache, one build: 57 s wall, largest single process 5.7 GB RSS (`/usr/bin/time -v`); 28 parallel sdcc jobs of ~0.1 GB each.
- Two builds do not reach 44 GB alone; the 2026-11-23 oomd kill was a scope already full (#316).
- Code: `scripts/build_guard.py`, test `tests/test_build_guard.py`.
