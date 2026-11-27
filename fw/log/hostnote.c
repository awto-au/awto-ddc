#include "SysInclude.h"

// #273 host note: the host writes the text slot over 0x35 (tag = next sequence), then test cmd AWTO_TC_HOST_NOTE: one ring entry per note.
// A newer note overwrites the slot: the older entry's sequence no longer matches the tag and the decoders print "text overwritten".
__xdata unsigned int g_usAwtoNoteN;                 // sequence of the last logged note
__xdata BYTE g_aucAwtoNote[AWTO_NOTE_SIZE];

// Shared MCU_DC port A access. Notes wait 3 frames of DDR arbitration (ms); the DRAM log only spins (AWTO_DDRN_SPIN polls, a few tens of us):
// a busy port leaves the line pending (write) or the line unread (read), counted, never a ms-long wait in the main loop or under a masked interrupt.
static __xdata BYTE s_ucDdrN;                       // spin counter and start time in XDATA: the log read sits on the deepest DATA overlay path (console line -> DDR read)
static __xdata DWORD s_ulDdrT;
__xdata BYTE g_ucAwtoAtLaps;                        // AwtoSyncAt: seq laps (AWTO_SYNC_WRAP lines) further back; set by the console for one row only (0 without the DRAM log)
__xdata BYTE g_ucAwtoDdrOff;                        // 1 while ScalerMemoryPowerControl has the memory off: no port A op (writes were lost, #358)

#pragma place bank(5)
static unsigned char AwtoDdrIdleMs(void)           // port A command idle (write ~1.7 us); 0 = stall for AWTO_DDRN_STALL_MS, the op is dropped
{
    if(g_ucAwtoDdrOff != 0)
    {
        return 0;                                   // memory off: a note write / read waits for the power-up
    }
    for(s_ucDdrN = AWTO_DDRN_SPIN; s_ucDdrN != 0; s_ucDdrN--)
    {
        if((AWTO_XB(AWTO_R_MCU_DC_CMD_A) & AWTO_F_MCU_DC_CMD_A_DDR_A_CMD) == 0)
        {
            return 1;
        }
    }
    s_ulDdrT = AwtoMs();
    while((AWTO_XB(AWTO_R_MCU_DC_CMD_A) & AWTO_F_MCU_DC_CMD_A_DDR_A_CMD) != 0)
    {
        if((AwtoMs() - s_ulDdrT) >= AWTO_DDRN_STALL_MS)
        {
            return 0;
        }
    }
    return 1;
}

#pragma place bank(5)
static unsigned char AwtoDdrReadWait(void)         // after the read command: READ_FLAG up within AWTO_DDRN_STALL_MS
{
    for(s_ucDdrN = AWTO_DDRN_SPIN; s_ucDdrN != 0; s_ucDdrN--)
    {
        if((AWTO_XB(AWTO_R_MCU_DC_READ_FLAG_A) & AWTO_DDRN_READ_FLAG) != 0)
        {
            return 1;
        }
    }
    s_ulDdrT = AwtoMs();
    while((AWTO_XB(AWTO_R_MCU_DC_READ_FLAG_A) & AWTO_DDRN_READ_FLAG) == 0)
    {
        if((AwtoMs() - s_ulDdrT) >= AWTO_DDRN_STALL_MS)
        {
            return 0;
        }
    }
    return 1;
}

#if(_AWTO_DRAM_LOG == _ON)
#pragma place bank(5)
static unsigned char AwtoDdrIdleSpin(void)          // port A command idle within AWTO_DDRN_SPIN polls (the log: no ms wait); 0 = busy
{
    for(s_ucDdrN = AWTO_DDRN_SPIN; s_ucDdrN != 0; s_ucDdrN--)
    {
        if((AWTO_XB(AWTO_R_MCU_DC_CMD_A) & AWTO_F_MCU_DC_CMD_A_DDR_A_CMD) == 0)
        {
            return 1;
        }
    }
    return 0;
}

