#include <stdint.h>
#define OSD_NO_FLUSH
#include "osd_lines.c"
#define AWTO_SC_SINE_N 64
#define AWTO_SC_SINE_MASK 63
#define AWTO_SC_AMP1 62
#define AWTO_SC_AMP2 28
#define AWTO_SC_SINE_SHIFT 7
#define AWTO_SC_H2_PER_PX 4
#define AWTO_SC_H2_PH 2
#define AWTO_SC_MID_Y 108
#define TW 12
#define BH 108
static const int8_t s_tSine[AWTO_SC_SINE_N] = {
    0, 12, 25, 37, 49, 60, 71, 81, 90, 98, 106, 112, 117, 122, 125, 126,
    127, 126, 125, 122, 117, 112, 106, 98, 90, 81, 71, 60, 49, 37, 25, 12,
    0, -12, -25, -37, -49, -60, -71, -81, -90, -98, -106, -112, -117, -122, -125, -126,
    -127, -126, -125, -122, -117, -112, -106, -98, -90, -81, -71, -60, -49, -37, -25, -12};
static __xdata uint8_t px[OSD_BITMAP_BYTES(1,6)];
static __xdata uint8_t dr[OSD_DIRTY_BYTES(1,6)];
static __xdata osd_canvas c;

      /* [0] columns*bands that differ, [1] first (col<<8|band) */
static int16_t ScY(int16_t sX, uint8_t ucPh)
{
    int16_t sV1 = ((int16_t)s_tSine[(sX + ucPh) & AWTO_SC_SINE_MASK] * AWTO_SC_AMP1) >> AWTO_SC_SINE_SHIFT;
    int16_t sV2 = ((int16_t)s_tSine[(sX * AWTO_SC_H2_PER_PX + ucPh * AWTO_SC_H2_PH) & AWTO_SC_SINE_MASK] * AWTO_SC_AMP2) >> AWTO_SC_SINE_SHIFT;
    return AWTO_SC_MID_Y - sV1 - sV2;
}
#include <stdio.h>
static char img[216][384];
void main(void){
 uint8_t col,band; int16_t ox,oy,x,prev,cur,y,xx; uint16_t t;
 osd_canvas_init(&c,1,6,px,sizeof px,dr,sizeof dr);
 for(band=0;band<2;band++) for(col=0;col<32;col++){
   ox=(int16_t)col*TW; oy=(int16_t)band*BH;
   osd_clear(&c);
   prev=ScY(ox-(ox>0?1:0),6);
   for(x=ox+(ox>0?0:1);x<ox+TW;x++){cur=ScY(x,6);osd_line(&c,x-1-ox,prev-oy,x-ox,cur-oy,1);prev=cur;}
   for(y=0;y<BH;y++)for(xx=0;xx<TW;xx++){int tl=y/18,b=(y%18)*12+xx; if(px[tl*OSD_TILE_BYTES+(b>>3)]&(0x80>>(b&7))) img[oy+y][ox+xx]=1;}
 }
 for(y=100;y<130;y++){printf("%3d ",y);for(xx=14;xx<40;xx++)putchar(img[y][xx]?'#':'.');puts("");}
}
