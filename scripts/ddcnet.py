#!/usr/bin/env python3
"""IP over DDC, host side (awto-ddc#80, docs/ip-over-ddc.md): link transports, SLIP, loopback + stack tests, TAP daemon.

usage:
  ddcnet.py loopback  (--sim BIN | --bus N --serial S) [--transport dbg|ddcci] [--bytes 600] [--wmax N]
  ddcnet.py stack     (--sim BIN | --bus N --serial S) [--transport ...]        ARP, ping, UDP echo, service; no TAP
  ddcnet.py daemon    (--sim BIN | --units 3[,1,2]) (--bridge | --route) [--transport ...]   one TAP per monitor (sudo -n ip)
  ddcnet.py svc --ip ADDR info | get ID.. | set ID=V.. | msgs [--follow]         UDP service client (through the TAP)
- Transport B `dbg` (default): debug slave 0x35 cmd 0x3D, ISR-answered, 25 B reply. Transport A `ddcci`: DDC/CI 0x37 op D0/D1.
- --sim BIN: fw_sim (MAP beside BIN); B through fw_sim.SimBus, A through SimDdcci (IIC_1 engine model, FE86..).
- Firmware side: fw/sdcc/awto_net.inc + awto_dbgisr.inc + awto_ddcci.inc (wb-p14net).
Log: ./tmp/logs/ddcnet.log (decoded, one line per step / exchange run), ./tmp/logs/ddcnet.raw.log (bytes)
"""
from __future__ import annotations

import argparse
import fcntl
import os
import random
import select
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_proto  # noqa: E402

ROOT = rtd_proto.repo_root()
F_ACC, F_FULL, F_BAD, F_RESET, F_ECHO, F_MORE, F_UP = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x80
CTL_ECHO, CTL_RESET = 0x01, 0x80
RING = 128                     # RL6449_Project.h AWTO_NET_RING
B_MAX, A_MAX, A_IN = 20, 9, 10  # AWTO_NET_B_MAX / _A_MAX / _A_IN
B_IN = 27                      # 0x3D data limit: SDK g_pucDdcciData 32 B - sub - seq/ctl/ack - chk
B_IN_SAFE = 12                 # default: whole write (sub + 15) fits the 16-byte IIC FIFO (regdb FF25) even if the ISR is late
XCHG_TRIES = 4                 # per exchange: a failed write/read/checksum is retried with the same seq (fw dedups)
END, ESC, ESC_END, ESC_ESC = 0xC0, 0xDB, 0xDC, 0xDD
ETH_CFG = 0x88B5               # local experimental ethertype: host -> monitor config (MAC + IP)
PORT = 5577                    # awto_net.inc AWTO_NET_PORT
NET = "10.235"                 # host-only subnet, not the house LAN (docs/ip-over-ddc.md "Addresses")
LOG = None


def say(s: str) -> None:
    print(s, flush=True)
    if LOG:
        LOG.log(s)


class LinkError(OSError):
    pass


# ---- transports: xchg(seq, ctl, ack, data) -> (flags, rxfree, txdata) | None ----------------------------------------
class DbgLink:
    """Transport B: write 0x3D [seq ctl ack data chk], read 0x08 x25 [seq flags free m data[20] chk]."""
    DEV8, SUB, READ_SUB = 0x6A, 0x3D, 0x08
    name, rmax = "dbg", B_MAX

    def __init__(self, io, wmax: int = B_IN_SAFE):
        self.io, self.wmax = io, min(wmax, B_IN)

    def xchg(self, seq, ctl, ack, data):
        q = bytes([seq, ctl, ack]) + bytes(data)
        if not self.io.write(self.DEV8, self.SUB, q + bytes([(0x3D + sum(q)) & 0xFF])):
            return None
        r = self.io.read(self.DEV8, self.READ_SUB, 25)
        if r is None or len(r) < 25 or (0x3D + sum(r[:24])) & 0xFF != r[24] or r[0] != seq or not r[1] & F_UP or r[3] > B_MAX:
            return None
        return r[1], r[2], bytes(r[4:4 + r[3]])


