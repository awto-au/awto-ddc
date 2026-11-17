#include "UserCommonInclude.h"

// OSD test screens (#226 demo, #227 QC pattern): the OSD frame-control registers and windows survive an MCU reset and a reflash, so a
// test screen inherits whatever an earlier image left (blend type, alpha, window 7 mask, pop-on, scale-up, ...). Realtek's own QC starts
// with ScalerQC_OSDRegInitial; this is the same for the registers the QC frames change. Photographed on unit 3 2026-11-17: stale blend +
// window 7 mask washed every colour out.
#define AWTO_OSDT_ZERO                          0x00

void AwtoOsdTestReset(void)
{
    BYTE ucI;

    ScalerOsdDisableOsd();
    for(ucI = _OSD_WINDOW_0; ucI <= _OSD_WINDOW_5_8; ucI++)
    {
        ScalerOsdWindowDisable((EnumOsdWindowsType)ucI);
    }
    ScalerSetByte(AWTO_R_FRAME_CTRL_07, AWTO_OSDT_ZERO);        // window 3 / 4 priority, window 7 mask option
    ScalerSetByte(AWTO_R_FRAME_CTRL_08, AWTO_OSDT_ZERO);        // window 2 / 8 / 9 priority, blend colour
    ScalerSetByte(AWTO_R_FRAME_CTRL_09, AWTO_OSDT_ZERO);        // blend type 2, window 7 special function
    ScalerSetByte(AWTO_R_FRAME_CTRL_0A, AWTO_OSDT_ZERO);        // alpha blending type, double width / height
    ScalerSetByte(AWTO_R_FRAME_CTRL_0B, AWTO_OSDT_ZERO);        // font rotation
    ScalerSetByte(AWTO_R_FRAME_CTRL_18, AWTO_OSDT_ZERO);        // pop-on / roll-up / vertical boundary / two fonts
    ScalerSetByte(AWTO_R_FRAME_CTRL_1E, AWTO_OSDT_ZERO);        // vertical boundary
    ScalerSetByte(AWTO_R_FRAME_CTRL_21, AWTO_OSDT_ZERO);        // window 6 / 7 blend types, 2 / 4-bit offsets
    ScalerSetByte(AWTO_R_FRAME_CTRL_41, AWTO_OSDT_ZERO);        // auto rotation
    ScalerSetByte(AWTO_R_FRAME_CTRL_43, AWTO_OSDT_ZERO);        // 24x36 font
    ScalerSetByte(AWTO_R_OSD_SU_CRTL, AWTO_OSDT_ZERO);          // scale-up engine off
    ScalerOsdSetTransparency(AWTO_OSDT_ZERO);                   // alpha level 0 = opaque
}
