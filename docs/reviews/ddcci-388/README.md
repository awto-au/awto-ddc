# DDC compatibility #388: original baseline evidence

See [the full review](../../ddcci-compatibility-review.md) for current status,
the compatibility matrices and approved follow-up.

These files preserve the original offline check against awto-ddc main
ce8e1625f5c168f67f0f28145395f2bee448f5f0. They have not been rerun at cac1c66f.
The old branch/PR inventory in revision-evidence.json is explicitly historical.

Run against an existing checkout of the original revision:

```sh
python3 run_baseline.py /path/to/awto-ddc
```

The harness compiles the checkout's actual vcp.c and generated set_table.c with
a mocked settings backend/menu. Original result: 1,580 checks, zero failures.
It verifies the baseline mapping, not I2C timing, physical switching, LUT output,
NVRAM persistence or the proposed new interface. See the review for the required
full-image simulator cases.
