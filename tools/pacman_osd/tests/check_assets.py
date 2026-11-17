#!/usr/bin/env python3
"""Independent pixel reconstruction of every phase, no hardware access."""
import json
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import generate_assets as G

class Assets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=json.loads((ROOT/'generated/manifest.json').read_text())
        cls.raw=(ROOT/'generated/glyphs.bin').read_bytes()
        cls.tiles,_,_,cls.ids,_=G.make_assets()

    def test_known_pixel_order(self):
        t=[[0]*12 for _ in range(18)];t[0][0]=1
        self.assertEqual(G.pack(t)[:3],bytes([0,0,128]))
        t=[[0]*12 for _ in range(18)];t[1][11]=1
        self.assertEqual(G.pack(t)[:3],bytes([1,0,0]))

    def test_all_cached_phases(self):
        # Decode bytes independently and OR the four fragments back into a
        # 24x24 image. Compare to the original sprite translated by dx,dy.
        for fi,name in enumerate(self.m['phase_frames']):
            for py in range(4):
                for px in range(4):
                    got=[[0]*24 for _ in range(24)]
                    for q in range(4):
                        gid=self.m['phase_glyphs'][fi*64+(py*4+px)*4+q]
                        tile=self.raw[gid*27:gid*27+27]
                        for y in range(12):
                            v=int.from_bytes(tile[(y//2)*3:(y//2)*3+3],'little')
                            for x in range(12):
                                bit=(v>>(23-(y%2)*12-x))&1
                                got[(q//2)*12+y][(q%2)*12+x]=bit
                    src=self.tiles[self.ids[name]]
                    expected=[[src[y-py*3][x-px*3] if 0<=y-py*3<12 and 0<=x-px*3<12 else 0
                               for x in range(24)]for y in range(24)]
                    self.assertEqual(got,expected,(name,px,py))

    def test_budget_and_padding(self):
        m=self.m
        self.assertLessEqual(m['glyph_count'],512)
        self.assertEqual(len(self.raw),27*m['glyph_count'])
        self.assertLessEqual(m['sram_words'],12288)
        self.assertEqual(m['sram_words'],36+1+28*36+9*m['glyph_count'])
        for i in range(m['glyph_count']):
            self.assertEqual(self.raw[i*27+18:i*27+27],bytes(9))
        self.assertTrue(all(g<m['base_glyph_count'] for g in m['initial_map']))

if __name__=='__main__':unittest.main(verbosity=2)
