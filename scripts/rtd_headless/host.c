/* Headless host for Realtek RTDCustomerTool plugins (DRAFT, never run). Static findings: docs/rtdtool-headless-feasibility.md
 * Build: i686-w64-mingw32-gcc -O2 -Wall -o rtd_host.exe host.c -luser32 -lws2_32 -static-libgcc   (see README.md)
 * Place rtd_host.exe in the tool root (next to Comm.dll, PlugIn\, Comm\Comm_LinuxI2C.dll): plugins resolve
 * Comm.dll, ISPToolSetting.ini, VersionResult.txt etc. from the EXE's directory [guess, GetModuleFileNameW(NULL)].
 *
 *   rtd_host version                 ISP plugin: InitialComm + ReadVersionExport -> VersionResult.txt   (read path)
 *   rtd_host rdreg <hex>             Comm.dll ReadRegEx(reg,&byte)           via CRsComm object
 *   rtd_host rdmcu <hex>             Comm.dll ReadMcuReg(addr,&byte)         [guess signature]
 *   rtd_host copybank | combine      ReadCopyBankVersionExport / SaveCombineVersionExport -> HPVersion.txt
 *   rtd_host plugin <name> [act...]  GUI plugin in a hidden dialog; act = click:<id> | msg:<hex>,<w>,<l> | wait:<ms> | dump
 * copybank/combine toggle the "factory mode" register: need RTD_HOST_ALLOW_WRITE=1.
 * Env: RTD_HOST_COMMID=<1..10> -> ISPToolSetting.ini [EXE] CommID (InitialComm only selects ids 1..10);
 *      RTD_HOST_DIRECT=1 -> I2C primitives go to the TCP bridge (scripts/rtd_i2c_bridge.py) from this process.
 */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

/* CDECL comes from windef.h (empty = default cdecl on i686 mingw) */
static wchar_t ROOT[MAX_PATH];

/* ---- CRsComm object layout: slot n = byte offset 4n. [0]=vtable, [1]=Comm.dll HMODULE, [2..0x7e]=Comm.dll exports (cdecl).
 * Order copied from PlugIn_ISP FUN_10001000 (GetProcAddress chain). Total 0x1fc bytes; we allocate 0x400 zeroed. */
