/* Fake nvapi.dll (i386) for SmartControl under Wine: one GPU, one display, an emulated DDC/CI
 * responder at I2C 0x6E/0x6F with the 288E2 profile. Logs every I2C byte and unknown interface id.
 * Env: SC_PROFILE (profile), SC_DDC_LOG (log). Nothing leaves the process: no real I2C. */
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static FILE *g_log;
static CRITICAL_SECTION g_cs;
static char g_caps[2048];
static BYTE g_edid[256];
typedef struct { int present, type; DWORD cur, max; } Vcp;
static Vcp g_vcp[256];
static BYTE g_reply[64];
static int g_replylen;
static int g_edidoff;

static void lg(const char *fmt, ...)
{
    SYSTEMTIME t; va_list ap; char buf[900];
    if (!g_log) return;
    GetLocalTime(&t);
    va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    EnterCriticalSection(&g_cs);
    fprintf(g_log, "%04d-%02d-%02dT%02d:%02d:%02d.%03d nvapi tid=%lu %s\n", t.wYear, t.wMonth, t.wDay,
            t.wHour, t.wMinute, t.wSecond, t.wMilliseconds, GetCurrentThreadId(), buf);
    fflush(g_log);
    LeaveCriticalSection(&g_cs);
}

static void hex(char *o, const BYTE *p, int n)
{ int i; for (i = 0; i < n && i < 60; i++) sprintf(o + i * 3, "%02X ", p[i]); o[i * 3] = 0; }

static void load_profile(void)
{
    const char *p = getenv("SC_PROFILE"); FILE *f; char *ln = malloc(8192);
    if (!p || !(f = fopen(p, "r"))) { free(ln); return; }
    while (fgets(ln, 8192, f)) {
        unsigned c, t, cur, mx; size_t n = strlen(ln);
        while (n && (ln[n-1] == '\n' || ln[n-1] == '\r')) ln[--n] = 0;
        if (!strncmp(ln, "caps ", 5)) strncpy(g_caps, ln + 5, sizeof g_caps - 1);
        else if (!strncmp(ln, "edid ", 5)) { int i; for (i = 0; i < 256 && ln[5 + 2*i]; i++) { char h[3] = { ln[5+2*i], ln[6+2*i], 0 }; g_edid[i] = (BYTE)strtoul(h, 0, 16); } }
        else if (sscanf(ln, "vcp %x %u %u %u", &c, &t, &cur, &mx) == 4 && c < 256) {
            g_vcp[c].present = 1; g_vcp[c].type = t; g_vcp[c].cur = cur; g_vcp[c].max = mx;
        }
    }
    fclose(f); free(ln);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r)
{
    if (why == DLL_PROCESS_ATTACH) {
        const char *lp = getenv("SC_DDC_LOG");
        InitializeCriticalSection(&g_cs);
        if (lp) g_log = fopen(lp, "a");
        load_profile();
        lg("nvapi shim attached, caps %u chars", (unsigned)strlen(g_caps));
    }
    return TRUE;
}

/* ---- DDC/CI responder ---- */
static void set_reply(const BYTE *body, int n) /* body = opcode.. (no addr/len/chk) */
{
    BYTE c = 0x50; int i;
    g_reply[0] = 0x6E; g_reply[1] = 0x80 | n; memcpy(g_reply + 2, body, n);
    c ^= g_reply[0] ^ g_reply[1];
    for (i = 0; i < n; i++) c ^= body[i];
    g_reply[2 + n] = c; g_replylen = 3 + n;
}

static void ddc_request(const BYTE *b, int n) /* b = full message from 0x51 on */
{
    char h[200]; BYTE body[40]; int len;
    if (n < 3 || b[0] != 0x51) { lg("DDC/CI write not a host message"); g_replylen = 0; return; }
    len = b[1] & 0x7F;
    if (len == 0) { lg("DDC/CI null message"); g_replylen = 0; return; }
    switch (b[2]) {
    case 0x01: { /* get VCP */
        BYTE c = b[3]; body[0] = 0x02;
        if (!g_vcp[c].present) { body[1] = 1; body[2] = c; body[3] = 0; memset(body + 4, 0, 4); lg("DDC/CI GetVCP 0x%02X -> unsupported", c); }
        else { body[1] = 0; body[2] = c; body[3] = (BYTE)g_vcp[c].type;
               body[4] = (BYTE)(g_vcp[c].max >> 8); body[5] = (BYTE)g_vcp[c].max; body[6] = (BYTE)(g_vcp[c].cur >> 8); body[7] = (BYTE)g_vcp[c].cur;
               lg("DDC/CI GetVCP 0x%02X -> cur=0x%04lX max=0x%04lX", c, g_vcp[c].cur, g_vcp[c].max); }
        set_reply(body, 8); break; }
    case 0x03: { /* set VCP */
        BYTE c = b[3]; DWORD v = (b[4] << 8) | b[5];
        lg("DDC/CI SetVCP 0x%02X = 0x%04lX [RAM only]", c, v);
        if (g_vcp[c].present) g_vcp[c].cur = v;
        g_replylen = 0; break; }
    case 0xF3: { /* capabilities request */
        int off = (b[3] << 8) | b[4], total = (int)strlen(g_caps), cnt = total - off;
        if (cnt < 0) cnt = 0; if (cnt > 32) cnt = 32;
        body[0] = 0xE3; body[1] = b[3]; body[2] = b[4]; memcpy(body + 3, g_caps + off, cnt);
        lg("DDC/CI CapsRequest offset=%d -> %d bytes", off, cnt);
        set_reply(body, 3 + cnt); break; }
    case 0x07: { body[0] = 0x4E; body[1] = 0; body[2] = 0; body[3] = 0; body[4] = 0; body[5] = 0; body[6] = 0; lg("DDC/CI TimingRequest"); set_reply(body, 7); break; }
    case 0x0C: lg("DDC/CI SaveCurrentSettings"); g_replylen = 0; break;
    default:
        hex(h, b, n); lg("DDC/CI UNKNOWN opcode 0x%02X (TPV/vendor?) msg=%s", b[2], h);
        g_replylen = 0; /* no reply: the app's behaviour on silence is itself informative */
    }
}

