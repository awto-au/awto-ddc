#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "emu8051.h"
static struct em8051 cpu;
static unsigned char code[65536], xram[65536], upper[128];
static unsigned long ticks, instructions;
static int done, failed;
static FILE *trace;
static void exception(struct em8051 *c,int n) { (void)c;fprintf(stderr,"8051 exception %d\n",n);failed=1; }
static void write_x(struct em8051 *c,uint16_t a,uint8_t v)
{
    c->mExtData[a]=v;
    if(a==0xF002){done=v==255;return;}
    if(a==0xF001){
        unsigned int f=c->mExtData[0xF000]*256+v;
        fprintf(trace,"F %d\n",f==65535?-1:(int)f);
        fprintf(trace,"S %lu %lu\n",instructions,ticks);return;
    }
    if(a<0xF000)fprintf(trace,"R %u %u\n",(unsigned)a,(unsigned)v);
}
int main(int argc,char **argv)
{
    FILE *f;size_t n;
    if(argc!=3)return 2;
    f=fopen(argv[1],"rb");if(!f)return 3;
    n=fread(code,1,sizeof code,f);fclose(f);if(!n)return 4;
    trace=fopen(argv[2],"w");if(!trace)return 5;
    memset(&cpu,0,sizeof cpu);cpu.mCodeMem=code;cpu.mCodeMemMaxIdx=65535;
    cpu.mExtData=xram;cpu.mExtDataMaxIdx=65535;cpu.mUpperData=upper;
    reset(&cpu,0);cpu.except=exception;cpu.xwrite=write_x;
    while(!done && !failed && ticks<5000000UL){++ticks;if(tick(&cpu))++instructions;}
    fclose(trace);
    if(!done || failed || cpu.mSFR[REG_SP]!=0x60){fprintf(stderr,"8051 app failed/stalled at %04X\n",cpu.mPC);return 6;}
    printf("8051 app executed: %lu instructions, %lu emulator ticks; stack restored\n",instructions,ticks);
    return 0;
}
