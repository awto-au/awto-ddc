"""gpio_diag default inputs table resolves inside this repo (#274)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gpio_diag


def test_default_inputs_tsv_exists_and_loads():
    assert gpio_diag.INPUTS_TSV.is_file()
    assert "awto-ddc-ui" not in str(gpio_diag.INPUTS_TSV)
    assert gpio_diag.load_inputs()
