#include "ScalerFunctionInclude.h"

// #60 / #78: DP Rx1 frame waits from the measured frame period (AWTO_DP_ONE_FRAME / AWTO_DP_TWO_FRAMES / AWTO_DP_FRAME_SET: RL6449_Project.h).
// The SDK waits _DP_ONE_FRAME_TIME_MAX (45 ms = one frame at 23 Hz) at every frame rate.
#if(_AWTO_DP_FRAME_WAIT == _ON)
#define AWTO_DP_FRAME_MIN_MS    4       // a measured period under 4 ms (> 250 Hz) is a bad count: treated as not measured

static __xdata unsigned int s_usAwtoDpFrameMs;  // ms per frame (rounded up), 0 = not measured

static unsigned int AwtoDpMeasured(void)        // measured period, or the SDK's 23 Hz worst case while unmeasured / implausible
{
    return ((s_usAwtoDpFrameMs < AWTO_DP_FRAME_MIN_MS) || (s_usAwtoDpFrameMs > _DP_ONE_FRAME_TIME_MAX)) ? _DP_ONE_FRAME_TIME_MAX : s_usAwtoDpFrameMs;
}

void AwtoDpFrameSet(DWORD ulVBs2BsCount)        // VBs2Bs count in GDI clocks = one frame period
{
    s_usAwtoDpFrameMs = (unsigned int)(ulVBs2BsCount / _GDI_CLK_KHZ) + 1;
}

void AwtoDpFrameClear(void)                     // scan failed / HPD toggled: the next stream may run at another rate
{
    s_usAwtoDpFrameMs = 0;
}

unsigned int AwtoDpOneFrameMs(void)             // 1 frame, never above the SDK's 23 Hz worst case
{
    return AwtoDpMeasured();
}

unsigned int AwtoDpTwoFramesMs(void)            // 2 frames + 1 ms tick margin, never above the SDK's 23 Hz worst case
{
    unsigned int usMs = AwtoDpMeasured() * 2 + 1;

    return (usMs > _DP_TWO_FRAME_TIME_MAX) ? _DP_TWO_FRAME_TIME_MAX : usMs;
}
#endif
