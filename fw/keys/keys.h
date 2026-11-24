// key ids = SDK key messages (menu.h MK_*), test cmd 0x01..0x05 - 1. Inside the menu / selector (Dan 2026-11-08, kept #132):
// AUTO = enter / take, MENU = back / cancel. Nothing open (#132): MENU opens the menu, AUTO = auto source select.
#define AWTO_K_AUTO                             _MENU_KEY_MESSAGE
#define AWTO_K_UP                               _RIGHT_KEY_MESSAGE
#define AWTO_K_DOWN                             _LEFT_KEY_MESSAGE
#define AWTO_K_MENU                             _EXIT_KEY_MESSAGE
#define AWTO_K_SOURCE                           AWTO_KEY_MSG_SOURCE
#define AWTO_K_POWER                            5
#define AWTO_K_UP_DOWN                          6       // combo: diagnostic console on / off
#define AWTO_K_NONE                             0xFF
#define AWTO_KEV_PRESS                          0
#define AWTO_KEV_REPEAT                         1
#define AWTO_KEV_RELEASE                        2
#define AWTO_KEV_COMBO                          3
#define AWTO_KEV_INJ                            0x80    // flag: injected (test cmd 0x01..0x05, key_inject)

// fw/keys: key panel + log (keytest.c) used by the key reader (keys.c)
void AwtoKeyEnsure(void);
void AwtoKeyLog(BYTE ucMask, BYTE ucMsg, BYTE ucFlags);
void AwtoKeyMsgNote(BYTE ucMsg);
void AwtoKeyShow(void);
void AwtoKeyClick(void);
