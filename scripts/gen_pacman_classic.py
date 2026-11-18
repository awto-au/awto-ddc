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
import os
import sys
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
OUT = ROOT / "fw/test/pacman_classic_data.inc"
LOG = ROOT / "tmp/logs/gen_pacman_classic.log"
COLS, ROWS = 28, 36
MAZE_TOP = 3                                  # tile row of maze row 0 (3 score rows above, 2 spare below)
W, H, VIS = 12, 18, 12                        # glyph 12 x 18, visible 12 x 12
STEPS = 260
BANK_A, BANK_B = 12, 11

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


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


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
    edge = lambda p: range(0, 2) if p < 0 else range(10, 12)
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
    """1 bit: two 12-bit rows per 24-bit word (9 words). 2 bit: two bit planes, MSB plane first, each like a 1-bit glyph (18 words)."""
    def plane(sel):
        out = bytearray()
        for y in range(0, H, 2):
            n = 0
            for row in g[y:y + 2]:
                for v in row:
                    n = n * 2 + sel(v)
            out += n.to_bytes(3, "little")
        return bytes(out)
    if bits == 1:
        return plane(lambda v: v & 1)
    return plane(lambda v: v >> 1 & 1) + plane(lambda v: v & 1)


# ---------------------------------------------------------------- the glyph set
class Set:
    def __init__(self):
        self.one, self.two, self.names1, self.fg1 = [], [], [], []
        self.id1, self.id2 = {}, {}

    def add1(self, name, g, fg):
        self.id1[name] = len(self.one)
        self.one.append(pack(g, 1))
        self.names1.append(name)
        self.fg1.append(fg)
        return self.id1[name]

    def add2(self, name, g):
        self.id2[name] = len(self.two)
        self.two.append(pack(g, 2))
        return self.id2[name]


def build_set(maze):
    s = Set()
    s.add1("BLANK", blank(), K_WHITE)
    s.add1("DOT", dot_glyph(False), K_DOOR if False else K_DOOR)
    s.add1("POWER", dot_glyph(True), K_DOOR)
    s.add1("DOOR", door_glyph(), K_DOOR + 1)
    seen = {}
    for y in range(len(maze)):
        for x in range(len(maze[0])):
            if is_wall(maze, x, y):
                g = wall_glyph(maze, x, y)
                key = bytes(pack(g, 1))
                if key not in seen:
                    seen[key] = s.add1(f"WALL_{len(seen)}", g, K_WALL)
    s.wall_ids = seen
    for d in range(4):
        for o in range(4):
            s.add1(f"PAC_{d}_{o}", pac_glyph(d, o), K_YEL)
    for ch in FONT:
        s.add1(f"T_{ch}", text_glyph(ch), K_WHITE)
    for k in range(11):
        s.add1(f"DEATH_{k}", pac_death(k), K_YEL)
    for d in range(4):
        for f in range(2):
            s.add2(f"GHOST_{d}_{f}", ghost_glyph(d, f))
    for f in range(2):
        s.add2(f"FRIGHT_{f}", ghost_fright(f))
    for d in range(4):
        s.add2(f"EYES_{d}", ghost_eyes(d))
    s.add2("CHERRY", cherry())
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


