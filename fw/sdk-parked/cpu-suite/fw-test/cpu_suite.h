#ifndef AWTO_CPU_SUITE_H
#define AWTO_CPU_SUITE_H
// CPU / interrupt / timer / memory conformance suite (docs/cpu-suite.md). Only the CPU suite image (-D _AWTO_CPU_SUITE) compiles cpu_suite.c.
// Guard-byte helper: reusable overflow detector for a fixed XDATA buffer (fill the bytes around it, check them afterwards).
#define AWTO_GUARD_SEED_LO                      0xA7                // guard byte n = seed ^ n: a copy shifted by one byte does not look intact
#define AWTO_GUARD_SEED_HI                      0x59
extern void AwtoGuardFill(volatile __xdata unsigned char *pucG, unsigned char ucLen, unsigned char ucSeed);
extern unsigned char AwtoGuardCheck(volatile __xdata unsigned char *pucG, unsigned char ucLen, unsigned char ucSeed);   // bytes changed
#endif
