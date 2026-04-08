# Fish Stimulus Generator

This project is now a deterministic, research-grade stimulus generator for fish behavioral experiments, with the splitting paradigm as the primary target use case.

## What It Does

- Generates `.mp4` videos as the primary output
- Uses a fixed timestep with `dt = 1 / fps`
- Runs fully offscreen during export
- Separates physics, paradigms, rendering, and UI
- Exposes simulation, paradigm, rendering, appearance, and output controls in a PyQt5 interface
- Saves a reproducibility sidecar JSON with each export by default

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Launch the UI

```bash
python3 src/main.py
```

## Headless Export

```bash
python3 src/main.py --headless --output output/stimulus.mp4
```

Optional CLI overrides:

```bash
python3 src/main.py --headless \
  --output output/stimulus.mp4 \
  --duration 10 \
  --fps 60 \
  --width 1280 \
  --height 720 \
  --seed 2024 \
  --agents 48 \
  --model "Hybrid Consensus" \
  --split-ratio 0.7
```

You can also reuse an exported metadata sidecar for exact reproduction:

```bash
python3 src/main.py --headless --config-json output/stimulus.json --output output/replay.mp4
```

## Default Fish-Training Profile

The default configuration is tuned for clear T-maze-style splitting:

- duration: `10s`
- fps: `60`
- resolution: `1280x720`
- split ratio: `0.7`
- strong attractors
- moderate rotation
- tight central aggregation
- stable pause
- clean left/right split
