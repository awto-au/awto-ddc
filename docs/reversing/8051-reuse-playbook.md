# 8051 firmware reversal: what worked and how to reuse it

Status: reconstructed from the RTD2795T/JXC work through 2026-11-09. This is the
repeatable process, not a claim that every step applies unchanged to every 8051.
The worked example is the Realtek RL6449 firmware; the concrete next target is
`/mnt/2tb/git/awto-jms539` (JMicron JMS539).

## Executive result

The main force multiplier was not better manual decompilation. It was removing
known code from the manual queue before reversing application code:

1. identify the architecture, memory model, bank layout and compiler family;
2. find the closest SDK, maps, sibling images and object libraries;
3. match library functions with relocation-aware signatures;
4. import register names, types and exact library names mechanically;
5. use sibling/SDK fingerprints to propose more names;
6. manually reverse and verify only the unmatched application and board code.

For the Realtek image this established that the vendor used the same
`RL6449_FunctionLib.LIB` build as the SDK copy. The match supplied 110 unique
vendor function addresses without manually reversing those functions. The
available library/source audit also showed that the object-only AdvancedLib was
not linked, and that the few source-less FunctionLib routines were not used.

The reusable lesson is: identify boilerplate per function, tag it `[lib]`, and
move on. A library match is identification, not proof that every sibling or
nearby function has the same role.

## What the Realtek work actually established

### Image and machine model

- RTD2795T/RL6449, DW8051-compatible core, one 64 KiB code program per flash
  bank, seven vendor banks.
- Ghidra language: `8051:BE:16:default`.
- Banks contained an identical common-code prefix and bank-specific tails. Each
  bank was imported as a separate Ghidra program rather than pretending the
  whole flash was one flat 8051 address space.
- XDATA held both scaler registers and ordinary RAM. The RTDCustomerTool
  register database supplied 9,209 labels, applied before hand names.
- Original flash was dumped twice and compared before the first write. Firmware
  bytes and the Ghidra project stayed in the vendor store; scripts, derived
  names and notes stayed in the private repository.

### Compiler identification: what was and was not proven

Several pieces of evidence identified the Realtek build as Keil C51-family:

- Keil-style startup and runtime-helper shapes in the firmware;
- Keil register argument/return conventions and generic-pointer layout;
- big-endian multi-byte storage and C51 memory spaces;
- Keil OMF-51 libraries and `.Uv2` projects in the matching SDK;
- a compatible bank linker/startup implementation and a matching FunctionLib.

The SDK supplied stronger build metadata than the stripped firmware did:

- `C51FL=21646608` decoded to `LARGE OPTIMIZE(9,SPEED) BROWSE DEBUG
  OBJECTEXTEND`, with normal integer promotion;
- the RL6432 reference map records banked `BL51 V6.11`;
- local C51 V9.60.7 under Wine was an oracle used to compile probes and measure
  the ABI/semantics. It was not evidence that the vendor firmware itself was
  built with V9.60.7.

That distinction is important. Startup/helper shapes can establish a compiler
family and ABI, but an exact compiler version normally needs a banner, listing,
map, project metadata, or an exact match against versioned runtime libraries.
Do not turn “looks like Keil C51” into an exact version claim.

The cheap compiler checks we used or built were:

- strings, paths, banners, maps, listings, `.Uv2` controls and symbol files;
- reset/vector layout and 8051 opcode-density checks;
- Keil startup clear-loop patterns (`scripts/fw_pkg_scan.py`);
- known runtime helper bodies and calling patterns;
- one-file compiler probes (`scripts/keil_probe.py`);
- uVision option decoding (`scripts/keil_uv_flags.py`);
- runtime semantic probes against Keil and SDCC;
- OMF-51 library parsing and exact masked matching.

Keil C51 facts recovered by probes included argument/return registers, memory
space pointer sizes and tags, big-endian layout, LSB-first bit-field packing,
evaluation order, `bit` semantics, startup behaviour and division/modulo edge
cases. These facts improved both Ghidra types and the later SDCC port.

### SDK and library discovery

