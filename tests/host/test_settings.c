/* test_settings.c: host test of awto/settings + awto/nvram (awto-ddc#67) with mock flash, OSD grid and apply hooks.
 * Build and run from the repo root:
 *   gcc -std=gnu11 -Wall -Wextra -Iawto/include -Iawto/settings tests/host/test_settings.c awto/settings/[a-z]*.c \
 *       awto/nvram/nvram.c -o tmp/test_settings && tmp/test_settings [--dump DIR]
 * --dump DIR: one text screen per menu page (DIR/page_NN.txt), for review without the sim. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "settings.h"
#include "nvram.h"
#include "osd.h"
#include "menu.h"
#include "vcp.h"

void vcp_box_service(void);

static int fails;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

/* ---- mock flash: 0xFD000..0xFEFFF ---- */
static uint8_t flash[0x2000];
static int erases, writes, cut_after = -1;
#define FB 0xFD000u
uint8_t fl_read(uint32_t a, uint8_t *dst, uint16_t n)
{
    if (a < FB || a + n > FB + sizeof flash) return 0;
    memcpy(dst, flash + (a - FB), n);
    return 1;
}
uint8_t fl_write(uint32_t a, const uint8_t *src, uint16_t n)
{
    uint16_t i;
    if (a < FB || a + n > FB + sizeof flash || ((a & 0xFF) + n) > 256) { printf("bad write %x %u\n", a, n); return 0; }
    if (cut_after == 0) return 0;                       /* power cut: nothing more reaches the flash */
    if (cut_after > 0) cut_after--;
    for (i = 0; i < n; i++) flash[a - FB + i] &= src[i];  /* NOR: program clears bits only */
    writes++;
    return 1;
}
uint8_t fl_erase(uint32_t a)
{
    if (a < FB || a >= FB + sizeof flash || (a & 0xFFF)) return 0;
    memset(flash + (a - FB), 0xFF, 0x1000);
    erases++;
    return 1;
}

/* ---- mock time, keys, status ---- */
static uint16_t now_ms;
static int keys_down;
uint16_t set_now_ms(void) { return now_ms; }
void set_wait_ms(uint16_t ms) { now_ms += ms; }
uint8_t set_recovery_requested(void) { return keys_down; }
int16_t set_status(uint8_t id) { return id == SET_ID_INFO_HRES ? 3840 : id == SET_ID_INFO_VFREQ ? 600 : 0; }

/* ---- mock apply functions: last call per name ---- */
static int ap_calls, last_ap_id, last_ap_v;
#define AP(n) void set_ap_##n(uint8_t id, int16_t v) { ap_calls++; last_ap_id = id; last_ap_v = v; }
AP(aspect) AP(backlight) AP(black_level) AP(colour_temp) AP(contrast) AP(debug_msgs) AP(debug_popup) AP(dp_edid)
AP(dp_version) AP(factory_menu) AP(gamma) AP(input_mode) AP(input_select) AP(msg_log) AP(osd_pos) AP(osd_scale)
AP(mute) AP(volume) AP(osd_transparency) AP(overscan) AP(power) AP(power_mode) AP(sdk_language) AP(search_time) AP(user_rgb) AP(vendor_menu)
static int injected = -1, held_mask, held_ms;
void key_inject(uint8_t k) { injected = k; menu_key(k); }   /* the firmware routes the key back into menu_key */
void key_hold(uint8_t mask, uint16_t ms) { held_mask = mask; held_ms = ms; }

/* ---- mock OSD: text grid ---- */
static char grid[MENU_ROWS][MENU_COLS + 1];
static uint8_t gfg[MENU_ROWS];
static int glyphs, shown, osd_cols;
void osd_tc_open(uint8_t cols, uint8_t rows) { osd_cols = cols; memset(grid, ' ', sizeof grid); (void)rows; }
void osd_tc_glyph(uint16_t id, const uint8_t *b) { (void)b; if (id < OSD_FONT_N) glyphs++; }
void osd_tc_row(uint8_t r, const char *s, uint8_t n, uint8_t fg, uint8_t bg)
{
    (void)bg;
    if (r >= MENU_ROWS || n > MENU_COLS) { fails++; printf("FAIL row %u n %u\n", r, n); return; }
    memcpy(grid[r], s, n); grid[r][MENU_COLS] = 0; gfg[r] = fg;
}
void osd_tc_place(uint8_t h, uint8_t v, uint8_t big) { (void)h; (void)v; (void)big; }
void osd_tc_show(uint8_t on) { shown = on; }
void osd_tc_close(void) { shown = 0; }

static void screen(FILE *f)
{
    int r;
    for (r = 0; r < MENU_ROWS; r++) fprintf(f, "|%s|%s\n", grid[r], gfg[r] == OC_HL || gfg[r] == OC_WARN ? " <" : "");
}