#pragma place bank(5)
static unsigned char AwtoDdrReadSpin(void)          // READ_FLAG within AWTO_DDRN_SPIN polls; 0 = not yet
{
    for(s_ucDdrN = AWTO_DDRN_SPIN; s_ucDdrN != 0; s_ucDdrN--)
    {
        if((AWTO_XB(AWTO_R_MCU_DC_READ_FLAG_A) & AWTO_DDRN_READ_FLAG) != 0)
        {
            return 1;
        }
    }
    return 0;
}
#endif

#pragma place bank(5)
static void AwtoDdrAddrU(DWORD ulU)
{
    AWTO_XB(AWTO_R_MCU_DC_ADDR_H_A) = (BYTE)(ulU >> 24);
    AWTO_XB(AWTO_R_MCU_DC_ADDR_M_A) = (BYTE)(ulU >> 16);
    AWTO_XB(AWTO_R_MCU_DC_ADDR_L_A) = (BYTE)(ulU >> 8);
    AWTO_XB(AWTO_R_MCU_DC_ADDR_A) = (BYTE)ulU;
}

#pragma place bank(5)
static void AwtoDdrAddr(unsigned int usSeq, BYTE ucBurst)
{
    AwtoDdrAddrU(AWTO_DDRN_UNITS0 + (DWORD)(usSeq & (AWTO_DDRN_SLOTS - 1)) * AWTO_DDRN_LINE_UNITS + (DWORD)ucBurst * (AWTO_DDRN_BURST_BYTES / 8));
}

#pragma place bank(5)
void AwtoDdrNoteWrite(void)
{
    BYTE ucB;
    BYTE ucJ;
    WORD usP;

    for(ucB = 0; ucB < AWTO_DDRN_BURSTS; ucB++)
    {
        if(AwtoDdrIdleMs() == 0)
        {
            return;
        }
        AwtoDdrAddr(g_usAwtoNoteN, ucB);
        for(ucJ = 0; ucJ < AWTO_DDRN_BURST_BYTES; ucJ++)
        {
            usP = (WORD)ucB * AWTO_DDRN_BURST_BYTES + ucJ;
            AWTO_XB(AWTO_R_MCU_DC_DATABUF_W_00_A + ((ucJ + AWTO_DDRN_HALF) % AWTO_DDRN_BURST_BYTES)) = (usP < AWTO_NOTE_SIZE) ? g_aucAwtoNote[usP] : 0;
        }
        AWTO_XB(AWTO_R_MCU_DC_CMD_A) = AWTO_DDRN_CMD_WRITE;
    }
}

#pragma place bank(5)
unsigned char AwtoDdrNoteRead(unsigned int usSeq, unsigned char ucBurst)
{
    if(AwtoDdrIdleMs() == 0)
    {
        return 0;
    }
    AwtoDdrAddr(usSeq, ucBurst);
    AWTO_XB(AWTO_R_MCU_DC_CMD_A) = AWTO_DDRN_CMD_READ;
    return AwtoDdrReadWait();
}

#if(_AWTO_DRAM_LOG == _ON)
static void AwtoDlNoteHdr(void);
#endif

#pragma place bank(5)
void AwtoHostNote(void)
{
    g_usAwtoNoteN++;
    if(g_aucAwtoNote[AWTO_NOTE_LEN] > AWTO_NOTE_CHARS)
    {
        g_aucAwtoNote[AWTO_NOTE_LEN] = AWTO_NOTE_CHARS;
    }
    AwtoDdrNoteWrite();                             // the text outlives the slot: the console redraw reads it from the DDR
#if(_AWTO_DRAM_LOG == _ON)
    AwtoDlNoteHdr();
#endif
    AwtoSyncPush(AWTO_SYNC_EV_NOTE, g_aucAwtoNote[AWTO_NOTE_LEN], g_usAwtoNoteN);      // value differs per note: never collapsed as a repeat
}

// DRAM log (docs/dram-log-design.md): the sync ring's history in the DDR. 16 B entry = one MCU_DC port A burst:
//   id, arg, ms32 (BE), value32 (BE), absolute index (24 bit BE), generation, boot, check = xor of bytes 0..14 ^ AWTO_DLOG_CHECK.
// Written from the XDATA tail (fw/log/sync.c) by the main loop only: no ISR touches port A.
#if(_AWTO_DRAM_LOG == _ON)

