/* Offline differential oracle. Include the core so we can compare ALL private
 * state (timer residues, cache tags, last opcode, IRQ inhibit), not just Pub. */
#include <stdio.h>
#include <assert.h>
#ifndef COUNTED_CORE_SOURCE
#define COUNTED_CORE_SOURCE "../scripts/mcs51_core.c"
#endif
#include COUNTED_CORE_SOURCE

static uint64_t cases;
static int reg_counter = -1;
static core_t *plain, *fast;
static uint8_t *snapshot;
static uint32_t *hits, *misses;

static void equal(void)
{
    core_t a = *plain, b = *fast;
    /* Host configuration and allocation addresses are not architectural state. */
    a.counted_ffwd = b.counted_ffwd = 0;
    a.code = b.code = NULL; a.cur = b.cur = NULL;
    a.fm_tag = b.fm_tag = NULL;
    a.fm_lacc = b.fm_lacc = NULL; a.fm_lmiss = b.fm_lmiss = NULL;
    if (memcmp(&a, &b, sizeof a) ||
        memcmp(plain->fm_tag, fast->fm_tag, plain->fm_sets * plain->fm_ways * 4) ||
        memcmp(plain->fm_lacc, fast->fm_lacc, FM_NLINES * 4) ||
        memcmp(plain->fm_lmiss, fast->fm_lmiss, FM_NLINES * 4)) {
        fprintf(stderr, "case %llu differs: pc %x/%x clk %llu/%llu instr %llu/%llu IRQ %llu/%llu\n",
                (unsigned long long)cases, plain->p.pc, fast->p.pc,
                (unsigned long long)plain->p.clk, (unsigned long long)fast->p.clk,
                (unsigned long long)plain->p.instr, (unsigned long long)fast->p.instr,
                (unsigned long long)plain->p.nirq, (unsigned long long)fast->p.nirq);
        const uint8_t *x = (const uint8_t *)&a, *y = (const uint8_t *)&b;
        for (size_t i = 0; i < sizeof a; i++) if (x[i] != y[i]) {
            fprintf(stderr, "first struct difference at %zu: %u/%u\n", i, x[i], y[i]); break;
        }
        exit(1);
    }
}

static void restore(core_t *c)
{
    core_restore(c, snapshot);
    memcpy(c->fm_lacc, hits, FM_NLINES * 4);
    memcpy(c->fm_lmiss, misses, FM_NLINES * 4);
}

static void check(int entry, int n, int base, int phase, int speed, int div, int bank, int chunk)
{
    core_t *pair[] = {plain, fast};
    for (int k = 0; k < 2; k++) {
        core_t *c = pair[k]; restore(c);
        c->p.pc = entry;
        c->sfr[1] = 0x81;
        c->iram[0x80] = 6; c->iram[0x81] = 0;
        c->iram[6] = n; c->iram[0x30] = n; c->iram[0x31] = base;
        c->sfr[0x50] = bank * 8;
        c->iram[bank * 8 + 7] = 0xA7;
        if (reg_counter >= 0) c->iram[bank * 8 + reg_counter] = n;
        c->sfr[0x28] = 0xAA; /* EA | ET2 */
        c->sfr[0x38] = 0x20; /* high priority */
        c->sfr[0x0E] = 1 | (div == 4 ? 0x38 : 0);
        unsigned reload = 65536u - (unsigned)(speed / 1000 / div);
        c->sfr[0x4A] = reload; c->sfr[0x4B] = reload >> 8;
        c->sfr[0x4C] = 0xFB; c->sfr[0x4D] = 0xFF;
        c->sfr[0x48] = 4;
        c->sfr[0x09] = 0x11; /* T0/T1 mode 1: different IRQ boundaries */
        c->sfr[0x08] = 0x50;
        c->sfr[0x0A] = 0xF1; c->sfr[0x0C] = 0xFF;
        c->sfr[0x0B] = 0xF5; c->sfr[0x0D] = 0xFF;
        c->tacc[0] = c->tacc[1] = c->tacc[2] = phase % div;
        timers_sched(c);
        core_set_fetch_ratio(c, speed > 200000000 ? 768 : speed > 100000000 ? 1024 : 512);
    }
    cases++;
    int r, s;
    do {
        r = core_run(plain, chunk); s = core_run(fast, chunk);
        assert(r == s);
        equal();
    } while (r == R_DONE);
    assert(r == R_PC && plain->p.pc == 6);
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    uint8_t image[65536], model[512];
    FILE *f = fopen(argv[1], "rb"); assert(f && fread(image, 1, sizeof image, f) == sizeof image); fclose(f);
    f = fopen(argv[2], "rb"); assert(f && fread(model, 1, sizeof model, f) == sizeof model); fclose(f);
    plain = core_new(image, sizeof image); fast = core_new(image, sizeof image);
    core_t *pair[] = {plain, fast};
    for (int k = 0; k < 2; k++) {
        core_t *c = pair[k];
        core_set_dw(c, 1, model, 2, 4, 4, 12, 4);
        core_set_fetch(c, 16, 64, 2, 40, 8, 10240, model + 256);
        core_set_fill(c, 68);
        core_lacc(c);
        core_reset(c);
        c->xram[0xFDA0] = 1;
        c->pch[6] = 0xFFFF;
        for (int i = 0; i < 256; i++) c->iram[i] = (i * 37 + 19) & 255;
    }
    core_set_counted_ffwd(fast, 1);
    snapshot = malloc(core_snap_size(plain)); core_snap(plain, snapshot);
    hits = calloc(FM_NLINES, 4); misses = calloc(FM_NLINES, 4);
    const int speeds[] = {87697750, 175395500, 350791000};
    for (int speed = 0; speed < 3; speed++)
        for (int div = 4; div <= 12; div += 8)
            for (int phase = 0; phase < div; phase++)
                for (int n = 0; n < 256; n++) {
                    check(0x1000, n, 29, phase, speeds[speed], div, 0, 1000000);
                    check(0x1100, n, 29, phase, speeds[speed], div, 0, 1000000);
                    check(0x1100, 3, n, phase, speeds[speed], div, 0, 1000000);
                    check(0x1300, n, 29, phase, speeds[speed], div, 0, 1000000);
                }
    /* Every register bank, and run ends in the middle of a loop / IRQ. */
    const int chunks[] = {1, 2, 7, 127, 255, 256, 257, 1000};
    for (int bank = 0; bank < 4; bank++)
        for (int i = 0; i < 8; i++)
            for (int n = 0; n < 256; n += 51)
                check(0x1000, n, 29, 7, speeds[2], 12, bank, chunks[i]);
    /* Every register DJNZ encoding, bank and initial count. */
    plain->code[0x1501] = fast->code[0x1501] = 0xFE;
    plain->code[0x1502] = fast->code[0x1502] = 0x22;
    for (reg_counter = 0; reg_counter < 8; reg_counter++) {
        plain->code[0x1500] = fast->code[0x1500] = 0xD8 + reg_counter;
        for (int bank = 0; bank < 4; bank++)
            for (int n = 0; n < 256; n++)
                check(0x1500, n, 29, 7, speeds[2], 12, bank, 1000000);
    }
    printf("%llu exact differential cases passed (all private state and fetch counters)\n", (unsigned long long)cases);
    core_free(plain); core_free(fast); free(snapshot); free(hits); free(misses);
    return 0;
}
