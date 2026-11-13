// Diag block functions (#23), inserted into SysMain.c by keil2sdcc.py. Layout: RL6449_Project.h StAwtoDiag.
void AwtoDiagStage(unsigned char ucStage)
{
    unsigned int usNow;

    if((ucStage > g_stAwtoDiag.ucStage) && (ucStage <= 8))      // awto: #53.17 usStageMs[7] is the last
    {
        do
        {
            usNow = d_g_usTimerCounter;
        }
        while(usNow != d_g_usTimerCounter);
        g_stAwtoDiag.usStageMs[ucStage - 1] = usNow;
        g_stAwtoDiag.ucStage = ucStage;
        // stage 1 = AwtoSyncInit's line; stages without a sync.tsv row (5 / 7 / 8: the panel machine's lines state them) no line
        if((ucStage >= 2) && (AwtoSyncRow(AWTO_SYNC_EV_STAGE, ucStage) != 0))
        {
            AwtoSyncPush(AWTO_SYNC_EV_STAGE, ucStage, 0);
        }
    }
}

void AwtoDiagInit(void)
{
    unsigned char ucI;

    for(ucI = 0; ucI < sizeof(StAwtoDiag); ucI++)
    {
        ((volatile __xdata unsigned char *)&g_stAwtoDiag)[ucI] = 0;      // awto: #53.18
    }
    g_stAwtoDiag.ucMagic0 = 'A';
    g_stAwtoDiag.ucMagic1 = 'D';
    g_stAwtoDiag.ucVersion = (_AWTO_DBGISR == _ON) ? 2 : 1;
    AwtoOsdOfsInit();
    AwtoDiagStage(1);
}

void AwtoDiagMainPass(void)
{
    static unsigned int usLastMs;
    static unsigned int usLastHb;
    unsigned int usNow;

    g_stAwtoDiag.usHeartbeat++;
    do
    {
        usNow = d_g_usTimerCounter;
    }
    while(usNow != d_g_usTimerCounter);
    AWTO_WDT_PASS(usNow);
    if((unsigned int)(usNow - usLastMs) >= 1000)
    {
        g_stAwtoDiag.usLoopRate = g_stAwtoDiag.usHeartbeat - usLastHb;
        usLastHb = g_stAwtoDiag.usHeartbeat;
        usLastMs = usNow;
    }
    AwtoDiagStage(6);                                  // first main-loop pass (#63 order: 5 = panel VDD comes first)
    AWTO_WDT_SHOW();
}