/* ---- NVAPI ---- */
typedef int NvS;
static NvS Ok0(void) { lg("NvAPI_Initialize/Unload"); return 0; }
static NvS EnumGPUs(void **h, DWORD *n) { lg("EnumPhysicalGPUs -> 1"); h[0] = (void *)0x1000; *n = 1; return 0; }
static NvS ConnDisp(void *g, DWORD *ids, DWORD *cnt, DWORD fl)
{
    DWORD stride; lg("GPU_GetConnectedDisplayIds(ids=%p flags=0x%lX)", ids, fl);
    if (!ids) { *cnt = 1; return 0; }
    stride = ids[0] & 0xFFFF; if (stride < 16) stride = 16;
    memset(ids + 1, 0, stride - 4);
    ids[1] = 0x23 /* NV_MONITOR_CONN_TYPE_DP */; ids[2] = 0x80061085; *cnt = 1; return 0;
}
static NvS GetEDID(void *g, DWORD id, BYTE *e)
{
    lg("GPU_GetEDID(displayId=0x%lX, version=0x%lX)", id, *(DWORD *)e);
    memcpy(e + 4, g_edid, 256); *(DWORD *)(e + 260) = 256; return 0;
}
static NvS I2CW(void *g, BYTE *i)
{
    BYTE msg[80]; int n = 0, rs = *(int *)(i + 16), cb = *(int *)(i + 24); BYTE *reg = *(BYTE **)(i + 12), *dat = *(BYTE **)(i + 20); char h[300];
    if (reg && rs > 0 && rs < 32) { memcpy(msg, reg, rs); n = rs; }
    if (dat && cb > 0 && n + cb < 80) { memcpy(msg + n, dat, cb); n += cb; }
    hex(h, msg, n);
    lg("I2CWrite dev=0x%02X ddc=%d mask=0x%lX port=%d reg=%d data=%d : %s", i[9], i[8], *(DWORD *)(i + 4), i[36], rs, cb, h);
    if ((i[9] | 1) == 0x6F) ddc_request(msg, n);
    else if (i[9] == 0xA0 && n >= 1) g_edidoff = msg[0]; /* EDID offset */
    return 0;
}
static NvS I2CR(void *g, BYTE *i)
{
    int cb = *(int *)(i + 24); BYTE *dat = *(BYTE **)(i + 20); char h[300]; int k;
    if (!dat) return -1;
    memset(dat, 0, cb);
    if (i[9] == 0xA1) { int j; for (j = 0; j < cb; j++) dat[j] = g_edid[(g_edidoff + j) & 255]; lg("I2CRead EDID off=%d len=%d", g_edidoff, cb); return 0; }
    k = g_replylen < cb ? g_replylen : cb;
    if (k) memcpy(dat, g_reply, k);
    hex(h, dat, k);
    lg("I2CRead dev=0x%02X want=%d -> %d bytes: %s", i[9], cb, k, h);
    g_replylen = 0;
    return k ? 0 : -1;
}

void *CDECL nvapi_QueryInterface(DWORD id)
{
    void *f = 0;
    switch (id) {
    case 0x0150E828: case 0xD22BDD7E: f = Ok0; break;
    case 0xE5AC921F: f = EnumGPUs; break;
    case 0x0078DBA2: f = ConnDisp; break;
    case 0x37D32E69: f = GetEDID; break;
    case 0xE812EB07: f = I2CW; break;
    case 0x2FDE12C5: f = I2CR; break;
    default: break;
    }
    lg("QueryInterface(0x%08lX) -> %s", id, f ? "implemented" : "NULL");
    return f;
}
