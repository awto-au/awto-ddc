// Export every scaler-register WRITE and READ site of one bank program (8051 CODE image, regs are XDATA at (page<<8)|reg).
// args: <outDir> <ports.tsv> <labels.tsv>   (ports/labels from scripts/regdb_ghidra_labels.py)
// outputs: <outDir>/regwrites.tsv, <outDir>/regreads.tsv
// Method: own 8051 decoder + path-sensitive (<=6 states/insn) constant propagation over A, R0-R7, DPH/DPL from every
//   Ghidra function entry. Needed because Keil inline data (call 0x15DA = 4-byte store) defeats Ghidra's disassembly.
// Write kinds: set | or | and | rmw | xor | copy | unk  (MOVX @DPTR,A; value/masks resolved when constant)
//   dword (inline-data store via 0x15DA), fill (memset 0x181A), burst (memcpy 0x11B3),
//   dp-call (call with R6:R7 = an address-port register: ScalerSet/GetDataPort*, R5=index, R3=value),
//   callarg (call with R6:R7 = another regdb register: ScalerSetBit-style helpers; low confidence).
// Entries Ghidra lacks (bank-switch stub targets, call targets) are analysed too and created as functions, so ExportAll decompiles them.
// Bank-switch stubs (MOV DPTR,#T; LJMP 04xx) are resolved: callee column = bank<N>:<T>.
// Data-port accesses: MOVX to data_addr after a constant write of idx to port_addr gets name of (port, idx).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

public class ExportRegAccess extends GhidraScript {
    // ---- abstract values ----
    static final class V {
        final int k; final int c, reg, and, or, xor; // k: 0 unknown, 1 const(c), 2 sym ((x(reg)&and|or)^xor)
        V(int k, int c, int reg, int and, int or, int xor) { this.k = k; this.c = c; this.reg = reg; this.and = and; this.or = or; this.xor = xor; }
        boolean eq(V o) { return k == o.k && c == o.c && reg == o.reg && and == o.and && or == o.or && xor == o.xor; }
    }
    static final V UNK = new V(0, 0, 0, 0, 0, 0);
    static V K(int c) { return new V(1, c & 0xFF, 0, 0, 0, 0); }
    static V SYM(int reg) { return new V(2, 0, reg, 0xFF, 0, 0); }

    static final class S {
        V a = UNK, dph = UNK, dpl = UNK; V[] r = new V[8];
        int pport = -1; V pidx = UNK; // last constant index written to an address-port register
        S() { Arrays.fill(r, UNK); }
        S copy() { S s = new S(); s.a = a; s.dph = dph; s.dpl = dpl; s.r = r.clone(); s.pport = pport; s.pidx = pidx; return s; }
        boolean same(S o) {
            if (!a.eq(o.a) || !dph.eq(o.dph) || !dpl.eq(o.dpl) || pport != o.pport || !pidx.eq(o.pidx)) return false;
            for (int i = 0; i < 8; i++) if (!r[i].eq(o.r[i])) return false;
            return true;
        }
        // t covers s: every field of t is unknown or equal
        boolean covers(S s) {
            if (!(a.k == 0 || a.eq(s.a)) || !(dph.k == 0 || dph.eq(s.dph)) || !(dpl.k == 0 || dpl.eq(s.dpl))) return false;
            if (pport != -1 && (pport != s.pport || !pidx.eq(s.pidx))) return false;
            for (int i = 0; i < 8; i++) if (!(r[i].k == 0 || r[i].eq(s.r[i]))) return false;
            return true;
        }
        static V m(V x, V y) { return x.eq(y) ? x : UNK; }
        S meet(S o) {
            S s = new S(); s.a = m(a, o.a); s.dph = m(dph, o.dph); s.dpl = m(dpl, o.dpl);
            for (int i = 0; i < 8; i++) s.r[i] = m(r[i], o.r[i]);
            if (pport == o.pport && pidx.eq(o.pidx)) { s.pport = pport; s.pidx = pidx; }
            return s;
        }
        int dptr() { return (dph.k == 1 && dpl.k == 1) ? (dph.c << 8 | dpl.c) : -1; }
        int r67() { return (r[6].k == 1 && r[7].k == 1) ? (r[6].c << 8 | r[7].c) : -1; }
    }