class DdcciLink:
    """Transport A: DDC/CI 0x37 write 51 len D0 seq ctl ack data chk; read 6E len D1 seq flags free data chk.
    The polled engine answers on the next main-loop pass: read after READ_WAITS (null message / our request = not ready)."""
    name, rmax = "ddcci", A_MAX
    # first try after a 4K60 pass (2.7 ms, #75), then up to the MCCS 40 ms reply wait (kvm.py) twice: ~90 ms worst
    READ_WAITS = (0.003, 0.006, 0.040, 0.040)

    def __init__(self, io, wmax: int = A_IN):
        self.io, self.wmax = io, min(wmax, A_IN)

    def xchg(self, seq, ctl, ack, data):
        body = bytes([0x80 | (4 + len(data)), 0xD0, seq, ctl, ack]) + bytes(data)
        chk = 0x6E ^ 0x51
        for b in body:
            chk ^= b
        if not self.io.ddc_write(body + bytes([chk])):
            return None
        for w in self.READ_WAITS:
            self.io.wait(w)
            r = self.io.ddc_read(16)
            if r is None or len(r) < 3 or r[0] != 0x6E or r[2] != 0xD1:
                continue                         # null message 6E 80 BE, or our request still in the buffer
            n = r[1] & 0x7F
            c = 0x50
            for b in r[:2 + n]:
                c ^= b
            if n < 4 or len(r) < 3 + n or c != r[2 + n] or r[3] != seq or not r[4] & F_UP:
                return None
            return r[4], r[5], bytes(r[6:2 + n])
        return None


class Pipe:
    """Reliable byte pipe over one transport: seq dedup in the firmware, ack = bytes taken from the last applied reply."""

    def __init__(self, link, ctl: int = 0):
        self.link, self.ctl = link, ctl
        self.seq = random.randint(1, 255)
        self.ack = 0
        self.n = self.retries = self.full = 0
        self.free = RING

    def _next(self):
        self.seq = self.seq % 255 + 1            # 1..255: the firmware's boot value 0 never matches
        return self.seq

    def xchg(self, data: bytes = b"", ctl: int | None = None):
        """-> (taken: bool, got: bytes, flags). Raises LinkError after XCHG_TRIES failed tries."""
        seq, c = self._next(), self.ctl if ctl is None else ctl
        for k in range(XCHG_TRIES):
            r = self.link.xchg(seq, c, self.ack, data)
            self.n += 1
            if r is None:
                self.retries += 1
                continue
            flags, self.free, got = r
            if flags & (F_ACC | F_FULL):         # applied: our ack moved the firmware's TX tail, `got` starts after it
                self.ack = len(got)
                self.full += bool(flags & F_FULL)
                return bool(flags & F_ACC), got, flags
            return False, b"", flags             # BAD / RESET: nothing applied, ack kept
        raise LinkError(f"{self.link.name}: exchange seq {seq} failed {XCHG_TRIES}x")

    def reset(self, ctl: int = 0, tries: int = 20) -> None:
        """Empty both firmware rings and its frame state; ctl = mode afterwards (CTL_ECHO = raw loopback)."""
        self.ctl = ctl
        self.xchg(b"", ctl | CTL_RESET)
        self.ack = 0
        for _ in range(tries):                   # AwtoNetPoll applies it on its next main-loop pass
            _, _, f = self.xchg(b"")
            if not f & F_RESET:
                self.ack = 0
                return
            self.link.io.wait(0.002)
        raise LinkError("reset still pending")


# ---- io backends ---------------------------------------------------------------------------------------------------
class RealIo:
    """i2cbus.Bus (the only /dev/i2c opener, #48) for both slaves; writes are this tool's own protocol (0x3D / D0)."""

    def __init__(self, bus: int):
        import i2cbus
        self.b = i2cbus.Bus(bus)

    def write(self, dev8, sub, data):
        try:
            self.b.write(dev8 >> 1, sub, data); return True
        except OSError:
            return False

    def read(self, dev8, sub, n):
        try:
            return self.b.read(dev8 >> 1, sub, n)
        except OSError:
            return None

    def ddc_write(self, data):
        return self.write(0x6E, 0x51, data)

    def ddc_read(self, n):
        try:
            d = self.b.raw_read(0x37, n)
        except OSError:
            return None
        rtd_proto.trace(0x37, "r", 0, d, n)
        return d

    def wait(self, s):
        time.sleep(s)                            # link pacing (the reply wait of the DDC/CI spec), not a poll

    def now(self):
        return time.monotonic()

    def close(self):
        self.b.close()


