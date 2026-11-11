/* In-process MCS-51 core for fw_sim (scripts/fastmachine.py): replaces the ucsim subprocess.
 * Semantics follow ucsim 0.9.12 -t 52 (sim/ucsim/src/sims/s51.src in awto-sdcc) so runs are comparable:
 * - cycles: machine cycles per instruction as ucsim ticks them; an accepted interrupt adds 1 cycle (not seen by timers)
 * - timers 0/1 (modes 0-3), timer 2 (reload/capture/baud/down/clock-out), EX0/EX1 level+edge from the P3 latch
 * - interrupt poll order EX0 T0 EX1 T1 TI RI TF2 EXF2 then DW8051 int2 (EIE.0/EXIF.4/EIP.0, 43h), 2 priority levels (IP/EIP),
 *   no IRQ after RETI or an IE / IP / EIE / EIP write (DW8051 databook v3.2a pp. 3-44..3-47; serial 1, int3..5, wdti, pfi
 *   not modelled: unused here)
 * - code banking: XDATA 0xFFFF write selects the 64 KiB code bank (low nibble), as ucsim's banker in fw_sim
 * Hooks: bitmaps on XDATA / SFR addresses record events (returned after the instruction + IRQ entry);
 * PC hooks (per-bank mask) stop before the instruction. Build: gcc -O2 -shared -fPIC (fastmachine.py does it). */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { R_DONE = 0, R_EVENT = 1, R_PC = 2, R_BADOP = 3 };
enum { EV_XR = 0, EV_XW = 1, EV_SR = 2, EV_SW = 3 };
#define NEV 16

typedef struct {                /* public part, mirrored by fastmachine.Pub */
    uint64_t instr, cycles, nirq;
    uint32_t pc, bank, nev, skip_pc;
    uint32_t ev[NEV];           /* kind << 16 | addr, in access order */
    uint32_t reason, bad_op, nbanks, nlvl;
    uint64_t serial_wr;         /* writes to SCON/SBUF (serial port not modelled) */
    uint32_t irq_tail, _pad;    /* 1: an IRQ was entered after the last instruction of the run (its cycle) */
} pub_t;

typedef struct {
    pub_t p;
    uint8_t iram[256];
    uint8_t sfr[128];
    uint8_t xram[65536];
    uint8_t hook[4][8192];      /* EV_* bitmaps (SFR maps use the address 0x80..0xFF) */
    uint16_t pch[65536];        /* PC hooks: bank mask */
    uint8_t *code, *cur;
    int8_t lvl[8];
    uint8_t was_reti, exf2_active, t2mode, t2ex_bit;
    uint32_t t0_edge, t1_edge, t2_edge, t2ex_edge;
    uint64_t opcount[256];      /* instructions executed per opcode (test coverage) */
} core_t;

#define S(a) c->sfr[(a) - 0x80]
#define ACC S(0xE0)
#define PSW S(0xD0)
#define BR S(0xF0)
#define SP S(0x81)
#define DPL S(0x82)
#define DPH S(0x83)
#define IE S(0xA8)
#define IP S(0xB8)
#define TCON S(0x88)
#define TMOD S(0x89)
#define T2CON S(0xC8)
#define CYF (PSW >> 7)
#define RN(n) c->iram[(PSW & 0x18) + (n)]
#define DPTR ((uint16_t)(DPH << 8 | DPL))

enum { T2_RELOAD, T2_CAPTURE, T2_BAUD, T2_DOWN, T2_CLKOUT, T2_OFF };

static uint8_t par[256];

static inline void ev(core_t *c, int kind, uint32_t a)
{
    if (c->hook[kind][a >> 3] >> (a & 7) & 1) {
        if (c->p.nev < NEV)
            c->p.ev[c->p.nev] = (uint32_t)kind << 16 | a;
        c->p.nev++;
    }
}

static inline void set_acc(core_t *c, uint8_t v)
{
    ACC = v;
    PSW = (PSW & ~1) | par[v];
}

static void set_bank(core_t *c, unsigned b)
{
    c->p.bank = b;
    if (b < c->p.nbanks)
        c->cur = c->code + ((size_t)b << 16);
}

