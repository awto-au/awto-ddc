#include "UserCommonInclude.h"

// #80 IP over DDC, main-loop side (docs/ip-over-ddc.md).
// Link: g_stAwtoNet rings; Transport B lives in the EXINT1 ISR (fw/diag/dbgisr.c), Transport A = AwtoNetXchgA (DDC/CI op D0).
// Stack: SLIP-framed Ethernet frames; config ethertype 0x88B5 (host sets MAC + IP), ARP, IPv4 ICMP echo, UDP 7 echo,
// UDP AWTO_NET_PORT service (settings by registry id #67, message ring #56). One frame buffer: RX decode -> reply -> TX encode.
#if(_AWTO_NET == _ON)
#define AWTO_NET_PORT                   5577
#define AWTO_NET_END                    0xC0    // SLIP (RFC 1055)
#define AWTO_NET_ESC                    0xDB
#define AWTO_NET_ESC_END                0xDC
#define AWTO_NET_ESC_ESC                0xDD
#define AWTO_NET_Q                      64      // service request bytes kept (the reply is built in the frame buffer)
#define AWTO_NET_GET_MAX                32      // ids per get: 4 + 4 x 32 reply bytes
#define AWTO_NET_SET_MAX                16
#define AWTO_NET_MSG_MAX                40      // entries per message datagram: 7 + 6 x 40 = 247 <= MTU - 28
#ifdef _AWTO_NEW_SETTINGS                       // awto-rtdfw settings.h (#67)
extern unsigned char set_idx(unsigned char ucId);
extern unsigned char set_put(unsigned char ucId, int iV, unsigned char ucApplyNow);
#endif

__xdata StAwtoNetLink g_stAwtoNet;
__xdata BYTE g_ucAwtoNetRun;
static __xdata BYTE s_pucAwtoNetBuf[AWTO_NET_BUF];
static __xdata BYTE s_pucAwtoNetQ[AWTO_NET_Q];
static __xdata WORD s_usAwtoNetLen;             // RX: bytes decoded so far; TX: frame length
static __xdata WORD s_usAwtoNetPos;             // TX: next frame byte to encode
static __xdata BYTE s_ucAwtoNetTx;              // TX state: 0 idle, 1 leading END, 2 body, 3 escape second byte pending
static __xdata BYTE s_ucAwtoNetEsc;             // RX: 1 after ESC, 2 = frame too long, drop to the next END
static __xdata BYTE s_pucAwtoNetMac[6];
static __xdata BYTE s_pucAwtoNetIp[4];          // 0.0.0.0 = not configured: only config frames are answered
static __xdata BYTE s_pucAwtoNetPeer[12];       // reply / stream target: MAC 6, IP 4, UDP port 2
static __xdata BYTE s_pucAwtoNetSub[12];        // message-ring subscriber (same layout), valid while s_ucAwtoNetSubOn
static __xdata BYTE s_ucAwtoNetSubOn;
static __xdata WORD s_usAwtoNetMsgSeq;          // next message seq to stream
static __xdata WORD s_usAwtoNetIpId;

