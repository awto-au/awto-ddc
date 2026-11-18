"""warn_policy_check.py (#173): a row whose line moved is stale; a -D row is not fatal in the default build."""
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
POLICY = ("# header\n"
          "^unreachable code$\tUser/x.c\t1361\tok\treason\n"
          "^unreachable code$\tUser/x.c\t50\tok\treason\t_AWTO_FRC=_OFF\n")


def run_check(tmp_path, warn_lines):
    (tmp_path / "fw").mkdir()
    (tmp_path / "fw" / "warn_policy.tsv").write_text(POLICY)
    w = tmp_path / "warnings.txt"
    w.write_text("".join(f"User/x.c:{n}: warning: unreachable code\n" for n in warn_lines))
    env = {k: v for k, v in os.environ.items() if k != "K2S_SDCC_EXTRA"}
    env["AWTO_DDC_REPO"] = str(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS / "warn_policy_check.py"), str(w),
                        "--policy", str(tmp_path / "fw" / "warn_policy.tsv")],
                       env=env, capture_output=True, text=True)
    return r.returncode, r.stdout


def test_matched_lines_pass(tmp_path):
    rc, out = run_check(tmp_path, [1361])
    assert rc == 0, out


def test_shifted_line_is_stale(tmp_path):
    # warnings from a build of a tree where the code moved 10 lines: row 1361 unused, site 1371 has no row
    rc, out = run_check(tmp_path, [1371])
    assert rc == 1, out
    assert "unused row 2: " in out and "User/x.c\t1361\t" in out and "no row: User/x.c:1371" in out, out


def test_d_option_row_not_fatal(tmp_path):
    rc, out = run_check(tmp_path, [1361])                    # row 50 (-D _AWTO_FRC=_OFF) has no site here
    assert rc == 0 and "belong to a -D build option" in out, out
