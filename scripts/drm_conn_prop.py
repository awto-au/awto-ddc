#!/usr/bin/env python3
"""Read-only: DRM connector properties (Broadcast RGB, max bpc, ...) of one connector, through libdrm (no master needed).

usage: drm_conn_prop.py CARD CONNECTOR [set "NAME" VALUE]  (set needs DRM master or the call fails: logged)     e.g. drm_conn_prop.py /dev/dri/card1 HDMI-A-2
Log: ./tmp/logs/drm_conn_prop.log
"""
import ctypes as C
import os
import sys

from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/drm_conn_prop.log"


class Res(C.Structure):
    _fields_ = [("count_fbs", C.c_int), ("fbs", C.POINTER(C.c_uint32)), ("count_crtcs", C.c_int), ("crtcs", C.POINTER(C.c_uint32)),
                ("count_connectors", C.c_int), ("connectors", C.POINTER(C.c_uint32)), ("count_encoders", C.c_int), ("encoders", C.POINTER(C.c_uint32)),
                ("min_w", C.c_uint32), ("max_w", C.c_uint32), ("min_h", C.c_uint32), ("max_h", C.c_uint32)]


class Conn(C.Structure):
    _fields_ = [("connector_id", C.c_uint32), ("encoder_id", C.c_uint32), ("connector_type", C.c_uint32), ("connector_type_id", C.c_uint32),
                ("connection", C.c_int), ("mm_w", C.c_uint32), ("mm_h", C.c_uint32), ("subpixel", C.c_int), ("count_modes", C.c_int),
                ("modes", C.c_void_p), ("count_props", C.c_int), ("props", C.POINTER(C.c_uint32)), ("prop_values", C.POINTER(C.c_uint64)),
                ("count_encoders", C.c_int), ("encoders", C.POINTER(C.c_uint32))]


class Prop(C.Structure):
    _fields_ = [("prop_id", C.c_uint32), ("flags", C.c_uint32), ("name", C.c_char * 32), ("count_values", C.c_int), ("values", C.POINTER(C.c_uint64)),
                ("count_enums", C.c_int), ("enums", C.c_void_p), ("count_blobs", C.c_int), ("blob_ids", C.POINTER(C.c_uint32))]


class Enum(C.Structure):
    _fields_ = [("value", C.c_uint64), ("name", C.c_char * 32)]


TYPES = {11: "HDMI-A", 10: "DP", 12: "HDMI-B"}


def main() -> int:
    d = C.CDLL("libdrm.so.2")
    d.drmModeGetResources.restype = C.POINTER(Res)
    d.drmModeGetConnector.restype = C.POINTER(Conn)
    d.drmModeGetProperty.restype = C.POINTER(Prop)
    fd = os.open(sys.argv[1], os.O_RDWR)
    res = d.drmModeGetResources(fd).contents
    for i in range(res.count_connectors):
        c = d.drmModeGetConnector(fd, res.connectors[i]).contents
        name = f"{TYPES.get(c.connector_type, c.connector_type)}-{c.connector_type_id}"
        if name != sys.argv[2]:
            continue
        for k in range(c.count_props):
            p = d.drmModeGetProperty(fd, c.props[k]).contents
            val = c.prop_values[k]
            nm = p.name.decode()
            if len(sys.argv) == 6 and sys.argv[3] == "set" and nm == sys.argv[4]:
                rc = d.drmModeObjectSetProperty(fd, c.connector_id, 0xC0C0C0C0, p.prop_id, C.c_uint64(int(sys.argv[5])))
                _log_line(f"{sys.argv[2]} set {nm} {val} -> {sys.argv[5]}: rc {rc}", LOG)
            if nm in ("Broadcast RGB", "max bpc", "Colorspace", "output format", "Output format", "content type", "audio", "force audio", "dithering", "Broadcast RGB range"):
                en = ""
                if p.count_enums:
                    arr = C.cast(p.enums, C.POINTER(Enum))
                    en = " = " + next((arr[j].name.decode() for j in range(p.count_enums) if arr[j].value == val), "?")
                _log_line(f"{sys.argv[2]} {nm}: {val}{en}", LOG)
        return 0
    _log_line(f"{sys.argv[2]}: connector not found on {sys.argv[1]}", LOG)
    return 1


if __name__ == "__main__":
    sys.exit(main())