    // ---- 8051 length table ----
    static final int[] LEN = new int[256];
    static {
        int[][] r = {
            {1,2,3,1,1,2,1,1, 1,1,1,1,1,1,1,1}, {3,2,3,1,1,2,1,1, 1,1,1,1,1,1,1,1},
            {3,2,1,1,2,2,1,1, 1,1,1,1,1,1,1,1}, {3,2,1,1,2,2,1,1, 1,1,1,1,1,1,1,1},
            {2,2,2,3,2,2,1,1, 1,1,1,1,1,1,1,1}, {2,2,2,3,2,2,1,1, 1,1,1,1,1,1,1,1},
            {2,2,2,3,2,2,1,1, 1,1,1,1,1,1,1,1}, {2,2,2,1,2,3,2,2, 2,2,2,2,2,2,2,2},
            {2,2,2,1,1,3,2,2, 2,2,2,2,2,2,2,2}, {3,2,2,1,2,2,1,1, 1,1,1,1,1,1,1,1},
            {2,2,2,1,1,1,2,2, 2,2,2,2,2,2,2,2}, {2,2,2,1,3,3,3,3, 3,3,3,3,3,3,3,3},
            {2,2,2,1,1,2,1,1, 1,1,1,1,1,1,1,1}, {2,2,2,1,1,3,1,1, 2,2,2,2,2,2,2,2},
            {1,2,1,1,1,2,1,1, 1,1,1,1,1,1,1,1}, {1,2,1,1,1,2,1,1, 1,1,1,1,1,1,1,1}};
        for (int i = 0; i < 16; i++) for (int j = 0; j < 16; j++) LEN[i * 16 + j] = r[i][j];
    }
    static final int[] BANK_STUB = {0x429, 0x43B, 0x44D, 0x45F, 0x471, 0x483, 0x495}; // LJMP target -> bank index

