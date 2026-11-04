/* multi-file: same-named statics in a.c/b.c, global vs local with same names */
#include "sim.h"
#include "mf.h"
unsigned char shared_g = 10;
void main(void)
{
    unsigned char counter = 4;           /* local named like others' globals/statics */
    unsigned int r = 0;
    r += a_entry(counter);
    r += b_entry(counter);
    r += a_entry(counter + 1);
    sim_val("r", r);
    sim_val("g", shared_g);
    sim_done();
}
