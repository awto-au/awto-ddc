#!/usr/bin/env python3
"""Decode a uVision2 `C51FL=` value into C51 controls: build a one-file Uv2 project with uVision (Wine) and print
the controls uVision passes to C51 (`COMPILER INVOKED BY:` header of the listing).

Usage: keil_uv_flags.py [--group G] C51FL [C51FL...]   e.g. 21646608 (RL6449 FunctionLib / RL6449_Project target)
  --group G: also give the file's group an Options block with C51FL=G (the SDK groups carry 177119914)
Tool tree: $KEIL_C51_TREE or tmp/wine-keil/tree; prefix tmp/wine-keil/prefix. Work: tmp/uvflags/<value>/.
Log: tmp/logs/keil_uv_flags.log
"""
import os
import re
import subprocess
import sys
from pathlib import Path

UV2 = """### uVision2 Project, (C) Keil Software
### Do not modify !

Target (T), 0x0000 // Tools: 'MCS-51'

Group (G)

File 1,1,<.\\t.c><t.c>

Options 1,0,0  // Target 'T'
 Device (W78LE516)
 Vendor (Winbond)
 Cpu (IRAM(0 - 0xFF) XRAM(0- 0xFF) IROM(0-0xFFFF) CLOCK(40000000))
 OutDir (.\\Output\\)
 OutName (t)
 GenApp=1
 GenLib=0
 GenHex=0
 Debug=1
 Browse=1
 LstDir (.\\Output\\)
 MODEL5=2
 ROMSZ5=2
 C51FL={c51fl}
 C51VA=0
 C51MSC ()
 C51DEF ()
 C51UDF ()
 INCC5 ()
 AX51FL=4
 LX51FL=292
EndOpt
"""
GROUP = """
Options 1,1,0  // Group 'G'
 PropFld {{ 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 }}
 IncBld=2
 AlwaysBuild=2
 GenAsm=2
 AsmAsm=2
 PublicsOnly=2
 StopCode=11
 CustArgs ()
 LibMods ()
 BankNo=1
 C51FL={group}
 C51VA=0
 C51MSC ()
 C51DEF ()
 C51UDF ()
 INCC5 ()
 AX51FL=170
 AX51MSC ()
 AX51SET ()
 AX51RST ()
 INCA5 ()
EndOpt
"""


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def decode(root: Path, tree: Path, c51fl: int, group, log) -> str:
    work = root / "tmp" / "uvflags" / (f"{c51fl}-g{group}" if group is not None else str(c51fl))
    (work / "Output").mkdir(parents=True, exist_ok=True)
    (work / "t.c").write_text("unsigned char a, b;\nvoid main(void) { while (1) { a = b + 1; } }\n")
    (work / "t.Uv2").write_text((UV2.format(c51fl=c51fl) + (GROUP.format(group=group) if group is not None else "")).replace("\n", "\r\n"), encoding="latin-1")
    for p in work.glob("Output/*"):
        p.unlink()
    env = dict(os.environ, WINEPREFIX=str(root / "tmp" / "wine-keil" / "prefix"), WINEDEBUG="-all")
    # stall guard: a one-file build takes a few s under Wine; 90 s = a modal dialog (uVision has no headless mode)
    try:
        r = subprocess.run(["wine", str(tree / "UV4" / "UV4.exe"), "-b", "t.Uv2", "-j0", "-o", "build.txt"],
                           cwd=work, env=env, capture_output=True, text=True, timeout=90)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        rc = "timeout 90 s (dialog?)"
    build = (work / "build.txt").read_text(errors="replace") if (work / "build.txt").exists() else ""
    log.write(f"== C51FL={c51fl} group={group} rc={rc}\n{build}\n")
    lst = work / "Output" / "t.lst"
    m = re.search(r"COMPILER INVOKED BY: \S+ t\.c (.*?)\n\s*\n", lst.read_text(errors="replace"), re.S) if lst.exists() else None
    if not m:
        return f"no listing header (rc={rc}); build.txt: {build.strip()[-300:]}"
    txt = re.sub(r"\r?\n\s*-", "", m.group(1)).strip()   # listing wraps at a fixed column, "-" starts the continuation
    log.write(txt + "\n")
    return txt


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = repo_root()
    tree = Path(os.environ.get("KEIL_C51_TREE", root / "tmp" / "wine-keil" / "tree"))
    ini = tree / "TOOLS.INI"
    if not ini.exists():   # uVision finds C51 through TOOLS.INI next to UV4/
        winpath = "Z:" + str(tree / "C51").replace("/", "\\") + "\\"
        ini.write_text(f'[UV2]\r\nORGANIZATION="awto"\r\nNAME="awto"\r\n[C51]\r\nPATH="{winpath}"\r\n'
                       f'VERSION=V9.60\r\nBOOK0=HLP\\Release_Notes.htm("Release Notes",GEN)\r\n')
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    with (root / "tmp" / "logs" / "keil_uv_flags.log").open("a") as log:
        args, group = sys.argv[1:], None
        if args[0] == "--group":
            group, args = int(args[1], 0), args[2:]
        for v in args:
            print(f"C51FL={v}{f' group={group}' if group is not None else ''}: {decode(root, tree, int(v, 0), group, log)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