#define OBJ_BYTES 0x400
static const char *const COMM_FN[0x7f] = {
    [0x02] = "GetI2CPageLength", [0x03] = "GetNativePageLength", [0x04] = "I2CWrite", [0x05] = "I2CRead",
    [0x06] = "I2CWriteByte", [0x07] = "I2CCurrentRead", [0x08] = "I2CWordWrite", [0x09] = "I2C2SubWrite",
    [0x0a] = "I2CWordRead", [0x0b] = "I2C2SubRead", [0x0c] = "I2CWriteEx", [0x0d] = "I2CReadEx",
    [0x0e] = "I2CCurrentReadEx", [0x0f] = "I2CWordWriteEx", [0x10] = "I2C2SubWriteEx", [0x11] = "I2CWordReadEx",
    [0x12] = "I2C2SubReadEx", [0x13] = "AdjustOption", [0x14] = "SetI2CSpeed", [0x15] = "GetI2CSpeed",
    [0x16] = "SetAuxMode", [0x17] = "SetWaitingMode", [0x18] = "GetWaitingMode", [0x19] = "Initiallize",
    [0x1a] = "GetCommCount", [0x1b] = "GetCommID", [0x1c] = "GetCommName", [0x1d] = "GetCommFile",
    [0x1e] = "SetCommByIndex", [0x1f] = "SetCommByID", [0x20] = "SetDebugSlave", [0x21] = "SetIspSlave",
    [0x22] = "SetIspContinuousSlave", [0x23] = "GetDebugSlave", [0x24] = "GetIspSlave",
    [0x25] = "GetIspContinuousSlave", [0x26] = "SetDebugMode", [0x27] = "GetDebugMode", [0x28] = "ReadReg",
    [0x29] = "WriteReg", [0x2a] = "ReadRegs", [0x2b] = "WriteRegs", [0x2c] = "WriteRegBit",
    [0x2d] = "WritePortRegBit", [0x2e] = "ReadRegEx", [0x2f] = "WriteRegEx", [0x30] = "ReadRegsEx",
    [0x31] = "WriteRegsEx", [0x32] = "WriteRegBitEx", [0x33] = "WritePortRegBitEx", [0x34] = "ReadSysDevice",
    [0x35] = "WriteSysDevice", [0x36] = "ReadWordSysDevice", [0x37] = "WriteWordSysDevice",
    [0x38] = "ScalerStop", [0x39] = "ScalerRun", [0x3a] = "WriteMcuReg", [0x3b] = "WriteMcuRegs",
    [0x3c] = "ReadMcuReg", [0x3d] = "WriteMcuRegBit", [0x3e] = "ReadMcuRegs", [0x3f] = "WriteContinuousMcuReg",
    [0x40] = "ReadContinuousMcuReg", [0x41] = "ReleaseDev", [0x42] = "NativeWrite", [0x43] = "NativeRead",
    [0x44] = "SetSettingFilePath", [0x45] = "GetDeviceHandler", [0x46] = "ResetFirmware", [0x47] = "EnterIspMode",
    [0x48] = "GetSMBUSDataType", [0x49] = "SetSMBUSDataType", [0x4a] = "GetDeviceCount", [0x4b] = "RemoveDevice",
    [0x4c] = "AutoDetectSlaveAddr", [0x4d] = "DDCCIWrite", [0x4e] = "DDCCIRead", [0x4f] = "SetFTDIGetAck",
    [0x50] = "GetFTDIGetAckStatus", [0x51] = "I2CMasterInitial", [0x52] = "I2CMasterCurrentRead",
    [0x53] = "I2CMasterCurrentReadEx", [0x54] = "I2CMasterRead", [0x55] = "I2CMasterReadEx",
    [0x56] = "I2CMasterWordRead", [0x57] = "I2CMasterWordReadEx", [0x58] = "I2CMasterCurrentWrite",
    [0x59] = "I2CMasterCurrentWriteEx", [0x5a] = "I2CMasterWrite", [0x5b] = "I2CMasterWriteByte",
    [0x5c] = "I2CMasterWriteEx", [0x5d] = "I2CMasterWordWrite", [0x5e] = "I2CMasterWordWriteEx",
    [0x5f] = "GetUsbDevicePath", [0x60] = "SelectUsbByDevicePath", [0x61] = "SelectUsbByIndex",
    [0x62] = "WriteFlashData", [0x63] = "ReadFlashData", [0x64] = "SectorErase", [0x65] = "BankErase",
    [0x66] = "DebugMessageEventStart", [0x67] = "DebugMessageEventFinish", [0x68] = "DebugMessageStart",
    [0x69] = "DebugMessageEnd", [0x6a] = "DebugMessageGetValue", [0x6b] = "DebugMessageGetString",
    [0x6c] = "SetCmdLine", [0x6d] = "GetSpecialCommType", [0x6e] = "SetSpecialCommType",
    [0x6f] = "Read32BitRegEx", [0x70] = "Write32BitRegEx", [0x71] = "Read32BitRegsEx",
    [0x72] = "Write32BitRegsEx", [0x73] = "ReadDDRRegEx", [0x74] = "WriteDDRRegEx", [0x75] = "ReadDDRRegsEx",
    [0x76] = "WriteDDRRegsEx", [0x77] = "ReadPWM2SPIReg", [0x78] = "WritePWM2SPIReg", [0x79] = "ReadPWM2SPIDev",
    [0x7a] = "WritePWM2SPIDev", [0x7b] = "I2CWriteSegment", [0x7c] = "I2CWriteSegmentEx",
    [0x7d] = "I2CReadSegment", [0x7e] = "I2CReadSegmentEx",
};

/* CRsComm vtable: 9 thiscall thunks; each forwards to one member, returns 6 when the member is NULL [fw].
 * vt0 ReadReg +0xA0 | vt1 WriteReg +0xA4 | vt2 ReadRegEx +0xB8 | vt3 WriteRegEx +0xBC | vt4 ScalerStop +0xE0
 * vt5 ScalerRun +0xE4 | vt6 EnterIspMode +0x11C | vt7 AutoDetectSlaveAddr +0x130 | vt8 DDCCIWrite +0x134 */
