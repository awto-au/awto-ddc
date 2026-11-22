#!/usr/bin/env python3
"""Classic-layout Pac-Man demo for the OSD (awto-ddc#227 side project): 28 x 36 tiles, the arcade tile grid, drawn procedurally.

usage: gen_pacman_classic.py [--steps N] [--png OUT] [--check]
  Original artwork (no ROM data): the 28 x 31 maze as ASCII (public layout description), outline walls autotiled from the 8 neighbours,
  dots / power pellets, Pac-Man (mouth frames x 4 directions, 1 bit), ghosts (2 bit: body / white eye / blue pupil, 4 directions x 2 feet
  frames, recoloured per cell), 5 x 7 text. Glyphs are 12 x 18 one-bit (9 words) or two-bit (18 words); only 12 x 12 of each is visible.
  A scripted demo (Pac-Man eats, four ghosts chase with the classic targets) runs N steps; every step is recorded as cell updates.
  Writes fw/test/pacman_classic_data.inc (see fw/test/pacman_classic.c for the layout) and, with --png, a sheet of the first / last frame.
Log: ./tmp/logs/gen_pacman_classic.log
"""
import argparse
import math
import sys
from pathlib import Path

import osd_gfx as OG
from _repo import ROOT

OUT = ROOT / "fw/test/pacman_classic_data.inc"
LOG = ROOT / "tmp/logs/gen_pacman_classic.log"
COLS, ROWS = 28, 36
MAZE_TOP = 3                                  # tile row of maze row 0 (3 score rows above, 2 spare below)
W, H, VIS = 12, 18, 12                        # glyph 12 x 18, visible 12 x 12
STEPS = 260
BANK_A, BANK_B, BANK_C = 12, 11, 13       # C: cell table, off bank 12 so no bank 12 const covers xdata 0xF0xx (fw_link_check gptr_const_xbank)
DELTA_B_MAX = 7200                            # bytes of delta stream in bank 11 (multiple of the record size)

# Palette: index 0 transparent, 1 opaque black (cell background), then colours.
PAL = [(0, 0, 0), (0, 0, 0), (33, 33, 222), (255, 255, 0), (255, 255, 255), (255, 0, 0), (255, 184, 255), (0, 255, 255),
       (255, 184, 82), (33, 33, 255), (255, 184, 174), (222, 151, 81)]
K_BG, K_WALL, K_YEL, K_WHITE, K_RED, K_PINK, K_CYAN, K_ORANGE, K_BLUE, K_DOOR = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
GHOST_COL = [K_RED, K_PINK, K_CYAN, K_ORANGE]

MAZE = """
############################
#............##............#
#.####.#####.##.#####.####.#
#o####.#####.##.#####.####o#
#.####.#####.##.#####.####.#
#..........................#
#.####.##.########.##.####.#
#.####.##.########.##.####.#
#......##....##....##......#
######.##### ## #####.######
######.##### ## #####.######
######.##          ##.######
######.## ###--### ##.######
######.## #      # ##.######
      .   #      #   .
######.## #      # ##.######
######.## ######## ##.######
######.##          ##.######
######.## ######## ##.######
######.## ######## ##.######
#............##............#
#.####.#####.##.#####.####.#
#.####.#####.##.#####.####.#
#o..##.......  .......##..o#
###.##.##.########.##.##.###
###.##.##.########.##.##.###
#......##....##....##......#
#.##########.##.##########.#
#.##########.##.##########.#
#..........................#
############################
""".strip("\n").split("\n")

FONT = {
    '0': '01110/10001/10011/10101/11001/10001/01110', '1': '00100/01100/00100/00100/00100/00100/01110',
    '2': '01110/10001/00001/00010/00100/01000/11111', '3': '11110/00001/00001/01110/00001/00001/11110',
    '4': '00010/00110/01010/10010/11111/00010/00010', '5': '11111/10000/10000/11110/00001/00001/11110',
    '6': '01110/10000/10000/11110/10001/10001/01110', '7': '11111/00001/00010/00100/01000/01000/01000',
    '8': '01110/10001/10001/01110/10001/10001/01110', '9': '01110/10001/10001/01111/00001/00001/01110',
    'A': '01110/10001/10001/11111/10001/10001/10001', 'C': '01111/10000/10000/10000/10000/10000/01111',
    'D': '11110/10001/10001/10001/10001/10001/11110', 'E': '11111/10000/10000/11110/10000/10000/11111',
    'G': '01111/10000/10000/10011/10001/10001/01111', 'H': '10001/10001/10001/11111/10001/10001/10001',
    'I': '01110/00100/00100/00100/00100/00100/01110', 'O': '01110/10001/10001/10001/10001/10001/01110',
    'P': '11110/10001/10001/11110/10000/10000/10000', 'R': '11110/10001/10001/11110/10100/10010/10001',
    'S': '01111/10000/10000/01110/00001/00001/11110', 'U': '10001/10001/10001/10001/10001/10001/01110',
    'Y': '10001/10001/01010/00100/00100/00100/00100', '!': '00100/00100/00100/00100/00100/00000/00100',
    ' ': '00000/00000/00000/00000/00000/00000/00000',
}


