/* LD_PRELOAD shim for ucsim_51 (fw_sim.py, #38): cl_app::run_nogo calls msleep(100) whenever no console input is
 * pending and the process is older than 2 s, so every command round trip costs 100 ms. A 100 ms nanosleep becomes 50 us. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <time.h>

int nanosleep(const struct timespec *req, struct timespec *rem)
{
    static int (*real)(const struct timespec *, struct timespec *);
    struct timespec s = {0, 50000};
    if (!real)
        real = (int (*)(const struct timespec *, struct timespec *))dlsym(RTLD_NEXT, "nanosleep");
    if (req->tv_sec == 0 && req->tv_nsec == 100000000L)
        return real(&s, rem);
    return real(req, rem);
}
