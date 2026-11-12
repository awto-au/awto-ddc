// #60: DP Rx1 two-frame waits from the measured frame period, inserted into ScalerDPRx1_SeptPhy.c by keil2sdcc.py.
// The SDK waits _DP_TWO_FRAME_TIME_MAX (2 x 45 ms, sized for 23 Hz) at every frame rate.
#if(_AWTO_DP_FRAME_WAIT == _ON)
static __xdata unsigned int s_usAwtoDpFrameMs;  // ms per frame (rounded up), 0 = not measured

static void AwtoDpFrameSet(DWORD ulVBs2BsCount)  // VBs2Bs count in GDI clocks = one frame period
{
    s_usAwtoDpFrameMs = (unsigned int)(ulVBs2BsCount / _GDI_CLK_KHZ) + 1;
}

static unsigned int AwtoDpTwoFramesMs(void)      // 2 frames + 1 ms tick margin, never above the SDK's 23 Hz worst case
{
    unsigned int usMs = s_usAwtoDpFrameMs * 2 + 1;

    return ((s_usAwtoDpFrameMs == 0) || (usMs > _DP_TWO_FRAME_TIME_MAX)) ? _DP_TWO_FRAME_TIME_MAX : usMs;
}
#define AWTO_DP_TWO_FRAMES()                                    AwtoDpTwoFramesMs()
#define AWTO_DP_FRAME_SET(n)                                    AwtoDpFrameSet(n)
#else
#define AWTO_DP_TWO_FRAMES()                                    _DP_TWO_FRAME_TIME_MAX
#define AWTO_DP_FRAME_SET(n)
#endif