static void t2_write(core_t *c, int a)
{
    uint8_t n = T2CON;
    int old = c->t2mode;
    c->exf2_active = 1;
    if (a == 0xC8) {
        int rclk = n & 0x20, tclk = n & 0x10, cp = n & 1;
        if (!(rclk || tclk) && !cp)
            c->t2mode = T2_RELOAD;
        else if (!(rclk || tclk) && cp)
            c->t2mode = T2_CAPTURE;
        else
            c->t2mode = T2_BAUD;
    } else {                    /* T2MOD */
        uint8_t m = S(0xC9);
        if ((m & 1) && c->t2mode == T2_RELOAD) {
            c->t2mode = T2_DOWN;
            c->exf2_active = 0;
        }
        if (m & 2)
            c->t2mode = T2_CLKOUT;
    }
    if (c->t2mode != old)
        c->t2_edge = c->t2ex_edge = 0;
}

static void sfr_store(core_t *c, int a, uint8_t v)
{
    uint8_t o = S(a);
    switch (a) {
    case 0xE0: set_acc(c, v); return;
    case 0xA8: case 0xB8: case 0xE8: case 0xF8:    /* IE IP EIE EIP: one more instruction before an IRQ (DW8051 db p. 3-45) */
        S(a) = v; c->was_reti = 1; return;
    case 0xB0:                   /* P3: INT0/INT1 falling edges, T0/T1 rising edges (pins = latch) */
        if ((TCON & 0x01) && (o & 0x04) && !(v & 0x04)) TCON |= 0x02;
        if ((TCON & 0x04) && (o & 0x08) && !(v & 0x08)) TCON |= 0x08;
        if ((v & 0x10) && !(o & 0x10)) c->t0_edge++;
        if ((v & 0x20) && !(o & 0x20)) c->t1_edge++;
        S(a) = v; return;
    case 0x90:                   /* P1: T2 count input P1.0, T2EX P1.1 (falling edges) */
        if (!(v & 1) && (o & 1)) c->t2_edge++;
        if (!(v & 2) && (o & 2)) c->t2ex_edge++;
        c->t2ex_bit = (v >> 1) & 1;
        S(a) = v; return;
    case 0xC8: T2CON = v; t2_write(c, 0xC8); return;
    case 0xC9: S(0xC9) = v; t2_write(c, 0xC9); return;
    case 0x98: case 0x99: c->p.serial_wr++; S(a) = v; return;
    default: S(a) = v; return;
    }
}

static inline uint8_t dread(core_t *c, uint8_t a)
{
    if (a < 0x80)
        return c->iram[a];
    ev(c, EV_SR, a);
    return S(a);
}

static inline void dwrite(core_t *c, uint8_t a, uint8_t v)
{
    if (a < 0x80) {
        c->iram[a] = v;
        return;
    }
    sfr_store(c, a, v);
    ev(c, EV_SW, a);
}

static inline uint8_t dget(core_t *c, uint8_t a)      /* no read event (bit write RMW) */
{
    return a < 0x80 ? c->iram[a] : S(a);
}

static inline int bit_read(core_t *c, uint8_t b)
{
    uint8_t a = b < 0x80 ? 0x20 + (b >> 3) : (b & 0xF8);
    return dread(c, a) >> (b & 7) & 1;
}

static inline void bit_write(core_t *c, uint8_t b, int v)
{
    uint8_t a = b < 0x80 ? 0x20 + (b >> 3) : (b & 0xF8);
    uint8_t m = 1 << (b & 7), x = dget(c, a);
    dwrite(c, a, v ? (x | m) : (x & ~m));
}

static inline uint8_t xread(core_t *c, uint16_t a)
{
    ev(c, EV_XR, a);
    return c->xram[a];
}

static inline void xwrite(core_t *c, uint16_t a, uint8_t v)
{
    c->xram[a] = v;
    if (a == 0xFFFF)
        set_bank(c, v & 0x0F);
    ev(c, EV_XW, a);
}

static inline void push(core_t *c, uint8_t v)
{
    SP = SP + 1;
    c->iram[SP] = v;
}

static inline uint8_t pop(core_t *c)
{
    uint8_t v = c->iram[SP];
    SP = SP - 1;
    return v;
}

