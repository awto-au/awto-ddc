/* settings.c: values, clamping, NVRAM record, risky auto-revert, recovery (awto/include/settings.h, awto-ddc#67). */
#include <stdint.h>
#include "cc.h"
#include "settings.h"
#include "nvram.h"

#define REC_LEN (3u + 3u * SET_NV_COUNT)        /* schema lo, hi, n, then (id, lo, hi) per stored row */

static int16_t __xdata val[SET_COUNT];
static struct setting __xdata row;
static uint8_t __xdata rec[REC_LEN];
static uint8_t __xdata dirty, booting, load_res;
static uint16_t __xdata dirty_t;
static uint8_t __xdata pend_id;
static int16_t __xdata pend_old;
static uint16_t __xdata pend_t;

static uint8_t st_load(uint8_t id)
{
    uint8_t i = set_idx(id);

    if (i != 0xFF)
        set_row(i, &row);
    return i;
}

static int16_t st_clampv(int16_t v)
{
    if (v < row.min)
        v = row.min;
    if (v > row.max)
        v = row.max;
    if (row.step > 1)
        v = row.min + (int16_t)((v - row.min) / row.step) * row.step;
    return v;
}

uint8_t set_in_boot(void)
{
    return booting;
}

int16_t set_get(uint8_t id)
{
    uint8_t i = st_load(id);

    if (i == 0xFF)
        return 0;
    if (row.flags & SF_RO)
        return set_status(id);
    return val[i];
}

static void st_apply(uint8_t i)
{
    if (row.apply != 0 && row.type != STY_ACTION)
        set_apply_call(row.apply, row.id, val[i]);
}

static void st_touch(void)
{
    if (row.flags & SF_NV) {
        dirty = 1;
        dirty_t = set_now_ms();
    }
}

/* never leave every input disabled: the unit would search nothing */
static uint8_t st_inputs_ok(uint8_t id, int16_t v)
{
    uint8_t n = 0, k;

    for (k = SET_ID_D1_ENABLE; k <= SET_ID_D3_ENABLE; k++)
        n += (k == id) ? (v != 0) : (val[set_idx(k)] != 0);
    return n != 0;
}

uint8_t set_put(uint8_t id, int16_t v, uint8_t apply_now)
{
    uint8_t i = st_load(id);

    if (i == 0xFF || (row.flags & SF_RO))
        return 0;
    if (row.type == STY_ACTION) {
        if (v != 0)
            set_action(id);
        return 1;
    }
    v = st_clampv(v);
    if (id >= SET_ID_D1_ENABLE && id <= SET_ID_D3_ENABLE && !st_inputs_ok(id, v))
        return 0;
    if (row.flags & SF_RISKY) {
        if (pend_id != 0 && pend_id != id)
            set_confirm();                       /* one revert target at a time: an older pending value is kept */
        if (pend_id == 0 && v != val[i]) {
            pend_id = id;
            pend_old = val[i];
        }
        pend_t = set_now_ms();
        if (pend_id == id && v == pend_old)
            pend_id = 0;                         /* back to the old value: nothing to confirm */
        st_load(id);
    }
    if (val[i] == v && !apply_now)
        return 1;
    val[i] = v;
    if ((row.flags & SF_LIVE) || apply_now)
        st_apply(i);
    st_touch();
    return 1;
}

void set_confirm(void)
{
    pend_id = 0;
}

void set_revert(void)
{
    uint8_t i;

    if (pend_id == 0)
        return;
    i = st_load(pend_id);
    pend_id = 0;
    val[i] = pend_old;
    st_apply(i);
    st_touch();
}

uint8_t set_pending(void)
{
    return pend_id;
}

uint16_t set_pending_left(void)
{
    uint16_t el = set_now_ms() - pend_t;

    return (pend_id == 0 || el >= SET_CONFIRM_MS) ? 0 : SET_CONFIRM_MS - el;
}

