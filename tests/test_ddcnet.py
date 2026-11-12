"""Busorra host regression tests. No I2C, TAP, firmware or external dependencies.

Run: python -m unittest discover -s tests -p test_ddcnet.py -v
"""
from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import mock_open, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ddcnet_model import ModelIo, options, N


def pipe(transport="dbg", adaptive=False, io=None):
    io = io or ModelIo()
    return N.Pipe(N.make_link(io, transport, None, adaptive=adaptive), N.CTL_ECHO), io


def grow(p):
    for _ in range(2 * N.GROW_AFTER):
        p.xchg(bytes(range(p.wmax)))
    assert p.wmax == 27


class PipeTests(unittest.TestCase):
    def test_defaults_stay_conservative(self):
        p, _ = pipe()
        for _ in range(200):
            p.xchg(bytes(12))
        self.assertEqual((p.wmax, p.promotions, p.backoffs), (12, 0, 0))
        p, _ = pipe("ddcci")
        self.assertEqual(p.wmax, 10)

    def test_opt_in_growth_and_short_writes_restart_clean_streak(self):
        p, _ = pipe(adaptive=True)
        for _ in range(N.GROW_AFTER - 1):
            p.xchg(bytes(12))
        p.xchg(b"x")
        p.xchg(b"")
        self.assertEqual((p.wmax, p.clean), (12, 0))
        grow(p)
        self.assertEqual(p.promotions, 2)

    def test_full_is_flow_control_and_keeps_queued_bytes(self):
        p, model = pipe(adaptive=True)
        grow(p)
        model.poll_enabled = False
        model.rx = bytearray(120)
        p.free = N.RING                           # stale credit; firmware is authoritative
        peer = N.Peer(p, 0.002)
        peer.out = bytearray(b"1234567890abcdef")
        before = bytes(peer.out)
        old_tail = bytes(model.tx)
        old_ack = p.ack
        peer.step()
        self.assertEqual(bytes(peer.out), before)
        self.assertEqual(p.full, 1)
        self.assertEqual(p.backoffs, 0)
        self.assertEqual(p.wmax, 27)
        self.assertEqual(bytes(model.tx), old_tail[old_ack:])
        model.rx.clear()
        p.free = 0                              # only an empty poll can refresh exhausted credit
        peer.step()
        self.assertEqual(bytes(peer.out), before)
        peer.step()
        self.assertFalse(peer.out)
        self.assertTrue(bytes(model.accepted).endswith(before))

    def test_retries_preserve_seq_ack_and_entire_payload(self):
        for transport in ("dbg", "ddcci"):
            for fault in ("drop", "short", "corrupt", "seq", "free", "flags", "length"):
                with self.subTest(transport=transport, fault=fault):
                    p, model = pipe(transport)
                    model.tx += b"oldreply"
                    p.ack = 3
                    # DDC/CI may re-read a dropped/not-ready reply without rewriting.
                    model.read_faults.extend([fault] * (4 if transport == "ddcci" and fault == "drop" else 1))
                    data = b"new stream"
                    took, _, _ = p.xchg(data)
                    self.assertTrue(took)
                    self.assertEqual(bytes(model.accepted), data)
                    self.assertGreaterEqual(p.retries, 1)
                    self.assertEqual(model.requests[0], model.requests[-1])
                    self.assertTrue(bytes(model.tx).startswith(b"reply"))

    def test_recovered_large_request_backs_off_only_future_requests(self):
        p, model = pipe(adaptive=True)
        grow(p)
        model.read_faults.append("drop")
        before = len(model.accepted)
        payload = bytes(range(27))
        self.assertTrue(p.xchg(payload)[0])
        self.assertEqual(bytes(model.accepted[before:]), payload)
        self.assertEqual(model.requests[-2], model.requests[-1])
        self.assertEqual((p.wmax, p.backoffs, p.locked), (12, 1, True))
        for _ in range(100):
            p.xchg(bytes(12))
        self.assertEqual(p.wmax, 12)

    def test_valid_bad_allows_safe_rechunk_with_ack_kept(self):
        p, model = pipe(adaptive=True)
        grow(p)
        model.tx = bytearray(b"pending reply")
        p.ack = 3
        peer = N.Peer(p, 0.002)
        peer.out = bytearray(range(27))
        model.write_faults.append("bad")
        self.assertEqual(peer.step(), 0)
        self.assertEqual((len(peer.out), p.ack, p.wmax), (27, 3, 12))
        self.assertEqual(model.tx, b"pending reply")
        self.assertEqual(p.bad, 1)
        peer.step()
        self.assertEqual(len(peer.out), 15)
        self.assertEqual(model.requests[-1][2:], (3, bytes(range(12))))

    def test_write_failure_retries_before_fallback(self):
        p, model = pipe(adaptive=True)
        grow(p)
        model.write_faults.append("nak")
        self.assertTrue(p.xchg(bytes(27))[0])
        self.assertEqual((p.wmax, p.retries), (12, 1))

    def test_bad_after_lost_acceptance_reply_cannot_authorize_rechunk(self):
        p, model = pipe(adaptive=True)
        grow(p)
        payload = bytes(range(27))
        before = len(model.accepted)
        model.read_faults.append("drop")
        model.write_faults.extend([None, "bad", None])
        self.assertTrue(p.xchg(payload)[0])
        self.assertEqual(bytes(model.accepted[before:]), payload)
        self.assertEqual(model.requests[-1], model.requests[-2])
        self.assertEqual((p.wmax, p.bad, p.retries), (12, 1, 2))

    def test_only_bad_after_lost_reply_still_stops(self):
        p, model = pipe(adaptive=True)
        grow(p)
        payload = bytes(range(27))
        before = len(model.accepted)
        model.read_faults.append("drop")
        model.write_faults.extend([None, "bad", "bad", "bad"])
        with self.assertRaisesRegex(N.LinkError, "outcome unknown"):
            p.xchg(payload)
        self.assertEqual(bytes(model.accepted[before:]), payload)
        self.assertTrue(p.failed)
        self.assertEqual(p.bad, 3)

    def test_unresolved_compatibility_failure_stops_until_explicit_reset(self):
        p, model = pipe(adaptive=True)
        grow(p)
        model.limit = 12
        peer = N.Peer(p, 0.002)
        peer.out = bytearray(range(27))
        before = bytes(model.accepted)
        with self.assertRaisesRegex(N.LinkError, "outcome unknown"):
            peer.step()
        self.assertEqual(bytes(model.accepted), before)
        self.assertEqual(peer.out, bytearray(range(27)))
        seq = p.seq
        with self.assertRaisesRegex(N.LinkError, "explicit reset"):
            peer.step()
        self.assertEqual(p.seq, seq)
        p.reset(N.CTL_ECHO)
        self.assertEqual((p.wmax, p.locked), (12, True))
        peer.step()
        self.assertEqual(len(peer.out), 15)

    def test_all_replies_lost_after_acceptance_does_not_duplicate_or_ack_twice(self):
        for transport in ("dbg", "ddcci"):
            with self.subTest(transport=transport):
                p, model = pipe(transport)
                model.tx += b"abcdef"
                p.ack = 2
                model.read_faults.extend(["drop"] * (N.XCHG_TRIES * 4))
                with self.assertRaises(N.LinkError):
                    p.xchg(b"once")
                self.assertEqual(model.accepted, b"once")
                self.assertEqual(p.ack, 2)
                self.assertTrue(bytes(model.tx).startswith(b"cdef"))
                self.assertEqual(len(set(model.requests)), 1)
                n = len(model.requests)
                with self.assertRaises(N.LinkError):
                    p.xchg(b"once")
                self.assertEqual(len(model.requests), n)

    def test_sequence_wrap_dedup_and_stream_roundtrip(self):
        for transport, adaptive in (("dbg", False), ("dbg", True), ("ddcci", False)):
            with self.subTest(transport=transport, adaptive=adaptive):
                p, model = pipe(transport, adaptive)
                p.seq = 254
                peer = N.Peer(p, 0.002)
                frames = [bytes(range(256)) + b"\xc0\xdb" * 22] * 18
                for frame in frames:
                    peer.send(frame)
                for i in range(2000):
                    if i % 31 == 7:
                        model.read_faults.append("corrupt")
                    peer.step()
                    if not peer.out and len(peer.frames) == len(frames):
                        break
                self.assertEqual(peer.frames, frames)
                self.assertEqual(model.accepted, b"".join(N.slip_enc(f) for f in frames))
                self.assertGreater(p.n, 255)


