/* Fake dxva2.dll monitor-configuration API for SmartControl under Wine.
 * One physical monitor; capabilities / VCP values from the profile
 * (scripts/smartcontrol_profile.py). Every call is logged with a timestamp.
 * Env: SC_PROFILE = profile path, SC_DDC_LOG = log path. Writes only touch RAM.
 * Build: tools/smartcontrol_dxva2/build.py */
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FAKE_HANDLE ((HANDLE)0x5C0001)
#define ERR_VCP_UNSUPPORTED 0xC0262589u /* ERROR_GRAPHICS_DDCCI_VCP_NOT_SUPPORTED */

static FILE *g_log;
static CRITICAL_SECTION g_cs;
static char g_caps[2048];
typedef struct { int present, type; DWORD cur, max; } Vcp;
static Vcp g_vcp[256];

static void lg(const char *fmt, ...)
{
    SYSTEMTIME t; va_list ap; char buf[600];
    if (!g_log) return;
    GetLocalTime(&t);
    va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    EnterCriticalSection(&g_cs);
    fprintf(g_log, "%04d-%02d-%02dT%02d:%02d:%02d.%03d pid=%lu tid=%lu %s\n", t.wYear, t.wMonth, t.wDay,
            t.wHour, t.wMinute, t.wSecond, t.wMilliseconds, GetCurrentProcessId(), GetCurrentThreadId(), buf);
    fflush(g_log);
    LeaveCriticalSection(&g_cs);
}

static void load_profile(void)
{
    const char *p = getenv("SC_PROFILE");
    FILE *f; char *ln = malloc(8192);
    if (!p || !(f = fopen(p, "r"))) { lg("profile: cannot open '%s'", p ? p : "(unset)"); free(ln); return; }
    while (fgets(ln, 8192, f)) {
        unsigned c, t, cur, mx; size_t n = strlen(ln);
        while (n && (ln[n-1] == '\n' || ln[n-1] == '\r')) ln[--n] = 0;
        if (!strncmp(ln, "caps ", 5)) { strncpy(g_caps, ln + 5, sizeof g_caps - 1); }
        else if (sscanf(ln, "vcp %x %u %u %u", &c, &t, &cur, &mx) == 4 && c < 256) {
            g_vcp[c].present = 1; g_vcp[c].type = t; g_vcp[c].cur = cur; g_vcp[c].max = mx;
        }
    }
    fclose(f); free(ln);
    lg("profile loaded: caps %u chars", (unsigned)strlen(g_caps));
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID r)
{
    if (why == DLL_PROCESS_ATTACH) {
        char exe[MAX_PATH]; const char *lp = getenv("SC_DDC_LOG");
        InitializeCriticalSection(&g_cs);
        if (lp) g_log = fopen(lp, "a");
        GetModuleFileNameA(NULL, exe, sizeof exe);
        lg("dxva2 shim attached in %s", exe);
        load_profile();
    }
    return TRUE;
}

#pragma pack(push, 1)
typedef struct { HANDLE h; WCHAR desc[128]; } PM;
#pragma pack(pop)

BOOL WINAPI GetNumberOfPhysicalMonitorsFromHMONITOR(HMONITOR m, LPDWORD n)
{ lg("GetNumberOfPhysicalMonitorsFromHMONITOR(%p) -> 1", m); if (n) *n = 1; return TRUE; }

BOOL WINAPI GetPhysicalMonitorsFromHMONITOR(HMONITOR m, DWORD n, PM *a)
{
    lg("GetPhysicalMonitorsFromHMONITOR(%p, %lu)", m, n);
    if (n < 1 || !a) return FALSE;
    a[0].h = FAKE_HANDLE; wcscpy(a[0].desc, L"Generic PnP Monitor");
    return TRUE;
}
BOOL WINAPI DestroyPhysicalMonitor(HANDLE h) { lg("DestroyPhysicalMonitor(%p)", h); return TRUE; }
BOOL WINAPI DestroyPhysicalMonitors(DWORD n, PM *a) { lg("DestroyPhysicalMonitors(%lu)", n); return TRUE; }

BOOL WINAPI GetCapabilitiesStringLength(HANDLE h, LPDWORD len)
{ lg("GetCapabilitiesStringLength -> %u", (unsigned)strlen(g_caps) + 1); *len = (DWORD)strlen(g_caps) + 1; return TRUE; }

