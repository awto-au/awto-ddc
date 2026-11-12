# Unused GPIO diagnostics

The GPIO diagnostic covers only package pins that the board ledger identifies
as unused: 65, 66, 67, 68, 69, 70, 74, 75, and 96. The firmware configures
them as high-impedance inputs; it does not enable unknown pins or drive any of
these pins.

Pin 96 is configured as the otherwise-unused low-speed `A-ADC2` input. The
screen and I2C snapshot report its raw 8-bit result and nominal voltage using
a 3.3 V full-scale reference.

While the diagnostic screen is open, the firmware also powers the otherwise
unused VGA analogue front end and displays one row for each fixed input pin:
AVS, AHS, B-/B+, G-/G+, SOG, and R-/R+. These rows expose the raw scaler sync
and comparator registers. They are useful for detecting transitions and
testing the front end, but they are not DC voltage measurements: the VGA RGB
inputs are high-speed differential video inputs, not general-purpose ADCs.
Closing the screen powers this experimental front end down again.

The same sampler also reports SOURCE, MENU, DOWN, UP, AUTO, and POWER. The
first five are decoded directly from the two ADC button ladders; POWER is read
from P3.0. Their normal actions are suppressed while the diagnostic screen is
open, so they can all be tested without navigating menus or powering down.
Each button has its own OSD row; ADC-ladder rows show state, channel, raw
count, and nominal voltage.

The sampler runs once per firmware main-loop pass. It stores the current eight
digital GPIO, spare ADC2, and six button states, a bitmap of inputs that have
changed since boot, plus the raw VGA status and the most recent 32 digital/key
transitions. Each transition records its sequence number, firmware
millisecond tick, package-pin index, and new state.  The live OSD redraws only
when a value changes and is rate-limited to one redraw per 20 ms.

Use the serial-guarded development commands:

```sh
./dev.py gpio --unit 2 snapshot
./dev.py gpio --unit 2 watch
./dev.py gpio --unit 2 --secs 60 watch
./dev.py gpio --unit 2 open
./dev.py gpio --unit 2 close
```

`watch` normally reads only the 20-byte header. When the sequence changes it
reads the complete ring and prints one line per transition.  Therefore I2C
traffic remains small while the pins are idle, without losing short changes
that occur between host polls.

The same screen is available from the firmware menu as **GPIO inputs**.  The
I2C open and close commands use diagnostic test commands `0x43` and `0x44`.
The exact XDATA address is resolved from the matching image map rather than
being hard-coded.