say = OG.logger(LOG)


# ---------------------------------------------------------------- glyph pixels (lists of rows of ints, H rows x W cols)
def blank():
    return [[0] * W for _ in range(H)]


def put(g, x, y, v=1):
    if 0 <= x < W and 0 <= y < VIS:
        g[y][x] = v


def is_wall(m, x, y):
    if y < 0 or y >= len(m) or x < 0 or x >= len(m[0]):
        return False
    return m[y][x] in "#-"


def wall_glyph(m, x, y):
    """Outline of the wall region: a 2 px line along every edge towards an open tile, joined at concave corners, rounded at convex ones."""
    g = blank()
    o = {(dx, dy): not is_wall(m, x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)}
    edge = lambda p: range(2) if p < 0 else range(10, 12)
    for (dx, dy) in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if o[(dx, dy)]:
            if dx:
                for yy in range(VIS):
                    for xx in edge(dx):
                        put(g, xx, yy)
            else:
                for xx in range(W):
                    for yy in edge(dy):
                        put(g, xx, yy)
    for (dx, dy) in ((-1, 0), (1, 0), (0, -1), (0, 1)):                     # second thin line 4 px in, where the wall is thick (the arcade's double line)
        if o[(dx, dy)] and is_wall(m, x - dx, y - dy) and is_wall(m, x - 2 * dx, y - 2 * dy):
            if dx:
                xx = 4 if dx < 0 else 7
                for yy in range(VIS):
                    put(g, xx, yy)
            else:
                yy = 4 if dy < 0 else 7
                for xx in range(W):
                    put(g, xx, yy)
    for (dx, dy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):                   # concave corner: both neighbours wall, the diagonal open
        if o[(dx, dy)] and not o[(dx, 0)] and not o[(0, dy)]:
            for xx in edge(dx):
                for yy in edge(dy):
                    put(g, xx, yy)
    for (dx, dy) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):                   # convex corner: both neighbours open: cut the corner pixel
        if o[(dx, 0)] and o[(0, dy)]:
            cx, cy = (0 if dx < 0 else 11), (0 if dy < 0 else 11)
            put(g, cx, cy, 0)
    return g


def circle(cx, cy, r):
    return lambda x, y: (x + .5 - cx) ** 2 + (y + .5 - cy) ** 2 <= r * r


def pac_glyph(direction, opening):
    g = blank()
    inside = circle(6, 6, 5.6)
    ang = math.radians((0, 12, 28, 44)[opening])
    base = (0.0, math.pi / 2, math.pi, -math.pi / 2)[direction]                # right, down, left, up
    for y in range(VIS):
        for x in range(W):
            if inside(x, y):
                a = math.atan2(y + .5 - 6, x + .5 - 6) - base
                a = (a + math.pi) % (2 * math.pi) - math.pi
                if opening and abs(a) < ang:
                    continue
                g[y][x] = 1
    return g


def ghost_glyph(direction, feet):
    """2-bit: 1 body, 2 white eye, 3 blue pupil, 0 background."""
    g = blank()
    for y in range(VIS):
        for x in range(W):
            if y < 6:
                if (x + .5 - 6) ** 2 + (y + .5 - 6) ** 2 <= 5.8 ** 2:
                    g[y][x] = 1
            elif y < 11:
                g[y][x] = 1
            else:                                                            # wavy bottom: two phases
                if (x + (feet * 2)) % 4 in (0, 1):
                    g[y][x] = 1
    dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[direction]
    for ex in (3, 8):
        for yy in range(3, 8):
            for xx in range(ex - 1, ex + 2):
                if abs(xx - ex) <= 1 and 3 <= yy <= 7:
                    g[yy][xx] = 2
        px, py = ex + dx, 5 + dy
        for yy in range(py, py + 2):
            for xx in range(px, px + 2):
                if 0 <= xx < W and 3 <= yy <= 7:
                    g[yy][xx] = 3
    return g


