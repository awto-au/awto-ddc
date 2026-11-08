/* settings.h: the ONE settings registry (our design, not ported; awto-ddc#67). Rows come from settings/registry.tsv
 * (generator: awto-ddc scripts/settings_gen.py): OSD menu pages, DDC/CI VCP map, NVRAM record, host table and
 * docs/settings.md all come from the same rows. Expose everything as a setting: more rather than less. */
#ifndef AWTO_SETTINGS_H
#define AWTO_SETTINGS_H

#include <stdint.h>
#include "cc.h"
#include "set_gen.h"             /* GENERATED: SET_ID_*, SET_COUNT, SET_PAGES, SET_SCHEMA, AP_* */

enum set_type { STY_BOOL = 0, STY_ENUM = 1, STY_INT = 2, STY_ACTION = 3 };
enum set_unit { SU_NONE = 0, SU_PERCENT = 1, SU_MS = 2, SU_S = 3, SU_STEP = 4, SU_HZ = 5, SU_DHZ = 6 };

#define SF_NV        0x01   /* stored in NVRAM */
#define SF_LIVE      0x02   /* apply on every change (else on confirm) */
#define SF_FACTORY   0x04   /* only in the factory menu */
#define SF_RISKY     0x08   /* can blank the panel or cut host access: auto-revert unless confirmed (SET_CONFIRM_MS) */
#define SF_RO        0x10   /* read-only status value (set_status) */
#define SF_INERT     0x20   /* stored only: no firmware function behind it yet */
#define SF_REBOOT    0x40   /* takes effect after a restart */

/* One row. No pointers: const tables stay in the bank of their accessors (set_table.c), callers get copies. */
struct setting {
    uint8_t  id;                 /* stable, never reused: NVRAM key, VCP paged id, docs anchor */
    uint8_t  type, unit, group, flags;
    int16_t  min, max, step, def;
    uint8_t  vcp;                /* MCCS code, 0 = none (paged 0xE0/0xE1 always works) */
    uint8_t  apply;              /* AP_* (set_gen.h), 0 = read by its owner */
    uint16_t label;              /* set_text offset of the menu label */
    uint16_t opts;               /* set_text offset of option 0 (options follow, NUL separated); 0xFFFF = none */
};

/* GENERATED accessors (set_table.c) */
uint8_t  set_idx(uint8_t id);                            /* row index, 0xFF = no such id */
void     set_row(uint8_t idx, struct setting __xdata *out);
uint8_t  set_text(uint16_t ofs, char __xdata *dst, uint8_t max);  /* copies a NUL-terminated label, returns length */
uint16_t set_opt(uint16_t opts, uint8_t k);              /* offset of option k */
uint8_t  set_vcp_opt(uint8_t idx, int16_t v);            /* VCP value of enum option v (option '=N' or v) */
int16_t  set_opt_from_vcp(uint8_t idx, uint8_t vcpv);    /* inverse; -1 = no option has it */
uint8_t  set_vcp_row(uint8_t vcp);                       /* row index of a MCCS code, 0xFF = none */
uint16_t set_caps_len(void);                             /* DDC/CI capabilities string (generated from the vcp column) */
char     set_caps_at(uint16_t i);
void     set_apply_call(uint8_t ap, uint8_t id, int16_t v);
uint8_t  set_page_title(uint8_t page, char __xdata *dst, uint8_t max);
uint8_t  set_page_parent(uint8_t page);                  /* 0xFF = top level */
uint8_t  set_page_n(uint8_t page);                       /* entries: sub-pages first, then rows */
uint8_t  set_page_entry(uint8_t page, uint8_t k);        /* 0x80 | page = sub-page, else row index */

#define SET_CONFIRM_MS 15000u    /* SF_RISKY auto-revert window (derived: our UI choice; time to read and press Menu) */
#define SET_SAVE_MS    2000u     /* NVRAM write after the last change (derived: one save per slider drag) */

int16_t set_get(uint8_t id);
/* clamp to [min, max] (step = menu increment, not enforced), store, apply (SF_LIVE or apply_now), queue the NVRAM save (SF_NV). 1 = accepted.
 * A SF_RISKY row keeps its old value as the revert target until set_confirm() or SET_CONFIRM_MS. */
uint8_t set_put(uint8_t id, int16_t v, uint8_t apply_now);
void    set_track(uint8_t id, int16_t v);    /* the firmware changed it (input after any switch path): store, no apply, no save */
void    set_confirm(void);               /* keep the pending SF_RISKY value */
void    set_revert(void);                /* restore it now */
uint8_t set_in_boot(void);               /* 1 while set_boot applies the stored values (apply functions skip switches) */
uint8_t set_pending(void);               /* id of the risky row waiting for a confirm, 0 = none */
uint16_t set_pending_left(void);         /* ms until the auto-revert */
void    set_action(uint8_t id);          /* run a STY_ACTION row */
void    set_load(void);                  /* boot: defaults, then every valid NVRAM pair (id-tagged: rows that still exist survive) */
void    set_apply_all(void);             /* push every row with an apply to the firmware (first main-loop pass) */
void    set_defaults(void);              /* every row to def, apply all, save */
void    set_group_defaults(uint8_t group);   /* rows of one page (SET_PAGE_*) to def, applied */
void    set_save_now(void);              /* write the record now (menu exit, host 'save') */
void    set_service(void);               /* main loop: debounced save, risky auto-revert */
uint8_t set_load_result(void);           /* 0 = defaults (no record), 1 = record loaded, 2 = recovery defaults */

/* Factory-defaults recovery: a bad setting must never brick the unit.
 * - boot: MENU + UP held for SET_RECOVERY_MS at the first main-loop pass -> set_defaults()
 * - DDC/CI VCP 0x04 (MCCS restore factory defaults), debug test command 0x40 -> set_defaults()
 * - SF_RISKY values auto-revert after SET_CONFIRM_MS without a confirm */
#define SET_RECOVERY_MS 1000u    /* hold time (derived: longer than a key bounce, short enough to hold at power-on) */
uint8_t set_recovery_requested(void);    /* integrator: 1 = both keys down now */
void    set_boot(void);                  /* first main-loop pass: recovery check, then set_apply_all */

/* integrator (firmware side) */
int16_t set_status(uint8_t id);          /* SF_RO rows */
uint16_t set_now_ms(void);               /* free-running ms count */
void    set_wait_ms(uint16_t ms);        /* blocking wait (recovery hold only) */

#endif