class TransportTests(unittest.TestCase):
    def test_daemon_unknown_outcome_exits_and_cleans_up(self):
        model = ModelIo()

        def tap(_):
            model.read_faults.extend(["drop"] * N.XCHG_TRIES)
            return 99

        a = options(sim=Path("unused.bin"), sim_mode="", units="3", bridge=False, route=True,
                    keep=False, cfg_s=5.0, limit_s=1)
        with patch.object(N, "sim_io", return_value=model), patch.object(N, "sh") as sh, \
                patch.object(N, "tap_open", side_effect=tap), patch.object(N.select, "select", return_value=([], [], [])), \
                patch("builtins.open", mock_open(read_data="02:41:57:00:fe:01")), \
                patch.object(N.os, "close") as close, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(N.LinkError, "unit 3.*outcome unknown"):
                N.daemon(a)
        close.assert_called_once_with(99)
        sh.assert_any_call("ip", "link", "del", "ddc3")
        self.assertTrue(model.closed)

    def test_limits_reject_invalid_sizes_and_mode_combinations(self):
        for transport, cap in (("dbg", 27), ("ddcci", 10)):
            for n in (0, -1, cap + 1):
                with self.subTest(transport=transport, n=n), self.assertRaises(ValueError):
                    N.make_link(ModelIo(), transport, n)
            link = N.make_link(ModelIo(), transport, cap)
            with self.assertRaises(ValueError):
                link.xchg(1, 0, 0, bytes(cap + 1))
        for transport, wmax in (("dbg", 27), ("ddcci", None)):
            with self.assertRaises(ValueError):
                N.make_link(ModelIo(), transport, wmax, adaptive=True)

    def test_ddcci_null_wait_preserves_request(self):
        p, model = pipe("ddcci")
        model.read_faults.extend(["null", "null"])
        self.assertTrue(p.xchg(b"hello")[0])
        self.assertEqual((len(model.requests), p.retries), (1, 0))
        self.assertEqual(model.accepted, b"hello")
        self.assertEqual(p.link.wire_bytes, model.wire_bytes)

    def test_reset_reply_does_not_count_cached_acceptance(self):
        p, _ = pipe()
        p.ack = 9
        with patch.object(p.link, "xchg", return_value=(N.F_UP | N.F_RESET | N.F_ACC, 128, b"")):
            self.assertFalse(p.xchg(b"x")[0])
        self.assertEqual(p.ack, 9)

    def test_cli_rejects_unsafe_options_before_opening_hardware(self):
        for args in (("--adaptive", "--transport", "ddcci"), ("--adaptive", "--wmax", "27"),
                     ("--wmax", "0"), ("--wmax", "28")):
            with self.subTest(args=args), patch.object(sys, "argv", ["ddcnet.py", "loopback", *args]), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
                N.main()
            self.assertEqual(e.exception.code, 2)


