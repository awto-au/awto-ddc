## Context
- Two faults in `ScalerDisplayDPTx1AuxRead` / `ScalerDisplayDPTx2AuxRead` (Realtek SDK source), fixed in 7b45605 -> f6dba6f.
- Symptom: ~1 in 3 boots at 350.8 MHz MCU lost the picture; the eDP "link training FAIL" line.

## Faults
- **Bug 1, buffer overrun:** copies `FIFO_WR_PTR[4:0]` bytes (up to 31) into the caller buffer without comparing with the request.
  - Callers pass a 16-byte buffer at XDATA 0xF63D; a longer reply overwrites 0xF64D onward, including `g_pucSourceSearchPriority` at 0xF65B.
- **Bug 2, length underflow:** on a partial reply the running offset is subtracted from an already reduced length.
  - After two partial replies it underflows and re-issues a 16-byte request; the wrong lane status feeds link training.
- Fix: remaining request = total - offset; over-long replies are retried.

## Static analysis
- Both are plain bounds / unsigned-arithmetic faults; a static-analysis pass should have flagged them.
- Add both functions on the pre-fix source (tag before 7b45605) as required test cases for the gate in #186; the SDK bug list is #100.

Related: #100, #186.
