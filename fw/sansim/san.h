/* T0 reload with a varying period (129..256 cycles) so the IRQ phase walks across the main loop */
#define RELOAD() do { static __data unsigned char r_; r_ = (r_ << 2) + r_ + 3; TH0 = 0xFF; TL0 = r_ & 0x7F; } while (0)
