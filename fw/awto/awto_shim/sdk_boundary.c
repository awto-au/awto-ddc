/* SDK <-> clean boundary (integrator-owned, private; never enters awto-rtdfw). docs/cleanroom.md, awto-ddc#68.
 * One block per module; each block is deleted with the module's rules.py at step 15.
 * Compiled with the project flags + clean awto/include + awto/<mod>; skipped when the clean tree has no sources.
 * Types: BYTE = unsigned char, WORD = unsigned int, DWORD = unsigned long, bit = __bit (SDK Global.h). */
#include <stdint.h>

#define SDK_AUTOINC 0     /* SDK _AUTOINC; the data-port/ScalerRead/ScalerWrite routines step the INDEX/ADDRESS when it is 0 */

#ifdef _AWTO_NEW_ARITH            /* set by keil2sdcc for every clean module directory */
#include "arith.h"

/* FunctionLib ScalerCommonComputeDwordMulDiv.c defines both; defining them here drops that module from the link. */
unsigned long ScalerComputeDwordMulDiv(unsigned long a, unsigned long b, unsigned long c)
{
    if (c == 0)                   /* outside the clean domain (spec arith): SDK returns x / 0 = all ones; the DP TX sets the TU size with link rate 0 */
        return 0xFFFFFFFFUL;
    return ar_muldiv(a, b, c);
}

/* (a * 2^pow) / b, rounded half up = ar_shldiv(a, pow, b) */
unsigned long ScalerComputeDwordPowDiv(unsigned long a, unsigned char pow, unsigned long b)
{
    return ar_shldiv(a, pow, b);
}
#endif

#ifdef _AWTO_NEW_DATAPORT
#include "dataport.h"

#define DP_STEP(autoinc) ((autoinc) == SDK_AUTOINC ? DP_SW_STEP : DP_HW_STEP)

/* FunctionLib ScalerCommonDataPortAccess{,GetWord,SetWord}.c: Set/GetDataPortBit, SetDataPortByte/Word are macros
 * to dp_* (rules.py ALIASES); the ones below differ in argument order or step polarity and are pinned to common. */
unsigned char ScalerEnableAccessPort(unsigned int port, unsigned char v) { (void)port; return v; }
void ScalerDisableAccessPort(unsigned int port) { (void)port; }


void ScalerGetDataPortByte(unsigned int port, unsigned char idx, unsigned int n, unsigned char *dst, __bit autoinc)
{
    dp_rd_n(port, idx, dst, n, DP_STEP(autoinc));
}




unsigned int ScalerGetDataPortWord(unsigned int port, unsigned char idx, __bit autoinc)
{
    return dp_rd16(port, idx, DP_STEP(autoinc));
}
#endif

#ifdef _AWTO_NEW_REG
#include "reg.h"
#include "mode.h"

extern unsigned long g_ulDClkFreq;    /* SDK display clock, kHz (GET_D_CLK_FREQ) */

/* mode.h interface, served from the SDK until the mode module lands */
uint32_t mode_dclk_khz(void)
{
    return g_ulDClkFreq;
}

/* FunctionLib ScalerCommonMultiByteRead/Write.c: _AUTOINC = consecutive addresses (memcpy), else one address */
void ScalerRead(unsigned int addr, unsigned int n, unsigned char *dst, __bit autoinc)
{
    reg_rd_n(addr, dst, n, autoinc == SDK_AUTOINC ? 1 : 0);
}

void ScalerWrite(unsigned int addr, unsigned int n, unsigned char *src, __bit autoinc)
{
    reg_wr_n(addr, src, n, autoinc == SDK_AUTOINC ? 1 : 0);
}

/* FunctionLib ScalerCommonBurstWrite.c. SDK table types 0 command, 1 data, 2 data auto-inc, 3 OSD data
 * -> HB_CMDS 3, HB_FIXED 0, HB_STEP 1, HB_OSD 2 = (type - 1) & 3 (no code table: banked callers). */
void ScalerBurstWrite(unsigned char *addr, unsigned int n, unsigned char bank, unsigned int host,
                      unsigned char type, __bit from_xram)
{
    hb_burst(((uint32_t)bank << 16) | (uint16_t)(unsigned int)addr, n, host, (type - 1) & 3, from_xram);
}
#endif

#ifdef _AWTO_NEW_GAMMA
#include "gamma.h"
#include "timer.h"

/* tmr_wait_edge (timer.h) until the timer module lands: SDK wait events IVS 0x01, IEN_STOP 0x04, DVS 0x08, DEN_STOP 0x20 */
extern __bit ScalerTimerWaitForEvent(unsigned char event);

uint8_t tmr_wait_edge(uint8_t edge)
{
    switch (edge) {
    case TE_IN_VSYNC:  return ScalerTimerWaitForEvent(0x01);
    case TE_IN_VEND:   return ScalerTimerWaitForEvent(0x04);
    case TE_OUT_VSYNC: return ScalerTimerWaitForEvent(0x08);
    default:           return ScalerTimerWaitForEvent(0x20);
    }
}

/* called from RTD2014UserAdjustOutputGamma.c (rules.py SUBS): gamma OSD value 1..4 -> kind 0..3 */
void AwtoGammaLoad(unsigned char kind)
{
    gamma_load(kind);
}

/* FunctionLib RL6449_Series_ColorOutputGammaEnable.c (on = _FUNCTION_ON = 1, anything else off) */
void ScalerColorOutputGammaEnable(unsigned char on)
{
    gamma_enable(on == 1);
}
#endif