/* ---- hardware tick (one machine cycle) ---- */
static inline void tick_t01(core_t *c, int id)
{
    uint8_t tmod = id ? TMOD >> 4 : TMOD & 15;
    int mode = tmod & 3, gate = tmod & 8, ct = tmod & 4;
    uint8_t trm = id ? 0x40 : 0x10, tfm = id ? 0x80 : 0x20;
    uint8_t *tl = &S(id ? 0x8B : 0x8A), *th = &S(id ? 0x8D : 0x8C);
    int n = 1;
    if (id == 1 && mode == 3)
        return;                  /* timer1 mode 3 holds */
    if (mode == 3) {             /* timer0 mode 3: TL0 with TR0, TH0 with TR1 */
        if ((TCON & trm) && !(gate && !(S(0xB0) & 0x04))) {
            if (ct) { n = c->t0_edge; c->t0_edge = 0; }
            while (n--)
                if (!++*tl) TCON |= tfm;
        }
        if (TCON & 0x40)
            if (!++*th) TCON |= 0x80;
        return;
    }
    if (!(TCON & trm))
        return;
    if (gate && !(S(0xB0) & (id ? 0x08 : 0x04)))
        return;
    if (ct) {
        uint32_t *e = id ? &c->t1_edge : &c->t0_edge;
        n = *e; *e = 0;
    }
    while (n--) {
        if (mode == 0) {
            uint8_t l = ++*tl;
            if ((l & 0x1F) == 0) {
                *tl = 0;
                if (!++*th) TCON |= tfm;
            }
        } else if (mode == 1) {
            if (!++*tl)
                if (!++*th) TCON |= tfm;
        } else {
            if (!++*tl) {
                *tl = *th;
                TCON |= tfm;
            }
        }
    }
}

static inline void t2_inc_reload(core_t *c)
{
    if (!++S(0xCC))
        if (!++S(0xCD)) {
            T2CON |= 0x80;
            S(0xCD) = S(0xCB);
            S(0xCC) = S(0xCA);
        }
}

static inline void tick_t2(core_t *c)
{
    int tr = T2CON & 0x04, ct = T2CON & 0x02, exen = T2CON & 0x08, n;
    switch (c->t2mode) {
    case T2_RELOAD:
        if (exen && c->t2ex_edge) {
            T2CON |= 0x40;
            S(0xCD) = S(0xCB); S(0xCC) = S(0xCA);
            c->t2ex_edge = 0;
        }
        if (!tr) return;
        if (ct) c->t2_edge = 0;  /* ucsim: counter mode still counts 1 per cycle */
        t2_inc_reload(c);
        return;
    case T2_CAPTURE:
        if (exen && c->t2ex_edge) {
            T2CON |= 0x40;
            S(0xCB) = S(0xCD); S(0xCA) = S(0xCC);
            c->t2ex_edge = 0;
        }
        if (!tr) return;
        if (ct) c->t2_edge = 0;
        if (!++S(0xCC))
            if (!++S(0xCD)) T2CON |= 0x80;
        return;
    case T2_BAUD:
    case T2_CLKOUT:
        if (exen && c->t2ex_edge) { T2CON |= 0x40; c->t2ex_edge = 0; }
        if (!tr) return;
        if (ct) { n = c->t2_edge; c->t2_edge = 0; } else n = 6;
        while (n--)
            if (!++S(0xCC))
                if (!++S(0xCD)) {
                    S(0xCD) = S(0xCB); S(0xCC) = S(0xCA);
                    if (c->t2mode == T2_CLKOUT && !ct) S(0x90) ^= 0x01;
                }
        return;
    case T2_DOWN: {
        int toggle = 0;
        if (!tr) return;
        n = 1;
        if (ct) { n = c->t2_edge; c->t2_edge = 0; }
        while (n--) {
            if (c->t2ex_bit) {
                if (!++S(0xCC))
                    if (!++S(0xCD)) {
                        T2CON |= 0x80;
                        S(0xCD) = S(0xCB); S(0xCC) = S(0xCA);
                        toggle = 1;
                    }
            } else {
                uint8_t l = --S(0xCC), h = l == 0xFF ? --S(0xCD) : S(0xCD);
                if ((uint16_t)(h << 8 | l) < (uint16_t)(S(0xCB) << 8 | S(0xCA))) {
                    T2CON |= 0x80;
                    S(0xCD) = 0xFF; S(0xCC) = 0xFF;
                    toggle = 1;
                }
            }
        }
        if (toggle) S(0x90) ^= 0x40;   /* ucsim toggles bmEXF2 (0x40) in P1 */
        return;
    }
    default:
        return;
    }
}

