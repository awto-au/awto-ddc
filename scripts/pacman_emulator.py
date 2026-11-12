#!/usr/bin/env python3
"""Pygame model of the Pac-Man OSD, driven by bytes from a linked firmware image.

This deliberately does not import the asset generator.  The glyph stream, tile
map, colours and palette are read back from BIN at the addresses in MAP.  That
makes packing, glyph-address and layout mistakes visible before hardware is
flashed.

The RTD2795 24x36 switch uses native 24x36/108-byte glyphs (36 SRAM words).
Treating it as a magnified 12x18/27-byte glyph is intentionally rejected.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import osd_vlc  # noqa: E402

PANEL_W, PANEL_H = 3840, 2160
MODEL_DIV = 2                         # 1920x1080 model; Pygame scales the window
GLYPH_GEOMETRY = {27: (12, 18), 108: (24, 36)}
WALL_FIRST, WALL_LAST = 3, 18
PAC_FIRST, GHOST = 19, 27


def symbol(map_text: str, name: str) -> tuple[int, int]:
    a = re.search(rf"^CH_{re.escape(name)}=0x([0-9a-fA-F]+)$", map_text, re.M)
    n = re.search(rf"^C:\s+([0-9a-fA-F]+)\s+l_CH_{re.escape(name)}\s*$", map_text, re.M)
    if not a or not n:
        raise SystemExit(f"{name}: address/length not found in map")
    return int(a.group(1), 16), int(n.group(1), 16)


def chunk(image: bytes, map_text: str, name: str) -> bytes:
    a, n = symbol(map_text, name)
    if a + n > len(image):
        raise SystemExit(f"{name}: {a:#x}+{n:#x} lies beyond {len(image):#x}-byte image")
    return image[a:a + n]


@dataclass
class Assets:
    slots: list[np.ndarray]
    logical_bytes: int
    glyph_w: int
    glyph_h: int
    fg: bytes
    grid: bytes
    phase: list[int]
    palette: list[tuple[int, int, int]]


def load_assets(bin_path: Path, map_path: Path, cells: int) -> Assets:
    image, mt = bin_path.read_bytes(), map_path.read_text(errors="replace")
    fg = chunk(image, mt, "pm_asset_fg")
    raw = chunk(image, mt, "pm_glyph_bytes")
    grid = chunk(image, mt, "pm_initial_map")
    phase_raw = chunk(image, mt, "pm_phase_glyph")
    pal_raw = chunk(image, mt, "tAwtoPacPalette")
    if len(grid) != cells:
        raise SystemExit(f"map has {len(grid)} cells, emulator geometry asks for {cells}")
    if not fg or len(raw) % len(fg):
        raise SystemExit(f"glyph stream {len(raw)} B is not divisible by {len(fg)} logical glyphs")
    logical_bytes = len(raw) // len(fg)
    if logical_bytes not in GLYPH_GEOMETRY:
        raise SystemExit(f"unsupported linked glyph size {logical_bytes} B")
    raw_w, raw_h = GLYPH_GEOMETRY[logical_bytes]
    # This is the hardware view: char id N addresses 27 bytes at N*27.  It is
    # intentionally not split using the generator's claimed logical size.
    slots = [np.array(osd_vlc.unpack_unit(raw[i:i + logical_bytes], raw_w, raw_h, 1), np.uint8)
             for i in range(0, len(raw), logical_bytes)]
    if len(phase_raw) % 2:
        raise SystemExit(f"phase table has odd byte length {len(phase_raw)}")
    phase = [int.from_bytes(phase_raw[i:i + 2], "big") for i in range(0, len(phase_raw), 2)]
    if any(g >= len(slots) for g in phase):
        raise SystemExit("phase table contains a glyph outside the linked font")
    palette = [(0, 0, 0)] + [tuple(pal_raw[i:i + 3]) for i in range(0, len(pal_raw), 3)]
    return Assets(slots, logical_bytes, raw_w, raw_h, fg, grid, phase, palette)


class Demo:
    def __init__(self, assets: Assets, cols: int, rows: int):
        self.a, self.cols, self.rows = assets, cols, rows
        self.x = [4, 36, 38, 40, 42]
        self.y = [30, 30, 30, 30, 30]
        self.direction = [0, 3, 3, 0, 2]       # right, down, left, up
        self.want, self.mouth = 0, 0
        self.eaten: set[tuple[int, int]] = set()

    def walkable(self, x: int, y: int) -> bool:
        if not (0 <= x < self.cols and 0 <= y < self.rows):
            return False
        g = self.a.grid[y * self.cols + x]
        return not WALL_FIRST <= g <= WALL_LAST

    def next(self, x: int, y: int, d: int):
        nx, ny = ((x + 1) % self.cols, y) if d == 0 else (x, y + 1) if d == 1 else \
                 ((x - 1) % self.cols, y) if d == 2 else (x, y - 1)
        return (nx, ny) if self.walkable(nx, ny) else None

    def step(self):
        self.mouth ^= 1
        for i in range(5):
            if i == 0 and self.next(self.x[i], self.y[i], self.want):
                self.direction[i] = self.want
            tries = (self.direction[i], (self.direction[i] + 1 + i) & 3,
                     (self.direction[i] + 3 - (i & 1)) & 3, (self.direction[i] + 2) & 3)
            for d in tries:
                p = self.next(self.x[i], self.y[i], d)
                if p:
                    self.x[i], self.y[i], self.direction[i] = *p, d
                    if i == 0 and self.a.grid[self.y[i] * self.cols + self.x[i]] in (1, 2):
                        self.eaten.add((self.x[i], self.y[i]))
                    break


def render(demo: Demo, char_w: int, row_h: int, font24: bool, double_x: bool, double_y: bool) -> np.ndarray:
    a, cols, rows = demo.a, demo.cols, demo.rows
    sx, sy = (2 if double_x else 1), (2 if double_y else 1)
    cw, rh = char_w * sx // MODEL_DIV, row_h * sy // MODEL_DIV
    glyph_w = a.glyph_w * sx // MODEL_DIV
    glyph_h = a.glyph_h * sy // MODEL_DIV
    if min(cw, rh, glyph_w, glyph_h) < 1:
        raise SystemExit("geometry is below the emulator's half-panel resolution")
    frame = np.zeros((PANEL_H // MODEL_DIV, PANEL_W // MODEL_DIV, 3), np.uint8)
    actors: dict[tuple[int, int], tuple[int, int]] = {}

    def actor(slot: int, frame_id: int, colour: int) -> None:
        off = frame_id * 4
        if off + 4 > len(a.phase):
            raise SystemExit(f"actor frame {frame_id} is absent from linked phase table")
        for part, gid in enumerate(a.phase[off:off + 4]):
            if gid:
                actors[(demo.x[slot] + (part & 1), demo.y[slot] + (part >> 1))] = (gid, colour)

    actor(0, demo.direction[0] * 2 + demo.mouth, 3)
    for i in range(1, 5):
        actor(i, 8, 4 + i)
    for y in range(rows):
        py = y * rh
        if py >= frame.shape[0]:
            break
        for x in range(cols):
            px = x * cw
            if px >= frame.shape[1]:
                break
            logical = a.grid[y * cols + x]
            if (x, y) in demo.eaten and logical in (1, 2):
                logical = 0
            gid, colour = actors.get((x, y), (logical, a.fg[logical] if logical < len(a.fg) else 0))
            # B2 background colour 1 is black for every cell in this firmware.
            frame[py:min(py + rh, frame.shape[0]), px:min(px + cw, frame.shape[1])] = a.palette[1]
            if gid >= len(a.slots) or colour >= len(a.palette):
                continue
            # Nearest-neighbour model of the panel scaling.  For the native
            # 24x36 font this downsamples only because MODEL_DIV=2.
            ys = np.arange(glyph_h) * a.glyph_h // glyph_h
            xs = np.arange(glyph_w) * a.glyph_w // glyph_w
            bits = a.slots[gid][ys[:, None], xs[None, :]]
            h, w = min(rh, bits.shape[0], frame.shape[0] - py), min(cw, bits.shape[1], frame.shape[1] - px)
            if h > 0 and w > 0:
                target = frame[py:py + h, px:px + w]
                target[bits[:h, :w] != 0] = a.palette[colour]
    return frame


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--cols", type=int, default=80)
    ap.add_argument("--rows", type=int, default=45)
    ap.add_argument("--char-width", type=int, default=24)
    ap.add_argument("--row-height", type=int, default=24)
    ap.add_argument("--font24", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--double-x", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--double-y", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--screenshot", type=Path)
    ap.add_argument("--steps", type=int, default=0, help="advance autonomous demo before the first frame")
    a = ap.parse_args()

    assets = load_assets(a.bin, a.map, a.cols * a.rows)
    print(f"firmware bytes: {a.bin}; {len(assets.grid)} map cells; {len(assets.fg)} logical glyphs; "
          f"{len(assets.slots)} hardware {assets.glyph_w}x{assets.glyph_h} slots; "
          f"{assets.logical_bytes} B/logical glyph")
    expected_bytes = 108 if a.font24 else 27
    if assets.logical_bytes != expected_bytes:
        raise SystemExit(f"PACKING ERROR: font mode expects {expected_bytes} B per glyph, "
                         f"linked firmware contains {assets.logical_bytes} B")
    print(f"geometry: {a.cols}x{a.rows}, char {a.char_width}x{a.row_height}, "
          f"font24={a.font24}, scale={2 if a.double_x else 1}x{2 if a.double_y else 1}; "
          "arrows steer, Esc/Q quits")

    import pygame
    pygame.init()
    flags = pygame.FULLSCREEN | pygame.SCALED if a.fullscreen else pygame.RESIZABLE
    screen = pygame.display.set_mode((1280, 720), flags)
    pygame.display.set_caption("AWTO Pac-Man — firmware-byte RTD OSD emulator")
    demo, clock, last = Demo(assets, a.cols, a.rows), pygame.time.Clock(), time.monotonic()
    for _ in range(max(0, a.steps)):
        demo.step()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_RIGHT: demo.want = 0
                elif event.key == pygame.K_DOWN: demo.want = 1
                elif event.key == pygame.K_LEFT: demo.want = 2
                elif event.key == pygame.K_UP: demo.want = 3
        now = time.monotonic()
        if now - last >= 0.120:
            demo.step(); last = now
        frame = render(demo, a.char_width, a.row_height, a.font24, a.double_x, a.double_y)
        surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
        surf = pygame.transform.scale(surf, screen.get_size())
        screen.blit(surf, (0, 0)); pygame.display.flip()
        if a.screenshot:
            a.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(surf, a.screenshot)
            print(f"screenshot {a.screenshot}")
            running = False
        clock.tick(60)
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
