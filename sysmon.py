#!/usr/bin/env python3
"""sys-mon — a tiny, efficient system monitor.

Time-series view of CPU, RAM, GPU, VRAM, network and disk activity.
Each metric gets its own color and label. Built on psutil + pynvml + pyqtgraph,
polling at a fixed interval so resource use stays negligible.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import deque

import psutil
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

APP_ID = "simple-sys-mon"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    import pynvml
except ImportError:  # pragma: no cover - optional dependency
    pynvml = None


# --- colors -----------------------------------------------------------------
# One distinct, high-contrast color per series.
C_CPU = "#00d7ff"
C_RAM = "#ff9500"
C_GPU = "#57d957"
C_VRAM = "#ff5db1"
C_NET_RX = "#4ea1ff"
C_NET_TX = "#ffd23f"
C_DISK_R = "#2dd4bf"
C_DISK_W = "#f97362"


def fmt_bytes(n: float) -> str:
    """Human-readable byte rate, e.g. 1.2 MB/s."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}/s" if unit == "B" else f"{n:.1f} {unit}/s"
        n /= 1024
    return f"{n:.1f} GB/s"


class ByteAxis(pg.AxisItem):
    """Y axis that labels ticks as byte rates instead of raw numbers."""

    def tickStrings(self, values, scale, spacing):
        return [fmt_bytes(max(v, 0)) for v in values]


class GpuReader:
    """Reads util + VRAM from the primary NVIDIA GPU. No-op if unavailable."""

    def __init__(self):
        self.ok = False
        self.handle = None
        self.name = "GPU"
        if pynvml is None:
            return
        try:
            pynvml.nvmlInit()
            if pynvml.nvmlDeviceGetCount() > 0:
                self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                name = pynvml.nvmlDeviceGetName(self.handle)
                self.name = name.decode() if isinstance(name, bytes) else name
                self.ok = True
        except Exception:
            self.ok = False

    def read(self) -> tuple[float, float]:
        """Return (gpu_util_pct, vram_used_pct). (0, 0) if unavailable."""
        if not self.ok:
            return 0.0, 0.0
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(self.handle).gpu
            mem = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
            vram = mem.used / mem.total * 100 if mem.total else 0.0
            return float(util), float(vram)
        except Exception:
            return 0.0, 0.0

    def shutdown(self):
        if self.ok:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass


# Each metric is one independent plot.
# (key, label, color, kind) — kind is "pct" (0-100 axis) or "bytes" (auto-scaled rate).
METRICS = [
    ("cpu", "CPU", C_CPU, "pct"),
    ("ram", "RAM", C_RAM, "pct"),
    ("gpu", "GPU", C_GPU, "pct"),
    ("vram", "VRAM", C_VRAM, "pct"),
    ("rx", "Net Down", C_NET_RX, "bytes"),
    ("tx", "Net Up", C_NET_TX, "bytes"),
    ("dr", "Disk Read", C_DISK_R, "bytes"),
    ("dw", "Disk Write", C_DISK_W, "bytes"),
]
COLS = 2  # grid columns
AXIS_WIDTH = 76  # fixed left-axis width (px) so plots don't jitter on update


