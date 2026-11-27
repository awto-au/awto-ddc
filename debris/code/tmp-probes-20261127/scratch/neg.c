#include <stdio.h>
#include "osd_lines.h"
static uint8_t px[OSD_BITMAP_BYTES(1,2)], dr[OSD_DIRTY_BYTES(1,2)];
static void dump(osd_canvas*c){int n=0;for(int y=0;y<36;y++)for(int x=0;x<12;x++){int t=y/18,b=(y%18)*12+x;if(c->pixels[t*OSD_TILE_BYTES+(b>>3)]&(0x80>>(b&7)))n++;}printf("lit=%d\n",n);}
int main(void){osd_canvas c;
 osd_canvas_init(&c,1,2,px,sizeof px,dr,sizeof dr);osd_clear(&c);
 osd_line(&c,5,-30,5,10,1);dump(&c);          /* expect 11 px (y 0..10) */
 osd_clear(&c);osd_line(&c,5,0,5,10,1);dump(&c);  /* reference 11 */
 osd_clear(&c);osd_line(&c,-1,5,3,5,1);dump(&c); /* expect 4 (x 0..3) */
 return 0;}
