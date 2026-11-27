🤖 **New question (from #144, 2026-11-12): should a DP AUX command alone still wake the monitor from power saving?**
- Context: with the SDK self-wakes fixed (tmds5, #144 comment 6811790646), the only thing ending power saving on unit 2 with all host outputs off is our own D1 trigger, `D1 AUX command from source: wake`. It fired after 23.7 s. The host's DP-1 is connected but not on the desktop, and its driver sends an AUX command while asleep. Each such wake lights the console + backlight.
- Options:
  1. Keep (task 4 as decided): any AUX command wakes, once per sleep (until a picture).
  2. **Drop the AUX-command trigger; DPCD 600h = D0 (the source powering the link) and the SDK link-training checks still wake.** A real DP host wake writes 600h = D0 first. Test image tmds6 (`-D _AWTO_PS_AUX_WAKE=_OFF`) does this and logs the AUX as `AUX command from source in power saving: no wake`.
  3. AUX only when no other port has a cable.
- Recommendation: 2. Unit-2 result of tmds6 to follow on #144.
