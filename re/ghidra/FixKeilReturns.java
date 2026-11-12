// Clear the non-returning flag on Keil C51 runtime helpers (and their thunks) that do return, so flow continues after LCALL.
// Keeps flagged only the real non-returners listed in KEEP (args: optional extra keep addresses, hex).
// Then disassembles the fall-through of every call to a cleared function, rebuilds function bodies, disables the
// non-returning-discovery analyzer (it re-flags them) and re-runs auto-analysis.
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.util.*;

public class FixKeilReturns extends GhidraScript {
    // 0x1617 / 0x163d (CCASE/ICASE inline tables) pop the return address: flow after the call is data.
    static final long[] KEEP = {0x1617, 0x163d};

    @Override
    public void run() throws Exception {
        Set<Long> keep = new HashSet<>();
        for (long k : KEEP) keep.add(k);
        for (String a : getScriptArgs()) keep.add(Long.decode("0x" + a));
        FunctionManager fm = currentProgram.getFunctionManager();
        List<Function> cleared = new ArrayList<>();
        for (Function f : fm.getFunctions(true)) {
            if (f.hasNoReturn() && !keep.contains(f.getEntryPoint().getOffset())) { f.setNoReturn(false); cleared.add(f); }
        }
        int dis = 0, ovr = 0;
        Map<Long, Integer> tgtHist = new TreeMap<Long, Integer>();
        // noreturn analysis turns the calls into call-terminators via a CALL_RETURN flow override: drop it (except KEEP targets)
        for (Instruction i : currentProgram.getListing().getInstructions(true)) {
            if (i.getFlowOverride() != FlowOverride.CALL_RETURN || !i.getMnemonicString().endsWith("CALL")) continue; // JMPs carry it from Shared Return Calls
            boolean kept = false;
            for (Address t : i.getFlows()) if (keep.contains(t.getOffset())) kept = true;
            if (kept) continue;
            for (Address t : i.getFlows()) tgtHist.merge(t.getOffset(), 1, Integer::sum);
            i.setFlowOverride(FlowOverride.NONE); ovr++;
            Address ft = i.getFallThrough();
            if (ft != null && getInstructionAt(ft) == null && disassemble(ft)) dis++;
        }
        setAnalysisOption(currentProgram, "Non-Returning Functions - Discovered", "false");
        analyzeAll(currentProgram);
        int rebuilt = 0;
        List<Function> all = new ArrayList<Function>();
        for (Function g : fm.getFunctions(true)) all.add(g);
        for (Function f : all) {
            try {
                AddressSetView body = CreateFunctionCmd.getFunctionBody(currentProgram, f.getEntryPoint(), monitor);
                if (body != null && !body.equals(f.getBody())) { f.setBody(body); rebuilt++; }
            } catch (Exception e) { /* overlap with another function: keep old body */ }
        }
        println("FixKeilReturns override targets " + tgtHist);
        println("FixKeilReturns: cleared " + cleared.size() + " noreturn flags, " + ovr + " call-return overrides, " + dis + " fall-throughs disassembled, " + rebuilt + " bodies rebuilt");
    }
}