static inline void tick_hw(core_t *c, int cyc)
{
    while (cyc-- > 0) {
        tick_t01(c, 0);
        tick_t01(c, 1);
        if (!(TCON & 0x01) && !(S(0xB0) & 0x04)) TCON |= 0x02;    /* level-triggered INT0/INT1 */
        if (!(TCON & 0x04) && !(S(0xB0) & 0x08)) TCON |= 0x08;
        tick_t2(c);
    }
}

/* ---- interrupts ---- */
static const struct { uint8_t iem, src, srcm, vec, clr, exf2; } SRC[8] = {
    {0x01, 0x88, 0x02, 0x03, 1, 0}, {0x02, 0x88, 0x20, 0x0B, 1, 0}, {0x04, 0x88, 0x08, 0x13, 1, 0},
    {0x08, 0x88, 0x80, 0x1B, 1, 0}, {0x10, 0x98, 0x02, 0x23, 0, 0}, {0x10, 0x98, 0x01, 0x23, 0, 0},
    {0x20, 0xC8, 0x80, 0x2B, 0, 0}, {0x20, 0xC8, 0x40, 0x2B, 0, 1},
};

static inline void irq(core_t *c)
{
    uint8_t ie = IE;
    int cur, i;
    if (c->was_reti || !(ie & 0x80))
        return;
    cur = c->p.nlvl ? c->lvl[c->p.nlvl - 1] : -1;
    for (i = 0; i < 8; i++) {
        int pr;
        if (!(ie & SRC[i].iem) || !(S(SRC[i].src) & SRC[i].srcm))
            continue;
        if (SRC[i].exf2 && !c->exf2_active)
            continue;
        pr = (IP & SRC[i].iem) ? 1 : 0;
        if (cur >= 0 && pr <= cur)
            continue;
        if (SRC[i].clr)
            S(SRC[i].src) &= ~SRC[i].srcm;
        if (c->p.nlvl < 8)
            c->lvl[c->p.nlvl++] = pr;
        c->p.cycles += 1;
        push(c, c->p.pc & 0xFF);
        push(c, c->p.pc >> 8);
        c->p.pc = SRC[i].vec;
        c->p.nirq++;
        return;
    }
    /* DW8051 EXINT2 (RL6449 WDT IRQ, FFC4 wdt_irq_pri = int2): EIE.0 enable, EXIF.4 flag (software clears), EIP.0 priority,
     * vector 0x43; polled after the 8051 sources (#138) */
    if ((S(0xE8) & 0x01) && (S(0x91) & 0x10)) {
        int pr = (S(0xF8) & 0x01) ? 1 : 0;
        if (cur >= 0 && pr <= cur)
            return;
        if (c->p.nlvl < 8)
            c->lvl[c->p.nlvl++] = pr;
        c->p.cycles += 1;
        push(c, c->p.pc & 0xFF);
        push(c, c->p.pc >> 8);
        c->p.pc = 0x43;
        c->p.nirq++;
    }
}

/* ---- one instruction; returns machine cycles ---- */
#define FETCH() (c->cur[pc++])
#define REL(r) (pc = (uint16_t)(pc + (int8_t)(r)))

static inline void add(core_t *c, uint8_t d, int cy)
{
    uint8_t a = ACC, ci = cy ? CYF : 0;
    uint8_t nc = ((unsigned)a + d + ci) > 255 ? 0x80 : 0;
    uint8_t nac = ((a & 15) + (d & 15) + ci) & 0xF0;
    uint8_t c6 = ((a & 0x7F) + (d & 0x7F) + ci) & 0x80;
    set_acc(c, a + d + ci);
    PSW = (PSW & 0x3B) | nc | ((nc ^ c6) ? 0x04 : 0) | (nac ? 0x40 : 0);
}

static inline void subb(core_t *c, uint8_t d)
{
    uint8_t a = ACC, ci = CYF, r = a - d - ci;
    PSW = (PSW & 0x3B) | ((unsigned)a < (unsigned)(d + ci) ? 0x80 : 0) |
          (((a < 0x80 && d > 0x7F && r > 0x7F) || (a > 0x7F && d < 0x80 && r < 0x80)) ? 0x04 : 0) |
          (((a & 15) < ((d + ci) & 15) || (ci && (d & 15) == 15)) ? 0x40 : 0);
    set_acc(c, r);
}

static inline void setc(core_t *c, int v)
{
    PSW = v ? (PSW | 0x80) : (PSW & 0x7F);
}

