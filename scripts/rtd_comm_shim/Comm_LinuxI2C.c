/* Comm back-end for Realtek RTDCustomerTool: forwards I2C to a native bridge over TCP.
 * Bridge: scripts/rtd_i2c_bridge.py (port RTD_BRIDGE_PORT, default 17420, 127.0.0.1).
 * Interface shape follows wbcbz7/RTDTool-Comm-CH341A; unimplemented calls return 0x2201.
 * Build (i686 mingw): scripts/rtd_comm_shim/build.py -> Comm_LinuxI2C.dll
 */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define EXP __declspec(dllexport)
#define ERR 0x2201

static SOCKET sock = INVALID_SOCKET;
static DWORD i2c_khz = 100;
static FILE *lg;

static void tr(const char *fmt, ...) {
    va_list ap;
    if (!lg) { const char *p = getenv("RTD_SHIM_LOG"); lg = fopen(p ? p : "Comm_LinuxI2C.log", "a"); }
    if (!lg) return;
    va_start(ap, fmt); vfprintf(lg, fmt, ap); va_end(ap); fputc('\n', lg); fflush(lg);
}

static int conn(void) {
    WSADATA w; struct sockaddr_in a; const char *p;
    if (sock != INVALID_SOCKET) return 1;
    WSAStartup(MAKEWORD(2, 2), &w);
    sock = socket(AF_INET, SOCK_STREAM, 0);
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    p = getenv("RTD_BRIDGE_PORT");
    a.sin_port = htons(p ? (u_short)atoi(p) : 17420);
    a.sin_addr.s_addr = inet_addr("127.0.0.1");
    if (connect(sock, (struct sockaddr *)&a, sizeof a) != 0) {
        tr("connect failed %d", WSAGetLastError()); closesocket(sock); sock = INVALID_SOCKET; return 0;
    }
    return 1;
}

static int rx(void *b, int n) {
    char *c = b;
    while (n > 0) { int r = recv(sock, c, n, 0); if (r <= 0) return 0; c += r; n -= r; }
    return 1;
}

/* op 1 read / 2 write. Returns 0 ok, ERR on failure. */
static DWORD xfer(uint8_t op, uint8_t dev8, uint8_t sub, uint16_t nb, const BYTE *data, uint16_t dl, BYTE *out) {
    uint8_t h[7], r[3]; uint16_t n;
    if (!conn()) return ERR;
    h[0] = op; h[1] = dev8; h[2] = sub; h[3] = nb & 255; h[4] = nb >> 8; h[5] = dl & 255; h[6] = dl >> 8;
    if (send(sock, (char *)h, 7, 0) != 7) return ERR;
    if (dl && send(sock, (const char *)data, dl, 0) != dl) return ERR;
    if (!rx(r, 3)) return ERR;
    n = r[1] | (r[2] << 8);
    if (n) { BYTE tmp[4096]; if (n > sizeof tmp || !rx(tmp, n)) return ERR; if (out) memcpy(out, tmp, n < nb ? n : nb); }
    tr("%s dev=0x%02x sub=0x%02x n=%u -> %s", op == 1 ? "R" : "W", dev8, sub, nb, r[0] ? "FAIL" : "ok");
    return r[0] ? ERR : 0;
}

EXP DWORD I2CRead(DWORD dev, DWORD sub, DWORD bytes, BYTE *ptr) {
    DWORD done = 0;
    if (!bytes || !ptr) return 0x2202;           /* stock GFXI2C: bad arg */
    while (done < bytes) {                       /* bridge reply buffer is 4096 */
        DWORD c = bytes - done > 1024 ? 1024 : bytes - done;
        if (xfer(1, dev & 0xFE, sub & 0xFF, (uint16_t)c, NULL, 0, ptr + done)) return ERR;
        done += c;
    }
    return 0;
}
EXP DWORD I2CWrite(DWORD dev, DWORD sub, DWORD bytes, BYTE *ptr) {
    if (bytes > 128) return ERR;
    return xfer(2, dev & 0xFE, sub & 0xFF, (uint16_t)bytes, ptr, (uint16_t)bytes, NULL);
}
EXP DWORD I2CWriteByte(DWORD dev, DWORD sub, DWORD v) {
    BYTE b = v & 0xFF;
    return xfer(2, dev & 0xFE, sub & 0xFF, 1, &b, 1, NULL);
}

