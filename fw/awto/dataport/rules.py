# dataport (step 2, #65): SDK names that match a clean signature are macros to the clean function (no wrapper hop);
# the others keep a wrapper in the shim, pinned to common so the caller reaches it without a bank trampoline.
ALIASES = [("ScalerSetDataPortByte", "dp_wr", "dataport"), ("ScalerSetDataPortBit", "dp_rmw", "dataport"),
           ("ScalerGetDataPortBit", "dp_test", "dataport"), ("ScalerSetDataPortWord", "dp_wr16", "dataport")]
PIN_COMMON = ["ScalerGetDataPortByte", "ScalerGetDataPortWord"]