#define MEM(self, off) (((void **)(self))[(off) / 4])
#define TC __attribute__((thiscall))
static int TC vt0(void *s, unsigned a, unsigned b) { int (CDECL *f)(unsigned, unsigned) = MEM(s, 0xA0); return f ? f(a, b) : 6; }
static int TC vt1(void *s, unsigned a, unsigned b) { int (CDECL *f)(unsigned, unsigned) = MEM(s, 0xA4); return f ? f(a, b) : 6; }
static int TC vt2(void *s, unsigned a, unsigned b) { int (CDECL *f)(unsigned, unsigned) = MEM(s, 0xB8); return f ? f(a, b) : 6; }
static int TC vt3(void *s, unsigned a, unsigned b) { int (CDECL *f)(unsigned, unsigned) = MEM(s, 0xBC); return f ? f(a, b) : 6; }
static int TC vt4(void *s) { int (CDECL *f)(void) = MEM(s, 0xE0); return f ? f() : 6; }
static int TC vt5(void *s) { int (CDECL *f)(void) = MEM(s, 0xE4); return f ? f() : 6; }
static int TC vt6(void *s, unsigned a) { int (CDECL *f)(unsigned) = MEM(s, 0x11C); return f ? f(a) : 6; }
static int TC vt7(void *s) { int (CDECL *f)(void) = MEM(s, 0x130); return f ? f() : 6; }
static int TC vt8(void *s, unsigned a, unsigned b, unsigned c, unsigned d) { int (CDECL *f)(unsigned, unsigned, unsigned, unsigned) = MEM(s, 0x134); return f ? f(a, b, c, d) : 6; }
static void *VTABLE[9] = { vt0, vt1, vt2, vt3, vt4, vt5, vt6, vt7, vt8 };

/* ---- optional: I2C primitives served by this process over the bridge (same wire format as Comm_LinuxI2C.c) ---- */
static SOCKET bsock = INVALID_SOCKET;
static int bridge_xfer(uint8_t op, uint8_t dev8, uint8_t sub, uint16_t nb, const BYTE *data, uint16_t dl, BYTE *out) {
    uint8_t h[7], r[3]; uint16_t n; char *c; int left;
    if (bsock == INVALID_SOCKET) {
        WSADATA w; struct sockaddr_in a; const char *p = getenv("RTD_BRIDGE_PORT");
        WSAStartup(MAKEWORD(2, 2), &w);
        bsock = socket(AF_INET, SOCK_STREAM, 0);
        memset(&a, 0, sizeof a); a.sin_family = AF_INET; a.sin_port = htons(p ? (u_short)atoi(p) : 17420);
        a.sin_addr.s_addr = inet_addr("127.0.0.1");
        if (connect(bsock, (struct sockaddr *)&a, sizeof a)) { closesocket(bsock); bsock = INVALID_SOCKET; return 0x2201; }
    }
    h[0] = op; h[1] = dev8; h[2] = sub; h[3] = nb & 255; h[4] = nb >> 8; h[5] = dl & 255; h[6] = dl >> 8;
    if (send(bsock, (char *)h, 7, 0) != 7) return 0x2201;
    if (dl && send(bsock, (const char *)data, dl, 0) != dl) return 0x2201;
    for (c = (char *)r, left = 3; left > 0;) { int k = recv(bsock, c, left, 0); if (k <= 0) return 0x2201; c += k; left -= k; }
    n = r[1] | (r[2] << 8);
    if (n) { BYTE tmp[4096]; if (n > sizeof tmp) return 0x2201;
        for (c = (char *)tmp, left = n; left > 0;) { int k = recv(bsock, c, left, 0); if (k <= 0) return 0x2201; c += k; left -= k; }
        if (out) memcpy(out, tmp, n < nb ? n : nb); }
    return r[0] ? 0x2201 : 0;
}
static DWORD CDECL d_I2CRead(DWORD dev, DWORD sub, DWORD n, BYTE *p) { DWORD d = 0; while (d < n) { DWORD c = n - d > 1024 ? 1024 : n - d; if (bridge_xfer(1, dev & 0xFE, sub & 0xFF, (uint16_t)c, NULL, 0, p + d)) return 0x2201; d += c; } return 0; }
static DWORD CDECL d_I2CWrite(DWORD dev, DWORD sub, DWORD n, BYTE *p) { return n > 128 ? 0x2201 : bridge_xfer(2, dev & 0xFE, sub & 0xFF, (uint16_t)n, p, (uint16_t)n, NULL); }
static DWORD CDECL d_I2CWriteByte(DWORD dev, DWORD sub, DWORD v) { BYTE b = v & 255; return bridge_xfer(2, dev & 0xFE, sub & 0xFF, 1, &b, 1, NULL); }
static DWORD CDECL d_PageLen(void) { return 0x80; }

