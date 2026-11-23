"""Common-region metric of one image (numbers only, no threshold): used by stats.py and fw_gates.py (tmp/fw/<stem>.gates.json "common").

Common = [0, COMMON_END), copied into every bank image. Source: the linker map (area sizes) and fw/bank_layout.tsv (slots).
- areas: plain sum of the linked areas below COMMON_END, per class (stubs ST*, function chunks CH*, residual CSEG / HOME / GSINIT / XINIT / vectors).
- slots: what the sticky layout reserves (chunk slot = size + 4 + size/32, stub slot 8 B, residual to #resid_end); this is the figure that fails the link.
"""
import re
from pathlib import Path

import chip_mem as CM

AREA = re.compile(r"^(\S+)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =\s+(\d+)\. bytes \(([^)]*)\)")


def areas(map_text: str) -> dict:
    """{(name, addr): size} of the CODE areas that start in common (the map repeats each area once per page)."""
    out = {}
    for line in map_text.splitlines():
        m = AREA.match(line)
        if m and "CODE" in m.group(5) and int(m.group(2), 16) < CM.COMMON_END and int(m.group(4)):
            out[(m.group(1), int(m.group(2), 16))] = int(m.group(4))
    return out


def layout_slots(layout: Path) -> dict:
    """{'resid_end', 'stub_slots', 'chunk_slots', 'stubs', 'chunks'} of the region C rows of a bank_layout.tsv."""
    r = {"resid_end": CM.RESID_END, "stubs": 0, "stub_slots": 0, "chunks": 0, "chunk_slots": 0}
    for line in layout.read_text().splitlines():
        if line.startswith("#resid_end"):
            r["resid_end"] = int(line.split()[1], 0)
        elif not line.startswith("#") and line.strip():
            kind, _name, region, _off, slot = line.split("\t")[:5]
            if region == "C":
                k = "stub" if kind == "stub" else "chunk"
                r[k + "s"] += 1
                r[k + "_slots"] += int(slot)
    return r


def measure(map_path: Path, layout: Path | None = None) -> dict:
    a = areas(map_path.read_text(errors="replace"))
    cls = {"stub": [0, 0], "chunk": [0, 0]}
    resid, chunks = {}, []
    for (name, _addr), size in a.items():
        if name.startswith("ST_"):
            cls["stub"][0] += 1
            cls["stub"][1] += size
        elif name.startswith("CH_"):
            cls["chunk"][0] += 1
            cls["chunk"][1] += size
            chunks.append((size, name[3:]))
        else:
            resid[name] = resid.get(name, 0) + size
    total = sum(a.values())
    top = [{"name": n, "bytes": s} for s, n in sorted(chunks, reverse=True)[:10]]
    rec = {"common_bytes": CM.COMMON_END,
           "areas": {"used": total, "free": CM.COMMON_END - total,
                     "stubs": cls["stub"][0], "stub_bytes": cls["stub"][1],
                     "chunks": cls["chunk"][0], "chunk_bytes": cls["chunk"][1],
                     "residual": dict(sorted(resid.items(), key=lambda kv: -kv[1])), "residual_bytes": sum(resid.values())},
           "top_chunks": top}
    if layout is not None and layout.is_file():
        s = layout_slots(layout)
        used = s["resid_end"] + s["stub_slots"] + s["chunk_slots"]
        rec["slots"] = {"used": used, "free": CM.COMMON_END - used, "resid_end": s["resid_end"],
                        "stub_rows": s["stubs"], "stub_slot_bytes": s["stub_slots"],
                        "chunk_rows": s["chunks"], "chunk_slot_bytes": s["chunk_slots"]}
    return rec


def lines(rec: dict) -> list[str]:
    a = rec["areas"]
    out = [f"common {rec['common_bytes']} B: areas used {a['used']} free {a['free']}; stubs {a['stubs']} = {a['stub_bytes']} B; "
           f"chunks {a['chunks']} = {a['chunk_bytes']} B; residual {a['residual_bytes']} B ("
           + ", ".join(f"{k} {v}" for k, v in a["residual"].items()) + ")"]
    if "slots" in rec:
        s = rec["slots"]
        out.append(f"common slots: used {s['used']} free {s['free']} = residual {s['resid_end']} + stub slots {s['stub_slot_bytes']} ({s['stub_rows']} rows) + "
                   f"chunk slots {s['chunk_slot_bytes']} ({s['chunk_rows']} rows)")
    out.append("common top chunks: " + ", ".join(f"{t['name']} {t['bytes']}" for t in rec["top_chunks"]))
    return out


if __name__ == "__main__":
    import json
    import sys
    m = Path(sys.argv[1])
    print("\n".join(lines(r := measure(m, Path(sys.argv[2]) if len(sys.argv) > 2 else None))))
    print(json.dumps(r))
