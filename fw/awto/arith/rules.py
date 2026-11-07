# arith (step 2, #65): the SDK's two FunctionLib helpers are replaced via the boundary shim (sdk_boundary.c).
# No WRAPS: select_lib drops the Lib module once the shim defines both symbols.
WRAPS = []
INSERTS = []
SUBS = []
