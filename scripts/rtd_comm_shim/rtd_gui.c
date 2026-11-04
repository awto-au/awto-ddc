/* In-Wine GUI driver for RTDTool.exe (Win32 messages, no coordinates).
 * rtd_gui tree                      list top-level windows + all child controls
 * rtd_gui click <hwnd>              BM_CLICK
 * rtd_gui combo <hwnd> <index>      CB_SETCURSEL + CBN_SELCHANGE to parent
 * rtd_gui text  <hwnd> <string>     WM_SETTEXT
 * rtd_gui cmd   <hwnd> <id>         WM_COMMAND(id) to window (menu/toolbar items)
 * hwnd is hex as printed by `tree`. Output is plain text on stdout.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int depth;

static void show(HWND h) {
    char cls[96] = "", txt[160] = ""; RECT r;
    GetClassNameA(h, cls, sizeof cls);
    SendMessageTimeoutA(h, WM_GETTEXT, sizeof txt, (LPARAM)txt, SMTO_ABORTIFHUNG, 500, NULL);
    GetWindowRect(h, &r);
    printf("%*s%p cls=%s id=%d vis=%d en=%d [%ld,%ld %ldx%ld] \"%s\"\n", depth * 2, "", (void *)h, cls,
           (int)GetDlgCtrlID(h), IsWindowVisible(h), IsWindowEnabled(h), r.left, r.top,
           r.right - r.left, r.bottom - r.top, txt);
}

static BOOL CALLBACK kid(HWND h, LPARAM p) {
    if (GetParent(h) != (HWND)p) return TRUE;
    show(h); depth++;
    EnumChildWindows(h, kid, (LPARAM)h);
    depth--;
    return TRUE;
}

static BOOL CALLBACK top(HWND h, LPARAM p) {
    char t[160] = "";
    GetWindowTextA(h, t, sizeof t);
    if (!t[0] || !IsWindowVisible(h)) return TRUE;
    show(h); depth = 1;
    EnumChildWindows(h, kid, (LPARAM)h);
    depth = 0;
    return TRUE;
}

int main(int argc, char **argv) {
    HWND h;
    if (argc < 2 || !strcmp(argv[1], "tree")) { EnumWindows(top, 0); return 0; }
    if (argc < 3) return 2;
    h = (HWND)(size_t)strtoull(argv[2], NULL, 16);
    if (!IsWindow(h)) { printf("no such window %s\n", argv[2]); return 3; }
    /* Post, never Send: a click handler can run long or open a modal dialog and would block us. */
    if (!strcmp(argv[1], "click")) { PostMessageA(h, BM_CLICK, 0, 0); }
    else if (!strcmp(argv[1], "combo") && argc > 3) {
        int i = atoi(argv[3]);
        DWORD_PTR res;
        SendMessageTimeoutA(h, CB_SETCURSEL, i, 0, SMTO_ABORTIFHUNG, 2000, &res);
        PostMessageA(GetParent(h), WM_COMMAND, MAKEWPARAM(GetDlgCtrlID(h), CBN_SELCHANGE), (LPARAM)h);
    }
    else if (!strcmp(argv[1], "text") && argc > 3) { SendMessageTimeoutA(h, WM_SETTEXT, 0, (LPARAM)argv[3], SMTO_ABORTIFHUNG, 2000, NULL); }
    else if (!strcmp(argv[1], "get")) { show(h); return 0; }
    else if (!strcmp(argv[1], "cmd") && argc > 3) { PostMessageA(h, WM_COMMAND, MAKEWPARAM(atoi(argv[3]), 0), 0); }
    else return 2;
    printf("ok\n");
    return 0;
}
