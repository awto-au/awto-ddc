#!/usr/bin/env python3
"""dev.py — canonical entry point for awto-ddc (awto dev.py convention).

AI agents: run `./dev.py describe` for machine-readable JSON help.
Humans: run `./dev.py --help`.

All output is timestamped in LOCAL time and mirrored to ./tmp/logs/dev.log.

Scaffold usage:
    cp awto-dan/dev.py-template/dev.py  <repo>/dev.py
    cp awto-dan/dev.py-template/test_dev.py <repo>/tests/
    - set PROJECT below
    - edit the STEPS table; that is the ONLY place build/test commands live

Everything else (help, describe, gate, ci, logging, exit codes) is generic
and should not need editing.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT = "awto-ddc"


def _repo_root() -> Path:
    """Three-tier resolution (awto-dan#35): env override, git toplevel,
    file-relative. Works at <repo>/dev.py AND <repo>/scripts/dev.py.
    Never VSCODE_CWD — that is the launch directory, not the workspace."""
    env = os.environ.get(f"{PROJECT.upper().replace('-', '_')}_REPO")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    here = Path(__file__).resolve().parent
    try:
        # local .git read, ~1 ms warm; 0.25 s covers a cold first exec.
        # On expiry/absence: file-relative fallback below.
        out = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=0.25)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return here.parent if here.name == "scripts" else here


REPO = _repo_root()
sys.path.insert(0, str(REPO / "scripts"))
import i2cbus  # noqa: E402  (the only module that touches /dev/i2c-N, #48)
TMP = REPO / "tmp"           # scratch, pidfiles
LOGS = TMP / "logs"          # logs, per the ./tmp/logs/ rule
LOG = LOGS / "dev.log"

# --------------------------------------------------------------------------
# STEPS — the only project-specific part.
#
# Each entry: command name -> (summary, argv, accepts_extra_args)
# argv of [] means "not configured for this project"; such a step SKIPS
# rather than fails, so a fresh scaffold runs green before you fill it in.
# Swap for your build system: cargo / pytest / west / npm / make ...
# --------------------------------------------------------------------------
# Ships UNCONFIGURED ([]) so a fresh copy runs green immediately: every step
# SKIPs, `ci` reports GO with skips listed, and you fill them in one at a time
# and watch each go from SKIP to ok. Replace [] with the real argv.
#
#   Rust    build ["cargo","build"]   test ["cargo","test","--workspace"]
#           lint  ["cargo","clippy","--all-targets"]   fmt ["cargo","fmt"]
#   Python  test  [sys.executable,"-m","pytest","-q"]  lint ["ruff","check","."]
#   Zephyr  build ["west","build"]     test ["west","build","-t","run_tests"]
STEPS: dict[str, tuple[str, list[str], bool]] = {
    "test":      ("dev.py contract tests",        [sys.executable, "-m", "pytest", "-q", "tests"], True),
    "lint":      ("ruff on scripts/ + dev.py",    ["ruff", "check", "dev.py", "scripts"], True),
    "fmt-check": ("formatting check (no writes)", [], False),
    "fmt":       ("reformat in place",            [], False),
    "run":       ("build + execute",              [], True),
    "speed":     ("offline cycle bench of fw images (fw_profile, docs/speed-bench.tsv)",
                  [sys.executable, "scripts/speed_bench.py"], True),
}

# gate = fail-fast, blocks a commit. First failure wins; fix that.
GATE = ["test", "build"]
# ci = run-all-collect-all. Every leg runs even after a failure, then ONE
# GO/NO-GO. On hardware a re-run costs minutes and may not reproduce.
CI = ["lint", "test", "build"]

# --------------------------------------------------------------------------
# Logging — Tier A (dev tooling): local time, stderr + ./tmp/logs/dev.log,
# colour on TTY only, file copy always plain.
# --------------------------------------------------------------------------
_COLOR = {
    "FATAL": "\033[1;91m", "ERROR": "\033[31m", "WARN": "\033[33m",
    "INFO": "\033[97m", "DEBUG": "\033[94m", "ALERT": "\033[92m",
}
_RESET = "\033[0m"
_USE_COLOR = (
    sys.stderr.isatty()
    and not os.environ.get("NO_COLOR")
    and os.environ.get("CLICOLOR") != "0"
)


def _stamp() -> str:
    # Local zone incl. DST (AEST +1000 / AEDT +1100). Never hardcode the
    # offset and never use UTC here: a human reads these live.
    return datetime.now().astimezone().strftime("%H:%M:%S.%f%z")


def log(msg: str, level: str = "INFO") -> None:
    line = f"{_stamp()}  {level:<5} [dev.py] {msg}"
    if _USE_COLOR:
        sys.stderr.write(f"{_COLOR.get(level, '')}{line}{_RESET}\n")
    else:
        sys.stderr.write(line + "\n")
    sys.stderr.flush()
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")          # file copy is ALWAYS plain
    except OSError:
        pass                                # never let logging kill the run


SKIPPED = 125   # distinct from any real tool's exit code


def run_step(name: str, extra: list[str] | None = None) -> int:
    """Run one STEPS entry (or a project command by name). Returns its exit code, or SKIPPED."""
    if name not in STEPS:
        return COMMANDS[name]["fn"](list(extra or []))
    summary, argv, takes_extra = STEPS[name]
    if not argv:
        log(f"{name}: not configured for this project - skipped", "WARN")
        return SKIPPED
    if not shutil.which(argv[0]) and argv[0] != sys.executable:
        log(f"{name}: {argv[0]} not on PATH - skipped", "WARN")
        return SKIPPED
    cmd = argv + (list(extra) if (extra and takes_extra) else [])
    log("run: " + " ".join(cmd))
    rc = subprocess.call(cmd, cwd=REPO)
    log(f"rc={rc}: " + " ".join(cmd), "INFO" if rc == 0 else "ERROR")
    return rc


# --------------------------------------------------------------------------
# Command registry — ONE source of truth. The decorator populates the table
# that drives dispatch, --help AND describe, so they cannot drift apart.
# --------------------------------------------------------------------------
COMMANDS: dict[str, dict] = {}


def command(summary: str, *, args: str = "", kind: str = "action"):
    def deco(fn):
        COMMANDS[fn.__name__.replace("cmd_", "").replace("_", "-")] = {
            "summary": summary, "args": args, "kind": kind, "fn": fn,
        }
        return fn
    return deco


@command("machine-readable command list (JSON, for AI agents)", kind="meta")
def cmd_describe(_extra: list[str]) -> int:
    print(json.dumps({
        "project": PROJECT,
        "schema": 1,
        "entrypoint": "./dev.py",
        "log": str(LOG.relative_to(REPO)),
        "exit_codes": {"0": "success", "2": "usage error",
                       "125": "step skipped (tool absent)", "other": "failure"},
        "commands": {
            name: {k: v for k, v in meta.items() if k != "fn"}
            for name, meta in COMMANDS.items()
        },
    }, indent=2))
    return 0


@command("check the toolchain is present; run this first when stuck", kind="meta")
def cmd_doctor(_extra: list[str]) -> int:
    log(f"project    : {PROJECT}")
    log(f"python     : {sys.version.split()[0]} ({sys.executable})")
    log(f"gil        : {'disabled (free-threaded)' if not sys._is_gil_enabled() else 'enabled'}"
        if hasattr(sys, "_is_gil_enabled") else "gil        : n/a (<3.13)")
    missing = []
    for name, (_s, argv, _e) in STEPS.items():
        if not argv:
            log(f"{name:10s} : not configured", "WARN")
        elif argv[0] == sys.executable or shutil.which(argv[0]):
            log(f"{name:10s} : {argv[0]} ok")
        else:
            log(f"{name:10s} : {argv[0]} MISSING", "ERROR")
            missing.append(argv[0])
    if missing:
        log(f"missing tools: {', '.join(sorted(set(missing)))}", "ERROR")
        return 1
    log("doctor ok", "ALERT")
    return 0


@command("remove build output only (tmp/sdcc-port, tmp/fw/<serial>/ build dirs); images, maps, manifests, flashed.json, regs, logs kept",
         kind="action")
def cmd_clean(_extra: list[str]) -> int:
    # #52.17: tmp/ also holds frozen images, flash state, measurements and logs - not regenerable
    targets = [TMP / "sdcc-port"] + (sorted(p for p in FW.iterdir() if p.is_dir()) if FW.is_dir() else [])
    for path in targets:
        if path.exists():
            shutil.rmtree(path)
            log(f"removed {path.relative_to(REPO)}")
    return 0


@command("fail-fast pre-commit gate: " + " + ".join(GATE), kind="aggregate")
def cmd_gate(_extra: list[str]) -> int:
    for name in GATE:
        rc = run_step(name)
        if rc not in (0, SKIPPED):
            log(f"GATE FAILED at {name} (rc={rc})", "FATAL")
            return rc
    log("GATE PASSED", "ALERT")
    return 0


@command("run every leg, collect all results, one GO/NO-GO", kind="aggregate")
def cmd_ci(_extra: list[str]) -> int:
    results: dict[str, int] = {}
    for name in CI:
        results[name] = run_step(name)          # no early exit - that is the point
    failed = {k: v for k, v in results.items() if v not in (0, SKIPPED)}
    skipped = [k for k, v in results.items() if v == SKIPPED]
    log("-" * 52)
    for name, rc in results.items():
        state = "SKIP" if rc == SKIPPED else ("ok" if rc == 0 else f"FAIL rc={rc}")
        log(f"  {name:12s} {state}", "INFO" if rc in (0, SKIPPED) else "ERROR")
    if skipped:
        log(f"{len(skipped)} step(s) skipped: {', '.join(skipped)}", "WARN")
    if failed:
        log(f"NO-GO - {len(failed)} of {len(results)} failed: {', '.join(failed)}", "FATAL")
        return 1
    log("GO", "ALERT")
    return 0


@command("verify dev.py's own contract (help/describe/exit codes)", kind="meta")
def cmd_selftest(_extra: list[str]) -> int:
    failures = []

    def check(label: str, cond: bool) -> None:
        log(f"  {label}: {'ok' if cond else 'FAIL'}", "INFO" if cond else "ERROR")
        if not cond:
            failures.append(label)

    out = subprocess.run([sys.executable, __file__, "describe"],
                         capture_output=True, text=True, cwd=REPO)
    check("describe exits 0", out.returncode == 0)
    try:
        doc = json.loads(out.stdout)
        check("describe emits valid JSON", True)
        check("describe has project+commands", {"project", "commands"} <= doc.keys())
        check("every command documented", all(
            m.get("summary") for m in doc.get("commands", {}).values()))
    except json.JSONDecodeError:
        check("describe emits valid JSON", False)

    h = subprocess.run([sys.executable, __file__, "--help"],
                       capture_output=True, text=True, cwd=REPO)
    check("--help exits 2 (usage)", h.returncode == 2)
    check("--help lists commands", all(c in h.stdout for c in COMMANDS))

    u = subprocess.run([sys.executable, __file__, "no-such-command"],
                       capture_output=True, text=True, cwd=REPO)
    check("unknown command exits 2", u.returncode == 2)

    check("registry has no duplicate handlers",
          len({m["fn"] for m in COMMANDS.values()}) == len(COMMANDS))

    if failures:
        log(f"selftest FAILED: {', '.join(failures)}", "FATAL")
        return 1
    log("selftest ok", "ALERT")
    return 0


# --------------------------------------------------------------------------
# awto-ddc: firmware build + test-unit loop (#26). Units: scripts/devices.json.
# --------------------------------------------------------------------------
SDCC_BE_BIN = "/mnt/2tb/git/awto-sdcc-be/tmp/be-install/bin"     # awto-sdcc big-endian install
FW = TMP / "fw"
BOOT_PORTS = {"DP": "_D1_INPUT_PORT", "HDMI": "_D2_INPUT_PORT"}               # debug port before first ACTIVE (#28)
MODES = {"1080p50": "1920x1080@50.000", "1080p60": "1920x1080@60.000", "4k30": "3840x2160@30.000",
         "4k60": "3840x2160@60.000"}


def _units() -> dict:
    return json.loads((REPO / "scripts/devices.json").read_text())["units"]


def _opt(extra: list[str], flag: str, default=None):
    """--flag VALUE from extra (removed); --flag alone -> True."""
    if flag not in extra:
        return default
    i = extra.index(flag)
    extra.pop(i)
    if i < len(extra) and not extra[i].startswith("--"):
        return extra.pop(i)
    return True


def _flag(extra: list[str], flag: str) -> bool:
    """Boolean --flag (removed); never consumes the next argument (--full once swallowed the image path)."""
    if flag in extra:
        extra.remove(flag)
        return True
    return False


def _image_arg(extra: list[str]) -> list[str]:
    """What is left after options: at most one existing .bin; anything else (--help, typos) is refused."""
    bad = [x for x in extra if x.startswith("-")] + extra[1:]
    if bad:
        raise SystemExit(f"unknown/extra argument(s) {bad}; nothing done")
    if extra:
        p = Path(extra[0]) if Path(extra[0]).is_absolute() else (Path.cwd() / extra[0])
        if p.suffix != ".bin" or not p.is_file():
            raise SystemExit(f"image {extra[0]!r} is not an existing .bin; nothing done")
        return [str(p.resolve())]
    return []


def _unit(extra: list[str]) -> tuple[str, dict]:
    n = str(_opt(extra, "--unit", "3"))
    u = _units().get(n)
    if u is None:
        raise SystemExit(f"unknown unit {n!r}: see scripts/devices.json")
    if _flag(extra, "--dp"):
        if not u.get("connector_dp"):
            raise SystemExit(f"unit {n} has no DP link in scripts/devices.json")
        u = {**u, "_conn": u["connector_dp"], "gdctl": u["gdctl_dp"], "input": "DP"}
    if not u.get("test") and not _flag(extra, "--force"):
        raise SystemExit(f"unit {n} is a working screen (devices.json test=false): add --force to touch it")
    return n, u


BUS_RESCAN_S = 0.25   # one scan of the candidate buses is ~0.1 s; rescan pace while EDID is silent

def _bus(u: dict, wait_s: float = 0.0) -> int:
    """The bus whose EDID serial is the unit's: the connector's i2c link first, else every display bus
    (NVIDIA has no link). A recable moved units between ports on 2026-11-06 and a flash hit the wrong one."""
    link = (Path("/sys/class/drm") / u.get("_conn", u["connector"]) / "ddc").resolve()
    cands = [int(link.name.split("-")[1])] if link.name.startswith("i2c-") else []
    cands += [b for b in i2cbus.list_buses(display_only=True) if b not in cands]
    if i2cbus.reset_rate():
        log("bus rate: gmbus_rate module was left loaded; unloaded (100 kHz)", "WARN")
    t0 = time.monotonic()
    while True:
        for b in cands:
            if i2cbus.edid_serial(b) == u["serial"]:
                return b
        if time.monotonic() - t0 >= wait_s:         # wait_s 0 = one scan; >0 = rescan (EDID returns as the scaler boots)
            break
        time.sleep(BUS_RESCAN_S)
    raise SystemExit(f"{u['serial']}: no bus with that EDID serial (unit off, wedged, or cabled elsewhere); "
                     f"use --bus N only after checking which monitor it is")


def check_image_identity(u: dict, img: Path) -> None:
    """Refuse an image built for another unit (a unit-2 image on unit 3 left the wrong EDID serial, #52.11):
    its file-name tag and every AWT<8 digits> string inside it must be this unit's serial."""
    me = u["serial"]
    m = re.match(r"(AWT\d{8})", img.name)
    if m and m.group(1) != me:
        raise SystemExit(f"image {img.name} is tagged for {m.group(1)}, unit is {me}; nothing done")
    found = set(re.findall(rb"AWT\d{8}", img.read_bytes()))
    other = sorted(x.decode() for x in found if x.decode() != me)
    if other:
        raise SystemExit(f"image {img.name} embeds serial(s) {other}, unit is {me}; nothing done")
    if me.encode() not in found:
        raise SystemExit(f"image {img.name} does not embed serial {me} (not built by `dev.py build --unit`?); "
                         f"--any-image to flash it anyway")


def _py(script: str, *args, env: dict | None = None) -> int:
    cmd = [sys.executable, str(REPO / "scripts" / script), *map(str, args)]
    log("run: " + " ".join(cmd[1:]))
    rc = subprocess.call(cmd, cwd=REPO, env={**os.environ, "AWTO_VIA_DEV": "1", **(env or {})})
    log(f"rc={rc}: {script}", "INFO" if rc == 0 else "ERROR")
    return rc


def _flashed(u: dict) -> dict:
    f = FW / f"{u['serial']}-flashed.json"
    return json.loads(f.read_text()) if f.exists() else {}


@command("build firmware for a unit; frozen to tmp/fw/<serial>-<commit>[-frc]-be.*",
         args="[--unit N] [--frc]", kind="action")
def cmd_build(extra: list[str]) -> int:
    n, u = _unit(extra)
    frc = _flag(extra, "--frc")
    defs = ["-D_AWTO_FRC"] if frc else []
    if BOOT_PORTS.get(u["input"]):
        defs.append(f"-D_AWTO_BOOT_PORT={BOOT_PORTS[u['input']]}")
    env = {"AWTO_SDCC_BE": "1" if u["be"] else "0", "AWTO_SDCC_BIN": SDCC_BE_BIN, "K2S_SDCC_EXTRA": " ".join(defs)}
    rc = _py("fw_build.py", "--serial", u["serial"], env=env)
    if rc:
        return rc
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = "+" if subprocess.run(["git", "diff", "--quiet"], cwd=REPO).returncode else ""
    tag = f"{u['serial']}-{commit}{dirty}{'-frc' if frc else ''}-be"
    out = FW / u["serial"]
    for src, ext in ((out / "fw.bin", "bin"), (out / "fw.map", "map"), (TMP / "sdcc-port/trace_ids.tsv", "ids.tsv")):
        shutil.copy2(src, FW / f"{tag}.{ext}")
    (FW / f"{u['serial']}-last.txt").write_text(tag)
    log(f"image tmp/fw/{tag}.bin (unit {n}{', FRC' if frc else ''})", "ALERT")
    return 0


@command("flash an image to a unit over ISP (default: last build); incremental by tmp/fw/<serial>-flash-state.json; GMBUS fallback auto-reset",
         args="[--unit N] [--full] [--any-image] [--verify crc|readback] [--write-mode byte|burst] [image.bin]", kind="action")
def cmd_flash(extra: list[str]) -> int:
    n, u = _unit(extra)
    full = _flag(extra, "--full")
    verify = _opt(extra, "--verify", "crc")
    wmode = _opt(extra, "--write-mode", "burst")  # burst default: faster, failed pages redone in byte mode (#12)
    bus = _opt(extra, "--bus")              # recover: bus proven by its own relay cycle (EDID silent while held)
    any_image = _flag(extra, "--any-image")
    extra = _image_arg(extra)
    if extra:
        img = Path(extra[0])
        tag = img.name.removesuffix(".bin")
    else:
        tag = (FW / f"{u['serial']}-last.txt").read_text().strip()
        img = FW / f"{tag}.bin"
    if not any_image:
        check_image_identity(u, img)
    identity = None
    if bus:
        identity = "dev.py recover: bus resolved by this unit's EDID serial, before or right after its own relay cycle"
        log(f"flash: bus {bus} given by caller ({identity}); rtd_flash_image checks the EDID serial, silent EDID accepted")
    bus = int(bus or _bus(u))
    # #52.12: from here the flash holds an unknown mix; the old tag/map must not be used by dbg/osd/health.
    # tag "" -> _fwmap/_diag find nothing; image stays so `recover` can retry it.
    (FW / f"{u['serial']}-flashed.json").write_text(json.dumps({"tag": "", "image": str(img), "attempted": tag}))
    with i2cbus.fast_bus(bus) as khz:       # 1 MHz only around the ISP write (0x35 NAKs at 1 MHz); unloaded in finally
        log(f"flash: bus {bus} at {khz} kHz")
        rc = _py("rtd_flash_image.py", bus, img, "--serial", u["serial"], "--write", "--no-backup",
                 "--tag", tag, "--verify", verify, "--write-mode", wmode, *(["--full"] if full else []),
                 *(["--identity", identity] if identity else []))
    if rc == 0:
        (FW / f"{u['serial']}-flashed.json").write_text(json.dumps({"tag": tag, "image": str(img)}))
    return rc


@command("mains power-cycle a unit via its relay (scripts/power_cycle.py)", args="[--unit N] [--on|--off]",
         kind="action")
def cmd_power_cycle(extra: list[str]) -> int:
    n, u = _unit(extra)
    if not u["relay"]:
        log(f"unit {n} has no relay (scripts/devices.json)", "ERROR")
        return 1
    return _py("power_cycle.py", "--relay", u["relay"], *extra)


def _diag(u: dict, *args, bus: int | None = None) -> int:
    ids = FW / f"{_flashed(u).get('tag', '')}.ids.tsv"
    more = ["--ids", ids] if ids.is_file() else []
    return _py("rtd_diag.py", bus if bus is not None else _bus(u), *(["--be"] if u["be"] else []), *args, *more)


@command("read the diag block (boot stages, rates, self-test)", args="[--unit N]", kind="action")
def cmd_diag(extra: list[str]) -> int:
    return _diag(_unit(extra)[1])


@command("read the safe-boot / canary / bus-watchdog block", args="[--unit N]", kind="action")
def cmd_safe(extra: list[str]) -> int:
    return _diag(_unit(extra)[1], "--safe")


@command("poll the function-entry trace ring until the unit stops answering", args="[--unit N]", kind="action")
def cmd_trace(extra: list[str]) -> int:
    return _diag(_unit(extra)[1], "--trace")


@command("log which I2C slaves answer through the first seconds after power-on", args="[--unit N] [--bus N] [--window S]",
         kind="action")
def cmd_probe(extra: list[str]) -> int:
    _n, u = _unit(extra)
    bus = _opt(extra, "--bus")              # EDID is silent while the unit boots, so _bus cannot find it then
    if bus is True:
        raise SystemExit("probe: --bus needs a value; nothing done")
    return _py("rtd_boot_probe.py", int(bus) if bus else _bus(u), *extra)


def _done(extra: list[str], what: str) -> None:
    """Refuse anything left in extra (typos, --help, stray options) before hardware is touched."""
    if extra:
        raise SystemExit(f"{what}: unknown/extra argument(s) {extra}; nothing done")


def _pairs(items: list[str], what: str) -> list[str]:
    """ADDR=VAL hex pairs, at least one; anything else is refused."""
    bad = [x for x in items if not re.fullmatch(r"[0-9a-fA-F]+=[0-9a-fA-F]+", x)]
    if bad or not items:
        raise SystemExit(f"{what}: need ADDR=VAL hex pairs (e.g. FE34=1), got {bad or 'none'}; nothing done")
    return items


def _fwmap(u: dict, given) -> str:
    """Link map of the image on the unit (the flashed tag); addresses from another image would poke the wrong bytes."""
    if given:
        m = Path(str(given))
    else:
        m = FW / f"{_flashed(u).get('tag', '')}.map"
    if not m.is_file():
        raise SystemExit(f"map {m} not found (flash an image first, or --map PATH); nothing done")
    return str(m.resolve())


@command("OSD test events/keys/popup in the running firmware (debug slave 0x35, EDID-guarded)",
         args="[--unit N] [--cmd] [--map F] ACTION...", kind="action")
def cmd_osd(extra: list[str]) -> int:
    import osd_test
    n, u = _unit(extra)
    cmdmode, given = _flag(extra, "--cmd"), _opt(extra, "--map")
    ok = set(osd_test.EVENTS) | set(osd_test.KEYS) | set(osd_test.CMD_ONLY)
    bad = [x for x in extra if x not in ok]
    if bad or not extra:
        raise SystemExit(f"osd: actions are {sorted(ok)}; got {bad or 'none'}; nothing done")
    cmdmode = cmdmode or any(x in osd_test.CMD_ONLY for x in extra)       # popup-only actions imply --cmd
    mp = _fwmap(u, given)
    return _py("osd_test.py", _bus(u), "--serial", u["serial"], "--map", mp, *(["--cmd"] if cmdmode else []), *extra)


@command("eyes-free health of a running unit (debug slave 0x35, 100 kHz): diag stage, loop rate, mode/power state, "
         "input timing vs host, backlight/panel pins, OSD round-trips; PASS/FAIL + exit code",
         args="[--unit N] [--map F] [--host-mode WxH@HZ]", kind="action")
def cmd_health(extra: list[str]) -> int:
    n, u = _unit(extra)
    given, hm = _opt(extra, "--map"), _opt(extra, "--host-mode")
    if given is True or hm is True:
        raise SystemExit("health: --map/--host-mode need a value; nothing done")
    _done(extra, "health")
    return _py("unit_health.py", _bus(u), "--serial", u["serial"], "--map", _fwmap(u, given),
               *(["--host-mode", hm] if hm else ["--gdctl", u["gdctl"]]))


@command("write scaler registers over ISP (MCU halted), read back; --reset reboots", args="[--unit N] [--reset] ADDR=VAL...",
         kind="action")
def cmd_poke(extra: list[str]) -> int:
    n, u = _unit(extra)
    reset = _flag(extra, "--reset")
    pokes = _pairs(extra, "poke")
    return _py("rtd_reg_poke.py", _bus(u), "--serial", u["serial"], *pokes, *(["--reset"] if reset else []))


@command("read scaler register pages / ports over ISP into tmp/regs/ (halts the MCU, resets after)",
         args="[--unit N] [--pages 00,01|all] [--port A:D:N] [--ports all] [--resume F]", kind="action")
def cmd_dump(extra: list[str]) -> int:
    n, u = _unit(extra)
    opts = []
    for flag in ("--pages", "--ports", "--resume"):
        v = _opt(extra, flag)
        if v is not None:
            if v is True:
                raise SystemExit(f"dump: {flag} needs a value; nothing done")
            opts += [flag, v]
    while "--port" in extra:
        v = _opt(extra, "--port")
        if v is True:
            raise SystemExit("dump: --port needs a value; nothing done")
        opts += ["--port", v]
    _done(extra, "dump")
    return _py("rtd_reg_dump.py", _bus(u), "--serial", u["serial"], *opts)


@command("write XDATA bytes in the running firmware over debug slave 0x35", args="[--unit N] [--map F] [--label L] ADDR=VAL...",
         kind="action")
def cmd_dbg_write(extra: list[str]) -> int:
    n, u = _unit(extra)
    given, label = _opt(extra, "--map"), _opt(extra, "--label", "")
    if label is True:
        raise SystemExit("dbg-write: --label needs a value; nothing done")
    writes = _pairs(extra, "dbg-write")
    return _py("rtd_dbg_write.py", _bus(u), "--serial", u["serial"], "--map", _fwmap(u, given), "--label", label, *writes)


@command("read live XDATA via debug slave 0x35 (addr|symbol[:len])", args="[--unit N] [--map F] [--halt] ITEM...",
         kind="action")
def cmd_dbg_read(extra: list[str]) -> int:
    n, u = _unit(extra)
    given, halt = _opt(extra, "--map"), _flag(extra, "--halt")
    bad = [x for x in extra if x.startswith("-")]
    if bad or not extra:
        raise SystemExit(f"dbg-read: need ITEMs (addr|symbol[:len]); bad {bad or 'none'}; nothing done")
    return _py("rtd_dbg_read.py", _bus(u), "--map", _fwmap(u, given), *(["--halt"] if halt else []), *extra)


@command("read the sink's HDMI SCDC registers (0x54), read-only", args="[--unit N]", kind="action")
def cmd_scdc(extra: list[str]) -> int:
    n, u = _unit(extra)
    _done(extra, "scdc")
    return _py("hdmi_scdc.py", _bus(u))


DDC_SUBS = {"list": 0, "get": 1, "sleep": 0, "wake": 0, "brightness": 1}


@command("DDC/CI via ddcutil on the unit's own bus: list | get CODE | sleep | wake | brightness N",
         args="[--unit N] list|get CODE|sleep|wake|brightness N", kind="action")
def cmd_ddc(extra: list[str]) -> int:
    n, u = _unit(extra)
    if not extra or extra[0] not in DDC_SUBS or len(extra) != 1 + DDC_SUBS[extra[0]] \
            or any(x.startswith("-") for x in extra):
        raise SystemExit(f"ddc: one of {DDC_SUBS} (arg counts {list(DDC_SUBS.values())}); got {extra}; nothing done")
    return _py("ddc_ctl.py", "--bus", _bus(u), *extra)


@command("identify the unit: EDID, DDC caps, scaler chip, flash params (ISP session halts the MCU, reboots after)",
         args="[--unit N] [--no-isp] [--json]", kind="action")
def cmd_identify(extra: list[str]) -> int:
    n, u = _unit(extra)
    flags = [f for f in ("--no-isp", "--json") if _flag(extra, f)]
    _done(extra, "identify")
    return _py("rtd_identify.py", _bus(u), *flags)


@command("read-throughput benchmark of the unit's bus (EDID 0x50 + ISP 0x4A reads)", args="[--unit N]", kind="action")
def cmd_bench(extra: list[str]) -> int:
    n, u = _unit(extra)
    _done(extra, "bench")
    return _py("i2c_bench.py", _bus(u))


RECOVER_BUS_WAIT_S = 5.0   # EDID returns ~1-2 s after the relay closes; 5 s = 2.5x; expiry: SystemExit, unit left powered


@command("recover a wedged unit: mains cycle, hold it in the safe window, reflash (default: last flashed)",
         args="[--unit N] [--write-mode byte|burst] [--any-image] [image.bin]", kind="action")
def cmd_recover(extra: list[str]) -> int:
    n, u = _unit(extra)
    wmode = _opt(extra, "--write-mode", "burst")  # burst default: faster, failed pages redone in byte mode (#12)
    any_image = _flag(extra, "--any-image")
    img = _image_arg(extra) or [_flashed(u).get("image", "")]
    # everything that can refuse does so BEFORE the relay: image exists, is a .bin, belongs to this unit (#52.3)
    p = Path(img[0]) if img[0] else None
    if p is None or p.suffix != ".bin" or not p.is_file():
        raise SystemExit(f"recover: no usable image ({img[0] or 'no flashed.json image'!r}); give one; nothing done")
    if not any_image:
        check_image_identity(u, p)
    try:
        bus = _bus(u)                       # unit still answering: identity proven by EDID, before the cycle
    except SystemExit:
        bus = None
    rc = cmd_power_cycle(["--unit", n])
    if rc:
        return rc
    if bus is None:                         # wedged: EDID silent before, so find it once after power-on
        bus = _bus(u, wait_s=RECOVER_BUS_WAIT_S)
    hrc = _diag(u, "--hold", bus=bus)       # best effort: an image without the safe window still flashes over ISP
    if hrc:
        log(f"recover: hold not set (rc={hrc}); flashing over ISP anyway", "WARN")
    return cmd_flash(["--unit", n, "--bus", str(bus), "--write-mode", wmode, *(["--any-image"] if any_image else []), *img])


GDCTL_SHOW_S = 3    # `gdctl show` is one D-Bus call (~0.1 s); 3 s = 30x, expiry -> mode refuses, nothing changed
GDCTL_SET_S = 15    # a modeset of 4 outputs takes ~2-3 s; expiry -> reported, layout left as mutter has it


def gdctl_set_args(show: str, target: str, mode: str) -> list[str]:
    """`gdctl set` args that re-apply EVERY logical monitor from `gdctl show` unchanged (position, primary, scale,
    transform, each monitor's current mode) except `target`, which gets `mode` (#52.7). SystemExit if target is absent."""
    head, sep, tail = show.partition("Logical monitors:")
    if not sep:
        raise SystemExit("mode: no 'Logical monitors:' section in gdctl show; nothing done")
    cur, name = {}, None
    lines = [ln.strip("│├└─ ") for ln in head.splitlines()]
    for i, s_ in enumerate(lines):
        if s_.startswith("Monitor "):
            name = s_.split(" ")[1]
        elif s_ == "Current mode" and name and i + 1 < len(lines):
            cur[name] = lines[i + 1]
    blocks, blk = [], None
    for s_ in (ln.strip("│├└─ ") for ln in tail.splitlines()):
        if s_.startswith("Logical monitor #"):
            blk = {"mons": [], "prim": False, "scale": "1.0", "tf": "normal", "pos": None}
            blocks.append(blk)
        elif blk is None:
            continue
        elif s_.startswith("Position:"):
            blk["pos"] = s_.split(":", 1)[1].strip(" ()").replace(" ", "").split(",")
        elif s_.startswith("Scale:"):
            blk["scale"] = s_.split(":", 1)[1].strip()
        elif s_.startswith("Transform:"):
            blk["tf"] = s_.split(":", 1)[1].strip()
        elif s_.startswith("Primary:"):
            blk["prim"] = s_.endswith("yes")
        elif s_.startswith("Monitors:"):
            continue
        elif re.match(r"[A-Za-z]+-[A-Za-z0-9-]+ \(", s_):
            blk["mons"].append(s_.split(" ")[0])
    if not any(target in b_["mons"] for b_ in blocks):
        raise SystemExit(f"mode: {target} is not an active logical monitor in gdctl show; nothing done")
    args = []
    for b_ in blocks:
        if not b_["mons"] or b_["pos"] is None or any(m not in cur for m in b_["mons"]):
            raise SystemExit(f"mode: cannot read position/mode of logical monitor {b_['mons']}; nothing done")
        args += ["--logical-monitor", *(["--primary"] if b_["prim"] else [])]
        for m in b_["mons"]:
            args += ["--monitor", m, "--mode", mode if m == target else cur[m]]
        args += ["--x", b_["pos"][0], "--y", b_["pos"][1]]
        if float(b_["scale"]) != 1.0:                   # defaults omitted: keeps the old, live-proven command shape
            args += ["--scale", b_["scale"]]
        if b_["tf"] != "normal":
            args += ["--transform", b_["tf"]]
    return args


@command("set the host video mode on a unit's connector (keeps the layout)", args="[--unit N] [--dp] " + "|".join(MODES),
         kind="action")
def cmd_mode(extra: list[str]) -> int:
    _n, u = _unit(extra)
    if len(extra) != 1 or extra[0] not in MODES:
        log(f"mode: one of {', '.join(MODES)}", "ERROR")
        return 2
    try:
        show = subprocess.run(["gdctl", "show"], capture_output=True, text=True, timeout=GDCTL_SHOW_S)
    except subprocess.TimeoutExpired:
        log(f"mode: gdctl show timed out after {GDCTL_SHOW_S} s; nothing changed", "ERROR")
        return 1
    if show.returncode:
        log(f"mode: gdctl show rc={show.returncode}: {show.stderr.strip()}; nothing changed", "ERROR")
        return 1
    args = gdctl_set_args(show.stdout, u["gdctl"], MODES[extra[0]])
    log("run: gdctl set " + " ".join(args))
    try:
        return subprocess.call(["gdctl", "set", *args], timeout=GDCTL_SET_S)
    except subprocess.TimeoutExpired:
        log(f"mode: gdctl set timed out after {GDCTL_SET_S} s", "ERROR")
        return 1


def _register_steps() -> None:
    """Expose each STEPS entry as a first-class command."""
    for name, (summary, _argv, takes_extra) in STEPS.items():
        if name in COMMANDS:
            continue
        COMMANDS[name] = {
            "summary": summary,
            "args": "[extra args passed through]" if takes_extra else "",
            "kind": "step",
            "fn": (lambda n: lambda extra: run_step(n, extra))(name),
        }


_register_steps()


def usage() -> int:
    print(__doc__.split("Scaffold usage:")[0].rstrip())
    print(f"\nUsage: ./dev.py <command> [args]\n")
    # Iterate the kinds actually present, ordered - a hardcoded list silently
    # drops any new kind from --help (selftest catches this).
    order = ["aggregate", "step", "action", "meta"]
    kinds = sorted({m["kind"] for m in COMMANDS.values()},
                   key=lambda k: (order.index(k) if k in order else len(order), k))
    for kind in kinds:
        group = {n: m for n, m in COMMANDS.items() if m["kind"] == kind}
        if not group:
            continue
        print(f"  {kind}:")
        for name, meta in sorted(group.items()):
            print(f"    {name:<12} {meta['summary']}")
        print()
    print(f"Log: {LOG.relative_to(REPO)}   JSON help: ./dev.py describe")
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        return usage()
    name, *extra = argv
    meta = COMMANDS.get(name)
    if meta is None:
        print(f"unknown command: {name!r} — try ./dev.py describe", file=sys.stderr)
        return 2
    rc = meta["fn"](extra)
    return 0 if rc == SKIPPED else rc


if __name__ == "__main__":
    sys.exit(main())