static int step(core_t *c)
{
    uint16_t pc = (uint16_t)c->p.pc;
    uint8_t op = FETCH(), a, b, d, r;
    int cyc = 1;
    uint16_t t;
    c->opcount[op]++;
    switch (op) {
    case 0x00: break;
    case 0x01: case 0x21: case 0x41: case 0x61: case 0x81: case 0xA1: case 0xC1: case 0xE1:
        a = FETCH(); pc = (pc & 0xF800) | ((op & 0xE0) << 3) | a; cyc = 2; break;
    case 0x02: a = FETCH(); b = FETCH(); pc = a << 8 | b; cyc = 2; break;
    case 0x03: a = ACC; set_acc(c, a >> 1 | a << 7); break;
    case 0x04: set_acc(c, ACC + 1); break;
    case 0x05: a = FETCH(); dwrite(c, a, dread(c, a) + 1); break;
    case 0x06: case 0x07: c->iram[RN(op & 1)]++; break;
    case 0x08: case 0x09: case 0x0A: case 0x0B: case 0x0C: case 0x0D: case 0x0E: case 0x0F: RN(op & 7)++; break;
    case 0x10:
        a = FETCH(); b = FETCH(); cyc = 2;
        if (bit_read(c, a)) { bit_write(c, a, 0); REL(b); }
        break;
    case 0x11: case 0x31: case 0x51: case 0x71: case 0x91: case 0xB1: case 0xD1: case 0xF1:
        a = FETCH(); push(c, pc & 0xFF); push(c, pc >> 8);
        pc = (pc & 0xF800) | ((op & 0xE0) << 3) | a; cyc = 2; break;
    case 0x12:
        a = FETCH(); b = FETCH(); push(c, pc & 0xFF); push(c, pc >> 8); pc = a << 8 | b; cyc = 2; break;
    case 0x13: a = ACC; d = CYF; setc(c, a & 1); set_acc(c, a >> 1 | d << 7); break;
    case 0x14: set_acc(c, ACC - 1); break;
    case 0x15: a = FETCH(); dwrite(c, a, dread(c, a) - 1); break;
    case 0x16: case 0x17: c->iram[RN(op & 1)]--; break;
    case 0x18: case 0x19: case 0x1A: case 0x1B: case 0x1C: case 0x1D: case 0x1E: case 0x1F: RN(op & 7)--; break;
    case 0x20: a = FETCH(); b = FETCH(); cyc = 2; if (bit_read(c, a)) REL(b); break;
    case 0x22: a = pop(c); b = pop(c); pc = a << 8 | b; cyc = 2; break;
    case 0x23: a = ACC; set_acc(c, a << 1 | a >> 7); break;
    case 0x24: add(c, FETCH(), 0); break;
    case 0x25: a = FETCH(); add(c, dread(c, a), 0); break;
    case 0x26: case 0x27: add(c, c->iram[RN(op & 1)], 0); break;
    case 0x28: case 0x29: case 0x2A: case 0x2B: case 0x2C: case 0x2D: case 0x2E: case 0x2F: add(c, RN(op & 7), 0); break;
    case 0x30: a = FETCH(); b = FETCH(); cyc = 2; if (!bit_read(c, a)) REL(b); break;
    case 0x32:
        a = pop(c); b = pop(c); pc = a << 8 | b; cyc = 2;
        c->was_reti = 1;
        if (c->p.nlvl) c->p.nlvl--;
        break;
    case 0x33: a = ACC; d = CYF; setc(c, a & 0x80); set_acc(c, a << 1 | d); break;
    case 0x34: add(c, FETCH(), 1); break;
    case 0x35: a = FETCH(); add(c, dread(c, a), 1); break;
    case 0x36: case 0x37: add(c, c->iram[RN(op & 1)], 1); break;
    case 0x38: case 0x39: case 0x3A: case 0x3B: case 0x3C: case 0x3D: case 0x3E: case 0x3F: add(c, RN(op & 7), 1); break;
    case 0x40: a = FETCH(); cyc = 2; if (CYF) REL(a); break;
    case 0x42: a = FETCH(); dwrite(c, a, dread(c, a) | ACC); break;
    case 0x43: a = FETCH(); b = FETCH(); dwrite(c, a, dread(c, a) | b); cyc = 2; break;
    case 0x44: set_acc(c, ACC | FETCH()); break;
    case 0x45: a = FETCH(); set_acc(c, ACC | dread(c, a)); break;
    case 0x46: case 0x47: set_acc(c, ACC | c->iram[RN(op & 1)]); break;
    case 0x48: case 0x49: case 0x4A: case 0x4B: case 0x4C: case 0x4D: case 0x4E: case 0x4F: set_acc(c, ACC | RN(op & 7)); break;
    case 0x50: a = FETCH(); cyc = 2; if (!CYF) REL(a); break;
    case 0x52: a = FETCH(); dwrite(c, a, dread(c, a) & ACC); break;
    case 0x53: a = FETCH(); b = FETCH(); dwrite(c, a, dread(c, a) & b); cyc = 2; break;
    case 0x54: set_acc(c, ACC & FETCH()); break;
    case 0x55: a = FETCH(); set_acc(c, ACC & dread(c, a)); break;
    case 0x56: case 0x57: set_acc(c, ACC & c->iram[RN(op & 1)]); break;
    case 0x58: case 0x59: case 0x5A: case 0x5B: case 0x5C: case 0x5D: case 0x5E: case 0x5F: set_acc(c, ACC & RN(op & 7)); break;
    case 0x60: a = FETCH(); cyc = 2; if (!ACC) REL(a); break;
    case 0x62: a = FETCH(); dwrite(c, a, dread(c, a) ^ ACC); break;
    case 0x63: a = FETCH(); b = FETCH(); dwrite(c, a, dread(c, a) ^ b); cyc = 2; break;
    case 0x64: set_acc(c, ACC ^ FETCH()); break;
    case 0x65: a = FETCH(); set_acc(c, ACC ^ dread(c, a)); break;
    case 0x66: case 0x67: set_acc(c, ACC ^ c->iram[RN(op & 1)]); break;
    case 0x68: case 0x69: case 0x6A: case 0x6B: case 0x6C: case 0x6D: case 0x6E: case 0x6F: set_acc(c, ACC ^ RN(op & 7)); break;
    case 0x70: a = FETCH(); cyc = 2; if (ACC) REL(a); break;
    case 0x72: a = FETCH(); cyc = 2; if (bit_read(c, a)) setc(c, 1); break;
    case 0x73: pc = DPTR + ACC; cyc = 2; break;
    case 0x74: set_acc(c, FETCH()); break;
    case 0x75: a = FETCH(); b = FETCH(); dwrite(c, a, b); cyc = 2; break;
    case 0x76: case 0x77: c->iram[RN(op & 1)] = FETCH(); break;
    case 0x78: case 0x79: case 0x7A: case 0x7B: case 0x7C: case 0x7D: case 0x7E: case 0x7F: RN(op & 7) = FETCH(); break;
    case 0x80: a = FETCH(); REL(a); cyc = 2; break;
    case 0x82: a = FETCH(); cyc = 2; if (!bit_read(c, a)) setc(c, 0); break;
    case 0x83: set_acc(c, c->cur[(uint16_t)(pc + ACC)]); cyc = 2; break;
    case 0x84:
        a = ACC; b = BR; d = PSW & 0x7F;
        if (!b) d |= 0x04;
        else { d &= ~0x04; BR = a % b; a = a / b; }
        PSW = d; set_acc(c, a); cyc = 4; break;
    case 0x85: a = FETCH(); b = FETCH(); dwrite(c, b, dread(c, a)); cyc = 2; break;
    case 0x86: case 0x87: a = FETCH(); dwrite(c, a, c->iram[RN(op & 1)]); cyc = 2; break;
    case 0x88: case 0x89: case 0x8A: case 0x8B: case 0x8C: case 0x8D: case 0x8E: case 0x8F:
        a = FETCH(); dwrite(c, a, RN(op & 7)); cyc = 2; break;
    case 0x90: a = FETCH(); b = FETCH(); DPH = a; DPL = b; cyc = 2; break;
    case 0x92: a = FETCH(); bit_write(c, a, CYF); cyc = 2; break;
    case 0x93: set_acc(c, c->cur[(uint16_t)(DPTR + ACC)]); cyc = 2; break;
    case 0x94: subb(c, FETCH()); break;
    case 0x95: a = FETCH(); subb(c, dread(c, a)); break;
    case 0x96: case 0x97: subb(c, c->iram[RN(op & 1)]); break;
    case 0x98: case 0x99: case 0x9A: case 0x9B: case 0x9C: case 0x9D: case 0x9E: case 0x9F: subb(c, RN(op & 7)); break;
    case 0xA0: a = FETCH(); cyc = 2; if (!bit_read(c, a)) setc(c, 1); break;
    case 0xA2: a = FETCH(); setc(c, bit_read(c, a)); break;
    case 0xA3: t = DPTR + 1; DPH = t >> 8; DPL = t & 0xFF; cyc = 2; break;
    case 0xA4:
        t = ACC * BR; set_acc(c, t & 0xFF); BR = t >> 8;
        PSW = (PSW & 0x7B) | (BR ? 0x04 : 0); cyc = 4; break;
    case 0xA6: case 0xA7: a = FETCH(); c->iram[RN(op & 1)] = dread(c, a); cyc = 2; break;
    case 0xA8: case 0xA9: case 0xAA: case 0xAB: case 0xAC: case 0xAD: case 0xAE: case 0xAF:
        a = FETCH(); RN(op & 7) = dread(c, a); cyc = 2; break;
    case 0xB0: a = FETCH(); cyc = 2; if (bit_read(c, a)) setc(c, 0); break;
    case 0xB2: a = FETCH(); bit_write(c, a, !bit_read(c, a)); break;
    case 0xB3: PSW ^= 0x80; break;
    case 0xB4: a = FETCH(); b = FETCH(); cyc = 2; setc(c, ACC < a); if (ACC != a) REL(b); break;
    case 0xB5: a = FETCH(); b = FETCH(); cyc = 2; d = dread(c, a); setc(c, ACC < d); if (ACC != d) REL(b); break;
    case 0xB6: case 0xB7:
        a = FETCH(); b = FETCH(); cyc = 2; d = c->iram[RN(op & 1)]; setc(c, d < a); if (d != a) REL(b); break;
    case 0xB8: case 0xB9: case 0xBA: case 0xBB: case 0xBC: case 0xBD: case 0xBE: case 0xBF:
        a = FETCH(); b = FETCH(); cyc = 2; d = RN(op & 7); setc(c, d < a); if (d != a) REL(b); break;
    case 0xC0: a = FETCH(); push(c, dread(c, a)); cyc = 2; break;
    case 0xC2: a = FETCH(); bit_write(c, a, 0); break;
    case 0xC3: PSW &= 0x7F; break;
    case 0xC4: a = ACC; set_acc(c, a << 4 | a >> 4); break;
    case 0xC5: a = FETCH(); d = dread(c, a); r = ACC; set_acc(c, d); dwrite(c, a, r); break;
    case 0xC6: case 0xC7: d = c->iram[RN(op & 1)]; c->iram[RN(op & 1)] = ACC; set_acc(c, d); break;
    case 0xC8: case 0xC9: case 0xCA: case 0xCB: case 0xCC: case 0xCD: case 0xCE: case 0xCF:
        d = RN(op & 7); RN(op & 7) = ACC; set_acc(c, d); break;
    case 0xD0: a = FETCH(); d = pop(c); dwrite(c, a, d); cyc = 2; break;
    case 0xD2: a = FETCH(); bit_write(c, a, 1); break;
    case 0xD3: PSW |= 0x80; break;
    case 0xD4:
        a = ACC; d = PSW;
        if ((a & 15) > 9 || (d & 0x40)) { if ((unsigned)a + 6 > 255) d |= 0x80; a += 6; }
        if ((a & 0xF0) > 0x90 || (d & 0x80)) { if ((unsigned)a + 0x60 > 255) d |= 0x80; a += 0x60; }
        PSW = d; set_acc(c, a); break;
    case 0xD5: a = FETCH(); b = FETCH(); cyc = 2; d = dread(c, a) - 1; dwrite(c, a, d); if (d) REL(b); break;
    case 0xD6: case 0xD7:
        d = c->iram[RN(op & 1)]; a = ACC;
        c->iram[RN(op & 1)] = (d & 0xF0) | (a & 15); set_acc(c, (a & 0xF0) | (d & 15)); break;
    case 0xD8: case 0xD9: case 0xDA: case 0xDB: case 0xDC: case 0xDD: case 0xDE: case 0xDF:
        a = FETCH(); cyc = 2; if (--RN(op & 7)) REL(a); break;
    case 0xE0: set_acc(c, xread(c, DPTR)); cyc = 2; break;
    case 0xE2: case 0xE3: set_acc(c, xread(c, S(0xA0) << 8 | RN(op & 1))); cyc = 2; break;
    case 0xE4: set_acc(c, 0); break;
    case 0xE5: a = FETCH(); set_acc(c, dread(c, a)); break;
    case 0xE6: case 0xE7: set_acc(c, c->iram[RN(op & 1)]); break;
    case 0xE8: case 0xE9: case 0xEA: case 0xEB: case 0xEC: case 0xED: case 0xEE: case 0xEF: set_acc(c, RN(op & 7)); break;
    case 0xF0: xwrite(c, DPTR, ACC); cyc = 2; break;
    case 0xF2: case 0xF3: xwrite(c, S(0xA0) << 8 | RN(op & 1), ACC); cyc = 2; break;
    case 0xF4: set_acc(c, ~ACC); break;
    case 0xF5: a = FETCH(); dwrite(c, a, ACC); break;
    case 0xF6: case 0xF7: c->iram[RN(op & 1)] = ACC; break;
    case 0xF8: case 0xF9: case 0xFA: case 0xFB: case 0xFC: case 0xFD: case 0xFE: case 0xFF: RN(op & 7) = ACC; break;
    default:                     /* 0xA5 */
        c->p.bad_op = op;
        c->p.reason = R_BADOP;
        break;
    }
    c->p.pc = pc;
    return cyc;
}

