/* reg.h: CPU access to scaler/MCU registers and the host-bus burst engine.
 * Registers sit in XDATA at (page << 8) | offset; addresses come from facts/regs.h (or facts/names.h).
 * Spec: reg (helpers wave). Multi-byte values: high byte at the lower address, written lowest address first. */
#ifndef AWTO_REG_H
#define AWTO_REG_H

#include <stdint.h>
#include "cc.h"

/* one CPU access each. Host tests predefine both hooks to record reads and writes separately. */
#ifndef REG8_RD
#define REG8_RD(a) (*(volatile __xdata uint8_t *)(uint16_t)(a))
#endif
#ifndef REG8_WR
#define REG8_WR(a, v) ((*(volatile __xdata uint8_t *)(uint16_t)(a)) = (uint8_t)(v))
#endif

/* single byte */
#define reg_rd(a)              (REG8_RD(a))
#define reg_wr(a, v)           REG8_WR(a, v)
/* new = (old & keep) | set: exactly one read, then one write */
#define reg_rmw(a, keep, set)  REG8_WR(a, (uint8_t)((REG8_RD(a) & (uint8_t)(keep)) | (uint8_t)(set)))
/* old & mask (one read) */
#define reg_test(a, mask)      ((uint8_t)(REG8_RD(a) & (uint8_t)(mask)))

/* multi-byte, big-endian in register space */
uint16_t reg_rd16(uint16_t a);
void     reg_wr16(uint16_t a, uint16_t v);
uint32_t reg_rd32(uint16_t a);
void     reg_wr32(uint16_t a, uint32_t v);
/* 32-bit read-modify-write: new = (old & keep) | (set & ~keep) */
void     reg_rmw32(uint16_t a, uint32_t keep, uint32_t set);

/* n bytes; step 1 = consecutive addresses a, a+1, ...; step 0 = all to/from address a (FIFO-style register) */
void     reg_wr_n(uint16_t a, const uint8_t *src, uint16_t n, uint8_t step);
void     reg_rd_n(uint16_t a, uint8_t *dst, uint16_t n, uint8_t step);

/* Host-bus burst engine: the CPU stalls while the engine copies a table into registers. */
enum hb_kind {
    HB_FIXED = 0,      /* data bytes, all to one target register */
    HB_STEP  = 1,      /* data bytes, target address increments */
    HB_OSD   = 2,      /* data bytes to one target, with the OSD item gap */
    HB_CMDS  = 3       /* command list (self-describing items) */
};
/* src24: 24-bit source address (flash bank << 16 | offset), or an XRAM address when from_xram.
 * target: full register address (page selects the register page). Returns 0 on done, 1 on engine timeout. */
uint8_t  hb_burst(uint32_t src24, uint16_t len, uint16_t target, uint8_t kind, uint8_t from_xram);
/* item gap for HB_OSD at the given display clock and OSD horizontal double-size state (pure; spec reg) */
uint8_t  hb_osd_gap(uint32_t dclk_khz, uint8_t hdouble);

#endif