/* ---- build the object the plugins expect ---- */
static void **comm_build(void) {
    wchar_t path[MAX_PATH]; HMODULE m; void **o; int i;
    swprintf(path, MAX_PATH, L"%ls\\Comm.dll", ROOT);
    m = LoadLibraryW(path);
    if (!m) { fprintf(stderr, "LoadLibrary Comm.dll failed: %lu\n", GetLastError()); return NULL; }
    o = calloc(OBJ_BYTES / 4, 4);
    o[0] = VTABLE; o[1] = m;
    for (i = 2; i <= 0x7e; i++) {
        o[i] = (void *)GetProcAddress(m, COMM_FN[i]);
        if (!o[i]) fprintf(stderr, "Comm.dll lacks %s (slot 0x%02x, off 0x%03x)\n", COMM_FN[i], i, i * 4);
    }
    if (getenv("RTD_HOST_DIRECT")) {
        o[0x02] = d_PageLen; o[0x03] = d_PageLen; o[0x04] = d_I2CWrite; o[0x05] = d_I2CRead; o[0x06] = d_I2CWriteByte;
    }
    return o;
}

/* Initiallize() enumerates Comm\Comm_*.dll; SetCommByID picks by the DLL's GetCommID (shim: pick 7/9/10, see doc). */
static int comm_start(void **o) {
    int (CDECL *init)(void) = o[0x19]; int (CDECL *setid)(int) = o[0x1f]; const char *id = getenv("RTD_HOST_COMMID");
    if (init) init();
    if (id && setid) setid(atoi(id));
    return 0;
}

static LONG WINAPI crash(EXCEPTION_POINTERS *e) {
    fprintf(stderr, "unhandled exception 0x%08lx at %p (plugin threw; MFC AtlThrow on missing Comm.dll/ini?)\n",
            e->ExceptionRecord->ExceptionCode, e->ExceptionRecord->ExceptionAddress);
    ExitProcess(3);
    return EXCEPTION_EXECUTE_HANDLER;
}

static int need_write(void) {
    const char *w = getenv("RTD_HOST_ALLOW_WRITE");
    if (w && w[0] == '1') return 1;
    fprintf(stderr, "refused: this call changes device state; set RTD_HOST_ALLOW_WRITE=1\n");
    return 0;
}

static void cat_file(const wchar_t *name) {
    wchar_t p[MAX_PATH]; FILE *f; char buf[512]; size_t n;
    swprintf(p, MAX_PATH, L"%ls\\%ls", ROOT, name);
    f = _wfopen(p, L"rb");
    if (!f) { fprintf(stderr, "%ls not written\n", name); return; }
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) fwrite(buf, 1, n, stdout);
    fclose(f);
}

