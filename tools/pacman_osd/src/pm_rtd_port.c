#include "pm_osd.h"
/* Bind pm_bus_write to the project's INTERNAL scaler-register API, not an
 * uncoordinated host ISP session. All calls must share the OSD owner's lock.
 * SRAM 12288 words (SDK constant), word addressing, all byte planes, M1+M2. */
void pm_rtd_word(uint16_t address, uint8_t b0, uint8_t b1, uint8_t b2)
{
    if (address >= 12288U) return;
    pm_bus_write(0x0094, 0xE8);
    pm_bus_write(0x0090, (uint8_t)(address >> 8));
    pm_bus_write(0x0091, (uint8_t)address);
    pm_bus_write(0x0092, b0);
    pm_bus_write(0x0092, b1);
    pm_bus_write(0x0092, b2);
}
