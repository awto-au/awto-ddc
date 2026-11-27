import re,sys
def fix(path, repl):
    t=open(path).read()
    i=0
    def sub(m):
        nonlocal i
        r=repl[i]; i+=1; return r
    t=re.sub(r'<<<<<<< HEAD\n(.*?)=======\n(.*?)>>>>>>> origin/main\n', lambda m: sub(m), t, flags=re.S)
    assert i==len(repl),(path,i)
    open(path,'w').write(t)
fix('scripts/mcs51_core.c',[
"    DDR_CORE_FIELDS\n    struct san *san;            /* sdcc_san race detector (-DSDCC_SAN builds only; docs/sanitizer.md) */\n",
"    if (!ddr_write_reg(c, a, v)) c->xram[a] = v;\n    SAN_X(c, a, 1);\n",
"        free(c->ddr);\n        SAN_FREE(c);\n",
"    c->code = code; c->fm_tag = tag; c->fm_lacc = la; c->fm_lmiss = lm; c->san = sn;\n    c->ddr = ddr;\n"])
fix('scripts/fastmachine.py',[
"""    so = SO_SAN if os.environ.get("AWTO_SIM_SAN") else SO
    if not so.exists() or so.stat().st_mtime < max(SRC.stat().st_mtime, SRC.with_name("mcs51_ddr.h").stat().st_mtime):
        so.parent.mkdir(parents=True, exist_ok=True)
        tmp = so.with_name(f"{so.name}.{os.getpid()}")
        subprocess.run(["gcc", "-O2", "-shared", "-fPIC", *(["-DSDCC_SAN"] if so is SO_SAN else []), "-o", str(tmp), str(SRC)],
                       check=True, timeout=GCC_TIMEOUT_S, capture_output=True)
        os.replace(tmp, so)                        # atomic: a concurrent build never loads half a file
    L = ctypes.CDLL(str(so))
"""])
