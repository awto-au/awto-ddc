#include <assert.h>
#include <stdio.h>
#include "pm_osd.h"
#include "pm_assets.h"
static FILE *out;
void pm_bus_write(uint16_t r,uint8_t v) { fprintf(out,"R %u %u\n",(unsigned)r,(unsigned)v); }
void pm_hw_word(uint16_t a,uint8_t b0,uint8_t b1,uint8_t b2) { pm_rtd_word(a,b0,b1,b2); }
int main(int argc,char **argv)
{
    unsigned int f,i,x,y,pos,dir;
    static const uint8_t colors[5]={3,5,6,7,8};
    if(argc!=2)return 2;
    out=fopen(argv[1],"w");if(!out)return 3;
    fputs("F -1\n",out);pm_load();
    for(f=0;f<96;++f){
        fprintf(out,"F %u\n",f);
        for(i=0;i<5;++i){
            pos=(f*3+i*210)%1296;
            if(pos<300){x=12+pos;y=48;dir=0;}
            else if(pos<648){x=312;y=48+pos-300;dir=1;}
            else if(pos<948){x=312-(pos-648);y=396;dir=2;}
            else{x=12;y=396-(pos-948);dir=3;}
            assert(pm_actor_smooth((uint8_t)i,(uint16_t)x,(uint16_t)y,
                (uint8_t)(i?8+dir:dir*2+(f/4)%2),colors[i],1));
            if(i==0)pm_eat((uint8_t)((x+6)/12),(uint8_t)((y+6)/12));
        }
        pm_flush();
    }
    if(fclose(out))return 4;
    return 0;
}
