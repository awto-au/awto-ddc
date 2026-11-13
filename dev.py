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

import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
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
import disk_guard  # noqa: E402  (free-space refusal + tmp/fw pruning, #77)
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
        for p in (LOG, *([_UNIT_LOG] if _UNIT_LOG else [])):
            with p.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")      # file copy is ALWAYS plain
    except OSError:
        pass                                # never let logging kill the run


_UNIT_LOG: Path | None = None               # tmp/logs/unit-<serial>.log once a command picks a unit (_unit)


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

    # #72: every non-step command's --help is side-effect free (intercepted in main(), handler never called)
    # timeout: help prints in <1 s; 30 s only stops a handler that ran anyway (raises -> selftest fails loudly)
    bad = [n for n, m in COMMANDS.items() if m["kind"] != "step" and n != "selftest"
           and subprocess.run([sys.executable, __file__, n, "--help"], capture_output=True, text=True,
                              cwd=REPO, timeout=30).returncode != 0]
    check(f"action --help exits 0 without running ({', '.join(bad) or 'all'})", not bad)

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
SDCC_BE_BIN = "/usr/local/bin"     # awto-sdcc main (= wb_build.py SDCC_INSTALL)
FW = TMP / "fw"
BOOT_PORTS = {"DP": "_D1_INPUT_PORT", "HDMI": "_D2_INPUT_PORT"}               # debug port before first ACTIVE (#28)
MODES = {"1080p50": "1920x1080@50.000", "1080p60": "1920x1080@60.000", "4k30": "3840x2160@30.000",
         "4k60": "3840x2160@60.000", "4k5994": "3840x2160@59.940",
         "off": "off"}                  # off: remove the connector from the desktop, other monitors unchanged


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
    forced = _flag(extra, "--force")        # always consumed, also on a test unit
    if not u.get("test") and not forced:
        raise SystemExit(f"unit {n} is a working screen (devices.json test=false): add --force to touch it")
    global _UNIT_LOG
    _UNIT_LOG = LOGS / f"unit-{u['serial']}.log"    # one file per monitor: dev.py lines + full tool output
    return n, u


BUS_RESCAN_S = 0.25   # one scan of the candidate buses is ~0.1 s; rescan pace while EDID is silent
CONN_TRIES = 3        # EDID reads of the connector's own bus before other buses (~0.5 s worst case, then fallback + WARN)

def _conn_bus(u: dict) -> int | None:
    """The connector's own i2c bus from sysfs (i915 links it; NVIDIA has none -> None)."""
    link = (Path("/sys/class/drm") / u.get("_conn", u["connector"]) / "ddc").resolve()
    return int(link.name.split("-")[1]) if link.name.startswith("i2c-") else None


def _bus(u: dict, wait_s: float = 0.0) -> int:
    """The bus whose EDID serial is the unit's: the connector's i2c link first, else every display bus
    (NVIDIA has no link). A recable moved units between ports on 2026-11-06 and a flash hit the wrong one."""
    cands = [b] if (b := _conn_bus(u)) is not None else []
    cands += [b for b in i2cbus.list_buses(display_only=True) if b not in cands]
    if i2cbus.reset_rate():
        log("bus rate: gmbus_rate module was left loaded; unloaded (100 kHz)", "WARN")
    conn = cands[0] if cands and cands[0] == _conn_bus(u) else None
    for _ in range(CONN_TRIES if conn is not None else 0):   # one missed EDID read fell through to DP-1 AUX (#76)
        if i2cbus.edid_serial(conn) == u["serial"]:
            return conn
        time.sleep(BUS_RESCAN_S)
    t0 = time.monotonic()
    while True:
        for b in cands:
            if i2cbus.edid_serial(b) == u["serial"]:
                if conn is not None and b != conn:
                    log(f"bus: {u['serial']} not on its connector bus {conn} after {CONN_TRIES} reads; using bus {b}", "WARN")
                return b
        if time.monotonic() - t0 >= wait_s:         # wait_s 0 = one scan; >0 = rescan (EDID returns as the scaler boots)
            break
        time.sleep(BUS_RESCAN_S)
    raise SystemExit(f"{u['serial']}: no bus with that EDID serial (unit off, wedged, or cabled elsewhere); "
                     f"use --bus N only after checking which monitor it is")


def _live_bus(u: dict) -> int:
    """For DDC/CI and debug-slave work: the unit's bus whose DDC is live (0x37 ACK or 0x35 answers).
    A unit cabled twice (unit 2: HDMI + DP) has both only on the ACTIVE input's cable; the connector bus may be the idle one."""
    import dbg_link
    c = _conn_bus(u)
    cands = ([c] if c is not None else []) + i2cbus.list_buses(display_only=True)
    mine = [b for b in cands if i2cbus.edid_serial(b) == u["serial"]]
    for b in dict.fromkeys(mine):
        if dbg_link.ddcci_ok(b) or dbg_link.dbg_ok(b):
            return b
    return _bus(u)


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


def check_gated(img: Path, force: bool) -> None:
    """Flash only gated images: tmp/fw/<stem>.gates.json (scripts/fw_gates.py) with this .bin's SHA-256, complete, no FAIL
    (SKIP allowed). Images archived in build-debris/images/ (byte-identical, already flashed once) pass. force: logged, never silent."""
    sha = hashlib.sha256(img.read_bytes()).hexdigest()
    why = None
    arch = REPO / "build-debris" / "images" / img.name
    if arch.is_file() and hashlib.sha256(arch.read_bytes()).hexdigest() == sha:
        log(f"gates: {img.name} is archived in build-debris/images/ (byte-identical, flashed before)")
        return
    rec = next((r for r in (FW / f"{img.stem}.gates.json", img.with_suffix(".gates.json")) if r.is_file()), None)
    if rec is None:
        why = f"no {img.stem}.gates.json (run scripts/fw_gates.py on it)"
    else:
        try:
            d = json.loads(rec.read_text())
            gates = d["gates"]
            failed = sorted(k for k, v in gates.items() if v.get("result") == "FAIL")
            if d.get("sha256") != sha:
                why = f"{rec.name} is for another build (SHA-256 mismatch: image changed after the gates ran)"
            elif failed:
                why = f"{rec.name}: gate(s) FAILED: {', '.join(failed)}"
            elif not d.get("complete"):
                why = f"{rec.name} is partial (fw_gates --only); run the full gate set"
            else:
                skipped = sorted(k for k, v in gates.items() if v.get("result") == "SKIP")
                log(f"gates: {img.name} passed {len(gates) - len(skipped)} gate(s) at {d.get('date')}, {len(skipped)} SKIP"
                    + (f" ({', '.join(skipped)})" if skipped else ""))
                return
        except (OSError, ValueError, KeyError, AttributeError) as e:
            why = f"{rec.name} unreadable ({e})"
    if force:
        log(f"gates: UNGATED IMAGE FLASHED ON PURPOSE (--force-ungated): {img.name}: {why}", "ALERT")
        return
    raise SystemExit(f"flash refused: {img.name}: {why}; --force-ungated to flash it anyway; nothing done")


