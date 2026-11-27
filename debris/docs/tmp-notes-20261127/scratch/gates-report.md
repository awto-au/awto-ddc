
| boot | PASS | 1 s | the sim boots to stage 8, heartbeat advances | ok 
| isr | PASS | 7 s | 1500 interrupts return, all banks covered | why 1500 ? can we just do minium to sweep all vaues 
| link | PASS | 3 s | linker findings: 0 problems |  
| h1080, h2160 | PASS (11/12) | 4 s, 6 s | health in the sim; "delay cal" fails by design (counted PASS) | more info 
| menu | PASS | 27 s | walks 16 menu pages, 133 entries | to long - extended gate only 
| ddc | PASS | 8 s | DDC/CI protocol sim | too longg - can we reduce to sesssential vlaues only 
| pump | PASS | 3 s | message pump sim |  |  |
| keys | PASS | 126 s | key dispatcher sim (80 checks) | why so long ?
| wdt | KILLED | 60 s | watchdog cases in the sim | why do long ? 
| sync | KILLED | 30 s | sync log sim |  why so long ?
| bootsim, bootsim_always | PASS | 11 s, 14 s | boot with console after the picture and at power-on | why 10x realtimed when sim runs 10 times quicket than realtime 
| wake | KILLED | 30 s | wake paths sim |  why do long 
| panel | PASS | 17 s | panel power, backlight and DP link sequencing | why 
| sysm | KILLED | 30 s | system state machine sim | whot sol ong 
| delays | KILLED | 93 s | delays against the clock, and the delay audit | huh  are there check ing what ?
| nvlog | PASS | 11 s | NVRAM flush log |  ?
| flashclk | PASS | 3 s | flash clock order |  |  |
| deadport | PASS | 75 s | dead-port search sim |  why so long 
| portcfg | PASS | 12 s | port configuration |  ?
| inputrate | PASS | 85 s | input rate measurement sim |  ?
| monitor | KILLED | 90 s | the input and ADC monitor |  ?
| htime | PASS | 13 s | host time and console title row | for one line on the osd
| conmode | KILLED | 30 s | console off, until signal, always | ?
| canary | PASS | 44 s | stack canary |  44s to chek thsa ?
| conwrap | KILLED | 30 s | console line wrapping |  shoule less .1s ?
| crash | KILLED | 30 s | crash and watchdog-bite handling | seem wring 
| pokes | PASS | 4 s | watchdog poking loops are bounded |  seem long 
| magic | PASS | 0 s | no raw register or palette numbers in our code |  |  |
| regs | PASS | 2 s | register-name header is current |  |  |
| regmap | PASS | 10 s | register database is current |  |  |
| iram | PASS | 4 s | IRAM names and placement |  |  |
| rules | PASS | 0 s | SDK is not patched by the build |  |  |
| gensync, geninputs, gensavers, dwmodel | PASS | 0 to 2 s | generated tables are current |  |  |  |  |

#
- `conwrap` should take under 0.5 s: it boots the firmware and plays a whole scenario to test a pure wrapping function. The speed-up agent is told to test pure-logic gates directly (shared boot snapshot or a host harness) and to prove each gate still fails on injected faults.
- Gate runner fix in progress: load-aware limit plus one automatic rerun of a killed gate (both runs logged).
- Speed-up agent scope: keys, delays, monitor, inputrate, deadport, plus the pure-logic gates (conwrap, conmode, sysm, sync, wake, crash, wdt).

## Build time (separate from gate and test times)

- Build (compile + link of one image, `./dev.py build`): about 40 s on the default config (the audio image: 12:59:30 to 13:00:18 = 48 s under load).
- Not part of the gate times above: the gates run against an already built image.
- A full gate run of the merged tree took 106 s wall (speed-up agent, 2026-11-19), build excluded.
- Flash is separate again: unit 3 over HDMI DDC 24 s, unit 2 over DP AUX 116 s.
