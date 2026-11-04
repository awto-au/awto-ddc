// arg0 = TSV (addr, name, type, comment, status). Labels only: no data creation, so adjacent registers stay intact.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.Files;
import java.nio.file.Paths;

public class ApplyRegLabels extends GhidraScript {
    @Override
    public void run() throws Exception {
        int n = 0, bad = 0;
        for (String line : Files.readAllLines(Paths.get(getScriptArgs()[0]))) {
            if (line.startsWith("#") || line.trim().isEmpty()) continue;
            String[] f = line.split("\t", -1);
            try {
                var a = toAddr(f[0].trim());
                createLabel(a, f[1].trim(), true, SourceType.USER_DEFINED);
                if (f.length > 3 && !f[3].isEmpty()) setPreComment(a, f[3] + " " + (f.length > 4 ? f[4] : ""));
                n++;
            } catch (Exception e) { bad++; }
        }
        println("ApplyRegLabels: " + n + " labelled, " + bad + " failed");
    }
}
