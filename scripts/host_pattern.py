#!/usr/bin/env python3
"""Host-side known pattern: borderless fullscreen GTK4 window on ONE connector, no layout change (awto-ddc#255).

usage: /usr/bin/python3 scripts/host_pattern.py --connector HDMI-3 --fifo tmp/scratch/pat.fifo [--initial "solid 255 0 0"]
Commands (one per line, written to the FIFO): code (R=y&255 G=y>>8 B=(x//16)&255) | solid R G B | box X Y W H R G B (on black) | hgrad (R ramp left->right, G ramp top->bottom,
B = 0x80) | quit. Coordinates are logical = physical pixels (scale 1.0 on this desk). Cairo antialiasing off.
Needs the system python (gi); the repo venv has no gi. Log: ./tmp/logs/host_pattern.log
"""
import argparse
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp/logs/host_pattern.log"
state = {"cmd": ["solid", "0", "0", "0"]}


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(s + "\n")


def draw(area, cr, w, h):
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    c = state["cmd"]
    op = c[0]
    if op == "solid":
        r, g, b = (int(x) / 255 for x in c[1:4])
        cr.set_source_rgb(r, g, b)
        cr.paint()
    elif op == "box":
        x, y, bw, bh, r, g, b = (int(x) for x in c[1:8])
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        cr.set_source_rgb(r / 255, g / 255, b / 255)
        cr.rectangle(x, y, bw, bh)
        cr.fill()
    elif op == "code":
        # R = y & 255, G = y >> 8, B = (x // 16) & 255: row and column position readable from one pixel
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        buf = surf.get_data()
        stride = surf.get_stride()
        row = bytearray(stride)
        row[0::4] = bytes((x // 16) & 255 for x in range(stride // 4))
        for y in range(h):
            row[1::4] = bytes([y >> 8]) * (stride // 4)
            row[2::4] = bytes([y & 255]) * (stride // 4)
            buf[y * stride:(y + 1) * stride] = bytes(row)
        surf.mark_dirty()
        cr.set_source_surface(surf, 0, 0)
        cr.paint()
    elif op == "xbits":
        # pixel colour = 3 bits of (x >> SH) as 0 / 255 per channel (R bit0, G bit1, B bit2): no dither, period 8 << SH px
        sh = int(c[1])
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        buf = surf.get_data()
        stride = surf.get_stride()
        row = bytearray(stride)
        for x in range(w):
            v = (x >> sh) & 7
            row[4 * x] = 255 * ((v >> 2) & 1)
            row[4 * x + 1] = 255 * ((v >> 1) & 1)
            row[4 * x + 2] = 255 * (v & 1)
        rb = bytes(row)
        for y in range(h):
            buf[y * stride:(y + 1) * stride] = rb
        surf.mark_dirty()
        cr.set_source_surface(surf, 0, 0)
        cr.paint()
    elif op == "debruijn":
        # symbol of pixel (x, y) = DB[(x + 7 y) % 64], DB = de Bruijn B(8, 2): any two neighbouring pixels name their position mod 64
        a, seq = [0] * 16, []

        def db(t, p):
            if t > 2:
                if 2 % p == 0:
                    seq.extend(a[1:p + 1])
            else:
                a[t] = a[t - p]
                db(t + 1, p)
                for j in range(a[t - p] + 1, 8):
                    a[t] = j
                    db(t + 1, t)
        db(1, 1)
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        buf = surf.get_data()
        stride = surf.get_stride()
        rows = []
        for sh in range(64):                                    # row variants: the symbol phase (7 y) % 64
            row = bytearray(stride)
            for x in range(w):
                v = seq[(x + sh) % 64]
                row[4 * x] = 255 * ((v >> 2) & 1)
                row[4 * x + 1] = 255 * ((v >> 1) & 1)
                row[4 * x + 2] = 255 * (v & 1)
            rows.append(bytes(row))
        for y in range(h):
            buf[y * stride:(y + 1) * stride] = rows[(7 * y) % 64]
        surf.mark_dirty()
        cr.set_source_surface(surf, 0, 0)
        cr.paint()
    elif op == "hgrad":
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        buf = surf.get_data()
        stride = surf.get_stride()
        row = bytearray(stride)
        for y in range(h):
            for x in range(w):
                # BGRX byte order (little endian RGB24)
                row[4 * x] = 0x80
                row[4 * x + 1] = y * 255 // (h - 1)
                row[4 * x + 2] = x * 255 // (w - 1)
            buf[y * stride:(y + 1) * stride] = bytes(row)
        surf.mark_dirty()
        cr.set_source_surface(surf, 0, 0)
        cr.paint()


def on_fifo(fd, cond, area, app):
    data = os.read(fd, 4096).decode()
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        log(f"cmd {line}")
        if line == "quit":
            app.quit()
            return False
        state["cmd"] = line.split()
        area.queue_draw()
        win = app.get_active_window()
        surf = win.get_surface() if win else None
        mon = Gdk.Display.get_default().get_monitor_at_surface(surf) if surf else None
        log(f"state fullscreen={win.is_fullscreen() if win else None} monitor={mon.get_connector() if mon else None} "
            f"size={win.get_width()}x{win.get_height() if win else 0}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--connector", required=True)
    ap.add_argument("--fifo", required=True)
    ap.add_argument("--initial", default="solid 0 0 0")
    a = ap.parse_args()
    state["cmd"] = a.initial.split()
    fifo = Path(a.fifo)
    fifo.parent.mkdir(parents=True, exist_ok=True)
    if not fifo.exists():
        os.mkfifo(fifo)
    fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    app = Gtk.Application(application_id="au.awto.hostpattern")

    def activate(app):
        win = Gtk.ApplicationWindow(application=app)
        win.set_decorated(False)
        area = Gtk.DrawingArea()
        area.set_draw_func(draw)
        win.set_child(area)
        mons = Gdk.Display.get_default().get_monitors()
        target = None
        for i in range(mons.get_n_items()):
            m = mons.get_item(i)
            log(f"monitor {m.get_connector()} {m.get_geometry().width}x{m.get_geometry().height} scale {m.get_scale_factor()}")
            if m.get_connector() == a.connector:
                target = m
        if target is None:
            log("connector not found")
            sys.exit(2)
        win.fullscreen_on_monitor(target)
        win.present()
        GLib.unix_fd_add_full(0, fd, GLib.IOCondition.IN, on_fifo, area, app)

    app.connect("activate", activate)
    app.run([])


if __name__ == "__main__":
    main()