The SDK hunt began with chip-family and register-set evidence rather than its
directory name. The public RL64xx tree contained:

- the matching RL6449 register and board family;
- C51/uVision projects, link scripts and startup assembly;
- most Kernel and FunctionLib C sources;
- `RL6449_FunctionLib.LIB` and `RL6449_AdvancedLib.LIB`;
- a built RL6432 sibling with a large `.m51` map and bank hex files.

The library process was:

1. `scripts/omf51_lib.py` parsed extended OMF-51 modules, code segments,
   publics, externals and fixups.
2. `scripts/rtk_libsig.py build` made one signature per function and wildcarded
   link-time relocation bytes.
3. `scripts/rtk_libsig.py match` searched every firmware bank and classified
   matches as `EXACT`, `EXACT-MULTI`, `NEAR`, `SIBLING`, `SHORT` or `ABSENT`.
4. Only unique exact matches were converted into `[lib]` Ghidra name rows.
5. Near matches were reviewed line by line. Several were look-alike wrappers,
   not the claimed function; the `SIBLING` class was added to prevent these
   false names.
6. `srccheck` compared library publics with all available C definitions so we
   knew which binary routines actually lacked source.

The final FunctionLib result was 111 exact functions at 110 unique vendor
addresses, two near matches, 48 too short to judge and 209 absent. Review found
two genuine source-revision variants; the other apparent variants were matcher
artefacts or sibling wrappers. AdvancedLib MBR/TCON routines were absent.

This was the point where “do not reverse the libraries” became evidence-backed:
exact matches got names and were removed from the manual queue; near/short
matches did not.

## The Ghidra process we used

### Durable sources of truth

- Ghidra project and firmware bytes: vendor analysis store.
- Per-bank names/comments: `re/jxc-4k/ghidra_names_bank<N>.tsv`.
- Cross-bank corrections: `ghidra_names_phase3.tsv`.
- Seeds: `seeds_bank<N>.txt`.
- SDK types and globals: `sdk_types.tsv`, `ghidra_globals*.tsv`.
- Generated outputs: named/unnamed decompile, disassembly, register reads and
  writes for every bank.

Generated decompile was never the source of truth. A finding went into a TSV,
was applied to the project, and was then re-exported.

### Import and mechanical analysis

`scripts/ghidra_re.py import|fixret|regen <bank|all>` orchestrated headless
Ghidra. For a new bank it:

1. imported the 64 KiB bank with the binary loader at code address zero;
2. selected `8051:BE:16:default`;
3. seeded interrupt vectors and likely call targets;
4. repaired Ghidra's mistaken non-returning Keil helpers;
5. applied register and indexed-data-port labels;
6. ensured every named function row had a real function entry;
7. applied merged hand, library and SDK names;
8. created SDK types and typed XDATA globals;
9. exported register access, decompile and disassembly.

The seed generator used the seven interrupt-vector locations plus in-range
`LCALL` targets seen at least twice in the bank-specific region. False targets
were possible when data contained byte `0x12`, so these were `[guess]` seeds,
not names.

`FixKeilReturns.java` was necessary because Ghidra marked helpers such as
long-multiply/divide and XDATA-stack routines non-returning, then truncated
callers after their first call. It cleared bad call overrides, restored
fall-through disassembly and left the genuinely non-returning inline switch
table helpers alone.

### Mechanical naming above the raw disassembler

The following passes were applied before broad manual reversal:

- exact OMF library names (`[lib]`);
- 9,209 scaler-register labels from the decoded vendor register database;
- data-port index labels;
- SDK-function candidates matched by weighted register/immediate fingerprints
  (`[auto-sdk]`);
- 464 SDK types (368 enums, 96 structs/unions), generated with the measured Keil
  data layout;
- XDATA global candidates inferred from identified SDK functions and their
  fixed-offset accesses;
- common-area names copied from bank 0, and bank-call thunk names regenerated
  from final targets.

The SDK register matcher compared the set of registers and the immediate
mask/value tokens used by each vendor function with the SDCC assembly of the
same SDK source. It required a minimum score, enough distinct registers and a
margin over the runner-up. It proposed candidates; exact library signatures
and hand-verified names had higher authority.