def sim_io(binp: Path, mode: str):
    """fw_sim.SimBus (0x35) + an IIC_1 engine model for DDC/CI; time = firmware ms (Timer2)."""
    import fw_sim as S

    class SimDdcci(S.Dev):
        """IIC_1 (0xFE86..): host write = SUB_IN + data FIFO + STATUS bit1/2; reply = DATA_OUT after a buffer reset."""
        SUB, DIN, DOUT, STAT, STAT2, IRQ2 = 0xFE88, 0xFE89, 0xFE8A, 0xFE8B, 0xFE8D, 0xFE8E

        def __init__(self):
            self.rx, self.rxpos, self.tx, self.flags = b"", 0, bytearray(), 0
            self.reads, self.writes = (self.DIN,), (self.DOUT, self.STAT, self.IRQ2)

        def init(self, m):
            m.put(f"set memory xram 0x{self.STAT2:x} 0x02")

        def on_read(self, m, a):
            self.rxpos += 1
            if self.rxpos < len(self.rx):
                m.put(f"set memory xram 0x{self.DIN:x} 0x{self.rx[self.rxpos]:x}")
            else:
                m.put(f"set memory xram 0x{self.STAT2:x} 0x{m.rd(self.STAT2)[0] | 0x02:x}")
                self.flags &= ~0x04
                m.put(f"set memory xram 0x{self.STAT:x} 0x{self.flags:x}")

        def on_write(self, m, a):
            v = m.rd(a)[0]
            if a == self.DOUT:
                self.tx.append(v)
            elif a == self.IRQ2 and v & 0x40:
                self.tx.clear()
                m.put(f"set memory xram 0x{self.IRQ2:x} 0x{v & ~0x40 & 0xFF:x}")
            elif a == self.STAT:
                self.flags &= v
                m.put(f"set memory xram 0x{self.STAT:x} 0x{self.flags:x}")

        def request(self, m, pkt: bytes):
            self.tx.clear()
            self.rx, self.rxpos, self.flags = pkt[1:], 0, 0x06 | 0x10
            m.wr(self.SUB, bytes([pkt[0]]))
            m.wr(self.DIN, bytes([self.rx[0]]))
            m.wr(self.STAT2, bytes([m.rd(self.STAT2)[0] & ~0x02 & 0xFF]))
            m.wr(self.STAT, bytes([self.flags]))

    eng = SimDdcci()
    bus = S.SimBus(binp, binp.with_suffix(".map"), devs=[eng], video=mode or None)

    def ddc_write(data):
        eng.request(bus.m, bytes([0x51]) + bytes(data))
        rtd_proto.trace(0x37, "w", 0x51, bytes(data))
        return True

    def ddc_read(n):
        d = bytes(eng.tx) if eng.tx else b"\x6e\x80\xbe"
        rtd_proto.trace(0x37, "r", 0, d, n)
        return d

    def traced(f, kind):
        def g(dev8, sub, x):
            r = f(dev8, sub, x)
            if kind == "w":
                rtd_proto.trace(dev8 >> 1, "w", sub, x, 0, None if r else "NAK")
            else:
                rtd_proto.trace(dev8 >> 1, "r", sub, r, x, None if r is not None else "NAK")
            return r
        return g

    bus.ddc_write, bus.ddc_read = ddc_write, ddc_read
    bus.write, bus.read = traced(bus.write, "w"), traced(bus.read, "r")
    return bus


def open_io(a):
    if a.sim:
        return sim_io(a.sim, a.sim_mode)
    import i2cbus
    i2cbus.require_unit(a.bus, a.serial)
    return RealIo(a.bus)


def make_link(io, transport: str, wmax: int | None, drop: float = 0.0):
    if drop:                                     # fault injection: lose replies after the firmware applied the request
        rnd = random.Random(8080)
        rd, dr = io.read, getattr(io, "ddc_read", None)
        io.read = lambda dev8, sub, n: None if rnd.random() < drop else rd(dev8, sub, n)
        if dr:
            io.ddc_read = lambda n: None if rnd.random() < drop else dr(n)
    return DbgLink(io, wmax or B_IN_SAFE) if transport == "dbg" else DdcciLink(io, wmax or A_IN)


# ---- SLIP + frames -------------------------------------------------------------------------------------------------
def slip_enc(frame: bytes) -> bytes:
    out = bytearray([END])
    for b in frame:
        out += bytes([ESC, ESC_END]) if b == END else bytes([ESC, ESC_ESC]) if b == ESC else bytes([b])
    return bytes(out + bytes([END]))


