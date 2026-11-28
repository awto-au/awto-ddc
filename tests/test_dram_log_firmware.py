"""Compile the production C publisher, selector and initializer against a DDR stub.

This runs real function bodies from hostnote.c, including CRC and boot recovery;
only port I/O, clock and boot reason are substituted. No cross compiler or
physical monitor is involved. The SDCC overlay/bank build remains a release gate.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fw/log/hostnote.c"


def function(source, name):
    # Find the definition without depending on comments / argument spelling.
    import re
    match = re.search(r"static [^;{}\n]+\b" + name + r"\([^;{}]*\)[^{}]*\{", source)
    assert match is not None, name
    start, pos, depth = match.start(), match.end(), 1
    while depth:
        depth += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[start:pos]


def test_production_firmware_publication_and_boot_recovery(tmp_path):
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("native C compiler required for firmware function harness")
    source = SOURCE.read_text()
    definitions = "\n".join(x for x in source.splitlines() if x.startswith("#define AWTO_DLOG_"))
    # AWTO_DLOG_UNIT is a single-line macro in the real source.
    funcs = "\n\n".join(function(source, name) for name in (
        "AwtoDlSum", "AwtoDlHdrCrc", "AwtoDlHdr", "AwtoDlEntryOk", "AwtoDlScan", "AwtoDlHdrOk", "AwtoDlPublication", "AwtoDlReadHdr", "AwtoDlInit"))
    prelude = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef uint8_t BYTE;
typedef uint16_t WORD;
typedef uint32_t DWORD;
#define AWTO_DLOG_HDR_UNITS 0x3ebffeUL
#define AWTO_DLOG_UNITS0 0x3ec000UL
#define AWTO_DLOG_SLOTS 32768UL
#define AWTO_DLOG_ENTRY_UNITS 2
#define AWTO_DLOG_HINT_EVERY 64
#define AWTO_BOOT_COLD 1
struct { BYTE ucGen, ucBoot, ucPend, ucOld, ucLost; DWORD ulWr; } g_stAwtoSync;
static BYTE s_aucDl[16], mem[2][16];
static BYTE read_ok[2] = {1,1}, write_ok = 1;
static BYTE s_ucDlHdrDirty, s_ucDlInvalid, s_ucDlMigrate;
static DWORD s_ulDlPub, s_pulAtAbs[2], g_ulAwtoBootAbs, g_ulAwtoEpAbs;
static WORD g_usAwtoNoteN;
static BYTE cold;
static DWORD reads, writes, last_unit;
static DWORD AwtoMs(void) { return 101; }
static BYTE AwtoBootReason(void) { return cold; }
static BYTE AwtoDlBurstW(DWORD unit) {
    ++writes; last_unit = unit;
    if(!write_ok) return 0;
    memcpy(mem[unit == AWTO_DLOG_HDR_UNITS ? 0 : 1], s_aucDl, 16);
    return 1;
}
static BYTE scan_io = 1;
static DWORD scan_end = 0;
static BYTE AwtoDlBurstR(DWORD unit) {
    ++reads;
    if(unit >= AWTO_DLOG_UNITS0) {
        if(!scan_io) return 0;
        memset(s_aucDl, 0, 16);
        DWORD a = (unit - AWTO_DLOG_UNITS0) / AWTO_DLOG_ENTRY_UNITS;
        if(a < scan_end) {
            s_aucDl[10] = (BYTE)(a >> 16); s_aucDl[11] = (BYTE)(a >> 8); s_aucDl[12] = (BYTE)a;
            s_aucDl[13] = 3; s_aucDl[14] = 2;
            BYTE c = 0x5a;
            for(int j=0; j<15; ++j) c ^= s_aucDl[j];
            s_aucDl[15] = c;
        }
        return 1;
    }
    int i = unit == AWTO_DLOG_HDR_UNITS ? 0 : 1;
    if(!read_ok[i]) return 0;
    memcpy(s_aucDl, mem[i], 16); return 1;
}
'''
    cases = r'''
static void legacy(BYTE gen, BYTE boot, DWORD hint) {
    memset(mem, 0, sizeof(mem));
    memcpy(s_aucDl, "DL", 2);
    memset(s_aucDl+2, 0, 14);
    s_aucDl[2]=1; s_aucDl[3]=gen; s_aucDl[4]=boot;
    s_aucDl[5]=(BYTE)(hint>>24); s_aucDl[6]=(BYTE)(hint>>16); s_aucDl[7]=(BYTE)(hint>>8); s_aucDl[8]=(BYTE)hint;
    s_aucDl[15]=AwtoDlSum(); memcpy(mem[0], s_aucDl, 16);
}
int main(void) {
    g_stAwtoSync.ucGen=3; g_stAwtoSync.ucBoot=2;
    // Migration first writes primary, then alternating slots. A stalled write
    // must retain the previous publication and retry the same target.
    AwtoDlHdr(64);
    assert(last_unit==AWTO_DLOG_HDR_UNITS && s_ulDlPub==1 && !s_ucDlHdrDirty);
    assert(AwtoDlReadHdr()==2 && AwtoDlPublication()==1);
    write_ok=0; AwtoDlHdr(128);
    assert(s_ulDlPub==1 && s_ucDlHdrDirty && last_unit==AWTO_DLOG_HDR2_UNITS);
    write_ok=1; AwtoDlHdr(128);
    assert(s_ulDlPub==2 && !s_ucDlHdrDirty && last_unit==AWTO_DLOG_HDR2_UNITS);
    BYTE primary[16], shadow[16];
    memcpy(primary,mem[0],16); memcpy(shadow,mem[1],16);
    // Every byte boundary of a torn newer write preserves the untouched copy.
    AwtoDlHdr(192); BYTE newer[16]; memcpy(newer,mem[0],16);
    for(int cut=0; cut<=16; ++cut) {
        memcpy(mem[0],primary,16); memcpy(mem[0],newer,cut);
        assert(AwtoDlReadHdr()==2);
        assert(AwtoDlPublication()==2 || AwtoDlPublication()==3);
    }
    memcpy(mem[0],newer,16); read_ok[0]=0;
    assert(AwtoDlReadHdr()==2 && AwtoDlPublication()==2);
    read_ok[0]=1; read_ok[1]=0;
    assert(AwtoDlReadHdr()==2 && AwtoDlPublication()==3);
    read_ok[0]=0; assert(AwtoDlReadHdr()==0);
    read_ok[0]=read_ok[1]=1;
    // Publication wraps with 24-bit serial ordering.
    s_ulDlPub=0xfffffe; AwtoDlHdr(256); AwtoDlHdr(320);
    assert(AwtoDlReadHdr()==2 && AwtoDlPublication()==0);
    // Paired changes that cancel the legacy XOR are caught by the v2 CRC.
    memcpy(mem[0],mem[1],16); mem[0][5]^=1; mem[0][6]^=1;
    assert(AwtoDlReadHdr()==2 && AwtoDlPublication()==0);
    // v1 migration and downgrade select the primary.
    legacy(3,2,64); assert(AwtoDlReadHdr()==2 && s_ulDlPub==1);
    BYTE legacy_copy[16]; memcpy(legacy_copy,mem[0],16);
    AwtoDlHdr(100);
    assert(s_ulDlPub==2 && s_ucDlHdrDirty && !memcmp(legacy_copy,mem[0],16));
    AwtoDlHdr(100);
    assert(s_ulDlPub==3 && !s_ucDlHdrDirty && AwtoDlReadHdr()==2);
    legacy(3,2,64);
    // Interrupted init read must preserve valid historical state / offsets.
    g_stAwtoSync.ucGen=3; g_stAwtoSync.ulWr=100;
    g_ulAwtoBootAbs=90; g_ulAwtoEpAbs=95;
    read_ok[0]=0;
    assert(!AwtoDlInit() && g_stAwtoSync.ulWr==100 && g_ulAwtoBootAbs==90);
    read_ok[0]=1;
    // One answered-but-invalid header does not clear history; next drain heals.
    BYTE saved=mem[0][15]; mem[0][15]^=1;
    assert(!AwtoDlInit() && g_stAwtoSync.ulWr==100 && g_ulAwtoEpAbs==95);
    mem[0][15]=saved;
    assert(AwtoDlInit() && g_stAwtoSync.ulWr==100 && g_stAwtoSync.ucGen==3 && g_stAwtoSync.ucBoot==3);
    // New image (lost XDATA): scan failure must not truncate to the hint.
    legacy(3,2,64); memset(&g_stAwtoSync,0,sizeof(g_stAwtoSync));
    scan_end=100; scan_io=0; g_ulAwtoBootAbs=8;
    assert(!AwtoDlInit() && !g_stAwtoSync.ucGen && g_ulAwtoBootAbs==8);
    scan_io=1;
    assert(AwtoDlInit() && g_stAwtoSync.ulWr==100 && g_stAwtoSync.ucGen==3);
    // Genuine cold boot: a valid old gen 255 wraps to 1, never sentinel 0.
    legacy(255,8,64); cold=1;
    assert(AwtoDlInit() && g_stAwtoSync.ucGen==1 && g_stAwtoSync.ulWr==0 && g_stAwtoSync.ucBoot==1);
    // Two corrupt copies on a warm boot: bounded invalid observations before
    // declaring lost DDR; no individual I/O failure advances that decision.
    memset(mem,0,sizeof(mem)); cold=0; s_ucDlInvalid=0;
    assert(!AwtoDlInit()); assert(!AwtoDlInit()); assert(AwtoDlInit());
    printf("HEADER "); for(int j=0; j<16; ++j) printf("%02x", mem[0][j]); puts("");
    puts("PASS production publisher/selector/init: tears, stalls, wrap, warm/cold, scan failure");
    return 0;
}
'''
    code = tmp_path / "publication.c"
    code.write_text(prelude + definitions + "\n" + funcs + cases)
    exe = tmp_path / "publication"
    built = subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined", str(code), "-o", str(exe)], capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(exe)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS production" in result.stdout

    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import dram_log as D
    header = bytes.fromhex(next(x.removeprefix("HEADER ") for x in result.stdout.splitlines() if x.startswith("HEADER ")))
    assert D._header(header) is not None