/* ---- API ---- */
core_t *core_new(const uint8_t *img, uint32_t len)
{
    core_t *c = calloc(1, sizeof *c);
    uint32_t nb = (len + 0xFFFF) >> 16, i;
    if (!c)
        return NULL;
    for (i = 0; i < 256; i++) {
        unsigned v = i, p = 0;
        while (v) { p ^= v & 1; v >>= 1; }
        par[i] = p;
    }
    c->code = malloc((size_t)(nb ? nb : 1) << 16);
    memset(c->code, 0xFF, (size_t)(nb ? nb : 1) << 16);
    memcpy(c->code, img, len);
    c->p.nbanks = nb;
    c->p.skip_pc = 0xFFFFFFFF;
    set_bank(c, 0);
    return c;
}

void core_free(core_t *c)
{
    if (c) {
        free(c->code);
        free(c);
    }
}

void core_reset(core_t *c)      /* ucsim cl_51core/cl_uc52 clear_sfr; RAM keeps its content */
{
    memset(c->sfr, 0, sizeof c->sfr);
    S(0x80) = S(0x90) = S(0xA0) = S(0xB0) = 0xFF;
    SP = 7;
    c->p.pc = 0;
    c->p.nlvl = 0;
    c->was_reti = 0;
    c->exf2_active = 1;
    c->t2mode = T2_RELOAD;
    c->t2ex_bit = 1;
    c->t0_edge = c->t1_edge = c->t2_edge = c->t2ex_edge = 0;
}

