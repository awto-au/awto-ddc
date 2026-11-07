/* nvram.c: record log in two 4 KiB flash sectors (awto/include/nvram.h, awto-ddc#67). Our design:
 * - 8 slots of 512 B per sector; a save writes the next blank slot, erasing a sector only when the log enters it.
 * - slot = 12 B header + payload; the magic byte (offset 0) is written last, so a cut write is never valid.
 * - load: the valid slot (magic, format, check) with the newest sequence number wins. */
#include <stdint.h>
#include "cc.h"
#include "nvram.h"

/* 0xFD000-0xFEFFF: erased on every unit (flash map: code 0x00000-0xDFFFF, vendor settings 0xFB000-0xFCFFF) [measured] */
#define NV_BASE     0xFD000ul
#define NV_SECTOR   0x1000u
#define NV_SLOT     512u
#define NV_SLOTS    16u                 /* 2 sectors x 8 */
#define NV_PER_SEC  8u
#define NV_PAGE     256u
#define NV_HDR      12u
#define NV_MAGIC    0xA7u
#define NV_FMT      1u

static uint8_t __xdata hdr[NV_HDR];
static uint8_t __xdata buf[32];
static uint8_t __xdata scanned, cur;    /* cur = newest valid slot, 0xFF = none */
static uint16_t __xdata cur_seq;

static uint32_t nv_slot_a(uint8_t s)
{
    return NV_BASE + (uint32_t)s * NV_SLOT;
}

static uint16_t nv_fletcher(uint16_t acc, const uint8_t __xdata *p, uint16_t n)
{
    uint8_t a = (uint8_t)acc, b = (uint8_t)(acc >> 8);

    while (n--) {
        a += *p++;
        b += a;
    }
    return (uint16_t)b << 8 | a;
}

/* check of header bytes 1..7 and the payload; reads the payload in place into dst */
static uint16_t nv_slot_check(uint8_t s, uint8_t __xdata *dst, uint16_t len)
{
    uint16_t c = nv_fletcher(0, hdr + 1, 7);

    if (!fl_read(nv_slot_a(s) + NV_HDR, dst, len))
        return 0xFFFF;
    return nv_fletcher(c, dst, len);
}

static uint8_t nv_read_hdr(uint8_t s, uint8_t rec)
{
    if (!fl_read(nv_slot_a(s), hdr, NV_HDR))
        return 0;
    return hdr[0] == NV_MAGIC && hdr[1] == NV_FMT && hdr[2] == rec;
}

static uint16_t nv_hdr_seq(void)
{
    return (uint16_t)hdr[5] << 8 | hdr[4];
}

static uint16_t nv_hdr_len(void)
{
    return (uint16_t)hdr[7] << 8 | hdr[6];
}

/* newest valid slot of rec, payload in dst; returns its length, 0 = none */
static uint16_t nv_scan(uint8_t rec, uint8_t __xdata *dst, uint16_t max)
{
    uint16_t bad = 0, best_seq = 0, len;
    uint8_t s, best, tries;

    for (tries = 0; tries < NV_SLOTS; tries++) {
        best = 0xFF;
        for (s = 0; s < NV_SLOTS; s++) {
            if ((bad >> s) & 1 || !nv_read_hdr(s, rec))
                continue;
            if (best == 0xFF || (int16_t)(nv_hdr_seq() - best_seq) > 0) {
                best = s;
                best_seq = nv_hdr_seq();
            }
        }
        scanned = 1;
        cur = best;
        cur_seq = best_seq;
        if (best == 0xFF || max == 0)
            return 0;                            /* max 0: headers only (newest slot and sequence for a save) */
        nv_read_hdr(best, rec);
        len = nv_hdr_len();
        if (len <= NV_PAYLOAD_MAX && len <= max &&
            nv_slot_check(best, dst, len) == ((uint16_t)hdr[9] << 8 | hdr[8]))
            return len;
        bad |= (uint16_t)1 << best;              /* broken: the next newest one */
    }
    return 0;
}

uint16_t nv_load(uint8_t rec, uint8_t __xdata *dst, uint16_t max)
{
    return nv_scan(rec, dst, max);
}

uint16_t nv_seq(void)
{
    return cur_seq;
}

static uint8_t nv_blank(uint8_t s)
{
    uint16_t o;
    uint8_t k;

    for (o = 0; o < NV_SLOT; o += sizeof buf) {
        if (!fl_read(nv_slot_a(s) + o, buf, sizeof buf))
            return 0;
        for (k = 0; k < sizeof buf; k++)
            if (buf[k] != 0xFF)
                return 0;
    }
    return 1;
}

static uint8_t nv_write_slot(uint8_t s, uint8_t rec, const uint8_t __xdata *src, uint16_t len, uint16_t seq)
{
    uint32_t a = nv_slot_a(s);
    uint16_t first = NV_PAGE - NV_HDR, c;

    hdr[0] = NV_MAGIC;
    hdr[1] = NV_FMT;
    hdr[2] = rec;
    hdr[3] = 0xFF;
    hdr[4] = (uint8_t)seq;
    hdr[5] = (uint8_t)(seq >> 8);
    hdr[6] = (uint8_t)len;
    hdr[7] = (uint8_t)(len >> 8);
    c = nv_fletcher(nv_fletcher(0, hdr + 1, 7), src, len);
    hdr[8] = (uint8_t)c;
    hdr[9] = (uint8_t)(c >> 8);
    hdr[10] = hdr[11] = 0xFF;
    if (!fl_write(a + 1, hdr + 1, NV_HDR - 1))
        return 0;
    if (!fl_write(a + NV_HDR, src, len < first ? len : first))
        return 0;
    if (len > first && !fl_write(a + NV_PAGE, src + first, len - first))
        return 0;
    if (!fl_write(a, hdr, 1))                    /* magic last: the slot becomes valid here */
        return 0;
    return 1;
}

uint8_t nv_store(uint8_t rec, const uint8_t __xdata *src, uint16_t len)
{
    uint8_t s, k;

    if (len > NV_PAYLOAD_MAX)
        return 0;
    if (!scanned)
        nv_scan(rec, buf, 0);
    s = (cur == 0xFF) ? NV_SLOTS - 1 : cur;
    for (k = 0; k < NV_SLOTS; k++) {
        s = (uint8_t)((s + 1) % NV_SLOTS);
        if (s % NV_PER_SEC == 0) {
            if (cur != 0xFF && s / NV_PER_SEC == cur / NV_PER_SEC)
                return 0;                        /* never erase the sector that holds the newest valid copy */
            if (!fl_erase(NV_BASE + (uint32_t)(s / NV_PER_SEC) * NV_SECTOR))
                continue;
        } else if (!nv_blank(s)) {
            continue;
        }
        if (nv_write_slot(s, rec, src, len, (uint16_t)(cur_seq + 1))) {
            cur = s;
            cur_seq++;
            return 1;
        }
    }
    return 0;
}

void nv_wipe(void)
{
    fl_erase(NV_BASE);
    fl_erase(NV_BASE + NV_SECTOR);
    cur = 0xFF;
    cur_seq = 0;
    scanned = 1;
}
