#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "pm_osd.h"
#include "pm_assets.h"
static unsigned char ram[12288][3];
static unsigned int writes;
void pm_hw_word(uint16_t a, uint8_t b0, uint8_t b1, uint8_t b2)
{
    assert(a < 12288); ram[a][0]=b0; ram[a][1]=b1; ram[a][2]=b2; ++writes;
}
static unsigned int gid(unsigned int x,unsigned int y)
{
    unsigned int a=PM_FS_BASE+y*PM_COLS+x;
    return ram[a][1]+((ram[a][0]&32)?256:0);
}
int main(void)
{
    unsigned int i,x,y,old,n,maxg=0;
    pm_load();
    assert(writes==PM_SRAM_WORDS);
    assert(ram[PM_ROWS][0]==0 && ram[0][1]==PM_CELL_H-1);
    for(i=0;i<PM_GLYPHS*27U;++i) assert(ram[PM_FONT_BASE+i/3][i%3]==pm_glyph_bytes[i]);
    for(y=0;y<PM_ROWS;++y)for(x=0;x<PM_COLS;++x)assert(gid(x,y)==pm_initial_map[y*PM_COLS+x]);
    writes=0;
    assert(pm_actor(0,1,4,PM_G_PAC_0_3,3,1)); pm_flush(); assert(writes==1);
    writes=0; assert(pm_actor(0,1,4,PM_G_PAC_0_3,3,1)); pm_flush(); assert(writes==0);
    assert(pm_actor(0,2,4,PM_G_PAC_0_0,3,1)); pm_flush();
    assert(gid(1,4)==PM_G_POWER); assert(gid(2,4)==PM_G_PAC_0_0);
    assert(pm_eat(2,4)); pm_flush(); assert(gid(2,4)==PM_G_PAC_0_0);
    assert(pm_actor(0,2,4,PM_G_PAC_0_0,3,0)); pm_flush(); assert(gid(2,4)==PM_G_BLANK);
    writes=0;
    assert(!pm_actor(5,0,0,0,1,1)); assert(!pm_actor(0,28,0,0,1,1));
    assert(!pm_actor(0,0,0,PM_GLYPHS,1,1)); assert(!pm_background(0,0,PM_BASE_GLYPHS));
    assert(!pm_actor_smooth(0,1,0,0,3,1)); assert(!pm_actor_smooth(0,0,0,PM_PHASE_FRAMES,3,1));
    assert(!pm_actor_smooth(0,PM_COLS*12,0,0,3,1)); pm_flush(); assert(writes==0);
    /* Every cached phase, including ids above 255, through the C renderer. */
    for(i=0;i<PM_PHASE_FRAMES;++i)for(y=0;y<4;++y)for(x=0;x<4;++x){
        assert(pm_actor_smooth(0,12+x*3,48+y*3,(uint8_t)i,3,1));
        writes=0; pm_flush(); assert(writes<=8);
        for(n=0;n<4;++n){
            unsigned int g=pm_phase_glyph[i*64+(y*4+x)*4+n];
            if(g) { assert(gid(1+n%2,4+n/2)==g); if(g>maxg)maxg=g; }
        }
    }
    assert(maxg>255);
    /* Exhaust the dirty list: explicit full redraw must retain the last state. */
    assert(pm_actor(0,0,0,PM_G_PAC_0_0,3,0)); pm_flush(); writes=0;
    for(i=0;i<100;++i) assert(pm_background((uint8_t)(i%28),(uint8_t)(i/28),PM_G_DOT));
    pm_flush(); assert(writes==PM_CELLS);
    for(i=0;i<100;++i)assert(gid(i%28,i/28)==PM_G_DOT);
    /* Two actors in the same cell, then reveal the lower one. */
    assert(pm_actor(0,10,10,PM_G_PAC_0_0,3,1));
    assert(pm_actor(1,10,10,PM_G_GHOST_0_0,5,1)); pm_flush();
    assert(gid(10,10)==PM_G_GHOST_0_0);
    assert(pm_actor(1,10,10,PM_G_GHOST_0_0,5,0)); pm_flush();
    assert(gid(10,10)==PM_G_PAC_0_0);
    /* Reload is a state reset, not a stale actor overlay. */
    old=writes; pm_load(); assert(writes-old==PM_SRAM_WORDS);
    for(i=0;i<PM_CELLS;++i)assert(gid(i%28,i/28)==pm_initial_map[i]);
    puts("native checks passed: SRAM layout, restoration, occlusion, phase IDs, bounds, dirty overflow, reload");
    return 0;
}