#define AWTO_DLOG_CHECK         0x5A
#define AWTO_DLOG_HDR_ID        'D'                 // header burst: 'D' 'L' version gen boot hint (32 bit BE) ... check
#define AWTO_DLOG_HDR_VER       1
#define AWTO_DLOG_FORCE         0x80                // AwtoDlFlush: also before Timer2 runs (the lines are not re-based then)
#define AWTO_DLOG_SCAN_MAX      (2 * AWTO_DLOG_HINT_EVERY + 2)   // a dropped hint write leaves the hint up to 2 x EVERY behind

__xdata DWORD g_ulAwtoDlMs;                         // ms the entry writes took, summed from 1 ms tick deltas (unbiased over many entries; host: delta / delta of ulWr = ms per entry)
__xdata BYTE g_ucAwtoDlBusy;                        // DDR port busy beyond the spin: ops left pending / unread since boot (255 max; host reads it at the map symbol)
static __xdata WORD s_usDlT;
static __xdata BYTE s_aucDl[16];                    // burst image (entry / header), memory order
static __xdata BYTE s_aucAtC[2][AWTO_DLOG_AT_B];    // AwtoSyncAt cache: DDR lines as tail entries (8 B ring entry + ms bits 31..16)
static __xdata DWORD s_pulAtAbs[2];                 // their absolute index (0xFFFFFFFF = empty)
static __xdata BYTE s_ucAtNext;

#pragma place bank(5)
static BYTE AwtoDlSum(void)
{
    BYTE ucJ;
    BYTE ucS = AWTO_DLOG_CHECK;

    for(ucJ = 0; ucJ < 15; ucJ++)
    {
        ucS ^= s_aucDl[ucJ];
    }
    return ucS;
}

#pragma place bank(5)
static void AwtoDlBusy(void)
{
    if(g_ucAwtoDlBusy != 0xFF)
    {
        g_ucAwtoDlBusy++;
    }
}

#pragma place bank(5)
static BYTE AwtoDlBurstW(DWORD ulUnits)             // s_aucDl -> DDR; 0 = port stalled, nothing written
{
    BYTE ucJ;

    if(g_ucAwtoDdrOff != 0)
    {
        return 0;                                   // memory off: the line stays pending in the XDATA tail (not a busy port)
    }
    if(AwtoDdrIdleSpin() == 0)
    {
        AwtoDlBusy();
        return 0;
    }
    AwtoDdrAddrU(ulUnits);
    for(ucJ = 0; ucJ < AWTO_DDRN_BURST_BYTES; ucJ++)
    {
        AWTO_XB(AWTO_R_MCU_DC_DATABUF_W_00_A + ((ucJ + AWTO_DDRN_HALF) % AWTO_DDRN_BURST_BYTES)) = s_aucDl[ucJ];
    }
    AWTO_XB(AWTO_R_MCU_DC_CMD_A) = AWTO_DDRN_CMD_WRITE;
    return 1;
}

#pragma place bank(5)
static BYTE AwtoDlBurstR(DWORD ulUnits)             // DDR -> s_aucDl; 0 = stalled
{
    BYTE ucJ;

    if(g_ucAwtoDdrOff != 0)
    {
        return 0;                                   // memory off: unread (the console shows it once the memory is up)
    }
    if(AwtoDdrIdleSpin() == 0)
    {
        AwtoDlBusy();
        return 0;
    }
    AwtoDdrAddrU(ulUnits);
    AWTO_XB(AWTO_R_MCU_DC_CMD_A) = AWTO_DDRN_CMD_READ;
    if(AwtoDdrReadSpin() == 0)
    {
        AwtoDlBusy();
        return 0;
    }
    for(ucJ = 0; ucJ < AWTO_DDRN_BURST_BYTES; ucJ++)
    {
        s_aucDl[ucJ] = AWTO_DDRN_BYTE(ucJ);
    }
    return 1;
}

#define AWTO_DLOG_UNIT(a)       (AWTO_DLOG_UNITS0 + ((DWORD)(a) & (AWTO_DLOG_SLOTS - 1)) * AWTO_DLOG_ENTRY_UNITS)

