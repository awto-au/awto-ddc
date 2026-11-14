#!/usr/bin/env python3
"""Faster NVIDIA DP-AUX paths to the ISP page FIFO (0x4A reg 0x70)? Nothing is programmed (#71, extends isp_write_probe.py).

usage: aux_probe.py <bus> --serial S [--rm] [--isp] [--sizes 16,64,128,255]
  default : READ ONLY. EDID read over /dev/i2c-<bus> (1 transfer of write+read) timed.
  --rm    : root. Raw native-AUX path through /dev/nvidiactl: NV0073_CTRL_CMD_DP_AUXCH_CTRL (16 B per call, MOT).
            Own RM client (root, device, subdevice, NV04_DISPLAY_COMMON); display picked by the adapter's DDC port
            (NV0073 GET_I2C_PORTID, ddcPortId-1 == "NVIDIA i2c adapter N"). Read-only steps: DPCD 0x000 read, EDID over
            I2C-over-AUX (16 B reads, MOT), compared byte for byte with the /dev/i2c EDID.
  --isp   : enter ISP (MCU halted, ISP exit = scaler reset at the end), then fill the 0x70 page FIFO (no program kick)
            by each path and time it: 1-byte messages (baseline), ONE message of reg+N bytes (--sizes, N <= 255:
            RM cap 256 per message), the 3-message i915 burst, and with --rm raw AUX in 16 B MOT chunks.
Per-message cost is the unknown being measured: #71 measured 21.3 ms per I2C message on the kernel adapter.
Source refs: osapi.c rm_i2c_transfer / RmDpAuxI2CTransfer, dp_evoadapter.cpp EvoAuxBus::transaction (#71 comment).
Log: ./tmp/logs/aux_probe.log   (unit log: ./tmp/logs/unit-<serial>.log for ISP enter/exit)
"""
import argparse
import ctypes
import fcntl
import os
import re
import struct
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import rtd_isp_probe as P
import rtd_proto
from rtd_flash_sector import Rtd

ISP = 0x4A
EDID_ADDR = 0x50

# ---- RM ioctl ABI (open-gpu-kernel-modules, same tag as the installed 615.78.08) -------------------------------
NV_IOCTL_MAGIC = ord("F")                                   # kernel-open/common/inc/nv-ioctl-numbers.h
ESC_CARD_INFO, ESC_CHECK_VERSION, ESC_ATTACH_GPUS = 200, 210, 212
ESC_RM_FREE, ESC_RM_CONTROL, ESC_RM_ALLOC = 0x29, 0x2A, 0x2B   # nv_escape.h
NV01_ROOT_CLIENT, NV01_DEVICE_0, NV20_SUBDEVICE_0, NV04_DISPLAY_COMMON = 0x41, 0x80, 0x2080, 0x73
CMD_SYSTEM_GET_SUPPORTED, CMD_SYSTEM_GET_CONNECT_STATE = 0x730107, 0x730108
CMD_SPECIFIC_GET_I2C_PORTID, CMD_DP_AUXCH_CTRL = 0x730211, 0x731341
AUX_TYPE_I2C, AUX_TYPE_NATIVE = 0, 1 << 3
AUX_MOT = 1 << 2
AUX_WRITE, AUX_READ = 0, 1
REPLY_ACK = 0
AUX_CHUNK = 16                                              # NV0073_CTRL_DP_AUXCH_MAX_DATA_SIZE


def ioc(nr, size):
    return (3 << 30) | (size << 16) | (NV_IOCTL_MAGIC << 8) | nr      # _IOWR


class CardInfo(ctypes.Structure):                           # nv_ioctl_card_info_t
    _fields_ = [("valid", ctypes.c_uint8), ("domain", ctypes.c_uint32), ("bus", ctypes.c_uint8),
                ("slot", ctypes.c_uint8), ("function", ctypes.c_uint8), ("vendor", ctypes.c_uint16),
                ("device", ctypes.c_uint16), ("gpu_id", ctypes.c_uint32), ("irq", ctypes.c_uint16),
                ("reg_address", ctypes.c_uint64), ("reg_size", ctypes.c_uint64), ("fb_address", ctypes.c_uint64),
                ("fb_size", ctypes.c_uint64), ("minor", ctypes.c_uint32), ("dev_name", ctypes.c_uint8 * 10)]


class VersionStr(ctypes.Structure):
    _fields_ = [("cmd", ctypes.c_uint32), ("reply", ctypes.c_uint32), ("version", ctypes.c_char * 64)]


