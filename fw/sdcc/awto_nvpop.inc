// #151 fmt nvw: the NVRAM flush result line (AwtoSyncLine case 22). Included last in RTD2014OsdDisplay.c: its string
// literals come after every other one of the file, so the bank layout's __str_N names stay as they were.
// Fields: RL6449_Project.h AWTO_NV_LOG_*; host copy: scripts/sync_log.py nv_flush. No locals (DATA path).
static __xdata WORD s_usAwtoNvF, s_usAwtoNvM;
static __xdata BYTE s_ucAwtoNvG;

static void AwtoPutNvF(void)                    // field s_usAwtoNvF; "+" when saturated (at s_usAwtoNvM)
{
    AwtoPutNum(s_usAwtoNvF, 1);
    if(s_usAwtoNvF >= s_usAwtoNvM)
    {
        AwtoPutChar('+');
    }
}

static void AwtoPutNvG(BYTE ucBit, const char *pcName)
{
    if(((BYTE)(s_ulAwtoLnV >> 27) & ucBit) != 0)
    {
        AwtoPutStr((s_ucAwtoNvG != 0) ? ", " : " (");
        AwtoPutStr(pcName);
        s_ucAwtoNvG = 1;
    }
}

static void AwtoPutNvFlush(void)
{
    s_usAwtoNvF = (WORD)s_ulAwtoLnV & AWTO_NV_LOG_MS_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_MS_MAX;
    if((s_ulAwtoLnV >> 19) == 0)                // no item, program or erase
    {
        AwtoPutStr("nothing changed, no flash write (");
        AwtoPutNvF();
        AwtoPutStr(" ms)");
        return;
    }
    AwtoPutStr("wrote ");
    s_usAwtoNvF = (WORD)(s_ulAwtoLnV >> 9) & AWTO_NV_LOG_B_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_B_MAX;
    AwtoPutNvF();
    AwtoPutStr(" B");
    s_ucAwtoNvG = 0;
    AwtoPutNvG(AWTO_NV_LOG_G_SYS, "system data");
    AwtoPutNvG(AWTO_NV_LOG_G_OSD, "OSD data");
    AwtoPutNvG(AWTO_NV_LOG_G_COLOUR, "colour");
    AwtoPutNvG(AWTO_NV_LOG_G_PANEL, "panel time");
    AwtoPutNvG(AWTO_NV_LOG_G_AUX, "awto settings");
    AwtoPutStr((s_ucAwtoNvG != 0) ? ") in " : " in ");
    s_usAwtoNvF = (WORD)(s_ulAwtoLnV >> 19) & AWTO_NV_LOG_PR_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_PR_MAX;
    AwtoPutNvF();
    AwtoPutStr((s_usAwtoNvF == 1) ? " program, " : " programs, ");
    s_usAwtoNvF = (WORD)(s_ulAwtoLnV >> 25) & AWTO_NV_LOG_ER_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_ER_MAX;
    AwtoPutNvF();
    AwtoPutStr((s_usAwtoNvF == 1) ? " erase, " : " erases, ");
    s_usAwtoNvF = (WORD)s_ulAwtoLnV & AWTO_NV_LOG_MS_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_MS_MAX;
    AwtoPutNvF();
    AwtoPutStr(" ms");
}
