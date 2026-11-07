/* settings.h: the ONE settings registry (our design, not ported). Rows are generated from settings/registry.tsv:
 * OSD menu pages, DDC/CI VCP map, NVRAM layout + schema version, host tool settings and docs/settings.md all come
 * from the same rows. Expose everything as a setting: more rather than less. */
#ifndef AWTO_SETTINGS_H
#define AWTO_SETTINGS_H

#include <stdint.h>
#include "cc.h"

enum set_type { STY_BOOL = 0, STY_ENUM = 1, STY_INT = 2, STY_ACTION = 3 };
enum set_unit { SU_NONE = 0, SU_PERCENT = 1, SU_MS = 2, SU_HZ = 3, SU_KELVIN = 4, SU_STEP = 5 };

#define SF_NV        0x01   /* stored in NVRAM */
#define SF_LIVE      0x02   /* apply on every change (else on menu exit) */
#define SF_FACTORY   0x04   /* only in the factory menu */
#define SF_RISKY     0x08   /* can blank the panel: auto-revert unless confirmed (SET_CONFIRM_MS) */
#define SF_RO        0x10   /* read-only status value */

struct setting {
    uint16_t id;                 /* stable, never reused: NVRAM key, VCP map and docs anchor */
    const char __code *name;     /* short name; OSD label index comes from the menu page table */
    uint8_t  type, unit, group, flags;
    int16_t  min, max, step, def;
    uint8_t  nv_slot;            /* byte offset in the NVRAM settings record; 0xFF = not stored */
    uint8_t  vcp;                /* DDC/CI VCP code, 0 = none */
    void (*apply)(int16_t v);    /* pushes the value to hardware; NULL = read by its owner when needed */
};

/* GENERATED: table, count, schema version (bumps whenever a stored row's slot/type/range changes) */
extern const struct setting __code set_table[];
extern const uint8_t set_count;
extern const uint16_t set_schema;

#define SET_CONFIRM_MS 15000u    /* SF_RISKY auto-revert window (derived: our UI choice) */

const struct setting __code *set_find(uint16_t id);
int16_t set_get(uint16_t id);
/* clamp to [min, max] on step, store, apply (SF_LIVE), queue the NVRAM save (SF_NV). 1 = accepted */
uint8_t set_put(uint16_t id, int16_t v);
void    set_load(void);          /* boot: NVRAM record -> values; bad check / other schema -> defaults */
void    set_defaults(void);      /* every row to def, apply all, save */

/* Factory-defaults recovery: a bad setting must never brick the unit.
 * - boot key combination (spec settings: keys and hold time) held at power-on -> set_defaults() before any apply
 * - DDC/CI VCP 0x04 (MCCS restore factory defaults) and the debug-slave command -> set_defaults()
 * - SF_RISKY values auto-revert after SET_CONFIRM_MS without a confirm key */
uint8_t set_recovery_requested(void);   /* boot check of the key combination; 1 = restore defaults */

#endif
