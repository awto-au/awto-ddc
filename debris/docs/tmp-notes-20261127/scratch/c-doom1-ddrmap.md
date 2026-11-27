🤖 DDR map review: awto-au/awto-ddc#348. Points for Doom:
- There are two 32 MiB chips. Port A is chip A, port B is chip B.
- Every current Doom DDR address (0x80010 to 0x800010, bytes) sits inside capture block 1 on chip A, which capture rewrites every frame unless frozen. Any mode set clears the freeze.
- Free in every 1- or 2-buffer mode:
  - A 0x3B5380-0x3EBFFD units (1,795,056 B).
  - B 0x3B5380-0x3FFFFF units (2,450,432 B).
- In the current mode only: A from 0x17BB00 (20.4 MB) and B from 0x17BB00 (21.1 MB).
- `scripts/ddr_sim.py:9` ("both ports share logical RAM") is wrong: two chips.
- Next: relocate Doom's layout out of block 1; run the retention test (#348 open item 2) before relying on any region.
