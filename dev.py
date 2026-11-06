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
import shutil
import subprocess
import sys
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


@command("remove build output and logs", kind="action")
def cmd_clean(_extra: list[str]) -> int:
    for path in (TMP,):
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


def _edid_serial(bus: int) -> str | None:
    """Text serial (descriptor 0xFF) of the EDID at 0x50 on a bus, or None (no EDID / not readable)."""
    import fcntl
    try:
        fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
    except OSError:
        return None
    try:
        fcntl.ioctl(fd, 0x0703, 0x50)               # I2C_SLAVE
        os.write(fd, b"\x00")
        e = os.read(fd, 128)
    except OSError:
        return None
    finally:
        os.close(fd)
    for i in range(54, 126, 18):
        if e[i:i + 3] == b"\0\0\0" and e[i + 3] == 0xFF:
            return e[i + 5:i + 18].split(b"\n")[0].decode("latin-1").strip()
    return None


def _bus(u: dict) -> int:
    """The bus whose EDID serial is the unit's: the connector's i2c link first, else every display bus
    (NVIDIA has no link). A recable moved units between ports on 2026-11-06 and a flash hit the wrong one."""
    link = (Path("/sys/class/drm") / u.get("_conn", u["connector"]) / "ddc").resolve()
    cands = [int(link.name.split("-")[1])] if link.name.startswith("i2c-") else []
    for d in sorted(Path("/sys/class/i2c-dev").iterdir(), key=lambda p: int(p.name.split("-")[1])):
        n = (d / "name").read_text()
        if ("i915 gmbus" in n or "NVIDIA" in n or "AUX" in n) and int(d.name.split("-")[1]) not in cands:
            cands.append(int(d.name.split("-")[1]))
    for b in cands:
        if _edid_serial(b) == u["serial"]:
            return b
    raise SystemExit(f"{u['serial']}: no bus with that EDID serial (unit off, wedged, or cabled elsewhere); "
                     f"use --bus N only after checking which monitor it is")


def _py(script: str, *args, env: dict | None = None) -> int:
    cmd = [sys.executable, str(REPO / "scripts" / script), *map(str, args)]
    log("run: " + " ".join(cmd[1:]))
    rc = subprocess.call(cmd, cwd=REPO, env={**os.environ, **(env or {})})
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
         args="[--unit N] [--full] [--verify crc|readback] [--write-mode byte|burst] [image.bin]", kind="action")
def cmd_flash(extra: list[str]) -> int:
    n, u = _unit(extra)
    full = _flag(extra, "--full")
    verify = _opt(extra, "--verify", "crc")
    wmode = _opt(extra, "--write-mode", "burst")  # burst default: faster, failed pages redone in byte mode (#12)
    bus = _opt(extra, "--bus")              # recover: bus proven by its own relay cycle (EDID silent while held)
    extra = _image_arg(extra)
    if extra:
        img = Path(extra[0])
        tag = img.name.removesuffix(".bin")
    else:
        tag = (FW / f"{u['serial']}-last.txt").read_text().strip()
        img = FW / f"{tag}.bin"
    if bus:
        log(f"flash: bus {bus} given by caller (identity proven by relay cycle), EDID check skipped")
    rc = _py("rtd_flash_image.py", bus or _bus(u), img, "--serial", u["serial"], "--write", "--no-backup",
             "--tag", tag, "--verify", verify, "--write-mode", wmode, *(["--full"] if full else []))
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
    return _py("power_cycle.py", *extra)


def _diag(u: dict, *args) -> int:
    ids = FW / f"{_flashed(u).get('tag', '')}.ids.tsv"
    more = ["--ids", ids] if ids.is_file() else []
    return _py("rtd_diag.py", _bus(u), *(["--be"] if u["be"] else []), *args, *more)


@command("read the diag block (boot stages, rates, self-test)", args="[--unit N]", kind="action")
def cmd_diag(extra: list[str]) -> int:
    return _diag(_unit(extra)[1])


@command("read the safe-boot / canary / bus-watchdog block", args="[--unit N]", kind="action")
def cmd_safe(extra: list[str]) -> int:
    return _diag(_unit(extra)[1], "--safe")


@command("poll the function-entry trace ring until the unit stops answering", args="[--unit N]", kind="action")
def cmd_trace(extra: list[str]) -> int:
    return _diag(_unit(extra)[1], "--trace")


@command("log which I2C slaves answer through the first seconds after power-on", args="[--unit N] [--window S]",
         kind="action")
def cmd_probe(extra: list[str]) -> int:
    _n, u = _unit(extra)
    return _py("rtd_boot_probe.py", _bus(u), *extra)


@command("recover a wedged unit: mains cycle, hold it in the safe window, reflash (default: last flashed)",
         args="[--unit N] [image.bin]", kind="action")
def cmd_recover(extra: list[str]) -> int:
    n, u = _unit(extra)
    wmode = _opt(extra, "--write-mode", "burst")  # burst default: faster, failed pages redone in byte mode (#12)
    img = _image_arg(extra) or [_flashed(u).get("image", "")]   # validated before the relay is touched
    rc = cmd_power_cycle(["--unit", n])
    if rc:
        return rc
    bus = _bus(u)                           # right after power-on, before the hold silences EDID
    _diag(u, "--hold")                      # best effort: an image without the safe window still flashes over ISP
    return cmd_flash(["--unit", n, "--bus", str(bus), "--write-mode", wmode, *img])


@command("set the host video mode on a unit's connector (keeps the layout)", args="[--unit N] " + "|".join(MODES),
         kind="action")
def cmd_mode(extra: list[str]) -> int:
    _n, u = _unit(extra)
    if not extra or extra[0] not in MODES:
        log(f"mode: one of {', '.join(MODES)}", "ERROR")
        return 2
    show = subprocess.run(["gdctl", "show"], capture_output=True, text=True).stdout
    cur, mon = {}, None
    for line in show.split("Logical monitors:")[0].splitlines():
        s = line.strip("│├└─ ")
        if s.startswith("Monitor "):
            mon = s.split(" ")[1]
        elif mon and "@" in s and "x" in s and mon not in cur and s[0].isdigit():
            cur[mon] = s.split(" ")[0]
    args, prim, pos = [], False, None
    for line in show.split("Logical monitors:")[1].splitlines():
        s = line.strip("│├└─ ")
        if s.startswith("Position:"):
            pos = s.split(":", 1)[1].strip(" ()").replace(" ", "").split(",")
        elif s.startswith("Primary:"):
            prim = s.endswith("yes")
        elif pos and s.split(" ")[0] in {v["gdctl"] for v in _units().values()} | {"DP-2"}:
            mon = s.split(" ")[0]
            args += ["--logical-monitor", *(["--primary"] if prim else []), "--monitor", mon,
                     "--mode", MODES[extra[0]] if mon == u["gdctl"] else cur[mon], "--x", pos[0], "--y", pos[1]]
            pos = None
    log("run: gdctl set " + " ".join(args))
    return subprocess.call(["gdctl", "set", *args])


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