def cells(demo, s, maze):
    """(char command bytes B0, B1, B2) per tile."""
    def c1(gid, colour):
        return (0x4C | ((gid >> 8) << 5), gid & 0xFF, (colour << 4) | K_BG)

    def c2(gid, body, white, pupil):
        # 2-bit char: B0 = 0x80 | c0[3]<<5 | c1[3]<<4 | c3[2:0]<<1 | c0[2];  B2 = c0[1:0]<<6 | c2<<3 | c1[2:0]
        c0 = K_BG
        b0 = 0x80 | ((c0 >> 3 & 1) << 5) | ((body >> 3 & 1) << 4) | ((pupil & 7) << 1) | (c0 >> 2 & 1)
        b2 = ((c0 & 3) << 6) | ((white & 7) << 3) | (body & 7)
        return (b0, gid, b2)
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
    for k in range(max(0, demo.lives - 1)):
        cell[(ROWS - 2) * COLS + 2 + 2 * k] = c1(s.id1["PAC_2_2"], K_YEL)
    fx, fy = FRUIT_TILE
    if demo.fruit_t > 0:
        cell[(fy + MAZE_TOP) * COLS + fx] = c2(s.id2["CHERRY"], K_RED, K_DOOR - 3, K_WHITE)
    cell[(ROWS - 2) * COLS + 25] = c2(s.id2["CHERRY"], K_RED, K_DOOR - 3, K_WHITE)       # level fruit
    if demo.mode == "ready":
        text("READY!", 11, MAZE_TOP + 17, K_YEL)
    if demo.mode == "over":
        text("GAME  OVER", 9, MAZE_TOP + 17, K_RED)
    px, py = demo.pac
    if demo.mode == "dying":
        k = min(10, DEATH_STEPS - demo.timer - 1)
        if DEATH_STEPS - demo.timer - 1 >= 0:
            cell[(py + MAZE_TOP) * COLS + px] = c1(s.id1[f"DEATH_{max(0, k)}"], K_YEL)
    elif demo.mode != "over":
        op = (demo.t % 3) + 1 if demo.t % 4 != 3 else 0
        cell[(py + MAZE_TOP) * COLS + px] = c1(s.id1[f"PAC_{demo.pdir}_{op if demo.mode == 'play' else 0}"], K_YEL)
    if demo.mode in ("play", "ready"):
        for i in range(4):
            gx, gy = demo.g[i]
            if demo.gst[i] == "f":
                flash = demo.power_t <= FLASH_STEPS and demo.t % 2 == 0
                cell[(gy + MAZE_TOP) * COLS + gx] = c2(s.id2[f"FRIGHT_{demo.t % 2}"], K_WHITE if flash else K_BLUE, K_RED if flash else K_WHITE, K_WHITE)
            elif demo.gst[i] == "e":
                cell[(gy + MAZE_TOP) * COLS + gx] = c2(s.id2[f"EYES_{demo.gdir[i]}"], K_BG, K_WHITE, K_BLUE)
            else:
                cell[(gy + MAZE_TOP) * COLS + gx] = c2(s.id2[f"GHOST_{demo.gdir[i]}_{demo.t % 2}"], GHOST_COL[i], K_WHITE, K_BLUE)
    return cell


def build(steps):
    maze = [r.ljust(28) for r in MAZE]
    assert len(maze) == 31 and all(len(r) == 28 for r in maze), "maze size"
    s = build_set(maze)
    demo = Demo(maze)
    cur = cells(demo, s, maze)
    init = cur
    frames, events, bgs = [], [], []
    for _ in range(steps):
        demo.step()
        nxt = cells(demo, s, maze)
        frames.append([(p, *n) for p, (n, o) in enumerate(zip(nxt, cur)) if n != o])
        events.append(demo.events)
        bgs.append(demo.bg)
        cur = nxt
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
    return s, init, frames, out, demo


def arr(name, data, per, bank):
    rows = ["    " + ", ".join(f"0x{b:02X}" for b in data[i:i + per]) + "," for i in range(0, len(data), per)]
    return f"#pragma place bank({bank})\nstatic const uint8_t __code {name}[{len(data)}] = {{\n" + "\n".join(rows) + "\n};\n"


