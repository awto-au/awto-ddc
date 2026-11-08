# Spec: dpphycts  (step 12, #65): DP RX PHY compliance test patterns from the public DP spec
Status: TO WRITE (Opus: DP PHY). Kept (Dan 2026-11-07).

## Sources
- Test patterns and DPCD test registers (TEST_REQUEST, PHY_TEST_PATTERN, ...) from the VESA DisplayPort spec / public CTS docs:
  tag `derived`.
- PHY register settings per pattern: facts + reference behaviour (`measured` traces), `sdk-value` where only the SDK says.

## Oracle
- fw_sim_dp: DPCD test request -> register sequence (`.equiv` rules); hardware with a DP source that can request PHY tests.
