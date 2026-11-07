#!/usr/bin/env python3
"""Offline tests for scripts/msg_table.py (#56): encode/decode, stability, image lookup, fallback. Run: python3 scripts/msg_table_test.py"""
import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import msg_table as M  # noqa: E402

TSV = ("0101\tSystem\tKernel/A.c:10\tPower on\t1\n"
       "0110\tRx0\tKernel/B.c:20\tVSC change\t0\n"
       "0120\tFRC\tKernel/A.c:30\tgot \\t tab\t1\n"
       "0120\tFRC\tKernel/C.c:99\tgot \\t tab\t1\n"
       "0130\tFRC\tKernel/C.c:40\tPower on\t1\n")


class T(unittest.TestCase):
    def test_roundtrip(self):
        blk = M.build(M.rows_from_tsv(TSV))
        i = M.parse(blk)
        self.assertEqual(i["count"], 3)                                  # disabled row dropped, dup id folded
        self.assertEqual(i["ids"][0x120], ("FRC", "Kernel/A.c:30", "got \t tab"))
        self.assertEqual(i["ids"][0x130][2], "Power on")
        self.assertNotIn(0x110, i["ids"])

    def test_deterministic_and_change_detected(self):
        a = M.build(M.rows_from_tsv(TSV))
        self.assertEqual(a, M.build(M.rows_from_tsv(TSV)))
        b = M.build(M.rows_from_tsv(TSV + "0140\tFS\tKernel/D.c:1\tnew\t1\n"))
        self.assertNotEqual(M.parse(a)["hash"], M.parse(b)["hash"])

    def test_corrupt_rejected(self):
        blk = bytearray(M.build(M.rows_from_tsv(TSV)))
        blk[-3] ^= 1
        with self.assertRaises(ValueError):
            M.parse(bytes(blk))
        with self.assertRaises(ValueError):
            M.parse(b"\xff" * 64)

    def test_too_big(self):
        rows = [(i, "System", "f.c", 1, "x" * 200) for i in range(1, 200)]
        with self.assertRaises(ValueError):
            M.build([(i, c, f, l, t + str(i)) for i, c, f, l, t in rows])

    def test_image_lookup_and_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "fw").mkdir(); (root / "tmp/fw").mkdir(parents=True)
            (root / "fw/msgids.tsv").write_text(TSV)
            img = bytearray(b"\xff" * (14 * 0x10000))
            blk = M.build(M.rows_from_tsv("0101\tSystem\tKernel/A.c:10\tfrom image\t1\n"))
            img[M.MSG_ADDR:M.MSG_ADDR + len(blk)] = blk
            (root / "tmp/fw/u-img.bin").write_bytes(img)
            (root / "tmp/fw/U-flashed.json").write_text(json.dumps({"image": str(root / "tmp/fw/u-img.bin")}))
            ids, src = M.load_ids(root, "U")
            self.assertEqual(ids[0x101], ("Kernel/A.c:10", "from image"))
            self.assertTrue(src.startswith("flashed image"))
            ids, src = M.load_ids(root, "nosuch")                      # no flashed.json -> tsv
            self.assertEqual(src, "fw/msgids.tsv")
            self.assertEqual(ids[0x110][1], "VSC change")              # tsv fallback keeps disabled rows
            (root / "tmp/fw/u-img.bin").write_bytes(b"\xff" * 0x100000)  # image without a table -> tsv
            self.assertEqual(M.load_ids(root, "U")[1], "fw/msgids.tsv")


if __name__ == "__main__":
    unittest.main()
