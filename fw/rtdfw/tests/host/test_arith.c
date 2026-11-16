/* test_arith.c: host test for awto/arith/arith.c against spec arith, all rows of a vectors file.
 * Build and run from the repo root:
 *   gcc -std=gnu11 -Wall -Wextra -Iawto/include tests/host/test_arith.c awto/arith/arith.c -o tmp/test_arith
 *   tmp/test_arith tests/vectors/arith.tsv */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "arith.h"

int main(int argc, char **argv)
{
    const char *path = argc > 1 ? argv[1] : "tests/vectors/arith.tsv";
    FILE *f = fopen(path, "r");
    char line[256];
    long rows = 0, fails = 0;

    if (!f) {
        printf("cannot open %s\n", path);
        return 2;
    }
    while (fgets(line, sizeof line, f)) {
        char fn[16];
        unsigned long a, b, c, want;
        uint32_t got;

        if (line[0] == '#' || line[0] == '\n')
            continue;
        if (sscanf(line, "%15s %lx %lx %lx %lx", fn, &a, &b, &c, &want) != 5) {
            printf("bad row: %s", line);
            fails++;
            continue;
        }
        rows++;
        if (strcmp(fn, "muldiv") == 0) {
            got = ar_muldiv((uint32_t)a, (uint32_t)b, (uint32_t)c);
        } else if (strcmp(fn, "shldiv") == 0) {
            got = ar_shldiv((uint32_t)a, (uint8_t)b, (uint32_t)c);
        } else {
            printf("unknown fn: %s", line);
            fails++;
            continue;
        }
        if (got != (uint32_t)want) {
            fails++;
            printf("FAIL %s %08lX %08lX %08lX: got %08lX want %08lX\n", fn, a, b, c,
                   (unsigned long)got, want);
        }
    }
    fclose(f);
    printf("test_arith: %ld rows, %ld failures\n", rows, fails);
    return fails ? 1 : 0;
}
