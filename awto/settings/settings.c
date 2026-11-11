/* settings.c: values, clamping, risky auto-revert, recovery (awto/include/settings.h, awto-ddc#67).
 * Stored rows live in the SDK store (awto-ddc#151): SF_SDK rows in its fields (set_sdk_*), the rest in the aux block the
 * integrator writes as its own items. The old record (nvram.c) is only read once, by set_load_legacy. */
#include <stdint.h>
#include "cc.h"
#include "settings.h"
#include "nvram.h"

#define REC_LEN (3u + 3u * SET_NV_COUNT)        /* legacy record: schema lo, hi, n, then (id, lo, hi) per stored row */
#if REC_LEN < SET_AUX_MAX
#error "aux block shares the legacy record buffer"
#endif

static int16_t __xdata val[SET_COUNT];
static struct setting __xdata row;
static uint8_t __xdata rec[REC_LEN];
static uint8_t __xdata booting, load_res;
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

static int16_t st_clampv(int16_t v)                /* step = the menu's increment only: a host may set any value in range */
{
    if (v < row.min)
        v = row.min;
    if (v > row.max)
        v = row.max;
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
    if (row.flags & SF_SDK)
        return st_clampv(set_sdk_get(id));
    return val[i];
}

static int16_t st_cur(uint8_t i)                   /* row (loaded) value */
{
    return (row.flags & SF_SDK) ? st_clampv(set_sdk_get(row.id)) : val[i];
}

static void st_store(uint8_t i, int16_t v)         /* row loaded; marks the stored copy dirty */
{
    if (row.flags & SF_SDK) {
        set_sdk_put(row.id, v);
        return;
    }
    val[i] = v;
    if (row.flags & SF_NV)
        set_nv_dirty();
}

static void st_apply(uint8_t i)
{
    if (row.apply != 0 && row.type != STY_ACTION)
        set_apply_call(row.apply, row.id, st_cur(i));
}

/* never leave every input disabled: the unit would search nothing */
static uint8_t st_inputs_ok(uint8_t id, int16_t v)
{
    uint8_t n = 0, k;

    for (k = SET_ID_D1_ENABLE; k <= SET_ID_D3_ENABLE; k++)
        n += (k == id) ? (v != 0) : (val[set_idx(k)] != 0);     /* aux rows: val[] holds them */
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
    if (st_cur(i) == v) {
        if (apply_now && !(row.flags & SF_SDK))
            st_apply(i);                         /* e.g. DPM off again after a wake; nothing to store (#151) */
        return 1;
    }
    st_store(i, v);
    if ((row.flags & SF_LIVE) || apply_now)
        st_apply(i);
    return 1;
}

void set_track(uint8_t id, int16_t v)
{
    uint8_t i = st_load(id);

    if (i != 0xFF && !(row.flags & SF_SDK))
        val[i] = st_clampv(v);
}

void set_confirm(void)
{
    if (pend_id != 0)
        set_nv_dirty();                          /* the aux block held the old value while pending */
    pend_id = 0;
}

void set_revert(void)
{
    uint8_t i;

    if (pend_id == 0)
        return;
    i = st_load(pend_id);
    pend_id = 0;
    st_store(i, pend_old);
    st_apply(i);
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

/* sdk = 1: SF_SDK rows too (factory reset); 0: only the rows held here (boot: the SDK store holds the others) */
static void st_all_defaults(uint8_t sdk)
{
    uint8_t i;

    for (i = 0; i < SET_COUNT; i++) {
        set_row(i, &row);
        if (row.type == STY_ACTION || (row.flags & SF_RO))
            continue;
        if (!(row.flags & SF_SDK))
            val[i] = row.def;
        else if (sdk)
            st_store(i, row.def);
    }
    pend_id = 0;
}

void set_load(void)
{
    st_all_defaults(0);
    load_res = 0;
}

uint8_t set_load_legacy(void)
{
    uint16_t n, k;
    uint8_t i, cnt;
    int16_t v;

    n = nv_load(NV_REC_SETTINGS, rec, REC_LEN);
    if (n < 3)
        return 0;
    cnt = rec[2];
    for (k = 0; k < cnt && 3u + 3u * k + 2u < n; k++) {
        i = st_load(rec[3 + 3 * k]);
        if (i == 0xFF || !(row.flags & SF_NV) || (row.flags & SF_RO))
            continue;                            /* row dropped or no longer stored: value forgotten */
        v = (int16_t)((uint16_t)rec[5 + 3 * k] << 8 | rec[4 + 3 * k]);
        if (v >= row.min && v <= row.max)
            st_store(i, st_clampv(v));           /* out of the new range: the default stays */
    }
    set_nv_dirty();
    load_res = 1;
    return 1;
}

uint8_t __xdata *set_aux_buf(void)
{
    return rec;
}

static uint8_t st_aux_check(void)                  /* layout check: ids and types of the aux rows */
{
    uint8_t i, c = 0x5A;

    for (i = 0; i < SET_COUNT; i++) {
        set_row(i, &row);
        if ((row.flags & (SF_NV | SF_SDK)) == SF_NV)
            c = (uint8_t)((c << 1 | c >> 7) ^ row.id ^ (row.type << 6));
    }
    return c;
}

uint8_t set_aux_pack(void)
{
    uint8_t i, n = 1;
    int16_t v;

    rec[0] = st_aux_check();
    for (i = 0; i < SET_COUNT; i++) {
        set_row(i, &row);
        if ((row.flags & (SF_NV | SF_SDK)) != SF_NV)
            continue;
        v = (pend_id != 0 && row.id == pend_id) ? pend_old : val[i];     /* a pending risky value is never stored */
        rec[n++] = (uint8_t)v;
        if (row.type == STY_INT)
            rec[n++] = (uint8_t)((uint16_t)v >> 8);
    }
    return n;
}

void set_aux_unpack(uint8_t len)
{
    uint8_t i, n = 1;
    int16_t v;

    if (len < SET_AUX_MAX || rec[0] != st_aux_check())
        return;
    for (i = 0; i < SET_COUNT; i++) {
        set_row(i, &row);
        if ((row.flags & (SF_NV | SF_SDK)) != SF_NV)
            continue;
        v = rec[n++];
        if (row.type == STY_INT)
            v |= (int16_t)((uint16_t)rec[n++] << 8);
        if (v >= row.min && v <= row.max)
            val[i] = v;
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

void set_defaults(void)
{
    st_all_defaults(1);
    set_nv_dirty();
    set_apply_all();
}

void set_group_defaults(uint8_t group)
{
    uint8_t i;

    for (i = 0; i < SET_COUNT; i++) {
        set_row(i, &row);
        if (row.group != group || row.type == STY_ACTION || (row.flags & SF_RO) || st_cur(i) == row.def)
            continue;
        st_store(i, row.def);
        st_apply(i);
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
            st_all_defaults(1);
            set_nv_dirty();                      /* stored through the gate */
            load_res = 2;
        }
    }
    set_apply_all();
    booting = 0;
}
