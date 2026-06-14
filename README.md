# sys-mon

A tiny, efficient system monitor. Live time-series of **CPU, RAM, GPU, VRAM,
network and disk** — each metric its own color and label. Built on
`psutil` + `pynvml` + `pyqtgraph`, polling on a fixed timer so it stays light
(~0.3% CPU at the default 1 Hz).

## Layout

Eight independent plots in a 2-column grid, each its own color and y-axis:

| | |
|---|---|
| CPU (overall %) | RAM (%) |
| GPU (%) | VRAM (%) |
| Net Down (B/s) | Net Up (B/s) |
| Disk Read (B/s) | Disk Write (B/s) |

Percentages are pinned to 0–100; byte rates auto-scale. Each plot's title
shows its live value; the graph shows the recent history.

## Run

```bash
./run.sh                 # default: 1 s interval, 120 s of history
./run.sh -i 500          # poll every 500 ms
./run.sh -s 300          # keep 5 minutes of history on screen
```

## Install (already done in this repo)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Notes

- **GPU:** monitors the primary NVIDIA GPU via NVML (`nvidia-ml-py`). If no
  NVIDIA GPU is present the GPU/VRAM series simply read 0 and the title shows
  "GPU n/a". Intel/AMD util is not collected (it needs root or vendor tools).
- Lower the poll rate (`-i 2000`) to make it even lighter.