class FramingAndHarnessTests(unittest.TestCase):
    def test_every_slip_escape_boundary(self):
        frame = bytes(range(256))
        encoded = N.slip_enc(frame)
        for split in range(len(encoded) + 1):
            d = N.SlipDec()
            self.assertEqual(d.feed(encoded[:split]) + d.feed(encoded[split:]), [frame])

    def test_corrupted_and_oversized_frames_drop_and_resync(self):
        for bad in (b"a\xdbXb", b"a\xdb\xdb", b"a\xdb", b"x" * 301,
                    b"\xdb\xdc" * 301):
            with self.subTest(bad=bad[:8]):
                d = N.SlipDec()
                self.assertEqual(d.feed(bad + bytes([N.END]) + N.slip_enc(b"good")), [b"good"])
                self.assertLessEqual(len(d.buf), N.FRAME_MAX)

    def test_loopback_harness_exact_bytes_and_requested_overhead(self):
        for transport, wmax, adaptive in (("dbg", None, False), ("dbg", 27, False),
                                           ("dbg", None, True), ("ddcci", None, False)):
            with self.subTest(transport=transport, wmax=wmax, adaptive=adaptive):
                model = ModelIo()
                lines = io.StringIO()
                with redirect_stdout(lines):
                    self.assertEqual(N.loopback(options(transport=transport, wmax=wmax, adaptive=adaptive,
                                                        bytes=6000), model), 0)
                self.assertIn("6000/6000 B", lines.getvalue())
                self.assertIn("requested I2C B", lines.getvalue())
                self.assertGreater(len(set(model.accepted[:6000])), 200)  # harness must not repeat one RNG byte

    def test_loopback_drop_injection_recovers(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(N.loopback(options(bytes=600, adaptive=True, drop=0.2), ModelIo()), 0)


if __name__ == "__main__":
    unittest.main()
