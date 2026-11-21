"""Decode of g_stAwtoMon (fw/diag/monitor.c, RL6449_Project.h StAwtoMon, 33 B, byte-only) for unit_health.py / dev.py health."""
SIZE = 33
STALL_CLASSES = ("main", "wait", "flash", "other")      # AWTO_STALL_* (RL6449_Project.h)
POKE_MS = 293 / 64                       # ucMaxPoke unit, ms (console.c: x 293 >> 6 = 4.58 ms)
BOOT = {1: "cold power-up", 2: "watchdog bite", 3: "warm reset", 4: "watchdog probe", 5: "hardware watchdog"}   # AWTO_BOOT_* (sync.tsv D0 rows)


def decode(b: bytes) -> dict | None:
    """None when the block holds no sample yet (magic missing: the first sample is AWTO_MON_MS after boot, or registry monitor off from the start)."""
    if len(b) < SIZE or b[0:2] != b"MN":
        return None
    return dict(version=b[2], on=b[3], beat=b[4], adc=list(b[5:9]), trim=b[9] << 8 | b[10], loop=b[11] << 8 | b[12],
                poke=b[13], poke_ms=round(b[13] * POKE_MS), site=b[14], stack=b[15], boot=b[16],
                up_s=b[17] << 16 | b[18] << 8 | b[19], rows=b[20],
                gap=[(b[21 + 2 * i] << 8 | b[22 + 2 * i]) / 10 for i in range(4)], gap_site=list(b[29:33]))


def text(d: dict) -> str:
    return (f"samples {d['beat']}, on {d['on']}; ADC A0 {d['adc'][0]:02X} A1 {d['adc'][1]:02X} A2 {d['adc'][2]:02X} A3 {d['adc'][3]:02X}; "
            f"IOSC trim {d['trim']}; {d['loop']} passes/s, longest stall {max(d['gap']):.1f} ms ("
            + ", ".join(f"{n} {g:.1f} ms at site {st}" for n, g, st in zip(STALL_CLASSES, d["gap"], d["gap_site"], strict=True)) + "); "
            f"uptime {d['up_s']} s, stack high {d['stack']:02X}, boot {BOOT.get(d['boot'], d['boot'])}, {d['rows']} rows logged")