BYTE AwtoNetXchgA(BYTE *pucQ, BYTE ucN, BYTE *pucR)    // Transport A, main loop: pucQ = seq ctl ack data[ucN]; pucR <- seq flags free data
{
    BYTE ucF = 0;
    BYTE ucM;
    BYTE ucI;

    if(ucN > AWTO_NET_A_IN)
    {
        ucN = AWTO_NET_A_IN;
    }
    if(pucQ[0] == g_stAwtoNet.ucASeq)
    {
        ucF = g_stAwtoNet.ucAFlags;
    }
    else if(g_stAwtoNet.ucReset == 0)
    {
        ucM = g_stAwtoNet.ucTxHead - g_stAwtoNet.ucTxTail;
        g_stAwtoNet.ucTxTail += (pucQ[2] < ucM) ? pucQ[2] : ucM;
        ucM = AWTO_NET_RING - (BYTE)(g_stAwtoNet.ucRxHead - g_stAwtoNet.ucRxTail);
        if((pucQ[1] & AWTO_NET_CTL_RESET) != 0)
        {
            g_stAwtoNet.ucReset = 1;
        }
        else if(ucN <= ucM)
        {
            for(ucI = 0; ucI < ucN; ucI++)
            {
                g_stAwtoNet.pucRx[(BYTE)(g_stAwtoNet.ucRxHead + ucI) & AWTO_NET_MASK] = pucQ[3 + ucI];
            }
            g_stAwtoNet.ucRxHead += ucN;
            ucF = AWTO_NET_F_ACC;
        }
        else
        {
            ucF = AWTO_NET_F_FULL;
        }
        g_stAwtoNet.ucCtl = pucQ[1] & ~AWTO_NET_CTL_RESET;
        g_stAwtoNet.ucASeq = pucQ[0];
        g_stAwtoNet.ucAFlags = ucF;
    }
    g_ucAwtoNetRun = 1;
    ucM = (g_stAwtoNet.ucReset != 0) ? 0 : (BYTE)(g_stAwtoNet.ucTxHead - g_stAwtoNet.ucTxTail);
    ucF |= AWTO_NET_F_UP | ((g_stAwtoNet.ucReset != 0) ? AWTO_NET_F_RESET : 0) |
           (((g_stAwtoNet.ucCtl & AWTO_NET_CTL_ECHO) != 0) ? AWTO_NET_F_ECHO : 0);
    if(ucM > AWTO_NET_A_MAX)
    {
        ucM = AWTO_NET_A_MAX;
        ucF |= AWTO_NET_F_MORE;
    }
    pucR[0] = pucQ[0];
    pucR[1] = ucF;
    pucR[2] = AWTO_NET_RING - (BYTE)(g_stAwtoNet.ucRxHead - g_stAwtoNet.ucRxTail);
    for(ucI = 0; ucI < ucM; ucI++)
    {
        pucR[3 + ucI] = g_stAwtoNet.pucTx[(BYTE)(g_stAwtoNet.ucTxTail + ucI) & AWTO_NET_MASK];
    }
    return ucM;
}

static void AwtoNetTxPush(void)                 // SLIP-encode the pending frame into the TX ring, as far as it fits
{
    BYTE ucH = g_stAwtoNet.ucTxHead;
    BYTE ucFree = AWTO_NET_RING - (BYTE)(ucH - g_stAwtoNet.ucTxTail);
    BYTE ucV;

    while((ucFree != 0) && (s_ucAwtoNetTx != 0))
    {
        if(s_ucAwtoNetTx == 1)
        {
            ucV = AWTO_NET_END;                 // leading END: flushes line noise at the host decoder
            s_ucAwtoNetTx = 2;
        }
        else if(s_ucAwtoNetTx == 3)
        {
            ucV = (s_pucAwtoNetBuf[s_usAwtoNetPos++] == AWTO_NET_END) ? AWTO_NET_ESC_END : AWTO_NET_ESC_ESC;
            s_ucAwtoNetTx = 2;
        }
        else if(s_usAwtoNetPos >= s_usAwtoNetLen)
        {
            ucV = AWTO_NET_END;
            s_ucAwtoNetTx = 0;
            s_usAwtoNetLen = 0;
        }
        else
        {
            ucV = s_pucAwtoNetBuf[s_usAwtoNetPos];
            if((ucV == AWTO_NET_END) || (ucV == AWTO_NET_ESC))
            {
                ucV = AWTO_NET_ESC;
                s_ucAwtoNetTx = 3;
            }
            else
            {
                s_usAwtoNetPos++;
            }
        }
        g_stAwtoNet.pucTx[ucH & AWTO_NET_MASK] = ucV;
        ucH++;
        ucFree--;
    }
    g_stAwtoNet.ucTxHead = ucH;                 // one publish: the transport never sees a half-written byte
}

