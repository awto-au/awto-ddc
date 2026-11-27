Title: dev.py gate fails at its test step on main: 37 pre-existing pytest failures

🤖 Found 2026-11-13 while fixing #177/#179 (branch tools-flash). `./dev.py gate` runs test, then build. On main b3a1057 the test step fails before build runs: `pytest -q tests` gives 37 failed, 202 passed, 12 skipped. tools-flash has the same 37 and no new ones.

By file:
- test_dev_hw_args.py (13): the subprocess `dev.py ... --unit 3` calls now hit "unit 3 is a working screen" (devices.json test=false). The tests expect the argument error to come first.
- test_rtd_proto.py (6), test_unit_health.py (5), test_settings_table.py (3: `KeyError: 'logo'`, generated files not current), test_sdcc_link.py (4: AttributeError on a module attribute).
- test_dev_tool_hazards.py (4):
  - relay so-th-1 now feeds unit 2, not unit 3
  - mode --dp
  - SIGHUP handler
  - archived image
- test_cleanroom_tools.py (1): `keil2sdcc` was removed in 1e89f72 (#162).
- test_i2c_single_layer.py (1).

Effect: the gate cannot block a commit, so agents run test subsets instead.
Log: /mnt/2tb/git/awto-ddc-flash/tmp/logs/gate_check.out
