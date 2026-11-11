/* test_nvstore.c: host test of awto/settings/settings.c storage (awto-ddc#151): SF_SDK rows through set_sdk_*, the aux
 * block, unchanged values, risky rows, legacy record import. Mock SDK store, flash and apply hooks.
 * Build and run from the repo root:
 *   gcc -std=gnu11 -Wall -Wextra -Iawto/include -Iawto/settings tests/host/test_nvstore.c awto/settings/settings.c \
 *       awto/settings/set_table.c awto/nvram/nvram.c -o tmp/test_nvstore && tmp/test_nvstore */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "settings.h"
#include "nvram.h"

static int fails;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

/* ---- mock flash for the legacy record (nvram.c) ---- */
static uint8_t flash[0x2000];
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
    if (a < FB || a + n > FB + sizeof flash) return 0;
    for (i = 0; i < n; i++) flash[a - FB + i] &= src[i];
    return 1;
}
uint8_t fl_erase(uint32_t a)
{
    if (a < FB || a >= FB + sizeof flash) return 0;
    memset(flash + (a - FB), 0xFF, 0x1000);
    return 1;
}

/* ---- mock SDK store: one field per id ---- */
static int16_t sdk[256];
static int sdk_puts, aux_dirty, commits;
int16_t set_sdk_get(uint8_t id) { return sdk[id]; }
void set_sdk_put(uint8_t id, int16_t v) { sdk[id] = v; sdk_puts++; }
void set_nv_dirty(void) { aux_dirty++; }
void set_nv_commit(uint8_t show) { (void)show; commits++; }

static uint16_t now_ms;
uint16_t set_now_ms(void) { return now_ms; }
void set_wait_ms(uint16_t ms) { now_ms += ms; }
uint8_t set_recovery_requested(void) { return 0; }
int16_t set_status(uint8_t id) { (void)id; return 0; }

static int ap_calls;
#define AP(n) void set_ap_##n(uint8_t id, int16_t v) { (void)id; (void)v; ap_calls++; }
AP(aspect) AP(backlight) AP(black_level) AP(colour_temp) AP(contrast) AP(debug_msgs) AP(debug_popup)
AP(dp_edid) AP(dp_version) AP(factory_menu) AP(gamma) AP(gpio_test) AP(input_mode) AP(input_select)
AP(key_test) AP(msg_log) AP(osd_font) AP(osd_pos) AP(osd_scale) AP(osd_transparency) AP(overscan) AP(power)
AP(power_mode) AP(sdk_language) AP(sdk_sys) AP(search_time) AP(user_rgb)

static void sdk_defaults(void)
{
    struct setting r;
    uint8_t i;
    for (i = 0; i < SET_COUNT; i++) { set_row(i, &r); sdk[r.id] = r.def; }
}

int main(void)
{
    uint8_t len, save[SET_AUX_MAX];
    int n;

    memset(flash, 0xFF, sizeof flash);
    sdk_defaults();
    set_load();
    set_boot();

    /* 1. SF_SDK row: stored in the SDK field, read back from it; unchanged = no put */
    n = sdk_puts;
    CHECK(set_put(SET_ID_BRIGHTNESS, 60, 0) && sdk[SET_ID_BRIGHTNESS] == 60 && sdk_puts == n + 1, "sdk put");
    sdk[SET_ID_BRIGHTNESS] = 61;                         /* the firmware changed the field: the registry sees it */
    CHECK(set_get(SET_ID_BRIGHTNESS) == 61, "sdk get %d", set_get(SET_ID_BRIGHTNESS));
    n = sdk_puts; ap_calls = 0;
    CHECK(set_put(SET_ID_BRIGHTNESS, 61, 1) && sdk_puts == n && ap_calls == 0, "unchanged sdk row: no put, no apply");
    sdk[SET_ID_BRIGHTNESS] = 500;
    CHECK(set_get(SET_ID_BRIGHTNESS) == 100, "sdk value clamped to the row range");

    /* 2. aux row: dirty only on a change; non-nv rows never dirty */
    n = aux_dirty;
    set_put(SET_ID_PANEL_T1, 12, 0); set_confirm();
    CHECK(aux_dirty > n, "aux change -> dirty");
    n = aux_dirty;
    set_put(SET_ID_PANEL_T1, 12, 1);
    CHECK(aux_dirty == n, "aux unchanged -> not dirty");
    set_put(SET_ID_INPUT, 2, 0); set_track(SET_ID_INPUT, 0);
    CHECK(aux_dirty == n, "input (not stored) never dirty");

    /* 3. aux pack / unpack round trip; pending risky value packed as its old value */
    set_put(SET_ID_SEARCH_HDMI_MS, 4000, 0); set_confirm();
    set_put(SET_ID_PANEL_T3, 900, 1);                    /* risky, pending */
    len = set_aux_pack();
    CHECK(len == SET_AUX_MAX, "aux length %u of %u", len, SET_AUX_MAX);
    memcpy(save, set_aux_buf(), len);
    set_revert();
    set_load();                                          /* defaults again */
    CHECK(set_get(SET_ID_SEARCH_HDMI_MS) == 2000, "defaults after load");
    memcpy(set_aux_buf(), save, len);
    set_aux_unpack(len);
    CHECK(set_get(SET_ID_SEARCH_HDMI_MS) == 4000 && set_get(SET_ID_PANEL_T1) == 12, "aux round trip %d %d",
          set_get(SET_ID_SEARCH_HDMI_MS), set_get(SET_ID_PANEL_T1));
    CHECK(set_get(SET_ID_PANEL_T3) == 550, "pending risky stored as the old value: %d", set_get(SET_ID_PANEL_T3));
    save[0] ^= 1;
    memcpy(set_aux_buf(), save, len);
    set_load(); set_aux_unpack(len);
    CHECK(set_get(SET_ID_SEARCH_HDMI_MS) == 2000, "wrong layout check: defaults stay");

    /* 4. defaults: SDK rows through set_sdk_put, never a write here */
    sdk[SET_ID_CONTRAST] = 10; n = commits;
    set_defaults();
    CHECK(sdk[SET_ID_CONTRAST] == 50 && commits == n, "defaults to the SDK fields, no commit");

    /* 5. legacy record: values land in the SDK fields and the aux rows */
    {
        uint8_t rec[3 + 6];
        rec[0] = 0; rec[1] = 0; rec[2] = 2;
        rec[3] = SET_ID_CONTRAST; rec[4] = 33; rec[5] = 0;
        rec[6] = SET_ID_PANEL_T2; rec[7] = 0x2C; rec[8] = 0x01;   /* 300 */
        /* write a slot by hand through nvram.c's own store */
        CHECK(nv_store(NV_REC_SETTINGS, rec, sizeof rec), "legacy slot written");
        set_load();
        CHECK(set_load_legacy() == 1 && sdk[SET_ID_CONTRAST] == 33 && set_get(SET_ID_PANEL_T2) == 300, "legacy import %d %d",
              sdk[SET_ID_CONTRAST], set_get(SET_ID_PANEL_T2));
    }

    printf("%s: %d failures (aux %u B, %u rows)\n", fails ? "FAIL" : "PASS", fails, SET_AUX_MAX, SET_COUNT);
    return fails != 0;
}