    // ---- per-run data ----
    byte[] code = new byte[65536];
    int bank;
    Map<Integer, List<S>> states = new HashMap<>();
    Map<Integer, Map<Integer, String[]>> portNames = new HashMap<>(); // port_addr -> idx -> {data_addr, name}
    Set<Integer> portAddrs = new HashSet<>(), dataAddrs = new HashSet<>(), labelAddrs = new HashSet<>();
    Map<Integer, String> nameCache = new HashMap<>();
    TreeSet<Integer> funcEntries = new TreeSet<>();
    Map<Integer, String> funcNames = new HashMap<>();
    Map<Integer, Boolean> inlineHelper = new HashMap<>();
    Set<String> rowsW = new TreeSet<>(), rowsR = new TreeSet<>();
    Set<Integer> inlineHelpersSeen = new TreeSet<>();
    int ub(int pc) { return code[pc & 0xFFFF] & 0xFF; }
    static final int RAM_LO = 0xD700, RAM_HI = 0xF6FF;
    static boolean ram(int a) { return a >= RAM_LO && a <= RAM_HI; }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String out = args[0];
        String pn = currentProgram.getName();
        bank = Integer.parseInt(pn.replaceAll("[^0-9]", ""));
        AddressSpace cs = currentProgram.getAddressFactory().getAddressSpace("CODE");
        for (int i = 0; i < 65536; i += 4096) {
            byte[] b = new byte[4096];
            try { currentProgram.getMemory().getBytes(cs.getAddress(i), b); System.arraycopy(b, 0, code, i, 4096); } catch (Exception e) { /* uninitialised */ }
        }
        loadPorts(args[1]); loadLabels(args[2]);
        FunctionManager fm = currentProgram.getFunctionManager();
        for (Function f : fm.getFunctions(true)) {
            int a = (int) f.getEntryPoint().getOffset();
            funcEntries.add(a); funcNames.put(a, f.getName());
        }
        for (int e : new ArrayList<>(funcEntries)) push(e, new S());
        // bank-switch stubs (MOV DPTR,#T; LJMP 04xx) in the common area: T is an entry of that bank (called from other banks)
        int nstub = 0;
        for (int p = 0; p < 0x3000; p++) {
            String st = stub(p);
            if (st != null && st.startsWith("bank" + bank + ":")) { seedEntry(Integer.parseInt(st.substring(6), 16)); nstub++; }
        }
        solve();
        emitAll();
        write(out + "/regwrites.tsv", rowsW, "bank\tinsn\tfunc_addr\tfunc\treg_addr\treg_name\tkind\tvalue\tand_mask\tor_mask\tcallee\tnote");
        write(out + "/regreads.tsv", rowsR, "bank\tinsn\tfunc_addr\tfunc\treg_addr\treg_name\tmask\tcontext\tnote");
        // make the entries Ghidra did not know real functions, so the decompile export covers them (idempotent)
        int made = 0;
        for (int a : synth) {
            try {
                Address ad = cs.getAddress(a);
                if (currentProgram.getFunctionManager().getFunctionAt(ad) != null) continue;
                disassemble(ad);
                if (createFunction(ad, null) != null) made++;
            } catch (Exception e) { /* data / overlap: leave */ }
        }
        println("ExportRegAccess bank" + bank + ": " + rowsW.size() + " write rows, " + rowsR.size() + " read rows, "
                + states.size() + " insns reached, " + synth.size() + " extra entries (" + made + " created), inline-data helpers: " + hexList(inlineHelpersSeen));
    }

    String hexList(Set<Integer> s) { StringBuilder b = new StringBuilder(); for (int x : s) b.append(String.format("%04x ", x)); return b.toString().trim(); }

    void write(String path, Set<String> rows, String hdr) throws Exception {
        List<String> sorted = new ArrayList<>(rows);
        sorted.sort(Comparator.comparingInt((String x) -> Integer.parseInt(x.split("\t")[1], 16)).thenComparing(x -> x));
        try (PrintWriter w = new PrintWriter(new FileWriter(path))) {
            w.println("# generated by re/ghidra/ExportRegAccess.java; do not edit");
            w.println(hdr);
            for (String r : sorted) w.println(r);
        }
    }

    void loadPorts(String p) throws Exception {
        for (String ln : Files.readAllLines(Paths.get(p))) {
            if (ln.startsWith("#") || ln.isEmpty()) continue;
            String[] f = ln.split("\t");
            int pa = Integer.parseInt(f[0], 16), da = Integer.parseInt(f[1], 16), ix = Integer.parseInt(f[2], 16);
            portAddrs.add(pa); dataAddrs.add(da);
            portNames.computeIfAbsent(pa, k -> new HashMap<>()).put(ix, new String[]{f[1], f[3]});
        }
    }

    void loadLabels(String p) throws Exception {
        for (String ln : Files.readAllLines(Paths.get(p))) {
            if (!ln.startsWith("EXTMEM:")) continue;
            String[] f = ln.split("\t");
            int a = Integer.parseInt(f[0].substring(7), 16);
            labelAddrs.add(a);
        }
    }

    String regName(int a) {
        return nameCache.computeIfAbsent(a, k -> {
            try {
                Address ad = currentProgram.getAddressFactory().getAddressSpace("EXTMEM").getAddress(k);
                Symbol s = currentProgram.getSymbolTable().getPrimarySymbol(ad);
                return s == null ? "" : s.getName();
            } catch (Exception e) { return ""; }
        });
    }

    // ---- dataflow ----
    void push(int pc, S s) {
        if (pc < 0 || pc > 0xFFFF) return;
        List<S> l = states.computeIfAbsent(pc, k -> new ArrayList<>());
        for (S t : l) if (t.covers(s)) return;
        { final S ns = s; l.removeIf(t -> ns.covers(t)); }
        l.add(s);
        if (l.size() > 6) { S m = l.get(0); for (int i = 1; i < l.size(); i++) m = m.meet(l.get(i)); l.clear(); l.add(m); s = m; }
        queue.add(new Object[]{pc, s});
    }
    ArrayDeque<Object[]> queue = new ArrayDeque<>();

    // add a synthetic function entry (code Ghidra has not made a function) and analyse from it with unknown state
    void seedEntry(int a) {
        if (a < 0 || a > 0xFFFF) return;
        if (funcEntries.add(a)) { funcNames.put(a, String.format("FUN_CODE_%04x", a)); synth.add(a); }
        push(a, new S());
    }
    Set<Integer> synth = new TreeSet<>();

    void solve() {
        int guard = 0;
        while (!queue.isEmpty()) {
            Object[] it = queue.poll();
            int pc = (Integer) it[0]; S s = (S) it[1];
            List<S> cur = states.get(pc);
            if (cur == null || !cur.contains(s)) continue; // replaced by a covering state
            if (++guard > 3_000_000) { println("solve guard hit"); break; }
            step(pc, s, false);
        }
    }

    void emitAll() {
        for (Map.Entry<Integer, List<S>> e : new ArrayList<>(states.entrySet())) {
            for (S s : e.getValue()) step(e.getKey(), s, true);
        }
    }

    static int rel(int pc, int len, int off) { return (pc + len + (byte) off) & 0xFFFF; }

    V get(S s, int d) {
        if (d < 8) return s.r[d];
        if (d == 0xE0) return s.a;
        if (d == 0x82) return s.dpl;
        if (d == 0x83) return s.dph;
        return UNK;
    }
    void put(S s, int d, V v) {
        if (d < 8) s.r[d] = v; else if (d == 0xE0) s.a = v; else if (d == 0x82) s.dpl = v; else if (d == 0x83) s.dph = v;
    }

    // alu op on values: 0 add 1 or 2 and 3 xor
    V alu(int op, V x, V y) {
        if (x.k == 1 && y.k == 1) {
            int a = x.c, b = y.c;
            return K(op == 0 ? a + b : op == 1 ? a | b : op == 2 ? a & b : a ^ b);
        }
        if (op == 0) return UNK;
        if (x.k != 2 && y.k == 2) { V t = x; x = y; y = t; }
        if (x.k == 2 && y.k == 1) {
            int m = y.c;
            if (op == 2) return new V(2, 0, x.reg, x.and & m, x.or & m, x.xor & m);
            if (op == 1) return x.xor == 0 ? new V(2, 0, x.reg, x.and, x.or | m, 0) : UNK;
            return new V(2, 0, x.reg, x.and, x.or, x.xor ^ m);
        }
        return UNK;
    }

    int[] succ = new int[4]; // scratch
    void next(int pc, S s, boolean emit) { if (!emit) push(pc, s); }

    // execute one instruction; during solve push successors, during emit produce rows
    void step(int pc, S in, boolean emit) {
        int op = ub(pc), len = LEN[op];
        int b1 = ub(pc + 1), b2 = ub(pc + 2);
        int npc = (pc + len) & 0xFFFF;
        S s = in.copy();
        int hi = op & 0xF0, lo = op & 0x0F;
        switch (op) {
            case 0x74: s.a = K(b1); break;
            case 0xE4: s.a = K(0); break;
            case 0xF4: s.a = s.a.k == 1 ? K(~s.a.c) : s.a.k == 2 ? new V(2, 0, s.a.reg, s.a.and, s.a.or, s.a.xor ^ 0xFF) : UNK; break;
            case 0x90: s.dph = K(b1); s.dpl = K(b2); break;
            case 0xA3: {
                if (s.dpl.k == 1 && s.dpl.c != 0xFF) s.dpl = K(s.dpl.c + 1);
                else if (s.dpl.k == 1 && s.dph.k == 1) { s.dpl = K(0); s.dph = K(s.dph.c + 1); }
                else { s.dpl = UNK; s.dph = UNK; }
                break;
            }
            case 0x75: put(s, b1, K(b2)); break;
            case 0xE5: s.a = get(s, b1); break;
            case 0xF5: put(s, b1, s.a); break;
            case 0x85: put(s, b2, get(s, b1)); break;
            case 0x04: s.a = s.a.k == 1 ? K(s.a.c + 1) : UNK; break;
            case 0x14: s.a = s.a.k == 1 ? K(s.a.c - 1) : UNK; break;
            case 0x05: put(s, b1, get(s, b1).k == 1 ? K(get(s, b1).c + 1) : UNK); break;
            case 0x15: put(s, b1, get(s, b1).k == 1 ? K(get(s, b1).c - 1) : UNK); break;
            case 0x24: s.a = alu(0, s.a, K(b1)); break;
            case 0x25: s.a = alu(0, s.a, get(s, b1)); break;
            case 0x44: s.a = alu(1, s.a, K(b1)); break;
            case 0x45: s.a = alu(1, s.a, get(s, b1)); break;
            case 0x54: s.a = alu(2, s.a, K(b1)); break;
            case 0x55: s.a = alu(2, s.a, get(s, b1)); break;
            case 0x64: s.a = alu(3, s.a, K(b1)); break;
            case 0x65: s.a = alu(3, s.a, get(s, b1)); break;
            case 0x42: put(s, b1, alu(1, get(s, b1), s.a)); break;
            case 0x43: put(s, b1, alu(1, get(s, b1), K(b2))); break;
            case 0x52: put(s, b1, alu(2, get(s, b1), s.a)); break;
            case 0x53: put(s, b1, alu(2, get(s, b1), K(b2))); break;
            case 0x62: put(s, b1, alu(3, get(s, b1), s.a)); break;
            case 0x63: put(s, b1, alu(3, get(s, b1), K(b2))); break;
            case 0xC5: { V t = get(s, b1); put(s, b1, s.a); s.a = t; break; }
            case 0xD0: put(s, b1, UNK); break;
            case 0xC2: case 0xD2: case 0xB2: case 0x92: case 0x10:
                if ((b1 & 0xF8) == 0xE0) s.a = UNK; break;
            case 0xC4: s.a = s.a.k == 1 ? K((s.a.c << 4) | (s.a.c >> 4)) : UNK; break;
            case 0x03: case 0x13: case 0x23: case 0x33: case 0x83: case 0x93: case 0xA4: case 0x84: case 0xD4:
            case 0x34: case 0x35: case 0x94: case 0x95: case 0x26: case 0x27: case 0x36: case 0x37: case 0x46: case 0x47:
            case 0x56: case 0x57: case 0x66: case 0x67: case 0x96: case 0x97: case 0xE6: case 0xE7: case 0xE2: case 0xE3:
            case 0xC6: case 0xC7: case 0xD6: case 0xD7:
                s.a = UNK; break;
            case 0xE0: { // MOVX A,@DPTR
                int d = s.dptr();
                if (emit) readRow(pc, s, d);
                if (d >= 0) {
                    if (!ram(d)) s.a = SYM(d); else s.a = UNK;
                } else s.a = UNK;
                break;
            }
            case 0xF0: { // MOVX @DPTR,A
                int d = s.dptr();
                if (emit) writeRow(pc, s, d);
                if (d >= 0 && portAddrs.contains(d)) { s.pport = d; s.pidx = s.a.k == 1 ? s.a : UNK; }
                break;
            }
            default:
                if (hi == 0x20 && lo >= 8) { s.a = alu(0, s.a, s.r[lo - 8]); }
                else if (hi == 0x40 && lo >= 8) { s.a = alu(1, s.a, s.r[lo - 8]); }
                else if (hi == 0x50 && lo >= 8) { s.a = alu(2, s.a, s.r[lo - 8]); }
                else if (hi == 0x60 && lo >= 8) { s.a = alu(3, s.a, s.r[lo - 8]); }
                else if (hi == 0x30 && lo >= 8) { s.a = UNK; }
                else if (hi == 0x90 && lo >= 8) { s.a = UNK; }
                else if (hi == 0x70 && lo >= 8) { s.r[lo - 8] = K(b1); }
                else if (hi == 0xE0 && lo >= 8) { s.a = s.r[lo - 8]; }
                else if (hi == 0xF0 && lo >= 8) { s.r[lo - 8] = s.a; }
                else if (hi == 0x00 && lo >= 8) { s.r[lo - 8] = s.r[lo - 8].k == 1 ? K(s.r[lo - 8].c + 1) : UNK; }
                else if (hi == 0x10 && lo >= 8) { s.r[lo - 8] = s.r[lo - 8].k == 1 ? K(s.r[lo - 8].c - 1) : UNK; }
                else if (hi == 0xA0 && lo >= 8) { s.r[lo - 8] = get(s, b1); }
                else if (hi == 0x80 && lo >= 8) { put(s, b1, s.r[lo - 8]); }
                else if (hi == 0xC0 && lo >= 8) { V t = s.r[lo - 8]; s.r[lo - 8] = s.a; s.a = t; }
                break;
        }
        // ---- control flow ----
        if (op == 0x73) { // JMP @A+DPTR: follow a table of LJMPs at a constant DPTR
            int d = in.dptr();
            if (d >= 0) for (int i = 0, p = d; i < 128 && ub(p) == 0x02; i++, p += 3) next(ub(p + 1) << 8 | ub(p + 2), new S(), emit);
            return;
        }
        if (op == 0x22 || op == 0x32) return;
        if (op == 0x02) { next(b1 << 8 | b2, s, emit); return; }
        if ((op & 0x1F) == 0x01) { // AJMP
            next(((pc + 2) & 0xF800) | ((op & 0xE0) << 3) | b1, s, emit); return;
        }
        if ((op & 0x1F) == 0x11 || op == 0x12) { // ACALL / LCALL
            int tgt = op == 0x12 ? (b1 << 8 | b2) : (((pc + 2) & 0xF800) | ((op & 0xE0) << 3) | b1);
            callInsn(pc, op == 0x12 ? 3 : 2, tgt, s, emit);
            return;
        }
        S ft = s;
        switch (op) {
            case 0x80: next(rel(pc, 2, b1), s, emit); return;
            case 0x40: case 0x50: next(rel(pc, 2, b1), s, emit); next(npc, ft, emit); return;
            case 0x60: case 0x70: {
                S br = s.copy(), fl = s.copy();
                boolean z = op == 0x60;
                if (s.a.k == 1) { boolean isz = s.a.c == 0; if (isz == z) next(rel(pc, 2, b1), br, emit); else next(npc, fl, emit); return; }
                (z ? br : fl).a = K(0);
                next(rel(pc, 2, b1), br, emit); next(npc, fl, emit); return;
            }
            case 0x10: case 0x20: case 0x30:
                next(rel(pc, 3, b2), s, emit); next(npc, ft, emit); return;
            case 0xB4: {
                S eq = s.copy(), ne = s.copy();
                if (s.a.k == 1) { if (s.a.c == b1) next(npc, eq, emit); else next(rel(pc, 3, b2), ne, emit); return; }
                eq.a = K(b1);
                next(rel(pc, 3, b2), ne, emit); next(npc, eq, emit); return;
            }
            case 0xB5: case 0xB6: case 0xB7:
                next(rel(pc, 3, b2), s, emit); next(npc, ft, emit); return;
            case 0xD5: {
                S t = s.copy(); put(t, b1, UNK); S f2 = t.copy();
                next(rel(pc, 3, b2), t, emit); next(npc, f2, emit); return;
            }
            default: break;
        }
        if ((op & 0xF8) == 0xB8) { // CJNE Rn,#i,rel
            int n = op & 7; S eq = s.copy(), ne = s.copy();
            if (s.r[n].k == 1) { if (s.r[n].c == b1) next(npc, eq, emit); else next(rel(pc, 3, b2), ne, emit); return; }
            eq.r[n] = K(b1);
            next(rel(pc, 3, b2), ne, emit); next(npc, eq, emit); return;
        }
        if ((op & 0xF8) == 0xD8) { // DJNZ Rn
            S t = s.copy(); t.r[op & 7] = UNK; S f2 = t.copy();
            next(rel(pc, 2, b1), t, emit); next(npc, f2, emit); return;
        }
        next(npc, s, emit);
    }

    // ---- calls ----
    // resolve bank stub: MOV DPTR,#T ; LJMP 04xx  ->  "bank<k>:<T>", else null
    String stub(int tgt) {
        if (ub(tgt) == 0x90 && ub(tgt + 3) == 0x02) {
            int j = ub(tgt + 4) << 8 | ub(tgt + 5);
            for (int k = 0; k < BANK_STUB.length; k++)
                if (BANK_STUB[k] == j) return String.format("bank%d:%04x", k, ub(tgt + 1) << 8 | ub(tgt + 2));
        }
        return null;
    }

    boolean isInlineHelper(int tgt) {
        return inlineHelper.computeIfAbsent(tgt, t -> {
            int p = t;
            for (int i = 0; i < 8; i++) {
                if (ub(p) == 0xD0 && ub(p + 1) == 0x83 && ub(p + 2) == 0xD0 && ub(p + 3) == 0x82) return true;
                int l = LEN[ub(p)]; int o = ub(p);
                if (o == 0x22 || o == 0x02 || o == 0x80) return false;
                p += l;
            }
            return false;
        });
    }

    void callInsn(int pc, int len, int tgt, S s, boolean emit) {
        int npc = (pc + len) & 0xFFFF;
        String callee = stub(tgt);
        if (callee == null) callee = String.format("bank%d:%04x", bank, tgt);
        S after = s.copy();
        if (callee.startsWith("bank" + bank + ":")) seedEntry(Integer.parseInt(callee.substring(6), 16));
        boolean inline = (tgt == 0x15DA) || isInlineHelper(tgt);
        if (tgt != 0x15DA && tgt != 0x1617 && tgt != 0x163D && inline) inlineHelpersSeen.add(tgt);
        if (emit) callRows(pc, tgt, callee, s);
        after.a = UNK; after.dph = UNK; after.dpl = UNK; Arrays.fill(after.r, UNK);
        after.pport = -1; after.pidx = UNK;
        if (tgt == 0x15DA) { next((npc + 4) & 0xFFFF, after, emit); return; }
        if (tgt == 0x1617 || tgt == 0x163D) { // inline switch tables (entry = target hi,lo + key; end marker, then default hi,lo)
            int w = tgt == 0x1617 ? 3 : 4, p = npc;
            S sw = s.copy(); sw.a = UNK; sw.r[0] = UNK;
            for (int i = 0; i < 256 && (ub(p) != 0 || (w == 4 && ub(p + 1) != 0)); i++, p += w) next(ub(p) << 8 | ub(p + 1), sw.copy(), emit);
            next(ub(p + 2) << 8 | ub(p + 3), sw.copy(), emit);
            return;
        }
        if (inline) return; // inline-data consumer other than 0x15DA: flow after the call is data
        next(npc, after, emit);
    }

    void callRows(int pc, int tgt, String callee, S s) {
        if (tgt == 0x15DA) {
            int d = s.dptr();
            if (d < 0) { addW(pc, -1, "dword", "?", "", "", callee, "dest unknown; inline bytes " + String.format("%02x%02x%02x%02x", ub(pc + 3), ub(pc + 4), ub(pc + 5), ub(pc + 6))); return; }
            for (int i = 0; i < 4; i++)
                addW(pc, d + i, "dword", String.format("0x%02x", ub(pc + 3 + i)), "", "", callee, "inline 4-byte store");
            return;
        }
        if (tgt == 0x181A && s.r[3].k == 1 && s.r[3].c == 1 && s.r[2].k == 1 && s.r[1].k == 1) { // memset(dst R3:R2:R1, val R5, n R6:R7)
            int d = s.r[2].c << 8 | s.r[1].c;
            if (!ram(d)) addW(pc, d, "fill", s.r[5].k == 1 ? String.format("0x%02x", s.r[5].c) : "?", "", "", callee, "len=" + (s.r67() >= 0 ? String.valueOf(s.r67()) : "?"));
            return;
        }
        if (tgt == 0x11B3 && s.r[5].k == 1 && s.r[5].c == 1 && s.r[4].k == 1 && s.r[0].k == 1) { // memcpy(dst R5:R4:R0, src R3:R2:R1, n R6:R7)
            int d = s.r[4].c << 8 | s.r[0].c;
            if (!ram(d)) {
                int n = s.r67();
                String src = s.r[3].k == 1 && s.r[2].k == 1 && s.r[1].k == 1 ? String.format("%s:%04x", s.r[3].c == 0xFF ? "code" : "mem" + s.r[3].c, s.r[2].c << 8 | s.r[1].c) : "?";
                String bytes = "";
                if (src.startsWith("code") && n > 0 && n <= 32) {
                    int sa = s.r[2].c << 8 | s.r[1].c; StringBuilder b = new StringBuilder();
                    for (int i = 0; i < n; i++) b.append(String.format("%02x", ub(sa + i)));
                    bytes = b.toString();
                }
                addW(pc, d, "burst", bytes.isEmpty() ? "?" : "0x" + bytes, "", "", callee, "src=" + src + " len=" + (n >= 0 ? n : -1));
            }
            return;
        }
        int a = s.r67();
        if (a >= 0 && portAddrs.contains(a)) { // address-port helper: R5=index, R3=value
            int ix = s.r[5].k == 1 ? s.r[5].c : -1;
            String[] pn = ix >= 0 && portNames.get(a).get(ix & 0x7F) != null ? portNames.get(a).get(ix & 0x7F) : null;
            String name = pn != null ? pn[1] : "";
            addW(pc, a + 1, "dp-call", s.r[3].k == 1 ? String.format("0x%02x", s.r[3].c) : "?", "", "", callee,
                 "port=" + String.format("%04x", a) + " idx=" + (ix >= 0 ? String.format("0x%02x", ix) : "?") + (name.isEmpty() ? "" : " " + name)
                 + " R4=" + rv(s.r[4]) + " R3=" + rv(s.r[3]));
            return;
        }
        if (a >= 0 && (a >> 8) != 0 && labelAddrs.contains(a) && !ram(a)) {
            addW(pc, a, "callarg", "?", "", "", callee, "R5=" + rv(s.r[5]) + " R3=" + rv(s.r[3]) + " R4=" + rv(s.r[4]));
        }
    }
    String rv(V v) { return v.k == 1 ? String.format("%02x", v.c) : "?"; }

    // ---- rows ----
    int[] funcOf(int pc) {
        Integer e = funcEntries.floor(pc);
        return new int[]{e == null ? -1 : e};
    }
    String fhead(int pc) {
        int e = funcOf(pc)[0];
        return e < 0 ? "\t" : String.format("%04x\t%s", e, funcNames.getOrDefault(e, ""));
    }

    String portName(S s, int d) {
        if (s.pport >= 0 && d == s.pport + 1 && s.pidx.k == 1) {
            Map<Integer, String[]> m = portNames.get(s.pport);
            String[] n = m == null ? null : m.get(s.pidx.c & 0x7F);
            return String.format("[port %04x idx %02x] ", s.pport, s.pidx.c) + (n != null ? n[1] : "");
        }
        return null;
    }

    void addW(int pc, int reg, String kind, String value, String andm, String orm, String callee, String note) {
        String name = reg >= 0 ? regName(reg) : "";
        rowsW.add(String.format("%d\t%04x\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s", bank, pc, fhead(pc),
                reg >= 0 ? String.format("%04x", reg) : "?", name, kind, value, andm, orm, callee) + "\t" + note);
    }

    void writeRow(int pc, S s, int d) {
        if (d >= 0 && ram(d)) return;
        V a = s.a;
        String kind, value = "", am = "", om = "", note = "";
        if (a.k == 1) { kind = "set"; value = String.format("0x%02x", a.c); }
        else if (a.k == 2 && a.reg == d) {
            boolean keep = a.and == 0xFF, noor = a.or == 0, noxor = a.xor == 0;
            if (noxor && keep && noor) return; // read-write-back of the same value
            if (noxor && keep) { kind = "or"; om = String.format("0x%02x", a.or); }
            else if (noxor && noor) { kind = "and"; am = String.format("0x%02x", a.and); }
            else if (noxor) { kind = "rmw"; am = String.format("0x%02x", a.and); om = String.format("0x%02x", a.or); }
            else { kind = "xor"; am = String.format("0x%02x", a.and); om = String.format("0x%02x", a.or); note = String.format("xor=0x%02x", a.xor); }
        } else if (a.k == 2) { kind = "copy"; note = String.format("from %04x", a.reg); }
        else { kind = "unk"; }
        String pn = portName(s, d);
        String callee = "";
        if (pn != null) { kind = "dp-" + kind; note = (note + " " + pn).trim(); }
        // data-port write: the data-port register itself is the target
        String name = d >= 0 ? regName(d) : "";
        rowsW.add(String.format("%d\t%04x\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s", bank, pc, fhead(pc),
                d >= 0 ? String.format("%04x", d) : "?", name, kind, value, am, om, callee, note));
    }

    void readRow(int pc, S s, int d) {
        if (d >= 0 && ram(d)) return;
        // lookahead for an ANL A,#m / context bytes
        int p = (pc + 1) & 0xFFFF, mask = -1; String ctx = "";
        for (int i = 0; i < 4; i++) {
            int o = ub(p);
            if (o == 0x54) { mask = ub(p + 1); break; }
            if (o == 0xF0 || o == 0x22 || o == 0x12 || o == 0x02) break;
            p += LEN[o];
        }
        String pn = d >= 0 ? portName(s, d) : null;
        rowsR.add(String.format("%d\t%04x\t%s\t%s\t%s\t%s\t%s\t%s", bank, pc, fhead(pc),
                d >= 0 ? String.format("%04x", d) : "?", d >= 0 ? regName(d) : "",
                mask >= 0 ? String.format("0x%02x", mask) : "", "", pn == null ? "" : pn));
    }
}
