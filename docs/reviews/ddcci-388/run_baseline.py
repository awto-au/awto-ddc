#!/usr/bin/env python3
"""Run the host VCP mapping check against an awto-ddc checkout, without hardware.
Usage: python3 run_baseline.py /path/to/awto-ddc
The check intentionally asserts the reviewed baseline, not the proposed API.
"""
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path(sys.argv[1]).resolve()
fw = root / 'fw/rtdfw/awto'
with tempfile.TemporaryDirectory(prefix='vcp-review-') as out:
    binary = pathlib.Path(out) / 'baseline'
    subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-ffunction-sections',
                    '-fdata-sections', '-I' + str(fw / 'include'),
                    '-I' + str(fw / 'settings'),
                    str(pathlib.Path(__file__).with_name('vcp_baseline.c')),
                    str(fw / 'settings/vcp.c'), str(fw / 'settings/set_table.c'),
                    '-Wl,--gc-sections', '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