#pragma place bank(5)
static void AwtoDlHdr(DWORD ulHint)                 // header burst: generation, boot, index of the newest entry written at the last hint
{
    BYTE ucJ;

    for(ucJ = 0; ucJ < 16; ucJ++)
    {
        s_aucDl[ucJ] = 0;
    }
    s_aucDl[0] = AWTO_DLOG_HDR_ID;
    s_aucDl[1] = 'L';
    s_aucDl[2] = AWTO_DLOG_HDR_VER;
    s_aucDl[3] = g_stAwtoSync.ucGen;
    s_aucDl[4] = g_stAwtoSync.ucBoot;
    s_aucDl[5] = (BYTE)(ulHint >> 24);
    s_aucDl[6] = (BYTE)(ulHint >> 16);
    s_aucDl[7] = (BYTE)(ulHint >> 8);
    s_aucDl[8] = (BYTE)ulHint;
    s_aucDl[9] = (BYTE)(g_usAwtoNoteN >> 8);          // note numbering goes on over a reset (the DDR note lines are keyed by it)
    s_aucDl[10] = (BYTE)g_usAwtoNoteN;
    s_aucDl[15] = AwtoDlSum();
    AwtoDlBurstW(AWTO_DLOG_HDR_UNITS);
}

#pragma place bank(5)
static BYTE AwtoDlEntryOk(DWORD ulA)                // s_aucDl holds entry ulA of this generation
{
    return (AwtoDlSum() == s_aucDl[15]) && (s_aucDl[10] == (BYTE)(ulA >> 16)) && (s_aucDl[11] == (BYTE)(ulA >> 8)) && (s_aucDl[12] == (BYTE)ulA) &&
           (s_aucDl[13] == g_stAwtoSync.ucGen);
}

// Newest entry: the XDATA ring survived (ulAbs, pend valid) or the DDR header hint plus a forward scan over the slots that carry the next index.
#pragma place bank(5)
static DWORD AwtoDlScan(DWORD ulHint)
{
    BYTE ucN;

    for(ucN = 0; ucN < AWTO_DLOG_SCAN_MAX; ucN++)
    {
        if((AwtoDlBurstR(AWTO_DLOG_UNIT(ulHint)) == 0) || (AwtoDlEntryOk(ulHint) == 0))
        {
            break;
        }
        ulHint++;
    }
    return ulHint;
}

static void AwtoDlFlushN(BYTE ucMax);

#pragma place bank(5)
static BYTE AwtoDlInit(void)                        // first drain whose header read gets an answer: 0 = the DDR does not answer yet (writes before it are lost, unit 3)
{
    DWORD ulHint = 0;
    BYTE ucOk = 0;
    BYTE ucNew = (g_stAwtoSync.ucGen == 0);          // the XDATA ring was cleared at this boot (cold / another image): generation 0 is never a DDR generation

    if(AwtoDlBurstR(AWTO_DLOG_HDR_UNITS) == 0)
    {
        return 0;                                   // not answering: the next drain asks again; a failed read must not look like an empty DDR (that starts a new generation)
    }
    g_ulAwtoBootAbs -= g_stAwtoSync.ulWr + g_stAwtoSync.ucPend;        // its distance from the ring end stays: re-added below
    g_ulAwtoEpAbs -= g_stAwtoSync.ulWr + g_stAwtoSync.ucPend;
    ucOk = (s_aucDl[0] == AWTO_DLOG_HDR_ID) && (s_aucDl[1] == 'L') && (s_aucDl[2] == AWTO_DLOG_HDR_VER) && (AwtoDlSum() == s_aucDl[15]);
    ulHint = ((DWORD)s_aucDl[5] << 24) | ((DWORD)s_aucDl[6] << 16) | ((DWORD)s_aucDl[7] << 8) | s_aucDl[8];
    g_usAwtoNoteN = ((WORD)s_aucDl[9] << 8) | s_aucDl[10];
    s_pulAtAbs[0] = 0xFFFFFFFFUL;
    s_pulAtAbs[1] = 0xFFFFFFFFUL;
    if((AwtoBootReason() == AWTO_BOOT_COLD) || (ucOk == 0))
    {
        g_stAwtoSync.ucGen = (ucOk != 0) ? (BYTE)(s_aucDl[3] + 1) : (BYTE)((BYTE)AwtoMs() | 1);    // old generation + 1; no valid header (undefined DDR, another image): a time-derived odd value, never 0 (stale entries of generation 1 must not continue the new ring)
        g_stAwtoSync.ucBoot = 0;
        g_usAwtoNoteN = 0;
        g_stAwtoSync.ulWr = 0;
        g_stAwtoSync.ucPend -= g_stAwtoSync.ucOld;  // the previous boot's unwritten lines belong to a DDR that is gone
        g_stAwtoSync.ucOld = 0;
        ulHint = 0;
    }
    else
    {
        g_stAwtoSync.ucGen = s_aucDl[3];
        g_stAwtoSync.ucBoot = s_aucDl[4];
        if(ucNew != 0)                              // XDATA ring lost (another image): the position from the DDR
        {
            g_stAwtoSync.ulWr = AwtoDlScan(ulHint);
        }
    }
    g_stAwtoSync.ucBoot++;
    g_stAwtoSync.ucLost = 0;
    g_ulAwtoBootAbs += g_stAwtoSync.ulWr + g_stAwtoSync.ucPend;
    g_ulAwtoEpAbs += g_stAwtoSync.ulWr + g_stAwtoSync.ucPend;
    AwtoDlHdr(g_stAwtoSync.ulWr);
    return 1;
}

