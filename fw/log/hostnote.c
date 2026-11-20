#include "SysInclude.h"

// #273 host note: the host writes the text slot over 0x35 (tag = next sequence), then test cmd AWTO_TC_HOST_NOTE: one ring entry per note.
// A newer note overwrites the slot: the older entry's sequence no longer matches the tag and the decoders print "text overwritten".
__xdata unsigned int g_usAwtoNoteN;                 // sequence of the last logged note
__xdata BYTE g_aucAwtoNote[AWTO_NOTE_SIZE];

static bit AwtoDdrIdle(void)                        // MCU_DC port A command idle (write ~1.7 us); 0 = stall, the op is dropped
{
    BYTE ucN;
    DWORD ulT;

    for(ucN = AWTO_DDRN_SPIN; ucN != 0; ucN--)
    {
        if((AWTO_XB(AWTO_R_MCU_DC_CMD_A) & AWTO_F_MCU_DC_CMD_A_DDR_A_CMD) == 0)
        {
            return _TRUE;
        }
    }
    ulT = AwtoMs();
    while((AWTO_XB(AWTO_R_MCU_DC_CMD_A) & AWTO_F_MCU_DC_CMD_A_DDR_A_CMD) != 0)
    {
        if((AwtoMs() - ulT) >= AWTO_DDRN_STALL_MS)
        {
            return _FALSE;
        }
    }
    return _TRUE;
}

static void AwtoDdrAddr(unsigned int usSeq, BYTE ucBurst)
{
    DWORD ulU = AWTO_DDRN_UNITS0 + (DWORD)(usSeq & (AWTO_DDRN_SLOTS - 1)) * AWTO_DDRN_LINE_UNITS + (DWORD)ucBurst * (AWTO_DDRN_BURST_BYTES / 8);

    AWTO_XB(AWTO_R_MCU_DC_ADDR_H_A) = (BYTE)(ulU >> 24);
    AWTO_XB(AWTO_R_MCU_DC_ADDR_M_A) = (BYTE)(ulU >> 16);
    AWTO_XB(AWTO_R_MCU_DC_ADDR_L_A) = (BYTE)(ulU >> 8);
    AWTO_XB(AWTO_R_MCU_DC_ADDR_A) = (BYTE)ulU;
}

void AwtoDdrNoteWrite(void)
{
    BYTE ucB;
    BYTE ucJ;
    WORD usP;

    for(ucB = 0; ucB < AWTO_DDRN_BURSTS; ucB++)
    {
        if(AwtoDdrIdle() == _FALSE)
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

unsigned char AwtoDdrNoteRead(unsigned int usSeq, unsigned char ucBurst)
{
    BYTE ucN;
    DWORD ulT;

    if(AwtoDdrIdle() == _FALSE)
    {
        return 0;
    }
    AwtoDdrAddr(usSeq, ucBurst);
    AWTO_XB(AWTO_R_MCU_DC_CMD_A) = AWTO_DDRN_CMD_READ;
    for(ucN = AWTO_DDRN_SPIN; ucN != 0; ucN--)
    {
        if((AWTO_XB(AWTO_R_MCU_DC_READ_FLAG_A) & AWTO_DDRN_READ_FLAG) != 0)
        {
            return 1;
        }
    }
    ulT = AwtoMs();
    while((AWTO_XB(AWTO_R_MCU_DC_READ_FLAG_A) & AWTO_DDRN_READ_FLAG) == 0)
    {
        if((AwtoMs() - ulT) >= AWTO_DDRN_STALL_MS)
        {
            return 0;
        }
    }
    return 1;
}

void AwtoHostNote(void)
{
    g_usAwtoNoteN++;
    if(g_aucAwtoNote[AWTO_NOTE_LEN] > AWTO_NOTE_CHARS)
    {
        g_aucAwtoNote[AWTO_NOTE_LEN] = AWTO_NOTE_CHARS;
    }
    AwtoDdrNoteWrite();                             // the text outlives the slot: the console redraw reads it from the DDR
    AwtoSyncPush(AWTO_SYNC_EV_NOTE, g_aucAwtoNote[AWTO_NOTE_LEN], g_usAwtoNoteN);      // value differs per note: never collapsed as a repeat
}