BOOL WINAPI CapabilitiesRequestAndCapabilitiesReply(HANDLE h, LPSTR buf, DWORD n)
{
    lg("CapabilitiesRequestAndCapabilitiesReply(len=%lu) -> caps string", n);
    if (n < strlen(g_caps) + 1) return FALSE;
    strcpy(buf, g_caps); return TRUE;
}

BOOL WINAPI GetVCPFeatureAndVCPFeatureReply(HANDLE h, BYTE c, LPDWORD type, LPDWORD cur, LPDWORD max)
{
    if (!g_vcp[c].present) { lg("GetVCP 0x%02X -> unsupported", c); SetLastError(ERR_VCP_UNSUPPORTED); return FALSE; }
    if (type) *type = g_vcp[c].type;
    if (cur) *cur = g_vcp[c].cur;
    if (max) *max = g_vcp[c].max;
    lg("GetVCP 0x%02X -> type=%d cur=0x%04lX max=0x%04lX", c, g_vcp[c].type, g_vcp[c].cur, g_vcp[c].max);
    return TRUE;
}

BOOL WINAPI SetVCPFeature(HANDLE h, BYTE c, DWORD v)
{
    int known = g_vcp[c].present;
    lg("SetVCP 0x%02X = 0x%04lX (%lu) [%s; RAM only, nothing sent]", c, v, v, known ? "known code" : "NOT in readable set");
    if (known) g_vcp[c].cur = v;
    return TRUE;
}
BOOL WINAPI SaveCurrentSettings(HANDLE h) { lg("SaveCurrentSettings"); return TRUE; }

#define STUB(name, ...) BOOL WINAPI name(HANDLE h, ##__VA_ARGS__) { lg(#name " (stub, FALSE)"); SetLastError(ERR_VCP_UNSUPPORTED); return FALSE; }
BOOL WINAPI GetMonitorCapabilities(HANDLE h, LPDWORD cap, LPDWORD ct)
{ lg("GetMonitorCapabilities"); if (cap) *cap = 0; if (ct) *ct = 0; return TRUE; }
BOOL WINAPI GetMonitorTechnologyType(HANDLE h, LPDWORD t) { lg("GetMonitorTechnologyType -> LCD(1)"); if (t) *t = 1; return TRUE; }
STUB(GetTimingReport, void *t)
STUB(GetMonitorBrightness, LPDWORD a, LPDWORD b, LPDWORD c)
STUB(SetMonitorBrightness, DWORD a)
STUB(GetMonitorContrast, LPDWORD a, LPDWORD b, LPDWORD c)
STUB(SetMonitorContrast, DWORD a)
STUB(GetMonitorColorTemperature, LPDWORD a)
STUB(SetMonitorColorTemperature, DWORD a)
STUB(GetMonitorRedGreenOrBlueGain, DWORD t, LPDWORD a, LPDWORD b, LPDWORD c)
STUB(SetMonitorRedGreenOrBlueGain, DWORD t, DWORD a)
STUB(GetMonitorRedGreenOrBlueDrive, DWORD t, LPDWORD a, LPDWORD b, LPDWORD c)
STUB(SetMonitorRedGreenOrBlueDrive, DWORD t, DWORD a)
STUB(GetMonitorDisplayAreaPosition, DWORD t, LPDWORD a, LPDWORD b, LPDWORD c)
STUB(GetMonitorDisplayAreaSize, DWORD t, LPDWORD a, LPDWORD b, LPDWORD c)
STUB(DegaussMonitor)
STUB(RestoreMonitorFactoryDefaults)
STUB(RestoreMonitorFactoryColorDefaults)
LONG WINAPI GetNumberOfPhysicalMonitorsFromIDirect3DDevice9(void *d, LPDWORD n) { lg("GetNumberOfPhysicalMonitorsFromIDirect3DDevice9"); if (n) *n = 0; return E_FAIL; }
LONG WINAPI GetPhysicalMonitorsFromIDirect3DDevice9(void *d, DWORD n, PM *a) { lg("GetPhysicalMonitorsFromIDirect3DDevice9"); return E_FAIL; }