class SlipDec:
    def __init__(self):
        self.buf, self.esc = bytearray(), False

    def feed(self, data: bytes) -> list[bytes]:
        out = []
        for b in data:
            if b == END:
                if self.buf:
                    out.append(bytes(self.buf))
                self.buf, self.esc = bytearray(), False
            elif b == ESC:
                self.esc = True
            else:
                if self.esc:
                    b = END if b == ESC_END else ESC if b == ESC_ESC else b
                    self.esc = False
                self.buf.append(b)
        return out


def csum(b: bytes) -> int:
    if len(b) % 2:
        b += b"\0"
    s = sum(struct.unpack(f"!{len(b) // 2}H", b))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return ~s & 0xFFFF


def mac_s(m: bytes) -> str:
    return ":".join(f"{x:02x}" for x in m)


def eth(dst: bytes, src: bytes, typ: int, pay: bytes) -> bytes:
    return dst + src + struct.pack("!H", typ) + pay


def cfg_frame(host_mac: bytes, mon_mac: bytes, ip: str) -> bytes:
    return eth(b"\xff" * 6, host_mac, ETH_CFG, b"AW\x01" + mon_mac + socket.inet_aton(ip))


def ipv4(src: str, dst: str, proto: int, pay: bytes, ident: int = 1) -> bytes:
    h = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(pay), ident, 0x4000, 64, proto, 0, socket.inet_aton(src), socket.inet_aton(dst))
    return h[:10] + struct.pack("!H", csum(h)) + h[12:] + pay


def udp(sport: int, dport: int, pay: bytes) -> bytes:
    return struct.pack("!HHHH", sport, dport, 8 + len(pay), 0) + pay


def icmp_echo(ident: int, seq: int, data: bytes) -> bytes:
    h = struct.pack("!BBHHH", 8, 0, 0, ident, seq) + data
    return h[:2] + struct.pack("!H", csum(h)) + h[4:]


class Peer:
    """In-process host end of one link: frames in/out through the Pipe, fw time or wall time per step."""

    def __init__(self, pipe: Pipe, poll_s: float):
        self.p, self.poll_s, self.dec = pipe, poll_s, SlipDec()
        self.out = bytearray()
        self.frames: list[bytes] = []

    def send(self, frame: bytes):
        self.out += slip_enc(frame)

    def step(self) -> int:
        """One exchange: as many queued bytes as the link and the firmware's free space allow."""
        n = min(self.p.link.wmax, self.p.free, len(self.out))
        took, got, _ = self.p.xchg(bytes(self.out[:n]))
        if took:
            del self.out[:n]
        self.frames += self.dec.feed(got)
        return len(got)

    def until(self, pred, limit_s: float):
        """Exchange until pred(frame) matches a received frame; -> (frame, elapsed s, exchanges) or (None, ...)."""
        io = self.p.link.io
        t0, n0 = io.now(), self.p.n
        while io.now() - t0 < limit_s:
            got = self.step()
            for i, f in enumerate(self.frames):
                if pred(f):
                    del self.frames[i]
                    return f, io.now() - t0, self.p.n - n0
            if not got and not self.out:
                io.wait(self.poll_s)
        return None, io.now() - t0, self.p.n - n0


# ---- tests ---------------------------------------------------------------------------------------------------------
def loopback(a, io) -> int:
    link = make_link(io, a.transport, a.wmax, a.drop)
    p = Pipe(link)
    p.reset(CTL_ECHO)
    data = bytes(random.Random(80).randrange(256) for _ in range(a.bytes))
    t0, n0, r0 = io.now(), p.n, p.retries
    sent, back = 0, bytearray()
    lat = []
    limit = a.limit_s
    while len(back) < len(data) and io.now() - t0 < limit:
        n = min(link.wmax, p.free, len(data) - sent)
        took, got, _ = p.xchg(data[sent:sent + n])
        if took:
            sent += n
        back += got
        if not got and sent >= len(data):
            io.wait(a.poll_s)                    # echo pending on the next main-loop pass
    dt = io.now() - t0
    ok = bytes(back) == data
    # latency: one byte out, exchanges until it is back
    t1, n1 = io.now(), p.n
    p.xchg(b"\x5a")
    got = b""
    while not got and io.now() - t1 < 1.0:
        io.wait(a.poll_s)
        _, got, _ = p.xchg(b"")
    lat = (io.now() - t1, p.n - n1)
    p.reset(0)
    unit = "fw ms" if a.sim else "ms"
    say(f"loopback {link.name} ({'sim' if a.sim else f'bus {a.bus}'}): {'PASS' if ok else 'FAIL'} {len(back)}/{len(data)} B echoed "
        f"in {dt * 1000:.0f} {unit}, {p.n - n0} exchanges ({p.retries - r0} retries, {p.full} full), "
        f"{len(data) / dt:.0f} B/s each way (wmax {link.wmax}, rmax {link.rmax}); 1-byte round trip {lat[0] * 1000:.1f} {unit}, "
        f"{lat[1]} exchanges")
    return 0 if ok else 1