static void AwtoNetSend(WORD usLen)
{
    s_usAwtoNetLen = usLen;
    s_usAwtoNetPos = 0;
    s_ucAwtoNetTx = 1;
}

static bit AwtoNetEq(__xdata BYTE *pucA, __xdata BYTE *pucB, BYTE ucN)
{
    while(ucN-- != 0)
    {
        if(*pucA++ != *pucB++)
        {
            return _FALSE;
        }
    }
    return _TRUE;
}

static void AwtoNetCopy(__xdata BYTE *pucD, __xdata BYTE *pucS, BYTE ucN)
{
    while(ucN-- != 0)
    {
        *pucD++ = *pucS++;
    }
}

static WORD AwtoNetSum(__xdata BYTE *pucP, BYTE ucN)   // Internet checksum (RFC 1071) of an even byte count
{
    WORD usS = 0;
    WORD usW;

    for(; ucN != 0; ucN -= 2, pucP += 2)
    {
        usW = ((WORD)pucP[0] << 8) | pucP[1];
        usS += usW;
        if(usS < usW)
        {
            usS++;
        }
    }
    return ~usS;
}

static void AwtoNetEthTo(__xdata BYTE *pucMac, WORD usType)
{
    AwtoNetCopy(s_pucAwtoNetBuf, pucMac, 6);
    AwtoNetCopy(s_pucAwtoNetBuf + 6, s_pucAwtoNetMac, 6);
    s_pucAwtoNetBuf[12] = usType >> 8;
    s_pucAwtoNetBuf[13] = usType;
}

static void AwtoNetUdpTo(__xdata BYTE *pucPeer, WORD usPay)     // headers for usPay payload bytes at offset 42, then send
{
    __xdata BYTE *pucIp = s_pucAwtoNetBuf + 14;
    WORD usT = 28 + usPay;
    WORD usS;

    AwtoNetEthTo(pucPeer, 0x0800);
    pucIp[0] = 0x45;
    pucIp[1] = 0;
    pucIp[2] = usT >> 8;
    pucIp[3] = usT;
    s_usAwtoNetIpId++;
    pucIp[4] = s_usAwtoNetIpId >> 8;
    pucIp[5] = s_usAwtoNetIpId;
    pucIp[6] = 0x40;                            // DF
    pucIp[7] = 0;
    pucIp[8] = 64;
    pucIp[9] = 17;
    pucIp[10] = 0;
    pucIp[11] = 0;
    AwtoNetCopy(pucIp + 12, s_pucAwtoNetIp, 4);
    AwtoNetCopy(pucIp + 16, pucPeer + 6, 4);
    usS = AwtoNetSum(pucIp, 20);
    pucIp[10] = usS >> 8;
    pucIp[11] = usS;
    pucIp[20] = AWTO_NET_PORT >> 8;
    pucIp[21] = AWTO_NET_PORT & 0xFF;
    pucIp[22] = pucPeer[10];
    pucIp[23] = pucPeer[11];
    usT = 8 + usPay;
    pucIp[24] = usT >> 8;
    pucIp[25] = usT;
    pucIp[26] = 0;                              // no UDP checksum (IPv4): every link byte is already checksummed
    pucIp[27] = 0;
    AwtoNetSend(42 + usPay);
}