/* 5 = GFXI2C (graphics-card DDC): RTDTool switch(GetCommID()) handles 1-6 only, ISP plugin 1-10; stock
 * Comm_GFXI2C.dll must be moved out of Comm\ (docs/rtdtool-headless-feasibility.md). */
EXP DWORD GetCommID(void) { tr("GetCommID"); return 5; }
EXP DWORD GetCommName(wchar_t *s, DWORD max) { tr("GetCommName max=%lu", max); wcsncpy(s, L"LinuxI2C", max); return 0; }
EXP DWORD GetDeviceCount(void) { tr("GetDeviceCount"); return 0; }
EXP DWORD GetDeviceHandler(void) { tr("GetDeviceHandler"); return 0; }
EXP DWORD GetI2CPageLength(void) { tr("GetI2CPageLength"); return 0x80; }
EXP DWORD GetI2CSpeed(void) { tr("GetI2CSpeed -> %lu", i2c_khz); return i2c_khz; }
EXP DWORD SetI2CSpeed(DWORD k) { tr("SetI2CSpeed %lu", k); i2c_khz = k; return 0; }
EXP DWORD GetNativePageLength(void) { tr("GetNativePageLength"); return 0; }
EXP DWORD GetSMBUSDataType(void) { tr("GetSMBUSDataType"); return 0; }
EXP ULONGLONG GetWaitingMode(void) { tr("GetWaitingMode"); return 0; }
EXP DWORD InitialDev(void) { tr("InitialDev"); return 0; }
EXP DWORD ReleaseDev(void) { tr("ReleaseDev"); return 0; }   /* stock GFXI2C always 0 */
EXP DWORD SetCmdLine(void) { tr("SetCmdLine"); return 0; }
EXP DWORD SetSettingFilePath(void) { tr("SetSettingFilePath"); return 0; }
EXP DWORD AdjustOption(void) { MessageBoxA(NULL, "Comm_LinuxI2C: forwards I2C to 127.0.0.1 bridge (RTD_BRIDGE_PORT)", "Comm_LinuxI2C", MB_OK); return 0; }
/* Unimplemented: logged + error (a silent 0 was a false success, hid which call precedes RTDTool's exit) */
#define STUB(n) EXP DWORD n(void) { tr("stub " #n); return ERR; }
STUB(I2C2SubRead) STUB(I2C2SubWrite) STUB(I2CCurrentRead) STUB(I2CReadSegment) STUB(I2CWordRead)
STUB(I2CWordWrite) STUB(I2CWriteSegment)
STUB(BankErase) STUB(DebugMessageEnd) STUB(DebugMessageEventFinish) STUB(DebugMessageEventStart)
STUB(DebugMessageGetString) STUB(DebugMessageGetValue) STUB(DebugMessageStart) STUB(GetFTDIGetAckStatus)
STUB(GetUsbDevicePath) STUB(IspEnable) STUB(ReadFlashData) STUB(RemoveDevice) STUB(ResetFirmware)
STUB(SectorErase) STUB(SelectUsbByDevicePath) STUB(SelectUsbByIndex) STUB(SetAuxMode) STUB(SetFTDIGetAck)
STUB(SetSMBUSDataType) STUB(SetWaitingMode) STUB(TypeCUsbReadReg) STUB(TypeCUsbReadSysDevice)
STUB(TypeCUsbWriteReg) STUB(TypeCUsbWriteSysDevice) STUB(WriteFlashData) STUB(NativeRead) STUB(NativeWrite)

BOOL APIENTRY DllMain(HMODULE h, DWORD why, LPVOID r) {
    if (why == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(h);
    return TRUE;
}