/* ---- ISP plugin: self-contained engine, has its own CRsComm (loads Comm.dll itself) ---- */
static int cmd_isp(const char *what) {
    wchar_t p[MAX_PATH], ini[MAX_PATH];
    HMODULE h; void (CDECL *initcomm)(void); void (CDECL *fn)(void); const char *id = getenv("RTD_HOST_COMMID");
    const wchar_t *outfile = L"VersionResult.txt";
    swprintf(p, MAX_PATH, L"%ls\\PlugIn\\PlugIn_ISP.dll", ROOT);
    h = LoadLibraryW(p);
    if (!h) { fprintf(stderr, "LoadLibrary PlugIn_ISP.dll failed: %lu\n", GetLastError()); return 1; }
    initcomm = (void *)GetProcAddress(h, "InitialComm");
    if (!strcmp(what, "version")) fn = (void *)GetProcAddress(h, "ReadVersionExport");
    else if (!strcmp(what, "copybank")) { fn = (void *)GetProcAddress(h, "ReadCopyBankVersionExport"); outfile = L"HPVersion.txt"; }
    else { fn = (void *)GetProcAddress(h, "SaveCombineVersionExport"); outfile = L"HPVersion.txt"; }
    if (!initcomm || !fn) { fprintf(stderr, "export missing\n"); return 1; }
    if (strcmp(what, "version") && !need_write()) return 2;
    if (id) {   /* InitialComm reads [EXE] CommID from here and only honours 1..10 */
        wchar_t v[16];
        swprintf(ini, MAX_PATH, L"%ls\\ISPToolSetting.ini", ROOT);
        swprintf(v, 16, L"%d", atoi(id));
        WritePrivateProfileStringW(L"EXE", L"CommID", v, ini);
    }
    swprintf(p, MAX_PATH, L"%ls\\%ls", ROOT, outfile);
    DeleteFileW(p);                       /* so a stale file cannot pass as a result */
    initcomm();                           /* Initiallize(); SetCommByID(ini); SetSettingFilePath(ini) */
    fn();                                 /* writes outfile; returns void, no status */
    cat_file(outfile);
    return 0;
}

/* ---- direct Comm register reads through our object (bypasses every plugin) ---- */
static int cmd_rd(const char *kind, const char *hex) {
    void **o = comm_build(); unsigned a = (unsigned)strtoul(hex, NULL, 16); unsigned char v = 0xEE; int rc;
    int (CDECL *rd)(unsigned, unsigned char *);
    if (!o) return 1;
    comm_start(o);
    rd = !strcmp(kind, "rdmcu") ? o[0x3c] : o[0x2e];
    if (!rd) { fprintf(stderr, "member missing\n"); return 1; }
    rc = rd(a, &v);
    printf("%s 0x%02x -> rc=%d val=0x%02x\n", kind, a, rc, v);
    return rc;
}