void set_action(uint8_t id)
{
    if (st_load(id) != 0xFF && row.type == STY_ACTION && row.apply != 0)
        set_apply_call(row.apply, id, 1);
}

static void st_all_defaults(void)
{
    uint8_t i;

    for (i = 0; i < SET_COUNT; i++) {
        set_row(i, &row);
        val[i] = row.def;
    }
    pend_id = 0;
}

void set_load(void)
{
    uint16_t n, k;
    uint8_t i, cnt;
    int16_t v;

    st_all_defaults();
    load_res = 0;
    n = nv_load(NV_REC_SETTINGS, rec, REC_LEN);
    if (n < 3)
        return;
    cnt = rec[2];
    for (k = 0; k < cnt && 3u + 3u * k + 2u < n; k++) {
        i = st_load(rec[3 + 3 * k]);
        if (i == 0xFF || !(row.flags & SF_NV) || (row.flags & SF_RO))
            continue;                            /* row dropped or no longer stored: value forgotten */
        v = (int16_t)((uint16_t)rec[5 + 3 * k] << 8 | rec[4 + 3 * k]);
        if (v >= row.min && v <= row.max)
            val[i] = st_clampv(v);                  /* out of the new range: the default stays */
    }
    load_res = 1;
}

uint8_t set_load_result(void)
{
    return load_res;
}

void set_apply_all(void)
{
    uint8_t i;

    for (i = 0; i < SET_COUNT; i++) {
        set_row(i, &row);
        st_apply(i);
    }
}

void set_save_now(void)
{
    uint8_t i, n = 0;

    for (i = 0; i < SET_COUNT && n < SET_NV_COUNT; i++) {
        set_row(i, &row);
        if (!(row.flags & SF_NV))
            continue;
        rec[3 + 3 * n] = row.id;
        rec[4 + 3 * n] = (uint8_t)val[i];
        rec[5 + 3 * n] = (uint8_t)((uint16_t)val[i] >> 8);
        n++;
    }
    rec[0] = (uint8_t)SET_SCHEMA;
    rec[1] = (uint8_t)(SET_SCHEMA >> 8);
    rec[2] = n;
    nv_store(NV_REC_SETTINGS, rec, 3u + 3u * n);
    dirty = 0;
}

void set_defaults(void)
{
    st_all_defaults();
    set_apply_all();
    set_save_now();
}

void set_group_defaults(uint8_t group)
{
    uint8_t i;

    for (i = 0; i < SET_COUNT; i++) {
        set_row(i, &row);
        if (row.group != group || row.type == STY_ACTION || (row.flags & SF_RO))
            continue;
        val[i] = row.def;
        st_apply(i);
        st_touch();
    }
}

/* MCCS 0x08 restore colour defaults */
void set_ap_colour_reset(uint8_t id, int16_t v)
{
    (void)id;
    (void)v;
    set_group_defaults(SET_PAGE_COLOUR);
    set_group_defaults(SET_PAGE_SIXAXIS);
}

void set_ap_defaults(uint8_t id, int16_t v)
{
    (void)id;
    (void)v;
    set_defaults();
}

void set_service(void)
{
    uint16_t now = set_now_ms();

    if (pend_id != 0 && (uint16_t)(now - pend_t) >= SET_CONFIRM_MS)
        set_revert();
    if (dirty && pend_id == 0 && (uint16_t)(now - dirty_t) >= SET_SAVE_MS)
        set_save_now();                          /* a pending risky value is never saved: a power cycle reverts it */
}

void set_boot(void)
{
    uint16_t t0;

    booting = 1;
    if (set_recovery_requested()) {
        t0 = set_now_ms();
        while (set_recovery_requested() && (uint16_t)(set_now_ms() - t0) < SET_RECOVERY_MS)
            set_wait_ms(10);
        if ((uint16_t)(set_now_ms() - t0) >= SET_RECOVERY_MS) {
            st_all_defaults();
            set_save_now();
            load_res = 2;
        }
    }
    set_apply_all();
    booting = 0;
}