#if(_DEBUG_MESSAGE_SUPPORT == _ON)
static BYTE AwtoNetMsgPut(__xdata BYTE *pucP, WORD usFrom)     // [lost seqH seqL n (idH idL v3 v2 v1 v0) x n]; returns bytes
{
    WORD usSeq = g_usAwtoMsgSeq;
    WORD usBack = usSeq - usFrom;
    BYTE ucLost = 0;
    BYTE ucN;
    BYTE ucK;
    BYTE ucI;

    if(usBack > AWTO_MSG_RING)
    {
        ucLost = ((usBack - AWTO_MSG_RING) > 255) ? 255 : (BYTE)(usBack - AWTO_MSG_RING);
        usBack = AWTO_MSG_RING;
        usFrom = usSeq - AWTO_MSG_RING;
    }
    ucN = (usBack > AWTO_NET_MSG_MAX) ? AWTO_NET_MSG_MAX : (BYTE)usBack;
    ucK = (g_ucAwtoMsgHead + AWTO_MSG_RING - (BYTE)usBack) % AWTO_MSG_RING;
    pucP[0] = ucLost;
    pucP[1] = usFrom >> 8;
    pucP[2] = usFrom;
    pucP[3] = ucN;
    pucP += 4;
    for(ucI = 0; ucI < ucN; ucI++)
    {
        pucP[0] = g_pstAwtoMsgRing[ucK].usId >> 8;
        pucP[1] = g_pstAwtoMsgRing[ucK].usId;
        pucP[2] = g_pstAwtoMsgRing[ucK].ulValue >> 24;
        pucP[3] = g_pstAwtoMsgRing[ucK].ulValue >> 16;
        pucP[4] = g_pstAwtoMsgRing[ucK].ulValue >> 8;
        pucP[5] = g_pstAwtoMsgRing[ucK].ulValue;
        pucP += 6;
        ucK = (ucK + 1 >= AWTO_MSG_RING) ? 0 : ucK + 1;
    }
    s_usAwtoNetMsgSeq = usFrom + ucN;
    return 4 + 6 * ucN;
}
#endif

static void AwtoNetSetting(__xdata BYTE *pucR, BYTE ucId, BYTE ucSet, WORD usV)    // pucR <- id st hi lo
{
    pucR[0] = ucId;
#ifdef _AWTO_NEW_SETTINGS
    if(set_idx(ucId) == 0xFF)
    {
        pucR[1] = 0x01;                         // no such id
    }
    else
    {
        pucR[1] = ((ucSet != 0) && (set_put(ucId, (int)usV, 1) == 0)) ? 0x02 : 0x00;     // 2 = refused (read-only, range)
        usV = (WORD)set_get(ucId);
    }
#else
    pucR[1] = 0xFE;                             // image without the #67 registry
    usV = 0;
    ucSet = ucSet;
#endif
    pucR[2] = usV >> 8;
    pucR[3] = usV;
}