class Os64(ctypes.Structure):                               # NVOS64_PARAMETERS (alloc)
    _fields_ = [("hRoot", ctypes.c_uint32), ("hParent", ctypes.c_uint32), ("hNew", ctypes.c_uint32),
                ("hClass", ctypes.c_uint32), ("pParams", ctypes.c_uint64), ("pRights", ctypes.c_uint64),
                ("size", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("status", ctypes.c_uint32)]


class Os54(ctypes.Structure):                               # NVOS54_PARAMETERS (control)
    _fields_ = [("hClient", ctypes.c_uint32), ("hObject", ctypes.c_uint32), ("cmd", ctypes.c_uint32),
                ("flags", ctypes.c_uint32), ("params", ctypes.c_uint64), ("size", ctypes.c_uint32),
                ("status", ctypes.c_uint32)]


class Os00(ctypes.Structure):                               # NVOS00_PARAMETERS (free)
    _fields_ = [("hRoot", ctypes.c_uint32), ("hParent", ctypes.c_uint32), ("hOld", ctypes.c_uint32),
                ("status", ctypes.c_uint32)]


class Dev0080(ctypes.Structure):                            # NV0080_ALLOC_PARAMETERS
    _fields_ = [("deviceId", ctypes.c_uint32), ("hClientShare", ctypes.c_uint32), ("hTargetClient", ctypes.c_uint32),
                ("hTargetDevice", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("vaSpaceSize", ctypes.c_uint64),
                ("vaStartInternal", ctypes.c_uint64), ("vaLimitInternal", ctypes.c_uint64),
                ("vaMode", ctypes.c_uint32)]


class Sub2080(ctypes.Structure):
    _fields_ = [("subDeviceId", ctypes.c_uint32)]


class GetSupported(ctypes.Structure):
    _fields_ = [("sub", ctypes.c_uint32), ("displayMask", ctypes.c_uint32), ("displayMaskDDC", ctypes.c_uint32)]


class ConnectState(ctypes.Structure):
    _fields_ = [("sub", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("displayMask", ctypes.c_uint32),
                ("retryTimeMs", ctypes.c_uint32)]


class PortId(ctypes.Structure):
    _fields_ = [("sub", ctypes.c_uint32), ("displayId", ctypes.c_uint32), ("commPortId", ctypes.c_uint32),
                ("ddcPortId", ctypes.c_uint32)]


class AuxCh(ctypes.Structure):                              # NV0073_CTRL_DP_AUXCH_CTRL_PARAMS
    _fields_ = [("sub", ctypes.c_uint32), ("displayId", ctypes.c_uint32), ("bAddrOnly", ctypes.c_uint8),
                ("cmd", ctypes.c_uint32), ("addr", ctypes.c_uint32), ("data", ctypes.c_uint8 * AUX_CHUNK),
                ("size", ctypes.c_uint32), ("replyType", ctypes.c_uint32), ("retryTimeMs", ctypes.c_uint32)]


class Rm:
    """Minimal RM client on /dev/nvidiactl. Needs root: AUXCH_CTRL is a PRIVILEGED control (flags 0x844)."""

    def __init__(self, pci_bus, pci_slot, pci_func, device_id=None):
        self.fd = os.open("/dev/nvidiactl", os.O_RDWR)
        ver = Path("/sys/module/nvidia/version").read_text().strip()
        v = VersionStr(0, 0, ver.encode())                  # NV_RM_API_VERSION_CMD_STRICT = 0
        self._ioctl(ESC_CHECK_VERSION, v)
        cards = (CardInfo * 32)()
        self._ioctl(ESC_CARD_INFO, cards)
        card = next((c for c in cards if c.valid and (c.bus, c.slot, c.function) == (pci_bus, pci_slot, pci_func)), None)
        if card is None:
            raise SystemExit(f"no GPU at {pci_bus:x}:{pci_slot:02x}.{pci_func} in NV_ESC_CARD_INFO")
        P.log(f"RM: GPU {pci_bus:x}:{pci_slot:02x}.{pci_func} gpu_id 0x{card.gpu_id:x} minor {card.minor}")
        self._ioctl(ESC_ATTACH_GPUS, ctypes.c_uint32(card.gpu_id))
        self.client = self._alloc(0, 0, 0, NV01_ROOT_CLIENT, None)
        dev = Dev0080(card.minor if device_id is None else device_id)
        self.dev = self._alloc(self.client, self.client, 0, NV01_DEVICE_0, dev)
        self.sub = self._alloc(self.client, self.dev, 0, NV20_SUBDEVICE_0, Sub2080(0))
        self.disp = self._alloc(self.client, self.dev, 0, NV04_DISPLAY_COMMON, None)

    def _ioctl(self, nr, arg):
        fcntl.ioctl(self.fd, ioc(nr, ctypes.sizeof(arg)), arg)

    def _alloc(self, root, parent, new, cls, params):
        p = Os64(root, parent, new, cls, ctypes.addressof(params) if params is not None else 0, 0,
                 ctypes.sizeof(params) if params is not None else 0, 0, 0)
        self._ioctl(ESC_RM_ALLOC, p)
        if p.status:
            raise OSError(f"RM alloc class 0x{cls:x}: status 0x{p.status:x}")
        return p.hNew

    def control(self, obj, cmd, params):
        c = Os54(self.client, obj, cmd, 0, ctypes.addressof(params), ctypes.sizeof(params), 0)
        self._ioctl(ESC_RM_CONTROL, c)
        if c.status:
            raise OSError(f"RM control 0x{cmd:x}: status 0x{c.status:x}")

    def close(self):
        try:
            self._ioctl(ESC_RM_FREE, Os00(self.client, 0, self.client, 0))
        finally:
            os.close(self.fd)

    # ---- display selection ----
    def display_for_ddc_port(self, port):
        """displayId whose I2C-over-AUX DDC port is `port` (adapter 'NVIDIA i2c adapter <port>'): ddcPortId == port + 1."""
        sup = GetSupported(0)
        self.control(self.disp, CMD_SYSTEM_GET_SUPPORTED, sup)
        for bit in range(32):
            did = 1 << bit
            if not sup.displayMask & did:
                continue
            pid = PortId(0, did)
            try:
                self.control(self.disp, CMD_SPECIFIC_GET_I2C_PORTID, pid)
            except OSError:
                continue
            P.log(f"RM: displayId 0x{did:x} ddcPortId {pid.ddcPortId}")
            if pid.ddcPortId == port + 1:
                return did
        raise SystemExit(f"no displayId with ddcPortId {port + 1}")

    def connected(self, did):
        cs = ConnectState(0, 0, did)
        self.control(self.disp, CMD_SYSTEM_GET_CONNECT_STATE, cs)
        return bool(cs.displayMask & did)

    # ---- raw AUX: one call = one AUX request, 1..16 B ----
    def aux(self, did, kind, mot, rw, addr, data=b"", n=0):
        """Returns (read bytes or b"", bytes completed). Raises OSError on a non-ACK reply."""
        p = AuxCh(0, did, 0, kind | (AUX_MOT if mot else 0) | rw, addr)
        n = len(data) if rw == AUX_WRITE else n
        assert 1 <= n <= AUX_CHUNK
        p.size = n - 1                                      # size is 0-based on input
        for i, b in enumerate(data):
            p.data[i] = b
        self.control(self.disp, CMD_DP_AUXCH_CTRL, p)
        if p.replyType != REPLY_ACK:
            raise OSError(f"AUX reply type {p.replyType} (0 ACK 1 NACK 2 DEFER 3 TIMEOUT 4 I2CNACK 8 I2CDEFER), size {p.size}")
        return bytes(p.data[:min(p.size, n)]) if rw == AUX_READ else b"", p.size

    def i2c_write(self, did, addr, data):
        """One I2C write transaction (STOP at the end) as ceil(len/16) AUX requests, MOT set on all but the last."""
        done = 0
        for i in range(0, len(data), AUX_CHUNK):
            chunk = data[i:i + AUX_CHUNK]
            _, got = self.aux(did, AUX_TYPE_I2C, i + AUX_CHUNK < len(data), AUX_WRITE, addr, chunk)
            done += got
            if got != len(chunk):
                raise OSError(f"I2C-over-AUX write took {got} of {len(chunk)} B at +{i}")
        return done

    def i2c_read(self, did, addr, n):
        out = b""
        while len(out) < n:
            k = min(AUX_CHUNK, n - len(out))
            got, _ = self.aux(did, AUX_TYPE_I2C, len(out) + k < n, AUX_READ, addr, n=k)
            if not got:
                raise OSError(f"I2C-over-AUX read returned 0 B at +{len(out)}")
            out += got
        return out


def ms(t0):
    return (time.monotonic() - t0) * 1000


def adapter_port_and_pci(bus):
    m = re.match(r"NVIDIA i2c adapter (\d+) at ([0-9a-f]+):([0-9a-f]+)\.(\d)", i2cbus.adapter_name(bus))
    if not m:
        raise SystemExit(f"bus {bus}: not an NVIDIA i2c adapter: {i2cbus.adapter_name(bus)!r}")
    return int(m[1]), int(m[2], 16), int(m[3], 16), int(m[4])


def timed(label, fn, n=1):
    t0 = time.monotonic()
    try:
        for _ in range(n):
            fn()
    except OSError as e:
        P.log(f"{label}: FAIL {e!r} after {ms(t0):.1f} ms")
        return False
    P.log(f"{label}: ok, {ms(t0):.1f} ms total, {ms(t0) / n:.1f} ms each")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--rm", action="store_true", help="raw AUX via /dev/nvidiactl (root)")
    ap.add_argument("--isp", action="store_true", help="enter ISP and fill the 0x70 FIFO (no program kick); resets the scaler")
    ap.add_argument("--sizes", default="16,64,128,255")
    a = ap.parse_args()
    root = P.repo_root()
    P.LOG = rtd_proto.setup_logs("aux_probe").main
    ulog = (root / f"tmp/logs/unit-{a.serial}.log").open("a")

    def unit(s):
        ulog.write(f"{isostamp.now()} [aux_probe] {s}\n"); ulog.flush(); P.log(s)

    i2cbus.require_unit(a.bus, a.serial)
    port, pb, ps, pf = adapter_port_and_pci(a.bus)
    P.log(f"bus {a.bus}: {i2cbus.adapter_name(a.bus)!r} kernel {os.uname().release}, nvidia "
          f"{Path('/sys/module/nvidia/version').read_text().strip()}")
    isp = Rtd(a.bus)

    with i2cbus.Bus(a.bus) as b:
        edid = {}
        def rd():
            edid["k"] = b.ops(EDID_ADDR, [b"\x00", 128])[0]
        timed("i2c-dev EDID read (write 0 + read 128, 2 msgs)", rd, 3)

    rm = did = None
    if a.rm:
        rm = Rm(pb, ps, pf)
        try:
            did = rm.display_for_ddc_port(port)
            P.log(f"RM: adapter port {port} -> displayId 0x{did:x}, connected={rm.connected(did)}")
            dpcd = {}
            def dp():
                dpcd["k"] = rm.aux(did, AUX_TYPE_NATIVE, False, AUX_READ, 0x000, n=16)[0]
            if timed("raw native AUX: DPCD 0x000 read 16 B", dp, 5):
                P.log(f"DPCD 0x000..0xF: {dpcd['k'].hex()}")
            got = {}
            def e():
                rm.aux(did, AUX_TYPE_I2C, True, AUX_WRITE, EDID_ADDR, b"\x00")     # offset, MOT: no STOP before the reads
                got["k"] = rm.i2c_read(did, EDID_ADDR, 128)
            if timed("raw AUX EDID: offset write + 8 x 16 B MOT reads (9 calls)", e, 3):
                P.log(f"raw AUX EDID == i2c-dev EDID: {got['k'] == edid['k']}")
        except Exception:
            rm.close(); raise

    if not a.isp:
        if rm:
            rm.close()
        P.log("read-only run done; add --isp for the FIFO-fill timings")
        return 0

    unit(f"ISP enter (MCU halted) bus {a.bus}")
    t_in = time.monotonic()
    isp.write(0x6F, 0x80)
    try:
        isp.set_retries(0)
        timed("FIFO 1-byte messages x 16 (baseline)", lambda: [isp.write(0x70, 0xFF) for _ in range(16)])
        for n in map(int, a.sizes.split(",")):
            timed(f"FIFO ONE message reg+{n} B", lambda n=n: isp.bus.write(ISP, 0x70, b"\xff" * n))
        timed("FIFO 3-message i915 burst, 128 B", lambda: isp.burst_write(0x70, b"\xff" * 128))
        P.log(f"0x6F after fills: 0x{isp.read(0x6F):02x}")
        if rm:
            for n in map(int, a.sizes.split(",")):
                timed(f"FIFO raw AUX I2C write reg+{n} B ({-(-(n + 1) // AUX_CHUNK)} calls)",
                      lambda n=n: rm.i2c_write(did, ISP, bytes([0x70]) + b"\xff" * n))
            P.log(f"0x6F after raw AUX fills: 0x{isp.read(0x6F):02x}")
    finally:
        isp.set_retries(i2cbus.I2C_RETRIES_DEFAULT)
        isp.write(0xEE, 0x02)
        unit(f"ISP exit (reset) after {time.monotonic() - t_in:.1f} s")
        if rm:
            rm.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
