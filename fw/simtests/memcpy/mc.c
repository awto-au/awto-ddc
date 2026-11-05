/* separate TU: SDCC infers register use of same-TU callees, an extern naked asm fn is assumed to clobber all */
#include "../../sdcc/crt_memcpy.c"
