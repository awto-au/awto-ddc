# gamma (step 8 data, #65): the RTD OSD gamma adjust calls the clean loader; ScalerColorOutputGammaEnable comes from the shim.
import os
from pathlib import Path

_CLEAN = Path(os.environ.get("AWTO_RTDFW_REPO", "/mnt/2tb/git/awto-rtdfw"))
WRAPS = []
INSERTS = []
SUBS = []
if (_CLEAN / "awto" / "gamma").is_dir():
    SUBS = [("User/RTD Series/RTD2014Function/Code/RTD2014UserAdjustOutputGamma.c",
             r"UserCommonAdjustGamma\(tGAMMA_TABLE\[ucGamma - 1\], GET_CURRENT_BANK_NUMBER\(\)\);",
             lambda m: "{ extern void AwtoGammaLoad(BYTE); AwtoGammaLoad(ucGamma - 1); }  // [keil2sdcc] sub", 1)]