Global recovery was deliberately conservative. It voted from SDK
`global+offset` accesses in already identified functions, required independent
support, resolved overlaps, and did not extrapolate a module's XDATA order from
source declaration order. Keil's linker did not preserve declaration order.

### Manual loop and verification

Manual work proceeded leaves-first:

1. choose an unnamed hardware-facing function;
2. use register read/write exports, constants, strings, known callees, call-site
   arguments and typed XDATA as evidence;
3. compare the closest SDK source and generated assembly;
4. name only when the SDK identity or role was clear;
5. tag the basis and confidence;
6. regenerate and read the new decompile;
7. repeat until a complete pass adds no reliable names.

Confidence mattered:

- exact library signature, matching call graph/register set, or hand-checked
  sequence could become `CONFIRMED`;
- one weak signal or an agent reading stayed `PLAUSIBLE`;
- contradicted names became `REFUTED` and were retracted;
- plausible names were not used as a basis for firmware changes.

The general rules from the shared reversing process still applied: reverse the
accessor code rather than guessing from data, one address gets one name, wrong
names are worse than missing names, and every loop ends with persisted names
and a regeneration.

## Mistakes and limits worth carrying forward

- An exact library match is per function, not permission to rename adjacent or
  similar functions.
- Very short functions do not carry enough entropy for safe signature naming.
- Wrapper families often differ by one register/index constant; fuzzy matching
  confuses siblings unless exact placements are reserved first.
- A FunctionID/signature database is compiler/version/option sensitive. A miss
  can mean the wrong signature build, not application code.
- Imported register labels do not prove a function's role. Masks, values,
  sequencing and callers still matter.
- Ghidra's default 8051 analysis can mistake inline data/switch tables for code
  and can mis-handle Keil shared-return/non-return helpers.
- Structs generated from a nearby SDK configuration can differ from the vendor
  build. Apply them only where address/size/access evidence agrees.
- Bit-field order is LSB-first for the measured Keil C51 build. The earlier
  MSB-first note in `docs/re-full-reversal.md` was stale and has been corrected.
- Do not infer exact compiler version from generic code-generation style.
- Preserve the project or rich exports. A prose summary is not a substitute for
  names, types, xrefs and decompile.

## Reusable plan for another 8051 firmware

Each phase has an exit gate. Do not start bulk manual naming before phases 0-4.

### Phase 0: define the target and safety boundary

- Record product, board revision, chip marking, transport and the exact question
  the reversal must answer.
- Separate read-only research from any hardware write path.
- Establish where vendor binaries/projects live and what derived material may be
  committed.
- If a device may be written later, obtain two identical original dumps first
  and document an independently credible recovery path.

Exit: target identity, evidence policy and no-write boundary are written down.

### Phase 1: acquire and normalise every image

- Preserve updater packages, device captures and sibling versions unchanged;
  record hashes, sizes and provenance.
- Unpack containers without executing updater applications.
- Locate headers, trailers, checksums/CRCs, configuration/NVRAM, duplicate copies
  and padding.
- Compare multiple reads and versions. Determine whether apparent duplicate
  regions are true copies or address wrap-around.
- Extract the logical code images but retain offsets back to the source package.

Exit: repeatable byte inputs and a documented image map.

### Phase 2: identify machine, layout and ABI cheaply

- Confirm 8051/8052 using datasheet evidence plus reset/vector/opcode structure.
- Determine code load address, code/XDATA/IDATA/SFR ranges, banking/thunks and
  whether multiple 64 KiB programs are present.
- Scan strings, paths, banners, maps/listings, startup loops and runtime helpers.
- Form a compiler-family/ABI hypothesis and tag its confidence.
- Compile small probes with candidate compilers when access is lawful and useful;
  measure byte order, pointer layout, argument registers, bit-fields and helpers.
- Do not claim an exact compiler version until direct metadata or an exact
  versioned-runtime match supports it.

Exit: a Ghidra language/load map and an explicit ABI fact table.