def emit(s, init, frames, events):
    n1, n2 = len(s.one), len(s.two)
    off2 = (27 * n1 + 53) // 54                                      # 2-bit glyph 0 at font_base + 18 words * off2 (bytes: 54 * off2)
    g1 = b"".join(s.one)
    g2 = b"".join(s.two)
    glyph = g1 + bytes(54 * off2 - len(g1)) + g2                  # one contiguous word stream from font_base
    cellb = b"".join(bytes(c) for c in init)
    idx, stream = [], bytearray()
    for f in frames:
        idx.append(len(stream))
        for p, b0, b1, b2 in f:
            stream += bytes([p & 0xFF, p >> 8, b0, b1, b2])
    idx.append(len(stream))
    idxb = b"".join(bytes([v & 0xFF, v >> 8]) for v in idx)
    pal = b"".join(bytes(c) for c in PAL)
    head = ("/* pacman_classic_data.inc: GENERATED by scripts/gen_pacman_classic.py. Do not edit. Read by fw/test/pacman_classic.c via movc. */\n"
            f"#define AWTO_PC_COLS            {COLS}\n#define AWTO_PC_ROWS            {ROWS}\n#define AWTO_PC_STEPS           {len(frames)}\n"
            f"#define AWTO_PC_PAL_N           {len(PAL)}\n#define AWTO_PC_OFF2            {off2}\n"
            f"#define AWTO_PC_GLYPH_BYTES     {len(glyph)}\n")
    half = len(stream) // 2 // 5 * 5
    return (head + arr("g_pcPal", pal, 3, BANK_A) + arr("g_pcGlyph", glyph, 27, BANK_A) + arr("g_pcCell", cellb, 12, BANK_A)
            + arr("g_pcIdx", idxb, 16, BANK_A) + arr("g_pcDeltaA", bytes(stream[:half]), 15, BANK_A)
            + arr("g_pcDeltaB", bytes(stream[half:]), 15, BANK_B)
            + f"#define AWTO_PC_HALF_BYTES      {half}\n"
            + "".join(f"#define AWTO_PC_EV_{n}  {v}\n" for n, v in (("NONE", 0), ("INTRO", EV_INTRO), ("WAKA_ON", EV_WAKA_ON), ("WAKA_OFF", EV_WAKA_OFF), ("DEATH", EV_DEATH), ("STOP", EV_STOP), ("GHOST", EV_GHOST), ("FRUIT", EV_FRUIT), ("BG_MASK", 0xF0), ("BG_SHIFT", BG_SHIFT), ("EV_MASK", 0x0F)))
            + arr("g_pcEvt", bytes(events), 16, BANK_A))


def render_png(s, cellsel, path):
    from PIL import Image
    import numpy as np
    img = np.zeros((ROWS * VIS, COLS * W, 3), np.uint8)
    for i, (b0, b1, b2) in enumerate(cellsel):
        x, y = i % COLS, i // COLS
        kind = b0 >> 6
        if kind == 1:
            gid = b1 + (256 if b0 & 0x20 else 0)
            fg = PAL[b2 >> 4]
            words = s.one[gid]
            bits = "".join(f"{int.from_bytes(words[k:k + 3], 'little'):024b}" for k in range(0, 27, 3))
            for yy in range(VIS):
                for xx in range(W):
                    if bits[yy * W + xx] == "1":
                        img[y * VIS + yy, x * W + xx] = fg
        elif kind == 2:
            c0 = (b0 >> 5 & 1) << 3 | (b0 & 1) << 2 | b2 >> 6
            cols = [PAL[c0], PAL[(b0 >> 4 & 1) << 3 | (b2 & 7)], PAL[b2 >> 3 & 7], PAL[b0 >> 1 & 7]]
            w = s.two[b1]
            planes = ["".join(f"{int.from_bytes(w[p * 27 + k:p * 27 + k + 3], 'little'):024b}" for k in range(0, 27, 3)) for p in range(2)]
            for yy in range(VIS):
                for xx in range(W):
                    v = int(planes[0][yy * W + xx]) * 2 + int(planes[1][yy * W + xx])
                    img[y * VIS + yy, x * W + xx] = cols[v]
    Image.fromarray(img).resize((img.shape[1] * 2, img.shape[0] * 2), Image.NEAREST).save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--steps", type=int, default=STEPS)
    ap.add_argument("--png", type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    s, init, frames, events, demo = build(a.steps)
    say(f"1-bit glyphs {len(s.one)}, 2-bit glyphs {len(s.two)}, steps {len(frames)}, updates {sum(len(f) for f in frames)}")
    if a.png:
        render_png(s, init, a.png)
        say(f"first frame -> {a.png}")
    text = emit(s, init, frames, events)
    if a.check:
        ok = OUT.exists() and OUT.read_text() == text
        say(f"{OUT} {'up to date' if ok else 'STALE'}")
        return 0 if ok else 1
    OUT.write_text(text)
    say(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
