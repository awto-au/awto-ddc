"""#271: a `subprocess.run(..., check=False)` whose result is dropped or never has `.returncode` read must say why.
The call's lines carry `# rc ignored: <reason>`; otherwise handle the rc (or use check=True).
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK = "rc ignored:"


def _is_run(n):
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "run"
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess")


def _check_false(n):
    return any(k.arg == "check" and isinstance(k.value, ast.Constant) and k.value.value is False for k in n.keywords)


def unchecked(path: Path) -> list[int]:
    src = path.read_text()
    lines = src.splitlines()
    bad = []
    for fn in ast.walk(ast.parse(src)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            continue
        nodes = list(ast.walk(fn))
        for st in nodes:
            call = name = None
            if isinstance(st, ast.Expr) and _is_run(st.value):
                call = st.value
            elif isinstance(st, ast.Assign) and _is_run(st.value):
                call = st.value
                name = st.targets[0].id if isinstance(st.targets[0], ast.Name) else None
            if not call or not _check_false(call):
                continue
            if name and any(isinstance(n, ast.Attribute) and n.attr == "returncode" and isinstance(n.value, ast.Name)
                            and n.value.id == name for n in nodes):
                continue
            span = " ".join(lines[call.lineno - 1:call.end_lineno])
            if MARK not in span:
                bad.append(call.lineno)
    return sorted(set(bad))


def test_no_unmarked_ignored_return_codes():
    found = {str(p.relative_to(ROOT)): b for p in [ROOT / "dev.py", *sorted((ROOT / "scripts").glob("*.py"))] if (b := unchecked(p))}
    assert not found, f"subprocess.run(check=False) with the rc never read (add check=True, handle rc, or `# {MARK} why`): {found}"


def test_detector_flags_a_dropped_rc(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("import subprocess\ndef a():\n    subprocess.run(['x'], check=False)\n"
                 "def b():\n    r = subprocess.run(['x'], check=False)\n    return r.returncode\n"
                 "def c():\n    subprocess.run(['x'], check=False)  # rc ignored: best effort\n")
    assert unchecked(f) == [3]