def stack(a, io) -> int:
    link = make_link(io, a.transport, a.wmax, a.drop)
    p = Pipe(link)
    p.reset(0)
    peer = Peer(p, a.poll_s)
    host_mac, mon_mac = bytes.fromhex("02415700fe01"), bytes.fromhex("024157000003")
    host_ip, mon_ip = f"{NET}.0.1", f"{NET}.0.13"
    fails = 0
    unit = "fw ms" if a.sim else "ms"

    def check(name, ok, detail=""):
        nonlocal fails
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    lim = a.limit_s
    peer.send(cfg_frame(host_mac, mon_mac, mon_ip))
    f, dt, n = peer.until(lambda f: f[12:14] == struct.pack("!H", ETH_CFG), lim)
    check("config", f is not None and f[16] == 2 and f[17:23] == mon_mac and f[23:27] == socket.inet_aton(mon_ip),
          f"({dt * 1000:.0f} {unit}, {n} exchanges)")
    arp = eth(b"\xff" * 6, host_mac, 0x0806, struct.pack("!HHBBH6s4s6s4s", 1, 0x0800, 6, 4, 1, host_mac, socket.inet_aton(host_ip),
                                                          b"\0" * 6, socket.inet_aton(mon_ip)))
    peer.send(arp)
    f, dt, n = peer.until(lambda f: f[12:14] == b"\x08\x06", lim)
    check("ARP who-has -> is-at", f is not None and f[20:22] == b"\x00\x02" and f[22:28] == mon_mac and f[0:6] == host_mac,
          f"({dt * 1000:.0f} {unit}, {n} exchanges)")
    rtts = []
    for seq in range(1, 4):
        data = bytes(range(56))
        peer.send(eth(mon_mac, host_mac, 0x0800, ipv4(host_ip, mon_ip, 1, icmp_echo(0x80, seq, data), seq)))
        f, dt, n = peer.until(lambda f: f[12:14] == b"\x08\x00" and f[23] == 1, lim)
        ok = (f is not None and f[34] == 0 and f[38:42] == struct.pack("!HH", 0x80, seq) and f[42:] == data
              and csum(f[14:34]) == 0 and csum(f[34:]) == 0 and f[26:30] == socket.inet_aton(mon_ip))
        rtts.append(dt * 1000)
        check(f"ping seq {seq} (56 B)", ok, f"rtt {dt * 1000:.1f} {unit}, {n} exchanges")
    burst = 6                                    # queued at once: fills the RX ring while replies drain (F_FULL path)
    for seq in range(10, 10 + burst):
        peer.send(eth(mon_mac, host_mac, 0x0800, ipv4(host_ip, mon_ip, 1, icmp_echo(0x81, seq, bytes(200)), seq)))
    got, t0, n0 = set(), io.now(), p.n
    while len(got) < burst and io.now() - t0 < lim * 2:
        f, _, _ = peer.until(lambda f: f[12:14] == b"\x08\x00" and f[23] == 1 and f[38:40] == b"\x00\x81", lim)
        if f is None:
            break
        got.add(f[40] << 8 | f[41])
    check(f"ping burst {burst} x 200 B", got == set(range(10, 10 + burst)),
          f"{len(got)} replies in {(io.now() - t0) * 1000:.0f} {unit}, {p.n - n0} exchanges, {p.full} full so far")
    pay = b"awto ddc echo " * 8
    peer.send(eth(mon_mac, host_mac, 0x0800, ipv4(host_ip, mon_ip, 17, udp(40000, 7, pay))))
    f, dt, n = peer.until(lambda f: f[12:14] == b"\x08\x00" and f[23] == 17 and f[34:36] == b"\x00\x07", lim)
    check(f"UDP echo port 7 ({len(pay)} B)", f is not None and f[42:42 + len(pay)] == pay and f[36:38] == struct.pack("!H", 40000),
          f"({dt * 1000:.0f} {unit}, {n} exchanges)")

    def svc(req: bytes):
        peer.send(eth(mon_mac, host_mac, 0x0800, ipv4(host_ip, mon_ip, 17, udp(40001, PORT, req))))
        f, dt, n = peer.until(lambda f: f[12:14] == b"\x08\x00" and f[23] == 17 and f[34:36] == struct.pack("!H", PORT)
                              and f[36:38] == struct.pack("!H", 40001), lim)
        return (f[42:] if f is not None else None), dt, n

    r, dt, n = svc(b"\x01\x11")
    check("service info", r is not None and r[:3] == b"\x81\x11\x00" and r[3] == 1,
          f"{svc_info(r) if r else ''} ({dt * 1000:.0f} {unit})")
    reg = r is not None and r[4] & 1
    r, dt, n = svc(b"\x02\x12\x02\x01\x07")
    want = 0x00 if reg else 0xFE
    check("service get ids 1, 7", r is not None and r[:4] == b"\x82\x12\x00\x02" and r[5] == want and r[9] == want,
          f"{svc_get(r) if r else ''} ({'registry' if reg else 'no registry: status FE expected'})")
    r, dt, n = svc(b"\x04\x13\x03")
    check("service subscribe + ring on", r is not None and r[:3] == b"\x84\x13\x00", f"seq {r[3] << 8 | r[4] if r else '?'}")
    if a.sim:                                    # 3 messages the way AwtoMsgV logs them (BE image) -> one push to the subscriber
        m = io.m
        ring, head, seq = m.addr("g_pstAwtoMsgRing"), m.addr("g_ucAwtoMsgHead"), m.addr("g_usAwtoMsgSeq")
        h, s = m.rd(head)[0], int.from_bytes(m.rd(seq, 2), "big")
        for k in range(3):
            m.wr(ring + 6 * ((h + k) % 40), struct.pack("!HI", 0x0800 + k, 1000 + k))
        m.wr(head, bytes([(h + 3) % 40]))
        m.wr(seq, struct.pack("!H", s + 3))
        r, dt, n = (lambda f: (f[0][42:] if f[0] is not None else None, f[1], f[2]))(peer.until(
            lambda f: f[12:14] == b"\x08\x00" and f[23] == 17 and f[36:38] == struct.pack("!H", 40001) and f[42] == 5, lim))
        check("message push (3 injected)", r is not None and r[6] == 3 and r[7:13] == struct.pack("!HI", 0x0800, 1000),
              f"{svc_msgs(r[3:]) if r else ''} ({dt * 1000:.0f} {unit})")
    r, dt, n = svc(b"\x06\x14\x00\x00")
    check("service msg read from 0", r is not None and r[:3] == b"\x86\x14\x00", svc_msgs(r[3:]) if r else "")
    r, dt, n = svc(b"\x7f\x15")
    check("service unknown op -> FF", r is not None and r[:3] == b"\xff\x15\xff")
    say(f"stack {link.name} ({'sim' if a.sim else f'bus {a.bus}'}): {'PASS' if not fails else f'{fails} FAIL'}; "
        f"ping rtt {min(rtts):.1f}..{max(rtts):.1f} {unit}; {p.n} exchanges, {p.retries} retries, {p.full} full")
    return 1 if fails else 0