static WORD AwtoNetService(BYTE ucN)            // request in s_pucAwtoNetQ[ucN]; reply at buf + 42; returns its length, 0 = none
{
    __xdata BYTE *pucR = s_pucAwtoNetBuf + 42;
    __xdata BYTE *pucQ = s_pucAwtoNetQ;
    BYTE ucI;
    BYTE ucK;

    if(ucN < 2)
    {
        return 0;
    }
    pucR[0] = pucQ[0] | 0x80;
    pucR[1] = pucQ[1];
    pucR[2] = 0;
    switch(pucQ[0])
    {
        case 0x01:                              // info: ver flags ring mtuH mtuL seqH seqL
            pucR[3] = 1;
#ifdef _AWTO_NEW_SETTINGS
            pucR[4] = 0x01;
#else
            pucR[4] = 0x00;
#endif
#if(_DEBUG_MESSAGE_SUPPORT == _ON)
            pucR[4] |= (g_ucAwtoMsgOn != 0) ? 0x02 : 0x00;
            pucR[5] = AWTO_MSG_RING;
            pucR[8] = g_usAwtoMsgSeq >> 8;
            pucR[9] = g_usAwtoMsgSeq;
#else
            pucR[5] = 0;
            pucR[8] = 0;
            pucR[9] = 0;
#endif
            pucR[6] = (AWTO_NET_BUF - 14) >> 8;
            pucR[7] = (AWTO_NET_BUF - 14) & 0xFF;
            return 10;

        case 0x02:                              // get: n id[n] -> n (id st hi lo)[n]
        case 0x03:                              // set: n (id hi lo)[n] -> n (id st hi lo)[n], read back after the set
            if(ucN < 3)
            {
                return 0;
            }
            ucK = (pucQ[0] == 0x02) ? 1 : 3;
            ucN = (ucN - 3) / ucK;
            if(ucN > pucQ[2])
            {
                ucN = pucQ[2];
            }
            if(ucN > ((ucK == 1) ? AWTO_NET_GET_MAX : AWTO_NET_SET_MAX))
            {
                ucN = (ucK == 1) ? AWTO_NET_GET_MAX : AWTO_NET_SET_MAX;
            }
            pucR[3] = ucN;
            for(ucI = 0; ucI < ucN; ucI++)
            {
                pucQ = s_pucAwtoNetQ + 3 + ucI * ucK;
                AwtoNetSetting(pucR + 4 + 4 * ucI, pucQ[0], (ucK == 3), (ucK == 3) ? (((WORD)pucQ[1] << 8) | pucQ[2]) : 0);
            }
            return 4 + 4 * ucN;

#if(_DEBUG_MESSAGE_SUPPORT == _ON)
        case 0x04:                              // subscribe: flags (bit0 stream to me, bit1 message ring on) -> seqH seqL
            if(ucN < 3)
            {
                return 0;
            }
            s_ucAwtoNetSubOn = pucQ[2] & 0x01;
            AwtoNetCopy(s_pucAwtoNetSub, s_pucAwtoNetPeer, 12);
            if((pucQ[2] & 0x02) != 0)
            {
                g_ucAwtoMsgOn = 1;
            }
            s_usAwtoNetMsgSeq = g_usAwtoMsgSeq;
            pucR[3] = g_usAwtoMsgSeq >> 8;
            pucR[4] = g_usAwtoMsgSeq;
            return 5;

        case 0x06:                              // read: seqH seqL -> lost seqH seqL n entries (as push 0x05)
            if(ucN < 4)
            {
                return 0;
            }
            return 3 + AwtoNetMsgPut(pucR + 3, ((WORD)pucQ[2] << 8) | pucQ[3]);
#endif

        default:
            pucR[2] = 0xFF;                     // unknown op
            return 3;
    }
}

