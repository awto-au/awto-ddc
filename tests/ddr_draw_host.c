/* Host harness for fw/test/ddr_draw.c (#267): a model of MCU_DC port A + the frame buffer; the firmware source is #included unchanged.
   stdin: "op x y w h r g b n" per line; "dump FILE" writes the model memory; "set blk0 blocks seed stride step inv swap retry samples" sets g_stAwtoAddr params; "addr" prints its results.
   argv[1] = polls CMD stays busy after a write (-1 = never idle); [2] = address bit tied low (-1 none); [3] = stuck-high bit "byte*8+bit" in every unit (-1 none);
   [4] = read lane swap of the model (0 / 1); [5] = every Nth read returns the previous burst (stale, 0 = never). */
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
#define HOST_CMD_READ 0xA0   /* [7:5] = 101 */
static unsigned char *mem;
static unsigned char regs[0x10000];
static long busy;
static long busy_after;
static unsigned long hazards, writes;
static unsigned long ms_now;
static int alias_bit = -1, stuck = -1, rdswap, stale_every;
static unsigned long nreads;
static unsigned char rbuf[16], prev[16];
static unsigned rflag;
static unsigned long aeff(unsigned long a) { return alias_bit < 0 ? a : (a & ~(1UL << alias_bit)); }

static unsigned long AwtoMs(void) { return ms_now++; }
static unsigned drw_rd(unsigned r)
{
    if(r == AWTO_R_MCU_DC_CMD_A)
    {
        if(busy_after < 0) return 0x80;
        if(busy > 0) { busy--; return 0x80; }
        return 0;
    }
    if(r == AWTO_R_MCU_DC_READ_FLAG_A) return rflag;
    if(r >= AWTO_R_MCU_DC_DATABUF_R_00_A && r < AWTO_R_MCU_DC_DATABUF_R_00_A + 16)
    {
        if(r == AWTO_R_MCU_DC_DATABUF_R_00_A + 15) rflag = 0;
        return rbuf[r - AWTO_R_MCU_DC_DATABUF_R_00_A];
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
        if(v == HOST_CMD_READ)
        {
            int k;
            unsigned long ae = aeff(a);
            memcpy(prev, rbuf, 16);
            for(k = 0; k < 16; k++) rbuf[k] = mem[8 * ae + ((k + 8 * rdswap) & 15)];
            if(stuck >= 0) rbuf[((stuck / 8) + 8 * rdswap) & 15] |= (unsigned char)(1u << (stuck % 8));
            nreads++;
            if(stale_every > 0 && (nreads % stale_every) == 0) memcpy(rbuf, prev, 16);
            rflag = 1;
            busy = busy_after;
            return;
        }
        if(regs[AWTO_R_MCU_DC_LEN_A] != 2 || a + 2 > UNITS) { hazards++; return; }
        for(j = 0; j < 16; j++)
            if(!((mask >> j) & 1)) mem[8 * aeff(a) + ((j + 8) & 15)] = regs[AWTO_R_MCU_DC_DATABUF_W_00_A + j];   /* halves swapped */
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
StAwtoAddr g_stAwtoAddr;

int main(int argc, char **argv)
{
    char line[256];
    busy_after = argc > 1 ? atol(argv[1]) : 0;
    alias_bit = argc > 2 ? atoi(argv[2]) : -1;
    stuck = argc > 3 ? atoi(argv[3]) : -1;
    rdswap = argc > 4 ? atoi(argv[4]) : 0;
    stale_every = argc > 5 ? atoi(argv[5]) : 0;
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
        else if(strncmp(line, "set ", 4) == 0)
        {
            unsigned long b0, nb, sd; unsigned st, sm, iv, sw, rt, sa;
            if(sscanf(line, "set %lu %lu %lu %u %u %u %u %u %u", &b0, &nb, &sd, &st, &sm, &iv, &sw, &rt, &sa) == 9)
            {
                g_stAwtoAddr.ulBlk0 = b0; g_stAwtoAddr.ulBlocks = nb; g_stAwtoAddr.ulSeed = sd; g_stAwtoAddr.usStride = st; g_stAwtoAddr.usStepMs = sm;
                g_stAwtoAddr.ucInv = iv; g_stAwtoAddr.ucSwap = sw; g_stAwtoAddr.ucRetry = rt; g_stAwtoAddr.ucSamples = sa;
            }
        }
        else if(strncmp(line, "addr", 4) == 0)
        {
            int k;
            printf("checked %lu bad %lu stale %lu shift %lu data %lu tmo %lu spin %lu slow %lu bits", g_stAwtoAddr.ulChecked, g_stAwtoAddr.ulBad, g_stAwtoAddr.ulStale, g_stAwtoAddr.ulShift, g_stAwtoAddr.ulData, g_stAwtoAddr.ulTmo, g_stAwtoAddr.ulSpin, g_stAwtoAddr.ulSlow);
            for(k = 0; k < AWTO_DRW_IDX_BITS; k++) printf(" %lu", g_stAwtoAddr.aulBit[k]);
            printf(" rec %u", g_stAwtoAddr.ucRecN);
            for(k = 0; k < g_stAwtoAddr.ucRecN; k++) printf(" %lu", g_stAwtoAddr.aulRecIdx[k]);
            printf("\nwatch");
            for(k = 0; k < AWTO_DRW_WATCH_N; k++) printf(" %u", g_stAwtoAddr.ausWatch[k]);
            printf("\n");
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
