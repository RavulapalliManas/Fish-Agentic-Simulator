# Fish Swarm Simulator

A modular fish-school simulator with multiple motion models, timing-based splitting, rotational dynamics, and a PyQt5 interface designed to stay approachable for psychology students.

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Run

```bash
python3 src/main.py
```

## Default Demo

On launch the simulation is stopped.

Default behavior:

- `time_in_center = 5s`
- `time_to_split = 10s`
- `split_ratio = 0.7`
- `rotation_strength = 0.48`
- `shape = triangle`

The default sequence is:

1. Gather at the center
2. Orbit during stabilization
3. Split into left and right subgroups
