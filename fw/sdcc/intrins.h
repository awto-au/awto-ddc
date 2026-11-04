/* Keil <intrins.h> for SDCC. Tracking: awto-ddc#8. */
#ifndef INTRINS_H
#define INTRINS_H

#define _nop_()  __asm nop __endasm
#define _crol_(c, n)  ((unsigned char)(((unsigned char)(c) << ((n) & 7)) | ((unsigned char)(c) >> ((8 - ((n) & 7)) & 7))))
#define _cror_(c, n)  ((unsigned char)(((unsigned char)(c) >> ((n) & 7)) | ((unsigned char)(c) << ((8 - ((n) & 7)) & 7))))
#define _irol_(i, n)  ((unsigned int)(((unsigned int)(i) << ((n) & 15)) | ((unsigned int)(i) >> ((16 - ((n) & 15)) & 15))))
#define _iror_(i, n)  ((unsigned int)(((unsigned int)(i) >> ((n) & 15)) | ((unsigned int)(i) << ((16 - ((n) & 15)) & 15))))
#define _lrol_(l, n)  ((unsigned long)(((unsigned long)(l) << ((n) & 31)) | ((unsigned long)(l) >> ((32 - ((n) & 31)) & 31))))
#define _lror_(l, n)  ((unsigned long)(((unsigned long)(l) >> ((n) & 31)) | ((unsigned long)(l) << ((32 - ((n) & 31)) & 31))))
#define _testbit_(b)  _keil_testbit(&(b))   /* unresolved: needs a JBC helper, see #8 */

#endif
