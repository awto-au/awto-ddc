#include <stdio.h>
#include <stdint.h>
#include "settings.h"
#include "menu.h"
#include "vcp.h"

/* Exercise the real vcp.c and generated table. Only the settings backend and
 * menu are mocked. This is a host mapping check, not a full-image simulator. */
static int16_t values[256];
static unsigned checks, fails;
struct menu_diag menu_diag;
int16_t set_get(uint8_t id) { return values[id]; }
uint8_t set_put(uint8_t id, int16_t v, uint8_t apply_now)
{ (void)apply_now; values[id] = v; return 1; }
uint8_t set_pending(void) { return 0; }
void set_confirm(void) {}
void set_nv_commit(uint8_t show) { (void)show; }
void set_defaults(void) {}
uint8_t menu_cmd(uint8_t op, uint16_t arg) { (void)op; (void)arg; return 1; }
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; printf("FAIL line %d: %s\n", __LINE__, #x); } } while (0)

int main(void)
{
    const uint8_t inputs[] = {0x0f, 0x11, 0x12};
    const uint8_t presets[] = {0x08, 0x06, 0x05, 0x04, 0x01, 0x0b};
    const uint8_t inert[] = {0x87, 0xf7, 0xfb, 0xfc};
    uint16_t cur, max;
    uint8_t type;
    struct setting row;
    unsigned i, high;
    for (i = 0; i < SET_COUNT; ++i) {
        set_row(i, &row);
        values[row.id] = row.def;
    }
    for (i = 0; i < 3; ++i) {
        values[SET_ID_INPUT] = i;
        CHECK(vcp_get(0x60, &cur, &max, &type));
        CHECK(cur == inputs[i] && (cur >> 8) == 0 && max == 0x12);
        for (high = 0; high < 256; ++high) {
            CHECK(vcp_set(0x60, (high << 8) | inputs[i]));
            CHECK(values[SET_ID_INPUT] == (int)i);
        }
    }
    values[SET_ID_INPUT] = 1;
    CHECK(vcp_set(0x60, 0x21));
    CHECK(values[SET_ID_INPUT] == 1);
    for (i = 0; i < 6; ++i) {
        values[SET_ID_COLOUR_TEMP] = i;
        CHECK(vcp_get(0x14, &cur, &max, &type) && cur == presets[i]);
        CHECK(vcp_set(0x14, presets[i]) && values[SET_ID_COLOUR_TEMP] == (int)i);
    }
    for (i = 0; i < 5; ++i) {
        CHECK(vcp_set(0xf2, i));
        CHECK(vcp_get(0xf2, &cur, &max, &type) && cur == i && max == 4);
    }
    CHECK(!vcp_get(0x72, &cur, &max, &type));
    CHECK(!vcp_get(0xdc, &cur, &max, &type));
    CHECK(set_vcp_row(0xec) == set_idx(SET_ID_D1_ENABLE));
    CHECK(set_vcp_row(0xed) == set_idx(SET_ID_D2_ENABLE));
    CHECK(set_vcp_row(0xee) == set_idx(SET_ID_D3_ENABLE));
    CHECK(set_vcp_row(0xef) == set_idx(SET_ID_INPUT_MODE));
    for (i = 0; i < sizeof inert; ++i) {
        set_row(set_vcp_row(inert[i]), &row);
        CHECK(row.flags & SF_INERT);
        CHECK(vcp_get(inert[i], &cur, &max, &type));
    }
    printf("%u checks, %u failures\n", checks, fails);
    printf("CAPS=");
    for (i = 0; i < set_caps_len(); ++i) putchar(set_caps_at(i));
    putchar('\n');
    return fails != 0;
}