static void AwtoNetFrame(void)                  // one received frame in s_pucAwtoNetBuf[s_usAwtoNetLen]; may start a reply
{
    __xdata BYTE *pucP = s_pucAwtoNetBuf;
    __xdata BYTE *pucIp = s_pucAwtoNetBuf + 14;
    WORD usT;
    WORD usS;

    if(s_usAwtoNetLen < 14)
    {
        return;
    }
    usT = ((WORD)pucP[12] << 8) | pucP[13];
    if(usT == 0x88B5)                           // config (local experimental ethertype): 'A' 'W' op ...
    {
        if((s_usAwtoNetLen < 17) || (pucP[14] != 'A') || (pucP[15] != 'W'))
        {
            return;
        }
        if((pucP[16] == 1) && (s_usAwtoNetLen >= 27))       // set: mac[6] ip[4]
        {
            AwtoNetCopy(s_pucAwtoNetMac, pucP + 17, 6);
            AwtoNetCopy(s_pucAwtoNetIp, pucP + 23, 4);
        }
        else if(pucP[16] != 3)                  // 3 = query
        {
            return;
        }
        AwtoNetCopy(s_pucAwtoNetPeer, pucP + 6, 6);
        AwtoNetEthTo(s_pucAwtoNetPeer, 0x88B5);
        pucP[16] = 2;                           // status: mac ip ver
        AwtoNetCopy(pucP + 17, s_pucAwtoNetMac, 6);
        AwtoNetCopy(pucP + 23, s_pucAwtoNetIp, 4);
        pucP[27] = 1;                           // protocol version
        AwtoNetSend(28);
        return;
    }
    if((s_pucAwtoNetIp[0] | s_pucAwtoNetIp[1] | s_pucAwtoNetIp[2] | s_pucAwtoNetIp[3]) == 0)
    {
        return;
    }
    if(usT == 0x0806)                           // ARP request for our IP -> reply
    {
        if((s_usAwtoNetLen < 42) || (pucP[20] != 0) || (pucP[21] != 1) || (AwtoNetEq(pucP + 38, s_pucAwtoNetIp, 4) == _FALSE))
        {
            return;
        }
        pucP[21] = 2;
        AwtoNetCopy(pucP + 32, pucP + 22, 10);  // target = sender (MAC + IP)
        AwtoNetCopy(pucP + 22, s_pucAwtoNetMac, 6);
        AwtoNetCopy(pucP + 28, s_pucAwtoNetIp, 4);
        AwtoNetCopy(s_pucAwtoNetPeer, pucP + 32, 6);
        AwtoNetEthTo(s_pucAwtoNetPeer, 0x0806);
        AwtoNetSend(42);
        return;
    }
    if((usT != 0x0800) || (s_usAwtoNetLen < 34) || (pucIp[0] != 0x45) || (AwtoNetSum(pucIp, 20) != 0) ||
       (AwtoNetEq(pucIp + 16, s_pucAwtoNetIp, 4) == _FALSE))
    {
        return;                                 // IPv4 without options, to us, header checksum good
    }
    usT = ((WORD)pucIp[2] << 8) | pucIp[3];
    if((usT < 28) || ((14 + usT) > s_usAwtoNetLen) || ((pucIp[6] & 0x3F) != 0) || (pucIp[7] != 0))
    {
        return;                                 // truncated, or a fragment
    }
    AwtoNetCopy(s_pucAwtoNetPeer, pucP + 6, 6);
    AwtoNetCopy(s_pucAwtoNetPeer + 6, pucIp + 12, 4);
    if(pucIp[9] == 1)                           // ICMP echo request -> reply in place
    {
        if(pucIp[20] != 8)
        {
            return;
        }
        pucIp[20] = 0;
        usS = (((WORD)pucIp[22] << 8) | pucIp[23]);
        usS += 0x0800;                          // type 8 -> 0: incremental checksum (RFC 1624)
        if(usS < 0x0800)
        {
            usS++;
        }
        pucIp[22] = usS >> 8;
        pucIp[23] = usS;
        AwtoNetEthTo(s_pucAwtoNetPeer, 0x0800);
        AwtoNetCopy(pucIp + 16, s_pucAwtoNetPeer + 6, 4);
        AwtoNetCopy(pucIp + 12, s_pucAwtoNetIp, 4);
        pucIp[8] = 64;
        pucIp[10] = 0;
        pucIp[11] = 0;
        usS = AwtoNetSum(pucIp, 20);
        pucIp[10] = usS >> 8;
        pucIp[11] = usS;
        AwtoNetSend(14 + usT);
        return;
    }
    if(pucIp[9] != 17)
    {
        return;
    }
    usS = ((WORD)pucIp[24] << 8) | pucIp[25];   // UDP length
    if((usS < 8) || (usS > (usT - 20)))
    {
        return;
    }
    s_pucAwtoNetPeer[10] = pucIp[20];
    s_pucAwtoNetPeer[11] = pucIp[21];
    usT = ((WORD)pucIp[22] << 8) | pucIp[23];   // destination port
    usS -= 8;
    if(usT == 7)                                // echo: payload stays in place (offset 42)
    {
        AwtoNetUdpTo(s_pucAwtoNetPeer, usS);
        pucIp[20] = 0;                          // source port 7, not the service port
        pucIp[21] = 7;
        return;
    }
    if(usT != AWTO_NET_PORT)
    {
        return;
    }
    if(usS > AWTO_NET_Q)
    {
        usS = AWTO_NET_Q;
    }
    AwtoNetCopy(s_pucAwtoNetQ, pucIp + 28, (BYTE)usS);
    usS = AwtoNetService((BYTE)usS);
    if(usS != 0)
    {
        AwtoNetUdpTo(s_pucAwtoNetPeer, usS);
    }
}