def text_glyph(ch):
    g = blank()
    rows = FONT[ch].split("/")
    for y in range(VIS):
        for x in range(W):
            sy, sx = min(6, y * 7 // VIS), x * 5 // 12
            if sx < 5 and 0 <= (x - 1) < 10:
                px = (x - 1) * 5 // 10
                if rows[sy][px] == '1' and (x - 1) % 2 == (x - 1) % 2:
                    g[y][x] = 1
    return g


def dot_glyph(power):
    g = blank()
    if power:
        for y in range(VIS):
            for x in range(W):
                if circle(6, 6, 4.6)(x, y):
                    g[y][x] = 1
    else:
        for y in (5, 6):
            for x in (5, 6):
                g[y][x] = 1
    return g


def door_glyph():
    g = blank()
    for y in (5, 6):
        for x in range(W):
            g[y][x] = 1
    return g


def ghost_fright(feet):
    """2-bit: 1 body, 2 white detail (eyes + zigzag mouth)."""
    g = ghost_glyph(0, feet)
    for y in range(VIS):
        for x in range(W):
            if g[y][x] in (2, 3):
                g[y][x] = 1
    for ex in (3, 8):
        for yy in (4, 5):
            for xx in (ex, ex + 1):
                g[yy][xx] = 2
    for x in range(1, 11):
        g[8][x] = 2 if x % 2 else 1
        g[9][x] = 2 if x % 2 == 0 else 1
    return g


def ghost_eyes(direction):
    """2-bit: eyes only (1 unused, 2 white, 3 blue pupil)."""
    g = blank()
    dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[direction]
    for ex in (3, 8):
        for yy in range(3, 8):
            for xx in range(ex - 1, ex + 2):
                g[yy][xx] = 2
        px, py = ex + dx, 5 + dy
        for yy in range(py, py + 2):
            for xx in range(px, px + 2):
                if 0 <= xx < W and 3 <= yy <= 7:
                    g[yy][xx] = 3
    return g


def pac_death(k):
    """Frame k = 0..10: the mouth opens upward until nothing is left."""
    g = blank()
    frac = k / 10.0
    half = math.radians(15 + 165 * frac)
    r = 5.6 * (1.0 if k < 9 else 0.5 if k == 9 else 0.2)
    for y in range(VIS):
        for x in range(W):
            if (x + .5 - 6) ** 2 + (y + .5 - 6) ** 2 <= r * r:
                a = math.atan2(y + .5 - 6, x + .5 - 6) + math.pi / 2          # 0 = straight up
                a = (a + math.pi) % (2 * math.pi) - math.pi
                if abs(a) >= half:
                    g[y][x] = 1
    return g


def cherry():
    """2-bit: 1 red cherry, 2 green stem, 3 white highlight."""
    g = blank()
    for cx, cy in ((3.5, 8.0), (8.0, 8.5)):
        for y in range(VIS):
            for x in range(W):
                if (x + .5 - cx) ** 2 + (y + .5 - cy) ** 2 <= 3.2 ** 2:
                    g[y][x] = 1
    for i in range(6):
        g[1 + i][4 + i // 2 + 1 if i < 3 else 4 + i // 2] = 2
    for i in range(6):
        g[1 + i][9 - i // 3] = 2
    g[7][2] = g[7][7] = 3
    return g


def pack(g, bits):
    """1 bit: two 12-bit rows per 24-bit word (9 words). 2 bit: two bit planes, low bit first (unit 3, docs/osd-hw-tests.md T9), each like a 1-bit glyph (18 words)."""
    if bits == 1:
        return OG.pack_rows(g[:H], lambda v: v & 1)
    return OG.pack_rows(g[:H], lambda v: v & 1) + OG.pack_rows(g[:H], lambda v: v >> 1 & 1)


# ---------------------------------------------------------------- the glyph set
class Set:
    """Glyph store with dedupe by content: 1-bit ids up to 511, 2-bit ids up to 255. Sprite pieces are added while the demo plays."""
    def __init__(self):
        self.one, self.two = [], []
        self.id1, self.id2, self.k1, self.k2 = {}, {}, {}, {}

    def _add(self, lst, key, data):
        return OG.add_unique(lst, key, data)

    def add1(self, name, g):
        self.id1[name] = self._add(self.one, self.k1, pack(g, 1))
        return self.id1[name]

    def piece(self, g, bits):
        """Glyph id of a sprite piece (12 x 12 grid), None when it is empty."""
        if not any(v for row in g[:VIS] for v in row):
            return None
        return self._add(self.one if bits == 1 else self.two, self.k1 if bits == 1 else self.k2, pack(g, bits))


def build_set(maze):
    s = Set()
    s.add1("BLANK", blank())
    s.add1("DOT", dot_glyph(False))
    s.add1("POWER", dot_glyph(True))
    s.add1("DOOR", door_glyph())
    s.wall_ids = {}
    for y in range(len(maze)):
        for x in range(len(maze[0])):
            if is_wall(maze, x, y):
                g = wall_glyph(maze, x, y)
                key = bytes(pack(g, 1))
                if key not in s.wall_ids:
                    s.wall_ids[key] = s.add1(f"WALL_{len(s.wall_ids)}", g)
    for ch in FONT:
        s.add1(f"T_{ch}", text_glyph(ch))
    return s


# ---------------------------------------------------------------- demo
DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]
EV_INTRO, EV_WAKA_ON, EV_WAKA_OFF, EV_DEATH, EV_STOP, EV_GHOST, EV_FRUIT = 1, 2, 3, 4, 5, 6, 7      # sound events (firmware: AwtoPmSound)
BG_NONE, BG_SIREN_1, BG_SIREN_2, BG_SIREN_3, BG_FRIGHT = 0, 1, 2, 3, 4      # background sound state, high nibble of g_pcEvt (firmware: AwtoPmSoundBg)
BG_SHIFT = 4
SIREN_FAST_LEFT, SIREN_MID_LEFT = (1, 3), (2, 3)               # siren speeds up when the remaining pellets fall below 2/3, then 1/3 of the maze (num, den)
READY_STEPS, POWER_STEPS, FLASH_STEPS, DEATH_STEPS, GAMEOVER_STEPS = 14, 26, 8, 14, 10
PEN_TILE, DOOR_TILE = (14, 14), (13, 10)
FRUIT_TILE, FRUIT_AT, FRUIT_STEPS = (13, 17), (70, 170), 40
CHASE_DIST = 16                                # demo Pac-Man goes for a frightened ghost up to this many steps away
CARELESS = (120, 235)                          # steps in which the demo Pac-Man ignores the ghosts (so it dies and the game ends)


class Demo:
    def __init__(self, maze):
        self.m = maze
        self.rng = 12345
        self.lives = 3
        self.score = 0
        self.t = 0
        self.mode = "ready"                        # ready, play, dying, over
        self.timer = READY_STEPS
        self.fruit_t = 0
        self.eaten = 0
        self.events = []
        self.bg = BG_NONE
        self.fruit_ate = False
        self.fresh_maze()
        self.reset_actors()

    def fresh_maze(self):
        m = self.m
        self.pellet = {(x, y) for y, r in enumerate(m) for x, c in enumerate(r) if c in ".o"}
        self.power = {(x, y) for y, r in enumerate(m) for x, c in enumerate(r) if c == "o"}
        self.eaten = 0
        self.total = len(self.pellet)

    def reset_actors(self):
        self.pac, self.pdir = (13, 23), 2
        self.g = [(13, 11), (13, 14), (11, 14), (15, 14)]
        self.gdir = [2, 3, 3, 3]
        self.gst = ["n"] * 4                      # n normal, f frightened, e eyes
        self.out = [0, 5, 12, 22]
        self.power_t = 0
        self.chain = 0
        self.skip = [0] * 4

    def rand(self, n):
        self.rng = (self.rng * 1103515245 + 12345) & 0x7FFFFFFF
        return (self.rng >> 8) % n

    def open(self, x, y, ghost=False):
        x %= 28
        if not (0 <= y < len(self.m)):
            return False
        c = self.m[y][x]
        return c != "#" and (c != "-" or ghost)

    def neighbours(self, p, ghost=False):
        return [((p[0] + dx) % 28, p[1] + dy) for dx, dy in DIRS if self.open((p[0] + dx) % 28, p[1] + dy, ghost)]

    def pac_move(self):
        from collections import deque
        normal = [self.g[i] for i in range(4) if self.gst[i] == "n" and self.out[i] == 0]
        scared = [self.g[i] for i in range(4) if self.gst[i] == "f"]
        chase = self.power_t > FLASH_STEPS and bool(scared)
        best = None
        for pellets in ((False, True) if chase or self.fruit_t > 0 else (True,)):     # ghosts / fruit first, pellets only if they are out of reach
            q = deque([(self.pac, 0, None)])
            seen = {self.pac}
            while q and best is None:
                p, dist, first = q.popleft()
                if dist > 0 and ((pellets and p in self.pellet) or (chase and p in scared and dist < CHASE_DIST)
                                 or (p == FRUIT_TILE and self.fruit_t > dist)):
                    best = first
                    break
                for d, (dx, dy) in enumerate(DIRS):
                    np_ = ((p[0] + dx) % 28, p[1] + dy)
                    if np_ in seen or not self.open(*np_):
                        continue
                    if dist < 3 and not CARELESS[0] <= self.t < CARELESS[1] and any(abs(np_[0] - gx) + abs(np_[1] - gy) <= 1 for gx, gy in normal):
                        continue
                    seen.add(np_)
                    q.append((np_, dist + 1, first if first is not None else d))
            if best is not None:
                break
        if best is None:
            for d, (dx, dy) in enumerate(DIRS):
                np_ = ((self.pac[0] + dx) % 28, self.pac[1] + dy)
                if self.open(*np_) and d != (self.pdir + 2) % 4:
                    best = d
                    break
        if best is None:
            best = (self.pdir + 2) % 4
        self.pdir = best
        dx, dy = DIRS[best]
        self.pac = ((self.pac[0] + dx) % 28, self.pac[1] + dy)
        ate = False
        if self.pac in self.pellet:
            self.pellet.discard(self.pac)
            ate = True
            self.eaten += 1
            if self.pac in self.power:
                self.score += 50
                self.power_t = POWER_STEPS
                self.chain = 0
                for i in range(4):
                    if self.gst[i] == "n":
                        self.gst[i] = "f"
                        self.gdir[i] = (self.gdir[i] + 2) % 4
            else:
                self.score += 10
            if self.eaten in FRUIT_AT:
                self.fruit_t = FRUIT_STEPS
        if self.pac == FRUIT_TILE and self.fruit_t > 0:
            self.fruit_t = 0
            self.score += 100
            self.fruit_ate = True
        return ate

    def ghost_target(self, i):
        px, py = self.pac
        pd = DIRS[self.pdir]
        if self.gst[i] == "e":
            return DOOR_TILE
        if i == 0:
            return px, py
        if i == 1:
            return px + 4 * pd[0], py + 4 * pd[1]
        if i == 2:
            bx, by = self.g[0]
            return 2 * (px + 2 * pd[0]) - bx, 2 * (py + 2 * pd[1]) - by
        x, y = self.g[i]
        return (px, py) if abs(px - x) + abs(py - y) > 8 else (0, 33)

    def ghost_move(self, i):
        if self.out[i] > 0:
            self.out[i] -= 1
            return
        if self.gst[i] == "f":
            self.skip[i] ^= 1
            if self.skip[i]:
                return
        x, y = self.g[i]
        if self.gst[i] == "e" and (x, y) == DOOR_TILE:
            self.g[i], self.gdir[i], self.gst[i] = (13, 14), 1, "n"
            self.out[i] = 2
            return
        inside = (12 <= x <= 15 and 12 <= y <= 14)
        tx, ty = (DOOR_TILE if inside and self.gst[i] != "e" else self.ghost_target(i))
        if self.gst[i] == "e" and (x, y) == (13, 10):
            tx, ty = 13, 14
        cands = []
        for d in (3, 2, 1, 0):                                             # classic tie break: up, left, down, right
            if d == (self.gdir[i] + 2) % 4:
                continue
            nx, ny = (x + DIRS[d][0]) % 28, y + DIRS[d][1]
            if self.open(nx, ny, ghost=True):
                cands.append((d, nx, ny))
        if not cands:
            d = (self.gdir[i] + 2) % 4
            cands = [(d, (x + DIRS[d][0]) % 28, y + DIRS[d][1])]
        if self.gst[i] == "f":
            d, nx, ny = cands[self.rand(len(cands))]
        else:
            d, nx, ny = min(cands, key=lambda c: (c[1] - tx) ** 2 + (c[2] - ty) ** 2)
        self.gdir[i] = d
        self.g[i] = (nx, ny)

    def collide(self, old_pac, old_g):
        for i in range(4):
            if self.out[i] > 0 or self.gst[i] == "e":
                continue
            hit = self.g[i] == self.pac or (self.g[i] == old_pac and self.pac == old_g[i])
            if not hit:
                continue
            if self.gst[i] == "f":
                self.gst[i] = "e"
                self.chain += 1
                self.score += 100 * 2 ** self.chain
                self.events.append(EV_GHOST)
            else:
                return True
        return False

    def step(self):
        """One step; self.events gets the sound events of this step."""
        self.t += 1
        self.events = []
        self.bg = BG_NONE
        self.fruit_ate = False
        if self.mode == "ready":
            if self.timer == READY_STEPS:
                self.events.append(EV_INTRO)
            self.timer -= 1
            if self.timer == 0:
                self.mode = "play"
            return
        if self.mode == "dying":
            self.timer -= 1
            if self.timer == DEATH_STEPS - 1:
                self.events.append(EV_DEATH)
            if self.timer == 0:
                self.lives -= 1
                self.reset_actors()
                if self.lives <= 0:
                    self.mode, self.timer = "over", GAMEOVER_STEPS
                else:
                    self.mode, self.timer = "ready", READY_STEPS // 2
            return
        if self.mode == "over":
            self.timer -= 1
            if self.timer == 0:
                self.lives, self.score = 3, 0
                self.fresh_maze()
                self.reset_actors()
                self.mode, self.timer = "ready", READY_STEPS
            return
        old_pac, old_g = self.pac, list(self.g)
        ate = self.pac_move()
        self.events.append(EV_WAKA_ON if ate else EV_WAKA_OFF)
        if self.fruit_ate:
            self.events.append(EV_FRUIT)
        for i in range(4):
            self.ghost_move(i)
        if self.power_t > 0:
            self.power_t -= 1
            if self.power_t == 0:
                for i in range(4):
                    if self.gst[i] == "f":
                        self.gst[i] = "n"
        if self.fruit_t > 0:
            self.fruit_t -= 1
        if self.collide(old_pac, old_g):
            self.mode, self.timer = "dying", DEATH_STEPS
            self.events.append(EV_STOP)
        if not self.pellet:
            self.fresh_maze()
            self.reset_actors()
            self.mode, self.timer = "ready", READY_STEPS
        if self.mode == "play":
            left = len(self.pellet) * SIREN_FAST_LEFT[1]
            self.bg = (BG_FRIGHT if any(g == "f" for g in self.gst) else
                       BG_SIREN_3 if left <= self.total * SIREN_FAST_LEFT[0] else
                       BG_SIREN_2 if left <= self.total * SIREN_MID_LEFT[0] else BG_SIREN_1)


# Cell = (kind, glyph id, colour): kind 1 = 1-bit glyph (colour = foreground), kind 2 = 2-bit glyph (colour = style index into STYLES).
STYLES = [(K_RED, K_WHITE, K_BLUE), (K_PINK, K_WHITE, K_BLUE), (K_CYAN, K_WHITE, K_BLUE), (K_ORANGE, K_WHITE, K_BLUE),
          (K_BLUE, K_WHITE, K_WHITE), (K_WHITE, K_RED, K_WHITE), (K_BG, K_WHITE, K_BLUE), (K_RED, K_DOOR - 3, K_WHITE)]   # body, white, pupil
ST_GHOST, ST_FRIGHT, ST_FLASH, ST_EYES, ST_CHERRY = 0, 4, 5, 6, 7
SUB = 4                                        # sub-steps per game step: a sprite moves 12 / SUB px per sub-step
STEP_PX = W // SUB
MOUTH = (1, 2, 3, 2)                           # Pac-Man mouth opening per sub-step


def style_bytes(st):
    """2-bit char: B0 = 0x80 | c0[3]<<5 | c1[3]<<4 | c3[2:0]<<1 | c0[2];  B2 = c0[1:0]<<6 | c2<<3 | c1[2:0] (c0 = background, c1 body, c2 white, c3 pupil)."""
    body, white, pupil = STYLES[st]
    c0 = K_BG
    return (0x80 | ((c0 >> 3 & 1) << 5) | ((body >> 3 & 1) << 4) | ((pupil & 7) << 1) | (c0 >> 2 & 1),
            ((c0 & 3) << 6) | ((white & 7) << 3) | (body & 7))


def cell_bytes(c):
    kind, gid, col = c
    if kind == 1:
        return (0x4C | ((gid >> 8) << 5), gid & 0xFF, (col << 4) | K_BG)
    b0, b2 = style_bytes(col)
    return (b0, gid, b2)


def base_cells(demo, s, maze):
    """Static layer of one game step: maze, dots, text."""
    def c1(gid, colour):
        return (1, gid, colour)
    cell = [c1(s.id1["BLANK"], K_WHITE)] * (COLS * ROWS)

    def text(txt, x0, y, colour=K_WHITE):
        for k, ch in enumerate(txt):
            cell[y * COLS + x0 + k] = c1(s.id1[f"T_{ch}"], colour)
    blink = (demo.t // 2) % 2
    text("1UP" if blink or demo.mode != "play" else "   ", 3, 1)
    text("HIGH SCORE", 9, 1)
    text(f"{min(demo.score, 999999):06d}", 2, 2)
    text("000000", 10, 2)
    for y, row in enumerate(maze):
        for x, c in enumerate(row):
            i = (y + MAZE_TOP) * COLS + x
            if c == "#":
                cell[i] = c1(s.wall_ids[bytes(pack(wall_glyph(maze, x, y), 1))], K_WALL)
            elif c == "-":
                cell[i] = c1(s.id1["DOOR"], K_PINK)
            elif (x, y) in demo.pellet:
                if (x, y) in demo.power:
                    cell[i] = c1(s.id1["POWER"], K_WHITE if not blink else K_BG)
                else:
                    cell[i] = c1(s.id1["DOT"], K_PINK + 4)
    if demo.mode == "ready":
        text("READY!", 11, MAZE_TOP + 17, K_YEL)
    if demo.mode == "over":
        text("GAME  OVER", 9, MAZE_TOP + 17, K_RED)
    return cell


def sprite_pos(old, new, k):
    """Pixel position (map pixels, maze row 0 = MAZE_TOP) of an actor that moved old -> new tile, at sub-step k = 1..SUB."""
    dx, dy = (new[0] - old[0] + COLS // 2) % COLS - COLS // 2, new[1] - old[1]
    if abs(dx) + abs(dy) != 1:
        return new[0] * W, (new[1] + MAZE_TOP) * VIS
    return old[0] * W + dx * STEP_PX * k, (old[1] + MAZE_TOP) * VIS + dy * STEP_PX * k


def sprites(demo, old_pac, old_g, k):
    """Things drawn as glyph pieces at sub-step k: (bits, 12 x 12 grid, px, py, colour or style), back to front."""
    out = []
    n = demo.t * SUB + k
    for j in range(max(0, demo.lives - 1)):
        out.append((1, pac_glyph(2, 2), (2 + 2 * j) * W, (ROWS - 2) * VIS, K_YEL))
    fx, fy = FRUIT_TILE
    if demo.fruit_t > 0:
        out.append((2, cherry(), fx * W, (fy + MAZE_TOP) * VIS, ST_CHERRY))
    out.append((2, cherry(), 25 * W, (ROWS - 2) * VIS, ST_CHERRY))                 # level fruit
    px, py = sprite_pos(old_pac, demo.pac, k)
    if demo.mode == "dying":
        j = DEATH_STEPS - demo.timer - 1
        if j >= 0:
            out.append((1, pac_death(min(10, j)), px, py, K_YEL))
    elif demo.mode != "over":
        out.append((1, pac_glyph(demo.pdir, MOUTH[n % len(MOUTH)] if demo.mode == "play" else 0), px, py, K_YEL))
    if demo.mode in ("play", "ready"):
        for i in range(4):
            gx, gy = sprite_pos(old_g[i], demo.g[i], k)
            feet = (n // 2) % 2
            if demo.gst[i] == "f":
                flash = demo.power_t <= FLASH_STEPS and demo.t % 2 == 0
                out.append((2, ghost_fright(feet), gx, gy, ST_FLASH if flash else ST_FRIGHT))
            elif demo.gst[i] == "e":
                out.append((2, ghost_eyes(demo.gdir[i]), gx, gy, ST_EYES))
            else:
                out.append((2, ghost_glyph(demo.gdir[i], feet), gx, gy, ST_GHOST + i))
    return out


def overlay(cell, s, sprs):
    """Cut every sprite into the (up to 4) tiles it overlaps; each piece is a glyph of its own, later sprites cover earlier ones."""
    cell = list(cell)
    for bits, grid, px, py, col in sprs:
        for ty in range(py // VIS, (py + VIS - 1) // VIS + 1):
            for tx in range(px // W, (px + W - 1) // W + 1):
                if not 0 <= ty < ROWS:
                    continue
                g = blank()
                for y in range(VIS):
                    sy = ty * VIS + y - py
                    for x in range(W):
                        sx = tx * W + x - px
                        if 0 <= sy < VIS and 0 <= sx < W:
                            g[y][x] = grid[sy][sx]
                gid = s.piece(g, bits)
                if gid is not None:
                    cell[ty * COLS + tx % COLS] = (bits, gid, col)
    return cell


def build(steps):
    """Returns the glyph set, the first frame, per sub-frame cell updates [(cell index, cell)], sound events per game step, the demo, Pac-Man pixel trace."""
    maze = [r.ljust(28) for r in MAZE]
    assert len(maze) == 31 and all(len(r) == 28 for r in maze), "maze size"
    s = build_set(maze)
    demo = Demo(maze)
    cur = overlay(base_cells(demo, s, maze), s, sprites(demo, demo.pac, demo.g, SUB))
    init = cur
    frames, events, bgs, trace = [], [], [], []
    for _ in range(steps):
        old_pac, old_g = demo.pac, list(demo.g)
        demo.step()
        base = base_cells(demo, s, maze)
        for k in range(1, SUB + 1):
            nxt = overlay(base, s, sprites(demo, old_pac, old_g, k))
            frames.append([(p, n) for p, (n, o) in enumerate(zip(nxt, cur)) if n != o])
            trace.append(sprite_pos(old_pac, demo.pac, k))
            cur = nxt
        events.append(demo.events)
        bgs.append(demo.bg)
    out, eating, idle = [], False, 0                                     # waka: on at the first pellet, off after 3 steps without one
    for evs, bg in zip(events, bgs):
        e = 0
        for v in evs:
            if v == EV_WAKA_ON:
                idle = 0
                if not eating:
                    eating, e = True, EV_WAKA_ON
            elif v == EV_WAKA_OFF:
                idle += 1
                if eating and idle >= 3:
                    eating, e = False, EV_WAKA_OFF
            else:
                e = v
                eating = False
        out.append(e | (bg << BG_SHIFT))
    assert len(s.one) <= 512 and len(s.two) <= 256, f"glyph ids: {len(s.one)} 1-bit (max 512), {len(s.two)} 2-bit (max 256)"
    return s, init, frames, out, demo, trace


arr = OG.arr


def delta_rec(p, c):
    """3 bytes: B0 = cell lo; B1 = cell hi (bits 1:0) | kind 2-bit (bit 2) | glyph id bit 8 (bit 3) | colour or style (bits 7:4); B2 = glyph id lo."""
    kind, gid, col = c
    return bytes([p & 0xFF, (p >> 8) | ((kind == 2) << 2) | ((gid >> 8) << 3) | (col << 4), gid & 0xFF])


def emit(s, init, frames, events):
    n1 = len(s.one)
    off2 = (27 * n1 + 53) // 54                                      # 2-bit glyph 0 at font_base + 18 words * off2 (bytes: 54 * off2)
    g1 = b"".join(s.one)
    g2 = b"".join(s.two)
    glyph = g1 + bytes(54 * off2 - len(g1)) + g2                  # one contiguous word stream from font_base
    cellb = b"".join(bytes(cell_bytes(c)) for c in init)
    idx, stream = [], bytearray()
    for f in frames:
        idx.append(len(stream))
        for p, c in f:
            stream += delta_rec(p, c)
    idx.append(len(stream))
    idxb = b"".join(bytes([v & 0xFF, v >> 8]) for v in idx)
    pal = b"".join(bytes(c) for c in PAL)
    style = bytes(b for st in range(len(STYLES)) for b in style_bytes(st))
    head = ("/* pacman_classic_data.inc: GENERATED by scripts/gen_pacman_classic.py. Do not edit. Read by fw/test/pacman_classic.c via movc. */\n"
            f"#define AWTO_PC_COLS            {COLS}\n#define AWTO_PC_ROWS            {ROWS}\n#define AWTO_PC_STEPS           {len(frames)}\n"
            f"#define AWTO_PC_SUB_SHIFT       {SUB.bit_length() - 1}\n"
            f"#define AWTO_PC_PAL_N           {len(PAL)}\n#define AWTO_PC_OFF2            {off2}\n"
            f"#define AWTO_PC_GLYPH_BYTES     {len(glyph)}\n")
    half = len(stream) - DELTA_B_MAX                              # bank 11 keeps the tail: it must fit its old slot (0x1da8..) so no bank 11 const covers the scope S2 strings (fw_link_check gptr_const_xbank)
    return (head + arr("g_pcPal", pal, 3, BANK_A) + arr("g_pcStyle", style, 2, BANK_A) + arr("g_pcGlyph", glyph, 27, BANK_A)
            + arr("g_pcCell", cellb, 12, BANK_C)
            + arr("g_pcIdx", idxb, 16, BANK_A) + arr("g_pcDeltaA", bytes(stream[:half]), 15, BANK_A)
            + arr("g_pcDeltaB", bytes(stream[half:]), 15, BANK_B)
            + f"#define AWTO_PC_HALF_BYTES      {half}\n"
            + "".join(f"#define AWTO_PC_EV_{n}  {v}\n" for n, v in (("NONE", 0), ("INTRO", EV_INTRO), ("WAKA_ON", EV_WAKA_ON), ("WAKA_OFF", EV_WAKA_OFF), ("DEATH", EV_DEATH), ("STOP", EV_STOP), ("GHOST", EV_GHOST), ("FRUIT", EV_FRUIT), ("BG_MASK", 0xF0), ("BG_SHIFT", BG_SHIFT), ("EV_MASK", 0x0F)))
            + arr("g_pcEvt", bytes(events), 16, BANK_A)), len(glyph), len(stream)


def render_cells(s, cells, x0=0, y0=0, w=COLS, h=ROWS):
    """RGB array of the tile rectangle (x0, y0, w, h) of a cell list."""
    import numpy as np
    img = np.zeros((h * VIS, w * W, 3), np.uint8)
    for ty in range(h):
        for tx in range(w):
            cx, cy = (x0 + tx) % COLS, y0 + ty
            if not 0 <= cy < ROWS:
                continue
            kind, gid, col = cells[cy * COLS + cx]
            if kind == 1:
                words, fg = s.one[gid], PAL[col]
                bits = "".join(f"{int.from_bytes(words[k:k + 3], 'little'):024b}" for k in range(0, 27, 3))
                for yy in range(VIS):
                    for xx in range(W):
                        if bits[yy * W + xx] == "1":
                            img[ty * VIS + yy, tx * W + xx] = fg
            else:
                body, white, pupil = STYLES[col]
                cols = [PAL[K_BG], PAL[body], PAL[white], PAL[pupil]]
                wd = s.two[gid]
                planes = ["".join(f"{int.from_bytes(wd[p * 27 + k:p * 27 + k + 3], 'little'):024b}" for k in range(0, 27, 3)) for p in range(2)]
                for yy in range(VIS):
                    for xx in range(W):
                        v = int(planes[1][yy * W + xx]) * 2 + int(planes[0][yy * W + xx])
                        img[ty * VIS + yy, tx * W + xx] = cols[v]
    return img


def cells_at(init, frames, n):
    """Cell list after n sub-frames."""
    cur = list(init)
    for f in frames[:n]:
        for p, c in f:
            cur[p] = c
    return cur


def save_png(img, path, zoom=2):
    from PIL import Image
    Image.fromarray(img).resize((img.shape[1] * zoom, img.shape[0] * zoom), Image.NEAREST).save(path)


def render_strip(s, init, frames, trace, start, count, path):
    """Consecutive sub-frames from `start`, each cropped to the same 6 x 3 tiles around Pac-Man at `start`, side by side."""
    import numpy as np
    tiles = []
    px, py = trace[start]
    x0, y0 = (px + W // 2) // W - 2, (py + VIS // 2) // VIS - 1                # fixed window: the sprite moves through it
    for n in range(start, start + count):
        tiles.append(render_cells(s, cells_at(init, frames, n + 1), x0, y0, 6, 3))
    gap = np.full((tiles[0].shape[0], 2, 3), 90, np.uint8)
    row = tiles[0]
    for im in tiles[1:]:
        row = np.concatenate([row, gap, im], axis=1)
    save_png(row, path, 3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--steps", type=int, default=STEPS, help="game steps (each SUB sub-frames)")
    ap.add_argument("--png", type=Path, help="whole screen after --frame sub-frames")
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--strip", type=Path, help="PNG of --count consecutive sub-frames from --frame, cropped around Pac-Man")
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    s, init, frames, events, _demo, trace = build(a.steps)
    say(f"1-bit glyphs {len(s.one)}, 2-bit glyphs {len(s.two)}, game steps {len(events)}, sub-frames {len(frames)}, updates {sum(len(f) for f in frames)}")
    if a.png:
        save_png(render_cells(s, cells_at(init, frames, a.frame)), a.png)
        say(f"frame {a.frame} -> {a.png}")
    if a.strip:
        render_strip(s, init, frames, trace, a.frame, a.count, a.strip)
        say(f"strip of {a.count} sub-frames from {a.frame} -> {a.strip}")
    text, glyph_bytes, stream_bytes = emit(s, init, frames, events)
    say(f"glyph bytes {glyph_bytes}, delta bytes {stream_bytes}, index bytes {2 * (len(frames) + 1)}, cell bytes {3 * len(init)}")
    if a.check:
        ok = OUT.exists() and OUT.read_text() == text
        say(f"{OUT} {'up to date' if ok else 'STALE'}")
        return 0 if ok else 1
    OUT.write_text(text)
    say(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