#pragma place bank(5)
static void AwtoDlFlushN(BYTE ucMax)
{
    BYTE ucForce = ucMax & AWTO_DLOG_FORCE;
    DWORD ulA;
    BYTE __xdata *puc;

    ucMax &= ~AWTO_DLOG_FORCE;
    if((ucForce == 0) && (g_usAwtoT2Base == 0xFFFF))
    {
        return;                                     // lines get re-based at the Timer2 start
    }
    while((g_stAwtoSync.ucPend != 0) && (ucMax != 0))
    {
        ulA = g_stAwtoSync.ulWr;
        puc = (BYTE __xdata *)&g_stAwtoSync.stTl[(BYTE)(g_stAwtoSync.ucHead - g_stAwtoSync.ucPend) & (AWTO_SYNC_TAIL - 1)];
        s_aucDl[0] = puc[0];
        s_aucDl[1] = puc[1];
        s_aucDl[2] = puc[8];                        // ms bits 31..24 (StAwtoSyncTl.ucMs3), then 23..16
        s_aucDl[3] = puc[9];
        s_aucDl[4] = puc[2];
        s_aucDl[5] = puc[3];
        s_aucDl[6] = puc[4];
        s_aucDl[7] = puc[5];
        s_aucDl[8] = puc[6];
        s_aucDl[9] = puc[7];
        s_aucDl[10] = (BYTE)(ulA >> 16);
        s_aucDl[11] = (BYTE)(ulA >> 8);
        s_aucDl[12] = (BYTE)ulA;
        s_aucDl[13] = g_stAwtoSync.ucGen;
        s_aucDl[14] = (g_stAwtoSync.ucOld != 0) ? (BYTE)(g_stAwtoSync.ucBoot - 1) : g_stAwtoSync.ucBoot;     // lines the previous boot left in the tail keep its number
        s_aucDl[15] = AwtoDlSum();
        s_usDlT = (WORD)AwtoMs();
        if(AwtoDlBurstW(AWTO_DLOG_UNIT(ulA)) == 0)
        {
            return;                                 // port stalled: the entry stays pending, the next pass tries again
        }
        g_ulAwtoDlMs += (WORD)((WORD)AwtoMs() - s_usDlT);
        g_stAwtoSync.ulWr++;
        g_stAwtoSync.ucPend--;
        if(g_stAwtoSync.ucOld != 0)
        {
            g_stAwtoSync.ucOld--;
        }
        ucMax--;
        if((((BYTE)ulA + 1) & (AWTO_DLOG_HINT_EVERY - 1)) == 0)
        {
            AwtoDlHdr(ulA + 1);
        }
    }
}