/* ---- GUI plugin driven headless: hidden parent window, Initinal builds the (hidden) dialog [fw] ---- */
static void pump(DWORD max_ms) {          /* drain posted messages; bound = caller's wait, handlers do a few ms of I2C each */
    DWORD end = GetTickCount() + max_ms; MSG m;
    while (GetTickCount() < end) {
        while (PeekMessageW(&m, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageW(&m); }
        MsgWaitForMultipleObjects(0, NULL, FALSE, 10, QS_ALLINPUT);
    }
}
static BOOL CALLBACK dump_kid(HWND h, LPARAM d) {
    wchar_t cls[64] = L"", txt[256] = L"";
    GetClassNameW(h, cls, 64);
    SendMessageTimeoutW(h, WM_GETTEXT, 256, (LPARAM)txt, SMTO_ABORTIFHUNG, 500, NULL);   /* 500 ms: control repaint-class call */
    if (txt[0]) printf("id=0x%04x cls=%ls text=\"%ls\"\n", GetDlgCtrlID(h), cls, txt);
    (void)d; return TRUE;
}
static int cmd_plugin(const char *name, int argc, char **argv) {
    wchar_t p[MAX_PATH], wname[64], setting[MAX_PATH], scaler[MAX_PATH]; HMODULE h; HWND parent, pi; void **o; int i;
    void (CDECL *Initinal)(HWND), (CDECL *SetComm)(void *), (CDECL *SetSetting)(const wchar_t *), (CDECL *SetScaler)(const wchar_t *);
    HWND (CDECL *GetHWnd)(void); void (CDECL *GetName)(wchar_t *, unsigned short);
    swprintf(p, MAX_PATH, L"%ls\\PlugIn\\%hs.dll", ROOT, name);
    h = LoadLibraryW(p);
    if (!h) { fprintf(stderr, "LoadLibrary %s failed: %lu\n", name, GetLastError()); return 1; }
    Initinal = (void *)GetProcAddress(h, "Initinal"); SetComm = (void *)GetProcAddress(h, "SetCommInterface");
    SetSetting = (void *)GetProcAddress(h, "SetSettingFilePath"); SetScaler = (void *)GetProcAddress(h, "SetScalerFilePath");
    GetHWnd = (void *)GetProcAddress(h, "GetPIHWnd"); GetName = (void *)GetProcAddress(h, "GetPIName");
    if (!Initinal || !SetComm || !SetSetting || !SetScaler || !GetHWnd) { fprintf(stderr, "not a plugin\n"); return 1; }
    o = comm_build(); if (!o) return 1;
    comm_start(o);
    swprintf(setting, MAX_PATH, L"%ls\\NewRTDCustomerToolSetting.ini", ROOT);          /* [str] file RTDTool keeps its [RTDTool] keys in */
    swprintf(scaler, MAX_PATH, L"%ls\\RTDScaler", ROOT);                              /* [?] RTDTool passes a per-scaler file; set via env */
    if (getenv("RTD_HOST_SCALER_FILE")) swprintf(scaler, MAX_PATH, L"%hs", getenv("RTD_HOST_SCALER_FILE"));
    SetSetting(setting); SetScaler(scaler); SetComm(o);
    parent = CreateWindowExW(0, L"STATIC", L"rtd_host", WS_POPUP, 0, 0, 1, 1, NULL, NULL, GetModuleHandleW(NULL), NULL);   /* never shown */
    Initinal(parent);                                                                 /* OnInitDialog runs inside this call [fw] */
    pi = GetHWnd();
    if (GetName) { GetName(wname, 64); printf("plugin \"%ls\" hwnd=%p\n", wname, (void *)pi); }
    if (!pi) { fprintf(stderr, "plugin created no window\n"); return 1; }
    for (i = 0; i < argc; i++) {
        unsigned long a, b, c;
        if (!strncmp(argv[i], "click:", 6)) { a = strtoul(argv[i] + 6, NULL, 0); PostMessageW(pi, WM_COMMAND, MAKEWPARAM(a, BN_CLICKED), (LPARAM)GetDlgItem(pi, (int)a)); }
        else if (!strncmp(argv[i], "msg:", 4)) { a = strtoul(argv[i] + 4, NULL, 16); b = c = 0; sscanf(argv[i] + 4, "%lx,%lx,%lx", &a, &b, &c); PostMessageW(pi, (UINT)a, b, c); }
        else if (!strncmp(argv[i], "wait:", 5)) pump((DWORD)atoi(argv[i] + 5));
        else if (!strcmp(argv[i], "dump")) EnumChildWindows(pi, dump_kid, 0);
    }
    return 0;
}

int main(int argc, char **argv) {
    wchar_t *s;
    SetUnhandledExceptionFilter(crash);
    GetModuleFileNameW(NULL, ROOT, MAX_PATH);
    s = wcsrchr(ROOT, L'\\'); if (s) *s = 0;
    SetDllDirectoryW(ROOT);
    if (argc < 2) { fprintf(stderr, "usage: rtd_host version|copybank|combine|rdreg <hex>|rdmcu <hex>|plugin <PlugIn_X> [click:<id>|msg:<m>,<w>,<l>|wait:<ms>|dump]...\n"); return 2; }
    if (!strcmp(argv[1], "version") || !strcmp(argv[1], "copybank") || !strcmp(argv[1], "combine")) return cmd_isp(argv[1]);
    if ((!strcmp(argv[1], "rdreg") || !strcmp(argv[1], "rdmcu")) && argc > 2) return cmd_rd(argv[1], argv[2]);
    if (!strcmp(argv[1], "plugin") && argc > 2) return cmd_plugin(argv[2], argc - 3, argv + 3);
    fprintf(stderr, "bad command\n");
    return 2;
}
