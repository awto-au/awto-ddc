// List functions flagged non-returning (diagnostic). args: none
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;

public class ListNoReturn extends GhidraScript {
    @Override
    public void run() throws Exception {
        int n = 0;
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            if (f.hasNoReturn()) { println("NORET " + f.getEntryPoint() + " " + f.getName()); n++; }
        }
        println("NORET total " + n);
    }
}
