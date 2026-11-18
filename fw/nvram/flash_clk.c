#include "UserCommonInclude.h"
#include "ScalerCommonFunctionInclude.h"                       // CKCON cycles, MCU_FF6C / FFE9 / FFED

// SPI flash clock for writes / erases (AWTO_FLASH_MHZ build option, docs/clock-sweep.md "Default flash clock").
// Reads run at the build's fast clock with the FF6C tune; PP / SE / WRSR run at <= 70.2 MHz (F2 5), in spec for MX25L8006E.
// Order keeps every transient a pair proven on unit 3: slow = tune then divider, fast = divider then tune.
#if(AWTO_FLASH_WR_SWITCH == 1)
static __xdata BYTE s_ucFlDepth;
static __xdata BYTE s_ucFlSwitched;
static __xdata BYTE s_ucFlSavedF2;
static __xdata BYTE s_ucFlSavedTune;

void AwtoFlashWrBegin(void)
{
    BYTE ucF2 = (BYTE)(MCU_FFE9_MCU_CLK_CONTROL_1 & AWTO_F_MCU_CLK_CONTROL_1_FLASH_CLK_DIV2);

    if(s_ucFlDepth++ != 0)
    {
        return;
    }

    // crystal / IOSC states run the flash slow already: nothing to switch
    if(((MCU_FFED_MCU_CONTROL & AWTO_F_MCU_CONTROL_MCU_CLK_SEL) != 0) && (ucF2 < _DIV_5))
    {
        s_ucFlSavedF2 = ucF2;
        s_ucFlSavedTune = (BYTE)(MCU_FF6C_READ_INSTRUCTION & AWTO_FLASH_TUNE_MASK);
        AWTO_FLASH_TUNE_SET(AWTO_FLASH_TUNE_SLOW);
        MCU_FFE9_MCU_CLK_CONTROL_1 = (MCU_FFE9_MCU_CLK_CONTROL_1 & ~AWTO_F_MCU_CLK_CONTROL_1_FLASH_CLK_DIV2) | _DIV_5;
        s_ucFlSwitched = 1;
    }
}

void AwtoFlashWrEnd(void)
{
    if(--s_ucFlDepth != 0)
    {
        return;
    }

    if(s_ucFlSwitched != 0)
    {
        s_ucFlSwitched = 0;
        MCU_FFE9_MCU_CLK_CONTROL_1 = (MCU_FFE9_MCU_CLK_CONTROL_1 & ~AWTO_F_MCU_CLK_CONTROL_1_FLASH_CLK_DIV2) | s_ucFlSavedF2;
        AWTO_FLASH_TUNE_SET(s_ucFlSavedTune);
    }
}
#else
void AwtoFlashWrBegin(void)
{
}

void AwtoFlashWrEnd(void)
{
}
#endif

// awto-ddc#238 hook (not implemented): boot CRC of the flash image at the fast clock + fallback to AWTO_FLASH_SLOW_* / F2 5, 30-minute window check.
void AwtoFlashWindowCheck(void)
{
}
