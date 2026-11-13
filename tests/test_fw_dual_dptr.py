"""Safety regressions for hand-written/generated ISR link inputs; no SDK/hardware."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fw_dual_dptr_check import audit, check_link_inputs

SAVE = 'push 0x86\npush 0x84\npush 0x85\nmov 0x86,#0\n'
RESTORE = 'pop 0x85\npop 0x84\npop 0x86\nreti\n'


class InterruptPreservation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def asm(self, code, name='handler.asm'):
        p = self.root / name
        p.write_text('.module fixture\n.area CSEG (CODE)\n_irq:\n' + code)
        return p

    def good(self, code):
        checked, errors = audit([self.asm(code)])
        self.assertEqual(errors, [])
        self.assertTrue(checked)

    def bad(self, code):
        _, errors = audit([self.asm(code)])
        self.assertTrue(errors)
        self.assertIn('handler.asm:_irq:', errors[0])

    def test_canonical_calling_handler(self):
        self.good(SAVE + 'push acc\nlcall _worker\npop acc\n' + RESTORE)

    def test_sfr_aliases(self):
        self.good((SAVE + RESTORE).replace('0x86', 'DPS').replace('0x84', 'DPL1').replace('0x85', 'DPH1'))

    def test_empty_vector_only_exception(self):
        self.good('reti\n')
        self.bad('mov dptr,#0xd700\nreti\n')
        self.bad('lcall _worker\nreti\n')

    def test_missing_each_save_and_restore(self):
        for reg in ('0x86', '0x84', '0x85'):
            with self.subTest(reg=reg):
                self.bad((SAVE + RESTORE).replace(f'push {reg}\n', ''))
                self.bad((SAVE + RESTORE).replace(f'pop {reg}\n', ''))

    def test_swapped_restores(self):
        self.bad(SAVE + 'pop 0x84\npop 0x85\npop 0x86\nreti\n')

    def test_save_after_dptr_or_call_is_unsafe(self):
        self.bad('mov dptr,#0xd700\n' + SAVE + RESTORE)
        self.bad('lcall _worker\n' + SAVE + RESTORE)

    def test_selector_must_be_reset_before_body(self):
        self.bad(SAVE.replace('mov 0x86,#0\n', '') + 'lcall _worker\n' + RESTORE)

    def test_branch_skipping_restore(self):
        self.bad(SAVE + 'jz 00100$\n' + RESTORE.replace('reti\n', '00100$:\nreti\n'))

    def test_two_valid_paths(self):
        self.good(SAVE + 'jz 00100$\nnop\n00100$:\n' + RESTORE)

    def test_branch_skipping_a_pop(self):
        self.bad(SAVE + 'jz 00100$\npop 0x85\n00100$:\npop 0x84\npop 0x86\nreti\n')

    def test_no_work_after_restore(self):
        self.bad(SAVE + RESTORE.replace('reti', 'lcall _worker\nreti'))

    def test_critical_handler(self):
        self.good('clr ea\n' + SAVE + RESTORE.replace('reti', 'setb ea\nreti'))

    def test_unsupported_stack_and_external_control_flow(self):
        for instruction in ('dec sp', 'mov sp,#0x80', 'ret', 'jmp @a+dptr',
                            'ljmp sdcc_atomic_maybe_rollback'):
            self.bad(SAVE + instruction + '\n' + RESTORE)

    def test_vector_target_without_reti_is_still_checked(self):
        vectors = self.root / 'awto_vectors.asm'
        vectors.write_text('.area VECTORS (ABS,CODE)\n.org 0\nljmp __sdcc_gsinit_startup\n.org 3\nljmp _irq\n.org 0x0b\nreti\n')
        _, errors = audit([vectors, self.asm('ljmp _some_other_handler\n')])
        self.assertTrue(any('handler.asm:_irq:' in error for error in errors))
        _, errors = audit([vectors])
        self.assertIn('vector target _irq: no assembly in link inputs', errors)

    def test_every_linked_object_needs_assembly(self):
        asm = self.asm(SAVE + RESTORE)
        checked = check_link_inputs([asm.with_suffix('.rel')])
        self.assertTrue(checked)
        with self.assertRaisesRegex(ValueError, 'assembly missing'):
            check_link_inputs([self.root / 'binary_only.rel'])

    def test_option_is_off_by_default_and_explicit_flags_propagate(self):
        script = ('import sys;from pathlib import Path;sys.path.insert(0,"scripts");'
                  'import sdcc_tools as t;import keil2sdcc as k;'
                  'c=k.sdcc_cmd(Path("/tmp/test.c"),Path("/tmp"),[],[],2);'
                  'assert c.count("--dual-dptr")==int(t.DUAL_DPTR);'
                  'print(t.CFLAGS_EXTRA)')
        root = Path(__file__).resolve().parents[1]
        for flags in ('', '--dual-dptr'):
            env = dict(os.environ, K2S_SDCC_EXTRA=flags, AWTO_SDCC_BE='0')
            output = subprocess.check_output([sys.executable, '-c', script], cwd=root, env=env, text=True)
            self.assertEqual('--dual-dptr' in output, bool(flags))


if __name__ == '__main__':
    unittest.main()
