/* Host harness for fw/test/ddr_draw.c (#267): a model of MCU_DC port A + the frame buffer; the firmware source is #included unchanged.
   stdin: "op x y w h r g b n" per line; "dump FILE" writes the model memory. argv[1] = polls CMD stays busy after a write (-1 = never idle). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned char BYTE;
typedef unsigned short WORD;
#define __xdata
#define __code
#define _ON 1
#define _OFF 0
#define _AWTO_FREEZE _ON
#define AWTO_DRW_HOST
#define GET_OSD_FREEZE_STATUS() 1
#include "../fw/sdk/Project/Header/AwtoRegs.h"

#define UNITS 3110400UL
static unsigned char *mem;
static unsigned char regs[0x10000];
static long busy;
static long busy_after;
static unsigned long hazards, writes;
static unsigned long ms_now;

static unsigned long AwtoMs(void) { return ms_now++; }
static unsigned drw_rd(unsigned r)
{
    if(r == AWTO_R_MCU_DC_CMD_A)
    {
        if(busy_after < 0) return 0x80;
        if(busy > 0) { busy--; return 0x80; }
        return 0;
    }
    return regs[r];
}
static void drw_wr(unsigned r, unsigned v)
{
    if(r == AWTO_R_MCU_DC_CMD_A)
    {
        unsigned long a = ((unsigned long)(regs[AWTO_R_MCU_DC_ADDR_H_A] & 0xF) << 24) | ((unsigned long)regs[AWTO_R_MCU_DC_ADDR_M_A] << 16) |
                          ((unsigned long)regs[AWTO_R_MCU_DC_ADDR_L_A] << 8) | regs[AWTO_R_MCU_DC_ADDR_A];
        unsigned mask = (regs[AWTO_R_MCU_DC_WMASK_H_A] << 8) | regs[AWTO_R_MCU_DC_WMASK_L_A];   /* bit n = buffer byte n not written */
        int j;
        if(drw_rd(r) != 0) hazards++;
        if(regs[AWTO_R_MCU_DC_LEN_A] != 2 || a + 2 > UNITS) { hazards++; return; }
        for(j = 0; j < 16; j++)
            if(!((mask >> j) & 1)) mem[8 * a + ((j + 8) & 15)] = regs[AWTO_R_MCU_DC_DATABUF_W_00_A + j];   /* halves swapped */
        busy = busy_after;
        writes++;
        return;
    }
    if(busy > 0 || busy_after < 0) hazards++;   /* address / data / mask / length changed while a command is in flight */
    regs[r] = (unsigned char)v;
}
#define DRW_RD(reg) drw_rd(reg)
#define DRW_WR(reg, val) drw_wr((reg), (val))
#define DRW_FEED() do { } while(0)

#include "../fw/test/ddr_draw.c"
StAwtoDraw g_stAwtoDraw;

int main(int argc, char **argv)
{
    char line[256];
    busy_after = argc > 1 ? atol(argv[1]) : 0;
    mem = calloc(UNITS, 8);
    while(fgets(line, sizeof line, stdin))
    {
        unsigned op, x, y, w, h, r, g, b, n;
        char f[200];
        if(sscanf(line, "dump %199s", f) == 1)
        {
            FILE *o = fopen(f, "wb");
            fwrite(mem, 8, UNITS, o);
            fclose(o);
        }
        else if(sscanf(line, "%u %u %u %u %u %u %u %u %u", &op, &x, &y, &w, &h, &r, &g, &b, &n) == 9)
        {
            g_stAwtoDraw.usX = x; g_stAwtoDraw.usY = y; g_stAwtoDraw.usW = w; g_stAwtoDraw.usH = h;
            g_stAwtoDraw.ucR = r; g_stAwtoDraw.ucG = g; g_stAwtoDraw.ucB = b; g_stAwtoDraw.ucN = n;
            g_stAwtoDraw.ucGo = op;
            AwtoDrwPoll();
            printf("state %u bursts %lu slow %u hazards %lu writes %lu go %u\n", g_stAwtoDraw.ucState, g_stAwtoDraw.ulBursts, g_stAwtoDraw.ucSlow, hazards, writes, g_stAwtoDraw.ucGo);
            busy = 0;
        }
    }
    return 0;
}