### Phase 3: find code we should not reverse

- Search for SDKs, design kits, sibling firmware, maps, symbols, libraries and
  source using chip-family/register evidence, not filenames alone.
- Inventory object libraries and available sources.
- For OMF-51, parse relocations and wildcard fixup bytes before matching.
- Build signatures for every plausible library version/compiler-option set.
- Classify exact, multiple, near, short, sibling and absent results.
- Apply only unique exact names automatically; manually verify near matches.
- If no library is available, build a corpus from sibling firmware and use
  Ghidra Version Tracking plus verified per-function byte/control-flow matches.

Exit: library/boilerplate functions are named and removed from the manual queue.

### Phase 4: build the reproducible Ghidra pipeline

- Create one program per real code address space/bank.
- Apply the memory map and SFR/XDATA/register labels before manual analysis.
- Seed vectors and repeated call targets, but keep heuristic seeds distinct from
  confirmed function names.
- Add target-specific fixes for shared returns, inline switch tables and data
  decoded as code.
- Keep names/comments/types in versioned files; provide `import`, `regen` and
  export commands.
- Export named and raw decompile, disassembly, call graph and hardware-register
  accesses.
- Add a progress report and checks for duplicate names, stale addresses and
  analysis drift.

Exit: deleting and recreating the generated exports does not lose knowledge.

### Phase 5: exploit siblings and source

- Run Version Tracking between closest firmware versions before manual work.
- Match SDK functions using registers, constants, call graph and table/string
  evidence, with an acceptance threshold and runner-up margin.
- Generate types from the measured ABI, not host-C defaults.
- Recover globals only from anchored functions and independently supported
  offsets; do not extrapolate linker layout from declaration order.
- Treat all automatic names as candidates until verified.

Exit: the mechanical naming/type passes are exhausted and their accuracy has
been sampled.

### Phase 6: manually reverse only the remaining application code

- Work leaves-first and hardware-first.
- Persist function, parameter, local and global names as each function is read.
- Reverse accessors before interpreting tables/configuration.
- Use explicit evidence tags and leave unresolved functions unnamed.
- Regenerate after each coherent batch and revisit callers whose callees are now
  known.
- Continue until a complete sweep produces no new confirmed names, or until the
  question that justified the reversal is answered.

Exit: required behaviour is understood, with guesses visibly separated from
facts.

### Phase 7: dynamic confirmation and hand-off

- Validate algorithms with host-side reimplementations and known vectors.
- When safe, emulate pure routines or compare traces across sibling images.
- Keep device writes out of the RE loop; a separate procedure must establish
  selection, erase scope, preservation, verification, reset and recovery.
- Publish the image map, ABI facts, library-match report, Ghidra regeneration
  command, names/types, open questions and stop condition.

Exit: another session can reproduce the analysis without rediscovering it.

## Applying this now to `awto-jms539`

### What is already available

- The JMS539 datasheet identifies an 8051 core.
- Repeatable 64 KiB and 128 KiB address-space captures exist; the latter contains
  two identical halves, but physical flash size versus wrap-around is unresolved.
- The installed 40.06 image matches a third-party 40.06 image for its first
  49,408 bytes. A 40.16 ORICO sibling is also present.
- Both images have a verified firmware marker/identifier and custom CRC at
  `0xBFF0..0xBFFF`; configuration begins at `0xC000` and is outside that CRC.
- After alignment, roughly 29 KiB of 40.06 and 40.16 code is identical. This is
  excellent Version Tracking material.
- The updater has already been analysed separately as a C++Builder host program;
  its recovered write/read/CRC logic should remain an oracle, not be mixed with
  claims about the 8051 compiler.
- Firmware currently has D52 disassembly, but no equivalent reproducible 8051
  Ghidra/name/type pipeline.
- No verified JMS539 SDK, design guide, compiler or object library is currently
  available. The simple Realtek Keil startup-clear signature is absent from both
  local JMS539 images, so Keil must not be assumed.

### Recommended JMS539 work order