def svc_info(r: bytes) -> str:
    return (f"proto {r[3]}, registry {'yes' if r[4] & 1 else 'no'}, msg ring {r[5]} ({'on' if r[4] & 2 else 'off'}), "
            f"mtu {r[6] << 8 | r[7]}, msg seq {r[8] << 8 | r[9]}")


def svc_get(r: bytes) -> str:
    return " ".join(f"{r[4 + 4 * i]}:{'ok' if r[5 + 4 * i] == 0 else f'st{r[5 + 4 * i]:02X}'}="
                    f"{struct.unpack('!h', r[6 + 4 * i:8 + 4 * i])[0]}" for i in range(r[3]))


def svc_msgs(b: bytes) -> str:
    lost, seq, n = b[0], b[1] << 8 | b[2], b[3]
    return f"lost {lost}, first seq {seq}, {n} entries" + "".join(
        f"; {b[4 + 6 * i] << 8 | b[5 + 6 * i]:04X}={int.from_bytes(b[6 + 6 * i:10 + 6 * i], 'big')}" for i in range(min(n, 4)))


# ---- daemon --------------------------------------------------------------------------------------------------------
TUNSETIFF, IFF_TAP, IFF_NO_PI = 0x400454CA, 0x0002, 0x1000
BRIDGE = "ddcbr0"