def _firmware_edid_sector(img: Path) -> int:
    """Return the one sector containing the three served EDID code tables.

    Importing the offline builder keeps this check identical to the one used
    to produce the per-monitor sector.  It runs before any hardware is touched.
    """
    from build_fw_edid_sector import edid_offsets
    offsets = edid_offsets(img.read_bytes())
    return (offsets[0] // 4096) * 4096


def _build_unit_edid_sector(u: dict, img: Path) -> tuple[int, Path, Path, int]:
    """Validate a shared image and emit (address, patched, expected, rc)."""
    sector_addr = _firmware_edid_sector(img)
    edid_dir = FW / "edid"
    stem = img.name.removesuffix(".bin")
    patched = edid_dir / f"{u['serial']}-{stem}-sector.bin"
    expected = edid_dir / f"{stem}-shared-sector.bin"
    rc = _py("build_fw_edid_sector.py", "--image", img, "--serial", u["serial"],
             "--out", patched, "--expect-out", expected)
    return sector_addr, patched, expected, rc


def _record_unit_edid(u: dict, img: Path, sector_addr: int, patched: Path) -> None:
    """Record the verified post-deployment sector in both state manifests."""
    fj = FW / f"{u['serial']}-flashed.json"
    state = _flashed(u)
    state.update({"edid_serial": u["serial"], "shared_firmware": str(img)})
    fj.write_text(json.dumps(state))
    try:
        import flash_state
        manifest = FW / f"{u['serial']}-flash-state.json"
        fs = flash_state.FlashState.load(manifest, u["serial"], lambda s: log(s, "WARN"))
        if fs is not None:
            fs.sectors[sector_addr // 4096] = flash_state.sha(patched.read_bytes())
            fs.save(source=f"{fs.source}+per-monitor-edid")
    except (OSError, ValueError) as e:
        log(f"deploy: could not update flash-state EDID sector ({e}); next flash will drift-check it", "WARN")


TAIL_POLL_S = 0.2       # spool tail: output latency only; the child's exit ends it (no limit: a full byte flash runs minutes)


def _tail_until_exit(p, spool: Path):
    """lines of the detached child's spool file as they appear, until it exits"""
    with spool.open(encoding="utf-8", errors="replace") as fh:
        buf = ""
        while True:
            done = p.poll() is not None
            buf += fh.read()
            *full, buf = buf.split("\n")
            for line in full:
                yield line + "\n"
            if done:
                if buf:
                    yield buf + "\n"
                return
            try:
                p.wait(TAIL_POLL_S)
            except subprocess.TimeoutExpired:
                pass


def _py(script: str, *args, env: dict | None = None, shield: bool = False) -> int:
    """shield: SIGINT/SIGTERM/SIGHUP are forwarded to the child once (it stops at a safe point) and dev.py keeps draining
    its output; otherwise dev.py would die first and its finally (fast_bus unload) would reload the bus mid-flash."""
    cmd = [sys.executable, str(REPO / "scripts" / script), *map(str, args)]
    log("run: " + " ".join(cmd[1:]))
    full_env = {**os.environ, "AWTO_VIA_DEV": "1", **(env or {})}
    sigs = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP) if shield else ()
    old, p, fwd = {}, None, []

    def on_sig(signum, _frame):
        fwd.append(signum)
        if p is not None and len(fwd) == 1:  # once: the child stops at its next safe point
            p.send_signal(signal.SIGTERM)

    def out(line: str) -> None:
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except (OSError, ValueError):    # the shell that ran dev.py is gone: keep the flash going, the logs still fill
            pass

    for s in sigs:
        old[s] = signal.signal(s, on_sig)
    try:
        if shield:      # own session + file output: a group SIGKILL (agent teardown) or dev.py's death can't stop a flash (#156)
            spool = REPO / "tmp" / "logs" / f"{Path(script).stem}.shield.out"
            with spool.open("w", encoding="utf-8") as so:
                p = subprocess.Popen(cmd, cwd=REPO, env={**full_env, "PYTHONUNBUFFERED": "1"}, stdout=so,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            lines = _tail_until_exit(p, spool)
        else:
            p = subprocess.Popen(cmd, cwd=REPO, env={**full_env, "PYTHONUNBUFFERED": "1"},
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            lines = p.stdout
        if _UNIT_LOG is None:
            for line in lines:
                out(line)
        else:                               # tee the tool's output into the unit log, line by line
            with _UNIT_LOG.open("a", encoding="utf-8") as fh:
                for line in lines:
                    out(line)
                    fh.write(f"{_stamp()}  {script}: {line}")
                    fh.flush()
        rc = p.wait()
    finally:
        for s, h in old.items():
            signal.signal(s, h)
    if fwd:
        log(f"{script}: {len(fwd)} stop signal(s) during the run, forwarded; child finished at a safe point (rc={rc})", "WARN")
    log(f"rc={rc}: {script}", "INFO" if rc == 0 else "ERROR")
    return rc


def _flashed(u: dict) -> dict:
    f = FW / f"{u['serial']}-flashed.json"
    return json.loads(f.read_text()) if f.exists() else {}


@command("build firmware for a unit (FRC + rotation by default); frozen to tmp/fw/<serial>-<commit>[-freeze|-nofrc][-audio-test]-be.*",
         args="[--unit N] [--freeze | --no-frc] [--audio-test]", kind="action")
def cmd_build(extra: list[str]) -> int:
    n, u = _unit(extra)
    disk_guard.prune_fw(FW)
    disk_guard.require_free("build", disk_guard.BUILD_FREE_MB)
    freeze, nofrc = _flag(extra, "--freeze"), _flag(extra, "--no-frc")   # FRC + rotation are the default (#165)
    if freeze and nofrc:
        raise SystemExit("build: --freeze needs the frame buffer, --no-frc removes it; nothing done")
    audio_test = _flag(extra, "--audio-test")
    defs = ["-D_AWTO_FREEZE=_ON"] if freeze else ["-D_AWTO_FRC=_OFF"] if nofrc else []
    opt = "-freeze" if freeze else "-nofrc" if nofrc else ""
    if audio_test:
        defs.append("-D_AWTO_AUDIO_TEST")
    if BOOT_PORTS.get(u["input"]):
        defs.append(f"-D_AWTO_BOOT_PORT={BOOT_PORTS[u['input']]}")
    env = {"AWTO_SDCC_BE": "1" if u["be"] else "0", "AWTO_SDCC_BIN": SDCC_BE_BIN, "AWTO_SDCCCALL": "3", "K2S_SDCC_EXTRA": " ".join(defs)}
    rc = _py("fw_build.py", "--serial", u["serial"], env=env)
    if rc:
        return rc
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = "+" if subprocess.run(["git", "diff", "--quiet"], cwd=REPO).returncode else ""
    tag = f"{u['serial']}-{commit}{dirty}{opt}{'-audio-test' if audio_test else ''}-be"
    out = FW / u["serial"]
    for src, ext in ((out / "fw.bin", "bin"), (out / "fw.map", "map"), (TMP / "sdcc-port/trace_ids.tsv", "ids.tsv")):
        shutil.copy2(src, FW / f"{tag}.{ext}")
    (FW / f"{u['serial']}-last.txt").write_text(tag)
    log(f"image tmp/fw/{tag}.bin (unit {n}{', freeze' if freeze else ', no FRC' if nofrc else ''}"
        f"{', internal audio test' if audio_test else ''})", "ALERT")
    return 0


LAYOUT_PID = TMP / "desk_layout_watch.pid"


def _layout_watch() -> None:
    """Keep scripts/desk_layout.py watch running (one per session): a unit reboot re-plugs its monitor and mutter
    then falls back to a row with DP-1 on; the watcher restores Dan's layout for the monitors present (#78).
    OFF unless AWTO_LAYOUT_WATCH=1 (Dan 2026-11-13: it reverted his own one-row layout 4x; DP-1 is now disabled
    in unit 2's firmware, #81, so the fallback it guarded against no longer happens)."""
    if os.environ.get("AWTO_LAYOUT_WATCH") != "1":
        return
    try:
        pid = int(LAYOUT_PID.read_text())
        os.kill(pid, 0)
        if "desk_layout.py" in Path(f"/proc/{pid}/cmdline").read_text(errors="replace"):
            return
    except (OSError, ValueError):
        pass
    out = (LOGS / "desk_layout_watch.out").open("a")
    pr = subprocess.Popen([sys.executable, str(REPO / "scripts/desk_layout.py"), "watch"], stdout=out, stderr=out,
                          stdin=subprocess.DEVNULL, start_new_session=True)
    LAYOUT_PID.write_text(str(pr.pid))
    log(f"layout watcher started (pid {pr.pid}, tmp/logs/desk_layout.log)")


@command("flash an image to a unit over ISP (default: last build); incremental by tmp/fw/<serial>-flash-state.json; GMBUS fallback auto-reset",
         args="[--unit N] [--full] [--any-image] [--force-ungated] [--verify crc|readback] [--write-mode byte|burst] [image.bin]", kind="action")
def cmd_flash(extra: list[str]) -> int:
    _layout_watch()
    n, u = _unit(extra)
    full = _flag(extra, "--full")
    verify = _opt(extra, "--verify", "crc")
    wmode = _opt(extra, "--write-mode", "burst")  # burst default: faster, failed pages redone in byte mode (#12)
    bus = _opt(extra, "--bus")              # recover: bus proven by its own relay cycle (EDID silent while held)
    any_image = _flag(extra, "--any-image")
    ungated = _flag(extra, "--force-ungated")
    extra = _image_arg(extra)
    if extra:
        img = Path(extra[0])
        tag = img.name.removesuffix(".bin")
    else:
        tag = (FW / f"{u['serial']}-last.txt").read_text().strip()
        img = FW / f"{tag}.bin"
    if not any_image:
        check_image_identity(u, img)
    check_gated(img, ungated)
    disk_guard.require_free("flash")        # before the flash-state file is touched (#77)
    identity = None
    if bus:
        identity = "dev.py caller: bus resolved for this unit before the flash (or by its own relay cycle)"
        log(f"flash: bus {bus} given by caller ({identity}); rtd_flash_image checks the EDID serial, silent EDID accepted")
    bus = int(bus or _bus(u))
    # #52.12: from here the flash holds an unknown mix; the old tag/map must not be used by dbg/osd/health.
    # tag "" -> _fwmap/_diag find nothing; image stays so `recover` can retry it.
    fj = FW / f"{u['serial']}-flashed.json"
    before = fj.read_text() if fj.is_file() else None
    fj.write_text(json.dumps({"tag": "", "image": str(img), "attempted": tag}))
    args = [bus, img, "--serial", u["serial"], "--write", "--no-backup",
            *([] if u.get("relay") else ["--per-sector", "--max-min", "20"]),   # no relay: per sector; stop if > 20 min (#71)
            *(["--read-chunk", "256"] if not i2cbus.adapter_name(bus).startswith("i915") else []),
            "--tag", tag, "--verify", verify, "--write-mode", wmode, *(["--full"] if full else []),
            *(["--identity", identity] if identity else [])]
    # rc 5 = read gate refused before any erase: 1 MHz ISP reads corrupt in the low-power state (unit 3, D1
    # NOSIGNAL -> POWER_OFF, #71). rtd_flash_image's exit reset reboots the unit at full clock: retry 1 MHz once, then 100 kHz
    FLASH_RC_INCOMPLETE = 10                # rtd_flash_image.RC_INCOMPLETE
    for attempt in (1, 2, 3):
        with (contextlib.nullcontext(100) if attempt == 3 else i2cbus.fast_bus(bus)) as khz:  # 1 MHz only around ISP
            log(f"flash: bus {bus} at {khz} kHz" + (f" (attempt {attempt})" if attempt > 1 else ""))
            rc = _py("rtd_flash_image.py", *args, shield=True)
        if rc == FLASH_RC_INCOMPLETE and attempt == 1:     # #167: MCU held in ISP on a partial image; a fresh ISP session recovers
            log("flash: image incomplete, MCU held in ISP; rerun once in a fresh ISP session", "WARN")
            if not identity:                    # EDID is silent while the MCU is halted; attempt 1 proved this bus
                args += ["--identity", f"dev.py: EDID serial {u['serial']} checked on bus {bus} by attempt 1; MCU held in ISP since"]
            continue
        if rc != 5 or (attempt == 2 and khz <= 100):
            break
        log(f"flash: read path unstable at {khz} kHz, nothing erased; "
            + ("retry after the reset reboot" if attempt == 1 else "retry at 100 kHz"), "WARN")
        if attempt == 1 and not identity:
            _bus(u, wait_s=RECOVER_BUS_WAIT_S)     # EDID back = rebooted (and the same unit)
    if rc == 5 and before is not None:      # nothing erased: the flash still holds the old image
        fj.write_text(before)
    if rc == 0:
        fj.write_text(json.dumps({"tag": tag, "image": str(img)}))
        if _py("fw_archive.py", img):      # every flashed image kept in build-debris/images; failure doesn't fail the flash
            log(f"flash: fw_archive.py failed for {img} (see tmp/logs/fw_archive.log)")
    return rc


@command("deploy one shared firmware image, then separately program this monitor's unique EDID tables",
         args="[--unit N] [--force] [--force-ungated] [--full] [--verify crc|readback] [--write-mode byte|burst] image.bin",
         kind="action")
def cmd_deploy(extra: list[str]) -> int:
    """Safe production deployment: common firmware first, per-unit EDID second.

    ``build --unit`` still makes useful test images, but it is not the
    multi-monitor deployment procedure.  Deployment deliberately accepts a
    shared image regardless of the serial compiled into its EDID tables, then
    replaces only the EDID-table sector for the selected physical monitor.
    """
    n, u = _unit(extra)
    full = _flag(extra, "--full")
    verify = _opt(extra, "--verify", "crc")
    wmode = _opt(extra, "--write-mode", "burst")
    ungated = _flag(extra, "--force-ungated")
    image_args = _image_arg(extra)
    if not image_args:
        raise SystemExit("deploy: give the shared firmware image explicitly; nothing done")
    img = Path(image_args[0])
    check_gated(img, ungated)       # before the EDID step and any hardware; cmd_flash re-checks (same result)

    # Validate the image and generate both sides of the sector guard before
    # resolving/touching a monitor.
    sector_addr, patched, expected, rc = _build_unit_edid_sector(u, img)
    if rc:
        return rc

    # Resolve identity while the unit still has its own EDID.  The shared
    # image may temporarily expose its build serial until the sector step.
    bus = _bus(u)
    flash_args = ["--unit", n, "--bus", str(bus), "--any-image",
                  "--verify", verify, "--write-mode", wmode,
                  *(["--full"] if full else []),
                  *(["--force"] if not u.get("test") else []), *(["--force-ungated"] if ungated else []), str(img)]
    rc = cmd_flash(flash_args)
    if rc:
        log(f"deploy: shared firmware failed (rc={rc}); EDID was not programmed", "ERROR")
        return rc

    log(f"deploy: shared image verified; programming {u['serial']} EDID in sector 0x{sector_addr:x}")
    rc = _py("rtd_flash_sector.py", bus, hex(sector_addr), patched,
             "--expect-current", expected, "--write", shield=True)
    if rc:
        log("deploy: FIRMWARE IS PRESENT BUT PER-MONITOR EDID FAILED; retry deploy on this same bus", "FATAL")
        return rc

    _record_unit_edid(u, img, sector_addr, patched)
    log(f"deploy complete: unit {n}, shared image {img.name}, EDID {u['serial']}", "ALERT")
    return 0


@command("program only this monitor's EDID tables from a shared firmware image (deploy recovery)",
         args="[--unit N] [--force] [--bus N] image.bin", kind="action")
def cmd_edid(extra: list[str]) -> int:
    """Program the per-monitor EDID sector without reflashing common firmware."""
    n, u = _unit(extra)
    given_bus = _opt(extra, "--bus")
    image_args = _image_arg(extra)
    if not image_args:
        raise SystemExit("edid: give the shared firmware image explicitly; nothing done")
    if given_bus is True:
        raise SystemExit("edid: --bus needs a value; nothing done")
    img = Path(image_args[0])
    sector_addr, patched, expected, rc = _build_unit_edid_sector(u, img)
    if rc:
        return rc
    bus = int(given_bus) if given_bus is not None else _bus(u)
    if given_bus is not None:
        log(f"edid: using caller-proven physical bus {bus} for unit {n}", "WARN")
    rc = _py("rtd_flash_sector.py", bus, hex(sector_addr), patched,
             "--expect-current", expected, "--write", shield=True)
    if rc == 0:
        _record_unit_edid(u, img, sector_addr, patched)
        log(f"EDID complete: unit {n}, {u['serial']}", "ALERT")
    return rc


@command("KVM: switch every unit's input at once over DDC/CI VCP 0x60, one process per bus (scripts/kvm.py, #60)",
         args="<D1|D2|D3|dp|hdmi1|hdmi2|next> [--units 1,2,3] [--ddcutil] [--verify] [--dry-run]", kind="action")
def cmd_kvm(extra: list[str]) -> int:
    return _py("kvm.py", *extra)


@command("mains power-cycle a unit via its relay (scripts/power_cycle.py)", args="[--unit N] [--on|--off]",
         kind="action")
def cmd_power_cycle(extra: list[str]) -> int:
    _layout_watch()
    n, u = _unit(extra)
    if not u["relay"]:
        log(f"unit {n} has no relay (scripts/devices.json)", "ERROR")
        return 1
    return _py("power_cycle.py", "--relay", u["relay"], *extra)


@command("which monitor input the cable is in, from the EDID port tag (scripts/edid_port.py, read-only; #28)",
         args="[--unit N]", kind="action")
def cmd_port(extra: list[str]) -> int:
    _n, u = _unit(extra)
    _done(extra, "port")
    sysfs = Path("/sys/class/drm") / u.get("_conn", u["connector"]) / "edid"
    return _py("edid_port.py", _bus(u), "--serial", u["serial"], "--sysfs", sysfs)


@command("active input port over ISP 0x4A (TMDS Rx2/Rx3 lock, scripts/isp_port.py); --draw leaves a panel up, MCU halted,"
         " until isp-port --clear (scaler reset)", args="[--unit N] [--draw | --clear]", kind="action")
def cmd_isp_port(extra: list[str]) -> int:
    _n, u = _unit(extra)
    draw, clear = _flag(extra, "--draw"), _flag(extra, "--clear")
    _done(extra, "isp-port")
    if clear:       # MCU halted by --draw: EDID may read silent, so the bus is the one whose 0x4A is in ISP mode
        b = next((x for x in i2cbus.list_buses(display_only=True) if _isp_halted(x)), None)
        if b is None:
            log("isp-port --clear: no bus with 0x4A in ISP mode (0x6F bit7); nothing to clear", "ERROR")
            return 1
        return _py("isp_port.py", b, "--serial", u["serial"], "--draw", "--reset",
                   "--identity", f"bus {b}: 0x4A reg 0x6F bit7 set (halted by isp-port --draw)")
    tag = _flashed(u).get("tag", "")
    m = FW / f"{tag}.map"
    return _py("isp_port.py", _bus(u), "--serial", u["serial"], *(["--map", m] if m.is_file() else []),
               "--tag", tag.removeprefix(u["serial"] + "-"), *(["--draw"] if draw else []))


def _isp_halted(bus: int) -> bool:
    try:
        with i2cbus.Bus(bus) as b:
            return bool(b.read(0x4A, 0x6F, 1)[0] & 0x80)
    except OSError:
        return False


@command("reboot the scaler MCU over ISP (0xEE <- 0x02), <1 s; falls back to nothing: use power-cycle if 0x4A is silent",
         args="[--unit N]", kind="action")
def cmd_reset(extra: list[str]) -> int:
    _layout_watch()
    _n, u = _unit(extra)
    _done(extra, "reset")
    return _py("rtd_reset.py", _bus(u), "--serial", u["serial"])


def _dbg_py(bus: int, script: str, *args, **kw) -> int:
    """_py with debug slave 0x35 on the unit's DDC for the run (#79 runtime swap: DDC/CI owns it by default); swapped
    back afterwards only if this call swapped it (scripts/dbg_link.py)."""
    import dbg_link
    with dbg_link.linked(int(bus)):
        return _py(script, *args, **kw)


def _diag(u: dict, *args, bus: int | None = None) -> int:
    ids = FW / f"{_flashed(u).get('tag', '')}.ids.tsv"
    more = ["--ids", ids] if ids.is_file() else []
    b = bus if bus is not None else _live_bus(u)
    return _dbg_py(b, "rtd_diag.py", b, *(["--be"] if u["be"] else []), *args, *more)


@command("#79 debug link: on = debug slave 0x35 onto the unit's DDC (DDC/CI owns it by default; on --minutes N, "
         "255 = until off), off = back to DDC/CI, state = who answers", args="[--unit N] on|off|state [--minutes N]",
         kind="action")
def cmd_link(extra: list[str]) -> int:
    _n, u = _unit(extra)
    mins = _opt(extra, "--minutes")
    if mins is True or (extra[:1] not in (["on"], ["off"], ["state"])) or len(extra) != 1:
        raise SystemExit("link: on|off|state [--minutes N]; nothing done")
    return _py("dbg_link.py", extra[0], _bus(u), *(["--minutes", mins] if mins else []))


@command("read the diag block (boot stages, rates, self-test); --messages [--secs S] polls debug messages; "
         "--release un-halts a firmware left stopped by a killed --messages; --watch N re-reads",
         args="[--unit N] [--messages [--secs S] | --release | --watch N]", kind="action")
def cmd_diag(extra: list[str]) -> int:
    n, u = _unit(extra)
    args = [f for f in ("--messages", "--release") if _flag(extra, f)]
    if len(args) > 1:
        raise SystemExit("diag: --messages and --release are exclusive; nothing done")
    for flag in ("--secs", "--watch"):
        v = _opt(extra, flag)
        if v is None:
            continue
        try:
            float(v)
        except (TypeError, ValueError):
            raise SystemExit(f"diag: {flag} needs a number; nothing done")
        if flag == "--secs" and "--messages" not in args:
            raise SystemExit("diag: --secs only applies to --messages; nothing done")
        args += [flag, v]
    _done(extra, "diag")
    return _diag(u, *args)


@command("read the safe-boot / canary / bus-watchdog block", args="[--unit N]", kind="action")
def cmd_safe(extra: list[str]) -> int:
    u = _unit(extra)[1]
    _done(extra, "safe")
    return _diag(u, "--safe")


@command("poll the function-entry trace ring until the unit stops answering", args="[--unit N]", kind="action")
def cmd_trace(extra: list[str]) -> int:
    u = _unit(extra)[1]
    _done(extra, "trace")
    return _diag(u, "--trace")


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
    b = _live_bus(u)
    return _dbg_py(b, "osd_test.py", b, "--serial", u["serial"], "--map", mp, *(["--cmd"] if cmdmode else []), *extra)


@command("clear the OSD diagnostics console (= osd clear, test cmd 0x27)", args="[--unit N] [--map F]", kind="action")
def cmd_diag_clear(extra: list[str]) -> int:
    return cmd_osd([*extra, "clear"])


@command("speaker ear test (#94): diagnostics console opened, firmware ear-test steps (VCP 0x63: speaker + amp, no amp, "
         "volume levels), each step's console line then its tones (each frequency announced on the console), volume checked after; "
         "times in tmp/logs/audio_test.log",
         args="[--unit N] [--only 1,2,..] [--freqs 200,1000,4000] [--secs S] [--map F]", kind="action")
def cmd_sound_test(extra: list[str]) -> int:
    n, u = _unit(extra)
    given = _opt(extra, "--map")
    more = []
    for flag, pat in (("--only", r"\d+(,\d+)*"), ("--freqs", r"\d+(,\d+)*"), ("--secs", r"\d+(\.\d+)?")):
        v = _opt(extra, flag)
        if v is None:
            continue
        if v is True or not re.fullmatch(pat, str(v)):
            raise SystemExit(f"sound-test: {flag} needs a value like {pat}; nothing done")
        more += [flag, v]
    _done(extra, "sound-test")
    b = _live_bus(u)        # DDC/CI (VCP 0x63) must answer; audio_test swaps the debug link in only to open the console
    return _py("audio_test.py", "steps", "--bus", b, "--serial", u["serial"], "--connector", u.get("_conn", u["connector"]),
               "--map", _fwmap(u, given), *more)


@command("settings registry (#67) on a unit or the sim: list | get NAME | set NAME VALUE | defaults | save | rows "
         "(rows = the table, offline)", args="[--unit N | --sim BIN] [--map F] [--no-confirm] CMD [ARGS]", kind="action")
def cmd_settings(extra: list[str]) -> int:
    sim, given = _opt(extra, "--sim"), _opt(extra, "--map")
    if extra[:1] == ["rows"]:
        return _py("settings_cli.py", "--map", "-", *extra)
    if sim:
        mp = given or str(Path(sim).with_suffix(".map"))
        return _py("settings_cli.py", "--sim", sim, "--map", mp, *extra)
    n, u = _unit(extra)
    b = _live_bus(u)
    return _dbg_py(b, "settings_cli.py", "--bus", str(b), "--serial", u["serial"], "--map", _fwmap(u, given), *extra)


@command("our OSD menu over I2C (#67): keyboard uses the computer arrows; state | key K | hold KEYS MS | open PAGE | "
         "select ITEM | set ITEM V | get ITEM | back | close | walk (every page + item checked against the registry; "
         "--png DIR renders pages in the sim)",
         args="[--unit N | --sim BIN] [--map F] [--png DIR] CMD [ARGS]", kind="action")
def cmd_menu(extra: list[str]) -> int:
    sim, given, png = _opt(extra, "--sim"), _opt(extra, "--map"), _opt(extra, "--png")
    pa = ["--png", png] if png else []
    if sim:
        return _py("menu_cli.py", "--sim", sim, "--map", given or str(Path(sim).with_suffix(".map")), *pa, *extra)
    n, u = _unit(extra)
    b = _live_bus(u)
    return _dbg_py(b, "menu_cli.py", "--bus", str(b), "--serial", u["serial"], "--map", _fwmap(u, given), *pa, *extra)


@command("full-screen landscape Pac-Man demo: computer arrow keys steer; Escape/Q closes",
         args="[--unit N] [--map F]", kind="action")
def cmd_pacman(extra: list[str]) -> int:
    n, u = _unit(extra)
    given = _opt(extra, "--map")
    _done(extra, "pacman")
    b = _live_bus(u)
    return _dbg_py(b, "pacman_cli.py", b, "--serial", u["serial"], "--map", _fwmap(u, given))


@command("Pygame RTD OSD emulator using the linked firmware's actual glyph/map/palette bytes",
         args="[BIN] [--map F] [--cols N] [--rows N] [--char-width N] [--row-height N] [--steps N] "
              "[--no-font24] [--no-double-x] [--no-double-y] [--fullscreen] [--screenshot PNG]", kind="action")
def cmd_pacman_sim(extra: list[str]) -> int:
    given, shot = _opt(extra, "--map"), _opt(extra, "--screenshot")
    fullscreen = _flag(extra, "--fullscreen")
    geometry = []
    for flag in ("--cols", "--rows", "--char-width", "--row-height", "--steps"):
        if (value := _opt(extra, flag)) is not None:
            if value is True:
                raise SystemExit(f"pacman-sim: {flag} needs a value")
            geometry += [flag, str(value)]
    for flag in ("--no-font24", "--no-double-x", "--no-double-y"):
        if _flag(extra, flag):
            geometry.append(flag)
    image = _image_arg(extra)
    if image:
        img = Path(image[0])
        mp = Path(str(given)) if given else img.with_suffix(".map")
    else:
        # Unit 2 is the declared test monitor; its flash manifest identifies
        # the exact linked image without probing or touching hardware.
        u = _units()["2"]
        state = _flashed(u)
        img = Path(state.get("image", ""))
        mp = Path(str(given)) if given else FW / f"{state.get('tag', '')}.map"
    if not img.is_file() or not mp.is_file():
        raise SystemExit(f"pacman-sim: need matching BIN+MAP, got {img} and {mp}")
    py = "/usr/bin/python3"                         # Fedora pygame package; project CPython 3.15t has no wheel
    cmd = [py, str(REPO / "scripts/pacman_emulator.py"), str(img.resolve()), str(mp.resolve()),
           *geometry, *(["--fullscreen"] if fullscreen else []), *(["--screenshot", str(shot)] if shot else [])]
    log("run: " + " ".join(cmd[1:]))
    rc = subprocess.call(cmd, cwd=REPO)
    log(f"rc={rc}: pacman emulator", "INFO" if rc == 0 else "ERROR")
    return rc


@command("eyes-free health of a running unit (debug slave 0x35, 100 kHz): diag stage, loop rate, mode/power state, "
         "input timing vs host, backlight/panel pins, OSD round-trips; PASS/FAIL + exit code",
         args="[--unit N] [--map F] [--host-mode WxH@HZ] | --sim BIN", kind="action")
def cmd_health(extra: list[str]) -> int:
    sim = _opt(extra, "--sim")
    if sim:                                                  # firmware simulator, no hardware (#38); map = BIN with .map
        if sim is True or not Path(str(sim)).is_file() or not Path(str(sim)).with_suffix(".map").is_file():
            raise SystemExit("health --sim BIN: needs an image path with BIN's .map beside it; nothing done")
        _done(extra, "health --sim")
        return _py("unit_health.py", "--sim", Path(str(sim)).resolve(), Path(str(sim)).resolve().with_suffix(".map"))
    n, u = _unit(extra)
    given, hm = _opt(extra, "--map"), _opt(extra, "--host-mode")
    if given is True or hm is True:
        raise SystemExit("health: --map/--host-mode need a value; nothing done")
    _done(extra, "health")
    b = _live_bus(u)
    return _dbg_py(b, "unit_health.py", b, "--serial", u["serial"], "--map", _fwmap(u, given),
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
    b = _live_bus(u)
    return _dbg_py(b, "rtd_dbg_write.py", b, "--serial", u["serial"], "--map", _fwmap(u, given), "--label", label, *writes)


@command("read live XDATA via debug slave 0x35 (addr|symbol[:len])", args="[--unit N] [--map F] [--halt] ITEM...",
         kind="action")
def cmd_dbg_read(extra: list[str]) -> int:
    n, u = _unit(extra)
    given, halt = _opt(extra, "--map"), _flag(extra, "--halt")
    bad = [x for x in extra if x.startswith("-")]
    if bad or not extra:
        raise SystemExit(f"dbg-read: need ITEMs (addr|symbol[:len]); bad {bad or 'none'}; nothing done")
    b = _live_bus(u)
    return _dbg_py(b, "rtd_dbg_read.py", b, "--map", _fwmap(u, given), *(["--halt"] if halt else []), *extra)


@command("unused GPIO inputs: snapshot | watch changes | open/close the live OSD screen over I2C",
         args="[--unit N] [--map F] [--secs S] snapshot|watch|open|close", kind="action")
def cmd_gpio(extra: list[str]) -> int:
    n, u = _unit(extra)
    given, secs = _opt(extra, "--map"), _opt(extra, "--secs")
    if len(extra) != 1 or extra[0] not in ("snapshot", "watch", "open", "close"):
        raise SystemExit("gpio: snapshot|watch|open|close [--secs S]; nothing done")
    if secs is True:
        raise SystemExit("gpio: --secs needs a number; nothing done")
    b = _live_bus(u)
    return _dbg_py(b, "gpio_diag.py", b, extra[0], "--serial", u["serial"], "--map", _fwmap(u, given),
                   *(["--secs", secs] if secs else []))


@command("read the sink's HDMI SCDC registers (0x54), read-only", args="[--unit N]", kind="action")
def cmd_scdc(extra: list[str]) -> int:
    n, u = _unit(extra)
    _done(extra, "scdc")
    return _py("hdmi_scdc.py", _bus(u))


DDC_SUBS = {"list": 0, "get": 1, "set": 2, "sleep": 0, "wake": 0, "brightness": 1}


@command("DDC/CI via ddcutil on the unit's own bus: list | get CODE | set CODE VALUE | sleep | wake | brightness N",
         args="[--unit N] list|get CODE|set CODE VALUE|sleep|wake|brightness N", kind="action")
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


def _flashed_has_safe_block(u: dict) -> bool:
    """True only if the map of the image on the unit (flashed tag) defines _g_stAwtoSafe; no map = no hold (#52)."""
    m = FW / f"{_flashed(u).get('tag', '')}.map"
    try:
        return re.search(r"^\s+[0-9A-Fa-f]{8}\s+_g_stAwtoSafe\b", m.read_text(errors="replace"), re.M) is not None
    except OSError:
        return False


RECOVER_BUS_WAIT_S = 5.0   # EDID returns ~1-2 s after the relay closes; 5 s = 2.5x; expiry: SystemExit, unit left powered


@command("recover a wedged unit: mains cycle, hold it in the safe window, reflash (default: last flashed)",
         args="[--unit N] [--bus N] [--write-mode byte|burst] [--any-image] [--force-ungated] [image.bin]", kind="action")
def cmd_recover(extra: list[str]) -> int:
    _layout_watch()
    n, u = _unit(extra)
    wmode = _opt(extra, "--write-mode", "burst")  # burst default: faster, failed pages redone in byte mode (#12)
    any_image = _flag(extra, "--any-image")
    ungated = _flag(extra, "--force-ungated")
    given_bus = _opt(extra, "--bus")        # caller-proven bus (EDID silent); still needs this unit's relay cycle
    img = _image_arg(extra) or [_flashed(u).get("image", "")]
    # everything that can refuse does so BEFORE the relay: image exists, is a .bin, belongs to this unit (#52.3)
    p = Path(img[0]) if img[0] else None
    if p is None or p.suffix != ".bin" or not p.is_file():
        raise SystemExit(f"recover: no usable image ({img[0] or 'no flashed.json image'!r}); give one; nothing done")
    if not any_image:
        check_image_identity(u, p)
    check_gated(p, ungated)                 # refuse before the relay too
    try:
        bus = _bus(u)                       # unit still answering: identity proven by EDID, before the cycle
    except SystemExit:
        bus = None
    if bus is not None and _py("rtd_reset.py", bus, "--serial", u["serial"]) == 0:
        log("recover: ISP reset sent (fast path, no mains cycle)")   # 0x4A answered: no 8 s relay cycle needed
        return cmd_flash(["--unit", n, "--bus", str(bus), "--write-mode", wmode,
                          *(["--any-image"] if any_image else []),
                          *(["--force-ungated"] if ungated else []), *img])
    rc = cmd_power_cycle(["--unit", n])
    if rc:
        return rc
    if bus is None:                         # wedged: EDID silent before, so find it once after power-on
        try:
            bus = _bus(u, wait_s=RECOVER_BUS_WAIT_S)
        except SystemExit:
            # EDID silent even after the cycle (sector 0 / EDID code erased, #71): --bus, else the connector's link
            bus = int(given_bus) if given_bus and given_bus is not True else _conn_bus(u)
            if bus is None:
                raise
            log(f"recover: EDID silent after the relay cycle; bus {bus} = "
                + ("--bus" if given_bus else f"connector {u['connector']}'s ddc link (devices.json)")
                + "; identity from this unit's own relay", "WARN")
    if _flashed_has_safe_block(u):          # --hold writes the marker at 0xF6B0: ordinary XDATA on images without the block (#52)
        hrc = _diag(u, "--hold", bus=bus)   # best effort: a failed hold still flashes over ISP
        if hrc:
            log(f"recover: hold not set (rc={hrc}); flashing over ISP anyway", "WARN")
    else:
        log("recover: flashed image has no _g_stAwtoSafe in its map; hold skipped, flashing over ISP", "WARN")
    return cmd_flash(["--unit", n, "--bus", str(bus), "--write-mode", wmode, *(["--any-image"] if any_image else []),
                          *(["--force-ungated"] if ungated else []), *img])


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
    for b_ in blocks:
        if not b_["mons"] or b_["pos"] is None or any(m not in cur for m in b_["mons"]):
            raise SystemExit(f"mode: cannot read position/mode of logical monitor {b_['mons']}; nothing done")

    def rect(b_, m_):                                   # logical rectangle of a block showing mode string m_
        w, h = (int(v) for v in m_.split("@")[0].split("x"))
        s = float(b_["scale"])
        return int(b_["pos"][0]), int(b_["pos"][1]), w / s, h / s

    tb = next(b_ for b_ in blocks if target in b_["mons"])
    if mode == "off":                                   # drop target's logical monitor, everything else unchanged
        if len(blocks) == 1:
            raise SystemExit(f"mode: {target} is the only logical monitor; nothing done")
        if tb["prim"]:
            raise SystemExit(f"mode: {target} is primary; nothing done")
        rx, ry, rw, _rh = rect(tb, cur[target])
        blocks.remove(tb)
        for b_ in blocks:                               # close the gap: same-row monitors right of it move left
            if int(b_["pos"][1]) == ry and int(b_["pos"][0]) > rx:
                b_["pos"][0] = str(int(int(b_["pos"][0]) - rw))
        target, mode = None, None
    else:
        _, _, w, h = rect(tb, mode)
        ox, oy, ow, oh = rect(tb, cur[target])
        others = [rect(b_, cur[b_["mons"][0]]) for b_ in blocks if b_ is not tb]

        def touch(edge_a, edge_b, lo_a, hi_a, lo_b, hi_b):   # shared edge with overlapping span
            return abs(edge_a - edge_b) < 1 and lo_a < hi_b and lo_b < hi_a
        right = any(touch(bx, ox + ow, by, by + bh, oy, oy + oh) for bx, by, bw, bh in others)
        left = any(touch(bx + bw, ox, by, by + bh, oy, oy + oh) for bx, by, bw, bh in others)
        below = any(touch(by, oy + oh, bx, bx + bw, ox, ox + ow) for bx, by, bw, bh in others)
        above = any(touch(by + bh, oy, bx, bx + bw, ox, ox + ow) for bx, by, bw, bh in others)
        # resize keeping the edge that touches a neighbour (grow or shrink); bbox normalised below
        nx = ox + ow - w if right and not left else ox
        ny = oy + oh - h if below and not above else oy
        overlap = any(nx < bx + bw and bx < nx + w and ny < by + bh and by < ny + h for bx, by, bw, bh in others)
        keep = int(mode.split("x")[0]) / ow
        if overlap and keep >= 1:                       # neighbours on both sides: keep the old footprint by scale
            tb["scale"] = f"{keep:g}"
            nx, ny = ox, oy
        tb["pos"] = [str(round(nx)), str(round(ny))]
        mx = min(int(b_["pos"][0]) for b_ in blocks)    # mutter wants the bounding box at (0,0) ("positions are offset")
        my = min(int(b_["pos"][1]) for b_ in blocks)
        for b_ in blocks:
            b_["pos"] = [str(int(b_["pos"][0]) - mx), str(int(b_["pos"][1]) - my)]
    args = []
    for b_ in blocks:
        args += ["--logical-monitor", *(["--primary"] if b_["prim"] else [])]
        for m in b_["mons"]:
            args += ["--monitor", m, "--mode", mode if m == target else cur[m]]
        args += ["--x", b_["pos"][0], "--y", b_["pos"][1]]
        if float(b_["scale"]) != 1.0:                   # defaults omitted: keeps the old, live-proven command shape
            args += ["--scale", b_["scale"]]
        if b_["tf"] != "normal":
            args += ["--transform", b_["tf"]]
    return args


def _dp_mirror_args(show: str, u: dict, on: bool) -> list[str]:
    """Dan's layout with DP-1 added to (on) or removed from (off) the HDMI connector's logical monitor, at the HDMI mode:
    same slot, same position, nothing else moves (#60 input-switch tests)."""
    hdmi, dp = _units()[u["_n"]]["gdctl"], u["gdctl"]
    cur = re.search(rf"Monitor {re.escape(hdmi)} .*?Current mode\s*\n[│├└─\s]*(\S+@\S+)", show, re.S)
    if not cur:
        raise SystemExit(f"mode --dp: no current mode for {hdmi}; nothing changed")
    m = cur.group(1)
    alone = re.search(rf"Monitors: \(1\)\s*\n[│├└─\s]*{re.escape(dp)} \(", show)
    if alone:                                         # DP-1 is its own logical monitor (mutter re-adds it on unit 3 hot-plugs)
        args = gdctl_set_args(show, dp, "off")        # drop it, gap closed
        if not on:
            return args
    else:
        args = gdctl_set_args(show, hdmi, m)
    out, k = [], 0
    while k < len(args):                              # drop an existing DP-1 entry first
        if args[k] == "--monitor" and args[k + 1] == dp:
            k += 4; continue
        out.append(args[k]); k += 1
    if on:
        i = out.index(hdmi)
        out[i + 3:i + 3] = ["--monitor", dp, "--mode", m]
    return out


@command("set the host video mode on a unit's connector (keeps the layout); --dp mirror|off: DP-1 mirrored into the HDMI slot",
         args="[--unit N] [--dp] " + "|".join(MODES) + " | --dp mirror|off",
         kind="action")
def cmd_mode(extra: list[str]) -> int:
    n, u = _unit(extra)
    if u.get("input") == "DP" and len(extra) == 1 and extra[0] in ("mirror", "off"):
        show = subprocess.run(["gdctl", "show"], capture_output=True, text=True, timeout=GDCTL_SHOW_S).stdout
        on = extra[0] == "mirror"
        args = _dp_mirror_args(show, {**u, "_n": n}, on)
        if on:                                        # layout watcher: the mirror is allowed, not mutter's fallback
            _py("desk_layout.py", "mirror", u["gdctl"], _units()[n]["gdctl"])
            _layout_watch()
        log("run: gdctl set (temporary, no keep-changes dialog) " + " ".join(args))
        rc = subprocess.call(["gdctl", "set", *args], timeout=GDCTL_SET_S)
        if not on and rc == 0:
            _py("desk_layout.py", "unmirror")
        return rc
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


@command("eyes-free host-mode sweep of a test unit (what works: OK/FRC/GARBLE/NOSUPPORT...), 1080p60 after each; log tmp/logs/mode_sweep.log",
         args="[--unit N] [--dry-run] [--modes WxH@HZ,...] [--label L] [--resume TSV]", kind="action")
def cmd_sweep(extra: list[str]) -> int:
    n, u = _unit(extra)
    opts = [f for f in ("--dry-run",) if _flag(extra, f)] + (["--dp"] if u.get("input") == "DP" else [])   # _unit took --dp
    for flag in ("--modes", "--label", "--resume"):
        v = _opt(extra, flag)
        if v is True:
            raise SystemExit(f"sweep: {flag} needs a value; nothing done")
        if v is not None:
            opts += [flag, v]
    _done(extra, "sweep")
    return _py("mode_sweep.py", "--unit", n, *opts)


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
    # #72: an action's --help must never reach its handler (build --help built and repointed last.txt)
    if meta["kind"] != "step" and any(a in ("-h", "--help") for a in extra):
        print(f"./dev.py {name} {meta.get('args', '')}".rstrip() + f"\n  {meta['summary']}")
        return 0
    rc = meta["fn"](extra)
    return 0 if rc == SKIPPED else rc


if __name__ == "__main__":
    sys.exit(main())
