/* cc.h: compiler shims. SDCC builds use its memory-space keywords; host test builds (gcc) drop them. */
#ifndef AWTO_CC_H
#define AWTO_CC_H

#ifndef __SDCC
#define __xdata
#define __code
#define __data
#define __idata
#endif

/* placement intent for the awto-ddc build (scripts/place_rules.py, awto-ddc#149); nothing for the compiler */
#define AWTO_PLACE(...)

#endif