def sh(*cmd: str) -> None:
    r = subprocess.run(["sudo", "-n", *cmd], capture_output=True, text=True, timeout=5)
    say(f"  $ {' '.join(cmd)}" + (f"  -> rc {r.returncode}: {r.stderr.strip()}" if r.returncode else ""))


def tap_open(name: str) -> int:
    fd = os.open("/dev/net/tun", os.O_RDWR | os.O_NONBLOCK)
    fcntl.ioctl(fd, TUNSETIFF, struct.pack("16sH", name.encode(), IFF_TAP | IFF_NO_PI))
    return fd


def daemon(a) -> int:
    """One TAP per monitor: frames TAP -> SLIP -> link, link -> SLIP -> TAP. --bridge: all TAPs on ddcbr0 (host 10.235.0.1/24,
    monitor N = 10.235.0.1N). --route: tap N alone (host 10.235.N.1/24, monitor 10.235.N.2), ip_forward between them."""
    units = [u for u in a.units.split(",") if u]
    links = []
    if a.bridge:
        sh("ip", "link", "add", BRIDGE, "type", "bridge")
        sh("sysctl", "-q", "-w", f"net.ipv6.conf.{BRIDGE}.disable_ipv6=1")    # no RS / MLD chatter over a ~5 KB/s link
        sh("ip", "addr", "replace", f"{NET}.0.1/24", "dev", BRIDGE)
        sh("ip", "link", "set", BRIDGE, "up")
    else:
        sh("sysctl", "-q", "-w", "net.ipv4.ip_forward=1")
    for u in units:
        tap = f"ddc{u}"
        sh("ip", "tuntap", "add", "dev", tap, "mode", "tap", "user", str(os.getuid()))
        sh("sysctl", "-q", "-w", f"net.ipv6.conf.{tap}.disable_ipv6=1")
        if a.bridge:
            sh("ip", "link", "set", tap, "master", BRIDGE)
            mon_ip = f"{NET}.0.1{u}"
        else:
            sh("ip", "addr", "replace", f"{NET}.{u}.1/24", "dev", tap)
            mon_ip = f"{NET}.{u}.2"
        sh("ip", "link", "set", tap, "mtu", "286", "up")
        if a.sim:
            io = sim_io(a.sim, a.sim_mode)
        else:
            import i2cbus
            import kvm
            info = kvm.units()[u]
            bus = kvm.find_bus(info) if a.transport == "ddcci" else a.bus
            i2cbus.require_unit(bus, info["serial"])
            io = RealIo(bus)
        p = Pipe(make_link(io, a.transport, a.wmax))
        p.reset(0)
        fd = tap_open(tap)
        mon_mac = bytes.fromhex(f"0241570000{int(u):02x}")
        host_mac = bytes.fromhex(open(f"/sys/class/net/{tap}/address").read().strip().replace(":", ""))
        links.append(dict(u=u, tap=tap, fd=fd, p=p, peer=Peer(p, a.poll_s), mon_ip=mon_ip, mon_mac=mon_mac, host_mac=host_mac,
                          cfg_t=-1e9, frames=0, back=0))
        say(f"unit {u}: {tap} {'on ' + BRIDGE if a.bridge else 'routed'}, monitor {mon_ip} {mac_s(mon_mac)} via {p.link.name}")
    t_end = time.monotonic() + a.limit_s if a.limit_s else None
    try:
        while t_end is None or time.monotonic() < t_end:
            busy = False
            r, _, _ = select.select([L["fd"] for L in links], [], [], 0)
            for L in links:
                pe = L["peer"]
                if time.monotonic() - L["cfg_t"] > a.cfg_s:              # re-config: survives a monitor reboot
                    pe.send(cfg_frame(L["host_mac"], L["mon_mac"], L["mon_ip"]))
                    L["cfg_t"] = time.monotonic()
                if L["fd"] in r:
                    while len(pe.out) < 4 * RING:
                        try:
                            fr = os.read(L["fd"], 2048)
                        except BlockingIOError:
                            break
                        pe.send(fr); L["frames"] += 1
                try:
                    busy |= bool(pe.step()) or bool(pe.out)
                except LinkError as e:
                    say(f"unit {L['u']}: {e}")
                for fr in pe.frames:
                    if fr[12:14] != struct.pack("!H", ETH_CFG):
                        os.write(L["fd"], fr); L["back"] += 1
                pe.frames.clear()
                if not busy:
                    L["p"].link.io.wait(a.poll_s / len(links))
    except KeyboardInterrupt:
        pass
    finally:
        for L in links:
            p = L["p"]
            say(f"unit {L['u']}: {L['frames']} frames to the monitor, {L['back']} back; {p.n} exchanges, {p.retries} retries")
            os.close(L["fd"])
            if not a.keep:
                sh("ip", "link", "del", L["tap"])
        if a.bridge and not a.keep:
            sh("ip", "link", "del", BRIDGE)
    return 0