class Monitor(QtWidgets.QMainWindow):
    def __init__(self, interval_ms: int, history_s: int):
        super().__init__()
        self.interval_ms = interval_ms
        self.npoints = max(2, history_s * 1000 // interval_ms)
        self.dt = interval_ms / 1000.0
        self.gpu = GpuReader()

        self.setWindowTitle("sys-mon")
        self.resize(900, 820)

        pg.setConfigOptions(antialias=True, background="#0e1116", foreground="#c0c6d0")
        layout = pg.GraphicsLayoutWidget()
        self.setCentralWidget(layout)

        # x axis: seconds in the past (… -2, -1, 0).
        self.x = [(-(self.npoints - 1) + i) * self.dt for i in range(self.npoints)]
        self._buf: dict[str, deque] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._plots: dict[str, pg.PlotItem] = {}
        self._text: dict[str, pg.TextItem] = {}
        self._labels: dict[str, str] = {}
        self._kinds: dict[str, str] = {}

        # one independent plot per metric, arranged in a grid
        for i, (key, label, color, kind) in enumerate(METRICS):
            row, col = divmod(i, COLS)
            axes = {"left": ByteAxis("left")} if kind == "bytes" else None
            plot = layout.addPlot(row=row, col=col, axisItems=axes)
            self._setup_plot(plot, kind)
            self._buf[key] = deque([0.0] * self.npoints, maxlen=self.npoints)
            self._curves[key] = plot.plot(
                self.x, list(self._buf[key]), pen=pg.mkPen(color=color, width=2)
            )
            self._plots[key] = plot
            self._text[key] = self._attach_readout(plot, color)
            self._labels[key] = label
            self._kinds[key] = kind

        # prime counters so the first sample is a real delta
        psutil.cpu_percent(interval=None)
        self._net = psutil.net_io_counters()
        self._disk = psutil.disk_io_counters()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(interval_ms)

    def _setup_plot(self, plot, kind):
        plot.setMenuEnabled(False)
        plot.setMouseEnabled(x=False, y=False)
        plot.hideButtons()
        plot.showGrid(x=True, y=True, alpha=0.15)
        plot.setLabel("bottom", "seconds")
        plot.setXRange(self.x[0], 0, padding=0)
        # Pin the y-axis width so changing tick-label lengths (e.g. "9.5 MB/s"
        # -> "143.1 MB/s") don't resize the axis and make the grid jitter.
        left = plot.getAxis("left")
        left.setStyle(autoExpandTextSpace=False)
        left.setWidth(AXIS_WIDTH)
        if kind == "pct":
            plot.setYRange(0, 100, padding=0)
        else:
            plot.setLimits(yMin=0)
            plot.enableAutoRange(axis="y")

    def _attach_readout(self, plot, color):
        """A label/value readout pinned to the plot's top-left corner.

        It lives inside the ViewBox (not the plot's layout), so its text can
        change length every update without ever resizing the plot or the grid.
        """
        text = pg.TextItem(anchor=(0, 0), color=color,
                           fill=pg.mkBrush(14, 17, 22, 190))
        text.setZValue(10)
        plot.addItem(text, ignoreBounds=True)  # don't let it affect auto-range
        vb = plot.getViewBox()

        def place(*_):
            (x0, _x1), (_y0, y1) = vb.viewRange()
            text.setPos(x0, y1)

        vb.sigRangeChanged.connect(place)
        place()
        return text

    def _update(self, key, value):
        """Push a sample, redraw its curve, and refresh the readout."""
        self._buf[key].append(value)
        self._curves[key].setData(self.x, list(self._buf[key]))
        if self._kinds[key] == "pct":
            text = f"{self._labels[key]}  {value:.0f}%"
        else:
            text = f"{self._labels[key]}  {fmt_bytes(value)}"
        self._text[key].setText(text)

    def tick(self):
        # --- percentages ---------------------------------------------------
        self._update("cpu", psutil.cpu_percent(interval=None))
        self._update("ram", psutil.virtual_memory().percent)
        gpu, vram = self.gpu.read()
        self._update("gpu", gpu)
        self._update("vram", vram)
        if not self.gpu.ok:
            self._text["gpu"].setText("GPU  n/a")
            self._text["vram"].setText("VRAM  n/a")

        # --- network rates -------------------------------------------------
        net = psutil.net_io_counters()
        self._update("rx", max(0, net.bytes_recv - self._net.bytes_recv) / self.dt)
        self._update("tx", max(0, net.bytes_sent - self._net.bytes_sent) / self.dt)
        self._net = net

        # --- disk rates ----------------------------------------------------
        disk = psutil.disk_io_counters()
        if disk and self._disk:
            dr = max(0, disk.read_bytes - self._disk.read_bytes) / self.dt
            dw = max(0, disk.write_bytes - self._disk.write_bytes) / self.dt
        else:
            dr = dw = 0.0
        self._update("dr", dr)
        self._update("dw", dw)
        self._disk = disk

    def closeEvent(self, event):
        self.timer.stop()
        self.gpu.shutdown()
        super().closeEvent(event)


def app_icon() -> QtGui.QIcon:
    """Build the window/taskbar icon from bundled assets, with theme fallback."""
    icon = QtGui.QIcon()
    icon_dir = os.path.join(BASE_DIR, "assets", "icons")
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        path = os.path.join(icon_dir, f"{APP_ID}-{size}.png")
        if os.path.exists(path):
            icon.addFile(path)
    if icon.isNull():
        svg = os.path.join(BASE_DIR, "assets", "icon.svg")
        if os.path.exists(svg):
            icon.addFile(svg)
    if icon.isNull():  # last resort: an installed theme icon
        icon = QtGui.QIcon.fromTheme(APP_ID)
    return icon


def main():
    ap = argparse.ArgumentParser(description="Tiny efficient system monitor.")
    ap.add_argument("-i", "--interval", type=int, default=1000,
                    help="poll interval in milliseconds (default: 1000)")
    ap.add_argument("-s", "--history", type=int, default=120,
                    help="seconds of history to keep on screen (default: 120)")
    args = ap.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("simple-sys-mon")
    # Wayland uses the desktop-file name as the window app_id, which is how KDE
    # links the window/taskbar entry to the installed .desktop (and its icon).
    app.setDesktopFileName(APP_ID)
    icon = app_icon()
    app.setWindowIcon(icon)

    win = Monitor(interval_ms=max(100, args.interval), history_s=max(10, args.history))
    win.setWindowIcon(icon)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
