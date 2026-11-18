/* test_nvequal.c: nv_store writes nothing when the payload equals the newest slot (awto-ddc#151).
 * Build and run from fw/rtdfw:
 *   gcc -std=gnu11 -Wall -Iawto/include tests/host/test_nvequal.c awto/nvram/nvram.c -o ../../tmp/test_nvequal && ../../tmp/test_nvequal */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "nvram.h"

static uint8_t flash[0x2000];
static int wr, er;
#define FB 0xFD000u
uint8_t fl_read(uint32_t a, uint8_t *d, uint16_t n)
{
    if (a < FB || a + n > FB + sizeof flash) return 0;
    memcpy(d, flash + (a - FB), n);
    return 1;
}
uint8_t fl_write(uint32_t a, const uint8_t *s, uint16_t n)
{
    uint16_t i;
    if (a < FB || a + n > FB + sizeof flash) return 0;
    wr++;
    for (i = 0; i < n; i++) flash[a - FB + i] &= s[i];
    return 1;
}
uint8_t fl_erase(uint32_t a)
{
    er++;
    memset(flash + (a - FB), 0xFF, 0x1000);
    return 1;
}

int main(void)
{
    uint8_t p[100];
    int w0, e0, fails = 0;

    memset(flash, 0xFF, sizeof flash);
    memset(p, 7, sizeof p);
    fails += !nv_store(NV_REC_SETTINGS, p, sizeof p);
    w0 = wr;
    e0 = er;
    printf("first store: %d programs, %d erases\n", wr, er);
    fails += !nv_store(NV_REC_SETTINGS, p, sizeof p);
    if (wr != w0 || er != e0) { puts("FAIL equal payload wrote"); fails++; }
    p[99] = 8;
    fails += !nv_store(NV_REC_SETTINGS, p, sizeof p);
    if (wr == w0) { puts("FAIL changed payload not written"); fails++; }
    printf("%s\n", fails ? "FAIL" : "PASS");
    return fails;
}
