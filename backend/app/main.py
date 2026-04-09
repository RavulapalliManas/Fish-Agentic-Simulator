"""Main entry point for GUI and headless export workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from renderer import VideoExporter
from utils import StimulusConfig


def _load_config_from_args(args) -> StimulusConfig:
    config = StimulusConfig()
    if args.config_json:
        payload = json.loads(Path(args.config_json).read_text(encoding="utf-8"))
        if "config" in payload and isinstance(payload["config"], dict):
            payload = payload["config"]
        for key, value in payload.items():
            if hasattr(config, key):
                setattr(config, key, value)

    overrides = {
        "video_duration": args.duration,
        "fps": args.fps,
        "output_width": args.width,
        "output_height": args.height,
        "random_seed": args.seed,
        "number_of_agents": args.agents,
        "model_type": args.model,
        "split_ratio": args.split_ratio,
    }
    for key, value in overrides.items():
        if value is not None:
            setattr(config, key, value)
    return config.validate()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fish stimulus generator")
    parser.add_argument("--headless", action="store_true", help="Export a stimulus video without launching the UI")
    parser.add_argument("--config-json", help="Load full parameters from a JSON file or metadata sidecar")
    parser.add_argument("--output", default="output/stimulus.mp4", help="Destination MP4 path")
    parser.add_argument("--duration", type=float, help="Video duration in seconds")
    parser.add_argument("--fps", type=int, help="Frames per second")
    parser.add_argument("--width", type=int, help="Output width")
    parser.add_argument("--height", type=int, help="Output height")
    parser.add_argument("--seed", type=int, help="Random seed")
    parser.add_argument("--agents", type=int, help="Number of agents")
    parser.add_argument("--model", help="Model type")
    parser.add_argument("--split-ratio", type=float, help="Left-group ratio during split")
    args = parser.parse_args()

    if args.headless:
        config = _load_config_from_args(args)
        exporter = VideoExporter(config)
        result = exporter.export(args.output)
        print(f"Saved video: {result.video_path}")
        if result.metadata_path:
            print(f"Saved metadata: {result.metadata_path}")
        return

    from gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
