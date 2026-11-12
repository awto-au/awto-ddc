/* Keil C51 -> SDCC compatibility, force-included by scripts/fw_compile.py. Tracking: awto-ddc#8.
 * Only keywords that are never ordinary identifiers in the SDK are macros here; `code`/`data`
 * are rewritten in declarator position by the port script instead. */
#ifndef KEIL_COMPAT_H
#define KEIL_COMPAT_H

#define xdata  __xdata
#define idata  __xdata   /* stack needs all of 0x80-0xFF (awto-ddc#8) */
#define pdata  __pdata
#define bdata  __data          /* SDCC has no bit-addressable qualifier; see #8 if bit access is needed */
#define bit    __bit
#define small
#define compact
#define large
#define reentrant __reentrant

/* SDK calls abs()/memcpy()/... with no #include (Keil accepts implicit decls; SDCC then sees 0 params) */
#include <stdlib.h>
#include <string.h>

#endif
