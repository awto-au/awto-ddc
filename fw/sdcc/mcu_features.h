/* Optional DW8051 CPU diagnostic. Never called by the normal firmware build.
 * Caller owns all 16 XDATA bytes and at least 18 free internal stack bytes.
 * Call with DPS.0 = 0, from main/startup, never from an ISR.
 * Byte-only record: identical layout in little- and big-endian builds.
 */
#ifndef AWTO_MCU_FEATURES_H
#define AWTO_MCU_FEATURES_H

#define AWTO_MCU_FEATURES_SIZE 16
void AwtoMcuFeatures(volatile unsigned char __xdata *record) __sdcccall(0);

#endif