static __xdata BYTE s_ucDlOn;                       // 0 until a main-loop drain got the DDR header back: before that the DDR is not usable (XDATA zeroed at boot)

#pragma place bank(5)
void AwtoDlFlush(BYTE ucOp)                         // main context only: up to ucOp & 0x3F pending lines to the DDR (| AWTO_DLOG_FORCE: also before Timer2); nothing before the DDR answers
{
    if(s_ucDlOn == 0)
    {
        if((ucOp & AWTO_DLOG_FORCE) != 0)
        {
            return;
        }
        if(AwtoDlInit() == 0)
        {
            return;
        }
        s_ucDlOn = 1;
    }
    AwtoDlFlushN(ucOp);
}

#pragma place bank(5)
static void AwtoDlNoteHdr(void)                     // a note was logged: the header takes its number (hint = the written position, 64-aligned: at most 64 entries behind)
{
    AwtoDlHdr(g_stAwtoSync.ulWr & ~(DWORD)(AWTO_DLOG_HINT_EVERY - 1));
}

#pragma place bank(5)
static BYTE AwtoDlRead(DWORD ulA, BYTE __xdata *pucOut)
{
    if((AwtoDlBurstR(AWTO_DLOG_UNIT(ulA)) == 0) || (AwtoDlEntryOk(ulA) == 0))
    {
        return 0;
    }
    pucOut[0] = s_aucDl[0];
    pucOut[1] = s_aucDl[1];
    pucOut[2] = s_aucDl[4];
    pucOut[3] = s_aucDl[5];
    pucOut[4] = s_aucDl[6];
    pucOut[5] = s_aucDl[7];
    pucOut[6] = s_aucDl[8];
    pucOut[7] = s_aucDl[9];
    pucOut[8] = s_aucDl[2];                        // ms bits 31..16 at the tail entry's place (StAwtoSyncTl): the console delta
    pucOut[9] = s_aucDl[3];
    return 1;
}

static __xdata DWORD s_ulAtA;                       // AwtoSyncAt temporaries in XDATA: it sits on the deepest DATA overlay path (console line -> DDR read)
static __xdata BYTE s_ucAtD;
static __xdata BYTE s_ucAtS;

#pragma place bank(5)
BYTE __xdata *AwtoSyncAt(BYTE ucSeq)                // the ring line ucSeq (AWTO_SYNC_N back at most) as a 10 B entry (AWTO_DLOG_AT_B); an unwritten / lost one is all 0
{
    s_ucAtD = AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, ucSeq);
    if((s_ucAtD != 0) && (s_ucAtD <= AWTO_SYNC_TAIL) && (g_ucAwtoAtLaps == 0))
    {
        return AWTO_SYNC_ENT(s_ucAtD);              // the tail: lines not yet in the DDR and the newest written ones
    }
    s_ulAtA = (DWORD)g_ucAwtoAtLaps * AWTO_SYNC_WRAP + s_ucAtD;     // lines back (laps: the console's episode start row, past one seq wrap)
    s_ucAtD = (s_ulAtA != 0) && ((g_stAwtoSync.ulWr + g_stAwtoSync.ucPend) >= s_ulAtA);
    s_ulAtA = g_stAwtoSync.ulWr + g_stAwtoSync.ucPend - s_ulAtA;
    for(s_ucAtS = 0; s_ucAtS < 2; s_ucAtS++)
    {
        if(s_pulAtAbs[s_ucAtS] == s_ulAtA)
        {
            return s_aucAtC[s_ucAtS];
        }
    }
    s_ucAtS = s_ucAtNext;
    s_ucAtNext ^= 1;
    s_pulAtAbs[s_ucAtS] = 0xFFFFFFFFUL;
    if((s_ucAtD != 0) && (AwtoDlRead(s_ulAtA, s_aucAtC[s_ucAtS]) != 0))
    {
        s_pulAtAbs[s_ucAtS] = s_ulAtA;
    }
    else
    {
        for(s_ucAtD = 0; s_ucAtD < AWTO_DLOG_AT_B; s_ucAtD++)
        {
            s_aucAtC[s_ucAtS][s_ucAtD] = 0;
        }
    }
    return s_aucAtC[s_ucAtS];
}

#endif
