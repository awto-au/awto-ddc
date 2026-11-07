# Spec: gamma  (step 8 data, #65): output gamma LUTs generated from maths
Status: TO WRITE (Sonnet). Kept (Dan 2026-11-07); replaces the 4 vendor LUTs (gamma 1.8 / 2.0 / 2.2 / 2.4, 6156 B each).

## Sources
- LUT format (entries, bit depth, packing, channel order) from facts + the reference load sequence: tag `derived` / `measured`.
- Values: our formula (power law, optional sRGB/BT.1886 variants), tag `derived`. Vendor table values are NOT copied;
  they are used only as a check (max error, monotonicity) on the spec side.

## Oracle
- Generator script output (host) vs vendor tables: report max |diff| per entry; accept by eye on unit 3 (photo, gamma pattern).
- Load sequence: `trace_equiv.py` rules for the LUT port (burst shape, not values).
