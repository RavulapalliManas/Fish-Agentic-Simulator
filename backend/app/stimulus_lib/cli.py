"""CLI: render a stimulus spec to lossless frames + a provenance manifest.

    python -m app.stimulus_lib.cli render path/to/spec.json [--out DIR]
"""

from __future__ import annotations

import argparse
import json

from .render import render_experiment
from .spec import load_spec


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="stimulus_lib", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    render_parser = sub.add_parser("render", help="Render a spec to a frame sequence + manifest")
    render_parser.add_argument("spec", help="Path to a .json or .yaml experiment spec")
    render_parser.add_argument("--out", default=None, help="Output directory (default: output/stimuli/<name>)")

    args = parser.parse_args(argv)

    if args.command == "render":
        spec = load_spec(args.spec)
        out_dir = args.out or f"output/stimuli/{spec.name}"
        result = render_experiment(spec, out_dir)
        manifest = result["manifest"]
        print(
            json.dumps(
                {
                    "out_dir": result["out_dir"],
                    "n_frames": result["n_frames"],
                    "config_hash": manifest["config_hash"],
                    "git_commit": manifest["git_commit"],
                    "qa": manifest["qa"],
                    "validation_warnings": manifest["validation_warnings"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