void AwtoNetPoll(void)                          // AWTO_NET_POLL(): only after a host exchange raised g_ucAwtoNetRun
{
    BYTE ucT;
    BYTE ucH;
    BYTE ucV;

    g_ucAwtoNetRun = 0;
    if(g_stAwtoNet.ucReset != 0)                // transports take no data and no ack while this is set
    {
        g_stAwtoNet.ucRxTail = g_stAwtoNet.ucRxHead;
        g_stAwtoNet.ucTxHead = g_stAwtoNet.ucTxTail;
        s_usAwtoNetLen = 0;
        s_ucAwtoNetEsc = 0;
        s_ucAwtoNetTx = 0;
        g_stAwtoNet.ucReset = 0;
        return;
    }
    ucT = g_stAwtoNet.ucRxTail;
    ucH = g_stAwtoNet.ucRxHead;
    if((g_stAwtoNet.ucCtl & AWTO_NET_CTL_ECHO) != 0)        // raw loopback: RX bytes straight back
    {
        ucV = g_stAwtoNet.ucTxHead;
        while((ucT != ucH) && ((BYTE)(ucV - g_stAwtoNet.ucTxTail) < AWTO_NET_RING))
        {
            g_stAwtoNet.pucTx[ucV & AWTO_NET_MASK] = g_stAwtoNet.pucRx[ucT & AWTO_NET_MASK];
            ucV++;
            ucT++;
        }
        g_stAwtoNet.ucTxHead = ucV;
        g_stAwtoNet.ucRxTail = ucT;
        return;
    }
    if(s_ucAwtoNetTx != 0)
    {
        AwtoNetTxPush();
        if(s_ucAwtoNetTx != 0)
        {
            return;                             // frame buffer busy until the reply is out
        }
    }
    while(ucT != ucH)
    {
        ucV = g_stAwtoNet.pucRx[ucT & AWTO_NET_MASK];
        ucT++;
        if(ucV == AWTO_NET_END)
        {
            if((s_usAwtoNetLen != 0) && (s_ucAwtoNetEsc != 2))
            {
                g_stAwtoNet.ucRxTail = ucT;
                AwtoNetFrame();
                if(s_ucAwtoNetTx == 0)
                {
                    s_usAwtoNetLen = 0;
                }
                s_ucAwtoNetEsc = 0;
                AwtoNetTxPush();
                g_ucAwtoNetRun = 1;             // one frame per call: the rest on the next pass
                return;
            }
            s_usAwtoNetLen = 0;
            s_ucAwtoNetEsc = 0;
        }
        else if(s_ucAwtoNetEsc == 2)
        {
            continue;
        }
        else if(ucV == AWTO_NET_ESC)
        {
            s_ucAwtoNetEsc = 1;
        }
        else
        {
            if(s_ucAwtoNetEsc == 1)
            {
                ucV = (ucV == AWTO_NET_ESC_END) ? AWTO_NET_END : (ucV == AWTO_NET_ESC_ESC) ? AWTO_NET_ESC : ucV;
                s_ucAwtoNetEsc = 0;
            }
            if(s_usAwtoNetLen < AWTO_NET_BUF)
            {
                s_pucAwtoNetBuf[s_usAwtoNetLen++] = ucV;
            }
            else
            {
                s_ucAwtoNetEsc = 2;
            }
        }
    }
    g_stAwtoNet.ucRxTail = ucT;
#if(_DEBUG_MESSAGE_SUPPORT == _ON)
    if((s_ucAwtoNetSubOn != 0) && (s_usAwtoNetLen == 0) && (s_usAwtoNetMsgSeq != g_usAwtoMsgSeq))
    {
        s_pucAwtoNetBuf[42] = 0x05;             // push: 05 00 00 lost seqH seqL n entries
        s_pucAwtoNetBuf[43] = 0;
        s_pucAwtoNetBuf[44] = 0;
        AwtoNetUdpTo(s_pucAwtoNetSub, 3 + AwtoNetMsgPut(s_pucAwtoNetBuf + 45, s_usAwtoNetMsgSeq));
        AwtoNetTxPush();
    }
#endif
}
#endif