1. **Freeze the image map.** Record `0x0000..code-end`, non-code tables,
   `0xBFF0..0xBFFF` trailer, `0xC000..0xC0FF` configuration and bytes beyond the
   49,408-byte file separately. Keep flash-capacity/wrap-around unresolved.
2. **Create two firmware Ghidra programs**, 40.06 and 40.16, at code base zero
   with `8051:BE:16:default`. Do not reuse the updater's x86 project.
3. **Seed conservatively.** Start with reset/interrupt/jump-table targets and
   repeated `LCALL` targets. Mark the dense low-address stubs/table structure as
   unresolved until its callers establish whether it is a ROM/API jump table.
4. **Run Version Tracking 40.06 ↔ 40.16 before naming.** Propagate only high
   confidence matches; report moved, inserted and unmatched functions.
5. **Identify compiler/ABI.** Catalogue startup, switch helpers, multiply/divide,
   generic-pointer and XDATA helper shapes in both versions. Compare against
   Keil, SDCC and any JMicron sibling corpus, but report family/ABI separately
   from exact version.
6. **Build a JMS sibling corpus.** Index every trustworthy JMS539 image by hash,
   version and board/product identifier. Extract exact common functions into a
   relocation-aware signature set. Later add a real SDK/`.LIB` if one is found.
7. **Map memory spaces from code.** Start with the confirmed configuration loader
   (`0xC000` into XDATA `0x3800`), CRC/trailer validator, USB/SCSI command paths,
   SATA bring-up and flash access. Give only confirmed XDATA/SFR addresses names.
8. **Persist names outside the generated D52.** Add a target names TSV, seeds,
   headless import/regen/export driver and named decompile/disassembly. The D52
   listing remains a useful cross-check, not the analysis database.
9. **Reverse the application delta first.** The 40.16-only SATA/port/debug-string
   paths are likely to explain the revision; shared helpers should already be
   named by VT/signatures.
10. **Keep write safety separate.** No firmware RE result by itself resolves
    physical flash capacity, erase scope, second-copy boot fallback, `5391` versus
    live `5392`, or recovery. Those remain blockers for writing hardware.

### First deliverables for JMS539

- `docs/firmware-image-map.md`: offsets, CRC coverage, config, uncertain regions.
- `re/jms539/abi.md`: architecture/compiler evidence and unresolved questions.
- `re/jms539/ghidra_names_40.06.tsv` and `_40.16.tsv`.
- `re/jms539/seeds_*.txt`.
- `scripts/ghidra_fw.py import|regen|vt|stats`.
- per-version named decompile/disassembly/call graph and an exact-match report.
- a library/sibling signature database with provenance and match classes.
- a focused report for the updater-relevant firmware routines: trailer/CRC,
  configuration load, flash read/write command handling, boot-copy selection and
  recovery behaviour.

## Existing implementation map

The Realtek artefacts to reuse or adapt are:

- `scripts/ghidra_re.py`, `scripts/ghidra_seeds.py`;
- `re/ghidra/{SeedFile,FixKeilReturns,EnsureFunctions,ApplyRegLabels,ApplySdkTypes,ExportRegAccess}.java`;
- shared `awto-2000/tools/ghidra/{ApplyNames,ExportAll}.java`;
- `scripts/{omf51_lib,rtk_libsig}.py`;
- `scripts/{ghidra_match_sdk,ghidra_sdk_types,ghidra_globals_map}.py`;
- `scripts/{ghidra_names_merge,ghidra_verify_names,ghidra_re_stats}.py`;
- `scripts/fw_pkg_scan.py` for cheap package/8051/Keil-family triage;
- `docs/re-full-reversal.md`, `docs/realtek-libs.md`,
  `docs/rtd2795t-sdk-hunt.md`;
- awto-sdcc `docs/{keil-c51,keil-abi,keil-vs-sdcc}.md` and their probe suites;
- `awto-2000/docs/reversing/{process,toolbox,reliability-convention,mistakes}.md`.

Reuse the orchestration and evidence discipline. Replace all Realtek-specific
bank counts, register databases, common-area boundaries, XDATA ranges, SDK
types and Keil assumptions with facts measured for the new target.
