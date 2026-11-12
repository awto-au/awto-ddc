// args: <sdk_types.tsv> <typed-label TSV>...   (see scripts/ghidra_sdk_types.py, scripts/ghidra_globals_map.py)
// 1. creates every E/S/U type of sdk_types.tsv under /SDK (Keil C51 layout, offsets precomputed, big-endian)
// 2. each following TSV: rows `addr<TAB>name<TAB>type...`; type = prim | StructName | any of those with [n];
//    names-TSV rows use `var:<type>` in column 3 (plain `var` rows are left to ApplyNames).
//    Creates the data at addr (EXTMEM:xxxx / INTMEM:xx) and labels it.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

public class ApplySdkTypes extends GhidraScript {
    private final Map<String, String[]> head = new LinkedHashMap<>();            // name -> [kind, size, enumvals]
    private final Map<String, List<String[]>> fields = new HashMap<>();
    private final Map<String, DataType> built = new HashMap<>();
    private DataTypeManager dtm;
    private final CategoryPath cat = new CategoryPath("/SDK");

    private DataType prim(String r) {
        switch (r) {
            case "u8": return ByteDataType.dataType;
            case "s8": return SignedByteDataType.dataType;
            case "u16": return WordDataType.dataType;
            case "s16": return SignedWordDataType.dataType;
            case "u32": return DWordDataType.dataType;
            case "s32": return SignedDWordDataType.dataType;
            case "f32": return FloatDataType.dataType;
            case "ptr1": return new PointerDataType(DataType.DEFAULT, 1, dtm);
            case "ptr2": return new PointerDataType(DataType.DEFAULT, 2, dtm);
            case "ptr3": return new PointerDataType(DataType.DEFAULT, 3, dtm);
            default: return null;
        }
    }

    private DataType resolve(String ref) {
        DataType p = prim(ref);
        if (p != null) return p;
        return build(ref);
    }

    private DataType build(String name) {
        if (built.containsKey(name)) return built.get(name);
        String[] h = head.get(name);
        if (h == null) return null;
        DataType dt;
        int size = Integer.parseInt(h[1]);
        if (h[0].equals("E")) {
            EnumDataType e = new EnumDataType(cat, name, size);
            for (String kv : h[2].split(",")) {
                if (kv.isEmpty()) continue;
                int i = kv.lastIndexOf('=');
                try { e.add(kv.substring(0, i), Long.parseLong(kv.substring(i + 1))); } catch (Exception ex) { }
            }
            dt = e;
        } else {
            boolean uni = h[0].equals("U");
            Composite c = uni ? new UnionDataType(cat, name) : new StructureDataType(cat, name, 0);
            built.put(name, c);                                                  // guards recursion
            for (String[] f : fields.get(name)) {
                DataType ft = resolve(f[3]);
                if (ft == null) { println("ApplySdkTypes: " + name + "." + f[2] + ": unknown type " + f[3]); ft = ByteDataType.dataType; }
                int cnt = Integer.parseInt(f[4]);
                DataType use = cnt > 1 ? new ArrayDataType(ft, cnt, ft.getLength()) : ft;
                String cm = f.length > 5 ? f[5] : "";
                if (uni) c.add(use, f[2], cm); else ((Structure) c).add(use, f[2], cm);
            }
            dt = c;
        }
        dt = dtm.addDataType(dt, DataTypeConflictHandler.REPLACE_HANDLER);
        built.put(name, dt);
        return dt;
    }

    private DataType parseType(String t) {
        int n = 1;
        int br = t.indexOf('[');
        if (br > 0) { n = Integer.parseInt(t.substring(br + 1, t.indexOf(']'))); t = t.substring(0, br); }
        DataType d = resolve(t);
        if (d == null) return null;
        return n > 1 ? new ArrayDataType(d, n, d.getLength()) : d;
    }

    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        dtm = currentProgram.getDataTypeManager();
        int tx = dtm.startTransaction("ApplySdkTypes");
        List<String> lines = Files.readAllLines(Paths.get(a[0]));
        String cur = null;
        for (String ln : lines) {
            if (ln.startsWith("#") || ln.isEmpty()) { continue; }
            String[] f = ln.split("\t", -1);
            if (f[0].equals("E") || f[0].equals("S") || f[0].equals("U")) {
                cur = f[1];
                head.put(cur, new String[] { f[0], f[2], f.length > 3 ? f[3] : "" });
                fields.put(cur, new ArrayList<>());
            } else if (f[0].equals("F") && cur != null) {
                fields.get(cur).add(f);
            }
        }
        int nt = 0;
        for (String n : new ArrayList<>(head.keySet())) { if (build(n) != null) nt++; }
        dtm.endTransaction(tx, true);
        println("ApplySdkTypes: " + nt + " types under /SDK");
        // XDATA RAM window needs memory behind it for data units (0xD700-0xF6FF = SDK RAM, scaler registers are below)
        var mem = currentProgram.getMemory();
        Address ram = toAddr("EXTMEM:d700");
        if (mem.getBlock(ram) == null) {
            var blk = mem.createUninitializedBlock("XRAM_SDK", ram, 0x2000, false);
            blk.setRead(true); blk.setWrite(true); blk.setExecute(false);
            println("ApplySdkTypes: created XRAM_SDK block EXTMEM:d700-f6ff");
        }
        int nv = 0, bad = 0;
        for (int i = 1; i < a.length; i++) {
            for (String ln : Files.readAllLines(Paths.get(a[i]))) {
                if (ln.startsWith("#") || ln.trim().isEmpty()) continue;
                String[] f = ln.split("\t", -1);
                if (f.length < 3) continue;
                String ty = f[2].trim();
                if (ty.startsWith("var:")) ty = ty.substring(4);
                else if (!a[i].endsWith("ghidra_globals.tsv") && !a[i].endsWith("ghidra_globals_hand.tsv")) continue;
                if (ty.equals("var") || ty.equals("func") || ty.equals("label") || ty.equals("data")) continue;
                try {
                    DataType dt = parseType(ty);
                    Address ad = toAddr(f[0].trim());
                    if (dt == null || ad == null) { bad++; println("ApplySdkTypes: bad row " + ln); continue; }
                    clearListing(ad, ad.add(dt.getLength() - 1));
                    createData(ad, dt);
                    createLabel(ad, f[1].trim(), true, SourceType.USER_DEFINED);
                    nv++;
                } catch (Exception e) { bad++; println("ApplySdkTypes: failed " + ln + ": " + e); }
            }
        }
        println("ApplySdkTypes: " + nv + " typed labels applied, " + bad + " failed");
    }
}
