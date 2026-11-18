// CEC message layer (docs/cec.md): pure logic, no register access, compiles on the host (tests/test_cec_msg.py).
// Opcodes and operands: HDMI 1.4b CEC spec; Linux include/uapi/linux/cec.h as the public cross-check.
#ifndef CEC_MSG_H
#define CEC_MSG_H

#define CEC_LA_TV                   0x00    // a PC monitor is a TV (device type 0)
#define CEC_LA_BROADCAST            0x0F
#define CEC_DEST_UNKNOWN            0x10    // basic CEC block (gen type 0): no register tells the destination of a received frame
#define CEC_DEVTYPE_TV              0x00
#define CEC_VERSION_1_4             0x05
#define CEC_PA_TV                   0x0000  // a TV is the topology root, 0.0.0.0 (its inputs are 1.0.0.0 and 2.0.0.0 in the EDID)
#define CEC_VENDOR_ID               0xA770D0UL      // awto OUI as in the EDID port tag (scripts/make_edid.py AWTO_OUI): unregistered
#define CEC_OSD_NAME                "awto-mon"      // = the EDID monitor name; 14 characters at most
#define CEC_MAX_DB                  16

#define CEC_OP_FEATURE_ABORT        0x00
#define CEC_OP_IMAGE_VIEW_ON        0x04
#define CEC_OP_TEXT_VIEW_ON         0x0D
#define CEC_OP_STANDBY              0x36
#define CEC_OP_USER_CONTROL_PRESSED 0x44
#define CEC_OP_USER_CONTROL_RELEASED 0x45
#define CEC_OP_GIVE_OSD_NAME        0x46
#define CEC_OP_SET_OSD_NAME         0x47
#define CEC_OP_ROUTING_CHANGE       0x80
#define CEC_OP_ROUTING_INFORMATION  0x81
#define CEC_OP_ACTIVE_SOURCE        0x82
#define CEC_OP_GIVE_PHYSICAL_ADDR   0x83
#define CEC_OP_REPORT_PHYSICAL_ADDR 0x84
#define CEC_OP_REQUEST_ACTIVE_SRC   0x85
#define CEC_OP_SET_STREAM_PATH      0x86
#define CEC_OP_DEVICE_VENDOR_ID     0x87
#define CEC_OP_GIVE_VENDOR_ID       0x8C
#define CEC_OP_GIVE_POWER_STATUS    0x8F
#define CEC_OP_REPORT_POWER_STATUS  0x90
#define CEC_OP_INACTIVE_SOURCE      0x9D
#define CEC_OP_CEC_VERSION          0x9E
#define CEC_OP_GET_CEC_VERSION      0x9F
#define CEC_OP_ABORT                0xFF

#define CEC_ABORT_UNRECOGNIZED      0x00    // <Feature Abort> reason
#define CEC_ABORT_REFUSED           0x04

#define CEC_POWER_ON                0x00
#define CEC_POWER_STANDBY           0x01
#define CEC_POWER_TO_ON             0x02
#define CEC_POWER_TO_STANDBY        0x03

// Hooks: messages that would change user-visible behaviour. Logged only until the registry setting cec_ctl allows them.
#define CEC_HOOK_NONE               0
#define CEC_HOOK_STANDBY            1       // <Standby>
#define CEC_HOOK_WAKE               2       // <Image View On> / <Text View On>
#define CEC_HOOK_ACTIVE_SOURCE      3       // <Active Source> / <Set Stream Path> / <Routing Information> / <Routing Change>
#define CEC_HOOK_USER_CONTROL       4       // <User Control Pressed> / <Released>

typedef struct
{
    unsigned char ucDest;                   // initiator of the request
    unsigned char ucLen;                    // opcode + operands; 0 = no reply
    unsigned char pucDb[CEC_MAX_DB];
    unsigned char ucHook;                   // CEC_HOOK_*
} StCecReply;

// ucInit: initiator logical address; ucDest: 0..15 or CEC_DEST_UNKNOWN; pucDb / ucLen: opcode + operands (len 0 = polling message).
// usPhys: this device's physical address; ucPower: CEC_POWER_*. Returns pReply->ucLen.
unsigned char CecMsgRx(unsigned char ucInit, unsigned char ucDest, const unsigned char *pucDb, unsigned char ucLen,
                       unsigned short usPhys, unsigned char ucPower, StCecReply *pReply);

#endif
