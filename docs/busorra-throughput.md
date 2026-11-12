# Busorra host throughput (#80)

## Evidence and limits

Busorra already carries SLIP Ethernet frames, ARP, ICMP, UDP services and Linux TAP traffic.
The existing network implementation and firmware are retained.

- [Unit 3 hardware measurements](https://github.com/awto-au/awto-ddc/issues/80#issuecomment-6715078111):
  600 B loopback, 100 kHz debug transport: 12 B writes 248 ms / 2417 B/s;
  27 B writes 174 ms / 3449 B/s, 35 exchanges, zero retries/full. About 43% higher measured throughput.
- [Unit 2 DDC/CI validation](https://github.com/awto-au/awto-ddc/issues/80#issuecomment-6716137339):
  stack 13/13, routed TAP ping 5/5, UDP info working.
- [Runtime switching #79](https://github.com/awto-au/awto-ddc/issues/79#issuecomment-6715270002)
  uses VCP **E3**, not the earlier E8 mapping. Leave `dbg_link.py`, its timeout and park-before-move behavior intact.
- Protocol checked against `wb-p14swap` commit `194116adc23bffc077a031ef341173b600c78d7e`,
  `fw/sdcc/awto_dbgisr.inc` and `awto_net.inc` (those files are not on host main).

Both slaves share two 128 B rings and one 300 B Ethernet frame buffer. Only one transport/client may own
a monitor's Busorra session. Debug 0x35 has a 27 B write ceiling and fixed 25 B replies carrying up to 20 B;
DDC/CI 0x37 has a 10 B write ceiling and up to 9 B of reply data. Neither ceiling is increased.
Chunks respect both the current write size and the monitor's advertised RX free space.

## Policy and failure handling

- Default debug mode stays fixed at **12 B**. DDC/CI stays fixed at **10 B**.
  Explicit `--wmax 1..27` (debug) / `1..10` (DDC/CI) remains available; invalid values now fail before I/O.
- `--adaptive` is an explicit debug-only experiment, mutually exclusive with `--wmax`.
  Each Pipe starts at 12 B. After 32 consecutive accepted writes using the full current size, it tries 20 B;
  another 32 promotes it to 27 B. Short writes, idle polls and FULL replies break the streak.
  The 32-write threshold is a conservative policy choice, not a hardware-derived reliability threshold.
- Any failed write/read, short/malformed/checksum-invalid reply, or verified BAD reply locks that Pipe to 12 B
  for its remaining lifetime. No automatic re-promotion or persisted capability cache.
  FULL alone is backpressure; it does not establish a write-size incompatibility.
- **An uncertain request is never shortened.** All four attempts retain the identical sequence, control,
  previous reply ACK and complete data. A recovered ACC consumes the original whole chunk exactly once;
  FULL applies the ACK but leaves the entire outgoing chunk queued. A verified BAD applies neither
  **on that attempt**. BAD is checked before dedup in firmware: after an earlier lost reply, BAD cannot
  disprove earlier acceptance. Continue identical retries until ACC/FULL resolves it, or stop.
  Only subsequent requests use the smaller size, or re-chunk data confirmed unaccepted by a first-attempt
  BAD or resolved FULL.
- After four unanswered attempts, acceptance is unknown. Pipe latches a failure and the daemon exits through
  TAP cleanup instead of continuing with a fresh sequence. This also fixes the previous daemon's unsafe
  catch-and-continue behavior after retry exhaustion. An explicit reset can discard the session and restart
  at 12 B, but automatic reset would lose in-flight Ethernet data and is deliberately not a recovery policy.

Thus intermittent errors with recoverable replies and unambiguous BAD can fall back safely. A controller that
permanently refuses oversized transfers without a usable reply **cannot fall back transparently with this
firmware protocol**: it cannot distinguish an unaccepted write from an accepted write whose reply vanished.
Use default 12 B for that controller. This change does not claim universal compatibility detection.

Reply validation now also bounds RX credit, DDC/CI reply length and contradictory acceptance flags.
SLIP keeps the same wire encoding; the host drops invalid escapes, dangling escapes and decoded frames
over 300 B, and resynchronizes at END. Link checksums remain unchanged. This does not add an end-to-end CRC
or claim to detect every checksum collision or arbitrary valid-looking payload corruption.

## Software validation and overhead comparison

From the repository root, no hardware or extra Python packages are needed:

```sh
python -m unittest discover -s tests -p test_ddcnet.py -v
python tests/ddcnet_model.py
python -m py_compile scripts/ddcnet.py tests/ddcnet_model.py tests/test_ddcnet.py
git diff --check
```

21 tests cover defaults, growth/short-write streaks, RX FULL/zero credit, queue preservation,
ACK application, NAK/BAD, dropped/short/corrupt/stale/malformed replies on both transports,
identical retry payloads, BAD after a lost acceptance reply, permanent incompatibility, all replies lost after acceptance,
sequence wrap, SLIP escape boundaries and bounded resynchronization, daemon fail/cleanup and CLI guards.
The existing `--drop` harness also exercises deterministic reply loss.

`tests/ddcnet_model.py` supplies a deterministic I/O backend to the **existing `ddcnet.loopback` harness**.
It is a protocol model, not `fw_sim`: it models rings, sequence dedup, ACKs, one echo pass per exchange
and 9 clock periods per requested I2C byte at 100 kHz. It does not model FIFO overrun, ISR scheduling,
clock stretching, video modes, controller latency or runtime channel switching.

| Payload | Policy | Exchanges | Requested I2C bytes | Duplex payload / requested bytes | Model B/s each way |
|---|---|---:|---:|---:|---:|
| 600 B | fixed 12 | 51 | 2334 | 51.4% | 2856 |
| 600 B | fixed 27 | 31 | 1654 | 72.6% | 4031 |
| 600 B | adaptive | 44 | 2096 | 57.3% | 3181 |
| 600 B | DDC/CI 10 | 68 | 2300 | 52.2% | 1460 |
| 60,000 B | fixed 12 | 5001 | 230034 | 52.2% | 2898 |
| 60,000 B | fixed 27 | 3001 | 162034 | 74.1% | 4114 |
| 60,000 B | adaptive | 3014 | 162476 | 73.9% | 4103 |
| 60,000 B | DDC/CI 10 | 6668 | 226700 | 52.9% | 1485 |

All model comparisons return exact payload bytes, zero retries/full/BAD. At 60,000 B adaptive reduces
requested bus bytes by 29.4% versus default 12, after its warm-up. These rates are **not hardware results**.
The firmware simulator was not run in this environment; no board has tested this host change yet.

The debug accounting is `34 + n` requested I2C bytes per successful exchange, including address/sub-select
bytes and fixed reply padding. DDC/CI accounts `8 + n` for the request plus 17 per requested reply read.
Counters count attempted/requested bytes on errors, not measured electrical traffic; START/STOP time is excluded.
Duplex efficiency counts useful bytes in both directions divided by those requested bytes.
The loopback harness now seeds its RNG once (formerly it repeated one byte) and snapshots exchanges,
retries/FULL/BAD and bus bytes before the separate latency check and reset. Historical exchange counts
included that cleanup; compare fresh equal-size runs, not only historical totals.

## Smallest useful hardware measurements (approval required)

**Do not execute this section until Dan approves the specific unit and bus. No firmware flashing is needed.**
Use an already-working Busorra image. Stop other Busorra/TAP/debug users on that monitor first.
These tests reset the two Busorra rings and frame state, temporarily enable raw echo and occupy the DDC
bus. The debug test can temporarily switch the active DDC channel from DDC/CI to 0x35. Video-mode changes
and normal VCP operations should wait until the block returns.

The smallest first measurement is unit 3 on its established controller: equal 6000 B loopbacks at fixed 12,
fixed 27 and adaptive. This reaches both growth thresholds and crosses the 255-sequence wrap, then checks
DDC/CI with a 600 B loopback. Record the unit, firmware tag, adapter/controller, cable, input/video mode and
actual bus frequency. The numbers below are the *historical* NVIDIA DP AUX bus assignment; the EDID guard
must confirm the live assignment before any channel switch. This does not change the bus clock.

Exact initial suite, from the repository root (pending approval):

```sh
export BUS=21 SERIAL=AWT26110003
python - <<'PY'
import os
import subprocess
import sys
sys.path.insert(0, 'scripts')
import dbg_link
import i2cbus

bus, serial = int(os.environ['BUS']), os.environ['SERIAL']
i2cbus.require_unit(bus, serial)  # mismatch/silent EDID aborts before switching
base = [sys.executable, 'scripts/ddcnet.py', 'loopback',
        '--bus', str(bus), '--serial', serial, '--limit-s', '30']
with dbg_link.linked(bus, minutes=5):  # existing #79 ownership/timeout/restore behavior
    for policy in (['--wmax', '12'], ['--wmax', '27'], ['--adaptive']):
        subprocess.run(base + ['--transport', 'dbg', '--bytes', '6000'] + policy, check=True)
# linked restores DDC/CI only if this block acquired it, preserving prior ownership.
if not dbg_link.ddcci_ok(bus):
    raise SystemExit('DDC/CI is not available after the block; stop and inspect link ownership')
subprocess.run(base + ['--transport', 'ddcci', '--bytes', '600'], check=True)
PY
```

Expected effects/results:

- Serial verified first. Existing `dbg_link.linked` acquires/releases only as established by #79;
  its 5-minute timeout remains a backstop. If debug was already owned, it stays owned, and the suite stops
  before the DDC/CI test if that slave is unavailable. Do not steal another client's ownership.
- Each successful debug run returns PASS 6000/6000. Fixed 12 stays 12; fixed 27 stays 27; adaptive reaches 27
  with two promotions **if the traffic is clean**. On a recovered transport error, adaptive reports a backoff,
  locks at 12 and must still return exact bytes. Four unresolved failures stop the suite immediately.
- Every PASS line includes time/B/s, exchange count, retries/FULL/BAD, final size, promotions/backoffs,
  requested bus bytes and duplex efficiency. A clean first baseline should have zero retries/BAD;
  FULL is valid backpressure, but record it. Preserve the decoded/raw logs in `tmp/logs/ddcnet*`.
- DDC/CI remains at 10 B and returns PASS 600/600 after switching back. No TAP or system route is created,
  no settings/brightness service writes are made, and no flash/ISP operation is invoked.

After that first approved check, the next useful evidence is repeated 60,000 B baseline/adaptive pairs on
units 2 and 3 across the Intel HDMI and NVIDIA DP AUX controllers (approve those unit/bus assignments
separately). Repeat after idle and at the relevant video mode. Record byte integrity, retry/BAD/FULL rates,
backoffs, rate and normal DDC/CI availability afterwards. Longer soak tests and other adapters remain
necessary before considering a default change; no default change is included here.
