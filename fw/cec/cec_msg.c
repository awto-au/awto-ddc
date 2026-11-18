#include "cec_msg.h"

// CEC sink (device type TV, logical address 0) reply rules; the register layer is ScalerCec.c, the glue RTD2014UserInterfaceCec.c.
#ifndef CEC_CODE
#define CEC_CODE __code
#endif

// Opcodes that are broadcast-only in the spec: with an unknown destination (CEC_DEST_UNKNOWN) never answered with <Feature Abort>.
static const CEC_CODE unsigned char tCecBcastOp[] = {
    0x32,                                   // Set Menu Language
    CEC_OP_ROUTING_CHANGE, CEC_OP_ROUTING_INFORMATION, CEC_OP_ACTIVE_SOURCE, CEC_OP_REPORT_PHYSICAL_ADDR,
    CEC_OP_REQUEST_ACTIVE_SRC, CEC_OP_SET_STREAM_PATH, CEC_OP_DEVICE_VENDOR_ID, 0x89, 0x8A, 0x8B, 0xA0};
static const CEC_CODE char tCecName[] = CEC_OSD_NAME;

static unsigned char CecBcastOp(unsigned char ucOp)
{
    unsigned char ucI;

    for(ucI = 0; ucI < sizeof(tCecBcastOp); ucI++)
    {
        if(tCecBcastOp[ucI] == ucOp)
        {
            return 1;
        }
    }
    return 0;
}

static void CecAbort(StCecReply *pR, unsigned char ucInit, unsigned char ucOp, unsigned char ucReason)
{
    pR->ucDest = ucInit;
    pR->pucDb[0] = CEC_OP_FEATURE_ABORT;
    pR->pucDb[1] = ucOp;
    pR->pucDb[2] = ucReason;
    pR->ucLen = 3;
}

unsigned char CecMsgRx(unsigned char ucInit, unsigned char ucDest, const unsigned char *pucDb, unsigned char ucLen,
                       unsigned short usPhys, unsigned char ucPower, StCecReply *pR)
{
    unsigned char ucOp, ucI;

    pR->ucLen = 0;
    pR->ucHook = CEC_HOOK_NONE;
    pR->ucDest = ucInit;
    if((ucLen == 0) || (ucLen > CEC_MAX_DB) || (ucInit == CEC_LA_BROADCAST))
    {
        return 0;                           // polling message: the block acks by logical address, nothing to answer
    }
    ucOp = pucDb[0];
    pR->ucHook = (ucOp == CEC_OP_STANDBY) ? CEC_HOOK_STANDBY :
                 ((ucOp == CEC_OP_IMAGE_VIEW_ON) || (ucOp == CEC_OP_TEXT_VIEW_ON)) ? CEC_HOOK_WAKE :
                 ((ucOp == CEC_OP_ACTIVE_SOURCE) || (ucOp == CEC_OP_SET_STREAM_PATH) || (ucOp == CEC_OP_ROUTING_INFORMATION) ||
                  (ucOp == CEC_OP_ROUTING_CHANGE)) ? CEC_HOOK_ACTIVE_SOURCE :
                 ((ucOp == CEC_OP_USER_CONTROL_PRESSED) || (ucOp == CEC_OP_USER_CONTROL_RELEASED)) ? CEC_HOOK_USER_CONTROL : CEC_HOOK_NONE;
    if(ucDest == CEC_LA_BROADCAST)
    {
        return 0;                           // broadcast: no request is answered (spec), hooks only
    }
    switch(ucOp)
    {
        case CEC_OP_GIVE_PHYSICAL_ADDR:     // answer is a broadcast
            pR->ucDest = CEC_LA_BROADCAST;
            pR->pucDb[0] = CEC_OP_REPORT_PHYSICAL_ADDR;
            pR->pucDb[1] = (unsigned char)(usPhys >> 8);
            pR->pucDb[2] = (unsigned char)usPhys;
            pR->pucDb[3] = CEC_DEVTYPE_TV;
            pR->ucLen = 4;
            break;
        case CEC_OP_GIVE_VENDOR_ID:         // broadcast as well
            pR->ucDest = CEC_LA_BROADCAST;
            pR->pucDb[0] = CEC_OP_DEVICE_VENDOR_ID;
            pR->pucDb[1] = (unsigned char)(CEC_VENDOR_ID >> 16);
            pR->pucDb[2] = (unsigned char)(CEC_VENDOR_ID >> 8);
            pR->pucDb[3] = (unsigned char)CEC_VENDOR_ID;
            pR->ucLen = 4;
            break;
        case CEC_OP_GET_CEC_VERSION:
            pR->pucDb[0] = CEC_OP_CEC_VERSION;
            pR->pucDb[1] = CEC_VERSION_1_4;
            pR->ucLen = 2;
            break;
        case CEC_OP_GIVE_OSD_NAME:
            pR->pucDb[0] = CEC_OP_SET_OSD_NAME;
            for(ucI = 0; (ucI < sizeof(tCecName) - 1) && (ucI < 14); ucI++)
            {
                pR->pucDb[1 + ucI] = (unsigned char)tCecName[ucI];
            }
            pR->ucLen = 1 + ucI;
            break;
        case CEC_OP_GIVE_POWER_STATUS:
            pR->pucDb[0] = CEC_OP_REPORT_POWER_STATUS;
            pR->pucDb[1] = ucPower;
            pR->ucLen = 2;
            break;
        case CEC_OP_ABORT:                  // spec: always <Feature Abort> [refused]
            CecAbort(pR, ucInit, CEC_OP_ABORT, CEC_ABORT_REFUSED);
            break;
        case CEC_OP_FEATURE_ABORT:          // never answer an abort
        case CEC_OP_REPORT_PHYSICAL_ADDR:   // answers and announcements from other devices: logged, no reply
        case CEC_OP_DEVICE_VENDOR_ID:
        case CEC_OP_SET_OSD_NAME:
        case CEC_OP_REPORT_POWER_STATUS:
        case CEC_OP_CEC_VERSION:
        case CEC_OP_ACTIVE_SOURCE:
        case CEC_OP_SET_STREAM_PATH:
        case CEC_OP_ROUTING_INFORMATION:
        case CEC_OP_ROUTING_CHANGE:
        case CEC_OP_REQUEST_ACTIVE_SRC:
        case CEC_OP_INACTIVE_SOURCE:
        case CEC_OP_IMAGE_VIEW_ON:
        case CEC_OP_TEXT_VIEW_ON:
        case CEC_OP_STANDBY:
        case CEC_OP_USER_CONTROL_PRESSED:
        case CEC_OP_USER_CONTROL_RELEASED:
            break;
        default:                            // not implemented: abort when directed, or when the destination cannot be told and it is no broadcast opcode
            if((ucDest != CEC_DEST_UNKNOWN) || (CecBcastOp(ucOp) == 0))
            {
                CecAbort(pR, ucInit, ucOp, CEC_ABORT_UNRECOGNIZED);
            }
            break;
    }
    return pR->ucLen;
}
