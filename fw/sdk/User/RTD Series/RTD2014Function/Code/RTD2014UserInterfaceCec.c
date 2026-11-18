//----------------------------------------------------------------------------------------------------
// ID Code      : RTD2014UserInterfaceCec.c No.0000
// Update Note  : awto: replaced by the CEC sink glue (docs/cec.md): replies from fw/cec/cec_msg.c, every frame logged
//----------------------------------------------------------------------------------------------------

#define __USER_INTERFACE_CEC__

#include "UserCommonInclude.h"
#include "cec_msg.h"

#if(_OSD_TYPE == _REALTEK_2014_OSD)

#if(_HDMI_CEC_SUPPORT == _ON)
//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************
#define CEC_TX_FREE                             0   // s_ucCecTx: no reply on the way
#define CEC_TX_SENT                             1   // reply handed to ScalerCec: the result is logged when the block is idle again
#define CEC_TX_RETRY                            3   // retransmissions of a reply (SDK value; limit 3 bits) [sdk-hypothesis]

//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************
static __xdata BYTE s_ucCecTx;

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
bit UserInterfaceCecGetCecActive(void);
void UserInterfaceCecReceivedNotify(StructCecRxReceivedInfo *pstCecRxInfo);
void UserInterfaceCecHighLevelFlow(void);
static void UserInterfaceCecLog(BYTE ucKind, BYTE ucFlags, BYTE ucHdr, BYTE *pucDb, BYTE ucLen);

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : registry cec_en (default on, Dan 2026-11-19)
// Input Value  : None
// Output Value : _TRUE: CEC block on
//--------------------------------------------------
bit UserInterfaceCecGetCecActive(void)
{
    return (AWTO_SET(CEC_EN) != 0);
}

//--------------------------------------------------
// Description  : one received frame (opcode + operands) from ScalerCec: log, answer, hook (analysing flag cleared by HighLevelFlow)
// Input Value  : pstCecRxInfo
// Output Value : None
//--------------------------------------------------
void UserInterfaceCecReceivedNotify(StructCecRxReceivedInfo *pstCecRxInfo)
{
    StCecReply stReply;

    UserInterfaceCecLog(AWTO_CEC_K_RX, AWTO_CEC_F_DEST_UNKNOWN, pstCecRxInfo->ucReceivedHb, pstCecRxInfo->pucReceivedDb, pstCecRxInfo->ucDbLength);
    if(CecMsgRx(pstCecRxInfo->ucReceivedHb >> 4, CEC_DEST_UNKNOWN, pstCecRxInfo->pucReceivedDb, pstCecRxInfo->ucDbLength, CEC_PA_TV,
                (SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL) ? CEC_POWER_ON : CEC_POWER_STANDBY, &stReply) != 0)
    {
        if(s_ucCecTx != CEC_TX_FREE)
        {
            AwtoSyncPush(AWTO_SYNC_EV_CEC, AWTO_CEC_K_DROP, 0);     // the previous reply is still on the way: the initiator asks again
        }
        else
        {
            // straight into the kernel's TX struct (no second copy); ScalerCecTxProcess takes it in this pass
            g_stCecTxTransmitInfo.ucTransmitHb = (CEC_LA_TV << 4) | stReply.ucDest;
            memcpy(g_stCecTxTransmitInfo.pucTransmitDb, stReply.pucDb, stReply.ucLen);
            g_stCecTxTransmitInfo.ucDbLength = stReply.ucLen;
            g_stCecTxTransmitInfo.b3RetryCnt = CEC_TX_RETRY;
            SET_CEC_TX_START();
            s_ucCecTx = CEC_TX_SENT;
            UserInterfaceCecLog(AWTO_CEC_K_TX, 0, g_stCecTxTransmitInfo.ucTransmitHb, g_stCecTxTransmitInfo.pucTransmitDb, g_stCecTxTransmitInfo.ucDbLength);
        }
    }
    if((stReply.ucHook != CEC_HOOK_NONE) && (AWTO_SET(CEC_CTL) != 0))
    {
        AwtoSyncPush(AWTO_SYNC_EV_CEC, AWTO_CEC_K_HOOK, stReply.ucHook);    // no action yet: Dan decides what CEC may control
    }
}

//--------------------------------------------------
// Description  : kind rx / tx / tx result / hook; the ring row is fmt cec (fw/awto/sync.tsv, fw/osd/console.c, scripts/sync_log.py)
// Input Value  : ucKind AWTO_CEC_K_*, ucFlags, ucHdr (initiator << 4 | destination), pucDb (opcode + operands), ucLen
// Output Value : None
//--------------------------------------------------
static void UserInterfaceCecLog(BYTE ucKind, BYTE ucFlags, BYTE ucHdr, BYTE *pucDb, BYTE ucLen)
{
    DWORD ulV = (DWORD)ucHdr << 24;

    if(ucLen > 0)
    {
        ulV |= (DWORD)pucDb[0] << 16;
    }
    if(ucLen > 1)
    {
        ulV |= (DWORD)pucDb[1] << 8;
    }
    if(ucLen > 2)
    {
        ulV |= pucDb[2];
    }
    AwtoSyncPush(AWTO_SYNC_EV_CEC, ucFlags | (BYTE)(ucLen << AWTO_CEC_LEN_SHIFT) | ucKind, ulV);
}

//--------------------------------------------------
// Description  : main loop: log the result of the last reply, release the RX path
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void UserInterfaceCecHighLevelFlow(void)
{
    if((s_ucCecTx == CEC_TX_SENT) && (GET_CEC_TX_START() == _FALSE) && (ScalerCecGetTxState() == _CEC_TX_IDLE_STATE))
    {
        AwtoSyncPush(AWTO_SYNC_EV_CEC, AWTO_CEC_K_TXRES, ScalerCecTxGetTransmitResult());
        s_ucCecTx = CEC_TX_FREE;
    }
    if(ScalerCecRxGetMsgAnalyzingFlag() == _TRUE)
    {
        ScalerCecRxClrIMsgAnalyzingFlag();      // the frame was handled in UserInterfaceCecReceivedNotify
    }
}
#endif

#endif // End of #if(_OSD_TYPE == _REALTEK_2014_OSD)
