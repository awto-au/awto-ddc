#include "SysInclude.h"

// #273 host note: the host writes the text slot over 0x35 (tag = next sequence), then test cmd AWTO_TC_HOST_NOTE: one ring entry per note.
// A newer note overwrites the slot: the older entry's sequence no longer matches the tag and the decoders print "text overwritten".
__xdata unsigned int g_usAwtoNoteN;                 // sequence of the last logged note
__xdata BYTE g_aucAwtoNote[AWTO_NOTE_SIZE];

void AwtoHostNote(void)
{
    g_usAwtoNoteN++;
    if(g_aucAwtoNote[AWTO_NOTE_LEN] > AWTO_NOTE_CHARS)
    {
        g_aucAwtoNote[AWTO_NOTE_LEN] = AWTO_NOTE_CHARS;
    }
    AwtoSyncPush(AWTO_SYNC_EV_NOTE, g_aucAwtoNote[AWTO_NOTE_LEN], g_usAwtoNoteN);      // value differs per note: never collapsed as a repeat
}