pub_t *core_pub(core_t *c) { return &c->p; }

uint8_t *core_mem(core_t *c, int space)
{
    switch (space) {
    case 0: return c->iram;
    case 1: return c->sfr;
    case 2: return c->xram;
    case 3: return c->code;
    case 4: return &c->hook[0][0];
    default: return NULL;
    }
}

uint16_t *core_pchooks(core_t *c) { return c->pch; }

uint64_t *core_opcount(core_t *c) { return c->opcount; }

void core_set_bank(core_t *c, unsigned b) { set_bank(c, b); }

void core_sfr_write(core_t *c, int a, int v) { sfr_store(c, a, (uint8_t)v); }   /* side effects, no event */

int core_level(core_t *c, int i) { return i < (int)c->p.nlvl ? c->lvl[i] : -1; }

int core_run(core_t *c, uint64_t n)
{
    uint64_t end = c->p.instr + n;
    c->p.nev = 0;
    c->p.reason = R_DONE;
    c->p.irq_tail = 0;
    while (c->p.instr < end) {
        uint32_t pc = c->p.pc;
        if (c->pch[pc] >> (c->p.bank & 15) & 1) {
            if (c->p.skip_pc != pc) {
                c->p.reason = R_PC;
                return R_PC;
            }
        }
        c->p.skip_pc = 0xFFFFFFFF;
        c->was_reti = 0;
        int cyc = step(c);
        c->p.instr++;
        c->p.cycles += cyc;
        tick_hw(c, cyc);
        uint64_t n0 = c->p.nirq;
        irq(c);
        c->p.irq_tail = c->p.nirq != n0;
        if (c->p.reason != R_DONE)
            return (int)c->p.reason;
        if (c->p.nev) {
            c->p.reason = R_EVENT;
            return R_EVENT;
        }
    }
    return R_DONE;
}
