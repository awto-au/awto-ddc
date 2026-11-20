"""Device operations on a unit's bus: the ONE implementation (awto-ddc#276). The GUI's workers run them through
`dev.py <cmd> --direct`; the dev.py CLI is a thin client of the GUI control port and never runs them by itself.
Each op takes the dev module `d` (unit lookup, bus lookup, script runner) and the argument list; returns the exit code."""
from __future__ import annotations

DDC_SUBS = {"list": 0, "get": 1, "set": 2, "sleep": 0, "wake": 0, "brightness": 1}
I2C_ADDR_MAX = 0x7F                                  # 7-bit address; an 8-bit 0x6E style address is refused, not shifted


def ddc(d, extra: list[str]) -> int:
    _n, u = d._unit(extra)
    many = bool(extra) and extra[0] == "get" and 2 <= len(extra) <= 9          # get CODE [CODE...]: one detect for all codes
    if not extra or extra[0] not in DDC_SUBS or (len(extra) != 1 + DDC_SUBS[extra[0]] and not many) \
            or any(x.startswith("-") for x in extra):
        raise SystemExit(f"ddc: one of {DDC_SUBS} (arg counts {list(DDC_SUBS.values())}); got {extra}; nothing done")
    return d._py("ddc_ctl.py", "--bus", d._bus(u), *extra)


def settings(d, extra: list[str]) -> int:
    sim, given = d._opt(extra, "--sim"), d._opt(extra, "--map")
    if extra[:1] == ["rows"]:
        return d._py("settings_cli.py", "--map", "-", *extra)
    if sim:
        mp = given or str(d.Path(sim).with_suffix(".map"))
        return d._py("settings_cli.py", "--sim", sim, "--map", mp, *extra)
    _n, u = d._unit(extra)
    b = d._live_bus(u)
    mp = d._fwmap(u, given)
    if not given:
        d._registry_verify(u, b)                     # flash registry staleness probe (same as before the port)
    return d._dbg_py(b, "settings_cli.py", "--bus", str(b), "--serial", u["serial"], "--map", mp, *extra)


def synclog(d, extra: list[str]) -> int:
    flags = [f for f in ("--whole", "--delta") if d._flag(extra, f)]
    given = d._opt(extra, "--map")
    _n, u = d._unit(extra)
    b = d._live_bus(u)
    return d._dbg_py(b, "sync_log.py", b, "--serial", u["serial"], "--map", d._fwmap(u, given), *flags)


def note(d, extra: list[str]) -> int:
    given, openc = d._opt(extra, "--map"), d._flag(extra, "--open-console")
    _n, u = d._unit(extra)
    text = list(extra)
    if given is True or len(text) != 1 or text[0].startswith("--"):
        raise SystemExit("note: one TEXT argument (quote it); nothing done")
    b = d._live_bus(u)
    return d._dbg_py(b, "host_note.py", b, "--serial", u["serial"], "--map", d._fwmap(u, given),
                     *(["--open-console"] if openc else []), text[0], keep_console=openc)


def kvm(d, extra: list[str]) -> int:
    return d._py("kvm.py", *extra)


def i2c(d, extra: list[str]) -> int:
    """raw transfer on the unit's EDID-proven bus: ADDR [BYTES...] [--read N]; bytes = write, then a repeated-start read of N"""
    read = d._opt(extra, "--read", None)
    _n, u = d._unit(extra)
    if not extra:
        raise SystemExit("i2c: ADDR [BYTES...] [--read N]; nothing done")
    args = ["--addr", extra[0], "--serial", u["serial"], "--bus", str(d._bus(u))]
    if extra[1:]:
        args += ["--write", *extra[1:]]
    if read not in (None, True):
        args += ["--read", str(read)]
    return d._py("i2c_raw.py", *args)