# ---- UDP service client (through the TAP) --------------------------------------------------------------------------
def svc_client(a) -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(a.limit_s or 5.0)
    tag = random.randint(0, 255)
    op = a.args[0]
    if op == "info":
        req = bytes([1, tag])
    elif op == "get":
        ids = [int(x) for x in a.args[1:]]
        req = bytes([2, tag, len(ids), *ids])
    elif op == "set":
        kv = [x.split("=") for x in a.args[1:]]
        req = bytes([3, tag, len(kv)]) + b"".join(bytes([int(k)]) + struct.pack("!h", int(v)) for k, v in kv)
    elif op == "msgs":
        req = bytes([4, tag, 3 if a.follow else 2])
    else:
        raise SystemExit(f"unknown op {op}")
    s.sendto(req, (a.ip, PORT))
    r, _ = s.recvfrom(512)
    say(f"svc {a.ip} {op}: " + (svc_info(r) if op == "info" else svc_get(r) if op in ("get", "set") else f"seq {r[3] << 8 | r[4]}"))
    if op == "msgs":
        r2 = None
        s.sendto(bytes([6, tag, 0, 0]), (a.ip, PORT))
        r2, _ = s.recvfrom(512)
        say(f"svc {a.ip} msgs: {svc_msgs(r2[3:])}")
        while a.follow:
            r, _ = s.recvfrom(512)
            if r[0] == 5:
                say(f"svc {a.ip} push: {svc_msgs(r[3:])}")
    return 0


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("loopback", "stack", "daemon", "svc"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--sim", type=Path, help="firmware image .bin (map beside it): run against fw_sim")
    ap.add_argument("--sim-mode", default="1080p60", help="fw_sim HDMI input on D2 ('' = bare CPU)")
    ap.add_argument("--bus", type=int)
    ap.add_argument("--serial")
    ap.add_argument("--units", default="3")
    ap.add_argument("--transport", choices=("dbg", "ddcci"), default="dbg")
    ap.add_argument("--wmax", type=int, help=f"bytes per write (dbg: default {B_IN_SAFE}, max {B_IN}; ddcci max {A_IN})")
    ap.add_argument("--bytes", type=int, default=600)
    ap.add_argument("--drop", type=float, default=0.0, help="test: fraction of reply reads lost (firmware dedup + host retry)")
    ap.add_argument("--poll-s", type=float, default=0.002, help="idle gap between exchanges (main-loop pass ~2.7 ms at 4K60)")
    ap.add_argument("--limit-s", type=float, default=0.0, help="test step limit (0 = default: 3 s fw / 10 s real); daemon: run time")
    ap.add_argument("--bridge", action="store_true")
    ap.add_argument("--route", action="store_true")
    ap.add_argument("--keep", action="store_true", help="daemon: leave the TAPs / bridge on exit")
    ap.add_argument("--cfg-s", type=float, default=5.0, help="daemon: config frame period (re-config after a monitor reboot)")
    ap.add_argument("--ip")
    ap.add_argument("--follow", action="store_true")
    a = ap.parse_args()
    LOG = rtd_proto.setup_logs("ddcnet")
    say(f"ddcnet {' '.join(sys.argv[1:])}")
    if a.cmd == "svc":
        return svc_client(a)
    if a.cmd == "daemon":
        if a.bridge == a.route:
            raise SystemExit("daemon: --bridge or --route")
        if not a.sim and a.transport == "dbg" and a.bus is None:
            raise SystemExit("daemon --transport dbg: --bus N (the unit's 0x35 bus); ddcci finds the bus by EDID serial")
        return daemon(a)
    if not a.sim and (a.bus is None or not a.serial):
        raise SystemExit("--sim BIN, or --bus N --serial S")
    a.limit_s = a.limit_s or (3.0 if a.sim else 10.0)
    io = open_io(a)
    try:
        return (loopback if a.cmd == "loopback" else stack)(a, io)
    finally:
        io.close()
        LOG.close()


if __name__ == "__main__":
    sys.exit(main())
