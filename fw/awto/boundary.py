"""SDK <-> clean-room boundary (fw_compile.py): SDK names that are macros to the clean function (no wrapper hop), and the
SDK functions pinned to common memory so their callers reach them without a bank trampoline (#65 #68)."""
# (sdk name, clean name, module): applied only when the clean tree has that module
ALIASES = [("ScalerSetDataPortByte", "dp_wr", "dataport"), ("ScalerSetDataPortBit", "dp_rmw", "dataport"),
           ("ScalerGetDataPortBit", "dp_test", "dataport"), ("ScalerSetDataPortWord", "dp_wr16", "dataport")]
PIN_COMMON = ["ScalerGetDataPortByte", "ScalerGetDataPortWord",       # dataport wrappers kept in the shim
              "ScalerRead", "ScalerWrite", "ScalerBurstWrite"]        # reg: multi-byte access / burst, argument order differs
