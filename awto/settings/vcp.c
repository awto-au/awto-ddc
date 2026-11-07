/* vcp.c: DDC/CI VCP get/set on the registry (awto/include/vcp.h), plus the host mailbox that carries the same
 * get/set over the debug link (awto-ddc scripts/settings_cli.py). */
#include <stdint.h>
#include "cc.h"
#include "settings.h"
#include "vcp.h"

static struct setting __xdata row;
static uint8_t __xdata sel = 1;

uint8_t vcp_get(uint8_t code, uint16_t __xdata *cur, uint16_t __xdata *max, uint8_t __xdata *type)
{
    uint8_t i;
    int16_t v;

    *type = 0;
    switch (code) {
    case VCP_SEL:
        *cur = sel;
        *max = 255;
        return 1;
    case VCP_SCHEMA:
        *cur = SET_SCHEMA;
        *max = 0xFFFF;
        return 1;
    case VCP_CMD:
        *cur = set_pending();
        *max = 3;
        return 1;
    case VCP_RESET:
        *cur = 0;
        *max = 1;
        *type = 1;
        return 1;
    case VCP_VAL:
        i = set_idx(sel);
        if (i == 0xFF)
            return 0;
        set_row(i, &row);
        *cur = (uint16_t)set_get(sel);
        *max = (uint16_t)row.max;
        return 1;
    default:
        i = set_vcp_row(code);
        if (i == 0xFF)
            return 0;
        set_row(i, &row);
        v = set_get(row.id);
        if (row.type == STY_ENUM) {
            *cur = set_vcp_opt(i, v);
            *max = set_vcp_opt(i, row.max);
        } else {
            *cur = (uint16_t)v;
            *max = (uint16_t)row.max;
        }
        *type = row.type == STY_ACTION;
        return 1;
    }
}

uint8_t vcp_set(uint8_t code, uint16_t v)
{
    uint8_t i;
    int16_t o;

    switch (code) {
    case VCP_SEL:
        sel = (uint8_t)v;
        return 1;
    case VCP_SCHEMA:
        return 1;
    case VCP_CMD:
        if (v == 1)
            set_confirm();
        else if (v == 2)
            set_save_now();
        else if (v == 3)
            set_defaults();
        return 1;
    case VCP_RESET:
        if (v != 0)
            set_defaults();
        return 1;
    case VCP_VAL:
        return set_put(sel, (int16_t)v, 1);
    default:
        i = set_vcp_row(code);
        if (i == 0xFF)
            return 0;
        set_row(i, &row);
        if (row.type == STY_ENUM) {
            o = set_opt_from_vcp(i, (uint8_t)v);
            if (o < 0)
                return 1;                        /* not one of ours: ignored, as MCCS asks */
            v = (uint16_t)o;
        }
        set_put(row.id, (int16_t)v, 1);
        return 1;
    }
}

/* Host mailbox (debug link, map symbol _vcp_box): the host writes code + value, then cmd; the main loop answers.
 * cmd 1 = get, 2 = set (then get); done: cmd = 0, result 1 = ok, 0 = unsupported code. Bytes, so no endian issue. */
struct vcp_box {
    uint8_t magic;               /* 'V' once the firmware has run vcp_box_service */
    uint8_t cmd, code, result;
    uint8_t val_lo, val_hi;      /* set: value in */
    uint8_t cur_lo, cur_hi, max_lo, max_hi, type, seq;
};
struct vcp_box __xdata vcp_box;
static uint16_t __xdata bcur, bmax;
static uint8_t __xdata btype;

void vcp_box_service(void)
{
    uint8_t ok = 1;

    vcp_box.magic = 'V';
    if (vcp_box.cmd == 0)
        return;
    if (vcp_box.cmd == 2)
        ok = vcp_set(vcp_box.code, (uint16_t)vcp_box.val_hi << 8 | vcp_box.val_lo);
    if (ok)
        ok = vcp_get(vcp_box.code, &bcur, &bmax, &btype);
    vcp_box.cur_lo = (uint8_t)bcur;
    vcp_box.cur_hi = (uint8_t)(bcur >> 8);
    vcp_box.max_lo = (uint8_t)bmax;
    vcp_box.max_hi = (uint8_t)(bmax >> 8);
    vcp_box.type = btype;
    vcp_box.result = ok;
    vcp_box.seq++;
    vcp_box.cmd = 0;
}
