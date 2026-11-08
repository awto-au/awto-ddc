# IP over DDC (#80)

- Firmware: branch `wb-p14net` (worktree `/mnt/2tb/git/awto-ddc-net`), `fw/sdcc/awto_net.inc`, ISR block in `fw/sdcc/awto_dbgisr.inc`, D0 dispatch in `fw/sdcc/awto_ddcci.inc`, switch `_AWTO_NET` in `RL6449_Project.h`.
- Host: `scripts/ddcnet.py` (loopback, stack, daemon, svc). Decoded log lines: `rtd_proto` (`net 0x3D` / `net DDC/CI D0` runs).
- Host throughput policy, offline regression/model results and approval-gated hardware commands:
  [Busorra throughput](busorra-throughput.md). Default remains 12 B; `--adaptive` is opt-in for debug transport only.

## Link
- Two byte rings in XDATA (`g_stAwtoNet`): host -> fw 128 B, fw -> host 128 B. BYTE indices, 128 divides 256.
- One exchange = one write + one read. Host polls: I2C is master-driven.
- Exchange fields: `seq` (1..255), `ctl` (bit0 echo mode, bit7 reset), `ack` (bytes taken from the previous applied reply), data.
- Reply: `seq`, flags, RX free, data from the TX tail (tail moves only on the next exchange's ack).
- Repeated `seq` = host retry: nothing re-applied, the stored result and current TX data are sent again.
- Applied = flag ACC or FULL. Not applied (BAD, RESET): host keeps its data and ack.

| flag | bit | meaning |
|---|---|---|
| ACC | 0x01 | request data taken |
| FULL | 0x02 | no room: data not taken (ack applied) |
| BAD | 0x04 | 0x3D checksum bad |
| RESET | 0x08 | reset pending: no data either way |
| ECHO | 0x10 | raw loopback mode |
| MORE | 0x20 | more TX bytes than this reply holds |
| UP | 0x80 | always set |

### Transport B: debug slave 0x35, cmd 0x3D (answered in the EXINT1 ISR)
- Write `0x3D [seq ctl ack data[n] chk]`, chk = (0x3D + sum) & 0xFF. n <= 27 (SDK `g_pucDdcciData` 32 B).
- Host default n = 12: the whole write fits the 16-byte IIC FIFO (regdb FF25) even if the ISR is late. `--wmax 27` to test more on hardware.
- Read sub 0x08, 25 B fixed: `seq flags rxfree m data[20] chk`, chk = (0x3D + sum of 24) & 0xFF.
- Firmware without #80: 0x3D falls into the SDK's default write-command case (no effect); the reply fails the checksum.

### Transport A: DDC/CI 0x37, op D0 / reply D1 (polled IIC_1 engine, main loop)
- Write `51 80|n D0 seq ctl ack data[<=10] chk` (XOR, DDC/CI rule). Engine buffer 16 B.
- Read `6E 80|n D1 seq flags free data[<=9] chk`. Not ready = null message or our request still in the buffer: host re-reads after 3 / 6 / 40 / 40 ms.
- Works beside VCP get/set (KVM 0x60): no channel swap, fits #79.
- Both transports share the rings: use one per monitor at a time.

## Frames
- SLIP (RFC 1055) carries Ethernet frames, so a TAP bridges them unchanged.
- Config ethertype 0x88B5 (local experimental): `'A' 'W' 01 mac[6] ip[4]` sets, `03` queries; reply `02 mac ip ver`. Daemon re-sends every 5 s (survives a monitor reboot). Unconfigured (IP 0) = only config answered.
- ARP request for our IP -> reply. IPv4 without options or fragments, header checksum checked.
- ICMP echo -> reply in place. UDP port 7 -> echo. UDP 5577 -> service. UDP checksum sent as 0 (link bytes are checksummed).
- Replies go to the requester's MAC: no ARP cache, routing works through the host.
- One 300 B frame buffer (IP MTU 286): no RX while a reply is being encoded.

## UDP service, port 5577
Request `[op tag ...]`, reply `[op|0x80 tag status ...]`; values big-endian.

| op | request | reply |
|---|---|---|
| 01 info | - | ver, flags (bit0 registry, bit1 msg ring on), ring size, mtu (2), msg seq (2) |
| 02 get | n, id[n] (n <= 32) | n, (id st val16)[n] |
| 03 set | n, (id val16)[n] (n <= 16) | n, (id st val16 read back)[n] |
| 04 subscribe | flags: bit0 stream to me, bit1 message ring on | msg seq (2) |
| 06 read msgs | from seq (2) | lost, first seq (2), n, (id16 val32)[n] (n <= 40) |
| 05 push (fw -> subscriber) | - | as 06 reply, tag 0 |

- Setting status: 0 ok, 1 no such id, 2 refused (read-only / inputs rule), 0xFE image without the #67 registry.
- Registry calls: `set_get` / `set_put(id, v, 1)` / `set_idx`, under `#ifdef _AWTO_NEW_SETTINGS` (live on `wb-osd67net`).
- Unknown op: status 0xFF.

## Addresses (host-only, not the house LAN 192.168.25.0/24)
- `--bridge` (broadcast): every TAP `ddcN` on `ddcbr0`, host 10.235.0.1/24, unit N = 10.235.0.1N, MAC 02:41:57:00:00:0N.
- `--route` (switched): TAP `ddcN` alone, host 10.235.N.1/24, unit N = 10.235.N.2; `net.ipv4.ip_forward=1`.
- TAP MTU 286, IPv6 off on the TAPs and the bridge (no RS / MLD over the link). Setup by `sudo -n ip`; `--keep` leaves them.

## Cost
- Main loop: `AWTO_NET_POLL()` tests `g_ucAwtoNetRun` (set by an exchange); idle = one XDATA byte test per pass.
- XDATA +614 B (hole 0xD700); code ~3.3 KB, bank 12; ISR block +476 B.

## Measured
Sim only so far (fw_sim, unit 3 image wb-p14net1, wb-p14net de074ad, 1080p60 source on D2, 2026-11-08). Fw time = Timer2 ms; the sim does not model I2C bus time, so these are firmware-side bounds, not link rates.

| test | dbg (0x3D, 12 B writes) | dbg (27 B writes) | ddcci (D0) |
|---|---|---|---|
| loopback 600 / 200 B | 200 B in 29 fw ms, 22 exchanges | 600 B in 52 fw ms, 35 exchanges | 200 B in 72 fw ms, 28 exchanges |
| 1-byte round trip | 5 fw ms, 2 exchanges | 5 fw ms | 8 fw ms, 2 exchanges |
| ping 56 B rtt | 23-25 fw ms, 14 exchanges | | 68 fw ms, 22 exchanges |
| ping burst 6 x 200 B | 223 fw ms, 135 exchanges | | |
| 20 % replies lost (dedup) | 600 B intact, 12 retries | | 200 B intact at 60 % loss |

- Speed bench (main loop, docs/speed-bench.tsv): work 4938 (kvm2e) -> 4944 cycles/pass (wb-p14net1), instr/pass 22503 both; with #67 settings 5062 (wb-osd67i) -> 5068 (wb-osd67net1, wb-osd67net c7ec071).
- wb-osd67net1 (registry): stack get id 1 = 44, set id 1 = 60 read back; `ddc_sim.py` (MCCS) PASS beside D0.
- Linux end to end in the sim: `ping 10.235.0.13` through TAP + bridge, 5/5, rtt 1.6-1.8 s wall (sim speed); `ddcnet.py svc info|get|msgs` through the kernel; route mode + ddcci ping 3/3 (9.4 s wall; first ARP timed out at sim speed).
- Hardware is working: [unit 3, both transports and TAP](https://github.com/awto-au/awto-ddc/issues/80#issuecomment-6715078111),
  [unit 2, DDC/CI and routed TAP](https://github.com/awto-au/awto-ddc/issues/80#issuecomment-6716137339).
  Unit 3's 600 B debug loopback measured 2417 B/s at 12 B and 3449 B/s at 27 B (35 exchanges, zero retries/full at 27 B).
  This does not validate the adaptive host policy or sustained/cross-adapter operation.