static int find_line(const char *s)
{
    int r;
    for (r = 0; r < MENU_ROWS; r++) if (strstr(grid[r], s)) return r;
    return -1;
}

static void key(uint8_t k) { menu_key(k); now_ms += 50; }

static void boot(void)
{
    set_load();
    set_boot();
}

int main(int argc, char **argv)
{
    const char *dump = (argc > 2 && !strcmp(argv[1], "--dump")) ? argv[2] : NULL;
    uint16_t cur, max; uint8_t type; int p, k;

    memset(flash, 0xFF, sizeof flash);

    /* 1. empty flash -> defaults, load result 0 */
    boot();
    CHECK(set_load_result() == 0, "load result %u", set_load_result());
    CHECK(set_get(SET_ID_BRIGHTNESS) == 44 && set_get(SET_ID_PANEL_T3) == 550, "defaults");
    CHECK(ap_calls > 10, "apply_all ran %d", ap_calls);

    /* 2. clamp + step + save + reload */
    CHECK(set_put(SET_ID_BRIGHTNESS, 150, 0) && set_get(SET_ID_BRIGHTNESS) == 100, "clamp high");
    CHECK(set_put(SET_ID_PANEL_T2, 333, 0) && set_get(SET_ID_PANEL_T2) == 330, "step 10: %d", set_get(SET_ID_PANEL_T2));
    set_confirm();
    CHECK(set_put(SET_ID_GAMMA, 3, 0) && set_get(SET_ID_GAMMA) == 3, "enum");
    now_ms += SET_SAVE_MS; set_service();
    CHECK(writes > 0, "saved");
    set_put(SET_ID_BRIGHTNESS, 7, 0); set_save_now();
    boot();
    CHECK(set_load_result() == 1, "reload result %u", set_load_result());
    CHECK(set_get(SET_ID_BRIGHTNESS) == 7 && set_get(SET_ID_GAMMA) == 3 && set_get(SET_ID_PANEL_T2) == 330, "round trip %d %d %d",
          set_get(SET_ID_BRIGHTNESS), set_get(SET_ID_GAMMA), set_get(SET_ID_PANEL_T2));

    /* 3. many saves: log wraps both sectors, newest wins */
    for (k = 0; k < 40; k++) { set_put(SET_ID_CONTRAST, k, 0); set_save_now(); }
    boot();
    CHECK(set_get(SET_ID_CONTRAST) == 39, "after 40 saves %d (erases %d)", set_get(SET_ID_CONTRAST), erases);

    /* 4. power cut during a save: the previous record stays */
    set_put(SET_ID_CONTRAST, 77, 0); cut_after = 2; set_save_now(); cut_after = -1;
    boot();
    CHECK(set_get(SET_ID_CONTRAST) == 39, "cut write: %d", set_get(SET_ID_CONTRAST));
    set_put(SET_ID_CONTRAST, 78, 0); set_save_now(); boot();
    CHECK(set_get(SET_ID_CONTRAST) == 78, "save after cut: %d", set_get(SET_ID_CONTRAST));

    /* 5. risky: auto-revert, confirm, never saved while pending */
    CHECK(set_put(SET_ID_PANEL_T3, 1000, 1) && set_pending() == SET_ID_PANEL_T3, "pending");
    now_ms += SET_CONFIRM_MS; set_service();
    CHECK(set_get(SET_ID_PANEL_T3) == 550 && set_pending() == 0, "reverted %d", set_get(SET_ID_PANEL_T3));
    set_put(SET_ID_PANEL_T3, 900, 1); set_confirm(); now_ms += SET_SAVE_MS; set_service(); boot();
    CHECK(set_get(SET_ID_PANEL_T3) == 900, "confirmed + saved %d", set_get(SET_ID_PANEL_T3));

    /* 6. never all inputs off */
    CHECK(set_put(SET_ID_D1_ENABLE, 0, 0), "d1 off"); set_confirm();
    CHECK(set_put(SET_ID_D2_ENABLE, 0, 0), "d2 off"); set_confirm();
    CHECK(!set_put(SET_ID_D3_ENABLE, 0, 0) && set_get(SET_ID_D3_ENABLE) == 1, "last input refused");

    /* 7. recovery: keys held -> defaults; a short press does nothing */
    keys_down = 1; boot(); keys_down = 0;
    CHECK(set_load_result() == 2 && set_get(SET_ID_PANEL_T3) == 550 && set_get(SET_ID_D1_ENABLE) == 1, "recovery");
    boot();
    CHECK(set_get(SET_ID_PANEL_T3) == 550, "recovery saved");

    /* 8. VCP */
    CHECK(vcp_get(0x10, &cur, &max, &type) && cur == 44 && max == 100, "vcp 0x10 %u/%u", cur, max);
    CHECK(vcp_set(0x10, 66) && set_get(SET_ID_BRIGHTNESS) == 66, "vcp set 0x10");
    CHECK(vcp_get(0x60, &cur, &max, &type) && cur == 0x11, "vcp 0x60 = D2 HDMI 0x11: %x", cur);
    CHECK(vcp_get(0x62, &cur, &max, &type) && cur == 50 && max == 100, "vcp 0x62 volume %u/%u", cur, max);
    CHECK(vcp_set(0x62, 30) && set_get(SET_ID_VOLUME) == 30, "vcp 0x62 set");
    CHECK(vcp_set(0x8D, 1) && set_get(SET_ID_MUTE) == 1, "vcp 0x8D = 1 muted -> option On");
    CHECK(vcp_get(0x8D, &cur, &max, &type) && cur == 1, "vcp 0x8D reads 1 muted: %u", cur);
    CHECK(vcp_set(0x8D, 2) && set_get(SET_ID_MUTE) == 0, "vcp 0x8D = 2 unmuted -> option Off");
    CHECK(vcp_set(0x60, 0x0F) && set_get(SET_ID_INPUT) == 0, "vcp 0x60 D1");
    CHECK(vcp_set(0x60, 0x33) && set_get(SET_ID_INPUT) == 0, "vcp 0x60 unknown value ignored");
    vcp_set(VCP_SEL, SET_ID_PANEL_T6);
    CHECK(vcp_get(VCP_VAL, &cur, &max, &type) && cur == 1100 && max == 5000, "paged get %u %u", cur, max);
    CHECK(vcp_set(VCP_VAL, 2000) && set_get(SET_ID_PANEL_T6) == 2000 && set_pending() == SET_ID_PANEL_T6, "paged set");
    vcp_set(VCP_CMD, 1);
    CHECK(set_pending() == 0, "vcp confirm");
    CHECK(vcp_get(VCP_SCHEMA, &cur, &max, &type) && cur == SET_SCHEMA, "schema");
    CHECK(!vcp_get(0x99, &cur, &max, &type), "unsupported code");
    CHECK(vcp_get(0x14, &cur, &max, &type) && cur == 0x05, "0x14 6500K = MCCS 0x05: %x", cur);
    CHECK(vcp_set(0x14, 0x0B) && set_get(SET_ID_COLOUR_TEMP) == 5, "0x14 user");
    CHECK(vcp_set(0x08, 1) && set_get(SET_ID_COLOUR_TEMP) == 2, "0x08 colour reset");
    CHECK(vcp_get(0xDF, &cur, &max, &type) && cur == 0x0202, "VCP version 2.2");
    CHECK(vcp_get(0xE6, &cur, &max, &type) && cur == 1 && max == 1, "manufacturer 0xE6 = fast switch");
    {
        char c[400]; uint16_t i, n = set_caps_len();
        for (i = 0; i < n && i < sizeof c - 1; i++) c[i] = set_caps_at(i);
        c[i] = 0;
        CHECK(strstr(c, "model(awto-mon)") && strstr(c, "60(0F 11 12)") && strstr(c, "mccs_ver(2.2))"), "caps %s", c);
    }
    vcp_set(VCP_RESET, 1);
    CHECK(set_get(SET_ID_PANEL_T6) == 1100 && set_get(SET_ID_BRIGHTNESS) == 44, "vcp 0x04 reset");
    {
        extern struct { uint8_t magic, cmd, code, result, val_lo, val_hi, cur_lo, cur_hi, max_lo, max_hi, type, seq; } vcp_box;
        vcp_box.code = 0x12; vcp_box.val_lo = 33; vcp_box.val_hi = 0; vcp_box.cmd = 2; vcp_box_service();
        CHECK(vcp_box.cmd == 0 && vcp_box.result == 1 && vcp_box.cur_lo == 33 && set_get(SET_ID_CONTRAST) == 33, "mailbox set");
    }

    /* 9. menu: open, walk every page, edit, risky confirm, exit */
    menu_open();
    CHECK(shown && glyphs == OSD_FONT_N && find_line("Settings") == 0, "menu open");
    CHECK(find_line("Picture >") >= 0 && find_line("Information >") >= 0, "main page list");
    if (dump) { char fn[256]; FILE *f; snprintf(fn, sizeof fn, "%s/page_main.txt", dump); f = fopen(fn, "w"); if (f) { screen(f); fclose(f); } }
    for (p = 0; p < 20; p++) {                          /* every top-level page and its sub-pages */
        int r = 2 + p;
        if (r >= 2 + MENU_LIST || grid[r][2] == ' ') break;
        while (menu_cursor() != p) key(MK_RIGHT);
        key(MK_MENU);
        if (dump) {
            char fn[256]; FILE *f;
            snprintf(fn, sizeof fn, "%s/page_%02d.txt", dump, p);
            f = fopen(fn, "w"); if (f) { screen(f); fclose(f); }
            if (strstr(grid[2], " >")) {                 /* first entry is a sub-page */
                key(MK_MENU);
                snprintf(fn, sizeof fn, "%s/page_%02d_sub.txt", dump, p);
                f = fopen(fn, "w"); if (f) { screen(f); fclose(f); }
                key(MK_EXIT);
            }
        }
        key(MK_EXIT);
    }
    /* Picture > Backlight: edit 50 -> 52 live, Menu sets */
    while (menu_cursor() != 0) key(MK_RIGHT);
    key(MK_MENU);
    key(MK_MENU);                                       /* edit Backlight */
    key(MK_RIGHT); key(MK_RIGHT);
    CHECK(set_get(SET_ID_BRIGHTNESS) == 46, "live edit %d", set_get(SET_ID_BRIGHTNESS));
    key(MK_EXIT);                                       /* undo */
    CHECK(set_get(SET_ID_BRIGHTNESS) == 44, "edit undo %d", set_get(SET_ID_BRIGHTNESS));
    key(MK_MENU); key(MK_LEFT); key(MK_MENU);
    CHECK(set_get(SET_ID_BRIGHTNESS) == 43, "edit set %d", set_get(SET_ID_BRIGHTNESS));
    key(MK_EXIT);
    /* Panel timing > T3: risky countdown, Exit = undo */
    for (k = 0; k < 20 && !strstr(grid[2 + menu_cursor()], "Panel timing"); k++) key(MK_RIGHT);
    key(MK_MENU);
    for (k = 0; k < 20 && !strstr(grid[2 + menu_cursor() ], "T3 video"); k++) key(MK_RIGHT);
    key(MK_MENU); key(MK_RIGHT); key(MK_MENU);
    CHECK(set_pending() == SET_ID_PANEL_T3 && find_line("Keep new value") >= 0, "risky prompt");
    if (dump) { char fn[256]; FILE *f; snprintf(fn, sizeof fn, "%s/risky.txt", dump); f = fopen(fn, "w"); if (f) { screen(f); fclose(f); } }
    key(MK_EXIT);
    CHECK(set_pending() == 0 && set_get(SET_ID_PANEL_T3) == 550, "risky undo");
    key(MK_EXIT); key(MK_EXIT);
    CHECK(!menu_active() && !shown, "menu closed");
    /* timeout */
    menu_open();
    for (k = 0; k < 31; k++) { now_ms += 1000; menu_service(); }
    CHECK(!menu_active(), "timeout closes the menu");

    /* 10. host commands + state struct */
    {
        uint16_t r0;
        CHECK(menu_cmd(MO_OPEN, 0) && menu_diag.open == 1 && menu_diag.page == 0 && menu_diag.item_id == SET_ID_BRIGHTNESS, "open page 0");
        r0 = menu_diag.redraw_lo | menu_diag.redraw_hi << 8;
        CHECK(menu_cmd(MO_SELECT, SET_ID_CONTRAST) && menu_diag.item_id == SET_ID_CONTRAST && menu_diag.cursor == 2, "select contrast");
        CHECK((uint16_t)(menu_diag.redraw_lo | menu_diag.redraw_hi << 8) != r0, "redraw counter moves");
        CHECK(menu_cmd(MO_SET, 61) && set_get(SET_ID_CONTRAST) == 61 && menu_diag.val_lo == 61, "set via command");
        CHECK(!menu_cmd(MO_SELECT, SET_ID_PANEL_T3), "select an item of another page refused");
        CHECK(menu_cmd(MO_OPEN, 1) && menu_diag.item_page == 2 && menu_diag.item_id == 0, "colour page: sub-page entry first");
        CHECK(menu_cmd(MO_KEY, MK_MENU) && menu_diag.page == 2 && menu_diag.parent == 1 && injected == MK_MENU, "key into sub-page");
        CHECK(menu_cmd(MO_BACK, 0) && menu_diag.page == 1 && menu_diag.cursor == 0, "back");
        CHECK(menu_cmd(MO_HOLD, (60 << 5) | 0x0A) && held_mask == 0x0A && held_ms == 3000, "hold menu+left 3 s");
        CHECK(menu_cmd(MO_OPEN, MENU_MAIN) && menu_diag.page == MENU_MAIN && menu_diag.item_page == 0, "main");
        CHECK(vcp_set(VCP_MENU, MO_CLOSE << 8) && !menu_diag.open, "close via VCP 0xE4");
        CHECK(!menu_cmd(MO_OPEN, 200), "bad page refused");
        menu_close();
    }

    printf("%s: %d failures (flash writes %d, erases %d)\n", fails ? "FAIL" : "PASS", fails, writes, erases);
    return fails != 0;
}
